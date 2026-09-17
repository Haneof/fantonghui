"""单测套件：1000 题认知实战大考组卷引擎与卷宗校验器 (test_cognitive_exam_volume.py).

覆盖出卷铁律与判卷契约：

- 四型配额（A/B/C/D = 380/270/250/100）与确定性可复现；
- 每卷 1~2 次白天手环交互，且**至少一次是不合时宜的打扰**（被无视 / 烦躁）；
- 每卷含跨维因果链、反过度诊断红线、候选新维度（平静陷阱卷必须克制）；
- 卷内"文案钟点"与"时间轴时间戳"自洽（防止文案与时间戳打架）；
- 参考答案可解性：密封裁判与方向性裁判双跑满分、零误杀；
- 校验器能识别被植入的违宪缺陷。
"""

from __future__ import annotations

import copy
import json

import pytest

from aios_core.bench.cognitive_exam_dataset import (
    run_oracle,
    validate_paper,
    validate_volume,
)
from aios_core.bench.cognitive_exam_paper_forge import (
    TYPE_PLAN,
    build_plan,
    build_volume,
    main as forge_main,
)
from aios_core.bench.cognitive_exam_dataset import main as validate_main
from aios_core.bench.cognitive_exam_pools import (
    DIMENSION_REGISTRY,
    circular_minute_gap,
    iter_clock_candidates,
)

SEED = 20260917
SAMPLE_SIZE = 120


@pytest.fixture(scope="module")
def sample_papers() -> list[dict]:
    """一次组卷、多次断言（组卷含去重重试，避免每个用例重复付成本）。"""
    return build_volume(SAMPLE_SIZE, SEED)


def test_type_plan_matches_dispatch_12() -> None:
    assert TYPE_PLAN == {"A": 380, "B": 270, "C": 250, "D": 100}
    assert sum(TYPE_PLAN.values()) == 1000


def test_plan_keeps_type_quotas_and_partial_rotation() -> None:
    """满编卷严格按配额，抽样卷按 A/B/C/D 轮转（便于分批生成）。"""
    distribution: dict[str, int] = {}
    for exam_type in build_plan(1000):
        distribution[exam_type] = distribution.get(exam_type, 0) + 1
    assert distribution == TYPE_PLAN
    assert build_plan(8) == ["A", "B", "C", "D"] * 2
    papers = build_volume(24, SEED)
    assert [paper["exam_type"][0] for paper in papers] == build_plan(24)


def test_build_volume_is_deterministic() -> None:
    left = build_volume(10, SEED)
    right = build_volume(10, SEED)
    assert json.dumps(left, ensure_ascii=False) == json.dumps(right, ensure_ascii=False)


def test_sample_volume_passes_every_check(sample_papers: list[dict]) -> None:
    report = validate_volume(sample_papers)
    assert report.errors == [], [issue.__dict__ for issue in report.errors[:5]]
    assert len(sample_papers) == SAMPLE_SIZE
    assert len({paper["question_id"] for paper in sample_papers}) == SAMPLE_SIZE
    for paper in sample_papers:
        interactions = paper["daytime_ai_interactions"]
        assert 1 <= len(interactions) <= 2
        assert any(item["user_response"] in {"IGNORED", "IRRITATED"} for item in interactions), \
            f"{paper['question_id']} 缺少不合时宜的手环打扰"
        timeline = paper["cleaned_daily_stream"]["timeline"]
        assert 8 <= len(timeline) <= 15
        assert {"MIC", "APP", "SENSOR"} <= {item["source"] for item in timeline}


def test_oracle_reference_answers_are_solvable(sample_papers: list[dict]) -> None:
    subset = sample_papers[:24]
    for mode in ("verbatim", "directional"):
        result = run_oracle(subset, mode=mode)
        assert result["canonical_pass_rate"] == 1.0, result["failures"][:2]
        assert result["directional_pass_rate"] == 1.0, result["failures"][:2]
        assert result["asserted_vetoes"] == []


