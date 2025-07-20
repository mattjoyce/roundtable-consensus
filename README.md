# Round Table Consensus

> **Transparent, deterministic democratic decision‑making for mixed AI‑human teams**

> \[!NOTE] **Work‑in‑Progress:** The reference simulator does not yet implement every rule in the spec. Expect breaking changes until we reach **v1.2.0**.

---
[round-table-consensus](https://github.com/mattjoyce/roundtable-consensus/blob/master/spec/round-table-consensus-latest.md)
---


## Why Round Table Consensus?

When groups that include **both human and AI agents** have to make real decisions, we run into three chronic problems:

| Problem                          | Traditional fix                 | Why it fails                               |
| -------------------------------- | ------------------------------- | ------------------------------------------ |
| Preference strength is invisible | One‑person‑one‑vote             | Ignores how *much* someone cares           |
| Discussion quality is low        | Pure yes/no voting              | No space to refine ideas first             |
| Audit trails are brittle         | Ad‑hoc minutes / off‑chain chat | Hard to reconstruct who decided what, when |

Round Table Consensus (RTC) solves all three by combining a deliberative **Revise phase** with a market‑style **Conviction Point** (CP) allocation—while logging every event to an append‑only ledger.

---

## How It Works — 30‑Second Flow

1. **Propose** — Every agent submits one proposal (or backs the canonical `NoAction`); the protocol auto‑stakes `ProposalSelfStake` CP on their own draft.

2. **Feedback** — Agents review peers’ proposals and leave up to `MaxFeedbackPerAgent` comments (costing `FeedbackStake` CP) to sharpen ideas and flag issues.

3. **Revise** — Authors may update their own proposals, paying a revision cost proportional to the size of the change.

4. **Stake** — Each agent allocates their remaining Conviction Points across whichever proposals they support; conviction multipliers reward steadfast support over multiple staking rounds.

5. **Finalize** — The proposal with the highest conviction‑weighted score wins; all staked CP are burned (or frozen per RFC‑001), and the result is recorded.

6. **Ledger Commit** — Every action and credit flow is written to an append‑only log for full auditability.

```bash
# clone & set up
$ git clone https://github.com/<your-org>/roundtable-consensus.git
$ cd roundtable-consensus
$ python -m venv .venv && source .venv/bin/activate
$ pip install -r requirements.txt

# run three‑agent example
$ python simulator.py examples/three_agents.json
```

The simulator prints a step‑by‑step trace and closes with an ASCII ledger summary. 

---

## Repository Layout

```
/spec/       → Versioned Markdown spec documents
/rfcs/       → Draft, accepted, and rejected RFCs (see below)
/simulator/  → Reference Python implementation
/docs/       → Extended design notes and maths
```

---

## Contributing

We welcome both humans **and AI agents** as contributors. The workflow is intentionally lightweight:

1. **Open an Issue**
   Use the *Spec Question*, *Spec Enhancement*, or *Code Bug* templates. Labels `area:spec` vs `area:code` keep things separate.
2. **For spec‑level changes**
   Fork / branch → add a Markdown file under `/rfcs/draft/` following [.github/rfc-template.md](.github/rfc-template.md). Open a **Draft PR**; “lazy consensus” rules apply (72 h silence ⇒ move to *Last‑Call*).
3. **Merge & Tag**
   Accepted RFCs move to `/rfcs/accepted/` and bump the spec (e.g. v1.0.0 → v1.1.0). Implementation PRs can follow.

Full details live in [docs/RFC‑workflow.md](docs/RFC-workflow.md).

---

## Roadmap Highlights

* **RFC‑001 – Canonical NoAction merge rule** *(Last‑Call)*
* **HTML ledger explorer**
* **Agent plug‑in API** for alternative evaluation heuristics

Track progress on the [project board](https://github.com/<your-org>/roundtable-consensus/projects/1).

---

## Documentation

| Doc                      | What’s inside                             |
| ------------------------ | ----------------------------------------- |
| **Protocol Spec v1.0.0** | Formal rules (deterministic, test‑able)   |
| **System Overview**      | Architecture diagram, security notes      |
| **Math Appendix**        | Proof sketches for fairness & termination |

---

> *Built with the conviction that AI‑human collaboration should be accountable by design.*
