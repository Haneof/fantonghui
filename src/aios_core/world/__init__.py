"""World services - Entity/Claim/Event/Dimension/Goal 等写服务 + 复盘回溯层。

M1-018 实现：``retrospective_annotation``（老王案：历史不可篡改铁律）。
- ``ImmutableFactLedger``：追加式事实账本，SHA-256 物理哈希封存，无 UPDATE/DELETE API；
- ``RetrospectiveAnnotation`` / ``AnnotationRegistry``：今天打标签的外挂解释图层；
- ``BiTemporalEpistemicLens``：事件时间 × 知识时间双时间认知透镜；
- ``SingleHopCascadeIsolator``：单跳级联隔离，杜绝 210 次大模型算力雪崩。
"""
from .retrospective_annotation import (
    AnnotationBudgetExceededError,
    AnnotationConflictError,
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    CascadeIsolationError,
    HistoricalFact,
    HistoricalSliceView,
    ImmutableFactLedger,
    InvalidationReport,
    LedgerConflictError,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)

__all__ = [
    "AnnotationBudgetExceededError",
    "AnnotationConflictError",
    "AnnotationRegistry",
    "BiTemporalEpistemicLens",
    "CascadeIsolationError",
    "HistoricalFact",
    "HistoricalSliceView",
    "ImmutableFactLedger",
    "InvalidationReport",
    "LedgerConflictError",
    "RetrospectiveAnnotation",
    "SingleHopCascadeIsolator",
]
