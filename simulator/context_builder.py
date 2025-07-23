"""
Simple context builder for agent LLM calls.
Provides minimal, focused context in readable format.
"""

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
        
        context_lines.append(f"Proposal:{proposal.proposal_id}, Agent:{proposal.author} Traits:{author_traits}")
        
        # Add full proposal content
        context_lines.append(f'"{proposal.content}"')
        context_lines.append("")
        
        # Add feedback for this proposal
        proposal_feedback = [fb for fb in feedback_log 
                           if fb.get("to") == proposal.proposal_id]
        
        if proposal_feedback:
            for fb in proposal_feedback[-3:]:  # Last 3 feedback items
                context_lines.append(f'Feedback - {fb["from"]}: "{fb["comment"]}"')
        else:
            context_lines.append("No feedback yet")
            
        context_lines.append("-----")
    
    return "\n".join(context_lines)

def enhance_context_for_call(agent, base_context, call_type, **kwargs):
    """
    Enhance the context parameter for LLM calls.
    Only adds context where it's actually useful.
    """
    
    if call_type == "proposal":
        # Proposals don't need much context - just current state
        tick = kwargs.get('tick', 0)
        return f"Tick {tick}\n\n{base_context}" if base_context else f"Tick {tick}"
    
    elif call_type == "propose_decision":
        # Propose decisions need rich context about current state and agent's history
        return build_propose_decision_context(agent, **kwargs)
    
    elif call_type == "feedback":
        # Feedback needs full context of current proposals and feedback
        state = kwargs.get('state')
        all_proposal_contents = kwargs.get('all_proposal_contents', {})
        tick = kwargs.get('tick', 0)
        
        if state:
            agent_pool = kwargs.get('agent_pool')
            return build_feedback_context(state, all_proposal_contents, tick, agent_pool)
        else:
            return base_context or f"Tick {tick}"
    
    else:
        # Other calls (revision, etc.) - minimal enhancement
        return base_context or ""

def build_propose_decision_context(agent, **kwargs):
    """
    Build rich context for propose decision LLM calls.
    
    Includes:
    - Current tick and issue information
    - Agent's memory of past actions in this phase
    - Current state of proposals and feedback if available
    - Agent's trait summary
    """
    tick = kwargs.get('tick', 0)
    issue_id = kwargs.get('issue_id', 'unknown')
    memory = kwargs.get('memory', {})
    state = kwargs.get('state')
    agent_pool = kwargs.get('agent_pool')
    
    context_lines = [
        f"Tick {tick}",
        f"Issue: {issue_id}",
        "-----"
    ]
    
    # Add agent's memory of past actions in this phase
    if memory:
        has_acted = memory.get('has_acted', False)
        if has_acted:
            context_lines.append("You have already acted in this propose phase.")
        else:
            context_lines.append("You have not yet acted in this propose phase.")
        
        initial_decision = memory.get('initial_decision')
        if initial_decision:
            context_lines.append(f"Previous decision approach: {initial_decision}")
    
    # Add current state information if available
    if state and state.current_issue:
        proposals = state.current_issue.proposals
        active_proposals = [p for p in proposals if p.active]
        
        if active_proposals:
            context_lines.append(f"\nCurrent proposals ({len(active_proposals)} active):")
            for proposal in active_proposals[-3:]:  # Show last 3 proposals
                author_info = f"by {proposal.author}"
                if agent_pool and proposal.author in agent_pool.agents:
                    author_agent = agent_pool.agents[proposal.author]
                    profile = author_agent.metadata.get("protocol_profile", {})
                    if profile:
                        # Show key traits of other agents
                        key_traits = []
                        for trait in ['initiative', 'sociability', 'persuasiveness']:
                            if trait in profile:
                                key_traits.append(f"{trait[:4]}={profile[trait]:.2f}")
                        if key_traits:
                            author_info += f" [{', '.join(key_traits)}]"
                
                context_lines.append(f"- Proposal {proposal.proposal_id} {author_info}")
                context_lines.append(f"  \"{proposal.content[:100]}{'...' if len(proposal.content) > 100 else ''}\"")
        else:
            context_lines.append("\nNo active proposals yet.")
    
    context_lines.append("-----")
    
    return "\n".join(context_lines)