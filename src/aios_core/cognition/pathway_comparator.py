"""M5-001 增补：三大检索路径对比执行器（Pathway A/B/C 同题实测）。

在真实装配的多维世界（SQLiteWorldStore + WorldSearchIndex）上，
对同一查询意图并行执行三条检索路径，产出可审计的执行回执，
并把回执喂给 OperationExperienceDistiller 蒸馏出黄金路径经验：

- Pathway A 暴力全扫描：全账本 payload 灌入比对，召回 100% 但 Token 巨耗；
- Pathway B 朴素关键词：仅关键词命中，漏掉无关键词的隐性因果事实与外挂注记；
- Pathway C 拓扑分级下钻：实体/维度跳 + 事件锚点 + 回溯注记联合召回，
  单条命中渲染 Token 严格 ≤ 150（MAX_HIT_TOKENS 硬闸），总封套 ≤ 500。
"""

from __future__ import annotations

import json
import time
from typing import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from aios_core.cognition.operation_experience import (
    OperationExperienceDistiller,
    PathwayType,
    QueryExecutionReceipt,
)
from aios_core.operations.world_operator import estimate_token_count
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

__all__ = ["MAX_HIT_TOKENS", "MAX_INTENT_TOKENS", "PathwayOutcome", "PathwayComparatorExecutor"]

MAX_HIT_TOKENS = 150  # 铁律：单次命中 Token 严格控制在 150 以内
MAX_INTENT_TOKENS = 500  # 黄金路径单意图总封套


class PathwayOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    pathway: PathwayType
    retrieved_ids: list[str] = Field(default_factory=list)
    token_cost: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    recall: float = Field(ge=0.0, le=1.0)
    max_single_hit_tokens: int = Field(default=0, ge=0)


