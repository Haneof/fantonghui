"""M3-001R conservative derived-dimension evolution guard.

A dimension can be proposed only after simultaneous anomalies in at least two
physical domains persist for three full days.  It then serves a complete
30-day trial.  Reflection admission is globally limited to once per UTC day,
active derived dimensions never exceed 32, and recursive reflection is cut
before a depth-2 evaluator call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.time import as_utc, require_aware


class DerivedDimensionState(StrEnum):
    CANDIDATE = "CANDIDATE"
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class AdmissionThresholdBlockError(RuntimeError):
    """Cross-domain persistence did not clear constitutional gate one."""


class QuotaExceededBlockError(RuntimeError):
    """The one-per-day new-dimension reflection quota is exhausted."""


class IllegalDimensionTransitionError(RuntimeError):
    """A lifecycle transition attempted to bypass a dimension gate."""


class ReflectionRecursionBlockError(RuntimeError):
    """A nested reflection attempted to enter depth two or deeper."""


class PhysicalDomainAnomaly(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    domain: str = Field(min_length=1, max_length=120)
    started_at: datetime
    observed_through: datetime

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return value.casefold()

    @field_validator("started_at", "observed_through")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime, info: Any) -> datetime:
        require_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def interval_must_not_run_backwards(self) -> PhysicalDomainAnomaly:
        if as_utc(self.observed_through) < as_utc(self.started_at):
            raise ValueError("observed_through cannot precede started_at")
        return self


class DimensionCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    dimension_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=4_096)
    anomalies: tuple[PhysicalDomainAnomaly, ...] = Field(min_length=2, max_length=16)
    activity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    contribution_score: float = Field(default=0.5, ge=0.0, le=1.0)


class TrialEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str = Field(min_length=1, max_length=160)
    observed_at: datetime
    explanation_supported: bool
    prediction_success: bool

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "observed_at")
        return value

    @property
    def utc_day(self) -> date:
        return as_utc(self.observed_at).date()


class DerivedDimensionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    dimension_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=4_096)
    state: DerivedDimensionState
    physical_domains: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime
    trial_started_at: datetime | None = None
    trial_deadline: datetime | None = None
    activity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    contribution_score: float = Field(default=0.5, ge=0.0, le=1.0)
    last_active_at: datetime | None = None
    expired_at: datetime | None = None
    archived_at: datetime | None = None

    @field_validator(
        "created_at",
        "trial_started_at",
        "trial_deadline",
        "last_active_at",
        "expired_at",
        "archived_at",
    )
    @classmethod
    def timestamps_must_be_aware(
        cls, value: datetime | None, info: Any
    ) -> datetime | None:
        require_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def trial_bounds_must_be_paired(self) -> DerivedDimensionRecord:
        if (self.trial_started_at is None) != (self.trial_deadline is None):
            raise ValueError("trial_started_at and trial_deadline must be paired")
        if (
            self.trial_started_at is not None
            and self.trial_deadline is not None
            and as_utc(self.trial_deadline) - as_utc(self.trial_started_at)
            != timedelta(days=30)
        ):
            raise ValueError("trial window must be exactly 30 days")
        return self

    @property
    def contribution_rank(self) -> float:
        return self.activity_score * 0.4 + self.contribution_score * 0.6


class TrialEvaluationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    dimension_id: str
    evaluated_at: datetime
    state: DerivedDimensionState
    finalized: bool
    covered_days: int = Field(ge=0, le=30)
    prediction_accuracy: float = Field(ge=0.0, le=1.0)
    continuous_explanation: bool
    archived_dimension_id: str | None = None

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "evaluated_at")
        return value


ReflectionEvaluator = Callable[[str, int], Any]


class DimensionEvolutionGuard:
    MIN_PHYSICAL_DOMAINS: ClassVar[int] = 2
    MIN_ANOMALY_DURATION: ClassVar[timedelta] = timedelta(days=3)
    TRIAL_DURATION: ClassVar[timedelta] = timedelta(days=30)
    MIN_PREDICTION_ACCURACY: ClassVar[float] = 0.70
    MAX_ACTIVE_DIMENSIONS: ClassVar[int] = 32
    MAX_REFLECTION_DEPTH_EXCLUSIVE: ClassVar[int] = 2

    _ALLOWED_TRANSITIONS: ClassVar[
        dict[DerivedDimensionState, frozenset[DerivedDimensionState]]
    ] = {
        DerivedDimensionState.CANDIDATE: frozenset({DerivedDimensionState.TRIAL}),
        DerivedDimensionState.TRIAL: frozenset(
            {DerivedDimensionState.ACTIVE, DerivedDimensionState.EXPIRED}
        ),
        DerivedDimensionState.ACTIVE: frozenset({DerivedDimensionState.ARCHIVED}),
        DerivedDimensionState.EXPIRED: frozenset(),
        DerivedDimensionState.ARCHIVED: frozenset(),
    }

    def __init__(
        self,
        active_dimensions: Iterable[DerivedDimensionRecord] = (),
    ) -> None:
        self._dimensions: dict[str, DerivedDimensionRecord] = {}
        self._trial_evidence: dict[str, dict[date, TrialEvidence]] = {}
        self._reflection_quota_days: set[date] = set()
        self._lock = RLock()
        for item in active_dimensions:
            record = DerivedDimensionRecord.model_validate(item)
            if record.state is not DerivedDimensionState.ACTIVE:
                raise ValueError("restored dimensions must be ACTIVE")
            if record.dimension_id in self._dimensions:
                raise ValueError(f"duplicate dimension_id: {record.dimension_id}")
            self._dimensions[record.dimension_id] = record
        self._assert_active_cap()

    def submit_candidate(
        self,
        request: DimensionCandidateRequest,
        *,
        submitted_at: datetime,
    ) -> DerivedDimensionRecord:
        candidate = DimensionCandidateRequest.model_validate(request)
        require_aware(submitted_at, "submitted_at")
        self._validate_cross_domain_gate(candidate.anomalies)
        quota_day = as_utc(submitted_at).date()
        with self._lock:
            if candidate.dimension_id in self._dimensions:
                raise ValueError(
                    f"dimension_id already exists: {candidate.dimension_id}"
                )
            if quota_day in self._reflection_quota_days:
                raise QuotaExceededBlockError(
                    f"new-dimension reflection quota already used on {quota_day}"
                )
            self._reflection_quota_days.add(quota_day)
            domains = tuple(sorted({item.domain for item in candidate.anomalies}))
            record = DerivedDimensionRecord(
                dimension_id=candidate.dimension_id,
                name=candidate.name,
                description=candidate.description,
                state=DerivedDimensionState.CANDIDATE,
                physical_domains=domains,
                created_at=submitted_at,
                activity_score=candidate.activity_score,
                contribution_score=candidate.contribution_score,
            )
            self._dimensions[record.dimension_id] = record
            self._trial_evidence[record.dimension_id] = {}
            return record

    def start_trial(
        self,
        dimension_id: str,
        *,
        started_at: datetime,
    ) -> DerivedDimensionRecord:
        require_aware(started_at, "started_at")
        with self._lock:
            current = self._get_locked(dimension_id)
            self._require_transition(current, DerivedDimensionState.TRIAL)
            if as_utc(started_at) < as_utc(current.created_at):
                raise ValueError("trial cannot start before candidate creation")
            updated = current.model_copy(
                update={
                    "state": DerivedDimensionState.TRIAL,
                    "trial_started_at": started_at,
                    "trial_deadline": started_at + self.TRIAL_DURATION,
                }
            )
            self._dimensions[dimension_id] = updated
            return updated

    def record_trial_evidence(self, evidence: TrialEvidence) -> TrialEvidence:
        normalized = TrialEvidence.model_validate(evidence)
        with self._lock:
            current = self._get_locked(normalized.dimension_id)
            if current.state is not DerivedDimensionState.TRIAL:
                raise IllegalDimensionTransitionError(
                    f"trial evidence requires TRIAL state, got {current.state.value}"
                )
            assert current.trial_started_at is not None
            assert current.trial_deadline is not None
            observed = as_utc(normalized.observed_at)
            if (
                not as_utc(current.trial_started_at)
                <= observed
                < as_utc(current.trial_deadline)
            ):
                raise ValueError("trial evidence must fall inside the 30-day window")
            evidence_by_day = self._trial_evidence[normalized.dimension_id]
            previous = evidence_by_day.get(normalized.utc_day)
            if previous is not None:
                if previous != normalized:
                    raise ValueError(
                        f"trial day already has different evidence: "
                        f"{normalized.utc_day}"
                    )
                return previous
            evidence_by_day[normalized.utc_day] = normalized
            return normalized

    def evaluate_trial(
        self,
        dimension_id: str,
        *,
        evaluated_at: datetime,
    ) -> TrialEvaluationReceipt:
        require_aware(evaluated_at, "evaluated_at")
        with self._lock:
            current = self._get_locked(dimension_id)
            if current.state is not DerivedDimensionState.TRIAL:
                raise IllegalDimensionTransitionError(
                    f"trial evaluation requires TRIAL state, got {current.state.value}"
                )
            assert current.trial_started_at is not None
            assert current.trial_deadline is not None
            evidence_by_day = self._trial_evidence[dimension_id]
            evaluation_utc = as_utc(evaluated_at)
            if evidence_by_day and evaluation_utc < max(
                as_utc(item.observed_at) for item in evidence_by_day.values()
            ):
                raise ValueError("trial cannot be evaluated before recorded evidence")
            coverage, accuracy, continuous = self._trial_metrics(
                current,
                evidence_by_day,
            )
            if evaluation_utc < as_utc(current.trial_deadline):
                return TrialEvaluationReceipt(
                    dimension_id=dimension_id,
                    evaluated_at=evaluated_at,
                    state=DerivedDimensionState.TRIAL,
                    finalized=False,
                    covered_days=coverage,
                    prediction_accuracy=accuracy,
                    continuous_explanation=continuous,
                )

            qualified = (
                coverage == 30
                and continuous
                and accuracy >= self.MIN_PREDICTION_ACCURACY
            )
            if not qualified:
                self._require_transition(current, DerivedDimensionState.EXPIRED)
                expired = current.model_copy(
                    update={
                        "state": DerivedDimensionState.EXPIRED,
                        "expired_at": evaluated_at,
                    }
                )
                self._dimensions[dimension_id] = expired
                return TrialEvaluationReceipt(
                    dimension_id=dimension_id,
                    evaluated_at=evaluated_at,
                    state=DerivedDimensionState.EXPIRED,
                    finalized=True,
                    covered_days=coverage,
                    prediction_accuracy=accuracy,
                    continuous_explanation=continuous,
                )

            archived_id = self._archive_lowest_if_full(
                activated_at=evaluated_at,
            )
            self._require_transition(current, DerivedDimensionState.ACTIVE)
            active = current.model_copy(
                update={
                    "state": DerivedDimensionState.ACTIVE,
                    "last_active_at": evaluated_at,
                }
            )
            self._dimensions[dimension_id] = active
            self._assert_active_cap()
            return TrialEvaluationReceipt(
                dimension_id=dimension_id,
                evaluated_at=evaluated_at,
                state=DerivedDimensionState.ACTIVE,
                finalized=True,
                covered_days=coverage,
                prediction_accuracy=accuracy,
                continuous_explanation=continuous,
                archived_dimension_id=archived_id,
            )

    def guarded_reflection(
        self,
        prompt: str,
        evaluator: ReflectionEvaluator,
        *,
        depth: int = 0,
    ) -> Any:
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ValueError("reflection depth must be a non-negative integer")
        if depth >= self.MAX_REFLECTION_DEPTH_EXCLUSIVE:
            raise ReflectionRecursionBlockError(
                f"reflection recursion physically blocked at depth {depth}"
            )
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("reflection prompt must not be blank")
        return evaluator(prompt, depth)

    def get(self, dimension_id: str) -> DerivedDimensionRecord:
        with self._lock:
            return self._get_locked(dimension_id)

    def active_dimensions(self) -> tuple[DerivedDimensionRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        record
                        for record in self._dimensions.values()
                        if record.state is DerivedDimensionState.ACTIVE
                    ),
                    key=lambda record: record.dimension_id,
                )
            )

    def archived_dimensions(self) -> tuple[DerivedDimensionRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        record
                        for record in self._dimensions.values()
                        if record.state is DerivedDimensionState.ARCHIVED
                    ),
                    key=lambda record: record.dimension_id,
                )
            )

    @classmethod
    def _validate_cross_domain_gate(
        cls,
        anomalies: tuple[PhysicalDomainAnomaly, ...],
    ) -> None:
        domains = {item.domain for item in anomalies}
        if len(domains) < cls.MIN_PHYSICAL_DOMAINS:
            raise AdmissionThresholdBlockError(
                "candidate requires anomalies in at least two physical domains"
            )
        overlap_start = max(as_utc(item.started_at) for item in anomalies)
        overlap_end = min(as_utc(item.observed_through) for item in anomalies)
        if overlap_end - overlap_start < cls.MIN_ANOMALY_DURATION:
            raise AdmissionThresholdBlockError(
                "cross-domain anomaly overlap must persist for at least three days"
            )

    @staticmethod
    def _trial_metrics(
        record: DerivedDimensionRecord,
        evidence_by_day: dict[date, TrialEvidence],
    ) -> tuple[int, float, bool]:
        assert record.trial_started_at is not None
        start_day = as_utc(record.trial_started_at).date()
        expected_days = {start_day + timedelta(days=index) for index in range(30)}
        covered_days = expected_days & set(evidence_by_day)
        evidence = [evidence_by_day[day] for day in sorted(covered_days)]
        accuracy = (
            sum(item.prediction_success for item in evidence) / len(evidence)
            if evidence
            else 0.0
        )
        continuous = len(covered_days) == 30 and all(
            item.explanation_supported for item in evidence
        )
        return len(covered_days), accuracy, continuous

    def _archive_lowest_if_full(self, *, activated_at: datetime) -> str | None:
        active = [
            record
            for record in self._dimensions.values()
            if record.state is DerivedDimensionState.ACTIVE
        ]
        if len(active) < self.MAX_ACTIVE_DIMENSIONS:
            return None
        victim = min(
            active,
            key=lambda record: (
                record.contribution_rank,
                as_utc(record.last_active_at or record.created_at),
                record.dimension_id,
            ),
        )
        self._require_transition(victim, DerivedDimensionState.ARCHIVED)
        self._dimensions[victim.dimension_id] = victim.model_copy(
            update={
                "state": DerivedDimensionState.ARCHIVED,
                "archived_at": activated_at,
            }
        )
        return victim.dimension_id

    def _require_transition(
        self,
        current: DerivedDimensionRecord,
        target: DerivedDimensionState,
    ) -> None:
        if target not in self._ALLOWED_TRANSITIONS[current.state]:
            raise IllegalDimensionTransitionError(
                f"illegal dimension transition for {current.dimension_id}: "
                f"{current.state.value} -> {target.value}"
            )

    def _get_locked(self, dimension_id: str) -> DerivedDimensionRecord:
        try:
            return self._dimensions[dimension_id]
        except KeyError as exc:
            raise KeyError(f"unknown derived dimension: {dimension_id}") from exc

    def _assert_active_cap(self) -> None:
        count = sum(
            record.state is DerivedDimensionState.ACTIVE
            for record in self._dimensions.values()
        )
        if count > self.MAX_ACTIVE_DIMENSIONS:
            raise ValueError("active derived dimensions cannot exceed 32")
