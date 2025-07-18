from models import AgentPool, GlobalConfig, RunConfig, UnifiedConfig, RoundtableState, Issue, Proposal
from models import ACTION_QUEUE
from roundtable import Consensus
from creditmanager import CreditManager
from typing import Optional
from collections import defaultdict
from simlog import log_event, logger, LogEntry, EventType, PhaseType, LogLevel


class TheBureau:
    def __init__(self, agent_pool: AgentPool):
        self.agent_pool = agent_pool
        self.config: Optional[UnifiedConfig] = None
        self.state: Optional[RoundtableState] = None
        self.creditmgr: Optional[CreditManager] = None
        self.current_consensus: Optional[Consensus] = None

    def register_issue(self, issue: Issue):
        """Register an issue to be solved by the roundtable."""
        if self.state:
            self.state.current_issue = issue
        else:
            # Store temporarily until state is initialized
            self._pending_issue = issue

    def get_next_proposal_id(self) -> int:
        """Get the next sequential proposal ID and increment counter."""
        if not self.state:
            raise RuntimeError("Bureau state not initialized")
        next_id = self.state.proposal_counter
        self.state.proposal_counter += 1
        return next_id

    def get_issue(self, issue_id: str) -> Issue:
        """Get the current issue being solved."""
        if self.state and self.state.current_issue and self.state.current_issue.issue_id == issue_id:
            return self.state.current_issue
        raise ValueError(f"Issue {issue_id} not found")

    def configure_consensus(
        self, global_config: GlobalConfig, run_config: RunConfig
    ) -> None:
        """Configure the roundtable for consensus on the registered issue."""
        
        # Create unified config
        self.config = UnifiedConfig.from_configs(global_config, run_config)
        
        # Preserve current issue from previous state if it exists
        current_issue = None
        if self.state and self.state.current_issue:
            current_issue = self.state.current_issue
        elif hasattr(self, '_pending_issue'):
            current_issue = self._pending_issue
            delattr(self, '_pending_issue')
        
        # Initialize roundtable state
        self.state = RoundtableState(
            agent_balances=self.config.get_initial_balances(),
            agent_memory={aid: {} for aid in self.config.agent_ids},
            agent_readiness={aid: False for aid in self.config.agent_ids},
            agent_proposal_ids={aid: None for aid in self.config.agent_ids},
            current_issue=current_issue
        )
        
        # Assign agents to current issue
        if self.state.current_issue:
            self.state.current_issue.agent_ids = self.config.agent_ids.copy()

        # Initialize credit manager with shared state
        self.creditmgr = CreditManager(self.state)
        
        # Award all agents initial credits
        for agent_id in self.config.agent_ids:
            self.creditmgr.credit(
                agent_id=agent_id,
                amount=self.config.assignment_award,
                reason="Initial credit for consensus run",
                tick=0,
                issue_id=self.config.issue_id,
            )

        # Create and store the Consensus instance with shared config and state
        self.current_consensus = Consensus(self.config, self.state, self.creditmgr)

        # Reset ready tracking for new consensus
        self.state.proposals_this_phase.clear()

    def run(self):
        """Run the consensus simulation until completion."""

        
        if not self.current_consensus:
            raise RuntimeError("No active consensus run.")

        if not self.state or not self.state.current_issue:
            raise RuntimeError("No active issue registered.")

        consensus = self.current_consensus

        while not consensus._is_complete():
            tick = self.state.tick
            phase = consensus.get_current_phase().phase_type

            # Log phase transitions BEFORE processing actions
            if self.state.phase_tick == 1:
                log_event(LogEntry(
                    tick=tick,
                    phase=PhaseType(phase),
                    event_type=EventType.PHASE_TRANSITION,
                    payload={
                        "phase_tick": self.state.phase_tick,
                        "issue_id": (
                            self.state.current_issue.issue_id if self.state.current_issue else None
                        ),
                    },
                    message=f"Transitioned to new phase: {consensus.get_current_phase().phase_number}"
                ))
                logger.debug(f"Phase Tick: {self.state.phase_tick}")

            self._process_pending_actions()




            # Update consensus state with current agent proposal mappings
            if self.state.current_issue:
                self.state.agent_proposal_ids = dict(
                    self.state.current_issue.agent_to_proposal_id
                )

            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.CONSENSUS_TICK,
                message="Ticking consensus...",
                level=LogLevel.DEBUG
            ))
            consensus.tick()

        return consensus._summarize_results()

    def _process_pending_actions(self):
        for action in ACTION_QUEUE.drain():
            if action.type == "submit_proposal":
                proposal = Proposal(**action.payload)
                self.receive_proposal(action.agent_id, proposal)
            elif action.type == "signal_ready":
                self.signal_ready(action.agent_id,payload={"reason":"Active Ready Signal"})
            elif action.type == "feedback":
                self.receive_feedback(action.agent_id, action.payload)
            elif action.type == "revise":
                self.receive_revision(action.agent_id, action.payload)
            elif action.type == "stake":
                self.receive_stake(action.agent_id, action.payload)

    def receive_proposal(self, agent_id: str, proposal: Proposal):
        tick = self.state.tick if self.current_consensus else 0
        phase = (
            self.state.current_phase
            if self.current_consensus
            else None
        )
        issue_id = self.state.current_issue.issue_id

        # Assign sequential proposal ID
        new_proposal_id = self.get_next_proposal_id()

        log_event(LogEntry(
            tick=tick,
            phase=PhaseType(phase),
            event_type=EventType.PROPOSAL_RECEIVED,
            agent_id=agent_id,
            payload={
                "proposal_id": new_proposal_id,
                "issue_id": proposal.issue_id,
            },
            message=f"Received proposal from {agent_id}: #{new_proposal_id} for issue {proposal.issue_id}"
        ))

        # Validation 1: Check if there's an active issue
        if not self.state.current_issue:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.PROPOSAL_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "no_active_issue",
                },
                message=f"Rejected proposal from {agent_id}: No active issue",
                level=LogLevel.WARNING
            ))
            return

        # Validation 2: Check if agent is assigned to the issue
        if not self.state.current_issue.is_assigned(agent_id):
            
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.PROPOSAL_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "not_assigned",
                    "issue_id": issue_id,
                },
                message=f"Rejected proposal from {agent_id}: Not assigned to issue {issue_id}",
                level=LogLevel.WARNING
            ))
            return

        # Validation 3: Check if agent already submitted in current PROPOSE phase
        if agent_id in self.state.proposals_this_phase:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.PROPOSAL_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "already_submitted",
                },
                message=f"Rejected proposal from {agent_id}: Already submitted in current PROPOSE phase",
                level=LogLevel.WARNING
            ))
            return

        # Validation 4: Check if proposal is for current issue
        if proposal.issue_id != self.state.current_issue.issue_id:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.PROPOSAL_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "wrong_issue_id",
                    "received_issue_id": proposal.issue_id,
                    "expected_issue_id": issue_id,
                },
                message=f"Rejected proposal from {agent_id}: Wrong issue ID (got {proposal.issue_id}, expected {issue_id})",
                level=LogLevel.WARNING
            ))
            return

        # check the agent has enough CP to stake
        if not self.creditmgr.get_balance(agent_id) >= self.config.proposal_self_stake:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.PROPOSAL_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "insufficient_cp_for_stake",
                },
                message=f"Rejected proposal from {agent_id}: Not enough CP to stake",
                level=LogLevel.WARNING
            ))
            return

        # If all validations pass, proceed with proposal acceptance
        # Update proposal with new ID system
        proposal.proposal_id = new_proposal_id
        proposal.tick = tick
        proposal.author = agent_id
        proposal.author_type = "agent"
        proposal.type = "standard"
        proposal.revision_number = 1

        # Store proposal in Issue
        self.state.current_issue.add_proposal(proposal)
        self.state.current_issue.assign_agent_to_proposal(agent_id, proposal.proposal_id)

        # Update agent's latest_proposal_id
        selected_agent = self.config.selected_agents.get(agent_id)
        if selected_agent:
            selected_agent.latest_proposal_id = new_proposal_id

        # Stake CP to proposal
        stake_success = self.creditmgr.stake_to_proposal(
            agent_id=agent_id,
            proposal_id=proposal.proposal_id,
            amount=self.config.proposal_self_stake,
            tick=tick,
            issue_id=issue_id,
        )

        # Mark agent as ready and track proposal submission
        self.signal_ready(agent_id,payload={"reason": "proposal_accepted"})
        self.state.proposals_this_phase.add(agent_id)

        log_event(LogEntry(
            tick=tick,
            phase=PhaseType(phase),
            event_type=EventType.PROPOSAL_ACCEPTED,
            agent_id=agent_id,
            payload={
            "proposal_id": proposal.proposal_id,
            "issue_id": issue_id,
            },
            message=f"Proposal accepted from {agent_id}: #{proposal.proposal_id} for issue {issue_id} at tick {tick}"
        ))

    def create_no_action_proposal(
        self, tick: int, agent_id: str, issue_id: str
    ) -> Proposal:
        proposal = Proposal(
            proposal_id=0,  # NoAction always uses ID 0
            content="Take no Action",
            agent_id=agent_id,  # Agent assigned to this proposal (backer)
            issue_id=issue_id,
            tick=tick,
            author="system",  # System is the author
            author_type="system",  # Mark as system-authored
            type="noaction",  # Mark as NoAction type
            revision_number=1,
        )
        return proposal

    def signal_ready(self, agent_id: str, payload: Optional[dict] = None):
        log_event(LogEntry(
            tick=(
            self.state.tick
            if self.current_consensus
            else 0
            ),
            phase=(
            self.state.current_phase
            if self.current_consensus
            else None
            ),
            event_type=EventType.AGENT_READY,
            agent_id=agent_id,
            payload=payload or {},
            message=f"Agent {agent_id} marked as Ready"
        ))
        self.current_consensus.set_agent_ready(agent_id)

    def receive_feedback(self, agent_id: str, payload: dict):
        """Process feedback submission with comprehensive validation."""
        target_pid = payload["target_proposal_id"]
        comment = payload["comment"]
        tick = payload["tick"]
        phase = self.state.current_phase if self.state else None
        issue_id = payload["issue_id"]

        if not self.state.current_issue or self.state.current_issue.issue_id != issue_id:
            logger.warning(f"Rejected feedback from {agent_id}: wrong or missing issue")
            return

        if not self.state.current_issue.is_assigned(agent_id):
            logger.warning(f"Rejected feedback from {agent_id}: not assigned to issue")
            return

        # Prevent self-feedback
        if self.state.current_issue.agent_to_proposal_id.get(agent_id) == target_pid:
            logger.warning(
                f"Rejected feedback from {agent_id}: cannot comment on own proposal"
            )
            return

        # Feedback limit check
        if (
            self.state.current_issue.count_feedbacks_by(agent_id)
            >= self.config.max_feedback_per_agent
        ):
            logger.warning(
                f"Rejected feedback from {agent_id}: exceeded max feedback entries"
            )
            return

        # TODO move to global config
        if len(comment) > 500:
            logger.warning(f"Rejected feedback from {agent_id}: comment too long")
            return

        # Check agent has enough CP to stake
        if not self.creditmgr.get_balance(agent_id) >= self.config.feedback_stake:
            log_event(LogEntry(
                tick=tick,
                phase=PhaseType(phase),
                event_type=EventType.FEEDBACK_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "insufficient_cp_for_stake",
                    "target_proposal_id": target_pid,
                },
                message=f"Rejected feedback from {agent_id}: Not enough CP to stake",
                level=LogLevel.WARNING
            ))
            return

        # Deduct stake
        if not self.creditmgr.attempt_deduct(
            agent_id, self.config.feedback_stake, "Feedback Stake", tick, issue_id
        ):
            logger.warning(f"Rejected feedback from {agent_id}: insufficient CP")
            return

        # Accept and record
        self.state.current_issue.add_feedback(agent_id, target_pid, comment, tick)
        
        # TODO should they be readu if they can submit other feedback
        self.signal_ready(agent_id)

        logger.info(f"Feedback from {agent_id} → {target_pid}: {comment[:40]}...")

    def receive_revision(self, agent_id: str, payload: dict):
        """Process a revision action from an agent - creates versioned proposals."""
        new_content = payload.get("new_content")
        delta = payload.get("delta")
        tick = payload.get("tick", 0)
        issue_id = payload.get("issue_id")

        # Look up agent's current proposal ID
        proposal_id = (
            self.state.current_issue.agent_to_proposal_id.get(agent_id)
            if self.state.current_issue
            else None
        )

        log_event(LogEntry(
            tick=tick,
            phase=(
            self.state.current_phase
            if self.current_consensus
            else None
            ),
            event_type=EventType.REVISION_RECEIVED,
            agent_id=agent_id,
            payload={
            "proposal_id": proposal_id,
            "delta": delta,
            "issue_id": issue_id,
            },
            message=f"Received revision from {agent_id}: #{proposal_id} (Δ={delta})"
        ))

        # Validation 1: Check if agent has a proposal to revise
        if not proposal_id:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "no_proposal_to_revise",
                },
                message=f"Rejected revision from {agent_id}: Agent has no proposal to revise",
                level=LogLevel.WARNING
            ))
            return

        # Validation 2: Check if there's an active issue
        if not self.state.current_issue or self.state.current_issue.issue_id != issue_id:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "wrong_issue",
                },
                message=f"Rejected revision from {agent_id}: Wrong or missing issue",
                level=LogLevel.WARNING
            ))
            return

        # Validation 2: Check if agent is assigned to the issue
        if not self.state.current_issue.is_assigned(agent_id):
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "not_assigned",
                },
                message=f"Rejected revision from {agent_id}: Not assigned to issue",
                level=LogLevel.WARNING
            ))
            return

        # Validation 3: Check revision delta and new content are present
        if not new_content or delta is None or delta < 0.1 or delta > 1.0:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "invalid_revision_data",
                },
                message=f"Rejected revision from {agent_id}: Invalid revision data",
                level=LogLevel.WARNING
            ))
            return

        # Calculate CP cost: cost = proposal_self_stake * delta
        cost = int(self.config.proposal_self_stake * delta)

        # Attempt to deduct CP (with automatic unstaking if needed)
        deduct_success = self.creditmgr.attempt_deduct(
            agent_id=agent_id,
            amount=cost,
            reason=f"Revision cost (Δ={delta})",
            tick=tick,
            issue_id=issue_id,
        )

        if not deduct_success:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "insufficient_cp",
                    "cost": cost,
                },
                message=f"Rejected revision from {agent_id}: Insufficient CP for cost {cost}",
                level=LogLevel.WARNING
            ))
            return

        # Find the current active proposal to revise
        old_proposal = None
        for proposal in self.state.current_issue.proposals:
            if proposal.proposal_id == proposal_id and proposal.active:
                old_proposal = proposal
                break

        if not old_proposal:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "active_proposal_not_found",
                },
                message=f"Rejected revision from {agent_id}: Active proposal #{proposal_id} not found",
                level=LogLevel.WARNING
            ))
            return

        # Validation: Check if agent is the author of the proposal
        if old_proposal.author != agent_id:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "not_proposal_author",
                    "proposal_id": proposal_id,
                    "actual_author": old_proposal.author,
                    "author_type": old_proposal.author_type,
                },
                message=f"Rejected revision from {agent_id}: Not author of proposal #{proposal_id} (author: {old_proposal.author}, type: {old_proposal.author_type})",
                level=LogLevel.WARNING
            ))
            return

        # Get next proposal ID for the revision
        new_proposal_id = self.get_next_proposal_id()
        new_revision_number = old_proposal.revision_number + 1

        # Mark old proposal as inactive
        old_proposal.active = False

        # Create new versioned proposal
        from models import Proposal

        new_proposal = Proposal(
            proposal_id=new_proposal_id,
            content=new_content,
            agent_id=agent_id,
            issue_id=issue_id,
            tick=tick,
            metadata={
                "RevisionNumber": str(new_revision_number),
                "LastRevisionDelta": str(delta),
                "origin": "revision",
            },
            active=True,
            author=old_proposal.author,  # Inherit author from original
            author_type=old_proposal.author_type,  # Inherit author type
            parent_id=proposal_id,  # Link to parent proposal
            revision_number=new_revision_number,
            type=old_proposal.type,  # Inherit type
        )

        # Add new proposal to issue
        self.state.current_issue.proposals.append(new_proposal)

        # Update agent assignment to new version
        self.state.current_issue.agent_to_proposal_id[agent_id] = new_proposal_id

        # Update agent's latest_proposal_id
        selected_agent = self.config.selected_agents.get(agent_id)
        if selected_agent:
            selected_agent.latest_proposal_id = new_proposal_id

        # Transfer stake from old to new proposal
        stake_transferred = self.creditmgr.transfer_stake(
            old_proposal_id=proposal_id,
            new_proposal_id=new_proposal_id,
            tick=tick,
            issue_id=issue_id,
        )

        if not stake_transferred:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.REVISION_WARNING,
                agent_id=agent_id,
                payload={
                    "reason": "no_stake_to_transfer",
                    "proposal_id": proposal_id,
                    "new_proposal_id": new_proposal_id,
                },
                message=f"No stake found to transfer from #{proposal_id} to #{new_proposal_id}",
                level=LogLevel.WARNING
            ))

        # Log a Revision event to the ledger with version lineage
        revision_event = {
            "type": "Revision",
            "agent_id": agent_id,
            "amount": -cost,
            "reason": f"Proposal revision (Δ={delta})",
            "tick": tick,
            "issue_id": issue_id,
            "parent_id": proposal_id,
            "new_proposal_id": new_proposal_id,
            "delta": delta,
            "revision_number": new_revision_number,
            "cp_cost": cost,
        }
        self.state.credit_events.append(revision_event)

        # Mark agent as ready
        self.signal_ready(agent_id, payload={"reason": "revision_accepted"})

        log_event(LogEntry(
            tick=tick,
            phase=(
            self.state.current_phase
            if self.current_consensus
            else None
            ),
            event_type=EventType.REVISION_ACCEPTED,
            agent_id=agent_id,
            payload={
            "parent_id": proposal_id,
            "new_proposal_id": new_proposal_id,
            "delta": delta,
            "cost": cost,
            "revision_number": new_revision_number,
            "issue_id": issue_id,
            },
            message=f"Revision accepted from {agent_id}: #{proposal_id} → #{new_proposal_id} (Δ={delta}, cost={cost}CP, rev{new_revision_number})"
        ))

    def receive_stake(self, agent_id: str, payload: dict):
        """Process a stake action from an agent - deduct CP and record stake with conviction tracking."""
        proposal_id = payload.get("proposal_id")
        stake_amount = payload.get("stake_amount")
        round_number = payload.get("round_number", 1)
        tick = payload.get("tick", 0)
        issue_id = payload.get("issue_id")
        choice_reason = payload.get("choice_reason", "unknown")

        log_event(LogEntry(
            tick=tick,
            phase=(
            self.state.current_phase
            if self.current_consensus
            else None
            ),
            event_type=EventType.STAKE_RECEIVED,
            agent_id=agent_id,
            payload={
            "proposal_id": proposal_id,
            "stake_amount": stake_amount,
            "round_number": round_number,
            "issue_id": issue_id,
            },
            message=f"Received stake from {agent_id}: {stake_amount} CP → {proposal_id} (Round {round_number})"
        ))

        # Validation 1: Check if there's an active issue
        if not self.state.current_issue or self.state.current_issue.issue_id != issue_id:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "wrong_issue",
                },
                message=f"Rejected stake from {agent_id}: Wrong or missing issue",
                level=LogLevel.WARNING
            ))
            return

        # Validation 2: Check if agent is assigned to the issue
        if not self.state.current_issue.is_assigned(agent_id):
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "not_assigned",
                },
                message=f"Rejected stake from {agent_id}: Not assigned to issue",
                level=LogLevel.WARNING
            ))
            return

        # Validation 3: Check stake amount is positive
        if not stake_amount or stake_amount <= 0:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "invalid_amount",
                },
                message=f"Rejected stake from {agent_id}: Invalid stake amount {stake_amount}",
                level=LogLevel.WARNING
            ))
            return

        # Validation 4: Check proposal_id is provided
        if not proposal_id:
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "missing_proposal_id",
                },
                message=f"Rejected stake from {agent_id}: Missing proposal ID",
                level=LogLevel.WARNING
            ))
            return

        # Validation 5: Check if agent is self-staking on their latest proposal
        agent_current_proposal = self.state.current_issue.agent_to_proposal_id.get(agent_id)
        selected_agent = self.config.selected_agents.get(agent_id)

        if (
            agent_current_proposal == proposal_id
            and selected_agent
            and selected_agent.latest_proposal_id != proposal_id
        ):
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "not_latest_proposal",
                    "proposal_id": proposal_id,
                    "latest_proposal_id": selected_agent.latest_proposal_id,
                },
                message=f"Rejected stake from {agent_id}: Can only self-stake on latest proposal (staking on #{proposal_id}, latest is #{selected_agent.latest_proposal_id})",
                level=LogLevel.WARNING
            ))
            return

        # Attempt to deduct CP
        deduct_success = self.creditmgr.attempt_deduct(
            agent_id=agent_id,
            amount=stake_amount,
            reason=f"Conviction stake (Round {round_number})",
            tick=tick,
            issue_id=issue_id,
        )

        if deduct_success:
            # Get conviction parameters from current consensus
            conviction_params = {}
            if self.current_consensus:
                conviction_params = self.config.conviction_params

            # Update conviction tracking and get conviction details
            conviction_details = self.creditmgr.update_conviction(
                agent_id=agent_id,
                proposal_id=proposal_id,
                stake_amount=stake_amount,
                conviction_params=conviction_params,
                tick=tick,
                issue_id=issue_id,
            )

            # Emit comprehensive stake_recorded event with conviction details
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_RECORDED,
                agent_id=agent_id,
                payload={
                    "proposal_id": proposal_id,
                    "stake_amount": stake_amount,
                    "round_number": round_number,
                    "choice_reason": choice_reason,
                    "conviction_multiplier": conviction_details["multiplier"],
                    "effective_weight": conviction_details["effective_weight"],
                    "total_conviction": conviction_details["total_conviction"],
                    "consecutive_rounds": conviction_details["consecutive_rounds"],
                    "switched_from": conviction_details["switched_from"],
                    "issue_id": issue_id,
                },
                message=(
                    f"Stake recorded: {agent_id} staked {stake_amount} CP on {proposal_id} "
                    f"(Round {round_number}, {choice_reason}) - Effective weight: "
                    f"{conviction_details['effective_weight']} (×{conviction_details['multiplier']})"
                )
            ))

        else:
            # Emit insufficient_credit event (already handled by attempt_deduct)
            log_event(LogEntry(
                tick=tick,
                phase=(
                    self.state.current_phase
                    if self.current_consensus
                    else None
                ),
                event_type=EventType.STAKE_REJECTED,
                agent_id=agent_id,
                payload={
                    "reason": "insufficient_credit",
                    "stake_amount": stake_amount,
                    "current_balance": self.creditmgr.get_balance(agent_id),
                },
                message=(
                    f"Rejected stake from {agent_id}: Insufficient CP "
                    f"(has {self.creditmgr.get_balance(agent_id)}, needs {stake_amount})"
                ),
                level=LogLevel.WARNING
            ))

        # Mark agent as ready (regardless of success/failure)
        self.signal_ready(agent_id,payload={"reason": "stake_received"})
