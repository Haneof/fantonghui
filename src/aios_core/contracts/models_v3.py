"""V3.0.1 extension world-object contracts (freeze-line: CONST-V3.0.1 / M0').

Every class here is added by the M0' contract patch (issues M0-024..M0-031).
Nothing in this file mutates the R2 frozen surface (models.py); the R2 gate
snapshot stays green while this module is captured by the parallel V3.0.1
snapshot (schemas/v3p1/m0p_contract_snapshot.json).

Design rules honoured here, codified in the ADJ set:
- ADJ-004: two-stage tombstone, revocation-free manifest, LLM owns no irreversible delete.
- ADJ-005: retrospective correction is append-only annotation; physical history unreadable.
- ADJ-009: speaker clusters retire (never resurrect) with continuity probes.
- R4 §3.4: bounded trigger AST, bounded invalidation epoch, budget lanes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import WorldObject
from .enums_v3 import (
    BudgetLane,
    DepEdgeType,
    EpochState,
    ExtractionStatus,
    InteractionChannel,
    JobState,
    LifeChapterStatus,
    ManifestLane,
    ObjectTypeV3,
    OutcomeDelivery,
    PredictionStatus,
    ProvenanceClass,
    RetentionClass,
    SafetyVerdict,
    SpeakerClusterStatus,
    TombstoneStage,
    TriggerOp,
    TriState,
    TrustLane,
    VerbosityLevel,
)
from .refs import ObjectRef
from .time import TemporalExtent, as_utc, require_aware

_MAX_AST_NODES = 64
_MAX_AST_DEPTH = 8


# ---------------------------------------------------------------------------
# M0-024 · Prediction 一等认知对象（第 50~53 条）
# ---------------------------------------------------------------------------


class PredictionCheckWindow(BaseModel):
    """Prediction 的核验窗口：窗口内到期而无观测 → INCONCLUSIVE，绝不自动 FALSIFIED。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opens_at: datetime
    closes_at: datetime

    @model_validator(mode="after")
    def _ordered(self) -> "PredictionCheckWindow":
        require_aware(self.opens_at, "opens_at")
        require_aware(self.closes_at, "closes_at")
        if as_utc(self.closes_at, "closes_at") <= as_utc(self.opens_at, "opens_at"):
            raise ValueError("check window closes_at must be after opens_at")
        return self


class Prediction(WorldObject):
    """第 50 条：Prediction 是一等认知对象（独立于 inline ClaimType.PREDICTION）。

    生命周期：PENDING → {SUPPORTED, FALSIFIED, INCONCLUSIVE, EXPIRED}（终态见
    services/state_machines_v3。EXPIRED 仅用于"核验计划本身被撤销"，与"到期缺测"
    INCONCLUSIVE 严格区分——缺测绝不判证伪）。
    """

    object_type: Literal[ObjectTypeV3.PREDICTION] = ObjectTypeV3.PREDICTION

    claim_ref: ObjectRef  # 被证伪对象（pinned revision）
    prediction_status: PredictionStatus = PredictionStatus.PENDING
    check_window: PredictionCheckWindow
    evaluator_version: str = Field(min_length=1)
    intervention_possible: bool = False  # AI 自身行为可能改变结果 → 自我实现检测锚
    outcome_refs: list[ObjectRef] = Field(default_factory=list)
    provenance_class: ProvenanceClass = ProvenanceClass.INFERENCE
    calibration_domain: str = Field(default="general", min_length=1)

    @model_validator(mode="after")
    def _pinned_and_terminal(self) -> "Prediction":
        if self.claim_ref.revision is None:
            raise ValueError("claim_ref must pin a revision")
        terminal = {
            PredictionStatus.SUPPORTED,
            PredictionStatus.FALSIFIED,
            PredictionStatus.INCONCLUSIVE,
            PredictionStatus.EXPIRED,
        }
        if self.prediction_status in terminal and not self.outcome_refs:
            raise ValueError(
                "terminal prediction status requires at least one outcome_ref "
                "(no outcome may only remain PENDING)"
            )
        return self


# ---------------------------------------------------------------------------
# M0-025 · LifeChapter（第 29 条）
# ---------------------------------------------------------------------------


