from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimePrecision(StrEnum):
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    HALF_YEAR = "half_year"
    YEAR = "year"
    MULTI_YEAR = "multi_year"
    UNKNOWN = "unknown"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_aware(value: datetime | None, field_name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must be timezone-aware")


class TemporalExtent(BaseModel):
    """A time point, bounded interval, one-sided interval, or explicitly unknown time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime | None = None
    end: datetime | None = None
    precision: TimePrecision = TimePrecision.UNKNOWN
    timezone_name: str | None = None
    unknown: bool = False

    @model_validator(mode="after")
    def validate_extent(self) -> "TemporalExtent":
        require_aware(self.start, "start")
        require_aware(self.end, "end")
        if self.unknown:
            if self.start is not None or self.end is not None:
                raise ValueError("unknown extent cannot also contain start/end")
            return self
        if self.start is None and self.end is None:
            raise ValueError("time requires start/end or unknown=true")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("end must not be before start")
        return self

    @classmethod
    def unknown_time(cls) -> "TemporalExtent":
        return cls(unknown=True, precision=TimePrecision.UNKNOWN)

    @classmethod
    def point(cls, value: datetime, precision: TimePrecision = TimePrecision.SECOND) -> "TemporalExtent":
        return cls(start=value, end=value, precision=precision)


class KnowledgeWindow(BaseModel):
    """Defines what the system was allowed to know for a query/evidence snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_cutoff: datetime
    world_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_window(self) -> "KnowledgeWindow":
        require_aware(self.knowledge_cutoff, "knowledge_cutoff")
        return self
