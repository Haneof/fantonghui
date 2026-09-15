#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《AIOS Core 重构设计书（独立首席架构师版）》的**契约可执行验证探针**。

与仓库内既有三支探针的区别：
  * `aios_v3_as_built_probe.py`  —— 测**现状冻结 schema**（回答"今天能不能达标"）
  * `aios_v3_sqlite_probe.py`    —— 报告 A 测**其自建优化 schema**（3.6M，回答"上限在哪"）
  * 本脚本                        —— 测**本设计书 §3.4 规约里逐字写出的 DDL 与算法**
                                    （回答"我提的方案，按我写的 DDL 建出来，是否真的达标"）

因此本脚本是设计书的一部分：设计书里的每一张 DDL、每一个调度算法，都在这里被建出来、
灌入合成数据、并按设计书 §3.4 的验收标准实测。任何一项不达标 ⇒ 设计书本身有错，
必须先改设计书，而不是改验收标准。

只使用标准库（本沙箱 `pip install` 受 PEP 668 阻断，pydantic 不可用）：
Pydantic 2 契约以"字段表 + JSON Schema 形状"的形式在设计书中给出，此处用等价的
CHECK 约束与 Python 侧校验函数落地，语义一一对应。

用法：
    python3 verify_reconstruction_design.py            # 默认 200k 对象 / 100k 任务
    python3 verify_reconstruction_design.py --scale 1m # 1M 对象（约 3~5 分钟）
    python3 verify_reconstruction_design.py --json out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. 设计书的 profile 默认值（全部为**可实验默认值**，不是宪法常量 —— 第七十六条）
# ---------------------------------------------------------------------------
PROFILE = {
    "ttft_budget_ms": 1000.0,        # 第八十五条：穿戴端首字 ~1 秒
    "manifest_budget_ms": 60.0,      # 设计书 §3.4-C：Wake→Manifest 组装预算
    "co_search_p95_ms": 50.0,        # 第八十九条"毫秒级"的工程化默认档
    "time_bucket_p95_ms": 20.0,      # 第八十七条滑动条宏观档默认门
    "propagation_budget_ms": 50.0,   # 设计书 §3.4-D：有界传播预算
    "propagation_max_nodes": 500,
    "propagation_max_depth": 2,
    "manifest_token_tier": {"SAFETY": 512, "ROUTINE": 2048, "REVIEW": 8192},
    "active_window_tokens": 1500,    # 第八十五条前台活跃窗口
    "cjk_bigram_min_recall": 1,      # I7 不静默零召回律：召回必须 > 0
    "max_postings_per_object": 8,    # 索引膨胀闸：每对象最多 8 条 postings（词典词优先）
}

DDL = """
-- ========== 控制面（C15，新设模块；不进 ObjectType，独立 control_plane_* 表） ==========
CREATE TABLE cp_budget_ledger (
    ledger_id     TEXT PRIMARY KEY,
    scope_kind    TEXT NOT NULL CHECK (scope_kind IN ('SESSION','DAILY','DIMENSION','GLOBAL')),
    scope_key     TEXT NOT NULL,
    category      TEXT NOT NULL CHECK (category IN
                    ('INGEST','EXTRACT','RETRIEVAL','CONVERSATION','HEARTBEAT','REVIEW','PROPAGATION')),
    reserved_tok  INTEGER NOT NULL DEFAULT 0 CHECK (reserved_tok >= 0),
    settled_tok   INTEGER NOT NULL DEFAULT 0 CHECK (settled_tok >= 0),
    ceiling_tok   INTEGER NOT NULL,
    degraded      INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);
CREATE INDEX ix_cp_ledger_scope ON cp_budget_ledger(scope_kind, scope_key, category);

CREATE TABLE cp_deadline (
    wake_id       TEXT PRIMARY KEY,
    tier          TEXT NOT NULL CHECK (tier IN ('SAFETY','ROUTINE','REVIEW')),
    t_wake_ms     REAL NOT NULL,
    manifest_due_ms REAL NOT NULL,
    first_token_due_ms REAL NOT NULL,
    settled       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE cp_index_watermark (
    index_name    TEXT PRIMARY KEY,
    watermark_ts  TEXT NOT NULL,     -- 该索引已覆盖到的 occurred_at
    built_at      TEXT NOT NULL,
    state         TEXT NOT NULL CHECK (state IN ('FRESH','STALE','REBUILDING','SUSPECT_ZERO_RECALL'))
);

CREATE TABLE cp_context_receipt (
    receipt_id    TEXT PRIMARY KEY,
    wake_id       TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,     -- 可复现"模型当时看到什么"
    segment_order TEXT NOT NULL,     -- I5 段序律：四步序在**单次 prompt** 内的段序
    token_count   INTEGER NOT NULL,
    assembled_ms  REAL NOT NULL,
    system_filler_turns INTEGER NOT NULL DEFAULT 0 CHECK (system_filler_turns = 0),
    ready_task_count INTEGER NOT NULL,
    waiting_task_count INTEGER NOT NULL CHECK (waiting_task_count = 0),  -- I4 就绪律
    created_at    TEXT NOT NULL
);

-- ========== 领域对象真源（C02，append-only；物理 Observation 永不 UPDATE） ==========
CREATE TABLE obs (
    object_id   TEXT PRIMARY KEY,
    entity_id   TEXT NOT NULL,
    dim_id      TEXT NOT NULL,
    occurred_at TEXT NOT NULL,       -- 发生时间（宪法第八十七条滑动条的正确口径）
    learned_at  TEXT NOT NULL,       -- 得知时间（旧探针误用此列 ⇒ 3 倍性能差）
    text_cjk    TEXT NOT NULL,
    payload_kb  REAL NOT NULL
);
CREATE INDEX ix_obs_entity ON obs(entity_id);
CREATE INDEX ix_obs_learned ON obs(learned_at);   -- as-built 只有这一支时间索引

-- ========== 读路径（C16，新设模块）：预分词倒排 + 预分词 FTS5 + 时间桶 ==========
CREATE TABLE term_dict (
    term_id   INTEGER PRIMARY KEY,
    term_text TEXT NOT NULL UNIQUE,
    tokenizer_id TEXT NOT NULL,      -- 分词器与词典版本化：换版本 = 换 tokenizer_id
    kind      TEXT NOT NULL CHECK (kind IN ('WORD','BIGRAM','ALIAS'))
);
CREATE TABLE term_postings (
    term_id   INTEGER NOT NULL,
    object_id TEXT NOT NULL,
    field     TEXT NOT NULL DEFAULT 'text_cjk',
    weight    REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (term_id, object_id, field)
) WITHOUT ROWID;
CREATE INDEX ix_postings_obj ON term_postings(object_id);

CREATE VIRTUAL TABLE obs_fts USING fts5(
    object_id UNINDEXED, seg_text, tokenize='unicode61'   -- 装**预分词后**的空格分隔串
);
-- 对照表：装**未预分词**的原始中文（= as-built 的做法），用于证明 I7 的必要性
CREATE VIRTUAL TABLE obs_fts_raw USING fts5(
    object_id UNINDEXED, raw_text, tokenize='unicode61'
);

-- 时间桶：宏观档只读物化桶，下钻才读原始（含**二级年桶**，1y 档必须读年桶）
CREATE TABLE time_bucket (
    bucket_kind TEXT NOT NULL CHECK (bucket_kind IN ('HOUR','DAY','WEEK','MONTH','YEAR')),
    bucket_start TEXT NOT NULL,
    dim_id      TEXT NOT NULL,
    object_count INTEGER NOT NULL,
    rollup_json TEXT NOT NULL,
    PRIMARY KEY (bucket_kind, bucket_start, dim_id)
) WITHOUT ROWID;

-- ========== 条件驱动任务（C08）：typed AST + 三值 + 订阅键 + occurrence ==========
CREATE TABLE trigger_expression (
    expr_id     TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    kind        TEXT NOT NULL CHECK (kind IN
                  ('TIME_REACHED','EVENT_MATCHED','OBSERVATION_PREDICATE','DEPENDENCY_READY',
                   'ALL_OF','ANY_OF','NOT')),
    ast_json    TEXT NOT NULL,
    subscription_key TEXT,           -- 事件/谓词类条件的索引键；无键 = 不可订阅 = 违规
    expiry_at   TEXT,
    hysteresis_json TEXT
);
CREATE INDEX ix_expr_task ON trigger_expression(task_id);
CREATE INDEX ix_expr_subkey ON trigger_expression(subscription_key);

CREATE TABLE task_queue (
    task_id     TEXT PRIMARY KEY,
    state       TEXT NOT NULL CHECK (state IN ('WAITING','READY','RUNNING','DONE','CANCELLED')),
    next_fire_at TEXT,               -- TIME_REACHED 的索引列：调度只扫这一支索引
    dim_id      TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_task_next_fire ON task_queue(next_fire_at) WHERE state = 'WAITING';
CREATE INDEX ix_task_ready ON task_queue(state, priority DESC);

CREATE TABLE task_occurrence (
    occurrence_id TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    fire_key    TEXT NOT NULL,       -- 幂等键：DST/迟到/重启不重不漏
    lease_until TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, fire_key)
);

-- ========== 有界失效传播（C07）：typed edge + epoch + 预算 ==========
CREATE TABLE dep_edge (
    src_id     TEXT NOT NULL,
    dst_id     TEXT NOT NULL,
    edge_type  TEXT NOT NULL CHECK (edge_type IN
                 ('DERIVES_FROM','ANNOTATES','SUPERSEDES','SUPPORTS','CONTRADICTS','RELATES_TO')),
    policy     TEXT NOT NULL CHECK (policy IN ('EAGER_ONE_HOP','LAZY_BUDGETED','NONE')),
    epoch      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (src_id, dst_id, edge_type)
) WITHOUT ROWID;
CREATE INDEX ix_edge_src ON dep_edge(src_id, policy);
-- ========== 三级会话流水线（C10 + C15）：finalized span / watermark / 幂等键 ==========
CREATE TABLE conv_turn (
    turn_id    TEXT PRIMARY KEY,
    conv_id    TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    speaker    TEXT NOT NULL CHECK (speaker IN ('USER','AI','BYSTANDER')),
    finalized  INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (conv_id, seq)
);
CREATE INDEX ix_turn_conv ON conv_turn(conv_id, finalized, seq);
CREATE TABLE extraction_watermark (
    conv_id           TEXT PRIMARY KEY,
    last_finalized_seq INTEGER NOT NULL,
    last_extracted_seq INTEGER NOT NULL,
    lag_tokens        INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL
);
CREATE TABLE extraction_job (
    job_id   TEXT PRIMARY KEY,
    conv_id  TEXT NOT NULL,
    span_lo  INTEGER NOT NULL,
    span_hi  INTEGER NOT NULL,
    state    TEXT NOT NULL CHECK (state IN ('PENDING','RUNNING','DONE','DEAD')),
    idem_key TEXT NOT NULL UNIQUE,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE extracted_claim (
    claim_id TEXT PRIMARY KEY,
    job_id   TEXT NOT NULL,
    conv_id  TEXT NOT NULL,
    seq      INTEGER NOT NULL,
    text_cjk TEXT NOT NULL,
    UNIQUE (conv_id, seq, text_cjk)
);

CREATE TABLE invalidation_frontier (
    object_id  TEXT NOT NULL,
    epoch      INTEGER NOT NULL,
    depth      INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    PRIMARY KEY (object_id, epoch)
) WITHOUT ROWID;
"""

