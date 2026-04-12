#!/usr/bin/env python3
"""rtc-primer — Generate OCEAN profiles for N agents.

Reuses the simulator's primer.py archetype and mutation system.

Usage:
    python3 -m cli.rtc_primer --count 5 --seed 42
    python3 -m cli.rtc_primer --count 3 --output profiles.json
"""

import argparse
import json
import sys
from pathlib import Path

_sim_dir = str(Path(__file__).resolve().parent.parent / "simulator")
if _sim_dir not in sys.path:
    sys.path.insert(0, _sim_dir)

from primer import generate_base_profile, mutate_profile, ARCHETYPES


def generate_profiles(count: int, seed: int = 42) -> list[dict]:
    """Generate N OCEAN-derived protocol profiles."""
    import random
    rng = random.Random(seed)

    archetype_names = list(ARCHETYPES.keys())
    profiles = []

    for i in range(count):
        # Round-robin through archetypes, then random
        arch_name = archetype_names[i % len(archetype_names)]
        agent_seed = rng.randint(0, 2**31)
        base_profile, actual_archetype = generate_base_profile(agent_seed, archetype_name=arch_name)
        mutated = mutate_profile(base_profile, seed=rng.randint(0, 2**31), rounds=20)
        profiles.append({
            "agent_id": f"agent-{i:03d}",
            "base_archetype": actual_archetype,
            "profile": mutated,
        })

    return profiles


def main():
    parser = argparse.ArgumentParser(description="Generate OCEAN profiles for RTC agents")
    parser.add_argument("--count", "-n", type=int, default=5, help="Number of profiles")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Random seed")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON file")
    args = parser.parse_args()

    profiles = generate_profiles(args.count, args.seed)

    output = json.dumps(profiles, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote {len(profiles)} profiles to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
