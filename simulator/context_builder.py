"""
Phase-specific context builder for agent LLM calls.
Provides lean markdown context optimized for token efficiency.
"""

import json
from simlog import EventType, LogEntry, LogLevel, PhaseType, log_event, logger




def build_feedback_context(state, all_proposal_contents, current_tick, agent_pool=None):
    """
    Build context for feedback generation showing current state.

    Format:
    Tick #
    -----
    Proposal ##, Agent ##
    [proposal content]

    Feedback - agent: comment
    Feedback - agent: comment
    -----
    [repeat for other proposals]
    """

    if not state or not state.current_issue:
        return f"Tick {current_tick}"

    context_lines = [f"Tick {current_tick}", "-----"]

    # Get proposals and their feedback
    proposals = state.current_issue.proposals
    feedback_log = state.current_issue.feedback_log

    for proposal in proposals:
        if not proposal.active:
            continue

        # Add proposal header with agent traits
        author_traits = ""
        if agent_pool and proposal.author in agent_pool.agents:
            agent = agent_pool.agents[proposal.author]
            profile = agent.metadata.get("protocol_profile", {})

            # Get first letter of each trait with value
            trait_parts = []
            for trait_name, value in profile.items():
                if isinstance(value, (int, float)):
                    first_letter = trait_name[0].upper()
                    trait_parts.append(f"{first_letter}{value:.2f}")

            if trait_parts:
                author_traits = f" [{' '.join(trait_parts)}]"

        context_lines.append(
            f"Proposal:{proposal.proposal_id}, Agent:{proposal.author} Traits:{author_traits}"
        )

        # Add full proposal content
        context_lines.append(f'"{proposal.content}"')
        context_lines.append("")

        # Add feedback for this proposal
        proposal_feedback = [
            fb for fb in feedback_log if fb.get("to") == proposal.proposal_id
        ]

        if proposal_feedback:
            for fb in proposal_feedback[-3:]:  # Last 3 feedback items
                context_lines.append(f'Feedback - {fb["from"]}: "{fb["comment"]}"')
        else:
            context_lines.append("No feedback yet")

        context_lines.append("-----")

    return "\n".join(context_lines)


def enhance_context_for_call(agent, payload, call_type):
    """
    Build phase-specific markdown context for LLM calls.
    Routes to appropriate phase builder based on call_type.
    """
    
    # Extract issue from state
    state = payload.get("state")
    if not state or not hasattr(state, "current_issue") or not state.current_issue:
        # Fallback for missing state - return minimal context
        return f"# Agent: {agent.agent_id}\n\nNo issue context available."
    
    issue = state.current_issue
    
    # Route to appropriate phase-specific context builder
    if call_type == "propose_decision":
        return build_context_propose(agent, issue)
    elif call_type == "feedback_decision":
        return build_context_feedback(agent, issue)
    elif call_type == "revise_decision":
        return build_context_revise(agent, issue)
    elif call_type == "stake_preferences":
        return build_context_stake_preferences(agent, issue, payload)
    elif call_type == "stake_action":
        stored_preferences = payload.get("stored_preferences")
        return build_context_stake_action(agent, issue, payload, stored_preferences)
    else:
        # Fallback for unknown call types
        print(f"WARNING: Unknown call type '{call_type}' - using base context.")
        return build_base_context(agent, issue)


