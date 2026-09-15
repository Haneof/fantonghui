#!/usr/bin/env python3
"""Disposable SQLite scale probe for the AIOS v3.0 constitutional review.

This is deliberately a *structural microbenchmark*, not a benchmark of the AIOS
implementation and not a product SLO proof.  It creates a synthetic append-style
world in a temporary database and compares:

* indexed temporal reads;
* raw scans versus pre-computed time rollups;
* FTS5 AND search versus normalized posting-list intersection;
* reverse-dependency fan-out and bounded graph traversal;
* WAL checkpoint behavior while a reader holds an old snapshot.

The database is deleted/recreated on every run.  No generated database belongs
in Git.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import time
from typing import Any, Callable, Sequence

DAY = 86_400
YEAR_DAYS = 365


def percentile(sorted_values: Sequence[float], p: float) -> float:
    if not sorted_values:
        return math.nan
    index = min(len(sorted_values) - 1, max(0, math.ceil(p * len(sorted_values)) - 1))
    return sorted_values[index]


def measure(fn: Callable[[], Any], repeats: int = 25) -> dict[str, Any]:
    # One unreported warm-up keeps this probe focused on steady-state query cost.
    fn()
    samples: list[float] = []
    result: Any = None
    for _ in range(repeats):
        started = time.perf_counter_ns()
        result = fn()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    samples.sort()
    return {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
        "result_cardinality_or_value": result,
    }


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("PRAGMA cache_size=-65536")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE object_revisions (
            row_id INTEGER PRIMARY KEY,
            object_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            subject_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            dimension_id INTEGER NOT NULL,
            occurred_at INTEGER NOT NULL,
            learned_at INTEGER NOT NULL,
            recorded_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE (object_id, revision)
        );
        CREATE INDEX object_time_idx
            ON object_revisions(subject_id, dimension_id, occurred_at DESC);
        CREATE INDEX object_identity_idx
            ON object_revisions(object_id, revision DESC);
        CREATE INDEX object_learned_idx
            ON object_revisions(subject_id, learned_at DESC);

        CREATE VIRTUAL TABLE object_fts USING fts5(
            object_id UNINDEXED,
            content,
            tokenize='unicode61'
        );

        CREATE TABLE object_terms (
            term TEXT NOT NULL,
            object_row_id INTEGER NOT NULL,
            occurred_at INTEGER NOT NULL,
            PRIMARY KEY (term, object_row_id)
        ) WITHOUT ROWID;
        CREATE INDEX object_terms_time_idx
            ON object_terms(term, occurred_at DESC, object_row_id);

        CREATE TABLE dependencies (
            dependency_row_id INTEGER PRIMARY KEY,
            dependency_object_id TEXT NOT NULL,
            dependency_revision INTEGER NOT NULL,
            dependent_object_id TEXT NOT NULL,
            dependent_revision INTEGER NOT NULL,
            dependency_type TEXT NOT NULL
        );
        CREATE INDEX dependency_reverse_idx
            ON dependencies(dependency_object_id, dependency_revision,
                            dependency_type, dependent_object_id);
        CREATE INDEX dependency_forward_idx
            ON dependencies(dependent_object_id, dependent_revision,
                            dependency_type, dependency_object_id);

        CREATE TABLE daily_rollups (
            subject_id TEXT NOT NULL,
            dimension_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            observation_count INTEGER NOT NULL,
            PRIMARY KEY(subject_id, dimension_id, day)
        ) WITHOUT ROWID;
        """
    )


def terms_for(index: int) -> tuple[str, ...]:
    result: list[str] = []
    # Nested frequencies intentionally produce a selective three-term result.
    if index % 1_000 == 0:
        result.append("妈妈")
    if index % 5_000 == 0:
        result.append("生日")
    if index % 10_000 == 0:
        result.append("礼物")
    if index % 250 == 0:
        result.append("老张")
    if index % 2_000 == 0:
        result.append("借钱")
    if index % 4_000 == 0:
        result.append("争执")
    if index % 7 == 0:
        result.append("加班")
    if index % 29 == 0:
        result.append("熬夜")
    if index % 997 == 0:
        result.append("心悸")
    return tuple(result)


