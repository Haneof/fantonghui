from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import WorldObject
from .enums import (
    ActionStatus,
    AnnotationSlot,
    BudgetOnExceed,
    BudgetScope,
    ClaimType,
    DimensionLifecycle,
    EventStatus,
    GoalSourceType,
    GoalStatus,
    KnowledgeState,
    ObjectType,
    ProfileName,
    PredictionVerificationState,
    SummaryStatus,
    TaskState,
    TaskType,
    UserReaction,
    WakeSource,
    WakeState,
)
from .refs import ObjectRef
from .time import KnowledgeWindow, TemporalExtent, as_utc, require_aware, require_timezone_name


class Observation(WorldObject):
    object_type: Literal[ObjectType.OBSERVATION] = ObjectType.OBSERVATION
    source_kind: str
    modality: str
    value: Any = None
    unit: str | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)
    raw_locator: str | None = None


class Entity(WorldObject):
    object_type: Literal[ObjectType.ENTITY] = ObjectType.ENTITY
    entity_kind: str
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    identity_claim_refs: list[ObjectRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entity_identity_refs(self) -> "Entity":
        for ref in self.identity_claim_refs:
            if ref.revision is None:
                raise ValueError(
                    "identity_claim_refs requires pinned ObjectRef revisions"
                )
        return self


class Relation(WorldObject):
    object_type: Literal[ObjectType.RELATION] = ObjectType.RELATION
    left: ObjectRef
    relation_type: str
    right: ObjectRef
    valid_time: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)
    evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_relation_evidence_refs(self) -> "Relation":
        for ref in self.evidence_set_refs:
            if ref.revision is None:
                raise ValueError(
                    "evidence_set_refs requires pinned ObjectRef revisions"
                )
        return self


class DimensionDefinition(WorldObject):
    object_type: Literal[ObjectType.DIMENSION_DEFINITION] = ObjectType.DIMENSION_DEFINITION
    name: str
    description: str
    data_shape: str
    lifecycle: DimensionLifecycle = DimensionLifecycle.CANDIDATE
    update_method: str | None = None
    expected_value: str | None = None
    maintenance_policy: dict[str, Any] = Field(default_factory=dict)


class DimensionMembership(WorldObject):
    object_type: Literal[ObjectType.DIMENSION_MEMBERSHIP] = ObjectType.DIMENSION_MEMBERSHIP
    dimension_ref: ObjectRef
    member_ref: ObjectRef
    applicable_time: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)
    basis_refs: list[ObjectRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimension_membership_refs(self) -> "DimensionMembership":
        if self.dimension_ref.revision is None:
            raise ValueError("dimension_ref requires pinned ObjectRef revision")
        if self.member_ref.revision is None:
            raise ValueError("member_ref requires pinned ObjectRef revision")
        for ref in self.basis_refs:
            if ref.revision is None:
                raise ValueError("basis_refs requires pinned ObjectRef revisions")
        return self


class DimensionDerivation(WorldObject):
    object_type: Literal[ObjectType.DIMENSION_DERIVATION] = ObjectType.DIMENSION_DERIVATION
    output_dimension_ref: ObjectRef
    input_refs: list[ObjectRef] = Field(min_length=1)
    derivation_description: str
    applicable_scope: dict[str, Any] = Field(default_factory=dict)
    applicable_time: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)
    evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    counterexample_refs: list[ObjectRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimension_derivation_refs(self) -> "DimensionDerivation":
        if self.output_dimension_ref.revision is None:
            raise ValueError("output_dimension_ref requires pinned ObjectRef revision")
        for field_name in ["input_refs", "evidence_set_refs", "counterexample_refs"]:
            for ref in getattr(self, field_name):
                if ref.revision is None:
                    raise ValueError(
                        f"{field_name} requires pinned ObjectRef revisions"
                    )
        return self


class Claim(WorldObject):
    object_type: Literal[ObjectType.CLAIM] = ObjectType.CLAIM
    claimant_id: str
    claim_type: ClaimType
    content: str
    valid_time: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)
    asserted_at: datetime
    knowledge_state: KnowledgeState
    confidence: float = Field(ge=0.0, le=1.0)
    support_evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    counter_evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    unknown_items: list[str] = Field(default_factory=list)
    # R4-09.1（第 38 条追加，候选冻结）：来源信任分层——"平等"是记录权利平等，
    # 不是行动授权平等。
    source_trust: float = Field(default=1.0, ge=0.0, le=1.0)
    corroboration_required: bool = False

    @model_validator(mode="after")
    def validate_asserted_at(self) -> "Claim":
        require_aware(self.asserted_at, "asserted_at")
        return self

    @model_validator(mode="after")
    def validate_trust_governance(self) -> "Claim":
        # V31 契约层执法点：未获印证的第三方转述不得直接成为 FACT。
        if self.corroboration_required and self.claim_type is ClaimType.FACT:
            raise ValueError(
                "corroboration_required=True 的转述类内容在印证前不得升为 FACT（R4-09.1）"
            )
        return self

    @property
    def may_drive_external_action(self) -> bool:
        """C06 消费谓词（契约层给语义、执法在 M2+ 行动授权路径）。"""

        return not self.corroboration_required


class EvidenceSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector_type: str
    subject_id: str
    time_range: TemporalExtent
    dimension_refs: list[ObjectRef] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    algorithm_version: str


class EvidenceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_count: int | None = Field(default=None, ge=0)
    observed_count: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_description: list[str] = Field(default_factory=list)


class EvidenceSet(WorldObject):
    object_type: Literal[ObjectType.EVIDENCE_SET] = ObjectType.EVIDENCE_SET
    purpose: str
    knowledge_window: KnowledgeWindow
    member_refs: list[ObjectRef] = Field(default_factory=list)
    support_refs: list[ObjectRef] = Field(default_factory=list)
    counter_refs: list[ObjectRef] = Field(default_factory=list)
    context_refs: list[ObjectRef] = Field(default_factory=list)
    selector: EvidenceSelector | None = None
    selection_method: str
    aggregation_method: str | None = None
    aggregation_version: str | None = None
    coverage: EvidenceCoverage = Field(default_factory=EvidenceCoverage)
    stale: bool = False

    @model_validator(mode="after")
    def validate_evidence_content(self) -> "EvidenceSet":
        if not self.member_refs and self.selector is None:
            raise ValueError("EvidenceSet requires member_refs or selector")

        for field_name in [
            "member_refs",
            "support_refs",
            "counter_refs",
            "context_refs",
        ]:
            refs = getattr(self, field_name)
            for ref in refs:
                if ref.revision is None:
                    raise ValueError(
                        f"{field_name} requires pinned ObjectRef revisions"
                    )

        if self.selector is not None:
            for ref in self.selector.dimension_refs:
                if ref.revision is None:
                    raise ValueError(
                        "selector.dimension_refs requires pinned ObjectRef revisions"
                    )

        if as_utc(
            self.knowledge_window.knowledge_cutoff,
            "knowledge_cutoff",
        ) > as_utc(self.learned_at, "learned_at"):
            raise ValueError(
                "knowledge_window.knowledge_cutoff must not be after learned_at"
            )

        return self


