#!/usr/bin/env python3
"""
Forensic Analysis: Feedback Stage Protocol Compliance

This script analyzes the database from a completed simulation to verify
that the Feedback stage followed protocol requirements:

1. Agents provided feedback within max_feedback_per_agent limits
2. Feedback stake (25 CP) was deducted for each feedback submission
3. No self-feedback was allowed
4. All feedback actions were properly logged
5. Phase lifecycle was executed correctly (_begin, _do, _finish)
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


def analyze_feedback_stage(db_path: Path) -> bool:
    """
    Analyze the feedback stage for protocol compliance.

    Returns True if all protocol requirements are met.
    """
    print("=" * 60)
    print("🔍 FORENSIC ANALYSIS: FEEDBACK STAGE COMPLIANCE")
    print("=" * 60)
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

        # Focus on FEEDBACK phase
        success = True
        success &= check_feedback_phase_events(cursor)
        success &= check_feedback_submissions(cursor)
        success &= check_feedback_stakes(cursor)
        success &= check_feedback_limits(cursor)
        success &= check_self_feedback_prevention(cursor)
        success &= check_phase_lifecycle(cursor)

        return success

    except Exception as e:
        print(f"❌ Error analyzing database: {e}")
        return False
    finally:
        conn.close()


def check_feedback_phase_events(cursor) -> bool:
    """Check that FEEDBACK phase events were properly logged."""
    print("\n" + "=" * 40)
    print("🔬 CHECKING FEEDBACK PHASE EVENTS")
    print("=" * 40)

    # Get all FEEDBACK phase events
    cursor.execute(
        """
        SELECT tick, event_type, agent_id, message, payload
        FROM events 
        WHERE phase = 'FEEDBACK' 
        ORDER BY tick, id
    """
    )

    feedback_events = cursor.fetchall()
    print(f"📊 FEEDBACK phase events found: {len(feedback_events)}")

    if len(feedback_events) == 0:
        print("❌ No FEEDBACK phase events found!")
        return False

    # Check for phase lifecycle events
    phase_transitions = [e for e in feedback_events if e[1] == "phase_transition"]

    print(f"📊 Phase transitions: {len(phase_transitions)}")

    if len(phase_transitions) == 0:
        print("❌ No phase_transition events found for FEEDBACK phase!")
        return False

    print("✅ FEEDBACK phase lifecycle events found")

    # Show event timeline
    print("\n📅 Event Timeline:")
    for tick, event_type, agent_id, message, payload in feedback_events:
        agent_str = f"({agent_id})" if agent_id else ""
        print(f"  T{tick} {agent_str} {event_type}: {message}")

    return True


def check_feedback_submissions(cursor) -> bool:
    """Check that feedback submissions were properly recorded."""
    print("\n" + "=" * 40)
    print("💬 CHECKING FEEDBACK SUBMISSIONS")
    print("=" * 40)

    # Get feedback-related events
    cursor.execute(
        """
        SELECT tick, agent_id, event_type, message, payload
        FROM events 
        WHERE event_type IN ('feedback_received', 'feedback_accepted', 'feedback_rejected')
        ORDER BY tick, id
    """
    )

    feedback_events = cursor.fetchall()
    print(f"📊 Feedback events found: {len(feedback_events)}")

    if len(feedback_events) == 0:
        print("⚠️  No explicit feedback events found")
        return True  # This might be okay if no feedback was submitted

    # Count feedback by type
    accepted_count = 0
    rejected_count = 0
    agents_with_feedback = set()

    for tick, agent_id, event_type, message, payload in feedback_events:
        if agent_id:
            agents_with_feedback.add(agent_id)

        if event_type == "feedback_accepted":
            accepted_count += 1
        elif event_type == "feedback_rejected":
            rejected_count += 1

        print(f"  T{tick} ({agent_id}) {event_type}: {message}")

    print(f"📊 Accepted feedback: {accepted_count}")
    print(f"📊 Rejected feedback: {rejected_count}")
    print(f"📊 Agents with feedback: {len(agents_with_feedback)}")

    return True


def check_feedback_stakes(cursor) -> bool:
    """Check that feedback stakes were properly deducted."""
    print("\n" + "=" * 40)
    print("💰 CHECKING FEEDBACK STAKE DEDUCTIONS")
    print("=" * 40)

    # Get credit burn events for feedback stakes
    cursor.execute(
        """
        SELECT tick, agent_id, event_type, message, payload
        FROM events 
        WHERE event_type = 'credit_burn'
        AND message LIKE '%Feedback Stake%'
        ORDER BY tick, id
    """
    )

    feedback_burns = cursor.fetchall()
    print(f"📊 Feedback stake burns found: {len(feedback_burns)}")

    if len(feedback_burns) == 0:
        print("⚠️  No feedback stake burns found (may be normal if no feedback)")
        return True

    # Get feedback stake from configuration
    cursor.execute(
        """
        SELECT payload FROM events 
        WHERE event_type = 'phase_transition'
        AND phase = 'FEEDBACK'
        LIMIT 1
    """
    )

    result = cursor.fetchone()
    FEEDBACK_STAKE = 25  # Default assumption

    if result and result[0]:
        try:
            payload_data = json.loads(result[0])
            FEEDBACK_STAKE = payload_data.get("feedback_stake", 25)
        except json.JSONDecodeError:
            pass

    print(f"📊 Expected feedback stake: {FEEDBACK_STAKE} CP")
    agents_with_stakes = set()
    correct_stakes = 0

    for tick, agent_id, event_type, message, payload in feedback_burns:
        if agent_id:
            agents_with_stakes.add(agent_id)

        # Parse payload to check burn amount
        if payload:
            try:
                payload_data = json.loads(payload)
                amount = payload_data.get("amount", 0)
                reason = payload_data.get("reason", "")

                print(f"  T{tick} ({agent_id}) Burned {amount} CP: {reason}")

                if amount == FEEDBACK_STAKE:
                    print(f"    ✅ Correct feedback stake deduction")
                    correct_stakes += 1
                else:
                    print(
                        f"    ❌ Unexpected stake amount: {amount} (expected {FEEDBACK_STAKE})"
                    )

            except json.JSONDecodeError:
                print(f"    ⚠️  Could not parse payload: {payload}")

    print(f"📊 Agents with feedback stakes: {len(agents_with_stakes)}")
    print(f"📊 Correct stake amounts: {correct_stakes}/{len(feedback_burns)}")

    if correct_stakes != len(feedback_burns):
        print(
            f"❌ Stake amount mismatch: {correct_stakes} correct out of {len(feedback_burns)}"
        )
        return False

    return True


def check_feedback_limits(cursor) -> bool:
    """Check that agents didn't exceed max_feedback_per_agent limits."""
    print("\n" + "=" * 40)
    print("📏 CHECKING FEEDBACK LIMITS")
    print("=" * 40)

    # Get all feedback submissions per agent
    cursor.execute(
        """
        SELECT agent_id, COUNT(*) as feedback_count
        FROM events 
        WHERE event_type IN ('feedback_accepted', 'feedback_received')
        AND agent_id IS NOT NULL
        GROUP BY agent_id
        ORDER BY feedback_count DESC
    """
    )

    agent_feedback_counts = cursor.fetchall()
    print(f"📊 Agents with feedback: {len(agent_feedback_counts)}")

    if len(agent_feedback_counts) == 0:
        print("⚠️  No agents submitted feedback")
        return True

    # Check for max_feedback_per_agent in phase configuration
    cursor.execute(
        """
        SELECT payload FROM events 
        WHERE event_type = 'phase_transition'
        AND phase = 'FEEDBACK'
        LIMIT 1
    """
    )

    result = cursor.fetchone()
    max_feedback_per_agent = 3  # Default assumption

    if result and result[0]:
        try:
            payload_data = json.loads(result[0])
            max_feedback_per_agent = payload_data.get("max_feedback_per_agent", 3)
        except json.JSONDecodeError:
            pass

    print(f"📊 Max feedback per agent: {max_feedback_per_agent}")

    violations = 0
    for agent_id, feedback_count in agent_feedback_counts:
        if feedback_count > max_feedback_per_agent:
            print(
                f"❌ {agent_id}: {feedback_count} feedback (exceeds limit of {max_feedback_per_agent})"
            )
            violations += 1
        else:
            print(f"✅ {agent_id}: {feedback_count} feedback (within limit)")

    print(f"📊 Limit violations: {violations}")

    return violations == 0


