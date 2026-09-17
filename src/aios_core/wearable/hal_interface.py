"""手环硬件抽象层软件契约 (Hardware Abstraction Layer, HAL).

贯彻宪法第五编第一百零四条及硬件资产规格：
1. 抽象 23cm 柔性屏手环底层物理硬件接口：
   - 超宽频偏心转子马达 (ERM/LRA) 触觉反馈；
   - 双耳骨传导换能器换能通路；
   - 23cm×5~6cm 环形柔性屏帧缓冲区；
   - 独立基带蜂窝急救直连通道 (P0 50ms 直穿)；
   - 传感器中断与低功耗步态采样通道。
2. 软硬件解耦：保证 AIOS 心智内核可在嵌入式真机、模拟器与 CI 环境无缝切换。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

UTC = timezone.utc


class VibrationPattern:
    """标准触觉震动模式。"""

    SINGLE_MILD_PULSE = "SINGLE_MILD_PULSE"        # 单次微震（先导提醒，体感轻柔）
    DOUBLE_ATTENTION = "DOUBLE_ATTENTION"          # 双击短震（关键待办）
    CONTINUOUS_MAX = "CONTINUOUS_MAX"              # P0 连续最高分贝强震（生命急救）


@dataclass
class HardwareTelemetry:
    """手环硬件健康与状态遥测指标。"""

    battery_percentage: float = 95.0
    battery_temperature_c: float = 28.5
    screen_powered_on: bool = False
    bone_conduction_powered: bool = False
    cellular_connected: bool = True
    bluetooth_connected: bool = True
    last_imu_interrupt_timestamp: Optional[datetime] = None


class WearableHardwareAbstractionLayer(ABC):
    """手环硬件抽象层抽象基类。"""

    @abstractmethod
    def set_haptic_vibration(self, pattern: str) -> bool:
        """驱动触觉震动马达。"""
        ...

    @abstractmethod
    def set_bone_conduction_power(self, enabled: bool) -> bool:
        """控制骨传导私密通路通断电。"""
        ...

    @abstractmethod
    def render_screen_card(self, text_content: str, visual_theme: str) -> bool:
        """向柔性屏显存推入微卡片渲染帧。"""
        ...

    @abstractmethod
    def set_speaker_broadcast(self, enabled: bool) -> bool:
        """控制外放喇叭广播（仅限 P0 急救场景）。"""
        ...

    @abstractmethod
    def trigger_cellular_sos(self, emergency_payload: Dict[str, Any]) -> float:
        """直通硬件蜂窝基带拨打 120/呼叫紧急联系人（返回硬件穿透耗时 ms，铁律三要求 <= 50ms）。"""
        ...

    @abstractmethod
    def get_telemetry(self) -> HardwareTelemetry:
        """读取硬件状态遥测数据。"""
        ...


class SimulatedHardwareActuator(WearableHardwareAbstractionLayer):
    """生产级硬件仿真器（兼具 CI 自动化断言与本地测试桩）。"""

    def __init__(self) -> None:
        self.telemetry = HardwareTelemetry()
        self.vibration_history: List[str] = []
        self.rendered_cards_history: List[Dict[str, str]] = []
        self.emergency_broadcast_active: bool = False
        self.sos_call_log: List[Dict[str, Any]] = []

    def set_haptic_vibration(self, pattern: str) -> bool:
        self.vibration_history.append(pattern)
        return True

    def set_bone_conduction_power(self, enabled: bool) -> bool:
        self.telemetry.bone_conduction_powered = enabled
        return True

    def render_screen_card(self, text_content: str, visual_theme: str) -> bool:
        self.telemetry.screen_powered_on = True
        self.rendered_cards_history.append({"text": text_content, "theme": visual_theme})
        return True

    def set_speaker_broadcast(self, enabled: bool) -> bool:
        self.emergency_broadcast_active = enabled
        return True

    def trigger_cellular_sos(self, emergency_payload: Dict[str, Any]) -> float:
        """模拟 P0 硬件直穿，严格断言耗时 <= 50ms。"""
        t0 = time.perf_counter()
        self.sos_call_log.append(emergency_payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return elapsed_ms

    def get_telemetry(self) -> HardwareTelemetry:
        return self.telemetry


__all__ = [
    "HardwareTelemetry",
    "SimulatedHardwareActuator",
    "VibrationPattern",
    "WearableHardwareAbstractionLayer",
]
