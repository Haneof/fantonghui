"""R5 AI Cognitive Runtime: bounded, auditable, model-driven tool loop.

This module intentionally does not encode a mandatory WAKE/ORIENT/RECALL thought
sequence. The model receives a compact snapshot and capability catalog, then decides
whether to answer, stay silent, or request capabilities. Deterministic code only
executes calls, enforces budgets/authorization, records results, and terminates loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .capabilities import (
    CapabilityCall,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
)


@dataclass(frozen=True)
class ModelDirective:
    """Observable model decision surface; never carries hidden chain-of-thought."""

    capability_calls: tuple[CapabilityCall, ...] = ()
    response: str | None = None
    silence: bool = False

    def __post_init__(self) -> None:
        terminal_count = int(self.response is not None) + int(self.silence)
        if self.capability_calls and terminal_count:
            raise ValueError("directive cannot request capabilities and terminate simultaneously")
        if not self.capability_calls and terminal_count != 1:
            raise ValueError("directive must either request capabilities, respond, or stay silent")
        if self.response is not None and not self.response.strip():
            raise ValueError("response must be non-blank when provided")


@dataclass(frozen=True)
class RuntimeSnapshot:
    user_input: str
    wake_reason: str
    cockpit: Mapping[str, Any]
    capability_catalog: tuple[Mapping[str, Any], ...]
    capability_history: tuple[CapabilityResult, ...]
    round_index: int
    remaining_tool_rounds: int


@dataclass(frozen=True)
class RuntimeTurnResult:
    response: str | None
    silenced: bool
    capability_history: tuple[CapabilityResult, ...]
    model_rounds: int
    termination_reason: str


ModelHandler = Callable[[RuntimeSnapshot], ModelDirective]
SideEffectAuthorizer = Callable[[CapabilitySpec, CapabilityCall, RuntimeSnapshot], bool]


class CognitiveRuntime:
    """Thin Executive Plane that lets the model drive registered capabilities."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        model_handler: ModelHandler,
        max_tool_rounds: int = 4,
        max_total_capability_calls: int = 12,
        repeated_call_limit: int = 2,
        side_effect_authorizer: SideEffectAuthorizer | None = None,
    ) -> None:
        if max_tool_rounds < 0:
            raise ValueError("max_tool_rounds must be >= 0")
        if max_total_capability_calls < 1:
            raise ValueError("max_total_capability_calls must be >= 1")
        if repeated_call_limit < 1:
            raise ValueError("repeated_call_limit must be >= 1")
        self.registry = registry
        self.model_handler = model_handler
        self.max_tool_rounds = max_tool_rounds
        self.max_total_capability_calls = max_total_capability_calls
        self.repeated_call_limit = repeated_call_limit
        self.side_effect_authorizer = side_effect_authorizer

    def _snapshot(
        self,
        *,
        user_input: str,
        wake_reason: str,
        cockpit: Mapping[str, Any],
        history: Sequence[CapabilityResult],
        round_index: int,
    ) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            user_input=user_input,
            wake_reason=wake_reason,
            cockpit=dict(cockpit),
            capability_catalog=tuple(self.registry.catalog()),
            capability_history=tuple(history),
            round_index=round_index,
            remaining_tool_rounds=max(0, self.max_tool_rounds - round_index),
        )

    def run_turn(
        self,
        user_input: str,
        *,
        wake_reason: str = "user_interaction",
        cockpit: Mapping[str, Any] | None = None,
    ) -> RuntimeTurnResult:
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be non-blank")

        history: list[CapabilityResult] = []
        signature_counts: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        total_calls = 0
        cockpit_data = dict(cockpit or {})

        # round_index counts model decisions, not a prescribed thought stage.
        for round_index in range(self.max_tool_rounds + 1):
            snapshot = self._snapshot(
                user_input=user_input,
                wake_reason=wake_reason,
                cockpit=cockpit_data,
                history=history,
                round_index=round_index,
            )
            directive = self.model_handler(snapshot)
            if not isinstance(directive, ModelDirective):
                raise TypeError("model_handler must return ModelDirective")

            if directive.response is not None:
                return RuntimeTurnResult(
                    response=directive.response,
                    silenced=False,
                    capability_history=tuple(history),
                    model_rounds=round_index + 1,
                    termination_reason="responded",
                )
            if directive.silence:
                return RuntimeTurnResult(
                    response=None,
                    silenced=True,
                    capability_history=tuple(history),
                    model_rounds=round_index + 1,
                    termination_reason="silence",
                )

            # At the final allowed model round, new tool requests are not executed.
            # We fail closed rather than silently granting unbounded autonomous loops.
            if round_index >= self.max_tool_rounds:
                return RuntimeTurnResult(
                    response=None,
                    silenced=False,
                    capability_history=tuple(history),
                    model_rounds=round_index + 1,
                    termination_reason="tool_round_budget_exhausted",
                )

            for call in directive.capability_calls:
                if total_calls >= self.max_total_capability_calls:
                    return RuntimeTurnResult(
                        response=None,
                        silenced=False,
                        capability_history=tuple(history),
                        model_rounds=round_index + 1,
                        termination_reason="capability_call_budget_exhausted",
                    )

                signature = call.normalized_signature()
                seen = signature_counts.get(signature, 0)
                if seen >= self.repeated_call_limit:
                    history.append(
                        CapabilityResult(
                            name=call.name,
                            ok=False,
                            error_code="REPEATED_CAPABILITY_CALL_BLOCKED",
                            error_message=(
                                "same capability call repeated beyond runtime loop guard; "
                                "change query path or terminate"
                            ),
                            call_id=call.call_id,
                        )
                    )
                    continue
                signature_counts[signature] = seen + 1

                try:
                    spec = self.registry.get_spec(call.name)
                except KeyError:
                    # Let registry.invoke produce the canonical not-found result.
                    spec = None

                if spec is not None and spec.side_effecting:
                    allowed = (
                        self.side_effect_authorizer is not None
                        and self.side_effect_authorizer(spec, call, snapshot)
                    )
                    if not allowed:
                        history.append(
                            CapabilityResult(
                                name=call.name,
                                ok=False,
                                error_code="CAPABILITY_NOT_AUTHORIZED",
                                error_message=(
                                    "side-effecting capability requires an explicit runtime authorizer"
                                ),
                                call_id=call.call_id,
                            )
                        )
                        total_calls += 1
                        continue

                history.append(self.registry.invoke(call))
                total_calls += 1

        raise AssertionError("unreachable runtime loop state")
