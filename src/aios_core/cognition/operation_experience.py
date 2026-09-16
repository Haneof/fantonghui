"""M5-SEARCH 黄金优选检索经验持久化（OperationExperienceDistiller）。

宪法依据：V3 §67（第一次查感情史通读十年、第二次关键词、第三次人物
关系→事件→关键词→区间效果最好——形成优选路径）、§68（认知操作经验
类型）、§15-12（AI 必须能够总结怎样更有效地使用自己的世界）。

机制：对同一 problem_type 的检索战役（campaign）逐次记录三路径对比；
从第 2 次起可蒸馏，从第 3 次起收敛固化——把胜出路径固化为黄金经验
（golden experience），此后同类型查问直接按经验执行：战役级 Token 从
暴力扫描的 15,000~50,000 压缩至 ≤500，单次命中简报 ≤150（由检索总线
物理保证），准确率必须 100%（蒸馏条件）。

经验是**可过期的一等对象**：注入反例（某次按经验执行准确率 <100%）
会使经验降级回观察期，绝不把一次成功升级为永久规则（§15 与工作台
规格 §12 纪律）。
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

from aios_core.query.search import (
    MultidimensionalSearchEngine,
    PathwayComparison,
    SearchPathway,
    SearchQuery,
    SearchResult,
)

__all__ = [
    "CampaignTokenBudget",
    "DistilledExperience",
    "ExperienceDemotedError",
    "OperationExperienceDistiller",
    "DistillerNotReadyError",
    "CAMPAIGN_TOKEN_BUDGET",
    "DISTILL_MIN_CAMPAIGNS",
]

#: 蒸馏后同题战役的 Token 硬预算（工单：≤500）。
CAMPAIGN_TOKEN_BUDGET = 500
#: 蒸馏所需最少战役样本（3 次对比后固化，避免单次偶然）。
DISTILL_MIN_CAMPAIGNS = 3


class DistillerNotReadyError(Exception):
    """战役样本不足，禁止提前固化黄金经验。"""


class ExperienceDemotedError(Exception):
    """黄金经验因反例被降级（调用方应回退到对比执行）。"""


class DistilledExperience(BaseModel):
    """固化的黄金检索经验（一等持久对象）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experience_id: StrictStr = Field(min_length=1)
    problem_type: StrictStr = Field(min_length=1)
    golden_pathway: SearchPathway
    expected_accuracy: StrictFloat = Field(ge=0.0, le=1.0)
    expected_tokens: StrictInt = Field(ge=1)
    sample_campaigns: StrictInt = Field(ge=1)
    distilled_at: datetime
    status: Literal["golden", "demoted"] = "golden"
    demote_reason: str = ""

    @property
    def is_golden(self) -> bool:
        return self.status == "golden"


