"""M5-005（Agent-10）验收：千人千面 Agent 心智竞技场。

覆盖工单四大点名项：
1. 千人千面发生器：三种人生各自成流，确定性可复现、互不相同；
2. 高智商省 Token vs 低能耗散策略：golden_topo 必须以显著优势压制
   naive_keyword 与 sloppy_brute（命中率 / 预算使用率 / 分寸感三指标）；
3. 铁律一票否决：改写历史 + P0 摇大模型 = 总分归零，反思配额闸必须挡下刷屏；
4. 全景体检报告持久化进经验库并可整卷重载，黄金检索经验蒸馏必须选中拓扑下钻。
"""

from __future__ import annotations

import sqlite3

import pytest

from aios_core.simulation.agent_mind_bench import (
    PERSONAS,
    AgentMindArena,
    AgentPolicy,
    MindPerformanceMetricsRecorder,
    ThousandFacesLifeFactory,
)


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    root = tmp_path_factory.mktemp("m5-arena")
    store = _open_store(root / "arena.db")
    arena = AgentMindArena(store, seed=7)
    reports = arena.run_bench(days=30)
    return arena, store, reports


def _open_store(path):
    from aios_core.storage.sqlite_store import SQLiteWorldStore

    return SQLiteWorldStore(str(path))


# ---------------------------------------------------------------------------
# 1. 千人千面
# ---------------------------------------------------------------------------


def test_thousand_faces_deterministic_and_distinct():
    factory = ThousandFacesLifeFactory(seed=2026)
    by_persona = {}
    for persona in PERSONAS:
        first = factory.build_stream(persona, days=20, events_per_day=5)
        second = factory.build_stream(persona, days=20, events_per_day=5)
        assert [e.event_id for e in first.events] == [e.event_id for e in second.events]
        assert [e.description for e in first.events] == [e.description for e in second.events], "同种子必须逐条可复现"
        by_persona[persona.persona_id] = {e.event_id for e in first.events}
    ids_prog, ids_boss, ids_mom = (by_persona[k] for k in ("prog", "boss", "mom"))
    assert not (ids_prog & ids_boss) and not (ids_boss & ids_mom) and not (ids_prog & ids_mom), "千人千面：不同人生互不混淆"
    with pytest.raises(ValueError, match="至少 7 天"):
        factory.build_stream(PERSONAS[0], days=3)


def test_world_materialization_links_hidden_facts(tmp_path):
    """隐性因果事实必须"有链无词"：物化后 source_ref 指向人生锚实体。"""
    store = _open_store(tmp_path / "w.db")
    factory = ThousandFacesLifeFactory(seed=5)
    persona = PERSONAS[1]  # 创业者·老王
    stream = factory.materialize(store, factory.build_stream(persona, days=10))
    hidden = [e for e in stream.events if e.event_id.endswith("_hidden")]
    assert hidden and all(persona.hidden_crisis_fact == e.description for e in hidden)
    payloads = {p["object_id"]: p for p in store.list_payloads()}
    ent = payloads[persona.anchor_entity_id]
    assert ent["canonical_name"] == "老王"
    for e in hidden:
        p = payloads[e.event_id]
        assert all(k not in p["value"] for k in ("借款", "诈骗", "早搏", "跌倒")), "隐性事实不得含危机关键词"
        assert any(r["object_id"] == persona.anchor_entity_id for r in p["source_refs"])


# ---------------------------------------------------------------------------
# 2/3. 记分牌：高智商省 Token 完胜低能耗散，违宪一票否决
# ---------------------------------------------------------------------------


def test_golden_agent_beats_naive_and_brute(bench):
    _arena, _store, reports = bench
    assert len(reports) == 3
    for r in reports:
        golden = r.card_for(AgentPolicy.golden().name)
        naive = r.card_for(AgentPolicy.naive().name)
        sloppy = r.card_for(AgentPolicy.sloppy().name)
        assert golden.retrieval_mean_recall == 1.0, f"{r.persona_id}: 拓扑路必须全量命中（含隐性事实与今日注记）"
        assert naive.retrieval_mean_recall < 0.9, "朴素关键词路必须暴露结构性漏检"
        assert sloppy.tokens_spent > 20 * golden.tokens_spent, "暴力全扫 Token 必须呈数量级劣势"
        assert sloppy.budget_usage_rate > 5.0, "低能耗散策略必须把预算用爆"
        assert golden.overall_score > naive.overall_score > sloppy.overall_score
        assert r.winner_policy == AgentPolicy.golden().name


