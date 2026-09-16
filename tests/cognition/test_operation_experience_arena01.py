# -*- coding: utf-8 -*-
"""Agent-06 / M5-SEARCH 三大检索路径对比与黄金经验蒸馏 · 验收测试（arena01 线）

硬门禁：
- 三路径在同一查询上结论 100% 一致（准确率）；
- Pathway A 暴力全盘扫描 Token 成本落在 15,000~50,000 的设定区间；
- Pathway C 拓扑分级下钻 ≤500 Token，黄金蒸馏直达 ≤500 且单次命中 ≤150；
- 经验库 JSONL 只追加持久化、跨进程可读。
"""

from pathlib import Path

import pytest

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.query.search_arena01 import (
    ExperiencePool,
    MultidimensionalSearchBus,
    OperationExperienceDistiller,
    PathwayComparisonExecutor,
    SearchDocument,
    DISTILL_TARGET_TOKENS,
    MIN_OBSERVATIONS_FOR_GOLD,
    TOKEN_HIT_SOFT_CAP,
)

GOLD_IDS = ("legal-breach-notice", "legal-board-decision")
QUERY = ("老王", "违约", "对赌", "回购")


def _build_bus() -> MultidimensionalSearchBus:
    bus = MultidimensionalSearchBus()
    noise_vocab = ("采购", "审计", "备货", "巡检", "排产", "折旧", "盘点", "仓储")
    for i in range(398):
        topic = noise_vocab[i % len(noise_vocab)]
        text = (
            f"{topic}台账第{i + 1}号：环比合规，留存单据{ (i % 7) + 2 }份，"
            f"复核签章齐备；季度{noise_vocab[(i + 3) % len(noise_vocab)]}滚动计划已发布。"
        )
        bus.add(SearchDocument(
            object_id=f"noise-{i:03d}", kind="Observation",
            title=f"{topic}记录{i:03d}", text=text,
            dimension_slug=f"dim-{topic}", day_index=i,
        ))
    bus.add(SearchDocument(
        object_id=GOLD_IDS[0], kind="Claim", title="违约告知函",
        text="老王违约：单方撕毁对赌回购协议第 4.2 条，连夜将核心专利转移离岸空壳公司；"
             "审计组已封存往来账册。",
        dimension_slug="dim-法务违约", day_index=0,
    ))
    bus.add(SearchDocument(
        object_id=GOLD_IDS[1], kind="Annotation", title="董事会紧急决议",
        text="就老王违约事项启动对赌回购条款主张与司法查封，授权法务提交保全申请。",
        dimension_slug="dim-法务违约", day_index=1,
    ))
    return bus


def test_gate1_three_pathways_agree_and_cost_curve():
    executor = PathwayComparisonExecutor(_build_bus())
    a, b, c = executor.run_all(QUERY)

    gold = {r.object_id for r in a.refs}
    assert gold == set(GOLD_IDS)
    assert {r.object_id for r in b.refs} == gold
    assert {r.object_id for r in c.refs} == gold

    # 暴力路径成本位于工单设定量级
    assert 15_000 <= a.token_cost <= 50_000
    assert a.doc_reads == 400
    # 拓扑分级下钻：只读 2 篇子树文档，总成本 ≤500
    assert c.doc_reads == 2
    assert c.token_cost <= DISTILL_TARGET_TOKENS
    assert c.token_cost < b.token_cost < a.token_cost


def test_gate2_golden_distillation_reaches_500_tokens_and_perfect_accuracy(tmp_path):
    bus = _build_bus()
    pool = ExperiencePool(tmp_path / "pool.jsonl")
    distiller = OperationExperienceDistiller(bus, pool)

    for _ in range(MIN_OBSERVATIONS_FOR_GOLD):
        distiller.observe(QUERY)
    record = distiller.maybe_distill_gold(QUERY)
    assert record is not None and record.accuracy == 1.0
    assert record.golden_pathway == "C_topology_drill"
    assert set(record.evidence_ref_ids) == set(GOLD_IDS)

    answer = distiller.distilled_search(QUERY)
    assert answer is not None and answer.reused_experience
    assert answer.token_cost <= DISTILL_TARGET_TOKENS
    assert estimate_tokens(answer.text) <= TOKEN_HIT_SOFT_CAP
    assert {r.object_id for r in answer.refs} == set(GOLD_IDS)
    assert answer.hit_accuracy == 1.0

    # 蒸馏前 A 路径成本 / 蒸馏后直达成本 ≥ 30 倍（15,000→500 量级压缩）
    a_cost = PathwayComparisonExecutor(bus).pathway_a_brute_scan(QUERY).token_cost
    assert a_cost / max(answer.token_cost, 1) >= 30


def test_gate3_experience_pool_is_append_only_and_roundtrips(tmp_path):
    path = tmp_path / "pool.jsonl"
    bus = _build_bus()
    distiller = OperationExperienceDistiller(bus, ExperiencePool(path))
    for _ in range(MIN_OBSERVATIONS_FOR_GOLD):
        distiller.observe(QUERY)
    assert distiller.maybe_distill_gold(QUERY) is not None
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # 同族黄金经验只登记一次（幂等）
    assert distiller.maybe_distill_gold(QUERY) is not None
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    reloaded = ExperiencePool(path)
    assert len(reloaded) == 1
    distiller_fresh = OperationExperienceDistiller(bus, reloaded)
    answer = distiller_fresh.distilled_search(QUERY)
    assert answer is not None and answer.hit_accuracy == 1.0


def test_gate4_unknown_intent_never_fabricates(tmp_path):
    distiller = OperationExperienceDistiller(_build_bus(), ExperiencePool(tmp_path / "p.jsonl"))
    assert distiller.distilled_search(("离岸", "空壳")) is None  # 未观测族绝不编造
