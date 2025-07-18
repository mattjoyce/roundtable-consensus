# consensus.py - Simulation runner and configuration generator
import random
import argparse
import time
from typing import List
from models import GlobalConfig, AgentActor, AgentPool, Issue, ActionQueue, Action, ACTION_QUEUE
from primer import Primer
from thebureau import TheBureau
from simlog import setup_logging, generate_sim_id
from config import get_config_with_args
from simlog import log_event, logger, LogEntry, EventType, PhaseType, LogLevel

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Round Table Consensus Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--sim-id", 
        type=str, 
        help="Custom simulation ID (default: auto-generated yymmddHH-N)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG, etc.)"
    )
    
    parser.add_argument(
        "--max-scenarios",
        type=int,
        default=2,
        help="Number of simulation scenarios to run (default: 2)"
    )
    
    parser.add_argument(
        "--pool-seed",
        type=int,
        default=1113,
        help="Seed for agent pool generation (default: 1113)"
    )
    
    parser.add_argument(
        "--run-seed",
        type=int,
        default=1719,
        help="Seed for run configuration generation (default: 1719)"
    )
    
    parser.add_argument(
        "--num-agents",
        type=int,
        default=5,
        help="Number of agents to select for each scenario (default: 5)"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode: suppress verbose logging, show only summary"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Configuration file path (default: config.yaml)"
    )
    
    return parser.parse_args()


