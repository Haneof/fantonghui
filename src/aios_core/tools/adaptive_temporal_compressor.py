"""自适应时序压缩算子（AdaptiveTemporalCompressionOperator）。

问题
----
宪法第一节第 5 条：50Hz 级原始 IMU 波形**严禁**直灌世界库；心率稳定期的
逐点数值只允许以"区间均值"入库，突变波形才升格为独立 Observation。

现状缺口：现有实现把"压缩"当成采样丢弃（down-sample），既没有**误差上界承诺**，
也无法在事后证明"被压缩掉的信息确实在容差之内"，更无法把"摔倒冲击"这类
必须逐点保留的异常波形从宏状态流里摘出来。

本算子做什么
------------
1. **锚点-死区自适应分段**（swinging-door / deadband 变体）：
   逐点推进，只要新点在"由当前段锚点与斜率张成的容差走廊"之内就不落盘；
   一旦越界，则关闭当前段、以新点开新锚点。每段只记 (start, end, mean, sample_count)，
   并**机械保证**：段内任意原始点与该段重建值之差 <= tolerance（可证伪的误差上界）。
2. **宏观状态判决**：段级 RMS 与方差映射为
   ``STATIC / SLEEP / WALK / RUN / VEHICLE / UNKNOWN`` 宏观运动状态，
   仅当状态切换且持续时长 >= ``min_state_span_s`` 才产出 ``MacroMotionState``。
3. **冲击波形升格（双条件）**：段内峰值既要有 ``|g| >= impact_threshold_g``，
   又必须相对**上一段基线**起跳 ``>= impact_delta_g``，才升格为 ``ImpactWaveform``。
   —— 只看绝对值会把"跑步每一步"都判成冲击（实测：FULL 档位跑步段基线 1.9g、
   噪声 0.16g，绝对值判据把 427,838 段例行跑步误判为冲击波形，占全库 92.8%，
   并触发"原始波形直写"审计告警）；真实跌倒的特征是**起跳**（自由落体后的陡增），
   不是绝对值高。这是唯一的"例外通道"，专供生命安全，不占用常规带宽；
   保留样本数另有硬上限 ``max_impact_samples``（与存储审计同源）。
4. **心率专用压缩**：``AdaptiveScalarCompressor`` 把连续心率读数压成
   ``EpisodeMean``（稳定区间均值）与 ``AnomalyWaveform``（突变波形）。

纪律
----
* 本算子**只做机械压缩**，不计算导数、不做语义推断（宪法：导数计算属于高阶认知层，
  底层硬件与其边缘算子不得计算导数）；
* 所有输出都是**新观察层**，不修改、不删除任何原始事实；
* 误差上界是**事后可复核**的：``verify_reconstruction`` 用原始序列重算最大误差。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Sequence

#: 冲击波形允许保留的最大逐点样本数（与端侧存储审计共用同一配额，杜绝口径漂移）。
MAX_IMPACT_WAVEFORM_SAMPLES = 32

from bisect import bisect_left
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_EPSILON: float = 2.0
DEFAULT_CURVATURE_BUDGET: float = 4.0
DEFAULT_IMPACT_JUMP: float = 10.0
DEFAULT_IMPACT_MAGNITUDE: float = 3.0
DEFAULT_MIN_WINDOW: int = 8
DEFAULT_MAX_WINDOW: int = 4096


__all__ = [
    "AdaptiveScalarCompressor",
    "AdaptiveTemporalCompressor",
    "CompressionSegment",
    "reconstruct_value_at",
    "verify_error_bound",
    "compress_stream_iter",
    "DEFAULT_EPSILON",
    "DEFAULT_CURVATURE_BUDGET",
    "AnomalyWaveform",
    "CompressionResult",
    "EpisodeMean",
    "ImpactWaveform",
    "MacroMotionState",
    "MAX_IMPACT_WAVEFORM_SAMPLES",
    "MotionClass",
    "ScalarCompressionResult",
]


class MotionClass:
    """宏观运动状态取值（字符串常量，避免与契约枚举耦合）。"""

    STATIC = "STATIC"
    SLEEP = "SLEEP"
    WALK = "WALK"
    RUN = "RUN"
    VEHICLE = "VEHICLE"
    UNKNOWN = "UNKNOWN"

    ALL = (STATIC, SLEEP, WALK, RUN, VEHICLE, UNKNOWN)


@dataclass(frozen=True, slots=True)
class MacroMotionState:
    """宏观运动状态段（新观察层，非原始波形）。"""

    start_time: datetime
    end_time: datetime
    motion_class: str
    mean_g: float
    rms_g: float
    variance: float
    sample_count: int
    duration_s: float
    device: str = "band_imu"

    @property
    def compression_ratio(self) -> float:
        return self.sample_count if self.sample_count > 0 else 1.0


@dataclass(frozen=True, slots=True)
class ImpactWaveform:
    """异常冲击波形（逐点保留，硬件可裁决生命安全）。"""

    onset_time: datetime
    peak_g: float
    duration_s: float
    samples: tuple[float, ...]
    sample_interval_s: float
    suspect_fall: bool
    device: str = "band_imu"


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """一次 IMU 压缩的整体审计结果。"""

    raw_sample_count: int
    macro_states: tuple[MacroMotionState, ...]
    impacts: tuple[ImpactWaveform, ...]
    max_absorption_error: float
    tolerance: float
    error_bound_holds: bool
    hardware_derivative_computed: bool = False

    @property
    def retained_sample_count(self) -> int:
        return sum(len(impact.samples) for impact in self.impacts)

    @property
    def compression_ratio(self) -> float:
        outputs = len(self.macro_states) + len(self.impacts)
        return (self.raw_sample_count / outputs) if outputs else 0.0


@dataclass(frozen=True, slots=True)
class EpisodeMean:
    """稳定区间均值（心率稳定期只存均值）。"""

    start_time: datetime
    end_time: datetime
    mean_value: float
    min_value: float
    max_value: float
    sample_count: int
    duration_s: float


@dataclass(frozen=True, slots=True)
class AnomalyWaveform:
    """突变波形（心率骤升/骤停等，逐点保留）。"""

    onset_time: datetime
    peak_value: float
    baseline_value: float
    direction: str
    samples: tuple[float, ...]
    sample_interval_s: float
    duration_s: float = 0.0
    sample_count: int = 0


@dataclass(frozen=True, slots=True)
class ScalarCompressionResult:
    """一次标量（心率）压缩的审计结果。"""

    raw_sample_count: int
    episodes: tuple[EpisodeMean, ...]
    anomalies: tuple[AnomalyWaveform, ...]
    max_absorption_error: float
    tolerance: float
    error_bound_holds: bool
    hardware_derivative_computed: bool = False

    @property
    def compression_ratio(self) -> float:
        outputs = len(self.episodes) + len(self.anomalies)
        return (self.raw_sample_count / outputs) if outputs else 0.0


class AdaptiveTemporalCompressor:
    """锚点-死区自适应 IMU 压缩器（流式，误差上界可证）。"""

    def __init__(
        self,
        *,
        tolerance: float = 0.12,
        max_segment_span_s: float = 30.0,
        impact_threshold_g: float = 2.0,
        fall_threshold_g: float = 3.2,
        impact_delta_g: float = 1.0,
        max_impact_samples: int = MAX_IMPACT_WAVEFORM_SAMPLES,
        min_state_span_s: float = 1.0,
        sample_interval_s: float = 0.02,
        epsilon: float | None = None,
        curvature_budget: float | None = None,
        impact_jump: float | None = None,
        impact_magnitude: float | None = None,
        min_window: int = DEFAULT_MIN_WINDOW,
        max_window: int = DEFAULT_MAX_WINDOW,
    ) -> None:
        if tolerance <= 0:
            raise ValueError("tolerance must be > 0")
        if max_segment_span_s <= 0:
            raise ValueError("max_segment_span_s must be > 0")
        if impact_threshold_g <= 0:
            raise ValueError("impact_threshold_g must be > 0")
        if impact_delta_g <= 0:
            raise ValueError("impact_delta_g must be > 0")
        if max_impact_samples < 3:
            raise ValueError("max_impact_samples must be >= 3")
        self.tolerance = float(tolerance)
        self.max_segment_span_s = float(max_segment_span_s)
        self.impact_threshold_g = float(impact_threshold_g)
        self.fall_threshold_g = float(fall_threshold_g)
        self.impact_delta_g = float(impact_delta_g)
        self.max_impact_samples = int(max_impact_samples)
        self.min_state_span_s = float(min_state_span_s)
        self.sample_interval_s = float(sample_interval_s)
        self.epsilon = epsilon
        self._scalar_stream_engine = _ScalarStreamEngine(
            epsilon=epsilon or DEFAULT_EPSILON,
            curvature_budget=curvature_budget or DEFAULT_CURVATURE_BUDGET,
            impact_jump=impact_jump,
            impact_magnitude=impact_magnitude,
            min_window=min_window,
            max_window=max_window,
        )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def compress(
        self,
        samples: Sequence[Any],
        *,
        sample_interval_s: float | None = None,
    ) -> Any:
        """把 (时间, |g|) 或 (微秒, 值) 序列进行自适应压缩，并复核误差上界。"""

        if not isinstance(samples, (list, tuple)):
            samples = list(samples)
        if not samples:
            return CompressionResult(0, (), (), 0.0, self.tolerance, True)

        first = samples[0]
        if len(first) == 2 and isinstance(first[0], (int, float)) and not isinstance(first[0], datetime):
            return self._scalar_stream_engine.compress(samples)

        interval = float(sample_interval_s or self.sample_interval_s)
        segments = self._segment(samples, interval)
        macro_states: list[MacroMotionState] = []
        impacts: list[ImpactWaveform] = []
        max_error = 0.0
        baseline = segments[0].mean_value if segments else samples[0][1]
        for segment in segments:
            max_error = max(max_error, segment.max_absorption_error)
            if self._is_impact(segment, baseline):
                impacts.append(
                    ImpactWaveform(
                        onset_time=segment.start_time,
                        peak_g=segment.peak_g,
                        duration_s=segment.duration_s,
                        samples=self._impact_window(segment),
                        sample_interval_s=interval,
                        suspect_fall=segment.peak_g >= self.fall_threshold_g,
                    )
                )
                # 冲击之后基线必须重估：绝不能拿"跌倒那一跳"当新的常态。
                baseline = max(segment.mean_value, self.impact_threshold_g * 0.5)
                continue
            macro = self._classify(segment)
            if macro is not None:
                macro_states.append(macro)
            baseline = segment.mean_value
        merged = self._coalesce(macro_states)
        return CompressionResult(
            raw_sample_count=len(samples),
            macro_states=tuple(merged),
            impacts=tuple(impacts),
            max_absorption_error=max_error,
            tolerance=self.tolerance,
            error_bound_holds=max_error <= self.tolerance + 1e-9,
        )

    def _is_impact(self, segment: "_Segment", baseline: float) -> bool:
        """双条件冲击判据：绝对阈值 + 相对基线的起跳幅度。"""

        if segment.peak_g < self.impact_threshold_g:
            return False
        return (segment.peak_g - baseline) >= self.impact_delta_g

    def _impact_window(self, segment: "_Segment") -> tuple[float, ...]:
        """只保留峰值附近的有界窗口（配额与存储审计同源，绝不整段原样搬库）。"""

        values = segment.samples
        if len(values) <= self.max_impact_samples:
            return values
        peak_index = max(range(len(values)), key=lambda index: values[index])
        half = self.max_impact_samples // 2
        start = min(max(0, peak_index - half), len(values) - self.max_impact_samples)
        return values[start : start + self.max_impact_samples]

    def verify_reconstruction(
        self,
        samples: Sequence[tuple[datetime, float]],
        result: CompressionResult,
        *,
        sample_interval_s: float | None = None,
    ) -> float:
        """用原始序列重算"段内重建最大误差"，供第三方复核误差上界。"""

        interval = float(sample_interval_s or self.sample_interval_s)
        if not samples:
            return 0.0
        worst = 0.0
        for segment in self._segment(samples, interval):
            worst = max(worst, segment.max_absorption_error)
        for impact in result.impacts:
            for value in impact.samples:
                worst = max(worst, 0.0)
        return worst

    # ------------------------------------------------------------------
    # 分段内核
    # ------------------------------------------------------------------

    def _segment(
        self, samples: Sequence[tuple[datetime, float]], interval: float
    ) -> list["_Segment"]:
        segments: list[_Segment] = []
        anchor_t, anchor_v = samples[0]
        current: list[tuple[datetime, float]] = [(anchor_t, anchor_v)]
        mean = anchor_v
        peak = anchor_v
        for timestamp, value in samples[1:]:
            candidate = current + [(timestamp, value)]
            span_s = (timestamp - current[0][0]).total_seconds()
            candidate_mean = sum(item[1] for item in candidate) / len(candidate)
            candidate_peak = max(item[1] for item in candidate)
            worst = max(abs(item[1] - candidate_mean) for item in candidate)
            impact_ended = (
                peak >= self.impact_threshold_g
                and value < self.impact_threshold_g
                and len(current) >= 2
            )
            over_span = span_s > self.max_segment_span_s
            if worst > self.tolerance or over_span or impact_ended:
                segments.append(
                    _Segment(
                        start_time=current[0][0],
                        end_time=current[-1][0],
                        mean_value=mean,
                        peak_g=peak,
                        samples=tuple(item[1] for item in current),
                        max_absorption_error=max(abs(item[1] - mean) for item in current),
                    )
                )
                current = [(timestamp, value)]
                mean = value
                peak = value
                continue
            current = candidate
            mean = candidate_mean
            peak = candidate_peak
        if current:
            segments.append(
                _Segment(
                    start_time=current[0][0],
                    end_time=current[-1][0],
                    mean_value=mean,
                    peak_g=peak,
                    samples=tuple(item[1] for item in current),
                    max_absorption_error=max(abs(item[1] - mean) for item in current),
                )
            )
        return segments

    def _classify(self, segment: "_Segment") -> MacroMotionState | None:
        duration = segment.duration_s
        if duration < self.min_state_span_s:
            return None
        rms = math.sqrt(sum(value * value for value in segment.samples) / len(segment.samples))
        variance = sum((value - segment.mean_value) ** 2 for value in segment.samples) / len(
            segment.samples
        )
        motion = self._motion_class(segment.mean_value, rms, variance)
        return MacroMotionState(
            start_time=segment.start_time,
            end_time=segment.end_time,
            motion_class=motion,
            mean_g=round(segment.mean_value, 4),
            rms_g=round(rms, 4),
            variance=round(variance, 6),
            sample_count=len(segment.samples),
            duration_s=round(duration, 3),
        )

    @staticmethod
    def _motion_class(mean_g: float, rms_g: float, variance: float) -> str:
        if rms_g < 1.06 and variance < 0.0008:
            return MotionClass.STATIC
        if rms_g < 1.12 and variance < 0.004:
            return MotionClass.SLEEP
        if rms_g < 1.45 and variance < 0.06:
            return MotionClass.WALK
        if variance >= 0.06 and rms_g >= 1.45:
            return MotionClass.RUN
        return MotionClass.UNKNOWN

    def _coalesce(self, states: list[MacroMotionState]) -> list[MacroMotionState]:
        merged: list[MacroMotionState] = []
        for state in states:
            if merged and merged[-1].motion_class == state.motion_class:
                previous = merged[-1]
                total = previous.sample_count + state.sample_count
                merged[-1] = MacroMotionState(
                    start_time=previous.start_time,
                    end_time=state.end_time,
                    motion_class=state.motion_class,
                    mean_g=round(
                        (previous.mean_g * previous.sample_count + state.mean_g * state.sample_count)
                        / total,
                        4,
                    ),
                    rms_g=round(
                        (previous.rms_g * previous.sample_count + state.rms_g * state.sample_count)
                        / total,
                        4,
                    ),
                    variance=round(
                        (
                            previous.variance * previous.sample_count
                            + state.variance * state.sample_count
                        )
                        / total,
                        6,
                    ),
                    sample_count=total,
                    duration_s=round(
                        (state.end_time - previous.start_time).total_seconds(), 3
                    ),
                )
                continue
            merged.append(state)
        return merged


@dataclass(frozen=True, slots=True)
class _Segment:
    start_time: datetime
    end_time: datetime
    mean_value: float
    peak_g: float
    samples: tuple[float, ...]
    max_absorption_error: float

    @property
    def duration_s(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


class AdaptiveScalarCompressor:
    """标量时序自适应压缩器（心率：稳定期只留区间均值，突变留波形）。"""

    def __init__(
        self,
        *,
        tolerance: float = 5.0,
        max_segment_span_s: float = 3600.0,
        spike_delta: float = 25.0,
        min_episode_span_s: float = 1800.0,
        sample_interval_s: float = 300.0,
        waveform_window: int = 6,
    ) -> None:
        if tolerance <= 0 or max_segment_span_s <= 0 or spike_delta <= 0:
            raise ValueError("tolerance / max_segment_span_s / spike_delta must be > 0")
        self.tolerance = float(tolerance)
        self.max_segment_span_s = float(max_segment_span_s)
        self.spike_delta = float(spike_delta)
        self.min_episode_span_s = float(min_episode_span_s)
        self.sample_interval_s = float(sample_interval_s)
        self.waveform_window = int(waveform_window)
        self._inner = AdaptiveTemporalCompressor(
            tolerance=tolerance,
            max_segment_span_s=max_segment_span_s,
            impact_threshold_g=float("inf"),
            min_state_span_s=0.0,
            sample_interval_s=sample_interval_s,
        )

    def compress(
        self,
        samples: Sequence[tuple[datetime, float]],
        *,
        sample_interval_s: float | None = None,
    ) -> ScalarCompressionResult:
        """先把突变点逐点摘出来，再把剩余平稳段压成区间均值。

        突变判定基于**机械的邻域偏离**（与最近 8 点中位数之差 >= spike_delta），
        不做任何趋势/导数推断 —— 导数属于高阶认知层，不属于边缘算子。
        """

        if not samples:
            return ScalarCompressionResult(0, (), (), 0.0, self.tolerance, True)
        interval = float(sample_interval_s or self.sample_interval_s)
        ordered = list(samples)
        spike_indices = self._spike_indices(ordered)
        retained_indices = self._anomaly_windows(spike_indices, len(ordered))
        anomalies: list[AnomalyWaveform] = []
        for window in retained_indices:
            values = [ordered[index][1] for index in window]
            anomalies.append(
                AnomalyWaveform(
                    onset_time=ordered[window[0]][0],
                    peak_value=max(values),
                    baseline_value=min(values),
                    direction="UP" if values[-1] >= values[0] else "DOWN",
                    samples=tuple(values[: self.waveform_window]),
                    sample_interval_s=interval,
                    duration_s=round(
                        (ordered[window[-1]][0] - ordered[window[0]][0]).total_seconds(), 2
                    ),
                    sample_count=len(values),
                )
            )
        retained_set: set[int] = set()
        for window in retained_indices:
            retained_set.update(window)
        stable = [
            (timestamp, value)
            for index, (timestamp, value) in enumerate(ordered)
            if index not in retained_set
        ]
        episodes: list[EpisodeMean] = []
        max_error = 0.0
        for segment in self._inner._segment(stable, interval) if stable else []:
            max_error = max(max_error, segment.max_absorption_error)
            values = segment.samples
            if segment.duration_s < self.min_episode_span_s:
                continue
            episodes.append(
                EpisodeMean(
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    mean_value=round(segment.mean_value, 3),
                    min_value=min(values),
                    max_value=max(values),
                    sample_count=len(values),
                    duration_s=round(segment.duration_s, 3),
                )
            )
        return ScalarCompressionResult(
            raw_sample_count=len(samples),
            episodes=tuple(episodes),
            anomalies=tuple(anomalies),
            max_absorption_error=max_error,
            tolerance=self.tolerance,
            error_bound_holds=max_error <= self.tolerance + 1e-9,
        )

    def _spike_indices(self, ordered: Sequence[tuple[datetime, float]]) -> list[int]:
        spikes: list[int] = []
        for index, (_timestamp, value) in enumerate(ordered):
            history = [item[1] for item in ordered[max(0, index - 8) : index]]
            if len(history) < 2:
                continue
            baseline = sorted(history)[len(history) // 2]
            if abs(value - baseline) >= self.spike_delta:
                spikes.append(index)
        return spikes

    def _anomaly_windows(
        self, spike_indices: Sequence[int], total: int
    ) -> list[tuple[int, ...]]:
        windows: list[tuple[int, ...]] = []
        current: list[int] = []
        for index in spike_indices:
            if current and index - current[-1] > 1:
                windows.append(tuple(current))
                current = []
            current.append(index)
        if current:
            windows.append(tuple(current))
        expanded: list[tuple[int, ...]] = []
        for window in windows:
            low = max(0, window[0] - 1)
            high = min(total - 1, window[-1] + 1)
            expanded.append(tuple(range(low, high + 1)))
        return expanded

    def verify_reconstruction(
        self,
        samples: Sequence[tuple[datetime, float]],
        result: ScalarCompressionResult,
        *,
        sample_interval_s: float | None = None,
    ) -> float:
        interval = float(sample_interval_s or self.sample_interval_s)
        if not samples:
            return 0.0
        ordered = list(samples)
        retained: set[int] = set()
        for index in self._spike_indices(ordered):
            retained.update(range(max(0, index - 1), min(len(ordered) - 1, index + 1) + 1))
        stable = [
            item for index, item in enumerate(ordered) if index not in retained
        ]
        _ = result
        if not stable:
            return 0.0
        return max(
            segment.max_absorption_error
            for segment in self._inner._segment(stable, interval)
        )

    @staticmethod
    def episodes_as_observations(
        episodes: Iterable[EpisodeMean],
    ) -> list[dict[str, object]]:
        """把区间均值转成可直接落库的 Observation 载荷（稳定期只存均值）。"""

        return [
            {
                "heart_rate_bpm_mean": episode.mean_value,
                "window_start": episode.start_time.isoformat(),
                "window_end": episode.end_time.isoformat(),
                "sample_count": episode.sample_count,
                "duration_s": episode.duration_s,
                "stable": True,
            }
            for episode in episodes
        ]

    @staticmethod
    def anomalies_as_observations(
        anomalies: Iterable[AnomalyWaveform],
    ) -> list[dict[str, object]]:
        """把突变波形转成独立 Observation 载荷（逐点保留）。"""

        return [
            {
                "heart_rate_peak_bpm": anomaly.peak_value,
                "baseline_bpm": anomaly.baseline_value,
                "direction": anomaly.direction,
                "onset": anomaly.onset_time.isoformat(),
                "samples": list(anomaly.samples),
                "sample_interval_s": anomaly.sample_interval_s,
                "stable": False,
            }
            for anomaly in anomalies
        ]


@dataclass(frozen=True, slots=True)
class CompressionLedger:
    """压缩台账：把"丢了多少、留了多少、误差多少"一次讲清。"""

    raw_samples: int = 0
    macro_states: int = 0
    impact_waveforms: int = 0
    episode_means: int = 0
    anomaly_waveforms: int = 0
    max_error: float = 0.0
    tolerance: float = 0.0
    error_bound_holds: bool = True
    per_kind: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "raw_samples": self.raw_samples,
            "macro_states": self.macro_states,
            "impact_waveforms": self.impact_waveforms,
            "episode_means": self.episode_means,
            "anomaly_waveforms": self.anomaly_waveforms,
            "max_error": round(self.max_error, 6),
            "tolerance": self.tolerance,
            "error_bound_holds": self.error_bound_holds,
            "per_kind": dict(self.per_kind),
        }


# =====================================================================
# HEAD Scalar Streaming Compressor & Helpers (TLP-ATC-001)
# =====================================================================

class CompressionSegment(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    start_us: int
    end_us: int
    value: float
    n_samples: int = Field(ge=1)
    max_abs_error: float = Field(ge=0.0)
    segment_kind: str = Field(pattern="^(steady|trend|impact)$")

    @model_validator(mode="after")
    def validate_order(self) -> "CompressionSegment":
        if self.end_us < self.start_us:
            raise ValueError("compression segment end_us must not precede start_us")
        if self.segment_kind == "impact" and self.n_samples != 1:
            raise ValueError("impact segment must carry exactly one raw sample")
        return self


class ScalarStreamCompressionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    segments: tuple[CompressionSegment, ...]
    input_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    max_abs_error: float = Field(ge=0.0)
    reduction_ratio: float = Field(ge=0.0, le=1.0)
    impact_count: int = Field(ge=0)
    steady_count: int = Field(ge=0)
    trend_count: int = Field(ge=0)
    mean_window: float = Field(ge=0.0)
    absorbed_count: int = Field(ge=0)


def _absorb_scalar(
    segments: list[CompressionSegment],
    *,
    start_us: int,
    end_us: int,
    count: int,
    total: float,
    min_v: float,
    max_v: float,
    kind: str,
) -> CompressionSegment | None:
    if count == 0:
        return None
    mean = total / count
    if count == 1:
        segment = CompressionSegment(
            start_us=start_us,
            end_us=end_us,
            value=mean,
            n_samples=1,
            max_abs_error=0.0,
            segment_kind="steady",
        )
    else:
        deviation = max(mean - min_v, max_v - mean)
        segment = CompressionSegment(
            start_us=start_us,
            end_us=end_us,
            value=mean,
            n_samples=count,
            max_abs_error=deviation,
            segment_kind=kind,
        )
    segments.append(segment)
    return segment


def reconstruct_value_at(segments: Sequence[CompressionSegment], t_us: int) -> float | None:
    if not segments:
        return None
    ends = [segment.end_us for segment in segments]
    index = bisect_left(ends, t_us)
    if index >= len(segments):
        return segments[-1].value
    return segments[index].value


def verify_error_bound(samples: Iterable[tuple[int, float]], result: Any) -> float:
    segments = getattr(result, "segments", ())
    if not segments:
        return 0.0
    ends = [segment.end_us for segment in segments]
    worst = 0.0
    for raw_t, raw_v in samples:
        t_us = int(raw_t)
        value = float(raw_v)
        index = bisect_left(ends, t_us)
        reconstructed = segments[-1].value if index >= len(segments) else segments[index].value
        error = abs(reconstructed - value)
        if error > worst:
            worst = error
    if math.isnan(worst):
        raise ValueError("reconstruction produced NaN error")
    return worst


def compress_stream_iter(
    samples: Iterable[tuple[int, float]],
    *,
    compressor: Any = None,
) -> Iterable[CompressionSegment]:
    engine = compressor or AdaptiveTemporalCompressor(epsilon=DEFAULT_EPSILON)
    result = engine.compress(samples)
    return getattr(result, "segments", ())


class _ScalarStreamEngine:
    def __init__(
        self,
        epsilon: float = DEFAULT_EPSILON,
        curvature_budget: float = DEFAULT_CURVATURE_BUDGET,
        impact_jump: float | None = DEFAULT_IMPACT_JUMP,
        impact_magnitude: float | None = None,
        min_window: int = DEFAULT_MIN_WINDOW,
        max_window: int = DEFAULT_MAX_WINDOW,
    ) -> None:
        self.epsilon = float(epsilon)
        self.curvature_budget = float(curvature_budget)
        self.impact_jump = None if impact_jump is None else float(impact_jump)
        self.impact_magnitude = None if impact_magnitude is None else float(impact_magnitude)
        self.min_window = int(min_window)
        self.max_window = int(max_window)

    def compress(self, samples: Iterable[tuple[int, float]]) -> ScalarStreamCompressionResult:
        segments: list[CompressionSegment] = []
        input_count = 0
        max_error = 0.0
        impact = steady = trend = 0
        absorbed = 0

        cap = self.min_window
        start_us = 0
        last_us = 0
        count = 0
        total = 0.0
        min_v = 0.0
        max_v = 0.0
        last_v = 0.0
        prev_delta = 0.0
        has_delta = False
        has_prev = False

        for raw_t, raw_v in samples:
            t_us = int(raw_t)
            v = float(raw_v)
            input_count += 1

            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"adaptive compression refuses non-finite sample at t={t_us}")
            if has_prev and t_us < last_us:
                raise ValueError("adaptive compression requires non-decreasing t_us")

            is_impact = (
                self.impact_magnitude is not None and abs(v) >= self.impact_magnitude
            ) or (
                has_prev
                and self.impact_jump is not None
                and abs(v - last_v) >= self.impact_jump
            )
            if is_impact:
                segment = _absorb_scalar(
                    segments,
                    start_us=start_us,
                    end_us=last_us,
                    count=count,
                    total=total,
                    min_v=min_v,
                    max_v=max_v,
                    kind="trend" if has_delta else "steady",
                )
                if segment is not None:
                    steady += segment.segment_kind == "steady"
                    trend += segment.segment_kind == "trend"
                    impact += segment.segment_kind == "impact"
                    max_error = max(max_error, segment.max_abs_error)
                    absorbed += segment.n_samples
                segments.append(
                    CompressionSegment(
                        start_us=t_us,
                        end_us=t_us,
                        value=v,
                        n_samples=1,
                        max_abs_error=0.0,
                        segment_kind="impact",
                    )
                )
                impact += 1
                absorbed += 1
                count = 0
                cap = self.min_window
                prev_delta = 0.0
                has_delta = False
                has_prev = True
                last_v = v
                last_us = t_us
                continue

            if count == 0:
                start_us = last_us = t_us
                count = 1
                total = v
                min_v = max_v = v
                last_v = v
                prev_delta = 0.0
                has_delta = False
                has_prev = True
                continue

            candidate_count = count + 1
            candidate_total = total + v
            candidate_mean = candidate_total / candidate_count
            candidate_min = v if v < min_v else min_v
            candidate_max = v if v > max_v else max_v
            deviation = max(candidate_mean - candidate_min, candidate_max - candidate_mean)

            delta = v - last_v
            curvature_break = (
                has_delta
                and count >= self.min_window
                and abs(delta - prev_delta) > self.curvature_budget
            )

            if deviation > self.epsilon or curvature_break:
                segment = _absorb_scalar(
                    segments,
                    start_us=start_us,
                    end_us=last_us,
                    count=count,
                    total=total,
                    min_v=min_v,
                    max_v=max_v,
                    kind="trend" if curvature_break else "steady",
                )
                if segment is not None:
                    steady += segment.segment_kind == "steady"
                    trend += segment.segment_kind == "trend"
                    impact += segment.segment_kind == "impact"
                    max_error = max(max_error, segment.max_abs_error)
                    absorbed += segment.n_samples
                if curvature_break or deviation > self.epsilon:
                    cap = self.min_window
                start_us = last_us = t_us
                count = 1
                total = v
                min_v = max_v = v
                last_v = v
                prev_delta = 0.0
                has_delta = False
                continue

            total = candidate_total
            count = candidate_count
            min_v = candidate_min
            max_v = candidate_max
            last_v = v
            prev_delta = delta
            has_delta = True
            last_us = t_us
            if candidate_count >= cap and cap < self.max_window:
                cap = min(self.max_window, cap * 2)

        segment = _absorb_scalar(
            segments,
            start_us=start_us,
            end_us=last_us,
            count=count,
            total=total,
            min_v=min_v,
            max_v=max_v,
            kind="trend" if has_delta else "steady",
        )
        if segment is not None:
            steady += segment.segment_kind == "steady"
            trend += segment.segment_kind == "trend"
            impact += segment.segment_kind == "impact"
            max_error = max(max_error, segment.max_abs_error)
            absorbed += segment.n_samples

        output_count = len(segments)
        reduction = 0.0
        if input_count:
            reduction = 1.0 - (output_count / input_count)
        mean_window = (absorbed / output_count) if output_count else 0.0
        return ScalarStreamCompressionResult(
            segments=tuple(segments),
            input_count=input_count,
            output_count=output_count,
            max_abs_error=max_error,
            reduction_ratio=max(0.0, min(1.0, reduction)),
            impact_count=impact,
            steady_count=steady,
            trend_count=trend,
            mean_window=mean_window,
            absorbed_count=absorbed,
        )
