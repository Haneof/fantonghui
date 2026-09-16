from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .base import WorldObject
from .enums import ObjectType
from .models import (
    Action,
    AssemblyPolicy,
    BudgetPolicy,
    Claim,
    CommunicationExperience,
    Dependency,
    DimensionDefinition,
    DimensionDerivation,
    DimensionMembership,
    Entity,
    EventAnchor,
    EvidenceSet,
    Goal,
    LifeChapter,
    NarrativeSegment,
    Observation,
    OperationExperience,
    Outcome,
    Prediction,
    Reinterpretation,
    Relation,
    Session,
    Summary,
    Task,
    ToolProposal,
    Wake,
    DimensionCurvePoint,
)

CANONICAL_WORLD_OBJECT_MODELS: Mapping[ObjectType, type[WorldObject]] = MappingProxyType({
    ObjectType.OBSERVATION: Observation,
    ObjectType.ENTITY: Entity,
    ObjectType.RELATION: Relation,
    ObjectType.DIMENSION_DEFINITION: DimensionDefinition,
    ObjectType.DIMENSION_MEMBERSHIP: DimensionMembership,
    ObjectType.DIMENSION_DERIVATION: DimensionDerivation,
    ObjectType.CLAIM: Claim,
    ObjectType.EVIDENCE_SET: EvidenceSet,
    ObjectType.EVENT: EventAnchor,
    ObjectType.SUMMARY: Summary,
    ObjectType.GOAL: Goal,
    ObjectType.DEPENDENCY: Dependency,
    ObjectType.TASK: Task,
    ObjectType.WAKE: Wake,
    ObjectType.SESSION: Session,
    ObjectType.ACTION: Action,
    ObjectType.OUTCOME: Outcome,
    ObjectType.OPERATION_EXPERIENCE: OperationExperience,
    ObjectType.TOOL_PROPOSAL: ToolProposal,
    # --- R4 修改案（M0-023~028）候选契约 ---
    ObjectType.PREDICTION: Prediction,
    ObjectType.LIFE_CHAPTER: LifeChapter,
    ObjectType.REINTERPRETATION: Reinterpretation,
    ObjectType.COMMUNICATION_EXPERIENCE: CommunicationExperience,
    ObjectType.BUDGET_POLICY: BudgetPolicy,
    ObjectType.ASSEMBLY_POLICY: AssemblyPolicy,
    ObjectType.NARRATIVE_SEGMENT: NarrativeSegment,
    ObjectType.DIMENSION_CURVE_POINT: DimensionCurvePoint,
})

if set(CANONICAL_WORLD_OBJECT_MODELS) != set(ObjectType):
    missing = set(ObjectType) - set(CANONICAL_WORLD_OBJECT_MODELS)
    extra = set(CANONICAL_WORLD_OBJECT_MODELS) - set(ObjectType)
    raise RuntimeError(
        f"canonical world-object registry mismatch; missing={missing!r}, extra={extra!r}"
    )


def canonical_model_for_object_type(object_type: ObjectType) -> type[WorldObject]:
    """Return the one frozen durable model authorized for this ObjectType."""

    return CANONICAL_WORLD_OBJECT_MODELS[object_type]
