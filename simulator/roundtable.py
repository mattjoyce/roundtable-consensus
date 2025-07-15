from models import GlobalConfig, RunConfig, AgentActor
import random
from typing import List, Dict
from loguru import logger

class Phase:
    def __init__(self, phase_type: str, phase_number: int, max_think_ticks: int = 3):
        self.phase_type = phase_type
        self.phase_number = phase_number
        self.max_think_ticks = max_think_ticks  
    
    def execute(self, state: Dict, agents: List[AgentActor]) -> Dict:
        raise NotImplementedError("Subclasses must implement execute")
    
    def is_complete(self, state: Dict) -> bool:
        raise NotImplementedError("Subclasses must implement is_complete")

class ProposePhase(Phase):
    def __init__(self, phase_number: int, max_think_ticks: int = 3):
        super().__init__("PROPOSE", phase_number, max_think_ticks)
    
    def execute(self, state: Dict, agents: List[AgentActor]) -> Dict:
        logger.bind(event_dict={
            "event_type": "phase_execution",
            "phase_type": "PROPOSE",
            "phase_number": self.phase_number,
            "max_think_ticks": self.max_think_ticks
        }).info(f"Executing Propose Phase [{self.phase_number}] with max think ticks {self.max_think_ticks}")
        for agent in agents:
            agent.on_signal({
                "type": "Propose",
                "phase_number": self.phase_number,
                "max_think_ticks": self.max_think_ticks,
                "issue_id": state.get("issue_id")
            })
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class FeedbackPhase(Phase):
    def __init__(self, phase_number: int, cycle_number: int, feedback_stake: int, 
                 max_feedback_per_agent: int, max_think_ticks: int = 3):
        super().__init__("FEEDBACK", phase_number, max_think_ticks)
        self.cycle_number = cycle_number
        self.feedback_stake = feedback_stake
        self.max_feedback_per_agent = max_feedback_per_agent
    
    def execute(self, state: Dict, agents: List[AgentActor]) -> Dict:
        logger.bind(event_dict={
            "event_type": "phase_execution",
            "phase_type": "FEEDBACK",
            "phase_number": self.phase_number,
            "cycle_number": self.cycle_number,
            "max_feedback_per_agent": self.max_feedback_per_agent
        }).info(f"Executing Feedback Phase [{self.phase_number}] for cycle {self.cycle_number} with max feedback per agent {self.max_feedback_per_agent}")
        
        issue_id = state.get("issue_id")
        tick = state.get("tick")
        
        for agent in agents:
            agent.on_signal({
                "type": "Feedback",
                "cycle_number": self.cycle_number,
                "tick": tick,
                "issue_id": issue_id,
                "max_feedback": self.max_feedback_per_agent
            })
        
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class RevisePhase(Phase):
    def __init__(self, phase_number: int, cycle_number: int, proposal_self_stake: int, 
                 max_think_ticks: int = 3):
        super().__init__("REVISE", phase_number, max_think_ticks)
        self.cycle_number = cycle_number
        self.proposal_self_stake = proposal_self_stake
    
    def execute(self, state: Dict, agents: List[AgentActor]) -> Dict:
        logger.bind(event_dict={
            "event_type": "phase_execution",
            "phase_type": "REVISE",
            "phase_number": self.phase_number,
            "cycle_number": self.cycle_number,
            "proposal_self_stake": self.proposal_self_stake
        }).info(f"Executing Revise Phase [{self.phase_number}] for cycle {self.cycle_number} with proposal self-stake {self.proposal_self_stake}")
        
        issue_id = state.get("issue_id")
        tick = state.get("tick")
        
        for agent in agents:
            # TODO: Get actual feedback received for this agent's proposal
            feedback_received = []  # Placeholder - should be populated with actual feedback
            
            # Get agent's current proposal ID - this should be passed from bureau
            current_proposal_id = state.get("agent_proposal_ids", {}).get(agent.agent_id)
            
            agent.on_signal({
                "type": "Revise",
                "cycle_number": self.cycle_number,
                "tick": tick,
                "issue_id": issue_id,
                "proposal_self_stake": self.proposal_self_stake,
                "feedback_received": feedback_received,
                "current_proposal_id": current_proposal_id
            })
        
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class StakePhase(Phase):
    def __init__(self, phase_number: int, round_number: int, conviction_params: Dict[str, float], 
                 max_think_ticks: int = 3):
        super().__init__("STAKE", phase_number, max_think_ticks)
        self.round_number = round_number
        self.conviction_params = conviction_params
    
    def execute(self, state: Dict, agents: List[AgentActor]) -> Dict:
        logger.bind(event_dict={
            "event_type": "phase_execution",
            "phase_type": "STAKE",
            "phase_number": self.phase_number,
            "round_number": self.round_number,
            "conviction_params": self.conviction_params
        }).info(f"Executing Stake Phase [{self.phase_number}] for round {self.round_number} with conviction params {self.conviction_params}")
        
        issue_id = state.get("issue_id")
        tick = state.get("tick")
        creditmgr = state.get("creditmgr")
        
        # Transfer initial proposal stakes to conviction tracking on first STAKE round
        if self.round_number == 1 and creditmgr:
            # Get all initial stakes from the ledger for this issue
            initial_stakes = [record for record in creditmgr.stake_ledger 
                            if record["stake_type"] == "initial" and record["issue_id"] == issue_id]
            
            for stake_record in initial_stakes:
                agent_id = stake_record["staked_by"]
                proposal_id = stake_record["proposal_id"]
                stake_amount = stake_record["amount"]
                
                # Initialize conviction tracking with the initial proposal stake
                conviction_details = creditmgr.update_conviction(
                    agent_id=agent_id,
                    proposal_id=proposal_id,
                    stake_amount=stake_amount,
                    conviction_params=self.conviction_params,
                    tick=tick,
                    issue_id=issue_id
                )
                
                logger.bind(event_dict={
                    "event_type": "proposal_stake_transferred",
                    "agent_id": agent_id,
                    "proposal_id": proposal_id,
                    "stake_amount": stake_amount,
                    "conviction_multiplier": conviction_details["multiplier"],
                    "effective_weight": conviction_details["effective_weight"],
                    "tick": tick,
                    "issue_id": issue_id
                }).info(f"Transferred initial proposal stake: {agent_id} {stake_amount} CP → {proposal_id} (Round 1, effective weight: {conviction_details['effective_weight']})")
        
        for agent in agents:
            # Include current balance in the signal
            current_balance = creditmgr.get_balance(agent.agent_id) if creditmgr else 0
            # Get agent's current proposal ID
            current_proposal_id = state.get("agent_proposal_ids", {}).get(agent.agent_id)
            
            agent.on_signal({
                "type": "Stake",
                "round_number": self.round_number,
                "conviction_params": self.conviction_params,
                "tick": tick,
                "issue_id": issue_id,
                "current_balance": current_balance,
                "current_proposal_id": current_proposal_id
            })
        
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class FinalizePhase(Phase):
    def __init__(self, phase_number: int, max_think_ticks: int = 3):
        super().__init__("FINALIZE", phase_number, max_think_ticks)
    
    def execute(self, state: Dict, agents: List[AgentActor]) -> Dict:
        logger.bind(event_dict={
            "event_type": "phase_execution",
            "phase_type": "FINALIZE",
            "phase_number": self.phase_number,
            "max_think_ticks": self.max_think_ticks
        }).info(f"Executing Finalize Phase [{self.phase_number}] with max think ticks {self.max_think_ticks}")
        
        # Signal agents about finalization phase (optional)
        issue_id = state.get("issue_id")
        tick = state.get("tick")
        
        for agent in agents:
            agent.on_signal({
                "type": "Finalize",
                "phase_number": self.phase_number,
                "tick": tick,
                "issue_id": issue_id
            })
        
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

