"""自适应时序压缩算子（AdaptiveTemporalCompactor）—— 海量盲测新工具发明 #1。

宪法第十章第三十三条（边缘轻量化摄入）的工程落地件：

- 50Hz/100Hz 的 IMU 与 1Hz 心率原始波形**严禁直写数据库**；
- 平稳期仅产出"时段均值观测"（一条 Observation 顶替上千个原始采样）；
- 剧烈突变（心率骤升骤降、跌倒冲击、运动相态切换）独立成波形观测，
  携带下采样波形摘要（digest），供驾驶舱与因果层按需回放；
- 全程单遍流式处理（O(1) 驻留内存），原始样本只在算子内过路，绝不落库。

该算子由 MT-001 海量盲测驱动发明：上万条混杂波形（伪造噪声、基线漂移）
必须被 95% 以上压缩过滤，而真实运动相变与冲击波形必须零漏检。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class ChannelKind(StrEnum):
    HEART_RATE = "heart_rate"
    IMU_MAGNITUDE = "imu_magnitude"


class AnomalyKind(StrEnum):
    RATE_SURGE = "rate_surge"          # 心率突变（骤升/骤降）
    IMPACT = "impact"                  # 跌倒/撞击冲击波形
    REGIME_SHIFT = "regime_shift"      # 运动相态切换（久坐->奔跑等）


@dataclass(frozen=True)
class SensorSample:
    """单条原始传感器采样（过路数据，永不落库）。"""

    t: datetime
    channel: str
    value: float


@dataclass(frozen=True)
class CompactedInterval:
    """平稳期时段均值观测：一条顶替整段原始采样。"""

    channel: str
    start: datetime
    end: datetime
    sample_count: int
    mean_value: float
    min_value: float
    max_value: float

    def to_observation_payload(self) -> Dict[str, object]:
        return {
            "source_kind": "biometrics" if self.channel == ChannelKind.HEART_RATE else "sensor",
            "modality": "interval_mean",
            "value": (
                f"{self.channel} 平稳段均值 {self.mean_value:.1f}"
                f"（{self.sample_count} 个采样压缩为 1 条）"
            ),
            "unit": "bpm" if self.channel == ChannelKind.HEART_RATE else "g",
            "occurred_start": self.start.isoformat(),
            "occurred_end": self.end.isoformat(),
        }


@dataclass(frozen=True)
class AnomalyWaveform:
    """突变波形独立观测：携带下采样 digest，供按需回放。"""

    channel: str
    kind: str
    t_peak: datetime
    peak_value: float
    baseline: float
    delta: float
    digest: Tuple[float, ...]  # 下采样波形摘要（<= max_digest_points）

    def to_observation_payload(self) -> Dict[str, object]:
        return {
            "source_kind": "biometrics" if self.channel == ChannelKind.HEART_RATE else "sensor",
            "modality": "waveform_digest",
            "value": f"{self.kind.value} 峰值 {self.peak_value:.1f}（基线 {self.baseline:.1f}，偏移 {self.delta:+.1f}）",
            "occurred_start": self.t_peak.isoformat(),
            "digest_points": len(self.digest),
        }


@dataclass
class CompactionResult:
    """压缩回执：铁律断言全部挂在它身上。"""

    intervals: List[CompactedInterval] = field(default_factory=list)
    anomalies: List[AnomalyWaveform] = field(default_factory=list)
    samples_in: int = 0
    raw_rows_persisted: int = 0  # 宪法红线：必须恒为 0
    elapsed_ms: float = 0.0

    @property
    def records_out(self) -> int:
        return len(self.intervals) + len(self.anomalies)

    @property
    def compression_ratio(self) -> float:
        return self.samples_in / self.records_out if self.records_out else 0.0

    @property
    def filtered_ratio(self) -> float:
        """被压缩过滤掉的原始采样占比（盲测要求 >= 95%）。"""
        if self.samples_in == 0:
            return 0.0
        return 1.0 - (self.records_out / self.samples_in)


class AdaptiveTemporalCompactor:
    """单遍流式自适应压缩器：平稳->均值，突变->独立波形，原始零落库。"""

    def __init__(
        self,
        *,
        calm_window: timedelta = timedelta(minutes=5),
        hr_surge_delta: float = 25.0,
        impact_g_threshold: float = 4.0,
        surge_refractory: timedelta = timedelta(seconds=90),
        regime_shift_ratio: float = 0.30,
        max_digest_points: int = 16,
    ) -> None:
        self.calm_window = calm_window
        self.hr_surge_delta = hr_surge_delta
        self.impact_g_threshold = impact_g_threshold
        self.regime_shift_ratio = regime_shift_ratio
        self.max_digest_points = max_digest_points
        self.surge_refractory = surge_refractory

    # ------------------------------------------------------------------
    def compact(self, samples: Iterable[SensorSample]) -> CompactionResult:
        import time

        started = time.perf_counter()
        result = CompactionResult()

        class _ChannelState:
            def __init__(self) -> None:
                self.window_start: Optional[datetime] = None
                self.last_t: Optional[datetime] = None
                self.count = 0
                self.total = 0.0
                self.min_v = math.inf
                self.max_v = -math.inf
                self.baseline: Optional[float] = None
                self.recent_window_means: List[float] = []
                self.digest_buffer: List[Tuple[datetime, float]] = []
                self.refractory_until: Optional[datetime] = None

        states: Dict[str, _ChannelState] = {}

        def _flush_interval(ch: str, st: _ChannelState, end_t: datetime) -> None:
            if st.count == 0:
                return
            result.intervals.append(
                CompactedInterval(
                    channel=ch,
                    start=st.window_start,  # type: ignore[arg-type]
                    end=end_t,
                    sample_count=st.count,
                    mean_value=st.total / st.count,
                    min_value=st.min_v,
                    max_value=st.max_v,
                )
            )
            st.recent_window_means.append(st.total / st.count)
            if len(st.recent_window_means) > 4:
                st.recent_window_means.pop(0)
            st.window_start = None
            st.count = 0
            st.total = 0.0
            st.min_v = math.inf
            st.max_v = -math.inf

        def _emit_anomaly(ch: str, kind: AnomalyKind, sample: SensorSample, st: _ChannelState) -> None:
            digest_raw = st.digest_buffer[-(self.max_digest_points * 4):] + [(sample.t, sample.value)]
            if len(digest_raw) > self.max_digest_points:
                step = len(digest_raw) / self.max_digest_points
                digest = tuple(digest_raw[int(i * step)][1] for i in range(self.max_digest_points))
            else:
                digest = tuple(v for _, v in digest_raw)
            baseline = st.baseline if st.baseline is not None else sample.value
            result.anomalies.append(
                AnomalyWaveform(
                    channel=ch,
                    kind=kind,
                    t_peak=sample.t,
                    peak_value=sample.value,
                    baseline=baseline,
                    delta=sample.value - baseline,
                    digest=digest,
                )
            )
            st.digest_buffer.clear()

        for sample in samples:
            result.samples_in += 1
            st = states.get(sample.channel)
            if st is None:
                st = states[sample.channel] = _ChannelState()

            if st.window_start is None:
                st.window_start = sample.t
                st.baseline = sample.value

            # ---- 突变判定（先于累计，异常样本不混入平稳均值）----
            in_refractory = (
                st.refractory_until is not None and sample.t < st.refractory_until
            )
            if sample.channel == ChannelKind.HEART_RATE:
                if (
                    not in_refractory
                    and st.baseline is not None
                    and abs(sample.value - st.baseline) >= self.hr_surge_delta
                ):
                    _flush_interval(sample.channel, st, sample.t)
                    _emit_anomaly(sample.channel, AnomalyKind.RATE_SURGE, sample, st)
                    # 基线保持突变前水平 + 不应期：回落不二次误报，连续突变零漏检
                    st.refractory_until = sample.t + self.surge_refractory
                    st.window_start = sample.t
                    continue
                if not in_refractory:
                    st.baseline = (st.baseline * 0.98) + (sample.value * 0.02)
            elif sample.channel == ChannelKind.IMU_MAGNITUDE:
                if sample.value >= self.impact_g_threshold:
                    _flush_interval(sample.channel, st, sample.t)
                    _emit_anomaly(sample.channel, AnomalyKind.IMPACT, sample, st)
                    st.window_start = sample.t
                    continue

            # ---- 累计平稳窗口 ----
            st.count += 1
            st.total += sample.value
            st.min_v = min(st.min_v, sample.value)
            st.max_v = max(st.max_v, sample.value)
            st.last_t = sample.t
            st.digest_buffer.append((sample.t, sample.value))
            if len(st.digest_buffer) > self.max_digest_points * 8:
                del st.digest_buffer[: len(st.digest_buffer) - self.max_digest_points * 8]

            if (sample.t - st.window_start) >= self.calm_window:
                prev_means = list(st.recent_window_means)
                window_mean = st.total / st.count
                _flush_interval(sample.channel, st, sample.t)
                # 运动相态切换：相邻窗口均值持续大幅位移
                if prev_means:
                    drift = abs(window_mean - prev_means[-1]) / max(abs(prev_means[-1]), 1e-6)
                    if drift >= self.regime_shift_ratio:
                        result.anomalies.append(
                            AnomalyWaveform(
                                channel=sample.channel,
                                kind=AnomalyKind.REGIME_SHIFT,
                                t_peak=sample.t,
                                peak_value=window_mean,
                                baseline=prev_means[-1],
                                delta=window_mean - prev_means[-1],
                                digest=(),
                            )
                        )
                st.window_start = sample.t

        # ---- 收尾：末段平稳期也要结晶，不许悬空 ----
        for ch, st in states.items():
            if st.count:
                _flush_interval(ch, st, st.last_t or st.window_start)  # type: ignore[arg-type]

        result.elapsed_ms = (time.perf_counter() - started) * 1000.0
        return result
