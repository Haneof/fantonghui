"""M2-001 · 主动心跳唤醒调度 + Step-0 安全便利闸门 + 反馈冷却队列 —— 门禁测试

落地路径说明：工单点名 ``wake/cooldown_queue.py``，但该路径已被并行线的 M2-001
（入站高频事件防抖 + DEEP_SLEEP 绝对静默）占据并在远端裁决中被采信；按"不覆盖任何
既有文件"的常设指令，本工单落在 ``wake/heartbeat_step0_gate.py``。两套测试并存：
``test_m2_001_wake_cooldown.py``（并行线）与本文件。

四大硬门禁各自的可判定形式（政策 ``runtime_policy.json`` 的 ``heartbeat`` /
``step0_safety_gate`` / ``token_budget`` / ``threshold_governance`` 四段为唯一权威）：

1. 心跳触发 100% 带候选触发器 —— 用**穷举**证明：遍历全部 ``WakePriority`` ×
   全部唤醒源，非安全唤醒缺触发器一律在构造期被拒；投递与闸门各再拒一次。
2. Step-0 在任何模型调用之前执行且 ``model_calls == 0`` —— 不只测"跑完是 0"，
   还测**结构上无法叫模型**：闸门签名里没有任何模型/适配器形参，且本模块内
   ``meter.charge(`` 调用点数为 0（源码级断言，与 M2-005R 的"唯一 charge 点"
   纪律互为镜像 —— 那边是恰好一个，这边是恰好零个）。
3. 便利闸门有最终否决权，QUIET 降级为静默巡检并留痕 —— 遍历政策里**全部**
   便利判据（``b_convenience_mechanical`` + ``heartbeat.gate_predicates``），
   并断言不变量 ``巡检留痕数 == 心跳数 - 出声数``（否则"被取消"与"没运行"无法区分）。
4. 7 天平稳数据下固定节奏炸弹数 = 0；安全触发与绝对底线永不被压制 ——
   正面跑 42 次心跳断言 0 次出声、0 枚炸弹；反面让睡眠+勿扰+无 epoch+预算爆表
   同时成立，安全险情仍须穿透并经既有 dispatcher 走硬件旁路。

测试一律**从政策文件读取**判据清单，因此政策新增一条便利判据时，覆盖面自动扩张
——这正是"引用而非复制"在测试侧的收益。
"""

from __future__ import annotations

import ast
import inspect
import json
import typing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios_core.contracts.enums import ErrorCode, WakeSource, WakeState
from aios_core.contracts.enums_v3 import SafetyVerdict, TriState, WakeSourceV3
from aios_core.contracts.models_v3 import ManifestInstance, SafetyGateVerdict
from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.scheduler import conditional_engine as ce
from aios_core.wake.heartbeat_step0_gate import ModelCallMeter
from aios_core.wake import heartbeat_step0_gate as cq
from aios_core.wake import dispatcher as wake_dispatcher
from aios_core.wake.heartbeat_step0_gate import (
    ABSOLUTE_FLOOR_CHANNELS,
    PROPOSED_DEDUP_WINDOW_SECONDS,
    PROPOSED_FEEDBACK_COOLDOWNS,
    TRIGGER_KIND_LEGAL_NAME,
    BeatOutcome,
    BudgetExhaustedError,
    BudgetLedger,
    CandidateTrigger,
    CandidateWake,
    CooldownQueue,
    GateDecision,
    GateSignals,
    HeartbeatScheduler,
    MissingCandidateTriggerError,
    PromiseToSpeakError,
    QueueDecision,
    SilentPatrolRecord,
    Step0SafetyGate,
    ThresholdChangeEntry,
    WakeError,
    load_heartbeat_policy,
    load_runtime_policy,
    load_step0_policy,
    load_token_budget_policy,
    validate_policy_section,
)

MODULE_SOURCE = Path(cq.__file__).read_text(encoding="utf-8")
ROOT = load_runtime_policy()
HB = ROOT["heartbeat"]
S0 = ROOT["step0_safety_gate"]
TB = ROOT["token_budget"]
TG = ROOT["threshold_governance"]

NOW = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)

#: 便利判据全集 = Step-0 的 b 段 + 心跳段的 gate_predicates（去重保序）。
CONVENIENCE: list[str] = []
for _n in list(S0["checks"]["b_convenience_mechanical"]) + list(HB["gate_predicates"]):
    if _n not in CONVENIENCE:
        CONVENIENCE.append(_n)
HARD_SIGNALS: list[str] = list(S0["checks"]["a_safety_hard_signal"])


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


class FakeCockpitPipeline:
    """非 P0 投递的落点。既有 dispatcher 会调用 ``context.cockpit_pipeline.execute``。"""

    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, wake):  # noqa: ANN001 - 刻意宽松，模拟既有装配入口
        self.executed.append(wake.wake_id)
        return {"status": "COCKPIT_ASSEMBLED", "wake_id": wake.wake_id}


class FakeContext:
    def __init__(self) -> None:
        self.cockpit_pipeline = FakeCockpitPipeline()


@pytest.fixture
def meter() -> ModelCallMeter:
    return ModelCallMeter()


@pytest.fixture
def ledger() -> BudgetLedger:
    return BudgetLedger(
        heartbeat_cap=TB["subsystems"]["heartbeat"]["monthly_cap"],
        monthly_cap=TB["monthly_total_cap"],
    )


@pytest.fixture
def sched(meter) -> HeartbeatScheduler:
    return HeartbeatScheduler(meter=meter)


@pytest.fixture
def clear(ledger) -> GateSignals:
    """全部机械判据均已明确解析为 FALSE 的信号集。"""
    return GateSignals.all_clear(NOW, notification_epoch=7, budget=ledger)


def evidence_beat(sched, signals, *, now=NOW, dim="dim.health", tokens=750, ev=("obs-1",)):
    """一次"有实质证据"的心跳，应当一路放行。"""
    return sched.beat(
        now=now, signals=signals, evidence_refs=ev, dimension_id=dim, projected_tokens=tokens
    )


# ---------------------------------------------------------------------------
# A · 政策绑定：引用而非复制，注入路径不得享受弱校验
# ---------------------------------------------------------------------------


