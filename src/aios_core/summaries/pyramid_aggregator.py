"""M1-010R 5D 时空多尺度连续聚合器与时间金字塔物化视图。

落实宪法第二十五至二十七条铁律（最高违宪红线）：

1. **总结绝不是压缩删除！** 总结是一个全新的观察层，绝不修改、绝不删除底层事实；
2. **原始事实永存**：``generate_materialized_rollup`` 生成月/年总结后，日记录与
   底层原始事件字节级保留在证据保险库（evidence vault）中，vault 只读、**永不删除**，
   绝不允许任何代码路径执行删除或覆盖（呼应"老王案：历史绝不篡改"铁律）。
   注意措辞：这里的保证是「永存」（never deleted），不是「永驻内存」（RAM resident）。
   当前实现的 vault 是进程内字典，进程退出即丢失；§25 要求的是跨进程持久永存，
   须由 storage 层落盘承载（本模块不做持久化，也不应假装做了）——见交付报告 P2 项；
3. **多尺度金字塔物化视图**：DAY < WEEK < MONTH < YEAR 四层物化，支撑手环端侧
   5D 滑动条从 1 秒到 10 年（``CONTINUOUS_ZOOM_SECONDS``）连续无损缩放与逐级下钻。

5D 聚合函数：物理距离 (x, y, z) × 时间衰减 (t) × 羁绊权重 (r) × 可信度 (c)

- 时间衰减 t：近因系数 ``recency = (t_event - t_start) / span``，跨度末端为 1.0，
  向跨度起点方向线性衰减（span 为 0 时视为 1.0）；
- 物理距离 xyz：邻近系数 ``prox = 1 / (1 + sqrt(x^2 + y^2 + z^2))``，
  距坐标原点越近权重越高；
- 事件权重 ``w = c * r * recency * prox``，用于合成文本中的 5D 总权重与时空加权重心；
  缺失 5D 描述字段的字段按缺省中性值 1.0 处理，并计入 ``missingness_ratio``。

无损下钻：``drill_down(summary_id, target_sub_scale)``

- 目标尺度为 DAY：返回底层原始事件 dict 的深拷贝列表（完好无损、按时间序），
  调用方对结果的任何修改都无法污染证据保险库；
- 目标尺度为中间层（WEEK / MONTH）：返回父总结时间跨度内该层物化出的
  ``TimePyramidSummary`` 子总结列表，其 evidence_ids 之并集与父总结严格相等，
  且子总结可以继续逐级下钻直至 DAY 层原始事件；
- 下钻是纯读操作：O(log n + k) 窗口定位 + O(k) 物化，典型规模下响应 <= 45ms。
"""
from __future__ import annotations

import copy
import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "CONTINUOUS_ZOOM_SECONDS",
    "MAX_SPAN_SECONDS",
    "SCALE_ORDER",
    "PyramidAggregator",
    "PyramidError",
    "TimePyramidSummary",
    "finer_than",
]

#: 细 -> 粗 的时间尺度序。索引越小越细粒度（下钻只能向更小索引方向进行）。
SCALE_ORDER: Tuple[str, ...] = ("DAY", "WEEK", "MONTH", "YEAR")

#: 手环端侧 5D 滑动条连续缩放范围（秒）：从 1 秒到 10 年。
CONTINUOUS_ZOOM_SECONDS: Tuple[int, int] = (1, 10 * 365 * 24 * 3600)

#: 5D 描述字段：物理距离 (x, y, z) × 时间衰减 (t，即事件 time) × 羁绊权重 (r) × 可信度 (c)。
_FIVE_D_FIELDS: Tuple[str, ...] = ("x", "y", "z", "r", "c")

