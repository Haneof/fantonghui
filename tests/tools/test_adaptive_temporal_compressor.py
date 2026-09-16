"""自适应时序压缩算子（TLP-ATC-001）：误差上界、冲击保真、窗口增长。"""

from __future__ import annotations

import math
import random

import pytest

from aios_core.tools.adaptive_temporal_compressor import (
    AdaptiveTemporalCompressor,
    compress_stream_iter,
    reconstruct_value_at,
    verify_error_bound,
)


def _steady(count: int, value: float = 70.0, step_us: int = 1_000_000) -> list[tuple[int, float]]:
    return [(index * step_us, value) for index in range(count)]


def test_steady_signal_collapses_and_bounds_the_error() -> None:
    engine = AdaptiveTemporalCompressor(epsilon=2.0, curvature_budget=4.0)
    samples = _steady(7_200)
    result = engine.compress(samples)
    assert result.input_count == 7_200
    assert result.output_count <= 10
    assert result.reduction_ratio > 0.99
    assert verify_error_bound(samples, result) <= 2.0


def test_window_growth_is_geometric_not_fixed_per_sample() -> None:
    engine = AdaptiveTemporalCompressor(epsilon=5.0, curvature_budget=10.0)
    result = engine.compress(_steady(144_000))
    assert result.output_count <= 20
    longest = max(segment.n_samples for segment in result.segments)
    assert longest >= 20_000


def test_impacts_survive_as_single_sample_segments() -> None:
    engine = AdaptiveTemporalCompressor(
        epsilon=0.5, curvature_budget=0.5, impact_jump=None, impact_magnitude=3.0
    )
    samples = [(index * 20_000, 1.0) for index in range(5_000)]
    for index in (100, 2_000, 4_000):
        samples[index] = (samples[index][0], 5.5)
    result = engine.compress(samples)
    assert result.impact_count == 3
    impacts = [segment for segment in result.segments if segment.segment_kind == "impact"]
    assert [segment.value for segment in impacts] == [5.5, 5.5, 5.5]


def test_monotone_ramp_is_not_flattened() -> None:
    engine = AdaptiveTemporalCompressor(epsilon=0.4, curvature_budget=0.4)
    samples = [(index * 1_000, float(index)) for index in range(3_000)]
    result = engine.compress(samples)
    assert result.output_count > 25
    assert verify_error_bound(samples, result) <= 0.4


def test_reconstruct_value_at_matches_segment_windows() -> None:
    engine = AdaptiveTemporalCompressor(epsilon=1.0, curvature_budget=1.0)
    samples = _steady(600, value=88.0)
    result = engine.compress(samples)
    for moment in (0, 100, samples[-1][0]):
        assert reconstruct_value_at(result.segments, moment) == pytest.approx(88.0)


def test_compress_stream_iter_returns_the_same_segments() -> None:
    rng = random.Random(7)
    samples = [(index * 1_000, 60.0 + rng.gauss(0, 0.2)) for index in range(4_000)]
    engine = AdaptiveTemporalCompressor(epsilon=0.5, curvature_budget=0.5)
    whole = engine.compress(samples)
    streamed = list(compress_stream_iter(samples, compressor=engine))
    assert whole.output_count == len(streamed)
    assert math.isclose(
        whole.max_abs_error, max(segment.max_abs_error for segment in streamed), rel_tol=1e-9
    )


def test_requires_non_decreasing_time() -> None:
    engine = AdaptiveTemporalCompressor()
    with pytest.raises(ValueError):
        engine.compress([(10, 1.0), (5, 1.0)])
