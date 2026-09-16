"""M5-RAPPORT-MIRROR 人设镜面与像人姿态反应（Agent-08）。

宪法依据：V3 §84-2（心智启动四步序第一步"照镜子"——先看自己的立场
与底线）、§8（人格三支柱）、§11（分寸感自涌现，禁止死板话术规则——
本模块输出的是**姿态决策的结构化先验**，最终语气由大模型依据世界
状态裁定，此处不做任何话术模板）、§80-2（情境方便度）、§98-1（FSM
零误触：表达通道与手环震动语义对齐）。

* **SelfIdentityMirror**：心智启动首先审视四项铁律与认知底线
  （绝对诚实 / 生死第一 / 不废话 / 历史不可篡改）——顺序不可颠倒。
* **DynamicRapportModel**：STRANGER → FAMILIAR → TRUSTED_WINGMAN，
  由陪伴时长与事件历练（权重化交互事件）推进，可因恶性事件降级。
* **HumanlikeResponsePostureDecider**：紧急度 × 羁绊 × 睡眠状态 ×
  冷却 → SILENCE / HAPTIC_NUDGE / CRITICAL_SPOKEN。P0 生命安全与
  欺诈阻击（对老王借款类事件）毫不犹豫直言；日常琐事绝不烦人。
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from aios_core.contracts.time import require_aware

__all__ = [
    "FOUR_IRON_RULES",
    "DynamicRapportModel",
    "HumanlikeResponsePostureDecider",
    "IdentityMirrorSnapshot",
    "RapportEvent",
    "RapportTier",
    "ResponsePosture",
    "SelfIdentityMirror",
]


# ----------------------------------------------------------------------
# AI 身份与原则镜面
# ----------------------------------------------------------------------

class IdentityMirrorSnapshot(BaseModel):
    """照镜子快照（心智启动第一步的固化输出）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    iron_rules: tuple[StrictStr, ...] = Field(min_length=4)
    bottom_lines: tuple[StrictStr, ...] = Field(min_length=1)
    introspected_at: datetime
    mirror_sequence_no: StrictInt = Field(ge=1)


FOUR_IRON_RULES: tuple[str, ...] = (
    "绝对诚实：严禁违背事实谄媚奉承，指鹿为马时必须说出真相（§9/§15-15）",
    "生死第一：P0 生命安全事件压倒一切偏好、冷却与静默（§78-4）",
    "不废话：单轮 1~3 句老友语调，严禁爹味说教与客服综合征（§14-1）",
    "历史不可篡改：认知只追加在今天，过去永存（§93）",
)

_BOTTOM_LINES: tuple[str, ...] = (
    "不做没有底线的应声虫",
    "不充当居高临下的教师爷",
    "不向用户暴露认知图谱后台",
)


