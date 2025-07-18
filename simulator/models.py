# models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Literal, Any
from collections import defaultdict
import random
from simlog import log_event, logger, LogEntry, EventType, LogLevel

class Proposal(BaseModel):
    tick: int
    proposal_id: int  # Sequential integer ID
    content: str
    agent_id: str  # Current backer/assignee
    issue_id: str
    metadata: Optional[Dict[str, str]] = {}
    active: bool = True
    author: str  # Agent name who created the proposal
    author_type: str = "agent"  # "agent" or "system"
    parent_id: Optional[int] = None  # Previous version ID for revisions
    revision_number: int = 1  # Version number (starts at 1)
    type: str = "standard"  # Either 'standard' or 'noaction'

class Agent(BaseModel):
    agent_id: str
    balance: int
    metadata: Optional[Dict[str, str]] = {}

class AgentActor(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    agent_id: str
    initial_balance: int
    metadata: Optional[Dict[str, Any]] = {}
    seed: Optional[int] = None  # Optional seed for reproducibility
    rng: Optional[random.Random] = None
    memory: Dict[str, Any] = {}
    latest_proposal_id: Optional[int] = None  # Track agent's current proposal

    def on_signal(self, payload: Dict[str, str|int]) -> Optional[dict]:
        """Handle signals sent to the agent."""
        from automoton import handle_signal
        return handle_signal(self, payload)

    def clone(self) -> 'AgentActor':
        new_rng = random.Random(self.seed) if self.seed is not None else None
        return AgentActor(
            agent_id=self.agent_id,
            initial_balance=self.initial_balance,
            metadata=self.metadata.copy() if self.metadata else {},
            seed=self.seed,
            rng=new_rng,
            memory={},
            latest_proposal_id=self.latest_proposal_id
        )

class AgentPool(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    agents: Dict[str, AgentActor]

    def get(self, agent_id: str) -> AgentActor:
        return self.agents[agent_id]

    def select_random(self, n: int, seed: int = None) -> Dict[str, AgentActor]:
        import random
        rng = random.Random(seed)
        selected_ids = rng.sample(list(self.agents.keys()), n)
        return {aid: self.agents[aid] for aid in selected_ids}

    def get_all_ids(self) -> List[str]:
        return list(self.agents.keys())

class Action(BaseModel):
    type: Literal["submit_proposal", "feedback", "signal_ready", "revise", "stake"]
    agent_id: str
    payload: Dict  # May be refined into specific models later

class ActionQueue(BaseModel):
    queue: List[Action] = []

    def submit(self, action: Action):
        self.queue.append(action)
        logger.debug(f"Action submitted: {action.type} by {action.agent_id}")

    def drain(self) -> List[Action]:
        drained = self.queue.copy()
        self.queue.clear()
        return drained

# Global ACTION_QUEUE instance
ACTION_QUEUE = ActionQueue()


class GlobalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    assignment_award: int = Field(ge=1)
    max_feedback_per_agent: int = Field(ge=1)
    feedback_stake: int = Field(ge=1)
    proposal_self_stake: int = Field(ge=1)
    revision_cycles: int = Field(ge=1, lt=5)
    staking_rounds: int = Field(ge=5, lt=11)
    conviction_params: Dict[str, float]
    agent_pool: AgentPool

class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed: int
    issue_id: str
    agent_ids: List[str]
    selected_agents: Dict[str, AgentActor]
    initial_proposals: Dict[str, str]
    
    def get_initial_balances(self) -> Dict[str, int]:
        return {aid: agent.initial_balance for aid, agent in self.selected_agents.items()}

class UnifiedConfig(BaseModel):
    """Unified configuration combining GlobalConfig and RunConfig into single immutable setup."""
    model_config = ConfigDict(frozen=True)
    
    # From GlobalConfig - System-wide settings
    assignment_award: int = Field(ge=1)
    max_feedback_per_agent: int = Field(ge=1)
    feedback_stake: int = Field(ge=1)
    proposal_self_stake: int = Field(ge=1)
    revision_cycles: int = Field(ge=1, lt=5)
    staking_rounds: int = Field(ge=5, lt=11)
    conviction_params: Dict[str, float]
    agent_pool: AgentPool
    
    # From RunConfig - Simulation-specific settings
    seed: int
    issue_id: str
    agent_ids: List[str]
    selected_agents: Dict[str, AgentActor]
    initial_proposals: Dict[str, str]
    
    def get_initial_balances(self) -> Dict[str, int]:
        """Get initial credit balances for selected agents."""
        return {aid: agent.initial_balance for aid, agent in self.selected_agents.items()}
    
    @classmethod
    def from_configs(cls, global_config: GlobalConfig, run_config: RunConfig) -> 'UnifiedConfig':
        """Create UnifiedConfig from separate GlobalConfig and RunConfig."""
        return cls(
            # GlobalConfig fields
            assignment_award=global_config.assignment_award,
            max_feedback_per_agent=global_config.max_feedback_per_agent,
            feedback_stake=global_config.feedback_stake,
            proposal_self_stake=global_config.proposal_self_stake,
            revision_cycles=global_config.revision_cycles,
            staking_rounds=global_config.staking_rounds,
            conviction_params=global_config.conviction_params,
            agent_pool=global_config.agent_pool,
            # RunConfig fields
            seed=run_config.seed,
            issue_id=run_config.issue_id,
            agent_ids=run_config.agent_ids,
            selected_agents=run_config.selected_agents,
            initial_proposals=run_config.initial_proposals
        )

class RoundtableState(BaseModel):
    """Mutable state for roundtable consensus process focused on solving an Issue."""
    
    # Core state tracking
    tick: int = 0
    current_phase: Optional[str] = None
    phase_start_tick: int = 0
    phase_tick: int = 0
    issue_finalized: bool = False
    finalization_tick: Optional[int] = None
    
    # Agent state during consensus
    agent_balances: Dict[str, int] = {}
    agent_memory: Dict[str, Dict[str, Any]] = {}  # agent_id -> memory dict
    agent_readiness: Dict[str, bool] = {}  # agent_id -> ready status
    agent_proposal_ids: Dict[str, Optional[int]] = {}  # agent_id -> current proposal_id
    
    # Credit and conviction tracking
    credit_events: List[Dict] = []  # Credit burn/award history
    stake_ledger: List[Dict] = []  # Stake records
    conviction_ledger: Dict[str, Dict[int, int]] = Field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))  # agent_id -> proposal_id -> stake
    conviction_rounds: Dict[str, Dict[int, int]] = Field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))  # agent_id -> proposal_id -> consecutive rounds
    conviction_rounds_held: Dict[str, Dict[int, int]] = Field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))  # agent_id -> proposal_id -> total rounds held
    
    # Issue and proposal state
    current_issue: Optional['Issue'] = None
    proposal_counter: int = 1  # Next available proposal ID
    proposals_this_phase: set = set()  # Track proposals in current phase
    
    # Phase execution ledger
    execution_ledger: List[Dict] = []  # Record of all state changes
    
    class Config:
        arbitrary_types_allowed = True
    
    def serialize_for_snapshot(self) -> dict:
        """Serialize state for database snapshot storage."""
        import json
        
        # Convert defaultdict to regular dict for JSON serialization
        conviction_ledger_dict = {}
        for agent_id, proposals in self.conviction_ledger.items():
            conviction_ledger_dict[agent_id] = dict(proposals)
        
        conviction_rounds_dict = {}
        for agent_id, proposals in self.conviction_rounds.items():
            conviction_rounds_dict[agent_id] = dict(proposals)
        
        conviction_rounds_held_dict = {}
        for agent_id, proposals in self.conviction_rounds_held.items():
            conviction_rounds_held_dict[agent_id] = dict(proposals)
        
        return {
            "tick": self.tick,
            "phase": self.current_phase,
            "phase_tick": self.phase_tick,
            "agent_balances": json.dumps(self.agent_balances),
            "agent_readiness": json.dumps(self.agent_readiness),
            "agent_proposal_ids": json.dumps(self.agent_proposal_ids),
            "conviction_ledger": json.dumps(conviction_ledger_dict),
            "conviction_rounds": json.dumps(conviction_rounds_dict),
            "conviction_rounds_held": json.dumps(conviction_rounds_held_dict),
            "stake_ledger": json.dumps(self.stake_ledger),
            "credit_events": json.dumps(self.credit_events),
            "execution_ledger": json.dumps(self.execution_ledger),
            "proposal_counter": self.proposal_counter,
            "issue_finalized": self.issue_finalized,
            "finalization_tick": self.finalization_tick
        }

