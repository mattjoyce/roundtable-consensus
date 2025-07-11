from models import AgentPool, GlobalConfig, RunConfig, Issue, Proposal
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
        self.ready_agents.clear()
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
                print(f"Timeout {consensus.get_current_phase()} at tick {consensus.state['tick']}")
                unready = self.get_unready_agents()

                if len(unready) != 0:
                    proposal= self.create_no_action_proposal(
                        tick=self.current_consensus.state["tick"],
                        agent_id="z",
                        issue_id=self.current_issue.issue_id
                    )
                    self.current_issue.add_proposal(proposal)
                    #link unready ahent to no action proposal
                    for agent_id in unready:
                        self.current_issue.assign_agent_to_proposal(agent_id, proposal.proposal_id)
                        self.signal_ready(agent_id)



            # if we transistioned to a new phase, reset ready agents
            if consensus.state["phase_tick"] == 1:
                print(f"Transitioned to new phase: {consensus.get_current_phase().phase_number}")
                print(f"Phase Tick: {consensus.state['phase_tick']}")
                self.ready_agents.clear()

            #share ready agents with consensus state
            consensus.state["all_agents_ready"] = not self.get_unready_agents()
            
            print("Ticking consensus...")
            consensus.tick()

        return consensus._summarize_results()
    
    def get_unready_agents(self) -> set:
        return set(self.assigned_agents) - self.ready_agents
    



    def _process_pending_actions(self):
        for action in ACTION_QUEUE.drain():
            if action.type == "submit_proposal":
                proposal=Proposal(**action.payload)
                self.receive_proposal(action.agent_id, proposal)
            if action.type == "ready_signal":
                self.signal_ready(action.agent_id)


    def receive_proposal(self, agent_id: str, proposal: Proposal):
        print(f"Received proposal from {agent_id}: {proposal.proposal_id} for issue {proposal.issue_id}")
        
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
        if proposal.issue_id != self.current_issue.issue_id:
            print(f"Rejected proposal from {agent_id}: Wrong issue ID (got {proposal.issue_id}, expected {self.current_issue.issue_id})")
            return
        
        issue_id = self.current_issue.issue_id
        tick = self.current_consensus.state["tick"]

        #update proposal with issue ID and tick
        proposal.tick = tick
        # Store proposal in Issue 
        self.current_issue.add_proposal(proposal)
        self.current_issue.assign_agent_to_proposal(agent_id, proposal.proposal_id)
        
        # Mark agent as ready and track proposal submission
        self.signal_ready(agent_id)
        self.proposals_this_phase.add(agent_id)

        print(f"Proposal accepted from {agent_id}: {proposal.proposal_id} for issue {issue_id} at tick {tick}")
        print(f"Agent {agent_id} marked as Ready")

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
        print(f"Agent {agent_id} marked as Ready")
        self.ready_agents.add(agent_id)