"""World services - Entity/Claim/Event/Dimension/Goal 等写服务 + 复盘回溯层。

M1-018「认知反向传播语义图层」（王建国/老王案：历史不可篡改铁律）在本包内
**双线并存**，两条线各自独立落盘、互不覆盖，供首席仲裁择优或熔铸：

1. ``retrospective_annotation``（战队已合入基线，b0c540a → 7785aed 加固）
   - ``ImmutableFactLedger``：追加式事实账本，SHA-256 物理哈希封存，无 UPDATE/DELETE API；
   - ``RetrospectiveAnnotation`` / ``AnnotationRegistry``：今天打标签的外挂解释图层；
   - ``BiTemporalEpistemicLens``：事件时间 × 知识时间双时间认知透镜（累积切片 ``(-∞, t]``）；
   - ``SingleHopCascadeIsolator``：单跳级联隔离，杜绝 210 次大模型算力雪崩。

2. ``epistemic_world_lens``（Agent-05 本线：超集契约面 + 重负载门禁）
   - ``EpistemicWorldLens``：直接吃 M0-005 世界对象（Observation/Claim/Summary/Entity/...），
     以**真实落库 payload 字节**的 SHA-256 为历史锚点，图层挂载前后逐条恒定；
   - 规范字段名采用升级版工单命名（``valid_time_start`` / ``valid_time_end`` /
     ``source_evidence_ref`` / ``confidence`` / ``recorded_at``），并以只读别名
     同时接受一号工单命名（``target_time_*`` / ``source_statement_ref``）；
   - ``HistoricalEpistemicSlice`` + ``BiTemporalEpistemicLens.query_entity_state``：
     支持 ``slice_mode="instant"``（精确时间点/区间）与 ``"cumulative"``（复现基线语义）；
   - ``SingleHopCascadeIsolator`` + ``SingleHopInvalidationReport``：审计报告字段被
     ``Field(ge=1, le=1)`` / ``le=0`` / ``Literal[False]`` 物理锁死，无法表达“发生过级联”；
   - ``coerce_annotation`` / ``RetrospectiveAnnotation.to_sibling_annotation``：与基线契约双向互操作。

三个同名符号（``BiTemporalEpistemicLens`` / ``RetrospectiveAnnotation`` /
``SingleHopCascadeIsolator``）在包级导出上**以基线为准**，避免破坏既有调用方；
需要本线实现时请显式 ``from aios_core.world.epistemic_world_lens import ...``。
"""
from .epistemic_world_lens import (
    DIGEST_ALGORITHM,
    MAX_DIAGNOSTIC_DEPTH,
    MAX_OVERLAY_HOPS,
    MAX_SUPERSEDE_CHAIN_DEPTH,
    AnnotationTargetNotFound,
    AttachmentReceipt,
    EpistemicSliceView,
    EpistemicWorldLens,
    FactAnchor,
    FactTamperFinding,
    HistoricalEpistemicSlice,
    HistoryImmutabilityViolation,
    IntegrityReport,
    OverlayCascadeForbidden,
    RecomputeAudit,
    RetrospectiveAnnotationError,
    SingleHopInvalidationReport,
    SliceCoverage,
    SliceFactView,
    SliceOverlayView,
    annotation_sha256,
    coerce_annotation,
    coerce_world_object,
    encode_fact_payload,
    fact_sha256,
    new_annotation_id,
    normalize_dependency_graph,
)
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
    # —— 基线（retrospective_annotation）——
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
    # —— 本线（epistemic_world_lens）非冲突导出 ——
    "DIGEST_ALGORITHM",
    "MAX_DIAGNOSTIC_DEPTH",
    "MAX_OVERLAY_HOPS",
    "MAX_SUPERSEDE_CHAIN_DEPTH",
    "AnnotationTargetNotFound",
    "AttachmentReceipt",
    "EpistemicSliceView",
    "EpistemicWorldLens",
    "FactAnchor",
    "FactTamperFinding",
    "HistoricalEpistemicSlice",
    "HistoryImmutabilityViolation",
    "IntegrityReport",
    "OverlayCascadeForbidden",
    "RecomputeAudit",
    "RetrospectiveAnnotationError",
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
