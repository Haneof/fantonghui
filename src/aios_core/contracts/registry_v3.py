"""Canonical model registry for the V3.0.1 extension objects (M0')."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .base import WorldObject
from .enums_v3 import ObjectTypeV3
from .models_v3 import (
    BudgetLedgerEntry,
    CommunicationExperience,
    ConversationTurn,
    DeletionLog,
    ExtractionJob,
    InvalidationEpoch,
    LifeChapter,
    ManifestInstance,
    NotificationReceipt,
    Prediction,
    RetentionTombstone,
    RetrospectiveAnnotation,
    SpeakerCluster,
    TriggerExpressionObject,
)

CANONICAL_WORLD_OBJECT_MODELS_V3: Mapping[ObjectTypeV3, type[WorldObject]] = (
    MappingProxyType(
        {
            ObjectTypeV3.PREDICTION: Prediction,
            ObjectTypeV3.LIFE_CHAPTER: LifeChapter,
            ObjectTypeV3.COMMUNICATION_EXPERIENCE: CommunicationExperience,
            ObjectTypeV3.RETROSPECTIVE_ANNOTATION: RetrospectiveAnnotation,
            ObjectTypeV3.TRIGGER_EXPRESSION: TriggerExpressionObject,
            ObjectTypeV3.CONVERSATION_TURN: ConversationTurn,
            ObjectTypeV3.EXTRACTION_JOB: ExtractionJob,
            ObjectTypeV3.MANIFEST_INSTANCE: ManifestInstance,
            ObjectTypeV3.NOTIFICATION_RECEIPT: NotificationReceipt,
            ObjectTypeV3.RETENTION_TOMBSTONE: RetentionTombstone,
            ObjectTypeV3.DELETION_LOG: DeletionLog,
            ObjectTypeV3.BUDGET_LEDGER_ENTRY: BudgetLedgerEntry,
            ObjectTypeV3.INVALIDATION_EPOCH: InvalidationEpoch,
            ObjectTypeV3.SPEAKER_CLUSTER: SpeakerCluster,
        }
    )
)

if set(CANONICAL_WORLD_OBJECT_MODELS_V3) != set(ObjectTypeV3):
    missing = set(ObjectTypeV3) - set(CANONICAL_WORLD_OBJECT_MODELS_V3)
    extra = set(CANONICAL_WORLD_OBJECT_MODELS_V3) - set(ObjectTypeV3)
    raise RuntimeError(
        "canonical v3 extension registry mismatch; "
        f"missing={missing!r}, extra={extra!r}"
    )


def canonical_model_for_object_type_v3(object_type: ObjectTypeV3) -> type[WorldObject]:
    """Return the one frozen durable model authorized for this V3 extension type."""

    return CANONICAL_WORLD_OBJECT_MODELS_V3[object_type]
