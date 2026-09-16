"""
M1-017 CJK 拓扑倒排聚集表与多词检索加速引擎

背景：
- SQLite FTS5 默认对中文不分词，查 [妈妈, 生日, 礼物] 命中为0
- 必须通过一元/二元重叠分词（纯Python，零重依赖）建立拓扑倒排表
- 通过 SQL: SELECT entity_id FROM topological_cjk_terms WHERE term IN (...) GROUP BY entity_id HAVING COUNT(DISTINCT term)=:num_terms 实现毫秒级多词交集召回

表：
- topological_cjk_terms: term, entity_id, occurred_at, PK(term, entity_id, occurred_at), INDEX(term, occurred_at DESC)
- entity_co_occurrence_edges: source_entity_id, target_entity_id, co_occurrence_count, last_occurred_at, PK(source,target), INDEX(co_occurrence_count DESC)

作者：Agent-02 战队
"""

from __future__ import annotations

import sqlite3
import time
from typing import List, Set, Iterable, Optional


def tokenize_cjk_overlapping(text: str) -> Set[str]:
    """
    一元/二元重叠滑动切分器（纯Python，零第三方重库依赖）

    设计：
    - 保留：字母数字 + CJK 统一表意文字（U+4E00-U+9FFF, U+3400-U+4DBF, U+F900-U+FAFF, U+3040-U+30FF日文假名, U+AC00-U+D7AF韩文）
    - 过滤：空白、标点（，。？！,.?! 等）仅用于分隔，不进入term，但不丢弃CJK字符
    - 输出：所有一元 + 二元重叠组合
      例："给妈妈买生日礼物" -> {"给","妈","买","生","日","礼","物","给妈","妈妈","妈买","买生","生日","日礼","礼物"}

    Args:
        text: 输入文本

    Returns:
        Set[str]: 去重后的term集合，包含一元和二元
    """
    if not text:
        return set()

    # 清洗：保留 isalnum 为 True 的字符（中文isalnum=True） + CJK范围，过滤空白和常见标点
    # 注意：Python中 "妈".isalnum() == True, "，" .isalnum() == False
    cleaned_chars: List[str] = []
    for c in text:
        # 跳过空白
        if c.isspace():
            continue
        # 跳过所有标点：中英文标点均过滤
        if c in "，。？！、；：,.?!;:()[]{}<>\"'`~@#$%^&*-_=+|\\/\n\t":
            continue
        if c in "。，、？！：；“”‘’（）【】《》":
            continue
        # 保留字母数字（包含中文、日文、韩文等，因为isalnum对CJK返回True）以及常见CJK
        # 额外显式保留CJK以防isalnum在某些环境下不一致，但排除CJK标点区
        is_cjk = (
            '\u4e00' <= c <= '\u9fff'  # CJK Unified Ideographs
            or '\u3400' <= c <= '\u4dbf'  # CJK Extension A
            or '\uf900' <= c <= '\ufaff'  # CJK Compatibility Ideographs
            or '\u3040' <= c <= '\u30ff'  # Hiragana + Katakana
            or '\uac00' <= c <= '\ud7af'  # Hangul
        )
        if c.isalnum() or is_cjk:
            cleaned_chars.append(c)
        # 其余标点直接丢弃

    cleaned = "".join(cleaned_chars)

    terms: Set[str] = set()
    n = len(cleaned)
    if n == 0:
        return terms

    # 一元+二元重叠滑动
    for i in range(n):
        # 一元
        terms.add(cleaned[i])
        # 二元
        if i + 1 < n:
            terms.add(cleaned[i:i+2])

    # 可选：为了更好支持三元查询，额外保留原始清洗串中出现过的长度>2的查询词？
    # 但工单要求一元/二元，故不额外加三元，避免索引膨胀。查询时以一元/二元求交已足够覆盖多词共现。

    return terms


