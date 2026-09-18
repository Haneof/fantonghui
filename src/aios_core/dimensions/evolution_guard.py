"""LEGACY/OFFLINE EXPERIMENTAL — dynamic-dimension evolution guard.

This module preserves the historical M3-001R experiment and its regression tests.
It is NOT imported by the R5 CognitiveRuntime / AI Worker production path.

The historical 2-domain / 3-day / 30-day / 70% / daily-quota values below are
legacy experiment defaults, not immutable cognitive truth. Under R6 they must be
represented as versioned Cognitive Policy (evidence-backed, scoped, mutable and
rollbackable) before any future production Runtime integration.

The deterministic recursion/resource fuse and capacity protections remain useful
engineering/safety mechanisms. Do not reconnect the semantic promotion thresholds
to the production Executive Plane merely because this module still exists.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.time import as_utc, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "DAILY_REFLECTION_QUOTA",
    "DIMENSION_TRIAL_DAYS",
    "GATE1_MIN_DOMAINS",
    "GATE1_MIN_DAYS",
    "GATE2_MIN_ACCURACY",
    "MAX_ACTIVE_DIMENSIONS",
    "MAX_REFLECTION_RECURSION_DEPTH",
    "AnomalyObservation",
    "AnomalyStream",
    "CandidateAdmission",
    "CandidateReview",
    "CandidateStatus",
    "CrossDomainVerdict",
    "DimensionCandidate",
    "DimensionRegistry",
    "DomainSpan",
    "EvolutionGuard",
    "DynamicDimensionEvolutionGuard",
    "CandidateDimension",
    "ImmaturePatternRejectedError",
    "PhysicalDomain",
    "QuotaExceededBlockError",
    "RecursiveReflectionCutError",
    "ReflectionQuota",
    "ReflectionRecursionGuard",
    "ReviewOutcome",
]

# ---- Legacy experiment defaults. R6 semantic thresholds require Policy Registry before production use. ----
GATE1_MIN_DOMAINS: Final[int] = 2
GATE1_MIN_DAYS: Final[int] = 3
DIMENSION_TRIAL_DAYS: Final[int] = 30
GATE2_MIN_ACCURACY: Final[float] = 0.70
DAILY_REFLECTION_QUOTA: Final[int] = 1
MAX_ACTIVE_DIMENSIONS: Final[int] = 512  # 解除早期 32 维度硬编码狭隘紧箍咒，认知空间全面释放至 512+
MAX_REFLECTION_RECURSION_DEPTH: Final[int] = 1  # 第 2 层即熔断


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class QuotaExceededBlockError(AIOSProtocolError):
    """每日新维度自省评估配额用尽（门限三）——直接阻断，不给"再来一次"的机会。"""

    def __init__(self, day: date, used: int, limit: int) -> None:
        super().__init__(
            ErrorCode.BUDGET_EXHAUSTED,
            "daily dimension reflection quota exhausted",
            context={
                "reason": "reflection_quota_exceeded",
                "day": day.isoformat(),
                "used": used,
                "limit": limit,
            },
        )


class ImmaturePatternRejectedError(AIOSProtocolError):
    """门限一未满足：跨域不足 / 持续不足 —— 候选一律不收，避免维度噪声。"""

    def __init__(self, verdict: CrossDomainVerdict) -> None:
        super().__init__(
            ErrorCode.INVALID_ARGUMENT,
            "pattern is not mature enough to become a dimension candidate",
            context={
                "reason": "immature_pattern",
                "distinct_domains": verdict.distinct_domains,
                "required_domains": verdict.required_domains,
                "overlapping_days": verdict.overlapping_days,
                "required_days": verdict.required_days,
                "domains": list(verdict.domains),
                "detail": verdict.reason,
            },
        )


class RecursiveReflectionCutError(AIOSProtocolError):
    """反思套娃熔断：第 2 层递归直接物理切断（防止自问自答烧穿端侧算力）。"""

    def __init__(self, depth: int, max_depth: int) -> None:
        super().__init__(
            ErrorCode.PERMISSION_DENIED,
            "reflection recursion cut off: self-interrogation loops are forbidden",
            context={
                "reason": "reflection_recursion_cut",
                "depth": depth,
                "max_depth": max_depth,
            },
        )


# ---------------------------------------------------------------------------
# 门限一：物理跨域持续异常
# ---------------------------------------------------------------------------


class PhysicalDomain(StrEnum):
    """物理域（跨域 = 不同器官/系统维度的异常同时成立）。"""

    SLEEP = "sleep"
    CARDIOVASCULAR = "cardiovascular"
    METABOLIC = "metabolic"
    RESPIRATORY = "respiratory"
    LOCOMOTION = "locomotion"
    ENDOCRINE = "endocrine"


class AnomalyObservation(BaseModel):
    """一条物理域异常事实（来自客观测量，不是模型臆想）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: PhysicalDomain
    observed_at: datetime
    metric: str = Field(min_length=1)
    value: float
    severity: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.observed_at, "observed_at")
        return self

    @property
    def day(self) -> date:
        return as_utc(self.observed_at, "observed_at").date()


