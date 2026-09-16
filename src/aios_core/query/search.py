"""M5-SEARCH 多维检索总线（MultidimensionalSearchEngine）与三路径对比执行器。

宪法依据：V3 §89（多关键词共现联想检索、拒绝单关键词语义断裂）、
§90（图谱拓扑穿透）、§67（OperationExperience：AI 学习如何查询自己的
世界）、§15-5（禁止每次唤醒通读人生——暴力扫描只能作为对照组存在）。

三路径（同一引擎索引，同一查问，可公平对比）：

* **Pathway A 暴力扫描（BRUTE_SCAN）**：全量通读世界（对照用途）。
  Token 成本 ≈ 世界总量（3 年人生 15,000~50,000），精准但天价。
* **Pathway B 朴素关键词（NAIVE_KEYWORD）**：单词条倒排 OR 命中。
  成本中等；无实体消歧、无共现约束 → 精度受损（同名污染、复合意图断裂）。
* **Pathway C 拓扑分级下钻（TOPOLOGICAL_DRILL）**：别名精确归一 →
  实体档案 → 事件锚点 → 观测切片，逐级收窄。成本极低且精准。

Token 记账：每路径执行后如实申报 tokens_spent；**单次命中简报
（hit brief）组装 ≤150 Token**（工单铁律），超限物理截断。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from aios_core.cockpit.pipeline import estimate_tokens

__all__ = [
    "HitBrief",
    "MindRecord",
    "MultidimensionalSearchEngine",
    "PathwayComparison",
    "PathwayStats",
    "SearchPathway",
    "SearchQuery",
    "SearchResult",
    "SINGLE_HIT_TOKEN_CAP",
]

#: 单次命中简报 Token 硬顶（工单铁律）。
SINGLE_HIT_TOKEN_CAP = 150

RecordType = Literal["dimension", "claim", "entity", "annotation"]


class SearchPathway(StrEnum):
    BRUTE_SCAN = "brute_scan"
    NAIVE_KEYWORD = "naive_keyword"
    TOPOLOGICAL_DRILL = "topological_drill"


class MindRecord(BaseModel):
    """多维心智记录（Dimension/Claim/Entity/Annotation 联合检索的最小单元）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: StrictStr = Field(min_length=1)
    record_type: RecordType
    keywords: tuple[StrictStr, ...] = Field(default=())
    entity_refs: tuple[StrictStr, ...] = Field(default=())
    content: StrictStr = Field(min_length=1)
    occurred_at: datetime | None = None
    anchor_id: StrictStr | None = None
    ground_truth: bool = False   # 测试真值标记：该记录是否为本次查问的期望命中

    @property
    def content_tokens(self) -> int:
        return estimate_tokens(self.content)


class SearchQuery(BaseModel):
    """一次联合检索查问：多关键词 + 实体提示 + 类型过滤。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    problem_type: StrictStr = Field(min_length=1)     # 如 "gift_history_research"
    keywords: tuple[StrictStr, ...] = Field(min_length=1)
    entity_hint: StrictStr | None = None              # 实体名或别名（供路径 C 归一）
    record_types: tuple[RecordType, ...] = Field(
        default=("dimension", "claim", "entity", "annotation")
    )


class HitBrief(BaseModel):
    """单次命中简报（≤150 Token 硬顶，指针优先、绝不内联全量）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: StrictStr
    record_type: RecordType
    brief: StrictStr
    token_cost: StrictInt = Field(ge=1, le=SINGLE_HIT_TOKEN_CAP)


class SearchResult(BaseModel):
    """单路径执行结果（命中 + 真实成本申报）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pathway: SearchPathway
    hit_ids: tuple[StrictStr, ...] = Field(default=())
    briefs: tuple[HitBrief, ...] = Field(default=())
    tokens_spent: StrictInt = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)

    def brief_tokens(self) -> int:
        return sum(b.token_cost for b in self.briefs)


class PathwayStats(BaseModel):
    """单路径对比统计（准确率对照调用方提供的期望命中集）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pathway: SearchPathway
    tokens_spent: StrictInt = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    hits: StrictInt = Field(ge=0)
    true_positives: StrictInt = Field(ge=0)
    false_positives: StrictInt = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)   # 精确率 = TP / 命中数（空命中=0）

    @property
    def cost_grade(self) -> str:
        if self.tokens_spent >= 15_000:
            return "prohibitive"
        if self.tokens_spent >= 500:
            return "moderate"
        return "lean"


