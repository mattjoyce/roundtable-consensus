from models import AgentActor, Action, ACTION_QUEUE, Proposal
from loguru import logger
import random

def weighted_trait_decision(traits: dict, weights: dict, rng: random.Random, threshold: float = 0.5) -> tuple[bool, float, float]:
    """
    Compute a blended trait decision and return True if agent takes action.
    Returns (decision, score, roll) for logging purposes.
    """
    assert abs(sum(weights.values()) - 1.0) < 1e-6, "Weights must sum to 1.0"
    score = sum(traits[trait] * weight for trait, weight in weights.items())
    roll = rng.random()
    decision = roll < score * threshold
    return decision, score, roll

def handle_signal(agent: AgentActor, payload: dict):
    phase_type = payload.get("type")
    
    if phase_type == "Propose":
        return handle_propose(agent, payload)
    
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
            rng=rng,
            threshold=1.0
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
            rng=rng,
            threshold=0.8  # Lower threshold for retries
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
