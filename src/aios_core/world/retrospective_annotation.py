"""M1-018 认知反向传播语义图层契约（复盘注记 + 双时间透镜 + 单跳失效隔离）。

工单：``governance/dispatches/TASK_DISPATCH_AGENT_5_M1_018.md``
融合档案：``docs/fusion_dossier/02_*`` M1-018 行（``ADD``/``P1``，严格禁止修改底层 Observation）
定案来源：``docs/fusion_dossier/04_*`` 争议二 —— 终审采纳**严格单跳（1-Hop）**依赖失效隔离

宪法级铁律（本模块逐条落地）
--------------------------------------------------------------------------
1. **历史事实绝对不可变（第 93 条 / 老大铁律 #2）**
   过去发生的客观事实（``Observation``）**字节级不可改写**：本模块不执行、也不允许
   任何 ``UPDATE`` / ``DELETE``，世界写入唯一入口仍是 ``SQLiteWorldStore.commit()``
   的**追加**语义。历史是否被改写由 :class:`ObservationHashLedger` 用 SHA-256 逐条
   物理哈希**独立举证**，一旦发现不一致立即抛 :class:`HistoryMutationDetectedError`。
2. **新认知只追加在今天（"今天打标签"）**
   推翻历史认知时只写一条 :class:`RetrospectiveAnnotation`：``learned_at = recorded_at = T_now``，
   ``valid_time_range`` 指向被重新解释的过去时空切片；严禁倒写历史
   （``learned_at < target_time_end`` 直接拒绝，抛 :class:`RetroactiveWriteDeniedError`）。
3. **双时间认知透镜（BiTemporalEpistemicLens）**
   ``valid time``（事实发生）与 ``knowledge time``（当时已知）正交：
   * ``as_of_cutoff = T_k``：只返回 ``learned_at <= T_k`` 的物理事实与当时已存在的注记
     —— 忠实还原**当时的人生状态**（``active_annotations`` 为空 = 当时并不知道后来发生的事）；
   * ``as_of_cutoff = None``：返回**当前认知**，历史事实原貌完整保留，仅**叠加**外挂解释图层。
   两种视图下同一条历史事实的物理哈希必须逐字节一致（历史曲线不被任何注记污染）。
4. **单跳隔离，杜绝算力雪崩（SingleHopCascadeIsolator）**
   反向失效**只标记直接消费该认知的 1 级下游节点**，遍历深度严格为 1；
   长尾下游不递归、不重算，进入有界延迟队列（并发重算预算 <= 3，长尾由后台分批消化）。
   本层**绝不触发任何大模型调用**（``llm_calls_issued == 0``）；
   标记路径成本只与"1 + 直接下游数"有关，与全图规模无关。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from bisect import bisect_right
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts import Claim, SourceRef, TemporalExtent
from aios_core.contracts.enums import ClaimType, ErrorCode, KnowledgeState, ObjectType
from aios_core.contracts.time import TimePrecision, as_utc, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "ANNOTATION_SCHEMA_TAG",
    "DEFAULT_CASCADE_AUDIT_BUDGET",
    "MAX_RECOMPUTE_CONCURRENCY",
    "SINGLE_HOP_MAX_DEPTH",
    "AnnotationKind",
    "AnnotationReceipt",
    "BiTemporalEpistemicLens",
    "CognitiveNode",
    "DeferredRecomputeBatch",
    "DependencyEdge",
    "DuplicateAnnotationError",
    "EpistemicSlice",
    "EpistemicWorldLens",
    "HashLedgerDiff",
    "HistoryMutationDetectedError",
    "InvalidationReport",
    "KnowledgeMode",
    "ObservationHashLedger",
    "PhysicalChainIndex",
    "PhysicalObservation",
    "RetroactiveWriteDeniedError",
    "RetrospectiveAnnotation",
    "RetrospectiveAnnotationLog",
    "RetrospectiveAnnotationWriter",
    "SingleHopCascadeIsolator",
    "UnknownTargetEntityError",
    "annotations_from_store",
    "invalidate_overturned_fact_single_hop",
    "observations_linked_to_entity",
]

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 注记对象在 ``Claim.metadata`` 中的模式标记（用于把普通 Claim 与复盘注记区分开）。
ANNOTATION_SCHEMA_TAG: Final[str] = "aios.m1_018.retrospective_annotation/v1"

#: 主裁定（dossier 04 争议二）：并发重算节点严格 <= 3。
MAX_RECOMPUTE_CONCURRENCY: Final[int] = 3

#: 单跳隔离的遍历深度上界（恒为 1：只标记直接消费该认知的节点）。
SINGLE_HOP_MAX_DEPTH: Final[int] = 1

#: "若级联会波及多少节点"这一**审计统计**的默认扫描预算。
#: 审计只影响报告里的规模数字，**不参与标记**；超出预算时按预算给出下界并显式上报。
DEFAULT_CASCADE_AUDIT_BUDGET: Final[int] = 10_000


# ---------------------------------------------------------------------------
# 异常（统一走 AIOSProtocolError 协议）
# ---------------------------------------------------------------------------


class HistoryMutationDetectedError(AIOSProtocolError):
    """历史被改写（SHA-256 物理哈希不一致）——最高级别违约，必须立即中断。"""

    def __init__(self, diff: Any, context: Mapping[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "reason": "history_mutation_detected",
            "root_hash_before": getattr(diff, "root_hash_before", None),
            "root_hash_after": getattr(diff, "root_hash_after", None),
            "mismatched_ids": list(getattr(diff, "mismatched_ids", ()))[:20],
            "missing_ids": list(getattr(diff, "missing_ids", ()))[:20],
            "mismatched_count": len(getattr(diff, "mismatched_ids", ())),
            "missing_count": len(getattr(diff, "missing_ids", ())),
        }
        if context:
            payload.update(context)
        super().__init__(ErrorCode.VERSION_CONFLICT, "history ledger mismatch detected", context=payload)


class RetroactiveWriteDeniedError(AIOSProtocolError):
    """严禁倒写历史：注记的认知时间不得早于被注记事实区间的结束（老大铁律 #2）。"""

    def __init__(self, learned_at: datetime, target_time_end: datetime) -> None:
        super().__init__(
            ErrorCode.PERMISSION_DENIED,
            "retroactive annotation is forbidden; new cognition may only be appended today",
            context={
                "reason": "retroactive_write_denied",
                "learned_at": learned_at.isoformat(),
                "target_time_end": target_time_end.isoformat(),
            },
        )


class UnknownTargetEntityError(AIOSProtocolError):
    def __init__(self, entity_id: str) -> None:
        super().__init__(
            ErrorCode.NOT_FOUND,
            "target entity is unknown to the epistemic lens",
            context={"reason": "unknown_target_entity", "entity_id": entity_id},
        )


class DuplicateAnnotationError(AIOSProtocolError):
    def __init__(self, annotation_id: str) -> None:
        super().__init__(
            ErrorCode.IDEMPOTENCY_CONFLICT,
            "annotation_id already exists in the append-only annotation log",
            context={"reason": "duplicate_annotation", "annotation_id": annotation_id},
        )


class AnnotationChainBrokenError(AIOSProtocolError):
    def __init__(self, index: int, expected: str, actual: str) -> None:
        super().__init__(
            ErrorCode.VERSION_CONFLICT,
            "annotation log is not a valid append-only hash chain",
            context={
                "reason": "annotation_chain_broken",
                "broken_index": index,
                "expected_chain_hash": expected,
                "actual_chain_hash": actual,
            },
        )


# ---------------------------------------------------------------------------
# 规范化 / 哈希工具
# ---------------------------------------------------------------------------


def _canonical_bytes(payload: Any) -> bytes:
    """稳定字节序列（键序固定、无多余空白、UTF-8）：哈希与比对只认字节。"""
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_aware(value: datetime, field_name: str) -> datetime:
    require_aware(value, field_name)
    return as_utc(value, field_name)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else as_utc(value, "value").isoformat()


