"""G-M1P：M1 规模冒烟 Gate 套件（检索 / 下钻 / 重建 / 追赶，三点位一致口径）。

设计书 R4 §3.4-T2 的 H 验收：p95 ≤ 50ms @ 50 万修订，且 G-M1P / M4a /
M7-002 三点位一致（±20%）。本模块是"预置压测件"：Gate 前把生成器、点位、
物理计划断言、报告格式全部固化并靠降规模冒烟保持常热；Gate 后只差一条命令。

教义约束（写进断言，不靠自觉）：
- 禁 payload 扫描 / 禁 LIKE 兜底 —— 对内核源码静态扫描；
- postings 与 finalize join 必须走索引 —— EXPLAIN QUERY PLAN 动态断言
  （finalize 的 SQL 形态与内核源码逐行对锁，防"基准测的是另一条查询"）；
- 迟到数据：adaptive 追赶在 ≤2000 修订内有硬预算；strict 必须立刻回
  stale_index（不许旧索引装新）。
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from aios_core.contracts import (
    Claim,
    ClaimType,
    Entity,
    EventAnchor,
    KnowledgeState,
    ObjectRef,
    Observation,
    OperationRequest,
    SourceClass,
    Task,
    TaskType,
    TemporalExtent,
    new_object_id,
)
from aios_core.query.search import WorldSearchIndex
from aios_core.storage import SQLiteWorldStore

SEED = 20260916
BASE_TIME = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

# 词表：前 8 词高权重（保证 [妈妈,生日,礼物] 类标准查询有真共现密度），
# 其余低频铺背景噪音——全词等权会测出假绿。
_CORE_WORDS = ["妈妈", "生日", "礼物", "保温杯", "围巾", "蛋糕", "公园", "阳台"]
_TAIL_WORDS = [
    "快递", "雨伞", "地铁", "夜班", "咖啡", "钥匙", "感冒", "体检", "花束", "相册",
    "门禁", "暖气", "疫苗", "牙套", "驾照", "报销", "租房", "续约", "巡检", "浇水",
]
_ASCII_WORDS = ["gift", "budget", "reminder"]


@dataclass(frozen=True)
class Budget:
    """降规模 CI 与正式 Gate 各自实例化；数字来源标注在报告里。"""

    search_p95_ms: float = 50.0
    drill_p95_ms: float = 50.0
    catchup_ms_per_revision: float = 8.0
    strict_stale_max_ms: float = 50.0


@dataclass
class Point:
    n: int = 0
    samples_ms: list[float] = field(default_factory=list)

    def percentiles(self) -> dict[str, float]:
        v = sorted(self.samples_ms)
        if not v:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}

        def q(p: float) -> float:
            i = min(len(v) - 1, int(len(v) * p))
            return round(v[i], 3)

        return {"p50": q(0.50), "p95": q(0.95), "p99": q(0.99), "max": round(v[-1], 3)}


def _measure(fn: Callable[[], Any], n: int, out: Point) -> Any:
    last: Any = None
    for _ in range(n):
        t0 = time.perf_counter()
        last = fn()
        out.samples_ms.append((time.perf_counter() - t0) * 1000.0)
        out.n += 1
    return last


def _text(rng: random.Random) -> str:
    pool = _CORE_WORDS * 3 + _TAIL_WORDS + _ASCII_WORDS
    parts = [rng.choice(pool) for _ in range(rng.randint(2, 9))]
    return "，".join(parts)


def _world_op(store: SQLiteWorldStore, name: str, key: str, source: SourceClass) -> OperationRequest:
    return OperationRequest(
        operation_name=name,
        expected_world_revision=store.current_world_revision(),
        reason="g_m1p synthetic generator",
        idempotency_key=key,
        source_class=source,
    )


def generate_world(db_path: Path, revisions: int, *, seed: int = SEED) -> dict[str, Any]:
    """确定性合成 50 万（或降规模）世界修订。objects/rev ≈ 1.4，含实体-ref 图。"""

    rng = random.Random(seed)
    store = SQLiteWorldStore(db_path)
    with sqlite3.connect(db_path) as warm:
        warm.execute("PRAGMA synchronous=OFF")  # 基准库不是真相库，速度换纪律
    entity_ids: list[str] = []
    built = {"entities": 0, "objects": 0}

    if store.current_world_revision() > 0:
        return _seed_and_fill(store, rng, revisions, entity_ids=[], built={"entities": 0, "objects": 0})

    # 先立实体（0 号 = 标准查询锚点：妈妈/母亲）
    anchor = Entity(
        object_id=new_object_id("entity"), subject_id="bench-user", learned_at=BASE_TIME,
        recorded_at=BASE_TIME, created_by="g_m1p", entity_kind="person",
        canonical_name="妈妈", aliases=["母亲", "老妈"],
    )
    store.commit([anchor], _world_op(store, "entity.upsert", "bench-e0", SourceClass.USER))
    entity_ids.append(anchor.object_id)
    built["entities"] += 1

    for i in range(1, min(max(2, revisions // 8), 800)):  # 实体占比 ≤1/8，小库也必有对象层
        ent = Entity(
            object_id=new_object_id("entity"), subject_id="bench-user", learned_at=BASE_TIME,
            recorded_at=BASE_TIME, created_by="g_m1p", entity_kind="person",
            canonical_name=f"人物{i:04d}", aliases=[f"小{i:04d}"],
        )
        store.commit([ent], _world_op(store, "entity.upsert", f"bench-e{i}", SourceClass.USER))
        entity_ids.append(ent.object_id)
        built["entities"] += 1

    return _fill(store, rng, revisions, entity_ids, built)


def _seed_and_fill(store, rng, revisions, entity_ids, built):
    return _fill(store, rng, revisions, entity_ids, built)


def _fill(store, rng, revisions, entity_ids, built):
    entity_ids = list(entity_ids) or [
        row[0] for row in []
    ]
    if not entity_ids:  # 注入轮：复用既有实体编号
        with sqlite3.connect(store.db_path) as conn:
            ent_rows = conn.execute(
                "SELECT DISTINCT object_id FROM object_revisions WHERE object_type='entity' LIMIT 800"
            ).fetchall()
            if not ent_rows:
                ent_rows = [("missing",)]
        entity_ids = [r[0] for r in ent_rows]
    start = store.current_world_revision()
    for r in range(start, revisions):
        at = BASE_TIME + timedelta(seconds=r * 3)
        objs: list[Any] = []
        kind = rng.choices(["observation", "claim", "event", "task"], weights=[55, 20, 18, 7])[0]
        common = dict(subject_id="bench-user", learned_at=at, recorded_at=at, created_by="g_m1p")
        if kind == "observation":
            objs.append(Observation(object_id=new_object_id("observation"), source_kind="ambient_audio",
                                    modality="text", value=_text(rng), occurred=TemporalExtent.point(at), **common))
        elif kind == "claim":
            hit = rng.random() < 0.35  # 妈妈锚点密度：claim 的 35% 含标准三元组
            content = (f"妈妈想要{rng.choice(['保温杯', '围巾', '蛋糕'])}当生日礼物" if hit else _text(rng))
            objs.append(Claim(object_id=new_object_id("claim"), claimant_id="bench-user", claim_type=ClaimType.DESIRE,
                              content=content, asserted_at=at, knowledge_state=KnowledgeState.REPORTED,
                              confidence=round(rng.uniform(0.4, 0.99), 2), **common))
            objs.append(obs_noise(rng, at)) if rng.random() < 0.4 else None
        elif kind == "event":
            parts = rng.sample(entity_ids, k=min(len(entity_ids), rng.randint(1, 3)))
            objs.append(EventAnchor(
                object_id=new_object_id("event"), title=f"事件{r:06d}：{_text(rng)}",
                interpretation="合成基准事件叙述", event_time=TemporalExtent.point(at + timedelta(hours=rng.randint(-48, 48))),
                participant_refs=[ObjectRef(object_id=p, revision=1) for p in parts],
                confidence=round(rng.uniform(0.5, 0.99), 2), **common))
        else:
            objs.append(Task(object_id=new_object_id("task"), task_type=rng.choice(list(TaskType)),
                             title=f"待办{r:06d}：{_text(rng)}", **common))
        built["objects"] += len(objs)
        store.commit(objs, _world_op(store, f"bench.{kind}", f"bench-r{r}", SourceClass.SENSOR))
    return {"revisions": store.current_world_revision(), **built}


def obs_noise(rng: random.Random, at: datetime) -> Observation:
    return Observation(object_id=new_object_id("observation"), subject_id="bench-user",
                       learned_at=at, recorded_at=at, created_by="g_m1p", source_kind="ambient_audio",
                       modality="text", value=_text(rng), occurred=TemporalExtent.point(at))


def _query_set(rng: random.Random, n: int) -> list[list[str]]:
    queries = [["妈妈", "生日", "礼物"]] * max(1, n // 6)
    while len(queries) < n:
        k = rng.randint(2, 3)
        queries.append([rng.choice(_CORE_WORDS) for _ in range(k)])
    rng.shuffle(queries)
    return queries


def _walk_ref_ids(node: Any):
    if isinstance(node, dict):
        oid = node.get("object_id")
        if isinstance(oid, str):
            yield oid
        for v in node.values():
            yield from _walk_ref_ids(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_ref_ids(v)


def plan_checks(db_path: Path) -> dict[str, Any]:
    """物理计划 + 源码纪律三重断言（T2-I 的机械执法）。"""

    import importlib.util
    origin = importlib.util.find_spec("aios_core.query.search").origin
    src = Path(origin).read_text(encoding="utf-8")
    finalize_shape = (
        "FROM search_candidates c\n"
        "            JOIN search_occurred o ON o.object_id = c.object_id AND o.revision = c.revision"
    )
    out = {
        "kernel_finalize_shape_locked": finalize_shape in src,
        "no_sql_like": not re.search(r"\bLIKE\b", src),
        "no_truth_table_query": not re.search(r"(?:FROM|JOIN)\s+(?:world_objects|object_revisions)", src),
    }
    with sqlite3.connect(db_path) as conn:
        plan = [row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT object_id, revision, COUNT(*) FROM search_postings "
            "WHERE token IN (?,?) GROUP BY object_id, revision", ("妈妈", "生日"))]
        out["postings_uses_index"] = any("USING" in p for p in plan) and not any(
            re.search(r"SCAN search_postings", p) for p in plan)
        conn.execute("CREATE TEMP TABLE search_candidates(object_id TEXT NOT NULL, revision INTEGER NOT NULL,"
                     "PRIMARY KEY(object_id, revision)) WITHOUT ROWID")
        conn.executemany("INSERT INTO search_candidates VALUES (?,?)", [("x", 1), ("y", 2)])
        plan2 = [row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT o.object_id FROM search_candidates c "
            "JOIN search_occurred o ON o.object_id=c.object_id AND o.revision=c.revision "
            "JOIN search_doc d ON d.object_id=o.object_id AND d.revision=o.revision")]
        out["finalize_join_uses_pk"] = not any(
            re.search(r"SCAN (?:search_occurred|search_doc)", p) for p in plan2)
        out["plans"] = {"postings": plan, "finalize": plan2}
    out["verdict"] = all(out[k] for k in ("kernel_finalize_shape_locked", "no_sql_like",
                                          "no_truth_table_query", "postings_uses_index", "finalize_join_uses_pk"))
    return out


def consistency_ok(p95s: dict[str, float | None], tolerance: float = 0.2) -> dict[str, Any]:
    """R4-02 三点位一致：任一为 None = pending；极差比 ≤ tolerance。"""

    vals = {k: v for k, v in p95s.items() if v is not None}
    if len(vals) < 2:
        return {"verdict": "pending_followup", "compared": vals}
    lo, hi = min(vals.values()), max(vals.values())
    ratio = (hi / lo - 1.0) if lo > 0 else float("inf")
    return {"verdict": "ok" if ratio <= tolerance else "drift",
            "ratio": round(ratio, 4), "tolerance": tolerance, "compared": vals}


def run_bench(db_path: Path, *, queries: int = 600, budget: Budget = Budget(),
              seed: int = SEED, revisions_target: int | None = None,
              late_revisions: int = 2000) -> dict[str, Any]:
    rng = random.Random(seed + 1)
    store = SQLiteWorldStore(db_path)
    index = WorldSearchIndex(db_path, store=store)

    t0 = time.perf_counter()
    n_obj = index.rebuild()
    rebuild_s = time.perf_counter() - t0

    search_pt, drill_pt = Point(), Point()
    qset = _query_set(rng, queries)
    last_hits: list[Any] = []
    qi = {"i": 0}

    def one_search():
        q = qset[qi["i"] % queries]
        qi["i"] += 1
        nonlocal last_hits
        page = index.co_search(q, limit=20)
        last_hits = page.hits
        return page

    _measure(one_search, queries, search_pt)

    def one_drill():
        if not last_hits:
            return None
        h = last_hits[rng.randrange(len(last_hits))]
        payload = store.get_payload(h.object_id)
        seen = []
        for rid in _walk_ref_ids(payload):
            if rid != h.object_id and rid not in seen:
                seen.append(rid)
            if len(seen) >= 8:
                break
        for rid in seen:
            store.get_payload(rid)
        return seen

    _measure(one_drill, max(50, queries // 4), drill_pt)

    # 迟到数据：2000 修订增量 → strict 立回 stale；adaptive 追赶有每修订预算
    late_n = late_revisions
    t0 = time.perf_counter()
    generate_world(db_path, store.current_world_revision() + late_n, seed=seed + 7)
    inject_s = time.perf_counter() - t0
    lag = index.lag()
    t0 = time.perf_counter()
    strict = index.co_search(["妈妈", "生日"], strict_freshness=True)
    strict_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    adaptive = index.co_search(["妈妈", "生日"], strict_freshness=False)
    catch_ms = (time.perf_counter() - t0) * 1000

    hot_status = "not_implemented"
    try:
        import importlib.util
        if importlib.util.find_spec("aios_core.query.hot_cards") is not None:
            hot_status = "present_unbenchmarked"  # 020a-d 落地后本行升级为计时点
    except ModuleNotFoundError:
        pass

    sp = search_pt.percentiles()
    dp = drill_pt.percentiles()
    failures = []
    if sp["p95"] > budget.search_p95_ms:
        failures.append(f"search p95 {sp['p95']}ms > {budget.search_p95_ms}ms")
    if dp["p95"] > budget.drill_p95_ms:
        failures.append(f"drill p95 {dp['p95']}ms > {budget.drill_p95_ms}ms")
    if strict.status != "stale_index":
        failures.append("strict_freshness 未回 stale_index（旧索引装新，红线）")
    if strict_ms > budget.strict_stale_max_ms:
        failures.append(f"strict stale 判定 {strict_ms:.1f}ms 超预算")
    per_rev = catch_ms / max(1, lag)
    if per_rev > budget.catchup_ms_per_revision:
        failures.append(f"追赶 {per_rev:.2f}ms/修订 超预算")
    plan = plan_checks(db_path)
    return {
        "gate": "G-M1P", "spec": "R4-02 / §3.4-T2-H",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "env": {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                "platform": platform.platform(), "cpus": platform.os.cpu_count()},
        "config": {"revisions": store.current_world_revision(), "requested": revisions_target,
                   "queries": queries, "seed": seed,
                   "budget": {"search_p95_ms": budget.search_p95_ms, "drill_p95_ms": budget.drill_p95_ms,
                              "catchup_ms_per_revision": budget.catchup_ms_per_revision,
                              "strict_stale_max_ms": budget.strict_stale_max_ms}},
        "points": {
            "search": {**sp, "n": search_pt.n, "verdict": "ok" if sp["p95"] <= budget.search_p95_ms else "fail"},
            "drill": {**dp, "n": drill_pt.n, "verdict": "ok" if dp["p95"] <= budget.drill_p95_ms else "fail"},
            "rebuild": {"seconds": round(rebuild_s, 3), "indexed_docs": n_obj,
                        "rows_per_sec": round(n_obj / max(rebuild_s, 1e-9))},
            "late_data": {"injected_revisions": late_n, "inject_seconds": round(inject_s, 3),
                          "lag_before": lag, "strict": {"status": strict.status, "ms": round(strict_ms, 2)},
                          "adaptive": {"status": adaptive.status, "catchup_total_ms": round(catch_ms, 2),
                                       "ms_per_revision": round(per_rev, 3)}},
            "hot_cards": {"status": hot_status, "note": "M1-020 施工图 §8 落地后升级为 fetch p95 点位"},
        },
        "plan_checks": plan,
        "consistency": consistency_ok({"G-M1P": sp["p95"], "M4a": None, "M7-002": None}),
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aios_core.bench.g_m1p", description=__doc__)
    ap.add_argument("--db", type=Path, required=True, help="基准库路径（不存在则生成）")
    ap.add_argument("--revisions", type=int, default=500_000)
    ap.add_argument("--queries", type=int, default=600)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--budget-search-ms", type=float, default=50.0)
    ap.add_argument("--budget-drill-ms", type=float, default=50.0)
    ap.add_argument("--out", type=Path, default=Path("g_m1p_report.json"))
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"[g_m1p] generating {args.revisions} revisions → {args.db}", flush=True)
        stats = generate_world(args.db, args.revisions, seed=args.seed)
        print(f"[g_m1p] generated: {stats}", flush=True)
    report = run_bench(
        args.db, queries=args.queries, seed=args.seed, revisions_target=args.revisions,
        budget=Budget(search_p95_ms=args.budget_search_ms, drill_p95_ms=args.budget_drill_ms),
    )
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "failures": report["failures"],
                      "search": report["points"]["search"], "consistency": report["consistency"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