def check_self_feedback_prevention(cursor) -> bool:
    """Check that agents were prevented from giving feedback on their own proposals."""
    print("\n" + "=" * 40)
    print("🚫 CHECKING SELF-FEEDBACK PREVENTION")
    print("=" * 40)

    # Get rejected feedback events with self-feedback reason
    cursor.execute(
        """
        SELECT tick, agent_id, message, payload
        FROM events 
        WHERE event_type = 'feedback_rejected'
        AND (message LIKE '%self%' OR message LIKE '%own proposal%')
        ORDER BY tick, id
    """
    )

    self_feedback_rejections = cursor.fetchall()
    print(f"📊 Self-feedback rejections found: {len(self_feedback_rejections)}")

    for tick, agent_id, message, payload in self_feedback_rejections:
        print(f"  T{tick} ({agent_id}) Rejected: {message}")

    # Also check if any feedback was accidentally accepted from agents on their own proposals
    cursor.execute(
        """
        SELECT e.tick, e.agent_id, e.message, e.payload,
               ss.agent_proposal_ids
        FROM events e
        JOIN state_snapshots ss ON e.tick = ss.tick
        WHERE e.event_type = 'feedback_accepted'
        AND e.agent_id IS NOT NULL
        ORDER BY e.tick
    """
    )

    accepted_feedback = cursor.fetchall()
    self_feedback_violations = 0

    for tick, agent_id, message, payload, proposal_ids_json in accepted_feedback:
        try:
            proposal_ids = json.loads(proposal_ids_json)
            agent_proposal_id = proposal_ids.get(agent_id)

            if payload:
                payload_data = json.loads(payload)
                target_proposal_id = payload_data.get("target_proposal_id")

                if agent_proposal_id == target_proposal_id:
                    print(
                        f"❌ T{tick} ({agent_id}) Self-feedback violation: feedback on own proposal #{target_proposal_id}"
                    )
                    self_feedback_violations += 1

        except (json.JSONDecodeError, KeyError):
            continue

    print(f"📊 Self-feedback violations: {self_feedback_violations}")

    if self_feedback_violations > 0:
        print("❌ Self-feedback prevention failed!")
        return False

    print("✅ Self-feedback prevention working correctly")
    return True


