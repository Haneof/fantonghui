"""多维时空共振与新事件合成（Event Resonance & Lifecycle，阶段三核心算子）。

宪法依据
--------
* 第二十二条：纵向交织 —— 基础各维度横向交叉汇聚，自发长成更高阶的衍生认知；
* 第二十四条：派生关系必须有一等结构记录来源与适用范围，且可从高层下钻到底层；
* 第八十八条（TimeLens/DimensionLens 精神）：跨维度必须做**时空对齐**，而不是
  各维度各扫一遍再靠关键词硬拼；
* 第十五条第 6 款：触发器只负责唤醒，**不得代判事件语义** —— 因此事件由认知层
  在共振证据之上合成，并保留 CANDIDATE → ACTIVE → RESOLVED 的可审计生命周期。

为什么既有实现不够
------------------
仓库既有的事件锚点基本由外部直接写入（"某人某天发生了某事"），缺少一条**从多源
证据自动长出事件**的机制：没有跨维度时间对齐，没有"多个维度在同一时空窗口内共振"
的判定，也就无法解释"为什么这条事件值得被记住"。

本模块补上这条链：

1. `add_stream` 登记各维度的**带指针采样**（心率突变 / GPS 轨迹 / 录音原话 / 财务流水…）；
2. `align(center_us, half_window_us)` 在**同一时空窗口**内横向对齐多维采样，
   返回按维度分桶的共振窗口（每个采样都带着指向底层 Observation 的 ObjectRef）；
3. `synthesize(...)` 仅在共振维度数 ≥ ``min_dimensions`` 时合成候选事件
   （``EventStatus.CANDIDATE``），并冻结当时的快照与共振理由；
4. `advance(...)` 推进生命周期：每个状态变化都产生**下一个修订版本**（复用仓库
   `validate_event_revision_transition` 的法定通道），同时留存时间快照与修订理由，
   并把直接下游标记 STALE（单跳隔离，绝不级联重算）。

零大模型调用：本模块只做机械对齐与结构化合成，语义由上层唤醒会话给出。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ClaimType, EventStatus, KnowledgeState, ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import Claim, EventAnchor, TemporalExtent
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import as_utc
from aios_core.services.state_machines import (
    validate_event_revision_transition,
    validate_event_transition,
)
from aios_core.world.retrospective_annotation import SingleHopCascadeIsolator

UTC = timezone.utc

__all__ = [
    "EventLifecycleLedger",
    "EventResonanceSynthesizer",
    "LifecycleStep",
    "ResonanceSample",
    "ResonanceWindow",
]


@dataclass(frozen=True, slots=True)
class ResonanceSample:
    """某一维度上的一条带指针采样（指针指向底层不可变 Observation）。"""

    t_us: int
    value: float
    ref: ObjectRef
    label: str = ""

    @property
    def magnitude(self) -> float:
        return abs(self.value)


class ResonanceWindow(BaseModel):
    """一次跨维度时空对齐的结果（按维度分桶，桶内按时间升序）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    center_us: int
    half_window_us: int
    buckets: dict[str, tuple[ResonanceSample, ...]]
    resonant_dimensions: tuple[str, ...]
    evidence_refs: tuple[ObjectRef, ...]
    alignment_span_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_buckets(self) -> "ResonanceWindow":
        if self.resonant_dimensions != tuple(sorted(self.buckets)):
            raise ValueError("resonant_dimensions must enumerate the populated buckets")
        return self

    @property
    def dimension_count(self) -> int:
        return len(self.resonant_dimensions)

    def sample_count(self) -> int:
        return sum(len(bucket) for bucket in self.buckets.values())


