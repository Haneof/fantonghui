# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-001 操作驾驶舱：WorldOperatorSuite 原生的多维检索算子位（工单 #6 第 2 件）。

MultidimensionalSearchOperator 是 search_mind 的窄出口：
  - 每次调用输出结构化命中 + Token 封套（≤150，硬顶）；
  - envelope 报表驱动方才可见：本算子不以任何形式把超限内容偷运出去。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from ..query.search_m5 import (
    PAGE_TOKEN_BUDGET,
    MindSearchPage,
    MultidimensionalSearchEngine,
)
from ..services.manifest_data_plane import estimate_tokens


@dataclass(slots=True, frozen=True)
class SearchOperationEnvelope:
    """一次多维检索操作的结构化回执：命中页 + 封套决算。"""

    page: MindSearchPage
    tokens_used: int
    token_budget: int
    within_envelope: bool


class MultidimensionalSearchOperator:
    def __init__(self, engine: MultidimensionalSearchEngine) -> None:
        self._engine = engine

    def execute(
        self,
        *,
        keywords: Iterable[str] = (),
        dimension: str | None = None,
        entity_id: str | None = None,
        object_types: Iterable[str] = (),
        time_range: tuple[datetime, datetime] | None = None,
        limit: int = 20,
    ) -> SearchOperationEnvelope:
        page = self._engine.search_mind(
            keywords=keywords, dimension=dimension, entity_id=entity_id,
            object_types=object_types, time_range=time_range, limit=limit,
            token_budget=PAGE_TOKEN_BUDGET,
        )
        return SearchOperationEnvelope(
            page=page,
            tokens_used=page.token_estimate,
            token_budget=PAGE_TOKEN_BUDGET,
            within_envelope=page.token_estimate <= PAGE_TOKEN_BUDGET,
        )


class WorldOperatorSuite:
    """C08 驾驶舱算子族（v0 只挂检索算子；后续算子沿本形态追加）。"""

    def __init__(self, engine: MultidimensionalSearchEngine) -> None:
        self.search = MultidimensionalSearchOperator(engine)

    def describe(self) -> dict[str, Any]:
        return {
            "operators": ["search"],
            "search_token_budget": PAGE_TOKEN_BUDGET,
            "token_estimator": "tok-est-v0",
            "estimator_probe": estimate_tokens("驾驶舱自检"),
        }


__all__ = [
    "MultidimensionalSearchOperator",
    "SearchOperationEnvelope",
    "WorldOperatorSuite",
]
