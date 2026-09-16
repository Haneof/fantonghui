# -*- coding: utf-8 -*-
"""Unit tests for UniversalEdgePurifierV3 and 5-stage funnel pipeline.

Covers:
1. P0 pure physical hard bypass (<=50ms, 0 LLM tokens, critical safety priority);
2. Voiceprint first-stage junk pruning (spk_stranger_* and marketing prunes);
3. Sensor cross-validation (fake fall fraud vs critical health denial);
4. Contextual density gate (R1 context scene validation + R2 density limit <=3);
5. Hierarchical 4-tier entity resolution;
6. Ground truth firewall compliance (Iron Law 5).
"""

from __future__ import annotations

import time
import pytest
from aios_core.ingest.universal_edge_purifier import (
    ContextualDensityGate,
    HierarchicalEntityResolver,
    P0BypassDetector,
    SensorCrossValidator,
    UniversalEdgePurifierV3,
    VoiceprintAndJunkPruner,
)


def test_p0_bypass_detector_fall_impact():
    q = {
        "sensor_stream": {
            "heart_rate_bpm": 75,
            "pvc_burst_count": 0,
            "raw_imu_g_force": [1.1, 8.5, 0.2],
            "motion_state": "FALL_IMPACT_STATIC",
        }
    }
    t0 = time.perf_counter()
    bypass = P0BypassDetector.evaluate(q)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    assert bypass is not None
    assert bypass["priority"] == "P0_CRITICAL_SAFETY"
    assert bypass["intent"] == "FALL_IMPACT"
    assert bypass["action"] == "SOS_FALL_PIPELINE"
    assert bypass["llm_tokens"] == 0
    assert latency_ms < 50.0  # Iron Law 3


def test_p0_bypass_detector_cardiac_burst():
    q = {
        "sensor_stream": {
            "heart_rate_bpm": 160,
            "pvc_burst_count": 5,
            "raw_imu_g_force": [1.0],
            "motion_state": "RESTING",
        }
    }
    bypass = P0BypassDetector.evaluate(q)
    assert bypass is not None
    assert bypass["intent"] == "CARDIAC_BURST"
    assert bypass["llm_tokens"] == 0


def test_p0_bypass_detector_suicide_statement():
    q = {
        "sensor_stream": {"heart_rate_bpm": 70},
        "user_dialogue_stream": [
            {"utterance_id": "u01", "raw_speech": "药已经攒够一瓶了，再见。"}
        ],
    }
    bypass = P0BypassDetector.evaluate(q)
    assert bypass is not None
    assert bypass["intent"] == "SUICIDE_CRISIS"
    assert bypass["action"] == "SOS_PSYCH_PIPELINE"


def test_voiceprint_and_junk_pruning():
    q = {
        "mic_stream": [
            {"snippet_id": "m01", "speaker_id": "spk_stranger_12", "text": "叫卖西瓜！"},
            {"snippet_id": "m02", "speaker_id": "spk_wife", "text": "明天早点回家吃饭。"},
        ],
        "app_message_stream": [
            {"msg_id": "app01", "sender": "砍一刀互助群", "content": "帮我点一下提现！"},
            {"msg_id": "app02", "sender": "张三", "content": "合同已经拟好了。"},
        ],
        "user_dialogue_stream": [
            {"utterance_id": "u01", "context_scene": "酒后与朋友聚餐", "raw_speech": "我明年收购腾讯！"},
            {"utterance_id": "u02", "context_scene": "办公室工作", "raw_speech": "请把财务报表发我一下。"},
        ],
    }
    pruned = VoiceprintAndJunkPruner.prune(q)
    assert "m01" in pruned
    assert "m02" not in pruned
    assert "app01" in pruned
    assert "app02" not in pruned
    assert "u01" in pruned
    assert "u02" not in pruned