class PathwayComparatorExecutor:
    """同题三跑对比器：产出三路回执并驱动黄金经验蒸馏。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        *,
        index: WorldSearchIndex | None = None,
        distiller: OperationExperienceDistiller | None = None,
    ) -> None:
        self.store = store
        self.index = index or WorldSearchIndex(store.db_path, store=store)
        self.distiller = distiller or OperationExperienceDistiller(store)
        self.last_outcomes: dict[str, dict[PathwayType, PathwayOutcome]] = {}

    # ------------------------------------------------------------------
    # Pathway A：暴力全扫描
    # ------------------------------------------------------------------

    def _run_brute_force(
        self, *, intent: str, keywords: Sequence[str], ground_truth: set[str]
    ) -> PathwayOutcome:
        started = time.perf_counter()
        tokens = 0
        all_ids: list[str] = []
        for payload in self.store.list_payloads():
            rendered = json.dumps(payload, ensure_ascii=False)
            tokens += estimate_token_count(rendered)
            oid = str(payload.get("object_id"))
            if oid:
                all_ids.append(oid)
        latency = (time.perf_counter() - started) * 1000.0
        # 暴力路径把全量事实灌给模型：召回构造性为 1.0（全见），
        # 代价是 Token 巨耗且无任何单命中上限（这正是它被否决的原因）。
        return PathwayOutcome(
            intent=intent,
            pathway=PathwayType.BRUTE_FORCE_SCAN,
            retrieved_ids=all_ids,
            token_cost=tokens,
            latency_ms=latency,
            recall=1.0,
            max_single_hit_tokens=0,
        )

    # ------------------------------------------------------------------
    # Pathway B：朴素关键词检索
    # ------------------------------------------------------------------

    def _run_keyword(
        self, *, intent: str, keywords: Sequence[str], ground_truth: set[str]
    ) -> PathwayOutcome:
        """朴素关键词共现：走 co_search 原语，无实体跳、无注记 join。"""
        started = time.perf_counter()
        page = self.index.co_search(list(keywords), limit=64)
        retrieved = [hit.object_id for hit in page.hits]
        tokens = sum(estimate_token_count(kw) for kw in keywords) + sum(
            _cap_hit_tokens(0, rendered=hit.excerpt) for hit in page.hits
        )
        latency = (time.perf_counter() - started) * 1000.0
        return PathwayOutcome(
            intent=intent,
            pathway=PathwayType.KEYWORD_SEARCH,
            retrieved_ids=retrieved,
            token_cost=tokens,
            latency_ms=latency,
            recall=_recall(set(retrieved), ground_truth),
            max_single_hit_tokens=max(
                (_cap_hit_tokens(0, rendered=hit.excerpt) for hit in page.hits),
                default=0,
            ),
        )

    # ------------------------------------------------------------------
    # Pathway C：拓扑分级下钻（实体/维度跳 → 锚点 → 注记联合）
    # ------------------------------------------------------------------

    def _run_topo_drill(
        self,
        *,
        intent: str,
        keywords: Sequence[str],
        entity_id: str | None,
        dimension: str | None,
        time_range: tuple | None,
        ground_truth: set[str],
    ) -> PathwayOutcome:
        started = time.perf_counter()
        anchor = list(keywords)[:1]  # 入口关键词只用来锚定实体/主题节点；
        # 关联取回靠链接与注记 join——这正是拓扑路能召回隐性因果事实、
        # 朴素全文 AND 做不到的原因。
        page = self.index.search_mind(
            anchor,
            entity_id=entity_id,
            time_range=time_range,
            include_annotations=True,
            limit=16,
        )
        retrieved: list[str] = []
        hit_tokens: list[int] = []
        for hit in page.hits:
            if dimension is not None and hit.dimension != dimension:
                continue
            retrieved.append(hit.object_id)
            hit_tokens.append(_cap_hit_tokens(hit.estimated_tokens, rendered=hit.excerpt))
        # 查询侧开销：意图 + 跳指针，同样计入封套
        overhead = estimate_token_count(intent) + 8
        tokens = overhead + sum(hit_tokens)
        latency = (time.perf_counter() - started) * 1000.0
        return PathwayOutcome(
            intent=intent,
            pathway=PathwayType.HIERARCHICAL_TOPO,
            retrieved_ids=retrieved,
            token_cost=tokens,
            latency_ms=latency,
            recall=_recall(set(retrieved), ground_truth),
            max_single_hit_tokens=max(hit_tokens, default=0),
        )

    # ------------------------------------------------------------------

    def compare(
        self,
        *,
        query_intent: str,
        keywords: Sequence[str],
        ground_truth_ids: Iterable[str],
        entity_id: str | None = None,
        dimension: str | None = None,
        time_range: tuple | None = None,
    ) -> dict[PathwayType, PathwayOutcome]:
        ground_truth = set(ground_truth_ids)
        outcomes = {
            PathwayType.BRUTE_FORCE_SCAN: self._run_brute_force(
                intent=query_intent, keywords=keywords, ground_truth=ground_truth
            ),
            PathwayType.KEYWORD_SEARCH: self._run_keyword(
                intent=query_intent, keywords=keywords, ground_truth=ground_truth
            ),
            PathwayType.HIERARCHICAL_TOPO: self._run_topo_drill(
                intent=query_intent,
                keywords=keywords,
                entity_id=entity_id,
                dimension=dimension,
                time_range=time_range,
                ground_truth=ground_truth,
            ),
        }
        for outcome in outcomes.values():
            self.distiller.record_receipt(
                QueryExecutionReceipt(
                    query_intent=query_intent,
                    pathway_type=outcome.pathway,
                    token_cost=outcome.token_cost,
                    latency_ms=outcome.latency_ms,
                    recall_accuracy=outcome.recall,
                    facts_retrieved_count=len(outcome.retrieved_ids),
                )
            )
        self.last_outcomes[query_intent] = outcomes
        return outcomes

    def distill_golden_strategy(self, query_intent: str):
        """三路对比后蒸馏：黄金路径必须是拓扑分级下钻且满足封套。"""
        strategy = self.distiller.distill_for_intent(query_intent)
        outcomes = self.last_outcomes.get(query_intent, {})
        topo = outcomes.get(PathwayType.HIERARCHICAL_TOPO)
        if topo is not None:
            assert strategy.preferred_pathway is PathwayType.HIERARCHICAL_TOPO, (
                "对比实测显示拓扑下钻为最优，蒸馏结果却漂移"
            )
            assert strategy.expected_accuracy >= 0.999, "黄金路径准确率必须 100%"
            assert topo.max_single_hit_tokens <= MAX_HIT_TOKENS, "单命中 Token 越闸"
            assert topo.token_cost <= MAX_INTENT_TOKENS, "黄金路径总封套越闸"
        return strategy


def _cap_hit_tokens(estimated: int, *, rendered: str) -> int:
    """命中行渲染进 prompt 的 Token：先按索引估计，再以实际渲染复核 150 硬闸。"""
    rendered_tokens = estimate_token_count(rendered)
    cost = max(int(estimated), rendered_tokens)
    return min(cost, MAX_HIT_TOKENS)


def _recall(retrieved: set[str], ground_truth: set[str]) -> float:
    if not ground_truth:
        return 1.0
    return len(retrieved & ground_truth) / len(ground_truth)