def test_propriety_and_iron_rule_veto(bench):
    _arena, _store, reports = bench
    for r in reports:
        golden = r.card_for(AgentPolicy.golden().name)
        sloppy = r.card_for(AgentPolicy.sloppy().name)
        assert golden.silence_rate >= 0.8, "日常琐事沉默是金：≥80%"
        assert golden.crisis_expectation_match_rate == 1.0, "老王借款/深夜早搏等该开口处必须果断直言，该沉默处不许聒噪"
        assert golden.iron_rules_ok and golden.overall_score > 0
        assert not sloppy.iron_rules_ok and sloppy.overall_score == 0, "违宪一票否决：总分直接归零"
        reasons = "|".join(sloppy.veto_reasons)
        assert "改写历史" in reasons and "大模型" in reasons
        assert sloppy.quota_guard_activations >= 1 and golden.quota_guard_activations == 0, "每日 1 次反思配额必须拦下刷屏"


def test_high_order_dimension_mounted_per_persona(bench):
    _arena, _store, reports = bench
    expected = {"prog": "DIM_BURNOUT_RISK", "boss": "DIM_CREDIT_RISK", "mom": "DIM_PARENT_HEALTH"}
    for r in reports:
        golden = r.card_for(AgentPolicy.golden().name)
        assert expected[r.persona_id] in golden.mounted_dimensions, f"{r.persona_id} 应按各自人生提炼专属高阶维度"
        assert golden.distill_promotions >= 1


def test_advice_always_evidence_backed(bench):
    _arena, _store, reports = bench
    for r in reports:
        golden = r.card_for(AgentPolicy.golden().name)
        assert golden.advice_count >= 3, "送礼/防诈/健康熔断顾问都必须真上场"
        assert golden.advice_evidence_backed == golden.advice_count, "确凿 ObjectRef 证据是铁律，无证据即违宪"


# ---------------------------------------------------------------------------
# 4. 体检报告：入经验库、可重载、黄金经验锁定拓扑
# ---------------------------------------------------------------------------


def test_reports_persisted_and_distilled_topo(bench):
    arena, store, reports = bench
    with sqlite3.connect(store.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM agent_mind_diagnostic_reports").fetchone()[0]
    assert n == 3
    for r in reports:
        loaded = arena.load_report(r.report_id)
        assert loaded.persona_id == r.persona_id and loaded.winner_policy == r.winner_policy
        assert [c.model_dump() for c in loaded.cards] == [c.model_dump() for c in r.cards]
        assert loaded.persisted_at, "报告必须带落库时间戳"
        assert r.distilled_preferred_pathway == "hierarchical_topo", "竞技场实测后蒸馏必须锁定拓扑分级下钻"
        assert 0 < r.distilled_expected_tokens <= 500, f"黄金策略预算越闸：{r.distilled_expected_tokens}"
    with pytest.raises(KeyError):
        arena.load_report("amr_not_exists_00000000")


def test_recorder_token_accounting_sanity():
    rec = MindPerformanceMetricsRecorder(token_budget=100)
    rec.spend(40)
    with pytest.raises(ValueError, match="negative"):
        rec.spend(-1)
    rec.note_trivial(True)
    rec.note_trivial(False)
    rec.note_crisis(True, 1.0, True)
    rec.note_crisis(False, 0.5, False)
    assert rec.silence_rate == 0.5 and rec.crisis_expectation_match_rate == 1.0
    assert rec.retrieval_mean_recall == 0.75 and rec.budget_usage_rate == 0.4
    rec.log_action("llm_call_on_p0", scenario="x")
    assert any("大模型" in v for v in rec.violations)
