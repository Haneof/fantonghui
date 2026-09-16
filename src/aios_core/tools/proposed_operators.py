"""新工具提案（ToolProposal 契约落地）：三个已实现的算子及其可执行验收探针。

宪法依据
--------
* 第二十章第 70 条：AI 不仅学习用户，还要学习"怎样更有效地使用自己的世界"，
  并把这种学习固化为可审阅的工具提案；
* 第二十八条：工具提案必须有明确的能力缺口、适用场景、当前局限、期望收益与
  **可执行的验收计划** —— 只有口号没有验收标准的提案不得进入评审；
* 第八十六条之一：任何新工具的价值必须折算成 Token / I/O / 时延上的量化收益。

三个算子（全部已在本仓库实现，可被探针当场验证）
------------------------------------------------
1. ``TLP-ATC-001`` 自适应时序压缩算子
   （:class:`aios_core.tools.adaptive_temporal_compressor.AdaptiveTemporalCompressor`）
   —— 用误差有界的自适应窗口替换固定窗口，专治高频端侧流；
2. ``TLP-DLV-002`` 双透镜虚拟索引投影器
   （:class:`aios_core.tools.dual_lens_index_projector.DualLensVirtualIndexProjector`）
   —— 让"今天打标签"以增量投影落地，读面零全量重建；
3. ``TLP-LCE-003`` 轻量条件事件求值器
   （:class:`aios_core.tools.conditional_event_evaluator.LightweightConditionalEventEvaluator`）
   —— 宽相位建索引、窄相位只碰命中桶，消灭休眠期的无差别扫描。

探针（probe）不是文档，而是**可执行函数**：:func:`validate_proposal` 会当场跑一遍，
只有真正跑出量化收益的提案才会被标记为 VERIFIED。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from aios_core.contracts.enums import ObjectType, ProposalStatus
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import TemporalExtent, ToolProposal
from aios_core.contracts.time import utc_now
from aios_core.scheduler.conditional_engine import (
    Condition,
    ConditionKind,
    ConditionalTask,
    Level1FastTrack,
    MechanicalSignal,
)
from aios_core.tools.adaptive_temporal_compressor import (
    AdaptiveTemporalCompressor,
    verify_error_bound,
)
from aios_core.tools.conditional_event_evaluator import (
    EvaluatorSignals,
    LightweightConditionalEventEvaluator,
)
from aios_core.tools.dual_lens_index_projector import (
    ANNOTATED,
    AS_KNOWN,
    DualLensVirtualIndexProjector,
)
from aios_core.tools.proposal_pipeline import ToolProposalPipeline

UTC = timezone.utc

__all__ = [
    "ProbeResult",
    "TOOL_PROPOSAL_IDS",
    "build_tool_proposals",
    "register_tool_proposals",
    "validate_proposal",
    "validate_all_proposals",
]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """一次可执行验收的结论（通过条件 + 实测数字，不是主观判断）。"""

    proposal_id: str
    passed: bool
    metric: str
    measured: float
    threshold: float
    detail: str


# ---------------------------------------------------------------------------
# 提案正文
# ---------------------------------------------------------------------------

TOOL_PROPOSAL_IDS = ("TLP-ATC-001", "TLP-DLV-002", "TLP-LCE-003")


def build_tool_proposals(*, now: datetime | None = None) -> tuple[ToolProposal, ...]:
    """构造三个新工具提案（一等对象，可直接进 :class:`ToolProposalPipeline`）。"""

    stamp = now or utc_now()
    return (
        ToolProposal(
            object_id=TOOL_PROPOSAL_IDS[0],
            subject_id="ai_self_world",
            revision=1,
            capability_gap=(
                "端侧高频流（IMU 50Hz / 心率 1Hz）只能用固定时间窗合并，平稳期仍在"
                "按窗产出、突变期又被平均抹平，缺乏'误差有界且冲击保真'的压缩算子。"
            ),
            use_cases=[
                "IMU 50Hz 宏观运动状态提炼与跌倒冲击保真",
                "心率长平稳期时段均值压缩（2 小时一批）",
                "任何需要'压缩后仍能给出误差上界'的端侧时序通道",
            ],
            current_limitations=[
                "PulseMergeWindow 是固定 5s 窗，压缩比与信号平稳度无关",
                "固定窗平均会削平冲击波形，必须另开通道检测跌倒",
                "无重建误差上界，压缩损失不可量化、不可审计",
            ],
            proposed_interface={
                "class": "AdaptiveTemporalCompressor",
                "method": "compress(samples: Iterable[tuple[int, float]]) -> CompressionResult",
                "params": [
                    "epsilon",
                    "curvature_budget",
                    "impact_jump",
                    "impact_magnitude",
                    "min_window",
                    "max_window",
                ],
                "audit": "verify_error_bound(samples, result) 独立复核最大重建误差",
            },
            expected_benefit=(
                "百万级原始采样压到千级派生段（>=95% 缩减），且冲击波形 100% 原值保留、"
                "窗口内偏差硬约束在 epsilon 之内 —— 存储与 Token 双降，跌倒识别不降级。"
            ),
            validation_plan=(
                "probe_atc：对 5 万条含 5 连击冲击的合成流压缩，断言"
                "缩减率 > 0.95、冲击段数 == 5、verify_error_bound <= epsilon。"
            ),
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            status=ProposalStatus.DRAFT,
            created_by="mass_blind_bench",
        ),
        ToolProposal(
            object_id=TOOL_PROPOSAL_IDS[1],
            subject_id="ai_self_world",
            revision=1,
            capability_gap=(
                "双透镜读面每次查询都要全量拉取底层事实再叠加注解，"
                "在'3 年 18000 条事实 + 今日 1 条注解'的老王案里等于每次查询重建全量索引。"
            ),
            use_cases=[
                "老王案：AS_KNOWN 与 ANNOTATED 双视图检索一致性校验",
                "任何'今天打标签'后仍需按历史认知口径检索的场景",
                "端侧受限内存下的只增不重建索引维护",
            ],
            current_limitations=[
                "view_at / EpistemicWorldLens 读面为 O(全部事实) 重建",
                "注解与基底混在一起，无法证明'基底未被污染'",
                "缺少量化口径说明增量投影到底省了多少",
            ],
            proposed_interface={
                "class": "DualLensVirtualIndexProjector",
                "methods": [
                    "index_fact(object_id, text, learned_us)",
                    "freeze_base() -> sha256",
                    "attach_annotation(...) -> int",
                    "query(keywords, lens=AS_KNOWN|ANNOTATED, as_of_us=None)",
                    "metrics() -> ProjectionMetrics",
                ],
            },
            expected_benefit=(
                "注解挂载成本从 O(基底 posting 总数) 降到 O(注解词元数)，"
                "读面两条透镜返回同一组事实，基底 SHA-256 前后逐字节不变。"
            ),
            validation_plan=(
                "probe_dlv：索引 1000 条事实后冻结基底、挂 1 条注解，断言"
                "saved_ratio >= 0.95、双透镜事实集合一致、基底哈希不变。"
            ),
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            status=ProposalStatus.DRAFT,
            created_by="mass_blind_bench",
        ),
        ToolProposal(
            object_id=TOOL_PROPOSAL_IDS[2],
            subject_id="ai_self_world",
            revision=1,
            capability_gap=(
                "机械快轨对**全部**待办任务做线性扫描，10 万休眠任务时每个信号都要看"
                "10 万遍 —— Token 虽为 0，端侧 CPU 与电量在静默期被无差别烧掉。"
            ),
            use_cases=[
                "10 万级条件任务的长期休眠与阈值触发",
                "没有新信号的静默 tick（应当 O(1) 空转）",
                "按指标/地点分桶的窄相位触发（只碰真正变化的桶）",
            ],
            current_limitations=[
                "Level1FastTrack.scan 每次 tick 遍历全部任务",
                "无声明的索引，无法回答'这次 tick 到底评估了多少任务'",
            ],
            proposed_interface={
                "class": "LightweightConditionalEventEvaluator",
                "methods": [
                    "register(task_id, title, conditions)",
                    "tick(EvaluatorSignals) -> EvaluationReport",
                    "index_sizes() / earliest_pending_us() / blocked_task_ids()",
                ],
            },
            expected_benefit=(
                "静默 tick 求值次数为 0（堆顶未到期即返回），"
                "有信号 tick 只碰命中的地理/指标桶，实际求值次数 < 注册任务数的 5%。"
            ),
            validation_plan=(
                "probe_lce：注册 5000 个条件任务（地理/指标/时间三桶），断言"
                "静默 tick 求值 0 次且耗时 < 1ms；带信号 tick 求值数 < 注册数的 5%。"
            ),
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            status=ProposalStatus.DRAFT,
            created_by="mass_blind_bench",
        ),
    )


def register_tool_proposals(
    pipeline: ToolProposalPipeline, *, now: datetime | None = None
) -> tuple[ToolProposal, ...]:
    """把提案提交进既有的 :class:`ToolProposalPipeline`（走正式评审通道）。"""

    submitted: list[ToolProposal] = []
    for proposal in build_tool_proposals(now=now):
        pipeline.submit_proposal(proposal)
        if proposal.status != ProposalStatus.SUBMITTED:
            raise RuntimeError(f"proposal {proposal.object_id} was not accepted as SUBMITTED")
        submitted.append(proposal)
    return tuple(submitted)


# ---------------------------------------------------------------------------
# 可执行验收探针
# ---------------------------------------------------------------------------


def _probe_atc() -> ProbeResult:
    rng = random.Random(20260916)
    samples: list[tuple[int, float]] = []
    t = 0
    for index in range(50_000):
        value = 1.0 + rng.gauss(0.0, 0.05)
        if 20_000 <= index < 20_005:
            value = 5.2
        samples.append((t, value))
        t += 20_000
    engine = AdaptiveTemporalCompressor(
        epsilon=0.5,
        curvature_budget=0.5,
        impact_magnitude=3.0,
        impact_jump=None,
    )
    result = engine.compress(samples)
    worst = verify_error_bound(samples, result)
    passed = (
        result.reduction_ratio > 0.95
        and result.impact_count == 5
        and worst <= engine.epsilon + 1e-9
    )
    return ProbeResult(
        proposal_id=TOOL_PROPOSAL_IDS[0],
        passed=passed,
        metric="reduction_ratio",
        measured=round(result.reduction_ratio, 6),
        threshold=0.95,
        detail=(
            f"in={result.input_count} out={result.output_count} "
            f"impacts={result.impact_count} max_err={worst:.4f} <= {engine.epsilon}"
        ),
    )


def _probe_dlv() -> ProbeResult:
    projector = DualLensVirtualIndexProjector()
    for index in range(1000):
        projector.index_fact(
            f"obs_partner_{index:04d}",
            f"与合伙人的出资、对赌协议与银行流水记录 第{index}笔",
            learned_us=1_700_000_000_000_000 + index,
        )
    frozen = projector.freeze_base()
    projector.attach_annotation(
        "ran_probe_1",
        target_object_id="obs_partner_0007",
        statement="事后证实该合伙人涉合同诈骗，相关往来需按诈骗口径重新评估",
        slot="meaning",
        annotated_us=1_800_000_000_000_000,
    )
    metrics = projector.metrics()
    consistent = projector.assert_lens_consistency(["合伙", "出资", "对赌"])
    annotated = projector.query(["合伙", "出资", "对赌"], lens=ANNOTATED)
    has_overlay = any(hit.annotation_ids for hit in annotated.hits)
    as_known = projector.query(["合伙", "出资", "对赌"], lens=AS_KNOWN)
    passed = (
        metrics.saved_ratio >= 0.95
        and consistent
        and has_overlay
        and projector.base_index_sha256 == frozen
        and projector.base_compatible_with_frozen()
        and len(as_known.hits) == len(annotated.hits)
    )
    return ProbeResult(
        proposal_id=TOOL_PROPOSAL_IDS[1],
        passed=passed,
        metric="saved_ratio",
        measured=round(metrics.saved_ratio, 6),
        threshold=0.95,
        detail=(
            f"base_postings={metrics.naive_rebuild_postings} "
            f"overlay_written={metrics.overlay_postings_written} "
            f"lens_consistent={consistent} overlay_visible={has_overlay}"
        ),
    )


def _probe_lce() -> ProbeResult:
    evaluator = LightweightConditionalEventEvaluator()
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)
    total = 5_000
    for index in range(total):
        if index % 3 == 0:
            conditions = (
                Condition(
                    kind=ConditionKind.ABSOLUTE_TIME,
                    summary=f"绝对时间 {index}",
                    deadline=now + timedelta(days=400 + index % 50),
                ),
            )
        elif index % 3 == 1:
            conditions = (
                Condition(
                    kind=ConditionKind.GEO_FENCE,
                    summary=f"地理围栏 {index}",
                    place_key=f"place_{index % 40}",
                ),
            )
        else:
            conditions = (
                Condition(
                    kind=ConditionKind.VITAL_THRESHOLD,
                    summary=f"生理阈值 {index}",
                    metric=f"metric_{index % 30}",
                    comparator=">",
                    threshold=110.0,
                    consecutive_days=3,
                ),
            )
        evaluator.register(f"task_{index}", title=f"任务 {index}", conditions=conditions)

    idle_report = evaluator.tick(EvaluatorSignals(now=now))
    signal_report = evaluator.tick(
        EvaluatorSignals(
            now=now,
            present_places=("place_7",),
            vitals={"metric_7": (118.0, 121.0, 124.0)},
        )
    )
    ratio = signal_report.tasks_evaluated / max(1, total)
    passed = (
        idle_report.tasks_evaluated == 0
        and idle_report.elapsed_ms < 1.0
        and ratio < 0.05
        and signal_report.llm_calls == 0
        and _fast_track_scans_more_than_evaluator(total, now)
    )
    return ProbeResult(
        proposal_id=TOOL_PROPOSAL_IDS[2],
        passed=passed,
        metric="narrow_phase_ratio",
        measured=round(ratio, 6),
        threshold=0.05,
        detail=(
            f"registered={total} idle_evaluated={idle_report.tasks_evaluated} "
            f"idle_ms={idle_report.elapsed_ms:.4f} signal_evaluated={signal_report.tasks_evaluated}"
        ),
    )


def _fast_track_scans_more_than_evaluator(total: int, now: datetime) -> bool:
    """对照基准：既有快轨在静默 tick 上仍会扫描全部任务（证明优化真实存在）。"""

    fast_track = Level1FastTrack()
    tasks = tuple(
        ConditionalTask(
            task_id=f"legacy_{index}",
            title=f"遗留任务 {index}",
            conditions=(
                Condition(
                    kind=ConditionKind.ABSOLUTE_TIME,
                    summary=f"绝对时间 {index}",
                    deadline=now + timedelta(days=400 + index % 50),
                ),
            ),
        )
        for index in range(min(total, 2_000))
    )
    signal = MechanicalSignal(now=now)
    report, _ready = fast_track.scan(tasks, signal)
    return report.scanned >= len(tasks) and report.evaluated == len(tasks)


_PROBES: Mapping[str, Callable[[], ProbeResult]] = {
    TOOL_PROPOSAL_IDS[0]: _probe_atc,
    TOOL_PROPOSAL_IDS[1]: _probe_dlv,
    TOOL_PROPOSAL_IDS[2]: _probe_lce,
}


def validate_proposal(proposal_id: str) -> ProbeResult:
    """执行某提案的验收探针（不在白名单里的提案直接失败，杜绝无验收提案）。"""

    probe = _PROBES.get(proposal_id)
    if probe is None:
        raise KeyError(f"no executable validation probe for proposal {proposal_id!r}")
    return probe()


def validate_all_proposals() -> tuple[ProbeResult, ...]:
    return tuple(validate_proposal(proposal_id) for proposal_id in TOOL_PROPOSAL_IDS)
