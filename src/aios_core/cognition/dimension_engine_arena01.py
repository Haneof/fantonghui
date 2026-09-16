"""M5-DIM-LIFECYCLE 心智维度演化与生命周期（arena01 独立命名并存线）。

三件事，全部宪法级硬门槛，绝不兜底放行：

1. CrossDimensionalAnomalyDetector——心率+账单+聊天等 ≥2 物理域、≥3 个
   独立自然日、跨度 ≥3 天的持续异常体征锁定（仅锁定，不建模维度）；
2. DimensionLifecycleGate——铁律 5 三重硬门槛状态机：
   门槛1（3 天跨域异常入册）、门槛2（候选试用 30 个自然日且预测验证
   准确率 ≥0.70 且覆盖 ≥0.80，未满 30 天注册/转正必须抛异常）、
   门槛3（反思配额每日最多 1 次，第二次必须被配额拒绝）；
3. HighOrderDimensionDistiller——自锁体与断言集提炼高阶维度只读探测
   标签（DIM_BURNOUT_RISK 过劳猝死风险、DIM_CREDIT_RISK 老王信用破产等）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Dict, List, Optional, Sequence, Set, Tuple

__all__ = [
    "DomainAnomaly",
    "CrossDomainLock",
    "CrossDimensionalAnomalyDetector",
    "LifecycleStage",
    "TrialWindowNotMetError",
    "ReflectionQuotaExceededError",
    "LifecycleGateError",
    "DimensionLifecycleGate",
    "HighOrderDimensionLabel",
    "HighOrderDimensionDistiller",
    "MIN_PHYSICALLY_SEPARATE_DOMAINS",
    "MIN_ANOMALY_DAYS",
    "MIN_ANOMALY_SPAN_DAYS",
    "TRIAL_DAYS",
    "MIN_TRIAL_ACCURACY",
    "MIN_TRIAL_COVERAGE",
    "DAILY_REFLECTION_QUOTA",
]

MIN_PHYSICALLY_SEPARATE_DOMAINS = 2
MIN_ANOMALY_DAYS = 3
MIN_ANOMALY_SPAN_DAYS = 3
TRIAL_DAYS = 30
MIN_TRIAL_ACCURACY = 0.70
MIN_TRIAL_COVERAGE = 0.80
DAILY_REFLECTION_QUOTA = 1


class LifecycleGateError(RuntimeError):
    """生命周期硬门槛违例基类。"""


class TrialWindowNotMetError(LifecycleGateError):
    """未满 30 个自然日试用即注册/转正。"""


class ReflectionQuotaExceededError(LifecycleGateError):
    """当日第二次反思被配额阻断。"""


@dataclass(frozen=True)
class DomainAnomaly:
    domain: str  # heartrate / billing / chat / motion ...
    day: date
    severity: float
    text: str


@dataclass(frozen=True)
class CrossDomainLock:
    lock_id: str
    domains: Tuple[str, ...]
    covered_days: Tuple[date, ...]
    span_days: int
    last_anomaly_day: date


class CrossDimensionalAnomalyDetector:
    """跨域物理异常探测器：跨域 × 跨日的持续异常体征才允许锁定。"""

    def __init__(self, *, window_days: int = 10) -> None:
        self._window_days = window_days
        self._observations: List[DomainAnomaly] = []

    def ingest(self, anomaly: DomainAnomaly) -> None:
        self._observations.append(anomaly)

    def try_lock(self, subject_hint: str = "self") -> Optional[CrossDomainLock]:
        days: Set[date] = {a.day for a in self._observations}
        domains: Set[str] = {a.domain for a in self._observations}
        if not days:
            return None
        ordered = sorted(days)
        coverage_by_day: Dict[date, Set[str]] = {}
        for a in self._observations:
            coverage_by_day.setdefault(a.day, set()).add(a.domain)
        robust_days = [d for d, ds in coverage_by_day.items() if ds]
        if len(domains) < MIN_PHYSICALLY_SEPARATE_DOMAINS:
            return None
        if len(robust_days) < MIN_ANOMALY_DAYS:
            return None
        span = (ordered[-1] - ordered[0]).days + 1
        if span < MIN_ANOMALY_SPAN_DAYS:
            return None
        lock = CrossDomainLock(
            lock_id=f"LOCK-{subject_hint}-{ordered[-1]:%Y%m%d}",
            domains=tuple(sorted(domains)),
            covered_days=tuple(sorted(robust_days)),
            span_days=span,
            last_anomaly_day=ordered[-1],
        )
        self._observations.clear()  # 锁定即清账，防止一票反复开票
        return lock


class LifecycleStage(StrEnum):
    CANDIDATE = "CANDIDATE"
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


@dataclass
class _DimensionTrack:
    slug: str
    stage: LifecycleStage
    enrolled_on: date  # 门槛1：最后异常日
    trial_start: Optional[date] = None
    predictions: List[Tuple[date, bool]] = field(default_factory=list)
    reflections: Dict[date, int] = field(default_factory=dict)
    label_codes: Tuple[str, ...] = ()


class DimensionLifecycleGate:
    """铁律 5 三重硬门槛状态机。"""

    def __init__(self) -> None:
        self._tracks: Dict[str, _DimensionTrack] = {}

    # 门槛1：3 天跨域异常入册
    def register_candidate(self, slug: str, lock: CrossDomainLock) -> _DimensionTrack:
        if slug in self._tracks:
            raise LifecycleGateError(f"dimension already registered: {slug}")
        if len(lock.domains) < MIN_PHYSICALLY_SEPARATE_DOMAINS:
            raise LifecycleGateError("gate-1 refused: physically separate domains < 2")
        if len(lock.covered_days) < MIN_ANOMALY_DAYS or lock.span_days < MIN_ANOMALY_SPAN_DAYS:
            raise LifecycleGateError("gate-1 refused: anomaly evidence < 3 days / span < 3")
        track = _DimensionTrack(slug=slug, stage=LifecycleStage.CANDIDATE,
                                enrolled_on=lock.last_anomaly_day)
        self._tracks[slug] = track
        return track

    def begin_trial(self, slug: str, on: date) -> None:
        track = self._require(slug)
        if track.stage is not LifecycleStage.CANDIDATE:
            raise LifecycleGateError(f"trial must begin from CANDIDATE, got {track.stage}")
        if on < track.enrolled_on:
            raise LifecycleGateError("gate-2 refused: trial backdated before enrollment day")
        track.stage = LifecycleStage.TRIAL
        track.trial_start = on

    # 门槛2：30 天试用预测验证
    def record_prediction(self, slug: str, day: date, correct: bool) -> None:
        track = self._require(slug)
        if track.stage is not LifecycleStage.TRIAL:
            raise LifecycleGateError("predictions only inside TRIAL")
        if track.trial_start is None or day < track.trial_start:
            raise LifecycleGateError("predate trial refused")
        if any(d == day for d, _ in track.predictions):
            raise LifecycleGateError("same-day prediction replay refused")
        track.predictions.append((day, correct))

    def activate(self, slug: str, on: date) -> _DimensionTrack:
        track = self._require(slug)
        if track.stage is not LifecycleStage.TRIAL:
            raise LifecycleGateError(f"activate requires TRIAL, got {track.stage}")
        assert track.trial_start is not None
        elapsed = (on - track.trial_start).days + 1
        if elapsed < TRIAL_DAYS:
            raise TrialWindowNotMetError(
                f"gate-2 refused: trial {elapsed}d < {TRIAL_DAYS}d (未满30天注册必须抛异常)"
            )
        total = len(track.predictions)
        accuracy = (sum(1 for _, ok in track.predictions if ok) / total) if total else 0.0
        coverage = len({d for d, _ in track.predictions}) / TRIAL_DAYS
        if accuracy < MIN_TRIAL_ACCURACY or coverage < MIN_TRIAL_COVERAGE:
            track.stage = LifecycleStage.EXPIRED
            raise LifecycleGateError(
                f"gate-2 expired: accuracy={accuracy:.3f} coverage={coverage:.3f}"
            )
        track.stage = LifecycleStage.ACTIVE
        return track

    # 门槛3：每日最多 1 次反思配额
    def reflect(self, slug: str, on: date) -> int:
        track = self._require(slug)
        used = track.reflections.get(on, 0)
        if used >= DAILY_REFLECTION_QUOTA:
            raise ReflectionQuotaExceededError(
                f"gate-3 refused: reflection quota {used}/{DAILY_REFLECTION_QUOTA} on {on}"
            )
        track.reflections[on] = used + 1
        return used + 1

    def attach_labels(self, slug: str, label_codes: Sequence[str]) -> None:
        track = self._require(slug)
        track.label_codes = tuple(sorted(set(track.label_codes) | set(label_codes)))

    def stage_of(self, slug: str) -> LifecycleStage:
        return self._require(slug).stage

    def _require(self, slug: str) -> _DimensionTrack:
        try:
            return self._tracks[slug]
        except KeyError:
            raise LifecycleGateError(f"unknown dimension: {slug}") from None


@dataclass(frozen=True)
class HighOrderDimensionLabel:
    """高阶维度只读探测标签：冻结不可变，改写抛 FrozenInstanceError。"""

    code: str
    title: str
    advisory: str
    evidence_domains: Tuple[str, ...]
    evidence_keywords: Tuple[str, ...]


class HighOrderDimensionDistiller:
    """从锁定体与断言文本提炼高阶维度标签（纯确定性规则，不空泛）。"""

    _RULES: Tuple[Tuple[str, str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
        ("DIM_CREDIT_RISK", "老王信用破产",
         "司法裁决+逾期债务锁定 ⇒ 阻断一切新增授信与借款回流",
         ("billing", "chat", "judicial"),
         ("老王", "违约", "逾期", "判决", "赖账")),
        ("DIM_BURNOUT_RISK", "过劳猝死风险",
         "跨周通宵+心律体征恶化锁定 ⇒ 强制停工保护，任何日程让步",
         ("heartrate", "chat", "calendar"),
         ("通宵", "加班", "早搏", "心悸", "猝死")),
    )

    def distill(self, *, locks: Sequence[CrossDomainLock],
                claim_texts: Sequence[str]) -> Tuple[HighOrderDimensionLabel, ...]:
        locked_domains: Set[str] = set()
        for lock in locks:
            locked_domains.update(lock.domains)
        corpus = "\n".join(claim_texts)
        labels: List[HighOrderDimensionLabel] = []
        for code, title, advisory, domains, keywords in self._RULES:
            kw_hits = [k for k in keywords if k in corpus]
            if len(kw_hits) >= 3 and locked_domains.intersection(domains):
                labels.append(HighOrderDimensionLabel(
                    code=code, title=title, advisory=advisory,
                    evidence_domains=tuple(sorted(locked_domains.intersection(domains))),
                    evidence_keywords=tuple(kw_hits[:5]),
                ))
        return tuple(labels)
