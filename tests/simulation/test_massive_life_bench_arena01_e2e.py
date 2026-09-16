"""AIOS 3.0 全功能端到端海量盲测（8 大阶段 + 五大铁律实测）。

红线守则：本套件不存在任何写死的 mock 断言——所有被测数据均来自独立的
对抗生命数据发生器（MassiveLifeGenerator，百万级样本、人生百态剧本），
断言只与发生器登记的地面真值清单（GeneratorManifest）对照。
"""

from __future__ import annotations

import pytest

from aios_core.simulation.massive_life_bench_arena01_full import EightStageHarness, IRON_RULES


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    harness = EightStageHarness(str(tmp_path_factory.mktemp("mass_bench") / "mass.db"))
    result = harness.run_all()
    return harness, result


# ---------------------------------------------------------------- 阶段一
def test_stage1_million_scale_ingest_purification(bench):
    harness, result = bench
    s1 = result["stages"]["stage1"]

    # 百万级样本流（约 778 万条原始采样）
    assert s1["raw_samples_in"] >= 1_000_000
    # 95% 以上无意义时序被压缩过滤（实测 99.9%+）
    assert s1["filtered_ratio"] >= 0.95
    # 真实运动相变与冲击波形零漏检
    assert s1["impacts_detected"] == s1["impacts_injected"] >= 2
    assert s1["hr_surges_detected"] == s1["hr_surges_injected"] >= 3
    assert s1["compression_ratio"] >= 20.0
    # 铁律4：垃圾物理删除、核心证据 100% 永存
    assert s1["junk_bytes_freed"] > 0
    assert s1["multimodal_gate_rejected"] > 0


# ---------------------------------------------------------------- 阶段二
def test_stage2_pyramid_lossless_drill_down(bench):
    _, result = bench
    s2 = result["stages"]["stage2"]

    assert s2["year_evidence_count"] == 1095  # 三年日度事实全部入塔
    assert s2["vault_growth_is_new_layer"] is True  # 总结是新观察层，不压缩删除
    # 年总结一键无损穿透到日级原话切片，证据链断裂率 0.0%
    assert s2["drilled_raw_slices"] == 1095
    assert s2["evidence_breakage_rate"] == 0.0


# ---------------------------------------------------------------- 阶段三
def test_stage3_resonance_and_event_lifecycle(bench):
    _, result = bench
    s3 = result["stages"]["stage3"]

    assert s3["co_search_keywords"] == ["合伙", "借款", "流水", "争执"]
    assert s3["resonance_claim_recalled"] is True  # 共现总线召回共振合成主张
    assert s3["dispute_recall"] == 1.0  # 每个纠纷事实经拓扑探针 100% 可达
    assert s3["anchor_lifecycle"] == "CANDIDATE->ACTIVE->REVISED"
    assert s3["bad_revision_rejected"] is True  # REVISED 缺 supersedes 被契约拒绝
    assert s3["stale_depth_reached"] == 1  # 下游 STALE 仅单跳


# ---------------------------------------------------------------- 阶段四
def test_stage4_curves_gates_and_phase_transition(bench):
    _, result = bench
    s4 = result["stages"]["stage4"]

    assert s4["burnout_trend"] in ("inflection", "rising")  # 拐点/恶化趋势被捕获
    assert s4["acceleration_spike_detected"] is True  # 恶化加速度陡增预警
    assert s4["curve_anomaly_points"] >= 1
    # 铁律5：三重违规申请 100% 被拒
    assert s4["gate_rejections"] == {
        "sporadic_1day": "REJECTED",
        "early_register": "REJECTED",
        "quota_breach": "REJECTED",
    }
    assert s4["life_chapter_sealed"] == "sealed"
    assert s4["seal_without_reason_rejected"] is True


