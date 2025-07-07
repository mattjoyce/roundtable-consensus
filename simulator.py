# consensus.py - Simulation runner and configuration generator
import random
from pprint import pprint
from models import GlobalConfig, AgentActor, AgentPool
from primer import Primer
from roundtable import Consensus

# Generate agent pool with 5 < n < 50 agents (seeded)
pool_seed = 123  # Fixed seed for reproducible agent pool generation
random.seed(pool_seed)
pool_size = random.randint(6, 49)  # 6-49 inclusive, so 5 < n < 50
agents = {
    f"Agent_{i}": AgentActor(
        agent_id=f"Agent_{i}",
        initial_balance=100,
        hooks=[],
        metadata={},
        seed=pool_seed + i  # Ensure unique seed for each agent
    ) for i in range(pool_size)
}
agent_pool = AgentPool(agents=agents)

gc = GlobalConfig(
    max_feedback_per_agent=3,
    feedback_stake=5,
    proposal_self_stake=50,
    revision_cycles=2,
    staking_rounds=5,
    conviction_params={
        "MaxMultiplier": 2.0,
        "TargetFraction": 0.98
    },
    agent_pool=agent_pool
)

print(f"Generated agent pool with {pool_size} agents (seed: {pool_seed})")

primer = Primer(gc)
rc = primer.generate_run_config(seed=42, num_agents=5)

scenario = Consensus(global_config=gc, run_config=rc)
result = scenario.run()

print("Phase execution:")
pprint(result["phases_executed"])
print("\nSummary:")
pprint(result["summary"])