class TestPolicyBinding:
    def test_policy_file_is_the_single_authority(self):
        assert cq._POLICY_PATH.exists()
        assert cq._POLICY_PATH.name == "runtime_policy.json"
        assert cq._POLICY_PATH.parent.name == "governance"

    def test_factory_interval_is_read_from_policy_not_hardcoded(self, sched):
        factory = HB["interval_hours_factory_default"]
        assert sched.factory_min == float(factory["min"])
        assert sched.factory_max == float(factory["max"])
        # 默认取中值，且这个中值是**算出来的**，不是写死的 4
        assert sched.interval_hours == pytest.approx((factory["min"] + factory["max"]) / 2.0)

    def test_no_heartbeat_budget_constant_is_copied_into_the_module(self):
        # 36000 / 2554000 是法定预算数字；一旦出现在源码里就是复制，必然与政策漂移
        for number in ("36000", "2554000", "85134"):
            assert number not in MODULE_SOURCE, f"源码里硬编码了法定预算数字 {number}"

    def test_interval_is_a_factory_default_not_a_law(self, sched):
        assert HB["interval_hours_is_factory_default_not_law"] is True
        assert HB["interval_is_learnable_secondary_governance_parameter"] is True
        # 学到 6.5 小时（超出 3~5 出厂默认）必须被允许 —— 它不是铁律
        entry = sched.learn_interval(
            6.5,
            learner_hash="lrn-abc123",
            rationale="连续 14 日 ignored 反馈，节律过密",
            input_window="2026-09-01/2026-09-14",
            now=NOW,
        )
        assert sched.interval_hours == 6.5
        assert entry.prev_value == pytest.approx(4.0)
        assert entry.reversible is True

    def test_learn_interval_lands_all_eight_legal_change_log_fields(self, sched):
        entry = sched.learn_interval(
            5.5, learner_hash="h", rationale="r", input_window="w", now=NOW
        )
        payload = entry.to_audit()
        assert set(payload) == set(TG["change_log_fields"])
        entry.validate_against_policy(TG)

    def test_change_log_schema_drift_is_refused(self, sched):
        drifted = dict(TG)
        drifted["change_log_fields"] = ["param_id", "prev_value"]  # 少了六个字段
        entry = ThresholdChangeEntry(
            param_id="heartbeat.interval_hours",
            prev_value=4.0,
            next_value=5.0,
            input_window="w",
            learner_hash="h",
            rationale="r",
            applied_at=NOW,
            reversible=True,
        )
        with pytest.raises(WakeError, match="漂移"):
            entry.validate_against_policy(drifted)

    def test_empty_learner_hash_is_refused(self, sched):
        # 没有 learner_hash 就无法追溯是哪一版学习器做的决定，回放/回滚都失效
        with pytest.raises(WakeError, match="learner_hash"):
            sched.learn_interval(5.0, learner_hash="", rationale="r", input_window="w", now=NOW)

    def test_rollback_restores_the_previous_interval(self, sched):
        before = sched.interval_hours
        sched.learn_interval(6.0, learner_hash="h", rationale="r", input_window="w", now=NOW)
        assert sched.interval_hours == 6.0
        reverted = sched.rollback_interval()
        assert sched.interval_hours == before
        assert reverted is not None and reverted.next_value == 6.0

    def test_rollback_without_history_is_a_noop(self, sched):
        assert sched.rollback_interval() is None

    def test_non_positive_interval_is_refused(self, sched):
        with pytest.raises(WakeError):
            sched.learn_interval(0, learner_hash="h", rationale="r", input_window="w", now=NOW)

    @pytest.mark.parametrize(
        "key",
        [
            "is_seventh_trigger_kind",
            "interval_hours_is_factory_default_not_law",
            "candidate_wake_not_promise_to_speak",
            "step0_convenience_check_has_final_veto",
            "candidate_wake_downgrades_to_silent_patrol_on_QUIET",
            "mechanical_gate_before_llm",
            "night_work_driving_sleep_windows_default_to_silent",
            "safety_trigger_never_suppressed_by_gate_or_cooldown",
            "feedback_cooldown_is_hard_constraint",
            "cancelled_heartbeat_must_still_log_silent_patrol",
        ],
    )
    def test_injected_heartbeat_section_with_a_flipped_law_is_refused(self, key):
        """注入路径必须享受**与文件路径完全相同**的校验。

        这是 M2-005R 初版栽过的真 bug：校验只写在读文件的函数里，
        ``policy=...`` 注入即绕过。此测试就是那条 bug 的回归门。
        """
        drifted = dict(HB)
        drifted[key] = False
        with pytest.raises(WakeError, match="法定值"):
            load_heartbeat_policy({"heartbeat": drifted})
        with pytest.raises(WakeError, match="法定值"):
            HeartbeatScheduler(heartbeat_policy=drifted)

    @pytest.mark.parametrize(
        "key",
        ["trigger_kind_name", "gate_predicates", "gate_cancel_target_share"],
    )
    def test_injected_heartbeat_section_missing_a_field_is_refused(self, key):
        drifted = {k: v for k, v in HB.items() if k != key}
        with pytest.raises(WakeError, match="缺少法定字段"):
            HeartbeatScheduler(heartbeat_policy=drifted)

    def test_injected_root_policy_gets_the_same_validation(self):
        drifted_root = dict(ROOT)
        hb = dict(HB)
        hb["mechanical_gate_before_llm"] = False
        drifted_root["heartbeat"] = hb
        with pytest.raises(WakeError, match="法定值"):
            HeartbeatScheduler(policy=drifted_root)

    def test_step0_model_calls_must_be_zero_in_the_policy_itself(self):
        assert S0["model_calls"] == 0
        drifted = dict(S0)
        drifted["model_calls"] = 1
        with pytest.raises(WakeError, match="纯机械闸"):
            load_step0_policy({"step0_safety_gate": drifted})

    @pytest.mark.parametrize(
        "key",
        [
            "runs_before_any_mental_step",
            "deterministic_rules_only",
            "hard_block_prohibits_external_delivery",
            "verdicts_materialized_into_session_audit",
            "hidden_chain_of_thought_substitute_prohibited",
        ],
    )
    def test_injected_step0_section_with_a_flipped_law_is_refused(self, key):
        drifted = dict(S0)
        drifted[key] = False
        with pytest.raises(WakeError, match="法定值"):
            Step0SafetyGate(step0_policy=drifted)

    def test_verdict_list_must_match_the_legal_names_not_the_values(self):
        """政策用的是 ``SafetyVerdict`` 的 **name**（大写），不是 value（小写）。

        这是个真实陷阱：``SafetyVerdict.OK.value == "ok"`` 而政策写 ``"OK"``。
        拿 value 去比会把"自己比错字段"误报成"政策漂移"。
        """
        assert set(S0["verdicts"]) == {v.name for v in SafetyVerdict}
        assert set(S0["verdicts"]) != {v.value for v in SafetyVerdict}
        drifted = dict(S0)
        drifted["verdicts"] = ["ok", "quiet", "hard_block"]  # 用了 value
        with pytest.raises(WakeError, match="名称"):
            load_step0_policy({"step0_safety_gate": drifted})

    def test_empty_check_lists_are_refused(self):
        drifted = dict(S0)
        checks = dict(S0["checks"])
        checks["a_safety_hard_signal"] = []
        drifted["checks"] = checks
        with pytest.raises(WakeError, match="非空列表"):
            load_step0_policy({"step0_safety_gate": drifted})

    @pytest.mark.parametrize("invented", [
        "SOMETHING_THE_POLICY_NEVER_SAID",
        "LONG_STABLE_HEART",          # 差一个后缀也不认：近似名最容易蒙混过关
        "RELATION_RHYTHM",           # 法定**枚举成员名**同样不是政策名，不得混用
        "",
    ])
    def test_unknown_trigger_kind_name_is_refused(self, invented):
        """拒绝自拟第七种触发器名 —— 编号漂移的真实成因就是各写各的名字。

        判据换过一次，原因记在这里：本测试原先拿 ``LONG_STABLE_HEARTBEAT`` 当"必须拒绝的
        作废旧名"（依本线 ADJ-002/ADJ-003 的改名裁决）。主干压平谱系从未收到该裁决，
        仍以它为现行法定名并由其政策测试钉死；政策 v1.4.0 并集取了主干值，于是这个名字
        **变成了合法输入**。若照旧断言它被拒，测试就会去锁一个治理尚未裁决的立场。
        现在改用一个任何谱系都没主张过的名字，并把守卫的真正判据（未登记即拒）测准。
        """
        drifted = dict(HB)
        drifted["trigger_kind_name"] = invented
        with pytest.raises(WakeError, match="编号漂移"):
            HeartbeatScheduler(heartbeat_policy=drifted)

    def test_trigger_kind_maps_to_an_existing_enum_member(self, sched):
        assert HB["is_seventh_trigger_kind"] is True
        assert TRIGGER_KIND_LEGAL_NAME[HB["trigger_kind_name"]] is WakeSourceV3.RELATION_RHYTHM
        assert sched.trigger_kind is WakeSourceV3.RELATION_RHYTHM

    def test_no_parallel_trigger_enum_was_invented(self):
        """政策名 ``RELATIONSHIP_RHYTHM_CANDIDATE`` 不得变成第二个枚举成员。

        本仓库出现过 ``ObjectType`` / ``ObjectTypeV3`` 双枚举导致 v3 扩展类型完全
        无法落盘的真实缺陷。法定载体是既有的 ``WakeSourceV3.RELATION_RHYTHM``，
        映射只写在 :data:`TRIGGER_KIND_LEGAL_NAME` 一处。
        """
        legal_name = HB["trigger_kind_name"]
        assert legal_name not in {m.value for m in WakeSourceV3}
        assert legal_name not in {m.value for m in WakeSource}
        assert legal_name not in {m.name for m in WakeSourceV3}
        # 两种拼写来自两条政策谱系（详见模块常量注释与政策 $name_collision_note）。
        # 条数不是重点，重点是**它们必须指向同一个法定载体**：只要映射恒等，
        # 别名就不可能悄悄变成第七种触发器；一旦有人给某个拼写指向别的成员，本断言即红。
        assert len(TRIGGER_KIND_LEGAL_NAME) == 2
        assert len(set(TRIGGER_KIND_LEGAL_NAME.values())) == 1, (
            "两种拼写映射到了不同法定成员 —— 那等于凭空多出一个触发器种类"
        )
        assert set(TRIGGER_KIND_LEGAL_NAME.values()) == {WakeSourceV3.RELATION_RHYTHM}
        for spelling in TRIGGER_KIND_LEGAL_NAME:
            assert spelling not in {m.value for m in WakeSourceV3}
            assert spelling not in {m.name for m in WakeSourceV3}
            assert spelling not in {m.value for m in WakeSource}

    def test_both_policy_spellings_map_to_the_same_legal_member(self):
        """**别名恒等**：政策名换拼写不得改变运行时行为。

        两条谱系对"哪个名是旧名"判定相反，治理尚未裁决。本测试把裁决悬置期间唯一能保证的
        事情钉死：无论政策写哪一个，``sched.trigger_kind`` 都是同一个法定成员。
        这样治理将来选定任一拼写，都不需要改本模块一行代码。
        """
        kinds = set()
        for spelling in ("LONG_STABLE_HEARTBEAT", "RELATIONSHIP_RHYTHM_CANDIDATE"):
            policy = dict(HB)
            policy["trigger_kind_name"] = spelling
            kinds.add(HeartbeatScheduler(heartbeat_policy=policy).trigger_kind)
        assert kinds == {WakeSourceV3.RELATION_RHYTHM}, f"两种拼写产生了不同行为：{kinds}"

    def test_absolute_floor_constant_matches_policy(self):
        assert ABSOLUTE_FLOOR_CHANNELS == frozenset(
            HB["absolute_floor_not_subject_to_rhythm_learning"]
        )

    def test_absolute_floor_constant_drift_is_refused(self):
        drifted = dict(HB)
        drifted["absolute_floor_not_subject_to_rhythm_learning"] = [
            "personal_safety_watch_channel"
        ]  # 少了一条
        with pytest.raises(WakeError, match="漂移"):
            HeartbeatScheduler(heartbeat_policy=drifted)