class EventAnchor(WorldObject):
    object_type: Literal[ObjectType.EVENT] = ObjectType.EVENT
    title: str
    interpretation: str
    event_status: EventStatus = EventStatus.CANDIDATE
    event_time: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)
    participant_refs: list[ObjectRef] = Field(default_factory=list)
    primary_claim_refs: list[ObjectRef] = Field(default_factory=list)
    evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    support_evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    counter_evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    supersedes_refs: list[ObjectRef] = Field(default_factory=list)
    merged_into_ref: ObjectRef | None = None
    split_from_ref: ObjectRef | None = None
    split_child_refs: list[ObjectRef] = Field(default_factory=list)
    revision_reason: str | None = None

    @model_validator(mode="after")
    def validate_event_contract(self) -> "EventAnchor":
        for field_name in [
            "primary_claim_refs",
            "evidence_set_refs",
            "support_evidence_set_refs",
            "counter_evidence_set_refs",
            "supersedes_refs",
            "split_child_refs",
        ]:
            for ref in getattr(self, field_name):
                if ref.revision is None:
                    raise ValueError(
                        f"{field_name} requires pinned ObjectRef revisions"
                    )

        for field_name in ["merged_into_ref", "split_from_ref"]:
            ref = getattr(self, field_name)
            if ref is not None and ref.revision is None:
                raise ValueError(f"{field_name} requires pinned ObjectRef revision")

        if self.event_status is EventStatus.REVISED and not self.supersedes_refs:
            raise ValueError("REVISED EventAnchor requires supersedes_refs")
        if self.event_status is EventStatus.MERGED and self.merged_into_ref is None:
            raise ValueError("MERGED EventAnchor requires merged_into_ref")
        if self.event_status is EventStatus.SPLIT and not self.split_child_refs:
            raise ValueError("SPLIT EventAnchor requires split_child_refs")

        if self.event_status in {
            EventStatus.REVISED,
            EventStatus.REJECTED,
            EventStatus.MERGED,
            EventStatus.SPLIT,
        }:
            if self.revision_reason is None or not self.revision_reason.strip():
                raise ValueError(
                    f"{self.event_status.value.upper()} EventAnchor requires revision_reason"
                )

        return self


class Summary(WorldObject):
    object_type: Literal[ObjectType.SUMMARY] = ObjectType.SUMMARY
    dimension_ref: ObjectRef | None = None
    summary_time: TemporalExtent
    granularity: str
    source_world_revision: int = Field(ge=0)
    evidence_set_ref: ObjectRef | None = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    claim_refs: list[ObjectRef] = Field(default_factory=list)
    summary_status: SummaryStatus = SummaryStatus.CURRENT


class Goal(WorldObject):
    object_type: Literal[ObjectType.GOAL] = ObjectType.GOAL
    owner_id: str
    source_type: GoalSourceType
    title: str
    description: str
    goal_status: GoalStatus = GoalStatus.PROPOSED
    success_criteria: list[str] = Field(default_factory=list)
    related_dimension_refs: list[ObjectRef] = Field(default_factory=list)
    related_event_refs: list[ObjectRef] = Field(default_factory=list)
    related_task_refs: list[ObjectRef] = Field(default_factory=list)
    app_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class Dependency(WorldObject):
    object_type: Literal[ObjectType.DEPENDENCY] = ObjectType.DEPENDENCY
    dependent_ref: ObjectRef
    dependency_ref: ObjectRef
    dependency_type: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dependency_contract(self) -> "Dependency":
        if self.dependent_ref.revision is None:
            raise ValueError("dependent_ref requires pinned ObjectRef revision")
        if self.dependency_ref.revision is None:
            raise ValueError("dependency_ref requires pinned ObjectRef revision")
        if not self.dependency_type.strip():
            raise ValueError("dependency_type must not be blank")
        if self.dependent_ref.object_id == self.dependency_ref.object_id:
            raise ValueError("Dependency cannot directly depend on itself")
        return self


