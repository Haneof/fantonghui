"""Wake - 机械触发、去重、队列与 P0 安全直穿调度。禁止语义判断。"""

from .dispatcher import (
    EmergencyHardwareBus,
    SafetyDispatchServices,
    V22DispatchOutcome,
    dispatch_emergency_hardware_pulse,
    dispatch_p0_acute_cardiac_fall,
    dispatch_wake_event,
    record_safety_bypass_event,
    safety_audit_log,
    settle_deferred_world_persistence,
)

__all__ = [
    "EmergencyHardwareBus",
    "SafetyDispatchServices",
    "V22DispatchOutcome",
    "dispatch_emergency_hardware_pulse",
    "dispatch_p0_acute_cardiac_fall",
    "dispatch_wake_event",
    "record_safety_bypass_event",
    "safety_audit_log",
    "settle_deferred_world_persistence",
]
