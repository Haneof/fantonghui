from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.time import require_aware
from aios_core.storage.sqlite_store import SQLiteWorldStore


class QueryCoverage(BaseModel):
    """Minimal truthful coverage for an M0 historical read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    returned_objects: int = Field(ge=0)


class HistoricalQueryResult(BaseModel):
    """Historical payloads plus the exact snapshot boundary used to read them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world_revision: int = Field(ge=0)
    knowledge_cutoff: datetime | None = None
    coverage: QueryCoverage
    payloads: list[dict[str, Any]]

    @model_validator(mode="after")
    def validate_cutoff(self) -> "HistoricalQueryResult":
        require_aware(self.knowledge_cutoff, "knowledge_cutoff")
        return self


class HistoricalWorldQuery:
    """Read-only historical world facade over SQLiteWorldStore.

    The facade snapshots the current global world revision first and then pins
    every storage read to that revision (or to an older requested revision), so
    a concurrent writer cannot silently widen one logical query mid-read.
    """

    def __init__(self, store: SQLiteWorldStore):
        self._store = store

    def _resolve_world_revision(self, requested: int | None) -> int:
        current = self._store.current_world_revision()
        if requested is None:
            return current
        if requested < 0:
            raise ValueError("as_of_world_revision must be >= 0")
        return min(requested, current)

    def get(
        self,
        object_id: str,
        *,
        revision: int | None = None,
        as_of_world_revision: int | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> HistoricalQueryResult:
        snapshot_revision = self._resolve_world_revision(as_of_world_revision)
        payload = self._store.get_payload(
            object_id,
            revision=revision,
            as_of_world_revision=snapshot_revision,
            knowledge_cutoff=knowledge_cutoff,
        )
        return HistoricalQueryResult(
            world_revision=snapshot_revision,
            knowledge_cutoff=knowledge_cutoff,
            coverage=QueryCoverage(returned_objects=1),
            payloads=[payload],
        )

    def list(
        self,
        *,
        object_type: ObjectType | None = None,
        subject_id: str | None = None,
        as_of_world_revision: int | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> HistoricalQueryResult:
        snapshot_revision = self._resolve_world_revision(as_of_world_revision)
        payloads = self._store.list_payloads(
            object_type=object_type,
            subject_id=subject_id,
            as_of_world_revision=snapshot_revision,
            knowledge_cutoff=knowledge_cutoff,
        )
        return HistoricalQueryResult(
            world_revision=snapshot_revision,
            knowledge_cutoff=knowledge_cutoff,
            coverage=QueryCoverage(returned_objects=len(payloads)),
            payloads=payloads,
        )
