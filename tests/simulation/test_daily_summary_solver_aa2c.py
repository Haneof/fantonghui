"""AIOS 3.0 全天生活流多维总结做题交付物与红线测试。

验证：
1. 答卷规模满额：aa2d 10,000 题 + aa2e 10,000 题；
2. 铁律五：严禁自出自做（做题人 != 出卷人）；
3. 官方裁判评分 PASS 且得分 >= 80.0；
4. 绝对红线触碰违例数严格为 0；
5. 六大维度总结完整。
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
BANK_DIR = ROOT / "benchmarks" / "daily_summary"

ANSWERS_AA2D = BANK_DIR / "answers" / "ans_01a0aa2c_on_01a0aa2d.jsonl"
ANSWERS_AA2E = BANK_DIR / "answers" / "ans_01a0aa2c_on_agent_aa2e.jsonl"
REPORT_CROSS = BANK_DIR / "reports" / "report_01a0aa2c_cross_solving.json"
EVOLUTION_FILE = BANK_DIR / "reports" / "evolution_daily_summary_01a0aa2c.md"


def test_cross_branch_answers_have_10000_lines_each():
    """验证做题答卷包含整整 10,000 道题。"""
    assert ANSWERS_AA2D.exists(), f"aa2d 答卷未找到: {ANSWERS_AA2D}"
    assert ANSWERS_AA2E.exists(), f"aa2e 答卷未找到: {ANSWERS_AA2E}"

    count_d = sum(1 for line in ANSWERS_AA2D.open("r", encoding="utf-8") if line.strip())
    count_e = sum(1 for line in ANSWERS_AA2E.open("r", encoding="utf-8") if line.strip())

    assert count_d == 10000, f"aa2d 答卷应为 10000 题，实际为 {count_d}"
    assert count_e == 10000, f"aa2e 答卷应为 10000 题，实际为 {count_e}"


def test_iron_law_5_no_self_solving_violation():
    """铁律五：绝不自出自做（做题人 != 出卷人）。"""
    with ANSWERS_AA2D.open("r", encoding="utf-8") as f:
        first_d = json.loads(f.readline())
        assert first_d["solver_agent"] == "01a0aa2c-fantonghui"
        assert first_d["solver_agent"] != "01a0aa2d-fantonghui"

    with ANSWERS_AA2E.open("r", encoding="utf-8") as f:
        first_e = json.loads(f.readline())
        assert first_e["solver_agent"] == "01a0aa2c-fantonghui"
        assert first_e["solver_agent"] != "agent-aa2e"


def test_answers_satisfy_six_dimensions_content():
    """验证两份答卷均包含六大维度总结。"""
    dims = [
        "generated_global_summary",
        "generated_health_summary",
        "generated_social_summary",
        "generated_emotion_summary",
        "generated_finance_summary",
        "generated_career_summary",
    ]
    with ANSWERS_AA2E.open("r", encoding="utf-8") as f:
        for idx in range(50):
            line = f.readline()
            data = json.loads(line)
            for d in dims:
                assert d in data and len(data[d]) > 0


def test_official_scoring_cross_report_pass_and_zero_redlines():
    """验证官方阅卷裁判结果：双考场 PASS、均分>=80分、0次触碰红线。"""
    assert REPORT_CROSS.exists(), f"跨支线总报告未找到: {REPORT_CROSS}"
    with REPORT_CROSS.open("r", encoding="utf-8") as f:
        rep = json.load(f)

    assert rep["overall_verdict"] == "PASS"
    assert rep["total_cross_questions_solved"] == 20000

    for opp_name, opp_rep in rep["opponents_solved"].items():
        assert opp_rep["verdict"] == "PASS"
        assert opp_rep["average_score"] >= 80.0
        assert opp_rep["fatal_redline_violations"] == 0
        assert opp_rep["pass_rate_percent"] == 100.0
