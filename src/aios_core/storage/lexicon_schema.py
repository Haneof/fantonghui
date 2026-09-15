"""词典层存储基础设施（M1-023/M1-018 共用的物理支座）。

刻意不碰 sqlite_store._initialize()——那是 M0 冻结面的初始化器；
词典层是自包含的新 schema，首次使用时 ensure，版本演进用 IF NOT EXISTS + 追加列，
与"旧 ObjectType 数据可复现迁移"同一纪律。
"""

from __future__ import annotations

import sqlite3

LEXICON_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokenizer_dict_pack (
    pack_id       TEXT PRIMARY KEY,
    version       INTEGER NOT NULL,
    source        TEXT NOT NULL,
    terms_json    TEXT NOT NULL,
    terms_sha     TEXT NOT NULL,
    created_rev   INTEGER NOT NULL,
    UNIQUE(version, source)
);

CREATE TABLE IF NOT EXISTS alias_miss_log (
    surface        TEXT NOT NULL,
    dict_version   INTEGER NOT NULL,
    first_seen_rev INTEGER NOT NULL,
    occurrences    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(surface, dict_version)
) WITHOUT ROWID;
"""

EXPECTED_TABLES = ("tokenizer_dict_pack", "alias_miss_log")


def ensure_lexicon_schema(conn: sqlite3.Connection) -> None:
    """幂等地建立词典层 schema（可反复调用，绝不 DROP）。"""
    conn.executescript(LEXICON_SCHEMA)
    present = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing = [t for t in EXPECTED_TABLES if t not in present]
    if missing:
        raise RuntimeError(f"lexicon schema ensure failed, missing tables: {missing}")
