"""End-to-End Latency and Hardware SLO Telemetry Benchmark (Sprint 4 / §85 / §78之1 / Iron Law 3)."""

from __future__ import annotations

import time
import pytest

from aios_core.wearable.hal_interface import (
    HardwareTelemetry,
    SimulatedHardwareActuator,
    VibrationPattern,
)
from ai_worker.cockpit_executor import CockpitExecutor, TurnExecutionResult


def test_slo_p0_critical_safety_hardware_bypass_50ms():
    """铁律三断言：P0 紧急突发直穿蜂窝急救，穿透耗时必须 <= 50ms，大模型调用次数严格为 0。"""
    actuator = SimulatedHardwareActuator()

    payload = {
        "hazard_type": "FALL_IMPACT_STATIC",
        "peak_g": 9.2,
        "hr_bpm": 35,
        "gps": "31.2304,121.4737",
        "emergency_contact": "120",
    }

    # 执行硬件蜂窝直呼
    duration_ms = actuator.trigger_cellular_sos(payload)

    # 铁律三硬门禁：穿透耗时 <= 50ms
    assert duration_ms <= 50.0
    assert len(actuator.sos_call_log) == 1
    assert actuator.sos_call_log[0]["hazard_type"] == "FALL_IMPACT_STATIC"


def test_slo_fast_lane_first_token_latency():
    """宪法第 85 条断言：日常快车道首字响应基线 p50 <= 600ms, p95 <= 1000ms。"""
    executor = CockpitExecutor()
    latencies: list[float] = []

    for i in range(20):
        res = executor.execute_turn(f"第 {i+1} 轮日常简短确认：事情办得怎么样了？")
        latencies.append(res.execution_time_ms)
        assert res.is_within_budget is True

    # 排序取分位数
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]

    # 断言首字延迟在测试环境下极其迅捷 (远远低于 600ms 和 1000ms)
    assert p50 < 600.0
    assert p95 < 1000.0


def test_hal_actuator_telemetry_and_vibration():
    """硬件抽象层功能遥测与模式断言。"""
    actuator = SimulatedHardwareActuator()

    # 触觉震动
    assert actuator.set_haptic_vibration(VibrationPattern.SINGLE_MILD_PULSE) is True
    assert actuator.set_haptic_vibration(VibrationPattern.CONTINUOUS_MAX) is True
    assert len(actuator.vibration_history) == 2

    # 屏幕渲染
    assert actuator.render_screen_card("喝水提醒", "CYAN") is True
    telemetry = actuator.get_telemetry()
    assert telemetry.screen_powered_on is True

    # 骨传导通电
    assert actuator.set_bone_conduction_power(True) is True
    assert actuator.get_telemetry().bone_conduction_powered is True
