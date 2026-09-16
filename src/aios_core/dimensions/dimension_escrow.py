"""M3-001R · 维度创建权的 Token 配额托管与 O(D²) 刹车

工单点名的政策域是 ``governance/runtime_policy.json`` 的 ``dimension_escrow`` 段。
本模块把该段的**七个法定字段逐条变成可执行的机械约束**，一个不落：

===============================================  ==============================  ==========================
法定字段                                          值                               本模块的落点
===============================================  ==============================  ==========================
``candidate_to_trial_requires_preallocated_       true                            :meth:`promote_to_trial`
monthly_token_quota``                                                               先托管后晋升，无托管不晋升
``insufficient_quota_action``                     reject_creation_with_           :exc:`BudgetExhaustedError`
                                                  BUDGET_EXHAUSTED                  用**法定** ErrorCode
``dormant_returns_quota``                         true                            :meth:`send_dormant` 归还配额
``low_frequency_dimension_must_not_be_deleted``   true                            无任何删除路径；只能 DORMANT
``resonance_pair_cap_per_window``                 60                              :meth:`add_resonance_pair`
``cross_domain_synapse_fanin_max``                8                               :meth:`add_synapse`
``cross_domain_synapse_fanout_max``               8                               :meth:`add_synapse`
===============================================  ==============================  ==========================

配额池同样有法定来源，**不臆造**：``token_budget.subsystems.dimension.monthly_cap``
= 30000，其 ``basis`` 明写「10 候选/月 × 3000（§76 预算托管准入）」。全部 12 个子系统
之和精确等于 ``monthly_total_cap``（零基闭合），因此维度托管花的每一个 token 都是从
用户月度总封套里真实扣走的，不是凭空多出来的一笔。

四大硬门禁
----------
**门禁 1 · 创建权必须预算托管**
CANDIDATE → TRIAL 之前必须预分配月度 token 配额；池不足即按法定动作
``reject_creation_with_BUDGET_EXHAUSTED`` 拒绝创建，错误码是法定
``ErrorCode.BUDGET_EXHAUSTED``（经 ``AIOSProtocolError`` 传播，可跨协议边界），
**不是** ``RuntimeError`` 之类的本地异常 —— 本地异常到不了协议边界，调用方无从分支。

**门禁 2 · DORMANT 归还配额（反棘轮）**
政策 ``evidence`` 行点名了病灶：「创建权无预算托管 + 低频禁删 = **棘轮效应**，
维度数与共振对 O(D²) 单调递增，无人能降」。棘轮的物理成因是配额只出不进，所以
归还路径必须存在且守恒。本模块的承重不变量是：

    自由配额 + Σ(未归还账户的托管配额) == 池总量        （每一次变更之后都成立）

:func:`DimensionEscrow._assert_conservation` 在每个变更方法末尾执行。这条守恒式
比"归还会发生"强得多：它同时排除了**重复归还**（凭空造配额）与**漏归还**（配额泄漏），
两者都会让棘轮重新长出来。

**门禁 3 · 低频不等于无价值，绝不删除**
法定 ``DimensionLifecycle`` 的十个成员里**没有 DELETED，也没有 ARCHIVED / EXPIRED**。
"留档但不再花钱"的法定形态是 ``LOW_ACTIVITY`` → ``DORMANT``（配额归还、记录永存）。
本模块**不提供任何删除 API**：``_records`` 与 ``_history`` 只增不减，DORMANT /
REJECTED / MERGED 的维度永远可查、永远带完整变迁史。这条用三种方式钉死：
AST 断言不存在 delete/remove/erase/purge/drop/forget/evict 之类的公开方法；
行为断言跑完整生命周期后每个曾注册的 id 仍可查且历史完整；
契约断言枚举里没有 DELETED 成员且本模块的转移表每个目标都是法定成员。

**门禁 4 · 共振对与跨域突触上限把 O(D²) 刹成 O(1)**
D 个维度的无序对数是 D(D-1)/2，随 D 平方增长；``resonance_pair_cap_per_window`` = 60
把它按窗截断成常数。:meth:`add_resonance_pair` 第 61 对即拒，换窗重置。
``cross_domain_synapse_fanin_max`` / ``fanout_max`` = 8 则阻止单个维度变成
"万物互联"的枢纽（那种枢纽一旦形成，任何一次修正都会沿它扇出成雪崩）。

复用的既有法定构件（不重复实现）
------------------------------
``contracts.enums.DimensionLifecycle``（**唯一**状态词汇表）、
``contracts.models.DimensionDefinition``（法定 WorldObject，维度记录的载体，其
``lifecycle`` 字段就是状态存放处 —— 状态活在契约里而不是活在本模块的私有枚举里）、
``contracts.enums.ErrorCode.BUDGET_EXHAUSTED``、``errors.AIOSProtocolError``、
``token_budget`` 与 ``dimension_escrow`` 政策段。

尚未入法 / 有意不做
------------------
* **维度生命周期转移表在法定代码里没有对应物。** ``services/state_machines.py``
  只有 ``_TASK_TRANSITIONS`` 与 ``_EVENT_TRANSITIONS``，没有维度表。因此
  :data:`PROPOSED_DIMENSION_TRANSITIONS` 明确标注为**本模块推导的提案**：每条边都
  给出依据（政策字段名或枚举成员语义），但须交治理批准。它的**法定归属地**是
  ``services/state_machines.py``（与任务/事件两表并列），而那是既有文件，在
  "不覆盖任何既有文件"的约束下不能改，故此处只留提案与归属地说明。
  即便如此，两条不依赖具体边集的硬性质已经可以先入测试：转移表的键**穷尽**
  法定枚举全部十个成员；每条边的两端**都是**法定成员（提案永不脱离契约）。
* **每候选 3000 token、10 候选/月**出自政策 ``basis`` 的散文说明，不是结构化字段，
  故不在生产代码里解析散文；相关算术闭合放在测试里作为锚（与 M2-001 对心跳
  240 × 750 的处置同一手法）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Final, Iterable, Mapping, Sequence

from aios_core.contracts.enums import DimensionLifecycle, ErrorCode
from aios_core.contracts.models import DimensionDefinition
from aios_core.errors import AIOSProtocolError

__all__ = [
    "PROPOSED_DIMENSION_TRANSITIONS",
    "BudgetExhaustedError",
    "DimensionDeletionAttemptError",
    "DimensionEscrow",
    "DimensionEscrowError",
    "EscrowAccount",
    "IllegalLifecycleTransitionError",
    "ResonanceCapExceededError",
    "SynapseFanCapExceededError",
    "TransitionProposal",
    "load_dimension_escrow_policy",
    "load_runtime_policy",
    "load_token_budget_policy",
    "validate_policy_section",
]


_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_POLICY_PATH: Final[Path] = _REPO_ROOT / "governance" / "runtime_policy.json"

#: ``dimension`` 子系统的法定名（配额池来源）。
DIMENSION_SUBSYSTEM: Final[str] = "dimension"


# ---------------------------------------------------------------------------
# 错误族
# ---------------------------------------------------------------------------


class DimensionEscrowError(AIOSProtocolError):
    """维度托管侧统一错误族。

    ``ErrorCode`` 没有 ``ILLEGAL_STATE``，故"状态不该如此"一律走 ``INVALID_ARGUMENT``
    （与 M2-005R / M2-001 同一处置：宁可复用既有码，也不为造码去改法定枚举）。
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
        context: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, context=context)


