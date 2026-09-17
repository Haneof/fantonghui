"""Auditable capability registry for the AIOS Executive Plane.

The registry is intentionally dumb about cognition. It tells the model what it can
ask the system to do, validates call shape, executes the registered handler, and
returns structured evidence/errors. It does not decide which capability is relevant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping


class CapabilityKind(StrEnum):
    READ = "read"
    WRITE = "write"
    ACTION = "action"
    RESPONSE = "response"


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    description: str
    kind: CapabilityKind = CapabilityKind.READ
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    hard_boundary: bool = False
    side_effecting: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("capability name must be non-blank")
        if not self.description or not self.description.strip():
            raise ValueError("capability description must be non-blank")
        if self.kind in {CapabilityKind.WRITE, CapabilityKind.ACTION} and not self.side_effecting:
            object.__setattr__(self, "side_effecting", True)


@dataclass(frozen=True)
class CapabilityCall:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    call_id: str | None = None

    def normalized_signature(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        # A conservative loop signature. repr() is only used for duplicate-call
        # detection inside one transient turn; it is not a durable identity format.
        return (
            self.name,
            tuple(sorted((str(k), repr(v)) for k, v in self.arguments.items())),
        )


@dataclass(frozen=True)
class CapabilityResult:
    name: str
    ok: bool
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None
    call_id: str | None = None


@dataclass(frozen=True)
class _RegisteredCapability:
    spec: CapabilitySpec
    handler: Callable[..., Any]


class CapabilityRegistry:
    """Registry + execution boundary for model-callable capabilities."""

    def __init__(self) -> None:
        self._items: dict[str, _RegisteredCapability] = {}

    def register(self, spec: CapabilitySpec, handler: Callable[..., Any]) -> None:
        if spec.name in self._items:
            raise ValueError(f"capability already registered: {spec.name}")
        if not callable(handler):
            raise TypeError("capability handler must be callable")
        self._items[spec.name] = _RegisteredCapability(spec=spec, handler=handler)

    def unregister(self, name: str) -> None:
        self._items.pop(name, None)

    def get_spec(self, name: str) -> CapabilitySpec:
        try:
            return self._items[name].spec
        except KeyError:
            raise KeyError(f"unknown capability: {name}") from None

    def catalog(self) -> list[dict[str, Any]]:
        """Return model-facing capability metadata without leaking Python handlers."""
        return [
            {
                "name": item.spec.name,
                "description": item.spec.description,
                "kind": item.spec.kind.value,
                "input_schema": dict(item.spec.input_schema),
                "hard_boundary": item.spec.hard_boundary,
                "side_effecting": item.spec.side_effecting,
            }
            for _, item in sorted(self._items.items())
        ]

    def invoke(self, call: CapabilityCall) -> CapabilityResult:
        item = self._items.get(call.name)
        if item is None:
            return CapabilityResult(
                name=call.name,
                ok=False,
                error_code="CAPABILITY_NOT_FOUND",
                error_message=f"unknown capability: {call.name}",
                call_id=call.call_id,
            )

        try:
            value = item.handler(**dict(call.arguments))
        except TypeError as exc:
            return CapabilityResult(
                name=call.name,
                ok=False,
                error_code="CAPABILITY_ARGUMENT_ERROR",
                error_message=str(exc),
                call_id=call.call_id,
            )
        except Exception as exc:  # handler errors become structured tool evidence
            return CapabilityResult(
                name=call.name,
                ok=False,
                error_code="CAPABILITY_EXECUTION_ERROR",
                error_message=f"{type(exc).__name__}: {exc}",
                call_id=call.call_id,
            )

        return CapabilityResult(
            name=call.name,
            ok=True,
            data=value,
            call_id=call.call_id,
        )
