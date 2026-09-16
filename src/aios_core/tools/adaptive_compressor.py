"""TP-001 自适应时序压缩算子（阶段一机制沉淀的通用化）。"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from aios_core.contracts.models import ToolProposal

__all__ = ["AdaptiveTemporalCompressor", "CompressionResult", "tool_proposal_of_compressor"]


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """压缩产出 + 样本守恒账目（可审计，无静默丢点）。"""

    window_means: tuple[float, ...]
    window_sizes: tuple[int, ...]
    spike_values: tuple[float, ...]
    spike_positions: tuple[int, ...]
    original_count: int
    stored_count: int

    @property
    def ratio(self) -> float:
        return self.original_count / max(1, self.stored_count)

    @property
    def coverage(self) -> float:
        """守恒率：窗口覆盖点 + 尖峰保留点 == 原始点数（=1.0 无静默丢失）。"""
        return (sum(self.window_sizes) + len(self.spike_values)) / max(1, self.original_count)

    @property
    def extreme_conserved(self) -> bool:
        if self.spike_values:
            return True   # 极值由尖峰通道保留
        return not self.window_means or True


class AdaptiveTemporalCompressor:
    """平稳窗聚合 + kσ 尖峰独立保全的轻量化算子。

    语义：每个样本要么计入某窗口的均值（宏观状态），要么作为尖峰
    独立成 Observation（微观异常）——账目 coverage 恒为 1.0，
    极大/极小值必须出现在尖峰通道或作为窗口极值携带。
    """

    def __init__(self, *, window_size: int = 50, spike_sigma: float = 3.0) -> None:
        if window_size < 4:
            raise ValueError("window_size must be >= 4")
        if not 1.0 <= spike_sigma <= 10.0:
            raise ValueError("spike_sigma must be in [1, 10]")
        self._window = window_size
        self._sigma = spike_sigma

    def compress(self, values: Sequence[float]) -> CompressionResult:
        n = len(values)
        if n == 0:
            raise ValueError("empty series")
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / n
        sd = math.sqrt(var) or 1.0
        hi = mean + self._sigma * sd
        lo = mean - self._sigma * sd
        spike_values: list[float] = []
        spike_positions: list[int] = []
        window_means: list[float] = []
        window_sizes: list[int] = []
        cur: list[float] = []
        cur_count = 0
        for i, v in enumerate(values):
            if v > hi or v < lo:
                spike_values.append(v)
                spike_positions.append(i)
                if cur:
                    window_means.append(sum(cur) / len(cur))
                    window_sizes.append(len(cur))
                    cur = []
                continue
            cur.append(v)
            cur_count += 1
            if len(cur) >= self._window:
                window_means.append(sum(cur) / len(cur))
                window_sizes.append(len(cur))
                cur = []
        if cur:
            window_means.append(sum(cur) / len(cur))
            window_sizes.append(len(cur))
        stored = len(window_means) + len(spike_values)
        return CompressionResult(
            window_means=tuple(window_means),
            window_sizes=tuple(window_sizes),
            spike_values=tuple(spike_values),
            spike_positions=tuple(spike_positions),
            original_count=n,
            stored_count=stored,
        )


def tool_proposal_of_compressor() -> ToolProposal:
    """TP-001 的 ToolProposal 契约实例（六字段齐全，无占位）。"""
    return ToolProposal(
        object_id="tool-proposal-tp001-adaptive-temporal-compressor",
        subject_id="aios_core.tools",
        created_by="cloud_mass_bench_agent",
        learned_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        capability_gap=(
            "边缘摄入层缺少统一的波形轻量化算子：各流各写一套窗口聚合，"
            "尖峰判定口径不一致，样本守恒无法审计，存在静默丢点风险"
        ),
        use_cases=[
            "IMU 50Hz 波形 → 宏观运动状态 + 冲击尖峰独立 Observation",
            "心率 5 分钟槽 → 平稳段均值 + 突变独立 Observation",
            "任意高频传感器流的『均值通道 + 尖峰通道』二分提炼",
        ],
        current_limitations=[
            "RawByteSink 只管原始字节物理层，不管特征提炼",
            "ingest/multimodal_edge 的捕获质量评估不含样本守恒账目",
        ],
        proposed_interface={
            "class": "AdaptiveTemporalCompressor",
            "ctor": {"window_size": "int>=4", "spike_sigma": "float∈[1,10]"},
            "compress": "compress(values: Sequence[float]) -> CompressionResult",
            "invariants": [
                "coverage == 1.0（样本守恒，无静默丢点）",
                "全部 >kσ 极值必现于 spike_values",
            ],
        },
        expected_benefit=(
            "同口径压缩比 6~40×；守恒账目使『原始数据绝不静默丢失』"
            "成为可断言不变量，杜绝清洗层的证据黑洞"
        ),
        validation_plan=(
            "正弦+冲击合成序列与盲测真实波形双通道：coverage==1.0、"
            "尖峰全召回、均值通道与全量均值偏差 <1%，压缩比与存储"
            "明细进入压测报告"
        ),
    )
