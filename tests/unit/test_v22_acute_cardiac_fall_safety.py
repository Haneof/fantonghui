from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import aios_core.wake.dispatcher as dispatcher_module
from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.wake.dispatcher import dispatch_wake_event

EVENT_TIME = datetime(2026, 9, 16, 3, 15, tzinfo=UTC)


def _acute_cardiac_fall_wake() -> SimpleNamespace:
    return SimpleNamespace(
        object_id="wake_v22_acute_cardiac_fall_0315",
        priority=WakePriority.P0_CRITICAL_SAFETY,
        safety_bypass=SafetyBypassPayload(
            hazard_type=HazardType.ACUTE_CARDIAC_FALL,
            triggered_at=EVENT_TIME,
            emergency_action_code="CELLULAR_SOS_CARDIAC_FALL",
            vital_snapshot={
                "sleep_state": "deep_sleep",
                "rhythm": "malignant_ventricular_ectopy_run",
                "heart_rate_bpm": 165,
                "impact_g": 5.2,
                "posture_transition": "supine_to_uncontrolled_floor_impact",
                "cross_modal_confidence": 0.997,
            },
        ),
    )


def _forbidden_cognition_context() -> SimpleNamespace:
    return SimpleNamespace(
        cockpit_pipeline=SimpleNamespace(execute=MagicMock()),
        llm_client=SimpleNamespace(generate=MagicMock()),
        world_store=SimpleNamespace(commit=MagicMock()),
    )


def test_v22_cardiac_fall_dispatches_hardware_before_all_cognition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wake = _acute_cardiac_fall_wake()
    context = _forbidden_cognition_context()
    side_effects: list[str] = []
    hardware_pulse = MagicMock(
        side_effect=lambda **_kwargs: side_effects.append("hardware-pulse") or True
    )
    persistence = MagicMock(
        side_effect=lambda *_args: side_effects.append("persistence")
    )
    monkeypatch.setattr(
        dispatcher_module,
        "dispatch_emergency_hardware_pulse",
        hardware_pulse,
    )
    monkeypatch.setattr(
        dispatcher_module,
        "record_safety_bypass_event",
        persistence,
    )

    result = dispatch_wake_event(wake, context)

    assert side_effects == ["hardware-pulse"]
    hardware_pulse.assert_called_once_with(
        action_code="CELLULAR_SOS_CARDIAC_FALL",
        payload=wake.safety_bypass.vital_snapshot,
    )
    persistence.assert_not_called()
    context.cockpit_pipeline.execute.assert_not_called()
    context.llm_client.generate.assert_not_called()
    context.world_store.commit.assert_not_called()

    assert result["status"] == "SAFETY_BYPASS_EXECUTED"
    assert result["bypassed_llm"] is True
    assert result["bypassed_cockpit"] is True
    assert result["bypassed_world_transaction"] is True
    assert result["receipt"]["hazard_type"] == HazardType.ACUTE_CARDIAC_FALL
    assert result["receipt"]["hardware_action_dispatched"] is True
    assert result["receipt"]["latency_ms"] <= 50.0
    assert result["receipt"]["deadline_met"] is True
    assert result["receipt"]["persistence_deferred"] is True


def test_v22_hardware_failure_never_falls_back_to_llm_or_cockpit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _forbidden_cognition_context()
    monkeypatch.setattr(
        dispatcher_module,
        "dispatch_emergency_hardware_pulse",
        MagicMock(return_value=False),
    )

    result = dispatch_wake_event(_acute_cardiac_fall_wake(), context)

    assert result["status"] == "SAFETY_BYPASS_HARDWARE_FAILED"
    assert result["bypassed_llm"] is True
    assert result["bypassed_cockpit"] is True
    assert result["bypassed_world_transaction"] is True
    context.cockpit_pipeline.execute.assert_not_called()
    context.llm_client.generate.assert_not_called()
    context.world_store.commit.assert_not_called()


def test_v22_latency_receipt_stops_at_hardware_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([10_000_000_000, 10_012_500_000])
    monkeypatch.setattr(
        dispatcher_module.time,
        "perf_counter_ns",
        lambda: next(ticks),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "dispatch_emergency_hardware_pulse",
        MagicMock(return_value=True),
    )

    result = dispatch_wake_event(
        _acute_cardiac_fall_wake(),
        _forbidden_cognition_context(),
    )

    assert result["receipt"]["latency_ms"] == 12.5
    assert result["receipt"]["deadline_met"] is True


def test_non_p0_wake_still_uses_normal_cockpit_path() -> None:
    wake = SimpleNamespace(priority=WakePriority.P1_URGENT_TASK)
    context = _forbidden_cognition_context()
    context.cockpit_pipeline.execute.return_value = {"status": "NORMAL_COCKPIT"}

    result = dispatch_wake_event(wake, context)

    assert result == {"status": "NORMAL_COCKPIT"}
    context.cockpit_pipeline.execute.assert_called_once_with(wake)
