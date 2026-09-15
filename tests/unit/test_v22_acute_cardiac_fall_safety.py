"""M0-023-V22 跨模态心血管突发危机 —— P0 硬件直穿安全测试。

实战场景：凌晨 03:15，用户深度睡眠中出现恶性心律失常（夜间室性早搏
连发 + 心率骤升至 165bpm），随后三轴加速度计检测到 5.2G 瞬间冲击与
体位骤变——夜间起夜突发心源性晕厥跌倒。

四大硬门禁：
1. 硬件直接穿透：事件被分级为 WakePriority.P0_CRITICAL_SAFETY；调度器
   首行直接执行硬件蜂窝紧急求救脉冲；
2. 世界模型与大模型彻底让路：LLM 调用严格 = 0；Cockpit 看板组装严格
   = 0；世界状态持久化事务让路（延迟结算句柄，脉冲后才可落库）；
3. 端到端耗时（事件进入调度器 → 硬件报警脉冲发出）严格 ≤ 50ms；
4. 重复事件幂等：同一事件绝不重复呼救（行动去重，A06 纪律）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.safety_bypass import (
    CARDIAC_FALL_WINDOW_S,
    CARDIAC_HR_SPIKE_BPM,
    CARDIAC_PVC_BURST_MIN,
    FALL_IMPACT_G,
    AcuteCardiacFallSignal,
    HazardType,
    WakePriority,
    classify_acute_cardiac_fall,
)
from aios_core.wake.dispatcher import (
    EmergencyHardwareBus,
    SafetyDispatchServices,
    dispatch_p0_acute_cardiac_fall,
    dispatch_wake_event,
    safety_audit_log,
    settle_deferred_world_persistence,
)

UTC = timezone.utc
T_EVENT = datetime(2026, 9, 16, 3, 15, 0, tzinfo=UTC)  # 凌晨 03:15


def build_scene_signal(**overrides) -> AcuteCardiacFallSignal:
    """03:15 深睡：室早连发 14 次/10min + 心率骤升 165 + 5.2G 冲击 + 体位骤变。"""
    kwargs = dict(
        observed_at=T_EVENT,
        asleep=True,
        heart_rate_bpm=165.0,
        pvc_count_10min=14,
        impact_g=5.2,
        posture_changed=True,
        signal_refs=(
            "obs_hrv_night_spike_0313",
            "obs_imu_impact_5g2_0315",
            "obs_posture_flip_0315",
        ),
    )
    kwargs.update(overrides)
    return AcuteCardiacFallSignal(**kwargs)


def build_services() -> tuple[SafetyDispatchServices, dict[str, int]]:
    """注入 LLM/看板/世界持久化探针，返回 (services, 计数器引用)。"""
    counters = {"llm": 0, "cockpit": 0, "world": 0}

    def llm_probe(*a, **k):
        counters["llm"] += 1
        raise AssertionError("P0 路径绝不允许调用大模型")

    def cockpit_probe(*a, **k):
        counters["cockpit"] += 1
        raise AssertionError("P0 路径绝不允许组装认知看板")

    def world_probe(*a, **k):
        counters["world"] += 1
        return {"persisted": True, **k}

    services = SafetyDispatchServices(
        hardware_bus=EmergencyHardwareBus(),
        llm_invoke=llm_probe,
        cockpit_assembly=cockpit_probe,
        world_persist=world_probe,
    )
    return services, counters


# ======================================================================
# 门禁 1：机械分级 + 硬件首行直穿
# ======================================================================

def test_gate1_cross_modal_signal_classified_p0() -> None:
    event = classify_acute_cardiac_fall(build_scene_signal(), event_id="v22_0315")
    assert event.priority is WakePriority.P0_CRITICAL_SAFETY
    assert event.hazard_type is HazardType.CARDIAC_ARREST
    reasons = " | ".join(event.mechanical_reasons)
    assert "CARDIAC_ANOMALY" in reasons and "FALL_IMPACT" in reasons
    # 分级是纯机械阈值比较（宪法 §77/§106），证据链完整
    assert len(event.signal.signal_refs) == 3


def test_gate1_severe_fall_alone_is_p0_cardiac_alone_is_p1() -> None:
    # 宪法 §78-4：严重摔倒/剧烈撞击单独出现即为最高优先级
    fall_only = classify_acute_cardiac_fall(
        build_scene_signal(heart_rate_bpm=64.0, pvc_count_10min=0),
        event_id="v22_fall_only",
    )
    assert fall_only.priority is WakePriority.P0_CRITICAL_SAFETY
    assert fall_only.hazard_type is HazardType.FALL_DETECTED
    # 单纯心律异常（无跌倒）：紧急任务级，不触发硬件急救特权
    cardiac_only = classify_acute_cardiac_fall(
        build_scene_signal(impact_g=0.2, posture_changed=False),
        event_id="v22_cardiac_only",
    )
    assert cardiac_only.priority is WakePriority.P1_URGENT_TASK
    # 低于机械阈值的普通夜间翻身：绝不误触
    benign = classify_acute_cardiac_fall(
        build_scene_signal(
            heart_rate_bpm=62.0, pvc_count_10min=1, impact_g=1.1
        ),
        event_id="v22_benign",
    )
    assert benign.priority is WakePriority.P2_NORMAL_INTERACT


def test_gate1_pulse_is_the_literal_first_action(tmp_path=None) -> None:
    services, counters = build_services()
    event = classify_acute_cardiac_fall(build_scene_signal(), event_id="v22_first")
    outcome = dispatch_p0_acute_cardiac_fall(event, services)

    assert outcome.result.pulse_dispatched is True
    assert outcome.result.action_order[0] == "hardware_pulse"
    bus = services.hardware_bus
    assert bus.pulse_count == 1
    pulse = bus.pulses[0]
    assert pulse["action_code"] == "EMERGENCY_BROADCAST_AND_SOS"
    assert pulse["payload"]["vital_snapshot"]["heart_rate_bpm"] == 165.0
    assert pulse["payload"]["vital_snapshot"]["impact_g"] == 5.2


# ======================================================================
# 门禁 2：大模型 / 看板 / 世界持久化彻底让路
# ======================================================================

def test_gate2_zero_llm_zero_cockpit_and_persistence_deferred() -> None:
    services, counters = build_services()
    event = classify_acute_cardiac_fall(build_scene_signal(), event_id="v22_yield")
    outcome = dispatch_p0_acute_cardiac_fall(event, services)

    # LLM 与看板：计数严格为 0（探针一旦被调用会直接抛断言异常）
    assert outcome.result.llm_calls == 0
    assert outcome.result.cockpit_assembly_calls == 0
    assert counters["llm"] == 0 and counters["cockpit"] == 0
    # 世界持久化让路：派发期间零写入，仅登记延迟句柄
    assert outcome.result.world_persistence_calls == 0
    assert counters["world"] == 0
    assert outcome.result.persistence_state == "DEFERRED"
    assert services.deferred_persistence == ["defer_world_persist:v22_yield"]

    # 脉冲之后的安全时机结算：审计回执追加式落库
    settled = settle_deferred_world_persistence(outcome, services, event=event)
    assert settled["settled"] is True
    assert counters["world"] == 1
    assert safety_audit_log()[-1].receipt_id == outcome.audit_receipt_id
    assert safety_audit_log()[-1].bypassed_mind_sequence is True


def test_gate2_non_p0_events_still_route_through_normal_path() -> None:
    """让路是选择性的：非 P0 事件必须照常走 LLM/看板路径（旁路不能吞掉日常）。"""
    counters = {"llm": 0, "cockpit": 0, "world": 0}
    services = SafetyDispatchServices(
        hardware_bus=EmergencyHardwareBus(),
        cockpit_assembly=lambda wake: {"status": "COCKPIT_DISPATCHED"},
    )
    # 用计数器包一层探针（计数与真实调用绑定在同一路径上）
    original = services._cockpit_assembly

    def counting_assembly(wake):
        counters["cockpit"] += 1
        return original(wake)

    services._cockpit_assembly = counting_assembly
    cardiac_only = classify_acute_cardiac_fall(
        build_scene_signal(impact_g=0.2, posture_changed=False),
        event_id="v22_normal_route",
    )
    assert cardiac_only.priority is WakePriority.P1_URGENT_TASK

    class _LegacyContext:
        class cockpit_pipeline:  # noqa: N801 - 与旧契约同名命名空间
            @staticmethod
            def execute(wake):
                services.assemble_cockpit(wake)
                return {"status": "COCKPIT_DISPATCHED"}

    result = dispatch_wake_event(cardiac_only, _LegacyContext())
    assert result["status"] == "COCKPIT_DISPATCHED"
    assert counters["cockpit"] == 1 and counters["llm"] == 0


# ======================================================================
# 门禁 3：端到端 ≤ 50ms
# ======================================================================

def test_gate3_end_to_end_latency_within_50ms() -> None:
    import time

    for round_index in range(20):
        services, _ = build_services()
        event = classify_acute_cardiac_fall(
            build_scene_signal(), event_id=f"v22_lat_{round_index}"
        )
        entry = time.perf_counter()
        outcome = dispatch_p0_acute_cardiac_fall(event, services)
        wall_ms = (time.perf_counter() - entry) * 1000.0
        assert outcome.result.entry_to_pulse_ms <= 50.0
        assert wall_ms <= 50.0, f"round {round_index}: {wall_ms}ms > 50ms"
        # 设计预期：数量级余量（模拟总线为纯内存操作）
        assert outcome.result.entry_to_pulse_ms < 5.0


# ======================================================================
# 门禁 4：幂等——同一事件绝不重复呼救
# ======================================================================

def test_gate4_duplicate_event_never_refires_pulse() -> None:
    services, _ = build_services()
    event = classify_acute_cardiac_fall(build_scene_signal(), event_id="v22_dedupe")
    first = dispatch_p0_acute_cardiac_fall(event, services)
    second = dispatch_p0_acute_cardiac_fall(event, services)
    assert first.result.pulse_dispatched is True
    assert second.result.pulse_dispatched is False
    assert second.result.dedup_replay is True
    assert services.hardware_bus.pulse_count == 1  # 只呼救一次


# ======================================================================
# 阈值边界（机械分级的可测试参数域）
# ======================================================================

@pytest.mark.parametrize(
    "hr,pvc,impact,posture,expected",
    [
        (CARDIAC_HR_SPIKE_BPM, CARDIAC_PVC_BURST_MIN, FALL_IMPACT_G, True,
         WakePriority.P0_CRITICAL_SAFETY),   # 恰在阈值上 = 命中
        (149.9, 14, 5.2, True, WakePriority.P0_CRITICAL_SAFETY),  # 心率差 0.1 但跌倒独立成立
        (165.0, 4, 5.2, True, WakePriority.P0_CRITICAL_SAFETY),   # 跌倒独立成立
        (165.0, 14, 4.4, True, WakePriority.P1_URGENT_TASK),      # 冲击不足 → 仅心律异常
        (165.0, 14, 5.2, False, WakePriority.P1_URGENT_TASK),     # 体位未变 → 仅心律异常
    ],
)
def test_threshold_boundaries_are_mechanical_and_exact(
    hr, pvc, impact, posture, expected
) -> None:
    event = classify_acute_cardiac_fall(
        build_scene_signal(
            heart_rate_bpm=hr,
            pvc_count_10min=pvc,
            impact_g=impact,
            posture_changed=posture,
        ),
        event_id=f"v22_boundary_{hr}_{pvc}_{impact}_{posture}",
    )
    assert event.priority is expected


def test_time_window_constant_documented() -> None:
    """跨模态同事件判定窗口存在且为机械常量（分级可解释性的最低要求）。"""
    assert 0 < CARDIAC_FALL_WINDOW_S <= 300
    delta = timedelta(seconds=CARDIAC_FALL_WINDOW_S)
    assert delta.total_seconds() > 0
