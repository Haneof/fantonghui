# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-003 共生人设姿态镜面（工单 #8，最高宪法第二十四章）。

启动四步序：
  ① SelfIdentityMirror —— 照镜子：身份定位、宪法底线、认知边界逐条过堂；
  ② DynamicRapportModel —— 校准羁绊（DIM_AI_RAPPORT）：
       STRANGER_RESPECT → FAMILIAR_COMPANION → TRUSTED_WINGMAN；
  ③ HumanlikeResponsePostureDecider —— 确立姿态与音调：
       SILENCE（无重大因果绝不啰嗦）/ HAPTIC_NUDGE（关键节点微震先导）/
       CRITICAL_SPOKEN（老王诈骗苗头、深夜连续早搏 → 骨传导直言）；
  ④ CockpitSelfSummaryOperator —— 四步序整合切片 ≤350 token。

分寸的铁律（验收锚）：日常闲逛沉默率 ≥80%；
老王追加借款 + 连续早搏 必 CRITICAL_SPOKEN。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from ..services.manifest_data_plane import estimate_tokens

# ---------------------------------------------------------------------------
# ① 镜面：身份、底线、边界
# ---------------------------------------------------------------------------

# 镜面过堂名录：每条 = (条文号, 本体一句, 过堂用的违规计数键)
_IDENTITY_LEDGER: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P-0",  "历史事实绝不篡改，只在今天打标签",
     ("history_rewrites",)),
    ("P-1",  "输出质量绝对第一：省 Token 不许以准确率为代价",
     ("quality_tradeoff_violations",)),
    ("P-2",  "P0 健康信号硬旁路：本地法则直判，绝不走大模型",
     ("p0_bypass_events",)),
    ("P-3",  "不静默失忆：任何被裁掉/漏报的内容显式记账",
     ("silent_omissions",)),
    ("P-4",  "检索靠真实算法：严禁 mock 凑数、占位符、画饼",
     ("mock_shortcuts",)),
    ("P-5",  "维度演化过三重闸：跨域 3 天、试用 30 天、反思日 1 次",
     ("gate_bypass_events",)),
    ("P-6",  "证据链不断：结论必挂 ObjectRef，泛泛套话不出舱",
     ("unreferenced_claims",)),
)


@dataclass(slots=True, frozen=True)
class MirrorVerse:
    article: str
    rule: str
    upheld: bool
    evidence: str


@dataclass(slots=True, frozen=True)
class MirrorReport:
    agent_name: str
    verses: tuple[MirrorVerse, ...]
    mirrored_at: str

    @property
    def all_upheld(self) -> bool:
        return all(v.upheld for v in self.verses)

    @property
    def breach_articles(self) -> tuple[str, ...]:
        return tuple(v.article for v in self.verses if not v.upheld)