# ---------------------------------------------------------------------------
# B · 门禁 1：心跳触发 100% 带候选触发器
# ---------------------------------------------------------------------------


NON_SAFETY_PRIORITIES = [p for p in WakePriority if p is not WakePriority.P0_CRITICAL_SAFETY]
NON_SAFETY_SOURCES = [WakeSourceV3.RELATION_RHYTHM, WakeSource.MECHANICAL_CHANGE, WakeSource.TASK_DUE]


class TestGate1EveryHeartbeatCarriesACandidateTrigger:
    @pytest.mark.parametrize("priority", NON_SAFETY_PRIORITIES)
    @pytest.mark.parametrize("source", NON_SAFETY_SOURCES)
    def test_wake_without_a_trigger_is_refused_at_construction(self, priority, source):
        """**穷举**证明 100%，而不是只测一个例子。"""
        with pytest.raises(MissingCandidateTriggerError, match="100%"):
            CandidateWake(
                wake_id="hb-x", source=source, created_at=NOW, trigger=None, priority=priority
            )

    def test_safety_wake_may_exist_without_a_heartbeat_trigger(self):
        """生命安全唤醒不是心跳，不该被要求出示"关系节奏候选触发器"。"""
        wake = CandidateWake(
            wake_id="sos-1",
            source=WakeSource.SAFETY,
            created_at=NOW,
            trigger=None,
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=SafetyBypassPayload(hazard_type=HazardType.FALL_DETECTED),
        )
        assert wake.is_safety_trigger is True

    def test_gate_boundary_refuses_a_triggerless_wake(self):
        """第二道拒绝点：闸门内的 ``require_trigger``。"""
        wake = CandidateWake(
            wake_id="sos-2", source=WakeSource.SAFETY, created_at=NOW, trigger=None
        )
        with pytest.raises(MissingCandidateTriggerError, match="拒绝投递"):
            wake.require_trigger()

    def test_delivery_boundary_refuses_a_beat_that_produced_no_wake(self, sched, clear):
        """第三道拒绝点：``deliver``。无证据的心跳根本不产出唤醒，无可投递。"""
        outcome = sched.beat(now=NOW, signals=clear)
        assert outcome.wake is None
        with pytest.raises(MissingCandidateTriggerError, match="无可投递"):
            sched.deliver(outcome, FakeContext())

    def test_beat_without_evidence_never_constructs_a_wake(self, sched, clear):
        outcome = sched.beat(now=NOW, signals=clear)
        assert outcome.wake is None
        assert outcome.decision is None
        assert outcome.deliverable is False
        assert outcome.patrol is not None
        assert outcome.patrol.reason == "no_candidate_evidence_rhythm_bomb_not_emitted"

    def test_beat_with_evidence_constructs_a_triggered_wake(self, sched, clear):
        outcome = evidence_beat(sched, clear)
        assert outcome.wake is not None
        assert outcome.wake.trigger is not None
        assert outcome.wake.trigger.kind is WakeSourceV3.RELATION_RHYTHM
        assert outcome.wake.trigger.evidence_refs == ("obs-1",)
        assert outcome.wake.source is WakeSourceV3.RELATION_RHYTHM

    def test_trigger_without_an_id_is_refused(self):
        with pytest.raises(WakeError, match="trigger_id"):
            CandidateTrigger(trigger_id="", detected_at=NOW)

    def test_unknown_floor_channel_is_refused(self):
        with pytest.raises(WakeError, match="未知的绝对底线通道"):
            CandidateTrigger(
                trigger_id="t", detected_at=NOW, floor_channel="make_up_a_channel"
            )

    def test_p0_wake_without_a_hazard_payload_is_refused_at_construction(self):
        """既有 dispatcher 的 P0 分支会读 ``safety_bypass.hazard_type`` 去构造必填的
        ``SafetyBypassReceipt``。留空不会在构造期报错，而是**推迟到投递那一刻**才炸 ——
        那时它已经穿过闸门与队列，是最难定位的位置。所以这里提前拦。
        """
        with pytest.raises(WakeError, match="safety_bypass"):
            CandidateWake(
                wake_id="sos-3",
                source=WakeSource.SAFETY,
                created_at=NOW,
                trigger=None,
                priority=WakePriority.P0_CRITICAL_SAFETY,
            )


# ---------------------------------------------------------------------------
# C · 红线 25：候选唤醒绝不承诺出声
# ---------------------------------------------------------------------------


