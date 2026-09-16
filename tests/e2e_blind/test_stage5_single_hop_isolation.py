"""阶段五盲测：老王案单跳隔离防雪崩（铁律 2 的物理证据）。"""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import BenchRunResult, truth_table_digest


def test_historical_facts_are_byte_level_immutable(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S5")
    assert stage.fact("truth_digest_unchanged") is True
    assert stage.fact("target_payload_bytes_unchanged") is True
    assert stage.fact("observations_after") == stage.fact("observations_before")
    assert stage.fact("target_tombstoned") is False
    before = stage.fact("truth_tables_before")
    after = stage.fact("truth_tables_after")
    assert before == after
    assert all(row_count > 0 for row_count in after.values())


def test_new_cognition_lands_as_today_overlay(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S5")
    assert stage.fact("annotation_is_pinned_to_now") is True
    assert stage.fact("annotation_id").startswith("rip_")


def test_single_hop_isolation_blocks_the_avalanche(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S5")
    assert stage.fact("naive_cascade_recompute_calls") == 210
    assert stage.fact("isolation_llm_calls") == 0
    assert stage.fact("isolation_recompute_triggered") == 0
    assert stage.fact("cascade_suppressed") is True
    assert stage.fact("traversal_depth_reached") <= 1
    assert stage.fact("stale_is_single_hop") is True
    assert stage.fact("multi_hop_untouched") is True


def test_dual_lens_consistency_and_base_hash(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S5")
    assert stage.fact("dual_lens_base_unchanged") is True
    assert stage.fact("dual_lens_consistency") is True
    assert stage.fact("dual_lens_fact_set_stable") is True
    assert stage.fact("dual_lens_overlay_visible") is True
    assert stage.fact("as_known_hits") == stage.fact("annotated_hits")
    assert stage.fact("dual_lens_saved_ratio") >= 0.5


def test_truth_digest_helper_is_deterministic(bench_run: BenchRunResult) -> None:
    digest = truth_table_digest(bench_run.db_path)
    assert digest == truth_table_digest(bench_run.db_path)
    assert digest["object_revisions"]["rows"] >= bench_run.world_revision
