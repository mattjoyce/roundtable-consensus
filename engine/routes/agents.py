"""Agent registration and action endpoints."""

import json
import os
import random
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

_DEBUG_DIR = os.environ.get("RTC_DEBUG_DIR", "")


def _log_action_debug(session_id: str, agent_id: str, req_type: str, payload: dict, tick: int, phase: str):
    """Append action submission to debug actions.jsonl if RTC_DEBUG_DIR set."""
    if not _DEBUG_DIR:
        return
    try:
        log_dir = Path(_DEBUG_DIR) / session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "actions.jsonl", "a") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "tick": tick,
                "phase": phase,
                "agent_id": agent_id,
                "type": req_type,
                "payload": payload,
            }) + "\n")
    except OSError:
        pass

_sim_dir = str(Path(__file__).resolve().parent.parent.parent / "simulator")
if _sim_dir not in sys.path:
    sys.path.insert(0, _sim_dir)

from models import ACTION_QUEUE, Action, Proposal

from ..remote_agent import RemoteAgentActor, generate_agent_token
from ..schemas import (
    ActionRequest,
    ActionResult,
    AgentRegisterRequest,
    AgentRegistration,
    AgentUpdateRequest,
)
from ..session_manager import SessionManager
from . import get_session_or_404

router = APIRouter(prefix="/v1/sessions/{session_id}/agents", tags=["agents"])

_manager: SessionManager = None

# Map API action types to internal Action types
_ACTION_TYPE_MAP = {
    "propose": "submit_proposal",
    "feedback": "feedback",
    "revise": "revise",
    "stake": "stake",
    "switch_stake": "switch_stake",
    "unstake": "unstake",
    "signal_ready": "signal_ready",
    "wait": "signal_ready",  # wait = no-op, signal ready
}

# Actions valid per phase
_PHASE_ACTIONS = {
    "PROPOSE": {"propose", "signal_ready", "wait"},
    "FEEDBACK": {"feedback", "signal_ready", "wait"},
    "REVISE": {"revise", "signal_ready", "wait"},
    "STAKE": {"stake", "switch_stake", "unstake", "signal_ready", "wait"},
    "FINALIZE": {"signal_ready", "wait"},
}


def init(manager: SessionManager):
    global _manager
    _manager = manager


@router.post("", response_model=AgentRegistration, status_code=201)
def register_agent(session_id: str, req: AgentRegisterRequest):
    """Register an external agent with OCEAN profile and runner endpoint."""
    session = get_session_or_404(session_id)

    if session.is_complete:
        raise HTTPException(status_code=409, detail="Session already complete")

    state = session.state
    config = session.config

    if req.agent_id in state.agent_balances:
        raise HTTPException(
            status_code=409,
            detail=f"Agent {req.agent_id} already registered in session {session_id}",
        )

    token = generate_agent_token()
    seed_val = random.randint(0, 2**31)
    agent = RemoteAgentActor(
        agent_id=req.agent_id,
        initial_balance=0,
        metadata={"protocol_profile": req.ocean_profile},
        seed=seed_val,
        rng=random.Random(seed_val),
        runner_url=req.runner_url,
        token=token,
        session_id=session_id,
    )

    # Register into session state
    state.agent_balances[req.agent_id] = 0
    state.agent_memory[req.agent_id] = {}
    state.agent_readiness[req.agent_id] = False
    state.agent_proposal_ids[req.agent_id] = None

    if state.current_issue:
        state.current_issue.agent_ids.append(req.agent_id)

    # Inject into config's selected_agents (dict is mutable despite frozen model)
    config.selected_agents[req.agent_id] = agent
    config.agent_ids.append(req.agent_id)

    # Award initial CP
    session.creditmgr.credit(
        agent_id=req.agent_id,
        amount=config.assignment_award,
        reason="Initial credit on registration",
        tick=state.tick,
        issue_id=config.issue_id,
    )

    session.register_agent_token(req.agent_id, token)

    return AgentRegistration(
        agent_id=req.agent_id,
        session_id=session_id,
        token=token,
        balance=state.agent_balances[req.agent_id],
        ocean_profile=req.ocean_profile,
        runner_url=req.runner_url,
    )


@router.patch("/{agent_id}", response_model=AgentRegistration)
def update_agent(session_id: str, agent_id: str, req: AgentUpdateRequest):
    """Update mutable fields on a registered agent (currently: runner_url)."""
    session = get_session_or_404(session_id)
    config = session.config
    state = session.state

    agent = config.selected_agents.get(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent {agent_id} not found in session {session_id}",
        )

    if req.runner_url is not None:
        agent.runner_url = req.runner_url

    return AgentRegistration(
        agent_id=agent_id,
        session_id=session_id,
        token=agent.token,
        balance=state.agent_balances.get(agent_id, 0),
        ocean_profile=(agent.metadata or {}).get("protocol_profile", {}),
        runner_url=agent.runner_url,
    )


