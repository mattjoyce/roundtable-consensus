from simlog import log_event, logger, LogEntry, EventType, LogLevel
from collections import defaultdict
import math


class CreditManager:
    """Stateless service class for managing credits and conviction on shared RoundtableState."""
    
    def __init__(self, state):
        self.state = state
        
        # Log credit manager initialization
        log_event(LogEntry(
            event_type=EventType.CREDIT_MANAGER_INIT,
            payload={
                "initial_balances": state.agent_balances,
                "total_agents": len(state.agent_balances),
                "total_credits": sum(state.agent_balances.values())
            },
            message=f"CreditManager initialized with {len(state.agent_balances)} agents and {sum(state.agent_balances.values())} total credits",
            level=LogLevel.DEBUG
        ))

    def get_balance(self, agent_id: str) -> int:
        return self.state.agent_balances.get(agent_id, 0)

    def attempt_deduct(self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str) -> bool:
        if self.get_balance(agent_id) >= amount:
            self.state.agent_balances[agent_id] -= amount
            event_data = {
                "type": "Burn",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id
            }
            self.state.credit_events.append(event_data)
            
            # Log the credit burn event
            log_event(LogEntry(
                tick=tick,
                event_type=EventType.CREDIT_BURN,
                agent_id=agent_id,
                payload={
                    "amount": amount,
                    "reason": reason,
                    "issue_id": issue_id,
                    "new_balance": self.state.agent_balances[agent_id]
                },
                message=f"Credit burned: {agent_id} -{amount} CP ({reason})"
            ))
            
            return True
        else:
            event_data = {
                "type": "InsufficientCredit",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id
            }
            self.state.credit_events.append(event_data)
            
            # Log the insufficient credit event
            log_event(LogEntry(
                tick=tick,
                event_type=EventType.INSUFFICIENT_CREDIT,
                agent_id=agent_id,
                payload={
                    "amount": amount,
                    "reason": reason,
                    "issue_id": issue_id,
                    "current_balance": self.get_balance(agent_id)
                },
                message=f"Insufficient credit: {agent_id} attempted {amount} CP but has {self.get_balance(agent_id)} CP",
                level=LogLevel.WARNING
            ))
            
            return False

    def credit(self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str):
        old_balance = self.get_balance(agent_id)
        self.state.agent_balances[agent_id] = old_balance + amount
        
        event_data = {
            "type": "Credit",
            "agent_id": agent_id,
            "amount": amount,
            "reason": reason,
            "tick": tick,
            "issue_id": issue_id
        }
        self.state.credit_events.append(event_data)
        
        # Log the credit award event
        log_event(LogEntry(
            tick=tick,
            event_type=EventType.CREDIT_AWARD,
            agent_id=agent_id,
            payload={
                "amount": amount,
                "reason": reason,
                "issue_id": issue_id,
                "old_balance": old_balance,
                "new_balance": self.state.agent_balances[agent_id]
            },
            message=f"Credit awarded: {agent_id} +{amount} CP ({reason})"
        ))

    def get_all_balances(self) -> dict:
        return dict(self.state.agent_balances)

    def get_events(self) -> list:
        return list(self.state.credit_events)

    def stake_to_proposal(self, agent_id: str, proposal_id: str, amount: int, tick: int, issue_id: str) -> bool:
        if self.attempt_deduct(agent_id, amount, "Proposal Self Stake", tick, issue_id):
            # Add stake record to ledger
            stake_record = {
                "proposal_id": proposal_id,
                "amount": amount,
                "staked_by": agent_id,
                "round": 0,  # Initial proposal stakes are round 0
                "tick": tick,
                "issue_id": issue_id,
                "stake_type": "initial"
            }
            self.state.stake_ledger.append(stake_record)
            
            log_event(LogEntry(
                tick=tick,
                event_type=EventType.STAKE_RECORDED,
                agent_id=agent_id,
                payload={
                    "proposal_id": proposal_id,
                    "amount": amount,
                    "issue_id": issue_id,
                    "stake_type": "initial"
                },
                message=f"Stake recorded: {agent_id} staked {amount} CP on {proposal_id} (Round 0, proposal_stake) - Ledger entry added"
            ))
            return True
        return False

    def transfer_stake(self, old_proposal_id: str, new_proposal_id: str, tick: int, issue_id: str) -> bool:
        """Transfer stake from old proposal to new proposal (for versioned revisions)."""
        # Find all stakes for the old proposal
        old_stakes = [record for record in self.state.stake_ledger if record["proposal_id"] == old_proposal_id]
        
        if old_stakes:
            # Update each stake record to point to new proposal
            for record in old_stakes:
                record["proposal_id"] = new_proposal_id
                record["tick"] = tick  # Update to current tick
                
                log_event(LogEntry(
                    tick=tick,
                    event_type=EventType.STAKE_TRANSFERRED,
                    agent_id=record["staked_by"],
                    payload={
                        "old_proposal_id": old_proposal_id,
                        "new_proposal_id": new_proposal_id,
                        "amount": record["amount"],
                        "issue_id": issue_id
                    },
                    message=f"Transferred stake of {record['amount']} CP from {old_proposal_id} to {new_proposal_id} (agent: {record['staked_by']})"
                ))
            
            return True
        return False

    def get_agent_stakes(self, agent_id: str, issue_id: str = None) -> list:
        """Get all stakes by a specific agent."""
        stakes = [record for record in self.state.stake_ledger if record["staked_by"] == agent_id]
        if issue_id:
            stakes = [record for record in stakes if record["issue_id"] == issue_id]
        return stakes
    
    def get_proposal_stakes(self, proposal_id: str, issue_id: str = None) -> list:
        """Get all stakes to a specific proposal."""
        stakes = [record for record in self.state.stake_ledger if record["proposal_id"] == proposal_id]
        if issue_id:
            stakes = [record for record in stakes if record["issue_id"] == issue_id]
        return stakes
    
    def get_total_stake_for_proposal(self, proposal_id: str, issue_id: str = None) -> int:
        """Get the total amount staked to a specific proposal."""
        stakes = self.get_proposal_stakes(proposal_id, issue_id)
        return sum(record["amount"] for record in stakes)
    
    def get_agent_stake_on_proposal(self, agent_id: str, proposal_id: str, issue_id: str = None) -> int:
        """Get the total amount a specific agent has staked on a specific proposal."""
        stakes = [record for record in self.state.stake_ledger 
                 if record["staked_by"] == agent_id and record["proposal_id"] == proposal_id]
        if issue_id:
            stakes = [record for record in stakes if record["issue_id"] == issue_id]
        return sum(record["amount"] for record in stakes)

    def calculate_conviction_multiplier(self, agent_id: str, proposal_id: str, conviction_params: dict) -> float:
        """Calculate conviction multiplier based on consecutive rounds and conviction parameters."""
        consecutive_rounds = self.state.conviction_rounds[agent_id][proposal_id]
        
        # Support both exponential and linear conviction calculation modes
        if "MaxMultiplier" in conviction_params and "TargetFraction" in conviction_params:
            # Exponential formula: EffectiveWeight = stake_amount × (1 + (MaxMultiplier - 1) × (1 - exp(-k × r)))
            max_multiplier = conviction_params["MaxMultiplier"]
            target_fraction = conviction_params.get("TargetFraction", 0.98)
            target_rounds = conviction_params.get("TargetRounds", 5)
            
            if consecutive_rounds == 0:
                return 1.0
                
            # Calculate k = -ln(1 - T) / R
            k = -math.log(1 - target_fraction) / target_rounds
            
            # Calculate multiplier: 1 + (MaxMultiplier - 1) × (1 - exp(-k × r))
            multiplier = 1 + (max_multiplier - 1) * (1 - math.exp(-k * consecutive_rounds))
            
        else:
            # Linear fallback: base + growth * prior_rounds
            base = conviction_params.get("base", 1.0)
            growth = conviction_params.get("growth", 0.2)
            multiplier = base + growth * consecutive_rounds
            
        return round(multiplier, 3)
    
    def get_agent_conviction_on_proposal(self, agent_id: str, proposal_id: str) -> int:
        """Get the accumulated conviction stake for an agent on a specific proposal."""
        return self.state.conviction_ledger[agent_id][proposal_id]
    
    def get_agent_current_proposal(self, agent_id: str) -> str:
        """Get the proposal the agent is currently supporting (if any)."""
        for proposal_id in self.state.conviction_ledger[agent_id]:
            if self.state.conviction_rounds[agent_id][proposal_id] > 0:
                return proposal_id
        return None
    
    def update_conviction(self, agent_id: str, proposal_id: str, stake_amount: int, 
                         conviction_params: dict, tick: int, issue_id: str) -> dict:
        """Update conviction tracking and return conviction details."""
        # No automatic switching detection - switching only happens via explicit switch_conviction() calls
        is_switching = False  # This will always be False now for regular staking
        
        # Update conviction tracking
        self.state.conviction_ledger[agent_id][proposal_id] += stake_amount
        self.state.conviction_rounds[agent_id][proposal_id] += 1
        self.state.conviction_rounds_held[agent_id][proposal_id] += 1  # Always increment total rounds held
        
        # Track original stake (first stake only)
        if self.state.original_stakes[agent_id][proposal_id] == 0:
            self.state.original_stakes[agent_id][proposal_id] = stake_amount
        
        # Calculate conviction multiplier
        multiplier = self.calculate_conviction_multiplier(agent_id, proposal_id, conviction_params)
        effective_weight = round(stake_amount * multiplier, 2)
        total_conviction = self.state.conviction_ledger[agent_id][proposal_id]
        consecutive_rounds = self.state.conviction_rounds[agent_id][proposal_id]
        
        # Log conviction update event with structured payload
        log_event(LogEntry(
            tick=tick,
            event_type=EventType.CONVICTION_UPDATED,
            agent_id=agent_id,
            payload={
                "proposal_id": proposal_id,
                "raw_stake": stake_amount,
                "multiplier": multiplier,
                "effective_weight": effective_weight,
                "total_conviction": total_conviction,
                "consecutive_rounds": consecutive_rounds,
                "issue_id": issue_id,
                "rounds_held": self.state.conviction_rounds_held[agent_id][proposal_id]
            },
            message=f"Conviction updated: {agent_id} → {proposal_id}: {stake_amount}CP × {multiplier} = {effective_weight} effective weight"
        ))
        
        return {
            "raw_stake": stake_amount,
            "multiplier": multiplier,
            "effective_weight": effective_weight,
            "total_conviction": total_conviction,
            "consecutive_rounds": consecutive_rounds,
            "switched_from": None  # Switching only happens via explicit switch_conviction() calls
        }

    #return events as a reported dict
    def get_reported_events(self) -> list:
        reported = []
        for event in self.events:
            if event["type"] == "Burn":
                reported.append({
                    "agent_id": event["agent_id"],
                    "amount": -event["amount"],
                    "reason": event["reason"],
                    "tick": event["tick"],
                    "issue_id": event["issue_id"]
                })
            elif event["type"] == "Credit":
                reported.append({
                    "agent_id": event["agent_id"],
                    "amount": event["amount"],
                    "reason": event["reason"],
                    "tick": event["tick"],
                    "issue_id": event["issue_id"]
                })
        return reported
    
    def auto_build_conviction(self, conviction_params: dict, tick: int, issue_id: str) -> int:
        """Automatically build conviction for all existing positions each round."""
        total_conviction_built = 0
        
        # Build conviction for all agents with existing positions
        for agent_id in list(self.state.conviction_ledger.keys()):
            for proposal_id in list(self.state.conviction_ledger[agent_id].keys()):
                current_conviction = self.state.conviction_ledger[agent_id][proposal_id]
                
                if current_conviction > 0:
                    # Calculate conviction growth based on multiplier
                    original_stake = self.state.original_stakes[agent_id][proposal_id]
                    current_rounds = self.state.conviction_rounds[agent_id][proposal_id]
                    
                    # Calculate what conviction should be with incremented rounds
                    incremented_rounds = current_rounds + 1
                    
                    # Temporarily increment rounds to calculate new multiplier
                    self.state.conviction_rounds[agent_id][proposal_id] = incremented_rounds
                    new_multiplier = self.calculate_conviction_multiplier(agent_id, proposal_id, conviction_params)
                    target_conviction = int(original_stake * new_multiplier)
                    
                    # Restore original rounds
                    self.state.conviction_rounds[agent_id][proposal_id] = current_rounds
                    
                    # Calculate conviction growth
                    conviction_growth = target_conviction - current_conviction
                    
                    if conviction_growth > 0:
                        # Apply conviction growth
                        self.state.conviction_ledger[agent_id][proposal_id] = target_conviction
                        self.state.conviction_rounds[agent_id][proposal_id] = incremented_rounds
                        self.state.conviction_rounds_held[agent_id][proposal_id] += 1
                        
                        total_conviction_built += conviction_growth
                        
                        log_event(LogEntry(
                            tick=tick,
                            event_type=EventType.CONVICTION_UPDATED,
                            agent_id=agent_id,
                            payload={
                                "proposal_id": proposal_id,
                                "conviction_growth": conviction_growth,
                                "new_total_conviction": target_conviction,
                                "original_stake": original_stake,
                                "new_multiplier": new_multiplier,
                                "consecutive_rounds": incremented_rounds,
                                "issue_id": issue_id,
                                "auto_build": True
                            },
                            message=f"Auto-conviction: {agent_id} → P{proposal_id}: +{conviction_growth} CP (total: {target_conviction}, ×{new_multiplier:.3f})"
                        ))
        
        if total_conviction_built > 0:
            log_event(LogEntry(
                tick=tick,
                event_type=EventType.CONVICTION_UPDATED,
                payload={
                    "total_conviction_built": total_conviction_built,
                    "issue_id": issue_id,
                    "auto_build_summary": True
                },
                message=f"Auto-built {total_conviction_built} CP conviction across all positions"
            ))
        
        return total_conviction_built
    
    def has_sufficient_conviction(self, agent_id: str, proposal_id: str, cp_amount: int) -> bool:
        """Check if agent has sufficient conviction on a proposal to withdraw the specified amount."""
        current_conviction = self.state.conviction_ledger[agent_id][proposal_id]
        return current_conviction >= cp_amount
    
    def switch_conviction(self, agent_id: str, source_proposal_id: str, target_proposal_id: str, 
                         cp_amount: int, tick: int, issue_id: str, reason: str = "strategic_switch") -> bool:
        """Move CP from one proposal to another with conviction reset penalty."""
        
        # Validate sufficient conviction on source
        if not self.has_sufficient_conviction(agent_id, source_proposal_id, cp_amount):
            return False
        
        # Store original values for logging
        source_conviction_before = self.state.conviction_ledger[agent_id][source_proposal_id]
        source_rounds_before = self.state.conviction_rounds[agent_id][source_proposal_id]
        target_conviction_before = self.state.conviction_ledger[agent_id][target_proposal_id]
        target_rounds_before = self.state.conviction_rounds[agent_id][target_proposal_id]
        
        # Withdraw CP from source proposal
        self.state.conviction_ledger[agent_id][source_proposal_id] -= cp_amount
        
        # If source conviction reaches zero, reset rounds to 0
        if self.state.conviction_ledger[agent_id][source_proposal_id] == 0:
            self.state.conviction_rounds[agent_id][source_proposal_id] = 0
            # Don't reset original_stakes - that's permanent record
        
        # Add CP to target proposal (conviction resets to base)
        self.state.conviction_ledger[agent_id][target_proposal_id] += cp_amount
        
        # Reset conviction rounds on target (penalty) - start over at 1
        self.state.conviction_rounds[agent_id][target_proposal_id] = 1
        
        # If this is first time staking on target, record original stake
        if self.state.original_stakes[agent_id][target_proposal_id] == 0:
            self.state.original_stakes[agent_id][target_proposal_id] = cp_amount
        
        # Always increment total rounds held for target
        self.state.conviction_rounds_held[agent_id][target_proposal_id] += 1
        
        # Log the switching event
        log_event(LogEntry(
            tick=tick,
            event_type=EventType.CONVICTION_SWITCHED,
            agent_id=agent_id,
            payload={
                "source_proposal_id": source_proposal_id,
                "target_proposal_id": target_proposal_id,
                "cp_amount": cp_amount,
                "reason": reason,
                "issue_id": issue_id,
                "source_conviction_before": source_conviction_before,
                "source_conviction_after": self.state.conviction_ledger[agent_id][source_proposal_id],
                "source_rounds_before": source_rounds_before,
                "source_rounds_after": self.state.conviction_rounds[agent_id][source_proposal_id],
                "target_conviction_before": target_conviction_before,
                "target_conviction_after": self.state.conviction_ledger[agent_id][target_proposal_id],
                "target_rounds_before": target_rounds_before,
                "target_rounds_after": self.state.conviction_rounds[agent_id][target_proposal_id],
            },
            message=f"Conviction switched: {agent_id} moved {cp_amount} CP from P{source_proposal_id} → P{target_proposal_id} ({reason}) - Target conviction reset"
        ))
        
        # Record in credit events for audit trail
        switch_event = {
            "type": "Switch",
            "agent_id": agent_id,
            "amount": 0,  # No CP created/destroyed
            "reason": f"Switch {cp_amount} CP from P{source_proposal_id} to P{target_proposal_id}: {reason}",
            "tick": tick,
            "issue_id": issue_id,
            "source_proposal_id": source_proposal_id,
            "target_proposal_id": target_proposal_id,
            "cp_amount": cp_amount,
            "switch_reason": reason
        }
        self.state.credit_events.append(switch_event)
        
        return True
    
