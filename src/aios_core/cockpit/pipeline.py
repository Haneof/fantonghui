"""M2-009R 单看板 Token 封套流水线（Cockpit Manifest Pipeline）。

高阶实战场景：用户遭遇重大职业危机（恶意降薪、强制调岗、竞业协议索赔），
深夜 2 小时内经手环连续 50 轮高频、碎片、情绪激烈的对抗对话。

四大铁律（工程结构保证）：

1. **1500 Token 绝对物理截断**：看板按分层预算装配，每层独立封顶，
   总量由 ``CockpitManifest`` 模型校验器强制 ≤ 预算——超预算不是告警，
   是构造失败（bug 即测试失败）。被截断内容全部进入省略索引（指针，
   绝不静默丢弃）；
2. **无损滚动**：6 轮易变窗口，被淘汰轮次完整封装为 ``Observation``
   归档对象（原话逐字节保留），关键争议点证据永可下钻（V3 §85-2）；
3. **Brevity Guard（反爹味）**：手环回复 1~3 句硬预算 + 爹味模式
   合宪性拦截，说教注入被强制截断并记录违例（V3 §14-1 / §15-16）；
4. **组装延迟**：装配只触碰窗口与定长层（O(预算) 不 O(历史)），50 轮
   压测 P95 ≤ 15ms。

宪法依据：V3 §84（单次看盘聚合，严禁多轮握手）、§85-2（滚动窗口 +
增量萃取 + 省略索引）、§15-16（一票否决爹味排比）。
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from aios_core.contracts.models import Observation
from aios_core.contracts.time import TemporalExtent, require_aware

__all__ = [
    "BrevityGuard",
    "CockpitManifest",
    "ConversationTurn",
    "CrisisDialoguePipeline",
    "GovernedReply",
    "MANIFEST_TOKEN_BUDGET",
    "OmissionEntry",
    "WINDOW_TURNS",
    "estimate_tokens",
]

#: 单次看板 Token 总预算（绝对物理上限）
MANIFEST_TOKEN_BUDGET = 1500
#: 前台活跃滑动窗口轮数（V3 §85-2：最近 5~8 轮取 6）
WINDOW_TURNS = 6
#: 单轮输出句子硬预算（V3 §14-1 单轮 1~3 句法则）
REPLY_SENTENCE_LIMIT = 3

_CJK_CHAR = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]")


def estimate_tokens(text: str) -> int:
    """确定性保守 Token 估算：CJK 字符≈1 token/字，其余按 4 字符/token。

    估算器刻意偏保守（宁可高估），保证 1500 硬封顶在任何真实分词器下
    都不会突破。纯函数、无外部依赖、跨平台可重放。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if _CJK_CHAR.match(ch))
    other = len(text) - cjk
    return cjk + (other + 3) // 4


class ConversationTurn(BaseModel):
    """对话轮次（前台窗口的最小单元）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_index: StrictInt = Field(ge=1)
    speaker: Literal["user", "ai"]
    text: StrictStr = Field(min_length=1)
    at: datetime

    @model_validator(mode="after")
    def _validate(self) -> "ConversationTurn":
        require_aware(self.at, "at")
        return self


class OmissionEntry(BaseModel):
    """省略索引：被截断内容的可复查指针（数量 + 入口，不是内容）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: StrictStr
    omitted_items: StrictInt = Field(ge=0)
    omitted_tokens: StrictInt = Field(ge=0)
    resume_pointer: StrictStr = Field(min_length=1)


