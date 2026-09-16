"""Single-hop dependency isolator (C07 / M3-001R / V21).

Overturned facts invalidate only depth=1 downstream nodes.
Zero cascade avalanche; LLM recompute calls = 0.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, List


def invalidate_overturned_fact_single_hop(
    conn: sqlite3.Connection,
    overturned_node_id: str,
    reason: str,
) -> List[str]:
    """Mark only 1-hop direct downstream nodes as is_stale=1."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT downstream_node_id FROM node_dependencies WHERE upstream_node_id = ?",
        (overturned_node_id,),
    )
    rows = cursor.fetchall()
    direct_downstream = [r[0] for r in rows]

    now = datetime.now(timezone.utc).isoformat()
    for node_id in direct_downstream:
        cursor.execute(
            "UPDATE cognitive_nodes SET is_stale = 1, stale_reason = ?, stale_at = ? WHERE node_id = ?",
            (reason, now, node_id),
        )
    conn.commit()
    return direct_downstream
