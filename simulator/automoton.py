"""Agent automation and decision-making for consensus simulation.

All decision-making is LLM-driven using OCEAN personality profiles.
"""

from pathlib import Path

from context_builder import build_context_stake_preferences, build_context_stake_action, enhance_context_for_call
from llm_provider import (
    FeedbackDecision,
    PreferenceRanking,
    ProposeDecision,
    ReviseDecision,
    StakeAction,
    load_agent_system_prompt,
    load_prompt,
    one_shot,
    one_shot_json,
)
from models import ACTION_QUEUE, Action, AgentActor, Proposal
from simlog import logger
from text_delta import sentence_sequence_delta


def agent_seed(agent: AgentActor) -> int:
    """Get deterministic seed for an agent's LLM calls."""
    return agent.seed if hasattr(agent, "seed") else hash(agent.agent_id) % 2**31


def get_debug_dir(config):
    """Get debug directory path if debug is enabled, None otherwise."""
    debug_config = getattr(config, 'debug_config', {})
    debug_enabled = debug_config.get("enabled", False)

    logger.debug(f"Debug config: {debug_config}, enabled: {debug_enabled}")

    if debug_enabled:
        debug_dir = Path(debug_config.get("output_dir", "debug"))
        debug_dir.mkdir(parents=True, exist_ok=True)
        return debug_dir

    return None


def signal_ready_action(agent_id: str, issue_id: str) -> None:
    """Submit a signal_ready action to the queue."""
    ACTION_QUEUE.submit(
        Action(type="signal_ready", agent_id=agent_id, payload={"issue_id": issue_id})
    )


def get_phase_memory(agent, phase_name: str) -> dict:
    """Get or initialize phase-specific memory for an agent."""
    return agent.memory.setdefault(phase_name, {})


def add_memory_action(
    agent, phase_name: str, tick: int, action_description: str, metadata: dict = None
):
    """Add descriptive action entry to agent memory."""
    memory = get_phase_memory(agent, phase_name)
    action_key = f"tick_{tick}_action"
    memory[action_key] = action_description
    if metadata:
        memory[f"tick_{tick}_metadata"] = metadata


def is_agent_ready_for_phase(agent, phase_name: str) -> bool:
    """Check if agent has already completed actions for this phase."""
    memory = get_phase_memory(agent, phase_name)
    return any(
        key.endswith("_action")
        and ("submitted" in str(value) or "signaled ready" in str(value))
        for key, value in memory.items()
    )


def calculate_strategic_cp_reserve(
    ocean: dict, current_balance: int, proposal_self_stake: int
) -> int:
    """Calculate how much CP to reserve for staking based on OCEAN profile.

    Mapping from old traits:
      self_interest  -> 1 - agreeableness  (less agreeable = more self-interested)
      risk_tolerance -> 1 - neuroticism    (less neurotic = more risk-tolerant)
      consistency    -> conscientiousness  (conscientious = plans ahead)
    """
    self_interest = 1 - ocean["agreeableness"]
    risk_tolerance = 1 - ocean["neuroticism"]
    consistency = ocean["conscientiousness"]

    strategic_factor = (
        self_interest * 0.4
        + (1 - risk_tolerance) * 0.4
        + consistency * 0.2
    )

    reserve_percentage = 0.2 + (strategic_factor * 0.6)
    estimated_staking_need = proposal_self_stake * 2
    percentage_reserve = int(current_balance * reserve_percentage)
    reserve_amount = max(percentage_reserve, estimated_staking_need)
    return min(reserve_amount, current_balance)


def handle_signal(agent: AgentActor, payload: dict):
    """Route phase signals to LLM handlers."""
    agent_proposal_id = payload.get("agent_proposal_id")
    if agent_proposal_id is not None:
        agent.latest_proposal_id = agent_proposal_id

    phase_type = payload.get("type")

    if phase_type == "Propose":
        return handle_propose_llm(agent, payload)
    elif phase_type == "Feedback":
        return handle_feedback_llm(agent, payload)
    elif phase_type == "Revise":
        return handle_revise_llm(agent, payload)
    elif phase_type == "Stake":
        return handle_stake_llm(agent, payload)

    logger.debug(f"{agent.agent_id} received unhandled phase signal: {phase_type}")
    return {"ack": True}


# ---------------------------------------------------------------------------
# LLM Handlers
# ---------------------------------------------------------------------------