def build_propose_decision_context(agent, **kwargs):
    """
    Build rich context for propose decision LLM calls.

    Includes:
    - Current tick and issue information
    - Agent's memory of past actions in this phase
    - Current state of proposals and feedback if available
    - Agent's trait summary
    """
    tick = kwargs.get("tick", 0)
    issue_id = kwargs.get("issue_id", "unknown")
    memory = kwargs.get("memory", {})
    state = kwargs.get("state")
    agent_pool = kwargs.get("agent_pool")

    context_lines = [f"Tick {tick}", f"Issue: {issue_id}", "-----"]

    # Add agent's memory of past actions in this phase
    if memory:
        has_acted = memory.get("has_acted", False)
        if has_acted:
            context_lines.append("You have already acted in this propose phase.")
        else:
            context_lines.append("You have not yet acted in this propose phase.")

        initial_decision = memory.get("initial_decision")
        if initial_decision:
            context_lines.append(f"Previous decision approach: {initial_decision}")

    # Add current state information if available
    if state and state.current_issue:
        proposals = state.current_issue.proposals
        active_proposals = [p for p in proposals if p.active]

        if active_proposals:
            context_lines.append(
                f"\nCurrent proposals ({len(active_proposals)} active):"
            )
            for proposal in active_proposals[-3:]:  # Show last 3 proposals
                author_info = f"by {proposal.author}"
                if agent_pool and proposal.author in agent_pool.agents:
                    author_agent = agent_pool.agents[proposal.author]
                    profile = author_agent.metadata.get("protocol_profile", {})
                    if profile:
                        # Show key traits of other agents
                        key_traits = []
                        for trait in ["initiative", "sociability", "persuasiveness"]:
                            if trait in profile:
                                key_traits.append(f"{trait[:4]}={profile[trait]:.2f}")
                        if key_traits:
                            author_info += f" [{', '.join(key_traits)}]"

                context_lines.append(f"- Proposal {proposal.proposal_id} {author_info}")
                context_lines.append(
                    f"  \"{proposal.content[:100]}{'...' if len(proposal.content) > 100 else ''}\""
                )
        else:
            context_lines.append("\nNo active proposals yet.")

    context_lines.append("-----")

    return "\n".join(context_lines)


def build_base_context(agent, issue):
    """
    Build shared context elements that appear in all phases.
    
    Returns markdown with agent traits and issue problem statement.
    """
    # Extract traits from agent metadata
    profile = agent.metadata.get("protocol_profile", {})
    
    context_lines = [f"# Agent: {agent.agent_id}", "", "## Traits"]
    
    # Add traits in a clean markdown list format
    for trait_name, value in profile.items():
        if isinstance(value, (int, float)):
            context_lines.append(f"- {trait_name}: {value:.2f}")
    
    context_lines.extend(["", f"## Issue {issue.issue_id}", issue.problem_statement])
    
    return "\n".join(context_lines)


def build_context_propose(agent, issue):
    """
    Build context for propose phase - clean and minimal.
    
    Per spec: Only shared elements (traits + issue), no prior proposals.
    This is a creative, unconstrained phase.
    """
    return build_base_context(agent, issue)


def build_context_feedback(agent, issue, selected_proposals=None):
    """
    Build context for feedback phase with curated proposals.
    
    Per spec: Shared elements + selected proposals for review.
    No word counts, timestamps, or author traits.
    """
    context = build_base_context(agent, issue)
    
    if not selected_proposals:
        # If no specific proposals selected, show active proposals (limit to 2 for token efficiency)
        active_proposals = [p for p in issue.proposals if getattr(p, "active", True) and p.author != "system"]
        selected_proposals = active_proposals[:2]
    
    if selected_proposals:
        context += "\n\n"
        for proposal in selected_proposals:
            context += f"## Proposal {proposal.proposal_id} by {proposal.author}\n"
            context += f"{proposal.content}\n\n"
    
    return context.rstrip()


def build_context_revise(agent, issue):
    """
    Build context for revise phase with agent's proposal and feedback received.
    
    Per spec: Shared elements + agent's original proposal + curated feedback received.
    No agent memory logs, word counts, or metadata.
    """
    context = build_base_context(agent, issue)
    
    # Find the agent's original proposal
    agent_proposal = None
    for proposal in issue.proposals:
        if proposal.author == agent.agent_id and getattr(proposal, "active", True):
            agent_proposal = proposal
            break
    
    if agent_proposal:
        context += f"\n\n## Your Original Proposal\n{agent_proposal.content}\n"
    
    # Find feedback received on agent's proposal
    feedback_received = []
    if hasattr(issue, 'feedback_log') and agent_proposal:
        feedback_received = [
            fb for fb in issue.feedback_log 
            if fb.get("to") == agent_proposal.proposal_id
        ]
    
    if feedback_received:
        context += "\n"
        for feedback in feedback_received:
            context += f"## Feedback from {feedback['from']}\n"
            context += f"{feedback['comment']}\n\n"
    
    return context.rstrip()


