---
title: "RFC-005.4: Conviction Per Stake Calculation"
number: 20
state: "open"
created: "2025-07-23T21:34:11+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "phase:stake"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/20"
comments_count: 1
---

# Issue #20: RFC-005.4: Conviction Per Stake Calculation

## Description

**Source:** RFC-005 Enhancement #4

## Protocol Change Required
Clarify conviction calculation method to prevent gaming:

**Current:** Ambiguous whether conviction is per-proposal or per-stake  
**Clarification:** Conviction accrued **per atomic stake**, not per proposal/agent  
**Purpose:** Prevents "conviction parking" exploits, ensures fair accumulation

## Spec Location
Update Section 16.6-16.7 conviction mechanics to explicitly state per-stake calculation

## Background Context
Addresses conviction exploitability concerns from external critiques. Critical for fair staking dynamics.

**Type:** Protocol clarification with behavioral implications  
**Related Issues:** #12, #13, #14  
**Decision Required:** Accept/Reject for v1.2.0 inclusion

## Comments

### Comment by mattjoyce (2025-07-28 11:59:01 UTC)

### Decision: Accept (Behavioural Clarification)

The current staking section describes how each individual stake accumulates a multiplier over consecutive rounds:

– In Section 16.6, “Every individual stake tracks the number of consecutive staking rounds it remains on the same proposal. Its effective voting weight each round is Weight = StakeAmount × ConvictionMultiplier(rounds_held)”
[GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L250-L254)
.
– Section 16.7 defines the exponential curve used to compute the multiplier
[GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L255-L260)
.

However, the spec does not explicitly state that conviction is accrued per atomic stake, rather than per proposal or per agent. This ambiguity could allow “conviction parking,” where an agent builds up conviction on a proposal and then moves their entire stake to a new proposal, preserving the high multiplier and unfairly boosting the new target
[GitHub](https://github.com/mattjoyce/roundtable-consensus/issues/20#L6-L9)
.

We accept RFC‑005.4 to clarify that:

    Conviction is tracked per atomic stake. Each stake has its own rounds_held counter. Moving or withdrawing a stake resets its rounds_held to zero. Agents cannot transfer conviction built on one proposal to another.

    When an agent increases or decreases the amount staked on a proposal, that change constitutes a new atomic stake with its own multiplier curve.

Guidance for the spec patch:
– In Section 16.6, explicitly add language stating that conviction multipliers apply per stake and that rounds_held resets if the stake is moved or withdrawn.
– In Section 16.7, reinforce that r refers to the consecutive rounds a particular stake remains on the same proposal
[GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L255-L260)
, not the total time an agent has participated.
– Consider adding an example illustrating that if an agent unstakes from Proposal A after three rounds (thus having a multiplier close to the maximum) and then stakes those CP on Proposal B, the multiplier resets to 1× for the new stake.

Clarifying this per‑stake behaviour will close the loophole that could enable conviction parking and ensure that conviction reflects sustained support for a specific proposal, preserving fairness and encouraging commitment.

---

