"""全天生活流出卷器 —— 出卷方自检测试。

覆盖：协议判卷（方向/红线/一票否决）、生成器自洽、题库审计器。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from aios_core.simulation.daily_life_exam_generator import (
    DECOYS_MASK_NEGATIVE,
    DECOYS_MASK_POSITIVE,
    DailyLifeExamGenerator,
    main,
)
from aios_core.simulation.daily_life_exam_pools import (
    CAREER_ARCS,
    DATING,
    EMOTION_PROFILES,
    FINANCE_ARCS,
    HEALTH_ARCS,
    SOCIAL_ARCS,
)
from aios_core.simulation.daily_life_exam_protocol import (
    DIMENSION_ORDER,
    DifficultyLevel,
    Dimension,
    Modality,
    grade_daily_submission,
    judge_direction,
)
from aios_core.simulation.daily_life_exam_validator import (
    validate_bank,
    validate_question,
)

GEN = DailyLifeExamGenerator("test-agent", seed=42)
SAMPLE = [GEN.build_question(i) for i in range(1, 121)]


# ---------------------------------------------------------------- 协议：方向判定


def test_synonym_counts_as_correct():
    """老大铁律：答"感情破裂"与标准答案"情侣争吵分手"同向，判对。"""
    v = judge_direction("两人感情破裂，晚上正式分开了", ["分手", "感情破裂", "决裂"], ["甜蜜互动"])
    assert v["verdict"] == "DIRECTION_ALIGNED"
    assert v["passed"] is True
    assert "感情破裂" in v["hit_direction"]


def test_red_line_is_one_vote_veto():
    """答"打情骂俏"属绝对偏离，一票否决。"""
    v = judge_direction("两人打情骂俏，很甜蜜", ["分手", "感情破裂"], ["打情骂俏", "甜蜜互动"])
    assert v["verdict"] == "RED_LINE_VIOLATION"
    assert v["passed"] is False
    assert "打情骂俏" in v["hit_red_line"]


def test_red_line_cannot_be_redeemed_by_also_hitting_synonym():
    """踩红线后即便同时蒙对同义词，也不得翻案 —— 红线优先。"""
    v = judge_direction("他们打情骂俏之后分手了", ["分手"], ["打情骂俏"])
    assert v["verdict"] == "RED_LINE_VIOLATION"
    assert v["passed"] is False


def test_missing_direction_is_missed_not_violation():
    v = judge_direction("今天天气不错", ["分手", "感情破裂"], ["甜蜜互动"])
    assert v["verdict"] == "DIRECTION_MISSED"
    assert v["passed"] is False


def test_red_line_zeroes_whole_score():
    """任一维踩红线 -> 总分归零，不论其余维度多准。"""
    q = SAMPLE[0]
    gt = q["directional_ground_truth"]
    good = {d: gt[d]["acceptable_directions"][0] for d in DIMENSION_ORDER}
    clean = grade_daily_submission(q, good)
    assert clean["final_score"] > 0

    poisoned = dict(good)
    poisoned[Dimension.SOCIAL] = gt[Dimension.SOCIAL]["red_line_deviations"][0]
    out = grade_daily_submission(q, poisoned)
    assert out["final_score"] == 0
    assert out["red_line_violation"] is True
    assert out["verdict"] == "FAIL"


def test_grade_accepts_wrapped_answers_payload():
    q = SAMPLE[1]
    gt = q["directional_ground_truth"]
    flat = {d: gt[d]["acceptable_directions"][0] for d in DIMENSION_ORDER}
    assert grade_daily_submission(q, flat) == grade_daily_submission(q, {"answers": flat})


# ---------------------------------------------------------------- 生成器


def test_deterministic_for_same_seed():
    a = DailyLifeExamGenerator("x", seed=7).build_question(3)
    b = DailyLifeExamGenerator("x", seed=7).build_question(3)
    assert a == b


def test_different_seed_changes_paper():
    a = DailyLifeExamGenerator("x", seed=7).build_question(3)
    b = DailyLifeExamGenerator("x", seed=8).build_question(3)
    assert a != b


def test_required_top_level_keys():
    """老大指定的标准 JSON 字段必须齐备。"""
    for q in SAMPLE:
        for k in ("question_id", "persona", "cleaned_daily_stream", "directional_ground_truth"):
            assert k in q


def test_all_six_dimensions_present_with_full_fields():
    for q in SAMPLE:
        gt = q["directional_ground_truth"]
        assert set(gt) == set(DIMENSION_ORDER)
        for dim in DIMENSION_ORDER:
            assert gt[dim]["core_content"]
            assert gt[dim]["acceptable_directions"]
            assert gt[dim]["red_line_deviations"]


def test_directions_never_collide_with_red_lines():
    """标答不得自相矛盾：同义词池与红线池必须不相交。"""
    for q in SAMPLE:
        for dim, g in q["directional_ground_truth"].items():
            assert not (set(g["acceptable_directions"]) & set(g["red_line_deviations"]))


def test_stream_is_chronological_and_within_day_window():
    for q in SAMPLE:
        mins = []
        for s in q["cleaned_daily_stream"]:
            h, m = s["timestamp"].split(":")
            mins.append(int(h) * 60 + int(m))
        assert mins == sorted(mins)
        assert mins[0] >= 7 * 60
        assert mins[-1] <= 23 * 60 + 30


def test_stream_mixes_all_three_modalities():
    """MIC 对话 + APP 通知 + 传感器体征，三者缺一不可。"""
    for q in SAMPLE:
        mods = {s["modality"] for s in q["cleaned_daily_stream"]}
        assert mods == {Modality.MIC, Modality.APP, Modality.SENSOR}


def test_stream_mixes_key_events_with_bulk_trivia():
    """关键大事 + 海量琐碎日常，必须共存且琐事占多数。"""
    for q in SAMPLE:
        stream = q["cleaned_daily_stream"]
        key = [s for s in stream if s["is_key_event"]]
        triv = [s for s in stream if not s["is_key_event"]]
        assert key, "缺少关键大事"
        assert len(triv) > len(key), "琐碎日常必须构成主体噪声"


def test_no_verbatim_duplicate_slices_within_a_day():
    for q in SAMPLE:
        contents = [s["content"] for s in q["cleaned_daily_stream"]]
        assert len(contents) == len(set(contents))


def test_emotional_shock_always_triggers_physiological_response():
    """跨维度编织铁律：晚间情感重创必须在体征上留下痕迹。"""
    shock = {"BREAKUP", "PARENT_ILLNESS", "PET_LOSS"}
    seen = 0
    for q in SAMPLE:
        sig = q["arc_signature"]
        if sig["social"] in shock:
            seen += 1
            assert sig["health"] in {"EMOTIONAL_TACHYCARDIA", "PANIC_EPISODE"}
            hc = q["directional_ground_truth"][Dimension.HEALTH]["core_content"]
            assert "心率" in hc
    assert seen > 0, "样本中应当出现情感重创剧情"


def test_breakup_only_for_unmarried_personas():
    """人设自洽：已婚人设不会收到"我们分手吧"。"""
    for q in SAMPLE:
        if q["arc_signature"]["social"] in {"BREAKUP", "PROPOSAL_ACCEPTED"}:
            assert q["persona"]["marital_status"] in DATING


def test_adversarial_decoys_contradict_the_truth():
    """对抗题的误导切片必须与真相**反向**，绝不顺向剧透。

    坏日子只允许出现"粉饰太平"式说辞，绝不能出现"唱衰"式说辞（那等于泄题）；
    好日子反之。并且整体样本中确实出现过掩饰性说辞。
    """
    mask_neg = {t for _, _, t in DECOYS_MASK_NEGATIVE}
    mask_pos = {t for _, _, t in DECOYS_MASK_POSITIVE}
    seen_masking = 0

    for q in SAMPLE:
        if q["difficulty"] != DifficultyLevel.ADVERSARIAL:
            continue
        sig = q["arc_signature"]
        career = next(a for a in CAREER_ARCS if a["key"] == sig["career"])
        social = next(a for a in SOCIAL_ARCS if a["key"] == sig["social"])
        valence = career["valence"] + social["valence"]
        name = q["persona"]["name"]
        rendered = {s["content"] for s in q["cleaned_daily_stream"]}

        def present(pool):
            return {t.format(self=name, name=name, peer="", friend="") for t in pool} & rendered

        if valence < 0:
            # 坏日子不得出现唱衰式干扰（那与真相同向，等于送分）
            assert not present(mask_pos), q["question_id"]
            seen_masking += len(present(mask_neg))
        elif valence > 0:
            assert not present(mask_neg), q["question_id"]
            seen_masking += len(present(mask_pos))

    assert seen_masking > 0, "对抗题应当出现与真相反向的掩饰性切片"


def test_global_summary_weaves_multiple_dimensions():
    for q in SAMPLE:
        g = q["directional_ground_truth"][Dimension.GLOBAL]["core_content"]
        assert q["persona"]["name"] in g
        assert len(g) > 60


def test_emotion_follows_career_and_social_valence():
    """情绪基调必须是事业与人际的因果结果，不能随机漂移。"""
    for q in SAMPLE:
        sig = q["arc_signature"]
        social = next(a for a in SOCIAL_ARCS if a["key"] == sig["social"])
        career = next(a for a in CAREER_ARCS if a["key"] == sig["career"])
        if social["valence"] <= -2:
            assert sig["emotion"] == "CRISIS_COLLAPSE"
        elif career["valence"] > 0 and social["valence"] > 0:
            assert sig["emotion"] == "UPLIFTED_JOY"


def test_persona_fields_are_populated():
    for q in SAMPLE:
        p = q["persona"]
        for f in ("persona_id", "name", "age", "city", "occupation", "marital_status"):
            assert p[f]
        assert 23 <= p["age"] <= 58


def test_no_unrendered_template_placeholders():
    """模板变量必须全部渲染，题面不得出现 {xxx}。"""
    for q in SAMPLE:
        blob = json.dumps(q, ensure_ascii=False)
        assert "{" not in blob.replace("{\"", "").replace("\"", ""), q["question_id"]


def test_question_ids_unique_across_bank():
    ids = [q["question_id"] for q in SAMPLE]
    assert len(set(ids)) == len(ids)


def test_all_difficulty_levels_are_produced():
    got = {q["difficulty"] for q in SAMPLE}
    assert got == {
        DifficultyLevel.EASY,
        DifficultyLevel.MEDIUM,
        DifficultyLevel.HARD,
        DifficultyLevel.ADVERSARIAL,
    }


def test_adversarial_has_more_trivia_than_easy():
    def avg(level):
        rows = [q for q in SAMPLE if q["difficulty"] == level]
        return sum(len(q["cleaned_daily_stream"]) for q in rows) / len(rows)

    assert avg(DifficultyLevel.ADVERSARIAL) > avg(DifficultyLevel.EASY)


# ---------------------------------------------------------------- 弧池完整性


@pytest.mark.parametrize(
    "pool", [CAREER_ARCS, SOCIAL_ARCS, HEALTH_ARCS, FINANCE_ARCS, EMOTION_PROFILES]
)
def test_every_arc_declares_directions_and_red_lines(pool):
    """出题铁律：每条弧都必须自带【同义词】与【红线】。"""
    for arc in pool:
        assert arc["directions"] and arc["red_lines"]
        assert not (set(arc["directions"]) & set(arc["red_lines"]))
        assert arc["core"] if "core" in arc else arc["core_content"]


def test_arc_keys_are_unique_per_pool():
    for pool in (CAREER_ARCS, SOCIAL_ARCS, HEALTH_ARCS, FINANCE_ARCS, EMOTION_PROFILES):
        keys = [a["key"] for a in pool]
        assert len(set(keys)) == len(keys)


# ---------------------------------------------------------------- 审计器


def test_validator_passes_clean_questions():
    for q in SAMPLE:
        assert validate_question(q) == []


def test_validator_catches_direction_redline_collision():
    q = json.loads(json.dumps(SAMPLE[0]))
    dim = Dimension.CAREER
    q["directional_ground_truth"][dim]["red_line_deviations"].append(
        q["directional_ground_truth"][dim]["acceptable_directions"][0]
    )
    assert any(e.startswith("S5") for e in validate_question(q))


def test_validator_catches_out_of_order_timeline():
    q = json.loads(json.dumps(SAMPLE[0]))
    q["cleaned_daily_stream"][0]["timestamp"] = "23:29"
    assert any(e.startswith("S2") for e in validate_question(q))


def test_validator_catches_missing_dimension():
    q = json.loads(json.dumps(SAMPLE[0]))
    del q["directional_ground_truth"][Dimension.FINANCE]
    assert any(e.startswith("S1") for e in validate_question(q))


def test_validator_catches_duplicate_content():
    q = json.loads(json.dumps(SAMPLE[0]))
    q["cleaned_daily_stream"][2]["content"] = q["cleaned_daily_stream"][1]["content"]
    assert any(e.startswith("S8") for e in validate_question(q))


def test_cli_writes_bank_manifest_and_sample(tmp_path: Path, capsys):
    out = tmp_path / "bank.jsonl"
    man = tmp_path / "manifest.json"
    smp = tmp_path / "sample.json"
    rc = main(
        ["--count", "40", "--generator-agent", "t", "--out", str(out),
         "--manifest", str(man), "--pretty-sample", str(smp)]
    )
    capsys.readouterr()
    assert rc == 0
    assert sum(1 for _ in out.open(encoding="utf-8")) == 40
    manifest = json.loads(man.read_text(encoding="utf-8"))
    assert manifest["total_questions"] == 40
    assert manifest["unique_question_ids"] == 40
    assert json.loads(smp.read_text(encoding="utf-8"))["question_id"]

    report = validate_bank(out)
    assert report["verdict"] == "ALL_GREEN"
