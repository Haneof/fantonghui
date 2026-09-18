"""AIOS runtime lifecycle orchestration.

Provides the minimal kernel boundary around the existing CognitiveRuntime.
The lifecycle layer owns startup, wake, cycle dispatch, and shutdown state;
it does not replace cognition, world storage, or capability execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RuntimeState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True)
class RuntimeCycle:
    cycle_id: str
    wake_reason: str
    input_payload: Mapping[str, Any]


@dataclass
class RuntimeLifecycle:
    """Kernel lifecycle state machine for AIOS execution.

    This intentionally stays independent from the model and storage layers.
    Concrete runtime adapters can attach CognitiveRuntime and World services.
    """

    state: RuntimeState = RuntimeState.CREATED
    history: list[RuntimeCycle] = field(default_factory=list)

    def start(self) -> None:
        if self.state not in (RuntimeState.CREATED, RuntimeState.STOPPED):
            raise RuntimeError("runtime already started")
        self.state = RuntimeState.RUNNING

    def wake(self, cycle: RuntimeCycle) -> None:
        if self.state != RuntimeState.RUNNING:
            raise RuntimeError("runtime is not running")
        self.history.append(cycle)

    def stop(self) -> None:
        if self.state == RuntimeState.RUNNING:
            self.state = RuntimeState.STOPPING
        self.state = RuntimeState.STOPPED

    @property
    def is_alive(self) -> bool:
        return self.state == RuntimeState.RUNNING
