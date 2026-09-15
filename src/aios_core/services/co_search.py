"""M1-018 · Chinese Hybrid Co-Search Engine（宪法 §89 共现检索的执行体）。

 §89 的字面："多关键词共现联想检索"。unicode61 实测 0 命中的合宪出口不在
 unicode61 身上，而在它前面——倒排位面已经按词典切好，查询期只走 AND 交集，
 fts5 那条道只是 bm25 的记分员，不是命中的门槛。

 验收锚（I5 全量对账）：
  1. 中文零命中即 fatal：种子词族 total_hits==0 → fail-loud，不静默
  2. plan 必有：每次返回带 plan + counters（无 plan=违规）
  3. hit_reasons：每个命中必须能解释为什么被召回
  4. 诚实水位：coverage.stale 如实上报，partial 不扮 fresh
  5. 有界扩展：graph depth≤2、frontier≤64、visited-set
  6. 严禁 unicode61 撞运气/LIKE 全扫/权重进 schema
"""

from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..storage.lexicon_schema import ensure_lexicon_schema
from ..storage.sqlite_store import SQLiteWorldStore
from .alias_dictionary import (
    BUILTIN_SEED_TERMS,
    AliasDictionaryService,
    InjectionResult,
)
from .search_index_worker import LANE, SearchIndexWorker


class ZeroHitFatal(RuntimeError):
    """种子词族零命中 = 宪法判词级的索引事故，沉默比错误更可恨。"""


@dataclass(slots=True)
class CoSearchPlan:
    query_terms: list[str]
    alias_hits: int
    fts_path: str
    postings_path: str
    graph_enabled: bool
    rows_examined: int = 0
    deadline_ms: int = 200
    elapsed_ms: float = 0.0
    weight_signature: str = "policy:1.2.0"
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchHit:
    object_id: str
    matched_terms: list[str]
    hit_reasons: list[str]
    score: float
    rank: int
    via_entity: bool


@dataclass(slots=True)
class CoSearchResult:
    hits: list[SearchHit]
    total_hits: int
    plan: CoSearchPlan
    coverage: dict[str, Any]
    stale_index: bool
    query_terms: list[str]
    zero_hit_seed_fatal: bool = False


def _policy_default_weights(policy: Mapping[str, Any] | None) -> dict[str, float]:
    base = {"bm25": 1.0, "postings": 0.85, "entity": 0.6, "graph": 0.35,
            "recency": 0.15, "alias_bonus": 0.25}
    if not policy:
        return base
    co = policy.get("co_search") or {}
    weights = co.get("weights") or {}
    merged = dict(base)
    for k, v in weights.items():
        if isinstance(v, (int, float)):
            merged[k] = float(v)
    return merged