class Task(WorldObject):
    object_type: Literal[ObjectType.TASK] = ObjectType.TASK
    task_type: TaskType
    task_state: TaskState = TaskState.DRAFT
    goal_ref: ObjectRef | None = None
    title: str = Field(min_length=1)
    reason_refs: list[ObjectRef] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=100)
    next_wake_at: datetime | None = None
    deadline: datetime | None = None
    recurrence: dict[str, Any] | None = None
    timezone_name: str | None = None
    dependency_refs: list[ObjectRef] = Field(default_factory=list)
    next_step: str | None = None
    completion_condition: dict[str, Any] = Field(default_factory=dict)
    cancel_condition: dict[str, Any] = Field(default_factory=dict)
    related_entity_refs: list[ObjectRef] = Field(default_factory=list)
    app_id: str | None = None
    attempts: int = Field(default=0, ge=0)
    execution_refs: list[ObjectRef] = Field(default_factory=list)
    outcome_refs: list[ObjectRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_task_contract(self) -> "Task":
        require_aware(self.next_wake_at, "next_wake_at")
        require_aware(self.deadline, "deadline")
        require_timezone_name(
            self.timezone_name,
            "timezone_name",
        )
        for field_name in ["reason_refs", "execution_refs", "outcome_refs"]:
            for ref in getattr(self, field_name):
                if ref.revision is None:
                    raise ValueError(
                        f"{field_name} requires pinned ObjectRef revisions"
                    )
        return self


class Wake(WorldObject):
    object_type: Literal[ObjectType.WAKE] = ObjectType.WAKE
    wake_source: WakeSource
    wake_state: WakeState = WakeState.NEW
    rule_id: str | None = None
    first_hit_at: datetime
    last_hit_at: datetime
    hit_count: int = Field(default=1, ge=1)
    evidence_refs: list[ObjectRef] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=100)
    dedupe_key: str | None = None

    @model_validator(mode="after")
    def validate_wake_contract(self) -> "Wake":
        require_aware(self.first_hit_at, "first_hit_at")
        require_aware(self.last_hit_at, "last_hit_at")
        if as_utc(
            self.last_hit_at,
            "last_hit_at",
        ) < as_utc(
            self.first_hit_at,
            "first_hit_at",
        ):
            raise ValueError("last_hit_at must not be before first_hit_at")
        for ref in self.evidence_refs:
            if ref.revision is None:
                raise ValueError("evidence_refs requires pinned ObjectRef revisions")
        return self


class Session(WorldObject):
    object_type: Literal[ObjectType.SESSION] = ObjectType.SESSION
    wake_ref: ObjectRef | None = None
    snapshot_world_revision: int = Field(ge=0)
    operation_ids: list[str] = Field(default_factory=list)
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    session_state: str = Field(default="open", min_length=1)

    @model_validator(mode="after")
    def validate_session_contract(self) -> "Session":
        if self.wake_ref is not None and self.wake_ref.revision is None:
            raise ValueError("wake_ref requires pinned ObjectRef revision")
        return self


class Action(WorldObject):
    object_type: Literal[ObjectType.ACTION] = ObjectType.ACTION
    execution_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    action_status: ActionStatus = ActionStatus.PROPOSED
    task_ref: ObjectRef | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str | None = None

    @model_validator(mode="after")
    def validate_action_contract(self) -> "Action":
        if self.task_ref is not None and self.task_ref.revision is None:
            raise ValueError("task_ref requires pinned ObjectRef revision")
        return self


class Outcome(WorldObject):
    object_type: Literal[ObjectType.OUTCOME] = ObjectType.OUTCOME
    action_ref: ObjectRef
    outcome_state: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[ObjectRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome_contract(self) -> "Outcome":
        if self.action_ref.revision is None:
            raise ValueError("action_ref requires pinned ObjectRef revision")
        for ref in self.evidence_refs:
            if ref.revision is None:
                raise ValueError("evidence_refs requires pinned ObjectRef revisions")
        return self


class OperationExperience(WorldObject):
    object_type: Literal[ObjectType.OPERATION_EXPERIENCE] = ObjectType.OPERATION_EXPERIENCE
    problem_type: str
    method_path: list[str]
    applicability: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, float] = Field(default_factory=dict)
    result_summary: str
    misses: list[str] = Field(default_factory=list)
    positive_case_refs: list[ObjectRef] = Field(default_factory=list)
    negative_case_refs: list[ObjectRef] = Field(default_factory=list)
    experience_state: str = "candidate"


class ToolProposal(WorldObject):
    object_type: Literal[ObjectType.TOOL_PROPOSAL] = ObjectType.TOOL_PROPOSAL
    capability_gap: str
    use_cases: list[str]
    current_limitations: list[str]
    proposed_interface: dict[str, Any]
    expected_benefit: str
    validation_plan: str


# ---------------------------------------------------------------------------
# R4 修改案（M0-023~028）新增一等对象。修改案批准前为候选契约；
# 快照 gate_version 标记 "R4-delta"，批准转正式后仅改字符串、不改字段。
# ---------------------------------------------------------------------------


