"""自适应时序压缩算子单元测试（对抗生成器驱动，拒绝写死样例）。"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from aios_core.tools.adaptive_temporal_compactor import (
    AdaptiveTemporalCompactor,
    AnomalyKind,
    ChannelKind,
    SensorSample,
)

UTC = timezone.utc
T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def _noisy_calm_hr_stream(rng: random.Random, seconds: int):
    """平稳心率流：昼夜慢漂 + 高斯噪声。"""
    for sec in range(seconds):
        value = 64 + 6 * math.sin(sec / 4000.0) + rng.gauss(0, 1.6)
        yield SensorSample(t=T0 + timedelta(seconds=sec), channel=ChannelKind.HEART_RATE, value=value)


def test_calm_stream_compresses_to_interval_means():
    rng = random.Random(7)
    compactor = AdaptiveTemporalCompactor()
    result = compactor.compact(_noisy_calm_hr_stream(rng, 3 * 3600))

    assert result.samples_in == 3 * 3600
    assert result.raw_rows_persisted == 0  # 宪法：原始采样零落库
    assert len(result.intervals) >= 30  # 5 分钟一段
    assert result.anomalies == []  # 平稳流不得误报突变
    total_samples_covered = sum(iv.sample_count for iv in result.intervals)
    assert total_samples_covered == result.samples_in  # 无损覆盖
    for iv in result.intervals:
        assert iv.min_value <= iv.mean_value <= iv.max_value
    assert result.filtered_ratio >= 0.99


def test_injected_surge_zero_miss_and_no_rebound_double_fire():
    rng = random.Random(11)
    samples = list(_noisy_calm_hr_stream(rng, 3600))
    injected = []
    for surge_sec in (900, 2400):
        spike = SensorSample(
            t=T0 + timedelta(seconds=surge_sec),
            channel=ChannelKind.HEART_RATE,
            value=105.0 + rng.random() * 6,  # 远高于 25bpm 突变阈值
        )
        samples[surge_sec] = spike
        injected.append(surge_sec)
        # 紧跟 30 秒高位平台：不应二次误报（不应期），回落也不误报（基线保持）
        for k in range(1, 31):
            samples[surge_sec + k] = SensorSample(
                t=T0 + timedelta(seconds=surge_sec + k),
                channel=ChannelKind.HEART_RATE,
                value=103.0 + rng.gauss(0, 1.2),
            )

    result = AdaptiveTemporalCompactor().compact(iter(samples))
    surges = [a for a in result.anomalies if a.kind == AnomalyKind.RATE_SURGE]
    assert len(surges) == len(injected)  # 零漏检且不重复触发
    detected_secs = {int((a.t_peak - T0).total_seconds()) for a in surges}
    assert detected_secs == set(injected)


def test_impact_waveform_zero_miss_with_digest():
    rng = random.Random(13)
    samples = []
    impact_secs = (500, 2600, 6100)
    for sec in range(2 * 3600):
        value = 1.0 + abs(rng.gauss(0, 0.05))  # 平静佩戴
        if sec in impact_secs:
            value = 4.6 + rng.random()  # 跌倒/磕碰冲击
        samples.append(
            SensorSample(t=T0 + timedelta(seconds=sec), channel=ChannelKind.IMU_MAGNITUDE, value=value)
        )

    result = AdaptiveTemporalCompactor().compact(iter(samples))
    impacts = [a for a in result.anomalies if a.kind == AnomalyKind.IMPACT]
    assert len(impacts) == len(impact_secs)
    for impact in impacts:
        assert impact.delta > 3.0
        assert len(impact.digest) >= 1  # 波形摘要可供回放
        assert impact.to_observation_payload()["modality"] == "waveform_digest"


def test_regime_shift_marked_when_activity_level_jumps():
    rng = random.Random(17)
    samples = []
    for sec in range(3600):
        # 前半小时久坐（1.0g），后半小时奔跑（2.1g）：运动相变
        value = (1.0 if sec < 1800 else 2.1) + abs(rng.gauss(0, 0.04))
        samples.append(
            SensorSample(t=T0 + timedelta(seconds=sec), channel=ChannelKind.IMU_MAGNITUDE, value=value)
        )

    result = AdaptiveTemporalCompactor(calm_window=timedelta(minutes=5)).compact(iter(samples))
    shifts = [a for a in result.anomalies if a.kind == AnomalyKind.REGIME_SHIFT]
    assert shifts, "久坐->奔跑的相态切换必须被标记"
    assert shifts[0].delta > 0.8
