"""M1-021 Eligibility & Ready View —— R4 AC 节选择的机械证。

  * 规模严证：200 个订阅任务、5 个到期，tick 的 `tasks_examined <= 1.05 × ready`（索引直查，非扫描）
  * 零 LLM：report.model_calls_in_eval == 0，结构性保证而非告警
  * V36 边界：事件迟到窗口外不触发、低质观测→UNKNOWN、A AND B 语义窗交由语义车道不猜 TRUE、循环依赖静态拒、UNKNOWN 重排复查
  * zombie：max_wait 过期即 DUE_FOR_REVIEW
  * 物化：机械真+无语义 → ready_view；含语义 → 复核 Wake 而非物化
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.models_v3 import (
    DependencyReady,
    EventMatched,
    MechanicalPredicate,
    SemanticPredicate,
    TimeReached,
    TriggerExpression,
    TriggerExpressionObject,
)
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.enums_v3 import TriState, TriggerOp
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.services.eligibility_worker import (
    EligibilityWorker,
    InMemoryEventBus,
    MechanicalEvaluator,
    materialize_subscription_keys,
)
from aios_core.storage.eligibility_schema import ensure_eligibility_schema
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

NOW = datetime(2026, 9, 16, 8, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path) -> SQLiteWorldStore:
    return SQLiteWorldStore(tmp_path / "world.db")


def _commit(store, expr_obj: TriggerExpressionObject, key: str) -> None:
    rev = store.current_world_revision()
    store.commit([expr_obj], OperationRequest(
        operation_id=f"seed-{key}", operation_name="world.commit",
        expected_world_revision=rev, reason="seed", idempotency_key=key))


def _expr_obj(oid: str, node: TriggerExpression) -> TriggerExpressionObject:
    return TriggerExpressionObject(
        object_id=oid, ast=node,
        **world_kwargs(learned_at=NOW, recorded_at=NOW),
    )


def _atom_time(at: datetime) -> TriggerExpression:
    return TriggerExpression(op=TriggerOp.ATOM, leaf=TimeReached(at=at))


def _atom_pred(kind: str = "no_update", params: dict | None = None) -> TriggerExpression:
    return TriggerExpression(op=TriggerOp.ATOM, leaf=MechanicalPredicate(kind=kind, params=params or {}))


# ---------------------------------------------------------------------------
# 规模严证
# ---------------------------------------------------------------------------


def test_scale_examined_ratio_stays_near_one(tmp_path):
    """200 订阅、5 到期 → tasks_examined 必须 ≈ ready 数，而非 200。"""
    store = _store(tmp_path)
    worker = EligibilityWorker(store)
    NOW_D = NOW

    # 195 个远期 + 5 个到期
    for i in range(195):
        expr = _atom_time(NOW_D + timedelta(days=1))
        obj = _expr_obj(f"expr-far-{i}", expr)
        _commit(store, obj, f"far-{i}")
        worker.register_task_proxy(f"task-far-{i}", obj, expr, "user-1")
    for i in range(5):
        expr = _atom_time(NOW_D - timedelta(seconds=1))
        obj = _expr_obj(f"expr-due-{i}", expr)
        _commit(store, obj, f"due-{i}")
        worker.register_task_proxy(f"task-due-{i}", obj, expr, "user-1")

    bus = InMemoryEventBus()
    report = worker.tick(NOW_D, bus)
    assert report.tasks_examined == 5
    ready = 5
    assert report.tasks_examined <= ready * 1.05 + 0.5  # 整数化容差
    assert report.model_calls_in_eval == 0


def test_zero_llm_is_structural_constant(tmp_path):
    store = _store(tmp_path)
    worker = EligibilityWorker(store)
    bus = InMemoryEventBus()
    report = worker.tick(NOW, bus)
    assert report.model_calls_in_eval == 0


# ---------------------------------------------------------------------------
# V36 边界
# ---------------------------------------------------------------------------


def test_event_late_beyond_window_is_ignored(tmp_path):
    """窗口期外命中的事件不算（不是"晚"，是"不算"）。"""
    store = _store(tmp_path)
    ev = MechanicalEvaluator(now_utc=NOW, world_payloads={}, event_bus=InMemoryEventBus())
    bus = InMemoryEventBus()
    bus.push({
        "object_type": "observation",
        "payload": {"source_kind": "hr"},
        "occurred_at": (NOW - timedelta(seconds=7000)).isoformat(),  # 超 1h 窗
        "recorded_at": NOW.isoformat(),
    })
    ev2 = MechanicalEvaluator(now_utc=NOW, world_payloads={}, event_bus=bus)
    verdict = ev2.event_matched(EventMatched(object_type="observation", match={"source_kind": "hr"}))
    assert verdict.value is TriState.FALSE  # 而非 TRUE（迟到不触发）


def test_low_quality_observation_yields_unknown_not_true(tmp_path):
    ev = MechanicalEvaluator(now_utc=NOW, world_payloads={}, event_bus=InMemoryEventBus())
    verdict = ev.mechanical(MechanicalPredicate(kind="no_update", params={"data_quality": "low"}), "user-1")
    assert verdict.value is TriState.UNKNOWN


def test_dependency_cycle_statically_rejected(tmp_path):
    worker = EligibilityWorker(_store(tmp_path))
    # 自环
    expr_def = TriggerExpression(
        op=TriggerOp.ATOM,
        leaf=DependencyReady(refs=[ObjectRef(object_id="expr-self")]),
    )
    with pytest.raises(ValueError, match="自环|循环"):
        worker.register_task_proxy(
            "task-x",
            _expr_obj("expr-self", expr_def),
            expr_def, "user-1",
        )


def test_unknown_verdict_reschedules_revisit(tmp_path):
    """UNKNOWN 不是终点：给 next_eval_at = min(now+15min, review_interval)。"""
    store = _store(tmp_path)
    worker = EligibilityWorker(store)
    expr = TriggerExpression(
        op=TriggerOp.ATOM,
        leaf=EventMatched(object_type="observation", match={"source_kind": "hr"}),
    )
    obj = _expr_obj("expr-unk", expr)
    _commit(store, obj, "unk")
    bus = InMemoryEventBus()  # 空 bus → UNKNOWN
    worker.register_task_proxy("task-unk", obj, expr, "user-1")
    report = worker.tick(NOW, bus)
    assert "expr-unk" in report.unknowns_next_eval
    expect = NOW + timedelta(seconds=900)
    assert report.unknowns_next_eval["expr-unk"] == expect.isoformat()


def test_missing_dependency_is_unknown_not_false(tmp_path):
    ev = MechanicalEvaluator(now_utc=NOW, world_payloads={}, event_bus=InMemoryEventBus())
    verdict = ev.dep_ready(DependencyReady(refs=[ObjectRef(object_id="ghost-task")]), "user-1")
    assert verdict.value is TriState.UNKNOWN


# ---------------------------------------------------------------------------
# 物化与语义分轨
# ---------------------------------------------------------------------------


def test_ready_view_materialized_on_mech_true_no_semantic(tmp_path):
    store = _store(tmp_path)
    worker = EligibilityWorker(store)
    expr = _atom_time(NOW - timedelta(seconds=60))
    obj = _expr_obj("expr-r1", expr)
    _commit(store, obj, "r1")
    worker.register_task_proxy("task-r1", obj, expr, "user-1")
    worker.tick(NOW, InMemoryEventBus())
    with worker._connect() as conn:
        row = conn.execute("SELECT * FROM ready_view WHERE task_id='task-r1'").fetchone()
    assert row is not None
    assert row["reason_json"].find("expr-r1") >= 0


def test_semantic_subtree_routes_to_review_not_ready(tmp_path):
    store = _store(tmp_path)
    worker = EligibilityWorker(store)
    expr = TriggerExpression(
        op=TriggerOp.ALL_OF,
        children=[
            _atom_time(NOW - timedelta(seconds=60)),
            TriggerExpression(op=TriggerOp.ATOM, leaf=SemanticPredicate(kind="context_fit", prompt_signature="sig-01")),
        ],
    )
    obj = _expr_obj("expr-sem", expr)
    _commit(store, obj, "sem")
    worker.register_task_proxy("task-sem", obj, expr, "user-1")
    report = worker.tick(NOW, InMemoryEventBus())
    assert report.review_wakes_issued >= 1
    with worker._connect() as conn:
        row = conn.execute("SELECT * FROM ready_view WHERE task_id='task-sem'").fetchone()
    assert row is None, "含语义子树的表达式不得在机械通道物化 ready_view"


# ---------------------------------------------------------------------------
# 僵尸回收
# ---------------------------------------------------------------------------


def test_zombie_after_max_wait_goes_review_state(tmp_path):
    store = _store(tmp_path)
    worker = EligibilityWorker(store)
    expr = _atom_time(NOW - timedelta(seconds=60))
    obj = _expr_obj("expr-z", expr)
    _commit(store, obj, "z")
    worker.register_task_proxy("task-z", obj, expr, "user-1", max_wait_seconds=3600)
    # task_proxy created_at 是注册时写入的——spray 成长型快照
    with worker._connect() as conn:
        conn.execute(
            "UPDATE task_proxy SET created_at=? WHERE task_id='task-z'",
            ((NOW - timedelta(seconds=3700)).isoformat(),),
        )
        conn.commit()
    # tick 前 zombie_sweep
    zombies = worker.zombie_sweep(NOW)
    assert "task-z" in zombies
    with worker._connect() as conn:
        row = conn.execute("SELECT state FROM task_proxy WHERE task_id='task-z'").fetchone()
    assert row["state"] == "DUE_FOR_REVIEW"


# ---------------------------------------------------------------------------
# 订阅键物化
# ---------------------------------------------------------------------------


def test_subscription_keys_reflect_ast_leaf_species():
    expr = TriggerExpression(
        op=TriggerOp.ALL_OF,
        children=[
            _atom_time(NOW),
            TriggerExpression(op=TriggerOp.ATOM, leaf=EventMatched(object_type="observation", match={})),
            TriggerExpression(op=TriggerOp.ATOM, leaf=MechanicalPredicate(kind="no_update", params={})),
        ],
    )
    keys = materialize_subscription_keys(expr, "expr-x", "user-1")
    kinds = {k[1] for k in keys}
    assert "time_due" in kinds and "event" in kinds and "obs_pred" in kinds


def test_compound_not_semantic_still_registered_as_review_due():
    expr = TriggerExpression(
        op=TriggerOp.ATOM, leaf=SemanticPredicate(kind="sentiment_match", prompt_signature="s1"),
    )
    keys = materialize_subscription_keys(expr, "expr-y", "user-1")
    assert any(k[1] == "sem_review_due" for k in keys)
