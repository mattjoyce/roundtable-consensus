# Changelog

All notable changes to the Round Table Consensus Protocol will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2025-07-30

### Added
- **Design Rationale Section** (RFC-007.2, #31)
  - New Section 2 explaining philosophical reasoning behind protocol mechanics
  - Conviction Points as preference budget (not currency/votes)
  - Burns as preference revelation (not punishment)
  - Feedback costs as quality gates against spam
  - Atomic stakes with individual conviction building
  - Controller as deterministic orchestrator (not ruler)

- **Design Assumptions Section** (RFC-005.1, #17)
  - New Section 4 clarifying protocol's operating environment
  - Curated, non-democratic environments explicit
  - Invitation-based participation only
  - Controller orchestration role clarification
  - Non-adversarial trust model assumptions

- **Blind Staking Mechanics** (RFC-006.2, #24)
  - Stakes hidden during current round, revealed at next tick
  - Prevents first-mover disadvantage in staking phase
  - New Section 16.2 with visibility rules and fairness rationale
  - Mandatory behavior (no configuration toggle)

- **Revision Distance Implementation Guidance** (RFC-005.6, #22)
  - Non-normative guidance for computing revision dissimilarity measure
  - Common approaches: token/sentence-level diffs, normalized Levenshtein distance, embedding-based similarity
  - Prevents gaming while preserving implementation flexibility

- **Experimental Status Acknowledgment** (RFC-007.4, #33)
  - Development status acknowledged in Abstract
  - Contextual experimental annotations on burn mechanics and conviction building
  - Nuanced approach avoiding global "experimental" label

### Changed
- **Issue Origination Delegation** (RFC-005.2, #18)
  - Section 6.1 clarified: issues enter from outside consensus process
  - Protocol agnostic about issue authorship and authorization methods
  - Decouples governance from consensus mechanisms

- **Feedback Cost Configurability** (RFC-005.3, #19)
  - FeedbackStake and MaxFeedbackPerAgent marked as configurable parameters
  - Section 8 constants table and Section 11.2 updated
  - Addresses concerns about potential dialogue suppression

- **Conviction Per-Stake Calculation** (RFC-005.4, #20)
  - Clarified conviction multipliers apply per atomic stake
  - Stakes reset conviction when moved or withdrawn
  - Prevents "conviction parking" exploits
  - Enhanced Section 16.6-16.7 with per-stake behavior examples

- **Ledger Transparency** (Blind Staking Support)
  - Section 13.1 updated to note delayed revelation of stake events
  - Maintains full auditability while supporting blind staking mechanics

### Technical Details
- Protocol version bumped to 1.2.0
- Spec file: `spec/round-table-consensus-v1.2.0.md`
- All sections systematically renumbered due to new Section 2 addition
- 8 individual commits with GitHub issue traceability
- Commits: 0426aaf, 64198e3, c616c47, c7dcf4b, 5040a1a, a047fe3, dfe0477, 5c3448b

## [1.1.0] - 2025-07-12

### Added
- Versioned proposal revisions system (RFC-001)
  - Each revision creates a new versioned proposal with incremental revision numbers
  - Revision lineage tracking with parent_id references
  - Automatic stake transfer to new versions
  - Previous versions archived and immutable
  - Optional system-wide revision caps

### Changed
- Clarified proposal stake accounting behavior (RFC-002)
  - Stakes deducted immediately upon submission
  - Stakes held by proposals, not agents
  - Stakes transferred automatically on revision
  - All stakes burned at finalization regardless of outcome
- Auto-submitted NoAction proposal staking (RFC-003)
  - NoAction proposals now deduct ProposalSelfStake CP for economic parity
  - InsufficientCredit events logged when agents lack sufficient CP

### Technical Details
- Protocol version bumped to 1.1.0
- Spec file: `spec/round-table-consensus-v1.1.0.md`
- Commits: 0aec7db, a19fb62, 0e481d0

## [1.0.0] - Initial Release
- Core Round Table Consensus Protocol specification
- Multi-phase consensus process (PROPOSE → FEEDBACK → REVISE → STAKE → FINALIZE)
- Credit-based participation system
- Conviction-based staking mechanism