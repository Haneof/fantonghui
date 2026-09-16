"""跨出卷方盲卷做题器（Solver 01a0aa2c-fantonghui on agent_01a0aa30 盲卷）单元测试。

覆盖四类不变量：

1. **盲解输入不变量**：``solve_question`` 只吃 ``persona`` + ``cleaned_daily_stream``，
   产物里不得出现任何标答字段；事实（数字/实体）必须来自题面切片。
2. **质量不变量**：不产出记录之外的绝对化评语（"睡眠充足"/"心率平稳"这类题型红线词），
   不产出"记录类型枚举"式的注水词。
3. **官方裁判语义**（vendored 到 ``scripts/_vendor_daily_protocol_a2d.py``）：
   满分/一票否决/自出自做否决行为固化，包含"红线是**无否定处理**的字面子串匹配"这一实测特性。
4. **分集与可复现**：``question_split`` 只依赖 question_id，且 dev 比例约 1/5。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_daily_summary_cross_01a0aa2c.py"
LIBRARY_PATH = (
    REPO_ROOT / "benchmarks" / "data_cleaning" / "cross_library_01a0aa2c"
    / "template_directions_01a0aa2c.json"
)


def _load_runner():
    if "cross_runner_aa2c" in sys.modules:
        return sys.modules["cross_runner_aa2c"]
    spec = importlib.util.spec_from_file_location("cross_runner_aa2c", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cross_runner_aa2c"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


@pytest.fixture(scope="module")
def judge(runner):
    return runner.load_judge()


@pytest.fixture(scope="module")
def library(runner):
    return runner.load_library()


def _question(**overrides):
    question = {
        "question_id": "Q_TEST_00001",
        "generator_agent": "daily-examiner-01a0aa30",
        "exam_date": "2026-09-16",
        "persona": {"name": "测试甲", "age": 33, "city": "上海", "job": "产品经理",
                    "relationship": "已婚", "partner": "测试乙"},
        "cleaned_daily_stream": [
            {"t": "07:05", "src": "sensor", "text": "晨起静息心率72bpm；昨夜睡眠6小时10分，深睡占比21%"},
            {"t": "09:47", "src": "app", "text": "【扣款通知】房贷月供9,800元自动扣款，刚性支出照旧"},
            {"t": "10:20", "src": "app", "text": "半年度绩效结果：C。本周五前提交改进计划。"},
            {"t": "16:57", "src": "sensor", "text": "心率由80bpm骤升至128bpm，持续约8分钟，血氧98%，判定情绪性心动过速"},
            {"t": "19:25", "src": "mic", "text": "还记得咱高中天台吗……一晃十年了啊。"},
            {"t": "20:41", "src": "mic", "text": "洗碗池的碗你堆三天了！说了多少遍？"},
            {"t": "23:13", "src": "sensor", "text": "入睡准备：今日步数5,914步，全天最高心率128bpm，久坐6小时"},
        ],
    }
    question.update(overrides)
    return question


# ---------------------------------------------------------------- 1. 盲解不变量

def test_solve_question_returns_official_six_dimension_schema(runner, library):
    answer = runner.solve_question(_question(), variant="v2", library=library)
    assert set(answer) >= {"question_id", "solver_agent", "generator_agent"} | set(
        runner.ANSWER_KEYS.values()
    )
    assert answer["solver_agent"] == runner.SOLVER_AGENT == "01a0aa2c-fantonghui"
    for key in runner.ANSWER_KEYS.values():
        assert answer[key].strip(), f"{key} 不应为空"


def test_solve_question_never_leaks_ground_truth_fields(runner, library):
    payload = json.dumps(runner.solve_question(_question(), variant="v2", library=library),
                         ensure_ascii=False)
    for forbidden in ("directional_ground_truth", "core_claim", "core_plot", "redline",
                      "acceptable_directions", "required_entities"):
        assert forbidden not in payload


def test_solve_question_quotes_facts_from_the_stream(runner, library):
    answer = runner.solve_question(_question(), variant="v2", library=library)
    assert "9,800元" in answer["generated_finance_summary"]
    assert "情绪性心动过速" in answer["generated_health_summary"]
    assert "128bpm" in answer["generated_health_summary"]


def test_solve_question_ignores_extra_ground_truth_like_input(runner, library):
    """即使调用方误塞标答字段，解算器也只读题面（结构上不可能用到 GT）。"""
    polluted = _question()
    polluted["directional_ground_truth"] = {"global_daily_summary": {"core_claim": "翻车日"}}
    clean = runner.solve_question(_question(), variant="v2", library=library)
    dirty = runner.solve_question(polluted, variant="v2", library=library)
    assert clean == dirty


# ---------------------------------------------------------------- 2. 质量不变量

FORBIDDEN_IDIOMS = ("睡眠充足", "睡眠不足", "体征平稳", "心率平稳", "无心率骤升", "体检全优")


def test_solver_avoids_evaluative_idioms_that_hit_literal_redlines(runner, library):
    answer = runner.solve_question(_question(), variant="v2", library=library)
    joined = " ".join(answer[key] for key in runner.ANSWER_KEYS.values())
    for idiom in FORBIDDEN_IDIOMS:
        assert idiom not in joined, f"不应产出无记录支持的绝对化评语: {idiom}"


def test_solver_does_not_emit_record_type_enumeration(runner, library):
    """"静息心率、睡眠时长、深睡占比"这类记录类型名属于注水，不得出现在总结里。"""
    answer = runner.solve_question(_question(), variant="v2", library=library)
    health = answer["generated_health_summary"]
    for junk in ("睡眠时长", "深睡占比", "全天活动量", "久坐时长"):
        assert junk not in health


def test_solver_marks_relationship_negative_day_truthfully(runner, library):
    answer = runner.solve_question(_question(), variant="v2", library=library)
    assert "人际冲突" in answer["generated_global_summary"] or \
           "压力" in answer["generated_global_summary"]


# ---------------------------------------------------------------- 3. 官方裁判语义

def _anchor(**overrides):
    base = {
        "core_plot": "晚间16:57心率由80骤升至128bpm（情绪性心动过速）",
        "core_anchors": ["心率骤升", "128bpm"],
        "acceptable_directions": ["心动过速", "心率飙升"],
        "redline_violations": ["心率骤升"],
        "key_evidence_refs": ["sensor@16:57"],
    }
    base.update(overrides)
    return base


def test_official_judge_gives_full_marks_for_exact_core_plot(judge):
    anchor = judge.DirectionalGroundTruthAnchor(**_anchor())
    result = judge.DailySummaryDirectionalMatcher.evaluate_dimension(
        "dim_health", "晚间16:57心率由80骤升至128bpm（情绪性心动过速）", anchor)
    assert result.score == 100.0


def test_official_judge_scores_direction_and_anchor_recall(judge):
    anchor = judge.DirectionalGroundTruthAnchor(**_anchor(redline_violations=[]))
    result = judge.DailySummaryDirectionalMatcher.evaluate_dimension(
        "dim_health", "晚间出现心动过速，峰值128bpm", anchor)
    assert result.direction_matched is True
    assert result.recalled_anchors == ["128bpm"]
    assert result.score == pytest.approx(80.0, abs=0.01)


def test_official_redline_is_negation_blind_literal_substring(judge):
    """实测特性：官方红线判据不做否定处理——写"无心率骤升"同样会命中红线"心率骤升"。

    因此本队解算器一律不写否定式评语（见 FORBIDDEN_IDIOMS 用例）。
    """
    anchor = judge.DirectionalGroundTruthAnchor(**_anchor())
    result = judge.DailySummaryDirectionalMatcher.evaluate_dimension(
        "dim_health", "当日无心率骤升记录，晨脉72bpm", anchor)
    assert result.triggered_redline_violations == ["心率骤升"]
    assert result.score == 0.0


def test_official_judge_vetoes_self_solving(judge):
    question = judge.DailyLifeQuestion(
        question_id="Q_TEST", generator_agent="01a0aa2c-fantonghui",
        persona={"name": "甲", "age": 30, "city": "上海", "job": "测试"},
        cleaned_daily_stream=[{"t": "07:05", "src": "sensor", "text": "x"}],
        directional_ground_truth={key: _anchor() for key in
                                  ("global_daily_summary", "dim:health", "dim:social",
                                   "dim:emotion", "dim:finance", "dim:career")},
    )
    submission = judge.DailySummarySubmission(
        question_id="Q_TEST", solver_agent="01a0aa2c-fantonghui",
        generated_global_summary="a", generated_health_summary="a", generated_social_summary="a",
        generated_emotion_summary="a", generated_finance_summary="a", generated_career_summary="a",
    )
    report = judge.DailySummaryDirectionalMatcher.evaluate_submission(question, submission)
    assert report.verdict == "FAIL"
    assert report.fatal_redline_triggered is True
    assert report.overall_score == 0.0


# ---------------------------------------------------------------- 4. 分集与可复现

def test_question_split_is_deterministic_and_roughly_one_fifth(runner):
    ids = [f"Q_01a0aa2d-fantonghui_{index:05d}" for index in range(1, 5001)]
    splits = [runner.question_split(qid) for qid in ids]
    assert splits == [runner.question_split(qid) for qid in ids]
    dev_ratio = splits.count("dev") / len(splits)
    assert 0.15 < dev_ratio < 0.25


def test_library_is_fitted_from_blind_stream_only(runner, library):
    assert LIBRARY_PATH.exists()
    fitted = library["fitted_from"]
    assert fitted["sha256"] == runner.BLIND_EXPECTED_SHA256
    assert "未接触任何标答字段" in fitted["discipline"]
    assert library["templates"], "模板库不应为空"
    assert all(set(entry) >= {"sig", "dim", "kind"} for entry in library["templates"])


def test_vendored_judge_matches_pinned_sha256(runner):
    import hashlib

    actual = hashlib.sha256(runner.JUDGE_PATH.read_bytes()).hexdigest()
    assert actual == runner.JUDGE_EXPECTED_SHA256
