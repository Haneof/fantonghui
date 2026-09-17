"""M0-023-V22 独立红队验收层（独立命名，纯追加 —— 不改动、不覆盖 V1 主链）。

跨模态心血管突发危机（03:15 深度睡眠：室性早搏连发 165bpm + 5.2G 心源性晕厥跌倒）
对抗性复核：

- 畸形 P0（safety_bypass 缺失 / hazard_type 缺失）：V1 主链必须"先脉冲后报错"
  （SOS 不静音），失败安全入口 ``safe_dispatch_v22`` 必须返回降级可审计结果；
- 良构 P0：委托 V1 主链行为不变，审计回执 FIFO 入队；
- 100 次 P0 突发端到端全部 <= 50ms；
- 复合体征快照（心脏 + 三轴撞击 + 时钟）逐字节透传至硬件脉冲；
- 脉冲失败回执诚实性（hardware_action_dispatched=False）；
- 非 P0 与 P0 的严格隔离（零脉冲 / 零队列 / 看板恰好 1 次）。
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.wake import dispatcher
from aios_core.wake.dispatcher import (
    SAFETY_AUDIT_QUEUE,
    clear_safety_audit_queue,
    dispatch_wake_event,
)
from aios_core.wake.v22_hardware_first import safe_dispatch_v22

UTC_NS = SimpleNamespace(tzinfo=None)  # 占位：时间一律用 datetime

V22_COMPOSITE_SNAPSHOT = {
    "clock": "03:15",
    "cardiac": {"pvc_run": 4, "hr_bpm_peak": 165, "arrhythmia": "nocturnal_pvc_run"},
    "fall": {"g_force_peak": 5.2, "three_axis": [4.1, 1.2, 3.0], "posture_change": True},
    "context": "deep_sleep_nocturnal_urination",
}


def make_wellformed_wake(object_id: str = "wake-rt-v22-001") -> SimpleNamespace:
    return SimpleNamespace(
        object_id=object_id,
        priority=WakePriority.P0_CRITICAL_SAFETY,
        safety_bypass=SafetyBypassPayload(
            hazard_type=HazardType.CARDIAC_ARREST,
            vital_snapshot=dict(V22_COMPOSITE_SNAPSHOT),
        ),
    )


class _PulseSpy:
    def __init__(self, ok: bool = True, delay_s: float = 0.0):
        self.ok = ok
        self.delay_s = delay_s
        self.calls: list[dict] = []

    def __call__(self, action_code: str, payload: dict) -> bool:
        self.calls.append({"action_code": action_code, "payload": payload, "at": time.perf_counter()})
        if self.delay_s:
            time.sleep(self.delay_s)
        return self.ok


@pytest.fixture
def pulse_spy(monkeypatch):
    spy = _PulseSpy()
    monkeypatch.setattr(dispatcher, "dispatch_emergency_hardware_pulse", spy)
    clear_safety_audit_queue()
    yield spy
    clear_safety_audit_queue()


class _CountingContext:
    def __init__(self):
        self.cockpit_calls = 0

    class _Cockpit:
        def __init__(self, parent):
            self._parent = parent

        def execute(self, wake):
            self._parent.cockpit_calls += 1
            return {"status": "COCKPIT_ASSEMBLED"}

    @property
    def cockpit_pipeline(self):
        return self._Cockpit(self)


class TestMalformedP0NeverSilencesSOS:
    def test_v1_main_chain_fires_pulse_before_any_exception(self, pulse_spy):
        """红队发现留档：畸形 P0 下 V1 主链先发出 SOS、后在收据阶段抛异常。
        生命安全语义成立（人先被救），审计降级由 v22_hardware_first 兜底。"""
        wake = SimpleNamespace(
            object_id="wake-rt-v22-malformed",
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=None,
        )
        with pytest.raises(AttributeError):
            dispatch_wake_event(wake, _CountingContext())
        assert len(pulse_spy.calls) == 1  # SOS 已在异常之前发出
        assert pulse_spy.calls[0]["action_code"] == "EMERGENCY_BROADCAST_AND_SOS"

    def test_safe_dispatch_malformed_returns_degraded_audit(self, pulse_spy):
        wake = SimpleNamespace(
            object_id="wake-rt-v22-malformed-2",
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=None,
        )
        started = time.perf_counter()
        result = safe_dispatch_v22(wake)
        e2e_ms = (time.perf_counter() - started) * 1000.0
        assert result["status"] == "SAFETY_BYPASS_EXECUTED_DEGRADED"
        assert result["first_action"] == "hardware_pulse"
        assert result["degraded"] is True
        assert result["llm_calls"] == 0
        assert result["cockpit_assemblies"] == 0
        assert result["world_persistence_yielded"] is True
        assert result["hardware_action_dispatched"] is True
        assert len(pulse_spy.calls) == 1
        assert result["audit"]["hazard_type"] is None  # 不伪造险情类型
        assert e2e_ms <= 50.0

    def test_safe_dispatch_missing_hazard_type_attr_is_degraded(self, pulse_spy):
        wake = SimpleNamespace(
            object_id="wake-rt-v22-nohazard",
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=SimpleNamespace(
                vital_snapshot={"hr_bpm": 165},
            ),  # 有载荷但缺 hazard_type
        )
        result = safe_dispatch_v22(wake)
        assert result["degraded"] is True
        assert result["hardware_action_dispatched"] is True
        assert pulse_spy.calls[0]["payload"] == {"hr_bpm": 165}

    def test_pulse_failure_yields_honest_degraded_receipt(self, pulse_spy):
        pulse_spy.ok = False
        wake = SimpleNamespace(
            object_id="wake-rt-v22-pulsefail",
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=None,
        )
        result = safe_dispatch_v22(wake)
        assert result["hardware_action_dispatched"] is False
        assert result["audit"]["hardware_action_dispatched"] is False


class TestWellformedP0DelegatesToV1:
    def test_safe_dispatch_wellformed_matches_v1_semantics(self, pulse_spy):
        wake = make_wellformed_wake()
        result = safe_dispatch_v22(wake, _CountingContext())
        assert result["status"] == "SAFETY_BYPASS_EXECUTED"
        assert "degraded" not in result or result.get("degraded") is not True
        assert result["bypassed_llm"] is False
        assert result["llm_calls"] == 1
        assert "emergency_decision" in result
        assert result["cockpit_assemblies"] == 0
        assert len(pulse_spy.calls) == 1
        # 良构 P0 走 V1 主链：审计回执必须入队
        assert len(SAFETY_AUDIT_QUEUE) == 1
        assert SAFETY_AUDIT_QUEUE[0].hazard_type == HazardType.CARDIAC_ARREST

    def test_composite_vital_snapshot_passed_byte_intact_to_pulse(self, pulse_spy):
        wake = make_wellformed_wake()
        safe_dispatch_v22(wake)
        assert pulse_spy.calls[0]["payload"] == V22_COMPOSITE_SNAPSHOT


class TestAuditQueueAndBurstStability:
    def test_audit_queue_fifo_ordering(self, pulse_spy):
        for i in range(3):
            safe_dispatch_v22(make_wellformed_wake(f"wake-rt-v22-queue-{i}"))
        receipts = list(SAFETY_AUDIT_QUEUE)
        assert len(receipts) == 3
        assert [r.receipt_id for r in receipts] == [
            f"rcpt_safe_wake-rt-v22-queue-{i}" for i in range(3)
        ]
        assert clear_safety_audit_queue() == 3
        assert len(SAFETY_AUDIT_QUEUE) == 0

    def test_hundred_p0_bursts_all_within_50ms(self, pulse_spy):
        worst = 0.0
        for i in range(100):
            wake = make_wellformed_wake(f"wake-rt-v22-burst-{i}")
            started = time.perf_counter()
            result = dispatch_wake_event(wake, _CountingContext())
            e2e_ms = (time.perf_counter() - started) * 1000.0
            assert e2e_ms <= 50.0, f"第 {i} 次 P0 穿透 {e2e_ms:.2f}ms 超过 50ms 红线"
            assert result["receipt"]["latency_ms"] <= 50.0
            worst = max(worst, e2e_ms)
        assert worst < 20.0  # 留档实测水位，防止后续退化逼近红线

    def test_slow_pulse_still_within_budget(self, monkeypatch):
        """硬件脉冲自身耗时 5ms（蜂窝通道抖动）时，端到端仍 <= 50ms。"""
        slow = _PulseSpy(ok=True, delay_s=0.005)
        monkeypatch.setattr(dispatcher, "dispatch_emergency_hardware_pulse", slow)
        wake = make_wellformed_wake("wake-rt-v22-slow")
        started = time.perf_counter()
        result = dispatch_wake_event(wake, _CountingContext())
        e2e_ms = (time.perf_counter() - started) * 1000.0
        assert e2e_ms <= 50.0
        assert result["receipt"]["hardware_action_dispatched"] is True


class TestNonP0Isolation:
    def test_p2_wake_uses_cockpit_exactly_once_without_pulse(self, pulse_spy):
        context = _CountingContext()
        wake = SimpleNamespace(object_id="wake-rt-v22-p2", priority=WakePriority.P2_NORMAL_INTERACT)
        result = safe_dispatch_v22(wake, context)
        assert result["status"] == "COCKPIT_ASSEMBLED"
        assert context.cockpit_calls == 1
        assert pulse_spy.calls == []
        assert len(SAFETY_AUDIT_QUEUE) == 0

    def test_non_p0_without_context_fails_closed(self, pulse_spy):
        wake = SimpleNamespace(object_id="wake-rt-v22-noctx", priority=WakePriority.P3_BACKGROUND_TICK)
        with pytest.raises(ValueError, match="cockpit_pipeline"):
            safe_dispatch_v22(wake, None)
        assert pulse_spy.calls == []
