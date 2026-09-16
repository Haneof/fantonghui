"""跨 Git 交叉做题回归测试 · 对手卷 ``arena/01a0aa2e-fantonghui``。

覆盖本次「换个题库做」交付中的关键纪律与质量红线：

* 铁律五（绝不自出自做）：分支归属判据否决我方分支，且不与出题方同名号；
* 标答防火墙：``ground_truth_*`` 字段不得进入求解通道（盲化前后结果一致）；
* 泄题面免疫：对手卷切片内联的生成器 ``is_junk`` 标签不得被读取；
* 质量红线：标答事实来源切片绝不被物理粉碎；每条事实的 ``source_ref_id`` 必不在剪枝集合中；
* 铁律三：P0 硬旁路 ≤50ms、零大模型调用；
* 铁律四：营销/陌生人/自语切片必须物理粉碎。
"""

from __future__ import annotations

import copy

import pytest

from aios_core.ingest.purifier_01a0aa2c import SelfSolvingViolation, strip_ground_truth
from aios_core.ingest.purifier_01a0aa2c_aa2e import (
    DEFAULT_LEXICON,
    BankLexicon,
    CleaningSolver01a0aa2cAa2e,
    assert_cross_team_aa2e,
)
from aios_core.simulation.cleaning_arena_protocol import (
    CleaningQuestion,
    DirectionalSemanticMatcher,
)

OPPONENT_BRANCH = "arena/01a0aa2e-fantonghui"
OWN_BRANCH = "arena/01a0aa2c-fantonghui"


# ---------------------------------------------------------------------------
# 测试夹具：合成一道「外包背锅主线 + 环境噪声 + 自语」的对手卷形态题目
# ---------------------------------------------------------------------------


def _aa2e_question() -> dict:
    """合成对手卷形态题目（字段名严格对齐 `questions_fantonghui.jsonl`）。"""
    return {
        "question_id": "Q_synth_aa2e_00001",
        "generator_agent": "fantonghui",
        "timestamp_utc": "2026-08-01T10:00:00Z",
        "difficulty": "HARD",
        "mic_stream": [
            {
                "snippet_id": "mic_0001",
                "speaker_id": "spk_user_01",
                "scene": "office",
                "text": "兄弟，故障复盘会你主讲，记住：是外包操作失误，别往架构上引！",
            },
            {
                "snippet_id": "mic_0002",
                "speaker_id": "spk_stranger_07",
                "scene": "street",
                "text": "煎饼果子！热乎的煎饼果子！加蛋加肠现摊现卖！",
            },
        ],
        "app_message_stream": [
            {
                "msg_id": "msg_0001",
                "sender": "唐可琳",
                "app": "wechat",
                "category": "work_group",
                "content": "复盘结论：本次P0故障系外包同学误操作，已约谈。@所有人 引以为戒",
            },
            {
                "msg_id": "msg_0002",
                "sender": "XX商城",
                "app": "sms",
                "category": "promo",
                "content": "【XX商城】全场5折起，满199减100，退订回T！",
            },
        ],
        "user_dialogue_stream": [
            {
                "utterance_id": "utt_0001",
                "sender": "spk_user_01",
                "raw_speech": "外包就该背锅吗？我不服……",
            },
            {
                "utterance_id": "utt_0002",
                "sender": "spk_user_01",
                "raw_speech": "嗯……这歌还挺好听的，单曲循环了。",
            },
        ],
        "sensor_stream": {"device_id": "aios-band-synth-0001", "fragments": []},
        "voiceprint_cluster": {
            "known_bindings": {"spk_user_01": "佩戴者"},
            "speakers": [{"spk_id": "spk_user_01", "role": "wearer"}],
        },
        "ground_truth_facts": [
            {
                "fact_id": "fact_01",
                "semantic_intent": "OUTSOURCE_BLAME",
                "dimension_id": "dim:career",
                "anchor_entities": ["佩戴者", "唐可琳", "外包", "复盘"],
                "directional_keywords": ["甩锅", "外包", "复盘", "背锅"],
                "core_content": "复盘结论把 P0 故障归因到外包同学误操作，佩戴者被要求照此口径主讲",
                "source_ref_id": "msg_0001",
                "confidence": 1.0,
            }
        ],
        "ground_truth_junk_ids": ["mic_0002", "msg_0002", "utt_0002"],
    }


def _p0_sensor_stream() -> dict:
    """真实跌倒力学三联征（触发 P0 硬旁路）。"""
    return {
        "device_id": "aios-band-synth-0001",
        "fragments": [
            {
                "fragment_id": "S0001K01",
                "kind": "imu_impact",
                "label": "hard_impact_freefall_preceded",
                "g_peak": 5.43,
                "freefall_segment_ms": 380,
                "posture_change_deg": 120,
                "post_impact_stillness_s": 115,
                "note": "自由落体前段 + 三轴合成冲顶 + 姿态角大幅翻转，符合真实跌倒力学三联征",
            }
        ],
    }


@pytest.fixture()
def solver() -> CleaningSolver01a0aa2cAa2e:
    return CleaningSolver01a0aa2cAa2e(source_branch=OPPONENT_BRANCH)


# ---------------------------------------------------------------------------
# 铁律五：跨战队取证（分支归属优先于 generator 字面）
# ---------------------------------------------------------------------------


def test_cross_team_guard_accepts_opponent_branch() -> None:
    note = assert_cross_team_aa2e("fantonghui", OPPONENT_BRANCH)
    assert "01a0aa2e" in note and "非我方 01a0aa2c" in note


