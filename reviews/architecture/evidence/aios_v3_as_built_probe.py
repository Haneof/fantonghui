#!/usr/bin/env python3
"""AIOS 宪法 v3.0 "as-built" 工程压力探针（独立评审工具，不 import、不修改产品代码）。

与同目录 `aios_v3_sqlite_probe.py`（报告 A 的 360 万对象结构微基准，测量的是**建议设计**
在自建 schema 上的表现）互补：本探针刻意只使用 **M0-017 已冻结的生产 schema 原形**
（payload_json blob + 仅有的 3 个索引），因此它测量的是"仓库今天真实能做什么"，
即宪法承诺与 as-built 实现之间的**差距量级**，而不是任何推荐方案的上限。

目的
----
宪法 v3.0 第八十五条/八十七条/八十九条/九十条/九十三条 对检索延迟、5D 时间滑动条、
多关键词共现联想、依赖回溯传播提出了"毫秒级/秒级""绝不算力雪崩"的硬性主张。
本探针在 **M0-017 已冻结的 SQLite 追加式版本库真实 schema 形状**上，用一年量级
（100 万条 object revision / 100 万条 dependency edge）的合成世界数据，实测：

  P1   存储体积与批量写入吞吐（WAL, synchronous=FULL, batch=10k）
  P1b  单条提交（1 Observation = 1 world_revision）的 fsync 代价：FULL vs NORMAL
  P2   已建索引的点查 / 类型+主体查 / learned_at 范围查（当前 schema 能做什么）
  P2b  单次看盘聚合看板（Cockpit Manifest）四步序组装的真实存储代价
  P3   多关键词共现检索：payload_json LIKE 全表扫描（当前 schema 唯一可行做法）
  P4   5D 时间滑动条：json_extract(occurred_at) 范围查询（当前 schema 唯一可行做法）
  P5   FTS5 三条路线对中文关键词的可用性：unicode61 / trigram / 预分词列
  P6   规范化倒排索引 keyword_posting + time_bucket 的构建成本、体积、延迟与结果等价性
  P6b  co_search 查询形状对照：GROUP BY 全量聚合 vs 最稀有关键词驱动 EXISTS
  P7   依赖传播：M0 内存反向扫描（object_revisions 全量 + json.loads + BFS）
       vs 规范化 dependency_edges 反向索引 + 预算上限，含枢纽实体雪崩扇出与复核 token 代价
  P8   由实测外推的一年期行数 / 存储账（宪法第三十三条边缘轻量化前提）
  P9   一年期 LLM token 账（确定性算术模型，不调用任何模型）

产物
----
标准输出为人类可读日志 + 末尾 `JSON_SUMMARY` 单行 JSON（供报告直接引用）。
数据库文件写在 /tmp（scratch），不进入仓库；.gitignore 已排除 *.db。

用法
----
    python3 probe_scale_v3.py [--rows 1000000] [--edges 1000000] [--db-dir /tmp/aios_probe]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- #
# 与 src/aios_core/storage/sqlite_store.py::_initialize 完全一致的 schema 形状
# --------------------------------------------------------------------------- #
M0_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO world_meta(key, value) VALUES ('world_revision', '0');

CREATE TABLE IF NOT EXISTS world_commits (
    world_revision INTEGER PRIMARY KEY,
    committed_at TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    session_id TEXT,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS object_revisions (
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    object_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    world_revision INTEGER NOT NULL,
    learned_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(object_id, revision),
    FOREIGN KEY(world_revision) REFERENCES world_commits(world_revision)
);

CREATE INDEX IF NOT EXISTS idx_objects_current_lookup
    ON object_revisions(object_id, world_revision DESC);
CREATE INDEX IF NOT EXISTS idx_objects_type_subject
    ON object_revisions(object_type, subject_id, world_revision DESC);
CREATE INDEX IF NOT EXISTS idx_objects_learned
    ON object_revisions(learned_at);

CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    session_id TEXT,
    operation_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    expected_world_revision INTEGER NOT NULL,
    reason TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    result_world_revision INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    world_revision INTEGER NOT NULL,
    result_json TEXT NOT NULL
);
"""

