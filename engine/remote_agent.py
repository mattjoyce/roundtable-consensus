"""Remote agent actor — dispatches signals to external HTTP runners.

Overrides AgentActor.on_signal() to POST serializable payloads to a runner URL
instead of calling automoton.handle_signal() in-process.
"""

import secrets
from typing import Any, Dict, Optional

import httpx

import sys
from pathlib import Path

_sim_dir = str(Path(__file__).resolve().parent.parent / "simulator")
if _sim_dir not in sys.path:
    sys.path.insert(0, _sim_dir)

from models import ACTION_QUEUE, Action, AgentActor


SIGNAL_TIMEOUT = 30.0  # seconds before giving up on a runner


class RemoteAgentActor(AgentActor):
    """Agent that dispatches signals to an external HTTP runner."""

    runner_url: str = ""
    token: str = ""
    session_id: str = ""

    def on_signal(self, payload: Dict[str, Any]) -> Optional[dict]:
        """Serialize payload and POST to runner. Queue signal_ready on timeout."""
        if not self.runner_url:
            # No runner registered — auto-ready (graceful degradation)
            ACTION_QUEUE.submit(
                Action(
                    type="signal_ready",
                    agent_id=self.agent_id,
                    payload={"issue_id": payload.get("config", {}).issue_id
                             if hasattr(payload.get("config", {}), "issue_id")
                             else "unknown"},
                )
            )
            return {"ack": True, "fallback": "no_runner"}

        signal = serialize_signal(self.agent_id, payload)
        signal["session_id"] = self.session_id

        try:
            resp = httpx.post(
                f"{self.runner_url}/signal",
                json=signal,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=SIGNAL_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError):
            # Runner down or slow — default to signal_ready (ISC-21)
            ACTION_QUEUE.submit(
                Action(
                    type="signal_ready",
                    agent_id=self.agent_id,
                    payload={"issue_id": signal.get("issue_id", "unknown")},
                )
            )
            return {"ack": True, "fallback": "timeout"}


def generate_agent_token() -> str:
    """Generate a URL-safe token for agent authentication."""
    return secrets.token_urlsafe(24)


def serialize_signal(agent_id: str, payload: Dict[str, Any]) -> dict:
    """Extract serializable context from the raw FSM signal payload.

    The simulator passes live Python objects (state, config, phase).
    We extract what runners actually need into a flat JSON dict.
    """
    phase_type = payload.get("type", "unknown")
    state = payload.get("state")
    config = payload.get("config")

    # Base signal — always present
    signal = {
        "type": phase_type,
        "agent_id": agent_id,
        "tick": state.tick if state else 0,
        "phase_tick": state.phase_tick if state else 0,
        "issue_id": config.issue_id if config else "unknown",
    }

    # Agent-specific context
    if state:
        signal["agent_balance"] = state.agent_balances.get(agent_id, 0)
        signal["agent_proposal_id"] = state.agent_proposal_ids.get(agent_id)
        signal["agent_ready"] = state.agent_readiness.get(agent_id, False)
        signal["agent_memory"] = state.agent_memory.get(agent_id, {})

    # OCEAN profile from agent metadata in selected_agents
    if config and agent_id in config.selected_agents:
        agent_meta = config.selected_agents[agent_id].metadata or {}
        signal["ocean_profile"] = agent_meta.get("protocol_profile", {})
        signal["background"] = agent_meta.get("background", "")

    # Protocol config
    if config:
        signal["protocol"] = {
            "assignment_award": config.assignment_award,
            "feedback_stake": config.feedback_stake,
            "proposal_self_stake": config.proposal_self_stake,
            "max_feedback_per_agent": config.max_feedback_per_agent,
            "conviction_params": config.conviction_params,
        }

    # Proposals — present in feedback/revise/stake phases
    if state and state.current_issue:
        proposals = []
        for p in state.current_issue.proposals:
            if p.active:
                proposals.append({
                    "proposal_id": p.proposal_id,
                    "content": p.content,
                    "author": p.author,
                    "type": p.type,
                    "revision_number": p.revision_number,
                })
        signal["proposals"] = proposals

    # Phase-specific context
    if phase_type == "Feedback":
        signal["proposal_contents"] = payload.get("proposal_contents", {})

    elif phase_type == "Revise":
        signal["feedback_received"] = payload.get("feedback_received", [])
        # Include feedback log for this agent's proposal
        if state and state.current_issue:
            agent_pid = state.agent_proposal_ids.get(agent_id)
            if agent_pid is not None:
                signal["feedback_for_proposal"] = [
                    fb for fb in state.current_issue.feedback_log
                    if fb.get("to") == agent_pid
                ]

    elif phase_type == "Stake":
        signal["agent_proposals"] = payload.get("agent_proposals", [])
        # Stake visibility — only show own stakes (blind staking, ISC-20)
        if state:
            own_stakes = state.get_active_stakes_by_agent(agent_id)
            signal["own_stakes"] = [
                {
                    "stake_id": s.stake_id,
                    "proposal_id": s.proposal_id,
                    "cp": s.cp,
                    "initial_tick": s.initial_tick,
                }
                for s in own_stakes
            ]

    return signal
