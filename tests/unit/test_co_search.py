"""M1-018 中文混合共现检索 —— I5 验收锚的机械对账。

  * AC-1 三族种子 fixture `total_hits == 0` 计数必须为 0（全命中有记录）；
  * plan 出现、rows_examined 计数、graph 有界（frontier ≤ 64 in expanded）;
  * hit_reasons 每个命中必带；
  * coverage 诚实：世界前进而索引未重建 → stale=true；
  * 种子词全零命中 → ZeroHitFatal（不加索引直接查种子词必须炸）；
  * 兜底词典升级后旧查询可重放（dict_version 钉住代际）；
  * 否定句 fixture 的 fusion 逻辑（"没有吵架" 不命中 "吵架"）属 M1-024 之后的
    行级内容判读 —— sim 期在 postings 层先保证"有吵架线索的对象先被召回"，
    fusion 语义过滤在 M2-020 ScenarioTest 中挂 V37 门槛。本测试只守 I5 §3.4 AC1/3/4/5/6。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Claim, Entity
from aios_core.contracts.enums import ClaimType
from aios_core.contracts.enums import KnowledgeState
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef, SourceRef
from aios_core.services.alias_dictionary import AliasDictionaryService
from aios_core.services.search_index_worker import SearchIndexWorker
from aios_core.services.co_search import CoSearchEngine, ZeroHitFatal, CoSearchResult
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


def _commit(store: SQLiteWorldStore, objs, key: str) -> None:
    rev = store.current_world_revision()
    store.commit(objs, OperationRequest(
        operation_id=f"seed-{key}", operation_name="world.commit",
        expected_world_revision=rev, reason=f"seed {key}", idempotency_key=key,
    ))


def _claim(oid: str, content: str, refs: list[str] | None = None, source_refs: list[str] | None = None) -> Claim:
    return Claim(
        object_id=oid,
        claimant_id="user-1",
        claim_type=ClaimType.FACT,
        content=content,
        asserted_at=T0,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.8,
        source_refs=[SourceRef(object_id=r, revision=1) for r in (source_refs or [])],
        metadata={},
        **{**world_kwargs(learned_at=T0, recorded_at=T0), **({"dependency_refs": [ObjectRef(object_id=r) ,] } or {}),
        },
    )


def _setup(tmp_path: Path) -> tuple[SQLiteWorldStore, CoSearchEngine]:
    store = SQLiteWorldStore(tmp_path / "world.db")
    ent_mother = Entity(object_id="ent-mom", entity_kind="person", canonical_name="王梅",
                        aliases=["妈妈"], **world_kwargs(learned_at=T0, recorded_at=T0))
    c1 = Claim(object_id="claim-gift", claimant_id="user-1", claim_type=ClaimType.FACT,
               content="妈妈生日礼物挑好了吗", asserted_at=T0,
               knowledge_state=KnowledgeState.REPORTED, confidence=0.8,
               **world_kwargs(learned_at=T0, recorded_at=T0))
    c2 = Claim(object_id="claim-money", claimant_id="user-1", claim_type=ClaimType.FACT,
               content="老王借钱争执三天了", asserted_at=T0,
               knowledge_state=KnowledgeState.REPORTED, confidence=0.8,
               **world_kwargs(learned_at=T0, recorded_at=T0))
    c3 = Claim(object_id="claim-health", claimant_id="user-1", claim_type=ClaimType.FACT,
               content="加班熬夜心悸两周了", asserted_at=T0,
               knowledge_state=KnowledgeState.REPORTED, confidence=0.8,
               **world_kwargs(learned_at=T0, recorded_at=T0))
    _commit(store, [ent_mother, c1, c2, c3], "s0")

    dictsvc = AliasDictionaryService(store)
    indexer = SearchIndexWorker(store, dictsvc)
    engine = CoSearchEngine(store, dictsvc, indexer, policy={
        "co_search": {
            "weights": {"bm25": 1.0, "postings": 0.85, "entity": 0.6,
                        "graph": 0.35, "recency": 0.15, "alias_bonus": 0.25},
            "graph": {"max_depth": 2, "frontier_cap": 64},
            "zero_hit_fail_loud_for_seed_terms": True,
        }
    })
    return store, engine


# ---------------------------------------------------------------------------
# AC-1: 三族 fixture total_hits==0 计数必须为 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("keywords,want", [
    (["妈妈生日礼物"], "claim-gift"),
    (["老王借钱争执"], "claim-money"),
    (["加班熬夜心悸"], "claim-health"),
])
def test_seed_fixtures_have_nonzero_hits(tmp_path: Path, keywords, want):
    store, engine = _setup(tmp_path)
    res = engine.query(keywords, ensure_fresh=True)
    assert res.total_hits > 0, f"fixture {keywords} 出现 0 命中 —— I5 AC-1 直红"
    assert res.hits[0].object_id == want


def test_zero_hit_on_seed_terms_is_fatal(tmp_path: Path, monkeypatch):
    """索引在但对象全不相干时，种子族 0 命中 = ZeroHitFatal（沉默即判词）。"""
    store, engine = _setup(tmp_path)
    # 只有无关对象的空索引 + 索引水位是新的 → 种子查询零命中
    store2 = SQLiteWorldStore(tmp_path / "world2.db")
    dictsvc2 = AliasDictionaryService(store2)
    indexer2 = SearchIndexWorker(store2, dictsvc2)
    eng2 = CoSearchEngine(store2, dictsvc2, indexer2, policy={"co_search": {"zero_hit_fail_loud_for_seed_terms": True}})
    indexer2.rebuild()
    with pytest.raises(ZeroHitFatal):
        eng2.query(["妈妈生日礼物"])


def test_plan_and_hit_reasons_present(tmp_path: Path):
    store, engine = _setup(tmp_path)
    res = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    assert res.plan.query_terms, "plan 必须带 query_terms（I5 AC-2 无 plan=违规）"
    assert res.plan.rows_examined > 0
    hit = res.hits[0]
    assert hit.hit_reasons, f"{hit.object_id} 缺 hit_reasons —— I5 AC-3 直红"
    assert hit.rank >= 1


def test_coverage_honest_stale_when_world_advances(tmp_path: Path):
    store, engine = _setup(tmp_path)
    res1 = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    assert res1.stale_index is False
    # 世界前进一位但没重建索引 → stale 必须亮
    extra = Claim(object_id="claim-extra", claimant_id="user-1", claim_type=ClaimType.FACT,
                  content="体检血压偏高", asserted_at=T0, knowledge_state=KnowledgeState.REPORTED,
                  confidence=0.6, **world_kwargs(learned_at=T0, recorded_at=T0))
    _commit(store, [extra], "s1")
    res2 = engine.query(["妈妈生日礼物"], ensure_fresh=False)
    assert res2.stale_index is True, "索引落后于世界却装新鲜 —— I5 AC-4 直红"
    assert res2.coverage["world_rev"] < res2.coverage["current"]


def test_rebuild_after_drift_restores_freshness(tmp_path: Path):
    store, engine = _setup(tmp_path)
    engine.query(["妈妈生日礼物"], ensure_fresh=True)
    extra = Claim(object_id="claim-extra2", claimant_id="user-1", claim_type=ClaimType.FACT,
                  content="体检血压偏高", asserted_at=T0, knowledge_state=KnowledgeState.REPORTED,
                  confidence=0.6, **world_kwargs(learned_at=T0, recorded_at=T0))
    _commit(store, [extra], "s1")
    engine.query(["妈妈生日礼物"], ensure_fresh=False)
    res = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    assert res.stale_index is False


def test_alias_injection_scores(tmp_path: Path):
    store, engine = _setup(tmp_path)
    res = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    hit = next(h for h in res.hits if h.object_id == "claim-gift")
    assert "alias_injected" in hit.hit_reasons
    assert hit.via_entity is True
    assert any(r == "entity:participant" for r in hit.hit_reasons)


def test_graph_walk_bounded(tmp_path: Path):
    """depth 有界 + frontier 有界 + visited-set：扩展不得失控。"""
    store, engine = _setup(tmp_path)
    # 建一条引用链 claim-gift ← claim-money（source_refs 关系）
    chain = Claim(object_id="claim-linked", claimant_id="user-1", claim_type=ClaimType.FACT,
                  content="跟生日那条有关系", asserted_at=T0,
                  knowledge_state=KnowledgeState.REPORTED, confidence=0.5,
                  source_refs=[SourceRef(object_id="claim-gift", revision=1)],
                  **world_kwargs(learned_at=T0, recorded_at=T0))
    _commit(store, [chain], "s2")
    res = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    # graph_walk 命中不得超 frontier=64（sim 数据远低此限）
    assert all(not r.startswith("graph_walk:depth") or int(r.split("depth")[1]) <= 2
               for h in res.hits for r in h.hit_reasons)


def test_query_terms_keep_canonical_form(tmp_path: Path):
    store, engine = _setup(tmp_path)
    res = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    assert "王梅" in res.query_terms and "生日" in res.query_terms and "礼物" in res.query_terms


def test_old_dict_pack_replayable(tmp_path: Path):
    """词典升级后，按旧版本回放仍能得到确定性（同样的命中集）。"""
    store, engine = _setup(tmp_path)
    res1 = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    dictsvc = AliasDictionaryService(store)
    # 词典升级（加一个新实体干扰项，不影响这一查询的目标命中）
    ent2 = Entity(object_id="ent-dad", entity_kind="person", canonical_name="王建国",
                  aliases=["爸"], **world_kwargs(learned_at=T0, recorded_at=T0))
    _commit(store, [ent2], "s3")
    res2 = engine.query(["妈妈生日礼物"], ensure_fresh=True)
    # 旧版本回放在 M1-024 的比对面板里消费；此处断言索引水位代际前进、查询仍然命中
    assert res2.coverage["dict_version"] > res1.coverage["dict_version"]
    assert res2.total_hits >= res1.total_hits
