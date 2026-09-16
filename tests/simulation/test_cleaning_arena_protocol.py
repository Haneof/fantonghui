import pytest
import sys
from pathlib import Path


from aios_core.simulation.cleaning_arena_protocol import (
    CleaningQuestion,
    DirectionalSemanticFact,
    ExtractedFactSubmission,
    CleaningAnswerSubmission,
    DirectionalSemanticMatcher,
    DifficultyLevel
)


def test_directional_semantic_matching_synonyms():
    """测试老大的指示：不能事实是发生了吵架，模型提取成了吵闹就判错！"""
    gt_fact = DirectionalSemanticFact(
        fact_id="fact-001",
        dimension_id="dim:social",
        semantic_intent="ARGUMENT_CONFLICT",
        anchor_entities=["老王", "佩戴者"],
        directional_keywords=["吵架", "争吵", "冲突", "口角", "争执", "吵闹"],
        core_content="佩戴者与老王在饭局发生激烈言语争执与推搡",
        source_ref_id="mic-snippet-108"
    )

    # 模型提取为“吵闹”，方向正确
    extracted = ExtractedFactSubmission(
        fact_id="sub-fact-01",
        dimension_id="dim:social",
        semantic_intent="ARGUMENT_CONFLICT",
        summary_text="佩戴者和老王发生了严重的口角与吵闹",
        recognized_entities=["老王", "佩戴者"],
        source_ref_id="mic-snippet-108"
    )

    aligned, diag = DirectionalSemanticMatcher.is_direction_aligned(gt_fact, extracted)
    assert aligned is True, f"应当判定方向吻合: {diag}"


def test_directional_semantic_matching_divergence():
    """测试方向严重偏离时被正确拦截（如恋爱、庆祝）。"""
    gt_fact = DirectionalSemanticFact(
        fact_id="fact-001",
        dimension_id="dim:social",
        semantic_intent="ARGUMENT_CONFLICT",
        anchor_entities=["老王", "佩戴者"],
        directional_keywords=["吵架", "争吵", "冲突", "口角", "争执", "吵闹"],
        core_content="佩戴者与老王在饭局发生激烈言语争执与推搡",
        source_ref_id="mic-snippet-108"
    )

    # 模型提取成了亲密庆祝，方向相反
    extracted_wrong = ExtractedFactSubmission(
        fact_id="sub-fact-02",
        dimension_id="dim:social",
        semantic_intent="ROMANTIC_CELEBRATION",
        summary_text="佩戴者和老王在饭局欢声笑语相亲相爱",
        recognized_entities=["老王", "佩戴者"],
        source_ref_id="mic-snippet-108"
    )

    aligned, diag = DirectionalSemanticMatcher.is_direction_aligned(gt_fact, extracted_wrong)
    assert aligned is False, f"应当判定方向偏离: {diag}"


def test_self_solving_violation_disqualification():
    """测试自出题自做违规判定（一票否决）。"""
    gt_fact = DirectionalSemanticFact(
        fact_id="fact-001",
        dimension_id="dim:social",
        semantic_intent="ARGUMENT_CONFLICT",
        anchor_entities=["老王"],
        directional_keywords=["吵架"],
        core_content="吵架事实",
        source_ref_id="snippet-1"
    )
    q = CleaningQuestion(
        question_id="Q_agent01_00001",
        generator_agent="agent-01",
        timestamp_utc="2026-09-16T12:00:00Z",
        difficulty=DifficultyLevel.EASY,
        ground_truth_facts=[gt_fact],
        ground_truth_junk_ids=["junk-1", "junk-2"]
    )

    # 违规：agent-01 自己做自己的题目
    submission = CleaningAnswerSubmission(
        question_id="Q_agent01_00001",
        solver_agent="agent-01",
        generator_agent="agent-01",
        extracted_facts=[],
        pruned_junk_ids=["junk-1", "junk-2"]
    )

    report = DirectionalSemanticMatcher.evaluate_submission(q, submission)
    assert report.is_self_solving_violation is True
    assert report.final_score == 0.0
    assert report.verdict == "FAIL"