def main():
    """Main simulation runner."""
    args = parse_arguments()
    
    # Load configuration with CLI argument precedence
    config = get_config_with_args(args.config, args)
    
    # Generate or use provided simulation ID
    sim_id = args.sim_id if args.sim_id else generate_sim_id()
    
    # Initialize logging - adjust verbosity for quiet mode
    effective_verbosity = -1 if args.quiet else args.verbose  # -1 suppresses most logs
    sim_logger = setup_logging(sim_id, effective_verbosity)
    
    try:
        # Extract configuration values
        pool_seed = config['simulation']['pool_seed']
        run_seed = config['simulation']['run_seed']
        num_agents = config['simulation']['num_agents']
        max_scenarios = config['simulation']['max_scenarios']
        
        # Log simulation parameters
        logger.info("Starting Round Table Consensus Simulation")
        log_event(LogEntry(
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
                "config_file": args.config
            },
            message="Simulation parameters configured"
        ))
        
        # Generate agent pool with configurable settings
        logger.info(f"Using pool seed: {pool_seed}, run seed: {run_seed}")

        random.seed(pool_seed)
        # Pool size from configuration
        pool_size = max(config['agent_pool']['min_size'], num_agents * config['agent_pool']['size_multiplier'])
        
        # Import archetypes from primer
        from primer import ARCHETYPES
        archetype_names = list(ARCHETYPES.keys())
        
        agents = {}
        for i in range(pool_size):
            # Cycle through archetypes to ensure balanced distribution
            archetype = archetype_names[i % len(archetype_names)]
            archetype_index = (i // len(archetype_names)) + 1  # Count within each archetype
            
            agent_id = f"Agent_{archetype}_{archetype_index}"
            agents[agent_id] = AgentActor(
                agent_id=agent_id,
                initial_balance=random.randint(
                    config['agent_pool']['balance_range']['min'],
                    config['agent_pool']['balance_range']['max']
                ),
                metadata={
                    "base_archetype": archetype  # Store the intended archetype
                },
                seed=pool_seed + i  # Ensure unique seed for each agent
            )
        agent_pool = AgentPool(agents=agents)
        pool_factor = round(pool_size / num_agents, 1)
        logger.info(f"Generated agent pool with {pool_size} agents ({pool_factor}x factor for {num_agents} selected, seed: {pool_seed})")
        
        # Validate pool size is sufficient
        if pool_size < num_agents:
            raise ValueError(f"Agent pool size ({pool_size}) must be >= num_agents ({num_agents})")
        
        # Extract the balanced balances from the agent pool
        initial_balances = {aid: agent.initial_balance for aid, agent in agents.items()}
        
        thebureau = TheBureau(agent_pool=agent_pool)
        
        # Track simulation round timings
        round_durations: List[float] = []
        
        for i in range(max_scenarios):
            scenario_seed = run_seed + i
            if not args.quiet:
                logger.info(f"Running simulation {i + 1} of {max_scenarios} with seed {scenario_seed}")
            else:
                # Show minimal progress in quiet mode
                print(f"Running scenario {i + 1}/{max_scenarios}...", end=" ", flush=True)
            
            log_event(LogEntry(
                tick=0,
                phase=PhaseType.INIT,
                event_type=EventType.SCENARIO_START,
                payload={
                    "scenario": i + 1,
                    "total_scenarios": max_scenarios,
                    "scenario_seed": scenario_seed
                },
                message=f"Starting scenario {i + 1}"
            ))
            
            gc = GlobalConfig(
                assignment_award=config['consensus']['assignment_award'],
                max_feedback_per_agent=config['consensus']['max_feedback_per_agent'],
                feedback_stake=config['consensus']['feedback_stake'],
                proposal_self_stake=config['consensus']['proposal_self_stake'],
                revision_cycles=random.randint(
                    config['consensus']['revision_cycles']['min'],
                    config['consensus']['revision_cycles']['max']
                ),
                staking_rounds=random.randint(
                    config['consensus']['staking_rounds']['min'],
                    config['consensus']['staking_rounds']['max']
                ),
                conviction_params=config['consensus']['conviction_params'],
                agent_pool=agent_pool
            )
            
            primer = Primer(gc)
            rc = primer.generate_run_config(
                seed=run_seed, 
                num_agents=num_agents,
                trait_config=config['traits']
            )
            
            # Create a sample issue for the simulation
            issue = Issue(
                issue_id=f"Issue_{scenario_seed}",
                problem_statement=config['issue']['problem_statement'],
                background=config['issue']['background'],
                metadata=config['issue']['metadata']
            )
            
            # Register the issue in TheBureau
            thebureau.register_issue(issue)
            logger.info(f"Registered issue: {issue.issue_id}")
            
            thebureau.configure_consensus(global_config=gc, run_config=rc)
            
            # Time the consensus round
            round_start = time.time()
            result = thebureau.run()
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
            
            log_event(LogEntry(
                tick=0,
                phase=PhaseType.INIT,
                event_type=EventType.SCENARIO_COMPLETE,
                payload={
                    "scenario": i + 1,
                    "issue_id": issue.issue_id,
                    "phases_executed": len(result["phases_executed"]),
                    "final_tick": result.get("final_state").tick if result.get("final_state") else 0,
                    "round_duration_ms": round(round_duration * 1000, 2)
                },
                message=f"Scenario {i + 1} completed in {round_duration:.3f}s"
            ))
        
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
            
            log_event(LogEntry(
                tick=0,
                phase=PhaseType.INIT,
                event_type=EventType.TIMING_STATS,
                payload={
                    "sim_id": sim_id,
                    "total_rounds": len(round_durations),
                    "min_duration_ms": round(min_duration * 1000, 2),
                    "max_duration_ms": round(max_duration * 1000, 2),
                    "avg_duration_ms": round(avg_duration * 1000, 2),
                    "all_durations_ms": [round(d * 1000, 2) for d in round_durations]
                },
                message="Timing statistics calculated"
            ))
        
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
            print(f"Performance: {min_duration:.3f}s / {avg_duration:.3f}s / {max_duration:.3f}s (min/avg/max)")
        
        if not args.quiet:
            logger.info("=== Simulation Summary ===")
            logger.info(f"Simulation ID: {sim_id}")
            logger.info(f"Agent Pool: {pool_size} agents")
            logger.info(f"Scenarios Completed: {max_scenarios}")
            logger.info(f"Agents per Scenario: {num_agents}")
            logger.info(f"Seeds Used: Pool={pool_seed}, Run={run_seed}")
            if round_durations:
                logger.info(f"Total Runtime: {total_time:.3f}s")
                logger.info(f"Performance: {min_duration:.3f}s / {avg_duration:.3f}s / {max_duration:.3f}s (min/avg/max)")
        
        log_event(LogEntry(
            tick=0,
            phase=PhaseType.INIT,
            event_type=EventType.SIMULATION_COMPLETE,
            payload={
                "sim_id": sim_id,
                "scenarios_completed": max_scenarios
            },
            message="Simulation completed successfully"
        ))
        
    except Exception as e:
        log_event(LogEntry(
            tick=0,
            phase=PhaseType.INIT,
            event_type=EventType.SIMULATION_ERROR,
            payload={
                "sim_id": sim_id,
                "error": str(e)
            },
            message=f"Simulation failed: {e}",
            level=LogLevel.ERROR
        ))
        raise
    finally:
        # Clean shutdown of logging
        sim_logger.close()


if __name__ == "__main__":
    main()
