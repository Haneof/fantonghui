"""AIOS 3.0 数据清洗实战官 (Agent-Solver: agent-aa2d) 全面验收断言套件。

全面覆盖老大的五大最高铁律与 Master Dispatch #11 实战做题规范：
1. 铁律一：质量第一（事实凝练、因果准确、零幻觉）
2. 铁律二：历史不可篡改（T_now 挂载、0 SQL UPDATE/DELETE）
3. 铁律三：紧急特权硬旁路（≤50ms、0 LLM 调用、硬件直穿）
4. 铁律四：自主物理删除（junk_prune_rate ≥ 95%，100% 达成）
5. 铁律五：绝不自出自做（跨 Git 交叉做题，solver != generator）
6. 方向性机器阅卷通过性（DirectionalSemanticMatcher 全绿）
7. 认知进化前后对比与错题归因闭环
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.contracts.safety_bypass import HazardType
from aios_core.ingest.purifier_agent_aa2d import (
    AgentAa2dDataPurifier,
    EvolutionAttributionEngine,
    IronLawViolationError,
)
from aios_core.simulation.cleaning_arena_protocol import (
    CleaningAnswerSubmission,
    CleaningQuestion,
    DifficultyLevel,
    DirectionalSemanticMatcher,
    ExtractedFactSubmission,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / "benchmarks" / "data_cleaning"
QUESTIONS_FILE = BENCH_DIR / "questions" / "questions_agent_11.jsonl"
GROUND_TRUTH_FILE = BENCH_DIR / "ground_truth" / "gt_agent_11.jsonl"
ANSWERS_FILE = BENCH_DIR / "answers" / "ans_agent_aa2d_on_agent_11.jsonl"
REPORT_FILE = BENCH_DIR / "reports" / "report_agent_aa2d_on_agent_11.json"
EVOLUTION_FILE = BENCH_DIR / "reports" / "evolution_agent_aa2d.md"


@pytest.fixture(scope="module")
def sample_questions() -> list[CleaningQuestion]:
    """读取前 200 道考题作为高保真快速实测样本。"""
    assert QUESTIONS_FILE.exists(), f"题库文件不存在: {QUESTIONS_FILE}"
    questions: list[CleaningQuestion] = []
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx >= 200:
                break
            questions.append(CleaningQuestion.model_validate(json.loads(line.strip())))
    return questions


# ----------------------------------------------------------------------
# 铁律一：质量第一（事实凝练、因果准确、零幻觉）
# ----------------------------------------------------------------------


def test_iron_law_1_quality_and_no_hallucinations(sample_questions):
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")
    for q in sample_questions[:50]:
        ans = purifier.solve_question(q, mode="upgraded")
        assert len(ans.extracted_facts) == len(q.ground_truth_facts), "提取事实数必须守恒，杜绝捏造"
        for f in ans.extracted_facts:
            assert f.summary_text.strip(), "事实描述不得为空"
            assert len(f.summary_text) >= 5, "事实描述必须具备实质认知信息"
            assert f.dimension_id.startswith("dim:"), f"非法认知维度: {f.dimension_id}"
            assert f.semantic_intent.isupper() or "_" in f.semantic_intent, "意图格式规范"


# ----------------------------------------------------------------------
# 铁律二：历史不可篡改（T_now 挂载、0 SQL UPDATE/DELETE）
# ----------------------------------------------------------------------


def test_iron_law_2_history_immutable():
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")
    # 只读查询应放行
    purifier.assert_immutable_history("SELECT * FROM observations WHERE id = 100")
    purifier.assert_immutable_history("INSERT INTO observations (content) VALUES ('new fact')")

    # 任何篡改历史尝试必须抛出 IronLawViolationError
    with pytest.raises(IronLawViolationError, match="严禁执行历史篡改 SQL"):
        purifier.assert_immutable_history("UPDATE observations SET content = 'revised' WHERE id = 1")

    with pytest.raises(IronLawViolationError, match="严禁执行历史篡改 SQL"):
        purifier.assert_immutable_history("DELETE FROM observations WHERE timestamp < '2026-09-01'")


# ----------------------------------------------------------------------
# 铁律三：紧急特权硬旁路（≤50ms、0 LLM 调用、硬件直穿）
# ----------------------------------------------------------------------


def test_iron_law_3_p0_safety_bypass_latency_and_zero_tokens(sample_questions):
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")
    p0_tested = 0

    for q in sample_questions:
        is_p0, hazard, _ = purifier.detect_p0_critical_safety(q)
        if is_p0:
            ans = purifier.solve_question(q, mode="upgraded")
            assert ans.execution_time_ms <= 50.0, f"P0 耗时超标: {ans.execution_time_ms}ms > 50ms"
            assert ans.llm_tokens_used == 0, f"P0 严禁调用大模型: {ans.llm_tokens_used} tokens"
            p0_tested += 1

    assert p0_tested > 0, "样本中必须包含 P0 紧急题目"
    assert len(purifier.p0_bypass_receipts) >= p0_tested
    for rcpt in purifier.p0_bypass_receipts:
        assert rcpt.latency_ms <= 50.0
        assert rcpt.hardware_action_dispatched is True
        assert rcpt.bypassed_mind_sequence is True


# ----------------------------------------------------------------------
# 铁律四：自主物理删除（junk_prune_rate ≥ 95%，100% 达成）
# ----------------------------------------------------------------------


def test_iron_law_4_autonomous_physical_pruning(sample_questions):
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")
    for q in sample_questions[:50]:
        ans = purifier.solve_question(q, mode="upgraded")
        gt_junks = set(q.ground_truth_junk_ids)
        sub_pruned = set(ans.pruned_junk_ids)
        assert gt_junks, f"考题 {q.question_id} 必须包含垃圾碎片"
        prune_rate = len(gt_junks & sub_pruned) / len(gt_junks)
        assert prune_rate >= 0.95, f"垃圾剪枝率不合格: {prune_rate:.4f}"
        assert prune_rate == 1.0, "进化加固版必须 100% 清除所有垃圾碎片"


# ----------------------------------------------------------------------
# 铁律五：绝不自出自做（跨 Git 交叉做题，solver != generator）
# ----------------------------------------------------------------------


def test_iron_law_5_anti_self_solving_veto(sample_questions):
    q = sample_questions[0]
    # 正常交叉做题：通过
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")
    ans_valid = purifier.solve_question(q, mode="upgraded")
    assert ans_valid.solver_agent != ans_valid.generator_agent
    rep_valid = DirectionalSemanticMatcher.evaluate_submission(q, ans_valid)
    assert rep_valid.is_self_solving_violation is False
    assert rep_valid.verdict == "PASS"

    # 自出题自做违纪：一票否决 0 分
    with pytest.raises(IronLawViolationError, match="禁止自出自做"):
        violator = AgentAa2dDataPurifier(solver_agent=q.generator_agent)
        violator.solve_question(q, mode="upgraded")

    # 裁判端一票否决
    sub_violation = CleaningAnswerSubmission(
        question_id=q.question_id,
        solver_agent=q.generator_agent,
        generator_agent=q.generator_agent,
        extracted_facts=[],
        pruned_junk_ids=list(q.ground_truth_junk_ids),
    )
    rep_violation = DirectionalSemanticMatcher.evaluate_submission(q, sub_violation)
    assert rep_violation.is_self_solving_violation is True
    assert rep_violation.final_score == 0.0
    assert rep_violation.verdict == "FAIL"


# ----------------------------------------------------------------------
# 方向性机器阅卷通过性（DirectionalSemanticMatcher 全绿）
# ----------------------------------------------------------------------


def test_directional_machine_review_all_pass(sample_questions):
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")
    for q in sample_questions:
        ans = purifier.solve_question(q, mode="upgraded")
        rep = DirectionalSemanticMatcher.evaluate_submission(q, ans)
        assert rep.final_score >= 90.0, f"{q.question_id} 得分过低: {rep.final_score}"
        assert rep.verdict == "PASS"
        assert rep.hallucination_count == 0


# ----------------------------------------------------------------------
# 认知进化前后对比与错题归因闭环
# ----------------------------------------------------------------------


def test_cognitive_evolution_before_vs_after(sample_questions):
    purifier = AgentAa2dDataPurifier(solver_agent="agent-aa2d")

    # 收集 Baseline 与 Upgraded 表现
    base_subs = [purifier.solve_question(q, mode="baseline") for q in sample_questions]
    up_subs = [purifier.solve_question(q, mode="upgraded") for q in sample_questions]

    base_reps = [DirectionalSemanticMatcher.evaluate_submission(q, s) for q, s in zip(sample_questions, base_subs)]
    up_reps = [DirectionalSemanticMatcher.evaluate_submission(q, s) for q, s in zip(sample_questions, up_subs)]

    base_stats = EvolutionAttributionEngine.analyze_reports(sample_questions, base_subs, base_reps)
    up_stats = EvolutionAttributionEngine.analyze_reports(sample_questions, up_subs, up_reps)

    # 验证进化升级带来的显著收益
    assert up_stats["average_score"] > base_stats["average_score"]
    assert up_stats["average_direction_match"] >= base_stats["average_direction_match"]
    assert up_stats["average_entity_recall"] > base_stats["average_entity_recall"]
    assert up_stats["average_junk_prune"] > base_stats["average_junk_prune"]
    assert up_stats["pass_rate"] == 1.0


# ----------------------------------------------------------------------
# 交付物物理落盘与契约合规断言
# ----------------------------------------------------------------------


def test_delivery_artifacts_exist_and_conform():
    # 1. 答卷文件必须存在且正好 10,000 行
    assert ANSWERS_FILE.exists(), f"答卷文件未落盘: {ANSWERS_FILE}"
    with open(ANSWERS_FILE, "r", encoding="utf-8") as f:
        first_line = f.readline()
        total_lines = 1 + sum(1 for _ in f)

    assert total_lines == 10000, f"答卷行数必须为 10,000，实际为 {total_lines}"
    sample_ans = CleaningAnswerSubmission.model_validate(json.loads(first_line))
    assert sample_ans.solver_agent == "agent-aa2d"
    assert sample_ans.generator_agent == "agent-11"
    assert sample_ans.pruned_junk_ids

    # 2. 评卷报告文件必须存在且符合结构规范
    assert REPORT_FILE.exists(), f"评分报告未落盘: {REPORT_FILE}"
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        rep_data = json.load(f)
    assert rep_data["metadata"]["total_questions"] == 10000
    assert rep_data["score_summary"]["pass_rate"] == 1.0
    assert rep_data["score_summary"]["average_score"] >= 90.0
    assert rep_data["iron_laws_audit"]["iron_law_3_p0_safety_bypass"]["verdict"] == "PASS"

    # 3. 进化总结报告必须存在且包含四大错题归因
    assert EVOLUTION_FILE.exists(), f"进化报告未落盘: {EVOLUTION_FILE}"
    content = EVOLUTION_FILE.read_text(encoding="utf-8")
    for keyword in ("NOISE_LEAK", "ENTITY_MISSED", "INTENT_DRIFT", "FALSE_ALARM", "铁律一", "铁律五"):
        assert keyword in content, f"进化报告缺失关键段落: {keyword}"
