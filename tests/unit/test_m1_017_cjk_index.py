"""M1-017 CJK 拓扑倒排索引与多词共现求交引擎单测。

对应工单 `governance/dispatches/TASK_DISPATCH_AGENT_2_M1_017.md` §3 验收标准，
并额外覆盖参考实现中被修正的三处缺陷（标点混入词元、查询词未去重、
三字以上查询词无法命中）。
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from aios_core.query.cjk_inverted_index import (
    MAX_QUERY_TERMS,
    CJKTopologicalInvertedIndex,
    tokenize_cjk_overlapping,
)

NOW_NS = 1_726_400_000_000_000_000


@pytest.fixture
def index() -> CJKTopologicalInvertedIndex:
    conn = sqlite3.connect(":memory:")
    try:
        yield CJKTopologicalInvertedIndex(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 工单 §3 指定验收
# ---------------------------------------------------------------------------


def test_cjk_co_search_intersection(index: CJKTopologicalInvertedIndex) -> None:
    """工单原文验收：三词求交必须精准命中妈妈实体，绝不误召回爸爸实体。"""
    index.index_entity_text("ent_mom", "给妈妈买生日礼物，妈妈非常喜欢这个礼物", NOW_NS)
    index.index_entity_text("ent_dad", "爸爸喜欢钓鱼，送爸爸一个渔具", NOW_NS)

    hits = index.co_search(["妈妈", "生日", "礼物"])

    assert "ent_mom" in hits
    assert "ent_dad" not in hits
    assert len(hits) == 1


def test_co_search_latency_within_30ms(index: CJKTopologicalInvertedIndex) -> None:
    """工单验收：检索耗时 <= 30ms。"""
    index.index_entity_text("ent_mom", "给妈妈买生日礼物，妈妈非常喜欢这个礼物", NOW_NS)
    index.index_entity_text("ent_dad", "爸爸喜欢钓鱼，送爸爸一个渔具", NOW_NS)

    started = time.perf_counter()
    hits = index.co_search(["妈妈", "生日", "礼物"])
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert hits == ["ent_mom"]
    assert elapsed_ms <= 30.0, f"co_search 耗时 {elapsed_ms:.3f}ms 超过 30ms 上限"


def test_default_fts5_cannot_tokenize_chinese() -> None:
    """坐实痛点：SQLite 默认 FTS5 对连续中文命中 0 行——本模块存在的理由。"""
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
        conn.execute("INSERT INTO t(body) VALUES ('给妈妈买生日礼物')")
        conn.commit()
        for keyword in ("妈妈", "生日", "礼物"):
            count = conn.execute(
                "SELECT COUNT(*) FROM t WHERE t MATCH ?", (keyword,)
            ).fetchone()[0]
            assert count == 0, f"unicode61 竟命中了 {keyword}，与本模块前提矛盾"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 切分器
# ---------------------------------------------------------------------------


def test_tokenize_emits_unigrams_and_overlapping_bigrams() -> None:
    terms = tokenize_cjk_overlapping("妈妈生日")
    assert {"妈", "生", "日"} <= terms  # 一元（集合去重）
    assert {"妈妈", "妈生", "生日"} <= terms  # 二元重叠


def test_tokenize_treats_punctuation_as_separator() -> None:
    """标点必须切句，不得产出跨句垃圾词元（修正工单参考实现）。"""
    terms = tokenize_cjk_overlapping("给妈妈买生日礼物，妈妈非常喜欢这个礼物")

    assert "，" not in terms
    assert "物，" not in terms
    assert "，妈" not in terms
    # 两句各自内部的二元词仍然在
    assert "礼物" in terms and "妈妈" in terms


def test_tokenize_keeps_latin_run_as_whole_token() -> None:
    terms = tokenize_cjk_overlapping("买了 iPhone 送给妈妈")
    assert "iphone" in terms
    assert "妈妈" in terms


def test_tokenize_empty_and_punctuation_only() -> None:
    assert tokenize_cjk_overlapping("") == set()
    assert tokenize_cjk_overlapping("，。？！") == set()


# ---------------------------------------------------------------------------
# 查询规范化（修正的两处缺陷）
# ---------------------------------------------------------------------------


def test_duplicate_query_terms_do_not_break_intersection(
    index: CJKTopologicalInvertedIndex,
) -> None:
    """参考实现用 len(query_terms) 作 HAVING 阈值，重复词会导致永远返回空。"""
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)

    assert index.co_search(["妈妈", "妈妈", "生日"]) == ["ent_mom"]


def test_multi_char_query_term_is_expanded(index: CJKTopologicalInvertedIndex) -> None:
    """索引只有一元/二元词，三字以上查询词必须经同一切分器展开。"""
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)
    index.index_entity_text("ent_dad", "爸爸喜欢钓鱼", NOW_NS)

    assert index.co_search(["妈妈", "生日礼物"]) == ["ent_mom"]


def test_empty_query_returns_empty(index: CJKTopologicalInvertedIndex) -> None:
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)
    assert index.co_search([]) == []
    assert index.co_search(["，。"]) == []


def test_partial_overlap_is_not_recalled(index: CJKTopologicalInvertedIndex) -> None:
    """只命中 2/3 个查询词的实体不得进入严格求交结果。"""
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)
    index.index_entity_text("ent_partial", "妈妈提到过生日", NOW_NS)

    hits = index.co_search(["妈妈", "生日", "礼物"])
    assert hits == ["ent_mom"]

    relaxed = index.partial_search(["妈妈", "生日", "礼物"], min_matched=2)
    assert {h.entity_id for h in relaxed} == {"ent_mom", "ent_partial"}


def test_too_many_query_terms_rejected(index: CJKTopologicalInvertedIndex) -> None:
    with pytest.raises(ValueError, match="too many query terms"):
        index.co_search([f"词{i}" for i in range(MAX_QUERY_TERMS + 1)])


def test_blank_query_term_rejected(index: CJKTopologicalInvertedIndex) -> None:
    with pytest.raises(ValueError, match="non-blank"):
        index.co_search(["妈妈", "  "])


# ---------------------------------------------------------------------------
# 写入 / 修订 / 幂等
# ---------------------------------------------------------------------------


def test_index_is_idempotent_for_same_timestamp(
    index: CJKTopologicalInvertedIndex,
) -> None:
    text = "给妈妈买生日礼物"
    first = index.index_entity_text("ent_mom", text, NOW_NS)
    second = index.index_entity_text("ent_mom", text, NOW_NS)

    assert first == second
    assert index.stats()["postings_rows"] == first


def test_reindex_removes_stale_terms(index: CJKTopologicalInvertedIndex) -> None:
    """实体文本修订后，旧词元不得残留成幽灵召回。"""
    index.index_entity_text("ent_x", "妈妈喜欢钓鱼", NOW_NS)
    assert index.co_search(["钓鱼"]) == ["ent_x"]

    index.reindex_entity_text("ent_x", "妈妈喜欢园艺", NOW_NS + 1)

    assert index.co_search(["钓鱼"]) == []
    assert index.co_search(["园艺"]) == ["ent_x"]


def test_delete_entity_terms(index: CJKTopologicalInvertedIndex) -> None:
    index.index_entity_text("ent_x", "妈妈喜欢钓鱼", NOW_NS)
    removed = index.delete_entity_terms("ent_x")

    assert removed > 0
    assert index.co_search(["妈妈"]) == []
    assert index.stats()["distinct_entities"] == 0


def test_index_many_batches(index: CJKTopologicalInvertedIndex) -> None:
    written = index.index_many(
        [
            ("ent_mom", "给妈妈买生日礼物", NOW_NS),
            ("ent_dad", "爸爸喜欢钓鱼", NOW_NS),
        ]
    )
    assert written > 0
    assert index.co_search(["妈妈", "生日", "礼物"]) == ["ent_mom"]


@pytest.mark.parametrize(
    ("entity_id", "timestamp_ns", "exc"),
    [
        ("  ", NOW_NS, ValueError),
        ("ent_x", -1, ValueError),
        ("ent_x", "not-an-int", TypeError),
        ("ent_x", True, TypeError),
    ],
)
def test_index_input_validation(
    index: CJKTopologicalInvertedIndex,
    entity_id: str,
    timestamp_ns: object,
    exc: type[Exception],
) -> None:
    with pytest.raises(exc):
        index.index_entity_text(entity_id, "妈妈生日", timestamp_ns)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 排序 / 诊断 / 共现拓扑 / 可观测性
# ---------------------------------------------------------------------------


def test_co_search_scored_orders_by_recency_and_limits(
    index: CJKTopologicalInvertedIndex,
) -> None:
    index.index_entity_text("ent_old", "妈妈生日礼物", NOW_NS)
    index.index_entity_text("ent_new", "妈妈生日礼物", NOW_NS + 1_000)

    hits = index.co_search_scored(["妈妈", "生日", "礼物"], limit=1)

    assert len(hits) == 1
    assert hits[0].entity_id == "ent_new"
    # 查询规范化后 len(required) == HAVING 阈值，故 matched_terms 就是
    # "命中了几个查询词"，可直接用于 top-k 排序。
    assert hits[0].matched_terms == 3


def test_explain_reports_postings_per_term(index: CJKTopologicalInvertedIndex) -> None:
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)
    index.index_entity_text("ent_dad", "爸爸喜欢钓鱼", NOW_NS)

    counts = index.explain(["妈妈", "钓鱼", "火箭"])

    assert counts["妈妈"] == 1
    assert counts["钓鱼"] == 1
    assert counts["火箭"] == 0


def test_co_occurrence_edges_are_maintained(index: CJKTopologicalInvertedIndex) -> None:
    """工单要求建 entity_co_occurrence_edges，必须有写入与读取路径。"""
    index.record_co_occurrence(["ent_mom", "ent_dad", "ent_kid"], NOW_NS)
    index.record_co_occurrence(["ent_mom", "ent_dad"], NOW_NS + 1)

    top = index.top_co_occurrence("ent_mom")
    # 边按 (min, max) 归一存储，查询实体可能落在任一侧，用 neighbor() 取对端。
    assert top[0].neighbor("ent_mom") == "ent_dad"
    assert top[0].co_occurrence_count == 2
    assert index.stats()["co_occurrence_edges"] == 3


def test_record_co_occurrence_normalises_pair_direction(
    index: CJKTopologicalInvertedIndex,
) -> None:
    index.record_co_occurrence(["a", "b"], NOW_NS)
    index.record_co_occurrence(["b", "a"], NOW_NS)
    assert index.stats()["co_occurrence_edges"] == 1


def test_stats_reports_index_scale(index: CJKTopologicalInvertedIndex) -> None:
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)
    stats = index.stats()

    assert stats["distinct_entities"] == 1
    assert stats["postings_rows"] > 0
    assert stats["distinct_terms"] > 0


def test_ensure_schema_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        idx = CJKTopologicalInvertedIndex(conn)
        idx.ensure_schema()
        idx.ensure_schema()
        idx.index_entity_text("ent_mom", "妈妈生日", NOW_NS)
        assert idx.co_search(["妈妈"]) == ["ent_mom"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 规模基准：验证"毫秒级"在真实数据量下仍成立
# ---------------------------------------------------------------------------


def test_co_search_at_scale_stays_under_30ms() -> None:
    """2 万实体 / 约 60 万倒排行规模下，三词求交仍须 <= 30ms。

    这是 M1-023 检索规模门的缩小版；完整 100 万行门在 M1-023 单独跑。
    """
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA synchronous = OFF")
        idx = CJKTopologicalInvertedIndex(conn)

        base = "今天去了公司开会讨论项目进度然后回家做饭休息"
        rows = [(f"ent_{i}", f"{base}编号{i}", NOW_NS + i) for i in range(20_000)]
        idx.index_many(rows)
        # 只有少数实体真正含目标三词
        idx.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)
        idx.index_entity_text("ent_decoy", "妈妈提到过生日", NOW_NS + 1)

        stats = idx.stats()
        assert stats["postings_rows"] > 100_000

        started = time.perf_counter()
        hits = idx.co_search(["妈妈", "生日", "礼物"])
        elapsed_ms = (time.perf_counter() - started) * 1000

        assert hits == ["ent_mom"]
        assert elapsed_ms <= 30.0, (
            f"20k 实体 / {stats['postings_rows']} 行倒排下 co_search "
            f"耗时 {elapsed_ms:.3f}ms，超过 30ms"
        )
    finally:
        conn.close()


def test_latin_query_is_case_insensitive(index: CJKTopologicalInvertedIndex) -> None:
    """索引侧与查询侧同用小写规则，拉丁词元大小写不敏感。"""
    index.index_entity_text("ent_phone", "买了 iPhone 送给妈妈", NOW_NS)

    assert index.co_search(["IPHONE"]) == ["ent_phone"]
    assert index.co_search(["iphone"]) == ["ent_phone"]


def test_matched_terms_counts_query_terms_not_sub_tokens(
    index: CJKTopologicalInvertedIndex,
) -> None:
    """展开只产出有判别力的词元，matched_terms 不被一元词污染。"""
    index.index_entity_text("ent_mom", "给妈妈买生日礼物", NOW_NS)

    hits = index.co_search_scored(["妈妈", "生日", "礼物"])
    assert len(hits) == 1
    assert hits[0].matched_terms == 3

    single = index.co_search_scored(["妈妈"])
    assert single[0].matched_terms == 1


def test_neighbor_rejects_foreign_entity(index: CJKTopologicalInvertedIndex) -> None:
    index.record_co_occurrence(["ent_a", "ent_b"], NOW_NS)
    edge = index.top_co_occurrence("ent_a")[0]

    with pytest.raises(ValueError, match="not an endpoint"):
        edge.neighbor("ent_zzz")


def test_index_many_validates_each_item(index: CJKTopologicalInvertedIndex) -> None:
    with pytest.raises(ValueError, match="entity_id must not be blank"):
        index.index_many([("ent_ok", "妈妈", NOW_NS), ("  ", "生日", NOW_NS)])
    with pytest.raises(ValueError, match="timestamp_ns must be >= 0"):
        index.index_many([("ent_ok", "妈妈", -5)])
