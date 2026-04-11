---
title: "RFC-006.2: Blind Stake Mode"
number: 24
state: "open"
created: "2025-07-23T21:37:53+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "phase:stake"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/24"
comments_count: 1
---

# Issue #24: RFC-006.2: Blind Stake Mode

## Description

**Source:** RFC-006 Proposal #2 - Optional enhancement

## Protocol Change Required
Add optional blind staking mechanism:

**Feature:** Stakes hidden until tick closes
**Purpose:** Prevents last-mover advantage in staking
**Trade-off:** May increase uncertainty in cooperative contexts

## Spec Location
Optional mode for Section 16 (Staking Phase)

## Implementation Notes
- Alternative to transparent staking
- Addresses game-theory vulnerability noted in critiques
- Controller/deployment configurable

**Type:** Optional strategic enhancement  
**Related:** #15 (RFC-006 parent), critiques #12/#14  
**Decision Required:** Accept/Reject/Defer for optional inclusion

## Comments

### Comment by mattjoyce (2025-07-28 12:22:00 UTC)

Decision: Accept – blind staking is now a mandatory rule, not an option.

We agree that in a turn‑based system, allowing agents to see others’ stakes within the same round disadvantages those who act early. To ensure fairness without adding tunable parameters, the staking phase will be blind by default: agents cannot see stake submissions made in the current round.

How it works:

    Each agent submits their stake during the STAKE round as usual. The system records these Stake events immediately in the ledger, but withholds them from other agents’ view until the round completes.

    Agents can inspect all stakes logged prior to the current round, including every atomic stake’s amount, proposal and conviction multiplier
    [GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L250-L254)
    . However, they cannot see any stake submitted during the current round until the next tick begins.

    At the start of the next tick, all hidden Stake events from the previous round become visible in the event log. This preserves full auditability and transparency over time
    [GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L194-L199)
    .

Guidance for the specification:

    Update Section 16 (“Staking Phase & Conviction Mechanics”) to describe this visibility rule. Replace any wording suggesting that stakes are broadcast immediately with language such as: “During each STAKE round, stake submissions are appended to the ledger but not visible to other agents until the round completes. At the beginning of the next tick, all stakes from the previous round are revealed.”

    Emphasise fairness in the design rationale: hiding in‑round stakes removes the first‑mover disadvantage and discourages strategic last‑second adjustments, while still allowing agents to re‑stake based on the cumulative distribution between rounds.

    No new parameters or modes: Blind staking is part of the core protocol; there is no BlindStakeEnabled toggle. This avoids introducing another variable for implementations to tune.

    Conviction mechanics unchanged: Each stake still tracks its own rounds_held and accumulates the conviction multiplier accordingly
    [GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L250-L254)
    . Moving a stake to a new proposal resets its rounds_held, as clarified in RFC‑005.4.

    Transparency and ledger: Because all stake events are ultimately published, the system remains fully auditable. Section 13 may require minor wording tweaks to note that stake events are revealed one tick later than they occur.

By adopting blind staking as a core rule, we strengthen fairness in the staking phase while keeping the protocol deterministic and transparent.

---

