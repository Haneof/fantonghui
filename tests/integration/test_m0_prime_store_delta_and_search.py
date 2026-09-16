"""M0-023 运行面迁移 + M1-017/018 检索核（预开工件）集成测试。

治理边界：本文件验证投影/迁移语义本身；接入唤醒/会话运行路径须待
M0-022R 签核与 M1 Gate（设计书 R4 §3.1）。
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts import (
    Claim,
    ClaimType,
    Entity,
    EventAnchor,
    KnowledgeState,
    MaintenanceClass,
    ObjectRef,
    Observation,
    ObjectType,
    OperationRequest,
    SourceClass,
    TemporalExtent,
    new_object_id,
)
from aios_core.query.search import WorldSearchIndex, tokens_for
from aios_core.storage import SQLiteWorldStore

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def op(store: SQLiteWorldStore, name: str, key: str, *, source: SourceClass = SourceClass.SENSOR,
       maintenance: MaintenanceClass | None = None) -> OperationRequest:
    return OperationRequest(
        operation_name=name,
        expected_world_revision=store.current_world_revision(),
        reason="m0-prime integration fixture",
        idempotency_key=key,
        source_class=source,
        maintenance_class=maintenance,
    )


def observation(object_id: str, text: str, *, at: datetime = NOW) -> Observation:
    return Observation(
        object_id=object_id, subject_id="user_1", occurred=TemporalExtent.point(at),
        learned_at=NOW, recorded_at=NOW, created_by="m0-prime-tests",
        source_kind="ambient_audio", modality="text", value=text,
    )


# ---------------------------------------------------------------- store side


def test_new_database_freezes_source_class_on_commits(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    store.commit([observation(new_object_id(ObjectType.OBSERVATION), "街边叫卖声")], op(store, "observation.write", "k1"))
    store.commit(
        [observation(new_object_id(ObjectType.OBSERVATION), "心跳巡检摘要")],
        op(store, "summary.mark_stale", "k2", source=SourceClass.MAINTENANCE, maintenance=MaintenanceClass.STALE_MARK),
    )
    current = store.current_world_revision()
    assert store.commit_source_class(1) == "sensor"
    assert store.commit_source_class(2) == "maintenance"
    triggerable = store.triggerable_commits_after(0)
    # R4-02 闭合点：维护写对触发评估结构性不可见
    assert [r["world_revision"] for r in triggerable] == [1]
    assert all(r["source_class"] != "maintenance" for r in triggerable)


def test_pre_r4_database_migrates_with_explicit_backfill_and_audit(tmp_path):
    db = tmp_path / "world.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE world_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO world_meta(key, value) VALUES ('world_revision', '3');
        CREATE TABLE world_commits (
            world_revision INTEGER PRIMARY KEY,
            committed_at TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            session_id TEXT,
            reason TEXT NOT NULL
        );
        INSERT INTO world_commits VALUES (3, '2026-09-14T00:00:00+00:00', 'op_legacy_1', NULL, 'v2.0 era commit');
        """
    )
    conn.commit()
    conn.close()

    store = SQLiteWorldStore(db)
    assert store.commit_source_class(3) == "ai_cognition"  # 显式回填，不是 DEFAULT 蒙混
    with sqlite3.connect(db) as audit_conn:
        raw = audit_conn.execute(
            "SELECT value FROM world_meta WHERE key='schema_migration_m0_023'"
        ).fetchone()
    assert raw is not None
    audit = json.loads(raw[0])
    assert audit["backfilled_rows"] == 1
    assert audit["policy"] == "explicit update; no silent DEFAULT"
    # 迁移后新语义立即可用
    store.commit([observation(new_object_id(ObjectType.OBSERVATION), "新传感数据")], op(store, "observation.write", "k9"))
    assert store.commit_source_class(4) == "sensor"
    assert store.triggerable_commits_after(3)[0]["source_class"] == "sensor"


# ---------------------------------------------------------------- search side


