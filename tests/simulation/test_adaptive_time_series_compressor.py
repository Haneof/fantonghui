"""ToolProposal #1 自适应时序压缩算子验收。

1. 高平稳占主流（80%+）的 HR 流压缩比严格 > 3.0；
2. 惊吓/剧变（>4σ）全数保留，零丢失；
3. MADσ 滚动窗口单调自洽（max ≥ min），digest 可复现；
4. 空输入拒绝；微小波动（<0.25bpm）稳定丢弃。
"""

from __future__ import annotations

import random

import pytest

from aios_core.tools.adaptive_time_series_compressor import (
    AdaptiveTimeSeriesCompressor,
    WaveformSample,
)


def _steady_stream(n: int = 2000, *, seed: int = 7) -> list[WaveformSample]:
    rng = random.Random(seed)
    base = 72.0
    return [
        WaveformSample(ts_ms=i * 40, value=base + rng.gauss(0, 0.05)) for i in range(n)
    ]


def test_steady_stream_compresses_hard_and_reproducible() -> None:
    samples = _steady_stream()
    report = AdaptiveTimeSeriesCompressor.compress(samples)
    assert report.raw_count == len(samples)
    assert 0 < report.kept_count < report.raw_count // 3
    assert report.compression_ratio > 3.0
    assert 0 <= report.rolling_mad_sigma_min <= report.rolling_mad_sigma_max
    assert (
        AdaptiveTimeSeriesCompressor.compress(samples).digest_hex == report.digest_hex
    )


def test_shock_window_and_above_4sigma_preserved() -> None:
    samples = _steady_stream()
    # 取第 1000 个伪踏：跌落——必须被 >4σ 条件的判定保留
    shocked = list(samples)
    shocked[1000] = WaveformSample(ts_ms=shocked[1000].ts_ms, value=95.0)
    shocked[1001] = WaveformSample(ts_ms=shocked[1001].ts_ms, value=96.5)
    report = AdaptiveTimeSeriesCompressor.compress(shocked)
    kept_times = {sample.ts_ms for sample in report.kept_samples}
    assert {40 * 1000, 40 * 1001} <= kept_times
    # 逃检测：压缩比降低证明更多样本被保
    assert (
        report.compression_ratio
        < AdaptiveTimeSeriesCompressor.compress(samples).compression_ratio
    )
    assert report.rolling_mad_sigma_max >= report.rolling_mad_sigma_min


def test_empty_and_microfluctuation_rejected() -> None:
    with pytest.raises(ValueError):
        AdaptiveTimeSeriesCompressor.compress([])
    flat = [
        WaveformSample(ts_ms=i * 40, value=70.0 + 0.05 * (i % 2)) for i in range(500)
    ]
    report = AdaptiveTimeSeriesCompressor.compress(flat)
    assert report.kept_count <= 2, f"浅波没必要被保，獳得太实: {report.kept_count}"