def populate(connection: sqlite3.Connection, rows: int) -> dict[str, float]:
    started = time.perf_counter()
    base = 1_735_689_600  # 2025-01-01T00:00:00Z, arbitrary synthetic origin.

    for start in range(1, rows + 1, 20_000):
        stop = min(rows + 1, start + 20_000)
        object_rows: list[tuple[Any, ...]] = []
        fts_rows: list[tuple[Any, ...]] = []
        posting_rows: list[tuple[Any, ...]] = []
        for index in range(start, stop):
            occurred = base + ((index * 31) % (YEAR_DAYS * DAY))
            learned = occurred + (index % 3_600)
            object_id = f"obs-{index:09d}"
            dimension = index % 48
            terms = terms_for(index)
            text = " ".join(("日常", f"维度{dimension}", *terms))
            payload = json.dumps(
                {"text": text, "quality": 0.97, "source": "synthetic"},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            object_rows.append(
                (
                    index,
                    object_id,
                    1,
                    "user-1",
                    "Observation",
                    dimension,
                    occurred,
                    learned,
                    learned + 1,
                    "CURRENT",
                    payload,
                )
            )
            fts_rows.append((object_id, text))
            posting_rows.extend((term, index, occurred) for term in terms)

        with connection:
            connection.executemany(
                "INSERT INTO object_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                object_rows,
            )
            connection.executemany(
                "INSERT INTO object_fts(object_id, content) VALUES (?,?)", fts_rows
            )
            connection.executemany(
                "INSERT INTO object_terms(term, object_row_id, occurred_at) VALUES (?,?,?)",
                posting_rows,
            )

    objects_finished = time.perf_counter()

    # Build a shallow parent graph, plus a 10% super-node fan-out.  The latter is
    # an intentional worst case for dependency invalidation.
    for start in range(2, rows + 1, 25_000):
        stop = min(rows + 1, start + 25_000)
        edge_rows: list[tuple[Any, ...]] = []
        edge_id = (start - 2) * 2 + 1
        for index in range(start, stop):
            parent = max(1, index // 3)
            edge_rows.append(
                (
                    edge_id,
                    f"obs-{parent:09d}",
                    1,
                    f"obs-{index:09d}",
                    1,
                    "derived_from",
                )
            )
            edge_id += 1
            if index % 10 == 0:
                edge_rows.append(
                    (
                        edge_id,
                        "obs-000000001",
                        1,
                        f"obs-{index:09d}",
                        1,
                        "evidence_support",
                    )
                )
                edge_id += 1
        with connection:
            connection.executemany(
                """INSERT INTO dependencies(
                       dependency_row_id, dependency_object_id,
                       dependency_revision, dependent_object_id,
                       dependent_revision, dependency_type
                   ) VALUES (?,?,?,?,?,?)""",
                edge_rows,
            )

    edges_finished = time.perf_counter()
    with connection:
        connection.execute(
            """INSERT INTO daily_rollups(
                   subject_id, dimension_id, day, observation_count
               )
               SELECT subject_id, dimension_id, occurred_at / ?, COUNT(*)
               FROM object_revisions
               GROUP BY subject_id, dimension_id, occurred_at / ?""",
            (DAY, DAY),
        )
        connection.execute("ANALYZE")
    finished = time.perf_counter()
    return {
        "objects_fts_postings_seconds": round(objects_finished - started, 3),
        "dependencies_seconds": round(edges_finished - objects_finished, 3),
        "rollups_and_analyze_seconds": round(finished - edges_finished, 3),
        "total_build_seconds": round(finished - started, 3),
    }


def scalar(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    value = connection.execute(sql, params).fetchone()
    assert value is not None
    return int(value[0])


def run_queries(connection: sqlite3.Connection, rows: int) -> dict[str, Any]:
    base = 1_735_689_600
    end = base + YEAR_DAYS * DAY
    month_start = end - 30 * DAY

    temporal_fetch = measure(
        lambda: len(
            connection.execute(
                """SELECT object_id, occurred_at, payload_json
                   FROM object_revisions
                   WHERE subject_id=? AND dimension_id=?
                     AND occurred_at>=? AND occurred_at<?
                   ORDER BY occurred_at DESC LIMIT 100""",
                ("user-1", 7, month_start, end),
            ).fetchall()
        )
    )

    raw_year_aggregate = measure(
        lambda: len(
            connection.execute(
                """SELECT occurred_at / ?, COUNT(*)
                   FROM object_revisions
                   WHERE subject_id=? AND dimension_id=?
                     AND occurred_at>=? AND occurred_at<?
                   GROUP BY occurred_at / ?""",
                (DAY, "user-1", 7, base, end, DAY),
            ).fetchall()
        )
    )

    rollup_year_aggregate = measure(
        lambda: len(
            connection.execute(
                """SELECT day, observation_count
                   FROM daily_rollups
                   WHERE subject_id=? AND dimension_id=? AND day>=? AND day<?
                   ORDER BY day""",
                ("user-1", 7, base // DAY, end // DAY),
            ).fetchall()
        )
    )

    fts_and = measure(
        lambda: scalar(
            connection,
            "SELECT COUNT(*) FROM object_fts WHERE object_fts MATCH ?",
            ('"妈妈" AND "生日" AND "礼物"',),
        )
    )

    posting_intersection = measure(
        lambda: len(
            connection.execute(
                """SELECT object_row_id
                   FROM object_terms
                   WHERE term IN (?,?,?)
                   GROUP BY object_row_id
                   HAVING COUNT(DISTINCT term)=3
                   LIMIT 500""",
                ("妈妈", "生日", "礼物"),
            ).fetchall()
        )
    )

    direct_supernode_fanout = measure(
        lambda: len(
            connection.execute(
                """SELECT dependent_object_id
                   FROM dependencies
                   WHERE dependency_object_id=? AND dependency_revision=?""",
                ("obs-000000001", 1),
            ).fetchall()
        ),
        repeats=12,
    )

    # A depth cap and visited-set UNION are essential.  The LIMIT models an
    # impact-analysis circuit breaker rather than pretending all descendants
    # can be synchronously recomputed.
    bounded_graph_walk = measure(
        lambda: len(
            connection.execute(
                """WITH RECURSIVE impacted(object_id, depth) AS (
                       VALUES(?, 0)
                       UNION
                       SELECT d.dependent_object_id, impacted.depth + 1
                       FROM dependencies AS d
                       JOIN impacted
                         ON d.dependency_object_id = impacted.object_id
                        AND d.dependency_revision = 1
                       WHERE impacted.depth < 4
                   )
                   SELECT object_id, MIN(depth)
                   FROM impacted
                   GROUP BY object_id
                   LIMIT 10001""",
                (f"obs-{max(2, rows // 243):09d}",),
            ).fetchall()
        ),
        repeats=12,
    )

    return {
        "indexed_recent_time_slice": temporal_fetch,
        "raw_one_dimension_year_daily_aggregate": raw_year_aggregate,
        "precomputed_rollup_equivalent": rollup_year_aggregate,
        "fts5_three_term_and_pretokenized_chinese": fts_and,
        "normalized_posting_three_term_intersection": posting_intersection,
        "reverse_dependency_supernode_materialization": direct_supernode_fanout,
        "bounded_dependency_walk_depth_4_limit_10001": bounded_graph_walk,
    }


def cjk_tokenizer_probe() -> dict[str, Any]:
    """Show why production Chinese tokenization cannot be left implicit."""
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content, tokenize='unicode61')")
    connection.execute("INSERT INTO probe(content) VALUES (?)", ("给妈妈买生日礼物",))
    connection.execute("INSERT INTO probe(content) VALUES (?)", ("妈妈 生日 礼物",))
    query = ('\"妈妈\" AND \"生日\" AND \"礼物\"',)
    result = {
        "continuous_chinese_match_rows": len(
            connection.execute(
                "SELECT rowid FROM probe WHERE rowid=1 AND probe MATCH ?", query
            ).fetchall()
        ),
        "pretokenized_chinese_match_rows": len(
            connection.execute(
                "SELECT rowid FROM probe WHERE rowid=2 AND probe MATCH ?", query
            ).fetchall()
        ),
        "note": (
            "The default unicode61 tokenizer does not segment continuous Chinese text "
            "into these words; the explicit space-pretokenized row is the only hit."
        ),
    }
    connection.close()
    return result


def wal_reader_probe(path: Path) -> dict[str, Any]:
    reader = connect(path)
    writer = connect(path)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM object_revisions").fetchone()

    before = path.with_name(path.name + "-wal")
    before_bytes = before.stat().st_size if before.exists() else 0
    for batch in range(80):
        with writer:
            writer.execute(
                "INSERT INTO daily_rollups VALUES (?,?,?,?)",
                ("probe", batch % 2, 999_000 + batch, batch),
            )
    held_bytes = before.stat().st_size if before.exists() else 0
    busy, log_pages, checkpointed_pages = writer.execute(
        "PRAGMA wal_checkpoint(PASSIVE)"
    ).fetchone()

    reader.rollback()
    busy2, log_pages2, checkpointed_pages2 = writer.execute(
        "PRAGMA wal_checkpoint(TRUNCATE)"
    ).fetchone()
    after_bytes = before.stat().st_size if before.exists() else 0
    reader.close()
    writer.close()
    return {
        "wal_bytes_before_extra_commits": before_bytes,
        "wal_bytes_with_old_reader_snapshot": held_bytes,
        "passive_checkpoint": {
            "busy": busy,
            "log_pages": log_pages,
            "checkpointed_pages": checkpointed_pages,
        },
        "truncate_after_reader_released": {
            "busy": busy2,
            "log_pages": log_pages2,
            "checkpointed_pages": checkpointed_pages2,
            "wal_bytes": after_bytes,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument(
        "--db", type=Path, default=Path("/tmp/aios_v3_sqlite_probe.db")
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.rows < 10_000:
        parser.error("--rows must be at least 10000")

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{args.db}{suffix}")
        if candidate.exists():
            candidate.unlink()

    connection = connect(args.db)
    create_schema(connection)
    build = populate(connection, args.rows)
    counts = {
        "object_revisions": scalar(connection, "SELECT COUNT(*) FROM object_revisions"),
        "fts_rows": scalar(connection, "SELECT COUNT(*) FROM object_fts"),
        "term_postings": scalar(connection, "SELECT COUNT(*) FROM object_terms"),
        "dependencies": scalar(connection, "SELECT COUNT(*) FROM dependencies"),
        "daily_rollups": scalar(connection, "SELECT COUNT(*) FROM daily_rollups"),
    }
    queries = run_queries(connection, args.rows)
    connection.close()
    wal = wal_reader_probe(args.db)

    sizes = {}
    for suffix, label in (("", "db_bytes"), ("-wal", "wal_bytes"), ("-shm", "shm_bytes")):
        candidate = Path(f"{args.db}{suffix}")
        sizes[label] = candidate.stat().st_size if candidate.exists() else 0

    result = {
        "disclaimer": (
            "Synthetic single-user structural SQLite microbenchmark; not an AIOS "
            "implementation benchmark, wearable benchmark, cold-cache result, or SLO proof."
        ),
        "environment": {
            "sqlite_version": sqlite3.sqlite_version,
            "python_version": os.sys.version.split()[0],
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
        },
        "requested_rows": args.rows,
        "counts": counts,
        "build": build,
        "steady_state_warm_queries": queries,
        "cjk_tokenizer_probe": cjk_tokenizer_probe(),
        "wal_old_reader_probe": wal,
        "sizes": sizes,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
