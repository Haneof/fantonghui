# -*- coding: utf-8 -*-
"""solver 战队 agent-01a0aa2c 提纯器单测 (纯合成题, 不依赖任何 GT)."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aios_core.ingest.purifier_agent_01a0aa2c import (  # noqa: E402
    SOLVER_AGENT,
    p0_triage,
    route_modality,
    solve_question,
)


def _base(qid="Q_test_00001"):
    return {
        "question_id": qid,
        "generator_agent": "agent-opponent",
        "timestamp_utc": "2026-09-16T10:00:00+08:00",
        "difficulty": "HARD",
        "sensor_stream": {},
        "mic_stream": [],
        "voiceprint_cluster": {},
        "app_message_stream": [],
        "user_dialogue_stream": [],
    }


def test_self_solving_guard():
    q = _base()
    q["generator_agent"] = SOLVER_AGENT
    with pytest.raises(ValueError, match="自出自做"):
        solve_question(q)


def test_mic_debt_arrival_template():
    """归因进化 #1 回归: “肯定到你卡上” 到账承诺不得误判为呼救."""
    q = _base()
    q["mic_stream"] = [
        {"snippet_id": "m1", "kind": "wind_noise",
         "text": "（呼呼——风噪压过人声，无有效语义）",
         "ambient_noise_db": 70, "duration_s": 10, "is_background_chatter": True},
        {"snippet_id": "m2", "kind": "core_dialogue",
         "text": "周涛：下月15号之前8万肯定到你卡上，误不了",
         "ambient_noise_db": 65, "duration_s": 12,
         "is_background_chatter": False, "speaker_hint": "周涛"},
    ]
    ans = solve_question(q)
    assert ans["extracted_facts"][0]["semantic_intent"] == "DEBT_BORROWING"
    assert ans["extracted_facts"][0]["dimension_id"] == "dim:finance"
    assert ans["pruned_junk_ids"] == ["m1"]
    assert ans["llm_tokens_used"] == 0


def test_mic_faint_is_p0():
    q = _base()
    q["mic_stream"] = [
        {"snippet_id": "m1", "kind": "faint_voice",
         "text": "（微弱）……胸口疼……起不来……电话在茶几上……",
         "ambient_noise_db": 62, "duration_s": 8,
         "is_background_chatter": False, "speaker_hint": "佩戴者"},
    ]
    is_p0, hit, ms = p0_triage(q)
    assert is_p0 and hit == "FAINT_DISTRESS_CALL" and ms <= 50
    ans = solve_question(q)
    assert ans["extracted_facts"][0]["semantic_intent"] == "FAINT_DISTRESS_CALL"
    assert ans["extracted_facts"][0]["dimension_id"] == "dim:health"


def test_sensor_fall_and_off_wrist():
    q = _base()
    q["sensor_stream"] = {"segments": [
        {"seg_id": "s1", "kind": "walk_swing", "desc": "步行摆臂节律",
         "peak_g": 0.9, "hr_bpm_mean": 95, "baro_hpa": 1010.0},
        {"seg_id": "s2", "kind": "impact_then_stillness",
         "desc": "客厅沙发发生垂直冲击后长时间静止",
         "peak_g": 8.1, "free_fall_ms": 300, "stillness_after_s": 120,
         "hr_bpm_mean": 110, "baro_hpa": 1010.0},
    ]}
    ans = solve_question(q)
    assert ans["extracted_facts"][0]["semantic_intent"] == "FALL_IMPACT"
    assert "客厅沙发" in ans["extracted_facts"][0]["summary_text"]
    assert ans["pruned_junk_ids"] == ["s1"]

    q2 = _base("Q_test_00002")
    q2["sensor_stream"] = {"segments": [
        {"seg_id": "s1", "kind": "impact_off_wrist", "desc": "高冲击但脱腕",
         "peak_g": 7.0, "off_wrist_flag": True, "gait_resumed_after_s": 12,
         "hr_bpm_mean": 80, "baro_hpa": 1010.0},
    ]}
    ans2 = solve_question(q2)
    assert ans2["extracted_facts"][0]["semantic_intent"] == "OFF_WRIST_FALSE_ALARM"
    assert ans2["extracted_facts"][0]["dimension_id"] == "dim:safety"


