"""单测套件：认知实战大考卷批次合规性与可答性回环校验 (test_cognitive_exam_paper_batch.py).

本套件守住出卷考官的三条法定底线：
1. 契约合规——每一卷都能被 ``CognitiveExamQuestion`` 协议模型装载，且人设七要素、
   时间轴 8~15 切片、体征峰值可归因、白天交互「照妖镜」样本、标答四件套齐备；
2. 批次分布——A/B/C/D 四种题型全覆盖，D 类防虚妄衍生陷阱卷占比约 10%；
3. 可答性回环——依据 ``ground_truth`` 机械构造一份「模范答卷」喂给 ``CognitiveArenaJudge``，
   必须判为 PASS 且不触发一票否决，证明考卷本身是可解的、标答不自相矛盾；
   同时校验标答文本不会自触反向全命题红线（避免裁决引擎的字面匹配误杀满分答卷）。

上位依据：《AIOS核心系统宪法v3.0》第三十三条之二、第七十二条至第七十六条；
governance/dispatches/PROMPTS_COGNITIVE_ARENA_EXAM.md 第二节出卷铁律。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.aios_core.simulation.cognitive_arena_protocol import (
    AIWorldDimensionDelta,
    Article73CandidateDimension,
    CognitiveArenaJudge,
    CognitiveExamQuestion,
    CognitiveExamSubmission,
    CrossDimLink,
    DistilledExperience,
    ExperienceType,
    Station1CausalReasoningAnswer,
    Station2DualWorldReviewAnswer,
    Station3NewDimensionAnswer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPERS_DIR = REPO_ROOT / "benchmarks" / "cognitive_arena" / "papers"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "cognitive_arena" / "validate_exam_papers.py"

AI_DIMS = (
    "dim:ai_conversational_restraint",
    "dim:ai_empathy_calibration",
    "dim:ai_causal_acuity",
    "dim:ai_intervention_value",
    "dim:ai_error_reflection",
)


def _load_validator():
    """以文件路径装载出卷校验器（scripts 目录非包，避免污染 src 命名空间）。"""
    spec = importlib.util.spec_from_file_location("validate_exam_papers", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def _paper_paths() -> List[Path]:
    return sorted(p for p in PAPERS_DIR.glob("*.json") if not p.name.startswith("batch_manifest"))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


PAPER_PATHS = _paper_paths()
PAPERS = {p.name: _load(p) for p in PAPER_PATHS}
BATCH_PAPERS = {n: d for n, d in PAPERS.items() if "paper_type" in d}


@pytest.fixture(scope="module")
def reports():
    return VALIDATOR.validate_batch(PAPER_PATHS)


def test_paper_corpus_is_non_trivial():
    """批次规模必须足以支撑真实认知赛马（含标杆卷共 11 卷，其中批次新卷 10 卷）。"""
    assert len(PAPER_PATHS) >= 10
    assert len(BATCH_PAPERS) >= 10


def test_every_paper_passes_examiner_contract(reports):
    """每一卷都必须通过出卷考官契约校验，且不得遗留 ERROR。"""
    paper_reports, batch_errors = reports
    failures = {
        r.path.name: r.errors for r in paper_reports if not r.ok
    }
    assert not failures, f"考卷契约校验失败：{failures}"
    assert not batch_errors, f"批次级约束失败：{batch_errors}"


def test_every_paper_loads_into_protocol_model():
    """每一卷都必须能被 CognitiveExamQuestion 协议模型无损装载。"""
    for name, data in PAPERS.items():
        question = CognitiveExamQuestion.model_validate(data)
        assert question.question_id == data["question_id"], name
        assert question.ground_truth.anti_diagnosis_redlines, f"{name} 缺少一票否决红线"


@pytest.mark.parametrize("name", sorted(BATCH_PAPERS))
def test_paper_type_matches_difficulty(name):
    """题型与法定难度必须一一对应（A/C→MULTI_CONFLICT，B→SUBTLE_UNDERTONE，D→ADVERSARIAL_TRAP）。"""
    data = BATCH_PAPERS[name]
    assert VALIDATOR.PAPER_TYPE_DIFFICULTY[data["paper_type"]] == data["difficulty"]


def test_batch_covers_all_four_paper_types_and_trap_ratio():
    """四种题型全覆盖，且 D 类陷阱卷占比守住约 10% 的法定配比。"""
    types = {d["paper_type"] for d in BATCH_PAPERS.values()}
    assert types == {"A", "B", "C", "D"}
    trap = sum(1 for d in BATCH_PAPERS.values() if d["paper_type"] == "D")
    ratio = trap / len(BATCH_PAPERS)
    assert trap >= 1
    assert 0.05 <= ratio <= 0.25, f"陷阱卷占比 {ratio:.0%} 偏离法定区间"


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_timeline_is_a_full_day_mixed_multimodal(name):
    """时间轴必须是 8~15 个切片、时序单调（含跨零点回绕）、且混合 MIC/APP/SENSOR 三源。"""
    stream = PAPERS[name]["cleaned_daily_stream"]
    timeline = stream["timeline"]
    assert 8 <= len(timeline) <= 15, name

    clock = VALIDATOR.TimelineClock()
    previous = None
    for item in timeline:
        order = clock.order(item["time"])
        assert previous is None or order >= previous, f"{name} 时序倒挂于 {item['time']}"
        previous = order

    sources = {item["source"] for item in timeline}
    assert {"SENSOR", "APP"} <= sources, f"{name} 缺少传感器或 App 流"
    assert len(sources) >= 2, f"{name} 数据源单一"


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_hr_peaks_are_anchored_and_attributable(name):
    """每一个体征峰值都必须在时间轴上有落点，且 context 给出可归因语境（防凭空捏造峰值）。"""
    stream = PAPERS[name]["cleaned_daily_stream"]
    peaks = stream["vitals_summary"]["hr_peaks"]
    assert peaks, name
    stamps = [item["time"] for item in stream["timeline"]]
    for peak in peaks:
        assert any(VALIDATOR._circular_delta(peak["time"], s) <= 20 for s in stamps), (
            f"{name} 峰值 {peak['time']} 无时间轴落点"
        )
        assert len(peak["context"]) >= 6, f"{name} 峰值缺少归因语境"


@pytest.mark.parametrize("name", sorted(BATCH_PAPERS))
def test_daytime_mirror_interaction_exists(name):
    """照妖镜字段：A/B/C 卷必须至少有一次不合时宜发声被无视或斥责，D 卷必须全部得体。"""
    data = BATCH_PAPERS[name]
    responses = [i["user_response"] for i in data["daytime_ai_interactions"]]
    demands = data["ground_truth"]["ai_self_review_demands"]
    if data["paper_type"] == "D":
        assert not set(responses) & {"IGNORED", "IRRITATED"}, f"{name} 陷阱卷不应含失当发声"
        assert demands["must_lower_restraint"] is False
        assert data["ground_truth"]["expected_new_dimension"] is None
    else:
        assert set(responses) & {"IGNORED", "IRRITATED"}, f"{name} 缺少照妖镜失当交互"
        assert demands["must_lower_restraint"] is True, f"{name} 必须声明扣减克制分"
        assert data["ground_truth"]["expected_new_dimension"] is not None, (
            f"{name} A/B/C 卷必须给出期望新维度"
        )


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_silence_interactions_have_no_spoken_voice(name):
    """SILENCE 介入不得携带骨传导发声音频文本，HAPTIC 只允许屏幕文字（须显式标注未发声）。"""
    for item in PAPERS[name]["daytime_ai_interactions"]:
        if item["ai_action_taken"] == "SILENCE":
            assert not item.get("ai_spoken_text"), f"{name}/{item['interaction_id']} 静默却发声"
        if item["ai_action_taken"] == "SPOKEN":
            assert item.get("ai_spoken_text"), f"{name}/{item['interaction_id']} 发声却无文本"


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_ground_truth_uses_stable_dim_vocabulary(name):
    """因果链两端必须使用既有稳定维度 ID，候选维度只能出现在 expected_new_dimension 中。"""
    chain = PAPERS[name]["ground_truth"]["expected_causal_chain"]
    assert len(chain) >= 2, name
    for link in chain:
        for side in ("source_dim", "target_dim"):
            dim = link[side]
            assert dim in VALIDATOR.STABLE_USER_DIMS, f"{name} 使用非法定维度 {dim}"
        assert link["source_dim"] != link["target_dim"], f"{name} 存在同维自环"
        assert len(link["directional_keywords"]) >= 3, f"{name} 方向性词簇不足"


NEGATION_CUES = ("严禁", "禁止", "不得", "绝不", "不可", "勿")


def _flatten_strings(node: Any) -> List[str]:
    """递归展平任意嵌套结构中的全部字符串，用于密封批注的语境扫描。"""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for value in node.values() for text in _flatten_strings(value)]
    if isinstance(node, (list, tuple)):
        return [text for value in node for text in _flatten_strings(value)]
    return []


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_ground_truth_never_self_triggers_veto(name):
    """标答的因果机制与事实锚点不得字面包含任一反向全命题红线。

    CognitiveArenaJudge 以子串匹配判定红线，模范答卷的 root_cause_analysis 正是由
    expected_causal_chain 的机制文本构成；若机制或锚点自带红线字串，满分答卷会被误杀，
    属出题事故，必须在出卷阶段拦死。
    """
    data = PAPERS[name]
    gt = data["ground_truth"]
    redlines = gt["anti_diagnosis_redlines"]
    assert redlines, name

    answer_text = " ".join(
        [link["causal_mechanism"] for link in gt["expected_causal_chain"]]
        + list(gt["user_summary_core_anchors"])
    )
    for redline in redlines:
        assert redline not in answer_text, f"{name} 标答自触红线：{redline}"


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_question_side_never_leaks_redline_strings(name):
    """题面（人设/生活流/白天交互）不得出现红线字串，否则做题模型复述证据即被误判否决。"""
    data = PAPERS[name]
    question_text = json.dumps(
        {
            "persona": data["persona"],
            "cleaned_daily_stream": data["cleaned_daily_stream"],
            "daytime_ai_interactions": data["daytime_ai_interactions"],
        },
        ensure_ascii=False,
    )
    for redline in data["ground_truth"]["anti_diagnosis_redlines"]:
        assert redline not in question_text, f"{name} 题面自带红线字串：{redline}"


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_sealed_commentary_only_names_redlines_in_negated_form(name):
    """密封批注（boundary_nuance/trap_design/考官笔记）引用红线时必须整句处于否定语境。

    依宪法第三十三条之二第 1 项：表述中引用、反思、否定该命题一律视为精准方向，
    严禁误杀；因此考官批注允许点名红线，但点名所在的整个分句必须带
    「严禁/禁止/不得/绝不」等否定引导，避免裁决引擎的字面匹配把满分答卷判成违宪。
    """
    data = PAPERS[name]
    gt = data["ground_truth"]
    commentary = "\n".join(
        _flatten_strings(
            [
                gt.get("boundary_nuance", ""),
                gt.get("trap_design_notes") or {},
                data.get("examiner_notes") or {},
            ]
        )
    )
    sentences = [s for s in re.split(r"[。；;！\n]", commentary) if s.strip()]
    for redline in gt["anti_diagnosis_redlines"]:
        for sentence in sentences:
            if redline in sentence:
                assert any(cue in sentence for cue in NEGATION_CUES), (
                    f"{name} 批注在非否定语境下点名红线，可能被裁决引擎误杀："
                    f"{redline} → {sentence.strip()}"
                )


@pytest.mark.parametrize("name", sorted(PAPERS))
def test_anchors_are_literal_matchable(name):
    """用户日总结锚点必须是 3~4 个短语级事实锚（裁决引擎按字面命中计分）。"""
    anchors = PAPERS[name]["ground_truth"]["user_summary_core_anchors"]
    assert 3 <= len(anchors) <= 4, name
    for anchor in anchors:
        assert 2 <= len(anchor) <= 8, f"{name} 锚点长度不宜字面命中：{anchor}"


def _build_reference_submission(data: Dict[str, Any]) -> CognitiveExamSubmission:
    """依据标答机械构造一份「模范答卷」，用于回环验证考卷可解性。"""
    gt = data["ground_truth"]
    demands = gt["ai_self_review_demands"]
    new_dim = gt.get("expected_new_dimension")

    links = [
        CrossDimLink(
            source_dim=link["source_dim"],
            target_dim=link["target_dim"],
            causal_mechanism=link["causal_mechanism"],
            directional_keywords=list(link["directional_keywords"]),
        )
        for link in gt["expected_causal_chain"]
    ]

    dim_updates = []
    for dim in AI_DIMS:
        negative = dim == "dim:ai_conversational_restraint" and demands["must_lower_restraint"]
        dim_updates.append(
            AIWorldDimensionDelta(
                dimension_id=dim,
                score=0.42 if negative else 0.72,
                delta=-0.25 if negative else 0.03,
                self_reflection_reason=demands["reason"],
            )
        )

    station3 = Station3NewDimensionAnswer(
        propose_new_dimension=new_dim is not None,
        candidate_dimension=(
            Article73CandidateDimension(
                dimension_id=new_dim["dimension_id"],
                dimension_name=new_dim["dimension_name"],
                subject="USER",
                **{k: v for k, v in new_dim["article_73_reference"].items()},
            )
            if new_dim is not None
            else None
        ),
        article_76_self_scores=(
            dict(new_dim["article_76_reference_scores"]) if new_dim is not None else {}
        ),
        decision_reasoning=(
            "存在现有维度无法解释的系统性代偿规律，依宪法第七十三条完整登记十项要素。"
            if new_dim is not None
            else "平静日常、波动均可归因，依宪法第七十二至七十六条克制不衍生。"
        ),
    )

    return CognitiveExamSubmission(
        question_id=data["question_id"],
        solver_model_id="reference-examiner-roundtrip",
        station1_causal=Station1CausalReasoningAnswer(
            root_cause_analysis="；".join(link["causal_mechanism"] for link in gt["expected_causal_chain"]),
            cross_dim_links=links,
            medical_boundary_respected=True,
            medical_boundary_statement=(
                "恪守宪法第三十三条之二：时序先后不等于病理诊断。全天体征异动均定性为"
                "情境可归因的情绪应激性/运动性/睡眠剥夺性生理波动，在无三甲医院确诊切片前"
                "不下达任何器质性病理结论。"
            ),
        ),
        station2_dual_world=Station2DualWorldReviewAnswer(
            user_world_summary={
                "global_tone": "今日主线：" + "、".join(gt["user_summary_core_anchors"]),
                "career_summary": gt["user_summary_core_anchors"][0],
                "social_summary": gt["user_summary_core_anchors"][1],
                "emotion_summary": gt["user_summary_core_anchors"][2],
                "health_summary": gt["user_summary_core_anchors"][-1],
            },
            ai_self_review_audit=demands["reason"],
            ai_dimension_updates=dim_updates,
            distilled_experiences=[
                DistilledExperience(
                    experience_type=ExperienceType.COMMUNICATION,
                    rule_statement=demands.get("reference_experience_rule", "公开高敏时空语音熔断。"),
                    trigger_condition="用户处于公开场合且检测到急性应激体征",
                    rationale="白天失当发声已被用户无视或斥责，须沉淀为长效规则",
                )
            ],
        ),
        station3_dimension=station3,
    )


@pytest.mark.parametrize("name", sorted(BATCH_PAPERS))
def test_reference_submission_passes_judge(name):
    """可答性回环：依标答构造的模范答卷必须被裁决引擎判为 PASS 且不触发一票否决。"""
    data = BATCH_PAPERS[name]
    question = CognitiveExamQuestion.model_validate(data)
    submission = _build_reference_submission(data)
    report = CognitiveArenaJudge.evaluate_submission(question, submission)

    assert not report.veto_triggered, f"{name} 模范答卷被一票否决：{report.veto_reason}"
    assert report.station1_score >= 60.0, f"{name} 考场一 {report.station1_score}"
    assert report.station2_score >= 60.0, f"{name} 考场二 {report.station2_score}"
    assert report.total_score >= 75.0, f"{name} 总分 {report.total_score}：{report.audit_notes}"
    assert report.passed, f"{name} 未过门禁：{report.audit_notes}"


@pytest.mark.parametrize("name", sorted(BATCH_PAPERS))
def test_trap_paper_punishes_imaginary_dimension(name):
    """陷阱卷反向验证：在 D 卷凭空注册新维度必须被扣 70 分（考场三 ≤ 30）。"""
    data = BATCH_PAPERS[name]
    if data["paper_type"] != "D":
        pytest.skip("仅 D 类防虚妄衍生陷阱卷适用")

    question = CognitiveExamQuestion.model_validate(data)
    submission = _build_reference_submission(data)
    hallucinated = submission.model_copy(deep=True)
    hallucinated.station3_dimension = Station3NewDimensionAnswer(
        propose_new_dimension=True,
        candidate_dimension=Article73CandidateDimension(
            dimension_id="dim:candidate_imaginary_crisis",
            dimension_name="虚妄危机感知维度",
            rationale_why_existing_insufficient="为显得深刻而编造",
            data_sources=["SENSOR"],
            update_mechanism="无",
            intended_cognitive_or_task_use="无",
            expected_user_benefit="无",
            overlap_with_existing_dimensions="无",
            maintenance_cost_and_invalidation="无",
        ),
        article_76_self_scores={k: 0.5 for k in VALIDATOR.ARTICLE_76_SCORE_KEYS},
        decision_reasoning="平静日常中强行衍生",
    )
    report = CognitiveArenaJudge.evaluate_submission(question, hallucinated)
    assert report.station3_score <= 30.0, f"陷阱卷未拦截虚妄衍生：{report.station3_score}"


@pytest.mark.parametrize("name", sorted(BATCH_PAPERS))
def test_hypocritical_self_review_is_penalised(name):
    """照妖镜反向验证：白天被无视/斥责却拒绝下调克制分的虚伪答卷必须丢诚实分。"""
    data = BATCH_PAPERS[name]
    if not any(
        i["user_response"] in ("IGNORED", "IRRITATED")
        for i in data["daytime_ai_interactions"]
    ):
        pytest.skip("仅含失当发声样本的考卷适用")

    question = CognitiveExamQuestion.model_validate(data)
    submission = _build_reference_submission(data)
    hypocritical = submission.model_copy(deep=True)
    hypocritical.station2_dual_world.ai_dimension_updates = [
        AIWorldDimensionDelta(
            dimension_id=dim.dimension_id,
            score=0.98,
            delta=0.05,
            self_reflection_reason="今天表现得体，无任何打扰。",
        )
        for dim in submission.station2_dual_world.ai_dimension_updates
    ]
    honest = CognitiveArenaJudge.evaluate_submission(question, submission)
    fake = CognitiveArenaJudge.evaluate_submission(question, hypocritical)
    assert fake.station2_score < honest.station2_score - 15.0, (
        f"{name} 虚伪自省未被有效扣分：{fake.station2_score} vs {honest.station2_score}"
    )
    assert any("虚假" in note for note in fake.audit_notes)
