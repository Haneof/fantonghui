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

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
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
_ANNO_FINGERPRINT_KEY = "search_annotation_fingerprint"
_CATCHUP_MAX_ROWS = 50_000



def derive_dimension(payload: dict, object_type: str) -> str:
    """宪法第十七章：多维时空维度推导（健康/财务/社交/工作/通用）。"""
    dim = payload.get("dimension")
    if isinstance(dim, str) and dim.strip():
        return dim.strip()
    dims = payload.get("dimensions")
    if isinstance(dims, list) and dims and isinstance(dims[0], str):
        return dims[0].strip()

    src = str(payload.get("source_kind", "")).lower()
    if src in ("biometrics", "heart_rate", "sleep", "sensor", "arrhythmia", "health"):
        return "dim_health"
    if src in ("transaction", "bank", "receipt", "finance", "loan", "contract"):
        return "dim_finance"
    if src in ("chat", "call", "audio", "message", "social"):
        return "dim_social"
    if src in ("work_log", "calendar", "meeting", "code", "work"):
        return "dim_work"

    content_blob = ""
    for k in ("content", "value", "title", "interpretation", "statement", "purpose"):
        v = payload.get(k)
        if isinstance(v, str):
            content_blob += " " + v
    content_blob = content_blob.lower()
    if any(w in content_blob for w in ("心率", "早搏", "理疗", "膝盖", "健康", "医院", "血压", "睡眠")):
        return "dim_health"
    if any(w in content_blob for w in ("借款", "转账", "元", "合伙", "判决", "诈骗", "还款", "投资", "消费")):
        return "dim_finance"
    if any(w in content_blob for w in ("恋爱", "前任", "争吵", "母亲", "老妈", "朋友", "生日", "小林")):
        return "dim_social"
    if any(w in content_blob for w in ("加班", "代码", "上线", "版本", "会议", "工作", "q3")):
        return "dim_work"

    return "dim_general"