class DomainSpan(BaseModel):
    """某物理域的异常持续跨度（按自然日计算）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: PhysicalDomain
    first_day: date
    last_day: date
    days: int = Field(ge=1)

    @property
    def window(self) -> tuple[date, date]:
        return (self.first_day, self.last_day)


class CrossDomainVerdict(BaseModel):
    """门限一裁决：跨几个域、持续几天、是否放行。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    distinct_domains: int = Field(ge=0)
    required_domains: int = Field(ge=1)
    overlapping_days: int = Field(ge=0)
    required_days: int = Field(ge=1)
    domains: tuple[PhysicalDomain, ...] = ()
    spans: tuple[DomainSpan, ...] = ()
    reason: str = Field(min_length=1)


class AnomalyStream:
    """物理域异常流：只接受客观事实，按域聚合出"连续 N 天"的跨度。"""

    def __init__(self, *, allow_gap_days: int = 0) -> None:
        self._observations: list[AnomalyObservation] = []
        self._allow_gap_days = allow_gap_days

    @property
    def size(self) -> int:
        return len(self._observations)

    def observations(self) -> tuple[AnomalyObservation, ...]:
        return tuple(self._observations)

    def add(self, observation: AnomalyObservation) -> None:
        self._observations.append(observation)

    def domains(self) -> tuple[PhysicalDomain, ...]:
        return tuple(sorted({o.domain for o in self._observations}, key=lambda d: d.value))

    def domain_span(self, domain: PhysicalDomain) -> DomainSpan | None:
        days = sorted({o.day for o in self._observations if o.domain is domain})
        if not days:
            return None
        return DomainSpan(
            domain=domain, first_day=days[0], last_day=days[-1], days=len(days)
        )

    def overlapping_window(
        self, domains: Sequence[PhysicalDomain], required_days: int
    ) -> tuple[date, date] | None:
        """这些域**共同覆盖**、且**锚定在最近一次异常**的连续窗口（不满足返回 None）。

        关键纪律：窗口必须一直延续到最新一次异常为止。
        "两周前曾连续爆发 3 天、中间断档、昨天又冒一次"这种陈旧模式**不算持续异常**——
        否则系统会拿着历史噪声立项，正是铁律 5 要防的维度爆炸。
        """
        if not domains:
            return None
        per_domain = [
            sorted({o.day for o in self._observations if o.domain is domain}) for domain in domains
        ]
        if any(not days for days in per_domain):
            return None
        common = set(per_domain[0])
        for days in per_domain[1:]:
            common &= set(days)
        if not common:
            return None
        ordered = sorted(common)
        run_start = ordered[0]
        previous = ordered[0]
        runs: list[tuple[date, date]] = []
        for current in ordered[1:]:
            if (current - previous).days - 1 > self._allow_gap_days:
                runs.append((run_start, previous))
                run_start = current
            previous = current
        runs.append((run_start, previous))

        latest_run = runs[-1]  # 由于 ordered 升序，最后一段必然止于最新一次异常
        if (latest_run[1] - latest_run[0]).days + 1 >= required_days:
            return latest_run
        return None

    def verdict(
        self,
        *,
        min_domains: int = GATE1_MIN_DOMAINS,
        min_days: int = GATE1_MIN_DAYS,
        candidate_domains: Sequence[PhysicalDomain] | None = None,
    ) -> CrossDomainVerdict:
        """门限一裁决：必须是"跨 >= 2 域"且"共同持续 >= 3 天"的同一股异常。"""
        domains = list(candidate_domains) if candidate_domains else list(self.domains())
        spans = tuple(
            span for span in (self.domain_span(domain) for domain in domains) if span is not None
        )
        distinct = len(domains)
        if distinct < min_domains:
            return CrossDomainVerdict(
                allowed=False,
                distinct_domains=distinct,
                required_domains=min_domains,
                overlapping_days=0,
                required_days=min_days,
                domains=tuple(domains),
                spans=spans,
                reason=f"仅覆盖 {distinct} 个物理域，未达跨域门限 {min_domains}",
            )
        window = self.overlapping_window(tuple(domains), min_days)
        if window is None:
            overlap_days = min((span.days for span in spans), default=0)
            return CrossDomainVerdict(
                allowed=False,
                distinct_domains=distinct,
                required_domains=min_domains,
                overlapping_days=overlap_days,
                required_days=min_days,
                domains=tuple(domains),
                spans=spans,
                reason=f"跨域成立但共同持续不足 {min_days} 天（实测 {overlap_days} 天）",
            )
        overlap = (window[1] - window[0]).days + 1
        return CrossDomainVerdict(
            allowed=True,
            distinct_domains=distinct,
            required_domains=min_domains,
            overlapping_days=overlap,
            required_days=min_days,
            domains=tuple(domains),
            spans=spans,
            reason=f"跨 {distinct} 域持续 {overlap} 天（{window[0]}~{window[1]}）",
        )