#: 每个尺度允许的最大事件跨度（秒）。``generate_materialized_rollup`` 只聚合调用方
#: 已经切好的**单个自然窗口**，scale 既是标签也是手环 5D 滑动条取内容的依据；
#: 若跨度超过该尺度的自然上限（例如把 28 天标成 WEEK），标签就在说谎，
#: 滑动条会按错误粒度取内容 —— 故 fail-closed 拒绝，而不是静默产出一个错标总结。
#: 上限取该尺度最长自然窗口的长度（最长月 31 天、闰年 366 天），不做日历对齐要求：
#: 对齐由调用方切片负责，本模块只保证「跨度不超过一个自然窗口」。
MAX_SPAN_SECONDS: Dict[str, float] = {
    "DAY": 24 * 3600.0,
    "WEEK": 7 * 24 * 3600.0,
    "MONTH": 31 * 24 * 3600.0,
    "YEAR": 366 * 24 * 3600.0,
}

_SCALE_RANK: Dict[str, int] = {scale: index for index, scale in enumerate(SCALE_ORDER)}


class PyramidError(ValueError):
    """金字塔聚合协议错误。

    覆盖：非法尺度、非法 dimension_id、空事件窗口、未知 summary_id / event_id、
    非法下钻方向（只能向更细尺度下钻）、以及证据冲突（同一 id 原始事实被改写）。
    """


def _normalize_scale(scale: Any) -> str:
    if isinstance(scale, str) and scale.strip().upper() in _SCALE_RANK:
        return scale.strip().upper()
    raise PyramidError(f"invalid scale {scale!r}; expected one of {list(SCALE_ORDER)}")


