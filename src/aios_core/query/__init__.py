"""Query layer - 时间镜头、搜索、下钻、对齐等只读能力。

此层封装 storage 的历史读取与 knowledge cutoff 逻辑，禁止直接 SQL。
"""

from .cjk_inverted_index import (
    CJKTopologicalInvertedIndex,
    ensure_cjk_schema,
    tokenize_cjk_overlapping,
)
from .epistemic_projection import (
    DualLensProjectionIndex,
    EpistemicProjection,
    ImmutableProjectionFact,
    ProjectionOverlay,
    dual_lens_projection_tool_proposal,
)
from .history import HistoricalQueryResult, HistoricalWorldQuery, QueryCoverage
from .hyperlink_traverser import (
    MAX_DEPTH,
    AmbiguousAlias,
    AmbiguousEntityAliasError,
    AnchorNode,
    EntityHyperlinkGraphTraverser,
    EntityNode,
    EvidenceSetNode,
    HyperlinkLevel,
    HyperlinkTraversalError,
    HyperlinkTraversalResult,
    IndexBuildReport,
    IndexWatermark,
    ObservationNode,
    StaleHyperlinkIndexError,
    TraversalContinuation,
    TraversalCoverage,
    UnknownEntityError,
    normalize_alias,
)

__all__ = [
    "MAX_DEPTH",
    "AmbiguousAlias",
    "AmbiguousEntityAliasError",
    "AnchorNode",
    "CJKTopologicalInvertedIndex",
    "DualLensProjectionIndex",
    "EntityHyperlinkGraphTraverser",
    "EntityNode",
    "EpistemicProjection",
    "EvidenceSetNode",
    "HistoricalQueryResult",
    "HistoricalWorldQuery",
    "HyperlinkLevel",
    "HyperlinkTraversalError",
    "HyperlinkTraversalResult",
    "ImmutableProjectionFact",
    "IndexBuildReport",
    "IndexWatermark",
    "ObservationNode",
    "ProjectionOverlay",
    "QueryCoverage",
    "StaleHyperlinkIndexError",
    "TraversalContinuation",
    "TraversalCoverage",
    "UnknownEntityError",
    "dual_lens_projection_tool_proposal",
    "ensure_cjk_schema",
    "normalize_alias",
    "tokenize_cjk_overlapping",
]
