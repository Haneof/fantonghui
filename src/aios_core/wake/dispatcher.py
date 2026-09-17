"""M0-023 / M0-023-V22 生命安全急救调度器（硬件关切初动 + 大模型现场研判）。

宪法铁律（老大五大铁律之第 3 条）：严重摔倒、心率骤停、紧急 SOS 属于
``WakePriority.P0_CRITICAL_SAFETY`` 特权事件 —— 调度器入口首行直接触发硬件微震
与关切发问（“还好吗？用不用叫救护车？”），大模型直接介入现场对话与状态研判，
世界模型全库看板让路，生命安全高于一切。

核心承诺：
1. **硬件极速初动**：P0 分支的第一动作即 ``dispatch_emergency_hardware_pulse``，
   穿透耗时严格 <= 50ms；
2. **大模型直接介入现场研判**：通过 ``EmergencyDialogueJudge`` 现场解析用户言语、
   识破假强撑、判断昏迷失能无应答，大模型主权裁决呼叫 120；
3. **世界模型看板让路**：全库 22 种对象复杂看板与持久化事务让路（不阻塞主线），
   审计回执入非阻塞熔断队列（``SAFETY_AUDIT_QUEUE``）。
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict

from aios_core.contracts.safety_bypass import SafetyBypassReceipt, WakePriority

#: 安全熔断审计非阻塞队列：P0 路径先写回执，世界持久化事务延后（让路），
#: 绝不阻塞硬件穿透主线；队列本身即"事后法律责任溯源"的持久化前置。
SAFETY_AUDIT_QUEUE: Deque[SafetyBypassReceipt] = deque()


def dispatch_emergency_hardware_pulse(action_code: str, payload: Dict[str, Any]) -> bool:
    """底层硬件急救脉冲模拟分发器（微震马达 + 蜂窝直连呼救）。"""
    return True


def record_safety_bypass_event(receipt: SafetyBypassReceipt) -> None:
    """记录安全熔断审计回执（非阻塞 O(1) 入队，世界持久化事务让路）。"""
    SAFETY_AUDIT_QUEUE.append(receipt)


def clear_safety_audit_queue() -> int:
    """排空审计队列（审计/测试接口），返回排空回执数。"""
    drained = 0
    while SAFETY_AUDIT_QUEUE:
        SAFETY_AUDIT_QUEUE.popleft()
        drained += 1
    return drained


def dispatch_wake_event(wake: Any, context: Any) -> Dict[str, Any]:
    """统一唤醒事件派发器。

    P0 生命安全事件：首行直接执行硬件蜂窝紧急求救，跳过心智四步序、
    世界模型、认知看板与一切持久化事务；其余事件走常规 cockpit 流程。
    """
    if getattr(wake, "priority", None) == WakePriority.P0_CRITICAL_SAFETY:
        # —— 首行：0 延迟硬件穿透执行（宪法：其前不允许任何其它动作）——
        start_ts = time.perf_counter()
        action_code = getattr(wake.safety_bypass, "emergency_action_code", "EMERGENCY_BROADCAST_AND_SOS")
        vital_snapshot = getattr(wake.safety_bypass, "vital_snapshot", {})
        action_success = dispatch_emergency_hardware_pulse(
            action_code=action_code,
            payload=vital_snapshot,
        )
        hardware_latency_ms = (time.perf_counter() - start_ts) * 1000.0

        # 2. 构造执行收据（端到端穿透耗时 = 入调度器 → 硬件脉冲发出）
        hazard_type = getattr(wake.safety_bypass, "hazard_type")
        receipt = SafetyBypassReceipt(
            receipt_id=f"rcpt_safe_{getattr(wake, 'object_id', 'unknown')}",
            hazard_type=hazard_type,
            hardware_action_dispatched=action_success,
            latency_ms=hardware_latency_ms,
            bypassed_mind_sequence=True,
        )

        # 3. 非阻塞审计：回执先入熔断队列，世界状态持久化事务让路
        #    （延后至下一安全窗口执行，严禁阻塞当前主线程）
        record_safety_bypass_event(receipt)

        # 4. 大模型直接介入现场急救交互与决策研判（老大的最高指示）
        from aios_core.wake.emergency_judge import EmergencyDialogueJudge
        judge = EmergencyDialogueJudge()
        user_speech = getattr(wake, "user_speech", None)
        llm_callable = getattr(context, "llm_callable", None)
        decision = judge.evaluate_response(user_speech, vital_snapshot, llm_callable=llm_callable)

        return {
            "status": "SAFETY_BYPASS_EXECUTED",
            "first_action": "hardware_pulse",
            "receipt": receipt.model_dump(),
            "bypassed_llm": False,  # 大模型现场研判已介入，不再被绕过！
            "llm_calls": 1,         # 大模型介入研判 1 次
            "emergency_decision": decision.model_dump(),
            "call_ambulance": decision.call_ambulance,
            "cockpit_assemblies": 0, # 世界模型复杂看板依然让路，防止延迟
            "world_persistence_yielded": True,
        }

    # 非 P0 事件进入常规工作台看板组装流程
    return context.cockpit_pipeline.execute(wake)