class Issue(BaseModel):
    issue_id: str
    problem_statement: str
    background: str
    agent_ids: List[str] = []  # Assigned agents
    proposals: List[Proposal] = []
    agent_to_proposal_id: Dict[str, str] = {}
    feedback_log: List[Dict] = []
    metadata: Optional[Dict] = {}
    
    def is_assigned(self, agent_id: str) -> bool:
        """Check if agent is assigned to this issue."""
        return agent_id in self.agent_ids
    
    def add_proposal(self, proposal: Proposal):
        """Add a proposal to this issue."""
        self.proposals.append(proposal)
        self.agent_to_proposal_id[proposal.agent_id] = proposal.proposal_id
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        """Get a proposal by ID."""
        return self.proposals.get(proposal_id)
    
    def assign_agent_to_proposal(self, agent_id: str, proposal_id: str):
        """Assign an agent to a proposal."""
        self.agent_to_proposal_id[agent_id] = proposal_id
    
    def add_feedback(self, from_id: str, target_pid: str, comment: str, tick: int):
        """Add feedback to the feedback log."""
        self.feedback_log.append({
            "from": from_id,
            "to": target_pid,
            "comment": comment,
            "tick": tick
        })

    def count_feedbacks_by(self, agent_id: str) -> int:
        """Count total feedbacks given by an agent."""
        return sum(1 for fb in self.feedback_log if fb["from"] == agent_id)