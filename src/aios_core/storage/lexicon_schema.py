"""词典/检索层存储基础设施（M1-023/M1-018 共用的物理支座）。

刻意不碰 sqlite_store._initialize()——那是 M0 冻结面的初始化器；
词典与检索层是自包含的新 schema，首次使用时 ensure，版本演进用 IF NOT EXISTS + 追加列，
与"旧 ObjectType 数据可复现迁移"同一纪律。

M1-018 三表 + 一水位（I5 DDL 的 sim 形态）：
  term_postings       词项→对象倒排（可重建；dict_version 钉住词典代际）
  entity_postings     实体→对象（role 区分 participant/subject/mention/pronoun_anchor）
  object_fts          FTS5 预分词外部面（unicode61 只负责切空格，切中文的工作在词典层做掉了）
  dependency_walk_cache 深度=1 的图边物化（查询期再做 ≤2 跳有界 BFS）
  index_watermark     索引水位（partial/stale 诚实地广播，不得沉默）
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

-- ---- M1-018 共现检索层 -------------------------------------------------

CREATE TABLE IF NOT EXISTS term_postings (
    term         TEXT NOT NULL,
    object_id    TEXT NOT NULL,
    weight       REAL NOT NULL,
    dict_version INTEGER NOT NULL,
    is_alias     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(term, object_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_postings_object ON term_postings(object_id);
CREATE INDEX IF NOT EXISTS idx_postings_dictver ON term_postings(dict_version);

CREATE TABLE IF NOT EXISTS entity_postings (
    entity_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    role      TEXT NOT NULL,
    PRIMARY KEY(entity_id, object_id, role)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_entity_postings_object ON entity_postings(object_id);

CREATE TABLE IF NOT EXISTS dependency_walk_cache (
    src        TEXT NOT NULL,
    dst        TEXT NOT NULL,
    depth      INTEGER NOT NULL,
    edge_types TEXT NOT NULL,
    PRIMARY KEY(src, dst, depth)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_depwalk_dst ON dependency_walk_cache(dst);

CREATE TABLE IF NOT EXISTS index_watermark (
    lane         TEXT PRIMARY KEY,
    world_rev    INTEGER NOT NULL,
    object_count INTEGER NOT NULL,
    built_at     TEXT NOT NULL,
    dict_version INTEGER NOT NULL
);
"""

FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS object_fts "
    "USING fts5(object_id UNINDEXED, body, tokenize='unicode61');"
)

EXPECTED_TABLES = ("tokenizer_dict_pack", "alias_miss_log")
EXPECTED_SEARCH_TABLES = ("term_postings", "entity_postings", "dependency_walk_cache", "index_watermark", "object_fts")


def ensure_lexicon_schema(conn: sqlite3.Connection) -> None:
    """幂等地建立词典层 schema（可反复调用，绝不 DROP）。"""
    _ensure(conn, EXPECTED_TABLES)

    _ensure(conn, EXPECTED_SEARCH_TABLES, extra_scripts=(FTS_DDL,))


def _ensure(
    conn: sqlite3.Connection,
    tables: tuple[str, ...],
    extra_scripts: tuple[str, ...] = (),
) -> None:
    conn.executescript(LEXICON_SCHEMA)
    for stmt in extra_scripts:
        conn.execute(stmt)
    present = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
    }
    missing = [t for t in tables if t not in present]
    if missing:
        raise RuntimeError(f"lexicon schema ensure failed, missing tables: {missing}")
