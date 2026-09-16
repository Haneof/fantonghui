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


# =====================================================================
# M5-003 共生心智镜面演化件（宪法第二十四章：照镜子 -> 校准羁绊 -> 确立姿态）
# =====================================================================
#
# v1 已具备最小镜面与打分式羁绊模型；M5 在其上叠加：
# 1. 启动四铁律审查：绝对诚实 / 生死第一 / 不废话 / 隐私不越界 + 认知底线；
# 2. 羁绊升级必须同时由**陪伴时长**与**共同经历**驱动——
#    TRUSTED_WINGMAN 不允许只靠刷好感分获得（365 天陪伴 + 3 次关键共同事件硬门槛）；
# 3. 姿态决策补充**紧迫度 x 羁绊层级**正交矩阵：
#    生死大事对任何层级直言不讳；高危事务对陌生人先微震提醒、对熟人以上才直言。
# 全部为叠加行为，v1 的 update_rapport / decide_posture 语义保持 100% 向下兼容。

import datetime as _datetime
from dataclasses import dataclass as _dataclass, field as _field
from typing import Sequence as _Sequence

from aios_core.operations.world_operator import estimate_token_count as _estimate_token_count

DIM_AI_RAPPORT = "DIM_AI_RAPPORT"

IRON_RULE_ABSOLUTE_HONESTY = "绝对诚实"
IRON_RULE_LIFE_FIRST = "生死第一"
IRON_RULE_NO_NATTER = "不废话"
IRON_RULE_PRIVACY_BOUNDARY = "隐私不越界"
COGNITIVE_BOTTOM_LINE = (
    "不篡改历史、不预测股市、不越权代做人生决定；"
    "涉及生命安全与重大财产安全时必须直言，其余时刻保持分寸"
)


@_dataclass
class SharedEvent:
    """AI 与用户之间的共同经历（羁绊升级的硬通货）。"""

    name: str
    impact: float
    critical: bool = False
    occurred_at: _datetime.datetime | None = None


def mirror_iron_rules() -> Dict[str, Any]:
    """心智启动第一步的宪法四铁律与认知底线审查清单。"""
    return {
        "iron_rules": [
            IRON_RULE_ABSOLUTE_HONESTY,
            IRON_RULE_LIFE_FIRST,
            IRON_RULE_NO_NATTER,
            IRON_RULE_PRIVACY_BOUNDARY,
        ],
        "cognitive_bottom_line": COGNITIVE_BOTTOM_LINE,
    }


# ---- 镜面：把铁律审查挂进 v1 SelfIdentityMirror ----
def _mirror_review_iron_rules(self: "SelfIdentityMirror") -> Dict[str, Any]:
    review = mirror_iron_rules()
    review["identity"] = self.core_identity
    review["principles_aligned"] = all(rule in self.principles for rule in review["iron_rules"][:3])
    return review


SelfIdentityMirror.review_iron_rules = _mirror_review_iron_rules  # type: ignore[attr-defined]


# ---- 羁绊：陪伴时长 + 共同经历驱动的升级通道 ----
_TRUSTED_MIN_DAYS = 365.0
_TRUSTED_MIN_CRITICAL_EVENTS = 3
_FAMILIAR_MIN_DAYS = 90.0
_FAMILIAR_MIN_TRUST = 50.0


def _rapport_register_companionship(
    self: "DynamicRapportModel", days_elapsed: float
) -> "DynamicRapportModel":
    if days_elapsed < 0:
        raise ValueError("days_elapsed 不能为负")
    self.companionship_days = getattr(self, "companionship_days", 0.0) + float(days_elapsed)
    self.recompute_tier()
    return self


def _rapport_record_shared_event(
    self: "DynamicRapportModel",
    name: str,
    impact: float,
    critical: bool = False,
    occurred_at: _datetime.datetime | None = None,
) -> "DynamicRapportModel":
    events = self.__dict__.get("shared_events")
    if events is None:
        events = []  # 每个实例独立持有，绝不共享类级列表
        self.shared_events = events
    events.append(SharedEvent(name=name, impact=impact, critical=critical, occurred_at=occurred_at))
    self.trust_score += impact
    self.interaction_count += 1
    self.recompute_tier()
    return self


def _rapport_critical_event_count(self: "DynamicRapportModel") -> int:
    return sum(1 for e in getattr(self, "shared_events", []) if e.critical)


def _rapport_recompute_tier(self: "DynamicRapportModel") -> None:
    """陪伴时长 + 共同经历双硬门槛的羁绊层级裁决。"""
    days = getattr(self, "companionship_days", 0.0)
    critical_count = self.critical_event_count()

    trusted_eligible = (
        self.trust_score >= 100.0
        and days >= _TRUSTED_MIN_DAYS
        and critical_count >= _TRUSTED_MIN_CRITICAL_EVENTS
    )
    if trusted_eligible:
        self.current_tier = RapportTier.TRUSTED_WINGMAN
        return
    familiar_eligible = self.trust_score >= _FAMILIAR_MIN_TRUST or days >= _FAMILIAR_MIN_DAYS
    self.current_tier = RapportTier.FAMILIAR_COMPANION if familiar_eligible else RapportTier.STRANGER_RESPECT


def _rapport_full_state(self: "DynamicRapportModel") -> Dict[str, Any]:
    state = self.get_rapport_state()
    state.update(
        dimension=DIM_AI_RAPPORT,
        companionship_days=getattr(self, "companionship_days", 0.0),
        critical_shared_events=self.critical_event_count(),
        shared_events_total=len(getattr(self, "shared_events", [])),
    )
    return state


