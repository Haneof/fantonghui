"""ToolProposal 契约与可执行验收探针：提案必须带能力缺口 + 量化收益 + 可跑验收。"""

from __future__ import annotations

from aios_core.contracts.enums import ProposalStatus
from aios_core.tools.proposed_operators import (
    TOOL_PROPOSAL_IDS,
    build_tool_proposals,
    register_tool_proposals,
    validate_all_proposals,
    validate_proposal,
)
from aios_core.tools.proposal_pipeline import ToolProposalPipeline


def test_three_proposals_are_bound_to_the_tool_proposal_contract() -> None:
    proposals = build_tool_proposals()
    assert [item.object_id for item in proposals] == list(TOOL_PROPOSAL_IDS)
    for proposal in proposals:
        assert proposal.capability_gap.strip()
        assert proposal.use_cases
        assert proposal.current_limitations
        assert proposal.proposed_interface
        assert proposal.expected_benefit.strip()
        assert proposal.validation_plan.strip()
        assert proposal.status == ProposalStatus.DRAFT


def test_proposals_enter_the_review_pipeline_as_submitted() -> None:
    pipeline = ToolProposalPipeline()
    submitted = register_tool_proposals(pipeline)
    assert len(submitted) == 3
    assert {item.status for item in submitted} == {ProposalStatus.SUBMITTED}
    listed = pipeline.list_proposals(ProposalStatus.SUBMITTED)
    assert {item.object_id for item in listed} == set(TOOL_PROPOSAL_IDS)
    approved = pipeline.review_proposal(TOOL_PROPOSAL_IDS[0], "approve")
    assert approved.status == ProposalStatus.APPROVED
    executed = pipeline.execute_proposal(TOOL_PROPOSAL_IDS[0])
    assert executed.status == ProposalStatus.EXECUTED


def test_every_proposal_has_an_executable_probe_that_passes() -> None:
    results = validate_all_proposals()
    assert len(results) == 3
    # 收益方向必须与指标语义一致：压缩/节省类指标"越大越好"，
    # 窄相位触碰比例"越小越好"，任何一条都不允许只凭 passed 字段过审。
    for result in results:
        assert result.passed is True, f"{result.proposal_id} 验收未通过：{result.detail}"
        if result.metric == "narrow_phase_ratio":
            assert result.measured < result.threshold
        else:
            assert result.measured >= result.threshold


def test_probe_metrics_are_quantified() -> None:
    compressor = validate_proposal("TLP-ATC-001")
    assert compressor.metric == "reduction_ratio"
    assert "impacts=5" in compressor.detail
    projector = validate_proposal("TLP-DLV-002")
    assert projector.metric == "saved_ratio"
    evaluator = validate_proposal("TLP-LCE-003")
    assert evaluator.metric == "narrow_phase_ratio"
    assert "idle_evaluated=0" in evaluator.detail


def test_unknown_proposal_has_no_probe() -> None:
    import pytest

    with pytest.raises(KeyError):
        validate_proposal("TLP-UNKNOWN-999")
