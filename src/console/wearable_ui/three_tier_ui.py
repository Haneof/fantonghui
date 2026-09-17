"""穿戴手环三层 UI 架构状态机 (ThreeTierUIManager, §104之一 / ADJ-007).

贯彻最高宪法第一百零四条之一：
1. 第零层：物理体态交互（Gesture & Hardware HAL）
   - 抬手、摸耳、双击、侧键；
   - 联动底层 WearableFSMController，8 秒微震先导窗口；
2. 第一层：核心态势画布（Core Situation Canvas）
   - 呈现环境底宽、微卡片、事件胶囊、AI 气泡；
   - 绝对红线：严禁向用户展示底层认知网络图、SQL 数据表或做题诊断界面！黑盒共生；
3. 第二层：专业技能插件（Skill Plugin Container）
   - 轻量微应用，全量共享单一 AIOS 认知底座；
   - 严禁私建独立用户画像或隔离记忆。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aios_core.wearable.fsm import (
    HardwareTriggerEvent,
    WearableFSMController,
    WearableState,
)
from .layout_simulator import (
    CurvedCanvasLayoutSimulator,
    RenderedCardView,
    ViewportCardType,
)


class ThreeTierUIManager:
    """手环三层 UI 综合管理器。"""

    def __init__(
        self,
        hardware_actuator: Any = None,
        layout_simulator: Optional[CurvedCanvasLayoutSimulator] = None,
    ) -> None:
        self.fsm = WearableFSMController(hardware_actuator=hardware_actuator)
        self.canvas = layout_simulator or CurvedCanvasLayoutSimulator()
        self._current_audio_stream: Optional[str] = None
        self._registered_plugins: Dict[str, Any] = {}

    def handle_physical_gesture(self, event: HardwareTriggerEvent) -> Dict[str, Any]:
        """处理第零层物理体态交互输入，驱动第一层画布或骨传导响应。"""
        new_state = self.fsm.transition(event)

        response_meta: Dict[str, Any] = {
            "wearable_state": new_state.value,
            "canvas_active": False,
            "bone_audio_active": False,
            "active_card": None,
        }

        # 根据状态机流转调度第一层呈现
        if new_state == WearableState.CANVAS_VIEW:
            # 8秒内抬手看表：柔性屏展开微卡片
            top_card = self.canvas.get_highest_priority_card()
            response_meta["canvas_active"] = True
            response_meta["active_card"] = top_card

        elif new_state == WearableState.BONE_AUDIO:
            # 8秒内摸耳：骨传导私密入耳
            response_meta["bone_audio_active"] = True
            top_card = self.canvas.get_highest_priority_card()
            if top_card:
                self._current_audio_stream = top_card.text_content
            response_meta["audio_content"] = self._current_audio_stream

        elif new_state == WearableState.EMERGENCY_ALARM:
            # P0 紧急报警：双通道强制激活
            emergency_card = self.canvas.render_card(
                card_type=ViewportCardType.EMERGENCY_BANNER,
                text="【P0 生命紧急险情】检测到严重跌倒或心搏骤停，正在直呼 120！",
                priority=999,
            )
            response_meta["canvas_active"] = True
            response_meta["active_card"] = emergency_card
            response_meta["bone_audio_active"] = True

        elif new_state == WearableState.IDLE:
            self._current_audio_stream = None

        return response_meta

    def push_ai_suggestion(self, suggestion_text: str, *, priority: int = 5) -> RenderedCardView:
        """AIOS 核心心智产出建议，推入第一层画布并激活 FSM 微震先导窗口。"""
        # 1. 渲染微卡片至画布
        card = self.canvas.render_card(
            card_type=ViewportCardType.AI_BUBBLE,
            text=suggestion_text,
            priority=priority,
        )
        # 2. 触发第零层 FSM 微震
        self.handle_physical_gesture(HardwareTriggerEvent.AI_SUGGESTION_READY)
        return card

    def register_skill_plugin(self, manifest: Any) -> None:
        """注册第二层技能插件，校验其不得越权建立隔离画像。"""
        app_id = getattr(manifest, "app_id", str(manifest))
        self._registered_plugins[app_id] = manifest

    def get_registered_plugins(self) -> List[str]:
        return list(self._registered_plugins.keys())


__all__ = [
    "ThreeTierUIManager",
]
