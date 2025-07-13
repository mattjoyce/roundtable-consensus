# Sprint: Configuration Dependencies Discovery

**Goal**: Analyze current configuration usage across the system to understand actual dependencies before designing refactoring.

## Background

Current architecture has over-coupling issues:
- TheBureau passes full `GlobalConfig` to Consensus
- Consensus stores full config in `state["config"]` for agents
- Agents get access to all configuration through consensus state
- Config access scattered across `global_config.*` and `self.current_consensus.gc.*`

## Discovery Tasks

### 1. Analyze roundtable.py (Consensus Engine)
**Objective**: Document all GlobalConfig property access in the consensus engine.

**Method**: 
- Read roundtable.py completely
- Document every `global_config.*` or `gc.*` property access
- Identify what consensus actually needs vs what it receives
- Check constructor parameters and all method usage

**Questions**:
- What GlobalConfig properties does Consensus actually use?
- Does Consensus need agent_pool or assignment_award?
- What config values are used for phase transitions?

### 2. Analyze automoton.py (Agent Handlers)
**Objective**: Find all config access in agent decision-making code.

**Method**:
- Search for `consensus.state["config"]` usage
- Document what config agents access for decisions
- Identify agent-specific vs consensus-specific config needs

**Questions**:
- What config do agents actually need for decision-making?
- Do agents need consensus settings or just behavior parameters?
- Are there hardcoded values that should be configurable?

### 3. Map Current Config Flow
**Objective**: Document complete configuration flow through the system.

**Method**:
- Trace config from simulator.py → thebureau.py → roundtable.py → automoton.py
- Identify all config access points
- Document over-coupling and unnecessary exposure

**Mapping**:
```
simulator.py (config.yaml) 
    ↓ GlobalConfig
thebureau.py (configure_consensus)
    ↓ full GlobalConfig
roundtable.py (Consensus constructor)
    ↓ state["config"] = GlobalConfig
automoton.py (agent handlers)
```

### 4. Identify Configuration Domains
**Objective**: Categorize config by responsibility and usage.

**Domains to investigate**:
- **TheBureau-specific**: assignment_award, agent_pool, credit management
- **Consensus-specific**: phase timing, staking rules, conviction params
- **Agent-specific**: decision parameters, behavior settings
- **Cross-cutting**: values needed by multiple components

### 5. Document Findings
**Objective**: Summarize discoveries and recommend separation strategy.

**Output**:
- Current architecture problems identified
- Actual config dependencies mapped
- Recommended configuration boundaries
- Potential sub-config classes needed
- Migration strategy considerations

## Expected Outcomes

1. **Clear dependency map** of what each component actually needs
2. **Identified over-coupling** where components get more config than needed
3. **Configuration domains** properly categorized by responsibility
4. **Concrete recommendations** for config separation architecture
5. **Foundation** for designing minimal, focused config classes

## Success Criteria

- [ ] All GlobalConfig usage documented across roundtable.py
- [ ] All agent config access documented in automoton.py  
- [ ] Complete config flow mapped from simulator to agents
- [ ] Configuration domains clearly identified and categorized
- [ ] Recommendations documented for config separation strategy

## Notes

This is pure discovery work - no code changes, just analysis and documentation to inform future architectural decisions.