class TestRedline25NeverPromiseToSpeak:
    def test_policy_anchor(self):
        assert HB["candidate_wake_not_promise_to_speak"] is True

    def test_promise_to_speak_is_refused_at_runtime(self):
        with pytest.raises(PromiseToSpeakError, match="红线 25"):
            CandidateWake(
                wake_id="hb-p",
                source=WakeSourceV3.RELATION_RHYTHM,
                created_at=NOW,
                trigger=CandidateTrigger("t", NOW, evidence_refs=("obs-1",)),
                promises_delivery=True,  # type: ignore[arg-type]
            )

    def test_promise_field_is_typed_literal_false_for_static_checkers(self):
        """运行层之外还有一层：``Literal[False]`` 让类型检查器在调用点就拒绝 ``True``。

        dataclass **不校验注解**，所以只靠 Literal 等于只挡静态检查；两层都得有。
        """
        hints = typing.get_type_hints(CandidateWake)
        assert hints["promises_delivery"] is typing.Literal[False]

    def test_delivering_a_quiet_candidate_raises_the_promise_error(self, sched, ledger):
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {"deep_sleep": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision is not None
        assert outcome.decision.verdict.verdict is SafetyVerdict.QUIET
        assert outcome.deliverable is False
        with pytest.raises(PromiseToSpeakError, match="不得出声"):
            sched.deliver(outcome, FakeContext())

    def test_delivering_a_hard_blocked_candidate_raises_the_promise_error(self, sched, ledger):
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS} | {"fall": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        with pytest.raises(PromiseToSpeakError):
            sched.deliver(outcome, FakeContext())

    def test_a_delivered_wake_still_does_not_promise(self, sched, clear):
        outcome = evidence_beat(sched, clear)
        receipt = sched.deliver(outcome, FakeContext())
        assert outcome.wake.promises_delivery is False
        assert receipt["status"] == "COCKPIT_ASSEMBLED"


# ---------------------------------------------------------------------------
# D · 门禁 2：Step-0 在任何模型调用之前，model_calls 恒为 0
# ---------------------------------------------------------------------------


class TestGate2Step0IsMechanicalAndPrecedesEveryModelCall:
    def test_policy_anchor(self):
        assert S0["runs_before_any_mental_step"] is True
        assert S0["deterministic_rules_only"] is True
        assert S0["model_calls"] == 0
        assert HB["mechanical_gate_before_llm"] is True

    def test_the_gate_has_no_model_adapter_parameter_at_all(self):
        """**结构上**无法叫模型，而不只是"当前实现恰好没叫"。

        两者的可回归性差一个数量级：前者靠类型守，后者靠人守。
        """
        params = set(inspect.signature(Step0SafetyGate.__init__).parameters)
        assert params == {"self", "step0_policy", "heartbeat_policy", "meter"}
        forbidden = {"model", "llm", "adapter", "client", "predictor", "completion", "generate"}
        assert not (params & forbidden)
        # evaluate 也只吃唤醒与机械信号
        eval_params = set(inspect.signature(Step0SafetyGate.evaluate).parameters)
        assert eval_params == {"self", "wake", "signals"}

    def test_module_contains_zero_model_charge_sites(self):
        """与 M2-005R 的"唯一 charge 点"纪律互为镜像：那边恰好一个，这边恰好零个。

        用 **AST** 而不是源码 grep：docstring 里*提到* ``meter.charge(`` 是正当的
        （说明纪律来源），字符串匹配会把它误判成调用点 —— M2-005R 已经在
        ``_TASK_TRANSITIONS`` 上踩过同一个坑，这次直接换成语法树。
        """
        import ast

        def charge_sites(path):
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            return [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "charge"
            ]

        assert charge_sites(cq.__file__) == [], "Step-0 必须零模型调用"

        # 反向自检：判据本身必须被证明有效，否则"数出 0"可能只是判据失效。
        #
        # 这里换过一次校准靶子，代价记在案：原先的靶子是 M2-005R 的 conditional_engine
        # （恰好一个 charge 点）。主干在压平提交里换掉那份实现后靶子消失，本测试随之变红 ——
        # 那不是被测模块出问题，是**拿别人的文件当自己判据的标尺**这个选择出了问题：
        # 别人一改，我就红，而且红得像是我的门禁失效。改用受控合成样本后，
        # 判据有效性只取决于本测试自己。
        probe = (
            '"""docstring 里正当提及 meter.charge( 不该被数成调用点。"""\n'
            "def f(meter):\n"
            "    meter.charge(lane='a', tokens=1, reason='r')\n"
            "    return meter.snapshot()\n"
        )
        # 字符串匹配会数出 2（1 个真调用点 + 1 处 docstring 提及）—— 这正是当年改用 AST 的原因
        assert probe.count("meter.charge(") == 2, "合成样本失效：应为 1 真调用点 + 1 处 docstring 提及"
        probe_sites = [
            node for node in ast.walk(ast.parse(probe))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "charge"
        ]
        assert len(probe_sites) == 1, "判据失效：合成样本里明明有一个 charge 调用点"

    def test_thirty_virtual_days_consume_zero_model_calls(self, sched, meter, ledger):
        """政策 ``degradation_invariants.measurement = compressed_30_virtual_days``。"""
        interval = timedelta(hours=sched.interval_hours)
        moment = NOW
        for _ in range(int(24 * 30 / sched.interval_hours)):
            signals = GateSignals.all_clear(
                moment, notification_epoch=1, budget=ledger
            )
            sched.beat(now=moment, signals=signals)
            moment += interval
        assert meter.model_calls == 0
        assert meter.tokens == 0
        assert sched.audit()["model_calls"] == 0

    def test_step0_runs_before_the_queue_and_before_delivery(self, sched, ledger):
        """HARD_BLOCK 时队列压根不该被触碰 —— 顺序即法律。"""
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS} | {"impact": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        before = sched.queue.pending_count()
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert outcome.queue is None, "HARD_BLOCK 之后不得再进入队列"
        assert sched.queue.pending_count() == before

    @pytest.mark.parametrize(
        "flag_name",
        CONVENIENCE + HARD_SIGNALS,
    )
    def test_every_decision_materializes_its_rules(self, sched, ledger, flag_name):
        """``hidden_chain_of_thought_substitute_prohibited``：判定必须落成结构化记录。"""
        verdict_kind = (
            SafetyVerdict.HARD_BLOCK if flag_name in HARD_SIGNALS else SafetyVerdict.QUIET
        )
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {flag_name: TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is verdict_kind
        assert outcome.decision.rules_fired, "空 rules_fired 等于隐藏思维链"
        assert any(flag_name in rule for rule in outcome.decision.rules_fired)

    def test_audit_record_is_json_serializable(self, sched, clear):
        outcome = evidence_beat(sched, clear)
        record = outcome.decision.audit_record()
        text = json.dumps(record, ensure_ascii=False)  # 不可序列化就直接炸
        assert json.loads(text)["model_calls"] == 0
        assert record["wake_id"] == outcome.wake.wake_id
        assert record["convenience"] == "OK"
        assert record["delivery_permitted"] is True

    def test_gate_verdict_is_the_legal_materialized_carrier(self, sched, clear):
        """复用 ``models_v3.SafetyGateVerdict``，不自造结论结构。"""
        outcome = evidence_beat(sched, clear)
        assert isinstance(outcome.decision.verdict, SafetyGateVerdict)
        assert outcome.decision.verdict.hard_safe_ok is True

    def test_the_carrier_is_exactly_what_the_manifest_demands(self):
        """``ManifestInstance.step0_safety`` 是**必填**字段 —— 没有 Step-0 结论，
        看板根本无法装配。这条断言把"闸门结论不会丢"钉在法定契约上。
        """
        field = ManifestInstance.model_fields["step0_safety"]
        assert field.annotation is SafetyGateVerdict
        assert field.is_required()

    def test_hard_block_prohibits_external_delivery(self, sched, ledger):
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {"current_interrupting_input": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert S0["hard_block_prohibits_external_delivery"] is True
        assert outcome.decision.delivery_permitted is False
        assert outcome.deliverable is False

    def test_hard_block_still_allows_patrol_and_safety_watch(self, sched, ledger):
        """政策 ``$precedence_note``：这是优先级裁定，不是例外清单。
        §80之3「后台静默巡检绝对不停转」优先于 HARD_BLOCK。
        """
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS} | {"fall": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.allows == frozenset(S0["hard_block_still_allows"])
        assert outcome.patrol is not None, "HARD_BLOCK 之下巡检仍须留痕"
        assert set(outcome.patrol.still_allows) == set(S0["hard_block_still_allows"])

    def test_ok_decisions_allow_nothing_extra(self, sched, clear):
        outcome = evidence_beat(sched, clear)
        assert outcome.decision.allows == frozenset()


# ---------------------------------------------------------------------------
# E · 门禁 3：便利闸门最终否决权 + QUIET 降级为静默巡检 + 留痕
# ---------------------------------------------------------------------------


class TestGate3ConvenienceHasTheFinalVeto:
    def test_policy_anchors(self):
        assert HB["step0_convenience_check_has_final_veto"] is True
        assert HB["candidate_wake_downgrades_to_silent_patrol_on_QUIET"] is True
        assert HB["cancelled_heartbeat_must_still_log_silent_patrol"] is True
        assert HB["night_work_driving_sleep_windows_default_to_silent"] is True

    @pytest.mark.parametrize("flag_name", CONVENIENCE)
    def test_every_legal_convenience_predicate_vetoes(self, sched, ledger, flag_name):
        """遍历政策里**全部**便利判据（Step-0 b 段 + 心跳 gate_predicates）。"""
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {flag_name: TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.QUIET
        assert outcome.decision.convenience == "QUIET"
        assert outcome.decision.delivery_permitted is False
        assert outcome.deliverable is False
        assert outcome.patrol is not None

    @pytest.mark.parametrize("flag_name", ["driving", "sleep", "deep_sleep"])
    def test_night_work_driving_sleep_default_to_silent(self, sched, ledger, flag_name):
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {flag_name: TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.deliverable is False
        assert f"convenience_silence:{flag_name}" in outcome.decision.verdict.overrides

    def test_unresolved_convenience_fails_toward_silence(self, sched, ledger):
        """**留空 flags 不是"一切方便"，而是"我没问" ⇒ 必须 QUIET。**

        失败方向永远朝着沉默，绝不朝着打扰 —— 这条方向性是整个闸门的立足点。
        """
        signals = GateSignals(now=NOW, flags={}, notification_epoch=7, budget=ledger)
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.QUIET
        assert outcome.deliverable is False

    def test_unresolved_signals_are_named_in_the_audit(self, sched, ledger):
        """未决信号必须逐字落名，否则"判不了"会伪装成"判过了"（静默失效非法）。"""
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS if n != "meeting"},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert "unresolved_convenience_signal:meeting" in outcome.decision.verdict.overrides
        assert any("b_convenience_unresolved:meeting" in r for r in outcome.decision.rules_fired)

    def test_a_hard_signal_outranks_a_convenience_signal(self, sched, ledger):
        """HARD_BLOCK 压倒 QUIET，因为前者禁止对外投递而后者只是不出声。"""
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {"driving": TriState.TRUE, "fall": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK

    def test_missing_notification_epoch_cuts_the_playback_channel(self, sched, ledger):
        """``delivery_fsm.zero_mistrigger_legal_criterion.false_playback_without_epoch = 0``
        的唯一实现点，也是其不变量 I1 的闸门侧对应物。
        """
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS},
            notification_epoch=None,
            budget=ledger,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert "false_playback_without_epoch_prevented" in outcome.decision.verdict.overrides
        assert outcome.deliverable is False

    def test_missing_budget_ledger_fails_closed(self, sched):
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS},
            notification_epoch=7,
            budget=None,
        )
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert "budget_ledger_absent_fail_closed" in outcome.decision.verdict.overrides

    def test_patrol_log_invariant_records_equal_silent_beats(self, sched, ledger):
        """不变量：**巡检留痕数 == 心跳数 - 出声数**。

        只有这条等式成立，"被闸门取消"与"根本没运行"才在审计上可区分；
        否则后台巡检停转会以"很安静"的形式伪装成合规。
        """
        interval = timedelta(hours=sched.interval_hours)
        moment = NOW
        quiet_flags = {n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS} | {
            "meeting": TriState.TRUE
        }
        for i in range(12):
            signals = GateSignals(
                now=moment,
                flags=quiet_flags if i % 3 else {
                    n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS
                },
                notification_epoch=3,
                budget=ledger,
            )
            outcome = sched.beat(
                now=moment,
                signals=signals,
                evidence_refs=("obs-%d" % i,),
                dimension_id="dim.health",
                projected_tokens=750,
            )
            if outcome.deliverable:
                sched.deliver(outcome, FakeContext())
            moment += interval
        audit = sched.audit()
        assert audit["counts"]["beats"] == 12
        assert audit["patrol_records"] == 12 - audit["counts"]["delivered"]
        assert audit["counts"]["quiet"] == 8
        assert audit["counts"]["delivered"] == 4

    def test_policy_added_convenience_predicate_takes_effect_without_code_change(self, ledger):
        """"引用而非复制"的实际收益：政策新增一条判据，闸门自动生效，代码不用改。"""
        drifted = dict(HB)
        drifted["gate_predicates"] = list(HB["gate_predicates"]) + ["commuting"]
        gate = Step0SafetyGate(heartbeat_policy=drifted)
        assert "commuting" in gate._gate_predicates
        wake = CandidateWake(
            wake_id="hb-new",
            source=WakeSourceV3.RELATION_RHYTHM,
            created_at=NOW,
            trigger=CandidateTrigger("t", NOW, evidence_refs=("obs-1",)),
            projected_tokens=750,
        )
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {"commuting": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        assert gate.evaluate(wake, signals).verdict.verdict is SafetyVerdict.QUIET


# ---------------------------------------------------------------------------
# F · 预算闸门（Step-0 §1(d)）
# ---------------------------------------------------------------------------


class TestBudgetGate:
    def test_heartbeat_subsystem_cap_blocks(self, sched):
        ledger = BudgetLedger(
            heartbeat_cap=TB["subsystems"]["heartbeat"]["monthly_cap"],
            monthly_cap=TB["monthly_total_cap"],
            heartbeat_spent=TB["subsystems"]["heartbeat"]["monthly_cap"],  # 已用满
        )
        signals = GateSignals.all_clear(NOW, notification_epoch=7, budget=ledger)
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert (
            "budget_gate:heartbeat_subsystem_cap_exceeded"
            in outcome.decision.verdict.overrides
        )
        assert any(r.startswith("d_budget_gate:") for r in outcome.decision.rules_fired)

    def test_monthly_total_cap_blocks(self, sched):
        ledger = BudgetLedger(
            heartbeat_cap=TB["subsystems"]["heartbeat"]["monthly_cap"],
            monthly_cap=TB["monthly_total_cap"],
            monthly_spent=TB["monthly_total_cap"],
        )
        signals = GateSignals.all_clear(NOW, notification_epoch=7, budget=ledger)
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert (
            "budget_gate:monthly_total_cap_exceeded" in outcome.decision.verdict.overrides
        )

    def test_unavailable_projection_blocks_rather_than_assuming_zero(self, sched):
        """无法估算花费 ⇒ "无法证明可负担" ⇒ 保守 HARD_BLOCK。

        把 None 当成 0 是最典型的静默超支成因。
        """
        ledger = BudgetLedger(heartbeat_cap=36000, monthly_cap=2554000)
        signals = GateSignals.all_clear(NOW, notification_epoch=7, budget=ledger)
        outcome = sched.beat(
            now=NOW, signals=signals, evidence_refs=("obs-1",), projected_tokens=None
        )
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert (
            "budget_gate:projected_tokens_unavailable_cannot_prove_affordable"
            in outcome.decision.verdict.overrides
        )

    def test_negative_projection_is_refused(self):
        with pytest.raises(WakeError, match="不得为负"):
            CandidateWake(
                wake_id="hb-neg",
                source=WakeSourceV3.RELATION_RHYTHM,
                created_at=NOW,
                trigger=CandidateTrigger("t", NOW, evidence_refs=("o",)),
                projected_tokens=-1,
            )

    def test_budget_error_uses_the_legal_error_code(self):
        err = BudgetExhaustedError("超额")
        assert err.code is ErrorCode.BUDGET_EXHAUSTED
        assert isinstance(err, WakeError)

    def test_heartbeat_budget_arithmetic_closes_on_the_cancel_share(self):
        """政策把心跳月度预算建立在"80% 的心跳被 Step-0 机械闸门取消"之上。

        240 次/月 × (1 - 0.8) × 750 tok = 36000，与 ``token_budget.subsystems.
        heartbeat.monthly_cap`` 精确相等。240 与 750 出自政策 ``basis`` 的散文说明，
        ``gate_cancel_target_share`` 与 ``monthly_cap`` 是结构化字段 —— 所以这条算术
        放在测试里（散文不该进生产代码解析），但它证明取消率是**预算闭合的承重参数**，
        不是观感指标。
        """
        share = HB["gate_cancel_target_share"]
        cap = TB["subsystems"]["heartbeat"]["monthly_cap"]
        assert share == 0.8
        assert round(240 * (1 - share) * 750) == cap == 36000
        # 浮点陷阱（真实发现）：1 - 0.8 == 0.19999999999999996，于是
        # int(240 * (1-0.8) * 750) == 35999，凭空少 1 token。政策 $closure_note 记载
        # v1.0.0 曾把合计凑成 2,550,000 而被判决门抓住 4,000 token 漂移 —— 同一类错误。
        # 预算算术不得让 float 截断决定合规与否。
        assert int(240 * (1 - share) * 750) == 35999 != cap
        assert 240 * (100 - int(share * 100)) * 750 // 100 == cap, "整数算术必须精确闭合"

    def test_a_lower_cancel_share_would_break_the_budget(self):
        """反向验证承重性：取消率一旦低于目标，同一批心跳就会冲破法定上限。"""
        cap = TB["subsystems"]["heartbeat"]["monthly_cap"]
        for share in (0.79, 0.6, 0.0):
            assert int(240 * (1 - share) * 750) > cap, f"取消率 {share} 竟未破预算"

    def test_cancel_share_is_reported_against_the_policy_target(self, sched, ledger):
        signals = GateSignals(
            now=NOW,
            flags={n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
            | {"deep_focus": TriState.TRUE},
            notification_epoch=7,
            budget=ledger,
        )
        for i in range(5):
            sched.beat(
                now=NOW + timedelta(hours=i),
                signals=signals,
                evidence_refs=("obs-%d" % i,),
                projected_tokens=750,
            )
        audit = sched.audit()
        assert audit["gate_cancel_share"] == 1.0
        assert audit["gate_cancel_target_share"] == HB["gate_cancel_target_share"]


# ---------------------------------------------------------------------------
# G · 门禁 4：7 天平稳数据节奏炸弹 = 0；安全触发与绝对底线永不被压制
# ---------------------------------------------------------------------------


class TestGate4RhythmBombsAndAbsoluteFloor:
    def test_policy_anchor(self):
        assert HB["fixed_rhythm_bomb_count_under_7d_stable_data"] == 0
        assert HB["safety_trigger_never_suppressed_by_gate_or_cooldown"] is True

    def test_seven_stable_virtual_days_produce_zero_rhythm_bombs(self, sched, meter, ledger):
        """正面跑满 7 个虚拟日：系统一切正常、没有内心数据流入 ⇒ 一声不出。

        这是政策给的**可判定反面指标**（``fixed_rhythm_bomb_count_under_7d_stable_
        data = 0``）：AI 不该为了维持节律而出声。
        """
        interval = timedelta(hours=sched.interval_hours)
        moment = NOW
        beats = int(7 * 24 / sched.interval_hours)
        assert beats == 42
        for _ in range(beats):
            signals = GateSignals.all_clear(moment, notification_epoch=1, budget=ledger)
            outcome = sched.beat(now=moment, signals=signals)  # 平稳数据 ⇒ 无证据
            assert outcome.deliverable is False
            moment += interval
        audit = sched.audit()
        assert audit["counts"]["rhythm_bombs_delivered"] == 0
        assert audit["counts"]["delivered"] == 0
        assert audit["counts"]["beats"] == 42
        assert audit["patrol_records"] == 42, "每一次没出声的心跳都必须留下巡检痕迹"
        assert meter.model_calls == 0

    def test_rhythm_bomb_is_a_property_of_the_trigger_not_of_the_scheduler(self):
        assert CandidateTrigger("t", NOW, evidence_refs=()).is_rhythm_bomb is True
        assert CandidateTrigger("t", NOW, evidence_refs=("obs-1",)).is_rhythm_bomb is False

    def test_a_forced_rhythm_bomb_is_vetoed_by_the_gate(self, sched, clear):
        """绕过调度器直接把无证据触发器送到闸门，仍须被 QUIET（防御纵深）。"""
        wake = CandidateWake(
            wake_id="hb-bomb",
            source=WakeSourceV3.RELATION_RHYTHM,
            created_at=NOW,
            trigger=CandidateTrigger("t", NOW, evidence_refs=()),
            projected_tokens=750,
        )
        decision = sched.gate.evaluate(wake, clear)
        assert decision.verdict.verdict is SafetyVerdict.QUIET
        assert "fixed_rhythm_bomb_suppressed" in decision.verdict.overrides
        assert decision.delivery_permitted is False

    def test_rhythm_bomb_counter_stays_zero_even_under_forced_attempts(
        self, sched, clear
    ):
        wake = CandidateWake(
            wake_id="hb-bomb2",
            source=WakeSourceV3.RELATION_RHYTHM,
            created_at=NOW,
            trigger=CandidateTrigger("t", NOW, evidence_refs=()),
            projected_tokens=750,
        )
        decision = sched.gate.evaluate(wake, clear)
        queued = sched.queue.enqueue(wake, now=NOW)
        outcome = BeatOutcome(1, NOW, wake, decision, queued, None)
        with pytest.raises(PromiseToSpeakError):
            sched.deliver(outcome, FakeContext())
        assert sched.audit()["counts"]["rhythm_bombs_delivered"] == 0

    def _worst_case_signals(self) -> GateSignals:
        """睡眠 + 勿扰 + 深度睡眠 + 无通知 epoch + 预算爆表，全部同时成立。"""
        return GateSignals(
            now=NOW,
            flags={
                "sleep": TriState.TRUE,
                "dnd_window": TriState.TRUE,
                "deep_sleep": TriState.TRUE,
                "driving": TriState.TRUE,
            },
            notification_epoch=None,
            budget=BudgetLedger(
                heartbeat_cap=TB["subsystems"]["heartbeat"]["monthly_cap"],
                monthly_cap=TB["monthly_total_cap"],
                heartbeat_spent=10**9,
                monthly_spent=10**9,
            ),
        )

    @pytest.mark.parametrize("channel", sorted(ABSOLUTE_FLOOR_CHANNELS))
    def test_absolute_floor_pierces_every_gate(self, sched, channel):
        """红线 31：安全便利优先于 token 预算 —— 安全触发连预算闸门一并穿透。"""
        outcome = sched.beat(
            now=NOW,
            signals=self._worst_case_signals(),
            floor_channel=channel,
            safety_bypass=SafetyBypassPayload(hazard_type=HazardType.FALL_DETECTED),
        )
        assert outcome.decision.verdict.verdict is SafetyVerdict.OK
        assert outcome.decision.delivery_permitted is True
        assert outcome.queue.state is WakeState.NEW
        assert "safety_trigger_never_suppressed_by_gate_or_cooldown" in (
            outcome.decision.verdict.overrides
        )
        assert "redline31_safety_over_token_budget" in outcome.decision.verdict.overrides

    def test_safety_trigger_routes_through_the_existing_hardware_bypass(self, sched):
        """复用既有 ``wake.dispatcher`` 的 P0 0 延迟硬件穿透，不另造第二条投递路径。

        两条投递路径意味着两套绕过闸门的可能。
        """
        outcome = sched.beat(
            now=NOW,
            signals=self._worst_case_signals(),
            floor_channel="personal_safety_watch_channel",
            safety_bypass=SafetyBypassPayload(
                hazard_type=HazardType.FALL_DETECTED, vital_snapshot={"g_force": 6.2}
            ),
        )
        receipt = sched.deliver(outcome, FakeContext())
        assert receipt["status"] == "SAFETY_BYPASS_EXECUTED"
        assert receipt["bypassed_llm"] is True
        assert receipt["receipt"]["hazard_type"] == HazardType.FALL_DETECTED.value
        assert receipt["receipt"]["bypassed_mind_sequence"] is True
        assert outcome.deliverable is True, "安全险情必须具备出声资格"

    def test_delivered_counter_counts_the_safety_delivery(self, sched):
        outcome = sched.beat(
            now=NOW,
            signals=self._worst_case_signals(),
            floor_channel="personal_safety_watch_channel",
            safety_bypass=SafetyBypassPayload(hazard_type=HazardType.MANUAL_SOS_HELD),
        )
        sched.deliver(outcome, FakeContext())
        assert sched.audit()["counts"]["delivered"] == 1
        assert sched.audit()["counts"]["safety_bypasses"] == 1

    def test_non_safety_wake_is_blocked_by_the_same_worst_case(self, sched, ledger):
        """对照组：同样的最坏信号下，普通心跳必须被拦住。

        没有这条对照，"安全穿透"测试可能只是因为闸门整体失效而通过。
        """
        outcome = evidence_beat(sched, self._worst_case_signals())
        assert outcome.decision.verdict.verdict is SafetyVerdict.HARD_BLOCK
        assert outcome.deliverable is False

    @pytest.mark.parametrize("channel", sorted(ABSOLUTE_FLOOR_CHANNELS))
    def test_absolute_floor_is_not_subject_to_cooldown(self, sched, clear, channel):
        """``absolute_floor_not_subject_to_rhythm_learning``：药物/复检与安全值守
        不因用户上次拒绝了**别的**话题就被一并静音。
        """
        first = evidence_beat(sched, clear, dim="dim.health")
        sched.deliver(first, FakeContext())
        sched.record_feedback(first, "suspended", now=NOW)  # 最长冷却
        later = NOW + timedelta(hours=1)
        signals = GateSignals.all_clear(later, notification_epoch=1, budget=clear.budget)
        outcome = sched.beat(
            now=later,
            signals=signals,
            floor_channel=channel,
            evidence_refs=("commitment-medication",),
            dimension_id="dim.health",
            projected_tokens=750,
        )
        assert outcome.queue.state is WakeState.NEW
        assert outcome.queue.reason == "absolute_floor_bypasses_cooldown_and_dedup"


# ---------------------------------------------------------------------------
# H · 冷却与去重合并队列
# ---------------------------------------------------------------------------


class TestCooldownQueue:
    def test_negative_feedback_cooldown_is_strictly_longer_than_positive(self):
        """政策只给了定性硬约束（``feedback_cooldown_is_hard_constraint``），没给秒数。
        所以真正被强制的是**与数值无关的序关系**：负反馈必须比正反馈更克制。
        """
        queue = CooldownQueue()
        assert queue._cooldowns["rejected"] > queue._cooldowns["accepted"]
        assert queue._cooldowns["suspended"] > queue._cooldowns["accepted"]
        assert queue._cooldowns["ignored"] >= queue._cooldowns["accepted"]

    @pytest.mark.parametrize("signal", ["rejected", "suspended"])
    def test_a_cooldown_table_violating_the_ordering_is_refused(self, signal):
        broken = dict(PROPOSED_FEEDBACK_COOLDOWNS)
        broken[signal] = 60  # 比 accepted 还短
        with pytest.raises(WakeError, match="硬约束|方向约束"):
            CooldownQueue(cooldowns=broken)

    def test_cooldown_durations_are_a_proposal_not_law(self):
        """秒数尚未入法，必须在源码里显式标注，避免被后人当成法定值引用。"""
        assert "PROPOSED_FEEDBACK_COOLDOWNS" in MODULE_SOURCE
        assert "尚未入法" in MODULE_SOURCE
        assert "提案" in MODULE_SOURCE
        assert HB["feedback_cooldown_is_hard_constraint"] is True
        # 政策全文没有任何冷却秒数 —— 所以这些数字确实是提案而非引用
        assert json.dumps(HB, ensure_ascii=False).count("cooldown_seconds") == 0

    def test_dedup_window_is_a_proposal_not_law(self):
        assert PROPOSED_DEDUP_WINDOW_SECONDS > 0
        assert "PROPOSED_DEDUP_WINDOW_SECONDS" in MODULE_SOURCE

    def test_all_four_legal_feedback_signals_have_a_cooldown(self):
        assert set(PROPOSED_FEEDBACK_COOLDOWNS) == set(
            HB["feedback_signals_for_frequency_adaptation"]
        )

    @pytest.mark.parametrize("signal", ["accepted", "ignored", "rejected", "suspended"])
    def test_every_legal_feedback_signal_is_accepted(self, sched, clear, signal):
        outcome = evidence_beat(sched, clear)
        sched.deliver(outcome, FakeContext())
        sched.record_feedback(outcome, signal, now=NOW)
        assert sched.queue._cooldown_until  # 冷却已生效

    @pytest.mark.parametrize("signal", ["", "liked", "ACCEPTED", "upvoted"])
    def test_illegal_feedback_signal_is_refused(self, sched, clear, signal):
        outcome = evidence_beat(sched, clear)
        with pytest.raises(WakeError, match="非法反馈信号"):
            sched.record_feedback(outcome, signal, now=NOW)

    def test_illegal_signal_in_the_cooldown_table_is_refused(self):
        broken = dict(PROPOSED_FEEDBACK_COOLDOWNS)
        broken["liked"] = 10
        with pytest.raises(WakeError, match="非法反馈信号"):
            CooldownQueue(cooldowns=broken)

    def test_missing_legal_signal_in_the_cooldown_table_is_refused(self):
        broken = {k: v for k, v in PROPOSED_FEEDBACK_COOLDOWNS.items() if k != "ignored"}
        with pytest.raises(WakeError, match="缺少法定反馈信号"):
            CooldownQueue(cooldowns=broken)

    def test_cooldown_survives_an_elapsed_rhythm(self, sched, ledger):
        """**节律到了也不能绕过冷却** —— 这正是"冷却是硬约束"的含义。"""
        first = evidence_beat(sched, GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger))
        sched.deliver(first, FakeContext())
        sched.record_feedback(first, "rejected", now=NOW)
        # 推进一个完整心跳间隔（4h）：节律到点，但冷却窗（提案 72h）仍在
        later = NOW + timedelta(hours=sched.interval_hours)
        outcome = sched.beat(
            now=later,
            signals=GateSignals.all_clear(later, notification_epoch=1, budget=ledger),
            evidence_refs=("obs-2",),
            dimension_id="dim.health",
            projected_tokens=750,
        )
        assert outcome.queue.state is WakeState.SUPPRESSED
        assert outcome.deliverable is False
        assert outcome.patrol.reason == "feedback_cooldown_hard_constraint"
        assert sched.audit()["counts"]["suppressed_by_cooldown"] == 1

    def test_suppressions_are_logged_not_silently_dropped(self, sched, ledger):
        first = evidence_beat(sched, GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger))
        sched.deliver(first, FakeContext())
        sched.record_feedback(first, "ignored", now=NOW)
        later = NOW + timedelta(hours=1)
        sched.beat(
            now=later,
            signals=GateSignals.all_clear(later, notification_epoch=1, budget=ledger),
            evidence_refs=("obs-2",),
            dimension_id="dim.health",
            projected_tokens=750,
        )
        log = sched.queue.suppression_log()
        assert len(log) == 1
        assert log[0]["reason"] == "feedback_cooldown"

    def test_same_source_within_the_window_is_merged(self, sched, ledger):
        signals = GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger)
        first = evidence_beat(sched, signals, dim="dim.health")
        # 第一件仍留在队列里（未 drain），第二件同源同维度 ⇒ 合并
        second = sched.beat(
            now=NOW + timedelta(minutes=1),
            signals=signals,
            evidence_refs=("obs-2",),
            dimension_id="dim.health",
            projected_tokens=750,
        )
        assert second.queue.state is WakeState.MERGED
        assert second.queue.merged_into == first.wake.wake_id
        assert sched.audit()["counts"]["merged"] == 1

    def test_a_different_dimension_is_not_merged(self, sched, ledger):
        signals = GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger)
        evidence_beat(sched, signals, dim="dim.health")
        other = sched.beat(
            now=NOW + timedelta(minutes=1),
            signals=signals,
            evidence_refs=("obs-2",),
            dimension_id="dim.work",
            projected_tokens=750,
        )
        assert other.queue.state is WakeState.NEW

    def test_outside_the_window_is_not_merged(self, sched, ledger):
        signals = GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger)
        evidence_beat(sched, signals, dim="dim.health")
        later = NOW + timedelta(seconds=PROPOSED_DEDUP_WINDOW_SECONDS + 1)
        outcome = sched.beat(
            now=later,
            signals=GateSignals.all_clear(later, notification_epoch=1, budget=ledger),
            evidence_refs=("obs-2",),
            dimension_id="dim.health",
            projected_tokens=750,
        )
        assert outcome.queue.state is WakeState.NEW

    def test_queue_states_are_the_legal_wake_states(self, sched, clear):
        outcome = evidence_beat(sched, clear)
        assert isinstance(outcome.queue.state, WakeState)
        assert outcome.queue.state is WakeState.NEW
        assert {d.state for d in (outcome.queue,)} <= set(WakeState)

    def test_non_positive_dedup_window_is_refused(self):
        with pytest.raises(WakeError, match="去重窗口"):
            CooldownQueue(dedup_window_seconds=0)

    def test_drain_is_fifo_and_empties_the_queue(self, sched, ledger):
        signals = GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger)
        for i, dim in enumerate(("dim.a", "dim.b", "dim.c")):
            sched.beat(
                now=NOW + timedelta(minutes=i),
                signals=signals,
                evidence_refs=(f"obs-{i}",),
                dimension_id=dim,
                projected_tokens=750,
            )
        assert sched.queue.pending_count() == 3
        drained = sched.queue.drain()
        assert [w.trigger.dimension_id for w in drained] == ["dim.a", "dim.b", "dim.c"]
        assert sched.queue.pending_count() == 0

    def test_delivering_a_merged_duplicate_is_refused(self, sched, ledger):
        """合并进来的重复件不得再投一次 —— 否则去重等于没做。"""
        signals = GateSignals.all_clear(NOW, notification_epoch=1, budget=ledger)
        evidence_beat(sched, signals, dim="dim.health")
        dup = sched.beat(
            now=NOW + timedelta(minutes=1),
            signals=signals,
            evidence_refs=("obs-2",),
            dimension_id="dim.health",
            projected_tokens=750,
        )
        assert dup.queue.state is WakeState.MERGED
        with pytest.raises(WakeError, match="非新件不得投递"):
            sched.deliver(dup, FakeContext())

    def test_delivering_without_a_step0_decision_is_refused(self, sched, clear):
        """未经 Step-0 的唤醒不得投递（顺序即法律）。"""
        outcome = evidence_beat(sched, clear)
        bypassed = BeatOutcome(outcome.beat_index, NOW, outcome.wake, None, outcome.queue, None)
        with pytest.raises(WakeError, match="未经 Step-0"):
            sched.deliver(bypassed, FakeContext())


