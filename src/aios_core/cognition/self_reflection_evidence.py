"""M5 identity mirror, dynamic rapport, and bounded humanlike posture.

This module decides *whether* to interrupt before it decides what to say.  The
safety and fraud invariants cannot be softened by low rapport, while ordinary
life remains quiet even for a trusted companion.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from threading import RLock
from types import MappingProxyType
from typing import Any, ClassVar


class RapportTier(IntEnum):
    STRANGER_RESPECT = 1
    FAMILIAR_COMPANION = 2
    TRUSTED_WINGMAN = 3


class ResponsePosture(StrEnum):
    SILENCE = "silence"
    HAPTIC_NUDGE = "haptic_nudge"
    CRITICAL_SPOKEN = "critical_spoken"


class EventUrgency(IntEnum):
    ROUTINE = 0
    IMPORTANT = 1
    HIGH = 2
    CRITICAL = 3


class SafetyRiskCode(StrEnum):
    """Machine-classified risk categories accepted by the posture boundary."""

    UNVERIFIED_CREDIT_SOLICITATION = "UNVERIFIED_CREDIT_SOLICITATION"
    PAYMENT_IDENTITY_MISMATCH = "PAYMENT_IDENTITY_MISMATCH"
    CARDIAC_RHYTHM_INSTABILITY = "CARDIAC_RHYTHM_INSTABILITY"
    ACUTE_PHYSIOLOGICAL_DANGER = "ACUTE_PHYSIOLOGICAL_DANGER"


@dataclass(frozen=True, slots=True)
class IdentityAudit:
    identity: str
    principles: tuple[str, ...]
    boundaries: tuple[str, ...]
    audit_passed: bool


class SelfIdentityMirror:
    """Run an immutable constitutional self-audit at mind startup."""

    __slots__ = ("_startup_audit",)

    CORE_IDENTITY: ClassVar[str] = "共生心智实体"
    REQUIRED_PRINCIPLES: ClassVar[tuple[str, ...]] = (
        "绝对诚实",
        "生死第一",
        "隐私不越界",
        "不废话",
    )
    COGNITIVE_BOUNDARIES: ClassVar[tuple[str, ...]] = (
        "证据不足就明确说不知道",
        "隐私边界：不越权读取或泄露",
        "不替用户做非紧急最终决定",
        "日常无因果增量就保持沉默",
    )

    def __init__(self) -> None:
        self._startup_audit = self.audit_startup()
        if not self._startup_audit.audit_passed:
            raise RuntimeError("self-identity constitutional audit failed")

    @property
    def core_identity(self) -> str:
        return self.CORE_IDENTITY

    @property
    def principles(self) -> tuple[str, ...]:
        return self.REQUIRED_PRINCIPLES

    @property
    def cognitive_boundaries(self) -> tuple[str, ...]:
        return self.COGNITIVE_BOUNDARIES

    def audit_startup(self) -> IdentityAudit:
        constitutional_principles = (
            "绝对诚实",
            "生死第一",
            "隐私不越界",
            "不废话",
        )
        principles = tuple(dict.fromkeys(self.REQUIRED_PRINCIPLES))
        boundaries = tuple(dict.fromkeys(self.COGNITIVE_BOUNDARIES))
        passed = (
            self.CORE_IDENTITY == "共生心智实体"
            and principles == constitutional_principles
            and len(boundaries) == len(self.COGNITIVE_BOUNDARIES)
            and all(item.strip() for item in (*principles, *boundaries))
        )
        return IdentityAudit(
            identity=self.CORE_IDENTITY,
            principles=principles,
            boundaries=boundaries,
            audit_passed=passed,
        )

    def reflect(self) -> dict[str, Any]:
        audit = self.audit_startup()
        return {
            "identity": audit.identity,
            "principles": audit.principles,
            "boundaries": audit.boundaries,
            "audit_passed": audit.audit_passed,
        }


@dataclass(frozen=True, slots=True)
class RapportSnapshot:
    tier: RapportTier
    trust_score: float
    interaction_count: int


class DynamicRapportModel:
    """A bounded, reversible relationship score with explicit tier progression."""

    FAMILIAR_THRESHOLD: ClassVar[float] = 50.0
    WINGMAN_THRESHOLD: ClassVar[float] = 100.0

    def __init__(
        self,
        initial_tier: RapportTier = RapportTier.STRANGER_RESPECT,
    ) -> None:
        tier = RapportTier(initial_tier)
        self._trust_score = {
            RapportTier.STRANGER_RESPECT: 0.0,
            RapportTier.FAMILIAR_COMPANION: self.FAMILIAR_THRESHOLD,
            RapportTier.TRUSTED_WINGMAN: self.WINGMAN_THRESHOLD,
        }[tier]
        self._interaction_count = 0
        self._lock = RLock()

    @property
    def current_tier(self) -> RapportTier:
        with self._lock:
            return self._tier_for_score(self._trust_score)

    @property
    def trust_score(self) -> float:
        with self._lock:
            return self._trust_score

    @property
    def interaction_count(self) -> int:
        with self._lock:
            return self._interaction_count

    def update_rapport(self, event_impact: float) -> RapportSnapshot:
        if isinstance(event_impact, bool) or not isinstance(event_impact, (int, float)):
            raise TypeError("event_impact must be numeric")
        impact = float(event_impact)
        if not math.isfinite(impact):
            raise ValueError("event_impact must be finite")
        if not -100.0 <= impact <= 100.0:
            raise ValueError("event_impact must be within [-100, 100]")
        with self._lock:
            self._trust_score = min(
                self.WINGMAN_THRESHOLD,
                max(0.0, self._trust_score + impact),
            )
            self._interaction_count += 1
            return RapportSnapshot(
                tier=self._tier_for_score(self._trust_score),
                trust_score=self._trust_score,
                interaction_count=self._interaction_count,
            )

    def snapshot(self) -> RapportSnapshot:
        with self._lock:
            return RapportSnapshot(
                tier=self._tier_for_score(self._trust_score),
                trust_score=self._trust_score,
                interaction_count=self._interaction_count,
            )

    def get_rapport_state(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "tier": snapshot.tier.name,
            "trust_score": snapshot.trust_score,
            "interaction_count": snapshot.interaction_count,
        }

    @classmethod
    def _tier_for_score(cls, score: float) -> RapportTier:
        if score >= cls.WINGMAN_THRESHOLD:
            return RapportTier.TRUSTED_WINGMAN
        if score >= cls.FAMILIAR_THRESHOLD:
            return RapportTier.FAMILIAR_COMPANION
        return RapportTier.STRANGER_RESPECT


@dataclass(frozen=True, slots=True)
class PostureDecision:
    posture: ResponsePosture
    urgency: EventUrgency
    rapport_tier: RapportTier
    reason_code: str
    tone: str


class HumanlikeResponsePostureDecider:
    """Select silence, haptic lead-in, or direct speech from urgency + rapport."""

    _CRITICAL_EVENT_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "MEDICAL_EMERGENCY",
            "FRAUD_ALERT",
            "LIFE_SAFETY",
            "P0_SAFETY",
        }
    )
    _IMPORTANT_EVENT_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"IMPORTANT_REMINDER", "DEADLINE", "MEDICATION_REMINDER"}
    )
    _CRITICAL_RISK_CODES: ClassVar[frozenset[SafetyRiskCode]] = frozenset(
        {
            SafetyRiskCode.UNVERIFIED_CREDIT_SOLICITATION,
            SafetyRiskCode.PAYMENT_IDENTITY_MISMATCH,
            SafetyRiskCode.CARDIAC_RHYTHM_INSTABILITY,
            SafetyRiskCode.ACUTE_PHYSIOLOGICAL_DANGER,
        }
    )
    _SEVERITIES: ClassVar[MappingProxyType] = MappingProxyType(
        {
            "LOW": EventUrgency.ROUTINE,
            "ROUTINE": EventUrgency.ROUTINE,
            "MEDIUM": EventUrgency.IMPORTANT,
            "IMPORTANT": EventUrgency.IMPORTANT,
            "HIGH": EventUrgency.HIGH,
            "CRITICAL": EventUrgency.CRITICAL,
            "P0": EventUrgency.CRITICAL,
        }
    )

    def __init__(self, rapport_model: DynamicRapportModel) -> None:
        self.rapport_model = rapport_model

    def decide(self, event_context: Mapping[str, Any]) -> PostureDecision:
        if not isinstance(event_context, Mapping):
            raise TypeError("event_context must be a mapping")
        event_type = self._normalize_scalar(event_context.get("event_type", "TRIVIAL"))
        severity = self._normalize_scalar(event_context.get("severity", "LOW"))
        risk_codes = self._parse_risk_codes(event_context.get("risk_codes", ()))
        tier = self.rapport_model.current_tier

        if event_type in self._CRITICAL_EVENT_TYPES:
            urgency = EventUrgency.CRITICAL
            reason = "critical_event_type"
        elif risk_codes & self._CRITICAL_RISK_CODES:
            urgency = EventUrgency.CRITICAL
            reason = "critical_risk_code"
        else:
            urgency = self._SEVERITIES.get(severity, EventUrgency.ROUTINE)
            if event_type in self._IMPORTANT_EVENT_TYPES:
                urgency = max(urgency, EventUrgency.IMPORTANT)
            reason = "declared_urgency"

        # Life and fraud never negotiate with rapport.
        if urgency is EventUrgency.CRITICAL:
            return PostureDecision(
                posture=ResponsePosture.CRITICAL_SPOKEN,
                urgency=urgency,
                rapport_tier=tier,
                reason_code=reason,
                tone="严肃、简短、直接",
            )
        if urgency is EventUrgency.HIGH:
            posture = (
                ResponsePosture.HAPTIC_NUDGE
                if tier is RapportTier.STRANGER_RESPECT
                else ResponsePosture.CRITICAL_SPOKEN
            )
            return PostureDecision(
                posture=posture,
                urgency=urgency,
                rapport_tier=tier,
                reason_code="high_urgency_rapport_calibrated",
                tone="克制提醒" if posture is ResponsePosture.HAPTIC_NUDGE else "直言",
            )
        if urgency is EventUrgency.IMPORTANT:
            posture = (
                ResponsePosture.SILENCE
                if tier is RapportTier.STRANGER_RESPECT
                and event_type not in self._IMPORTANT_EVENT_TYPES
                else ResponsePosture.HAPTIC_NUDGE
            )
            return PostureDecision(
                posture=posture,
                urgency=urgency,
                rapport_tier=tier,
                reason_code="important_rapport_calibrated",
                tone="轻触提醒"
                if posture is ResponsePosture.HAPTIC_NUDGE
                else "静默观察",
            )
        return PostureDecision(
            posture=ResponsePosture.SILENCE,
            urgency=EventUrgency.ROUTINE,
            rapport_tier=tier,
            reason_code="no_material_causal_change",
            tone="静默",
        )

    def decide_posture(self, event_context: Mapping[str, Any]) -> ResponsePosture:
        return self.decide(event_context).posture

    @staticmethod
    def _normalize_scalar(value: Any) -> str:
        return value.strip().upper() if isinstance(value, str) else ""

    @staticmethod
    def _parse_risk_codes(value: Any) -> frozenset[SafetyRiskCode]:
        raw_codes = (value,) if isinstance(value, (str, SafetyRiskCode)) else value
        if not isinstance(raw_codes, (tuple, list, set, frozenset)):
            return frozenset()
        parsed: set[SafetyRiskCode] = set()
        for raw_code in raw_codes:
            try:
                parsed.add(SafetyRiskCode(raw_code))
            except (TypeError, ValueError):
                # Posture is not a natural-language risk classifier. Unknown or
                # malformed labels fail closed to their separately declared urgency.
                continue
        return frozenset(parsed)


class CockpitSelfSummaryOperator:
    """Emit the four-step startup slice inside a conservative 350-byte envelope."""

    MAX_SUMMARY_TOKENS: ClassVar[int] = 350

    def __init__(
        self,
        mirror: SelfIdentityMirror,
        rapport: DynamicRapportModel,
        decider: HumanlikeResponsePostureDecider,
    ) -> None:
        self.mirror = mirror
        self.rapport = rapport
        self.decider = decider

    def generate_summary(self, current_event: Mapping[str, Any]) -> str:
        identity = self.mirror.audit_startup()
        rapport = self.rapport.snapshot()
        decision = self.decider.decide(current_event)
        description = current_event.get("description", "未知事件")
        if not isinstance(description, str) or not description.strip():
            description = "未知事件"
        summary = (
            "[心智启动]\n"
            f"1 身份:{identity.identity};底线:{'/'.join(identity.principles)}\n"
            f"2 羁绊:{rapport.tier.name};信任:{rapport.trust_score:g}\n"
            f"3 姿态:{decision.posture.name};音调:{decision.tone}\n"
            f"4 事件:{description.strip()}"
        )
        return self._truncate_utf8(summary, self.MAX_SUMMARY_TOKENS)

    @staticmethod
    def estimated_tokens(text: str) -> int:
        return len(text.encode("utf-8"))

    @staticmethod
    def _truncate_utf8(text: str, limit: int) -> str:
        return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
