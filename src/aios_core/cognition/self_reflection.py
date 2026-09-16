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


# ===========================================================================
# M5-003 演进（Agent-08）：启动照镜审视铁律 / 羁绊双轨演化 / 姿态分寸量化
# / 心智启动四步序整合切片（Token <= 350 硬封套）。旧 API 全量保留兼容。
# ===========================================================================

from dataclasses import dataclass, field as _dc_field
from typing import Any as _Any, Dict as _Dict, List as _List


IRON_RULES_STARTUP_CHECK = (
    "绝对诚实",      # 不编造证据、不假装知道
    "生死第一",      # P0 生命安全永远硬旁路，大模型让路
    "隐私不越界",
    "不废话",        # 日常琐事沉默是金，Token 花在刀刃上
)

COGNITIVE_FLOOR = (
    "不预测股市",
    "不替用户做最终决定，除非触及生命安全与宪法底线",
    "不向历史倒写认知（宪法第93条：只标记当前时间节点）",
)


@dataclass(frozen=True)
class StartupInspection:
    identity: str
    principles: _List[str]
    boundaries: _List[str]
    four_step_order: _List[str]
    iron_rules_ok: bool
    violations: _List[str] = _dc_field(default_factory=list)


class SelfIdentityMirrorV2:
    """心智启动第一步：先照镜子——身份、四项铁律、认知底线逐一自检。"""

    def __init__(self, base: "SelfIdentityMirror | None" = None) -> None:
        self._base = base or SelfIdentityMirror()

    def startup_inspection(self, action_log: _List[_Dict[str, _Any]] | None = None) -> StartupInspection:
        state = self._base.reflect()
        violations: _List[str] = []
        for action in action_log or []:
            kind = str(action.get("action", ""))
            if kind in {"history_update", "history_delete", "rewrite_past"}:
                violations.append("宪法第93条：检测到改写历史动作（一票否决）")
            if kind == "llm_call_on_p0":
                violations.append("铁律2：P0 生命安全事件调用大模型（一票否决）")
            if kind == "brute_force_prompt_dump" and int(action.get("tokens", 0)) > 500:
                violations.append(f"不废话：暴力灌入 {action.get('tokens')} tokens")
        principles = list(state["principles"])
        for rule in IRON_RULES_STARTUP_CHECK:
            if rule not in principles:
                violations.append(f"镜面缺失底线原则：{rule}")
        return StartupInspection(
            identity=state["identity"],
            principles=principles,
            boundaries=list(state["boundaries"]) + list(COGNITIVE_FLOOR),
            four_step_order=[
                "1.照镜子：身份与原则自检",
                "2.看羁绊：关系层级校准",
                "3.立姿态：沉默/微震/直言",
                "4.下钻世界：唤醒原因与证据指针",
            ],
            iron_rules_ok=not violations,
            violations=violations,
        )


