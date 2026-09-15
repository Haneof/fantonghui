import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from aios_core.contracts.safety_bypass import WakePriority, HazardType, SafetyBypassPayload
from aios_core.wake.dispatcher import dispatch_wake_event

def test_p0_safety_bypass_execution_latency_and_llm_exemption():
    # 模拟外部 P0 跌倒事件
    mock_wake = MagicMock()
    mock_wake.object_id = "wake_test_001"
    mock_wake.priority = WakePriority.P0_CRITICAL_SAFETY
    mock_wake.safety_bypass = SafetyBypassPayload(
        hazard_type=HazardType.FALL_DETECTED,
        vital_snapshot={"g_force": 4.8, "heart_rate": 142}
    )
    
    mock_context = MagicMock()
    
    # 执行调度
    result = dispatch_wake_event(mock_wake, mock_context)
    
    # 断言 1：必须确认熔断旁路执行成功
    assert result["status"] == "SAFETY_BYPASS_EXECUTED"
    assert result["bypassed_llm"] is True
    
    # 断言 2：调度器穿透延迟严格 <= 50ms
    assert result["receipt"]["latency_ms"] <= 50.0
    
    # 断言 3：心智四步序大模型工作台被调用次数必须严格为 0！
    mock_context.cockpit_pipeline.execute.assert_not_called()
