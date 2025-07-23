from simlog import log_event, logger, LogEntry, EventType, LogLevel
from collections import defaultdict
import math


class CreditManager:
    """Stateless service class for managing credits and conviction on shared RoundtableState."""

    def __init__(self, state):
        self.state = state

        # Log credit manager initialization
        log_event(
            LogEntry(
                event_type=EventType.CREDIT_MANAGER_INIT,
                payload={
                    "initial_balances": state.agent_balances,
                    "total_agents": len(state.agent_balances),
                    "total_credits": sum(state.agent_balances.values()),
                },
                message=f"CreditManager initialized with {len(state.agent_balances)} agents and {sum(state.agent_balances.values())} total credits",
                level=LogLevel.DEBUG,
            )
        )

    def get_balance(self, agent_id: str) -> int:
        return self.state.agent_balances.get(agent_id, 0)

    def attempt_deduct(
        self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str
    ) -> bool:
        if self.get_balance(agent_id) >= amount:
            self.state.agent_balances[agent_id] -= amount
            event_data = {
                "type": "Burn",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id,
            }
            self.state.credit_events.append(event_data)

            # Log the credit burn event
            log_event(
                LogEntry(
                    tick=tick,
                    event_type=EventType.CREDIT_BURN,
                    agent_id=agent_id,
                    payload={
                        "amount": amount,
                        "reason": reason,
                        "issue_id": issue_id,
                        "new_balance": self.state.agent_balances[agent_id],
                    },
                    message=f"Credit burned: {agent_id} -{amount} CP ({reason})",
                )
            )

            return True
        else:
            event_data = {
                "type": "InsufficientCredit",
                "agent_id": agent_id,
                "amount": amount,
                "reason": reason,
                "tick": tick,
                "issue_id": issue_id,
            }
            self.state.credit_events.append(event_data)

            # Log the insufficient credit event
            log_event(
                LogEntry(
                    tick=tick,
                    event_type=EventType.INSUFFICIENT_CREDIT,
                    agent_id=agent_id,
                    payload={
                        "amount": amount,
                        "reason": reason,
                        "issue_id": issue_id,
                        "current_balance": self.get_balance(agent_id),
                    },
                    message=f"Insufficient credit: {agent_id} attempted {amount} CP but has {self.get_balance(agent_id)} CP",
                    level=LogLevel.WARNING,
                )
            )

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
            "issue_id": issue_id,
        }
        self.state.credit_events.append(event_data)

        # Log the credit award event
        log_event(
            LogEntry(
                tick=tick,
                event_type=EventType.CREDIT_AWARD,
                agent_id=agent_id,
                payload={
                    "amount": amount,
                    "reason": reason,
                    "issue_id": issue_id,
                    "old_balance": old_balance,
                    "new_balance": self.state.agent_balances[agent_id],
                },
                message=f"Credit awarded: {agent_id} +{amount} CP ({reason})",
            )
        )

    def get_all_balances(self) -> dict:
        return dict(self.state.agent_balances)

    def get_events(self) -> list:
        return list(self.state.credit_events)

    def stake_credits(
        self, agent_id: str, amount: int, reason: str, tick: int, issue_id: str
    ) -> bool:
        """Remove credits from agent balance for staking (not burning - can be recovered)."""
        if self.get_balance(agent_id) >= amount:
            self.state.agent_balances[agent_id] -= amount

            # Log the staking event (different from burning)
            log_event(
                LogEntry(
                    tick=tick,
                    event_type=EventType.CREDIT_BURN,  # Using same event type but different reason
                    agent_id=agent_id,
                    payload={
                        "amount": amount,
                        "reason": reason,
                        "issue_id": issue_id,
                        "new_balance": self.state.agent_balances[agent_id],
                        "staked": True,  # Flag to indicate this is staking, not burning
                    },
                    message=f"Credits staked: {agent_id} -{amount} CP ({reason})",
                )
            )

            return True
        else:
            # Log insufficient credit event
            log_event(
                LogEntry(
                    tick=tick,
                    event_type=EventType.INSUFFICIENT_CREDIT,
                    agent_id=agent_id,
                    payload={
                        "amount": amount,
                        "reason": reason,
                        "issue_id": issue_id,
                        "current_balance": self.get_balance(agent_id),
                    },
                    message=f"Insufficient credit for staking: {agent_id} attempted {amount} CP but has {self.get_balance(agent_id)} CP",
                    level=LogLevel.WARNING,
                )
            )

            return False

    def stake_to_proposal(
        self, agent_id: str, proposal_id: str, amount: int, tick: int, issue_id: str
    ) -> bool:
        """Create mandatory self-stake at proposal submission tick."""
        from models import StakeRecord

        if self.stake_credits(agent_id, amount, "Proposal Self Stake", tick, issue_id):
            # Create mandatory stake record at actual proposal submission tick
            stake_record = StakeRecord(
                agent_id=agent_id,
                proposal_id=int(proposal_id),
                cp=amount,
                initial_tick=tick,  # Use actual tick when proposal is submitted
                status="active",
                issue_id=issue_id,
                mandatory=True,  # Self-stakes are mandatory
            )
            self.state.stake_ledger.append(stake_record)

            log_event(
                LogEntry(
                    tick=tick,
                    event_type=EventType.STAKE_RECORDED,
                    agent_id=agent_id,
                    payload={
                        "proposal_id": proposal_id,
                        "amount": amount,
                        "issue_id": issue_id,
                        "stake_type": "mandatory",
                        "stake_id": stake_record.stake_id,
                        "initial_tick": tick,
                    },
                    message=f"Mandatory stake recorded: {agent_id} staked {amount} CP on P{proposal_id} (tick={tick}, recoverable until finalize)",
                )
            )
            return True
        return False

    def create_voluntary_stake(
        self, agent_id: str, proposal_id: int, amount: int, tick: int, issue_id: str
    ) -> bool:
        """Create voluntary stake during stake phases (initial_tick = current tick)."""
        from models import StakeRecord

        if self.stake_credits(agent_id, amount, "Voluntary Stake", tick, issue_id):
            # Create voluntary stake record at current tick
            stake_record = StakeRecord(
                agent_id=agent_id,
                proposal_id=proposal_id,
                cp=amount,
                initial_tick=tick,  # Voluntary stakes use current tick
                status="active",
                issue_id=issue_id,
                mandatory=False,  # Voluntary stakes are not mandatory
            )
            self.state.stake_ledger.append(stake_record)

            log_event(
                LogEntry(
                    tick=tick,
                    event_type=EventType.STAKE_RECORDED,
                    agent_id=agent_id,
                    payload={
                        "proposal_id": proposal_id,
                        "amount": amount,
                        "issue_id": issue_id,
                        "stake_type": "voluntary",
                        "stake_id": stake_record.stake_id,
                        "initial_tick": tick,
                    },
                    message=f"Voluntary stake recorded: {agent_id} staked {amount} CP on P{proposal_id} (tick={tick}, switchable, recoverable until finalize)",
                )
            )
            return True
        return False

    def transfer_stake(
        self, old_proposal_id: str, new_proposal_id: str, tick: int, issue_id: str
    ) -> bool:
        """Transfer stake from old proposal to new proposal (for versioned revisions)."""
        # Find all stakes for the old proposal
        old_stakes = [
            record
            for record in self.state.stake_ledger
            if record.proposal_id == old_proposal_id
        ]

        if old_stakes:
            # Update each stake record to point to new proposal
            for record in old_stakes:
                record.proposal_id = new_proposal_id
                record.initial_tick = tick  # Update to current tick

                log_event(
                    LogEntry(
                        tick=tick,
                        event_type=EventType.STAKE_TRANSFERRED,
                        agent_id=record.agent_id,
                        payload={
                            "old_proposal_id": old_proposal_id,
                            "new_proposal_id": new_proposal_id,
                            "amount": record.cp,
                            "issue_id": issue_id,
                        },
                        message=f"Transferred stake of {record.cp} CP from {old_proposal_id} to {new_proposal_id} (agent: {record.agent_id})",
                    )
                )

            return True
        return False

    def get_agent_stakes(self, agent_id: str, issue_id: str = None) -> list:
        """Get all stakes by a specific agent."""
        stakes = [
            record for record in self.state.stake_ledger if record.agent_id == agent_id
        ]
        if issue_id:
            stakes = [record for record in stakes if record.issue_id == issue_id]
        return stakes

    def get_proposal_stakes(self, proposal_id: str, issue_id: str = None) -> list:
        """Get all stakes to a specific proposal."""
        stakes = [
            record
            for record in self.state.stake_ledger
            if record.proposal_id == proposal_id
        ]
        if issue_id:
            stakes = [record for record in stakes if record.issue_id == issue_id]
        return stakes

    def get_total_stake_for_proposal(
        self, proposal_id: str, issue_id: str = None
    ) -> int:
        """Get the total amount staked to a specific proposal."""
        stakes = self.get_proposal_stakes(proposal_id, issue_id)
        return sum(record.cp for record in stakes)

    def get_agent_stake_on_proposal(
        self, agent_id: str, proposal_id: str, issue_id: str = None
    ) -> int:
        """Get the total amount a specific agent has staked on a specific proposal."""
        stakes = [
            record
            for record in self.state.stake_ledger
            if record.agent_id == agent_id and record.proposal_id == proposal_id
        ]
        if issue_id:
            stakes = [record for record in stakes if record.issue_id == issue_id]
        return sum(record.cp for record in stakes)

    def calculate_growth_curve(self, time_held: int, conviction_params: dict) -> float:
        """Calculate growth curve value based on time held according to spec."""
        if (
            "MaxMultiplier" in conviction_params
            and "TargetFraction" in conviction_params
        ):
            # Exponential formula: growth_curve(t) = 1 + (MaxMultiplier - 1) × (1 - exp(-k × t))
            max_multiplier = conviction_params["MaxMultiplier"]
            target_fraction = conviction_params.get("TargetFraction", 0.98)
            target_rounds = conviction_params.get("TargetRounds", 5)

            if time_held == 0:
                return 1.0

            # Calculate k = -ln(1 - T) / R
            k = -math.log(1 - target_fraction) / target_rounds

            # Calculate growth curve: 1 + (MaxMultiplier - 1) × (1 - exp(-k × t))
            growth_value = 1 + (max_multiplier - 1) * (1 - math.exp(-k * time_held))

        else:
            # Linear fallback: base + growth * time_held
            base = conviction_params.get("base", 1.0)
            growth = conviction_params.get("growth", 0.2)
            growth_value = base + growth * time_held

        return round(growth_value, 3)

    def calculate_stake_conviction(
        self, stake: "StakeRecord", current_tick: int, conviction_params: dict
    ) -> float:
        """Calculate conviction for a single stake: conviction(t) = cp * growth_curve(t - initial_tick)"""
        time_held = current_tick - stake.initial_tick
        growth_multiplier = self.calculate_growth_curve(time_held, conviction_params)
        return stake.cp * growth_multiplier

    def calculate_total_conviction_for_proposal(
        self, proposal_id: int, current_tick: int, conviction_params: dict
    ) -> float:
        """Calculate total conviction for a proposal by summing individual stake convictions."""
        active_stakes = self.state.get_active_stakes_for_proposal(proposal_id)
        total_conviction = sum(
            self.calculate_stake_conviction(stake, current_tick, conviction_params)
            for stake in active_stakes
        )
        return round(total_conviction, 2)

    def calculate_agent_conviction_on_proposal(
        self,
        agent_id: str,
        proposal_id: int,
        current_tick: int,
        conviction_params: dict,
    ) -> float:
        """Calculate agent's total conviction on a specific proposal."""
        agent_stakes = self.state.get_agent_stake_on_proposal(agent_id, proposal_id)
        total_conviction = sum(
            self.calculate_stake_conviction(stake, current_tick, conviction_params)
            for stake in agent_stakes
        )
        return round(total_conviction, 2)

    def get_agent_current_proposal(self, agent_id: str) -> str:
        """Get the proposal the agent is currently supporting (if any)."""
        # Get proposals that agent has active stakes on
        agent_stakes = self.state.get_active_stakes_by_agent(agent_id)
        if agent_stakes:
            # Return the most recent proposal (highest proposal_id)
            return str(max(stake.proposal_id for stake in agent_stakes))
        return None

    def calculate_stake_conviction_details(
        self,
        agent_id: str,
        proposal_id: int,
        stake_amount: int,
        conviction_params: dict,
        tick: int,
        issue_id: str,
    ) -> dict:
        """Calculate conviction details for a new stake using pure stake-based calculations."""

        # Find the stake record that was just created for this amount and tick
        # (This should be the most recent stake for this agent/proposal/tick)
        agent_stakes = self.state.get_agent_stake_on_proposal(agent_id, proposal_id)
        current_stake = None
        for stake in agent_stakes:
            if stake.cp == stake_amount and stake.initial_tick == tick:
                current_stake = stake
                break

        if not current_stake:
            # Fallback: create a temporary stake record for calculation
            from models import StakeRecord

            current_stake = StakeRecord(
                agent_id=agent_id,
                proposal_id=proposal_id,
                cp=stake_amount,
                initial_tick=tick,
                status="active",
                issue_id=issue_id,
                mandatory=False,
            )

        # Calculate conviction for this specific stake
        time_held = tick - current_stake.initial_tick
        growth_multiplier = self.calculate_growth_curve(time_held, conviction_params)
        effective_weight = round(stake_amount * growth_multiplier, 2)

        # Calculate total conviction for this agent on this proposal
        total_conviction = self.calculate_agent_conviction_on_proposal(
            agent_id, proposal_id, tick, conviction_params
        )

        # Count consecutive rounds (number of active stakes for this agent on this proposal)
        consecutive_rounds = len(agent_stakes)

        # Log conviction update event with structured payload
        log_event(
            LogEntry(
                tick=tick,
                event_type=EventType.CONVICTION_UPDATED,
                agent_id=agent_id,
                payload={
                    "proposal_id": proposal_id,
                    "raw_stake": stake_amount,
                    "multiplier": growth_multiplier,
                    "effective_weight": effective_weight,
                    "total_conviction": total_conviction,
                    "time_held": time_held,
                    "issue_id": issue_id,
                    "stake_based": True,
                },
                message=f"Stake conviction calculated: {agent_id} → P{proposal_id}: {stake_amount}CP × {growth_multiplier} = {effective_weight} effective weight (time_held={time_held})",
            )
        )

        return {
            "raw_stake": stake_amount,
            "multiplier": growth_multiplier,
            "effective_weight": effective_weight,
            "total_conviction": total_conviction,
            "consecutive_rounds": consecutive_rounds,
            "switched_from": None,
        }

    # return events as a reported dict
    def get_reported_events(self) -> list:
        reported = []
        for event in self.events:
            if event["type"] == "Burn":
                reported.append(
                    {
                        "agent_id": event["agent_id"],
                        "amount": -event["amount"],
                        "reason": event["reason"],
                        "tick": event["tick"],
                        "issue_id": event["issue_id"],
                    }
                )
            elif event["type"] == "Credit":
                reported.append(
                    {
                        "agent_id": event["agent_id"],
                        "amount": event["amount"],
                        "reason": event["reason"],
                        "tick": event["tick"],
                        "issue_id": event["issue_id"],
                    }
                )
        return reported

    def has_sufficient_conviction(
        self,
        agent_id: str,
        proposal_id: int,
        cp_amount: int,
        current_tick: int,
        conviction_params: dict,
    ) -> bool:
        """Check if agent has sufficient conviction on a proposal to withdraw the specified amount."""
        current_conviction = self.calculate_agent_conviction_on_proposal(
            agent_id, proposal_id, current_tick, conviction_params
        )
        return current_conviction >= cp_amount

    def switch_stake(
        self,
        agent_id: str,
        source_proposal_id: int,
        target_proposal_id: int,
        cp_amount: int,
        tick: int,
        issue_id: str,
        reason: str = "strategic_switch",
    ) -> bool:
        """Switch CP from source proposal to target proposal using atomic stake ledger (RFC-004)."""
        from models import StakeRecord

        # Get agent's active stakes on source proposal
        source_stakes = self.state.get_agent_stake_on_proposal(
            agent_id, source_proposal_id
        )

        # Check for mandatory stake protection (mandatory stakes cannot be switched)
        mandatory_stakes = [s for s in source_stakes if s.mandatory]
        if mandatory_stakes:
            mandatory_cp = sum(s.cp for s in mandatory_stakes)
            available_cp = sum(s.cp for s in source_stakes) - mandatory_cp
            if cp_amount > available_cp:
                return False

        # Check sufficient CP available
        total_available = sum(s.cp for s in source_stakes if not s.mandatory)
        if cp_amount > total_available:
            return False

        # Sort voluntary stakes by initial_tick (FIFO order)
        voluntary_stakes = [s for s in source_stakes if not s.mandatory]
        voluntary_stakes.sort(key=lambda x: x.initial_tick)

        # Reduce/close source stakes (FIFO)
        remaining_to_switch = cp_amount
        for stake in voluntary_stakes:
            if remaining_to_switch <= 0:
                break

            if stake.cp <= remaining_to_switch:
                # Close this stake completely
                remaining_to_switch -= stake.cp
                stake.status = "closed"
            else:
                # Partially reduce this stake
                stake.cp -= remaining_to_switch
                remaining_to_switch = 0

        # Create new stake on target proposal at current tick
        new_stake = StakeRecord(
            agent_id=agent_id,
            proposal_id=target_proposal_id,
            cp=cp_amount,
            initial_tick=tick,
            status="active",
            issue_id=issue_id,
            mandatory=False,  # Switched stakes are never mandatory
        )
        self.state.stake_ledger.append(new_stake)

        # Log the switching event
        log_event(
            LogEntry(
                tick=tick,
                event_type=EventType.CONVICTION_SWITCHED,
                agent_id=agent_id,
                payload={
                    "source_proposal_id": source_proposal_id,
                    "target_proposal_id": target_proposal_id,
                    "cp_amount": cp_amount,
                    "reason": reason,
                    "issue_id": issue_id,
                    "new_stake_id": new_stake.stake_id,
                },
                message=f"Stake switched: {agent_id} moved {cp_amount} CP from P{source_proposal_id} → P{target_proposal_id} ({reason})",
            )
        )

        # Record in credit events for audit trail
        switch_event = {
            "type": "StakeSwitch",
            "agent_id": agent_id,
            "amount": 0,  # No CP created/destroyed
            "reason": f"Switch {cp_amount} CP from P{source_proposal_id} to P{target_proposal_id}: {reason}",
            "tick": tick,
            "issue_id": issue_id,
            "source_proposal_id": source_proposal_id,
            "target_proposal_id": target_proposal_id,
            "cp_amount": cp_amount,
            "switch_reason": reason,
            "new_stake_id": new_stake.stake_id,
        }
        self.state.credit_events.append(switch_event)

        return True

    def unstake_from_proposal(
        self,
        agent_id: str,
        proposal_id: int,
        cp_amount: int,
        tick: int,
        issue_id: str,
        reason: str = "unstake",
    ) -> bool:
        """Unstake CP from a proposal and return to agent's balance (only voluntary stakes)."""

        # Get agent's active stakes on proposal
        agent_stakes = self.state.get_agent_stake_on_proposal(agent_id, proposal_id)

        # Only voluntary stakes (not mandatory) can be unstaked
        voluntary_stakes = [
            s for s in agent_stakes if not s.mandatory and s.status == "active"
        ]
        total_available = sum(s.cp for s in voluntary_stakes)

        if cp_amount > total_available:
            return False

        # Sort voluntary stakes by initial_tick (FIFO order)
        voluntary_stakes.sort(key=lambda x: x.initial_tick)

        # Reduce/close stakes (FIFO) and restore CP to balance
        remaining_to_unstake = cp_amount
        for stake in voluntary_stakes:
            if remaining_to_unstake <= 0:
                break

            if stake.cp <= remaining_to_unstake:
                # Close this stake completely
                remaining_to_unstake -= stake.cp
                stake.status = "closed"
            else:
                # Partially reduce this stake
                stake.cp -= remaining_to_unstake
                remaining_to_unstake = 0

        # Restore CP to agent's balance
        self.state.agent_balances[agent_id] += cp_amount

        # Log the unstaking event
        log_event(
            LogEntry(
                tick=tick,
                event_type=EventType.CREDIT_AWARD,  # CP returned to balance
                agent_id=agent_id,
                payload={
                    "proposal_id": proposal_id,
                    "cp_amount": cp_amount,
                    "reason": reason,
                    "issue_id": issue_id,
                    "unstake": True,
                },
                message=f"Unstaked: {agent_id} withdrew {cp_amount} CP from P{proposal_id} → balance",
            )
        )

        # Record in credit events for audit trail
        unstake_event = {
            "type": "Unstake",
            "agent_id": agent_id,
            "amount": cp_amount,
            "reason": f"Unstake {cp_amount} CP from P{proposal_id}: {reason}",
            "tick": tick,
            "issue_id": issue_id,
            "proposal_id": proposal_id,
            "cp_amount": cp_amount,
        }
        self.state.credit_events.append(unstake_event)

        return True

    def switch_conviction(
        self,
        agent_id: str,
        source_proposal_id: str,
        target_proposal_id: str,
        cp_amount: int,
        tick: int,
        issue_id: str,
        reason: str = "strategic_switch",
    ) -> bool:
        """Legacy method - redirects to new stake-based switching."""
        return self.switch_stake(
            agent_id,
            int(source_proposal_id),
            int(target_proposal_id),
            cp_amount,
            tick,
            issue_id,
            reason,
        )
