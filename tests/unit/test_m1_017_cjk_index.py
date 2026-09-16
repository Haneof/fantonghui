"""
M1-017 CJK 拓扑倒排聚集表与多词检索加速引擎 - 验收单测

必须断言：
- 录入包含“给妈妈买生日礼物”的实体和包含“爸爸喜欢钓鱼”的实体；
- 执行 co_search(["妈妈", "生日", "礼物"])，必须精准返回妈妈实体，绝对不可误召回爸爸实体；
- 检索耗时断言 <= 30ms。
"""

import sqlite3
import time
import pytest

from src.aios_core.query.cjk_inverted_index import (
    CJKTopologicalInvertedIndex,
    tokenize_cjk_overlapping,
    ensure_cjk_schema,
)


def test_tokenize_cjk_overlapping_basic():
    """分词基础：必须包含一元+二元重叠"""
    terms = tokenize_cjk_overlapping("给妈妈买生日礼物")
    # 必须包含查询词
    assert "妈妈" in terms
    assert "生日" in terms
    assert "礼物" in terms
    # 必须包含一元
    assert "妈" in terms
    assert "生" in terms
    # 二元重叠
    assert "给妈" in terms
    assert "妈买" in terms

    # 空输入
    assert tokenize_cjk_overlapping("") == set()
    assert tokenize_cjk_overlapping("   ") == set()

    # 纯标点应为空
    assert tokenize_cjk_overlapping("，。？！") == set()

    # 英文+数字也应保留（isalnum）
    terms_en = tokenize_cjk_overlapping("AIOS 2.0")
    assert "A" in terms_en or "AI" in terms_en or "AIOS" in terms_en or "2" in terms_en


def test_cjk_schema_ddl():
    """DDL自动建表与降序复合索引"""
    conn = sqlite3.connect(":memory:")
    ensure_cjk_schema(conn)

    cursor = conn.cursor()
    # 检查表存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='topological_cjk_terms'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entity_co_occurrence_edges'")
    assert cursor.fetchone() is not None

    # 检查索引存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_cjk_term_occurred'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_co_count'")
    assert cursor.fetchone() is not None

    # 检查主键
    cursor.execute("SELECT sql FROM sqlite_master WHERE name='topological_cjk_terms'")
    sql = cursor.fetchone()[0]
    assert "PRIMARY KEY" in sql
    assert "term" in sql and "entity_id" in sql and "occurred_at" in sql

    conn.close()


def test_cjk_co_search_intersection():
    """
    核心验收：
    - 录入“给妈妈买生日礼物”实体和“爸爸喜欢钓鱼”实体
    - co_search(["妈妈", "生日", "礼物"]) 必须精准返回妈妈实体，绝对不可误召回爸爸实体
    - 检索耗时 <=30ms
    """
    conn = sqlite3.connect(":memory:")
    # 建表由类自动完成
    index = CJKTopologicalInvertedIndex(conn)

    now_ns = 1726400000000000000

    # 录入妈妈实体
    inserted_mom = index.index_entity_text(
        "ent_mom", "给妈妈买生日礼物，妈妈非常喜欢这个礼物", now_ns
    )
    assert inserted_mom > 0

    # 录入爸爸实体
    inserted_dad = index.index_entity_text(
        "ent_dad", "爸爸喜欢钓鱼，送爸爸一个渔具", now_ns
    )
    assert inserted_dad > 0

    # 三词求交集，计时
    start = time.perf_counter()
    hits = index.co_search(["妈妈", "生日", "礼物"])
    elapsed_ms = (time.perf_counter() - start) * 1000

    # 精准返回妈妈实体
    assert "ent_mom" in hits, f"妈妈实体未命中，hits={hits}"
    # 绝对不可误召回爸爸实体
    assert "ent_dad" not in hits, f"误召回爸爸实体，hits={hits}"
    # 仅1个命中
    assert len(hits) == 1, f"应仅命中1个，实际{hits}"

    # 检索耗时 <=30ms（内存库，数据量小，应远低于此）
    assert elapsed_ms <= 30, f"检索耗时超标: {elapsed_ms:.2f}ms > 30ms"

    # 额外：单次查妈妈也应命中
    hits_mom = index.co_search(["妈妈"])
    assert "ent_mom" in hits_mom

    # 查爸爸不应命中妈妈
    hits_dad = index.co_search(["爸爸", "钓鱼"])
    assert "ent_dad" in hits_dad
    assert "ent_mom" not in hits_dad

    # 空查询
    assert index.co_search([]) == []

    # 不存在的词
    assert index.co_search(["不存在的词"]) == []

    conn.close()


def test_cjk_co_search_partial_overlap():
    """部分重叠不应误判为全包含"""
    conn = sqlite3.connect(":memory:")
    index = CJKTopologicalInvertedIndex(conn)
    now_ns = 1726400000000000000

    index.index_entity_text("ent_mom", "给妈妈买生日礼物", now_ns)
    index.index_entity_text("ent_dad", "爸爸喜欢钓鱼", now_ns)

    # 只查2个词，妈妈应命中（因为同时有妈妈+生日）
    hits_2 = index.co_search(["妈妈", "生日"])
    assert "ent_mom" in hits_2
    assert "ent_dad" not in hits_2

    # 查3个词，但爸爸只有爸爸+钓鱼，没有生日礼物，不应命中
    hits_3 = index.co_search(["爸爸", "生日", "礼物"])
    assert "ent_dad" not in hits_3
    assert len(hits_3) == 0

    conn.close()


def test_cjk_co_search_performance_1000_entities():
    """性能压测：1000实体下三词交集仍应 <=30ms"""
    conn = sqlite3.connect(":memory:")
    index = CJKTopologicalInvertedIndex(conn)
    now_ns = 1726400000000000000

    # 批量写入1000实体
    items = []
    for i in range(1000):
        if i == 500:
            text = "给妈妈买生日礼物，妈妈非常喜欢"
            eid = "ent_mom"
        else:
            text = f"实体{i} 随机文本 测试数据 钓鱼 打球 看书"
            eid = f"ent_{i}"
        items.append((eid, text, now_ns + i))

    index.index_entity_texts_batch(items)

    # 计时检索
    start = time.perf_counter()
    hits = index.co_search(["妈妈", "生日", "礼物"])
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert "ent_mom" in hits
    assert elapsed_ms <= 30, f"1000实体下耗时超标: {elapsed_ms:.2f}ms"

    conn.close()


def test_cjk_co_occurrence_edges_table():
    """第二张表 entity_co_occurrence_edges 可用"""
    conn = sqlite3.connect(":memory:")
    index = CJKTopologicalInvertedIndex(conn)
    now_ns = 1726400000000000000

    # 更新共现边
    index.update_co_occurrence_edge("ent_mom", "ent_gift", now_ns, 1)
    index.update_co_occurrence_edge("ent_mom", "ent_gift", now_ns + 1000, 2)

    top = index.get_top_co_occurrences("ent_mom", limit=5)
    assert len(top) == 1
    assert top[0][0] == "ent_gift"
    assert top[0][1] == 3  # 1+2

    conn.close()
