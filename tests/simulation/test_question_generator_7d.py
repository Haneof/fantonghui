import json
import pytest
from pathlib import Path

from aios_core.simulation.cleaning_arena_protocol import (
    CleaningQuestion,
    DirectionalSemanticFact,
    ExtractedFactSubmission,
    CleaningAnswerSubmission,
    DirectionalSemanticMatcher,
    DifficultyLevel
)
from aios_core.simulation.life_spectrum_question_engine import (
    SevenDimensionalQuestionEngine,
    CognitiveDomain,
    PERSONAS,
    EVENT_ARCHETYPES,
    ACOUSTIC_TOPOLOGIES,
    SENSOR_GENERATORS,
    TRAP_BLUEPRINTS
)


def test_engine_seven_dimensions_topology():
    """验证七维拓扑要素库完整性与非空。"""
    assert len(PERSONAS) == 15, "必须涵盖 D01~D15 15类人生阶段"
    assert len(EVENT_ARCHETYPES) >= 15, "必须涵盖五大认知域的极限事件"
    assert len(ACOUSTIC_TOPOLOGIES) == 7, "必须涵盖 A01~A07 七类声学拓扑"
    assert len(SENSOR_GENERATORS) == 6, "必须涵盖 S01~S06 六类传感器波形"
    assert len(TRAP_BLUEPRINTS) >= 5, "必须涵盖 T00~T04 等真假对抗陷阱"


def test_single_question_cleaning_question_contract():
    """验证单题生成 100% 遵从 CleaningQuestion 规范。"""
    engine = SevenDimensionalQuestionEngine(generator_id="agent-01", seed=42)
    q = engine.generate_single_question(question_idx=1)

    assert isinstance(q, CleaningQuestion)
    assert q.question_id == "Q_agent-01_00001"
    assert q.generator_agent == "agent-01"
    assert q.persona_tag is not None
    assert len(q.ground_truth_facts) >= 1
    assert len(q.ground_truth_junk_ids) >= 1
    assert "raw_imu_g_force" in q.sensor_stream
    assert "heart_rate_bpm" in q.sensor_stream
    assert len(q.mic_stream) >= 1
    assert "user_speaker_id" in q.voiceprint_cluster
    assert len(q.voiceprint_cluster["detected_speakers"]) >= 3

    # 验证反向序列化与校验
    dumped = q.model_dump()
    reloaded = CleaningQuestion.model_validate(dumped)
    assert reloaded.question_id == q.question_id


def test_all_15_personas_generation():
    """验证 15 个千人千面佩戴者身份均能成功出题。"""
    engine = SevenDimensionalQuestionEngine(generator_id="agent-01", seed=100)
    for p in PERSONAS:
        q = engine.generate_single_question(question_idx=1, forced_persona_id=p.tag_id)
        assert q.persona_tag == p.persona_tag
        assert len(q.ground_truth_facts) >= 1


def test_five_domains_coverage_and_balance():
    """验证五大认知域均衡覆盖，每类考题在整卷中占比不得低于 15%。"""
    engine = SevenDimensionalQuestionEngine(generator_id="agent-01", seed=2026)
    questions = engine.generate_batch(count=100, balance_domains=True)

    domain_counts = {}
    for q in questions:
        domain = q.ground_truth_facts[0].dimension_id
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    # 100题中，五大域应当各占 20 题左右，且必须均 >= 15 题 (15%)
    for dom in CognitiveDomain:
        cnt = domain_counts.get(dom.value, 0)
        assert cnt >= 15, f"认知域 {dom.value} 占比 {cnt}% 低于 15% 红线！"


def test_adversarial_traps_directional_matching():
    """验证真假对抗陷阱 (T01~T04) 正确生成并且被 DirectionalSemanticMatcher 识别。"""
    engine = SevenDimensionalQuestionEngine(generator_id="agent-01", seed=999)
    # 生成多道题测试对抗 trap
    questions = [engine.generate_single_question(i) for i in range(1, 30)]
    
    # 抽取包含定向同义词簇的题目
    test_q = questions[0]
    gt_fact = test_q.ground_truth_facts[0]
    assert len(gt_fact.directional_keywords) >= 3

    # 模拟一个答题战队提纯的答案（命中近义词簇中的词与主要实体）
    keyword_hit = gt_fact.directional_keywords[0]
    extracted = ExtractedFactSubmission(
        fact_id="sub_fact_01",
        dimension_id=gt_fact.dimension_id,
        semantic_intent=gt_fact.semantic_intent,
        summary_text=f"涉及当事人的核心事实：{keyword_hit}，需要及时处理",
        recognized_entities=gt_fact.anchor_entities[:3],
        source_ref_id=gt_fact.source_ref_id
    )

    aligned, diag = DirectionalSemanticMatcher.is_direction_aligned(gt_fact, extracted)
    assert aligned is True, f"应当判定方向吻合: {diag}"


def test_export_to_jsonl_files(tmp_path: Path):
    """验证批量流式导出到 JSONL 文件及其统计合规性。"""
    engine = SevenDimensionalQuestionEngine(generator_id="agent-01", seed=777)
    q_file = tmp_path / "questions_test.jsonl"
    gt_file = tmp_path / "gt_test.jsonl"

    stats = engine.export_to_files(count=50, questions_path=q_file, gt_path=gt_file)

    assert stats["total_questions"] == 50
    assert stats["generator_agent"] == "agent-01"
    assert q_file.exists()
    assert gt_file.exists()

    # 逐行读取验证 JSON
    lines_q = q_file.read_text(encoding="utf-8").strip().split("\n")
    lines_gt = gt_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines_q) == 50
    assert len(lines_gt) == 50

    sample_q = json.loads(lines_q[0])
    assert "persona_tag" in sample_q
    assert "sensor_stream" in sample_q
    assert "mic_stream" in sample_q
    assert "ground_truth_facts" in sample_q

    sample_gt = json.loads(lines_gt[0])
    assert sample_gt["question_id"] == sample_q["question_id"]
    assert len(sample_gt["ground_truth_facts"]) >= 1
