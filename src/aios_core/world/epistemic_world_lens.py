"""M1-018 认知反向传播语义图层契约与回溯标注引擎（王建国案 / 宪法第九十三条）.

老大最高指示（唯一准则）：
    “只标记当前时间节点的事件，老王是骗子这个标签，没必要回去把所有对话都改成老王是骗子！”
    “推翻历史认知时，新认知只追加在今天，严禁倒写历史！”

高阶实战情境（升级版工单）：用户两年前与核心技术合伙人“王建国”签署联合孵化协议，
过去 730 天累积 18,000 条客观 Observation 事实链；第 730 天（``T_now``）司法部门下达
查封执行文书。本模块要保证：**那 18,000 条历史事实一个字节都不许动**，今天只追加一条
外挂解释图层，并且下游重算严格锁死在单跳。

三条工程铁律被固化为代码级不可绕过的约束：

1. **历史字节级不可篡改**：过去发生的原始客观事实（战略合同、股东会纪要、汇款凭证、
   晚间心率）在本引擎内只有只读锚点（:class:`FactAnchor`），不存在任何 UPDATE / DELETE
   通道；每次挂载图层与每次历史切片查询都会重新计算并比对底层事实的 SHA-256（与
   ``SQLiteWorldStore.object_revisions.payload_json`` 的行字节完全同源），一旦发现
   改写立即 fail-closed 抛出 :class:`HistoryImmutabilityViolation`。
2. **新认知只写在今天（T_now）**：:class:`RetrospectiveAnnotation` 的
   ``learned_at == recorded_at == T_now``，只通过 ``valid_time_start / valid_time_end``
   这对指针外挂（Overlay）到过去的时间切片；模型层直接拒绝 ``learned_at`` 早于目标
   切片结束的“倒写历史”标注。
3. **严格单跳、拒绝级联雪崩**：解释图层只能挂载在原始事实之上
   （``MAX_OVERLAY_HOPS == 1``），禁止图层叠图层、禁止无界的 supersede 递归链；
   :class:`SingleHopCascadeIsolator` 只把直接消费该实体认知的 1 级下游打上
   ``is_stale``，邻接查询次数被契约锁死为 1，大模型重算触发次数恒为 0，彻底掐灭
   210 次（10 个一级 + 200 个二级）API 算力雪崩。

双时间透镜（valid time × 认知时间）：

* :class:`EpistemicWorldLens` —— 引擎本体，``query_historical_slice(entity_id,
  target_time, as_of_cutoff=None) -> Dict[str, Any]``（一号工单签名原文形态）；
* :class:`BiTemporalEpistemicLens` —— 升级版工单契约外壳，``query_entity_state(...)
  -> HistoricalEpistemicSlice``；
* ``as_of_cutoff = T0 + 100d`` → 精准再现用户第 100 天面对的世界认知原貌（绝不产生
  “事后诸葛亮”的历史虚无主义）；
* ``as_of_cutoff = None`` → 在完整保留历史事实的基础上叠加“事后证实为特大诈骗”的
  解释注记，历史曲线原貌与其哈希保持不变。

**并存说明（多模型并行开发收敛）**：战队已合入基线 ``world/retrospective_annotation.py``
（``ImmutableFactLedger`` / ``AnnotationRegistry`` / ``BiTemporalEpistemicLens`` /
``SingleHopCascadeIsolator``，ValueError 错误家族 + 强类型 dataclass 视图）保持一字不动；
本文件是同一工单的另一条实现线，落盘于独立路径以便首席择优或熔铸：

* 错误分类走 ``aios_core.errors.AIOSProtocolError`` + ``ErrorCode``（与 C02 存储底座同族）；
* 时间戳按 ``contracts.time.require_aware`` 对 naive 值 fail-closed（与 WorldObject 全仓纪律一致）；
* 历史事实直接以 ``WorldObject`` / 持久化 payload 形态登记，指纹与 SQLite 行字节同源，
  因此“原始数据哈希永久不变”可以在存储层逐字节复核；
* 注记挂载内建于透镜（幂等重放 + 冲突判定 + 实体分桶时间索引），并额外支持认知再修正
  （``supersedes_annotation_id``，旧图层永不删除）；
* :func:`coerce_annotation` / :meth:`RetrospectiveAnnotation.to_sibling_annotation`
  提供与基线契约的双向投影，供熔铸合体时零成本对接。
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from importlib import import_module
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ClaimType, ErrorCode, KnowledgeState, ObjectType
from aios_core.contracts.models import Claim, Dependency
from aios_core.contracts.refs import SourceRef
from aios_core.contracts.registry import canonical_model_for_object_type
from aios_core.contracts.time import (
    TemporalExtent,
    TimePrecision,
    as_utc,
    canonical_utc_iso,
    require_aware,
    utc_now,
)
from aios_core.errors import AIOSProtocolError
from aios_core.storage.idempotency import (
    DurableJSONError,
    canonical_json_dumps,
    canonical_world_object_payload,
)

if TYPE_CHECKING:  # pragma: no cover - 仅用于类型标注，避免 world -> query 运行时耦合
    from aios_core.query.history import HistoricalWorldQuery


__all__ = [
    "DIGEST_ALGORITHM",
    "MAX_DIAGNOSTIC_DEPTH",
    "MAX_OVERLAY_HOPS",
    "MAX_SUPERSEDE_CHAIN_DEPTH",
    "AnnotationTargetNotFound",
    "AttachmentReceipt",
    "BiTemporalEpistemicLens",
    "EpistemicSliceView",
    "EpistemicWorldLens",
    "FactAnchor",
    "FactTamperFinding",
    "HistoricalEpistemicSlice",
    "HistoryImmutabilityViolation",
    "IntegrityReport",
    "OverlayCascadeForbidden",
    "RecomputeAudit",
    "RetrospectiveAnnotation",
    "RetrospectiveAnnotationError",
    "SingleHopCascadeIsolator",
    "SingleHopInvalidationReport",
    "SliceCoverage",
    "SliceFactView",
    "SliceOverlayView",
    "annotation_sha256",
    "coerce_annotation",
    "coerce_world_object",
    "encode_fact_payload",
    "fact_sha256",
    "new_annotation_id",
    "normalize_dependency_graph",
]


#: 底层事实指纹算法；与 storage 层持久化 JSON 编码器同源，可逐字节复核。
DIGEST_ALGORITHM: Final[str] = "sha256"

#: 解释图层严格单跳：图层只能挂在原始事实上，禁止图层叠图层。
MAX_OVERLAY_HOPS: Final[int] = 1

#: 认知向前演化允许的 supersede 链上限，超出即视为无界级联并拒绝。
MAX_SUPERSEDE_CHAIN_DEPTH: Final[int] = 64

_ANNOTATION_ID_PREFIX: Final[str] = "ran"

#: 规范名（升级版工单）→ 战队已合入基线命名，仅用于 to_sibling_annotation 投影。
_SUPERSET_TO_SIBLING_FIELDS: Final[dict[str, str]] = {
    "valid_time_start": "target_time_start",
    "valid_time_end": "target_time_end",
    "source_evidence_ref": "source_statement_ref",
}

#: 姊妹契约的默认落点（战队已合入基线），惰性导入以免形成包内硬耦合。
_SIBLING_MODULE: Final[str] = "aios_core.world.retrospective_annotation"
_SIBLING_MODEL: Final[str] = "RetrospectiveAnnotation"

ViewMode = Literal["as_of_cutoff", "current_cognition"]
SliceMode = Literal["instant", "cumulative"]
OverlayStatus = Literal["active", "superseded"]
TamperReason = Literal["digest_mismatch", "payload_unreadable"]


# ---------------------------------------------------------------------------
# 协议级失败（统一收敛为一个异常家族，便于协议边界分支处理）
# ---------------------------------------------------------------------------


class RetrospectiveAnnotationError(AIOSProtocolError):
    """M1-018 语义图层引擎的协议级失败基类。"""


class HistoryImmutabilityViolation(RetrospectiveAnnotationError):
    """宪法第九十三条红线：历史原始事实被改写（或引擎被要求改写历史）。"""


class OverlayCascadeForbidden(RetrospectiveAnnotationError):
    """违反严格单跳：图层叠图层、supersede 自指/成环/无界链。"""


class AnnotationTargetNotFound(RetrospectiveAnnotationError):
    """回溯标注的指针没有命中任何已登记的历史时间切片。"""


# ---------------------------------------------------------------------------
# 底层事实指纹（只读）
# ---------------------------------------------------------------------------


def new_annotation_id() -> str:
    """生成不透明、与人名/标签无关的回溯标注编号。"""

    return f"{_ANNOTATION_ID_PREFIX}_{uuid.uuid4().hex}"


def coerce_world_object(fact: WorldObject | Mapping[str, Any]) -> WorldObject:
    """把“活的 WorldObject”或“持久化 payload 映射”统一收敛为规范世界对象。

    持久化 payload 会经过 ``canonical_model_for_object_type`` 的严格再校验，
    伪造/残缺的历史载荷在此处 fail-closed，而不是带病进入透镜。
    """

    if isinstance(fact, WorldObject):
        return fact

    if isinstance(fact, Mapping):
        raw_type = fact.get("object_type")
        if not isinstance(raw_type, str) or not raw_type:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "durable fact payload is missing object_type",
                context={"reason": "missing_object_type"},
            )
        try:
            object_type = ObjectType(raw_type)
        except ValueError as exc:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                f"durable fact payload has an unknown object_type: {raw_type}",
                context={"reason": "unknown_object_type", "object_type": raw_type},
            ) from exc

        model = canonical_model_for_object_type(object_type)
        try:
            return model.model_validate(dict(fact))
        except (ValidationError, TypeError, ValueError) as exc:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "durable fact payload failed canonical world-object validation",
                context={
                    "reason": "payload_revalidation_failed",
                    "object_type": object_type.value,
                },
            ) from exc

    raise TypeError(
        "fact must be a WorldObject or a durable payload mapping, "
        f"got {type(fact).__name__}"
    )


def encode_fact_payload(
    fact: WorldObject | Mapping[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """返回 ``(canonical payload, canonical encoded JSON, sha256)``。

    编码路径与 ``SQLiteWorldStore.commit`` 写入 ``payload_json`` 的字节完全一致，
    因此这里的 SHA-256 就是“原始数据哈希值永久不变”的可复核证据。
    """

    obj = coerce_world_object(fact)
    try:
        payload = canonical_world_object_payload(obj)
        encoded = canonical_json_dumps(payload)
    except (DurableJSONError, ValidationError, TypeError) as exc:
        raise RetrospectiveAnnotationError(
            ErrorCode.INVALID_ARGUMENT,
            "fact cannot be encoded as durable JSON",
            context={
                "reason": "durable_json_validation_failed",
                "object_id": str(obj.object_id),
            },
        ) from exc
    return payload, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fact_sha256(fact: WorldObject | Mapping[str, Any]) -> str:
    """底层原始事实对象的 SHA-256 指纹（挂载图层前后必须 100% 相同）。"""

    return encode_fact_payload(fact)[2]


def _coerce_utc(value: object, field_name: str) -> datetime:
    """把 ``datetime`` / ISO-8601 字符串统一成 timezone-aware UTC。"""

    candidate = value
    if isinstance(candidate, str):
        text = candidate.strip()
        try:
            candidate = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                f"{field_name} is not a valid ISO-8601 timestamp",
                context={"reason": "query_timestamp_invalid", "field": field_name},
            ) from exc
    if not isinstance(candidate, datetime):
        raise RetrospectiveAnnotationError(
            ErrorCode.INVALID_ARGUMENT,
            f"{field_name} must be a datetime",
            context={"reason": "query_timestamp_invalid", "field": field_name},
        )
    try:
        require_aware(candidate, field_name)
        return as_utc(candidate, field_name)
    except (ValueError, OverflowError, OSError) as exc:
        raise RetrospectiveAnnotationError(
            ErrorCode.INVALID_ARGUMENT,
            f"{field_name} is not a supported timestamp",
            context={"reason": "query_timestamp_invalid", "field": field_name},
        ) from exc


# ---------------------------------------------------------------------------
# 数据契约：RetrospectiveAnnotation（今天的新认知 → 过去切片的外挂图层）
# ---------------------------------------------------------------------------


class RetrospectiveAnnotation(BaseModel):
    """今天在 ``T_now`` 产生的新认知，以只读指针外挂到过去的时间切片。

    本对象描述的是“**今天**学到了什么”，而不是“历史应该被改成什么”：

    * ``learned_at`` / ``recorded_at`` 恒为 ``T_now``（默认取当前时刻，且
      ``recorded_at`` 默认与 ``learned_at`` 同值，对齐工单原文
      ``learned_at = recorded_at = T_now``，回填不依赖真实时钟）；
    * ``valid_time_start`` / ``valid_time_end`` 是指向过去时空切片
      （``valid_time_range = [T0, T_now]``）的只读指针；
    * ``source_evidence_ref`` 指向今天这条新认知的证据来源（如法院执行文书、司法审计
      报告，或记录用户指认的那条 T_now Claim/Observation 的 ``object_id``）；
    * ``supersedes_annotation_id`` 让认知继续向前演化（例如日后澄清误会）时，
      以“追加新图层”的方式取代旧图层，**旧图层永不删除**。

    字段命名同时兼容两版工单：升级版工单的 ``valid_time_start / valid_time_end /
    source_evidence_ref`` 是规范名，一号工单与战队已合入基线使用的
    ``target_time_start / target_time_end / source_statement_ref`` 作为校验别名
    （``AliasChoices``）同样接受，并以只读属性暴露，方便双线熔铸。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(
        min_length=1,
        description="不透明的回溯标注编号，与人名/标签无关",
    )
    target_entity_id: str = Field(
        min_length=1,
        description="图层指向的实体（如 ent_wangjianguo），只读指针，不修改实体本身",
    )
    semantic_overlay: str = Field(
        min_length=1,
        description="挂载的法律/信用/关系重估事实标签，如 '司法冻结查封确认欺诈'",
    )
    valid_time_start: datetime = Field(
        validation_alias=AliasChoices("valid_time_start", "target_time_start"),
        description="指向历史事件实际生效区间的起点（valid_time_range.start）",
    )
    valid_time_end: datetime = Field(
        validation_alias=AliasChoices("valid_time_end", "target_time_end"),
        description="指向历史事件实际生效区间的终点（valid_time_range.end）",
    )
    learned_at: datetime = Field(
        default_factory=utc_now,
        description="学到该新认知的时刻，恒为 T_now（今天）",
    )
    recorded_at: datetime = Field(
        default_factory=utc_now,
        description="落账时刻，默认与 learned_at 同值（learned_at == recorded_at == T_now）",
    )
    source_evidence_ref: str = Field(
        min_length=1,
        validation_alias=AliasChoices("source_evidence_ref", "source_statement_ref"),
        description="新认知来源指针（法院执行文书 / 司法审计报告 / T_now 陈述对象 object_id）",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="对“今天确实产生了这条新认知”的置信度",
    )
    supersedes_annotation_id: str | None = Field(
        default=None,
        min_length=1,
        description="被本图层取代的旧图层编号；旧图层仍永久留存在认知账本中",
    )

    @model_validator(mode="before")
    @classmethod
    def _default_recorded_at_to_learned_at(cls, data: Any) -> Any:
        """未显式给出 ``recorded_at`` 时，锁定 ``recorded_at == learned_at == T_now``。"""

        if not isinstance(data, Mapping):
            return data
        values = dict(data)
        if values.get("recorded_at") is None:
            learned_at = values.get("learned_at")
            values["recorded_at"] = utc_now() if learned_at is None else learned_at
        return values

    @model_validator(mode="after")
    def validate_bi_temporal_contract(self) -> "RetrospectiveAnnotation":
        for field_name in (
            "annotation_id",
            "target_entity_id",
            "semantic_overlay",
            "source_evidence_ref",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")

        for field_name in (
            "valid_time_start",
            "valid_time_end",
            "learned_at",
            "recorded_at",
        ):
            require_aware(getattr(self, field_name), field_name)

        start = as_utc(self.valid_time_start, "valid_time_start")
        end = as_utc(self.valid_time_end, "valid_time_end")
        learned_at = as_utc(self.learned_at, "learned_at")
        recorded_at = as_utc(self.recorded_at, "recorded_at")

        if end < start:
            raise ValueError("valid_time_end must not be before valid_time_start")

        # 铁律：新认知只能写在事实之后（今天），严禁倒写历史。
        if learned_at < end:
            raise ValueError(
                "learned_at must not be before valid_time_end: "
                "retrospective cognition is only allowed to grow forward in time"
            )

        if recorded_at < learned_at:
            raise ValueError("recorded_at must be >= learned_at")

        if (
            self.supersedes_annotation_id is not None
            and not self.supersedes_annotation_id.strip()
        ):
            raise ValueError("supersedes_annotation_id must not be blank")

        if self.supersedes_annotation_id == self.annotation_id:
            raise ValueError("annotation cannot supersede itself")

        return self

    # -- 一号工单 / 战队基线命名兼容（只读投影，规范名见字段定义） -------------

    @property
    def valid_time_range(self) -> TemporalExtent:
        """指向过去时间切片的只读指针（``valid_time_range = [T0, T_now]``）。"""

        return TemporalExtent(
            start=self.valid_time_start,
            end=self.valid_time_end,
            precision=TimePrecision.SECOND,
        )

    @property
    def target_time_range(self) -> TemporalExtent:
        """:attr:`valid_time_range` 的一号工单命名别名。"""

        return self.valid_time_range

    @property
    def target_time_start(self) -> datetime:
        """:attr:`valid_time_start` 的一号工单命名别名。"""

        return self.valid_time_start

    @property
    def target_time_end(self) -> datetime:
        """:attr:`valid_time_end` 的一号工单命名别名。"""

        return self.valid_time_end

    @property
    def source_statement_ref(self) -> str:
        """:attr:`source_evidence_ref` 的一号工单命名别名。"""

        return self.source_evidence_ref

    def covers(self, target_time: datetime) -> bool:
        """本图层指针窗口是否覆盖某个历史时刻。"""

        instant = _coerce_utc(target_time, "target_time")
        return (
            as_utc(self.valid_time_start, "valid_time_start")
            <= instant
            <= as_utc(self.valid_time_end, "valid_time_end")
        )

    def intersects(self, start: datetime, end: datetime) -> bool:
        """本图层指针窗口是否与 ``[start, end]`` 相交（闭区间）。"""

        left = _coerce_utc(start, "start")
        right = _coerce_utc(end, "end")
        return (
            as_utc(self.valid_time_start, "valid_time_start") <= right
            and as_utc(self.valid_time_end, "valid_time_end") >= left
        )

    def started_by(self, target_time: datetime) -> bool:
        """累积切片语义：图层窗口在该历史时刻之前（含）已经开始生效。"""

        instant = _coerce_utc(target_time, "target_time")
        return as_utc(self.valid_time_start, "valid_time_start") <= instant

    def to_durable_claim(
        self,
        *,
        subject_id: str,
        claimant_id: str | None = None,
        object_id: str | None = None,
        claim_type: ClaimType = ClaimType.INFERENCE,
        knowledge_state: KnowledgeState = KnowledgeState.INFERRED,
        created_by: str = "m1-018-retrospective-annotation",
    ) -> Claim:
        """把今天的新认知投影成一条可落盘的 ``T_now`` :class:`Claim`。

        投影遵守双时间语义：``occurred / asserted_at / learned_at`` 全部是今天，
        ``valid_time`` 才是两年前的目标切片。因此它经过既有的 append-only
        ``SQLiteWorldStore`` 落盘后，天然对 ``knowledge_cutoff = 两年前`` 不可见，
        不需要（也绝不允许）改写任何历史行。
        """

        return Claim(
            object_id=object_id or f"clm_{uuid.uuid4().hex}",
            subject_id=subject_id,
            revision=1,
            occurred=TemporalExtent.point(self.learned_at),
            learned_at=self.learned_at,
            recorded_at=self.recorded_at,
            created_by=created_by,
            claimant_id=claimant_id or subject_id,
            claim_type=claim_type,
            content=f"[回溯标注 {self.annotation_id}] {self.semantic_overlay}",
            valid_time=self.valid_time_range,
            asserted_at=self.learned_at,
            knowledge_state=knowledge_state,
            confidence=self.confidence,
            source_refs=[SourceRef(object_id=self.source_evidence_ref)],
            metadata={
                "retrospective_annotation_id": self.annotation_id,
                "semantic_overlay": self.semantic_overlay,
                "target_entity_id": self.target_entity_id,
                "valid_time_start": canonical_utc_iso(
                    self.valid_time_start, "valid_time_start"
                ),
                "valid_time_end": canonical_utc_iso(self.valid_time_end, "valid_time_end"),
                "source_evidence_ref": self.source_evidence_ref,
                "supersedes_annotation_id": self.supersedes_annotation_id,
            },
        )

    def to_sibling_annotation(self, sibling_model: type[BaseModel] | None = None) -> Any:
        """投影到战队已合入基线的姊妹契约（``world.retrospective_annotation``）。

        只投影对方声明过的字段并按对方命名改写（``valid_time_*`` → ``target_time_*``、
        ``source_evidence_ref`` → ``source_statement_ref``），本线独有的
        ``confidence`` / ``supersedes_annotation_id`` 自动略去，供首席熔铸合体时直接对接。
        """

        model = (
            sibling_model if sibling_model is not None else default_sibling_model()
        )
        data = self.model_dump()
        renamed = {_SUPERSET_TO_SIBLING_FIELDS.get(key, key): value for key, value in data.items()}
        projected = {
            key: value for key, value in renamed.items() if key in model.model_fields
        }
        return model.model_validate(projected)


# ---------------------------------------------------------------------------
# 只读事实锚点与审计视图
# ---------------------------------------------------------------------------


def annotation_sha256(annotation: RetrospectiveAnnotation) -> str:
    """一条回溯标注自身的 SHA-256 指纹，用于幂等重放与冲突判定。"""

    if not isinstance(annotation, RetrospectiveAnnotation):
        raise TypeError(
            "annotation must be a RetrospectiveAnnotation, "
            f"got {type(annotation).__name__}"
        )
    return hashlib.sha256(
        canonical_json_dumps(annotation).encode("utf-8")
    ).hexdigest()


def default_sibling_model() -> type[BaseModel]:
    """返回战队已合入基线的姊妹注记契约（惰性导入，缺失时 fail-closed）。"""

    try:
        module = import_module(_SIBLING_MODULE)
        model = getattr(module, _SIBLING_MODEL)
    except (ImportError, AttributeError) as exc:
        raise RetrospectiveAnnotationError(
            ErrorCode.NOT_FOUND,
            "sibling retrospective annotation contract is not available",
            context={"reason": "sibling_contract_missing", "module": _SIBLING_MODULE},
        ) from exc
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise RetrospectiveAnnotationError(
            ErrorCode.INVALID_ARGUMENT,
            "sibling retrospective annotation contract is not a pydantic model",
            context={"reason": "sibling_contract_invalid", "module": _SIBLING_MODULE},
        )
    return model


def coerce_annotation(value: Any) -> RetrospectiveAnnotation:
    """把本线契约、姊妹契约或原始映射统一收敛为 :class:`RetrospectiveAnnotation`。

    两版工单的字段命名都被 ``AliasChoices`` 接受，因此战队基线的注记对象可以
    直接投喂给本线引擎（``model_dump`` → ``model_validate``），无需人工改写。
    """

    if isinstance(value, RetrospectiveAnnotation):
        return value

    if isinstance(value, BaseModel):
        data: Any = value.model_dump()
    elif isinstance(value, Mapping):
        data = dict(value)
    else:
        raise RetrospectiveAnnotationError(
            ErrorCode.INVALID_ARGUMENT,
            "annotation must be a RetrospectiveAnnotation, a sibling annotation "
            "model or a mapping of its fields",
            context={
                "reason": "annotation_type_invalid",
                "got": type(value).__name__,
            },
        )

    try:
        return RetrospectiveAnnotation.model_validate(data)
    except (ValidationError, TypeError, ValueError) as exc:
        raise RetrospectiveAnnotationError(
            ErrorCode.INVALID_ARGUMENT,
            "annotation payload failed the retrospective annotation contract",
            context={"reason": "annotation_coercion_failed"},
        ) from exc


class FactAnchor(BaseModel):
    """一条历史客观事实在透镜中的只读锚点（登记瞬间的字节快照 + SHA-256）。

    锚点只承载“读”的语义：它保存登记时刻的规范 payload 与指纹，供日后逐字节复核；
    它不回写、不接管任何存储写权限。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    object_type: ObjectType
    occurred_start: datetime | None = None
    occurred_end: datetime | None = None
    time_unknown: bool = False
    learned_at: datetime
    recorded_at: datetime
    payload: dict[str, Any]
    payload_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_anchor_times(self) -> "FactAnchor":
        require_aware(self.occurred_start, "occurred_start")
        require_aware(self.occurred_end, "occurred_end")
        require_aware(self.learned_at, "learned_at")
        require_aware(self.recorded_at, "recorded_at")

        if self.time_unknown and (
            self.occurred_start is not None or self.occurred_end is not None
        ):
            raise ValueError("time_unknown anchor cannot carry occurred_start/end")

        if (
            not self.time_unknown
            and self.occurred_start is not None
            and self.occurred_end is not None
            and self.occurred_end < self.occurred_start
        ):
            raise ValueError("occurred_end must not be before occurred_start")

        return self

    @property
    def sha256(self) -> str:
        return self.payload_sha256

    def covers(self, target_time: datetime) -> bool:
        """事实的发生区间是否覆盖某个历史时刻（开区间边界视为无界）。"""

        if self.time_unknown:
            return False
        instant = _coerce_utc(target_time, "target_time")
        if self.occurred_start is not None and instant < self.occurred_start:
            return False
        if self.occurred_end is not None and instant > self.occurred_end:
            return False
        return True

    def intersects(self, start: datetime, end: datetime) -> bool:
        """事实的发生区间是否与 ``[start, end]`` 相交。"""

        if self.time_unknown:
            return False
        left = _coerce_utc(start, "start")
        right = _coerce_utc(end, "end")
        if self.occurred_end is not None and self.occurred_end < left:
            return False
        if self.occurred_start is not None and self.occurred_start > right:
            return False
        return True

    def started_by(self, target_time: datetime) -> bool:
        """累积切片语义：事实在该历史时刻之前（含）已经开始发生。"""

        if self.time_unknown:
            return False
        instant = _coerce_utc(target_time, "target_time")
        return self.occurred_start is None or instant >= self.occurred_start

    def payload_copy(self) -> dict[str, Any]:
        """返回历史 payload 的深拷贝，杜绝调用方通过返回值反向改写历史。"""

        return copy.deepcopy(self.payload)


class FactTamperFinding(BaseModel):
    """一次历史篡改取证结论。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    expected_sha256: str = Field(min_length=64, max_length=64)
    observed_sha256: str | None = None
    reason: TamperReason


class IntegrityReport(BaseModel):
    """底层原始事实 SHA-256 复核报告。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm: Literal["sha256"] = DIGEST_ALGORITHM
    checked_facts: int = Field(default=0, ge=0)
    verified: bool = True
    tampered: tuple[FactTamperFinding, ...] = ()

    @model_validator(mode="after")
    def validate_report_consistency(self) -> "IntegrityReport":
        if self.verified and self.tampered:
            raise ValueError("verified report cannot carry tamper findings")
        if not self.verified and not self.tampered:
            raise ValueError("unverified report requires tamper findings")
        return self


class RecomputeAudit(BaseModel):
    """级联重算审计：本引擎对历史做过什么（答案永远是“什么都没做”）。

    ``history_rewrites`` / ``derived_recomputations`` / ``max_recursion_depth``
    被契约锁死为 0，任何非零值都会在构造阶段直接被 pydantic 拒绝。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_overlay_hops: int = Field(default=MAX_OVERLAY_HOPS, ge=1, le=MAX_OVERLAY_HOPS)
    overlay_hops_used: int = Field(default=1, ge=1, le=MAX_OVERLAY_HOPS)
    max_recursion_depth: int = Field(default=0, ge=0, le=0)
    history_rewrites: int = Field(default=0, ge=0, le=0)
    derived_recomputations: int = Field(default=0, ge=0, le=0)
    history_rewrite_attempts_blocked: int = Field(default=0, ge=0)
    cascade_attempts_blocked: int = Field(default=0, ge=0)
    facts_registered: int = Field(default=0, ge=0)
    annotations_attached: int = Field(default=0, ge=0)
    slice_queries: int = Field(default=0, ge=0)


class AttachmentReceipt(BaseModel):
    """一次图层挂载的回执：包含挂载瞬间被锚定历史事实的指纹证据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(min_length=1)
    annotation_sha256: str = Field(min_length=64, max_length=64)
    target_entity_id: str = Field(min_length=1)
    attached_at: datetime
    anchored_fact_sha256: dict[str, str] = Field(default_factory=dict)
    anchored_fact_count: int = Field(default=0, ge=0)
    overlay_hops: int = Field(default=MAX_OVERLAY_HOPS, ge=1, le=MAX_OVERLAY_HOPS)
    history_rewrites: int = Field(default=0, ge=0, le=0)
    derived_recomputations: int = Field(default=0, ge=0, le=0)
    idempotent_replay: bool = False


class SliceFactView(BaseModel):
    """历史切片中的一条原始事实视图（payload 与指纹与登记瞬间完全一致）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    object_type: ObjectType
    occurred_start: datetime | None = None
    occurred_end: datetime | None = None
    learned_at: datetime
    recorded_at: datetime
    payload_sha256: str = Field(min_length=64, max_length=64)
    payload: dict[str, Any]


class SliceOverlayView(BaseModel):
    """渲染在历史切片之上的解释图层视图。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    annotation_id: str = Field(min_length=1)
    semantic_overlay: str = Field(min_length=1)
    valid_time_start: datetime
    valid_time_end: datetime
    learned_at: datetime
    source_evidence_ref: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    status: OverlayStatus = "active"
    superseded_by: str | None = None
    annotation_sha256: str = Field(min_length=64, max_length=64)


class SliceCoverage(BaseModel):
    """真实、不含糊的切片覆盖率说明（被 cutoff 挡住的认知必须可见地记为“被挡住”）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    returned_facts: int = Field(default=0, ge=0)
    returned_overlays: int = Field(default=0, ge=0)
    hidden_by_cutoff_facts: int = Field(default=0, ge=0)
    hidden_by_cutoff_overlays: int = Field(default=0, ge=0)
    superseded_overlays_hidden: int = Field(default=0, ge=0)
    skipped_time_unknown_facts: int = Field(default=0, ge=0)
    cutoff_precedes_target: bool = False


class EpistemicSliceView(BaseModel):
    """一次双时间透镜查询的完整结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    target_time: datetime
    as_of_cutoff: datetime | None = None
    view_mode: ViewMode
    slice_mode: SliceMode = "instant"
    facts: tuple[SliceFactView, ...] = ()
    overlays: tuple[SliceOverlayView, ...] = ()
    overlay_labels: tuple[str, ...] = ()
    integrity: IntegrityReport
    recompute_audit: RecomputeAudit
    coverage: SliceCoverage

    @model_validator(mode="after")
    def validate_view_times(self) -> "EpistemicSliceView":
        require_aware(self.target_time, "target_time")
        require_aware(self.as_of_cutoff, "as_of_cutoff")
        if self.as_of_cutoff is None and self.view_mode != "current_cognition":
            raise ValueError("view without cutoff must use current_cognition mode")
        if self.as_of_cutoff is not None and self.view_mode != "as_of_cutoff":
            raise ValueError("view with cutoff must use as_of_cutoff mode")
        return self


# ---------------------------------------------------------------------------
# 双时间透镜
# ---------------------------------------------------------------------------


class EpistemicWorldLens:
    """双时间透镜：``valid time``（历史何时发生）× ``认知时间``（何时学到 / as_of_cutoff）。

    设计约束（全部由代码强制，而非注释承诺）：

    * **只读历史**：本类没有 ``update_* / delete_* / remove_* / rewrite_*`` 任何写历史
      的公开方法；查询返回的 payload 均为深拷贝；
    * **逐字节复核**：挂载与查询都会重算被触达事实的 SHA-256 并与登记指纹比对，
      任何不一致立即 :class:`HistoryImmutabilityViolation`；
    * **有界工作集**：校验与渲染严格限定在目标实体 + 目标时间窗口内，绝不扫描或
      重算全量历史，也绝不触发任何派生总结重算；
    * **认知只追加**：标注账本 append-only，同一 ``annotation_id`` 幂等重放，
      内容不同则判为 :data:`ErrorCode.IDEMPOTENCY_CONFLICT`；旧图层被取代时依然留存。
    """

    def __init__(
        self,
        facts: Iterable[WorldObject | Mapping[str, Any]] = (),
        *,
        require_anchored_target: bool = True,
    ) -> None:
        self._require_anchored_target = require_anchored_target
        # entity_id -> (object_id, revision) -> 只读锚点
        self._anchors_by_entity: dict[str, dict[tuple[str, int], FactAnchor]] = {}
        # (object_id, revision) -> 登记时拿到的活对象引用，仅用于篡改复核
        self._live_facts: dict[tuple[str, int], WorldObject] = {}
        # annotation_id -> 冻结标注（append-only，永不删除、永不改写）
        self._annotations: dict[str, RetrospectiveAnnotation] = {}
        self._attachments: list[AttachmentReceipt] = []
        self._blocked_history_rewrites = 0
        self._blocked_cascades = 0
        self._slice_queries = 0
        for fact in facts:
            self.register_fact(fact)

    # -- 只读属性 ----------------------------------------------------------

    @property
    def require_anchored_target(self) -> bool:
        return self._require_anchored_target

    @property
    def annotations(self) -> tuple[RetrospectiveAnnotation, ...]:
        """append-only 认知账本（含已被取代的旧图层）。"""

        return tuple(self._annotations.values())

    @property
    def attachments(self) -> tuple[AttachmentReceipt, ...]:
        return tuple(self._attachments)

    def fact_anchors(
        self,
        entity_id: str | None = None,
    ) -> tuple[FactAnchor, ...]:
        if entity_id is None:
            anchors: list[FactAnchor] = []
            for per_entity in self._anchors_by_entity.values():
                anchors.extend(per_entity.values())
            return tuple(anchors)
        return tuple(self._anchors_by_entity.get(entity_id, {}).values())

    # -- 历史事实登记（只读快照） -------------------------------------------

    def register_fact(
        self,
        fact: WorldObject | Mapping[str, Any],
        *,
        entity_ids: str | Iterable[str] | None = None,
    ) -> tuple[FactAnchor, ...]:
        """登记一条已经发生的客观事实，返回它在一个或多个实体下的只读锚点。

        登记只做两件事：计算规范 payload 的 SHA-256、建立时间/实体索引。
        同一 ``(object_id, revision)`` 只允许存在一种字节形态；若再次登记时指纹不同，
        说明有人试图改写历史，直接 :class:`HistoryImmutabilityViolation`。
        """

        obj = coerce_world_object(fact)
        payload, _encoded, digest = encode_fact_payload(obj)
        resolved = self._resolve_entity_ids(obj, entity_ids)

        pending: list[tuple[str, FactAnchor]] = []
        for entity_id in resolved:
            key = (obj.object_id, obj.revision)
            existing = self._anchors_by_entity.get(entity_id, {}).get(key)
            if existing is not None:
                if existing.payload_sha256 == digest:
                    pending.append((entity_id, existing))
                    continue
                self._blocked_history_rewrites += 1
                raise HistoryImmutabilityViolation(
                    ErrorCode.STORAGE_FAILURE,
                    "historical fact was rewritten: the same object_id/revision "
                    "already exists with different bytes",
                    context={
                        "reason": "history_immutability_violation",
                        "object_id": obj.object_id,
                        "revision": obj.revision,
                        "entity_id": entity_id,
                        "expected_sha256": existing.payload_sha256,
                        "observed_sha256": digest,
                    },
                )
            pending.append(
                (entity_id, self._build_anchor(entity_id, obj, payload, digest))
            )

        # 全部实体校验通过后才落账，保证多实体锚定的原子性。
        for entity_id, anchor in pending:
            per_entity = self._anchors_by_entity.setdefault(entity_id, {})
            per_entity[(anchor.object_id, anchor.revision)] = anchor
        self._live_facts[(obj.object_id, obj.revision)] = obj
        return tuple(anchor for _entity_id, anchor in pending)

    def register_facts(
        self,
        facts: Iterable[WorldObject | Mapping[str, Any]],
        *,
        entity_ids: str | Iterable[str] | None = None,
    ) -> tuple[FactAnchor, ...]:
        anchors: list[FactAnchor] = []
        for fact in facts:
            anchors.extend(self.register_fact(fact, entity_ids=entity_ids))
        return tuple(anchors)

    def record_observation(
        self,
        observation: WorldObject | Mapping[str, Any],
        *,
        involved_entity_ids: str | Iterable[str] | None = None,
    ) -> str:
        """多方工单 API 兼容：委托给 register_fact，返回首个锚点 SHA-256。"""
        anchors = self.register_fact(observation, entity_ids=involved_entity_ids)
        return anchors[0].sha256 if anchors else ""

    def _build_anchor(
        self,
        entity_id: str,
        obj: WorldObject,
        payload: dict[str, Any],
        digest: str,
    ) -> FactAnchor:
        extent = obj.occurred
        return FactAnchor(
            entity_id=entity_id,
            object_id=obj.object_id,
            revision=obj.revision,
            object_type=ObjectType(obj.object_type),
            occurred_start=(
                None
                if extent.unknown or extent.start is None
                else as_utc(extent.start, "occurred.start")
            ),
            occurred_end=(
                None
                if extent.unknown or extent.end is None
                else as_utc(extent.end, "occurred.end")
            ),
            time_unknown=bool(extent.unknown),
            learned_at=as_utc(obj.learned_at, "learned_at"),
            recorded_at=as_utc(obj.recorded_at, "recorded_at"),
            payload=copy.deepcopy(payload),
            payload_sha256=digest,
        )

    def _resolve_entity_ids(
        self,
        obj: WorldObject,
        entity_ids: str | Iterable[str] | None,
    ) -> tuple[str, ...]:
        if entity_ids is None:
            meta_value = obj.metadata.get("entity_id", obj.metadata.get("entity_ids"))
            if isinstance(meta_value, str):
                candidates: Iterable[str] = (meta_value,)
            elif isinstance(meta_value, (list, tuple)):
                candidates = tuple(str(item) for item in meta_value)
            else:
                candidates = (obj.subject_id,)
        elif isinstance(entity_ids, str):
            candidates = (entity_ids,)
        else:
            candidates = tuple(entity_ids)

        resolved: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate.strip():
                raise RetrospectiveAnnotationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "entity id must be a non-blank string",
                    context={
                        "reason": "entity_id_invalid",
                        "object_id": obj.object_id,
                    },
                )
            if candidate not in resolved:
                resolved.append(candidate)

        if not resolved:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "fact must be anchored to at least one entity",
                context={
                    "reason": "entity_id_missing",
                    "object_id": obj.object_id,
                },
            )
        return tuple(resolved)

    # -- 图层挂载（append-only，严格单跳） -----------------------------------

    def attach_annotation(
        self,
        annotation: RetrospectiveAnnotation,
    ) -> AttachmentReceipt:
        """把今天产生的新认知以外挂图层挂载到过去的时间切片。

        挂载过程**只写认知账本**：它会复核目标窗口内历史事实的 SHA-256，
        但绝不修改、绝不重算任何历史对象或派生总结。
        """

        # 双线兼容：本线契约、战队基线契约、原始映射都可以挂载（统一收敛后再校验）。
        annotation = coerce_annotation(annotation)

        digest = annotation_sha256(annotation)
        existing = self._annotations.get(annotation.annotation_id)
        if existing is not None:
            if annotation_sha256(existing) != digest:
                raise RetrospectiveAnnotationError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "annotation_id was already attached with different content",
                    context={
                        "reason": "annotation_fingerprint_mismatch",
                        "annotation_id": annotation.annotation_id,
                    },
                )
            annotation = existing

        self._assert_single_hop(annotation)
        self._assert_bounded_supersede_chain(annotation)

        window_anchors = self._anchors_intersecting(
            annotation.target_entity_id,
            annotation.valid_time_start,
            annotation.valid_time_end,
        )
        if not window_anchors and self._require_anchored_target:
            raise AnnotationTargetNotFound(
                ErrorCode.NOT_FOUND,
                "retrospective annotation does not point at any registered "
                "historical time slice",
                context={
                    "reason": "annotation_target_not_found",
                    "target_entity_id": annotation.target_entity_id,
                    "valid_time_start": canonical_utc_iso(
                        annotation.valid_time_start, "valid_time_start"
                    ),
                    "valid_time_end": canonical_utc_iso(
                        annotation.valid_time_end, "valid_time_end"
                    ),
                },
            )

        # 宪法红线复核：只在被指针命中的历史切片上校验，绝不扫描全量历史。
        self._verify_anchors(window_anchors)

        is_replay = existing is not None
        if not is_replay:
            self._annotations[annotation.annotation_id] = annotation

        receipt = AttachmentReceipt(
            annotation_id=annotation.annotation_id,
            annotation_sha256=digest,
            target_entity_id=annotation.target_entity_id,
            attached_at=utc_now(),
            anchored_fact_sha256={
                f"{anchor.object_id}@{anchor.revision}": anchor.payload_sha256
                for anchor in window_anchors
            },
            anchored_fact_count=len(window_anchors),
            overlay_hops=MAX_OVERLAY_HOPS,
            history_rewrites=0,
            derived_recomputations=0,
            idempotent_replay=is_replay,
        )
        if not is_replay:
            self._attachments.append(receipt)
        return receipt

    def _assert_single_hop(self, annotation: RetrospectiveAnnotation) -> None:
        """严格单跳：图层只能指向原始事实，禁止指向另一条图层。"""

        if annotation.target_entity_id in self._annotations:
            self._blocked_cascades += 1
            raise OverlayCascadeForbidden(
                ErrorCode.INVALID_ARGUMENT,
                "semantic overlay must not be attached on top of another overlay "
                f"(max overlay hops = {MAX_OVERLAY_HOPS})",
                context={
                    "reason": "overlay_of_overlay_forbidden",
                    "annotation_id": annotation.annotation_id,
                    "target_entity_id": annotation.target_entity_id,
                    "max_overlay_hops": MAX_OVERLAY_HOPS,
                },
            )

    def _assert_bounded_supersede_chain(
        self,
        annotation: RetrospectiveAnnotation,
    ) -> None:
        """认知向前演化的链条必须有界且可解析，杜绝无界级联递归。"""

        if annotation.supersedes_annotation_id is None:
            return

        superseded = self._annotations.get(annotation.supersedes_annotation_id)
        if superseded is None:
            raise RetrospectiveAnnotationError(
                ErrorCode.NOT_FOUND,
                "superseded annotation is not present in the append-only ledger",
                context={
                    "reason": "supersede_target_missing",
                    "annotation_id": annotation.annotation_id,
                    "supersedes_annotation_id": annotation.supersedes_annotation_id,
                },
            )
        if superseded.target_entity_id != annotation.target_entity_id:
            self._blocked_cascades += 1
            raise OverlayCascadeForbidden(
                ErrorCode.INVALID_ARGUMENT,
                "superseding overlay must stay on the same target entity",
                context={
                    "reason": "supersede_entity_mismatch",
                    "annotation_id": annotation.annotation_id,
                    "supersedes_annotation_id": annotation.supersedes_annotation_id,
                },
            )

        # 单趟迭代走链（非递归），并施加硬上限。
        seen = {annotation.annotation_id}
        current: RetrospectiveAnnotation | None = superseded
        depth = 0
        while current is not None:
            depth += 1
            if depth > MAX_SUPERSEDE_CHAIN_DEPTH:
                self._blocked_cascades += 1
                raise OverlayCascadeForbidden(
                    ErrorCode.INVALID_ARGUMENT,
                    "supersede chain exceeds the bounded single-hop budget",
                    context={
                        "reason": "supersede_chain_unbounded",
                        "annotation_id": annotation.annotation_id,
                        "max_supersede_chain_depth": MAX_SUPERSEDE_CHAIN_DEPTH,
                    },
                )
            previous_id = current.supersedes_annotation_id
            if previous_id is None:
                return
            if previous_id in seen:
                self._blocked_cascades += 1
                raise OverlayCascadeForbidden(
                    ErrorCode.INVALID_ARGUMENT,
                    "supersede chain must stay acyclic",
                    context={
                        "reason": "supersede_cycle",
                        "annotation_id": annotation.annotation_id,
                        "cycle_annotation_id": previous_id,
                    },
                )
            seen.add(previous_id)
            current = self._annotations.get(previous_id)
            if current is None:
                raise RetrospectiveAnnotationError(
                    ErrorCode.NOT_FOUND,
                    "supersede chain references a missing annotation",
                    context={
                        "reason": "supersede_chain_broken",
                        "missing_annotation_id": previous_id,
                    },
                )

    def _anchors_intersecting(
        self,
        entity_id: str,
        start: datetime,
        end: datetime,
    ) -> tuple[FactAnchor, ...]:
        left = _coerce_utc(start, "valid_time_start")
        right = _coerce_utc(end, "valid_time_end")
        anchors = [
            anchor
            for anchor in self._anchors_by_entity.get(entity_id, {}).values()
            if anchor.intersects(left, right)
        ]
        anchors.sort(key=lambda anchor: (anchor.object_id, anchor.revision))
        return tuple(anchors)

    def _superseded_by_map(self, cutoff: datetime | None) -> dict[str, str]:
        """单趟推导“谁被谁取代”，绝不递归回溯历史。

        “取代”本身也是认知：只有在该 cutoff 之下已经学到的取代关系才算数，
        否则两年前那个视角会提前看见今天才发生的认知修正。
        """

        mapping: dict[str, str] = {}
        for annotation in self._annotations.values():
            target = annotation.supersedes_annotation_id
            if target is None:
                continue
            if cutoff is not None and as_utc(
                annotation.learned_at, "learned_at"
            ) > cutoff:
                continue
            mapping.setdefault(target, annotation.annotation_id)
        return mapping

    # -- 完整性复核 ---------------------------------------------------------

    def verify_history_integrity(
        self,
        entity_id: str | None = None,
    ) -> IntegrityReport:
        """复核底层原始事实的 SHA-256 是否仍然与登记瞬间一致（只读诊断）。"""

        anchors: list[FactAnchor] = []
        if entity_id is None:
            for per_entity in self._anchors_by_entity.values():
                anchors.extend(per_entity.values())
        else:
            anchors.extend(self._anchors_by_entity.get(entity_id, {}).values())

        unique: dict[tuple[str, int], FactAnchor] = {}
        for anchor in anchors:
            unique.setdefault((anchor.object_id, anchor.revision), anchor)
        return self._inspect_anchors(tuple(unique.values()))

    def _inspect_anchors(self, anchors: Iterable[FactAnchor]) -> IntegrityReport:
        findings: list[FactTamperFinding] = []
        checked = 0
        for anchor in anchors:
            checked += 1
            live = self._live_facts.get((anchor.object_id, anchor.revision))
            if live is None:
                continue
            try:
                observed: str | None = fact_sha256(live)
                reason: TamperReason = "digest_mismatch"
            except (RetrospectiveAnnotationError, DurableJSONError, TypeError):
                observed = None
                reason = "payload_unreadable"
            if observed != anchor.payload_sha256:
                findings.append(
                    FactTamperFinding(
                        object_id=anchor.object_id,
                        revision=anchor.revision,
                        expected_sha256=anchor.payload_sha256,
                        observed_sha256=observed,
                        reason=reason,
                    )
                )
        return IntegrityReport(
            checked_facts=checked,
            verified=not findings,
            tampered=tuple(findings),
        )

    def _verify_anchors(self, anchors: Iterable[FactAnchor]) -> IntegrityReport:
        report = self._inspect_anchors(anchors)
        if not report.verified:
            self._blocked_history_rewrites += 1
            first = report.tampered[0]
            raise HistoryImmutabilityViolation(
                ErrorCode.STORAGE_FAILURE,
                "historical raw fact failed SHA-256 verification; the lens refuses "
                "to attach or render overlays on tampered history",
                context={
                    "reason": "history_immutability_violation",
                    "algorithm": DIGEST_ALGORITHM,
                    "tampered_object_ids": [
                        finding.object_id for finding in report.tampered
                    ],
                    "object_id": first.object_id,
                    "revision": first.revision,
                    "expected_sha256": first.expected_sha256,
                    "observed_sha256": first.observed_sha256,
                    "tamper_reason": first.reason,
                },
            )
        return report

    # -- 双时间视图查询 -----------------------------------------------------

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
        *,
        include_superseded: bool = False,
        slice_mode: SliceMode = "instant",
    ) -> dict[str, Any]:
        """双时间透镜查询，返回 JSON 友好的历史切片视图。

        * ``as_of_cutoff`` 给定（例如“两年前”）→ ``view_mode = "as_of_cutoff"``：
          只返回当时已知的原始事实，今天才学到的图层与新事实一个字都不泄露，
          完全重现当时的历史人生原貌；
        * ``as_of_cutoff is None`` → ``view_mode = "current_cognition"``：
          在**同一段未被改写**的历史切片上动态渲染今天的解释图层（警示标记）；
          两种视图返回的事实 payload 与 SHA-256 完全相同。
        """

        view = self.query_slice_view(
            entity_id,
            target_time,
            as_of_cutoff,
            include_superseded=include_superseded,
            slice_mode=slice_mode,
        )
        dump = view.model_dump(mode="json")
        dump["overlay_suppressed_by_cutoff"] = view.coverage.hidden_by_cutoff_overlays
        return dump

    def query_slice_view(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
        *,
        include_superseded: bool = False,
        slice_mode: SliceMode = "instant",
    ) -> EpistemicSliceView:
        """:meth:`query_historical_slice` 的强类型版本。"""

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "entity_id must be a non-blank string",
                context={"reason": "entity_id_invalid"},
            )
        instant = _coerce_utc(target_time, "target_time")
        cutoff = None if as_of_cutoff is None else _coerce_utc(as_of_cutoff, "as_of_cutoff")

        if slice_mode not in ("instant", "cumulative"):
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "slice_mode must be either 'instant' or 'cumulative'",
                context={
                    "reason": "slice_mode_invalid",
                    "slice_mode": str(slice_mode),
                },
            )
        selected_anchors, fact_views, fact_coverage = self._select_facts(
            entity_id,
            instant,
            cutoff,
            slice_mode,
        )
        _overlay_annotations, overlay_views, overlay_coverage = self._select_overlays(
            entity_id,
            instant,
            cutoff,
            include_superseded=include_superseded,
            slice_mode=slice_mode,
        )
        # 宪法红线复核：严格限定在本次切片命中的事实上，绝不扫描或重算全量历史。
        integrity = self._verify_anchors(selected_anchors)
        self._slice_queries += 1
        return EpistemicSliceView(
            entity_id=entity_id,
            target_time=instant,
            as_of_cutoff=cutoff,
            view_mode="as_of_cutoff" if cutoff is not None else "current_cognition",
            slice_mode=slice_mode,
            facts=tuple(fact_views),
            overlays=tuple(overlay_views),
            overlay_labels=tuple(
                dict.fromkeys(
                    view.semantic_overlay
                    for view in overlay_views
                    if view.status == "active"
                )
            ),
            integrity=integrity,
            recompute_audit=self.recompute_audit(),
            coverage=SliceCoverage(
                returned_facts=len(fact_views),
                returned_overlays=len(overlay_views),
                hidden_by_cutoff_facts=fact_coverage["hidden_by_cutoff"],
                hidden_by_cutoff_overlays=overlay_coverage["hidden_by_cutoff"],
                superseded_overlays_hidden=overlay_coverage["superseded_hidden"],
                skipped_time_unknown_facts=fact_coverage["time_unknown"],
                cutoff_precedes_target=(
                    cutoff is not None and cutoff < instant
                ),
            ),
        )

    def _select_facts(
        self,
        entity_id: str,
        instant: datetime,
        cutoff: datetime | None,
        slice_mode: SliceMode = "instant",
    ) -> tuple[tuple[FactAnchor, ...], list[SliceFactView], dict[str, int]]:
        hidden_by_cutoff = 0
        time_unknown = 0
        # 只在目标实体的锚点内选取“当时可见的最新版本”，与 storage 层
        # knowledge_cutoff 语义一致：learned_at <= cutoff。
        visible: dict[str, FactAnchor] = {}
        for anchor in self._anchors_by_entity.get(entity_id, {}).values():
            if anchor.time_unknown:
                time_unknown += 1
                continue
            in_slice = (
                anchor.covers(instant)
                if slice_mode == "instant"
                else anchor.started_by(instant)
            )
            if not in_slice:
                continue
            if cutoff is not None and anchor.learned_at > cutoff:
                hidden_by_cutoff += 1
                continue
            current = visible.get(anchor.object_id)
            if current is None or anchor.revision > current.revision:
                visible[anchor.object_id] = anchor

        selected = sorted(
            visible.values(),
            key=lambda anchor: (
                canonical_utc_iso(anchor.recorded_at, "recorded_at"),
                anchor.object_id,
                anchor.revision,
            ),
        )
        views = [
            SliceFactView(
                object_id=anchor.object_id,
                revision=anchor.revision,
                object_type=anchor.object_type,
                occurred_start=anchor.occurred_start,
                occurred_end=anchor.occurred_end,
                learned_at=anchor.learned_at,
                recorded_at=anchor.recorded_at,
                payload_sha256=anchor.payload_sha256,
                payload=anchor.payload_copy(),
            )
            for anchor in selected
        ]
        return (
            tuple(selected),
            views,
            {
                "hidden_by_cutoff": hidden_by_cutoff,
                "time_unknown": time_unknown,
            },
        )

    def _select_overlays(
        self,
        entity_id: str,
        instant: datetime,
        cutoff: datetime | None,
        *,
        include_superseded: bool,
        slice_mode: SliceMode = "instant",
    ) -> tuple[
        list[RetrospectiveAnnotation],
        list[SliceOverlayView],
        dict[str, int],
    ]:
        hidden_by_cutoff = 0
        superseded_hidden = 0
        superseded_by = self._superseded_by_map(cutoff)
        selected: list[tuple[RetrospectiveAnnotation, SliceOverlayView]] = []
        for annotation in self._annotations.values():
            if annotation.target_entity_id != entity_id:
                continue
            in_slice = (
                annotation.covers(instant)
                if slice_mode == "instant"
                else annotation.started_by(instant)
            )
            if not in_slice:
                continue
            learned_at = as_utc(annotation.learned_at, "learned_at")
            # 铁律：历史 cutoff 之下，今天才学到的新认知绝对不可泄露。
            if cutoff is not None and learned_at > cutoff:
                hidden_by_cutoff += 1
                continue
            status: OverlayStatus = (
                "superseded"
                if annotation.annotation_id in superseded_by
                else "active"
            )
            if status == "superseded" and not include_superseded:
                superseded_hidden += 1
                continue
            selected.append(
                (
                    annotation,
                    SliceOverlayView(
                        annotation_id=annotation.annotation_id,
                        semantic_overlay=annotation.semantic_overlay,
                        valid_time_start=as_utc(
                            annotation.valid_time_start, "valid_time_start"
                        ),
                        valid_time_end=as_utc(
                            annotation.valid_time_end, "valid_time_end"
                        ),
                        learned_at=learned_at,
                        source_evidence_ref=annotation.source_evidence_ref,
                        confidence=annotation.confidence,
                        status=status,
                        superseded_by=superseded_by.get(annotation.annotation_id),
                        annotation_sha256=annotation_sha256(annotation),
                    ),
                )
            )
        selected.sort(
            key=lambda item: (
                canonical_utc_iso(item[1].learned_at, "learned_at"),
                item[1].annotation_id,
            )
        )
        return (
            [annotation for annotation, _view in selected],
            [view for _annotation, view in selected],
            {
                "hidden_by_cutoff": hidden_by_cutoff,
                "superseded_hidden": superseded_hidden,
            },
        )

    def active_annotations(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
        *,
        include_superseded: bool = False,
        slice_mode: SliceMode = "instant",
    ) -> tuple[RetrospectiveAnnotation, ...]:
        """返回某个历史时刻在该认知截止下可见的图层对象（冻结原件，非视图）。"""

        instant = _coerce_utc(target_time, "target_time")
        cutoff = (
            None
            if as_of_cutoff is None
            else _coerce_utc(as_of_cutoff, "as_of_cutoff")
        )
        annotations, _views, _coverage = self._select_overlays(
            entity_id,
            instant,
            cutoff,
            include_superseded=include_superseded,
            slice_mode=slice_mode,
        )
        return tuple(annotations)

    # -- 级联审计 -----------------------------------------------------------

    def recompute_audit(self) -> RecomputeAudit:
        """证明本引擎从未改写历史、从未级联重算派生对象。"""

        return RecomputeAudit(
            max_overlay_hops=MAX_OVERLAY_HOPS,
            overlay_hops_used=MAX_OVERLAY_HOPS,
            max_recursion_depth=0,
            history_rewrites=0,
            derived_recomputations=0,
            history_rewrite_attempts_blocked=self._blocked_history_rewrites,
            cascade_attempts_blocked=self._blocked_cascades,
            facts_registered=sum(
                len(per_entity) for per_entity in self._anchors_by_entity.values()
            ),
            annotations_attached=len(self._attachments),
            slice_queries=self._slice_queries,
        )

    # -- 与既有 M0 历史读门面的对接（只读） ----------------------------------

    @classmethod
    def from_historical_query(
        cls,
        query: "HistoricalWorldQuery",
        *,
        entity_ids: str | Iterable[str] | None = None,
        object_type: ObjectType | None = None,
        subject_id: str | None = None,
        as_of_world_revision: int | None = None,
        knowledge_cutoff: datetime | None = None,
        require_anchored_target: bool = True,
    ) -> "EpistemicWorldLens":
        """用 M0-020 的只读历史门面装载事实，构建同一套双时间透镜。

        装载进来的持久化 payload 会经过规范模型再校验，其 SHA-256 与
        ``object_revisions.payload_json`` 行字节同源，因此“原始数据哈希永久不变”
        可以直接在 SQLite 层逐字节复核。
        """

        result = query.list(
            object_type=object_type,
            subject_id=subject_id,
            as_of_world_revision=as_of_world_revision,
            knowledge_cutoff=knowledge_cutoff,
        )
        lens = cls(require_anchored_target=require_anchored_target)
        for payload in result.payloads:
            lens.register_fact(payload, entity_ids=entity_ids)
        return lens


# ---------------------------------------------------------------------------
# 升级版工单契约：HistoricalEpistemicSlice + BiTemporalEpistemicLens
# ---------------------------------------------------------------------------


def _render_effective_interpretation(
    entity_id: str,
    view_kind: Literal["AS_OF", "CURRENT"],
    annotations: Iterable[RetrospectiveAnnotation],
    as_of_cutoff: datetime | None,
) -> str:
    """渲染“此刻对这个实体的生效解释”，绝不改写历史事实本身。"""

    labels = [annotation.semantic_overlay for annotation in annotations]
    if not labels:
        if view_kind == "AS_OF":
            cutoff_text = (
                "当时"
                if as_of_cutoff is None
                else canonical_utc_iso(as_of_cutoff, "as_of_cutoff")
            )
            return (
                f"{entity_id} 在 {cutoff_text} 的当时已知认知原貌："
                "无任何事后重估图层（严禁事后诸葛亮的历史虚无主义）"
            )
        return f"{entity_id} 当前认知：暂无外挂重估图层，历史事实按原貌呈现"
    return (
        f"{entity_id} 当前认知叠加（T_now 外挂解释图层）："
        + "；".join(labels)
        + "——历史事实原貌与其 SHA-256 保持不变"
    )


class HistoricalEpistemicSlice(BaseModel):
    """双时间透镜查询产物：呈现当时历史与外挂注记（升级版工单契约）。

    工单骨架字段（``entity_id / query_time / as_of_cutoff / raw_observations /
    active_annotations / effective_interpretation``）全部保留，本线额外增补
    ``view_kind`` 与 ``raw_observation_digests``：让“历史哈希 100% 不变”这条门禁
    可以直接在查询产物上自证，无需回到引擎内部取证。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    query_time: datetime
    as_of_cutoff: datetime | None = None
    raw_observations: list[dict[str, Any]] = Field(default_factory=list)
    active_annotations: list[RetrospectiveAnnotation] = Field(default_factory=list)
    effective_interpretation: str = Field(min_length=1)
    view_kind: Literal["AS_OF", "CURRENT"] = "CURRENT"
    raw_observation_digests: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_slice_times(self) -> "HistoricalEpistemicSlice":
        require_aware(self.query_time, "query_time")
        require_aware(self.as_of_cutoff, "as_of_cutoff")
        if self.as_of_cutoff is None and self.view_kind != "CURRENT":
            raise ValueError("slice without cutoff must use CURRENT view_kind")
        if self.as_of_cutoff is not None and self.view_kind != "AS_OF":
            raise ValueError("slice with cutoff must use AS_OF view_kind")
        return self

    @property
    def has_overlay(self) -> bool:
        return bool(self.active_annotations)

    @property
    def target_time(self) -> datetime:
        """引擎内视图统一叫 ``target_time``；工单骨架字段名是 ``query_time``（同值）。"""

        return self.query_time


def _iter_source(source: Any) -> tuple[Any, ...]:
    """把工单骨架里的 ``raw_store`` / ``annotation_store`` 归一成可迭代来源。"""

    if source is None:
        return ()
    if isinstance(source, EpistemicWorldLens):
        raise TypeError(
            "pass an existing engine through engine=... instead of raw_store"
        )
    if isinstance(source, (BaseModel, Mapping, str, bytes)):
        return (source,)
    payloads = getattr(source, "payloads", None)
    if isinstance(payloads, (list, tuple)):
        return tuple(payloads)
    if isinstance(source, Iterable):
        return tuple(source)
    raise TypeError(
        "store must be an iterable of facts/annotations or a query result, "
        f"got {type(source).__name__}"
    )


class BiTemporalEpistemicLens:
    """双时间认知透镜（事件时间 × 知识时间）——升级版工单契约外壳。

    构造签名遵循工单骨架 ``BiTemporalEpistemicLens(raw_store, annotation_store)``：
    两个 store 只需是可迭代的事实/注记来源（``WorldObject``、持久化 payload 映射、
    ``HistoricalQueryResult`` 或注记序列）。全部语义委托给 :class:`EpistemicWorldLens`
    引擎，因此 SHA-256 逐字节复核、严格单跳、幂等挂载与 cutoff 防泄露同源生效。
    """

    def __init__(
        self,
        raw_store: Any = None,
        annotation_store: Any = None,
        *,
        engine: EpistemicWorldLens | None = None,
        require_anchored_target: bool = True,
    ) -> None:
        if engine is not None and (
            raw_store is not None or annotation_store is not None
        ):
            raise ValueError(
                "engine and raw_store/annotation_store are mutually exclusive"
            )
        self._engine = (
            engine
            if engine is not None
            else EpistemicWorldLens(require_anchored_target=require_anchored_target)
        )
        # 工单骨架原文语义：raw_store / annotation_store 就是调用方注入的那两个库对象
        self.raw_store: Any = raw_store
        self.annotation_store: Any = annotation_store
        for fact in _iter_source(raw_store):
            self._engine.register_fact(fact)
        for annotation in _iter_source(annotation_store):
            self.attach_annotation(annotation)

    @property
    def engine(self) -> EpistemicWorldLens:
        """底层引擎（历史事实账本 + 认知账本 + 完整性复核）。"""

        return self._engine

    @property
    def registered_annotations(self) -> tuple[RetrospectiveAnnotation, ...]:
        """经契约校验后落入 append-only 认知账本的图层（可能是基线契约投影而来）。"""

        return self._engine.annotations

    @property
    def registered_fact_count(self) -> int:
        """已锚定的历史事实条数（引擎只读事实账本规模）。"""

        return len(self._engine.fact_anchors())

    def attach_annotation(self, annotation: Any) -> AttachmentReceipt:
        """在今天追加一条外挂解释图层（委托引擎，含单跳与哈希门禁）。"""

        return self._engine.attach_annotation(annotation)

    def query_entity_state(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
        *,
        include_superseded: bool = False,
        slice_mode: SliceMode = "instant",
    ) -> HistoricalEpistemicSlice:
        """查询实体在某个历史时刻、某个知识截止下的完整认知状态。

        ``slice_mode="cumulative"`` 复现战队基线的累积切片语义 ``(-∞, target_time]``
        （“第 100 天时面对的世界”），默认 ``"instant"`` 则是精确时间点/区间切片。
        """

        view = self._engine.query_slice_view(
            entity_id,
            target_time,
            as_of_cutoff,
            include_superseded=include_superseded,
            slice_mode=slice_mode,
        )
        annotations = list(
            self._engine.active_annotations(
                entity_id,
                target_time,
                as_of_cutoff,
                include_superseded=include_superseded,
                slice_mode=slice_mode,
            )
        )
        view_kind: Literal["AS_OF", "CURRENT"] = (
            "AS_OF" if view.as_of_cutoff is not None else "CURRENT"
        )
        return HistoricalEpistemicSlice(
            entity_id=view.entity_id,
            query_time=view.target_time,
            as_of_cutoff=view.as_of_cutoff,
            raw_observations=[fact.payload for fact in view.facts],
            active_annotations=annotations,
            effective_interpretation=_render_effective_interpretation(
                view.entity_id,
                view_kind,
                annotations,
                view.as_of_cutoff,
            ),
            view_kind=view_kind,
            raw_observation_digests={
                f"{fact.object_id}@{fact.revision}": fact.payload_sha256
                for fact in view.facts
            },
        )

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
        *,
        include_superseded: bool = False,
        slice_mode: SliceMode = "instant",
    ) -> dict[str, Any]:
        """一号工单签名形态：``query_historical_slice(...) -> Dict[str, Any]``。"""

        return self._engine.query_historical_slice(
            entity_id,
            target_time,
            as_of_cutoff,
            include_superseded=include_superseded,
            slice_mode=slice_mode,
        )


