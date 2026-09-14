from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, TypeVar

from pydantic import BaseModel, JsonValue, ValidationError

from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.models import Dependency
from aios_core.contracts.operations import CommitResult, OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now
from aios_core.dependency import validate_dependency_graph_acyclic
from aios_core.errors import AIOSProtocolError
from aios_core.storage.idempotency import request_fingerprint, stored_request_fingerprint

T = TypeVar("T", bound=WorldObject)


class StoreError(AIOSProtocolError):
    """Storage layer error, now inherits from AIOSProtocolError for unified handling.

    Keeps backward compatibility:
    - except StoreError still works
    - except AIOSProtocolError also catches StoreError
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        context: dict[str, JsonValue] | None = None,
    ):
        super().__init__(code, message, context=context)


class SQLiteWorldStore:
    """Append-only object revision store with global world revisions.

    This is a deliberately small reference implementation. It establishes the
    invariants that higher layers must not bypass:
      * object revisions are append-only;
      * every write transaction advances one global world revision;
      * optimistic concurrency uses expected_world_revision;
      * idempotency keys prevent duplicate writes;
      * references are validated before every commit;
      * historical reads can reconstruct what was visible at a world revision.
    """

    SQLITE_BUSY_TIMEOUT_MS = 5000

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.SQLITE_BUSY_TIMEOUT_MS / 1000.0,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA busy_timeout = {self.SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                ErrorCode.INVALID_ARGUMENT,
                "SQLite integrity constraint rejected the operation",
                context={"reason": "sqlite_integrity_error"},
            ) from exc
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" in message or "busy" in message:
                raise StoreError(
                    ErrorCode.VERSION_CONFLICT,
                    "world store is busy; retry from a fresh snapshot",
                    context={"reason": "storage_busy"},
                ) from exc
            raise StoreError(
                ErrorCode.INVALID_ARGUMENT,
                "SQLite operational failure",
                context={"reason": "sqlite_operational_error"},
            ) from exc
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS world_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                INSERT OR IGNORE INTO world_meta(key, value)
                VALUES ('world_revision', '0');

                CREATE TABLE IF NOT EXISTS world_commits (
                    world_revision INTEGER PRIMARY KEY,
                    committed_at TEXT NOT NULL,
                    operation_id TEXT NOT NULL UNIQUE,
                    session_id TEXT,
                    reason TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS object_revisions (
                    object_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    object_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    world_revision INTEGER NOT NULL,
                    learned_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(object_id, revision),
                    FOREIGN KEY(world_revision) REFERENCES world_commits(world_revision)
                );

                CREATE INDEX IF NOT EXISTS idx_objects_current_lookup
                    ON object_revisions(object_id, world_revision DESC);
                CREATE INDEX IF NOT EXISTS idx_objects_type_subject
                    ON object_revisions(object_type, subject_id, world_revision DESC);
                CREATE INDEX IF NOT EXISTS idx_objects_learned
                    ON object_revisions(learned_at);

                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    operation_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    expected_world_revision INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    result_world_revision INTEGER,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    world_revision INTEGER NOT NULL,
                    result_json TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def current_world_revision(self) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM world_meta WHERE key='world_revision'"
            ).fetchone()
            return int(row["value"])

    def _get_idempotent_result(
        self,
        conn: sqlite3.Connection,
        operation: OperationRequest,
        objects: list[WorldObject],
    ) -> CommitResult | None:
        row = conn.execute(
            """
            SELECT operation_id, world_revision, result_json
            FROM idempotency_records
            WHERE idempotency_key=?
            """,
            (operation.idempotency_key,),
        ).fetchone()
        if not row:
            return None

        incoming_fingerprint = request_fingerprint(operation, objects)
        original_fingerprint = stored_request_fingerprint(
            conn,
            operation_id=str(row["operation_id"]),
            world_revision=int(row["world_revision"]),
        )
        if incoming_fingerprint != original_fingerprint:
            raise StoreError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "idempotency key was already used for a different request",
                context={
                    "idempotency_key": operation.idempotency_key,
                    "original_operation_id": str(row["operation_id"]),
                    "operation_id": operation.operation_id,
                    "reason": "request_fingerprint_mismatch",
                },
            )

        data = json.loads(row["result_json"])
        data["idempotent_replay"] = True
        return CommitResult.model_validate(data)

    def _latest_revision(self, conn: sqlite3.Connection, object_id: str) -> int | None:
        row = conn.execute(
            "SELECT MAX(revision) AS rev FROM object_revisions WHERE object_id=?",
            (object_id,),
        ).fetchone()
        return None if row["rev"] is None else int(row["rev"])

    def _latest_object_type(self, conn: sqlite3.Connection, object_id: str) -> str | None:
        row = conn.execute(
            """
            SELECT object_type
            FROM object_revisions
            WHERE object_id=?
            ORDER BY revision DESC
            LIMIT 1
            """,
            (object_id,),
        ).fetchone()
        return None if row is None else str(row["object_type"])

    def _reference_exists(
        self,
        conn: sqlite3.Connection,
        ref: ObjectRef | SourceRef,
        pending_pairs: set[tuple[str, int]],
        pending_objects: dict[tuple[str, int], WorldObject],
        *,
        knowledge_cutoff: datetime,
    ) -> bool:
        """
        Generic knowledge visibility: target learned_at <= referencing_object.learned_at
        - For pinned ref (revision=N): check exact revision visible within cutoff
        - For floating ref (revision=None): check at least one visible revision within cutoff
        - Pending objects are considered with UTC instant comparison
        """
        cutoff_canonical = canonical_utc_iso(knowledge_cutoff, "knowledge_cutoff")

        if ref.revision is not None:
            key = (ref.object_id, ref.revision)
            if key in pending_pairs:
                pending_target = pending_objects.get(key)
                if pending_target is None:
                    return False
                try:
                    if as_utc(pending_target.learned_at, "pending_learned_at") <= as_utc(
                        knowledge_cutoff, "knowledge_cutoff"
                    ):
                        return True
                    return False
                except Exception:
                    return False
            row = conn.execute(
                "SELECT 1 FROM object_revisions WHERE object_id=? AND revision=? AND learned_at<=? LIMIT 1",
                (ref.object_id, ref.revision, cutoff_canonical),
            ).fetchone()
            return row is not None

        for (oid, _rev), pending_obj in pending_objects.items():
            if oid == ref.object_id:
                try:
                    if as_utc(pending_obj.learned_at, "pending_learned_at") <= as_utc(
                        knowledge_cutoff, "knowledge_cutoff"
                    ):
                        return True
                except Exception:
                    continue
        row = conn.execute(
            "SELECT 1 FROM object_revisions WHERE object_id=? AND learned_at<=? LIMIT 1",
            (ref.object_id, cutoff_canonical),
        ).fetchone()
        return row is not None

    @staticmethod
    def _collect_refs(value: object) -> list[ObjectRef | SourceRef]:
        refs: list[ObjectRef | SourceRef] = []

        def walk(node: object) -> None:
            if isinstance(node, (ObjectRef, SourceRef)):
                refs.append(node)
                return
            if isinstance(node, BaseModel):
                for field_name in type(node).model_fields:
                    walk(getattr(node, field_name))
                return
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
                return
            if isinstance(node, (list, tuple, set)):
                for v in node:
                    walk(v)

        walk(value)
        return refs

    def _validate_dependency_graph(
        self,
        conn: sqlite3.Connection,
        objects: list[WorldObject],
    ) -> None:
        pending = [obj for obj in objects if isinstance(obj, Dependency)]
        if not pending:
            return

        rows = conn.execute(
            """
            SELECT o.payload_json
            FROM object_revisions o
            JOIN (
                SELECT object_id, MAX(revision) AS max_revision
                FROM object_revisions
                WHERE object_type=?
                GROUP BY object_id
            ) latest
            ON latest.object_id=o.object_id AND latest.max_revision=o.revision
            WHERE o.object_type=?
            """,
            (ObjectType.DEPENDENCY.value, ObjectType.DEPENDENCY.value),
        ).fetchall()

        current_by_id: dict[str, Dependency] = {}
        for row in rows:
            dependency = Dependency.model_validate(json.loads(row["payload_json"]))
            current_by_id[dependency.object_id] = dependency
        for dependency in pending:
            current_by_id[dependency.object_id] = dependency

        try:
            validate_dependency_graph_acyclic(current_by_id.values())
        except ValueError as exc:
            raise StoreError(
                ErrorCode.DEPENDENCY_INVALID,
                str(exc),
                context={
                    "reason": "dependency_cycle",
                    "pending_dependency_ids": [dep.object_id for dep in pending],
                },
            ) from exc

    def commit(
        self,
        objects: Iterable[WorldObject],
        operation: OperationRequest,
    ) -> CommitResult:
        object_list = list(objects)
        if not object_list:
            raise StoreError(
                ErrorCode.INVALID_ARGUMENT,
                "commit requires at least one object",
                context={
                    "operation_id": operation.operation_id,
                    "reason": "empty_commit",
                },
            )

        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                replay = self._get_idempotent_result(conn, operation, object_list)
                if replay is not None:
                    conn.rollback()
                    return replay

                reused_operation = conn.execute(
                    "SELECT idempotency_key FROM operations WHERE operation_id=?",
                    (operation.operation_id,),
                ).fetchone()
                if reused_operation is not None:
                    raise StoreError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "operation_id was already committed with a different idempotency key",
                        context={
                            "operation_id": operation.operation_id,
                            "idempotency_key": operation.idempotency_key,
                            "original_idempotency_key": str(reused_operation["idempotency_key"]),
                            "reason": "operation_id_reused",
                        },
                    )

                current_world_revision = int(
                    conn.execute(
                        "SELECT value FROM world_meta WHERE key='world_revision'"
                    ).fetchone()["value"]
                )
                if operation.expected_world_revision != current_world_revision:
                    raise StoreError(
                        ErrorCode.VERSION_CONFLICT,
                        f"expected world revision {operation.expected_world_revision}, current is {current_world_revision}",
                        context={
                            "expected_world_revision": operation.expected_world_revision,
                            "current_world_revision": current_world_revision,
                            "operation_id": operation.operation_id,
                        },
                    )

                validated_objects: list[WorldObject] = []
                for obj in object_list:
                    try:
                        snapshot = obj.model_dump(
                            mode="python",
                            round_trip=True,
                        )
                        validated = type(obj).model_validate(snapshot)
                    except ValidationError as exc:
                        raise StoreError(
                            ErrorCode.INVALID_ARGUMENT,
                            "world object failed persistence validation",
                            context={
                                "object_id": obj.object_id,
                                "object_type": obj.object_type.value,
                                "revision": obj.revision,
                                "reason": "persistence_revalidation_failed",
                            },
                        ) from exc
                    validated_objects.append(validated)
                object_list = validated_objects

                pending_pairs = {(o.object_id, o.revision) for o in object_list}
                pending_objects = {(o.object_id, o.revision): o for o in object_list}
                if len(pending_pairs) != len(object_list):
                    raise StoreError(
                        ErrorCode.INVALID_ARGUMENT,
                        "duplicate object revision in one commit",
                        context={
                            "operation_id": operation.operation_id,
                            "reason": "duplicate_revision",
                        },
                    )

                for obj in object_list:
                    latest = self._latest_revision(conn, obj.object_id)
                    expected_revision = 1 if latest is None else latest + 1
                    if obj.revision != expected_revision:
                        raise StoreError(
                            ErrorCode.VERSION_CONFLICT,
                            f"{obj.object_id} must write revision {expected_revision}, got {obj.revision}",
                            context={
                                "object_id": obj.object_id,
                                "expected_revision": expected_revision,
                                "actual_revision": obj.revision,
                            },
                        )
                    if latest is not None:
                        existing_object_type = self._latest_object_type(conn, obj.object_id)
                        if existing_object_type is not None and existing_object_type != obj.object_type.value:
                            raise StoreError(
                                ErrorCode.VERSION_CONFLICT,
                                "object type cannot change across revisions",
                                context={
                                    "object_id": obj.object_id,
                                    "expected_object_type": existing_object_type,
                                    "actual_object_type": obj.object_type.value,
                                },
                            )

                for obj in object_list:
                    for ref in self._collect_refs(obj):
                        if ref.object_id == obj.object_id and (
                            ref.revision is None or ref.revision == obj.revision
                        ):
                            raise StoreError(
                                ErrorCode.DEPENDENCY_INVALID,
                                f"object {obj.object_id} cannot cite its own current/floating revision as evidence/source",
                                context={
                                    "object_id": obj.object_id,
                                    "revision": obj.revision,
                                    "referenced_revision": ref.revision,
                                    "reason": "self_reference",
                                },
                            )
                        if not self._reference_exists(
                            conn,
                            ref,
                            pending_pairs,
                            pending_objects,
                            knowledge_cutoff=obj.learned_at,
                        ):
                            raise StoreError(
                                ErrorCode.NOT_FOUND,
                                f"reference does not exist: {ref.object_id}@{ref.revision or 'latest'}",
                                context={
                                    "referenced_object_id": ref.object_id,
                                    "referenced_revision": ref.revision,
                                    "reason": "reference_not_visible_or_missing",
                                },
                            )

                self._validate_dependency_graph(conn, object_list)

                next_world_revision = current_world_revision + 1
                now_dt = utc_now()
                now = canonical_utc_iso(now_dt, "now")
                conn.execute(
                    "INSERT INTO world_commits(world_revision, committed_at, operation_id, session_id, reason) VALUES(?,?,?,?,?)",
                    (
                        next_world_revision,
                        now,
                        operation.operation_id,
                        operation.session_id,
                        operation.reason,
                    ),
                )

                refs: list[tuple[str, int]] = []
                for obj in object_list:
                    payload = obj.model_dump_json()
                    conn.execute(
                        """
                        INSERT INTO object_revisions(
                            object_id, revision, object_type, subject_id, world_revision,
                            learned_at, recorded_at, payload_json
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (
                            obj.object_id,
                            obj.revision,
                            obj.object_type.value,
                            obj.subject_id,
                            next_world_revision,
                            canonical_utc_iso(obj.learned_at, "learned_at"),
                            canonical_utc_iso(obj.recorded_at, "recorded_at"),
                            payload,
                        ),
                    )
                    refs.append((obj.object_id, obj.revision))

                result = CommitResult(
                    operation_id=operation.operation_id,
                    world_revision=next_world_revision,
                    object_refs=refs,
                )
                result_json = result.model_dump_json()

                conn.execute(
                    """
                    INSERT INTO operations(
                        operation_id, session_id, operation_name, arguments_json,
                        expected_world_revision, reason, idempotency_key, status,
                        result_world_revision, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        operation.operation_id,
                        operation.session_id,
                        operation.operation_name,
                        json.dumps(operation.arguments, ensure_ascii=False, default=str),
                        operation.expected_world_revision,
                        operation.reason,
                        operation.idempotency_key,
                        "committed",
                        next_world_revision,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO idempotency_records(idempotency_key, operation_id, world_revision, result_json) VALUES(?,?,?,?)",
                    (
                        operation.idempotency_key,
                        operation.operation_id,
                        next_world_revision,
                        result_json,
                    ),
                )
                conn.execute(
                    "UPDATE world_meta SET value=? WHERE key='world_revision'",
                    (str(next_world_revision),),
                )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def get_payload(
        self,
        object_id: str,
        *,
        revision: int | None = None,
        as_of_world_revision: int | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> dict:
        clauses = ["object_id=?"]
        params: list[object] = [object_id]
        if revision is not None:
            clauses.append("revision=?")
            params.append(revision)
        if as_of_world_revision is not None:
            clauses.append("world_revision<=?")
            params.append(as_of_world_revision)
        if knowledge_cutoff is not None:
            clauses.append("learned_at<=?")
            params.append(canonical_utc_iso(knowledge_cutoff, "knowledge_cutoff"))
        sql = (
            "SELECT payload_json FROM object_revisions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY revision DESC LIMIT 1"
        )
        with self._connection() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            if row is None:
                raise StoreError(
                    ErrorCode.NOT_FOUND,
                    f"object not found: {object_id}",
                    context={
                        "object_id": object_id,
                        "revision": revision,
                    },
                )
            return json.loads(row["payload_json"])

    def list_payloads(
        self,
        *,
        object_type: ObjectType | None = None,
        subject_id: str | None = None,
        as_of_world_revision: int | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> list[dict]:
        """Return the newest visible revision of each object under the supplied cutoff."""
        if as_of_world_revision is not None or knowledge_cutoff is not None:
            return self._list_payloads_historical(
                object_type=object_type,
                subject_id=subject_id,
                as_of_world_revision=as_of_world_revision,
                knowledge_cutoff=knowledge_cutoff,
            )

        clauses = ["1=1"]
        params: list[object] = []
        if object_type is not None:
            clauses.append("o.object_type=?")
            params.append(object_type.value)
        if subject_id is not None:
            clauses.append("o.subject_id=?")
            params.append(subject_id)
        where = " AND ".join(clauses)
        sql = f"""
            SELECT o.payload_json
            FROM object_revisions o
            JOIN (
                SELECT object_id, MAX(revision) AS max_revision
                FROM object_revisions
                GROUP BY object_id
            ) latest
            ON latest.object_id=o.object_id AND latest.max_revision=o.revision
            WHERE {where}
            ORDER BY o.recorded_at ASC
        """
        with self._connection() as conn:
            return [json.loads(row["payload_json"]) for row in conn.execute(sql, tuple(params)).fetchall()]

    def _list_payloads_historical(
        self,
        *,
        object_type: ObjectType | None,
        subject_id: str | None,
        as_of_world_revision: int | None,
        knowledge_cutoff: datetime | None,
    ) -> list[dict]:
        # First reconstruct the latest visible revision of each object. Only then
        # apply mutable-object filters such as subject_id; otherwise an older
        # matching revision could incorrectly reappear after the latest visible
        # revision changed subject.
        clauses = ["1=1"]
        params: list[object] = []
        if as_of_world_revision is not None:
            clauses.append("world_revision<=?")
            params.append(as_of_world_revision)
        if knowledge_cutoff is not None:
            clauses.append("learned_at<=?")
            params.append(canonical_utc_iso(knowledge_cutoff, "knowledge_cutoff"))
        sql = (
            "SELECT object_id, revision, object_type, subject_id, recorded_at, payload_json "
            "FROM object_revisions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY object_id, revision DESC"
        )
        with self._connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        seen: set[str] = set()
        selected: list[tuple[str, dict]] = []
        for row in rows:
            object_id = str(row["object_id"])
            if object_id in seen:
                continue
            seen.add(object_id)
            if object_type is not None and row["object_type"] != object_type.value:
                continue
            if subject_id is not None and row["subject_id"] != subject_id:
                continue
            selected.append((row["recorded_at"], json.loads(row["payload_json"])))

        selected.sort(key=lambda item: item[0])
        return [payload for _, payload in selected]

    def operation_record(self, operation_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise StoreError(
                    ErrorCode.NOT_FOUND,
                    f"operation not found: {operation_id}",
                    context={
                        "operation_id": operation_id,
                    },
                )
            return dict(row)
