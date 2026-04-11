---
title: "RFC-005.2: Issue Origination Delegation"
number: 18
state: "open"
created: "2025-07-23T21:30:21+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "topic:issues"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/18"
comments_count: 1
---

# Issue #18: RFC-005.2: Issue Origination Delegation

## Description

**Source:** RFC-005 Enhancement #2

## Protocol Change Required
Clarify that while agents *can* author Issues, the controller acts as a filter:

**Addition:** IssueAdmissionPolicy() function for implementers  
**Purpose:** Defend against low-value or spam Issues  
**Scope:** Implementation-specific filtering rules

## Spec Location
Update Section 3.1 "Issues are created externally" with delegation details

## Background Context
Addresses concerns about Issue framing integrity and controller transparency from external critiques.

**Related Issues:** #12, #13, #14  
**Decision Required:** Accept/Reject for v1.2.0 inclusion

## Comments

### Comment by mattjoyce (2025-07-28 11:34:02 UTC)

We’ve reviewed RFC‑005.2 and agree that the specification should remain agnostic about who can author issues. To avoid prescribing specific roles or authorisation mechanisms, Section 3.1 should be revised to say that issues enter the system from outside the consensus process and that the protocol does not define the authorisation method or qualifications of an issue’s author
[GitHub](https://github.com/mattjoyce/roundtable-consensus/blob/cab011dd555f03e0534bbb8188c4225a0450b46d/spec/round-table-consensus-latest.md#L49-L52)
. Once an issue is authorised, the existing life‑cycle rules ensure fair resolution. This change decouples governance from consensus, allowing deployments to implement their own issue‑creation policies while keeping the consensus engine focused on aggregating preferences and producing legitimate decisions.

---

