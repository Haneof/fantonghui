"""M1-022 Manifest Data-Plane Builder v0 —— R4/宪法 AC 的机械证。

  * 四步排版：§84.2 段落序 step1→step2→step4（step0/step3 明文缺席进 omissions，绝不伪造）
  * 确定性回放：同世界状态+同输入 ⇒ 同 canonical_hash 同 manifest_id，物化幂等不双份
  * 零 LLM：model_calls_per_build == 0 结构性常数
  * 规模无关：queries_per_build == 3，10 倍数据同查询次数；ready 行检视比 1.0
  * §86.2 硬过滤：state='READY' 之外的代理行（连陈旧 ready_view 行）绝不进看板
  * 物化铁律：manifest_instance UPDATE/DELETE 触发器物理拒绝；manifest_version=0 CHECK
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.enums_v3 import TriggerOp
from aios_core.contracts.models_v3 import TimeReached, TriggerExpression, TriggerExpressionObject
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.services.eligibility_worker import EligibilityWorker, InMemoryEventBus
from aios_core.services.manifest_data_plane import (
    ESTIMATOR_VERSION,
    L0SliceStore,
    ManifestDataPlaneBuilderV0,
    OMIT_STEP0_REASON,
    OMIT_STEP3_REASON,
    SLICE_CAPABILITY_REGISTRY,
    SLICE_NOW_CONTEXT,
    SLICE_RAPPORT,
    SLICE_SELF_STATE,
    WakeInput,
    estimate_tokens,
)
from aios_core.storage.manifest_schema import ensure_manifest_schema
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

NOW = datetime(2026, 9, 16, 9, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path) -> SQLiteWorldStore:
    return SQLiteWorldStore(tmp_path / "world.db")


def _wake(subject: str = "user-1", scene: tuple = (), lane: str = "notify",
          now: datetime = NOW, wake_id: str = "wake-1") -> WakeInput:
    return WakeInput(
        subject_id=subject,
        wake_object_id=wake_id,
        wake_revision=1,
        wake_reason_kind="user_interaction",
        lane=lane,
        scene_refs=scene,
        now_utc=now,
    )


def _seed_slices(store: L0SliceStore, subject: str = "user-1") -> None:
    store.upsert(subject, SLICE_SELF_STATE, {"stance": "steady", "last_state": "reflecting"},
                 source_object_id="self-obj", source_revision=7,
                 freshness_at=NOW - timedelta(minutes=5), slice_rev=11)
    store.upsert(subject, SLICE_RAPPORT, {"dim": "DIM_AI_RAPPORT", "value": 0.72},
                 source_object_id="rapport-obj", source_revision=3,
                 freshness_at=NOW - timedelta(hours=2), slice_rev=11)
    store.upsert(subject, SLICE_NOW_CONTEXT, {"place": "home", "main_event": "morning"},
                 source_object_id="now-obj", source_revision=9,
                 freshness_at=NOW - timedelta(minutes=1), slice_rev=11)
    store.upsert(subject, SLICE_CAPABILITY_REGISTRY,
                 {"capabilities": [{"object_id": "cap:calendar", "revision": 2},
                                   {"object_id": "cap:alarm", "revision": 1}]},
                 source_object_id="cap-obj", source_revision=2,
                 freshness_at=NOW - timedelta(days=1), slice_rev=11)


def _seed_ready(store: SQLiteWorldStore, subject: str, n: int, *, due: bool = True, tag: str = "a") -> list[str]:
    """借 M1-021 通道物化真 READY 集（集成证据：数据面吃消费面，不回填）。"""
    worker = EligibilityWorker(store)
    task_ids = []
    for i in range(n):
        at = NOW - timedelta(seconds=60) if due else NOW + timedelta(days=1)
        expr = TriggerExpression(op=TriggerOp.ATOM, leaf=TimeReached(at=at))
        obj = TriggerExpressionObject(
            object_id=f"expr-{subject}-{tag}-{i}", ast=expr,
            **world_kwargs(subject_id=subject, learned_at=NOW, recorded_at=NOW),
        )
        rev = store.current_world_revision()
        store.commit([obj], OperationRequest(
            operation_id=f"seed-{subject}-{tag}-{i}", operation_name="world.commit",
            expected_world_revision=rev, reason="seed", idempotency_key=f"k-{subject}-{tag}-{i}"))
        task_id = f"task-{subject}-{tag}-{i}"
        worker.register_task_proxy(task_id, obj, expr, subject)
        task_ids.append(task_id)
    worker.tick(NOW, InMemoryEventBus())
    return task_ids


def _read_row(tmp_path, manifest_id: str) -> sqlite3.Row | None:
    conn = sqlite3.connect(tmp_path / "world.db")
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM manifest_instance WHERE manifest_id=?", (manifest_id,)
        ).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 四步排版与 L0 装配
# ---------------------------------------------------------------------------


def test_four_step_layout_l0_only_assembly(tmp_path):
    store = _store(tmp_path)
    _seed_slices(L0SliceStore(store))
    _seed_ready(store, "user-1", 2)
    builder = ManifestDataPlaneBuilderV0(store)
    scene = (ObjectRef(object_id="obs-scene-1", revision=2),
             ObjectRef(object_id="obs-scene-2", revision=5))
    report = builder.build(_wake(scene=scene))

    body = builder.read_manifest_body(report.manifest_id)
    assert body is not None
    sections = body["sections"]
    # §84.2 排版顺序是契约字段序：step1→step2→step3→step4
    assert list(sections.keys()) == ["step1_self", "step2_rapport", "step3_stance", "step4_world"]
    assert len(sections["step1_self"]) == 1
    assert len(sections["step2_rapport"]) == 1
    assert sections["step3_stance"] == []            # v0 明文不装配
    assert len(sections["step4_world"]) == 3         # now_context + 2 现场切片
    assert len(body["ready_tasks"]) == 2
    assert len(body["capabilities"]) == 2
    # step0/step3 缺席必须显式可见（防静默失忆）
    reasons = {o["reason"] for o in body["omissions"]}
    assert OMIT_STEP0_REASON in reasons and OMIT_STEP3_REASON in reasons
    assert report.ready_exposed == 2 and report.waiting_exposed == 0
    assert report.reused_existing is False


def test_slots_are_pinned_pointers_with_freshness(tmp_path):
    store = _store(tmp_path)
    _seed_slices(L0SliceStore(store))
    task_ids = _seed_ready(store, "user-1", 1)
    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake(scene=(ObjectRef(object_id="obs-x", revision=4),)))
    body = builder.read_manifest_body(report.manifest_id)

    all_slots = [s for group in body["sections"].values() for s in group]
    all_slots += body["ready_tasks"] + body["capabilities"]
    assert all_slots, "至少需要若干槽位能证指针铁律"
    for slot in all_slots:
        assert slot["ref"]["object_id"] and slot["ref"]["revision"] >= 1  # 钉版
        assert slot["source"] == "l0_slice"
        assert slot["freshness_at"] and slot["reason"].startswith("l0:")
        assert slot["token_cost"] >= 0
    # 新鲜度来自切片/就绪面，不是装配时刻（比瞬间值，不比字符串形态）
    s1 = body["sections"]["step1_self"][0]
    assert datetime.fromisoformat(s1["freshness_at"].replace("Z", "+00:00")) == NOW - timedelta(minutes=5)
    rt = body["ready_tasks"][0]
    assert rt["ref"]["object_id"] == task_ids[0]


# ---------------------------------------------------------------------------
# 确定性回放与幂等物化
# ---------------------------------------------------------------------------


def test_deterministic_replay_content_addressed_idempotent(tmp_path):
    store = _store(tmp_path)
    _seed_slices(L0SliceStore(store))
    _seed_ready(store, "user-1", 3)
    builder = ManifestDataPlaneBuilderV0(store)
    wake = _wake(scene=(ObjectRef(object_id="obs-y", revision=1),))

    r1 = builder.build(wake)
    r2 = builder.build(wake)  # 世界未动、输入相同 ⇒ 重放
    assert r1.canonical_hash == r2.canonical_hash
    assert r1.manifest_id == r2.manifest_id
    assert r2.reused_existing is True

    conn = sqlite3.connect(tmp_path / "world.db")
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM manifest_instance WHERE manifest_id=?",
            (r1.manifest_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 1, "内容寻址：重放绝不产生第二行物化"


def test_distinct_inputs_distinct_manifest_ids(tmp_path):
    store = _store(tmp_path)
    _seed_slices(L0SliceStore(store))
    builder = ManifestDataPlaneBuilderV0(store)
    r1 = builder.build(_wake(now=NOW))
    r2 = builder.build(_wake(now=NOW + timedelta(minutes=1)))
    assert r1.manifest_id != r2.manifest_id
    assert r1.canonical_hash != r2.canonical_hash


# ---------------------------------------------------------------------------
# 物化铁律（append-only / 版本锁 / 钉版拒绝）
# ---------------------------------------------------------------------------


def test_manifest_instance_append_only_triggers_fire(tmp_path):
    store = _store(tmp_path)
    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake())

    conn = sqlite3.connect(tmp_path / "world.db", isolation_level=None)
    ensure_manifest_schema(conn)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            "UPDATE manifest_instance SET token_total=999 WHERE manifest_id=?",
            (report.manifest_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            "DELETE FROM manifest_instance WHERE manifest_id=?", (report.manifest_id,)
        )
    conn.close()


def test_manifest_version_locked_to_v0(tmp_path):
    store = _store(tmp_path)
    builder = ManifestDataPlaneBuilderV0(store)
    builder.build(_wake())
    conn = sqlite3.connect(tmp_path / "world.db", isolation_level=None)
    ensure_manifest_schema(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO manifest_instance VALUES ('mani-x',1,'u','w',1,'k','notify',"
            "'{}','[]',0,0,1.0,3,1,'tok-est-v0','h','2026-01-01T00:00:00+00:00')"
        )
    conn.close()


def test_unpinned_scene_ref_rejected(tmp_path):
    store = _store(tmp_path)
    builder = ManifestDataPlaneBuilderV0(store)
    with pytest.raises(ValueError, match="未钉版"):
        builder.build(_wake(scene=(ObjectRef(object_id="obs-unpinned"),)))


def test_invalid_lane_rejected(tmp_path):
    with pytest.raises(ValueError, match="lane"):
        _wake(lane="turbo")


# ---------------------------------------------------------------------------
# 零 LLM 与规模无关查询形态
# ---------------------------------------------------------------------------


def test_zero_llm_is_structural_constant(tmp_path):
    builder = ManifestDataPlaneBuilderV0(_store(tmp_path))
    report = builder.build(_wake())
    assert report.model_calls_in_build == 0


def test_query_count_invariant_under_data_scale(tmp_path):
    store = _store(tmp_path)
    slices = L0SliceStore(store)
    _seed_slices(slices)
    builder = ManifestDataPlaneBuilderV0(store)
    r1 = builder.build(_wake())

    # ━━━ 10 倍噪声：30 个其他主体全量切片 + 其他主体的真 READY ━━━
    for i in range(30):
        other = f"other-{i}"
        slices.upsert(other, SLICE_SELF_STATE, {"s": i},
                      source_object_id=f"self-{i}", source_revision=1,
                      freshness_at=NOW, slice_rev=1)
        slices.upsert(other, SLICE_RAPPORT, {"v": i},
                      source_object_id=f"rap-{i}", source_revision=1,
                      freshness_at=NOW, slice_rev=1)
        slices.upsert(other, SLICE_NOW_CONTEXT, {"n": i},
                      source_object_id=f"now-{i}", source_revision=1,
                      freshness_at=NOW, slice_rev=1)
        slices.upsert(other, SLICE_CAPABILITY_REGISTRY, {"capabilities": []},
                      source_object_id=f"cap-{i}", source_revision=1,
                      freshness_at=NOW, slice_rev=1)
    _seed_ready(store, "other-0", 8)

    r2 = builder.build(_wake(now=NOW + timedelta(seconds=1)))
    assert r1.queries_executed == 3 and r2.queries_executed == 3
    # 数据面只看见 user-1 自己的切片（隔离性由主键索引保证）
    assert r2.slices_hit == 4
    assert r2.ready_exposed == 0


def test_rows_examined_per_ready_ratio_one(tmp_path):
    store = _store(tmp_path)
    _seed_ready(store, "user-1", 30)
    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake())
    assert report.ready_exposed == 30
    assert report.rows_examined_ready == 30
    ratio = report.rows_examined_ready / max(report.ready_exposed, 1)
    assert 1.0 <= ratio <= 1.05, "索引 JOIN 直查：检视行数 == 就绪行数"


def test_stale_ready_view_row_cannot_leak_waiting_task(tmp_path):
    """投毒：ready_view 有行但代理 state!='READY' ⇒ 看板绝不可见（G2 硬过滤）。"""
    store = _store(tmp_path)
    _seed_ready(store, "user-1", 1)
    conn = sqlite3.connect(tmp_path / "world.db", isolation_level=None)
    conn.execute(
        "INSERT INTO ready_view VALUES ('poison-task',?,?,0)",
        (NOW.isoformat(), '{"verdict":"stale"}'),
    )
    conn.execute(
        "INSERT INTO task_proxy VALUES ('poison-task','expr-x','user-1','PENDING',NULL,?,NULL)",
        (NOW.isoformat(),),
    )
    conn.close()

    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake())
    body = builder.read_manifest_body(report.manifest_id)
    exposed = {s["ref"]["object_id"] for s in body["ready_tasks"]}
    assert "poison-task" not in exposed
    assert report.ready_exposed == 1 and report.waiting_exposed == 0


def test_pending_proxies_without_ready_rows_never_exposed(tmp_path):
    store = _store(tmp_path)
    _seed_ready(store, "user-1", 5, due=True, tag="a")
    _seed_ready(store, "user-1", 5, due=False, tag="b")  # 5 个 PENDING 休眠者
    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake())
    body = builder.read_manifest_body(report.manifest_id)
    assert report.ready_exposed == 5
    assert len(body["ready_tasks"]) == 5


# ---------------------------------------------------------------------------
# 缺席显式化 / token 会计 / 延迟闸
# ---------------------------------------------------------------------------


def test_missing_slices_become_explicit_omissions_not_fabrication(tmp_path):
    store = _store(tmp_path)
    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake())
    body = builder.read_manifest_body(report.manifest_id)

    assert body["sections"]["step1_self"] == []
    assert body["sections"]["step2_rapport"] == []
    assert body["sections"]["step4_world"] == []
    reasons = {o["reason"] for o in body["omissions"]}
    for kind in ("self_state", "rapport", "now_context", "capability_registry"):
        assert f"l0_slice_absent:{kind}" in reasons
    assert OMIT_STEP0_REASON in reasons and OMIT_STEP3_REASON in reasons
    assert len(body["omissions"]) == 6
    assert report.slices_hit == 0 and report.token_total == 0


def test_token_estimator_deterministic_formula():
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好世界") == 4
    assert estimate_tokens("abcdefgh") == 2          # 8 ASCII → ceil(8/4)
    assert estimate_tokens("你好abcd") == 3         # 2 CJK + ceil(4/4)
    assert estimate_tokens("hello world") == 3      # 11 → ceil(11/4)


def test_token_total_equals_sum_of_slot_costs_and_versions_stamped(tmp_path):
    store = _store(tmp_path)
    _seed_slices(L0SliceStore(store))
    builder = ManifestDataPlaneBuilderV0(store)
    report = builder.build(_wake(scene=(ObjectRef(object_id="obs-z", revision=1),)))
    body = builder.read_manifest_body(report.manifest_id)

    all_slots = [s for group in body["sections"].values() for s in group]
    all_slots += body["ready_tasks"] + body["capabilities"]
    assert report.token_total == sum(s["token_cost"] for s in all_slots)
    assert body["manifest_version"] == 0
    assert body["estimator_version"] == ESTIMATOR_VERSION
    assert body["world_rev"] == store.current_world_revision()
    row = _read_row(tmp_path, report.manifest_id)
    assert row["build_ms"] > 0 and row["queries_executed"] == 3


def test_l0_p95_latency_latch_and_query_shape(tmp_path):
    """L0 p95 闸（R4/I2：≤50ms 目标；CI 留 2 倍余量，真闸是同批 queries==3）。"""
    store = _store(tmp_path)
    _seed_slices(L0SliceStore(store))
    _seed_ready(store, "user-1", 20)
    builder = ManifestDataPlaneBuilderV0(store)

    builds: list[float] = []
    for i in range(40):
        r = builder.build(_wake(now=NOW + timedelta(seconds=i), wake_id=f"wake-lat-{i}"))
        builds.append(r.build_ms)
        assert r.queries_executed == 3
        assert r.ready_exposed == 20
    builds.sort()
    p95 = builds[int(0.95 * len(builds)) - 1]
    assert p95 <= 100.0, f"L0 装配 p95={p95:.1f}ms 越过闸（目标 50ms，CI 余量 100ms）"
