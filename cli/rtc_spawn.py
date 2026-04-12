#!/usr/bin/env python3
"""rtc-spawn — Start agent runner processes and register them with the engine.

Usage:
    python3 -m cli.rtc_spawn --session <session_id> --profiles profiles.json
    python3 -m cli.rtc_spawn --session <session_id> --profiles profiles.json --agent claude-sonnet
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time

import httpx


def find_free_port(start: int = 8200, count: int = 100) -> int:
    """Find a free port starting from `start`."""
    import socket

    for port in range(start, start + count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{start + count}")


def _patch_runner_url(engine_url: str, session_id: str, agent_id: str, runner_url: str) -> None:
    """Tell the engine where to dispatch signals for this agent."""
    resp = httpx.patch(
        f"{engine_url}/v1/sessions/{session_id}/agents/{agent_id}",
        json={"runner_url": runner_url},
        timeout=5.0,
    )
    resp.raise_for_status()


def spawn_runners(
    engine_url: str,
    session_id: str,
    profiles_file: str,
    agent_name: str = None,
    base_port: int = 8200,
) -> tuple[list[dict], list[subprocess.Popen]]:
    """Spawn a runner process per agent and register each with the engine."""

    with open(profiles_file) as f:
        registrations = json.load(f)

    if not registrations:
        print("No registrations found in profiles file")
        return []

    # If the profiles file has agent registrations (from rtc_scenario), use those.
    # Otherwise treat as raw profiles and register first.
    if "token" not in registrations[0]:
        print("Profiles file has no tokens — register agents first with rtc-scenario --profiles")
        sys.exit(1)

    processes = []
    runners = []

    for i, reg in enumerate(registrations):
        agent_id = reg["agent_id"]
        token = reg["token"]

        port = find_free_port(base_port + i)
        runner_url = f"http://127.0.0.1:{port}"

        env = {
            **os.environ,
            "ENGINE_URL": engine_url,
            "AGENT_TOKEN": token,
        }
        if agent_name:
            env["AGENT_NAME"] = agent_name

        proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "runner.app:app",
                "--host", "127.0.0.1",
                "--port", str(port),
                "--log-level", "warning",
            ],
            env=env,
            cwd=str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )

        # Wait briefly for startup
        time.sleep(0.5)
        if proc.poll() is not None:
            print(f"  Runner for {agent_id} failed to start (exit {proc.returncode})")
            continue

        try:
            _patch_runner_url(engine_url, session_id, agent_id, runner_url)
        except httpx.HTTPError as e:
            print(f"  Warning: could not register runner_url for {agent_id}: {e}")

        agent_label = agent_name or "default"
        print(f"  Runner {agent_id} on {runner_url} (pid {proc.pid}, agent={agent_label})")

        processes.append(proc)
        runners.append({
            "agent_id": agent_id,
            "port": port,
            "pid": proc.pid,
            "runner_url": runner_url,
        })

    return runners, processes


def main():
    parser = argparse.ArgumentParser(description="Spawn RTC agent runners")
    parser.add_argument("--engine", default="http://localhost:8100", help="Engine URL")
    parser.add_argument("--session", required=True, help="Session ID")
    parser.add_argument("--profiles", "-p", required=True, help="Registrations JSON (output of rtc-scenario)")
    parser.add_argument("--agent", "-a", default=None, help="Agent name from agents.yaml (default: from yaml default_agent)")
    parser.add_argument("--base-port", type=int, default=8200, help="Starting port for runners")
    args = parser.parse_args()

    agent_label = args.agent or "default"
    print(f"Spawning runners for session {args.session} with agent={agent_label}")

    runners, processes = spawn_runners(
        engine_url=args.engine,
        session_id=args.session,
        profiles_file=args.profiles,
        agent_name=args.agent,
        base_port=args.base_port,
    )

    if not runners:
        print("No runners spawned")
        sys.exit(1)

    print(f"\n{len(runners)} runners active. Press Ctrl+C to stop all.")

    def shutdown(signum, frame):
        print("\nShutting down runners...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        print("All runners stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for all processes
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
