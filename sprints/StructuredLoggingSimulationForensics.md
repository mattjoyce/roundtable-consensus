Sprint Document: Logging Infrastructure & Forensic Output
🧭 Sprint Title

Feature: Structured Logging & Simulation Forensics
🎯 Objective

Implement a structured, extensible logging system to support:

    Full forensic capture of simulation events in a persistent SQLite format

    Configurable verbosity to support debugging, research, and production

    Human-readable terminal output using rich

    A simulation ID system to isolate and track run artifacts

    Strict separation of logging infrastructure from protocol logic

This will allow replay, inspection, and eventual visualization of simulation outcomes.
📂 Scope
✅ What’s In Scope

    New simlog.py module under /simulator/

    Loguru + Rich console logging

    SQLite event store (/simulator/db/{sim_id}.sqlite3)

    CLI integration using argparse

    Verbosity flag (-v through -vvvvv)

    Auto-generated simulation ID: format yymmddHH-N

    Refactor of print() → logger.*() across:

        thebureau.py

        roundtable.py

        creditmanager.py

    Bind events via .bind(event_dict=...) and capture via log sink

    Event schema includes: tick, phase, agent_id, event_type, message, payload

🚫 What’s Out of Scope

    Changes to protocol rules or simulation behavior

    Modifications to state progression, tick handling, or CP mechanics

    Proposal formatting, scoring, or winner logic

    ⚠️ All protocol logic must remain untouched.
    Logging is a pure observer, with no causal influence on simulation execution or state.

🛠 Deliverables
1. simlog.py Module

Encapsulates all logging setup:

    setup_logging(sim_id: str, verbosity: int) → SimulationLogger

    Uses loguru for event routing

    Adds rich handler for console, sqlite_sink for persistent logs

    Stores SQLite DBs at /simulator/db/{sim_id}.sqlite3

    Tables:

    CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        tick INTEGER,
        phase TEXT,
        agent_id TEXT,
        event_type TEXT,
        message TEXT,
        payload TEXT
    );

2. Simulation ID Generator

Added to simulator.py:

    Base ID from datetime: yymmddHH

    Uniqueness suffix: -1, -2, etc. (auto-increment by checking /simulator/db/)

    CLI override: --sim-id

3. Verbosity Control

Via CLI using argparse:

    -v, -vv, -vvv → maps to INFO, DEBUG, etc.

    Passed to setup_logging()

4. Logging Integration

All print() statements removed and replaced with:

from loguru import logger
logger.bind(event_dict={...}).debug("Action taken")

or simpler:

logger.info("Phase transition")

5. Close SimulationLogger

If a SQLite logger is active, ensure .close() is called at end of run.
🔍 Validation Criteria

    ✅ Simulation runs without error at all verbosity levels

    ✅ Console logs honor verbosity flags

    ✅ A SQLite .db file is created per simulation

    ✅ Events written with correct schema and values

    ✅ Protocol rules, ticks, credit flows, and winner selection remain unchanged

📁 Directory Structure

simulator/
├── db/                  # ← new: contains {sim_id}.sqlite3 logs
├── simlog.py            # ← new: logging module
├── simulator.py         # ← updated: adds argparse, sim_id, verbosity
├── roundtable.py        # ← updated: replaces print with logger
├── thebureau.py         # ← updated: replaces print with logger
├── creditmanager.py     # ← updated: structured burn/credit events