# ---------------------------------------------------------------------------
# 门限二 & 二之半：试用期、预测检验、全局硬顶
# ---------------------------------------------------------------------------


class CandidateStatus(StrEnum):
    CANDIDATE = "CANDIDATE"    # 试用期观察中
    ACTIVE = "ACTIVE"          # 通过 30 天预测检验，正式活跃
    EXPIRED = "EXPIRED"        # 试用期未达标，自动失效
    ARCHIVED = "ARCHIVED"      # 硬顶淘汰归档


class DimensionCandidate(BaseModel):
    """维度候选：带 30 天试用期与预测检验账本。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    domains: tuple[PhysicalDomain, ...] = Field(min_length=1)
    proposed_at: datetime
    trial_days: int = Field(default=DIMENSION_TRIAL_DAYS, ge=1)
    status: CandidateStatus = CandidateStatus.CANDIDATE
    predictions_total: int = Field(default=0, ge=0)
    predictions_correct: int = Field(default=0, ge=0)
    explanation_days: int = Field(default=0, ge=0, description="连续提供认知解释力的天数")
    activity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    contribution_score: float = Field(default=0.5, ge=0.0, le=1.0)
    status_reason: str | None = None

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _ = require_aware(self.proposed_at, "proposed_at")
        if self.predictions_correct > self.predictions_total:
            raise ValueError("predictions_correct must not exceed predictions_total")
        return self

    @property
    def trial_ends_at(self) -> datetime:
        return as_utc(self.proposed_at, "proposed_at") + timedelta(days=self.trial_days)

    @property
    def accuracy(self) -> float:
        if self.predictions_total == 0:
            return 0.0
        return self.predictions_correct / self.predictions_total

    @property
    def utility_score(self) -> float:
        """淘汰排序依据：活跃度 x 贡献度（工单要求按二者淘汰末位）。"""
        return round(self.activity_score * 0.6 + self.contribution_score * 0.4, 6)

    def with_updates(self, **updates: object) -> DimensionCandidate:
        return self.model_copy(update=updates)


class ReviewOutcome(StrEnum):
    STILL_ON_TRIAL = "still_on_trial"
    PROMOTED = "promoted"
    EXPIRED = "expired"


class CandidateReview(BaseModel):
    """试用期复核结论（可核对：准确率、解释力、结论）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    outcome: ReviewOutcome
    accuracy: float = Field(ge=0.0, le=1.0)
    required_accuracy: float = Field(ge=0.0, le=1.0)
    explanations_continuous: bool
    days_elapsed: int = Field(ge=0)
    trial_days: int = Field(ge=1)
    archived_dimension_id: str | None = None
    reason: str = Field(min_length=1)


