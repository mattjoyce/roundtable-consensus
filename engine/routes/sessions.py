"""Session CRUD, tick, and query endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    PhaseStatus,
    SessionCreateRequest,
    SessionDetail,
    SessionStatus,
    TickResult,
)
from ..session_manager import SessionManager
from . import get_session_or_404

_CONFIG_FIELDS = {
    "assignment_award",
    "max_feedback_per_agent",
    "feedback_stake",
    "proposal_self_stake",
    "revision_cycles",
    "conviction_params",
    "propose_phase_ticks",
    "feedback_phase_ticks",
    "revise_phase_ticks",
    "stake_phase_ticks",
    "finalize_phase_ticks",
}

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

# Singleton session manager — injected from app.py
_manager: SessionManager = None


def init(manager: SessionManager):
    global _manager
    _manager = manager


@router.post("", response_model=SessionStatus, status_code=201)
def create_session(req: SessionCreateRequest):
    """Create a new consensus session with issue and config."""
    return _manager.create_session(req).to_status()


@router.get("", response_model=list[SessionStatus])
def list_sessions():
    """List all sessions."""
    return [s.to_status() for s in _manager.list_sessions()]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str):
    """Get detailed session status including agents."""
    s = get_session_or_404(session_id)

    status = s.to_status()
    return SessionDetail(
        **status.model_dump(),
        agents=s.get_agent_summaries(),
        config=s.config.model_dump(include=_CONFIG_FIELDS),
    )


@router.get("/{session_id}/phase", response_model=PhaseStatus)
def get_phase(session_id: str):
    """Get current phase details — who's ready, who's pending."""
    s = get_session_or_404(session_id)

    unready = s.get_unready_agents()

    return PhaseStatus(
        session_id=s.session_id,
        phase=s.current_phase,
        phase_tick=s.phase_tick,
        max_phase_ticks=s.max_phase_ticks,
        agents_ready=len(s.state.agent_balances) - len(unready),
        agents_pending=len(unready),
        pending_agent_ids=unready,
    )


@router.post("/{session_id}/tick", response_model=TickResult)
def tick_session(session_id: str):
    """Advance the session by one tick."""
    s = get_session_or_404(session_id)
    if s.is_complete:
        raise HTTPException(status_code=409, detail="Session already complete")

    prev_phase = s.current_phase
    _manager.tick_session(session_id)

    return TickResult(
        session_id=s.session_id,
        tick=s.tick,
        phase=s.current_phase,
        phase_tick=s.phase_tick,
        is_complete=s.is_complete,
        auto_advanced=(s.current_phase != prev_phase),
    )


# --- Query Endpoints (Phase 5) ---


@router.get("/{session_id}/proposals")
def get_proposals(session_id: str):
    """Return all proposals with revision history."""
    s = get_session_or_404(session_id)
    if not s.state.current_issue:
        return []
    return [
        {
            "proposal_id": p.proposal_id,
            "content": p.content,
            "author": p.author,
            "author_type": p.author_type,
            "type": p.type,
            "active": p.active,
            "revision_number": p.revision_number,
            "parent_id": p.parent_id,
            "tick": p.tick,
            "metadata": p.metadata,
        }
        for p in s.state.current_issue.proposals
    ]


@router.get("/{session_id}/proposals/{proposal_id}/feedback")
def get_proposal_feedback(session_id: str, proposal_id: int):
    """Return all feedback for a specific proposal."""
    s = get_session_or_404(session_id)
    if not s.state.current_issue:
        return []
    return [
        fb for fb in s.state.current_issue.feedback_log
        if fb.get("to") == proposal_id
    ]


@router.get("/{session_id}/stakes")
def get_stakes(
    session_id: str,
    agent_id: Optional[str] = Query(default=None, description="Filter by agent (blind staking: only own stakes)"),
):
    """Return stake state. If agent_id provided, only that agent's stakes (blind staking)."""
    s = get_session_or_404(session_id)
    stakes = s.state.stake_ledger

    if agent_id:
        # Blind staking: only return requesting agent's stakes
        stakes = [st for st in stakes if st.agent_id == agent_id]

    return [
        {
            "stake_id": st.stake_id,
            "agent_id": st.agent_id,
            "proposal_id": st.proposal_id,
            "cp": st.cp,
            "initial_tick": st.initial_tick,
            "status": st.status,
            "mandatory": st.mandatory,
        }
        for st in stakes
    ]


@router.get("/{session_id}/ledger")
def get_ledger(session_id: str):
    """Return CP transaction history."""
    s = get_session_or_404(session_id)
    return s.state.credit_events


@router.get("/{session_id}/events")
def get_events(
    session_id: str,
    agent_id: Optional[str] = Query(default=None),
    phase: Optional[str] = Query(default=None),
    tick: Optional[int] = Query(default=None),
):
    """Return the execution ledger, filterable by agent, phase, tick."""
    s = get_session_or_404(session_id)
    events = s.state.execution_ledger

    if agent_id is not None:
        events = [e for e in events if e.get("agent_id") == agent_id]
    if tick is not None:
        events = [e for e in events if e.get("tick") == tick]
    if phase is not None:
        events = [e for e in events if e.get("phase") == phase]

    return events
