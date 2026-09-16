"""跨队全天生活流多维总结解题器测试。

重点守护三条铁律：盲视、严禁自出自做、红线自保。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.perception.daily_summary_arena_runner import (
    AA2D_WEIGHTS,
    gt_from_aa2c,
    gt_from_aa2d,
    grade_aa2c,
    grade_aa2d,
    load_jsonl,
    run_arena,
)
from aios_core.perception.daily_summary_solver import (
    AA2C_DIMS,
    AA2D_DIMS,
    DailySummarySolver,
    LeakageError,
    SelfSolveError,
    SolverConfig,
    assert_blind,
    assert_cross_team,
    blind_view,
    evidence_keys,
    normalise,
)


def _aa2d_question(qid: str = "Q_rival_0001") -> dict:
    return {
        "question_id": qid,
        "generator_agent": "rival-agent",
        "difficulty": "HARD",
        "persona": {"name": "毛娟", "age": 32, "job": "电气工程师", "relationship": "已婚"},
        "cleaned_daily_stream": [
            {"t": "07:05", "src": "sensor", "text": "晨起静息心率74bpm；昨夜睡眠6小时"},
            {"t": "16:55", "src": "mic", "text": "全员大会上被点名批评", "who": "领导"},
            {"t": "16:57", "src": "sensor", "text": "心率由83骤升至134bpm"},
            {"t": "19:25", "src": "mic", "text": "和老同学聚会聊到深夜", "who": "老同学"},
        ],
        "directional_ground_truth": {
            "global_daily_summary": {
                "core_plot": "转折起伏日",
                "core_anchors": ["转折", "情绪起伏"],
                "acceptable_directions": ["喜忧参半"],
                "redline_violations": ["平淡无波"],
            },
            "dim:health": {
                "core_plot": "心率骤升134bpm",
                "core_anchors": ["心率骤升", "134bpm"],
                "acceptable_directions": ["心动过速"],
                "redline_violations": ["体检全优"],
            },
            "dim:social": {
                "core_plot": "老同学聚会",
                "core_anchors": ["老同学", "聚会"],
                "acceptable_directions": ["老友重逢"],
                "redline_violations": ["不欢而散"],
            },
            "dim:emotion": {
                "core_plot": "先抑后扬",
                "core_anchors": ["委屈"],
                "acceptable_directions": ["先苦后甜"],
                "redline_violations": ["全程崩溃"],
            },
            "dim:finance": {
                "core_plot": "股票浮亏6000元",
                "core_anchors": ["浮亏"],
                "acceptable_directions": ["投资亏损"],
                "redline_violations": ["大额盈利"],
            },
            "dim:career": {
                "core_plot": "大会被点名批评",
                "core_anchors": ["大会点名"],
                "acceptable_directions": ["公开挨批"],
                "redline_violations": ["大会表扬"],
            },
        },
    }


# ---------------------------------------------------------------- 盲视


def test_blind_view_strips_ground_truth():
    q = _aa2d_question()
    v = blind_view(q)
    assert "directional_ground_truth" not in v
    assert v["question_id"] == q["question_id"]
    assert len(v["cleaned_daily_stream"]) == 4


def test_blind_view_strips_nested_leaky_fields():
    q = {"a": {"b": [{"core_anchors": ["x"], "text": "keep"}]}}
    v = blind_view(q)
    assert v["a"]["b"][0] == {"text": "keep"}


def test_blind_view_does_not_mutate_original():
    q = _aa2d_question()
    blind_view(q)
    assert "directional_ground_truth" in q


def test_assert_blind_raises_on_leak():
    with pytest.raises(LeakageError):
        assert_blind({"x": {"directional_ground_truth": {}}})


def test_assert_blind_passes_on_clean_view():
    assert_blind(blind_view(_aa2d_question())) is None


# ---------------------------------------------------------------- 严禁自出自做


def test_assert_cross_team_rejects_same_agent():
    with pytest.raises(SelfSolveError):
        assert_cross_team("agent-x", "agent-x")


def test_assert_cross_team_is_case_and_space_insensitive():
    with pytest.raises(SelfSolveError):
        assert_cross_team("Agent X", "agentx")


def test_solver_refuses_to_solve_own_bank():
    q = _aa2d_question()
    solver = DailySummarySolver(solver_agent="rival-agent", dims=AA2D_DIMS)
    with pytest.raises(SelfSolveError):
        solver.solve(q)


# ---------------------------------------------------------------- 红线自保


def test_redline_guard_drops_dangerous_terms():
    """在别的题里当过红线的短语，绝不落笔。"""
    solver = DailySummarySolver(solver_agent="me", dims=("dim:social",))
    solver._redline_vocab["dim:social"] = {"分手": 3}
    safe = solver._redline_guard("dim:social", ["老友重逢", "分手", "聚会"])
    assert safe == ["老友重逢", "聚会"]


def test_redline_guard_also_drops_supersets():
    """判分器用子串匹配，含危险词的长短语同样会引爆红线。"""
    solver = DailySummarySolver(solver_agent="me", dims=("dim:social",))
    solver._redline_vocab["dim:social"] = {"分手": 1}
    assert solver._redline_guard("dim:social", ["深夜提出分手了"]) == []


def test_redline_guard_can_be_disabled():
    solver = DailySummarySolver(
        solver_agent="me", dims=("dim:social",), config=SolverConfig(redline_guard=False)
    )
    solver._redline_vocab["dim:social"] = {"分手": 1}
    assert solver._redline_guard("dim:social", ["分手"]) == ["分手"]


def test_solver_never_emits_trained_redlines():
    """端到端：训练后作答不得命中训练集见过的红线。"""
    qs = [_aa2d_question(f"Q{i}") for i in range(30)]
    gts = [gt_from_aa2d(q) for q in qs]
    solver = DailySummarySolver(solver_agent="me", dims=AA2D_DIMS)
    solver.fit(zip(qs, gts))
    ans = solver.solve(_aa2d_question("Q_eval"))
    for d in AA2D_DIMS:
        for red in gts[0][d]["redlines"]:
            assert normalise(red) not in normalise(ans[d])


# ---------------------------------------------------------------- 证据抽取


def test_evidence_keys_cover_text_and_speaker():
    keys = evidence_keys(blind_view(_aa2d_question()))
    flat = {k for _, k in keys}
    assert any("全员大会上被点名批评" in k for k in flat)
    assert "领导" in flat


def test_evidence_keys_handles_aa2c_nested_shape():
    view = {
        "persona": {"occupation": "财务总监"},
        "cleaned_daily_stream": {
            "vitals_summary": {"wake_resting_hr_bpm": 84},
            "slices": [{"time": "09:38", "modality": "app", "text": "浮亏12万"}],
        },
    }
    flat = {k for _, k in evidence_keys(view)}
    assert "浮亏12万" in flat
    assert "财务总监" in flat
    assert any("wake_resting_hr_bpm" in k for k in flat)


def test_evidence_keys_empty_stream_is_safe():
    assert evidence_keys({"cleaned_daily_stream": []}) == []


# ---------------------------------------------------------------- 阅卷口径


def test_grade_aa2d_redline_zeroes_whole_paper():
    gt = gt_from_aa2d(_aa2d_question())
    ans = {d: "" for d in AA2D_DIMS}
    ans["dim:health"] = "体检全优"
    rep = grade_aa2d(gt, ans)
    assert rep["total"] == 0.0
    assert rep["pass"] is False
    assert "dim:health" in rep["vetoes"]


def test_grade_aa2d_core_plot_match_is_full_marks():
    gt = gt_from_aa2d(_aa2d_question())
    ans = {d: gt[d]["core"] for d in AA2D_DIMS}
    rep = grade_aa2d(gt, ans)
    assert rep["total"] == pytest.approx(100.0)
    assert rep["pass"] is True


def test_grade_aa2d_weights_favour_global_dimension():
    assert AA2D_WEIGHTS["global_daily_summary"] == 0.25
    assert sum(AA2D_WEIGHTS.values()) == pytest.approx(1.0)


def test_grade_aa2d_low_recall_without_direction_scores_zero():
    gt = gt_from_aa2d(_aa2d_question())
    rep = grade_aa2d(gt, {d: "完全无关的一句话" for d in AA2D_DIMS})
    assert rep["total"] == 0.0


def test_grade_aa2c_uses_anchor_coverage():
    gt_row = {
        "question_id": "x",
        "directional_ground_truth": {
            d: {"core_statement": "c", "accepted_synonyms": ["甲", "乙"], "red_lines": ["禁"]}
            for d in AA2C_DIMS
        },
    }
    gt = gt_from_aa2c(gt_row)
    assert grade_aa2c(gt, {d: "甲乙" for d in AA2C_DIMS})["total"] == pytest.approx(100.0)
    assert grade_aa2c(gt, {d: "甲" for d in AA2C_DIMS})["total"] == pytest.approx(50.0)


def test_grade_aa2c_redline_zeroes_that_dimension_only():
    gt_row = {
        "question_id": "x",
        "directional_ground_truth": {
            d: {"core_statement": "c", "accepted_synonyms": ["甲"], "red_lines": ["禁"]}
            for d in AA2C_DIMS
        },
    }
    gt = gt_from_aa2c(gt_row)
    ans = {d: "甲" for d in AA2C_DIMS}
    ans["dim:health"] = "禁"
    rep = grade_aa2c(gt, ans)
    assert rep["dims"]["dim:health"]["score"] == 0.0
    assert rep["dims"]["dim:social"]["score"] == 100.0
    assert rep["total"] == pytest.approx(round(500 / 6, 2))


def test_grade_aa2c_neutral_dimension_is_full_marks_when_silent():
    gt = {
        d: {"anchors": [], "directions": [], "redlines": [], "core": "", "neutral": True}
        for d in AA2C_DIMS
    }
    assert grade_aa2c(gt, {d: "" for d in AA2C_DIMS})["total"] == pytest.approx(100.0)


# ---------------------------------------------------------------- 跑场


def test_run_arena_splits_are_disjoint_and_reports_zero_llm():
    qs = [_aa2d_question(f"Q{i}") for i in range(40)]
    gts = [gt_from_aa2d(q) for q in qs]
    rep, answers = run_arena("AA2D", qs, gts, "me", 10, SolverConfig())
    assert rep["n_calibration"] == 10
    assert rep["n_evaluated"] == 30
    assert rep["llm_calls"] == 0
    assert len(answers) == 30


def test_run_arena_rejects_self_solving():
    qs = [_aa2d_question(f"Q{i}") for i in range(10)]
    gts = [gt_from_aa2d(q) for q in qs]
    with pytest.raises(SelfSolveError):
        run_arena("AA2D", qs, gts, "rival-agent", 3, SolverConfig())


def test_answers_never_contain_ground_truth_field_names():
    qs = [_aa2d_question(f"Q{i}") for i in range(20)]
    gts = [gt_from_aa2d(q) for q in qs]
    _, answers = run_arena("AA2D", qs, gts, "me", 5, SolverConfig())
    blob = json.dumps(answers, ensure_ascii=False)
    for leak in ("core_plot", "redline_violations", "directional_ground_truth"):
        assert leak not in blob


def test_load_jsonl_respects_limit(tmp_path: Path):
    p = tmp_path / "b.jsonl"
    p.write_text("\n".join(json.dumps({"i": i}) for i in range(10)), encoding="utf-8")
    assert len(load_jsonl(p, 4)) == 4
    assert len(load_jsonl(p)) == 10


def test_normalise_strips_all_whitespace_and_lowercases():
    assert normalise("  A b\tC\n") == "abc"
    assert normalise(None) == ""
