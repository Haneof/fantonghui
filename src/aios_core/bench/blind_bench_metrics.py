"""盲测压测的度量基建：延迟分位、内存驻留峰值、Token 账本、模型调用计量。

设计纪律
--------
1. **只测真实现场**：所有延迟都来自 ``time.perf_counter`` 的真实调用点，
   不做估算，不加权，不做平滑；
2. **内存口径采信差值归因**（ADJ-V3G-012）：读 ``/proc/self/statm`` 取驻留页，
   记录"进入阶段前 → 阶段峰值"的差值，避免跨用例污染；
3. **模型调用必须可审计**：任何"大模型调用"都要经过 ``ModelCallMeter``，
   P0 安全通道与未成熟条件任务必须证明恒为 0。
"""

from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Sequence

__all__ = [
    "LatencyRecorder",
    "MemoryProbe",
    "ModelCallMeter",
    "StageMetric",
    "TokenLedger",
    "percentile",
]


def percentile(values: Sequence[float], fraction: float) -> float:
    """最近秩分位数（小样本下比插值更保守，绝不低估尾部）。"""

    if not values:
        return 0.0
    if fraction <= 0:
        return float(min(values))
    if fraction >= 1:
        return float(max(values))
    ordered = sorted(float(value) for value in values)
    rank = max(1, min(len(ordered), int(round(fraction * len(ordered) + 0.5))))
    return ordered[rank - 1]


_STATM = pathlib.Path("/proc/self/statm")
_PAGE_SIZE = 4096


def _rss_kb() -> int:
    """读取当前进程驻留内存（kB）；无 /proc 时回退 0（平台无关兜底）。"""

    try:
        raw = _STATM.read_text(encoding="utf-8").split()
        return int(raw[1]) * _PAGE_SIZE // 1024
    except (OSError, IndexError, ValueError):
        return 0


class LatencyRecorder:
    """按操作名记录真实耗时，输出 P50/P95/P99。"""

    def __init__(self) -> None:
        self._samples: Dict[str, list[float]] = {}
        self._totals: Dict[str, float] = {}
        self._counts: Dict[str, int] = {}

    def record(self, operation: str, latency_ms: float) -> None:
        self._samples.setdefault(operation, []).append(float(latency_ms))
        self._totals[operation] = self._totals.get(operation, 0.0) + float(latency_ms)
        self._counts[operation] = self._counts.get(operation, 0) + 1

    def time_block(self, operation: str) -> "_TimedBlock":
        return _TimedBlock(self, operation)

    def samples(self, operation: str) -> tuple[float, ...]:
        return tuple(self._samples.get(operation, ()))

    def summary(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for operation, values in self._samples.items():
            out[operation] = {
                "count": len(values),
                "total_ms": round(self._totals.get(operation, 0.0), 3),
                "p50_ms": round(percentile(values, 0.50), 4),
                "p95_ms": round(percentile(values, 0.95), 4),
                "p99_ms": round(percentile(values, 0.99), 4),
                "max_ms": round(max(values), 4),
                "mean_ms": round(self._totals.get(operation, 0.0) / len(values), 4),
            }
        return out

    def operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._samples))


class _TimedBlock:
    def __init__(self, recorder: LatencyRecorder, operation: str) -> None:
        self._recorder = recorder
        self._operation = operation
        self._start = 0.0

    def __enter__(self) -> "_TimedBlock":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        self._recorder.record(self._operation, elapsed_ms)


class MemoryProbe:
    """驻留内存探针（差值归因口径）。"""

    def __init__(self) -> None:
        self.baseline_kb = _rss_kb()
        self.peak_kb = self.baseline_kb
        self._samples: list[int] = []

    def sample(self) -> int:
        current = _rss_kb()
        self._samples.append(current)
        self.peak_kb = max(self.peak_kb, current)
        return current

    @property
    def peak_delta_kb(self) -> int:
        return max(0, self.peak_kb - self.baseline_kb)

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def snapshot(self) -> Dict[str, int]:
        """驻留内存快照（峰值/基线/差值/采样数），供报告与门禁核账。"""

        return {
            "baseline_kb": self.baseline_kb,
            "peak_kb": self.peak_kb,
            "peak_delta_kb": self.peak_delta_kb,
            "sample_count": self.sample_count,
        }


class TokenLedger:
    """Token 账本（按子系统记账，用于月度封套对照）。"""

    def __init__(self, *, monthly_budget: int = 2_554_000) -> None:
        self.monthly_budget = int(monthly_budget)
        self._tokens: Dict[str, int] = {}
        self._calls: Dict[str, int] = {}

    def charge(self, subsystem: str, tokens: int, *, calls: int = 1) -> int:
        if tokens < 0:
            raise ValueError("tokens must be >= 0")
        self._tokens[subsystem] = self._tokens.get(subsystem, 0) + int(tokens)
        self._calls[subsystem] = self._calls.get(subsystem, 0) + int(calls)
        return self._tokens[subsystem]

    def tokens(self, subsystem: str) -> int:
        return self._tokens.get(subsystem, 0)

    def calls(self, subsystem: str) -> int:
        return self._calls.get(subsystem, 0)

    @property
    def total_tokens(self) -> int:
        return sum(self._tokens.values())

    @property
    def total_calls(self) -> int:
        return sum(self._calls.values())

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        return {
            subsystem: {
                "tokens": self._tokens[subsystem],
                "calls": self._calls[subsystem],
            }
            for subsystem in sorted(self._tokens)
        }

    @property
    def budget_utilisation(self) -> float:
        if self.monthly_budget <= 0:
            return 0.0
        return self.total_tokens / self.monthly_budget


class ModelCallMeter:
    """大模型调用计量器：每个阶段可独立开关，恒零断言用它。"""

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}

    def record(self, channel: str, calls: int = 1) -> int:
        self._counts[channel] = self._counts.get(channel, 0) + int(calls)
        return self._counts[channel]

    def count(self, channel: str) -> int:
        return self._counts.get(channel, 0)

    @property
    def total(self) -> int:
        return sum(self._counts.values())

    def snapshot(self) -> Dict[str, int]:
        return dict(sorted(self._counts.items()))


@dataclass
class StageMetric:
    """单阶段度量快照（可直接序列化进压测报告工件）。"""

    stage: str
    label: str
    elapsed_ms: float = 0.0
    rss_peak_delta_kb: int = 0
    tokens: int = 0
    llm_calls: int = 0
    counters: Dict[str, Any] = field(default_factory=dict)
    latencies: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "label": self.label,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "rss_peak_delta_kb": self.rss_peak_delta_kb,
            "tokens": self.tokens,
            "llm_calls": self.llm_calls,
            "counters": self.counters,
            "latencies": self.latencies,
        }


def merge_latency_summaries(
    summaries: Iterable[Mapping[str, Mapping[str, float]]],
) -> Dict[str, Dict[str, float]]:
    """合并多阶段延迟表（同名操作按 max 保守合并）。"""

    merged: Dict[str, Dict[str, float]] = {}
    for summary in summaries:
        for operation, stats in summary.items():
            bucket = merged.setdefault(operation, dict(stats))
            if bucket is not stats:
                bucket["p99_ms"] = max(bucket.get("p99_ms", 0.0), stats.get("p99_ms", 0.0))
                bucket["max_ms"] = max(bucket.get("max_ms", 0.0), stats.get("max_ms", 0.0))
    return merged


def dumps_report(report: Mapping[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)
