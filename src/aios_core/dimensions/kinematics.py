"""阶段四：高阶认知运动学——速度/加速度/拐点与非线性人生相变（MT-011/016）。

宪法口径：**导数计算属于认知层，严禁底层硬件做导数**——本模块消费的
是已被边缘层提纯的维度曲线（如《身心耗竭》《投资焦虑》），输出：

* Velocity（恶化速度，单位/天）与 Acceleration（恶化加速度，单位/天²）；
* Inflection 拐点探测：加速度陡增即提前触发熔断预警（预警领先于
  阈值击穿，领先时间可量化）；
* LifeChapter 相变：核心基线永久断裂识别（滚动中位数 + MAD 判据），
  封存旧章节、重置敏感基线，绝不触碰历史事实记录。

另附铁律5三重硬门槛的对接套件：突发新维度申请必须经
:mod:`aios_core.dimensions.evolution_guard` 拦截器放行。
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from aios_core.contracts.time import require_aware

__all__ = [
    "SeverityPoint",
    "KinematicStep",
    "compute_kinematics",
    "Inflection",
    "InflectionDetector",
    "LifeChapter",
    "LifeChapterDetector",
]


@dataclass(frozen=True, slots=True)
class SeverityPoint:
    """维度严重度采样（0~100，认知层口径）。"""

    at: datetime
    value: float


@dataclass(frozen=True, slots=True)
class KinematicStep:
    """相邻窗口间的一阶/二阶认知导数。"""

    at: datetime
    velocity: float            # 严重度/天
    acceleration: float        # 严重度/天²
    window_days: float


def compute_kinematics(series: Sequence[SeverityPoint]) -> list[KinematicStep]:
    """认知层导数：v_i = Δvalue/Δt，a_i = Δv/Δt（相邻步中心差分）。"""
    if len(series) < 3:
        raise ValueError("kinematics needs >= 3 points")
    steps: list[KinematicStep] = []
    for i in range(1, len(series)):
        dt = (series[i].at - series[i - 1].at).total_seconds() / 86400.0
        if dt <= 0:
            raise ValueError("series must be strictly increasing in time")
        v = (series[i].value - series[i - 1].value) / dt
        if steps:
            prev = steps[-1]
            dt2 = (series[i].at - prev.at).total_seconds() / 86400.0
            a = (v - prev.velocity) / max(dt2, 1e-9) if dt2 > 0 else 0.0
        else:
            a = 0.0
        steps.append(KinematicStep(at=series[i].at, velocity=v, acceleration=a, window_days=dt))
    return steps


@dataclass(frozen=True, slots=True)
class Inflection:
    """拐点：加速度陡增点 + 相对阈值击穿的预警领先量。"""

    at: datetime
    acceleration: float
    lead_time_days: float | None   # 相对 severity_threshold 击穿日的领先天数
    warning: str


class InflectionDetector:
    """拐点探测：加速度越限即预警；若后续发生阈值击穿，回算领先时间。"""

    def __init__(
        self,
        *,
        accel_threshold: float = 0.02,
        severity_threshold: float = 80.0,
    ) -> None:
        if accel_threshold <= 0:
            raise ValueError("accel_threshold must be positive")
        self._accel_t = accel_threshold
        self._sev_t = severity_threshold

    def detect(self, series: Sequence[SeverityPoint]) -> list[Inflection]:
        steps = compute_kinematics(series)
        breach_at: datetime | None = next(
            (p.at for p in series if p.value >= self._sev_t), None
        )
        out: list[Inflection] = []
        for step in steps:
            if step.acceleration >= self._accel_t:
                lead = None
                if breach_at is not None and breach_at > step.at:
                    lead = (breach_at - step.at).total_seconds() / 86400.0
                out.append(Inflection(
                    at=step.at,
                    acceleration=step.acceleration,
                    lead_time_days=lead,
                    warning=(
                        f"恶化加速度 {step.acceleration:.2f}/天² 越限 "
                        f"(>{self._accel_t})，熔断预警先行"
                        + (f"，领先阈值击穿 {lead:.1f} 天" if lead is not None else "")
                    ),
                ))
        return out


@dataclass(frozen=True, slots=True)
class LifeChapter:
    """人生章节：基线断裂处的封存与重启。"""

    chapter_id: str
    start: datetime
    end: datetime | None
    end_reason: str | None
    sealed: bool
    baseline: dict[str, float]


class LifeChapterDetector:
    """非线性相变识别：滚动中位数基线 + MAD 突变判据。

    判据：新窗口中位数相对旧基线偏离 > k·MAD 且持续 ≥ sustain_days，
    判定核心基线永久断裂 → 封存旧章节（end_reason 记录断裂指标），
    以新窗口基线开启新章节。全程只读历史、只写今天。
    """

    def __init__(
        self,
        *,
        window_days: int = 30,
        mad_multiple: float = 4.0,
        sustain_days: int = 10,
    ) -> None:
        if window_days < 7:
            raise ValueError("window_days must be >= 7")
        self._window = window_days
        self._k = mad_multiple
        self._sustain = sustain_days
        self._lock = threading.RLock()
        self._counter = 0

    def detect(
        self,
        series: Sequence[SeverityPoint],
        *,
        metric: str = "resting_hr",
    ) -> list[LifeChapter]:
        """旧章节窗（当前章起点 → 预警点前 sustain 天）内滚动中位数 + MAD
        为基线判据；新窗（最近 window_days）中位偏离 > k·MAD 且持续
        ≥ sustain_days → 封存旧章、以断裂日开启新章。
        """
        require_aware(series[0].at, "series[0].at")
        chapters: list[LifeChapter] = []
        current_start = series[0].at
        breach_day: datetime | None = None
        n = len(series)
        for i, p in enumerate(series):
            old = [
                q.value for q in series
                if current_start <= q.at < p.at - timedelta_days(self._sustain)
            ]
            if len(old) < 10:
                continue
            baseline = _median(old)
            mad = _mad(old) or max(1.0, baseline * 0.02)
            new = [
                q.value for q in series
                if p.at - timedelta_days(self._window) <= q.at <= p.at
            ]
            if len(new) < max(5, self._window // 3):
                continue
            w_median = _median(new)
            dev = abs(w_median - baseline) / mad
            if dev > self._k:
                if breach_day is None:
                    breach_day = p.at
                if (p.at - breach_day).days >= self._sustain:
                    self._counter += 1
                    chapters.append(LifeChapter(
                        chapter_id=f"chapter-{self._counter:03d}",
                        start=current_start,
                        end=breach_day,
                        end_reason=(
                            f"{metric} 基线断裂：新窗中位 {w_median:.1f} 偏离"
                            f"旧基线 {baseline:.1f} 达 {dev:.1f}×MAD，持续 "
                            f"{(p.at - breach_day).days} 天（相变归档，历史未动）"
                        ),
                        sealed=True,
                        baseline={metric: baseline},
                    ))
                    current_start = breach_day
                    breach_day = None
            else:
                breach_day = None
        self._counter += 1
        chapters.append(LifeChapter(
            chapter_id=f"chapter-{self._counter:03d}",
            start=current_start,
            end=None,
            end_reason=None,
            sealed=False,
            baseline={metric: baseline if chapters or old else series[0].value},
        ))
        return chapters


# ----------------------------------------------------------------------

def timedelta_days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


def _window_median(series: Sequence[SeverityPoint], at: datetime, window_days: int) -> float:
    lo = at - timedelta_days(window_days)
    hi = at + timedelta_days(window_days)
    window = [p.value for p in series if lo <= p.at <= hi]
    return _median(window or [p.value for p in series])


def _median(values: Sequence[float]) -> float:
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        raise ValueError("median of empty sequence")
    mid = n // 2
    if n % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def _mad(values: Sequence[float]) -> float:
    med = _median(values)
    return _median([abs(v - med) for v in values])
