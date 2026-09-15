"""M1-021 就绪索引物理面（R4 §3.4-M1-021 DDL 的 sim 形态，纯增量，不碰冻结初始化器）。

  subscription_key  就绪检查的唯一索引本体：tick 永远只查这张表，永远不扫 task 全表
  ready_view        物化就绪集：给 C15/M2-016 的只读消费面（world_rev 记代际）
  task_proxy        任务侧代理（r2 Task 是冻结面；条件绑定/僵尸线走这里，
                    与 ConditionalTaskPatch 的 trigger_expr_ref/max_wait 对位）
"""

from __future__ import annotations

import sqlite3

ELIGIBILITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_key (
    expr_id   TEXT NOT NULL,
    key_kind  TEXT NOT NULL,   -- time_due|event|obs_pred|dep_ready|sem_review_due
    key_value TEXT NOT NULL,
    due_at    TEXT,            -- time 类键的物化到期点（UTC ISO，tz 已解析）
    PRIMARY KEY (expr_id, key_kind, key_value)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS sk_lookup ON subscription_key(key_kind, key_value, due_at);

CREATE TABLE IF NOT EXISTS ready_view (
    task_id     TEXT PRIMARY KEY,
    ready_since TEXT NOT NULL,
    reason_json TEXT NOT NULL,
    world_rev   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS task_proxy (
    task_id          TEXT PRIMARY KEY,
    expr_id          TEXT NOT NULL,
    subject_id       TEXT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|READY|DUE_FOR_REVIEW|COMPLETED|CANCELLED
    max_wait_seconds INTEGER,
    created_at       TEXT NOT NULL,
    ready_rev        INTEGER
);
CREATE INDEX IF NOT EXISTS tp_expr ON task_proxy(expr_id);
"""

EXPECTED_TABLES = ("subscription_key", "ready_view", "task_proxy")

# 终态集合：僵尸回收只扫这些之外的代理
TERMINAL_STATES = ("COMPLETED", "CANCELLED", "DUE_FOR_REVIEW")


def ensure_eligibility_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ELIGIBILITY_SCHEMA)
    present = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    missing = [t for t in EXPECTED_TABLES if t not in present]
    if missing:
        raise RuntimeError(f"eligibility schema ensure failed, missing: {missing}")
