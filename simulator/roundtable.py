from models import GlobalConfig, RunConfig, UnifiedConfig, RoundtableState, AgentActor
import random
from typing import List, Dict
from simlog import log_event, logger, LogEntry, EventType, PhaseType, LogLevel, save_state_snapshot

class Phase:
    def __init__(self, phase_type: str, phase_number: int, max_phase_ticks: int = 3):
        self.phase_type = phase_type
        self.phase_number = phase_number
        self.max_phase_ticks = max_phase_ticks  
    
    def execute(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        """Execute phase with lifecycle: begin -> do -> finish."""
        # Handle lifecycle methods conditionally
        if state.phase_tick == 1:
            self._begin(state, config, creditmgr)
        
        self._do(state, agents, config, creditmgr)
        
        if state.phase_tick == self.max_phase_ticks:
            self._finish(state, config, creditmgr)
    
    def _begin(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Initialize phase when it starts."""
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType(self.phase_type),
            event_type=EventType.PHASE_BEGIN,
            payload={
                "phase_number": self.phase_number,
                "phase_type": self.phase_type,
                "max_phase_ticks": self.max_phase_ticks,
                "issue_id": config.issue_id
            },
            message=f"{self.phase_type} Phase [{self.phase_number}] beginning"
        ))
    
    def _finish(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Clean up phase when it ends."""
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType(self.phase_type),
            event_type=EventType.PHASE_FINISH,
            payload={
                "phase_number": self.phase_number,
                "phase_type": self.phase_type,
                "phase_tick": state.phase_tick,
                "issue_id": config.issue_id
            },
            message=f"{self.phase_type} Phase [{self.phase_number}] finishing at tick {state.phase_tick}"
        ))
    
    def _do(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        """Execute main phase logic."""
        raise NotImplementedError("Subclasses must implement _do")
    
    def signal_ready(self, agent_id: str, state: RoundtableState) -> None:
        """Mark agent as ready."""
        if agent_id in state.agent_readiness:
            state.agent_readiness[agent_id] = True
    
    def is_complete(self, state: RoundtableState) -> bool:
        raise NotImplementedError("Subclasses must implement is_complete")

class ProposePhase(Phase):
    def __init__(self, phase_number: int, max_phase_ticks: int = 3):
        super().__init__("PROPOSE", phase_number, max_phase_ticks)
    
    def _begin(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Create NoAction proposal #0."""
        super()._begin(state, config, creditmgr)
        if state.current_issue:
            # Check if NoAction proposal already exists
            existing_noaction = next(
                (p for p in state.current_issue.proposals if p.proposal_id == 0),
                None
            )
            if not existing_noaction:
                from models import Proposal
                noaction_proposal = Proposal(
                    proposal_id=0,  # NoAction always uses ID 0
                    content="Take no Action",
                    agent_id="system",
                    issue_id=state.current_issue.issue_id,
                    tick=state.tick,
                    author="system",
                    author_type="system",
                    type="noaction",
                    revision_number=1,
                )
                state.current_issue.add_proposal(noaction_proposal)
                log_event(LogEntry(
                    tick=state.tick,
                    phase=PhaseType.PROPOSE,
                    event_type=EventType.PROPOSAL_RECEIVED,
                    payload={
                        "proposal_id": noaction_proposal.proposal_id,
                        "agent_id": "system",
                        "issue_id": state.current_issue.issue_id,
                        "proposal_type": "noaction"
                    },
                    message=f"NoAction proposal #0 created for issue {state.current_issue.issue_id}"
                ))
    
    def _finish(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Handle timeout: stake inactive agents to NoAction."""
        super()._finish(state, config, creditmgr)
        if not creditmgr or not state.current_issue:
            return
            
        # Find unready agents and ready agents without stakes
        all_agent_ids = set(creditmgr.get_all_balances().keys())
        unready_agents = [aid for aid, ready in state.agent_readiness.items() if not ready]
        unassigned_ready = [
            agent_id for agent_id in all_agent_ids
            if agent_id not in unready_agents
            and not state.current_issue.is_assigned(agent_id)
        ]
        unstaked_agents = unready_agents + unassigned_ready
        
        if unstaked_agents:
            # Get NoAction proposal (should exist from _begin)
            noaction_proposal = next(
                (p for p in state.current_issue.proposals if p.proposal_id == 0),
                None
            )
            
            if noaction_proposal:
                # Link unstaked agents to NoAction and stake for them
                for agent_id in unstaked_agents:
                    creditmgr.stake_to_proposal(
                        agent_id=agent_id,
                        proposal_id=noaction_proposal.proposal_id,
                        amount=config.proposal_self_stake,
                        tick=state.tick,
                        issue_id=state.current_issue.issue_id,
                    )
                    
                    state.current_issue.assign_agent_to_proposal(
                        agent_id, noaction_proposal.proposal_id
                    )
                    self.signal_ready(agent_id, state)
                    
                    log_event(LogEntry(
                        tick=state.tick,
                        phase=PhaseType.PROPOSE,
                        event_type=EventType.AGENT_READY,
                        agent_id=agent_id,
                        payload={"reason": "no_action_proposal"},
                        message=f"Agent {agent_id} assigned to NoAction on timeout"
                    ))
    
    def _do(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        """Signal agents to make proposal decisions."""
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType.PROPOSE,
            event_type=EventType.PHASE_EXECUTION,
            payload={
                "phase_number": self.phase_number,
                "max_phase_ticks": self.max_phase_ticks
            },
            message=f"Executing Propose Phase [{self.phase_number}] with max think ticks {self.max_phase_ticks}"
        ))
        for agent in agents:
            agent.on_signal({
                "type": "Propose",
                "phase_number": self.phase_number,
                "max_phase_ticks": self.max_phase_ticks,
                "issue_id": config.issue_id,
                "use_llm_proposal": config.llm_config.get('proposal', False),
                "model": config.llm_config.get('model', 'gemma3n:e4b')
            })
    
    def is_complete(self, state: RoundtableState) -> bool:
        return True

class FeedbackPhase(Phase):
    def __init__(self, phase_number: int, cycle_number: int, feedback_stake: int, 
                 max_feedback_per_agent: int, max_phase_ticks: int = 3):
        super().__init__("FEEDBACK", phase_number, max_phase_ticks)
        self.cycle_number = cycle_number
        self.feedback_stake = feedback_stake
        self.max_feedback_per_agent = max_feedback_per_agent
        self.feedback_stats = {}
    
    def _begin(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Initialize feedback phase tracking and log phase start."""
        super()._begin(state, config, creditmgr)
        self.feedback_stats = {
            "feedbacks_submitted": 0,
            "agents_participated": set(),
            "target_proposals": set()
        }
        
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType.FEEDBACK,
            event_type=EventType.PHASE_TRANSITION,
            payload={
                "phase_number": self.phase_number,
                "cycle_number": self.cycle_number,
                "max_feedback_per_agent": self.max_feedback_per_agent,
                "feedback_stake": self.feedback_stake
            },
            message=f"Starting Feedback Phase [{self.phase_number}] for cycle {self.cycle_number}"
        ))
    
    def _do(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        """Signal agents to provide feedback and check for completion."""
        for agent in agents:
            # Get all available proposals for agent decision making
            all_proposals = list(state.agent_proposal_ids.values())
            current_proposal_id = state.agent_proposal_ids.get(agent.agent_id)
            
            # Check if agent has reached max feedback and mark ready if so
            if state.current_issue:
                feedback_count = state.current_issue.count_feedbacks_by(agent.agent_id)
                if feedback_count >= self.max_feedback_per_agent:
                    self.signal_ready(agent.agent_id, state)
                    continue
            
            # Get proposal contents for LLM feedback generation
            all_proposal_contents = {}
            if state.current_issue:
                for proposal in state.current_issue.proposals:
                    if proposal.active:
                        all_proposal_contents[proposal.proposal_id] = proposal.content
            
            agent.on_signal({
                "type": "Feedback",
                "cycle_number": self.cycle_number,
                "tick": state.tick,
                "issue_id": config.issue_id,
                "max_feedback": self.max_feedback_per_agent,
                "all_proposals": all_proposals,
                "current_proposal_id": current_proposal_id,
                "use_llm_feedback": config.llm_config.get('feedback', False),
                "model": config.llm_config.get('model', 'gemma3n:e4b'),
                "all_proposal_contents": all_proposal_contents,
                "state": state,  # Add state for context building
                "agent_pool": config.agent_pool  # Add agent pool for trait display
            })
    
    def _finish(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Complete feedback phase - force all agents ready on timeout."""
        super()._finish(state, config, creditmgr)
        # Calculate feedback stats from actual state
        total_feedbacks = 0
        agents_with_feedback = set()
        target_proposals = set()
        
        if state.current_issue:
            total_feedbacks = len(state.current_issue.feedback_log)
            for feedback in state.current_issue.feedback_log:
                agents_with_feedback.add(feedback["from"])
                target_proposals.add(feedback["to"])
        
        # Force all agents ready on phase timeout
        for agent_id in config.agent_ids:
            self.signal_ready(agent_id, state)
        
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType.FEEDBACK,
            event_type=EventType.PHASE_TRANSITION,
            payload={
                "phase_number": self.phase_number,
                "cycle_number": self.cycle_number,
                "feedbacks_submitted": total_feedbacks,
                "agents_participated": len(agents_with_feedback),
                "target_proposals": len(target_proposals)
            },
            message=f"Completed Feedback Phase [{self.phase_number}]: {total_feedbacks} feedbacks from {len(agents_with_feedback)} agents (timeout)"
        ))
    
    
    def is_complete(self, state: RoundtableState) -> bool:
        """Check if feedback phase is complete."""
        return True

class RevisePhase(Phase):
    def __init__(self, phase_number: int, cycle_number: int, proposal_self_stake: int, 
                 max_phase_ticks: int = 3):
        super().__init__("REVISE", phase_number, max_phase_ticks)
        self.cycle_number = cycle_number
        self.proposal_self_stake = proposal_self_stake
    
    def _do(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType.REVISE,
            event_type=EventType.PHASE_EXECUTION,
            payload={
                "phase_number": self.phase_number,
                "cycle_number": self.cycle_number,
                "proposal_self_stake": self.proposal_self_stake
            },
            message=f"Executing Revise Phase [{self.phase_number}] for cycle {self.cycle_number} with proposal self-stake {self.proposal_self_stake}"
        ))
        
        for agent in agents:
            # TODO: Get actual feedback received for this agent's proposal
            feedback_received = []  # Placeholder - should be populated with actual feedback
            
            # Get agent's current proposal ID
            current_proposal_id = state.agent_proposal_ids.get(agent.agent_id)
            
            # Get all available proposals for agent decision making
            all_proposals = list(state.agent_proposal_ids.values())
            
            agent.on_signal({
                "type": "Revise",
                "cycle_number": self.cycle_number,
                "tick": state.tick,
                "issue_id": config.issue_id,
                "proposal_self_stake": self.proposal_self_stake,
                "feedback_received": feedback_received,
                "current_proposal_id": current_proposal_id,
                "all_proposals": all_proposals,
                "current_balance": state.agent_balances.get(agent.agent_id, 0)
            })
    
    def is_complete(self, state: RoundtableState) -> bool:
        return True

class StakePhase(Phase):
    def __init__(self, phase_number: int, round_number: int, conviction_params: Dict[str, float], 
                 max_phase_ticks: int = 3):
        super().__init__("STAKE", phase_number, max_phase_ticks)
        self.round_number = round_number
        self.conviction_params = conviction_params
    
    def _begin(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Initialize stake phase """
        super()._begin(state, config, creditmgr)
        
        # # Transfer initial proposal stakes to conviction tracking on first STAKE round
        # if self.round_number == 1 and creditmgr:
        #     # Get all initial stakes from the ledger for this issue
        #     initial_stakes = [record for record in state.stake_ledger 
        #                     if record.initial_tick == 1 and record.issue_id == config.issue_id]
            
        #     for stake_record in initial_stakes:
        #         agent_id = stake_record.agent_id
        #         proposal_id = stake_record.proposal_id
        #         stake_amount = stake_record.cp
                
        #         # NOTE: No longer needed - conviction calculated directly from stake records
        #         # Initial stakes are already in the stake ledger, conviction calculated on-demand
                
        #         log_event(LogEntry(
        #             tick=state.tick,
        #             phase=PhaseType.STAKE,
        #             event_type=EventType.PROPOSAL_STAKE_TRANSFERRED,
        #             payload={
        #                 "agent_id": agent_id,
        #                 "proposal_id": proposal_id,
        #                 "stake_amount": stake_amount,
        #                 "issue_id": config.issue_id
        #             },
        #             message=f"Transferred initial proposal stake: {agent_id} {stake_amount} CP → {proposal_id} (Round 1)"
        #         ))
    
    def _do(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        """Signal agents to make staking decisions and automatically build conviction."""
        log_event(LogEntry(
            tick=state.tick,
            phase=PhaseType.STAKE,
            event_type=EventType.PHASE_EXECUTION,
            payload={
                "phase_number": self.phase_number,
                "round_number": self.round_number,
                "conviction_params": self.conviction_params
            },
            message=f"Executing Stake Phase [{self.phase_number}] for round {self.round_number} with conviction params {self.conviction_params}"
        ))
        
        # NOTE: Removed auto_build_conviction - conviction now calculated directly from stake records
        # No artificial conviction building needed with atomic stake-based system
        
        for agent in agents:
            # Include current balance in the signal
            current_balance = state.agent_balances.get(agent.agent_id, 0)
            # Get agent's current proposal ID
            current_proposal_id = state.agent_proposal_ids.get(agent.agent_id)
            
            # Get all available proposals for agent decision making
            all_proposals = list(state.agent_proposal_ids.values())
            
            # Get current conviction data for switching decisions (stake-based)
            # current_conviction = {}
            # for agent in agents:
            #     agent_stakes = state.get_active_stakes_by_agent(agent.agent_id)
            #     if agent_stakes:
            #         agent_convictions = {}
            #         for stake in agent_stakes:
            #             conviction = creditmgr.calculate_stake_conviction(stake, state.tick, self.conviction_params)
            #             if conviction > 0:
            #                 if stake.proposal_id not in agent_convictions:
            #                     agent_convictions[stake.proposal_id] = 0
            #                 agent_convictions[stake.proposal_id] += conviction
            #         if agent_convictions:
            #             current_conviction[agent.agent_id] = agent_convictions
            
            agent.on_signal({
                "type": "Stake",
                "round_number": self.round_number,
                "conviction_params": self.conviction_params,
                "tick": state.tick,
                "issue_id": config.issue_id,
                "current_balance": current_balance,
                "current_proposal_id": current_proposal_id,
                "all_proposals": all_proposals,
            })
    
    def is_complete(self, state: RoundtableState) -> bool:
        return True

class FinalizePhase(Phase):
    def __init__(self, phase_number: int, max_phase_ticks: int = 3):
        super().__init__("FINALIZE", phase_number, max_phase_ticks)
    
    def _begin(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Initialize finalization phase."""
        super()._begin(state, config, creditmgr)
        # Additional finalization-specific initialization can go here
    
    def _do(self, state: RoundtableState, agents: List[AgentActor], config: UnifiedConfig, creditmgr=None) -> None:
        """Signal agents about finalization and mark them ready."""
        # Signal agents about finalization phase
        for agent in agents:
            agent.on_signal({
                "type": "Finalize",
                "phase_number": self.phase_number,
                "tick": state.tick,
                "issue_id": config.issue_id
            })
        
        # Mark all agents as ready since finalization doesn't require agent input
        for agent in agents:
            state.agent_readiness[agent.agent_id] = True
    
    def _finish(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Complete finalization phase and execute finalization logic."""
        super()._finish(state, config, creditmgr)
        
        # Execute the actual finalization logic to calculate conviction multipliers and determine winner
        # Need to get the consensus instance to call finalize_issue()
        # For now, we'll inline the finalization logic here
        self._execute_finalization(state, config, creditmgr)
    
    def _execute_finalization(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None) -> None:
        """Execute finalization logic using stake records."""
        issue_id = config.issue_id
        tick = state.tick
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_START,
            payload={
            "issue_id": issue_id
            },
            message=f"Starting finalization for issue {issue_id} at tick {tick}"
        ))
        
        # Aggregate conviction weights by proposal using latest stake records
        proposal_weights = self._aggregate_conviction_weights_inline(state, config, creditmgr)
        
        if not proposal_weights:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType.FINALIZE,
                event_type=EventType.FINALIZATION_WARNING,
                payload={
                    "issue_id": issue_id,
                    "reason": "no_stakes_found"
                },
                message="No conviction stakes found for finalization"
            ))
            return
        
        # Determine winner with tie-breaking
        winner_proposal_id, winner_data = self._determine_winner_inline(proposal_weights)
        
        # Emit finalization decision event
        self._emit_finalization_decision_inline(winner_proposal_id, winner_data, issue_id, tick, state)
        
        # Emit influence recorded events for winning proposal
        self._emit_influence_events_inline(winner_proposal_id, issue_id, tick, state, config, creditmgr)
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_COMPLETE,
            payload={
            "issue_id": issue_id,
            "winner_proposal_id": winner_proposal_id
            },
            message=f"Finalization completed for issue {issue_id} - Winner: {winner_proposal_id}"
        ))
    
    def _aggregate_conviction_weights_inline(self, state: RoundtableState, config: UnifiedConfig, creditmgr=None):
        """Aggregate effective weights by proposal using latest stake records."""
        proposal_weights = {}
        conviction_params = config.conviction_params
        current_tick = state.tick
        
        # Find the first stake phase tick for mandatory stake time calculation
        first_stake_tick = None
        for phase_entry in state.execution_ledger:
            if phase_entry.get("phase") == "STAKE":
                first_stake_tick = phase_entry["tick"]
                break
        
        if first_stake_tick is None:
            # Fallback if no stake phase found in ledger
            first_stake_tick = current_tick
        
        # Get all active stakes for this issue
        active_stakes = [stake for stake in state.stake_ledger 
                        if stake.status == "active" and stake.issue_id == config.issue_id]
        
        # Group stakes by proposal and calculate conviction multipliers
        for stake in active_stakes:
            proposal_id = stake.proposal_id
            
            # Calculate time held based on stake type
            if stake.mandatory:
                # Mandatory stakes use time from first stake phase tick
                time_held = current_tick - first_stake_tick
            else:
                # Voluntary stakes use time from their initial tick (during stake phases)
                time_held = current_tick - stake.initial_tick
            
            # Calculate conviction multiplier for this stake
            growth_multiplier = creditmgr.calculate_growth_curve(time_held, conviction_params)
            effective_weight = round(stake.cp * growth_multiplier, 2)
            
            if proposal_id not in proposal_weights:
                proposal_weights[proposal_id] = {
                    "total_effective_weight": 0,
                    "total_raw_weight": 0,
                    "contributor_count": 0,
                    "first_stake_tick": stake.initial_tick if not stake.mandatory else first_stake_tick
                }
            
            proposal_weights[proposal_id]["total_effective_weight"] += effective_weight
            proposal_weights[proposal_id]["total_raw_weight"] += stake.cp
            proposal_weights[proposal_id]["contributor_count"] += 1
            
            # Track earliest stake tick for tie-breaking (use first stake tick for mandatory)
            stake_tick = first_stake_tick if stake.mandatory else stake.initial_tick
            if stake_tick < proposal_weights[proposal_id]["first_stake_tick"]:
                proposal_weights[proposal_id]["first_stake_tick"] = stake_tick
        
        return proposal_weights
    
    def _determine_winner_inline(self, proposal_weights):
        """Determine winning proposal with tie-breaking by earliest stake."""
        if not proposal_weights:
            return None, None
        
        # Find proposal with highest effective weight
        max_weight = max(data["total_effective_weight"] for data in proposal_weights.values())
        
        # Get all proposals with max weight (for tie-breaking)
        tied_proposals = [
            (pid, data) for pid, data in proposal_weights.items()
            if data["total_effective_weight"] == max_weight
        ]
        
        # Tie-breaker: earliest first stake tick
        winner_proposal_id, winner_data = min(tied_proposals, key=lambda x: x[1]["first_stake_tick"])
        
        return winner_proposal_id, winner_data
    
    def _emit_finalization_decision_inline(self, winner_proposal_id, winner_data, issue_id, tick, state):
        """Emit the finalization decision event."""
        # Look up the proposal to get the author
        agent_id = "unknown"
        if winner_proposal_id == 0:
            agent_id = "system"  # NoAction proposal
        else:
            # Find the proposal by ID to get the author
            if state.current_issue:
                for proposal in state.current_issue.proposals:
                    if proposal.proposal_id == winner_proposal_id:
                        agent_id = proposal.author
                        break
        
        finalization_event = {
            "type": "finalization_decision",
            "agent_id": agent_id,
            "amount": 0,  # No credit change
            "reason": f"Proposal {winner_proposal_id} declared winner with {winner_data['total_effective_weight']} CP effective weight.",
            "tick": tick,
            "issue_id": issue_id,
            "proposal_id": winner_proposal_id,
            "effective_weight": winner_data["total_effective_weight"],
            "raw_weight": winner_data["total_raw_weight"],
            "final_tick": tick
        }
        
        state.credit_events.append(finalization_event)
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_DECISION,
            payload={
            "proposal_id": winner_proposal_id,
            "agent_id": agent_id,
            "effective_weight": winner_data["total_effective_weight"],
            "raw_weight": winner_data["total_raw_weight"],
            "contributor_count": winner_data["contributor_count"],
            "final_tick": tick,
            "issue_id": issue_id
            },
            message=finalization_event["reason"]
        ))
    
    def _emit_influence_events_inline(self, winner_proposal_id, issue_id, tick, state, config, creditmgr):
        """Emit influence recorded events for each agent's contribution to winning proposal."""
        conviction_params = config.conviction_params
        current_tick = state.tick
        
        # Find the first stake phase tick for mandatory stake time calculation
        first_stake_tick = None
        for phase_entry in state.execution_ledger:
            if phase_entry.get("phase") == "STAKE":
                first_stake_tick = phase_entry["tick"]
                break
        
        if first_stake_tick is None:
            first_stake_tick = current_tick
        
        # Get all active stakes for winning proposal
        winning_stakes = [stake for stake in state.stake_ledger 
                         if stake.status == "active" 
                         and stake.issue_id == issue_id 
                         and stake.proposal_id == winner_proposal_id]
        
        # Group stakes by agent and calculate their contributions
        agent_contributions = {}
        for stake in winning_stakes:
            agent_id = stake.agent_id
            
            # Calculate time held based on stake type
            if stake.mandatory:
                time_held = current_tick - first_stake_tick
            else:
                time_held = current_tick - stake.initial_tick
            
            # Calculate conviction multiplier for this stake
            growth_multiplier = creditmgr.calculate_growth_curve(time_held, conviction_params)
            effective_weight = round(stake.cp * growth_multiplier, 2)
            
            if agent_id not in agent_contributions:
                agent_contributions[agent_id] = {
                    "raw_stake": 0,
                    "effective_contribution": 0,
                    "multiplier": growth_multiplier  # Store last multiplier for logging
                }
            
            agent_contributions[agent_id]["raw_stake"] += stake.cp
            agent_contributions[agent_id]["effective_contribution"] += effective_weight
        
        # Emit influence events for each contributing agent
        for agent_id, contrib_data in agent_contributions.items():
            influence_event = {
                "type": "influence_recorded",
                "agent_id": agent_id,
                "amount": 0,  # No credit change
                "reason": f"Agent {agent_id} contributed {contrib_data['effective_contribution']} CP effective weight to winning proposal {winner_proposal_id}",
                "tick": tick,
                "issue_id": issue_id,
                "winning_proposal_id": winner_proposal_id,
                "contribution": contrib_data["effective_contribution"],
                "raw_stake": contrib_data["raw_stake"],
                "multiplier": contrib_data["multiplier"]
            }
            
            state.credit_events.append(influence_event)
            
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType.FINALIZE,
                event_type=EventType.INFLUENCE_RECORDED,
                payload={
                    "winning_proposal_id": winner_proposal_id,
                    "agent_id": agent_id,
                    "contribution": contrib_data["effective_contribution"],
                    "raw_stake": contrib_data["raw_stake"],
                    "multiplier": contrib_data["multiplier"],
                    "issue_id": issue_id
                },
                message=influence_event["reason"]
            ))

    def is_complete(self, state: RoundtableState) -> bool:
        return True