def build_context_stake(agent, issue, payload):
    """
    Build context for stake phase with structured format for action decisions.
    
    This is used for Phase 2 (tactical actions) and includes preferences, ledger, and leaderboard.
    """
    # Get current state information
    current_balance = payload.get("current_balance", 0)
    tick = payload.get("tick", 0)
    max_ticks = payload.get("max_ticks", 15)  # Default fallback
    current_conviction = payload.get("current_conviction", {})
    
    # Extract traits from agent metadata
    profile = agent.metadata.get("protocol_profile", {})
    
    # Start building context with agent information
    context_lines = [
        "# 🧠 Agent Context",
        "",
        "## Agent ID",
        agent.agent_id,
        "",
        "## Your Traits",
        "| Trait         | Value |",
        "|---------------|-------|"
    ]
    
    # Add traits table
    for trait_name, value in profile.items():
        if isinstance(value, (int, float)):
            context_lines.append(f"| {trait_name:<13} | {value:<5.1f} |")
    
    return "\n".join(context_lines)


def build_context_stake_preferences(agent, issue, payload):
    """
    Build context for stake preferences (Phase 1) - simpler format with proposals.
    """
    # Get current state information - NO DEFAULTS to expose missing data
    logger.info(f"[STAKE-LLM] Building context for {agent.agent_id} at tick {payload.get('tick', 0)}")   
    

    current_balance = payload["current_balance"]  # Will KeyError if missing
    tick = payload["tick"]  # Will KeyError if missing  
    max_ticks = payload.get("max_ticks", 15)  # This one can have a default
    
    # Extract traits from agent metadata
    profile = agent.metadata.get("protocol_profile", {})
    
    # Start building context with agent information
    context_lines = [
        "# 🧠 Agent Context",
        "",
        "## Agent ID",
        agent.agent_id,
        "",
        "## Your Traits",
        "| Trait         | Value |",
        "|---------------|-------|"
    ]
    
    # Add traits table
    for trait_name, value in profile.items():
        if isinstance(value, (int, float)):
            context_lines.append(f"| {trait_name:<13} | {value:<5.1f} |")
    
    context_lines.extend([
        "",
        "## Credit Balance",
        f"{current_balance} CP",
        "",
        "## Current Tick", 
        f"Tick {tick} of {max_ticks}",
        "",
        "---",
        "",
        "# 📄 Active Proposals"
    ])
    
    # Add proposals section
    if hasattr(issue, 'proposals') and issue.proposals:
        active_proposals = [p for p in issue.proposals if getattr(p, "active", True)]
        
        for proposal in active_proposals:
            # Check if this is the agent's own proposal
            is_own = proposal.author == agent.agent_id
            proposal_title = f"## Proposal {proposal.proposal_id}"
            if is_own:
                proposal_title += " (Your Proposal)"
            
            context_lines.extend([
                "",
                proposal_title,
                f"- **Author**: {proposal.author}",
                "- **Content**:",
                f"> {proposal.content}"
            ])
    else:
        context_lines.extend([
            "",
            "No active proposals available."
        ])
    
    
    logger.debug(f"[STAKE-LLM] Preference context size = {len(context_lines)} lines")
    return "\n".join(context_lines)