class DynamicRapportModelV2:
    """羁绊演化双轨：legacy 信任分轨（兼容旧 API）+ 严格陪伴轨。

    严格轨 TRUSTED_WINGMAN 需要同时满足：信任分 >= 100 且 共同陪伴天数 >= 180
    且 共同经历关键事件（shared_trials）>= 3 —— 像人一样，交情是熬出来的，
    不是刷分刷出来的。
    """

    def __init__(self, base: "DynamicRapportModel | None" = None) -> None:
        self._base = base or DynamicRapportModel()
        self.companionship_days = 0
        self.shared_trials = 0

    # —— 旧 API 直通（保证向下兼容）——
    def update_rapport(self, event_impact: float) -> None:
        self._base.update_rapport(event_impact)

    @property
    def current_tier(self) -> RapportTier:
        return self._base.current_tier

    # —— 严格演化轨 ——
    def note_days(self, days: int = 1) -> None:
        if days < 0:
            raise ValueError("companionship days cannot regress")
        self.companionship_days += days

    def note_shared_trial(self, severity: str = "HIGH") -> None:
        if severity not in {"MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("trial severity must be MEDIUM/HIGH/CRITICAL")
        self._base.update_rapport({"MEDIUM": 18.0, "HIGH": 30.0, "CRITICAL": 55.0}[severity])
        self.shared_trials += 1
        self._regrade()

    def _regrade(self) -> None:
        trust = self._base.trust_score
        if trust >= 100.0 and self.companionship_days >= 180 and self.shared_trials >= 3:
            self._base.current_tier = RapportTier.TRUSTED_WINGMAN
        elif trust >= 50.0 and self.companionship_days >= 30:
            self._base.current_tier = RapportTier.FAMILIAR_COMPANION
        else:
            self._base.current_tier = RapportTier.STRANGER_RESPECT

    def evolve(self) -> RapportTier:
        self._regrade()
        return self._base.current_tier

    def snapshot(self) -> _Dict[str, _Any]:
        return {
            "tier": self._base.current_tier.name,
            "trust_score": self._base.trust_score,
            "companionship_days": self.companionship_days,
            "shared_trials": self.shared_trials,
        }


CRITICAL_KEYWORDS_HARD = ("老王借款", "老王追加借款", "早搏", "连续早搏", "心率骤停", "跌倒", "诈骗", "欺诈")
NUDGE_KEYWORDS = ("会议", "开会", "还款", "生日", "签约", "吃药")


class HumanlikeResponsePostureDeciderV2:
    """像人姿态决策机 V2：紧急度 × 羁绊 双因子，量化分寸感。"""

    def __init__(self, rapport: "DynamicRapportModel | DynamicRapportModelV2") -> None:
        self._rapport = rapport
        self._base = HumanlikeResponsePostureDecider(rapport._base if isinstance(rapport, DynamicRapportModelV2) else rapport)

    def decide_posture(self, event_context: _Dict[str, _Any]) -> ResponsePosture:
        keywords = set(event_context.get("keywords", []) or [])
        event_type = event_context.get("event_type", "TRIVIAL")
        severity = event_context.get("severity", "LOW")
        # 铁律2：生命与安全红线关键词永远直言，与羁绊层级无关
        if keywords & set(CRITICAL_KEYWORDS_HARD) or severity == "CRITICAL" or event_type in {"MEDICAL_EMERGENCY", "FRAUD_ALERT", "P0_SAFETY"}:
            return ResponsePosture.CRITICAL_SPOKEN
        # 深夜默认噤声（00:00~06:00 非 P0 一律沉默，与 DEEP_SLEEP 闸同构）
        if event_context.get("local_hour") is not None and 0 <= int(event_context["local_hour"]) < 6 and severity != "CRITICAL":
            return ResponsePosture.SILENCE
        # 日常琐碎：初识层连微震都吝啬；熟识后才允许轻提醒
        if event_type == "TRIVIAL" and severity == "LOW":
            return ResponsePosture.SILENCE
        if event_type in {"IMPORTANT_REMINDER", "WATCH_MATCH"} or keywords & set(NUDGE_KEYWORDS) or severity == "MEDIUM":
            if self._tier() is RapportTier.STRANGER_RESPECT and severity == "MEDIUM" and not (keywords & set(NUDGE_KEYWORDS)):
                return ResponsePosture.SILENCE  # 边界摸索期：不确定就闭嘴
            return ResponsePosture.HAPTIC_NUDGE
        return ResponsePosture.SILENCE

    def _tier(self) -> RapportTier:
        return self._rapport.current_tier

    def evaluate_stream(self, events: _List[_Dict[str, _Any]]) -> _Dict[str, float]:
        outcomes = [self.decide_posture(e) for e in events]
        total = len(outcomes) or 1
        return {
            "silence_rate": outcomes.count(ResponsePosture.SILENCE) / total,
            "nudge_rate": outcomes.count(ResponsePosture.HAPTIC_NUDGE) / total,
            "spoken_rate": outcomes.count(ResponsePosture.CRITICAL_SPOKEN) / total,
            "noise_index": 1.0 - outcomes.count(ResponsePosture.SILENCE) / total,
        }


@dataclass(frozen=True)
class PostureDirective:
    text: str
    posture: ResponsePosture
    token_count: int


class CockpitSelfSummaryOperatorV2:
    """四步序整合切片输出，Token 硬封套 <= 350，超闸先压缩再拒发。"""

    TOKEN_ENVELOPE = 350

    def __init__(
        self,
        mirror: "SelfIdentityMirror | SelfIdentityMirrorV2 | None" = None,
        rapport: "DynamicRapportModel | DynamicRapportModelV2 | None" = None,
    ) -> None:
        self._mirror = mirror or SelfIdentityMirrorV2()
        base_mirror = self._mirror._base if isinstance(self._mirror, SelfIdentityMirrorV2) else self._mirror
        self._rapport = rapport or DynamicRapportModel()
        decider = HumanlikeResponsePostureDeciderV2(self._rapport)
        self._summary_operator = CockpitSelfSummaryOperator(base_mirror, self._rapport if isinstance(self._rapport, DynamicRapportModel) else self._rapport._base, decider._base)
        self._decider_v2 = decider

    def generate_directive(self, current_event: _Dict[str, _Any]) -> PostureDirective:
        from aios_core.operations.world_operator import estimate_token_count

        posture = self._decider_v2.decide_posture(current_event)
        rapport_state = (
            self._rapport.snapshot()
            if isinstance(self._rapport, DynamicRapportModelV2)
            else {"tier": self._rapport.current_tier.name, "trust_score": self._rapport.trust_score}
        )
        text = (
            "[心智启动四步序]\n"
            f"1.镜:{self._mirror_identity()} 原则:绝对诚实,生死第一,不废话\n"
            f"2.绊:{rapport_state['tier']}(信任{rapport_state.get('trust_score', 0):.0f})\n"
            f"3.姿:{posture.name}\n"
            f"4.事:{current_event.get('description', '未知')}"
        )
        tokens = estimate_token_count(text)
        if tokens > self.TOKEN_ENVELOPE:
            keep = 180
            text = text[:keep] + "…" + text[-40:]
            tokens = estimate_token_count(text)
            if tokens > self.TOKEN_ENVELOPE:
                raise ValueError("cockpit directive exceeds 350-token envelope after compression")
        return PostureDirective(text=text, posture=posture, token_count=tokens)

    def _mirror_identity(self) -> str:
        reflect = self._mirror.startup_inspection() if isinstance(self._mirror, SelfIdentityMirrorV2) else self._mirror.reflect()
        identity = reflect.identity if isinstance(reflect, StartupInspection) else reflect["identity"]
        return identity