def generate_phases(global_config: GlobalConfig) -> List[Phase]:
    phases = []
    phase_counter = 0
    
    # 1. Initial PROPOSE phase
    phases.append(ProposePhase(
        phase_number=phase_counter,
        max_think_ticks=3
    ))
    phase_counter += 1
    
    # 2. FEEDBACK → REVISE cycles
    for cycle in range(global_config.revision_cycles):
        # FEEDBACK phase
        phases.append(FeedbackPhase(
            phase_number=phase_counter,
            cycle_number=cycle + 1,
            feedback_stake=global_config.feedback_stake,
            max_feedback_per_agent=global_config.max_feedback_per_agent,
            max_think_ticks=3
        ))
        phase_counter += 1
        
        # REVISE phase
        phases.append(RevisePhase(
            phase_number=phase_counter,
            cycle_number=cycle + 1,
            proposal_self_stake=global_config.proposal_self_stake,
            max_think_ticks=3
        ))
        phase_counter += 1
    
    # 3. STAKE phases (initial self-stake + conviction rounds)
    phases.append(StakePhase(
        phase_number=phase_counter,
        round_number=1,
        conviction_params=global_config.conviction_params,
        max_think_ticks=3
    ))
    phase_counter += 1
    
    # Additional stake rounds for conviction building
    staking_rounds = global_config.staking_rounds
    for stake_round in range(2, staking_rounds + 2):
        phases.append(StakePhase(
            phase_number=phase_counter,
            round_number=stake_round,
            conviction_params=global_config.conviction_params,
            max_think_ticks=3
        ))
        phase_counter += 1
    
    # 4. FINALIZE phase
    phases.append(FinalizePhase(
        phase_number=phase_counter,
        max_think_ticks=3
    ))
    
    return phases

