from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class WakePriority(str, Enum):
    P0_CRITICAL_SAFETY = "P0_CRITICAL_SAFETY"  # 生命安全急救特权 (0 延迟心智熔断)
    P1_URGENT_TASK     = "P1_URGENT_TASK"      # 强时效突发任务
    P2_NORMAL_INTERACT = "P2_NORMAL_INTERACT"   # 正常日常交互/微震提示
    P3_BACKGROUND_TICK = "P3_BACKGROUND_TICK"  # 后台静默时钟与巡检

class HazardType(str, Enum):
    FALL_DETECTED       = "FALL_DETECTED"       # 严重跌倒与强撞击 (G-force > 4.5G)
    CARDIAC_ARREST      = "CARDIAC_ARREST"      # 心率骤停或恶性心律失常
    ACUTE_HYPOXIA       = "ACUTE_HYPOXIA"       # 急性重度缺氧 (SpO2 < 80%)
    MANUAL_SOS_HELD     = "MANUAL_SOS_HELD"     # 侧键长按 3 秒紧急呼救

class SafetyBypassPayload(BaseModel):
    is_safety_bypass: bool = Field(default=True, description="熔断标志")
    hazard_type: HazardType = Field(..., description="险情类型")
    vital_snapshot: Dict[str, Any] = Field(default_factory=dict, description="心率、加速度传感器原始突变快照")
    emergency_action_code: str = Field(default="EMERGENCY_BROADCAST_AND_SOS", description="急救硬件指令码")
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SafetyBypassReceipt(BaseModel):
    receipt_id: str
    hazard_type: HazardType
    hardware_action_dispatched: bool
    latency_ms: float
    bypassed_mind_sequence: bool = True
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
