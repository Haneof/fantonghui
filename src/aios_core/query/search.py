"""M1-017/M1-018 预开工内核：世界检索的投影面（宪法第 89/36/95/96/27/86.4 条）。

治理声明
--------
本模块是 **M1 的预开工件**：M0-022R 签核、M1 Gate 开启之前，不得接入任何
运行路径（唤醒/会话/工作台）。它只依赖 `SQLiteWorldStore` 的公共读面
（``revisions_after`` / ``current_world_revision``），保持"唯一写入服务"
边界：索引是可重建投影，坏了删表重建，永不与真相争辩。

为什么自研倒排而第一版不用 FTS5
--------------------------------
本构建的 FTS5 `unicode61` 不做 CJK 分词、`trigram` 拒绝两个字符的查询
（"妈妈"这类双字中文词必然失配）。宪法第 89 条的入口是中文关键词共现，
因此 v1 直接实现设计书 §3.4-T2 的物理计划：

    posting-AND 交集 ∩ occurred 时间过滤 ∩ 实体消歧前置 ∩ 双视图截止

FTS5 仍是可替换适配器（第 18 条反教条）：对外只暴露 ``co_search``。

三条硬纪律
----------
1. **白名单抽取**：只索引契约文本字段，禁止把 payload 整包拷进索引（第 18 条
   反冗余；haystack 是检索辅助位，可整体重建）；
2. **消歧先于交集**（第 36 条）：别名解析出的实体编号参与匹配；歧义别名不
   自动二选一，标记 ``ambiguous`` 交还调用方；
3. **水位即诚实**（第 86.4 条）：任何返回都携带 ``lag``；strict 模式下落后
   直接 STALE_INDEX，禁止把旧索引装成新世界。
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios_core.contracts.time import as_utc

_WORD_RE = re.compile(r"[a-z0-9_]+")
_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_ID_STRIP_RE = re.compile(r"[^a-z0-9]")

# 白名单：object_type -> 可索引文本字段（契约内声明，绝不整包拷贝）。
_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "claim": ("content",),
    "observation": ("value",),
    "event": ("title", "interpretation"),
    "task": ("title", "next_step"),
    "entity": ("canonical_name",),
    "goal": ("title", "description"),
    "prediction": ("expected_change", "reasoning"),
    "reinterpretation": ("statement",),
    "life_chapter": ("chapter_title",),
    "communication_experience": ("scenario", "style", "tone"),
}
_TIME_FIELDS: dict[str, tuple[str, ...]] = {
    "event": ("event_time",),
    "prediction": ("time_window",),
    "relation": ("valid_time",),
    "reinterpretation": ("valid_time",),
}
_TYPE_BOOST: dict[str, int] = {"event": 2, "claim": 1, "task": 1}
_EXCERPT_LIMIT = 200
_WATERMARK_KEY = "search_watermark_world_revision"
_CATCHUP_MAX_ROWS = 50_000


def tokens_for(text: str) -> set[str]:
    """ASCII 词元 + CJK 二元组（bi-gram）。

    双字中文词（"妈妈""生日"）在 bi-gram 下即完整词元；长句命中为"所有
    bigram 共现"的近似召回，由 ``co_search`` 的 haystack 子串复核保证精确。
    """

    lowered = text.lower()
    tokens = set(_WORD_RE.findall(lowered))
    for run in _CJK_RUN_RE.findall(lowered):
        if len(run) == 1:
            tokens.add(run)
        tokens.update(a + b for a, b in zip(run, run[1:]))
    return tokens


def normalize_alias(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _id_token(kind: str, object_id: str) -> str:
    return kind + _ID_STRIP_RE.sub("", object_id.lower())


def _iter_ref_ids(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        object_id = node.get("object_id")
        if isinstance(object_id, str) and "revision" in node:
            yield object_id
        for value in node.values():
            yield from _iter_ref_ids(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_ref_ids(item)


def _extent_us(payload: dict, object_type: str) -> tuple[int | None, int | None]:
    extent = None
    for name in _TIME_FIELDS.get(object_type, ()) + ("occurred",):
        candidate = payload.get(name)
        if isinstance(candidate, dict) and not candidate.get("unknown", False):
            extent = candidate
            break
    if extent is None:
        for fallback_key in ("learned_at", "recorded_at"):
            val = payload.get(fallback_key)
            if isinstance(val, str):
                try:
                    us = int(as_utc(datetime.fromisoformat(val), "extent").timestamp() * 1_000_000)
                    return us, us
                except (ValueError, TypeError):
                    pass
        return None, None

    def _us(value: Any) -> int | None:
        if not isinstance(value, str):
            return None
        try:
            return int(as_utc(datetime.fromisoformat(value), "extent").timestamp() * 1_000_000)
        except ValueError:
            return None

    return _us(extent.get("start")), _us(extent.get("end"))


@dataclass(frozen=True)
class SearchHit:
    object_id: str
    revision: int
    object_type: str
    subject_id: str
    score: int
    excerpt: str


@dataclass
class SearchPage:
    status: str  # "ok" | "stale_index"
    lag: int
    world_revision: int
    index_watermark: int
    hits: list[SearchHit] = field(default_factory=list)
    ambiguous_keywords: dict[str, list[str]] = field(default_factory=dict)


class WorldSearchIndex:
    """Rebuildable projection index over one AIOS world database."""

    def __init__(self, db_path: str | Path, *, store: Any) -> None:
        self.db_path = str(db_path)
        self._store = store
        self._ensure_schema()

    # ---------------- schema / lifecycle ----------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_postings(
                    token TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY(token, object_id, revision)
                );
                CREATE TABLE IF NOT EXISTS search_occurred(
                    object_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    subject_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    occurred_start_us INTEGER,
                    occurred_end_us INTEGER,
                    PRIMARY KEY(object_id, revision)
                );
                CREATE TABLE IF NOT EXISTS search_doc(
                    object_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    haystack TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    PRIMARY KEY(object_id, revision)
                );
                CREATE TABLE IF NOT EXISTS search_alias(
                    alias_norm TEXT NOT NULL,
                    entity_object_id TEXT NOT NULL,
                    PRIMARY KEY(alias_norm, entity_object_id)
                );
                CREATE TABLE IF NOT EXISTS search_tombstones(
                    object_id TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS search_meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def drop_projection(self) -> None:
        """索引可弃（第 86.4 条：投影坏了删掉重建，不许与真相谈判）。"""

        with self._connect() as conn:
            conn.executescript(
                """
                DROP TABLE IF EXISTS search_postings;
                DROP TABLE IF EXISTS search_occurred;
                DROP TABLE IF EXISTS search_doc;
                DROP TABLE IF EXISTS search_alias;
                DROP TABLE IF EXISTS search_tombstones;
                DROP TABLE IF EXISTS search_meta;
                """
            )
        self._ensure_schema()

    # ---------------- watermarks ----------------

    def watermark(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM search_meta WHERE key=?", (_WATERMARK_KEY,)
            ).fetchone()
        return int(row["value"]) if row else 0

    def lag(self) -> int:
        return max(0, int(self._store.current_world_revision()) - self.watermark())

    # ---------------- incremental build ----------------

    def catch_up(self, *, max_rows: int = _CATCHUP_MAX_ROWS) -> int:
        """Apply commit-order deltas. Returns number of rows indexed.

        Truncation is cut at a world-revision boundary so a partial batch can
        never leave a watermark that skips objects of one logical commit.
        """

        target = int(self._store.current_world_revision())
        start = self.watermark()
        if start >= target:
            return 0
        rows = self._store.revisions_after(start, limit=max_rows)
        if not rows:
            return 0
        cut = int(rows[-1]["world_revision"])
        if len(rows) >= max_rows and int(rows[0]["world_revision"]) != cut:
            # 截断必须落在逻辑提交边界：丢掉可能残缺的尾组，
            # 水位绝不越过未完整索引的 world_revision（已知限制：单提交
            # 行数超过 max_rows 时需要流式重建，属 M1 Gate 后扩展）
            while rows and int(rows[-1]["world_revision"]) == cut:
                rows.pop()
            if not rows:
                return 0
            cut = int(rows[-1]["world_revision"])
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for row in rows:
                self._index_row(conn, row)
            conn.execute(
                "INSERT OR REPLACE INTO search_meta(key, value) VALUES(?, ?)",
                (_WATERMARK_KEY, str(cut)),
            )
            conn.commit()
        return len(rows)

    def rebuild(self) -> int:
        self.drop_projection()
        applied = 0
        while True:
            n = self.catch_up()
            applied += n
            if n == 0:
                return applied

    def _index_row(self, conn: sqlite3.Connection, row: dict) -> None:
        object_id = str(row["object_id"])
        revision = int(row["revision"])
        object_type = str(row["object_type"])
        subject_id = str(row["subject_id"])
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return  # 损坏行：跳过并留给水位审计，索引绝不反向污染世界
        if not isinstance(payload, dict):
            return

        texts: list[str] = []
        for name in _TEXT_FIELDS.get(object_type, ()):
            value = payload.get(name)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        tokens: set[str] = set()
        for text in texts:
            tokens |= tokens_for(text)

        revision_kind = row.get("revision_kind", "content")
        if revision_kind == "tombstone":
            conn.execute("INSERT OR REPLACE INTO search_tombstones(object_id) VALUES(?)", (object_id,))
            return

        tokens.add(_id_token("sub", subject_id))
        for ref_id in _iter_ref_ids(payload):
            tokens.add(_id_token("ref", ref_id))

        if object_type == "entity":
            tokens.add(_id_token("ent", object_id))
            names = [payload.get("canonical_name"), *(payload.get("aliases") or [])]
            for name in names:
                if isinstance(name, str) and name.strip():
                    tokens |= tokens_for(name)
                    conn.execute(
                        "INSERT OR IGNORE INTO search_alias(alias_norm, entity_object_id) VALUES(?, ?)",
                        (normalize_alias(name), object_id),
                    )

        haystack = "\n".join(texts)
        joined = haystack.lower()
        if tokens:
            conn.executemany(
                "INSERT OR IGNORE INTO search_postings(token, object_id, revision) VALUES(?,?,?)",
                [(token, object_id, revision) for token in tokens],
            )
        start_us, end_us = _extent_us(payload, object_type)
        conn.execute(
            """
            INSERT OR REPLACE INTO search_occurred(
                object_id, revision, subject_id, object_type, occurred_start_us, occurred_end_us
            ) VALUES(?,?,?,?,?,?)
            """,
            (object_id, revision, subject_id, object_type, start_us, end_us),
        )
        conn.execute(
            "INSERT OR REPLACE INTO search_doc(object_id, revision, haystack, excerpt) VALUES(?,?,?,?)",
            (object_id, revision, joined, haystack[:_EXCERPT_LIMIT]),
        )

    # ---------------- query ----------------

    def _postings_for(self, conn: sqlite3.Connection, tokens: set[str]) -> dict[tuple[str, int], int]:
        if not tokens:
            return {}
        ordered = sorted(tokens)
        placeholders = ",".join("?" for _ in ordered)
        rows = conn.execute(
            f"""
            SELECT object_id, revision, COUNT(*) AS hit_tokens
            FROM search_postings
            WHERE token IN ({placeholders})
            GROUP BY object_id, revision
            """,
            ordered,
        ).fetchall()
        return {(r["object_id"], int(r["revision"])): int(r["hit_tokens"]) for r in rows}

    def co_search(
        self,
        keywords: list[str],
        *,
        subject: str | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        limit: int = 50,
        strict_freshness: bool = False,
        view: str = "ANNOTATED",
        as_of: datetime | None = None,
        include_tombstones: bool = True,
    ) -> SearchPage:
        if not keywords or any(not kw.strip() for kw in keywords):
            raise ValueError("co_search requires non-blank keywords (第 89 条共现,不是单点通配)")
        current = int(self._store.current_world_revision())
        wm_before = self.watermark()
        if strict_freshness and wm_before < current:
            return SearchPage(status="stale_index", lag=current - wm_before,
                              world_revision=current, index_watermark=wm_before)
        if wm_before < current:
            self.catch_up()
        wm = self.watermark()

        per_kw: list[dict[tuple[str, int], int]] = []
        ambiguous: dict[str, list[str]] = {}
        with self._connect() as conn:
            for kw in keywords:
                tokens = set(tokens_for(kw))
                ent_rows = conn.execute(
                    "SELECT entity_object_id FROM search_alias WHERE alias_norm=?",
                    (normalize_alias(kw),),
                ).fetchall()
                ent_ids = sorted({r["entity_object_id"] for r in ent_rows})
                if len(ent_ids) > 1:
                    ambiguous[kw] = ent_ids  # 第 36 条：不自动合并身份
                elif len(ent_ids) == 1:
                    eid = ent_ids[0]
                    tokens.add(_id_token("ent", eid))
                    tokens.add(_id_token("ref", eid))
                    # 唯一解析到单实体→按别名全集展开召回（"母亲"→"妈妈"文本命中；
                    # 身份仍锚定实体编号，不改写任何对象）
                    for (alias,) in conn.execute(
                        "SELECT alias_norm FROM search_alias WHERE entity_object_id = ?", (eid,)
                    ):
                        tokens |= tokens_for(alias)
                hits = self._postings_for(conn, tokens)
                if not hits:
                    return SearchPage(status="ok", lag=current - wm, world_revision=current,
                                      index_watermark=wm, ambiguous_keywords=ambiguous)
                _ = tokens  # per-keyword token 集已折叠进 postings 命中
                per_kw.append(hits)
            candidates = set.intersection(*(set(h) for h in per_kw))
            if not candidates:
                return SearchPage(status="ok", lag=current - wm, world_revision=current,
                                  index_watermark=wm, ambiguous_keywords=ambiguous)
            page = self._finalize(conn, candidates, keywords, per_kw,
                                  subject=subject, time_range=time_range, limit=limit,
                                  lag=current - wm, current=current, wm=wm, ambiguous=ambiguous,
                                  view=view, as_of=as_of, include_tombstones=include_tombstones)
        return page

    def _finalize(
        self, conn: sqlite3.Connection, candidates: set[tuple[str, int]], keywords: list[str],
        per_kw: list[dict[tuple[str, int], int]], *, subject: str | None, time_range, limit: int,
        lag: int, current: int, wm: int, ambiguous: dict[str, list[str]],
        view: str = "ANNOTATED", as_of: datetime | None = None, include_tombstones: bool = True,
    ) -> SearchPage:
        if not include_tombstones:
            tombstones = {
                r[0] for r in conn.execute("SELECT object_id FROM search_tombstones").fetchall()
            }
            if hasattr(self._store, "is_latest_pruned"):
                def _is_pruned_or_refs_pruned(oid: str, rev: int) -> bool:
                    if oid in tombstones or self._store.is_latest_pruned(oid):
                        return True
                    try:
                        p = self._store.get_payload(oid, revision=rev)
                        for ref_id in _iter_ref_ids(p):
                            if ref_id in tombstones or self._store.is_latest_pruned(ref_id):
                                return True
                            if ref_id.startswith("evidence_"):
                                try:
                                    ev_p = self._store.get_payload(ref_id)
                                    for m in ev_p.get("member_refs", []):
                                        if isinstance(m, dict):
                                            mid = m.get("object_id")
                                            if mid and (mid in tombstones or self._store.is_latest_pruned(mid)):
                                                return True
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    return False
                candidates = {c for c in candidates if not _is_pruned_or_refs_pruned(c[0], c[1])}
            else:
                candidates = {c for c in candidates if c[0] not in tombstones}

        if view == "AS_KNOWN" and as_of is not None:
            as_of_us = int(as_utc(as_of, "as_of").timestamp() * 1_000_000)
            valid_candidates = set()
            for oid, rev in candidates:
                row = conn.execute(
                    "SELECT occurred_start_us FROM search_occurred WHERE object_id=? AND revision=?",
                    (oid, rev),
                ).fetchone()
                if row and row["occurred_start_us"] is not None:
                    if row["occurred_start_us"] <= as_of_us:
                        valid_candidates.add((oid, rev))
                else:
                    try:
                        p = self._store.get_payload(oid, revision=rev)
                        lat = p.get("learned_at")
                        if lat:
                            l_us = int(as_utc(datetime.fromisoformat(lat), "lat").timestamp() * 1_000_000)
                            if l_us <= as_of_us:
                                valid_candidates.add((oid, rev))
                        else:
                            valid_candidates.add((oid, rev))
                    except Exception:
                        valid_candidates.add((oid, rev))
            candidates = valid_candidates
        pairs = sorted(candidates)
        # 50 万修订下的物理计划纪律（G-M1P/T2-I 禁扫描）：候选对经临时表
        # WITHOUT ROWID 主键 join，杜绝行值 IN 退化为 SCAN search_occurred。
        conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS search_candidates("
            "object_id TEXT NOT NULL, revision INTEGER NOT NULL,"
            "PRIMARY KEY(object_id, revision)) WITHOUT ROWID"
        )
        conn.execute("DELETE FROM search_candidates")
        conn.executemany("INSERT INTO search_candidates VALUES (?,?)", pairs)
        params: list[Any] = []
        sql = """
            SELECT o.object_id, o.revision, o.object_type, o.subject_id,
                   o.occurred_start_us, o.occurred_end_us,
                   d.haystack, d.excerpt
            FROM search_candidates c
            JOIN search_occurred o ON o.object_id = c.object_id AND o.revision = c.revision
            JOIN search_doc d ON d.object_id = o.object_id AND d.revision = o.revision
            WHERE 1=1
        """
        if subject is not None:
            sql += " AND o.subject_id = ?"
            params.append(subject)
        if time_range is not None:
            t0 = int(time_range[0].astimezone(timezone.utc).timestamp() * 1_000_000)
            t1 = int(time_range[1].astimezone(timezone.utc).timestamp() * 1_000_000)
            sql += (
                " AND o.occurred_start_us IS NOT NULL"
                " AND NOT (COALESCE(o.occurred_end_us, o.occurred_start_us) < ? OR o.occurred_start_us > ?)"
            )
            params.extend([t0, t1])
        rows = conn.execute(sql + " ORDER BY o.occurred_start_us DESC, o.object_id", params).fetchall()

        best: dict[str, sqlite3.Row] = {}
        for row in rows:  # 同对象取最新可见 revision（pinned 语义由调用方在展开层处理）
            best.setdefault(row["object_id"], row)

        hits: list[SearchHit] = []
        for row in best.values():
            haystack = row["haystack"] or ""
            ok = True
            for kw in keywords:
                kwl = kw.strip().lower()
                if kwl in haystack:
                    continue
                # 文本不命中时，仅当该关键词已被实体编号解析（引用命中）才放行
                resolved = sorted({r["entity_object_id"] for r in conn.execute(
                    "SELECT entity_object_id FROM search_alias WHERE alias_norm=?", (normalize_alias(kw),))})
                if len(resolved) == 1:
                    alias_variants = [r[0] for r in conn.execute(
                        "SELECT alias_norm FROM search_alias WHERE entity_object_id = ?", (resolved[0],))]
                    if any(v in haystack for v in alias_variants):
                        continue
                    token = _id_token("ent", resolved[0])
                    has_link = conn.execute(
                        "SELECT 1 FROM search_postings WHERE token=? AND object_id=? AND revision=? LIMIT 1",
                        (token, row["object_id"], row["revision"]),
                    ).fetchone()
                    token2 = _id_token("ref", resolved[0])
                    has_link = has_link or conn.execute(
                        "SELECT 1 FROM search_postings WHERE token=? AND object_id=? AND revision=? LIMIT 1",
                        (token2, row["object_id"], row["revision"]),
                    ).fetchone()
                    if has_link:
                        continue
                ok = False
                break
            if not ok:
                continue
            pair = (row["object_id"], int(row["revision"]))
            score = sum(hits.get(pair, 0) for hits in per_kw)  # 共现证据数：各关键词命中词元之和
            score += _TYPE_BOOST.get(row["object_type"], 0)
            hits.append(SearchHit(
                object_id=row["object_id"], revision=int(row["revision"]),
                object_type=row["object_type"], subject_id=row["subject_id"],
                score=score, excerpt=row["excerpt"] or "",
            ))
        hits.sort(key=lambda h: (-h.score, h.object_id))
        return SearchPage(status="ok", lag=lag, world_revision=current, index_watermark=wm,
                          hits=hits[:limit], ambiguous_keywords=ambiguous)