class OperationExperienceDistiller:
    """检索经验蒸馏器：对比 → 收敛 → 固化 → 复用 → 反例降级。"""

    def __init__(
        self,
        engine: MultidimensionalSearchEngine,
        *,
        experience_sink: Any | None = None,
    ) -> None:
        self._engine = engine
        self._sink = experience_sink          # 持久化槽（如 json 文件句柄回调）
        self._lock = threading.RLock()
        self._campaigns: dict[str, list[PathwayComparison]] = {}
        self._experiences: dict[str, DistilledExperience] = {}
        self._seq = 0

    # ------------------------------------------------------------------
    # 战役执行
    # ------------------------------------------------------------------

    def run_campaign(
        self,
        query: SearchQuery,
        *,
        expected_hit_ids: Sequence[str],
        at: datetime,
    ) -> PathwayComparison:
        """执行一次三路径对比战役并记账（观测，不预设结论）。"""
        comparison = self._engine.compare_pathways(
            query, expected_hit_ids=expected_hit_ids
        )
        with self._lock:
            self._campaigns.setdefault(query.problem_type, []).append(comparison)
        return comparison

    def run_by_experience(
        self,
        query: SearchQuery,
        *,
        expected_hit_ids: Sequence[str],
        at: datetime,
    ) -> SearchResult:
        """按已固化黄金经验直接执行（零对比、最小 Token）。"""
        experience = self.experience_for(query.problem_type)
        if experience is None or not experience.is_golden:
            raise ExperienceDemotedError(
                f"no golden experience for {query.problem_type}"
            )
        result = self._engine.run_pathway(query, experience.golden_pathway)
        expected = set(expected_hit_ids)
        found = set(result.hit_ids)
        tp = len(found & expected)
        precision = tp / len(found) if found else 0.0
        recall = tp / len(expected) if expected else 1.0
        if expected and (precision < 1.0 or recall < 1.0):
            self.demote(
                query.problem_type,
                reason=(
                    f"counterexample: precision={precision:.2f} "
                    f"recall={recall:.2f} at {at.isoformat()}"
                ),
            )
            raise ExperienceDemotedError(
                f"golden experience failed (precision={precision:.2f}, "
                f"recall={recall:.2f}); demoted"
            )
        return result

    # ------------------------------------------------------------------
    # 蒸馏与固化
    # ------------------------------------------------------------------

    def distill(self, problem_type: str, *, at: datetime) -> DistilledExperience:
        """把该问题类型的胜出路径固化为黄金经验。

        条件：≥3 次战役；被固化路径在全部战役中准确率 == 100%；
        战役成本经多次确认（取中位数）。
        """
        with self._lock:
            campaigns = self._campaigns.get(problem_type, [])
            if len(campaigns) < DISTILL_MIN_CAMPAIGNS:
                raise DistillerNotReadyError(
                    f"{problem_type}: only {len(campaigns)} campaign(s), "
                    f"need >= {DISTILL_MIN_CAMPAIGNS}"
                )
            tally: dict[SearchPathway, list[float]] = {}
            tokens: dict[SearchPathway, list[int]] = {}
            for comparison in campaigns:
                for stat in comparison.stats:
                    tally.setdefault(stat.pathway, []).append(stat.accuracy)
                    tokens.setdefault(stat.pathway, []).append(stat.tokens_spent)
            qualified: list[tuple[SearchPathway, float, int]] = []
            for pathway, accuracies in tally.items():
                if min(accuracies) >= 1.0:  # 全部战役 100% 准确
                    costs = sorted(tokens[pathway])
                    median_cost = costs[len(costs) // 2]
                    qualified.append((pathway, 1.0, median_cost))
            if not qualified:
                raise DistillerNotReadyError(
                    f"{problem_type}: no pathway sustained 100% accuracy"
                )
            # 胜出：成本最低者（准确率并列 100%）；平手按 C>B>A 优先
            priority = (
                SearchPathway.TOPOLOGICAL_DRILL,
                SearchPathway.NAIVE_KEYWORD,
                SearchPathway.BRUTE_SCAN,
            )
            golden_pathway, accuracy, median_cost = min(
                qualified,
                key=lambda item: (item[2], priority.index(item[0])),
            )
            self._seq += 1
            experience = DistilledExperience(
                experience_id=f"exp_{problem_type}_{self._seq:03d}",
                problem_type=problem_type,
                golden_pathway=golden_pathway,
                expected_accuracy=accuracy,
                expected_tokens=median_cost,
                sample_campaigns=len(campaigns),
                distilled_at=at,
            )
            self._experiences[problem_type] = experience
        self._persist(experience)
        return experience

    def demote(self, problem_type: str, *, reason: str) -> DistilledExperience | None:
        """反例降级：黄金经验回观察期（数据仍在，语义状态改变）。"""
        with self._lock:
            experience = self._experiences.get(problem_type)
            if experience is None:
                return None
            demoted = experience.model_copy(
                update={"status": "demoted", "demote_reason": reason}
            )
            self._experiences[problem_type] = demoted
        self._persist(demoted)
        return demoted

    # ------------------------------------------------------------------
    # 查询与持久化
    # ------------------------------------------------------------------

    def experience_for(self, problem_type: str) -> DistilledExperience | None:
        with self._lock:
            return self._experiences.get(problem_type)

    def all_experiences(self) -> tuple[DistilledExperience, ...]:
        with self._lock:
            return tuple(self._experiences.values())

    def campaign_count(self, problem_type: str) -> int:
        with self._lock:
            return len(self._campaigns.get(problem_type, []))

    def _persist(self, experience: DistilledExperience) -> None:
        if self._sink is not None:
            self._sink(experience.model_dump(mode="json"))
