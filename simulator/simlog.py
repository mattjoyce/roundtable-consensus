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

from loguru import logger
from rich.console import Console
from rich.logging import RichHandler


class SQLiteSink:
    """Custom loguru sink for SQLite event storage."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(db_path))
        self._init_tables()
    
    def _init_tables(self):
        """Initialize the events table with the required schema."""
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                tick INTEGER,
                phase TEXT,
                agent_id TEXT,
                event_type TEXT,
                message TEXT,
                payload TEXT
            )
        """)
        self.connection.commit()
    
    def write(self, message):
        """Write a log record to SQLite."""
        record = message.record
        
        # Extract event data from the bound context or record extra
        event_dict = record.get("extra", {}).get("event_dict", {})
        
        # Insert into SQLite
        self.connection.execute("""
            INSERT INTO events (tick, phase, agent_id, event_type, message, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            event_dict.get("tick"),
            event_dict.get("phase"),
            event_dict.get("agent_id"),
            event_dict.get("event_type"),
            record["message"],
            json.dumps(event_dict.get("payload")) if event_dict.get("payload") else None
        ))
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
            filter=self._add_forensic_symbol
        )
        
        # Add SQLite sink for forensic capture
        self.sqlite_sink = SQLiteSink(self.db_path)
        logger.add(
            self.sqlite_sink.write,
            level="DEBUG",  # Capture everything to SQLite
            format="{message}",
            filter=lambda record: "event_dict" in record["extra"]  # Only structured events
        )
        
        logger.info(f"Simulation logging initialized: {self.sim_id}")
        logger.info(f"Database: {self.db_path}")
        logger.info(f"Console verbosity: {log_level}")
    
    def _get_log_level(self) -> str:
        """Map verbosity level to loguru level."""
        level_map = {
            -1: "ERROR",   # Quiet mode - suppress most console output
            0: "WARNING",
            1: "INFO",
            2: "DEBUG", 
            3: "TRACE",
            4: "TRACE",
            5: "TRACE"
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
    return SimulationLogger(sim_id, verbosity)


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
            suffix = int(file.stem.split('-')[1])
            suffixes.append(suffix)
        except (IndexError, ValueError):
            continue
    
    next_suffix = max(suffixes) + 1 if suffixes else 1
    return f"{base_id}-{next_suffix}"