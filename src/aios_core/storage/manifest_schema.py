"""M1-022 Manifest 数据面物理层（R4 §3.4-M1-022，纯增量，不碰冻结初始化器）。

  l0_slice           L0 确定性切片的机械面：（主体, 切片种类）→ 最新载荷 + 钉版指针。
                     写入是 writer 的事（自我状态/羁绊/现场 writers 属 C05/C06/C15），
                     本表面只承诺：按主键一次索引直查即为装配供给全部 L0 输入。
  manifest_instance  版本化 Manifest 物化证据（宪法 §86.4 运行日志 / R4 I2 核心承诺的
                     v0 地基）：append-only，UPDATE/DELETE 由触发器物理拒绝；
                     manifest_version=0 锁死 v0 平面，v1 归 M2-017 的 WorldObject 出口。

  id 设计：内容寻址（canonical_hash 前 16 位）。同世界状态 + 同唤醒输入 ⇒ 同 id，
  INSERT OR IGNORE 幂等——重放不产生第二行，这本身就是"确定性装配"的物证。
"""

from __future__ import annotations

import sqlite3

MANIFEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS l0_slice (
    subject_id        TEXT NOT NULL,
    slice_kind        TEXT NOT NULL,   -- self_state|rapport|now_context|capability_registry
    payload_json      TEXT NOT NULL CHECK (json_valid(payload_json)),  -- 写入侧已 canonical 化
    source_object_id  TEXT NOT NULL,   -- 切片的世界对象指针（钉版）
    source_revision   INTEGER NOT NULL CHECK (source_revision >= 1),
    freshness_at      TEXT NOT NULL,   -- 切片最新鲜时刻（UTC ISO, aware）
    slice_rev         INTEGER NOT NULL, -- 写入时的 world revision（代际）
    PRIMARY KEY (subject_id, slice_kind)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS manifest_instance (
    manifest_id       TEXT PRIMARY KEY,  -- mani0-<canonical_hash[:16]>（内容寻址）
    manifest_version  INTEGER NOT NULL CHECK (manifest_version = 0),
    subject_id        TEXT NOT NULL,
    wake_object_id    TEXT NOT NULL,
    wake_revision     INTEGER NOT NULL CHECK (wake_revision >= 1),
    wake_reason_kind  TEXT NOT NULL,
    lane              TEXT NOT NULL CHECK (lane IN ('notify','investigate','chapter')),
    body_json         TEXT NOT NULL CHECK (json_valid(body_json)),  -- 装配全量 canonical body
    omissions_json    TEXT NOT NULL CHECK (json_valid(omissions_json)),
    ready_task_count  INTEGER NOT NULL CHECK (ready_task_count >= 0),
    token_total       INTEGER NOT NULL CHECK (token_total >= 0),
    build_ms          REAL NOT NULL,
    queries_executed  INTEGER NOT NULL,
    world_rev         INTEGER NOT NULL,
    estimator_version TEXT NOT NULL,
    canonical_hash    TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS mi_subject_time ON manifest_instance(subject_id, created_at);

-- 物化即证据：宪法 §86.4 / R4 I2「被遗忘的看板是不存在的归因」的物理臂
CREATE TRIGGER IF NOT EXISTS manifest_no_update BEFORE UPDATE ON manifest_instance
BEGIN SELECT RAISE(ABORT, 'manifest_instance is append-only evidence'); END;
CREATE TRIGGER IF NOT EXISTS manifest_no_delete BEFORE DELETE ON manifest_instance
BEGIN SELECT RAISE(ABORT, 'manifest_instance is append-only evidence'); END;
"""

EXPECTED_TABLES = ("l0_slice", "manifest_instance")

EXPECTED_TRIGGERS = ("manifest_no_update", "manifest_no_delete")


def ensure_manifest_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(MANIFEST_SCHEMA)
    present = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger')"
        ).fetchall()
    }
    missing = [t for t in (*EXPECTED_TABLES, *EXPECTED_TRIGGERS) if t not in present]
    if missing:
        raise RuntimeError(f"manifest schema ensure failed, missing: {missing}")
