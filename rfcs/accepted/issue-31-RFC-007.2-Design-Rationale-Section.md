---
title: "RFC-007.2: Design Rationale Section"
number: 31
state: "open"
created: "2025-07-23T21:43:23+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "topic:framing"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/31"
comments_count: 1
---

# Issue #31: RFC-007.2: Design Rationale Section

## Description

**Source:** RFC-007 Section #2 - Add design rationale explanation

## Spec Change Required
Add new section explaining key philosophical choices:

**Rationale Topics:**
- CP as Preference Budget (not currency/influence tokens)
- Burn as Signal, Not Cost (reveals priorities) 
- Feedback Cost logic (selective critique vs spam)
- Atomic Stake Conviction (individual building vs strategic timing)
- Controller as Coordinator (not ruler - can be automated)

## Spec Location
New section (likely Section 2 or appendix)

## Purpose
Addresses "design underspecification" critiques by explaining the "why" behind mechanics.

**Type:** Major documentation addition  
**Related:** #16 (RFC-007 parent), critiques #12/#14  
**Decision Required:** Accept design rationale section for v1.2.0

## Comments

### Comment by mattjoyce (2025-07-27 03:49:44 UTC)

## Resolution – RFC‑007.2 Accepted

We accept the proposal in RFC‑007.2 to add a Design Rationale section to the specification. This new section will explain the reasoning behind key architectural and philosophical choices. Below is guidance for the amendment author to use when drafting this section.
💡 Design Rationale Summary
1. Conviction Points (CP) as Preference Budget

CP is not a currency, vote, or influence token. It is a scarce preference budget used to express what each participant cares about most. Backing a proposal, giving feedback, or revising a proposal requires CP—revealing relative importance through resource allocation.
2. Burn as Preference Revelation, Not Penalty

While the term “burn” has blockchain connotations, in this protocol it functions as preference revelation—a non-refundable commitment that demonstrates sincerity. It is not punitive, but expressive.
3. Feedback Tolls to Incentivize Meaningful Engagement

Feedback incurs a CP cost to discourage low-effort or spam responses. This creates a soft gate, ensuring participants weigh the value of their feedback before investing CP.
4. Atomic Stakes and Conviction Accumulation

By treating each stake as an atomic transaction with a unique aging curve, we allow agents to dynamically adjust positions and accumulate conviction over time. This encourages early staking and clearer strategic signaling.
5. Coordinator as Minimal Judge

The Coordinator is not a central authority or adjudicator. It is a deterministic orchestrator that advances ticks, validates phases, and records outcomes. In future versions, this role could be automated or even governed by another RTCP process (“stacked coordination”).

---

