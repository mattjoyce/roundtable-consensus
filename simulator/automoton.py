from models import AgentActor, Action, ACTION_QUEUE, Proposal
from loguru import logger
import random

def weighted_trait_decision(traits, weights, rng):
    score = sum(traits[t] * weights[t] for t in weights)
    roll = rng.random()
    return roll < score, score, roll

def handle_signal(agent: AgentActor, payload: dict):
    phase_type = payload.get("type")
    
    if phase_type == "Propose":
        return handle_propose(agent, payload)
    elif phase_type == "Feedback":
        return handle_feedback(agent, payload)
    
    logger.debug(f"{agent.agent_id} received unhandled phase signal: {phase_type}")
    return {"ack": True}

def handle_propose(agent: AgentActor, payload: dict):
    profile = agent.metadata.get("protocol_profile", {})
    rng = agent.rng
    tick = payload.get("tick", 0)
    issue_id = payload.get("issue_id", "unknown")

    # Get or initialize phase memory
    memory = agent.memory.setdefault("propose", {})
    has_acted = memory.get("has_acted", False)
    initial_decision = memory.get("initial_decision", None)

    # Traits
    initiative = profile.get("initiative", 0.5)
    compliance = profile.get("compliance", 0.9)
    risk = profile.get("risk_tolerance", 0.2)

    decision_made = None

    if not has_acted:
        # First time decision: Blend initiative + compliance  
        should_submit, score, roll = weighted_trait_decision(
            traits={"initiative": initiative, "compliance": compliance},
            weights={"initiative": 0.8, "compliance": 0.2},
            rng=rng
        )
        
        logger.info(f"[DECISION] {agent.agent_id} first-time scored {score:.2f} vs roll {roll:.2f} "
                   f"→ {'SUBMIT' if should_submit else 'CONSIDER'} | Weights: init=0.8, comp=0.2")
        
        if should_submit:
            decision_made = "submit"
        else:
            # Secondary decision: signal ready vs wait (pure compliance)
            if rng.random() < compliance:
                decision_made = "signal"
                logger.info(f"[DECISION] {agent.agent_id} compliance check → SIGNAL")
            else:
                decision_made = "wait"
                logger.info(f"[DECISION] {agent.agent_id} compliance check → WAIT")
        
        memory["initial_decision"] = decision_made
    else:
        # Retry decision: More compliance-driven with some initiative
        should_retry, score, roll = weighted_trait_decision(
            traits={"compliance": compliance, "initiative": initiative},
            weights={"compliance": 0.7, "initiative": 0.3},
            rng=rng
        )
        
        logger.info(f"[DECISION] {agent.agent_id} retry scored {score:.2f} vs roll {roll:.2f} "
                   f"→ {'RETRY' if should_retry else 'HOLD'} | Weights: comp=0.7, init=0.3")
        
        if should_retry:
            # Decide between submit vs signal
            if rng.random() < 0.5:
                decision_made = "submit"
            else:
                decision_made = "signal"
        else:
            decision_made = "hold"

    if decision_made == "submit":
        proposal = Proposal(
            proposal_id=f"P{agent.agent_id}",
            content="Sample proposal content",
            agent_id=agent.agent_id,
            issue_id=issue_id,
            tick=tick,
            metadata={"origin": "trait:initiative"}
        )
        ACTION_QUEUE.submit(Action(
            type="submit_proposal",
            agent_id=agent.agent_id,
            payload=proposal.model_dump()
        ))
        memory["has_acted"] = True
        logger.info(f"{agent.agent_id} submitted proposal. (tick {tick})")

    elif decision_made == "signal":
        ACTION_QUEUE.submit(Action(
            type="signal_ready",
            agent_id=agent.agent_id,
            payload={"issue_id": issue_id}
        ))
        memory["has_acted"] = True
        logger.info(f"{agent.agent_id} signaled ready. (tick {tick})")

    elif decision_made == "wait":
        logger.info(f"{agent.agent_id} is waiting (passive no-action). (tick {tick})")

    elif decision_made == "hold":
        logger.debug(f"{agent.agent_id} is holding position. (tick {tick})")

    return {"ack": True}

def handle_feedback(agent: AgentActor, payload: dict):
    from models import Action
    issue_id = payload["issue_id"]
    max_feedback = payload.get("max_feedback", 3)
    tick = payload.get("tick", 0)
    
    rng = agent.rng
    own_id = agent.agent_id
    profile = agent.metadata.get("protocol_profile", {})
    
    # Get or initialize feedback memory
    memory = agent.memory.setdefault("feedback", {})
    feedback_given = memory.get("feedback_given", 0)
    
    # Check if already at quota
    if feedback_given >= max_feedback:
        logger.info(f"[FEEDBACK] {agent.agent_id} already at quota ({feedback_given}/{max_feedback})")
        return {"ack": True}
    
    # Use agent traits to determine feedback intent
    sociability = profile.get("sociability", 0.5)
    initiative = profile.get("initiative", 0.5)
    compliance = profile.get("compliance", 0.9)
    
    # Decide if agent will provide feedback this round
    should_give_feedback, score, roll = weighted_trait_decision(
        traits={"sociability": sociability, "initiative": initiative, "compliance": compliance},
        weights={"sociability": 0.5, "initiative": 0.3, "compliance": 0.2},
        rng=rng
    )
    
    if not should_give_feedback:
        logger.info(f"[FEEDBACK] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → NO FEEDBACK | Weights: soc=0.5, init=0.3, comp=0.2")
        return {"ack": True}
    
    # Calculate how many feedbacks to give this round
    remaining_quota = max_feedback - feedback_given
    max_this_round = min(remaining_quota, 3)
    
    # Scale with sociability or use random within bounds
    scaled = int(round(max_this_round * sociability))
    num_feedbacks = max(1, min(scaled, max_this_round))
    
    logger.info(f"[FEEDBACK] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → PROVIDING {num_feedbacks} FEEDBACK(S)")

    # Sample target proposal IDs (fake for now - excluding own)
    possible_targets = [f"PAgent_{i}" for i in range(10) if f"Agent_{i}" != own_id]
    targets = rng.sample(possible_targets, min(num_feedbacks, len(possible_targets)))
    
    # Submit feedback actions
    for pid in targets:
        ACTION_QUEUE.submit(Action(
            type="feedback",
            agent_id=own_id,
            payload={
                "target_proposal_id": pid,
                "comment": f"Agent {own_id} thinks {pid} lacks clarity.",
                "tick": tick,
                "issue_id": issue_id
            }
        ))
    
    # Update memory to track feedback count
    memory["feedback_given"] = feedback_given + len(targets)
    
    logger.info(f"[FEEDBACK] {agent.agent_id} submitted {len(targets)} feedbacks | Total: {memory['feedback_given']}/{max_feedback}")
    return {"ack": True}
