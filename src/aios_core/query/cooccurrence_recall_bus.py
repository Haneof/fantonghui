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

1. **口语词 → 世界术语的同义展开**（``seed_expansions`` 可注入、可版本化）；
2. **覆盖度召回**：不再要求"每个词都命中"，而是按"命中了查询原词组的几个组"
   打分（覆盖度 = 命中组数 / 查询组数），并保留**每个组的实际命中词**用于解释；
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
    "DEFAULT_SEED_EXPANSIONS",
    "RecallHit",
    "RecallResult",
]


#: 口语查询词 → 世界术语种子展开表（**词元级**，与 1/2 元重叠倒排的切词口径对齐）。
#: 表本身可版本化、可由经验沉淀（OperationExperience）替换。
DEFAULT_SEED_EXPANSIONS: Mapping[str, Sequence[str]] = {
    "合伙": ("合伙", "股份", "协议", "白纸"),
    "借贷": ("借条", "借款", "欠", "还你", "流水", "转出"),
    "撕逼": ("翻脸", "不认", "法庭", "账"),
    "银行流水": ("流水", "转出", "尾号", "招商"),
    "早搏": ("早搏", "心律", "心口", "发紧"),
    "熬夜": ("熬夜", "通宵", "凌晨", "咖啡"),
    "妈妈": ("妈", "住院", "血压", "饺子", "回家"),
    "搬家": ("搬家", "搬到", "搬去", "租的房子", "成都"),
    "慢性病": ("血压", "血糖", "胰岛素", "复查", "住院"),
    "承诺": ("答应", "说好", "承诺", "我来"),
}


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
        merged: Dict[str, tuple[str, ...]] = {
            key: tuple(value) for key, value in DEFAULT_SEED_EXPANSIONS.items()
        }
        if expansions:
            for key, value in expansions.items():
                merged[key] = tuple(value)
        self._expansions = merged
        self._token_cost_per_hit = int(token_cost_per_hit)

    # ------------------------------------------------------------------
    # 召回
    # ------------------------------------------------------------------

    def recall(
        self,
        query_terms: Sequence[str],
        *,
        limit: int = 10,
        min_coverage: float = 0.5,
    ) -> RecallResult:
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
            if coverage < min_coverage:
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
