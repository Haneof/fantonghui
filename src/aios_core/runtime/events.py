"""Runtime event boundary between world input and cognitive execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeEvent:
    """Normalized wake event consumed by the AIOS runtime loop."""

    event_type: str
    payload: Mapping[str, Any]
    source: str = "unknown"
    created_at: datetime = datetime.now(timezone.utc)

    def as_cycle_input(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "payload": dict(self.payload),
        }