def handle_propose_llm(agent: AgentActor, payload: dict):
    """Handle propose phase using LLM decision making."""
    state = payload.get("state")
    config = payload.get("config")

    tick = state.tick
    phase_tick = state.phase_tick
    issue_id = config.issue_id

    memory = get_phase_memory(agent, "propose")

    try:
        context_payload = {
            "type": payload["type"],
            "state": payload["state"],
            "config": payload["config"],
            "tick": tick,
            "phase_tick": phase_tick,
            "issue_id": issue_id,
            "max_phase_ticks": payload["phase"].max_phase_ticks,
        }
        enhanced_context = enhance_context_for_call(
            agent, context_payload, "propose_decision"
        )

        system_prompt = load_agent_system_prompt()
        user_prompt = load_prompt("propose_decision")
        model = config.llm_config.get("model", None)

        seed = agent_seed(agent)
        logger.info(
            f"[LLM-PROPOSE] {agent.agent_id} using seed {seed} (agent.seed={agent.seed})"
        )

        debug_dir = get_debug_dir(config)
        if debug_dir:
            filename = f"context_{agent.agent_id}_{tick}_{phase_tick}_propose.txt"
            (debug_dir / filename).write_text(enhanced_context, encoding="utf-8")

        context_window = config.llm_config.get("context_window")
        decision = one_shot_json(
            system=system_prompt,
            context=enhanced_context,
            prompt=user_prompt,
            response_model=ProposeDecision,
            model=model,
            seed=seed,
            context_window=context_window,
        )

        logger.debug(
            f"[LLM_DECISION] {agent.agent_id} LLM decided: {decision.action} | Reasoning: {decision.reasoning[:100]}..."
        )

        if decision.action == "propose":
            problem_statement = (
                state.current_issue.problem_statement
                if state.current_issue
                else "A technology issue requires collaborative solution"
            )
            content = generate_proposal_content(
                agent, problem_statement, model, context_window
            )

            proposal = Proposal(
                proposal_id=0,
                content=content,
                agent_id=agent.agent_id,
                issue_id=issue_id,
                tick=tick,
                metadata={"origin": "llm:decision", "reasoning": decision.reasoning},
                author=agent.agent_id,
                author_type="agent",
            )
            ACTION_QUEUE.submit(
                Action(
                    type="submit_proposal",
                    agent_id=agent.agent_id,
                    payload=proposal.model_dump(),
                )
            )
            add_memory_action(
                agent,
                "propose",
                tick,
                f"submitted {len(content.split())}-word LLM proposal based on reasoning: {decision.reasoning[:50]}...",
                {
                    "word_count": len(content.split()),
                    "char_count": len(content),
                    "llm_reasoning": decision.reasoning,
                },
            )
            memory["original_content"] = content
            signal_ready_action(agent.agent_id, issue_id)
            logger.info(
                f"{agent.agent_id} submitted LLM proposal. (tick {tick}) [Content: {len(content.split())} words, {len(content)} chars]"
            )

        elif decision.action == "signal_ready":
            signal_ready_action(agent.agent_id, issue_id)
            add_memory_action(
                agent,
                "propose",
                tick,
                f"LLM decided to signal ready: {decision.reasoning[:50]}...",
                {"llm_reasoning": decision.reasoning},
            )
            logger.info(f"{agent.agent_id} LLM signaled ready. (tick {tick})")

        elif decision.action == "wait":
            add_memory_action(
                agent,
                "propose",
                tick,
                f"LLM decided to wait: {decision.reasoning[:50]}...",
                {"llm_reasoning": decision.reasoning},
            )
            logger.info(f"{agent.agent_id} LLM decided to wait. (tick {tick})")

    except Exception as exc:
        logger.error(
            f"{agent.agent_id} LLM propose decision failed: {exc}. "
            "Aborting propose phase. Please check LLM configuration, model availability, and input context."
        )
        raise RuntimeError(
            f"LLM propose decision failed for agent {agent.agent_id}: {exc}. "
            "Propose phase aborted. Check LLM setup and logs for details."
        )

    return {"ack": True}


