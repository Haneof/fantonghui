"""Context Assembly Pipeline (C15 / M2-009R / ADJ-001).

单次看盘上下文分层装配流水线：
严格遵循 v3.0.1 裁决集 ADJ-001 与 runtime_policy.json 规定：
1. L0 层（底座心智）：Cockpit Manifest 四步序（照镜子、校准羁绊、确立姿态、审视世界）；
2. L1 层（动态记忆）：超链接主动联想回捞切片与关键事实指针；
3. L2 层（即时会话）：前台活跃滑动窗口（5~8 轮）；
4. 预算封套控制：依据场景自动适配 SAFETY (<=512), ROUTINE (<=3400), REVIEW (<=8000)。
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
        """装配多层上下文并校验预算封套。"""
        tier_cap = cls.BUDGET_CAPS.get(budget_tier, 3400)
        recalled_cues = recalled_cues or []
        rolling_messages = rolling_messages or []

        # 1. 构建 System Prompt (L0 四步序装配)
        system_sections = [
            f"=== 【AIOS 3.0 心智启动看板 (Cockpit Manifest)】===",
            f"[第一步·照镜子 (原则底线)]:\n{manifest.step1_self_mirror}",
            f"[第二步·校准羁绊 (动态关系)]:\n{manifest.step2_rapport_model}",
            f"[第三步·确立姿态 (态度与语调)]:\n{manifest.step3_posture_and_tone}",
            f"[第四步·审视世界与就绪任务]:\n{manifest.step4_world_inspection}",
        ]

        # 2. 注入 L1 联想回捞切片
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

        # 3. 统计各层 Token 消耗
        manifest_tokens = manifest.manifest_token_count
        recalled_tokens = estimate_token_count(recalled_text_block) if recalled_text_block else 0
        dialogue_text = "".join(m.get("content", "") for m in rolling_messages)
        dialogue_tokens = estimate_token_count(dialogue_text) if dialogue_text else 0

        total_tokens = manifest_tokens + recalled_tokens + dialogue_tokens
        is_within_budget = total_tokens <= tier_cap

        # 4. 装配最终 Prompt Messages 序列
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
