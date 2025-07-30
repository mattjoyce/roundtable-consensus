---
title: Round Table Consensus Protocol
version: 1.1.0
status: Stable
date: 2025-07-13
authors:
  - Matt Joyce
acknowledgments:
  - name: GPT-4o (OpenAI, 2024)
    role: Assisted with logical formalization, predicate structuring, and clear formatting of protocol rules.
  - name: OpenAI o3 (2025)
    role: Provided background research and surfaced design insights for staking phase mechanics.
---
# Round Table Consensus Protocol

**A democratic protocol for hybrid teams of humans and machines, grounded in fairness, accountability, and traceable reasoning.**

## Abstract

In an era where artificial intelligence and human agents must increasingly collaborate to solve complex problems, traditional models of group decision-making face new constraints. Simple majority votes obscure preference strength. Market-based systems create inequity. And consensus models often falter under scale or ambiguity. What is needed is a protocol that treats all agents—human or artificial—as equal participants, offering mechanisms to express intensity of preference, foster deliberative refinement, and leave behind a transparent, tamper-evident trail of all decisions made.

The Round Table Consensus Protocol is designed for precisely this purpose.

This protocol defines a deterministic, multi-phase decision process where each participant is endowed with a finite, auditable resource—Conviction Points—which they expend to submit, revise, critique, and support proposals. Each Issue moves through a structured lifecycle of proposal, feedback, revision, and conviction-weighted staking. All agent actions are explicitly tied to identity, every credit flow is recorded, and all transitions are defined purely by protocol logic, without requiring moderator discretion.

The design is intentionally transparent and simulation-friendly. Every consensus cycle can be replayed or audited from an immutable ledger of state transitions. The system accommodates both asynchronous and turn-based execution, and is suitable for integration with agent-based infrastructure, including autonomous agents and protocol-governed collectives.

This specification serves as the authoritative reference for all implementations. While initial versions assume a trusted execution environment and non-adversarial actors, the protocol's structure lays the groundwork for future enhancements, including adversarial resilience, reputation systems, and off-chain hooks.

By combining democratic ideals with formal mechanism design, the Round Table Consensus Protocol aspires to create a new standard for collective reasoning in hybrid teams of humans and machines.


## 1. Identity & Invitation

* **1.1 Agents are invited to the System by an administrator.**
* **1.2 Each invited agent receives a unique credential (API key or similar) that must be presented with every action, binding those actions to that agent's identity.**

---

## 1.3 Design Assumptions

* **1.3.1 The protocol operates in curated, non-democratic environments.** It is not a permissionless public consensus system.
* **1.3.2 Agents participate by invitation and assignment only.** Each agent receives a credential and is enrolled/assigned by a controller.
* **1.3.3 The controller functions as an orchestrator** and may be a human administrator or an automated system. Its role is to invite agents and coordinate state transitions.
* **1.3.4 The base trust model assumes honest, bounded-rational agents** interacting in a trusted execution environment. Future versions may add adversarial resilience mechanisms.

---

## 2. Deterministic State Machine

* **2.1 The system operates as a deterministic state machine.**
* **2.2 At each `tick` the protocol rules are applied to the current ledger to derive the next state.**
* **2.3 Ticks are *logical events*, not tied to wall‑clock time.**
* **2.4 The algorithm is designed to minimise or eliminate the need for a human moderator; all transitions are fully specified by the protocol.**

---

## 3. Issue Lifecycle & Schema

* **3.1 Issues are created externally.** Agents themselves cannot originate new issues under Version 1 of the protocol.
* **3.2 Each Issue *must* include the following mandatory fields:**

  * **Problem Statement** – a concise articulation of the decision to be made.
  * **Background Information** – relevant facts, domain data, or constraints.
* **3.3 An Issue *may* optionally include additional context such as:**

  * **Indicators / Metrics** – measurable criteria for evaluating success.
  * **Goals & Policies** – references to system‑level objectives and policy documents that proposals should respect.
  * **Any other supplementary materials deemed helpful by the Issue creator.**

---

## 4. Conviction Points

* **4.1 Upon invitation, each agent is automatically credited with `StandardInvitePayment` Conviction Points (default = 100).**
* **4.2 Conviction Points constitute the transferable stake agents spend on proposals, feedback, and voting.**
* **4.3 The total Conviction Points in circulation equals the sum of all initial allocations minus any burns (e.g., penalties).**
* **4.4 An agent's Conviction Point balance may never exceed `MaximumCredit()`.** This constraint is evaluated immediately after any action that grants additional points.

---

## 5. Core Variables & Constants

