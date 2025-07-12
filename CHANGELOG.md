# Changelog

All notable changes to the Round Table Consensus Protocol will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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