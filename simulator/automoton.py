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
        # Generate bigger lorem ipsum content for testing
        def generate_lorem_content(rng, word_count=60):
            words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
                    "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
                    "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud", 
                    "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo", 
                    "consequat", "duis", "aute", "irure", "in", "reprehenderit", "voluptate", 
                    "velit", "esse", "cillum", "fugiat", "nulla", "pariatur", "excepteur", "sint", 
                    "occaecat", "cupidatat", "non", "proident", "sunt", "culpa", "qui", "officia", 
                    "deserunt", "mollit", "anim", "id", "est", "laborum", "suscipit", "lobortis", 
                    "nisl", "aliquam", "erat", "volutpat", "blandit", "praesent", "zzril", "delenit", 
                    "augue", "feugait", "facilisi", "diam", "nonummy", "nibh", "euismod", "tincidunt"]
            return " ".join(rng.choices(words, k=word_count))
        
        # Use traits to determine proposal size - similar to revision logic
        thoroughness = profile.get("compliance", 0.5) + profile.get("consistency", 0.5)  # More methodical agents
        verbosity = profile.get("sociability", 0.5)  # More social agents tend to be verbose  
        initiative_boost = profile.get("initiative", 0.5) * 0.3  # Initiative agents may write more detailed proposals
        trait_factor = (thoroughness + verbosity + initiative_boost) / 3.3  # Combine traits, normalize
        
        # Proposal size influenced by traits (30-70 words)
        min_words = 30
        max_words = 70
        proposal_word_count = int(min_words + (trait_factor * (max_words - min_words)))
        
        content = generate_lorem_content(rng, proposal_word_count)
        
        proposal = Proposal(
            proposal_id=f"P{agent.agent_id}",
            content=content,
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
        logger.info(f"{agent.agent_id} submitted proposal. (tick {tick}) [Content: {len(content.split())} words, {len(content)} chars] (trait_factor={trait_factor:.2f})")

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
    
    # Use agent traits to determine feedback intent
    sociability = profile.get("sociability", 0.5)
    initiative = profile.get("initiative", 0.5)
    compliance = profile.get("compliance", 0.9)
    
    # Check if already at quota
    if feedback_given >= max_feedback:
        # Store in memory that agent has reached quota
        memory["quota_reached"] = True
        
        # Use compliance trait to decide whether to respect quota
        should_respect_quota, compliance_score, compliance_roll = weighted_trait_decision(
            traits={"compliance": compliance},
            weights={"compliance": 1.0},
            rng=rng
        )
        
        if should_respect_quota:
            logger.info(f"[FEEDBACK] {agent.agent_id} already at quota ({feedback_given}/{max_feedback}) - respects limit (compliance {compliance_score:.2f} vs roll {compliance_roll:.2f})")
            return {"ack": True}
        else:
            logger.info(f"[FEEDBACK] {agent.agent_id} already at quota ({feedback_given}/{max_feedback}) - attempts anyway (compliance {compliance_score:.2f} vs roll {compliance_roll:.2f})")
            # Continue to decision logic below
    
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
    
    # If agent is at quota, they may still try 1 feedback (will be rejected)
    if remaining_quota <= 0:
        num_feedbacks = 1
        logger.info(f"[FEEDBACK] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → OVER-QUOTA ATTEMPT (will be rejected)")
    else:
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
    memory = agent.memory.setdefault("revise", {})
    has_revised = memory.get("has_revised", False)
    
    # Traits used for revision decisions
    adaptability = profile.get("adaptability", 0.5)
    self_interest = profile.get("self_interest", 0.5) 
    compliance = profile.get("compliance", 0.9)
    consistency = profile.get("consistency", 0.5)
    risk_tolerance = profile.get("risk_tolerance", 0.2)
    
    # Check if agent has feedback on their proposal
    if not feedback_received:
        # For testing: Make agents more likely to revise even without feedback
        # Use a combination of traits to decide whether to make a "preemptive" revision
        should_revise_anyway, score, roll = weighted_trait_decision(
            traits={"adaptability": adaptability, "initiative": profile.get("initiative", 0.5)},
            weights={"adaptability": 0.7, "initiative": 0.3},
            rng=rng
        )
        
        if should_revise_anyway:
            # Make a preemptive revision (simulating self-improvement)
            delta_factor = (adaptability * 0.6 + risk_tolerance * 0.4)
            delta = max(0.1, min(1.0, 0.1 + delta_factor * 0.6))  # Smaller deltas for preemptive revisions
            
            # Generate bigger revised content using lorem ipsum
            def generate_lorem_content(rng, word_count=60):
                words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
                        "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
                        "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud", 
                        "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo", 
                        "consequat", "duis", "aute", "irure", "in", "reprehenderit", "voluptate", 
                        "velit", "esse", "cillum", "fugiat", "nulla", "pariatur", "excepteur", "sint", 
                        "occaecat", "cupidatat", "non", "proident", "sunt", "culpa", "qui", "officia", 
                        "deserunt", "mollit", "anim", "id", "est", "laborum", "suscipit", "lobortis", 
                        "nisl", "aliquam", "erat", "volutpat", "blandit", "praesent", "zzril", "delenit", 
                        "augue", "feugait", "facilisi", "diam", "nonummy", "nibh", "euismod", "tincidunt"]
                return " ".join(rng.choices(words, k=word_count))
            
            # Use traits to determine revision size - more thorough agents write longer revisions
            thoroughness = profile.get("compliance", 0.5) + profile.get("consistency", 0.5)  # More methodical agents
            verbosity = profile.get("sociability", 0.5)  # More social agents tend to be verbose
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
        
        # Fall back to compliance-based ready signal
        should_signal, score2, roll2 = weighted_trait_decision(
            traits={"compliance": compliance},
            weights={"compliance": 1.0},
            rng=rng
        )
        
        if should_signal:
            ACTION_QUEUE.submit(Action(
                type="signal_ready",
                agent_id=agent.agent_id,
                payload={"issue_id": issue_id}
            ))
            logger.info(f"[REVISE] {agent.agent_id} no feedback received, signaling ready (compliance {score2:.2f} vs roll {roll2:.2f})")
        else:
            logger.info(f"[REVISE] {agent.agent_id} no feedback received, waiting (compliance {score2:.2f} vs roll {roll2:.2f})")
        
        return {"ack": True}
    
    # Agent received feedback - decide whether to revise
    if has_revised:
        # Already revised once this phase, use consistency trait to avoid over-revising
        should_revise_again, score, roll = weighted_trait_decision(
            traits={"consistency": 1 - consistency, "adaptability": adaptability},  # Lower consistency = more likely to revise again
            weights={"consistency": 0.7, "adaptability": 0.3},
            rng=rng
        )
        
        if not should_revise_again:
            ACTION_QUEUE.submit(Action(
                type="signal_ready",
                agent_id=agent.agent_id,
                payload={"issue_id": issue_id}
            ))
            logger.info(f"[REVISE] {agent.agent_id} already revised, signaling ready (consistency check {score:.2f} vs roll {roll:.2f})")
            return {"ack": True}
    
    # First revision or willing to revise again - evaluate feedback
    should_revise, score, roll = weighted_trait_decision(
        traits={
            "adaptability": adaptability,
            "self_interest": self_interest,
            "risk_tolerance": risk_tolerance
        },
        weights={
            "adaptability": 0.5,      # Main driver for accepting feedback
            "self_interest": 0.3,     # Self-interest may resist change
            "risk_tolerance": 0.2     # Willingness to take revision risk
        },
        rng=rng
    )
    
    if not should_revise:
        ACTION_QUEUE.submit(Action(
            type="signal_ready",
            agent_id=agent.agent_id,
            payload={"issue_id": issue_id}
        ))
        logger.info(f"[REVISE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → NO REVISION | Weights: adapt=0.5, self=0.3, risk=0.2")
        return {"ack": True}
    
    # Decide revision size (delta) based on adaptability and risk tolerance
    # Higher adaptability + risk tolerance = larger revisions
    delta_factor = (adaptability * 0.6 + risk_tolerance * 0.4)
    delta = max(0.1, min(1.0, 0.2 + delta_factor * 0.8))  # Range [0.1, 1.0]
    
    # Generate bigger revised content using lorem ipsum
    def generate_lorem_content(rng, word_count=60):
        words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
                "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
                "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud", 
                "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo", 
                "consequat", "duis", "aute", "irure", "in", "reprehenderit", "voluptate", 
                "velit", "esse", "cillum", "fugiat", "nulla", "pariatur", "excepteur", "sint", 
                "occaecat", "cupidatat", "non", "proident", "sunt", "culpa", "qui", "officia", 
                "deserunt", "mollit", "anim", "id", "est", "laborum", "suscipit", "lobortis", 
                "nisl", "aliquam", "erat", "volutpat", "blandit", "praesent", "zzril", "delenit", 
                "augue", "feugait", "facilisi", "diam", "nonummy", "nibh", "euismod", "tincidunt"]
        return " ".join(rng.choices(words, k=word_count))
    
    # Use traits to determine revision size for feedback-based revisions
    thoroughness = profile.get("compliance", 0.5) + profile.get("consistency", 0.5)  # More methodical agents
    verbosity = profile.get("sociability", 0.5)  # More social agents tend to be verbose
    adaptability_boost = profile.get("adaptability", 0.5) * 0.5  # Adaptable agents may write more when responding to feedback
    trait_factor = (thoroughness + verbosity + adaptability_boost) / 3.5  # Combine traits, normalize
    
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
            "proposal_id": f"P{agent.agent_id}",  # Assuming consistent proposal ID format
            "new_content": new_content,
            "delta": delta,
            "tick": tick,
            "issue_id": issue_id
        }
    ))
    
    # Update memory
    memory["has_revised"] = True
    memory["revision_delta"] = delta
    
    logger.info(f"[REVISE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → REVISING (Δ={delta:.2f}) | Weights: adapt=0.5, self=0.3, risk=0.2 [Content: {len(lorem_content.split())} words, {len(new_content)} chars] (trait_factor={trait_factor:.2f})")
    
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
    memory = agent.memory.setdefault("stake", {})
    stakes_this_round = memory.get(f"round_{round_number}_stakes", 0)
    
    # Agent traits used for staking decisions
    self_interest = profile.get("self_interest", 0.5)
    risk_tolerance = profile.get("risk_tolerance", 0.2)
    compliance = profile.get("compliance", 0.9)
    sociability = profile.get("sociability", 0.5)
    initiative = profile.get("initiative", 0.5)
    consistency = profile.get("consistency", 0.5)
    adaptability = profile.get("adaptability", 0.5)
    
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
        rng=rng
    )
    
    if not should_stake:
        # Signal ready without staking
        ACTION_QUEUE.submit(Action(
            type="signal_ready",
            agent_id=agent.agent_id,
            payload={"issue_id": issue_id}
        ))
        logger.info(f"[STAKE] {agent.agent_id} scored {score:.2f} vs roll {roll:.2f} → NO STAKE | Round {round_number} | Weights: risk=0.4, init=0.3, self=0.2, comp=0.1")
        return {"ack": True}
    
    # Decision 2: Choose proposal to support
    own_proposal_id = f"P{agent.agent_id}"
    
    # First check: stake on own proposal?
    stake_on_own, score, roll = weighted_trait_decision(
        traits={
            "self_interest": self_interest,       # Higher = own proposal
            "consistency": consistency,           # Higher = stick with own
            "risk_tolerance": risk_tolerance      # Higher = confident in own
        },
        weights={
            "self_interest": 0.5, 
            "consistency": 0.3, 
            "risk_tolerance": 0.2
        },
        rng=rng
    )
    
    if stake_on_own:
        target_proposal_id = own_proposal_id
        proposal_choice_reason = "own_proposal"
        logger.info(f"[STAKE] {agent.agent_id} proposal choice: own ({score:.2f} vs {roll:.2f}) | Weights: self=0.5, cons=0.3, risk=0.2")
    else:
        # Check: stake on others' proposals?
        stake_on_others, score2, roll2 = weighted_trait_decision(
            traits={
                "sociability": sociability,          # Higher = support community
                "adaptability": adaptability         # Higher = hedge bets
            },
            weights={
                "sociability": 0.6, 
                "adaptability": 0.4
            },
            rng=rng
        )
        
        if stake_on_others:
            # Sample from other agents' proposals
            possible_proposals = [f"PAgent_{i}" for i in range(10) if f"Agent_{i}" != agent.agent_id]
            target_proposal_id = rng.choice(possible_proposals) if possible_proposals else own_proposal_id
            proposal_choice_reason = "sampled_other"
            logger.info(f"[STAKE] {agent.agent_id} proposal choice: others ({score2:.2f} vs {roll2:.2f}) | Weights: soc=0.6, adapt=0.4")
        else:
            # Default to own if both fail
            target_proposal_id = own_proposal_id
            proposal_choice_reason = "default_own"
            logger.info(f"[STAKE] {agent.agent_id} proposal choice: default to own (others failed: {score2:.2f} vs {roll2:.2f})")
    
    # Decision 3: Calculate stake amount (direct trait calculation)
    # Simulate current balance (in real implementation, would get from credit manager)
    estimated_balance = 100 - (round_number * 10)  # Simple balance estimation
    
    # Direct trait-driven stake percentage (up to 80% of balance)
    stake_percentage = risk_tolerance * 0.8
    stake_amount = max(1, int(estimated_balance * stake_percentage))
    
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
    ACTION_QUEUE.submit(Action(
        type="signal_ready",
        agent_id=agent.agent_id,
        payload={"issue_id": issue_id}
    ))
    
    # Update memory
    memory[f"round_{round_number}_stakes"] = stakes_this_round + 1
    memory[f"round_{round_number}_amount"] = stake_amount
    memory[f"round_{round_number}_target"] = target_proposal_id
    
    logger.info(f"[STAKE] {agent.agent_id} → STAKING {stake_amount} CP | Round {round_number} | Target: {target_proposal_id} ({proposal_choice_reason}) | Stake %: {stake_percentage:.2f}")
    
    return {"ack": True}
