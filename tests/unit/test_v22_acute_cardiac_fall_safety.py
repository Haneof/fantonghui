"""M0-023-V22 跨模态心血管突发危机 P0 硬件直穿验收单测。

高阶实战场景：凌晨 03:15，手环监测到用户深度睡眠状态下出现恶性心律失常
（夜间室性早搏连发、心率骤升至 165bpm），随后三轴加速度计检测到 5.2G 瞬间
冲击力与体位骤变（夜间起夜突发心源性晕厥跌倒）。

四大硬门禁断言：
1. 硬件直接穿透：调度器首行直接执行 dispatch_emergency_hardware_pulse，
   跨模态 vital_snapshot（心率/早搏/G 值/体位）原样送达硬件层；
2. 世界模型与大模型彻底让路：LLM 调用严格 0、Cockpit Assembly 严格 0、
   世界持久化事务让路（审计回执走非阻塞队列）；
3. 耗时硬指标：入调度器 → 硬件报警脉冲发出，端到端严格 <= 50ms。
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import aios_core.wake.dispatcher as dispatcher_module
from aios_core.contracts.safety_bypass import HazardType, SafetyBypassPayload, WakePriority
from aios_core.wake.dispatcher import (
    SAFETY_AUDIT_QUEUE,
    clear_safety_audit_queue,
    dispatch_wake_event,
)

UTC = timezone.utc
CRISIS_MOMENT = datetime(2026, 9, 15, 3, 15, tzinfo=UTC)  # 凌晨 03:15

#: 跨模态生命体征快照：恶性心律失常 + 心源性晕厥跌倒（多传感器交叉证据）
V22_VITAL_SNAPSHOT = {
    "scene": "deep_sleep_nocturnal",
    "clock": "03:15",
    "heart_rate_bpm": 165,
    "pvc_burst_count": 7,  # 室性早搏连发
    "rhythm": "nocturnal_pvc_run_with_hr_spike",
    "axial_g_force": 5.2,  # 三轴加速度计瞬间冲击
    "posture_change": True,  # 体位骤变（起夜晕厥跌倒）
    "spo2_percent": 91,
}


def build_v22_wake(order: list | None = None) -> SimpleNamespace:
    """构造凌晨 03:15 的 P0 跨模态危机唤醒事件。"""
    _ = order  # 事件本身不感知调用顺序
    return SimpleNamespace(
        object_id="wake_v22_cardiac_fall_0315",
        priority=WakePriority.P0_CRITICAL_SAFETY,
        safety_bypass=SafetyBypassPayload(
            is_safety_bypass=True,
            hazard_type=HazardType.CARDIAC_ARREST,
            vital_snapshot=dict(V22_VITAL_SNAPSHOT),
            emergency_action_code="EMERGENCY_BROADCAST_AND_SOS",
            triggered_at=CRISIS_MOMENT,
        ),
    )


class InstrumentedContext:
    """全插桩上下文：对 LLM / 看板 / 世界持久化三类动作逐一计数并记录顺序。"""

    def __init__(self, order: list) -> None:
        self.order = order
        self.llm_calls = 0
        self.cockpit_assemblies = 0
        self.world_persistence_tx = 0

    def llm_complete(self, *args, **kwargs) -> str:
        self.order.append("llm_call")
        self.llm_calls += 1
        return ""

    class _Cockpit:
        def __init__(self, ctx: "InstrumentedContext") -> None:
            self.ctx = ctx

        def execute(self, wake):
            self.ctx.order.append("cockpit_assembly")
            self.ctx.cockpit_assemblies += 1
            return {"status": "COCKPIT_ASSEMBLED"}

    class _WorldStore:
        def __init__(self, ctx: "InstrumentedContext") -> None:
            self.ctx = ctx

        def commit(self, *args, **kwargs):
            self.ctx.order.append("world_persistence")
            self.ctx.world_persistence_tx += 1
            return {"ok": True}


@pytest.fixture(autouse=True)
def _drain_audit_queue():
    clear_safety_audit_queue()
    yield
    clear_safety_audit_queue()


# ----------------------------------------------------------------------
# 门禁 1 + 2：首行硬件穿透 + 世界模型/大模型/持久化彻底让路
# ----------------------------------------------------------------------


class TestP0HardwareDirectPierce:
    def test_first_line_is_hardware_pulse_and_everything_yields(self, monkeypatch):
        order: list = []
        pulse_payloads: list = []

        def spy_pulse(action_code: str, payload: dict) -> bool:
            order.append("hardware_pulse")
            pulse_payloads.append((action_code, payload))
            return True

        monkeypatch.setattr(dispatcher_module, "dispatch_emergency_hardware_pulse", spy_pulse)

        ctx = InstrumentedContext(order)
        ctx.cockpit_pipeline = InstrumentedContext._Cockpit(ctx)
        ctx.world_store = InstrumentedContext._WorldStore(ctx)
        wake = build_v22_wake(order)

        result = dispatch_wake_event(wake, ctx)

        # 首行即硬件穿透，且是 P0 分支内唯一动作（顺序日志严格等于一条）
        assert order == ["hardware_pulse"]
        assert result["status"] == "SAFETY_BYPASS_EXECUTED"
        assert result["first_action"] == "hardware_pulse"
        assert result["bypassed_llm"] is True

        # 大模型彻底让路：调用次数严格 0
        assert result["llm_calls"] == 0
        assert ctx.llm_calls == 0

        # 认知看板组装彻底让路：调用次数严格 0
        assert result["cockpit_assemblies"] == 0
        assert ctx.cockpit_assemblies == 0

        # 世界状态持久化事务让路：0 次事务，回执走非阻塞审计队列
        assert result["world_persistence_yielded"] is True
        assert ctx.world_persistence_tx == 0
        assert len(SAFETY_AUDIT_QUEUE) == 1
        queued_receipt = SAFETY_AUDIT_QUEUE[0]
        assert queued_receipt.hardware_action_dispatched is True
        assert queued_receipt.hazard_type == HazardType.CARDIAC_ARREST

        # 跨模态 vital_snapshot 原样送达硬件层（多传感器交叉证据零丢失）
        action_code, payload = pulse_payloads[0]
        assert action_code == "EMERGENCY_BROADCAST_AND_SOS"
        assert payload["heart_rate_bpm"] == 165
        assert payload["pvc_burst_count"] == 7
        assert payload["axial_g_force"] == 5.2
        assert payload["posture_change"] is True
        assert payload["clock"] == "03:15"

        receipt = result["receipt"]
        assert receipt["hazard_type"] == HazardType.CARDIAC_ARREST.value
        assert receipt["bypassed_mind_sequence"] is True

    def test_latency_receipt_measures_entry_to_pulse(self, monkeypatch):
        order: list = []
        monkeypatch.setattr(
            dispatcher_module,
            "dispatch_emergency_hardware_pulse",
            lambda action_code, payload: (order.append("hardware_pulse") or True),
        )
        ctx = InstrumentedContext(order)
        ctx.cockpit_pipeline = InstrumentedContext._Cockpit(ctx)
        wake = build_v22_wake(order)

        result = dispatch_wake_event(wake, ctx)
        receipt = result["receipt"]
        assert receipt["latency_ms"] >= 0.0
        assert receipt["latency_ms"] <= 50.0


# ----------------------------------------------------------------------
# 门禁 3：端到端耗时硬指标 <= 50ms
# ----------------------------------------------------------------------


class TestE2ELatencyHardGate:
    def test_end_to_end_dispatch_within_50ms(self):
        import time

        ctx = InstrumentedContext([])
        wake = build_v22_wake([])
        started = time.perf_counter()
        result = dispatch_wake_event(wake, ctx)
        e2e_ms = (time.perf_counter() - started) * 1000.0

        assert e2e_ms <= 50.0, f"端到端穿透耗时 {e2e_ms:.2f}ms 超过 50ms 红线"
        assert result["receipt"]["latency_ms"] <= 50.0

    def test_sustained_p0_bursts_all_within_50ms(self):
        """连续 20 次 P0 突发（早搏反复报警）：每一次都守住 50ms。"""
        import time

        ctx = InstrumentedContext([])
        for _ in range(20):
            wake = build_v22_wake([])
            started = time.perf_counter()
            result = dispatch_wake_event(wake, ctx)
            e2e_ms = (time.perf_counter() - started) * 1000.0
            assert e2e_ms <= 50.0
            assert result["status"] == "SAFETY_BYPASS_EXECUTED"
        # 20 次熔断审计回执全部入队（非阻塞，事后可溯源）
        assert len(SAFETY_AUDIT_QUEUE) == 20


# ----------------------------------------------------------------------
# 对照组：非 P0 事件不受穿透影响，正常走看板流水线
# ----------------------------------------------------------------------


class TestNonP0Control:
    def test_p2_wake_goes_through_cockpit_not_bypass(self):
        order: list = []
        ctx = InstrumentedContext(order)
        ctx.cockpit_pipeline = InstrumentedContext._Cockpit(ctx)
        wake = SimpleNamespace(
            object_id="wake_p2_evening_checkin",
            priority=WakePriority.P2_NORMAL_INTERACT,
        )
        result = dispatch_wake_event(wake, ctx)
        assert result["status"] == "COCKPIT_ASSEMBLED"
        assert order == ["cockpit_assembly"]
        assert ctx.cockpit_assemblies == 1
        assert len(SAFETY_AUDIT_QUEUE) == 0  # 非 P0 不产生熔断审计
