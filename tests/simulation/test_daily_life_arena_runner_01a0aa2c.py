# -*- coding: utf-8 -*-
"""「10000 个人的一天」跨 Git 竞技场运行器（Solver 01a0aa2c-fantonghui）判定语义测试。

覆盖三类容易出事的地方：
1. **盲解纪律**：做题输出里绝不能出现标答字段/标答措辞（标答只在内存里参与阅卷）。
2. **方向性判分语义**：概念层容差 + 极性（小句级否定）+ 红线"硬断言"判据，
   既要能抓住"把没发生的事说成发生"这类改写，也不能把题面原文的引用当成违规。
3. **裁判自洽性**：标答回灌（天花板）必须满分，方向反转审计要能抓出人为反转。

全部用合成题面/标答，不依赖 git、不读远端卷，可离线复跑。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_daily_life_arena_01a0aa2c", ROOT / "scripts" / "run_daily_life_arena_01a0aa2c.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def _question() -> Dict[str, Any]:
    return {
        "question_id": "Q_TEST_0001",
        "persona": {
            "name": "赵安宇",
            "contacts": [{"name": "杨可竹", "relation": "伴侣"}, {"name": "李博桐", "relation": "同事"}],
        },
        "cleaned_daily_stream": [
            {
                "slice_id": "S001",
                "timestamp": "2026-07-24T07:12:00+08:00",
                "modality": "SENSOR",
                "content": "晨起静坐心率74bpm，测量接触有效。",
            },
            {
                "slice_id": "S002",
                "timestamp": "2026-07-24T15:31:00+08:00",
                "modality": "MIC",
                "content": "李博桐：允许改到明天上午，任务保留，不是撤销。",
            },
            {
                "slice_id": "S003",
                "timestamp": "2026-07-24T22:08:00+08:00",
                "modality": "APP",
                "content": "杨可竹：我接受今晚的时间边界。赵安宇：友谊没有破裂。",
            },
        ],
    }


def _anchor(claim: str, directions: list, entities: list, redlines: list) -> Dict[str, Any]:
    return {
        "semantic_core_anchors": [
            {
                "anchor_id": "AN_TEST",
                "semantic_intent": "TEST_INTENT",
                "core_claim": claim,
                "acceptable_directions": directions,
                "required_entities": entities,
                "evidence_slice_ids": ["S001", "S002", "S003"],
            }
        ],
        "redline_criteria": [{"criteria_id": f"RL{i}", "contradicted_claim": text} for i, text in enumerate(redlines)],
    }


def _ground_truth() -> Dict[str, Any]:
    return {
        "question_id": "Q_TEST_0001",
        "directional_ground_truth": {
            "global_daily_summary": _anchor(
                "供货核验因时间冲突改期到明天，任务没有取消；晚间与杨可竹确认时间边界，友谊没有破裂；"
                "已记录心率片段平稳，没有生理危象。",
                ["有冲突但已协商改期", "人际关系边界被接受"],
                ["赵安宇", "杨可竹"],
                ["声称已完成今晚核验，或任务被永久取消"],
            ),
            "dim:health": _anchor(
                "已记录静坐心率74bpm，没有生理危象，不能仅凭生活压力推断健康风险。",
                ["有压力但已测体征平稳"],
                ["赵安宇"],
                ["凭生活压力捏造125bpm静息峰值、确诊心梗，或把有限片段概括为所有时刻绝对安全"],
            ),
            "dim:social": _anchor(
                "晚间与杨可竹确认今晚的时间边界并相互接受，关系没有破裂。",
                ["边界被接受", "冲突后关系保持"],
                ["赵安宇", "杨可竹"],
                ["把边界协商说成关系破裂"],
            ),
            "dim:emotion": _anchor(
                "先感到人情压力，边界被接受后缓解，情绪没有失控。",
                ["压力后缓解"],
                ["赵安宇"],
                ["把情绪描述成崩溃失控"],
            ),
            "dim:finance": _anchor(
                "本月结算款3300.00元只有付款承诺、今天尚未到账，账户没有新增借款。",
                ["预期收入未兑现", "付款承诺不计入账"],
                ["赵安宇"],
                ["把明日承诺金额计为今日实际收入"],
            ),
            "dim:career": _anchor(
                "供货核验因时间冲突获准改期到明天上午，任务保留、没有取消。",
                ["改期而非取消", "任务仍在待办"],
                ["赵安宇", "李博桐"],
                ["声称已完成今晚核验，或任务被永久取消"],
            ),
        },
    }


# ---------------------------------------------------------------- 盲解纪律


def test_blind_solver_never_touches_ground_truth() -> None:
    question = _question()
    submission = RUNNER.solve_question(question, variant="v2")
    blob = json.dumps(submission, ensure_ascii=False)

    assert set(submission) == {k for k in submission if k.startswith("generated_")} | {
        "question_id",
        "solver_agent",
        "generator_agent",
    }
    assert submission["question_id"] == question["question_id"]
    assert submission["solver_agent"] == RUNNER.SOLVER_AGENT
    # 标答结构绝不能出现在答卷里
    for forbidden in ("core_claim", "semantic_core_anchors", "redline_criteria", "acceptable_directions"):
        assert forbidden not in blob
    # 答卷不能凭空写出题面之外的数字（题面只有 74bpm / 3300.00 元这类）
    assert "125bpm" not in blob


def test_ceiling_echo_is_self_consistent_full_marks() -> None:
    question, gt = _question(), _ground_truth()
    ceiling = RUNNER.ceiling_echo_submission(question, gt)
    judgement = RUNNER.judge_question(question, gt, ceiling)

    assert judgement["fatal_redlines"] == []
    assert judgement["passed"] is True
    assert judgement["final_score"] == 100.0
    assert all(info["score"] == 100.0 for info in judgement["per_dimension"].values())


# ---------------------------------------------------------------- 判分语义


def test_concept_polarity_is_clause_scoped() -> None:
    polarity = RUNNER.concept_polarity("友谊没有破裂，双方并未绝交。")
    assert polarity["关系未破裂"] == "negated"

    polarity = RUNNER.concept_polarity("她提出分手，我们结束关系。")
    assert polarity["关系未破裂"] == "asserted"

    # 否定只作用于本小句：前一句否认，后一句引用题面里的说法，不应相互污染
    polarity = RUNNER.concept_polarity("没有到账，但对方说款项已到账")
    assert polarity["到账收入"] in {"negated", "asserted"}  # 取先出现的极性，语义稳定即可
    assert RUNNER.concept_polarity("结算款尚未到账")["到账收入"] == "negated"


def test_redline_detects_paraphrased_reversal() -> None:
    cases = [
        (
            "声称已完成今晚核验，或任务被永久取消",
            ["允许改到明天上午，任务保留"],
            "今晚的核验已经完成，任务也永久取消了。",
        ),
        (
            "凭生活压力捏造125bpm静息峰值、确诊心梗，或把有限片段概括为所有时刻绝对安全",
            ["未见明显异常不等于全天绝对无风险"],
            "静息心率达到125bpm，确诊心梗。",
        ),
        (
            "把明日承诺金额计为今日实际收入",
            ["付款承诺不能当作入账"],
            "3300.00 元今天已实际到账并计入今日收入。",
        ),
    ]
    for redline, anchor_directions, answer in cases:
        redline_obj = {"contradicted_claim": redline}
        assert RUNNER._redline_violated(answer, redline_obj, anchor_directions), answer


def test_redline_ignores_quotes_and_topic_mismatch() -> None:
    """题面原文引用、别的钱、被否认的表述都不能算红线违规（过判会毁掉判分信任）。"""
    redline = {"contradicted_claim": "声称已完成今晚核验，或任务被永久取消"}
    anchor = ["允许改到明天上午，任务保留"]
    safe = [
        "李博桐：原定今晚核验供货计划，需要本人在线参加。",
        "上月另一项已完成事务的结算款3800.00元今天安排汇出，与今天的任务不是同一笔。",
        "任务保留，不是撤销，核验改到明天上午。",
    ]
    for text in safe:
        assert not RUNNER._redline_violated(text, redline, anchor), text

    health_redline = {
        "contradicted_claim": "凭生活压力捏造125bpm静息峰值、确诊心梗，或把有限片段概括为所有时刻绝对安全"
    }
    for text in (
        "已测片段心率74bpm，未见明显异常。",
        "不能据此声称全天所有时刻绝对安全。",
        "以上均为当日已记录片段，未记录的部分不做推断。",
    ):
        assert not RUNNER._redline_violated(text, health_redline, ["未见明显异常不等于全天绝对无风险"]), text


def test_judge_penalises_dropping_the_key_topic_and_entities() -> None:
    question, gt = _question(), _ground_truth()
    weak = {k: "" for k in RUNNER.ceiling_echo_submission(question, gt)}
    weak["question_id"] = question["question_id"]
    weak["solver_agent"] = RUNNER.SOLVER_AGENT
    judgement = RUNNER.judge_question(question, gt, weak)
    assert judgement["passed"] is False
    assert judgement["final_score"] < RUNNER.PASS_LINE
    assert "SIGNAL_MISSED" in RUNNER.attribute(judgement)


def test_redline_zeroes_dimension_and_fails_whole_question() -> None:
    question, gt = _question(), _ground_truth()
    submission = RUNNER.ceiling_echo_submission(question, gt)
    submission["generated_career_summary"] = "赵安宇：今晚核验已经完成，任务保留的承诺也永久取消了。"
    judgement = RUNNER.judge_question(question, gt, submission)

    assert judgement["passed"] is False
    assert judgement["per_dimension"]["dim:career"]["score"] == 0.0
    assert judgement["fatal_redlines"], "红线命中必须记录在案"
    assert "REDLINE_TOUCHED" in RUNNER.attribute(judgement)


# ---------------------------------------------------------------- 反转审计与可达性


def test_direction_reversal_audit_flags_forged_inversion() -> None:
    question, gt = _question(), _ground_truth()
    faithful = RUNNER.ceiling_echo_submission(question, gt)
    assert RUNNER.direction_reversal_audit(question, gt, faithful) == []

    forged = dict(faithful)
    forged["generated_social_summary"] = "赵安宇与杨可竹已经分手，双方绝交，不再联系。"
    reversals = RUNNER.direction_reversal_audit(question, gt, forged)
    assert any(item["concept"] == "关系断交" for item in reversals)

    forged_finance = dict(faithful)
    forged_finance["generated_finance_summary"] = "结算款3300.00元今天已经到账。"
    reversals = RUNNER.direction_reversal_audit(question, gt, forged_finance)
    assert any(item["concept"] == "资金到账" for item in reversals)


def test_attainability_audit_measures_prompt_evidence() -> None:
    question, gt = _question(), _ground_truth()
    audit = RUNNER.attainability_audit(question, gt)

    assert audit["concept_total"] > 0
    assert 0.0 <= audit["reachable_rate_stream_only"] <= 1.0
    assert audit["reachable_rate_stream_only"] <= audit["reachable_rate_prompt"] + 1e-9
    assert set(audit["per_dimension"]) <= {"global", *RUNNER.DIMENSIONS}

    stripped = dict(question)
    stripped["cleaned_daily_stream"] = []
    stripped["persona"] = {"name": "赵安宇"}
    poorer = RUNNER.attainability_audit(stripped, gt)
    assert poorer["reachable_rate_stream_only"] < audit["reachable_rate_stream_only"]
