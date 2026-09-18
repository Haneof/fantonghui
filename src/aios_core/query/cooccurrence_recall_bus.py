"""多关键词共现拓扑召回总线（CoOccurrenceRecallBus）。

问题
----
底层 ``CJKTopologicalInvertedIndex.co_search`` 走的是
``GROUP BY entity_id HAVING COUNT(DISTINCT term) = N`` 的**精确交集**：查询词必须
与索引里的切词结果逐字相同，才会被计数。

于是现实里的口语查询（"合伙 借贷 撕逼 银行流水"）会**一词不中、全盘落空**：
用户说的是"撕逼"，世界里的原话是"翻脸/不认这笔账"；用户说"银行流水"，
世界里存的是"流水号/转出"。检索层把**词汇鸿沟**甩给了用户，这违反"关键词是世界
入口、不是世界最终真相"（第三十六条）。

本工具做了什么
--------------
在真实倒排索引之上加一层**召回总线**（不改索引内部实现，只做只读投影）：

1. **可选策略扩展**：同义/近义扩展必须由调用方或版本化 Cognitive Policy 显式注入；本模块不内置世界语义词典；
2. **覆盖度度量**：返回命中组数 / 查询组数作为可解释检索证据；默认不以固定 coverage 阈值替 AI 作相关性裁决；
3. **拒绝全表扫描**：召回只走 ``topological_cjk_terms`` 的 term 索引 + 一次
   ``IN`` 查询，然后按 entity 聚合（在 CPU 上做覆盖度计算，绝不做 LIKE 全扫）。

输出结构自带"为什么召回它"的解释（matched_groups / matched_terms），可直接进入
驾驶舱看板的证据摘要 —— 满足"每个结论必须能追溯证据"的要求。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Sequence

from aios_core.query.cjk_inverted_index import tokenize_cjk_overlapping

__all__ = [
    "CoOccurrenceRecallBus",
    "RecallHit",
    "RecallResult",
]


#: R5/R6: no built-in semantic expansion table. Callers inject versioned policy data explicitly.



@dataclass(frozen=True, slots=True)
class RecallHit:
    """一条召回命中（含"为什么召回"的可解释字段）。"""

    entity_id: str
    coverage: float
    matched_groups: tuple[str, ...]
    matched_terms: tuple[str, ...]
    window_matches: int
    last_occurred_ns: int

    @property
    def group_count(self) -> int:
        return len(self.matched_groups)


@dataclass(frozen=True, slots=True)
class RecallResult:
    """一次共现召回的整体结果（含召回代价审计）。"""

    query_terms: tuple[str, ...]
    expanded_terms: tuple[str, ...]
    hits: tuple[RecallHit, ...]
    candidate_entities_scanned: int
    tokens_cost: int
    scan_mode: str = "inverted_index_only"


class CoOccurrenceRecallBus:
    """多关键词共现拓扑召回总线（同义展开 + 覆盖度打分）。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        expansions: Mapping[str, Sequence[str]] | None = None,
        token_cost_per_hit: int = 12,
    ) -> None:
        self._conn = conn
        self._expansions: Dict[str, tuple[str, ...]] = {}
        if expansions:
            for key, value in expansions.items():
                self._expansions[str(key)] = tuple(value)
        self._token_cost_per_hit = int(token_cost_per_hit)

    # ------------------------------------------------------------------
    # 召回
    # ------------------------------------------------------------------

    def recall(
        self,
        query_terms: Sequence[str],
        *,
        limit: int = 10,
        min_coverage: float | None = None,
    ) -> RecallResult:
        """Return retrieval candidates without a built-in relevance cutoff.

        min_coverage is an optional caller/policy hint. None means the
        retrieval layer returns all matched candidates and leaves relevance
        judgment to the cognitive runtime.
        """
        if min_coverage is not None and not 0.0 <= float(min_coverage) <= 1.0:
            raise ValueError("min_coverage must be within [0, 1] when provided")
        groups: list[tuple[str, tuple[str, ...]]] = []
        for term in query_terms:
            key = str(term).strip()
            if not key:
                continue
            expanded = self._expansions.get(key, (key,))
            if key not in expanded:
                expanded = (key,) + tuple(expanded)
            groups.append((key, tuple(dict.fromkeys(expanded))))
        if not groups:
            return RecallResult((), (), (), 0, 0)

        expanded_terms: list[str] = []
        for _key, terms in groups:
            expanded_terms.extend(terms)
        expanded_terms = list(dict.fromkeys(expanded_terms))

        placeholders = ",".join("?" for _ in expanded_terms)
        rows = self._conn.execute(
            f"""
            SELECT entity_id, term, occurred_at
            FROM topological_cjk_terms
            WHERE term IN ({placeholders})
            """,
            tuple(expanded_terms),
        ).fetchall()

        per_entity: Dict[str, Dict[str, object]] = {}
        for entity_id, term, occurred_at in rows:
            bucket = per_entity.setdefault(
                str(entity_id),
                {"groups": set(), "terms": set(), "count": 0, "last": 0},
            )
            for key, terms in groups:
                if term in terms:
                    bucket["groups"].add(key)  # type: ignore[union-attr]
            bucket["terms"].add(str(term))  # type: ignore[union-attr]
            bucket["count"] = int(bucket["count"]) + 1  # type: ignore[arg-type]
            bucket["last"] = max(int(bucket["last"]), int(occurred_at))  # type: ignore[arg-type]

        hits: list[RecallHit] = []
        for entity_id, bucket in per_entity.items():
            groups_hit = sorted(bucket["groups"])  # type: ignore[arg-type]
            coverage = len(groups_hit) / len(groups)
            if min_coverage is not None and coverage < float(min_coverage):
                continue
            hits.append(
                RecallHit(
                    entity_id=entity_id,
                    coverage=round(coverage, 4),
                    matched_groups=tuple(groups_hit),
                    matched_terms=tuple(sorted(bucket["terms"])),  # type: ignore[arg-type]
                    window_matches=int(bucket["count"]),  # type: ignore
                    last_occurred_ns=int(bucket["last"]),  # type: ignore
                )
            )
        hits.sort(key=lambda hit: (-hit.coverage, -hit.last_occurred_ns, hit.entity_id))
        limited = tuple(hits[:limit])
        return RecallResult(
            query_terms=tuple(str(term).strip() for term in query_terms if str(term).strip()),
            expanded_terms=tuple(expanded_terms),
            hits=limited,
            candidate_entities_scanned=len(per_entity),
            tokens_cost=len(limited) * self._token_cost_per_hit,
        )

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    def expansion_table(self) -> Mapping[str, tuple[str, ...]]:
        return dict(self._expansions)

    def indexed_term_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(DISTINCT term) FROM topological_cjk_terms").fetchone()
        return int(row[0]) if row else 0

    def index_entity_texts(self, items: Iterable[tuple[str, str, int]]) -> int:
        """批量写入倒排（与底层索引同构的写入口径，供盲测装配世界用）。"""

        payload: list[tuple[str, str, int]] = []
        for entity_id, text, timestamp_ns in items:
            for term in tokenize_cjk_overlapping(text):
                payload.append((term, entity_id, int(timestamp_ns)))
        if not payload:
            return 0
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO topological_cjk_terms (term, entity_id, occurred_at) "
                "VALUES (?, ?, ?)",
                payload,
            )
        return len(payload)
