"""Dual-lens world view reader (Gate B2: AS_KNOWN vs ANNOTATED).

- AS_KNOWN: Point-in-time snapshot respecting knowledge cutoff;
- ANNOTATED: Current annotated reality with Reinterpretation overlays.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from aios_core.contracts.models import ObjectType
from aios_core.storage.sqlite_store import SQLiteWorldStore


def view_at(
    store: SQLiteWorldStore,
    *,
    at: datetime,
    view: str = "AS_KNOWN",
    pin_revision: int | None = None,
) -> dict[str, Any]:
    """Dual-lens reader (Gate B2 delivery)."""
    if pin_revision is not None and pin_revision <= 0:
        raise ValueError(f"invalid pin_revision: {pin_revision}, cutoff revision must be >= 1")
    if view not in ("AS_KNOWN", "ANNOTATED"):
        raise ValueError(f"unknown view: {view}, expected AS_KNOWN or ANNOTATED")

    if view == "AS_KNOWN":
        payloads = store.list_payloads(knowledge_cutoff=at)
        return {p["object_id"]: p for p in payloads}
    else:  # ANNOTATED
        payloads = store.list_payloads(knowledge_cutoff=at)
        obj_map = {p["object_id"]: dict(p) for p in payloads}

        all_reinterps = store.list_payloads(object_type=ObjectType.REINTERPRETATION)
        for r in all_reinterps:
            target_ref = r.get("target_ref")
            if target_ref and isinstance(target_ref, dict):
                tid = target_ref.get("object_id")
                if tid in obj_map:
                    obj = obj_map[tid]
                    annos = obj.setdefault("annotations", [])
                    annos.append(r)
                    stmt = r.get("statement", "")
                    obj["reinterpretation_statement"] = stmt
                    obj["annotations_text"] = stmt
        return obj_map