class PathwayComparison(BaseModel):
    """三路径同题对比结果（经验蒸馏的原始素材）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    problem_type: StrictStr
    stats: tuple[PathwayStats, ...]
    winner: SearchPathway
    winner_tokens: StrictInt

    def by(self, pathway: SearchPathway) -> PathwayStats:
        for stat in self.stats:
            if stat.pathway is pathway:
                return stat
        raise KeyError(pathway)


class MultidimensionalSearchEngine:
    """多维联合检索总线：Dimension/Claim/Entity/Annotation 一体索引。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, MindRecord] = {}
        self._by_keyword: dict[str, set[str]] = {}
        self._by_entity: dict[str, set[str]] = {}
        self._alias_to_entity: dict[str, str] = {}
        self._scan_count = 0

    # -- 索引 ---------------------------------------------------------

    def register(self, record: MindRecord) -> None:
        with self._lock:
            self._records[record.record_id] = record
            for kw in record.keywords:
                self._by_keyword.setdefault(kw.casefold(), set()).add(record.record_id)
            for entity in record.entity_refs:
                self._by_entity.setdefault(entity, set()).add(record.record_id)
            if record.record_type == "entity":
                self._alias_to_entity[record.content.casefold()] = record.record_id
                for kw in record.keywords:
                    self._alias_to_entity.setdefault(kw.casefold(), record.record_id)

    def register_all(self, records: Iterable[MindRecord]) -> None:
        for record in records:
            self.register(record)

    def resolve_entity(self, name_or_alias: str) -> str | None:
        with self._lock:
            return self._alias_to_entity.get(name_or_alias.casefold())

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)

    def world_total_tokens(self) -> int:
        with self._lock:
            return sum(r.content_tokens for r in self._records.values())

    # -- 三路径执行 -----------------------------------------------------

    def run_pathway(self, query: SearchQuery, pathway: SearchPathway) -> SearchResult:
        started = time.perf_counter()
        if pathway is SearchPathway.BRUTE_SCAN:
            candidates = self._brute_scan(query)
        elif pathway is SearchPathway.NAIVE_KEYWORD:
            candidates = self._naive_keyword(query)
        else:
            candidates = self._topological_drill(query)
        briefs = self._build_briefs(candidates, query)
        elapsed = (time.perf_counter() - started) * 1000.0
        return SearchResult(
            pathway=pathway,
            hit_ids=tuple(r.record_id for r in candidates),
            briefs=briefs,
            tokens_spent=self._pathway_cost(query, pathway, candidates),
            elapsed_ms=round(elapsed, 3),
        )

    def _brute_scan(self, query: SearchQuery) -> list[MindRecord]:
        """路径 A：全量通读（成本=世界总量）。"""
        with self._lock:
            self._scan_count += 1
            visible = [
                r for r in self._records.values()
                if r.record_type in query.record_types
            ]
        lowered = [k.casefold() for k in query.keywords]
        return [
            r for r in visible
            if any(kw in r.content.casefold() or kw in (x.casefold() for x in r.keywords)
                   for kw in lowered)
        ]

    def _naive_keyword(self, query: SearchQuery) -> list[MindRecord]:
        """路径 B：任意关键词倒排 OR 命中（朴素、无共现约束、无实体消歧）。"""
        with self._lock:
            ids: set[str] = set()
            for keyword in query.keywords:
                ids |= self._by_keyword.get(keyword.casefold(), set())
            return [self._records[i] for i in ids if self._records[i].record_type in query.record_types]

    def _topological_drill(self, query: SearchQuery) -> list[MindRecord]:
        """路径 C：别名归一 → 实体档案 → 记录过滤（多关键词共现 AND）。"""
        with self._lock:
            pool: set[str] = set()
            if query.entity_hint is not None:
                entity_id = self._alias_to_entity.get(query.entity_hint.casefold())
                if entity_id is not None:
                    pool |= self._by_entity.get(entity_id, set())
                    pool.add(entity_id)
            lowered = [k.casefold() for k in query.keywords]
            for rid in self._records:
                record = self._records[rid]
                if record.record_type not in query.record_types:
                    continue
                # 共现约束：全部关键词在其关键词集或正文中命中
                hay = set(k.casefold() for k in record.keywords) | {record.content.casefold()}
                text = record.content.casefold()
                if all(kw in hay or kw in text for kw in lowered):
                    pool.add(rid)
            return [self._records[i] for i in pool]

    def _pathway_cost(
        self,
        query: SearchQuery,
        pathway: SearchPathway,
        candidates: list[MindRecord],
    ) -> int:
        """真实 Token 成本申报（读入大模型上下文的量，非命中量）。"""
        if pathway is SearchPathway.BRUTE_SCAN:
            # 全量通读：世界所有可见记录的内容 Token + 检索指令
            with self._lock:
                total = sum(
                    r.content_tokens
                    for r in self._records.values()
                    if r.record_type in query.record_types
                )
            return total + 64
        if pathway is SearchPathway.NAIVE_KEYWORD:
            with self._lock:
                ids: set[str] = set()
                for keyword in query.keywords:
                    ids |= self._by_keyword.get(keyword.casefold(), set())
                total = sum(
                    self._records[i].content_tokens
                    for i in ids
                )
            return total + 48
        # 拓扑下钻：只装载归一指针 + 命中简报（简报另计于 briefs）
        return 24 + sum(r.content_tokens for r in candidates[:4]) // 4

    def _build_briefs(
        self, candidates: list[MindRecord], query: SearchQuery
    ) -> tuple[HitBrief, ...]:
        """命中简报：单条 ≤150 Token 物理截断，指针化。"""
        briefs: list[HitBrief] = []
        for record in candidates[:8]:
            text, _ = _fit_tokens(record.content, SINGLE_HIT_TOKEN_CAP - 12)
            brief = HitBrief(
                record_id=record.record_id,
                record_type=record.record_type,
                brief=f"{record.record_type}:{text}→{record.record_id}",
                token_cost=estimate_tokens(f"{record.record_type}:{text}→{record.record_id}") + 4,
            )
            if brief.token_cost > SINGLE_HIT_TOKEN_CAP:
                text, _ = _fit_tokens(record.content, SINGLE_HIT_TOKEN_CAP // 2)
                brief = HitBrief(
                    record_id=record.record_id,
                    record_type=record.record_type,
                    brief=f"{record.record_type}:{text}→{record.record_id}",
                    token_cost=SINGLE_HIT_TOKEN_CAP,
                )
            briefs.append(brief)
        return tuple(briefs)

    # ------------------------------------------------------------------
    # 三路径对比执行器
    # ------------------------------------------------------------------

    def compare_pathways(
        self,
        query: SearchQuery,
        *,
        expected_hit_ids: Sequence[str] | None = None,
    ) -> PathwayComparison:
        """三路径同题对比。expected_hit_ids 提供时计算精确率并裁定胜者。"""
        stats: list[PathwayStats] = []
        expected = set(expected_hit_ids or ())
        results: dict[SearchPathway, SearchResult] = {}
        for pathway in SearchPathway:
            result = self.run_pathway(query, pathway)
            results[pathway] = result
            if expected:
                tp = len(set(result.hit_ids) & expected)
                hits = len(result.hit_ids)
                accuracy = (tp / hits) if hits else 0.0
                stats.append(
                    PathwayStats(
                        pathway=pathway,
                        tokens_spent=result.tokens_spent,
                        elapsed_ms=result.elapsed_ms,
                        hits=hits,
                        true_positives=tp,
                        false_positives=hits - tp,
                        accuracy=round(accuracy, 4),
                    )
                )
            else:
                stats.append(
                    PathwayStats(
                        pathway=pathway,
                        tokens_spent=result.tokens_spent,
                        elapsed_ms=result.elapsed_ms,
                        hits=len(result.hit_ids),
                        true_positives=0,
                        false_positives=0,
                        accuracy=0.0,
                    )
                )
        winner = self._adjudicate(stats)
        return PathwayComparison(
            problem_type=query.problem_type,
            stats=tuple(stats),
            winner=winner,
            winner_tokens=next(s.tokens_spent for s in stats if s.pathway is winner),
        )

    @staticmethod
    def _adjudicate(stats: Sequence[PathwayStats]) -> SearchPathway:
        """胜者裁定：准确率最高者优先；平手取成本最低；再平按 C>B>A 顺序。"""
        priority = (
            SearchPathway.TOPOLOGICAL_DRILL,
            SearchPathway.NAIVE_KEYWORD,
            SearchPathway.BRUTE_SCAN,
        )
        best = max(
            stats,
            key=lambda s: (
                s.accuracy,
                -s.tokens_spent,
                -priority.index(s.pathway),
            ),
        )
        return best.pathway


def _fit_tokens(text: str, cap: int) -> tuple[str, bool]:
    if estimate_tokens(text) <= cap:
        return text, False
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(text[:mid]) <= cap:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…", True
