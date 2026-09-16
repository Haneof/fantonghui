"""Agent-06 / M5-SEARCH：三路径对比执行器 + 黄金经验蒸馏 单测。

验收点：A 暴力扫描落 15k~50k 区间（对照价值）；C 拓扑下钻 100% 准确且
战役 Token ≤500；单次命中简报 ≤150；3 战役后蒸馏固化；反例自动降级。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios_core.cognition.operation_experience import (
    CAMPAIGN_TOKEN_BUDGET,
    DistillerNotReadyError,
    ExperienceDemotedError,
    OperationExperienceDistiller,
)
from aios_core.query.search import (
    SINGLE_HIT_TOKEN_CAP,
    MindRecord,
    MultidimensionalSearchEngine,
    SearchPathway,
    SearchQuery,
)

UTC = timezone.utc
T0 = datetime(2023, 1, 1, tzinfo=UTC)


def _build_world() -> tuple[MultidimensionalSearchEngine, SearchQuery, list[str]]:
    engine = MultidimensionalSearchEngine()
    # 填充世界：400 条干扰维度（每条 ~40 token）→ 暴力扫描 ≈ 16k+ tokens
    for i in range(400):
        engine.register(MindRecord(
            record_id=f"dim_noise_{i:03d}",
            record_type="dimension",
            keywords=("生活流",),
            content=f"第{i}周生活记录：采购日用与例行开销，偶尔讨论健康话题与家庭安排" * 2,
            occurred_at=T0,
        ))
    truth_ids = []
    rows = (
        ("2023", "丝巾", "2023 母亲节送丝巾，妈妈礼貌收下后收进柜子"),
        ("2024", "足浴盆", "2024 足浴盆闲置吃灰，妈妈倒水时闪了腰"),
        ("2025", "按摩椅", "2025 按摩椅是唯一获好评并被天天使用的家电"),
        ("2026", "膝盖", "2026 入秋妈妈膝盖受凉，适合轻便膝盖热敷仪"),
    )
    for year, kw, text in rows:
        rid = f"ann_gift_{year}"
        engine.register(MindRecord(
            record_id=rid,
            record_type="annotation",
            keywords=("妈妈", "礼物", kw, "热敷" if year == "2026" else "礼品"),
            content=text,
            occurred_at=T0,
            ground_truth=True,
        ))
        truth_ids.append(rid)
    # 同名干扰（只含"妈妈"，无"膝盖/热敷"共现）
    for i in range(3):
        engine.register(MindRecord(
            record_id=f"ann_noise_{i}",
            record_type="annotation",
            keywords=("妈妈",),
            content=f"社区群里其他妈妈团购水果的闲聊记录第{i}条",
            occurred_at=T0,
        ))
    query = SearchQuery(
        problem_type="mom_gift_history",
        keywords=("妈妈", "礼物"),   # 共现链：证据链四年均含此二词
        entity_hint="妈妈",
        record_types=("annotation", "dimension", "claim", "entity"),
    )
    return engine, query, truth_ids


def test_brute_scan_cost_lands_in_reference_band() -> None:
    engine, query, truth = _build_world()
    result = engine.run_pathway(query, SearchPathway.BRUTE_SCAN)
    assert 15_000 <= result.tokens_spent <= 50_000


def test_topological_drill_is_exact_and_lean() -> None:
    engine, query, truth = _build_world()
    result = engine.run_pathway(query, SearchPathway.TOPOLOGICAL_DRILL)
    assert set(result.hit_ids) == set(truth)
    assert result.tokens_spent <= CAMPAIGN_TOKEN_BUDGET
    for brief in result.briefs:
        assert brief.token_cost <= SINGLE_HIT_TOKEN_CAP


def test_naive_keyword_over_matches_distractors() -> None:
    engine, query, truth = _build_world()
    stats = engine.compare_pathways(query, expected_hit_ids=truth).by(
        SearchPathway.NAIVE_KEYWORD
    )
    assert stats.false_positives > 0
    assert stats.accuracy < 1.0


def test_compare_adjudicates_topological_as_winner() -> None:
    engine, query, truth = _build_world()
    comparison = engine.compare_pathways(query, expected_hit_ids=truth)
    assert comparison.winner is SearchPathway.TOPOLOGICAL_DRILL


def test_distiller_requires_three_campaigns() -> None:
    engine, query, truth = _build_world()
    distiller = OperationExperienceDistiller(engine)
    with pytest.raises(DistillerNotReadyError):
        distiller.distill("mom_gift_history", at=T0)
    distiller.run_campaign(query, expected_hit_ids=truth, at=T0)
    distiller.run_campaign(query, expected_hit_ids=truth, at=T0)
    with pytest.raises(DistillerNotReadyError):
        distiller.distill("mom_gift_history", at=T0)


def test_golden_experience_compresses_campaign_under_500() -> None:
    engine, query, truth = _build_world()
    distiller = OperationExperienceDistiller(engine)
    for _ in range(3):
        distiller.run_campaign(query, expected_hit_ids=truth, at=T0)
    golden = distiller.distill("mom_gift_history", at=T0)
    assert golden.golden_pathway is SearchPathway.TOPOLOGICAL_DRILL
    assert golden.expected_accuracy == 1.0
    assert golden.is_golden
    # 经验直取：100% 命中 + 战役成本 ≤500（对比暴力 15k+ → 压缩 ~300 倍）
    result = distiller.run_by_experience(query, expected_hit_ids=truth, at=T0)
    assert set(result.hit_ids) == set(truth)
    assert result.tokens_spent <= CAMPAIGN_TOKEN_BUDGET
    assert golden.expected_tokens <= CAMPAIGN_TOKEN_BUDGET


def test_counterexample_demotes_golden_experience() -> None:
    engine, query, truth = _build_world()
    distiller = OperationExperienceDistiller(engine)
    for _ in range(3):
        distiller.run_campaign(query, expected_hit_ids=truth, at=T0)
    distiller.distill("mom_gift_history", at=T0)
    # 反例：期望命中一个不存在的记录 → 准确率 <100% → 自动降级
    with pytest.raises(ExperienceDemotedError):
        distiller.run_by_experience(
            query, expected_hit_ids=[*truth, "ann_ghost"], at=T0
        )
    experience = distiller.experience_for("mom_gift_history")
    assert experience is not None and not experience.is_golden
    assert "counterexample" in experience.demote_reason
    with pytest.raises(ExperienceDemotedError):
        distiller.run_by_experience(query, expected_hit_ids=truth, at=T0)
