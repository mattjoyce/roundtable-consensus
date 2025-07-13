# SQL Queries for Round Table Consensus Database

This file contains useful SQL queries for analyzing simulation data stored in the SQLite databases.

## Database Schema

```sql
-- Check table structure
.schema events

-- Current schema:
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    tick INTEGER,
    phase TEXT,
    agent_id TEXT,
    event_type TEXT,
    message TEXT,
    payload TEXT
);
```

## Credit Management Queries

### Proposal Staking Analysis

```sql
-- All proposal stakes recorded
SELECT event_type, agent_id, message 
FROM events 
WHERE event_type = 'stake_recorded' 
ORDER BY id;

-- Proposal stakes by agent
SELECT agent_id, COUNT(*) as stake_count
FROM events 
WHERE event_type = 'stake_recorded'
GROUP BY agent_id
ORDER BY stake_count DESC;

-- Active vs Auto-submitted NoAction stakes
SELECT 
    CASE 
        WHEN message LIKE '%PNOACTION%' THEN 'Auto NoAction'
        ELSE 'Active Proposal'
    END as proposal_type,
    COUNT(*) as count
FROM events 
WHERE event_type = 'stake_recorded'
GROUP BY proposal_type;
```

### Credit Burns and Awards

```sql
-- All credit burns
SELECT agent_id, message 
FROM events 
WHERE event_type = 'credit_burn' 
ORDER BY id;

-- Credit burns by reason
SELECT 
    CASE 
        WHEN message LIKE '%Proposal Self Stake%' THEN 'Proposal Stake'
        WHEN message LIKE '%Initial credit%' THEN 'Initial Award'
        ELSE 'Other'
    END as reason,
    COUNT(*) as count
FROM events 
WHERE event_type = 'credit_burn'
GROUP BY reason;

-- Insufficient credit attempts
SELECT agent_id, message 
FROM events 
WHERE event_type = 'insufficient_credit' 
ORDER BY id;
```

### Agent Credit Activity

```sql
-- Agent credit activity summary
SELECT 
    agent_id,
    SUM(CASE WHEN event_type = 'credit_award' THEN 1 ELSE 0 END) as awards,
    SUM(CASE WHEN event_type = 'credit_burn' THEN 1 ELSE 0 END) as burns,
    SUM(CASE WHEN event_type = 'insufficient_credit' THEN 1 ELSE 0 END) as rejections
FROM events 
WHERE event_type IN ('credit_award', 'credit_burn', 'insufficient_credit')
GROUP BY agent_id
ORDER BY agent_id;
```

## Proposal Analysis

### Proposal Lifecycle

```sql
-- Proposal submissions and outcomes
SELECT event_type, agent_id, message 
FROM events 
WHERE event_type IN ('proposal_received', 'proposal_accepted', 'proposal_rejected')
ORDER BY id;

-- Proposal rejection reasons
SELECT 
    CASE 
        WHEN message LIKE '%insufficient_cp_for_stake%' THEN 'Insufficient CP'
        WHEN message LIKE '%already_submitted%' THEN 'Already Submitted'
        WHEN message LIKE '%not_assigned%' THEN 'Not Assigned'
        WHEN message LIKE '%no_active_issue%' THEN 'No Active Issue'
        WHEN message LIKE '%wrong_issue_id%' THEN 'Wrong Issue ID'
        ELSE 'Other'
    END as rejection_reason,
    COUNT(*) as count
FROM events 
WHERE event_type = 'proposal_rejected'
GROUP BY rejection_reason;
```

## Phase and Timing Analysis

### Phase Transitions

```sql
-- Phase transitions
SELECT tick, phase, message 
FROM events 
WHERE event_type = 'phase_transition' 
ORDER BY tick;

-- Phase timeouts
SELECT tick, phase, message 
FROM events 
WHERE event_type = 'phase_timeout' 
ORDER BY tick;
```

### Agent Readiness

```sql
-- Agent ready signals
SELECT agent_id, COUNT(*) as ready_count
FROM events 
WHERE event_type = 'agent_ready'
GROUP BY agent_id
ORDER BY ready_count DESC;
```

## System Events

### Consensus Management

```sql
-- Consensus initialization and completion
SELECT event_type, message 
FROM events 
WHERE event_type IN ('credit_manager_init', 'consensus_tick')
ORDER BY id;
```

## Debugging Queries

### Event Timeline

