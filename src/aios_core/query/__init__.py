"""Query layer - 时间镜头、搜索、下钻、对齐等只读能力。

此层封装 storage 的历史读取与 knowledge cutoff 逻辑，禁止直接 SQL。
"""

from .history import HistoricalQueryResult, HistoricalWorldQuery, QueryCoverage
from .cjk_inverted_index import (
    CJKTopologicalInvertedIndex,
    ensure_cjk_schema,
    tokenize_cjk_overlapping,
)
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
    "HistoricalQueryResult",
    "HistoricalWorldQuery",
    "QueryCoverage",
    "CJKTopologicalInvertedIndex",
    "ensure_cjk_schema",
    "tokenize_cjk_overlapping",
    "MAX_DEPTH",
    "AmbiguousAlias",
    "AmbiguousEntityAliasError",
    "AnchorNode",
    "EntityHyperlinkGraphTraverser",
    "EntityNode",
    "EvidenceSetNode",
    "HyperlinkLevel",
    "HyperlinkTraversalError",
    "HyperlinkTraversalResult",
    "IndexBuildReport",
    "IndexWatermark",
    "ObservationNode",
    "StaleHyperlinkIndexError",
    "TraversalContinuation",
    "TraversalCoverage",
    "UnknownEntityError",
    "normalize_alias",
]