def handle_feedback_llm(agent: AgentActor, payload: dict):
    """Handle feedback phase using LLM decision making."""
    state = payload.get("state")
    config = payload.get("config")
    phase = payload.get("phase")

    issue_id = config.issue_id
    max_feedback = phase.max_feedback_per_agent
    tick = state.tick

    memory = get_phase_memory(agent, "feedback")
    feedback_given = memory.get("feedback_given", 0)

    if feedback_given >= max_feedback:
        logger.info(
            f"[FEEDBACK-LLM] {agent.agent_id} already at quota ({feedback_given}/{max_feedback}) - cannot proceed"
        )
        return {"ack": True}

    try:
        context_payload = {
            "type": payload["type"],
            "state": payload["state"],
            "config": payload["config"],
            "tick": tick,
            "max_feedback": max_feedback,
            "agent_proposals": payload.get("agent_proposals", []),
            "agent_proposal_id": payload.get("agent_proposal_id"),
            "proposal_contents": payload.get("proposal_contents", {}),
        }
        enhanced_context = enhance_context_for_call(
            agent, context_payload, "feedback_decision"
        )

        system_prompt = load_agent_system_prompt()
        user_prompt = load_prompt("feedback_decision")
        model = config.llm_config.get("model", None)

        seed = agent_seed(agent)
        logger.info(
            f"[LLM-FEEDBACK] {agent.agent_id} using seed {seed} (agent.seed={agent.seed})"
        )

        debug_dir = get_debug_dir(config)
        if debug_dir:
            phase_tick = state.phase_tick
            filename = f"context_{agent.agent_id}_{tick}_{phase_tick}_feedback.txt"
            (debug_dir / filename).write_text(enhanced_context, encoding="utf-8")

        context_window = config.llm_config.get("context_window")
        decision = one_shot_json(
            system=system_prompt,
            context=enhanced_context,
            prompt=user_prompt,
            response_model=FeedbackDecision,
            model=model,
            seed=seed,
            context_window=context_window,
        )

        logger.info(
            f"[FEEDBACK-LLM] {agent.agent_id} LLM decision: {decision.action}, "
            f"targets={decision.target_proposals}, reasoning='{decision.reasoning}'"
        )

        if decision.action == "provide_feedback":
            own_proposal_id = payload.get("agent_proposal_id")
            all_proposals = payload.get("agent_proposals", [])

            valid_targets = [
                pid
                for pid in decision.target_proposals
                if pid != own_proposal_id and pid in all_proposals
            ]

            remaining_quota = max_feedback - feedback_given
            final_targets = valid_targets[:remaining_quota]

            if not final_targets:
                add_memory_action(
                    agent,
                    "feedback",
                    tick,
                    f"LLM decided to provide feedback but no valid targets: {decision.reasoning[:50]}...",
                    {
                        "llm_reasoning": decision.reasoning,
                        "attempted_targets": decision.target_proposals,
                    },
                )
                logger.info(
                    f"[FEEDBACK-LLM] {agent.agent_id} has no valid targets after filtering"
                )
            else:
                all_proposal_contents = payload.get("proposal_contents", {})

                # Build context once — it doesn't vary per target proposal
                feedback_context_payload = {
                    "type": payload["type"],
                    "state": payload["state"],
                    "config": payload["config"],
                    "tick": tick,
                    "max_feedback": max_feedback,
                    "agent_proposals": payload.get("agent_proposals", []),
                    "agent_proposal_id": payload.get("agent_proposal_id"),
                    "proposal_contents": payload.get("proposal_contents", {}),
                }
                feedback_context = enhance_context_for_call(
                    agent, feedback_context_payload, "feedback"
                )

                for pid in final_targets:
                    if pid in all_proposal_contents:
                        comment = generate_feedback_content(
                            agent,
                            feedback_context,
                            all_proposal_contents[pid],
                            model,
                            context_window,
                        )

                        ACTION_QUEUE.submit(
                            Action(
                                type="feedback",
                                agent_id=agent.agent_id,
                                payload={
                                    "target_proposal_id": pid,
                                    "comment": comment,
                                    "tick": tick,
                                    "issue_id": issue_id,
                                },
                            )
                        )

                        memory["feedback_given"] = memory.get("feedback_given", 0) + 1
                        add_memory_action(
                            agent,
                            "feedback",
                            tick,
                            f"LLM provided feedback to proposal {pid}: {comment[:30]}...",
                            {
                                "target_proposal_id": pid,
                                "llm_generated": True,
                                "feedback_count": memory["feedback_given"],
                                "llm_reasoning": decision.reasoning,
                            },
                        )
                        logger.info(
                            f"[FEEDBACK-LLM] {agent.agent_id} submitted feedback to P{pid}: '{comment[:50]}...'"
                        )

                logger.info(
                    f"[FEEDBACK-LLM] {agent.agent_id} submitted {len(final_targets)} feedbacks | Total: {memory['feedback_given']}/{max_feedback}"
                )

        elif decision.action == "wait":
            add_memory_action(
                agent,
                "feedback",
                tick,
                f"LLM decided to wait: {decision.reasoning[:50]}...",
                {"llm_reasoning": decision.reasoning},
            )
            logger.info(
                f"[FEEDBACK-LLM] {agent.agent_id} LLM decided to wait. (tick {tick})"
            )

    except Exception as exc:
        logger.error(
            f"[FEEDBACK-LLM] {agent.agent_id} LLM feedback decision failed: {exc}"
        )
        raise RuntimeError(
            f"LLM feedback decision failed for agent {agent.agent_id}: {exc}. "
            "Feedback phase aborted. Check LLM setup and logs for details."
        )

    return {"ack": True}


