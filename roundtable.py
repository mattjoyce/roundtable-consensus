from models import GlobalConfig, RunConfig, Agent, AgentActor, AgentPool
import random
from primer import Primer
from typing import List, Dict

class Phase:
    def __init__(self, phase_type: str, phase_number: int, max_think_ticks: int = 3):
        self.phase_type = phase_type
        self.phase_number = phase_number
        self.max_think_ticks = max_think_ticks
    
    def execute(self, state: Dict, agents: List[Agent]) -> Dict:
        raise NotImplementedError("Subclasses must implement execute")
    
    def is_complete(self, state: Dict) -> bool:
        raise NotImplementedError("Subclasses must implement is_complete")

class ProposePhase(Phase):
    def __init__(self, phase_number: int, max_think_ticks: int = 3):
        super().__init__("PROPOSE", phase_number, max_think_ticks)
    
    def execute(self, state: Dict, agents: List[Agent]) -> Dict:
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
    
    def execute(self, state: Dict, agents: List[Agent]) -> Dict:
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class RevisePhase(Phase):
    def __init__(self, phase_number: int, cycle_number: int, proposal_self_stake: int, 
                 max_think_ticks: int = 3):
        super().__init__("REVISE", phase_number, max_think_ticks)
        self.cycle_number = cycle_number
        self.proposal_self_stake = proposal_self_stake
    
    def execute(self, state: Dict, agents: List[Agent]) -> Dict:
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class StakePhase(Phase):
    def __init__(self, phase_number: int, round_number: int, conviction_params: Dict[str, float], 
                 max_think_ticks: int = 3):
        super().__init__("STAKE", phase_number, max_think_ticks)
        self.round_number = round_number
        self.conviction_params = conviction_params
    
    def execute(self, state: Dict, agents: List[Agent]) -> Dict:
        return state
    
    def is_complete(self, state: Dict) -> bool:
        return True

class FinalizePhase(Phase):
    def __init__(self, phase_number: int, max_think_ticks: int = 3):
        super().__init__("FINALIZE", phase_number, max_think_ticks)
    
    def execute(self, state: Dict, agents: List[Agent]) -> Dict:
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

class Consensus:
    def __init__(self, global_config: GlobalConfig, run_config: RunConfig):
        self.gc = global_config
        self.rc = run_config
        self.state = self._init_state()
        self.ledger = []
        self.phases = generate_phases(global_config)
        self.current_phase_index = 0

    def _init_state(self):
        return {
            "tick": 0,
            "agents": self.rc.agent_ids,
            "balances": self.rc.get_initial_balances(),
            "proposals": dict(self.rc.initial_proposals),
            "current_phase": None,
            "phase_start_tick": 0,
        }

    def run(self):
        while not self._is_complete():
            self.tick()
        return self._summarize_results()

    def tick(self):
        self.state["tick"] += 1
        
        # Get current phase
        current_phase = self.get_current_phase()
        if current_phase != self.state["current_phase"]:
            # Phase transition
            self.state["current_phase"] = current_phase.phase_type if current_phase else None
            self.state["phase_start_tick"] = self.state["tick"]
            
        # Execute current phase
        if current_phase:
            agents = list(self.rc.selected_agents.values())
            self.state = current_phase.execute(self.state, agents)
            
            # Check if phase is complete
            if current_phase.is_complete(self.state):
                self.current_phase_index += 1
        
        # Record state
        self.ledger.append(self.state.copy())

    def get_current_phase(self) -> Phase:
        if self.current_phase_index >= len(self.phases):
            return None
        return self.phases[self.current_phase_index]

    def _is_complete(self):
        return self.current_phase_index >= len(self.phases)
    
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
    
    
