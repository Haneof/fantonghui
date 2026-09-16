"""Solver ``01a0aa2c-fantonghui`` 数据清洗器 · 五条铁律合规回归测试。

覆盖：
* 铁律一（质量第一）：提炼事实必须锚点完整、方向可判、无幻觉；
* 铁律二（历史不可篡改）：事实只在 T_now 挂载，UPDATE/DELETE 被物理阻断；
* 铁律三（紧急特权硬旁路）：P0 场景 ≤50ms、零大模型调用、世界模型让路；
* 铁律四（大模型自主物理删除）：营销/验证码/环境噪声进入 ``pruned_junk_ids`` 并物理粉碎；
* 铁律五（绝不自出自做）：跨 Git 取证，禁止取我方分支、禁止标答进入求解通道。
"""

from __future__ import annotations

import json
import sqlite3
import time

import pytest

from aios_core.ingest.purifier_01a0aa2c import (
    SOLVER_AGENT,
    SOLVER_BRANCH,
    EdgeByteShredder,
    GroundTruthFirewallViolation,
    JunkPolicy,
    P0CriticalSafetyBypass,
    SelfSolvingViolation,
    CleaningSolver01a0aa2c,
    TNowFactLedger,
    assert_cross_team_provenance,
    assert_ground_truth_firewall,
    extract_entities,
    iter_items,
)
from aios_core.simulation.cleaning_arena_protocol import (
    CleaningQuestion,
    DirectionalSemanticMatcher,
)


# ---------------------------------------------------------------------------
# 测试夹具：一题「P0 真实跌倒 + 营销噪声」的合成题库记录
# ---------------------------------------------------------------------------


def _p0_question() -> dict:
    return {
        "question_id": "Q_agent-synthetic_90001",
        "generator_agent": "agent-synthetic",
        "timestamp_utc": "2026-08-01T10:00:00Z",
        "difficulty": "HARD",
        "sensor_stream": {
            "device_id": "aios-band-p99-0101",
            "fragments": [
                {
                    "fragment_id": "S90001K01",
                    "kind": "imu_impact",
                    "label": "hard_impact_freefall_preceded",
                    "label_zh": "真实跌倒冲击波形",
                    "window_offset_s": 2286.0,
                    "duration_s": 4,
                    "g_peak": 5.43,
                    "g_rms": 1.27,
                    "impact_rise_ms": 73,
                    "freefall_segment_ms": 380,
                    "post_impact_stillness_s": 115,
                    "posture_change_deg": 120,
                    "note": "存在自由落体前段 + 三轴合成冲顶 + 姿态角大幅翻转，符合真实跌倒力学三联征",
                },
                {
                    "fragment_id": "S90001J01",
                    "kind": "imu_window",
                    "label": "typing_vibration",
                    "g_peak": 1.02,
                    "note": "键盘敲击震动",
                },
            ],
        },
        "mic_stream": [
            {
                "snippet_id": "M90001J01",
                "scene": "mall_promotion",
                "ambient_noise_db": 79,
                "snr_db": 2.0,
                "asr_confidence": 0.72,
                "text": "商场广播：全场三折起，办卡立减五十，欢迎了解。",
                "is_background_chatter": True,
            },
        ],
        "voiceprint_cluster": {
            "total_detected_speakers": 24,
            "speakers": [
                {
                    "speaker_frag_id": "V90001K01",
                    "cluster_label": "SPK_USER",
                    "role": "佩戴者本人",
                    "fragment_count": 30,
                    "total_duration_s": 689.5,
                    "cosine_to_user": 1.0,
                    "is_transient": False,
                    "ttl_policy": "permanent_anchor",
                },
                {
                    "speaker_frag_id": "V90001J01",
                    "cluster_label": "SPK_STRANGER_07",
                    "role": "推销员",
                    "fragment_count": 2,
                    "total_duration_s": 11.0,
                    "cosine_to_user": 0.21,
                    "is_transient": True,
                    "ttl_policy": "expire_24h",
                },
            ],
        },
        "app_message_stream": [
            {
                "msg_id": "A90001K01",
                "category": "bank",
                "app_name": "手机银行",
                "sender": "招商银行",
                "content": "您尾号1234账户8月15日入账5000.00元，对方户名：李国强。",
            },
            {
                "msg_id": "A90001J01",
                "category": "sms_code",
                "sender": "95588",
                "content": "【验证码】839201，切勿泄露给他人。",
            },
        ],
        "user_dialogue_stream": [],
    }