class BudgetExhaustedError(DimensionEscrowError):
    """门禁 1：配额不足。政策法定动作 ``reject_creation_with_BUDGET_EXHAUSTED``。

    用法定 ``ErrorCode.BUDGET_EXHAUSTED`` 并经 ``AIOSProtocolError`` 传播 ——
    调用方（含协议边界之外）因此可以按码分支，而不是靠匹配错误文案。
    """

    def __init__(self, message: str, *, context: Dict[str, Any] | None = None) -> None:
        super().__init__(message, code=ErrorCode.BUDGET_EXHAUSTED, context=context)


class IllegalLifecycleTransitionError(DimensionEscrowError):
    """生命周期跃迁不在提案转移表内。"""


class ResonanceCapExceededError(DimensionEscrowError):
    """门禁 4：共振对超出 ``resonance_pair_cap_per_window``。"""


class SynapseFanCapExceededError(DimensionEscrowError):
    """门禁 4：跨域突触的扇入或扇出超出法定上限。"""


class DimensionDeletionAttemptError(DimensionEscrowError):
    """门禁 3：任何试图删除维度记录的调用。

    本模块**不提供**删除路径，此异常存在的意义是让"想删"这件事有一个明确的、
    可被测试捕获的失败形态，而不是让调用方去摸一个不存在的 API 后自己造一个。
    """


# ---------------------------------------------------------------------------
# 政策引用与校验
# ---------------------------------------------------------------------------


def load_runtime_policy() -> Dict[str, Any]:
    """读取整份 ``runtime_policy.json``。唯一权威来源，不复制常量。"""
    if not _POLICY_PATH.exists():
        raise DimensionEscrowError(f"找不到法定政策文件：{_POLICY_PATH}")
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def validate_policy_section(
    section_name: str,
    section: Any,
    required_fields: Sequence[str],
    *,
    required_true: Sequence[str] = (),
) -> Dict[str, Any]:
    """校验一段政策：字段必须存在，``required_true`` 里的布尔字段必须为真。

    **文件路径与注入路径都必须过这一关**。这条纪律是 M2-005R 被自己的测试抓出来的
    真 bug（初版只在读文件时校验，``policy=...`` 注入即绕过法律），此后每个模块沿用。
    """
    if not isinstance(section, dict):
        raise DimensionEscrowError(f"政策段 {section_name!r} 必须是对象")
    for key in required_fields:
        if key not in section:
            raise DimensionEscrowError(f"政策段 {section_name} 缺少法定字段 {key!r}")
    for key in required_true:
        if section.get(key) is not True:
            raise DimensionEscrowError(
                f"政策段 {section_name}.{key} 法定值为 True，实际为 {section.get(key)!r}"
                " —— 拒绝带着漂移的法律参数运行"
            )
    return dict(section)


