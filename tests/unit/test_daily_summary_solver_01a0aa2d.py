"""全天生活流与多维总结竞技场·做题方引擎（01a0aa2d-fantonghui）验收单测。

硬门禁：
1. 盲做纪律：标答字段必须在进入总结器前被物理剥离，答案不得泄露标答内容；
2. 孤律五：遇到本战队自有考卷必须拒绝作答（自出自做一票否决）；
3. 方向性判分口径：命中可接受方向同义词得高分、踩中红线直接 0 分（官方裁判器）；
4. 否定/极性护栏：否定语境（“千万别销毁证据”）与他人祝福（“祝你幸福”）不得写进总结；
5. 确定性：同卷重跑逐字节一致；
6. 已交付答卷与阅卷报告一致性（红线 0 触碰）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aios_core.simulation.daily_summary_solver_01a0aa2d import (
    SOLVER_AGENT,
    blind_question,
    load_ground_truth,
    solve_stream_bank,
    summarize_question,
)

pytest.importorskip("pydantic")

DEMO = {
    "question_id": "Q_demo_0001",
    "generator_agent": "agent-other",
    "persona": {"name": "苏晴", "age": 31, "occupation": "财务专员"},
    "cleaned_daily_stream": {
        "date_span": "07:00~23:30",
        "events": [
            {"time": "07:00", "channel": "SENSOR", "content": "晨起静息心率84bpm，昨夜睡眠4.2小时，全天步数5053步。"},
            {"time": "09:38", "channel": "APP", "content": "开盘买的基金组合直接砸跌停, 浮亏12万, 手抖得拿不住手机"},
            {"time": "12:26", "channel": "MIC", "content": "电话里为胎心仪吵起来: 我妈嫌贵说智商税, 我说身体要紧互不相让"},
            {"time": "14:24", "channel": "APP", "content": "紧急约税务顾问: 对方说主动补正争取从轻, 千万别销毁证据"},
            {"time": "19:26", "channel": "APP", "content": "女友: 你根本没时间谈恋爱, 祝你幸福[对方已开启朋友验证]"},
            {"time": "22:52", "channel": "MIC", "content": "半夜拿计算器一笔笔算, 浮亏12万加搭进去的3万要不回来, 整宿失眠没睡"},
        ],
    },
    "directional_ground_truth": {"global_daily_summary": {"core_content": "标答正文不得出现在答卷里"}},
}


def _write_bank(tmp_path: Path, rows: list[dict], name: str = "bank.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


def test_selftest_passes():
    from aios_core.simulation.daily_summary_solver_01a0aa2d import selftest

    assert selftest() == 0


def test_blind_discipline_and_no_label_leak():
    blind = blind_question(DEMO)
    assert "directional_ground_truth" not in blind
    assert blind["_blind"] is True
    answer = summarize_question(blind)
    joined = " ".join(str(v) for v in answer.values())
    assert "标答正文不得出现在答卷里" not in joined
    assert answer["solver_agent"] == SOLVER_AGENT


def test_summarize_requires_blind_question():
    with pytest.raises(AssertionError):
        summarize_question(dict(DEMO))  # 未剥离标答 → 必须拒绝


def test_never_solve_own_bank(tmp_path: Path):
    own = dict(DEMO)
    own["generator_agent"] = SOLVER_AGENT
    own["question_id"] = f"Q_{SOLVER_AGENT}_00001"
    bank = _write_bank(tmp_path, [own])
    with pytest.raises(SystemExit):
        solve_stream_bank(bank, tmp_path / "ans.jsonl")


def test_polarity_and_negation_guards():
    answer = summarize_question(blind_question(DEMO))
    emotion = answer["generated_emotion_summary"]
    social = answer["generated_social_summary"]
    assert "幸福" not in emotion, "他人祝福（祝你幸福）不得当成本人情绪"
    assert "销毁证据" not in " ".join(str(v) for v in answer.values()), "否定语境不得写进总结"
    assert any(word in social for word in ("争吵", "冲突", "争执", "婆媳", "观念")), "争执事实必须上报"
    assert "浮亏" in answer["generated_finance_summary"]
    assert "失眠" in answer["generated_health_summary"] or "睡眠" in answer["generated_health_summary"]


def test_grading_is_directional_not_literal(tmp_path: Path):
    """吵架 vs 吵闹：方向簇命中应给分；触碰红线一票否决。"""
    from aios_core.simulation.daily_summary_solver_01a0aa2d import grade_answers

    bank = _write_bank(tmp_path, [DEMO, dict(DEMO, question_id="Q_demo_0002")])
    gt = {
        "Q_demo_0001": {
            "global_daily_summary": {"core_content": "因投资巨亏与家人冲突失眠", "acceptable_directions": ["投资巨亏", "家人争吵", "失眠算账"],
                                     "forbidden_directions": ["投资大赚"], "anchor_entities": ["浮亏12万"]},
            "dim:finance": {"core_content": "基金浮亏12万", "acceptable_directions": ["浮亏12万", "资产缩水"],
                            "forbidden_directions": ["盈利", "回本"], "anchor_entities": ["浮亏12万"]},
        },
        "Q_demo_0002": {
            "dim:finance": {"core_content": "基金浮亏12万", "acceptable_directions": ["浮亏12万"],
                            "forbidden_directions": ["浮亏12万"], "anchor_entities": []},
        },
    }
    gt_path = tmp_path / "gt.jsonl"
    gt_path.write_text("".join(json.dumps({"question_id": qid, "directional_ground_truth": payload}, ensure_ascii=False) + "\n"
                               for qid, payload in gt.items()), encoding="utf-8")
    answers = tmp_path / "ans.jsonl"
    solve_stream_bank(bank, answers)
    report = grade_answers(bank, load_ground_truth(bank, gt_path), answers, tmp_path / "report.json")
    assert report["questions_graded"] == 2
    # 第 1 题：方向同义词命中 → 财务维度得分不为 0
    assert report["dimension_mean_scores"]["dim:finance"] > 0
    # 第 2 题：标答把“浮亏12万”同时列为红线 → 一票否决触发
    assert report["fatal_redline_hits"] >= 1


def test_solver_is_deterministic(tmp_path: Path):
    bank = _write_bank(tmp_path, [dict(DEMO, question_id="Q_demo_0003"), dict(DEMO, question_id="Q_demo_0004")])
    first = tmp_path / "a.jsonl"
    second = tmp_path / "b.jsonl"
    solve_stream_bank(bank, first)
    solve_stream_bank(bank, second)
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest()


def test_delivered_daily_banks_report_zero_redlines():
    """已交付答卷：题量、红线零触碰、无自出自做。"""
    root = Path(__file__).resolve().parents[2]
    cases = {
        "agent-aa2c": (10_000, "ans_01a0aa2d-fantonghui_on_agent-aa2c_blind.jsonl"),
        "agent-aa2e": (10_000, "ans_01a0aa2d-fantonghui_on_agent-aa2e_blind.jsonl"),
        "agent-01a0aa2c": (1_000, "ans_01a0aa2d-fantonghui_on_agent-01a0aa2c_blind.jsonl"),
    }
    checked = 0
    for gen, (expected, answers_name) in cases.items():
        answers = root / "benchmarks/daily_summary/answers" / answers_name
        report_path = root / f"benchmarks/daily_summary/reports/report_01a0aa2d-fantonghui_on_{gen}_blind.json"
        if not (answers.exists() and report_path.exists()):
            continue
        rows = [json.loads(line) for line in answers.open(encoding="utf-8")]
        assert len(rows) == expected
        assert all(row["solver_agent"] == SOLVER_AGENT for row in rows)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["fatal_redline_hits"] == 0, f"{gen} 触碰红线"
        assert report["questions_graded"] == expected
        checked += 1
    if not checked:
        pytest.skip("交付答卷不在当前工作区")
