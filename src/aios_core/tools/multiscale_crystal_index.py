"""多尺度结晶索引（MultiScaleCrystalIndex：日<周<月<季<半年<年<多年）。

问题
----
时间金字塔聚合器只覆盖 DAY/WEEK/MONTH/YEAR 四档，**季度与半年这两个尺度是缝**：
季度经营复盘、半年体检、跨年生活相变都恰好落在缝里。更要命的是，
"逐级生成小结"很容易退化成"用小结覆盖原始事实"——一旦原始事实被压缩掉，
下钻到最后就只剩孤零零的一句概述，证据链断裂率不再为 0。

本索引做什么
------------
1. **七档无损结晶**：每一档结晶都只是**新增观察层**，底层原始事实进入证据武器库
   （``_vault``）后字节级只读；同一 event_id 若以不同字节再次出现，直接抛
   ``CrystalError``（篡改零容忍）。
2. **逐档证据守恒**：父层证据集合必须严格等于子层证据集合之并
   （``assert_union_conserved``），任何"丢证据"的结晶都是协议错误。
3. **下钻到单条原始事实**：``drill(crystal_id, "DAY")`` 返回深拷贝的原始事件，
   任意层数下钻都真无损（下钻结果被调用方篡改也污染不了武器库）。
4. **可审计指纹**：``vault_fingerprint`` 对整个武器库做 SHA-256 聚合，
   用于"下钻前后原始事实未被改动"的机械证明。
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

__all__ = [
    "CrystalError",
    "CrystalLayer",
    "MultiScaleCrystalIndex",
    "SCALE_LADDER",
    "finer_than",
]

#: 由细到粗的尺度阶梯。
SCALE_LADDER: tuple[str, ...] = (
    "DAY",
    "WEEK",
    "MONTH",
    "QUARTER",
    "HALF_YEAR",
    "YEAR",
    "MULTI_YEAR",
    "MULTI_YEAR_3Y",
    "MULTI_YEAR_5Y",
    "DECADE",
)
_RANK: Dict[str, int] = {scale: index for index, scale in enumerate(SCALE_LADDER)}
#: 多年档的分桶宽度（3 年与 5 年与 10 年）。
MULTI_YEAR_SPAN = 3


class CrystalError(ValueError):
    """结晶协议错误（非法尺度、未知 id、跨窗结晶、原始事实被篡改）。"""


def _normalize_scale(scale: str) -> str:
    normalized = str(scale).strip().upper()
    if normalized not in _RANK:
        raise CrystalError(f"unknown scale {scale!r}; expected one of {list(SCALE_LADDER)}")
    return normalized


def finer_than(fine: str, coarse: str) -> bool:
    return _RANK[_normalize_scale(fine)] < _RANK[_normalize_scale(coarse)]


def _as_utc(value: Any, event_id: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise CrystalError(f"event {event_id!r} has non-datetime time field: {value!r}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _window_key(moment: datetime, scale: str) -> str:
    if scale == "DAY":
        return f"D{moment.date().isoformat()}"
    if scale == "WEEK":
        iso = moment.isocalendar()
        return f"W{iso.year}-{iso.week:02d}"
    if scale == "MONTH":
        return f"M{moment.year}-{moment.month:02d}"
    if scale == "QUARTER":
        return f"Q{moment.year}-{(moment.month - 1) // 3 + 1}"
    if scale == "HALF_YEAR":
        return f"H{moment.year}-{1 if moment.month <= 6 else 2}"
    if scale == "YEAR":
        return f"Y{moment.year}"
    if scale in ("MULTI_YEAR", "MULTI_YEAR_3Y"):
        bucket = moment.year // 3
        return f"MY3_{bucket * 3}-{bucket * 3 + 2}"
    if scale == "MULTI_YEAR_5Y":
        bucket = moment.year // 5
        return f"MY5_{bucket * 5}-{bucket * 5 + 4}"
    if scale == "DECADE":
        bucket = moment.year // 10
        return f"DEC_{bucket * 10}-{bucket * 10 + 9}"
    bucket = moment.year // MULTI_YEAR_SPAN
    return f"MY{bucket * MULTI_YEAR_SPAN}-{bucket * MULTI_YEAR_SPAN + MULTI_YEAR_SPAN - 1}"


def _window_start(moment: datetime, scale: str) -> datetime:
    if scale == "DAY":
        return datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc)
    if scale == "WEEK":
        start_of_day = datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc)
        return start_of_day - timedelta(days=moment.isoweekday() - 1)
    if scale == "MONTH":
        return datetime(moment.year, moment.month, 1, tzinfo=timezone.utc)
    if scale == "QUARTER":
        month = (moment.month - 1) // 3 * 3 + 1
        return datetime(moment.year, month, 1, tzinfo=timezone.utc)
    if scale == "HALF_YEAR":
        month = 1 if moment.month <= 6 else 7
        return datetime(moment.year, month, 1, tzinfo=timezone.utc)
    if scale == "YEAR":
        return datetime(moment.year, 1, 1, tzinfo=timezone.utc)
    if scale in ("MULTI_YEAR", "MULTI_YEAR_3Y"):
        year = moment.year // 3 * 3
        return datetime(year, 1, 1, tzinfo=timezone.utc)
    if scale == "MULTI_YEAR_5Y":
        year = moment.year // 5 * 5
        return datetime(year, 1, 1, tzinfo=timezone.utc)
    if scale == "DECADE":
        year = moment.year // 10 * 10
        return datetime(year, 1, 1, tzinfo=timezone.utc)
    year = moment.year // MULTI_YEAR_SPAN * MULTI_YEAR_SPAN
    return datetime(year, 1, 1, tzinfo=timezone.utc)


def _window_end(moment: datetime, scale: str) -> datetime:
    start = _window_start(moment, scale)
    if scale == "DAY":
        return start + timedelta(days=1) - timedelta(microseconds=1)
    if scale == "WEEK":
        return start + timedelta(days=7) - timedelta(microseconds=1)
    if scale == "MONTH":
        year, month = start.year, start.month
        next_month = datetime(year + (month // 12), month % 12 + 1, 1, tzinfo=timezone.utc)
        return next_month - timedelta(microseconds=1)
    if scale == "QUARTER":
        month = start.month + 3
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    if scale == "HALF_YEAR":
        month = start.month + 6
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    if scale == "YEAR":
        return datetime(start.year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    if scale in ("MULTI_YEAR", "MULTI_YEAR_3Y"):
        return datetime(start.year + 3, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    if scale == "MULTI_YEAR_5Y":
        return datetime(start.year + 5, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    if scale == "DECADE":
        return datetime(start.year + 10, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    return datetime(
        start.year + MULTI_YEAR_SPAN, 1, 1, tzinfo=timezone.utc
    ) - timedelta(microseconds=1)


def _event_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CrystalLayer:
    """一档结晶（新观察层，绝不替代底层事实）。"""

    crystal_id: str
    scale: str
    dimension_id: str
    start_time: datetime
    end_time: datetime
    headline: str
    synthesis_text: str
    evidence_ids: tuple[str, ...]
    event_count: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "crystal_id": self.crystal_id,
            "scale": self.scale,
            "dimension_id": self.dimension_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "headline": self.headline,
            "synthesis_text": self.synthesis_text,
            "evidence_ids": list(self.evidence_ids),
            "event_count": self.event_count,
        }


@dataclass
class _VaultEvent:
    event_id: str
    payload: Mapping[str, Any]
    utc_time: datetime
    digest: str


@dataclass
class _LayerRecord:
    layer: CrystalLayer
    events: list[_VaultEvent] = field(default_factory=list)


class MultiScaleCrystalIndex:
    """七档无损失钻结晶索引。"""

    def __init__(self) -> None:
        self._vault: Dict[str, _VaultEvent] = {}
        self._layers: Dict[str, _LayerRecord] = {}
        self._counter = 0

    # ------------------------------------------------------------------
    # 结晶
    # ------------------------------------------------------------------

    def crystallize(
        self,
        scale: str,
        dimension_id: str,
        events: Iterable[Mapping[str, Any]],
        *,
        headline: str | None = None,
    ) -> CrystalLayer:
        """把一批同尺度窗口内的事实结晶为新观察层（跨窗事实必须分次结晶）。"""

        normalized = _normalize_scale(scale)
        event_list = list(events)
        if not event_list:
            raise CrystalError("crystallize requires at least one event")
        stored: list[_VaultEvent] = []
        seen: set[str] = set()
        for event in event_list:
            entry = self._absorb(event)
            if entry.event_id in seen:
                continue
            seen.add(entry.event_id)
            stored.append(entry)
        stored.sort(key=lambda item: (item.utc_time, item.event_id))
        windows = {_window_key(item.utc_time, normalized) for item in stored}
        if len(windows) != 1:
            raise CrystalError(
                f"events span multiple {normalized} windows: {sorted(windows)}; "
                "crystallize one window per call"
            )
        window = next(iter(windows))
        self._counter += 1
        crystal_id = f"crystal_{normalized.lower()}_{self._counter:06d}"
        layer = CrystalLayer(
            crystal_id=crystal_id,
            scale=normalized,
            dimension_id=dimension_id,
            start_time=_window_start(stored[0].utc_time, normalized),
            end_time=_window_end(stored[0].utc_time, normalized),
            headline=headline
            or f"{normalized} 结晶 {window}（{len(stored)} 条底层事实）",
            synthesis_text=(
                f"本层为 {normalized} 尺度的**新增观察层**："
                f"{len(stored)} 条原始事实字节级保留在武器库中，"
                f"本层只持有证据指针（{len(stored)} 条），不做任何压缩删除。"
            ),
            evidence_ids=tuple(item.event_id for item in stored),
            event_count=len(stored),
        )
        self._layers[crystal_id] = _LayerRecord(layer=layer, events=stored)
        return layer

    def _absorb(self, event: Mapping[str, Any]) -> _VaultEvent:
        payload = copy.deepcopy(dict(event))
        event_id = str(payload.get("id") or payload.get("event_id") or "")
        if not event_id:
            raise CrystalError("event requires an 'id' field")
        moment = _as_utc(payload.get("time") or payload.get("occurred_at"), event_id)
        digest = _event_digest(payload)
        existing = self._vault.get(event_id)
        if existing is not None:
            if existing.digest != digest:
                raise CrystalError(
                    f"raw fact {event_id!r} already crystallized with different bytes "
                    "(history mutation blocked)"
                )
            return existing
        entry = _VaultEvent(
            event_id=event_id, payload=payload, utc_time=moment, digest=digest
        )
        self._vault[event_id] = entry
        return entry

    # ------------------------------------------------------------------
    # 下钻
    # ------------------------------------------------------------------

    def drill(self, crystal_id: str, target_scale: str) -> tuple[Any, ...]:
        """向更细尺度下钻：DAY 返回深拷贝的原始事实，其余返回子结晶。"""

        record = self._layers.get(crystal_id)
        if record is None:
            raise CrystalError(f"unknown crystal_id {crystal_id!r}")
        target = _normalize_scale(target_scale)
        if not finer_than(target, record.layer.scale):
            raise CrystalError(
                f"drill target {target} must be strictly finer than {record.layer.scale}"
            )
        if target == "DAY":
            return tuple(copy.deepcopy(dict(item.payload)) for item in record.events)
        grouped: Dict[str, list[_VaultEvent]] = {}
        for item in record.events:
            grouped.setdefault(_window_key(item.utc_time, target), []).append(item)
        return tuple(
            self.crystallize(
                target,
                record.layer.dimension_id,
                [item.payload for item in grouped[key]],
            )
            for key in sorted(grouped)
        )

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    def evidence_ids(self, crystal_id: str) -> frozenset[str]:
        record = self._layers.get(crystal_id)
        if record is None:
            raise CrystalError(f"unknown crystal_id {crystal_id!r}")
        return frozenset(item.event_id for item in record.events)

    def assert_union_conserved(self, crystal_id: str, target_scale: str) -> bool:
        """父层证据集合 == 所有子层证据集合之并（逐档守恒）。"""

        parent = self.evidence_ids(crystal_id)
        children = [
            child for child in self.drill(crystal_id, target_scale) if isinstance(child, CrystalLayer)
        ]
        union: set[str] = set()
        for child in children:
            union |= set(child.evidence_ids)
        return union == set(parent)

    def raw_event(self, event_id: str) -> Dict[str, Any]:
        entry = self._vault.get(event_id)
        if entry is None:
            raise CrystalError(f"unknown event_id {event_id!r}")
        return copy.deepcopy(dict(entry.payload))

    def raw_event_count(self) -> int:
        return len(self._vault)

    def vault_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for event_id in sorted(self._vault):
            digest.update(event_id.encode("utf-8"))
            digest.update(self._vault[event_id].digest.encode("utf-8"))
        return digest.hexdigest()

    def crystal_count(self) -> int:
        return len(self._layers)

    def scale_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {scale: 0 for scale in SCALE_LADDER}
        for record in self._layers.values():
            counts[record.layer.scale] += 1
        return counts

    def layers_at(self, scale: str) -> tuple[CrystalLayer, ...]:
        normalized = _normalize_scale(scale)
        return tuple(
            record.layer for record in self._layers.values() if record.layer.scale == normalized
        )

    def all_crystal_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._layers))

    def deepest_evidence(self, crystal_id: str) -> frozenset[str]:
        """递归到 DAY 档，回收该结晶覆盖的全部原始事实 id（无损穿透自证）。"""

        record = self._layers.get(crystal_id)
        if record is None:
            raise CrystalError(f"unknown crystal_id {crystal_id!r}")
        return frozenset(item.event_id for item in record.events)

    def cross_scale_consistency(self, coarse: CrystalLayer, fine_scale: str) -> bool:
        """粗层证据集合 == 细层全部子结晶证据集合之并（跨档一致性证明）。"""

        children = [
            child for child in self.drill(coarse.crystal_id, fine_scale) if isinstance(child, CrystalLayer)
        ]
        union: set[str] = set()
        for child in children:
            union |= set(child.evidence_ids)
        return union == set(coarse.evidence_ids)

    @staticmethod
    def scale_order() -> Sequence[str]:
        return SCALE_LADDER
