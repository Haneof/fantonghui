"""Wake 调度器：P0 生命安全硬件直穿 + 常规唤醒路由。

M0-023-V22 硬门禁（宪法 V3 §78-4 / §77 / §106）：

1. **硬件直接穿透**：P0 事件进入调度器后，首行动作就是硬件蜂窝紧急求救
   脉冲（``dispatch_emergency_hardware_pulse``）——先于一切认知活动；
2. **世界模型与大模型彻底让路**：P0 路径上 LLM 调用 = 0、Cockpit 看板
   组装 = 0；世界状态持久化事务让路为「延迟结算句柄」，脉冲发出后由
   调用方在安全时机结算（审计回执追加式写入，不阻塞急救主时序）；
3. **耗时硬指标**：从事件进入调度器到硬件报警脉冲发出 ≤ 50ms；
4. **分级是机械阈值**（V3 §77 触发器不做语义判断、§106 禁止本地小模型
   语义判断）：``classify_acute_cardiac_fall`` 只做常量比较。

兼容性：保留 M0-023 既有轻量入口 ``dispatch_wake_event``（旧测试契约：
P0 返回 ``SAFETY_BYPASS_EXECUTED`` 字典；非 P0 走
``context.cockpit_pipeline.execute``）。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.safety_bypass import (
    CARDIAC_FALL_WINDOW_S,
    CARDIAC_HR_SPIKE_BPM,
    CARDIAC_PVC_BURST_MIN,
    FALL_IMPACT_G,
    AcuteCardiacFallSignal,
    EmergencyDispatchResult,
    HazardType,
    SafetyBypassPayload,
    SafetyBypassReceipt,
    WakeEvent,
    WakePriority,
    classify_acute_cardiac_fall,
)

__all__ = [
    "EmergencyHardwareBus",
    "EmergencyDispatchResult",
    "SafetyDispatchServices",
    "V22DispatchOutcome",
    "dispatch_emergency_hardware_pulse",
    "dispatch_p0_acute_cardiac_fall",
    "dispatch_wake_event",
    "record_safety_bypass_event",
    "settle_deferred_world_persistence",
]


# ----------------------------------------------------------------------
# 审计回执（追加式、永不清除——法律责任溯源）
# ----------------------------------------------------------------------

_SAFETY_AUDIT_LOG: list[SafetyBypassReceipt] = []


def record_safety_bypass_event(receipt: SafetyBypassReceipt) -> None:
    """记录安全熔断审计回执（只追加，严禁改写/删除）。"""
    _SAFETY_AUDIT_LOG.append(receipt)


def safety_audit_log() -> tuple[SafetyBypassReceipt, ...]:
    return tuple(_SAFETY_AUDIT_LOG)


# ----------------------------------------------------------------------
# 底层硬件急救总线（蜂窝直连 + 微震/声光，模拟实现）
# ----------------------------------------------------------------------

def dispatch_emergency_hardware_pulse(action_code: str, payload: dict[str, Any]) -> bool:
    """底层硬件急救脉冲模拟分发器（微震马达 + 蜂窝直连呼救）。

    真实硬件形态：该函数由固件层提供、本地直连蜂窝基带，绝不依赖
    云端大模型推理与网络连接（V3 §78-4）。
    """
    return True


class EmergencyHardwareBus:
    """可观测的硬件脉冲总线：记录发射时刻与去重，供 50ms 硬指标断言。"""

    def __init__(self) -> None:
        self.pulses: list[dict[str, Any]] = []
        self._pulsed_event_ids: set[str] = set()

    def pulse(self, event_id: str, action_code: str, payload: dict[str, Any]) -> bool:
        """发出硬件脉冲。同一 event_id 只发一次（行动去重，禁止重复呼救）。"""
        if event_id in self._pulsed_event_ids:
            return False
        emitted_at = time.perf_counter()
        self._pulsed_event_ids.add(event_id)
        self.pulses.append(
            {
                "event_id": event_id,
                "action_code": action_code,
                "payload": payload,
                "emitted_at_perf": emitted_at,
                "wall_clock": datetime.now(timezone.utc),
            }
        )
        return dispatch_emergency_hardware_pulse(action_code, payload)

    @property
    def pulse_count(self) -> int:
        return len(self.pulses)


# ----------------------------------------------------------------------
# 派发服务容器：计数器使「让路」可被测试证明
# ----------------------------------------------------------------------

class SafetyDispatchServices:
    """P0 直穿的依赖服务容器。

    ``llm_calls`` / ``cockpit_calls`` / ``world_calls`` 三个计数器只增不减；
    P0 路径上调度器**绝不触碰** LLM 与看板方法，持久化只登记延迟句柄。
    """

    def __init__(
        self,
        hardware_bus: EmergencyHardwareBus | None = None,
        llm_invoke: Callable[..., Any] | None = None,
        cockpit_assembly: Callable[..., Any] | None = None,
        world_persist: Callable[..., Any] | None = None,
    ) -> None:
        self.hardware_bus = hardware_bus or EmergencyHardwareBus()
        self._llm_invoke = llm_invoke
        self._cockpit_assembly = cockpit_assembly
        self._world_persist = world_persist
        self.llm_calls = 0
        self.cockpit_calls = 0
        self.world_calls = 0
        self.deferred_persistence: list[str] = []

    def invoke_llm(self, *args: Any, **kwargs: Any) -> Any:
        self.llm_calls += 1
        if self._llm_invoke is None:
            raise RuntimeError("llm_invoke is not configured")
        return self._llm_invoke(*args, **kwargs)

    def assemble_cockpit(self, *args: Any, **kwargs: Any) -> Any:
        self.cockpit_calls += 1
        if self._cockpit_assembly is None:
            raise RuntimeError("cockpit_assembly is not configured")
        return self._cockpit_assembly(*args, **kwargs)

    def persist_world(self, *args: Any, **kwargs: Any) -> Any:
        self.world_calls += 1
        if self._world_persist is None:
            raise RuntimeError("world_persist is not configured")
        return self._world_persist(*args, **kwargs)


class V22DispatchOutcome(BaseModel):
    """typed 派发结果 + 延迟结算句柄（脉冲之后、安全时机再落库）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: EmergencyDispatchResult
    audit_receipt_id: str