class CockpitManifest(BaseModel):
    """单次看盘看板：一次性交付大模型的全部上下文。

    ``token_total <= token_budget`` 由模型校验器强制——任何装配 bug
    都在构造期爆炸，绝不允许超预算看板流入大模型。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: StrictStr
    wake_reason: StrictStr
    layers: dict[str, str]
    layer_tokens: dict[str, int]
    token_total: StrictInt = Field(ge=0)
    token_budget: StrictInt = Field(ge=1)
    omission_index: tuple[OmissionEntry, ...] = Field(default=())
    window_turns_included: StrictInt = Field(ge=0)
    window_turn_range: tuple[int, int] | None = None
    assembled_at: datetime

    @model_validator(mode="after")
    def enforce_hard_cap(self) -> "CockpitManifest":
        require_aware(self.assembled_at, "assembled_at")
        if self.token_total > self.token_budget:
            raise ValueError(
                f"manifest hard cap breached: {self.token_total} > "
                f"{self.token_budget} tokens — assembly bug, never ship"
            )
        if sum(self.layer_tokens.values()) != self.token_total:
            raise ValueError("layer token accounting mismatch")
        return self


# ----------------------------------------------------------------------
# 滚动窗口与无损归档
# ----------------------------------------------------------------------

class _RollingWindow:
    """固定容量轮次窗口；逐出轮次经回调无损归档。"""

    def __init__(
        self,
        capacity: int,
        on_evict: Callable[[ConversationTurn], Observation],
    ) -> None:
        self._items: deque[ConversationTurn] = deque()
        self._capacity = capacity
        self._on_evict = on_evict

    def append(self, turn: ConversationTurn) -> list[Observation]:
        archived: list[Observation] = []
        self._items.append(turn)
        while len(self._items) > self._capacity:
            evicted = self._items.popleft()
            archived.append(self._on_evict(evicted))  # 逐出≠丢弃
        return archived

    def snapshot(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._items)


# ----------------------------------------------------------------------
# Brevity Guard（反爹味 / 1~3 句老友语调治理）
# ----------------------------------------------------------------------

#: 爹味说教模式（合宪性拦截清单：V3 §15-16 一票否决项的输出侧探针）
PREACHY_PATTERNS: tuple[re[str], ...] = tuple(  # type: ignore[arg-type]
    re.compile(p)
    for p in (
        r"保持(一个)?(积极|乐观)(的)?(心态|心情)",
        r"心理疏导",
        r"为您推荐以下",
        r"以下[一二三四五六七八九十\d]+\s*[点条步]",
        r"建议您(应当|最好|不妨)",
        r"首先.*其次.*(再次|最后)",
        r"人生(就是|总是)",
        r"要相信(生活|明天|自己)",
        r"[一二三四五]\u3001",
        r"\d+\s*\u3001",
    )
)

_SENTENCE_SPLIT = re.compile(r"([。！？!?…]+|\n+)")


def split_sentences(text: str) -> list[str]:
    """按中英文终止符与换行切句，保留终止符，保证重组无损截断。"""
    parts = _SENTENCE_SPLIT.split(text)
    sentences: list[str] = []
    buffer = ""
    for part in parts:
        if part is None:
            continue
        buffer += part
        if _SENTENCE_SPLIT.fullmatch(part):
            if buffer.strip():
                sentences.append(buffer)
            buffer = ""
    if buffer.strip():
        sentences.append(buffer)
    return sentences


class GovernedReply(BaseModel):
    """治理后的输出计划：句数硬预算内、违例可审计。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: StrictStr
    # 紧急安全通道豁免句数上限（急救指令不受 3 句约束），故不设 le 约束；
    # 非紧急路径的 ≤3 由 BrevityGuard 截断逻辑结构性保证。
    sentence_count: StrictInt = Field(ge=0)
    channel: Literal["text_card", "bone_audio", "haptic_only", "silence"]
    truncated: bool = False
    preaching_detected: bool = False
    violations: tuple[StrictStr, ...] = Field(default=())
    original_sentence_count: StrictInt = Field(ge=0)
    original_tokens: StrictInt = Field(ge=0)
    reply_tokens: StrictInt = Field(ge=0)


class BrevityGuard:
    """输出风格治理器：1~3 句硬预算 + 爹味合宪性拦截。

    治理顺序：先判定爹味（违例记录），再执行强制截断（保留前 3 个完整
    句）。紧急安全通道豁免长度限制（急救指令不受 3 句约束）。
    """

    def govern(
        self,
        draft: str,
        *,
        channel: Literal[
            "text_card", "bone_audio", "haptic_only", "silence"
        ] = "text_card",
        emergency: bool = False,
    ) -> GovernedReply:
        if channel == "silence":
            return GovernedReply(
                text="",
                sentence_count=0,
                channel=channel,
                original_sentence_count=0,
                original_tokens=estimate_tokens(draft),
                reply_tokens=0,
            )
        sentences = split_sentences(draft)
        preaching = any(p.search(draft) for p in PREACHY_PATTERNS)
        violations: list[str] = []
        truncated = False
        if preaching:
            violations.append("PREACHINESS_INTERCEPTED")
        if not emergency:
            candidates = sentences
            if preaching:
                # 先整句剔除爹味句（说教清单/鸡汤模板不留残句）
                candidates = [
                    s for s in sentences
                    if not any(p.search(s) for p in PREACHY_PATTERNS)
                ]
                if len(candidates) < len(sentences):
                    truncated = True
                if not candidates:
                    # 全稿爹味：治理降级为沉默（该闭嘴就闭嘴，V3 §14-1）
                    return GovernedReply(
                        text="",
                        sentence_count=0,
                        channel=channel,
                        truncated=True,
                        preaching_detected=True,
                        violations=tuple(
                            [*violations, "ALL_SENTENCES_PREACHY_SILENCED"]
                        ),
                        original_sentence_count=len(sentences),
                        original_tokens=estimate_tokens(draft),
                        reply_tokens=0,
                    )
            if len(candidates) > REPLY_SENTENCE_LIMIT:
                candidates = candidates[:REPLY_SENTENCE_LIMIT]
                truncated = True
                violations.append("BREVITY_LIMIT_EXCEEDED")
            output_sentences = candidates
        else:
            output_sentences = sentences
        governed_text = "".join(output_sentences)
        return GovernedReply(
            text=governed_text,
            sentence_count=len(split_sentences(governed_text)),
            channel=channel,
            truncated=truncated,
            preaching_detected=preaching,
            violations=tuple(violations),
            original_sentence_count=len(sentences),
            original_tokens=estimate_tokens(draft),
            reply_tokens=estimate_tokens(governed_text),
        )


