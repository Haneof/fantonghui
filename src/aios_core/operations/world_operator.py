"""AIOS 3.0 AI 世界操作原语与动作机制 (AI World Operations Suite).

贯彻最高宪法第十七章（§26~30）、第二十章（§67~70）、第二十四章（§84~89）
及老大五大铁律：
1. 输出质量第一：分级下钻，兼具因果深度与精准证据；
2. 老王案历史不可篡改：绝对禁止 SQL UPDATE/DELETE，只在今天（T_now）通过单跳隔离器挂载外挂解释层；
3. 紧急触发硬旁路跳过世界模型；
4. 大模型自主判断删除；
5. 新维度与自省严苛门槛。

核心组件：
- ScaleLevel: 生物多尺度时间枚举 (1s ~ 10y)
- TimeLensOperator: 时间滑动缩放与时空窗双重视角切片
- DimensionLensOperator: 维度开闭聚焦与跨维横向共振
- WorldNavigator: 超链接拓扑跳转与因果事件链穿透
- EvidenceDrillDownOperator: 分层指针下钻与极简 Token 按需物化
- CognitionOperator: 历史不可变今天打标签与单跳隔离认知增量
- ConditionalTaskOperator: 条件驱动零浪费任务调度
- WorldOperatorSuite: AI 操作世界集成驾驶舱
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from aios_core.contracts.enums import (
    ClaimType,
    KnowledgeState,
    ObjectType,
    SourceClass,
    TaskState,
    TaskType,
)
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import (
    Claim,
    Entity,
    EventAnchor,
    EvidenceSet,
    Observation,
    Relation,
    Task,
    TemporalExtent,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation import (
    BiTemporalEpistemicLens,
    EpistemicWorldLens,
    RetrospectiveAnnotation,
    SingleHopCascadeIsolator,
)
from aios_core.world.view_lens import view_at

UTC = timezone.utc


class ScaleLevel(StrEnum):
    """宪法第八十七条：生物多尺度时间镜头分级。"""

    SCALE_1S = "1s"       # 微观生理脉冲、单句语音瞬态原话切片
    SCALE_1MIN = "1min"   # 即时对话流、突发环境态势与即时生理波形
    SCALE_1H = "1h"       # 事件生命周期、单日活动轨迹、日总结
    SCALE_1D = "1d"       # 单日全局综合
    SCALE_1W = "1w"       # 中周期心理状态区间、周生活节奏
    SCALE_1M = "1m"       # 月度多维总结、人际关系波动
    SCALE_1Y = "1y"       # 宏观人生大章节、长期人际羁绊演变
    SCALE_10Y = "10y"     # 命运相变曲线、十年人生跨度


def estimate_token_count(text_or_obj: Any) -> int:
    """估算对象序列化后的 Token 消耗（按中英混合 1 token ≈ 3.2 字符启发式估算）。"""
    if text_or_obj is None:
        return 0
    if isinstance(text_or_obj, str):
        content = text_or_obj
    else:
        try:
            content = json.dumps(text_or_obj, ensure_ascii=False)
        except Exception:
            content = str(text_or_obj)
    chars = len(content)
    return max(1, math.ceil(chars / 3.2))


def _extract_ref_id(ref: Any) -> str:
    """从 ObjectRef 或 dict 中提取 object_id。"""
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        return str(ref.get("object_id", ""))
    if hasattr(ref, "object_id"):
        return str(ref.object_id)
    return str(ref)


class TimeLensOperator:
    """宪法第八十七条：5D 时间镜头滑动条与生物多尺度自由导航机制。"""

    def __init__(self, store: SQLiteWorldStore, aggregator: Any = None) -> None:
        self.store = store
        self.aggregator = aggregator
        self.current_scale: ScaleLevel = ScaleLevel.SCALE_1D

    def zoom(self, scale: ScaleLevel) -> ScaleLevel:
        """设定当前观察尺度。"""
        self.current_scale = scale
        return self.current_scale

    def slice_window(
        self,
        start: datetime,
        end: datetime,
        *,
        as_of: Optional[datetime] = None,
        lens_mode: str = "ANNOTATED",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """在时间滑动条上截取指定时空窗切片，支持历史回溯视角与注记视角。"""
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)

        start_iso = start.isoformat()
        end_iso = end.isoformat()

        # 读取切片
        all_objs: List[Dict[str, Any]] = []
        for o_type in (ObjectType.OBSERVATION, ObjectType.EVENT):
            all_objs.extend(self.store.list_payloads(object_type=o_type, knowledge_cutoff=as_of))

        # 读取外挂注记表（若有）
        annotations_by_target: Dict[str, List[Dict[str, Any]]] = {}
        if lens_mode == "ANNOTATED":
            try:
                import sqlite3
                with sqlite3.connect(self.store.db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT target_object_id, reinterpretation_claim, is_invalidating, created_at "
                        "FROM retrospective_annotations"
                    )
                    for tid, r_claim, is_inv, c_at in cur.fetchall():
                        annotations_by_target.setdefault(tid, []).append({
                            "reinterpretation_claim": r_claim,
                            "is_invalidating": bool(is_inv),
                            "annotated_at": c_at,
                        })
            except Exception:
                pass

        results: List[Dict[str, Any]] = []
        for obj in all_objs:
            obj_id = obj.get("object_id")
            obj_type = obj.get("object_type")
            occurred = obj.get("occurred", {})
            t_point = occurred.get("start") or occurred.get("point") or obj.get("created_at") or obj.get("learned_at")
            if not t_point:
                continue

            if start_iso <= t_point <= end_iso:
                item = {
                    "object_id": obj_id,
                    "object_type": obj_type,
                    "occurred_time": t_point,
                    "scale": self.current_scale.value,
                    "data": obj,
                }
                if lens_mode == "ANNOTATED" and obj_id in annotations_by_target:
                    item["annotations"] = annotations_by_target[obj_id]
                results.append(item)
                if len(results) >= limit:
                    break

        return results


class DimensionLensOperator:
    """宪法第八十八条：多维神经共振与跨维度对齐机制。"""

    def __init__(self, store: SQLiteWorldStore) -> None:
        self.store = store
        self.active_dimensions: Set[str] = set()

    def focus_dimensions(self, dimension_keys: Sequence[str]) -> Set[str]:
        """开启并聚焦特定维度集合，屏蔽无关维度噪声。"""
        self.active_dimensions = set(dimension_keys)
        return self.active_dimensions

    def align_cross_dimensions(
        self,
        time_window: Tuple[datetime, datetime],
        dimension_keys: Sequence[str],
        limit_per_dim: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """时空基准横向对齐：将不同维度的同一物理时间段拉平对齐。"""
        start, end = time_window
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)

        start_iso = start.isoformat()
        end_iso = end.isoformat()

        aligned_streams: Dict[str, List[Dict[str, Any]]] = {k: [] for k in dimension_keys}

        observations = self.store.list_payloads(object_type=ObjectType.OBSERVATION)
        for obs in observations:
            obj_id = obs.get("object_id")
            src_kind = obs.get("source_kind", "")
            occurred = obs.get("occurred", {})
            t_point = occurred.get("start") or occurred.get("point") or obs.get("created_at") or obs.get("learned_at")
            if not t_point or not (start_iso <= t_point <= end_iso):
                continue

            for dim in dimension_keys:
                matched = False
                if "health" in dim and src_kind in ("biometrics", "heart_rate", "sleep", "sensor"):
                    matched = True
                elif "social" in dim and src_kind in ("chat", "call", "audio", "message"):
                    matched = True
                elif "finance" in dim and src_kind in ("transaction", "bank", "receipt"):
                    matched = True
                elif "work" in dim and src_kind in ("calendar", "meeting", "work_log"):
                    matched = True
                elif dim in src_kind:
                    matched = True

                if matched and len(aligned_streams[dim]) < limit_per_dim:
                    aligned_streams[dim].append({
                        "object_id": obj_id,
                        "timestamp": t_point,
                        "dimension": dim,
                        "value": obs.get("value"),
                    })

        return aligned_streams


class WorldNavigator:
    """宪法第二十六章：世界超链接网络穿透检索与实体/事件导航器。"""

    def __init__(self, store: SQLiteWorldStore, traverser: Any = None) -> None:
        self.store = store
        self.traverser = traverser

    def hop_entity(self, entity_id: str, depth: int = 2) -> Dict[str, Any]:
        """从特定实体节点出发，进行结构化拓扑跳转（关联事件锚点、关联 Claim 与关联人脉）。"""
        # 1. 查找实体基础信息
        entity_payload = None
        try:
            entity_payload = self.store.get_payload(entity_id)
        except Exception:
            all_ents = self.store.list_payloads(object_type=ObjectType.ENTITY)
            for e in all_ents:
                if e.get("object_id") == entity_id:
                    entity_payload = e
                    break

        # 2. 查找包含该实体的事件锚点 (EventAnchor / ObjectType.EVENT)
        anchors: List[Dict[str, Any]] = []
        all_events = self.store.list_payloads(object_type=ObjectType.EVENT)
        for ev in all_events:
            participants = [_extract_ref_id(r) for r in ev.get("participant_refs", [])]
            if entity_id in participants or any(entity_id in p for p in participants):
                ev_refs = [_extract_ref_id(r) for r in ev.get("evidence_set_refs", [])]
                anchors.append({
                    "anchor_id": ev.get("object_id"),
                    "name": ev.get("title") or ev.get("name"),
                    "summary": ev.get("interpretation") or ev.get("summary"),
                    "occurred": ev.get("occurred") or ev.get("event_time"),
                    "evidence_set_refs": ev_refs,
                })

        # 3. 查找与该实体相关的 Claim
        claims: List[Dict[str, Any]] = []
        all_claims = self.store.list_payloads(object_type=ObjectType.CLAIM)
        for c in all_claims:
            subj = c.get("subject_id")
            claimant = c.get("claimant_id")
            content = c.get("content") or c.get("statement", "")
            if subj == entity_id or claimant == entity_id or entity_id in str(content):
                sup_refs = [_extract_ref_id(r) for r in c.get("support_evidence_set_refs", [])]
                if not sup_refs:
                    sup_refs = [_extract_ref_id(r) for r in c.get("evidence_set_refs", [])]
                claims.append({
                    "claim_id": c.get("object_id"),
                    "statement": content,
                    "confidence": c.get("confidence"),
                    "evidence_set_refs": sup_refs,
                })

        # 4. 查找直接关联 Relation
        relations: List[Dict[str, Any]] = []
        all_relations = self.store.list_payloads(object_type=ObjectType.RELATION)
        for r in all_relations:
            left_id = _extract_ref_id(r.get("left")) or r.get("source_id")
            right_id = _extract_ref_id(r.get("right")) or r.get("target_id")
            if left_id == entity_id or right_id == entity_id:
                relations.append({
                    "relation_id": r.get("object_id"),
                    "relation_type": r.get("relation_type"),
                    "left_id": left_id,
                    "right_id": right_id,
                })

        return {
            "root_entity_id": entity_id,
            "entity": entity_payload,
            "related_anchors": anchors,
            "related_claims": claims,
            "related_relations": relations,
        }

    def get_event_chain(self, anchor_ids: Sequence[str]) -> List[Dict[str, Any]]:
        """按时间序列因果穿透事件链。"""
        if not anchor_ids:
            return []
        chain = []
        for aid in anchor_ids:
            try:
                p = self.store.get_payload(aid)
            except Exception:
                continue
            occurred = p.get("occurred") or p.get("event_time") or {}
            t = occurred.get("start") or occurred.get("point") or p.get("learned_at") or ""
            ev_refs = [_extract_ref_id(r) for r in p.get("evidence_set_refs", [])]
            chain.append({
                "anchor_id": aid,
                "name": p.get("title") or p.get("name"),
                "summary": p.get("interpretation") or p.get("summary"),
                "timestamp": str(t),
                "evidence_set_refs": ev_refs,
            })
        chain.sort(key=lambda x: x["timestamp"])
        return chain


class EvidenceDrillDownOperator:
    """宪法第十三章、第二十四章：分层指针下钻与极简 Token 按需物化引擎。

    核心铁律：
    - 严禁将全量成千上万条日志一股脑灌进大模型上下文；
    - 第一层：只看摘要/元数据（~20 tokens）；
    - 第二层：只看证据集成员指针（~40 tokens）；
    - 第三层：仅当严格因果需要时，才解开目标微切片原话（~50 tokens）；
    - 相比全表扫描节省 90%~98% Token！
    """

    def __init__(self, store: SQLiteWorldStore) -> None:
        self.store = store

    def peek_claim(self, claim_id: str) -> Dict[str, Any]:
        """第一级下钻：极简查看 Claim 核心主张与元数据 (约 20~30 tokens)。"""
        try:
            payload = self.store.get_payload(claim_id)
        except Exception:
            return {"error": "CLAIM_NOT_FOUND", "claim_id": claim_id}

        stmt = payload.get("content") or payload.get("statement")
        sup_refs = payload.get("support_evidence_set_refs") or payload.get("evidence_set_refs") or []

        manifest = {
            "claim_id": claim_id,
            "statement": stmt,
            "confidence": payload.get("confidence"),
            "subject_id": payload.get("subject_id"),
            "evidence_count": len(sup_refs),
        }
        manifest["estimated_tokens"] = estimate_token_count(manifest)
        return manifest

    def get_evidence_pointers(self, claim_id: str) -> List[Dict[str, Any]]:
        """第二级下钻：获取证据集成员引用指针 (约 40~60 tokens)。"""
        try:
            c_payload = self.store.get_payload(claim_id)
        except Exception:
            return []

        ev_refs = c_payload.get("support_evidence_set_refs") or c_payload.get("evidence_set_refs") or []
        pointers: List[Dict[str, Any]] = []
        for ref in ev_refs:
            ref_id = _extract_ref_id(ref)
            try:
                ev_data = self.store.get_payload(ref_id)
            except Exception:
                continue
            members = [_extract_ref_id(m) for m in ev_data.get("member_refs", [])]
            pointers.append({
                "evidence_set_id": ref_id,
                "purpose": ev_data.get("purpose", ""),
                "member_observation_ids": members,
                "member_count": len(members),
            })
        return pointers

    def drill_observation_slice(
        self,
        observation_id: str,
        *,
        max_chars: int = 300,
    ) -> Dict[str, Any]:
        """第三级下钻：仅在必须时按需解开目标微观测原话切片 (约 30~50 tokens)。"""
        try:
            obs = self.store.get_payload(observation_id)
        except Exception:
            return {"error": "OBSERVATION_NOT_FOUND", "observation_id": observation_id}

        raw_val = obs.get("value")
        if isinstance(raw_val, str) and len(raw_val) > max_chars:
            slice_text = raw_val[:max_chars] + "...[TRUNCATED]"
        else:
            slice_text = raw_val

        slice_data = {
            "observation_id": observation_id,
            "modality": obs.get("modality"),
            "source_kind": obs.get("source_kind"),
            "occurred": obs.get("occurred"),
            "value_slice": slice_text,
        }
        slice_data["estimated_tokens"] = estimate_token_count(slice_data)
        return slice_data


@dataclass(frozen=True)
class CognitionAnnotation:
    """今天认知打标签记录（外挂解释图层）。"""

    annotation_id: str
    target_object_id: str
    target_object_type: ObjectType
    reinterpretation_claim: str
    is_invalidating: bool
    created_at: datetime
    created_by: str
    target_time_start: datetime
    target_time_end: datetime
    raw_annotation: RetrospectiveAnnotation

    @property
    def target_entity_id(self) -> str:
        return self.target_object_id

    @property
    def semantic_overlay(self) -> str:
        return self.reinterpretation_claim

    @property
    def learned_at(self) -> datetime:
        return self.created_at

    @property
    def recorded_at(self) -> datetime:
        return self.created_at

    @property
    def source_statement_ref(self) -> str:
        return self.created_by


class CognitionOperator:
    """宪法第二十章、老大第二铁律【老王案：历史绝不篡改，只在今天打标签】。"""

    def __init__(self, store: SQLiteWorldStore) -> None:
        self.store = store
        self.isolator = SingleHopCascadeIsolator()
        self._ensure_annotation_table()

    def _ensure_annotation_table(self) -> None:
        import sqlite3
        with sqlite3.connect(self.store.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS retrospective_annotations (
                    annotation_id TEXT PRIMARY KEY,
                    target_object_id TEXT NOT NULL,
                    target_object_type TEXT NOT NULL,
                    reinterpretation_claim TEXT NOT NULL,
                    is_invalidating INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def record_realization_today(
        self,
        target_object_id: str,
        target_object_type: ObjectType,
        reinterpretation_claim: str,
        *,
        is_invalidating: bool = False,
        actor: str = "ai_cognition_brain",
        now: Optional[datetime] = None,
    ) -> CognitionAnnotation:
        """在今天挂载外挂解释图层，不修改历史原始 Observation。"""
        t_now = now or datetime.now(UTC)
        if t_now.tzinfo is None:
            t_now = t_now.replace(tzinfo=UTC)
        annotation_id = new_object_id(ObjectType.REINTERPRETATION)

        # 探寻目标对象的历史时空跨度（不可变历史指针）
        t_start = t_now
        t_end = t_now
        try:
            target_payload = self.store.get_payload(target_object_id)
            occ = target_payload.get("occurred")
            if isinstance(occ, dict):
                s = occ.get("start")
                e = occ.get("end")
                if s:
                    t_start = datetime.fromisoformat(s)
                if e:
                    t_end = datetime.fromisoformat(e)
                elif s:
                    t_end = t_start
            elif isinstance(occ, str):
                t_start = datetime.fromisoformat(occ)
                t_end = t_start
        except Exception:
            pass

        if t_start.tzinfo is None:
            t_start = t_start.replace(tzinfo=UTC)
        if t_end.tzinfo is None:
            t_end = t_end.replace(tzinfo=UTC)

        # 确保符合时间因果律：learned_at >= target_time_end
        if t_now < t_end:
            t_end = t_now
        if t_start > t_end:
            t_start = t_end

        raw_anno = RetrospectiveAnnotation(
            annotation_id=annotation_id,
            target_entity_id=target_object_id,
            semantic_overlay=reinterpretation_claim,
            target_time_start=t_start,
            target_time_end=t_end,
            learned_at=t_now,
            recorded_at=t_now,
            source_statement_ref=actor,
        )

        anno = CognitionAnnotation(
            annotation_id=annotation_id,
            target_object_id=target_object_id,
            target_object_type=target_object_type,
            reinterpretation_claim=reinterpretation_claim,
            is_invalidating=is_invalidating,
            created_at=t_now,
            created_by=actor,
            target_time_start=t_start,
            target_time_end=t_end,
            raw_annotation=raw_anno,
        )

        import sqlite3
        with sqlite3.connect(self.store.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO retrospective_annotations (
                    annotation_id, target_object_id, target_object_type,
                    reinterpretation_claim, is_invalidating, created_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anno.annotation_id,
                    anno.target_object_id,
                    anno.target_object_type.value,
                    anno.reinterpretation_claim,
                    int(anno.is_invalidating),
                    anno.created_at.isoformat(),
                    anno.created_by,
                ),
            )
            conn.commit()
        self.isolator.register_node(anno.target_object_id)
        self.isolator.register_node(anno.annotation_id)
        self.isolator.add_dependency(anno.target_object_id, anno.annotation_id)
        return anno

    def commit_claim(
        self,
        statement: str,
        subject_id: str,
        evidence_set_refs: Sequence[str] = (),
        confidence: float = 0.9,
        *,
        now: Optional[datetime] = None,
    ) -> Claim:
        """向世界提交新认知 Claim（不可变追加）。"""
        t_now = now or datetime.now(UTC)
        if t_now.tzinfo is None:
            t_now = t_now.replace(tzinfo=UTC)

        sup_refs = [
            ObjectRef(object_id=ref, revision=1)
            if isinstance(ref, str) else ref
            for ref in evidence_set_refs
        ]

        claim = Claim(
            object_id=new_object_id(ObjectType.CLAIM),
            subject_id=subject_id,
            revision=1,
            claimant_id="ai_cognition_brain",
            claim_type=ClaimType.BELIEF,
            content=statement,
            valid_time=TemporalExtent.point(t_now),
            asserted_at=t_now,
            knowledge_state=KnowledgeState.INFERRED,
            confidence=confidence,
            support_evidence_set_refs=sup_refs,
            occurred=TemporalExtent.point(t_now),
            learned_at=t_now,
            recorded_at=t_now,
            created_by="ai_cognition_brain",
        )

        op = OperationRequest(
            operation_id=new_operation_id(),
            operation_name="world.claim.commit",
            expected_world_revision=self.store.current_world_revision(),
            reason=f"Commit new Claim: {statement[:30]}",
            idempotency_key=f"claim_{claim.object_id}",
            source_class=SourceClass.AI_COGNITION,
        )
        self.store.commit([claim], op)
        return claim


class ConditionalTaskOperator:
    """宪法第八十六条：条件驱动的任务零浪费执行机制。"""

    def __init__(self, store: SQLiteWorldStore) -> None:
        self.store = store

    def schedule_conditional_task(
        self,
        title: str,
        trigger_condition: Dict[str, Any],
        *,
        due_time: Optional[datetime] = None,
        priority: int = 50,
        now: Optional[datetime] = None,
    ) -> Task:
        """调度带条件的智能任务，若未声明条件则直接违宪报错。"""
        if not trigger_condition or not isinstance(trigger_condition, dict):
            raise ValueError(
                "ConditionalTaskOperator 违宪拦截：待办任务必须声明显式触发条件（trigger_condition），"
                "杜绝无条件轮询导致的 Token 空转浪费！"
            )

        cond_type = trigger_condition.get("type")
        if not cond_type or cond_type not in (
            "time_reached",
            "context_matched",
            "event_occurred",
            "dependency_ready",
            "biometric_threshold",
        ):
            raise ValueError(f"无效的触发条件类型: {cond_type}")

        t_now = now or datetime.now(UTC)
        if t_now.tzinfo is None:
            t_now = t_now.replace(tzinfo=UTC)

        task_id = new_object_id(ObjectType.TASK)

        task = Task(
            object_id=task_id,
            subject_id="user_1",
            revision=1,
            task_type=TaskType.SCHEDULED,
            task_state=TaskState.DRAFT,
            title=title,
            priority=priority,
            completion_condition=trigger_condition,
            next_wake_at=due_time,
            deadline=due_time,
            timezone_name="UTC",
            occurred=TemporalExtent.point(t_now),
            learned_at=t_now,
            recorded_at=t_now,
            created_by="ai_task_operator",
        )

        op = OperationRequest(
            operation_id=new_operation_id(),
            operation_name="world.task.schedule",
            expected_world_revision=self.store.current_world_revision(),
            reason=f"Schedule conditional task: {title}",
            idempotency_key=f"task_{task_id}",
            source_class=SourceClass.AI_COGNITION,
        )
        self.store.commit([task], op)
        return task


class MultidimensionalSearchOperator:
    """宪法第二十章：多维心智感知搜索操作原语。"""

    def __init__(self, store: SQLiteWorldStore, index: Optional[Any] = None) -> None:
        self.store = store
        if index is not None:
            self.index = index
        else:
            from aios_core.query.search import MultidimensionalSearchEngine
            self.index = MultidimensionalSearchEngine(store.db_path, store=store)

    def search_mind(
        self,
        keywords: Sequence[str] = (),
        *,
        dimension: Optional[str] = None,
        entity_id: Optional[str] = None,
        object_types: Optional[Sequence[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: int = 20,
    ) -> Any:
        """执行多维心智联合感知检索。"""
        return self.index.search_mind(
            keywords=keywords,
            dimension=dimension,
            entity_id=entity_id,
            object_types=object_types,
            time_range=time_range,
            limit=limit,
        )

    def query(
        self,
        keywords: Sequence[str] = (),
        *,
        dimension: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """极简快捷检索接口，直接输出结构化摘要切片（Token <= 150）。"""
        page = self.search_mind(keywords=keywords, dimension=dimension, entity_id=entity_id, limit=limit)
        results = []
        for hit in page.hits:
            results.append({
                "object_id": hit.object_id,
                "revision": hit.revision,
                "object_type": hit.object_type,
                "dimension": hit.dimension,
                "score": hit.score,
                "excerpt": hit.excerpt,
                "is_annotation": hit.is_annotation,
                "estimated_tokens": hit.estimated_tokens,
            })
        return results


class WorldOperatorSuite:
    """AI 操作世界集成驾驶舱套件 (World Operator Suite)。"""

    def __init__(self, store: SQLiteWorldStore, aggregator: Any = None, traverser: Any = None) -> None:
        self.store = store
        self.time_lens = TimeLensOperator(store, aggregator=aggregator)
        self.dim_lens = DimensionLensOperator(store)
        self.navigator = WorldNavigator(store, traverser=traverser)
        self.evidence_drill = EvidenceDrillDownOperator(store)
        self.cognition = CognitionOperator(store)
        self.task_operator = ConditionalTaskOperator(store)
        self.search = MultidimensionalSearchOperator(store)

