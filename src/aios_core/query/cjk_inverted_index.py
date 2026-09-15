"""M1-017：CJK 拓扑倒排聚集表与多词共现检索加速引擎。

对应《AIOS 核心系统宪法 v3.0》第八十九条（多关键词共现联想检索引擎）：
系统必须原生支持 ``[妈妈, 生日, 礼物]`` 这类复合意图的一次性交集召回，
严禁把复合意图割裂为多次低效的单词检索。

为什么必须自建倒排表
--------------------
SQLite 自带的 FTS5 默认分词器 ``unicode61`` 按 Unicode 词边界切分，
对连续中文不分词——``MATCH '妈妈'`` 在中文文本上实测命中 **0 行**。
因此本模块用纯 Python 的一元/二元重叠切分建立倒排表，
再用一条 ``GROUP BY ... HAVING COUNT(DISTINCT term) = N`` 完成毫秒级求交。

与 M0 冻结契约的关系
--------------------
本模块只创建**独立的加速侧表**（``topological_cjk_terms`` /
``entity_co_occurrence_edges``），不 ``ALTER`` 任何 M0 冻结表，
也不修改 ``object_revisions`` 的结构。它是可随时重建的派生索引：
数据源永远是 ``object_revisions``，本表丢失后可全量重建。

已知边界（不隐藏）
------------------
一元/二元索引是 CJK 信息检索的标准折中，**不做词法分析**。因此
"今天天气好" 会产出二元词 "天天"，查询 "天天" 会命中它——这是
二元索引固有的边界跨越假阳性，不是缺陷。要消除它需要词典分词，
那属于 M1-018 的检索内核范畴，不在本工单内。

并行实现提示
------------
分支 ``arena/agent-02-m1-017`` 上存在同一工单的另一份实现（提交
``e509280``）。两者都能通过工单 §3 的验收断言，但有两处行为差异，
合并前必须择一：

1. **标点处理**：该实现把标点**删除**后拼接，于是 "…生日礼物，妈妈…"
   会产出跨句二元词 ``物妈``，``co_search(["物妈"])`` 可命中——
   这是假共现来源。本实现把标点作为**分隔符**切句，不产出 ``物妈``。
2. **查询词展开**：该实现对查询词不再二次分词，因此三字以上的查询词
   （如 ``"生日礼物"``）**静默返回空集**。本实现按同一规则展开为二元词
   后求交，``co_search(["妈妈", "生日礼物"])`` 正确命中。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence

__all__ = [
    "CJKTopologicalInvertedIndex",
    "CoOccurrenceEdge",
    "ScoredHit",
    "tokenize_cjk_overlapping",
]

# 单条 IN(...) 查询允许的最大词元数。超过这个数量说明调用方在做全文分析，
# 应当走 M1-018 的检索内核，而不是本加速表。
MAX_QUERY_TERMS = 64

# 判定一个字符是否属于 CJK（含扩展 A 与兼容表意文字）。
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x3040, 0x30FF),  # 平假名 / 片假名
    (0xAC00, 0xD7AF),  # 谚文音节
)


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return any(start <= code <= end for start, end in _CJK_RANGES)


def _is_run_char(char: str) -> bool:
    """词元内字符：字母、数字或 CJK。标点与空白是**分隔符**，不是词元。"""
    return char.isalnum()


def tokenize_cjk_overlapping(text: str) -> set[str]:
    """纯 Python 一元 + 二元重叠滑动切分器（零第三方依赖）。

    规则：
    1. 标点与空白一律作为**分隔符**，把文本切成若干连续 run。
       （工单参考实现把 ``，。？！`` 保留进文本，会产出 "物，"、"，妈"
       这类跨句垃圾词元，既污染索引又制造假共现——此处修正。）
    2. run 内逐字产出一元词；相邻两字产出二元词（重叠滑动）。
    3. 纯 ASCII 的 run 额外保留整体小写形式，使 ``iPhone`` 这类
       拉丁词元可直接命中，而不必退化成字符级碎片。

    >>> sorted(tokenize_cjk_overlapping("妈妈生日"))
    ['妈', '妈妈', '妈生', '日', '生', '生日']
    """
    if not text:
        return set()

    terms: set[str] = set()
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        length = len(run)
        for i in range(length):
            terms.add(run[i])
            if i + 1 < length:
                terms.add(run[i] + run[i + 1])
        # 纯拉丁/数字 run 额外保留整词，便于精确命中产品名、型号等。
        if length > 2 and all(run[i].isascii() for i in range(length)):
            terms.add("".join(run))
        run.clear()

    for char in text:
        if _is_run_char(char):
            # ASCII 一律小写，使拉丁词元大小写不敏感；索引侧与查询侧同规则。
            run.append(char.lower() if char.isascii() else char)
        else:
            flush()
    flush()
    return terms


def _expand_query_term(term: str) -> set[str]:
    """把单个查询词展开为索引里真实存在的词元。

    与 :func:`tokenize_cjk_overlapping` 的区别：**只产出有判别力的词元**。
    索引侧必须产出每个字符的一元词（否则二元词无法组合），但查询侧
    要求一元词是纯浪费——二元词存在时其两个一元词必然存在，加进
    ``HAVING`` 阈值只会让 ``matched_terms`` 变得不可读、并放大 IN 列表。

    规则：CJK run 长度 1 取该字，长度 >= 2 取全部重叠二元词；
    纯 ASCII 且长度 > 2 的 run 取整词（与索引侧一致）。
    """
    expanded: set[str] = set()
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        if len(run) == 1:
            expanded.add(run[0])
        else:
            for i in range(len(run) - 1):
                expanded.add(run[i] + run[i + 1])
        if len(run) > 2 and all(c.isascii() for c in run):
            expanded.add("".join(run))
        run.clear()

    for char in term:
        if _is_run_char(char):
            run.append(char.lower() if char.isascii() else char)
        else:
            flush()
    flush()
    return expanded


class ScoredHit:
    """带匹配词数与最近命中时间的检索结果。"""

    __slots__ = ("entity_id", "last_occurred_at", "matched_terms")

    def __init__(
        self, entity_id: str, matched_terms: int, last_occurred_at: int
    ) -> None:
        self.entity_id = entity_id
        self.matched_terms = matched_terms
        self.last_occurred_at = last_occurred_at

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        return (
            f"ScoredHit(entity_id={self.entity_id!r}, "
            f"matched_terms={self.matched_terms}, last_occurred_at={self.last_occurred_at})"
        )


class CoOccurrenceEdge:
    """``entity_co_occurrence_edges`` 的一行。"""

    __slots__ = (
        "co_occurrence_count",
        "last_occurred_at",
        "source_entity_id",
        "target_entity_id",
    )

    def __init__(
        self,
        source_entity_id: str,
        target_entity_id: str,
        co_occurrence_count: int,
        last_occurred_at: int,
    ) -> None:
        self.source_entity_id = source_entity_id
        self.target_entity_id = target_entity_id
        self.co_occurrence_count = co_occurrence_count
        self.last_occurred_at = last_occurred_at

    def neighbor(self, entity_id: str) -> str:
        """返回边的另一端。

        边按 ``(min, max)`` 归一存储，因此查询实体可能落在 source 或 target
        任一侧；调用方要的是"邻居是谁"，不是"我在哪一列"。
        """
        if entity_id == self.source_entity_id:
            return self.target_entity_id
        if entity_id == self.target_entity_id:
            return self.source_entity_id
        raise ValueError(f"{entity_id!r} is not an endpoint of this edge")

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        return (
            f"CoOccurrenceEdge({self.source_entity_id!r} -> {self.target_entity_id!r}, "
            f"count={self.co_occurrence_count})"
        )


_DDL = """
CREATE TABLE IF NOT EXISTS topological_cjk_terms (
    term TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    occurred_at INTEGER NOT NULL,
    PRIMARY KEY (term, entity_id, occurred_at)
);

