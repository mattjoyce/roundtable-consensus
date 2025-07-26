"""
Simulation Logging Infrastructure

Provides structured logging with forensic SQLite capture and rich console output.
Designed as a pure observer with zero impact on simulation protocol logic.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from loguru import logger
from rich.console import Console
from rich.logging import RichHandler


class EventType(str, Enum):
    """Event types for structured logging"""

    # Credit Management
    CREDIT_MANAGER_INIT = "credit_manager_init"
    CREDIT_BURN = "credit_burn"
    INSUFFICIENT_CREDIT = "insufficient_credit"
    CREDIT_AWARD = "credit_award"
    STAKE_RECORDED = "stake_recorded"
    STAKE_TRANSFERRED = "stake_transferred"
    CONVICTION_SWITCHED = "conviction_switched"
    CONVICTION_UPDATED = "conviction_updated"

    # Simulation Lifecycle
    SIMULATION_START = "simulation_start"
    SIMULATION_COMPLETE = "simulation_complete"
    SIMULATION_ERROR = "simulation_error"
    SCENARIO_START = "scenario_start"
    SCENARIO_COMPLETE = "scenario_complete"
    TIMING_STATS = "timing_stats"

    # Consensus Engine
    PHASE_EXECUTION = "phase_execution"
    PHASE_TRANSITION = "phase_transition"
    PHASE_BEGIN = "phase_begin"
    PHASE_FINISH = "phase_finish"
    CONSENSUS_TICK = "consensus_tick"
    PROPOSAL_STAKE_TRANSFERRED = "proposal_stake_transferred"

    # Finalization
    FINALIZATION_START = "finalization_start"
    FINALIZATION_WARNING = "finalization_warning"
    FINALIZATION_COMPLETE = "finalization_complete"
    FINALIZATION_DECISION = "finalization_decision"
    FINALIZATION_TRIGGER = "finalization_trigger"
    INFLUENCE_RECORDED = "influence_recorded"
    ISSUE_FINALIZED = "issue_finalized"

    # Proposals
    PROPOSAL_RECEIVED = "proposal_received"
    PROPOSAL_ACCEPTED = "proposal_accepted"
    PROPOSAL_REJECTED = "proposal_rejected"

    # Feedback
    FEEDBACK_REJECTED = "feedback_rejected"

    # Revisions
    REVISION_RECEIVED = "revision_received"
    REVISION_ACCEPTED = "revision_accepted"
    REVISION_REJECTED = "revision_rejected"
    REVISION_WARNING = "revision_warning"

    # Staking
    STAKE_RECEIVED = "stake_received"
    STAKE_REJECTED = "stake_rejected"

    # Switching
    SWITCH_RECEIVED = "switch_received"
    SWITCH_RECORDED = "switch_recorded"
    SWITCH_REJECTED = "switch_rejected"

    # Unstaking
    UNSTAKE_RECEIVED = "unstake_received"
    UNSTAKE_RECORDED = "unstake_recorded"
    UNSTAKE_REJECTED = "unstake_rejected"

    # Agent Actions
    AGENT_READY = "agent_ready"
    PHASE_TIMEOUT = "phase_timeout"

    # State Snapshots
    STATE_SNAPSHOT = "state_snapshot"


class PhaseType(str, Enum):
    """Phase types in consensus process"""

    INIT = "INIT"
    PROPOSE = "PROPOSE"
    FEEDBACK = "FEEDBACK"
    REVISE = "REVISE"
    STAKE = "STAKE"
    FINALIZE = "FINALIZE"


class LogLevel(str, Enum):
    """Log levels for structured logging"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogEntry(BaseModel):
    """Structured log entry with full type safety"""

    tick: Optional[int] = None
    phase: Optional[PhaseType] = None
    event_type: EventType
    agent_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    message: str
    level: LogLevel = LogLevel.INFO


