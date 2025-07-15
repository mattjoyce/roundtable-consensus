# models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Literal, Any
import random
from loguru import logger

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