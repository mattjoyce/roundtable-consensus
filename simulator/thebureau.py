from models import AgentPool, GlobalConfig, RunConfig, Issue, Proposal
from models import ACTION_QUEUE
from roundtable import Consensus
from creditmanager import CreditManager
from typing import Optional
from loguru import logger

class TheBureau:
    def __init__(self, agent_pool: AgentPool):
        self.agent_pool = agent_pool
        self.creditmgr = CreditManager({})  # Persistent ledger across runs
        self.current_consensus = None
        initial_balances = {aid: agent.initial_balance for aid, agent in self.agent_pool.agents.items()}
        self.creditmgr = CreditManager(initial_balances=initial_balances)
        self.current_issue: Optional[Issue] = None
        self.proposals_this_phase: set = set()  # Track proposals submitted in current PROPOSE phase
        self.assigned_agents: set = set()  # Track agents assigned to the current issue

    def register_issue(self, issue: Issue):
        self.current_issue = issue

    def get_issue(self, issue_id: str) -> Issue:
        if self.current_issue and self.current_issue.issue_id == issue_id:
            return self.current_issue
        raise ValueError(f"Issue {issue_id} not found")

    def configure_consensus(self, global_config: GlobalConfig, run_config: RunConfig ) -> None:

        # Assign agents to current issue
        if self.current_issue:
            self.current_issue.agent_ids = run_config.agent_ids.copy()

        self.assigned_agents = set(run_config.agent_ids)

        #award all agents a credit
        for agent_id in self.assigned_agents:
            self.creditmgr.credit(
                agent_id=agent_id,
                amount=global_config.assignment_award,
                reason="Initial credit for consensus run",
                tick=0,
                issue_id=run_config.issue_id
            )

        # Create and store the Consensus instance
        consensus = Consensus(global_config=global_config, run_config=run_config,creditmgr=self.creditmgr)
        consensus.state["creditmgr"] = self.creditmgr
        consensus.state["config"] = global_config  # Pass full config for signal context
        self.current_consensus = consensus
        
        # Reset ready tracking for new consensus
        self.proposals_this_phase.clear()



    def run(self):
        """Run the consensus simulation until completion."""
        if not self.current_consensus:
            raise RuntimeError("No active consensus run.")

        if not self.current_issue:
            raise RuntimeError("No active issue registered.")

        consensus = self.current_consensus
        consensus.state["issue_id"] = self.current_issue.issue_id

        while not consensus._is_complete():
            self._process_pending_actions()
            if self.current_consensus.is_think_tick_over():
                current_phase = consensus.get_current_phase()
                logger.bind(event_dict={
                    "event_type": "phase_timeout",
                    "tick": consensus.state['tick'],
                    "phase": current_phase.phase_type,
                    "phase_number": current_phase.phase_number,
                    "issue_id": self.current_issue.issue_id if self.current_issue else None
                }).warning(f"Timeout {current_phase.phase_type} Phase [{current_phase.phase_number}] at tick {consensus.state['tick']}")
                unready = self.current_consensus.get_unready_agents()

                if len(unready) != 0:
                    proposal= self.create_no_action_proposal(
                        tick=self.current_consensus.state["tick"],
                        agent_id="z",
                        issue_id=self.current_issue.issue_id
                    )
                    self.current_issue.add_proposal(proposal)
                    #link unready agent to no action proposal
                    for agent_id in unready:
                        # Only PROPOSE phase requires proposal submission cost
                        if current_phase.phase_type == "PROPOSE":
                            self.creditmgr.stake_to_proposal(
                                agent_id=agent_id,
                                proposal_id=proposal.proposal_id,
                                amount=self.current_consensus.gc.proposal_self_stake,
                                tick=self.current_consensus.state["tick"],
                                issue_id=self.current_issue.issue_id
                            )
                        
                        self.current_issue.assign_agent_to_proposal(agent_id, proposal.proposal_id)
                        self.signal_ready(agent_id)



            # Log phase transitions
            if consensus.state["phase_tick"] == 1:
                logger.bind(event_dict={
                    "event_type": "phase_transition",
                    "tick": consensus.state['tick'],
                    "phase_number": consensus.get_current_phase().phase_number,
                    "phase_tick": consensus.state['phase_tick'],
                    "issue_id": self.current_issue.issue_id if self.current_issue else None
                }).info(f"Transitioned to new phase: {consensus.get_current_phase().phase_number}")
                logger.debug(f"Phase Tick: {consensus.state['phase_tick']}")
            
            logger.bind(event_dict={
                "event_type": "consensus_tick",
                "tick": consensus.state['tick']
            }).debug("Ticking consensus...")
            consensus.tick()

        return consensus._summarize_results()
    
    def _process_pending_actions(self):
        for action in ACTION_QUEUE.drain():
            if action.type == "submit_proposal":
                proposal=Proposal(**action.payload)
                self.receive_proposal(action.agent_id, proposal)
            elif action.type == "ready_signal":
                self.signal_ready(action.agent_id)
            elif action.type == "feedback":
                self.receive_feedback(action.agent_id, action.payload)
            elif action.type == "revise":
                self.receive_revision(action.agent_id, action.payload)


    def receive_proposal(self, agent_id: str, proposal: Proposal):
        logger.bind(event_dict={
            "event_type": "proposal_received",
            "agent_id": agent_id,
            "proposal_id": proposal.proposal_id,
            "issue_id": proposal.issue_id
        }).info(f"Received proposal from {agent_id}: {proposal.proposal_id} for issue {proposal.issue_id}")
        
        # Validation 1: Check if there's an active issue
        if not self.current_issue:
            logger.bind(event_dict={
                "event_type": "proposal_rejected",
                "agent_id": agent_id,
                "reason": "no_active_issue"
            }).warning(f"Rejected proposal from {agent_id}: No active issue")
            return
            
        # Validation 2: Check if agent is assigned to the issue
        if not self.current_issue.is_assigned(agent_id):
            logger.bind(event_dict={
                "event_type": "proposal_rejected",
                "agent_id": agent_id,
                "reason": "not_assigned",
                "issue_id": self.current_issue.issue_id
            }).warning(f"Rejected proposal from {agent_id}: Not assigned to issue {self.current_issue.issue_id}")
            return
            
        # Validation 3: Check if agent already submitted in current PROPOSE phase
        if agent_id in self.proposals_this_phase:
            logger.bind(event_dict={
                "event_type": "proposal_rejected",
                "agent_id": agent_id,
                "reason": "already_submitted"
            }).warning(f"Rejected proposal from {agent_id}: Already submitted in current PROPOSE phase")
            return
            
        # Validation 4: Check if proposal is for current issue
        if proposal.issue_id != self.current_issue.issue_id:
            logger.bind(event_dict={
                "event_type": "proposal_rejected",
                "agent_id": agent_id,
                "reason": "wrong_issue_id",
                "received_issue_id": proposal.issue_id,
                "expected_issue_id": self.current_issue.issue_id
            }).warning(f"Rejected proposal from {agent_id}: Wrong issue ID (got {proposal.issue_id}, expected {self.current_issue.issue_id})")
            return
        
        issue_id = self.current_issue.issue_id
        tick = self.current_consensus.state["tick"]

        #update proposal with issue ID and tick
        proposal.tick = tick
        # Store proposal in Issue 
        self.current_issue.add_proposal(proposal)
        self.current_issue.assign_agent_to_proposal(agent_id, proposal.proposal_id)
        
        # Stake CP to proposal
        stake_success = self.creditmgr.stake_to_proposal(
            agent_id=agent_id,
            proposal_id=proposal.proposal_id,
            amount=self.current_consensus.gc.proposal_self_stake,
            tick=tick,
            issue_id=issue_id
        )

        if not stake_success:
            logger.bind(event_dict={
                "event_type": "proposal_rejected",
                "agent_id": agent_id,
                "reason": "insufficient_cp_for_stake"
            }).warning(f"Rejected proposal from {agent_id}: Not enough CP to stake")
            return
        
        # Mark agent as ready and track proposal submission
        self.signal_ready(agent_id)
        self.proposals_this_phase.add(agent_id)

        logger.bind(event_dict={
            "event_type": "proposal_accepted",
            "agent_id": agent_id,
            "proposal_id": proposal.proposal_id,
            "issue_id": issue_id,
            "tick": tick
        }).info(f"Proposal accepted from {agent_id}: {proposal.proposal_id} for issue {issue_id} at tick {tick}")
        logger.bind(event_dict={
            "event_type": "agent_ready",
            "agent_id": agent_id
        }).debug(f"Agent {agent_id} marked as Ready")

    def create_no_action_proposal(self, tick: int, agent_id: str, issue_id: str) -> Proposal:
        proposal = Proposal(
            proposal_id=f"PNOACTION",  
            content="Take no Action",
            agent_id=agent_id,
            issue_id=issue_id,
            tick=tick
        )
        return proposal
    
    def signal_ready(self, agent_id: str):
        logger.bind(event_dict={
            "event_type": "agent_ready",
            "agent_id": agent_id
        }).debug(f"Agent {agent_id} marked as Ready")
        self.current_consensus.set_agent_ready(agent_id)

    def receive_feedback(self, agent_id: str, payload: dict):
        target_pid = payload["target_proposal_id"]
        comment = payload["comment"]
        tick = payload["tick"]
        issue_id = payload["issue_id"]
        
        if not self.current_issue or self.current_issue.issue_id != issue_id:
            logger.warning(f"Rejected feedback from {agent_id}: wrong or missing issue")
            return

        if not self.current_issue.is_assigned(agent_id):
            logger.warning(f"Rejected feedback from {agent_id}: not assigned to issue")
            return

        # Prevent self-feedback
        if self.current_issue.agent_to_proposal_id.get(agent_id) == target_pid:
            logger.warning(f"Rejected feedback from {agent_id}: cannot comment on own proposal")
            return

        # Feedback limit check
        if self.current_issue.count_feedbacks_by(agent_id) >= self.current_consensus.gc.max_feedback_per_agent:
            logger.warning(f"Rejected feedback from {agent_id}: exceeded max feedback entries")
            return

        if len(comment) > 500:
            logger.warning(f"Rejected feedback from {agent_id}: comment too long")
            return

        # Deduct stake
        if not self.creditmgr.attempt_deduct(agent_id, 5, "Feedback Stake", tick, issue_id):
            logger.warning(f"Rejected feedback from {agent_id}: insufficient CP")
            return

        # Accept and record
        self.current_issue.add_feedback(agent_id, target_pid, comment, tick)
        self.signal_ready(agent_id)

        logger.info(f"Feedback from {agent_id} → {target_pid}: {comment[:40]}...")

    def receive_revision(self, agent_id: str, payload: dict):
        """Process a revision action from an agent - creates versioned proposals."""
        proposal_id = payload.get("proposal_id")
        new_content = payload.get("new_content")
        delta = payload.get("delta")
        tick = payload.get("tick", 0)
        issue_id = payload.get("issue_id")
        
        logger.bind(event_dict={
            "event_type": "revision_received",
            "agent_id": agent_id,
            "proposal_id": proposal_id,
            "delta": delta,
            "issue_id": issue_id
        }).info(f"Received revision from {agent_id}: {proposal_id} (Δ={delta})")
        
        # Validation 1: Check if there's an active issue
        if not self.current_issue or self.current_issue.issue_id != issue_id:
            logger.bind(event_dict={
                "event_type": "revision_rejected",
                "agent_id": agent_id,
                "reason": "wrong_issue"
            }).warning(f"Rejected revision from {agent_id}: Wrong or missing issue")
            return
        
        # Validation 2: Check if agent is assigned to the issue
        if not self.current_issue.is_assigned(agent_id):
            logger.bind(event_dict={
                "event_type": "revision_rejected",
                "agent_id": agent_id,
                "reason": "not_assigned"
            }).warning(f"Rejected revision from {agent_id}: Not assigned to issue")
            return
        
        # Validation 3: Check if proposal is owned by agent (handle version mismatch)
        agent_proposal_id = self.current_issue.agent_to_proposal_id.get(agent_id)
        
        # If agent submitted base proposal ID but has versioned ID, use the current version
        if agent_proposal_id != proposal_id:
            # Check if the proposal_id is a base version of the agent's current proposal
            base_proposal_id = f"P{agent_id}"
            if proposal_id == base_proposal_id and agent_proposal_id and agent_proposal_id.startswith(base_proposal_id):
                # Agent submitted base ID but has versioned ID - use the versioned one
                proposal_id = agent_proposal_id
                logger.bind(event_dict={
                    "event_type": "revision_id_corrected",
                    "agent_id": agent_id,
                    "submitted_id": payload.get("proposal_id"),
                    "corrected_id": proposal_id
                }).info(f"Corrected proposal ID for {agent_id}: {payload.get('proposal_id')} → {proposal_id}")
            else:
                logger.bind(event_dict={
                    "event_type": "revision_rejected",
                    "agent_id": agent_id,
                    "reason": "not_proposal_owner",
                    "expected_proposal_id": agent_proposal_id,
                    "received_proposal_id": proposal_id
                }).warning(f"Rejected revision from {agent_id}: Not owner of proposal {proposal_id}")
                return
        
        # Validation 4: Check revision delta and new content are present
        if not new_content or delta is None or delta < 0.1 or delta > 1.0:
            logger.bind(event_dict={
                "event_type": "revision_rejected",
                "agent_id": agent_id,
                "reason": "invalid_revision_data"
            }).warning(f"Rejected revision from {agent_id}: Invalid revision data")
            return
        
        # Calculate CP cost: cost = proposal_self_stake * delta
        cost = int(self.current_consensus.gc.proposal_self_stake * delta)
        
        # Attempt to deduct CP (with automatic unstaking if needed)
        deduct_success = self.creditmgr.attempt_deduct(
            agent_id=agent_id,
            amount=cost,
            reason=f"Revision cost (Δ={delta})",
            tick=tick,
            issue_id=issue_id
        )
        
        if not deduct_success:
            logger.bind(event_dict={
                "event_type": "revision_rejected",
                "agent_id": agent_id,
                "reason": "insufficient_cp",
                "cost": cost
            }).warning(f"Rejected revision from {agent_id}: Insufficient CP for cost {cost}")
            return
        
        # Find the current active proposal to revise
        old_proposal = None
        for proposal in self.current_issue.proposals:
            if proposal.proposal_id == proposal_id and proposal.active:
                old_proposal = proposal
                break
        
        if not old_proposal:
            logger.bind(event_dict={
                "event_type": "revision_rejected",
                "agent_id": agent_id,
                "reason": "active_proposal_not_found"
            }).warning(f"Rejected revision from {agent_id}: Active proposal {proposal_id} not found")
            return
        
        # Create versioned proposal - extract base ID to avoid nested versions
        new_version = old_proposal.version + 1
        
        # Extract base proposal ID (remove any existing @vN suffix)
        if "@v" in proposal_id:
            base_proposal_id = proposal_id.split("@v")[0]
        else:
            base_proposal_id = proposal_id
            
        new_proposal_id = f"{base_proposal_id}@v{new_version}"
        
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
                "RevisionNumber": str(new_version),
                "LastRevisionDelta": str(delta),
                "origin": "revision"
            },
            version=new_version,
            parent_id=proposal_id,
            active=True
        )
        
        # Add new proposal to issue
        self.current_issue.proposals.append(new_proposal)
        
        # Update agent assignment to new version
        self.current_issue.agent_to_proposal_id[agent_id] = new_proposal_id
        
        # Transfer stake from old to new proposal
        stake_transferred = self.creditmgr.transfer_stake(
            old_proposal_id=proposal_id,
            new_proposal_id=new_proposal_id,
            tick=tick,
            issue_id=issue_id
        )
        
        if not stake_transferred:
            logger.bind(event_dict={
                "event_type": "revision_warning",
                "agent_id": agent_id,
                "reason": "no_stake_to_transfer"
            }).warning(f"No stake found to transfer from {proposal_id} to {new_proposal_id}")
        
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
            "revision_number": new_version,
            "cp_cost": cost
        }
        self.creditmgr.events.append(revision_event)
        
        # Mark agent as ready
        self.signal_ready(agent_id)
        
        logger.bind(event_dict={
            "event_type": "revision_accepted",
            "agent_id": agent_id,
            "parent_id": proposal_id,
            "new_proposal_id": new_proposal_id,
            "delta": delta,
            "cost": cost,
            "version": new_version,
            "issue_id": issue_id,
            "tick": tick
        }).info(f"Revision accepted from {agent_id}: {proposal_id} → {new_proposal_id} (Δ={delta}, cost={cost}CP)")  