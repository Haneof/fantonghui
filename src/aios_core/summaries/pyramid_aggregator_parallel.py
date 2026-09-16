"""阶段二：时间金字塔多尺度逐级结晶与无损穿透。

对应《AIOS 核心系统宪法 v3.0》时间金字塔章节与端到端盲测总纲阶段二。

两条不可让渡的原则
------------------
1. **总结是新观察层，绝非压缩删除原始记录**。结晶出日/周/月/季/年总结之后，
   底层原始观测一条都不许少 —— 这是"证据链断裂率 0.0%"能成立的前提。
2. **宏观结论必须能一键无损穿透到当时那一句原话**。年度总结里的任何一条
   结论，顺着指针超链接逐级下钻，必须落到具体月份、具体日期、直至当时的
   原始原话切片；断链即为缺陷。

本模块只做"结晶 + 指针 + 穿透校验"，不做语义压缩（那是大模型复盘的职责）。
结晶产物的粒度、时间窗与状态直接对齐冻结契约 ``contracts.models.Summary``
（granularity / summary_time / summary_status），因此可以原样落库。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from aios_core.contracts.enums import SummaryStatus
from aios_core.contracts.time import as_utc, require_aware

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "TIER_ORDER",
    "ChainIntegrityReport",
    "DrillDownPath",
    "RawObservation",
    "SummaryNode",
    "SummaryTier",
    "TimePyramidAggregator",
]


class SummaryTier(StrEnum):
    """时间金字塔五层。"""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


TIER_ORDER: tuple[SummaryTier, ...] = (
    SummaryTier.DAY,
    SummaryTier.WEEK,
    SummaryTier.MONTH,
    SummaryTier.QUARTER,
    SummaryTier.YEAR,
)

_TIER_RANK: dict[SummaryTier, int] = {tier: i for i, tier in enumerate(TIER_ORDER)}


@dataclass(frozen=True, slots=True)
class RawObservation:
    """一条原始观测切片（最底层的"当时那一句原话"）。"""

    observation_id: str
    text: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class SummaryNode:
    """金字塔上的一层结晶。

    ``child_refs`` 指向下一层的结晶节点；只有 DAY 层的 ``leaf_refs`` 直接
    指向原始观测。这样"年 -> 季 -> 月 -> 周 -> 日 -> 原话"是一条纯指针链。
    """

    node_id: str
    tier: SummaryTier
    period_start: date
    period_end: date
    statement: str
    child_refs: tuple[str, ...] = ()
    leaf_refs: tuple[str, ...] = ()
    summary_status: SummaryStatus = SummaryStatus.CURRENT

    @property
    def granularity(self) -> str:
        """对齐冻结契约 ``Summary.granularity``。"""
        return self.tier.value


@dataclass(frozen=True, slots=True)
class DrillDownPath:
    """一次穿透下钻的完整路径。"""

    hops: tuple[str, ...]
    tiers: tuple[SummaryTier, ...]
    leaf_texts: tuple[str, ...]
    reached_raw: bool

    @property
    def depth(self) -> int:
        return len(self.hops)


@dataclass(frozen=True, slots=True)
class ChainIntegrityReport:
    """证据链完整性体检。"""

    nodes_checked: int
    dangling_child_refs: int
    dangling_leaf_refs: int
    tiers_reaching_raw: int
    total_paths: int
    broken_paths: int

    @property
    def breakage_rate(self) -> float:
        """证据链断裂率。工单要求恒为 0.0%。"""
        if self.total_paths == 0:
            return 0.0
        return self.broken_paths / self.total_paths


class TimePyramidAggregator:
    """把原始观测逐级结晶成五层时间金字塔，并保证穿透无损。"""

    def __init__(self) -> None:
        self._observations: dict[str, RawObservation] = {}
        self._nodes: dict[str, SummaryNode] = {}
        # (tier, period_start) -> node_id，保证同一周期只结晶一次
        self._index: dict[tuple[SummaryTier, date], str] = {}

    # ------------------------------------------------------------ 摄入

    def ingest_observation(
        self, observation_id: str, text: str, occurred_at: datetime
    ) -> RawObservation:
        """摄入一条原始观测。追加式：绝不覆盖、绝不删除既有观测。"""
        require_aware(occurred_at, "occurred_at")
        if not observation_id.strip():
            raise ValueError("observation_id must not be blank")
        if not text.strip():
            raise ValueError("observation text must not be blank")
        if observation_id in self._observations:
            raise ValueError(f"duplicate observation_id: {observation_id}")
        observation = RawObservation(
            observation_id=observation_id,
            text=text,
            occurred_at=as_utc(occurred_at, "occurred_at"),
        )
        self._observations[observation_id] = observation
        return observation

    def ingest_many(self, observations: Iterable[tuple[str, str, datetime]]) -> int:
        count = 0
        for observation_id, text, occurred_at in observations:
            self.ingest_observation(observation_id, text, occurred_at)
            count += 1
        return count

    @property
    def raw_observation_count(self) -> int:
        return len(self._observations)

    @property
    def summary_count(self) -> int:
        return len(self._nodes)

    # ------------------------------------------------------------ 周期

    @staticmethod
    def period_for(tier: SummaryTier, anchor: date) -> tuple[date, date]:
        """返回 anchor 所属周期的 [起, 止]（闭区间）。"""
        if tier is SummaryTier.DAY:
            return anchor, anchor
        if tier is SummaryTier.WEEK:
            start = anchor - timedelta(days=anchor.weekday())
            return start, start + timedelta(days=6)
        if tier is SummaryTier.MONTH:
            start = anchor.replace(day=1)
            end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            return start, end
        if tier is SummaryTier.QUARTER:
            quarter_first_month = ((anchor.month - 1) // 3) * 3 + 1
            start = anchor.replace(month=quarter_first_month, day=1)
            end_month = quarter_first_month + 2
            end = start.replace(month=end_month, day=1)
            end = (end + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            return start, end
        if tier is SummaryTier.YEAR:
            return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31)
        raise ValueError(f"unknown tier: {tier}")

    def _observations_in(self, start: date, end: date) -> list[RawObservation]:
        return [
            o
            for o in self._observations.values()
            if start <= o.occurred_at.date() <= end
        ]

    # ------------------------------------------------------------ 结晶

    def crystallize(self, tier: SummaryTier, anchor: date) -> SummaryNode | None:
        """结晶出 anchor 所属周期的一层总结。幂等：重复调用返回同一节点。

        **空周期不结晶**：周/月/季的周期边界会与相邻周期错位（例如跨月的
        那一周），若为空周期也建节点，就会产生"既无子节点也无叶子"的空壳，
        把合法的空档误判成证据链断裂。返回 None 表示该周期无数据。
        """
        key = (tier, self.period_for(tier, anchor)[0])
        existing = self._index.get(key)
        if existing is not None:
            return self._nodes[existing]

        start, end = self.period_for(tier, anchor)
        if not self._observations_in(start, end):
            return None

        if tier is SummaryTier.DAY:
            members = sorted(
                self._observations_in(start, end), key=lambda o: o.occurred_at
            )
            leaf_refs = tuple(o.observation_id for o in members)
            node = SummaryNode(
                node_id=f"sum_day_{start.isoformat()}",
                tier=tier,
                period_start=start,
                period_end=end,
                statement=self._statement(tier, start, end, len(members)),
                child_refs=(),
                leaf_refs=leaf_refs,
            )
        else:
            lower = TIER_ORDER[_TIER_RANK[tier] - 1]
            child_refs = self._crystallize_children(lower, start, end)
            covered = sum(self._leaf_count_below(c) for c in child_refs)
            node = SummaryNode(
                node_id=f"sum_{tier.value}_{start.isoformat()}",
                tier=tier,
                period_start=start,
                period_end=end,
                statement=self._statement(tier, start, end, covered),
                child_refs=child_refs,
            )

        self._nodes[node.node_id] = node
        self._index[key] = node.node_id
        return node

    def crystallize_all(self, anchor: date) -> dict[SummaryTier, SummaryNode]:
        """一次性把五层全部结晶出来（自底向上）。空周期不出现在结果里。"""
        out: dict[SummaryTier, SummaryNode] = {}
        for tier in TIER_ORDER:
            node = self.crystallize(tier, anchor)
            if node is not None:
                out[tier] = node
        return out

    def _crystallize_children(
        self, tier: SummaryTier, start: date, end: date
    ) -> tuple[str, ...]:
        refs: list[str] = []
        cursor = start
        while cursor <= end:
            node = self.crystallize(tier, cursor)
            if node is not None and node.node_id not in refs:
                refs.append(node.node_id)
            cursor = self._next_period_start(tier, cursor)
        return tuple(refs)

    @staticmethod
    def _next_period_start(tier: SummaryTier, current: date) -> date:
        _, period_end = TimePyramidAggregator.period_for(tier, current)
        return period_end + timedelta(days=1)

    def _leaf_count_below(self, node_id: str) -> int:
        node = self._nodes[node_id]
        if node.leaf_refs:
            return len(node.leaf_refs)
        return sum(self._leaf_count_below(c) for c in node.child_refs)

    @staticmethod
    def _statement(tier: SummaryTier, start: date, end: date, covered: int) -> str:
        return (
            f"{tier.value} summary {start.isoformat()}..{end.isoformat()} "
            f"covering {covered} raw observation(s)"
        )

    # ------------------------------------------------------------ 穿透

    def drill_down(self, node_id: str) -> DrillDownPath:
        """顺着指针超链接一路穿透到原始原话切片。"""
        hops: list[str] = []
        tiers: list[SummaryTier] = []
        leaves: list[str] = []
        seen_nodes: set[str] = set()
        seen_leaves: set[str] = set()

        def walk(current_id: str) -> bool:
            node = self._nodes.get(current_id)
            if node is None:
                return False  # 断链
            if current_id in seen_nodes:
                return True  # 已穿透过：周周期跨月会被相邻两个月共享，去重即可
            seen_nodes.add(current_id)
            hops.append(current_id)
            tiers.append(node.tier)
            if node.leaf_refs:
                for leaf in node.leaf_refs:
                    observation = self._observations.get(leaf)
                    if observation is None:
                        return False  # 断链：指向已不存在的原始观测
                    if leaf in seen_leaves:
                        continue
                    seen_leaves.add(leaf)
                    leaves.append(observation.text)
                return True
            if not node.child_refs:
                # 空周期已不再结晶，走到这里只能是数据被外部改动过。
                return not node.leaf_refs
            return all(walk(child) for child in node.child_refs)

        reached = walk(node_id)
        return DrillDownPath(
            hops=tuple(hops),
            tiers=tuple(tiers),
            leaf_texts=tuple(leaves),
            reached_raw=reached,
        )

    def verify_chain_integrity(self) -> ChainIntegrityReport:
        """全量体检：每一个结晶节点都必须能穿透到原始观测。"""
        dangling_children = 0
        dangling_leaves = 0
        total = 0
        broken = 0
        reaching_raw = 0

        for node in self._nodes.values():
            for child in node.child_refs:
                if child not in self._nodes:
                    dangling_children += 1
            for leaf in node.leaf_refs:
                if leaf not in self._observations:
                    dangling_leaves += 1

            total += 1
            path = self.drill_down(node.node_id)
            if path.reached_raw:
                reaching_raw += 1
            else:
                broken += 1

        return ChainIntegrityReport(
            nodes_checked=len(self._nodes),
            dangling_child_refs=dangling_children,
            dangling_leaf_refs=dangling_leaves,
            tiers_reaching_raw=reaching_raw,
            total_paths=total,
            broken_paths=broken,
        )

    # ------------------------------------------------------------ 查询

    def node(self, node_id: str) -> SummaryNode:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise KeyError(f"unknown summary node: {node_id}") from None

    def nodes_at(self, tier: SummaryTier) -> tuple[SummaryNode, ...]:
        return tuple(n for n in self._nodes.values() if n.tier is tier)

    def observations_on(self, day: date) -> tuple[RawObservation, ...]:
        return tuple(
            sorted(
                (o for o in self._observations.values() if o.occurred_at.date() == day),
                key=lambda o: o.occurred_at,
            )
        )
