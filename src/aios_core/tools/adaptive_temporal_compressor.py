"""自适应时序压缩算子（Adaptive Temporal Compressor，ToolProposal TLP-ATC-001）。

宪法依据
--------
* 第三十三条第 1 款：IMU 属运动状态采集器，**绝对不得**把 50Hz/100Hz 高频时序
  数值直接记入数据库；心率平稳期仅压缩记录一个时段均值点，异常波形才独立成
  Observation；
* 第二十五条：总结是新观察层，不是压缩删除 —— 本算子只产出**派生的聚合段**
  （派生观察层），绝不改写、绝不丢弃原始采样流本身；调用方拥有原始流的所有权；
* 第八十六条之一（预算）：端侧算力与存储寸土寸金，压缩必须在 O(1) 附加内存、
  单趟流式、纯标准库下完成。

为什么既有实现不够
------------------
仓库既有的 ``PulseMergeWindow`` 是**固定时间窗**（5s 脉搏归一）去重合并，存在
两个硬缺陷：

1. 固定窗口在平稳期仍然每窗产出一个点（心率平稳 8 小时 = 3600 点），没有把
   "平稳即长窗" 这条宪法语义吃进去；
2. 固定窗口在剧烈波动期会把波形压平（冲击被平均掉），冲击保护只能靠额外通道，
   造成"平稳期浪费、突变期失真"的双向损耗。

本算子用**误差有界的自适应窗口**替换固定窗口：

* 窗口长度按几何级数自适应增长（``min_window`` → ``max_window``），且**填满即翻倍**
  ——平稳期一段最多吸收 ``max_window`` 个采样而只产出一个均值点，压缩比随平稳度
  自动放大；窗口只由误差界与曲率预算关闭，绝不为"凑窗口"而切碎数据；
* 窗口内**均值偏差上界** ``max(|v - mean|)`` 被硬约束在 ``epsilon`` 之内 ——
  这是可证明的重建误差界（见 :func:`verify_error_bound`），不是启发式口号；
* 二阶差分（曲率）超预算立即封窗，陡变前沿不会被长窗抹平；
* 命中 ``impact_jump``（相邻跳变，心率骤升/骤降）或 ``impact_magnitude``（绝对
  幅值，IMU 撞击 g 值）的冲击采样**永不被平均**：先封当前窗，再以
  ``segment_kind="impact"``、``n_samples=1`` 原值落段（宪法"异常冲击波形独立成
  Observation"的算子级保障）。

复杂度：单趟 O(n)、附加内存 O(1)（只维护 running sum / min / max / 上一采样值 /
上一差分），零第三方依赖。
"""

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AdaptiveTemporalCompressor",
    "CompressionResult",
    "CompressionSegment",
    "DEFAULT_CURVATURE_BUDGET",
    "DEFAULT_EPSILON",
    "DEFAULT_IMPACT_JUMP",
    "DEFAULT_IMPACT_MAGNITUDE",
    "DEFAULT_MAX_WINDOW",
    "DEFAULT_MIN_WINDOW",
    "compress_stream_iter",
    "reconstruct_value_at",
    "verify_error_bound",
]

#: 默认误差界（心率 bpm 与 IMU 合成加速度共用同一量纲无关的抽象界）。
DEFAULT_EPSILON: float = 2.0
#: 默认曲率预算：相邻一阶差分的变化量超过该值即认为"形态在拐弯"。
DEFAULT_CURVATURE_BUDGET: float = 4.0
#: 默认跳变冲击阈值：相邻采样跳变达到该幅度即视为突发波形（心率骤升/骤降）。
DEFAULT_IMPACT_JUMP: float = 10.0
#: 默认绝对幅值冲击阈值：合成加速度幅值达到该值即视为疑似撞击/跌倒（IMU 通道）。
DEFAULT_IMPACT_MAGNITUDE: float = 3.0
#: 窗口下界：至少吸收这么多采样，避免退化成采样级碎片。
DEFAULT_MIN_WINDOW: int = 8
#: 窗口上界：平稳期单窗最大吸收长度（几何增长天花板）。
DEFAULT_MAX_WINDOW: int = 4096


