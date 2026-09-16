"""海量吞吐极限压测验收测试（CI 冒烟档）。

诚实性纪律：本测试绝不自编 latency 数字，数字必须从同一进程真实执行中采样而来。
因此这里只对"压测器能跑、且报告里没有任何伪造字段"做严格断言；数字本身由
``python -m aios_core.simulation.mass_stress --scale full`` 在验收沙箱复跑。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios_core.simulation.mass_stress import (
    CI_SCALE,
    StreamScale,
    run_mass_stress,
)


@pytest.fixture()
def stress_report(tmp_path: Path) -> dict:
    scale = StreamScale(target_records=1500, commit_batch=400, query_fan=6, pyramid_events=40)
    return run_mass_stress(tmp_path / "stress.db", scale)


def test_stress_report_has_latency_distributions(stress_report: dict) -> None:
    lat = stress_report["latency_ms"]
    for key in ("ingest_commit_ms", "co_search_ms", "pyramid_drill_ms"):
        assert lat[key]["count"] > 0, f"{key} 无采样"


def test_stress_report_compression_ratio_honest(stress_report: dict) -> None:
    """原始 3 条流压成宏观观测：压缩比有实实在在的原始样本账目。"""
    tp = stress_report["throughput"]
    assert tp["raw_samples_generated"] == 1500 * 3
    assert tp["observations_committed"] < tp["raw_samples_generated"]
    assert tp["raw_compression_ratio"] > 1.0


def test_stress_report_raw_bytes_zero_retained(stress_report: dict) -> None:
    assert stress_report["throughput"]["raw_bytes_sink_retained"] == 0


def test_stress_report_memory_peak_recorded(stress_report: dict) -> None:
    assert stress_report["memory"]["peak_rss_mb"] > 0.0


def test_ci_scale_present() -> None:
    assert CI_SCALE.target_records > 0
