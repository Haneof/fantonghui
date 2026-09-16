"""M0-023-V22 失败安全硬件直穿入口（独立命名：v22_hardware_first）。

纯增量加固（不修改 dispatcher.py 的 V1 主链，不覆盖任何已交付版本）：

红队审计发现：当 P0 唤醒事件的 ``safety_bypass`` 载荷畸形（缺失或
``hazard_type`` 缺失）时，V1 主链在硬件脉冲发出**之后**构造收据阶段抛出
异常 —— SOS 虽然送达，但审计回执丢失，违反"事后法律责任溯源"要求，
且调用方拿到的是裸异常而非可审计结果。

本入口的生命安全语义（宪法：生命安全高于一切）：

- 任何 P0 事件**必须**先发出硬件脉冲、**必须**返回可审计结果 —— 畸形载荷
  绝不静音 SOS；
- 良构 P0（safety_bypass 完整）→ 委托 V1 ``dispatch_wake_event`` 主链
  （行为与审计队列语义完全保持原样）；
- 畸形 P0（safety_bypass 缺失 / hazard_type 缺失）→ 直接发出默认紧急
  硬件脉冲，返回降级审计（``degraded=True``）：不伪造 hazard_type、
  不向 ``SAFETY_AUDIT_QUEUE`` 注入伪回执，降级事实本身即可审计；
- 非 P0 → 常规 cockpit 流水线（与 V1 语义一致；无 context 时 fail-closed）。
"""
from __future__ import annotations

import time
from typing import Any, Dict

from aios_core.contracts.safety_bypass import WakePriority
from . import dispatcher as _dispatcher

# 注意：脉冲函数经由 dispatcher 模块命名空间**延迟绑定**调用 ——
# 与 V1 主链保持同一调用点，硬件脉冲实现升级/测试 spy 对两条路径同时生效。

__all__ = [
    "safe_dispatch_v22",
]

_DEFAULT_ACTION_CODE = "EMERGENCY_BROADCAST_AND_SOS"


def _safe_attr(obj: Any, name: str, default: Any) -> Any:
    try:
        value = getattr(obj, name, default)
    except Exception:  # 属性访问器抛异常同样不得阻塞 SOS
        return default
    return value


def _dispatch_non_p0(wake: Any, context: Any) -> Dict[str, Any]:
    if context is None or not hasattr(context, "cockpit_pipeline"):
        raise ValueError(
            "non-P0 wake requires a context exposing cockpit_pipeline (fail-closed)"
        )
    return context.cockpit_pipeline.execute(wake)


def _dispatch_malformed_p0(wake: Any) -> Dict[str, Any]:
    """畸形 P0：先脉冲、后降级审计 —— SOS 绝不静音。"""
    entry_ts = time.perf_counter()
    bypass = _safe_attr(wake, "safety_bypass", None)
    action_code = _safe_attr(bypass, "emergency_action_code", _DEFAULT_ACTION_CODE)
    if not isinstance(action_code, str) or not action_code.strip():
        action_code = _DEFAULT_ACTION_CODE
    vital_snapshot = _safe_attr(bypass, "vital_snapshot", None)
    if not isinstance(vital_snapshot, dict):
        vital_snapshot = {}

    dispatched = bool(
        _dispatcher.dispatch_emergency_hardware_pulse(action_code=action_code, payload=vital_snapshot)
    )
    latency_ms = (time.perf_counter() - entry_ts) * 1000.0
    object_id = _safe_attr(wake, "object_id", "unknown")
    return {
        "status": "SAFETY_BYPASS_EXECUTED_DEGRADED",
        "first_action": "hardware_pulse",
        "degraded": True,
        "degradation_reason": "malformed safety_bypass payload (missing or without hazard_type)",
        "hardware_action_dispatched": dispatched,
        "latency_ms": latency_ms,
        "bypassed_llm": True,
        "llm_calls": 0,
        "cockpit_assemblies": 0,
        "world_persistence_yielded": True,
        "audit": {
            "receipt_id": f"rcpt_degraded_{object_id}",
            "hazard_type": None,  # 不伪造险情类型：降级事实本身即审计证据
            "hardware_action_dispatched": dispatched,
            "latency_ms": latency_ms,
        },
    }


def safe_dispatch_v22(wake: Any, context: Any = None) -> Dict[str, Any]:
    """V22 失败安全调度入口：P0 必脉冲、必可审计；非 P0 走常规看板。"""
    if getattr(wake, "priority", None) != WakePriority.P0_CRITICAL_SAFETY:
        return _dispatch_non_p0(wake, context)

    bypass = getattr(wake, "safety_bypass", None)
    hazard_type = getattr(bypass, "hazard_type", None) if bypass is not None else None
    if bypass is None or hazard_type is None:
        return _dispatch_malformed_p0(wake)
    return _dispatcher.dispatch_wake_event(wake, context)
