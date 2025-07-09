# consensus.py - Simulation runner and configuration generator
import random
from pprint import pprint
from models import GlobalConfig, AgentActor, AgentPool, Issue
from primer import Primer
from thebureau import TheBureau

# Generate agent pool with 5 < n < 50 agents (seeded)
pool_seed = 123  # Fixed seed for reproducible agent pool generation
run_seed = 42  # Seed for run configuration generation
print(f"Using pool seed: {pool_seed}, run seed: {run_seed}")

random.seed(pool_seed)
pool_size = random.randint(6, 49)  # 6-49 inclusive, so 5 < n < 50
agents = {
    f"Agent_{i}": AgentActor(
        agent_id=f"Agent_{i}",
        initial_balance=random.randint(0, 300),  # Random initial balance for variety
        metadata={},
        seed=pool_seed + i  # Ensure unique seed for each agent
    ) for i in range(pool_size)
}
agent_pool = AgentPool(agents=agents)
print(f"Generated agent pool with {pool_size} agents (seed: {pool_seed})")

#extract the balanced balances from the agent pool
initial_balances = {aid: agent.initial_balance for aid, agent in agents.items()}


thebureau = TheBureau(agent_pool=agent_pool)

max_scenarios = 5  # Number of simulations to run
for i in range(max_scenarios):
    print(f"Running simulation {i + 1} of {max_scenarios} with seed {run_seed + i}")

    gc = GlobalConfig(
        assignment_award=100,  # Fixed award for assignment
        max_feedback_per_agent=3,
        feedback_stake=5,
        proposal_self_stake=50,
        revision_cycles=random.randint(1, 4),  # Randomize revision cycles for variety
        staking_rounds=random.randint(5, 10),  # Randomize staking rounds
        conviction_params={
            "MaxMultiplier": 2.0,
            "TargetFraction": 0.98
        },
        agent_pool=agent_pool
    )

    primer = Primer(gc)
    rc = primer.generate_run_config(seed=run_seed, num_agents=5)

    # Create a sample issue for the simulation
    issue = Issue(
        issue_id=f"Issue_{run_seed + i}",
        problem_statement="Sample problem statement for the issue.",
        background="Background information about the issue.",
        metadata={"created_by": "simulator", "created_at": "2023-10-01"}
    )

    # Register the issue in TheBureau
    thebureau.register_issue(issue)
    print(f"Registered issue: {issue.issue_id}")



    thebureau.start_consensus_run(global_config=gc, run_config=rc)
    result = thebureau.run()

    print("Phase execution:")
    pprint(result["phases_executed"])
    print("\nSummary:")
    pprint(result["summary"])
