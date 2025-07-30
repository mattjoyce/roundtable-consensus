# Round Table Consensus

**Structured Deliberation for Autonomous Agents and Humans**

Round Table Consensus (RTC) is an experimental protocol for achieving consensus through structured, transparent deliberation. It is designed for both autonomous agents and human participants, simulating fair and accountable decision-making under constrained resources and imperfect agreement.

This repository contains the **reference implementation** of version **v1.2.0** — now recognized as the **canonical release**.

---

## 🔍 What Is It?

Round Table Consensus is **not a voting system**. It is a **protocol for collaborative preference aggregation**, implemented as a staged simulation with agents, proposals, feedback, revision, and conviction-based staking.

Each participant operates within a fixed Credit Point (CP) budget. Their decisions — to propose, revise, or stake — are resource-constrained and visible, revealing the intensity of their preferences.

Key properties:
- **Phase-based structure**: Clear demarcation of decision-making stages
- **Conviction staking**: Stake value grows over time to reward early commitment
- **Atomic stake records**: Every stake is tracked as a discrete ledger entry
- **Structured feedback and revision**: Encourages refinement, not just opposition
- **No economic value**: CPs are not tradable tokens; they are spent to express care

---

## 🧠 Protocol Design Philosophy

Consensus should emerge from *careful deliberation*, not competition. Round Table Consensus encodes several core beliefs:

- **Burn reveals preference**: Agents must burn CP to express what they care about
- **Time matters**: Early commitments are worth more via conviction accrual
- **Revision is constrained**: Agents can revise but must manage cost and timing
- **Noaction is valid**: An explicit "do nothing" proposal anchors the system
- **Simplicity over economics**: No stake farming, yield, or currency games

---

## 🔄 Protocol Phases

Each run of the protocol progresses through five distinct phases:

### 1. **Propose**  
Agents can:
- Submit a proposal (must self-stake)
- Signal readiness without proposing

### 2. **Feedback**  
Agents can:
- Provide feedback on up to N proposals
- Each feedback costs CP

### 3. **Revise**  
Agents can:
- Revise their own proposal (if feedback exists)
- Signal readiness

### 4. **Stake**  
Agents can:
- Stake CP on any active proposal (not their own)
- Switch existing voluntary stake to a different proposal
- Unstake voluntary stake

Conviction is calculated **per stake**, using an age-based multiplier.

### 5. **Finalize**  
The proposal with the highest **total conviction** becomes the decision. All others are archived.

---

## 🔢 Conviction Mechanics

- Every stake includes: agent, proposal, tick, and CP
- Conviction multiplier: increases per tick since staking
- Mandatory (self) stake is non-reversible
- Switching stake resets conviction
- Noaction can be staked like any other proposal

Conviction = CP × f(age)

---

## 🧪 Simulation Features

- Python-based simulation using deterministic seeds
- Supports local Ollama LLM agents and handcrafted agent types
- Trait-based agent personalities influence behavior
- Rich event logging and snapshotting for forensic replay

---

## 📁 Repo Structure

- `simulator.py` – entry point for scenario runs
- `models.py` – core data types: agents, proposals, stakes, issues
- `roundtable.py` – protocol FSM
- `primer.py` – agent selection and trait mutation
- `controller.py` – top-level orchestration
- `context_builder.py` – structured prompt assembly for LLMs
- `llm.py` – local model execution
- `simlog.py` – structured logging system

---

## 🛣️ Roadmap

Current version: **v1.2.0** — canonical, complete

Planned explorations (post-1.2):
- Sub-protocols for dispute or synthesis
- Stackable consensus (meta-groups)
- Reputation tracking
- Blinding mechanisms for partial information
- Multi-issue federated deliberation

---

## 📚 Documentation

- [Protocol Specification (v1.2.0)](./spec/round-table-consensus-v1.2.0.md)
- [RFC Index](./rfc/README.md)
- [Staking & Conviction Notes](./docs/staking-and-conviction-notes.md)

---

## 🤝 Acknowledgements

This protocol is the product of many conversations, critiques, and refinements. Special thanks to agents Gemini and Claude for rigorous adversarial review.

If you’re reading this: welcome to the table. You are now part of the experiment.

