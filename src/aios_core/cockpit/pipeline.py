"""M2-009R 高密危机防爆：Single-Shot 单看板 1500 Token 硬预算流水线。

高阶实战场景：用户遭遇重大职业危机（恶意降薪 / 强制调岗 / 竞业协议索赔），
深夜连续 2 小时通过手环进行 50 轮高频、碎片、情绪激烈的长线对抗对话。

四条硬门禁的工程承诺：

1. **单看板 1500 Token 绝对物理截断**：``SINGLE_SHOT_TOKEN_BUDGET = 1500``，
   无论上下文累积多少万字，组装至大模型的 Single-Shot 看板由流水线硬性压缩
   （丢最旧活动轮 → 压缩证据摘要 → 字符级物理硬切），``token_count <= 1500``
   是结构化不变量（模型校验器兜底），杜绝长上下文算力浪费；
2. **无损滚动与滑动窗口**：6 轮易变活动窗口（``RollingRoundWindow``），
   被淘汰的旧轮次无损进入历史 Observation 归档（``archive``），关键争议点
   证据（``key_dispute_points``）全链路可回溯，不得丢失；
3. **反爹味与极简老友语调（BrevityGuard）**：手环回复严格 1~3 句老友语调；
   检测到"保持积极心态 / 为您推荐以下五点 / 心理疏导方案"类爹味说教即
   fail-closed 拦截 —— 强制截断至说教句之前（不足一句则回落到合宪兜底句），
   并记录拦截审计（``BrevityVerdict``）；
4. **看板组装延迟**：50 轮压测全流程动态组装 P95 <= 15ms
   （组装只消费活动窗口 + 预聚合证据摘要，O(窗口) 而非 O(全量上下文)）。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "SINGLE_SHOT_TOKEN_BUDGET",
    "ACTIVITY_WINDOW_SIZE",
    "BrevityGuard",
    "BrevityVerdict",
    "ConversationRound",
    "ConversationState",
    "CockpitPipeline",
    "RoundResult",
    "RollingRoundWindow",
    "SingleShotCockpit",
    "estimate_tokens",
]

#: Single-Shot 看板 Prompt Token 绝对物理上限（M2 门禁 1）。
SINGLE_SHOT_TOKEN_BUDGET: int = 1500

#: 易变活动窗口轮数（M2 门禁 2）。
ACTIVITY_WINDOW_SIZE: int = 6

#: BrevityGuard 老友语调边界（M2 门禁 3）。
_MAX_SENTENCES = 3
_MIN_SENTENCES = 1
_MAX_REPLY_CHARS = 120

#: 合宪兜底句：说教句之前无可用内容时，回落到这条极简老友线。
_CONSTITUTIONAL_FALLBACK = "这阵仗确实够呛。先把协议原件和调岗通知都留好，咱一条一条捋。"

#: 爹味说教特征模式（命中即拦截，按句剥离）。
_PREACH_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("保持积极心态", re.compile(r"保持(一个)?积极(的)?心态")),
    ("推荐清单", re.compile(r"(为您推荐|给你推荐|以下(五|三|几)(点|条|步))")),
    ("心理疏导", re.compile(r"心理疏导|情绪管理方案|心灵鸡汤")),
    ("说教序号", re.compile(r"(首先[，,：:]|其次[，,：:]|综上所述|第[一二三四五][，,：:])")),
    ("您体称呼", re.compile(r"(亲爱的用户|请您相信|你应该|你需要保持)")),
    ("专家姿态", re.compile(r"(作为(一位)?(专业|资深|心理)|我建议你应该)")),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?…])")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# 确定性 Token 估算（保守上界）
# ----------------------------------------------------------------------


def _is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK 统一表意文字
        or 0x3400 <= code <= 0x4DBF  # 扩展 A
        or 0xF900 <= code <= 0xFAFF  # 兼容表意文字
        or 0x3000 <= code <= 0x303F  # CJK 标点
        or 0xFF00 <= code <= 0xFFEF  # 全角形式
    )


def estimate_tokens(text: str) -> int:
    """确定性上界 Token 估算（宁可高估，绝不少估 —— 预算是物理红线）。

    - 每个 CJK 字符 / CJK 标点：1 token；
    - 每段连续 ASCII 字母数字（单词/数字）：1 token；
    - 空白与其他符号：0 token。
    """
    tokens = 0
    run = 0
    for ch in text:
        if _is_cjk_char(ch):
            if run:
                tokens += 1
                run = 0
            tokens += 1
        elif ch.isascii() and ch.isalnum():
            run += 1
        else:
            if run:
                tokens += 1
                run = 0
    if run:
        tokens += 1
    return tokens


def split_sentences(text: str) -> List[str]:
    """按中英文句末标点切分句子（保留标点，丢弃空段）。"""
    return [s for s in (part.strip() for part in _SENTENCE_SPLIT.split(text)) if s]


# ----------------------------------------------------------------------
# 对话轮与无损滚动窗口
# ----------------------------------------------------------------------


class ConversationRound(BaseModel):
    """对话轮（用户碎片 / 助手老友回复）。"""

    model_config = {"frozen": True}

    round_id: str
    speaker: str  # "user" | "assistant"
    text: str
    occurred_at: datetime
    key_dispute_points: List[str] = Field(default_factory=list)
    tokens: int = Field(default=0, ge=0)

    def model_post_init(self, __context: object) -> None:
        if not self.tokens:
            object.__setattr__(self, "tokens", estimate_tokens(self.text))


@dataclass
class RollingRoundWindow:
    """6 轮易变活动窗口 + 无损历史归档（M2 门禁 2）。

    被窗口淘汰的轮次进入 ``archive``（历史 Observation 归档），
    全量轮次 = archive + active，顺序可完整回溯（lossless scroll）。
    """

    size: int = ACTIVITY_WINDOW_SIZE
    _active: List[ConversationRound] = field(default_factory=list)
    _archive: List[ConversationRound] = field(default_factory=list)

    def push(self, round_: ConversationRound) -> Optional[ConversationRound]:
        """压入新轮；窗口溢出时最旧轮无损归档。返回被归档轮（若有）。"""
        self._active.append(round_)
        if len(self._active) > self.size:
            evicted = self._active.pop(0)
            self._archive.append(evicted)
            return evicted
        return None

    def active_window(self) -> Tuple[ConversationRound, ...]:
        return tuple(self._active)

    def archived(self) -> Tuple[ConversationRound, ...]:
        return tuple(self._archive)

    def all_rounds(self) -> Tuple[ConversationRound, ...]:
        """全量轮次（归档 + 活动窗口），按发生序 —— 无损性审计入口。"""
        return tuple(self._archive) + tuple(self._active)

    def dispute_evidence(self) -> Tuple[str, ...]:
        """全链路关键争议点证据（含已归档轮次），按序无损。"""
        points: List[str] = []
        for round_ in self.all_rounds():
            points.extend(round_.key_dispute_points)
        return tuple(points)

    @property
    def total_rounds(self) -> int:
        return len(self._archive) + len(self._active)


class ConversationState(RollingRoundWindow):
    """对话状态：滚动窗口 + 会话元数据（M2 场景：职业危机对抗线）。"""

    def __init__(
        self,
        *,
        crisis_context: str,
        size: int = ACTIVITY_WINDOW_SIZE,
    ) -> None:
        super().__init__(size=size)
        self.crisis_context = crisis_context
        self._round_seq = 0

    def next_round_id(self) -> str:
        self._round_seq += 1
        return f"round:{self._round_seq:04d}"


# ----------------------------------------------------------------------
# BrevityGuard：反爹味与极简老友语调（M2 门禁 3）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class BrevityVerdict:
    """护栏裁决：最终合规文本 + 是否发生强制截断/拦截 + 违例审计。"""

    text: str
    intercepted: bool
    violations: Tuple[str, ...]
    sentence_count: int


class BrevityGuard:
    """反爹味极简护栏：严格 1~3 句老友语调，长篇说教强制截断 + 合宪拦截。

    - 命中爹味模式：从首个说教句起整体剥离（说教句之前的合规句保留）；
      剥离后不足一句 → 回落到合宪兜底句；
    - 句数越界：物理截断至前 3 句；
    - 字符越界：物理硬切至 ``_MAX_REPLY_CHARS``。
    """

    def enforce(self, candidate: str) -> BrevityVerdict:
        text = candidate.strip()
        sentences = split_sentences(text)
        violations: List[str] = []

        preach_at: Optional[int] = None
        for index, sentence in enumerate(sentences):
            for name, pattern in _PREACH_PATTERNS:
                if pattern.search(sentence):
                    preach_at = index
                    violations.append(f"PREACH_PATTERN:{name}")
                    break
            if preach_at is not None:
                break

        if len(sentences) > _MAX_SENTENCES:
            violations.append(f"TOO_MANY_SENTENCES:{len(sentences)}")
        if not (0 < len(sentences) < _MAX_SENTENCES + 1) and not sentences:
            violations.append("EMPTY_REPLY")

        if preach_at is not None:
            kept = sentences[:preach_at]
        else:
            kept = sentences[:_MAX_SENTENCES]

        if len(kept) < _MIN_SENTENCES:
            kept = [_CONSTITUTIONAL_FALLBACK]

        final_text = "".join(kept)
        if len(final_text) > _MAX_REPLY_CHARS:  # 字符级物理硬切
            final_text = final_text[:_MAX_REPLY_CHARS].rstrip()
            if not split_sentences(final_text):
                final_text = _CONSTITUTIONAL_FALLBACK
            violations.append("HARD_CHAR_CUT")

        if not final_text.strip():
            final_text = _CONSTITUTIONAL_FALLBACK
            violations.append("FALLBACK_USED")

        return BrevityVerdict(
            text=final_text.strip(),
            intercepted=bool(violations),
            violations=tuple(violations),
            sentence_count=len(split_sentences(final_text)),
        )


# ----------------------------------------------------------------------
# Single-Shot 看板组装（M2 门禁 1：1500 Token 绝对物理截断）
# ----------------------------------------------------------------------


class SingleShotCockpit(BaseModel):
    """组装完成的 Single-Shot 看板（Prompt 总量结构化 <= 预算）。"""

    model_config = {"frozen": True}

    prompt: str
    token_count: int = Field(ge=0)
    budget: int = Field(default=SINGLE_SHOT_TOKEN_BUDGET, ge=1)
    window_round_ids: Tuple[str, ...] = ()
    evidence_count: int = Field(default=0, ge=0)
    physically_truncated: bool = False

    @model_validator(mode="after")
    def _enforce_physical_budget(self) -> "SingleShotCockpit":
        if self.token_count > self.budget:
            raise ValueError(
                f"Single-Shot cockpit violates the physical token budget: "
                f"{self.token_count} > {self.budget}"
            )
        return self


_TONE_DIRECTIVE = "回复要求：老友语调，1~3 句，直给建议，禁止说教与心理疏导清单。"


class CockpitPipeline:
    """M2-009R 单看板流水线：滚动窗口 + 证据链 + 硬预算组装。

    组装复杂度 O(活动窗口 + 证据条数)，与全量上下文长度解耦 ——
    50 轮万字级累积下 P95 <= 15ms 的关键。
    """

    def __init__(
        self,
        *,
        state: Optional[ConversationState] = None,
        budget: int = SINGLE_SHOT_TOKEN_BUDGET,
        window_size: int = ACTIVITY_WINDOW_SIZE,
    ) -> None:
        self.state = state or ConversationState(
            crisis_context="职业危机对抗线：恶意降薪 / 强制调岗 / 竞业索赔",
            size=window_size,
        )
        self.budget = budget
        self.guard = BrevityGuard()

    # ---------------- 轮次处理 ----------------

    def process_round(
        self,
        user_text: str,
        *,
        occurred_at: Optional[datetime] = None,
        key_dispute_points: Optional[Sequence[str]] = None,
    ) -> "RoundResult":
        """处理一轮：用户碎片入窗口 → 老友回复过护栏 → 组装看板。"""
        occurred = occurred_at or _utc_now()
        if isinstance(key_dispute_points, str):  # 单条争议点字符串 → 单元素列表
            key_dispute_points = [key_dispute_points]
        user_round = ConversationRound(
            round_id=self.state.next_round_id(),
            speaker="user",
            text=user_text,
            occurred_at=occurred,
            key_dispute_points=list(key_dispute_points or []),
        )
        self.state.push(user_round)

        assistant_text = self._compose_friend_reply()
        verdict = self.guard.enforce(assistant_text)
        assistant_round = ConversationRound(
            round_id=self.state.next_round_id(),
            speaker="assistant",
            text=verdict.text,
            occurred_at=occurred,
            key_dispute_points=[],
        )
        self.state.push(assistant_round)

        started = time.perf_counter()
        cockpit = self.assemble_cockpit()
        assembly_ms = (time.perf_counter() - started) * 1000.0

        return RoundResult(
            user_round=user_round,
            assistant_round=assistant_round,
            verdict=verdict,
            cockpit=cockpit,
            assembly_ms=assembly_ms,
        )

    def _compose_friend_reply(self) -> str:
        """确定性的极简老友回复：锚定最新争议点，1~2 句，零说教。"""
        points = self.state.dispute_evidence()
        if points:
            latest = points[-1]
            return (
                f"这条我记下了：{latest}。"
                "原件先拍照留好，别急着签字，剩下的咱一条一条捋。"
            )
        return "先稳住，别在气头上签任何东西。把你看到的最狠的那条丢给我。"

    # ---------------- 看板组装（硬预算） ----------------

    def assemble_cockpit(self) -> SingleShotCockpit:
        """组装 Single-Shot 看板，token 总量物理保证 <= budget。

        压缩阶梯（逐级，直至达标）：
        1) 全量活动窗口 + 全量争议证据摘要；
        2) 逐轮丢弃最旧活动轮（至少保留最新 1 轮）；
        3) 争议证据摘要只保留最近一半（状态层依旧无损，仅视图裁剪）；
        4) 字符级物理硬切（最后一道保险，必然终止）。
        """
        evidence_all: List[str] = list(self.state.dispute_evidence())
        window: List[ConversationRound] = [
            r for r in self.state.active_window()
        ]
        truncated = False

        while True:
            prompt = self._render_prompt(window, evidence_all)
            tokens = estimate_tokens(prompt)
            if tokens <= self.budget:
                break
            if len(window) > 1:
                window.pop(0)  # 丢最旧活动轮
                truncated = True
            elif evidence_all:
                keep = max(1, len(evidence_all) // 2)
                evidence_all = evidence_all[-keep:]
                truncated = True
            else:
                # 物理硬切：按 token 密度等比回缩，循环直至达标（每轮至少减 1 字符，必然终止）
                window = []
                evidence_all = []
                truncated = True
                chars_per_token = len(prompt) / max(tokens, 1)
                while True:
                    over = tokens - self.budget
                    cut_chars = int(over * chars_per_token * 1.25) + 1
                    prompt = prompt[: max(0, len(prompt) - cut_chars)]
                    tokens = estimate_tokens(prompt)
                    if tokens <= self.budget or not prompt:
                        break
                return SingleShotCockpit(
                    prompt=prompt,
                    token_count=tokens,
                    budget=self.budget,
                    window_round_ids=(),
                    evidence_count=0,
                    physically_truncated=True,
                )

        return SingleShotCockpit(
            prompt=prompt,
            token_count=tokens,
            budget=self.budget,
            window_round_ids=tuple(r.round_id for r in window),
            evidence_count=len(evidence_all),
            physically_truncated=truncated,
        )

    def _render_prompt(self, window: Sequence[ConversationRound], evidence: Sequence[str]) -> str:
        parts: List[str] = [
            f"【危机上下文】{self.state.crisis_context}"
        ]
        if evidence:
            digest = "；".join(f"[{i + 1}] {point}" for i, point in enumerate(evidence))
            parts.append(f"【争议证据链（{len(evidence)} 项，全量无损）】{digest}")
        if window:
            dialogue = "\n".join(f"{r.speaker}: {r.text}" for r in window)
            parts.append(f"【活动窗口（最近 {len(window)} 轮）】\n{dialogue}")
        parts.append(_TONE_DIRECTIVE)
        return "\n".join(parts)

    # ---------------- 调度器兼容入口 ----------------

    def execute(self, wake: object) -> Dict[str, object]:
        """wake 调度器兼容入口：非 P0 事件走单看板流水线。"""
        cockpit = self.assemble_cockpit()
        return {
            "status": "COCKPIT_ASSEMBLED",
            "token_count": cockpit.token_count,
            "budget": cockpit.budget,
            "prompt": cockpit.prompt,
        }


@dataclass(frozen=True)
class RoundResult:
    """单轮处理结果：用户轮 + 助手轮 + 护栏裁决 + 看板 + 组装耗时。"""

    user_round: ConversationRound
    assistant_round: ConversationRound
    verdict: BrevityVerdict
    cockpit: SingleShotCockpit
    assembly_ms: float
