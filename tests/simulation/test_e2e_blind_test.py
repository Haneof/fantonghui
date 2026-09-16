"""8 阶段全流程盲测执行器测试（小 IMU 规模全链路，~1 分钟）。"""

import os
import tempfile

import pytest

from aios_core.simulation.e2e_blind_test import (
    E2EBlindTest,
    BlindTestReport,
    run_e2e_blind_test,
)


@pytest.fixture(scope="module")
def full_run():
    """一次完整的 8 阶段盲测（IMU 100k，全对象量级 ~19.5k）。"""
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    report = run_e2e_blind_test(db, imu_sample_count=100_000)
    yield report, db
    os.remove(db)


def test_all_eight_stages_pass(full_run):
    report, _ = full_run
    assert isinstance(report, BlindTestReport)
    assert len(report.stages) == 8
    for s in report.stages:
        assert s.passed, f"阶段 {s.stage} 失败: {s.error}"
        assert s.error is None
    assert report.all_passed


def test_five_iron_rules_100_percent(full_run):
    report, _ = full_run
    assertions = report.iron_rule_assertions
    assert len(assertions) >= 15
    for a in assertions:
        assert a.passed, f"铁律断言未通过: {a.rule} {a.description}"
    assert report.iron_rules_100_percent


def test_llm_strictly_zero(full_run):
    report, _ = full_run
    assert report.llm_calls == 0
    assert report.stages[7].metrics["p0_llm_calls"] == 0
    assert report.stages[4].metrics["llm_calls"] == 0


def test_stage1_throughput_and_immutability(full_run):
    report, _ = full_run
    s1 = report.stages[0]
    assert s1.metrics["raw_records"] > 200_000
    assert s1.metrics["raw_imu_samples"] == 100_000
    assert s1.metrics["core_evidence"] > 6_000
    assert s1.metrics["commit_batches"] >= 39
    assert report.world_revision > 50
    assert report.commit_latency_p50_ms > 0


def test_stage2_pyramid_drilldown_zero_break(full_run):
    report, _ = full_run
    s2 = report.stages[1]
    assert s2.metrics["evidence_break_rate"] == 0.0
    assert s2.metrics["drill_year_to_day_ms"] < 45.0
    assert s2.metrics["summaries"] == 5
    assert s2.metrics["vault_events"] > 900


def test_stage3_cooccurrence_and_lifecycle(full_run):
    report, _ = full_run
    s3 = report.stages[2]
    assert s3.metrics["core_saga_recalled"] == "4/4"
    assert s3.metrics["co_occurrence_pair"] == ["obs_e2e_partner_fight"]
    assert s3.metrics["event_revisions"] == 3
    assert s3.metrics["aligned_sources"] == 3


def test_stage4_derivatives_and_gates(full_run):
    report, _ = full_run
    s4 = report.stages[3]
    assert s4.metrics["curve_points"] == 101
    assert s4.metrics["trend"] in ("rising", "inflection")
    assert s4.metrics["gate_rejected"] == 2
    assert s4.metrics["review"] == "promoted"
    assert s4.metrics["level_shift"] >= 8


def test_stage5_dual_lens_consistency(full_run):
    report, _ = full_run
    s5 = report.stages[4]
    assert s5.metrics["as_known_facts"] == 3
    assert s5.metrics["annotated_facts"] == 3
    assert s5.metrics["as_known_annotations"] == 0
    assert s5.metrics["annotated_annotations"] == 1
    assert s5.metrics["tamper_blocked"] is True
    assert s5.metrics["query_p99_ms"] < 50.0


def test_stage6_advice_and_retraction(full_run):
    report, _ = full_run
    s6 = report.stages[5]
    assert s6.metrics["evidence_pointers"] == 4
    assert s6.metrics["advice_sentences"] <= 3
    assert s6.metrics["goal_revisions"] == 2
    assert s6.metrics["task_revisions"] == 2


def test_stage7_style_evolution(full_run):
    report, _ = full_run
    s7 = report.stages[6]
    assert s7.metrics["effective_style"] == "老友"
    assert s7.metrics["avoidance_list"] == ["损友"]
    assert len(s7.metrics["sycophancy_intercepts"]) >= 1


def test_stage8_p0_dormant_and_rounds(full_run):
    report, _ = full_run
    s8 = report.stages[7]
    m = s8.metrics
    assert m["p0_hardware_ms"] <= 50.0
    assert m["p0_e2e_ms"] <= 50.0
    assert m["dormant_token_cost"] == 0
    assert all(1 <= n <= 3 for n in m["sentences_per_round"])
    assert m["rounds"] == 10
    assert m["cockpit_tokens_max"] <= 1500
    assert all(m["four_steps"].values())
    # 交付物 3：两工具实测 + 生命周期
    assert m["tool_a_ratio"] >= 3
    assert m["tool_a_peak_error"] < 0.5
    assert m["tool_b_identical_4kw"] is True
    assert m["tool_b_identical_pair"] is True
    assert m["tool_b_pair_hit"] == ["obs_e2e_partner_fight"]


def test_report_markdown_sections(full_run):
    report, _ = full_run
    md = report.render_markdown()
    for section in (
        "# AIOS 全流程海量盲测与极限压测报告",
        "## 一、8 阶段执行明细",
        "## 二、五大铁律 100% 捍卫断言账目",
        "## 三、全生命周期心智瓶颈与缺陷诊断（交付物 2）",
        "## 四、新机制发明与新工具提议（交付物 3）",
        "adaptive_timeseries_compressor",
        "cooccurrence_recall_accelerator",
    ):
        assert section in md
    assert report.bottlenecks["most_token_stage"].startswith("阶段")
    assert report.bottlenecks["most_lossy_detail"].startswith("1,024,000")


def test_world_contains_tool_proposals(full_run):
    """ToolProposal 落世界：两个工具提议均为 EXECUTED 状态的一等对象。"""
    from aios_core.storage.sqlite_store import SQLiteWorldStore

    report, db = full_run
    store = SQLiteWorldStore(db)
    for oid in (
        "tool_proposal_adaptive_timeseries_compressor",
        "tool_proposal_cooccurrence_recall_accelerator",
    ):
        payload = store.get_payload(oid)
        assert payload["object_type"] == "tool_proposal"
        assert payload["created_by"] == "e2e_blind_test_agent11"
    assert isinstance(report, BlindTestReport)


def test_executor_constructible():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        bt = E2EBlindTest(db, imu_sample_count=10_000)
        assert bt.store.current_world_revision() == 0
        assert bt.llm_calls == 0
    finally:
        os.remove(db)