def test_sensor_cross_validation_fake_fall():
    q = {
        "sensor_stream": {
            "raw_imu_g_force": [1.02, 1.05],
            "motion_state": "GENTLE_LIE_DOWN",
        }
    }
    fraud = SensorCrossValidator.validate_fall_vs_fraud(q, "撞死我了！腰断了！赔钱！")
    assert fraud == "FAKE_FALL_FRAUD"

    # With high impact peak, not fraud
    q_real = {
        "sensor_stream": {
            "raw_imu_g_force": [12.0],
            "motion_state": "FALL_IMPACT_STATIC",
        }
    }
    fraud_real = SensorCrossValidator.validate_fall_vs_fraud(q_real, "摔倒了！")
    assert fraud_real is None


def test_sensor_cross_validation_health_denial():
    q = {
        "sensor_stream": {
            "heart_rate_bpm": 145,
            "pvc_burst_count": 4,
        }
    }
    denial = SensorCrossValidator.validate_health_denial(q, "我没事，就是心口有点闷，不用去医院")
    assert denial == "MI_DENIAL_CRITICAL"


def test_contextual_density_gate_r1_and_r2():
    candidates = [
        {"intent": "BIPOLAR_CRISIS", "scene": "白天客厅", "cls": "main"},
        {"intent": "SUICIDE_IDEATION_CRITICAL", "scene": "白天客厅", "cls": "crisis"},
        {"intent": "CARDIAC_BURST", "cls": "symptom"},
        {"intent": "FALL_IMPACT", "cls": "symptom"},
        {"intent": "BRADYCARDIA_SYNCOPE", "cls": "symptom"},
    ]
    # R1 should filter daytime suicide statement when BIPOLAR_CRISIS is present
    # R2 should limit total facts to <= 3
    filtered = ContextualDensityGate.filter_candidates(candidates)
    intents = [c["intent"] for c in filtered]

    assert "SUICIDE_IDEATION_CRITICAL" not in intents
    assert len(filtered) <= 3


def test_hierarchical_entity_resolver():
    known_bindings = {
        "spk_01": "李明",
        "spk_02": "王芳",
    }
    q = {}
    source_text = "李明向王芳提起了借款50万元的事情"
    names = HierarchicalEntityResolver.resolve_names(
        q, source_text, "spk_01", known_bindings, "佩戴者", [], 2
    )
    assert "李明" in names
    assert "王芳" in names

    amount = HierarchicalEntityResolver.extract_amount([source_text])
    assert amount == "50万元"

    institution = HierarchicalEntityResolver.extract_institution("【招商银行】您的转账已受理")
    assert institution == "招商银行"


def test_universal_edge_purifier_full_pipeline():
    purifier = UniversalEdgePurifierV3()
    q = {
        "question_id": "Q_TEST_001",
        "ground_truth_facts": [{"cheat": "forbidden"}],  # embedded GT trap
        "sensor_stream": {
            "heart_rate_bpm": 155,
            "pvc_burst_count": 4,
            "raw_imu_g_force": [1.1],
            "motion_state": "RESTING",
        },
        "mic_stream": [
            {"snippet_id": "m_stranger", "speaker_id": "spk_stranger_1", "text": "商场打折！"},
            {"snippet_id": "m_valid", "speaker_id": "spk_01", "text": "李明说心口疼得很。"},
        ],
        "app_message_stream": [
            {"msg_id": "app_spam", "sender": "砍一刀互助群", "content": "砍一刀领800元！"},
        ],
        "user_dialogue_stream": [
            {"utterance_id": "u01", "raw_speech": "我没事，就是心口有点闷"},
        ],
        "voiceprint_cluster": {
            "known_bindings": {"spk_01": "李明"},
            "user_speaker_id": "spk_user",
        },
    }

    res = purifier.purify(q)

    # 1. Firewall stripped GT
    assert "ground_truth_facts" not in q

    # 2. P0 bypass triggered
    assert res["p0_bypass"] is not None
    assert res["p0_bypass"]["intent"] == "CARDIAC_BURST"

    # 3. Junk pruned
    assert "m_stranger" in res["pruned_junk_ids"]
    assert "app_spam" in res["pruned_junk_ids"]

    # 4. Extracted facts present
    assert len(res["extracted_facts"]) >= 1
    intents = [f["semantic_intent"] for f in res["extracted_facts"]]
    assert "CARDIAC_BURST" in intents or "MI_DENIAL_CRITICAL" in intents
