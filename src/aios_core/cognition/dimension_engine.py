"""M5 high-order dimension lifecycle with anti-explosion hard gates.

A high-order label is not created from a clever story.  It must be backed by a
three-day consecutive cross-domain anomaly streak, survive a thirty-day
prediction trial, and consume the single global reflection quota for each day
on which it is evaluated.  Registration creates append-only overlays; it never
rewrites historical world objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from threading import RLock
from types import MappingProxyType
from typing import ClassVar
from uuid import uuid4


class DimensionStatus(StrEnum):
    UNINIT = "uninit"
    PROPOSED = "proposed"
    CANDIDATE = "candidate"
    REGISTERED = "registered"
    REJECTED = "rejected"


class HighOrderDimension(StrEnum):
    BURNOUT_RISK = "DIM_BURNOUT_RISK"
    CREDIT_RISK = "DIM_CREDIT_RISK"
    PARENT_HEALTH = "DIM_PARENT_HEALTH"


_DOMAIN_ALIASES = MappingProxyType(
    {
        "heart": "health",
        "heart_rate": "health",
        "arrhythmia": "health",
        "biometrics": "health",
        "health": "health",
        "bill": "finance",
        "billing": "finance",
        "transaction": "finance",
        "expense": "finance",
        "finance": "finance",
        "chat": "social",
        "message": "social",
        "conversation": "social",
        "social": "social",
        "sleep": "sleep",
        "late_night": "sleep",
        "work": "work",
        "work_log": "work",
        "calendar": "work",
    }
)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("time must be a datetime")
    # The first public M5 draft accepted naive fixture times.  Preserve that
    # API by interpreting them as UTC, while all internal comparisons use UTC.
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_domain(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("anomaly domain must not be blank")
    normalized = "_".join(value.casefold().replace("-", " ").split())
    return _DOMAIN_ALIASES.get(normalized, normalized)


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    timestamp: datetime
    domain: str
    description: str
    event_id: str = field(default_factory=lambda: f"anomaly_{uuid4().hex}")
    severity: float = 1.0
    evidence_object_id: str | None = None

    def __post_init__(self) -> None:
        _utc(self.timestamp)
        object.__setattr__(self, "domain", _normalize_domain(self.domain))
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("anomaly description must not be blank")
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must not be blank")
        if isinstance(self.severity, bool) or not isinstance(
            self.severity, (int, float)
        ):
            raise TypeError("severity must be numeric")
        if not 0.0 <= float(self.severity) <= 1.0:
            raise ValueError("severity must be between 0 and 1")
        object.__setattr__(self, "severity", float(self.severity))
        if self.evidence_object_id is not None and not self.evidence_object_id.strip():
            raise ValueError("evidence_object_id must not be blank")


@dataclass(frozen=True, slots=True)
class AnomalyStreak:
    start_date: date
    end_date: date
    active_dates: tuple[date, ...]
    domains: frozenset[str]
    event_ids: tuple[str, ...]

    @property
    def days(self) -> int:
        return len(self.active_dates)


class CrossDimensionalAnomalyDetector:
    """Detect consecutive UTC calendar-day anomalies across physical domains."""

    def __init__(self) -> None:
        self._events: dict[str, AnomalyEvent] = {}
        self._lock = RLock()

    @property
    def events(self) -> tuple[AnomalyEvent, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._events.values(),
                    key=lambda event: (_utc(event.timestamp), event.event_id),
                )
            )

    def add_event(self, event: AnomalyEvent) -> bool:
        normalized = event if isinstance(event, AnomalyEvent) else AnomalyEvent(**event)
        with self._lock:
            previous = self._events.get(normalized.event_id)
            if previous is not None:
                if previous != normalized:
                    raise ValueError(
                        f"event_id has conflicting immutable content: {normalized.event_id}"
                    )
                return False
            self._events[normalized.event_id] = normalized
            return True

    def qualifying_streak(
        self,
        current_time: datetime,
        required_days: int = 3,
        *,
        required_domains: frozenset[str] | set[str] | None = None,
        minimum_distinct_domains: int = 2,
    ) -> AnomalyStreak | None:
        if isinstance(required_days, bool) or required_days < 1:
            raise ValueError("required_days must be a positive integer")
        if isinstance(minimum_distinct_domains, bool) or minimum_distinct_domains < 2:
            raise ValueError("cross-domain detection requires at least two domains")
        now = _utc(current_time)
        today = now.date()
        earliest = today - timedelta(days=required_days)
        normalized_required = frozenset(
            _normalize_domain(domain) for domain in (required_domains or ())
        )

        by_day: dict[date, list[AnomalyEvent]] = {}
        for event in self.events:
            event_time = _utc(event.timestamp)
            event_day = event_time.date()
            if (
                earliest <= event_day <= today
                and event_time <= now
                and event.severity > 0.0
            ):
                by_day.setdefault(event_day, []).append(event)

        qualifying: list[AnomalyStreak] = []
        for start in sorted(by_day):
            active_dates = tuple(
                start + timedelta(days=offset) for offset in range(required_days)
            )
            if active_dates[-1] > today or any(
                day not in by_day for day in active_dates
            ):
                continue
            streak_events = [
                event for day in active_dates for event in by_day.get(day, ())
            ]
            domains = frozenset(event.domain for event in streak_events)
            if len(domains) < minimum_distinct_domains:
                continue
            if normalized_required and not normalized_required <= domains:
                continue
            qualifying.append(
                AnomalyStreak(
                    start_date=active_dates[0],
                    end_date=active_dates[-1],
                    active_dates=active_dates,
                    domains=domains,
                    event_ids=tuple(sorted(event.event_id for event in streak_events)),
                )
            )
        if not qualifying:
            return None
        return max(qualifying, key=lambda streak: streak.end_date)

    def detect_continuous_anomaly(
        self,
        current_time: datetime,
        required_days: int = 3,
    ) -> bool:
        return self.qualifying_streak(current_time, required_days) is not None


@dataclass(frozen=True, slots=True)
class DimensionState:
    name: str
    status: DimensionStatus = DimensionStatus.UNINIT
    proposal_time: datetime | None = None
    last_reflection_time: date | None = None
    reflection_count_today: int = 0
    predictions_attempted: int = 0
    predictions_validated: int = 0
    prediction_ids: frozenset[str] = field(default_factory=frozenset)
    anomaly_dates: tuple[date, ...] = ()
    anomaly_domains: frozenset[str] = field(default_factory=frozenset)
    anomaly_event_ids: tuple[str, ...] = ()
    registered_at: datetime | None = None


class DimensionLifecycleStateMachine:
    """Enforce all three gates without weighted scores or discretionary bypass."""

    REQUIRED_ANOMALY_DAYS: ClassVar[int] = 3
    TRIAL_DURATION: ClassVar[timedelta] = timedelta(days=30)

    def __init__(self, detector: CrossDimensionalAnomalyDetector | None = None) -> None:
        self._dimensions: dict[str, DimensionState] = {}
        self.detector = detector or CrossDimensionalAnomalyDetector()
        # Global, not per-dimension: opening two candidates cannot mint a second
        # same-day introspection budget.
        self._reflection_quota_days: set[date] = set()
        self._lock = RLock()

    @property
    def dimensions(self) -> MappingProxyType:
        return MappingProxyType(self._dimensions)

    def propose_dimension(
        self,
        name: str,
        current_time: datetime,
        *,
        required_domains: frozenset[str] | set[str] | None = None,
    ) -> DimensionState:
        normalized_name = self._normalize_name(name)
        now = _utc(current_time)
        with self._lock:
            if normalized_name in self._dimensions:
                raise ValueError(f"Dimension '{normalized_name}' already exists.")
            streak = self.detector.qualifying_streak(
                now,
                self.REQUIRED_ANOMALY_DAYS,
                required_domains=required_domains,
            )
            if streak is None:
                raise ValueError(
                    f"Cannot propose dimension '{normalized_name}'. "
                    "Threshold 1 (3-day physical cross-domain anomaly) not met."
                )
            state = DimensionState(
                name=normalized_name,
                status=DimensionStatus.CANDIDATE,
                proposal_time=now,
                anomaly_dates=streak.active_dates,
                anomaly_domains=streak.domains,
                anomaly_event_ids=streak.event_ids,
            )
            self._dimensions[normalized_name] = state
            return state

    def reflect_and_validate(
        self,
        name: str,
        current_time: datetime,
        successful_prediction: bool,
        *,
        prediction_id: str | None = None,
    ) -> DimensionState:
        normalized_name = self._normalize_name(name)
        now = _utc(current_time)
        if not isinstance(successful_prediction, bool):
            raise TypeError("successful_prediction must be a bool")
        with self._lock:
            state = self._candidate(normalized_name)
            assert state.proposal_time is not None
            if now < _utc(state.proposal_time):
                raise ValueError("reflection cannot precede candidate proposal")
            quota_day = now.date()
            if quota_day in self._reflection_quota_days:
                raise ValueError("Threshold 3 (Daily reflection quota of 1) exceeded.")
            normalized_prediction_id = prediction_id or (
                f"{normalized_name}:{quota_day.isoformat()}"
            )
            if not normalized_prediction_id.strip():
                raise ValueError("prediction_id must not be blank")
            if normalized_prediction_id in state.prediction_ids:
                raise ValueError("prediction_id has already been evaluated")

            # Quota is consumed by the attempt, including an unsuccessful one.
            self._reflection_quota_days.add(quota_day)
            object.__setattr__(state, "last_reflection_time", quota_day)
            object.__setattr__(state, "reflection_count_today", 1)
            object.__setattr__(
                state,
                "predictions_attempted",
                state.predictions_attempted + 1,
            )
            object.__setattr__(
                state,
                "prediction_ids",
                state.prediction_ids | {normalized_prediction_id},
            )
            if successful_prediction:
                object.__setattr__(
                    state,
                    "predictions_validated",
                    state.predictions_validated + 1,
                )
            return state

    def attempt_register(
        self,
        name: str,
        current_time: datetime,
    ) -> DimensionState:
        normalized_name = self._normalize_name(name)
        now = _utc(current_time)
        with self._lock:
            state = self._candidate(normalized_name)
            assert state.proposal_time is not None
            elapsed = now - _utc(state.proposal_time)
            if elapsed < self.TRIAL_DURATION:
                completed_days = max(0, elapsed.days)
                raise ValueError(
                    f"Cannot register dimension '{normalized_name}'. Threshold 2 "
                    f"(30-day trial period) not met. Current days: {completed_days}"
                )
            if state.predictions_validated <= 0:
                raise ValueError(
                    f"Cannot register dimension '{normalized_name}'. Threshold 2 "
                    "(Prediction validation) not met."
                )
            object.__setattr__(state, "status", DimensionStatus.REGISTERED)
            object.__setattr__(state, "registered_at", now)
            return state

    def reflection_quota_used(self, when: datetime) -> bool:
        return _utc(when).date() in self._reflection_quota_days

    def _candidate(self, name: str) -> DimensionState:
        state = self._dimensions.get(name)
        if state is None:
            raise ValueError(f"Dimension '{name}' not found.")
        if state.status is not DimensionStatus.CANDIDATE:
            raise ValueError(f"Dimension '{name}' is not in CANDIDATE status.")
        return state

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("dimension name must not be blank")
        return name.strip().upper()


@dataclass(frozen=True, slots=True)
class HighOrderDimensionDefinition:
    name: HighOrderDimension
    required_domains: frozenset[str]
    description: str


class HighOrderDimensionDistiller:
    """A closed allowlist prevents arbitrary narrative dimensions from spawning."""

    DEFINITIONS: ClassVar[MappingProxyType] = MappingProxyType(
        {
            HighOrderDimension.BURNOUT_RISK.value: HighOrderDimensionDefinition(
                name=HighOrderDimension.BURNOUT_RISK,
                required_domains=frozenset({"health", "sleep"}),
                description="身心衰竭指数",
            ),
            HighOrderDimension.CREDIT_RISK.value: HighOrderDimensionDefinition(
                name=HighOrderDimension.CREDIT_RISK,
                required_domains=frozenset({"finance", "social"}),
                description="商业信用风险",
            ),
            HighOrderDimension.PARENT_HEALTH.value: HighOrderDimensionDefinition(
                name=HighOrderDimension.PARENT_HEALTH,
                required_domains=frozenset({"health", "social"}),
                description="亲情健康关切",
            ),
        }
    )

    def __init__(self, state_machine: DimensionLifecycleStateMachine) -> None:
        self.state_machine = state_machine

    def distill(
        self,
        name: str,
        current_time: datetime,
    ) -> DimensionState | None:
        normalized = DimensionLifecycleStateMachine._normalize_name(name)
        definition = self.DEFINITIONS.get(normalized)
        if definition is None:
            return None
        try:
            return self.state_machine.propose_dimension(
                normalized,
                current_time,
                required_domains=definition.required_domains,
            )
        except ValueError:
            return None


@dataclass(slots=True)
class Entity:
    id: str
    _dimension_tags: set[str] = field(default_factory=set, repr=False)
    target_kind: str = field(default="entity", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("entity id must not be blank")

    @property
    def tags(self) -> frozenset[str]:
        return frozenset(self._dimension_tags)

    def _mount_dimension(self, name: str) -> None:
        self._dimension_tags.add(name)


@dataclass(slots=True)
class Relation:
    id: str
    _dimension_tags: set[str] = field(default_factory=set, repr=False)
    target_kind: str = field(default="relation", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("relation id must not be blank")

    @property
    def tags(self) -> frozenset[str]:
        return frozenset(self._dimension_tags)

    def _mount_dimension(self, name: str) -> None:
        self._dimension_tags.add(name)


@dataclass(slots=True)
class Event:
    id: str
    _dimension_tags: set[str] = field(default_factory=set, repr=False)
    target_kind: str = field(default="event", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("event id must not be blank")

    @property
    def tags(self) -> frozenset[str]:
        return frozenset(self._dimension_tags)

    def _mount_dimension(self, name: str) -> None:
        self._dimension_tags.add(name)


@dataclass(frozen=True, slots=True)
class DimensionOverlay:
    target_kind: str
    target_id: str
    dimension_name: str
    mounted_at: datetime


class DimensionOverlayOperator:
    """Mount registered dimensions as append-only, externally read-only labels."""

    def __init__(self) -> None:
        self._overlays: dict[tuple[str, str, str], DimensionOverlay] = {}
        self._lock = RLock()

    def overlay_dimension(
        self,
        entity: Entity | Relation | Event,
        dimension: DimensionState,
        *,
        current_time: datetime | None = None,
    ) -> DimensionOverlay:
        if dimension.status is not DimensionStatus.REGISTERED:
            raise ValueError(
                f"Cannot overlay unregistered dimension '{dimension.name}'."
            )
        when = _utc(current_time or datetime.now(UTC))
        key = (entity.target_kind, entity.id, dimension.name)
        with self._lock:
            overlay = self._overlays.get(key)
            if overlay is None:
                overlay = DimensionOverlay(
                    target_kind=entity.target_kind,
                    target_id=entity.id,
                    dimension_name=dimension.name,
                    mounted_at=when,
                )
                self._overlays[key] = overlay
                entity._mount_dimension(dimension.name)
            return overlay

    def overlays_for(
        self,
        target: Entity | Relation | Event,
    ) -> tuple[DimensionOverlay, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        overlay
                        for overlay in self._overlays.values()
                        if overlay.target_kind == target.target_kind
                        and overlay.target_id == target.id
                    ),
                    key=lambda overlay: (overlay.mounted_at, overlay.dimension_name),
                )
            )
