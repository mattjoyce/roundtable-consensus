"""Simulation runner and configuration generator for Round Table Consensus."""

import random
import argparse
import time
from typing import List
from models import (
    GlobalConfig,
    AgentActor,
    AgentPool,
    Issue,
)
from primer import Primer, ARCHETYPES
from controller import Controller
from config import get_config_with_args
from simlog import (
    setup_logging,
    generate_sim_id,
    log_event,
    logger,
    LogEntry,
    EventType,
    PhaseType,
    LogLevel,
)
from llm import one_shot, load_prompt
from proposal_debug import generate_proposal_debug_files


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Round Table Consensus Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--sim-id",
        type=str,
        help="Custom simulation ID (default: auto-generated yymmddHH-N)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG, etc.)",
    )

    parser.add_argument(
        "--max-scenarios",
        type=int,
        default=None,
        help="Number of simulation scenarios to run (default: from config file)",
    )

    parser.add_argument(
        "--pool-seed",
        type=int,
        default=None,
        help="Seed for agent pool generation (default: from config file)",
    )

    parser.add_argument(
        "--run-seed",
        type=int,
        default=None,
        help="Seed for run configuration generation (default: from config file)",
    )

    parser.add_argument(
        "--num-agents",
        type=int,
        default=None,
        help="Number of agents to select for each scenario (default: from config file)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode: suppress verbose logging, show only summary",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Configuration file path (default: config.yaml)",
    )

    parser.add_argument(
        "--nollm",
        action="store_true",
        help="Disable LLM usage and force RNG-based decisions for faster testing",
    )

    parser.add_argument(
        "--model",
        type=str,
        help="Disable LLM usage and force RNG-based decisions for faster testing",
    )

    parser.add_argument(
        "--issue",
        type=str,
        help="Path to markdown file containing issue content to override issue generation",
    )

    return parser.parse_args()


