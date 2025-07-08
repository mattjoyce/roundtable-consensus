# models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional

class Agent(BaseModel):
    agent_id: str
    balance: int
    metadata: Optional[Dict[str, str]] = {}

class AgentActor(BaseModel):
    agent_id: str
    initial_balance: int
    metadata: Optional[Dict[str, str]] = {}
    seed: Optional[int] = None  # Optional seed for reproducibility

    def on_signal(self, payload: Dict[str, str]) ->  Optional[dict]:
        """Handle signals sent to the agent."""
        # This method can be overridden by subclasses to implement specific behavior
        pass

    def clone(self) -> 'AgentActor':
        return AgentActor(
            agent_id=self.agent_id,
            initial_balance=self.initial_balance,
            metadata=self.metadata.copy() if self.metadata else {},
            seed=self.seed
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