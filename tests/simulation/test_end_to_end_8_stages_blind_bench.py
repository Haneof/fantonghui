"""AIOS 3.0 全功能 8 大阶段端到端海量盲测套件.

落实老大五大最高铁律与首席架构总工沙箱门禁要求：
- 阶段一：原始数据百万级摄入、清洗与边缘提纯测试 (铁律4)
- 阶段二：时间金字塔多尺度逐级结晶与无损穿透测试 (0.0%断裂率)
- 阶段三：多维时空共振、新事件合成与生命周期测试
- 阶段四：高阶认知演进、维度曲线与新维度衍生门槛测试 (铁律5)
- 阶段五：历史认知回溯与老王案单跳隔离防雪崩测试 (铁律2)
- 阶段六：共生决策推演与主动帮助测试 (铁律1)
- 阶段七：AI自身世界维护、沟通策略博弈与人设防线测试
- 阶段八：驾驶舱全景调度、硬旁路与终极对话实操测试 (铁律3)
"""

from __future__ import annotations

import pytest

from aios_core.simulation.adversarial_life_bench import (
    AdversarialLifeStreamGenerator,
    EndToEnd8StagesBlindBenchmarkRunner,
)


@pytest.fixture(scope="module")
def benchmark_results():
    """执行 100,000 条高熵样本端到端全流程盲测。"""
    runner = EndToEnd8StagesBlindBenchmarkRunner(target_stream_samples=100_000, seed=42)
    report = runner.run_full_pipeline()
    return report


def test_end_to_end_8_stages_full_pass(benchmark_results):
    report = benchmark_results

    # 1. 全部 8 个阶段必须 100% 通过
    assert report.all_passed is True
    assert len(report.stages) == 8
    assert all(s.passed for s in report.stages)

    # 2. 五大铁律必须 100% 捍卫
    assert report.iron_rules_verdicts["IronRule1_OutputQuality"] is True
    assert report.iron_rules_verdicts["IronRule2_HistoryImmutable"] is True
    assert report.iron_rules_verdicts["IronRule3_P0SafetyHardBypass"] is True
    assert report.iron_rules_verdicts["IronRule4_LLMAutonomousPrune"] is True
    assert report.iron_rules_verdicts["IronRule5_TripleThresholdGuard"] is True

    # 3. 内存与执行效率受控
    assert report.memory_peak_rss_mb <= 256.0
    assert report.total_elapsed_sec <= 5.0


def test_stage1_million_scale_purification_and_iron_rule4(benchmark_results):
    s1 = benchmark_results.stages[0]
    assert s1.stage_id == 1
    assert s1.passed is True
    assert s1.items_processed >= 100_000
    assert s1.throughput_items_per_sec > 50_000


def test_stage2_time_pyramid_lossless_drilling(benchmark_results):
    s2 = benchmark_results.stages[1]
    assert s2.stage_id == 2
    assert s2.passed is True
    assert s2.p95_latency_ms <= 45.0


def test_stage3_spatiotemporal_resonance_and_event_lifecycle(benchmark_results):
    s3 = benchmark_results.stages[2]
    assert s3.stage_id == 3
    assert s3.passed is True


def test_stage4_cognitive_derivatives_and_iron_rule5(benchmark_results):
    s4 = benchmark_results.stages[3]
    assert s4.stage_id == 4
    assert s4.passed is True


def test_stage5_history_immutability_and_single_hop_isolation(benchmark_results):
    s5 = benchmark_results.stages[4]
    assert s5.stage_id == 5
    assert s5.passed is True
    assert s5.p95_latency_ms <= 5.0


def test_stage6_symbiotic_advice_and_goal_task_decoupling(benchmark_results):
    s6 = benchmark_results.stages[5]
    assert s6.stage_id == 6
    assert s6.passed is True


def test_stage7_ai_self_world_and_persona_defense(benchmark_results):
    s7 = benchmark_results.stages[6]
    assert s7.stage_id == 7
    assert s7.passed is True


def test_stage8_cockpit_manifest_p0_bypass_and_dialogue_brevity(benchmark_results):
    s8 = benchmark_results.stages[7]
    assert s8.stage_id == 8
    assert s8.passed is True
    assert s8.p95_latency_ms <= 10.0


def test_million_scale_stream_benchmark():
    """百万级（1,000,000）海量样本流极限压测。"""
    runner = EndToEnd8StagesBlindBenchmarkRunner(target_stream_samples=1_000_000, seed=123)
    report = runner.run_full_pipeline()
    assert report.all_passed is True
    assert report.total_samples == 1_000_000
    assert report.total_elapsed_sec <= 10.0
    assert report.stages[0].items_processed == 1_000_000
