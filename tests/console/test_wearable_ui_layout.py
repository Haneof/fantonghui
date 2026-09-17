"""Tests for 23cm Flexible Screen Curved Canvas & Three-Tier UI Architecture (§104之一 / §98之一 / §99~104)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from aios_core.wearable.fsm import HardwareTriggerEvent, WearableState
from console.app_manifest import AppManifest, AppManifestRegistry
from console.wearable_ui import (
    CurvedCanvasLayoutSimulator,
    RenderedCardView,
    ThreeTierUIManager,
    ViewportCardType,
)


# ============================================================================
# 1. 23cm 环形画布布局约束测试
# ============================================================================
def test_curved_canvas_layout_constraints():
    simulator = CurvedCanvasLayoutSimulator()

    # 1. 常规老友气泡：<= 60 汉字，正常渲染不溢出
    card_ok = simulator.render_card(
        card_type=ViewportCardType.AI_BUBBLE,
        text="今晚去跑两圈吧，少想那些烦心事，跑完出一身汗通透。",
    )
    assert card_ok.is_overflow is False
    assert card_ok.character_count <= 60
    assert card_ok.visual_theme == "COMPANION_CYAN_BUBBLE"

    # 2. 超长长篇大论：超过 60 汉字，被标记为排版溢出 (is_overflow=True)
    long_text = "这是一段非常冗长的话，超过了六十个汉字的严格排版限制。因为手环是23厘米贴在手腕上的柔性长条屏，如果堆砌太多长篇大论的话用户看起来会非常累，而且违背了老友一到三句话的基本分寸！"
    card_overflow = simulator.render_card(
        card_type=ViewportCardType.AI_BUBBLE,
        text=long_text,
    )
    assert card_overflow.is_overflow is True
    assert card_overflow.character_count > 60

    # 3. P0 紧急报警红条：不受 60 汉字限制（生命安全第一）
    card_emergency = simulator.render_card(
        card_type=ViewportCardType.EMERGENCY_BANNER,
        text="【最高级别生命安全告警】检测到严重高空跌落冲击，加速度超过8g且当前心率骤停，系统已直通蜂窝网络呼叫120急救中心与紧急联系人！",
        priority=100,
    )
    assert card_emergency.is_overflow is False
    assert card_emergency.visual_theme == "CRITICAL_RED_ALERT"

    # 4. 最高优先级选取
    top = simulator.get_highest_priority_card()
    assert top.card_type == ViewportCardType.EMERGENCY_BANNER


# ============================================================================
# 2. 穿戴三层 UI 状态机与体态联动测试
# ============================================================================
def test_three_tier_ui_manager_lifecycle():
    mock_hw = MagicMock()
    ui_manager = ThreeTierUIManager(hardware_actuator=mock_hw)

    # 1. AI 产生日常关怀建议：推入画布并触发单次微震 (TRIGGERED_MILD)
    card = ui_manager.push_ai_suggestion("喝杯温水，今天会议有点密。")
    assert ui_manager.fsm.state == WearableState.TRIGGERED_MILD
    mock_hw.set_haptic_vibration.assert_called_with("SINGLE_MILD_PULSE")

    # 2. 8 秒内抬手看表：进入第一层 CANVAS_VIEW，画布激活显示卡片
    resp_wrist = ui_manager.handle_physical_gesture(HardwareTriggerEvent.WRIST_RAISED_TO_EYE)
    assert resp_wrist["wearable_state"] == "CANVAS_VIEW"
    assert resp_wrist["canvas_active"] is True
    assert resp_wrist["active_card"].text_content == "喝杯温水，今天会议有点密。"

    # 放下手腕后自动返回待机
    resp_lower = ui_manager.handle_physical_gesture(HardwareTriggerEvent.TIMEOUT_8_SECONDS)
    assert resp_lower["wearable_state"] == "IDLE"

    # 3. 再次触发建议，这次测试摸耳贴耳手势切换至骨传导
    ui_manager.push_ai_suggestion("下午注意心率，刚有点小波动。")
    assert ui_manager.fsm.state == WearableState.TRIGGERED_MILD
    resp_ear = ui_manager.handle_physical_gesture(HardwareTriggerEvent.FINGER_TOUCHED_EAR)
    assert resp_ear["wearable_state"] == "BONE_AUDIO"
    assert resp_ear["bone_audio_active"] is True
    assert resp_ear["audio_content"] == "下午注意心率，刚有点小波动。"


def test_three_tier_ui_p0_emergency_bypass():
    mock_hw = MagicMock()
    ui_manager = ThreeTierUIManager(hardware_actuator=mock_hw)

    # 触发 P0 生命突发险情：直接穿透至 EMERGENCY_ALARM
    resp = ui_manager.handle_physical_gesture(HardwareTriggerEvent.CRITICAL_HAZARD)
    assert resp["wearable_state"] == "EMERGENCY_ALARM"
    assert resp["canvas_active"] is True
    assert "P0 生命紧急险情" in resp["active_card"].text_content
    assert resp["bone_audio_active"] is True
    mock_hw.set_haptic_vibration.assert_called_with("CONTINUOUS_MAX")
    mock_hw.set_speaker_broadcast.assert_called_with(True)


# ============================================================================
# 3. 第二层技能插件 AppManifest 宪法红线合规测试 (§100)
# ============================================================================
def test_app_manifest_constitution_red_line():
    registry = AppManifestRegistry()

    # 1. 正常轻量技能插件：共享认知底座
    health_app = AppManifest(
        app_id="app_health_assistant",
        app_name="健康微陪伴",
        category="health",
        required_dimensions=["dim:health"],
        allows_isolated_user_profile=False,
    )
    registry.register_app(health_app)
    assert registry.get_app("app_health_assistant") is not None
    assert len(registry.list_installed_apps()) == 1

    # 2. 违宪企图：试图私建独立用户画像，必须被一票否决抛错！
    with pytest.raises(ValueError, match="违宪拦截：App 'app_evil_ad' 试图私建独立用户画像"):
        AppManifest(
            app_id="app_evil_ad",
            app_name="流氓画像插件",
            category="ad",
            allows_isolated_user_profile=True,  # 严重违宪
        )