@pytest.fixture()
def world(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    ent_mom = Entity(object_id=new_object_id(ObjectType.ENTITY), subject_id="user_1",
                     learned_at=NOW, recorded_at=NOW, created_by="fixture",
                     entity_kind="person", canonical_name="妈妈", aliases=["母亲", "老妈"])
    claim = Claim(object_id=new_object_id(ObjectType.CLAIM), subject_id="user_1",
                  learned_at=NOW, recorded_at=NOW, created_by="fixture",
                  claimant_id="user_1", claim_type=ClaimType.DESIRE,
                  content="妈妈想要一个保温杯当生日礼物", asserted_at=NOW,
                  knowledge_state=KnowledgeState.REPORTED, confidence=0.9)
    event = EventAnchor(object_id=new_object_id(ObjectType.EVENT), subject_id="user_1",
                        learned_at=NOW, recorded_at=NOW, created_by="fixture",
                        title="筹备妈妈生日", interpretation="确认礼物预算",
                        event_time=TemporalExtent.point(NOW + timedelta(days=30)),
                        participant_refs=[ObjectRef(object_id=ent_mom.object_id, revision=1)],
                        confidence=0.85)
    noise = observation(new_object_id(ObjectType.OBSERVATION), "下午在商圈闲逛，周围全是叫卖声")
    store.commit([ent_mom, claim, event, noise], op(store, "world.commit", "seed"))
    return store


def index_for(store) -> WorldSearchIndex:
    return WorldSearchIndex(store.db_path, store=store)


def test_cjk_bigrams_cover_two_char_words():
    assert "妈妈" in tokens_for("和妈妈聊了生日")
    assert "gift" in tokens_for("a gift for mom")


def test_multi_keyword_cooccurrence_intersection(world):
    idx = index_for(world)
    assert idx.rebuild() == 4
    page = idx.co_search(["妈妈", "生日", "礼物"])
    assert page.status == "ok"
    types = {h.object_type for h in page.hits}
    assert {"claim", "event"} <= types  # 噪音观测被交集正确排除
    assert all("妈妈" in h.excerpt or h.object_type in {"claim", "event"} for h in page.hits)


def test_alias_resolution_honours_identity_disambiguation(world):
    idx = index_for(world)
    idx.rebuild()
    # "母亲"不是事件文本的字面子串：必须经实体编号解析（ref 命中）才召回事件
    page = idx.co_search(["母亲", "生日"])
    hits = {(h.object_id, h.object_type) for h in page.hits}
    event_hit = [t for _, t in hits if t == "event"]
    assert event_hit, "别名解析应经 ref 链接召回事件（第 36/89 条）"
    claim_hit = [t for _, t in hits if t == "claim"]
    assert claim_hit, "claim 文本含'妈妈'；'母亲'解析到同实体后不应丢失共现"


def test_time_range_and_watermark_semantics(world):
    idx = index_for(world)
    idx.rebuild()
    future = (NOW + timedelta(days=29), NOW + timedelta(days=31))
    page = idx.co_search(["妈妈", "生日"], time_range=future)
    assert {h.object_type for h in page.hits} == {"event"}
    # 水位：新提交未追平 → strict 拒绝；自适应追平后可见
    late = observation(new_object_id(ObjectType.OBSERVATION), "妈妈补充说不要杯子想要围巾", at=NOW)
    world.commit([late], op(world, "observation.write", "late1"))
    assert world.current_world_revision() > idx.watermark()
    stale = idx.co_search(["妈妈", "围巾"], strict_freshness=True)
    assert stale.status == "stale_index" and stale.lag >= 1
    fresh = idx.co_search(["妈妈", "围巾"])
    assert fresh.status == "ok" and fresh.hits and fresh.lag == 0


def test_dropped_projection_rebuilds_bit_identical(world):
    idx = index_for(world)
    idx.rebuild()
    before = idx.co_search(["妈妈", "生日", "礼物"])
    idx.drop_projection()
    after = WorldSearchIndex(world.db_path, store=world)
    after.rebuild()
    second = after.co_search(["妈妈", "生日", "礼物"])
    assert [(h.object_id, h.revision) for h in before.hits] == [(h.object_id, h.revision) for h in second.hits]


def test_scale_smoke_reduced_g_m1p(world):
    """G-M1P 降规模 CI 版：2000 对象下共现检索 p95 < 250ms（正式 50 万修订版在 M1 Gate 后跑脚本）。"""

    batch = []
    for i in range(2000):
        batch.append(observation(new_object_id(ObjectType.OBSERVATION),
                                f"第{i}段环境录音，路人提到礼物与生日的闲聊片段{i % 97}", at=NOW + timedelta(minutes=i)))
    world.commit(batch, op(world, "observation.write", "bulk"))
    idx = index_for(world)
    idx.rebuild()
    latencies = []
    for i in range(60):
        t0 = time.perf_counter()
        idx.co_search(["生日", "礼物", f"片段{i % 97}"], limit=20)
        latencies.append(time.perf_counter() - t0)
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 0.250, f"p95={p95 * 1000:.1f}ms 超出降规模闸门"
    assert idx.lag() == 0