class CreditManager:
    def __init__(self, initial_balances: dict):
        # Map agent_id -> current CP balance
        self.balances = dict(initial_balances)  # Make a copy
        self.events = []  # Burn / Transfer / Rejection logs

    def get_balance(self, agent_id: str) -> int:
        return self.balances.get(agent_id, 0)

    def attempt_deduct(self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str) -> bool:
        if self.get_balance(agent_id) >= amount:
            self.balances[agent_id] -= amount
            self.events.append({
                "type": "Burn",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id
            })
            return True
        else:
            self.events.append({
                "type": "InsufficientCredit",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id
            })
            return False

    def credit(self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str):
        self.balances[agent_id] = self.get_balance(agent_id) + amount
        self.events.append({
            "type": "Credit",
            "agent_id": agent_id,
            "amount": amount,
            "reason": reason,
            "tick": tick,
            "issue_id": issue_id
        })

    def get_all_balances(self) -> dict:
        return dict(self.balances)

    def get_events(self) -> list:
        return list(self.events)


class Consensus:
    def __init__(self, global_config: GlobalConfig, run_config: RunConfig, creditmgr: CreditManager):
        self.gc = global_config
        self.rc = run_config
        self.creditmgr = creditmgr
        self.state = self._init_state()
        self.ledger = []
        self.phases = generate_phases(global_config)
        self.current_phase_index = 0
        self.agent_ready: Dict[str, bool] = {}  # agent_id → True/False
        
        # Initialize agent readiness
        for agent_id in self.rc.agent_ids:
            self.agent_ready[agent_id] = False

    def _init_state(self):
        return {
            "tick": 0,
            "agents": self.rc.agent_ids,
            "balances": self.rc.get_initial_balances(),
            "proposals": dict(self.rc.initial_proposals),
            "current_phase": None,
            "creditmgr": self.creditmgr,
            "phase_start_tick": 0,
            "phase_tick": 0,
            "ready_agents": set()
        }

    def run(self):
        """Run the consensus simulation until completion."""
        # check the issue is set
        if not self.rc.issue_id:
            raise ValueError("RunConfig must have a valid issue_id set.")
        while not self._is_complete():
            self.tick()
        return self._summarize_results()

    def tick(self):
        self.state["tick"] += 1
        current_phase = self.get_current_phase()

        # Phase transition detection
        if current_phase.phase_type != self.state["current_phase"]:
            self.state["current_phase"] = current_phase.phase_type
            self.state["phase_start_tick"] = self.state["tick"]
            self.state["phase_tick"] = 1
            self.state["ready_agents"] = set()
            # Reset agent readiness for new phase
            self.agent_ready = {aid: False for aid in self.agent_ready}
        else:
            self.state["phase_tick"] += 1

        logger.bind(event_dict={
            "event_type": "consensus_tick",
            "tick": self.state['tick'],
            "phase": self.state['current_phase'],
            "phase_tick": self.state['phase_tick']
        }).debug(f"Tick {self.state['tick']} — Phase {self.state['current_phase']} (Phase Tick {self.state['phase_tick']})")

        # Phase complete: skip execution, advance phase
        current_phase = self.get_current_phase()
        phase_ticks_expired = current_phase and self.state['phase_tick'] > current_phase.max_think_ticks
        
        if self.all_agents_ready and phase_ticks_expired:
            logger.bind(event_dict={
                "event_type": "phase_transition",
                "tick": self.state['tick'],
                "current_phase_index": self.current_phase_index
            }).info("All agents ready and think ticks expired — transitioning to next phase.")
            self.current_phase_index += 1

        else:
            # Execute phase logic
            if current_phase:
                agents = list(self.rc.selected_agents.values())
                # agent_proposal_ids should be set by the bureau
                
                self.state = current_phase.execute(self.state, agents)

        # Record the state in the ledger
        self.ledger.append(self.state.copy())



    def get_current_phase(self) -> Phase:
        if self.current_phase_index >= len(self.phases):
            return None
        return self.phases[self.current_phase_index]

    def _is_complete(self):
        return self.current_phase_index >= len(self.phases)
    
    def is_think_tick_over(self) -> bool:
        current_tick = self.state["tick"]
        start_tick = self.state["phase_start_tick"]
        phase = self.get_current_phase()
        return (current_tick - start_tick) == phase.max_think_ticks
    
    def set_agent_ready(self, agent_id: str):
        if agent_id in self.agent_ready:
            self.agent_ready[agent_id] = True
    
    def get_unready_agents(self) -> List[str]:
        return [aid for aid, ready in self.agent_ready.items() if not ready]
    
    @property
    def all_agents_ready(self) -> bool:
        return all(self.agent_ready.values())
    
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
        issue_id = self.state.get("issue_id")
        tick = self.state.get("tick")
        
        logger.bind(event_dict={
            "event_type": "finalization_start",
            "issue_id": issue_id,
            "tick": tick
        }).info(f"Starting finalization for issue {issue_id} at tick {tick}")
        
        # Aggregate conviction weights by proposal
        proposal_weights = self._aggregate_conviction_weights()
        
        if not proposal_weights:
            logger.bind(event_dict={
                "event_type": "finalization_warning",
                "issue_id": issue_id,
                "tick": tick,
                "reason": "no_stakes_found"
            }).warning("No conviction stakes found for finalization")
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
        
        logger.bind(event_dict={
            "event_type": "finalization_complete",
            "issue_id": issue_id,
            "winner_proposal_id": winner_proposal_id,
            "tick": tick
        }).info(f"Finalization completed for issue {issue_id} - Winner: {winner_proposal_id}")
    
    def _aggregate_conviction_weights(self):
        """Aggregate effective weights by proposal from CreditManager's conviction tracking."""
        proposal_weights = {}
        conviction_params = self.gc.conviction_params
        
        # Iterate through all agent conviction data
        for agent_id in self.creditmgr.conviction_ledger:
            for proposal_id, total_stake in self.creditmgr.conviction_ledger[agent_id].items():
                if total_stake > 0:  # Only include proposals with actual stakes
                    # Calculate effective weight using current conviction multiplier
                    multiplier = self.creditmgr.calculate_conviction_multiplier(
                        agent_id, proposal_id, conviction_params
                    )
                    effective_weight = round(total_stake * multiplier, 2)
                    
                    if proposal_id not in proposal_weights:
                        proposal_weights[proposal_id] = {
                            "total_effective_weight": 0,
                            "total_raw_weight": 0,
                            "contributor_count": 0,
                            "first_stake_tick": float('inf')  # Will need to track this separately if needed
                        }
                    
                    proposal_weights[proposal_id]["total_effective_weight"] += effective_weight
                    proposal_weights[proposal_id]["total_raw_weight"] += total_stake
                    proposal_weights[proposal_id]["contributor_count"] += 1
        
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
        # Extract agent_id from proposal_id (assuming format like PAgent_3 or P{agent_id})
        agent_id = "unknown"
        if winner_proposal_id.startswith("P"):
            agent_id = winner_proposal_id[1:].split("@")[0]  # Handle versioned proposals
        
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
        
        logger.bind(event_dict={
            "event_type": "finalization_decision",
            "message": finalization_event["reason"],
            "payload": {
                "proposal_id": winner_proposal_id,
                "agent_id": agent_id,
                "effective_weight": winner_data["total_effective_weight"],
                "raw_weight": winner_data["total_raw_weight"],
                "contributor_count": winner_data["contributor_count"],
                "final_tick": tick,
                "issue_id": issue_id
            }
        }).info(finalization_event["reason"])
    
    def _emit_influence_events(self, winner_proposal_id, issue_id, tick):
        """Emit influence recorded events for each agent's contribution to winning proposal."""
        conviction_params = self.gc.conviction_params
        
        # Calculate each agent's contribution to the winning proposal
        for agent_id in self.creditmgr.conviction_ledger:
            total_stake = self.creditmgr.conviction_ledger[agent_id].get(winner_proposal_id, 0)
            
            if total_stake > 0:
                # Calculate effective weight for this agent's contribution
                multiplier = self.creditmgr.calculate_conviction_multiplier(
                    agent_id, winner_proposal_id, conviction_params
                )
                effective_contribution = round(total_stake * multiplier, 2)
                
                influence_event = {
                    "type": "influence_recorded",
                    "agent_id": agent_id,
                    "amount": 0,  # No credit change
                    "reason": f"Agent {agent_id} contributed {effective_contribution} CP effective weight to winning proposal {winner_proposal_id}",
                    "tick": tick,
                    "issue_id": issue_id,
                    "winning_proposal_id": winner_proposal_id,
                    "contribution": effective_contribution,
                    "raw_stake": total_stake,
                    "multiplier": multiplier
                }
                
                self.creditmgr.events.append(influence_event)
                
                logger.bind(event_dict={
                    "event_type": "influence_recorded",
                    "agent_id": agent_id,
                    "message": influence_event["reason"],
                    "payload": {
                        "winning_proposal_id": winner_proposal_id,
                        "contribution": effective_contribution,
                        "raw_stake": total_stake,
                        "multiplier": multiplier,
                        "tick": tick,
                        "issue_id": issue_id
                    }
                }).info(influence_event["reason"])
    
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
        
        logger.bind(event_dict={
            "event_type": "finalization_decision",
            "message": no_winner_event["reason"],
            "payload": {
                "proposal_id": None,
                "agent_id": "system",
                "effective_weight": 0,
                "raw_weight": 0,
                "final_tick": tick
            }
        }).warning(no_winner_event["reason"])
    
    def _perform_finalization_cleanup(self, issue_id, tick):
        """Perform final cleanup tasks."""
        # Mark issue as finalized in state
        self.state["issue_finalized"] = True
        self.state["finalization_tick"] = tick
        
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
        
        logger.bind(event_dict={
            "event_type": "issue_finalized",
            "issue_id": issue_id,
            "tick": tick
        }).info(f"Issue {issue_id} finalized at tick {tick}")

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
            
            print(f"{marker:10} {proposal_id:<20} "
                  f"Effective: {effective_weight:>8.2f} CP  "
                  f"Raw: {raw_weight:>6} CP  "
                  f"Contributors: {contributors}")
        
        print(f"\n🌊 INFLUENCE FLOW ANALYSIS:")
        print("-" * 70)
        
        conviction_params = self.gc.conviction_params
        
        # Show detailed influence flow for each proposal
        for proposal_id, data in ranked_proposals:
            print(f"\n📋 {proposal_id}:")
            
            # Find all agents who supported this proposal
            supporters = []
            for agent_id in self.creditmgr.conviction_ledger:
                stake = self.creditmgr.conviction_ledger[agent_id].get(proposal_id, 0)
                if stake > 0:
                    multiplier = self.creditmgr.calculate_conviction_multiplier(
                        agent_id, proposal_id, conviction_params
                    )
                    effective = round(stake * multiplier, 2)
                    consecutive_rounds = self.creditmgr.conviction_rounds[agent_id][proposal_id]
                    supporters.append((agent_id, stake, multiplier, effective, consecutive_rounds))
            
            if supporters:
                # Sort by effective contribution (highest first)
                supporters.sort(key=lambda x: x[3], reverse=True)
                for agent_id, raw_stake, multiplier, effective, rounds in supporters:
                    print(f"   {agent_id:<20} {raw_stake:>6} CP × {multiplier:>5.3f} = {effective:>8.2f} CP  ({rounds} rounds)")
            else:
                print(f"   No supporters")
        
        print(f"\n📈 CONVICTION STATISTICS:")
        print("-" * 70)
        
        # Calculate conviction stats
        all_multipliers = []
        total_agents_participated = 0
        
        for agent_id in self.creditmgr.conviction_ledger:
            agent_participated = False
            for proposal_id in self.creditmgr.conviction_ledger[agent_id]:
                stake = self.creditmgr.conviction_ledger[agent_id][proposal_id]
                if stake > 0:
                    if not agent_participated:
                        total_agents_participated += 1
                        agent_participated = True
                    multiplier = self.creditmgr.calculate_conviction_multiplier(
                        agent_id, proposal_id, conviction_params
                    )
                    all_multipliers.append(multiplier)
        
        if all_multipliers:
            avg_multiplier = sum(all_multipliers) / len(all_multipliers)
            max_multiplier = max(all_multipliers)
            min_multiplier = min(all_multipliers)
            
            print(f"Agents Participated: {total_agents_participated}")
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
            "ledger": self.ledger,
            "phases_executed": phase_summary,
            "summary": f"Simulation completed in {self.state['tick']} ticks across {len(self.phases)} phases."
        }
    
    
