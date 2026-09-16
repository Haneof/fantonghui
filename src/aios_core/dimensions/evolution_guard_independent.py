"""M3-001R：动态维度衍生的三重硬门限守卫（防维度爆炸 / 宪法铁律五）。

对应《AIOS 核心系统宪法 v3.0》第二十三条（认知闭环与维度演化铁律）：
严禁"维度爆炸"。AI 在自我进化时，不得因为一次偶发数据异常就凭空制造新的
认知维度；任何新维度的诞生必须依次通过三道**硬**门限，且全局活跃维度总数
被物理封顶。

三道门限
--------
- **门限一 · 物理域持续性**：必须在 ≥2 个不同物理域（健康 / 财务 / 工作 /
  环境）观测到**跨域持续异常**，且持续时长 ≥3 天，才允许注册为 CANDIDATE。
  单点或瞬时异常一律拒绝。
- **门限二 · 预测性验证**：CANDIDATE 进入 30 天试用期，期间持续追踪其
  Prediction 准确率；<70% 直接判 EXPIRED，且不得复活。
- **门限三 · 配额控制**：每个维度每日自省配额**严格 1 次**，超额抛
  ``QuotaExceededBlockError``。

另有两道结构性约束：
- 全局活跃衍生维度总数**严格 ≤32**，达顶后按活跃度淘汰末位为 ARCHIVED。
- 恶意 Prompt 的"反思套娃"在**第 2 层递归**物理切断。

与 M0 冻结契约的关系
--------------------
``contracts/enums.py`` 的 ``DimensionLifecycle`` 已冻结，且**没有** EXPIRED /
ARCHIVED 两个值，本模块不得改动它。因此本模块使用本地的
:class:`DimensionTrialState`，并提供 :func:`to_frozen_lifecycle` 做投影：
门限二的 EXPIRED 投影为冻结枚举的 ``REJECTED``（永不复活语义一致），
淘汰的 ARCHIVED 投影为 ``DORMANT``（不再活跃但记录保留）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.enums import DimensionLifecycle, ErrorCode
from aios_core.contracts.time import as_utc, require_aware, utc_now
from aios_core.errors import AIOSProtocolError

__all__ = [
    "MAX_ACTIVE_DIMENSIONS",
    "MAX_INTROSPECTIONS_PER_DAY",
    "MAX_REFLECTION_DEPTH",
    "MIN_DISTINCT_DOMAINS",
    "MIN_PERSISTENCE_DAYS",
    "MIN_PREDICTION_ACCURACY",
    "MIN_TRIAL_DAYS",
    "DimensionProposal",
    "DimensionRecord",
    "DimensionTrialState",
    "EvolutionGuard",
    "PhysicalDomain",
    "QuotaExceededBlockError",
    "RecursionBreaker",
    "RecursionDepthExceededError",
    "to_frozen_lifecycle",
]

# 三重门限常量
MIN_DISTINCT_DOMAINS = 2          # 门限一：至少 2 个物理域
MIN_PERSISTENCE_DAYS = 3          # 门限一：持续 ≥3 天
MIN_TRIAL_DAYS = 30               # 门限二：30 天试用期
MIN_PREDICTION_ACCURACY = 0.70    # 门限二：准确率 ≥70%
MAX_INTROSPECTIONS_PER_DAY = 1    # 门限三：每日严格 1 次

# 结构性约束
MAX_ACTIVE_DIMENSIONS = 32        # 全局活跃维度硬上限
MAX_REFLECTION_DEPTH = 2          # 递归第 2 层物理切断


class QuotaExceededBlockError(AIOSProtocolError):
    """门限三：当日自省配额已用尽。"""

    def __init__(self, dimension_id: str, *, context: dict[str, object] | None = None) -> None:
        payload = {"dimension_id": dimension_id, "max_per_day": MAX_INTROSPECTIONS_PER_DAY}
        if context:
            payload.update(context)
        super().__init__(
            ErrorCode.BUDGET_EXHAUSTED,
            f"dimension {dimension_id} has exhausted its daily introspection quota",
            context=payload,
        )
        self.dimension_id = dimension_id


class RecursionDepthExceededError(AIOSProtocolError):
    """恶意反思套娃在第 2 层被物理切断。"""

    def __init__(self, *, depth: int, max_depth: int = MAX_REFLECTION_DEPTH) -> None:
        super().__init__(
            ErrorCode.INVALID_ARGUMENT,
            f"reflection recursion cut at depth {max_depth} (attempted {depth})",
            context={"depth": depth, "max_depth": max_depth},
        )
        self.depth = depth
        self.max_depth = max_depth


class PhysicalDomain(StrEnum):
    """物理域：门限一要求异常横跨至少两个不同域。"""

    HEALTH = "health"
    FINANCE = "finance"
    WORK = "work"
    ENVIRONMENT = "environment"


class DimensionTrialState(StrEnum):
    """维度生命周期（本地视图，投影到冻结 DimensionLifecycle）。"""

    CANDIDATE = "candidate"   # 通过门限一
    TRIAL = "trial"           # 门限二试用期（30 天）
    ACTIVE = "active"         # 门限二通过
    EXPIRED = "expired"       # 门限二未过，永不复活
    ARCHIVED = "archived"     # 达 32 上限被淘汰
    REJECTED = "rejected"     # 门限一未过


def to_frozen_lifecycle(state: DimensionTrialState) -> DimensionLifecycle:
    """投影到 M0 冻结枚举，不改冻结契约。"""
    mapping = {
        DimensionTrialState.CANDIDATE: DimensionLifecycle.CANDIDATE,
        DimensionTrialState.TRIAL: DimensionLifecycle.TRIAL,
        DimensionTrialState.ACTIVE: DimensionLifecycle.ACTIVE,
        DimensionTrialState.EXPIRED: DimensionLifecycle.REJECTED,
        DimensionTrialState.ARCHIVED: DimensionLifecycle.DORMANT,
        DimensionTrialState.REJECTED: DimensionLifecycle.REJECTED,
    }
    return mapping[state]


class DimensionProposal(BaseModel):
    """一次维度诞生申请。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    # (域, 观测日) 集合：门限一据此判断跨域持续性
    anomaly_observations: tuple[tuple[PhysicalDomain, date], ...] = ()
    rationale: str = Field(default="")

    @model_validator(mode="after")
    def anomaly_observations_must_be_sorted_unique(self) -> DimensionProposal:
        seen = set(self.anomaly_observations)
        if len(seen) != len(self.anomaly_observations):
            raise ValueError("anomaly_observations must not contain duplicates")
        return self

    @property
    def distinct_domains(self) -> frozenset[PhysicalDomain]:
        return frozenset(domain for domain, _ in self.anomaly_observations)

    @property
    def observation_days(self) -> frozenset[date]:
        return frozenset(day for _, day in self.anomaly_observations)