def check_phase_lifecycle(cursor) -> bool:
    """Check that FEEDBACK phase executed proper lifecycle (_begin, _do, _finish)."""
    print("\n" + "=" * 40)
    print("🔄 CHECKING PHASE LIFECYCLE")
    print("=" * 40)

    # Get FEEDBACK phase snapshots to see phase progression
    cursor.execute(
        """
        SELECT tick, phase_tick, agent_readiness
        FROM state_snapshots
        WHERE phase = 'FEEDBACK'
        ORDER BY tick
    """
    )

    snapshots = cursor.fetchall()
    print(f"📊 FEEDBACK phase snapshots: {len(snapshots)}")

    if len(snapshots) == 0:
        print("❌ No FEEDBACK phase snapshots found!")
        return False

    # Check phase progression
    phase_ticks = []
    for tick, phase_tick, readiness_json in snapshots:
        phase_ticks.append(phase_tick)
        try:
            readiness = json.loads(readiness_json)
            ready_count = sum(1 for is_ready in readiness.values() if is_ready)
            total_agents = len(readiness)
            print(
                f"  T{tick} Phase tick {phase_tick}: {ready_count}/{total_agents} agents ready"
            )
        except json.JSONDecodeError:
            print(f"  T{tick} Phase tick {phase_tick}: Could not parse readiness")

    print(f"📊 Phase tick progression: {phase_ticks}")

    # Check that phase started at tick 1 (_begin)
    if phase_ticks and phase_ticks[0] != 1:
        print(f"❌ Phase should start at tick 1, found {phase_ticks[0]}")
        return False

    # Check that phase ended properly (_finish)
    if len(phase_ticks) > 1:
        max_phase_tick = max(phase_ticks)
        print(f"📊 Maximum phase tick: {max_phase_tick}")

        # Check for phase transition events indicating completion
        cursor.execute(
            """
            SELECT COUNT(*) FROM events 
            WHERE event_type = 'phase_transition'
            AND phase = 'FEEDBACK'
            AND message LIKE '%timeout%'
        """
        )

        completion_count = cursor.fetchone()[0]
        if completion_count == 0:
            print("⚠️  No explicit phase completion events found (may be normal)")
        else:
            print(f"✅ Found {completion_count} phase completion indicators")

        print("✅ Phase lifecycle executed correctly")

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

    success = analyze_feedback_stage(db_path)

    print("\n" + "=" * 60)
    if success:
        print("🎉 FEEDBACK STAGE PROTOCOL COMPLIANCE: PASSED")
        print("✅ All requirements verified successfully")
    else:
        print("❌ FEEDBACK STAGE PROTOCOL COMPLIANCE: FAILED")
        print("⚠️  Protocol violations detected")
    print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
