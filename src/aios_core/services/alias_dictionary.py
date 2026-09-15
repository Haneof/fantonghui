"""M1-023 · Alias Dictionary & Entity Canonical Injection.

宪法 §89 的物理前提：中文是连续字符串，unicode61 对「妈妈生日」命中数是零——
词典/别名/预分词不是品味选择，是物理上绕不过的河（I5 规约原话）。本服务是
M1-018 共现检索引擎的词典资产层，职责三件，全部确定性：

  ① 词典构建：从世界树 Entity（canonical_name + aliases）+ 内置种子 + 人工
     增补，编译成一张版本化的 DictPack，落库 tokenizer_dict_pack（I5 DDL）。
  ② 版本化与重放：内容寻址（terms_sha）+ 单调 version；内容不变⇒同 pack 重放，
     内容漂移⇒新 version，旧版本行永不改写——词典升级必须可对照旧结果（I5 AC-1）。
  ③ 别名注入：把用户关键词解析成 (canonical_terms, alias_hits, misses)；
     misses 落 alias_miss_log——词典 bug 自动清单源（I5 观测指标
     alias_miss_log_count 的出处）。

确定性纪律：注入与分段零模型调用；同一 pack + 同一关键词 ⇒ 同一结果。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..contracts.enums import ObjectType
from ..storage.lexicon_schema import ensure_lexicon_schema
from ..storage.sqlite_store import SQLiteWorldStore

# 内置种子：宪法 §89 举例族 + 高频亲属/情绪/动作 2~3 字词。
# 这不是语言学工程，是"崩溃点八词不能保证 0 命中"的最低防线；
# 每个种子必须能在词典 bug 清单流出后增补，而不是写死后遗忘。
BUILTIN_SEED_TERMS: tuple[tuple[str, str], ...] = tuple(sorted({
    ("妈妈", "妈妈"), ("生日", "生日"), ("礼物", "礼物"),
    ("爸爸", "爸爸"), ("加班", "加班"), ("熬夜", "熬夜"),
    ("心悸", "心悸"), ("借钱", "借钱"), ("争执", "争执"),
    ("吵架", "吵架"), ("体检", "体检"), ("血压", "血压"),
}))

_CJK = re.compile(r"[一-鿿]")
_MIN_MISS_LEN = 2

TermKind = str  # 'builtin' | 'entity_alias' | 'entity_canonical' | 'manual'


@dataclass(frozen=True, slots=True)
class DictEntry:
    surface: str          # 用户可能书写的字面（原形或别名）
    canonical: str        # 归一后的检索词形
    entity_id: str | None  # 注入实体解析时的归属
    kind: TermKind


@dataclass(frozen=True, slots=True)
class DictPack:
    pack_id: str
    version: int
    source: str
    created_rev: int
    terms_sha: str
    entries: tuple[DictEntry, ...]

    def surface_index(self) -> dict[str, list[DictEntry]]:
        idx: dict[str, list[DictEntry]] = {}
        for e in self.entries:
            idx.setdefault(e.surface, []).append(e)
            if e.canonical != e.surface:
                idx.setdefault(e.canonical, []).append(e)
        return idx


@dataclass(slots=True)
class AliasHit:
    keyword: str
    matched_surface: str
    canonical: str
    entity_id: str | None
    ambiguous: bool


@dataclass(slots=True)
class InjectionResult:
    dict_pack_id: str
    dict_version: int
    canonical_terms: list[str] = field(default_factory=list)
    alias_hits: list[AliasHit] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _terms_sha(entries: Iterable[DictEntry]) -> str:
    payload = _canonical_json([
        [e.surface, e.canonical, e.entity_id, e.kind] for e in entries
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _has_cjk(text: str) -> bool:
    return bool(_CJK.search(text))


def _segment(keyword: str, surfaces_by_len: list[str]) -> tuple[list[str], bool]:
    """极简最长匹配分段（确定性，向 unicode61 无能宣战的第一把刀）。

    返回 (tokens, fully_covered)。不走统计/模型——词典覆盖度由 miss 清单喂养。
    """
    if not keyword:
        return [], True
    tokens: list[str] = []
    i, n = 0, len(keyword)
    fully = True
    while i < n:
        hit = next((s for s in surfaces_by_len if keyword.startswith(s, i) and s), None)
        if hit:
            tokens.append(hit)
            i += len(hit)
        else:
            tokens.append(keyword[i])
            if _has_cjk(keyword[i]):
                fully = False
            i += 1
    return tokens, fully


class AliasDictionaryService:
    """tokenizer_dict_pack 的唯一写入者（与政府形态一致：词典是法律不是缓存）。"""

    SOURCE_PREFIX = "dict-"

    def __init__(self, store: SQLiteWorldStore) -> None:
        self._store = store

    # ------------------------------------------------------------ storage

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(self._store.db_path))
        conn.row_factory = sqlite3.Row
        ensure_lexicon_schema(conn)
        return conn

    # ------------------------------------------------------------ build

    def build_pack(
        self,
        *,
        extra_terms: Iterable[tuple[str, str, str]] = (),  # (surface, canonical, entity_id|None)
        source: str = "entity_aliases",
    ) -> DictPack:
        """构建（或等价重放）一份 DictPack。

        确定性：相同世界投影 + 相同 extra_terms ⇒ 相同 pack_id 与 version。
        内容漂移 ⇒ version 单调+1，旧行封存（可重放）。
        """
        entries: list[DictEntry] = [
            DictEntry(s, c, None, "builtin") for s, c in BUILTIN_SEED_TERMS
        ]
        for p in self._store.list_payloads(object_type=ObjectType.ENTITY):
            name = p.get("canonical_name")
            eid = p.get("object_id")
            if name:
                entries.append(DictEntry(name, name, eid, "entity_canonical"))
            for alias in p.get("aliases") or []:
                if alias and name:
                    entries.append(DictEntry(alias, name, eid, "entity_alias"))
        for surface, canonical, entity_id in extra_terms:
            entries.append(DictEntry(surface, canonical, entity_id or None, "manual"))

        # 冲突裁决：同 surface 多 canonical 全保留（ambiguity 在注入层标记），
        # 完全相同的四元组去重。排序保证与输入顺序无关。
        uniq = sorted({(e.surface, e.canonical, e.entity_id, e.kind): e for e in entries}.values(),
                      key=lambda e: (e.surface, e.canonical, e.entity_id or "", e.kind))
        sha = _terms_sha(uniq)
        created_rev = self._store.current_world_revision()

        with self._connect() as conn:
            latest = conn.execute(
                "SELECT * FROM tokenizer_dict_pack WHERE source=? ORDER BY version DESC LIMIT 1",
                (source,),
            ).fetchone()
            if latest is not None and latest["terms_sha"] == sha:
                return self._row_to_pack(latest)
            version = (latest["version"] + 1) if latest is not None else 1
            pack_id = f"{self.SOURCE_PREFIX}{source}-{version}-{_terms_sha([*uniq])[:12]}"
            conn.execute(
                "INSERT INTO tokenizer_dict_pack(pack_id, version, source, terms_json, terms_sha, created_rev)"
                " VALUES (?,?,?,?,?,?)",
                (pack_id, version, source, _canonical_json([
                    {"surface": e.surface, "canonical": e.canonical,
                     "entity_id": e.entity_id, "kind": e.kind} for e in uniq
                ]), sha, created_rev),
            )
            conn.commit()
            return DictPack(pack_id, version, source, created_rev, sha, tuple(uniq))

    def current_pack(self, *, source: str = "entity_aliases") -> DictPack | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tokenizer_dict_pack WHERE source=? ORDER BY version DESC LIMIT 1",
                (source,),
            ).fetchone()
            return self._row_to_pack(row) if row else None

    def pack_by_version(self, version: int, *, source: str = "entity_aliases") -> DictPack | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tokenizer_dict_pack WHERE source=? AND version=?",
                (source, version),
            ).fetchone()
            return self._row_to_pack(row) if row else None

    @staticmethod
    def _row_to_pack(row: sqlite3.Row) -> DictPack:
        raw = json.loads(row["terms_json"])
        entries = tuple(DictEntry(e["surface"], e["canonical"], e["entity_id"], e["kind"]) for e in raw)
        return DictPack(row["pack_id"], row["version"], row["source"],
                        row["created_rev"], row["terms_sha"], entries)

    # ------------------------------------------------------------ inject

    def inject(
        self,
        keywords: Iterable[str],
        *,
        pack: DictPack | None = None,
        record_misses: bool = True,
    ) -> InjectionResult:
        """别名注入：关键词 → canonical_terms / alias_hits / misses。

        别名指向同 canonical ⇒ 不歧义；指向多 canonical ⇒ ambiguous=True，
        由 M1-018 fusion 层裁决（词典层只供货，不做语意判决）。
        """
        pack = pack or self.current_pack() or self.build_pack()
        idx = pack.surface_index()
        surfaces_by_len = sorted(idx.keys(), key=len, reverse=True)

        result = InjectionResult(dict_pack_id=pack.pack_id, dict_version=pack.version)
        seen_terms: set[str] = set()

        for kw in keywords:
            if not kw or not str(kw).strip():
                continue
            kw = str(kw).strip()
            direct = idx.get(kw)
            if direct:
                self._absorb(result, kw, direct, seen_terms)
                continue
            tokens, fully = _segment(kw, surfaces_by_len)
            absorbed_any = False
            for tok in tokens:
                hit = idx.get(tok)
                if hit:
                    self._absorb(result, kw, hit, seen_terms, via=tok)
                    absorbed_any = True
            if not fully or not absorbed_any:
                if _has_cjk(kw) and len(kw) >= _MIN_MISS_LEN:
                    result.misses.append(kw)

        if record_misses:
            self._record_misses(result.misses, pack)
        return result

    @staticmethod
    def _absorb(
        result: InjectionResult,
        keyword: str,
        entries: list[DictEntry],
        seen: set[str],
        via: str | None = None,
    ) -> None:
        """注入裁决顺序：实体归因 > 词典词形。

        「妈妈」撞实体别名时，身份归因赢（它回答"在说谁"）；
        词典词形仍进 canonical_terms 供货 text postings（它回答"说什么"）。
        歧义只发生在实体层——多 canonical 或多 entity——不在词典与实体之间。
        """
        entity_entries = [e for e in entries if e.entity_id]
        all_canonicals = {e.canonical for e in entries}
        for canon in sorted(all_canonicals):
            if canon not in seen:
                seen.add(canon)
                result.canonical_terms.append(canon)
        if entity_entries:
            e_canonicals = {e.canonical for e in entity_entries}
            e_ids = {e.entity_id for e in entity_entries}
            result.alias_hits.append(AliasHit(
                keyword=keyword,
                matched_surface=via or keyword,
                canonical=sorted(e_canonicals)[0],
                entity_id=sorted(e_ids)[0],
                ambiguous=len(e_canonicals) > 1 or len(e_ids) > 1,
            ))
        else:
            result.alias_hits.append(AliasHit(
                keyword=keyword,
                matched_surface=via or keyword,
                canonical=sorted(all_canonicals)[0] if all_canonicals else keyword,
                entity_id=None,
                ambiguous=len(all_canonicals) > 1,
            ))

    def _record_misses(self, misses: Iterable[str], pack: DictPack) -> None:
        if not misses:
            return
        rev = self._store.current_world_revision()
        with self._connect() as conn:
            for surface in misses:
                conn.execute(
                    "INSERT INTO alias_miss_log(surface, dict_version, first_seen_rev, occurrences)"
                    " VALUES (?,?,?,1)"
                    " ON CONFLICT(surface, dict_version)"
                    " DO UPDATE SET occurrences = occurrences + 1",
                    (surface, pack.version, rev),
                )
            conn.commit()

    # ------------------------------------------------------------ audit

    def miss_report(self, *, min_occurrences: int = 1) -> list[Mapping[str, Any]]:
        """词典 bug 清单：未命中词按频率排序——词典升级的输入，不是摆设。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT surface, dict_version, occurrences, first_seen_rev"
                " FROM alias_miss_log WHERE occurrences >= ?"
                " ORDER BY occurrences DESC, surface ASC",
                (min_occurrences,),
            ).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "AliasDictionaryService",
    "AliasHit",
    "BUILTIN_SEED_TERMS",
    "DictEntry",
    "DictPack",
    "InjectionResult",
]
