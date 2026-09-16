"""M5-SEARCH 验收：三路径执行器 + 黄金经验持久化。

1. 同一语料上，C 路径命中 == A 暴力扫描全集（准确率 100%，零漏检）；
2. Token 数量级严格分层：A 达 15,000~50,000 级，C ≤ 500；
3. 每张 C 路径证据卡单次命中 ≤ 150 token（铁律）；
4. 仅当 ≥3 轮跨 2 主题的 100% 达标样本齐备，黄金经验才落盘；
   落盘卡本身 ≤ 500 token；蒸馏后经验重载可查；
5. Topic 查询无匹配时 C 返回 0 token（链路不开销）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.cockpit.pipeline import Utf8ByteTokenCounter
from aios_core.cognition.operation_experience_independent2 import (
    CorpusDoc,
    InsufficientEvidenceError,
    OperationExperienceDistiller,
    PathwayId,
    RetrievalPathwayComparator,
)


def _corpus() -> list[CorpusDoc]:
    topics = RetrievalPathwayComparator.TOPIC_UNIVERSE
    docs: list[CorpusDoc] = []
    for i in range(100):
        topic = topics[i % len(topics)]
        body = (f"doc-{i:03d}-{topic}-" + "x" * 180)[:192]
        docs.append(CorpusDoc(
            doc_id=f"d{i:03d}",
            topics=(topic,),
            title=f"{topic}-record-{i:03d}",
            body=body,
        ))
    return docs


def test_three_pathway_token_ladder_and_full_recall() -> None:
    comp = RetrievalPathwayComparator(_corpus())
    report = comp.benchmark("健康 巡检报告")
    a = report.run(PathwayId.BRUTE_FORCE_A)
    b = report.run(PathwayId.NAIVE_KEYWORD_B)
    c = report.run(PathwayId.TOPOLOGICAL_DRILL_C)

    # 硬门禁：A 达到 15,000~50,000 那个烧预算量级
    assert 15_000 <= a.tokens_used <= 50_000, f"A 量级失真: {a.tokens_used}"
    assert b.tokens_used < a.tokens_used
    # 硬门禁：C 达到「15,000~50,000 → ≤500」
    assert c.tokens_used <= 500, f"C 越顶: {c.tokens_used}"

    # 硬门禁：C 命中率准确 100%
    assert set(c.hit_doc_ids) == set(a.hit_doc_ids), (
        f"漏检: {sorted(set(a.hit_doc_ids) - set(c.hit_doc_ids))}"
    )

    # 硬门禁：单次命中 ≤ 150 token
    counter = Utf8ByteTokenCounter()
    for card in c.evidence_cards:
        assert counter.count(card) <= 150, f"证据卡越顶: {counter.count(card)}"


def test_topicless_query_yields_zero_token_on_path_c() -> None:
    comp = RetrievalPathwayComparator(_corpus())
    c = comp.pathway_c_topological_drill("玄外之音不命中任何主题")
    assert c.tokens_used == 0
    assert c.hit_doc_ids == ()
    assert c.evidence_cards == ()


def test_golden_experience_persists_only_when_strict(tmp_path: Path) -> None:
    comp = RetrievalPathwayComparator(_corpus())
    distiller = OperationExperienceDistiller(tmp_path / "golden.json")

    # 三轮、跨 ≥2 个不同主题，全部 C 优于 A 且召回 100%
    reports = [
        comp.benchmark("健康 心率记录"),
        comp.benchmark("财务 季度报表"),
        comp.benchmark("法务 合同审查"),
    ]
    exp = distiller.distill(reports)
    assert exp.chosen_pathway == PathwayId.TOPOLOGICAL_DRILL_C.value
    assert exp.support_runs == 3
    assert exp.full_recall_every_run
    assert exp.worst_case_tokens <= 500
    assert Utf8ByteTokenCounter().count(exp.distilled_card) <= 500

    raw = json.loads((tmp_path / "golden.json").read_text(encoding="utf-8"))
    assert raw["chosen_pathway"] == PathwayId.TOPOLOGICAL_DRILL_C.value
    reloaded = distiller.load()
    assert reloaded.distilled_card == exp.distilled_card


def test_distiller_rejects_unqualified_samples(tmp_path: Path) -> None:
    comp = RetrievalPathwayComparator(_corpus())
    distiller = OperationExperienceDistiller(tmp_path / "golden.json")
    single = [comp.benchmark("健康 巡检") for _ in range(3)]  # 都同主题
    with pytest.raises(InsufficientEvidenceError):
        distiller.distill(single)
    with pytest.raises(InsufficientEvidenceError):
        distiller.distill(comp.benchmark("健康 巡检") for _ in range(2))
    assert not distiller.store_path.exists(), "低质量样本不许污染经验库"
