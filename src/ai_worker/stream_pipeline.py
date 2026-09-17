"""Long-conversation streaming support for AIOS R5/R6.

This module now has three strictly separated jobs:
1. keep a bounded active window for prompt assembly;
2. move evicted turns to an optional *model-backed* extraction worker;
3. provide cheap lexical prefetch hints from already-derived candidates.

It deliberately does **not** contain a default regex/keyword cognitive extractor. When
no cognitive extractor is configured, raw turns remain the source of truth and the
worker advances its watermark without inventing Claims, sentiment, relationship
meaning or importance. AI Cognitive Runtime owns deeper recall and interpretation.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from aios_core.runtime.conversation_timeline import (
    ConversationTimelineStore,
    ConversationTurn,
)

UTC = timezone.utc


class ActiveRollingWindow:
    """Bounded foreground dialogue window; this is a cache, not durable memory."""

    def __init__(self, max_turns: int = 6, max_tokens: int = 1500) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._turns: deque[Tuple[str, str]] = deque()

    def push_turn(self, user_msg: str, ai_msg: str) -> List[Tuple[str, str]]:
        self._turns.append((user_msg, ai_msg))
        evicted: List[Tuple[str, str]] = []
        while len(self._turns) > self.max_turns:
            evicted.append(self._turns.popleft())
        return evicted

    def get_prompt_messages(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for user_msg, ai_msg in self._turns:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": ai_msg})
        return messages

    @property
    def total_turns(self) -> int:
        return len(self._turns)

    def estimate_tokens(self) -> int:
        # Engineering estimate only; it is not a semantic truncation rule.
        total_chars = sum(len(u) + len(a) for u, a in self._turns)
        return int(total_chars * 0.7) + 1

    def clear(self) -> None:
        self._turns.clear()


class ExtractedClaimCandidate(BaseModel):
    """Candidate emitted by an explicitly configured cognitive extractor."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_val: str = Field(min_length=1)
    context_topic: str = Field(default="日常对话")
    sentiment: str = Field(default="未知")
    raw_quote: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    idempotency_key: str = Field(min_length=1)


Extractor = Callable[[List[Tuple[str, str]], int], List[ExtractedClaimCandidate]]


class StreamingExtractWorker:
    """Async/sync transport for a configured cognitive extractor.

    No extractor -> no synthetic cognition. The worker still advances its processing
    watermark so orchestration can know that the raw batch was seen.
    """

    def __init__(self, custom_extractor: Optional[Extractor] = None) -> None:
        self._queue: queue.Queue[Optional[Tuple[List[Tuple[str, str]], int]]] = queue.Queue()
        self._extracted_claims: List[ExtractedClaimCandidate] = []
        self._seen_idempotency_keys: set[str] = set()
        self._custom_extractor = custom_extractor
        self._watermark: int = 0
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None

    @property
    def extraction_configured(self) -> bool:
        return self._custom_extractor is not None

    @property
    def background_running(self) -> bool:
        return self._worker_thread is not None and self._worker_thread.is_alive()

    def start_background_thread(self) -> None:
        if not self.background_running:
            self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._worker_thread.start()

    def stop_background_thread(self) -> None:
        if not self.background_running:
            self._worker_thread = None
            return
        self._queue.put(None)
        assert self._worker_thread is not None
        self._worker_thread.join(timeout=2.0)
        self._worker_thread = None

    def _run_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                batch, turn_offset = item
                self.extract_sync(batch, turn_offset)
            finally:
                self._queue.task_done()

    def enqueue_evicted_turns(self, batch: List[Tuple[str, str]], turn_offset: int) -> None:
        if batch:
            self._queue.put((list(batch), int(turn_offset)))

    def extract_sync(
        self,
        batch: List[Tuple[str, str]],
        turn_offset: int,
    ) -> List[ExtractedClaimCandidate]:
        results = (
            self._custom_extractor(batch, turn_offset)
            if self._custom_extractor is not None
            else []
        )
        validated = [ExtractedClaimCandidate.model_validate(item) for item in results]
        accepted: list[ExtractedClaimCandidate] = []
        with self._lock:
            for candidate in validated:
                if candidate.idempotency_key in self._seen_idempotency_keys:
                    continue
                self._seen_idempotency_keys.add(candidate.idempotency_key)
                self._extracted_claims.append(candidate)
                accepted.append(candidate)
            self._watermark = max(self._watermark, turn_offset + len(batch))
        return accepted

    def drain(self, timeout: float = 2.0) -> List[ExtractedClaimCandidate]:
        del timeout  # kept for API compatibility
        if self.background_running:
            self._queue.join()
        else:
            # Public callers may enqueue without starting the worker. Process such
            # items synchronously instead of blocking forever on queue.join().
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    if item is not None:
                        batch, turn_offset = item
                        self.extract_sync(batch, turn_offset)
                finally:
                    self._queue.task_done()
        with self._lock:
            return list(self._extracted_claims)

    def get_all_extracted(self) -> List[ExtractedClaimCandidate]:
        with self._lock:
            return list(self._extracted_claims)

    @property
    def watermark(self) -> int:
        with self._lock:
            return self._watermark