class SQLiteSink:
    """Custom loguru sink for SQLite event storage."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(db_path))
        self._init_tables()

    def _init_tables(self):
        """Initialize the events table with the required schema."""
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                tick INTEGER,
                phase TEXT,
                agent_id TEXT,
                event_type TEXT,
                message TEXT,
                payload TEXT
            )
        """
        )

        # Create state snapshots table
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS state_snapshots (
                id INTEGER PRIMARY KEY,
                tick INTEGER NOT NULL,
                phase TEXT,
                phase_tick INTEGER,
                agent_balances TEXT,
                agent_readiness TEXT,
                agent_proposal_ids TEXT,
                proposals TEXT,
                stake_ledger TEXT,
                credit_events TEXT,
                execution_ledger TEXT,
                proposal_counter INTEGER,
                issue_finalized BOOLEAN,
                finalization_tick INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self.connection.commit()

    def write(self, message):
        """Write a log record to SQLite."""
        record = message.record

        # Extract event data from the bound context or record extra
        event_dict = record.get("extra", {}).get("event_dict", {})

        # Insert into SQLite
        self.connection.execute(
            """
            INSERT INTO events (tick, phase, agent_id, event_type, message, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                event_dict.get("tick"),
                event_dict.get("phase"),
                event_dict.get("agent_id"),
                event_dict.get("event_type"),
                record["message"],
                (
                    json.dumps(event_dict.get("payload"))
                    if event_dict.get("payload")
                    else None
                ),
            ),
        )
        self.connection.commit()

    def save_state_snapshot(self, state_data: dict):
        """Save a complete state snapshot to the database."""
        self.connection.execute(
            """
            INSERT INTO state_snapshots (
                tick, phase, phase_tick, agent_balances, agent_readiness,
                agent_proposal_ids, proposals, stake_ledger, credit_events,
                execution_ledger, proposal_counter, issue_finalized,
                finalization_tick
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                state_data["tick"],
                state_data["phase"],
                state_data["phase_tick"],
                state_data["agent_balances"],
                state_data["agent_readiness"],
                state_data["agent_proposal_ids"],
                state_data["proposals"],
                state_data["stake_ledger"],
                state_data["credit_events"],
                state_data["execution_ledger"],
                state_data["proposal_counter"],
                state_data["issue_finalized"],
                state_data["finalization_tick"],
            ),
        )
        self.connection.commit()

    def close(self):
        """Close the SQLite connection."""
        if self.connection:
            self.connection.close()


class SimulationLogger:
    """Main logging coordinator for simulations."""

    def __init__(self, sim_id: str, verbosity: int):
        self.sim_id = sim_id
        self.verbosity = verbosity
        self.db_path = Path(__file__).parent / "db" / f"{sim_id}.sqlite3"
        self.sqlite_sink: Optional[SQLiteSink] = None
        self.console = Console()

        self._setup_logging()

    def _add_forensic_symbol(self, record):
        """Add forensic symbol to record extra data."""
        # Check if this is a forensic event (has event_dict)
        is_forensic = "event_dict" in record["extra"]
        record["extra"]["symbol"] = "🔬" if is_forensic else "💬"
        return True

    def _setup_logging(self):
        """Configure loguru with rich console and SQLite sinks."""
        # Remove default logger
        logger.remove()

        # Add rich console handler with symbol formatting
        log_level = self._get_log_level()
        logger.add(
            RichHandler(console=self.console, rich_tracebacks=True),
            level=log_level,
            format="{time:HH:mm:ss} | {level: <8} | {extra[symbol]} {message}",
            filter=self._add_forensic_symbol,
        )

        # Add SQLite sink for forensic capture
        self.sqlite_sink = SQLiteSink(self.db_path)
        logger.add(
            self.sqlite_sink.write,
            level="DEBUG",  # Capture everything to SQLite
            format="{message}",
            filter=lambda record: "event_dict"
            in record["extra"],  # Only structured events
        )

        logger.info(f"Simulation logging initialized: {self.sim_id}")
        logger.info(f"Database: {self.db_path}")
        logger.info(f"Console verbosity: {log_level}")

    def _get_log_level(self) -> str:
        """Map verbosity level to loguru level."""
        level_map = {
            -1: "ERROR",  # Quiet mode - suppress most console output
            0: "WARNING",
            1: "INFO",
            2: "DEBUG",
            3: "TRACE",
            4: "TRACE",
            5: "TRACE",
        }
        return level_map.get(self.verbosity, "INFO")

    def close(self):
        """Clean shutdown of logging infrastructure."""
        if self.sqlite_sink:
            self.sqlite_sink.close()
        logger.info(f"Simulation logging closed: {self.sim_id}")


def setup_logging(sim_id: str, verbosity: int) -> SimulationLogger:
    """
    Initialize structured logging for a simulation run.

    Args:
        sim_id: Unique simulation identifier
        verbosity: Console verbosity level (0-5)

    Returns:
        SimulationLogger instance for cleanup
    """
    global _current_sim_logger
    _current_sim_logger = SimulationLogger(sim_id, verbosity)
    return _current_sim_logger


def generate_sim_id() -> str:
    """
    Generate a unique simulation ID in yymmddHH-N format.

    Returns:
        Unique simulation ID string
    """
    now = datetime.now()
    base_id = now.strftime("%y%m%d%H")

    # Check for existing databases to determine suffix
    db_dir = Path(__file__).parent / "db"
    if not db_dir.exists():
        return f"{base_id}-1"

    # Find the highest existing suffix for this base_id
    existing_files = list(db_dir.glob(f"{base_id}-*.sqlite3"))
    if not existing_files:
        return f"{base_id}-1"

    # Extract suffixes and find the next available number
    suffixes = []
    for file in existing_files:
        try:
            suffix = int(file.stem.split("-")[1])
            suffixes.append(suffix)
        except (IndexError, ValueError):
            continue

    next_suffix = max(suffixes) + 1 if suffixes else 1
    return f"{base_id}-{next_suffix}"


# Global reference to current simulation logger
_current_sim_logger: Optional[SimulationLogger] = None


def log_event(entry: LogEntry, forensic: bool = True):
    """
    Log a structured event with type safety and forensic capture.

    Args:
        entry: LogEntry with structured event data
        forensic: If True, captures to SQLite database (default: True)
    """
    import inspect

    # Get the caller's frame info to preserve original file/line
    frame = inspect.currentframe()
    try:
        caller_frame = frame.f_back
        caller_info = {
            "name": caller_frame.f_code.co_filename.split("/")[-1],  # Just filename
            "function": caller_frame.f_code.co_name,
            "line": caller_frame.f_lineno,
        }
    finally:
        del frame  # Prevent reference cycles

    if forensic:
        # Use existing logger.bind() format for backward compatibility
        # Use opt() to preserve caller information
        logger.opt(depth=1).bind(
            event_dict={
                "tick": entry.tick,
                "phase": entry.phase.value if entry.phase else None,
                "event_type": entry.event_type.value,
                "agent_id": entry.agent_id,
                "payload": entry.payload,
            }
        ).info(entry.message)
    else:
        # Console-only logging based on level with preserved caller info
        if entry.level == LogLevel.DEBUG:
            logger.opt(depth=1).debug(entry.message)
        elif entry.level == LogLevel.WARNING:
            logger.opt(depth=1).warning(entry.message)
        elif entry.level == LogLevel.ERROR:
            logger.opt(depth=1).error(entry.message)
        else:
            logger.opt(depth=1).info(entry.message)


def save_state_snapshot(state_data: dict):
    """Save a state snapshot using the current simulation logger."""
    global _current_sim_logger
    if _current_sim_logger and _current_sim_logger.sqlite_sink:
        _current_sim_logger.sqlite_sink.save_state_snapshot(state_data)
