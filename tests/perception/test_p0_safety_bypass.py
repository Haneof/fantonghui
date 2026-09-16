"""铁律三验证：P0 紧急特权硬旁路必须 <= 50ms、大模型调用严格为 0。"""

from __future__ import annotations

import time

import pytest

from aios_core.perception.p0_safety_bypass import (
    HR_BRADY_CRITICAL_BPM,
    HR_TACHY_CRITICAL_BPM,
    PVC_BURST_CRITICAL,
    WakePriority,
    evaluate_p0_bypass,
    evaluate_question_p0,
)

#: 铁律三规定的硬预算。
P0_BUDGET_MS = 50.0


def test_cardiac_arrest_triggers_p0():
    """心搏骤停（重度心动过缓）必须触发 P0。"""
    verdict = evaluate_p0_bypass({"heart_rate_bpm": HR_BRADY_CRITICAL_BPM - 5})
    assert verdict.triggered is True
    assert verdict.priority is WakePriority.P0_CRITICAL_SAFETY
    assert any("BRADY" in r for r in verdict.reasons)


def test_malignant_tachycardia_triggers_p0():
    verdict = evaluate_p0_bypass({"heart_rate_bpm": HR_TACHY_CRITICAL_BPM + 20})
    assert verdict.triggered is True
    assert any("TACHY" in r for r in verdict.reasons)


def test_fall_with_static_pause_triggers_p0():
    """严重摔倒后静止 —— 失能跌倒，必须触发。"""
    verdict = evaluate_p0_bypass(
        {"motion_state": "FALL_TILT_AFTER_PAUSE", "pause_seconds": 4.2, "heart_rate_bpm": 90}
    )
    assert verdict.triggered is True
    assert any("FALL" in r for r in verdict.reasons)


def test_pvc_burst_triggers_p0():
    verdict = evaluate_p0_bypass(
        {"pvc_burst_count": PVC_BURST_CRITICAL + 1, "heart_rate_bpm": 95}
    )
    assert verdict.triggered is True


def test_sos_utterance_triggers_p0():
    verdict = evaluate_p0_bypass({"heart_rate_bpm": 92}, ["救命啊，快叫救护车！"])
    assert verdict.triggered is True
    assert any("SOS" in r for r in verdict.reasons)


def test_fake_fall_does_not_trigger_on_speech_alone():
    """碰瓷/假摔属于对抗样本，不得仅凭原话误报（铁律一：质量第一）。"""
    verdict = evaluate_p0_bypass(
        {"heart_rate_bpm": 88, "motion_state": "STANDING"},
        ["哎哟摔死我了快赔钱！我髋关节都断了要赔五万！这就是碰瓷"],
    )
    assert verdict.triggered is False


def test_normal_stream_does_not_trigger():
    verdict = evaluate_p0_bypass(
        {"heart_rate_bpm": 78, "pvc_burst_count": 0, "motion_state": "RUNNING"}
    )
    assert verdict.triggered is False
    assert verdict.priority is WakePriority.P1_NORMAL


def test_zero_llm_and_no_world_model():
    """铁律三硬约束：大模型调用严格为 0，世界模型让路。"""
    verdict = evaluate_p0_bypass({"heart_rate_bpm": 30})
    assert verdict.llm_calls == 0
    assert verdict.world_model_consulted is False


def test_latency_within_50ms_budget():
    """1000 次连续判定，单次耗时必须远低于 50ms。"""
    sensor = {
        "heart_rate_bpm": 31,
        "pvc_burst_count": 7,
        "motion_state": "FALL_IMPACT_STATIC",
        "pause_seconds": 3.9,
        "raw_imu_g_force": [0.1, 4.8, 0.3] * 8,
        "sensor_label": "心律失常恶性事件",
    }
    texts = ["胸口剧痛喘不上气", "救命"]
    worst = 0.0
    for _ in range(1000):
        started = time.perf_counter()
        verdict = evaluate_p0_bypass(sensor, texts)
        worst = max(worst, (time.perf_counter() - started) * 1000.0)
        assert verdict.triggered is True
    assert worst <= P0_BUDGET_MS, f"P0 穿透耗时 {worst:.3f}ms 超出 50ms 预算"


def test_evaluate_question_p0_reads_streams():
    question = {
        "sensor_stream": {"heart_rate_bpm": 84},
        "user_dialogue_stream": [{"raw_speech": "胸口剧痛，快叫救护车"}],
        "mic_stream": [],
    }
    verdict = evaluate_question_p0(question)
    assert verdict.triggered is True
    assert verdict.llm_calls == 0
