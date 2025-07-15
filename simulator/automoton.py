from models import AgentActor, Action, ACTION_QUEUE, Proposal
from simlog import log_event, logger, LogEntry, EventType, PhaseType, LogLevel
import random
from utils import linear, sigmoid, ACTIVATIONS, generate_lorem_content

# Trait default values for consistency
TRAIT_DEFAULTS = {
    "initiative": 0.5,
    "compliance": 0.9,
    "risk_tolerance": 0.2,
    "persuasiveness": 0.5,
    "sociability": 0.5,
    "adaptability": 0.5,
    "self_interest": 0.5,
    "consistency": 0.5
}

def extract_traits(profile: dict) -> dict:
    """Extract all traits from profile with consistent defaults."""
    return {trait: profile.get(trait, default) for trait, default in TRAIT_DEFAULTS.items()}

def signal_ready_action(agent_id: str, issue_id: str) -> None:
    """Submit a signal_ready action to the queue."""
    ACTION_QUEUE.submit(Action(
        type="signal_ready",
        agent_id=agent_id,
        payload={"issue_id": issue_id}
    ))

def calculate_content_traits(profile: dict) -> tuple[float, float, float]:
    """Calculate thoroughness, verbosity, and trait_factor for content sizing."""
    thoroughness = profile.get("compliance", 0.5) + profile.get("consistency", 0.5)
    verbosity = profile.get("sociability", 0.5)
    return thoroughness, verbosity

def get_phase_memory(agent, phase_name: str) -> dict:
    """Get or initialize phase-specific memory for an agent."""
    return agent.memory.setdefault(phase_name, {})


def weighted_trait_decision(traits, weights, rng, activation: str = "linear"):
    raw_score = sum(traits[t] * weights[t] for t in weights)
    activation_fn = ACTIVATIONS.get(activation, linear)
    activated_score = activation_fn(raw_score)
    roll = rng.random()
    return roll < activated_score, activated_score, roll

def handle_signal(agent: AgentActor, payload: dict):
    phase_type = payload.get("type")
    
    if phase_type == "Propose":
        return handle_propose(agent, payload)
    elif phase_type == "Feedback":
        return handle_feedback(agent, payload)
    elif phase_type == "Revise":
        return handle_revise(agent, payload)
    elif phase_type == "Stake":
        return handle_stake(agent, payload)
    
    logger.debug(f"{agent.agent_id} received unhandled phase signal: {phase_type}")
    return {"ack": True}

