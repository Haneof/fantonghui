"""AIOS 3.0 自适应时序流压缩与拐点检测算子 (AdaptiveTimeSeriesCompressor).

落实宪法第十章第三十三条（边缘轻量化摄入）、第七章第二十三条（高阶认知导数与拐点检测）：
1. 严禁 50Hz/100Hz 高频物理时序直写主数据库；
2. 平稳期动态聚合为时段均值/方差/极值宏观切片（Piecewise Aggregate Approximation + Deadband）；
3. 突变波形（异常冲击、早搏波峰）无损保留为高精度独立切片；
4. 在流式滑动窗口中在线计算一阶速度(Velocity)与二阶加速度(Acceleration)，精准识别拐点(Inflection)。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aios_core.contracts.enums import ObjectType, ProposalStatus
from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import TemporalExtent, utc_now

UTC = timezone.utc


@dataclass(frozen=True)
class StreamDataPoint:
    """原始时序数据点。"""

    timestamp: datetime
    stream_type: str  # "imu_accel", "heart_rate", "ambient_db", etc.
    value: float
    secondary_values: Dict[str, float] = field(default_factory=dict)
    is_raw_shock: bool = False


@dataclass(frozen=True)
class CompressedTimeSegment:
    """压缩后的时序宏观段。"""

    start_time: datetime
    end_time: datetime
    stream_type: str
    sample_count: int
    min_value: float
    max_value: float
    avg_value: float
    variance: float
    is_anomaly: bool = False
    anomaly_tag: Optional[str] = None


@dataclass(frozen=True)
class InflectionEvent:
    """高阶认知/生理拐点事件。"""

    timestamp: datetime
    stream_type: str
    metric_name: str
    value: float
    velocity: float
    acceleration: float
    severity: str  # "INFO", "WARNING", "CRITICAL_CIRCUIT_BREAKER"


@dataclass
class TimeSeriesCompressionReport:
    """时序压缩总报表。"""

    raw_samples_count: int = 0
    compressed_segments_count: int = 0
    anomalies_detected: int = 0
    inflection_events_count: int = 0
    compression_ratio: float = 0.0
    elapsed_ms: float = 0.0


class AdaptiveTimeSeriesCompressor:
    """端侧高效自适应时序压缩与拐点检测器。"""

    def __init__(
        self,
        deadband_ratio: float = 0.08,
        max_segment_duration_sec: float = 900.0,  # 平稳期最长15分钟聚合成一段
        shock_threshold_g: float = 4.0,  # 冲击加速度阈值 (4g)
        hr_jump_threshold: float = 25.0,  # 心率剧烈突变跳变阈值 (bpm)
        accel_spike_threshold: float = 0.35,  # 恶化加速度陡增阈值
    ) -> None:
        self.deadband_ratio = deadband_ratio
        self.max_segment_duration_sec = max_segment_duration_sec
        self.shock_threshold_g = shock_threshold_g
        self.hr_jump_threshold = hr_jump_threshold
        self.accel_spike_threshold = accel_spike_threshold

    def compress_stream(
        self,
        points: Sequence[StreamDataPoint],
    ) -> Tuple[List[CompressedTimeSegment], List[InflectionEvent], TimeSeriesCompressionReport]:
        """批量流式压缩高频时序流。"""
        import time

        t_start = time.perf_counter()
        if not points:
            return (
                [],
                [],
                TimeSeriesCompressionReport(elapsed_ms=0.0),
            )

        compressed_segments: List[CompressedTimeSegment] = []
        inflection_events: List[InflectionEvent] = []

        # 按 stream_type 分流处理以保持时序自洽
        stream_buckets: Dict[str, List[StreamDataPoint]] = {}
        for p in points:
            stream_buckets.setdefault(p.stream_type, []).append(p)

        for stream_type, s_points in stream_buckets.items():
            s_segments, s_inflections = self._process_single_stream(s_points, stream_type)
            compressed_segments.extend(s_segments)
            inflection_events.extend(s_inflections)

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        raw_count = len(points)
        comp_count = len(compressed_segments)
        comp_ratio = (
            (raw_count - comp_count) / raw_count if raw_count > 0 else 0.0
        )
        anomaly_count = sum(1 for seg in compressed_segments if seg.is_anomaly)

        report = TimeSeriesCompressionReport(
            raw_samples_count=raw_count,
            compressed_segments_count=comp_count,
            anomalies_detected=anomaly_count,
            inflection_events_count=len(inflection_events),
            compression_ratio=comp_ratio,
            elapsed_ms=elapsed_ms,
        )
        return compressed_segments, inflection_events, report

    def _process_single_stream(
        self,
        points: Sequence[StreamDataPoint],
        stream_type: str,
    ) -> Tuple[List[CompressedTimeSegment], List[InflectionEvent]]:
        segments: List[CompressedTimeSegment] = []
        inflections: List[InflectionEvent] = []

        if not points:
            return segments, inflections

        # 状态机缓存
        curr_start = points[0].timestamp
        curr_end = points[0].timestamp
        count = 0
        sum_val = 0.0
        sum_sq = 0.0
        min_val = points[0].value
        max_val = points[0].value
        baseline_val = points[0].value

        prev_val: Optional[float] = None
        prev_time: Optional[datetime] = None
        prev_velocity: Optional[float] = None

        for pt in points:
            val = pt.value
            ts = pt.timestamp

            # 1. 导数与拐点计算 (Velocity & Acceleration)
            if prev_val is not None and prev_time is not None:
                dt_sec = max(0.001, (ts - prev_time).total_seconds())
                vel = (val - prev_val) / dt_sec
                if prev_velocity is not None:
                    accel = (vel - prev_velocity) / dt_sec
                    # 检查加速度拐点突变
                    if abs(accel) >= self.accel_spike_threshold:
                        sev = "CRITICAL_CIRCUIT_BREAKER" if abs(accel) > self.accel_spike_threshold * 2 else "WARNING"
                        inflections.append(
                            InflectionEvent(
                                timestamp=ts,
                                stream_type=stream_type,
                                metric_name=stream_type,
                                value=val,
                                velocity=vel,
                                acceleration=accel,
                                severity=sev,
                            )
                        )
                prev_velocity = vel
            prev_val = val
            prev_time = ts

            # 2. 突变异常识别 (Shock / PVC jump)
            is_shock = False
            anomaly_tag = None
            if stream_type.startswith("imu") and (val >= self.shock_threshold_g or pt.is_raw_shock):
                is_shock = True
                anomaly_tag = "IMU_HIGH_G_SHOCK"
            elif stream_type == "heart_rate" and abs(val - baseline_val) >= self.hr_jump_threshold:
                is_shock = True
                anomaly_tag = "ACUTE_ARRHYTHMIA_SPIKE"

            if is_shock:
                # 若当前已有累积平稳窗口，先将其收拢结算
                if count > 0:
                    avg_v = sum_val / count
                    var_v = max(0.0, (sum_sq / count) - (avg_v * avg_v))
                    segments.append(
                        CompressedTimeSegment(
                            start_time=curr_start,
                            end_time=curr_end,
                            stream_type=stream_type,
                            sample_count=count,
                            min_value=min_val,
                            max_value=max_val,
                            avg_value=avg_v,
                            variance=var_v,
                            is_anomaly=False,
                        )
                    )
                    count = 0
                    sum_val = 0.0
                    sum_sq = 0.0

                # 异常点作为独立 Observation 级别高保真切片保留
                segments.append(
                    CompressedTimeSegment(
                        start_time=ts,
                        end_time=ts,
                        stream_type=stream_type,
                        sample_count=1,
                        min_value=val,
                        max_value=val,
                        avg_value=val,
                        variance=0.0,
                        is_anomaly=True,
                        anomaly_tag=anomaly_tag,
                    )
                )
                baseline_val = val
                curr_start = ts
                curr_end = ts
                continue

            # 3. 平稳期死区聚集 (Deadband + Duration)
            duration_sec = (ts - curr_start).total_seconds()
            deadband_delta = abs(val - baseline_val) / max(1.0, abs(baseline_val))

            if count > 0 and (duration_sec >= self.max_segment_duration_sec or deadband_delta > self.deadband_ratio):
                # 触发段落收拢
                avg_v = sum_val / count
                var_v = max(0.0, (sum_sq / count) - (avg_v * avg_v))
                segments.append(
                    CompressedTimeSegment(
                        start_time=curr_start,
                        end_time=curr_end,
                        stream_type=stream_type,
                        sample_count=count,
                        min_value=min_val,
                        max_value=max_val,
                        avg_value=avg_v,
                        variance=var_v,
                        is_anomaly=False,
                    )
                )
                # 开启新段落
                curr_start = ts
                curr_end = ts
                count = 1
                sum_val = val
                sum_sq = val * val
                min_val = val
                max_val = val
                baseline_val = val
            else:
                # 纳入当前累积窗口
                if count == 0:
                    curr_start = ts
                    min_val = val
                    max_val = val
                    baseline_val = val
                curr_end = ts
                count += 1
                sum_val += val
                sum_sq += val * val
                if val < min_val:
                    min_val = val
                if val > max_val:
                    max_val = val

        # 结算尾部剩余段落
        if count > 0:
            avg_v = sum_val / count
            var_v = max(0.0, (sum_sq / count) - (avg_v * avg_v))
            segments.append(
                CompressedTimeSegment(
                    start_time=curr_start,
                    end_time=curr_end,
                    stream_type=stream_type,
                    sample_count=count,
                    min_value=min_val,
                    max_value=max_val,
                    avg_value=avg_v,
                    variance=var_v,
                    is_anomaly=False,
                )
            )

        return segments, inflections


def create_adaptive_compressor_tool_proposal(
    subject_id: str = "sys_user_0",
    now: Optional[datetime] = None,
) -> ToolProposal:
    """生成符合 ToolProposal 契约的新工具提案。"""
    t_now = now or utc_now()
    return ToolProposal(
        object_id="tp_adaptive_timeseries_compressor",
        subject_id=subject_id,
        occurred=TemporalExtent.point(t_now),
        learned_at=t_now,
        recorded_at=t_now,
        created_by="aios_mind_agent",
        status=ProposalStatus.DRAFT,
        metadata={"category": "edge_processing", "algorithm": "deadband_paa_inflection"},
        capability_gap="高频 50Hz IMU 与连续心率波形直写主存易造成 I/O 阻塞和内存膨胀；常规降采样易漏失冲击与早搏拐点。",
        use_cases=[
            "马拉松备赛及日常办公 50Hz IMU 运动流平滑压缩",
            "深夜通宵心律失常与静息心率突变波形捕获",
            "楼梯踩空与高 G 跌倒冲击瞬间零漏检捕获",
            "身心耗竭度 (Burnout) 与焦虑恶化加速度实时在线计算与熔断预警",
        ],
        current_limitations=[
            "纯 Python 原生列表直存 100 万时序内存消耗超 500MB",
            "大模型无法直接摄入千万级原始时间序列，必须依靠边缘算子先验提纯",
        ],
        proposed_interface={
            "module": "aios_core.tools.timeseries_compressor",
            "class": "AdaptiveTimeSeriesCompressor",
            "methods": ["compress_stream"],
            "inputs": "Sequence[StreamDataPoint]",
            "outputs": "Tuple[List[CompressedTimeSegment], List[InflectionEvent], TimeSeriesCompressionReport]",
        },
        expected_benefit="时序数据压缩率 >= 95%，冲击异常与心律突变 100% 保全，拐点检测耗时 <= 1ms，彻底解放大模型与主库 I/O 压力。",
        validation_plan="在 100 万条高熵生理及运动对抗样本流下进行压测，验证压缩率、漏检率与拐点召回率。",
    )
