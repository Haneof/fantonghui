"""Communication action audit and feedback persistence.

R5/R6 boundary
--------------
This module is deliberately not a semantic judge. The cognitive model/runtime
chooses whether to speak, intervene, or stay silent, chooses the wording, and supplies
its rationale. Python validates the shape, preserves the chosen payload, persists an
audit trail, and records evidence-linked user reactions.

No regex, keyword list, style ranking, or fixed response replacement is allowed here.
Safety hard boundaries live in the dedicated safety/permission path.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.communication.experience_tracker import ExperienceTracker
from aios_core.contracts.enums import ActionStatus, ObjectType, SourceClass, UserReaction
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import Action, CommunicationExperience, TemporalExtent
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import as_utc
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

__all__ = [
    "AIActionKind",
    "AIActionLog",
    "CommunicationHistorySnapshot",
    "CommunicationStyleGovernor",
]


class AIActionKind(StrEnum):
    """Model-selected communication action kind."""

    INTERVENTION = "intervention"
    SILENCE = "silence"
    ADVICE = "advice"


class CommunicationHistorySnapshot(BaseModel):
    """Descriptive history only; it never recommends or bans a style."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: str
    samples: int = Field(ge=0)
    reaction_counts: Mapping[str, int]
    style_counts: Mapping[str, int]
    style_acceptance_rates: Mapping[str, float]


