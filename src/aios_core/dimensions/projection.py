"""World object to dimension projection boundary for AIOS 3.0.

Projection is deliberately explicit: observations do not become dimensions
without a projection rule. This keeps raw facts separate from cognition.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from .world import DimensionState


class DimensionProjection(BaseModel):
    """A deterministic mapping from world facts into a dimension state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    projection_id: str
    dimension_id: str
    metric_mapping: Mapping[str, str] = Field(default_factory=dict)

    def apply(
        self,
        owner_id: str,
        revision: int,
        facts: Mapping[str, float],
    ) -> DimensionState:
        metrics = {
            target: facts[source]
            for source, target in self.metric_mapping.items()
            if source in facts
        }
        return DimensionState(
            owner_id=owner_id,
            dimension_id=self.dimension_id,
            revision=revision,
            metrics=metrics,
            observed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
