# RFC-004: Staking Action Limits Per Tick
*Status*: Draft
*Issue*: #11  
*Target version*: 1.2.0

## Spec Changes Required

Add new subsection **16.2 Staking Action Constraints** after existing Section 16.1:

**Rule 1:** One stake-related action per agent per tick (Stake/Switch/Unstake)
**Rule 2:** Each action targets single proposal only
**Rule 3:** Self-stake switchable but not unstakable; voluntary stakes fully flexible

## Integration Notes
- Insert after Section 16.1.3 (Hooks for External Pulses)
- Update enforcement language: "Protocol violations ignored/logged"
- Self-stake CP tracking required for Rule 3 implementation

## Reference Implementation
- [ ] Spec patch Section 16.2
- [ ] Code alignment (post-spec)
- [ ] Test coverage