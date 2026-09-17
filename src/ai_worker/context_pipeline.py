"""Context Assembly Pipeline (C15 / M2-009R / ADJ-001 / R6).

Single-shot context assembly keeps the v3.0.1 cockpit layout stable while
preserving AI cognitive sovereignty:
1. L0: four compatible cockpit layout panels (not a mandatory thought order);
2. L1: associative recall slices and evidence pointers;
3. L2: active rolling dialogue window;
4. engineering token budgets are measured and reported, not used to rewrite AI semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from aios_core.operations.world_operator import estimate_token_count
from .manifest_optimizer import CockpitManifest, CockpitManifestOptimizer
from .stream_pipeline import ActiveRollingWindow, ThreeStageStreamPipeline


class AssembledContext(BaseModel):
    """装配完成的多层全息上下文。"""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(min_length=1)
    prompt_messages: List[Dict[str, str]] = Field(default_factory=list)
    total_tokens: int = Field(ge=0)
    manifest_tokens: int = Field(ge=0)
    recalled_tokens: int = Field(ge=0)
    dialogue_tokens: int = Field(ge=0)
    budget_tier: str = Field(default="ROUTINE")
    is_within_budget: bool = Field(default=True)


class ContextAssemblyPipeline:
    """上下文分层装配流水线。"""

    BUDGET_CAPS: Dict[str, int] = {
        "SAFETY": 512,
        "ROUTINE": 3400,
        "REVIEW": 8000,
    }

    @classmethod
    def assemble(
        cls,
        manifest: CockpitManifest,
        recalled_cues: Optional[List[Dict[str, Any]]] = None,
        rolling_messages: Optional[List[Dict[str, str]]] = None,
        budget_tier: str = "ROUTINE",
    ) -> AssembledContext:
        """装配多层上下文并报告工程预算状态。"""
        tier_cap = cls.BUDGET_CAPS.get(budget_tier, 3400)
        recalled_cues = recalled_cues or []
        rolling_messages = rolling_messages or []

        # L0 keeps ADJ-001-compatible physical layout order only. The labels
        # deliberately say "layout panel" so the prompt does not instruct the
        # model to execute a fixed cognitive sequence.
        system_sections = [
            "=== 【AIOS 3.0 驾驶舱看板 (Cockpit Manifest)】===",
            "以下四段仅为稳定排版/缓存布局，不规定 AI 的思考顺序；AI 可从任意信息开始判断并按需继续查询。",
            f"[布局段1·AI自身世界]:\n{manifest.step1_self_mirror}",
            f"[布局段2·关系模型]:\n{manifest.step2_rapport_model}",
            f"[布局段3·沟通策略提示]:\n{manifest.step3_posture_and_tone}",
            f"[布局段4·当前世界与就绪任务]:\n{manifest.step4_world_inspection}",
        ]

        recalled_text_block = ""
        if recalled_cues:
            cue_lines = []
            for c in recalled_cues:
                cue_lines.append(
                    f"• 历史关联事实 [轮次 {c.get('turn_index')}]: 主体={c.get('subject')}, "
                    f"事项={c.get('predicate')}:{c.get('object_val')}, 原话引用=\"{c.get('raw_quote')}\""
                )
            recalled_text_block = "\n[L1 联想回捞历史证据]:\n" + "\n".join(cue_lines)
            system_sections.append(recalled_text_block)

        full_system_prompt = "\n\n".join(system_sections)

        manifest_tokens = manifest.manifest_token_count
        recalled_tokens = estimate_token_count(recalled_text_block) if recalled_text_block else 0
        dialogue_text = "".join(m.get("content", "") for m in rolling_messages)
        dialogue_tokens = estimate_token_count(dialogue_text) if dialogue_text else 0

        total_tokens = manifest_tokens + recalled_tokens + dialogue_tokens
        is_within_budget = total_tokens <= tier_cap

        final_messages: List[Dict[str, str]] = [
            {"role": "system", "content": full_system_prompt}
        ]
        final_messages.extend(rolling_messages)

        return AssembledContext(
            system_prompt=full_system_prompt,
            prompt_messages=final_messages,
            total_tokens=total_tokens,
            manifest_tokens=manifest_tokens,
            recalled_tokens=recalled_tokens,
            dialogue_tokens=dialogue_tokens,
            budget_tier=budget_tier,
            is_within_budget=is_within_budget,
        )


__all__ = [
    "ActiveRollingWindow",
    "AssembledContext",
    "ContextAssemblyPipeline",
    "ThreeStageStreamPipeline",
]
