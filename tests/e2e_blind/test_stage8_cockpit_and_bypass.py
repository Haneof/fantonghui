"""阶段八盲测：驾驶舱全景调度 / P0 硬旁路 / 终极对话。"""

from __future__ import annotations

from aios_core.cockpit.mind_order_manifest import MIND_ORDER, MindOrderSession
from aios_core.simulation.blind_bench_harness import BenchRunResult


def test_manifest_is_a_single_load_minimal_dashboard(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("manifest_source_reads") == 1
    assert stage.fact("manifest_loader_loads") == 1
    assert stage.fact("manifest_questions_to_user") == 0
    assert stage.fact("manifest_total_tokens") <= stage.fact("manifest_budget")
    assert stage.fact("manifest_section_order") == "self,bond,stance,scene"


def test_mind_order_is_immutable(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("mind_order_reorder_blocked") is True
    assert stage.fact("mind_order_sealed") == "self,bond,stance,scene"
    assert MindOrderSession.order_is_legal(MIND_ORDER) is True
    assert MindOrderSession.order_is_legal((MIND_ORDER[3], *MIND_ORDER[:3])) is False


def test_p0_hardware_bypass_preempts_the_world_model(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("p0_first_action") == "hardware_pulse"
    assert stage.fact("p0_bypassed_llm") is True
    assert stage.fact("p0_llm_calls") == 0
    assert stage.fact("p0_max_ms") <= 50.0
    assert stage.fact("p0_p99_ms") <= 50.0
    assert stage.fact("p0_audit_receipts") == 50


def test_dormant_conditional_tasks_burn_zero_tokens(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("dormant_tasks") == 200
    assert stage.fact("dormant_tokens_in_board") == 0
    assert stage.fact("dormant_tokens_if_naive") > 0
    assert stage.fact("dormant_frozen_out") == 200
    assert stage.fact("scheduler_llm_calls") == 0
    assert stage.fact("scheduler_autonomous_wakes") == 0
    assert stage.fact("evaluator_idle_evaluated") == 0
    assert stage.fact("evaluator_signal_evaluated") < stage.fact("evaluator_registered") // 4


def test_final_ten_round_daily_conversation(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("conversation_rounds") == 10
    counts = [int(item) for item in stage.fact("conversation_sentence_counts").split(",")]
    assert len(counts) == 10
    assert min(counts) >= 1
    assert max(counts) <= 3
    assert stage.fact("conversation_max_round_tokens") <= stage.fact("conversation_single_shot_budget")
    assert stage.fact("conversation_preach_hits") == 0


def test_conversation_window_is_lossless_and_fast(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("conversation_active_window") <= stage.fact("conversation_window_size")
    assert stage.fact("conversation_lossless_rounds") == 20
    assert stage.fact("assembly_p95_ms") <= 15.0
