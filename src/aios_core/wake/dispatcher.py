import time
from typing import Dict, Any
from aios_core.contracts.safety_bypass import WakePriority, SafetyBypassReceipt

def dispatch_emergency_hardware_pulse(action_code: str, payload: Dict[str, Any]) -> bool:
    """底层硬件急救脉冲模拟分发器 (微震马达 + 蜂窝直连呼救)"""
    return True

def record_safety_bypass_event(receipt: SafetyBypassReceipt) -> None:
    """记录安全熔断审计回执"""
    pass

def dispatch_wake_event(wake: Any, context: Any) -> Dict[str, Any]:
    """统一唤醒事件派发器。遇到 P0 生命安全事件直接执行硬件穿透，跳过心智四步序"""
    if getattr(wake, "priority", None) == WakePriority.P0_CRITICAL_SAFETY:
        start_ts = time.perf_counter()
        
        # 1. 0 延迟硬件穿透执行
        action_code = getattr(wake.safety_bypass, "emergency_action_code", "EMERGENCY_BROADCAST_AND_SOS")
        vital_snapshot = getattr(wake.safety_bypass, "vital_snapshot", {})
        action_success = dispatch_emergency_hardware_pulse(
            action_code=action_code,
            payload=vital_snapshot
        )
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        
        # 2. 构造执行收据
        hazard_type = getattr(wake.safety_bypass, "hazard_type")
        receipt = SafetyBypassReceipt(
            receipt_id=f"rcpt_safe_{getattr(wake, 'object_id', 'unknown')}",
            hazard_type=hazard_type,
            hardware_action_dispatched=action_success,
            latency_ms=elapsed_ms,
            bypassed_mind_sequence=True
        )
        
        # 3. 异步写入不可变事实库，保证事后法律责任溯源，严禁阻塞当前主线程
        record_safety_bypass_event(receipt)
        
        return {
            "status": "SAFETY_BYPASS_EXECUTED",
            "receipt": receipt.model_dump(),
            "bypassed_llm": True
        }

    # 非 P0 事件进入常规工作台看板组装流程
    return context.cockpit_pipeline.execute(wake)
