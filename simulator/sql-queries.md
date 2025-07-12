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