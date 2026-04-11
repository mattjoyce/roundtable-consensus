# RFC-002: Proposal Stake Accounting Clarification

**Status**: Accepted  
**Issue**: #4  
**Target version**: 1.1.0  
**Author**: Matt Joyce  
**Date**: 2025-07-12  
**Relevant Spec Section**: §6.2 Proposal Submission & Self-Stake  

---

## 🎯 Summary

The spec currently mandates that `ProposalSelfStake` (default = 50 CP) is applied when a proposal is submitted, but it does not clearly define:

- Where the stake is held
- Whether it is burned immediately
- Whether it can be reused
- What happens to it on revision

---

## 🎯 Motivation

The current protocol specification lacks clarity around the accounting mechanics of proposal self-stakes. This ambiguity can lead to:

- Inconsistent implementation behavior
- Difficulty in auditing credit flows
- Potential for agents to misuse staked credits
- Unclear expectations for stake lifecycle management

Clear specification of stake accounting ensures:
- Deterministic behavior across implementations
- Proper economic incentives for meaningful proposals
- Clean audit trails for credit management
- Consistent user expectations

---

## ✅ Current Simulator Behavior

- Stake is **deducted from the agent immediately**
- Stake is **credited to the proposal** via `creditmgr.proposal_stakes`
- Stake is **moved** to the revised proposal if updated
- Stake is **burned** at finalization

This matches the intended behavior of self-stake as a form of **locked commitment**.

---

## 📜 Proposal

We clarify the stake accounting rules as follows:

1. **Immediate Deduction**: Self-stake is **immediately deducted** from the agent's balance upon proposal submission
2. **Proposal Custody**: Stake is **held by the proposal**, not the agent
3. **Revision Transfer**: If the proposal is revised, the stake is **moved** to the new version
4. **Non-Refundable**: Stake is **never refundable** to the agent
5. **Finalization Burn**: Stake is **burned** at the end of the Issue, regardless of outcome

### Detailed Accounting Rules

#### On Proposal Submission
```
Agent.balance -= ProposalSelfStake
Proposal.stake += ProposalSelfStake
CreditManager.log_transaction(STAKE, agent_id, proposal_id, amount)
```

#### On Proposal Revision
```
OldProposal.stake -= ProposalSelfStake
NewProposal.stake += ProposalSelfStake
CreditManager.log_transaction(STAKE_TRANSFER, old_proposal_id, new_proposal_id, amount)
```

#### On Issue Finalization
```
FOR each proposal IN issue:
    CreditManager.burn(proposal.stake)
    CreditManager.log_transaction(BURN, proposal_id, null, proposal.stake)
```

---

## 🔄 Backwards Compatibility

This clarification aligns with current simulator behavior, so no breaking changes are required. Existing implementations that follow the current simulator logic will remain compliant.

---

## Reference Implementation Checklist

- [ ] Spec patch to clarify stake accounting rules in §6.2
- [ ] Verify simulator matches proposed behavior
- [ ] Add tests for stake transfer on revision
- [ ] Add tests for stake burning on finalization
- [ ] Update documentation with accounting examples

---

## ✳️ Justification

- **Prevents misuse**: Stake CP cannot be reused for feedback/revise actions
- **Encourages commitment**: Meaningful proposal commitment through locked stakes
- **Clean auditing**: Ledger burn events are clean and auditable
- **Implementation alignment**: Matches current simulation logic and expectations
- **Economic consistency**: Maintains proper incentive structures

---

## 🔚 Alternatives Considered

1. **Refundable Stakes**: Allow stake refund if proposal is withdrawn
   - Rejected: Reduces commitment incentives
   
2. **Agent-Held Stakes**: Keep stake in agent balance but mark as reserved
   - Rejected: More complex accounting, potential for misuse
   
3. **Immediate Burning**: Burn stake immediately on submission
   - Rejected: Prevents stake transfer on revision

---

## 📆 Next Steps

If accepted:
- Update spec §6.2 with detailed accounting rules
- Verify simulator implementation matches specification
- Add comprehensive tests for all stake lifecycle events
- Update any documentation that references stake mechanics