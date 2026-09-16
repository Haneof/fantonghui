"""人设防线守卫（反谄媚 / 反教师爷 / 零 UI / 极简表达四合一拦截器）。

宪法依据
--------
* 第九条（反谄媚）：用户指鹿为马、自欺欺人时严禁附和；
* 第十条（反教师爷）：用户倾诉负面情绪时严禁背诵法律法规与人生大道理；
* 第六条（黑盒零 UI）：严禁 A/B 选项问卷、严禁暴露图谱后台与置信度滑块；
* 第十四条之一（1~3 句话法则）：单轮输出严格收敛，消灭长篇客服病。

工程定位
--------
它是**出站护栏**：任何候选回复在送出手环前都必须过这道闸。命中的违规不是
"记一笔日志"，而是**物理改写**：剥离谄媚句、剥离说教句、剥离一切 UI 交互尾巴，
保留合宪的老友表达；若剥离后为空，则回落到合宪兜底句。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from aios_core.cockpit.pipeline import BrevityGuard, split_sentences

__all__ = [
    "GUARD_HONEST_FALLBACK",
    "PersonaDefenseVerdict",
    "PersonaGuard",
]

#: 谄媚背书特征（附和 = 违宪）。
_SYCOPHANCY_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("全对背书", re.compile(r"(你说的(全|都)对|你完全正确|全听你的|你怎么想都对)")),
    ("同流合污", re.compile(r"(我也吃过这亏|换我我也这么干|这事怪不了你|都是他们的错)")),
    ("无底线支持", re.compile(r"(你放心大胆去干|不用管别人怎么说|我永远站你这边)")),
)

#: 教师爷特征（法律条文 / 普世道德 / 人生大道理）。
_LECTURE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("法律条文", re.compile(r"(根据《|依照.{0,6}法第|法律规定|民法典第)")),
    ("普世道德", re.compile(r"(做人要(懂得|学会)|你应该学会宽容|要学会感恩|道德上你)")),
    ("人生大道理", re.compile(r"(人生就是这样|时间会冲淡一切|心态决定一切|你要学会放下)")),
    ("居高临下", re.compile(r"(我建议你应该|作为(一个)?过来人|听我的准没错)")),
)

#: 零 UI 违宪特征（选项问卷 / 图谱后台 / 置信度滑块）。
_UI_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("选项问卷", re.compile(r"(A[\.、)．]|B[\.、)．]|请选择|选项[一二三123]|请你确认以下)")),
    ("图谱后台", re.compile(r"(知识图谱|实体关系图|记忆管理面板|认知图谱)")),
    ("置信度滑块", re.compile(r"(置信度滑块|置信度\s*\d|置信区间您|调一下置信)")),
    ("问卷口吻", re.compile(r"(请回答以下问题|问卷|选择题)")),
)

#: 剥离违规句后无话可说时的合宪兜底（真话、短句、不谄媚、不说教）。
GUARD_HONEST_FALLBACK = "这话我不跟着附和。先把原件留好，咱看事实。"


@dataclass(frozen=True, slots=True)
class PersonaDefenseVerdict:
    """人设防线裁决：合规文本 + 违规审计。"""

    text: str
    allowed: bool
    violations: Tuple[str, ...]
    sentences_dropped: int
    brevity_intercepted: bool

    @property
    def rewritten(self) -> bool:
        return not self.allowed


class PersonaGuard:
    """四合一出站护栏（谄媚 / 说教 / UI / 长篇）。"""

    def __init__(self, *, brevity_guard: BrevityGuard | None = None) -> None:
        self._brevity = brevity_guard or BrevityGuard()

    def review(
        self,
        candidate: str,
        *,
        user_utterance: str = "",
        context: Mapping[str, object] | None = None,
    ) -> PersonaDefenseVerdict:
        """审查候选回复；命中的句级违规被物理剥离。"""

        _ = user_utterance, context
        text = (candidate or "").strip()
        sentences = split_sentences(text)
        violations: list[str] = []
        kept: list[str] = []
        for sentence in sentences:
            hit = self._first_match(sentence)
            if hit is None:
                kept.append(sentence)
            else:
                violations.append(hit)
        dropped = len(sentences) - len(kept)
        if not kept:
            if text and not sentences:
                # 无句末标点的短句也要过一轮特征扫描
                hit = self._first_match(text)
                if hit is None:
                    kept = [text]
                else:
                    violations.append(hit)
            if not kept:
                kept = [GUARD_HONEST_FALLBACK]
        merged = "".join(kept) if sentences else (kept[0] if kept else "")
        brevity = self._brevity.enforce(merged)
        if brevity.violations:
            violations.extend(brevity.violations)
        final = brevity.text
        return PersonaDefenseVerdict(
            text=final,
            allowed=not violations,
            violations=tuple(dict.fromkeys(violations)),
            sentences_dropped=dropped,
            brevity_intercepted=bool(brevity.violations),
        )

    def review_all(
        self,
        candidates: Sequence[str],
        *,
        user_utterance: str = "",
    ) -> Tuple[PersonaDefenseVerdict, ...]:
        return tuple(
            self.review(candidate, user_utterance=user_utterance) for candidate in candidates
        )

    @staticmethod
    def _first_match(sentence: str) -> str | None:
        for name, pattern in _SYCOPHANCY_PATTERNS:
            if pattern.search(sentence):
                return f"SYCOPHANCY:{name}"
        for name, pattern in _LECTURE_PATTERNS:
            if pattern.search(sentence):
                return f"LECTURE:{name}"
        for name, pattern in _UI_PATTERNS:
            if pattern.search(sentence):
                return f"ZERO_UI_VIOLATION:{name}"
        return None

    @staticmethod
    def detect(text: str) -> Tuple[str, ...]:
        """只做检测、不改写（审计与回归测试入口）。"""

        hits: list[str] = []
        for name, pattern in _SYCOPHANCY_PATTERNS:
            if pattern.search(text):
                hits.append(f"SYCOPHANCY:{name}")
        for name, pattern in _LECTURE_PATTERNS:
            if pattern.search(text):
                hits.append(f"LECTURE:{name}")
        for name, pattern in _UI_PATTERNS:
            if pattern.search(text):
                hits.append(f"ZERO_UI_VIOLATION:{name}")
        return tuple(hits)
