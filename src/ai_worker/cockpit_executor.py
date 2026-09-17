"""Legacy one-shot Cockpit Executor (C10 / M2-012R / ADJ-001 / R6).

This remains a compatibility executor, not the full R5 CognitiveRuntime. It preserves
model semantics, records raw turns when a durable timeline is configured, and hands
evicted turns to exactly one extraction path (background *or* synchronous).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .brevity_guard import enforce_dialogue_brevity_guard
from .context_pipeline import AssembledContext, ContextAssemblyPipeline
from .manifest_optimizer import CockpitManifestOptimizer
from .stream_pipeline import ThreeStageStreamPipeline


@dataclass
class TurnExecutionResult:
    reply: str
    raw_reply: str
    turn_index: int
    was_brevity_truncated: bool
    recalled_cues: List[Dict[str, Any]]
    total_tokens: int
    manifest_tokens: int
    execution_time_ms: float
    budget_tier: str
    is_within_budget: bool
    raw_turn_ref: str | None = None


class CockpitExecutor:
    """Compatibility foreground executor; new autonomous tool loops live in R5 runtime."""

    def __init__(
        self,
        pipeline: Optional[ThreeStageStreamPipeline] = None,
        model_handler: Optional[Callable[[AssembledContext], str]] = None,
    ) -> None:
        self.pipeline = pipeline or ThreeStageStreamPipeline()
        self.model_handler = model_handler or self._default_mock_model_handler
        self._turn_history_results: List[TurnExecutionResult] = []

    def execute_turn(
        self,
        user_msg: str,
        *,
        wake_reason: str = "用户主动发起日常交互",
        user_name: str = "用户",
        rapport_tier: str = "待当前证据校准",
        posture_tone: str = "自然、口语化；简单事项简短回答，需要解释时充分展开；根据当前语境自主决定语气与详略",
        ready_tasks: Optional[List[Dict[str, Any]]] = None,
        budget_tier: str = "ROUTINE",
        allow_expansion: bool = False,
    ) -> TurnExecutionResult:
        """Execute one compatibility conversation turn.

        ``allow_expansion`` remains only for caller compatibility. R6 removed the
        destructive length cap, so the flag no longer grants a semantic exception.
        """

        t0 = time.perf_counter()
        _ = allow_expansion

        recalled_cues = self.pipeline.recall.recall_for_turn(user_msg)
        manifest = CockpitManifestOptimizer.assemble_cockpit(
            wake_reason=wake_reason,
            user_name=user_name,
            rapport_tier=rapport_tier,
            posture_tone=posture_tone,
            ready_tasks=ready_tasks,
        )
        rolling_msgs = self.pipeline.window.get_prompt_messages()
        assembled_ctx = ContextAssemblyPipeline.assemble(
            manifest=manifest,
            recalled_cues=recalled_cues,
            rolling_messages=rolling_msgs,
            budget_tier=budget_tier,
        )

        raw_reply = self.model_handler(assembled_ctx)
        final_reply, was_truncated = enforce_dialogue_brevity_guard(raw_reply)

        turn_no = self.pipeline._turn_counter + 1
        self.pipeline._turn_counter = turn_no
        raw_turn_ref = self.pipeline.record_raw_turn(turn_no, user_msg, final_reply)
        evicted = self.pipeline.window.push_turn(user_msg, final_reply)
        if evicted:
            offset = max(
                0,
                turn_no
                - len(self.pipeline.window.get_prompt_messages()) // 2
                - len(evicted),
            )
            self.pipeline.process_evicted(evicted, offset)

        execution_time_ms = (time.perf_counter() - t0) * 1000.0
        res = TurnExecutionResult(
            reply=final_reply,
            raw_reply=raw_reply,
            turn_index=turn_no,
            was_brevity_truncated=was_truncated,
            recalled_cues=recalled_cues,
            total_tokens=assembled_ctx.total_tokens,
            manifest_tokens=assembled_ctx.manifest_tokens,
            execution_time_ms=execution_time_ms,
            budget_tier=budget_tier,
            is_within_budget=assembled_ctx.is_within_budget,
            raw_turn_ref=raw_turn_ref,
        )
        self._turn_history_results.append(res)
        return res

    def _default_mock_model_handler(self, ctx: AssembledContext) -> str:
        last_user = ""
        for message in reversed(ctx.prompt_messages):
            if message.get("role") == "user":
                last_user = message.get("content", "")
                break
        return f"听到了。关于'{last_user[:10]}'，咱们按当前情况看就行。"


__all__ = [
    "CockpitExecutor",
    "TurnExecutionResult",
    "enforce_dialogue_brevity_guard",
]
