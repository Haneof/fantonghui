"""M2-005R conditional scheduling with a zero-token dormant lane.

Level-1 conditions are evaluated locally and can only move a task from
``DORMANT`` to ``READY``.  Level-2 conditions have no autonomous evaluation
entry point: they are considered only while piggybacking on a relevant,
user-initiated wake.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.time import as_utc, require_aware


class ConditionalTaskState(StrEnum):
    DORMANT = "DORMANT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


class ConditionTrack(StrEnum):
    LEVEL_1_MECHANICAL = "LEVEL_1_MECHANICAL"
    LEVEL_2_SEMANTIC = "LEVEL_2_SEMANTIC"


class MechanicalConditionKind(StrEnum):
    ABSOLUTE_TIME = "ABSOLUTE_TIME"
    GEOFENCE = "GEOFENCE"
    HEART_RATE_THRESHOLD = "HEART_RATE_THRESHOLD"


class IllegalStateTransitionError(RuntimeError):
    """Raised before an invalid conditional-task state change can execute."""

    def __init__(
        self,
        task_id: str,
        current: ConditionalTaskState,
        target: ConditionalTaskState,
    ) -> None:
        self.task_id = task_id
        self.current = current
        self.target = target
        super().__init__(
            f"illegal conditional task transition for {task_id}: "
            f"{current.value} -> {target.value}"
        )


class MechanicalCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    kind: MechanicalConditionKind
    due_at: datetime | None = None
    geofence_id: str | None = Field(default=None, min_length=1, max_length=160)
    min_heart_rate_bpm: float | None = Field(default=None, ge=1.0, le=300.0)
    required_consecutive_evenings: int = Field(default=1, ge=1, le=365)

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_aware(cls, value: datetime | None) -> datetime | None:
        require_aware(value, "due_at")
        return value

    @model_validator(mode="after")
    def fields_must_match_kind(self) -> MechanicalCondition:
        if self.kind is MechanicalConditionKind.ABSOLUTE_TIME:
            if self.due_at is None:
                raise ValueError("ABSOLUTE_TIME requires due_at")
            if self.geofence_id is not None or self.min_heart_rate_bpm is not None:
                raise ValueError("ABSOLUTE_TIME rejects unrelated condition fields")
            if self.required_consecutive_evenings != 1:
                raise ValueError("ABSOLUTE_TIME cannot require consecutive evenings")
        elif self.kind is MechanicalConditionKind.GEOFENCE:
            if self.geofence_id is None:
                raise ValueError("GEOFENCE requires geofence_id")
            if self.due_at is not None or self.min_heart_rate_bpm is not None:
                raise ValueError("GEOFENCE rejects unrelated condition fields")
            if self.required_consecutive_evenings != 1:
                raise ValueError("GEOFENCE cannot require consecutive evenings")
        elif self.kind is MechanicalConditionKind.HEART_RATE_THRESHOLD:
            if self.min_heart_rate_bpm is None:
                raise ValueError("HEART_RATE_THRESHOLD requires min_heart_rate_bpm")
            if self.due_at is not None or self.geofence_id is not None:
                raise ValueError(
                    "HEART_RATE_THRESHOLD rejects unrelated condition fields"
                )
        return self


class SemanticCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    relevant_scene_tags: frozenset[str] = Field(min_length=1, max_length=32)
    evaluation_question: str = Field(min_length=1, max_length=2_000)

    @field_validator("relevant_scene_tags")
    @classmethod
    def scene_tags_must_be_non_blank(cls, values: frozenset[str]) -> frozenset[str]:
        normalized = frozenset(value.strip().casefold() for value in values)
        if "" in normalized:
            raise ValueError("relevant_scene_tags must not contain blanks")
        return normalized


class ConditionalTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    task_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=4_096)
    track: ConditionTrack
    state: ConditionalTaskState = ConditionalTaskState.DORMANT
    created_at: datetime
    mechanical_condition: MechanicalCondition | None = None
    semantic_condition: SemanticCondition | None = None

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "created_at")
        return value

    @model_validator(mode="after")
    def track_must_have_exactly_one_condition(self) -> ConditionalTask:
        if self.track is ConditionTrack.LEVEL_1_MECHANICAL:
            if self.mechanical_condition is None or self.semantic_condition is not None:
                raise ValueError("Level-1 task requires only mechanical_condition")
        elif self.semantic_condition is None or self.mechanical_condition is not None:
            raise ValueError("Level-2 task requires only semantic_condition")
        return self


class MechanicalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: datetime
    active_geofences: frozenset[str] = Field(default_factory=frozenset)
    heart_rate_bpm: float | None = Field(default=None, ge=1.0, le=300.0)
    consecutive_evening_days_above_threshold: int = Field(default=0, ge=0, le=365)

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "observed_at")
        return value


class UserWakeContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    user_initiated: bool
    scene_tags: frozenset[str] = Field(default_factory=frozenset, max_length=32)
    semantic_context: str = Field(default="", max_length=16_384)

    @field_validator("scene_tags")
    @classmethod
    def normalize_scene_tags(cls, values: frozenset[str]) -> frozenset[str]:
        normalized = frozenset(value.strip().casefold() for value in values)
        if "" in normalized:
            raise ValueError("scene_tags must not contain blanks")
        return normalized


class CockpitTaskProjection(BaseModel):
    """Physical prompt fragment; dormant tasks can never enter this model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fragment: str
    token_count: int = Field(ge=0)
    visible_task_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def receipt_must_match_physical_fragment(self) -> CockpitTaskProjection:
        if self.token_count != len(self.fragment.encode("utf-8")):
            raise ValueError("token_count must equal the physical UTF-8 envelope")
        if not self.visible_task_ids and (self.fragment or self.token_count):
            raise ValueError("empty visibility must use an empty zero-token fragment")
        return self


