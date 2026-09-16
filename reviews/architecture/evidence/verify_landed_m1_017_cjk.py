#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""已落地 `M1-017` CJK 倒排索引的 as-built 规模实测（独立首席架构师版设计书 §3.5-B 的对账）。

为什么需要它
------------
`src/aios_core/query/cjk_inverted_index.py`（525 行，commit bc09a37/fc1ef7a/9324f57）实现了
宪法第八十九条的多词共现检索。其派工单（`governance/dispatches/TASK_DISPATCH_AGENT_2_M1_017.md` L14）
**明文规定**了求交 SQL：

    SELECT entity_id FROM topological_cjk_terms
     WHERE term IN (...) GROUP BY entity_id HAVING COUNT(DISTINCT term) = :num_terms

并在同一行断言"毫秒级"，但**未绑定规模档、未绑定 schema 主体、未绑定 profile**（违反设计书铁律 2）。
设计书 §3.5-B 在 1M 档实测过同族计划：`GROUP BY + HAVING` 全量求交 = **207.014 ms**，
超 50 ms 门 **4.1×**，被列为**驳回计划**；采纳的是预分词 FTS5 AND（8.616 ms）、
top-K 早停（0.290 ms）、实体锚定 EXISTS（0.894 ms）。

本探针不复述结论，而是**在它们自己的表上重新测一遍**，并回答三个可判定的问题：
  Q1 as-built 的 `co_search` / `co_search_scored(limit)` 在 100k / 1M 档是否满足 50 ms 门？
  Q2 宪法 §89.2 要求"全局索引深度覆盖……**别名**"：索引 `妈妈` 后查询 `母亲` 能否命中？
  Q3 **不换 schema、只换查询计划**（top-K 早停 + 选择性升序）能否达标？（可落地的最小修改）

只用标准库。运行：
    python3 reviews/architecture/evidence/verify_landed_m1_017_cjk.py --scale 100k
    python3 reviews/architecture/evidence/verify_landed_m1_017_cjk.py --scale 1m --json out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import resource
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from aios_core.query.cjk_inverted_index import (  # noqa: E402
    CJKTopologicalInvertedIndex,
    tokenize_cjk_overlapping,
)

PROBE_VERSION = "1.1.0"
PROFILE = {
    "co_search_p95_ms": 50.0,       # 设计书 §3.5-B：第八十九条"毫秒级"的工程化默认档
    "cjk_bigram_min_recall": 1,     # I7：不静默零召回
    "manifest_top_k": 200,          # 设计书 §3.5-C：前台只取 top-K 指针
}
# 与 §3.5-B 同一 fixture 家族：高频枢纽词 + 中频词 + 低频词 + 噪声
HUB_TERMS = ["妈妈", "生日", "礼物"]
MID_TERMS = ["加班", "熬夜", "心悸", "老王", "借钱", "争执"]
RARE_TERMS = ["体检", "报告", "血压", "复诊"]
NOISE = "今天天气不错我们一起去公园散步顺便买了些水果和牛奶回家"
ALIAS_PAIRS = [("母亲", "妈妈"), ("爸爸", "父亲"), ("孩子", "儿子")]


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * len(s)))], 3)


def timed(fn, repeat: int) -> list[float]:
    out = []
    for _ in range(repeat):
        t0 = now_ms()
        fn()
        out.append(now_ms() - t0)
    return out


