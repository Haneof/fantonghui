"""阶段二：单维时间金字塔多尺度逐级结晶与无损穿透（MT-015）。

宪法红线：**总结是新观察层，绝非压缩删除原始记录**——结晶器只消费
记录指针生成上层总结节点并回注引擎（append-only），原始记录条数
在结晶前后必须逐位不变。

无损穿透断言：从任一年度总结结论出发，沿 child_refs 指针链
年→季→月→周→日→原始记录，一键穿透到当时某一句原始原话切片；
:func:`TimePyramid.audit` 输出证据链断裂率（盲测要求 0.0%）。

结晶为确定性模板聚合（零大模型调用），Token 成本可复算可审计——
这是"多尺度摘要"的工程化口径：结论层廉价、证据层永存。
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from aios_core.contracts.refs import ObjectRef
from aios_core.query.search import MindRecord, MultidimensionalSearchEngine

__all__ = [
    "PyramidLevel",
    "PyramidNode",
    "TimePyramid",
    "TimePyramidCrystallizer",
    "DrillPath",
]

UTC = timezone.utc

PyramidLevel = Literal["day", "week", "month", "quarter", "year"]


@dataclass(frozen=True, slots=True)
class PyramidNode:
    """金字塔节点：上层结论 + 指向下层的指针（总结层，可穿透）。"""

    node_id: str
    level: PyramidLevel
    period_label: str
    period_start: date
    period_end: date
    conclusion: str
    record_count: int
    child_ids: tuple[str, ...]
    ref: ObjectRef

    @property
    def tokens(self) -> int:
        return max(1, len(self.conclusion) // 4)


@dataclass(frozen=True, slots=True)
class DrillPath:
    """一次下钻穿透的完整证据链（年→…→原始记录）。"""

    leaf_record_id: str
    chain: tuple[str, ...]          # node_id 自上而下，末位为 day 节点
    leaf_reachable: bool


@dataclass(slots=True)
class TimePyramid:
    """结晶产物：节点索引 + 逐级父子关系。"""

    nodes: dict[str, PyramidNode] = field(default_factory=dict)
    leaves: dict[str, str] = field(default_factory=dict)   # leaf_record_id -> day node_id
    source_record_count: int = 0

    def by_level(self, level: PyramidLevel) -> list[PyramidNode]:
        return sorted(
            (n for n in self.nodes.values() if n.level == level),
            key=lambda n: n.period_start,
        )

    def drill_down(self, leaf_record_id: str) -> DrillPath:
        """从索引定位叶 → 沿父链上溯构造自上而下穿透路径。"""
        day_id = self.leaves.get(leaf_record_id)
        if day_id is None:
            return DrillPath(
                leaf_record_id=leaf_record_id, chain=(), leaf_reachable=False
            )
        chain: list[str] = [day_id]
        current = day_id
        level_order: tuple[PyramidLevel, ...] = ("week", "month", "quarter", "year")
        for level in level_order:
            parent = next(
                (
                    n.node_id
                    for n in self.nodes.values()
                    if n.level == level and current in n.child_ids
                ),
                None,
            )
            if parent is None:
                return DrillPath(
                    leaf_record_id=leaf_record_id,
                    chain=tuple(reversed(chain)),
                    leaf_reachable=False,
                )
            chain.append(parent)
            current = parent
        return DrillPath(
            leaf_record_id=leaf_record_id,
            chain=tuple(reversed(chain)),   # year → … → day
            leaf_reachable=True,
        )

    def audit(self, leaf_record_ids: list[str]) -> tuple[float, list[DrillPath]]:
        """证据链断裂率 = 不可达叶占比（盲测红线：0.0%）。"""
        paths = [self.drill_down(leaf) for leaf in leaf_record_ids]
        broken = sum(1 for p in paths if not p.leaf_reachable)
        rate = broken / len(paths) if paths else 0.0
        return rate, paths


class TimePyramidCrystallizer:
    """日→周→月→季→年 逐级结晶（确定性模板，零 LLM 调用）。"""

    def __init__(self, *, engine: MultidimensionalSearchEngine | None = None) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------

    def crystallize(self, records: list[MindRecord]) -> TimePyramid:
        """五级结晶；总结节点回注引擎（append-only），原始记录不动。"""
        dated = [
            r for r in records if r.occurred_at is not None
        ]
        pyramid = TimePyramid(source_record_count=len(dated))
        day_groups: dict[date, list[MindRecord]] = {}
        for r in dated:
            day_groups.setdefault(r.occurred_at.date(), []).append(r)  # type: ignore[union-attr]

        # ---- 日层 ----
        for day, recs in sorted(day_groups.items()):
            node = self._make_node(
                level="day",
                period_start=day,
                period_end=day,
                conclusion=self._day_conclusion(day, recs),
                record_count=len(recs),
                child_ids=(),
                leaf_ids=[r.record_id for r in recs],
            )
            pyramid.nodes[node.node_id] = node
            for r in recs:
                if r.record_id not in pyramid.leaves:
                    pyramid.leaves[r.record_id] = node.node_id

        # ---- 周 / 月 / 季 / 年 逐级聚合 ----
        parent_spec: tuple[tuple[PyramidLevel, PyramidLevel, object], ...] = (
            ("week", "day", _week_key),
            ("month", "week", _month_key),
            ("quarter", "month", _quarter_key),
            ("year", "quarter", _year_key),
        )
        for level, child_level, key_fn in parent_spec:
            groups: dict[object, list[PyramidNode]] = {}
            for node in pyramid.nodes.values():
                if node.level != child_level:
                    continue
                groups.setdefault(key_fn(node.period_start), []).append(node)
            for key, children in groups.items():
                start = min(c.period_start for c in children)
                end = max(c.period_end for c in children)
                node = self._make_node(
                    level=level,  # type: ignore[arg-type]
                    period_start=start,
                    period_end=end,
                    conclusion=self._aggregate_conclusion(level, children),  # type: ignore[arg-type]
                    record_count=sum(c.record_count for c in children),
                    child_ids=tuple(sorted(c.node_id for c in children)),
                    leaf_ids=[],
                )
                pyramid.nodes[node.node_id] = node
        return pyramid

    def register_into_engine(
        self, pyramid: TimePyramid, engine: MultidimensionalSearchEngine
    ) -> int:
        """总结节点作为新观察层回注引擎（append-only，annotation 型）。"""
        registered = 0
        for node in pyramid.nodes.values():
            engine.register(MindRecord(
                record_id=node.node_id,
                record_type="annotation",
                keywords=("总结", node.level, node.period_label),
                content=node.conclusion,
                occurred_at=datetime.combine(
                    node.period_start, datetime.min.time(), tzinfo=UTC
                ),
            ))
            registered += 1
        return registered

    # ------------------------------------------------------------------

    def _make_node(
        self,
        *,
        level: PyramidLevel,
        period_start: date,
        period_end: date,
        conclusion: str,
        record_count: int,
        child_ids: tuple[str, ...],
        leaf_ids: list[str],
    ) -> PyramidNode:
        label = {
            "day": period_start.isoformat(),
            "week": f"{period_start.isocalendar().year}-W{period_start.isocalendar().week:02d}",
            "month": f"{period_start.year}-{period_start.month:02d}",
            "quarter": f"{period_start.year}-Q{(period_start.month - 1) // 3 + 1}",
            "year": str(period_start.year),
        }[level]
        node_id = f"py-{level}-{label}"
        return PyramidNode(
            node_id=node_id,
            level=level,
            period_label=label,
            period_start=period_start,
            period_end=period_end,
            conclusion=conclusion,
            record_count=record_count,
            child_ids=child_ids,
            ref=ObjectRef(object_id=node_id, revision=1),
        )

    def _day_conclusion(self, day: date, recs: list[MindRecord]) -> str:
        kw = Counter(
            k for r in recs for k in r.keywords if k not in ("motion",)
        )
        top = "、".join(k for k, _ in kw.most_common(3))
        types = Counter(r.record_type for r in recs)
        return (
            f"{day.isoformat()} 共 {len(recs)} 条事实（"
            + "，".join(f"{t}×{c}" for t, c in types.most_common())
            + f"）；高频主题：{top or '无'}"
        )

    def _aggregate_conclusion(
        self, level: str, children: list[PyramidNode]
    ) -> str:
        total = sum(c.record_count for c in children)
        themes = Counter(
            k for c in children for k in _conclusion_keywords(c.conclusion)
        )
        top = "、".join(k for k, _ in themes.most_common(4))
        span = f"{children[0].period_label}~{children[-1].period_label}"
        if level == "week":
            return f"周报（{span}）：聚合 {len(children)} 个日总结、{total} 条事实；主线：{top}"
        if level == "month":
            return f"月报（{span}）：聚合 {len(children)} 周、{total} 条事实；主线：{top}"
        if level == "quarter":
            return f"季报（{span}）：聚合 {len(children)} 个月、{total} 条事实；主线：{top}"
        return f"年报（{span}）：聚合 {len(children)} 个季度、{total} 条事实；主线：{top}"


def _week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso.year, iso.week)


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _quarter_key(d: date) -> tuple[int, int]:
    return (d.year, (d.month - 1) // 3 + 1)


def _year_key(d: date) -> int:
    return d.year


def _conclusion_keywords(text: str) -> list[str]:
    """从子节点结论中提取聚合主题（确定性切词：顿号/主题段）。"""
    if "；主线：" not in text and "高频主题：" not in text:
        return []
    tail = text.split("主线：")[-1] if "主线：" in text else text.split("高频主题：")[-1]
    tail = tail.split("（")[0].strip("；。 ")
    return [t for t in tail.split("、") if t]
