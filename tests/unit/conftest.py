"""Shared helpers for unit tests (incl. V3.0.1 contract patch tests)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aios_core.contracts.refs import ObjectRef

AWARE = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
AWARE_LATER = AWARE + timedelta(hours=6)


def ref(object_id: str, revision: int | None = None) -> ObjectRef:
    return ObjectRef(object_id=object_id, revision=revision)


def world_kwargs(**overrides) -> dict:
    """The shared WorldObject field bundle every V3 extension object needs."""
    base = {
        "subject_id": "user-1",
        "revision": 1,
        "learned_at": AWARE,
        "recorded_at": AWARE,
        "created_by": "test-m0p",
    }
    base.update(overrides)
    return base
