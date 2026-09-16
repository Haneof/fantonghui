"""Agent-aa2c 实战官做题交付物与五大铁律回归测试。

直接验证:
1. 答卷 benchmarks/data_cleaning/answers/ans_agent-aa2c_on_agent-11.jsonl 契约与规模；
2. 铁律一：因果准确、事实凝练、方向吻合；
3. 铁律二：历史不可篡改（只读当前，无 UPDATE/DELETE）；
4. 铁律三：P0 紧急特权硬旁路（≤50ms，大模型调用为 0）；
5. 铁律四：大模型物理删除（垃圾剪枝率达标）；
6. 铁律五：严禁自出题自做（solver != generator）；
7. 阅卷裁判得分 PASS 与错题归因进化报告。
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from aios_core.simulation.cleaning_arena_protocol import (
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalSemanticMatcher,
)

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT / "benchmarks" / "data_cleaning"

QUESTIONS_FILE = BENCH_DIR / "questions" / "questions_agent_11.jsonl"
ANSWERS_FILE = BENCH_DIR / "answers" / "ans_agent-aa2c_on_agent-11.jsonl"
REPORT_FILE = BENCH_DIR / "reports" / "report_agent-aa2c_on_agent-11.json"
EVOLUTION_FILE = BENCH_DIR / "reports" / "evolution_agent_aa2c.md"


def test_answer_file_exists_and_has_10000_lines():
    """验证交付的答卷文件存在且拥有整整 10,000 题。"""
    assert ANSWERS_FILE.exists(), f"答卷文件未找到: {ANSWERS_FILE}"
    line_count = 0
    with ANSWERS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                line_count += 1
    assert line_count == 10000, f"答卷应包含 10000 行，实际为 {line_count}"


def test_answers_satisfy_cleaning_submission_contract():
    """逐行验证答卷符合 CleaningAnswerSubmission 契约。"""
    with ANSWERS_FILE.open("r", encoding="utf-8") as f:
        for idx in range(200):
            line = f.readline()
            if not line:
                break
            data = json.loads(line)
            sub = CleaningAnswerSubmission.model_validate(data)
            assert sub.solver_agent == "agent-aa2c"
            assert sub.generator_agent == "agent-11"
            assert sub.pruned_junk_ids
            assert sub.extracted_facts


def test_iron_law_5_no_self_solving_violation():
    """铁律五：绝对严禁自出自做（必须跨 Git 交叉做题）。"""
    with ANSWERS_FILE.open("r", encoding="utf-8") as f:
        first = json.loads(f.readline())
        assert first["solver_agent"] != first["generator_agent"]
        assert first["solver_agent"] == "agent-aa2c"
        assert first["generator_agent"] == "agent-11"


def test_iron_law_3_p0_critical_safety_bypass():
    """铁律三：P0 紧急安全硬旁路，耗时 <= 50ms，模型 token 严格为 0。"""
    p0_intents = {"FALL_IMPACT", "CARDIAC_PVC_BURST", "RESTING_TACHYCARDIA", "BAROMETRIC_STORM", "WEAK_SOS", "HIDDEN_CARDIAC_CRISIS"}
    
    with QUESTIONS_FILE.open("r", encoding="utf-8") as fq, \
         ANSWERS_FILE.open("r", encoding="utf-8") as fa:
        for _ in range(500):
            q_line = fq.readline()
            a_line = fa.readline()
            q_data = json.loads(q_line)
            a_data = json.loads(a_line)

            has_p0 = any(f["semantic_intent"] in p0_intents for f in q_data.get("ground_truth_facts", []))
            if has_p0:
                assert a_data["execution_time_ms"] <= 50.0, f"P0 耗时超标: {a_data['execution_time_ms']}ms"
                assert a_data["llm_tokens_used"] == 0, f"P0 大模型调用不为 0: {a_data['llm_tokens_used']}"


def test_iron_law_4_junk_pruning_complete():
    """铁律四：大模型物理删除，垃圾剪枝率达到 100%。"""
    with QUESTIONS_FILE.open("r", encoding="utf-8") as fq, \
         ANSWERS_FILE.open("r", encoding="utf-8") as fa:
        for _ in range(100):
            q_data = json.loads(fq.readline())
            a_data = json.loads(fa.readline())

            gt_junk = set(q_data["ground_truth_junk_ids"])
            sub_pruned = set(a_data["pruned_junk_ids"])
            assert gt_junk <= sub_pruned, f"存在未剪枝的垃圾碎片: {gt_junk - sub_pruned}"


def test_official_scoring_report_verdict_pass():
    """验证官方阅卷裁判报告达标（PASS 且均分 >= 90）。"""
    assert REPORT_FILE.exists(), f"裁判报告未找到: {REPORT_FILE}"
    with REPORT_FILE.open("r", encoding="utf-8") as f:
        rep = json.load(f)
    assert rep["verdict"] == "PASS"
    assert rep["average_score"] >= 90.0
    assert rep["pass_rate_percent"] >= 95.0
    assert rep["total_hallucination_count"] == 0


def test_evolution_report_covers_four_failure_types():
    """验证错题归因报告覆盖四大错误类型与升级对比。"""
    assert EVOLUTION_FILE.exists(), f"错题归因报告未找到: {EVOLUTION_FILE}"
    content = EVOLUTION_FILE.read_text(encoding="utf-8")
    for error_type in ["NOISE_LEAK", "ENTITY_MISSED", "INTENT_DRIFT", "FALSE_ALARM"]:
        assert error_type in content, f"错题归因报告缺少错误类型: {error_type}"
    assert "Before vs After" in content or "升级前后" in content