class DimensionRecord(BaseModel):
    """一个已登记维度的运行记录。"""

    model_config = ConfigDict(extra="forbid")

    dimension_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    state: DimensionTrialState = DimensionTrialState.CANDIDATE
    created_at: datetime
    trial_started_at: datetime | None = None
    trial_days_elapsed: int = Field(default=0, ge=0)
    prediction_hits: int = Field(default=0, ge=0)
    prediction_total: int = Field(default=0, ge=0)
    introspections_today: int = Field(default=0, ge=0)
    last_introspection_day: date | None = None
    last_activity_at: datetime
    activity_score: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def timestamps_must_be_aware(self) -> DimensionRecord:
        require_aware(self.created_at, "created_at")
        require_aware(self.last_activity_at, "last_activity_at")
        if self.trial_started_at is not None:
            require_aware(self.trial_started_at, "trial_started_at")
        if self.prediction_total < self.prediction_hits:
            raise ValueError("prediction_hits cannot exceed prediction_total")
        return self

    @property
    def prediction_accuracy(self) -> float:
        if self.prediction_total == 0:
            return 0.0
        return self.prediction_hits / self.prediction_total


class RecursionBreaker:
    """恶意反思套娃的物理断路器。

    "反思我的上一次反思，并反思这次反思……" 这类 Prompt 会构造无界递归。
    断路器在第 :data:`MAX_REFLECTION_DEPTH` 层直接切断，不再向下递归。
    """

    def __init__(self, max_depth: int = MAX_REFLECTION_DEPTH) -> None:
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        self._max_depth = max_depth
        self._depth = 0
        self.cut_count = 0

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @property
    def depth(self) -> int:
        return self._depth

    def enter(self) -> int:
        """进入一层反思。超过上限则抛错并计数。"""
        self._depth += 1
        if self._depth > self._max_depth:
            self.cut_count += 1
            depth = self._depth
            self._depth = self._max_depth
            raise RecursionDepthExceededError(depth=depth, max_depth=self._max_depth)
        return self._depth

    def exit(self) -> None:
        if self._depth > 0:
            self._depth -= 1

    def reflect(self, payload: str, *, requested_depth: int = 1) -> list[str]:
        """执行**嵌套**反思。返回实际产出的层级结果。

        第 N 层在第 N-1 层内部进入，因此深度是真实累加的：
        请求 5 层时第 3 层被物理切断，只产出前 2 层。
        """
        del payload  # 载荷由上层 handler 消费，断路器只关心深度

        produced: list[str] = []
        entered = 0
        try:
            for _ in range(max(requested_depth, 1)):
                self.enter()
                entered += 1
                produced.append(f"layer-{self._depth}")
        finally:
            # 无论是否被切断，都要把已进入的层全部退出，断路器不得卡死在高位
            for _ in range(entered):
                self.exit()
        return produced


