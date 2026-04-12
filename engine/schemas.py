"""Pydantic request/response schemas for the RTC Engine API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Request schemas ---


class SessionCreateRequest(BaseModel):
    """Create a new consensus session."""

    issue_id: str
    problem_statement: str
    background: str = ""
    agent_count: int = Field(default=5, ge=0, le=20)
    seed: int = Field(default=42)

    # Protocol parameters (all optional, sensible defaults from config.yaml)
    assignment_award: int = Field(default=100, ge=1)
    max_feedback_per_agent: int = Field(default=3, ge=1)
    feedback_stake: int = Field(default=5, ge=1)
    proposal_self_stake: int = Field(default=50, ge=1)
    revision_cycles: int = Field(default=2, ge=1, lt=5)
    propose_phase_ticks: int = Field(default=3, ge=1)
    feedback_phase_ticks: int = Field(default=3, ge=1)
    revise_phase_ticks: int = Field(default=3, ge=1)
    stake_phase_ticks: int = Field(default=5, ge=1)
    finalize_phase_ticks: int = Field(default=3, ge=1)
    conviction_params: Dict[str, float] = Field(
        default_factory=lambda: {"MaxMultiplier": 2.0, "TargetFraction": 0.98}
    )
    llm_config: Dict[str, Any] = Field(default_factory=dict)


# --- Response schemas ---


class AgentRegisterRequest(BaseModel):
    """Register an external agent with a runner endpoint."""

    agent_id: str
    runner_url: str  # HTTP base URL for the runner (e.g., http://localhost:8200)
    ocean_profile: Dict[str, float] = Field(
        default_factory=dict,
        description="OCEAN-derived protocol profile (initiative, compliance, etc.)",
    )


class AgentUpdateRequest(BaseModel):
    """Update mutable fields on a registered agent."""

    runner_url: Optional[str] = None


class AgentRegistration(BaseModel):
    """Response after successful agent registration."""

    agent_id: str
    session_id: str
    token: str  # Bearer token for authenticating actions
    balance: int
    ocean_profile: Dict[str, float]
    runner_url: str


class ActionRequest(BaseModel):
    """Action submitted by a runner back to the engine."""

    type: str = Field(
        description="Action type: propose, feedback, revise, stake, switch_stake, unstake, signal_ready, wait"
    )
    payload: Dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    """Result of action submission."""

    accepted: bool
    agent_id: str
    action_type: str
    message: str = ""
    balance: Optional[int] = None


class AgentSummary(BaseModel):
    agent_id: str
    balance: int
    ready: bool


class SessionStatus(BaseModel):
    session_id: str
    issue_id: str
    tick: int
    phase: Optional[str]
    phase_tick: int
    is_complete: bool
    agent_count: int
    proposal_count: int


class SessionDetail(SessionStatus):
    agents: List[AgentSummary]
    config: Dict[str, Any]


class PhaseStatus(BaseModel):
    session_id: str
    phase: Optional[str]
    phase_tick: int
    max_phase_ticks: int
    agents_ready: int
    agents_pending: int
    pending_agent_ids: List[str]


class TickResult(BaseModel):
    session_id: str
    tick: int
    phase: Optional[str]
    phase_tick: int
    is_complete: bool
    auto_advanced: bool = False