# ---------------------------------------------------------------------------
# I · 复用既有法定构件，不重复实现
# ---------------------------------------------------------------------------


class TestReuseNotReimplementation:
    def test_the_meter_is_owned_locally_since_mainline_dropped_it(self):
        """计量器归属：本模块自持，不再依赖 ``scheduler.conditional_engine``。

        原先这里是 ``assert cq.ModelCallMeter is ce.ModelCallMeter``（复用 M2-005R 的计量器，
        不新造）。主干在 M5 之前的压平提交里换上了另一套 ``conditional_engine``，其中不再有
        ``ModelCallMeter``，本模块因此 import 即崩 —— 门禁 2 的**证据出口随别人的文件改名而
        消失**。收回自持后，本测试改钉三件事：本模块自己定义该类；不再从那个争议文件导入
        任何东西（AST 判据）；``charge()`` 仍是唯一记账出口且拒绝负数。
        """
        tree = ast.parse(Path(cq.__file__).read_text(encoding="utf-8"))
        defined = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
        assert "ModelCallMeter" in defined, "计量器必须在本模块内定义"
        rebound = [
            n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("conditional_engine")
        ]
        assert rebound == [], f"又绑回争议文件：{rebound}"

        meter = cq.ModelCallMeter()
        meter.charge(lane="probe", tokens=5, reason="自检")
        assert meter.snapshot() == {
            "model_calls": 1, "tokens": 5, "call_log": [("probe", 5, "自检")],
        }
        with pytest.raises(WakeError):
            meter.charge(lane="probe", tokens=-1, reason="负数必须拒")

    def test_reuses_the_existing_dispatcher(self):
        assert cq.dispatch_wake_event is wake_dispatcher.dispatch_wake_event

    def test_reuses_the_legal_verdict_and_tristate_enums(self):
        from aios_core.contracts import enums_v3

        assert cq.SafetyVerdict is enums_v3.SafetyVerdict
        assert cq.TriState is enums_v3.TriState
        assert cq.WakeSourceV3 is enums_v3.WakeSourceV3

    def test_reuses_the_legal_materialized_carrier(self):
        from aios_core.contracts import models_v3

        assert cq.SafetyGateVerdict is models_v3.SafetyGateVerdict

    @staticmethod
    def _classes_defined_here():
        """**用 AST 数类定义，不用字符串匹配。**

        字符串匹配会把 docstring 里的*提及*误判成定义 —— 本模块的 docstring 正当
        引用了并行线的 ``class WakePriority`` 以记录其双枚举缺陷，grep 立刻误报。
        这是同一类陷阱第三次出现（前两次：M2-005R 的 ``_TASK_TRANSITIONS``、
        本文件的 ``meter.charge(``），所以一律改判据而不是改文档。
        """
        import ast

        tree = ast.parse(MODULE_SOURCE)
        return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    def test_module_does_not_define_its_own_verdict_enum(self):
        """本模块不得出现第二个裁决枚举（双枚举 = 落盘失败的既有前车之鉴）。"""
        defined = self._classes_defined_here()
        assert not (defined & {"SafetyVerdict", "Verdict", "Step0Verdict", "Convenience"})

    def test_module_does_not_define_its_own_priority_or_wake_state(self):
        defined = self._classes_defined_here()
        assert not (defined & {"WakePriority", "WakeState", "WakeSource", "WakeSourceV3"})

    def test_the_legal_wake_priority_is_used_and_the_sibling_shadow_enum_is_gone(self):
        """钉住"用法定四级优先级"，并把一个**已被主干修掉的缺陷**转成回归守卫。

        取证历史（保留，别丢）：并行线 ``wake/cooldown_queue.py`` 曾在模块内自定义
        ``WakePriority``，成员 ``P0_CRITICAL_SAFETY`` / ``NORMAL`` —— 与法定
        ``contracts.safety_bypass.WakePriority`` 同名而不同物，且 ``NORMAL`` 在法定枚举里
        没有对应成员。本仓库 ObjectType / ObjectTypeV3 双枚举曾致 v3 扩展类型完全无法落盘，
        属已付学费的缺陷类。

        主干重写后该缺陷**已消失**：``cooldown_queue.py`` 改为
        ``from aios_core.contracts.safety_bypass import WakePriority``，不再自定义同名枚举，
        并按法定四级建了 ``_PRIORITY_ORDER``。于是本测试从"留证他人缺陷"改写为
        "缺陷不得回归"：用 AST 断言兄弟模块内不存在 ``WakePriority`` 类定义
        （字符串匹配会命中 import 行与 docstring，故必须用语法树），
        并断言它引用的就是法定本体。旧影子成员名 ``NORMAL`` 不得复活。
        """
        from aios_core.contracts.safety_bypass import WakePriority as LegalPriority
        from aios_core.wake import cooldown_queue as sibling

        # 本模块引用的 WakePriority **就是**法定枚举本体，不是影子副本
        assert cq.WakePriority is LegalPriority
        assert "WakePriority" not in cq.__all__, "不得把枚举再导出一次，避免第二处命名权威"
        hints = typing.get_type_hints(CandidateWake)
        assert hints["priority"] is LegalPriority

        # 兄弟模块的影子枚举已消失，且不得回归
        assert sibling.WakePriority is LegalPriority, "兄弟模块又开始用影子枚举"
        shadow = [
            n.name for n in ast.walk(ast.parse(Path(sibling.__file__).read_text(encoding="utf-8")))
            if isinstance(n, ast.ClassDef) and n.name == "WakePriority"
        ]
        assert shadow == [], f"影子枚举回归：{shadow}"

        # 法定四级仍是四级；旧影子成员名 NORMAL 不是法定成员，不得复活
        assert {m.value for m in LegalPriority} == {
            "P0_CRITICAL_SAFETY", "P1_URGENT_TASK", "P2_NORMAL_INTERACT", "P3_BACKGROUND_TICK"
        }
        assert not hasattr(LegalPriority, "NORMAL")

    def test_non_positive_interval_rejected_at_construction(self):
        with pytest.raises(WakeError):
            HeartbeatScheduler(interval_hours=-1.0)

    def test_explicit_interval_overrides_the_factory_default(self):
        sched = HeartbeatScheduler(interval_hours=3.0)
        assert sched.interval_hours == 3.0

    def test_naive_datetimes_are_interpreted_as_utc(self, sched, ledger):
        """虚拟时钟里混入本地时区会让 7 天/30 天的断言随机器时区漂移。"""
        naive = datetime(2026, 9, 16, 10, 0)
        outcome = sched.beat(
            now=naive,
            signals=GateSignals.all_clear(naive, notification_epoch=1, budget=ledger),
            evidence_refs=("obs-1",),
            projected_tokens=750,
        )
        assert outcome.at.tzinfo is not None
        assert outcome.at == NOW

    def test_silent_patrol_record_is_json_auditable(self):
        record = SilentPatrolRecord(
            beat_index=1,
            at=NOW,
            reason="r",
            verdict=SafetyVerdict.QUIET,
            wake_id="w",
            still_allows=("background_silent_patrol",),
        )
        payload = json.loads(json.dumps(record.to_audit(), ensure_ascii=False))
        assert payload["verdict"] == "quiet"
        assert payload["still_allows"] == ["background_silent_patrol"]

    def test_queue_decision_is_json_auditable(self):
        decision = QueueDecision(
            state=WakeState.SUPPRESSED,
            wake_id="w",
            reason="feedback_cooldown_is_hard_constraint",
            cooldown_until=NOW,
        )
        payload = json.loads(json.dumps(decision.to_audit(), ensure_ascii=False))
        assert payload["state"] == "suppressed"
        assert payload["cooldown_until"] == NOW.isoformat()

    def test_validate_policy_section_rejects_a_non_object(self):
        with pytest.raises(WakeError, match="必须是对象"):
            validate_policy_section("heartbeat", ["not", "a", "dict"], required_fields=())

    def test_missing_policy_file_is_reported_not_swallowed(self, monkeypatch):
        monkeypatch.setattr(cq, "_POLICY_PATH", Path("/nonexistent/runtime_policy.json"))
        with pytest.raises(WakeError, match="找不到法定政策文件"):
            cq.load_runtime_policy()


