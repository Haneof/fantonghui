"""ToolProposal TLP-C01 自适应时序压缩算子验收测试。

宪法第 33 条：IMU 50Hz 高频时序禁止直写、心率平稳期仅存时段均值、突变波形独立成
Observation。本算子把"自适应漏斗"落地为纯代码，测试只验证可复算的机械证据。
"""

from __future__ import annotations

from datetime import timedelta

from aios_core.contracts.time import utc_now
from aios_core.tools.adaptive_temporal_compactor import (
    HeartRateCompactor,
    ImuMagnitudeCompactor,
    Spo2Compactor,
)


def test_steady_hr_compresses_to_single_window_mean() -> None:
    compactor = HeartRateCompactor()
    t0 = utc_now()
    produced = []
    for i in range(20):
        spec = compactor.feed(70.0, now=t0 + timedelta(seconds=i * 1))
        if spec is not None:
            produced.extend(spec.chunks)
    # 平稳流不产生任何突变快照；只统计聚合值
    assert produced == []


def test_steady_window_flushes_mean_not_raw_sequence() -> None:
    compactor = HeartRateCompactor()
    t0 = utc_now()
    chunks = []
    for i in range(60):
        spec = compactor.feed(72.0, now=t0 + timedelta(seconds=i * 720))
        if spec is not None:
            chunks.extend(spec.chunks)
    # 平稳段分窗封段：全部是时段均值，绝不混入任何 50Hz 原始序列
    assert chunks
    assert all(c.kind == "steady_average" for c in chunks)
    # 已封段样本数 + 仍开窗未封段的样本数 == 总样本数（一条不丢）
    assert sum(c.sample_count for c in chunks) + compactor.pending_samples == 60
    for c in chunks:
        assert abs(c.avg - 72.0) < 0.1
        payload = c.as_payload()
        assert "raw" not in payload
        assert "max" in payload and "min" in payload


def test_abrupt_spike_becomes_standalone_observation() -> None:
    compactor = HeartRateCompactor()
    t0 = utc_now()
    for i in range(10):
        compactor.feed(70.0, now=t0 + timedelta(seconds=i * 1))
    # 突变：>15 BPM 跳变，独立成 Observation（不再被均值抹平）
    spec = compactor.feed(112.0, now=t0 + timedelta(seconds=20))
    assert spec is not None
    kinds = [c.kind for c in spec.chunks]
    assert "abrupt_spike" in kinds
    spike = next(c for c in spec.chunks if c.kind == "abrupt_spike")
    assert spike.sample_count == 1
    assert spike.avg == 112.0


def test_compactor_is_zero_llm_and_derivative_free() -> None:
    compactor = HeartRateCompactor()
    # 算子只做机械分带 + 均值，绝无模型调用、绝无导数计算
    assert compactor.llm_calls == 0
    assert compactor.derivative_free is True
    # 喂满一路数据后依然为零
    t0 = utc_now()
    for i in range(30):
        compactor.feed(70.0 + (i % 3), now=t0 + timedelta(seconds=i * 10))
    assert compactor.llm_calls == 0


def test_imu_magnitude_channel_extracts_macro_state() -> None:
    compactor = ImuMagnitudeCompactor()
    t0 = utc_now()
    spec = None
    for i in range(10):
        spec = compactor.feed(0.15 + (i % 4) * 0.01, now=t0 + timedelta(seconds=i * 2))
    # IMU 宏观状态：只产聚合，不产 1 条/样本的 50Hz 原始直写
    assert compactor.raw_samples_dropped_total >= 10
    assert spec is None or all(c.kind in ("steady_average", "abrupt_spike") for c in spec.chunks)


def test_spo2_channel_low_saturation_is_detected_as_spike() -> None:
    compactor = Spo2Compactor()
    t0 = utc_now()
    for i in range(6):
        compactor.feed(98.0, now=t0 + timedelta(seconds=i * 1))
    spec = compactor.feed(86.0, now=t0 + timedelta(seconds=10))
    assert spec is not None
    assert any(c.kind == "abrupt_spike" for c in spec.chunks)
