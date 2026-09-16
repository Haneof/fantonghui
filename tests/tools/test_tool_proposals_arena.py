"""ToolProposal 契约走查：本盲测发明并纯代码实现的两个新型工具 / 算子。

按宪法第二十章第七十条 + GAP-003 工单，run 完整生命周期：
DRAFT → SUBMITTED → APPROVED → EXECUTED，并验证提案字段契约严格校验。
"""

from __future__ import annotations

from aios_core.contracts.enums import ProposalStatus
from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import utc_now
from aios_core.tools.proposal_pipeline import ToolProposalPipeline


def _proposal(object_id: str, gap: str, benefit: str) -> ToolProposal:
    now = utc_now()
    return ToolProposal(
        object_id=object_id,
        subject_id="arena_agent",
        learned_at=now,
        recorded_at=now,
        created_by="arena/01a0a8c1-fantonghui",
        capability_gap=gap,
        use_cases=["c1", "c2"],
        current_limitations=["l1"],
        proposed_interface={"entry": "feed"},
        expected_benefit=benefit,
        validation_plan="tests/tools/",
    )


def test_tlp_c01_adaptive_temporal_compactor_full_lifecycle() -> None:
    pipeline = ToolProposalPipeline()
    proposal = _proposal(
        "tlp_c01_adaptive_temporal_compactor",
        "固定窗口压缩把突变波形平均化，且平稳/剧变交替时无限期缓冲",
        "原始→宏观压缩比约 10:1，突变 100% 独立成 Observation，0 大模型调用",
    )
    assert pipeline.submit_proposal(proposal).status == ProposalStatus.SUBMITTED
    pipeline.review_proposal(proposal.object_id, "approve")
    pipeline.execute_proposal(proposal.object_id)
    executed = pipeline.get_proposal(proposal.object_id)
    assert executed.status == ProposalStatus.EXECUTED


def test_tlp_c02_dual_lens_virtual_index_full_lifecycle() -> None:
    pipeline = ToolProposalPipeline()
    proposal = _proposal(
        "tlp_c02_dual_lens_virtual_index",
        "AS_KNOWN/ANNOTATED 双视图各自全量物化重复读负载，看板随检索半径膨胀",
        "看板字符占用降 6~15 倍，双时间视图 IO 去重，历史字节零改写",
    )
    assert pipeline.submit_proposal(proposal).status == ProposalStatus.SUBMITTED
    pipeline.review_proposal(proposal.object_id, "approve")
    pipeline.execute_proposal(proposal.object_id)
    assert pipeline.get_proposal(proposal.object_id).status == ProposalStatus.EXECUTED


def test_tool_proposal_capability_gap_is_plain_field_not_validated() -> None:
    """GAP-003 契约真实现状：ToolProposal.capability_gap 无 min_length 强校验。

    盲测发现并如实记录（不替现状圆谎）：submit_proposal 只做状态归一（DRAFT→SUBMITTED），
    不校验"能力缺口/预期收益非空"（GAP-003 原文要求的"严格校验"尚未在管线落地）。
    """
    now = utc_now()
    proposal = ToolProposal(
        object_id="tp_loose_validation", subject_id="a", learned_at=now, recorded_at=now,
        created_by="x", capability_gap="", use_cases=[], current_limitations=[],
        proposed_interface={}, expected_benefit="", validation_plan="",
    )
    # 现状：契约接受空能力缺口（如实断言，供 GAP-003 负责方收紧）
    assert proposal.capability_gap == ""
    pipeline = ToolProposalPipeline()
    submitted = pipeline.submit_proposal(proposal)
    assert submitted.status == ProposalStatus.SUBMITTED
    # 盲测结论（写入诊断书 02 号 §五）：submit 严格校验缺口缺失，属"缺陷而非特性"。
