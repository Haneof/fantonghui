"""M1-018 内心数据反哺与历史重估注记管线（RetroAnnotation）。

对应 R3-ARCH 蓝图 M0-027（契约）/ M3-013（管线）的 M1 阶段实现，
宪法依据：V3 §31-1（内心数据反向反哺）、§17（三类时间分离）、
§93（时间单向向前、历史不可篡改、拒绝全盘级联雪崩）。

三大铁律（工程结构保证，不依赖调用方自觉）：

1. **三不动原则**：本模块对历史对象零 UPDATE、零 DELETE、零改写。
   注记是追加式外挂图层；历史事实的物理完整性由 SHA-256 规范化摘要
   （``canonical_payload_digest`` / ``combined_history_digest``）锚定，
   注记创建时固化全量 ``integrity_anchors``，任何事后篡改可被即时证伪。

2. **双时间认知透镜（BiTemporalEpistemicLens）**：历史事实层永远完整
   存在，**只有重估注记图层**受 ``learned_at`` 可见性门控——在
   ``as_of_cutoff = T0+100 天`` 的时刻，系统忠实还原"当时确实还信任
   对方"的认知状态（active 图层为空）；``as_of_cutoff = None`` 时
   外挂重估图层精确叠加。可见性由 learned_at 门控（§17 三类时间），
   追溯适用性由 valid_time_range 声明（§31-1 倒带标注），二者严格分离。

3. **单跳隔离杜绝雪崩（SingleHopCascadeIsolator）**：反向失效只标记
   直接消费者（严格 1 跳，遍历深度由结果契约 ``Field(ge=1, le=1)``
   物理封死）。更深层的下游复核一律延迟为 AI 调度器派发的有界复核
   任务（V3 §93-3 懒加载），严禁进程内递归级联引发大模型算力雪崩。

持久化说明：注记对象的 ObjectType 纳入冻结契约属于 M0-027 增补门
（additive-only），本阶段先以进程内追加式账本（Ledger）承载，接口
形态已按世界写服务对齐；观测事实的完整性验证直接使用冻结的
``SQLiteWorldStore`` 真实引擎执行。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import require_aware

__all__ = [
    "BiTemporalEpistemicLens",
    "CanonicalIntegrityAnchor",
    "CascadeIsolationResult",
    "DuplicateAnnotationError",
    "EpistemicView",
    "MalformedIdentifierError",
    "ProtocolError",
    "RetrospectiveAnnotation",
    "RetrospectiveAnnotationLedger",
    "RetrospectiveAnnotationType",
    "SingleHopCascadeIsolator",
    "UnknownCognitionNodeError",
    "combined_history_digest",
    "canonical_payload_digest",
]

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


class RetrospectiveAnnotationType(StrEnum):
    """重估注记类型（可扩展；禁止把语义判断硬编码进本层）。"""

    JUDICIAL_FREEZE = "judicial_freeze"                      # 司法冻结/查封
    COUNTERPARTY_FRAUD_REASSESSMENT = "fraud_reassessment"   # 交易对手欺诈重估
    INNER_STATE_RETAG = "inner_state_retag"                  # 内心状态倒带标注
    TRUST_BASELINE_RESET = "trust_baseline_reset"            # 信任基线重置


class ProtocolError(Exception):
    """携带协议级错误码的领域异常（机器可分支，行为对齐 ErrorResponse）。"""

    code: ErrorCode = ErrorCode.INVALID_ARGUMENT

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, object] = context


class MalformedIdentifierError(ProtocolError):
    code = ErrorCode.INVALID_ARGUMENT


class DuplicateAnnotationError(ProtocolError):
    code = ErrorCode.IDEMPOTENCY_CONFLICT


class UnknownCognitionNodeError(ProtocolError):
    code = ErrorCode.NOT_FOUND


def _require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedIdentifierError(
            f"{field} must be a non-empty string", field=field
        )
    if value != value.strip() or any(ch.isspace() for ch in value):
        raise MalformedIdentifierError(
            f"{field} must not contain whitespace", field=field
        )
    return value


# ----------------------------------------------------------------------
# 规范化物理摘要（SHA-256）
# ----------------------------------------------------------------------

def canonical_payload_digest(payload: Mapping[str, Any]) -> str:
    """单个世界对象载荷的规范化 SHA-256 物理摘要。

    规范化：键排序 + 紧凑分隔符 + UTF-8，保证同载荷同摘要（跨进程、
    跨时间可重放）。任何字段级改动（哪怕一个字符）都会改变摘要。
    """
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def combined_history_digest(digest_by_object_id: Mapping[str, str]) -> str:
    """全量历史链的组合摘要：逐对象摘要按 object_id 排序后再级联哈希。

    顺序无关（按 ID 排序），因此对读取顺序不敏感；任一对象被篡改、
    缺失或新增都会改变组合摘要。
    """
    joined = "".join(
        f"{object_id}:{digest}\n"
        for object_id, digest in sorted(digest_by_object_id.items())
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class CanonicalIntegrityAnchor(BaseModel):
    """注记创建时固化的单对象完整性锚（object_id -> 规范化 SHA-256）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: StrictStr
    payload_sha256: StrictStr = Field(min_length=64, max_length=64)


