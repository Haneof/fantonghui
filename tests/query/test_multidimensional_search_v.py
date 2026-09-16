# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-001 多维搜索底座验收（工单 #6 §3）。

  * 联合检索：Dimension × Entity × CJK Bi-gram × 时空窗 全切面 ∧ 语义
  * 单次多维联合检索耗时 ≤ 20ms
  * 今天挂载的外挂注记 100% 召回
  * 与 co_search 100% 向下兼容（行为面分毫不动）
  * Token 封套：单页 ≤150 硬顶，溢出只记数不偷运
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.enums import ClaimType, KnowledgeState, ObjectType
from aios_core.contracts.models import Claim
from aios_core.contracts.models import Reinterpretation
from aios_core.contracts.time import TemporalExtent
from aios_core.contracts.enums import AnnotationSlot
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.query.search_m5 import (
    PAGE_TOKEN_BUDGET,
    MultidimensionalSearchEngine,
    derive_dimension,
)
from aios_core.operations.world_operator_m5 import WorldOperatorSuite
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

T0 = datetime(2026, 9, 16, 8, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path) -> SQLiteWorldStore:
    return SQLiteWorldStore(tmp_path / "world.db")


def _commit(store, obj, key: str) -> None:
    store.commit([obj], OperationRequest(
        operation_id=f"m5-{key}", operation_name="world.commit",
        expected_world_revision=store.current_world_revision(),
        reason="seed", idempotency_key=f"m5-{key}"))


def _claim(oid: str, content: str, at: datetime, subject: str = "director") -> Claim:
    return Claim(
        object_id=oid,
        claimant_id=subject,
        claim_type=ClaimType.FACT,
        content=content,
        asserted_at=at,
        knowledge_state=KnowledgeState.OBSERVED,
        confidence=0.9,
        **world_kwargs(subject_id=subject, learned_at=at, recorded_at=at),
    )


def _annotation(oid: str, anchor_oid: str, at: datetime, overlay: dict) -> Reinterpretation:
    """今天挂载的外挂注记（新典 Reinterpretation：target_ref pinned 到 revision）。"""
    return Reinterpretation(
        object_id=oid,
        target_ref=ObjectRef(object_id=anchor_oid, revision=1),
        slot=AnnotationSlot.MEANING,
        statement=overlay["overlay"],
        confidence=0.95,
        evidence_set_ref=ObjectRef(object_id=anchor_oid, revision=1),
        valid_time=TemporalExtent(
            start=T0 - timedelta(days=400), end=T0 - timedelta(days=1)
        ),
        **world_kwargs(subject_id="director", learned_at=at, recorded_at=at),
    )


def _seed_corpus(store: SQLiteWorldStore) -> None:
    from aios_core.contracts.models import Entity

    _commit(store, Entity(object_id="ent-laowang", entity_kind="person",
                          canonical_name="王建国", aliases=["老王"],
                          **world_kwargs(subject_id="director",
                                         learned_at=T0 - timedelta(days=30),
                                         recorded_at=T0 - timedelta(days=30))), "e0")
    _commit(store, _claim("c-hr-1", "连续三天深夜间心率骤升到 98bpm，疑似过劳", T0 - timedelta(hours=3)), "c1")
    _commit(store, _claim("c-legal-1", "与王建国的股权回购合同进入对赌条款复核", T0 - timedelta(days=2)), "c2")
    _commit(store, _claim("c-mom-1", "母亲上周说膝盖受凉，上下楼费力", T0 - timedelta(days=1)), "c3")
    _commit(store, _claim("c-noise-1", "今天午饭吃了拉面", T0 - timedelta(hours=1)), "c4")
    _commit(store, _annotation(
        "ra-laowang", "c-legal-1", T0,
        {"overlay": "司法证明王建国设立离岸壳公司，全部合作记录需重估"},
    ), "ra1")


# ---------------------------------------------------------------------------
# 联合检索切面
# ---------------------------------------------------------------------------


def test_derive_dimension_deterministic_rules():
    assert derive_dimension({"content": "心率骤升"}, "claim") == "DIM_BODY_VITALS"
    assert derive_dimension({"content": "对赌条款复核"}, "claim") == "DIM_CAREER_LEGAL"
    assert derive_dimension({"content": "母亲膝盖"}, "claim") == "DIM_FAMILY_PARENTS"
    assert derive_dimension({"content": "无提示文本"}, "claim") == "DIM_GENERAL"
    assert derive_dimension({}, "manifest_instance") == "DIM_AI_SELF_COGNITION"
    # 跨 object_type 同 payload 同结论（类型优先序稳定）
    assert derive_dimension({"content": "心率"}, "event") == "DIM_BODY_VITALS"


