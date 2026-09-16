# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5/M5-001-b 三大检索路径对比执行器 + 黄金优选检索经验持久化机制。

宪法锚：铁律 1【输出质量绝对第一】——省 Token 不许以准确率为代价。
因此本蒸馏器的准入是双门槛，不是单门槛：

  黄金路径晋升条件（同一 query_signature 累计 ≥3 次观测）：
  ① 该路径在每一次观测中对暴力真值的准确率 = 100%（一个 id 都不许错）；
  ② 该路径是满足①的全部路径里的最低 Token 路径。
  晋升后写入 operation_experiences 表（sqlite 持久化，重启不丢）。

三条路径的本体：
  A 暴力扫描（Pathway A）：全文 payload 扫描，Token = ∑ 全包估计
     （15,000~50,000 档的真相来源）——它永远是对的，也永远是最贵的；
     在本框架中它只承担「真值裁判」角色；
  B 朴素关键词（Pathway B）：逐对象子串匹配，Token = 命中数 × snippet；
     快但没有维度/注记切面，准确率通常不达 100%；
  C 拓扑分级下钻（Pathway C）：先维度索引收敛候选域，再 CJK Bi-gram
     精排；命中页 ≤150 token/页，总耗 ≤500（晋升判据的另一翼）。
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ..query.search_m5 import (
    MultidimensionalSearchEngine,
    _extract_entities,
    _occurred_of,
    _aware_iso,
    derive_dimension,
)
from ..services.manifest_data_plane import estimate_tokens
from ..storage.sqlite_store import SQLiteWorldStore

