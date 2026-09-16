"""Unit tests for AdaptiveTimeSeriesCompressor and tool proposal."""

from datetime import datetime, timedelta, timezone
import pytest

from aios_core.contracts.enums import ProposalStatus
from aios_core.tools.proposal_pipeline import ToolProposalPipeline
from aios_core.tools.timeseries_compressor import (
    AdaptiveTimeSeriesCompressor,
    StreamDataPoint,
    create_adaptive_compressor_tool_proposal,
)

UTC = timezone.utc


def test_compressor_steady_and_shock_detection():
    compressor = AdaptiveTimeSeriesCompressor(
        deadband_ratio=0.1,
        max_segment_duration_sec=300.0,
        shock_threshold_g=4.0,
        hr_jump_threshold=20.0,
        accel_spike_threshold=0.3,
    )

    t0 = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)
    points = []

    # 1. 模拟 100 个平稳期步态 IMU 点 (1.0g ~ 1.05g)
    for i in range(100):
        t = t0 + timedelta(seconds=i * 0.1)
        points.append(
            StreamDataPoint(
                timestamp=t,
                stream_type="imu_accel",
                value=1.0 + 0.02 * (i % 3),
            )
        )

    # 2. 模拟 1 个楼梯踩空冲击高 G 点 (5.2g)
    t_shock = t0 + timedelta(seconds=10.1)
    points.append(
        StreamDataPoint(
            timestamp=t_shock,
            stream_type="imu_accel",
            value=5.2,
            is_raw_shock=True,
        )
    )

    # 3. 冲击后再平稳 50 个点
    for j in range(50):
        t = t_shock + timedelta(seconds=(j + 1) * 0.1)
        points.append(
            StreamDataPoint(
                timestamp=t,
                stream_type="imu_accel",
                value=1.01,
            )
        )

    segments, inflections, report = compressor.compress_stream(points)

    # 核心断言 1：压缩率 > 90%
    assert report.compression_ratio >= 0.90
    assert report.raw_samples_count == 151
    assert report.compressed_segments_count < 10

    # 核心断言 2：冲击异常 100% 捕获，绝不漏检
    assert report.anomalies_detected >= 1
    shock_segs = [s for s in segments if s.is_anomaly]
    assert len(shock_segs) >= 1
    assert shock_segs[0].max_value >= 5.0
    assert shock_segs[0].anomaly_tag == "IMU_HIGH_G_SHOCK"

    # 核心断言 3：拐点突变产生预警事件
    assert len(inflections) >= 1
    assert any(inf.acceleration > 0 for inf in inflections)


def test_compressor_arrhythmia_and_inflection():
    compressor = AdaptiveTimeSeriesCompressor(hr_jump_threshold=25.0)
    t0 = datetime(2026, 9, 16, 2, 0, tzinfo=UTC)
    points = []

    # 平稳静息心率 (68 bpm)
    for i in range(50):
        t = t0 + timedelta(seconds=i * 2)
        points.append(
            StreamDataPoint(
                timestamp=t,
                stream_type="heart_rate",
                value=68.0 + (i % 2),
            )
        )

    # 突发室性早搏与心动过速 (跳跃至 125 bpm)
    t_spike = t0 + timedelta(seconds=102)
    points.append(
        StreamDataPoint(
            timestamp=t_spike,
            stream_type="heart_rate",
            value=125.0,
        )
    )

    segments, inflections, report = compressor.compress_stream(points)
    assert report.anomalies_detected >= 1
    spike_seg = [s for s in segments if s.anomaly_tag == "ACUTE_ARRHYTHMIA_SPIKE"]
    assert len(spike_seg) == 1
    assert spike_seg[0].avg_value == 125.0


def test_compressor_tool_proposal_lifecycle():
    pipeline = ToolProposalPipeline()
    proposal = create_adaptive_compressor_tool_proposal(subject_id="user_admin")
    assert proposal.status == ProposalStatus.DRAFT

    pipeline.submit_proposal(proposal)
    assert proposal.status == ProposalStatus.SUBMITTED

    pipeline.review_proposal(proposal.object_id, "approve")
    assert proposal.status == ProposalStatus.APPROVED

    executed = pipeline.execute_proposal(proposal.object_id)
    assert executed.status == ProposalStatus.EXECUTED
    assert pipeline.get_proposal(proposal.object_id).status == ProposalStatus.EXECUTED
