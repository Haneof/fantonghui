"""AIOS 3.0 全天生活流与多维总结高熵考卷验收断言套件 (Daily Summary Question Bank Verification).

严格落实最高指令长（老大）法定出卷铁律：
1. 1 万个人的一天：满额 10,000 题，题号与人物姓名全局唯一；
2. 24 小时生活流：完整覆盖 07:00 ~ 23:30，真实交织大事与生活琐碎（咖啡/快递/外卖/通勤/日常体征）；
3. 六大维度方向性标答：全局日总结 + 健康/社交/情绪/财务/事业；
4. 标答必须标明【可接受的方向同义词簇】与【绝对偏离的红线判据】；
5. 裁判器断言：标准方向答卷满分 PASS，红线违规一票否决 FAIL，自出自做一票否决 FAIL。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.simulation.daily_summary_arena_protocol import (
    DailyLifeQuestion,
    DailySummaryDirectionalMatcher,
    DailySummarySubmission,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / "benchmarks" / "daily_summary"
QUESTIONS_FILE = BENCH_DIR / "questions" / "questions_01a0aa2d-fantonghui.jsonl"
MANIFEST_FILE = BENCH_DIR / "manifest_01a0aa2d-fantonghui.json"
REPORT_FILE = BENCH_DIR / "reports" / "generation_report_01a0aa2d-fantonghui.md"


@pytest.fixture(scope="module")
def sample_rows():
    """读取前 200 行作为高保真快速实测样本。"""
    assert QUESTIONS_FILE.exists(), f"题库文件未生成: {QUESTIONS_FILE}"
    rows = []
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx >= 200:
                break
            rows.append(json.loads(line.strip()))
    return rows


def test_bank_file_exists_and_has_ten_thousand_lines():
    """断言题库文件存在且正好 10,000 行。"""
    assert QUESTIONS_FILE.exists(), f"题库文件未找到: {QUESTIONS_FILE}"
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        line_count = sum(1 for _ in f)
    assert line_count == 10000, f"题量必须严格等于 10,000，实际 {line_count}"


def test_every_row_satisfies_pydantic_contract(sample_rows):
    """断言每道考题均符合 DailyLifeQuestion 严格契约。"""
    for r in sample_rows:
        q = DailyLifeQuestion.model_validate(r)
        assert q.question_id.startswith("Q_01a0aa2d-fantonghui_")
        assert q.generator_agent == "01a0aa2d-fantonghui"
        assert q.persona.name
        assert 18 <= q.persona.age <= 85
        assert len(q.cleaned_daily_stream) >= 10


def test_full_day_time_span_coverage(sample_rows):
    """断言每道题时间轴必须完整覆盖清晨到深夜（07:00 ~ 23:30），且时间戳单调递增。"""
    for r in sample_rows:
        times = [s["t"] for s in r["cleaned_daily_stream"]]
        earliest = min(times)
        latest = max(times)
        assert earliest <= "08:00", f"{r['question_id']} 早晨起点过晚: {earliest}"
        assert latest >= "23:00", f"{r['question_id']} 深夜终点过早: {latest}"
        assert times == sorted(times), f"{r['question_id']} 时间戳未按时序严格单调递增"


def test_mixture_of_major_conflicts_and_trivial_routines(sample_rows):
    """断言每道题必须交织关键大事件与海量琐碎日常（多模态通道混合）。"""
    for r in sample_rows:
        slices = r["cleaned_daily_stream"]
        srcs = {s["src"] for s in slices}
        # 必须同时包含传感器、对话麦克风与应用通知通道
        assert "sensor" in srcs
        assert "mic" in srcs
        assert "app" in srcs
        assert len(slices) >= 10


def test_six_dimensions_ground_truth_completeness(sample_rows):
    """断言必须具备 6 维完整的方向性语义标答，每维均含可接受同义词与红线判据。"""
    required_dims = [
        "global_daily_summary",
        "dim:health",
        "dim:social",
        "dim:emotion",
        "dim:finance",
        "dim:career",
    ]
    for r in sample_rows:
        gt = r["directional_ground_truth"]
        for d in required_dims:
            assert d in gt, f"{r['question_id']} 缺失维度标答: {d}"
            anchor = gt[d]
            assert anchor["core_plot"].strip(), f"{d} 核心事实为空"
            assert len(anchor["acceptable_directions"]) >= 1, f"{d} 缺失方向同义词簇"
            assert len(anchor["redline_violations"]) >= 1, f"{d} 缺失红线违规判据"
            assert len(anchor["core_anchors"]) >= 1, f"{d} 缺失关键事实锚点"


def test_directional_matcher_gold_score_full_marks(sample_rows):
    """裁判器断言：方向正确的标答必须得分 >= 90 并判定 PASS。"""
    for r in sample_rows[:30]:
        q = DailyLifeQuestion.model_validate(r)
        gt = q.directional_ground_truth
        submission = DailySummarySubmission(
            question_id=q.question_id,
            solver_agent="test-gold-solver",
            generated_global_summary=gt.global_daily_summary.core_plot,
            generated_health_summary=gt.dim_health.core_plot,
            generated_social_summary=gt.dim_social.core_plot,
            generated_emotion_summary=gt.dim_emotion.core_plot,
            generated_finance_summary=gt.dim_finance.core_plot,
            generated_career_summary=gt.dim_career.core_plot,
        )
        rep = DailySummaryDirectionalMatcher.evaluate_submission(q, submission)
        assert rep.overall_score >= 90.0, f"标准答卷得分过低: {rep.overall_score}"
        assert rep.verdict == "PASS"


def test_directional_matcher_redline_boundary_veto(sample_rows):
    """裁判器断言：触碰红线禁区判据（如吵架分手答成恩爱互动）必须一票否决判 FAIL。"""
    q = DailyLifeQuestion.model_validate(sample_rows[0])
    gt = q.directional_ground_truth
    redline_syn = gt.global_daily_summary.redline_violations[0]

    submission = DailySummarySubmission(
        question_id=q.question_id,
        solver_agent="test-bad-solver",
        generated_global_summary=f"今天整体非常顺心，{redline_syn}，毫无波澜。",
        generated_health_summary=gt.dim_health.core_plot,
        generated_social_summary=gt.dim_social.core_plot,
        generated_emotion_summary=gt.dim_emotion.core_plot,
        generated_finance_summary=gt.dim_finance.core_plot,
        generated_career_summary=gt.dim_career.core_plot,
    )
    rep = DailySummaryDirectionalMatcher.evaluate_submission(q, submission)
    assert rep.verdict == "FAIL", "红线违规必须一票否决"
    assert rep.dimension_results["global_daily_summary"].triggered_redline_violations
    assert rep.dimension_results["global_daily_summary"].score == 0.0


def test_self_solving_forbidden_iron_law(sample_rows):
    """最高铁律断言：严禁自出自做（solver_agent == generator_agent 必判 FAIL）。"""
    q = DailyLifeQuestion.model_validate(sample_rows[0])
    gt = q.directional_ground_truth
    submission = DailySummarySubmission(
        question_id=q.question_id,
        solver_agent=q.generator_agent,  # 故意违规自出自做
        generated_global_summary=gt.global_daily_summary.core_plot,
        generated_health_summary=gt.dim_health.core_plot,
        generated_social_summary=gt.dim_social.core_plot,
        generated_emotion_summary=gt.dim_emotion.core_plot,
        generated_finance_summary=gt.dim_finance.core_plot,
        generated_career_summary=gt.dim_career.core_plot,
    )
    rep = DailySummaryDirectionalMatcher.evaluate_submission(q, submission)
    assert rep.verdict == "FAIL"
    assert rep.overall_score == 0.0
    assert "严禁自出自做" in rep.details


def test_delivery_manifest_and_report_exist():
    """断言交付清单与交付报告均已落盘且校验错误为 0。"""
    assert MANIFEST_FILE.exists(), f"清单缺失: {MANIFEST_FILE}"
    assert REPORT_FILE.exists(), f"报告缺失: {REPORT_FILE}"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["n_questions"] == 10000
    assert manifest["unique_ids"] == 10000
    assert manifest["unique_names"] == 10000
    assert manifest["validation_error_count"] == 0
