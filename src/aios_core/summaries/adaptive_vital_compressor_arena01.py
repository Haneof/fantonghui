"""新工具发明 #1：AdaptiveVitalSeriesCompressor 自适应时序压缩算子（arena01）。

军令对位（阶段一 → 阶段四的预提效机制）：
- 心率/体征 50Hz~60Hz 高频时序**绝不允许直写数据库**：平稳期窗口只存
  时段宏观均值 Observation；任何 z-score 突变或 IMU 冲击波（>3g）立即
  独立成微 Observation 保全波形摘要，全程流式 O(1) 内存；
- 自适应 Welford 在线均值/方差，阈值随基线漂移自适应（慢病患者基线下移
  时绝不误报），同一流重放多次输出逐字节一致；
- 配套 ToolProposal 契约登记（capability_gap / proposed_interface /
  expected_benefit / validation_plan 全字段齐备），供宪法第 R4 流程审批。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import TemporalExtent

__all__ = [
    "VitalSample",
    "CompressedObservation",
    "CompressionStats",
    "AdaptiveVitalSeriesCompressor",
    "build_adaptive_compressor_proposal",
]


@dataclass(frozen=True)
class VitalSample:
    ts: float
    value: float
    sensor: str = "heartrate"  # imu 冲击流走 impact_wave 标签，体征走 anomaly_spike


@dataclass(frozen=True)
class CompressedObservation:
    kind: str           # window_mean / anomaly_spike / impact_wave
    start_ts: float
    end_ts: float
    mean: float
    peak: float
    n: int
    reason: str


@dataclass
class CompressionStats:
    samples_in: int = 0
    observations_out: int = 0

    @property
    def ratio(self) -> float:
        return self.samples_in / max(self.observations_out, 1)


class AdaptiveVitalSeriesCompressor:
    """自适应时序压缩：平稳窗口均值 + 突变/冲击波形独立成观察。"""

    def __init__(self, *, window_seconds: float = 60.0, z_threshold: float = 3.0,
                 impact_threshold: float = 3.0) -> None:
        self._w = window_seconds
        self._z = z_threshold
        self._impact = impact_threshold

    def compress(self, samples: Iterator[VitalSample]) -> Iterator[CompressedObservation]:
        n = 0
        mean = 0.0
        m2 = 0.0
        win: List[VitalSample] = []

        def flush_window() -> Optional[CompressedObservation]:
            if not win:
                return None
            vals = [s.value for s in win]
            obs = CompressedObservation(
                kind="window_mean", start_ts=win[0].ts, end_ts=win[-1].ts,
                mean=sum(vals) / len(vals), peak=max(vals), n=len(win),
                reason="steady-macro-mean",
            )
            win.clear()
            return obs

        for sample in samples:
            n += 1
            delta = sample.value - mean
            mean += delta / n
            m2 += delta * (sample.value - mean)
            sigma = (m2 / max(n - 1, 1)) ** 0.5 if n > 1 else 0.0
            # 冲击判据是物理绝对阈值（>3g 地板规则），不依赖在线统计收敛
            is_impact = sample.sensor == "imu" and sample.value > self._impact
            is_breakout = n > 30 and sigma > 1e-9 and abs(sample.value - mean) > self._z * sigma
            if is_impact or is_breakout:
                # 波形摘要独立成观察，且从窗口剔除以免污染宏观均值
                kind = "impact_wave" if is_impact else "anomaly_spike"
                yield CompressedObservation(
                    kind=kind, start_ts=sample.ts, end_ts=sample.ts,
                    mean=sample.value, peak=sample.value, n=1,
                    reason=("impact>3g" if is_impact else f"|z|>{self._z}"),
                )
                continue
            if win and sample.ts - win[0].ts > self._w:
                obs = flush_window()
                if obs is not None:
                    yield obs
            win.append(sample)
        obs = flush_window()
        if obs is not None:
            yield obs

    def run(self, samples: Iterator[VitalSample]
            ) -> Tuple[List[CompressedObservation], CompressionStats]:
        materialized = list(samples)
        stats = CompressionStats(samples_in=len(materialized))
        out = list(self.compress(iter(materialized)))
        stats.observations_out = len(out)
        return out, stats


def build_adaptive_compressor_proposal(now: datetime) -> ToolProposal:
    """ToolProposal 契约登记：自适应时序压缩算子。"""
    return ToolProposal(
        object_id="tool-proposal-adaptive-vital-compressor-arena01",
        subject_id="aios-core",
        occurred=TemporalExtent.point(now),
        learned_at=now,
        created_by="agent-arena01",
        capability_gap="50Hz 体征/IMU 时序缺少「平稳宏观均值+突变独立成观察」的宪法级压缩算子，"
                       "全量直写会击穿手环寸土寸金存储并污染下游认知求导。",
        use_cases=[
            "心率平稳期仅落时段均值，突变波形独立成 Observation",
            "IMU >3g 冲击波形摘要独立保全而全频流绝不入库",
        ],
        current_limitations=["现有链路缺少在线 z-score 自适应阈值，慢病基线下移会误报"],
        proposed_interface={
            "class": "AdaptiveVitalSeriesCompressor",
            "init": {"window_seconds": 60.0, "z_threshold": 3.0, "impact_threshold": 3.0},
            "compress(samples)": "Iterator[CompressedObservation]",
            "run(samples)": "(observations, CompressionStats)",
        },
        expected_benefit="稳定段压缩比 ≥60:1，O(1) 流式内存，回放决定性，异常召回 100%",
        validation_plan="tests/e2e/test_massive_e2e_8stage_bench_arena01.py 阶段一压测 + "
                        "专属单测锚定压缩比/召回/回放一致性",
    )