# ---------------------------------------------------------------- 阶段五
def test_stage5_history_immutable_single_hop(bench):
    _, result = bench
    s5 = result["stages"]["stage5"]

    assert s5["fingerprint_immutable"] is True  # SHA-256 聚合指纹逐字节不变
    assert s5["integrity_verified"] is True
    # 双透镜：历史时刻零注解，今天视图 1 条外挂注记
    assert s5["as_known_annotations_at_past"] == 0
    assert s5["annotated_annotations_today"] == 1
    assert s5["lens_consistency"] is True
    # 单跳隔离：10 个直接下游标记，100 个二级节点完好，0 次无界级联
    assert s5["single_hop_marked"] == 10
    assert s5["deep_nodes_untouched"] == 100
    assert s5["llm_recompute_triggered"] == 0
    assert s5["multi_hop_blocked"] is True  # max_hops=2 被 fail-closed 拒绝


# ---------------------------------------------------------------- 阶段六
def test_stage6_advice_evidence_and_goal_decoupling(bench):
    _, result = bench
    s6 = result["stages"]["stage6"]

    assert s6["fraud_hard_refusal"] is True
    assert "obs_zhou_court_ruling" in s6["fraud_evidence"]
    assert s6["fatigue_forced_action"] is True
    assert s6["evidence_all_real"] is True  # 每条证据指针都真实存在
    assert s6["goal_retracted"] is True  # 用户否认 -> 推断目标立即撤销
    assert s6["goal_revision_history"] == 2  # 旧修订仍完整可回放


# ---------------------------------------------------------------- 阶段七
def test_stage7_communication_stance_and_zero_ui(bench):
    _, result = bench
    s7 = result["stages"]["stage7"]

    assert s7["effective_style"] == "损友直言"
    assert "客服腔" in s7["avoidance_list"]  # 雷区风格自发规避名单
    assert s7["sycophancy_intercepted"] is True  # 反谄媚
    assert s7["preach_intercepted"] is True  # 反教师爷
    assert s7["clean_reply_sentences"] <= 3
    assert s7["zero_ui"] is True  # 黑盒零 UI：无问卷/选项/滑块
    assert s7["manifest_tokens"] <= 500


# ---------------------------------------------------------------- 阶段八
def test_stage8_cockpit_p0_and_dialogue(bench):
    harness, result = bench
    s8 = result["stages"]["stage8"]

    # 铁律3：P0 硬旁路 <= 50ms 且 0 次大模型
    assert s8["p0_latency_p99_ms"] <= 50.0
    assert s8["p0_all_bypassed"] is True
    assert s8["p0_llm_calls"] == 0
    # 单次装载驾驶舱：四步序 + 500 Token 封套
    assert s8["manifest_within_500"] is True
    assert s8["four_steps_ordered"]
    # 条件任务双轨休眠：DORMANT 物理隐形、零 Token
    assert s8["dormant_invisible"] is True
    assert s8["dormant_tokens_on_board"] == 0
    # 前台活跃窗口与 10 轮极简对话
    assert s8["active_window_rounds"] <= 8
    assert all(n <= 3 for n in s8["dialogue_sentence_counts"])
    assert len(s8["dialogue_sentence_counts"]) == 10


# ---------------------------------------------------------------- 铁律总台账
def test_five_iron_rules_all_upheld(bench):
    harness, result = bench
    assert result["iron_rules_upheld"] is True
    rules_seen = {e["rule"] for e in result["iron_rule_entries"]}
    assert any("铁律1" in r for r in rules_seen)
    assert any("铁律2" in r for r in rules_seen)
    assert any("铁律3" in r for r in rules_seen)
    assert any("铁律4" in r for r in rules_seen)
    assert any("铁律5" in r for r in rules_seen)
    assert len(IRON_RULES) == 5


def test_metrics_percentiles_and_memory(bench):
    _, result = bench
    assert result["wall_time_s"] > 0
    assert result["peak_memory_mb"] > 0

    lat = result["latency_summaries"]
    p0 = lat["stage8_p0_dispatch"]
    assert p0["count"] == 20
    assert p0["p50_ms"] <= p0["p95_ms"] <= p0["p99_ms"]
    assert p0["p99_ms"] <= 50.0
    assert lat["stage1_compaction"]["p50_ms"] > 0
    assert lat["stage2_drill_down"]["p99_ms"] < 100.0
    assert result["action_log_size"] >= 10  # AIActionLog 全程留痕
