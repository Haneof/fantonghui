"""Tool A 自适应时序压缩算子测试：合成信号 + 真实 bench 2M IMU 流。"""

import hashlib
import math
import random

import pytest

from aios_core.simulation.adversarial_life_bench import AdversarialLifeGenerator
from aios_core.tools.adaptive_timeseries_compressor import (
    AdaptiveTimeseriesCompressor,
    TSCompressionResult,
    _checksum,
)


@pytest.fixture
def compressor():
    return AdaptiveTimeseriesCompressor()


def test_empty_input(compressor):
    r = compressor.compress([])
    assert r.sample_count == 0
    assert r.segments == ()
    assert r.compression_ratio == 0.0
    assert r.peak_error == 0.0


def test_invalid_params():
    with pytest.raises(ValueError):
        AdaptiveTimeseriesCompressor(dynamic_leaf=4)
    with pytest.raises(ValueError):
        AdaptiveTimeseriesCompressor(transient_threshold=0.0)
    with pytest.raises(ValueError):
        AdaptiveTimeseriesCompressor(context=-1)


def test_constant_signal_zero_error(compressor):
    samples = [1.0] * 100_000
    r = compressor.compress(samples)
    assert r.peak_error == 0.0
    assert all(sg.mode == "steady" for sg in r.segments)
    # 300 样本小叶 × 8 锚点 ≈ 37:1
    assert r.compression_ratio > 25
    # 段级统计与原始一致
    for sg in r.segments:
        assert sg.mean == pytest.approx(1.0)
        assert sg.variance == 0.0
        assert sg.peak == 1.0 and sg.minimum == 1.0
    # checksum 可复算（审计链：由存储的 kept 值复算，不依赖原始序列）
    for sg in r.segments:
        assert sg.checksum == _checksum(sg.kept)


def test_quasi_static_noise_bounded_error(compressor):
    rng = random.Random(42)
    samples = [1.0 + rng.gauss(0, 0.005) for _ in range(120_000)]
    r = compressor.compress(samples)
    # 准平稳段：锚点插值误差被噪声幅值封住（~4σ 界，确定性种子可复算）
    assert r.peak_error < 0.04
    # 300 样本小叶 × 8 锚点 ≈ 37:1
    assert r.compression_ratio > 25


def test_impact_transient_kept_exactly(compressor):
    rng = random.Random(7)
    n = 60_000
    samples = [1.0 + rng.gauss(0, 0.02) for _ in range(n)]
    fall = n // 2
    for k in range(18):
        samples[fall + k] = 1.0 + 5.2 * math.exp(-((k - 6) ** 2) / 12.0)
    r = compressor.compress(samples)
    transients = [sg for sg in r.segments if sg.mode == "transient"]
    assert len(transients) == 1
    sg = transients[0]
    # 峰值完整保留（含 context 边界）
    assert sg.peak == pytest.approx(6.2, abs=0.2)
    assert fall >= sg.start and fall + 18 <= sg.end
    # 瞬态段重建零误差
    recon = compressor.reconstruct(r, samples)
    for i in range(sg.start, sg.end):
        assert recon[i] == samples[i]


def test_step_signal_subdivided(compressor):
    # 两电平信号（均值差大、块方差超阈）→ 递归细分到叶子块
    samples = [1.0] * 40_000 + [3.0] * 40_000
    r = compressor.compress(samples)
    modes = [sg.mode for sg in r.segments]
    assert "steady" in modes
    # 边界块不应把 1.0 与 3.0 混进同一锚点段（峰值/最小值分得开）
    mixed = [sg for sg in r.segments if sg.mode == "steady" and sg.peak - sg.minimum > 0.5]
    assert not mixed or r.peak_error < 0.6


def test_real_bench_imu_stream():
    """真实对抗生命 bench 的 IMU 流（200k 样本）：压缩比/瞬态保峰/确定性。"""
    gen = AdversarialLifeGenerator(imu_sample_count=200_000)
    raw = gen.generate_raw_streams()
    samples = list(raw.imu_samples)
    compressor = AdaptiveTimeseriesCompressor()

    r1 = compressor.compress(samples)
    assert r1.sample_count == 200_000
    # 静坐叶 300 样本/8 锚点 ≈ 37:1，步行/震颤叶零误差全保留 → 总体 ≥3:1
    assert r1.compression_ratio >= 3
    # 跌倒冲击（6.2g）必须被瞬态段完整保留
    assert r1.transient_segment_count >= 1
    impact_segments = [sg for sg in r1.segments if sg.mode == "transient" and sg.peak > 5.0]
    assert impact_segments, "6.2g 跌倒冲击必须落入瞬态段"
    for sg in r1.segments:
        if sg.mode == "transient":
            assert sg.kept_count == sg.length  # 瞬态/动态段零误差全保留
    # 保真审计：重建误差被叶噪声地板（5σ）与局部振荡摆动封住（逐段可审计），
    # 而非信号幅度（步行 0.55g 振荡由动态门零误差全保留）
    assert r1.peak_error < 0.2
    # 确定性：两次压缩逐段校验和一致
    r2 = compressor.compress(samples)
    assert [sg.checksum for sg in r1.segments] == [sg.checksum for sg in r2.segments]
    # 总校验和 = 各段校验和的链接哈希（可由压缩结构独立复算）
    h = hashlib.sha256()
    for sg in r1.segments:
        h.update(str(sg.checksum).encode("utf-8"))
    assert r1.total_checksum == h.hexdigest()
    # 产物体量：段数远小于样本数（索引化，非原始存储）
    assert len(r1.segments) < 10_000


def test_result_immutability(compressor):
    samples = [1.0 + i * 0.0001 for i in range(20_000)]
    r = compressor.compress(samples)
    with pytest.raises(Exception):
        r.sample_count = 1  # type: ignore[misc]
    assert isinstance(r, TSCompressionResult)