def generate_phases(config: UnifiedConfig) -> List[Phase]:
    phases = []
    phase_counter = 0
    
    # 1. Initial PROPOSE phase
    phases.append(ProposePhase(
        phase_number=phase_counter,
        max_phase_ticks=config.propose_phase_ticks
    ))
    phase_counter += 1
    
    # 2. FEEDBACK → REVISE cycles
    for cycle in range(config.revision_cycles):
        # FEEDBACK phase
        phases.append(FeedbackPhase(
            phase_number=phase_counter,
            cycle_number=cycle + 1,
            feedback_stake=config.feedback_stake,
            max_feedback_per_agent=config.max_feedback_per_agent,
            max_phase_ticks=config.feedback_phase_ticks
        ))
        phase_counter += 1
        
        # REVISE phase
        phases.append(RevisePhase(
            phase_number=phase_counter,
            cycle_number=cycle + 1,
            proposal_self_stake=config.proposal_self_stake,
            max_phase_ticks=config.revise_phase_ticks
        ))
        phase_counter += 1
    
    # 3. STAKE phase
    # Add TargetRounds to conviction_params to match stake_phase_ticks
    conviction_params_with_target = config.conviction_params.copy()
    conviction_params_with_target["TargetRounds"] = config.stake_phase_ticks
    
    # Single stake phase that runs for stake_phase_ticks
    phases.append(StakePhase(
        phase_number=phase_counter,
        round_number=1,  # Single staking phase
        conviction_params=conviction_params_with_target,
        max_phase_ticks=config.stake_phase_ticks
    ))
    phase_counter += 1
    
    # 4. FINALIZE phase
    phases.append(FinalizePhase(
        phase_number=phase_counter,
        max_phase_ticks=config.finalize_phase_ticks
    ))
    
    return phases



