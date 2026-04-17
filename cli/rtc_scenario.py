#!/usr/bin/env python3
"""rtc-scenario — Create a consensus session via the API.

Usage:
    python3 -m cli.rtc_scenario --issue "Should we adopt microservices?" --agents 5
    python3 -m cli.rtc_scenario --issue "Budget allocation" --agents 3 --profiles profiles.json
"""

import argparse
import json

import httpx


def create_scenario(
    engine_url: str,
    issue_id: str,
    problem_statement: str,
    agent_count: int = 0,
    profiles_file: str = None,
    seed: int = 42,
    **config_overrides,
) -> dict:
    """Create a session and optionally register agents from a profiles file."""

    # Create session
    payload = {
        "issue_id": issue_id,
        "problem_statement": problem_statement,
        "agent_count": agent_count if not profiles_file else 0,
        "seed": seed,
    }
    payload.update(config_overrides)

    resp = httpx.post(f"{engine_url}/v1/sessions", json=payload, timeout=10.0)
    resp.raise_for_status()
    session = resp.json()
    session_id = session["session_id"]
    print(f"Created session {session_id} for issue '{issue_id}'")

    # Register agents from profiles file if provided
    if profiles_file:
        with open(profiles_file) as f:
            profiles = json.load(f)

        registrations = []
        for p in profiles[:agent_count or len(profiles)]:
            reg_payload = {
                "agent_id": p["agent_id"],
                "runner_url": "",  # No runner yet — use rtc-spawn for that
                "ocean_profile": p["profile"],
                "background": p.get("background", ""),
            }
            reg_resp = httpx.post(
                f"{engine_url}/v1/sessions/{session_id}/agents",
                json=reg_payload,
                timeout=10.0,
            )
            reg_resp.raise_for_status()
            reg = reg_resp.json()
            registrations.append(reg)
            print(f"  Registered {reg['agent_id']} (token: {reg['token'][:8]}...)")

        session["registrations"] = registrations

    return session


def main():
    parser = argparse.ArgumentParser(description="Create an RTC consensus scenario")
    parser.add_argument("--engine", default="http://localhost:8100", help="Engine URL")
    parser.add_argument("--issue", required=True, help="Issue ID / problem statement")
    parser.add_argument("--agents", "-n", type=int, default=5, help="Number of agents")
    parser.add_argument("--profiles", "-p", type=str, default=None, help="Profiles JSON file")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    result = create_scenario(
        engine_url=args.engine,
        issue_id=args.issue.replace(" ", "-").lower()[:32],
        problem_statement=args.issue,
        agent_count=args.agents,
        profiles_file=args.profiles,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
