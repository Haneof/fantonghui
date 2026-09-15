"""Query layer - 时间镜头、搜索、下钻、对齐等只读能力。

此层封装 storage 的历史读取与 knowledge cutoff 逻辑。

边界约定：**读取世界对象一律经 ``SQLiteWorldStore``，不得直接对
``object_revisions`` 等 M0 冻结表写 SQL。**

唯一例外是 ``cjk_inverted_index``（M1-017）：它只操作自己创建的两张
派生加速侧表（``topological_cjk_terms`` / ``entity_co_occurrence_edges``），
既不 ``ALTER`` 也不查询任何冻结表；这些表可随时从 ``object_revisions``
全量重建，属于可丢弃的索引缓存，不是世界数据。
"""

from .cjk_inverted_index import (
    CJKTopologicalInvertedIndex,
    CoOccurrenceEdge,
    ScoredHit,
    tokenize_cjk_overlapping,
)
from .history import HistoricalQueryResult, HistoricalWorldQuery, QueryCoverage

__all__ = [
    "CJKTopologicalInvertedIndex",
    "CoOccurrenceEdge",
    "HistoricalQueryResult",
    "HistoricalWorldQuery",
    "QueryCoverage",
    "ScoredHit",
    "tokenize_cjk_overlapping",
]
