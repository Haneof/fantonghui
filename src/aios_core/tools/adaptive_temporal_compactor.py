"""自适应时序压缩算子 (AdaptiveTemporalCompactor) —— ToolProposal TLP-C01 纯代码实现。

宪法出处：第 33 条（心率平稳期仅存时段均值、突变独立成 Observation、50Hz 禁止直写）、
第 33.5 条（tombstone 归档可开关不可关）。

解决的问题（能力缺口）：

    手环端侧 24×7 的低频体征流（HR/HRV/SpO2/体动四通道）在"平稳态"与"剧变态"
    之间反复切换。固定窗口压缩（例如恒 2 小时的均值窗）有两个天然缺陷：

    1) 窗口内一旦夹带一次 15 跳的早期瞬变，整窗被均值抹平，那个"异常冲击波形"被
       统计平均稀释，违反第 33 条"突变波形独立成 Observation"；
    2) 平稳段与剧变段交替出现时，固定窗口会无限期缓冲（等不到安静的 2 小时），
       造成心跳慢变化信息被延迟。

机制（三层自适应漏斗）：

    * ``NormSensor``：机械规则判定正常值（无大模型）——按通道的个体化基线 + 公差
      带的偏离分，只产生 [0,1] 量级的偏离分；
    * ``BreakDetector``：剧变评分（偏离分 + 一阶跳变幅度）越过阈值即强制"切段排水"，
      突变前后各自独立成 Observation，突变瞬时快照带 spike 标记；
    * ``ChunkSpec``：平稳段由 ``max_span_seconds``（端侧算力预算上限）触发封段，
      输出时段均值/min/max，绝不输出 50Hz 原始序列。

纯确定性、零大模型调用、O(1) 内存驻留（只保留当前段聚合器，不还流全序列）。

各通道 compactor 实例的基线由 ``NormSensor`` 静态定义；任何需要个体化的场景在构造
实例时传入 ``CompactionConfig``，不改代码路径（与 runtime_profile 哲学一致）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aios_core.contracts.time import as_utc, utc_now

__all__ = [
    "AdaptiveTemporalCompactor",
    "BreakDetector",
    "ChunkSpec",
    "CompactedChunk",
    "CompactionConfig",
    "HeartRateCompactor",
    "ImuMagnitudeCompactor",
    "NormSensor",
    "Spo2Compactor",
]

#: 人群上限：静息心率硬上限 / SpO2 硬下限 / 体动 g 硬上限（机械规则，非大模型）。


@dataclass(frozen=True)
class CompactionConfig:
    """端侧压缩参数（band_v0：算力预算内自适应，切勿当作可绕过第 33 条的开关）。"""

    max_span_seconds: float = 7200.0        # 平稳段最长聚合窗口（宪法第 33 条原文）
    jump_hard_break_bpm: float = 15.0       # 心率一阶跳变硬阈值（绝对值）
    break_threshold: float = 0.60           # 剧变评分阈值（越过即切段排水）
    derivative_free: bool = True            # 保持真：本算子不做导数，导数见认知层


@dataclass(frozen=True)
class NormSensor:
    """通道规范度判定：个体基线带内的偏离分，机械可判、零模型调用。"""

    baseline: float
    tolerance: float

    def anomaly_score(self, value: float) -> float:
        if self.tolerance <= 0.0:
            return 0.0
        return abs(value - self.baseline) / self.tolerance


class BreakDetector:
    """剧变检测器：规范度 + 一阶跳变；越界时输出突变快照。"""

    def __init__(self, config: CompactionConfig) -> None:
        self._config = config
        self._last_value: float | None = None

    def evaluate(self, value: float, sensor: NormSensor) -> tuple[bool, float]:
        """返回 (是否剧变, 剧变评分)。评分 = 偏离分 + 归一化一阶跳变幅度。"""
        base = sensor.anomaly_score(value)
        jump = 0.0 if self._last_value is None else abs(value - self._last_value)
        self._last_value = value
        score = base + jump / self._config.jump_hard_break_bpm
        return score >= self._config.break_threshold, round(score, 4)


@dataclass(frozen=True)
class CompactedChunk:
    """一个已封段的聚合 Observation：绝不包含 50Hz 原始序列。"""

    channel: str
    started_at: datetime
    ended_at: datetime
    avg: float
    min: float
    max: float
    sample_count: int
    kind: str  # "steady_average" | "abrupt_spike"
    note: str = ""

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "avg": round(self.avg, 3),
            "min": round(self.min, 3),
            "max": round(self.max, 3),
            "sample_count": self.sample_count,
        }
        if self.kind == "abrupt_spike":
            payload["spike"] = True
        return payload


@dataclass(frozen=True)
class ChunkSpec:
    """把"平稳聚合"与"突变快照"两类产出物统一成可入库的形状。"""

    channel: str
    span_seconds: float
    chunks: tuple[CompactedChunk, ...]
    raw_samples_dropped: int

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(chunk.kind for chunk in self.chunks)


class AdaptiveTemporalCompactor:
    """三层自适应压缩器：单个通道实例，内存 O(1)，零大模型调用。

    ``feed`` 是唯一入口：喂入一条样本，封段时返回 :class:`ChunkSpec`，否则 None。
    平稳段按 ``max_span_seconds`` 封段（时段均值），剧变点立刻"切段排水 + 突变快照"。
    """

    #: 通道级机械规则基线（类属性：实例级可整体覆盖为自定义 CompactionConfig 不改路径）。
    channel: str = "heart_rate"
    _SENSOR = NormSensor(baseline=72.0, tolerance=18.0)

    def __init__(self, config: CompactionConfig | None = None) -> None:
        self._config = config or CompactionConfig()
        self._break = BreakDetector(self._config)
        self._sum = 0.0
        self._min = float("inf")
        self._max = float("-inf")
        self._count = 0
        self._started_at: datetime | None = None
        self._last_at: datetime | None = None
        self._llm_calls = 0
        self._segments_emitted = 0
        self._steady_emitted = 0
        self._spikes_emitted = 0
        self._raw_dropped = 0

    # -- 审计只读属性 --------------------------------------------------

    @property
    def derivative_free(self) -> bool:
        return self._config.derivative_free

    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    @property
    def segments_emitted(self) -> int:
        return self._segments_emitted

    @property
    def spikes_emitted(self) -> int:
        return self._spikes_emitted

    @property
    def raw_samples_dropped_total(self) -> int:
        return self._raw_dropped

    @property
    def pending_samples(self) -> int:
        return self._count

    # -- 主入口 --------------------------------------------------------

    def feed(self, value: float, *, now: datetime | None = None) -> ChunkSpec | None:
        """喂入一条样本；封段时返回 ChunkSpec，否则 None。0 大模型调用。"""
        at = as_utc(now or utc_now(), "at")
        broken, _score = self._break.evaluate(value, self._SENSOR)

        if broken:
            emitted: list[CompactedChunk] = []
            span_before = self._span_seconds(at)
            if self._count > 0:
                emitted.extend(self._drain_steady(at))
            emitted.append(self._spike_chunk(value, at))
            self._segments_emitted += 1
            self._spikes_emitted += 1
            self._raw_dropped += self._count  # 突变前已聚合样本自然升维，不再逐条回放
            self._started_at = at
            self._last_at = at
            return ChunkSpec(
                channel=self.channel,
                span_seconds=span_before,
                chunks=tuple(emitted),
                raw_samples_dropped=self._raw_dropped,
            )

        if self._started_at is None:
            self._started_at = at
        self._accumulate(value)
        self._last_at = at
        self._raw_dropped += 1
        if self._span_seconds(at) >= self._config.max_span_seconds:
            chunks = self._drain_steady(at)
            self._segments_emitted += 1
            self._steady_emitted += 1
            return ChunkSpec(
                channel=self.channel,
                span_seconds=self._config.max_span_seconds,
                chunks=tuple(chunks),
                raw_samples_dropped=self._raw_dropped,
            )
        return None

    # -- 内部 ----------------------------------------------------------

    def _accumulate(self, value: float) -> None:
        self._sum += value
        self._min = min(self._min, value)
        self._max = max(self._max, value)
        self._count += 1

    def _span_seconds(self, at: datetime) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, (at - self._started_at).total_seconds())

    def _drain_steady(self, at: datetime) -> list[CompactedChunk]:
        if self._count == 0 or self._started_at is None:
            return []
        ended = self._last_at or at
        chunk = CompactedChunk(
            channel=self.channel,
            started_at=self._started_at,
            ended_at=ended,
            avg=self._sum / self._count,
            min=self._min,
            max=self._max,
            sample_count=self._count,
            kind="steady_average",
        )
        self._reset_segment_only()
        return [chunk]

    def _reset_segment_only(self) -> None:
        self._sum = 0.0
        self._min = float("inf")
        self._max = float("-inf")
        self._count = 0
        self._started_at = None

    def _spike_chunk(self, value: float, at: datetime) -> CompactedChunk:
        return CompactedChunk(
            channel=self.channel,
            started_at=at,
            ended_at=at,
            avg=value,
            min=value,
            max=value,
            sample_count=1,
            kind="abrupt_spike",
            note="第33条突变波形：独立成 Observation，仅存宏观统计与异常冲击摘要",
        )


class HeartRateCompactor(AdaptiveTemporalCompactor):
    """心率通道实例（命名体贴 API：平稳均值 / 突变独立成 Observation）。"""

    channel = "heart_rate"
    _SENSOR = NormSensor(baseline=72.0, tolerance=18.0)


class Spo2Compactor(AdaptiveTemporalCompactor):
    """血氧通道实例。"""

    channel = "spo2"
    _SENSOR = NormSensor(baseline=98.0, tolerance=6.0)


class ImuMagnitudeCompactor(AdaptiveTemporalCompactor):
    """体动幅值通道实例：只提取宏观运动状态与异常冲击波形（50Hz 严禁直写）。"""

    channel = "imu_g"
    _SENSOR = NormSensor(baseline=0.15, tolerance=1.0)