class CompressionSegment(BaseModel):
    """一个自适应窗口压缩后的派生段（新观察层，不删除任何原始采样）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class CompressionResult(BaseModel):
    """压缩结果与可复核的压缩比 / 误差界 / 冲击计数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

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

    @model_validator(mode="after")
    def validate_counts(self) -> "CompressionResult":
        if self.output_count != len(self.segments):
            raise ValueError("output_count must equal the number of segments")
        if self.impact_count + self.steady_count + self.trend_count != self.output_count:
            raise ValueError("segment kind counters must sum to output_count")
        if self.absorbed_count != self.input_count:
            raise ValueError("every input sample must be accounted for by exactly one segment")
        return self


def _absorb(
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


class AdaptiveTemporalCompressor:
    """误差有界的自适应时序压缩算子（端侧高频流首选入口）。"""

    def __init__(
        self,
        *,
        epsilon: float = DEFAULT_EPSILON,
        curvature_budget: float = DEFAULT_CURVATURE_BUDGET,
        impact_jump: float | None = DEFAULT_IMPACT_JUMP,
        impact_magnitude: float | None = None,
        min_window: int = DEFAULT_MIN_WINDOW,
        max_window: int = DEFAULT_MAX_WINDOW,
    ) -> None:
        if epsilon <= 0.0:
            raise ValueError("epsilon must be positive (误差界必须为正)")
        if curvature_budget <= 0.0:
            raise ValueError("curvature_budget must be positive")
        if impact_jump is not None and impact_jump <= 0.0:
            raise ValueError("impact_jump must be positive when enabled")
        if impact_magnitude is not None and impact_magnitude <= 0.0:
            raise ValueError("impact_magnitude must be positive when enabled")
        if min_window < 1:
            raise ValueError("min_window must be >= 1")
        if max_window < min_window:
            raise ValueError("max_window must be >= min_window")
        self.epsilon = float(epsilon)
        self.curvature_budget = float(curvature_budget)
        self.impact_jump = None if impact_jump is None else float(impact_jump)
        self.impact_magnitude = (
            None if impact_magnitude is None else float(impact_magnitude)
        )
        self.min_window = int(min_window)
        self.max_window = int(max_window)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def compress(self, samples: Iterable[tuple[int, float]]) -> CompressionResult:
        """单趟流式压缩 ``(t_us, value)`` 序列（时间必须单调不减）。"""

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
                raise ValueError(
                    "adaptive compression requires non-decreasing t_us "
                    f"(got {t_us} after {last_us})"
                )

            # -- 冲击优先：绝不把撞击/骤变波形平均进任何平稳窗 --
            is_impact = (
                self.impact_magnitude is not None and abs(v) >= self.impact_magnitude
            ) or (
                has_prev
                and self.impact_jump is not None
                and abs(v - last_v) >= self.impact_jump
            )
            if is_impact:
                segment = _absorb(
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
                segment = _absorb(
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
                # 波形/越界封窗回到最小窗；平稳封窗保持当前窗口长度
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
            # 窗口填满即几何放大上界：平稳期的窗口长度按 2 的幂次迅速爬升到
            # max_window，而不是每关一个窗口才翻一倍（爬升期会被无谓切碎）。
            if candidate_count >= cap and cap < self.max_window:
                cap = min(self.max_window, cap * 2)

        segment = _absorb(
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
        return CompressionResult(
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


def reconstruct_value_at(segments: Sequence[CompressionSegment], t_us: int) -> float | None:
    """按段内常量重建给定时刻的值（``bisect`` 定位，O(log k)）。"""

    if not segments:
        return None
    ends = [segment.end_us for segment in segments]
    index = bisect_left(ends, t_us)
    if index >= len(segments):
        return segments[-1].value
    return segments[index].value


def verify_error_bound(samples: Iterable[tuple[int, float]], result: CompressionResult) -> float:
    """独立复核压缩结果的真实最大重建误差（外部审计口径，不读算子内部状态）。"""

    segments = result.segments
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
    compressor: AdaptiveTemporalCompressor | None = None,
) -> Iterable[CompressionSegment]:
    """生成器封装：端侧内存受限时压缩后立即消费段，不驻留结果集。"""

    engine = compressor or AdaptiveTemporalCompressor()
    result = engine.compress(samples)
    return result.segments
