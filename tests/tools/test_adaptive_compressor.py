"""自适应时序压缩算子单测"""
from datetime import datetime, timedelta, timezone
import random

from aios_core.tools.adaptive_compressor import AdaptiveTimeSeriesCompressor

UTC = timezone.utc


def test_hr_flat_compression_ratio():
    comp = AdaptiveTimeSeriesCompressor(hr_flat_window_seconds=7200)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # 2h 平稳：每分钟1点，平稳68bpm
    samples = [(base + timedelta(minutes=i), 68.0 + random.Random(42).gauss(0, 0.8)) for i in range(240)]
    windows, stats = comp.compress_heart_rate_stream(samples)
    assert stats.compression_ratio >= 5
    assert stats.p95_latency_ms < 5
    assert len(windows) < len(samples)


def test_hr_spike_preserved():
    comp = AdaptiveTimeSeriesCompressor(hr_spike_threshold_bpm=15.0)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    samples = [(base + timedelta(minutes=i), 68.0) for i in range(20)]
    samples.append((base + timedelta(minutes=20), 110.0))  # spike
    samples.extend([(base + timedelta(minutes=i), 68.0) for i in range(21, 40)])
    windows, _ = comp.compress_heart_rate_stream(samples)
    anomalies = [w for w in windows if w.is_anomaly]
    assert len(anomalies) >= 1


def test_imu_stationary_vs_impact():
    comp = AdaptiveTimeSeriesCompressor()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    samples = [(base + timedelta(milliseconds=i*20), 0.12) for i in range(500)]  # stationary 10s
    samples.extend([(base + timedelta(milliseconds=500*20 + i*20), 4.0) for i in range(5)])  # impact
    events, stats = comp.compress_imu_stream(samples)
    assert any(e.is_impact for e in events)
    assert stats.compression_ratio > 10
    # macro state must be one of 4
    assert all(e.macro_state in ("静止", "平缓走动", "剧烈跑动", "疑似摔倒撞击") for e in events)


def test_imu_50hz_not_direct_db():
    comp = AdaptiveTimeSeriesCompressor()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # 50Hz 5秒 = 250 点 → 应压成 1 窗口
    samples = [(base + timedelta(milliseconds=i*20), 0.15) for i in range(250)]
    events, _ = comp.compress_imu_stream(samples)
    assert len(events) == 1
    assert events[0].sample_count == 250


def test_compressor_reset():
    comp = AdaptiveTimeSeriesCompressor()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    samples = [(base + timedelta(minutes=i), 70.0) for i in range(10)]
    comp.compress_heart_rate_stream(samples)
    comp.reset_stats()
    assert comp.overall_stats().raw_points == 0