CREATE INDEX IF NOT EXISTS idx_cjk_term_occurred
    ON topological_cjk_terms (term, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_cjk_entity_term
    ON topological_cjk_terms (entity_id, term);

CREATE TABLE IF NOT EXISTS entity_co_occurrence_edges (
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    co_occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_occurred_at INTEGER NOT NULL,
    PRIMARY KEY (source_entity_id, target_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_co_count
    ON entity_co_occurrence_edges (co_occurrence_count DESC);
"""


class CJKTopologicalInvertedIndex:
    """CJK 一元/二元倒排索引 + 多词共现求交引擎。

    只依赖一个 ``sqlite3.Connection``，不持有业务状态，因此可以指向
    内存库（单测）、独立加速库文件，或与主库同连接。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.ensure_schema()

    # ------------------------------------------------------------------ DDL

    def ensure_schema(self) -> None:
        """幂等建表建索引。"""
        with self._conn:
            self._conn.executescript(_DDL)

    # ------------------------------------------------------------- 写入路径

    def index_entity_text(self, entity_id: str, text: str, timestamp_ns: int) -> int:
        """把一个实体的文本切词后写入倒排表，返回写入的词元数。

        重复 ``(term, entity_id, occurred_at)`` 由主键吸收（``INSERT OR IGNORE``），
        因此同一段文本重复索引是幂等的。
        """
        if not entity_id.strip():
            raise ValueError("entity_id must not be blank")
        if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool):
            raise TypeError("timestamp_ns must be an int (nanoseconds)")
        if timestamp_ns < 0:
            raise ValueError("timestamp_ns must be >= 0")

        terms = tokenize_cjk_overlapping(text)
        if not terms:
            return 0

        rows = [(term, entity_id, timestamp_ns) for term in sorted(terms)]
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO topological_cjk_terms "
                "(term, entity_id, occurred_at) VALUES (?, ?, ?)",
                rows,
            )
        return len(rows)

    def index_many(self, items: Iterable[tuple[str, str, int]]) -> int:
        """批量索引 ``(entity_id, text, timestamp_ns)``，单事务提交。"""
        rows: list[tuple[str, str, int]] = []
        for entity_id, text, timestamp_ns in items:
            if not entity_id.strip():
                raise ValueError("entity_id must not be blank")
            if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool):
                raise TypeError("timestamp_ns must be an int (nanoseconds)")
            if timestamp_ns < 0:
                raise ValueError("timestamp_ns must be >= 0")
            rows.extend(
                (term, entity_id, timestamp_ns)
                for term in sorted(tokenize_cjk_overlapping(text))
            )
        if not rows:
            return 0
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO topological_cjk_terms "
                "(term, entity_id, occurred_at) VALUES (?, ?, ?)",
                rows,
            )
        return len(rows)

    def delete_entity_terms(self, entity_id: str) -> int:
        """删除某实体的全部倒排行，返回删除行数。

        实体文本被修订时必须先删后写，否则旧词元会残留成幽灵召回。
        """
        if not entity_id.strip():
            raise ValueError("entity_id must not be blank")
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM topological_cjk_terms WHERE entity_id = ?", (entity_id,)
            )
            self._conn.execute(
                "DELETE FROM entity_co_occurrence_edges "
                "WHERE source_entity_id = ? OR target_entity_id = ?",
                (entity_id, entity_id),
            )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def reindex_entity_text(self, entity_id: str, text: str, timestamp_ns: int) -> int:
        """先删后写的原子重建，用于实体文本修订。"""
        with self._conn:
            self.delete_entity_terms(entity_id)
        return self.index_entity_text(entity_id, text, timestamp_ns)

    # ------------------------------------------------------------- 检索路径

    def _required_terms(self, query_terms: Sequence[str]) -> list[str]:
        """把查询词元规范化为索引里真实存在的词元集合。

        两处修正（相对工单参考实现）：
        1. **去重**：``["妈妈","妈妈","生日"]`` 若直接取 ``len()`` 作为
           ``HAVING`` 的阈值，永远不可能满足，会返回空集。
        2. **展开**：索引只含一元/二元词，三字以上的查询词（如 "生日礼物"）
           必须经同一切分器展开为二元词后求交，否则永远命中不到。
        规范化后 ``len(required)`` 恰好等于 ``HAVING`` 阈值，因此
        :meth:`co_search_scored` 返回的 ``matched_terms`` 就是
        "命中了几个查询词"，可直接用于 top-k 排序。
        """
        if not query_terms:
            return []
        if len(query_terms) > MAX_QUERY_TERMS:
            raise ValueError(f"too many query terms (max {MAX_QUERY_TERMS})")

        required: set[str] = set()
        for raw in query_terms:
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("query terms must be non-blank strings")
            expanded = _expand_query_term(raw)
            if not expanded:
                # 查询词全是标点：视为无约束，而不是让整个查询静默返回空。
                continue
            required.update(expanded)
        return sorted(required)

    def co_search(self, query_terms: Sequence[str]) -> list[str]:
        """多词共现求交：只返回**同时命中全部查询词**的实体。

        执行工单指定的核心 SQL：
        ``GROUP BY entity_id HAVING COUNT(DISTINCT term) = :num_terms``。
        """
        required = self._required_terms(query_terms)
        if not required:
            return []

        placeholders = ",".join("?" * len(required))
        sql = (
            "SELECT entity_id FROM topological_cjk_terms "
            f"WHERE term IN ({placeholders}) "
            "GROUP BY entity_id "
            "HAVING COUNT(DISTINCT term) = ? "
            "ORDER BY entity_id"
        )
        cursor = self._conn.execute(sql, (*required, len(required)))
        return [row[0] for row in cursor.fetchall()]

    def co_search_scored(
        self, query_terms: Sequence[str], *, limit: int | None = None
    ) -> list[ScoredHit]:
        """同 :meth:`co_search`，但附带匹配词数与最近命中时间，按时间倒序。

        供上层做 top-k 截断与"最近优先"排序，避免一次性把全部命中拉进上下文
        （宪法第八十九条要求返回指针而非全文）。
        """
        required = self._required_terms(query_terms)
        if not required:
            return []
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")

        placeholders = ",".join("?" * len(required))
        sql = (
            "SELECT entity_id, COUNT(DISTINCT term) AS matched, MAX(occurred_at) AS latest "
            "FROM topological_cjk_terms "
            f"WHERE term IN ({placeholders}) "
            "GROUP BY entity_id "
            "HAVING matched = ? "
            "ORDER BY latest DESC"
        )
        params: list[object] = [*required, len(required)]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        cursor = self._conn.execute(sql, params)
        return [ScoredHit(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def partial_search(
        self, query_terms: Sequence[str], *, min_matched: int = 1
    ) -> list[ScoredHit]:
        """放宽版：命中至少 ``min_matched`` 个查询词即返回，按命中数降序。

        用于"共振密集区"展示（宪法第八十九条），与严格求交互补。
        """
        required = self._required_terms(query_terms)
        if not required:
            return []
        if min_matched < 1:
            raise ValueError("min_matched must be >= 1")

        placeholders = ",".join("?" * len(required))
        sql = (
            "SELECT entity_id, COUNT(DISTINCT term) AS matched, MAX(occurred_at) AS latest "
            "FROM topological_cjk_terms "
            f"WHERE term IN ({placeholders}) "
            "GROUP BY entity_id "
            "HAVING matched >= ? "
            "ORDER BY matched DESC, latest DESC"
        )
        cursor = self._conn.execute(sql, (*required, min(min_matched, len(required))))
        return [ScoredHit(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def explain(self, query_terms: Sequence[str]) -> dict[str, int]:
        """返回每个查询词元的倒排行数，用于超节点诊断与预算判断。"""
        required = self._required_terms(query_terms)
        if not required:
            return {}
        placeholders = ",".join("?" * len(required))
        cursor = self._conn.execute(
            f"SELECT term, COUNT(*) FROM topological_cjk_terms "
            f"WHERE term IN ({placeholders}) GROUP BY term",
            required,
        )
        counts = {row[0]: row[1] for row in cursor.fetchall()}
        return {term: counts.get(term, 0) for term in required}

    # --------------------------------------------------------- 共现拓扑边

    def record_co_occurrence(self, entity_ids: Sequence[str], timestamp_ns: int) -> int:
        """记录一批实体在同一次上下文中共现，两两累加边权重。

        同一次上下文内的实体互为转载边；边是无向的，但按
        ``(min, max)`` 归一存储，避免 A->B 与 B->A 双份。
        """
        if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool):
            raise TypeError("timestamp_ns must be an int (nanoseconds)")
        if timestamp_ns < 0:
            raise ValueError("timestamp_ns must be >= 0")

        unique = sorted({e for e in entity_ids if e and e.strip()})
        if len(unique) < 2:
            return 0

        pairs: list[tuple[str, str, int, int]] = []
        for i, source in enumerate(unique):
            for target in unique[i + 1 :]:
                pairs.append((source, target, 1, timestamp_ns))

        with self._conn:
            self._conn.executemany(
                "INSERT INTO entity_co_occurrence_edges "
                "(source_entity_id, target_entity_id, co_occurrence_count, last_occurred_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(source_entity_id, target_entity_id) DO UPDATE SET "
                "co_occurrence_count = co_occurrence_count + excluded.co_occurrence_count, "
                "last_occurred_at = MAX(last_occurred_at, excluded.last_occurred_at)",
                pairs,
            )
        return len(pairs)

    def top_co_occurrence(
        self, entity_id: str, *, limit: int = 10
    ) -> list[CoOccurrenceEdge]:
        """返回与某实体共现最强的邻居，按共现次数降序。"""
        if not entity_id.strip():
            raise ValueError("entity_id must not be blank")
        if limit <= 0:
            raise ValueError("limit must be positive")
        cursor = self._conn.execute(
            "SELECT source_entity_id, target_entity_id, co_occurrence_count, last_occurred_at "
            "FROM entity_co_occurrence_edges "
            "WHERE source_entity_id = ? OR target_entity_id = ? "
            "ORDER BY co_occurrence_count DESC LIMIT ?",
            (entity_id, entity_id, limit),
        )
        return [CoOccurrenceEdge(*row) for row in cursor.fetchall()]

    # ------------------------------------------------------------ 可观测性

    def stats(self) -> dict[str, int]:
        """索引规模，供 M1-014 索引水位与容量规划使用。"""
        cursor = self._conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT term), COUNT(DISTINCT entity_id) "
            "FROM topological_cjk_terms"
        )
        rows, distinct_terms, distinct_entities = cursor.fetchone()
        edge_count = self._conn.execute(
            "SELECT COUNT(*) FROM entity_co_occurrence_edges"
        ).fetchone()[0]
        return {
            "postings_rows": rows,
            "distinct_terms": distinct_terms,
            "distinct_entities": distinct_entities,
            "co_occurrence_edges": edge_count,
        }
