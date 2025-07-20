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