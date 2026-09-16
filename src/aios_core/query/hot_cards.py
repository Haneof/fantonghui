"""HotCard Entity x Day precomputation pipeline (M1-020 / Gate B4).

Fast-path synchronous recall budget <= 50ms.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from aios_core.contracts.models import ObjectType
from aios_core.contracts.time import as_utc


def _ensure_hot_cards_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hot_cards (
            subject_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            day_us INTEGER NOT NULL,
            digest_json TEXT NOT NULL,
            built_from_revision INTEGER NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(subject_id, entity_id, day_us)
        );
        CREATE TABLE IF NOT EXISTS hot_cards_dirty (
            subject_id TEXT,
            entity_id TEXT,
            day_us INTEGER,
            marked_from_revision INTEGER NOT NULL,
            PRIMARY KEY(subject_id, entity_id, day_us)
        );
        CREATE TABLE IF NOT EXISTS hot_cards_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def build_cards(store: Any, *, day: datetime) -> None:
    """Build hot cards for entities touching the given day."""
    day_us = int(as_utc(day, "day").timestamp() * 1_000_000)
    current_rev = store.current_world_revision()

    entities = store.list_payloads(object_type=ObjectType.ENTITY)
    events = store.list_payloads(object_type=ObjectType.EVENT)
    reinterps = store.list_payloads(object_type=ObjectType.REINTERPRETATION)

    reinterp_map: dict[str, str] = {}
    for r in reinterps:
        t_ref = r.get("target_ref")
        if isinstance(t_ref, dict) and "object_id" in t_ref:
            reinterp_map[t_ref["object_id"]] = r.get("statement", "")

    db_path = getattr(store, "db_path", None)
    if not db_path:
        return

    with sqlite3.connect(db_path) as conn:
        _ensure_hot_cards_schema(conn)
        for ent in entities:
            eid = ent["object_id"]
            sub = ent.get("subject_id", "u1")

            matching_events = []
            for ev in events:
                p_refs = ev.get("participant_refs", [])
                p_ids = [p.get("object_id") for p in p_refs if isinstance(p, dict)]
                if eid in p_ids:
                    matching_events.append(ev)

            recent_event_digest = {}
            if matching_events:
                ev = matching_events[-1]
                ev_id = ev["object_id"]
                stmt = reinterp_map.get(ev_id, "")
                recent_event_digest = {
                    "object_id": ev_id,
                    "revision": ev.get("revision", 1),
                    "title": ev.get("title", ""),
                    "interpretation": ev.get("interpretation", ""),
                    "reinterpretation": stmt,
                    "summary": f"{ev.get('title', '')} - {stmt}" if stmt else ev.get("title", ""),
                }

            digest = {
                "recent_event": recent_event_digest,
                "canonical_name": ent.get("canonical_name", ""),
                "entity_id": eid,
            }

            conn.execute(
                """
                INSERT OR REPLACE INTO hot_cards (
                    subject_id, entity_id, day_us, digest_json, built_from_revision, stale
                ) VALUES (?, ?, ?, ?, ?, 0)
                """,
                (sub, eid, day_us, json.dumps(digest, ensure_ascii=False), current_rev),
            )
        conn.commit()


def fetch_hot_cards(
    store: Any,
    subject_id: str,
    entity_ids: list[str],
    *,
    day: datetime,
    as_of_revision: int | None = None,
) -> dict[str, Any]:
    """Fetch hot card digest for given entity (PK query <= 50ms)."""
    day_us = int(as_utc(day, "day").timestamp() * 1_000_000)
    eid = entity_ids[0] if entity_ids else ""

    db_path = getattr(store, "db_path", None)
    if db_path:
        with sqlite3.connect(db_path) as conn:
            _ensure_hot_cards_schema(conn)
            row = conn.execute(
                "SELECT digest_json, built_from_revision, stale FROM hot_cards WHERE subject_id=? AND entity_id=? AND day_us=?",
                (subject_id, eid, day_us),
            ).fetchone()
            if row:
                digest = json.loads(row[0])
                return {
                    "subject_id": subject_id,
                    "entity_id": eid,
                    "day": day.isoformat(),
                    "digest": digest,
                    "built_from_revision": row[1],
                    "stale": row[2],
                }

    # On-demand fallback synthesis if not yet cached in hot_cards
    payloads = store.list_payloads(knowledge_cutoff=day)
    events = [p for p in payloads if p.get("object_type") == "event"]
    reinterps = [p for p in payloads if p.get("object_type") == "reinterpretation"]

    reinterp_map: dict[str, str] = {}
    for r in reinterps:
        t_ref = r.get("target_ref")
        if isinstance(t_ref, dict) and "object_id" in t_ref:
            reinterp_map[t_ref["object_id"]] = r.get("statement", "")

    matching = []
    for ev in events:
        p_refs = ev.get("participant_refs", [])
        p_ids = [p.get("object_id") for p in p_refs if isinstance(p, dict)]
        if eid in p_ids:
            matching.append(ev)

    recent = {}
    if matching:
        ev = matching[-1]
        ev_id = ev["object_id"]
        stmt = reinterp_map.get(ev_id, "")
        recent = {
            "object_id": ev_id,
            "revision": ev.get("revision", 1),
            "title": ev.get("title", ""),
            "reinterpretation": stmt,
            "summary": f"{ev.get('title', '')} - {stmt}" if stmt else ev.get("title", ""),
        }

    return {
        "subject_id": subject_id,
        "entity_id": eid,
        "day": day.isoformat(),
        "digest": {
            "recent_event": recent,
            "entity_id": eid,
        },
        "built_from_revision": store.current_world_revision(),
        "stale": 0,
    }
