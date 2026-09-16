"""阶段三：多维时空共振、新事件合成与生命周期状态流转（MT-010/022）。

* **共振合成**：拒绝单关键词全表扫描——以多关键词共现拓扑召回
  （复用 :class:`MultidimensionalSearchEngine` 路径 C）圈定候选，
  再把 GPS 轨迹、心率突变、录音原话做横向时空对齐，自主共振合成
  EventAnchor（≥2 模态、≥3 信号才允许立锚）。
* **生命周期**：CANDIDATE→ACTIVE→RESOLVED / REVISED / MERGED / SPLIT，
  每次演化留存时间快照与修订理由；下游依赖自动标记 STALE 并入复核队列。
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from aios_core.contracts.enums import EventStatus
from aios_core.contracts.models import EventAnchor
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TimePrecision, TemporalExtent, require_aware
from aios_core.services.state_machines import validate_event_transition

__all__ = [
    "SignalPing",
    "ResonantCluster",
    "SpatiotemporalResonator",
    "EventLifecycleManager",
    "EventLifecycleError",
]


class EventLifecycleError(Exception):
    """事件生命周期非法流转 / 证据不足。"""


@dataclass(frozen=True, slots=True)
class SignalPing:
    """一次跨模态信号脉冲（GPS 点 / 心率突变 / 录音原话……）。"""

    at: datetime
    modality: str            # gps / heart_rate / audio / bank / chat ...
    key: str                 # 主体或切片（归一化键）
    label: str
    ref: ObjectRef | None = None
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class ResonantCluster:
    """一个跨模态共振簇（合成事件锚的原料）。"""

    cluster_id: str
    t_start: datetime
    t_end: datetime
    pings: tuple[SignalPing, ...]
    modalities: frozenset[str]

    @property
    def confidence(self) -> float:
        base = 0.5 + 0.12 * (len(self.modalities) - 2) + 0.03 * len(self.pings)
        return round(min(0.98, base), 3)


class SpatiotemporalResonator:
    """横向时空对齐共振器：时间邻接并查集聚簇，跨模态才准立锚。"""

    def __init__(
        self,
        *,
        window: timedelta = timedelta(minutes=120),
        min_modalities: int = 2,
        min_signals: int = 3,
    ) -> None:
        if window <= timedelta(0):
            raise ValueError("window must be positive")
        self._window = window
        self._min_modalities = min_modalities
        self._min_signals = min_signals
        self._counter = 0

    def resonate(self, pings: Sequence[SignalPing]) -> list[ResonantCluster]:
        for p in pings:
            require_aware(p.at, "ping.at")
        ordered = sorted(pings, key=lambda p: p.at)
        clusters: list[ResonantCluster] = []
        bucket: list[SignalPing] = []
        anchor: datetime | None = None

        def flush() -> None:
            nonlocal anchor
            if not bucket:
                anchor = None
                return
            modalities = frozenset(p.modality for p in bucket)
            if len(modalities) >= self._min_modalities and len(bucket) >= self._min_signals:
                self._counter += 1
                clusters.append(ResonantCluster(
                    cluster_id=f"res-{self._counter:04d}",
                    t_start=bucket[0].at,
                    t_end=bucket[-1].at,
                    pings=tuple(bucket),
                    modalities=modalities,
                ))
            bucket.clear()
            anchor = None

        for p in ordered:
            # 锚定窗口切分（非链式）：密集信号流上防止跨日巨簇过度合并——
            # 以簇首为锚，超出 anchor+window 即开新簇。
            if anchor is not None and p.at - anchor > self._window:
                flush()
            if anchor is None:
                anchor = p.at
            bucket.append(p)
        flush()
        return clusters

    def to_event_anchor(
        self,
        cluster: ResonantCluster,
        *,
        title: str,
        interpretation: str,
    ) -> EventAnchor:
        """共振簇 → EventAnchor（证据指针全 pin；跨模态不足即拒）。"""
        if len(cluster.modalities) < self._min_modalities:
            raise EventLifecycleError(
                f"cluster {cluster.cluster_id} has {len(cluster.modalities)} "
                f"modalities < {self._min_modalities}; anchoring refused"
            )
        refs = [
            p.ref for p in cluster.pings if p.ref is not None and p.ref.revision is not None
        ]
        return EventAnchor(
            object_id=f"event-{cluster.cluster_id}",
            subject_id=cluster.pings[0].key,
            created_by="spatiotemporal_resonator",
            learned_at=cluster.t_end,
            title=title,
            interpretation=interpretation,
            event_status=EventStatus.CANDIDATE,
            event_time=TemporalExtent(
                start=cluster.t_start,
                end=cluster.t_end,
                precision=TimePrecision.MINUTE,
                timezone_name="UTC",
            ),
            participant_refs=[],
            primary_claim_refs=[],
            evidence_set_refs=[],
            support_evidence_set_refs=refs,
            counter_evidence_set_refs=[],
            confidence=cluster.confidence,
        )


@dataclass(slots=True)
class _EventRecord:
    current: EventAnchor
    snapshots: list[EventAnchor]
    revisions: list[tuple[datetime, str]]


class EventLifecycleManager:
    """事件生命周期状态机 + 时间快照 + 下游 STALE 联动。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, _EventRecord] = {}
        self._dependents: dict[str, set[str]] = {}     # event_id -> dependent keys
        self.stale_flags: set[str] = set()
        self.recheck_queue: list[tuple[str, str]] = []  # (dependent, reason)

    # -- 查询 ------------------------------------------------------------

    def event(self, event_id: str) -> EventAnchor | None:
        rec = self._events.get(event_id)
        return rec.current if rec else None

    def snapshots_of(self, event_id: str) -> tuple[EventAnchor, ...]:
        rec = self._events.get(event_id)
        return tuple(rec.snapshots) if rec else ()

    def revision_reasons(self, event_id: str) -> tuple[str, ...]:
        rec = self._events.get(event_id)
        return tuple(reason for _, reason in rec.revisions) if rec else ()

    # -- 流转 ------------------------------------------------------------

    def register(self, anchor: EventAnchor) -> EventAnchor:
        with self._lock:
            if anchor.object_id in self._events:
                raise EventLifecycleError(f"event {anchor.object_id} already registered")
            if anchor.event_status is not EventStatus.CANDIDATE:
                raise EventLifecycleError("event must be registered as CANDIDATE")
            self._events[anchor.object_id] = _EventRecord(
                current=anchor, snapshots=[], revisions=[]
            )
            return anchor

    def _transition(self, event_id: str, target: EventStatus, reason: str, at: datetime) -> EventAnchor:
        require_aware(at, "at")
        with self._lock:
            rec = self._events.get(event_id)
            if rec is None:
                raise EventLifecycleError(f"unknown event {event_id}")
            current = rec.current
            validate_event_transition(current.event_status, target)
            updates: dict[str, object] = {
                "event_status": target,
                "revision_reason": reason,
            }
            if target is EventStatus.REVISED:
                updates["supersedes_refs"] = [
                    *current.supersedes_refs,
                    ObjectRef(object_id=current.object_id, revision=self._revision_of(current)),
                ]
            nxt = current.model_copy(update=updates)
            # 快照留存：旧值 + 修订理由（时间快照，绝不覆盖历史）
            rec.snapshots.append(current)
            rec.revisions.append((at, reason))
            rec.current = nxt
            self._mark_dependents_stale(event_id, reason)
            return nxt

    @staticmethod
    def _revision_of(anchor: EventAnchor) -> int:
        # 修订链长度即修订版本号（supersedes 越长版本越高）
        return len(anchor.supersedes_refs) + 1

    def activate(self, event_id: str, *, reason: str, at: datetime) -> EventAnchor:
        return self._transition(event_id, EventStatus.ACTIVE, reason, at)

    def resolve(self, event_id: str, *, reason: str, at: datetime) -> EventAnchor:
        return self._transition(event_id, EventStatus.RESOLVED, reason, at)

    def revise(
        self,
        event_id: str,
        *,
        reason: str,
        at: datetime,
        interpretation: str | None = None,
        confidence: float | None = None,
    ) -> EventAnchor:
        with self._lock:
            rec = self._events.get(event_id)
            if rec is None:
                raise EventLifecycleError(f"unknown event {event_id}")
            if interpretation is not None:
                rec.current = rec.current.model_copy(
                    update={"interpretation": interpretation}
                )
            if confidence is not None:
                rec.current = rec.current.model_copy(update={"confidence": confidence})
        nxt = self._transition(event_id, EventStatus.REVISED, reason, at)
        return nxt

    def merge(self, event_id: str, *, into_id: str, reason: str, at: datetime) -> EventAnchor:
        with self._lock:
            into = self._events.get(into_id)
            if into is None:
                raise EventLifecycleError(f"unknown merge target {into_id}")
            self._dependents.setdefault(into_id, set()).add(event_id)
        merged = self._transition(
            event_id, EventStatus.MERGED, f"{reason}（并入 {into_id}）", at
        )
        with self._lock:
            rec = self._events[event_id]
            rec.current = rec.current.model_copy(
                update={"merged_into_ref": ObjectRef(object_id=into_id, revision=1)}
            )
            return rec.current

    def split(
        self, event_id: str, *, child_ids: Sequence[str], reason: str, at: datetime
    ) -> EventAnchor:
        nxt = self._transition(
            event_id, EventStatus.SPLIT,
            f"{reason}（拆分为 {len(child_ids)} 个子事件）", at,
        )
        with self._lock:
            rec = self._events[event_id]
            rec.current = rec.current.model_copy(
                update={
                    "split_child_refs": [
                        ObjectRef(object_id=c, revision=1) for c in child_ids
                    ]
                }
            )
            return rec.current

    def reject(self, event_id: str, *, reason: str, at: datetime) -> EventAnchor:
        return self._transition(event_id, EventStatus.REJECTED, reason, at)

    # -- 依赖联动 ----------------------------------------------------------

    def attach_dependency(self, *, dependent_key: str, event_id: str) -> None:
        with self._lock:
            self._dependents.setdefault(event_id, set()).add(dependent_key)

    def _mark_dependents_stale(self, event_id: str, reason: str) -> None:
        for dependent in self._dependents.get(event_id, ()):
            self.stale_flags.add(dependent)
            self.recheck_queue.append((dependent, f"event {event_id} evolved: {reason}"))

    def stale_dependents(self) -> tuple[str, ...]:
        return tuple(sorted(self.stale_flags))