class LifeChapter(WorldObject):
    """第 29 条：人生章节相变。

    CANDIDATE 必须横跨多个关键维度（≥2 change-point 维度引用）；确认 ACTIVE 需要
    持续性 + 反证 + 迟滞证据；旧章节归档 ARCHIVED 而非删除；误判 REVISED 链接修正版，
    旧版本完整封存。
    """

    object_type: Literal[ObjectTypeV3.LIFE_CHAPTER] = ObjectTypeV3.LIFE_CHAPTER

    chapter_status: LifeChapterStatus = LifeChapterStatus.CANDIDATE
    label: str = Field(min_length=1)
    change_point_dimension_refs: list[ObjectRef] = Field(min_length=2)
    persistence_evidence_refs: list[ObjectRef] = Field(default_factory=list)
    counter_evidence_refs: list[ObjectRef] = Field(default_factory=list)
    baseline_parameter_version: str | None = None  # 旧基线参数版本化归档（ADJ/M0-031）
    prior_chapter_ref: ObjectRef | None = None
    migration_reason: str | None = None

    @model_validator(mode="after")
    def _chapter_rules(self) -> "LifeChapter":
        for ref in self.change_point_dimension_refs:
            if ref.revision is None:
                raise ValueError("change_point_dimension_refs must pin revisions")
        if self.chapter_status in {
            LifeChapterStatus.ACTIVE,
            LifeChapterStatus.ARCHIVED,
        } and not self.persistence_evidence_refs:
            raise ValueError(
                "ACTIVE/ARCHIVED chapter requires persistence_evidence_refs "
                "(a single signal can never directly confirm a chapter)"
            )
        if self.prior_chapter_ref is not None and self.prior_chapter_ref.revision is None:
            raise ValueError("prior_chapter_ref must pin a revision")
        return self


# ---------------------------------------------------------------------------
# M0-026 · CommunicationExperience（第 69 条）
# ---------------------------------------------------------------------------


class CommunicationExperience(WorldObject):
    """第 69 条：AI 沟通经验（v3.0 新增）。

    事实阈值单调性（R4 M5 终审裁决）：经验只改变表达的通道/时机/语气成本，
    绝不改变任何事实判定阈值；本契约用不可用字段的方式立宪——经验体上根本没有
    fact_threshold 这类字段可写。
    """

    object_type: Literal[ObjectTypeV3.COMMUNICATION_EXPERIENCE] = (
        ObjectTypeV3.COMMUNICATION_EXPERIENCE
    )

    pattern: str = Field(min_length=1)  # 经验的行为化描述
    applicable_scope: dict[str, Any] = Field(default_factory=dict)
    derived_from_refs: list[ObjectRef] = Field(min_length=1)  # Action/Outcome/Receipt
    counter_example_refs: list[ObjectRef] = Field(default_factory=list)
    avoids_sycophancy: bool = True  # 注册断言：本经验不以讨好换接受率
    expiry: datetime | None = None

    @model_validator(mode="after")
    def _exp_rules(self) -> "CommunicationExperience":
        if not self.avoids_sycophancy:
            raise ValueError(
                "communication experience that does not assert avoids_sycophancy "
                "is not registrable (fact thresholds are invariant)"
            )
        for ref in self.derived_from_refs:
            if ref.revision is None:
                raise ValueError("derived_from_refs must pin revisions")
        if self.expiry is not None:
            require_aware(self.expiry, "expiry")
            if as_utc(self.expiry, "expiry") <= as_utc(self.learned_at, "learned_at"):
                raise ValueError("expiry must be after learned_at")
        return self


# ---------------------------------------------------------------------------
# M0-026 附 · RetrospectiveAnnotation（ADJ-005 唯一合法回溯修正形式）
# ---------------------------------------------------------------------------