# 宪法建议新增的派生投影（本探针用于对照实验，产品代码尚未存在）
PROJECTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_posting (
    keyword TEXT NOT NULL,
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    object_type TEXT NOT NULL,
    PRIMARY KEY(keyword, object_id, revision)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_posting_time
    ON keyword_posting(keyword, occurred_at);

CREATE TABLE IF NOT EXISTS time_bucket (
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    object_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    day_bucket TEXT NOT NULL,
    PRIMARY KEY(occurred_at, object_id, revision)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_time_bucket_range
    ON time_bucket(day_bucket, object_type, occurred_at);
"""

DEP_SCHEMA = """
CREATE TABLE IF NOT EXISTS dependency_objects (
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    object_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    world_revision INTEGER NOT NULL,
    learned_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(object_id, revision)
);

CREATE TABLE IF NOT EXISTS dependency_edges (
    dependency_object_id TEXT NOT NULL,
    dependency_revision INTEGER NOT NULL,
    dependent_object_id TEXT NOT NULL,
    dependent_revision INTEGER NOT NULL,
    PRIMARY KEY(dependency_object_id, dependency_revision,
                dependent_object_id, dependent_revision)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_edges_dependent
    ON dependency_edges(dependent_object_id, dependent_revision);
"""

# --------------------------------------------------------------------------- #
# 合成虚拟世界：一年、单用户、宪法第三十三条边缘轻量化后的观测量级
# --------------------------------------------------------------------------- #
TZ = timezone(timedelta(hours=8))
T0 = datetime(2025, 9, 15, 0, 0, 0, tzinfo=TZ)
SPAN_DAYS = 365

KEYWORDS = [
    ("妈妈", 0.055), ("生日", 0.020), ("礼物", 0.012), ("老张", 0.018),
    ("老王", 0.010), ("借钱", 0.006), ("争执", 0.008), ("加班", 0.030),
    ("熬夜", 0.022), ("心悸", 0.004), ("项目", 0.045), ("老板", 0.026),
    ("女朋友", 0.014), ("分手", 0.005), ("健身", 0.016), ("体检", 0.006),
    ("房租", 0.007), ("面试", 0.009), ("出差", 0.011), ("失眠", 0.013),
]
KW_NAMES = [k for k, _ in KEYWORDS]
KW_WEIGHTS = [w for _, w in KEYWORDS]

CHAT_TEMPLATES = [
    "今天{kw}那边又出了点事，晚上再聊",
    "刚跟{kw}通完电话，心里有点堵",
    "下周{kw}的事情得提前安排一下",
    "别提了，{kw}这事折腾我一整天",
    "{kw}说明天见面，我先把材料准备好",
]

TYPE_MIX = [
    ("observation", 0.78),
    ("claim", 0.08),
    ("event", 0.04),
    ("summary", 0.04),
    ("dimension_membership", 0.06),
]


def pick_type(rng: random.Random) -> str:
    return rng.choices([t for t, _ in TYPE_MIX], [w for _, w in TYPE_MIX])[0]


def make_row(rng: random.Random, idx: int, world_revision: int) -> tuple:
    object_type = pick_type(rng)
    day = rng.randrange(SPAN_DAYS)
    occurred = T0 + timedelta(
        days=day,
        hours=rng.randrange(24),
        minutes=rng.randrange(60),
        seconds=rng.randrange(60),
    )
    learned = occurred + timedelta(seconds=rng.randrange(0, 600))
    n_kw = rng.choices([0, 1, 2, 3], [0.45, 0.35, 0.15, 0.05])[0]
    kws: list[str] = []
    if rng.random() < 0.62:
        kws = list(dict.fromkeys(rng.choices(KW_NAMES, KW_WEIGHTS, k=n_kw)))
    text = rng.choice(CHAT_TEMPLATES).format(kw=kws[0] if kws else "生活")
    object_id = f"{object_type[:3]}-{idx:08d}"
    payload = {
        "object_id": object_id,
        "object_type": object_type,
        "subject_id": "U001",
        "revision": 1,
        "occurred_at": occurred.isoformat(),
        "learned_at": learned.isoformat(),
        "recorded_at": learned.isoformat(),
        "source_kind": "chat" if object_type == "observation" else "derived",
        "modality": "text",
        "value": {"text": text, "entities": [f"P{rng.randrange(1, 500):03d}"]},
        "keywords": kws,
        "data_quality": {"snr": round(rng.uniform(0.5, 1.0), 2)},
    }
    return (
        object_id,
        1,
        object_type,
        "U001",
        world_revision,
        learned.isoformat(),
        learned.isoformat(),
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        kws,
        occurred.isoformat(),
    )


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def db_size_mb(path: str) -> float:
    total = os.path.getsize(path)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            total += os.path.getsize(path + suffix)
    return total / (1024 * 1024)


def timeit(fn, *args, **kwargs):
    start = time.perf_counter()
    out = fn(*args, **kwargs)
    return (time.perf_counter() - start) * 1000.0, out


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.data: dict = {}

    def section(self, title: str) -> None:
        line = f"\n=== {title} ==="
        print(line, flush=True)
        self.lines.append(line)

    def row(self, key: str, value: object, note: str = "") -> None:
        line = f"{key:<58} {value!s:<22} {note}"
        print(line, flush=True)
        self.lines.append(line)

    def note(self, text: str) -> None:
        print(text, flush=True)
        self.lines.append(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--edges", type=int, default=1_000_000)
    parser.add_argument("--db-dir", default="/tmp/aios_probe")
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--json-out", default=None,
                        help="可选：把 JSON_SUMMARY 另存为机器可读结果文件")
    args = parser.parse_args()

    shutil.rmtree(args.db_dir, ignore_errors=True)
    os.makedirs(args.db_dir, exist_ok=True)
    db_path = os.path.join(args.db_dir, "world.db")
    dep_path = os.path.join(args.db_dir, "dep.db")

    rep = Report()
    rng = random.Random(args.seed)
    summary: dict = {
        "probe": "aios_v3_as_built_probe",
        "disclaimer": ("As-built structural microbenchmark on the frozen M0-017 schema shape "
                       "(payload_json blob + its 3 indexes). Not an AIOS implementation benchmark, "
                       "not a wearable/edge benchmark, not a cold-cache result, and not an SLO proof. "
                       "Absolute latencies are for a 2-vCPU container host; only orders of magnitude "
                       "and relative ratios should be generalized."),
        "sqlite_version": sqlite3.sqlite_version,
        "python_version": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "rows_target": args.rows,
        "edges_target": args.edges,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    rep.note(
        f"SQLite {sqlite3.sqlite_version} / Python {sys.version.split()[0]} / "
        f"cpu={os.cpu_count()} / target_rows={args.rows:,} / target_edges={args.edges:,}"
    )

    # ------------------------------------------------------------------ P1 -- #
    rep.section("P1 写入吞吐与存储体积（M0-017 冻结 schema，WAL）")
    conn = connect(db_path)
    conn.executescript(M0_SCHEMA)
    conn.executescript(PROJECTION_SCHEMA)
    conn.execute("PRAGMA synchronous = FULL")

    checkpoints = sorted({int(args.rows * f) for f in (0.05, 0.2, 0.5, 1.0)})
    batch = 10_000
    inserted = 0
    world_revision = 0
    write_seconds = 0.0
    keyword_rows: list[tuple] = []
    scale_curve: list[dict] = []
    insert_start = time.perf_counter()
    pending: list[tuple] = []

    for idx in range(args.rows):
        world_revision += 1
        row = make_row(rng, idx, world_revision)
        pending.append(row[:8])
        keyword_rows.append((row[0], row[8], row[9], row[2]))
        if len(pending) >= batch:
            t0 = time.perf_counter()
            # 与生产提交一致：world_commits 必须先于 object_revisions 落库（FK 立即校验）
            conn.executemany(
                "INSERT INTO world_commits(world_revision, committed_at,"
                " operation_id, session_id, reason) VALUES (?,?,?,?,?)",
                [(world_revision - len(pending) + 1 + i, T0.isoformat(),
                  f"op-{world_revision - len(pending) + 1 + i:09d}", None, "probe")
                 for i in range(len(pending))],
            )
            conn.executemany(
                "INSERT INTO object_revisions(object_id, revision, object_type,"
                " subject_id, world_revision, learned_at, recorded_at, payload_json)"
                " VALUES (?,?,?,?,?,?,?,?)",
                pending,
            )
            conn.commit()
            write_seconds += time.perf_counter() - t0
            inserted += len(pending)
            pending.clear()
            if inserted in checkpoints or inserted >= args.rows:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                size_mb = db_size_mb(db_path)
                scale_curve.append(
                    {
                        "rows": inserted,
                        "db_mb": round(size_mb, 1),
                        "bytes_per_row": round(size_mb * 1024 * 1024 / inserted, 1),
                        "write_rows_per_sec": round(inserted / max(write_seconds, 1e-6), 0),
                    }
                )
                rep.row(
                    f"  已写入 {inserted:,} 行",
                    f"{size_mb:,.1f} MB",
                    f"{size_mb * 1024 * 1024 / inserted:,.0f} B/row, "
                    f"{inserted / max(write_seconds, 1e-6):,.0f} rows/s (synchronous=FULL)",
                )
    if pending:
        conn.executemany(
            "INSERT INTO object_revisions(object_id, revision, object_type,"
            " subject_id, world_revision, learned_at, recorded_at, payload_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            pending,
        )
        conn.commit()
        inserted += len(pending)
    summary["p1_scale_curve"] = scale_curve
    summary["p1_total_write_seconds"] = round(write_seconds, 1)
    rep.row("P1 总写入耗时", f"{write_seconds:,.1f} s", f"{inserted:,} 行")

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    rep.row("P1 主表行数（测量基数）",
            f"{conn.execute('SELECT count(*) FROM object_revisions').fetchone()[0]:,}")

    # P1b 单行单提交（= 一个 world_revision，M0-018 语义）fsync 代价对照：
    # 宪法第三十三条的摄入路径会产生大量小 Observation，若每条各自成为一次提交，
    # synchronous=FULL 的 fsync 将成为端侧写入的真实瓶颈。
    rep.section("P1b 单条提交（1 Observation = 1 world_revision）fsync 代价")
    commit_probe: dict = {}
    for mode in ("FULL", "NORMAL"):
        cpath = os.path.join(args.db_dir, f"commit_{mode.lower()}.db")
        cconn = connect(cpath)
        cconn.executescript(M0_SCHEMA)
        cconn.execute(f"PRAGMA synchronous = {mode}")
        rows = [make_row(rng, 900_000 + i, i + 1)[:8] for i in range(2_000)]
        start = time.perf_counter()
        for i, row in enumerate(rows, start=1):
            cconn.execute(
                "INSERT INTO world_commits(world_revision, committed_at,"
                " operation_id, session_id, reason) VALUES (?,?,?,?,?)",
                (i, T0.isoformat(), f"op-c-{i:09d}", None, "probe"))
            cconn.execute(
                "INSERT INTO object_revisions(object_id, revision, object_type,"
                " subject_id, world_revision, learned_at, recorded_at, payload_json)"
                " VALUES (?,?,?,?,?,?,?,?)", row)
            cconn.commit()
        elapsed = time.perf_counter() - start
        cconn.close()
        os.remove(cpath)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(cpath + suffix):
                os.remove(cpath + suffix)
        commit_probe[mode] = {
            "commits": 2_000,
            "seconds": round(elapsed, 2),
            "commits_per_sec": round(2_000 / elapsed, 1),
            "ms_per_commit": round(elapsed / 2_000 * 1000, 2),
        }
        rep.row(f"P1b synchronous={mode}：2000 次单行提交", f"{elapsed:,.2f} s",
                f"{2_000 / elapsed:,.0f} commits/s（{elapsed / 2_000 * 1000:,.2f} ms/提交）")
    summary["p1b_single_commit"] = commit_probe
    conn.execute("PRAGMA synchronous = FULL")

    # ------------------------------------------------------------------ P2 -- #
    rep.section("P2 当前 schema 已建索引可支撑的查询")
    n_rows = conn.execute("SELECT count(*) FROM object_revisions").fetchone()[0]

    sample_ids = [r[0] for r in conn.execute(
        "SELECT object_id FROM object_revisions ORDER BY random() LIMIT 200").fetchall()]

    def point_lookup() -> int:
        total = 0
        for oid in sample_ids:
            total += len(conn.execute(
                "SELECT payload_json FROM object_revisions"
                " WHERE object_id=? ORDER BY world_revision DESC LIMIT 1", (oid,)
            ).fetchall())
        return total

    ms, hits = timeit(point_lookup)
    rep.row("P2 点查 200 次（idx_objects_current_lookup）", f"{ms:,.1f} ms 总",
            f"{ms / 200:,.3f} ms/次, 命中 {hits}")
    summary["p2_point_lookup_ms_per_query"] = round(ms / 200, 3)

    ms, cnt = timeit(lambda: conn.execute(
        "SELECT count(*) FROM object_revisions WHERE object_type='claim' AND subject_id='U001'"
    ).fetchone()[0])
    rep.row("P2 类型+主体计数（idx_objects_type_subject）", f"{ms:,.1f} ms", f"{cnt:,} 行")
    summary["p2_type_subject_count_ms"] = round(ms, 1)

    ms, cnt = timeit(lambda: conn.execute(
        "SELECT count(*) FROM object_revisions WHERE learned_at >= ? AND learned_at < ?",
        ((T0 + timedelta(days=100)).isoformat(), (T0 + timedelta(days=101)).isoformat()),
    ).fetchone()[0])
    rep.row("P2 learned_at 单日范围（idx_objects_learned）", f"{ms:,.1f} ms", f"{cnt:,} 行")
    summary["p2_learned_range_ms"] = round(ms, 1)

    ms, rows = timeit(lambda: conn.execute(
        "SELECT payload_json FROM object_revisions"
        " WHERE object_type='observation' AND subject_id='U001'"
        " ORDER BY world_revision DESC LIMIT 50"
    ).fetchall())
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT payload_json FROM object_revisions"
        " WHERE object_type='observation' AND subject_id='U001'"
        " ORDER BY world_revision DESC LIMIT 50").fetchall()
    rep.row("P2 看板典型查询：最近 50 条观测", f"{ms:,.1f} ms",
            f"{len(rows)} 行；plan={' | '.join(str(r[-1]) for r in plan)}")
    summary["p2_cockpit_recent50_ms"] = round(ms, 1)

    # P2b 单次看盘聚合看板（宪法第八十四条）的真实组装代价：
    # 一次唤醒需要串起 AI 自身切片 + 羁绊模型 + 事件锚点 + 现场观测 + 就绪任务
    rep.section("P2b 单次看盘聚合看板（Cockpit Manifest）组装实测")
    manifest_steps = {
        "第一步 照镜子：AI 自身 identity/growth 切片": (
            "SELECT payload_json FROM object_revisions WHERE object_type='summary'"
            " AND subject_id='U001' ORDER BY world_revision DESC LIMIT 5", ()),
        "第二步 校准羁绊：最近关系类 Claim": (
            "SELECT payload_json FROM object_revisions WHERE object_type='claim'"
            " AND subject_id='U001' ORDER BY world_revision DESC LIMIT 20", ()),
        "第三步 定态度：最近事件锚点": (
            "SELECT payload_json FROM object_revisions WHERE object_type='event'"
            " AND subject_id='U001' ORDER BY world_revision DESC LIMIT 10", ()),
        "第四步 审视现场：最近观测切片": (
            "SELECT payload_json FROM object_revisions WHERE object_type='observation'"
            " AND subject_id='U001' ORDER BY world_revision DESC LIMIT 30", ()),
        "第四步 就绪任务/维度成员挂载": (
            "SELECT payload_json FROM object_revisions"
            " WHERE object_type='dimension_membership' AND subject_id='U001'"
            " ORDER BY world_revision DESC LIMIT 20", ()),
    }
    total_ms = 0.0
    p2b: dict = {}
    for label, (sql, params) in manifest_steps.items():
        ms, rows = timeit(lambda: conn.execute(sql, params).fetchall())
        total_ms += ms
        p2b[label] = round(ms, 2)
        rep.row(f"P2b {label}", f"{ms:,.2f} ms", f"{len(rows)} 行")
    rep.row("P2b 看板组装合计（不含 LLM 首字）", f"{total_ms:,.1f} ms",
            "→ 1 秒首字预算中留给世界存储检索的份额")
    summary["p2b_manifest_assembly"] = {"steps_ms": p2b, "total_ms": round(total_ms, 1)}

    # ------------------------------------------------------------------ P3 -- #
    rep.section("P3 多关键词共现检索（宪法第八十九条）——当前 schema 唯一可行路径：LIKE 全表扫描")
    co_queries = {
        "2kw [妈妈,生日]": ["妈妈", "生日"],
        "3kw [妈妈,生日,礼物]": ["妈妈", "生日", "礼物"],
        "3kw [老张,借钱,争执]": ["老张", "借钱", "争执"],
        "3kw [加班,熬夜,心悸]": ["加班", "熬夜", "心悸"],
    }
    p3: dict = {}
    truth_sets: dict[str, set] = {}
    for label, kws in co_queries.items():
        sql = (
            "SELECT object_id, revision FROM object_revisions WHERE "
            + " AND ".join(["payload_json LIKE ?"] * len(kws))
        )
        params = [f"%{k}%" for k in kws]
        ms, rows = timeit(lambda: conn.execute(sql, params).fetchall())
        truth_sets[label] = {r[0] for r in rows}
        p3[label] = {"ms": round(ms, 1), "hits": len(rows)}
        rep.row(f"P3 {label}", f"{ms:,.1f} ms", f"命中 {len(rows):,} 条 / {n_rows:,} 行")
    summary["p3_like_cooccurrence"] = p3
    summary["p3_scan_throughput_mb_per_sec"] = round(
        db_size_mb(db_path) / (max(p3["3kw [妈妈,生日,礼物]"]["ms"], 1e-6) / 1000.0), 1
    )

    # ------------------------------------------------------------------ P4 -- #
    rep.section("P4 5D 时间滑动条（宪法第八十七条）——occurred_at 在 payload_json 内，无索引")
    p4: dict = {}
    for span_label, days in (("1d", 1), ("1w", 7), ("1m", 30), ("1y", 365)):
        start = (T0 + timedelta(days=120)).isoformat()
        end = (T0 + timedelta(days=120 + days)).isoformat()
        sql = (
            "SELECT count(*), avg(length(payload_json)) FROM object_revisions"
            " WHERE json_extract(payload_json, '$.occurred_at') >= ?"
            " AND json_extract(payload_json, '$.occurred_at') < ?"
        )
        ms, row = timeit(lambda: conn.execute(sql, (start, end)).fetchone())
        p4[span_label] = {"ms": round(ms, 1), "hits": row[0]}
        rep.row(f"P4 时间窗口 {span_label}（json_extract 全表扫描）", f"{ms:,.1f} ms",
                f"命中 {row[0]:,} 条")
    # 对比：learned_at 有索引
    ms, row = timeit(lambda: conn.execute(
        "SELECT count(*) FROM object_revisions WHERE learned_at >= ? AND learned_at < ?",
        ((T0 + timedelta(days=120)).isoformat(), (T0 + timedelta(days=121)).isoformat()),
    ).fetchone())
    p4["learned_at_1d_indexed"] = {"ms": round(ms, 1), "hits": row[0]}
    rep.row("P4 对照：learned_at 1d（有索引）", f"{ms:,.1f} ms", f"命中 {row[0]:,} 条")
    summary["p4_time_slider"] = p4
    db_mb_before_projections = db_size_mb(db_path)
    summary["p4_db_mb_before_projections"] = round(db_mb_before_projections, 1)

    # ------------------------------------------------------------------ P5 -- #
    rep.section("P5 FTS5 中文关键词可用性实测（unicode61 / trigram / 预分词列）")
    sample = conn.execute(
        "SELECT object_id, revision, payload_json FROM object_revisions LIMIT 200000"
    ).fetchall()
    p5: dict = {"sample_rows": len(sample)}

    fts_path = os.path.join(args.db_dir, "fts.db")
    fts = connect(fts_path)
    fts.execute("DROP TABLE IF EXISTS fts_unicode")
    fts.execute("CREATE VIRTUAL TABLE fts_unicode USING fts5("
                "object_id UNINDEXED, body, tokenize='unicode61')")
    ms, _ = timeit(lambda: fts.executemany(
        "INSERT INTO fts_unicode(object_id, body) VALUES (?,?)",
        [(r[0], json.loads(r[2])["value"]["text"]) for r in sample],
    ))
    fts.commit()
    try:
        u_hits = fts.execute(
            "SELECT count(*) FROM fts_unicode WHERE body MATCH '妈妈'").fetchone()[0]
        u_err = None
    except sqlite3.OperationalError as exc:  # pragma: no cover
        u_hits, u_err = -1, str(exc)
    p5["unicode61"] = {"build_ms_200k": round(ms, 1), "match_妈妈_hits": u_hits, "error": u_err}
    rep.row(f"P5 unicode61 构建（{len(sample):,} 条文本）", f"{ms:,.1f} ms", "")
    rep.row("P5 unicode61 MATCH '妈妈' 命中", f"{u_hits}",
            "→ 中文整串被当作单一 token，子串关键词检索失效" if u_hits == 0 else "")

    fts.execute("DROP TABLE IF EXISTS fts_trigram")
    fts.execute("CREATE VIRTUAL TABLE fts_trigram USING fts5("
                "object_id UNINDEXED, body, tokenize='trigram')")
    ms, _ = timeit(lambda: fts.executemany(
        "INSERT INTO fts_trigram(object_id, body) VALUES (?,?)",
        [(r[0], json.loads(r[2])["value"]["text"]) for r in sample],
    ))
    fts.commit()
    fts.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    tri_size = db_size_mb(fts_path)
    three_char_hits, two_char_hits, two_char_err = None, None, None
    try:
        three_char_hits = fts.execute(
            "SELECT count(*) FROM fts_trigram WHERE body MATCH '女朋友'").fetchone()[0]
    except sqlite3.OperationalError as exc:
        two_char_err = f"3char:{exc}"
    try:
        two_char_hits = fts.execute(
            "SELECT count(*) FROM fts_trigram WHERE body MATCH '妈妈'").fetchone()[0]
    except sqlite3.OperationalError as exc:
        two_char_err = str(exc)
    p5["trigram"] = {
        "build_ms_200k": round(ms, 1),
        "fts_db_mb_unicode61_plus_trigram": round(tri_size, 1),
        "match_3char_女朋友_hits": three_char_hits,
        "match_2char_妈妈_hits": two_char_hits,
        "match_2char_error": two_char_err,
    }
    rep.row(f"P5 trigram 构建（{len(sample):,} 条文本）", f"{ms:,.1f} ms",
            f"fts.db 体积（unicode61+trigram，{len(sample):,} 条短文本）→ {tri_size:,.1f} MB")
    rep.row("P5 trigram MATCH '女朋友'（3 字）命中", f"{three_char_hits}")
    rep.row("P5 trigram MATCH '妈妈'（2 字）命中", f"{two_char_hits}",
            two_char_err or "→ 宪法第八十九条的示例关键词多为 2 字，trigram 不可用")

    fts.execute("DROP TABLE IF EXISTS fts_segmented")
    fts.execute("CREATE VIRTUAL TABLE fts_segmented USING fts5("
                "object_id UNINDEXED, body, tokenize='unicode61')")
    ms, _ = timeit(lambda: fts.executemany(
        "INSERT INTO fts_segmented(object_id, body) VALUES (?,?)",
        [(r[0], " ".join(json.loads(r[2])["keywords"]) + " "
                + json.loads(r[2])["value"]["text"]) for r in sample],
    ))
    fts.commit()
    fts.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    p5["fts_db_mb_final"] = round(db_size_mb(fts_path), 1)
    seg_ms, seg_rows = timeit(lambda: fts.execute(
        "SELECT object_id FROM fts_segmented WHERE body MATCH '妈妈 AND 生日 AND 礼物'"
    ).fetchall())
    p5["segmented"] = {
        "build_ms_200k": round(ms, 1),
        "match_3kw_ms": round(seg_ms, 2),
        "match_3kw_hits": len(seg_rows),
    }
    rep.row(f"P5 预分词列 FTS5 构建（{len(sample):,} 条）", f"{ms:,.1f} ms", "")
    rep.row("P5 预分词列 MATCH '妈妈 AND 生日 AND 礼物'", f"{seg_ms:,.2f} ms",
            f"命中 {len(seg_rows):,} 条")
    summary["p5_fts"] = p5
    fts.close()

    # ------------------------------------------------------------------ P6 -- #
    rep.section("P6 建议方案：规范化倒排索引 keyword_posting（派生投影，可全量重建）")
    posting_rows = []
    for object_id, kws, occurred, object_type in keyword_rows:
        for kw in kws:
            posting_rows.append((kw, object_id, 1, occurred, object_type))
    ms, _ = timeit(lambda: conn.executemany(
        "INSERT OR IGNORE INTO keyword_posting(keyword, object_id, revision,"
        " occurred_at, object_type) VALUES (?,?,?,?,?)",
        posting_rows,
    ))
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    posting_count = conn.execute("SELECT count(*) FROM keyword_posting").fetchone()[0]
    rep.row("P6 倒排索引构建（全量一次性）", f"{ms / 1000:,.1f} s",
            f"{posting_count:,} postings")
    summary["p6_posting_build_sec"] = round(ms / 1000, 1)
    summary["p6_posting_rows"] = posting_count

    p6: dict = {}
    for label, kws in co_queries.items():
        sql = (
            "SELECT object_id FROM keyword_posting WHERE keyword IN ("
            + ",".join("?" * len(kws))
            + ") GROUP BY object_id HAVING count(DISTINCT keyword) = ?"
        )
        q_ms, rows = timeit(lambda: conn.execute(sql, (*kws, len(kws))).fetchall())
        fast = {r[0] for r in rows}
        slow = truth_sets[label]
        p6[label] = {
            "ms": round(q_ms, 2),
            "hits": len(fast),
            "identical_to_like_scan": fast == slow,
            "missing": len(slow - fast),
            "extra": len(fast - slow),
        }
        rep.row(f"P6 {label}", f"{q_ms:,.2f} ms",
                f"命中 {len(fast):,}；与 LIKE 全表扫描结果一致={fast == slow}"
                f"（LIKE 慢路径 {p3[label]['ms']:,.0f} ms → 提速 "
                f"{p3[label]['ms'] / max(q_ms, 1e-6):,.0f}×）")
    summary["p6_posting_cooccurrence"] = p6

    # P6b 同一倒排索引的正确查询形状：按 posting 基数升序驱动 + EXISTS 探针
    # （宪法第八十九条宣称"毫秒级"，GROUP BY 全量聚合达不到，交集必须由最稀有关键词驱动）
    rep.section("P6b co_search 查询形状对照：GROUP BY 聚合 vs 最稀有关键词驱动 EXISTS")
    p6b: dict = {}
    for label, kws in co_queries.items():
        counts = {
            k: conn.execute(
                "SELECT count(*) FROM keyword_posting WHERE keyword=?", (k,)
            ).fetchone()[0]
            for k in kws
        }
        ordered = sorted(kws, key=lambda k: counts[k])
        sql = "SELECT p.object_id FROM keyword_posting p WHERE p.keyword = ?"
        for _ in ordered[1:]:
            sql += (" AND EXISTS (SELECT 1 FROM keyword_posting q WHERE q.keyword = ?"
                    " AND q.object_id = p.object_id AND q.revision = p.revision)")
        q_ms, rows = timeit(lambda: conn.execute(sql, (ordered[0], *ordered[1:])).fetchall())
        fast = {r[0] for r in rows}
        p6b[label] = {
            "ms": round(q_ms, 2),
            "hits": len(fast),
            "identical_to_like_scan": fast == truth_sets[label],
            "posting_cardinality": counts,
            "driver_keyword": ordered[0],
        }
        rep.row(f"P6b {label}", f"{q_ms:,.2f} ms",
                f"命中 {len(fast):,}；驱动词={ordered[0]}({counts[ordered[0]]:,} postings)"
                f"；结果与 LIKE 全表扫描一致={fast == truth_sets[label]}"
                f"（GROUP BY 形状 {p6[label]['ms']:,.0f} ms → 再提速 "
                f"{p6[label]['ms'] / max(q_ms, 1e-6):,.0f}×）")
    summary["p6b_rarest_first_cooccurrence"] = p6b

    # time_bucket 投影：5D 滑动条
    bucket_rows = [
        (oid, 1, otype, occ, occ[:10])
        for oid, kws, occ, otype in keyword_rows
    ]
    ms, _ = timeit(lambda: conn.executemany(
        "INSERT OR IGNORE INTO time_bucket(object_id, revision, object_type,"
        " occurred_at, day_bucket) VALUES (?,?,?,?,?)",
        bucket_rows,
    ))
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    summary["p6_time_bucket_build_sec"] = round(ms / 1000, 1)
    rep.row("P6 time_bucket 投影构建（全量一次性）", f"{ms / 1000:,.1f} s", "")

    p6t: dict = {}
    for span_label, days in (("1d", 1), ("1w", 7), ("1m", 30), ("1y", 365)):
        start = (T0 + timedelta(days=120)).isoformat()
        end = (T0 + timedelta(days=120 + days)).isoformat()
        buckets = [
            (T0 + timedelta(days=120 + i)).date().isoformat() for i in range(days)
        ]
        sql = (
            "SELECT count(*) FROM time_bucket WHERE day_bucket IN ("
            + ",".join("?" * len(buckets)) + ") AND occurred_at >= ? AND occurred_at < ?"
        )
        q_ms, row = timeit(lambda: conn.execute(sql, (*buckets, start, end)).fetchone())
        p6t[span_label] = {"ms": round(q_ms, 2), "hits": row[0]}
        rep.row(f"P6 5D 滑动条 {span_label}（time_bucket 投影）", f"{q_ms:,.2f} ms",
                f"命中 {row[0]:,}（json_extract 慢路径 {p4[span_label]['ms']:,.0f} ms → 提速 "
                f"{p4[span_label]['ms'] / max(q_ms, 1e-6):,.0f}×）")
    summary["p6_time_slider_projection"] = p6t
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    summary["p6_db_mb_after_projections"] = round(db_size_mb(db_path), 1)
    rep.row("P6 加投影后 DB 总体积", f"{db_size_mb(db_path):,.1f} MB",
            f"投影前 {db_mb_before_projections:,.1f} MB → 投影净增 "
            f"{db_size_mb(db_path) - db_mb_before_projections:,.1f} MB "
            f"(+{(db_size_mb(db_path) / max(db_mb_before_projections, 1e-6) - 1) * 100:,.0f}%)")
    conn.close()

    # ------------------------------------------------------------------ P7 -- #
    rep.section("P7 依赖回溯传播（宪法第四十九条 vs 第九十三条）——雪崩实测")
    dep_conn = connect(dep_path)
    dep_conn.executescript(DEP_SCHEMA)
    E = args.edges
    rng2 = random.Random(args.seed + 1)

    # 拓扑：500 实体；1 个枢纽实体（"老张"）被 4000 条 Claim 引用；
    # Claim → Event → DaySummary → WeekSummary → MonthSummary → DerivedDim → LifeChapter
    hub = "ent-hub-laozhang"
    hub_stride = max(1, E // 20000)  # 枢纽实体（合伙人级）全年被 2 万条 Claim 引用
    edges: list[tuple] = []
    claim_ids = []
    for i in range(E):
        if i % hub_stride == 0:
            dep_id, dep_rev = hub, 1
        else:
            dep_id, dep_rev = f"ent-{rng2.randrange(500):04d}", 1
        dependent = f"claim-{i:08d}"
        claim_ids.append(dependent)
        edges.append((dep_id, dep_rev, dependent, 1))
    # 二级：每 5 条 claim → 1 个 event
    events = []
    for i in range(0, len(claim_ids), 5):
        ev = f"event-{i // 5:07d}"
        events.append(ev)
        for c in claim_ids[i:i + 5]:
            edges.append((c, 1, ev, 1))
    # 三级：每 20 个 event → 1 个日总结
    day_sums = []
    for i in range(0, len(events), 20):
        ds = f"sum-day-{i // 20:06d}"
        day_sums.append(ds)
        for e in events[i:i + 20]:
            edges.append((e, 1, ds, 1))
    # 四级：每 7 个日总结 → 周总结
    week_sums = []
    for i in range(0, len(day_sums), 7):
        ws = f"sum-week-{i // 7:06d}"
        week_sums.append(ws)
        for d in day_sums[i:i + 7]:
            edges.append((d, 1, ws, 1))
    # 五级：每 4 个周总结 → 月总结
    month_sums = []
    for i in range(0, len(week_sums), 4):
        msx = f"sum-month-{i // 4:06d}"
        month_sums.append(msx)
        for w in week_sums[i:i + 4]:
            edges.append((w, 1, msx, 1))
    # 六级：每 12 个月总结 → 派生维度
    dims = []
    for i in range(0, len(month_sums), 12):
        dim = f"dim-derived-{i // 12:05d}"
        dims.append(dim)
        for m in month_sums[i:i + 12]:
            edges.append((m, 1, dim, 1))
    # 七级：每 6 个派生维度 → 人生章节
    chapters = []
    for i in range(0, len(dims), 6):
        ch = f"chapter-{i // 6:04d}"
        chapters.append(ch)
        for d in dims[i:i + 6]:
            edges.append((d, 1, ch, 1))

    t0 = time.perf_counter()
    dep_conn.executemany(
        "INSERT OR IGNORE INTO dependency_edges VALUES (?,?,?,?)", edges)
    dep_conn.commit()
    edge_build_s = time.perf_counter() - t0
    total_edges = dep_conn.execute("SELECT count(*) FROM dependency_edges").fetchone()[0]
    rep.row("P7 规范化边表构建", f"{edge_build_s:,.1f} s", f"{total_edges:,} 条边")
    rep.row("P7 拓扑规模", "",
            f"claims={len(claim_ids):,} events={len(events):,} day={len(day_sums):,} "
            f"week={len(week_sums):,} month={len(month_sums):,} dim={len(dims):,} "
            f"chapter={len(chapters):,}")

    # M0 现状：Dependency 是 WorldObject，反向扫描需要把全部依赖对象读进内存并 json.loads
    t0 = time.perf_counter()
    chunk: list[tuple] = []
    for i, e in enumerate(edges):
        chunk.append((
            f"dep-{i:08d}", 1, "dependency", "U001", i + 1,
            T0.isoformat(), T0.isoformat(),
            json.dumps({
                "object_id": f"dep-{i:08d}",
                "object_type": "dependency",
                "dependent_ref": {"object_id": e[2], "revision": e[3]},
                "dependency_ref": {"object_id": e[0], "revision": e[1]},
                "dependency_kind": "evidence",
            }, ensure_ascii=False, separators=(",", ":")),
        ))
        if len(chunk) >= 20_000:
            dep_conn.executemany(
                "INSERT OR REPLACE INTO dependency_objects VALUES (?,?,?,?,?,?,?,?)", chunk)
            chunk.clear()
    if chunk:
        dep_conn.executemany(
            "INSERT OR REPLACE INTO dependency_objects VALUES (?,?,?,?,?,?,?,?)", chunk)
        chunk.clear()
    dep_conn.commit()
    dep_obj_build_s = time.perf_counter() - t0
    rep.row("P7 同规模 Dependency 作为 WorldObject 落库", f"{dep_obj_build_s:,.1f} s",
            f"{total_edges:,} 行 payload_json")

    # M0 路径：全表读 + json.loads + 内存 BFS（collect_impacted_dependents 的输入前提）
    def m0_style_reverse_scan(target_id: str, cap: int | None = None) -> tuple[int, float]:
        start = time.perf_counter()
        reverse: dict[str, list[str]] = {}
        cur = dep_conn.execute(
            "SELECT payload_json FROM dependency_objects")
        parsed = 0
        while True:
            chunk = cur.fetchmany(20_000)
            if not chunk:
                break
            for (payload,) in chunk:
                doc = json.loads(payload)
                parsed += 1
                reverse.setdefault(
                    doc["dependency_ref"]["object_id"], []
                ).append(doc["dependent_ref"]["object_id"])
        # BFS
        seen = {target_id}
        frontier = [target_id]
        impacted = 0
        depth = 0
        while frontier:
            depth += 1
            nxt: list[str] = []
            for node in frontier:
                for dep in reverse.get(node, ()):
                    if dep in seen:
                        continue
                    seen.add(dep)
                    impacted += 1
                    nxt.append(dep)
                    if cap is not None and impacted >= cap:
                        return impacted, time.perf_counter() - start
            frontier = nxt
        return impacted, time.perf_counter() - start

    ms_imp, sec = None, None
    t0 = time.perf_counter()
    m0_impacted, m0_sec = m0_style_reverse_scan(hub)
    m0_total_ms = (time.perf_counter() - t0) * 1000
    rep.row("P7 M0 路径：全量依赖读入+json.loads+内存 BFS（枢纽实体）",
            f"{m0_total_ms / 1000:,.1f} s",
            f"解析 {total_edges:,} 条边，传递影响对象 {m0_impacted:,} 个")

    # 建议路径：规范化边表 + 反向索引 + 预算上限（深度/数量）
    def indexed_reverse(target_id: str, max_nodes: int, max_depth: int) -> tuple[int, int, float]:
        start = time.perf_counter()
        seen = {target_id}
        frontier = [target_id]
        impacted = 0
        depth = 0
        while frontier and depth < max_depth and impacted < max_nodes:
            depth += 1
            nxt = []
            for offset in range(0, len(frontier), 500):
                batch_frontier = frontier[offset:offset + 500]
                placeholders = ",".join("?" * len(batch_frontier))
                rows = dep_conn.execute(
                    f"SELECT DISTINCT dependent_object_id FROM dependency_edges"
                    f" WHERE dependency_object_id IN ({placeholders})", batch_frontier
                ).fetchall()
                for (node,) in rows:
                    if node in seen:
                        continue
                    seen.add(node)
                    impacted += 1
                    nxt.append(node)
                    if impacted >= max_nodes:
                        break
                if impacted >= max_nodes:
                    break
            frontier = nxt
        return impacted, depth, time.perf_counter() - start

    idx_unbounded_imp, idx_unbounded_depth, idx_unbounded_s = indexed_reverse(
        hub, max_nodes=10_000_000, max_depth=64)
    rep.row("P7 索引路径（无预算上限）：传递影响对象",
            f"{idx_unbounded_s * 1000:,.1f} ms",
            f"{idx_unbounded_imp:,} 个 / 深度 {idx_unbounded_depth}"
            f" → 与 M0 路径同为 {m0_impacted:,}，雪崩规模不变")
    idx_cap_imp, idx_cap_depth, idx_cap_s = indexed_reverse(hub, max_nodes=500, max_depth=2)
    rep.row("P7 索引路径（预算 500 节点 / 深度 2）",
            f"{idx_cap_s * 1000:,.2f} ms",
            f"{idx_cap_imp:,} 个 / 深度 {idx_cap_depth} → 可预测、可入队懒复核")
    lazy_ms, lazy_row = timeit(lambda: dep_conn.execute(
        "SELECT count(*) FROM dependency_edges WHERE dependency_object_id=?", (hub,)
    ).fetchone())
    rep.row("P7 懒传播（只标记直接依赖者，宪法第九十三条第 3 款）",
            f"{lazy_ms:,.2f} ms", f"{lazy_row[0]:,} 个直接依赖者")

    normal_entity = "ent-0042"
    n_imp, n_depth, n_s = indexed_reverse(normal_entity, 10_000_000, 64)
    rep.row("P7 对照：普通实体（非枢纽）传递影响", f"{n_s * 1000:,.2f} ms",
            f"{n_imp:,} 个 / 深度 {n_depth}")

    recheck_tokens = m0_impacted * 300  # 每个受影响对象保守 300 tokens 复核上下文
    rep.row("P7 单次枢纽实体修正的下游复核 Token 代价",
            f"{recheck_tokens / 1e6:,.2f} M tokens",
            f"{m0_impacted:,} 个受影响对象 × 300 tokens/次（不含重算输出）")
    rep.row("P7 普通实体修正的下游复核 Token 代价（地板值）",
            f"{n_imp * 300 / 1e6:,.2f} M tokens", f"{n_imp:,} 个受影响对象 × 300 tokens")

    summary["p7"] = {
        "recheck_tokens_single_hub_correction": recheck_tokens,
        "recheck_tokens_normal_entity_correction": n_imp * 300,
        "edges": total_edges,
        "m0_style_full_scan_ms": round(m0_total_ms, 1),
        "m0_style_impacted_nodes": m0_impacted,
        "indexed_unbounded_ms": round(idx_unbounded_s * 1000, 1),
        "indexed_unbounded_impacted_nodes": idx_unbounded_imp,
        "indexed_budgeted_500_depth2_ms": round(idx_cap_s * 1000, 2),
        "lazy_direct_dependents_ms": round(lazy_ms, 2),
        "lazy_direct_dependents": lazy_row[0],
        "normal_entity_impacted": n_imp,
        "avalanche_ratio_hub_vs_normal": (
            round(m0_impacted / max(n_imp, 1), 1)
        ),
        "dep_db_mb": round(db_size_mb(dep_path), 1),
    }
    dep_conn.close()

    # ------------------------------------------------------------------ P8 -- #
    rep.section("P8 由实测外推的一年期资源账（宪法第三十三条边缘轻量化前提下）")
    bytes_per_row = scale_curve[-1]["bytes_per_row"]
    obs_per_day = {
        "对话/转写切片": 220,
        "心率压缩点+异常波形": 60,
        "IMU 宏观运动状态": 120,
        "GPS/位置语义点": 240,
        "图像语义化文本": 40,
        "App/日历/消息摄入": 150,
    }
    daily_obs = sum(obs_per_day.values())
    derived_per_day = 260  # claim / event / summary / membership / dependency 派生层
    daily_rows = daily_obs + derived_per_day
    year_rows = daily_rows * 365
    year_mb = year_rows * bytes_per_row / (1024 * 1024)
    for k, v in obs_per_day.items():
        rep.row(f"P8 每日观测：{k}", f"{v} 条/日", "")
    rep.row("P8 每日总行数（观测 + 派生认知层）", f"{daily_rows:,} 行/日", "")
    rep.row("P8 一年行数外推", f"{year_rows:,} 行/年",
            f"约 {year_mb:,.0f} MB（{bytes_per_row:,.0f} B/行，含 3 个现有索引）")
    proj_pct = (summary["p6_db_mb_after_projections"]
                / max(db_mb_before_projections, 1e-6) - 1) * 100
    rep.row("P8 建议派生投影（倒排+时间桶）净增存储", f"+{proj_pct:,.0f}%",
            f"实测 {db_mb_before_projections:,.1f} MB → "
            f"{summary['p6_db_mb_after_projections']:,.1f} MB；"
            f"一年外推 {year_mb * (1 + proj_pct / 100):,.0f} MB")
    summary["p8"] = {
        "bytes_per_row": bytes_per_row,
        "daily_observations": daily_obs,
        "daily_rows": daily_rows,
        "year_rows": year_rows,
        "year_mb_existing_schema": round(year_mb, 0),
        "projection_overhead_pct": round(proj_pct, 1),
        "year_mb_with_projections": round(year_mb * (1 + proj_pct / 100), 0),
        "obs_per_day_breakdown": obs_per_day,
    }

    rep.section("P9 一年期 LLM Token 账（确定性算术模型，不调用任何模型）")
    # 假设全部显式列出，便于总工按真实数据替换
    tok_per_obs_slice = 40        # 一条边缘轻量化后的观测切片（含时间/实体/原话短句）
    tok_per_summary_in = 300      # 上一层总结作为下一层输入的 token 数
    tok_manifest = 1200           # 单次看盘看板（四步序切片 + Wake Reason + 就绪任务）
    tok_recall = 800              # 主动联想召回注入的历史切片
    tok_window = 1500             # 前台活跃滑动窗口（宪法第八十五条）
    tok_out_short = 60            # 1~3 句话输出（宪法第十四条之一）
    tok_out_reflect = 600         # 复盘/自省输出

    daily_obs = summary["p8"]["daily_observations"]
    dims_active = 17              # 12 用户世界种子维度 + 5 AI 世界种子维度
    dims_derived = 5              # 保守估计的活跃派生维度
    dims_total = dims_active + dims_derived

    daily_cleanup_in = daily_obs * tok_per_obs_slice
    daily_cleanup_out = tok_out_reflect * 3

    pyramid_day_in = dims_total * 365 * (daily_obs / max(dims_total, 1) * tok_per_obs_slice)
    pyramid_week_in = dims_total * 52 * 7 * tok_per_summary_in
    pyramid_month_in = dims_total * 12 * 5 * tok_per_summary_in
    pyramid_out = (dims_total * (365 + 52 + 12)) * tok_out_reflect

    heartbeat_wakes = 6 * 365
    heartbeat_in = heartbeat_wakes * (tok_manifest + tok_out_short)

    conv_turns = 40 * 365
    conv_in = conv_turns * (tok_window + tok_recall + tok_manifest * 0.3)
    conv_out = conv_turns * tok_out_short

    items = [
        ("每日大模型复盘清洗（宪法第三十三条第 5 款）",
         daily_cleanup_in * 365, daily_cleanup_out * 365),
        ("多尺度总结金字塔 日/周/月（第二十八条，%d 个活跃维度）" % dims_total,
         pyramid_day_in + pyramid_week_in + pyramid_month_in, pyramid_out),
        ("长平稳心跳唤醒 6 次/日（第八十条）", heartbeat_in, heartbeat_wakes * tok_out_short),
        ("真人对话 40 轮/日（第八十五条三级流水线）", conv_in, conv_out),
    ]
    total_in = sum(i for _, i, _ in items)
    total_out = sum(o for _, _, o in items)
    for label, tin, tout in items:
        rep.row(f"P9 {label}", f"{tin / 1e6:,.2f} M in / {tout / 1e6:,.2f} M out",
                f"占输入 {tin / max(total_in, 1) * 100:,.1f}%")
    rep.row("P9 单用户单年 Token 合计",
            f"{total_in / 1e6:,.1f} M in / {total_out / 1e6:,.1f} M out", "")
    for price_in, price_out, name in ((3.0, 15.0, "中端云模型 $3/$15 每百万 token"),
                                      (0.4, 1.6, "低价批量模型 $0.4/$1.6 每百万 token")):
        cost = total_in / 1e6 * price_in + total_out / 1e6 * price_out
        rep.row(f"P9 年成本估算（{name}）", f"${cost:,.0f}/用户/年",
                f"≈ ${cost / 12:,.1f}/月")
    summary["p9_token_budget"] = {
        "assumptions": {
            "tok_per_obs_slice": tok_per_obs_slice,
            "tok_per_summary_in": tok_per_summary_in,
            "tok_manifest": tok_manifest,
            "tok_recall": tok_recall,
            "tok_window": tok_window,
            "dims_total": dims_total,
            "daily_observations": daily_obs,
            "heartbeat_wakes_per_day": 6,
            "conv_turns_per_day": 40,
        },
        "annual_input_tokens": int(total_in),
        "annual_output_tokens": int(total_out),
        "breakdown_input_tokens": {label: int(tin) for label, tin, _ in items},
        "breakdown_output_tokens": {label: int(tout) for label, _, tout in items},
        "annual_cost_usd_mid_tier": round(total_in / 1e6 * 3.0 + total_out / 1e6 * 15.0, 0),
        "annual_cost_usd_batch_tier": round(total_in / 1e6 * 0.4 + total_out / 1e6 * 1.6, 0),
    }

    rep.section("JSON_SUMMARY")
    payload = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    print("JSON_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    rep.lines.append("JSON_SUMMARY " + json.dumps(summary, ensure_ascii=False))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        print(f"JSON_OUT {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