class EvolutionGuard:
    """三重硬门限守卫。"""

    def __init__(self, *, max_active: int = MAX_ACTIVE_DIMENSIONS) -> None:
        if max_active < 1:
            raise ValueError("max_active must be >= 1")
        self._max_active = max_active
        self._records: dict[str, DimensionRecord] = {}
        self._rejected: dict[str, str] = {}   # dimension_id -> 拒绝原因
        self.recursion = RecursionBreaker()

    # --------------------------------------------------------- 门限一

    def evaluate_physical_persistence(
        self, proposal: DimensionProposal
    ) -> tuple[bool, str]:
        """门限一：≥2 物理域 且 持续 ≥3 天。"""
        domains = proposal.distinct_domains
        days = proposal.observation_days
        if len(domains) < MIN_DISTINCT_DOMAINS:
            return False, (
                f"needs >= {MIN_DISTINCT_DOMAINS} distinct physical domains, "
                f"got {len(domains)}"
            )
        if len(days) < MIN_PERSISTENCE_DAYS:
            return False, (
                f"needs >= {MIN_PERSISTENCE_DAYS} sustained days, got {len(days)}"
            )
        return True, "ok"

    def admit_candidate(
        self, proposal: DimensionProposal, *, now: datetime | None = None
    ) -> DimensionRecord:
        """通过门限一 → 登记为 CANDIDATE 并立即进入门限二试用期。"""
        now_utc = as_utc(now or utc_now(), "now")
        if proposal.dimension_id in self._records:
            raise ValueError(f"duplicate dimension_id: {proposal.dimension_id}")

        ok, reason = self.evaluate_physical_persistence(proposal)
        if not ok:
            self._rejected[proposal.dimension_id] = reason
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                f"dimension {proposal.dimension_id} rejected by persistence gate: {reason}",
                context={
                    "dimension_id": proposal.dimension_id,
                    "gate": "physical_persistence",
                    "reason": reason,
                    "distinct_domains": sorted(d.value for d in proposal.distinct_domains),
                    "observation_days": len(proposal.observation_days),
                },
            )

        record = DimensionRecord(
            dimension_id=proposal.dimension_id,
            label=proposal.label,
            state=DimensionTrialState.CANDIDATE,
            created_at=now_utc,
            trial_started_at=now_utc,
            last_activity_at=now_utc,
        )
        self._records[proposal.dimension_id] = record
        self._enforce_active_cap(now_utc)
        return record

    # --------------------------------------------------------- 门限二

    def record_prediction(
        self, dimension_id: str, *, hit: bool, now: datetime | None = None
    ) -> DimensionRecord:
        """记录一次预测结果，用于 30 天试用期的准确率核算。"""
        record = self._require(dimension_id)
        if record.state in (
            DimensionTrialState.EXPIRED,
            DimensionTrialState.ARCHIVED,
            DimensionTrialState.REJECTED,
        ):
            raise AIOSProtocolError(
                ErrorCode.INVALID_ARGUMENT,
                f"dimension {dimension_id} is {record.state.value} and cannot be scored",
                context={"dimension_id": dimension_id, "state": record.state.value},
            )
        record.prediction_total += 1
        if hit:
            record.prediction_hits += 1
        record.last_activity_at = as_utc(now or utc_now(), "now")
        record.activity_score += 1.0
        return record

    def advance_trial_day(
        self, dimension_id: str, *, now: datetime | None = None
    ) -> DimensionTrialState:
        """推进一天试用期；满 30 天按准确率裁决 ACTIVE 或 EXPIRED。"""
        record = self._require(dimension_id)
        now_utc = as_utc(now or utc_now(), "now")

        if record.state not in (
            DimensionTrialState.CANDIDATE,
            DimensionTrialState.TRIAL,
        ):
            return record.state

        record.trial_days_elapsed += 1
        record.state = DimensionTrialState.TRIAL
        record.last_activity_at = now_utc

        if record.trial_days_elapsed >= MIN_TRIAL_DAYS:
            if record.prediction_accuracy >= MIN_PREDICTION_ACCURACY:
                record.state = DimensionTrialState.ACTIVE
            else:
                record.state = DimensionTrialState.EXPIRED
                self._rejected[dimension_id] = (
                    f"prediction accuracy {record.prediction_accuracy:.2%} "
                    f"< {MIN_PREDICTION_ACCURACY:.0%}"
                )
        return record.state

    def run_full_trial(
        self, dimension_id: str, *, hits: int, total: int, now: datetime | None = None
    ) -> DimensionTrialState:
        """便捷方法：一次性跑完 30 天试用期。"""
        base = as_utc(now or utc_now(), "now")
        for i in range(total):
            self.record_prediction(dimension_id, hit=i < hits, now=base)
        state = DimensionTrialState.TRIAL
        for day in range(MIN_TRIAL_DAYS):
            state = self.advance_trial_day(
                dimension_id, now=base + timedelta(days=day + 1)
            )
            if state in (DimensionTrialState.ACTIVE, DimensionTrialState.EXPIRED):
                break
        return state

    # --------------------------------------------------------- 门限三

    def introspect(
        self, dimension_id: str, *, now: datetime | None = None
    ) -> DimensionRecord:
        """门限三：每日自省配额严格 1 次，超额抛 QuotaExceededBlockError。"""
        record = self._require(dimension_id)
        now_utc = as_utc(now or utc_now(), "now")
        today = now_utc.date()

        if record.last_introspection_day == today:
            if record.introspections_today >= MAX_INTROSPECTIONS_PER_DAY:
                raise QuotaExceededBlockError(
                    dimension_id,
                    context={
                        "day": today.isoformat(),
                        "used": record.introspections_today,
                    },
                )
        else:
            record.introspections_today = 0

        record.introspections_today += 1
        record.last_introspection_day = today
        record.last_activity_at = now_utc
        record.activity_score += 2.0
        return record

    # --------------------------------------------------- 32 维硬上限

    @property
    def max_active(self) -> int:
        return self._max_active

    def active_count(self) -> int:
        return sum(
            1
            for r in self._records.values()
            if r.state in (DimensionTrialState.TRIAL, DimensionTrialState.ACTIVE,
                           DimensionTrialState.CANDIDATE)
        )

    def _enforce_active_cap(self, now: datetime) -> None:
        """达顶则按活跃度淘汰末位为 ARCHIVED。"""
        while self.active_count() > self._max_active:
            victims = [
                r
                for r in self._records.values()
                if r.state
                in (
                    DimensionTrialState.CANDIDATE,
                    DimensionTrialState.TRIAL,
                    DimensionTrialState.ACTIVE,
                )
            ]
            victim = min(victims, key=lambda r: (r.activity_score, r.last_activity_at))
            victim.state = DimensionTrialState.ARCHIVED
            victim.last_activity_at = now
            self._rejected[victim.dimension_id] = (
                f"archived: active dimension cap {self._max_active} reached"
            )

    def archived_ids(self) -> tuple[str, ...]:
        return tuple(
            r.dimension_id
            for r in self._records.values()
            if r.state is DimensionTrialState.ARCHIVED
        )

    # --------------------------------------------------------- 递归防护

    def reflect(self, payload: str, *, requested_depth: int = 1) -> list[str]:
        """执行反思，恶意套娃在第 2 层被切断。"""
        return self.recursion.reflect(payload, requested_depth=requested_depth)

    # --------------------------------------------------------- 查询

    def get(self, dimension_id: str) -> DimensionRecord:
        return self._require(dimension_id)

    def rejection_reason(self, dimension_id: str) -> str | None:
        return self._rejected.get(dimension_id)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for record in self._records.values():
            counts[record.state.value] += 1
        counts["rejected_before_admission"] = len(
            [d for d in self._rejected if d not in self._records]
        )
        counts["recursion_cuts"] = self.recursion.cut_count
        counts["active"] = self.active_count()
        return dict(counts)

    def _require(self, dimension_id: str) -> DimensionRecord:
        try:
            return self._records[dimension_id]
        except KeyError:
            raise KeyError(f"unknown dimension_id: {dimension_id}") from None
