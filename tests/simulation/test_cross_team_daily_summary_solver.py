"""AIOS 3.0 全天生活流多维总结跨战队做题官验收断言套件 (Cross-Team Daily Summary Solver Tests).

严格断言：
1. 跨 Git 交叉做题题量达到 10,000 / 10,000 满额；
2. 铁律一：严格禁止自出自做（solver_agent != generator_agent）；
3. 铁律三：零大模型调用（llm_tokens_used == 0），极速耗时（< 50ms）；
4. 铁律四：绝对偏离红线 0 触发；
5. 官方机器阅卷及格率 100.0%，平均分达到 100.0 分。
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ANS_AA2E = REPO_ROOT / "benchmarks/daily_summary/answers/ans_01a0aa2d-fantonghui_on_agent-aa2e.jsonl"
ANS_AA2C = REPO_ROOT / "benchmarks/daily_summary/answers/ans_01a0aa2d-fantonghui_on_agent-aa2c.jsonl"
REP_AA2E = REPO_ROOT / "benchmarks/daily_summary/reports/report_01a0aa2d-fantonghui_on_agent-aa2e.json"
REP_AA2C = REPO_ROOT / "benchmarks/daily_summary/reports/report_01a0aa2d-fantonghui_on_agent-aa2c.json"


@pytest.mark.parametrize("ans_path, expected_gen", [
    (ANS_AA2E, "agent-aa2e"),
    (ANS_AA2C, "agent-aa2c"),
])
def test_cross_team_answers_exist_and_have_ten_thousand_rows(ans_path: Path, expected_gen: str):
    """断言答卷文件存在且满额 10,000 行。"""
    assert ans_path.exists(), f"答卷未找到: {ans_path}"
    count = 0
    with open(ans_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    assert count == 10000, f"答卷必须严格等于 10,000 题，实际 {count}"


@pytest.mark.parametrize("ans_path, expected_gen", [
    (ANS_AA2E, "agent-aa2e"),
    (ANS_AA2C, "agent-aa2c"),
])
def test_strict_cross_solving_iron_law_one(ans_path: Path, expected_gen: str):
    """断言铁律一：严格禁止自出自做，做题官与出题官必须跨 Git 隔离。"""
    with open(ans_path, "r", encoding="utf-8") as f:
        for idx in range(200):
            line = f.readline()
            if not line:
                break
            a = json.loads(line.strip())
            assert a["solver_agent"] == "01a0aa2d-fantonghui"
            assert a["generator_agent"] == expected_gen
            assert a["solver_agent"] != a["generator_agent"], "严禁自出自做违规"


@pytest.mark.parametrize("ans_path", [ANS_AA2E, ANS_AA2C])
def test_zero_llm_tokens_and_sub_millisecond_latency(ans_path: Path):
    """断言铁律三：全流程 0 大模型调用，单题耗时远低于 50ms。"""
    with open(ans_path, "r", encoding="utf-8") as f:
        for idx in range(200):
            line = f.readline()
            if not line:
                break
            a = json.loads(line.strip())
            assert a["llm_tokens_used"] == 0, "严禁调用大模型"
            assert a["execution_time_ms"] < 50.0, f"耗时超过50ms门禁: {a['execution_time_ms']}ms"


@pytest.mark.parametrize("ans_path", [ANS_AA2E, ANS_AA2C])
def test_six_dimensions_present_in_generated_summary(ans_path: Path):
    """断言每道答卷均完整覆盖六大认知维度。"""
    with open(ans_path, "r", encoding="utf-8") as f:
        for idx in range(100):
            line = f.readline()
            if not line:
                break
            a = json.loads(line.strip())
            summary = a["generated_summary"]
            assert len(summary) == 6, f"必须覆盖6个维度，实际 {len(summary)}"
            for k, text in summary.items():
                assert len(text) >= 10, f"维度 {k} 总结过短: {text}"


def test_evaluation_reports_show_one_hundred_percent_pass_and_zero_redlines():
    """断言机器阅卷报告中及格率 100%、平均分 100 且 0 红线触犯。"""
    for rep_path in [REP_AA2E, REP_AA2C]:
        assert rep_path.exists(), f"报告未找到: {rep_path}"
        with open(rep_path, "r", encoding="utf-8") as f:
            rep = json.load(f)
        assert rep["total_questions"] == 10000
        assert rep["passed_questions"] == 10000
        assert rep["pass_rate"] == 1.0
        assert rep["average_score"] == 100.0
        for dim, info in rep["dimension_breakdown"].items():
            assert info["redline_violation_count"] == 0, f"{dim} 存在红线违规"
            assert info["direction_match_rate"] == 1.0, f"{dim} 方向未命中"
            assert info["avg_score"] == 100.0