class CandidateAdmission(BaseModel):
    """候选准入回执（含被它挤掉的那一个维度）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: DimensionCandidate
    verdict: CrossDomainVerdict
    archived_dimension_id: str | None = None
    active_after: int = Field(ge=0)
    quota_used_today: int = Field(ge=0)


class DimensionRegistry:
    """活跃维度注册表：全局容量 512+（解除 32 狭隘硬顶限制），满员即淘汰末位（ARCHIVED）。"""

    def __init__(self, *, max_active: int = MAX_ACTIVE_DIMENSIONS) -> None:
        if max_active < 1:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "max_active must be positive",
                context={"reason": "invalid_dimension_cap"},
            )
        self._max_active = max_active
        self._active: dict[str, DimensionCandidate] = {}
        self._archived: dict[str, DimensionCandidate] = {}
        self._expired: dict[str, DimensionCandidate] = {}
        self._lock = threading.RLock()

    @property
    def max_active(self) -> int:
        return self._max_active

    @property
    def active_count(self) -> int:
        return len(self._active)

    def active(self) -> tuple[DimensionCandidate, ...]:
        return tuple(self._active.values())

    def archived(self) -> tuple[DimensionCandidate, ...]:
        return tuple(self._archived.values())

    def expired(self) -> tuple[DimensionCandidate, ...]:
        return tuple(self._expired.values())

    def admission_plan(self) -> DimensionCandidate | None:
        """若此刻要引入新维度，应该淘汰谁（活跃度 x 贡献度最低者）。"""
        if not self._active:
            return None
        return min(self._active.values(), key=lambda c: (c.utility_score, c.candidate_id))

    def admit(self, candidate: DimensionCandidate) -> str | None:
        """登记活跃维度；满员时淘汰末位并返回其 id。"""
        with self._lock:
            archived_id: str | None = None
            if len(self._active) >= self._max_active:
                victim = self.admission_plan()
                assert victim is not None
                archived_id = victim.candidate_id
                self._archived[archived_id] = victim.with_updates(
                    status=CandidateStatus.ARCHIVED,
                    status_reason=f"全局活跃维度容量上限 {self._max_active}：按活跃度 x 贡献度淘汰末位",
                )
                self._active.pop(archived_id, None)
            self._active[candidate.candidate_id] = candidate.with_updates(
                status=CandidateStatus.ACTIVE
            )
            return archived_id

    def expire(self, candidate_id: str, reason: str) -> DimensionCandidate | None:
        with self._lock:
            candidate = self._active.pop(candidate_id, None)
            if candidate is None:
                return None
            expired = candidate.with_updates(status=CandidateStatus.EXPIRED, status_reason=reason)
            self._expired[candidate_id] = expired
            return expired


# ---------------------------------------------------------------------------
# 门限三：每日反思配额
# ---------------------------------------------------------------------------


class ReflectionQuota:
    """每日新维度自省评估配额（严格 1 次/天）。"""

    def __init__(self, *, daily_limit: int = DAILY_REFLECTION_QUOTA) -> None:
        if daily_limit < 0:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "daily_limit must be non-negative",
                context={"reason": "invalid_reflection_quota"},
            )
        self._daily_limit = daily_limit
        self._usage: dict[date, int] = {}
        self._lock = threading.RLock()

    @property
    def daily_limit(self) -> int:
        return self._daily_limit

    def used_on(self, day: date) -> int:
        return self._usage.get(day, 0)

    def remaining(self, now: datetime) -> int:
        return max(self._daily_limit - self.used_on(as_utc(now, "now").date()), 0)

    def consume(self, now: datetime) -> int:
        """占用一次配额；超额抛 :class:`QuotaExceededBlockError`。"""
        day = as_utc(now, "now").date()
        with self._lock:
            used = self._usage.get(day, 0)
            if used >= self._daily_limit:
                raise QuotaExceededBlockError(day, used, self._daily_limit)
            self._usage[day] = used + 1
            return self._usage[day]


# ---------------------------------------------------------------------------
# 自问自答死循环熔断
# ---------------------------------------------------------------------------


class ReflectionRecursionGuard:
    """反思递归守卫：第 2 层递归直接物理切断。"""

    def __init__(self, *, max_depth: int = MAX_REFLECTION_RECURSION_DEPTH) -> None:
        if max_depth < 0:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "max_depth must be non-negative",
                context={"reason": "invalid_reflection_depth"},
            )
        self._max_depth = max_depth
        self._cut_count = 0
        self._admitted = 0

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @property
    def cut_count(self) -> int:
        return self._cut_count

    @property
    def admitted_count(self) -> int:
        return self._admitted

    def enter(self, depth: int) -> int:
        """进入第 ``depth`` 层反思；超过上限立即熔断（不返回、不降级、不追问）。"""
        if not isinstance(depth, int) or depth < 1:
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                "reflection depth must be a positive integer",
                context={"reason": "invalid_reflection_depth", "depth": depth},
            )
        if depth > self._max_depth:
            self._cut_count += 1
            raise RecursiveReflectionCutError(depth, self._max_depth)
        self._admitted += 1
        return depth


# ---------------------------------------------------------------------------
# 守卫门面：三重门限 + 硬顶 + 熔断
# ---------------------------------------------------------------------------


class EvolutionGuard:
    """维度演化守卫：把"克制"变成可执行的三重门限状态机。"""

    def __init__(
        self,
        *,
        stream: AnomalyStream | None = None,
        registry: DimensionRegistry | None = None,
        quota: ReflectionQuota | None = None,
        recursion_guard: ReflectionRecursionGuard | None = None,
    ) -> None:
        self._stream = stream or AnomalyStream()
        self._registry = registry or DimensionRegistry()
        self._quota = quota or ReflectionQuota()
        self._recursion = recursion_guard or ReflectionRecursionGuard()
        self._candidates: dict[str, DimensionCandidate] = {}
        self._lock = threading.RLock()
        self._submissions: list[CandidateAdmission] = []

    # ---- 只读 ----

    @property
    def stream(self) -> AnomalyStream:
        return self._stream

    @property
    def registry(self) -> DimensionRegistry:
        return self._registry

    @property
    def quota(self) -> ReflectionQuota:
        return self._quota

    @property
    def recursion_guard(self) -> ReflectionRecursionGuard:
        return self._recursion

    @property
    def active_count(self) -> int:
        return self._registry.active_count

    def candidate(self, candidate_id: str) -> DimensionCandidate | None:
        return self._candidates.get(candidate_id)

    def candidates(self) -> tuple[DimensionCandidate, ...]:
        return tuple(self._candidates.values())

    def submissions(self) -> tuple[CandidateAdmission, ...]:
        return tuple(self._submissions)

    # ---- 事实摄入 ----

    def observe_anomaly(
        self,
        domain: PhysicalDomain,
        *,
        observed_at: datetime,
        metric: str,
        value: float,
        severity: float = 0.5,
    ) -> AnomalyObservation:
        observation = AnomalyObservation(
            domain=domain,
            observed_at=observed_at,
            metric=metric,
            value=value,
            severity=severity,
        )
        self._stream.add(observation)
        return observation

    def gate_one_verdict(
        self, domains: Sequence[PhysicalDomain] | None = None
    ) -> CrossDomainVerdict:
        return self._stream.verdict(candidate_domains=domains) if domains else self._stream.verdict()

    # ---- 门限一 + 门限三：提交候选 ----

    def submit_candidate(
        self,
        candidate_id: str,
        *,
        name: str,
        domains: Sequence[PhysicalDomain],
        now: datetime,
        description: str = "",
        trial_days: int = DIMENSION_TRIAL_DAYS,
    ) -> CandidateAdmission:
        """提交新维度候选。

        顺序即纪律：**先做门限一机械裁决（0 Token，不占配额）**，只有跨域且持续异常
        才允许消耗当天那唯一一次自省评估配额（门限三）。
        """
        with self._lock:
            if candidate_id in self._candidates:
                raise AIOSProtocolError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "candidate_id already exists",
                    context={"reason": "duplicate_candidate", "candidate_id": candidate_id},
                )
            verdict = self._stream.verdict(candidate_domains=tuple(domains))
            if not verdict.allowed:
                # 门限一不通过：机械拒绝，连配额都不烧（不成熟就闭嘴）。
                raise ImmaturePatternRejectedError(verdict)
            used = self._quota.consume(now)  # 门限三：超额抛 QuotaExceededBlockError
            candidate = DimensionCandidate(
                candidate_id=candidate_id,
                name=name,
                description=description,
                domains=tuple(domains),
                proposed_at=now,
                trial_days=trial_days,
            )
            self._candidates[candidate_id] = candidate
            admission = CandidateAdmission(
                candidate=candidate,
                verdict=verdict,
                active_after=self._registry.active_count,
                quota_used_today=used,
            )
            self._submissions.append(admission)
            return admission

    # ---- 门限二：30 天试用期与预测检验 ----

    def review_candidate(
        self,
        candidate_id: str,
        *,
        now: datetime,
        predictions_total: int,
        predictions_correct: int,
        explanation_days: int,
    ) -> CandidateReview:
        """试用期复核：达标则晋升 ACTIVE（受全局硬顶约束），否则 EXPIRED。"""
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                raise AIOSProtocolError(
                    ErrorCode.NOT_FOUND,
                    "unknown dimension candidate",
                    context={"reason": "unknown_candidate", "candidate_id": candidate_id},
                )
            if candidate.status is not CandidateStatus.CANDIDATE:
                raise AIOSProtocolError(
                    ErrorCode.INVALID_ARGUMENT,
                    "candidate is not on trial",
                    context={
                        "reason": "candidate_not_on_trial",
                        "candidate_id": candidate_id,
                        "status": candidate.status.value,
                    },
                )
            moment = as_utc(now, "now")
            elapsed = (moment - candidate.proposed_at).days
            if elapsed < 1:
                raise AIOSProtocolError(
                    ErrorCode.INVALID_ARGUMENT,
                    "trial review requires at least one full day of evidence",
                    context={"reason": "trial_not_started", "candidate_id": candidate_id},
                )
            updated = candidate.with_updates(
                predictions_total=predictions_total,
                predictions_correct=predictions_correct,
                explanation_days=explanation_days,
            )
            accuracy = updated.accuracy
            # 连续解释力 = 从立项那天起每一天都能解释（缺席一天即算断档）
            continuous = explanation_days >= elapsed
            on_time = moment <= updated.trial_ends_at
            passed = accuracy >= GATE2_MIN_ACCURACY and continuous

            if passed:
                archived_id = self._registry.admit(updated.with_updates(activity_score=1.0))
                self._candidates[candidate_id] = updated.with_updates(
                    status=CandidateStatus.ACTIVE,
                    status_reason=f"30 天试用期预测准确率 {accuracy:.0%} 达标，晋升活跃维度",
                )
                return CandidateReview(
                    candidate_id=candidate_id,
                    outcome=ReviewOutcome.PROMOTED,
                    accuracy=accuracy,
                    required_accuracy=GATE2_MIN_ACCURACY,
                    explanations_continuous=continuous,
                    days_elapsed=elapsed,
                    trial_days=updated.trial_days,
                    archived_dimension_id=archived_id,
                    reason=(
                        f"预测准确率 {accuracy:.0%} >= 70% 且解释力连续 {explanation_days} 天"
                        + (f"；硬顶淘汰 {archived_id}" if archived_id else "")
                    ),
                )

            if on_time and accuracy < GATE2_MIN_ACCURACY:
                # 试用期内明确不达标：立即失效，不占用硬顶、不拖到 30 天期满。
                expired = updated.with_updates(
                    status=CandidateStatus.EXPIRED,
                    status_reason=f"预测准确率 {accuracy:.0%} 低于 70% 门限",
                )
                self._candidates[candidate_id] = expired
                return CandidateReview(
                    candidate_id=candidate_id,
                    outcome=ReviewOutcome.EXPIRED,
                    accuracy=accuracy,
                    required_accuracy=GATE2_MIN_ACCURACY,
                    explanations_continuous=continuous,
                    days_elapsed=elapsed,
                    trial_days=updated.trial_days,
                    reason=f"预测准确率 {accuracy:.0%} 低于 {GATE2_MIN_ACCURACY:.0%} 门限，自动失效",
                )

            if not on_time or elapsed >= updated.trial_days:
                expired = updated.with_updates(
                    status=CandidateStatus.EXPIRED,
                    status_reason="30 天试用期届满仍未达标",
                )
                self._candidates[candidate_id] = expired
                return CandidateReview(
                    candidate_id=candidate_id,
                    outcome=ReviewOutcome.EXPIRED,
                    accuracy=accuracy,
                    required_accuracy=GATE2_MIN_ACCURACY,
                    explanations_continuous=continuous,
                    days_elapsed=elapsed,
                    trial_days=updated.trial_days,
                    reason="30 天试用期届满仍未满足预测/解释力门限，自动失效",
                )

            self._candidates[candidate_id] = updated
            return CandidateReview(
                candidate_id=candidate_id,
                outcome=ReviewOutcome.STILL_ON_TRIAL,
                accuracy=accuracy,
                required_accuracy=GATE2_MIN_ACCURACY,
                explanations_continuous=continuous,
                days_elapsed=elapsed,
                trial_days=updated.trial_days,
                reason=(
                    f"试用期第 {elapsed} 天：准确率 {accuracy:.0%}，"
                    f"解释力连续 {explanation_days} 天，继续观察"
                ),
            )

    # ---- 熔断 ----


    @property
    def active_dimension_count(self) -> int:
        return self._registry.active_count

    @property
    def candidate_dimension_count(self) -> int:
        return len(self._candidates)

    @property
    def max_active_limit(self) -> int:
        return self._registry.max_active

    def evaluate_and_register(self, dim: Any) -> Any:
        if isinstance(dim, CandidateDimension):
            if len(dim.physical_domains) < 2 or dim.consecutive_days < 3:
                dim.status = "CANDIDATE"
                self._candidates[dim.name] = dim
                return dim
            elif dim.prediction_accuracy >= 0.70 and self._registry.active_count < self._registry.max_active:
                dim.status = "ACTIVE"
                return dim
        return dim

    def consider_reflection(self, depth: int) -> int:
        """允许一层自省；第 2 层递归立即物理切断。"""
        return self._recursion.enter(depth)

    # ---- 审计 ----

    def audit(self) -> dict[str, object]:
        trial = [
            c.candidate_id
            for c in self._candidates.values()
            if c.status is CandidateStatus.CANDIDATE
        ]
        # 试用期未达标而失效的候选（从未进入 ACTIVE，独立于"活跃维度被失效"）
        expired_candidates = [
            c.candidate_id
            for c in self._candidates.values()
            if c.status is CandidateStatus.EXPIRED
        ]
        return {
            "anomaly_observations": self._stream.size,
            "domains_observed": [d.value for d in self._stream.domains()],
            "candidates_on_trial": trial,
            "active_dimensions": self._registry.active_count,
            "active_cap": self._registry.max_active,
            "archived_dimensions": [c.candidate_id for c in self._registry.archived()],
            "expired_candidates": expired_candidates,
            "expired_dimensions": [c.candidate_id for c in self._registry.expired()],
            "reflection_cuts": self._recursion.cut_count,
        }


def retention_summary(registry: DimensionRegistry) -> Mapping[str, int]:
    """维度留存一览：活跃 / 归档 / 失效（供看板只读引用）。"""
    return {
        "active": registry.active_count,
        "archived": len(registry.archived()),
        "expired": len(registry.expired()),
    }


class CandidateDimension(BaseModel):
    name: str
    physical_domains: list[str] = Field(default_factory=list)
    consecutive_days: int = 1
    prediction_accuracy: float = 0.5
    status: str = "CANDIDATE"


DynamicDimensionEvolutionGuard = EvolutionGuard
