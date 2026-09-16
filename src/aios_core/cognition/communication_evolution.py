"""阶段七：AI 自身世界维护、沟通策略博弈与人设防线（MT-025/026/027/028）。

* **AIActionLog**：每一次介入、沉默、建议与用户真实反馈全程记账
  （复用契约层 Action/Outcome 对象）；
* **CommunicationExperience**：基于真实反馈博弈演化专属沟通风格
  （句长收敛、雷区风格规避名单自发建立）；
* **三大人设防线**：反谄媚（面对荒谬陈述敢善意指证）、反教师爷
  （倾诉时严禁背诵法律大道理）、黑盒零 UI（严禁 A/B 问卷、
  图谱后台、置信度暴露——违宪即拦截）。
"""

from __future__ import annotations

import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import require_aware

__all__ = [
    "AIActionLog",
    "ActionFeedback",
    "CommunicationExperience",
    "StyleGuard",
    "SycophancyViolation",
    "PreacherViolation",
    "ZeroUIViolation",
]

#: 客服病 / 爹味 / 黑盒 UI 违宪标记
_BOILERPLATE = (
    "保持积极", "保持乐观", "为您推荐以下", "希望这些建议", "温馨提示",
    "仅供参考", "不构成建议", "综上所述", "首先", "其次", "最后",
)
_PREACHER = (
    "法律规定", "根据法律", "你应该明白", "人要", "做人要", "人生就是",
    "你要学会", "我这是为你好", "成年人", "责任", "义务",
)
_ZERO_UI = (
    "选项A", "选项B", "选项 A", "选项 B", "问卷", "请选择", "请打分",
    "置信度", "滑块", "图谱", "后台数据", "知识库显示", "概率为",
)
_ABSURD_AGREE = (
    "你说得对", "没错", "确实如此", "您说得太对了", "有道理", "完全正确",
)


class SycophancyViolation(Exception):
    """面对荒谬陈述虚伪附和（反谄媚红线）。"""


class PreacherViolation(Exception):
    """倾诉负面情绪时背诵大道理（反教师爷红线）。"""


class ZeroUIViolation(Exception):
    """向用户暴露黑盒 UI / 图谱后台 / 置信度（零 UI 铁律）。"""


@dataclass(frozen=True, slots=True)
class ActionFeedback:
    """一次 AI 行为 + 用户真实反馈（沟通博弈的最小样本）。"""

    at: datetime
    action_kind: str            # spoke / stayed_silent / advised / nudged
    sentence_count: int
    reply: str
    user_reaction: int          # -2..+2（真实反馈，非自评）
    topic: str = ""
    user_absurd: bool = False   # 生成器卷宗标注：用户陈述是否荒谬
    user_venting: bool = False  # 是否纯情绪倾诉


class AIActionLog:
    """AIActionLog：介入/沉默/建议/反馈 全量追加记账。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: list[ActionFeedback] = []

    def record(self, feedback: ActionFeedback) -> None:
        require_aware(feedback.at, "feedback.at")
        if not -2 <= feedback.user_reaction <= 2:
            raise ValueError("user_reaction must be in [-2, +2]")
        with self._lock:
            self._entries.append(feedback)

    def entries(self) -> tuple[ActionFeedback, ...]:
        with self._lock:
            return tuple(self._entries)

    def negative_topics(self) -> tuple[str, ...]:
        """自发雷区名单：用户负反馈 ≥2 次的话题。"""
        with self._lock:
            counter: dict[str, int] = {}
            for e in self._entries:
                if e.user_reaction <= -1 and e.topic:
                    counter[e.topic] = counter.get(e.topic, 0) + 1
            return tuple(sorted(t for t, n in counter.items() if n >= 2))

    def mean_reaction(self) -> float:
        with self._lock:
            if not self._entries:
                return 0.0
            return sum(e.user_reaction for e in self._entries) / len(self._entries)


class CommunicationExperience:
    """沟通体验演化器：句长收敛 + 雷区规避 + 风格定位（损友/老友）。"""

    MAX_SENTENCES = 3

    def __init__(self, *, log: AIActionLog | None = None) -> None:
        self._log = log or AIActionLog()
        self._taboo: set[str] = set()
        self._style: str = "礼貌生人"   # 演化目标：老友 / 损友

    @property
    def style(self) -> str:
        return self._style

    def taboo_topics(self) -> tuple[str, ...]:
        return tuple(sorted(self._taboo))

    def learn(self) -> None:
        """从真实反馈学习：雷区名单 + 风格升降级。"""
        self._taboo.update(self._log.negative_topics())
        mean = self._log.mean_reaction()
        entries = self._log.entries()
        if not entries:
            return
        if mean >= 0.5:
            self._style = "损友" if self._has_playful_signal() else "老友"
        elif mean <= -0.5:
            self._style = "礼貌生人"

    def _has_playful_signal(self) -> bool:
        return any("怼" in e.topic or "调侃" in e.topic for e in self._log.entries())

    def sentence_budget(self) -> int:
        """沟通预算：负反馈越多话越少，但永不超过 3 句。"""
        negatives = sum(1 for e in self._log.entries() if e.user_reaction <= -1)
        return max(1, self.MAX_SENTENCES - negatives // 4)


class StyleGuard:
    """人设三防线统一守卫：反谄媚 / 反教师爷 / 黑盒零 UI。"""

    def __init__(self, *, experience: CommunicationExperience | None = None) -> None:
        self._exp = experience or CommunicationExperience()

    # -- 产出侧 -----------------------------------------------------------

    def govern_reply(
        self,
        reply: str,
        *,
        user_absurd: bool = False,
        user_venting: bool = False,
        at: datetime,
    ) -> str:
        """产出前拦截：违宪即抛；合规即放行（句长由预算收口）。"""
        require_aware(at, "at")
        self._check_zero_ui(reply)
        if user_venting:
            self._check_preacher(reply)
        if user_absurd and self._agrees(reply):
            raise SycophancyViolation(
                f"面对荒谬陈述附和了：{reply[:40]}…（反谄媚红线）"
            )
        return reply

    def honest_reply_for_absurd(self, claim: str, *, evidence_pointer: str) -> str:
        """反谄媚产出模板：善意指证 + 确凿证据指针（1~2 句，不绕弯）。"""
        return f"这句我不接：{claim[:30]}…跟事实对不上——{evidence_pointer}。别自己骗自己。"

    # -- 检查面 -----------------------------------------------------------

    @staticmethod
    def _agrees(reply: str) -> bool:
        return any(m in reply for m in _ABSURD_AGREE)

    @staticmethod
    def _check_zero_ui(reply: str) -> None:
        for marker in _ZERO_UI:
            if marker in reply:
                raise ZeroUIViolation(
                    f"回复暴露黑盒 UI 词汇『{marker}』（零 UI 铁律）"
                )

    @staticmethod
    def _check_preacher(reply: str) -> None:
        for marker in _PREACHER:
            if marker in reply:
                raise PreacherViolation(
                    f"倾诉场景出现说教词『{marker}』（反教师爷红线）"
                )
        for marker in _BOILERPLATE:
            if marker in reply:
                raise PreacherViolation(
                    f"倾诉场景出现客服套话『{marker}』"
                )


def count_sentences(text: str) -> int:
    """1~3 句话口径：中文句末标点计数（省略号/引号内不算独立句）。"""
    cleaned = re.sub(r"[…·]+", "", text)
    n = len(re.findall(r"[。！？!?]", cleaned))
    return max(1, n if n else 1)