def test_trap_papers_demand_restraint(sample_papers: list[dict]) -> None:
    traps = [paper for paper in sample_papers if paper["exam_type"].startswith("D")]
    assert traps, "抽样卷中必须包含平静陷阱卷"
    for paper in traps:
        ground_truth = paper["ground_truth"]
        assert ground_truth["expected_new_dimension"] is None
        assert ground_truth["trap_profile"]["required_solver_decision"] == "propose_new_dimension = false"
        assert len(ground_truth["trap_profile"]["forbidden_claims"]) >= 3
        assert ground_truth["ai_self_review_demands"]["must_lower_restraint"] is True
        assert "平静日常" in ground_truth["user_summary_core_anchors"]
        for link in ground_truth["expected_causal_chain"]:
            assert link["source_dim"] in DIMENSION_REGISTRY
            assert link["target_dim"] in DIMENSION_REGISTRY
            assert link["source_dim"] != link["target_dim"]


def test_dimension_papers_carry_article_73_elements(sample_papers: list[dict]) -> None:
    candidates = [paper for paper in sample_papers if not paper["exam_type"].startswith("D")]
    assert candidates
    for paper in candidates:
        dimension = paper["ground_truth"]["expected_new_dimension"]
        assert dimension is not None
        assert dimension["dimension_id"].startswith("dim:candidate_")
        assert dimension["subject"] == "USER"
        assert len(dimension["required_article73_elements"]) == 10
        assert len(dimension["article_73_expected_content"]) == 10
        assert all(dimension["article_73_expected_content"].values())
        assert len(dimension["article_76_self_score_keys"]) == 6
        evidence = dimension["gate_evidence"]
        assert len(set(evidence["physical_domains"])) >= 2
        assert evidence["pattern_days"] >= 3
        assert evidence["occurrences_in_window"] >= 3


def test_clock_text_matches_timestamps(sample_papers: list[dict]) -> None:
    for paper in sample_papers:
        for item in paper["cleaned_daily_stream"]["timeline"]:
            candidates = iter_clock_candidates(item["text"])
            if not candidates:
                continue
            hour, minute = (int(part) for part in item["time"].split(":"))
            stamped = hour * 60 + minute
            assert any(circular_minute_gap(candidate, stamped) <= 15 for candidate in candidates), \
                f"{paper['question_id']} {item['time']} 与文案钟点不符：{item['text'][:40]}"


def test_validate_paper_catches_planted_defects(sample_papers: list[dict]) -> None:
    paper = sample_papers[0]

    broken_redline = copy.deepcopy(paper)
    broken_redline["cleaned_daily_stream"]["timeline"][0]["text"] += "；最终被确诊急性心肌梗死"
    codes = {issue.code for issue in validate_paper(broken_redline).issues}
    assert "REDLINE_LEAK" in codes

    broken_misfire = copy.deepcopy(paper)
    for item in broken_misfire["daytime_ai_interactions"]:
        item["user_response"] = "ACCEPTED"
    codes = {issue.code for issue in validate_paper(broken_misfire).issues}
    assert "MISFIRE_MISSING" in codes

    broken_self_review = copy.deepcopy(paper)
    broken_self_review["ground_truth"]["ai_self_review_demands"]["must_lower_restraint"] = False
    codes = {issue.code for issue in validate_paper(broken_self_review).issues}
    assert "SELF_REVIEW_LOGIC" in codes


def test_forge_and_validate_cli_roundtrip(tmp_path) -> None:
    volume_path = tmp_path / "volume.jsonl"
    assert forge_main(["--out", str(volume_path), "--count", "8", "--seed", str(SEED)]) == 0
    assert volume_path.exists()

    report_path = tmp_path / "report.json"
    assert validate_main(["validate", "--papers", str(volume_path),
                          "--report-json", str(report_path)]) == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["errors"] == []
    assert payload["papers"] == 8
