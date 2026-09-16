"""Voiceprint TTL and Edge Cleaner (C01 / M1-001R / V23).

180-day TTL for unknown stranger voiceprints; active entity bindings preserved.
"""

from __future__ import annotations

from typing import Any, Dict, List


def prune_expired_voiceprints(
    voiceprints: List[Dict[str, Any]],
    current_day_offset: int,
    ttl_days: int = 180,
) -> int:
    """Prune unbound stranger voiceprints that exceed TTL."""
    pruned_count = 0
    for vp in voiceprints:
        if vp.get("bound_entity_id"):
            continue
        last_seen = vp.get("last_seen_day", 0)
        if (current_day_offset - last_seen) > ttl_days:
            vp["is_tombstone"] = True
            pruned_count += 1
    return pruned_count
