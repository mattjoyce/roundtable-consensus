"""Session manager — creates and manages per-session consensus instances.

Each session wraps the simulator's Controller, which manages the full lifecycle:
Consensus FSM + CreditManager + action queue processing.
"""

import random
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

# Add simulator to path so we can import its modules
_sim_dir = str(Path(__file__).resolve().parent.parent / "simulator")
if _sim_dir not in sys.path:
    sys.path.insert(0, _sim_dir)

from controller import Controller
from models import (
    AgentActor,
    AgentPool,
    GlobalConfig,
    Issue,
    RunConfig,
)

from .schemas import SessionCreateRequest


class Session:
    """A single consensus session wrapping a Controller."""

    def __init__(self, session_id: str, controller: Controller):
        self.session_id = session_id
        self.controller = controller
        self._agent_tokens: Dict[str, str] = {}  # agent_id → token

    @property
    def config(self):
        return self.controller.config

    @property
    def state(self):
        return self.controller.state

    @property
    def is_complete(self) -> bool:
        return self.controller.current_consensus._is_complete()

    @property
    def current_phase(self) -> Optional[str]:
        return self.state.current_phase

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def phase_tick(self) -> int:
        return self.state.phase_tick

    @property
    def max_phase_ticks(self) -> int:
        phase = self.controller.current_consensus.get_current_phase()
        return phase.max_phase_ticks if phase else 0

    @property
    def proposal_count(self) -> int:
        if self.state.current_issue:
            return len(self.state.current_issue.proposals)
        return 0

    def get_agent_summaries(self) -> list[dict]:
        # Use agent_balances keys — includes dynamically registered agents
        return [
            {
                "agent_id": aid,
                "balance": balance,
                "ready": self.state.agent_readiness.get(aid, False),
            }
            for aid, balance in self.state.agent_balances.items()
        ]

    def to_status(self):
        """Build a SessionStatus dict for API responses."""
        from .schemas import SessionStatus
        return SessionStatus(
            session_id=self.session_id,
            issue_id=self.config.issue_id,
            tick=self.tick,
            phase=self.current_phase,
            phase_tick=self.phase_tick,
            is_complete=self.is_complete,
            agent_count=len(self.state.agent_balances),
            proposal_count=self.proposal_count,
        )

    @property
    def creditmgr(self):
        return self.controller.creditmgr

    def register_agent_token(self, agent_id: str, token: str):
        self._agent_tokens[agent_id] = token

    def verify_agent_token(self, agent_id: str, token: str) -> bool:
        return self._agent_tokens.get(agent_id) == token

    def get_unready_agents(self) -> list[str]:
        return [
            aid
            for aid, ready in self.state.agent_readiness.items()
            if not ready
        ]

    def do_tick(self):
        """Advance by one tick using the Controller's full pipeline.

        The Controller.run() loop does: process_pending_actions → consensus.tick().
        We replicate one iteration of that loop here for single-tick control.
        """
        if self.is_complete:
            return

        consensus = self.controller.current_consensus

        # Intentional coupling: Controller._process_pending_actions() is private
        # but is the only way to drain ACTION_QUEUE without running the full loop.
        # If the simulator exposes a public step() method, switch to that.
        self.controller._process_pending_actions()

        # Update agent proposal mappings
        if self.state.current_issue:
            self.state.agent_proposal_ids = dict(
                self.state.current_issue.agent_to_proposal_id
            )

        # Tick the FSM
        consensus.tick()


class SessionManager:
    """Manages multiple concurrent consensus sessions in memory."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create_session(self, req: SessionCreateRequest) -> Session:
        """Create a new consensus session from request parameters."""
        session_id = str(uuid.uuid4())[:8]
        rng = random.Random(req.seed)

        # Build agent pool — generate agents with OCEAN-derived profiles
        agents = {}
        for i in range(req.agent_count * 2):  # Pool twice the needed size
            aid = f"agent-{i:03d}"
            seed_val = rng.randint(0, 2**31)
            profile = _generate_protocol_profile(rng)
            agents[aid] = AgentActor(
                agent_id=aid,
                initial_balance=0,
                metadata={"protocol_profile": profile},
                seed=seed_val,
                rng=random.Random(seed_val),
            )

        agent_pool = AgentPool(agents=agents)

        # Select agents for this session
        selected_ids = rng.sample(list(agents.keys()), req.agent_count)
        selected_agents = {aid: agents[aid] for aid in selected_ids}

        global_config = GlobalConfig(
            assignment_award=req.assignment_award,
            max_feedback_per_agent=req.max_feedback_per_agent,
            feedback_stake=req.feedback_stake,
            proposal_self_stake=req.proposal_self_stake,
            revision_cycles=req.revision_cycles,
            conviction_params=req.conviction_params,
            agent_pool=agent_pool,
            propose_phase_ticks=req.propose_phase_ticks,
            feedback_phase_ticks=req.feedback_phase_ticks,
            revise_phase_ticks=req.revise_phase_ticks,
            stake_phase_ticks=req.stake_phase_ticks,
            finalize_phase_ticks=req.finalize_phase_ticks,
            llm_config=req.llm_config,
        )

        run_config = RunConfig(
            seed=req.seed,
            issue_id=req.issue_id,
            agent_ids=selected_ids,
            selected_agents=selected_agents,
            initial_proposals={},
        )

        # Build issue
        issue = Issue(
            issue_id=req.issue_id,
            problem_statement=req.problem_statement,
            background=req.background,
            agent_ids=selected_ids,
        )

        # Use the simulator's Controller — it handles everything
        ctrl = Controller(agent_pool)
        ctrl.register_issue(issue)
        ctrl.configure_consensus(global_config, run_config)

        session = Session(session_id=session_id, controller=ctrl)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def session_count(self) -> int:
        return len(self._sessions)

    def tick_session(self, session_id: str) -> Optional[Session]:
        """Advance a session by one tick."""
        session = self._sessions.get(session_id)
        if session is not None:
            session.do_tick()
        return session


def _generate_protocol_profile(rng: random.Random) -> dict:
    """Generate a random OCEAN-derived protocol profile for an agent."""
    return {
        "initiative": round(rng.random(), 2),
        "compliance": round(rng.random(), 2),
        "risk_tolerance": round(rng.random(), 2),
        "persuasiveness": round(rng.random(), 2),
        "sociability": round(rng.random(), 2),
        "adaptability": round(rng.random(), 2),
        "self_interest": round(rng.random(), 2),
        "consistency": round(rng.random(), 2),
    }