def _annotation_fingerprint(rows: list[sqlite3.Row]) -> str:
    """外挂注记清单指纹：判断「今天挂的标签」是否需要重新进投影。"""

    digest = hashlib.sha1()
    for row in sorted(rows, key=lambda r: str(r[0])):
        digest.update("|".join(str(col) for col in tuple(row)[:5]).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


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



@dataclass(frozen=True)
class MindSearchHit:
    object_id: str
    revision: int
    object_type: str
    subject_id: str
    score: int
    dimension: str
    excerpt: str
    is_annotation: bool = False
    related_entity_ids: list[str] = field(default_factory=list)
    estimated_tokens: int = 0


@dataclass
class MindSearchPage:
    status: str  # "ok" | "stale_index"
    lag: int
    world_revision: int
    index_watermark: int
    hits: list[MindSearchHit] = field(default_factory=list)
    total_estimated_tokens: int = 0
    query_intent: str = ""


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
                    dimension TEXT DEFAULT '',
                    PRIMARY KEY(object_id, revision)
                );
                CREATE TABLE IF NOT EXISTS search_annotations(
                    annotation_id TEXT PRIMARY KEY,
                    target_object_id TEXT NOT NULL,
                    target_object_type TEXT NOT NULL,
                    reinterpretation_claim TEXT NOT NULL,
                    is_invalidating INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    dimension TEXT DEFAULT ''
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
            try:
                conn.execute("ALTER TABLE search_occurred ADD COLUMN dimension TEXT DEFAULT ''")
            except Exception:
                pass

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
                DROP TABLE IF EXISTS search_annotations;
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
        # 世界本体没有新 revision 时，外挂注记仍可能刚刚挂载：注记不产生
        # revision，其同步必须独立于索引水位，否则「今天挂的标签今天可召回」
        # 会退化成「等下一次世界提交才可见」（宪法第二十章）。
        rows = self._store.revisions_after(start, limit=max_rows) if start < target else []
        if not rows:
            self.sync_annotations()
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
            self._catch_up_annotations(conn)
            conn.commit()
        return len(rows)

    def sync_annotations(self) -> int:
        """把外挂注记同步进检索投影（不依赖世界版本水位）。

        注记是「今天挂的解释图层」，它不产生 ``world_revision``；索引追平世界
        本体之后新挂的注记，只有本方法能让它立即可召回（宪法第二十章）。

        语义与 ``catch_up`` 一致：幂等、可重复调用；注记清单指纹未变化时
        直接返回 0，且不开启任何写事务。
        """

        with self._connect() as conn:
            if not self._annotations_pending(conn):
                return 0
            conn.execute("BEGIN IMMEDIATE")
            synced = self._catch_up_annotations(conn)
            conn.commit()
        return synced

    def _annotations_pending(self, conn: sqlite3.Connection) -> bool:
        """只读比对注记清单指纹：判断是否需要重新投影。"""

        rows = self._select_annotation_rows(conn)
        if rows is None:
            return False
        stored = conn.execute(
            "SELECT value FROM search_meta WHERE key=?", (_ANNO_FINGERPRINT_KEY,)
        ).fetchone()
        return (str(stored["value"]) if stored else "") != _annotation_fingerprint(rows)

    def _select_annotation_rows(self, conn: sqlite3.Connection) -> list[sqlite3.Row] | None:
        """读外挂注记清单；底层没有注记表时返回 None（投影可独立重建）。"""

        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='retrospective_annotations'"
            )
            if not cur.fetchone():
                return None
            return conn.execute(
                "SELECT annotation_id, target_object_id, target_object_type, "
                "reinterpretation_claim, is_invalidating, created_at, created_by "
                "FROM retrospective_annotations"
            ).fetchall()
        except sqlite3.Error:
            return None

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
        dim = derive_dimension(payload, object_type)
        tokens.add(_id_token("dim", dim))
        if tokens:
            conn.executemany(
                "INSERT OR IGNORE INTO search_postings(token, object_id, revision) VALUES(?,?,?)",
                [(token, object_id, revision) for token in tokens],
            )

        start_us, end_us = _extent_us(payload, object_type)
        conn.execute(
            """
            INSERT OR REPLACE INTO search_occurred(
                object_id, revision, subject_id, object_type, occurred_start_us, occurred_end_us, dimension
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (object_id, revision, subject_id, object_type, start_us, end_us, dim),
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

    def ring_adjacency(
        self,
        object_ids: Sequence[str],
        *,
        limit: int = 50,
    ) -> dict[str, list[str]]:
        """拓扑下钻专用：**同层一次批读**入边指针环。

        返回 ``{给定对象: [指向它的对象 id]}``：语义与逐点调用
        ``search_mind(entity_id=...)`` 的入边环一致（``ref`` / ``ent`` 两类指针，
        去掉墓碑与自身，按发生时间降序），但把 N 次单点检索压成一次 SQL。

        为什么必须批读：逐点检索每次都要开一条 SQLite 连接并重建 token 集，
        连接开销是 N 倍；「拓扑分级下钻」若按点走，单次检索延迟会被 N 拖到
        20ms 以上。批读后延迟与世界规模、跳数都只成一次 SQL 常数关系。
        """

        ids = [str(i) for i in object_ids if str(i)]
        if not ids:
            return {}
        token_owner: dict[str, str] = {}
        for oid in ids:
            token_owner.setdefault(_id_token("ref", oid), oid)
            token_owner.setdefault(_id_token("ent", oid), oid)
        ordered = sorted(token_owner)
        placeholders = ", ".join("?" for _ in ordered)

        with self._connect() as conn:
            tombstones = {str(r[0]) for r in conn.execute("SELECT object_id FROM search_tombstones")}
            rows = conn.execute(
                f"""
                SELECT p.token AS token, p.object_id AS object_id, p.revision AS revision,
                       o.occurred_start_us AS occurred_start_us
                FROM search_postings p
                JOIN search_occurred o ON o.object_id = p.object_id AND o.revision = p.revision
                JOIN search_doc d ON d.object_id = p.object_id AND d.revision = p.revision
                WHERE p.token IN ({placeholders})
                ORDER BY o.occurred_start_us DESC
                """,
                ordered,
            ).fetchall()

        ring: dict[str, list[str]] = {}
        seen: dict[str, set[str]] = {}
        for row in rows:
            owner = token_owner.get(str(row["token"]))
            if owner is None:
                continue
            oid = str(row["object_id"])
            if oid == owner or oid in tombstones:
                continue
            bucket = ring.setdefault(owner, [])
            if len(bucket) >= limit:
                continue
            visited = seen.setdefault(owner, set())
            if oid in visited:
                continue
            visited.add(oid)
            bucket.append(oid)
        return ring

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


    def _catch_up_annotations(self, conn: sqlite3.Connection) -> int:
        """同步外挂注记表（retrospective_annotations）进入多维搜索投影。

        返回本次投影的注记条数；同步完成后写入清单指纹，供
        ``sync_annotations`` 判断注记是否有变化（幂等，不重复写）。
        """

        try:
            rows = self._select_annotation_rows(conn)
            if rows is None:
                return 0
            fingerprint = _annotation_fingerprint(rows)
            for r in rows:
                anno_id = str(r[0])
                target_id = str(r[1])
                target_type = str(r[2])
                claim_text = str(r[3])
                is_inv = int(r[4])
                created_at = str(r[5])
                created_by = str(r[6])
                dim = derive_dimension({"value": claim_text}, "reinterpretation")

                tokens = set(tokens_for(claim_text))
                tokens.add(_id_token("sub", "user_1"))
                tokens.add(_id_token("ref", target_id))
                tokens.add(_id_token("ent", target_id))
                tokens.add(_id_token("anno", anno_id))
                tokens.add(_id_token("dim", dim))

                conn.execute(
                    "INSERT OR REPLACE INTO search_annotations(annotation_id, target_object_id, target_object_type, "
                    "reinterpretation_claim, is_invalidating, created_at, created_by, dimension) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (anno_id, target_id, target_type, claim_text, is_inv, created_at, created_by, dim),
                )
                if tokens:
                    conn.executemany(
                        "INSERT OR IGNORE INTO search_postings(token, object_id, revision) VALUES(?,?,?)",
                        [(t, anno_id, 1) for t in tokens],
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO search_doc(object_id, revision, haystack, excerpt) VALUES(?,?,?,?)",
                    (anno_id, 1, claim_text.lower(), claim_text[:_EXCERPT_LIMIT]),
                )
                us = 0
                try:
                    us = int(datetime.fromisoformat(created_at).astimezone(timezone.utc).timestamp() * 1_000_000)
                except Exception:
                    pass
                conn.execute(
                    "INSERT OR REPLACE INTO search_occurred(object_id, revision, subject_id, object_type, "
                    "occurred_start_us, occurred_end_us, dimension) VALUES(?,?,?,?,?,?,?)",
                    (anno_id, 1, "user_1", "reinterpretation", us, us, dim),
                )
            conn.execute(
                "INSERT OR REPLACE INTO search_meta(key, value) VALUES(?, ?)",
                (_ANNO_FINGERPRINT_KEY, fingerprint),
            )
            return len(rows)
        except Exception:
            return 0

    def search_mind(
        self,
        keywords: Sequence[str] = (),
        *,
        dimension: Optional[str] = None,
        claim_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        annotation_id: Optional[str] = None,
        object_types: Optional[Sequence[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        include_annotations: bool = True,
        limit: int = 20,
    ) -> MindSearchPage:
        """宪法第二十章：多维心智联合感知检索入口。

        原生支持按**维度（Dimension）、主张（Claim）、实体（Entity）、注记（Annotation）**
        的多维正交联合精准检索，兼具时空窗剪裁与极简 Token 输出。
        """
        current = int(self._store.current_world_revision())
        wm_before = self.watermark()
        if wm_before < current:
            self.catch_up()
        else:
            # 索引已追平世界，但注记可能刚挂上：稳态下同样要保证
            # 「今天挂的标签今天可召回」（宪法第二十章）。
            self.sync_annotations()
        wm = self.watermark()

        search_tokens: set[str] = set()
        for kw in keywords:
            search_tokens |= tokens_for(kw)
        if entity_id:
            search_tokens.add(_id_token("ent", entity_id))
            search_tokens.add(_id_token("ref", entity_id))
        if claim_id:
            search_tokens.add(_id_token("ref", claim_id))
        if annotation_id:
            search_tokens.add(_id_token("anno", annotation_id))

        with self._connect() as conn:
            # 如果提供了 search_tokens，根据 postings 交集加速
            if search_tokens:
                expanded_tokens = set(search_tokens)
                for kw in keywords:
                    ent_rows = conn.execute(
                        "SELECT entity_object_id FROM search_alias WHERE alias_norm=?",
                        (normalize_alias(kw),),
                    ).fetchall()
                    for (eid,) in ent_rows:
                        expanded_tokens.add(_id_token("ent", eid))
                        expanded_tokens.add(_id_token("ref", eid))
                        for (anorm,) in conn.execute(
                            "SELECT alias_norm FROM search_alias WHERE entity_object_id=?", (eid,)
                        ):
                            expanded_tokens |= tokens_for(anorm)

                hits_map = self._postings_for(conn, expanded_tokens)
                candidate_pairs = set(hits_map.keys())
            else:
                candidate_pairs = None

            params: list[Any] = []
            clauses = ["1=1"]
            if dimension:
                clauses.append("o.dimension = ?")
                params.append(dimension)
            if claim_id:
                clauses.append("(o.object_id = ? OR o.object_id IN (SELECT object_id FROM search_postings WHERE token = ?))")
                params.extend([claim_id, _id_token("ref", claim_id)])
            if annotation_id:
                clauses.append("(o.object_id = ? OR o.object_id IN (SELECT target_object_id FROM search_annotations WHERE annotation_id = ?))")
                params.extend([annotation_id, annotation_id])
            if object_types:
                placeholders = ",".join("?" for _ in object_types)
                clauses.append(f"o.object_type IN ({placeholders})")
                params.extend(object_types)
            if time_range:
                t0 = int(time_range[0].astimezone(timezone.utc).timestamp() * 1_000_000)
                t1 = int(time_range[1].astimezone(timezone.utc).timestamp() * 1_000_000)
                clauses.append(
                    "o.occurred_start_us IS NOT NULL AND NOT (COALESCE(o.occurred_end_us, o.occurred_start_us) < ? OR o.occurred_start_us > ?)"
                )
                params.extend([t0, t1])

            # 排除墓碑
            tombstones = {r[0] for r in conn.execute("SELECT object_id FROM search_tombstones").fetchall()}

            where_sql = " AND ".join(clauses)
            sql = f"""
                SELECT o.object_id, o.revision, o.object_type, o.subject_id, o.dimension,
                       d.haystack, d.excerpt
                FROM search_occurred o
                JOIN search_doc d ON d.object_id = o.object_id AND d.revision = o.revision
                WHERE {where_sql}
                ORDER BY o.occurred_start_us DESC
            """
            rows = conn.execute(sql, params).fetchall()

            mind_hits: list[MindSearchHit] = []
            total_toks = 0
            retrieved_object_ids: set[str] = set()

            for r in rows:
                oid = r["object_id"]
                rev = int(r["revision"])
                if oid in tombstones:
                    continue
                if candidate_pairs is not None and (oid, rev) not in candidate_pairs:
                    continue

                haystack = r["haystack"] or ""
                matched_all = True
                for kw in keywords:
                    if kw.lower() in haystack:
                        continue
                    resolved = sorted({
                        row[0] for row in conn.execute(
                            "SELECT entity_object_id FROM search_alias WHERE alias_norm=?", (normalize_alias(kw),)
                        ).fetchall()
                    })
                    if resolved:
                        alias_variants = [row[0] for row in conn.execute(
                            "SELECT alias_norm FROM search_alias WHERE entity_object_id = ?", (resolved[0],)
                        ).fetchall()]
                        if any(v in haystack for v in alias_variants):
                            continue
                        tok1 = _id_token("ent", resolved[0])
                        tok2 = _id_token("ref", resolved[0])
                        has_link = conn.execute(
                            "SELECT 1 FROM search_postings WHERE token IN (?,?) AND object_id=? LIMIT 1",
                            (tok1, tok2, oid),
                        ).fetchone()
                        if has_link:
                            continue

                    matched_all = False
                    break

                if not matched_all:
                    continue

                is_anno = (r["object_type"] == "reinterpretation")
                excerpt = r["excerpt"] or ""
                est_tok = max(10, len(excerpt) // 3)
                total_toks += est_tok
                retrieved_object_ids.add(oid)

                mind_hits.append(
                    MindSearchHit(
                        object_id=oid,
                        revision=rev,
                        object_type=r["object_type"],
                        subject_id=r["subject_id"],
                        score=10 if is_anno else _TYPE_BOOST.get(r["object_type"], 1),
                        dimension=r["dimension"] or "dim_general",
                        excerpt=excerpt,
                        is_annotation=is_anno,
                        estimated_tokens=est_tok,
                    )
                )
                if len(mind_hits) >= limit:
                    break

            # 伴随外挂注记联动（如果包含注记且命中列表中有被注记的目标）
            if include_annotations and retrieved_object_ids:
                placeholders = ",".join("?" for _ in retrieved_object_ids)
                anno_rows = conn.execute(
                    f"""
                    SELECT annotation_id, target_object_id, target_object_type,
                           reinterpretation_claim, dimension
                    FROM search_annotations
                    WHERE target_object_id IN ({placeholders})
                    """,
                    list(retrieved_object_ids),
                ).fetchall()
                for ar in anno_rows:
                    aid = str(ar[0])
                    if aid not in retrieved_object_ids:
                        claim_txt = str(ar[3])
                        est_a_tok = max(10, len(claim_txt) // 3)
                        total_toks += est_a_tok
                        mind_hits.append(
                            MindSearchHit(
                                object_id=aid,
                                revision=1,
                                object_type="reinterpretation",
                                subject_id="user_1",
                                score=15,  # 外挂注记拥有最高解释权
                                dimension=str(ar[4]) or "dim_general",
                                excerpt=f"[外挂注记/老王案] 指向 {ar[1]}: {claim_txt}",
                                is_annotation=True,
                                estimated_tokens=est_a_tok,
                            )
                        )

            # 排序：外挂注记与核心主张排在最前
            mind_hits.sort(key=lambda h: (-h.score, -h.revision))

            intent_parts = list(keywords)
            if dimension:
                intent_parts.append(f"dim:{dimension}")
            if claim_id:
                intent_parts.append(f"claim:{claim_id}")
            if entity_id:
                intent_parts.append(f"entity:{entity_id}")
            if annotation_id:
                intent_parts.append(f"anno:{annotation_id}")

            return MindSearchPage(
                status="ok",
                lag=current - wm,
                world_revision=current,
                index_watermark=wm,
                hits=mind_hits[:limit],
                total_estimated_tokens=total_toks,
                query_intent=" ".join(intent_parts) or "all",
            )

    # ---------------- 快捷多维原语接口 ----------------

    def search_by_dimension(self, dimension: str, keywords: Sequence[str] = (), limit: int = 20) -> MindSearchPage:
        """按特定维度聚焦检索（如 dim_health, dim_finance, dim_social, dim_work）。"""
        return self.search_mind(keywords=keywords, dimension=dimension, limit=limit)

    def search_by_claim(self, claim_id: str, keywords: Sequence[str] = (), limit: int = 20) -> MindSearchPage:
        """按主张与证据链因果检索。"""
        return self.search_mind(keywords=keywords, claim_id=claim_id, limit=limit)

    def search_by_entity(self, entity_id: str, keywords: Sequence[str] = (), limit: int = 20) -> MindSearchPage:
        """按实体关系网络检索。"""
        return self.search_mind(keywords=keywords, entity_id=entity_id, limit=limit)

    def search_by_annotation(self, annotation_id: str, limit: int = 20) -> MindSearchPage:
        """按外挂解释图层检索。"""
        return self.search_mind(annotation_id=annotation_id, limit=limit)


# 别名导出与类型对齐（最高法统命名规范）
MultidimensionalSearchEngine = WorldSearchIndex