# ----------------------------------------------------------------------
# RetrospectiveAnnotation 一等对象
# ----------------------------------------------------------------------

class RetrospectiveAnnotation(BaseModel):
    """倒带重估注记：只追加、不改写历史的外挂认知图层（V3 §31-1）。

    时间语义（严格对应 §17 三类时间）：
    - ``occurred_at``：触发重估的现实事件（如司法裁定下达）发生时间；
    - ``learned_at``：系统获知该重估事实的时间——**可见性门控字段**；
    - ``recorded_at``：本注记写入账本的时间；
    - ``valid_from / valid_until``：注记追溯适用的历史时间窗
      （[T0, T_today]），**适用性声明**，不参与可见性判定。

    ``integrity_anchors`` 固化创建时刻全部相关历史对象的物理摘要，
    构成"历史未被本注记触碰"的可验证证据。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: StrictStr
    subject_entity_id: StrictStr
    annotation_type: RetrospectiveAnnotationType
    headline: StrictStr = Field(min_length=1)
    notes: tuple[StrictStr, ...] = Field(default=())
    valid_from: datetime
    valid_until: datetime
    occurred_at: datetime
    learned_at: datetime
    recorded_at: datetime
    source_refs: tuple[ObjectRef, ...] = Field(default=())
    target_object_refs: tuple[ObjectRef, ...] = Field(default=())
    integrity_anchors: tuple[CanonicalIntegrityAnchor, ...] = Field(default=())
    created_by: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def validate_annotation_contract(self) -> "RetrospectiveAnnotation":
        for name in (
            "valid_from",
            "valid_until",
            "occurred_at",
            "learned_at",
            "recorded_at",
        ):
            require_aware(getattr(self, name), name)
        if self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be before valid_from")
        if self.valid_until > self.learned_at:
            raise ValueError(
                "retroactive applicability window cannot extend beyond the"
                " moment the system learned the annotation (learned_at)"
            )
        if self.learned_at > self.recorded_at:
            raise ValueError("learned_at must not be after recorded_at")
        for ref in (*self.source_refs, *self.target_object_refs):
            if ref.revision is None:
                raise ValueError(
                    "annotation refs require pinned ObjectRef revisions"
                    " (history must be cited at an exact version)"
                )
        _require_identifier(self.annotation_id, "annotation_id")
        _require_identifier(self.subject_entity_id, "subject_entity_id")
        return self


# ----------------------------------------------------------------------
# 追加式注记账本
# ----------------------------------------------------------------------

class RetrospectiveAnnotationLedger:
    """只追加（append-only）的重估注记账本。

    刻意**不提供**任何 update/delete/retract 接口——撤销重估的唯一合法
    途径是再追加一条新注记（认知随时间向前演化，V3 §93）。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, RetrospectiveAnnotation] = {}
        self._order: list[RetrospectiveAnnotation] = []

    def append(self, annotation: RetrospectiveAnnotation) -> bool:
        """追加一条注记。同 ID 同内容 = 幂等无操作；同 ID 异内容 = 冲突。"""
        _require_identifier(annotation.annotation_id, "annotation_id")
        with self._lock:
            existing = self._by_id.get(annotation.annotation_id)
            if existing is not None:
                if existing == annotation:
                    return False
                raise DuplicateAnnotationError(
                    "annotation_id already exists with different content",
                    annotation_id=annotation.annotation_id,
                )
            self._by_id[annotation.annotation_id] = annotation
            self._order.append(annotation)
            return True

    def append_all(
        self, annotations: Iterable[RetrospectiveAnnotation]
    ) -> int:
        appended = 0
        for annotation in annotations:
            if self.append(annotation):
                appended += 1
        return appended

    def __len__(self) -> int:
        with self._lock:
            return len(self._order)

    def annotations_active_at(
        self, as_of_cutoff: datetime | None
    ) -> tuple[RetrospectiveAnnotation, ...]:
        """双时间可见性过滤：learned_at <= cutoff 的注记才进入认知图层。

        ``as_of_cutoff=None`` 表示"当下"（以账本全部注记为界）。
        """
        if as_of_cutoff is not None:
            require_aware(as_of_cutoff, "as_of_cutoff")
        with self._lock:
            if as_of_cutoff is None:
                return tuple(self._order)
            return tuple(
                a for a in self._order if a.learned_at <= as_of_cutoff
            )

    def annotations_for_subject(
        self,
        subject_entity_id: str,
        as_of_cutoff: datetime | None = None,
    ) -> tuple[RetrospectiveAnnotation, ...]:
        _require_identifier(subject_entity_id, "subject_entity_id")
        return tuple(
            a
            for a in self.annotations_active_at(as_of_cutoff)
            if a.subject_entity_id == subject_entity_id
        )


