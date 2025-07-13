from loguru import logger
from collections import defaultdict
import math


class CreditManager:
    def __init__(self, initial_balances: dict):
        # Map agent_id -> current CP balance
        self.balances = dict(initial_balances)  # Make a copy
        self.events = []  # Burn / Transfer / Rejection logs
        self.proposal_stakes = {}  # proposal_id -> staked amount
        
        # Conviction tracking structures
        self.conviction_ledger = defaultdict(lambda: defaultdict(int))  # agent_id -> proposal_id -> accumulated stake
        self.conviction_rounds = defaultdict(lambda: defaultdict(int))  # agent_id -> proposal_id -> consecutive rounds
        
        # Log credit manager initialization
        logger.bind(event_dict={
            "event_type": "credit_manager_init",
            "initial_balances": initial_balances,
            "total_agents": len(initial_balances),
            "total_credits": sum(initial_balances.values())
        }).debug(f"CreditManager initialized with {len(initial_balances)} agents and {sum(initial_balances.values())} total credits")

    def get_balance(self, agent_id: str) -> int:
        return self.balances.get(agent_id, 0)

    def attempt_deduct(self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str) -> bool:
        if self.get_balance(agent_id) >= amount:
            self.balances[agent_id] -= amount
            event_data = {
                "type": "Burn",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id
            }
            self.events.append(event_data)
            
            # Log the credit burn event
            logger.bind(event_dict={
                "event_type": "credit_burn",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id,
                "new_balance": self.balances[agent_id]
            }).info(f"Credit burned: {agent_id} -{amount} CP ({reason})")
            
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
            self.events.append(event_data)
            
            # Log the insufficient credit event
            logger.bind(event_dict={
                "event_type": "insufficient_credit",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id,
                "current_balance": self.get_balance(agent_id)
            }).warning(f"Insufficient credit: {agent_id} attempted {amount} CP but has {self.get_balance(agent_id)} CP")
            
            return False

    def credit(self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str):
        old_balance = self.get_balance(agent_id)
        self.balances[agent_id] = old_balance + amount
        
        event_data = {
            "type": "Credit",
            "agent_id": agent_id,
            "amount": amount,
            "reason": reason,
            "tick": tick,
            "issue_id": issue_id
        }
        self.events.append(event_data)
        
        # Log the credit award event
        logger.bind(event_dict={
            "event_type": "credit_award",
            "agent_id": agent_id,
            "amount": amount,
            "reason": reason,
            "tick": tick,
            "issue_id": issue_id,
            "old_balance": old_balance,
            "new_balance": self.balances[agent_id]
        }).info(f"Credit awarded: {agent_id} +{amount} CP ({reason})")

    def get_all_balances(self) -> dict:
        return dict(self.balances)

    def get_events(self) -> list:
        return list(self.events)

    def stake_to_proposal(self, agent_id: str, proposal_id: str, amount: int, tick: int, issue_id: str) -> bool:
        if self.attempt_deduct(agent_id, amount, "Proposal Self Stake", tick, issue_id):
            self.proposal_stakes[proposal_id] = amount
            logger.bind(event_dict={
                "event_type": "stake_recorded",
                "agent_id": agent_id,
                "proposal_id": proposal_id,
                "amount": amount,
                "tick": tick,
                "issue_id": issue_id
            }).info(f"Staked {amount} CP from {agent_id} to proposal {proposal_id}")
            return True
        return False

    def transfer_stake(self, old_proposal_id: str, new_proposal_id: str, tick: int, issue_id: str) -> bool:
        """Transfer stake from old proposal to new proposal (for versioned revisions)."""
        if old_proposal_id in self.proposal_stakes:
            amount = self.proposal_stakes[old_proposal_id]
            # Remove stake from old proposal
            del self.proposal_stakes[old_proposal_id]
            # Add stake to new proposal
            self.proposal_stakes[new_proposal_id] = amount
            
            logger.bind(event_dict={
                "event_type": "stake_transferred",
                "old_proposal_id": old_proposal_id,
                "new_proposal_id": new_proposal_id,
                "amount": amount,
                "tick": tick,
                "issue_id": issue_id
            }).info(f"Transferred stake of {amount} CP from {old_proposal_id} to {new_proposal_id}")
            return True
        return False

    def calculate_conviction_multiplier(self, agent_id: str, proposal_id: str, conviction_params: dict) -> float:
        """Calculate conviction multiplier based on consecutive rounds and conviction parameters."""
        consecutive_rounds = self.conviction_rounds[agent_id][proposal_id]
        
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
        return self.conviction_ledger[agent_id][proposal_id]
    
    def get_agent_current_proposal(self, agent_id: str) -> str:
        """Get the proposal the agent is currently supporting (if any)."""
        for proposal_id in self.conviction_ledger[agent_id]:
            if self.conviction_rounds[agent_id][proposal_id] > 0:
                return proposal_id
        return None
    
    def update_conviction(self, agent_id: str, proposal_id: str, stake_amount: int, 
                         conviction_params: dict, tick: int, issue_id: str) -> dict:
        """Update conviction tracking and return conviction details."""
        # Check if agent is switching from another proposal
        current_proposal = self.get_agent_current_proposal(agent_id)
        is_switching = current_proposal is not None and current_proposal != proposal_id
        
        if is_switching:
            # Reset conviction on previous proposal
            self.conviction_rounds[agent_id][current_proposal] = 0
            logger.bind(event_dict={
                "event_type": "conviction_switched",
                "agent_id": agent_id,
                "from_proposal_id": current_proposal,
                "to_proposal_id": proposal_id,
                "stake_amount": stake_amount,
                "tick": tick,
                "issue_id": issue_id
            }).info(f"Agent {agent_id} switched conviction from {current_proposal} to {proposal_id}")
        
        # Update conviction tracking
        self.conviction_ledger[agent_id][proposal_id] += stake_amount
        self.conviction_rounds[agent_id][proposal_id] += 1
        
        # Calculate conviction multiplier
        multiplier = self.calculate_conviction_multiplier(agent_id, proposal_id, conviction_params)
        effective_weight = round(stake_amount * multiplier, 2)
        total_conviction = self.conviction_ledger[agent_id][proposal_id]
        consecutive_rounds = self.conviction_rounds[agent_id][proposal_id]
        
        # Log conviction update event
        logger.bind(event_dict={
            "event_type": "conviction_updated",
            "agent_id": agent_id,
            "proposal_id": proposal_id,
            "raw_stake": stake_amount,
            "multiplier": multiplier,
            "effective_weight": effective_weight,
            "total_conviction": total_conviction,
            "consecutive_rounds": consecutive_rounds,
            "tick": tick,
            "issue_id": issue_id
        }).info(f"Conviction updated: {agent_id} → {proposal_id}: {stake_amount}CP × {multiplier} = {effective_weight} effective weight")
        
        return {
            "raw_stake": stake_amount,
            "multiplier": multiplier,
            "effective_weight": effective_weight,
            "total_conviction": total_conviction,
            "consecutive_rounds": consecutive_rounds,
            "switched_from": current_proposal if is_switching else None
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