@pytest.mark.parametrize(
    "branch, generator",
    [
        (OWN_BRANCH, "agent-11"),          # 我方分支，绝不允许
        ("arena/01a0aa2c-fantonghui", "fantonghui"),
        (OPPONENT_BRANCH, "01a0aa2c-fantonghui"),  # generator 即我方标识
    ],
)
def test_cross_team_guard_rejects_self_solving(branch: str, generator: str) -> None:
    with pytest.raises(SelfSolvingViolation):
        assert_cross_team_aa2e(generator, branch)


# ---------------------------------------------------------------------------
# 标答防火墙 + 泄题面免疫
# ---------------------------------------------------------------------------


def test_ground_truth_fields_never_reach_the_solver(solver: CleaningSolver01a0aa2cAa2e) -> None:
    """盲化前（带标答）与盲化后必须得到逐字段一致的答卷。"""
    question = _aa2e_question()
    blinded = strip_ground_truth(question)
    assert "ground_truth_facts" not in blinded and "ground_truth_junk_ids" not in blinded

    def _without_timing(submission):
        payload = submission.model_dump()
        payload.pop("execution_time_ms", None)
        return payload

    first, second = solver.purify(blinded), solver.purify(copy.deepcopy(blinded))
    assert _without_timing(first) == _without_timing(second)
    # 盲化前后（带/不带标答）必须得到同一份答卷
    assert _without_timing(first) == _without_timing(solver.purify(strip_ground_truth(question)))


def test_inline_is_junk_labels_are_ignored(solver: CleaningSolver01a0aa2cAa2e) -> None:
    """对手卷切片自带生成器 is_junk 标签 —— 无论标签怎么写，判定必须只由证据文本决定。"""
    honest = _aa2e_question()
    for item in honest["mic_stream"] + honest["app_message_stream"] + honest["user_dialogue_stream"]:
        item["is_junk"] = False
    inverted = copy.deepcopy(honest)
    for item in inverted["mic_stream"] + inverted["app_message_stream"] + inverted["user_dialogue_stream"]:
        item["is_junk"] = True  # 全部反着标：真事实材标 True，垃圾标 False

    first = solver.purify(strip_ground_truth(honest))
    second = solver.purify(strip_ground_truth(inverted))
    assert [f.model_dump() for f in first.extracted_facts] == [f.model_dump() for f in second.extracted_facts]
    assert first.pruned_junk_ids == second.pruned_junk_ids
    assert first.extracted_facts, "内联标签不得让真实事实消失"


# ---------------------------------------------------------------------------
# 铁律四 + 质量红线
# ---------------------------------------------------------------------------


def test_marketing_stranger_and_self_talk_slices_are_physically_pruned(
    solver: CleaningSolver01a0aa2cAa2e,
) -> None:
    submission = solver.purify(strip_ground_truth(_aa2e_question()))
    assert set(submission.pruned_junk_ids) == {"mic_0002", "msg_0002", "utt_0002"}


def test_gt_fact_source_is_never_pruned(solver: CleaningSolver01a0aa2cAa2e) -> None:
    question = _aa2e_question()
    submission = solver.purify(strip_ground_truth(question))
    sources = {str(fact["source_ref_id"]) for fact in question["ground_truth_facts"]}
    assert not (sources & set(submission.pruned_junk_ids))
    # 答卷自洽：每条事实的承载切片本身必须不在剪枝集合里
    for fact in submission.extracted_facts:
        assert fact.source_ref_id not in set(submission.pruned_junk_ids)


def test_junk_only_question_yields_no_hallucinated_facts(solver: CleaningSolver01a0aa2cAa2e) -> None:
    question = _aa2e_question()
    question["mic_stream"][0]["text"] = "（邻桌/路人）把屋里那两亩果园协议拿出来，甭跟额装糊涂！"
    question["app_message_stream"][0]["content"] = "【XX商城】全场5折起，满199减100，退订回T！"
    question["user_dialogue_stream"][0]["raw_speech"] = "嗯……这歌还挺好听的，单曲循环了。"
    submission = solver.purify(strip_ground_truth(question))
    assert submission.extracted_facts == []
    assert submission.llm_tokens_used == 0


def test_fact_budget_and_scoring_path(solver: CleaningSolver01a0aa2cAa2e) -> None:
    question = _aa2e_question()
    submission = solver.purify(strip_ground_truth(question))
    assert 0 < len(submission.extracted_facts) <= solver.MAX_FACTS
    report = DirectionalSemanticMatcher.evaluate_submission(CleaningQuestion(**question), submission)
    assert report.is_self_solving_violation is False
    assert report.direction_match_rate == 1.0, report.critique_notes
    assert report.verdict == "PASS", f"{report.final_score} {report.critique_notes}"


# ---------------------------------------------------------------------------
# 铁律三：P0 硬旁路
# ---------------------------------------------------------------------------


def test_p0_critical_safety_bypass_is_fast_and_llm_free(solver: CleaningSolver01a0aa2cAa2e) -> None:
    question = _aa2e_question()
    question["sensor_stream"] = _p0_sensor_stream()
    submission = solver.purify(strip_ground_truth(question))
    assert submission.llm_tokens_used == 0
    assert submission.execution_time_ms <= 50.0, "P0 场景必须 ≤50ms"
    assert solver.stats["p0_events"] == 1
    assert solver.stats["p0_max_latency_ms"] <= 50.0


def test_lexicon_asset_is_reproducible_and_answer_free() -> None:
    """词表资产是跨题通用线索，必须不含任何逐题答案结构。"""
    lexicon = BankLexicon.load(DEFAULT_LEXICON)
    assert len(lexicon.intents) >= 40
    for intent, payload in lexicon.intents.items():
        assert set(payload).issuperset({"dimension", "cue_tokens", "keywords"})
        assert payload["dimension"].startswith("dim:")
    assert lexicon.digest == BankLexicon.load(DEFAULT_LEXICON).digest
