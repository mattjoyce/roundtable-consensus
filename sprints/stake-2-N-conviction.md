# 📍 Sprint STAKE‑3: Implement Conviction Growth and Stake Reallocation

## 🔍 Context

In STAKE-2, agents learned how to allocate remaining CP to proposals. However, the protocol calls for additional staking behaviors:

* Conviction multipliers that reward persistent support
* The ability to shift support (stake reallocation)

This sprint delivers STAKE-3, which implements those core protocol expectations.

---

## ✅ Goal

Enable agents to:

* Accumulate conviction through repeated staking rounds
* Switch stake between proposals
* Benefit from conviction multipliers as per `conviction_params`
* Maintain an audit trail of conviction-weighted support

---

## 🗂️ Scope of Work

### 1. Conviction Registry (New Structure)

Create a structure in `CreditManager`:

```python
self.conviction_ledger = defaultdict(lambda: defaultdict(int))  # agent_id -> proposal_id -> accumulated stake
```

This will:

* Track each agent's cumulative CP committed per proposal
* Be updated in each stake round

### 2. Conviction Multiplier Logic

The exponential conviction growth formula is defined as:

```
EffectiveWeight = stake_amount × (1 + (MaxMultiplier - 1) × (1 - exp(-k × r)))
```

Where:

* `r` is the number of consecutive rounds the agent has supported the proposal
* `k = -ln(1 - T) / R`
* `T` is the target fraction of `MaxMultiplier` reached at round `R` (e.g. 98% at 5 rounds)

This produces an asymptotic growth curve:

* Round 1: \~1.16×
* Round 3: \~1.55×
* Round 5: \~1.96×
* Round ∞: → 2.0×

Use `conviction_params` from `StakePhase`, e.g.:

```python
conviction_params = {
  "base": 1.0,
  "growth": 0.2
}
```

Effective weight = `stake_amount * (base + growth * prior_rounds)`
Store result alongside raw stake.

### 3. Update `receive_stake()` in `thebureau.py`

Before applying new stake:

* Check if agent has existing conviction on another proposal
* If so:

  * Option A: Reject new stake if switching is disallowed
  * Option B: Allow switch and update `conviction_ledger` and `proposal_stakes`

Record in:

```python
self.creditmgr.conviction_ledger[agent_id][proposal_id] += stake_amount
```

Also emit a `conviction_updated` event with multiplier.

### 4. Stake Transfer Logic (Optional or Phase Gated)

If stake switches are allowed:

* Detect if agent is switching
* Log `conviction_switched` event
* Optionally zero conviction on prior proposal

---

## 🥺 Constraints

* Do not alter STAKE-1 behavior
* Conviction multiplier must be deterministic and transparent
* Trait influence on stake amount remains valid
* Conviction can only grow; no decay implemented yet

---

## 🔎 Auditing Guidance

This sprint introduces cross-round memory and amplified impact, which can increase audit complexity. To support visibility:

* Emit a `conviction_updated` event each time an agent increases support for a proposal.

* Include the following in each event:

  * Raw stake amount
  * Calculated multiplier
  * Effective weight
  * Total accumulated conviction for that `(agent_id, proposal_id)` pair

* When switching stakes, emit a `conviction_switched` event that includes:

  * From proposal ID
  * To proposal ID
  * Amount reallocated
  * Tick and round metadata

Use these queries to support trace:

```sql
SELECT * FROM events WHERE event_type LIKE 'conviction_%';
SELECT * FROM events WHERE agent_id = 'Agent_7' AND event_type = 'stake_recorded';
```

---

## 🤔 Testing Plan

1. Run simulation with `staking_rounds > 2`
2. Enable high verbosity and use SQLite log queries:

```bash
sqlite3 db/YOURSIM.sqlite3 "SELECT * FROM events WHERE event_type LIKE 'conviction%';"
```

3. Confirm:

* `conviction_updated` events appear
* Multiplier increases per round
* Support shifts tracked cleanly if switching is enabled

---

## 📌 Outcome

* Conviction weights now grow over time
* Stake is remembered per agent–proposal pair
* Protocol-compliant support logic
* Clear event trace for auditing and analysis

---
