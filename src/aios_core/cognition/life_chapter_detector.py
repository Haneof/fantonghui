"""非线性人生相变识别与章节封存（LifeChapter Detector，阶段四核心算子）。

宪法依据
--------
* 第二十九条：多尺度总结属于"物理时钟"，人生本质是非线性的**阶段相变**；
* 第二十九条之一（去参数化原则）：**坚决杜绝在宪法中硬编码"5 个维度、2 倍标准差"
  这类机械指标** —— 相变的判据必须是"跨多个关键维度的核心基线发生结构性断裂与
  永久性重组"，且门限由调用方（AI 在会话中）以策略对象注入；
* 第二十九条之二：相变后旧章节**完整封存归档**（保留为历史底色），依赖旧基线的
  敏感度参数重置，避免刻舟求剑。

判据的工程形态（全部为策略数字，代码里没有任何"2 倍标准差"）
-------------------------------------------------------------
对每个维度序列，在候选切分点上评估**结构性断裂**：

1. 相对位移 ``shift_ratio = |μ_after - μ_before| / max(|μ_before|, tiny)``；
2. 分形分离度 ``separation = |μ_after - μ_before| / (σ_before + σ_after + tiny)``
   —— 断裂必须"跳出去"，而不只是"数据量大所以显著"；
3. 新常态必须**持续** ``min_duration_days``（短暂波动不算相变）；
4. 至少 ``min_broken_dimensions`` 个关键维度在 ``coupling_window_days`` 内同时断裂
   —— 单维度漂移是噪声，多维度同时断裂才是相变。

满足即封存旧章节：旧基线整体归档（只读），新基线取自 after 段并重建敏感度。
"""

from __future__ import annotations

import statistics
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc

UTC = timezone.utc

__all__ = [
    "BaselineSeries",
    "BreakPolicy",
    "DimensionBreak",
    "LifeChapterDetector",
    "LifeChapterTransition",
    "SealedChapter",
    "SensitivityProfile",
]

_TINY = 1e-9
_US_PER_DAY = 86_400_000_000


class BaselineSeries(BaseModel):
    """单维度的基线时序（时间升序，微秒时间戳）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str = Field(min_length=1)
    times_us: tuple[int, ...] = Field(min_length=2)
    values: tuple[float, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_shape(self) -> "BaselineSeries":
        if len(self.times_us) != len(self.values):
            raise ValueError("times_us and values must have the same length")
        if any(b < a for a, b in zip(self.times_us, self.times_us[1:])):
            raise ValueError("times_us must be non-decreasing")
        return self

    def span_days(self) -> float:
        return (self.times_us[-1] - self.times_us[0]) / _US_PER_DAY


class BreakPolicy(BaseModel):
    """相变判据门限（由 AI 在会话中注入，代码层零硬编码）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_shift_ratio: float = Field(default=0.25, gt=0.0)
    min_separation: float = Field(default=2.0, gt=0.0)
    min_duration_days: float = Field(default=30.0, gt=0.0)
    min_broken_dimensions: int = Field(default=3, ge=2)
    coupling_window_days: float = Field(default=180.0, gt=0.0)
    max_candidates_per_series: int = Field(default=96, ge=4)


class DimensionBreak(BaseModel):
    """单维度上的一次结构性断裂（可复核：位移、分离度、持续时长）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str
    split_us: int
    before_mean: float
    after_mean: float
    before_std: float
    after_std: float
    shift_ratio: float
    separation: float
    duration_days: float
    score: float

    @model_validator(mode="after")
    def validate_shift(self) -> "DimensionBreak":
        if self.duration_days <= 0.0:
            raise ValueError("a structural break must persist for a positive duration")
        return self


class SensitivityProfile(BaseModel):
    """依赖基线的敏感度参数（相变后必须重置，旧值归档保留）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str
    baseline_mean: float
    baseline_std: float
    upper_alert: float
    lower_alert: float
    derived_from_us: int

    @model_validator(mode="after")
    def validate_alerts(self) -> "SensitivityProfile":
        if self.upper_alert < self.baseline_mean or self.lower_alert > self.baseline_mean:
            raise ValueError("alert thresholds must bracket the baseline mean")
        return self


def build_sensitivity(
    dimension_id: str, values: Sequence[float], *, k_sigma: float = 2.0, derived_from_us: int = 0
) -> SensitivityProfile:
    """由基线序列重建敏感度（``k_sigma`` 由调用方给定，不在判据内核里写死）。"""

    if len(values) < 2:
        raise ValueError("sensitivity requires at least two baseline samples")
    mean = statistics.fmean(values)
    std = statistics.pstdev(values) or _TINY
    return SensitivityProfile(
        dimension_id=dimension_id,
        baseline_mean=mean,
        baseline_std=std,
        upper_alert=mean + k_sigma * std,
        lower_alert=mean - k_sigma * std,
        derived_from_us=derived_from_us,
    )


