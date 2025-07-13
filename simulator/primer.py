
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
            # Use the archetype from agent metadata (set during pool creation)
            intended_archetype = agent.metadata.get("base_archetype")
            base_profile, archetype_name = generate_base_profile(seed + i, intended_archetype)
            mutated_profile = mutate_profile(base_profile, seed=seed + 1000 + i)

            agent.metadata = agent.metadata or {}
            agent.metadata["protocol_profile"] = mutated_profile
            agent.metadata["archetype"] = archetype_name
            agent.metadata["profile_origin"] = {
                "seed": seed + i,
                "mutations": 20,
                "base_archetype": archetype_name
            }
            
            logger.info(f"[TraitProfile] {aid} ({archetype_name}) → {mutated_profile}")
        
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

# Define 8 personality archetypes with distinct trait patterns
ARCHETYPES = {
    "Leader": {
        "compliance": 0.3, "initiative": 0.9, "adaptability": 0.7, "sociability": 0.8,
        "self_interest": 0.6, "risk_tolerance": 0.7, "consistency": 0.8, "persuasiveness": 0.9
    },
    "Collaborator": {
        "compliance": 0.8, "initiative": 0.6, "adaptability": 0.8, "sociability": 0.9,
        "self_interest": 0.3, "risk_tolerance": 0.4, "consistency": 0.7, "persuasiveness": 0.7
    },
    "Analyst": {
        "compliance": 0.9, "initiative": 0.4, "adaptability": 0.3, "sociability": 0.3,
        "self_interest": 0.4, "risk_tolerance": 0.2, "consistency": 0.9, "persuasiveness": 0.5
    },
    "Maverick": {
        "compliance": 0.2, "initiative": 0.8, "adaptability": 0.9, "sociability": 0.5,
        "self_interest": 0.7, "risk_tolerance": 0.9, "consistency": 0.3, "persuasiveness": 0.6
    },
    "Diplomat": {
        "compliance": 0.7, "initiative": 0.5, "adaptability": 0.7, "sociability": 0.8,
        "self_interest": 0.4, "risk_tolerance": 0.3, "consistency": 0.6, "persuasiveness": 0.9
    },
    "Opportunist": {
        "compliance": 0.4, "initiative": 0.7, "adaptability": 0.8, "sociability": 0.6,
        "self_interest": 0.9, "risk_tolerance": 0.8, "consistency": 0.4, "persuasiveness": 0.7
    },
    "Follower": {
        "compliance": 0.9, "initiative": 0.2, "adaptability": 0.5, "sociability": 0.6,
        "self_interest": 0.5, "risk_tolerance": 0.2, "consistency": 0.8, "persuasiveness": 0.3
    },
    "Contrarian": {
        "compliance": 0.2, "initiative": 0.6, "adaptability": 0.4, "sociability": 0.4,
        "self_interest": 0.6, "risk_tolerance": 0.7, "consistency": 0.7, "persuasiveness": 0.8
    },
    "Saboteur": {
    "compliance": 0.05, "initiative": 0.8, "adaptability": 0.6, "sociability": 0.4,
    "self_interest": 0.95, "risk_tolerance": 0.95, "consistency": 0.2, "persuasiveness": 0.7
    },
    "Caretaker": {
    "compliance": 0.85, "initiative": 0.4, "adaptability": 0.7, "sociability": 0.9,
    "self_interest": 0.15, "risk_tolerance": 0.25, "consistency": 0.75, "persuasiveness": 0.65
    }
}

def generate_base_profile(seed: int, archetype_name: str = None) -> tuple[dict, str]:
    """Generate a base profile by using specified archetype or randomly selecting one.
    
    Args:
        seed: Random seed for variations
        archetype_name: Specific archetype to use, or None for random selection
    
    Returns:
        tuple: (profile_dict, archetype_name)
    """
    rng = random.Random(seed)
    
    # Use specified archetype or select randomly
    if archetype_name is None:
        archetype_name = rng.choice(list(ARCHETYPES.keys()))
    
    base_traits = ARCHETYPES[archetype_name].copy()
    
    # Add small random variations to the archetype (±0.1 max)
    for trait in base_traits:
        variation = rng.uniform(-0.1, 0.1)
        new_value = base_traits[trait] + variation
        base_traits[trait] = round(max(0.02, min(0.98, new_value)), 2)
    
    return base_traits, archetype_name

def mutate_profile(profile: dict, seed: int, rounds: int = 20, delta: float = 0.05) -> dict:
    rng = random.Random(seed)
    traits = list(profile.keys())
    new_profile = profile.copy()

    for _ in range(rounds):
        trait = rng.choice(traits)
        direction = rng.choice([-1, 1])
        change = direction * delta
        new_value = round(new_profile[trait] + change, 2)
        new_profile[trait] = max(0.02, min(0.98, new_value))
    
    return new_profile