class RetrospectiveAnnotation(WorldObject):
    """第 31 条之一的唯一合法实现：在当前时刻追加的有效期指向过去的标注。

    被标注的物理 Observation 永不改写；本对象只携带 refs + 注解体。
    """

    object_type: Literal[ObjectTypeV3.RETROSPECTIVE_ANNOTATION] = (
        ObjectTypeV3.RETROSPECTIVE_ANNOTATION
    )

    anchor_ref: ObjectRef  # 被标注对象（pinned revision）
    valid_time: TemporalExtent  # 注解在过去有效的区间（occurred 语义）
    payload: dict[str, Any] = Field(default_factory=dict)  # 注解体（情绪/解释/标签）
    evidence_refs: list[ObjectRef] = Field(min_length=1)

    @model_validator(mode="after")
    def _annotation_rules(self) -> "RetrospectiveAnnotation":
        if self.anchor_ref.revision is None:
            raise ValueError("anchor_ref must pin a revision")
        for ref in self.evidence_refs:
            if ref.revision is None:
                raise ValueError("evidence_refs must pin revisions")
        end = self.valid_time.end
        if end is not None and as_utc(end, "valid_time.end") > as_utc(
            self.learned_at, "learned_at"
        ):
            raise ValueError(
                "valid_time.end must not exceed learned_at (annotations may "
                "only reach backwards in time, never into the future)"
            )
        return self


# ---------------------------------------------------------------------------
# M0-027 · TriggerExpression 与条件资格（第 61/86 条 / R4 §3.4-I1）
# ---------------------------------------------------------------------------

_MAX_MAX_WAIT = timedelta(days=400)


class RelativeTimeSpec(BaseModel):
    """相对时间规格：从锚事件起算的偏移（配合 TimeReached）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor: Literal["event", "created_at", "enqueued_at"]
    offset_seconds: int = Field(ge=0)


class TimeReached(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    at: datetime
    tz_policy: Literal["absolute_utc", "follow_subject", "fixed_zone"] = "absolute_utc"
    relative: RelativeTimeSpec | None = None


class EventMatched(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_type: str = Field(min_length=1)  # R2 ObjectType 或 V3 ObjectTypeV3 的字符串值
    match: dict[str, Any] = Field(default_factory=dict)
    window_seconds: int | None = Field(default=None, ge=1)


class MechanicalPredicate(BaseModel):
    """机械（确定性）子树——永不调用模型（R4 I1 零 LLM 承诺的载体）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "obs_threshold",
        "state_change",
        "duration_over",
        "slope",
        "no_update",
        "keyword_entity",
        "data_gap",
    ]
    params: dict[str, Any] = Field(default_factory=dict)
    since_seconds: int | None = Field(default=None, ge=1)


