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
            
            agent.on_signal({
                "type": "Revise",
                "cycle_number": self.cycle_number,
                "tick": tick,
                "issue_id": issue_id,
                "proposal_self_stake": self.proposal_self_stake,
                "feedback_received": feedback_received
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
        
        for agent in agents:
            agent.on_signal({
                "type": "Stake",
                "round_number": self.round_number,
                "conviction_params": self.conviction_params,
                "tick": tick,
                "issue_id": issue_id
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
        if self.all_agents_ready:
            logger.bind(event_dict={
                "event_type": "phase_transition",
                "tick": self.state['tick'],
                "current_phase_index": self.current_phase_index
            }).info("All agents ready — transitioning to next phase.")
            self.current_phase_index += 1

        else:
            # Execute phase logic
            if current_phase:
                agents = list(self.rc.selected_agents.values())
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
    
    
