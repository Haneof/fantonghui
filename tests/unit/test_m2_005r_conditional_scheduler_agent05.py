"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制 —— 四大硬门禁验收。
独立命名并存线（agent-05）：本文件为 agent-05 共存线交付版本的独立验收测试，与规范实现的验收测试并存，零覆盖、互不依赖。

实战业务情境：创业企业法务总监 200 项跨周期复杂条件任务。
- 门禁 1：DORMANT 任务看板 Token 严格为 0（物理隐形）；
- 门禁 2：Level-1 机械快轨 1ms 内 0 Token / 0 LLM 判定，直接 DORMANT→READY；
- 门禁 3：Level-2 机会式捎带（仅用户主动唤醒 + 相关场景），无自主唤醒入口；
- 门禁 4：状态机非法跃迁 100% 拦截（DORMANT→READY→RUNNING→COMPLETED 单向链）。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.scheduler.conditional_engine_agent05 import (
    BiometricThresholdCondition,
    ConditionalTask,
    ConditionalTaskEngine,
    ConditionalTaskState,
    CompositeAndCondition,
    ContextFlagCondition,
    GeofenceCondition,
    IllegalStateTransitionError,
    PhysicalContext,
    SemanticSceneCondition,
    TimeAbsoluteCondition,
    TokenMeter,
    build_legal_director_schedule,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
OFFICE = (31.2304, 121.4737)


def make_task(task_id: str, condition, description: str = "法务任务") -> ConditionalTask:
    return ConditionalTask(
        task_id=task_id,
        description=description,
        condition=condition,
        created_at=T0,
    )


# ----------------------------------------------------------------------
# 门禁 1：DORMANT 任务 Token 严格为 0（物理隐形）
# ----------------------------------------------------------------------


class TestDormantPhysicalInvisibility:
    def test_200_tasks_195_dormant_render_strictly_zero_tokens(self):
        engine = ConditionalTaskEngine()
        tasks = build_legal_director_schedule(start=T0, count=200)
        engine.register_all(tasks)
        assert len(engine.by_state(ConditionalTaskState.DORMANT)) == 200

        # DORMANT 全量片段必须为空串 → Token 严格为 0
        assert engine.cockpit_fragment() == ""
        assert engine.dormant_token_footprint() == 0

        # 制造 5 个 READY：看板片段只含这 5 个，195 个休眠任务物理隐形
        for t in tasks[:5]:
            t.state = ConditionalTaskState.READY
        fragment = engine.cockpit_fragment()
        visible_ids = {t.task_id for t in tasks[:5]}
        dormant_ids = {t.task_id for t in tasks[5:]}
        for vid in visible_ids:
            assert vid in fragment
        for did in dormant_ids:
            assert did not in fragment  # 未成熟任务严禁灌入 LLM Prompt
        # Token 差量 = 5 个可见任务的片段（休眠贡献严格为 0）
        assert engine.dormant_token_footprint() == 0
        assert estimate_tokens(fragment) == estimate_tokens(engine.cockpit_fragment(tasks[:5]))

    def test_empty_registry_fragment_is_empty(self):
        engine = ConditionalTaskEngine()
        assert engine.cockpit_fragment() == ""
        assert engine.dormant_token_footprint() == 0


# ----------------------------------------------------------------------
# 门禁 2：Level-1 机械快轨（0 Token / 0 LLM / 1ms 内）
# ----------------------------------------------------------------------


class TestLevel1MechanicalFastTrack:
    def test_200_task_sweep_within_1ms_with_zero_llm(self):
        engine = ConditionalTaskEngine()
        engine.register_all(build_legal_director_schedule(start=T0, count=200))
        ctx = PhysicalContext(
            now=T0 + timedelta(days=1),
            location=OFFICE,
            biometrics={"heart_rate_bpm": 72.0, "hrv_ms": 55.0},
            flags={"deep_focus": False, "calendar_free": True},
        )
        started = time.perf_counter()
        matured = engine.evaluate_physical(ctx)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert isinstance(matured, tuple)
        assert elapsed_ms < 1.0, f"Level-1 机械快轨 200 任务扫描 {elapsed_ms:.3f}ms 超过 1ms 红线"
        # 大模型调用次数严格为 0
        assert engine.meter.llm_calls == 0
        assert engine.meter.tokens == 0
        # 时间到期任务确实成熟
        assert any(t.task_id.startswith("task:legal:") for t in matured)

    def test_time_absolute_deadline_matures(self):
        engine = ConditionalTaskEngine()
        task = make_task("t:time", TimeAbsoluteCondition(T0 + timedelta(hours=1)))
        engine.register(task)
        assert engine.evaluate_physical(PhysicalContext(now=T0)) == ()
        matured = engine.evaluate_physical(PhysicalContext(now=T0 + timedelta(hours=1)))
        assert [t.task_id for t in matured] == ["t:time"]
        assert engine.get("t:time").state is ConditionalTaskState.READY

    def test_geofence_radius_boundary(self):
        engine = ConditionalTaskEngine()
        task = make_task("t:geo", GeofenceCondition("office_shanghai", *OFFICE, radius_m=300.0))
        engine.register(task)
        # 办公室内（≈0m）
        assert [t.task_id for t in engine.evaluate_physical(PhysicalContext(now=T0, location=OFFICE))] == ["t:geo"]
        # 1km 外：不成熟
        engine2 = ConditionalTaskEngine()
        engine2.register(make_task("t:geo2", GeofenceCondition("office_shanghai", *OFFICE, radius_m=300.0)))
        assert engine2.evaluate_physical(PhysicalContext(now=T0, location=(31.2404, 121.4737))) == ()
        # 无定位：fail-closed 不成熟
        engine3 = ConditionalTaskEngine()
        engine3.register(make_task("t:geo3", GeofenceCondition("office_shanghai", *OFFICE, radius_m=300.0)))
        assert engine3.evaluate_physical(PhysicalContext(now=T0, location=None)) == ()

    def test_biometric_3_consecutive_evenings_matures_on_day3_only(self):
        engine = ConditionalTaskEngine()
        engine.register(
            make_task(
                "t:cardiology",
                BiometricThresholdCondition.above("evening_heart_rate_bpm", 95.0, 3),
                "连续 3 天晚间心率 > 95bpm 启动心内科预约建档",
            )
        )
        # 第 1 晚：HR 98 → 不成熟
        assert engine.evaluate_physical(
            PhysicalContext(now=T0, biometrics={"evening_heart_rate_bpm": 98.0})
        ) == ()
        # 第 2 晚：HR 97 → 仍不成熟
        assert engine.evaluate_physical(
            PhysicalContext(now=T0 + timedelta(days=1), biometrics={"evening_heart_rate_bpm": 97.0})
        ) == ()
        # 第 3 晚：HR 96 → 恰好成熟
        matured = engine.evaluate_physical(
            PhysicalContext(now=T0 + timedelta(days=2), biometrics={"evening_heart_rate_bpm": 96.0})
        )
        assert [t.task_id for t in matured] == ["t:cardiology"]
        assert engine.get("t:cardiology").state is ConditionalTaskState.READY

    def test_biometric_streak_broken_by_low_day(self):
        engine = ConditionalTaskEngine()
        engine.register(make_task("t:hrv", BiometricThresholdCondition.below("hrv_ms", 40.0, 3)))
        engine.evaluate_physical(PhysicalContext(now=T0, biometrics={"hrv_ms": 30.0}))
        engine.evaluate_physical(PhysicalContext(now=T0 + timedelta(days=1), biometrics={"hrv_ms": 35.0}))
        engine.evaluate_physical(PhysicalContext(now=T0 + timedelta(days=2), biometrics={"hrv_ms": 52.0}))  # 中断
        engine.evaluate_physical(PhysicalContext(now=T0 + timedelta(days=3), biometrics={"hrv_ms": 28.0}))
        engine.evaluate_physical(PhysicalContext(now=T0 + timedelta(days=4), biometrics={"hrv_ms": 29.0}))
        assert engine.get("t:hrv").state is ConditionalTaskState.DORMANT  # 连续性被打破，不成熟

    def test_composite_and_office_plus_not_deep_focus(self):
        engine = ConditionalTaskEngine()
        engine.register(
            make_task(
                "t:buyback",
                CompositeAndCondition(
                    (
                        GeofenceCondition("office_shanghai", *OFFICE, radius_m=300.0),
                        ContextFlagCondition("deep_focus", False),
                    )
                ),
                "回到上海办公室且非深度专注时提示签署对赌回购协议",
            )
        )
        # 在办公室但深度专注：不成熟
        assert engine.evaluate_physical(
            PhysicalContext(now=T0, location=OFFICE, flags={"deep_focus": True})
        ) == ()
        # 非深度专注但不在办公室：不成熟
        engine2 = ConditionalTaskEngine()
        engine2.register(
            make_task(
                "t:buyback2",
                CompositeAndCondition(
                    (
                        GeofenceCondition("office_shanghai", *OFFICE, radius_m=300.0),
                        ContextFlagCondition("deep_focus", False),
                    )
                ),
            )
        )
        assert engine2.evaluate_physical(
            PhysicalContext(now=T0, location=None, flags={"deep_focus": False})
        ) == ()
        # 两者齐备：成熟
        matured = engine.evaluate_physical(
            PhysicalContext(now=T0, location=OFFICE, flags={"deep_focus": False})
        )
        assert [t.task_id for t in matured] == ["t:buyback"]


# ----------------------------------------------------------------------
# 门禁 3：Level-2 机会式捎带（仅用户主动唤醒 + 相关场景）
# ----------------------------------------------------------------------


class TestLevel2OpportunisticPiggyback:
    def _engine_with_semantic_task(self) -> ConditionalTaskEngine:
        engine = ConditionalTaskEngine()
        engine.register(
            make_task(
                "t:equity",
                SemanticSceneCondition(frozenset({"external_event:equity_change"})),
                "诉讼对方实控人股权变更提醒",
            )
        )
        return engine

    def test_semantic_task_never_touched_by_level1(self):
        engine = self._engine_with_semantic_task()
        # 无论机械快轨扫描多少次，语义任务绝不成熟
        for i in range(30):
            engine.evaluate_physical(
                PhysicalContext(
                    now=T0 + timedelta(hours=i),
                    location=OFFICE,
                    biometrics={"heart_rate_bpm": 120.0},
                    flags={"deep_focus": False},
                )
            )
        assert engine.get("t:equity").state is ConditionalTaskState.DORMANT
        assert engine.meter.llm_calls == 0

    def test_piggyback_requires_active_user_wake(self):
        engine = self._engine_with_semantic_task()
        with pytest.raises(ValueError, match="wake_ref"):
            engine.piggyback_semantic(wake_ref="", scene_tags=frozenset({"external_event:equity_change"}))
        with pytest.raises(ValueError, match="wake_ref"):
            engine.piggyback_semantic(wake_ref="   ", scene_tags=frozenset())
        assert engine.get("t:equity").state is ConditionalTaskState.DORMANT

    def test_piggyback_scene_match_matures_without_matching_stays(self):
        engine = self._engine_with_semantic_task()
        # 场景不匹配：保持 DORMANT
        assert engine.piggyback_semantic(
            wake_ref="wake:user:001", scene_tags=frozenset({"contract_review"})
        ) == ()
        assert engine.get("t:equity").state is ConditionalTaskState.DORMANT
        # 场景匹配：顺路捎带成熟
        matured = engine.piggyback_semantic(
            wake_ref="wake:user:002", scene_tags=frozenset({"external_event:equity_change", "morning_brief"})
        )
        assert [t.task_id for t in matured] == ["t:equity"]
        assert "level2:piggyback:wake:user:002" in engine.get("t:equity").maturity_reason

    def test_no_autonomous_wake_api_exists(self):
        # 引擎不存在任何"自主唤醒"入口（防退化审计）
        forbidden = {"wake_autonomous", "self_wake", "autonomous_evaluate", "evaluate_semantic"}
        exposed = {name for name in dir(ConditionalTaskEngine) if not name.startswith("_")}
        assert not (forbidden & exposed)


# ----------------------------------------------------------------------
# 门禁 4：状态机非法跃迁 100% 拦截
# ----------------------------------------------------------------------


class TestIllegalStateTransitionInterception:
    def _fresh(self, state: ConditionalTaskState) -> ConditionalTaskEngine:
        engine = ConditionalTaskEngine()
        task = make_task("t:sm", TimeAbsoluteCondition(T0))
        engine.register(task)
        if state is not ConditionalTaskState.DORMANT:
            task.state = state
        return engine

    @pytest.mark.parametrize(
        ("from_state", "op"),
        [
            (ConditionalTaskState.DORMANT, "start"),      # 越级触发执行：严禁
            (ConditionalTaskState.DORMANT, "complete"),   # 越级完成：严禁
            (ConditionalTaskState.READY, "complete"),     # 未运行不得完成
            (ConditionalTaskState.RUNNING, "start"),      # 回退：严禁
            (ConditionalTaskState.COMPLETED, "start"),    # 死任务复活：严禁
            (ConditionalTaskState.COMPLETED, "complete"), # 重复完成：严禁
        ],
    )
    def test_illegal_transitions_all_intercepted(self, from_state, op):
        engine = self._fresh(from_state)
        with pytest.raises(IllegalStateTransitionError):
            if op == "start":
                engine.start("t:sm", at=T0)
            else:
                engine.complete("t:sm", at=T0)

    def test_legal_chain_end_to_end(self):
        engine = ConditionalTaskEngine()
        task = make_task("t:legal", TimeAbsoluteCondition(T0))
        engine.register(task)
        engine.evaluate_physical(PhysicalContext(now=T0))
        assert task.state is ConditionalTaskState.READY
        engine.start("t:legal", at=T0 + timedelta(minutes=1))
        assert task.state is ConditionalTaskState.RUNNING
        engine.complete("t:legal", at=T0 + timedelta(minutes=30))
        assert task.state is ConditionalTaskState.COMPLETED
        assert task.completed_at == T0 + timedelta(minutes=30)

    def test_already_ready_task_not_re_matured(self):
        engine = ConditionalTaskEngine()
        engine.register(make_task("t:once", TimeAbsoluteCondition(T0)))
        assert len(engine.evaluate_physical(PhysicalContext(now=T0))) == 1
        assert engine.evaluate_physical(PhysicalContext(now=T0 + timedelta(days=1))) == ()
        assert len(engine.by_state(ConditionalTaskState.READY)) == 1

    def test_registration_contract(self):
        engine = ConditionalTaskEngine()
        task = make_task("t:dup", TimeAbsoluteCondition(T0))
        engine.register(task)
        with pytest.raises(ValueError, match="already registered"):
            engine.register(make_task("t:dup", TimeAbsoluteCondition(T0)))
        non_dormant = make_task("t:nd", TimeAbsoluteCondition(T0))
        non_dormant.state = ConditionalTaskState.READY
        with pytest.raises(ValueError, match="DORMANT"):
            engine.register(non_dormant)
