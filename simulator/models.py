"""Core data models for the roundtable consensus simulation."""
import random
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Delayed import to avoid circular dependency
from simlog import log_event, logger


class StakeRecord(BaseModel):
    """Record of a staking transaction in the consensus system."""
    """Atomic stake ledger entry as defined in staking-and-conviction-notes.md"""

    stake_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    proposal_id: int
    cp: int = Field(ge=1)
    initial_tick: int = Field(ge=1)
    status: Literal["active", "closed", "burned"] = "active"
    issue_id: str
    mandatory: bool = False  # True for self-stakes when submitting proposals


class Proposal(BaseModel):
    """A proposal submitted by an agent in the consensus process."""
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
    """Basic agent model with identifier and balance."""
    agent_id: str
    balance: int
    metadata: Optional[Dict[str, str]] = {}


class AgentActor(BaseModel):
    """Active agent participant with RNG, memory, and signal handling capabilities."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    initial_balance: int
    metadata: Optional[Dict[str, Any]] = {}
    seed: Optional[int] = None  # Optional seed for reproducibility
    rng: Optional[random.Random] = None
    memory: Dict[str, Any] = {}
    latest_proposal_id: Optional[int] = None  # Track agent's current proposal

    def on_signal(self, payload: Dict[str, Any]) -> Optional[dict]:
        """Handle signals sent to the agent."""
        # Import here to avoid circular dependency
        from automoton import handle_signal

        return handle_signal(self, payload)

    def clone(self) -> "AgentActor":
        new_rng = random.Random(self.seed) if self.seed is not None else None
        return AgentActor(
            agent_id=self.agent_id,
            initial_balance=self.initial_balance,
            metadata=self.metadata.copy() if self.metadata else {},
            seed=self.seed,
            rng=new_rng,
            memory={},
            latest_proposal_id=self.latest_proposal_id,
        )


class AgentPool(BaseModel):
    """Collection of agents available for selection in consensus scenarios."""
    model_config = ConfigDict(frozen=True)

    agents: Dict[str, AgentActor]

    def get(self, agent_id: str) -> AgentActor:
        """Get an agent by ID."""
        return self.agents[agent_id]

    def select_random(self, num_agents: int, seed: int = None) -> Dict[str, AgentActor]:
        """Select a random subset of agents."""
        rng = random.Random(seed)
        selected_ids = rng.sample(list(self.agents.keys()), num_agents)
        return {aid: self.agents[aid] for aid in selected_ids}

    def get_all_ids(self) -> List[str]:
        """Get all agent IDs in the pool."""
        return list(self.agents.keys())


class Action(BaseModel):
    """An action submitted by an agent to the action queue."""
    type: Literal[
        "submit_proposal",
        "feedback",
        "signal_ready",
        "revise",
        "stake",
        "switch_stake",
        "unstake",
    ]
    agent_id: str
    payload: Dict  # May be refined into specific models later


class ActionQueue(BaseModel):
    """Queue for managing agent actions during consensus phases."""
    queue: List[Action] = []

    def submit(self, action: Action):
        """Add an action to the queue."""
        self.queue.append(action)
        logger.debug(f"Action submitted: {action.type} by {action.agent_id}")

    def drain(self) -> List[Action]:
        """Remove and return all actions from the queue."""
        drained = self.queue.copy()
        self.queue.clear()
        return drained


# Global ACTION_QUEUE instance
ACTION_QUEUE = ActionQueue()


class GlobalConfig(BaseModel):
    """Global configuration parameters for consensus simulation."""
    model_config = ConfigDict(frozen=True)

    assignment_award: int = Field(ge=1)
    max_feedback_per_agent: int = Field(ge=1)
    feedback_stake: int = Field(ge=1)
    proposal_self_stake: int = Field(ge=1)
    revision_cycles: int = Field(ge=1, lt=5)
    conviction_params: Dict[str, float]
    agent_pool: AgentPool

    # Phase timeout configurations
    propose_phase_ticks: int = Field(default=3, ge=1)
    feedback_phase_ticks: int = Field(default=3, ge=1)
    revise_phase_ticks: int = Field(default=3, ge=1)
    stake_phase_ticks: int = Field(default=5, ge=1)
    finalize_phase_ticks: int = Field(default=3, ge=1)

    # LLM configuration
    llm_config: Dict[str, Any] = Field(default_factory=dict)
    
    # Debug configuration
    debug_config: Dict[str, Any] = Field(default_factory=dict)


class RunConfig(BaseModel):
    """Configuration for a specific consensus simulation run."""
    model_config = ConfigDict(frozen=True)

    seed: int
    issue_id: str
    agent_ids: List[str]
    selected_agents: Dict[str, AgentActor]
    initial_proposals: Dict[str, str]

    def get_initial_balances(self) -> Dict[str, int]:
        """Get initial balance mapping for all selected agents."""
        return {
            aid: agent.initial_balance for aid, agent in self.selected_agents.items()
        }


class UnifiedConfig(BaseModel):
    """Unified configuration combining GlobalConfig and RunConfig into single immutable setup."""

    model_config = ConfigDict(frozen=True)

    # From GlobalConfig - System-wide settings
    assignment_award: int = Field(ge=1)
    max_feedback_per_agent: int = Field(ge=1)
    feedback_stake: int = Field(ge=1)
    proposal_self_stake: int = Field(ge=1)
    revision_cycles: int = Field(ge=1, lt=5)
    conviction_params: Dict[str, float]
    agent_pool: AgentPool

    # Phase timeout configurations
    propose_phase_ticks: int = Field(default=3, ge=1)
    feedback_phase_ticks: int = Field(default=3, ge=1)
    revise_phase_ticks: int = Field(default=3, ge=1)
    stake_phase_ticks: int = Field(default=5, ge=1)
    finalize_phase_ticks: int = Field(default=3, ge=1)

    # LLM configuration
    llm_config: Dict[str, Any] = Field(default_factory=dict)

    # From RunConfig - Simulation-specific settings
    seed: int
    issue_id: str
    agent_ids: List[str]
    selected_agents: Dict[str, AgentActor]
    initial_proposals: Dict[str, str]

    def get_initial_balances(self) -> Dict[str, int]:
        """Get initial credit balances for selected agents."""
        return {
            aid: agent.initial_balance for aid, agent in self.selected_agents.items()
        }

    @classmethod
    def from_configs(
        cls, global_config: GlobalConfig, run_config: RunConfig
    ) -> "UnifiedConfig":
        """Create UnifiedConfig from separate GlobalConfig and RunConfig."""
        return cls(
            # GlobalConfig fields
            assignment_award=global_config.assignment_award,
            max_feedback_per_agent=global_config.max_feedback_per_agent,
            feedback_stake=global_config.feedback_stake,
            proposal_self_stake=global_config.proposal_self_stake,
            revision_cycles=global_config.revision_cycles,
            conviction_params=global_config.conviction_params,
            agent_pool=global_config.agent_pool,
            # Phase timeout configurations
            propose_phase_ticks=global_config.propose_phase_ticks,
            feedback_phase_ticks=global_config.feedback_phase_ticks,
            revise_phase_ticks=global_config.revise_phase_ticks,
            stake_phase_ticks=global_config.stake_phase_ticks,
            finalize_phase_ticks=global_config.finalize_phase_ticks,
            llm_config=global_config.llm_config,
            # RunConfig fields
            seed=run_config.seed,
            issue_id=run_config.issue_id,
            agent_ids=run_config.agent_ids,
            selected_agents=run_config.selected_agents,
            initial_proposals=run_config.initial_proposals,
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
    stake_ledger: List[StakeRecord] = (
        []
    )  # Atomic stake records - all conviction calculated from this

    # Issue and proposal state
    current_issue: Optional["Issue"] = None
    proposal_counter: int = 1  # Next available proposal ID
    proposals_this_phase: set = set()  # Track proposals in current phase

    # Phase execution ledger
    execution_ledger: List[Dict] = []  # Record of all state changes

    class Config:
        arbitrary_types_allowed = True

    def get_active_stakes_by_agent(self, agent_id: str) -> List[StakeRecord]:
        """Get all active stakes for an agent."""
        return [
            stake
            for stake in self.stake_ledger
            if stake.agent_id == agent_id and stake.status == "active"
        ]

    def get_active_stakes_for_proposal(self, proposal_id: int) -> List[StakeRecord]:
        """Get all active stakes for a proposal."""
        return [
            stake
            for stake in self.stake_ledger
            if stake.proposal_id == proposal_id and stake.status == "active"
        ]

    def get_agent_stake_on_proposal(
        self, agent_id: str, proposal_id: int
    ) -> List[StakeRecord]:
        """Get agent's active stakes on a specific proposal."""
        return [
            stake
            for stake in self.stake_ledger
            if stake.agent_id == agent_id
            and stake.proposal_id == proposal_id
            and stake.status == "active"
        ]

    def get_mandatory_stakes(self) -> List[StakeRecord]:
        """Get all mandatory stakes."""
        return [
            stake
            for stake in self.stake_ledger
            if stake.mandatory and stake.status == "active"
        ]

    def serialize_for_snapshot(self) -> dict:
        """Serialize state for database snapshot storage."""
        import json

        return {
            "tick": self.tick,
            "phase": self.current_phase,
            "phase_tick": self.phase_tick,
            "agent_balances": json.dumps(self.agent_balances),
            "agent_readiness": json.dumps(self.agent_readiness),
            "agent_proposal_ids": json.dumps(self.agent_proposal_ids),
            "proposals": json.dumps(
                [
                    proposal.model_dump()
                    for proposal in self.current_issue.proposals
                    if proposal.active
                ]
                if self.current_issue
                else []
            ),
            "stake_ledger": json.dumps(
                [stake.model_dump() for stake in self.stake_ledger]
            ),
            "credit_events": json.dumps(self.credit_events),
            "execution_ledger": json.dumps(self.execution_ledger),
            "proposal_counter": self.proposal_counter,
            "issue_finalized": self.issue_finalized,
            "finalization_tick": self.finalization_tick,
        }


