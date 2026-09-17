"""AI 自身世界模型存储通道与自省记忆库 (AISelfWorldStore).

贯彻宪法第九条（§30~32）、第三十二条之一《AI 自身世界维度、自省日总结与高手演进宪章》：
1. 双主体平等架构：维护【用户世界】与【AI 自身世界】两个平等的认知主体；
2. AI 自身世界拥有固定的主语标识：subject_id = "ai_agent_self"；
3. 持久化 AI 自身五大心智成长维度：
   - dim:ai_restraint：克制分寸感（防过度打扰、防爹味废话）
   - dim:ai_empathy：真人共情与损友默契度（反谄媚、反机械客服）
   - dim:ai_keenness：因果穿透敏锐度（抓住底层核心症结）
   - dim:ai_intervention：事前关键干预有效性（在危险/机遇前及早介入）
   - dim:ai_guilt：错判内疚与反思记忆（将教训刻入骨髓，永不再犯）
4. 结晶沉淀操作经验 (OperationExperience) 与沟通经验 (CommunicationExperience)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.enums import ObjectType, SourceClass
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import (
    CommunicationExperience,
    DimensionCurvePoint,
    ObjectRef,
    OperationExperience,
    Summary,
)

UTC = timezone.utc
AI_SELF_SUBJECT_ID = "ai_agent_self"

AI_SELF_CORE_DIMENSIONS = [
    "dim:ai_restraint",
    "dim:ai_empathy",
    "dim:ai_keenness",
    "dim:ai_intervention",
    "dim:ai_guilt",
]


class AISelfDimensionSnapshot(BaseModel):
    """AI 自身心智维度当前快照。"""

    model_config = ConfigDict(extra="forbid")

    dimension_id: str
    dimension_name: str
    current_score: float = Field(ge=0.0, le=100.0)
    velocity: float = 0.0
    evaluation_notes: str = ""
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AISelfWorldStore:
    """AI 自身世界存储管理器。"""

    def __init__(self, world_store: Any = None) -> None:
        self.world_store = world_store
        self._dimensions: Dict[str, AISelfDimensionSnapshot] = {
            "dim:ai_restraint": AISelfDimensionSnapshot(
                dimension_id="dim:ai_restraint",
                dimension_name="克制分寸感",
                current_score=85.0,
                evaluation_notes="初始基线：严格收敛于1~3句，非紧急绝不出声打扰",
            ),
            "dim:ai_empathy": AISelfDimensionSnapshot(
                dimension_id="dim:ai_empathy",
                dimension_name="真人共情与默契",
                current_score=80.0,
                evaluation_notes="初始基线：生死死党/损友僚机，不装模作样、不机械客服",
            ),
            "dim:ai_keenness": AISelfDimensionSnapshot(
                dimension_id="dim:ai_keenness",
                dimension_name="因果穿透敏锐度",
                current_score=75.0,
                evaluation_notes="初始基线：能穿透多维事实发现底层症结，非表面浅显归因",
            ),
            "dim:ai_intervention": AISelfDimensionSnapshot(
                dimension_id="dim:ai_intervention",
                dimension_name="事前关键干预有效性",
                current_score=70.0,
                evaluation_notes="初始基线：在疲劳驾驶、重大欺诈、健康崩盘前提供有效阻击",
            ),
            "dim:ai_guilt": AISelfDimensionSnapshot(
                dimension_id="dim:ai_guilt",
                dimension_name="错判内疚与自省记忆",
                current_score=10.0,
                evaluation_notes="初始基线：记录每次误报、打扰或错判，持续反躬自省",
            ),
        }
        self._curve_points: List[Dict[str, Any]] = []
        self._daily_reflections: List[Dict[str, Any]] = []
        self._op_experiences: List[Dict[str, Any]] = []
        self._comm_experiences: List[Dict[str, Any]] = []

    def update_dimension_score(
        self,
        dimension_id: str,
        new_score: float,
        *,
        notes: str = "",
        point_time: Optional[datetime] = None,
    ) -> AISelfDimensionSnapshot:
        """更新 AI 自身维度评分并记录时序曲线点。"""
        if dimension_id not in self._dimensions:
            raise KeyError(f"未知的 AI 自身世界维度: {dimension_id}")

        now = point_time or datetime.now(UTC)
        snap = self._dimensions[dimension_id]
        old_score = snap.current_score
        velocity = round(new_score - old_score, 2)

        snap.current_score = max(0.0, min(100.0, new_score))
        snap.velocity = velocity
        snap.evaluation_notes = notes
        snap.last_updated = now

        # 记录曲线历史点
        curve_entry = {
            "dimension_id": dimension_id,
            "subject_id": AI_SELF_SUBJECT_ID,
            "value": snap.current_score,
            "velocity": velocity,
            "point_time": now.isoformat(),
            "notes": notes,
        }
        self._curve_points.append(curve_entry)
        return snap

    def get_dimension_snapshot(self, dimension_id: str) -> AISelfDimensionSnapshot:
        if dimension_id not in self._dimensions:
            raise KeyError(f"未知的 AI 自身世界维度: {dimension_id}")
        return self._dimensions[dimension_id]

    def get_all_dimension_snapshots(self) -> Dict[str, AISelfDimensionSnapshot]:
        return dict(self._dimensions)

    def record_daily_reflection(
        self,
        reflection_date: str,
        summary_text: str,
        dimension_changes: Dict[str, float],
        guilt_points: List[str],
        crystallized_insights: List[str],
    ) -> Dict[str, Any]:
        """记录 AI 自身世界的每日照镜子日总结。"""
        record = {
            "reflection_id": f"refl_{reflection_date}_{new_object_id(ObjectType.SUMMARY)[:6]}",
            "subject_id": AI_SELF_SUBJECT_ID,
            "reflection_date": reflection_date,
            "summary_text": summary_text,
            "dimension_changes": dimension_changes,
            "guilt_points": guilt_points,
            "crystallized_insights": crystallized_insights,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._daily_reflections.append(record)

        # 同时应用维度变动
        for dim_id, delta in dimension_changes.items():
            if dim_id in self._dimensions:
                cur = self._dimensions[dim_id].current_score
                self.update_dimension_score(dim_id, cur + delta, notes=f"日复盘自省调优: {delta:+0.2f}")

        return record

    def record_operation_experience(
        self,
        query_intent: str,
        pathway_selected: str,
        tokens_consumed: int,
        latency_ms: float,
        efficiency_gain: float,
        lesson_learned: str,
    ) -> Dict[str, Any]:
        """沉淀操作经验。"""
        record = {
            "experience_id": f"op_exp_{new_object_id(ObjectType.OPERATION_EXPERIENCE)[:8]}",
            "subject_id": AI_SELF_SUBJECT_ID,
            "query_intent": query_intent,
            "pathway_selected": pathway_selected,
            "tokens_consumed": tokens_consumed,
            "latency_ms": latency_ms,
            "efficiency_gain": efficiency_gain,
            "lesson_learned": lesson_learned,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._op_experiences.append(record)
        return record

    def record_communication_experience(
        self,
        situation: str,
        posture_chosen: str,
        brevity_level: str,
        user_reaction: str,
        rapport_shift: float,
        rule_crystallized: str,
    ) -> Dict[str, Any]:
        """沉淀沟通经验。"""
        record = {
            "experience_id": f"comm_exp_{new_object_id(ObjectType.COMMUNICATION_EXPERIENCE)[:8]}",
            "subject_id": AI_SELF_SUBJECT_ID,
            "situation": situation,
            "posture_chosen": posture_chosen,
            "brevity_level": brevity_level,
            "user_reaction": user_reaction,
            "rapport_shift": rapport_shift,
            "rule_crystallized": rule_crystallized,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._comm_experiences.append(record)
        return record

    def get_recent_reflections(self, limit: int = 7) -> List[Dict[str, Any]]:
        return self._daily_reflections[-limit:]

    def get_crystallized_rules(self) -> List[str]:
        rules: List[str] = []
        for r in self._daily_reflections:
            rules.extend(r.get("crystallized_insights", []))
        for c in self._comm_experiences:
            rules.append(c.get("rule_crystallized", ""))
        return [r for r in rules if r]


__all__ = [
    "AI_SELF_CORE_DIMENSIONS",
    "AI_SELF_SUBJECT_ID",
    "AISelfDimensionSnapshot",
    "AISelfWorldStore",
]
