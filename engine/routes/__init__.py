"""Route modules for the RTC Engine API."""

from fastapi import HTTPException

from ..session_manager import SessionManager

_manager: SessionManager = None


def init_manager(manager: SessionManager):
    global _manager
    _manager = manager


def get_session_or_404(session_id: str):
    s = _manager.get_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return s