def _question_with_ground_truth() -> dict:
    question = _p0_question()
    question["ground_truth_facts"] = [
        {
            "fact_id": "F90001_01",
            "dimension_id": "dim:safety",
            "semantic_intent": "FALL_IMPACT",
            "anchor_entities": ["5.43g", "115秒", "自由落体"],
            "directional_keywords": ["摔倒", "跌倒", "倒地", "坠地", "冲击峰值", "跌倒后静止"],
            "core_content": "存在自由落体前段 + 硬冲击 5.43g + 姿态角翻转，判定真实跌倒",
            "source_ref_id": "S90001K01",
            "confidence": 0.97,
        }
    ]
    question["ground_truth_junk_ids"] = [
        "S90001J01",
        "M90001J01",
        "V90001J01",
        "A90001J01",
    ]
    return question


# ---------------------------------------------------------------------------
# 铁律五：跨 Git 取证 —— 绝不自出自做
# ---------------------------------------------------------------------------


def test_cross_team_provenance_rejects_self_solving() -> None:
    assert_cross_team_provenance("agent-11", SOLVER_BRANCH.split("/", 1)[1])  # 对手可做
    with pytest.raises(SelfSolvingViolation):
        assert_cross_team_provenance("agent-11", SOLVER_BRANCH)
    with pytest.raises(SelfSolvingViolation):
        assert_cross_team_provenance(SOLVER_AGENT, "arena/01a0a9f6-fantonghui")


def test_ground_truth_firewall_blocks_answer_key() -> None:
    with pytest.raises(GroundTruthFirewallViolation):
        assert_ground_truth_firewall({"question_id": "q", "ground_truth_facts": []})

    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    with pytest.raises(GroundTruthFirewallViolation):
        solver.purify(_question_with_ground_truth())


def test_solver_result_declares_generator_and_solver_identity() -> None:
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    submission = solver.purify(_p0_question())
    assert submission.solver_agent == SOLVER_AGENT
    assert submission.generator_agent == "agent-synthetic"
    assert submission.solver_agent != submission.generator_agent


# ---------------------------------------------------------------------------
# 铁律三：紧急特权硬旁路（≤50ms、0 大模型调用）
# ---------------------------------------------------------------------------


def test_p0_bypass_detects_fall_and_stays_under_50ms() -> None:
    verdict = P0CriticalSafetyBypass().scan(_p0_question())
    assert verdict.triggered is True
    assert verdict.latency_ms <= 50.0
    assert verdict.llm_calls == 0


def test_p0_hard_bypass_produces_fact_with_zero_llm_calls() -> None:
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    submission = solver.purify(_p0_question())
    assert submission.llm_tokens_used == 0
    assert submission.extracted_facts, "P0 场景必须直接产出事实（世界模型让路）"
    assert submission.extracted_facts[0].dimension_id == "dim:safety"
    assert solver.stats["p0_events"] >= 1
    assert solver.stats["p0_llm_calls"] == 0
    assert solver.stats["p0_max_latency_ms"] <= 50.0


def test_p0_latency_p99_is_within_hard_budget() -> None:
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    latencies = []
    start = time.perf_counter()
    for _ in range(50):
        solver.purify(_p0_question())
        latencies.append(solver.audits[-1].p0_latency_ms)
    wall_ms = (time.perf_counter() - start) * 1000.0 / 50.0
    assert max(latencies) <= 50.0
    assert wall_ms <= 50.0  # 端到端单题时延同样满足硬旁路预算


# ---------------------------------------------------------------------------
# 铁律四：垃圾物理删除（营销/验证码/环境噪声 → pruned_junk_ids + 字节粉碎）
# ---------------------------------------------------------------------------


def test_junk_policy_prunes_marketing_and_noise() -> None:
    policy = JunkPolicy()
    verdict = P0CriticalSafetyBypass().scan(_p0_question())
    items = {item.item_id: item for item in iter_items(_p0_question())}
    for junk_id in ("S90001J01", "M90001J01", "V90001J01", "A90001J01"):
        is_junk, reason = policy.decide(items[junk_id], verdict)
        assert is_junk, f"{junk_id} 应判为垃圾：{reason}"
    is_junk, reason = policy.decide(items["S90001K01"], verdict)
    assert not is_junk, f"P0 跌倒证据不可剪：{reason}"


def test_shredder_physically_removes_bytes_and_keeps_tombstone() -> None:
    shredder = EdgeByteShredder()
    shredder.sink("M90001J01", "mic", b"x" * 4096)
    assert shredder.is_recoverable("M90001J01") is True
    receipt = shredder.shred("M90001J01")
    assert shredder.is_recoverable("M90001J01") is False
    assert receipt.bytes_reclaimed == 4096
    assert receipt.tombstone.startswith("tombstone::mic::")
    assert shredder.reclaimed_bytes == 4096
    assert len(shredder.receipts) == 1


def test_pruned_junk_ids_are_reported_and_keep_p0_evidence() -> None:
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    submission = solver.purify(_p0_question())
    pruned = set(submission.pruned_junk_ids)
    assert {"S90001J01", "M90001J01", "V90001J01", "A90001J01"} <= pruned
    assert "S90001K01" not in pruned
    assert solver.stats["junk_items_physically_shredded"] >= 4


