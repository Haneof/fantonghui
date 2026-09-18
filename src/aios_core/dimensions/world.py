"""AIOS 3.0 Dimension World foundation.

Dimension World turns static dimension definitions into a versioned personal
world model. It intentionally keeps dimensions append-only and separates:
- dimension schema (what a dimension means)
- dimension instance (a user's current world state)
- dimension relation (how dimensions influence each other)
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DimensionRelationType(StrEnum):
    CAUSE = "cause"
    CORRELATION = "correlation"
    DEPENDENCY = "dependency"
    CONFLICT = "conflict"
    REINFORCEMENT = "reinforcement"


class DimensionState(BaseModel):
    """A versioned snapshot of one dimension for one world owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str
    owner_id: str
    revision: int = Field(ge=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    observed_at: datetime


class DimensionRelation(BaseModel):
    """A typed edge between dimensions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str
    source_dimension_id: str
    target_dimension_id: str
    relation_type: DimensionRelationType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = ()


class DimensionWorld(BaseModel):
    """Container for a user's evolving multi-dimensional world."""

    model_config = ConfigDict(extra="forbid")

    owner_id: str
    dimensions: dict[str, DimensionState] = Field(default_factory=dict)
    relations: dict[str, DimensionRelation] = Field(default_factory=dict)

    def project(self, dimension_id: str) -> DimensionState | None:
        return self.dimensions.get(dimension_id)

    def related_to(self, dimension_id: str) -> list[DimensionRelation]:
        return [
            relation
            for relation in self.relations.values()
            if relation.source_dimension_id == dimension_id
            or relation.target_dimension_id == dimension_id
        ]
