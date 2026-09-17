"""AIOS 3.0 single-shot Cockpit Manifest assembler.

The cockpit is an information dashboard, not a scripted chain of thought.
ADJ-001 keeps the historical step1~step4 field order as a stable layout and
serialization contract; it does not require the AI to inspect or reason through
those panels in that order. The AI may start from any panel, skip a panel, or
request more world context whenever the task requires it.

Token targets are engineering latency budgets, not cognitive truth boundaries.
They may guide assembly and observability, but must not force semantic deletion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aios_core.operations.world_operator import estimate_token_count

UTC = timezone.utc


class CockpitManifest(BaseModel):
    """Single-shot cockpit dashboard.

    The ``step1`` ... ``step4`` names are retained for wire compatibility with
    the v3.0.1 manifest layout. They are layout positions only, not a mandatory
    cognitive execution order.
    """

    model_config = ConfigDict(extra="forbid")

    step1_self_mirror: str = Field(
        min_length=1,
        description="兼容布局段 1：AI 自身世界与原则；不规定必须首先思考",
    )
    step2_rapport_model: str = Field(
        min_length=1,
        description="兼容布局段 2：关系模型候选；不得预设关系亲密度",
    )
    step3_posture_and_tone: str = Field(
        min_length=1,
        description="兼容布局段 3：沟通策略提示；AI 可依当前语境自主修正",
    )
    step4_world_inspection: Dict[str, Any] = Field(
        description="兼容布局段 4：当前世界、触发源与就绪任务；可随时查看或下钻"
    )

    wake_reason: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    manifest_token_count: int = Field(ge=0)


class CockpitManifestOptimizer:
    """Assemble a compact cockpit without prescribing how the AI must think."""

    @classmethod
    def assemble_cockpit(
        cls,
        *,
        wake_reason: str,
        user_name: str = "用户",
        rapport_tier: str = "待当前证据校准",
        rapport_notes: str = "不预设关系亲密度；由历史交互、用户明确表达和当前证据动态判断",
        self_identity: str = "AIOS 3.0 的 AI 驾驶员；依据证据理解世界，自主使用系统能力并遵守安全与权限边界",
        posture_tone: str = "自然、口语化；简单事项简短回答，需要解释时充分展开；根据当前语境自主决定语气与详略",
        active_focus_facts: Optional[List[Dict[str, Any]]] = None,
        ready_tasks: Optional[List[Dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> CockpitManifest:
        """Assemble four compatible layout panels with no mandatory thought order."""
        t_now = now or datetime.now(UTC)

        # Compatibility layout panel: AI self-world.
        s1 = f"【AI自身世界与原则】: {self_identity}"

        # Compatibility layout panel: relationship model. No intimacy is assumed.
        s2 = (
            f"【关系模型候选】: 用户={user_name}; 当前状态={rapport_tier}; "
            f"证据/说明={rapport_notes}"
        )

        # Compatibility layout panel: a soft communication-policy hint.
        s3 = f"【沟通策略提示】: {posture_tone}"

        # Compatibility layout panel: current world and actionable pointers.
        s4: Dict[str, Any] = {
            "wake_reason": wake_reason,
            "current_time": t_now.isoformat(),
            "focused_fact_pointers": active_focus_facts or [],
            "condition_ready_tasks": ready_tasks or [],
        }

        raw_repr = f"{s1}\n{s2}\n{s3}\n{json.dumps(s4, ensure_ascii=False)}"
        tok_cnt = estimate_token_count(raw_repr)

        return CockpitManifest(
            step1_self_mirror=s1,
            step2_rapport_model=s2,
            step3_posture_and_tone=s3,
            step4_world_inspection=s4,
            wake_reason=wake_reason,
            timestamp=t_now,
            manifest_token_count=tok_cnt,
        )
