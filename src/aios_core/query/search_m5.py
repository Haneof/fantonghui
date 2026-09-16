# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-001 多维世界搜索底座（工单 #6，纯增量，不借 mainline 移植，原生适配本树）。

宪法锚：§89 中文关键词共现入口 / §36 消歧先于交集 / §86.4 水位即诚实。

联合检索切面：维度 (Dimension) × 实体 (Entity) × CJK Bi-gram × 时空窗 ×
外挂注记 (RetrospectiveAnnotation)。三种硬纪律：

1. 【白名单抽取】只索引契约文本字段与本推导器认可的口袋字段，
   payload 整包绝不进索引（haystack 是可整体重建的投影，不是真相）；
2. 【水位即诚实】每页结果携带 indexed_rev 与世界 rev 的 lag；调用方
   据此自行决断新鲜度——本投影永不假装与真相同步；
3. 【Token 封套】∑ 所有命中 snippet 的 token 估计 ≤ 150 硬顶，
   溢出只记 overflow_count，绝不静默膨胀（M5 交互红线）。

与 M1-018 co_search 的兼容边界：本模块只新增表与只读路径，
co_search 的行为分毫不动（见 tests 的同语料一致性断言）。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..query.cjk_inverted_index import tokenize_cjk_overlapping
from ..services.manifest_data_plane import estimate_tokens
from ..storage.sqlite_store import SQLiteWorldStore

PAGE_TOKEN_BUDGET = 150          # 单次命中 Token 封套硬顶（工单铁律）
MAX_SNIPPET_CHARS = 96

SEARCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_occurred (
    object_id    TEXT NOT NULL,
    object_type  TEXT NOT NULL,
    dimension    TEXT NOT NULL,
    occurred_iso TEXT NOT NULL,
    haystack     TEXT NOT NULL,   -- 白名单文本拼接（白底抽取，非整包）
    entities     TEXT NOT NULL,   -- JSON 数组：本对象关联的实体 id
    PRIMARY KEY (object_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS so_dim_time ON search_occurred(dimension, occurred_iso);
CREATE INDEX IF NOT EXISTS so_type_time ON search_occurred(object_type, occurred_iso);

CREATE TABLE IF NOT EXISTS search_annotations (
    annotation_id TEXT PRIMARY KEY,
    anchor_object_id TEXT NOT NULL,
    learned_iso    TEXT NOT NULL,
    valid_start    TEXT,
    valid_end      TEXT,
    overlay_text   TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS sa_learned ON search_annotations(learned_iso);

CREATE TABLE IF NOT EXISTS search_watermark (
    mark_id INTEGER PRIMARY KEY CHECK (mark_id = 1),
    indexed_count INTEGER NOT NULL,
    indexed_rev   INTEGER NOT NULL
);
"""

_TEXT_WHITELIST = (
    "content", "headline", "text", "summary", "semantic_caption",
    "title", "note", "utterance", "name", "description", "statement",
)

_DIMENSION_RULES: tuple[tuple[str, str], ...] = (
    ("trigger_expression", "DIM_TASK_SCHEDULING"),
    ("manifest_instance", "DIM_AI_SELF_COGNITION"),
    ("retrospective_annotation", "DIM_RETRO_OVERLAY"),
    ("reinterpretation", "DIM_RETRO_OVERLAY"),
    ("retention_tombstone", "DIM_SYSTEM_GOVERNANCE"),
)

_PAYLOAD_DIMENSION_HINTS: tuple[tuple[str, str], ...] = (
    ("心率", "DIM_BODY_VITALS"), ("血压", "DIM_BODY_VITALS"), ("早搏", "DIM_BODY_VITALS"),
    ("睡眠", "DIM_BODY_VITALS"), ("熬夜", "DIM_BODY_VITALS"), ("通宵", "DIM_BODY_VITALS"),
    ("会议", "DIM_CAREER_LEGAL"), ("合同", "DIM_CAREER_LEGAL"), ("对赌", "DIM_CAREER_LEGAL"),
    ("诉讼", "DIM_CAREER_LEGAL"), ("判决", "DIM_CAREER_LEGAL"), ("股权", "DIM_CAREER_LEGAL"),
    ("母亲", "DIM_FAMILY_PARENTS"), ("妈", "DIM_FAMILY_PARENTS"), ("膝盖", "DIM_FAMILY_PARENTS"),
    ("借款", "DIM_CREDIT_RELATION"), ("王建国", "DIM_CREDIT_RELATION"), ("老王", "DIM_CREDIT_RELATION"),
    ("羁绊", "DIM_AI_RAPPORT"), ("rapport", "DIM_AI_RAPPORT"),
)


def derive_dimension(payload: Mapping[str, Any], object_type: str) -> str:
    """维度推导：对象类型优先，其次白名单文本命中提示，兜底 DIM_GENERAL。

    纯确定性规则表（同 payload 同维度）；规则表本身就是治理件，
    加规则 = 走变更，不让检索面出现概率性归类。
    """
    for ot, dim in _DIMENSION_RULES:
        if object_type == ot:
            return dim
    text = " ".join(str(payload.get(k, "")) for k in _TEXT_WHITELIST if payload.get(k))
    for kw, dim in _PAYLOAD_DIMENSION_HINTS:
        if kw.lower() in text.lower():
            return dim
    return "DIM_GENERAL"


def _extract_haystack(payload: Mapping[str, Any]) -> str:
    parts = [str(payload[k]) for k in _TEXT_WHITELIST if payload.get(k) is not None]
    nested = payload.get("payload")
    if isinstance(nested, dict):  # 外挂注记 overlay / 其他嵌套文本并案入库
        parts.extend(str(v) for v in nested.values())
    return " ".join(parts)[:2000]


def _extract_entities(payload: Mapping[str, Any]) -> list[str]:
    """从 ObjectRef 形态字段里抽实体指针（浅扫一层 + refs 数组）。"""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            oid = value.get("object_id")
            if isinstance(oid, str) and oid:
                found.append(oid)
            for v in value.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, (dict, list)):
                    walk(v)

    for key in ("anchor_ref", "target_ref", "evidence_refs", "evidence_set_ref",
                "support_evidence_set_refs",
                "counter_evidence_set_refs", "refs", "entity_refs"):
        if key in payload:
            walk(payload[key])
    subj = payload.get("subject_id")
    if isinstance(subj, str) and subj:
        found.append(subj)
    seen: set[str] = set()
    out = []
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out[:16]


def _occurred_of(payload: Mapping[str, Any]) -> str:
    for k in ("occurred_at", "asserted_at", "learned_at", "recorded_at", "captured_at", "created_at"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, datetime):
            return v.isoformat()
    return ""


def _aware_iso(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(slots=True, frozen=True)
class MindSearchHit:
    object_id: str
    object_type: str
    dimension: str
    occurred_iso: str
    snippet: str
    entity_ids: tuple[str, ...]
    is_annotation: bool = False


@dataclass
class MindSearchPage:
    hits: list[MindSearchHit]
    total_matched: int
    token_estimate: int
    overflow_count: int
    indexed_rev: int
    world_rev: int
    lag: int
    token_budget: int = PAGE_TOKEN_BUDGET


class MultidimensionalSearchEngine:
    """多维联合检索总线：索引是投影，世界是真相，水位差永远亮明。"""

    def __init__(self, store: SQLiteWorldStore) -> None:
        self._store = store

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._store.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(SEARCH_SCHEMA)
        return conn

    # ------------------------- 投影同步 ---------------------------------

    def catch_up(self) -> int:
        """把世界公共读面(list_payloads)的最新投影刷进索引表，幂等。"""
        payloads = self._store.list_payloads()
        n = 0
        with self._connect() as conn:
            for p in payloads:
                oid = p.get("object_id")
                if not isinstance(oid, str) or not oid:
                    continue
                otype = str(p.get("object_type", "unknown"))
                # 公共读面行即权威 payload（注记行内嵌 overlay dict 也需并案索引）
                payload: Mapping[str, Any] = p
                conn.execute(
                    "INSERT OR REPLACE INTO search_occurred VALUES (?,?,?,?,?,?)",
                    (
                        oid, otype, derive_dimension(payload, otype),
                        _occurred_of(payload) or "",
                        _extract_haystack(payload),
                        json.dumps(_extract_entities(payload), ensure_ascii=False),
                    ),
                )
                if otype in ("retrospective_annotation", "reinterpretation"):
                    anchor = (payload.get("anchor_ref") or payload.get("target_ref")
                              or {})
                    valid = payload.get("valid_time") or {}
                    nested = payload.get("payload")
                    if isinstance(nested, dict):
                        overlay = json.dumps(nested, ensure_ascii=False)
                    else:
                        overlay = json.dumps(
                            {"statement": payload.get("statement", ""),
                             "slot": str(payload.get("slot", ""))},
                            ensure_ascii=False)
                    conn.execute(
                        "INSERT OR REPLACE INTO search_annotations VALUES (?,?,?,?,?,?)",
                        (
                            oid,
                            str(anchor.get("object_id", "")),
                            _occurred_of(payload),
                            str(valid.get("start")) if isinstance(valid, dict) else None,
                            str(valid.get("end")) if isinstance(valid, dict) else None,
                            overlay,
                        ),
                    )
                n += 1
            conn.execute(
                "INSERT OR REPLACE INTO search_watermark VALUES (1,?,?)",
                (n, self._store.current_world_revision()),
            )
        return n

    # ------------------------- 联合检索 ---------------------------------

    def search_mind(
        self,
        *,
        keywords: Iterable[str] = (),
        dimension: str | None = None,
        entity_id: str | None = None,
        object_types: Iterable[str] = (),
        time_range: tuple[datetime, datetime] | None = None,
        limit: int = 20,
        token_budget: int = PAGE_TOKEN_BUDGET,
    ) -> MindSearchPage:
        """∧ 语义的全联合查询：所有给到的切面必须同时满足。"""
        budget = min(token_budget, PAGE_TOKEN_BUDGET)
        clauses: list[str] = []
        params: list[Any] = []
        if dimension is not None:
            clauses.append("dimension = ?")
            params.append(dimension)
        types = list(object_types)
        if types:
            clauses.append("object_type IN (" + ",".join("?" * len(types)) + ")")
            params.extend(types)
        if time_range is not None:
            start, end = time_range
            clauses.append("occurred_iso >= ?")
            params.append(_aware_iso(start.isoformat()).isoformat())
            clauses.append("occurred_iso <= ?")
            params.append(_aware_iso(end.isoformat()).isoformat())
        kws = [k for k in keywords if k]
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM search_occurred{where} ORDER BY occurred_iso DESC LIMIT 512",
                params,
            ).fetchall()
            mark = conn.execute("SELECT * FROM search_watermark WHERE mark_id=1").fetchone()

        candidates: list[tuple[MindSearchHit, int]] = []
        for r in rows:
            hay = r["haystack"]
            ok_kw = True
            for kw in kws:
                toks = tokenize_cjk_overlapping(kw)
                if (kw not in hay) and not all(t in hay for t in toks):
                    ok_kw = False
                    break
            if not ok_kw:
                continue
            entities = tuple(json.loads(r["entities"]))
            if entity_id is not None and entity_id not in entities:
                continue
            hit = MindSearchHit(
                object_id=r["object_id"], object_type=r["object_type"],
                dimension=r["dimension"], occurred_iso=r["occurred_iso"],
                snippet=hay[:MAX_SNIPPET_CHARS], entity_ids=entities,
            )
            candidates.append((hit, 0))

        total_matched = len(candidates)
        page: list[MindSearchHit] = []
        token_sum = 0
        overflow = 0
        for hit, _ in candidates:
            cost = max(1, estimate_tokens(hit.snippet))
            if len(page) >= limit or token_sum + cost > budget:
                overflow += 1
                continue
            page.append(hit)
            token_sum += cost

        world_rev = self._store.current_world_revision()
        indexed_rev = int(mark["indexed_rev"]) if mark else 0
        return MindSearchPage(
            hits=page, total_matched=total_matched, token_estimate=token_sum,
            overflow_count=overflow, indexed_rev=indexed_rev, world_rev=world_rev,
            lag=world_rev - indexed_rev, token_budget=budget,
        )

    def annotations_of_today(self, day_start: datetime) -> list[dict[str, Any]]:
        """外挂注记 100% 召回面：凡是 learned_at ≥ day_start 的注记一条不漏。"""
        start = _aware_iso(day_start.isoformat()).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM search_annotations WHERE learned_iso >= ? ORDER BY learned_iso",
                (start,),
            ).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "MAX_SNIPPET_CHARS",
    "MindSearchHit",
    "MindSearchPage",
    "MultidimensionalSearchEngine",
    "PAGE_TOKEN_BUDGET",
    "derive_dimension",
    "_aware_iso",
    "_extract_entities",
    "_occurred_of",
]
