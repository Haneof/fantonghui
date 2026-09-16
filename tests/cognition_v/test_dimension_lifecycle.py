# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-002 维度生命周期验收（工单 #7 §3）：

  * <3 天（连续跨域异常不足 3 天）提炼必拦截
  * 30 天试用期通过必须注册成功（ACTIVE）且能挂载成功
  * 三重硬门与铁律 5 全等：门行为唯一来源 = evolution_guard（不另造）
  * 三只高阶维度名录：DIM_BURNOUT_RISK / DIM_CREDIT_RISK / DIM_PARENT_HEALTH
  * overlay 只读：挂摘不动世界本体一个 bit
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cognition_m5.dimension_engine import (
    HIGH_ORDER_DIMENSIONS,
    AnomalySignal,
    CrossDimensionalAnomalyDetector,
    DimensionLifecycleStateMachine,
    DimensionOverlayOperator,
    DimensionState,
    GateRejectionError,
    HighOrderDimensionDistiller,
)
from aios_core.contracts.enums import ClaimType, KnowledgeState
from aios_core.contracts.models import Claim
from aios_core.contracts.operations import OperationRequest
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

T0 = datetime(2026, 9, 13, 9, 0, 0, tzinfo=timezone.utc)  # 周日计起点


def _claims_for_burnout() -> list[Claim]:
    """连续四天：熬夜（SLEEP）× 心率（BODY）× 咖啡因（STIMULANT）三域合流。"""
    texts = [
        "第{n}天：凌晨两点还在改方案，心率 96bpm 飙高，又灌了一杯美式咖啡",
        "第{n}天：通宵后心悸明显，咖啡加量到三杯",
        "第{n}天：熬夜到三点，心率骤升 101，靠浓茶硬撑",
        "第{n}天：又失眠，咖啡因摄入过量，室性早搏一次",
    ]
    out = []
    for i, tpl in enumerate(texts):
        at = T0 + timedelta(days=i, minutes=30)
        out.append(Claim(
            object_id=f"burn-{i}", claimant_id="director",
            claim_type=ClaimType.FACT,
            content=tpl.format(n=i + 1), asserted_at=at,
            knowledge_state=KnowledgeState.OBSERVED, confidence=0.9,
            **world_kwargs(subject_id="director", learned_at=at, recorded_at=at),
        ))
    return out


def _store(tmp_path, objs) -> SQLiteWorldStore:
    store = SQLiteWorldStore(tmp_path / "world.db")
    store.commit(list(objs), OperationRequest(
        operation_id="m5-seed", operation_name="world.commit",
        expected_world_revision=store.current_world_revision(),
        reason="seed", idempotency_key="m5-seed"))
    return store


def _signal(days: int = 3, domains: tuple[str, ...] = ("A", "B")) -> AnomalySignal:
    first = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return AnomalySignal(
        signal_id=f"s-{days}d",
        domains=domains,
        first_seen=first.date().isoformat(),
        last_seen=(first + timedelta(days=days - 1)).date().isoformat(),
        span_days=days,
        evidence=({"object_id": "e-1", "revision": "1", "domain": "+".join(domains)},),
        occurrence_count=days,
    )


# ---------------------------------------------------------------------------
# 侦测器：连 3 天跨域成信号；单域/短促不成信号
# ---------------------------------------------------------------------------


def test_detector_finds_three_day_cross_domain_signal():
    detector = CrossDimensionalAnomalyDetector()
    payloads = [c.model_dump() for c in _claims_for_burnout()]
    signals = detector.detect(payloads)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.span_days == 4
    assert {"SLEEP_BEHAVIOR", "BODY_VITALS", "STIMULANT_INTAKE"} <= set(sig.domains)
    assert sig.occurrence_count >= 4


def test_detector_ignores_single_domain_or_short_runs():
    detector = CrossDimensionalAnomalyDetector()
    # 连 5 天但只有心率一个域
    mono = [
        {"object_id": f"m-{i}", "occurred_at": (T0 + timedelta(days=i)).isoformat(),
         "content": "心率 90bpm 记录"} for i in range(5)
    ]
    assert detector.detect(mono) == [], "单域异常不构成跨域信号"
    # 跨域但只有 2 天
    two = [
        {"object_id": f"s-{i}-a", "occurred_at": (T0 + timedelta(days=i)).isoformat(),
         "content": "熬夜心率骤升"} for i in range(2)
    ]
    assert detector.detect(two) == [], "不足连续 3 天不得成信号"
    # 断档 1 天重算连续
    broken = [
        {"object_id": f"b-{i}", "occurred_at": (T0 + timedelta(days=d)).isoformat(),
         "content": "熬夜加咖啡因"} for i, d in enumerate((0, 1, 3, 4))
    ]
    assert detector.detect(broken) == []


# ---------------------------------------------------------------------------
# 门一：<3 天必拦截
# ---------------------------------------------------------------------------


def test_shorter_than_three_days_distillation_is_blocked():
    machine = DimensionLifecycleStateMachine()
    with pytest.raises(GateRejectionError, match="3 天|持续"):
        machine.propose_from_signal("DIM_BURNOUT_RISK", _signal(days=2))
    with pytest.raises(GateRejectionError, match="3 天|持续"):
        machine.propose_from_signal("DIM_BURNOUT_RISK", _signal(days=0))


def test_single_domain_signal_is_blocked():
    machine = DimensionLifecycleStateMachine()
    with pytest.raises(GateRejectionError, match="跨域|物理域"):
        machine.propose_from_signal("DIM_X", _signal(days=5, domains=("A",)))


