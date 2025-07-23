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

def calculate_strategic_cp_reserve(traits: dict, current_balance: int, proposal_self_stake: int) -> int:
    """Calculate how much CP to reserve for staking based on strategic traits."""
    
    # Strategic thinking traits (reinterpreted)
    self_interest = traits["self_interest"]      # Higher = more strategic about resources
    risk_tolerance = traits["risk_tolerance"]    # Lower = more conservative with CP
    consistency = traits["consistency"]          # Higher = plans ahead better
    
    # Calculate strategic reserve factor
    strategic_factor = (
        self_interest * 0.4 +           # Self-interested agents plan better
        (1 - risk_tolerance) * 0.4 +    # Risk-averse agents save more
        consistency * 0.2               # Consistent agents plan ahead
    )
    
    # Reserve 20-80% of CP for future staking based on strategic thinking
    reserve_percentage = 0.2 + (strategic_factor * 0.6)
    
    # Estimate needed CP for staking (assume 3-5 staking rounds, each ~20-50 CP)
    estimated_staking_need = proposal_self_stake * 2  # Conservative estimate
    
    # Reserve the higher of percentage-based or absolute estimate
    percentage_reserve = int(current_balance * reserve_percentage)
    reserve_amount = max(percentage_reserve, estimated_staking_need)
    
    # Don't reserve more than current balance
    return min(reserve_amount, current_balance)


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
        
        logger.debug(f"[DECISION] {agent.agent_id} first-time scored {score:.2f} vs roll {roll:.2f} "
                   f"→ {'SUBMIT' if should_submit else 'CONSIDER'} | Weights: init=0.6, comp=0.2, pers=0.2")
        
        if should_submit:
            decision_made = "submit"
        else:
            # Secondary decision: signal ready vs wait (pure compliance)
            if rng.random() < compliance:
                decision_made = "signal"
                logger.debug(f"[DECISION] {agent.agent_id} compliance check → SIGNAL")
            else:
                decision_made = "wait"
                logger.debug(f"[DECISION] {agent.agent_id} compliance check → WAIT")
        
        memory["initial_decision"] = decision_made
    else:
        # Retry decision: More compliance-driven with initiative and persuasiveness
        should_retry, score, roll = weighted_trait_decision(
            traits={"compliance": compliance, "initiative": initiative, "persuasiveness": persuasiveness},
            weights={"compliance": 0.5, "initiative": 0.3, "persuasiveness": 0.2},
            rng=rng,
            activation="linear"  # Keep linear for retry decisions
        )
        
        logger.debug(f"[DECISION] {agent.agent_id} retry scored {score:.2f} vs roll {roll:.2f} "
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
        
        # Generate proposal content - use LLM if enabled in payload, otherwise lorem ipsum
        use_llm = payload.get('use_llm_proposal', False)
        
        if use_llm:
            # TODO: Get actual problem statement from current issue
            problem_statement = "A technology issue requires collaborative solution"
            model = payload.get('model', 'gemma3n:e4b')  # Get model from payload
            content = generate_proposal_content(agent, problem_statement, traits, model)
        else:
            # Original lorem ipsum generation
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
        memory["original_content"] = content  # Store for delta calculation in revisions
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
    use_llm = payload.get('use_llm_feedback', False)
    all_proposal_contents = payload.get("all_proposal_contents", {})  # Dict mapping proposal_id -> content
    
    for pid in targets:
        # Generate feedback content
        if use_llm and pid in all_proposal_contents:
            model = payload.get('model', 'gemma3n:e4b')  # Get model from payload
            
            # Build rich context for feedback
            from context_builder import enhance_context_for_call
            enhanced_context = enhance_context_for_call(
                agent, "", "feedback", 
                state=payload.get('state'),
                all_proposal_contents=all_proposal_contents,
                tick=tick,
                agent_pool=payload.get('agent_pool')
            )
            
            comment = generate_feedback_content(agent, enhanced_context, all_proposal_contents[pid], traits, model)
        else:
            # Fall back to simple template
            comment = f"Agent {own_id} thinks {pid} {'needs improvement' if persuasiveness > 0.6 else 'lacks clarity'}."
        
        ACTION_QUEUE.submit(Action(
            type="feedback",
            agent_id=own_id,
            payload={
                "target_proposal_id": pid,
                "comment": comment,
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

def generate_proposal_content(agent: AgentActor, problem_statement: str, traits: dict, model: str = "gemma3n:e4b") -> str:
    """Generate proposal content using LLM based on agent traits and problem statement."""
    try:
        from llm import one_shot
        from prompts import load_agent_system_prompt, load_prompt
        
        system_prompt = load_agent_system_prompt(traits)
        context = problem_statement
        user_prompt = load_prompt("proposal")
        
        # Use agent's RNG seed for deterministic generation
        seed = agent.seed if hasattr(agent, 'seed') else hash(agent.agent_id) % 2**31
        
        return one_shot(system_prompt, context, user_prompt, model=model, seed=seed)
    except Exception as e:
        # Fall back to lorem ipsum if LLM fails
        from utils import generate_lorem_content
        return generate_lorem_content(agent.rng, 50)

def generate_feedback_content(agent: AgentActor, context: str, proposal_content: str, traits: dict, model: str = "gemma3n:e4b") -> str:
    """Generate feedback content using LLM with enhanced context and specific proposal."""
    try:
        from llm import one_shot
        from prompts import load_agent_system_prompt, load_prompt
        
        system_prompt = load_agent_system_prompt(traits)
        user_prompt = f"{load_prompt('feedback')}\n\nSpecific proposal to review:\n{proposal_content}"
        
        # Use agent's RNG seed + proposal hash for deterministic but varied generation
        base_seed = agent.seed if hasattr(agent, 'seed') else hash(agent.agent_id) % 2**31
        proposal_hash = hash(proposal_content) % 1000
        seed = base_seed + proposal_hash
        
        return one_shot(system_prompt, context, user_prompt, model=model, seed=seed)
    except Exception as e:
        # Fall back to simple template if LLM fails
        persuasiveness = traits.get('persuasiveness', 0.5)
        return f"Agent {agent.agent_id} thinks this proposal {'needs improvement' if persuasiveness > 0.6 else 'lacks clarity'}."

def handle_revise(agent: AgentActor, payload: dict):
    """Handle REVISE phase signals for agent to revise their own proposals based on feedback."""
    from models import Action
    from text_delta import sentence_sequence_delta
    
    issue_id = payload.get("issue_id", "unknown")
    tick = payload.get("tick", 0)
    feedback_received = payload.get("feedback_received", [])  # Feedback on agent's proposal
    proposal_self_stake = payload.get("proposal_self_stake", 50)  # Get from config
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
    
    # Get current balance for strategic planning
    current_balance = payload.get("current_balance", 150)  # Get from signal payload
    
    # Calculate strategic CP reserve
    strategic_reserve = calculate_strategic_cp_reserve(traits, current_balance, proposal_self_stake)
    available_for_revision = current_balance - strategic_reserve
    
    logger.debug(f"[REVISE] {agent.agent_id} strategic planning: balance={current_balance}, reserve={strategic_reserve}, available={available_for_revision} | self_interest={self_interest:.2f}, risk_tolerance={risk_tolerance:.2f}, consistency={consistency:.2f}")
    
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
            # Get original content from memory
            propose_memory = get_phase_memory(agent, "propose")
            original_content = propose_memory.get("original_content", "")
            
            if not original_content:
                logger.warning(f"[REVISE] {agent.agent_id} cannot revise - no original content found in memory")
                signal_ready_action(agent.agent_id, issue_id)
                return {"ack": True}
            
            # Generate revised content using lorem ipsum (LLM module will replace this later)
            # Use traits to determine revision size - more thorough agents write longer revisions
            thoroughness, verbosity = calculate_content_traits(profile)
            trait_factor = (thoroughness + verbosity) / 3.0  # Combine traits, normalize
            
            # Base revision size influenced by traits (20-80 words)
            min_words = 20
            max_words = 80
            revision_word_count = int(min_words + (trait_factor * (max_words - min_words)))
            
            lorem_content = generate_lorem_content(rng, revision_word_count)
            new_content = f"REVISED: {lorem_content}"
            
            # Calculate preview delta for affordability check
            preview_delta = sentence_sequence_delta(original_content, new_content)
            
            # Strategic CP check: can agent afford this revision?
            estimated_cost = int(proposal_self_stake * preview_delta)
            if estimated_cost > available_for_revision:
                logger.info(f"[REVISE] {agent.agent_id} strategic holdback: preemptive revision estimated cost {estimated_cost} CP (Δ={preview_delta:.3f}), only {available_for_revision} available (reserved {strategic_reserve} CP for staking)")
                signal_ready_action(agent.agent_id, issue_id)
                return {"ack": True}
            
            ACTION_QUEUE.submit(Action(
                type="revise",
                agent_id=agent.agent_id,
                payload={
                    "proposal_id": f"P{agent.agent_id}",
                    "new_content": new_content,
                    "tick": tick,
                    "issue_id": issue_id
                }
            ))
            
            memory["has_revised"] = True
            memory["preview_delta"] = preview_delta  # Store preview for debugging
            
            logger.info(f"[REVISE] {agent.agent_id} no feedback received, making preemptive revision (estimated Δ={preview_delta:.3f}, cost={estimated_cost}CP) | adaptability={adaptability:.2f}, score={score:.2f} vs roll={roll:.2f} [Content: {len(lorem_content.split())} words, {len(new_content)} chars] (trait_factor={trait_factor:.2f})")
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
    
    # Get original content from memory for delta calculation
    propose_memory = get_phase_memory(agent, "propose")
    original_content = propose_memory.get("original_content", "")
    
    if not original_content:
        logger.warning(f"[REVISE] {agent.agent_id} cannot revise - no original content found in memory")
        signal_ready_action(agent.agent_id, issue_id)
        return {"ack": True}
    
    # Generate revised content using lorem ipsum (LLM module will replace this later)
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
    new_content = f"FEEDBACK-REVISED: {lorem_content}"
    
    # Calculate preview delta for affordability check
    preview_delta = sentence_sequence_delta(original_content, new_content)
    
    # Strategic CP check: can agent afford this revision?
    estimated_cost = int(proposal_self_stake * preview_delta)
    if estimated_cost > available_for_revision:
        logger.info(f"[REVISE] {agent.agent_id} strategic holdback: feedback revision estimated cost {estimated_cost} CP (Δ={preview_delta:.3f}), only {available_for_revision} available (reserved {strategic_reserve} CP for staking)")
        signal_ready_action(agent.agent_id, issue_id)
        return {"ack": True}
    
    # Submit revision action
    ACTION_QUEUE.submit(Action(
        type="revise",
        agent_id=agent.agent_id,
        payload={
            "new_content": new_content,
            "tick": tick,
            "issue_id": issue_id
        }
    ))
    
    # Update memory
    memory["has_revised"] = True
    memory["preview_delta"] = preview_delta  # Store preview for debugging
    
    logger.info(f"[REVISE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → REVISING (estimated Δ={preview_delta:.3f}, cost={estimated_cost}CP) | Weights: adapt=0.4, self=0.25, risk=0.2, pers=0.15 [Content: {len(lorem_content.split())} words, {len(new_content)} chars] (trait_factor={trait_factor:.2f})")
    
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
    
    # Decision 1.5: Consider switching existing stakes before new staking
    current_conviction = payload.get("current_conviction", {})  # agent_id -> proposal_id -> conviction_amount
    agent_conviction = current_conviction.get(agent.agent_id, {})
    
    if agent_conviction:  # Agent has existing stakes to potentially switch
        # Check if agent should consider switching (REDUCED SWITCHING PROBABILITY)
        should_switch, switch_score, switch_roll = weighted_trait_decision(
            traits={
                "adaptability": adaptability,         # Higher = more likely to switch when advantageous
                "risk_tolerance": risk_tolerance,     # Higher = willing to risk losing conviction multiplier
                "self_interest": self_interest,       # Higher = strategic about optimizing position
                "consistency": consistency           # Lower = more willing to change positions
            },
            weights={
                "adaptability": 0.15,  # Reduced from 0.4 - less adaptive switching
                "risk_tolerance": 0.1,  # Reduced from 0.3 - more conservative
                "self_interest": 0.05,  # Reduced from 0.2 - less strategic switching
                "consistency": -0.3  # Increased negative weight - consistency strongly reduces switching
            },
            rng=rng,
            activation="linear"  # Switching should be gradual decision
        )
        
        if should_switch:
            # Find current proposal with highest conviction
            current_proposal_id = max(agent_conviction.keys(), key=lambda pid: agent_conviction[pid])
            current_conviction_amount = agent_conviction[current_proposal_id]
            
            # Get available proposals to switch to
            all_proposals = payload.get("all_proposals", [])
            possible_targets = [pid for pid in all_proposals if pid != current_proposal_id]
            
            if possible_targets and current_conviction_amount > 0:
                # Choose target proposal (random for now, could be enhanced with feedback analysis)
                target_proposal_id = rng.choice(possible_targets)
                
                # Determine how much to switch (trait-based)
                switch_percentage = min(0.8, adaptability * 0.6 + risk_tolerance * 0.4)  # Up to 80%
                switch_amount = max(1, int(current_conviction_amount * switch_percentage))
                
                # Generate switch reason based on traits
                switch_reasons = ["poor_feedback", "better_alternative", "hedging_strategy", "strategic_reposition"]
                reason_weights = [adaptability, persuasiveness, risk_tolerance, self_interest]
                switch_reason = rng.choices(switch_reasons, weights=reason_weights)[0]
                
                # Submit switch action
                ACTION_QUEUE.submit(Action(
                    type="switch_stake",
                    agent_id=agent.agent_id,
                    payload={
                        "source_proposal_id": current_proposal_id,
                        "target_proposal_id": target_proposal_id,
                        "cp_amount": switch_amount,
                        "tick": tick,
                        "issue_id": issue_id,
                        "reason": switch_reason
                    }
                ))
                
                # Signal ready and return (don't also do regular staking)
                signal_ready_action(agent.agent_id, issue_id)
                logger.info(f"[STAKE] {agent.agent_id} scored {switch_score:.2f} vs roll {switch_roll:.2f} → SWITCHING {switch_amount} CP from P{current_proposal_id} → P{target_proposal_id} ({switch_reason}) | Round {round_number}")
                return {"ack": True}
            
        logger.info(f"[STAKE] {agent.agent_id} considered switching: {switch_score:.2f} vs roll {switch_roll:.2f} → NO SWITCH | Proceeding to check unstaking")
    
    # Get own proposal ID for use throughout function
    own_proposal_id = payload.get("current_proposal_id", f"P{agent.agent_id}")
    
    # Decision 1.75: Consider unstaking existing stakes (strategic withdrawal)
    if agent_conviction:  # Agent has existing stakes to potentially unstake
        # Check if agent should consider unstaking for strategic reasons
        should_unstake, unstake_score, unstake_roll = weighted_trait_decision(
            traits={
                "risk_tolerance": 1 - risk_tolerance,  # Lower risk tolerance = more likely to unstake (get conservative)
                "adaptability": adaptability,          # Higher = strategic position adjustments
                "self_interest": self_interest,        # Higher = strategic about capital preservation
                "consistency": 1 - consistency        # Lower consistency = more willing to change positions
            },
            weights={
                "risk_tolerance": 0.4,  # Risk-averse agents unstake to preserve capital
                "adaptability": 0.25,   # Adaptive agents adjust positions strategically
                "self_interest": 0.2,   # Self-interested agents preserve CP for better opportunities
                "consistency": 0.15     # Inconsistent agents more likely to withdraw
            },
            rng=rng,
            activation="linear"  # Unstaking should be gradual decision
        )
        
        if should_unstake:
            # Find proposal with stakes to unstake from
            # Prefer unstaking from proposals with lower conviction or that aren't agent's own
            proposal_options = []
            for pid, conviction_amount in agent_conviction.items():
                if conviction_amount > 0:
                    # Score proposals for unstaking (prefer others' proposals over own)
                    unstake_score = conviction_amount
                    if pid != own_proposal_id:
                        unstake_score *= 1.5  # Prefer unstaking from others' proposals
                    proposal_options.append((pid, conviction_amount, unstake_score))
            
            if proposal_options:
                # Choose proposal to unstake from (weighted by score)
                proposal_options.sort(key=lambda x: x[2], reverse=True)
                unstake_proposal_id = proposal_options[0][0]
                available_conviction = proposal_options[0][1]
                
                # Determine how much to unstake (trait-based)
                # More risk-averse and self-interested agents unstake more
                unstake_percentage = min(0.6, (1 - risk_tolerance) * 0.4 + self_interest * 0.3)  # Up to 60%
                unstake_amount = max(1, int(available_conviction * unstake_percentage))
                
                # Generate unstake reason based on traits
                unstake_reasons = ["capital_preservation", "strategic_repositioning", "risk_management", "better_opportunities"]
                reason_weights = [1 - risk_tolerance, adaptability, 1 - risk_tolerance, self_interest]
                unstake_reason = rng.choices(unstake_reasons, weights=reason_weights)[0]
                
                # Submit unstake action
                ACTION_QUEUE.submit(Action(
                    type="unstake",
                    agent_id=agent.agent_id,
                    payload={
                        "proposal_id": unstake_proposal_id,
                        "cp_amount": unstake_amount,
                        "tick": tick,
                        "issue_id": issue_id,
                        "reason": unstake_reason
                    }
                ))
                
                # Signal ready and return (don't also do regular staking)
                signal_ready_action(agent.agent_id, issue_id)
                logger.info(f"[STAKE] {agent.agent_id} scored {unstake_score:.2f} vs roll {unstake_roll:.2f} → UNSTAKING {unstake_amount} CP from P{unstake_proposal_id} ({unstake_reason}) | Round {round_number}")
                return {"ack": True}
        
        logger.info(f"[STAKE] {agent.agent_id} considered unstaking: {unstake_score:.2f} vs roll {unstake_roll:.2f} → NO UNSTAKE | Proceeding to regular staking")
    
    # Decision 2: Choose proposal to support
    
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
    
    if stake_amount >0 :
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
    
  
        # Update memory
        memory[f"round_{round_number}_stakes"] = stakes_this_round + 1
        memory[f"round_{round_number}_amount"] = stake_amount
        memory[f"round_{round_number}_target"] = target_proposal_id

    # Always signal ready after staking
    signal_ready_action(agent.agent_id, issue_id)
      
    logger.info(f"[STAKE] {agent.agent_id} → STAKING {stake_amount} CP | Round {round_number} | Balance: {current_balance} CP | Target: {target_proposal_id} ({proposal_choice_reason}) | Stake %: {stake_percentage:.2f}")
    
    return {"ack": True}
