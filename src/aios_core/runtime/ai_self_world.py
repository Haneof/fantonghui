"""Evidence-linked AI Self World for R5/R6.

This is deliberately not a game-style personality score board. AI self memory is a
set of versioned understandings, commitments and reflections. New evidence creates a
new forward version; it never rewrites the historical record that explains what the
AI believed or learned at an earlier time.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now
from aios_core.storage.idempotency import canonical_json_dumps

AI_SELF_SUBJECT_ID = "ai_agent_self"


class AISelfMemoryKind(StrEnum):
    IDENTITY = "identity"
    PRINCIPLE = "principle"
    BOUNDARY = "boundary"
    BELIEF = "belief"
    RELATIONSHIP_UNDERSTANDING = "relationship_understanding"
    REFLECTION = "reflection"
    COMMITMENT = "commitment"
    COMMUNICATION_EXPERIENCE = "communication_experience"
    OPERATION_EXPERIENCE = "operation_experience"
    POLICY_LEARNING = "policy_learning"


_EVIDENCE_REQUIRED = {
    AISelfMemoryKind.BELIEF,
    AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING,
    AISelfMemoryKind.REFLECTION,
    AISelfMemoryKind.COMMUNICATION_EXPERIENCE,
    AISelfMemoryKind.OPERATION_EXPERIENCE,
    AISelfMemoryKind.POLICY_LEARNING,
}


class AISelfMemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    memory_key: str = Field(min_length=1)
    version: int = Field(ge=1)
    kind: AISelfMemoryKind
    statement: str = Field(min_length=1)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    learned_at: datetime = Field(default_factory=utc_now)
    recorded_at: datetime = Field(default_factory=utc_now)
    previous_record_id: str | None = None
    retracted: bool = False
    retraction_reason: str | None = None
    subject_id: str = AI_SELF_SUBJECT_ID

    @model_validator(mode="after")
    def validate_record(self) -> "AISelfMemoryRecord":
        if self.subject_id != AI_SELF_SUBJECT_ID:
            raise ValueError("AI Self World records must use the AI self subject")
        if not self.memory_key.strip() or not self.statement.strip():
            raise ValueError("memory_key/statement must not be blank")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence_refs must contain only non-blank refs")
        learned = as_utc(self.learned_at, "learned_at")
        recorded = as_utc(self.recorded_at, "recorded_at")
        if recorded < learned:
            raise ValueError("recorded_at must be >= learned_at")
        if self.version == 1 and self.previous_record_id is not None:
            raise ValueError("version 1 cannot point at previous_record_id")
        if self.version > 1 and not (self.previous_record_id or "").strip():
            raise ValueError("later AI self versions must point at previous_record_id")
        if self.kind in _EVIDENCE_REQUIRED and not self.evidence_refs:
            raise ValueError(f"{self.kind.value} requires evidence_refs")
        if self.retracted and not (self.retraction_reason or "").strip():
            raise ValueError("retracted memory requires retraction_reason")
        return self

    @classmethod
    def create(
        cls,
        *,
        memory_key: str,
        version: int,
        kind: AISelfMemoryKind,
        statement: str,
        structured_data: dict[str, Any] | None = None,
        evidence_refs: tuple[str, ...] = (),
        learned_at: datetime | None = None,
        recorded_at: datetime | None = None,
        previous_record_id: str | None = None,
        retracted: bool = False,
        retraction_reason: str | None = None,
    ) -> "AISelfMemoryRecord":
        learned = learned_at or utc_now()
        recorded = recorded_at or utc_now()
        identity = canonical_json_dumps(
            {
                "memory_key": memory_key,
                "version": version,
                "kind": kind.value,
                "statement": statement,
                "evidence_refs": evidence_refs,
                "learned_at": learned,
                "previous_record_id": previous_record_id,
            }
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return cls(
            record_id=f"aiself_{digest}",
            memory_key=memory_key,
            version=version,
            kind=kind,
            statement=statement,
            structured_data=structured_data or {},
            evidence_refs=evidence_refs,
            learned_at=learned,
            recorded_at=recorded,
            previous_record_id=previous_record_id,
            retracted=retracted,
            retraction_reason=retraction_reason,
        )


class AISelfWorldConflict(ValueError):
    pass


class AISelfWorldStoreV2:
    """Append-only durable AI Self World."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_ai_self_memory(
                    memory_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    record_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    learned_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(memory_key, version)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_ai_self_latest
                ON runtime_ai_self_memory(memory_key, version DESC)
                """
            )
            conn.commit()

    @staticmethod
    def _decode(raw: str) -> AISelfMemoryRecord:
        return AISelfMemoryRecord.model_validate(json.loads(raw))

    def latest(self, memory_key: str) -> AISelfMemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM runtime_ai_self_memory
                WHERE memory_key=? ORDER BY version DESC LIMIT 1
                """,
                (memory_key,),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def get(self, memory_key: str, version: int) -> AISelfMemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM runtime_ai_self_memory WHERE memory_key=? AND version=?",
                (memory_key, version),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def history(self, memory_key: str) -> list[AISelfMemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM runtime_ai_self_memory
                WHERE memory_key=? ORDER BY version ASC
                """,
                (memory_key,),
            ).fetchall()
        return [self._decode(str(row["payload_json"])) for row in rows]

    def append(self, record: AISelfMemoryRecord) -> AISelfMemoryRecord:
        record = AISelfMemoryRecord.model_validate(record.model_dump(mode="python"))
        payload = canonical_json_dumps(record.model_dump(mode="python"))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT version, record_id, kind
                FROM runtime_ai_self_memory
                WHERE memory_key=? ORDER BY version DESC LIMIT 1
                """,
                (record.memory_key,),
            ).fetchone()
            if row is None:
                if record.version != 1:
                    conn.rollback()
                    raise AISelfWorldConflict("initial AI self memory version must be 1")
            else:
                current_version = int(row["version"])
                current_record_id = str(row["record_id"])
                current_kind = str(row["kind"])
                if record.version != current_version + 1:
                    conn.rollback()
                    raise AISelfWorldConflict(
                        f"{record.memory_key!r} must append version {current_version + 1}"
                    )
                if record.previous_record_id != current_record_id:
                    conn.rollback()
                    raise AISelfWorldConflict("previous_record_id must pin the latest durable record")
                if record.kind.value != current_kind:
                    conn.rollback()
                    raise AISelfWorldConflict("memory kind cannot change inside one memory_key stream")

            conn.execute(
                """
                INSERT INTO runtime_ai_self_memory(
                    memory_key, version, record_id, kind, learned_at, recorded_at, payload_json
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    record.memory_key,
                    record.version,
                    record.record_id,
                    record.kind.value,
                    canonical_utc_iso(record.learned_at, "learned_at"),
                    canonical_utc_iso(record.recorded_at, "recorded_at"),
                    payload,
                ),
            )
            conn.commit()
        return record

    def latest_by_kind(self, kind: AISelfMemoryKind) -> list[AISelfMemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.payload_json
                FROM runtime_ai_self_memory m
                JOIN (
                    SELECT memory_key, MAX(version) AS version
                    FROM runtime_ai_self_memory
                    WHERE kind=?
                    GROUP BY memory_key
                ) latest
                ON latest.memory_key=m.memory_key AND latest.version=m.version
                ORDER BY m.memory_key
                """,
                (kind.value,),
            ).fetchall()
        return [self._decode(str(row["payload_json"])) for row in rows]
