"""M1-023 Alias Dictionary —— 词典资产层的确定性测试。

验收锚（R4 §M1-023 + I5 前置）：
  * 内容寻址 + 单调版本：同内容同 pack（重放），内容漂移 version+1，旧行封存；
  * Entity aliases 自动入典（canonical + alias 双项）；
  * 注入确定性：同 pack 同关键词同结果（seed terms 覆盖宪法 §89 崩溃八词族）；
  * 歧义标记只标记不裁决（词典不是语义法官，fusion 层才是）；
  * miss 清单：未命中 CJK 词落 alias_miss_log，频次聚合 = 词典升级输入。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Entity
from aios_core.contracts.operations import OperationRequest
from aios_core.services.alias_dictionary import (
    AliasDictionaryService,
    BUILTIN_SEED_TERMS,
    DictPack,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

T = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path: Path, *, seeded_entities: tuple[tuple[str, list[str]], ...] = ()) -> SQLiteWorldStore:
    store = SQLiteWorldStore(tmp_path / "world.db")
    if seeded_entities:
        objs = [
            Entity(
                object_id=f"ent-{i}",
                entity_kind="person",
                canonical_name=canonical,
                aliases=aliases,
                **world_kwargs(learned_at=T, recorded_at=T),
            )
            for i, (canonical, aliases) in enumerate(seeded_entities)
        ]
        rev = store.current_world_revision()
        store.commit(objs, OperationRequest(
            operation_id="seed-entities", operation_name="world.commit",
            expected_world_revision=rev, reason="seed entities",
            idempotency_key="seed-entities",
        ))
    return store


def _svc(store: SQLiteWorldStore) -> AliasDictionaryService:
    return AliasDictionaryService(store)


# ---------------------------------------------------------------------------
# 构建与版本化
# ---------------------------------------------------------------------------


def test_build_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path, seeded_entities=(("王梅", ["妈妈", "梅梅"]),))
    svc = _svc(store)
    p1 = svc.build_pack()
    p2 = svc.build_pack()
    assert p1.pack_id == p2.pack_id
    assert p1.version == p2.version == 1
    assert p1.terms_sha == p2.terms_sha


def test_content_drift_bumps_version_and_preserves_old_pack(tmp_path: Path) -> None:
    store = _store(tmp_path, seeded_entities=(("王梅", ["妈妈"]),))
    svc = _svc(store)
    v1 = svc.build_pack()

    # 世界漂移：新增实体别名 → 重新入库再构建
    more = Entity(
        object_id="ent-100", entity_kind="person", canonical_name="王建国",
        aliases=["爸爸", "老王"], **world_kwargs(learned_at=T, recorded_at=T),
    )
    rev = store.current_world_revision()
    store.commit([more], OperationRequest(
        operation_id="seed-more", operation_name="world.commit",
        expected_world_revision=rev, reason="seed", idempotency_key="seed-more",
    ))
    v2 = svc.build_pack()
    assert v2.version == 2 and v2.pack_id != v1.pack_id

    # 旧包可重放（I5 AC-1：词典升级后旧结果可对照）
    replay = svc.pack_by_version(1)
    assert replay is not None and replay.terms_sha == v1.terms_sha
    surfaces_v1 = {e.surface for e in replay.entries}
    assert "老王" not in surfaces_v1
    assert "老王" in {e.surface for e in v2.entries}


def test_entity_alias_and_canonical_both_indexed(tmp_path: Path) -> None:
    store = _store(tmp_path, seeded_entities=(("王梅", ["妈妈", "老妈"]),))
    pack = _svc(store).build_pack()
    idx = pack.surface_index()
    hit_alias = idx["妈妈"]
    # 实体别名指向 canonical 本人；内置种子同面共存（防线不因撞名而消失）
    assert "王梅" in {e.canonical for e in hit_alias}
    assert "妈妈" in {e.canonical for e in hit_alias}
    assert any(e.kind == "entity_alias" for e in idx["妈妈"])
    assert any(e.kind == "entity_canonical" for e in idx["王梅"])


def test_builtin_seeds_cover_constitution_crash_corpus() -> None:
    """宪法 §89 的零命中八词族必须在内置种子里——这不是覆盖，是防线。"""
    seeds = {s for s, _ in BUILTIN_SEED_TERMS}
    for word in ("妈妈", "生日", "礼物", "加班", "熬夜", "心悸", "借钱", "争执"):
        assert word in seeds, f"种子表漏掉崩溃语料: {word}"


# ---------------------------------------------------------------------------
# 注入
# ---------------------------------------------------------------------------


def test_inject_resolves_alias_to_canonical_without_ambiguity(tmp_path: Path) -> None:
    store = _store(tmp_path, seeded_entities=(("王梅", ["妈妈"]),))
    svc = _svc(store)
    svc.build_pack()
    r = svc.inject(["妈妈"])
    assert "王梅" in r.canonical_terms
    hit = next(h for h in r.alias_hits if h.keyword == "妈妈")
    assert hit.canonical == "王梅" and hit.entity_id is not None
    assert hit.ambiguous is False
    assert r.misses == []


def test_inject_segments_continuous_cjk_longest_match(tmp_path: Path) -> None:
    """unicode61 零命中的判词的物理出口：最长匹配切出词典词。"""
    store = _store(tmp_path, seeded_entities=(("王梅", ["妈妈"]),))
    svc = _svc(store)
    svc.build_pack()
    r = svc.inject(["妈妈生日礼物"])
    assert "王梅" in r.canonical_terms
    assert "生日" in r.canonical_terms and "礼物" in r.canonical_terms


def test_inject_same_pack_same_keywords_same_result(tmp_path: Path) -> None:
    store = _store(tmp_path, seeded_entities=(("王梅", ["妈妈"]),))
    svc = _svc(store)
    svc.build_pack()
    a = svc.inject(["妈妈", "生日"], record_misses=False)
    b = svc.inject(["妈妈", "生日"], record_misses=False)
    assert a.canonical_terms == b.canonical_terms
    assert [ (h.keyword, h.canonical, h.ambiguous) for h in a.alias_hits ] == [
        (h.keyword, h.canonical, h.ambiguous) for h in b.alias_hits
    ]


def test_ambiguous_surface_is_flagged_not_adjudicated(tmp_path: Path) -> None:
    store = _store(tmp_path, seeded_entities=(("王梅", ["老妈"]), ("李秀", ["老妈"])))
    svc = _svc(store)
    svc.build_pack()
    r = svc.inject(["老妈"])
    hit = next(h for h in r.alias_hits if h.keyword == "老妈")
    assert hit.ambiguous is True
    # canonical_terms 两党都上桌——裁决权在 fusion 不在词典
    assert set(r.canonical_terms) >= {"王梅", "李秀"}


def test_manual_extra_terms_participate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    svc = _svc(store)
    svc.build_pack(extra_terms=[("深海路8号", "公司", "ent-loc-1")])
    r = svc.inject(["深海路8号"])
    assert "公司" in r.canonical_terms


# ---------------------------------------------------------------------------
# miss 清单
# ---------------------------------------------------------------------------


def test_misses_are_logged_with_frequency(tmp_path: Path) -> None:
    store = _store(tmp_path)
    svc = _svc(store)
    svc.build_pack()
    svc.inject(["耽心", "耽心"])  # 「耽心」不在词表 → miss ×1 次调用（同调用去重外计）
    svc.inject(["耽心"])
    report = svc.miss_report()
    row = next((r for r in report if r["surface"] == "耽心"), None)
    assert row is not None and row["occurrences"] >= 1
    # 版本化：miss 记录带字典版本，词典升级后可分清是哪一代的锅
    assert row["dict_version"] == 1


def test_ascii_only_noncjk_is_not_a_dictionary_bug(tmp_path: Path) -> None:
    store = _store(tmp_path)
    svc = _svc(store)
    svc.build_pack()
    r = svc.inject(["heartbeat"])
    assert r.misses == [], "非 CJK 词不进词典 bug 清单（词典只背中文的锅）"
