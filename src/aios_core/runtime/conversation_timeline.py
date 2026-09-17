"""Append-only raw conversation timeline.

Summaries, working state and long-term cognition may reference these turns, but they
never replace or rewrite the original user/assistant text.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now
from aios_core.storage.idempotency import canonical_json_dumps


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    turn_index: int = Field(ge=1)
    turn_id: str = Field(min_length=1)
    user_text: str
    assistant_text: str
    occurred_at: datetime = Field(default_factory=utc_now)
    recorded_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_turn(self) -> "ConversationTurn":
        if not self.session_id.strip() or not self.turn_id.strip():
            raise ValueError("session_id/turn_id must not be blank")
        occurred = as_utc(self.occurred_at, "occurred_at")
        recorded = as_utc(self.recorded_at, "recorded_at")
        if recorded < occurred:
            raise ValueError("recorded_at must be >= occurred_at")
        return self

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        turn_index: int,
        user_text: str,
        assistant_text: str,
        occurred_at: datetime | None = None,
        recorded_at: datetime | None = None,
    ) -> "ConversationTurn":
        occurred = occurred_at or utc_now()
        recorded = recorded_at or utc_now()
        identity = canonical_json_dumps(
            {
                "session_id": session_id,
                "turn_index": turn_index,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "occurred_at": occurred,
            }
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return cls(
            session_id=session_id,
            turn_index=turn_index,
            turn_id=f"turn_{digest}",
            user_text=user_text,
            assistant_text=assistant_text,
            occurred_at=occurred,
            recorded_at=recorded,
        )


class ConversationTimelineConflict(ValueError):
    pass


class ConversationTimelineStore:
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
                CREATE TABLE IF NOT EXISTS runtime_conversation_turns(
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    turn_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY(session_id, turn_index)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_turns_time
                ON runtime_conversation_turns(session_id, occurred_at)
                """
            )
            conn.commit()

    @staticmethod
    def _payload(turn: ConversationTurn) -> tuple[str, str]:
        payload = canonical_json_dumps(turn.model_dump(mode="python"))
        return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode(raw: str) -> ConversationTurn:
        return ConversationTurn.model_validate(json.loads(raw))

    def append(self, turn: ConversationTurn) -> ConversationTurn:
        turn = ConversationTurn.model_validate(turn.model_dump(mode="python"))
        payload, digest = self._payload(turn)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT payload_sha256, payload_json
                FROM runtime_conversation_turns
                WHERE session_id=? AND turn_index=?
                """,
                (turn.session_id, turn.turn_index),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_sha256"]) == digest:
                    conn.rollback()
                    return self._decode(str(existing["payload_json"]))
                conn.rollback()
                raise ConversationTimelineConflict(
                    f"turn slot already sealed with different content: {turn.session_id}@{turn.turn_index}"
                )

            previous = conn.execute(
                "SELECT MAX(turn_index) AS idx FROM runtime_conversation_turns WHERE session_id=?",
                (turn.session_id,),
            ).fetchone()
            current = int(previous["idx"]) if previous and previous["idx"] is not None else 0
            if turn.turn_index != current + 1:
                conn.rollback()
                raise ConversationTimelineConflict(
                    f"session {turn.session_id!r} must append turn {current + 1}, got {turn.turn_index}"
                )

            conn.execute(
                """
                INSERT INTO runtime_conversation_turns(
                    session_id, turn_index, turn_id, occurred_at, recorded_at,
                    payload_json, payload_sha256
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    turn.session_id,
                    turn.turn_index,
                    turn.turn_id,
                    canonical_utc_iso(turn.occurred_at, "occurred_at"),
                    canonical_utc_iso(turn.recorded_at, "recorded_at"),
                    payload,
                    digest,
                ),
            )
            conn.commit()
        return turn

    def get(self, session_id: str, turn_index: int) -> ConversationTurn | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM runtime_conversation_turns WHERE session_id=? AND turn_index=?",
                (session_id, turn_index),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def list_turns(
        self,
        session_id: str,
        *,
        after_turn: int = 0,
        limit: int = 1000,
    ) -> list[ConversationTurn]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM runtime_conversation_turns
                WHERE session_id=? AND turn_index>?
                ORDER BY turn_index ASC LIMIT ?
                """,
                (session_id, after_turn, max(1, int(limit))),
            ).fetchall()
        return [self._decode(str(row["payload_json"])) for row in rows]
