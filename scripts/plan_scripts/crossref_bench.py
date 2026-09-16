"""R4 线 vs V3 主干 cjk_inverted_index 同场对拍（接入提案的证据生成器）。

同一合成世界、同一查询集，各测：构建耗时、查询 p50/p95、行数足迹。
口径声明：主干核为实体级共现（返回 entity_id），我方核为文档修订级检索
（返回 object@revision + 水位三元组）——**召回语义不可比，延迟与足迹可比**。
本脚本只宣称可比部分；能力差异矩阵在提案正文里定性陈述。

用法: PYTHONPATH=src python scripts/plan_scripts/crossref_bench.py [--revisions 20000]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import zlib
import time
from pathlib import Path
from tempfile import mkdtemp

from aios_core.bench.g_m1p import Budget, _query_set, generate_world
from aios_core.query.cjk_inverted_index import CJKTopologicalInvertedIndex
from aios_core.query.search import WorldSearchIndex
import random


def pct(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(len(v) * p))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--revisions", type=int, default=20_000)
    ap.add_argument("--queries", type=int, default=240)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    db = Path(mkdtemp()) / "cross.db"
    t0 = time.perf_counter()
    stats = generate_world(db, a.revisions, seed=a.seed)
    gen_s = time.perf_counter() - t0

    queries = _query_set(random.Random(a.seed + 1), a.queries)

    # —— V3 主干核（实体级）：把世界文本按实体聚合喂入 ——
    from datetime import datetime, timezone
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT o.object_id, o.object_type, o.payload_json FROM object_revisions o "
            "WHERE o.revision=1"
        ).fetchall()
    event_to_entities = {}
    with sqlite3.connect(db) as conn:
        for r in conn.execute("SELECT object_id, payload_json FROM object_revisions WHERE object_type='event'"):
            payload = json.loads(r[1])
            for ref in payload.get("participant_refs", []):
                event_to_entities.setdefault(ref["object_id"], []).append(r[0])
    texts: dict[str, list[str]] = {}
    for oid, otype, pj in rows:
        try:
            payload = json.loads(pj)
        except json.JSONDecodeError:
            continue
        blob = json.dumps(payload, ensure_ascii=False)
        for ent in event_to_entities.get(oid, []) if otype == "event" else []:
            texts.setdefault(ent, []).append(blob)
        if otype == "claim":
            for m in ("妈妈", "母亲"):
                if m in blob:
                    texts.setdefault("entity_sports_anchor", []).append(blob)
                    break
    # 通用挂靠：所有文本挂到按编号哈希的 40 个虚拟实体上，保证负载规模一致（口径对等，非业务正确）
    for oid, otype, pj in rows:
        texts.setdefault(f"xent_{zlib.crc32(oid.encode()) % 40}", []).append(pj or "")
    ts = int(time.time() * 1e9)
    with sqlite3.connect(db) as conn:
        trunk = CJKTopologicalInvertedIndex(conn)
        t0 = time.perf_counter()
        items = [(e, "\n".join(parts)[:4000], ts) for e, parts in texts.items()]
        trunk.index_entity_texts_batch(items)
        trunk_build_s = time.perf_counter() - t0
        trunk_ms = []
        for q in queries:
            t1 = time.perf_counter()
            trunk.co_search(q)
            trunk_ms.append((time.perf_counter() - t1) * 1000)
        trunk_rows = conn.execute("SELECT COUNT(*) FROM topological_cjk_terms").fetchone()[0]

    # —— R4 核（文档修订级）——
    store = None
    from aios_core.storage import SQLiteWorldStore
    store = SQLiteWorldStore(db)
    mine = WorldSearchIndex(db, store=store)
    t0 = time.perf_counter()
    mine.rebuild()
    mine_build_s = time.perf_counter() - t0
    mine_ms = []
    for q in queries:
        t1 = time.perf_counter()
        mine.co_search(q, limit=20)
        mine_ms.append((time.perf_counter() - t1) * 1000)
    with sqlite3.connect(db) as conn:
        mine_rows = conn.execute("SELECT COUNT(*) FROM search_postings").fetchone()[0]

    # —— 粒度对等模式：每文档作为独立"实体"喂主干核（同规模倒排下的公平延迟对比）——
    conn = trunk.conn  # 复用主干核自己的连接，避免双连接写锁互踩
    conn.execute("DELETE FROM topological_cjk_terms")
    conn.commit()
    t0 = time.perf_counter()
    per_doc = [(oid, (pj or "")[:4000], ts) for oid, _otype, pj in rows]
    trunk.index_entity_texts_batch(per_doc)
    parity_build = time.perf_counter() - t0
    conn.commit()
    parity_ms = []
    for q in queries:
        t1 = time.perf_counter()
        trunk.co_search(q)
        parity_ms.append((time.perf_counter() - t1) * 1000)
    parity_rows = conn.execute("SELECT COUNT(*) FROM topological_cjk_terms").fetchone()[0]
    parity = {"build_seconds": round(parity_build, 2), "posting_rows": parity_rows,
              "query_ms": {"p50": round(pct(parity_ms, .5), 2), "p95": round(pct(parity_ms, .95), 2),
                           "n": len(parity_ms)},
              "note": "主干核按 1文档=1实体 重建索引后的同规模延迟；召回仍为 id 集合，无语义等价性主张"}

    report = {
        "world": {"revisions": stats["revisions"], "objects": stats["objects"], "generate_seconds": round(gen_s, 1),
                  "note": "同一合成世界喂两核；口径=延迟与足迹可比，召回语义不可比（实体级 vs 文档修订级）"},
        "trunk_cjk": {"build_seconds": round(trunk_build_s, 2), "posting_rows": trunk_rows,
                      "query_ms": {"p50": round(pct(trunk_ms, .5), 2), "p95": round(pct(trunk_ms, .95), 2),
                                   "n": len(trunk_ms)}},
        "r4_search": {"build_seconds": round(mine_build_s, 2), "posting_rows": mine_rows,
                      "query_ms": {"p50": round(pct(mine_ms, .5), 2), "p95": round(pct(mine_ms, .95), 2),
                                   "n": len(mine_ms)}},
        "parity_mode": parity,
        "capability_matrix_note": "水位/严格新鲜度、别名消歧不自动合并、时间透镜、双视图：仅 R4 核；实体共现边表：仅主干核",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if a.out:
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