```sql
-- Full event timeline for debugging
SELECT id, tick, phase, agent_id, event_type, message 
FROM events 
ORDER BY id;

-- Events for specific agent
SELECT id, tick, phase, event_type, message 
FROM events 
WHERE agent_id = 'Agent_0' 
ORDER BY id;

-- Events by tick range
SELECT tick, agent_id, event_type, message 
FROM events 
WHERE tick BETWEEN 10 AND 20 
ORDER BY tick, id;
```

### Error Analysis

```sql
-- All warning/error events
SELECT event_type, agent_id, message 
FROM events 
WHERE event_type IN ('proposal_rejected', 'insufficient_credit', 'phase_timeout')
ORDER BY id;
```

## Useful Commands

```bash
# Connect to most recent database
sqlite3 "$(ls -t db/*.sqlite3 | head -1)"

# Run query from command line
sqlite3 db/FILENAME.sqlite3 "SELECT COUNT(*) FROM events;"

# Export query results to CSV
sqlite3 -header -csv db/FILENAME.sqlite3 "SELECT * FROM events;" > export.csv
```

## Analysis Examples

### Sprint Validation: Proposal Staking

```sql
-- Verify proposal staking implementation
SELECT 
    'Stake Events' as metric,
    COUNT(*) as count
FROM events 
WHERE event_type = 'stake_recorded'
UNION ALL
SELECT 
    'Credit Burns for Stakes' as metric,
    COUNT(*) as count
FROM events 
WHERE event_type = 'credit_burn' AND message LIKE '%Proposal Self Stake%'
UNION ALL
SELECT 
    'Insufficient CP Rejections' as metric,
    COUNT(*) as count
FROM events 
WHERE event_type = 'insufficient_credit';
```

This should show equal counts for stake events and credit burns, proving the staking mechanism is working correctly.

## Conviction-Based Staking Analysis (STAKE-3)

### Conviction Growth and Multipliers

```sql
-- All conviction updates with multiplier progression
SELECT 
    agent_id,
    SUBSTR(message, INSTR(message, '→') + 2, INSTR(message, ':') - INSTR(message, '→') - 2) as proposal_id,
    CAST(SUBSTR(message, INSTR(message, ': ') + 2, INSTR(message, 'CP ×') - INSTR(message, ': ') - 2) AS INTEGER) as raw_stake,
    CAST(SUBSTR(message, INSTR(message, '× ') + 2, INSTR(message, ' =') - INSTR(message, '× ') - 2) AS REAL) as multiplier,
    CAST(SUBSTR(message, INSTR(message, '= ') + 2, INSTR(message, ' effective') - INSTR(message, '= ') - 2) AS REAL) as effective_weight,
    tick
FROM events 
WHERE event_type = 'conviction_updated'
ORDER BY agent_id, tick;

-- Average conviction multipliers by round
SELECT 
    phase,
    AVG(CAST(SUBSTR(message, INSTR(message, '× ') + 2, INSTR(message, ' =') - INSTR(message, '× ') - 2) AS REAL)) as avg_multiplier,
    COUNT(*) as conviction_count
FROM events 
WHERE event_type = 'conviction_updated'
GROUP BY phase
ORDER BY phase;

-- Top conviction builders (highest multipliers achieved)
SELECT 
    agent_id,
    MAX(CAST(SUBSTR(message, INSTR(message, '× ') + 2, INSTR(message, ' =') - INSTR(message, '× ') - 2) AS REAL)) as max_multiplier,
    COUNT(*) as conviction_updates
FROM events 
WHERE event_type = 'conviction_updated'
GROUP BY agent_id
ORDER BY max_multiplier DESC;
```

### Conviction Switching Analysis

```sql
-- All conviction switches between proposals
SELECT agent_id, message, tick
FROM events 
WHERE event_type = 'conviction_switched'
ORDER BY agent_id, tick;

-- Agents who switched conviction support
SELECT 
    agent_id,
    COUNT(*) as switches,
    GROUP_CONCAT(DISTINCT SUBSTR(message, INSTR(message, 'from ') + 5, INSTR(message, ' to ') - INSTR(message, 'from ') - 5)) as from_proposals,
    GROUP_CONCAT(DISTINCT SUBSTR(message, INSTR(message, ' to ') + 4, INSTR(message, ' (Agent') - INSTR(message, ' to ') - 4)) as to_proposals
FROM events 
WHERE event_type = 'conviction_switched'
GROUP BY agent_id
ORDER BY switches DESC;

-- Conviction loyalty analysis (agents who never switched)
SELECT 
    agent_id,
    COUNT(DISTINCT SUBSTR(message, INSTR(message, '→') + 2, INSTR(message, ':') - INSTR(message, '→') - 2)) as proposal_count,
    COUNT(*) as total_convictions
FROM events 
WHERE event_type = 'conviction_updated'
AND agent_id NOT IN (SELECT agent_id FROM events WHERE event_type = 'conviction_switched')
GROUP BY agent_id
HAVING proposal_count = 1  -- Only supported one proposal
ORDER BY total_convictions DESC;
```

