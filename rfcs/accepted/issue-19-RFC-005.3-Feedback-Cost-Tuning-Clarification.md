---
title: "RFC-005.3: Feedback Cost Tuning Clarification"
number: 19
state: "open"
created: "2025-07-23T21:33:20+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "phase:feedback"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/19"
comments_count: 1
---

# Issue #19: RFC-005.3: Feedback Cost Tuning Clarification

## Description

**Source:** RFC-005 Enhancement #3, critique responses #12 + #14

## Spec Clarification Required
**Current Issue:** Spec implies fixed feedback costs, but economy has always been tunable  
**Fix:** Clarify that feedback_cost and max_feedback_per_agent are configurable parameters

**Current Spec Language:** "FeedbackStake = 5" (appears fixed)  
**Proposed:** "FeedbackStake = 5 (default, configurable per Issue/deployment)"

## Spec Location  
Section 5 constants table + Section 11.2 "Cost of Feedback"

## Background Context
External critiques assumed fixed costs led to dialogue suppression. Need to clarify existing tunability.

**Type:** Editorial clarification, not behavioral change  
**Related Issues:** #12, #13, #14  
**Decision Required:** Accept/Reject clarifying language

## Comments

### Comment by mattjoyce (2025-07-28 11:48:24 UTC)

### Decision: Accept (Editorial Clarification)

The specification currently lists FeedbackStake = 5 and MaxFeedbackPerAgent = 3 in the core constants table
[GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L81-L85)
. This could be misinterpreted as a fixed, non‑tunable cost, whereas the protocol’s economic parameters are designed to be adaptable. External critiques pointed out that assuming fixed costs could suppress participation
[GitHub](https://github.com/mattjoyce/roundtable-consensus/issues/19#L13-L14)
.

We therefore accept this issue as an editorial clarification. FeedbackStake and MaxFeedbackPerAgent should be annotated as default values that may be adjusted per issue or deployment
[GitHub](https://github.com/mattjoyce/roundtable-consensus/issues/19#L4-L9)
. Section 5 and Section 11.2 should be updated accordingly to make this tunability explicit.

This clarification aligns with the upcoming design‑rationale section proposed in RFC‑007.2, which will explain why the protocol treats Conviction Points as a preference budget and uses feedback costs as a selective mechanism
[GitHub](https://github.com/mattjoyce/roundtable-consensus/issues/31#L6-L10)
. By making tunability explicit, we reinforce that costs are levers for balancing deliberation quality and spam prevention, not rigid tolls.

Guidance for the spec patch:
– In the core variables table (Section 5), change the language for FeedbackStake and MaxFeedbackPerAgent to “default, configurable per Issue/deployment.”
– In Section 11.2 (“Cost of Feedback”), add a sentence noting that these values may be tuned based on group size, problem complexity, or other deployment considerations.
– Cross‑reference the forthcoming design‑rationale section once RFC‑007.2 is merged.

---