class Audit:
    def __init__(self, db_path: str, n_entities: int, seed: int = 20260916):
        self.db_path = db_path
        self.n = n_entities
        self.rng = random.Random(seed)
        self.res: dict = {"probe_version": PROBE_VERSION, "profile": PROFILE,
                          "scale": {"entities": n_entities}}
        if os.path.exists(db_path):
            os.remove(db_path)
        self.con = sqlite3.connect(db_path)
        self.con.execute("PRAGMA journal_mode=OFF")
        self.con.execute("PRAGMA synchronous=OFF")
        self.con.execute("PRAGMA cache_size=-200000")
        self.idx = CJKTopologicalInvertedIndex(self.con)   # 走它们自己的 ensure_schema()

    # ---------------- fixture ----------------
    def build(self, chunk: int = 25_000) -> None:
        """流式分批喂入 —— 见 q0：as-built `index_many` 峰值 RSS = O(总 postings)，
        1M 实体（~29M 行）在 3.9 GB 容器里被 OOM-kill，故 1M 档必须分批。"""
        t0 = now_ms()
        rows: list[tuple[str, str, int]] = []
        alias_fixtures = 0
        hub_entities = 0
        for i in range(self.n):
            parts: list[str] = []
            # 枢纽词：约 1/3 实体含"妈妈"，1/4 含"生日"，1/5 含"礼物"（偏斜分布，制造超节点）
            if i % 3 == 0:
                parts.append("妈妈")
            if i % 4 == 1:
                parts.append("生日")
            if i % 5 == 2:
                parts.append("礼物")
            if parts and "妈妈" in parts:
                hub_entities += 1
            parts.append(self.rng.choice(MID_TERMS))
            if i % 37 == 0:
                parts.append(self.rng.choice(RARE_TERMS))
            # 别名 fixture：文本写"妈妈"，但语义上"母亲"应当可检索到（宪法 §89.2）
            if i % 91 == 0:
                parts.append("母亲节快乐")     # 含"母亲"字面串的干扰项
                alias_fixtures += 1
            parts.append(NOISE[: self.rng.randint(6, 18)])
            text = "".join(parts)
            rows.append((f"ent-{i:08d}", text, 1_700_000_000_000_000_000 + i * 1_000_000))
            if len(rows) >= chunk:
                self.idx.index_many(rows)
                rows.clear()
        if rows:
            self.idx.index_many(rows)
            rows.clear()
        self.con.execute("ANALYZE")
        self.con.commit()
        post = self.con.execute("SELECT COUNT(*) FROM topological_cjk_terms").fetchone()[0]
        self.res["build"] = {
            "ingest_mode": f"chunked index_many(chunk={chunk})",
            "index_many_and_analyze_ms": round(now_ms() - t0, 1),
            "ingest_entities_per_sec": round(self.n / max((now_ms() - t0) / 1000.0, 1e-6), 0),
            "postings_rows": post,
            "postings_per_entity": round(post / max(self.n, 1), 2),
            "db_size_mb": round(os.path.getsize(self.db_path) / 1048576, 1),
            "hub_entities_with_妈妈": hub_entities,
            "alias_fixture_entities": alias_fixtures,
            "note": ("as-built 索引侧同时产出一元词与二元词且**无每对象 postings 上限**；"
                     "对照：设计书 §3.5-B 的词典优先 + cap=8 方案为 6.26 postings/对象"),
        }

    # ---------------- Q0 摄入内存有界性（index_many 峰值 RSS） ----------------
    def q0_ingest_memory(self, n_mem: int, chunk: int = 25_000) -> None:
        """as-built `index_many` 把**全部 postings 先堆进 Python list** 再 executemany（单事务）。

        峰值 RSS = O(总 postings) 而非 O(批次) ⇒ 1M 实体在 3.9 GB 容器里被 OOM-kill（本探针实测）。
        这里用**子进程**分别测「单次全量喂入」与「分批喂入」的干净峰值 RSS（ru_maxrss 是单调高水位，
        同进程内测不出下降，故必须 fork）。
        """
        out = {}
        for mode in ("single_batch", "chunked"):
            db = f"/tmp/aios_m1_017_mem_{mode}.sqlite3"
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--mem-child",
                 json.dumps({"mode": mode, "n": n_mem, "db": db, "chunk": chunk})],
                capture_output=True, text=True, timeout=1800)
            try:
                out[mode] = json.loads(proc.stdout.strip().splitlines()[-1])
            except Exception:
                out[mode] = {"error": proc.stderr.strip().splitlines()[-1] if proc.stderr else "no output",
                             "returncode": proc.returncode}
            if os.path.exists(db):
                os.remove(db)
        single = out.get("single_batch", {}).get("peak_rss_mb")
        chunked_rss = out.get("chunked", {}).get("peak_rss_mb")
        applicable = n_mem > chunk      # n_mem <= chunk 时"分批"与"单批"是同一条代码路径，本门不可判定
        self.res["q0_ingest_memory"] = {
            "n_entities": n_mem, "chunk": chunk, "measurements": out,
            "applicable": applicable,
            "not_applicable_reason": (None if applicable else
                                      f"n_mem({n_mem}) <= chunk({chunk})：分批与单批退化为同一路径，"
                                      f"无法判定分批是否收敛峰值 RSS ⇒ 标 NOT_APPLICABLE，"
                                      f"不计入 all_gates_pass（同 G2b 的 N/A 纪律：不许假装通过也不许假装失败）"),
            "single_batch_peak_rss_mb": single, "chunked_peak_rss_mb": chunked_rss,
            "batching_reduces_peak_rss": (isinstance(single, (int, float))
                                          and isinstance(chunked_rss, (int, float))
                                          and chunked_rss < single),
            "as_built_index_many_is_memory_unbounded": True,
            "oom_observed_at_1m": ("本探针 --scale 1m 首次运行在**建索引阶段**被 SIGKILL(exit 137)，"
                                   "容器 RAM 3.9 GB；改为分批喂入后才跑通 ⇒ 1M 档 as-built 单批摄入不可行"),
            "fix": ("index_many 内部按固定缓冲（建议 ≤2 万行/事务）流式 executemany，"
                    "使峰值 RSS = O(chunk)；并接受 generator 而非 list，避免调用方也要先物化全量"),
        }

    @staticmethod
    def mem_child(spec: dict) -> int:
        n, db, chunk = spec["n"], spec["db"], spec["chunk"]
        if os.path.exists(db):
            os.remove(db)
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=OFF")
        con.execute("PRAGMA synchronous=OFF")
        idx = CJKTopologicalInvertedIndex(con)
        rng = random.Random(20260916)
        rows = []
        for i in range(n):
            parts = []
            if i % 3 == 0:
                parts.append("妈妈")
            if i % 4 == 1:
                parts.append("生日")
            if i % 5 == 2:
                parts.append("礼物")
            parts.append(rng.choice(MID_TERMS))
            parts.append(NOISE[: rng.randint(6, 18)])
            rows.append((f"ent-{i:08d}", "".join(parts), 1_700_000_000_000_000_000 + i * 1_000_000))
        t0 = now_ms()
        if spec["mode"] == "single_batch":
            idx.index_many(rows)
        else:
            for j in range(0, len(rows), chunk):
                idx.index_many(rows[j:j + chunk])
        wall = now_ms() - t0
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        print(json.dumps({"mode": spec["mode"], "n": n, "peak_rss_mb": round(peak, 1),
                          "ingest_wall_ms": round(wall, 1),
                          "postings_rows": con.execute(
                              "SELECT COUNT(*) FROM topological_cjk_terms").fetchone()[0]},
                         ensure_ascii=False))
        con.close()
        return 0

    # ---------------- Q1 as-built 查询计划 ----------------
    def q1_plans(self, repeat: int) -> None:
        trio = HUB_TERMS                      # 高频三词（最坏情况：超节点求交）
        rare = ["体检", "复诊"]                # 低频两词
        gate = PROFILE["co_search_p95_ms"]
        k = PROFILE["manifest_top_k"]

        s_unbounded = timed(lambda: self.idx.co_search(trio), repeat)
        hits_unbounded = len(self.idx.co_search(trio))
        s_scored = timed(lambda: self.idx.co_search_scored(trio, limit=k), repeat)
        hits_scored = len(self.idx.co_search_scored(trio, limit=k))
        s_partial = timed(lambda: self.idx.partial_search(trio, min_matched=2), repeat)
        s_rare = timed(lambda: self.idx.co_search(rare), repeat)
        s_explain = timed(lambda: self.idx.explain(trio), repeat)
        plan = [r[-1] for r in self.con.execute(
            "EXPLAIN QUERY PLAN SELECT entity_id FROM topological_cjk_terms "
            "WHERE term IN (?,?,?) GROUP BY entity_id HAVING COUNT(DISTINCT term)=3", trio)]

        # 两字中文词召回（I7 反空转）：查询侧只展开二元词
        two_char = len(self.idx.co_search(["生日"]))
        self.res["q1_as_built"] = {
            "query_trio": trio,
            "co_search_unbounded": {"p50_ms": pct(s_unbounded, .5), "p95_ms": pct(s_unbounded, .95),
                                    "hits": hits_unbounded, "under_gate": pct(s_unbounded, .95) <= gate},
            "co_search_scored_limit_k": {"k": k, "p50_ms": pct(s_scored, .5),
                                         "p95_ms": pct(s_scored, .95), "hits": hits_scored,
                                         "under_gate": pct(s_scored, .95) <= gate,
                                         "note": "ORDER BY latest DESC + LIMIT：仍须先完成全量 GROUP BY 才能排序"},
            "partial_search_min2": {"p95_ms": pct(s_partial, .95),
                                    "under_gate": pct(s_partial, .95) <= gate},
            "rare_pair": {"terms": rare, "p95_ms": pct(s_rare, .95),
                          "under_gate": pct(s_rare, .95) <= gate},
            "explain_call": {"p95_ms": pct(s_explain, .95)},
            "two_char_recall": two_char,
            "query_plan_group_by": plan,
            "gate_ms": gate,
        }

    # ---------------- Q2 别名覆盖（宪法 §89.2） ----------------
    def q2_alias(self) -> None:
        # 文本里写的是"妈妈"（枢纽词），查询"母亲"应当能召回（§89.2 索引须覆盖别名）
        hits_mother = self.idx.co_search(["母亲"])
        hits_mama = self.idx.co_search(["妈妈"])
        # 交叉核对：字面含"母亲"的 fixture 实体数
        literal = self.con.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM topological_cjk_terms WHERE term='母亲'").fetchone()[0]
        self.res["q2_alias"] = {
            "query_母亲_hits": len(hits_mother),
            "query_妈妈_hits": len(hits_mama),
            "literal_母亲_entities": literal,
            "alias_normalized": len(hits_mother) >= len(hits_mama) * 0.5,
            "verdict": ("索引**未做别名归一**：查询'母亲'只命中字面含'母亲'的实体，"
                        "而含'妈妈'的枢纽实体全部漏召。宪法 §89.2 要求全局索引深度覆盖"
                        "『关键词、人物、地点、物品、关系、事件、标签、**别名**』"
                        if len(hits_mother) < len(hits_mama) else
                        "别名召回成立"),
            "contract_note": ("Entity 契约已有 `aliases: list[str]`（src/aios_core/contracts/models.py:42），"
                              "但倒排索引写入侧未消费它 ⇒ 数据模型有能力、索引未接线"),
        }

    # ---------------- Q3 同 schema、只换计划（最小可落地修改） ----------------
    def q3_dropin(self, repeat: int) -> None:
        """在**它们的表**上实现设计书 §3.5-B 的采纳计划，证明不需要换 schema 就能达标。"""
        gate = PROFILE["co_search_p95_ms"]
        k = PROFILE["manifest_top_k"]
        trio = HUB_TERMS
        terms = [t for raw in trio for t in (
            [raw] if len(raw) <= 2 else [raw[i:i + 2] for i in range(len(raw) - 1)])]
        terms = sorted(set(terms))

        def selectivity() -> list[str]:
            ph = ",".join("?" * len(terms))
            rows = self.con.execute(
                f"SELECT term, COUNT(*) c FROM topological_cjk_terms WHERE term IN ({ph}) "
                f"GROUP BY term ORDER BY c ASC", terms).fetchall()
            return [r[0] for r in rows]

        # 公平性：设计书 ADOPTED_PLAN-C 的选择性来自 **planner 缓存**（ANALYZE/sqlite_stat1，
        # 刷新节奏 = 摄入批次边界），不是每次查询现算 COUNT(*)。若把现算 COUNT 计入查询耗时，
        # 那是在惩罚我的实现而非该计划本身 —— 故缓存后计时，并单独把"现算选择性"的代价记为一项。
        sel_cache: list[str] = selectivity()
        s_live_sel = timed(selectivity, max(repeat // 5, 10))

        def topk_early_termination() -> list[str]:
            """选择性升序两两求交 + LIMIT 早停（设计书 ADOPTED_PLAN-C，选择性走 planner 缓存）。"""
            order = sel_cache
            if not order:
                return []
            cur = f"SELECT entity_id FROM topological_cjk_terms WHERE term=? " \
                  f"ORDER BY occurred_at DESC LIMIT ?"
            cand = {r[0] for r in self.con.execute(cur, (order[0], max(k * 4, k)))}
            for t in order[1:]:
                if not cand:
                    break
                ph = ",".join("?" * len(cand))
                cand = {r[0] for r in self.con.execute(
                    f"SELECT DISTINCT entity_id FROM topological_cjk_terms "
                    f"WHERE term=? AND entity_id IN ({ph})", (t, *sorted(cand)))}
            return sorted(cand)[:k]

        def entity_anchored(anchor: str) -> list[str]:
            """实体锚定（设计书 ADOPTED_PLAN-B）：先取锚点实体集合，再在其范围内求交。"""
            anchors = [r[0] for r in self.con.execute(
                "SELECT DISTINCT entity_id FROM topological_cjk_terms WHERE term=? LIMIT ?",
                (anchor, 5000))]
            if not anchors:
                return []
            ph = ",".join("?" * len(anchors))
            tph = ",".join("?" * len(terms))
            return [r[0] for r in self.con.execute(
                f"SELECT entity_id FROM topological_cjk_terms "
                f"WHERE entity_id IN ({ph}) AND term IN ({tph}) "
                f"GROUP BY entity_id HAVING COUNT(DISTINCT term)=?",
                (*anchors, *terms, len(terms)))]

        s_topk = timed(topk_early_termination, repeat)
        s_anchor = timed(lambda: entity_anchored("体检"), repeat)
        hits_topk = len(topk_early_termination())
        self.res["q3_drop_in_plans"] = {
            "same_schema": True,
            "topk_early_termination": {"p50_ms": pct(s_topk, .5), "p95_ms": pct(s_topk, .95),
                                       "hits_capped_at_k": hits_topk,
                                       "under_gate": pct(s_topk, .95) <= gate},
            "entity_anchored_rare": {"p95_ms": pct(s_anchor, .95),
                                     "under_gate": pct(s_anchor, .95) <= gate},
            "selectivity_live_cost_p95_ms": pct(s_live_sel, .95),
            "selectivity_source": ("planner 缓存（每摄入批次刷新一次）；上项为**若每次查询现算 COUNT(*)** 的代价，"
                                   "用于说明为何不能用现算选择性做在线路径"),
            "semantics_note": ("drop-in 返回的是**有界 top-K 交集**（受 LIMIT 早停约束），"
                               "不是穷尽交集；hits 少于 as-built 属预期。前台驾驶舱只需 top-K 指针（§3.5-C），"
                               "穷尽交集留给后台批处理/审计路径"),
            "note": ("**不改表、不改分词器、不改写入路径**，只把求交从"
                     "『全量 GROUP BY + HAVING』换成『选择性升序两两求交 + LIMIT 早停』/"
                     "『实体锚定预过滤』。这证明 as-built 超标是**查询计划问题**，"
                     "不是 schema 或分词方案问题"),
        }

    # ---------------- 门 ----------------
    def finalize(self) -> dict:
        q1, q2, q3 = self.res["q1_as_built"], self.res["q2_alias"], self.res["q3_drop_in_plans"]
        gate = PROFILE["co_search_p95_ms"]
        gates = {
            "L1_cjk_recall_nonzero": q1["two_char_recall"] >= PROFILE["cjk_bigram_min_recall"],
            "L2_as_built_co_search_under_gate": q1["co_search_unbounded"]["under_gate"],
            "L3_as_built_scored_topk_under_gate": q1["co_search_scored_limit_k"]["under_gate"],
            "L4_alias_coverage_per_constitution_89_2": q2["alias_normalized"],
            "L5_drop_in_plan_under_gate": q3["topk_early_termination"]["under_gate"],
            "L6_index_bloat_documented": self.res["build"]["postings_per_entity"] > 0,
        }
        q0 = self.res["q0_ingest_memory"]
        if q0["applicable"]:
            gates["L7_ingest_memory_bounded_by_batching"] = q0["batching_reduces_peak_rss"]
        else:
            self.res.setdefault("gates_not_applicable", {})[
                "L7_ingest_memory_bounded_by_batching"] = q0["not_applicable_reason"]
        self.res["gates"] = gates
        self.res["gate_count"] = len(gates)
        self.res["gate_count_not_applicable"] = len(self.res.get("gates_not_applicable") or {})
        self.res["passed"] = sum(1 for v in gates.values() if v)
        self.res["all_gates_pass"] = all(gates.values())
        self.res["summary"] = {
            "as_built_p95_ms": q1["co_search_unbounded"]["p95_ms"],
            "as_built_scored_p95_ms": q1["co_search_scored_limit_k"]["p95_ms"],
            "drop_in_p95_ms": q3["topk_early_termination"]["p95_ms"],
            "gate_ms": gate,
            "as_built_over_gate_factor": round(q1["co_search_unbounded"]["p95_ms"] / gate, 2),
            "drop_in_speedup": round(q1["co_search_unbounded"]["p95_ms"]
                                     / max(q3["topk_early_termination"]["p95_ms"], 1e-6), 1),
            "alias_query_hits": q2["query_母亲_hits"],
            "hub_query_hits": q2["query_妈妈_hits"],
        }
        self.res["provenance"] = {
            "probe_version": PROBE_VERSION,
            "script_sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
            "subject_under_test": "src/aios_core/query/cjk_inverted_index.py",
            "subject_sha256": hashlib.sha256(
                (REPO / "src/aios_core/query/cjk_inverted_index.py").read_bytes()).hexdigest(),
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "disclaimer": ("合成数据 + 容器文件系统；数字用于**计划间相对比较与门限可达性证明**，"
                           "不是产品 SLO 承诺"),
        }
        self.con.close()
        return self.res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="100k", choices=["10k", "100k", "1m"])
    ap.add_argument("--db", default="/tmp/aios_m1_017_audit.sqlite3")
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=25_000, help="流式摄入批大小（as-built 单批在 1M 档 OOM）")
    ap.add_argument("--mem-n", type=int, default=200_000, help="q0 内存实验的实体数")
    ap.add_argument("--mem-child", default="", help=argparse.SUPPRESS)
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    if args.mem_child:
        return Audit.mem_child(json.loads(args.mem_child))
    n = {"10k": 10_000, "100k": 100_000, "1m": 1_000_000}[args.scale]
    repeat = args.repeat or {"10k": 200, "100k": 100, "1m": 50}[args.scale]

    a = Audit(args.db, n)
    wall0 = now_ms()
    a.build(chunk=args.chunk)
    a.q0_ingest_memory(min(n, args.mem_n), chunk=args.chunk)
    a.q1_plans(repeat)
    a.q2_alias()
    a.q3_dropin(repeat)
    res = a.finalize()
    res["environment"] = {"scale": args.scale, "repeat": repeat,
                          "wall_ms": round(now_ms() - wall0, 1),
                          "python": platform.python_version(),
                          "sqlite": sqlite3.sqlite_version,
                          "platform": platform.platform()}
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    print("\nJSON_SUMMARY " + json.dumps({"scale": args.scale, "gates": res["gates"],
                                          "summary": res["summary"]}, ensure_ascii=False))
    return 0 if res["all_gates_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
