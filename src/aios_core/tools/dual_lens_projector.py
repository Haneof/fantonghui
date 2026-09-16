"""双透镜虚拟索引投影器（DualLensVirtualIndexProjector）—— 海量盲测新工具发明 #2。

宪法第二十三条（Reinterpretation 外挂解释层）与铁律 2（历史绝不篡改，只在
今天打标签）的读面工程件：

- **AsKnown 透镜**：历史在当时被知道的樣子——只含事实本身，绝不混入后世注解；
- **Annotated 透镜**：今天（T_now）的认知——事实 + 只读外挂注解的联合视图；
- 两个透镜都是**虚拟投影**：只从不可变事实账本与注解注册表读取并投影，
  任何一次投影前后，历史总指纹（SHA-256 聚合）必须逐字节不变；
- 注解引发的下游失效只许走单跳隔离器（SingleHopCascadeIsolator），
  遍历深度 == 1、大模型重算触发次数受常数预算约束，
  彻底掐灭旧式无界级联的 210 次 API 算力雪崩。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional, Set, Tuple

from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    ImmutableFactLedger,
    InvalidationReport,
    SingleHopCascadeIsolator,
)


class LensKind(StrEnum):
    AS_KNOWN = "as_known"
    ANNOTATED = "annotated"


@dataclass(frozen=True)
class VirtualProjection:
    """某一透镜在某一时刻的只读虚拟视图（绝不物化改写历史）。"""

    lens: str
    built_at: datetime
    fact_count: int
    history_fingerprint: str
    annotated_fact_ids: Tuple[str, ...]  # 在该视图下携带外挂注解的事实
    annotation_count: int
    overlay_entries: Tuple[Tuple[str, str], ...]  # (fact_id, annotation_id)

    @property
    def is_pure_history(self) -> bool:
        return self.annotation_count == 0


class LensConsistencyError(RuntimeError):
    """双透镜一致性被破坏（历史指纹漂移/越界注解）时抛出。"""


class DualLensVirtualIndexProjector:
    """在不可变账本 + 注解注册表之上投影 AS_KNOWN / ANNOTATED 双读面。"""

    def __init__(
        self,
        ledger: ImmutableFactLedger,
        registry: AnnotationRegistry,
        isolator: Optional[SingleHopCascadeIsolator] = None,
    ) -> None:
        self.ledger = ledger
        self.registry = registry
        self.isolator = isolator or SingleHopCascadeIsolator()
        self._projections: List[VirtualProjection] = []

    # ------------------------------------------------------------------
    def project(self, lens: LensKind, *, now: Optional[datetime] = None) -> VirtualProjection:
        t_now = now or datetime.now(timezone.utc)
        fingerprint_before = self.ledger.aggregate_fingerprint()

        annotations = self.registry.all()
        overlay: List[Tuple[str, str]] = []
        annotated_ids: Set[str] = set()
        for anno in annotations:
            if lens == LensKind.AS_KNOWN and anno.learned_at > t_now:
                continue  # AsKnown 透镜：注解诞生晚于被注视时刻 -> 历史视图不可见
            target = str(anno.target_entity_id)
            overlay.append((target, anno.annotation_id))
            annotated_ids.add(target)

        projection = VirtualProjection(
            lens=lens.value,
            built_at=t_now,
            fact_count=self.ledger.count(),
            history_fingerprint=self.ledger.aggregate_fingerprint(),
            annotated_fact_ids=tuple(sorted(annotated_ids)),
            annotation_count=len(overlay),
            overlay_entries=tuple(sorted(overlay)),
        )

        fingerprint_after = self.ledger.aggregate_fingerprint()
        if fingerprint_before != fingerprint_after or fingerprint_before != projection.history_fingerprint:
            raise LensConsistencyError(
                f"投影 {lens.value} 导致历史指纹漂移：{fingerprint_before} -> {fingerprint_after}"
            )
        self._projections.append(projection)
        return projection

    # ------------------------------------------------------------------
    def consistency_check(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        """双透镜数据一致性体检：AS_KNOWN ⊆ ANNOTATED，且历史指纹恒定。"""
        as_known = self.project(LensKind.AS_KNOWN, now=now)
        annotated = self.project(LensKind.ANNOTATED, now=now)
        subset_ok = set(as_known.annotated_fact_ids) <= set(annotated.annotated_fact_ids)
        fingerprint_ok = as_known.history_fingerprint == annotated.history_fingerprint
        return {
            "as_known_annotations": as_known.annotation_count,
            "annotated_annotations": annotated.annotation_count,
            "subset_ok": subset_ok,
            "fingerprint_ok": fingerprint_ok,
            "consistent": subset_ok and fingerprint_ok,
        }

    # ------------------------------------------------------------------
    def register_dependency_graph(self, dependencies: Dict[str, List[str]]) -> None:
        """登记事实依赖网络（downstream 认知消费 upstream）。"""
        for upstream, downstreams in dependencies.items():
            self.isolator.register_node(upstream)
            for downstream in downstreams:
                self.isolator.register_node(downstream)
                self.isolator.add_dependency(upstream, downstream)

    def invalidate_single_hop(self, origin_fact_id: str) -> InvalidationReport:
        """注解落地后对直接下游做单跳失效：深度恒 1，0 次无界级联。"""
        report = self.isolator.reverse_invalidate(origin_fact_id, max_hops=1)
        if report.traversal_depth_reached > 1 or not report.cascade_suppressed:
            raise LensConsistencyError(
                f"单跳隔离失效：深度 {report.traversal_depth_reached}，级联抑制 {report.cascade_suppressed}"
            )
        return report
