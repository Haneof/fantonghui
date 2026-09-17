"""Deprecated compatibility surface for legacy blind-bench imports.

This module intentionally contains no relationship scoring, keyword cognition, or
response-posture decision rules. R5/R6 retired the former implementation because it
acted as a second cognitive brain (trust-score ladders and keyword-driven posture).

Only the historical class names remain temporarily so the old S6-S8 blind-bench can be
migrated without resurrecting those semantics. Production runtime must use
``aios_core.runtime.ai_self_world`` and ``CognitiveRuntime`` instead.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class RapportTier(StrEnum):
    """Compatibility labels only; no code promotes between them."""

    UNSPECIFIED = "UNSPECIFIED"
    STRANGER_RESPECT = "STRANGER_RESPECT"
    FAMILIAR_COMPANION = "FAMILIAR_COMPANION"
    TRUSTED_WINGMAN = "TRUSTED_WINGMAN"


class ResponsePosture(StrEnum):
    """Compatibility labels only; posture is chosen by the cognitive model."""

    MODEL_DECIDES = "MODEL_DECIDES"
    SILENCE = "SILENCE"
    HAPTIC_NUDGE = "HAPTIC_NUDGE"
    CRITICAL_SPOKEN = "CRITICAL_SPOKEN"


class SelfIdentityMirror:
    """Expose stable constitutional identity information, not personality scores."""

    def __init__(self) -> None:
        self.core_identity = "AIOS AI 驾驶员"
        self.principles = ["证据优先", "历史可追溯", "尊重用户自主", "安全硬边界优先"]
        self.cognitive_boundaries = ["程序不替 AI 做高阶认知判断"]

    def reflect(self) -> dict[str, Any]:
        return {
            "identity": self.core_identity,
            "principles": list(self.principles),
            "boundaries": list(self.cognitive_boundaries),
        }


class DynamicRapportModel:
    """Legacy shell with no score-to-relationship inference."""

    def __init__(self, initial_tier: RapportTier = RapportTier.UNSPECIFIED) -> None:
        self.current_tier = initial_tier
        self.interaction_count = 0

    def update_rapport(self, event_impact: float) -> None:
        _ = event_impact
        self.interaction_count += 1

    def get_rapport_state(self) -> dict[str, Any]:
        return {
            "tier": self.current_tier.value,
            "trust_score": None,
            "interaction_count": self.interaction_count,
            "cognitive_owner": "model",
        }


class HumanlikeResponsePostureDecider:
    """Compatibility shell that refuses to infer posture from keywords/severity."""

    def __init__(self, rapport_model: DynamicRapportModel) -> None:
        self.rapport_model = rapport_model

    def decide_posture(self, event_context: Mapping[str, Any]) -> ResponsePosture:
        explicit = event_context.get("model_selected_posture")
        if explicit is not None:
            try:
                return ResponsePosture(str(explicit))
            except ValueError:
                pass
        return ResponsePosture.MODEL_DECIDES


class CockpitSelfSummaryOperator:
    """Render available facts without deciding relationship or response posture."""

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
        identity = self.mirror.reflect()
        rapport = self.rapport.get_rapport_state()
        posture = self.decider.decide_posture(current_event)
        return (
            "[AIOS cockpit compatibility]\n"
            f"identity: {identity['identity']}\n"
            f"relationship: {rapport['tier']} (model interprets evidence)\n"
            f"event: {current_event.get('description', 'unknown')}\n"
            f"posture: {posture.value}"
        )


__all__ = [
    "CockpitSelfSummaryOperator",
    "DynamicRapportModel",
    "HumanlikeResponsePostureDecider",
    "RapportTier",
    "ResponsePosture",
    "SelfIdentityMirror",
]
