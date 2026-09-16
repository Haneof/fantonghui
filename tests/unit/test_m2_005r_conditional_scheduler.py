"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制 —— 四大硬门禁验收。

工单情境：长期高压的创业企业法务总监，日程挂载 200 项跨周期复杂条件任务。
三条样例任务在本文件里被逐条建成法定 ``TriggerExpression`` AST：

- 「当诉讼对方实控人出现股权变更时提醒」→ 纯语义 → Level-2 捎带轨；
- 「连续 3 天晚间心率超过 95bpm 时启动心内科预约建档」→ ``obs_threshold`` → Level-1；
- 「回到上海办公室且处于非深度专注状态时提示签署对赌回购协议」→ 机械地理围栏 AND
  语义情境 → Level-2，且机械前置子树可在**不叫模型**的情况下先行否决。

门禁 4 的"100% 拦截"用**穷举全部法定 TaskState**的方式验证，而不是只测工单举的
那两个例子——只测举例等于把拦截率的分母留给运气。
"""
from __future__ import annotations

import copy
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios_core.contracts.enums import ErrorCode, TaskState
from aios_core.contracts.enums_v3 import TriggerOp, TriState
from aios_core.contracts.models_v3 import (
    EventMatched,
    MechanicalPredicate,
    SemanticPredicate,
    TimeReached,
    TriggerExpression,
)
from aios_core.scheduler.conditional_engine import (
    DORMANT,
    PRIMARY_CHAIN,
    AutonomousWakeProhibitedError,
    ConditionalEngine,
    ForgedWakeTokenError,
    IllegalStateTransitionError,
    MissingTriggerCriteriaError,
    SchedulerError,
    TrackKind,
    TrackMismatchError,
    load_task_readiness_policy,
    reference_physical_resolver,
)
from aios_core.services.eligibility_worker import InMemoryEventBus
from aios_core.services.state_machines import allowed_task_transitions

UTC = timezone.utc
BASE = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

#: 工单情境的主体（法务总监）
SUBJECT = "user_legal_director"


# ----------------------------------------------------------------------
# AST 构造助手（一律走法定 TriggerExpression，绝不另造条件表示）
# ----------------------------------------------------------------------


def atom(leaf) -> TriggerExpression:
    return TriggerExpression(op=TriggerOp.ATOM, leaf=leaf)


def all_of(*children: TriggerExpression) -> TriggerExpression:
    return TriggerExpression(op=TriggerOp.ALL_OF, children=list(children))


def not_of(child: TriggerExpression) -> TriggerExpression:
    return TriggerExpression(op=TriggerOp.NOT, children=[child])


def time_trigger(at: datetime) -> TriggerExpression:
    return atom(TimeReached(at=at))


def hr_streak_trigger(*, value: int = 95, streak_days: int = 3,
                      source_ref: str = "hr_evening") -> TriggerExpression:
    """「连续 N 天晚间心率超过 X bpm」——纯客观物理条件，Level-1。"""
    return atom(
        MechanicalPredicate(
            kind="obs_threshold",
            params={
                "source_ref": source_ref,
                "field": "hr_bpm",
                "op": ">=",
                "value": value,
                "streak_days": streak_days,
            },
        )
    )


def geofence_trigger(*, equals: str = "shanghai_office",
                     source_ref: str = "location_now") -> TriggerExpression:
    """「回到上海办公室」——地理围栏，纯客观物理条件，Level-1。"""
    return atom(
        MechanicalPredicate(
            kind="state_change",
            params={"source_ref": source_ref, "field": "location", "equals": equals},
        )
    )


def equity_change_trigger() -> TriggerExpression:
    """「诉讼对方实控人出现股权变更」——需要语义识别，Level-2。"""
    return atom(
        SemanticPredicate(kind="context_fit", prompt_signature="equity_change_review")
    )


def vam_signing_trigger() -> TriggerExpression:
    """「回到上海办公室且非深度专注时提示签署对赌回购协议」——机械 AND 语义。"""
    return all_of(
        geofence_trigger(),
        atom(SemanticPredicate(kind="context_fit", prompt_signature="not_deep_focus")),
    )


def make_engine() -> ConditionalEngine:
    return ConditionalEngine(clock=lambda: BASE)


# ----------------------------------------------------------------------
# 门禁 1：未成熟任务 Token 严格为 0（DORMANT 物理隐形）
# ----------------------------------------------------------------------


class TestGate1DormantTokenZero:
    def test_dormant_tasks_contribute_exactly_zero_tokens(self):
        engine = make_engine()
        for index in range(200):  # 工单情境：200 项跨周期复杂条件任务
            engine.register_task(
                f"task-{index:03d}", SUBJECT,
                f"第 {index} 项跨周期条件任务：当某客观条件成立时提醒法务总监处理",
                time_trigger(BASE + timedelta(days=index + 1)),
            )
        assert len(engine.task_ids(state=DORMANT)) == 200

        build = engine.build_manifest()
        assert build.mounted == ()
        assert build.token_total == 0
        assert build.dormant_population == 200
        assert build.model_calls == 0

    def test_token_total_is_invariant_under_dormant_population_growth(self):
        """**门禁 1 的真正证明**：DORMANT 数量增长，token_total 分毫不动。

        只断言"DORMANT 不在结果里"是不够的——那挡不住"先全量估算 200 项再筛掉"
        的实现，而那种实现照样会把未成熟任务灌进 prompt 组装路径、照样烧 token。
        不变性才排除得掉它。
        """
        engine = make_engine()
        engine.register_task("ready-1", SUBJECT, "已就绪：签署对赌回购协议", time_trigger(BASE))
        engine.register_task("ready-2", SUBJECT, "已就绪：心内科预约建档", time_trigger(BASE))
        engine.tick(BASE, {}, None)  # 两项时间已到期 -> 自动 READY
        assert len(engine.task_ids(state=TaskState.READY)) == 2

        baseline = engine.build_manifest()
        assert baseline.token_total > 0
        assert len(baseline.mounted) == 2

        for population in (1, 50, 200, 1000):
            for index in range(population):
                engine.register_task(
                    f"dormant-{population}-{index:04d}", SUBJECT,
                    f"未成熟任务 {population}-{index}：" + "很长的条件描述" * 20,
                    time_trigger(BASE + timedelta(days=400 + index)),
                )
            grown = engine.build_manifest()
            assert grown.token_total == baseline.token_total, (
                f"灌入 {population} 项 DORMANT 后 token_total 从 {baseline.token_total} "
                f"变成 {grown.token_total} —— 未成熟任务泄漏进了装配路径"
            )
            assert len(grown.mounted) == 2
            assert grown.model_calls == 0

    def test_estimate_audit_never_charges_a_dormant_task(self):
        """引擎自己记账：token 估算只发生在 READY 上，DORMANT 一次都没有。"""
        engine = make_engine()
        engine.register_task("d1", SUBJECT, "休眠任务一", time_trigger(BASE + timedelta(days=9)))
        engine.register_task("d2", SUBJECT, "休眠任务二", time_trigger(BASE + timedelta(days=9)))
        engine.build_manifest()
        audit = engine.estimate_audit()
        assert audit.get(DORMANT.value, {"calls": 0})["calls"] == 0
        assert audit == {}, f"DORMANT-only 场景下不应有任何估算记账，实得 {audit}"

        engine.register_task("r1", SUBJECT, "就绪任务", time_trigger(BASE))
        engine.tick(BASE, {}, None)
        engine.build_manifest()
        audit = engine.estimate_audit()
        assert audit[TaskState.READY.value]["calls"] == 1
        assert audit.get(DORMANT.value, {"calls": 0})["calls"] == 0

    def test_manifest_mounts_only_ready_tasks_per_policy(self):
        """政策字段 manifest_mounts_only_ready_tasks 必须在实现里真的成立。"""
        policy = load_task_readiness_policy()
        assert policy["manifest_mounts_only_ready_tasks"] is True

        engine = make_engine()
        engine.register_task("dormant", SUBJECT, "休眠", time_trigger(BASE + timedelta(days=2)))
        engine.register_task("ready", SUBJECT, "就绪", time_trigger(BASE))
        engine.tick(BASE, {}, None)
        # 制造一个 RUNNING 态：它也不是 READY，同样不得挂载
        engine.request_execution("ready")
        build = engine.build_manifest()
        assert build.mounted == ()
        assert build.token_total == 0

    def test_manifest_is_scoped_by_subject(self):
        engine = make_engine()
        engine.register_task("a", "user_a", "甲的就绪任务", time_trigger(BASE))
        engine.register_task("b", "user_b", "乙的就绪任务", time_trigger(BASE))
        engine.tick(BASE, {}, None)
        only_a = engine.build_manifest(subject="user_a")
        assert [slot.task_id for slot in only_a.mounted] == ["a"]
        assert only_a.token_total < engine.build_manifest().token_total


# ----------------------------------------------------------------------
# 门禁 2：Level-1 机械快轨 —— 0 Token、1ms、自动跃迁 READY
# ----------------------------------------------------------------------


class TestGate2Level1MechanicalFastTrack:
    def test_pure_time_expiry_promotes_with_zero_model_calls(self):
        engine = make_engine()
        engine.register_task("due", SUBJECT, "纯时间到期：季度合规复核", time_trigger(BASE))
        report = engine.tick(BASE, {}, None)
        assert report.promoted_to_ready == ("due",)
        assert engine.state_of("due") is TaskState.READY
        assert report.model_calls == 0
        assert engine.meter.model_calls == 0
        assert engine.meter.tokens == 0

    def test_hr_threshold_streak_promotes_with_zero_model_calls(self):
        """工单样例二：连续 3 天晚间心率超过 95bpm。"""
        engine = make_engine()
        engine.register_task("hr", SUBJECT, "启动心内科预约建档", hr_streak_trigger())
        assert engine.task("hr").track == TrackKind.LEVEL1_MECHANICAL

        # 未达阈值 -> 不跃迁
        engine.tick(BASE, {"hr_evening": {"hr_bpm": 88, "daily_streak": 0}}, None,
                    predicate_resolver=reference_physical_resolver)
        assert engine.state_of("hr") is DORMANT

        # 达标但连续天数不足 -> 仍不跃迁（不许猜 TRUE）
        engine.tick(BASE, {"hr_evening": {"hr_bpm": 101, "daily_streak": 2}}, None,
                    predicate_resolver=reference_physical_resolver)
        assert engine.state_of("hr") is DORMANT

        # 达标且连续 3 天 -> 纯 Python 判定，0 模型调用，自动 READY
        report = engine.tick(BASE, {"hr_evening": {"hr_bpm": 101, "daily_streak": 3}}, None,
                             predicate_resolver=reference_physical_resolver)
        assert report.promoted_to_ready == ("hr",)
        assert report.model_calls == 0
        assert engine.meter.model_calls == 0

    def test_geofence_promotes_with_zero_model_calls(self):
        """工单样例三的机械部分：回到上海办公室。"""
        engine = make_engine()
        engine.register_task("geo", SUBJECT, "到办公室后归档证据", geofence_trigger())
        engine.tick(BASE, {"location_now": {"location": "home"}}, None,
                    predicate_resolver=reference_physical_resolver)
        assert engine.state_of("geo") is DORMANT
        report = engine.tick(BASE, {"location_now": {"location": "shanghai_office"}}, None,
                             predicate_resolver=reference_physical_resolver)
        assert report.promoted_to_ready == ("geo",)
        assert report.model_calls == 0

    def test_missing_world_data_yields_unknown_never_guessed_true(self):
        """fail-closed：世界里没有这个来源 => UNKNOWN，绝不猜 TRUE。"""
        engine = make_engine()
        engine.register_task("hr", SUBJECT, "心率任务", hr_streak_trigger())
        report = engine.tick(BASE, {}, None, predicate_resolver=reference_physical_resolver)
        assert report.promoted_to_ready == ()
        assert engine.state_of("hr") is DORMANT
        assert engine.task("hr").last_verdict is TriState.UNKNOWN

    def test_single_task_decision_latency_within_1ms(self):
        """工单门禁 2 的 1ms：200 项任务逐项判定，单任务最大耗时 <= 1ms。"""
        engine = make_engine()
        for index in range(200):
            engine.register_task(
                f"t-{index:03d}", SUBJECT, f"任务 {index}",
                time_trigger(BASE + timedelta(hours=1)),
            )
        engine.tick(BASE, {}, None)  # 预热：一次性属性查找/分支预测成本不入门禁
        report = engine.tick(BASE + timedelta(minutes=30), {}, None)
        assert report.evaluated == 200
        assert report.max_task_ms <= 1.0, f"单任务判定 {report.max_task_ms:.3f}ms 越过 1ms"
        assert report.elapsed_ms <= 200.0, f"整轮 200 项耗时 {report.elapsed_ms:.2f}ms"
        assert report.model_calls == 0

    def test_tick_never_touches_semantic_track_tasks(self):
        """tick 不做周期性语义扫荡（periodic_todo_sweep_prohibited）。"""
        engine = make_engine()
        engine.register_task("sem", SUBJECT, "股权变更提醒", equity_change_trigger())
        engine.register_task("mixed", SUBJECT, "签署对赌回购协议", vam_signing_trigger())
        assert engine.task("sem").track == TrackKind.LEVEL2_SEMANTIC
        assert engine.task("mixed").track == TrackKind.LEVEL2_SEMANTIC

        report = engine.tick(BASE, {"location_now": {"location": "shanghai_office"}}, None,
                             predicate_resolver=reference_physical_resolver)
        assert report.evaluated == 0
        assert report.semantic_tasks_touched == 0
        assert engine.state_of("sem") is DORMANT
        assert engine.state_of("mixed") is DORMANT
        assert engine.meter.model_calls == 0

    def test_event_bus_is_replayed_per_task_not_drained_by_the_first(self):
        """**回归守卫**：一条事件必须能触发所有匹配它的任务。

        既有 ``MechanicalEvaluator.event_matched`` 的语义是 drain（取走即清空）。
        若逐任务共享同一条真总线，第一个含 EventMatched 的任务会把本 tick 的事件
        全部喝干，后续任务一律判 no_events_drained —— 200 项里只有排在最前的
        那几项能被事件触发，且失败是静默的。
        """
        engine = make_engine()
        for index in range(3):
            engine.register_task(
                f"ev-{index}", SUBJECT, f"事件任务 {index}",
                atom(EventMatched(object_type="equity_change")),
            )
        bus = InMemoryEventBus()
        bus.push({
            "object_type": "equity_change",
            "payload": {"target": "对手方实控人"},
            "occurred_at": BASE.isoformat(),
        })
        report = engine.tick(BASE, {}, bus)
        assert report.evaluated == 3
        assert len(report.promoted_to_ready) == 3, (
            f"只有 {len(report.promoted_to_ready)} 项被同一条事件触发，"
            "说明事件总线被第一个任务喝干了"
        )
        assert all(engine.state_of(f"ev-{i}") is TaskState.READY for i in range(3))
        assert report.model_calls == 0

    def test_level1_track_never_invokes_the_review_lane(self):
        """机械轨任务在任何路径上都不产生模型调用。"""
        engine = make_engine()
        engine.register_task("hr", SUBJECT, "心率任务", hr_streak_trigger())
        engine.tick(BASE, {"hr_evening": {"hr_bpm": 120, "daily_streak": 9}}, None,
                    predicate_resolver=reference_physical_resolver)
        assert engine.state_of("hr") is TaskState.READY
        assert engine.meter.snapshot() == {"model_calls": 0, "tokens": 0, "call_log": []}
        # 机械轨任务送语义复核必须被拒（那是纯浪费预算）
        token = engine.issue_user_wake_token("s1", ["meeting"])
        with pytest.raises(TrackMismatchError):
            engine.piggyback_evaluate("hr", token, lambda sig, ctx: (TriState.TRUE, 100))
        assert engine.meter.model_calls == 0


# ----------------------------------------------------------------------
# 门禁 3：Level-2 机会式捎带（绝不自主唤醒大模型）
# ----------------------------------------------------------------------


class TestGate3OpportunisticPiggyback:
    def test_semantic_task_without_wake_token_is_refused(self):
        engine = make_engine()
        engine.register_task("sem", SUBJECT, "股权变更提醒", equity_change_trigger())
        with pytest.raises(AutonomousWakeProhibitedError):
            engine.piggyback_evaluate("sem", None, lambda sig, ctx: (TriState.TRUE, 500))
        assert engine.meter.model_calls == 0
        assert engine.state_of("sem") is DORMANT

    def test_forged_wake_token_is_refused(self):
        """任务侧无法伪造"用户唤醒了我"：HMAC 签名不符即拒。"""
        engine = make_engine()
        engine.register_task("sem", SUBJECT, "股权变更提醒", equity_change_trigger())
        genuine = engine.issue_user_wake_token("s1", ["meeting"])
        forged = type(genuine)(
            session_id=genuine.session_id,
            issued_at=genuine.issued_at,
            context=frozenset({"meeting", "deep_sleep"}),  # 偷偷扩了情境
            signature=genuine.signature,
        )
        with pytest.raises(ForgedWakeTokenError):
            engine.piggyback_evaluate("sem", forged, lambda sig, ctx: (TriState.TRUE, 500))
        assert engine.meter.model_calls == 0

        # 换个会话 id 复用签名同样不行
        hijacked = type(genuine)(
            session_id="attacker", issued_at=genuine.issued_at,
            context=genuine.context, signature=genuine.signature,
        )
        with pytest.raises(ForgedWakeTokenError):
            engine.piggyback_evaluate("sem", hijacked, lambda sig, ctx: (TriState.TRUE, 500))
        assert engine.meter.model_calls == 0

    def test_one_wake_cannot_piggyback_the_same_task_twice(self):
        """同一次用户唤醒对同一任务只许评估一次 —— 这就是"绝不频繁唤醒"。"""
        engine = make_engine()
        engine.register_task("sem", SUBJECT, "股权变更提醒", equity_change_trigger())
        token = engine.issue_user_wake_token("s1", ["alone_silent"])
        first = engine.piggyback_evaluate(
            "sem", token, lambda sig, ctx: (TriState.UNKNOWN, 300)
        )
        assert first.invoked_model is True
        assert engine.meter.model_calls == 1
        with pytest.raises(AutonomousWakeProhibitedError):
            engine.piggyback_evaluate("sem", token, lambda sig, ctx: (TriState.UNKNOWN, 300))
        assert engine.meter.model_calls == 1, "重复捎带又叫了一次模型"

    def test_irrelevant_context_skips_without_spending_a_model_call(self):
        """用户此刻不在相关场景 => 正常跳过，不叫模型（不是错误）。"""
        engine = make_engine()
        engine.register_task(
            "vam", SUBJECT, "签署对赌回购协议", vam_signing_trigger(),
            required_context=["in_geofence", "idle_transition"],
        )
        token = engine.issue_user_wake_token("s1", ["driving"])  # 在开车，不相关
        outcome = engine.piggyback_evaluate(
            "vam", token, lambda sig, ctx: (TriState.TRUE, 800)
        )
        assert outcome.invoked_model is False
        assert outcome.model_calls == 0
        assert outcome.reason.startswith("context_not_relevant")
        assert "in_geofence" in outcome.reason
        assert engine.meter.model_calls == 0
        assert engine.state_of("vam") is DORMANT

    def test_mechanical_prefix_false_vetoes_without_a_model_call(self):
        """工单样例三：人不在上海办公室时，连模型都不必问。

        这是"机会式捎带"省钱的实质：机械上就不可能成立的事，不花一次模型调用。
        """
        engine = make_engine()
        engine.register_task(
            "vam", SUBJECT, "签署对赌回购协议", vam_signing_trigger(),
            required_context=["in_geofence"],
        )
        token = engine.issue_user_wake_token("s1", ["in_geofence"])
        outcome = engine.piggyback_evaluate(
            "vam", token, lambda sig, ctx: (TriState.TRUE, 800),
            now_utc=BASE, world_payloads={"location_now": {"location": "beijing_home"}},
            predicate_resolver=reference_physical_resolver,
        )
        assert outcome.invoked_model is False
        assert outcome.verdict is TriState.FALSE
        assert outcome.reason.startswith("mechanical_prefix_false")
        assert engine.meter.model_calls == 0
        assert engine.meter.tokens == 0

    def test_piggyback_true_promotes_and_charges_exactly_once(self):
        engine = make_engine()
        engine.register_task(
            "vam", SUBJECT, "签署对赌回购协议", vam_signing_trigger(),
            required_context=["in_geofence"],
        )
        token = engine.issue_user_wake_token("s1", ["in_geofence"])
        seen: list = []

        def review_fn(signature, context):
            seen.append((signature, context))
            return TriState.TRUE, 640

        outcome = engine.piggyback_evaluate(
            "vam", token, review_fn, now_utc=BASE,
            world_payloads={"location_now": {"location": "shanghai_office"}},
            predicate_resolver=reference_physical_resolver,
        )
        assert outcome.invoked_model is True
        assert outcome.promoted_to_ready is True
        assert engine.state_of("vam") is TaskState.READY
        assert engine.meter.model_calls == 1
        assert engine.meter.tokens == 640
        assert seen == [("not_deep_focus", frozenset({"in_geofence"}))]

    def test_review_adapter_must_return_legal_tristate(self):
        engine = make_engine()
        engine.register_task("sem", SUBJECT, "股权变更提醒", equity_change_trigger())
        token = engine.issue_user_wake_token("s1", ["alone_silent"])
        with pytest.raises(SchedulerError):
            engine.piggyback_evaluate("sem", token, lambda sig, ctx: ("maybe", 100))

    def test_model_charging_has_exactly_one_call_site_and_it_is_token_guarded(self):
        """**结构性守卫**：全模块只有一处能给模型计费，且它在令牌守卫之后。

        这条比"测几个场景都返回 0"强得多：它排除了将来有人在别处新增一条
        自主调用模型的路径。任何新增计费点都会让本测试立刻变红。
        """
        source = Path(inspect.getfile(ConditionalEngine)).read_text(encoding="utf-8")
        assert source.count("self.meter.charge(") == 1, (
            "模型计费点必须唯一；出现第二个计费点就意味着多了一条可能自主唤醒的路径"
        )
        charge_index = source.index("self.meter.charge(")
        fn_start = source.rindex("def piggyback_evaluate", 0, charge_index)
        following = source.find("\n    def ", charge_index)
        assert fn_start < charge_index < (following if following != -1 else len(source)), (
            "唯一的计费点必须位于 piggyback_evaluate 内部"
        )
        # 且该方法内，计费点必须在令牌校验之后
        guard = source.index("hmac.compare_digest", fn_start)
        assert guard < charge_index, "计费点必须排在 HMAC 令牌校验之后"

    def test_engine_offers_no_periodic_sweep_entry_point(self):
        """政策 periodic_todo_sweep_prohibited：不得存在"遍历全部待办求值"的入口。"""
        assert load_task_readiness_policy()["periodic_todo_sweep_prohibited"] is True
        public = [
            name for name, _ in inspect.getmembers(ConditionalEngine, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for banned in ("sweep", "sweep_all", "evaluate_all", "scan_todos", "review_all"):
            assert banned not in public, f"出现了被政策禁止的扫荡入口 {banned}"
        # tick 只碰机械轨；piggyback 只针对单个任务且需令牌
        assert "tick" in public and "piggyback_evaluate" in public


# ----------------------------------------------------------------------
# 门禁 4：状态机非法跃迁 100% 拦截（穷举全部法定状态）
# ----------------------------------------------------------------------


class TestGate4IllegalTransitionInterception:
    def test_primary_chain_is_legal_end_to_end(self):
        engine = make_engine()
        engine.register_task("t", SUBJECT, "任务", time_trigger(BASE))
        assert engine.state_of("t") is DORMANT
        assert [s.value for s in PRIMARY_CHAIN] == ["draft", "ready", "running", "completed"]

        engine.tick(BASE, {}, None)
        assert engine.state_of("t") is TaskState.READY
        engine.request_execution("t")
        assert engine.state_of("t") is TaskState.RUNNING
        engine.complete("t")
        assert engine.state_of("t") is TaskState.COMPLETED

    @pytest.mark.parametrize("target", list(TaskState))
    def test_every_transition_from_dormant_matches_the_canonical_table(self, target):
        """穷举法定 TaskState 全集：合法即放行，非法即 100% 拦截。"""
        engine = make_engine()
        engine.register_task("t", SUBJECT, "任务", time_trigger(BASE + timedelta(days=1)))
        assert engine.state_of("t") is DORMANT
        legal = allowed_task_transitions(DORMANT)
        if target in legal:
            assert engine.transition("t", target) is target
        else:
            with pytest.raises(IllegalStateTransitionError):
                engine.transition("t", target)
            assert engine.state_of("t") is DORMANT, "拦截失败后状态被污染了"

    @pytest.mark.parametrize("state", list(TaskState))
    def test_execution_is_allowed_only_from_ready_for_every_state(self, state):
        """穷举：从任何一个状态请求执行，只有 READY 放行，其余 100% 拦截。"""
        engine = make_engine()
        engine.register_task("t", SUBJECT, "任务", time_trigger(BASE + timedelta(days=1)))
        # 白盒置位以覆盖法定路径不可直达的状态（如 WAITING_EVIDENCE 需先 RUNNING）。
        # 这里测的是**守卫**本身，故直接设定当前态是正当的。
        engine.task("t").state = state
        if state is TaskState.READY:
            assert engine.request_execution("t") is TaskState.RUNNING
        else:
            with pytest.raises(IllegalStateTransitionError):
                engine.request_execution("t")
            assert engine.state_of("t") is state, "拦截后状态被改动了"
            assert engine.meter.model_calls == 0

    def test_dormant_cannot_jump_straight_to_running_or_completed(self):
        """工单点名的两种越权：DORMANT 直接执行 / 直接完成。"""
        engine = make_engine()
        engine.register_task("t", SUBJECT, "任务", time_trigger(BASE + timedelta(days=1)))
        for target in (TaskState.RUNNING, TaskState.COMPLETED):
            with pytest.raises(IllegalStateTransitionError) as exc:
                engine.transition("t", target)
            assert exc.value.code is ErrorCode.INVALID_ARGUMENT
            assert engine.state_of("t") is DORMANT

    def test_terminal_states_accept_nothing(self):
        engine = make_engine()
        engine.register_task("t", SUBJECT, "任务", time_trigger(BASE))
        engine.tick(BASE, {}, None)
        engine.request_execution("t")
        engine.complete("t")
        assert allowed_task_transitions(TaskState.COMPLETED) == frozenset()
        for target in TaskState:
            with pytest.raises(IllegalStateTransitionError):
                engine.transition("t", target)

    def test_running_is_reachable_only_from_ready_in_the_canonical_table(self):
        """**这条不变量是 request_execution 显式守卫可以"冗余"的前提**。

        变异测试发现：删掉 request_execution 里的 ``state is not READY`` 检查，
        62 项测试依旧全绿 —— 因为 ``transition()`` 仍会查法定表并抛同一个异常，
        而法定表里 RUNNING 只能从 READY 到达。所以门禁 4 的执行力**不依赖**
        本模块自己的检查，而是锚在 ``services.state_machines`` 的法定表上，
        这正是"不复制转移表"的设计意图（显式守卫的价值只剩错误信息更具体）。

        但这个冗余是**有条件**的：一旦将来有人给法定表加了另一条通往 RUNNING 的边，
        显式守卫立刻变成承重墙，而本测试会先变红，提醒复核。
        """
        sources = [
            state for state in TaskState
            if TaskState.RUNNING in allowed_task_transitions(state)
        ]
        assert sources == [TaskState.READY], (
            f"法定表里通往 RUNNING 的来源变成了 {[s.value for s in sources]}；"
            "request_execution 的显式 READY 守卫自此成为承重墙，必须复核其测试覆盖"
        )

    def test_dormant_is_the_canonical_draft_not_a_parallel_enum(self):
        """**反双枚举守卫**：DORMANT 必须就是法定 TaskState.DRAFT 本体。

        本仓库曾出现 ObjectType / ObjectTypeV3 双枚举，导致 v3 扩展类型完全无法
        落盘（13 项测试红）。同一个坑不踩第二次：工单词汇只允许做别名，
        不允许新增枚举成员。
        """
        assert DORMANT is TaskState.DRAFT
        assert not hasattr(TaskState, "DORMANT"), (
            "法定 TaskState 里出现了 DORMANT 成员 —— 这是双枚举漂移的开端"
        )
        assert set(PRIMARY_CHAIN) <= set(TaskState)

    def test_transition_table_is_imported_not_copied(self):
        """引擎不得自带一份转移表副本（副本必然漂移）。"""
        source = Path(inspect.getfile(ConditionalEngine)).read_text(encoding="utf-8")
        assert "from aios_core.services.state_machines import allowed_task_transitions" in source
        assert "allowed_task_transitions(task.state)" in source
        # 模块内不得出现第二份硬编码转移表。注意不能简单断言字符串不存在：
        # docstring 里**引用** services.state_machines._TASK_TRANSITIONS 是正当的
        # （说明来源），要禁的是在本模块里**赋值**出一份副本。
        import re

        assert re.search(r"^\s*_TASK_TRANSITIONS\s*[:=]", source, re.M) is None, (
            "本模块出现了一份自己的转移表赋值 —— 副本必然与法定表漂移"
        )
        assert "frozenset({TaskState." not in source, (
            "本模块内出现了硬编码的 TaskState 转移集合"
        )


# ----------------------------------------------------------------------
# 登记闸与法律绑定
# ----------------------------------------------------------------------


class TestAdmissionAndPolicyBinding:
    def test_task_without_trigger_criteria_is_rejected(self):
        """法律：trigger_criteria_is_required_on_task，错误码 INVALID_ARGUMENT。"""
        engine = make_engine()
        with pytest.raises(MissingTriggerCriteriaError) as exc:
            engine.register_task("todo", SUBJECT, "无条件待办", None)
        assert exc.value.code is ErrorCode.INVALID_ARGUMENT
        assert engine.task_ids() == ()

    @pytest.mark.parametrize("bad", [lambda ctx: True, "hr_bpm > 95", "eval('1+1')", 42])
    def test_non_finite_json_trigger_is_rejected(self, bad):
        """法律：predicate_dsl_must_be_finite_json + python_eval_prohibited。"""
        engine = make_engine()
        with pytest.raises(SchedulerError):
            engine.register_task("t", SUBJECT, "任务", bad)

    def test_unregistered_context_predicate_is_rejected(self):
        engine = make_engine()
        with pytest.raises(SchedulerError, match="未在政策登记"):
            engine.register_task(
                "t", SUBJECT, "任务", time_trigger(BASE),
                required_context=["in_geofence", "mood_sad"],
            )
        with pytest.raises(SchedulerError, match="未登记谓词"):
            engine.issue_user_wake_token("s1", ["made_up_context"])

    def test_registered_predicates_are_all_legal(self):
        registry = set(load_task_readiness_policy()["context_predicate_registry"])
        engine = make_engine()
        engine.register_task(
            "t", SUBJECT, "任务", time_trigger(BASE), required_context=sorted(registry)
        )
        assert engine.task("t").required_context == frozenset(registry)

    def test_duplicate_task_id_is_rejected(self):
        engine = make_engine()
        engine.register_task("t", SUBJECT, "任务", time_trigger(BASE))
        with pytest.raises(SchedulerError, match="重复登记"):
            engine.register_task("t", SUBJECT, "另一个", time_trigger(BASE))

    def test_unknown_task_lookup_raises_not_found(self):
        engine = make_engine()
        with pytest.raises(SchedulerError) as exc:
            engine.state_of("ghost")
        assert exc.value.code is ErrorCode.NOT_FOUND

    def test_engine_refuses_to_run_on_drifted_policy(self):
        """引用而非复制：政策字段被改动，引擎拒绝启动而不是带着旧参数静默运行。"""
        good = load_task_readiness_policy()
        for key, _ in (
            ("manifest_mounts_only_ready_tasks", False),
            ("periodic_todo_sweep_prohibited", False),
            ("python_eval_prohibited", False),
            ("trigger_criteria_is_required_on_task", False),
        ):
            drifted = copy.deepcopy(good)
            drifted[key] = False
            with pytest.raises(SchedulerError, match="法定值"):
                ConditionalEngine(policy=drifted)
        stripped = copy.deepcopy(good)
        del stripped["manifest_mounts_only_ready_tasks"]
        with pytest.raises(SchedulerError, match="缺少法定字段"):
            ConditionalEngine(policy=stripped)

    def test_the_three_work_order_scenarios_classify_to_the_right_tracks(self):
        """工单三条样例任务必须落到正确的轨道上。"""
        engine = make_engine()
        engine.register_task("equity", SUBJECT, "股权变更提醒", equity_change_trigger())
        engine.register_task("hr", SUBJECT, "心内科预约建档", hr_streak_trigger())
        engine.register_task("vam", SUBJECT, "签署对赌回购协议", vam_signing_trigger())

        assert engine.task("equity").track == TrackKind.LEVEL2_SEMANTIC
        assert engine.task("hr").track == TrackKind.LEVEL1_MECHANICAL
        # 混合任务归语义轨，但其机械子树被单独抽出来做前置否决
        assert engine.task("vam").track == TrackKind.LEVEL2_SEMANTIC
        prefix = engine.task("vam").mechanical_prefix
        assert prefix is not None and not prefix.has_semantic()
        # 纯语义任务的机械前置为空 => 没有可以省钱的否决点
        assert engine.task("equity").mechanical_prefix is None
