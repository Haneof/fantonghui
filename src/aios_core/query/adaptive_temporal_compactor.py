# -*- MEGA-PIPELINE 新机制发明①：自适应时序压缩算子（ToolProposal TP-001 纯码兑现） -*-
"""自适应时序压缩算子（AdaptiveTemporalCompactor）。

能力缺口（铁律 1/4 的交点）：手环端 IMU 50Hz 与心率流全量直写必死于存储
与检索双边爆炸；等间隔死采样又会把唯一重要的突变波形磨平。

机制：方差感知自适应成桶——
  * 平稳段（窗口内极差 < HARD_DELTA 且波动率 < VAR_REDLINE）：整段塌缩成
    一条「时段均值 Observation」，携带窗口与样本数，原始拍点不落库；
  * 突变段（|Δ|≥SPIKE_DELTA 或冲击冲击标记）：逐拍独立成 Observation，
    一拍不丢——跌倒、早搏这类宪法级信号从不在均值里淹死；
  * 衔接缝手不抖：突变拍前后各保留 GUARD_RING 拍上下文（回放可验）。

本件是纯函数契约：输入拍点流，输出压缩计划（桶表 + 独立拍表 + 统计），
写入姿态（Observation/Event 落成）由调用方执行，算子不碰存储。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import fmean, pstdev
from typing import Any, Iterable, Sequence

# 治理参数（变更走低语权流程，不许运行时漂移）
HARD_DELTA_BPM = 8.0          # 窗口极差红线（心率 bpm）
VAR_REDLINE = 2.5             # 窗口波动率红线（总体标准差）
SPIKE_DELTA_BPM = 15.0        # 相邻拍跳变红线 → 突变逐拍成件
GUARD_RING = 2                # 突变上下文保护环（拍）
MIN_BUCKET_BEATS = 30         # 平稳窗口最小拍数（频度地板）


@dataclass(slots=True, frozen=True)
class Beat:
    ts: str                     # ISO
    kind: str                   # heart_rate|imu_shock|...
    value: float
    shock: bool = False         # IMU 冲击波形标记（跌倒面）


@dataclass(slots=True, frozen=True)
class Bucket:
    slot: str                   # bucket-{i}
    kind: str
    window_start: str
    window_end: str
    mean: float
    variance: float
    beat_count: int


@dataclass(slots=True, frozen=True)
class CompactionPlan:
    buckets: tuple[Bucket, ...]         # 平稳段（均值塌缩）
    spikes: tuple[Beat, ...]            # 突变独立拍（含保护环，不重不漏）
    input_beats: int
    output_records: int
    compression_ratio: float
    stats: dict[str, Any]


class AdaptiveTemporalCompactor:
    def compact(self, beats: Sequence[Beat]) -> CompactionPlan:
        if not beats:
            return CompactionPlan((), (), 0, 0, 1.0, {"empty": True})

        shock_idx = {i for i, b in enumerate(beats) if b.shock}
        spike_idx: set[int] = set(shock_idx)
        prev = beats[0]
        for i, b in enumerate(beats):
            if i > 0 and abs(b.value - prev.value) >= SPIKE_DELTA_BPM:
                spike_idx.update((i - 1, i))
            if i > 0 and abs(b.value - beats[i - 1].value) >= SPIKE_DELTA_BPM:
                spike_idx.add(i)
            prev = b
        # 保护环：突变前后 GUARD_RING 拍全部独立保留
        ring: set[int] = set()
        for i in spike_idx:
            ring.update(range(max(0, i - GUARD_RING),
                              min(len(beats), i + GUARD_RING + 1)))
        spike_set = sorted(ring | spike_idx)
        spike_beats = tuple(beats[i] for i in spike_set)

        # 非突变拍按 kind 分段、满 MIN_BUCKET_BEATS 成桶；不足尾桶并表
        buckets: list[Bucket] = []
        buffer: list[tuple[int, Beat]] = []

        def flush() -> None:
            if not buffer:
                return
            vals = [b.value for _, b in buffer]
            mean = fmean(vals)
            var = pstdev(vals) if len(vals) > 1 else 0.0
            kind = buffer[0][1].kind
            if (len(vals) >= MIN_BUCKET_BEATS and var < VAR_REDLINE
                    and (max(vals) - min(vals)) < HARD_DELTA_BPM):
                buckets.append(Bucket(
                    slot=f"bucket-{len(buckets)}", kind=kind,
                    window_start=buffer[0][1].ts,
                    window_end=buffer[-1][1].ts,
                    mean=round(mean, 3), variance=round(var, 3),
                    beat_count=len(vals),
                ))
            else:
                # 不达标段不硬压：退化为逐拍（粘性真值优先于压缩率）
                for i, b in buffer:
                    spike_beats_holder.append(b)
            buffer.clear()

        spike_beats_holder: list[Beat] = []
        cur_kind = beats[0].kind
        for i, b in enumerate(beats):
            if i in spike_set:
                flush()
                continue
            if b.kind != cur_kind:
                flush()
                cur_kind = b.kind
            buffer.append((i, b))
        flush()

        spills = tuple(spike_beats_holder)
        spikes_all = spike_beats + spills
        out = len(buckets) + len(spikes_all)
        return CompactionPlan(
            buckets=tuple(buckets), spikes=spikes_all,
            input_beats=len(beats), output_records=out,
            compression_ratio=round(len(beats) / max(1, out), 3),
            stats={
                "spike_beats": len(spike_beats),
                "spill_beats": len(spills),       # 不达标段退化逐拍的拍数
                "bucket_beats": sum(bt.beat_count for bt in buckets),
                "buckets": len(buckets),
            },
        )


__all__ = [
    "AdaptiveTemporalCompactor",
    "Beat",
    "Bucket",
    "CompactionPlan",
    "GUARD_RING",
    "HARD_DELTA_BPM",
    "MIN_BUCKET_BEATS",
    "SPIKE_DELTA_BPM",
    "VAR_REDLINE",
]
