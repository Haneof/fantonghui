"""AIOS 3.0 全维度多尺度时间总结引擎（Universal Multi-Scale Time Summarization Engine）。

老大铁律指示（2026-09-16）：
“时间维度的总结是所有维度都要有的机制，不是单独某个维度的专属！
为什么多尺度穿透没有加入季度、半年、3年、5年这样的世界跨度？”

本模块彻底根治时间跨度夹缝与维度割裂问题：
1. 【全维度通用机制】：
   - 绝非生理健康或某单一维度的专有逻辑；
   - 任何已注册维度（dim:health, dim:emotion, dim:social, dim:finance, dim:cognition,
     dim:career, dim:habit, dim:narrative 等）均平等享有全尺度聚合与下钻；
   - 同时原生支持 SYNOPTIC_ALL（跨维度全景人生总结），将多维共振事实统一成宏观全貌。

2. 【九档无损物化时间阶梯】：
   - DAY (日, 1d)
   - WEEK (周, 7d)
   - MONTH (月, 30d)
   - QUARTER (季度, 3个月：经营/大考复盘)
   - HALF_YEAR (半年, 6个月：半年度体检/学期大总结)
   - YEAR (年度, 1年：人生大章节)
   - MULTI_YEAR_3Y (3年：初创期/高中/大周期)
   - MULTI_YEAR_5Y (5年：五年规划/相变大跨度)
   - DECADE (10年：命运轨迹/十年宏观相变)

3. 【证据并集严格守恒与零篡改】：
   - 总结是新增的高阶观察层，绝不修改、绝不删除底层事实；
   - 逐级下钻至单条 Observation 原始事实，SHA-256 证据链 100% 守恒；
   - 产物原生对齐 `aios_core.contracts.models.Summary` 契约，支持 SQLite 持久化与检索。
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.enums import ObjectType, SummaryStatus
from aios_core.contracts.models import Summary, TemporalExtent
from aios_core.contracts.refs import ObjectRef


UTC = timezone.utc


class UniversalTimeScale(StrEnum):
    """九档全局统一物化时间尺度。"""
    DAY = "DAY"                        # 单日全局综合（24小时）
    WEEK = "WEEK"                      # 周生活节律（7天）
    MONTH = "MONTH"                    # 月度多维总结（自然月）
    QUARTER = "QUARTER"                # 季度经营与大考复盘（Q1~Q4，3个月）
    HALF_YEAR = "HALF_YEAR"            # 半年度体检与目标对比（H1~H2，6个月）
    YEAR = "YEAR"                      # 年度人生大章节（自然年）
    MULTI_YEAR_3Y = "MULTI_YEAR_3Y"    # 三年大周期（如高中三年/初创阶段）
    MULTI_YEAR_5Y = "MULTI_YEAR_5Y"    # 五年规划与人生相变跨度
    DECADE = "DECADE"                  # 十年命运大轨迹


#: 尺度从细到粗的严格偏序排列
SCALE_LADDER: Tuple[UniversalTimeScale, ...] = (
    UniversalTimeScale.DAY,
    UniversalTimeScale.WEEK,
    UniversalTimeScale.MONTH,
    UniversalTimeScale.QUARTER,
    UniversalTimeScale.HALF_YEAR,
    UniversalTimeScale.YEAR,
    UniversalTimeScale.MULTI_YEAR_3Y,
    UniversalTimeScale.MULTI_YEAR_5Y,
    UniversalTimeScale.DECADE,
)
_SCALE_INDEX: Dict[UniversalTimeScale, int] = {scale: idx for idx, scale in enumerate(SCALE_LADDER)}

#: 全维度共振综合标识
SYNOPTIC_ALL: str = "ALL_DIMENSIONS"


def scale_finer_than(fine: UniversalTimeScale | str, coarse: UniversalTimeScale | str) -> bool:
    """判定 fine 尺度是否严格细于 coarse 尺度（下钻合法性判断）。"""
    fine_val = UniversalTimeScale(str(fine).strip().upper())
    coarse_val = UniversalTimeScale(str(coarse).strip().upper())
    return _SCALE_INDEX[fine_val] < _SCALE_INDEX[coarse_val]


# ---------------------------------------------------------------------------
# 时间窗口计算与分桶算法（按自然日历与多年周期对齐）
# ---------------------------------------------------------------------------

def calculate_window_bounds(moment: datetime, scale: UniversalTimeScale) -> Tuple[datetime, datetime]:
    """根据给定时点与尺度，计算其所属的标准自然时间窗区间 [start_utc, end_utc]。"""
    dt = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    dt_utc = dt.astimezone(UTC)

    if scale == UniversalTimeScale.DAY:
        start = datetime(dt_utc.year, dt_utc.month, dt_utc.day, tzinfo=UTC)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.WEEK:
        start_day = datetime(dt_utc.year, dt_utc.month, dt_utc.day, tzinfo=UTC)
        start = start_day - timedelta(days=dt_utc.isoweekday() - 1)
        end = start + timedelta(days=7) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.MONTH:
        start = datetime(dt_utc.year, dt_utc.month, 1, tzinfo=UTC)
        next_month = dt_utc.month % 12 + 1
        next_year = dt_utc.year + (dt_utc.month // 12)
        end = datetime(next_year, next_month, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.QUARTER:
        quarter = (dt_utc.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = datetime(dt_utc.year, start_month, 1, tzinfo=UTC)
        end_month = start_month + 3
        next_year = dt_utc.year + (end_month - 1) // 12
        end_month_norm = (end_month - 1) % 12 + 1
        end = datetime(next_year, end_month_norm, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.HALF_YEAR:
        start_month = 1 if dt_utc.month <= 6 else 7
        start = datetime(dt_utc.year, start_month, 1, tzinfo=UTC)
        end_month = start_month + 6
        next_year = dt_utc.year + (end_month - 1) // 12
        end_month_norm = (end_month - 1) % 12 + 1
        end = datetime(next_year, end_month_norm, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.YEAR:
        start = datetime(dt_utc.year, 1, 1, tzinfo=UTC)
        end = datetime(dt_utc.year + 1, 1, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.MULTI_YEAR_3Y:
        start_year = (dt_utc.year // 3) * 3
        start = datetime(start_year, 1, 1, tzinfo=UTC)
        end = datetime(start_year + 3, 1, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.MULTI_YEAR_5Y:
        start_year = (dt_utc.year // 5) * 5
        start = datetime(start_year, 1, 1, tzinfo=UTC)
        end = datetime(start_year + 5, 1, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    if scale == UniversalTimeScale.DECADE:
        start_year = (dt_utc.year // 10) * 10
        start = datetime(start_year, 1, 1, tzinfo=UTC)
        end = datetime(start_year + 10, 1, 1, tzinfo=UTC) - timedelta(microseconds=1)
        return start, end

    raise ValueError(f"Unsupported time scale: {scale}")


def get_window_id(moment: datetime, scale: UniversalTimeScale, dimension_id: str) -> str:
    """生成确定性窗口 ID。"""
    start, _ = calculate_window_bounds(moment, scale)
    dim_slug = dimension_id.replace(":", "_").replace("/", "_")
    return f"win_{scale.value.lower()}_{dim_slug}_{start.strftime('%Y%m%d%H%M%S')}"


# ---------------------------------------------------------------------------
# 全维度多尺度通用总结数据结构
# ---------------------------------------------------------------------------

class DimensionSummaryNode(BaseModel):
    """单维度或跨维度在某尺度下的高阶物化总结节点。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    summary_id: str = Field(..., description="总结全局唯一 ID")
    dimension_id: str = Field(..., description="所属维度（如 dim:health 或 ALL_DIMENSIONS）")
    scale: UniversalTimeScale = Field(..., description="时间尺度（DAY ~ DECADE）")
    start_time: datetime = Field(..., description="时间窗起点")
    end_time: datetime = Field(..., description="时间窗终点")
    headline: str = Field(..., description="一句话核心结论")
    synthesis_narrative: str = Field(..., description="深度多维归纳与因果叙事")
    evidence_ids: List[str] = Field(default_factory=list, description="所涵盖的底层原始事实 ID 列表")
    dimension_metrics: Dict[str, Any] = Field(default_factory=dict, description="该维度的聚合量化指标")
    child_summary_ids: List[str] = Field(default_factory=list, description="下一级子总结 ID（用于逐级物化下钻）")
    source_event_count: int = Field(default=0, description="支撑该总结的原始事实总条数")
    fingerprint_sha256: str = Field(..., description="证据集 SHA-256 机械可审计指纹")

    def to_contract_summary(
        self,
        *,
        subject_id: str = "user_1",
        created_by: str = "agent_pyramid_engine",
        source_world_revision: int = 1,
    ) -> Summary:
        """导出为 AIOS 宪法规范的 Summary 实体，可直接入库 SQLite。"""
        dim_ref = None
        if self.dimension_id != SYNOPTIC_ALL:
            dim_ref = ObjectRef(
                object_id=self.dimension_id,
                revision=1
            )
        now = datetime.now(UTC)
        return Summary(
            object_id=self.summary_id,
            subject_id=subject_id,
            learned_at=now,
            recorded_at=now,
            created_by=created_by,
            dimension_ref=dim_ref,
            summary_time=TemporalExtent(start=self.start_time, end=self.end_time),
            granularity=self.scale.value,
            source_world_revision=source_world_revision,
            coverage={
                "dimension_id": self.dimension_id,
                "headline": self.headline,
                "event_count": self.source_event_count,
                "metrics": self.dimension_metrics,
                "fingerprint": self.fingerprint_sha256,
            },
            summary_status=SummaryStatus.CURRENT,
        )