def handle_revise_llm(agent: AgentActor, payload: dict):
    """Handle revise phase using LLM decision making."""
    state = payload.get("state")
    config = payload.get("config")
    phase = payload.get("phase")

    tick = state.tick
    phase_tick = state.phase_tick
    issue_id = config.issue_id
    proposal_self_stake = payload.get("proposal_self_stake", 50)
    current_balance = payload.get("current_balance", 150)

    memory = get_phase_memory(agent, "revise")

    ocean = agent.metadata["ocean_profile"]
    strategic_reserve = calculate_strategic_cp_reserve(
        ocean, current_balance, proposal_self_stake
    )
    available_for_revision = current_balance - strategic_reserve

    logger.debug(
        f"[REVISE-LLM] {agent.agent_id} strategic planning: balance={current_balance}, reserve={strategic_reserve}, available={available_for_revision}"
    )

    try:
        context_payload = {
            "type": payload["type"],
            "state": payload["state"],
            "config": payload["config"],
            "tick": tick,
            "phase_tick": phase_tick,
            "issue_id": issue_id,
            "max_phase_ticks": phase.max_phase_ticks,
            "current_balance": current_balance,
            "proposal_self_stake": proposal_self_stake,
        }
        enhanced_context = enhance_context_for_call(
            agent, context_payload, "revise_decision"
        )

        system_prompt = load_agent_system_prompt()
        user_prompt = load_prompt("revise_decision")
        model = config.llm_config.get("model", None)

        seed = agent_seed(agent)
        logger.info(
            f"[LLM-REVISE] {agent.agent_id} using seed {seed} (agent.seed={agent.seed})"
        )

        debug_dir = get_debug_dir(config)
        if debug_dir:
            filename = f"context_{agent.agent_id}_{tick}_{phase_tick}_revise.txt"
            (debug_dir / filename).write_text(enhanced_context, encoding="utf-8")

        context_window = config.llm_config.get("context_window")
        decision = one_shot_json(
            system=system_prompt,
            context=enhanced_context,
            prompt=user_prompt,
            response_model=ReviseDecision,
            model=model,
            seed=seed,
            context_window=context_window,
        )

        logger.debug(
            f"[LLM_DECISION] {agent.agent_id} LLM decided: {decision.action} | Reasoning: {decision.reasoning[:100]}..."
        )

        if decision.action == "revise":
            propose_memory = get_phase_memory(agent, "propose")
            original_content = propose_memory.get("original_content", "")

            if not original_content:
                logger.warning(
                    f"[REVISE-LLM] {agent.agent_id} cannot revise - no original content found in memory"
                )
                signal_ready_action(agent.agent_id, issue_id)
                add_memory_action(
                    agent,
                    "revise",
                    tick,
                    f"LLM revision failed due to missing original content: {decision.reasoning[:50]}...",
                    {
                        "llm_reasoning": decision.reasoning,
                        "error": "no_original_content",
                    },
                )
                return {"ack": True}

            new_content = generate_revision_content(
                agent,
                enhanced_context,
                original_content,
                model,
                context_window,
            )
            new_content = new_content.strip()

            if not new_content:
                logger.error(
                    f"[REVISE-LLM] {agent.agent_id} LLM generated empty revision content. Defaulting to signal_ready."
                )
                signal_ready_action(agent.agent_id, issue_id)
                add_memory_action(
                    agent,
                    "revise",
                    tick,
                    f"LLM revision failed due to empty generated content: {decision.reasoning[:50]}...",
                    {
                        "llm_reasoning": decision.reasoning,
                        "error": "empty_generated_content",
                    },
                )
                return {"ack": True}

            preview_delta = sentence_sequence_delta(original_content, new_content)

            estimated_cost = int(proposal_self_stake * preview_delta)
            if estimated_cost > available_for_revision:
                logger.info(
                    f"[REVISE-LLM] {agent.agent_id} strategic holdback: LLM revision estimated cost {estimated_cost} CP (delta={preview_delta:.3f}), only {available_for_revision} available (reserved {strategic_reserve} CP for staking)"
                )
                signal_ready_action(agent.agent_id, issue_id)
                add_memory_action(
                    agent,
                    "revise",
                    tick,
                    f"LLM revision blocked by strategic CP limit: {decision.reasoning[:50]}...",
                    {
                        "llm_reasoning": decision.reasoning,
                        "estimated_cost": estimated_cost,
                        "available": available_for_revision,
                    },
                )
                return {"ack": True}

            ACTION_QUEUE.submit(
                Action(
                    type="revise",
                    agent_id=agent.agent_id,
                    payload={
                        "proposal_id": payload.get("agent_proposal_id"),
                        "new_content": new_content,
                        "tick": tick,
                        "issue_id": issue_id,
                    },
                )
            )

            memory["has_revised"] = True
            memory["preview_delta"] = preview_delta

            add_memory_action(
                agent,
                "revise",
                tick,
                f"LLM revised proposal (delta={preview_delta:.3f}, cost={estimated_cost}CP): {decision.reasoning[:50]}...",
                {
                    "word_count": len(new_content.split()),
                    "char_count": len(new_content),
                    "llm_reasoning": decision.reasoning,
                    "preview_delta": preview_delta,
                    "estimated_cost": estimated_cost,
                },
            )

            logger.info(
                f"[REVISE-LLM] {agent.agent_id} LLM revised proposal (estimated delta={preview_delta:.3f}, cost={estimated_cost}CP) [Content: {len(new_content.split())} words, {len(new_content)} chars]"
            )

        elif decision.action == "signal_ready":
            signal_ready_action(agent.agent_id, issue_id)
            add_memory_action(
                agent,
                "revise",
                tick,
                f"LLM decided to signal ready: {decision.reasoning[:50]}...",
                {"llm_reasoning": decision.reasoning},
            )
            logger.info(
                f"[REVISE-LLM] {agent.agent_id} LLM signaled ready. (tick {tick})"
            )

    except Exception as exc:
        logger.error(
            f"[REVISE-LLM] {agent.agent_id} LLM revise decision failed: {exc}. "
            "Aborting revise phase."
        )
        raise RuntimeError(
            f"LLM revise decision failed for agent {agent.agent_id}: {exc}. "
            "Revise phase aborted. Check LLM setup and logs for details."
        )

    return {"ack": True}


