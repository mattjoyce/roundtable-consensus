from loguru import logger


class CreditManager:
    def __init__(self, initial_balances: dict):
        # Map agent_id -> current CP balance
        self.balances = dict(initial_balances)  # Make a copy
        self.events = []  # Burn / Transfer / Rejection logs
        self.proposal_stakes = {}  # proposal_id -> staked amount
        
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