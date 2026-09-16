"""M1-018 append-only retrospective overlays and bounded invalidation.

A retrospective discovery changes what AIOS knows *today* about an earlier
period; it must not rewrite the observations recorded during that period.  This
module therefore separates three concerns:

* :class:`RetrospectiveAnnotation` is an immutable, bitemporal overlay;
* :class:`BiTemporalEpistemicLens` composes historical facts with only the
  overlays visible at a requested knowledge cutoff;
* :class:`SingleHopCascadeIsolator` marks direct consumers stale without
  recursively recomputing their dependents.

The optional SQLite journal has only append and read operations.  It never owns
or mutates the canonical ``object_revisions`` table used by ``SQLiteWorldStore``.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from aios_core.contracts.models import Dependency, Observation
from aios_core.contracts.time import (
    TemporalExtent,
    TimePrecision,
    as_utc,
    canonical_utc_iso,
    require_aware,
    utc_now,
)


class RetrospectiveAnnotation(BaseModel):
    """An interpretation learned now and overlaid on an earlier valid period."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        revalidate_instances="always",
    )

    annotation_id: str = Field(min_length=1, max_length=160)
    target_entity_id: str = Field(min_length=1, max_length=160)
    semantic_overlay: str = Field(min_length=1, max_length=16_384)
    target_time_start: datetime
    target_time_end: datetime
    learned_at: datetime = Field(default_factory=utc_now)
    source_statement_ref: str = Field(min_length=1, max_length=1024)

    @field_validator("target_time_start", "target_time_end", "learned_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime, info: Any) -> datetime:
        require_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def validate_bitemporal_order(self) -> RetrospectiveAnnotation:
        start = as_utc(self.target_time_start, "target_time_start")
        end = as_utc(self.target_time_end, "target_time_end")
        learned = as_utc(self.learned_at, "learned_at")
        if end < start:
            raise ValueError("target_time_end must not precede target_time_start")
        if learned < end:
            raise ValueError(
                "retrospective valid time must not extend beyond learned_at"
            )
        return self

    @computed_field(return_type=datetime)
    @property
    def recorded_at(self) -> datetime:
        """The append-only record is written at the exact knowledge timestamp."""

        return self.learned_at

    @computed_field(return_type=TemporalExtent)
    @property
    def valid_time_range(self) -> TemporalExtent:
        return TemporalExtent(
            start=self.target_time_start,
            end=self.target_time_end,
            precision=TimePrecision.SECOND,
        )


class AnnotationConflictError(ValueError):
    """An annotation id was reused with different immutable content."""


class AnnotationJournalCorruptionError(RuntimeError):
    """The append-only annotation journal contains an invalid row."""


class RetrospectiveAnnotationJournal:
    """Small append-only SQLite journal for retrospective overlays.

    The journal intentionally exposes no update or removal method.  A duplicate
    append is idempotent only when every immutable field is identical; reusing
    an id for different content is a conflict.
    """

    SQLITE_BUSY_TIMEOUT_MS: ClassVar[int] = 5_000

    _CREATE_SCHEMA: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS retrospective_annotations (
            annotation_id       TEXT PRIMARY KEY,
            target_entity_id    TEXT NOT NULL,
            semantic_overlay    TEXT NOT NULL,
            target_time_start   TEXT NOT NULL,
            target_time_end     TEXT NOT NULL,
            learned_at          TEXT NOT NULL,
            recorded_at         TEXT NOT NULL,
            source_statement_ref TEXT NOT NULL,
            CHECK (target_time_start <= target_time_end),
            CHECK (target_time_end <= learned_at),
            CHECK (recorded_at = learned_at)
        );

        CREATE INDEX IF NOT EXISTS idx_retrospective_visible
        ON retrospective_annotations(
            target_entity_id,
            target_time_start,
            target_time_end,
            learned_at
        );
    """

    _INSERT: ClassVar[str] = """
        INSERT INTO retrospective_annotations(
            annotation_id,
            target_entity_id,
            semantic_overlay,
            target_time_start,
            target_time_end,
            learned_at,
            recorded_at,
            source_statement_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    _SELECT_BY_ID: ClassVar[str] = """
        SELECT annotation_id, target_entity_id, semantic_overlay,
               target_time_start, target_time_end, learned_at,
               recorded_at, source_statement_ref
        FROM retrospective_annotations
        WHERE annotation_id = ?
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.SQLITE_BUSY_TIMEOUT_MS / 1000.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self.SQLITE_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(self._CREATE_SCHEMA)
            connection.commit()
        finally:
            connection.close()

    def append(self, annotation: RetrospectiveAnnotation) -> RetrospectiveAnnotation:
        """Append one immutable overlay, with exact-content idempotency."""

        normalized = RetrospectiveAnnotation.model_validate(annotation)
        values = self._values(normalized)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(self._INSERT, values)
            except sqlite3.IntegrityError as exc:
                row = connection.execute(
                    self._SELECT_BY_ID,
                    (normalized.annotation_id,),
                ).fetchone()
                if row is None:
                    raise AnnotationConflictError(
                        "annotation append violated journal integrity"
                    ) from exc
                existing = self._row_to_annotation(row)
                if existing != normalized:
                    raise AnnotationConflictError(
                        f"annotation_id already has different content: "
                        f"{normalized.annotation_id}"
                    ) from exc
                connection.rollback()
                return existing
            connection.commit()
            return normalized
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, annotation_id: str) -> RetrospectiveAnnotation:
        if not isinstance(annotation_id, str) or not annotation_id.strip():
            raise ValueError("annotation_id must not be blank")
        connection = self._connect()
        try:
            row = connection.execute(
                self._SELECT_BY_ID,
                (annotation_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(annotation_id)
        return self._row_to_annotation(row)

    def count(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM retrospective_annotations"
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise AnnotationJournalCorruptionError(
                "annotation count query returned no row"
            )
        return int(row["n"])

    def visible_annotations(
        self,
        target_entity_id: str,
        target_time: datetime,
        *,
        as_of_cutoff: datetime | None = None,
    ) -> list[RetrospectiveAnnotation]:
        """Read overlays whose valid time covers the target and whose knowledge is visible."""

        if not isinstance(target_entity_id, str) or not target_entity_id.strip():
            raise ValueError("target_entity_id must not be blank")
        require_aware(target_time, "target_time")
        require_aware(as_of_cutoff, "as_of_cutoff")
        target_iso = canonical_utc_iso(target_time, "target_time")

        clauses = [
            "target_entity_id = ?",
            "target_time_start <= ?",
            "target_time_end >= ?",
        ]
        parameters: list[str] = [target_entity_id, target_iso, target_iso]
        if as_of_cutoff is not None:
            clauses.append("learned_at <= ?")
            parameters.append(canonical_utc_iso(as_of_cutoff, "as_of_cutoff"))

        statement = (
            "SELECT annotation_id, target_entity_id, semantic_overlay, "
            "target_time_start, target_time_end, learned_at, recorded_at, "
            "source_statement_ref FROM retrospective_annotations WHERE "
            + " AND ".join(clauses)
            + " ORDER BY learned_at, annotation_id"
        )
        connection = self._connect()
        try:
            rows = connection.execute(statement, tuple(parameters)).fetchall()
        finally:
            connection.close()
        return [self._row_to_annotation(row) for row in rows]

    @staticmethod
    def _values(annotation: RetrospectiveAnnotation) -> tuple[str, ...]:
        learned_at = canonical_utc_iso(annotation.learned_at, "learned_at")
        return (
            annotation.annotation_id,
            annotation.target_entity_id,
            annotation.semantic_overlay,
            canonical_utc_iso(annotation.target_time_start, "target_time_start"),
            canonical_utc_iso(annotation.target_time_end, "target_time_end"),
            learned_at,
            learned_at,
            annotation.source_statement_ref,
        )

    @staticmethod
    def _row_to_annotation(row: sqlite3.Row) -> RetrospectiveAnnotation:
        try:
            learned_at = datetime.fromisoformat(row["learned_at"])
            recorded_at = datetime.fromisoformat(row["recorded_at"])
            if recorded_at != learned_at:
                raise ValueError("recorded_at differs from learned_at")
            return RetrospectiveAnnotation(
                annotation_id=row["annotation_id"],
                target_entity_id=row["target_entity_id"],
                semantic_overlay=row["semantic_overlay"],
                target_time_start=datetime.fromisoformat(row["target_time_start"]),
                target_time_end=datetime.fromisoformat(row["target_time_end"]),
                learned_at=learned_at,
                source_statement_ref=row["source_statement_ref"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AnnotationJournalCorruptionError(
                "retrospective annotation row is invalid"
            ) from exc


class EpistemicSlice(BaseModel):
    """Historical facts and non-destructive overlays visible through one lens."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    target_entity_id: str
    target_time: datetime
    as_of_cutoff: datetime | None = None
    historical_observations: list[Observation] = Field(default_factory=list)
    active_annotations: list[RetrospectiveAnnotation] = Field(default_factory=list)

    @field_validator("target_time", "as_of_cutoff")
    @classmethod
    def query_times_must_be_aware(
        cls, value: datetime | None, info: Any
    ) -> datetime | None:
        require_aware(value, info.field_name)
        return value

    @computed_field(return_type=int)
    @property
    def observation_count(self) -> int:
        return len(self.historical_observations)


class BiTemporalEpistemicLens:
    """Compose immutable observations with knowledge-time-aware overlays."""

    def __init__(
        self,
        observations: Iterable[Observation] = (),
        annotations: Iterable[RetrospectiveAnnotation] = (),
        *,
        journal: RetrospectiveAnnotationJournal | None = None,
    ) -> None:
        self._observations = tuple(observations)
        annotation_by_id: dict[str, RetrospectiveAnnotation] = {}
        for annotation in annotations:
            normalized = RetrospectiveAnnotation.model_validate(annotation)
            previous = annotation_by_id.setdefault(normalized.annotation_id, normalized)
            if previous != normalized:
                raise AnnotationConflictError(
                    f"annotation_id has conflicting in-memory content: "
                    f"{normalized.annotation_id}"
                )
        self._annotations = tuple(annotation_by_id.values())
        self._journal = journal

    def query_historical_slice(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: datetime | None = None,
    ) -> EpistemicSlice:
        """Return facts at event time plus overlays known by the cutoff.

        Observation visibility requires both occurrence on/before ``target_time``
        and knowledge on/before ``as_of_cutoff``.  A ``None`` cutoff means the
        current knowledge view.  Later annotations are never projected into an
        earlier as-of view.
        """

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("entity_id must not be blank")
        require_aware(target_time, "target_time")
        require_aware(as_of_cutoff, "as_of_cutoff")
        target_utc = as_utc(target_time, "target_time")
        cutoff_utc = (
            as_utc(as_of_cutoff, "as_of_cutoff") if as_of_cutoff is not None else None
        )

        observations = [
            observation
            for observation in self._observations
            if self._observation_mentions_entity(observation, entity_id)
            and self._observation_started_by(observation, target_utc)
            and (
                cutoff_utc is None
                or as_utc(observation.learned_at, "learned_at") <= cutoff_utc
            )
        ]
        observations.sort(
            key=lambda item: (
                self._observation_sort_time(item),
                item.object_id,
                item.revision,
            )
        )

        active = self._visible_in_memory_annotations(
            entity_id,
            target_utc,
            cutoff_utc,
        )
        if self._journal is not None:
            active.extend(
                self._journal.visible_annotations(
                    entity_id,
                    target_time,
                    as_of_cutoff=as_of_cutoff,
                )
            )
        active_by_id: dict[str, RetrospectiveAnnotation] = {}
        for annotation in active:
            previous = active_by_id.setdefault(annotation.annotation_id, annotation)
            if previous != annotation:
                raise AnnotationConflictError(
                    f"annotation_id differs between sources: {annotation.annotation_id}"
                )
        visible_annotations = sorted(
            active_by_id.values(),
            key=lambda item: (
                as_utc(item.learned_at, "learned_at"),
                item.annotation_id,
            ),
        )

        return EpistemicSlice(
            target_entity_id=entity_id,
            target_time=target_time,
            as_of_cutoff=as_of_cutoff,
            historical_observations=observations,
            active_annotations=visible_annotations,
        )

    def _visible_in_memory_annotations(
        self,
        entity_id: str,
        target_utc: datetime,
        cutoff_utc: datetime | None,
    ) -> list[RetrospectiveAnnotation]:
        return [
            annotation
            for annotation in self._annotations
            if annotation.target_entity_id == entity_id
            and as_utc(annotation.target_time_start, "target_time_start")
            <= target_utc
            <= as_utc(annotation.target_time_end, "target_time_end")
            and (
                cutoff_utc is None
                or as_utc(annotation.learned_at, "learned_at") <= cutoff_utc
            )
        ]

    @staticmethod
    def _observation_mentions_entity(observation: Observation, entity_id: str) -> bool:
        if observation.subject_id == entity_id:
            return True
        metadata = observation.metadata
        if metadata.get("target_entity_id") == entity_id:
            return True
        entity_ids = metadata.get("target_entity_ids", ())
        return (
            isinstance(entity_ids, (list, tuple, set, frozenset))
            and entity_id in entity_ids
        )

    @staticmethod
    def _observation_started_by(observation: Observation, target_utc: datetime) -> bool:
        start = observation.occurred.start
        return start is not None and as_utc(start, "occurred.start") <= target_utc

    @staticmethod
    def _observation_sort_time(observation: Observation) -> datetime:
        start = observation.occurred.start
        if start is None:
            return as_utc(observation.learned_at, "learned_at")
        return as_utc(start, "occurred.start")


class DependencyEdge(BaseModel):
    """Minimal reverse-invalidation edge: upstream fact -> dependent consumer."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    upstream_node_id: str = Field(min_length=1, max_length=256)
    dependent_node_id: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def reject_self_dependency(self) -> DependencyEdge:
        if self.upstream_node_id == self.dependent_node_id:
            raise ValueError("dependency edge cannot point to itself")
        return self


class StaleNodeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=256)
    is_stale: Literal[True] = True
    reason_annotation_id: str = Field(min_length=1, max_length=160)


class SingleHopIsolationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    changed_node_id: str
    stale_nodes: list[StaleNodeState] = Field(default_factory=list)
    traversal_depth: int = Field(ge=0, le=1)
    visited_edge_count: int = Field(ge=0)
    llm_recompute_requests: Literal[0] = 0

    @computed_field(return_type=int)
    @property
    def stale_count(self) -> int:
        return len(self.stale_nodes)


class SingleHopCascadeIsolator:
    """Invalidate only direct consumers; never enqueue them for recursion."""

    MAX_TRAVERSAL_DEPTH: ClassVar[Literal[1]] = 1

    def __init__(
        self,
        dependencies: Iterable[DependencyEdge | Dependency] = (),
    ) -> None:
        reverse: dict[str, set[str]] = defaultdict(set)
        for dependency in dependencies:
            edge = self._normalize_edge(dependency)
            reverse[edge.upstream_node_id].add(edge.dependent_node_id)
        self._direct_dependents = {
            upstream: tuple(sorted(dependents))
            for upstream, dependents in reverse.items()
        }

    def invalidate_direct_consumers(
        self,
        changed_node_id: str,
        *,
        reason_annotation_id: str,
    ) -> SingleHopIsolationResult:
        """Mark direct dependents stale without traversing their outgoing edges."""

        if not isinstance(changed_node_id, str) or not changed_node_id.strip():
            raise ValueError("changed_node_id must not be blank")
        if (
            not isinstance(reason_annotation_id, str)
            or not reason_annotation_id.strip()
        ):
            raise ValueError("reason_annotation_id must not be blank")

        direct = self._direct_dependents.get(changed_node_id, ())
        stale_nodes = [
            StaleNodeState(
                node_id=node_id,
                reason_annotation_id=reason_annotation_id,
            )
            for node_id in direct
        ]
        return SingleHopIsolationResult(
            changed_node_id=changed_node_id,
            stale_nodes=stale_nodes,
            traversal_depth=1 if stale_nodes else 0,
            visited_edge_count=len(stale_nodes),
            llm_recompute_requests=0,
        )

    def isolate(
        self,
        changed_node_id: str,
        *,
        reason_annotation_id: str,
    ) -> SingleHopIsolationResult:
        """Alias with the domain language used by the M1-018 dispatch."""

        return self.invalidate_direct_consumers(
            changed_node_id,
            reason_annotation_id=reason_annotation_id,
        )

    @staticmethod
    def _normalize_edge(dependency: DependencyEdge | Dependency) -> DependencyEdge:
        if isinstance(dependency, Dependency):
            return DependencyEdge(
                upstream_node_id=dependency.dependency_ref.object_id,
                dependent_node_id=dependency.dependent_ref.object_id,
            )
        return DependencyEdge.model_validate(dependency)


# Compatibility name from the original dispatch skeleton.
EpistemicWorldLens = BiTemporalEpistemicLens


__all__ = [
    "AnnotationConflictError",
    "AnnotationJournalCorruptionError",
    "BiTemporalEpistemicLens",
    "DependencyEdge",
    "EpistemicSlice",
    "EpistemicWorldLens",
    "RetrospectiveAnnotation",
    "RetrospectiveAnnotationJournal",
    "SingleHopCascadeIsolator",
    "SingleHopIsolationResult",
    "StaleNodeState",
]