class LifecycleStep(BaseModel):
    """事件生命周期的一次演化（快照 + 理由 + 下游失效回执）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str
    from_status: str
    to_status: str
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1)
    snapshot: dict
    stale_downstream: tuple[str, ...] = ()
    occurred_at: datetime


class EventLifecycleLedger:
    """事件生命周期账本：快照只追加，从不覆盖（宪法第九十三条同源纪律）。"""

    def __init__(self) -> None:
        self._steps: list[LifecycleStep] = []
        self._isolator = SingleHopCascadeIsolator()

    @property
    def isolator(self) -> SingleHopCascadeIsolator:
        return self._isolator

    def record(
        self,
        *,
        event: EventAnchor,
        from_status: EventStatus,
        reason: str,
        occurred_at: datetime,
    ) -> LifecycleStep:
        self._isolator.register_node(event.object_id)
        step = LifecycleStep(
            object_id=event.object_id,
            from_status=from_status.value,
            to_status=event.event_status.value,
            revision=event.revision,
            reason=reason,
            snapshot=event.model_dump(mode="json"),
            occurred_at=occurred_at,
        )
        self._steps.append(step)
        return step

    def mark_stale_downstream(self, step: LifecycleStep, stale: Sequence[str]) -> LifecycleStep:
        """把"本次演化导致的下游 STALE"补记到刚写入的那一步（只追加，不改历史）。"""

        try:
            index = self._steps.index(step)
        except ValueError:
            raise KeyError("cannot annotate a lifecycle step that is not in the ledger") from None
        updated = step.model_copy(update={"stale_downstream": tuple(stale)})
        self._steps[index] = updated
        return updated

    def steps(self, object_id: str | None = None) -> tuple[LifecycleStep, ...]:
        if object_id is None:
            return tuple(self._steps)
        return tuple(step for step in self._steps if step.object_id == object_id)

    def snapshot_at(self, object_id: str, revision: int) -> dict:
        """按修订号取回历史快照（事件演化的可复核轨迹）。"""

        for step in self._steps:
            if step.object_id == object_id and step.revision == revision:
                return dict(step.snapshot)
        raise KeyError(f"no snapshot for {object_id!r}@r{revision}")


class EventResonanceSynthesizer:
    """多源跨维度共振合成器（时空对齐 → 共振判定 → 候选事件 → 生命周期）。"""

    def __init__(
        self,
        *,
        subject_id: str,
        min_dimensions: int = 3,
        default_half_window_us: int = 30 * 60 * 1_000_000,
    ) -> None:
        if min_dimensions < 2:
            raise ValueError("resonance requires at least 2 dimensions")
        if default_half_window_us <= 0:
            raise ValueError("default_half_window_us must be positive")
        self.subject_id = subject_id
        self.min_dimensions = min_dimensions
        self.default_half_window_us = default_half_window_us
        self._streams: dict[str, list[ResonanceSample]] = {}
        self._sorted_us: dict[str, list[int]] = {}
        self.ledger = EventLifecycleLedger()

    # ------------------------------------------------------------------
    # 维度登记
    # ------------------------------------------------------------------

    def add_stream(self, dimension: str, samples: Iterable[ResonanceSample]) -> int:
        bucket = self._streams.setdefault(dimension, [])
        bucket.extend(samples)
        bucket.sort(key=lambda sample: sample.t_us)
        self._sorted_us[dimension] = [sample.t_us for sample in bucket]
        return len(bucket)

    def dimensions(self) -> tuple[str, ...]:
        return tuple(sorted(self._streams))

    # ------------------------------------------------------------------
    # 时空对齐
    # ------------------------------------------------------------------

    def align(
        self,
        *,
        center: datetime,
        half_window_us: int | None = None,
    ) -> ResonanceWindow:
        """在中心时刻 ± 半窗内横向对齐所有维度（每维只取该窗口内的采样）。"""

        span = half_window_us or self.default_half_window_us
        if span <= 0:
            raise ValueError("half_window_us must be positive")
        center_us = int(as_utc(center, "center").timestamp() * 1_000_000)
        low = center_us - span
        high = center_us + span

        buckets: dict[str, tuple[ResonanceSample, ...]] = {}
        evidence: list[ObjectRef] = []
        earliest: int | None = None
        latest: int | None = None
        for dimension in self.dimensions():
            timestamps = self._sorted_us[dimension]
            start = bisect_left(timestamps, low)
            stop = bisect_right(timestamps, high)
            if start >= stop:
                continue
            picked = tuple(self._streams[dimension][start:stop])
            buckets[dimension] = picked
            for sample in picked:
                evidence.append(sample.ref)
                earliest = sample.t_us if earliest is None else min(earliest, sample.t_us)
                latest = sample.t_us if latest is None else max(latest, sample.t_us)

        alignment_span = 0 if earliest is None or latest is None else latest - earliest
        return ResonanceWindow(
            center_us=center_us,
            half_window_us=span,
            buckets=buckets,
            resonant_dimensions=tuple(sorted(buckets)),
            evidence_refs=tuple(evidence),
            alignment_span_us=alignment_span,
        )

    def is_resonant(self, window: ResonanceWindow) -> bool:
        return window.dimension_count >= self.min_dimensions

    # ------------------------------------------------------------------
    # 候选事件合成
    # ------------------------------------------------------------------

    def synthesize(
        self,
        *,
        window: ResonanceWindow,
        title: str,
        interpretation: str,
        confidence: float,
        learned_at: datetime,
        participant_refs: Sequence[ObjectRef] = (),
    ) -> EventAnchor:
        """把一次跨维度共振冻结成候选事件（CANDIDATE，等待证据复核后转 ACTIVE）。"""

        if not self.is_resonant(window):
            raise ValueError(
                "cross-dimension resonance requires at least "
                f"{self.min_dimensions} dimensions, got {window.dimension_count}"
            )
        if not title.strip() or not interpretation.strip():
            raise ValueError("event title and interpretation must not be blank")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

        stamp = as_utc(learned_at, "learned_at")
        event = EventAnchor(
            object_id=new_object_id(ObjectType.EVENT),
            subject_id=self.subject_id,
            revision=1,
            title=title,
            interpretation=interpretation,
            event_status=EventStatus.CANDIDATE,
            participant_refs=list(participant_refs),
            evidence_set_refs=[],
            primary_claim_refs=[],
            confidence=confidence,
            event_time=TemporalExtent(
                start=datetime.fromtimestamp(window.center_us / 1_000_000, tz=UTC),
                end=datetime.fromtimestamp(window.center_us / 1_000_000, tz=UTC),
            ),
            occurred=TemporalExtent(
                start=datetime.fromtimestamp(window.center_us / 1_000_000, tz=UTC),
                end=datetime.fromtimestamp(window.center_us / 1_000_000, tz=UTC),
            ),
            learned_at=stamp,
            recorded_at=stamp,
            created_by="event_resonance_synthesizer",
            metadata={
                "resonant_dimensions": list(window.resonant_dimensions),
                "aligned_evidence_refs": [
                    {"object_id": ref.object_id, "revision": ref.revision}
                    for ref in window.evidence_refs
                ],
            },
        )
        self.ledger.record(
            event=event,
            from_status=EventStatus.CANDIDATE,
            reason=(
                "跨维度共振合成："
                + "、".join(window.resonant_dimensions)
                + f" 在 ±{window.half_window_us // 60_000_000} 分钟内对齐"
            ),
            occurred_at=stamp,
        )
        return event

    def synthesize_claim(
        self,
        *,
        event: EventAnchor,
        statement: str,
        claim_type: ClaimType = ClaimType.INFERENCE,
        evidence_set_refs: Sequence[ObjectRef] = (),
        confidence: float | None = None,
        learned_at: datetime,
    ) -> Claim:
        """把共振事件的主张固化为 Claim（含证据集指针，可下钻）。"""

        stamp = as_utc(learned_at, "learned_at")
        return Claim(
            object_id=new_object_id(ObjectType.CLAIM),
            subject_id=self.subject_id,
            revision=1,
            claimant_id="ai_cognition_brain",
            claim_type=claim_type,
            content=statement,
            valid_time=TemporalExtent.point(stamp),
            asserted_at=stamp,
            knowledge_state=KnowledgeState.INFERRED,
            confidence=confidence if confidence is not None else event.confidence,
            support_evidence_set_refs=list(evidence_set_refs),
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            created_by="event_resonance_synthesizer",
        )

    # ------------------------------------------------------------------
    # 生命周期推进
    # ------------------------------------------------------------------

    def advance(
        self,
        event: EventAnchor,
        *,
        target: EventStatus,
        revision_reason: str,
        learned_at: datetime,
        supersedes_ref: ObjectRef | None = None,
        merged_into_ref: ObjectRef | None = None,
        split_child_refs: Sequence[ObjectRef] = (),
    ) -> EventAnchor:
        """推进事件生命周期：产生下一个修订版本 + 快照 + 理由 + 下游 STALE 标记。"""

        if not revision_reason.strip():
            raise ValueError("event lifecycle advance requires a revision reason")
        stamp = as_utc(learned_at, "learned_at")
        validate_event_transition(event.event_status, target)

        updates: dict[str, object] = {
            "revision": event.revision + 1,
            "event_status": target,
            "revision_reason": revision_reason,
            "learned_at": stamp,
            "recorded_at": stamp,
        }
        if supersedes_ref is not None:
            updates["supersedes_refs"] = [*event.supersedes_refs, supersedes_ref]
        if merged_into_ref is not None:
            updates["merged_into_ref"] = merged_into_ref
        if split_child_refs:
            updates["split_child_refs"] = [*event.split_child_refs, *split_child_refs]

        successor = event.model_copy(update=updates)
        validate_event_revision_transition(event, successor)

        # 下游依赖单跳隔离：事件修订只把直接消费者标记 STALE，绝不级联重算。
        self.ledger.isolator.register_node(successor.object_id)
        report = self.ledger.isolator.reverse_invalidate(successor.object_id)
        step = self.ledger.record(
            event=successor,
            from_status=event.event_status,
            reason=revision_reason,
            occurred_at=stamp,
        )
        if report.marked_stale:
            self.ledger.mark_stale_downstream(step, report.marked_stale)
        return successor

    def register_dependent(self, dependency: str, dependent: str) -> None:
        """登记下游依赖（用于验证"下游自动标记 STALE 并触发复核"）。"""

        self.ledger.isolator.add_dependency(dependency, dependent)

    def stale_downstream(self) -> frozenset[str]:
        return self.ledger.isolator.stale_nodes()