def handle_stake_llm(agent: AgentActor, payload: dict):
    """Handle STAKE phase using LLM decision making with two-prompt system."""
    state = payload.get("state")
    config = payload.get("config")
    current_balance = payload.get("current_balance")

    issue_id = config.issue_id
    tick = state.tick
    phase_tick = state.phase_tick
    round_number = payload.get("round_number", 1)

    memory = get_phase_memory(agent, "stake")

    debug_dir = get_debug_dir(config)

    try:
        # Phase 1: Get proposal preferences (once per stake phase)
        preferences_key = f"round_{round_number}_preferences"
        if preferences_key not in memory:
            logger.info(f"[STAKE-LLM] {agent.agent_id} getting proposal preferences for round {round_number}")

            context_payload = {
                "type": payload["type"],
                "state": payload["state"],
                "config": payload["config"],
                "tick": tick,
                "phase_tick": phase_tick,
                "issue_id": issue_id,
                "max_phase_ticks": payload["phase"].max_phase_ticks,
                "current_balance": current_balance,
            }

            preference_context = enhance_context_for_call(
                agent, context_payload, "stake_preferences"
            )

            system_prompt = load_agent_system_prompt()
            user_prompt = load_prompt("stake_preferences")
            model = config.llm_config.get("model", None)

            seed = agent_seed(agent)

            if debug_dir:
                filename = f"context_{agent.agent_id}_{tick}_{phase_tick}_stake_prefs.txt"
                (debug_dir / filename).write_text(preference_context, encoding="utf-8")

            context_window = config.llm_config.get("context_window")
            preferences = one_shot_json(
                system=system_prompt,
                context=preference_context,
                prompt=user_prompt,
                response_model=PreferenceRanking,
                model=model,
                seed=seed,
                context_window=context_window,
            )

            memory[preferences_key] = {
                "preferences": [p.model_dump() for p in preferences.preferences],
                "self_proposal_id": preferences.self_proposal_id,
                "strategy_summary": preferences.strategy_summary,
            }

            sorted_prefs = sorted(preferences.preferences, key=lambda x: x.rank)
            top_3_ids = [p.proposal_id for p in sorted_prefs[:3]]

            logger.info(
                f"[STAKE-LLM] {agent.agent_id} established preferences: {top_3_ids}... | Strategy: {preferences.strategy_summary[:50]}..."
            )

        # Phase 2: Get tactical stake action based on preferences + current state
        stored_preferences = memory.get(preferences_key)
        if not stored_preferences:
            logger.error(f"[STAKE-LLM] {agent.agent_id} no preferences found for round {round_number}")
            signal_ready_action(agent.agent_id, issue_id)
            return {"ack": True}

        context_payload = {
            "type": payload["type"],
            "state": payload["state"],
            "config": payload["config"],
            "tick": tick,
            "phase_tick": phase_tick,
            "issue_id": issue_id,
            "max_phase_ticks": payload["phase"].max_phase_ticks,
            "current_balance": payload.get("current_balance"),
            "atomic_stakes": payload.get("atomic_stakes", []),
            "stored_preferences": stored_preferences,
        }
        action_context = enhance_context_for_call(
            agent, context_payload, "stake_action"
        )

        if debug_dir:
            filename = f"context_{agent.agent_id}_{tick}_{phase_tick}_stake_action.txt"
            (debug_dir / filename).write_text(action_context, encoding="utf-8")

        system_prompt = load_agent_system_prompt()
        user_prompt = load_prompt("stake_action")
        model = config.llm_config.get("model", None)

        seed = agent_seed(agent)
        context_window = config.llm_config.get("context_window")

        action_decision = one_shot_json(
            system=system_prompt,
            context=action_context,
            prompt=user_prompt,
            response_model=StakeAction,
            model=model,
            seed=seed + tick,
            context_window=context_window,
        )

        logger.debug(
            f"[LLM_DECISION] {agent.agent_id} LLM decided: {action_decision.action} on P{action_decision.proposal_id} with {action_decision.cp_amount} CP | Reasoning: {action_decision.reasoning[:100]}..."
        )

        if action_decision.action == "stake":
            stake_amount = min(action_decision.cp_amount, current_balance)
            if stake_amount > 0:
                ACTION_QUEUE.submit(
                    Action(
                        type="stake",
                        agent_id=agent.agent_id,
                        payload={
                            "proposal_id": action_decision.proposal_id,
                            "stake_amount": stake_amount,
                            "round_number": round_number,
                            "tick": tick,
                            "issue_id": issue_id,
                            "choice_reason": "llm_decision",
                        },
                    )
                )

                add_memory_action(
                    agent,
                    "stake",
                    tick,
                    f"LLM staked {stake_amount} CP on proposal {action_decision.proposal_id}: {action_decision.reasoning[:50]}...",
                    {
                        "action": "stake",
                        "proposal_id": action_decision.proposal_id,
                        "amount": stake_amount,
                        "llm_reasoning": action_decision.reasoning,
                    },
                )

                logger.info(
                    f"[STAKE-LLM] {agent.agent_id} LLM staked {stake_amount} CP on P{action_decision.proposal_id} | Round {round_number}"
                )

        elif action_decision.action == "switch_stake":
            if action_decision.source_proposal_id is not None:
                switch_amount = min(action_decision.cp_amount, current_balance)
                if switch_amount > 0:
                    ACTION_QUEUE.submit(
                        Action(
                            type="switch_stake",
                            agent_id=agent.agent_id,
                            payload={
                                "source_proposal_id": action_decision.source_proposal_id,
                                "target_proposal_id": action_decision.proposal_id,
                                "cp_amount": switch_amount,
                                "tick": tick,
                                "issue_id": issue_id,
                                "reason": "llm_decision",
                            },
                        )
                    )

                    add_memory_action(
                        agent,
                        "stake",
                        tick,
                        f"LLM switched {switch_amount} CP from P{action_decision.source_proposal_id} to P{action_decision.proposal_id}: {action_decision.reasoning[:50]}...",
                        {
                            "action": "switch_stake",
                            "source_proposal_id": action_decision.source_proposal_id,
                            "target_proposal_id": action_decision.proposal_id,
                            "amount": switch_amount,
                            "llm_reasoning": action_decision.reasoning,
                        },
                    )

                    logger.info(
                        f"[STAKE-LLM] {agent.agent_id} LLM switched {switch_amount} CP from P{action_decision.source_proposal_id} to P{action_decision.proposal_id} | Round {round_number}"
                    )

        elif action_decision.action == "unstake":
            unstake_amount = min(action_decision.cp_amount, current_balance)
            if unstake_amount > 0:
                ACTION_QUEUE.submit(
                    Action(
                        type="unstake",
                        agent_id=agent.agent_id,
                        payload={
                            "proposal_id": action_decision.proposal_id,
                            "cp_amount": unstake_amount,
                            "tick": tick,
                            "issue_id": issue_id,
                            "reason": "llm_decision",
                        },
                    )
                )

                add_memory_action(
                    agent,
                    "stake",
                    tick,
                    f"LLM unstaked {unstake_amount} CP from proposal {action_decision.proposal_id}: {action_decision.reasoning[:50]}...",
                    {
                        "action": "unstake",
                        "proposal_id": action_decision.proposal_id,
                        "amount": unstake_amount,
                        "llm_reasoning": action_decision.reasoning,
                    },
                )

                logger.info(
                    f"[STAKE-LLM] {agent.agent_id} LLM unstaked {unstake_amount} CP from P{action_decision.proposal_id} | Round {round_number}"
                )

        elif action_decision.action == "wait":
            add_memory_action(
                agent,
                "stake",
                tick,
                f"LLM decided to wait: {action_decision.reasoning[:50]}...",
                {
                    "action": "wait",
                    "llm_reasoning": action_decision.reasoning,
                },
            )
            logger.info(
                f"[STAKE-LLM] {agent.agent_id} LLM decided to wait. (tick {tick})"
            )

    except Exception as exc:
        logger.error(
            f"[STAKE-LLM] {agent.agent_id} LLM stake decision failed: {exc}. "
            "Aborting stake phase. Please check LLM configuration, model availability, and input context."
        )
        raise RuntimeError(
            f"LLM stake decision failed for agent {agent.agent_id}: {exc}. "
            "Stake phase aborted. Check LLM setup and logs for details."
        )

    signal_ready_action(agent.agent_id, issue_id)

    return {"ack": True}