def load_issue_from_file(file_path: str) -> str:
    """
    Load issue content from a markdown file.

    Args:
        file_path: Path to markdown file containing issue content

    Returns:
        Issue content from file
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            raise ValueError("Issue file is empty")
        logger.info(f"Loaded issue content from {file_path}")
        return content
    except Exception as exc:
        logger.error(f"Failed to load issue from {file_path}: {exc}")
        raise


def generate_issue_content(seed: int, model: str = "gemma3n:e4b") -> str:
    """
    Generate a realistic IT problem statement using LLM.

    Args:
        seed: Random seed for deterministic generation
        model: LLM model to use

    Returns:
        Generated problem statement
    """
    try:
        prompt = load_prompt("issue")
        return one_shot("", "", prompt, model=model, seed=seed)
    except Exception as exc:
        logger.warning(f"LLM issue generation failed: {exc}, falling back to default")
        return "A critical system issue requires team consensus to resolve."


def main():
    """Main simulation runner."""
    args = parse_arguments()

    # Load configuration with CLI argument precedence
    print(f"DEBUG: Loading config from: {args.config}")
    config = get_config_with_args(args.config, args)
    print(f"DEBUG: num_agents in loaded config: {config['simulation']['num_agents']}")
    print(
        f"DEBUG: stake_phase_ticks in loaded config: {config['consensus']['stake_phase_ticks']}"
    )

    # Generate or use provided simulation ID
    sim_id = args.sim_id if args.sim_id else generate_sim_id()

    # Initialize logging - adjust verbosity for quiet mode
    effective_verbosity = -1 if args.quiet else args.verbose  # -1 suppresses most logs
    sim_logger = setup_logging(sim_id, effective_verbosity)

    try:
        # Extract configuration values
        pool_seed = config["simulation"]["pool_seed"]
        run_seed = config["simulation"]["run_seed"]
        num_agents = config["simulation"]["num_agents"]
        max_scenarios = config["simulation"]["max_scenarios"]

        # Log simulation parameters
        logger.info("Starting Round Table Consensus Simulation")
        log_event(
            LogEntry(
                tick=0,
                phase=PhaseType.INIT,
                event_type=EventType.SIMULATION_START,
                payload={
                    "sim_id": sim_id,
                    "pool_seed": pool_seed,
                    "run_seed": run_seed,
                    "max_scenarios": max_scenarios,
                    "num_agents": num_agents,
                    "verbosity": args.verbose,
                    "config_file": args.config,
                },
                message="Simulation parameters configured",
            )
        )

        # Generate agent pool with configurable settings
        logger.info(f"Using pool seed: {pool_seed}, run seed: {run_seed}")

        random.seed(pool_seed)
        # Pool size from configuration
        pool_size = max(
            config["agent_pool"]["min_size"],
            num_agents * config["agent_pool"]["size_multiplier"],
        )

        # Use imported archetypes
        archetype_names = list(ARCHETYPES.keys())

        agents = {}
        for i in range(pool_size):
            # Cycle through archetypes to ensure balanced distribution
            archetype = archetype_names[i % len(archetype_names)]
            archetype_index = (
                i // len(archetype_names)
            ) + 1  # Count within each archetype

            agent_id = f"Agent_{archetype}_{archetype_index}"
            agents[agent_id] = AgentActor(
                agent_id=agent_id,
                initial_balance=random.randint(
                    config["agent_pool"]["balance_range"]["min"],
                    config["agent_pool"]["balance_range"]["max"],
                ),
                metadata={"base_archetype": archetype},  # Store the intended archetype
                seed=pool_seed + i,  # Ensure unique seed for each agent
            )
        agent_pool = AgentPool(agents=agents)
        pool_factor = round(pool_size / num_agents, 1)
        logger.info(
            f"Generated agent pool with {pool_size} agents ({pool_factor}x factor for {num_agents} selected, seed: {pool_seed})"
        )

        # Validate pool size is sufficient
        if pool_size < num_agents:
            raise ValueError(
                f"Agent pool size ({pool_size}) must be >= num_agents ({num_agents})"
            )

        # Note: initial_balances could be used for future balance tracking
        # initial_balances = {aid: agent.initial_balance for aid, agent in agents.items()}

        controller = Controller(agent_pool=agent_pool)

        # Track simulation round timings
        round_durations: List[float] = []

        for i in range(max_scenarios):
            scenario_seed = run_seed + i
            if not args.quiet:
                logger.info(
                    f"Running simulation {i + 1} of {max_scenarios} with seed {scenario_seed}"
                )
            else:
                # Show minimal progress in quiet mode
                print(
                    f"Running scenario {i + 1}/{max_scenarios}...", end=" ", flush=True
                )

            log_event(
                LogEntry(
                    tick=0,
                    phase=PhaseType.INIT,
                    event_type=EventType.SCENARIO_START,
                    payload={
                        "scenario": i + 1,
                        "total_scenarios": max_scenarios,
                        "scenario_seed": scenario_seed,
                    },
                    message=f"Starting scenario {i + 1}",
                )
            )

            # Override LLM model if specified
            if args.model:
                if "llm" not in config:
                    config["llm"] = {}
                config["llm"]["model"] = args.model

            global_config = GlobalConfig(
                assignment_award=config["consensus"]["assignment_award"],
                max_feedback_per_agent=config["consensus"]["max_feedback_per_agent"],
                feedback_stake=config["consensus"]["feedback_stake"],
                proposal_self_stake=config["consensus"]["proposal_self_stake"],
                revision_cycles=random.randint(
                    config["consensus"]["revision_cycles"]["min"],
                    config["consensus"]["revision_cycles"]["max"],
                ),
                conviction_params=config["consensus"]["conviction_params"],
                agent_pool=agent_pool,
                # Phase timeout configurations
                propose_phase_ticks=config["consensus"]["propose_phase_ticks"],
                feedback_phase_ticks=config["consensus"]["feedback_phase_ticks"],
                revise_phase_ticks=config["consensus"]["revise_phase_ticks"],
                stake_phase_ticks=random.randint(
                    config["consensus"]["stake_phase_ticks"]["min"],
                    config["consensus"]["stake_phase_ticks"]["max"],
                ),
                finalize_phase_ticks=config["consensus"]["finalize_phase_ticks"],
                llm_config={} if args.nollm else config.get("llm", {}),
            )

            primer = Primer(global_config)
            run_config = primer.generate_run_config(
                seed=run_seed, num_agents=num_agents, trait_config=config["traits"]
            )

            # Create a sample issue for the simulation
            # Use issue file if provided, otherwise use LLM generation or config
            if args.issue:
                problem_statement = load_issue_from_file(args.issue)
                if not args.quiet:
                    logger.info(f"Using issue from file: {args.issue}")
            elif config.get("llm", {}).get("issue", False) and not args.nollm:
                model = config.get("llm", {}).get("model", "gemma3n:e4b")
                problem_statement = generate_issue_content(scenario_seed, model)
                if not args.quiet:
                    logger.info(f"Generated LLM issue: {problem_statement[:50]}...")
            else:
                problem_statement = config["issue"]["problem_statement"]

            issue = Issue(
                issue_id=f"Issue_{scenario_seed}",
                problem_statement=problem_statement,
                background=config["issue"]["background"],
                metadata=config["issue"]["metadata"],
            )

            # Register the issue in Controller
            controller.register_issue(issue)
            logger.info(f"Registered issue: {issue.issue_id}")

            controller.configure_consensus(
                global_config=global_config, run_config=run_config
            )

            # Time the consensus round
            round_start = time.time()
            result = controller.run()
            round_end = time.time()
            round_duration = round_end - round_start
            round_durations.append(round_duration)

            if not args.quiet:
                logger.info("Phase execution:")
                for phase in result["phases_executed"]:
                    logger.info(f"  {phase}")
                logger.info("Summary:")
                logger.info(f"  {result['summary']}")
            else:
                print(f"✓ ({round_duration:.2f}s)")

            # Generate proposal debug files after scenario completion
            try:
                generate_proposal_debug_files(sim_id, issue.issue_id)
                if not args.quiet:
                    logger.info(f"Generated proposal debug files for scenario {i + 1}")
            except Exception as e:
                logger.warning(f"Failed to generate proposal debug files for scenario {i + 1}: {e}")

            log_event(
                LogEntry(
                    tick=0,
                    phase=PhaseType.INIT,
                    event_type=EventType.SCENARIO_COMPLETE,
                    payload={
                        "scenario": i + 1,
                        "issue_id": issue.issue_id,
                        "phases_executed": len(result["phases_executed"]),
                        "final_tick": (
                            result.get("final_state").tick
                            if result.get("final_state")
                            else 0
                        ),
                        "round_duration_ms": round(round_duration * 1000, 2),
                    },
                    message=f"Scenario {i + 1} completed in {round_duration:.3f}s",
                )
            )

        # Calculate timing statistics
        if round_durations:
            min_duration = min(round_durations)
            max_duration = max(round_durations)
            avg_duration = sum(round_durations) / len(round_durations)
            total_time = sum(round_durations)

            if not args.quiet:
                logger.info("=== Simulation Timing Statistics ===")
                logger.info(f"Total rounds: {len(round_durations)}")
                logger.info(f"Fastest round: {min_duration:.3f}s")
                logger.info(f"Slowest round: {max_duration:.3f}s")
                logger.info(f"Average duration: {avg_duration:.3f}s")

            log_event(
                LogEntry(
                    tick=0,
                    phase=PhaseType.INIT,
                    event_type=EventType.TIMING_STATS,
                    payload={
                        "sim_id": sim_id,
                        "total_rounds": len(round_durations),
                        "min_duration_ms": round(min_duration * 1000, 2),
                        "max_duration_ms": round(max_duration * 1000, 2),
                        "avg_duration_ms": round(avg_duration * 1000, 2),
                        "all_durations_ms": [
                            round(d * 1000, 2) for d in round_durations
                        ],
                    },
                    message="Timing statistics calculated",
                )
            )

        # Always show simulation summary (even in quiet mode)
        if args.quiet:
            print()  # New line after progress dots
        print("=== Simulation Summary ===")
        print(f"Simulation ID: {sim_id}")
        print(f"Agent Pool: {pool_size} agents")
        print(f"Scenarios Completed: {max_scenarios}")
        print(f"Agents per Scenario: {num_agents}")
        print(f"Seeds Used: Pool={pool_seed}, Run={run_seed}")
        if round_durations:
            print(f"Total Runtime: {total_time:.3f}s")
            print(
                f"Performance: {min_duration:.3f}s / {avg_duration:.3f}s / {max_duration:.3f}s (min/avg/max)"
            )

        if not args.quiet:
            logger.info("=== Simulation Summary ===")
            logger.info(f"Simulation ID: {sim_id}")
            logger.info(f"Agent Pool: {pool_size} agents")
            logger.info(f"Scenarios Completed: {max_scenarios}")
            logger.info(f"Agents per Scenario: {num_agents}")
            logger.info(f"Seeds Used: Pool={pool_seed}, Run={run_seed}")
            if round_durations:
                logger.info(f"Total Runtime: {total_time:.3f}s")
                logger.info(
                    f"Performance: {min_duration:.3f}s / {avg_duration:.3f}s / {max_duration:.3f}s (min/avg/max)"
                )

        log_event(
            LogEntry(
                tick=0,
                phase=PhaseType.INIT,
                event_type=EventType.SIMULATION_COMPLETE,
                payload={"sim_id": sim_id, "scenarios_completed": max_scenarios},
                message="Simulation completed successfully",
            )
        )

    except Exception as exc:
        log_event(
            LogEntry(
                tick=0,
                phase=PhaseType.INIT,
                event_type=EventType.SIMULATION_ERROR,
                payload={"sim_id": sim_id, "error": str(exc)},
                message=f"Simulation failed: {exc}",
                level=LogLevel.ERROR,
            )
        )
        raise
    finally:
        # Clean shutdown of logging
        sim_logger.close()


if __name__ == "__main__":
    main()