def test_voiceprint_two_facts():
    q = _base()
    q["voiceprint_cluster"] = {
        "user_speaker_id": "vp10",
        "enrolled_contacts": ["丈夫"],
        "n_detected_speakers": 3,
        "detected_speakers": [
            {"spk_id": "vp10", "n_fragments": 40,
             "cosine_to_enrolled_user": 0.96,
             "sample_text": "好，那就这么定。", "recurrence_days_30d": 30},
            {"spk_id": "vp09", "n_fragments": 38,
             "cosine_to_enrolled_user": 0.32,
             "cosine_to_contact_bank": {"丈夫": 0.91},
             "sample_text": "合伙开店的分成比例谈拢了。",
             "recurrence_days_30d": 16, "total_talk_minutes": 75},
            {"spk_id": "vp01", "n_fragments": 2,
             "cosine_to_enrolled_user": 0.05,
             "sample_text": "外卖员：办卡吗今天有活动", "recurrence_days_30d": 0},
        ],
    }
    ans = solve_question(q)
    intents = [f["semantic_intent"] for f in ans["extracted_facts"]]
    assert intents == ["VOICEPRINT_IDENTITY_BINDING", "KEY_CONVERSATION_WITH_CONTACT"]
    assert ans["pruned_junk_ids"] == ["vp01"]


def test_app_phish_bait_never_key():
    q = _base()
    q["app_message_stream"] = [
        {"msg_id": "a1", "app_name": "短信", "sender": "+85261xxxx",
         "content": "【法院通知】您有一份传票未领取，加微信fk8899处理（诈骗）",
         "minute_offset": 10},
        {"msg_id": "a2", "app_name": "短信", "sender": "12368",
         "content": "【天河区人民法院】您涉及的劳动争议一案定于11月3日上午9时30分开庭，"
                    "请携带身份证件及证据材料准时出庭。案号（2026）民初7344号。",
         "minute_offset": 20},
    ]
    ans = solve_question(q)
    assert ans["extracted_facts"][0]["semantic_intent"] == "COURT_SUMMONS"
    assert ans["extracted_facts"][0]["dimension_id"] == "dim:legal"
    assert ans["extracted_facts"][0]["source_ref_id"] == "a2"
    assert ans["pruned_junk_ids"] == ["a1"]


def test_dialogue_drunk_vs_resignation():
    q = _base()
    q["user_dialogue_stream"] = [
        {"utterance_id": "u1", "raw_speech": "累了累了，躺平躺平",
         "context_scene": "口头禅", "emotional_tone": "平淡"},
        {"utterance_id": "u2",
         "raw_speech": "（酒局，含混）跟你们说，下个月我必收购腾讯，谁拦我跟谁急！",
         "context_scene": "酒局吹牛", "emotional_tone": "醉酒亢奋"},
    ]
    ans = solve_question(q)
    assert ans["extracted_facts"][0]["semantic_intent"] == "DRUNK_BOASTING"
    assert "并非真实计划" in ans["extracted_facts"][0]["summary_text"]

    q2 = _base("Q_test_00003")
    q2["user_dialogue_stream"] = [
        {"utterance_id": "u1", "raw_speech": "辞职报告我昨晚写完了，今天就发HR，别劝我",
         "context_scene": "郑重决定", "emotional_tone": "平静坚定"},
    ]
    ans2 = solve_question(q2)
    assert ans2["extracted_facts"][0]["semantic_intent"] == "RESIGNATION_DECISION"


def test_dialogue_hidden_crisis_with_vitals():
    q = _base()
    q["sensor_stream"] = {"segments": [
        {"seg_id": "imu1", "kind": "concurrent_vitals", "hr_bpm_mean": 128,
         "eda_surge": True, "motion_state": "leaning_still"}]}
    q["user_dialogue_stream"] = [
        {"utterance_id": "u1", "raw_speech": "没事没事，老毛病，缓缓就好……（大汗，说话断续）",
         "context_scene": "强撑否认", "emotional_tone": "虚弱嘴硬"},
    ]
    assert route_modality(q) == "dialogue"
    is_p0, hit, _ = p0_triage(q)
    assert is_p0 and hit == "HIDDEN_CARDIAC_CRISIS"
    ans = solve_question(q)
    assert ans["extracted_facts"][0]["semantic_intent"] == "HIDDEN_CARDIAC_CRISIS"
    assert "128bpm" in ans["extracted_facts"][0]["summary_text"]


def test_p0_triage_latency_budget():
    q = _base()
    q["mic_stream"] = [{"snippet_id": f"m{i}", "kind": "wind_noise",
                        "text": "风噪" * 20, "is_background_chatter": True}
                       for i in range(20)]
    t0 = time.perf_counter()
    p0_triage(q)
    assert (time.perf_counter() - t0) * 1000 <= 50