def _parse_moment(value: Any) -> datetime | None:
    """把存储读回的时点（ISO 字符串或 datetime）解析为 aware UTC。

    存储层以 ``canonical_utc_iso`` 写入（``...Z``），这里必须兼容字符串；
    无时区信息时按 UTC 处理（存储写入侧已强制 aware，此分支仅防御）。
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _extent_bounds(extent: Any) -> tuple[datetime | None, datetime | None]:
    """从（dict / TemporalExtent）里取 (start, end)；未知时间返回 (None, None)。"""
    if extent is None:
        return (None, None)
    if isinstance(extent, TemporalExtent):
        if extent.unknown:
            return (None, None)
        return (extent.start, extent.end)
    if isinstance(extent, Mapping):
        if extent.get("unknown"):
            return (None, None)
        return (_parse_moment(extent.get("start")), _parse_moment(extent.get("end")))
    return (None, None)


# ===========================================================================
# 一、复盘注记契约（"今天打标签"）
# ===========================================================================


class AnnotationKind(StrEnum):
    """解释图层类型（高熵商业场景：司法查封 / 欺诈重估 / 平反恢复）。"""

    JUDICIAL_FREEZE = "judicial_freeze"          # 司法查封、冻结、查封裁定
    FRAUD_REASSESSMENT = "fraud_reassessment"    # 欺诈重估（事后发现系蓄意隐瞒）
    REPUTATION_RESTORATION = "reputation_restoration"  # 平反：事后证明清白
    CUSTOM = "custom"


class KnowledgeMode(StrEnum):
    HISTORICAL = "historical"
    CURRENT = "current"


class RetrospectiveAnnotation(BaseModel):
    """复盘注记：**只追加在今天**的外挂解释图层（绝不回写历史事实）。

    字段沿用工单骨架（``annotation_id`` / ``target_entity_id`` / ``semantic_overlay`` /
    ``target_time_start`` / ``target_time_end`` / ``learned_at`` / ``source_statement_ref``），
    并补充类型、置信度与二次标记位。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    semantic_overlay: str = Field(min_length=1, description="挂载的解释图层，如'疑似欺诈'")
    target_time_start: datetime
    target_time_end: datetime
    learned_at: datetime
    source_statement_ref: str = Field(min_length=1)
    recorded_at: datetime | None = None
    annotation_kind: AnnotationKind = AnnotationKind.FRAUD_REASSESSMENT
    secondary_kinds: tuple[AnnotationKind, ...] = ()
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    claimant_id: str = Field(default="core_review", min_length=1)

    # ---- 时间与派生 ----

    @model_validator(mode="after")
    def validate_bitemporal_rules(self) -> Self:
        _require_aware(self.target_time_start, "target_time_start")
        _require_aware(self.target_time_end, "target_time_end")
        _require_aware(self.learned_at, "learned_at")
        if as_utc(self.target_time_end, "target_time_end") < as_utc(
            self.target_time_start, "target_time_start"
        ):
            raise ValueError("target_time_end must not be before target_time_start")
        # 铁律：新认知只追加在今天，严禁倒写历史。
        if as_utc(self.learned_at, "learned_at") < as_utc(self.target_time_end, "target_time_end"):
            raise RetroactiveWriteDeniedError(self.learned_at, self.target_time_end)
        if self.recorded_at is not None:
            _require_aware(self.recorded_at, "recorded_at")
            if as_utc(self.recorded_at, "recorded_at") < as_utc(self.learned_at, "learned_at"):
                raise ValueError("recorded_at must be >= learned_at")
        return self

    @property
    def valid_time_range(self) -> tuple[datetime, datetime]:
        """有效时间区间 = 被重新解释的过去时空切片（工单要求 [T0, T_today]）。"""
        return (self.target_time_start, self.target_time_end)

    @property
    def knowledge_time(self) -> datetime:
        """认知时间 = 这条标签"是什么时候知道的"（只有今天）。"""
        return self.learned_at

    @property
    def effective_recorded_at(self) -> datetime:
        return self.recorded_at if self.recorded_at is not None else self.learned_at

    @property
    def kinds(self) -> tuple[AnnotationKind, ...]:
        ordered = (self.annotation_kind, *self.secondary_kinds)
        return tuple(dict.fromkeys(ordered))

    @property
    def content_hash(self) -> str:
        """内容指纹：取**有效记录时间**（``recorded_at`` 未填时等于 ``learned_at``）。

        这样"未显式填写"与"显式填写同一时刻"必然得到同一指纹，注记经
        ``to_claim`` -> 存储 -> ``from_claim_payload`` 往返后仍可比对。
        """
        projection = self.model_dump(mode="json")
        projection["recorded_at"] = _iso(self.effective_recorded_at)
        return _sha256_hex(_canonical_bytes(projection))

    def overlaps(self, window_start: datetime, window_end: datetime) -> bool:
        """该注记覆盖的过去切片是否与查询窗口相交。"""
        return (
            as_utc(self.target_time_start, "target_time_start")
            <= as_utc(window_end, "window_end")
            and as_utc(self.target_time_end, "target_time_end")
            >= as_utc(window_start, "window_start")
        )

    # ---- 持久化适配（复用冻结契约，不新增 ObjectType）----

    def to_claim(
        self,
        *,
        subject_id: str,
        created_by: str,
        object_id: str | None = None,
        asserted_at: datetime | None = None,
    ) -> Claim:
        """映射为世界对象 ``Claim``（append-only 追加，绝不修改任何既有对象）。

        * ``valid_time``   <- ``valid_time_range``（有效时间：被注记的过去）
        * ``learned_at``   <- 今天（认知时间：何时知道）
        * ``claim_type``   <- ``INFERENCE``（事后推断，不是当时的事实）
        * ``knowledge_state`` <- ``HYPOTHESIS``（已挂证据假设，可被后续事实修订）
        """
        return Claim(
            object_id=object_id or self.annotation_id,
            subject_id=subject_id,
            learned_at=self.learned_at,
            recorded_at=self.effective_recorded_at,
            created_by=created_by,
            claimant_id=self.claimant_id,
            claim_type=ClaimType.INFERENCE,
            content=self.semantic_overlay,
            valid_time=TemporalExtent(
                start=self.target_time_start,
                end=self.target_time_end,
                precision=TimePrecision.SECOND,
            ),
            asserted_at=asserted_at or self.learned_at,
            knowledge_state=KnowledgeState.HYPOTHESIS,
            confidence=self.confidence,
            source_refs=[SourceRef(object_id=self.source_statement_ref, revision=None)],
            metadata={
                ANNOTATION_SCHEMA_TAG: {
                    "annotation_id": self.annotation_id,
                    "target_entity_id": self.target_entity_id,
                    "target_time_start": _iso(self.target_time_start),
                    "target_time_end": _iso(self.target_time_end),
                    "learned_at": _iso(self.learned_at),
                    "recorded_at": _iso(self.effective_recorded_at),
                    "source_statement_ref": self.source_statement_ref,
                    "annotation_kind": self.annotation_kind.value,
                    "secondary_kinds": [kind.value for kind in self.secondary_kinds],
                    "confidence": self.confidence,
                    "content_hash": self.content_hash,
                }
            },
        )

    @classmethod
    def from_claim_payload(cls, payload: Mapping[str, Any]) -> Self | None:
        """把存储读回的 Claim 载荷还原为注记；非注记返回 ``None``（不猜、不吞）。"""
        if not isinstance(payload, Mapping):
            return None
        meta = payload.get("metadata")
        if not isinstance(meta, Mapping):
            return None
        tag = meta.get(ANNOTATION_SCHEMA_TAG)
        if not isinstance(tag, Mapping):
            return None

        valid_start, valid_end = _extent_bounds(payload.get("valid_time"))
        learned_at = _parse_moment(tag.get("learned_at")) or _parse_moment(payload.get("learned_at"))
        recorded_at = _parse_moment(tag.get("recorded_at")) or _parse_moment(
            payload.get("recorded_at")
        )
        start = _parse_moment(tag.get("target_time_start")) or valid_start
        end = _parse_moment(tag.get("target_time_end")) or valid_end
        content = payload.get("content")
        annotation_id = tag.get("annotation_id") or payload.get("object_id")
        target_entity = tag.get("target_entity_id")
        source_ref = tag.get("source_statement_ref")
        if not all(
            isinstance(value, str) and value
            for value in (annotation_id, target_entity, content, source_ref)
        ):
            return None
        if learned_at is None or start is None or end is None:
            return None
        secondary: tuple[AnnotationKind, ...] = ()
        raw_secondary = tag.get("secondary_kinds")
        if isinstance(raw_secondary, list):
            secondary = tuple(
                AnnotationKind(item) for item in raw_secondary if item in set(AnnotationKind)
            )
        raw_kind = tag.get("annotation_kind")
        kind = (
            AnnotationKind(raw_kind)
            if isinstance(raw_kind, str) and raw_kind in set(AnnotationKind)
            else AnnotationKind.FRAUD_REASSESSMENT
        )
        raw_confidence = tag.get("confidence")
        return cls(
            annotation_id=annotation_id,
            target_entity_id=target_entity,
            semantic_overlay=content,
            target_time_start=start,
            target_time_end=end,
            learned_at=learned_at,
            recorded_at=recorded_at if recorded_at is not None else learned_at,
            source_statement_ref=source_ref,
            annotation_kind=kind,
            secondary_kinds=secondary,
            confidence=float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.9,
            claimant_id=str(payload.get("claimant_id") or "core_review"),
        )


