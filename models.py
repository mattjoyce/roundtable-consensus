# models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Literal

class Proposal(BaseModel):
    tick: int
    proposal_id: str
    content: str
    agent_id: str
    issue_id: str
    metadata: Optional[Dict[str, str]] = {}

class Agent(BaseModel):
    agent_id: str
    balance: int
    metadata: Optional[Dict[str, str]] = {}

class AgentActor(BaseModel):
    agent_id: str
    initial_balance: int
    metadata: Optional[Dict[str, str|int]] = {}
    seed: Optional[int] = None  # Optional seed for reproducibility

    def on_signal(self, payload: Dict[str, str|int]) -> Optional[dict]:
        """Handle signals sent to the agent."""
        # This method can be overridden by subclasses to implement specific behavior
        self.automoton(payload)
        return {"ack": True}

    def clone(self) -> 'AgentActor':
        return AgentActor(
            agent_id=self.agent_id,
            initial_balance=self.initial_balance,
            metadata=self.metadata.copy() if self.metadata else {},
            seed=self.seed
        )
    
    def automoton(self, payload: Dict[str, str|int]) -> Optional[dict]:
        """Simulate Agents Behavior"""
        # This method can be overridden by subclasses to implement specific behavior
        if payload.get("type") == "Propose":
            # Handle proposal logic here
            print(f"Agent {self.agent_id} received proposal signal.")

            if int(self.metadata["proposal_submission_likelihood"]) > 50:
                print(f"Agent {self.agent_id} is likely to submit a proposal.")

                # create a proposal

                proposal = Proposal(
                    proposal_id=f"P{self.agent_id}",
                    content="Sample proposal content",
                    agent_id=self.agent_id,
                    issue_id=payload.get("issue_id", "default_issue"),
                    metadata={"example_key": "example_value"},
                    tick=0
                )
                print(f"Agent {self.agent_id} created proposal: {proposal}")

                # add message to ACTION_QUEUE
                ACTION_QUEUE.submit(Action(
                    type="submit_proposal",
                    agent_id=self.agent_id,
                    payload=proposal.model_dump()
                ))

        elif payload.get("type") == "Feedback":
            # Handle feedback logic here
            print(f"Agent {self.agent_id} received feedback signal.")
        elif payload.get("type") == "Revise":
            # Handle revision logic here
            print(f"Agent {self.agent_id} received revise signal.")
        elif payload.get("type") == "Finalize":
            # Handle finalization logic here
            print(f"Agent {self.agent_id} received finalize signal.")
        else:            
            print(f"Agent {self.agent_id} received unknown signal: {payload}")
        return {"ack": True}

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
    type: Literal["submit_proposal", "feedback", "signal_ready"]
    agent_id: str
    payload: Dict  # May be refined into specific models later

class ActionQueue(BaseModel):
    queue: List[Action] = []

    def submit(self, action: Action):
        self.queue.append(action)
        print(f"Action submitted: {action.type} by {action.agent_id}")

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