class Issue(BaseModel):
    """An issue being decided by consensus with proposals and feedback."""
    issue_id: str
    problem_statement: str
    background: str
    agent_ids: List[str] = []  # Assigned agents
    proposals: List[Proposal] = []
    agent_to_proposal_id: Dict[str, str] = {}
    feedback_log: List[Dict] = []
    metadata: Optional[Dict] = {}

    def is_assigned(self, agent_id: str) -> bool:
        """Check if agent is assigned to this issue (authorized to participate)."""
        # Check if agent is in the authorized agent list for this issue
        return agent_id in self.agent_ids

    def add_proposal(self, proposal: Proposal):
        """Add a proposal to this issue."""
        self.proposals.append(proposal)
        self.agent_to_proposal_id[proposal.agent_id] = proposal.proposal_id

        # Log proposal addition to track array changes
        from simlog import logger

        logger.info(
            f"📝 Issue {self.issue_id}: Added proposal #{proposal.proposal_id} from {proposal.author}. Total proposals: {len(self.proposals)}"
        )

    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        """Get a proposal by ID."""
        return self.proposals.get(proposal_id)

    def assign_agent_to_proposal(self, agent_id: str, proposal_id: str):
        """Assign an agent to a proposal."""
        self.agent_to_proposal_id[agent_id] = proposal_id

    def add_feedback(self, from_id: str, target_pid: str, comment: str, tick: int):
        """Add feedback to the feedback log."""
        self.feedback_log.append(
            {"from": from_id, "to": target_pid, "comment": comment, "tick": tick}
        )

    def count_feedbacks_by(self, agent_id: str) -> int:
        """Count total feedbacks given by an agent."""
        return sum(1 for fb in self.feedback_log if fb["from"] == agent_id)