def annotations_from_store(store: Any) -> tuple[RetrospectiveAnnotation, ...]:
    """从世界存储里读出全部复盘注记（按认知时间升序，确定性）。"""
    payloads = store.list_payloads(object_type=ObjectType.CLAIM)
    found: list[RetrospectiveAnnotation] = []
    for payload in payloads:
        annotation = RetrospectiveAnnotation.from_claim_payload(payload)
        if annotation is not None:
            found.append(annotation)
    found.sort(key=lambda item: (as_utc(item.learned_at, "learned_at"), item.annotation_id))
    return tuple(found)


class RetrospectiveAnnotationLog:
    """只追加的注记日志（哈希链自证不可篡改）。

    * 追加：写入一条注记即产生一个 ``chain_hash``，与前一条链接；
    * 只读：``visible_at`` / ``active_for`` 提供双时间可见性视图；
    * 自证：``assert_chain_intact`` 重算全链，任何插入/改写/删除都会被抓到。
    """

    def __init__(self, annotations: Iterable[RetrospectiveAnnotation] = ()) -> None:
        self._entries: list[RetrospectiveAnnotation] = []
        self._chain: list[str] = []
        self._by_id: dict[str, RetrospectiveAnnotation] = {}
        self._lock = threading.RLock()
        for annotation in annotations:
            self.append(annotation)

    # ---- 写路径（只追加）----

    def append(self, annotation: RetrospectiveAnnotation) -> str:
        """追加一条注记，返回其链哈希；重复 id 直接拒绝（幂等冲突显式化）。"""
        with self._lock:
            if annotation.annotation_id in self._by_id:
                raise DuplicateAnnotationError(annotation.annotation_id)
            previous = self._chain[-1] if self._chain else "genesis"
            chain_hash = _sha256_hex(
                _canonical_bytes({"previous": previous, "annotation": annotation.content_hash})
            )
            self._entries.append(annotation)
            self._chain.append(chain_hash)
            self._by_id[annotation.annotation_id] = annotation
            return chain_hash

    # ---- 读路径 ----

    @property
    def entries(self) -> tuple[RetrospectiveAnnotation, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def head_hash(self) -> str:
        return self._chain[-1] if self._chain else "genesis"

    def chain_hashes(self) -> tuple[str, ...]:
        return tuple(self._chain)

    def get(self, annotation_id: str) -> RetrospectiveAnnotation | None:
        return self._by_id.get(annotation_id)

    def visible_at(self, cutoff: datetime | None) -> tuple[RetrospectiveAnnotation, ...]:
        """认知时间 <= cutoff 的注记（``None`` = 当前视图，返回全部）。"""
        if cutoff is None:
            return self.entries
        bound = _require_aware(cutoff, "cutoff")
        return tuple(a for a in self._entries if as_utc(a.learned_at, "learned_at") <= bound)

    def active_for(
        self,
        entity_id: str,
        window_start: datetime,
        window_end: datetime,
        cutoff: datetime | None,
    ) -> tuple[RetrospectiveAnnotation, ...]:
        """在给定查询窗口与认知截止下**生效**的注记。"""
        return tuple(
            a
            for a in self.visible_at(cutoff)
            if a.target_entity_id == entity_id and a.overlaps(window_start, window_end)
        )

    def suppressed_for(
        self,
        entity_id: str,
        window_start: datetime,
        window_end: datetime,
        cutoff: datetime | None,
    ) -> tuple[RetrospectiveAnnotation, ...]:
        """当前视图已存在、但在 cutoff 时点尚未出现的注记（"当时并不知道"）。"""
        if cutoff is None:
            return ()
        bound = _require_aware(cutoff, "cutoff")
        return tuple(
            a
            for a in self._entries
            if a.target_entity_id == entity_id
            and a.overlaps(window_start, window_end)
            and as_utc(a.learned_at, "learned_at") > bound
        )

    # ---- 完整性自证 ----

    def assert_chain_intact(self) -> None:
        previous = "genesis"
        for index, (entry, stored) in enumerate(zip(self._entries, self._chain, strict=True)):
            expected = _sha256_hex(
                _canonical_bytes({"previous": previous, "annotation": entry.content_hash})
            )
            if expected != stored:
                raise AnnotationChainBrokenError(index, expected, stored)
            previous = stored


# ===========================================================================
# 二、物理事实的 SHA-256 台账（历史不可篡改的独立举证）
# ===========================================================================


class HashLedgerDiff(BaseModel):
    """历史哈希台账的比对结果（逐条 + 聚合）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    matched: int = Field(ge=0)
    mismatched_ids: tuple[str, ...] = ()
    missing_ids: tuple[str, ...] = ()
    added_ids: tuple[str, ...] = ()
    root_hash_before: str = Field(min_length=1)
    root_hash_after: str = Field(min_length=1)
    hash_mode: str = Field(min_length=1)

    @property
    def unchanged(self) -> bool:
        return not self.mismatched_ids and not self.missing_ids

    @property
    def identical(self) -> bool:
        """连"新增"都没有（严格全等）。"""
        return self.unchanged and not self.added_ids


class ObservationHashLedger:
    """客观事实的 SHA-256 物理台账。

    两种模式，语义必须说清（绝不模糊）：

    * ``mode="raw"``：哈希**存储层原始字节**（如 ``object_revisions.payload_json`` 文本），
      这是最严格的"物理哈希"，能抓到任何字节级改写；
    * ``mode="canonical"``：哈希**规范化 JSON 字节**（键序固定 / 无空白 / UTF-8），
      与存储实现解耦，跨序列化器稳定。

    比对时模式必须一致；``root_hash`` 可逐字节复现。
    """

    def __init__(
        self,
        entries: Mapping[str, str],
        *,
        mode: str,
        captured_at: datetime | None = None,
        label: str = "observations",
    ) -> None:
        self._entries: dict[str, str] = dict(entries)
        self._mode = mode
        self._captured_at = captured_at or utc_now()
        self._label = label
        self._root = self._compute_root(self._entries)

    # ---- 构造 ----

    @classmethod
    def capture(
        cls,
        payloads: Iterable[Mapping[str, Any]],
        *,
        captured_at: datetime | None = None,
        label: str = "observations",
    ) -> ObservationHashLedger:
        """按规范化 JSON 字节捕获（存储无关，读取的载荷即可用）。"""
        entries = {
            str(payload["object_id"]): _sha256_hex(_canonical_bytes(payload))
            for payload in payloads
            if isinstance(payload, Mapping) and isinstance(payload.get("object_id"), str)
        }
        return cls(entries, mode="canonical", captured_at=captured_at, label=label)

    @classmethod
    def from_raw_payloads(
        cls,
        raw_payloads: Mapping[str, str | bytes],
        *,
        captured_at: datetime | None = None,
        label: str = "observations",
    ) -> ObservationHashLedger:
        """按存储层**原始字节**捕获（最严格的物理哈希）。"""
        entries = {
            object_id: _sha256_hex(raw.encode("utf-8") if isinstance(raw, str) else raw)
            for object_id, raw in raw_payloads.items()
        }
        return cls(entries, mode="raw", captured_at=captured_at, label=label)

    # ---- 属性 ----

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def root_hash(self) -> str:
        return self._root

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def captured_at(self) -> datetime:
        return self._captured_at

    @property
    def label(self) -> str:
        return self._label

    def entry_hash(self, object_id: str) -> str | None:
        return self._entries.get(object_id)

    def entries(self) -> Mapping[str, str]:
        return dict(self._entries)

    @staticmethod
    def _compute_root(entries: Mapping[str, str]) -> str:
        lines = "\n".join(f"{oid}\t{digest}" for oid, digest in sorted(entries.items()))
        return _sha256_hex(lines.encode("utf-8"))

    # ---- 比对 ----

    def verify(self, payloads: Iterable[Mapping[str, Any]]) -> HashLedgerDiff:
        """用当前读回的载荷重新哈希，与台账逐条比对（台账本身不被修改）。"""
        if self._mode != "canonical":
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "verify() re-hashes canonical payloads; use verify_raw() for raw-byte ledgers",
                context={"reason": "ledger_mode_mismatch", "mode": self._mode},
            )
        return self._diff(
            {
                str(payload["object_id"]): _sha256_hex(_canonical_bytes(payload))
                for payload in payloads
                if isinstance(payload, Mapping) and isinstance(payload.get("object_id"), str)
            }
        )

    def verify_raw(self, raw_payloads: Mapping[str, str | bytes]) -> HashLedgerDiff:
        """用存储层原始字节重新哈希比对（与 :meth:`from_raw_payloads` 成对使用）。"""
        if self._mode != "raw":
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "verify_raw() requires a raw-byte ledger",
                context={"reason": "ledger_mode_mismatch", "mode": self._mode},
            )
        return self._diff(
            {
                object_id: _sha256_hex(raw.encode("utf-8") if isinstance(raw, str) else raw)
                for object_id, raw in raw_payloads.items()
            }
        )

    def _diff(self, current: Mapping[str, str]) -> HashLedgerDiff:
        mismatched = sorted(
            oid for oid, digest in self._entries.items() if oid in current and current[oid] != digest
        )
        missing = sorted(oid for oid in self._entries if oid not in current)
        added = sorted(oid for oid in current if oid not in self._entries)
        matched = sum(1 for oid, digest in self._entries.items() if current.get(oid) == digest)
        return HashLedgerDiff(
            total=len(self._entries),
            matched=matched,
            mismatched_ids=tuple(mismatched),
            missing_ids=tuple(missing),
            added_ids=tuple(added),
            root_hash_before=self._root,
            root_hash_after=self._compute_root(current),
            hash_mode=self._mode,
        )

    def assert_unchanged(
        self, payloads: Iterable[Mapping[str, Any]], *, context: Mapping[str, Any] | None = None
    ) -> HashLedgerDiff:
        """核对历史完整；一旦不一致立即抛 :class:`HistoryMutationDetectedError`。"""
        diff = self.verify(payloads)
        if not diff.unchanged:
            raise HistoryMutationDetectedError(diff, context)
        return diff

    def assert_unchanged_raw(
        self,
        raw_payloads: Mapping[str, str | bytes],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> HashLedgerDiff:
        diff = self.verify_raw(raw_payloads)
        if not diff.unchanged:
            raise HistoryMutationDetectedError(diff, context)
        return diff


# ===========================================================================
# 三、双时间认知透镜
# ===========================================================================


class PhysicalObservation(BaseModel):
    """物理事实的只读投影（内容原貌，永不被注记改写）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = Field(min_length=1)
    occurred_start: datetime | None = None
    occurred_end: datetime | None = None
    learned_at: datetime
    recorded_at: datetime | None = None
    source_kind: str | None = None
    modality: str | None = None
    unit: str | None = None
    caption: str = ""
    revision: int = Field(default=1, ge=1)
    content_hash: str = Field(min_length=1)


class EpistemicSlice(BaseModel):
    """查询结果：同一物理事实在两种认知视图下的**忠实还原 + 外挂图层**。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    knowledge_mode: KnowledgeMode
    as_of_cutoff: datetime | None = None
    target_time_start: datetime
    target_time_end: datetime

    physical_observations: tuple[PhysicalObservation, ...] = ()
    physical_count: int = Field(ge=0)
    suppressed_by_cutoff: int = Field(ge=0)
    stored_observation_total: int = Field(ge=0)

    active_annotations: tuple[RetrospectiveAnnotation, ...] = ()
    suppressed_annotations: tuple[RetrospectiveAnnotation, ...] = ()
    overlay_applied: bool

    physical_chain_hash: str = Field(min_length=1)
    full_chain_hash: str = Field(min_length=1)
    physical_hashes: dict[str, str] = Field(default_factory=dict)

    @property
    def active_annotation_count(self) -> int:
        return len(self.active_annotations)

    @property
    def history_preserved(self) -> bool:
        """历史原貌是否完整保留（可见 + 被认知截止隐藏 = 存储中该实体的全量事实）。"""
        return self.physical_count + self.suppressed_by_cutoff == self.stored_observation_total

    def hash_of(self, observation_id: str) -> str | None:
        return self.physical_hashes.get(observation_id)


class PhysicalChainIndex:
    """客观事实链的**内存派生**索引：实体 -> 按发生时间有序的事实（可重建）。

    只读设施：绝无 UPDATE / DELETE，世界本体仍由 ``SQLiteWorldStore`` 独占写入。
    查询热路径只碰原始数组（``_ids/_starts/_ends/_learned``），不进 Pydantic。
    """

    def __init__(
        self,
        payloads: Iterable[Mapping[str, Any]],
        *,
        entity_links: Mapping[str, Sequence[str]] | None = None,
        subject_field: str = "subject_id",
    ) -> None:
        materialized = [payload for payload in payloads if isinstance(payload, Mapping)]

        records: dict[str, PhysicalObservation] = {}
        hashes: dict[str, str] = {}
        subjects: dict[str, str] = {}

        for payload in materialized:
            observation_id = payload.get("object_id")
            if not isinstance(observation_id, str) or not observation_id:
                continue
            start, end = _extent_bounds(payload.get("occurred"))
            learned_at = _parse_moment(payload.get("learned_at")) or start
            if learned_at is None:
                # 无认知时间亦无发生时间：无法参与双时间视图，如实跳过（不猜时间）。
                continue
            if start is None:
                start = learned_at
            if end is None:
                end = start
            digest = _sha256_hex(_canonical_bytes(payload))
            records[observation_id] = PhysicalObservation(
                observation_id=observation_id,
                occurred_start=start,
                occurred_end=end,
                learned_at=learned_at,
                recorded_at=_parse_moment(payload.get("recorded_at")),
                source_kind=(
                    payload.get("source_kind")
                    if isinstance(payload.get("source_kind"), str)
                    else None
                ),
                modality=(
                    payload.get("modality") if isinstance(payload.get("modality"), str) else None
                ),
                unit=payload.get("unit") if isinstance(payload.get("unit"), str) else None,
                caption=payload.get("value") if isinstance(payload.get("value"), str) else "",
                revision=int(payload.get("revision") or 1),
                content_hash=digest,
            )
            hashes[observation_id] = digest
            subject = payload.get(subject_field)
            subjects[observation_id] = subject if isinstance(subject, str) else ""

        # 实体归属：显式链接表优先（来自 C06 结构化引用链）；否则退回 subject_id。
        per_entity: dict[str, list[str]] = {}
        if entity_links is not None:
            for entity_id, observation_ids in entity_links.items():
                per_entity.setdefault(entity_id, []).extend(
                    oid for oid in observation_ids if oid in records
                )
        else:
            for observation_id, subject in subjects.items():
                if subject:
                    per_entity.setdefault(subject, []).append(observation_id)

        # 每个实体建立按发生时间升序的确定性序列；查询期只碰原始数组（不进 Pydantic）。
        ordered: dict[str, tuple[str, ...]] = {}
        starts: dict[str, tuple[datetime, ...]] = {}
        ends: dict[str, tuple[datetime, ...]] = {}
        learned: dict[str, tuple[datetime, ...]] = {}
        for entity_id, ids in per_entity.items():
            sequence = sorted(
                set(ids),
                key=lambda oid: (records[oid].occurred_start or records[oid].learned_at, oid),
            )
            ordered[entity_id] = tuple(sequence)
            starts[entity_id] = tuple(
                records[oid].occurred_start or records[oid].learned_at for oid in sequence
            )
            ends[entity_id] = tuple(
                records[oid].occurred_end or records[oid].occurred_start or records[oid].learned_at
                for oid in sequence
            )
            learned[entity_id] = tuple(records[oid].learned_at for oid in sequence)

        self._records = records
        self._hashes = hashes
        self._subjects = subjects
        self._subject_field = subject_field
        self._ordered = ordered
        self._starts = starts
        self._ends = ends
        self._learned = learned
        self._chain_hash_cache: dict[str, str] = {}
        self._ledger = ObservationHashLedger(
            hashes,
            mode="canonical",
            captured_at=utc_now(),
            label="physical_chain",
        )

    # ---- 只读访问 ----

    @property
    def ledger(self) -> ObservationHashLedger:
        """全量物理事实台账（历史不可篡改的比对基准）。"""
        return self._ledger

    @property
    def observation_total(self) -> int:
        return len(self._records)

    def entity_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._ordered))

    def observation_ids(self, entity_id: str) -> tuple[str, ...]:
        if entity_id not in self._ordered:
            raise UnknownTargetEntityError(entity_id)
        return self._ordered[entity_id]

    def record(self, observation_id: str) -> PhysicalObservation | None:
        return self._records.get(observation_id)

    def entity_chain_hash(self, entity_id: str) -> str:
        """该实体全量事实（不受认知截止影响）的台账指纹；构建后不变，故记忆化。"""
        cached = self._chain_hash_cache.get(entity_id)
        if cached is not None:
            return cached
        ids = self.observation_ids(entity_id)
        lines = "\n".join(f"{oid}\t{self._hashes[oid]}" for oid in ids)
        digest = _sha256_hex(lines.encode("utf-8"))
        self._chain_hash_cache[entity_id] = digest
        return digest

    def slice(
        self,
        entity_id: str,
        window_start: datetime,
        window_end: datetime,
        as_of_cutoff: datetime | None = None,
    ) -> tuple[tuple[PhysicalObservation, ...], int]:
        """按窗口与认知截止取事实：返回 (可见事实, 因认知截止而被隐藏的事实数)。"""
        ordered = self.observation_ids(entity_id)
        starts = self._starts[entity_id]
        ends = self._ends[entity_id]
        learned = self._learned[entity_id]
        records = self._records

        lower_bound = as_utc(window_start, "window_start")
        upper = bisect_right(starts, as_utc(window_end, "window_end"))

        visible_ids: list[str] = []
        suppressed = 0
        if as_of_cutoff is None:
            for index in range(upper):
                if ends[index] >= lower_bound:
                    visible_ids.append(ordered[index])
        else:
            cutoff = as_utc(as_of_cutoff, "as_of_cutoff")
            for index in range(upper):
                if ends[index] < lower_bound:
                    continue
                if learned[index] > cutoff:
                    suppressed += 1
                else:
                    visible_ids.append(ordered[index])
        return tuple(records[oid] for oid in visible_ids), suppressed


class BiTemporalEpistemicLens:
    """双时间认知透镜：``valid time``（事实发生） x ``knowledge time``（当时已知）。

    铁律实现要点：
    * 物理事实**只读投影**，任何注记都不修改其内容与哈希；
    * 注记只在 ``learned_at <= as_of_cutoff``（或 ``None`` = 当前）时生效；
    * ``as_of_cutoff`` 视图下"当时还不知道"的事实与注记都必须不可见（忠实还原）。
    """

    def __init__(
        self,
        index: PhysicalChainIndex,
        *,
        annotations: RetrospectiveAnnotationLog | Iterable[RetrospectiveAnnotation] = (),
    ) -> None:
        self._index = index
        self._log = (
            annotations
            if isinstance(annotations, RetrospectiveAnnotationLog)
            else RetrospectiveAnnotationLog(annotations)
        )
        self._lock = threading.RLock()

    # ---- 构造 ----

    @classmethod
    def from_store(
        cls,
        store: Any,
        *,
        entity_links: Mapping[str, Sequence[str]] | None = None,
        annotations: Iterable[RetrospectiveAnnotation] | None = None,
    ) -> BiTemporalEpistemicLens:
        """从世界存储重建（只读：``list_payloads``，绝不写库）。

        ``annotations=None`` 时自动从存储中的复盘注记 Claim 还原（同一世界、单一真源）。
        """
        payloads = store.list_payloads(object_type=ObjectType.OBSERVATION)
        if annotations is None:
            annotations = annotations_from_store(store)
        return cls(
            PhysicalChainIndex(payloads, entity_links=entity_links),
            annotations=annotations,
        )

    # ---- 只读访问 ----

    @property
    def index(self) -> PhysicalChainIndex:
        return self._index

    @property
    def log(self) -> RetrospectiveAnnotationLog:
        return self._log

    @property
    def history_ledger(self) -> ObservationHashLedger:
        return self._index.ledger

    # ---- 主入口（工单骨架签名）----

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime | tuple[datetime, datetime] | TemporalExtent,
        as_of_cutoff: datetime | None = None,
    ) -> EpistemicSlice:
        """查询某实体在 ``target_time`` 切片上的认知视图。

        * ``as_of_cutoff`` 为时点：返回**当时**的真实认知（注记不可跨越认知时间生效）；
        * ``as_of_cutoff`` 为 ``None``：返回**当前**认知（历史原貌 + 外挂重估图层）。
        """
        window_start, window_end = _normalize_window(target_time)
        mode = KnowledgeMode.CURRENT if as_of_cutoff is None else KnowledgeMode.HISTORICAL
        if as_of_cutoff is not None:
            _require_aware(as_of_cutoff, "as_of_cutoff")

        with self._lock:
            visible, suppressed = self._index.slice(
                entity_id, window_start, window_end, as_of_cutoff
            )
            active = self._log.active_for(entity_id, window_start, window_end, as_of_cutoff)
            suppressed_annotations = self._log.suppressed_for(
                entity_id, window_start, window_end, as_of_cutoff
            )
            full_chain_hash = self._index.entity_chain_hash(entity_id)

        physical_hashes = {record.observation_id: record.content_hash for record in visible}
        lines = "\n".join(f"{oid}\t{digest}" for oid, digest in sorted(physical_hashes.items()))
        return EpistemicSlice(
            entity_id=entity_id,
            knowledge_mode=mode,
            as_of_cutoff=as_of_cutoff,
            target_time_start=window_start,
            target_time_end=window_end,
            physical_observations=visible,
            physical_count=len(visible),
            suppressed_by_cutoff=suppressed,
            stored_observation_total=len(self._index.observation_ids(entity_id)),
            active_annotations=active,
            suppressed_annotations=suppressed_annotations,
            overlay_applied=bool(active),
            physical_chain_hash=_sha256_hex(lines.encode("utf-8")),
            full_chain_hash=full_chain_hash,
            physical_hashes=physical_hashes,
        )

    def historical_view(
        self, entity_id: str, target_time: Any, as_of_cutoff: datetime
    ) -> EpistemicSlice:
        """显式历史视图（等价于传入 ``as_of_cutoff``）。"""
        return self.query_historical_slice(entity_id, target_time, as_of_cutoff)

    def current_view(self, entity_id: str, target_time: Any) -> EpistemicSlice:
        """显式当前视图（历史原貌 + 事后注记图层）。"""
        return self.query_historical_slice(entity_id, target_time, None)


class EpistemicWorldLens(BiTemporalEpistemicLens):
    """工单骨架名称兼容类（新代码请直接使用 :class:`BiTemporalEpistemicLens`）。"""


def _normalize_window(
    target_time: datetime | tuple[datetime, datetime] | TemporalExtent,
) -> tuple[datetime, datetime]:
    if isinstance(target_time, TemporalExtent):
        start, end = _extent_bounds(target_time)
        if start is None or end is None:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "TemporalExtent target_time must carry start/end (unknown time is not queryable)",
                context={"reason": "unknown_target_time"},
            )
        return (_require_aware(start, "target_time.start"), _require_aware(end, "target_time.end"))
    if isinstance(target_time, datetime):
        moment = _require_aware(target_time, "target_time")
        return (moment, moment)
    if isinstance(target_time, (tuple, list)) and len(target_time) == 2:
        start, end = target_time
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "target_time tuple must contain two datetimes",
                context={"reason": "invalid_target_window"},
            )
        first = _require_aware(start, "target_time.start")
        second = _require_aware(end, "target_time.end")
        if second < first:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "target_time window end must not be before start",
                context={"reason": "invalid_target_window"},
            )
        return (first, second)
    raise AIOSProtocolError(
        ErrorCode.INVALID_ARGUMENT,
        "target_time must be a datetime, a (start, end) tuple or a TemporalExtent",
        context={"reason": "invalid_target_time", "value_type": type(target_time).__name__},
    )


# ===========================================================================
# 四、单跳失效隔离（杜绝级联重算雪崩）
# ===========================================================================


class CognitiveNode(BaseModel):
    """认知节点（SUMMARY / BELIEF / CLAIM）：黄金 DDL ``cognitive_nodes`` 的契约化。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    node_type: str = Field(default="SUMMARY", min_length=1)
    content: str = ""
    is_stale: bool = False
    stale_reason: str | None = None
    stale_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    def with_stale(self, reason: str, at: datetime) -> CognitiveNode:
        """**返回新节点**（认知层同样不原地改写既有对象，保持可审计的追加语义）。"""
        return self.model_copy(
            update={"is_stale": True, "stale_reason": reason, "stale_at": at}
        )


class DependencyEdge(BaseModel):
    """``node_dependencies``：downstream 消费 upstream（方向：downstream -> upstream）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    downstream_node_id: str = Field(min_length=1)
    upstream_node_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)


class DeferredRecomputeBatch(BaseModel):
    """长尾下游的**有界**延迟重算批次（不递归、不雪崩，交给后台分批消化）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_node_id: str = Field(min_length=1)
    batch: tuple[CognitiveNode, ...] = ()
    concurrency_budget: int = Field(ge=0)
    remaining_after_batch: int = Field(ge=0)


class InvalidationReport(BaseModel):
    """反向失效审计报告：把"为什么没有雪崩"变成可核对的数字。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    changed_node_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    stale_at: datetime

    marked_stale_ids: tuple[str, ...] = ()
    marked_count: int = Field(ge=0)
    marked_depth: int = Field(ge=0)

    would_be_cascade_nodes: int = Field(ge=0)
    would_be_cascade_depth: int = Field(ge=0)
    cascade_audit_truncated: bool = False
    cascade_audit_budget: int = Field(ge=0)
    suppressed_cascade_nodes: int = Field(ge=0)

    traversal_depth: int = Field(ge=0)
    max_depth: int = Field(ge=0)
    nodes_scanned: int = Field(ge=0)
    audit_nodes_scanned: int = Field(default=0, ge=0)
    llm_calls_issued: int = Field(ge=0)
    llm_calls_if_cascaded: int = Field(ge=0)
    deferred_count: int = Field(ge=0)
    deferred_sample_ids: tuple[str, ...] = ()
    marking_ms: float = Field(default=0.0, ge=0.0)
    audit_ms: float = Field(default=0.0, ge=0.0)
    elapsed_ms: float = Field(ge=0.0)

    @property
    def cascade_avoided(self) -> int:
        return self.suppressed_cascade_nodes

    @property
    def is_single_hop(self) -> bool:
        return (
            self.traversal_depth == SINGLE_HOP_MAX_DEPTH
            and self.max_depth == SINGLE_HOP_MAX_DEPTH
        )


class SingleHopCascadeIsolator:
    """严格单跳（1-Hop）反向失效隔离（dossier 04 争议二终审裁定）。

    规则：
    1. 只标记**直接消费**被推翻认知的 1 级下游节点（``is_stale=True``）；
    2. **绝不递归**：遍历深度恒为 1，标记数恒等于一级下游数；
    3. 长尾下游进入**有界延迟队列**（并发重算 <= 3），由后台分批消化；
    4. 本层**零大模型调用**（``llm_calls_issued == 0``）——算力雪崩在结构上不可能发生。
    """

    def __init__(
        self,
        *,
        recompute_sink: Callable[[str], None] | None = None,
        max_recompute_concurrency: int = MAX_RECOMPUTE_CONCURRENCY,
    ) -> None:
        if not isinstance(max_recompute_concurrency, int) or max_recompute_concurrency < 1:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "max_recompute_concurrency must be a positive integer",
                context={"reason": "invalid_recompute_budget"},
            )
        self._nodes: dict[str, CognitiveNode] = {}
        self._downstream: dict[str, set[str]] = {}
        self._upstream: dict[str, set[str]] = {}
        self._recompute_sink = recompute_sink
        self._recompute_calls = 0
        self._concurrency = max_recompute_concurrency
        self._lock = threading.RLock()
        self._stale_marks: list[tuple[str, str, datetime]] = []

    # ---- 拓扑登记（认知层，与历史事实层完全分离）----

    def register_node(
        self, node_id: str, *, node_type: str = "SUMMARY", content: str = ""
    ) -> CognitiveNode:
        self._require_id(node_id, "node_id")
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                node = CognitiveNode(node_id=node_id, node_type=node_type, content=content)
                self._nodes[node_id] = node
                self._downstream.setdefault(node_id, set())
                self._upstream.setdefault(node_id, set())
            return node

    def register_dependency(self, downstream_node_id: str, upstream_node_id: str) -> DependencyEdge:
        """登记 ``downstream -> upstream``（下游消费上游结论）。"""
        self._require_id(downstream_node_id, "downstream_node_id")
        self._require_id(upstream_node_id, "upstream_node_id")
        if downstream_node_id == upstream_node_id:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "node cannot depend on itself",
                context={"reason": "self_dependency", "node_id": downstream_node_id},
            )
        with self._lock:
            self.register_node(downstream_node_id)
            self.register_node(upstream_node_id)
            self._downstream[upstream_node_id].add(downstream_node_id)
            self._upstream[downstream_node_id].add(upstream_node_id)
        return DependencyEdge(
            downstream_node_id=downstream_node_id, upstream_node_id=upstream_node_id
        )

    # ---- 只读访问 ----

    def node(self, node_id: str) -> CognitiveNode | None:
        return self._nodes.get(node_id)

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return sum(len(values) for values in self._downstream.values())

    def is_stale(self, node_id: str) -> bool:
        node = self._nodes.get(node_id)
        return bool(node and node.is_stale)

    def stale_node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(node_id for node_id, node in self._nodes.items() if node.is_stale))

    def direct_dependents(self, node_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._downstream.get(node_id, ())))

    def stale_mark_count(self) -> int:
        return len(self._stale_marks)

    # ---- 反向失效（核心）----

    def mark_stale_from(
        self,
        changed_node_id: str,
        reason: str,
        *,
        at: datetime | None = None,
        deferred_sample_limit: int = 64,
        cascade_audit_budget: int = DEFAULT_CASCADE_AUDIT_BUDGET,
    ) -> InvalidationReport:
        """严格单跳标记：只动 1 级下游，长尾只登记进延迟队列。

        成本纪律（可断言）：
        * **标记路径** 只扫描 ``1 + 直接下游数`` 个节点（``nodes_scanned``），与全图规模无关；
        * **审计路径** 只用于回答"若真级联会波及多少"，受 ``cascade_audit_budget`` 约束，
          超预算时按预算给出**下界**并置 ``cascade_audit_truncated=True``（绝不谎报精确值）。
        """
        started = time.perf_counter()
        self._require_id(changed_node_id, "changed_node_id")
        if not isinstance(reason, str) or not reason.strip():
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "reason must be a non-empty string",
                context={"reason": "empty_stale_reason"},
            )
        if not isinstance(cascade_audit_budget, int) or cascade_audit_budget < 0:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "cascade_audit_budget must be a non-negative integer",
                context={"reason": "invalid_audit_budget"},
            )
        stale_at = _require_aware(at, "stale_at") if at is not None else utc_now()

        with self._lock:
            if changed_node_id not in self._nodes:
                raise UnknownTargetEntityError(changed_node_id)
            direct = sorted(self._downstream.get(changed_node_id, ()))
            scanned = 1 + len(direct)
            for node_id in direct:
                current = self._nodes[node_id]
                if not current.is_stale:
                    self._nodes[node_id] = current.with_stale(reason, stale_at)
                    self._stale_marks.append((node_id, reason, stale_at))
            marking_ms = (time.perf_counter() - started) * 1000.0
            deferred_sample = self._bounded_downstream_sample(
                changed_node_id, deferred_sample_limit
            )

        audit_started = time.perf_counter()
        cascade_nodes, cascade_depth, audit_truncated, audit_scanned = self._audit_downstream(
            changed_node_id, cascade_audit_budget
        )
        audit_ms = (time.perf_counter() - audit_started) * 1000.0

        return InvalidationReport(
            changed_node_id=changed_node_id,
            reason=reason,
            stale_at=stale_at,
            marked_stale_ids=tuple(direct),
            marked_count=len(direct),
            marked_depth=1 if direct else 0,
            would_be_cascade_nodes=cascade_nodes,
            would_be_cascade_depth=cascade_depth,
            cascade_audit_truncated=audit_truncated,
            cascade_audit_budget=cascade_audit_budget,
            suppressed_cascade_nodes=max(cascade_nodes - len(direct), 0),
            traversal_depth=1,
            max_depth=SINGLE_HOP_MAX_DEPTH,
            nodes_scanned=scanned,
            audit_nodes_scanned=audit_scanned,
            llm_calls_issued=0,
            llm_calls_if_cascaded=cascade_nodes,
            deferred_count=max(cascade_nodes - len(direct), 0),
            deferred_sample_ids=deferred_sample,
            marking_ms=marking_ms,
            audit_ms=audit_ms,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    def prepare_deferred_batch(
        self, source_node_id: str, *, budget: int | None = None
    ) -> DeferredRecomputeBatch:
        """把长尾下游切成**有界**批次（并发预算 <= 3），交给后台懒重算。"""
        allowance = self._concurrency if budget is None else budget
        if not isinstance(allowance, int) or allowance < 1:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "batch budget must be a positive integer",
                context={"reason": "invalid_recompute_budget"},
            )
        with self._lock:
            if source_node_id not in self._nodes:
                raise UnknownTargetEntityError(source_node_id)
            eligible_total = self._count_pending_tail(source_node_id)
            tail = self._pending_downstream_sample(source_node_id, allowance)
            batch = tuple(self._nodes[node_id] for node_id in tail)
            remaining = max(eligible_total - len(batch), 0)
        return DeferredRecomputeBatch(
            source_node_id=source_node_id,
            batch=batch,
            concurrency_budget=allowance,
            remaining_after_batch=remaining,
        )

    # ---- 黄金 DDL 适配（唯一允许的 SQL 写目标：cognitive_nodes）----

    def apply_stale_marks_to_connection(
        self, connection: Any, report: InvalidationReport
    ) -> int:
        """把失效标记写进 ``cognitive_nodes``（黄金 DDL §3.5 的同语义落库）。

        只更新**认知层**状态位，绝不触碰 ``object_revisions`` / 历史事实。
        """
        if not report.marked_stale_ids:
            return 0
        placeholders = ",".join("?" for _ in report.marked_stale_ids)
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE cognitive_nodes "
            "SET is_stale = 1, stale_reason = ?, stale_at = ? "
            f"WHERE node_id IN ({placeholders})",
            (report.reason, report.stale_at.isoformat(), *report.marked_stale_ids),
        )
        connection.commit()
        return cursor.rowcount if cursor.rowcount is not None else len(report.marked_stale_ids)

    # ---- 内部 ----

    def _bounded_downstream_sample(self, node_id: str, limit: int) -> tuple[str, ...]:
        """按 BFS 顺序取前 ``limit`` 个下游 id（有界，绝不物化全量长尾）。"""
        if limit <= 0:
            return ()
        sample: list[str] = []
        seen: set[str] = set()
        queue: deque[str] = deque(sorted(self._downstream.get(node_id, ())))
        while queue and len(sample) < limit:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            sample.append(current)
            queue.extend(sorted(self._downstream.get(current, ())))
        return tuple(sample)

    def _pending_downstream_sample(self, node_id: str, limit: int) -> tuple[str, ...]:
        """有界采样"仍需后台消化"的下游节点（跳过已被直接标记的那一层）。

        与 :meth:`_bounded_downstream_sample` 的区别：已失效节点不再进批次，
        但**仍可穿过它们继续下行**去找真正的长尾（延迟队列只关心还没消化的部分）。
        """
        if limit <= 0:
            return ()
        sample: list[str] = []
        seen: set[str] = set()
        queue: deque[str] = deque(sorted(self._downstream.get(node_id, ())))
        while queue and len(sample) < limit:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            if not self._nodes[current].is_stale:
                sample.append(current)
            queue.extend(sorted(self._downstream.get(current, ())))
        return tuple(sample)

    def _count_pending_tail(self, node_id: str) -> int:
        """仍需后台消化的长尾节点数（= 全量下游 - 已被直接标记的一级下游）。

        审计口径受默认预算约束，超预算即为下界（由报告的 ``cascade_audit_truncated`` 说明）。
        """
        total, _, _, _ = self._audit_downstream(node_id, DEFAULT_CASCADE_AUDIT_BUDGET)
        return max(total - len(self._downstream.get(node_id, ())), 0)

    def _audit_downstream(self, node_id: str, budget: int) -> tuple[int, int, bool, int]:
        """审计：若真的级联会波及多少节点、多深（**只读统计**，绝不递归标记）。

        返回 ``(节点数, 最大深度, 是否因预算截断, 实际扫描节点数)``；
        截断时节点数为**下界**，由 ``cascade_audit_truncated`` 显式告知调用方。
        """
        seen: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque(
            (child, 1) for child in sorted(self._downstream.get(node_id, ()))
        )
        scanned = 0
        truncated = False
        while queue:
            if scanned >= budget:
                truncated = True
                break
            current, depth = queue.popleft()
            scanned += 1
            if current in seen and seen[current] <= depth:
                continue
            seen[current] = depth
            for child in sorted(self._downstream.get(current, ())):
                queue.append((child, depth + 1))
        if not seen:
            return (0, 0, truncated, scanned)
        return (len(seen), max(seen.values()), truncated, scanned)

    def dispatch_deferred_batch(
        self, batch: DeferredRecomputeBatch, sink: Callable[[str], None] | None = None
    ) -> int:
        """把长尾批次**交接**给后台消化，返回交接出去的节点数。

        纪律：标记路径绝不调用本方法（``llm_calls_issued == 0``、``recompute_dispatch_count == 0``），
        长尾必须由后台按并发预算慢消化——这正是"掐灭级联雪崩"的工程落点。
        """
        target = sink if sink is not None else self._recompute_sink
        dispatched = 0
        for node in batch.batch:
            dispatched += 1
            self._recompute_calls += 1
            if target is not None:
                target(node.node_id)
        return dispatched

    @property
    def recompute_dispatch_count(self) -> int:
        """已交接给后台的重算节点数（标记路径本身恒为 0）。"""
        return self._recompute_calls

    @staticmethod
    def _require_id(value: Any, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                f"{field_name} must be a non-empty string",
                context={"reason": "invalid_identifier", "field": field_name},
            )


def invalidate_overturned_fact_single_hop(
    db_connection: Any, overturned_node_id: str, reason: str
) -> list[str]:
    """黄金 DDL §3.5 的严格单跳失效隔离（drop-in 兼容实现）。

    语义与 :meth:`SingleHopCascadeIsolator.mark_stale_from` 完全一致：
    只把**直接下游**标记 ``is_stale=1``，绝不递归；返回被标记的节点 id（升序）。
    """
    cursor = db_connection.cursor()
    now_iso = utc_now().isoformat()
    cursor.execute(
        "SELECT downstream_node_id FROM node_dependencies WHERE upstream_node_id = ?",
        (overturned_node_id,),
    )
    direct_downstream_ids = sorted({row[0] for row in cursor.fetchall()})
    if not direct_downstream_ids:
        return []
    placeholders = ",".join("?" for _ in direct_downstream_ids)
    cursor.execute(
        "UPDATE cognitive_nodes "
        "SET is_stale = 1, stale_reason = ?, stale_at = ? "
        f"WHERE node_id IN ({placeholders})",
        (reason, now_iso, *direct_downstream_ids),
    )
    db_connection.commit()
    return direct_downstream_ids


# ===========================================================================
# 五、今天写一条注记（编排：追加 + 自证历史未被改写）
# ===========================================================================


class AnnotationReceipt(BaseModel):
    """"今天打标签"的收据：把"历史没被动过"变成可核对的证据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation: RetrospectiveAnnotation
    appended_object_id: str = Field(min_length=1)
    world_revision_before: int = Field(ge=0)
    world_revision_after: int = Field(ge=0)
    appended_object_count: int = Field(ge=0)
    annotations_written_today: int = Field(ge=0)
    history_root_hash_before: str = Field(min_length=1)
    history_root_hash_after: str = Field(min_length=1)
    history_unchanged: bool
    history_matched: int = Field(ge=0)
    observations_total_before: int = Field(ge=0)
    observations_total_after: int = Field(ge=0)
    mutating_sql_attempts: int = Field(default=0, ge=0)
    written_at: datetime
    elapsed_ms: float = Field(ge=0.0)


class RetrospectiveAnnotationWriter:
    """把复盘注记**追加**进世界的唯一写路径（单写者纪律）。

    * 写入前：捕获历史台账（SHA-256）并核对；
    * 写入：``store.commit([...])`` 一次，只追加、不修改；
    * 写入后：重读历史并逐条核对哈希，不一致立即抛错并给出差异清单。
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    def write(
        self,
        annotation: RetrospectiveAnnotation,
        *,
        history_ledger: ObservationHashLedger,
        subject_id: str,
        created_by: str,
        expected_world_revision: int | None = None,
        reason: str | None = None,
        history_payloads: Iterable[Mapping[str, Any]] | None = None,
    ) -> AnnotationReceipt:
        from aios_core.contracts import OperationRequest  # 局部导入：避免包级循环依赖

        started = time.perf_counter()
        revision_before = self._store.current_world_revision()
        if expected_world_revision is not None and expected_world_revision != revision_before:
            raise AIOSProtocolError(
                ErrorCode.VERSION_CONFLICT,
                "world revision advanced before annotation was appended",
                context={
                    "reason": "stale_expected_revision",
                    "expected": expected_world_revision,
                    "actual": revision_before,
                },
            )

        before_payloads = (
            list(history_payloads)
            if history_payloads is not None
            else self._store.list_payloads(object_type=ObjectType.OBSERVATION)
        )
        ledger_diff_before = history_ledger.verify(before_payloads)
        if not ledger_diff_before.unchanged:
            raise HistoryMutationDetectedError(
                ledger_diff_before,
                {"phase": "pre_append", "annotation_id": annotation.annotation_id},
            )

        claim = annotation.to_claim(subject_id=subject_id, created_by=created_by)
        self._store.commit(
            [claim],
            OperationRequest(
                operation_name="world.commit",
                expected_world_revision=revision_before,
                reason=reason or f"M1-018 复盘注记追加: {annotation.annotation_id}",
                idempotency_key=f"m1-018-annotation-{annotation.annotation_id}",
            ),
        )
        revision_after = self._store.current_world_revision()

        after_payloads = self._store.list_payloads(object_type=ObjectType.OBSERVATION)
        ledger_diff_after = history_ledger.verify(after_payloads)
        if not ledger_diff_after.unchanged:
            raise HistoryMutationDetectedError(
                ledger_diff_after,
                {"phase": "post_append", "annotation_id": annotation.annotation_id},
            )

        annotations_today = sum(
            1
            for item in annotations_from_store(self._store)
            if as_utc(item.knowledge_time, "learned_at").date()
            == as_utc(annotation.knowledge_time, "learned_at").date()
        )
        return AnnotationReceipt(
            annotation=annotation,
            appended_object_id=claim.object_id,
            world_revision_before=revision_before,
            world_revision_after=revision_after,
            appended_object_count=1,
            annotations_written_today=annotations_today,
            history_root_hash_before=ledger_diff_before.root_hash_before,
            history_root_hash_after=ledger_diff_after.root_hash_after,
            history_unchanged=ledger_diff_after.unchanged,
            history_matched=ledger_diff_after.matched,
            observations_total_before=len(before_payloads),
            observations_total_after=len(after_payloads),
            written_at=utc_now(),
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )


# ===========================================================================
# 六、与 C06 超链接穿透层的桥接（谁的事实到底属于哪个实体）
# ===========================================================================


def observations_linked_to_entity(hyperlink_result: Any) -> dict[str, tuple[str, ...]]:
    """从 C06 超链接穿透结果提取 ``实体 -> 观察 id`` 链接表（鸭子类型，不引入硬依赖）。

    用途：注记透镜需要知道"哪些客观事实属于这个实体"，而实体归属的真实来源是
    ``Entity -> EventAnchor -> EvidenceSet -> Observation`` 结构化引用链
    （C06 超链接穿透器），**不是**文本模糊匹配。
    """
    entity_id = getattr(hyperlink_result, "root_entity_id", None)
    observations = getattr(hyperlink_result, "observations", None)
    if not isinstance(entity_id, str) or not entity_id:
        raise AIOSProtocolError(
            ErrorCode.INVALID_ARGUMENT,
            "hyperlink result must expose root_entity_id",
            context={"reason": "invalid_hyperlink_result"},
        )
    ids: list[str] = []
    for item in observations or ():
        observation_id = (
            item.get("observation_id")
            if isinstance(item, Mapping)
            else getattr(item, "observation_id", None)
        )
        if isinstance(observation_id, str) and observation_id:
            ids.append(observation_id)
    return {entity_id: tuple(dict.fromkeys(ids))}
