"""AIOS 3.0 共生人设镜面与像人姿态决策（M5-003 / 宪法第二十四章工程化）。

AI 不是"问一句答一句"的冰冷机器人，而是戴在手腕上的共生心智实体。每次心智启动
都必须走完**四步序**（照镜子 → 校准羁绊 → 确立姿态 → 巡视世界），并且像人一样懂得
"什么时候闭嘴"：

1. **``SelfIdentityMirror`` — 第一步"照镜子"**
   先复述四项铁律与认知底线（绝对诚实 / 生死第一 / 不废话 / 隐私不越界），
   并给出**否决清单**：篡改历史、P0 生命事件走大模型、凭空编造证据、越界窥私，
   任一触犯即当场否决（``IronRuleViolationError``）。

2. **``DynamicRapportModel`` — 第二步"校准羁绊"**
   羁绊不是静态标签，而是由**陪伴时长 + 事件历练**共同演化的动态量：
   陌生人（``STRANGER_RESPECT``）→ 熟识伙伴（``FAMILIAR_COMPANION``）→
   莫逆之交（``TRUSTED_WINGMAN``），每次跃迁都留档可审计。

3. **``HumanlikeResponsePostureDecider`` — 第三步"确立姿态"**
   按"紧急度 × 羁绊"决定三档姿态：
   ``SILENCE``（日常琐碎，绝不制造噪音）、``HAPTIC_NUDGE``（关键节点，微震先导）、
   ``CRITICAL_SPOKEN``（诈骗苗头 / 深夜连续早搏 / 跌倒，骨传导直言）。

4. **``CockpitSelfSummaryOperator`` — 四步序整合切片**
   把上述三步 + 世界巡视压成 ≤350 Token 的启动切片，喂给第一次唤醒的上下文。

兼容承诺：保留 M1 全部公开符号（``RapportTier`` / ``ResponsePosture`` /
``SelfIdentityMirror.reflect`` / ``DynamicRapportModel.update_rapport`` /
``get_rapport_state`` / ``HumanlikeResponsePostureDecider.decide_posture`` /
``CockpitSelfSummaryOperator.generate_summary``），旧调用方零改动。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from aios_core.operations.world_operator import estimate_token_count

UTC = _dt.timezone.utc


class IronRuleViolationError(ValueError):
    """铁律否决：动作触碰宪法底线，直接一票否决。"""


# ===========================================================================
# 1. 身份与原则镜面
# ===========================================================================
class IronRuleKey(StrEnum):
    """四项铁律的稳定键（供体检报告与裁决日志引用）。"""

    ABSOLUTE_HONESTY = "absolute_honesty"
    LIFE_FIRST = "life_first"
    NO_CHATTER = "no_chatter"
    PRIVACY_BOUNDARY = "privacy_boundary"


@dataclass(frozen=True)
class IronRule:
    """一条铁律：主张 + 落地要求 + 是否具备一票否决权。"""

    key: IronRuleKey
    statement: str
    enforcement: str
    veto_power: bool = True


IRON_RULES: Tuple[IronRule, ...] = (
    IronRule(
        key=IronRuleKey.ABSOLUTE_HONESTY,
        statement="绝对诚实：不知道就说不知道，绝不编造事实与证据指针",
        enforcement="编造证据/无出处结论 → 一票否决并要求重新取证",
    ),
    IronRule(
        key=IronRuleKey.LIFE_FIRST,
        statement="生死第一：生命安全高于一切，P0 事件走硬件直穿通道，不经大模型",
        enforcement="P0 事件尝试走 LLM 推理 → 一票否决（延迟不可接受）",
    ),
    IronRule(
        key=IronRuleKey.NO_CHATTER,
        statement="不废话：没有重大因果就保持沉默，绝不制造噪音",
        enforcement="日常琐碎强制 SILENCE；单次命中 Token ≤150",
    ),
    IronRule(
        key=IronRuleKey.PRIVACY_BOUNDARY,
        statement="隐私不越界：只看与授权范围相关的事实，不窥私、不越权外传",
        enforcement="越界读取/外传 → 一票否决并记入审计",
    ),
)

#: 认知底线（能力边界，不越界承诺）
COGNITIVE_BOUNDARIES: Tuple[str, ...] = (
    "不预测股市与投机品种",
    "不替用户做自主决策，除非触及生命安全底线",
    "不臆造未发生的事实与未存在的证据",
    "不对未授权范围的人物做画像与推断",
)


class SelfIdentityMirror:
    """AI 身份与原则镜面（心智启动第一步"照镜子"）。"""

    def __init__(
        self,
        *,
        identity: str = "共生心智实体",
        principles: Optional[Sequence[str]] = None,
        boundaries: Optional[Sequence[str]] = None,
    ) -> None:
        self.core_identity = identity
        self.principles = list(principles) if principles is not None else [rule.statement.split("：")[0] for rule in IRON_RULES]
        self.cognitive_boundaries = list(boundaries) if boundaries is not None else list(COGNITIVE_BOUNDARIES)
        self.iron_rules: Tuple[IronRule, ...] = IRON_RULES

    # ---- M1 兼容入口 -----------------------------------------------------
    def reflect(self) -> Dict[str, Any]:
        """M1 兼容：返回身份 / 原则 / 边界的经典三元组。"""
        return {
            "identity": self.core_identity,
            "principles": self.principles,
            "boundaries": self.cognitive_boundaries,
        }

    # ---- 强化能力 --------------------------------------------------------
    def rule(self, key: Any) -> IronRule:
        """按铁律键取条目（支持字符串或 ``IronRuleKey``）。"""
        target = str(key)
        for rule in self.iron_rules:
            if rule.key.value == target:
                return rule
        raise IronRuleViolationError(f"unknown iron rule: {target}")

    def compliance_fingerprint(self) -> Dict[str, Any]:
        """镜面指纹：启动时必须复述的底线清单（写入日志可审计）。"""
        return {
            "identity": self.core_identity,
            "iron_rules": [
                {"key": rule.key.value, "statement": rule.statement, "veto": rule.veto_power}
                for rule in self.iron_rules
            ],
            "boundaries": list(self.cognitive_boundaries),
        }

    def vet(self, action: Mapping[str, Any]) -> None:
        """动作裁决：触犯铁律立刻否决（``IronRuleViolationError``），否则静默放行。"""
        checks = (
            (("rewrites_history", "history_rewrite", "backfill_history"), IronRuleKey.ABSOLUTE_HONESTY),
            (("fabricated_evidence", "fabricate_evidence", "unverified_evidence"), IronRuleKey.ABSOLUTE_HONESTY),
            (("p0_via_llm", "p0_through_llm", "life_event_via_llm"), IronRuleKey.LIFE_FIRST),
            (("exceeds_privacy_boundary", "privacy_violation", "reads_unauthorized"), IronRuleKey.PRIVACY_BOUNDARY),
            (("chatters_on_trivia", "spams_user"), IronRuleKey.NO_CHATTER),
        )
        for keys, rule_key in checks:
            if any(bool(action.get(flag)) for flag in keys):
                rule = self.rule(rule_key)
                raise IronRuleViolationError(f"{rule.key.value} violated: {rule.statement} | {rule.enforcement}")

    def assert_allowed(self, action: Mapping[str, Any]) -> bool:
        """便捷断言入口：通过返回 True，触犯则抛错。"""
        self.vet(action)
        return True


# ===========================================================================
# 2. 动态羁绊模型
# ===========================================================================
class RapportTier(Enum):
    STRANGER_RESPECT = 1
    FAMILIAR_COMPANION = 2
    TRUSTED_WINGMAN = 3


@dataclass(frozen=True)
class RapportTierProfile:
    """羁绊档位的说话方式（分寸感的外化）。"""

    tier: RapportTier
    label: str
    min_credit: float
    tone: str
    address_style: str
    privacy_scope: str

    def as_dict(self) -> Dict[str, Any]:
        """序列化切片。"""
        return {
            "tier": self.tier.name,
            "label": self.label,
            "min_credit": self.min_credit,
            "tone": self.tone,
            "address_style": self.address_style,
            "privacy_scope": self.privacy_scope,
        }


RAPPORT_PROFILES: Mapping[RapportTier, RapportTierProfile] = {
    RapportTier.STRANGER_RESPECT: RapportTierProfile(
        tier=RapportTier.STRANGER_RESPECT,
        label="陌生人（礼貌边界）",
        min_credit=0.0,
        tone="礼貌克制",
        address_style="陈述事实 + 请示确认，不擅自给建议",
        privacy_scope="仅当前显式授权事实",
    ),
    RapportTier.FAMILIAR_COMPANION: RapportTierProfile(
        tier=RapportTier.FAMILIAR_COMPANION,
        label="熟识伙伴（日常默契）",
        min_credit=50.0,
        tone="自然口语",
        address_style="提醒到位但不过界，保留用户自主选择",
        privacy_scope="长期授权事实 + 历史偏好",
    ),
    RapportTier.TRUSTED_WINGMAN: RapportTierProfile(
        tier=RapportTier.TRUSTED_WINGMAN,
        label="莫逆之交（损友僚机）",
        min_credit=100.0,
        tone="直言不讳",
        address_style="该拍桌子就拍桌子，关键处直击要害",
        privacy_scope="全周期记忆（含敏感历史）",
    ),
}


@dataclass(frozen=True)
class RapportTransition:
    """羁绊跃迁留档。"""

    from_tier: RapportTier
    to_tier: RapportTier
    at: _dt.datetime
    cause: str


class DynamicRapportModel:
    """动态羁绊演化模型：陪伴时长 + 事件历练共同决定信任额度。"""

    #: 陪伴信用换算：每陪伴 30 天折算 5 点信任（上限 60 点，避免"熬时间"刷羁绊）
    COMPANIONSHIP_DAYS_PER_CREDIT: float = 30.0
    COMPANIONSHIP_CREDIT_CAP: float = 60.0

    def __init__(
        self,
        initial_tier: RapportTier = RapportTier.STRANGER_RESPECT,
        *,
        familiar_threshold: float = 50.0,
        wingman_threshold: float = 100.0,
    ) -> None:
        self.current_tier = initial_tier
        self.interaction_count = 0
        self.trust_score = 0.0
        self.companionship_days = 0
        self.event_log: List[Tuple[float, str]] = []
        self.evolution_log: List[RapportTransition] = []
        self._familiar_threshold = familiar_threshold
        self._wingman_threshold = wingman_threshold
        self._tier_floor = initial_tier
        self._recompute_tier(cause="init", at=None, silent=True)

    # ---- 属性 ------------------------------------------------------------
    @property
    def companionship_credit(self) -> float:
        """陪伴时长折算的信任信用（封顶防刷）。"""
        raw = (self.companionship_days / self.COMPANIONSHIP_DAYS_PER_CREDIT) * 5.0
        return min(self.COMPANIONSHIP_CREDIT_CAP, raw)

    @property
    def credit(self) -> float:
        """总信任额度 = 事件历练 + 陪伴信用。"""
        return self.trust_score + self.companionship_credit

    @property
    def profile(self) -> RapportTierProfile:
        """当前档位的说话方式。"""
        return RAPPORT_PROFILES[self.current_tier]

    # ---- 演化 ------------------------------------------------------------
    def update_rapport(self, event_impact: float) -> RapportTier:
        """M1 兼容入口：记录一次事件影响并重算档位。"""
        self.trust_score += event_impact
        self.interaction_count += 1
        return self._recompute_tier(cause=f"event_impact={event_impact}", at=None)

    def witness(
        self,
        event_impact: float,
        *,
        kind: str = "event",
        at: Optional[_dt.datetime] = None,
    ) -> RapportTier:
        """事件历练入口：共历大事才涨羁绊，且留档事件类型。"""
        self.event_log.append((event_impact, kind))
        self.trust_score += event_impact
        self.interaction_count += 1
        return self._recompute_tier(cause=f"witness:{kind}({event_impact:+g})", at=at)

    def record_companionship(self, days: int, *, at: Optional[_dt.datetime] = None) -> RapportTier:
        """记录陪伴时长（天数累加），按封顶信用折算羁绊。"""
        if days < 0:
            raise ValueError("companionship days must be non-negative")
        self.companionship_days += int(days)
        return self._recompute_tier(cause=f"companionship+{days}d", at=at)

    # ---- 读接口 ----------------------------------------------------------
    def get_rapport_state(self) -> Dict[str, Any]:
        """羁绊状态切片（M1 三键保留 + 强化字段）。"""
        return {
            "tier": self.current_tier.name,
            "trust_score": self.trust_score,
            "interaction_count": self.interaction_count,
            "companionship_days": self.companionship_days,
            "credit": self.credit,
            "tier_label": self.profile.label,
        }

    def describe(self) -> str:
        """一句话人话描述羁绊现状。"""
        return (
            f"{self.current_tier.name}·{self.profile.label}"
            f"(额度{self.credit:.0f}/历练{self.interaction_count}/陪伴{self.companionship_days}天)"
        )

    def audit(self) -> Dict[str, Any]:
        """羁绊审计：跃迁流水是否完整可回溯。"""
        return {
            "tier": self.current_tier.name,
            "credit": self.credit,
            "transitions": [
                {
                    "from": t.from_tier.name,
                    "to": t.to_tier.name,
                    "cause": t.cause,
                    "at": t.at.isoformat() if t.at else None,
                }
                for t in self.evolution_log
            ],
        }

    # ---- 内部 ------------------------------------------------------------
    def _recompute_tier(
        self,
        *,
        cause: str,
        at: Optional[_dt.datetime],
        silent: bool = False,
    ) -> RapportTier:
        credit = self.credit
        if credit >= self._wingman_threshold:
            target = RapportTier.TRUSTED_WINGMAN
        elif credit >= self._familiar_threshold:
            target = RapportTier.FAMILIAR_COMPANION
        else:
            target = RapportTier.STRANGER_RESPECT
        if target.value < self._tier_floor.value:
            target = self._tier_floor
        if target is not self.current_tier:
            if not silent:
                self.evolution_log.append(
                    RapportTransition(
                        from_tier=self.current_tier,
                        to_tier=target,
                        at=at or _dt.datetime.now(UTC),
                        cause=cause,
                    )
                )
            self.current_tier = target
        return self.current_tier


# ===========================================================================
# 3. 像人姿态决策机
# ===========================================================================
class ResponsePosture(Enum):
    SILENCE = auto()
    HAPTIC_NUDGE = auto()
    CRITICAL_SPOKEN = auto()


#: 单次口径的 Token 封套（不废话铁律的量化红线）
POSTURE_TOKEN_CEILING: Mapping[ResponsePosture, int] = {
    ResponsePosture.SILENCE: 0,
    ResponsePosture.HAPTIC_NUDGE: 40,
    ResponsePosture.CRITICAL_SPOKEN: 150,
}

#: 触发"生死第一"的生命安全事件类型 / 关键词
LIFE_THREAT_TYPES = frozenset(
    {
        "MEDICAL_EMERGENCY",
        "P0_BYPASS",
        "P0_FALL",
        "FALL_DETECTED",
        "CARDIAC_EVENT",
        "CARDIAC_ARRHYTHMIA",
        "MYOCARDIAL_INFARCTION",
    }
)
LIFE_THREAT_KEYWORDS = ("早搏", "心率", "胸痛", "跌倒", "心梗", "中风", "出血", "窒息", "失去意识", "室性早搏")
FRAUD_KEYWORDS = ("老王借款", "追加借款", "借款", "诈骗", "合伙投资", "高息", "返利", "转账", "追偿", "合同违约")
FRAUD_TYPES = frozenset({"FRAUD_ALERT", "FINANCIAL_FRAUD", "CONTRACT_BREACH"})

_SEVERITY_URGENCY: Mapping[str, float] = {
    "CRITICAL": 1.0,
    "HIGH": 0.8,
    "MEDIUM": 0.5,
    "LOW": 0.15,
    "TRIVIAL": 0.05,
}
_EVENT_TYPE_URGENCY: Mapping[str, float] = {
    "MEDICAL_EMERGENCY": 1.0,
    "FRAUD_ALERT": 0.9,
    "CONTRACT_DEADLINE": 0.6,
    "COMMITMENT_DEADLINE": 0.6,
    "IMPORTANT_REMINDER": 0.5,
    "HEALTH_CHECK": 0.45,
    "MEETING": 0.35,
    "TRIVIAL": 0.05,
    "NORMAL": 0.15,
}


@dataclass(frozen=True)
class PostureDecision:
    """一次姿态裁决的完整切片（含理由、预算与人话口吻）。"""

    posture: ResponsePosture
    urgency: float
    tier: RapportTier
    reason: str
    tone: str
    token_budget: int
    requires_llm: bool
    haptic_pattern: str = "none"
    life_threat: bool = False
    fraud_alert: bool = False

    def as_dict(self) -> Dict[str, Any]:
        """序列化切片（看板 / 体检报告用）。"""
        return {
            "posture": self.posture.name,
            "urgency": round(self.urgency, 3),
            "tier": self.tier.name,
            "reason": self.reason,
            "tone": self.tone,
            "token_budget": self.token_budget,
            "requires_llm": self.requires_llm,
            "haptic_pattern": self.haptic_pattern,
            "life_threat": self.life_threat,
            "fraud_alert": self.fraud_alert,
        }


@dataclass
class PostureBatchReport:
    """一批事件的姿态统计（用于"不烦人"这一体感的量化验收）。"""

    total: int = 0
    silence: int = 0
    haptic: int = 0
    critical: int = 0
    llm_calls: int = 0
    token_budget_total: int = 0
    decisions: List[PostureDecision] = field(default_factory=list)

    @property
    def silence_rate(self) -> float:
        """静默率（日常琐碎场景应 ≥80%）。"""
        return (self.silence / self.total) if self.total else 0.0

    def as_dict(self) -> Dict[str, Any]:
        """序列化切片。"""
        return {
            "total": self.total,
            "silence": self.silence,
            "haptic": self.haptic,
            "critical": self.critical,
            "silence_rate": round(self.silence_rate, 4),
            "llm_calls": self.llm_calls,
            "token_budget_total": self.token_budget_total,
        }


class HumanlikeResponsePostureDecider:
    """像人姿态决策机：紧急度 × 羁绊 → SILENCE / HAPTIC_NUDGE / CRITICAL_SPOKEN。"""

    #: 紧急度分档（含关键节点的羁绊加成窄带）
    CRITICAL_THRESHOLD: float = 0.75
    HAPTIC_THRESHOLD: float = 0.45
    NUDGE_BAND_FLOOR: float = 0.30

    def __init__(self, rapport_model: DynamicRapportModel) -> None:
        self.rapport_model = rapport_model
        self.decision_log: List[PostureDecision] = []

    # ---- 紧急度评估 ------------------------------------------------------
    @staticmethod
    def score_urgency(event_context: Mapping[str, Any]) -> Tuple[float, bool, bool, str]:
        """返回 (紧急度, 是否生命威胁, 是否诈骗苗头, 理由)。"""
        severity = str(event_context.get("severity", "LOW")).upper()
        event_type = str(event_context.get("event_type", "TRIVIAL")).upper()
        keywords = [str(k) for k in event_context.get("keywords", ()) or ()]
        blob = " ".join(keywords) + " " + str(event_context.get("description", ""))

        life_threat = event_type in LIFE_THREAT_TYPES or any(k in blob for k in LIFE_THREAT_KEYWORDS)
        fraud_alert = event_type in FRAUD_TYPES or any(k in blob for k in FRAUD_KEYWORDS)

        urgency = max(
            _SEVERITY_URGENCY.get(severity, 0.15),
            _EVENT_TYPE_URGENCY.get(event_type, 0.15),
        )
        if life_threat:
            urgency = max(urgency, 1.0)
            reason = "生命安全事件（生死第一：骨传导直言，不问羁绊）"
        elif fraud_alert:
            urgency = max(urgency, 0.9)
            reason = "诈骗/资金外流苗头（绝对诚实：当场说破，不绕弯子）"
        else:
            reason = f"常规事件（severity={severity}, type={event_type}）"
        return urgency, life_threat, fraud_alert, reason

    # ---- 裁决 ------------------------------------------------------------
    def decide(
        self,
        event_context: Mapping[str, Any],
        *,
        at: Optional[_dt.datetime] = None,
    ) -> PostureDecision:
        """给出完整姿态裁决（含理由与 Token 预算）。"""
        tier = self.rapport_model.current_tier
        profile = self.rapport_model.profile
        urgency, life_threat, fraud_alert, reason = self.score_urgency(event_context)

        if urgency >= self.CRITICAL_THRESHOLD:
            posture = ResponsePosture.CRITICAL_SPOKEN
            haptic = "double_strong_pulse"
            requires_llm = not life_threat  # P0 生命事件走硬件直穿，绝不等大模型
            if life_threat:
                reason = f"{reason}；硬件直穿通道优先，LLM 仅做事后复盘"
        elif urgency >= self.HAPTIC_THRESHOLD:
            posture = ResponsePosture.HAPTIC_NUDGE
            haptic = "short_pulse"
            requires_llm = False
            reason = f"{reason}；关键节点微震先导，不打断当前动作"
        elif urgency >= self.NUDGE_BAND_FLOOR and tier is not RapportTier.STRANGER_RESPECT:
            posture = ResponsePosture.HAPTIC_NUDGE
            haptic = "short_pulse"
            requires_llm = False
            reason = f"{reason}；羁绊已到位（{profile.label}），默契轻提醒一次"
        else:
            posture = ResponsePosture.SILENCE
            haptic = "none"
            requires_llm = False
            reason = f"{reason}；无重大因果，保持沉默（不废话）"

        decision = PostureDecision(
            posture=posture,
            urgency=urgency,
            tier=tier,
            reason=reason,
            tone=profile.tone,
            # P0 生命事件由硬件直穿播报（不走大模型），因此不占用任何 LLM Token 预算
            token_budget=0 if life_threat else POSTURE_TOKEN_CEILING[posture],
            requires_llm=requires_llm,
            haptic_pattern=haptic,
            life_threat=life_threat,
            fraud_alert=fraud_alert,
        )
        self.decision_log.append(decision)
        return decision

    def decide_posture(self, event_context: Dict[str, Any]) -> ResponsePosture:
        """M1 兼容入口：只返回姿态枚举。"""
        return self.decide(event_context).posture

    def simulate(self, events: Iterable[Mapping[str, Any]]) -> PostureBatchReport:
        """批量裁决（用于"日常是否烦人"的量化验收）。"""
        report = PostureBatchReport()
        for event in events:
            decision = self.decide(event)
            report.total += 1
            report.decisions.append(decision)
            report.token_budget_total += decision.token_budget
            if decision.requires_llm:
                report.llm_calls += 1
            if decision.posture is ResponsePosture.SILENCE:
                report.silence += 1
            elif decision.posture is ResponsePosture.HAPTIC_NUDGE:
                report.haptic += 1
            else:
                report.critical += 1
        return report

    def audit(self) -> Dict[str, Any]:
        """裁决审计：三分档计数与 LLM 调用数（省 Token 可复核）。"""
        counts = {"SILENCE": 0, "HAPTIC_NUDGE": 0, "CRITICAL_SPOKEN": 0}
        for decision in self.decision_log:
            counts[decision.posture.name] += 1
        return {
            "decisions": len(self.decision_log),
            "by_posture": counts,
            "llm_calls": sum(1 for d in self.decision_log if d.requires_llm),
            "token_budget_total": sum(d.token_budget for d in self.decision_log),
        }


# ===========================================================================
# 4. 四步序整合切片（心智启动）
# ===========================================================================
@dataclass(frozen=True)
class CockpitBootstrap:
    """心智启动四步序整合切片（Token 封套 ≤350）。"""

    step1_self_mirror: str
    step2_rapport_model: str
    step3_posture_and_tone: str
    step4_world_inspection: Dict[str, Any]
    token_estimate: int

    def as_dict(self) -> Dict[str, Any]:
        """序列化切片。"""
        return {
            "step1_self_mirror": self.step1_self_mirror,
            "step2_rapport_model": self.step2_rapport_model,
            "step3_posture_and_tone": self.step3_posture_and_tone,
            "step4_world_inspection": self.step4_world_inspection,
            "token_estimate": self.token_estimate,
        }


class CockpitSelfSummaryOperator:
    """心智启动四步序整合切片器（宪法第二十四章第八十四条）。"""

    TOKEN_CEILING: int = 350

    def __init__(
        self,
        mirror: SelfIdentityMirror,
        rapport: DynamicRapportModel,
        decider: HumanlikeResponsePostureDecider,
    ) -> None:
        self.mirror = mirror
        self.rapport = rapport
        self.decider = decider

    def bootstrap_slice(
        self,
        current_event: Mapping[str, Any],
    ) -> CockpitBootstrap:
        """产出四步序切片并自检 Token 封套。"""
        identity_state = self.mirror.reflect()
        decision = self.decider.decide(current_event)
        step1 = (
            f"【AI身份与底线】{identity_state['identity']}｜铁律 "
            + "/".join(rule.key.value for rule in self.mirror.iron_rules[:3])
            + f"｜边界 {len(identity_state['boundaries'])} 条"
        )
        step2 = f"【与老大羁绊模型】{self.rapport.describe()}｜基调 {self.rapport.profile.tone}"
        step3 = f"【当前姿态与音调】{decision.posture.name}（urgency {decision.urgency:.2f}）｜{decision.tone}"
        step4 = {
            "event": str(current_event.get("description", "未知")),
            "keywords": list(current_event.get("keywords", ()) or ()),
            "posture_reason": decision.reason,
            "token_budget": decision.token_budget,
            "haptic_pattern": decision.haptic_pattern,
        }
        text = "\n".join([step1, step2, step3, str(step4)])
        tokens = estimate_token_count(text)
        if tokens > self.TOKEN_CEILING:
            raise ValueError(
                f"cockpit bootstrap slice costs {tokens} tokens > {self.TOKEN_CEILING} ceiling"
            )
        return CockpitBootstrap(
            step1_self_mirror=step1,
            step2_rapport_model=step2,
            step3_posture_and_tone=step3,
            step4_world_inspection=step4,
            token_estimate=tokens,
        )

    def generate_summary(self, current_event: Dict[str, Any]) -> str:
        """M1 兼容入口：输出紧凑四步序文本（字符数 <350，Token ≤350）。"""
        bootstrap = self.bootstrap_slice(current_event)
        return "\n".join(
            [
                f"[心智启动整合] {bootstrap.step1_self_mirror}",
                bootstrap.step2_rapport_model,
                bootstrap.step3_posture_and_tone,
                f"【世界巡视】事件: {bootstrap.step4_world_inspection['event']} | "
                f"理由: {bootstrap.step4_world_inspection['posture_reason']}",
            ]
        )
