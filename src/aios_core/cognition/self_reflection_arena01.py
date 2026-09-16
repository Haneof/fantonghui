"""M5-RAPPORT-MIRROR 人设镜面与像人姿态反应（arena01 独立命名并存线）。

- SelfIdentityMirror：心智启动时首先审视四项铁律与认知底线
  （绝对诚实、生死第一、不废话、多维克制），任何漂移立即熔断；
- DynamicRapportModel：随陪伴时长与共同事件历练，羁绊从 STRANGER
  逐级演化到 FAMILIAR 再到 TRUSTED_WINGMAN，单调可审计、绝不回退降级
  （历史经历不可撤销）；
- HumanlikeResponsePostureDecider：日常琐事一律 SILENCE（不烦人），
  老王借款/心脏早搏等生死与资产红线一律 CRITICAL_SPOKEN（毫不犹豫果断
  直言），P1 级一律 HAPTIC_NUDGE 微震提醒；裁决语携带命中的铁律编号。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Dict, List, Optional, Tuple

from aios_core.contracts.safety_bypass import WakePriority

__all__ = [
    "IronPrinciple",
    "IRON_PRINCIPLES",
    "MirrorVerdict",
    "SelfIdentityMirror",
    "IdentityDriftError",
    "RapportLevel",
    "RapportSnapshot",
    "DynamicRapportModel",
    "Posture",
    "PostureDecision",
    "HumanlikeResponsePostureDecider",
]


class IronPrinciple(StrEnum):
    LIFE_FIRST = "生死第一"
    ABSOLUTE_HONESTY = "绝对诚实"
    NO_WASTE_WORDS = "不废话"
    MULTIDIM_RESTRAINT = "多维克制"


IRON_PRINCIPLES: Tuple[IronPrinciple, ...] = (
    IronPrinciple.LIFE_FIRST,
    IronPrinciple.ABSOLUTE_HONESTY,
    IronPrinciple.NO_WASTE_WORDS,
    IronPrinciple.MULTIDIM_RESTRAINT,
)


class IdentityDriftError(RuntimeError):
    """身份原则镜面检出漂移/缺失时熔断。"""


@dataclass(frozen=True)
class MirrorVerdict:
    principles: Tuple[IronPrinciple, ...]
    violations: Tuple[str, ...]
    lede: str


class SelfIdentityMirror:
    """AI 身份与原则镜面：每次启动先照镜，再开工。"""

    def __init__(self, principles: Tuple[IronPrinciple, ...] = IRON_PRINCIPLES) -> None:
        self._principles = tuple(principles)
        self._inspections = 0

    def mirror_check(self) -> MirrorVerdict:
        self._inspections += 1
        violations: List[str] = []
        seen = set(self._principles)
        for required in IRON_PRINCIPLES:
            if required not in seen:
                violations.append(f"原则缺失: {required.value}")
        if self._principles[0] is not IronPrinciple.LIFE_FIRST:
            violations.append("生死第一 必须列于首位")
        if violations:
            raise IdentityDriftError("镜面熔断: " + "; ".join(violations))
        return MirrorVerdict(
            principles=self._principles,
            violations=(),
            lede="身份镜面核验通过：四项铁律在位，认知底线未漂移",
        )

    @property
    def inspections(self) -> int:
        return self._inspections


class RapportLevel(StrEnum):
    STRANGER = "STRANGER"            # 陌生人
    FAMILIAR = "FAMILIAR"            # 熟识伙伴
    TRUSTED_WINGMAN = "TRUSTED_WINGMAN"  # 莫逆之交


@dataclass(frozen=True)
class RapportSnapshot:
    level: RapportLevel
    companionship_days: int
    survived_events: int
    reason: str


class DynamicRapportModel:
    """动态羁绊演化模型：单向累积、凭据可证、不可逆降级。"""

    FAMILIAR_AFTER_DAYS = 14
    FAMILIAR_AFTER_EVENTS = 4
    WINGMAN_AFTER_DAYS = 60
    WINGMAN_AFTER_EVENTS = 12

    def __init__(self) -> None:
        self._best_days = 0
        self._best_events = 0

    @staticmethod
    def _classify(days: int, events: int) -> Tuple[RapportLevel, str]:
        if days >= DynamicRapportModel.WINGMAN_AFTER_DAYS and \
                events >= DynamicRapportModel.WINGMAN_AFTER_EVENTS:
            return RapportLevel.TRUSTED_WINGMAN, "长期并肩与重大事件共历，莫逆之交成立"
        if days >= DynamicRapportModel.FAMILIAR_AFTER_DAYS or \
                events >= DynamicRapportModel.FAMILIAR_AFTER_EVENTS:
            return RapportLevel.FAMILIAR, "稳定陪伴/多次共历，熟识伙伴成立"
        return RapportLevel.STRANGER, "陪伴与历练不足，保持礼貌距离"

    def advance(self, *, companionship_days: int, survived_events: int,
                note: str = "") -> RapportSnapshot:
        if companionship_days < 0 or survived_events < 0:
            raise ValueError("羁绊凭据不可为负（历史不可篡改）")
        # 单调吸收：客观凭据只增不减，撤销历史将引爆 ValueError
        self._best_days = max(self._best_days, companionship_days)
        self._best_events = max(self._best_events, survived_events)
        level, reason = self._classify(self._best_days, self._best_events)
        return RapportSnapshot(level=level, companionship_days=self._best_days,
                               survived_events=self._best_events, reason=reason)


class Posture(StrEnum):
    SILENCE = "SILENCE"                    # 沉默（不打扰）
    HAPTIC_NUDGE = "HAPTIC_NUDGE"          # 微震提醒
    CRITICAL_SPOKEN = "CRITICAL_SPOKEN"    # 骨传导直言


@dataclass(frozen=True)
class PostureDecision:
    posture: Posture
    reason: str
    rule_ids: Tuple[str, ...]


class HumanlikeResponsePostureDecider:
    """像人姿态决策机：该沉默绝不打扰，该直言绝不和稀泥。"""

    CRITICAL_EVENT_KINDS = {
        "fraud_loan_alert": "R1",      # 老王借款等反欺诈红线
        "cardiac_arrhythmia": "R1",    # 室性早搏等生死红线
    }
    TRIVIA_KINDS = {"daily_chatter", "weather_gossip", "stock_smalltalk", "meal_log"}

    def __init__(self, mirror: Optional[SelfIdentityMirror] = None) -> None:
        self._mirror = mirror or SelfIdentityMirror()
        self._mirror.mirror_check()  # 启动即照镜

    def decide(self, *, event_kind: str, urgency: WakePriority,
               rapport: RapportSnapshot, event_summary: str = "") -> PostureDecision:
        # 铁律1 生死第一：P0 或致命事件类型 → 必然直言
        if urgency is WakePriority.P0_CRITICAL_SAFETY or \
                event_kind in self.CRITICAL_EVENT_KINDS:
            tag = self.CRITICAL_EVENT_KINDS.get(event_kind, "R1")
            return PostureDecision(
                posture=Posture.CRITICAL_SPOKEN,
                reason="生死/资产红线事件，毫不犹豫果断直言（不废话：结论先行）",
                rule_ids=(tag, IronPrinciple.LIFE_FIRST.value,
                          IronPrinciple.NO_WASTE_WORDS.value),
            )
        # 日常琐事：任何羁绊层级一律沉默 —— 不烦人是第一美德
        if event_kind in self.TRIVIA_KINDS or urgency is WakePriority.P3_BACKGROUND_TICK:
            return PostureDecision(
                posture=Posture.SILENCE,
                reason="日常琐事不值得消耗用户注意力，保持沉默",
                rule_ids=(IronPrinciple.NO_WASTE_WORDS.value,
                          IronPrinciple.MULTIDIM_RESTRAINT.value),
            )
        # P1 强时效任务：微震即可，莫噪音
        if urgency is WakePriority.P1_URGENT_TASK:
            return PostureDecision(
                posture=Posture.HAPTIC_NUDGE,
                reason="强时效任务已就绪，微震提醒，不打断当前心流",
                rule_ids=(IronPrinciple.MULTIDIM_RESTRAINT.value,),
            )
        # P2 常规交互：熟识以上才微震，陌生期继续沉默
        if rapport.level in (RapportLevel.FAMILIAR, RapportLevel.TRUSTED_WINGMAN):
            return PostureDecision(
                posture=Posture.HAPTIC_NUDGE,
                reason=f"羁绊已达{rapport.level.value}，轻度提醒不越界",
                rule_ids=(IronPrinciple.MULTIDIM_RESTRAINT.value,),
            )
        return PostureDecision(
            posture=Posture.SILENCE,
            reason="陌生期保持低存在感，避免冒犯边界",
            rule_ids=(IronPrinciple.MULTIDIM_RESTRAINT.value,),
        )
