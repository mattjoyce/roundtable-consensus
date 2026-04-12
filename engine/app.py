"""RTC Engine — FastAPI application entry point."""

from fastapi import FastAPI

from .routes import agents, sessions, init_manager
from .session_manager import SessionManager

app = FastAPI(
    title="RTC Engine",
    description="Round Table Consensus Engine — REST API wrapping the consensus FSM",
    version="0.1.0",
)

# Initialize session manager and wire into routes
manager = SessionManager()
init_manager(manager)
sessions.init(manager)
agents.init(manager)

app.include_router(sessions.router)
app.include_router(agents.router)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "sessions_active": manager.session_count(),
    }
