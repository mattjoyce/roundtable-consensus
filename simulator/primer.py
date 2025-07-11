
from models import GlobalConfig, RunConfig, AgentActor
import random

class Primer:
    """Primer class to generate initial configurations for a simulation."""
    def __init__(self, global_config: GlobalConfig):
        self.gc = global_config

    def generate_run_config(self, seed: int, num_agents: int) -> RunConfig:
        """Generates a RunConfig based on the global configuration and given seed."""
        random.seed(seed)
        
        # Select agents from the agent pool and clone them to avoid modifying originals
        selected_agents_raw = self.gc.agent_pool.select_random(num_agents, seed)
        selected_agents = {aid: agent.clone() for aid, agent in selected_agents_raw.items()}
        agent_ids = list(selected_agents.keys())
        
        initial_proposals = {
            aid: self._generate_lorem_proposal(seed + i)
            for i, aid in enumerate(agent_ids)
        }
        
        return RunConfig(
            seed=seed,
            issue_id=f"Issue_{seed}",
            agent_ids=agent_ids,
            selected_agents=selected_agents,
            initial_proposals=initial_proposals
        )

    def _generate_lorem_proposal(self, seed: int) -> str:
        random.seed(seed)
        words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur"]
        return " ".join(random.choices(words, k=10))