class CoSearchEngine:
    """查询引擎：确定性的三段召回（fts bm25 / postings AND / entity）+ 有界图。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        dictsvc: AliasDictionaryService,
        indexer: SearchIndexWorker,
        *,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        self._store = store
        self._dict = dictsvc
        self._idx = indexer
        self._policy = policy or {}
        self._w = _policy_default_weights(self._policy or None)
        co = (self._policy or {}).get("co_search") or {}
        self._graph_depth = int((co.get("graph") or {}).get("max_depth", 2))
        self._graph_frontier = int((co.get("graph") or {}).get("frontier_cap", 64))
        self._zero_hit_fatal = bool(co.get("zero_hit_fail_loud_for_seed_terms", True))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(self._store.db_path))
        conn.row_factory = sqlite3.Row
        ensure_lexicon_schema(conn)
        return conn

    # ---------------- 召回 --------------------------------------------------

    def query(
        self,
        keywords: Iterable[str],
        *,
        topk: int = 20,
        deadline_ms: int = 200,
        ensure_fresh: bool = False,
    ) -> CoSearchResult:
        t0 = time.monotonic()
        if ensure_fresh:
            self._idx.rebuild()
        cov = self._idx.coverage()
        stale = bool(cov.get("stale"))

        plan = CoSearchPlan(
            query_terms=[], alias_hits=0, fts_path="bm25:v1", postings_path="and-v1",
            graph_enabled=True, deadline_ms=deadline_ms,
        )

        inj: InjectionResult = self._dict.inject(keywords, record_misses=True)
        terms = list(dict.fromkeys(inj.canonical_terms))
        plan.query_terms = terms
        plan.alias_hits = len(inj.alias_hits)
        entity_ids = [h.entity_id for h in inj.alias_hits if h.entity_id]
        alias_surfaces = {h.matched_surface for h in inj.alias_hits if h.matched_surface != h.canonical}

        if not terms:
            plan.notes.append("no_canonical_terms")
            return CoSearchResult([], 0, plan, cov, stale, [])

        with self._connect() as conn:
            v = int((cov.get("dict_version") or self._dict.current_pack().version))
            scores: dict[str, float] = {}
            reasons: dict[str, list[str]] = {}
            terms_of: dict[str, set[str]] = {}

            def bump(oid: str, amount: float, reason: str, term: str | None = None) -> None:
                scores[oid] = scores.get(oid, 0.0) + amount
                if reason not in reasons.setdefault(oid, []):
                    reasons[oid].append(reason)
                if term is not None:
                    terms_of.setdefault(oid, set()).add(term)

            # 路 A：postings 显式 AND 交集（稳定路径——sim 阶段的主干道）
            for term in terms:
                rows = conn.execute(
                    "SELECT object_id, weight FROM term_postings WHERE term=? AND dict_version=?",
                    (term, v),
                ).fetchall()
                plan.rows_examined += len(rows)
                for r in rows:
                    bump(r["object_id"], self._w["postings"] * float(r["weight"]), "postings_and", term)

            # 路 B：fts bm25（记分员角色，token 串已在建索引时切好）
            for term in terms:
                try:
                    rows = conn.execute(
                        "SELECT object_id, bm25(object_fts) AS score FROM object_fts"
                        " WHERE object_fts MATCH ? LIMIT 100",
                        (f'"{term}"',),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                    plan.notes.append(f"fts_unavailable:{term}")
                plan.rows_examined += len(rows)
                for r in rows:
                    n = -float(r["score"])  # bm25 在 sqlite 是负数，越小越好
                    bump(r["object_id"], self._w["bm25"] / (1.0 + n), "fts_bm25", term)

            # 路 C：实体注入（谁在说≠说什么）
            for eid in entity_ids:
                rows = conn.execute(
                    "SELECT object_id, role FROM entity_postings WHERE entity_id=?",
                    (eid,),
                ).fetchall()
                plan.rows_examined += len(rows)
                for r in rows:
                    bump(r["object_id"], self._w["entity"] if r["role"] == "participant" else self._w["entity"] * 0.5,
                         f"entity:{r['role']}", f"@{eid}")

            # 别名 bonus：走了别名的关键词多一票可信度
            for s in alias_surfaces:
                for oid, seen_terms in terms_of.items():
                    if s in seen_terms:
                        scores[oid] += self._w["alias_bonus"]
                        if "alias_injected" not in reasons[oid]:
                            reasons[oid].append("alias_injected")

            # 多词共现门槛：AND——少一个词就别上桌（§89 "共现"的字面要求）
            required = len(terms)
            seed_vocabulary = {s for s, _ in BUILTIN_SEED_TERMS}
            seeded = [t for t in terms if t in seed_vocabulary]
            candidates = [
                oid for oid, seen in terms_of.items()
                if len(seen - {f"@{e}" for e in entity_ids}) >= required
                or (entity_ids and len(seen - {f"@{e}" for e in entity_ids}) >= max(0, required - 1) and any(s.startswith("@") for s in seen))
            ]
            # 有界图扩展（只对命中对象，visited-set，depth≤2, frontier≤64）
            expanded: dict[str, int] = {}
            if self._graph_depth > 0 and candidates:
                frontier = list(candidates)
                visited = set(frontier)
                depth = 0
                while frontier and depth < self._graph_depth and len(expanded) < self._graph_frontier:
                    depth += 1
                    q = ",".join("?" for _ in frontier)
                    rows = conn.execute(
                        f"SELECT dst, src FROM dependency_walk_cache WHERE src IN ({q}) LIMIT {self._graph_frontier}",
                        frontier,
                    ).fetchall()
                    plan.rows_examined += len(rows)
                    nxt: list[str] = []
                    for r in rows:
                        dst = r["dst"]
                        if dst in visited:
                            continue
                        visited.add(dst)
                        if len(expanded) < self._graph_frontier:
                            expanded[dst] = depth
                            nxt.append(dst)
                    frontier = nxt
            for oid, depth in expanded.items():
                scores[oid] = scores.get(oid, 0.0) + self._w["graph"] * (1.0 / (1 + depth))
                reasons.setdefault(oid, []).append(f"graph_walk:depth{depth}")

            for oid in candidates:
                reasons.setdefault(oid, [])
                terms_of.setdefault(oid, set())
            all_oids = sorted(set(candidates) | set(expanded))
            ranked: list[SearchHit] = []
            for oid in all_oids:
                entity_reasons = [r for r in reasons.get(oid, []) if r.startswith("entity:")]
                hit = SearchHit(
                    object_id=oid,
                    matched_terms=sorted(t for t in terms_of.get(oid, set()) if not t.startswith("@")),
                    hit_reasons=reasons.get(oid, []),
                    score=scores.get(oid, 0.0),
                    rank=0,
                    via_entity=bool(entity_reasons),
                )
                ranked.append(hit)
            ranked.sort(key=lambda h: (-h.score, h.object_id))
            for i, h in enumerate(ranked[: max(0, topk)], 1):
                h.rank = i
            hits = ranked[:topk]

        plan.elapsed_ms = (time.monotonic() - t0) * 1000.0
        zero_seed_fatal = (
            self._zero_hit_fatal
            and not hits
            and bool(seeded)
            and len(seeded) == len(terms)
        )
        if zero_seed_fatal:
            plan.notes.append("zero_hit_on_seed_terms FATAL")
            raise ZeroHitFatal(
                f"种子词族零命中（判词事故）：terms={terms}; index_dict_version={cov.get('dict_version')}"
            )
        return CoSearchResult(hits, len(ranked), plan, cov, stale, terms)


__all__ = [
    "CoSearchEngine", "CoSearchPlan", "CoSearchResult", "SearchHit", "ZeroHitFatal",
]
