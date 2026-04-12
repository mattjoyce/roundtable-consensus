"""RTC Agent Runner — receives signals from the engine, spawns agent CLIs.

The runner builds a mono context (state + API docs + curl examples) and
spawns an external agent CLI. The agent is responsible for submitting its
action back to the engine via curl. The runner does NOT relay or parse
the agent's response.

Usage:
    uvicorn runner.app:app --port 8200

Environment:
    ENGINE_URL: Base URL of the RTC engine (default: http://localhost:8100)
    AGENT_NAME: Name of agent config in agents.yaml (default: from agents.yaml default_agent)
    AGENT_TOKEN: Bearer token for authenticating with the engine
    RTC_DEBUG_DIR: If set, write mono-context + agent stdout under this dir.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request

from .agent_exec import spawn_agent
from .prompt_builder import build_mono_context, build_system_prompt

app = FastAPI(title="RTC Agent Runner", version="0.2.0")

ENGINE_URL = os.environ.get("ENGINE_URL", "http://localhost:8100")
AGENT_NAME = os.environ.get("AGENT_NAME", None)  # None = use default from agents.yaml
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")
DEBUG_DIR = os.environ.get("RTC_DEBUG_DIR", "")


@app.post("/signal")
async def receive_signal(request: Request):
    """Receive a signal from the engine, spawn an agent CLI to handle it.

    The agent CLI receives the full mono context (session state + API docs +
    curl examples + auth token) and is responsible for submitting its action
    back to the engine via curl. We return immediately after spawning.
    """
    signal = await request.json()

    agent_id = signal.get("agent_id", "unknown")
    token = request.headers.get("authorization", f"Bearer {AGENT_TOKEN}")
    # Extract bare token for inclusion in mono context curl examples
    auth_token = token.removeprefix("Bearer ").strip()

    # Build prompts
    system_prompt = build_system_prompt(signal)
    mono_context = build_mono_context(signal, ENGINE_URL, auth_token)

    debug_agent_dir = ""
    if DEBUG_DIR:
        session_id = signal.get("session_id", "unknown")
        tick = signal.get("tick", 0)
        phase = signal.get("type", "unknown")
        debug_agent_dir = str(
            Path(DEBUG_DIR) / session_id / f"tick{tick:03d}_{phase}" / agent_id
        )
        Path(debug_agent_dir).mkdir(parents=True, exist_ok=True)
        Path(debug_agent_dir, "system_prompt.md").write_text(system_prompt)
        Path(debug_agent_dir, "mono_context.md").write_text(mono_context)

    # Spawn agent CLI — fire and forget
    proc = spawn_agent(
        agent_name=AGENT_NAME,
        system_prompt=system_prompt,
        mono_context=mono_context,
        debug_dir=debug_agent_dir,
    )

    return {
        "ack": True,
        "agent_id": agent_id,
        "agent_config": AGENT_NAME or "default",
        "pid": proc.pid,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_NAME or "default",
        "engine_url": ENGINE_URL,
    }
