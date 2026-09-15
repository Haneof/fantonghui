"""Query layer - 时间镜头、搜索、下钻、对齐等只读能力。

此层封装 storage 的历史读取与 knowledge cutoff 逻辑，禁止直接 SQL。
"""

from .history import HistoricalQueryResult, HistoricalWorldQuery, QueryCoverage
from .hyperlink_traverser import (
    AliasAmbiguousError,
    EntityHyperlinkGraphTraverser,
    EntityNotRegisteredError,
    HyperlinkQueryError,
    HyperlinkTraversalResult,
    InvalidTraversalDepthError,
    MalformedIdentifierError,
    MAX_TRAVERSAL_DEPTH,
    normalize_alias,
)

__all__ = [
    "HistoricalQueryResult",
    "HistoricalWorldQuery",
    "QueryCoverage",
    "AliasAmbiguousError",
    "EntityHyperlinkGraphTraverser",
    "EntityNotRegisteredError",
    "HyperlinkQueryError",
    "HyperlinkTraversalResult",
    "InvalidTraversalDepthError",
    "MalformedIdentifierError",
    "MAX_TRAVERSAL_DEPTH",
    "normalize_alias",
]
