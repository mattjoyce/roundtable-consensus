---
title: "RFC-005.1: Design Assumptions Clarification"
number: 17
state: "open"
created: "2025-07-23T21:29:31+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "topic:controller"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/17"
comments_count: 1
---

# Issue #17: RFC-005.1: Design Assumptions Clarification

## Description

**Source:** RFC-005 Enhancement #1, issues #12 + #14 critiques

## Protocol Change Required
Add explicit design assumptions section to spec clarifying:

**Scope:** Curated, non-democratic environments  
**Agent Selection:** Invited and selected by controller  
**Controller Role:** May be automated/agent system, not necessarily human  
**Trust Model:** Non-adversarial, bounded-rational agents assumed

## Spec Location
New Section 1.3 "Design Assumptions" after Section 1.2

## Background Context  
External critiques (Google Gemini #12, Claude Opus #14) highlighted that the protocol's curated trust assumptions weren't explicit, leading to concerns about controller omnipotence and adversarial behavior.

**Related Issues:** #12, #13, #14  
**Decision Required:** Accept/Reject for v1.2.0 inclusion

## Comments

### Comment by mattjoyce (2025-07-28 11:35:39 UTC)

After reviewing RFC‑005.1 we agree that the specification should make its trust assumptions explicit. The current introduction mentions that initial versions assume a trusted execution environment and non‑adversarial actors
[GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L25-L28)
, but this is implicit and easy to overlook. External critiques have flagged concerns about hidden assumptions and controller omnipotence
[GitHub](https://github.com/mattjoyce/roundtable-consensus/issues/17#L14-L16)
, so clarity is important.

We therefore support adding a new Section 1.3 titled “Design Assumptions.” This section would summarise:

    The protocol operates in curated, non‑democratic environments; it is not a permissionless public consensus system.

    Agents participate by invitation and assignment; each agent receives a credential and is enrolled/assigned by a controller
    [GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L33-L37)
    .

    The controller functions as an orchestrator and may be a human administrator or an automated system; its role is to invite agents and coordinate state transitions.

    The base trust model assumes honest, bounded‑rational agents interacting in a trusted execution environment, while noting that future versions may add adversarial resilience
    [GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L25-L28)
    .

Making these assumptions explicit will help implementers, reviewers and simulators understand the environment the protocol is designed for and lay the groundwork for future enhancements.

---