# ---------------------------------------------------------------------------
# 门禁 4：单跳级联隔离器（彻底掐灭 210 次递归算力雪崩）
# ---------------------------------------------------------------------------

#: 只读诊断允许展开的最大层数（失效标记永远只有 1 跳，诊断也不许无界）。
MAX_DIAGNOSTIC_DEPTH: Final[int] = 8


def normalize_dependency_graph(
    dependency_graph: Mapping[str, Iterable[str]] | Iterable[Dependency],
) -> dict[str, tuple[str, ...]]:
    """把依赖来源规范化为 ``upstream -> downstream`` 邻接表。

    接受两种形态：

    * ``Mapping[str, Iterable[str]]``：已经是“上游 → 直接下游”的邻接表；
    * ``Iterable[Dependency]``：M0-005 的显式依赖记录，其中
      ``dependency_ref`` 是被依赖的上游、``dependent_ref`` 是消费它的下游。
    """

    adjacency: dict[str, list[str]] = {}

    def add(upstream: str, downstream: str) -> None:
        if not isinstance(upstream, str) or not upstream.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "dependency graph node id must be a non-blank string",
                context={"reason": "dependency_node_invalid"},
            )
        if not isinstance(downstream, str) or not downstream.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "dependency graph node id must be a non-blank string",
                context={"reason": "dependency_node_invalid"},
            )
        adjacency.setdefault(upstream, []).append(downstream)

    if isinstance(dependency_graph, Mapping):
        for upstream, downstream_nodes in dependency_graph.items():
            if isinstance(downstream_nodes, str):
                add(str(upstream), downstream_nodes)
                continue
            for downstream in downstream_nodes:
                add(str(upstream), str(downstream))
        return {
            upstream: tuple(dict.fromkeys(nodes))
            for upstream, nodes in adjacency.items()
        }

    for edge in dependency_graph:
        if not isinstance(edge, Dependency):
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "dependency graph iterable must contain Dependency records",
                context={
                    "reason": "dependency_edge_invalid",
                    "got": type(edge).__name__,
                },
            )
        add(edge.dependency_ref.object_id, edge.dependent_ref.object_id)

    return {
        upstream: tuple(dict.fromkeys(nodes))
        for upstream, nodes in adjacency.items()
    }


