from models import GlobalConfig, RunConfig, AgentActor
import random
from simlog import log_event, logger, LogEntry, EventType, LogLevel
from utils import generate_lorem_content


class Primer:
    """Primer class to generate initial configurations for a simulation."""

    def __init__(self, global_config: GlobalConfig):
        self.gc = global_config

    def generate_run_config(
        self, seed: int, num_agents: int, trait_config: dict = None
    ) -> RunConfig:
        """Generates a RunConfig based on the global configuration and given seed."""
        rng = random.Random(seed)  # Use isolated random instance

        # Select agents from the agent pool and clone them to avoid modifying originals
        selected_agents_raw = self.gc.agent_pool.select_random(num_agents, seed)
        selected_agents = {
            aid: agent.clone() for aid, agent in selected_agents_raw.items()
        }
        agent_ids = list(selected_agents.keys())

        # Inject OCEAN profiles into selected agents
        for i, (aid, agent) in enumerate(selected_agents.items()):
            intended_archetype = agent.metadata.get("base_archetype")
            base_profile, archetype_name = generate_ocean_profile(
                seed + i, intended_archetype
            )
            mutation_rounds = (
                trait_config["mutation_rounds"] if trait_config else MUTATION_ROUNDS
            )
            mutated_profile = mutate_profile(
                base_profile, seed=seed + i, rounds=mutation_rounds
            )

            agent.metadata = agent.metadata or {}
            agent.metadata["ocean_profile"] = mutated_profile
            agent.metadata["archetype"] = archetype_name
            agent.metadata["profile_origin"] = {
                "seed": seed + i,
                "mutations": mutation_rounds,
                "base_archetype": archetype_name,
            }

            logger.info(f"[OCEAN] {aid} ({archetype_name}) → {mutated_profile}")

        initial_proposals = {
            aid: self._generate_lorem_proposal(seed + i, trait_config)
            for i, aid in enumerate(agent_ids)
        }

        return RunConfig(
            seed=seed,
            issue_id=f"Issue_{seed}",
            agent_ids=agent_ids,
            selected_agents=selected_agents,
            initial_proposals=initial_proposals,
        )

    def _generate_lorem_proposal(self, seed: int, trait_config: dict = None) -> str:
        rng = random.Random(seed)  # Use isolated random instance
        if trait_config and "proposal_word_range" in trait_config:
            word_range = trait_config["proposal_word_range"]
            word_count = rng.randint(word_range["min"], word_range["max"])
        else:
            word_count = rng.randint(50, 80)  # Default fallback
        return generate_lorem_content(rng, word_count)


# Fallback constants (used when config not provided)
MUTATION_ROUNDS = 20

# OCEAN (Big Five) personality archetypes
# Keys: openness, conscientiousness, extraversion, agreeableness, neuroticism
ARCHETYPES = {
    "Leader": {
        "openness": 0.70,
        "conscientiousness": 0.80,
        "extraversion": 0.90,
        "agreeableness": 0.50,
        "neuroticism": 0.20,
    },
    "Collaborator": {
        "openness": 0.60,
        "conscientiousness": 0.70,
        "extraversion": 0.70,
        "agreeableness": 0.90,
        "neuroticism": 0.30,
    },
    "Analyst": {
        "openness": 0.50,
        "conscientiousness": 0.90,
        "extraversion": 0.30,
        "agreeableness": 0.50,
        "neuroticism": 0.40,
    },
    "Maverick": {
        "openness": 0.90,
        "conscientiousness": 0.20,
        "extraversion": 0.60,
        "agreeableness": 0.30,
        "neuroticism": 0.50,
    },
    "Diplomat": {
        "openness": 0.60,
        "conscientiousness": 0.60,
        "extraversion": 0.70,
        "agreeableness": 0.80,
        "neuroticism": 0.20,
    },
    "Opportunist": {
        "openness": 0.70,
        "conscientiousness": 0.40,
        "extraversion": 0.70,
        "agreeableness": 0.30,
        "neuroticism": 0.40,
    },
    "Follower": {
        "openness": 0.30,
        "conscientiousness": 0.70,
        "extraversion": 0.50,
        "agreeableness": 0.80,
        "neuroticism": 0.60,
    },
    "Contrarian": {
        "openness": 0.70,
        "conscientiousness": 0.50,
        "extraversion": 0.50,
        "agreeableness": 0.20,
        "neuroticism": 0.60,
    },
    "Saboteur": {
        "openness": 0.50,
        "conscientiousness": 0.15,
        "extraversion": 0.60,
        "agreeableness": 0.10,
        "neuroticism": 0.80,
    },
    "Caretaker": {
        "openness": 0.40,
        "conscientiousness": 0.70,
        "extraversion": 0.60,
        "agreeableness": 0.95,
        "neuroticism": 0.30,
    },
}

ARCHETYPE_NAMES = list(ARCHETYPES.keys())


def generate_ocean_profile(seed: int, archetype_name: str = None) -> tuple[dict, str]:
    """Generate an OCEAN profile from an archetype with small random variations.

    Args:
        seed: Random seed for variations
        archetype_name: Specific archetype to use, or None for random selection

    Returns:
        tuple: (ocean_profile_dict, archetype_name)
    """
    rng = random.Random(seed)

    if archetype_name is None:
        archetype_name = rng.choice(ARCHETYPE_NAMES)

    base_traits = ARCHETYPES[archetype_name].copy()

    # Add small random variations to the archetype (±0.1 max)
    for trait in base_traits:
        variation = rng.uniform(-0.1, 0.1)
        new_value = base_traits[trait] + variation
        base_traits[trait] = round(max(0.02, min(0.98, new_value)), 2)

    return base_traits, archetype_name


def mutate_profile(
    profile: dict, seed: int, rounds: int = MUTATION_ROUNDS, delta: float = 0.05
) -> dict:
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
