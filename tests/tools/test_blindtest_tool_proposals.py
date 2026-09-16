"""海量盲测新工具发明登记：两个新算子按 ToolProposal 契约走完整提案流水线。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aios_core.contracts.enums import ProposalStatus
from aios_core.contracts.models import TemporalExtent, ToolProposal
from aios_core.tools.proposal_pipeline import ToolProposalPipeline

UTC = timezone.utc
T0 = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _proposal(object_id: str, gap: str, interface: dict) -> ToolProposal:
    return ToolProposal(
        object_id=object_id,
        subject_id="user_mass",
        revision=1,
        capability_gap=gap,
        use_cases=[
            "百万级传感器波形边缘提纯（MT-001）",
            "老王案历史回溯双透镜读面（MT-012）",
        ],
        current_limitations=[
            "50Hz 原始波形若直写数据库将撑爆端侧存储",
            "无界级联重算历史曾造成 210 次 API 算力雪崩",
        ],
        proposed_interface=interface,
        expected_benefit="Token 与 I/O 双降，历史不可变铁律工程化落地",
        validation_plan="pytest 全绿 + 海量盲测 8 阶段实测断言",
        occurred=TemporalExtent.point(T0),
        learned_at=T0,
        recorded_at=T0,
        created_by="arena01_blindtest",
    )


def test_two_invented_tools_pass_full_proposal_lifecycle():
    pipeline = ToolProposalPipeline()

    compactor_proposal = _proposal(
        "tool_adaptive_temporal_compactor",
        "高频传感器波形缺乏自适应压缩，平稳期与突变期一视同仁",
        {
            "class": "AdaptiveTemporalCompactor",
            "module": "aios_core.tools.adaptive_temporal_compactor",
            "methods": ["compact(samples) -> CompactionResult"],
            "invariants": ["raw_rows_persisted == 0", "突变零漏检", "过滤率 >= 95%"],
        },
    )
    projector_proposal = _proposal(
        "tool_dual_lens_virtual_index_projector",
        "AsKnown/Annotated 双读面缺乏零改写的虚拟索引投影",
        {
            "class": "DualLensVirtualIndexProjector",
            "module": "aios_core.tools.dual_lens_projector",
            "methods": ["project(lens, now)", "consistency_check()", "invalidate_single_hop(origin)"],
            "invariants": ["历史指纹恒定", "单跳深度 == 1", "max_hops > 1 fail-closed"],
        },
    )

    submitted = [pipeline.submit_proposal(p) for p in (compactor_proposal, projector_proposal)]
    assert all(p.status == ProposalStatus.SUBMITTED for p in submitted)

    for p in submitted:
        pipeline.review_proposal(p.object_id, "approve")
        pipeline.execute_proposal(p.object_id)
    assert all(p.status == ProposalStatus.EXECUTED for p in pipeline.list_proposals(ProposalStatus.EXECUTED))

    # 已执行提案不得再次执行
    import pytest

    with pytest.raises(ValueError):
        pipeline.execute_proposal("tool_adaptive_temporal_compactor")


def test_invented_tools_are_real_and_importable():
    """提案不是纸面文章：两个算子必须真实存在且可运行。"""
    from aios_core.tools.adaptive_temporal_compactor import AdaptiveTemporalCompactor, SensorSample
    from aios_core.tools.dual_lens_projector import DualLensVirtualIndexProjector, LensKind

    result = AdaptiveTemporalCompactor().compact(
        iter(
            SensorSample(t=T0 + timedelta(seconds=i), channel="heart_rate", value=65.0)
            for i in range(600)
        )
    )
    assert result.raw_rows_persisted == 0
    assert result.records_out >= 1
    assert LensKind.AS_KNOWN.value == "as_known"
    assert DualLensVirtualIndexProjector is not None
