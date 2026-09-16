"""Wearable FSM controller for 23cm flexible screen bracelet (M2-018 / V29).

8-second mild pulse pilot window to causally eliminate accidental touch false triggers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class WearableState(str, Enum):
    IDLE = "IDLE"                        # 静默待机 (骨传导断电，麦克风休眠，误触因果律为0)
    TRIGGERED_MILD = "TRIGGERED_MILD"    # 发出单次先导微震，开启 8 秒检测窗口
    CANVAS_VIEW = "CANVAS_VIEW"          # 8秒内抬手看屏，柔性屏展开 1~3 句极简卡片
    BONE_AUDIO = "BONE_AUDIO"            # 8秒内贴耳摸耳，骨传导通电私密入耳传音
    EMERGENCY_ALARM = "EMERGENCY_ALARM"  # P0 连续强震与最高分贝呼叫


class HardwareTriggerEvent(str, Enum):
    AI_SUGGESTION_READY = "AI_SUGGESTION_READY"  # AI 产生非紧急提醒
    WRIST_RAISED_TO_EYE = "WRIST_RAISED_TO_EYE"  # 抬手看表姿势
    FINGER_TOUCHED_EAR = "FINGER_TOUCHED_EAR"    # 手指贴耳姿势
    TIMEOUT_8_SECONDS = "TIMEOUT_8_SECONDS"      # 8 秒无响应超时
    CRITICAL_HAZARD = "CRITICAL_HAZARD"          # P0 生命突发险情


class WearableFSMController:
    def __init__(self, hardware_actuator: Any) -> None:
        self.state: WearableState = WearableState.IDLE
        self.window_start_time: Optional[datetime] = None
        self.hardware = hardware_actuator
        if hasattr(self.hardware, "set_bone_conduction_power"):
            self.hardware.set_bone_conduction_power(False)

    def transition(self, event: HardwareTriggerEvent) -> WearableState:
        now = datetime.now(timezone.utc)
        if event == HardwareTriggerEvent.CRITICAL_HAZARD:
            self.state = WearableState.EMERGENCY_ALARM
            if hasattr(self.hardware, "set_haptic_vibration"):
                self.hardware.set_haptic_vibration("CONTINUOUS_MAX")
            if hasattr(self.hardware, "set_speaker_broadcast"):
                self.hardware.set_speaker_broadcast(True)
            return self.state

        if self.state == WearableState.IDLE:
            if event == HardwareTriggerEvent.AI_SUGGESTION_READY:
                self.state = WearableState.TRIGGERED_MILD
                self.window_start_time = now
                if hasattr(self.hardware, "set_haptic_vibration"):
                    self.hardware.set_haptic_vibration("SINGLE_MILD_PULSE")
                return self.state

        elif self.state == WearableState.TRIGGERED_MILD:
            if (
                self.window_start_time is not None
                and (now - self.window_start_time).total_seconds() > 8.0
            ) or event == HardwareTriggerEvent.TIMEOUT_8_SECONDS:
                self.state = WearableState.IDLE
                self.window_start_time = None
                return self.state
            if event == HardwareTriggerEvent.WRIST_RAISED_TO_EYE:
                self.state = WearableState.CANVAS_VIEW
                if hasattr(self.hardware, "render_screen_card"):
                    self.hardware.render_screen_card()
                return self.state
            if event == HardwareTriggerEvent.FINGER_TOUCHED_EAR:
                self.state = WearableState.BONE_AUDIO
                if hasattr(self.hardware, "set_bone_conduction_power"):
                    self.hardware.set_bone_conduction_power(True)
                if hasattr(self.hardware, "play_audio_stream"):
                    self.hardware.play_audio_stream()
                return self.state

        elif self.state in (WearableState.CANVAS_VIEW, WearableState.BONE_AUDIO):
            if hasattr(self.hardware, "set_bone_conduction_power"):
                self.hardware.set_bone_conduction_power(False)
            self.state = WearableState.IDLE
            self.window_start_time = None
            return self.state

        return self.state