class Prediction(WorldObject):
    """第 50~53 条：假说-演绎闭环的一等认知对象。

    第 53 条封死"无病呻吟预测"：reasoning（立项理由）为空即拒绝写入；
    对撞状态推进到 CORROBORATED/FALSIFIED 时必须携带真实观测证据引用。
    """

    object_type: Literal[ObjectType.PREDICTION] = ObjectType.PREDICTION
    source_claim_ref: ObjectRef
    target_dimension_id: str | None = None
    expected_change: str = Field(min_length=1)
    time_window: TemporalExtent
    confidence: float = Field(ge=0.0, le=1.0)
    verification_state: PredictionVerificationState = PredictionVerificationState.PENDING
    actual_outcome_ref: ObjectRef | None = None
    reasoning: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prediction_contract(self) -> "Prediction":
        if self.source_claim_ref.revision is None:
            raise ValueError("source_claim_ref requires pinned ObjectRef revision")
        if not self.reasoning.strip():
            raise ValueError("prediction reasoning (第 53 条立项理由) must not be blank")
        if not self.expected_change.strip():
            raise ValueError("expected_change must be falsifiable, not blank")
        if (
            self.verification_state
            in {PredictionVerificationState.CORROBORATED, PredictionVerificationState.FALSIFIED}
            and self.actual_outcome_ref is None
        ):
            raise ValueError(
                "verdict states require actual_outcome_ref pointing at reality observation"
            )
        return self


class LifeChapter(WorldObject):
    """第 29 条：人生章节相变模型。

    相变判定由 AI 在唤醒会话中形成（触发器不得代判，第 77 条）；本契约只
    保证章节可追溯：基线引用、相变证据、封章理由缺一不可。
    """

    object_type: Literal[ObjectType.LIFE_CHAPTER] = ObjectType.LIFE_CHAPTER
    chapter_title: str | None = None
    baseline_refs: list[ObjectRef] = Field(default_factory=list)
    transition_evidence_set_refs: list[ObjectRef] = Field(default_factory=list)
    supersedes_chapter_id: str | None = None
    sealed_reason: str | None = None

    @model_validator(mode="after")
    def validate_sealed_chapter(self) -> "LifeChapter":
        if self.status == "sealed" and not (self.sealed_reason or "").strip():
            raise ValueError("sealed LifeChapter must carry sealed_reason (第 29 条归档封存)")
        return self


class Reinterpretation(WorldObject):
    """第 23 个一等对象（R4-01）：历史节点的回溯解释层。

    裁决要点（与第 93 条"历史不可篡改"同时成立）：
    - target_ref 必须 pinned 到精确 revision；被指向对象永不改动；
    - occurred_at/learned_at 均为标注诞生时间（T_now），valid_time 指向被
      加注区间；AS_KNOWN / ANNOTATED 双透镜由读面（M0-020 机制）解析；
    - slot 为注册制枚举（第 76 条防爆炸）；新语义需先走候选维度流程。
    """

    object_type: Literal[ObjectType.REINTERPRETATION] = ObjectType.REINTERPRETATION
    target_ref: ObjectRef
    slot: AnnotationSlot
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_set_ref: ObjectRef | None = None
    supersedes_id: str | None = None
    valid_time: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)

    @model_validator(mode="after")
    def validate_pinned_target(self) -> "Reinterpretation":
        if self.target_ref.revision is None:
            raise ValueError("target_ref requires pinned ObjectRef revision (第 18/93 条)")
        if not self.statement.strip():
            raise ValueError("reinterpretation statement must not be blank")
        return self


class CommunicationExperience(WorldObject):
    """第 12/69 条：沟通风格进化——说什么、怎么说、用户如何反应，一体记录。"""

    object_type: Literal[ObjectType.COMMUNICATION_EXPERIENCE] = ObjectType.COMMUNICATION_EXPERIENCE
    scenario: str = Field(min_length=1)
    style: str = Field(min_length=1)
    tone: str | None = None
    user_reaction: UserReaction
    action_ref: ObjectRef | None = None
    applicable_conditions: dict[str, Any] = Field(default_factory=dict)
    counterexample_refs: list[ObjectRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_pin(self) -> "CommunicationExperience":
        if self.action_ref is not None and self.action_ref.revision is None:
            raise ValueError("action_ref requires pinned ObjectRef revision")
        return self


class BudgetPolicy(WorldObject):
    """第 86 条之一（R4-08）：经济控制的预算对象。

    预算是世界对象（可版本化、可由经验经 ToolProposal 提案修订）；执法在
    C13 网关（不可协商）。至少声明一个封顶，否则不构成预算。
    """

    object_type: Literal[ObjectType.BUDGET_POLICY] = ObjectType.BUDGET_POLICY
    scope: BudgetScope
    max_model_calls: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)
    max_wakes: int | None = Field(default=None, ge=0)
    on_exceed: BudgetOnExceed = BudgetOnExceed.CHECKPOINT

    @model_validator(mode="after")
    def validate_has_cap(self) -> "BudgetPolicy":
        if self.max_model_calls is None and self.max_tokens is None and self.max_wakes is None:
            raise ValueError("budget policy must declare at least one cap")
        return self