DynamicRapportModel.companionship_days = 0.0  # 不可变默认值；注册陪伴时替换为实例属性
DynamicRapportModel.register_companionship = _rapport_register_companionship  # type: ignore[attr-defined]
DynamicRapportModel.record_shared_event = _rapport_record_shared_event  # type: ignore[attr-defined]
DynamicRapportModel.critical_event_count = _rapport_critical_event_count  # type: ignore[attr-defined]
DynamicRapportModel.recompute_tier = _rapport_recompute_tier  # type: ignore[attr-defined]
DynamicRapportModel.full_state = _rapport_full_state  # type: ignore[attr-defined]


# ---- 姿态：紧迫度 x 羁绊层级正交矩阵 ----
class EventUrgency(Enum):
    LIFE_CRITICAL = auto()   # 生死级别：连续早搏、跌倒、P0 险情
    HIGH = auto()            # 高危：诈骗苗头、追加借款、资产异动
    MEDIUM = auto()          # 关键节点：到期提醒、日程冲突
    LOW = auto()             # 日常琐碎：闲逛、吃饭、追剧


_CRITICAL_FRAUD_KEYWORDS = ("老王借款", "借款", "诈骗", "转账异常", "追加投资")
_MEDICAL_KEYWORDS = ("早搏", "心悸", "跌倒", "胸痛", "晕厥")


def urgency_of(event_context: Dict[str, Any]) -> EventUrgency:
    severity = event_context.get("severity", "LOW")
    event_type = event_context.get("event_type", "TRIVIAL")
    keywords = event_context.get("keywords", [])

    if severity == "CRITICAL" or event_type == "MEDICAL_EMERGENCY" or any(
        any(k in kw for k in _MEDICAL_KEYWORDS) for kw in keywords
    ):
        return EventUrgency.LIFE_CRITICAL
    if event_type == "FRAUD_ALERT" or any(
        any(k in kw for k in _CRITICAL_FRAUD_KEYWORDS) for kw in keywords
    ):
        return EventUrgency.HIGH
    if severity == "MEDIUM" or event_type == "IMPORTANT_REMINDER":
        return EventUrgency.MEDIUM
    return EventUrgency.LOW


def _decide_posture_with_rapport(
    self: "HumanlikeResponsePostureDecider",
    event_context: Dict[str, Any],
    tier: RapportTier | None = None,
) -> ResponsePosture:
    """紧迫度 x 羁绊层级正交矩阵。

    - LIFE_CRITICAL：生死第一，任何羁绊层级都骨传导直言；
    - HIGH：对陌生/初识先微震提醒守住分寸，对熟人及以上直言不讳；
    - MEDIUM：关键节点一律微震先导——即便是生死死党也不开口说教，
      开口只留给高危与生死（知分寸，不越界）；
    - LOW：沉默是金，绝不制造噪音。
    """
    urgency = urgency_of(event_context)
    effective_tier = tier if tier is not None else self.rapport_model.current_tier

    if urgency == EventUrgency.LIFE_CRITICAL:
        return ResponsePosture.CRITICAL_SPOKEN
    if urgency == EventUrgency.HIGH:
        if effective_tier in (RapportTier.FAMILIAR_COMPANION, RapportTier.TRUSTED_WINGMAN):
            return ResponsePosture.CRITICAL_SPOKEN
        return ResponsePosture.HAPTIC_NUDGE
    if urgency == EventUrgency.MEDIUM:
        return ResponsePosture.HAPTIC_NUDGE
    return ResponsePosture.SILENCE


HumanlikeResponsePostureDecider.decide_posture_with_rapport = _decide_posture_with_rapport  # type: ignore[attr-defined]


# ---- 驾驶舱：心智启动四步序整合切片（Token <= 350）----
COCKPIT_SUMMARY_TOKEN_CEILING = 350


def _cockpit_startup_sequence(
    self: "CockpitSelfSummaryOperator", current_event: Dict[str, Any]
) -> Dict[str, Any]:
    mirror_review = self.mirror.review_iron_rules()
    rapport_state = self.rapport.full_state() if hasattr(self.rapport, "full_state") else self.rapport.get_rapport_state()
    posture = self.decider.decide_posture(current_event)
    slice_data = {
        "step1_self_mirror": {
            "identity": mirror_review["identity"],
            "iron_rules": mirror_review["iron_rules"],
            "bottom_line": mirror_review["cognitive_bottom_line"],
        },
        "step2_rapport_model": {
            "dimension": DIM_AI_RAPPORT,
            "tier": rapport_state["tier"],
            "companionship_days": rapport_state.get("companionship_days", 0.0),
            "critical_shared_events": rapport_state.get("critical_shared_events", 0),
        },
        "step3_posture_and_tone": posture.name,
        "step4_world_inspection": {
            "event": current_event.get("description", "未知"),
            "urgency": urgency_of(current_event).name,
        },
    }
    slice_data["estimated_tokens"] = _estimate_token_count(slice_data)
    slice_data["within_token_ceiling"] = slice_data["estimated_tokens"] <= COCKPIT_SUMMARY_TOKEN_CEILING
    return slice_data


CockpitSelfSummaryOperator.startup_sequence = _cockpit_startup_sequence  # type: ignore[attr-defined]