class SemanticPredicate(BaseModel):
    """语义子树——只产生有预算的语义复核 Wake，绝不进入 tick 热路径。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["sentiment_match", "context_fit", "person_available"]
    prompt_signature: str = Field(min_length=1)
    budget_lane: Literal["review"] = "review"
    safe_default: TriState = (
        TriState.UNKNOWN
    )  # 缺预算/超时兜底；安全相关在装配处固化为 TRUE-出声


class DependencyReady(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    refs: list[ObjectRef] = Field(min_length=1)  # 全部 COMPLETED 才算就绪


class TriggerExpression(BaseModel):
    """条件 AST。有界：node_count ≤ 64、depth ≤ 8、禁止任意代码、机械/语义显式分轨。"""

    model_config = ConfigDict(extra="forbid")

    op: TriggerOp
    leaf: (
        TimeReached
        | EventMatched
        | MechanicalPredicate
        | SemanticPredicate
        | DependencyReady
        | None
    ) = None
    children: list["TriggerExpression"] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def _bounded(self) -> "TriggerExpression":
        if self.op is TriggerOp.ATOM:
            if self.leaf is None or self.children:
                raise ValueError("ATOM requires exactly one leaf and no children")
        else:
            if self.leaf is not None or not self.children:
                raise ValueError("composite nodes require children and no leaf")
            if self.op is TriggerOp.NOT and len(self.children) != 1:
                raise ValueError("NOT requires exactly one child")
        if self.node_count() > _MAX_AST_NODES:
            raise ValueError(f"trigger AST exceeds node cap {_MAX_AST_NODES}")
        if self.depth() > _MAX_AST_DEPTH:
            raise ValueError(f"trigger AST exceeds depth cap {_MAX_AST_DEPTH}")
        if not (self.has_mechanical() or self.has_semantic() or self.has_temporal()):
            raise ValueError("expression must contain at least one temporal/semantic/mechanical atom")
        return self

    def node_count(self) -> int:
        return 1 + sum(c.node_count() for c in self.children)

    def depth(self) -> int:
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)

    def has_semantic(self) -> bool:
        if isinstance(self.leaf, SemanticPredicate):
            return True
        return any(c.has_semantic() for c in self.children)

    def has_mechanical(self) -> bool:
        if isinstance(self.leaf, (MechanicalPredicate, EventMatched, DependencyReady)):
            return True
        return any(c.has_mechanical() for c in self.children)

    def has_temporal(self) -> bool:
        if isinstance(self.leaf, TimeReached):
            return True
        return any(c.has_temporal() for c in self.children)


class TriggerExpressionObject(WorldObject):
    """触发表达式作为一等冻结对象（任务引用其 pinned revision）。"""

    object_type: Literal[ObjectTypeV3.TRIGGER_EXPRESSION] = (
        ObjectTypeV3.TRIGGER_EXPRESSION
    )

    ast: TriggerExpression
    subscription_keys: list[dict[str, Any]] = Field(
        default_factory=list
    )  # 物化订阅键（key_kind/key_value/due_at，由资格引擎生成并冻结）
    superseded_by: ObjectRef | None = None

    @model_validator(mode="after")
    def _expr_rules(self) -> "TriggerExpressionObject":
        if self.superseded_by is not None and self.superseded_by.revision is None:
            raise ValueError("superseded_by must pin a revision")
        return self


# ---------------------------------------------------------------------------
# M0-028 · Conversation Stream / 流式萃取（第 85 条 / R4 §3.4-I3）
# ---------------------------------------------------------------------------


class ConversationTurn(WorldObject):
    """对话轮次的一等载体（乱序/重复幂等由 (conv_id, seq) 唯一性在存储层保证）。"""

    object_type: Literal[ObjectTypeV3.CONVERSATION_TURN] = (
        ObjectTypeV3.CONVERSATION_TURN
    )

    conv_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    speaker: Literal["user", "ai", "system", "simulator"]
    utterance: str = Field(min_length=1)
    finalized_at: datetime
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    skip_reason: str | None = None  # SKIPPED 必填原因（模型无权决定 skip）

    @model_validator(mode="after")
    def _turn_rules(self) -> "ConversationTurn":
        require_aware(self.finalized_at, "finalized_at")
        if as_utc(self.finalized_at, "finalized_at") < as_utc(
            self.learned_at, "learned_at"
        ) and self.speaker == "ai":
            raise ValueError("ai turn finalized_at before learned_at is not reconstructible")
        if self.extraction_status is ExtractionStatus.SKIPPED and not (
            self.skip_reason and self.skip_reason.strip()
        ):
            raise ValueError("SKIPPED turns require a non-empty skip_reason")
        if self.extraction_status is not ExtractionStatus.SKIPPED and self.skip_reason:
            raise ValueError("skip_reason is only meaningful for SKIPPED turns")
        return self


class ExtractionJob(WorldObject):
    """萃取任务：幂等唯一键（span 范围 + extractor_ver）由存储层强制执行。"""

    object_type: Literal[ObjectTypeV3.EXTRACTION_JOB] = ObjectTypeV3.EXTRACTION_JOB

    span_start_ref: ObjectRef
    span_end_ref: ObjectRef
    extractor_ver: str = Field(min_length=1)  # pipeline+词典+prompt 版本三元组
    idempotency_fp: str = Field(min_length=32)
    job_state: JobState = JobState.QUEUED
    attempts: int = Field(default=0, ge=0)
    deadline: datetime

    @model_validator(mode="after")
    def _job_rules(self) -> "ExtractionJob":
        for name, ref in (("span_start_ref", self.span_start_ref), ("span_end_ref", self.span_end_ref)):
            if ref.revision is None:
                raise ValueError(f"{name} must pin a revision")
        require_aware(self.deadline, "deadline")
        if self.job_state is JobState.DEAD_LETTER and self.attempts < 1:
            raise ValueError("DEAD_LETTER requires at least one attempt")
        return self


class WatermarkState(BaseModel):
    """萃取水位（水位即承诺：以后的原文永远可回读）。运营行，非一等对象。"""

    model_config = ConfigDict(extra="forbid")

    lane: str = Field(min_length=1)
    last_committed_turn_ref: ObjectRef | None = None
    world_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def _wm_rules(self) -> "WatermarkState":
        if self.last_committed_turn_ref is not None and (
            self.last_committed_turn_ref.revision is None
        ):
            raise ValueError("last_committed_turn_ref must pin a revision")
        return self


# ---------------------------------------------------------------------------
# M0-029 · CockpitManifest / ContextSnapshot（第 84 条 / R4 §3.4-I2）
# ---------------------------------------------------------------------------


class SlotRef(BaseModel):
    """Manifest 槽位：每个被引用的切片都标明来源、新鲜度、token 成本、入选理由。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: ObjectRef
    source: Literal["l0_slice", "l1_recall", "l2_deferred"]
    freshness_at: datetime
    token_cost: int = Field(ge=0)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _slot_rules(self) -> "SlotRef":
        if self.ref.revision is None and self.source != "l2_deferred":
            raise ValueError("SlotRef must pin a revision unless deferred")
        require_aware(self.freshness_at, "freshness_at")
        return self


