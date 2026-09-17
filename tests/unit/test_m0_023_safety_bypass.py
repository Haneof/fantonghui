import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from aios_core.contracts.safety_bypass import WakePriority, HazardType, SafetyBypassPayload
from aios_core.wake.dispatcher import dispatch_wake_event

def test_p0_safety_bypass_execution_latency_and_llm_intervention():
    # 模拟外部 P0 跌倒事件
    mock_wake = MagicMock()
    mock_wake.object_id = "wake_test_001"
    mock_wake.priority = WakePriority.P0_CRITICAL_SAFETY
    mock_wake.safety_bypass = SafetyBypassPayload(
        hazard_type=HazardType.FALL_DETECTED,
        vital_snapshot={"g_force": 4.8, "heart_rate": 142}
    )
    mock_wake.user_speech = "没事不用叫车，我缓一缓就行"
    
    mock_context = MagicMock()
    
    # 执行调度
    result = dispatch_wake_event(mock_wake, mock_context)
    
    # 断言 1：必须确认急救调度执行成功，大模型现场研判已介入
    assert result["status"] == "SAFETY_BYPASS_EXECUTED"
    assert result["bypassed_llm"] is False
    assert result["llm_calls"] == 1
    assert "emergency_decision" in result
    assert result["call_ambulance"] is False  # 用户明确说没事，大模型判定不叫车
    
    # 断言 2：调度器首行动作穿透延迟严格 <= 50ms
    assert result["receipt"]["latency_ms"] <= 50.0
    
    # 断言 3：全库复杂看板让路，不调用常规慢速工作台
    mock_context.cockpit_pipeline.execute.assert_not_called()