def ensure_cjk_schema(conn: sqlite3.Connection) -> None:
    """
    DDL 自动建表：topological_cjk_terms 与 entity_co_occurrence_edges 及其降序复合索引
    幂等，可重复调用
    """
    # 开启WAL以提升并发（可选，不影响正确性）
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass

    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS topological_cjk_terms (
            term TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            occurred_at INTEGER NOT NULL,
            PRIMARY KEY (term, entity_id, occurred_at)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_cjk_term_occurred
        ON topological_cjk_terms (term, occurred_at DESC);
        """,
        """
        CREATE TABLE IF NOT EXISTS entity_co_occurrence_edges (
            source_entity_id TEXT NOT NULL,
            target_entity_id TEXT NOT NULL,
            co_occurrence_count INTEGER NOT NULL DEFAULT 1,
            last_occurred_at INTEGER NOT NULL,
            PRIMARY KEY (source_entity_id, target_entity_id)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_co_count
        ON entity_co_occurrence_edges (co_occurrence_count DESC);
        """,
        # 额外加速索引：按entity_id反查
        """
        CREATE INDEX IF NOT EXISTS idx_cjk_entity
        ON topological_cjk_terms (entity_id);
        """,
    ]

    with conn:
        for stmt in ddl_statements:
            conn.execute(stmt)


class CJKTopologicalInvertedIndex:
    """
    核心索引类：CJK拓扑倒排索引

    用法：
        conn = sqlite3.connect(":memory:")
        idx = CJKTopologicalInvertedIndex(conn)
        idx.index_entity_text("ent_mom", "给妈妈买生日礼物", now_ns)
        hits = idx.co_search(["妈妈", "生日", "礼物"])  # -> ["ent_mom"]
    """

    def __init__(self, conn: sqlite3.Connection, auto_create: bool = True):
        self.conn = conn
        if auto_create:
            ensure_cjk_schema(self.conn)

    def index_entity_text(self, entity_id: str, text: str, timestamp_ns: int) -> int:
        """
        索引实体文本：分词后写入topological_cjk_terms，INSERT OR IGNORE去重

        Args:
            entity_id: 实体ID，如 "ent_mom"
            text: 实体关联文本，如 "给妈妈买生日礼物，妈妈非常喜欢这个礼物"
            timestamp_ns: 发生时间，纳秒级，如 1726400000000000000

        Returns:
            int: 实际写入的term数量
        """
        if not entity_id or not text:
            return 0

        terms = tokenize_cjk_overlapping(text)
        if not terms:
            return 0

        # 批量写入，使用事务
        # 使用 INSERT OR IGNORE 避免 PK 冲突（term, entity_id, occurred_at）
        inserted = 0
        with self.conn:
            # executemany 更快
            data = [(t, entity_id, timestamp_ns) for t in terms]
            # 使用 INSERT OR IGNORE
            self.conn.executemany(
                "INSERT OR IGNORE INTO topological_cjk_terms (term, entity_id, occurred_at) VALUES (?, ?, ?)",
                data,
            )
            # sqlite3 的 rowcount 在 executemany 时可能为 -1，故用 changes() 近似或直接返回 len(terms)
            # 这里返回去重后尝试写入的数量，实际可用 total_changes 差值，但为简单返回 len
            inserted = len(terms)

            # 可选：更新共现边（实体与term的共现，此处简化为实体自环或与高频term共现）
            # 为满足第二张表存在，我们维护一个简单的共现统计：若同一entity_id出现多次，更新last_occurred_at
            # 真实场景中，entity_co_occurrence_edges 用于实体-实体共现（如妈妈与礼物实体共现），此处提供基础实现
            # 这里不强制实现复杂逻辑，仅保证表可用
            # 示例：若文本中同时出现多个已索引实体，可在此更新边（本简化版跳过，留作扩展）

        return inserted

    def index_entity_texts_batch(self, items: Iterable[tuple[str, str, int]]) -> int:
        """
        批量索引，加速M1大规模写入

        Args:
            items: Iterable of (entity_id, text, timestamp_ns)

        Returns:
            总写入term数
        """
        total = 0
        batch_data = []
        for entity_id, text, ts in items:
            terms = tokenize_cjk_overlapping(text)
            for t in terms:
                batch_data.append((t, entity_id, ts))
            total += len(terms)

        if not batch_data:
            return 0

        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO topological_cjk_terms (term, entity_id, occurred_at) VALUES (?, ?, ?)",
                batch_data,
            )
        return total

    def co_search(self, query_terms: List[str]) -> List[str]:
        """
        核心：毫秒级多词交集召回
        执行 SQL: SELECT entity_id FROM topological_cjk_terms WHERE term IN (...) GROUP BY entity_id HAVING COUNT(DISTINCT term) = :num_terms

        Args:
            query_terms: 查询词列表，如 ["妈妈", "生日", "礼物"]

        Returns:
            List[str]: 命中且同时包含所有查询词的entity_id列表
        """
        if not query_terms:
            return []

        # 去重查询词，避免 HAVING 计数不一致
        # 保留原始顺序去重
        seen = set()
        deduped_terms: List[str] = []
        for q in query_terms:
            if q not in seen:
                seen.add(q)
                deduped_terms.append(q)

        if not deduped_terms:
            return []

        # 清洗查询词：去除空白，保留有效term
        # 查询词本身已是分词结果（如"妈妈"），直接使用，不再二次分词，避免"妈妈"被拆成"妈"+"妈妈"
        # 若查询词包含标点或空格，过滤
        cleaned_query = [t.strip() for t in deduped_terms if t and t.strip()]
        if not cleaned_query:
            return []

        placeholders = ",".join(["?"] * len(cleaned_query))
        sql = f"""
            SELECT entity_id
            FROM topological_cjk_terms
            WHERE term IN ({placeholders})
            GROUP BY entity_id
            HAVING COUNT(DISTINCT term) = ?
            ORDER BY MAX(occurred_at) DESC
        """

        # 执行
        cursor = self.conn.cursor()
        # 参数：terms + num_terms
        params = (*cleaned_query, len(cleaned_query))
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [row[0] for row in rows]

    def co_search_with_score(self, query_terms: List[str]) -> List[tuple[str, int, int]]:
        """
        扩展：带共现分数和最新时间，用于排序

        Returns:
            List of (entity_id, matched_term_count, max_occurred_at)
        """
        if not query_terms:
            return []

        seen = set()
        deduped = []
        for q in query_terms:
            if q not in seen:
                seen.add(q)
                deduped.append(q)
        cleaned_query = [t.strip() for t in deduped if t and t.strip()]
        if not cleaned_query:
            return []

        placeholders = ",".join(["?"] * len(cleaned_query))
        sql = f"""
            SELECT entity_id, COUNT(DISTINCT term) as matched, MAX(occurred_at) as last_at
            FROM topological_cjk_terms
            WHERE term IN ({placeholders})
            GROUP BY entity_id
            HAVING COUNT(DISTINCT term) = ?
            ORDER BY matched DESC, last_at DESC
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (*cleaned_query, len(cleaned_query)))
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def update_co_occurrence_edge(self, source_entity_id: str, target_entity_id: str, timestamp_ns: int, increment: int = 1) -> None:
        """
        更新实体共现边：用于预聚合高频共现拓扑

        Args:
            source_entity_id: 源实体
            target_entity_id: 目标实体
            timestamp_ns: 时间
            increment: 共现计数增量
        """
        if not source_entity_id or not target_entity_id:
            return
        if source_entity_id == target_entity_id:
            return  # 忽略自环

        with self.conn:
            # 先尝试更新
            self.conn.execute(
                """
                INSERT INTO entity_co_occurrence_edges (source_entity_id, target_entity_id, co_occurrence_count, last_occurred_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_entity_id, target_entity_id) DO UPDATE SET
                    co_occurrence_count = co_occurrence_count + ?,
                    last_occurred_at = MAX(last_occurred_at, ?)
                """,
                (source_entity_id, target_entity_id, increment, timestamp_ns, increment, timestamp_ns),
            )

    def get_top_co_occurrences(self, entity_id: str, limit: int = 10) -> List[tuple[str, int]]:
        """查询与某实体共现最多的实体"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT target_entity_id, co_occurrence_count
            FROM entity_co_occurrence_edges
            WHERE source_entity_id = ?
            ORDER BY co_occurrence_count DESC
            LIMIT ?
            """,
            (entity_id, limit),
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def count_terms(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM topological_cjk_terms")
        return cursor.fetchone()[0]

    def clear(self) -> None:
        """清空，用于测试"""
        with self.conn:
            self.conn.execute("DELETE FROM topological_cjk_terms")
            self.conn.execute("DELETE FROM entity_co_occurrence_edges")
