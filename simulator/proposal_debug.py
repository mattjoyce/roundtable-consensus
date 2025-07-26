"""Debug output module for generating proposal markdown files with rankings and staking history."""

import os
import sqlite3
import json
from typing import Dict, List, Tuple
from simlog import logger


def load_state_from_db(db_path: str = "roundtable_state.db") -> Dict:
    """Load the final state snapshot from the database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get the latest state snapshot
        cursor.execute(
            """
            SELECT * FROM state_snapshots 
            ORDER BY tick DESC 
            LIMIT 1
        """
        )

        snapshot = cursor.fetchone()
        if not snapshot:
            raise ValueError("No state snapshots found in database")

        state_data = {
            "tick": snapshot["tick"],
            "phase": snapshot["phase"],
            "agent_proposal_ids": (
                json.loads(snapshot["agent_proposal_ids"])
                if snapshot["agent_proposal_ids"]
                else {}
            ),
            "proposals": (
                json.loads(snapshot["proposals"]) if snapshot["proposals"] else []
            ),
        }

        # Get stake ledger from stake events
        cursor.execute(
            """
            SELECT payload FROM events 
            WHERE event_type = 'stake_recorded' 
            ORDER BY tick
        """
        )

        stakes = []
        stake_rows = cursor.fetchall()
        for row in stake_rows:
            payload = json.loads(row["payload"])
            stakes.append(payload)

        state_data["stake_ledger"] = stakes

        # Get proposal weights from finalization events
        cursor.execute(
            """
            SELECT payload FROM events 
            WHERE event_type = 'finalization_decision' 
            ORDER BY tick DESC 
            LIMIT 1
        """
        )

        finalization_event = cursor.fetchone()
        if finalization_event:
            payload = json.loads(finalization_event["payload"])
            # Handle single winner format
            proposal_id = payload.get("proposal_id")
            effective_weight = payload.get("effective_weight", 0)

            if proposal_id:
                state_data["proposal_weights"] = {
                    proposal_id: {"effective_weight": effective_weight}
                }
            else:
                state_data["proposal_weights"] = {}
        else:
            state_data["proposal_weights"] = {}

        conn.close()
        return state_data

    except Exception as e:
        logger.error(f"Failed to load state from database: {e}")
        raise


def generate_proposal_debug_files(
    sim_id: str, issue_id: str, db_path: str = "roundtable_state.db"
):
    """Generate debug files for each agent's proposal with front matter and ranking."""
    try:
        # Load state from database
        state_data = load_state_from_db(db_path)

        # Create debug directory if it doesn't exist
        debug_dir = "debug"
        os.makedirs(debug_dir, exist_ok=True)

        proposal_weights = state_data.get("proposal_weights", {})
        agent_proposal_ids = state_data.get("agent_proposal_ids", {})
        proposals_list = state_data.get("proposals", [])
        stake_ledger = state_data.get("stake_ledger", [])

        # Convert proposals list to dict by proposal_id for easier lookup
        proposals = {p["proposal_id"]: p for p in proposals_list}

        # Get all unique proposal IDs from agent mappings and add default rankings
        all_proposal_ids = set(agent_proposal_ids.values())
        all_proposal_ids.discard(0)  # Remove system/no-action proposals

        if not proposal_weights and all_proposal_ids:
            # If no finalization weights, assign equal weight to all proposals
            proposal_weights = {
                pid: {"effective_weight": 1.0} for pid in all_proposal_ids
            }
            logger.info(
                "No finalization weights found, using equal ranking for all proposals"
            )
        elif not proposal_weights:
            logger.warning("No proposals found to rank")
            return

        # Create ranking from proposal weights (sorted by effective weight descending)
        if proposal_weights:
            ranked_proposals = sorted(
                proposal_weights.items(),
                key=lambda x: x[1].get("effective_weight", 0),
                reverse=True,
            )
        else:
            ranked_proposals = [
                (pid, {"effective_weight": 0}) for pid in all_proposal_ids
            ]

        # Create proposal_id to rank mapping (1-based ranking)
        proposal_ranks = {
            proposal_id: rank + 1
            for rank, (proposal_id, _) in enumerate(ranked_proposals)
        }

        # Process each agent's proposal
        for agent_id, proposal_id in agent_proposal_ids.items():
            if proposal_id in proposals:
                proposal_data = proposals[proposal_id]
                rank = proposal_ranks.get(proposal_id, len(ranked_proposals) + 1)

                # Get staking history for this agent's proposal
                agent_stakes = [
                    stake
                    for stake in stake_ledger
                    if stake.get("proposal_id") == proposal_id
                    and stake.get("issue_id") == issue_id
                ]

                # Build YAML front matter
                front_matter = "---\n"
                front_matter += f"sim_id: {sim_id}\n"
                front_matter += f"agent_id: {agent_id}\n"
                front_matter += f"proposal_id: {proposal_id}\n"
                front_matter += f"rank: {rank}\n"
                front_matter += f"final_weight: {proposal_weights.get(proposal_id, {}).get('effective_weight', 0)}\n"
                front_matter += "staking_history:\n"

                for stake in agent_stakes:
                    front_matter += (
                        f"  - tick: {stake.get('initial_tick', 'unknown')}\n"
                    )
                    front_matter += f"    amount: {stake.get('amount', 'unknown')}\n"
                    front_matter += (
                        f"    proposal_id: {stake.get('proposal_id', 'unknown')}\n"
                    )
                    front_matter += (
                        f"    stake_type: {stake.get('stake_type', 'unknown')}\n"
                    )

                front_matter += "---\n\n"

                # Get proposal content
                proposal_content = proposal_data.get("content", "No content available")

                # Combine front matter with proposal content
                content = front_matter + proposal_content

                # Write to file with naming format: <sim_id>_proposal_<agent_id>_<rank>.md
                filename = f"{sim_id}_proposal_{agent_id}_{rank}.md"
                filepath = os.path.join(debug_dir, filename)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

                logger.info(f"Generated proposal debug file: {filename}")

        logger.info(f"Completed proposal debug file generation for sim_id: {sim_id}")

    except Exception as e:
        logger.error(f"Failed to generate proposal debug files: {e}")
        raise


if __name__ == "__main__":
    # Test function - can be called directly for debugging
    import sys

    if len(sys.argv) > 1:
        sim_id = sys.argv[1]
        issue_id = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        db_path = sys.argv[3] if len(sys.argv) > 3 else "roundtable_state.db"
        generate_proposal_debug_files(sim_id, issue_id, db_path)
    else:
        print("Usage: python proposal_debug.py <sim_id> [issue_id] [db_path]")
