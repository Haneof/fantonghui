"""Stable cockpit information slots, not a forced reasoning chain.

The four historical labels are retained as a deterministic manifest layout so
serialization, cache shape, and token accounting remain stable. The cognitive
model may populate, revisit, or replace these slots in any order. This module
must never be used to prescribe private chain-of-thought.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

__all__ = [
    "MIND_SEQUENCE",
    "STEP_CALIBRATE_BOND",
    "STEP_INSPECT_FIELD",
    "STEP_MIRROR_SELF",
    "STEP_SET_POSTURE",
    "MindSequenceError",
    "MindSequenceRunner",
    "StepOutcome",
]

STEP_MIRROR_SELF = "MIRROR_SELF"
STEP_CALIBRATE_BOND = "CALIBRATE_BOND"
STEP_SET_POSTURE = "SET_POSTURE"
STEP_INSPECT_FIELD = "INSPECT_FIELD"

# Stable serialization layout only. It is not a cognitive execution order.
MIND_SEQUENCE: tuple[str, ...] = (
    STEP_MIRROR_SELF,
    STEP_CALIBRATE_BOND,
    STEP_SET_POSTURE,
    STEP_INSPECT_FIELD,
)

STEP_LABELS: Mapping[str, str] = {
    STEP_MIRROR_SELF: "①照镜子看自己",
    STEP_CALIBRATE_BOND: "②校准羁绊看关系",
    STEP_SET_POSTURE: "③确立姿态定语调",
    STEP_INSPECT_FIELD: "④审视现场看世界",
}


class MindSequenceError(RuntimeError):
    """Structural manifest or budget violation."""


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """One cockpit slot value with deterministic token accounting."""

    step: str
    label: str
    payload: Mapping[str, Any]
    tokens: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "label": self.label,
            "tokens": self.tokens,
            "payload": dict(self.payload),
        }


@dataclass
class MindSequenceRunner:
    """Mutable cockpit-slot collector with stable manifest serialization."""

    token_budgets: Mapping[str, int] = field(
        default_factory=lambda: {
            STEP_MIRROR_SELF: 260,
            STEP_CALIBRATE_BOND: 260,
            STEP_SET_POSTURE: 180,
            STEP_INSPECT_FIELD: 800,
        }
    )
    _outcomes: Dict[str, StepOutcome] = field(default_factory=dict)
    _call_order: List[str] = field(default_factory=list)
    _runs: int = 0

    def begin(self) -> None:
        """Start a new assembly attempt; abandoning a partial one is legal."""

        self._outcomes = {}
        self._call_order = []
        self._runs += 1

    def advance(
        self, step: str, payload: Mapping[str, Any], *, tokens: int
    ) -> StepOutcome:
        """Populate or revise any known slot; no reasoning order is enforced."""

        if step not in MIND_SEQUENCE:
            raise MindSequenceError(f"unknown cockpit slot {step!r}")
        if tokens < 0:
            raise MindSequenceError("tokens must be >= 0")
        budget = int(self.token_budgets.get(step, 0))
        if budget and tokens > budget:
            raise MindSequenceError(
                f"{STEP_LABELS[step]} 装配 Token {tokens} 超出该槽位预算 {budget}"
            )
        outcome = StepOutcome(
            step=step,
            label=STEP_LABELS[step],
            payload=dict(payload),
            tokens=int(tokens),
        )
        self._outcomes[step] = outcome
        self._call_order.append(step)
        return outcome

    def context_for(self, step: str) -> Mapping[str, Any]:
        """Return currently available slot data without positional visibility rules."""

        if step not in MIND_SEQUENCE:
            raise MindSequenceError(f"unknown cockpit slot {step!r}")
        merged: Dict[str, Any] = {}
        for slot in MIND_SEQUENCE:
            outcome = self._outcomes.get(slot)
            if outcome is not None:
                merged.update(outcome.payload)
        return merged

    @property
    def completed(self) -> bool:
        return all(step in self._outcomes for step in MIND_SEQUENCE)

    @property
    def progress(self) -> int:
        return len(self._outcomes)

    @property
    def runs(self) -> int:
        return self._runs

    def outcomes(self) -> tuple[StepOutcome, ...]:
        """Current slot values in stable serialization layout."""

        return tuple(
            self._outcomes[step]
            for step in MIND_SEQUENCE
            if step in self._outcomes
        )

    def runtime_call_order(self) -> tuple[str, ...]:
        """Audit the actual model/runtime write order without treating it as law."""

        return tuple(self._call_order)

    def manifest_tokens(self) -> int:
        return sum(outcome.tokens for outcome in self._outcomes.values())

    def as_manifest(self) -> Mapping[str, Any]:
        """Serialize a complete cockpit in stable layout."""

        if not self.completed:
            missing = [step for step in MIND_SEQUENCE if step not in self._outcomes]
            raise MindSequenceError(
                f"cockpit slots incomplete; missing: {missing}"
            )
        ordered = [self._outcomes[step] for step in MIND_SEQUENCE]
        return {
            "steps": [
                {"step": outcome.step, "label": outcome.label, "tokens": outcome.tokens}
                for outcome in ordered
            ],
            "token_count": self.manifest_tokens(),
            "order": [STEP_LABELS[step] for step in MIND_SEQUENCE],
            "runtime_call_order": list(self._call_order),
            "single_load": True,
            "backtracking_allowed": True,
            "cognitive_order_enforced": False,
        }

    @staticmethod
    def labels(sequence: Sequence[str] = MIND_SEQUENCE) -> tuple[str, ...]:
        return tuple(STEP_LABELS[step] for step in sequence)