class OmissionDetail(BaseModel):
    """被预算裁掉的内容必须显式可见——防静默失忆（R4 I2 omissions 铁律）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["l0_slice", "l1_recall", "l2_deferred"]
    reason: str = Field(min_length=1)
    projected_token_cost: int = Field(ge=0)


class FourStepsSections(BaseModel):
    """ADJ-001：四步序 = 段落排版顺序，非调用顺序。"""

    model_config = ConfigDict(extra="forbid")

    step1_self: list[SlotRef] = Field(default_factory=list)
    step2_rapport: list[SlotRef] = Field(default_factory=list)
    step3_stance: list[SlotRef] = Field(default_factory=list)
    step4_world: list[SlotRef] = Field(default_factory=list)


class SafetyGateVerdict(BaseModel):
    """ADJ-001 Step-0 机械闸的物化结论（零模型调用产生）。"""

    model_config = ConfigDict(extra="forbid")

    verdict: SafetyVerdict
    hard_safe_ok: bool
    convenience: Literal["OK", "QUIET", "HARD_BLOCK"]
    overrides: list[str] = Field(default_factory=list)  # 审计关键：每个放行原因都必须落字


class FactorSeed(BaseModel):
    """FactorLog 种子：装配器本批决策因子的结构化记录（隐藏思维链的合规替代）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: Any = None
    source: str = Field(min_length=1)
    weight_role: str = Field(min_length=1)


class ManifestInstance(WorldObject):
    """装配产物 = 模型输入 = 可回放的物化证据（R4 §3.4-I2 核心承诺）。

    第 86.4 条 7 向归因的物理前提：没有物化的看板，归因是无源之水。
    """

    object_type: Literal[ObjectTypeV3.MANIFEST_INSTANCE] = (
        ObjectTypeV3.MANIFEST_INSTANCE
    )

    manifest_version: Literal[1] = 1
    lane: ManifestLane
    token_budget: int = Field(gt=0)
    token_used: int = Field(ge=0)
    step0_safety: SafetyGateVerdict
    sections: FourStepsSections = Field(default_factory=FourStepsSections)
    ready_task_refs: list[ObjectRef] = Field(default_factory=list)
    conversation_watermark: WatermarkState | None = None
    extraction_watermark: WatermarkState | None = None
    omissions: list[OmissionDetail] = Field(default_factory=list)
    partial: bool = False
    factor_seed: list[FactorSeed] = Field(default_factory=list)
    snapshot_world_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def _manifest_rules(self) -> "ManifestInstance":
        if self.token_used > self.token_budget:
            raise ValueError(
                f"token_used {self.token_used} exceeds token_budget {self.token_budget}"
            )
        if self.partial and not self.omissions:
            raise ValueError("partial manifests must enumerate omissions")
        for ref in self.ready_task_refs:
            if ref.revision is None:
                raise ValueError("ready_task_refs must pin revisions")
        return self


# ---------------------------------------------------------------------------
# M0-030 · 信任分级 / 保留 / 墓碑（ADJ-004）
# ---------------------------------------------------------------------------


