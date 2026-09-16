"""Solver 01a0aa2c-fantonghui 提纯器契约测试（铁律门禁）。

覆盖：P0 硬旁路时限、零 LLM 调用、盲做（GT 剥离）、答案 schema、
垃圾剪枝方向正确性、跨库 smoke。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aios_core.ingest.purifier_01a0aa2c_fantonghui import (
    SOLVER_AGENT, UniversalPurifier, detect_p0, purify_question)
from aios_core.simulation.cleaning_arena_protocol import (
    CleaningAnswerSubmission, DirectionalSemanticMatcher, CleaningQuestion)


def _q_a11_app():
    return {
        "question_id": "Q_agent11_T001", "generator_agent": "agent-11",
        "timestamp_utc": "2026-09-16T12:00:00Z", "difficulty": "MEDIUM",
        "sensor_stream": {}, "mic_stream": [], "voiceprint_cluster": {},
        "app_message_stream": [
            {"msg_id": "J01", "app_name": "短信", "sender": "10690",
             "content": "【孩子王】店庆3折起，回T退订", "category": "sms_marketing",
             "notification_priority": "low"},
            {"msg_id": "K01", "app_name": "健康云", "sender": "市中心医院",
             "content": "您已成功预约3月11日 放射科门诊，请提前到院取号。",
             "category": "medical", "notification_priority": "normal"},
        ],
        "user_dialogue_stream": [],
    }


def _q_fth_multi():
    return {
        "question_id": "Q_fantonghui_T001", "generator_agent": "fantonghui",
        "timestamp_utc": "2026-09-16T12:00:00Z", "difficulty": "HARD",
        "sensor_stream": {"raw_imu_g_force": [1.0, 1.1], "heart_rate_bpm": 91,
                          "pvc_burst_count": 0, "baro_hpa": 985.0,
                          "motion_state": "SHELTER_RUSH", "sensor_mode": "S05"},
        "mic_stream": [
            {"snippet_id": "mic_01", "speaker_id": "spk_stranger_17",
             "ambient_noise_db": 65.5, "text": "护士站呼叫：5床心电图推过来！"},
            {"snippet_id": "mic_02", "speaker_id": "spk_user",
             "ambient_noise_db": 70.0, "text": "租房踩大雷，一觉醒来下水倒灌家里成化粪池了，找房东索赔5万元"},
        ],
        "voiceprint_cluster": {"user_speaker_id": "spk_user",
                               "detected_speakers": ["spk_user", "spk_stranger_17"],
                               "known_bindings": {"spk_user": "大大（佩戴者）"}},
        "app_message_stream": [
            {"msg_id": "msg_01", "app": "WeChat", "sender": "砍一刀互助群",
             "content": "【帮我点一下】我只差0.01元就能提现100元现金！"},
            {"msg_id": "msg_02", "app": "WeChat", "sender": "物业管家",
             "content": "师傅已上门，主管道油污堵塞致污水倒灌，正在紧急疏通。"},
        ],
        "user_dialogue_stream": [
            {"utterance_id": "ut_01", "raw_speech": "租房合同里写了，管道问题房东负责索赔！",
             "context_scene": "深夜难眠"},
        ],
    }


def test_p0_bypass_fall_and_cardiac_within_50ms():
    fall_q = {"sensor_stream": {"raw_imu_g_force": [0.2, 0.1, 18.5, 0.3],
                                "heart_rate_bpm": 120, "pvc_burst_count": 0,
                                "motion_state": "FALL_STILLNESS", "sensor_mode": "S01"}}
    t0 = time.perf_counter()
    hit, kind = detect_p0(fall_q)
    dt_ms = (time.perf_counter() - t0) * 1000
    assert hit and kind.startswith("P0_FALL")
    assert dt_ms <= 50.0
    cardiac_q = {"sensor_stream": {"raw_imu_g_force": [1.0, 1.0],
                                  "heart_rate_bpm": 211, "pvc_burst_count": 8,
                                  "motion_state": "NOCTURNAL_REST_CRITICAL_CARDIO"}}
    hit, kind = detect_p0(cardiac_q)
    assert hit and "CARDIAC" in kind
    normal_q = {"sensor_stream": {"raw_imu_g_force": [1.0, 1.1],
                                  "heart_rate_bpm": 72, "pvc_burst_count": 0,
                                  "motion_state": "RUNNING", "sensor_mode": "S06"}}
    hit, _ = detect_p0(normal_q)
    assert not hit


def test_zero_llm_calls_and_fast():
    ans = purify_question(_q_a11_app())
    assert ans["llm_tokens_used"] == 0
    assert ans["execution_time_ms"] <= 50.0
    ans2 = purify_question(_q_fth_multi())
    assert ans2["llm_tokens_used"] == 0
    assert ans2["execution_time_ms"] <= 50.0


def test_answer_schema_validates():
    for q in (_q_a11_app(), _q_fth_multi()):
        ans = purify_question(q)
        sub = CleaningAnswerSubmission.model_validate(ans)
        assert sub.solver_agent == SOLVER_AGENT
        assert sub.solver_agent != sub.generator_agent  # 铁律五：绝不自做


def test_a11_app_prune_and_fact():
    ans = purify_question(_q_a11_app())
    assert ans["pruned_junk_ids"] == ["J01"]
    assert len(ans["extracted_facts"]) == 1
    f = ans["extracted_facts"][0]
    assert f["dimension_id"] == "dim:health"
    assert f["semantic_intent"] == "MEDICAL_APPOINTMENT"
    assert f["source_ref_id"] == "K01"
    assert "3月11日" in f["recognized_entities"]


def test_multimodal_prune_and_cluster():
    ans = purify_question(_q_fth_multi())
    assert set(ans["pruned_junk_ids"]) == {"mic_01", "msg_01"}
    # 同一下水道事件多片段应聚为少量事实（≤3），且含索赔方向词
    assert 1 <= len(ans["extracted_facts"]) <= 3
    blob = "；".join(f["summary_text"] for f in ans["extracted_facts"])
    assert any(k in blob for k in ("下水", "倒灌", "索赔", "污水", "赔偿"))


def test_blindness_no_gt_leak_usage():
    """含 GT/泄漏字段的输入与剥离后输入必须产生相同答案（盲做证明）。"""
    q = _q_fth_multi()
    q["ground_truth_facts"] = [{"fact_id": "x", "dimension_id": "dim:life",
                                "semantic_intent": "X", "core_content": "y",
                                "source_ref_id": "mic_02"}]
    q["ground_truth_junk_ids"] = ["mic_01"]
    for m in q["mic_stream"]:
        m["is_junk"] = m["snippet_id"] == "mic_01"
    a1 = purify_question(q)
    q2 = _q_fth_multi()
    a2 = purify_question(q2)
    assert a1["pruned_junk_ids"] == a2["pruned_junk_ids"]
    assert [f["semantic_intent"] for f in a1["extracted_facts"]] == \
           [f["semantic_intent"] for f in a2["extracted_facts"]]


def test_direction_match_on_synthetic():
    from aios_core.simulation.cleaning_arena_protocol import DirectionalSemanticFact, ExtractedFactSubmission
    gt = DirectionalSemanticFact(
        fact_id="f1", dimension_id="dim:health", semantic_intent="MEDICAL_APPOINTMENT",
        anchor_entities=["佩戴者", "3月11日", "放射科"],
        directional_keywords=["复查", "门诊预约", "预约就诊"],
        core_content="佩戴者已预约3月11日到放射科门诊就诊", source_ref_id="K01")
    ans = purify_question(_q_a11_app())
    sub = ExtractedFactSubmission.model_validate(ans["extracted_facts"][0])
    aligned, _ = DirectionalSemanticMatcher.is_direction_aligned(gt, sub)
    assert aligned is True