def _validated_section(loader: Any, section: Any, section_name: str) -> Dict[str, Any]:
    """把"注入一个政策段"归一成"注入一份合成 root"，再走**同一个** loader。"""
    if section is None:
        return loader()
    return loader({section_name: section})


def load_dimension_escrow_policy(
    policy: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """读取并校验 ``dimension_escrow`` 段（本工单点名的政策域）。"""
    root = dict(policy) if policy is not None else load_runtime_policy()
    section = validate_policy_section(
        "dimension_escrow",
        root.get("dimension_escrow"),
        required_fields=(
            "insufficient_quota_action",
            "resonance_pair_cap_per_window",
            "cross_domain_synapse_fanin_max",
            "cross_domain_synapse_fanout_max",
        ),
        required_true=(
            "candidate_to_trial_requires_preallocated_monthly_token_quota",
            "dormant_returns_quota",
            "low_frequency_dimension_must_not_be_deleted",
        ),
    )
    if section["insufficient_quota_action"] != "reject_creation_with_BUDGET_EXHAUSTED":
        raise DimensionEscrowError(
            "dimension_escrow.insufficient_quota_action 法定值为 "
            f"'reject_creation_with_BUDGET_EXHAUSTED'，实际为 "
            f"{section['insufficient_quota_action']!r}"
        )
    for key in (
        "resonance_pair_cap_per_window",
        "cross_domain_synapse_fanin_max",
        "cross_domain_synapse_fanout_max",
    ):
        if not isinstance(section[key], int) or section[key] <= 0:
            raise DimensionEscrowError(f"dimension_escrow.{key} 必须是正整数")
    return section


def load_token_budget_policy(policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """读取并校验 ``token_budget`` 段，且必须含 ``dimension`` 子系统（配额池来源）。"""
    root = dict(policy) if policy is not None else load_runtime_policy()
    section = validate_policy_section(
        "token_budget",
        root.get("token_budget"),
        required_fields=("monthly_total_cap", "subsystems"),
    )
    subsystem = section["subsystems"].get(DIMENSION_SUBSYSTEM)
    if not isinstance(subsystem, dict) or "monthly_cap" not in subsystem:
        raise DimensionEscrowError(
            f"token_budget.subsystems.{DIMENSION_SUBSYSTEM}.monthly_cap 缺失 —— "
            "维度配额池没有法定来源，拒绝臆造一个数字"
        )
    return section


# ---------------------------------------------------------------------------
# 生命周期转移表（提案，尚未入法）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransitionProposal:
    """一条提案边：目标状态 + **依据**。

    依据必须写出来，否则"提案"与"随手编的"在代码里长得一模一样。治理评审时，
    没有依据的边无从判断该批准还是该驳回。
    """

    target: DimensionLifecycle
    basis: str


#: **提案，尚未入法**：维度生命周期转移表。
#:
#: 法定代码里没有维度转移表（``services/state_machines.py`` 只有任务与事件两张），
#: 所以这里按政策字段与枚举成员语义推导。它的**法定归属地**是与
#: ``_TASK_TRANSITIONS`` / ``_EVENT_TRANSITIONS`` 并列放进 ``state_machines.py``，
#: 但那是既有文件，在"不覆盖任何既有文件"的约束下不能改 —— 故只留提案 + 归属地说明。
#:
#: 即便边集尚未批准，两条不依赖具体边的硬性质已经可以先入测试：
#: 键**穷尽**法定枚举全部十个成员；每条边两端**都是**法定成员。
PROPOSED_DIMENSION_TRANSITIONS: Final[
    Dict[DimensionLifecycle, tuple[TransitionProposal, ...]]
] = {
    DimensionLifecycle.CANDIDATE: (
        TransitionProposal(
            DimensionLifecycle.TRIAL,
            "dimension_escrow.candidate_to_trial_requires_preallocated_monthly_token_quota",
        ),
        TransitionProposal(DimensionLifecycle.REJECTED, "法定负向终态；记录仍须留档"),
        TransitionProposal(DimensionLifecycle.MERGED, "§76 维度不能无限爆炸：候选期即可并入既有维度"),
        TransitionProposal(DimensionLifecycle.REVISED, "候选定义被修正后重新入册"),
    ),
    DimensionLifecycle.TRIAL: (
        TransitionProposal(DimensionLifecycle.ACTIVE, "试用期通过晋升"),
        TransitionProposal(DimensionLifecycle.REJECTED, "试用期未通过；托管配额须归还"),
        TransitionProposal(DimensionLifecycle.DORMANT, "dimension_escrow.dormant_returns_quota"),
        TransitionProposal(DimensionLifecycle.MERGED, "试用期内并入既有维度"),
        TransitionProposal(DimensionLifecycle.REVISED, "试用期定义被修正"),
    ),
    DimensionLifecycle.ACTIVE: (
        TransitionProposal(
            DimensionLifecycle.LOW_ACTIVITY,
            "dimension_escrow.low_frequency_dimension_must_not_be_deleted："
            "低频先降级，不删除",
        ),
        TransitionProposal(DimensionLifecycle.DORMANT, "休眠并归还配额"),
        TransitionProposal(DimensionLifecycle.MERGED, "§76 抑制维度爆炸"),
        TransitionProposal(DimensionLifecycle.SPLIT, "维度过载时分裂"),
        TransitionProposal(DimensionLifecycle.REVISED, "定义被修正"),
    ),
    DimensionLifecycle.LOW_ACTIVITY: (
        TransitionProposal(DimensionLifecycle.DORMANT, "低频的自然归宿：留档且归还配额"),
        TransitionProposal(DimensionLifecycle.ACTIVE, "§75 低频不等于无价值：回暖即复活跃"),
        TransitionProposal(DimensionLifecycle.REACTIVATED, "低频后被显式重新启用"),
        TransitionProposal(DimensionLifecycle.MERGED, "并入既有维度"),
        TransitionProposal(DimensionLifecycle.REVISED, "定义被修正"),
    ),
    DimensionLifecycle.DORMANT: (
        TransitionProposal(DimensionLifecycle.REACTIVATED, "法定成员；复活须重新托管配额"),
        TransitionProposal(DimensionLifecycle.MERGED, "休眠期亦可并入"),
        TransitionProposal(DimensionLifecycle.REVISED, "休眠期定义被修正"),
    ),
    DimensionLifecycle.REACTIVATED: (
        TransitionProposal(DimensionLifecycle.ACTIVE, "复活后回到活跃"),
        TransitionProposal(DimensionLifecycle.TRIAL, "复活须重新走试用期检验"),
        TransitionProposal(DimensionLifecycle.DORMANT, "再度休眠并归还配额"),
        TransitionProposal(DimensionLifecycle.MERGED, "并入既有维度"),
        TransitionProposal(DimensionLifecycle.REVISED, "定义被修正"),
    ),
    # 三个终态：出边为空集，但**记录永存**（门禁 3）。
    DimensionLifecycle.MERGED: (),
    DimensionLifecycle.SPLIT: (),
    DimensionLifecycle.REJECTED: (),
    DimensionLifecycle.REVISED: (
        TransitionProposal(DimensionLifecycle.CANDIDATE, "修正后的定义重新入册走候选"),
        TransitionProposal(DimensionLifecycle.ACTIVE, "仅修订描述、不改变活跃度"),
        TransitionProposal(DimensionLifecycle.DORMANT, "修订后归入休眠"),
    ),
}


def allowed_dimension_transitions(
    current: DimensionLifecycle,
) -> frozenset[DimensionLifecycle]:
    """提案表的查询接口，形状对齐既有 ``allowed_task_transitions``。

    刻意同名同形：将来这张表获批迁入 ``services/state_machines.py`` 时，调用方
    只需改 import，不需要改调用形状。
    """
    if not isinstance(current, DimensionLifecycle):
        raise DimensionEscrowError(
            f"current 必须是法定 DimensionLifecycle 成员，收到 {current!r}"
        )
    return frozenset(p.target for p in PROPOSED_DIMENSION_TRANSITIONS[current])


# ---------------------------------------------------------------------------
# 托管账户
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EscrowAccount:
    """一个维度的配额托管账户。

    ``quota`` 是**当前仍被占用**的额度；归还后置 0 并记 ``returned_at``。
    刻意不删除账户本身 —— 归还过的账户是"这个维度曾经花过多少"的唯一凭证，
    删掉它，棘轮效应就会以"看不出发生过"的形式回来。
    """

    dimension_id: str
    quota: int
    escrowed_at: datetime
    lifecycle: DimensionLifecycle
    returned_at: datetime | None = None
    history: tuple[tuple[str, str], ...] = ()

    @property
    def holds_quota(self) -> bool:
        return self.quota > 0 and self.returned_at is None

    def to_audit(self) -> Dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "quota": self.quota,
            "escrowed_at": self.escrowed_at.isoformat(),
            "lifecycle": self.lifecycle.value,
            "returned_at": self.returned_at.isoformat() if self.returned_at else None,
            "history": [{"at": a, "to": b} for a, b in self.history],
        }


def _utc(moment: datetime) -> datetime:
    """naive datetime 一律按 UTC 解释，避免虚拟时钟混入本地时区。"""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 托管器
# ---------------------------------------------------------------------------


class DimensionEscrow:
    """维度创建权的 Token 配额托管器 + O(D²) 刹车。

    状态一律活在**法定契约**里：维度记录是 ``DimensionDefinition``，其 ``lifecycle``
    字段是 ``DimensionLifecycle``。本模块不定义任何状态枚举 —— 私有枚举与法定枚举
    同名同义却不同值，是本仓库已经付过学费的缺陷类（``ObjectType`` /
    ``ObjectTypeV3`` 双枚举曾致 v3 扩展类型完全无法落盘）。
    """

    def __init__(
        self,
        *,
        policy: Mapping[str, Any] | None = None,
        escrow_policy: Mapping[str, Any] | None = None,
        token_budget_policy: Mapping[str, Any] | None = None,
        pool_tokens: int | None = None,
    ) -> None:
        root: Dict[str, Any] = dict(policy) if policy is not None else load_runtime_policy()
        self.escrow_policy: Dict[str, Any] = (
            _validated_section(load_dimension_escrow_policy, escrow_policy, "dimension_escrow")
            if escrow_policy is not None
            else load_dimension_escrow_policy(root)
        )
        self.token_budget_policy: Dict[str, Any] = (
            _validated_section(load_token_budget_policy, token_budget_policy, "token_budget")
            if token_budget_policy is not None
            else load_token_budget_policy(root)
        )

        #: 配额池：法定来源是 ``token_budget.subsystems.dimension.monthly_cap``。
        self.pool_tokens: Final[int] = (
            pool_tokens
            if pool_tokens is not None
            else int(self.token_budget_policy["subsystems"][DIMENSION_SUBSYSTEM]["monthly_cap"])
        )
        monthly_total = int(self.token_budget_policy["monthly_total_cap"])
        if self.pool_tokens < 0:
            raise DimensionEscrowError(f"配额池不得为负：{self.pool_tokens}")
        if self.pool_tokens > monthly_total:
            # 零基闭合：12 个子系统之和精确等于 monthly_total_cap。任何子系统
            # 托管超过总封套都意味着闭合被破坏 —— 那是政策级矛盾，必须硬失败。
            raise DimensionEscrowError(
                f"维度配额池 {self.pool_tokens} 超过月度总封套 {monthly_total}；"
                "token_budget 的零基闭合被破坏"
            )

        self.resonance_cap: Final[int] = int(
            self.escrow_policy["resonance_pair_cap_per_window"]
        )
        self.fanin_max: Final[int] = int(self.escrow_policy["cross_domain_synapse_fanin_max"])
        self.fanout_max: Final[int] = int(self.escrow_policy["cross_domain_synapse_fanout_max"])

        self._records: Dict[str, DimensionDefinition] = {}   # 只增不减（门禁 3）
        self._accounts: Dict[str, EscrowAccount] = {}        # 只增不减（门禁 2/3）
        self._history: Dict[str, list[Dict[str, Any]]] = {}  # 只增不减（门禁 3）
        self._free_tokens: int = self.pool_tokens
        self._resonance: Dict[str, set[tuple[str, str]]] = {}
        self._synapses: set[tuple[str, str]] = set()
        self._rejections: list[Dict[str, Any]] = []

    # -- 内部工具 ----------------------------------------------------------

    def _assert_conservation(self) -> None:
        """门禁 2 的承重不变量：**自由 + 托管 == 池总量**，每一次变更后都成立。

        这条守恒式比"归还会发生"强得多 —— 它同时排除**重复归还**（凭空造配额）
        与**漏归还**（配额泄漏）。两者都会让棘轮重新长出来，而且都不会被
        "归还在某个用例里发生过"这种测试发现。
        """
        escrowed = sum(a.quota for a in self._accounts.values() if a.holds_quota)
        if self._free_tokens + escrowed != self.pool_tokens:
            raise DimensionEscrowError(
                "配额守恒破裂："
                f"free={self._free_tokens} + escrowed={escrowed} != pool={self.pool_tokens}",
                context={
                    "free": self._free_tokens,
                    "escrowed": escrowed,
                    "pool": self.pool_tokens,
                },
            )

    def _record(self, dimension_id: str) -> DimensionDefinition:
        record = self._records.get(dimension_id)
        if record is None:
            raise DimensionEscrowError(
                f"维度 {dimension_id!r} 不在册", context={"dimension_id": dimension_id}
            )
        return record

    def _account(self, dimension_id: str) -> EscrowAccount:
        account = self._accounts.get(dimension_id)
        if account is None:
            raise DimensionEscrowError(
                f"维度 {dimension_id!r} 无托管账户", context={"dimension_id": dimension_id}
            )
        return account

    def _transition(
        self, dimension_id: str, target: DimensionLifecycle, *, now: datetime
    ) -> None:
        """按提案转移表跃迁，并把状态写回**法定契约字段** ``DimensionDefinition.lifecycle``。"""
        now = _utc(now)
        record = self._record(dimension_id)
        current = record.lifecycle
        if target not in allowed_dimension_transitions(current):
            legal = sorted(t.value for t in allowed_dimension_transitions(current))
            raise IllegalLifecycleTransitionError(
                f"维度 {dimension_id!r} 从 {current.value} 到 {target.value} 非法；"
                f"提案表允许的目标为 {legal}",
                context={
                    "dimension_id": dimension_id,
                    "current": current.value,
                    "target": target.value,
                    "allowed": legal,
                },
            )
        # validate_assignment=True 的法定契约会当场校验：写进去的值必须是法定成员。
        # 状态活在契约里，所以"非法状态"根本无法被写入，而不是写入后再检查。
        record.lifecycle = target
        self._history.setdefault(dimension_id, []).append(
            {"at": now.isoformat(), "from": current.value, "to": target.value}
        )
        account = self._accounts.get(dimension_id)
        if account is not None:
            self._accounts[dimension_id] = EscrowAccount(
                dimension_id=account.dimension_id,
                quota=account.quota,
                escrowed_at=account.escrowed_at,
                lifecycle=target,
                returned_at=account.returned_at,
                history=account.history + ((now.isoformat(), target.value),),
            )

    def _escrow(self, dimension_id: str, quota: int, *, now: datetime) -> None:
        """门禁 1 的执行点：先从池里扣，扣不出就按法定动作拒绝。"""
        now = _utc(now)
        if quota <= 0:
            raise DimensionEscrowError(
                f"托管配额必须为正：{quota}", context={"dimension_id": dimension_id}
            )
        existing = self._accounts.get(dimension_id)
        if existing is not None and existing.holds_quota:
            # 重复托管会让守恒式失去意义：旧额度既没归还也没被计入新账户，
            # 池里就凭空少了一笔。必须在改动任何状态之前拦住，而不是让
            # _assert_conservation 在事后抛一个看不出成因的错。
            raise DimensionEscrowError(
                f"维度 {dimension_id!r} 已托管 {existing.quota} token；"
                "重复托管会破坏配额守恒（须先归还再托管）",
                context={"dimension_id": dimension_id, "held": existing.quota},
            )
        if quota > self._free_tokens:
            self._rejections.append(
                {
                    "at": now.isoformat(),
                    "dimension_id": dimension_id,
                    "requested": quota,
                    "free": self._free_tokens,
                    "action": self.escrow_policy["insufficient_quota_action"],
                }
            )
            raise BudgetExhaustedError(
                f"维度 {dimension_id!r} 请求托管 {quota} token，池内仅剩 {self._free_tokens}"
                f"；按法定动作 {self.escrow_policy['insufficient_quota_action']} 拒绝创建",
                context={
                    "dimension_id": dimension_id,
                    "requested": quota,
                    "free": self._free_tokens,
                    "pool": self.pool_tokens,
                    "action": self.escrow_policy["insufficient_quota_action"],
                },
            )
        self._free_tokens -= quota
        self._accounts[dimension_id] = EscrowAccount(
            dimension_id=dimension_id,
            quota=quota,
            escrowed_at=now,
            lifecycle=self._record(dimension_id).lifecycle,
            history=(
                existing.history if existing is not None else ()
            ) + ((now.isoformat(), f"escrow:{quota}"),),
        )

    def _return_quota(self, dimension_id: str, *, now: datetime, reason: str) -> int:
        """门禁 2 的执行点：归还托管配额。**幂等** —— 已归还的账户再归还返回 0。

        幂等不是便利，是守恒的前提：若归还可重复执行，池里就会凭空多出配额，
        守恒式当场破裂。
        """
        now = _utc(now)
        account = self._account(dimension_id)
        if not account.holds_quota:
            return 0
        returned = account.quota
        self._free_tokens += returned
        self._accounts[dimension_id] = EscrowAccount(
            dimension_id=account.dimension_id,
            quota=0,
            escrowed_at=account.escrowed_at,
            lifecycle=account.lifecycle,
            returned_at=now,
            history=account.history + ((now.isoformat(), f"return:{returned}:{reason}"),),
        )
        return returned

    # -- 生命周期 ----------------------------------------------------------

    def register_candidate(
        self, definition: DimensionDefinition, *, now: datetime
    ) -> EscrowAccount:
        """注册一个 CANDIDATE 维度。此刻**不托管配额**（尚未申请创建权）。

        记录与账户从此只增不减：门禁 3 的"绝不删除"从这里开始生效。
        """
        now = _utc(now)
        if definition.lifecycle is not DimensionLifecycle.CANDIDATE:
            raise DimensionEscrowError(
                f"入册时 lifecycle 必须是 {DimensionLifecycle.CANDIDATE.value}，"
                f"收到 {definition.lifecycle.value}",
                context={"dimension_id": definition.object_id},
            )
        if definition.object_id in self._records:
            raise DimensionEscrowError(
                f"维度 {definition.object_id!r} 已在册（含终态维度）；"
                "终态维度禁复活，但记录永存",
                context={"dimension_id": definition.object_id},
            )
        self._records[definition.object_id] = definition
        self._history.setdefault(definition.object_id, []).append(
            {"at": now.isoformat(), "from": None, "to": DimensionLifecycle.CANDIDATE.value}
        )
        self._accounts[definition.object_id] = EscrowAccount(
            dimension_id=definition.object_id,
            quota=0,
            escrowed_at=now,
            lifecycle=DimensionLifecycle.CANDIDATE,
            history=((now.isoformat(), "registered"),),
        )
        self._assert_conservation()
        return self._accounts[definition.object_id]

    def promote_to_trial(
        self, dimension_id: str, *, monthly_token_quota: int, now: datetime
    ) -> EscrowAccount:
        """门禁 1：CANDIDATE → TRIAL，**先托管后晋升**。

        顺序是法律本身：若先晋升再托管，那么在"已晋升但未托管"的窗口里，
        一个没有预算的维度已经在世界里存在并可能开始花钱 —— 那正是政策
        ``evidence`` 行所说的"创建权无预算托管"。
        """
        self._escrow(dimension_id, monthly_token_quota, now=now)
        try:
            self._transition(dimension_id, DimensionLifecycle.TRIAL, now=now)
        except IllegalLifecycleTransitionError:
            # 跃迁失败必须把刚托管的配额退回，否则守恒式虽成立、额度却被死锁。
            self._return_quota(dimension_id, now=now, reason="transition_failed_rollback")
            self._assert_conservation()
            raise
        self._assert_conservation()
        return self._account(dimension_id)

    def promote_to_active(self, dimension_id: str, *, now: datetime) -> None:
        """TRIAL → ACTIVE。配额继续托管（维度正在花钱）。"""
        self._transition(dimension_id, DimensionLifecycle.ACTIVE, now=now)
        self._assert_conservation()

    def reject(self, dimension_id: str, *, now: datetime, reason: str = "") -> int:
        """→ REJECTED，并归还托管配额。终态，但**记录永存**。"""
        returned = self._return_quota(dimension_id, now=now, reason=f"rejected:{reason}")
        self._transition(dimension_id, DimensionLifecycle.REJECTED, now=now)
        self._assert_conservation()
        return returned

    def mark_low_activity(self, dimension_id: str, *, now: datetime) -> None:
        """门禁 3：低频**先降级**，不删除（§75 低频不等于无价值）。"""
        self._transition(dimension_id, DimensionLifecycle.LOW_ACTIVITY, now=now)
        self._assert_conservation()

    def send_dormant(self, dimension_id: str, *, now: datetime) -> int:
        """门禁 2：→ DORMANT 并**归还配额**。返回归还的 token 数。

        这是棘轮的刹车片：低频维度不删除（门禁 3），但也不再占预算。
        两者必须同时成立 —— 只禁删不归还就是纯棘轮，只归还可删就丢了 §75。
        """
        returned = self._return_quota(dimension_id, now=now, reason="dormant")
        self._transition(dimension_id, DimensionLifecycle.DORMANT, now=now)
        self._assert_conservation()
        return returned

    def reactivate(
        self, dimension_id: str, *, monthly_token_quota: int, now: datetime
    ) -> EscrowAccount:
        """DORMANT → REACTIVATED，**重新托管**配额（复活不是免费的）。"""
        self._transition(dimension_id, DimensionLifecycle.REACTIVATED, now=now)
        try:
            self._escrow(dimension_id, monthly_token_quota, now=now)
        except BudgetExhaustedError:
            # 托管失败则把状态退回 DORMANT，否则会出现"已复活但无预算"的维度。
            self._transition(dimension_id, DimensionLifecycle.DORMANT, now=now)
            self._assert_conservation()
            raise
        self._assert_conservation()
        return self._account(dimension_id)

    def merge_into(self, dimension_id: str, target_id: str, *, now: datetime) -> int:
        """→ MERGED 并归还配额（§76 维度不能无限爆炸的正面手段）。"""
        self._record(target_id)
        returned = self._return_quota(dimension_id, now=now, reason=f"merged_into:{target_id}")
        self._transition(dimension_id, DimensionLifecycle.MERGED, now=now)
        self._history[dimension_id].append(
            {"at": _utc(now).isoformat(), "merged_into": target_id}
        )
        self._assert_conservation()
        return returned

    # -- 门禁 4：共振对与跨域突触 ------------------------------------------

    def add_resonance_pair(self, left: str, right: str, *, window_id: str) -> bool:
        """登记一对共振。超出 ``resonance_pair_cap_per_window`` 即拒，换窗重置。

        无序对：(a,b) 与 (b,a) 是同一对。若按有序处理，上限会被无声地翻倍，
        而 O(D²) 的 D² 项恰好来自无序对数 D(D-1)/2。
        """
        if left == right:
            raise DimensionEscrowError(
                f"维度 {left!r} 不得与自身共振", context={"dimension_id": left}
            )
        self._record(left)
        self._record(right)
        pair = (left, right) if left < right else (right, left)
        window = self._resonance.setdefault(window_id, set())
        if pair in window:
            return True  # 幂等：同一窗内重复登记不占第二个名额
        if len(window) >= self.resonance_cap:
            self._rejections.append(
                {
                    "window_id": window_id,
                    "pair": list(pair),
                    "cap": self.resonance_cap,
                    "reason": "resonance_pair_cap_per_window",
                }
            )
            raise ResonanceCapExceededError(
                f"窗口 {window_id!r} 的共振对已达法定上限 {self.resonance_cap}，"
                f"拒绝 {pair[0]!r}↔{pair[1]!r}",
                context={"window_id": window_id, "pair": list(pair), "cap": self.resonance_cap},
            )
        window.add(pair)
        return True

    def add_synapse(self, source: str, target: str) -> bool:
        """登记一条跨域突触，扇入与扇出都受法定上限约束。

        上限的意义不是省内存：一个扇入/扇出无界的枢纽维度一旦形成，任何一次修正
        都会沿它扇出成雪崩 —— 这正是 M3 里程碑"依赖雪崩隔离"要防的东西。
        """
        if source == target:
            raise DimensionEscrowError(
                f"维度 {source!r} 不得与自身建立突触", context={"dimension_id": source}
            )
        self._record(source)
        self._record(target)
        edge = (source, target)
        if edge in self._synapses:
            return True  # 幂等
        fanout = sum(1 for s, _ in self._synapses if s == source)
        fanin = sum(1 for _, t in self._synapses if t == target)
        if fanout >= self.fanout_max:
            raise SynapseFanCapExceededError(
                f"维度 {source!r} 的扇出已达法定上限 {self.fanout_max}",
                context={"dimension_id": source, "fanout": fanout, "cap": self.fanout_max},
            )
        if fanin >= self.fanin_max:
            raise SynapseFanCapExceededError(
                f"维度 {target!r} 的扇入已达法定上限 {self.fanin_max}",
                context={"dimension_id": target, "fanin": fanin, "cap": self.fanin_max},
            )
        self._synapses.add(edge)
        return True

    # -- 门禁 3：只读观测面（无删除路径） ----------------------------------

    def lifecycle_of(self, dimension_id: str) -> DimensionLifecycle:
        """当前生命周期状态 —— 直接读**法定契约字段**，不是本模块的私有副本。"""
        return self._record(dimension_id).lifecycle

    def record_of(self, dimension_id: str) -> DimensionDefinition:
        """维度记录本体。终态维度同样可查（门禁 3）。"""
        return self._record(dimension_id)

    def history_of(self, dimension_id: str) -> list[Dict[str, Any]]:
        """完整变迁史，只增不减。"""
        self._record(dimension_id)
        return list(self._history.get(dimension_id, []))

    def registered_ids(self) -> tuple[str, ...]:
        """曾经注册过的**全部**维度 id，含 REJECTED / MERGED / DORMANT。"""
        return tuple(self._records)

    def quota_of(self, dimension_id: str) -> int:
        return self._account(dimension_id).quota

    def resonance_pairs_in(self, window_id: str) -> int:
        return len(self._resonance.get(window_id, ()))

    def fanin_of(self, dimension_id: str) -> int:
        return sum(1 for _, t in self._synapses if t == dimension_id)

    def fanout_of(self, dimension_id: str) -> int:
        return sum(1 for s, _ in self._synapses if s == dimension_id)

    def audit(self) -> Dict[str, Any]:
        """托管器自记账。``conservation_holds`` 恒应为 True。"""
        escrowed = sum(a.quota for a in self._accounts.values() if a.holds_quota)
        by_state: Dict[str, int] = {}
        for record in self._records.values():
            by_state[record.lifecycle.value] = by_state.get(record.lifecycle.value, 0) + 1
        return {
            "pool_tokens": self.pool_tokens,
            "free_tokens": self._free_tokens,
            "escrowed_tokens": escrowed,
            "conservation_holds": self._free_tokens + escrowed == self.pool_tokens,
            "dimensions_registered": len(self._records),
            "dimensions_by_lifecycle": by_state,
            "quota_returning_events": sum(
                1 for a in self._accounts.values() if a.returned_at is not None
            ),
            "resonance_cap_per_window": self.resonance_cap,
            "resonance_windows": {k: len(v) for k, v in self._resonance.items()},
            "synapse_fanin_max": self.fanin_max,
            "synapse_fanout_max": self.fanout_max,
            "synapses": len(self._synapses),
            "rejections": len(self._rejections),
            "rejection_log": list(self._rejections),
        }