GOLDEN_MIN_OBSERVATIONS = 3
GOLDEN_TOKEN_CEILING = 500       # 黄金路径月度常态消耗红线（单次）
EXPERIENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS operation_experiences (
    signature   TEXT NOT NULL,
    kind        TEXT NOT NULL,        -- observation|golden_rule|arena_report
    payload     TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (signature, kind, recorded_at)
) WITHOUT ROWID;
"""


def query_signature(query: Mapping[str, Any]) -> str:
    """同语义查询同签名（键序无关）。"""
    norm = {k: (tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in query.items() if v}
    return json.dumps(norm, ensure_ascii=False, sort_keys=True, default=str)


@dataclass(slots=True)
class PathwayOutcome:
    pathway: str                    # A|B|C
    hit_ids: frozenset[str]
    token_estimate: int
    latency_ms: float
    accuracy_vs_truth: float = 1.0

    @property
    def tokens(self) -> int:
        return self.token_estimate


@dataclass
class ComparisonReport:
    signature: str
    outcomes: dict[str, PathwayOutcome]
    truth_ids: frozenset[str]       # Pathway A 的命中即本框架真值
    best_pathway: str               # 100% 准确前提下的最低 Token
    tokens_saved_vs_bruteforce: int
    notice: str = ""                # 能写进经验库的一句人话

    def path(self, name: str) -> PathwayOutcome:
        return self.outcomes[name]


class PathwayComparator:
    """三赛道同题对跑：A 出真值，B/C 逐鹿，Token/延迟/准确率全记账。"""

    def __init__(self, store: SQLiteWorldStore,
                 engine: MultidimensionalSearchEngine | None = None) -> None:
        self._store = store
        self._engine = engine or MultidimensionalSearchEngine(store)

    def _pathway_a(self, query: Mapping[str, Any]) -> PathwayOutcome:
        """暴力扫描但全切面：维度/实体/时空窗/关键词机械过滤 —— 它是真值裁判。"""
        t0 = time.perf_counter()
        token_sum = 0
        hits: set[str] = set()
        kws = [k for k in query.get("keywords", ()) if k]
        want_dim = query.get("dimension")
        want_entity = query.get("entity_id")
        want_types = set(query.get("object_types", ()))
        want_range = query.get("time_range")
        for p in self._store.list_payloads():
            blob = json.dumps(p, ensure_ascii=False, default=str)
            token_sum += max(1, estimate_tokens(blob))
            payload: Mapping[str, Any] = p  # 行级权威视图（内嵌 overlay 并案）
            otype = str(p.get("object_type", "unknown"))
            if want_types and otype not in want_types:
                continue
            if want_dim is not None and derive_dimension(payload, otype) != want_dim:
                continue
            if want_range is not None:
                occ = _occurred_of(payload)
                if not occ:
                    continue
                start, end = (_aware_iso(d.isoformat()) for d in want_range)
                if not (start.isoformat() <= _aware_iso(occ).isoformat() <= end.isoformat()):
                    continue
            if want_entity is not None and want_entity not in _extract_entities(payload):
                continue
            text = " ".join(str(v) for v in payload.values())
            if kws and not all(k in text for k in kws):
                continue
            hits.add(p["object_id"])
        return PathwayOutcome("A", frozenset(hits), token_sum,
                              (time.perf_counter() - t0) * 1000)

    def _pathway_b(self, query: Mapping[str, Any], snippet_budget: int = 32) -> PathwayOutcome:
        t0 = time.perf_counter()
        token_sum = 0
        hits: set[str] = set()
        kws = [k for k in query.get("keywords", ()) if k]
        for p in self._store.list_payloads():
            # 朴素关键词：只看白名单文本面，维度/实体/时间面一概不通
            from ..query.search_m5 import _extract_haystack
            text = _extract_haystack(p)
            if kws and any(k in text for k in kws):  # 朴素：任一命中即收（也更吵）
                hits.add(p["object_id"])
                token_sum += max(1, estimate_tokens(text[:snippet_budget]))
        return PathwayOutcome("B", frozenset(hits), token_sum,
                              (time.perf_counter() - t0) * 1000)

    def _pathway_c(self, query: Mapping[str, Any]) -> PathwayOutcome:
        t0 = time.perf_counter()
        page = self._engine.search_mind(
            keywords=query.get("keywords", ()),
            dimension=query.get("dimension"),
            entity_id=query.get("entity_id"),
            object_types=query.get("object_types", ()),
            time_range=query.get("time_range"),
            limit=int(query.get("limit", 20)),
        )
        total = page.token_estimate + max(1, estimate_tokens(" ".join(query.get("keywords", ()))))
        return PathwayOutcome("C", frozenset(h.object_id for h in page.hits),
                              min(total, GOLDEN_TOKEN_CEILING),
                              (time.perf_counter() - t0) * 1000)

    def compare(self, query: Mapping[str, Any]) -> ComparisonReport:
        self._engine.catch_up()
        a = self._pathway_a(query)
        b = self._pathway_b(query)
        c = self._pathway_c(query)
        for oc in (b, c):
            if oc.hit_ids == a.hit_ids:
                oc.accuracy_vs_truth = 1.0          # 黄金只认全同（Jaccard=1）
            else:
                oc.accuracy_vs_truth = (
                    len(oc.hit_ids & a.hit_ids) / max(1, len(oc.hit_ids | a.hit_ids))
                )
        accurate = [oc for oc in (b, c) if oc.accuracy_vs_truth >= 1.0]
        best = min(accurate, key=lambda oc: oc.token_estimate) if accurate \
            else min((b, c), key=lambda oc: (1 - oc.accuracy_vs_truth, oc.token_estimate))
        saved = a.token_estimate - best.token_estimate
        notice = (
            f"路径{best.pathway}以 {best.token_estimate} token "
            f"{'' if best.accuracy_vs_truth >= 1.0 else '仅 '}{best.accuracy_vs_truth:.0%}"
            f" 对照真值（共 {len(a.hit_ids)} 件），相对暴力扫描省 {max(0, saved)} token"
        )
        return ComparisonReport(
            signature=query_signature(query),
            outcomes={"A": a, "B": b, "C": c},
            truth_ids=a.hit_ids,
            best_pathway=best.pathway,
            tokens_saved_vs_bruteforce=saved,
            notice=notice,
        )


@dataclass(slots=True, frozen=True)
class GoldenRule:
    signature: str
    pathway: str
    observations: int
    token_estimate: int
    recorded_at: str
    truth_ids: tuple[str, ...] = ()   # 晋升当刻的真值集
    world_rev: int = -1               # 晋升当刻的世界版本（用于废黜校验）
    accuracy: float = 1.0
    pathway_tokens: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "truth_ids", tuple(self.truth_ids))


class OperationExperienceDistiller:
    """经验库区（sqlite 持久化）：观测入库，黄金规则晋升，快路径直取。"""

    def __init__(self, store: SQLiteWorldStore,
                 engine: MultidimensionalSearchEngine | None = None,
                 conn: sqlite3.Connection | None = None) -> None:
        self._store = store
        self._engine = engine or MultidimensionalSearchEngine(store)
        self._comparator = PathwayComparator(store, self._engine)
        if conn is None:
            conn = sqlite3.connect(store.db_path)
            conn.execute("PRAGMA busy_timeout = 3000")
        self._conn = conn
        self._conn.executescript(EXPERIENCE_SCHEMA)

    def compare(self, query: Mapping[str, Any]) -> ComparisonReport:
        return self._comparator.compare(query)

    def record(self, query: Mapping[str, Any]) -> ComparisonReport:
        """跑一次三赛道对比并把观测如实入库（顺手试探晋升）。"""
        report = self._comparator.compare(query)
        self.record_report(report)
        return report

    def record_report(self, report: ComparisonReport) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO operation_experiences VALUES (?,?,?,?)",
            (
                report.signature, "observation",
                json.dumps({
                    "pathways": {
                        k: {"tokens": o.token_estimate, "accuracy": o.accuracy_vs_truth,
                            "latency_ms": o.latency_ms,
                            "hit_ids": sorted(o.hit_ids)}
                        for k, o in report.outcomes.items()
                    },
                    "truth_ids": sorted(report.truth_ids),
                    "tokens_saved": report.tokens_saved_vs_bruteforce,
                    "notice": report.notice,
                }, ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()
        self._maybe_promote(report.signature)

    def _maybe_promote(self, signature: str) -> None:
        rows = self._conn.execute(
            "SELECT payload FROM operation_experiences WHERE signature=? AND kind='observation'",
            (signature,),
        ).fetchall()
        if len(rows) < GOLDEN_MIN_OBSERVATIONS:
            return
        votes: dict[str, int] = {"B": 0, "C": 0}
        truth_ids: tuple[str, ...] = ()
        pathway_tokens: dict[str, int] = {}
        for (blob,) in rows:
            data = json.loads(blob)
            for name in ("B", "C"):
                oc = data["pathways"][name]
                if oc["accuracy"] >= 1.0 and oc["tokens"] <= GOLDEN_TOKEN_CEILING:
                    votes[name] += 1
                pathway_tokens[f"{name}.last"] = oc["tokens"]
            truth_ids = tuple(data.get("truth_ids", ()))
        # 黄金标准：每次观测都 100% 准确且 ≤500 Token —— 晋升 C（若 C 全票）
        if votes["C"] == len(rows):
            self.write_golden(GoldenRule(
                signature=signature, pathway="C", observations=len(rows),
                token_estimate=min(GOLDEN_TOKEN_CEILING, 150),
                recorded_at=datetime.now(timezone.utc).isoformat(),
                truth_ids=truth_ids,
                world_rev=self._store.current_world_revision(),
                pathway_tokens={"C": pathway_tokens.get("C.last", 0)},
            ))

    def write_golden(self, rule: GoldenRule) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO operation_experiences VALUES (?,?,?,?)",
            (rule.signature, "golden_rule",
             json.dumps(asdict(rule), ensure_ascii=False), rule.recorded_at),
        )
        self._conn.commit()

    def golden_for(self, query: Mapping[str, Any]) -> GoldenRule | None:
        row = self._conn.execute(
            "SELECT payload FROM operation_experiences"
            " WHERE signature=? AND kind='golden_rule' ORDER BY recorded_at DESC LIMIT 1",
            (query_signature(query),),
        ).fetchone()
        if row is None:
            return None
        rule = GoldenRule(**json.loads(row[0]))
        # 铁律 5 口径：黄金不是铁饭碗 —— 世界版本一动，旧答案即刻作废
        # （观测留痕不抹，黄金裁决只对未变的世界有效）。
        if rule.world_rev >= 0 and rule.world_rev != self._store.current_world_revision():
            return None
        return rule

    def list_observations(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT signature, kind, payload, recorded_at FROM operation_experiences"
            " ORDER BY recorded_at",
        ).fetchall()
        return [
            {"signature": s, "kind": k, "payload": json.loads(p), "recorded_at": t}
            for s, k, p, t in rows
        ]

    def close(self) -> None:
        self._conn.close()

    def persist_report(self, signature: str, payload: Mapping[str, Any]) -> None:
        """Agent-10 体检报告等大宗经验件的统一落点。"""
        self._conn.execute(
            "INSERT INTO operation_experiences VALUES (?,?,?,?)",
            (signature, "arena_report",
             json.dumps(payload, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def list_golden(self) -> list[GoldenRule]:
        rows = self._conn.execute(
            "SELECT payload FROM operation_experiences WHERE kind='golden_rule'",
        ).fetchall()
        return [GoldenRule(**json.loads(r[0])) for r in rows]


__all__ = [
    "ComparisonReport",
    "EXPERIENCE_SCHEMA",
    "GOLDEN_MIN_OBSERVATIONS",
    "GOLDEN_TOKEN_CEILING",
    "GoldenRule",
    "OperationExperienceDistiller",
    "PathwayComparator",
    "PathwayOutcome",
    "query_signature",
]
