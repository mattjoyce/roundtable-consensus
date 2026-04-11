# RFC-003: Clarify Staking Behavior for Auto-Submitted NoAction Proposals

**Status**: Accepted  
**Issue**: #5  
**Target version**: 1.0.1  
**Author**: Matt Joyce  
**Date**: 2025-07-12  
**Relevant Spec Section**: §6.2 Proposal Submission & Self-Stake, §9.3 Kick-Out Substitution  

---

## 📌 Summary

The protocol currently states that submitting a proposal (including `NoAction`) incurs a `ProposalSelfStake` deduction from the agent. However, it's unclear whether this applies when `NoAction` is **auto-submitted** due to timeout substitution.

---

## 🎯 Motivation

### Current Ambiguity

The specification contains potentially conflicting guidance:

> **§6.2** — *"Upon proposal submission (including `No Action`), the system automatically places a self‑stake..."*

> **§9.3** — *"If the timer fires, the inactive agent's move is replaced with the protocol's canonical default (e.g., `NoAction`)."*

### The Problem

- ✅ It is **clear** that active submission of `NoAction` incurs a stake
- ❓ It is **unclear** if **auto-submitted** `NoAction` also incurs a stake

Without clarification, this creates:
- **Inconsistent implementation behavior** across different simulators
- **Potential economic exploit** where passive agents could avoid staking costs
- **Fairness concerns** between active and passive participation
- **Audit complexity** in determining whether stakes were properly applied

---

## 📜 Proposal

Clarify that **auto-submitted NoAction proposals incur the same staking cost as manually submitted proposals**.

### Specific Text Changes

Add to **§9.3 Kick‑Out Substitution**:

> 📎 *Note: When `NoAction` is substituted for a non-responsive agent, the system still deducts `ProposalSelfStake` CP from the agent's balance. This ensures economic parity with active proposal submission.*

Alternative amendment to §6.2:

> *This staking rule applies equally to `NoAction` proposals, whether submitted manually by the agent or substituted automatically by the timeout mechanism.*

### Accounting Behavior

When timeout substitution occurs:
```
IF agent.balance >= ProposalSelfStake:
    agent.balance -= ProposalSelfStake
    proposal.stake += ProposalSelfStake
    CreditManager.log_transaction(TIMEOUT_STAKE, agent_id, proposal_id, ProposalSelfStake)
ELSE:
    CreditManager.log_insufficient_balance_event(agent_id, ProposalSelfStake)
    // Handle insufficient balance per existing protocol
```

---

## 🔄 Backwards Compatibility

This clarification aligns with current simulator behavior and maintains consistency with existing economic models. No breaking changes are required.

---

## Reference Implementation Checklist

- [ ] Spec patch to clarify timeout staking behavior in §9.3
- [ ] Verify simulator applies stakes to auto-submitted NoAction
- [ ] Add tests for timeout staking scenarios  
- [ ] Add tests for insufficient balance during timeout
- [ ] Update documentation with timeout staking examples

---

## ✳️ Justification

### Economic Fairness
- **No benefit from inaction**: Prevents gaming through deliberate timeouts
- **Consistent incentives**: Same economic model for all proposal types
- **Participation encouragement**: Maintains pressure for active engagement

### Technical Benefits
- **Deterministic behavior**: Clear rules for all submission paths
- **Audit trail consistency**: All proposals have associated stakes
- **Implementation simplicity**: Single staking rule across submission methods

### Protocol Integrity
- **Supply consistency**: Credit burns occur regardless of submission method
- **Replay determinism**: Timeout scenarios produce consistent results
- **Fair resource allocation**: All participants bear equal proposal costs

---

## ⚠️ Drawbacks

- **Potential hardship**: Agents with low balances may face forced staking
- **Complexity edge case**: Need to handle insufficient balance during timeout
- **Implementation effort**: Requires verification across all timeout paths

---

## 🔚 Alternatives Considered

1. **No staking for auto-submitted NoAction**
   - Rejected: Creates economic exploit and fairness issues
   
2. **Reduced staking cost for timeouts**
   - Rejected: Adds complexity without clear benefit
   
3. **Grace period before timeout staking**
   - Rejected: Complicates timing mechanisms unnecessarily

---

## 📆 Next Steps

If accepted:
- Update spec §9.3 with timeout staking clarification
- Verify simulator implementation matches specification  
- Add comprehensive timeout staking tests
- Document edge cases for insufficient balance scenarios
- Consider if this requires a minor version bump (1.0.1) for clarification