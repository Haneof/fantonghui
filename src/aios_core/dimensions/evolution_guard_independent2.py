"""M3-001R 动态维度衍生三重硬门限状态机（最高宪法铁律 5 落实）。

铁律 5：严禁 AI 无休止自言自语、虚假自省导致维度爆炸；端侧算力有限，
认知维度必须极度克制。

三重门限准入状态机：
    门一（物理跨域持续异常）：证据必须横跨 ≥2 个物理域（如 SLEEP +
    BLOOD_PRESSURE），且最短持续跨度 ≥3 天，否则 GateOneRejection，
    连 CANDIDATE 都不准生成。

    门二（30 天试用期与预测检验）：CANDIDATE 创建起 30 天内连续接受
    认知解释力检验；到期时预测准确率严格 ≥ 70%（success/total），
    否则自动 EXPIRED。准确率分母必须非零——零次预测直接 EXPIRED，
    杜绝"不检验就转正"。

    门三（每日反思配额）：每自然日自省评估配额 == 1，第二次同日落点
    直接 QuotaExceededBlockError。

活跃维度全局硬顶：
    ACTIVE 集合任何时候 ≤ 32。第 33 个激活时，凭（活跃度, 贡献度）
    双键排序淘汰末位归档 ARCHIVED；归档永不自动复活。

自问自答死循环熔断：
    反思链深度由 ``reflection_scope()`` 上下文计数：第 1 层放行，
    试图进入第 2 层递归时直接 ReflectionLoopBreaker 物理切断，
    ``self_talk_cut_count`` 见证切断次数——AI 不允许对自己的反思
    再进行反思。

工程护栏：
    - 日历日由调用方注入（``day: int``），守卫本身不读系统时钟——
      仿真与真机共用同一裁决路径，杜绝"打表绕门禁"。
    - 全部状态迁移走唯一入口，外部无直接篡改状态的公共写口。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Sequence


class PhysicalDomain(Enum):
    SLEEP = "sleep"
    HEART_RATE = "heart_rate"
    BLOOD_PRESSURE = "blood_pressure"
    ACTIVITY = "activity"
    METABOLIC = "metabolic"
    VOCAL_BIOMARKER = "vocal_biomarker"


class DimensionState(Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class DimensionGateRejection(ValueError):
    """门一拒绝：证据不满足物理跨域持续异常的准入条件。"""


class QuotaExceededBlockError(RuntimeError):
    """门三拒绝：每日自省配额（1 次）已耗尽。"""


class ReflectionLoopBreaker(RuntimeError):
    """自问自答熔断：试图进入第 2 层反思递归时被物理切断。"""


@dataclass(frozen=True)
class AnomalyEvidence:
    domain: PhysicalDomain
    first_seen_day: int
    last_seen_day: int
    description: str = ""

    def __post_init__(self) -> None:
        if self.last_seen_day < self.first_seen_day:
            raise ValueError("last_seen_day 不能早于 first_seen_day")

    @property
    def sustained_days(self) -> int:
        return self.last_seen_day - self.first_seen_day + 1


@dataclass
class DimensionCandidate:
    candidate_id: str
    name: str
    evidence: tuple[AnomalyEvidence, ...]
    proposed_day: int
    state: DimensionState = DimensionState.CANDIDATE
    prediction_success: int = 0
    prediction_fail: int = 0
    activity_score: float = 0.0
    contribution_score: float = 0.0

    @property
    def prediction_accuracy(self) -> float | None:
        total = self.prediction_success + self.prediction_fail
        if total == 0:
            return None
        return self.prediction_success / total


class EvolutionGuard:
    """三重硬门限准入状态机 + 全局 32 硬顶 + 反思熔断。"""

    MAX_ACTIVE = 32
    MIN_DOMAINS = 2
    MIN_SUSTAINED_DAYS = 3
    PROBATION_DAYS = 30
    MIN_ACCURACY = 0.70
    DAILY_REFLECTION_QUOTA = 1

    def __init__(self) -> None:
        self._candidates: dict[str, DimensionCandidate] = {}
        self._reflection_quota_by_day: dict[int, int] = {}
        self._reflection_depth = 0
        # 门禁证据计数
        self.gate_one_rejections = 0
        self.quota_blocks = 0
        self.self_talk_cut_count = 0
        self.evacuated_to_archive: list[str] = []

    # ------------------------------------------------------------ 门一：准入

    def submit(self, candidate_id: str, name: str, evidence: Sequence[AnomalyEvidence], *, day: int) -> DimensionCandidate:
        """门一：物理跨域持续异常准入。不满足 → DimensionGateRejection。"""
        if candidate_id in self._candidates:
            raise ValueError(f"重复提交候选: {candidate_id}")
        evidence_tuple = tuple(evidence)
        if not name.strip():
            raise ValueError("候选维度名不能为空")

        domains = {e.domain for e in evidence_tuple}
        if len(domains) < self.MIN_DOMAINS:
            self.gate_one_rejections += 1
            raise DimensionGateRejection(
                f"门一拒绝：证据只覆盖 {len(domains)} 个物理域（{sorted(d.value for d in domains)}），"
                f"准入要求横跨 ≥ {self.MIN_DOMAINS} 个域"
            )
        weakest = min((e.sustained_days for e in evidence_tuple), default=0)
        if weakest < self.MIN_SUSTAINED_DAYS:
            self.gate_one_rejections += 1
            raise DimensionGateRejection(
                f"门一拒绝：最短持续跨度 {weakest} 天 < {self.MIN_SUSTAINED_DAYS} 天，"
                f"瞬时噪声不构成新维度资格"
            )

        candidate = DimensionCandidate(
            candidate_id=candidate_id,
            name=name,
            evidence=evidence_tuple,
            proposed_day=day,
        )
        self._candidates[candidate_id] = candidate
        return candidate

    # ----------------------------------------------------- 门二：试用期裁决

    def record_prediction(self, candidate_id: str, *, day: int, success: bool) -> None:
        cand = self._must_get(candidate_id)
        if cand.state is not DimensionState.CANDIDATE:
            raise ValueError(f"候选 {candidate_id} 不在试用期（{cand.state.value}），拒绝继续记录预测")
        if day < cand.proposed_day:
            raise ValueError("试用记录日不能早于提案日")
        if success:
            cand.prediction_success += 1
        else:
            cand.prediction_fail += 1

    def resolve_probation(self, candidate_id: str, *, day: int) -> DimensionState:
        """满 30 天试用裁决：准确率 ≥70% → ACTIVE，否则 EXPIRED（零样本必死）。"""
        cand = self._must_get(candidate_id)
        if cand.state is not DimensionState.CANDIDATE:
            return cand.state
        if day - cand.proposed_day < self.PROBATION_DAYS:
            return DimensionState.CANDIDATE  # 试用期未满，继续观察
        accuracy = cand.prediction_accuracy
        if accuracy is None or accuracy < self.MIN_ACCURACY:
            cand.state = DimensionState.EXPIRED
        else:
            self._activate(cand)
        return cand.state

    # ------------------------------------------------------------ 门三：配额

    def reflect(self, candidate_id: str, *, day: int) -> str:
        """每日自省评估配额 == 1。超额直接 QuotaExceededBlockError。"""
        cand = self._must_get(candidate_id)
        if cand.state not in (DimensionState.CANDIDATE, DimensionState.ACTIVE):
            raise ValueError(f"仅 CANDIDATE/ACTIVE 可自省（{cand.state.value}）")
        used = self._reflection_quota_by_day.get(day, 0)
        if used >= self.DAILY_REFLECTION_QUOTA:
            self.quota_blocks += 1
            raise QuotaExceededBlockError(
                f"门三拒绝：第 {day} 日自省配额（{self.DAILY_REFLECTION_QUOTA} 次）已耗尽"
            )
        self._reflection_quota_by_day[day] = used + 1
        return f"reflection:{day}:{cand.candidate_id}"

    # -------------------------------------------------- 全局硬顶 32 & 淘汰

    def _activate(self, cand: DimensionCandidate) -> None:
        active = [c for c in self._candidates.values() if c.state is DimensionState.ACTIVE]
        if len(active) >= self.MAX_ACTIVE:
            # （活跃度, 贡献度, 提案日）三键淘汰末位：最低者优先归档
            victim = min(
                active,
                key=lambda c: (c.activity_score, c.contribution_score, c.proposed_day),
            )
            victim.state = DimensionState.ARCHIVED
            self.evacuated_to_archive.append(victim.candidate_id)
        cand.state = DimensionState.ACTIVE

    def set_scores(self, candidate_id: str, *, activity: float, contribution: float) -> None:
        if not (0.0 <= activity <= 1.0 and 0.0 <= contribution <= 1.0):
            raise ValueError("活跃度/贡献度必须落在 [0,1]")
        cand = self._must_get(candidate_id)
        cand.activity_score = activity
        cand.contribution_score = contribution

    @property
    def active_count(self) -> int:
        return sum(1 for c in self._candidates.values() if c.state is DimensionState.ACTIVE)

    @property
    def archived_count(self) -> int:
        return sum(1 for c in self._candidates.values() if c.state is DimensionState.ARCHIVED)

    def state_of(self, candidate_id: str) -> DimensionState:
        return self._must_get(candidate_id).state

    # ---------------------------------------------------- 自问自答熔断

    @contextmanager
    def reflection_scope(self) -> Iterator[None]:
        """反思链上下文：第 1 层放行；试图嵌套进入第 2 层即物理切断。

        熔断不抛出"可恢复的软错误"——ReflectionLoopBreaker 是硬切断，
        调用方必须在第 2 层入口前停下（``self_talk_cut_count`` 记账）。
        """
        if self._reflection_depth >= 1:
            self.self_talk_cut_count += 1
            raise ReflectionLoopBreaker(
                f"铁律 5 熔断：检测到第 {self._reflection_depth + 1} 层反思递归，物理切断"
            )
        self._reflection_depth += 1
        try:
            yield
        finally:
            self._reflection_depth -= 1

    # ------------------------------------------------------------ 内部

    def _must_get(self, candidate_id: str) -> DimensionCandidate:
        try:
            return self._candidates[candidate_id]
        except KeyError:
            raise KeyError(f"未知候选维度: {candidate_id}") from None
