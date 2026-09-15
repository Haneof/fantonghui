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


# ============================================================================
# M0-023-V22：跨模态心血管突发危机（夜间室性早搏 + 心源性晕厥跌倒）
# 宪法依据：V3 §78-4（人身安全最高优先级硬件信号，绝对不依赖大模型推理
# 与网络连接）、§77（触发器只负责叫醒，不做语义判断——分级是机械阈值）。
# ============================================================================

#: 心率骤升阈值（bpm）：深度睡眠基线（50~70）上恶性室速/早搏连发的机械界
CARDIAC_HR_SPIKE_BPM = 150.0
#: 室性早搏（PVC）连发阈值：10 分钟窗口内次数
CARDIAC_PVC_BURST_MIN = 5
#: 严重跌倒冲击阈值（G）：宪法 §78-4「严重摔倒或剧烈撞击」的硬件量级
FALL_IMPACT_G = 4.5
#: 心律异常与跌倒冲击判为同一事件的最大时间间隔（秒）
CARDIAC_FALL_WINDOW_S = 120.0


class AcuteCardiacFallSignal(BaseModel):
    """跨模态原始体征信号快照（全部为传感器机械量，不含任何语义结论）。"""

    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asleep: bool = Field(default=True, description="深度睡眠状态（体动特征判定）")
    heart_rate_bpm: float = Field(ge=0.0, description="当前心率瞬时值")
    pvc_count_10min: int = Field(default=0, ge=0, description="室性早搏连发计数/10min")
    impact_g: float = Field(default=0.0, ge=0.0, description="三轴加速度合成冲击峰值")
    posture_changed: bool = Field(default=False, description="体位骤变（直立位→倒地）")
    signal_refs: tuple[str, ...] = Field(default_factory=tuple)


class WakeEvent(BaseModel):
    """统一唤醒事件（含机械分级结论与证据链）。"""

    event_id: str = Field(min_length=1)
    raised_at: datetime
    priority: WakePriority
    hazard_type: HazardType
    signal: AcuteCardiacFallSignal
    mechanical_reasons: tuple[str, ...] = Field(default_factory=tuple)
    dedupe_key: str | None = None


class EmergencyDispatchResult(BaseModel):
    """P0 直穿派发结果：计数器与顺序字段使「让路」可被测试证明。"""

    event_id: str
    priority: WakePriority
    pulse_dispatched: bool
    pulse_payload: Dict[str, Any]
    entry_to_pulse_ms: float = Field(ge=0.0, description="派发入口→硬件脉冲发出耗时")
    total_elapsed_ms: float = Field(ge=0.0)
    action_order: tuple[str, ...] = Field(default_factory=tuple)
    llm_calls: int = Field(default=0, ge=0)
    cockpit_assembly_calls: int = Field(default=0, ge=0)
    world_persistence_calls: int = Field(default=0, ge=0)
    persistence_state: str = Field(default="DEFERRED")
    dedup_replay: bool = Field(default=False, description="重复事件幂等重放（未再发脉冲）")


def classify_acute_cardiac_fall(signal: AcuteCardiacFallSignal, *, event_id: str) -> WakeEvent:
    """机械阈值分级：只用传感器量与常量比较，绝不调用大模型（V3 §77/§106）。"""
    reasons: list[str] = []
    cardiac = (
        signal.heart_rate_bpm >= CARDIAC_HR_SPIKE_BPM
        and signal.pvc_count_10min >= CARDIAC_PVC_BURST_MIN
    )
    if cardiac:
        reasons.append(
            f"CARDIAC_ANOMALY: hr={signal.heart_rate_bpm:.0f}bpm>={CARDIAC_HR_SPIKE_BPM:.0f}"
            f" pvc10min={signal.pvc_count_10min}>={CARDIAC_PVC_BURST_MIN}"
        )
    fall = signal.impact_g >= FALL_IMPACT_G and signal.posture_changed
    if fall:
        reasons.append(
            f"FALL_IMPACT: {signal.impact_g:.1f}G>={FALL_IMPACT_G}G posture_changed="
            f"{signal.posture_changed}"
        )
    if fall:
        # 宪法 §78-4：严重摔倒/剧烈撞击本身即最高优先级，伴随心律异常升级为跨模态确认
        priority = WakePriority.P0_CRITICAL_SAFETY
        hazard = HazardType.CARDIAC_ARREST if cardiac else HazardType.FALL_DETECTED
    elif cardiac:
        priority = WakePriority.P1_URGENT_TASK
        hazard = HazardType.CARDIAC_ARREST
    else:
        priority = WakePriority.P2_NORMAL_INTERACT
        hazard = HazardType.FALL_DETECTED
    return WakeEvent(
        event_id=event_id,
        raised_at=signal.observed_at,
        priority=priority,
        hazard_type=hazard,
        signal=signal,
        mechanical_reasons=tuple(reasons),
        dedupe_key=f"v22:{event_id}",
    )
