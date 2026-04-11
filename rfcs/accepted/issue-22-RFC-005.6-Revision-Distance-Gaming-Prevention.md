---
title: "RFC-005.6: Revision Distance Gaming Prevention"
number: 22
state: "open"
created: "2025-07-23T21:35:36+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "phase:revise"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/22"
comments_count: 1
---

# Issue #22: RFC-005.6: Revision Distance Gaming Prevention

## Description

**Source:** RFC-005 Enhancement #6

## Protocol Change Required
Provide revision distance calculation guidance to prevent gaming:

**Current:** Revision distance underspecified ("token-level diff ratio")  
**Proposed:** Add implementation suggestions:
- Token-level or sentence-level diffs
- Normalized Levenshtein distance  
- Embedding-based similarity
- Leave exact method implementation-specific

## Spec Location
Update Section 14.1 RevisionCost(Δ) calculation details

## Background Context
External critiques noted potential for revision gaming. Need concrete guidance while preserving implementation flexibility.

**Type:** Implementation guidance addition  
**Related Issues:** #12, #13, #14  
**Decision Required:** Accept/Reject guidance additions

## Comments

### Comment by mattjoyce (2025-07-28 12:29:52 UTC)

### Decision: Accept – add guidance on revision‑distance computation

The current specification requires implementations to compute a “revision distance” between a new revision and its parent to prevent gaming, but the description is minimal (token‑level diff ratio)
[GitHub](https://github.com/mattjoyce/roundtable-consensus/issues/22#L6-L18)
. To address concerns about gaming while preserving implementation flexibility, we propose the following guidance:

    Define a dissimilarity measure d in the range 0 ≤ d ≤ 1. A value of 0 means the new revision is identical to its parent; 1 means they are completely different. This scalar is the only requirement. Implementers are free to choose the method used to compute d.

    Avoid prescribing specific algorithms. Organisations may use simple text blocks or complex file structures. The protocol should not mandate a particular diff algorithm; instead, it should stipulate that a defensible measure of dissimilarity must be computed and documented by each deployment.

    Offer general advice:
    – For plain text revisions, common techniques include token‑level or sentence‑level diff ratios, or normalised Levenshtein distance (edit distance divided by the length of the longer string).
    – For documents with more structure or semantics, one might compute vector embeddings (e.g. using language models) and derive d as one minus the cosine similarity between embeddings.
    – When revisions include multiple files or sections, consider weighting changes by the significance of each component.

This approach ensures that implementers cannot game the system by artificially inflating or deflating the distance metric, while allowing them to choose a method suited to their content. The guidance should be added to Section 14.1 of the specification as a non‑normative note, explaining that the revision‑distance computation must yield d ∈ [0, 1] and providing the above examples. Each deployment should document its chosen method and rationale.

---