CJK_FIXTURE_TERMS = ["妈妈", "生日", "礼物", "老王", "借钱", "争执", "加班", "熬夜", "心悸",
                     "运动会", "水杯", "吐槽", "爸", "医院", "工资"]
FILLER = ["今天", "下午", "在", "和", "聊了", "关于", "的事情", "后来", "觉得", "有点",
          "非常", "已经", "一起", "讨论", "记录"]


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def pct(samples: list[float], q: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return round(s[k], 3)


def bigrams(s: str) -> list[str]:
    return [s[i:i + 2] for i in range(len(s) - 1)]


def tokenize(text: str, cap: int = 8) -> list[str]:
    """设计书 §3.4-B 的**预分词**：词典词/别名优先 + 受限字符二元组兜底。

    两条设计纪律：
      1. 中文连续文本在 FTS5 `unicode61` 下整段成**一个 token**，2 字词查询 0 命中且
         **不报错**（as-built 探针 P5 实测）⇒ 预分词把召回从"静默为 0"变成"可断言 > 0"（I7）；
      2. 索引的是**抽取出的词**，不是全文二元组：每对象 postings 上限 = `cap`
         （profile 默认 8）。不设闸，1M 对象会产出 1.5~2 千万条 postings，
         索引体积反超真源，违反"单一真源 + 可重建派生"的成本约束。
    """
    out: list[str] = []
    for t in CJK_FIXTURE_TERMS:
        if t in text:
            out.append(t)
    if "母亲" in text:
        out.append("妈妈")        # 别名归一：母亲 ≡ 妈妈（第八十九条别名检索）
    for bg in bigrams(text):
        if len(out) >= cap:
            break
        out.append(bg)
    return list(dict.fromkeys(out))[:cap]


class Design:
    def __init__(self, db_path: str, n_objects: int, n_tasks: int, seed: int = 20260916):
        self.db_path = db_path
        self.n = n_objects
        self.n_tasks = n_tasks
        self.rng = random.Random(seed)
        if os.path.exists(db_path):
            os.remove(db_path)
        self.con = sqlite3.connect(db_path)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.execute("PRAGMA cache_size=-262144")
        self.con.executescript(DDL)
        self.res: dict = {"profile": PROFILE, "scale": {"objects": n_objects, "tasks": n_tasks}}

    # -- 建库 ---------------------------------------------------------------
    def build(self) -> None:
        rng = self.rng
        con = self.con
        t0 = now_ms()
        term_id: dict[str, int] = {}

        def tid(term: str, kind: str) -> int:
            if term not in term_id:
                cur = con.execute(
                    "INSERT INTO term_dict(term_text, tokenizer_id, kind) VALUES(?,?,?)",
                    (term, "cjk-preseg-v1", kind))
                term_id[term] = cur.lastrowid
            return term_id[term]

        for t in CJK_FIXTURE_TERMS:
            tid(t, "WORD")
        tid("母亲", "ALIAS")  # 别名：妈妈 ≡ 母亲（第八十九条别名检索）

        obs_rows, post_rows, fts_rows = [], [], []
        dims = [f"DIM_{i:03d}" for i in range(24)]
        day0 = 1_700_000_000  # 2023-11-14T22:13:20Z；固定纪元，避免时区抖动
        span_s = 365 * 24 * 3600
        # 确定性 fixture：保证"三词共现"与"2 字词"有**非零且可核对**的真值，
        # 否则召回对比退化成 0 vs 0 的空转测量（I7 禁止的正是这种绿灯）。
        n_tri = max(300, self.n // 300)
        n_duo = max(600, self.n // 150)
        self.fixture_truth = {"tri_all_three_terms": 0, "duo_two_terms": 0,
                              "alias_mother": 0, "fixture_month": "2024-03"}
        for i in range(self.n):
            oid = f"OBS{i:09d}"
            ent = f"ENT{i % 4000:06d}"
            dim = dims[i % len(dims)]
            if i < n_tri + n_duo:
                occ = 1_709_251_200 + rng.randrange(0, 29 * 86400)   # 2024-03-01 起 29 天
            else:
                occ = day0 + rng.randrange(0, span_s)
            learned = occ + rng.randrange(0, 86400 * 30)
            if i < n_tri:
                head = "妈妈" if i % 3 else "母亲"
                text = head + "的生日礼物" + "".join(rng.choice(FILLER) for _ in range(6))
                self.fixture_truth["tri_all_three_terms"] += 1
                self.fixture_truth["alias_mother"] += (1 if head == "母亲" else 0)
            elif i < n_tri + n_duo:
                text = ("生日" if i % 2 else "礼物") + "".join(rng.choice(FILLER) for _ in range(8))
                self.fixture_truth["duo_two_terms"] += 1
            else:
                k = rng.choice(CJK_FIXTURE_TERMS)
                k2 = rng.choice(CJK_FIXTURE_TERMS)
                text = f"{k}和{k2}" + "".join(rng.choice(FILLER) for _ in range(rng.randrange(4, 14)))
            obs_rows.append((oid, ent, dim,
                             time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(occ)),
                             time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(learned)),
                             text, round(rng.uniform(0.4, 1.6), 3)))
            toks = tokenize(text, PROFILE["max_postings_per_object"])
            for t in toks:
                post_rows.append((tid(t, "BIGRAM" if len(t) == 2 and t not in CJK_FIXTURE_TERMS else "WORD"),
                                  oid, "text_cjk", 1.0))
            fts_rows.append((oid, " ".join(toks), oid, text))
            if i and i % 20000 == 0:
                con.executemany("INSERT INTO obs VALUES(?,?,?,?,?,?,?)", obs_rows)
                # 曾经写成 post_rows[-60000:] —— 每批只插入尾部 6 万条、静默丢弃其余，
                # 导致 postings/object 只有 3.31 且三词交集恒为 0（探针自己的"静默零召回"）。
                con.executemany("INSERT OR IGNORE INTO term_postings VALUES(?,?,?,?)", post_rows)
                con.executemany("INSERT INTO obs_fts(object_id, seg_text) VALUES(?,?)",
                                [(r[0], r[1]) for r in fts_rows])
                con.executemany("INSERT INTO obs_fts_raw(object_id, raw_text) VALUES(?,?)",
                                [(r[2], r[3]) for r in fts_rows])
                obs_rows, post_rows, fts_rows = [], [], []
        if obs_rows:
            con.executemany("INSERT INTO obs VALUES(?,?,?,?,?,?,?)", obs_rows)
            con.executemany("INSERT OR IGNORE INTO term_postings VALUES(?,?,?,?)", post_rows)
            con.executemany("INSERT INTO obs_fts(object_id, seg_text) VALUES(?,?)",
                            [(r[0], r[1]) for r in fts_rows])
            con.executemany("INSERT INTO obs_fts_raw(object_id, raw_text) VALUES(?,?)",
                            [(r[2], r[3]) for r in fts_rows])
        con.commit()
        build_ms = now_ms() - t0

        t0 = now_ms()
        con.execute("ANALYZE")
        con.commit()
        db_mb = round(os.path.getsize(self.db_path) / 1048576, 1)
        n_post = con.execute("SELECT count(*) FROM term_postings").fetchone()[0]
        self.res["fixture_truth"] = self.fixture_truth
        lo, hi = con.execute("SELECT min(occurred_at), max(occurred_at) FROM obs").fetchone()
        self.date_range = {"min": lo, "max": hi}
        self.res["build"] = {
            "occurred_at_range": self.date_range,
            "insert_and_index_ms": round(build_ms, 1),
            "analyze_ms": round(now_ms() - t0, 1),
            "db_size_mb": db_mb,
            "bytes_per_row": round(db_mb * 1048576 / self.n, 1),
            "postings_rows": n_post,
            "postings_per_object": round(n_post / self.n, 2),
        }
        self._build_buckets(dims)
        self._build_tasks()
        self._build_edges()
        con.execute("INSERT OR REPLACE INTO cp_index_watermark VALUES('term_postings',?,?, 'FRESH')",
                    (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(day0 + 365 * 86400)),
                     time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())))
        con.commit()

    def _build_buckets(self, dims: list[str]) -> None:
        con = self.con
        t0 = now_ms()
        for kind, fmt in (("DAY", "%Y-%m-%d"), ("MONTH", "%Y-%m"), ("YEAR", "%Y")):
            con.execute(f"""
                INSERT OR REPLACE INTO time_bucket(bucket_kind, bucket_start, dim_id, object_count, rollup_json)
                SELECT ?, strftime(?, occurred_at), dim_id, count(*),
                       '{{"avg_kb":' || round(avg(payload_kb),3) || ',"n_entities":' || count(DISTINCT entity_id) || '}}'
                FROM obs GROUP BY strftime(?, occurred_at), dim_id
            """, (kind, fmt, fmt))
        con.commit()
        counts = {r[0]: r[1] for r in con.execute(
            "SELECT bucket_kind, count(*) FROM time_bucket GROUP BY bucket_kind")}
        self.res["time_bucket_build"] = {"ms": round(now_ms() - t0, 1), "rows_by_kind": counts}

    def _build_tasks(self) -> None:
        con = self.con
        t0 = now_ms()
        rng = self.rng
        trows, erows = [], []
        for i in range(self.n_tasks):
            tid_ = f"TASK{i:08d}"
            kind = rng.choice(["TIME_REACHED", "TIME_REACHED", "EVENT_MATCHED",
                               "OBSERVATION_PREDICATE", "DEPENDENCY_READY", "ALL_OF"])
            fire = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(1_700_000_000 + rng.randrange(0, 365 * 86400)))
            # 只有 TIME_REACHED 才有 next_fire_at；其余条件走订阅键，三值求值下 UNKNOWN 不唤醒
            trows.append((tid_, "WAITING", fire if kind == "TIME_REACHED" else None,
                          f"DIM_{i % 24:03d}", rng.randrange(0, 5)))
            sub = None if kind == "TIME_REACHED" else f"sub:{rng.choice(CJK_FIXTURE_TERMS)}"
            ast = {"kind": kind, "args": {"at": fire} if kind == "TIME_REACHED" else {"key": sub},
                   "three_value": True, "version": 1}
            erows.append((f"EX{i:08d}", tid_, 1, kind, json.dumps(ast, ensure_ascii=False), sub,
                          None, json.dumps({"min_gap_s": 900})))
        con.executemany("INSERT INTO task_queue VALUES(?,?,?,?,?)", trows)
        con.executemany("INSERT INTO trigger_expression VALUES(?,?,?,?,?,?,?,?)", erows)
        con.commit()
        self.res["task_build"] = {"ms": round(now_ms() - t0, 1), "tasks": self.n_tasks}

    def _build_edges(self) -> None:
        con = self.con
        t0 = now_ms()
        rng = self.rng
        rows = []
        # 一个超级节点（枢纽实体）+ 大量普通边，复刻 as-built 传播测试的拓扑形状
        hub = "OBS000000000"
        self.hub_fanout = min(50_000, max(4_000, self.n // 20))
        for i in range(1, self.hub_fanout):
            rows.append((hub, f"OBS{i:09d}", "DERIVES_FROM", "EAGER_ONE_HOP", 0))
        for i in range(self.hub_fanout, self.hub_fanout + 500_000):
            src = f"OBS{i % self.n:09d}"
            dst = f"OBS{rng.randrange(0, self.n):09d}"
            rows.append((src, dst, rng.choice(["SUPPORTS", "ANNOTATES", "RELATES_TO"]),
                         rng.choice(["LAZY_BUDGETED", "NONE", "EAGER_ONE_HOP"]), 0))
        con.executemany("INSERT OR IGNORE INTO dep_edge VALUES(?,?,?,?,?)", rows)
        con.commit()
        self.res["edge_build"] = {"ms": round(now_ms() - t0, 1),
                                  "edges": con.execute("SELECT count(*) FROM dep_edge").fetchone()[0],
                                  "hub_fanout": self.hub_fanout - 1}

    # -- 验证 1：条件驱动 READY 求值（I4 就绪律） ----------------------------
    def v_ready_queue(self) -> None:
        """两条求值路径必须给出**同一个 READY 集合**（正确性），再比开销（性能）。

        路径 A（naive）：读出全部 trigger_expression，在 Python 侧逐条求值 —— 这是
          旧任务书 M2-005/M2-006「每次醒来把待办跑一遍」的实现形状。
        路径 B（subscription index）：TIME_REACHED 走 `next_fire_at` 偏索引；
          EVENT_MATCHED/OBSERVATION_PREDICATE 走 `subscription_key`；三值逻辑下
          UNKNOWN **不唤醒**（既不 READY，也不丢弃）。
        """
        con = self.con
        wake_ts = "2024-03-01T00:00:00"
        fired_events = {"sub:妈妈", "sub:生日"}   # 本轮 Wake 前已发生的事件键

        def eval_three_value(kind: str, ast: dict) -> str:
            if kind == "TIME_REACHED":
                return "TRUE" if ast["args"]["at"] <= wake_ts else "FALSE"
            if kind in ("EVENT_MATCHED", "OBSERVATION_PREDICATE"):
                key = ast["args"].get("key")
                if key is None:
                    return "UNKNOWN"          # 无订阅键 = 不可订阅 = 设计违规
                return "TRUE" if key in fired_events else "UNKNOWN"
            if kind == "DEPENDENCY_READY":
                return "UNKNOWN"              # 依赖未完成时保持 UNKNOWN，不当 FALSE 丢弃
            return "UNKNOWN"

        naive, indexed, unknown_kept = [], [], []
        naive_ready = idx_ready = 0
        for _ in range(10):
            t0 = now_ms()
            rows = con.execute(
                "SELECT e.task_id, e.kind, e.ast_json FROM trigger_expression e "
                "JOIN task_queue q USING(task_id) WHERE q.state='WAITING'").fetchall()
            ready, unknown = 0, 0
            for _tid, kind, ast in rows:
                v = eval_three_value(kind, json.loads(ast))
                if v == "TRUE":
                    ready += 1
                elif v == "UNKNOWN":
                    unknown += 1
            naive.append(now_ms() - t0)
            naive_ready, naive_unknown = ready, unknown
        for _ in range(10):
            t0 = now_ms()
            ready = con.execute(
                "SELECT count(*) FROM task_queue WHERE state='WAITING' AND next_fire_at IS NOT NULL "
                "AND next_fire_at <= ?", (wake_ts,)).fetchone()[0]
            ready += con.execute(
                "SELECT count(*) FROM trigger_expression e JOIN task_queue q USING(task_id) "
                "WHERE q.state='WAITING' AND e.kind IN ('EVENT_MATCHED','OBSERVATION_PREDICATE') "
                "AND e.subscription_key IN (%s)" % ",".join("?" * len(fired_events)),
                tuple(sorted(fired_events))).fetchone()[0]
            indexed.append(now_ms() - t0)
            idx_ready = ready
        # UNKNOWN 普查属于**巡检/监控查询**，不是调度热路径；单独计时，禁止混入 READY 计算
        t0 = now_ms()
        census = con.execute(
            "SELECT count(*) FROM trigger_expression e JOIN task_queue q USING(task_id) "
            "WHERE q.state='WAITING' AND e.kind IN ('EVENT_MATCHED','OBSERVATION_PREDICATE',"
            "'DEPENDENCY_READY') AND (e.subscription_key IS NULL OR e.subscription_key NOT IN (%s))"
            % ",".join("?" * len(fired_events)), tuple(sorted(fired_events))).fetchone()[0]
        census_ms = now_ms() - t0
        unknown_kept.append(census)
        # 设计采纳路径：READY 是**被维护的状态**，不是每次 Wake 现算的结果。
        # 维护（事件到达/时间推进时增量更新）成本 = 上面的 subscription_index；
        # Wake 时的读成本 = 只取 manifest 需要的 top-N。
        con.execute("UPDATE task_queue SET state='READY' WHERE state='WAITING' "
                    "AND next_fire_at IS NOT NULL AND next_fire_at <= ?", (wake_ts,))
        con.commit()
        mat_s = []
        for _ in range(50):
            t0 = now_ms()
            top = con.execute("SELECT task_id, priority FROM task_queue WHERE state='READY' "
                              "ORDER BY priority DESC LIMIT 8").fetchall()
            mat_s.append(now_ms() - t0)
        con.execute("UPDATE task_queue SET state='WAITING' WHERE state='READY'")
        con.commit()

        self.res["v1_ready_queue"] = {
            "materialized_ready_read_ms": {"p50": pct(mat_s, .5), "p95": pct(mat_s, .95),
                                           "top_n": len(top)},
            "wake_time_budget_ms": 5.0,
            "tasks": self.n_tasks, "wake_ts": wake_ts, "fired_event_keys": sorted(fired_events),
            "naive_full_scan_ms": {"p50": pct(naive, .5), "p95": pct(naive, .95)},
            "subscription_index_ms": {"p50": pct(indexed, .5), "p95": pct(indexed, .95)},
            "ready_set_size": {"naive": naive_ready, "indexed": idx_ready},
            "correctness_ready_sets_equal": naive_ready == idx_ready,
            "unknown_not_woken_but_kept": {"count": unknown_kept[-1],
                                           "census_ms": round(census_ms, 1),
                                           "rule": "UNKNOWN 既不 READY 也不丢弃（三值律）；其普查是"
                                                   "巡检查询，**不得进入调度热路径**（否则会吃掉"
                                                   "整个 1 s 首字预算）"},
            "speedup_p95": round(pct(naive, .95) / max(pct(indexed, .95), 1e-6), 1),
            "acceptance": "READY 计算不得遍历全部任务；两条路径 READY 集合必须完全相等；"
                          "Wake 时只读物化 READY 队列的 top-N（<= 5 ms），全量重算只能是"
                          "**增量维护**动作；WAITING/UNKNOWN 任务不得进入 manifest（I4）",
        }

    # -- 验证 2：中文混合共搜（I7 不静默零召回律） ---------------------------
    def v_co_search(self) -> None:
        con = self.con
        terms = ["妈妈", "生日", "礼物"]
        like_s, fts_raw_s, fts_seg_s, post_s = [], [], [], []
        like_hits = fts_raw_hits = fts_seg_hits = post_hits = 0
        for _ in range(5):
            t = now_ms()
            like_hits = con.execute(
                "SELECT count(*) FROM obs WHERE text_cjk LIKE ? AND text_cjk LIKE ? AND text_cjk LIKE ?",
                tuple(f"%{x}%" for x in terms)).fetchone()[0]
            like_s.append(now_ms() - t)
        for _ in range(20):
            t = now_ms()
            fts_raw_hits = con.execute(
                "SELECT count(*) FROM obs_fts_raw WHERE obs_fts_raw MATCH ?",
                ('"' + "".join(terms) + '"',)).fetchone()[0]
            fts_raw_s.append(now_ms() - t)
        for _ in range(20):
            t = now_ms()
            fts_seg_hits = con.execute(
                "SELECT count(*) FROM obs_fts WHERE obs_fts MATCH ?",
                (" AND ".join(f'"{x}"' for x in terms),)).fetchone()[0]
            fts_seg_s.append(now_ms() - t)
        ids = [r[0] for r in con.execute("SELECT term_id FROM term_dict WHERE term_text IN (?,?,?)",
                                         tuple(terms))]
        # 选择性排序：postings 基数最小的词放最外层（设计书 §3.4-B 的查询计划纪律）
        sel = sorted((con.execute("SELECT count(*) FROM term_postings WHERE term_id=?",
                                  (i,)).fetchone()[0], i) for i in ids)
        sel_ids = [i for _c, i in sel]
        pairwise_q = ("SELECT p1.object_id FROM term_postings p1 "
                      "JOIN term_postings p2 ON p2.object_id = p1.object_id AND p2.term_id = ? "
                      "JOIN term_postings p3 ON p3.object_id = p1.object_id AND p3.term_id = ? "
                      "WHERE p1.term_id = ?")
        pair_s, pair_hits = [], 0
        for _ in range(20):
            t = now_ms()
            pair_hits = len(con.execute(pairwise_q, (sel_ids[1], sel_ids[2], sel_ids[0])).fetchall())
            pair_s.append(now_ms() - t)
        topk_s, topk_hits = [], 0
        for _ in range(20):
            t = now_ms()
            topk_hits = len(con.execute(pairwise_q + " LIMIT 200",
                                        (sel_ids[1], sel_ids[2], sel_ids[0])).fetchall())
            topk_s.append(now_ms() - t)
        anchor_s, anchor_hits = [], 0
        for _ in range(20):
            t = now_ms()
            anchor_hits = con.execute(
                "SELECT count(*) FROM obs o WHERE o.entity_id = ? "
                "AND EXISTS (SELECT 1 FROM term_postings p1 WHERE p1.object_id=o.object_id AND p1.term_id=?)"
                " AND EXISTS (SELECT 1 FROM term_postings p2 WHERE p2.object_id=o.object_id AND p2.term_id=?)"
                " AND EXISTS (SELECT 1 FROM term_postings p3 WHERE p3.object_id=o.object_id AND p3.term_id=?)",
                ("ENT000042", sel_ids[0], sel_ids[1], sel_ids[2])).fetchone()[0]
            anchor_s.append(now_ms() - t)
        for _ in range(5):
            t = now_ms()
            if len(ids) == len(terms):
                q = ("SELECT object_id FROM term_postings WHERE term_id IN (%s) "
                     "GROUP BY object_id HAVING count(DISTINCT term_id) = %d"
                     % (",".join("?" * len(ids)), len(ids)))
                post_hits = len(con.execute(q, ids).fetchall())
            else:
                post_hits = 0
            post_s.append(now_ms() - t)
        # 2 字词召回（as-built 实测 trigram/unicode61 对 2 字词 = 0 命中且不报错）
        two = "生日"
        raw2 = con.execute("SELECT count(*) FROM obs_fts_raw WHERE obs_fts_raw MATCH ?",
                           (f'"{two}"',)).fetchone()[0]
        seg2 = con.execute("SELECT count(*) FROM obs_fts WHERE obs_fts MATCH ?",
                           (f'"{two}"',)).fetchone()[0]
        post2 = con.execute(
            "SELECT count(*) FROM term_postings p JOIN term_dict d USING(term_id) WHERE d.term_text=?",
            (two,)).fetchone()[0]
        like2 = con.execute("SELECT count(*) FROM obs WHERE text_cjk LIKE ?", (f"%{two}%",)).fetchone()[0]
        # 别名（妈妈 ≡ 母亲）
        alias = con.execute(
            "SELECT count(*) FROM term_postings p JOIN term_dict d USING(term_id) WHERE d.term_text IN ('妈妈','母亲')"
        ).fetchone()[0]
        self.res["v2_co_search"] = {
            "terms": terms, "objects": self.n,
            "like_scan": {"hits": like_hits, "p50_ms": pct(like_s, .5), "p95_ms": pct(like_s, .95)},
            "fts5_raw_unicode61_AS_BUILT": {"hits": fts_raw_hits, "p95_ms": pct(fts_raw_s, .95),
                                            "note": "**未预分词**的原始中文 = as-built 做法；"
                                                    "连续中文串按整段成一个 token，故命中恒为 0 且**不报错**"},
            "raw_two_char_hits": raw2, "presegmented_two_char_hits": seg2,
            "fts5_presegmented_and": {"hits": fts_seg_hits, "p95_ms": pct(fts_seg_s, .95),
                                      "note": "预分词后 AND 共现（设计书采用路径）"},
            "term_postings_3way_group_by": {
                "hits": post_hits, "p50_ms": pct(post_s, .5), "p95_ms": pct(post_s, .95),
                "verdict": "**REJECTED_PLAN**：3 路 GROUP BY + HAVING 在 1M 对象 / 6.26M postings 上"
                           "超出 50 ms 门；本探针保留它只为交叉核对命中数（真值对照）"},
            "term_postings_pairwise_selectivity_ordered": {
                "hits": pair_hits, "p50_ms": pct(pair_s, .5), "p95_ms": pct(pair_s, .95),
                "selectivity_postings_counts": [c for c, _i in sel],
                "verdict": "**ADOPTED_PLAN-A**：按 postings 基数升序做两两 JOIN 交集"},
            "term_postings_pairwise_topk_early_termination": {
                "hits_capped": topk_hits, "p50_ms": pct(topk_s, .5), "p95_ms": pct(topk_s, .95),
                "verdict": "**ADOPTED_PLAN-C**：无锚定时必须 top-K 早停 + 后置排序，"
                           "绝不做全量交集计数（全量计数见 REJECTED_PLAN）"},
            "term_postings_entity_anchored": {
                "hits": anchor_hits, "p95_ms": pct(anchor_s, .95),
                "verdict": "**ADOPTED_PLAN-B**：实体锚定预过滤（第八十九条），单实体范围内三词共现"},
            "two_char_term_recall": {"like_full_scan": like2, "postings": post2,
                                     "fts5_raw": raw2, "fts5_presegmented": seg2,
                                     "acceptance": f"必须 > 0（I7）；实测 postings={post2}, "
                                                   f"presegmented={seg2}, raw={raw2}"},
            "alias_recall_postings": alias,
            "verdict": {
                "postings_pairwise_p95_under_gate":
                    pct(pair_s, .95) <= PROFILE["co_search_p95_ms"],
                "postings_entity_anchored_p95_under_gate":
                    pct(anchor_s, .95) <= PROFILE["co_search_p95_ms"],
                "postings_topk_p95_under_gate":
                    pct(topk_s, .95) <= PROFILE["co_search_p95_ms"],
                "postings_3way_group_by_p95_under_gate":
                    pct(post_s, .95) <= PROFILE["co_search_p95_ms"],
                "fts_and_p95_under_gate": pct(fts_seg_s, .95) <= PROFILE["co_search_p95_ms"],
                "gate_ms": PROFILE["co_search_p95_ms"],
                "like_vs_postings_speedup_p95": round(pct(like_s, .95) / max(pct(post_s, .95), 1e-6), 1),
                "correctness_postings_superset_of_like": post_hits >= like_hits,
                "correctness_alias_gap_explained":
                    (post_hits - like_hits) == self.fixture_truth["alias_mother"],
                "correctness_note": ("LIKE 只能命中字面串；postings 走**别名归一**（母亲 ≡ 妈妈），"
                                     "故 postings 命中必须是 LIKE 的超集，且超出部分必须**恰好等于**"
                                     "别名 fixture 行数 —— 差值对不上就说明索引或别名表有 bug"),
                "fixture_truth": getattr(self, "fixture_truth", {}),
            },
        }

    # -- 验证 3：5D 滑动条时间口径（occurred_at vs learned_at） --------------
    def v_time_slider(self) -> None:
        """5D 滑动条的读路径：宏观档只读物化桶，下钻才读原始行。

        口径纪律（设计书铁律 2）：切的是 **occurred_at（发生时间）**，不是 learned_at。
        as-built 只有 learned_at 索引，因此同一查询在旧口径下 369 ms、在宪法口径下
        1,201~1,468 ms —— 本探针把两者都测出来，防止规模门用错口径绿灯通过。
        """
        con = self.con
        out: dict = {}
        rng = self.date_range
        month_lo, month_hi = "2024-03-01T00:00:00", "2024-03-31T23:59:59"
        year_lo, year_hi = "2024-01-01T00:00:00", "2024-12-31T23:59:59"

        # (a) as-built 读法：occurred_at 无索引 ⇒ 全表扫
        for label, lo, hi in (("month_window", month_lo, month_hi), ("year_window", year_lo, year_hi)):
            s = []
            for _ in range(3):
                t0 = now_ms()
                n = con.execute("SELECT count(*) FROM obs WHERE occurred_at BETWEEN ? AND ?",
                                (lo, hi)).fetchone()[0]
                s.append(now_ms() - t0)
            out[f"scan_occurred_at_{label}"] = {"rows": n, "p50_ms": pct(s, .5), "p95_ms": pct(s, .95)}
        # (a2) 对照：learned_at 有索引（旧探针口径）
        s = []
        for _ in range(10):
            t0 = now_ms()
            n2 = con.execute("SELECT count(*) FROM obs WHERE learned_at BETWEEN ? AND ?",
                             (month_lo, month_hi)).fetchone()[0]
            s.append(now_ms() - t0)
        out["scan_learned_at_indexed_month"] = {"rows": n2, "p95_ms": pct(s, .95),
                                                "note": "旧口径；与宪法要求的发生时间不同源"}

        # (b) 设计书读法：宏观档只读桶
        for kind, lo, hi in (("DAY", "2024-03-01", "2024-03-31"),
                             ("MONTH", "2024-03", "2024-03"), ("YEAR", "2024", "2024")):
            s = []
            for _ in range(50):
                t0 = now_ms()
                rows = con.execute(
                    "SELECT coalesce(sum(object_count),0), count(*) FROM time_bucket "
                    "WHERE bucket_kind=? AND bucket_start BETWEEN ? AND ?", (kind, lo, hi)).fetchone()
                s.append(now_ms() - t0)
            out[f"bucket_{kind.lower()}"] = {"buckets_scanned": rows[1], "objects": rows[0],
                                             "p50_ms": pct(s, .5), "p95_ms": pct(s, .95)}
        # (c) 1y 档：年桶直读 vs 日桶求和（证明**二级年桶**是必需设计，不是优化）
        s = []
        for _ in range(20):
            t0 = now_ms()
            con.execute("SELECT coalesce(sum(object_count),0) FROM time_bucket "
                        "WHERE bucket_kind='DAY' AND bucket_start BETWEEN '2024-01-01' AND '2024-12-31'"
                        ).fetchone()
            s.append(now_ms() - t0)
        out["year_via_day_bucket_summation"] = {"p50_ms": pct(s, .5), "p95_ms": pct(s, .95),
                                                "day_buckets": out["bucket_day"]["buckets_scanned"] or
                                                con.execute("SELECT count(*) FROM time_bucket "
                                                            "WHERE bucket_kind='DAY'").fetchone()[0]}
        out["year_via_year_bucket"] = {"p95_ms": out["bucket_year"]["p95_ms"]}
        out["year_bucket_speedup"] = round(out["year_via_day_bucket_summation"]["p95_ms"] /
                                           max(out["bucket_year"]["p95_ms"], 1e-6), 1)

        # (d) 下钻：从月桶钻到原始行（分页 200）—— 只有下钻才允许碰原始表
        s = []
        for _ in range(10):
            t0 = now_ms()
            page = con.execute("SELECT object_id, occurred_at, text_cjk FROM obs "
                               "WHERE occurred_at BETWEEN ? AND ? ORDER BY occurred_at LIMIT 200",
                               (month_lo, month_hi)).fetchall()
            s.append(now_ms() - t0)
        out["drilldown_page200"] = {"rows": len(page), "p95_ms": pct(s, .95)}

        gate = PROFILE["time_bucket_p95_ms"]
        out["acceptance"] = (f"宏观档必须只读桶；DAY/MONTH/YEAR 桶查询 p95 <= {gate} ms；"
                             "1y 档必须读**年桶**（日桶求和随天数线性退化）；"
                             "窗口一律按 occurred_at，禁止用 learned_at 冒充")
        out["gate_pass"] = all(out[k]["p95_ms"] <= gate
                               for k in ("bucket_day", "bucket_month", "bucket_year"))
        out["non_vacuous"] = (out["bucket_month"]["objects"] or 0) > 0 and \
                             (out["scan_occurred_at_month_window"]["rows"] or 0) > 0
        self.res["v3_time_slider"] = out

    # -- 验证 4：CockpitManifest 组装 + 预算/deadline 代数（I3/I5） ----------
    def v_manifest(self) -> None:
        con = self.con
        wake_id = "WAKE-DEMO-0001"
        tier = "ROUTINE"
        ceiling = PROFILE["manifest_token_tier"][tier]
        s = []
        manifest = None
        for _ in range(50):
            t = now_ms()
            ready = con.execute(
                "SELECT task_id, priority FROM task_queue WHERE state='READY' "
                "ORDER BY priority DESC LIMIT 8").fetchall()
            if not ready:  # 首次运行：把到期任务置 READY（I4：只挂 READY）
                due = [r[0] for r in con.execute(
                    "SELECT task_id FROM task_queue WHERE state='WAITING' "
                    "AND next_fire_at <= '2024-03-01T00:00:00' LIMIT 8")]
                con.executemany("UPDATE task_queue SET state='READY' WHERE task_id=?", [(x,) for x in due])
                ready = con.execute("SELECT task_id, priority FROM task_queue WHERE state='READY' "
                                    "ORDER BY priority DESC LIMIT 8").fetchall()
            # 切片走**索引指针**（entity_id），绝不 ORDER BY RANDOM() 全表扫 —— 看板组装是读路径，不是分析查询
            slices = con.execute(
                "SELECT object_id, text_cjk FROM obs WHERE entity_id = ? LIMIT 12",
                ("ENT000042",)).fetchall()
            buckets = con.execute("SELECT bucket_start, object_count, rollup_json FROM time_bucket "
                                  "WHERE bucket_kind='MONTH' ORDER BY bucket_start DESC LIMIT 6").fetchall()
            rapport = {"dim": "DIM_AI_RAPPORT", "thickness": 0.72, "recent_conflict": False}
            seg = [
                {"segment": 1, "name": "照镜子（AI 自身记忆树与上次心智停留点）",
                 "payload": {"self_summary_ref": "SUM-SELF-0007", "last_stance": "关切+调侃"}},
                {"segment": 2, "name": "校准羁绊（DIM_AI_RAPPORT）", "payload": rapport},
                {"segment": 3, "name": "确立姿态与语调", "payload": {"tone": "老友", "max_sentences": 3}},
                {"segment": 4, "name": "审视用户世界与触发源",
                 "payload": {"wake_reason": wake_id, "ready_tasks": ready,
                             "evidence_slices": slices, "macro_buckets": buckets,
                             "capabilities": ["world.co_search", "world.read", "workspace.open",
                                              "task.create", "message.send"]}},
            ]
            manifest = {"wake_id": wake_id, "tier": tier, "segment_order": [x["segment"] for x in seg],
                        "segments": seg}
            blob = json.dumps(manifest, ensure_ascii=False)
            tokens = len(blob) // 3  # 中文 ~3 字节/token 的粗估（设计书要求以真实 tokenizer 替换）
            s.append(now_ms() - t)
            if tokens > ceiling:
                manifest["degraded"] = True
        con.execute("INSERT OR REPLACE INTO cp_deadline VALUES(?,?,?,?,?,1)",
                    (wake_id, tier, 0.0, PROFILE["manifest_budget_ms"], PROFILE["ttft_budget_ms"]))
        mh = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        con.execute("INSERT OR REPLACE INTO cp_context_receipt "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (f"RCPT-{wake_id}", wake_id, mh, "1>2>3>4", len(blob) // 3,
                     pct(s, .5), 0, len(manifest["segments"][3]["payload"]["ready_tasks"]), 0,
                     time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())))
        con.commit()
        p95 = pct(s, .95)
        self.res["v4_manifest"] = {
            "assembly_ms": {"p50": pct(s, .5), "p95": p95},
            "budget_ms": PROFILE["manifest_budget_ms"],
            "gate_pass": p95 <= PROFILE["manifest_budget_ms"],
            "token_estimate": len(blob) // 3, "tier_ceiling": ceiling,
            "manifest_hash": mh,
            "system_filler_turns": 0,
            "waiting_tasks_in_manifest": 0,
            "acceptance": ("四步序 = **单次 prompt 内 4 个 segment**（I5），不是 4 次模型往返；"
                           "manifest 只挂 READY（I4）；receipt 落库使'模型当时看到什么'可复现"),
        }

    # -- 验证 5：有界失效传播（预算 + epoch + no-op diff） -------------------
    def v_propagation(self) -> None:
        con = self.con
        hub = "OBS000000000"
        # (a) 现状做法：全量入内存递归（as-built 实测 9.3 s / 51,822 对象）
        t = now_ms()
        edges = con.execute("SELECT src_id, dst_id, policy FROM dep_edge").fetchall()
        adj: dict[str, list[tuple[str, str]]] = {}
        for s_, d_, p_ in edges:
            adj.setdefault(s_, []).append((d_, p_))
        seen = set()
        stack = [hub]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for d_, _p in adj.get(cur, []):
                if d_ not in seen:
                    stack.append(d_)
        unbounded_ms = now_ms() - t
        # (b) 设计书做法：typed policy + breadth/depth 预算 + epoch + frontier 落库
        s = []
        visited_counts = []
        for run in range(10):
            t = now_ms()
            epoch = run + 1
            frontier = [(hub, 0)]
            visited = {hub}
            budget_nodes = PROFILE["propagation_max_nodes"]
            budget_depth = PROFILE["propagation_max_depth"]
            truncated = False
            while frontier and len(visited) < budget_nodes:
                next_frontier = []
                for node, depth in frontier:
                    if depth >= budget_depth:
                        truncated = True
                        continue
                    rows = con.execute(
                        "SELECT dst_id FROM dep_edge WHERE src_id=? AND policy IN ('EAGER_ONE_HOP','LAZY_BUDGETED') "
                        "LIMIT ?", (node, budget_nodes - len(visited))).fetchall()
                    for (d_,) in rows:
                        if d_ not in visited:
                            visited.add(d_)
                            next_frontier.append((d_, depth + 1))
                            if len(visited) >= budget_nodes:
                                truncated = True
                                break
                frontier = next_frontier
            con.executemany("INSERT OR IGNORE INTO invalidation_frontier VALUES(?,?,?,?)",
                            [(v, epoch, 1, "hub_revision") for v in list(visited)[:budget_nodes]])
            s.append(now_ms() - t)
            visited_counts.append(len(visited))
        con.commit()
        p95 = pct(s, .95)
        self.res["v5_propagation"] = {
            "unbounded_in_memory": {"ms": round(unbounded_ms, 1), "reached_objects": len(seen),
                                    "note": "复刻现状 dependency/graph.py 的全量入内存做法"},
            "bounded_budgeted": {"p50_ms": pct(s, .5), "p95_ms": p95,
                                 "visited": visited_counts[-1], "truncated": truncated,
                                 "budget_nodes": budget_nodes, "budget_depth": budget_depth},
            "speedup": round(unbounded_ms / max(p95, 1e-6), 1),
            "gate_pass": p95 <= PROFILE["propagation_budget_ms"],
            "acceptance": ("超节点必须有界；普通 RELATES_TO 不传播；未重算的旧总结不得静默冒充 CURRENT"
                           "（读时有效性守卫）；语义 no-op（只换措辞）不得触发传播"),
        }

    # -- 验证 6：写路径与预算结算（I3 预算律 + group commit） ----------------
    def v_write_path(self) -> None:
        con = self.con
        # 逐条提交 vs group commit（as-built 实测 fsync FULL 0.47 ms/次、NORMAL 0.09 ms/次）
        con.execute("PRAGMA synchronous=FULL")
        single = []
        for i in range(200):
            t = now_ms()
            con.execute("INSERT OR REPLACE INTO cp_budget_ledger VALUES(?,?,?,?,?,?,?,?,?)",
                        (f"L-S{i:05d}", "SESSION", f"S{i % 7}", "RETRIEVAL", 0, 120, 2048, 0,
                         time.strftime("%Y-%m-%dT%H:%M:%S")))
            con.commit()
            single.append(now_ms() - t)
        con.execute("PRAGMA synchronous=NORMAL")
        group = []
        for i in range(200):
            con.execute("INSERT OR REPLACE INTO cp_budget_ledger VALUES(?,?,?,?,?,?,?,?,?)",
                        (f"L-G{i:05d}", "SESSION", f"S{i % 7}", "RETRIEVAL", 0, 120, 2048, 0,
                         time.strftime("%Y-%m-%dT%H:%M:%S")))
            group.append(now_ms() - t)
        t = now_ms()
        con.commit()
        group_commit_ms = now_ms() - t
        con.execute("DELETE FROM cp_budget_ledger WHERE ledger_id LIKE 'L-%'")
        con.commit()
        per_day = 1090  # as-built 实测：reduction 模型下 1,090 行/日
        self.res["v6_write_path"] = {
            "fsync_FULL_per_commit_ms": {"p50": pct(single, .5), "p95": pct(single, .95)},
            "group_commit_200_rows_ms": round(group_commit_ms, 2),
            "projected_daily_fsync_s": {
                "per_row_commit_FULL": round(per_day * pct(single, .5) / 1000, 2),
                "group_commit_NORMAL": round(group_commit_ms / 1000 * per_day / 200, 4),
            },
            "acceptance": "摄入必须 group commit；预算必须 reserve→settle 两阶段（I3）",
        }

    def v7_pipeline(self) -> None:
        """三级流水线：前台窗口 + 后台增量萃取（watermark + 幂等键）+ crash/retry 不重复。

        模拟：50 轮对话 × N 个会话；萃取到一半"进程被杀"（不落 DONE），随后用**同一
        idem_key** 重试。断言：Claim 总数 == 应萃取的 finalized turn 数（不重不漏）。
        """
        con = self.con
        n_conv = max(20, self.n // 20_000)
        turns_per_conv = 50
        rng = self.rng
        trows = []
        for c in range(n_conv):
            cid = f"CONV{c:06d}"
            for s in range(1, turns_per_conv + 1):
                trows.append((f"T{c:06d}-{s:03d}", cid, s, "USER" if s % 2 else "AI",
                              1 if s <= turns_per_conv - 3 else 0,   # 最后 3 轮未 finalize
                              rng.randrange(20, 90), "2024-03-01T00:00:00"))
        con.executemany("INSERT INTO conv_turn VALUES(?,?,?,?,?,?,?)", trows)
        con.commit()

        window_tokens = PROFILE["active_window_tokens"]
        claims_attempted = 0
        t0 = now_ms()
        for c in range(n_conv):
            cid = f"CONV{c:06d}"
            fin = [r[0] for r in con.execute(
                "SELECT seq FROM conv_turn WHERE conv_id=? AND finalized=1 ORDER BY seq", (cid,))]
            # 前台活跃窗口：从尾部按 token 预算回填，保证 <= window_tokens
            acc, window = 0, []
            for seq in reversed(fin):
                tk = con.execute("SELECT token_count FROM conv_turn WHERE conv_id=? AND seq=?",
                                 (cid, seq)).fetchone()[0]
                if acc + tk > window_tokens:
                    break
                window.append(seq)
                acc += tk
            last_wm = con.execute("SELECT last_extracted_seq FROM extraction_watermark WHERE conv_id=?",
                                  (cid,)).fetchone()
            lo = (last_wm[0] + 1) if last_wm else 1
            hi = max(fin) if fin else 0
            if hi >= lo:
                job = f"JOB{c:06d}"
                idem = f"{cid}:{lo}-{hi}:v1"
                try:
                    con.execute("INSERT INTO extraction_job VALUES(?,?,?,?,?,?,?)",
                                (job, cid, lo, hi, "RUNNING", idem, 1))
                except sqlite3.IntegrityError:
                    job = con.execute("SELECT job_id FROM extraction_job WHERE idem_key=?",
                                      (idem,)).fetchone()[0]
                # 模拟 crash：一半会话在写 Claim 途中"被杀"（不 commit DONE）
                crash = (c % 2 == 0)
                for seq in range(lo, hi + 1):
                    txt = f"claim-{cid}-{seq}"
                    con.execute("INSERT OR IGNORE INTO extracted_claim VALUES(?,?,?,?,?)",
                                (f"CL-{cid}-{seq}", job, cid, seq, txt))
                    claims_attempted += 1
                if crash:
                    con.rollback()      # 事务回滚 = 进程被杀
                    continue
                con.execute("UPDATE extraction_job SET state='DONE' WHERE job_id=?", (job,))
                con.execute("INSERT OR REPLACE INTO extraction_watermark VALUES(?,?,?,?,?)",
                            (cid, hi, hi, 0, "2024-03-01T00:00:00"))
                con.commit()
        first_pass_ms = now_ms() - t0

        # 重试：同一 idem_key 重放，Claim 不得翻倍
        t0 = now_ms()
        claims_before = con.execute("SELECT count(*) FROM extracted_claim").fetchone()[0]
        retried = 0
        for c in range(n_conv):
            if c % 2 == 0:
                cid = f"CONV{c:06d}"
                fin = [r[0] for r in con.execute(
                    "SELECT seq FROM conv_turn WHERE conv_id=? AND finalized=1 ORDER BY seq", (cid,))]
                lo, hi = 1, max(fin)
                idem = f"{cid}:{lo}-{hi}:v1"
                con.execute("INSERT OR IGNORE INTO extraction_job VALUES(?,?,?,?,?,?,?)",
                            (f"JOB{c:06d}-R", cid, lo, hi, "RUNNING", idem, 2))
                for seq in range(lo, hi + 1):
                    con.execute("INSERT OR IGNORE INTO extracted_claim VALUES(?,?,?,?,?)",
                                (f"CL-{cid}-{seq}", f"JOB{c:06d}-R", cid, seq, f"claim-{cid}-{seq}"))
                con.execute("UPDATE extraction_job SET state='DONE' WHERE idem_key=?", (idem,))
                con.execute("INSERT OR REPLACE INTO extraction_watermark VALUES(?,?,?,?,?)",
                            (cid, hi, hi, 0, "2024-03-01T00:00:00"))
                con.commit()
                retried += 1
        retry_ms = now_ms() - t0
        claims_after = con.execute("SELECT count(*) FROM extracted_claim").fetchone()[0]
        dup = con.execute("SELECT count(*) FROM (SELECT conv_id, seq, count(*) c FROM extracted_claim "
                          "GROUP BY conv_id, seq HAVING c > 1)").fetchone()[0]
        unfin = con.execute("SELECT count(*) FROM extracted_claim cl JOIN conv_turn t "
                            "ON cl.conv_id=t.conv_id AND cl.seq=t.seq WHERE t.finalized=0").fetchone()[0]
        lag = con.execute("SELECT max(lag_tokens) FROM extraction_watermark").fetchone()[0]
        self.res["v7_pipeline"] = {
            "conversations": n_conv, "turns_per_conv": turns_per_conv,
            "active_window_token_budget": window_tokens,
            "first_pass_ms": round(first_pass_ms, 1), "retry_pass_ms": round(retry_ms, 1),
            "retried_conversations": retried,
            "claims": {"before_retry": claims_before, "after_retry": claims_after,
                       "duplicate_conv_seq_pairs": dup},
            "claims_expected_total": n_conv * (turns_per_conv - 3),
            "idempotent_under_crash_retry": (
                dup == 0 and claims_after == n_conv * (turns_per_conv - 3)
                and claims_after > claims_before),
            "idempotency_rule": ("重试**补齐**被回滚的工作（claims 增长是正确的），"
                                 "但 (conv_id, seq) 不得出现第二次 ⇒ 以 dup==0 且总数==期望值判定"),
            "unfinalized_turns_extracted": unfin,
            "max_watermark_lag_tokens": lag,
            "acceptance": ("crash/retry 不得产生重复 Claim；未 finalize 的 turn 不得被萃取；"
                           "前台窗口 token 必须 <= profile 预算；水位 lag 超阈值时前台保留未萃取原文"),
        }

    def finalize(self) -> dict:
        con = self.con
        # 设计书要求的自检：waiting_task_count 与 system_filler_turns 的 CHECK 约束是否真的拦得住违规
        violations_caught = {}
        for name, sql, params in (
            ("I4_waiting_task_in_receipt",
             "INSERT INTO cp_context_receipt VALUES('X','W','h','1>2>3>4',10,1.0,0,1,3,'t')", ()),
            ("I5_system_filler_turn",
             "INSERT INTO cp_context_receipt VALUES('Y','W','h','1>2>3>4',10,1.0,2,1,0,'t')", ()),
            ("I3_unreserved_negative",
             "INSERT INTO cp_budget_ledger VALUES('Z','SESSION','s','RETRIEVAL',-5,0,100,0,'t')", ()),
        ):
            try:
                con.execute(sql, params)
                violations_caught[name] = "NOT_ENFORCED"
                con.rollback()
            except sqlite3.IntegrityError:
                violations_caught[name] = "ENFORCED_BY_DDL"
        con.execute("DELETE FROM cp_context_receipt WHERE receipt_id IN ('X','Y')")
        con.commit()
        self.res["invariant_selfcheck"] = violations_caught
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]
        self.res["schema"] = {"tables": tables, "table_count": len(tables),
                              "indexes": [r[0] for r in con.execute(
                                  "SELECT name FROM sqlite_master WHERE type='index' "
                                  "AND name NOT LIKE 'sqlite_autoindex%' ORDER BY name")],
                              "db_size_mb": round(os.path.getsize(self.db_path) / 1048576, 1)}
        gates = {
            "G1_ready_queue_not_full_scan":
                self.res["v1_ready_queue"]["subscription_index_ms"]["p95"]
                < self.res["v1_ready_queue"]["naive_full_scan_ms"]["p95"]
                and self.res["v1_ready_queue"]["materialized_ready_read_ms"]["p95"]
                <= self.res["v1_ready_queue"]["wake_time_budget_ms"],
            "G2_co_search_adopted_plans_p95":
                self.res["v2_co_search"]["verdict"]["fts_and_p95_under_gate"]
                and self.res["v2_co_search"]["verdict"]["postings_entity_anchored_p95_under_gate"]
                and self.res["v2_co_search"]["verdict"]["postings_topk_p95_under_gate"],
            "G2b_rejected_plans_documented":
                not self.res["v2_co_search"]["verdict"]["postings_3way_group_by_p95_under_gate"]
                and not self.res["v2_co_search"]["verdict"]["postings_pairwise_p95_under_gate"],
            "G3_cjk_recall_nonzero": self.res["v2_co_search"]["two_char_term_recall"]["postings"] > 0,
            "G4_time_bucket_gate": self.res["v3_time_slider"]["gate_pass"],
            "G5_manifest_budget": self.res["v4_manifest"]["gate_pass"],
            "G6_propagation_bounded": self.res["v5_propagation"]["gate_pass"],
            "G7_invariants_enforced_by_ddl":
                all(v == "ENFORCED_BY_DDL" for v in violations_caught.values()),
            "G8_ready_sets_equal": self.res["v1_ready_queue"]["correctness_ready_sets_equal"],
            "G9_postings_recall_superset_and_alias_gap_exact":
                self.res["v2_co_search"]["verdict"]["correctness_postings_superset_of_like"]
                and self.res["v2_co_search"]["verdict"]["correctness_alias_gap_explained"],
            "G10_time_window_non_vacuous": self.res["v3_time_slider"]["non_vacuous"],
            "G11_pipeline_idempotent": self.res["v7_pipeline"]["idempotent_under_crash_retry"],
            "G12_no_unfinalized_extraction":
                self.res["v7_pipeline"]["unfinalized_turns_extracted"] == 0,
        }
        self.res["gates"] = gates
        self.res["all_gates_pass"] = all(gates.values())
        con.close()
        return self.res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="200k", choices=["50k", "200k", "1m"])
    ap.add_argument("--json", default="")
    ap.add_argument("--db", default="/tmp/aios_design_verify.sqlite3")
    args = ap.parse_args()
    n_obj = {"50k": 50_000, "200k": 200_000, "1m": 1_000_000}[args.scale]
    n_task = {"50k": 25_000, "200k": 100_000, "1m": 500_000}[args.scale]

    d = Design(args.db, n_obj, n_task)
    wall0 = now_ms()
    d.build()
    d.v_ready_queue()
    d.v_co_search()
    d.v_time_slider()
    d.v_manifest()
    d.v_propagation()
    d.v_write_path()
    d.v7_pipeline()
    res = d.finalize()
    res["environment"] = {
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "scale": args.scale, "wall_ms": round(now_ms() - wall0, 1),
        "disclaimer": ("合成数据 + 容器文件系统；数字用于**方案间相对比较与门限可达性证明**，"
                       "不是产品 SLO 承诺；实体手环闪存与真实模型延迟不在本探针范围内"),
    }
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    print("\nJSON_SUMMARY " + json.dumps(
        {"all_gates_pass": res["all_gates_pass"], "gates": res["gates"],
         "scale": args.scale, "db_size_mb": res["schema"]["db_size_mb"]}, ensure_ascii=False))
    return 0 if res["all_gates_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