class ProactiveAssociativeRecall:
    """Cheap prefetch hints from already-derived candidates.

    Exact lexical overlap is only a retrieval signal. This class no longer fabricates
    an authoritative `relevance_score=0.95`; final relevance belongs to the model.
    """

    def __init__(self, extract_worker: StreamingExtractWorker, world_store: Any = None) -> None:
        self.extract_worker = extract_worker
        self.world_store = world_store

    def recall_for_turn(self, user_msg: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not user_msg or top_k <= 0:
            return []

        recalled: List[Dict[str, Any]] = []
        for candidate in reversed(self.extract_worker.get_all_extracted()):
            subject_hit = candidate.subject != "用户" and candidate.subject in user_msg
            object_hit = len(candidate.object_val) >= 2 and candidate.object_val in user_msg
            if not (subject_hit or object_hit):
                continue
            signal = (
                "exact_subject_and_object"
                if subject_hit and object_hit
                else "exact_subject"
                if subject_hit
                else "exact_object"
            )
            recalled.append(
                {
                    "anchor_id": candidate.claim_id,
                    "subject": candidate.subject,
                    "predicate": candidate.predicate,
                    "object_val": candidate.object_val,
                    "raw_quote": candidate.raw_quote,
                    "turn_index": candidate.turn_index,
                    "retrieval_signal": signal,
                    "why_recalled": (
                        f"prefetch lexical signal matched candidate from turn {candidate.turn_index}; "
                        "AI must decide actual relevance"
                    ),
                }
            )
            if len(recalled) >= top_k:
                break
        return recalled


class ThreeStageStreamPipeline:
    """Foreground cache + optional cognitive extraction + prefetch accelerator."""

    def __init__(
        self,
        max_active_turns: int = 6,
        max_active_tokens: int = 1500,
        custom_extractor: Optional[Extractor] = None,
        world_store: Any = None,
        *,
        session_id: str = "default",
        timeline_store: ConversationTimelineStore | None = None,
    ) -> None:
        self.window = ActiveRollingWindow(max_turns=max_active_turns, max_tokens=max_active_tokens)
        self.extractor = StreamingExtractWorker(custom_extractor=custom_extractor)
        self.recall = ProactiveAssociativeRecall(self.extractor, world_store=world_store)
        self.session_id = session_id
        if timeline_store is None and world_store is not None and hasattr(world_store, "db_path"):
            timeline_store = ConversationTimelineStore(world_store.db_path)
        self.timeline_store = timeline_store
        self._turn_counter: int = 0

    def record_raw_turn(self, turn_no: int, user_msg: str, ai_msg: str) -> str | None:
        if self.timeline_store is None:
            return None
        turn = ConversationTurn.create(
            session_id=self.session_id,
            turn_index=turn_no,
            user_text=user_msg,
            assistant_text=ai_msg,
        )
        return self.timeline_store.append(turn).turn_id

    def process_evicted(self, evicted: List[Tuple[str, str]], turn_offset: int) -> None:
        if not evicted:
            return
        if self.extractor.background_running:
            self.extractor.enqueue_evicted_turns(evicted, turn_offset)
        else:
            self.extractor.extract_sync(evicted, turn_offset)

    def process_turn(
        self,
        user_msg: str,
        reply_generator: Callable[[List[Dict[str, str]], List[Dict[str, Any]]], str],
    ) -> Dict[str, Any]:
        self._turn_counter += 1
        turn_no = self._turn_counter

        recalled_cues = self.recall.recall_for_turn(user_msg)
        prompt_messages = self.window.get_prompt_messages()
        raw_reply = reply_generator(prompt_messages, recalled_cues)

        raw_turn_ref = self.record_raw_turn(turn_no, user_msg, raw_reply)
        evicted = self.window.push_turn(user_msg, raw_reply)
        if evicted:
            evicted_offset = max(
                0,
                turn_no - len(self.window.get_prompt_messages()) // 2 - len(evicted),
            )
            self.process_evicted(evicted, evicted_offset)

        return {
            "reply": raw_reply,
            "turn_index": turn_no,
            "raw_turn_ref": raw_turn_ref,
            "recalled_cues": recalled_cues,
            "active_turns": self.window.total_turns,
            "estimated_tokens": self.window.estimate_tokens(),
            "evicted_count": len(evicted),
            "extraction_mode": (
                "cognitive_extractor" if self.extractor.extraction_configured else "raw_only"
            ),
            "total_extracted_claims": len(self.extractor.get_all_extracted()),
        }

    def flush_and_extract_all(self) -> List[ExtractedClaimCandidate]:
        remaining = list(self.window._turns)
        if remaining:
            self.extractor.extract_sync(
                remaining,
                max(0, self._turn_counter - len(remaining)),
            )
        return self.extractor.drain()
