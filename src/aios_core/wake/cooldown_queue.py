"""M2-001 wake pulse coalescing, adaptive cooldown, and deep-sleep gate."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite
from threading import RLock
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.time import as_utc, require_aware


class SleepState(StrEnum):
    AWAKE = "AWAKE"
    DEEP_SLEEP = "DEEP_SLEEP"


class WakeUrgency(StrEnum):
    P0_LIFE_SAFETY = "P0_LIFE_SAFETY"
    P1_URGENT = "P1_URGENT"
    P2_ROUTINE = "P2_ROUTINE"


class WakeCategory(StrEnum):
    PHYSICAL_VITAL = "PHYSICAL_VITAL"
    GENERAL_NOTIFICATION = "GENERAL_NOTIFICATION"
    REFLECTION = "REFLECTION"
    TASK_REMINDER = "TASK_REMINDER"


class EnqueueStatus(StrEnum):
    MERGED = "MERGED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    P0_DISPATCHED = "P0_DISPATCHED"


class WakePulse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    event_id: str = Field(min_length=1, max_length=200)
    episode_key: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    urgency: WakeUrgency
    category: WakeCategory
    sensor_type: str = Field(min_length=1, max_length=100)
    value: float | None = None
    hardware_action_code: str | None = Field(default=None, min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=32)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "occurred_at")
        return value

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("value must be finite")
        return value

    @model_validator(mode="after")
    def p0_requires_hardware_action(self) -> WakePulse:
        if (
            self.urgency is WakeUrgency.P0_LIFE_SAFETY
            and self.hardware_action_code is None
        ):
            raise ValueError("P0 pulse requires hardware_action_code")
        if (
            self.urgency is not WakeUrgency.P0_LIFE_SAFETY
            and self.hardware_action_code is not None
        ):
            raise ValueError("non-P0 pulse cannot request a hardware action")
        return self


class WakeBatchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    batch_id: str = Field(pattern=r"^wake_batch_[0-9a-f]{24}$")
    episode_key: str
    first_occurred_at: datetime
    last_occurred_at: datetime
    event_ids: tuple[str, ...] = Field(min_length=1)
    pulse_count: int = Field(ge=1)
    sensor_types: tuple[str, ...] = Field(min_length=1)
    categories: tuple[WakeCategory, ...] = Field(min_length=1)
    urgency: WakeUrgency
    minimum_value: float | None = None
    maximum_value: float | None = None
    average_value: float | None = None

    @field_validator("first_occurred_at", "last_occurred_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime, info: Any) -> datetime:
        require_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def batch_receipt_must_be_consistent(self) -> WakeBatchEvent:
        if self.pulse_count != len(self.event_ids):
            raise ValueError("pulse_count must equal unique event_ids")
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError("event_ids must be unique")
        if as_utc(self.last_occurred_at) < as_utc(self.first_occurred_at):
            raise ValueError("last_occurred_at cannot precede first_occurred_at")
        return self


class WakePresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    presented_at: datetime
    batches: tuple[WakeBatchEvent, ...] = Field(min_length=1)
    total_unique_pulses: int = Field(ge=1)
    cooldown_until: datetime
    cooldown_seconds: int = Field(ge=900, le=1_800)
    motor_vibration_count: Literal[1] = 1

    @field_validator("presented_at", "cooldown_until")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime, info: Any) -> datetime:
        require_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def presentation_receipt_must_be_consistent(self) -> WakePresentation:
        expected = sum(batch.pulse_count for batch in self.batches)
        if self.total_unique_pulses != expected:
            raise ValueError("total_unique_pulses does not match batches")
        actual_seconds = int(
            (as_utc(self.cooldown_until) - as_utc(self.presented_at)).total_seconds()
        )
        if actual_seconds != self.cooldown_seconds:
            raise ValueError("cooldown receipt does not match timestamps")
        return self


@dataclass(slots=True)
class _BatchAccumulator:
    episode_key: str
    first_occurred_at: datetime
    last_occurred_at: datetime
    urgency: WakeUrgency
    event_ids: list[str] = field(default_factory=list)
    event_id_set: set[str] = field(default_factory=set)
    sensor_types: set[str] = field(default_factory=set)
    categories: set[WakeCategory] = field(default_factory=set)
    values: list[float] = field(default_factory=list)

    @classmethod
    def from_pulse(cls, pulse: WakePulse) -> _BatchAccumulator:
        accumulator = cls(
            episode_key=pulse.episode_key,
            first_occurred_at=pulse.occurred_at,
            last_occurred_at=pulse.occurred_at,
            urgency=pulse.urgency,
        )
        accumulator.add(pulse)
        return accumulator

    def add(self, pulse: WakePulse) -> None:
        self.event_ids.append(pulse.event_id)
        self.event_id_set.add(pulse.event_id)
        self.last_occurred_at = pulse.occurred_at
        self.sensor_types.add(pulse.sensor_type)
        self.categories.add(pulse.category)
        if pulse.value is not None:
            self.values.append(pulse.value)
        if pulse.urgency is WakeUrgency.P1_URGENT:
            self.urgency = WakeUrgency.P1_URGENT

    def freeze(self) -> WakeBatchEvent:
        identity = "\x1f".join(self.event_ids).encode("utf-8")
        digest = hashlib.sha256(identity).hexdigest()[:24]
        minimum = min(self.values) if self.values else None
        maximum = max(self.values) if self.values else None
        average = sum(self.values) / len(self.values) if self.values else None
        return WakeBatchEvent(
            batch_id=f"wake_batch_{digest}",
            episode_key=self.episode_key,
            first_occurred_at=self.first_occurred_at,
            last_occurred_at=self.last_occurred_at,
            event_ids=tuple(self.event_ids),
            pulse_count=len(self.event_ids),
            sensor_types=tuple(sorted(self.sensor_types)),
            categories=tuple(sorted(self.categories, key=lambda item: item.value)),
            urgency=self.urgency,
            minimum_value=minimum,
            maximum_value=maximum,
            average_value=average,
        )


MotorCallback = Callable[[WakePresentation], None]
EmergencyCallback = Callable[[WakePulse], None]


class WakeCooldownQueue:
    """Coalesce normal wakes; P0 bypasses batching, sleep, and cooldown."""

    MERGE_WINDOW: ClassVar[timedelta] = timedelta(seconds=5)
    MIN_COOLDOWN: ClassVar[timedelta] = timedelta(minutes=15)
    MAX_COOLDOWN: ClassVar[timedelta] = timedelta(minutes=30)

    def __init__(
        self,
        *,
        motor_vibrate: MotorCallback | None = None,
        emergency_dispatch: EmergencyCallback | None = None,
    ) -> None:
        self._motor_vibrate = motor_vibrate
        self._emergency_dispatch = emergency_dispatch
        self._sleep_state = SleepState.AWAKE
        self._open: dict[str, _BatchAccumulator] = {}
        self._pending: list[WakeBatchEvent] = []
        self._silent_backlog: list[WakeBatchEvent] = []
        self._seen_event_ids: set[str] = set()
        self._cooldown_until: datetime | None = None
        self._last_advanced_at: datetime | None = None
        self._motor_vibration_count = 0
        self._emergency_dispatch_count = 0
        self._lock = RLock()

    def enqueue(self, pulse: WakePulse) -> EnqueueStatus:
        normalized = WakePulse.model_validate(pulse)
        emergency_callback: EmergencyCallback | None = None
        with self._lock:
            if normalized.event_id in self._seen_event_ids:
                return EnqueueStatus.DUPLICATE_IGNORED
            self._seen_event_ids.add(normalized.event_id)
            if normalized.urgency is WakeUrgency.P0_LIFE_SAFETY:
                self._emergency_dispatch_count += 1
                emergency_callback = self._emergency_dispatch
            else:
                try:
                    self._merge_normal_pulse(normalized)
                except Exception:
                    self._seen_event_ids.remove(normalized.event_id)
                    raise
                return EnqueueStatus.MERGED

        if emergency_callback is not None:
            emergency_callback(normalized)
        return EnqueueStatus.P0_DISPATCHED

    def advance(self, current_time: datetime) -> WakePresentation | None:
        require_aware(current_time, "current_time")
        now = as_utc(current_time, "current_time")
        presentation: WakePresentation | None = None
        motor_callback: MotorCallback | None = None
        with self._lock:
            if self._last_advanced_at is not None and now < self._last_advanced_at:
                raise ValueError("current_time cannot move backwards")
            self._last_advanced_at = now
            self._finalize_due_batches(now)
            if self._sleep_state is SleepState.DEEP_SLEEP:
                if self._pending:
                    self._silent_backlog.extend(self._pending)
                    self._pending.clear()
                return None
            if self._cooldown_until is not None and now < as_utc(
                self._cooldown_until, "cooldown_until"
            ):
                return None
            batches = sorted(
                (*self._silent_backlog, *self._pending),
                key=lambda batch: (
                    as_utc(batch.first_occurred_at),
                    batch.batch_id,
                ),
            )
            if not batches:
                return None
            total_pulses = sum(batch.pulse_count for batch in batches)
            cooldown_seconds = self._adaptive_cooldown_seconds(total_pulses)
            cooldown_until = now + timedelta(seconds=cooldown_seconds)
            presentation = WakePresentation(
                presented_at=current_time,
                batches=tuple(batches),
                total_unique_pulses=total_pulses,
                cooldown_until=cooldown_until,
                cooldown_seconds=cooldown_seconds,
            )
            self._silent_backlog.clear()
            self._pending.clear()
            self._cooldown_until = cooldown_until
            self._motor_vibration_count += 1
            motor_callback = self._motor_vibrate

        if motor_callback is not None:
            motor_callback(presentation)
        return presentation

    def set_sleep_state(
        self,
        state: SleepState,
        *,
        observed_at: datetime,
    ) -> WakePresentation | None:
        normalized_state = SleepState(state)
        require_aware(observed_at, "observed_at")
        observed_utc = as_utc(observed_at, "observed_at")
        with self._lock:
            if (
                self._last_advanced_at is not None
                and observed_utc < self._last_advanced_at
            ):
                raise ValueError("sleep state time cannot move backwards")
            self._sleep_state = normalized_state
            if normalized_state is SleepState.DEEP_SLEEP and self._pending:
                self._silent_backlog.extend(self._pending)
                self._pending.clear()
        return self.advance(observed_at)

    def _merge_normal_pulse(self, pulse: WakePulse) -> None:
        accumulator = self._open.get(pulse.episode_key)
        if accumulator is None:
            self._open[pulse.episode_key] = _BatchAccumulator.from_pulse(pulse)
            return
        if as_utc(pulse.occurred_at) < as_utc(accumulator.last_occurred_at):
            raise ValueError("pulse time must increase within an episode")
        if (
            as_utc(pulse.occurred_at) - as_utc(accumulator.first_occurred_at)
            <= self.MERGE_WINDOW
        ):
            accumulator.add(pulse)
            return
        self._route_finalized(accumulator.freeze())
        self._open[pulse.episode_key] = _BatchAccumulator.from_pulse(pulse)

    def _finalize_due_batches(self, now: datetime) -> None:
        for episode_key, accumulator in list(self._open.items()):
            if now - as_utc(accumulator.first_occurred_at) < self.MERGE_WINDOW:
                continue
            self._route_finalized(accumulator.freeze())
            del self._open[episode_key]

    def _route_finalized(self, batch: WakeBatchEvent) -> None:
        if self._sleep_state is SleepState.DEEP_SLEEP:
            self._silent_backlog.append(batch)
        else:
            self._pending.append(batch)

    @classmethod
    def _adaptive_cooldown_seconds(cls, total_pulses: int) -> int:
        minimum = int(cls.MIN_COOLDOWN.total_seconds())
        maximum = int(cls.MAX_COOLDOWN.total_seconds())
        if total_pulses <= 1:
            return minimum
        extra = min(maximum - minimum, (total_pulses - 1) * 900 // 249)
        return minimum + extra

    @property
    def sleep_state(self) -> SleepState:
        with self._lock:
            return self._sleep_state

    @property
    def silent_batch_count(self) -> int:
        with self._lock:
            return len(self._silent_backlog)

    @property
    def pending_batch_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def motor_vibration_count(self) -> int:
        with self._lock:
            return self._motor_vibration_count

    @property
    def emergency_dispatch_count(self) -> int:
        with self._lock:
            return self._emergency_dispatch_count

    @property
    def cooldown_until(self) -> datetime | None:
        with self._lock:
            return self._cooldown_until