| Variable                     | Type               | Default                 | Purpose                                                                                                                                                   |
| ---------------------------- | ------------------ | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `StandardInvitePayment`      | Integer            | 100                     | Initial Conviction Points granted to each invited agent.                                                                                                  |
| `MaximumCredit()`            | Function → Integer | *TBD*                   | Returns the upper limit on an agent's Conviction Point balance.                                                                                           |
| `ProposalSelfStake`          | Integer            | 50                      | Conviction Points automatically staked by an agent on their own proposal.                                                                                 |
| `RevisionCost(Δ)`            | Formula            | `ProposalSelfStake × Δ` | Dynamic cost for a proposal revision where Δ ∈ \[0,1] is the token‑level diff ratio between old and new drafts.                                           |
| `MaxThinkTicks`              | Integer            | 3                       | Logical ticks allowed **per phase** for an agent to act or signal before kick‑out substitution occurs; the counter resets at the start of each new phase. |
| `KickOutPenalty`             | Integer            | 0                       | Conviction Points burned when an agent is auto‑substituted for inactivity (0 = no penalty).                                                               |
| `FeedbackStake`              | Integer            | 5                       | Conviction Points deducted from an agent each time they submit feedback on another proposal.                                                              |
| `MaxFeedbackPerAgent`        | Integer            | 3                       | Maximum number of feedback entries an agent may submit per Issue.                                                                                         |
| `FeedbackCharLimit`          | Integer            | 500                     | Maximum character length of a single feedback comment.                                                                                                    |
| `RevisionCycles`             | Integer            | 2                       | Number of (Feedback → Revise) loops the system executes before moving to the next consensus phase.                                                        |
| `MaxConvictionMultiplier`    | Float              | 2.0                     | Maximum multiplier a stake can achieve through conviction building.                                                                                       |
| `ConvictionTargetFraction`   | Float              | 0.98                    | Fraction of `MaxConvictionMultiplier` reached after `ConvictionSaturationRounds`.                                                                         |
| `ConvictionSaturationRounds` | Integer            | 5                       | Number of consecutive stake rounds needed to reach `ConvictionTargetFraction` of the maximum multiplier.                                                  |

---

## 6. Proposal Submission & Self‑Stake

* **6.1 Each agent must submit exactly one proposal for an issue.** Agents who do not craft a unique proposal must select the canonical `No Action` proposal.

* **6.2 Upon proposal submission (including `No Action`), the system automatically places a self‑stake of `ProposalSelfStake` Conviction Points (default = 50) from the submitting agent onto that proposal.**

### 🔒 Stake Accounting Rules (RFC‑002)

* Self‑stake is **deducted immediately** from the agent's CP balance.
* The CP is **held by the proposal**, not the agent.
* On revision, the stake is **transferred** to the new version.
* Stake is **non‑refundable** and **burned** at finalization.
* An agent can only have one active proposal per issue.

---

## 7. Enrollment & Issue Assignment

* **7.1 Agents are considered *enrolled* in the System once they have accepted their invitation and authenticated using their credential.**
* **7.2 An enrolled agent must be explicitly assigned to an Issue before they can participate in that Issue's consensus process.**

---

## 8. Proposal Schema

* **8.1 Mandatory fields (every proposal must supply):**

  * **Title** – short human‑readable label for the proposal.
  * **Proposed Action** – clear description of the decision or action the agent is advocating.
  * **Rationale** – explanation of how the Proposed Action addresses the Issue's Problem Statement and aligns with Background constraints.
* **8.2 Optional fields (recommended but not enforced):**

  * **Impact Metrics** – expected effects on the Issue's Indicators / KPIs.
  * **Risk Assessment & Mitigations** – identified risks and how they will be reduced.
  * **Implementation Notes** – high‑level plan, resource needs, timelines.
  * **References & Attachments** – links or artefacts supporting the proposal.
* **8.3 System‑generated fields (populated by the protocol, not the agent):**

  * **AuthorAgentID** – the credential of the submitting agent.
  * **ParentIssueID** – linkage to the Issue under deliberation.
  * **RevisionNumber** – incremented each time the proposal is revised.
  * **CurrentStake** – total Conviction Points staked on the proposal.
  * **CreatedTick / LastUpdatedTick** – logical tick counters for provenance.

---

## 9. Phase Progression & Kick‑Out Timer

* **9.1 Turn‑Based Advancement** – Within each phase, the orchestrator advances from tick *N* to *N+1* once every assigned agent has submitted its required action **or** explicitly signalled READY for tick *N*, **or** when the laggard timer for any agent reaches `MaxThinkTicks`. The timer resets at the beginning of every new phase.
* **9.2 Ready Signal** – In any phase where an agent has no mandatory payload to submit (e.g., they choose to give no feedback), the agent must call `signal_ready()` to confirm completion. This action is free and counts toward 9.1's completeness check.
* **9.3 Kick‑Out Substitution** – If the timer fires, the inactive agent's move is replaced with the protocol's canonical default (e.g., `No Action` for proposals or `Abstain` for votes). The agent is optionally debited `KickOutPenalty` Conviction Points.

