"""出卷官 01a0aa2d 高熵题库发生器的验收单测（工序一：1 万个人的一天）。

硬门禁断言：
1. 信号/垃圾目录自检通过：每条标答事实的方向词簇与实体锚点都能在证据文本中命中；
2. 确定性：同一 seed 重跑逐字节一致（sha256 相同）；
3. 公平性不变量：标答载体全部可溯源、实体全落地、垃圾占比 >= 95%；
4. 契约兼容：题目 + 标答可被主干 ``CleaningQuestion`` 契约校验；
5. 配额：数据流 30/30/20/15/5、难度、事实条数分布按调度书比例铺满。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.simulation.question_generator_01a0aa2d import (
    ANCHOR_DIMS,
    DEFAULT_SEED,
    GENERATOR_AGENT,
    verify_bank,
)

pytest.importorskip("pydantic")


def _generate(tmp_path: Path, count: int = 60) -> tuple[Path, Path, dict]:
    from aios_core.simulation.question_generator_01a0aa2d import generate

    questions = tmp_path / "questions.jsonl"
    gt = tmp_path / "gt.jsonl"
    summary = generate(count, DEFAULT_SEED, questions, gt, progress=False)
    return questions, gt, summary


def test_signal_catalog_selftest_passes():
    from aios_core.simulation.question_generator_01a0aa2d import selftest

    assert selftest() == 0


def test_generated_bank_meets_fairness_invariants(tmp_path: Path):
    questions, gt, summary = _generate(tmp_path)
    verify = summary["verify"]
    assert verify["problem_total"] == 0, verify["problems"]
    counters = verify["counters"]
    assert counters["questions"] == 60
    assert counters["source_ok"] == counters["facts"]
    assert counters["entity_ok"] == counters["facts"]
    assert counters["keyword_ok"] == counters["facts"]
    assert counters["pydantic_ok"] == 60
    assert counters["junk_ratio_min"] >= 0.95

    first = json.loads(questions.read_text(encoding="utf-8").splitlines()[0])
    assert first["generator_agent"] == GENERATOR_AGENT
    assert first["question_id"].startswith(f"Q_{GENERATOR_AGENT}_")
    dgt = first["directional_ground_truth"]
    assert "global_summary" in dgt
    for dim in ANCHOR_DIMS:
        assert dim in dgt, f"方向性标答缺少维度锚点 {dim}"
    for key, value in dgt.items():
        if isinstance(value, dict) and "core" in value:
            assert value["red_lines"], f"{key} 缺少绝对偏离红线"
    assert first["cleaned_daily_stream"]["window"] == "07:00-23:30"


def test_generator_is_deterministic(tmp_path: Path):
    a_q, a_g, a_s = _generate(tmp_path / "a")
    b_q, b_g, b_s = _generate(tmp_path / "b")
    assert a_s["questions_sha256"] == b_s["questions_sha256"]
    assert a_s["ground_truth_sha256"] == b_s["ground_truth_sha256"]
    assert a_q.read_bytes() == b_q.read_bytes()


def test_quota_and_difficulty_mix(tmp_path: Path):
    _, _, summary = _generate(tmp_path, count=400)
    focus = summary["focus_counts"]
    assert set(focus) == {"sensor", "mic", "voiceprint", "app", "dialogue"}
    total = sum(focus.values())
    assert abs(focus["sensor"] / total - 0.30) < 0.05
    assert abs(focus["mic"] / total - 0.30) < 0.05
    assert abs(focus["voiceprint"] / total - 0.20) < 0.05
    assert abs(focus["app"] / total - 0.15) < 0.05
    assert abs(focus["dialogue"] / total - 0.05) < 0.05
    difficulty = summary["difficulty_counts"]
    assert set(difficulty) == {"EASY", "MEDIUM", "HARD", "ADVERSARIAL"}
    assert abs(difficulty["HARD"] / total - 0.35) < 0.05
    assert abs(difficulty["ADVERSARIAL"] / total - 0.15) < 0.05


def test_no_self_solving_possible(tmp_path: Path):
    """铁律五：本卷 generator_agent 恒为 01a0aa2d-fantonghui，跨 Git 交叉做题才可得分。"""
    questions, _, _ = _generate(tmp_path, count=10)
    for line in questions.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert row["generator_agent"] == GENERATOR_AGENT
        assert row["generator_agent"] != "fantonghui"


def test_verify_reports_problems_for_tampered_bank(tmp_path: Path):
    """反向校验：蓄意改坏标答后，校验器必须报错（避免“自证清白”的空转）。"""
    questions, gt, _ = _generate(tmp_path, count=5)
    rows = [json.loads(line) for line in gt.read_text(encoding="utf-8").splitlines()]
    rows[0]["ground_truth_facts"][0]["anchor_entities"].append("张三不存在")
    gt.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    result = verify_bank(questions, gt)
    assert result["problem_total"] > 0
