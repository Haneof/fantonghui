"""World services - Entity/Claim/Event/Dimension/Goal 等写服务占位。

M1 实现，M0-001 仅建边界。

M1-018（本包已落地）：认知反向传播语义图层契约
------------------------------------------------
* :class:`RetrospectiveAnnotation`：只追加在"今天"的复盘注记（司法查封 / 欺诈重估）；
* :class:`BiTemporalEpistemicLens`：双时间认知透镜（当时已知 vs 当前叠加视图）；
* :class:`ObservationHashLedger`：客观事实的 SHA-256 物理台账（历史不可篡改的举证）；
* :class:`SingleHopCascadeIsolator`：严格单跳失效隔离（杜绝 210 次级联算力雪崩）。

铁律：本包**绝不**改写或删除历史事实；世界写入唯一入口仍是
``SQLiteWorldStore.commit()`` 的追加语义。
"""

from .retrospective_annotation import (
    ANNOTATION_SCHEMA_TAG,
    MAX_RECOMPUTE_CONCURRENCY,
    AnnotationKind,
    AnnotationReceipt,
    BiTemporalEpistemicLens,
    CognitiveNode,
    DeferredRecomputeBatch,
    DependencyEdge,
    DuplicateAnnotationError,
    EpistemicSlice,
    EpistemicWorldLens,
    HashLedgerDiff,
    HistoryMutationDetectedError,
    InvalidationReport,
    KnowledgeMode,
    ObservationHashLedger,
    PhysicalChainIndex,
    PhysicalObservation,
    RetroactiveWriteDeniedError,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationLog,
    RetrospectiveAnnotationWriter,
    SingleHopCascadeIsolator,
    UnknownTargetEntityError,
    annotations_from_store,
    invalidate_overturned_fact_single_hop,
    observations_linked_to_entity,
)

__all__ = [
    "ANNOTATION_SCHEMA_TAG",
    "MAX_RECOMPUTE_CONCURRENCY",
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
