# Sprint: Implement Proposal Staking in TheBureau

**Sprint Name**: bureau-proposal-stake

## Goal

Implement enforcement and tracking of ProposalSelfStake CP for all proposal submissions — including explicit and auto-submitted NoAction proposals — using the CreditManager. Stake must be:

1. Deducted immediately from the agent's CP balance.
2. Held against the proposal ID.
3. Never spendable by the agent.
4. Moved on revision (handled in a future sprint).
5. Burned at finalization (handled in FinalizePhase sprint).

## 📍 Scope

- ✅ Modify only TheBureau and CreditManager.
- ✅ Apply to both active and passive NoAction submissions.
- 🚫 Do not modify agents, proposal phases, or consensus tick logic.
- 🚫 Do not implement burn/finalization yet.

## 📦 Tasks

### 1. Extend CreditManager with proposal stake store

In `creditmanager.py`:

```python
self.proposal_stakes: Dict[str, int] = {}  # proposal_id → staked amount
```

### 2. Add method to stake CP to a proposal

```python
def stake_to_proposal(self, agent_id: str, proposal_id: str, amount: int, tick: int, issue_id: str) -> bool:
    if self.attempt_deduct(agent_id, amount, "Proposal Self Stake", tick, issue_id):
        self.proposal_stakes[proposal_id] = amount
        logger.bind(event_dict={
            "event_type": "stake_recorded",
            "agent_id": agent_id,
            "proposal_id": proposal_id,
            "amount": amount,
            "tick": tick,
            "issue_id": issue_id
        }).info(f"Staked {amount} CP from {agent_id} to proposal {proposal_id}")
        return True
    return False
```

### 3. Modify TheBureau.receive_proposal() to stake CP

After the proposal passes all validation and is added to the issue:

```python
stake_success = self.creditmgr.stake_to_proposal(
    agent_id=agent_id,
    proposal_id=proposal.proposal_id,
    amount=self.current_consensus.gc.proposal_self_stake,
    tick=tick,
    issue_id=issue_id
)

if not stake_success:
    logger.bind(event_dict={
        "event_type": "proposal_rejected",
        "agent_id": agent_id,
        "reason": "insufficient_cp_for_stake"
    }).warning(f"Rejected proposal from {agent_id}: Not enough CP to stake")
    return
```

Place this after `self.current_issue.assign_agent_to_proposal(...)` and before `self.signal_ready(agent_id)`.

### 4. Update create_no_action_proposal() to also stake

In the for loop inside `run()` when assigning fallback proposals:

```python
proposal = self.create_no_action_proposal(...)
self.current_issue.add_proposal(proposal)

self.creditmgr.stake_to_proposal(
    agent_id=agent_id,
    proposal_id=proposal.proposal_id,
    amount=self.current_consensus.gc.proposal_self_stake,
    tick=self.current_consensus.state["tick"],
    issue_id=self.current_issue.issue_id
)

self.current_issue.assign_agent_to_proposal(agent_id, proposal.proposal_id)
self.signal_ready(agent_id)
```

## 🧪 Acceptance Criteria

- ✅ All submitted proposals (custom or NoAction) result in 50 CP staked.
- ✅ Stake is deducted from agent balance and held in `creditmgr.proposal_stakes`.
- ✅ Simulator logs all stake events with `stake_recorded`.
- ✅ Agents who cannot afford the stake are rejected and logged with `insufficient_cp_for_stake`.
- ✅ Stake is not burned yet.

## 🔒 Invariants

- One proposal per agent per phase.
- No double staking.
- Proposal must be accepted into the Issue before stake is recorded.
- Stake is non-refundable and not included in balance checks for other actions (feedback, revise).