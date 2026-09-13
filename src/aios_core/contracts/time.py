from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def require_aware(
    value: datetime | None,
    field_name: str,
) -> None:
    if value is not None and (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be timezone-aware"
        )


def require_timezone_name(
    value: str | None,
    field_name: str = "timezone_name",
) -> None:
    if value is None:
        return

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a valid IANA timezone name"
        )

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a valid IANA timezone name: {value}"
        ) from exc


def as_utc(
    value: datetime,
    field_name: str = "timestamp",
) -> datetime:
    require_aware(value, field_name)
    return value.astimezone(timezone.utc)


def canonical_utc_iso(
    value: datetime,
    field_name: str = "timestamp",
) -> str:
    """Return a fixed-shape UTC timestamp suitable for indexed TEXT ordering."""
    return as_utc(
        value,
        field_name,
    ).isoformat(timespec="microseconds")


class TemporalExtent(BaseModel):
    """Point, interval, open interval, or explicitly unknown event time."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    start: datetime | None = None
    end: datetime | None = None
    precision: TimePrecision = TimePrecision.UNKNOWN
    timezone_name: str | None = None
    unknown: bool = False

    @model_validator(mode="after")
    def validate_extent(self) -> "TemporalExtent":
        require_aware(self.start, "start")
        require_aware(self.end, "end")
        require_timezone_name(
            self.timezone_name,
            "timezone_name",
        )

        if self.unknown:
            if self.start is not None or self.end is not None:
                raise ValueError(
                    "unknown extent cannot also contain start/end"
                )

            if self.precision is not TimePrecision.UNKNOWN:
                raise ValueError(
                    "unknown extent must use unknown precision"
                )

            return self

        if self.start is None and self.end is None:
            raise ValueError(
                "time requires start/end or unknown=true"
            )

        if (
            self.start is not None
            and self.end is not None
            and self.end < self.start
        ):
            raise ValueError(
                "end must not be before start"
            )

        return self

    @classmethod
    def unknown_time(cls) -> "TemporalExtent":
        return cls(
            unknown=True,
            precision=TimePrecision.UNKNOWN,
        )

    @classmethod
    def point(
        cls,
        value: datetime,
        precision: TimePrecision = TimePrecision.SECOND,
        *,
        timezone_name: str | None = None,
    ) -> "TemporalExtent":
        return cls(
            start=value,
            end=value,
            precision=precision,
            timezone_name=timezone_name,
        )


class KnowledgeWindow(BaseModel):
    """What the system was allowed to know for one query/evidence snapshot."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    knowledge_cutoff: datetime
    world_revision: int | None = Field(
        default=None,
        ge=0,
    )

    @model_validator(mode="after")
    def validate_window(self) -> "KnowledgeWindow":
        require_aware(
            self.knowledge_cutoff,
            "knowledge_cutoff",
        )
        return self
