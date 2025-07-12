# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Guidelines

- Do not credit Claude in commits
- NEVER add claude attribution to git commits
- ALWAYS attribute commits to git user
- Do not add files to gitr with out explicit permission
- NEVER add CLAUDE.md
- NEVER add include claude as the author
- NEVER mention Claude Code in git actions
- Never include CLAUDEmd - ignore CLAUDE.MD

## Common Commands

### Running the Simulation
```bash
python3 simulator.py
```
The main simulation runner that executes multiple consensus scenarios with randomized parameters.

### Dependencies
This project uses standard Python libraries:
- `pydantic` for data models and validation
- `random` for seeded randomization
- `pprint` for formatted output

No package manager configuration files (requirements.txt, pyproject.toml) are present.

## Architecture Overview

This is a Round Table Consensus simulation system that implements democratic decision-making for AI/human teams with credit-based participation.

### Core Components

**Models (`models.py`)**: Defines the core data structures using Pydantic:
- `AgentActor`: Represents participants with initial balances and metadata
- `AgentPool`: Manages collections of agents with selection methods
- `GlobalConfig`: System-wide configuration (stakes, cycles, conviction parameters)
- `RunConfig`: Per-simulation configuration (selected agents, initial proposals)

**Credit Management (`creditmanager.py`)**: 
- Tracks agent credit balances and transaction history
- Handles credit burns, awards, and insufficient balance events
- Provides audit trail through event logging

**Consensus Engine (`roundtable.py`)**:
- Implements the multi-phase consensus process
- Phase types: PROPOSE → FEEDBACK → REVISE (cycles) → STAKE (rounds) → FINALIZE
- Tick-based execution with state management
- Phase generation based on GlobalConfig parameters

**The Bureau (`thebureau.py`)**:
- Orchestrates consensus runs and manages the CreditManager
- Awards initial credits to participating agents
- Serves as the entry point for starting consensus processes

**Primer (`primer.py`)**:
- Generates RunConfig from GlobalConfig
- Handles agent selection and initial proposal generation
- Uses seeded randomization for reproducible scenarios

**Simulation Runner (`simulator.py`)**:
- Main entry point that runs multiple consensus scenarios
- Generates agent pools and configurations with seeded randomization
- Executes scenarios and reports results

### Key Concepts

- **Credit Points (CP)**: Agents spend credits to participate in consensus phases
- **Conviction System**: Multi-round staking with conviction multipliers
- **Phase-based Execution**: Structured progression through proposal, feedback, revision, and staking phases
- **Reproducible Scenarios**: Seeded randomization for consistent simulation results

### Development Notes

The system is designed around immutable configurations (frozen Pydantic models) and event-driven credit management. All phases currently return immediately (placeholder implementations) but the framework supports tick-based execution with state transitions.