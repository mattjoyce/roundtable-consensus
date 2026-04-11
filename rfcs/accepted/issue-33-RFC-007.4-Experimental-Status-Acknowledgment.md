---
title: "RFC-007.4: Experimental Status Acknowledgment"
number: 33
state: "open"
created: "2025-07-23T21:44:35+00:00"
author: "mattjoyce"
labels: ["area:spec", "type:rfc", "status:accepted", "topic:framing"]
milestone: null
assignees: []
url: "https://github.com/mattjoyce/roundtable-consensus/issues/33"
comments_count: 1
---

# Issue #33: RFC-007.4: Experimental Status Acknowledgment

## Description

**Source:** RFC-007 Section #4 - Acknowledge experimental nature

## Spec Change Required
Update versioning/status language to reflect exploratory phase:

**Proposed Language:**
> "RTCP v1.2 is an experimental protocol under active development. It is suitable for simulation, educational, or cooperative research use."

## Spec Location
- Protocol header/metadata
- Abstract or introduction
- README status badges

## Purpose
Align community expectations, acknowledge development status appropriately.

**Type:** Status/metadata update  
**Related:** #16 (RFC-007 parent)  
**Decision Required:** Accept experimental status acknowledgment

## Comments

### Comment by mattjoyce (2025-07-27 04:12:02 UTC)

### RFC‑007.4 Accepted with Modifications

We accept the core intent of RFC‑007.4: the need to acknowledge the developmental nature of the protocol and communicate its evolving status to readers and contributors.

However, rather than globally labeling the entire specification as “experimental,” we will adopt a more nuanced approach:
🧾 Resolution

    ✅ The specification will acknowledge that it is under active development and that some features are experimental.

    ❌ We will not apply a global 'experimental' badge or label to the full protocol or version (e.g., v1.2), as this may obscure its usefulness for simulation, concept testing, and structured deliberation.

    ✅ We will annotate specific mechanics (e.g., burn, stacking, dynamic conviction) as experimental within the spec where relevant.

📅 Versioning to Be Handled Separately (RFC‑008)

We will draft a separate RFC (RFC‑008) to define a new calendar-based versioning and release cadence, potentially using YY.MM format. This system will clarify how development snapshots (e.g., 2025.3-rc1) relate to future stable releases (e.g., 2025.4).

Until then, the current working spec remains v1.2, with experimental annotations applied contextually.

---

