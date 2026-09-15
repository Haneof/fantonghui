"""M1-018 · Co-Search Index Worker —— 世界树 → postings/FTS/entity 倒排位面。

不是查询期的临时拼接，是 M1-021 物化支座的姊妹：索引是**可重建的派生事实**，
可随词典版本整体重建，重建期间老老实实广播 STALE，
绝不把旧一代词典吐出的结果说成本代完整结果。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..storage.lexicon_schema import ensure_lexicon_schema
from ..storage.sqlite_store import SQLiteWorldStore
from .alias_dictionary import AliasDictionaryService, DictPack

LANE = "co_search"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _body_of(payload: dict) -> str | None:
    """从对象 payload 提取检索文本（失败不哑，返回 None）。什么对象的文本算文本，
    由对象自己的字段说——不挖字段意义，不做 LLM 二次解读。"""
    kind = payload.get("object_type")
    if kind == "claim":
        return payload.get("content")
    if kind in ("conversation_turn", "observation", "entity"):
        parts = [payload.get("utterance") or payload.get("value") or payload.get("canonical_name")]
        aliases = payload.get("aliases") or []
        parts.extend(a for a in aliases if isinstance(a, str))
        return " ".join(p for p in parts if p) or None
    if kind == "summary":
        return payload.get("content") or payload.get("title")
    if kind in ("goal",):
        return payload.get("title") or payload.get("statement")
    return None


class SearchIndexWorker:
    """建/重建；确定性（同投影+同词典包 ⇒ 同 postings 集，只是重放）。"""

    def __init__(self, store: SQLiteWorldStore, dictsvc: AliasDictionaryService) -> None:
        self._store = store
        self._dict = dictsvc

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(self._store.db_path))
        conn.row_factory = sqlite3.Row
        ensure_lexicon_schema(conn)
        return conn

    def rebuild(self, *, source: str = "entity_aliases") -> dict[str, Any]:
        """全体重建：先清老 postings（当前 dict_version 代际），再插新，原子落水位。"""
        pack: DictPack = self._dict.build_pack(source=source)
        rev = self._store.current_world_revision()

        term_rows: dict[tuple[str, str], dict] = {}
        ent_rows: set[tuple[str, str, str]] = set()
        dep_rows: set[tuple[str, str, int, str]] = set()
        fts_rows: list[tuple[str, str]] = []
        count = 0

        for p in self._store.list_payloads():
            oid = p.get("object_id")
            if not oid or p.get("object_type") == "retention_tombstone":
                continue
            body = _body_of(p)
            if not body:
                continue
            count += 1

            inj = self._dict.inject([body], pack=pack, record_misses=False)
            n_terms = len(inj.canonical_terms) or 1
            weight = 1.0 / (n_terms ** 0.5)
            for term in inj.canonical_terms:
                key = (term, oid)
                if key not in term_rows:
                    term_rows[key] = {
                        "term": term, "object_id": oid, "weight": weight,
                        "dict_version": pack.version,
                    }
            for hit in inj.alias_hits:
                if hit.entity_id:
                    role = "participant" if hit.keyword in body else "mention"
                    ent_rows.add((hit.entity_id, oid, role))

            # 深度=1 图边物化：对象 → 其 ObjectRef 直指的兄弟（边型用字段名标注）
            for ref_key, ref_val in p.items():
                if isinstance(ref_val, dict) and "object_id" in ref_val and "revision" in ref_val:
                    dep_rows.add((oid, ref_val["object_id"], 1, ref_key))
                elif isinstance(ref_val, list):
                    for item in ref_val:
                        if isinstance(item, dict) and "object_id" in item and "revision" in item:
                            dep_rows.add((oid, item["object_id"], 1, ref_key))

            # FTS 面：给 unicode61 喂已经按词典切好的 token 串（它唯一擅长的任务：切空格）
            fts_rows.append((oid, " ".join(inj.canonical_terms)))

        with self._connect() as conn:
            conn.execute("DELETE FROM term_postings")
            conn.execute("DELETE FROM entity_postings")
            conn.execute("DELETE FROM dependency_walk_cache")
            conn.execute("DELETE FROM object_fts")
            conn.executemany(
                "INSERT OR REPLACE INTO term_postings(term, object_id, weight, dict_version, is_alias)"
                " VALUES (:term, :object_id, :weight, :dict_version, 0)",
                term_rows.values(),
            )
            conn.executemany(
                "INSERT OR REPLACE INTO entity_postings(entity_id, object_id, role) VALUES (?,?,?)",
                sorted(ent_rows),
            )
            conn.executemany(
                "INSERT OR REPLACE INTO dependency_walk_cache(src, dst, depth, edge_types) VALUES (?,?,?,?)",
                sorted(dep_rows),
            )
            conn.executemany("INSERT INTO object_fts(object_id, body) VALUES (?,?)", fts_rows)
            conn.execute(
                "INSERT OR REPLACE INTO index_watermark(lane, world_rev, object_count, built_at, dict_version)"
                " VALUES (?,?,?,?,?)",
                (LANE, rev, count, _now_iso(), pack.version),
            )
            conn.commit()
        return {
            "objects_indexed": count, "world_rev": rev, "dict_version": pack.version,
            "terms": len(term_rows), "entity_links": len(ent_rows), "dep_edges": len(dep_rows),
        }

    def coverage(self) -> dict[str, Any]:
        """索引水位的诚实面。stale = 水位落后于世界 revision。"""
        world_rev = self._store.current_world_revision()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM index_watermark WHERE lane=?", (LANE,)
            ).fetchone()
        if row is None:
            return {"lane": LANE, "world_rev": None, "current": world_rev,
                    "stale": True, "stale_reason": "index_never_built", "coverage": 0.0}
        stale = int(row["world_rev"]) < world_rev
        return {
            "lane": LANE,
            "world_rev": int(row["world_rev"]),
            "current": world_rev,
            "stale": stale,
            "stale_reason": "world_advanced_since_index" if stale else "fresh",
            "dict_version": int(row["dict_version"]),
            "object_count": int(row["object_count"]),
            "coverage": float(int(row["world_rev"]) / world_rev) if world_rev else 1.0,
        }


__all__ = ["LANE", "SearchIndexWorker"]
