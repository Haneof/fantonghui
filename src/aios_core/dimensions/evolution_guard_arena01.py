"""M3-001R 动态维度衍生三重硬门限状态机（坚决捍卫宪法铁律 5）。

宪法铁律 5：严禁 AI 无休止地自言自语、虚假自省导致系统维度爆炸。
在端侧有限算力下，认知维度的衍生必须极度克制、可审计、可淘汰。

四大硬门禁的工程落点：

1. **三重门限准入状态机**：
   - 门限一（物理跨域持续异常）：异常信号必须跨越 **≥2 个物理域**
     （如睡眠异常 + 血压异常），且最早/最晚信号跨度 **≥3 天**、且异常日
     覆盖 **≥3 个自然日**，才允许提交新维度候选（``CANDIDATE``）；
   - 门限二（30 天试用期与预测检验）：候选维度必须在 30 天内提供连续
     解释力——预测样本 **准确率 ≥ 70%** 且 **覆盖率 ≥ 80%**（每天是否
     都有预测），达标晋升 ``ACTIVE``，逾期不达标自动 ``EXPIRED``；
   - 门限三（每日自省配额）：新维度自省评估每自然日 **严格 1 次**，
     超额直接抛出 ``QuotaExceededBlockError``；
2. **活跃维度全局硬顶 ≤32**：超限引入时，按「活跃度 × 贡献度」得分淘汰
   末位维度并归档（``ARCHIVED``），同分时按维度 slug 字典序决出——
   淘汰永远确定、可复算；
3. **自问自答死循环熔断**：注入恶意 Prompt 诱导反思套娃时，
   ``reflect`` 的因果链深度达到 **第 2 层自指递归**（即反思之反思之反思）
   即被物理切断，抛出 ``ReflectionLoopCutError`` 并将熔断器置为开路——
   开路状态下一切自省拒绝，必须显式人工复位。

时间基准全部按「自然日序号」注入（``day``），测试确定性推进 30 天。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "DimensionEvolutionState",
    "AnomalyObservation",
    "AdmissionVerdict",
    "TrialVerdict",
    "QuotaExceededBlockError",
    "ReflectionLoopCutError",
    "EvolutionGuard",
]

#: 门限常量（云端工单冻结值）
MIN_PHYSICAL_DOMAINS = 2
MIN_ANOMALY_SPAN_DAYS = 3
MIN_ANOMALY_DAYS_COVERED = 3
TRIAL_DAYS = 30
MIN_PREDICTION_ACCURACY = 0.70
MIN_TRIAL_COVERAGE = 0.80
DAILY_REFLECTION_QUOTA = 1
MAX_ACTIVE_DIMENSIONS = 32
MAX_SELF_REFLECTION_DEPTH = 1  # 允许的嵌套自指深度；第 2 层递归即物理切断


class QuotaExceededBlockError(Exception):
    """每日自省配额超限硬阻断（门限三，超导即抛）。"""


class ReflectionLoopCutError(Exception):
    """自问自答死循环物理熔断（铁律 5 反套娃电闸）。"""


class DimensionEvolutionState(StrEnum):
    """维度衍生命名状态机。"""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AnomalyObservation:
    """一条物理域异常信号（如：第 d 天睡眠效率 58% 且深睡 < 40 分钟）。"""

    day: int
    domain: str  # sleep / blood_pressure / heart_rate / cortisol / workshop_noise ...
    metric: str
    value: float
    abnormal: bool = True

    def __post_init__(self) -> None:
        if not self.domain.strip() or not self.metric.strip():
            raise ValueError("domain/metric must be non-empty")


@dataclass(frozen=True)
class AdmissionVerdict:
    """门限一裁决。"""

    admitted: bool
    slug: Optional[str]
    reasons: Tuple[str, ...]
    state: DimensionEvolutionState


@dataclass(frozen=True)
class TrialVerdict:
    """门限二（30 天试用期）裁决。"""

    slug: str
    elapsed_days: int
    predictions_total: int
    prediction_accuracy: Optional[float]
    coverage_ratio: float
    state: DimensionEvolutionState
    verdict: str  # promoted / expired / in_trial


@dataclass
class _CandidateProfile:
    slug: str
    enrolled_day: int
    domains: Tuple[str, ...]
    description: str
    predictions: Dict[int, bool] = field(default_factory=dict)  # day -> 当日预测是否命中


@dataclass
class _ActiveProfile:
    slug: str
    activity: float
    contribution: float
    promoted_day: int


class EvolutionGuard:
    """动态维度衍生三重硬门限守卫。"""

    def __init__(
        self,
        *,
        max_active: int = MAX_ACTIVE_DIMENSIONS,
        trial_days: int = TRIAL_DAYS,
        min_accuracy: float = MIN_PREDICTION_ACCURACY,
        min_coverage: float = MIN_TRIAL_COVERAGE,
    ) -> None:
        if max_active < 1:
            raise ValueError("max_active must be >= 1")
        if not 0.0 < min_accuracy <= 1.0:
            raise ValueError("min_accuracy must be within (0, 1]")
        self._max_active = max_active
        self._trial_days = trial_days
        self._min_accuracy = min_accuracy
        self._min_coverage = min_coverage

        self._anomalies: List[AnomalyObservation] = []
        self._candidates: Dict[str, _CandidateProfile] = {}
        self._active: Dict[str, _ActiveProfile] = {}
        self._archived: Dict[str, Tuple[_ActiveProfile, str]] = {}
        self._reflection_quota: Dict[int, int] = {}
        self._reflection_parents: Dict[str, Optional[str]] = {}
        self._reflection_seq = 0
        self._circuit_open = False
        self._stats: Dict[str, int] = {
            "anomalies_recorded": 0,
            "candidates_admitted": 0,
            "candidates_rejected": 0,
            "promoted": 0,
            "expired": 0,
            "archived": 0,
            "quota_blocks": 0,
            "loop_cuts": 0,
        }

    # ------------------------------------------------------------------
    # 门限一：物理跨域持续异常准入
    # ------------------------------------------------------------------

    def record_anomaly(self, signal: AnomalyObservation) -> None:
        self._anomalies.append(signal)
        self._stats["anomalies_recorded"] += 1

    def submit_candidate(
        self, *, slug: str, description: str, evidence: Optional[List[AnomalyObservation]] = None
    ) -> AdmissionVerdict:
        """以「全部异常信号 + 可选增量证据」申请新维度候选。"""
        if not slug.strip():
            raise ValueError("slug must be non-empty")
        if slug in self._candidates or slug in self._active:
            raise ValueError(f"dimension already exists: {slug}")
        pool = list(self._anomalies) + list(evidence or [])
        if not pool:
            return AdmissionVerdict(False, None, ("no-evidence",), DimensionEvolutionState.REJECTED)

        abnormal = [s for s in pool if s.abnormal]
        domains = {s.domain for s in abnormal}
        days = sorted({s.day for s in abnormal})
        reasons: List[str] = []
        if len(domains) < MIN_PHYSICAL_DOMAINS:
            reasons.append(f"cross-domain<2: only {sorted(domains)}")
        if len(days) < MIN_ANOMALY_DAYS_COVERED:
            reasons.append(f"days-covered<{MIN_ANOMALY_DAYS_COVERED}: only {len(days)} day(s)")
        if days and days[-1] - days[0] < MIN_ANOMALY_SPAN_DAYS:
            reasons.append(f"span<{MIN_ANOMALY_SPAN_DAYS}d: {days[-1] - days[0]} day(s)")
        if reasons:
            self._stats["candidates_rejected"] += 1
            return AdmissionVerdict(False, None, tuple(reasons), DimensionEvolutionState.REJECTED)

        self._candidates[slug] = _CandidateProfile(
            slug=slug,
            enrolled_day=days[-1],
            domains=tuple(sorted(domains)),
            description=description,
        )
        self._stats["candidates_admitted"] += 1
        return AdmissionVerdict(True, slug, (), DimensionEvolutionState.CANDIDATE)

    # ------------------------------------------------------------------
    # 门限二：30 天试用期与预测检验
    # ------------------------------------------------------------------

    def record_prediction(self, slug: str, *, day: int, correct: bool) -> None:
        profile = self._candidates[slug]
        if not isinstance(correct, bool):
            raise ValueError("correct must be bool")
        if day in profile.predictions:
            raise ValueError(f"duplicate prediction for day {day}")
        if day < profile.enrolled_day:
            raise ValueError("prediction cannot predate enrollment")
        profile.predictions[day] = correct

    def evaluate_trial(self, slug: str, *, as_of_day: int) -> TrialVerdict:
        """30 天试用裁决：准确率/覆盖率达标晋升 ACTIVE，否则自动 EXPIRED。"""
        profile = self._candidates[slug]
        elapsed = as_of_day - profile.enrolled_day
        total = len(profile.predictions)
        hits = sum(1 for ok in profile.predictions.values() if ok)
        accuracy = hits / total if total else None
        coverage = total / self._trial_days

        if elapsed < self._trial_days:
            return TrialVerdict(slug, elapsed, total, accuracy, coverage,
                                DimensionEvolutionState.CANDIDATE, "in_trial")

        passed = (
            accuracy is not None
            and accuracy >= self._min_accuracy
            and coverage >= self._min_coverage
        )
        if passed:
            del self._candidates[slug]
            self._admit_active(slug, activity=1.0, contribution=1.0, promoted_day=as_of_day)
            self._stats["promoted"] += 1
            return TrialVerdict(slug, elapsed, total, accuracy, coverage,
                                DimensionEvolutionState.ACTIVE, "promoted")
        del self._candidates[slug]
        self._stats["expired"] += 1
        return TrialVerdict(slug, elapsed, total, accuracy, coverage,
                            DimensionEvolutionState.EXPIRED, "expired")

    # ------------------------------------------------------------------
    # 门禁 2：活跃维度全局硬顶 ≤32，末位淘汰归档
    # ------------------------------------------------------------------

    def _eviction_score(self, profile: _ActiveProfile) -> Tuple[float, str]:
        """淘汰分：活跃度 60% + 贡献度 40%；同分按 slug 字典序（最小者优先淘汰）。"""
        return (round(profile.activity * 0.6 + profile.contribution * 0.4, 9), profile.slug)

    def _admit_active(self, slug: str, *, activity: float, contribution: float, promoted_day: int) -> Optional[str]:
        evicted: Optional[str] = None
        if len(self._active) >= self._max_active:
            victim_slug, victim = min(self._active.items(), key=lambda kv: self._eviction_score(kv[1]))
            del self._active[victim_slug]
            self._archived[victim_slug] = (victim, f"evicted-by:{slug}")
            self._stats["archived"] += 1
            evicted = victim_slug
        self._active[slug] = _ActiveProfile(
            slug=slug, activity=activity, contribution=contribution, promoted_day=promoted_day
        )
        return evicted

    def promote_strategic_dimension(
        self, slug: str, *, activity: float, contribution: float, day: int
    ) -> Optional[str]:
        """战略直晋通道（例：系统根维度）——同样受 32 硬顶约束，返回被淘汰者。"""
        if not slug.strip():
            raise ValueError("slug must be non-empty")
        if slug in self._active:
            raise ValueError(f"dimension already active: {slug}")
        if not 0.0 <= activity <= 1.0 or not 0.0 <= contribution <= 1.0:
            raise ValueError("activity/contribution must be within [0, 1]")
        return self._admit_active(slug, activity=activity, contribution=contribution, promoted_day=day)

    def sync_scores(self, slug: str, *, activity: float, contribution: float) -> None:
        profile = self._active[slug]
        if not 0.0 <= activity <= 1.0 or not 0.0 <= contribution <= 1.0:
            raise ValueError("scores must be within [0, 1]")
        profile.activity = activity
        profile.contribution = contribution

    # ------------------------------------------------------------------
    # 门限三 + 门禁 3：每日自省配额 与 自问自答死循环熔断
    # ------------------------------------------------------------------

    def reflect(
        self, *, day: int, content: str, parent_reflection_id: Optional[str] = None
    ) -> str:
        """一次新维度自省评估。返回 reflection_id。

        - 每自然日全局配额严格 1 次，超额抛 ``QuotaExceededBlockError``；
        - 因果链（自指）深度达到第 2 层递归即物理切断，抛
          ``ReflectionLoopCutError`` 并使熔断器开路；
        - 熔断器开路后一切自省拒绝，须 ``reset_circuit()`` 人工复位。
        """
        if self._circuit_open:
            raise ReflectionLoopCutError(
                "reflection circuit is OPEN: 套娃熔断已切断，需人工复位"
            )
        if not content.strip():
            raise ValueError("content must be non-empty")

        spent = self._reflection_quota.get(day, 0)
        if spent >= DAILY_REFLECTION_QUOTA:
            self._stats["quota_blocks"] += 1
            raise QuotaExceededBlockError(
                f"daily reflection quota exceeded on day {day}: quota={DAILY_REFLECTION_QUOTA}"
            )

        depth = self._self_reference_depth(parent_reflection_id)
        if depth > MAX_SELF_REFLECTION_DEPTH:
            self._circuit_open = True
            self._stats["loop_cuts"] += 1
            raise ReflectionLoopCutError(
                f"self-reflection recursion cut at depth {depth}: 第 2 层递归物理切断"
            )

        self._reflection_quota[day] = spent + 1
        self._reflection_seq += 1
        reflection_id = f"refl-{day}-{self._reflection_seq:04d}"
        self._reflection_parents[reflection_id] = parent_reflection_id
        return reflection_id

    def _self_reference_depth(self, parent_id: Optional[str]) -> int:
        """沿因果链回溯自指深度：顶层自省为 0，反思之反思为 1，依此递归。"""
        depth = 0
        cursor = parent_id
        seen: set = set()
        while cursor is not None:
            if cursor in seen:  # 环引用直接视为死循环
                return MAX_SELF_REFLECTION_DEPTH + 1
            seen.add(cursor)
            if cursor not in self._reflection_parents:
                raise ValueError(f"unknown parent reflection: {cursor}")
            depth += 1
            cursor = self._reflection_parents[cursor]
        return depth

    def reset_circuit(self) -> None:
        """人工复位熔断器（运维开关，非自愈）。"""
        self._circuit_open = False

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def active_slugs(self) -> Tuple[str, ...]:
        return tuple(sorted(self._active))

    def archived_slugs(self) -> Tuple[str, ...]:
        return tuple(sorted(self._archived))

    def candidate_slugs(self) -> Tuple[str, ...]:
        return tuple(sorted(self._candidates))

    def state_of(self, slug: str) -> DimensionEvolutionState:
        if slug in self._active:
            return DimensionEvolutionState.ACTIVE
        if slug in self._candidates:
            return DimensionEvolutionState.CANDIDATE
        if slug in self._archived:
            return DimensionEvolutionState.ARCHIVED
        raise KeyError(slug)
