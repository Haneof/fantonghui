"""AIOS 3.0 极简单次看盘聚合看板装配器 (Cockpit Manifest Optimizer).

贯彻最高宪法第二十四章第八十四条：
1. 单次看盘聚合原则（Single-Shot Cockpit Manifest）：
   - 严禁通过多轮低效对话唤醒 AI；
   - 系统如同飞行员进入驾驶舱看仪表盘，以极简、结构化的统一看板一次性交付给大模型；
2. AI 心智启动四步序（顺序绝不可颠倒！）：
   - 第一步：照镜子（AI 自省记忆与底线原则）
   - 第二步：校准羁绊（与用户的动态关系模型 DIM_AI_RAPPORT）
   - 第三步：确立姿态（情绪色调与态度：严肃/调侃/关切）
   - 第四步：审视用户世界与触发源（带着滤镜查看精准切片与条件就绪任务）
3. 严格控制 Token 封套：看板控制在 300~500 tokens，首字响应极速无卡顿。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aios_core.operations.world_operator import estimate_token_count

UTC = timezone.utc


class CockpitManifest(BaseModel):
    """单次看盘聚合看板数据结构。"""

    model_config = ConfigDict(extra="forbid")

    # 心智启动四步序结构
    step1_self_mirror: str = Field(min_length=1, description="第一步：照镜子（先看自己记忆与原则底线）")
    step2_rapport_model: str = Field(min_length=1, description="第二步：校准羁绊（看用户关系深度模型）")
    step3_posture_and_tone: str = Field(min_length=1, description="第三步：确立姿态与视角（定态度与语调）")
    step4_world_inspection: Dict[str, Any] = Field(description="第四步：审视用户世界（精准指针切片与任务）")

    # 看板元指标
    wake_reason: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    manifest_token_count: int = Field(ge=0)


class CockpitManifestOptimizer:
    """看板极简组装器。"""

    @classmethod
    def assemble_cockpit(
        cls,
        *,
        wake_reason: str,
        user_name: str = "老大",
        rapport_tier: str = "生死死党/损友僚机",
        rapport_notes: str = "深度默契，彼此信任，说话可直接幽默，有底线不谄媚",
        self_identity: str = "AIOS 3.0 端侧共生心智实体，独立平等，不迎合不虚伪，严守底线",
        posture_tone: str = "自然真诚、敏锐关切、关键节点直言不讳",
        active_focus_facts: Optional[List[Dict[str, Any]]] = None,
        ready_tasks: Optional[List[Dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> CockpitManifest:
        """组装符合心智四步序的极简看板。"""
        t_now = now or datetime.now(UTC)

        # 1. 照镜子
        s1 = f"【AI身份与底线】: {self_identity}"

        # 2. 校准羁绊
        s2 = f"【与{user_name}羁绊模型】: 等级={rapport_tier}; 特征={rapport_notes}"

        # 3. 确立姿态
        s3 = f"【当前姿态与音调】: {posture_tone}"

        # 4. 审视世界
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
