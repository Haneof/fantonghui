"""MEGA-PIPELINE 总纲验收：8 大阶段端到端盲测 + 铁律捍卫账本。

语料全部来自对抗发生器（MassiveLifeBenchGenerator），断言只审真实模块的
实际行为；任何「自己写死 mock 然后自 assert」的场景都视为本测试的失败。
"""

from __future__ import annotations

import pytest

from aios_core.simulation.total_pipeline_bench import (
    DIALOGUE_SENTENCE_LIMIT,
    P0_LATENCY_REDLINE_MS,
    ROLLING_TOKEN_LIMIT,
    TotalPipelineBench,
)


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    d = tmp_path_factory.mktemp("mega")
    return TotalPipelineBench(str(d / "world.db"), scale=4000)


# ---------------------------------------------------------------------------
# S1 摄入清洗（铁律 4）
# ---------------------------------------------------------------------------


def test_s1_edge_intake_does_not_drown_storage(bench):
    r = bench.stage_1_edge_intake()
    p = r.promises
    assert p["collapse_ratio"] >= 100, "平稳流必须兑现百倍级塌缩"
    assert p["shock_independent"], "IMU 跌倒冲击独立成件，绝不进均值"
    assert p["spikes_kept"] >= 10, "突变拍逐拍永存（含保护环）"
    assert p["caption_only"], "图片只存文字 Caption"
    assert p["low_quality_dropped"], "低画质图片垃圾物理丢弃，不落库"
    assert p["sink_retained_bytes"] == 0, "原始字节保留量归零（铁律 4 硬面）"
    assert p["core_evidence_preserved"] > 0, "借款/判决/合同证据链 100% 永存"


# ---------------------------------------------------------------------------
# S2 时间金字塔
# ---------------------------------------------------------------------------


def test_s2_pyramid_drill_down_zero_breaks(bench):
    r = bench.stage_2_time_pyramid()
    p = r.promises
    assert p["layers"] == 4
    assert p["drill_breaks"] == 0, "年结论穿透到原始拍，证据链断裂率必须为 0.0%"
    assert p["raw_layer_intact"], "总结是新观察层，绝不压缩删除原始记录"
    assert p["vault_size"] >= 30


# ---------------------------------------------------------------------------
# S3 多维共振
# ---------------------------------------------------------------------------


def test_s3_cooccurrence_bus_and_event_lifecycle(bench):
    r = bench.stage_3_multidim_resonance()
    p = r.promises
    assert p["total_hits"] > 0, "多关键词共现总线拒收割裂单关键词扫描"
    assert p["event_anchors"] > 0
    assert p["lifecycle_field_present"]


# ---------------------------------------------------------------------------
# S4 高阶演进（铁律 5）
# ---------------------------------------------------------------------------


def test_s4_derivatives_inflection_and_triple_gates(bench):
    r = bench.stage_4_cognition_lifecycle()
    p = r.promises
    assert p["inflection_fuse_armed"], "恶化加速度陡增必须提前熔断预警"
    assert p["immature_blocked"] == 2, "<3 天的维度申请 100% 被拒（门一）"
    assert p["quota_one_per_day_enforced"], "每日反思配额严格为 1（门三）"


# ---------------------------------------------------------------------------
# S5 老王案单跳隔离（铁律 2）
# ---------------------------------------------------------------------------


def test_s5_history_immutable_single_hop_isolation(bench):
    r = bench.stage_5_laowang_single_hop()
    p = r.promises
    assert p["history_fingerprint_stable"], "过去事实 SHA-256 绝对不可变"
    assert p["single_hop_only"], "级联严格单跳：只有直接下游被标 STALE"
    assert p["stale_marked"] == ["B"]
    assert p["llm_calls_constant"] == 1, "禁止 210 次 API 算力雪崩：常数级调用"
    assert p["annotated_overlay"] >= 1, "ANNOTATED 透镜必须看到挂载注记"


# ---------------------------------------------------------------------------
# S6 硬核建议（铁律 1）
# ---------------------------------------------------------------------------


def test_s6_actionable_advice_with_evidence_and_goaltask_decoupled(bench):
    r = bench.stage_6_actionable_advice()
    p = r.promises
    assert p["advisors"] == 3
    assert p["evidence_min"] >= 1, "结论无证据 ObjectRef 即拒收"
    assert p["mom_hit"], "2026 膝盖受凉必命中轻便膝盖理疗仪"
    assert p["fraud_block"] and p["fuse_checklist"]
    assert p["goal_revoked_without_rewrite"]


# ---------------------------------------------------------------------------
# S7 人设防线
# ---------------------------------------------------------------------------


def test_s7_persona_defense_lines_hold(bench):
    r = bench.stage_7_persona_defense()
    p = r.promises
    assert p["anti_sycophancy"], "面对荒谬陈述严禁虚伪附和"
    assert p["black_box_ui_clean"], "严禁 UI 问卷/置信度滑块/图谱后台"
    assert p["action_logged"] and p["communication_experience_recorded"]


# ---------------------------------------------------------------------------
# S8 驾驶舱 + 硬旁路 + 终极对话（铁律 1/3）
# ---------------------------------------------------------------------------


def test_s8_cockpit_hard_bypass_and_dialogue(bench):
    r = bench.stage_8_cockpit_dialogue()
    p = r.promises
    assert p["four_step_order"] == ["MIRROR", "RAPPORT", "POSTURE", "SCENE"], \
        "心智四步序不可颠倒"
    assert p["mirror_upheld"]
    assert p["summary_within_350"], "心智启动切片 ≤350 token"
    assert p["p0_status"] == "SAFETY_BYPASS_EXECUTED"
    assert p["p0_llm_calls"] == 0, "P0 大模型调用严格为 0"
    assert (p["p0_receipt_latency_ms"] or p["p0_latency_ms"]) <= P0_LATENCY_REDLINE_MS
    assert p["dormant_zero_token"], "未成熟任务后台休眠，零 Token 空转"
    assert 5 <= p["window_rounds"] <= 8
    assert p["window_tokens"] <= ROLLING_TOKEN_LIMIT
    assert p["dialogue_rounds"] == 10
    assert max(p["sentence_counts"]) <= DIALOGUE_SENTENCE_LIMIT, \
        "日常会话单轮 1~3 句铁律"


# ---------------------------------------------------------------------------
# 总汇编：性能台账
# ---------------------------------------------------------------------------


def test_full_pipeline_ledger_and_report_shape(tmp_path):
    # run_all 自带全套种子提交：独立实例，不与上面的共享考场争幂等键
    bench = TotalPipelineBench(str(tmp_path / "world-ledger.db"), scale=4000)
    report = bench.run_all()
    assert len(report["stages"]) == 8
    assert report["world_revision"] > 0
    assert report["peak_traced_bytes"] > 0
    for s in report["stages"]:
        assert s["wall_ms"] >= 0 and s["p95_ms"] >= s["p50_ms"]
    # 纯增量承诺：llm 调用总数为硬建议与审判记账的有限常数，不是雪崩
    assert report["llm_calls_total"] <= 16