def build_context_stake_action(agent, issue, payload, stored_preferences):
    """
    Build context for stake action decisions (Phase 2) with preferences, ledger, and leaderboard.
    """
    # Get current state information - NO DEFAULTS to expose missing data
    print(f"PAYLOAD_DEBUG: Available keys: {list(payload.keys())}")
    
    # Fail explicitly if expected keys are missing
    if "current_balance" not in payload:
        print(f"ERROR: 'current_balance' not in payload. Available: {list(payload.keys())}")
    if "tick" not in payload:
        print(f"ERROR: 'tick' not in payload. Available: {list(payload.keys())}")
    current_balance = payload["current_balance"]  # Will KeyError if missing
    tick = payload["tick"]  # Will KeyError if missing  
    max_ticks = payload.get("max_ticks", 15)  # This one can have a default
    atomic_stakes = payload.get("atomic_stakes", [])  # List of atomic stake records
    
    # Extract traits from agent metadata
    profile = agent.metadata.get("protocol_profile", {})
    
    # Start building context with agent information
    context_lines = [
        "# 🧠 Agent Context",
        "",
        "## Agent ID",
        agent.agent_id,
        "",
        "## Your Traits",
        "| Trait         | Value |",
        "|---------------|-------|"
    ]
    
    # Add traits table
    for trait_name, value in profile.items():
        if isinstance(value, (int, float)):
            context_lines.append(f"| {trait_name:<13} | {value:<5.1f} |")
    
    # Add declared preferences table
    context_lines.extend([
        "",
        "## Declared Preferences",
        "| Proposal ID | Rank | Score | Reasoning Summary |",
        "|-------------|------|-------|--------------------| "
    ])
    
    # Sort preferences by rank and add to table
    prefs_sorted = sorted(stored_preferences['preferences'], key=lambda x: x['rank'])
    for pref in prefs_sorted:
        # Truncate reasoning for table display
        reasoning_summary = pref['reasoning'][:50] + "..." if len(pref['reasoning']) > 50 else pref['reasoning']
        context_lines.append(f"| {pref['proposal_id']:<11} | {pref['rank']:<4} | {pref['preference_score']:<5.1f} | {reasoning_summary:<18} |")
    
    # Add tick progress
    context_lines.extend([
        "",
        "---",
        "",
        "# ⏱️ Tick Progress",
        "",
        f"**Tick {tick} of {max_ticks}**",
        "",
        "---",
        "",
        "# 💰 CP Balance",
        "",
        f"**Remaining CP:** {current_balance}"
    ])
    
    # Add active stake ledger
    context_lines.extend([
        "",
        "---",
        "",
        "# 📑 Active Stake Ledger",
        "",
        "| Tick | Agent ID | Proposal ID | CP | Age (ticks) | Multiplier | CP × Multiplier |",
        "|------|----------|-------------|----|-------------|------------|------------------|"
    ])
    
    # Show ALL atomic stakes (from all agents), not just this agent's
    self_proposal_id = stored_preferences.get('self_proposal_id')
    has_stakes = len(atomic_stakes) > 0
    
    for stake in atomic_stakes:
        # Mark if this stake is by the current agent
        agent_marker = " (you)" if stake["agent_id"] == agent.agent_id else ""
        agent_display = f"{stake['agent_id']}{agent_marker}"
        context_lines.append(f"| {stake['stake_tick']:<4} | {agent_display:<8} | {stake['proposal_id']:<11} | {stake['staked_cp']:<2} | {stake['age']:<11} | {stake['conviction_multiplier']:<10.2f} | {stake['total_cp']:<15.1f} |")
    
    if not has_stakes:
        context_lines.append("| --   | --       | --          | -- | --          | --         | --              |")
        context_lines.append("")
        context_lines.append("> **Note**: No active stakes.")
    elif self_proposal_id and any(stake["proposal_id"] == self_proposal_id and stake["agent_id"] == agent.agent_id for stake in atomic_stakes):
        context_lines.append("")
        context_lines.append(f"> **Note**: You cannot unstake from Proposal {self_proposal_id} (your own), but you *may* switch this stake.")
    
    # Add proposal leaderboard
    context_lines.extend([
        "",
        "---",
        "",
        "# 🏆 Proposal Leaderboard",
        "",
        "| Proposal ID | Total CP Staked | Effective Conviction Value |",
        "|-------------|------------------|-----------------------------|"
    ])
    
    # Calculate totals and effective values for leaderboard
    if hasattr(issue, 'proposals') and issue.proposals:
        active_proposals = [p for p in issue.proposals if getattr(p, "active", True)]
        leaderboard_data = []
        
        for proposal in active_proposals:
            proposal_id = proposal.proposal_id
            total_cp = 0
            effective_conviction = 0.0
            
            # Calculate totals from atomic stakes
            proposal_stakes = [stake for stake in atomic_stakes if stake["proposal_id"] == proposal_id]
            for stake in proposal_stakes:
                total_cp += stake["staked_cp"]
                effective_conviction += stake["total_cp"]
            
            leaderboard_data.append((proposal_id, total_cp, effective_conviction))
        
        # Sort by effective conviction value (descending)
        leaderboard_data.sort(key=lambda x: x[2], reverse=True)
        
        for proposal_id, total_cp, effective_conviction in leaderboard_data:
            # Mark if it's the agent's own proposal
            marker = " (you)" if proposal_id == self_proposal_id else ""
            context_lines.append(f"| {proposal_id:<11}{marker:<6} | {total_cp:<16} | {effective_conviction:<27.1f} |")
    
    context_lines.extend([
        "",
        "---"
    ])
    
    return "\n".join(context_lines)