SemanticEvaluator = Callable[[ConditionalTask, UserWakeContext], bool]


class ConditionalScheduler:
    """Thread-safe dual-track scheduler with a strict four-state lifecycle."""

    _ALLOWED_TRANSITIONS: ClassVar[
        dict[ConditionalTaskState, frozenset[ConditionalTaskState]]
    ] = {
        ConditionalTaskState.DORMANT: frozenset({ConditionalTaskState.READY}),
        ConditionalTaskState.READY: frozenset({ConditionalTaskState.RUNNING}),
        ConditionalTaskState.RUNNING: frozenset({ConditionalTaskState.COMPLETED}),
        ConditionalTaskState.COMPLETED: frozenset(),
    }

    def __init__(self, tasks: Iterable[ConditionalTask] = ()) -> None:
        self._tasks: dict[str, ConditionalTask] = {}
        self._lock = RLock()
        self._mechanical_evaluation_count = 0
        self._semantic_evaluation_count = 0
        for task in tasks:
            self.register(task)

    def register(self, task: ConditionalTask) -> None:
        normalized = ConditionalTask.model_validate(task)
        if normalized.state is not ConditionalTaskState.DORMANT:
            raise ValueError("new conditional tasks must enter as DORMANT")
        with self._lock:
            previous = self._tasks.get(normalized.task_id)
            if previous is not None:
                if previous != normalized:
                    raise ValueError(
                        f"task_id already registered with different content: "
                        f"{normalized.task_id}"
                    )
                return
            self._tasks[normalized.task_id] = normalized

    def evaluate_level1(self, snapshot: MechanicalSnapshot) -> tuple[str, ...]:
        """Evaluate physical facts locally; this method has no model callback."""

        current = MechanicalSnapshot.model_validate(snapshot)
        ready: list[str] = []
        with self._lock:
            for task_id, task in self._tasks.items():
                if (
                    task.state is ConditionalTaskState.DORMANT
                    and task.track is ConditionTrack.LEVEL_1_MECHANICAL
                ):
                    self._mechanical_evaluation_count += 1
                    condition = task.mechanical_condition
                    if condition is not None and self._mechanical_matches(
                        condition, current
                    ):
                        self._tasks[task_id] = task.model_copy(
                            update={"state": ConditionalTaskState.READY}
                        )
                        ready.append(task_id)
        return tuple(ready)

    def piggyback_on_user_wake(
        self,
        context: UserWakeContext,
        evaluator: SemanticEvaluator,
    ) -> tuple[str, ...]:
        """Evaluate relevant semantic tasks only on an explicit user wake."""

        wake = UserWakeContext.model_validate(context)
        if not wake.user_initiated or not wake.scene_tags:
            return ()
        with self._lock:
            candidates = tuple(
                task
                for task in self._tasks.values()
                if task.state is ConditionalTaskState.DORMANT
                and task.track is ConditionTrack.LEVEL_2_SEMANTIC
                and task.semantic_condition is not None
                and bool(task.semantic_condition.relevant_scene_tags & wake.scene_tags)
            )

        ready: list[str] = []
        for task in candidates:
            with self._lock:
                self._semantic_evaluation_count += 1
            decision = evaluator(task, wake)
            if not isinstance(decision, bool):
                raise TypeError("semantic evaluator must return bool")
            if not decision:
                continue
            with self._lock:
                current = self._tasks[task.task_id]
                if current.state is ConditionalTaskState.DORMANT:
                    self._tasks[task.task_id] = current.model_copy(
                        update={"state": ConditionalTaskState.READY}
                    )
                    ready.append(task.task_id)
        return tuple(ready)

    def transition(
        self,
        task_id: str,
        target: ConditionalTaskState,
    ) -> ConditionalTask:
        normalized_target = ConditionalTaskState(target)
        with self._lock:
            try:
                current = self._tasks[task_id]
            except KeyError as exc:
                raise KeyError(f"unknown conditional task: {task_id}") from exc
            if normalized_target not in self._ALLOWED_TRANSITIONS[current.state]:
                raise IllegalStateTransitionError(
                    task_id,
                    current.state,
                    normalized_target,
                )
            updated = current.model_copy(update={"state": normalized_target})
            self._tasks[task_id] = updated
            return updated

    def cockpit_projection(self) -> CockpitTaskProjection:
        """Serialize READY work only; all DORMANT task bytes are absent."""

        with self._lock:
            visible = tuple(
                sorted(
                    (
                        task
                        for task in self._tasks.values()
                        if task.state is ConditionalTaskState.READY
                    ),
                    key=lambda item: (as_utc(item.created_at), item.task_id),
                )
            )
        if not visible:
            return CockpitTaskProjection(fragment="", token_count=0)
        payload: list[dict[str, Any]] = [
            {"state": task.state.value, "task_id": task.task_id, "title": task.title}
            for task in visible
        ]
        fragment = "[READY_CONDITIONAL_TASKS]" + json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return CockpitTaskProjection(
            fragment=fragment,
            token_count=len(fragment.encode("utf-8")),
            visible_task_ids=tuple(task.task_id for task in visible),
        )

    def get(self, task_id: str) -> ConditionalTask:
        with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as exc:
                raise KeyError(f"unknown conditional task: {task_id}") from exc

    def snapshot(self) -> tuple[ConditionalTask, ...]:
        with self._lock:
            return tuple(self._tasks[key] for key in sorted(self._tasks))

    @property
    def mechanical_evaluation_count(self) -> int:
        with self._lock:
            return self._mechanical_evaluation_count

    @property
    def semantic_evaluation_count(self) -> int:
        with self._lock:
            return self._semantic_evaluation_count

    @property
    def level1_model_call_count(self) -> Literal[0]:
        return 0

    @staticmethod
    def _mechanical_matches(
        condition: MechanicalCondition,
        snapshot: MechanicalSnapshot,
    ) -> bool:
        if condition.kind is MechanicalConditionKind.ABSOLUTE_TIME:
            return condition.due_at is not None and as_utc(
                snapshot.observed_at, "observed_at"
            ) >= as_utc(condition.due_at, "due_at")
        if condition.kind is MechanicalConditionKind.GEOFENCE:
            return condition.geofence_id in snapshot.active_geofences
        return (
            snapshot.heart_rate_bpm is not None
            and condition.min_heart_rate_bpm is not None
            and snapshot.heart_rate_bpm >= condition.min_heart_rate_bpm
            and snapshot.consecutive_evening_days_above_threshold
            >= condition.required_consecutive_evenings
        )