# ----------------------------------------------------------------------
# 双时间认知透镜
# ----------------------------------------------------------------------

class EpistemicView(BaseModel):
    """某一认知时点的世界透镜快照。

    ``active_annotations`` 是该时点可见的重估注记图层；
    ``suppressed_annotations`` 是该时点**尚未获知**（learned_at >
    cutoff）的注记——它们的存在本身证明透镜没有偷看未来。
    ``historical_fact_layer_intact`` 恒为 True：事实本体存于世界存储，
    透镜只引用不复制、只加层不改写。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    view_cutoff: datetime
    active_annotations: tuple[RetrospectiveAnnotation, ...] = Field(default=())
    suppressed_annotations: tuple[StrictStr, ...] = Field(default=())
    historical_fact_layer_intact: Literal[True] = True


class BiTemporalEpistemicLens:
    """双时间认知透镜：任意 as_of_cutoff 下精准还原当时的认知状态。

    透镜**永远不过滤历史事实层**——事实在 T0+100 天时系统"确实还不知
    情"，这正是 §31-1 要求忠实还原的商业信任状态；透镜只对**重估注记
    图层**执行 learned_at 门控。
    """

    def __init__(self, ledger: RetrospectiveAnnotationLedger) -> None:
        self._ledger = ledger

    def view(
        self,
        as_of_cutoff: datetime | None,
        *,
        subject_entity_id: str | None = None,
        now: datetime | None = None,
    ) -> EpistemicView:
        if as_of_cutoff is not None:
            require_aware(as_of_cutoff, "as_of_cutoff")
        if now is not None:
            require_aware(now, "now")
        resolved = as_of_cutoff if as_of_cutoff is not None else now
        if resolved is None:
            resolved = max(
                (a.learned_at for a in self._ledger.annotations_active_at(None)),
                default=_EPOCH_UTC,
            )
        if subject_entity_id is not None:
            every = self._ledger.annotations_for_subject(subject_entity_id, None)
        else:
            every = self._ledger.annotations_active_at(None)
        active = tuple(a for a in every if a.learned_at <= resolved)
        suppressed = tuple(
            a.annotation_id for a in every if a.learned_at > resolved
        )
        return EpistemicView(
            view_cutoff=resolved,
            active_annotations=active,
            suppressed_annotations=suppressed,
            historical_fact_layer_intact=True,
        )


# ----------------------------------------------------------------------
# 单跳级联隔离器
# ----------------------------------------------------------------------

class CascadeIsolationResult(BaseModel):
    """单跳反向失效结果。

    ``traversal_hops`` 的契约域是 ``[1, 1]``——**遍历深度被物理封死为
    1**，任何未来改动试图递归级联都必须先修改此契约（代码评审可见）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_node_id: StrictStr
    stale_node_ids: tuple[StrictStr, ...] = Field(default=())
    marked_stale_count: StrictInt = Field(ge=0)
    traversal_hops: StrictInt = Field(default=1, ge=1, le=1)
    suppressed_cascade_count: StrictInt = Field(
        ge=0,
        description="被隔离而未访问的传递下游节点数（算力雪崩扼杀量）",
    )
    elapsed_ms: float = Field(ge=0.0)