def handle_propose(agent: AgentActor, payload: dict):
    profile = agent.metadata.get("protocol_profile", {})
    rng = agent.rng
    tick = payload.get("tick", 0)
    issue_id = payload.get("issue_id", "unknown")

    # Get or initialize phase memory
    memory = get_phase_memory(agent, "propose")
    has_acted = memory.get("has_acted", False)
    initial_decision = memory.get("initial_decision", None)

    # Extract traits with consistent defaults
    traits = extract_traits(profile)
    initiative = traits["initiative"]
    compliance = traits["compliance"]
    risk = traits["risk_tolerance"]
    persuasiveness = traits["persuasiveness"]

    decision_made = None

    if not has_acted:
        # First time decision: Blend initiative + compliance + persuasiveness
        should_submit, score, roll = weighted_trait_decision(
            traits={"initiative": initiative, "compliance": compliance, "persuasiveness": persuasiveness},
            weights={"initiative": 0.6, "compliance": 0.2, "persuasiveness": 0.2},
            rng=rng,
            activation="sigmoid"  # More decisive for extreme trait combinations
        )
        
        logger.info(f"[DECISION] {agent.agent_id} first-time scored {score:.2f} vs roll {roll:.2f} "
                   f"→ {'SUBMIT' if should_submit else 'CONSIDER'} | Weights: init=0.6, comp=0.2, pers=0.2")
        
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
        # Retry decision: More compliance-driven with initiative and persuasiveness
        should_retry, score, roll = weighted_trait_decision(
            traits={"compliance": compliance, "initiative": initiative, "persuasiveness": persuasiveness},
            weights={"compliance": 0.5, "initiative": 0.3, "persuasiveness": 0.2},
            rng=rng,
            activation="linear"  # Keep linear for retry decisions
        )
        
        logger.info(f"[DECISION] {agent.agent_id} retry scored {score:.2f} vs roll {roll:.2f} "
                   f"→ {'RETRY' if should_retry else 'HOLD'} | Weights: comp=0.5, init=0.3, pers=0.2")
        
        if should_retry:
            # Decide between submit vs signal using persuasiveness
            # High persuasiveness = more likely to submit rather than just signal
            if rng.random() < (0.3 + persuasiveness * 0.4):  # 30-70% range based on persuasiveness
                decision_made = "submit"
            else:
                decision_made = "signal"
        else:
            decision_made = "hold"

    if decision_made == "submit":
        
        # Use traits to determine proposal size
        thoroughness, verbosity = calculate_content_traits(profile)
        initiative_boost = traits["initiative"] * 0.3  # Initiative agents may write more detailed proposals
        trait_factor = (thoroughness + verbosity + initiative_boost) / 3.3  # Combine traits, normalize
        
        # Proposal size influenced by traits (30-70 words)
        min_words = 30
        max_words = 70
        proposal_word_count = int(min_words + (trait_factor * (max_words - min_words)))
        
        content = generate_lorem_content(rng, proposal_word_count)
        
        proposal = Proposal(
            proposal_id=0,  # Placeholder - will be assigned by bureau
            content=content,
            agent_id=agent.agent_id,
            issue_id=issue_id,
            tick=tick,
            metadata={"origin": "trait:initiative"},
            author=agent.agent_id,
            author_type="agent"
        )
        ACTION_QUEUE.submit(Action(
            type="submit_proposal",
            agent_id=agent.agent_id,
            payload=proposal.model_dump()
        ))
        memory["has_acted"] = True
        logger.info(f"{agent.agent_id} submitted proposal. (tick {tick}) [Content: {len(content.split())} words, {len(content)} chars] (trait_factor={trait_factor:.2f})")

    elif decision_made == "signal":
        signal_ready_action(agent.agent_id, issue_id)
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
    memory = get_phase_memory(agent, "feedback")
    feedback_given = memory.get("feedback_given", 0)
    
    # Extract traits with consistent defaults
    traits = extract_traits(profile)
    sociability = traits["sociability"]
    initiative = traits["initiative"]
    compliance = traits["compliance"]
    persuasiveness = traits["persuasiveness"]
    
    # Check if already at quota
    if feedback_given >= max_feedback:
        # Store in memory that agent has reached quota
        memory["quota_reached"] = True
        
        # Use compliance trait to decide whether to respect quota (heavily weighted toward compliance)
        # Only very low compliance agents (~<0.1) should attempt quota violations
        should_respect_quota, compliance_score, compliance_roll = weighted_trait_decision(
            traits={"compliance": compliance},
            weights={"compliance": 1.0},
            rng=rng,
            activation="sigmoid"  # Strong compliance should be very decisive
        )
        
        # Additional check: make violations extremely rare (only when compliance < 0.15 AND random chance)
        if not should_respect_quota and (compliance > 0.15 or rng.random() < 0.9):
            should_respect_quota = True  # Force compliance for testing simulation
        
        if should_respect_quota:
            logger.info(f"[FEEDBACK] {agent.agent_id} already at quota ({feedback_given}/{max_feedback}) - respects limit (compliance {compliance_score:.2f} vs roll {compliance_roll:.2f})")
            return {"ack": True}
        else:
            logger.info(f"[FEEDBACK] {agent.agent_id} already at quota ({feedback_given}/{max_feedback}) - attempts anyway (compliance {compliance_score:.2f} vs roll {compliance_roll:.2f})")
            # Continue to decision logic below
    
    # Decide if agent will provide feedback this round
    should_give_feedback, score, roll = weighted_trait_decision(
        traits={"sociability": sociability, "initiative": initiative, "compliance": compliance, "persuasiveness": persuasiveness},
        weights={"sociability": 0.4, "initiative": 0.25, "compliance": 0.2, "persuasiveness": 0.15},
        rng=rng,
        activation="linear"  # Keep linear for general participation decisions
    )
    
    if not should_give_feedback:
        logger.info(f"[FEEDBACK] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → NO FEEDBACK | Weights: soc=0.4, init=0.25, comp=0.2, pers=0.15")
        return {"ack": True}
    
    # Calculate how many feedbacks to give this round
    remaining_quota = max_feedback - feedback_given
    max_this_round = min(remaining_quota, 3)
    
    # If agent is at quota, they may still try 1 feedback (will be rejected)
    if remaining_quota <= 0:
        num_feedbacks = 1
        logger.info(f"[FEEDBACK] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → OVER-QUOTA ATTEMPT (will be rejected)")
    else:
        # Scale with sociability and persuasiveness - more persuasive agents give more feedback
        social_factor = (sociability * 0.7 + persuasiveness * 0.3)  # Blend social engagement with persuasive drive
        scaled = int(round(max_this_round * social_factor))
        num_feedbacks = max(1, min(scaled, max_this_round))
        logger.info(f"[FEEDBACK] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → PROVIDING {num_feedbacks} FEEDBACK(S) (social_factor={social_factor:.2f})")

    # Sample target proposal IDs from actual proposals in the system
    # Get all available proposals from the agent-to-proposal mapping
    all_proposals = payload.get("all_proposals", [])  # Should be passed from consensus system
    own_proposal_id = payload.get("current_proposal_id")
    
    # Filter out own proposal for feedback targets
    possible_targets = [pid for pid in all_proposals if pid != own_proposal_id]
    targets = rng.sample(possible_targets, min(num_feedbacks, len(possible_targets))) if possible_targets else []
    
    # Submit feedback actions
    for pid in targets:
        ACTION_QUEUE.submit(Action(
            type="feedback",
            agent_id=own_id,
            payload={
                "target_proposal_id": pid,
                "comment": f"Agent {own_id} thinks {pid} {'needs improvement' if persuasiveness > 0.6 else 'lacks clarity'}.",
                "tick": tick,
                "issue_id": issue_id
            }
        ))
    
    # Update memory to track feedback count (only if within quota)
    if remaining_quota > 0:
        memory["feedback_given"] = feedback_given + len(targets)
        logger.info(f"[FEEDBACK] {agent.agent_id} submitted {len(targets)} feedbacks | Total: {memory['feedback_given']}/{max_feedback}")
    else:
        logger.info(f"[FEEDBACK] {agent.agent_id} attempted {len(targets)} over-quota feedbacks | Still at: {feedback_given}/{max_feedback}")
    return {"ack": True}