class Consensus:
    def __init__(self, config: UnifiedConfig, state: RoundtableState, creditmgr):
        self.config = config
        self.state = state
        self.creditmgr = creditmgr
        self.phases = generate_phases(config)
        self.current_phase_index = 0

    def run(self):
        """Run the consensus until completion to solve the issue."""
        # check the issue is set
        if not self.config.issue_id:
            raise ValueError("Config must have a valid issue_id set.")
        while not self._is_complete():
            self.tick()
        return self._summarize_results()

    def tick(self):
        self.state.tick += 1
        current_phase = self.get_current_phase()

        # Phase transition detection
        if current_phase.phase_type != self.state.current_phase:
            self.state.current_phase = current_phase.phase_type
            self.state.phase_start_tick = self.state.tick
            self.state.phase_tick = 1
            # Reset agent readiness for new phase
            self.state.agent_readiness = {aid: False for aid in self.state.agent_readiness}
        else:
            self.state.phase_tick += 1

        log_event(LogEntry(
            tick=self.state.tick,
            phase=PhaseType(self.state.current_phase) if self.state.current_phase else None,
            event_type=EventType.CONSENSUS_TICK,
            payload={
                "phase_tick": self.state.phase_tick
            },
            message=f"Tick {self.state.tick} — Phase {self.state.current_phase} (Phase Tick {self.state.phase_tick})"
        ))

        # Phase complete: skip execution, advance phase
        current_phase = self.get_current_phase()
        phase_ticks_expired = current_phase and self.state.phase_tick > current_phase.max_phase_ticks
        
        if self.all_agents_ready and phase_ticks_expired:
            log_event(LogEntry(
                tick=self.state.tick,
                phase=PhaseType(self.state.current_phase) if self.state.current_phase else None,
                event_type=EventType.PHASE_TRANSITION,
                payload={
                    "current_phase_index": self.current_phase_index
                },
                message="All agents ready and think ticks expired — transitioning to next phase."
            ))
            self.current_phase_index += 1

        else:
            # Execute phase logic
            if current_phase:
                agents = list(self.config.selected_agents.values())
                current_phase.execute(self.state, agents, self.config, self.creditmgr)

        # Record the state in the execution ledger
        self.state.execution_ledger.append({
            "tick": self.state.tick,
            "phase": self.state.current_phase,
            "phase_tick": self.state.phase_tick,
            "agent_readiness": self.state.agent_readiness.copy()
        })
        
        # Save complete state snapshot to database
        state_snapshot = self.state.serialize_for_snapshot()
        save_state_snapshot(state_snapshot)
        
        # Log state snapshot event
        log_event(LogEntry(
            tick=self.state.tick,
            phase=PhaseType(self.state.current_phase) if self.state.current_phase else None,
            event_type=EventType.STATE_SNAPSHOT,
            payload={
                "phase_tick": self.state.phase_tick,
                "agent_count": len(self.state.agent_balances),
                "total_credits": sum(self.state.agent_balances.values()),
                "snapshot_size": len(str(state_snapshot))
            },
            message=f"State snapshot saved for tick {self.state.tick}",
            level=LogLevel.DEBUG
        ))



    def get_current_phase(self) -> Phase:
        if self.current_phase_index >= len(self.phases):
            return None
        return self.phases[self.current_phase_index]

    def _is_complete(self):
        return self.current_phase_index >= len(self.phases)
    
    def is_think_tick_over(self) -> bool:
        current_tick = self.state.tick
        start_tick = self.state.phase_start_tick
        phase = self.get_current_phase()
        return (current_tick - start_tick) == phase.max_phase_ticks
    
    def set_agent_ready(self, agent_id: str):
        if agent_id in self.state.agent_readiness:
            self.state.agent_readiness[agent_id] = True
    
    def get_unready_agents(self) -> List[str]:
        return [aid for aid, ready in self.state.agent_readiness.items() if not ready]
    
    @property
    def all_agents_ready(self) -> bool:
        return all(self.state.agent_readiness.values())
    
    def is_final_stake_round(self) -> bool:
        """Check if current phase is the final STAKE round."""
        current_phase = self.get_current_phase()
        if not current_phase or current_phase.phase_type != "STAKE":
            return False
        
        # Check if this is the last STAKE phase in the sequence
        remaining_phases = self.phases[self.current_phase_index + 1:]
        has_more_stake_phases = any(phase.phase_type == "STAKE" for phase in remaining_phases)
        
        return not has_more_stake_phases  

    def finalize_issue(self):
        """
        Finalize the consensus issue by determining the winning proposal
        based on conviction-weighted effective weights and emitting finalization events.
        """
        issue_id = self.config.issue_id
        tick = self.state.tick
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_START,
            payload={
            "issue_id": issue_id
            },
            message=f"Starting finalization for issue {issue_id} at tick {tick}"
        ))
        
        # Aggregate conviction weights by proposal
        proposal_weights = self._aggregate_conviction_weights()
        
        if not proposal_weights:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType.FINALIZE,
                event_type=EventType.FINALIZATION_WARNING,
                payload={
                    "issue_id": issue_id,
                    "reason": "no_stakes_found"
                },
                message="No conviction stakes found for finalization"
            ))
            self._emit_no_winner_event(issue_id, tick)
            self._print_finalization_summary(proposal_weights, None, issue_id, tick)
            return
        
        # Determine winner with tie-breaking
        winner_proposal_id, winner_data = self._determine_winner(proposal_weights)
        
        # Emit finalization decision event
        self._emit_finalization_decision(winner_proposal_id, winner_data, issue_id, tick)
        
        # Emit influence recorded events for winning proposal
        self._emit_influence_events(winner_proposal_id, issue_id, tick)
        
        # Perform protocol cleanup
        self._perform_finalization_cleanup(issue_id, tick)
        
        # Print finalization summary
        self._print_finalization_summary(proposal_weights, winner_proposal_id, issue_id, tick)
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_COMPLETE,
            payload={
            "issue_id": issue_id,
            "winner_proposal_id": winner_proposal_id
            },
            message=f"Finalization completed for issue {issue_id} - Winner: {winner_proposal_id}"
        ))
    
    def _aggregate_conviction_weights(self):
        """Aggregate effective weights by proposal using latest stake records."""
        proposal_weights = {}
        conviction_params = self.config.conviction_params
        current_tick = self.state.tick
        
        # Find the first stake phase tick for mandatory stake time calculation
        first_stake_tick = None
        for phase_entry in self.state.execution_ledger:
            if phase_entry.get("phase") == "STAKE":
                first_stake_tick = phase_entry["tick"]
                break
        
        if first_stake_tick is None:
            # Fallback if no stake phase found in ledger
            first_stake_tick = current_tick
        
        # Get all active stakes for this issue
        active_stakes = [stake for stake in self.state.stake_ledger 
                        if stake.status == "active" and stake.issue_id == self.config.issue_id]
        
        # Group stakes by proposal and calculate conviction multipliers
        for stake in active_stakes:
            proposal_id = stake.proposal_id
            
            # Calculate time held based on stake type
            if stake.mandatory:
                # Mandatory stakes use time from first stake phase tick
                time_held = current_tick - first_stake_tick
            else:
                # Voluntary stakes use time from their initial tick (during stake phases)
                time_held = current_tick - stake.initial_tick
            
            # Calculate conviction multiplier for this stake
            growth_multiplier = self.creditmgr.calculate_growth_curve(time_held, conviction_params)
            effective_weight = round(stake.cp * growth_multiplier, 2)
            
            if proposal_id not in proposal_weights:
                proposal_weights[proposal_id] = {
                    "total_effective_weight": 0,
                    "total_raw_weight": 0,
                    "contributor_count": 0,
                    "first_stake_tick": stake.initial_tick if not stake.mandatory else first_stake_tick
                }
            
            proposal_weights[proposal_id]["total_effective_weight"] += effective_weight
            proposal_weights[proposal_id]["total_raw_weight"] += stake.cp
            proposal_weights[proposal_id]["contributor_count"] += 1
            
            # Track earliest stake tick for tie-breaking (use first stake tick for mandatory)
            stake_tick = first_stake_tick if stake.mandatory else stake.initial_tick
            if stake_tick < proposal_weights[proposal_id]["first_stake_tick"]:
                proposal_weights[proposal_id]["first_stake_tick"] = stake_tick
        
        return proposal_weights
    
    def _determine_winner(self, proposal_weights):
        """Determine winning proposal with tie-breaking by earliest stake."""
        if not proposal_weights:
            return None, None
        
        # Find proposal with highest effective weight
        max_weight = max(data["total_effective_weight"] for data in proposal_weights.values())
        
        # Get all proposals with max weight (for tie-breaking)
        tied_proposals = [
            (pid, data) for pid, data in proposal_weights.items()
            if data["total_effective_weight"] == max_weight
        ]
        
        # Tie-breaker: earliest first stake tick
        winner_proposal_id, winner_data = min(tied_proposals, key=lambda x: x[1]["first_stake_tick"])
        
        return winner_proposal_id, winner_data
    
    def _emit_finalization_decision(self, winner_proposal_id, winner_data, issue_id, tick):
        """Emit the finalization decision event."""
        # Look up the proposal to get the author
        agent_id = "unknown"
        if winner_proposal_id == 0:
            agent_id = "system"  # NoAction proposal
        else:
            # Find the proposal by ID to get the author
            bureau = self.state.get("bureau")
            if bureau and bureau.current_issue:
                for proposal in bureau.current_issue.proposals:
                    if proposal.proposal_id == winner_proposal_id:
                        agent_id = proposal.author
                        break
        
        finalization_event = {
            "type": "finalization_decision",
            "agent_id": agent_id,
            "amount": 0,  # No credit change
            "reason": f"Proposal {winner_proposal_id} declared winner with {winner_data['total_effective_weight']} CP effective weight.",
            "tick": tick,
            "issue_id": issue_id,
            "proposal_id": winner_proposal_id,
            "effective_weight": winner_data["total_effective_weight"],
            "raw_weight": winner_data["total_raw_weight"],
            "final_tick": tick
        }
        
        self.creditmgr.events.append(finalization_event)
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_DECISION,
            payload={
            "proposal_id": winner_proposal_id,
            "agent_id": agent_id,
            "effective_weight": winner_data["total_effective_weight"],
            "raw_weight": winner_data["total_raw_weight"],
            "contributor_count": winner_data["contributor_count"],
            "final_tick": tick,
            "issue_id": issue_id
            },
            message=finalization_event["reason"]
        ))
    
    def _emit_influence_events(self, winner_proposal_id, issue_id, tick):
        """Emit influence recorded events for each agent's contribution to winning proposal."""
        conviction_params = self.config.conviction_params
        current_tick = self.state.tick
        
        # Find the first stake phase tick for mandatory stake time calculation
        first_stake_tick = None
        for phase_entry in self.state.execution_ledger:
            if phase_entry.get("phase") == "STAKE":
                first_stake_tick = phase_entry["tick"]
                break
        
        if first_stake_tick is None:
            first_stake_tick = current_tick
        
        # Get all active stakes for winning proposal
        winning_stakes = [stake for stake in self.state.stake_ledger 
                         if stake.status == "active" 
                         and stake.issue_id == issue_id 
                         and stake.proposal_id == winner_proposal_id]
        
        # Group stakes by agent and calculate their contributions
        agent_contributions = {}
        for stake in winning_stakes:
            agent_id = stake.agent_id
            
            # Calculate time held based on stake type
            if stake.mandatory:
                time_held = current_tick - first_stake_tick
            else:
                time_held = current_tick - stake.initial_tick
            
            # Calculate conviction multiplier for this stake
            growth_multiplier = self.creditmgr.calculate_growth_curve(time_held, conviction_params)
            effective_weight = round(stake.cp * growth_multiplier, 2)
            
            if agent_id not in agent_contributions:
                agent_contributions[agent_id] = {
                    "raw_stake": 0,
                    "effective_contribution": 0,
                    "multiplier": growth_multiplier  # Store last multiplier for logging
                }
            
            agent_contributions[agent_id]["raw_stake"] += stake.cp
            agent_contributions[agent_id]["effective_contribution"] += effective_weight
        
        # Emit influence events for each contributing agent
        for agent_id, contrib_data in agent_contributions.items():
            influence_event = {
                "type": "influence_recorded",
                "agent_id": agent_id,
                "amount": 0,  # No credit change
                "reason": f"Agent {agent_id} contributed {contrib_data['effective_contribution']} CP effective weight to winning proposal {winner_proposal_id}",
                "tick": tick,
                "issue_id": issue_id,
                "winning_proposal_id": winner_proposal_id,
                "contribution": contrib_data["effective_contribution"],
                "raw_stake": contrib_data["raw_stake"],
                "multiplier": contrib_data["multiplier"]
            }
            
            self.state.credit_events.append(influence_event)
            
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType.FINALIZE,
                event_type=EventType.INFLUENCE_RECORDED,
                payload={
                    "winning_proposal_id": winner_proposal_id,
                    "agent_id": agent_id,
                    "contribution": contrib_data["effective_contribution"],
                    "raw_stake": contrib_data["raw_stake"],
                    "multiplier": contrib_data["multiplier"],
                    "issue_id": issue_id
                },
                message=influence_event["reason"]
            ))
    
    def _emit_no_winner_event(self, issue_id, tick):
        """Emit event when no winner can be determined."""
        no_winner_event = {
            "type": "finalization_decision",
            "agent_id": "system",
            "amount": 0,
            "reason": "No winner determined - no conviction stakes found",
            "tick": tick,
            "issue_id": issue_id,
            "proposal_id": None,
            "effective_weight": 0,
            "raw_weight": 0,
            "final_tick": tick
        }
        
        self.creditmgr.events.append(no_winner_event)
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.FINALIZATION_DECISION,
            payload={
            "proposal_id": None,
            "agent_id": "system",
            "effective_weight": 0,
            "raw_weight": 0,
            "final_tick": tick
            },
            message=no_winner_event["reason"]
        ))
    
    def _perform_finalization_cleanup(self, issue_id, tick):
        """Perform final cleanup tasks."""
        # Mark issue as finalized in state
        self.state.issue_finalized = True
        self.state.finalization_tick = tick
        
        # Clear agent readiness flags
        self.agent_ready = {aid: False for aid in self.agent_ready}
        
        # Emit final issue_finalized event
        finalized_event = {
            "type": "issue_finalized",
            "agent_id": "system",
            "amount": 0,
            "reason": f"Issue {issue_id} finalized at tick {tick}",
            "tick": tick,
            "issue_id": issue_id
        }
        
        self.creditmgr.events.append(finalized_event)
        
        log_event(LogEntry(
            tick=tick,
            phase=PhaseType.FINALIZE,
            event_type=EventType.ISSUE_FINALIZED,
            payload={
            "issue_id": issue_id
            },
            message=f"Issue {issue_id} finalized at tick {tick}"
        ))

    def _format_proposal_display(self, proposal_id, issue_id):
        """Format proposal ID for display as #ID (author, revN)."""
        if proposal_id == 0:
            return "#0 (System)"
        
        # Look up the proposal in the current issue
        bureau = self.state.get("bureau")
        if bureau and bureau.current_issue and bureau.current_issue.issue_id == issue_id:
            for proposal in bureau.current_issue.proposals:
                if proposal.proposal_id == proposal_id:
                    return f"#{proposal_id} ({proposal.author}, rev{proposal.revision_number})"
        
        # Fallback if proposal not found
        return f"#{proposal_id}"

    def _print_finalization_summary(self, proposal_weights, winner_proposal_id, issue_id, tick):
        """Print human-readable finalization summary showing influence flow and proposal outcomes."""
        print("\n" + "="*70)
        print(f"🏆 CONSENSUS FINALIZATION SUMMARY - {issue_id}")
        print("="*70)
        
        if not proposal_weights:
            print("❌ No proposals received any conviction stakes")
            return
        
        # Sort proposals by effective weight (highest first)
        ranked_proposals = sorted(
            proposal_weights.items(), 
            key=lambda x: x[1]["total_effective_weight"], 
            reverse=True
        )
        
        print(f"\n📊 PROPOSAL RANKINGS (by Effective Weight):")
        print("-" * 70)
        
        for rank, (proposal_id, data) in enumerate(ranked_proposals, 1):
            marker = "🥇 WINNER" if proposal_id == winner_proposal_id else f"#{rank}"
            effective_weight = data["total_effective_weight"]
            raw_weight = data["total_raw_weight"]
            contributors = data["contributor_count"]
            formatted_proposal = self._format_proposal_display(proposal_id, issue_id)
            
            print(f"{marker:10} {formatted_proposal:<30} "
                  f"Effective: {effective_weight:>8.2f} CP  "
                  f"Raw: {raw_weight:>6} CP  "
                  f"Contributors: {contributors}")
        
        print(f"\n🌊 INFLUENCE FLOW ANALYSIS:")
        print("-" * 70)
        
        conviction_params = self.config.conviction_params
        current_tick = self.state.tick
        
        # Find the first stake phase tick for mandatory stake time calculation
        first_stake_tick = None
        for phase_entry in self.state.execution_ledger:
            if phase_entry.get("phase") == "STAKE":
                first_stake_tick = phase_entry["tick"]
                break
        
        if first_stake_tick is None:
            first_stake_tick = current_tick
        
        # Show detailed influence flow for each proposal
        for proposal_id, data in ranked_proposals:
            formatted_proposal = self._format_proposal_display(proposal_id, issue_id)
            print(f"\n📋 {formatted_proposal}:")
            
            # Find all stakes for this proposal
            proposal_stakes = [stake for stake in self.state.stake_ledger 
                             if stake.status == "active" 
                             and stake.issue_id == issue_id 
                             and stake.proposal_id == proposal_id]
            
            # Group stakes by agent and calculate their contributions
            agent_contributions = {}
            for stake in proposal_stakes:
                agent_id = stake.agent_id
                
                # Calculate time held based on stake type
                if stake.mandatory:
                    time_held = current_tick - first_stake_tick
                else:
                    time_held = current_tick - stake.initial_tick
                
                # Calculate conviction multiplier for this stake
                growth_multiplier = self.creditmgr.calculate_growth_curve(time_held, conviction_params)
                effective_weight = round(stake.cp * growth_multiplier, 2)
                
                if agent_id not in agent_contributions:
                    agent_contributions[agent_id] = {
                        "raw_stake": 0,
                        "effective_contribution": 0,
                        "multiplier": growth_multiplier,
                        "stake_count": 0
                    }
                
                agent_contributions[agent_id]["raw_stake"] += stake.cp
                agent_contributions[agent_id]["effective_contribution"] += effective_weight
                agent_contributions[agent_id]["stake_count"] += 1
            
            if agent_contributions:
                # Sort by effective contribution (highest first)
                supporters = [(agent_id, data["raw_stake"], data["multiplier"], 
                             data["effective_contribution"], data["stake_count"]) 
                            for agent_id, data in agent_contributions.items()]
                supporters.sort(key=lambda x: x[3], reverse=True)
                
                for agent_id, raw_stake, multiplier, effective, stake_count in supporters:
                    print(f"   {agent_id:<20} {raw_stake:>6} CP × {multiplier:>5.3f} = {effective:>8.2f} CP  ({stake_count} stakes)")
            else:
                print(f"   No supporters")
        
        print(f"\n📈 CONVICTION STATISTICS:")
        print("-" * 70)
        
        # Calculate conviction stats from stake records
        all_multipliers = []
        participating_agents = set()
        
        # Get all active stakes for this issue
        active_stakes = [stake for stake in self.state.stake_ledger 
                        if stake.status == "active" and stake.issue_id == issue_id]
        
        for stake in active_stakes:
            participating_agents.add(stake.agent_id)
            
            # Calculate time held based on stake type
            if stake.mandatory:
                time_held = current_tick - first_stake_tick
            else:
                time_held = current_tick - stake.initial_tick
            
            # Calculate conviction multiplier for this stake
            growth_multiplier = self.creditmgr.calculate_growth_curve(time_held, conviction_params)
            all_multipliers.append(growth_multiplier)
        
        if all_multipliers:
            avg_multiplier = sum(all_multipliers) / len(all_multipliers)
            max_multiplier = max(all_multipliers)
            min_multiplier = min(all_multipliers)
            
            print(f"Agents Participated: {len(participating_agents)}")
            print(f"Average Conviction Multiplier: {avg_multiplier:.3f}")
            print(f"Highest Conviction Multiplier: {max_multiplier:.3f}")
            print(f"Lowest Conviction Multiplier: {min_multiplier:.3f}")
            print(f"Total Stakes Recorded: {len(all_multipliers)}")
        
        print("\n" + "="*70)
        print(f"✅ Consensus reached at tick {tick}")
        print("="*70 + "\n")

    def _summarize_results(self):
        phase_summary = []
        for i, phase in enumerate(self.phases):
            phase_summary.append(f"Phase {i}: {phase.phase_type}")
        
        return {
            "final_state": self.state,
            "ledger": self.state.execution_ledger,
            "phases_executed": phase_summary,
            "summary": f"Roundtable completed in {self.state.tick} ticks across {len(self.phases)} phases."
        }
    
    
