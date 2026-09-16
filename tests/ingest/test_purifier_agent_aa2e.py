# -*- coding: utf-8 -*-
"""agent-aa2e 清洗提纯器回归测试（不依赖对手题库文件，用内联样题验证五大铁律）。"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "purifier_agent_aa2e", REPO / "src/aios_core/ingest/purifier_agent_aa2e.py")
purifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(purifier)


def _sample_question() -> dict:
    return {
        "question_id": "Q_test_00001",
        "generator_agent": "fantonghui",
        "sensor_stream": {
            "raw_imu_g_force": [1.0, 0.98, 29.4, 1.01],
            "heart_rate_bpm": 101,
            "pvc_burst_count": 0,
            "motion_state": "FALL_IMPACT_STATIC",
        },
        "mic_stream": [
            {"snippet_id": "mic_01", "speaker_id": "spk_stranger_03",
             "text": "大刀肉大刀肉！两块钱一串！现烤现卖！"},
            {"snippet_id": "mic_02", "speaker_id": "spk_neighbor",
             "text": "合同是写了我负责维修，可你5万元的贵重物品放地上泡水，怪我咯？"},
        ],
        "voiceprint_cluster": {
            "user_speaker_id": "spk_user",
            "detected_speakers": ["spk_stranger_03", "spk_neighbor", "spk_user"],
            "known_bindings": {"spk_neighbor": "何欣怡", "spk_user": "大大（佩戴者）"},
        },
        "app_message_stream": [
            {"msg_id": "msg_01", "app": "WeChat", "sender": "砍一刀互助群",
             "content": "【帮我点一下】我只差0.01元就能提现100元现金！"},
            {"msg_id": "msg_02", "app": "BankApp", "sender": "银行",
             "content": "转账失败：对方账户状态异常，6.8万元已原路退回，请勿轻信截图。"},
            {"msg_id": "msg_03", "app": "WeChat", "sender": "曾曜威",
             "content": "【转账截图】已向您转账6.8万元，请查收！[图片]"},
        ],
        "user_dialogue_stream": [
            {"utterance_id": "ut_01", "context_scene": "酒后与朋友聚餐",
             "raw_speech": "下个月我就收购腾讯，到时候你们都来当总监！"},
            {"utterance_id": "ut_02", "context_scene": "身体不适时独处",
             "raw_speech": "哎呦！摔了一跤，半天爬不起来……"},
        ],
    }


def test_iron_law_3_p0_bypass_is_fast_and_llm_free() -> None:
    q = _sample_question()
    t0 = time.perf_counter()
    p0 = purifier.emergency_bypass(q)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert p0 is not None, "剧烈跌倒冲击必须触发 P0 硬旁路"
    assert p0["p0"] == "FALL_IMPACT", "跌倒冲击应路由至 SOS_FALL_PIPELINE"
    assert p0["llm_calls"] == 0, "铁律三：P0 旁路大模型调用必须严格为 0"
    assert elapsed_ms <= 50.0, "铁律三：P0 旁路耗时必须 <= 50ms"


def test_iron_law_4_physical_pruning() -> None:
    ans = purifier.purify(_sample_question())
    pruned = set(ans["pruned_junk_ids"])
    assert {"mic_01", "msg_01", "ut_01"} <= pruned, "叫卖/砍一刀/酒后吹牛必须物理剪枝"
    assert "mic_02" not in pruned and "msg_02" not in pruned, "核心事实证据不得误删"
    assert "ut_02" not in pruned, "真实体征原话不得误删"


def test_fact_extraction_direction_and_entities() -> None:
    ans = purifier.purify(_sample_question())
    facts = {f["semantic_intent"]: f for f in ans["extracted_facts"]}
    assert "SEWAGE_BACKFLOW" in facts, "下水倒灌主事件必须被提纯"
    assert "FAKE_TRANSFER_COUNTER" in facts, "T01 假转账陷阱必须被识破"
    assert "FALL_INJURY_ALERT" in facts, "传感器互证的真实跌倒必须立项"
    sewage = facts["SEWAGE_BACKFLOW"]
    assert sewage["dimension_id"] == "dim:life", "维度归属必须正确"
    assert "何欣怡" in sewage["recognized_entities"], "关键当事人不得张冠李戴"
    assert "5万元" in sewage["recognized_entities"], "涉案金额必须召回"
    fake = facts["FAKE_TRANSFER_COUNTER"]
    assert "曾曜威" in fake["recognized_entities"], "假转账当事人应取自截图发送方"
    assert ans["llm_tokens_used"] == 0 if "llm_tokens_used" in ans else True


def test_iron_law_5_no_self_solving_marker() -> None:
    ans = purifier.purify(_sample_question())
    assert ans["solver_agent"] == "agent-aa2e"
    assert ans["generator_agent"] == "fantonghui"
    assert ans["solver_agent"] != ans["generator_agent"], "铁律五：严禁自出自做"