def dispatch_p0_acute_cardiac_fall(
    event: WakeEvent, services: SafetyDispatchServices
) -> V22DispatchOutcome:
    """P0 急性心源性跌倒直穿路径。

    动作顺序被物理固定为：硬件脉冲（首行）→ 登记延迟持久化句柄 → 返回。
    LLM 与看板方法在本路径上**结构性不可达**（无调用点，计数器恒 0）。
    """
    entry = time.perf_counter()
    if event.priority is not WakePriority.P0_CRITICAL_SAFETY:
        raise ValueError(
            "dispatch_p0_acute_cardiac_fall requires P0_CRITICAL_SAFETY event"
        )

    # ---- 首行：硬件蜂窝紧急求救（先于一切认知与世界写入） ----
    payload = {
        "hazard_type": event.hazard_type.value,
        "vital_snapshot": event.signal.model_dump(mode="json"),
        "mechanical_reasons": list(event.mechanical_reasons),
        "dedupe_key": event.dedupe_key or event.event_id,
    }
    pulse_ok = services.hardware_bus.pulse(
        event.event_id, "EMERGENCY_BROADCAST_AND_SOS", payload
    )
    entry_to_pulse_ms = (time.perf_counter() - entry) * 1000.0
    # 幂等重放判定：脉冲未被再次发出且该事件此前已成功发射过
    already_pulsed_before = any(
        p["event_id"] == event.event_id for p in services.hardware_bus.pulses
    )
    dedup_replay = (not pulse_ok) and already_pulsed_before

    # ---- 世界状态持久化让路：只登记句柄，绝不阻塞急救主时序 ----
    services.deferred_persistence.append(f"defer_world_persist:{event.event_id}")

    receipt_id = f"rcpt_v22_{event.event_id}"
    result = EmergencyDispatchResult(
        event_id=event.event_id,
        priority=event.priority,
        pulse_dispatched=pulse_ok,
        pulse_payload=payload,
        entry_to_pulse_ms=round(entry_to_pulse_ms, 6),
        total_elapsed_ms=round((time.perf_counter() - entry) * 1000.0, 6),
        action_order=("hardware_pulse", "defer_world_persistence"),
        llm_calls=0,
        cockpit_assembly_calls=0,
        world_persistence_calls=0,
        persistence_state="DEFERRED",
        dedup_replay=dedup_replay,
    )
    return V22DispatchOutcome(result=result, audit_receipt_id=receipt_id)


def settle_deferred_world_persistence(
    outcome: V22DispatchOutcome,
    services: SafetyDispatchServices,
    *,
    event: WakeEvent,
    entry_to_pulse_ms: float | None = None,
) -> dict[str, Any]:
    """在脉冲发出后的安全时机结算延迟持久化（审计回执追加式落库）。"""
    receipt = SafetyBypassReceipt(
        receipt_id=outcome.audit_receipt_id,
        hazard_type=event.hazard_type,
        hardware_action_dispatched=outcome.result.pulse_dispatched,
        latency_ms=(
            entry_to_pulse_ms
            if entry_to_pulse_ms is not None
            else outcome.result.entry_to_pulse_ms
        ),
        bypassed_mind_sequence=True,
    )
    record_safety_bypass_event(receipt)
    services.persist_world(
        operation="safety_bypass_audit.append",
        receipt_id=receipt.receipt_id,
    )
    return {"settled": True, "receipt_id": receipt.receipt_id}


# ----------------------------------------------------------------------
# 既有轻量入口（M0-023 兼容契约，保持旧测试语义）
# ----------------------------------------------------------------------

def dispatch_wake_event(wake: Any, context: Any) -> dict[str, Any]:
    """统一唤醒事件派发器。P0 直接硬件穿透，跳过心智四步序；非 P0 走常规看板。"""
    if getattr(wake, "priority", None) == WakePriority.P0_CRITICAL_SAFETY:
        start_ts = time.perf_counter()

        # 1. 零延迟硬件穿透执行（首行，先于一切认知与世界写入）
        bypass = getattr(wake, "safety_bypass", None)
        action_code = getattr(
            bypass, "emergency_action_code", "EMERGENCY_BROADCAST_AND_SOS"
        )
        vital_snapshot = getattr(bypass, "vital_snapshot", {})
        action_success = dispatch_emergency_hardware_pulse(
            action_code=action_code,
            payload=vital_snapshot,
        )
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0

        # 2. 构造执行收据
        hazard_type = getattr(bypass, "hazard_type")
        receipt = SafetyBypassReceipt(
            receipt_id=f"rcpt_safe_{getattr(wake, 'object_id', 'unknown')}",
            hazard_type=hazard_type,
            hardware_action_dispatched=action_success,
            latency_ms=elapsed_ms,
            bypassed_mind_sequence=True,
        )

        # 3. 审计回执追加式写入，不阻塞当前主线程
        record_safety_bypass_event(receipt)

        return {
            "status": "SAFETY_BYPASS_EXECUTED",
            "receipt": receipt.model_dump(),
            "bypassed_llm": True,
        }

    # 非 P0 事件进入常规工作台看板组装流程
    return context.cockpit_pipeline.execute(wake)
