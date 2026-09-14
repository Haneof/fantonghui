from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import WorldObject
from .enums import (
    ActionStatus,
    ClaimType,
    DimensionLifecycle,
    EventStatus,
    GoalSourceType,
    GoalStatus,
    KnowledgeState,
    ObjectType,
    SummaryStatus,
    TaskState,
    TaskType,
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

    @model_validator(mode="after")
    def validate_asserted_at(self) -> "Claim":
        require_aware(self.asserted_at, "asserted_at")
        return self


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
    dependency_type: str


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