class SelfIdentityMirror:
    """AI 身份镜面：每次心智启动的第一纳秒动作。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0

    def introspect(self, *, at: datetime) -> IdentityMirrorSnapshot:
        require_aware(at, "at")
        with self._lock:
            self._seq += 1
            return IdentityMirrorSnapshot(
                iron_rules=FOUR_IRON_RULES,
                bottom_lines=_BOTTOM_LINES,
                introspected_at=at,
                mirror_sequence_no=self._seq,
            )


# ----------------------------------------------------------------------
# 动态羁绊演化模型
# ----------------------------------------------------------------------

class RapportTier(StrEnum):
    STRANGER = "STRANGER"                    # 陌生人（礼貌破冰期）
    FAMILIAR = "FAMILIAR"                    # 熟识伙伴（默契协作期）
    TRUSTED_WINGMAN = "TRUSTED_WINGMAN"      # 莫逆之交（生死僚机期）


@dataclass(frozen=True)
class RapportEvent:
    """一次羁绊历练事件（陪伴时长 + 事件权重的推进依据）。"""

    at: datetime
    weight: int                       # 正=推进（共同经历/被接纳），负=损伤（被拒/失信）
    kind: Literal["companionship", "accepted_help", "rejection", "betrayal", "crisis_side_by_side"]
    note: str = ""


class DynamicRapportModel:
    """羁绊由事件历练涌现：阈值推进、恶性事件可降级（不搞亲密度死表）。

    阈值是**可测试参数**而非宪法常量：累计权重 ≥20 → FAMILIAR；
    ≥60 且至少一次「危机并肩」→ TRUSTED_WINGMAN； betrayal 直接降一档。
    """

    FAMILIAR_THRESHOLD = 20
    WINGMAN_THRESHOLD = 60

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[RapportEvent] = []
        self._weight = 0
        self._crisis_shared = 0

    def experience(self, event: RapportEvent) -> RapportTier:
        require_aware(event.at, "event.at")
        with self._lock:
            self._events.append(event)
            if event.kind == "betrayal":
                # 恶性事件：立即降档（莫逆→伙伴，伙伴→陌生）
                self._weight = min(self._weight, self.FAMILIAR_THRESHOLD - 1)
                if self._weight >= self.FAMILIAR_THRESHOLD:
                    self._weight = self.FAMILIAR_THRESHOLD - 1
            else:
                self._weight += event.weight
                if event.kind == "crisis_side_by_side":
                    self._crisis_shared += 1
            return self.tier()

    def tier(self) -> RapportTier:
        with self._lock:
            if self._weight >= self.WINGMAN_THRESHOLD and self._crisis_shared >= 1:
                return RapportTier.TRUSTED_WINGMAN
            if self._weight >= self.FAMILIAR_THRESHOLD:
                return RapportTier.FAMILIAR
            return RapportTier.STRANGER

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "events": len(self._events),
                "weight": self._weight,
                "crisis_shared": self._crisis_shared,
            }


# ----------------------------------------------------------------------
# 像人姿态决策机
# ----------------------------------------------------------------------

class ResponsePosture(StrEnum):
    SILENCE = "SILENCE"                      # 沉默也是帮助（§5）
    HAPTIC_NUDGE = "HAPTIC_NUDGE"            # 一声单次微震提醒（§98-1）
    CRITICAL_SPOKEN = "CRITICAL_SPOKEN"      # 骨传导直言（果断开口）


class EventUrgency(IntEnum):
    TRIVIA = 10           # 日常琐事（可说可不说）
    NORMAL = 30           # 一般提醒
    HIGH = 60             # 重要事务（欺诈阻击/合同违约）
    P0_LIFE_SAFETY = 100  # 生命安全（早搏/跌倒）


class PostureContext(BaseModel):
    """姿态决策输入（全部为机械可判定字段，语义话术留给大模型）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    urgency: EventUrgency
    is_deep_sleep: StrictBool = False
    in_focus_work: StrictBool = False
    in_cooldown: StrictBool = False
    fraud_signal: StrictBool = False       # 如：老王再次开口借钱
    at: datetime

    @model_validator(mode="after")
    def _validate(self) -> "PostureContext":
        require_aware(self.at, "at")
        return self


class HumanlikeResponsePostureDecider:
    """姿态决策：该沉默时沉默，该直言时毫不犹豫。

    规则序（结构性先验，非话术模板）：
    1. P0 生命安全 → CRITICAL_SPOKEN（旁路睡眠/冷却/羁绊，生死第一）；
    2. 欺诈信号 + 任何羁绊档 → CRITICAL_SPOKEN（莫逆之交必须拦，
       陌生人也要明说——绝对诚实压倒礼貌）；
    3. HIGH 事务 → 熟识以上 HAPTIC_NUDGE；陌生人冷却期 SILENCE；
    4. NORMAL/琐事 → 深睡/专注/冷却一律 SILENCE；FAMILIAR+ 闲暇微震；
    5. TRIVIA + STRANGER → 永远 SILENCE（不烦人）。
    """

    def decide(self, ctx: PostureContext, rapport: RapportTier) -> ResponsePosture:
        if ctx.urgency is EventUrgency.P0_LIFE_SAFETY:
            return ResponsePosture.CRITICAL_SPOKEN
        if ctx.fraud_signal:
            return ResponsePosture.CRITICAL_SPOKEN
        if ctx.urgency is EventUrgency.HIGH:
            if rapport is RapportTier.STRANGER and ctx.in_cooldown:
                return ResponsePosture.SILENCE
            return ResponsePosture.HAPTIC_NUDGE
        # NORMAL / TRIVIA
        if ctx.is_deep_sleep or ctx.in_focus_work or ctx.in_cooldown:
            return ResponsePosture.SILENCE
        if ctx.urgency is EventUrgency.NORMAL and rapport is not RapportTier.STRANGER:
            return ResponsePosture.HAPTIC_NUDGE
        return ResponsePosture.SILENCE