# ---------------------------------------------------------------------------
# J · 端到端：一次合规的主动出声
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_a_well_founded_heartbeat_reaches_the_user_exactly_once(
        self, sched, meter, ledger
    ):
        """全链路：有证据 → Step-0 放行 → 入队 NEW → 经既有 dispatcher 装配看板。"""
        ctx = FakeContext()
        signals = GateSignals.all_clear(NOW, notification_epoch=42, budget=ledger)
        outcome = evidence_beat(sched, signals)
        assert outcome.decision.verdict.verdict is SafetyVerdict.OK
        assert outcome.decision.convenience == "OK"
        assert outcome.queue.state is WakeState.NEW
        receipt = sched.deliver(outcome, ctx)
        assert receipt == {"status": "COCKPIT_ASSEMBLED", "wake_id": outcome.wake.wake_id}
        assert ctx.cockpit_pipeline.executed == [outcome.wake.wake_id]
        assert meter.model_calls == 0
        assert outcome.patrol is None, "出声的心跳不该同时留下静默巡检记录"

    def test_thirty_virtual_days_at_the_policy_rhythm_stay_inside_the_budget(self, meter):
        """门禁 2/3/4 合起来跑一个月，且**按政策 basis 的节律**跑：3 小时一次 =
        240 次/月，正是 ``token_budget.subsystems.heartbeat.basis`` 假设的次数。

        刻意让"生活"很慷慨（一半的日子有实质证据），于是候选出声数会超过预算允许的
        48 次 —— 这条测试要证明的正是：**d_budget_gate 会把多出来的部分挡掉**，
        花费停在法定上限之内。取消率下界不写死成 0.8，而是由
        ``上限 / (心跳数 × 单次花费)`` 算出来，避免用魔法数字"通过"测试。
        """
        per_beat = 750
        sched = HeartbeatScheduler(meter=meter, interval_hours=3.0)
        cap = TB["subsystems"]["heartbeat"]["monthly_cap"]
        beats_per_month = int(24 * 30 / sched.interval_hours)
        assert beats_per_month == 240, "政策 basis 假设的正是 240 次/月"

        interval = timedelta(hours=sched.interval_hours)
        moment = NOW
        ctx = FakeContext()
        spent = 0
        budget_blocks = 0
        for day in range(30):
            for _ in range(int(24 / sched.interval_hours)):
                flags = {n: TriState.FALSE for n in CONVENIENCE + HARD_SIGNALS}
                if moment.hour < 7 or moment.hour >= 23:
                    flags["sleep" if moment.hour < 7 else "deep_focus"] = TriState.TRUE
                if day % 3 == 0:
                    flags["meeting"] = TriState.TRUE
                signals = GateSignals(
                    now=moment,
                    flags=flags,
                    notification_epoch=day + 1,
                    budget=BudgetLedger(
                        heartbeat_cap=cap,
                        monthly_cap=TB["monthly_total_cap"],
                        heartbeat_spent=spent,
                        monthly_spent=spent,
                    ),
                )
                outcome = sched.beat(
                    now=moment,
                    signals=signals,
                    evidence_refs=(f"obs-{day}",) if day % 2 == 0 else (),
                    dimension_id="dim.health",
                    projected_tokens=per_beat,
                )
                if outcome.patrol is not None and any(
                    r.startswith("d_budget_gate:") and r != "d_budget_gate:within_cap"
                    for r in outcome.patrol.rules_fired
                ):
                    budget_blocks += 1
                if outcome.deliverable:
                    sched.deliver(outcome, ctx)
                    spent += per_beat
                moment += interval

        audit = sched.audit()
        assert meter.model_calls == 0, "一个月里 Step-0 与心跳不得叫过一次模型"
        assert spent <= cap, f"心跳月度花费 {spent} 冲破法定上限 {cap}"
        assert spent + per_beat > cap, "预算必须被用到闸门挡住为止，否则本测试没测到闸门"
        assert budget_blocks > 0, "d_budget_gate 从未开火 —— 它可能根本没接线"
        assert audit["counts"]["hard_blocked"] >= budget_blocks
        assert audit["counts"]["rhythm_bombs_delivered"] == 0
        assert audit["patrol_records"] == audit["counts"]["beats"] - audit["counts"]["delivered"]
        affordable_share = 1 - (cap / per_beat) / beats_per_month
        assert audit["gate_cancel_share"] >= affordable_share, (
            f"取消率低于预算所能承受的下界 {affordable_share:.3f} —— 承重参数被击穿"
        )