def handle_revise(agent: AgentActor, payload: dict):
    """Handle REVISE phase signals for agent to revise their own proposals based on feedback."""
    from models import Action
    
    issue_id = payload.get("issue_id", "unknown")
    tick = payload.get("tick", 0)
    feedback_received = payload.get("feedback_received", [])  # Feedback on agent's proposal
    rng = agent.rng
    profile = agent.metadata.get("protocol_profile", {})
    
    # Get or initialize revise memory
    memory = get_phase_memory(agent, "revise")
    has_revised = memory.get("has_revised", False)
    
    # Extract traits with consistent defaults
    traits = extract_traits(profile)
    adaptability = traits["adaptability"]
    self_interest = traits["self_interest"]
    compliance = traits["compliance"]
    consistency = traits["consistency"]
    risk_tolerance = traits["risk_tolerance"]
    persuasiveness = traits["persuasiveness"]
    
    # Check if agent has feedback on their proposal
    if not feedback_received:
        # For testing: Make agents more likely to revise even without feedback
        # Use a combination of traits to decide whether to make a "preemptive" revision
        should_revise_anyway, score, roll = weighted_trait_decision(
            traits={"adaptability": adaptability, "initiative": traits["initiative"], "persuasiveness": persuasiveness},
            weights={"adaptability": 0.6, "initiative": 0.25, "persuasiveness": 0.15},
            rng=rng,
            activation="linear"  # Preemptive revisions should be gradual decisions
        )
        
        if should_revise_anyway:
            # Make a preemptive revision (simulating self-improvement)
            delta_factor = (adaptability * 0.6 + risk_tolerance * 0.4)
            delta = max(0.1, min(1.0, 0.1 + delta_factor * 0.6))  # Smaller deltas for preemptive revisions
            
            # Generate bigger revised content using lorem ipsum
            
            # Use traits to determine revision size - more thorough agents write longer revisions
            thoroughness, verbosity = calculate_content_traits(profile)
            trait_factor = (thoroughness + verbosity) / 3.0  # Combine traits, normalize
            
            # Base revision size influenced by traits (20-80 words)
            min_words = 20
            max_words = 80
            revision_word_count = int(min_words + (trait_factor * (max_words - min_words)))
            
            lorem_content = generate_lorem_content(rng, revision_word_count)
            new_content = f"REVISED (Δ={delta:.2f}): {lorem_content}"
            
            ACTION_QUEUE.submit(Action(
                type="revise",
                agent_id=agent.agent_id,
                payload={
                    "proposal_id": f"P{agent.agent_id}",
                    "new_content": new_content,
                    "delta": delta,
                    "tick": tick,
                    "issue_id": issue_id
                }
            ))
            
            memory["has_revised"] = True
            memory["revision_delta"] = delta
            
            logger.info(f"[REVISE] {agent.agent_id} no feedback received, making preemptive revision (Δ={delta:.2f}) | adaptability={adaptability:.2f}, score={score:.2f} vs roll={roll:.2f} [Content: {len(lorem_content.split())} words, {len(new_content)} chars] (trait_factor={trait_factor:.2f})")
            return {"ack": True}
        
        # Fall back to participation-based ready signal (not about rule compliance)
        should_signal, score2, roll2 = weighted_trait_decision(
            traits={"compliance": compliance, "initiative": traits["initiative"], "sociability": traits["sociability"]},
            weights={"compliance": 0.5, "initiative": 0.3, "sociability": 0.2},  # Compliance = process participation, not rule-following
            rng=rng,
            activation="linear"  # Participation decisions should be gradual
        )
        
        if should_signal:
            signal_ready_action(agent.agent_id, issue_id)
            logger.info(f"[REVISE] {agent.agent_id} no feedback received, signaling ready (participation {score2:.2f} vs roll {roll2:.2f}) | Weights: comp=0.5, init=0.3, soc=0.2")
        else:
            logger.info(f"[REVISE] {agent.agent_id} no feedback received, waiting (participation {score2:.2f} vs roll {roll2:.2f}) | Weights: comp=0.5, init=0.3, soc=0.2")
        
        return {"ack": True}
    
    # Agent received feedback - decide whether to revise
    if has_revised:
        # Already revised once this phase, use consistency trait to avoid over-revising
        should_revise_again, score, roll = weighted_trait_decision(
            traits={"consistency": 1 - consistency, "adaptability": adaptability, "persuasiveness": persuasiveness},  # Lower consistency = more likely to revise again
            weights={"consistency": 0.6, "adaptability": 0.25, "persuasiveness": 0.15},
            rng=rng,
            activation="linear"  # Multi-revision decisions should be gradual
        )
        
        if not should_revise_again:
            signal_ready_action(agent.agent_id, issue_id)
            logger.info(f"[REVISE] {agent.agent_id} already revised, signaling ready (consistency check {score:.2f} vs roll {roll:.2f})")
            return {"ack": True}
    
    # First revision or willing to revise again - evaluate feedback
    should_revise, score, roll = weighted_trait_decision(
        traits={
            "adaptability": adaptability,
            "self_interest": self_interest,
            "risk_tolerance": risk_tolerance,
            "persuasiveness": persuasiveness
        },
        weights={
            "adaptability": 0.4,      # Main driver for accepting feedback
            "self_interest": 0.25,    # Self-interest may resist change
            "risk_tolerance": 0.2,    # Willingness to take revision risk
            "persuasiveness": 0.15    # Persuasive agents want to improve their position
        },
        rng=rng,
        activation="sigmoid"  # Feedback response should be decisive
    )
    
    if not should_revise:
        signal_ready_action(agent.agent_id, issue_id)
        logger.info(f"[REVISE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → NO REVISION | Weights: adapt=0.4, self=0.25, risk=0.2, pers=0.15")
        return {"ack": True}
    
    # Decide revision size (delta) based on adaptability and risk tolerance
    # Higher adaptability + risk tolerance = larger revisions
    delta_factor = (adaptability * 0.6 + risk_tolerance * 0.4)
    delta = max(0.1, min(1.0, 0.2 + delta_factor * 0.8))  # Range [0.1, 1.0]
    
    # Generate bigger revised content using lorem ipsum
    
    # Use traits to determine revision size for feedback-based revisions
    thoroughness, verbosity = calculate_content_traits(profile)
    adaptability_boost = traits["adaptability"] * 0.5  # Adaptable agents may write more when responding to feedback
    persuasive_boost = persuasiveness * 0.3  # Persuasive agents write more to convince
    trait_factor = (thoroughness + verbosity + adaptability_boost + persuasive_boost) / 3.8  # Combine traits, normalize
    
    # Feedback revisions tend to be more substantial (30-90 words)
    min_words = 30
    max_words = 90
    revision_word_count = int(min_words + (trait_factor * (max_words - min_words)))
    
    lorem_content = generate_lorem_content(rng, revision_word_count)
    new_content = f"FEEDBACK-REVISED (Δ={delta:.2f}): {lorem_content}"
    
    # Submit revision action
    ACTION_QUEUE.submit(Action(
        type="revise",
        agent_id=agent.agent_id,
        payload={
            "new_content": new_content,
            "delta": delta,
            "tick": tick,
            "issue_id": issue_id
        }
    ))
    
    # Update memory
    memory["has_revised"] = True
    memory["revision_delta"] = delta
    
    logger.info(f"[REVISE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → REVISING (Δ={delta:.2f}) | Weights: adapt=0.4, self=0.25, risk=0.2, pers=0.15 [Content: {len(lorem_content.split())} words, {len(new_content)} chars] (trait_factor={trait_factor:.2f})")
    
    return {"ack": True}