def finer_than(fine_scale: str, coarse_scale: str) -> bool:
    """``fine_scale`` 是否严格细于（低于）``coarse_scale`` 的尺度。"""
    return _SCALE_RANK[_normalize_scale(fine_scale)] < _SCALE_RANK[_normalize_scale(coarse_scale)]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any, *, field_name: str, event_id: str) -> datetime:
    """把事件时间归一化为 aware UTC。

    - ``datetime``：naive 视为 UTC，aware 转换为 UTC；
    - ISO 字符串：``datetime.fromisoformat`` 解析（支持 ``Z`` 后缀），同样规则归一化。
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PyramidError(
                f"event {event_id!r} field {field_name!r} is not a valid ISO datetime: {value!r}"
            ) from exc
    else:
        raise PyramidError(
            f"event {event_id!r} field {field_name!r} must be a datetime or ISO string, "
            f"got {type(value).__name__}"
        )
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _unit_factor(value: Any, field_name: str, event_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PyramidError(f"event {event_id!r} field {field_name!r} must be a number, got {value!r}")
    number = float(value)
    if math.isnan(number) or number < 0.0 or number > 1.0:
        raise PyramidError(
            f"event {event_id!r} field {field_name!r} must be within [0, 1], got {value!r}"
        )
    return number


def _window_key(utc_time: datetime, scale: str) -> int:
    """目标尺度自然窗口的整数分组键（随时间单调递增，支撑 O(k) 无分配分组）。"""
    if scale == "WEEK":
        iso = utc_time.date().isocalendar()
        return iso.year * 53 + iso.week
    if scale == "MONTH":
        return utc_time.year * 12 + (utc_time.month - 1)
    return utc_time.year  # YEAR


def _copy_event(value: Any, memo: Dict[int, Any]) -> Any:
    """事件载荷的结构化深拷贝：容器（dict/list/set）递归复制，不可变标量共享。

    与 ``copy.deepcopy`` 对 dict/list 的隔离语义等价（含环保护），但省去
    ``__reduce_ex__`` 分派与类型分派表查找，大规模下钻（万级事件）时显著更快，
    保证下钻响应 <= 45ms 红线。调用方拿到的是全新容器树，任何篡改都无法污染
    证据保险库原件。
    """
    if isinstance(value, dict):
        cached = memo.get(id(value))
        if cached is not None:
            return cached
        result: Dict[Any, Any] = {}
        memo[id(value)] = result
        for key, item in value.items():
            result[key] = _copy_event(item, memo)
        return result
    if isinstance(value, list):
        cached = memo.get(id(value))
        if cached is not None:
            return cached
        result_list: List[Any] = []
        memo[id(value)] = result_list
        for item in value:
            result_list.append(_copy_event(item, memo))
        return result_list
    if isinstance(value, set):
        cached = memo.get(id(value))
        if cached is not None:
            return cached
        result_set: set = set()
        memo[id(value)] = result_set
        for item in value:
            result_set.add(_copy_event(item, memo))
        return result_set
    return value


def _describe_event(
    payload: Dict[str, Any], event_id: str
) -> Tuple[float, bool, Optional[Tuple[float, float, float]]]:
    """写入路径一次性完成 5D 描述校验与基础权重计算。

    返回 ``(base_weight, has_full_5d, xyz)``：

    - ``base_weight = c * r * prox``，缺失字段按中性值 1.0 处理；
    - ``prox = 1 / (1 + sqrt(x^2 + y^2 + z^2))``（仅在 5D 完整时生效）；
    - 校验失败（c/r 越界、xyz 非数值）在写入时立即抛出 ``PyramidError``，
      使下钻/物化读路径保持纯计算、零校验开销（<= 45ms 红线的关键）。
    """
    missing = [key for key in _FIVE_D_FIELDS if key not in payload]
    has_full_5d = not missing

    xyz: Optional[Tuple[float, float, float]] = None
    for key in ("x", "y", "z"):
        if key in payload and (
            isinstance(payload[key], bool) or not isinstance(payload[key], (int, float))
        ):
            raise PyramidError(
                f"event {event_id!r} field {key!r} must be a number, got {payload[key]!r}"
            )
    if has_full_5d:
        x = float(payload["x"])
        y = float(payload["y"])
        z = float(payload["z"])
        xyz = (x, y, z)

    base_weight = 1.0
    if "c" in payload:
        base_weight *= _unit_factor(payload["c"], "c", event_id)
    if "r" in payload:
        base_weight *= _unit_factor(payload["r"], "r", event_id)
    if xyz is not None:
        distance = math.sqrt(xyz[0] ** 2 + xyz[1] ** 2 + xyz[2] ** 2)
        base_weight *= 1.0 / (1.0 + distance)

    return base_weight, has_full_5d, xyz


class TimePyramidSummary(BaseModel):
    """时间金字塔物化总结视图（新观察层，不替代、不压缩、不删除底层事实）。"""

    model_config = ConfigDict(extra="forbid")

    summary_id: str = Field(min_length=1)
    scale: str = Field(..., description="DAY / WEEK / MONTH / YEAR")
    start_time: datetime
    end_time: datetime
    dimension_id: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    synthesis_text: str = Field(min_length=1)
    evidence_ids: List[str] = Field(min_length=1)
    missingness_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_pyramid_contract(self) -> "TimePyramidSummary":
        if self.scale not in _SCALE_RANK:
            raise ValueError(f"scale must be one of {list(SCALE_ORDER)}, got {self.scale!r}")
        try:
            inverted = self.start_time > self.end_time
        except TypeError as exc:
            raise ValueError(
                "start_time and end_time must share comparable timezone awareness"
            ) from exc
        if inverted:
            raise ValueError("start_time must not be after end_time")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must not contain duplicates")
        return self


@dataclass
class _VaultEvent:
    """证据保险库中的底层原始事件（深拷贝、只读、永存）。

    ``base_weight`` / ``has_full_5d`` / ``xyz`` 在写入时一次性预计算，
    下钻物化读路径只做纯算术，不再重复校验与开方。
    """

    payload: Dict[str, Any]
    event_id: str
    utc_time: datetime
    base_weight: float = 1.0
    has_full_5d: bool = True
    xyz: Optional[Tuple[float, float, float]] = None


@dataclass
class _PyramidRecord:
    """物化总结的内部索引记录，支撑 O(log n + k) 无损下钻。"""

    summary_id: str
    scale: str
    dimension_id: str
    start_utc: datetime
    end_utc: datetime
    events: List[_VaultEvent] = field(default_factory=list)
    utc_times: List[datetime] = field(default_factory=list)


class PyramidAggregator:
    """5D 时空多尺度时间金字塔物化聚合器。

    宪法不变量（第二十五至二十七条铁律）：

    - 任何 ``generate_materialized_rollup`` 调用只**新增**高层物化视图，绝不修改、
      绝不删除底层事件；
    - 底层事件在首次出现时被深拷贝进证据保险库 ``_vault``，vault 只读、原始事实
      永存；同一 event id 再次出现时内容必须与原件逐字节一致，否则抛出
      ``PyramidError``（证据冲突），杜绝任何覆盖式改写；
    - ``drill_down`` 为纯读操作，任何下钻结果都是深拷贝，调用方篡改结果
      无法污染 vault。
    """

    def __init__(self, *, clock: Optional[Callable[[], datetime]] = None) -> None:
        self._clock = clock or _utc_now
        self._vault: Dict[str, _VaultEvent] = {}
        self._summaries: Dict[str, TimePyramidSummary] = {}
        self._records: Dict[str, _PyramidRecord] = {}

    # ------------------------------------------------------------------
    # 物化聚合
    # ------------------------------------------------------------------

    def generate_materialized_rollup(
        self,
        scale: str,
        dimension_id: str,
        events: List[Dict[str, Any]],
        *,
        now: Optional[datetime] = None,
    ) -> TimePyramidSummary:
        """聚合生成单层物化总结视图。

        绝不删除底层 events：每个事件被深拷贝进证据保险库后，仅提取高阶物化层。
        ``now`` 用于 summary_id 的时间戳，缺省使用注入时钟（``clock`` 参数）。
        """
        normalized_scale = _normalize_scale(scale)
        _validate_dimension_id(dimension_id)
        if not isinstance(events, (list, tuple)) or len(events) == 0:
            raise PyramidError("events must be a non-empty list of event dicts")
        stamp = now if now is not None else self._clock()

        vault_events = [self._ingest_event(event) for event in events]
        vault_events.sort(key=lambda v: (v.utc_time, v.event_id))

        unique_events: List[_VaultEvent] = []
        seen_ids: set = set()
        for vault_event in vault_events:
            if vault_event.event_id not in seen_ids:
                seen_ids.add(vault_event.event_id)
                unique_events.append(vault_event)

        return self._materialize(
            normalized_scale, dimension_id, unique_events, now=stamp, id_base=None
        )

    # ------------------------------------------------------------------
    # 无损下钻
    # ------------------------------------------------------------------

    def drill_down(self, summary_id: str, target_sub_scale: str) -> List[Any]:
        """无损下钻：从高层总结回溯到目标细粒度尺度的明细。

        - ``target_sub_scale == "DAY"``：返回底层原始事件深拷贝列表（完好无损，
          按时间序），证据链 100% 可回溯；
        - ``target_sub_scale`` 为中间层（WEEK / MONTH）：返回父总结时间跨度内
          该层物化的 ``TimePyramidSummary`` 子总结列表，evidence_ids 并集与父
          总结严格相等，且子总结可继续下钻；
        - 只能向严格更细的尺度下钻；下钻为纯读操作，响应目标 <= 45ms。
        """
        record = self._records.get(summary_id)
        if record is None:
            raise PyramidError(f"unknown summary_id: {summary_id!r}")
        target = _normalize_scale(target_sub_scale)
        if not finer_than(target, record.scale):
            raise PyramidError(
                f"drill_down target {target} must be strictly finer than summary scale "
                f"{record.scale} (down-drill only, scale order: {' < '.join(SCALE_ORDER)})"
            )

        low = bisect_left(record.utc_times, record.start_utc)
        high = bisect_right(record.utc_times, record.end_utc)
        window_events = record.events[low:high]

        if target == "DAY":
            return [_copy_event(vault_event.payload, {}) for vault_event in window_events]

        groups: Dict[int, List[_VaultEvent]] = {}
        for vault_event in window_events:
            key = _window_key(vault_event.utc_time, target)
            groups.setdefault(key, []).append(vault_event)

        sub_summaries: List[TimePyramidSummary] = []
        for index, group_events in enumerate(groups.values()):
            sub_summaries.append(
                self._materialize(
                    target,
                    record.dimension_id,
                    group_events,
                    now=self._clock(),
                    id_base=f"sub_{target.lower()}_{summary_id}_{index:03d}",
                )
            )
        return sub_summaries

    # ------------------------------------------------------------------
    # 只读查询接口
    # ------------------------------------------------------------------

    def get_summary(self, summary_id: str) -> TimePyramidSummary:
        """按 summary_id 取回物化总结。"""
        try:
            return self._summaries[summary_id]
        except KeyError:
            raise PyramidError(f"unknown summary_id: {summary_id!r}") from None

    def summary_ids(self) -> List[str]:
        """当前已物化的全部 summary_id（含下钻产出的子总结）。"""
        return list(self._summaries)

    def vault_size(self) -> int:
        """证据保险库中永存的底层原始事件数量。"""
        return len(self._vault)

    def get_raw_event(self, event_id: str) -> Dict[str, Any]:
        """取回底层原始事件的深拷贝（宪法审计入口：原始事实永存可验证）。"""
        try:
            return _copy_event(self._vault[event_id].payload, {})
        except KeyError:
            raise PyramidError(f"unknown event_id: {event_id!r}") from None

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _ingest_event(self, event: Any) -> _VaultEvent:
        if not isinstance(event, dict):
            raise PyramidError(f"event must be a dict, got {type(event).__name__}")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise PyramidError("each event requires a non-empty string field 'id'")
        if "time" not in event:
            raise PyramidError(f"event {event_id!r} is missing required field 'time'")

        payload = copy.deepcopy(event)
        utc_time = _as_utc(payload["time"], field_name="time", event_id=event_id)
        base_weight, has_full_5d, xyz = _describe_event(payload, event_id)

        existing = self._vault.get(event_id)
        if existing is not None:
            if existing.payload != payload:
                raise PyramidError(
                    f"evidence conflict: event {event_id!r} is already preserved in the "
                    "vault with different content; raw facts are permanent and may not be overwritten"
                )
            return existing

        vault_event = _VaultEvent(
            payload=payload,
            event_id=event_id,
            utc_time=utc_time,
            base_weight=base_weight,
            has_full_5d=has_full_5d,
            xyz=xyz,
        )
        self._vault[event_id] = vault_event
        return vault_event

    def _materialize(
        self,
        scale: str,
        dimension_id: str,
        vault_events: List[_VaultEvent],
        *,
        now: datetime,
        id_base: Optional[str],
    ) -> TimePyramidSummary:
        if not vault_events:
            raise PyramidError("cannot materialize an empty window")

        span_start = vault_events[0].utc_time
        span_end = vault_events[-1].utc_time
        span_seconds = (span_end - span_start).total_seconds()

        max_span = MAX_SPAN_SECONDS[scale]
        if span_seconds > max_span:
            raise PyramidError(
                f"{scale} rollup cannot span {span_seconds:.0f}s (> {max_span:.0f}s, the "
                f"longest natural {scale} window); slice the caller window per scale — "
                "a mislabeled summary would serve the wrong granularity to the 5D slider"
            )

        total_weight = 0.0
        weighted_coords = [0.0, 0.0, 0.0]
        centroid_weight = 0.0
        missing_count = 0
        for vault_event in vault_events:
            if span_seconds > 0:
                # 时间衰减 t：近因系数，跨度末端 1.0 -> 起点 0.0
                weight = vault_event.base_weight * (
                    (vault_event.utc_time - span_start).total_seconds() / span_seconds
                )
            else:
                weight = vault_event.base_weight
            if not vault_event.has_full_5d:
                missing_count += 1
            total_weight += weight
            if vault_event.has_full_5d:
                xyz = vault_event.xyz
                if xyz is None:
                    # 写入路径已保证 has_full_5d <=> xyz 非空；这里不用 assert，
                    # 因为 python -O 会剥离 assert，届时不变量破裂会静默变成 TypeError。
                    raise PyramidError(
                        "internal invariant broken: event "
                        f"{vault_event.event_id!r} is marked 5D-complete but has no coordinates"
                    )
                weighted_coords[0] += xyz[0] * weight
                weighted_coords[1] += xyz[1] * weight
                weighted_coords[2] += xyz[2] * weight
                centroid_weight += weight

        count = len(vault_events)
        centroid = None
        if centroid_weight > 0:
            centroid = tuple(coord / centroid_weight for coord in weighted_coords)

        # 机械聚合层只允许陈述**本函数真正测量过的量**。
        # 违宪点（已修）：此处曾硬编码「关系稳步加深」。该句与任何输入无关——
        # 本函数不测量趋势方向，在全部事件为负效价、羁绊权重 r 递减、甚至
        # missingness_ratio == 1.0（五项 5D 描述全缺）时它照样输出，是一句
        # 恒真的假话。它同时违反：
        #   · §11 分寸感自涌现 / R3 §5.1「严禁写死亲密度结论」；
        #   · governance/runtime_policy.json style_constraints
        #     .hardcoded_intimacy_rules_prohibited = true；
        #   · ADJ-003「机械触发不直接产生语义结论」（task_readiness
        #     .mechanical_trigger_output_is_binary_signal_only = true）。
        # headline 原为「阶段性演变概览」，同样预设了「演变」已经发生
        # （单事件窗口内不存在演变），一并改为中性的结构标签。
        headline = f"{scale} 阶段汇总"
        synthesis = (
            f"在此跨度内沉淀了 {count} 项核心事实（底层原始记录一条未删）。"
            f"5D 聚合：总权重 {total_weight:.3f}"
        )
        if centroid is not None:
            synthesis += (
                f"，时空重心 ({centroid[0]:.2f}, {centroid[1]:.2f}, {centroid[2]:.2f})"
            )
        else:
            # 不可计算就必须说不可计算，不能沉默省略——沉默会被读成「重心为零/无位置」。
            synthesis += "，时空重心不可计算（窗口内无 5D 完整且权重非零的事件）"
        if missing_count:
            # 缺失必须披露：缺省中性值 1.0 会抬高权重，不披露等于把降级伪装成正常。
            synthesis += (
                f"；其中 {missing_count} 项 5D 描述不完整（缺失率 "
                f"{missing_count / count:.1%}），缺失维度按中性缺省 1.0 计入"
            )
        synthesis += "。"

        summary_id = self._alloc_summary_id(scale, dimension_id, now, id_base)
        summary = TimePyramidSummary(
            summary_id=summary_id,
            scale=scale,
            start_time=span_start,
            end_time=span_end,
            dimension_id=dimension_id,
            headline=headline,
            synthesis_text=synthesis,
            evidence_ids=[vault_event.event_id for vault_event in vault_events],
            missingness_ratio=missing_count / count,
        )
        record = _PyramidRecord(
            summary_id=summary_id,
            scale=scale,
            dimension_id=dimension_id,
            start_utc=span_start,
            end_utc=span_end,
            events=vault_events,
            utc_times=[vault_event.utc_time for vault_event in vault_events],
        )
        self._summaries[summary_id] = summary
        self._records[summary_id] = record
        return summary

    def _alloc_summary_id(
        self,
        scale: str,
        dimension_id: str,
        now: datetime,
        id_base: Optional[str],
    ) -> str:
        if id_base is not None:
            # 子总结 id 由 (父 id, 目标尺度, 窗口序号) 决定：对不变 vault 幂等可重放。
            return id_base
        base = f"sum_{scale.lower()}_{dimension_id}_{int(now.timestamp())}"
        candidate = base
        suffix = 2
        while candidate in self._summaries:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate


def _validate_dimension_id(dimension_id: Any) -> str:
    if not isinstance(dimension_id, str) or not dimension_id.strip():
        raise PyramidError(
            f"dimension_id must be a non-empty string, got {dimension_id!r}"
        )
    return dimension_id.strip()
