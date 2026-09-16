"""M1-018 认知反向传播语义图层契约（老王案 / 历史不可篡改铁律）。

落实宪法第 93 条与用户最高指示：

> "只标记当前时间节点的事件，老王是骗子这个标签，没必要回去把所有对话都改成老王是骗子！"
> "推翻历史认知时，新认知只追加在今天，严禁倒写历史！"

工程承诺（四大硬门禁）：

1. **历史事实字节级不可变**：过去 730 天的 18,000 条原始 Observation 事实经
   ``ImmutableFactLedger`` 写入时即做全记录规范字节 SHA-256 物理哈希封存；
   追加式账本 API 面上**不存在** update/delete/覆盖类方法（物理抹掉
   SQL UPDATE / DELETE 攻击面）；新裁定进入后全部历史哈希 100% 一致。
2. **今天打标签**：今天只写入一条 ``RetrospectiveAnnotation``：
   ``learned_at = T_today``、``valid_time_range = [T0, T_today]``，
   挂载"司法冻结查封与欺诈重估"外挂解释图层，指向过去、绝不触碰过去；
   注记模型 frozen，落库后不可倒改（严禁倒写历史）。
3. **双时间认知透镜** ``BiTemporalEpistemicLens``（事件时间 × 知识时间）：
   - ``as_of_cutoff = T0 + 100 天`` → "当时已知视图"：``active_annotations``
     必为空，忠实还原用户当时的真实商业信任状态（老王彼时是可信合伙人）；
   - ``as_of_cutoff = None`` → "当前认知视图"：历史事实完整保留 + 外挂重估
     图层精确叠加，历史曲线原貌不受任何破坏。
4. **单跳级联隔离** ``SingleHopCascadeIsolator``：反向失效严格 1 跳——
   仅把直接消费该认知的 1 级节点标记 ``is_stale=True``（万级 5 层依赖网络中
   严格等于 10 个），遍历深度严格为 1，大模型重算触发次数严格为 0，
   彻底掐灭旧式无界级联递归导致的 210 次（10 一级 + 200 二级）API 算力雪崩。

生产接线说明：``ImmutableFactLedger`` 是 SQLite 追加式版本库物理哈希层的
内存物化契约——每条账目与追加式事实行一一对应，哈希即完整性审计唯一依据；
本模块不直接访问 SQLite，保持 C02 存储底座与 C05 复盘回溯层的边界清晰。
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AnnotationBudgetExceededError",
    "AnnotationConflictError",
    "AnnotationRegistry",
    "BiTemporalEpistemicLens",
    "CascadeIsolationError",
    "EpistemicWorldLens",
    "HistoricalFact",
    "HistoricalSliceView",
    "ImmutableFactLedger",
    "InvalidationReport",
    "LedgerConflictError",
    "RetrospectiveAnnotation",
    "SingleHopCascadeIsolator",
]

from .epistemic_world_lens import EpistemicWorldLens


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime, field_name: str) -> datetime:
    """归一化为 aware UTC（naive 一律按 UTC 解释，与全仓时间契约一致）。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ----------------------------------------------------------------------
# 核心数据模型
# ----------------------------------------------------------------------


