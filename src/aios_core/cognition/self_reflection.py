from enum import Enum, auto
from typing import Dict, Any, List

class RapportTier(Enum):
    STRANGER_RESPECT = 1
    FAMILIAR_COMPANION = 2
    TRUSTED_WINGMAN = 3

class ResponsePosture(Enum):
    SILENCE = auto()
    HAPTIC_NUDGE = auto()
    CRITICAL_SPOKEN = auto()

class SelfIdentityMirror:
    def __init__(self):
        self.core_identity = "共生心智实体"
        self.principles = ["绝对诚实", "生死第一", "隐私不越界", "不废话"]
        self.cognitive_boundaries = ["不预测股市", "不干预用户自主决策，除非涉及底线"]
    
    def reflect(self) -> Dict[str, Any]:
        return {
            "identity": self.core_identity,
            "principles": self.principles,
            "boundaries": self.cognitive_boundaries
        }

class DynamicRapportModel:
    def __init__(self, initial_tier: RapportTier = RapportTier.STRANGER_RESPECT):
        self.current_tier = initial_tier
        self.interaction_count = 0
        self.trust_score = 0.0

    def update_rapport(self, event_impact: float):
        self.trust_score += event_impact
        self.interaction_count += 1
        
        if self.trust_score >= 100.0:
            self.current_tier = RapportTier.TRUSTED_WINGMAN
        elif self.trust_score >= 50.0:
            self.current_tier = RapportTier.FAMILIAR_COMPANION
        else:
            self.current_tier = RapportTier.STRANGER_RESPECT

    def get_rapport_state(self) -> Dict[str, Any]:
        return {
            "tier": self.current_tier.name,
            "trust_score": self.trust_score,
            "interaction_count": self.interaction_count
        }

class HumanlikeResponsePostureDecider:
    def __init__(self, rapport_model: DynamicRapportModel):
        self.rapport_model = rapport_model

    def decide_posture(self, event_context: Dict[str, Any]) -> ResponsePosture:
        severity = event_context.get("severity", "LOW")
        event_type = event_context.get("event_type", "TRIVIAL")
        keywords = event_context.get("keywords", [])

        if severity == "CRITICAL" or event_type in ["MEDICAL_EMERGENCY", "FRAUD_ALERT"]:
            return ResponsePosture.CRITICAL_SPOKEN
        
        if "老王借款" in keywords or "早搏" in keywords:
            return ResponsePosture.CRITICAL_SPOKEN

        if severity == "MEDIUM" or event_type == "IMPORTANT_REMINDER":
            return ResponsePosture.HAPTIC_NUDGE

        return ResponsePosture.SILENCE

class CockpitSelfSummaryOperator:
    def __init__(self, mirror: SelfIdentityMirror, rapport: DynamicRapportModel, decider: HumanlikeResponsePostureDecider):
        self.mirror = mirror
        self.rapport = rapport
        self.decider = decider

    def generate_summary(self, current_event: Dict[str, Any]) -> str:
        identity_state = self.mirror.reflect()
        rapport_state = self.rapport.get_rapport_state()
        posture = self.decider.decide_posture(current_event)
        
        summary = (
            f"[心智启动整合]\n"
            f"1. 身份: {identity_state['identity']} | 原则: {','.join(identity_state['principles'])}\n"
            f"2. 羁绊: {rapport_state['tier']} (信任度 {rapport_state['trust_score']})\n"
            f"3. 当前事件: {current_event.get('description', '未知')}\n"
            f"4. 响应姿态: {posture.name}"
        )
        
        return summary