class AIActionLog(BaseModel):
    """Auditable record of a model-selected communication action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(min_length=1)
    kind: AIActionKind
    scenario: str = Field(min_length=1)
    style: str | None = None
    content: str = ""
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[ObjectRef, ...] = ()
    token_cost: int = Field(ge=0)
    silence_reason: str | None = None
    recorded_at: datetime
    feedback: UserReaction | None = None
    feedback_source: str = "none"
    reaction_evidence_ref: ObjectRef | None = None

    @model_validator(mode="after")
    def validate_log(self) -> "AIActionLog":
        if self.kind is AIActionKind.SILENCE:
            if not (self.silence_reason or "").strip():
                raise ValueError("a model-selected silence must carry its supplied reason")
            if self.content:
                raise ValueError("a silence action must not carry user-visible content")
        elif not self.content.strip():
            raise ValueError("a speaking action must carry the model-selected content")
        if self.feedback_source not in {"passive_observation", "explicit_reply", "none"}:
            raise ValueError("feedback_source must describe an observed source")
        if self.feedback is not None and self.reaction_evidence_ref is None:
            raise ValueError("recorded feedback requires a pinned evidence reference")
        return self


class CommunicationStyleGovernor:
    """Persistence boundary for model-selected communication decisions.

    The historical name is retained to avoid a repository-wide rename, but the class
    no longer governs style. It validates and records an already-made decision.
    """

    def __init__(
        self,
        *,
        store: SQLiteWorldStore | None = None,
        tracker: ExperienceTracker | None = None,
        subject_id: str = "user_1",
    ) -> None:
        self.store = store
        self.tracker = tracker or ExperienceTracker()
        self.subject_id = subject_id
        self._logs: list[AIActionLog] = []
        self._ui_prompts = 0

    def record_action(
        self,
        *,
        kind: AIActionKind,
        scenario: str,
        content: str,
        rationale: str,
        evidence_refs: Sequence[ObjectRef] = (),
        recorded_at: datetime | None = None,
        style: str | None = None,
        silence_reason: str | None = None,
        token_cost: int | None = None,
    ) -> AIActionLog:
        """Record the decision exactly as supplied by the cognitive runtime."""

        stamp = as_utc(recorded_at or datetime.now(UTC), "recorded_at")
        cost = len(content) if token_cost is None else int(token_cost)
        log = AIActionLog(
            action_id=new_object_id(ObjectType.ACTION),
            kind=kind,
            scenario=scenario,
            style=style,
            content=content,
            rationale=rationale,
            evidence_refs=tuple(evidence_refs),
            token_cost=cost,
            silence_reason=silence_reason,
            recorded_at=stamp,
        )
        self._logs.append(log)
        if self.store is not None:
            self._persist_action(log)
        return log

    def decide(
        self,
        *,
        kind: AIActionKind | None = None,
        scenario: str,
        candidate_reply: str,
        rationale: str,
        evidence_refs: Sequence[ObjectRef] = (),
        recorded_at: datetime | None = None,
        style: str | None = None,
        silence_reason: str | None = None,
        user_text: str = "",
    ) -> AIActionLog:
        """Compatibility entry point that still requires an explicit model decision.

        user_text is intentionally ignored. This layer must not infer a decision
        from the user's words.
        """

        _ = user_text
        if kind is None:
            raise ValueError(
                "kind must be selected explicitly by the cognitive runtime; "
                "CommunicationStyleGovernor does not infer it"
            )
        return self.record_action(
            kind=kind,
            scenario=scenario,
            content=candidate_reply,
            rationale=rationale,
            evidence_refs=evidence_refs,
            recorded_at=recorded_at,
            style=style,
            silence_reason=silence_reason,
        )

    def _persist_action(self, log: AIActionLog) -> None:
        if self.store is None:
            return
        action = Action(
            object_id=log.action_id,
            subject_id=self.subject_id,
            revision=1,
            execution_id=log.action_id,
            action_type=log.kind.value,
            action_status=ActionStatus.COMPLETED,
            payload={
                "scenario": log.scenario,
                "style": log.style,
                "kind": log.kind.value,
                "content": log.content,
                "rationale": log.rationale,
                "token_cost": log.token_cost,
                "silence_reason": log.silence_reason,
                "evidence_refs": [
                    {"object_id": ref.object_id, "revision": ref.revision}
                    for ref in log.evidence_refs
                ],
            },
            expected_outcome="observed user reaction, if any",
            occurred=TemporalExtent.point(log.recorded_at),
            learned_at=log.recorded_at,
            recorded_at=log.recorded_at,
            created_by="communication_style_governor",
        )
        self.store.commit(
            [action],
            OperationRequest(
                operation_id=new_operation_id(),
                operation_name="world.ai_action.log",
                expected_world_revision=self.store.current_world_revision(),
                reason=f"record model-selected communication action: {log.kind.value}/{log.scenario}",
                idempotency_key=new_operation_id(),
                source_class=SourceClass.AI_COGNITION,
            ),
        )

    def record_feedback(
        self,
        action: AIActionLog,
        *,
        reaction: UserReaction,
        evidence_ref: ObjectRef,
        feedback_source: str = "passive_observation",
        observed_at: datetime | None = None,
        commit: bool = True,
    ) -> tuple[AIActionLog, CommunicationExperience]:
        """Persist an observed reaction; no strategy is inferred from it."""

        if evidence_ref.revision is None:
            raise ValueError("feedback evidence must pin a revision")
        if reaction is UserReaction.UNKNOWN:
            raise ValueError("UNKNOWN feedback is not persisted as known evidence")
        if feedback_source not in {"passive_observation", "explicit_reply"}:
            raise ValueError("feedback_source must be an observed source")

        stamp = as_utc(observed_at or datetime.now(UTC), "observed_at")
        updated = action.model_copy(
            update={
                "feedback": reaction,
                "feedback_source": feedback_source,
                "reaction_evidence_ref": evidence_ref,
            }
        )
        for index, entry in enumerate(self._logs):
            if entry.action_id == action.action_id:
                self._logs[index] = updated
                break

        experience = CommunicationExperience(
            object_id=new_object_id(ObjectType.COMMUNICATION_EXPERIENCE),
            subject_id=self.subject_id,
            revision=1,
            scenario=action.scenario,
            style=action.style or "unspecified",
            tone=action.kind.value,
            user_reaction=reaction,
            action_ref=ObjectRef(object_id=action.action_id, revision=1),
            applicable_conditions={
                "kind": action.kind.value,
                "feedback_source": feedback_source,
            },
            occurred=TemporalExtent.point(stamp),
            learned_at=stamp,
            recorded_at=stamp,
            created_by="communication_style_governor",
        )
        self.tracker.record_experience(experience)
        if commit and self.store is not None:
            self.store.commit(
                [experience],
                OperationRequest(
                    operation_id=new_operation_id(),
                    operation_name="world.communication.experience",
                    expected_world_revision=self.store.current_world_revision(),
                    reason=f"record observed communication feedback: {action.scenario}/{reaction.value}",
                    idempotency_key=new_operation_id(),
                    source_class=SourceClass.AI_COGNITION,
                ),
            )
        return updated, experience

    def history_snapshot(self, scenario: str) -> CommunicationHistorySnapshot:
        """Return descriptive evidence statistics without making a style decision."""

        experiences = self.tracker.get_experiences_by_scenario(scenario)
        reaction_counts = Counter(exp.user_reaction.value for exp in experiences)
        style_counts = Counter(exp.style for exp in experiences)
        accepted: dict[str, int] = defaultdict(int)
        totals: dict[str, int] = defaultdict(int)
        for exp in experiences:
            totals[exp.style] += 1
            if exp.user_reaction is UserReaction.ACCEPTED:
                accepted[exp.style] += 1
        rates = {
            style: accepted[style] / total
            for style, total in sorted(totals.items())
            if total
        }
        return CommunicationHistorySnapshot(
            scenario=scenario,
            samples=len(experiences),
            reaction_counts=dict(sorted(reaction_counts.items())),
            style_counts=dict(sorted(style_counts.items())),
            style_acceptance_rates=rates,
        )

    def style_landscape(self) -> dict[str, dict[str, float]]:
        """Observed action/feedback counts only; no ranking is produced."""

        by_style: dict[str, list[AIActionLog]] = defaultdict(list)
        for log in self._logs:
            by_style[log.style or "unspecified"].append(log)
        landscape: dict[str, dict[str, float]] = {}
        for style, logs in sorted(by_style.items()):
            rated = [log for log in logs if log.feedback is not None]
            accepted = sum(1 for log in rated if log.feedback is UserReaction.ACCEPTED)
            landscape[style] = {
                "actions": float(len(logs)),
                "rated_actions": float(len(rated)),
                "acceptance_rate": (accepted / len(rated)) if rated else 0.0,
            }
        return landscape

    @property
    def ui_prompts_issued(self) -> int:
        return self._ui_prompts

    def issue_ui_prompt(self, prompt: str) -> None:
        if not prompt.strip():
            raise ValueError("an empty prompt is still a prompt")
        self._ui_prompts += 1

    def assert_zero_surface(self) -> None:
        if self._ui_prompts:
            raise AssertionError("cockpit surface emitted a questionnaire/confirmation prompt")

    def logs(self) -> tuple[AIActionLog, ...]:
        return tuple(self._logs)

    def logs_of_kind(self, kind: AIActionKind) -> tuple[AIActionLog, ...]:
        return tuple(log for log in self._logs if log.kind is kind)