> 📎 *When `NoAction` is substituted for a non‑responsive agent, the system still deducts `ProposalSelfStake` CP from the agent's balance (RFC‑003). This ensures economic parity with active proposal submission. If the agent lacks sufficient CP, an `InsufficientCredit` event is logged.*

* **9.4 External Tick Provider (Version 1)** – Version 1 relies on an external scheduler/orchestrator to emit ticks; agents themselves do not initiate ticks autonomously.
* **9.5 Determinism** – All substitutions, penalties, and READY checks are deterministic functions of ledger state, removing human discretion.

---

## 10. Agent Record Schema

* **10.1 Mandatory fields:**

  * **UID** – globally unique, stable identifier for the agent.
  * **Name** – human‑readable label for display and logs.
  * **CredentialKey** – secret token presented with every action (issued at invitation time).
* **10.2 Optional extensions:**

  * **CustomHooks** – list of external endpoints or callback specifications the system may invoke to notify the agent or trigger off‑chain processing.
  * **Metadata** – arbitrary key‑value dictionary reserved for future attributes (e.g., role, reputation score).

---

## 11. Feedback Phase

* **11.1 Eligibility** – Any enrolled agent assigned to the Issue may submit written feedback on any proposal authored by another agent.
* **11.2 Cost of Feedback** – Upon submission, the system deducts `FeedbackStake` Conviction Points (default = 5) from the feedback‑giving agent. These points are burned (removed from circulation) unless future rules re‑allocate them.
* **11.3 Feedback Record** – Each feedback item stores: `FromAgentID`, `TargetProposalID`, `CommentBody`, and `CreatedTick`.
* **11.4 Credit Check** – A `FEEDBACK` entry is accepted only if the author's available balance is ≥ `FeedbackStake`. Otherwise, the action is rejected and an `InsufficientCredit` event is logged.
* **11.5 Quantity Cap** – An agent may submit at most `MaxFeedbackPerAgent` feedback entries per Issue. Additional attempts are rejected with `FeedbackLimitReached`.
* **11.6 Character Limit** – The `CommentBody` must not exceed `FeedbackCharLimit` characters. Longer inputs are rejected with `FeedbackTooLong`.

---

## 12. Phase Structure

The core deliberation workflow for each Issue proceeds as:

```
PROPOSE → ( FEEDBACK → REVISE ) × `RevisionCycles` → …
```

* **12.1 Initial Proposal Phase (`PROPOSE`)** – All agents submit (and self‑stake) their proposals.
* **12.2 Feedback–Revise Loop** – The pair of phases `FEEDBACK` and `REVISE` repeats `RevisionCycles` times (default = 2). Each iteration allows agents to critique others' proposals (costing `FeedbackStake`) and update their own proposals accordingly.
* **12.3 Configurability** – `RevisionCycles` can be tuned per Issue or kept system‑wide. A value of 0 would skip feedback entirely.
* **12.4 Tick Alignment** – Each phase transition follows the Turn‑Based + Kick‑Out rules defined in Section 9.

*Next phases (e.g., VOTE, FINALIZE) will be specified later.*

---

## 13. Ledger & Transparency

* **13.1 Immutable Event Log** – Every state‑changing action (credit, debit, burn, stake transfer, proposal creation, feedback submission, etc.) is appended to an immutable event log with a deterministic sequence number.
* **13.2 Burn Events** – Whenever Conviction Points are burned (e.g., via `FeedbackStake` or `KickOutPenalty`), a `Burn` event is recorded specifying: `AgentID`, `Amount`, `Reason`, `ParentIssueID`, and `Tick`.
* **13.3 Auditability** – At any time, the entire Conviction Point supply can be reconciled by summing initial allocations minus all recorded burns, ensuring full supply transparency without the need for per‑Issue treasuries.

---

## 14. Revise Phase & Costs

* **14.1 Dynamic Revision Cost** – When an agent submits a `REVISE` action, the system computes the token‑level diff ratio `Δ` (changed\_tokens ÷ max(len(old), len(new))). The Conviction Points deducted are:

  ```
  RevisionCost(Δ) = ProposalSelfStake × Δ
  ```

  Thus, a tiny edit (Δ = 0.1) costs 5 CP, a half rewrite (Δ = 0.5) costs 25 CP, and a full rewrite (Δ = 1.0) costs the full 50 CP.

* **14.2 Auto‑Stake‑Tap for Insufficient Credit** – If the agent's liquid balance is < `RevisionCost(Δ)` *but* they still have staked CP on their own proposal, the protocol automatically un‑stakes sufficient CP from that proposal to cover the deficit. If stake is still inadequate, the revision is rejected and an `InsufficientCredit` event is logged.