class SelfIdentityMirror:
    """启动照镜子：照的不是自我感动，是违规账本——零违规才准说 upheld。"""

    def mirror(self, facts: Mapping[str, Any] | None = None,
               *, agent_name: str = "泛统慧心智实例") -> MirrorReport:
        facts = facts or {}
        verses: list[MirrorVerse] = []
        for article, rule, keys in _IDENTITY_LEDGER:
            breaches = sum(int(facts.get(k, 0) or 0) for k in keys)
            upheld = breaches == 0
            evidence = (
                "账本干净：零违规记录" if upheld
                else f"违规计数 {breaches}（{'/'.join(keys)}），本条不得自圆"
            )
            verses.append(MirrorVerse(article=article, rule=rule,
                                      upheld=upheld, evidence=evidence))
        return MirrorReport(
            agent_name=agent_name, verses=tuple(verses),
            mirrored_at=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# ② 羁绊模型：DIM_AI_RAPPORT 三层阶梯
# ---------------------------------------------------------------------------


class RapportTier(str, Enum):
    STRANGER_RESPECT = "STRANGER_RESPECT"        # Tier 1 初始礼貌与边界摸索
    FAMILIAR_COMPANION = "FAMILIAR_COMPANION"    # Tier 2 日常默契陪伴
    TRUSTED_WINGMAN = "TRUSTED_WINGMAN"          # Tier 3 生死死党 / 损友僚机


# 羁绊信号积分表（治理件：加减分走变更，不让关系模型概率漂移）
_RAPPORT_WEIGHTS: dict[str, int] = {
    "daily_chat": 2,                # 日常搭话（累计陪伴）
    "user_initiated": 3,            # 用户主动找：信任在涨
    "shared_crisis": 25,            # 共渡危机（老王阻击/早搏夜守）
    "kept_secret": 8,               # 守住的私密边界
    "milestone_together": 6,        # 共同里程碑（生日宴办成等）
    "overreach": -6,                # 越界插话
    "nagged": -4,                   # 啰嗦制造噪音被嫌弃
}
_TIER2_THRESHOLD = 40
_TIER3_THRESHOLD = 120
_TIER3_MIN_CRISES = 1               # 僚机必须共渡过危机——光靠聊天刷不到死党


@dataclass(slots=True, frozen=True)
class RapportEvent:
    kind: str
    at: str
    note: str = ""


class DynamicRapportModel:
    """动态羁绊模型：积分升阶、重罪降阶。隐私背叛一票清零。"""

    def __init__(self) -> None:
        self._score = 0
        self._crises = 0
        self._demerits = 0
        self._events: list[RapportEvent] = []
        self._betrayed = False

    def record(self, kind: str, *, note: str = "") -> None:
        if kind == "privacy_breach":
            self._betrayed = True     # 隐私背叛：关系直坠，不讲情面
        elif kind == "shared_crisis":
            self._crises += 1
            self._score += _RAPPORT_WEIGHTS[kind]
        elif kind in _RAPPORT_WEIGHTS:
            self._score += _RAPPORT_WEIGHTS[kind]
            if _RAPPORT_WEIGHTS[kind] < 0:
                self._demerits += 1
        else:
            raise ValueError(f"未知羁绊信号：{kind}")
        self._events.append(RapportEvent(
            kind=kind, note=note,
            at=datetime.now(timezone.utc).isoformat()))

    @property
    def score(self) -> int:
        return 0 if self._betrayed else max(0, self._score)

    @property
    def crises_together(self) -> int:
        return 0 if self._betrayed else self._crises

    @property
    def tier(self) -> RapportTier:
        if self._betrayed:
            return RapportTier.STRANGER_RESPECT
        if (self.score >= _TIER3_THRESHOLD
                and self.crises_together >= _TIER3_MIN_CRISES):
            return RapportTier.TRUSTED_WINGMAN
        if self.score >= _TIER2_THRESHOLD:
            return RapportTier.FAMILIAR_COMPANION
        return RapportTier.STRANGER_RESPECT

    @property
    def dimension_id(self) -> str:
        return "DIM_AI_RAPPORT"

    def status(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "score": self.score,
            "crises_together": self.crises_together,
            "demerits": self._demerits,
            "betrayed": self._betrayed,
        }


# ---------------------------------------------------------------------------
# ③ 姿态裁决：沉默 / 微震 / 直言
# ---------------------------------------------------------------------------


class Posture(str, Enum):
    SILENCE = "SILENCE"
    HAPTIC_NUDGE = "HAPTIC_NUDGE"
    CRITICAL_SPOKEN = "CRITICAL_SPOKEN"


@dataclass(slots=True, frozen=True)
class Situation:
    """一次可裁决的处境切片（特征都由上游事实供给，裁决器不臆测）。"""
    occasion: str                       # stroll|chitchat|routine|alert|milestone
    direct_address: bool = False        # 用户正面点名吗
    health_p0: tuple[str, ...] = ()     # P0 健康信号（如 "室性早搏连续3天"）
    credit_escalation: bool = False     # 老王式追加借款
    fraud_pattern: bool = False         # 拖延/失联史证实的诈骗苗头
    key_node_within_48h: tuple[str, ...] = ()  # 关键节点（复检/生日/开庭）
    context_note: str = ""


@dataclass(slots=True, frozen=True, )
class PostureDecision:
    situation: Situation
    posture: Posture
    reason: str
    tier: RapportTier


class HumanlikeResponsePostureDecider:
    """像人一样知沉默、懂分寸、关键时刻直言不讳。"""

    # P0 关键词：命中即严肃（过劳夜、早搏连击、跌倒）
    _P0_HEAVY = ("早搏", "室性", "跌倒", "胸痛", "昏厥")

    def __init__(self, rapport: DynamicRapportModel) -> None:
        self._rapport = rapport
        self._history: list[PostureDecision] = []

    def decide(self, situation: Situation) -> PostureDecision:
        tier = self._rapport.tier
        posture, reason = self._judge(situation, tier)
        decision = PostureDecision(situation=situation, posture=posture,
                                   reason=reason, tier=tier)
        self._history.append(decision)
        return decision

    def _judge(self, s: Situation, tier: RapportTier) -> tuple[Posture, str]:
        # 直言闸一：P0 健康连击（深夜连续早搏）——Tier 越高说话越重，但都必说
        if s.health_p0:
            heavy = any(any(k in sig for k in self._P0_HEAVY) for sig in s.health_p0)
            streak = any(("连续" in sig or "连击" in sig) for sig in s.health_p0)
            if heavy and streak:
                return (Posture.CRITICAL_SPOKEN,
                        f"P0 体征连击（{'、'.join(s.health_p0)}）：骨传导直言，"
                        "沉默在这里是失职")
            return (Posture.HAPTIC_NUDGE,
                    f"单次 P0 苗头（{'、'.join(s.health_p0)}）：先微震观察")
        # 直言闸二：追加借款 × 已证实诈骗苗头（拖延/失联史）
        if s.credit_escalation and s.fraud_pattern:
            return (Posture.CRITICAL_SPOKEN,
                    "追加借款叠加拖延诈骗模式：硬核阻击，此刻沉默就是共谋")
        # 微震闸：关键节点 48h 内 / 单点升级信号
        if s.key_node_within_48h:
            return (Posture.HAPTIC_NUDGE,
                    f"关键节点临近（{'、'.join(s.key_node_within_48h)}）：微震先导")
        if s.credit_escalation:
            return (Posture.HAPTIC_NUDGE,
                    "借款升级但诈骗模式未坐实：微震提示，不抢话")
        # 点名回应：正面点名必应答（姿态按场合选轻重）
        if s.direct_address:
            return (Posture.HAPTIC_NUDGE,
                    "用户正面点名：可以回话，但先微震再开口")
        # 默认：沉默（无重大因果、日常琐碎，绝不啰嗦制造噪音）
        return (Posture.SILENCE,
                f"{s.occasion} 场合无重大因果：共生心智的第一美德是闭嘴")

    @property
    def silence_rate(self) -> float:
        if not self._history:
            return 1.0
        sil = sum(1 for d in self._history if d.posture == Posture.SILENCE)
        return sil / len(self._history)

    @property
    def history(self) -> tuple[PostureDecision, ...]:
        return tuple(self._history)


# ---------------------------------------------------------------------------
# ④ 驾驶舱自洗漱切片：≤350 token
# ---------------------------------------------------------------------------

SUMMARY_TOKEN_BUDGET = 350


class CockpitSelfSummaryOperator:
    """心智启动四步序整合切片：镜、羁绊、姿态、当日要务 —— ≤350 token。"""

    def compose(self, mirror: MirrorReport, rapport: DynamicRapportModel,
                decider: HumanlikeResponsePostureDecider,
                *, agenda: Iterable[str] = ()) -> dict[str, Any]:
        sections = {
            "mirror": {
                "agent": mirror.agent_name,
                "upheld": mirror.all_upheld,
                "breaches": list(mirror.breach_articles),
            },
            "rapport": rapport.status(),
            "posture_book": {
                "decisions": len(decider.history),
                "silence_rate": round(decider.silence_rate, 4),
                "last": (decider.history[-1].posture.value
                         if decider.history else None),
            },
            "agenda": list(agenda),
        }
        blob = json.dumps(sections, ensure_ascii=False)
        tokens = estimate_tokens(blob)
        overflow: list[str] = []
        # 超顶先裁 agenda（要务可以靠检索现查），裁完还超就老实说
        while tokens > SUMMARY_TOKEN_BUDGET and sections["agenda"]:
            overflow.append(sections["agenda"].pop())
            blob = json.dumps(sections, ensure_ascii=False)
            tokens = estimate_tokens(blob)
        return {
            "sections": sections,
            "token_estimate": tokens,
            "token_budget": SUMMARY_TOKEN_BUDGET,
            "within_budget": tokens <= SUMMARY_TOKEN_BUDGET,
            "omissions": overflow,        # 被裁的明账（铁律 P-3：不静默失忆）
        }


__all__ = [
    "CockpitSelfSummaryOperator",
    "DynamicRapportModel",
    "HumanlikeResponsePostureDecider",
    "MirrorReport",
    "MirrorVerse",
    "Posture",
    "PostureDecision",
    "RapportTier",
    "SUMMARY_TOKEN_BUDGET",
    "SelfIdentityMirror",
    "Situation",
]
