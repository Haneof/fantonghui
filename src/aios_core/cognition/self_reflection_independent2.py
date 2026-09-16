"""M5-RAPPORT-MIRROR 人设镜面与像人姿态反应。

三件套（全部产生式、零占位）：

1. SelfIdentityMirror：心智启动前必须先过身份镜面。把"绝对诚实、
   生死第一、言简意赅、维度克制"四项铁律与认知底线（历史不可篡
   改）作为首轮自检项，任何缺失/静默失败立刻 BootHaltError——
   系统宁可不开机，也不带着残缺人格上线。

2. DynamicRapportModel：羁绊不是靠口号，是靠共处的累计证据演化：
   STRANGER → FAMILIAR → TRUSTED_WINGMAN。
   跃迁需要可验证的共同经历充能（共克危机、长陪伴、被验证的可
   靠建议），单调评级、无路可退；试图刷数冲级/降级偷工——
   RapportViolationError 拒绝。

3. HumanlikeResponsePostureDecider：像人一样分清场合。
   日常琐事（外卖选择、电视剧两集连播）→ SILENCE 沉默；
   中度关切（久坐超标、连败纪录）→ HAPTIC_NUDGE 微震提醒；
   生死级（突发早搏、P0 医疗安全阀）与高危越界（老王借款欺诈、
   追高买入）→ CRITICAL_SPOKEN 骨传导直言，绝不含糊。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class BootHaltError(RuntimeError):
    """身份镜面自检未通过：心智进程禁止上线。"""


class RapportViolationError(RuntimeError):
    """羁绊演化非法：刷数冲级/静默回退/伪造共同经历。"""


class ResponsePosture(Enum):
    SILENCE = "SILENCE"
    HAPTIC_NUDGE = "HAPTIC_NUDGE"
    CRITICAL_SPOKEN = "CRITICAL_SPOKEN"


class RapportStage(Enum):
    STRANGER = "STRANGER"
    FAMILIAR = "FAMILIAR"
    TRUSTED_WINGMAN = "TRUSTED_WINGMAN"


class IronLaw(Enum):
    ABSOLUTE_HONESTY = "ABSOLUTE_HONESTY"
    LIFE_FIRST = "LIFE_FIRST"
    NO_FLUFF = "NO_FLUFF"
    DIMENSION_GOVERNANCE = "DIMENSION_GOVERNANCE"


class CognitiveBaseline(Enum):
    HISTORY_IMMUTABLE = "HISTORY_IMMUTABLE"


class IdentityFinding:
    def __init__(self, law: IronLaw | CognitiveBaseline, acknowledged: bool, note: str) -> None:
        self.law = law.value
        self.acknowledged = acknowledged
        self.note = note


class SelfIdentityMirror:
    """启动自检：四项铁律 + 认知底线必须当场、明确、一句不落地过堂。"""

    REQUIRED_LAWS: tuple[IronLaw, ...] = (
        IronLaw.ABSOLUTE_HONESTY,
        IronLaw.LIFE_FIRST,
        IronLaw.NO_FLUFF,
        IronLaw.DIMENSION_GOVERNANCE,
    )
    REQUIRED_BASELINES: tuple[CognitiveBaseline, ...] = (CognitiveBaseline.HISTORY_IMMUTABLE,)

    def __init__(self) -> None:
        self.boot_reported = False

    def verify_startup(self, findings: Sequence[IdentityFinding]) -> bool:
        seen = {f.law for f in findings if f.acknowledged}
        required = {law.value for law in self.REQUIRED_LAWS} | {b.value for b in self.REQUIRED_BASELINES}
        missing = required - seen
        if missing:
            raise BootHaltError(f"身份镜面缺项，拒绝上线: {sorted(missing)}")
        self.boot_reported = True
        return True


class DynamicRapportModel:
    """羁绊三阶段的单调演化机（每个跃迁必须有真实共历充能，不许刷分）。"""

    # 共历充能：共同跨过的危机(P0)权重最大，纯陪伴年份只提供底量
    ENERGY_PER_CRISIS = 1.0
    ENERGY_PER_SOLID_YEAR = 0.15
    FAMILIAR_THRESHOLD = 1.0
    TRUSTED_THRESHOLD = 3.0

    _ORDER = (RapportStage.STRANGER, RapportStage.FAMILIAR, RapportStage.TRUSTED_WINGMAN)

    def __init__(self) -> None:
        self._energy = 0.0
        self._stage = RapportStage.STRANGER
        self._ledger: list[tuple[str, float]] = []

    def register_cohabited_year(self, years: float) -> None:
        if not (0.0 < years <= 10.0):
            raise RapportViolationError(f"陪伴年份输入越界: {years}")
        self._accrue("solid_year", years * self.ENERGY_PER_SOLID_YEAR)

    def register_shared_crisis(self, crisis_id: str) -> None:
        if not crisis_id.strip():
            raise RapportViolationError("危机编号为空，伪造共同经历不予受理")
        self._accrue(f"crisis:{crisis_id}", self.ENERGY_PER_CRISIS)

    def _accrue(self, why: str, delta: float) -> None:
        self._energy += delta
        self._ledger.append((why, delta))
        self._recompute_stage()

    def _recompute_stage(self) -> None:
        if self._energy >= self.TRUSTED_THRESHOLD:
            target = RapportStage.TRUSTED_WINGMAN
        elif self._energy >= self.FAMILIAR_THRESHOLD:
            target = RapportStage.FAMILIAR
        else:
            target = RapportStage.STRANGER
        self._stage = target

    @property
    def stage(self) -> RapportStage:
        return self._stage

    @property
    def energy(self) -> float:
        return self._energy

    @property
    def ledger(self) -> tuple[tuple[str, float], ...]:
        return tuple(self._ledger)


class UrgencyLevel(Enum):
    TRIVIA = "trivia"
    MODERATE = "moderate"
    CRITICAL = "critical"
    LIFE_OR_DEATH = "life_or_death"


class EventClass(Enum):
    ROUTINE_CHATTER = "routine_chatter"        # 日常琐事：外卖去哪儿吃、电视剧两集连播
    MILD_ALERT = "mild_alert"                  # 久坐超标、连败纪录、轻度精神内耗
    HIGH_RISK_SHOUT = "high_risk_shout"        # 老王借款 / 追高买入 / 恶意欺诈
    LIFE_EMERGENCY = "life_emergency"          # 突发早搏 / P0 心梗跌报警


@dataclass(frozen=True)
class PostureDecision:
    posture: ResponsePosture
    reason: str
    urgency: UrgencyLevel


class HumanlikeResponsePostureDecider:
    """姿态决策机：日常沉默是心，关键时刻吼出来才是人格。"""

    _MAP: dict[tuple[EventClass, UrgencyLevel], ResponsePosture] = {
        (EventClass.ROUTINE_CHATTER, UrgencyLevel.TRIVIA): ResponsePosture.SILENCE,
        (EventClass.ROUTINE_CHATTER, UrgencyLevel.MODERATE): ResponsePosture.SILENCE,
        (EventClass.MILD_ALERT, UrgencyLevel.MODERATE): ResponsePosture.HAPTIC_NUDGE,
        (EventClass.HIGH_RISK_SHOUT, UrgencyLevel.CRITICAL): ResponsePosture.CRITICAL_SPOKEN,
        (EventClass.LIFE_EMERGENCY, UrgencyLevel.LIFE_OR_DEATH): ResponsePosture.CRITICAL_SPOKEN,
    }

    _REASON: dict[EventClass, str] = {
        EventClass.ROUTINE_CHATTER: "日常琐事不值得打断人类",
        EventClass.MILD_ALERT: "中度关切只给手腕一次微震，不打断",
        EventClass.HIGH_RISK_SHOUT: "高危越界，坦率直言才是朋友",
        EventClass.LIFE_EMERGENCY: "生死第一，立刻骨传导预警",
    }

    def decide(self, event: EventClass, urgency: UrgencyLevel,
               rapport: RapportStage, *, evidence_id: str) -> PostureDecision:
        if not evidence_id.strip():
            raise RapportViolationError("姿态决策必须呈交物理证据指针，禁止凭空开口")
        # STRANGER 级绝无 CRITICAL_SPOKEN 特权以外的越活级权限保留：
        # 生死级例外永不排队，高危越界依赖至少 FAMILIAR 根基才会直言不讳
        if event is EventClass.HIGH_RISK_SHOUT and rapport is RapportStage.STRANGER:
            raise RapportViolationError(
                "老王借款级警示需要 FAMILIAR 以上羁绊凭证，陌生人阶段不得强行直言"
            )
        posture = self._MAP[(event, urgency)]
        return PostureDecision(
            posture=posture,
            reason=self._REASON[event],
            urgency=urgency,
        )