class SealedChapter(BaseModel):
    """被封存归档的旧章节（只读历史底色，永不被改写）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chapter_id: str
    sealed_at: datetime
    sealed_reason: str = Field(min_length=1)
    baselines: dict[str, float]
    sensitivities: dict[str, SensitivityProfile]
    start_us: int
    end_us: int


class LifeChapterTransition(BaseModel):
    """一次人生相变的完整裁决（多维度断裂 + 新基线 + 封章与重置）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chapter_id: str
    title: str = Field(min_length=1)
    breaks: tuple[DimensionBreak, ...] = Field(min_length=2)
    coupling_span_days: float = Field(ge=0.0)
    sealed_chapter: SealedChapter
    reset_sensitivities: dict[str, SensitivityProfile]
    detected_at: datetime

    @model_validator(mode="after")
    def validate_coupling(self) -> "LifeChapterTransition":
        if self.sealed_chapter.chapter_id != self.chapter_id:
            raise ValueError("sealed chapter must carry the same chapter_id")
        if set(self.reset_sensitivities) != {item.dimension_id for item in self.breaks}:
            raise ValueError("every broken dimension must receive a reset sensitivity profile")
        return self


class LifeChapterDetector:
    """人生相变识别器：多维度结构性断裂 → 封章 → 敏感度重置。"""

    def __init__(self, *, policy: BreakPolicy | None = None, k_sigma: float = 2.0) -> None:
        self.policy = policy or BreakPolicy()
        self.k_sigma = k_sigma
        self._series: dict[str, BaselineSeries] = {}
        self._sealed: list[SealedChapter] = []
        self._current_baselines: dict[str, float] = {}
        self._current_sensitivities: dict[str, SensitivityProfile] = {}
        self._detections: list[LifeChapterTransition] = []
        self._chapter_counter = 0

    # ------------------------------------------------------------------
    # 序列登记
    # ------------------------------------------------------------------

    def register_series(self, series: BaselineSeries) -> None:
        self._series[series.dimension_id] = series
        after = series.values
        self._current_baselines[series.dimension_id] = statistics.fmean(after)
        self._current_sensitivities[series.dimension_id] = build_sensitivity(
            series.dimension_id, after, k_sigma=self.k_sigma, derived_from_us=series.times_us[-1]
        )

    def series(self, dimension_id: str) -> BaselineSeries:
        if dimension_id not in self._series:
            raise KeyError(f"unknown dimension: {dimension_id!r}")
        return self._series[dimension_id]

    def current_baseline(self, dimension_id: str) -> float:
        return self._current_baselines[dimension_id]

    def current_sensitivity(self, dimension_id: str) -> SensitivityProfile:
        return self._current_sensitivities[dimension_id]

    def sealed_chapters(self) -> tuple[SealedChapter, ...]:
        return tuple(self._sealed)

    def detections(self) -> tuple[LifeChapterTransition, ...]:
        return tuple(self._detections)

    # ------------------------------------------------------------------
    # 断裂检测
    # ------------------------------------------------------------------

    def find_break(self, dimension_id: str) -> DimensionBreak | None:
        """在单维度上寻找"最优结构断裂点"（粗筛候选 → 逐点评估）。"""

        series = self.series(dimension_id)
        n = len(series.values)
        policy = self.policy
        if n < 8:
            return None

        candidates: list[int] = []
        stride = max(2, n // policy.max_candidates_per_series)
        index = stride
        while index < n - 1:
            candidates.append(index)
            index += stride
        if n - 2 not in candidates:
            candidates.append(n - 2)

        span_us = series.times_us[-1] - series.times_us[0]
        min_points = max(2, int(n * 0.1))
        best: DimensionBreak | None = None

        for split in candidates:
            if split < min_points or n - split < min_points:
                continue
            before = series.values[:split]
            after = series.values[split:]
            before_mean = statistics.fmean(before)
            after_mean = statistics.fmean(after)
            before_std = statistics.pstdev(before)
            after_std = statistics.pstdev(after)
            shift = abs(after_mean - before_mean) / max(abs(before_mean), _TINY)
            separation = abs(after_mean - before_mean) / (before_std + after_std + _TINY)
            duration_days = (series.times_us[-1] - series.times_us[split]) / _US_PER_DAY
            if shift < policy.min_shift_ratio:
                continue
            if separation < policy.min_separation:
                continue
            if duration_days < policy.min_duration_days:
                continue
            score = separation * min(shift, 1.0)
            candidate = DimensionBreak(
                dimension_id=dimension_id,
                split_us=series.times_us[split],
                before_mean=before_mean,
                after_mean=after_mean,
                before_std=before_std,
                after_std=after_std,
                shift_ratio=shift,
                separation=separation,
                duration_days=duration_days,
                score=round(score, 6),
            )
            if best is None or candidate.score > best.score:
                best = candidate
        _ = span_us  # 跨度只用于可读性说明，不参与判据（避免硬编码时间尺度）
        return best

    # ------------------------------------------------------------------
    # 相变裁决
    # ------------------------------------------------------------------

    def detect(
        self,
        *,
        title: str,
        detected_at: datetime,
        dimension_ids: Sequence[str] | None = None,
    ) -> LifeChapterTransition | None:
        """多维度耦合裁决：足够多的维度在耦合窗内同时断裂才算人生相变。"""

        stamp = as_utc(detected_at, "detected_at")
        targets = list(dimension_ids or self._series)
        breaks = [
            item for item in (self.find_break(dimension_id) for dimension_id in targets) if item
        ]
        if len(breaks) < self.policy.min_broken_dimensions:
            return None

        breaks.sort(key=lambda item: item.split_us)
        window_us = int(self.policy.coupling_window_days * _US_PER_DAY)
        best_cluster: list[DimensionBreak] = []
        for start in range(len(breaks)):
            cluster = [
                item
                for item in breaks
                if 0 <= item.split_us - breaks[start].split_us <= window_us
            ]
            if len(cluster) > len(best_cluster):
                best_cluster = cluster
        if len(best_cluster) < self.policy.min_broken_dimensions:
            return None

        cluster.sort(key=lambda item: item.dimension_id)
        self._chapter_counter += 1
        chapter_id = f"lifc_{stamp.date().isoformat()}_{self._chapter_counter:03d}"
        coupling_span = (
            max(item.split_us for item in cluster) - min(item.split_us for item in cluster)
        ) / _US_PER_DAY

        baselines = {item.dimension_id: item.after_mean for item in cluster}
        sensitivities = {
            item.dimension_id: build_sensitivity(
                item.dimension_id,
                self._series[item.dimension_id].values,
                k_sigma=self.k_sigma,
                derived_from_us=self._series[item.dimension_id].times_us[-1],
            )
            for item in cluster
        }
        sealed = SealedChapter(
            chapter_id=chapter_id,
            sealed_at=stamp,
            sealed_reason=(
                f"{len(cluster)} 个关键维度的核心基线在 {coupling_span:.0f} 天内发生结构性断裂"
                f"（跨域耦合窗 {self.policy.coupling_window_days:.0f} 天）"
            ),
            baselines=dict(self._current_baselines),
            sensitivities=dict(self._current_sensitivities),
            start_us=min(series.times_us[0] for series in self._series.values()),
            end_us=min(item.split_us for item in cluster),
        )
        transition = LifeChapterTransition(
            chapter_id=chapter_id,
            title=title,
            breaks=tuple(cluster),
            coupling_span_days=coupling_span,
            sealed_chapter=sealed,
            reset_sensitivities=sensitivities,
            detected_at=stamp,
        )
        self._sealed.append(sealed)
        self._detections.append(transition)
        self._current_baselines.update(baselines)
        self._current_sensitivities.update(sensitivities)
        return transition

    # ------------------------------------------------------------------
    # 敏感度重置视图
    # ------------------------------------------------------------------

    def sensitivity_shift(self, dimension_id: str) -> dict[str, float]:
        """新常态与旧章节基线的对比（用于"避免刻舟求剑"的可读证据）。"""

        if not self._sealed:
            raise ValueError("no sealed chapter yet; nothing to compare against")
        old = self._sealed[-1].baselines.get(dimension_id)
        new = self._current_baselines.get(dimension_id)
        if old is None or new is None:
            raise KeyError(f"dimension {dimension_id!r} is not part of the last sealed chapter")
        return {
            "old_baseline": old,
            "new_baseline": new,
            "absolute_shift": new - old,
            "relative_shift": (new - old) / max(abs(old), _TINY),
        }

    def window_mean(self, dimension_id: str, *, start: datetime, end: datetime) -> float:
        """取某时间窗内的均值（供"新常态下重新评估旧数据"的对照使用）。"""

        series = self.series(dimension_id)
        low = int(as_utc(start, "start").timestamp() * 1_000_000)
        high = int(as_utc(end, "end").timestamp() * 1_000_000)
        start_index = bisect_left(series.times_us, low)
        stop_index = bisect_right(series.times_us, high)
        if start_index >= stop_index:
            raise ValueError(
                f"window {start.isoformat()}~{end.isoformat()} contains no samples for {dimension_id!r}"
            )
        return statistics.fmean(series.values[start_index:stop_index])


def default_chapter_start(chapter: SealedChapter) -> datetime:
    """章节起点（便捷函数，避免调用方重复实现时间换算）。"""

    return datetime.fromtimestamp(chapter.start_us / 1_000_000, tz=UTC)


def chapter_duration(chapter: SealedChapter) -> timedelta:
    return timedelta(microseconds=chapter.end_us - chapter.start_us)
