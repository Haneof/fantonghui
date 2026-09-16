"""AIOS 3.0 全天生活流多维总结做题交付物与红线测试。

验证：
1. 答卷规模满额 10,000 题；
2. 铁律五：严禁自出自做（solver 01a0aa2c != generator 01a0aa2d）；
3. 官方裁判评分 PASS 且得分 >= 80.0；
4. 绝对红线触碰违例数为 0；
5. 六大维度总结完整。
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

ROOT = Path(__file__).resolve().parents[2]
BANK_DIR = ROOT / "benchmarks" / "daily_summary"

QUESTIONS_FILE = BANK_DIR / "questions" / "questions_01a0aa2d-fantonghui.jsonl"
ANSWERS_FILE = BANK_DIR / "answers" / "ans_01a0aa2c_on_01a0aa2d.jsonl"
REPORT_FILE = BANK_DIR / "reports" / "report_01a0aa2c_on_01a0aa2d.json"
EVOLUTION_FILE = BANK_DIR / "reports" / "evolution_daily_summary_01a0aa2c.md"


def test_cross_branch_answers_has_10000_lines():
    """验证做题答卷包含整整 10,000 道题。"""
    assert ANSWERS_FILE.exists(), f"答卷未找到: {ANSWERS_FILE}"
    count = 0
    with ANSWERS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    assert count == 10000, f"答卷题数应为 10000，实际为 {count}"


def test_iron_law_5_no_self_solving_violation():
    """铁律五：绝不自出自做（做题人 != 出卷人）。"""
    with ANSWERS_FILE.open("r", encoding="utf-8") as f:
        first = json.loads(f.readline())
        assert first["solver_agent"] == "01a0aa2c-fantonghui"
        assert first["solver_agent"] != "01a0aa2d-fantonghui"


def test_answers_satisfy_daily_summary_submission_contract():
    """验证答卷符合 DailySummarySubmission 契约。"""
    with ANSWERS_FILE.open("r", encoding="utf-8") as f:
        for idx in range(100):
            line = f.readline()
            data = json.loads(line)
            sub = DailySummarySubmission.model_validate(data)
            assert sub.generated_global_summary
            assert sub.generated_health_summary
            assert sub.generated_social_summary
            assert sub.generated_emotion_summary
            assert sub.generated_finance_summary
            assert sub.generated_career_summary


def test_official_scoring_report_pass_and_zero_redlines():
    """验证官方阅卷裁判结果：PASS、均分>=80分、0次触碰红线。"""
    assert REPORT_FILE.exists(), f"报告未找到: {REPORT_FILE}"
    with REPORT_FILE.open("r", encoding="utf-8") as f:
        rep = json.load(f)
    assert rep["verdict"] == "PASS"
    assert rep["average_score"] >= 80.0
    assert rep["fatal_redline_violations"] == 0
    assert rep["pass_rate_percent"] >= 95.0
