"""
Configuration loading module for Round Table Consensus Simulation.

Loads YAML configuration with command line argument precedence.
Future-proof design for config includes/linking.
"""

import yaml
import argparse
from typing import Dict, Any, Optional
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    # Future: add _resolve_includes(config, config_path) here
    return config


def merge_cli_args(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Override config values with command line arguments.

    CLI arguments take precedence over config file values.

    Args:
        config: Configuration dictionary from file
        args: Parsed command line arguments

    Returns:
        Updated configuration dictionary
    """
    # Override simulation parameters if provided via CLI
    if hasattr(args, "max_scenarios") and args.max_scenarios is not None:
        config["simulation"]["max_scenarios"] = args.max_scenarios

    if hasattr(args, "pool_seed") and args.pool_seed is not None:
        config["simulation"]["pool_seed"] = args.pool_seed

    if hasattr(args, "run_seed") and args.run_seed is not None:
        config["simulation"]["run_seed"] = args.run_seed

    if hasattr(args, "num_agents") and args.num_agents is not None:
        config["simulation"]["num_agents"] = args.num_agents

    return config


def get_config_with_args(
    config_path: Optional[str] = None, args: Optional[argparse.Namespace] = None
) -> Dict[str, Any]:
    """Load configuration and apply CLI argument overrides.

    Args:
        config_path: Path to config file (default: "config.yaml")
        args: CLI arguments to override config values

    Returns:
        Final configuration dictionary with CLI precedence applied
    """
    if config_path is None:
        config_path = "config.yaml"

    config = load_config(config_path)

    if args is not None:
        config = merge_cli_args(config, args)

    return config
