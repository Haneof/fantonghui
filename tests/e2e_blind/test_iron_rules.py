"""五大铁律的盲测终审：每条铁律都必须有机器可复核的实测证据。"""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import BenchRunResult, raw_stream_totals


def test_summary_of_the_run(bench_run: BenchRunResult) -> None:
    assert bench_run.scale == 1.0 or bench_run.stage("S1").fact("raw_samples_generated") >= 100_000
    assert bench_run.world_revision > 0
    assert len(bench_run.stages) == 8
    assert bench_run.total_seconds > 0
    assert [stage.stage_id for stage in bench_run.stages] == [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8",
    ]


def test_iron_rule_1_output_quality_first(bench_run: BenchRunResult) -> None:
    advice = bench_run.stage("S6")
    conversation = bench_run.stage("S8")
    assert advice.fact("advice_sentence_count") <= 3
    counts = [int(item) for item in conversation.fact("conversation_sentence_counts").split(",")]
    assert set(counts) <= {1, 2, 3}
    assert conversation.fact("conversation_preach_hits") == 0
    assert advice.fact("advice_grounding_verified") is True


def test_iron_rule_2_history_never_rewritten(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S5")
    assert stage.fact("truth_digest_unchanged") is True
    assert stage.fact("target_payload_bytes_unchanged") is True
    assert stage.fact("isolation_llm_calls") == 0
    assert stage.fact("traversal_depth_reached") <= 1


def test_iron_rule_3_p0_pierces_straight_to_hardware(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S8")
    assert stage.fact("p0_first_action") == "hardware_pulse"
    assert stage.fact("p0_llm_calls") >= 1
    assert stage.fact("p0_p95_ms") <= 50.0


def test_iron_rule_4_noise_purged_evidence_kept(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("noise_visible_after_review") == 0
    assert stage.fact("core_texts_retained_after_review") == stage.fact("core_texts_total")
    assert stage.fact("raw_image_bytes_retained") == 0
    assert stage.fact("raw_imu_rows_persisted") == 0


def test_iron_rule_5_dimension_explosion_is_gated(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S4")
    assert stage.fact("immature_pattern_rejected") is True
    assert stage.fact("same_day_second_reflection_blocked") is True
    assert stage.fact("trial_weak_prediction_outcome") == "expired"
    assert stage.fact("trial_patchy_outcome") == "expired"


def test_raw_stream_budget_matches_the_million_scale_claim() -> None:
    totals = raw_stream_totals(scale=1.0)
    assert totals["total"] == 1_131_330
    assert totals["imu"] == 1_050_000
    assert totals["total"] > 1_000_000


# ---------------------------------------------------------------------------
# 由外部仪器复算的五条铁律判据（与上面的逐字段断言互为独立验证）
# ---------------------------------------------------------------------------


def test_iron_rule_assertions_from_the_instrument(bench_session) -> None:
    assertions = bench_session.iron_rules
    assert len(assertions) == 5
    for assertion in assertions:
        assert assertion.passed is True, assertion.render()
        assert assertion.checks


def test_token_ledger_traces_every_stage(bench_session) -> None:
    ledger = {row.stage_id: row for row in bench_session.diagnosis["token_ledger"]}
    assert set(ledger) == {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
    # 机械阶段恒为 0：没有任何字段能烧 Token
    for stage_id in ("S1", "S4", "S5"):
        assert ledger[stage_id].tokens == 0
    assert bench_session.diagnosis["token_hotspot"].stage_id == "S8"
    assert bench_session.diagnosis["token_total"] > 0


def test_io_probe_attributes_sql_by_stage(bench_session) -> None:
    attribution = bench_session.attribution
    assert attribution.overall
    assert attribution.hottest().rows_scanned > 0
    assert attribution.per_stage
    stage, rows = attribution.heaviest_stage()
    assert stage.startswith("S")
    assert rows > 0


def test_abstraction_fidelity_is_ranked_and_bounded(bench_session) -> None:
    rows = bench_session.diagnosis["abstraction_fidelity"]
    assert len(rows) == 4
    for row in rows:
        assert 0.0 <= float(row["distortion"]) <= 1.0
        assert row["basis"]
        assert row["compensation"]
        assert row["recoverable"]
    assert bench_session.diagnosis["worst_abstraction"]["abstraction"]


def test_defect_catalog_only_contains_measured_hits(bench_session) -> None:
    defects = bench_session.diagnosis["defects"]
    assert defects
    for defect in defects:
        assert defect["measured"]
        assert defect["mechanism"]
        assert defect["fix"]