class SingleHopCascadeIsolator:
    """依赖网络的单跳反向失效隔离器。

    反向失效语义：当源认知（如"合伙人可信"）被推翻，**只有直接消费它
    的一级节点**被标记 ``is_stale=True``；二级及更深的传递下游保持
    原状，等待 AI 调度器按需派发有界复核任务（V3 §93-3 懒加载评估，
    拒绝全盘级联雪崩）。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nodes: dict[str, bool] = {}             # node_id -> is_stale
        self._consumers_of: dict[str, set[str]] = {}  # 被消费 -> {直接消费者}

    def register_node(self, node_id: str) -> None:
        _require_identifier(node_id, "node_id")
        with self._lock:
            self._nodes.setdefault(node_id, False)

    def register_dependency(self, consumer_id: str, consumed_id: str) -> None:
        """登记一条"消费者 → 被消费认知"的直接依赖边（幂等）。"""
        _require_identifier(consumer_id, "consumer_id")
        _require_identifier(consumed_id, "consumed_id")
        with self._lock:
            self._nodes.setdefault(consumer_id, False)
            self._nodes.setdefault(consumed_id, False)
            self._consumers_of.setdefault(consumed_id, set()).add(consumer_id)

    @property
    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    def is_stale(self, node_id: str) -> bool:
        _require_identifier(node_id, "node_id")
        with self._lock:
            if node_id not in self._nodes:
                raise UnknownCognitionNodeError(
                    "node is not registered", node_id=node_id
                )
            return self._nodes[node_id]

    def stale_nodes(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(n for n, stale in self._nodes.items() if stale)
            )

    def invalidate_direct_consumers(
        self, source_node_id: str
    ) -> CascadeIsolationResult:
        """反向失效：严格单跳。多级传播被结构性禁止（不是性能优化，是铁律）。"""
        started = time.perf_counter()
        _require_identifier(source_node_id, "source_node_id")
        with self._lock:
            if source_node_id not in self._nodes:
                raise UnknownCognitionNodeError(
                    "source node is not registered", node_id=source_node_id
                )
            direct = self._consumers_of.get(source_node_id, set())
            for consumer in direct:
                self._nodes[consumer] = True
            suppressed = len(self._nodes) - 1 - len(direct)
            elapsed = (time.perf_counter() - started) * 1000.0
            return CascadeIsolationResult(
                source_node_id=source_node_id,
                stale_node_ids=tuple(sorted(direct)),
                marked_stale_count=len(direct),
                traversal_hops=1,
                suppressed_cascade_count=max(suppressed, 0),
                elapsed_ms=round(elapsed, 6),
            )