# ---------------------------------------------------------------------------
# 全维度多尺度时间金字塔聚合与下钻引擎
# ---------------------------------------------------------------------------

class UniversalTimePyramidEngine:
    """全维度通用时间金字塔引擎：承载所有维度的日、周、月、季、半年、年、3年、5年、10年总结。"""

    def __init__(self) -> None:
        # 底层原始事实保险库：event_id -> payload dict（不可篡改、只读永存）
        self._raw_events_vault: Dict[str, Dict[str, Any]] = {}
        # 维度倒排索引：dimension_id -> List[event_id]
        self._dimension_index: Dict[str, List[str]] = {}
        # 物化总结缓存：summary_id -> DimensionSummaryNode
        self._summaries: Dict[str, DimensionSummaryNode] = {}
        # 时间窗反查索引：(scale, dimension_id, window_key) -> summary_id
        self._window_summary_map: Dict[Tuple[str, str, str], str] = {}

    def ingest_event(self, event: Dict[str, Any], dimension_id: str) -> str:
        """吸纳一条原始 Observation 事实进保险库，并挂载到指定维度。"""
        event_id = str(event.get("id") or f"obs_{len(self._raw_events_vault) + 1}")
        if "time" not in event:
            raise ValueError(f"Event {event_id} must have a 'time' field")

        # 确保时间为 aware UTC
        t = event["time"]
        if isinstance(t, str):
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        elif isinstance(t, datetime):
            dt = t if t.tzinfo is not None else t.replace(tzinfo=UTC)
        else:
            raise ValueError(f"Unsupported time type: {type(t)}")
        dt_utc = dt.astimezone(UTC)

        payload = copy.deepcopy(event)
        payload["id"] = event_id
        payload["time"] = dt_utc
        payload["dimension_id"] = dimension_id

        # 不可篡改断言（若已存在且内容不同，则拒绝）
        if event_id in self._raw_events_vault:
            existing = self._raw_events_vault[event_id]
            if existing != payload:
                raise ValueError(f"Fact immutability violation: event {event_id} already exists with different content")
            return event_id

        self._raw_events_vault[event_id] = payload
        self._dimension_index.setdefault(dimension_id, []).append(event_id)
        return event_id

    def list_dimensions(self) -> List[str]:
        """获取当前已存在事实的所有活跃维度清单。"""
        return sorted(self._dimension_index.keys())

    def get_events_for_dimension(
        self,
        dimension_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """获取指定维度在时间范围内的原始事实列表（按时间排序）。"""
        if dimension_id == SYNOPTIC_ALL:
            event_ids = list(self._raw_events_vault.keys())
        else:
            event_ids = self._dimension_index.get(dimension_id, [])

        matched: List[Dict[str, Any]] = []
        for eid in event_ids:
            ev = self._raw_events_vault[eid]
            t = ev["time"]
            if start_time and t < start_time:
                continue
            if end_time and t > end_time:
                continue
            matched.append(ev)

        matched.sort(key=lambda x: x["time"])
        return matched

    def summarize_window(
        self,
        dimension_id: str,
        scale: UniversalTimeScale,
        anchor_moment: datetime,
        *,
        custom_synthesizer: Optional[Callable[[List[Dict[str, Any]], str, UniversalTimeScale], Tuple[str, str, Dict[str, Any]]]] = None,
    ) -> DimensionSummaryNode:
        """为特定维度在特定时间尺度上生成物化总结。

        :param dimension_id: 可以是任何单一维度（如 dim:health, dim:career）或全维度 SYNOPTIC_ALL
        :param scale: DAY, WEEK, MONTH, QUARTER, HALF_YEAR, YEAR, MULTI_YEAR_3Y, MULTI_YEAR_5Y, DECADE
        :param anchor_moment: 落在目标窗口内的任意时点
        """
        start, end = calculate_window_bounds(anchor_moment, scale)
        window_key = f"{start.isoformat()}_{end.isoformat()}"
        lookup_key = (scale.value, dimension_id, window_key)

        if lookup_key in self._window_summary_map:
            cached_id = self._window_summary_map[lookup_key]
            return self._summaries[cached_id]

        # 获取窗口内的所有原始事实
        events = self.get_events_for_dimension(dimension_id, start_time=start, end_time=end)
        if not events:
            # 空窗口保护
            headline = f"【{dimension_id}】在 {scale.value} 区间无活动记录"
            narrative = "当前时间窗口内未检测到底层事实流入，系统保持静默观察。"
            metrics: Dict[str, Any] = {"event_count": 0}
            evidence_ids: List[str] = []
        else:
            evidence_ids = [e["id"] for e in events]
            if custom_synthesizer:
                headline, narrative, metrics = custom_synthesizer(events, dimension_id, scale)
            else:
                headline, narrative, metrics = self._default_synthesizer(events, dimension_id, scale)

        # 计算证据集不可篡改 SHA-256 指纹
        evidence_str = "".join(sorted(evidence_ids))
        fingerprint = hashlib.sha256(evidence_str.encode("utf-8")).hexdigest()

        summary_id = f"sum_{scale.value.lower()}_{dimension_id.replace(':', '_')}_{start.strftime('%Y%m%d%H%M')}"
        
        node = DimensionSummaryNode(
            summary_id=summary_id,
            dimension_id=dimension_id,
            scale=scale,
            start_time=start,
            end_time=end,
            headline=headline,
            synthesis_narrative=narrative,
            evidence_ids=evidence_ids,
            dimension_metrics=metrics,
            source_event_count=len(evidence_ids),
            fingerprint_sha256=fingerprint,
        )

        self._summaries[summary_id] = node
        self._window_summary_map[lookup_key] = summary_id
        return node

    def summarize_all_dimensions_at_scale(
        self,
        scale: UniversalTimeScale,
        anchor_moment: datetime,
    ) -> Dict[str, DimensionSummaryNode]:
        """一键对系统当前所有活跃维度执行该尺度的物化总结，并附加全维度 SYNOPTIC_ALL 宏观总结。"""
        results: Dict[str, DimensionSummaryNode] = {}
        # 1. 逐个维度分别总结
        for dim in self.list_dimensions():
            node = self.summarize_window(dim, scale, anchor_moment)
            results[dim] = node

        # 2. 全维度跨域共振总结
        synoptic_node = self.summarize_window(SYNOPTIC_ALL, scale, anchor_moment)
        results[SYNOPTIC_ALL] = synoptic_node
        return results

    def drill_down(
        self,
        summary_id: str,
        target_sub_scale: Optional[UniversalTimeScale] = None,
    ) -> List[Any]:
        """无损下钻：从高层总结回溯到更细粒度的子总结或最底层的原始 Observation。

        - 若 target_sub_scale 为 None 或 DAY：返回底层所有原始 Observation 的深拷贝列表；
        - 若 target_sub_scale 为中间尺度：自动物化该父时间跨度内的各子窗口总结列表，
          且所有子总结的 evidence_ids 并集必须与父总结严格 100% 守恒！
        """
        parent = self._summaries.get(summary_id)
        if parent is None:
            raise KeyError(f"Summary ID not found: {summary_id}")

        # 1. 直接下钻到底层原始事实
        if target_sub_scale is None or target_sub_scale == UniversalTimeScale.DAY:
            raw_facts = [
                copy.deepcopy(self._raw_events_vault[eid])
                for eid in parent.evidence_ids
                if eid in self._raw_events_vault
            ]
            raw_facts.sort(key=lambda x: x["time"])
            return raw_facts

        # 2. 下钻到中间层子尺度（如 DECADE -> YEAR, 或 YEAR -> QUARTER）
        if not scale_finer_than(target_sub_scale, parent.scale):
            raise ValueError(
                f"Drill-down target scale {target_sub_scale} must be strictly finer than parent scale {parent.scale}"
            )

        # 遍历父区间内的所有子窗口
        sub_nodes: List[DimensionSummaryNode] = []
        current_cursor = parent.start_time
        while current_cursor < parent.end_time:
            sub_node = self.summarize_window(parent.dimension_id, target_sub_scale, current_cursor)
            if sub_node.evidence_ids:  # 只收集包含证据的子窗口
                sub_nodes.append(sub_node)
            _, next_end = calculate_window_bounds(current_cursor, target_sub_scale)
            current_cursor = next_end + timedelta(microseconds=1)

        # 严格检验并集守恒性
        sub_evidence_set: Set[str] = set()
        for s in sub_nodes:
            sub_evidence_set.update(s.evidence_ids)

        parent_evidence_set = set(parent.evidence_ids)
        if sub_evidence_set != parent_evidence_set:
            diff = parent_evidence_set.symmetric_difference(sub_evidence_set)
            raise ValueError(f"Evidence union conservation violated during drill-down: difference={diff}")

        return sub_nodes

    # -----------------------------------------------------------------------
    # 默认合成器（用于无大模型介入时的轻量因果提炼与量化汇总）
    # -----------------------------------------------------------------------
    def _default_synthesizer(
        self,
        events: List[Dict[str, Any]],
        dimension_id: str,
        scale: UniversalTimeScale,
    ) -> Tuple[str, str, Dict[str, Any]]:
        count = len(events)
        texts = [str(e.get("text") or e.get("content") or "") for e in events if e.get("text") or e.get("content")]
        sample_snippets = "；".join(texts[:3])

        # 指标聚合
        metrics: Dict[str, Any] = {"total_events": count}
        numeric_keys = ["bpm", "g_force", "amount", "stress_score", "score"]
        for k in numeric_keys:
            vals = [float(e[k]) for e in events if k in e and isinstance(e[k], (int, float))]
            if vals:
                metrics[f"avg_{k}"] = round(sum(vals) / len(vals), 2)
                metrics[f"max_{k}"] = round(max(vals), 2)
                metrics[f"min_{k}"] = round(min(vals), 2)

        headline = f"【{dimension_id}·{scale.value}】共汇聚 {count} 条事实，态势平稳可追溯"
        narrative = f"在 {scale.value} 尺度周期内，该维度沉淀了 {count} 条确凿事实，典型样本包括：{sample_snippets}。证据链条完整闭环。"
        return headline, narrative, metrics