* **14.3 Ledger Entry** – Every revision produces a `Revision` event recording `AgentID`, `ProposalID`, `Δ`, `Cost`, `Tick`, and any auto‑stake withdrawal amount.

### 🆕 Versioned Proposal Revisions (RFC‑001)

* Each revision creates a **new versioned proposal** (e.g., `PAgent_3@v2`) linked to its parent via `parent_id`.
* The `revision_number` is incremented and tracked.
* The protocol considers **only the latest version** active for staking, feedback, and scoring.
* Existing stake is **transferred** to the new version (no restake required).
* Previous versions are **archived and immutable**.
* Revision lineage is included in the ledger with `delta`, `parent_id`, `tick`, and `revision_cost`.

Optional: A system‑wide or per‑issue cap may limit the number of revisions (e.g., max 5).

---

## 15. Feedback Credit Check

* **15.1 Submission Gate** – A `FEEDBACK` entry is accepted only if the author's available balance is ≥ `FeedbackStake`. Otherwise, the action is rejected and an `InsufficientCredit` event is logged.

---

## 16. Staking Phase & Conviction Mechanics

* **16.1 Phase Ordering** – After the final REVISE phase, the protocol enters one or more `STAKE` rounds.

### STAKE Round Advancement

* **16.1.1 Turn-Based or Timeout** – Each STAKE round advances to the next when **either**:

  * All assigned agents have submitted staking actions or signalled READY, **or**
  * `MaxThinkTicks` have elapsed without input from one or more agents.
* **16.1.2 Silent Agent Behavior** – If an agent does not act or signal by the timeout, their stake is assumed to persist unchanged. No penalty is applied.
* **16.1.3 Hooks for External Pulses** – The orchestrator may emit periodic tick signals to agent `CustomHooks` to support loopless AI agents or polling-based infrastructure.

### STAKE ₁

* **16.6 Per‑Stake Multiplier** – Every individual stake tracks the number of consecutive staking rounds it remains on the *same* proposal. Its effective voting weight each round is:

  ```
  Weight = StakeAmount × ConvictionMultiplier(rounds_held)
  ```
* **16.7 Conviction Curve** – The multiplier follows a smooth exponential approach toward a configurable maximum:

  ```
  k = -ln(1 - ConvictionTargetFraction) / ConvictionSaturationRounds
  ConvictionMultiplier(r) = 1 + (MaxConvictionMultiplier - 1) × (1 - e^(-k × r))
  ```

  where:

  * `r` = `rounds_held` (consecutive rounds on the same proposal, capped at `ConvictionSaturationRounds`).
  * `MaxConvictionMultiplier`, `ConvictionTargetFraction`, and `ConvictionSaturationRounds` are defined in **Section 5**.
  * This guarantees the multiplier reaches ≥ `ConvictionTargetFraction × MaxConvictionMultiplier` after `ConvictionSaturationRounds` (e.g., 1.96× when the max is 2.0× and target fraction is 0.98).

---

## 17. Voting & Winner Determination

* **17.1 Effective Proposal Score** – At the end of the final staking round, each proposal's score is computed as:

  ```
  Score = √( Σ EffectiveStake )
  ```

  where `EffectiveStake` is the conviction‑weighted stake held on the proposal.
* **17.2 Winner Selection** – The proposal with the highest `Score` is declared the consensus winner.
* **17.3 Tie‑Breaker** – If two or more proposals share the top `Score`, the winner is the proposal whose *most recent* stake addition or move occurred earliest (Earliest LastStakeTick).
* **17.4 Ledger Event** – A `Finalize` event records the winning `ProposalID`, winning `Score`, and tie‑breaker resolution.

---

## 18. Finalization & Post-Vote Cleanup

* **18.1 Credit Persistence** – After voting concludes and a winner is declared, any unspent Conviction Points in an agent's balance persist and are retained for use in future Issues.
* **18.2 Stake Burn** – All Conviction Points **staked on proposals**—regardless of whether they were winning or losing—are burned at the conclusion of the Issue. This includes CPs transferred through proposal versioning (RFC‑001) and stakes on auto-submitted `NoAction` proposals (RFC‑003).
* **18.3 Supply Adjustment** – Total Conviction Point supply is recalculated as:

  ```
  TotalSupply = Σ InitialAllocations − Σ BurnEvents
  ```

  This allows full auditability and prevents silent loss of CP.
* **18.4 Post-Issue Transparency** – After an Issue is finalized, the complete ledger of all recorded events, proposals, feedback, and scoring is published. This ledger is publicly accessible to all agents, including those who were not assigned to the Issue. This ensures transparency and supports retrospective review.

---