def _direct_consumers(dependency_graph: Any, origin_node_id: str) -> tuple[str, ...]:
    """取出源节点的直接（1 级）下游消费者——这是隔离器唯一允许的邻接查询。"""

    if dependency_graph is None:
        return ()

    if isinstance(dependency_graph, Mapping):
        raw = dependency_graph.get(origin_node_id, ())
        nodes = (raw,) if isinstance(raw, str) else tuple(raw)
        return tuple(dict.fromkeys(str(node) for node in nodes))

    consumer_api = getattr(dependency_graph, "direct_consumers", None)
    if callable(consumer_api):
        nodes = consumer_api(origin_node_id)
        return tuple(dict.fromkeys(str(node) for node in nodes))

    if isinstance(dependency_graph, Iterable):
        adjacency = normalize_dependency_graph(dependency_graph)
        return adjacency.get(origin_node_id, ())

    raise RetrospectiveAnnotationError(
        ErrorCode.INVALID_ARGUMENT,
        "dependency_graph must be a mapping, a Dependency iterable or an object "
        "exposing direct_consumers(node_id)",
        context={
            "reason": "dependency_graph_invalid",
            "got": type(dependency_graph).__name__,
        },
    )


class SingleHopInvalidationReport(BaseModel):
    """单跳失效报告（字段命名与战队基线 ``InvalidationReport`` 对齐，便于逐行比对）。

    ``graph_queries`` 与 ``second_hop_expanded`` 被契约锁死：邻接查询最多 1 次、
    2 级展开只能是 ``False``，``llm_recompute_triggered`` 只能是 0——
    一份“发生过级联递归”的报告在构造阶段就无法被表达出来。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    annotation_id: str = Field(min_length=1)
    origin_node_id: str = Field(min_length=1)
    marked_stale: tuple[str, ...] = ()
    marked_stale_count: int = Field(default=0, ge=0)
    traversal_depth_reached: int = Field(default=1, ge=1, le=MAX_OVERLAY_HOPS)
    graph_queries: int = Field(default=1, ge=1, le=1)
    nodes_visited: int = Field(default=0, ge=0)
    llm_recompute_triggered: int = Field(default=0, ge=0, le=0)
    second_hop_expanded: Literal[False] = False
    cascade_suppressed: Literal[True] = True
    stale_reason: str = Field(min_length=1)
    stale_at: datetime
    untouched_downstream: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_report_counts(self) -> "SingleHopInvalidationReport":
        require_aware(self.stale_at, "stale_at")
        if self.marked_stale_count != len(self.marked_stale):
            raise ValueError("marked_stale_count must equal len(marked_stale)")
        if len(set(self.marked_stale)) != len(self.marked_stale):
            raise ValueError("marked_stale must not contain duplicates")
        return self


class SingleHopCascadeIsolator:
    """单跳级联隔离器：新认知只写在今天，只把 1 级直接下游打上 ``is_stale``。

    * **邻接查询严格 1 次**：只问“谁直接消费这个实体的认知”，绝不追问下游的下游；
    * **2 级及更远坚决不展开**：``second_hop_expanded`` 被契约锁死为 ``False``；
    * **大模型重算触发次数恒为 0**：懒加载复核由 M3-001R 的按需 Worker 负责，
      本隔离器即使拿到 ``recompute_hook`` 也绝不调用（单测以间谍回调实证）；
    * 需要看清“雪崩被掐灭在哪里”时，显式调用只读的
      :meth:`diagnose_suppressed_downstream`，它与失效标记、重算完全解耦。
    """

    def __init__(
        self,
        *,
        recompute_hook: Callable[[str], Any] | None = None,
    ) -> None:
        self._recompute_hook = recompute_hook
        self._recompute_calls: list[str] = []
        self._stale_reasons: dict[str, str] = {}
        self._stale_reports: dict[str, SingleHopInvalidationReport] = {}
        self._last_report: SingleHopInvalidationReport | None = None
        self._isolations = 0
        self._blocked_cascades = 0

    @property
    def recompute_calls(self) -> tuple[str, ...]:
        """被触发的重算调用（恒为空——本隔离器从不主动重算）。"""

        return tuple(self._recompute_calls)

    @property
    def isolation_count(self) -> int:
        return self._isolations

    def stale_nodes(self) -> frozenset[str]:
        return frozenset(self._stale_reasons)

    def is_stale(self, node_id: str) -> bool:
        return node_id in self._stale_reasons

    def stale_reason(self, node_id: str) -> str | None:
        return self._stale_reasons.get(node_id)

    def stale_report(self, node_id: str) -> SingleHopInvalidationReport | None:
        return self._stale_reports.get(node_id)

    def last_report(self) -> SingleHopInvalidationReport | None:
        return self._last_report

    def invalidate_downstream_single_hop(
        self,
        entity_id: str,
        annotation: Any,
        dependency_graph: Any,
        *,
        origin_node_id: str | None = None,
        max_hops: int = MAX_OVERLAY_HOPS,
        stale_reason: str | None = None,
    ) -> set[str]:
        """仅把直接消费该实体认知的 1 级下游标记为 ``is_stale``，返回被标记节点集。

        对二度及更远的间接节点坚决禁止级联递归触发展开：``max_hops`` 只接受 1，
        任何其他值都会被判为违宪的无界级联请求并直接拒绝。
        """

        coerced = coerce_annotation(annotation)

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "entity_id must be a non-blank string",
                context={"reason": "entity_id_invalid"},
            )

        if max_hops != MAX_OVERLAY_HOPS:
            self._blocked_cascades += 1
            raise OverlayCascadeForbidden(
                ErrorCode.INVALID_ARGUMENT,
                "cascade isolation is locked to a single hop; multi-hop recursive "
                "invalidation is unconstitutional",
                context={
                    "reason": "max_hops_locked_to_one",
                    "requested_max_hops": int(max_hops),
                    "max_overlay_hops": MAX_OVERLAY_HOPS,
                },
            )

        origin = origin_node_id or entity_id
        consumers = _direct_consumers(dependency_graph, origin)
        marked = tuple(sorted({consumer for consumer in consumers if consumer != origin}))

        reason = stale_reason or (
            f"retrospective_annotation:{coerced.annotation_id}:"
            f"{coerced.semantic_overlay}"
        )
        report = SingleHopInvalidationReport(
            entity_id=entity_id,
            annotation_id=coerced.annotation_id,
            origin_node_id=origin,
            marked_stale=marked,
            marked_stale_count=len(marked),
            traversal_depth_reached=MAX_OVERLAY_HOPS,
            graph_queries=1,
            nodes_visited=1 + len(marked),
            llm_recompute_triggered=0,
            second_hop_expanded=False,
            cascade_suppressed=True,
            stale_reason=reason,
            stale_at=utc_now(),
        )

        for node_id in marked:
            self._stale_reasons[node_id] = reason
            self._stale_reports[node_id] = report
        self._last_report = report
        self._isolations += 1
        # 注意：此处刻意不调用 self._recompute_hook —— 重算属于 M3-001R 的按需懒加载。
        return set(marked)

    def diagnose_suppressed_downstream(
        self,
        dependency_graph: Any,
        origin_node_id: str,
        *,
        depth: int = 2,
    ) -> tuple[str, ...]:
        """只读诊断：列出被刻意压制、绝不重算的 2 级及更远下游节点。

        与失效标记完全解耦——本方法不会把任何节点标 ``is_stale``，也不会触发任何
        重算；``depth`` 受 :data:`MAX_DIAGNOSTIC_DEPTH` 上限约束，禁止无界展开。
        """

        if depth < 2:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "diagnostics must ask for at least the second hop",
                context={"reason": "diagnostic_depth_invalid", "depth": int(depth)},
            )
        if depth > MAX_DIAGNOSTIC_DEPTH:
            raise RetrospectiveAnnotationError(
                ErrorCode.INVALID_ARGUMENT,
                "diagnostic depth is bounded to keep the audit read cheap",
                context={
                    "reason": "diagnostic_depth_unbounded",
                    "depth": int(depth),
                    "max_diagnostic_depth": MAX_DIAGNOSTIC_DEPTH,
                },
            )

        first_hop = set(_direct_consumers(dependency_graph, origin_node_id))
        suppressed: set[str] = set()
        frontier = first_hop
        for _ in range(depth - 1):
            nxt: set[str] = set()
            for node_id in frontier:
                for consumer in _direct_consumers(dependency_graph, node_id):
                    if consumer in first_hop or consumer in suppressed:
                        continue
                    nxt.add(consumer)
            suppressed |= nxt
            frontier = nxt
            if not frontier:
                break
        return tuple(sorted(suppressed))

    @property
    def blocked_cascades(self) -> int:
        """被拒绝的无界级联请求计数。"""

        return self._blocked_cascades