# ---------------------------------------------------------------------------
# 铁律二：历史不可篡改（T_now 挂载 + UPDATE/DELETE 物理阻断）
# ---------------------------------------------------------------------------


def test_ledger_blocks_history_mutation() -> None:
    ledger = TNowFactLedger()
    ledger.archive_observation(
        observation_id="S90001K01",
        question_id="Q_agent-synthetic_90001",
        observed_at="2026-08-01T10:00:00Z",
        modality="sensor",
        payload_sha256="deadbeef",
    )
    ledger.mount_fact(
        fact_id="fact-1",
        question_id="Q_agent-synthetic_90001",
        observed_at="2026-08-01T10:00:00Z",
        dimension_id="dim:safety",
        semantic_intent="FALL_IMPACT",
        summary_text="自由落体后硬冲击 5.43g",
        source_ref_id="S90001K01",
        recognized_entities=["5.43g"],
        direction_cluster=["摔倒", "跌倒"],
    )
    blocked = ledger.attempts_to_mutate_history()
    assert blocked == (True, True), "UPDATE/DELETE 必须被触发器阻断"
    assert ledger.fact_count() == 1
    assert ledger.observation_count() == 1

    with pytest.raises(sqlite3.DatabaseError):
        ledger.connection.execute("UPDATE fact_ledger SET semantic_intent = 'X'")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.connection.execute("DELETE FROM observation_archive")


def test_facts_are_mounted_at_t_now_only() -> None:
    ledger = TNowFactLedger()
    common = dict(
        question_id="Q_agent-synthetic_90001",
        observed_at="2026-08-01T10:00:00Z",
        dimension_id="dim:finance",
        semantic_intent="BANK_LARGE_TRANSFER",
        summary_text="入账 5000 元",
        source_ref_id="A90001K01",
        recognized_entities=["5000元"],
        direction_cluster=["入账"],
    )
    first = ledger.mount_fact(fact_id="fact-1", **common)
    second = ledger.mount_fact(fact_id="fact-2", **common)
    assert first and second
    rows = ledger.connection.execute(
        "SELECT COUNT(*) FROM fact_ledger WHERE mounted_at IS NOT NULL"
    ).fetchone()
    assert rows[0] == 2
    # 幂等重放：同一事实重复挂载不产生第二条账目
    again = ledger.mount_fact(fact_id="fact-1", **common)
    assert again == first
    assert ledger.fact_count() == 2


# ---------------------------------------------------------------------------
# 铁律一：事实提纯质量（锚点完整、方向可判、零幻觉）
# ---------------------------------------------------------------------------


def test_entity_synthesis_recovers_units_and_roles() -> None:
    items = {item.item_id: item for item in iter_items(_p0_question())}
    sensor_entities = extract_entities(items["S90001K01"])
    assert "5.43g" in sensor_entities
    assert "115秒" in sensor_entities
    assert "1分钟" in sensor_entities or "1.9分钟" in sensor_entities  # 秒 → 分钟换算

    voiceprint_entities = extract_entities(items["V90001K01"])
    assert "佩戴者" in voiceprint_entities
    assert "30人" in voiceprint_entities

    # 关闭锚点合成后，数值/单位/字段换算锚点不再产生（消融口径一致）
    bare = extract_entities(items["S90001K01"], synthesize=False)
    assert "5.43g" not in bare


def test_end_to_end_submission_passes_directional_judging() -> None:
    question = _question_with_ground_truth()
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    submission = solver.purify({k: v for k, v in question.items() if not k.startswith("ground_truth")})
    report = DirectionalSemanticMatcher.evaluate_submission(CleaningQuestion(**question), submission)
    assert report.is_self_solving_violation is False
    assert report.hallucination_count == 0, "严禁幻觉"
    assert report.junk_prune_rate == 1.0, "垃圾必须全部物理剪枝"
    assert report.direction_match_rate == 1.0, report.critique_notes
    assert report.final_score >= 90.0, report.critique_notes


def test_submission_contains_anchor_text_and_source_ref() -> None:
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    submission = solver.purify(_p0_question())
    fact = submission.extracted_facts[0]
    assert fact.source_ref_id == "S90001K01"
    summary = fact.summary_text
    assert "5.43g" in summary or "5.43g" in fact.recognized_entities
    assert "自由落体" in summary
    assert fact.dimension_id == "dim:safety"
    assert len(summary) <= 600, "事实描述必须克制，禁止口水话"


def test_submission_is_json_serialisable_for_arena_handover() -> None:
    solver = CleaningSolver01a0aa2c(source_branch="arena/01a0a9f6-fantonghui")
    payload = json.loads(solver.purify(_p0_question()).model_dump_json())
    assert payload["question_id"] == "Q_agent-synthetic_90001"
    assert set(payload) >= {"question_id", "solver_agent", "extracted_facts", "pruned_junk_ids"}
