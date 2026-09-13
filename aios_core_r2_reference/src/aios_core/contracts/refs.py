from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ObjectRef(BaseModel):
    """A version-aware reference to another long-term object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str = Field(min_length=1)
    revision: int | None = Field(default=None, ge=1)


class SourceRef(BaseModel):
    """Reference to a raw or derived source, with optional immutable version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str = Field(min_length=1)
    revision: int | None = Field(default=None, ge=1)
    source_locator: str | None = None
