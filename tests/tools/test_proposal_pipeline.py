import pytest
from aios_core.contracts.enums import ProposalStatus, ObjectType
from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import utc_now, TemporalExtent
from aios_core.tools.proposal_pipeline import ToolProposalPipeline
from datetime import timedelta

@pytest.fixture
def pipeline():
    return ToolProposalPipeline()

@pytest.fixture
def mock_proposal():
    now = utc_now()
    return ToolProposal(
        object_id="tp_001",
        subject_id="sub_001",
        occurred=TemporalExtent(start=now, end=now + timedelta(hours=1)),
        learned_at=now,
        recorded_at=now,
        source_refs=[],
        created_by="test_user",
        metadata={},
        capability_gap="gap 1",
        use_cases=["use case 1"],
        current_limitations=["limit 1"],
        proposed_interface={},
        expected_benefit="benefit 1",
        validation_plan="plan 1",
        status=ProposalStatus.DRAFT
    )

def test_submit_proposal(pipeline, mock_proposal):
    proposal = pipeline.submit_proposal(mock_proposal)
    assert proposal.status == ProposalStatus.SUBMITTED
    assert pipeline.get_proposal("tp_001") is not None

def test_review_approve(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    proposal = pipeline.review_proposal("tp_001", "approve")
    assert proposal.status == ProposalStatus.APPROVED

def test_review_reject(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    proposal = pipeline.review_proposal("tp_001", "reject")
    assert proposal.status == ProposalStatus.REJECTED

def test_review_needs_changes(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    proposal = pipeline.review_proposal("tp_001", "request_changes")
    assert proposal.status == ProposalStatus.NEEDS_CHANGES

def test_execute_approved(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    pipeline.review_proposal("tp_001", "approve")
    proposal = pipeline.execute_proposal("tp_001")
    assert proposal.status == ProposalStatus.EXECUTED

def test_execute_unapproved(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    with pytest.raises(ValueError, match="Only approved proposals can be executed"):
        pipeline.execute_proposal("tp_001")

def test_list_proposals_by_status(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    
    now = utc_now()
    prop2 = mock_proposal.model_copy()
    prop2.object_id = "tp_002"
    pipeline.submit_proposal(prop2)
    pipeline.review_proposal("tp_002", "approve")
    
    submitted = pipeline.list_proposals(ProposalStatus.SUBMITTED)
    assert len(submitted) == 1
    assert submitted[0].object_id == "tp_001"
    
    approved = pipeline.list_proposals(ProposalStatus.APPROVED)
    assert len(approved) == 1
    assert approved[0].object_id == "tp_002"

def test_retire_proposal(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    proposal = pipeline.retire_proposal("tp_001")
    assert proposal.status == ProposalStatus.RETIRED

def test_get_nonexistent(pipeline):
    assert pipeline.get_proposal("nonexistent") is None

def test_review_invalid_action(pipeline, mock_proposal):
    pipeline.submit_proposal(mock_proposal)
    with pytest.raises(ValueError, match="Invalid review action"):
        pipeline.review_proposal("tp_001", "invalid_action")