def test_joint_query_hits_exactly_right_slice(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()

    page = engine.search_mind(keywords=["心率"], dimension="DIM_BODY_VITALS")
    assert [h.object_id for h in page.hits] == ["c-hr-1"]

    page2 = engine.search_mind(keywords=["王建国"], dimension="DIM_CAREER_LEGAL")
    assert [h.object_id for h in page2.hits] == ["c-legal-1"]

    none_page = engine.search_mind(keywords=["心率"], dimension="DIM_CAREER_LEGAL")
    assert none_page.hits == [], "维度切面 ∧ 语义：错维度一律不命中"


def test_entity_and_time_window_facets(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()

    # 主体实体切面：subject_id 进实体集；锚点 refs 也进实体集
    page = engine.search_mind(entity_id="director")
    ids = {h.object_id for h in page.hits}
    assert {"c-hr-1", "c-legal-1", "c-mom-1", "c-noise-1", "ra-laowang"} <= ids

    anchor_page = engine.search_mind(entity_id="c-legal-1")
    assert "ra-laowang" in {h.object_id for h in anchor_page.hits}, "外挂注记必须能被锚点实体拉出"

    recent = engine.search_mind(time_range=(T0 - timedelta(hours=4), T0 + timedelta(hours=1)))
    recent_ids = {h.object_id for h in recent.hits}
    assert "c-hr-1" in recent_ids and "c-legal-1" not in recent_ids


def test_cjk_bigram_decomposition_matches_double_char_word(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()
    # “妈妈”式双字中文词：bi-gram 分解后仍可命中“母亲”语料（按分解路径）
    page = engine.search_mind(keywords=["母亲"])
    assert "c-mom-1" in {h.object_id for h in page.hits}


def test_joint_query_latency_under_20ms(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()
    samples = []
    for _ in range(25):
        t0 = time.perf_counter()
        engine.search_mind(keywords=["心率"], dimension="DIM_BODY_VITALS",
                           time_range=(T0 - timedelta(days=7), T0))
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 <= 20.0, f"联合检索 p95={p95:.2f}ms 越 20ms 红线"


# ---------------------------------------------------------------------------
# 外挂注记 100% 召回（今天挂载）
# ---------------------------------------------------------------------------


def test_todays_annotations_recalled_at_100_percent(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    _commit(store, _annotation(
        "ra-second", "c-mom-1", T0 + timedelta(minutes=5),
        {"overlay": "母亲体检报告显示骨质疏松趋势"},
    ), "ra2")
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()

    day_start = T0.replace(hour=0, minute=0, second=0, microsecond=0)
    notes = engine.annotations_of_today(day_start)
    assert len(notes) == 2, "今天挂载的注记一条不漏"
    assert {n["annotation_id"] for n in notes} == {"ra-laowang", "ra-second"}
    assert any("司法证明" in n["overlay_text"] for n in notes)
    assert any("骨质疏松" in n["overlay_text"] for n in notes)


# ---------------------------------------------------------------------------
# Token 封套与水位诚实
# ---------------------------------------------------------------------------


def test_token_envelope_hard_capped_at_150(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    for i in range(40):
        _commit(store, _claim(f"c-flood-{i}", f"过劳 心率 记录 {i} " + "补" * 60,
                              T0 - timedelta(minutes=i)), f"f{i}")
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()
    page = engine.search_mind(keywords=["过劳"], dimension="DIM_BODY_VITALS", limit=40)
    assert page.token_estimate <= PAGE_TOKEN_BUDGET == 150
    assert page.overflow_count > 0, "溢出必须显式记数，不是静默砍断"
    assert page.token_budget == 150


def test_watermark_lag_is_honest(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    engine = MultidimensionalSearchEngine(store)
    page_before = engine.search_mind()
    assert page_before.indexed_rev == 0 and page_before.lag == page_before.world_rev
    engine.catch_up()
    page_after = engine.search_mind()
    assert page_after.lag == 0, "catch_up 后水位必须归零（不装新鲜）"


# ---------------------------------------------------------------------------
# 驾驶舱算子与 co_search 兼容
# ---------------------------------------------------------------------------


def test_world_operator_suite_envelope(tmp_path):
    store = _store(tmp_path)
    _seed_corpus(store)
    engine = MultidimensionalSearchEngine(store)
    engine.catch_up()
    suite = WorldOperatorSuite(engine)
    env = suite.search.execute(keywords=["心率"], dimension="DIM_BODY_VITALS")
    assert env.within_envelope and env.tokens_used <= 150
    assert env.page.hits[0].object_id == "c-hr-1"
    desc = suite.describe()
    assert desc["search_token_budget"] == 150


def test_co_search_backward_compat_unbroken(tmp_path):
    """100% 向下兼容：同语料下 co_search 引擎行为面与搜索结果互不干扰。"""
    from aios_core.services.alias_dictionary import AliasDictionaryService
    from aios_core.services.co_search import CoSearchEngine
    from aios_core.services.search_index_worker import SearchIndexWorker

    store = _store(tmp_path)
    _seed_corpus(store)
    page = MultidimensionalSearchEngine(store)
    page.catch_up()

    dictsvc = AliasDictionaryService(store)
    indexer = SearchIndexWorker(store, dictsvc)
    indexer.rebuild()
    co = CoSearchEngine(store, dictsvc, indexer, policy={
        "co_search": {"zero_hit_fail_loud_for_seed_terms": False}
    })
    result = co.query(["王建国"], ensure_fresh=True)
    assert result.total_hits > 0, "co_search 在多维索引落地后照常工作"
    mind_page = page.search_mind(keywords=["王建国"])
    assert "c-legal-1" in {h.object_id for h in mind_page.hits}
    assert {h.object_id for h in result.hits} >= {"c-legal-1"}, "两引擎同语料同词命中同真值"
