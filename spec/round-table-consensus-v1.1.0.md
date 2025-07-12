---

title: Round Table Consensus Protocol
version: 1.1.0
status: Draft
date: 2025-07-12
authors:

* Matt Joyce
  acknowledgments:
* name: GPT-4o (OpenAI, 2024)
  role: Assisted with logical formalization, predicate structuring, and clear formatting of protocol rules.
* name: OpenAI o3 (2025)
  role: Provided background research and surfaced design insights for staking phase mechanics.

---

<!-- NOTE: This is a patched spec draft reflecting RFC-001, RFC-002, and RFC-003 -->

# Round Table Consensus Protocol

... <!-- (omitted unchanged sections for brevity) -->

## 6. Proposal Submission & Self‑Stake

* **6.1 Each agent must submit exactly one proposal for an issue.** Agents who do not craft a unique proposal must select the canonical `No Action` proposal.

* **6.2 Upon proposal submission (including `No Action`), the system automatically places a self‑stake of `ProposalSelfStake` Conviction Points (default = 50) from the submitting agent onto that proposal.**

### 🔒 Stake Accounting Rules (RFC‑002)

* Self‑stake is **deducted immediately** from the agent’s CP balance.
* The CP is **held by the proposal**, not the agent.
* On revision, the stake is **transferred** to the new version.
* Stake is **non‑refundable** and **burned** at finalization.
* An agent can only have one active proposal per issue.

---

## 9. Phase Progression & Kick‑Out Timer

... <!-- (unchanged intro text) -->

* **9.3 Kick‑Out Substitution** – If the timer fires, the inactive agent’s move is replaced with the protocol’s canonical default (e.g., `No Action` for proposals or `Abstain` for votes). The agent is optionally debited `KickOutPenalty` Conviction Points.

> 📎 *When `NoAction` is substituted for a non‑responsive agent, the system still deducts `ProposalSelfStake` CP from the agent's balance (RFC‑003). This ensures economic parity with active proposal submission. If the agent lacks sufficient CP, an `InsufficientCredit` event is logged.*

... <!-- (unchanged remaining sections) -->

## 14. Revise Phase & Costs

... <!-- (existing intro retained) -->

### 🆕 Versioned Proposal Revisions (RFC‑001)

* Each revision creates a **new versioned proposal** (e.g., `PAgent_3@v2`) linked to its parent via `parent_id`.
* The `revision_number` is incremented and tracked.
* The protocol considers **only the latest version** active for staking, feedback, and scoring.
* Existing stake is **transferred** to the new version (no restake required).
* Previous versions are **archived and immutable**.
* Revision lineage is included in the ledger with `delta`, `parent_id`, `tick`, and `revision_cost`.

Optional: A system‑wide or per‑issue cap may limit the number of revisions (e.g., max 5).

---

## 18. Finalization & Post-Vote Cleanup

... <!-- unchanged intro -->

* **18.2 Stake Burn** – All Conviction Points **staked on proposals**—regardless of whether they were winning or losing—are burned at the conclusion of the Issue. This includes CPs transferred through proposal versioning (RFC‑001) and stakes on auto-submitted `NoAction` proposals (RFC‑003).

...
