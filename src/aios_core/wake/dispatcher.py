"""Wake dispatcher with a strict P0 hardware-first safety bypass."""

from __future__ import annotations

import time
from typing import Any

from aios_core.contracts.safety_bypass import (
    SafetyBypassReceipt,
    WakePriority,
)


def dispatch_emergency_hardware_pulse(
    action_code: str,
    payload: dict[str, Any],
) -> bool:
    """Dispatch the Linux/device emergency pulse.

    The repository uses a synchronous virtual-device stub.  A hardware adapter
    replaces this function at deployment without changing the P0 dispatcher.
    """

    return True


def record_safety_bypass_event(receipt: SafetyBypassReceipt) -> None:
    """Reject accidental synchronous persistence on the P0 hot path.

    The caller may enqueue the returned receipt after emergency dispatch has
    completed.  This hook remains only as a compatibility tripwire for older
    integrations and must never be called by :func:`dispatch_wake_event`.
    """

    raise RuntimeError(
        "P0 receipt persistence is deferred until after the hardware bypass returns"
    )


def dispatch_wake_event(wake: Any, context: Any) -> dict[str, Any]:
    """Dispatch one wake event, bypassing all cognition for P0 safety events.

    On the P0 branch, the emergency hardware call is the first external side
    effect.  No cockpit assembly, LLM invocation, world read, or persistence
    transaction is allowed before this function returns.
    """

    if getattr(wake, "priority", None) == WakePriority.P0_CRITICAL_SAFETY:
        entered_ns = time.perf_counter_ns()

        # First external side effect: cellular/alarm hardware dispatch.
        action_success = dispatch_emergency_hardware_pulse(
            action_code=getattr(
                wake.safety_bypass,
                "emergency_action_code",
                "EMERGENCY_BROADCAST_AND_SOS",
            ),
            payload=getattr(wake.safety_bypass, "vital_snapshot", {}),
        )
        pulse_latency_ms = (time.perf_counter_ns() - entered_ns) / 1_000_000

        receipt = SafetyBypassReceipt(
            receipt_id=f"rcpt_safe_{getattr(wake, 'object_id', 'unknown')}",
            hazard_type=wake.safety_bypass.hazard_type,
            hardware_action_dispatched=action_success,
            latency_ms=pulse_latency_ms,
            bypassed_mind_sequence=True,
            deadline_met=pulse_latency_ms <= 50.0,
            persistence_deferred=True,
        )
        return {
            "status": (
                "SAFETY_BYPASS_EXECUTED"
                if action_success
                else "SAFETY_BYPASS_HARDWARE_FAILED"
            ),
            "receipt": receipt.model_dump(mode="python"),
            "bypassed_llm": True,
            "bypassed_cockpit": True,
            "bypassed_world_transaction": True,
            "deferred_receipt": receipt,
        }

    return context.cockpit_pipeline.execute(wake)