# ---------------------------------------------------------------------------
# Content Generators (LLM-powered)
# ---------------------------------------------------------------------------


def _generate_content(
    agent: AgentActor,
    context: str,
    user_prompt: str,
    model: str = None,
    context_window: int = None,
    seed_salt: int = 0,
) -> str:
    """Shared LLM content generation. Seed is agent_seed + salt for variation."""
    seed = agent_seed(agent) + seed_salt
    return one_shot(
        load_agent_system_prompt(),
        context,
        user_prompt,
        model=model,
        seed=seed,
        context_window=context_window,
    )


def generate_proposal_content(
    agent: AgentActor,
    problem_statement: str,
    model: str = None,
    context_window: int = None,
) -> str:
    """Generate proposal content using LLM."""
    return _generate_content(
        agent, problem_statement, load_prompt("proposal"), model, context_window
    )


def generate_feedback_content(
    agent: AgentActor,
    context: str,
    proposal_content: str,
    model: str = None,
    context_window: int = None,
) -> str:
    """Generate feedback content using LLM for a specific proposal."""
    user_prompt = f"{load_prompt('feedback')}\n\nSpecific proposal to review:\n{proposal_content}"
    return _generate_content(
        agent, context, user_prompt, model, context_window,
        seed_salt=hash(proposal_content) % 1000,
    )


def generate_revision_content(
    agent: AgentActor,
    context: str,
    original_content: str,
    model: str = None,
    context_window: int = None,
) -> str:
    """Generate revised proposal content using LLM."""
    user_prompt = f"{load_prompt('revise')}\n\nOriginal proposal to revise:\n{original_content}"
    return _generate_content(
        agent, context, user_prompt, model, context_window,
        seed_salt=hash(original_content) % 1000,
    )