def handle_stake(agent: AgentActor, payload: dict):
    """Handle STAKE phase signals for agents to decide on conviction-based staking."""
    from models import Action
    
    issue_id = payload.get("issue_id", "unknown")
    tick = payload.get("tick", 0)
    round_number = payload.get("round_number", 1)
    conviction_params = payload.get("conviction_params", {})
    
    rng = agent.rng
    profile = agent.metadata.get("protocol_profile", {})
    
    # Get or initialize stake memory
    memory = get_phase_memory(agent, "stake")
    stakes_this_round = memory.get(f"round_{round_number}_stakes", 0)
    
    # Extract traits with consistent defaults
    traits = extract_traits(profile)
    self_interest = traits["self_interest"]
    risk_tolerance = traits["risk_tolerance"]
    compliance = traits["compliance"]
    sociability = traits["sociability"]
    initiative = traits["initiative"]
    consistency = traits["consistency"]
    adaptability = traits["adaptability"]
    persuasiveness = traits["persuasiveness"]
    
    # Get current balance from memory or assume it's tracked elsewhere
    # For now, we'll use a simple heuristic based on traits
    
    # Decision 1: Should agent stake this round?
    should_stake, score, roll = weighted_trait_decision(
        traits={
            "risk_tolerance": risk_tolerance,     # Higher = more likely to stake
            "initiative": initiative,             # Higher = more proactive
            "self_interest": self_interest,       # Higher = more motivated
            "compliance": compliance              # Higher = follows protocol
        },
        weights={
            "risk_tolerance": 0.4, 
            "initiative": 0.3, 
            "self_interest": 0.2, 
            "compliance": 0.1
        },
        rng=rng,
        activation="sigmoid"  # High-stakes financial decision needs clear commitment
    )
    
    if not should_stake:
        # Signal ready without staking
        signal_ready_action(agent.agent_id, issue_id)
        logger.info(f"[STAKE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → NO STAKE | Round {round_number} | Weights: risk=0.4, init=0.3, self=0.2, comp=0.1")
        return {"ack": True}
    
    # Decision 2: Choose proposal to support
    own_proposal_id = payload.get("current_proposal_id", f"P{agent.agent_id}")
    
    # First check: stake on own proposal?
    stake_on_own, score, roll = weighted_trait_decision(
        traits={
            "self_interest": self_interest,       # Higher = own proposal
            "consistency": consistency,           # Higher = stick with own
            "risk_tolerance": risk_tolerance,     # Higher = confident in own
            "persuasiveness": persuasiveness      # Higher = believe in own proposal's merit
        },
        weights={
            "self_interest": 0.4, 
            "consistency": 0.25, 
            "risk_tolerance": 0.2,
            "persuasiveness": 0.15
        },
        rng=rng,
        activation="sigmoid"  # Strong conviction should be decisive
    )
    
    if stake_on_own:
        target_proposal_id = own_proposal_id
        proposal_choice_reason = "own_proposal"
        logger.info(f"[STAKE] {agent.agent_id} proposal choice: own ({score:.2f} vs {roll:.2f}) | Weights: self=0.4, cons=0.25, risk=0.2, pers=0.15")
    else:
        # Check: stake on others' proposals?
        stake_on_others, score2, roll2 = weighted_trait_decision(
            traits={
                "sociability": sociability,          # Higher = support community
                "adaptability": adaptability,        # Higher = hedge bets
                "persuasiveness": persuasiveness     # Higher = recognize good proposals
            },
            weights={
                "sociability": 0.5, 
                "adaptability": 0.3,
                "persuasiveness": 0.2
            },
            rng=rng,
            activation="linear"  # Community support should be gradual
        )
        
        if stake_on_others:
            # Sample from other agents' proposals
            all_proposals = payload.get("all_proposals", [])  # Should be passed from consensus system
            possible_proposals = [pid for pid in all_proposals if pid != own_proposal_id]
            target_proposal_id = rng.choice(possible_proposals) if possible_proposals else own_proposal_id
            proposal_choice_reason = "sampled_other"
            logger.info(f"[STAKE] {agent.agent_id} proposal choice: others ({score2:.2f} vs {roll2:.2f}) | Weights: soc=0.5, adapt=0.3, pers=0.2")
        else:
            # Default to own if both fail
            target_proposal_id = own_proposal_id
            proposal_choice_reason = "default_own"
            logger.info(f"[STAKE] {agent.agent_id} proposal choice: default to own (others failed: {score2:.2f} vs {roll2:.2f})")
    
    # Decision 3: Calculate stake amount (trait-based with balance knowledge)
    current_balance = payload.get("current_balance", 0)
    
    # Pure trait-driven stake percentage
    base_percentage = risk_tolerance * 0.6
    persuasive_boost = persuasiveness * 0.3  # Up to 30% additional stake for highly persuasive agents
    stake_percentage = min(0.8, base_percentage + persuasive_boost)  # Cap at 80%
    
    # Apply trait-driven percentage to actual balance
    stake_amount = max(1, int(current_balance * stake_percentage))
    
    # Only constraint: don't stake more than available balance
    stake_amount = min(stake_amount, current_balance)
    
    # Submit stake action
    ACTION_QUEUE.submit(Action(
        type="stake",
        agent_id=agent.agent_id,
        payload={
            "proposal_id": target_proposal_id,
            "stake_amount": stake_amount,
            "round_number": round_number,
            "tick": tick,
            "issue_id": issue_id,
            "choice_reason": proposal_choice_reason
        }
    ))
    
    # Always signal ready after staking
    signal_ready_action(agent.agent_id, issue_id)
    
    # Update memory
    memory[f"round_{round_number}_stakes"] = stakes_this_round + 1
    memory[f"round_{round_number}_amount"] = stake_amount
    memory[f"round_{round_number}_target"] = target_proposal_id
    
    logger.info(f"[STAKE] {agent.agent_id} → STAKING {stake_amount} CP | Round {round_number} | Balance: {current_balance} CP | Target: {target_proposal_id} ({proposal_choice_reason}) | Stake %: {stake_percentage:.2f}")
    
    return {"ack": True}
