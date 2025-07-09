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
        issue_id = self.current_issue.issue_id
        tick = self.current_consensus.state["tick"]
        print(f"Received proposal from {agent_id}: {proposal}")
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

        print(f"Proposal accepted from {agent_id}: {proposal_id}")