### Staking Behavior Analysis

```sql
-- Balance-aware staking patterns
SELECT 
    agent_id,
    CAST(SUBSTR(message, INSTR(message, ': ') + 2, INSTR(message, ' CP →') - INSTR(message, ': ') - 2) AS INTEGER) as stake_amount,
    SUBSTR(message, INSTR(message, '(Round ') + 7, 1) as round_number,
    tick
FROM events 
WHERE event_type = 'stake_received'
ORDER BY agent_id, round_number;

-- Staking progression by rounds
SELECT 
    SUBSTR(message, INSTR(message, '(Round ') + 7, 1) as round_number,
    AVG(CAST(SUBSTR(message, INSTR(message, ': ') + 2, INSTR(message, ' CP →') - INSTR(message, ': ') - 2) AS INTEGER)) as avg_stake,
    MIN(CAST(SUBSTR(message, INSTR(message, ': ') + 2, INSTR(message, ' CP →') - INSTR(message, ': ') - 2) AS INTEGER)) as min_stake,
    MAX(CAST(SUBSTR(message, INSTR(message, ': ') + 2, INSTR(message, ' CP →') - INSTR(message, ': ') - 2) AS INTEGER)) as max_stake,
    COUNT(*) as stake_count
FROM events 
WHERE event_type = 'stake_received'
GROUP BY round_number
ORDER BY CAST(round_number AS INTEGER);

-- Effective weight vs raw stake comparison
SELECT 
    cu.agent_id,
    cu.proposal_id,
    cu.raw_stake,
    cu.effective_weight,
    cu.multiplier,
    ROUND((cu.effective_weight - cu.raw_stake) / cu.raw_stake * 100, 2) as conviction_bonus_pct
FROM (
    SELECT 
        agent_id,
        SUBSTR(message, INSTR(message, '→') + 2, INSTR(message, ':') - INSTR(message, '→') - 2) as proposal_id,
        CAST(SUBSTR(message, INSTR(message, ': ') + 2, INSTR(message, 'CP ×') - INSTR(message, ': ') - 2) AS INTEGER) as raw_stake,
        CAST(SUBSTR(message, INSTR(message, '× ') + 2, INSTR(message, ' =') - INSTR(message, '× ') - 2) AS REAL) as multiplier,
        CAST(SUBSTR(message, INSTR(message, '= ') + 2, INSTR(message, ' effective') - INSTR(message, '= ') - 2) AS REAL) as effective_weight
    FROM events 
    WHERE event_type = 'conviction_updated'
) cu
ORDER BY conviction_bonus_pct DESC;
```

### Stake Rejection Analysis

```sql
-- Insufficient balance attempts (outlier behavior)
SELECT 
    agent_id,
    COUNT(*) as rejection_count,
    GROUP_CONCAT(DISTINCT SUBSTR(message, 1, 50)) as rejection_reasons
FROM events 
WHERE event_type = 'stake_rejected' AND message LIKE '%insufficient%'
GROUP BY agent_id
ORDER BY rejection_count DESC;

-- Rejection rate by agent (compliance analysis)
SELECT 
    sr.agent_id,
    sr.attempts,
    COALESCE(rej.rejections, 0) as rejections,
    ROUND(CAST(COALESCE(rej.rejections, 0) AS REAL) / sr.attempts * 100, 2) as rejection_rate_pct
FROM (
    SELECT agent_id, COUNT(*) as attempts
    FROM events 
    WHERE event_type = 'stake_received'
    GROUP BY agent_id
) sr
LEFT JOIN (
    SELECT agent_id, COUNT(*) as rejections
    FROM events 
    WHERE event_type = 'stake_rejected'
    GROUP BY agent_id
) rej ON sr.agent_id = rej.agent_id
ORDER BY rejection_rate_pct DESC;
```

### STAKE-3 Validation Queries