@router.get("", response_model=list[dict])
def list_agents(session_id: str):
    """List all registered agents in a session."""
    return get_session_or_404(session_id).get_agent_summaries()


@router.post("/{agent_id}/action", response_model=ActionResult)
def submit_action(
    session_id: str,
    agent_id: str,
    req: ActionRequest,
    authorization: str = Header(default=""),
):
    """Accept an action from a runner and queue it for processing."""
    session = get_session_or_404(session_id)
    state = session.state
    ctrl = session.controller

    # Verify agent exists
    if agent_id not in state.agent_balances:
        raise HTTPException(
            status_code=404,
            detail=f"Agent {agent_id} not found in session {session_id}",
        )

    # Verify token
    token = authorization.removeprefix("Bearer ").strip()
    if token and not session.verify_agent_token(agent_id, token):
        raise HTTPException(status_code=403, detail="Invalid agent token")

    # Session must not be complete
    if session.is_complete:
        raise HTTPException(status_code=409, detail="Session already complete")

    # Validate action type
    if req.type not in _ACTION_TYPE_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action type: {req.type}. "
            f"Valid types: {', '.join(_ACTION_TYPE_MAP.keys())}",
        )

    # Validate phase allows this action (ISC-24)
    current_phase = state.current_phase
    if current_phase and current_phase in _PHASE_ACTIONS:
        if req.type not in _PHASE_ACTIONS[current_phase]:
            raise HTTPException(
                status_code=400,
                detail=f"Action '{req.type}' not valid in {current_phase} phase. "
                f"Valid actions: {', '.join(sorted(_PHASE_ACTIONS[current_phase]))}",
            )

    # Check CP for actions that cost CP (ISC-25)
    balance = state.agent_balances.get(agent_id, 0)
    if req.type == "propose" and balance < ctrl.config.proposal_self_stake:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient CP for proposal. "
            f"Need {ctrl.config.proposal_self_stake}, have {balance}",
        )
    if req.type == "feedback" and balance < ctrl.config.feedback_stake:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient CP for feedback. "
            f"Need {ctrl.config.feedback_stake}, have {balance}",
        )

    # Check protocol constraints (ISC-26)
    if req.type == "feedback":
        target_pid = req.payload.get("proposal_id")
        if target_pid is not None:
            agent_pid = state.agent_proposal_ids.get(agent_id)
            if target_pid == agent_pid:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot provide feedback on your own proposal",
                )

    # Build the internal Action and queue it
    internal_type = _ACTION_TYPE_MAP[req.type]
    payload = dict(req.payload)
    payload["issue_id"] = ctrl.config.issue_id
    payload.setdefault("tick", state.tick)

    # Translate external API field names to internal controller names.
    # The external API uses intuitive names (proposal_id, amount); the
    # simulator controller uses disambiguated names (target_proposal_id,
    # source_proposal_id, stake_amount).
    if req.type == "feedback":
        if "proposal_id" in payload and "target_proposal_id" not in payload:
            payload["target_proposal_id"] = payload.pop("proposal_id")
    elif req.type == "stake":
        if "amount" in payload and "stake_amount" not in payload:
            payload["stake_amount"] = payload.pop("amount")
    elif req.type == "revise":
        if "content" in payload and "new_content" not in payload:
            payload["new_content"] = payload.pop("content")
    elif req.type == "switch_stake":
        if "proposal_id" in payload and "target_proposal_id" not in payload:
            payload["target_proposal_id"] = payload.pop("proposal_id")
        if "from_proposal_id" in payload and "source_proposal_id" not in payload:
            payload["source_proposal_id"] = payload.pop("from_proposal_id")

    # For proposals, build the Proposal fields
    if req.type == "propose":
        payload.setdefault("content", payload.get("content", ""))
        payload.setdefault("agent_id", agent_id)
        payload.setdefault("author", agent_id)
        payload.setdefault("proposal_id", 0)  # Controller assigns real ID

    ACTION_QUEUE.submit(
        Action(type=internal_type, agent_id=agent_id, payload=payload)
    )

    _log_action_debug(
        session_id, agent_id, req.type, dict(req.payload),
        state.tick, state.current_phase or "",
    )

    return ActionResult(
        accepted=True,
        agent_id=agent_id,
        action_type=req.type,
        message=f"Action '{req.type}' queued for processing",
        balance=state.agent_balances.get(agent_id),
    )
