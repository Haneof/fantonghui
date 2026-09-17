"""Durable Conversation Working State for long-running sessions.

The state is an append-only runtime checkpoint: it tells the next model turn where
this conversation currently stands without pretending to replace the raw turn
history. Every state version can point back to raw turns/entities/evidence, and old
versions remain queryable.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now
from aios_core.storage.idempotency import canonical_json_dumps


class ConversationWorkingState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    current_topic: str | None = None
    topic_branches: tuple[str, ...] = ()
    open_loops: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    commitments: tuple[str, ...] = ()
    key_turn_refs: tuple[str, ...] = ()
    relevant_entity_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    updated_at: datetime = Field(default_factory=utc_now)
    supersedes_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_state(self) -> "ConversationWorkingState":
        as_utc(self.updated_at, "updated_at")
        if not self.session_id.strip():
            raise ValueError("session_id must not be blank")
        if self.version == 1 and self.supersedes_version is not None:
            raise ValueError("version 1 cannot supersede an earlier version")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise ValueError("state versions must form a contiguous append-only chain")
        for field_name in (
            "topic_branches",
            "open_loops",
            "unresolved_questions",
            "commitments",
            "key_turn_refs",
            "relevant_entity_refs",
            "evidence_refs",
        ):
            values = getattr(self, field_name)
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain only non-blank strings")
        return self


class ConversationStateConflict(ValueError):
    pass


class ConversationStateStore:
    """Append-only durable store, intentionally separate from frozen WorldObject schema."""

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
                CREATE TABLE IF NOT EXISTS runtime_conversation_state_revisions(
                    session_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(session_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_conversation_state_latest
                ON runtime_conversation_state_revisions(session_id, version DESC)
                """
            )
            conn.commit()

    def append(self, state: ConversationWorkingState) -> ConversationWorkingState:
        # Revalidate a possibly caller-mutated model copy before durable write.
        state = ConversationWorkingState.model_validate(state.model_dump(mode="python"))
        payload = canonical_json_dumps(state.model_dump(mode="python"))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT MAX(version) AS version FROM runtime_conversation_state_revisions WHERE session_id=?",
                (state.session_id,),
            ).fetchone()
            current = int(row["version"]) if row and row["version"] is not None else 0
            expected = current + 1
            if state.version != expected:
                conn.rollback()
                raise ConversationStateConflict(
                    f"session {state.session_id!r} must append version {expected}, got {state.version}"
                )
            conn.execute(
                """
                INSERT INTO runtime_conversation_state_revisions(
                    session_id, version, updated_at, payload_json
                ) VALUES(?,?,?,?)
                """,
                (
                    state.session_id,
                    state.version,
                    canonical_utc_iso(state.updated_at, "updated_at"),
                    payload,
                ),
            )
            conn.commit()
        return state

    @staticmethod
    def _decode(raw: str) -> ConversationWorkingState:
        return ConversationWorkingState.model_validate(json.loads(raw))

    def latest(self, session_id: str) -> ConversationWorkingState | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM runtime_conversation_state_revisions
                WHERE session_id=?
                ORDER BY version DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def get(self, session_id: str, version: int) -> ConversationWorkingState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM runtime_conversation_state_revisions WHERE session_id=? AND version=?",
                (session_id, version),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def history(self, session_id: str) -> list[ConversationWorkingState]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM runtime_conversation_state_revisions
                WHERE session_id=?
                ORDER BY version ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._decode(str(row["payload_json"])) for row in rows]
