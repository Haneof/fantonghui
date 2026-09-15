"""M2-009R bounded Single-Shot cockpit and long-conversation pipeline.

The model adapter must send ``SingleShotCockpitManifest.prompt`` verbatim and
must not append hidden conversation history.  The physical envelope budgets
one UTF-8 byte as one conservative token unit.  A model adapter may additionally
audit its exact tokenizer, but it may never replace or relax this 1,500-unit
upper bound.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from math import ceil
from threading import RLock
from typing import Any, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from aios_core.contracts.time import require_aware, utc_now


class Utf8ByteTokenCounter:
    """Conservative dependency-free token envelope.

    Counting UTF-8 bytes is intentionally stricter than ordinary BPE token
    counts for Chinese and Latin text.  Truncation never emits invalid UTF-8.
    """

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens < 0:
            raise ValueError("max_tokens must be >= 0")
        encoded = text.encode("utf-8")
        if len(encoded) <= max_tokens:
            return text
        return encoded[:max_tokens].decode("utf-8", errors="ignore")


class ConversationTurn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    turn_id: str = Field(min_length=1, max_length=160)
    sequence_no: int = Field(ge=1)
    occurred_at: datetime
    user_text: str = Field(min_length=1, max_length=200_000)
    assistant_text: str = Field(min_length=1, max_length=200_000)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "occurred_at")
        return value


class ArchivedTurnObservation(BaseModel):
    """Lossless historical Observation projection for an evicted turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = Field(min_length=1, max_length=200)
    source_turn_id: str = Field(min_length=1, max_length=160)
    sequence_no: int = Field(ge=1)
    occurred_at: datetime
    learned_at: datetime
    user_text: str
    assistant_text: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("occurred_at", "learned_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime, info: Any) -> datetime:
        require_aware(value, info.field_name)
        return value


class ConversationObservationArchive:
    """Thread-safe, append-only archive with exact-content idempotency."""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self._by_turn_id: dict[str, ArchivedTurnObservation] = {}
        self._ordered: list[ArchivedTurnObservation] = []
        self._lock = RLock()

    def append_turn(self, turn: ConversationTurn) -> ArchivedTurnObservation:
        canonical = json.dumps(
            {
                "assistant_text": turn.assistant_text,
                "occurred_at": turn.occurred_at.isoformat(),
                "sequence_no": turn.sequence_no,
                "turn_id": turn.turn_id,
                "user_text": turn.user_text,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        archived = ArchivedTurnObservation(
            observation_id=f"obs_conversation_{turn.turn_id}",
            source_turn_id=turn.turn_id,
            sequence_no=turn.sequence_no,
            occurred_at=turn.occurred_at,
            learned_at=self._clock(),
            user_text=turn.user_text,
            assistant_text=turn.assistant_text,
            content_sha256=hashlib.sha256(canonical).hexdigest(),
        )
        with self._lock:
            previous = self._by_turn_id.get(turn.turn_id)
            if previous is not None:
                if (
                    previous.sequence_no != archived.sequence_no
                    or previous.occurred_at != archived.occurred_at
                    or previous.user_text != archived.user_text
                    or previous.assistant_text != archived.assistant_text
                    or previous.content_sha256 != archived.content_sha256
                ):
                    raise ValueError(
                        f"turn_id already archived with different content: {turn.turn_id}"
                    )
                return previous
            self._by_turn_id[turn.turn_id] = archived
            self._ordered.append(archived)
        return archived

    def snapshot(self) -> tuple[ArchivedTurnObservation, ...]:
        with self._lock:
            return tuple(self._ordered)

    def __len__(self) -> int:
        with self._lock:
            return len(self._ordered)


class ActiveRollingWindow:
    """Tier-1 volatile window: exactly the newest six complete turns."""

    HARD_MAX_TURNS: ClassVar[int] = 6

    def __init__(self, max_turns: int = HARD_MAX_TURNS) -> None:
        if not 1 <= max_turns <= self.HARD_MAX_TURNS:
            raise ValueError("max_turns must be between 1 and 6")
        self.max_turns = max_turns
        self._turns: deque[ConversationTurn] = deque()
        self._lock = RLock()

    def push(self, turn: ConversationTurn) -> tuple[ConversationTurn, ...]:
        normalized = ConversationTurn.model_validate(turn)
        with self._lock:
            if self._turns and normalized.sequence_no <= self._turns[-1].sequence_no:
                raise ValueError("conversation sequence_no must increase monotonically")
            self._turns.append(normalized)
            evicted: list[ConversationTurn] = []
            while len(self._turns) > self.max_turns:
                evicted.append(self._turns.popleft())
            return tuple(evicted)

    def snapshot(self) -> tuple[ConversationTurn, ...]:
        with self._lock:
            return tuple(self._turns)

    def __len__(self) -> int:
        with self._lock:
            return len(self._turns)


class CrisisCockpitContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    session_id: str = Field(min_length=1, max_length=160)
    ai_self_summary: str = Field(min_length=1, max_length=500_000)
    rapport_state: str = Field(min_length=1, max_length=500_000)
    wake_reason_anchor: str = Field(min_length=1, max_length=500_000)
    local_world_facts: str = Field(min_length=1, max_length=2_000_000)
    ready_tasks: list[dict[str, Any]] = Field(default_factory=list, max_length=3)


class SingleShotCockpitManifest(BaseModel):
    """The only prompt envelope allowed to cross the model boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    generated_at: datetime
    prompt: str = Field(min_length=1)
    prompt_token_count: int = Field(ge=1, le=1_500)
    active_turn_ids: list[str] = Field(max_length=6)
    archived_observation_count: int = Field(ge=0)
    omitted_utf8_bytes: int = Field(ge=0)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "generated_at")
        return value

    @model_validator(mode="after")
    def token_receipt_must_match_physical_prompt(self) -> SingleShotCockpitManifest:
        physical_count = len(self.prompt.encode("utf-8"))
        if self.prompt_token_count != physical_count:
            raise ValueError(
                "prompt_token_count does not match physical prompt envelope"
            )
        if physical_count > 1_500:
            raise ValueError("Single-Shot prompt exceeds the 1500-token hard ceiling")
        return self


class CockpitPipeline:
    """Archive evicted turns and assemble one bounded prompt per new turn."""

    HARD_PROMPT_TOKEN_LIMIT: ClassVar[int] = 1_500

    def __init__(
        self,
        *,
        window: ActiveRollingWindow | None = None,
        archive: ConversationObservationArchive | None = None,
        prompt_token_limit: int = HARD_PROMPT_TOKEN_LIMIT,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not 1 <= prompt_token_limit <= self.HARD_PROMPT_TOKEN_LIMIT:
            raise ValueError("prompt_token_limit must be between 1 and 1500")
        self.window = window if window is not None else ActiveRollingWindow()
        self.archive = (
            archive
            if archive is not None
            else ConversationObservationArchive(clock=clock)
        )
        self.token_counter = Utf8ByteTokenCounter()
        self.prompt_token_limit = prompt_token_limit
        self._clock = clock

    def process_turn(
        self,
        turn: ConversationTurn,
        context: CrisisCockpitContext,
    ) -> SingleShotCockpitManifest:
        evicted = self.window.push(turn)
        for old_turn in evicted:
            self.archive.append_turn(old_turn)
        return self.assemble_manifest(context)

    def assemble_manifest(
        self,
        context: CrisisCockpitContext,
    ) -> SingleShotCockpitManifest:
        active_turns = self.window.snapshot()
        contract = (
            "Single-Shot only; evidence first; no paternalistic lecture; "
            "reply in 1-3 sentences."
        )
        ready_json = json.dumps(
            context.ready_tasks,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        sections = [
            self._bounded_section("CONTRACT", contract, 120),
            self._bounded_section("WAKE", context.wake_reason_anchor, 120),
            self._bounded_section("SELF", context.ai_self_summary, 80),
            self._bounded_section("RAPPORT", context.rapport_state, 80),
            self._bounded_section("CRISIS_FACTS", context.local_world_facts, 220),
            self._bounded_section("READY", ready_json, 80),
        ]
        for turn in active_turns:
            sections.append(
                self._bounded_section(
                    f"TURN_{turn.sequence_no}_{turn.turn_id}",
                    f"U:{turn.user_text}\nA:{turn.assistant_text}",
                    100,
                )
            )

        unbounded_prompt = "\n".join(sections)
        prompt = self.token_counter.truncate(
            unbounded_prompt,
            self.prompt_token_limit,
        )
        count = self.token_counter.count(prompt)
        if count > self.prompt_token_limit:
            raise RuntimeError("token counter failed to enforce prompt ceiling")
        source_bytes = sum(
            self.token_counter.count(value)
            for value in (
                contract,
                context.wake_reason_anchor,
                context.ai_self_summary,
                context.rapport_state,
                context.local_world_facts,
                ready_json,
            )
        ) + sum(
            self.token_counter.count(turn.user_text)
            + self.token_counter.count(turn.assistant_text)
            for turn in active_turns
        )
        omitted = max(0, source_bytes - count)
        return SingleShotCockpitManifest(
            session_id=context.session_id,
            generated_at=self._clock(),
            prompt=prompt,
            prompt_token_count=count,
            active_turn_ids=[turn.turn_id for turn in active_turns],
            archived_observation_count=len(self.archive),
            omitted_utf8_bytes=omitted,
        )

    def _bounded_section(self, label: str, content: str, budget: int) -> str:
        prefix = f"[{label}] "
        prefix_cost = self.token_counter.count(prefix)
        if prefix_cost >= budget:
            return self.token_counter.truncate(prefix, budget)
        return prefix + self.token_counter.truncate(content, budget - prefix_cost)

    @staticmethod
    def p95_ms(samples_ms: Sequence[float]) -> float:
        if not samples_ms:
            raise ValueError("samples_ms must not be empty")
        ordered = sorted(samples_ms)
        index = max(0, ceil(0.95 * len(ordered)) - 1)
        return ordered[index]


_SENTENCE_PATTERN = re.compile(r"[^。！？!?\n]+[。！？!?]?", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in _SENTENCE_PATTERN.finditer(text)
        if match.group(0).strip()
    ]


class BrevityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    sentences: list[str] = Field(min_length=1, max_length=3)
    blocked_patterns: list[str] = Field(default_factory=list)
    was_truncated: bool = False
    was_rewritten: bool = False


class BrevityGuard:
    """Fail-closed anti-lecture output gate for the wearable channel."""

    MAX_SENTENCES: ClassVar[int] = 3
    MAX_CHARACTERS_BEFORE_REWRITE: ClassVar[int] = 180
    SAFE_CRISIS_REPLY: ClassVar[str] = (
        "这不是你的错，先别在高压下签任何东西。"
        "把降薪、调岗和竞业索赔材料原样留住，我们一起把主动权拿回来。"
    )
    FORBIDDEN_PATTERNS: ClassVar[tuple[tuple[str, re.Pattern[str]], ...]] = (
        ("positive-mindset", re.compile(r"您?要保持积极心态")),
        ("five-point-counselling", re.compile(r"为您推荐以下[五5]点.*方案")),
        ("paternal-advice", re.compile(r"我建议您(?:采取|保持|首先|应该)?")),
        (
            "numbered-lecture",
            re.compile(r"第[一二三四五六七八九十]点|首先.*其次.*最后", re.DOTALL),
        ),
        (
            "customer-service",
            re.compile(r"很高兴为您服务|请问有什么(?:可以)?帮(?:助)?您"),
        ),
        ("formulaic-summary", re.compile(r"综上所述|综合以上分析")),
    )

    def enforce(self, raw_reply: str) -> BrevityResult:
        if not isinstance(raw_reply, str) or not raw_reply.strip():
            return self._safe_rewrite(["empty-output"])

        blocked = [
            name
            for name, pattern in self.FORBIDDEN_PATTERNS
            if pattern.search(raw_reply)
        ]
        if blocked or len(raw_reply.strip()) > self.MAX_CHARACTERS_BEFORE_REWRITE:
            return self._safe_rewrite(blocked or ["overlong-single-reply"])

        sentences = split_sentences(raw_reply)
        if not sentences:
            return self._safe_rewrite(["empty-after-segmentation"])
        truncated = len(sentences) > self.MAX_SENTENCES
        kept = sentences[: self.MAX_SENTENCES]
        text = "".join(kept).strip()
        if any(pattern.search(text) for _, pattern in self.FORBIDDEN_PATTERNS):
            return self._safe_rewrite(["forbidden-after-truncation"])
        return BrevityResult(
            text=text,
            sentences=kept,
            blocked_patterns=[],
            was_truncated=truncated,
            was_rewritten=False,
        )

    def _safe_rewrite(self, blocked: Iterable[str]) -> BrevityResult:
        sentences = split_sentences(self.SAFE_CRISIS_REPLY)
        return BrevityResult(
            text=self.SAFE_CRISIS_REPLY,
            sentences=sentences,
            blocked_patterns=list(blocked),
            was_truncated=True,
            was_rewritten=True,
        )


__all__ = [
    "ActiveRollingWindow",
    "ArchivedTurnObservation",
    "BrevityGuard",
    "BrevityResult",
    "CockpitPipeline",
    "ConversationObservationArchive",
    "ConversationTurn",
    "CrisisCockpitContext",
    "SingleShotCockpitManifest",
    "Utf8ByteTokenCounter",
    "split_sentences",
]
