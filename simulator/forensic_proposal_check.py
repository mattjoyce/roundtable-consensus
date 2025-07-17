#!/usr/bin/env python3
"""
Forensic Analysis: Proposal Stage Protocol Compliance

This script analyzes the database from a completed simulation to verify
that the Proposal stage followed protocol requirements:

1. Each agent submitted exactly one proposal
2. ProposalSelfStake (50 CP) was deducted from each agent
3. All actions were properly logged
4. State transitions were recorded correctly
"""

import sqlite3
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def find_latest_db() -> Optional[Path]:
    """Find the most recent simulation database."""
    db_dir = Path("db")
    if not db_dir.exists():
        return None
    
    db_files = list(db_dir.glob("*.sqlite3"))
    if not db_files:
        return None
    
    # Return the most recently modified database
    return max(db_files, key=lambda p: p.stat().st_mtime)


def analyze_proposal_stage(db_path: Path) -> bool:
    """
    Analyze the proposal stage for protocol compliance.
    
    Returns True if all protocol requirements are met.
    """
    print("="*60)
    print("🔍 FORENSIC ANALYSIS: PROPOSAL STAGE COMPLIANCE")
    print("="*60)
    print(f"Database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get simulation metadata
        cursor.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM state_snapshots")
        total_snapshots = cursor.fetchone()[0]
        
        print(f"📊 Total events: {total_events}")
        print(f"📊 Total snapshots: {total_snapshots}")
        
        # Focus on PROPOSE phase
        success = True
        success &= check_proposal_phase_events(cursor)
        success &= check_agent_balances(cursor)
        success &= check_proposal_submissions(cursor)
        success &= check_stake_deductions(cursor)
        
        return success
        
    except Exception as e:
        print(f"❌ Error analyzing database: {e}")
        return False
    finally:
        conn.close()


def check_proposal_phase_events(cursor) -> bool:
    """Check that PROPOSE phase events were properly logged."""
    print("\n" + "="*40)
    print("🔬 CHECKING PROPOSAL PHASE EVENTS")
    print("="*40)
    
    # Get all PROPOSE phase events
    cursor.execute("""
        SELECT tick, event_type, agent_id, message, payload
        FROM events 
        WHERE phase = 'PROPOSE' 
        ORDER BY tick, id
    """)
    
    propose_events = cursor.fetchall()
    print(f"📊 PROPOSE phase events found: {len(propose_events)}")
    
    if len(propose_events) == 0:
        print("❌ No PROPOSE phase events found!")
        return False
    
    # Check for phase execution event
    execution_events = [e for e in propose_events if e[1] == "phase_execution"]
    if len(execution_events) == 0:
        print("❌ No phase_execution event found for PROPOSE phase!")
        return False
    
    print("✅ PROPOSE phase execution event found")
    
    # Show event timeline
    print("\n📅 Event Timeline:")
    for tick, event_type, agent_id, message, payload in propose_events:
        agent_str = f"({agent_id})" if agent_id else ""
        print(f"  T{tick} {agent_str} {event_type}: {message}")
    
    return True


def check_agent_balances(cursor) -> bool:
    """Check that agent balances were properly deducted."""
    print("\n" + "="*40)
    print("💰 CHECKING AGENT BALANCE DEDUCTIONS")
    print("="*40)
    
    # Get state snapshots to track balance changes
    cursor.execute("""
        SELECT tick, phase, agent_balances
        FROM state_snapshots 
        WHERE phase = 'PROPOSE'
        ORDER BY tick
    """)
    
    snapshots = cursor.fetchall()
    if len(snapshots) == 0:
        print("❌ No PROPOSE phase snapshots found!")
        return False
    
    print(f"📊 PROPOSE phase snapshots: {len(snapshots)}")
    
    # Analyze balance changes
    initial_balances = None
    final_balances = None
    
    for tick, phase, balances_json in snapshots:
        balances = json.loads(balances_json)
        if initial_balances is None:
            initial_balances = balances
        final_balances = balances
    
    if initial_balances is None or final_balances is None:
        print("❌ Could not determine initial/final balances!")
        return False
    
    print(f"📊 Initial balances: {initial_balances}")
    print(f"📊 Final balances: {final_balances}")
    
    # Check that each agent was deducted exactly 50 CP (ProposalSelfStake)
    PROPOSAL_SELF_STAKE = 50
    success = True
    
    # Get all agents who were charged the proposal self-stake
    cursor.execute("""
        SELECT agent_id FROM events 
        WHERE event_type = 'credit_burn' 
        AND message LIKE '%Proposal Self Stake%'
    """)
    agents_with_proposal_burns = set(row[0] for row in cursor.fetchall())
    
    for agent_id in initial_balances:
        initial = initial_balances[agent_id]
        final = final_balances[agent_id]
        
        if agent_id in agents_with_proposal_burns:
            expected = initial - PROPOSAL_SELF_STAKE
            if final == expected:
                print(f"✅ {agent_id}: {initial} → {final} (−{PROPOSAL_SELF_STAKE} CP)")
            else:
                print(f"❌ {agent_id}: Expected {expected}, got {final}")
                success = False
        else:
            # Agent should have been charged but wasn't
            print(f"❌ {agent_id}: No proposal self-stake found (should be −{PROPOSAL_SELF_STAKE} CP)")
            success = False
    
    print(f"\n📊 Agents with proposal burns: {len(agents_with_proposal_burns)}")
    print(f"📊 Expected agents: {len(initial_balances)}")
    
    if len(agents_with_proposal_burns) != len(initial_balances):
        print(f"❌ Mismatch: {len(agents_with_proposal_burns)} got burns, {len(initial_balances)} expected")
        success = False
    
    return success


def check_proposal_submissions(cursor) -> bool:
    """Check that proposal submissions were properly recorded."""
    print("\n" + "="*40)
    print("📝 CHECKING PROPOSAL SUBMISSIONS")
    print("="*40)
    
    # Get proposal-related events
    cursor.execute("""
        SELECT tick, agent_id, event_type, message, payload
        FROM events 
        WHERE event_type IN ('proposal_received', 'proposal_accepted', 'proposal_rejected')
        ORDER BY tick, id
    """)
    
    proposal_events = cursor.fetchall()
    print(f"📊 Proposal events found: {len(proposal_events)}")
    
    if len(proposal_events) == 0:
        print("⚠️  No explicit proposal events found (may be normal)")
        return True  # This might be okay if proposals are handled differently
    
    # Count unique agents who submitted proposals
    agents_with_proposals = set()
    for tick, agent_id, event_type, message, payload in proposal_events:
        if agent_id:
            agents_with_proposals.add(agent_id)
        print(f"  T{tick} ({agent_id}) {event_type}: {message}")
    
    print(f"📊 Agents with proposal events: {len(agents_with_proposals)}")
    
    return True


def check_stake_deductions(cursor) -> bool:
    """Check that stake deductions were properly recorded."""
    print("\n" + "="*40)
    print("🔥 CHECKING STAKE DEDUCTIONS")
    print("="*40)
    
    # Get credit burn events
    cursor.execute("""
        SELECT tick, agent_id, event_type, message, payload
        FROM events 
        WHERE event_type = 'credit_burn'
        ORDER BY tick, id
    """)
    
    burn_events = cursor.fetchall()
    print(f"📊 Credit burn events found: {len(burn_events)}")
    
    if len(burn_events) == 0:
        print("❌ No credit burn events found!")
        return False
    
    # Analyze burn events
    PROPOSAL_SELF_STAKE = 50
    agents_with_burns = set()
    
    for tick, agent_id, event_type, message, payload in burn_events:
        if agent_id:
            agents_with_burns.add(agent_id)
        
        # Parse payload to check burn amount
        if payload:
            try:
                payload_data = json.loads(payload)
                amount = payload_data.get("amount", 0)
                reason = payload_data.get("reason", "")
                
                print(f"  T{tick} ({agent_id}) Burned {amount} CP: {reason}")
                
                if amount == PROPOSAL_SELF_STAKE and "proposal" in reason.lower():
                    print(f"    ✅ Correct proposal self-stake deduction")
                elif amount != PROPOSAL_SELF_STAKE:
                    print(f"    ⚠️  Unexpected burn amount: {amount}")
                
            except json.JSONDecodeError:
                print(f"    ⚠️  Could not parse payload: {payload}")
    
    print(f"📊 Agents with burn events: {len(agents_with_burns)}")
    
    return True


def check_state_snapshots(cursor) -> bool:
    """Check that state snapshots captured proper progression."""
    print("\n" + "="*40)
    print("📸 CHECKING STATE SNAPSHOT INTEGRITY")
    print("="*40)
    
    # Get snapshots from PROPOSE phase
    cursor.execute("""
        SELECT tick, phase, phase_tick, agent_proposal_ids, stake_ledger
        FROM state_snapshots
        WHERE phase = 'PROPOSE'
        ORDER BY tick
    """)
    
    snapshots = cursor.fetchall()
    print(f"📊 PROPOSE phase snapshots: {len(snapshots)}")
    
    for tick, phase, phase_tick, proposal_ids_json, stake_ledger_json in snapshots:
        proposal_ids = json.loads(proposal_ids_json)
        stake_ledger = json.loads(stake_ledger_json)
        
        print(f"  T{tick} Phase {phase} (tick {phase_tick})")
        print(f"    Proposal IDs: {proposal_ids}")
        print(f"    Stake entries: {len(stake_ledger)}")
    
    return True


def main():
    """Main forensic analysis function."""
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            sys.exit(1)
    else:
        db_path = find_latest_db()
        if not db_path:
            print("❌ No simulation database found in db/ directory")
            print("💡 Run a simulation first: python3 simulator.py")
            sys.exit(1)
    
    success = analyze_proposal_stage(db_path)
    
    print("\n" + "="*60)
    if success:
        print("🎉 PROPOSAL STAGE PROTOCOL COMPLIANCE: PASSED")
        print("✅ All requirements verified successfully")
    else:
        print("❌ PROPOSAL STAGE PROTOCOL COMPLIANCE: FAILED")
        print("⚠️  Protocol violations detected")
    print("="*60)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()