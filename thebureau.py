from models import AgentPool, GlobalConfig, RunConfig, Issue
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

    def start_consensus_run(self, global_config: GlobalConfig, run_config: RunConfig ) -> Consensus:

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

        return consensus

    def run(self):
        if not self.current_consensus:
            raise RuntimeError("No active consensus run.")
        return self.current_consensus.run()
