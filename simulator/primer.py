
from models import GlobalConfig, RunConfig, AgentActor
import random
from loguru import logger

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
        
        # Inject trait profiles into selected agents
        for i, (aid, agent) in enumerate(selected_agents.items()):
            base_profile = generate_base_profile(seed + i)
            mutated_profile = mutate_profile(base_profile, seed=seed + 1000 + i)

            agent.metadata = agent.metadata or {}
            agent.metadata["protocol_profile"] = mutated_profile
            agent.metadata["profile_origin"] = {
                "seed": seed + i,
                "mutations": 20
            }
            
            logger.info(f"[TraitProfile] {aid} → {mutated_profile}")
        
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
        words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
                "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
                "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud", 
                "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo", 
                "consequat", "duis", "aute", "irure", "in", "reprehenderit", "voluptate", 
                "velit", "esse", "cillum", "fugiat", "nulla", "pariatur", "excepteur", "sint", 
                "occaecat", "cupidatat", "non", "proident", "sunt", "culpa", "qui", "officia", 
                "deserunt", "mollit", "anim", "id", "est", "laborum", "suscipit", "lobortis", 
                "nisl", "aliquam", "erat", "volutpat", "blandit", "praesent", "zzril", "delenit", 
                "augue", "feugait", "facilisi", "lorem", "ipsum", "dolor", "diam", "nonummy", "nibh"]
        
        # Generate 50-80 words for bigger proposals
        word_count = random.randint(50, 80)
        return " ".join(random.choices(words, k=word_count))

def generate_base_profile(seed: int) -> dict:
    rng = random.Random(seed)
    return {
        "compliance": round(rng.uniform(0.1, 0.9), 2),
        "initiative": round(rng.uniform(0.1, 0.9), 2),
        "adaptability": round(rng.uniform(0.1, 0.9), 2),
        "sociability": round(rng.uniform(0.1, 0.9), 2),
        "self_interest": round(rng.uniform(0.1, 0.9), 2),
        "risk_tolerance": round(rng.uniform(0.1, 0.9), 2),
        "consistency": round(rng.uniform(0.1, 0.9), 2)
    }

def mutate_profile(profile: dict, seed: int, rounds: int = 20, delta: float = 0.1) -> dict:
    rng = random.Random(seed)
    traits = list(profile.keys())
    new_profile = profile.copy()

    for _ in range(rounds):
        trait = rng.choice(traits)
        direction = rng.choice([-1, 1])
        change = direction * delta
        new_value = round(new_profile[trait] + change, 2)
        new_profile[trait] = max(0.1, min(0.9, new_value))
    
    return new_profile