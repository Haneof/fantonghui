from typing import Optional
from aios_core.contracts.enums import ProposalStatus
from aios_core.contracts.models import ToolProposal

class ToolProposalPipeline:
    def __init__(self):
        self._proposals: dict[str, ToolProposal] = {}

    def submit_proposal(self, proposal: ToolProposal) -> ToolProposal:
        if proposal.status == ProposalStatus.DRAFT or proposal.status == "active":
            proposal.status = ProposalStatus.SUBMITTED
        self._proposals[proposal.object_id] = proposal
        return proposal

    def review_proposal(self, object_id: str, action: str) -> ToolProposal:
        proposal = self.get_proposal(object_id)
        if not proposal:
            raise ValueError("Proposal not found")
            
        if action == "approve":
            proposal.status = ProposalStatus.APPROVED
        elif action == "reject":
            proposal.status = ProposalStatus.REJECTED
        elif action == "request_changes":
            proposal.status = ProposalStatus.NEEDS_CHANGES
        else:
            raise ValueError(f"Invalid review action: {action}")
        return proposal

    def execute_proposal(self, object_id: str) -> ToolProposal:
        proposal = self.get_proposal(object_id)
        if not proposal:
            raise ValueError("Proposal not found")
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError("Only approved proposals can be executed")
        
        proposal.status = ProposalStatus.EXECUTED
        return proposal

    def list_proposals(self, status: Optional[ProposalStatus] = None) -> list[ToolProposal]:
        if status:
            return [p for p in self._proposals.values() if p.status == status]
        return list(self._proposals.values())

    def get_proposal(self, object_id: str) -> Optional[ToolProposal]:
        return self._proposals.get(object_id)

    def retire_proposal(self, object_id: str) -> ToolProposal:
        proposal = self.get_proposal(object_id)
        if not proposal:
            raise ValueError("Proposal not found")
            
        proposal.status = ProposalStatus.RETIRED
        return proposal
