from models import AgentPool, GlobalConfig, RunConfig, Issue
from models import ACTION_QUEUE
from roundtable import Consensus
from creditmanager import CreditManager
from typing import Optional

class TheBureau:
    def __init__(self, agent_pool: AgentPool):
        self.agent_pool = agent_pool
        self.creditmgr = CreditManager({})  # Persistent ledger across runs
        self.current_consensus = None
        initial_balances = {aid: agent.initial_balance for aid, agent in self.agent_pool.agents.items()}
        self.creditmgr = CreditManager(initial_balances=initial_balances)
        self.current_issue: Optional[Issue] = None
        self.ready_agents: set = set()  # Track agents who submitted in current PROPOSE phase
        self.proposals_this_phase: set = set()  # Track proposals submitted in current PROPOSE phase

    def register_issue(self, issue: Issue):
        self.current_issue = issue

    def get_issue(self, issue_id: str) -> Issue:
        if self.current_issue and self.current_issue.issue_id == issue_id:
            return self.current_issue
        raise ValueError(f"Issue {issue_id} not found")

    def configure_consensus(self, global_config: GlobalConfig, run_config: RunConfig ) -> None:

        #award all agents a credit
        for agent_id in run_config.agent_ids:
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
        self.ready_agents.clear()
        self.proposals_this_phase.clear()



    def run(self):
        if not self.current_consensus:
            raise RuntimeError("No active consensus run.")

        consensus = self.current_consensus

        while not consensus._is_complete():
            self._process_pending_actions()
            consensus.tick()

        return consensus._summarize_results()
    
    def _process_pending_actions(self):
        for action in ACTION_QUEUE.drain():
            if action.type == "submit_proposal":
                self.receive_proposal(action.agent_id, action.payload)


    def receive_proposal(self, agent_id: str, proposal: dict):
        print(f"Received proposal from {agent_id}: {proposal}")
        
        # Validation 1: Check if there's an active issue
        if not self.current_issue:
            print(f"Rejected proposal from {agent_id}: No active issue")
            return
            
        # Validation 2: Check if agent is assigned to the issue
        if not self.current_issue.is_assigned(agent_id):
            print(f"Rejected proposal from {agent_id}: Not assigned to issue {self.current_issue.issue_id}")
            return
            
        # Validation 3: Check if agent already submitted in current PROPOSE phase
        if agent_id in self.proposals_this_phase:
            print(f"Rejected proposal from {agent_id}: Already submitted in current PROPOSE phase")
            return
            
        # Validation 4: Check if proposal is for current issue
        proposal_issue_id = proposal.get("parent_issue_id") or proposal.get("issue_id")
        if proposal_issue_id != self.current_issue.issue_id:
            print(f"Rejected proposal from {agent_id}: Wrong issue ID (got {proposal_issue_id}, expected {self.current_issue.issue_id})")
            return
        
        issue_id = self.current_issue.issue_id
        tick = self.current_consensus.state["tick"]
        
        # Burn self-stake
        stake = self.current_consensus.gc.proposal_self_stake
        ok = self.creditmgr.attempt_deduct(
            agent_id=agent_id,
            amount=stake,
            reason="Proposal submission self-stake",
            tick=tick,
            issue_id=issue_id
        )

        if not ok:
            print(f"Agent {agent_id} had insufficient credit for self-stake.")
            return

        # Store proposal in consensus state
        proposal_id = proposal.get("proposal_id")
        self.current_consensus.state["proposals"][proposal_id] = {
            "agent_id": agent_id,
            "content": proposal["content"],
            "stake": stake,
            "tick": tick
        }
        
        # Mark agent as ready and track proposal submission
        self.ready_agents.add(agent_id)
        self.proposals_this_phase.add(agent_id)

        print(f"Proposal accepted from {agent_id}: {proposal_id}")
        print(f"Agent {agent_id} marked as Ready")