class RetrospectiveAnnotation(BaseModel):
    """今天的"外挂解释图层"（Retrospective Annotation）。

    宪法语义：
    - ``learned_at`` 永远是"今天"（认知获知时刻），绝不倒填历史时间；
    - ``target_time_start / target_time_end`` 是指向过去时空切片的指针
      （valid_time_range = [T0, T_today]），只标记、不修改被指向的事实；
    - 模型 frozen：落库后任何字段改写都会失败（严禁倒写历史）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    semantic_overlay: str = Field(
        ..., description="挂载的解释图层，如'司法冻结查封确认欺诈'（欺诈重估注记）"
    )
    target_time_start: datetime
    target_time_end: datetime
    learned_at: datetime = Field(default_factory=_utc_now)
    recorded_at: datetime = Field(
        default_factory=_utc_now,
        description="注记落账时间；缺省时经 _align_recorded_at 与 learned_at 对齐（learned_at = recorded_at = T_today）",
    )
    source_statement_ref: str = Field(
        min_length=1, description="新认知来源指针（如司法裁定书编号）"
    )

    @model_validator(mode="before")
    @classmethod
    def _align_recorded_at(cls, data: Any) -> Any:
        """agent-05 增量硬化：对齐 learned_at/recorded_at 双时间戳。

        云端工单原文：自身的 learned_at = recorded_at = T_now（今天的时间戳）。
        缺省规则（不依赖真实时钟，保证冻结时刻测试的确定性）：
        - 两者皆缺 → 取同一 now 锚点；
        - 仅 recorded_at 缺 → 回填 learned_at（显式的『今天只写在今天』）；
        - 仅 learned_at 缺 → 回填 recorded_at。
        """
        if isinstance(data, dict):
            learned = data.get("learned_at")
            recorded = data.get("recorded_at")
            if learned is None and recorded is None:
                now = _utc_now()
                data = {**data, "learned_at": now, "recorded_at": now}
            elif recorded is None:
                data = {**data, "recorded_at": learned}
            elif learned is None:
                data = {**data, "learned_at": recorded}
        return data

    @model_validator(mode="after")
    def _validate_time_contract(self) -> "RetrospectiveAnnotation":
        try:
            inverted = self.target_time_start > self.target_time_end
        except TypeError as exc:
            raise ValueError(
                "target_time_start/target_time_end must share comparable timezone awareness"
            ) from exc
        if inverted:
            raise ValueError("target_time_start must not be after target_time_end")

        # agent-05 增量硬化（认知单向向前，严禁倒写历史）：
        learned_utc = _as_aware_utc(self.learned_at, "learned_at")
        recorded_utc = _as_aware_utc(self.recorded_at, "recorded_at")
        target_end_utc = _as_aware_utc(self.target_time_end, "target_time_end")
        if recorded_utc < learned_utc:
            raise ValueError("recorded_at must be >= learned_at")
        if learned_utc < target_end_utc:
            raise ValueError(
                "learned_at must be >= target_time_end: 回溯注记只能在目标切片"
                "结束之后学到（learned_at = T_today），严禁假装当时就已知晓"
            )
        return self


@dataclass(frozen=True)
class HistoricalFact:
    """不可变历史事实（Observation 链元素，只读视图）。

    ``payload`` 属性每次访问都从账本封存的规范字节重建全新副本，
    调用方任何篡改都无法污染账本原件。
    """

    fact_id: str
    entity_id: str
    occurred_at: datetime
    kind: str
    sha256: str
    _payload_bytes: bytes = field(repr=False, compare=False, default=b"{}")

    @property
    def payload(self) -> Dict[str, Any]:
        return json.loads(self._payload_bytes)


# ----------------------------------------------------------------------
# 门禁 1：追加式事实账本（SHA-256 物理哈希封存，API 面无 UPDATE/DELETE）
# ----------------------------------------------------------------------


class LedgerConflictError(ValueError):
    """同一 fact_id 已封存且内容不一致：原始事实不可覆盖。"""


@dataclass(frozen=True)
class _FactEntry:
    fact_id: str
    entity_id: str
    occurred_at: datetime
    kind: str
    payload_bytes: bytes
    canonical_bytes: bytes
    sha256: str


class ImmutableFactLedger:
    """追加式（append-only）历史事实账本。

    宪法承诺：
    - API 面只有"追加"与"读取"，物理上不存在 update / delete / 覆盖方法，
      从类型系统层面抹掉 SQL UPDATE / DELETE 攻击面；
    - 每条事实在写入瞬间对全记录规范字节计算 SHA-256 物理哈希并封存，
      哈希是历史完整性审计的唯一依据（verify_integrity 可随时重算比对）。
    """

    def __init__(self) -> None:
        self._entries: Dict[str, _FactEntry] = {}

    # ---------------- 追加（唯一的写入口） ----------------

    def record_fact(
        self,
        *,
        fact_id: str,
        entity_id: str,
        occurred_at: datetime,
        kind: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """追加封存一条原始事实，返回其 SHA-256 物理哈希。

        同一 fact_id 重复追加：内容逐字节一致 → 幂等返回原哈希；
        内容不一致 → 抛出 LedgerConflictError（原始事实永存，不可覆盖）。
        """
        if not isinstance(fact_id, str) or not fact_id.strip():
            raise ValueError("fact_id must be a non-empty string")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("entity_id must be a non-empty string")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("kind must be a non-empty string")
        payload = payload or {}
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON-object dict")

        occurred_utc = _as_aware_utc(occurred_at, "occurred_at")
        payload_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        record = {
            "fact_id": fact_id,
            "entity_id": entity_id,
            "occurred_at": occurred_utc.isoformat(),
            "kind": kind,
            "payload": json.loads(payload_bytes),
        }
        canonical = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()

        existing = self._entries.get(fact_id)
        if existing is not None:
            if existing.canonical_bytes != canonical:
                raise LedgerConflictError(
                    f"fact {fact_id!r} is already sealed with different content; "
                    "historical facts are immutable and may not be overwritten"
                )
            return existing.sha256

        self._entries[fact_id] = _FactEntry(
            fact_id=fact_id,
            entity_id=entity_id,
            occurred_at=occurred_utc,
            kind=kind,
            payload_bytes=payload_bytes,
            canonical_bytes=canonical,
            sha256=digest,
        )
        return digest

    def record_facts(self, records: Iterable[Dict[str, Any]]) -> List[str]:
        """批量追加，按输入顺序返回哈希列表。"""
        return [self.record_fact(**record) for record in records]

    # ---------------- 只读查询与完整性审计 ----------------

    def count(self) -> int:
        return len(self._entries)

    def get_hash(self, fact_id: str) -> str:
        try:
            return self._entries[fact_id].sha256
        except KeyError:
            raise KeyError(f"unknown fact_id: {fact_id!r}") from None

    def all_hashes(self) -> Dict[str, str]:
        """全部 (fact_id -> SHA-256) 快照：历史不可变性的指纹矩阵。"""
        return {fact_id: entry.sha256 for fact_id, entry in self._entries.items()}

    def aggregate_fingerprint(self) -> str:
        """全体记录哈希按 fact_id 序拼接后的总指纹（单一数字锚点）。"""
        joined = "\n".join(
            f"{fact_id}:{entry.sha256}"
            for fact_id, entry in sorted(self._entries.items())
        )
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def verify_integrity(self, fact_ids: Optional[Iterable[str]] = None) -> Tuple[bool, int]:
        """对封存字节重算 SHA-256 并与封存哈希比对。返回 (是否全部一致, 检查条数)。"""
        if fact_ids is None:
            targets = list(self._entries.items())
        else:
            targets = [(fid, self._entries[fid]) for fid in fact_ids]
        checked = 0
        for fact_id, entry in targets:
            recomputed = hashlib.sha256(entry.canonical_bytes).hexdigest()
            if recomputed != entry.sha256:
                return False, checked
            checked += 1
        return True, checked

    def facts_for(
        self,
        entity_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Tuple[HistoricalFact, ...]:
        """读取某实体在 [start, end] 时间窗内的不可变事实（按事件时间升序）。

        返回只读视图：``payload`` 每次访问均从封存字节重建，篡改不外泄。
        """
        start_utc = _as_aware_utc(start, "start") if start is not None else None
        end_utc = _as_aware_utc(end, "end") if end is not None else None
        picked = [
            entry
            for entry in self._entries.values()
            if entry.entity_id == entity_id
            and (start_utc is None or entry.occurred_at >= start_utc)
            and (end_utc is None or entry.occurred_at <= end_utc)
        ]
        picked.sort(key=lambda e: (e.occurred_at, e.fact_id))
        return tuple(
            HistoricalFact(
                fact_id=e.fact_id,
                entity_id=e.entity_id,
                occurred_at=e.occurred_at,
                kind=e.kind,
                sha256=e.sha256,
                _payload_bytes=e.payload_bytes,
            )
            for e in picked
        )


# ----------------------------------------------------------------------
# 门禁 2：外挂解释图层注册表（只追加，严禁倒写历史）
# ----------------------------------------------------------------------


class AnnotationConflictError(ValueError):
    """annotation_id 冲突：外挂图层只能追加新注记，不可覆盖既有注记。"""


class AnnotationBudgetExceededError(ValueError):
    """每实体外挂图层预算超限：注记风暴被物理拒绝（认知更新必须有界、可审计）。"""


class AnnotationRegistry:
    """外挂解释图层注册表（append-only）。

    - 注记一旦写入即不可修改（模型 frozen + 注册表只存深拷贝）；
    - 新的重估只能作为新注记追加，绝不倒改、绝不"撤回"历史图层
      （认知修正 = 追加新认知，而不是篡改旧认知）；
    - 每实体注记数带硬预算（``max_per_entity``），无界注记风暴 fail-closed 拒绝。
    """

    def __init__(self, *, max_per_entity: int = 64) -> None:
        if not isinstance(max_per_entity, int) or max_per_entity < 1:
            raise ValueError("max_per_entity must be an int >= 1")
        self._max_per_entity = max_per_entity
        self._items: Dict[str, RetrospectiveAnnotation] = {}

    def append(self, annotation: RetrospectiveAnnotation) -> RetrospectiveAnnotation:
        if annotation.annotation_id in self._items:
            raise AnnotationConflictError(
                f"annotation {annotation.annotation_id!r} already exists; "
                "overlays are append-only, re-annotation must use a new annotation_id"
            )
        entity_count = sum(
            1
            for existing in self._items.values()
            if existing.target_entity_id == annotation.target_entity_id
        )
        if entity_count >= self._max_per_entity:
            raise AnnotationBudgetExceededError(
                f"annotation budget for entity {annotation.target_entity_id!r} exhausted "
                f"({entity_count}/{self._max_per_entity}); unbounded annotation storms are rejected"
            )
        stored = annotation.model_copy(deep=True)
        self._items[stored.annotation_id] = stored
        return stored

    def get(self, annotation_id: str) -> RetrospectiveAnnotation:
        try:
            return self._items[annotation_id]
        except KeyError:
            raise KeyError(f"unknown annotation_id: {annotation_id!r}") from None

    def all(self) -> Tuple[RetrospectiveAnnotation, ...]:
        return tuple(
            sorted(
                self._items.values(),
                key=lambda a: (_as_aware_utc(a.learned_at, "learned_at"), a.annotation_id),
            )
        )

    def for_entity(self, entity_id: str) -> Tuple[RetrospectiveAnnotation, ...]:
        return tuple(a for a in self.all() if a.target_entity_id == entity_id)

    def count(self) -> int:
        return len(self._items)


# ----------------------------------------------------------------------
# 门禁 3：双时间认知透镜（事件时间 × 知识时间）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalSliceView:
    """双时间透镜查询结果：历史切片事实 × 该知识时刻可见的外挂图层。"""

    entity_id: str
    slice_start: Optional[datetime]
    slice_end: datetime
    knowledge_cutoff: datetime
    view_kind: str  # "AS_OF"（当时已知视图） | "CURRENT"（当前认知视图）
    facts: Tuple[HistoricalFact, ...]
    active_annotations: Tuple[RetrospectiveAnnotation, ...]

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    @property
    def has_overlay(self) -> bool:
        return len(self.active_annotations) > 0


def _ranges_overlap(
    a_start: Optional[datetime], a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    if a_start is not None and b_end < a_start:
        return False
    if b_start > a_end:
        return False
    return True


class BiTemporalEpistemicLens:
    """双时间认知透镜：事件时间（occurred_at）× 知识时间（learned_at）。

    - 给定 ``as_of_cutoff``（"当时已知视图"）：只返回该知识时刻之前已发生的
      事实，且只叠加该知识时刻之前已获知的注记 —— 忠实还原历史认知原貌；
    - ``as_of_cutoff=None``（"当前认知视图"）：知识截止 = 当前时刻，历史事实
      完整保留，外挂重估图层精确叠加，历史曲线原貌不受任何破坏。
    """

    def __init__(
        self,
        ledger: ImmutableFactLedger,
        registry: AnnotationRegistry,
        *,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._ledger = ledger
        self._registry = registry
        self._clock = clock or _utc_now

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime,
        target_time_end: Optional[datetime] = None,
        *,
        as_of_cutoff: Optional[datetime] = None,
    ) -> HistoricalSliceView:
        """查询历史切片。

        - 仅传 ``target_time``：累积切片 (−∞, target_time]（该时刻的完整认知状态）；
        - 传 ``target_time + target_time_end``：显式区间 [start, end]；
        - ``as_of_cutoff`` 为知识时间截止；None = 当前。
        """
        if target_time_end is None:
            slice_start: Optional[datetime] = None
            slice_end = target_time
        else:
            slice_start = target_time
            slice_end = target_time_end
            try:
                if slice_start > slice_end:
                    raise ValueError("target_time must not be after target_time_end")
            except TypeError as exc:
                raise ValueError(
                    "target_time and target_time_end must share comparable timezone awareness"
                ) from exc

        knowledge_cutoff = _as_aware_utc(
            as_of_cutoff if as_of_cutoff is not None else self._clock(),
            "as_of_cutoff",
        )

        window_facts = self._ledger.facts_for(entity_id, slice_start, slice_end)
        # 双时间正确性：知识截止之前的"事件时间"事实才"当时已知"
        facts = tuple(
            fact for fact in window_facts if fact.occurred_at <= knowledge_cutoff
        )

        active: List[RetrospectiveAnnotation] = []
        for annotation in self._registry.for_entity(entity_id):
            learned = _as_aware_utc(annotation.learned_at, "learned_at")
            if learned > knowledge_cutoff:
                continue  # 该知识时刻尚未获知此重估 —— 不叠加（还原当时认知）
            if not _ranges_overlap(
                slice_start,
                slice_end,
                _as_aware_utc(annotation.target_time_start, "target_time_start"),
                _as_aware_utc(annotation.target_time_end, "target_time_end"),
            ):
                continue  # 图层未覆盖所查询切片
            active.append(annotation)

        return HistoricalSliceView(
            entity_id=entity_id,
            slice_start=slice_start,
            slice_end=_as_aware_utc(slice_end, "target_time"),
            knowledge_cutoff=knowledge_cutoff,
            view_kind="AS_OF" if as_of_cutoff is not None else "CURRENT",
            facts=facts,
            active_annotations=tuple(active),
        )


# ----------------------------------------------------------------------
# 门禁 4：单跳级联隔离器（杜绝 210 次大模型算力雪崩）
# ----------------------------------------------------------------------


class CascadeIsolationError(ValueError):
    """级联隔离违宪请求：只允许 1 跳反向失效，无界级联递归重算被物理拒绝。"""


@dataclass(frozen=True)
class InvalidationReport:
    """反向失效审计报告：谁被标记、遍历多深、触发多少次重算。"""

    origin_id: str
    marked_stale: Tuple[str, ...]
    traversal_depth_reached: int
    nodes_visited: int
    llm_recompute_triggered: int
    cascade_suppressed: bool
    untouched_downstream: int


class SingleHopCascadeIsolator:
    """单跳级联隔离器（宪法：绝对禁止无界级联递归重算历史）。

    依赖网络语义：``add_dependency(upstream, downstream)`` 表示 downstream
    的认知消费（依赖）upstream。对 origin 执行反向失效时：

    - 仅把**直接**消费 origin 的 1 级下游节点标记 ``is_stale=True``；
    - 遍历深度严格为 1：不进入二级及以下任何节点，不触发任何大模型重算
      （旧式无界级联在 10+200 的 1/2 级网络上会产生 210 次 API 雪崩）；
    - 要求 ``max_hops > 1`` 的调用被 fail-closed 拒绝，零违宪妥协；
    - 深层节点保持完好：它们的失效必须等待各自的 1 跳直接上游被标记后，
      由调度器在**未来的独立预算窗口**内单跳处理（逐级、可审计、不递归）。
    """

    _ALLOWED_MAX_HOPS = 1

    def __init__(self) -> None:
        self._nodes: set = set()
        self._consumers: Dict[str, set] = {}
        self._stale: Dict[str, datetime] = {}
        self._last_report: Optional[InvalidationReport] = None

    # ---------------- 依赖网络注册 ----------------

    def register_node(self, node_id: str) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        self._nodes.add(node_id)

    def add_dependency(self, upstream_id: str, downstream_id: str) -> None:
        """downstream 的认知依赖（消费）upstream。"""
        if upstream_id == downstream_id:
            raise ValueError("a node cannot depend on itself")
        self.register_node(upstream_id)
        self.register_node(downstream_id)
        self._consumers.setdefault(upstream_id, set()).add(downstream_id)

    # ---------------- 状态查询 ----------------

    def node_count(self) -> int:
        return len(self._nodes)

    def direct_consumers(self, node_id: str) -> Tuple[str, ...]:
        if node_id not in self._nodes:
            raise KeyError(f"unknown node_id: {node_id!r}")
        return tuple(sorted(self._consumers.get(node_id, ())))

    def is_stale(self, node_id: str) -> bool:
        return node_id in self._stale

    def stale_nodes(self) -> frozenset:
        return frozenset(self._stale)

    # ---------------- 单跳反向失效 ----------------

    def reverse_invalidate(self, origin_id: str, *, max_hops: int = 1) -> InvalidationReport:
        """对 origin 认知执行反向失效。严格单跳，返回审计报告。"""
        if max_hops != self._ALLOWED_MAX_HOPS:
            raise CascadeIsolationError(
                f"unbounded cascade is forbidden by constitution: max_hops must be "
                f"{self._ALLOWED_MAX_HOPS}, got {max_hops} (拒绝无界级联递归重算)"
            )
        if origin_id not in self._nodes:
            raise KeyError(f"unknown node_id: {origin_id!r}")

        direct = self.direct_consumers(origin_id)
        marked_at = _utc_now()
        for node_id in direct:
            self._stale[node_id] = marked_at

        untouched = len(self._nodes) - 1 - len(direct)
        report = InvalidationReport(
            origin_id=origin_id,
            marked_stale=direct,
            traversal_depth_reached=1 if direct else 0,
            nodes_visited=len(direct),
            llm_recompute_triggered=0,
            cascade_suppressed=True,
            untouched_downstream=untouched,
        )
        self._last_report = report
        return report

    @property
    def last_report(self) -> Optional[InvalidationReport]:
        return copy.deepcopy(self._last_report) if self._last_report is not None else None