class AssemblyPolicy(WorldObject):
    """第 84/85 条：看板组装策略版本化对象（谁组看板谁定义 AI 的世界——
    策略本身必须可读、可版本、可被经验修订，但数据源白名单由内核强制，
    经验只能改排序与裁剪参数）。
    """

    object_type: Literal[ObjectType.ASSEMBLY_POLICY] = ObjectType.ASSEMBLY_POLICY
    wake_kind: str | None = None
    section_order: list[str] = Field(min_length=1)
    section_token_caps: dict[str, int] = Field(default_factory=dict)
    max_prefill_tokens: int = Field(ge=256)
    data_source_allowlist: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sections(self) -> "AssemblyPolicy":
        if len(set(self.section_order)) != len(self.section_order):
            raise ValueError("section_order must not repeat sections")
        unknown = [k for k in self.section_token_caps if k not in set(self.section_order)]
        if unknown:
            raise ValueError(f"section_token_caps references sections outside section_order: {unknown}")
        return self


# ---------------------------------------------------------------------------
# M0-030（R4-09.3）runtime_profile 双配置契约：virtual / band_v0。
# 教义：profile 只改数字，不改代码路径——因此所有硬约束都写进同一个模型的
# validator（结构性同路径），band_v0 逐数字"不弱于 virtual 默认"。
# ---------------------------------------------------------------------------


class IngestPolicy(BaseModel):
    """C01 摄入硬约束（第 33 条）：不存大图 / 不存 50Hz 原始 / 心率平均线。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hr_compression_window_seconds: int = Field(default=7200, ge=0)
    imu_mode: Literal["macro_events_only", "raw_stream"] = "macro_events_only"
    images_mode: Literal["semantic_text_only", "thumbnail_meta"] = "semantic_text_only"
    compute_budget_us_per_ingest: int | None = None  # None=不限（virtual 可）
    image_queue_depth: int = Field(default=8, ge=1)
    frame_drop_must_record: bool = True


class LatencyPolicy(BaseModel):
    """C13 延迟预算：首字/同步召回；band_v0 附 TTS 分段硬线。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    first_token_budget_ms: int = Field(default=1000, ge=1)
    recall_sync_budget_ms: int = Field(default=50, ge=1)
    transport: Literal["mock_fixed_rtt", "real"] = "mock_fixed_rtt"
    tts_max_sec_per_turn: int | None = None
    tts_force_split_on_exceed: bool = True


