"""跨域时空共振合成器（CrossDomainResonanceSynthesizer）。

问题
----
单域检索能把"心率异常"或"某句原话"各自捞出来，但**事件锚点的诞生没有机制承载体**：
GPS 轨迹位移、生理突变、原话语义是三条平行的线，谁都不会自己合并成"那天发生了什么"。
人工写死剧情线不成立（宪法禁止硬编码死维度，要求多维输入横向交叉汇聚自发长成新维度）。

本工具做什么
------------
把"共振"变成**可复算的机械算子**：

1. 信号按域登记（``location`` / ``physiology`` / ``utterance`` / ``finance`` / ``environment``）；
2. 在滑动时间窗内做**跨域共现聚类**：同窗内不同域的信号组成一个共振簇；
3. 共振强度 ``score = 域覆盖数 × (1 + 关键词重合率) × 时间紧致度``；
4. 产出的候选**只携带证据指针**（谁在什么时刻贡献了什么），不复制原始事实
   （铁律：指针连接，禁止数据冗余拷贝）。

候选锚点随后交给上层（认知层）决定是否正式登记为 ``EventAnchor``、
以及它处于 CANDIDATE / ACTIVE 哪个生命周期状态 —— 算子本身不做状态判断。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

__all__ = [
    "DOMAIN_ENVIRONMENT",
    "DOMAIN_FINANCE",
    "DOMAIN_LOCATION",
    "DOMAIN_PHYSIOLOGY",
    "DOMAIN_UTTERANCE",
    "CrossDomainResonanceSynthesizer",
    "ResonanceCandidate",
    "ResonanceSignal",
    "ResonanceSynthesizerError",
]

DOMAIN_LOCATION = "location"
DOMAIN_PHYSIOLOGY = "physiology"
DOMAIN_UTTERANCE = "utterance"
DOMAIN_FINANCE = "finance"
DOMAIN_ENVIRONMENT = "environment"

#: 各域在共振评分中的基础权重（生理突变与关键原话权重最高）。
_DOMAIN_WEIGHTS: Mapping[str, float] = {
    DOMAIN_PHYSIOLOGY: 1.0,
    DOMAIN_UTTERANCE: 1.0,
    DOMAIN_FINANCE: 0.9,
    DOMAIN_LOCATION: 0.7,
    DOMAIN_ENVIRONMENT: 0.4,
}


class ResonanceSynthesizerError(ValueError):
    """共振合成协议错误。"""


def _as_utc(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResonanceSynthesizerError(f"{field_name} is not a valid ISO datetime") from exc
    else:
        raise ResonanceSynthesizerError(f"{field_name} must be datetime or ISO string")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ResonanceSignal:
    """一条只为自己域投票的证据信号（指针式，不拷贝原始事实）。"""

    signal_id: str
    domain: str
    occurred_at: datetime
    reference: str
    label: str = ""
    keywords: tuple[str, ...] = ()

    @property
    def keyword_set(self) -> frozenset[str]:
        return frozenset(keyword for keyword in self.keywords if keyword)


@dataclass(frozen=True, slots=True)
class ResonanceCandidate:
    """跨域共振候选锚点（证据指针集合，尚未登记为世界事件）。"""

    cluster_id: str
    domains: tuple[str, ...]
    signals: tuple[ResonanceSignal, ...]
    window_start: datetime
    window_end: datetime
    cross_domain_score: float
    shared_keywords: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    proposed_title: str
    proposed_interpretation: str

    @property
    def domain_count(self) -> int:
        return len(self.domains)

    @property
    def signal_count(self) -> int:
        return len(self.signals)


class CrossDomainResonanceSynthesizer:
    """跨域时空共振合成器（多维输入横向汇聚 → 事件锚点候选）。"""

    def __init__(
        self,
        *,
        window_hours: float = 48.0,
        min_domains: int = 2,
        min_score: float = 1.0,
    ) -> None:
        if window_hours <= 0:
            raise ResonanceSynthesizerError("window_hours must be positive")
        if min_domains < 2:
            raise ResonanceSynthesizerError("min_domains must be >= 2 (单域不成共振)")
        self.window_hours = float(window_hours)
        self.min_domains = int(min_domains)
        self.min_score = float(min_score)
        self._signals: list[ResonanceSignal] = []
        self._seen_ids: set[str] = set()

    # ------------------------------------------------------------------
    # 信号登记
    # ------------------------------------------------------------------

    def add_signal(
        self,
        *,
        signal_id: str,
        domain: str,
        occurred_at: Any,
        reference: str,
        label: str = "",
        keywords: Sequence[str] = (),
    ) -> ResonanceSignal:
        if not signal_id or not signal_id.strip():
            raise ResonanceSynthesizerError("signal_id must be non-empty")
        if signal_id in self._seen_ids:
            raise ResonanceSynthesizerError(f"signal {signal_id!r} already registered")
        if domain not in _DOMAIN_WEIGHTS:
            raise ResonanceSynthesizerError(f"unknown domain {domain!r}")
        signal = ResonanceSignal(
            signal_id=signal_id,
            domain=domain,
            occurred_at=_as_utc(occurred_at, "occurred_at"),
            reference=reference,
            label=label,
            keywords=tuple(keywords),
        )
        self._seen_ids.add(signal_id)
        self._signals.append(signal)
        return signal

    def add_signals(self, signals: Iterable[Mapping[str, Any]]) -> tuple[ResonanceSignal, ...]:
        registered = []
        for raw in signals:
            registered.append(
                self.add_signal(
                    signal_id=str(raw.get("signal_id", "")),
                    domain=str(raw.get("domain", "")),
                    occurred_at=raw.get("occurred_at"),
                    reference=str(raw.get("reference", "")),
                    label=str(raw.get("label", "")),
                    keywords=tuple(raw.get("keywords", ()) or ()),
                )
            )
        return tuple(registered)

    # ------------------------------------------------------------------
    # 合成
    # ------------------------------------------------------------------

    def synthesize(self, *, limit: int = 10) -> tuple[ResonanceCandidate, ...]:
        """按滑动时间窗做跨域共现聚类，产出共振候选锚点（确定性排序）。"""

        if not self._signals:
            return ()
        ordered = sorted(self._signals, key=lambda item: (item.occurred_at, item.signal_id))
        window = timedelta(hours=self.window_hours)
        assigned: set[str] = set()
        candidates: list[ResonanceCandidate] = []
        for signal in ordered:
            if signal.signal_id in assigned:
                continue
            end = signal.occurred_at + window
            members = [
                item
                for item in ordered
                if signal.occurred_at <= item.occurred_at <= end
            ]
            assigned.update(item.signal_id for item in members)
            candidate = self._build_candidate(members)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (-item.cross_domain_score, item.window_start))
        return tuple(candidates[:limit])

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _build_candidate(self, members: Sequence[ResonanceSignal]) -> ResonanceCandidate | None:
        domains = tuple(sorted({item.domain for item in members}))
        if len(domains) < self.min_domains:
            return None
        keyword_counter: Dict[str, int] = {}
        for item in members:
            for keyword in item.keyword_set:
                keyword_counter[keyword] = keyword_counter.get(keyword, 0) + 1
        shared = tuple(
            sorted(
                keyword for keyword, count in keyword_counter.items() if count >= 2
            )
        )
        overlap = (len(shared) / max(1, len(keyword_counter))) if keyword_counter else 0.0
        weight_sum = sum(_DOMAIN_WEIGHTS[item.domain] for item in members)
        span_hours = max(
            1e-6, (members[-1].occurred_at - members[0].occurred_at).total_seconds() / 3600.0
        )
        tightness = self.window_hours / (self.window_hours + span_hours)
        score = round(len(domains) * weight_sum * (1.0 + overlap) * tightness, 4)
        if score < self.min_score:
            return None
        refs = tuple(item.reference for item in members)
        title = "跨域共振事件候选"
        if shared:
            title = f"跨域共振事件候选（{','.join(shared[:3])}）"
        interpretation = (
            f"{len(domains)} 个域（{'/'.join(domains)}）在 {span_hours:.1f} 小时内共振；"
            f"共享线索：{'、'.join(shared) if shared else '无'}；"
            f"证据指针 {len(refs)} 条：{'; '.join(item.label or item.signal_id for item in members)}。"
        )
        return ResonanceCandidate(
            cluster_id=f"resonance:{members[0].occurred_at.date().isoformat()}:{len(domains)}",
            domains=domains,
            signals=tuple(members),
            window_start=members[0].occurred_at,
            window_end=members[-1].occurred_at,
            cross_domain_score=score,
            shared_keywords=shared,
            evidence_refs=refs,
            proposed_title=title,
            proposed_interpretation=interpretation,
        )

    @property
    def signal_count(self) -> int:
        return len(self._signals)

    def domains_present(self) -> tuple[str, ...]:
        return tuple(sorted({item.domain for item in self._signals}))
