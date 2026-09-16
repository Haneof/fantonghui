# -*- 老谱系对照跑道：M3-001R DimensionEvolutionGuard（三重硬门槛+32顶+配额+熔断），压平后 canonical 为 mainline EvolutionGuard；本件只为 M5 志愿跑道与广告契约存续，合并时另行仲裁。 -*-
"""M3-001R 动态维度衍生三重硬门限状态机（老大铁律 5 的物理臂）。

最高铁律 5：严禁 AI 无休止地自言自语、虚假自省导致维度爆炸。
端侧有限算力下，认知维度必须极度克制。本守卫的状态面极小：

  （注册即）CANDIDATE ── 30 天试用期终评 ──→ ACTIVE ── 末位淘汰 ──→ ARCHIVED
                    └── 准确率不足 ──→ EXPIRED（终态）

三重门限（任一不过即物理拦截）：
  门限一【物理跨域持续异常】≥2 个物理域 且 持续 ≥3 天 才准注册 CANDIDATE；
  门限二【30 天试用期与预测检验】30 期记录齐全后准确率 ≥70% 晋升 ACTIVE，
        否则 EXPIRED；
  门限三【每日反思配额】每自然日新维度自省评估配额=1，超额抛
        QuotaExceededBlockError。

全局硬顶：ACTIVE ≤ 32 永远成立（不变量断言，不是告警）。第 33 个准入
强制按 (activity_score, contribution, dimension_id) 字典序淘汰末位为
ARCHIVED——确定性键序保证可复放。

自问自答熔断：`enter_reflection(depth)` 在 depth≥2 时抛
RecursionFuseError——第 2 层递归即物理切断，反思套娃没有第 3 帧。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

ACTIVE_CAP = 32
MIN_ANOMALY_DOMAINS = 2
MIN_ANOMALY_SECONDS = 3 * 86_400      # 持续 ≥3 整天
PROBATION_REPORTS_REQUIRED = 30       # 30 天试用期 = 30 期记录
MIN_PREDICTION_ACCURACY = 0.70
DAILY_REFLECTION_QUOTA = 1
RECURSION_FUSE_DEPTH = 2              # 第 2 层递归物理切断


class DimensionState(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"     # 终态
    ARCHIVED = "ARCHIVED"   # 终态


class GateRejectionError(RuntimeError):
    """门限拦截总家：物理域不足 / 持续不足 / 生命周期非法 / 报告不齐。"""


class QuotaExceededBlockError(GateRejectionError):
    """每日反思配额超额（配额=1/自然日，无例外）。"""


class RecursionFuseError(RuntimeError):
    """自问自答熔断：第 2 层递归物理切断。"""


@dataclass(slots=True)
class _Candidate:
    dimension_id: str
    anomaly_domains: frozenset[str]
    anomaly_duration_seconds: float
    reports: list[tuple[int, int]] = field(default_factory=list)  # (made, correct)


@dataclass(slots=True)
class _Active:
    dimension_id: str
    activity_score: float = 0.0
    contribution: float = 0.0


class DimensionEvolutionGuard:
    """三重硬门限 + 32 硬顶 + 递归熔断的确定性守卫（sim 期驻内存）。"""

    def __init__(self) -> None:
        self._candidates: dict[str, _Candidate] = {}
        self._active: dict[str, _Active] = {}
        self._archived: dict[str, str] = {}     # id -> 淘汰原因
        self._expired: dict[str, str] = {}      # id -> 失效原因
        self._reflection_quota: dict[str, int] = {}
        self._current_reflection_depth = 0

    # ------------------------- 门限一：候选准入 -------------------------

    def submit_candidate(
        self,
        dimension_id: str,
        *,
        anomaly_domains: set[str] | frozenset[str],
        anomaly_duration_seconds: float,
    ) -> None:
        domains = frozenset(anomaly_domains)
        if len(domains) < MIN_ANOMALY_DOMAINS:
            raise GateRejectionError(
                f"{dimension_id}: 物理跨域不足（{len(domains)}<{MIN_ANOMALY_DOMAINS}），"
                "单域异常不构成新维度候选"
            )
        if anomaly_duration_seconds < MIN_ANOMALY_SECONDS:
            raise GateRejectionError(
                f"{dimension_id}: 异常持续 {anomaly_duration_seconds / 86400:.2f} 天 "
                f"< {MIN_ANOMALY_SECONDS / 86400:.0f} 天，短期波动不衍生维度"
            )
        if dimension_id in self._candidates or dimension_id in self._active:
            raise GateRejectionError(f"{dimension_id}: 重复注册")
        if dimension_id in self._archived or dimension_id in self._expired:
            raise GateRejectionError(f"{dimension_id}: 终态维度禁复活")
        self._candidates[dimension_id] = _Candidate(
            dimension_id=dimension_id,
            anomaly_domains=domains,
            anomaly_duration_seconds=float(anomaly_duration_seconds),
        )

    # ------------------------- 门限三：每日反思配额 ----------------------

    def consume_reflection_quota(self, day_key: str) -> None:
        used = self._reflection_quota.get(day_key, 0)
        if used >= DAILY_REFLECTION_QUOTA:
            raise QuotaExceededBlockError(
                f"{day_key}: 每日反思配额严格为 {DAILY_REFLECTION_QUOTA} 次，已用尽"
            )
        self._reflection_quota[day_key] = used + 1

    def quota_left(self, day_key: str) -> int:
        return DAILY_REFLECTION_QUOTA - self._reflection_quota.get(day_key, 0)

    # ------------------------- 门限二：30 天试用期 -----------------------

    def record_probation_report(
        self, dimension_id: str, *, predictions_made: int, predictions_correct: int
    ) -> None:
        cand = self._candidates.get(dimension_id)
        if cand is None:
            raise GateRejectionError(f"{dimension_id}: 非在册候选")
        if len(cand.reports) >= PROBATION_REPORTS_REQUIRED:
            raise GateRejectionError(f"{dimension_id}: 试用期已满，待终评")
        if predictions_made < 0 or predictions_correct < 0 or predictions_correct > predictions_made:
            raise GateRejectionError(
                f"{dimension_id}: 预测记录不自洽（correct={predictions_correct} > made={predictions_made}？）"
            )
        cand.reports.append((predictions_made, predictions_correct))

    def finalize_probation(self, dimension_id: str) -> DimensionState:
        cand = self._candidates.get(dimension_id)
        if cand is None:
            raise GateRejectionError(f"{dimension_id}: 非在册候选")
        if len(cand.reports) < PROBATION_REPORTS_REQUIRED:
            raise GateRejectionError(
                f"{dimension_id}: 试用期记录 {len(cand.reports)}/{PROBATION_REPORTS_REQUIRED}，"
                "不足 30 期不得终评（防提前晋升）"
            )
        made = sum(m for m, _ in cand.reports)
        correct = sum(c for _, c in cand.reports)
        accuracy = (correct / made) if made > 0 else 0.0
        del self._candidates[dimension_id]
        if made > 0 and accuracy >= MIN_PREDICTION_ACCURACY:
            self._activate(dimension_id)
            return DimensionState.ACTIVE
        self._expired[dimension_id] = (
            f"试用期准确率 {accuracy:.1%} < {MIN_PREDICTION_ACCURACY:.0%}"
            if made > 0 else "试用期零预测：无认知解释力证据"
        )
        return DimensionState.EXPIRED

    # ------------------------- 硬顶与末位淘汰 ----------------------------

    def _activate(self, dimension_id: str) -> None:
        if len(self._active) >= ACTIVE_CAP:
            victim = min(
                self._active.values(),
                key=lambda a: (a.activity_score, a.contribution, a.dimension_id),
            )
            del self._active[victim.dimension_id]
            self._archived[victim.dimension_id] = (
                f"末位淘汰：activity={victim.activity_score}, "
                f"contribution={victim.contribution}（新维度 {dimension_id} 准入）"
            )
        self._active[dimension_id] = _Active(dimension_id=dimension_id)
        assert len(self._active) <= ACTIVE_CAP, "ACTIVE 硬顶不变量破裂"

    def register_activity(self, dimension_id: str, *, activity_score: float, contribution: float) -> None:
        slot = self._active.get(dimension_id)
        if slot is None:
            raise GateRejectionError(f"{dimension_id}: 非活跃维度")
        slot.activity_score = float(activity_score)
        slot.contribution = float(contribution)

    # ------------------------- 递归熔断 ---------------------------------

    def enter_reflection(self, depth: int) -> None:
        """反思套娃熔断：depth 从 0 计，depth>=2 即第 2 层递归——物理切断。"""
        if depth >= RECURSION_FUSE_DEPTH:
            raise RecursionFuseError(
                f"反思递归深度 {depth} ≥ {RECURSION_FUSE_DEPTH}：物理切断，"
                "AI 不得就反思再反思（自问自答死循环）"
            )

    # ------------------------- 观测面 -----------------------------------

    @property
    def active_count(self) -> int:
        return len(self._active)

    def state_of(self, dimension_id: str) -> DimensionState:
        if dimension_id in self._active:
            return DimensionState.ACTIVE
        if dimension_id in self._candidates:
            return DimensionState.CANDIDATE
        if dimension_id in self._archived:
            return DimensionState.ARCHIVED
        if dimension_id in self._expired:
            return DimensionState.EXPIRED
        raise KeyError(dimension_id)

    def archive_reason(self, dimension_id: str) -> str:
        return self._archived[dimension_id]

    def expired_reason(self, dimension_id: str) -> str:
        return self._expired[dimension_id]

    def candidate_report_count(self, dimension_id: str) -> int:
        return len(self._candidates[dimension_id].reports)


__all__ = [
    "ACTIVE_CAP",
    "DAILY_REFLECTION_QUOTA",
    "DimensionEvolutionGuard",
    "DimensionState",
    "GateRejectionError",
    "MIN_ANOMALY_DOMAINS",
    "MIN_ANOMALY_SECONDS",
    "MIN_PREDICTION_ACCURACY",
    "PROBATION_REPORTS_REQUIRED",
    "QuotaExceededBlockError",
    "RECURSION_FUSE_DEPTH",
    "RecursionFuseError",
]