class SourceEnvelopeV3(BaseModel):
    """SourceEnvelope 的 V3 显式契约：来源信任道 + 变形谱系 + 保留类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    collector: str = Field(min_length=1)
    firmware_version: str | None = None
    transform_lineage: list[dict[str, Any]] = Field(default_factory=list)
    trust_lane: TrustLane = TrustLane.DATA
    retention_class: RetentionClass = RetentionClass.REVOCABLE_RAW
    legal_hold: bool = False


class RetentionTombstone(WorldObject):
    """两阶段删除的终身墓碑：任何 canonical ID 的历史引用都必须解析到这里。"""

    object_type: Literal[ObjectTypeV3.RETENTION_TOMBSTONE] = (
        ObjectTypeV3.RETENTION_TOMBSTONE
    )

    target_ref: ObjectRef  # 被删除物（canonical id + 最后 revision）
    tombstone_stage: TombstoneStage = TombstoneStage.STAGE1_SOFT
    source_key_hash: str = Field(min_length=32)  # 供审计复查的来源键哈希
    tombstoned_at: datetime
    deletion_log_ref: ObjectRef | None = None  # 物理粉碎完成后回指 DeletionLog

    @model_validator(mode="after")
    def _tb_rules(self) -> "RetentionTombstone":
        if self.target_ref.revision is None:
            raise ValueError("target_ref must pin a revision")
        require_aware(self.tombstoned_at, "tombstoned_at")
        if self.tombstone_stage is TombstoneStage.STAGE2_SHREDDED and (
            self.deletion_log_ref is None
        ):
            raise ValueError("STAGE2_SHREDDED requires a deletion_log_ref")
        if self.deletion_log_ref is not None and self.deletion_log_ref.revision is None:
            raise ValueError("deletion_log_ref must pin a revision")
        return self


class DeletionLog(WorldObject):
    """物理删除登记（ADJ-004.3：每次粉碎必登记，与 tombstone 终身对账）。"""

    object_type: Literal[ObjectTypeV3.DELETION_LOG] = ObjectTypeV3.DELETION_LOG

    deleted_ref: ObjectRef
    reason: str = Field(min_length=1)
    authorized_by: str = Field(min_length=1)  # 保留 Worker 身份（LLM 无权直接填自身）
    mechanical_check_passed: bool
    legal_hold_at_time: bool = False

    @model_validator(mode="after")
    def _dl_rules(self) -> "DeletionLog":
        if self.deleted_ref.revision is None:
            raise ValueError("deleted_ref must pin a revision")
        if not self.mechanical_check_passed:
            raise ValueError(
                "DeletionLog requires mechanical_check_passed=True "
                "(reference lock, retention class, legal hold all cleared)"
            )
        if self.legal_hold_at_time:
            raise ValueError("deletion under legal hold is unconstitutional")
        return self


# ---------------------------------------------------------------------------
# M0-031 · BudgetLedger / InvalidationEpoch / SpeakerCluster
# ---------------------------------------------------------------------------


class BudgetLedgerEntry(WorldObject):
    """每车道日预算池的一条进出账；每帮助单位 token 能够从这里反算。"""

    object_type: Literal[ObjectTypeV3.BUDGET_LEDGER_ENTRY] = (
        ObjectTypeV3.BUDGET_LEDGER_ENTRY
    )

    lane: BudgetLane
    period_start: datetime
    budget: int = Field(ge=0)
    used: int = Field(ge=0)
    unit: Literal["token_in", "llm_call", "bytes", "maint_ms"] = "token_in"

    @model_validator(mode="after")
    def _ledger_rules(self) -> "BudgetLedgerEntry":
        require_aware(self.period_start, "period_start")
        if self.used > self.budget:
            raise ValueError("ledger entry used exceeds budget")
        return self


class EpochBudget(BaseModel):
    """传播预算：标记阶段 LLM 调用数恒为 0（R4 §3.4-I4 零 LLM 承诺）。"""

    model_config = ConfigDict(extra="forbid")

    eval_units: int = Field(default=200, ge=1, le=2000)
    frontier_cap: int = Field(default=512, ge=1, le=4096)
    llm_calls: int = Field(default=0, ge=0)
    supernode_fanout_threshold: int = Field(default=1000, ge=1)

    @model_validator(mode="after")
    def _budget_rules(self) -> "EpochBudget":
        if self.llm_calls != 0:
            # 这条不是写死的宪法常量，而是 R4 出厂值；若调整需在治理参数账本留痕。
            raise ValueError(
                "EpochBudget.llm_calls must stay 0 in the marking phase; "
                "semantic review consumes the review lane pool, never this field"
            )
        return self


class ReviewTaskUnit(BaseModel):
    """语义复核单元（Phase-2 复核池的工作单位）。"""

    model_config = ConfigDict(extra="forbid")

    dependent_ref: ObjectRef
    prior_revision: int = Field(ge=1)
    priority_class: Literal["safety", "factual", "style"] = "factual"
    retryable: bool = True

    @model_validator(mode="after")
    def _rt_rules(self) -> "ReviewTaskUnit":
        if self.dependent_ref.revision is None:
            raise ValueError("dependent_ref must pin a revision")
        return self


class InvalidationEpoch(WorldObject):
    """第 93 条的执行体：一次失效传播 = 一个不可变代际。"""

    object_type: Literal[ObjectTypeV3.INVALIDATION_EPOCH] = (
        ObjectTypeV3.INVALIDATION_EPOCH
    )

    root_ref: ObjectRef
    root_new_revision: int = Field(ge=1)
    cause: dict[str, Any] = Field(default_factory=dict)
    budget: EpochBudget = Field(default_factory=EpochBudget)
    epoch_state: EpochState = EpochState.DRAFT
    review_units: list[ReviewTaskUnit] = Field(default_factory=list, max_length=2000)
    quarantined_refs: list[ObjectRef] = Field(default_factory=list)
    continuation_after_ref: ObjectRef | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    edge_types_considered: list[DepEdgeType] = Field(
        default_factory=lambda: list(DepEdgeType)
    )

    @model_validator(mode="after")
    def _epoch_rules(self) -> "InvalidationEpoch":
        if self.root_ref.revision is None:
            raise ValueError("root_ref must pin a revision")
        for ref in self.quarantined_refs:
            if ref.revision is None:
                raise ValueError("quarantined_refs must pin revisions")
        if self.continuation_after_ref is not None and (
            self.continuation_after_ref.revision is None
        ):
            raise ValueError("continuation_after_ref must pin a revision")
        return self


class SpeakerCluster(WorldObject):
    """声纹簇（ADJ-009）：退休不等于删除；退休/墓碑态不可逆回归。"""

    object_type: Literal[ObjectTypeV3.SPEAKER_CLUSTER] = ObjectTypeV3.SPEAKER_CLUSTER

    cluster_status: SpeakerClusterStatus = SpeakerClusterStatus.ACTIVE
    feature_locator: str | None = None  # 特征向量存储引用（吊销权外清单）
    first_heard_at: datetime
    last_heard_at: datetime
    retired_after: datetime | None = None  # 退休计划点
    reidentification_probe: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _cluster_rules(self) -> "SpeakerCluster":
        require_aware(self.first_heard_at, "first_heard_at")
        require_aware(self.last_heard_at, "last_heard_at")
        if as_utc(self.last_heard_at, "last_heard_at") < as_utc(
            self.first_heard_at, "first_heard_at"
        ):
            raise ValueError("last_heard_at must not precede first_heard_at")
        if self.retired_after is not None:
            require_aware(self.retired_after, "retired_after")
        return self


# ---------------------------------------------------------------------------
# M0-023 附 · NotificationReceipt（第 97 条投放回执 / C16 通道契约）
# ---------------------------------------------------------------------------


class NotificationReceipt(WorldObject):
    """投放回执：delivered/seen/ignored/unknown/refused 分型——无回应≠拒绝。"""

    object_type: Literal[ObjectTypeV3.NOTIFICATION_RECEIPT] = (
        ObjectTypeV3.NOTIFICATION_RECEIPT
    )

    notification_epoch_ref: ObjectRef  # 通知 epoch（播放类通道的因果前提）
    channel: InteractionChannel
    delivery: OutcomeDelivery = OutcomeDelivery.UNKNOWN
    verbosity: VerbosityLevel = VerbosityLevel.CONCISE
    expand_requested: bool = False  # 用户请求展开（ADJ-007.3 例外信号）
    action_ref: ObjectRef | None = None

    @model_validator(mode="after")
    def _receipt_rules(self) -> "NotificationReceipt":
        if self.notification_epoch_ref.revision is None:
            raise ValueError("notification_epoch_ref must pin a revision")
        if self.channel in {
            InteractionChannel.PRIVATE_AUDIO,
            InteractionChannel.SPEAKER,
        } and self.notification_epoch_ref is None:
            raise ValueError(
                "spoken channels require a notification epoch "
                "(false_playback_without_epoch=0)"
            )
        if self.action_ref is not None and self.action_ref.revision is None:
            raise ValueError("action_ref must pin a revision")
        return self


TriggerExpression.model_rebuild()
