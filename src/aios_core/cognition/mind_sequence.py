"""心智四步序守卫（严格不可逆：照镜子 → 校准羁绊 → 确立姿态 → 审视现场）。

宪法与驾驶舱规格要求：云端心智唤醒必须走一条**严格不可逆的四步序**：

① 照镜子看自己（身份/原则/能力边界）→
② 校准羁绊看关系（信任层级/关系温度）→
③ 确立姿态定语调（沉默/震动提示/严肃直说）→
④ 审视现场看世界（证据、现场事实、行动建议）

缺一不可、顺序不可换、不可回退、不可跳步。工程上这条约束最容易"文档里写着、
代码里没有"：任何一步都可以被随手调用，于是姿态先于羁绊、结论先于身份，
输出就会变成没有分寸感的客服话术。

本守卫把这条顺序变成**机械约束**：

* ``advance(step, ...)`` 只接受"下一步"，跳步/回退/重复一律抛 ``MindSequenceError``；
* ``context_for(step)`` 只把**前面步骤的产物**暴露给当前步 —— 第 3 步拿不到第 4 步的
  现场证据，从数据可见性上杜绝"先有结论再补姿态"；
* 完整走完四步才会产出可序列化的 ``CockpitManifest`` 骨架（单次装载，禁止反复追问）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

__all__ = [
    "MIND_SEQUENCE",
    "STEP_CALIBRATE_BOND",
    "STEP_INSPECT_FIELD",
    "STEP_MIRROR_SELF",
    "STEP_SET_POSTURE",
    "MindSequenceError",
    "MindSequenceRunner",
    "StepOutcome",
]

STEP_MIRROR_SELF = "MIRROR_SELF"
STEP_CALIBRATE_BOND = "CALIBRATE_BOND"
STEP_SET_POSTURE = "SET_POSTURE"
STEP_INSPECT_FIELD = "INSPECT_FIELD"

#: 四步序的固定执行顺序（不可逆）。
MIND_SEQUENCE: tuple[str, ...] = (
    STEP_MIRROR_SELF,
    STEP_CALIBRATE_BOND,
    STEP_SET_POSTURE,
    STEP_INSPECT_FIELD,
)

#: 面向用户的中文步骤名（①~④ 与宪法口径逐字一致）。
STEP_LABELS: Mapping[str, str] = {
    STEP_MIRROR_SELF: "①照镜子看自己",
    STEP_CALIBRATE_BOND: "②校准羁绊看关系",
    STEP_SET_POSTURE: "③确立姿态定语调",
    STEP_INSPECT_FIELD: "④审视现场看世界",
}


class MindSequenceError(RuntimeError):
    """四步序违宪（跳步/回退/重复/越权读取后续步骤产物）。"""


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """单步产物（含该步 Token 计量，供装配预算核算）。"""

    step: str
    label: str
    payload: Mapping[str, Any]
    tokens: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "label": self.label,
            "tokens": self.tokens,
            "payload": dict(self.payload),
        }


@dataclass
class MindSequenceRunner:
    """一次唤醒会话内的四步序执行器（非可逆）。"""

    token_budgets: Mapping[str, int] = field(
        default_factory=lambda: {
            STEP_MIRROR_SELF: 260,
            STEP_CALIBRATE_BOND: 260,
            STEP_SET_POSTURE: 180,
            STEP_INSPECT_FIELD: 800,
        }
    )
    _cursor: int = 0
    _outcomes: List[StepOutcome] = field(default_factory=list)
    _runs: int = 0

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def begin(self) -> None:
        """开启一次新的四步序（上一轮必须已走完）。"""

        if self._outcomes and self._cursor < len(MIND_SEQUENCE):
            raise MindSequenceError(
                f"上一轮四步序未走完（已到 {self._cursor}/{len(MIND_SEQUENCE)}），禁止重开"
            )
        self._cursor = 0
        self._outcomes = []
        self._runs += 1

    def advance(self, step: str, payload: Mapping[str, Any], *, tokens: int) -> StepOutcome:
        """推进到下一步；顺序错误一律拒绝。"""

        if self._cursor >= len(MIND_SEQUENCE):
            raise MindSequenceError("四步序已走完，不允许重复执行（严格不可逆）")
        expected = MIND_SEQUENCE[self._cursor]
        if step != expected:
            raise MindSequenceError(
                f"心智四步序不可乱序：期望 {expected}（{STEP_LABELS[expected]}），"
                f"收到 {step}；跳过与回退均被禁止"
            )
        if tokens < 0:
            raise MindSequenceError("tokens must be >= 0")
        budget = int(self.token_budgets.get(step, 0))
        if budget and tokens > budget:
            raise MindSequenceError(
                f"{STEP_LABELS[step]} 装配 Token {tokens} 超出该步预算 {budget}"
            )
        outcome = StepOutcome(
            step=step, label=STEP_LABELS[step], payload=dict(payload), tokens=int(tokens)
        )
        self._outcomes.append(outcome)
        self._cursor += 1
        return outcome

    # ------------------------------------------------------------------
    # 读取与审计
    # ------------------------------------------------------------------

    def context_for(self, step: str) -> Mapping[str, Any]:
        """第 N 步只能看到前 N-1 步的产物（数据可见性即防越权）。"""

        if step not in MIND_SEQUENCE:
            raise MindSequenceError(f"unknown step {step!r}")
        position = MIND_SEQUENCE.index(step)
        if position != self._cursor:
            raise MindSequenceError(
                f"{STEP_LABELS[step]} 不是当前步（当前在 {self._cursor}），"
                "禁止提前读取或回看后续步骤产物"
            )
        merged: Dict[str, Any] = {}
        for outcome in self._outcomes[:position]:
            merged.update(outcome.payload)
        return merged

    @property
    def completed(self) -> bool:
        return self._cursor == len(MIND_SEQUENCE)

    @property
    def progress(self) -> int:
        return self._cursor

    @property
    def runs(self) -> int:
        return self._runs

    def outcomes(self) -> tuple[StepOutcome, ...]:
        return tuple(self._outcomes)

    def manifest_tokens(self) -> int:
        return sum(outcome.tokens for outcome in self._outcomes)

    def as_manifest(self) -> Mapping[str, Any]:
        """单次装载的驾驶舱骨架（四步全走完才允许产出）。"""

        if not self.completed:
            raise MindSequenceError(
                f"四步序未走完（{self._cursor}/{len(MIND_SEQUENCE)}），不允许装载驾驶舱"
            )
        return {
            "steps": [
                {"step": outcome.step, "label": outcome.label, "tokens": outcome.tokens}
                for outcome in self._outcomes
            ],
            "token_count": self.manifest_tokens(),
            "order": [STEP_LABELS[step] for step in MIND_SEQUENCE],
            "single_load": True,
            "backtracking_allowed": False,
        }

    @staticmethod
    def labels(sequence: Sequence[str] = MIND_SEQUENCE) -> tuple[str, ...]:
        return tuple(STEP_LABELS[step] for step in sequence)