class StoragePolicy(BaseModel):
    """C02 存储速率上限 + 33.5 归档硬线（tombstone 开关不是配置项）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_tier_days: int = Field(default=30, ge=1)
    pruned_tombstone: bool = True
    band_local_only: bool = False
    ring_buffer_hours: int | None = None
    max_commits_per_hour: int | None = None


class RuntimeProfile(BaseModel):
    """双 Profile 契约（设计书 §2.4）。不是世界对象——是配置，不进 registry。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ProfileName
    ingest: IngestPolicy = Field(default_factory=IngestPolicy)
    latency: LatencyPolicy = Field(default_factory=LatencyPolicy)
    storage: StoragePolicy = Field(default_factory=StoragePolicy)

    @model_validator(mode="after")
    def validate_profile_rules(self) -> "RuntimeProfile":
        # 宪法硬线，与 profile 无关（两个名字都必须成立）：
        if not self.storage.pruned_tombstone:
            raise ValueError("pruned_tombstone=false 被第 33.5 条拒绝：tombstone 不可配置关闭")
        if self.ingest.imu_mode != "macro_events_only":
            raise ValueError("raw_stream IMU 被第 33 条摄入硬约束拒绝（两 profile 同判）")
        if self.ingest.images_mode != "semantic_text_only":
            raise ValueError("存大图/缩略图元数据被第 33 条摄入硬约束拒绝（两 profile 同判）")
        if self.ingest.frame_drop_must_record is not True:
            raise ValueError("丢帧必须写 Observation（数据覆盖异常）是路径不是数字，禁关")
        if self.name is ProfileName.BAND_V0:
            v = DEFAULT_VIRTUAL
            if self.ingest.compute_budget_us_per_ingest is None:
                raise ValueError("band_v0 必须声明每摄入算力预算（us）")
            if self.ingest.image_queue_depth > 3:
                raise ValueError("band_v0 图像队列深度上限 3")
            if self.storage.ring_buffer_hours is None or self.storage.ring_buffer_hours > 48:
                raise ValueError("band_v0 必须声明 ring_buffer_hours ≤ 48")
            if not self.storage.band_local_only:
                raise ValueError("band_v0 端侧语义文本+波形包络为 band_local_only 前提")
            if self.storage.max_commits_per_hour is None or self.storage.max_commits_per_hour > 200_000:
                raise ValueError("band_v0 必须声明存储速率上限（≤200k 修订/小时）")
            if self.latency.tts_max_sec_per_turn is None or self.latency.tts_max_sec_per_turn > 20:
                raise ValueError("band_v0 TTS ≤20s/轮且超限强制分段")
            if not self.latency.tts_force_split_on_exceed:
                raise ValueError("band_v0 tts_force_split_on_exceed 必须为真")
            # "同款 + 更严"：逐数字不得弱于 virtual 默认。
            pairs = (
                ("hr_compression_window_seconds", self.ingest, v.ingest),
                ("compute_budget_us_per_ingest", self.ingest, v.ingest, True),
                ("image_queue_depth", self.ingest, v.ingest),
                ("first_token_budget_ms", self.latency, v.latency),
                ("recall_sync_budget_ms", self.latency, v.latency),
                ("tts_max_sec_per_turn", self.latency, v.latency, True),
                ("raw_tier_days", self.storage, v.storage),
                ("ring_buffer_hours", self.storage, v.storage, True),
                ("max_commits_per_hour", self.storage, v.storage, True),
            )
            for item in pairs:
                field, a, b = item[0], item[1], item[2]
                none_ok_lenient = len(item) > 3  # None 视为更严的场景不在此列
                if getattr(a, field) is None:
                    if not none_ok_lenient:
                        raise ValueError(f"band_v0.{field} 不得为 None")
                    continue
                if getattr(b, field) is None:
                    continue
                if getattr(a, field) > getattr(b, field):
                    raise ValueError(
                        f"band_v0 只可更严：{field}={getattr(a, field)} > virtual 默认 {getattr(b, field)}"
                    )
        return self


DEFAULT_VIRTUAL = RuntimeProfile(name=ProfileName.VIRTUAL)
DEFAULT_BAND_V0 = RuntimeProfile(
    name=ProfileName.BAND_V0,
    ingest=IngestPolicy(
        hr_compression_window_seconds=3600,
        compute_budget_us_per_ingest=800,
        image_queue_depth=3,
    ),
    latency=LatencyPolicy(first_token_budget_ms=1000, recall_sync_budget_ms=50,
                          tts_max_sec_per_turn=20),
    storage=StoragePolicy(raw_tier_days=30, band_local_only=True,
                          ring_buffer_hours=48, max_commits_per_hour=100_000),
)


def resolve_runtime_profile(name: str) -> RuntimeProfile:
    try:
        parsed = ProfileName(name)
    except ValueError as exc:
        raise ValueError(f"未知 runtime_profile：{name!r}（合法值：virtual / band_v0）") from exc
    return DEFAULT_BAND_V0 if parsed is ProfileName.BAND_V0 else DEFAULT_VIRTUAL
