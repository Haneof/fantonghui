"""Cockpit Executor (C10 / M2-012R / ADJ-001 / R6).

Foreground conversation execution flow:
1. retrieve candidate historical context;
2. assemble the Cockpit Manifest as an information dashboard;
3. assemble layered context;
4. invoke the model or deterministic test backend;
5. preserve the model's semantic reply exactly (brevity is a soft style policy);
6. advance the rolling window and background extraction pipeline.
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
    """单轮会话执行结果。"""

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


class CockpitExecutor:
    """驾驶舱会话总执行器。"""

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
        """执行单轮端到端会话。

        ``allow_expansion`` is retained for API compatibility. Expansion no
        longer needs an exception flag because there is no destructive length
        cap: the AI itself decides how much explanation the situation needs.
        """
        t0 = time.perf_counter()
        _ = allow_expansion

        # 1. 联想回捞：结果是候选记忆，不是最终认知结论。
        recalled_cues = self.pipeline.recall.recall_for_turn(user_msg)

        # 2. 组装驾驶舱信息面板。布局顺序不等于思维顺序。
        manifest = CockpitManifestOptimizer.assemble_cockpit(
            wake_reason=wake_reason,
            user_name=user_name,
            rapport_tier=rapport_tier,
            posture_tone=posture_tone,
            ready_tasks=ready_tasks,
        )

        # 3. 组装上下文。
        rolling_msgs = self.pipeline.window.get_prompt_messages()
        assembled_ctx = ContextAssemblyPipeline.assemble(
            manifest=manifest,
            recalled_cues=recalled_cues,
            rolling_messages=rolling_msgs,
            budget_tier=budget_tier,
        )

        # 4. 由 AI 进行实际认知与表达。
        raw_reply = self.model_handler(assembled_ctx)

        # 5. 兼容旧调用契约，但不得再按句数/字数/正则改写 AI 语义。
        final_reply, was_truncated = enforce_dialogue_brevity_guard(raw_reply)

        # 6. 压入前台滑窗与后台萃取。
        turn_no = self.pipeline._turn_counter + 1
        self.pipeline._turn_counter = turn_no
        evicted = self.pipeline.window.push_turn(user_msg, final_reply)
        if evicted:
            offset = max(
                0,
                turn_no
                - len(self.pipeline.window.get_prompt_messages()) // 2
                - len(evicted),
            )
            self.pipeline.extractor.enqueue_evicted_turns(evicted, offset)
            self.pipeline.extractor.extract_sync(evicted, offset)

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
        )
        self._turn_history_results.append(res)
        return res

    def _default_mock_model_handler(self, ctx: AssembledContext) -> str:
        """默认测试模型回显器。"""
        last_user = ""
        for m in reversed(ctx.prompt_messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        return f"听到了。关于'{last_user[:10]}'，咱们按当前情况看就行。"


__all__ = [
    "CockpitExecutor",
    "TurnExecutionResult",
    "enforce_dialogue_brevity_guard",
]