# ----------------------------------------------------------------------
# 危机对话流水线（窗口 + 归档 + 看板装配）
# ----------------------------------------------------------------------

#: 分层 Token 预算（占比之和 = 100%，逐层独立封顶）
_LAYER_CAPS: dict[str, float] = {
    "system_preamble": 0.05,
    "wake_reason": 0.08,
    "self_mirror": 0.06,
    "world_digest": 0.10,
    "ready_tasks": 0.14,
    "recall_digest": 0.16,
    "session_digest": 0.05,
    "conversation_window": 0.36,
}


class CrisisDialoguePipeline:
    """深夜长线危机对话的单看板流水线。"""

    def __init__(
        self,
        *,
        session_id: str,
        subject_id: str = "user_founder",
        token_budget: int = MANIFEST_TOKEN_BUDGET,
        window_turns: int = WINDOW_TURNS,
        archive_sink: Callable[[Observation], None] | None = None,
        guard: BrevityGuard | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.session_id = session_id
        self.subject_id = subject_id
        self.token_budget = token_budget
        self._archived: list[Observation] = []
        self._archive_sink = archive_sink or self._archived.append
        self._guard = guard or BrevityGuard()
        self.style_violations: list[GovernedReply] = []
        self._turn_counter = 0
        self._window = _RollingWindow(
            window_turns, self._archive_turn
        )

    # -- 输入侧 ---------------------------------------------------------

    def push_turn(self, speaker: Literal["user", "ai"], text: str, at: datetime) -> list[Observation]:
        """推进一轮对话；被逐出窗口的轮次无损封装为 Observation 归档。"""
        require_aware(at, "at")
        with self._lock:
            self._turn_counter += 1
            turn = ConversationTurn(
                turn_index=self._turn_counter, speaker=speaker, text=text, at=at
            )
            return self._window.append(turn)

    # -- 装配侧 ---------------------------------------------------------

    def assemble_manifest(
        self,
        *,
        wake_reason: str,
        world_digest: str = "",
        self_mirror: str = "",
        ready_tasks: Sequence[str] = (),
        recall_digest: Sequence[str] = (),
        session_digest: str = "",
        now: datetime | None = None,
    ) -> CockpitManifest:
        """按分层预算装配单次看板；总量 ≤ token_budget 由模型校验器兜底。"""
        assembled_at = now or datetime.now().astimezone()
        omissions: list[OmissionEntry] = []
        layers: dict[str, str] = {}
        layer_tokens: dict[str, int] = {}

        window_snapshot = self._window.snapshot()
        window_turn_range = (
            (window_snapshot[0].turn_index, window_snapshot[-1].turn_index)
            if window_snapshot
            else None
        )
        archived_span = (
            f"conversation_archive:turns_1..{self._turn_counter - len(window_snapshot)}"
            if self._turn_counter > len(window_snapshot)
            else "conversation_archive:empty"
        )

        sources: dict[str, Any] = {
            "system_preamble": (
                "AIOS 单次看盘：严禁复述看板；严禁长篇说教；输出 1~3 句老友语调。"
            ),
            "wake_reason": wake_reason,
            "self_mirror": self_mirror,
            "world_digest": world_digest,
            "ready_tasks": list(ready_tasks),
            "recall_digest": list(recall_digest),
            "session_digest": session_digest,
            "conversation_window": [
                f"[T{t.turn_index:03d} {t.speaker}] {t.text}"
                for t in window_snapshot
            ],
        }

        for layer, content in sources.items():
            cap = max(8, int(self.token_budget * _LAYER_CAPS[layer]))
            if isinstance(content, str):
                rendered, omitted_items, omitted_tokens = self._pack_text(
                    content, cap
                )
            else:
                rendered, omitted_items, omitted_tokens = self._pack_items(
                    content, cap
                )
            layers[layer] = rendered
            layer_tokens[layer] = estimate_tokens(rendered)
            if omitted_items:
                omissions.append(
                    OmissionEntry(
                        layer=layer,
                        omitted_items=omitted_items,
                        omitted_tokens=omitted_tokens,
                        resume_pointer=(
                            archived_span
                            if layer == "conversation_window"
                            else f"{layer}@full_context"
                        ),
                    )
                )

        manifest = CockpitManifest(
            session_id=self.session_id,
            wake_reason=wake_reason,
            layers=layers,
            layer_tokens=layer_tokens,
            token_total=sum(layer_tokens.values()),
            token_budget=self.token_budget,
            omission_index=tuple(omissions),
            window_turns_included=len(window_snapshot),
            window_turn_range=window_turn_range,
            assembled_at=assembled_at,
        )
        return manifest

    # -- 输出侧 ---------------------------------------------------------

    def guard_reply(
        self,
        draft: str,
        *,
        channel: Literal[
            "text_card", "bone_audio", "haptic_only", "silence"
        ] = "text_card",
        emergency: bool = False,
    ) -> GovernedReply:
        reply = self._guard.govern(draft, channel=channel, emergency=emergency)
        if reply.violations:
            self.style_violations.append(reply)  # 违例记录 → 沟通经验回路
        return reply

    # -- 观测 -----------------------------------------------------------

    @property
    def archived_observations(self) -> tuple[Observation, ...]:
        return tuple(self._archived)

    @property
    def window(self) -> tuple[ConversationTurn, ...]:
        return self._window.snapshot()

    # -- 内部 -----------------------------------------------------------

    def _archive_turn(self, turn: ConversationTurn) -> Observation:
        observation = Observation(
            object_id=f"obs_conv_{self.session_id}_{turn.turn_index:05d}",
            subject_id=self.subject_id,
            occurred=TemporalExtent.point(turn.at),
            learned_at=turn.at,
            recorded_at=turn.at,
            created_by="cockpit_pipeline:m2-009r",
            source_kind="conversation_turn",
            modality="text",
            value={
                "turn_index": turn.turn_index,
                "speaker": turn.speaker,
                "text": turn.text,  # 原话逐字节无损保留
            },
        )
        self._archive_sink(observation)
        return observation

    @staticmethod
    def _pack_text(content: str, cap: int) -> tuple[str, int, int]:
        total = estimate_tokens(content)
        if total <= cap:
            return content, 0, 0
        # 预留截断标记自身的 token，保证渲染后总量 <= 层预算
        marker = "…〔截断〕"
        cut_cap = cap - estimate_tokens(marker)
        # 收敛式截断：初始按比例切，随后按 90% 逐次收缩。
        # 保证硬封顶（混排 CJK/ASCII 密度变化不会造成预算穿透）。
        if cut_cap <= 0:
            cut = ""
        else:
            cut = content[: max(0, int(cut_cap * len(content) / max(total, 1)))]
            iterations = 0
            while estimate_tokens(cut) > cut_cap and iterations < 64:
                cut = cut[: max(1, int(len(cut) * 0.9))]
                iterations += 1
            if estimate_tokens(cut) > cut_cap:  # 极端兜底：逐字符收缩
                while cut and estimate_tokens(cut) > cut_cap:
                    cut = cut[:-1]
        return f"{cut}{marker}", 1, total - estimate_tokens(cut)

    @staticmethod
    def _pack_items(
        items: Sequence[str], cap: int
    ) -> tuple[str, int, int]:
        kept: list[str] = []
        spent = 0
        omitted_items = 0
        omitted_tokens = 0
        for item in items:
            t = estimate_tokens(item)
            if spent + t > cap and kept:
                omitted_items += 1
                omitted_tokens += t
                continue
            if spent + t > cap:
                # 单条即超预算：硬切单条
                rendered, _, _ = CrisisDialoguePipeline._pack_text(item, cap - spent)
                kept.append(rendered)
                omitted_items += 1
                omitted_tokens += t - estimate_tokens(rendered)
                spent = cap
                continue
            kept.append(item)
            spent += t
        rendered = "\n".join(kept) if kept else ""
        if omitted_items:
            rendered = (
                (rendered + "\n") if rendered else ""
            ) + f"…另有 {omitted_items} 项见省略索引"
        return rendered, omitted_items, omitted_tokens


def measure_assembly_p95(
    pipeline: CrisisDialoguePipeline,
    rounds: int = 50,
    **assembly_kwargs: Any,
) -> tuple[float, list[float]]:
    """看板装配延迟压测：返回 (p95_ms, 全样本)。装配只触碰窗口与定长层。"""
    durations: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        pipeline.assemble_manifest(**assembly_kwargs)
        durations.append((time.perf_counter() - started) * 1000.0)
    durations.sort()
    index = min(len(durations) - 1, int(round(0.95 * len(durations))) - 1)
    return durations[max(index, 0)], durations
