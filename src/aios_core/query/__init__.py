"""Query layer - 时间镜头、搜索、下钻、对齐等只读能力。

此层封装 storage 的历史读取与 knowledge cutoff 逻辑，禁止直接 SQL。
"""

from .history import HistoricalQueryResult, HistoricalWorldQuery, QueryCoverage
from .hyperlink_traverser import (
    AliasConflictError,
    EntityHyperlinkGraphTraverser,
    HyperlinkTraversalResult,
    HyperlinkTraversalError,
    UnknownEntityError,
)

__all__ = [
    "AliasConflictError",
    "EntityHyperlinkGraphTraverser",
    "HistoricalQueryResult",
    "HistoricalWorldQuery",
    "HyperlinkTraversalError",
    "HyperlinkTraversalResult",
    "QueryCoverage",
    "UnknownEntityError",
]
