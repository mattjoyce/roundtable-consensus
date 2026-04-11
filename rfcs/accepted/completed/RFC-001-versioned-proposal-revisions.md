---
**rfc:** 001  
**title:** Versioned Proposal Revisions  
**status:** Accepted  
**author:** Matt Joyce  
**date:** 2025-07-12  
**issue:** #6
**target-version:** 1.1.0
**implemented:** commit a19fb62
**labels:** [revision, proposal, versioning, protocol-change]  
---

# RFC‑001: Versioned Proposal Revisions

## 🧭 Summary

This RFC proposes changing the behavior of the `REVISE` phase to **preserve previous versions** of an agent's proposal by assigning **explicit version identifiers**. Rather than modifying a proposal in-place, each revision becomes a new version (e.g., `PAgent_4@v2`) linked to its predecessor. This provides traceability, analytics value, and potential benefits for human–AI interfaces.

---

## 🎯 Motivation

The current protocol (v1.0.0) specifies that:
> "A revision modifies the original proposal in-place [...] There is no need to re-stake."

While minimal and efficient, this approach:
- **Obscures the deliberation trail** during revision cycles.
- **Prevents agents (and humans) from reviewing changes over time.**
- **Limits scoring models** that could reward constructive editing or penalize flip-flopping.
- **Complicates debugging** and audit logs.

In contexts where **transparency, explainability, or human-in-the-loop interfaces** are valued, having access to the **full revision lineage** of proposals is essential.

---

## ✏️ Proposal

We amend `REVISE` behavior to support **versioned proposals**, as follows:

### Proposal Identity

- Each proposal submitted starts at version 1:
  - `PAgent_4@v1`
- Revisions increment the version:
  - `PAgent_4@v2`, `PAgent_4@v3`, etc.

### Protocol Changes

1. **Revision creates a new proposal version.**
   - It is linked to its immediate parent by `parent_id`.
   - Proposal ID is extended with `@vN`.

2. **Only the latest version is considered active.**
   - All CP stake, scoring, and conviction actions apply to the active version.
   - Earlier versions are archived and immutable.

3. **No new stake is required for a revision.**
   - Existing stake is automatically transferred to the new version.
   - This preserves the "single active proposal per agent" principle.

4. **Protocol ledger records revision lineage.**
   - Include `delta`, `parent_id`, `revision_number`, `tick`, and CP cost in event logs.

5. **Limit revision versions per issue (optional).**
   - A soft or hard limit (e.g., max 5 versions) may be imposed to prevent abuse.

---

## 🔄 Backwards Compatibility

- Existing single-version proposals remain compatible
- Simulations may store proposal history as a list
- Human UIs may show a diff timeline
- No changes required to scoring unless future RFCs extend this

---

## Reference Implementation Checklist

- [x] Spec patch to support versioned proposals
- [x] Implement `ProposalVersion` model or extend `Proposal` with `version` and `parent_id`  
- [x] Update `receive_revision()` to create new objects instead of mutating in-place
- [x] Update ledger and credit manager to attach to the current version
- [x] Ensure old versions are excluded from scoring/conviction
- [x] Tests pass

---

## ✅ Benefits

| Feature | Benefit |
|--------|------------|
| 📜 Provenance | Clear trace of changes, improves accountability |
| 🧠 Deliberation | Enables richer analysis of agent behavior |
| 🧩 Extensibility | Lays foundation for future scoring, voting, or human co-editing |
| 🧪 Debuggability | Easier to understand why proposals evolved or failed |

---

## ⚠️ Drawbacks

- **Slight increase in complexity** of proposal tracking.
- **Memory/storage cost** increases with each version (though modest).
- Requires internal changes to `TheBureau`, proposal assignment logic, and possibly `assign_agent_to_proposal`.

---

## 🔚 Alternatives Considered

- Keeping only a flat "revision number" in metadata (status quo).
- Copying content to an audit log instead of versioning proposals.
- Using proposal hashes instead of version tags (harder to trace).

---

## 📆 Implementation

Implemented in commit a19fb62 with the following changes:
- Added versioning support to proposal system
- Modified revision behavior to create new versions
- Updated credit management to handle version transfers
- Enhanced logging for revision lineage tracking