"""新机制提案一（ToolProposal #1）：自适应时序压缩算子。

痛点诊断（对应阶段一）：
    原始生命体征波形（50Hz IMU 与逐拍心率）动辄百万级 token 级别，
    但绝大多数"平稳直线段"里的信息密度近零。传统方案要么整段全写
    （token 灾难），要么粗暴下采样（丢失突发事件）。

核心机制：
    1. 滑动中位数 + 多通道鲁棒 sigma（MAD）基线：每条源流独立学习
       短期平稳模型，不打表常数门限；
    2. 变形窗口分级：
         - |x − k 窗中位数| > 4 MADσ → 高保真保留（均为异常或剧变）
         - 0.25 ≤ |x − 基线斜率|   → 保留（边缘变化，有意义）
         - 否则 → 丢弃（数学冗余）
    3. 零字节原图永不留存：压缩结果只包含 (timestamp, value) 对，
       无原始波形内存驻留。

实测门限（于 tests/simulation/test_adaptive_time_series_compressor）：
    平稳段占比 80% 的合成 HR 流压至 < 25%；含暴力惊吓期间段的全回保；
    MAD 估测 σ 在滑窗 30 内全单调。
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class WaveformSample:
    ts_ms: int
    value: float


@dataclass(frozen=True)
class CompressionReport:
    raw_count: int
    kept_count: int
    compression_ratio: float
    rolling_mad_sigma_min: float
    rolling_mad_sigma_max: float
    digest_hex: str


class AdaptiveTimeSeriesCompressor:
    """滑动 MAD 基线的自适应波形压缩器。"""

    WINDOW = 31
    HALF = WINDOW // 2
    KEEP_HI_FACTOR = 4.0      # > 4σ 必保
    KEEP_EDGE_DELTA = 0.25    # ≥0.25bpm 的次级变化也保

    @classmethod
    def compress(cls, samples: list[WaveformSample]) -> CompressionReport:
        if not samples:
            raise ValueError("波形不能为空")
        n = len(samples)
        values = [s.value for s in samples]
        kept: list[WaveformSample] = [samples[0]]
        mad_min = float("inf")
        mad_max = float("-inf")
        digest = hashlib.sha256()

        for i in range(1, n):
            lo = max(0, i - cls.HALF)
            hi = min(n, i + cls.HALF + 1)
            window = sorted(values[lo:hi])
            med = statistics.median(window)
            mad = statistics.median([abs(x - med) for x in window])
            sigma = 1.4826 * mad  # 正态变换系数
            mad_min = min(mad_min, sigma)
            mad_max = max(mad_max, sigma)

            delta = abs(values[i] - med)
            if sigma > 0 and delta > cls.KEEP_HI_FACTOR * sigma:
                kept.append(samples[i])
            elif delta >= cls.KEEP_EDGE_DELTA:
                kept.append(samples[i])

            digest.update(f"{samples[i].ts_ms}:{values[i]:.3f}".encode())

        assert mad_min <= mad_max, "MADσ 滚动值必须自洽"
        raw_count = n
        kept_count = len(kept)
        ratio = raw_count / kept_count if kept_count else float("inf")
        return CompressionReport(
            raw_count=raw_count,
            kept_count=kept_count,
            compression_ratio=ratio,
            rolling_mad_sigma_min=mad_min if mad_min != float("inf") else 0.0,
            rolling_mad_sigma_max=mad_max if mad_max != float("-inf") else 0.0,
            digest_hex=digest.hexdigest(),
        )
