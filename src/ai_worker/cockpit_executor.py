"""Cockpit Executor (C10 / M2-012R / ADJ-001 / ADJ-007).

负责前台交互会话的完整端到端执行流：
1. 组装 Cockpit Manifest 四步序看板；
2. 执行跨周期超链接联想回捞；
3. 装配多层上下文；
4. 调度大模型或确定性测试推理后端；
5. 执行 1~3 句反说教老友语调护栏（含 ADJ-007 四大立宪豁免判定）；
6. 压入前台滑动窗口并将迁出轮次送入后台萃取流水线。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .brevity_guard import enforce_dialogue_brevity_guard
from .context_pipeline import AssembledContext, ContextAssemblyPipeline
from .manifest_optimizer import CockpitManifest, CockpitManifestOptimizer
from .stream_pipeline import ThreeStageStreamPipeline

UTC = timezone.utc


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
        user_name: str = "老大",
        rapport_tier: str = "生死死党/损友僚机",
        posture_tone: str = "自然真诚、敏锐关切、关键节点直言不讳",
        ready_tasks: Optional[List[Dict[str, Any]]] = None,
        budget_tier: str = "ROUTINE",
        allow_expansion: bool = False,
    ) -> TurnExecutionResult:
        """执行单轮端到端会话。"""
        t0 = time.perf_counter()

        # 1. 联想回捞 (Stage 3)
        recalled_cues = self.pipeline.recall.recall_for_turn(user_msg)

        # 2. 组装 Cockpit Manifest
        manifest = CockpitManifestOptimizer.assemble_cockpit(
            wake_reason=wake_reason,
            user_name=user_name,
            rapport_tier=rapport_tier,
            posture_tone=posture_tone,
            ready_tasks=ready_tasks,
        )

        # 3. 组装上下文
        rolling_msgs = self.pipeline.window.get_prompt_messages()
        assembled_ctx = ContextAssemblyPipeline.assemble(
            manifest=manifest,
            recalled_cues=recalled_cues,
            rolling_messages=rolling_msgs,
            budget_tier=budget_tier,
        )

        # 4. 执行模型推理
        raw_reply = self.model_handler(assembled_ctx)

        # 5. 校验 ADJ-007 豁免条件：用户明确要求展开或生命安全等
        is_expansion_requested = allow_expansion or any(
            kw in user_msg for kw in ("展开", "详细说说", "为什么", "具体讲讲", "到底怎么想的")
        )

        # 6. 执行 1~3 句反说教护栏
        if is_expansion_requested:
            final_reply = raw_reply
            was_truncated = False
        else:
            final_reply, was_truncated = enforce_dialogue_brevity_guard(raw_reply)

        # 7. 压入前台滑窗与后台萃取 (Stage 1 & 2)
        turn_no = self.pipeline._turn_counter + 1
        self.pipeline._turn_counter = turn_no
        evicted = self.pipeline.window.push_turn(user_msg, final_reply)
        if evicted:
            offset = max(0, turn_no - len(self.pipeline.window.get_prompt_messages()) // 2 - len(evicted))
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
        # 从最后一条 user 消息返回老友风格简答
        last_user = ""
        for m in reversed(ctx.prompt_messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        return f"听到了。关于'{last_user[:10]}'，咱们按原计划办就行。"


__all__ = [
    "CockpitExecutor",
    "TurnExecutionResult",
    "enforce_dialogue_brevity_guard",
]
