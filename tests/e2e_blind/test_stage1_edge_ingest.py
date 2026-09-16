"""阶段一盲测：百万级摄入 / 清洗 / 边缘提纯（铁律 4 的物理证据）。"""

from __future__ import annotations

from aios_core.simulation.blind_bench_harness import (
    BenchRunResult,
    raw_stream_totals,
)


def test_stream_matches_the_independent_generator_quota(bench_run: BenchRunResult) -> None:
    """实产条数必须与**独立发生器声明的配额**逐通道相等（禁止手搓数据）。"""

    stage = bench_run.stage("S1")
    quota = raw_stream_totals(scale=bench_run.scale, seed=bench_run.seed)
    assert stage.fact("raw_samples_generated") == quota["total"]
    assert stage.fact("raw_samples_ingested") == quota["total"]
    assert stage.fact("raw_imu") == quota["imu"]
    assert stage.fact("raw_heart") == quota["heart"]
    assert stage.fact("raw_vision") == quota["vision"]
    assert stage.fact("raw_audio") == quota["audio"]
    assert stage.fact("raw_text") == quota["text"]
    if bench_run.scale >= 1.0:
        assert quota["total"] >= 1_000_000
        assert stage.fact("throughput_samples_per_second") > 100_000


def test_no_high_frequency_raw_write_into_the_world(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("raw_imu_rows_persisted") == 0
    assert stage.fact("min_imu_window_samples") >= 50
    assert stage.fact("imu_impact_windows_preserving_raw") == stage.fact(
        "imu_impact_observations"
    )


def test_heart_steady_period_is_averaged_and_anomalies_are_separate(
    bench_run: BenchRunResult,
) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("heart_summary_observations") > 0
    assert stage.fact("heart_anomaly_observations") > 0
    assert stage.fact("compression_ratio") > 0.99


def test_vision_keeps_caption_only(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("caption_observations") > 0
    assert stage.fact("raw_image_bytes_retained") == 0
    assert stage.fact("raw_image_bytes_sunk") > 0


def test_audio_transcript_and_voiceprint_ttl(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("transcript_observations") > 0
    assert stage.fact("voiceprints_registered") >= 4
    assert stage.fact("voiceprints_tombstoned_by_ttl") >= 1
    assert stage.fact("voiceprint_bound_survivors") >= 3


def test_iron_rule_4_noise_deleted_and_evidence_kept(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("core_texts_total") == 25
    assert stage.fact("core_texts_retained") == stage.fact("core_texts_total")
    assert stage.fact("core_texts_retained_after_review") == stage.fact("core_texts_total")
    assert stage.fact("noise_visible_after_review") == 0
    assert stage.fact("purge_ledger_chain_ok") is True
    assert stage.fact("purge_ledger_tombstones") >= 1


def test_edge_compressor_error_bound_is_verified(bench_run: BenchRunResult) -> None:
    stage = bench_run.stage("S1")
    assert stage.fact("compressor_steady_error") <= 2.0
    assert stage.fact("compressor_steady_segments") <= 5