```sql
-- Verify conviction system is working
SELECT 
    'Conviction Updates' as metric,
    COUNT(*) as count
FROM events 
WHERE event_type = 'conviction_updated'
UNION ALL
SELECT 
    'Conviction Switches' as metric,
    COUNT(*) as count
FROM events 
WHERE event_type = 'conviction_switched'
UNION ALL
SELECT 
    'Unique Conviction Multipliers' as metric,
    COUNT(DISTINCT CAST(SUBSTR(message, INSTR(message, '× ') + 2, INSTR(message, ' =') - INSTR(message, '× ') - 2) AS REAL)) as count
FROM events 
WHERE event_type = 'conviction_updated'
UNION ALL
SELECT 
    'Balance-Aware Stakes' as metric,
    COUNT(*) as count
FROM events 
WHERE event_type = 'stake_received';

-- Conviction multiplier distribution
SELECT 
    CASE 
        WHEN multiplier >= 2.0 THEN '2.0+ (max conviction)'
        WHEN multiplier >= 1.5 THEN '1.5-1.99 (high conviction)'
        WHEN multiplier >= 1.2 THEN '1.2-1.49 (medium conviction)'
        ELSE '1.0-1.19 (low conviction)'
    END as conviction_tier,
    COUNT(*) as count,
    ROUND(AVG(multiplier), 3) as avg_multiplier
FROM (
    SELECT CAST(SUBSTR(message, INSTR(message, '× ') + 2, INSTR(message, ' =') - INSTR(message, '× ') - 2) AS REAL) as multiplier
    FROM events 
    WHERE event_type = 'conviction_updated'
) 
GROUP BY conviction_tier
ORDER BY avg_multiplier DESC;
```

### Enhanced Payload-Based Analysis

```sql
-- Conviction data using structured JSON payloads (when available)
SELECT 
    agent_id,
    JSON_EXTRACT(payload, '$.raw') as raw_stake,
    JSON_EXTRACT(payload, '$.multiplier') as multiplier,
    JSON_EXTRACT(payload, '$.weight') as effective_weight,
    JSON_EXTRACT(payload, '$.rounds_supported') as consecutive_rounds,
    JSON_EXTRACT(payload, '$.rounds_held') as total_rounds_held,
    JSON_EXTRACT(payload, '$.total_conviction') as total_conviction,
    tick
FROM events 
WHERE event_type = 'conviction_updated' 
AND payload IS NOT NULL
ORDER BY agent_id, tick;

-- Rounds held vs consecutive rounds analysis
SELECT 
    agent_id,
    AVG(CAST(JSON_EXTRACT(payload, '$.rounds_supported') AS REAL)) as avg_consecutive_rounds,
    AVG(CAST(JSON_EXTRACT(payload, '$.rounds_held') AS REAL)) as avg_total_rounds_held,
    COUNT(*) as conviction_updates
FROM events 
WHERE event_type = 'conviction_updated' 
AND payload IS NOT NULL
GROUP BY agent_id
ORDER BY avg_total_rounds_held DESC;

-- Conviction switching impact analysis (with payload data)
SELECT 
    cs.agent_id,
    cs.from_proposal,
    cs.to_proposal,
    JSON_EXTRACT(cs.payload, '$.previous_rounds_held') as lost_rounds,
    cu.new_consecutive_rounds,
    cu.new_multiplier
FROM (
    SELECT 
        agent_id,
        JSON_EXTRACT(payload, '$.from_proposal') as from_proposal,
        JSON_EXTRACT(payload, '$.to_proposal') as to_proposal,
        payload,
        tick
    FROM events 
    WHERE event_type = 'conviction_switched' 
    AND payload IS NOT NULL
) cs
LEFT JOIN (
    SELECT 
        agent_id,
        JSON_EXTRACT(payload, '$.rounds_supported') as new_consecutive_rounds,
        JSON_EXTRACT(payload, '$.multiplier') as new_multiplier,
        tick
    FROM events 
    WHERE event_type = 'conviction_updated' 
    AND payload IS NOT NULL
) cu ON cs.agent_id = cu.agent_id AND cu.tick > cs.tick
ORDER BY lost_rounds DESC;

-- Conviction efficiency: weight gained per CP invested
SELECT 
    agent_id,
    SUM(CAST(JSON_EXTRACT(payload, '$.raw') AS INTEGER)) as total_cp_invested,
    SUM(CAST(JSON_EXTRACT(payload, '$.weight') AS REAL)) as total_effective_weight,
    ROUND(
        SUM(CAST(JSON_EXTRACT(payload, '$.weight') AS REAL)) / 
        SUM(CAST(JSON_EXTRACT(payload, '$.raw') AS INTEGER)), 
        3
    ) as efficiency_ratio
FROM events 
WHERE event_type = 'conviction_updated' 
AND payload IS NOT NULL
GROUP BY agent_id
HAVING total_cp_invested > 0
ORDER BY efficiency_ratio DESC;
```