# ---------------------------------------------------------------------------
# 门二/门三：30 天试用 → ACTIVE → 挂载成功
# ---------------------------------------------------------------------------


def _run_full_lifecycle(tmp_path):
    store = _store(tmp_path, _claims_for_burnout())
    machine = DimensionLifecycleStateMachine()
    detector = CrossDimensionalAnomalyDetector()
    signals = detector.detect([c.model_dump() for c in _claims_for_burnout()])
    assert signals, "三域合流四天必须采到信号"
    machine.propose_from_signal("DIM_BURNOUT_RISK", signals[0])
    # 30 天试用：每日 1 次反思配额 + 逐日预测验证（25/30 正确 ⇒ 83.3% ≥ 70%）
    for d in range(30):
        day_key = f"2026-09-{d + 1:02d}"
        machine.submit_trial_day(
            "DIM_BURNOUT_RISK", day_key=day_key,
            predictions_made=1, predictions_correct=1 if d != 7 else 0,
        )
    return store, machine


def test_thirty_day_probation_registers_and_mounts(tmp_path):
    store, machine = _run_full_lifecycle(tmp_path)
    state = machine.finalize("DIM_BURNOUT_RISK")
    assert state == DimensionState.ACTIVE, "30 天合规试用必注册"
    assert machine.state_of("DIM_BURNOUT_RISK") == DimensionState.ACTIVE

    overlay = DimensionOverlayOperator(store)
    overlay.mount("DIM_BURNOUT_RISK", "burn-0", machine=machine,
                  note="过劳熔断证据：首日三域合流")
    overlay.mount("DIM_BURNOUT_RISK", "burn-1", machine=machine)
    assert overlay.dimensions_of("burn-0") == ("DIM_BURNOUT_RISK",)
    notes = overlay.overlays_of("burn-0")
    assert notes[0]["note"].startswith("过劳熔断证据")


def test_reflection_quota_is_exactly_one_per_day(tmp_path):
    machine = DimensionLifecycleStateMachine()
    machine.propose_from_signal("DIM_BURNOUT_RISK", _signal(days=3))
    machine.submit_trial_day("DIM_BURNOUT_RISK", day_key="2026-09-16",
                             predictions_made=1, predictions_correct=1)
    assert machine.quota_left("2026-09-16") == 0
    with pytest.raises(GateRejectionError, match="配额"):
        machine.submit_trial_day("DIM_BURNOUT_RISK", day_key="2026-09-16",
                                 predictions_made=1, predictions_correct=1)


def test_probation_below_accuracy_expires(tmp_path):
    machine = DimensionLifecycleStateMachine()
    machine.propose_from_signal("DIM_BURNOUT_RISK", _signal(days=3))
    for d in range(30):
        machine.submit_trial_day("DIM_BURNOUT_RISK", day_key=f"2026-10-{d + 1:02d}",
                                 predictions_made=1, predictions_correct=1 if d < 15 else 0)
    assert machine.finalize("DIM_BURNOUT_RISK") == DimensionState.EXPIRED
    with pytest.raises(GateRejectionError, match="终态"):
        machine.propose_from_signal("DIM_BURNOUT_RISK", _signal(days=4))


# ---------------------------------------------------------------------------
# 蒸馏器：名录锁死三只，名录外免谈
# ---------------------------------------------------------------------------


def test_high_order_names_are_exactly_three():
    assert set(HIGH_ORDER_DIMENSIONS) == {
        "DIM_BURNOUT_RISK", "DIM_CREDIT_RISK", "DIM_PARENT_HEALTH"}


def test_distiller_maps_burnout_signal():
    signals = CrossDimensionalAnomalyDetector().detect(
        [c.model_dump() for c in _claims_for_burnout()])
    proposals = HighOrderDimensionDistiller().distill(signals)
    dim_ids = {p.dimension_id for p in proposals}
    assert "DIM_BURNOUT_RISK" in dim_ids
    assert "DIM_CREDIT_RISK" not in dim_ids, "过劳信号不得蒸出信用维度"
    assert "DIM_PARENT_HEALTH" not in dim_ids
    burnout = next(p for p in proposals if p.dimension_id == "DIM_BURNOUT_RISK")
    assert burnout.evidence, "提案必须背证据"
    assert "过劳" in burnout.rationale


# ---------------------------------------------------------------------------
# overlay 只读钢印：挂摘不动世界本体
# ---------------------------------------------------------------------------


def test_overlay_is_read_only_against_world_body(tmp_path):
    store = _store(tmp_path, _claims_for_burnout())
    before = store.get_payload("burn-0")
    rev_before = store.current_world_revision()

    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    _, machine = _run_full_lifecycle(trial_dir)
    overlay = DimensionOverlayOperator(store)
    overlay.mount("DIM_BURNOUT_RISK", "burn-0")  # 不带 machine 也允许挂（只读旁车）

    after = store.get_payload("burn-0")
    assert after == before, "挂标签动世界本体 = 一票否决面"
    assert store.current_world_revision() == rev_before, "overlay 走旁车，不推版本"


def test_mount_requires_existing_object(tmp_path):
    store = _store(tmp_path, _claims_for_burnout())
    overlay = DimensionOverlayOperator(store)
    with pytest.raises(GateRejectionError, match="虚空|不存在"):
        overlay.mount("DIM_BURNOUT_RISK", "ghost-404")
