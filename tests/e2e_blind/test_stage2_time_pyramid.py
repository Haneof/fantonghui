"""阶段二盲测：时间金字塔多尺度结晶 + 无损穿透（证据链断链率 0.0%）。"""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import BenchRunResult


def test_pyramid_is_additive_not_destructive(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S2")
    assert stage.fact("year_summary_scale") == "YEAR"
    assert stage.fact("year_evidence_ids") > 0
    assert stage.fact("events_vaulted") >= stage.fact("year_evidence_ids")
    assert stage.fact("store_observation_count_after") >= stage.fact("events_vaulted")


def test_evidence_chain_break_rate_is_zero(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S2")
    assert stage.fact("evidence_chain_break_rate") == 0.0
    assert stage.fact("evidence_break_year_to_month") == 0
    assert stage.fact("evidence_break_year_to_week") == 0
    assert stage.fact("evidence_break_year_to_day") == 0


def test_three_year_old_annual_summary_drills_to_raw_quote(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S2")
    assert stage.fact("year_summary_years") == 2024
    assert stage.fact("raw_quote_recovered") is True
    assert stage.fact("day_slices_recovered") >= stage.fact("year_evidence_ids")


def test_summaries_are_new_layers_and_conflicts_are_refused(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S2")
    assert stage.fact("month_summaries") > 0
    assert stage.fact("week_summaries") >= stage.fact("month_summaries")
    assert stage.fact("evidence_conflict_rejected") is True
    assert stage.fact("vault_size") == stage.fact("year_evidence_ids")


def test_drill_latency_within_budget(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S2")
    assert stage.fact("drill_p95_ms") <= 45.0
    assert stage.fact("drill_max_ms") <= 45.0
