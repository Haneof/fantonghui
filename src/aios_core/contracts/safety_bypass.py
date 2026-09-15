"""P0 safety-bypass contracts shared by wake dispatch and virtual devices."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aios_core.contracts.time import require_aware, utc_now


class WakePriority(StrEnum):
    P0_CRITICAL_SAFETY = "P0_CRITICAL_SAFETY"
    P1_URGENT_TASK = "P1_URGENT_TASK"
    P2_NORMAL_INTERACT = "P2_NORMAL_INTERACT"
    P3_BACKGROUND_TICK = "P3_BACKGROUND_TICK"


class HazardType(StrEnum):
    FALL_DETECTED = "FALL_DETECTED"
    CARDIAC_ARREST = "CARDIAC_ARREST"
    ACUTE_CARDIAC_FALL = "ACUTE_CARDIAC_FALL"
    ACUTE_HYPOXIA = "ACUTE_HYPOXIA"
    MANUAL_SOS_HELD = "MANUAL_SOS_HELD"


class SafetyBypassPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    is_safety_bypass: Literal[True] = True
    hazard_type: HazardType
    vital_snapshot: dict[str, Any] = Field(default_factory=dict)
    emergency_action_code: str = Field(
        default="EMERGENCY_BROADCAST_AND_SOS",
        min_length=1,
        max_length=160,
    )
    triggered_at: datetime = Field(default_factory=utc_now)

    @field_validator("triggered_at")
    @classmethod
    def triggered_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "triggered_at")
        return value


class SafetyBypassReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    receipt_id: str = Field(min_length=1, max_length=200)
    hazard_type: HazardType
    hardware_action_dispatched: bool
    latency_ms: float = Field(ge=0.0)
    bypassed_mind_sequence: Literal[True] = True
    deadline_met: bool = True
    persistence_deferred: Literal[True] = True
    recorded_at: datetime = Field(default_factory=utc_now)

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "recorded_at")
        return value
