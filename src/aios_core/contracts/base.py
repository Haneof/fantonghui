from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ObjectType
from .refs import SourceRef
from .time import TemporalExtent, as_utc, require_aware, utc_now


class WorldObject(BaseModel):
    """Base contract shared by all durable objects in the AIOS world."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    object_id: str = Field(min_length=1)
    object_type: ObjectType
    subject_id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    occurred: TemporalExtent = Field(default_factory=TemporalExtent.unknown_time)
    learned_at: datetime
    recorded_at: datetime = Field(default_factory=utc_now)
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_by: str = Field(min_length=1)
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_times(self) -> "WorldObject":
        require_aware(self.learned_at, "learned_at")
        require_aware(self.recorded_at, "recorded_at")
        if as_utc(
            self.recorded_at,
            "recorded_at",
        ) < as_utc(
            self.learned_at,
            "learned_at",
        ):
            # Allow ingestion delay only in the forward direction. If data is imported
            # from old systems, learned_at should still represent when AIOS learned it.
            raise ValueError("recorded_at must be >= learned_at")
        return self
