"""M2-001 · 主动心跳唤醒调度 + Step-0 安全便利闸门 + 反馈冷却队列

模块边界与命名（**读代码前必看**）
--------------------------------
工单点名的落地路径是 ``wake/cooldown_queue.py``。但该路径已被并行线的 M2-001
实现占据，且已在远端赛马裁决中被采信；用户的常设指令是"**不要覆盖任何别的文件**"。
两条硬约束相撞时，常设指令优先，故本模块落在同包的独立文件里，**对既有文件零改动**
（``cooldown_queue.py`` 与远端逐字节一致，md5 已核验）。

两者范围不同且互补，不是竞争关系，因此分文件本身就是正确的，不只是妥协：

=========================  ====================================  ====================================
　                         ``wake/cooldown_queue.py``（并行线）    本文件
=========================  ====================================  ====================================
方向                        **入站**：高频唤醒事件风暴              **出站**：AI 主动心跳
机制                        5s 防抖合并窗、15→30min 自适应          Step-0 四段机械闸、候选唤醒/节奏炸弹、
                            冷却阶梯、DEEP_SLEEP 绝对静默、          反馈硬冷却、节律学习变更日志
                            晨间无损延递聚合
法律锚                      §11 分寸感 / 铁律 3（P0 硬旁路）        ``heartbeat`` + ``step0_safety_gate``
                                                                    政策段（ADJ-001 §1 / ADJ-002）
=========================  ====================================  ====================================

**在并行线文件里发现的一处红线缺陷（须交治理裁决，本模块不代改）**：
它在模块内自定义了 ``class WakePriority(str, Enum)``，成员为
``P0_CRITICAL_SAFETY`` 与 ``NORMAL`` —— 而法定 ``contracts.safety_bypass.WakePriority``
已有 ``P0_CRITICAL_SAFETY / P1_URGENT_TASK / P2_NORMAL_INTERACT / P3_BACKGROUND_TICK``
四级。这是**同名双枚举**：本仓库的 ``ObjectType`` / ``ObjectTypeV3`` 双枚举曾导致
v3 扩展类型完全无法落盘，是已经付过学费的缺陷类。``NORMAL`` 在法定枚举里没有对应
成员（语义上应是 ``P2_NORMAL_INTERACT``），因此跨模块传递优先级时必然要么丢信息、
要么静默错配。本模块一律使用法定枚举，并在测试里钉住这一选择；修正方向有两条，
须由治理择一：把 ``NORMAL`` 提升为法定成员（一级治理变更），或把并行线迁移到
``P2_NORMAL_INTERACT``。

本文件是唤醒侧三件套的合流点。三者写在同一个模块里不是图省事，而是因为它们
共享**同一条不可分割的不变量**：

    任何一次面向用户的出声，必须同时通过 Step-0 闸门、冷却去重队列，
    并且持有非空的候选触发器证据；三者缺一，物理上就到不了用户面前。

把它们拆成三个模块，就等于允许调用方只挑其中一个来用 —— 那正是"主动服务变成
骚扰"的经典成因。合流之后，:class:`HeartbeatScheduler.deliver` 是唯一的出声出口，
而它要求三张凭证同时到位。

政策权威
--------
一律**引用** ``governance/runtime_policy.json`` 的 ``heartbeat`` /
``step0_safety_gate`` / ``token_budget`` / ``delivery_fsm`` 四段，不复制常量。
与 M2-005R 同一条纪律：校验在**文件路径与注入路径上都执行**（见
:func:`validate_policy_section`），只在读文件时校验等于给
``HeartbeatScheduler(policy=...)`` 留一条绕过法律的口子。

四大硬门禁的落点
----------------
**门禁 1 · 心跳触发 100% 带候选触发器**
心跳产出的是 :class:`CandidateWake`，其 ``trigger`` 字段是 :class:`CandidateTrigger`。
``trigger is None`` 的唤醒在**构造边界与投递边界各拒一次**
（:exc:`MissingCandidateTriggerError`）。触发器种类不新造枚举：政策
``heartbeat.trigger_kind_name = "RELATIONSHIP_RHYTHM_CANDIDATE"`` 的法定载体是
既有的 ``WakeSourceV3.RELATION_RHYTHM``（政策 ``$name_note`` 明文要求用法定名
"以免再造编号漂移"），本模块把这条映射写成**单一常量**
:data:`TRIGGER_KIND_LEGAL_NAME` 并加守卫测试，杜绝第二处各写各的。

**门禁 2 · Step-0 在任何模型调用之前执行，``model_calls == 0``**
:class:`Step0SafetyGate` 全模块**没有任何模型/LLM 适配器参数**，因此"叫模型"在
结构上不可能发生，而不只是"当前实现没叫"。它接收外部传入的
:class:`ModelCallMeter`（本模块自持，见下方"计量器归属"说明），只读不写；测试断言跑完 30 个虚拟日后 ``meter.model_calls == 0``，
并用源码 grep 断言本模块内 ``meter.charge(`` 调用点数为 **0**。

**门禁 3 · 便利闸门有最终否决权，QUIET 降级为静默巡检并留痕**
政策 ``step0_convenience_check_has_final_veto`` / ``candidate_wake_downgrades_to_
silent_patrol_on_QUIET`` / ``cancelled_heartbeat_must_still_log_silent_patrol``。
每一次未出声的心跳都产出一条 :class:`SilentPatrolRecord`（可审计、非空），
所以"被闸门取消"与"根本没跑"在审计上是可区分的 —— 静默失效一律非法。

**门禁 4 · 7 天平稳数据下固定节奏炸弹数 = 0；安全触发与绝对底线永不被压制**
政策 ``fixed_rhythm_bomb_count_under_7d_stable_data = 0`` 是**可判定的反面指标**：
系统一切正常、用户没有内心数据流入时，AI 不得为了维持节律而出声。落点是
``CandidateTrigger.evidence_refs`` 为空 ⇒ 该唤醒的**唯一**正当理由就是节奏时钟
⇒ 判定为节奏炸弹 ⇒ 闸门 QUIET。审计里 ``rhythm_bombs_delivered`` 恒为 0。
反面是 :data:`ABSOLUTE_FLOOR_CHANNELS`：``safety_trigger_never_suppressed_by_gate_
or_cooldown`` 与 ``absolute_floor_not_subject_to_rhythm_learning`` 使生命安全值守
与已登记的自我承诺任务（药物、复检）**穿透闸门与冷却**（红线 31：安全便利优先于
token 预算 —— 故安全触发连 ``d_budget_gate`` 一并穿透，并在 ``overrides`` 落字）。

红线 25「绝不承诺」的类型化落地
------------------------------
``candidate_wake_not_promise_to_speak`` 是一条语义降级：触发 ≠ 必须打扰。把它写成
文档约定等于没写，所以 :class:`CandidateWake.promises_delivery` 的类型是
``Literal[False]`` —— **"承诺出声"在类型系统里不可表达**，传 ``True`` 直接被
pydantic 拒绝。这比"记得不要承诺"强一个数量级：违宪状态根本无法被构造出来。

有意不做 / 尚未入法
------------------
* **冷却时长与去重窗口没有法定数值。** 政策只给了定性硬约束
  ``feedback_cooldown_is_hard_constraint = true``，全文搜不到任何秒数。因此
  :data:`PROPOSED_FEEDBACK_COOLDOWNS` 与 :data:`PROPOSED_DEDUP_WINDOW_SECONDS`
  明确标注为**本模块提出的提案，须先提交治理批准**，不是法律。真正被强制的是
  与数值无关的**序关系**：``rejected``/``suspended`` 的冷却必须**严格长于**
  ``accepted``（:meth:`CooldownQueue.assert_cooldown_ordering`），这条不依赖提案
  数值成立，因此可以先入测试。
* **心跳间隔 3~5 小时是出厂默认，不是铁律。** 政策
  ``interval_hours_is_factory_default_not_law = true`` +
  ``interval_is_learnable_secondary_governance_parameter = true``（ADJ-008 归入
  二级治理参数）。:meth:`HeartbeatScheduler.learn_interval` 按
  ``threshold_governance.change_log_fields`` 的**八个法定字段**逐字产出可回放、
  可回滚的变更条目；本模块**不自行决定**学到的值是否合法，只保证每一步都留痕。
  注意：该参数目前**尚未**登记进 ``governance/thresholds/baseline_v1.json``，
  出厂默认仍取自 ``heartbeat.interval_hours_factory_default``；上线学习前必须先
  完成 THRESH 登记，否则 ``prev_value`` 无权威来源。

复用的既有法定构件（不重复实现）
------------------------------
``contracts.enums_v3.SafetyVerdict`` / ``TriState`` / ``WakeSourceV3``、
``contracts.models_v3.SafetyGateVerdict``（Step-0 结论的**法定物化载体**，
``ManifestInstance.step0_safety`` 是必填字段，没有它看板根本无法装配）、
``contracts.enums.WakeState``（NEW/QUEUED/MERGED/SUPPRESSED）、
``contracts.safety_bypass.WakePriority``、``contracts.enums.ErrorCode.
BUDGET_EXHAUSTED``、
``wake.dispatcher.dispatch_wake_event``（P0 生命安全 0 延迟硬件穿透，本模块不
另造第二条投递路径）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Final, Iterable, Literal, Mapping, Sequence

from pydantic import ValidationError

from aios_core.contracts.enums import ErrorCode, WakeSource, WakeState
from aios_core.contracts.enums_v3 import SafetyVerdict, TriState, WakeSourceV3
from aios_core.contracts.models_v3 import SafetyGateVerdict
from aios_core.contracts.safety_bypass import SafetyBypassPayload, WakePriority
from aios_core.errors import AIOSProtocolError
from aios_core.wake.dispatcher import dispatch_wake_event

__all__ = [
    "ABSOLUTE_FLOOR_CHANNELS",
    "PROPOSED_DEDUP_WINDOW_SECONDS",
    "PROPOSED_FEEDBACK_COOLDOWNS",
    "TRIGGER_KIND_LEGAL_NAME",
    "BeatOutcome",
    "BudgetExhaustedError",
    "BudgetLedger",
    "CandidateTrigger",
    "CandidateWake",
    "CooldownQueue",
    "GateDecision",
    "GateSignals",
    "HeartbeatScheduler",
    "MissingCandidateTriggerError",
    "ModelCallMeter",
    "PromiseToSpeakError",
    "QueueDecision",
    "SilentPatrolRecord",
    "Step0SafetyGate",
    "ThresholdChangeEntry",
    "WakeError",
    "load_heartbeat_policy",
    "load_runtime_policy",
    "load_step0_policy",
    "validate_policy_section",
]


_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_POLICY_PATH: Final[Path] = _REPO_ROOT / "governance" / "runtime_policy.json"

#: 政策 ``heartbeat.trigger_kind_name`` → 法定枚举成员的**单一**映射。
#: 写在常量里而不是散落在各处字符串比较中，是为了让"第七种触发器"只有一个法定名。
#:
#: **为什么这里有两条而不是一条**：两条政策谱系对同一个触发器各写了一个名，且对"哪个是
#: 旧名"的判定完全相反 —— 本线 v1.1.0 依 ADJ-002/ADJ-003 把 ``LONG_STABLE_HEARTBEAT``
#: 记为已作废的自拟名并改用 ``RELATIONSHIP_RHYTHM_CANDIDATE``；主干压平提交 582e187 的
#: 谱系从未收到该裁决，仍用 ``LONG_STABLE_HEARTBEAT``，并由其政策测试 L655 钉死。
#: 政策 v1.4.0 并集取了主干值（详见政策 ``heartbeat.$name_collision_note``），本模块同时
#: 登记两种拼写，**且都映射到同一个法定成员** ``RELATION_RHYTHM``。
#:
#: 这不是放宽守卫：守卫的目的是禁止自拟**第七种触发器**，而两种拼写指向的是同一个法定
#: 载体，运行时行为逐位相同 —— 有测试钉住二者映射恒等，别名不可能悄悄变成新触发器。
#: 未登记的名字仍然一律拒绝（fail-closed），:meth:`HeartbeatScheduler.__init__` 会抛
#: :class:`WakeError` 而不是猜一个枚举成员。
TRIGGER_KIND_LEGAL_NAME: Final[Dict[str, WakeSourceV3]] = {
    "LONG_STABLE_HEARTBEAT": WakeSourceV3.RELATION_RHYTHM,
    "RELATIONSHIP_RHYTHM_CANDIDATE": WakeSourceV3.RELATION_RHYTHM,
}

#: ``heartbeat.absolute_floor_not_subject_to_rhythm_learning`` 的法定值。
#: 这里写成常量只为给类型注解与守卫测试一个稳定引用；**运行时判定一律读政策**，
#: 政策改了而常量没改，:func:`_assert_floor_channels_match_policy` 会立刻失败。
ABSOLUTE_FLOOR_CHANNELS: Final[frozenset[str]] = frozenset(
    {"personal_safety_watch_channel", "registered_self_commitment_tasks"}
)

#: 提案，**尚未入法**：反馈冷却时长（秒）。政策只规定冷却是硬约束，未给数值。
PROPOSED_FEEDBACK_COOLDOWNS: Final[Dict[str, int]] = {
    "accepted": 3 * 3600,
    "ignored": 12 * 3600,
    "rejected": 72 * 3600,
    "suspended": 7 * 24 * 3600,
}

#: 提案，**尚未入法**：同源唤醒的去重合并窗口（秒）。
PROPOSED_DEDUP_WINDOW_SECONDS: Final[int] = 30 * 60


# ---------------------------------------------------------------------------
# 政策引用与校验
# ---------------------------------------------------------------------------


class WakeError(AIOSProtocolError):
    """唤醒侧统一错误族。

    ``ErrorCode`` 没有 ``ILLEGAL_STATE``，故所有"状态不该如此"的失败统一走
    ``INVALID_ARGUMENT``（与 M2-005R 同一处置，避免为造错误码而改法定枚举）。
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
        context: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, context=context)


class MissingCandidateTriggerError(WakeError):
    """门禁 1：心跳唤醒不带候选触发器 —— 拒绝唤醒。"""


class PromiseToSpeakError(WakeError):
    """红线 25：候选唤醒被当成"承诺出声"使用。"""


class BudgetExhaustedError(WakeError):
    """Step-0 §1(d) 预算闸门：超额。使用法定 ``BUDGET_EXHAUSTED``。"""

    def __init__(self, message: str, *, context: Dict[str, Any] | None = None) -> None:
        super().__init__(message, code=ErrorCode.BUDGET_EXHAUSTED, context=context)


@dataclass(slots=True)
class ModelCallMeter:
    """模型调用与 token 计量器 —— "叫没叫模型"这条门禁的**唯一**可观测证据。

    **计量器归属（一次被迫的变更，记录在案）**：本类原先复用
    ``scheduler.conditional_engine.ModelCallMeter``（M2-005R 的产物），不新造。主干在
    M5 之前的压平提交里换上了另一套 ``conditional_engine`` 实现，其中**不再有**这个
    符号，导致本模块 import 即崩。这里把计量器收回本模块自持，理由有三：

    1. 门禁 2 的判据是 ``model_calls == 0``，它的证据出口必须存在且唯一；出口随别人
       的文件改名而消失，等于门禁失效。
    2. 本模块与 ``conditional_engine`` 并无逻辑耦合 —— 只用它当一个计数器。为一个计数器
       绑定一条争议中的实现线，是把自己交给不确定的上游。
    3. 全仓检索确认除本模块与其测试外无第二处使用 ``ModelCallMeter``，因此就地定义
       不产生第二份口径。

    若主干将来重新提供同名计量器，应以主干为准并把本类改为转调，不要两份并存。
    """

    model_calls: int = 0
    tokens: int = 0
    call_log: list = field(default_factory=list)

    def charge(self, *, lane: str, tokens: int, reason: str) -> None:
        """记一次模型调用。**本模块从不调用它**（门禁 2），调用点数为 0 有测试钉住。"""
        if tokens < 0:
            raise WakeError(f"token 计量不得为负：{tokens}")
        self.model_calls += 1
        self.tokens += tokens
        self.call_log.append((lane, tokens, reason))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "tokens": self.tokens,
            "call_log": list(self.call_log),
        }


def load_runtime_policy() -> Dict[str, Any]:
    """读取整份 ``runtime_policy.json``。唯一权威来源，不复制常量。"""
    if not _POLICY_PATH.exists():
        raise WakeError(f"找不到法定政策文件：{_POLICY_PATH}")
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def validate_policy_section(
    section_name: str,
    section: Any,
    required_fields: Sequence[str],
    *,
    required_true: Sequence[str] = (),
) -> Dict[str, Any]:
    """校验一段政策：字段必须存在，且 ``required_true`` 里的布尔字段必须为真。

    **文件路径与注入路径都必须过这一关**。这是 M2-005R 被自己的测试抓出来的真 bug
    （初版只在读文件时校验，``policy=...`` 注入即绕过），此处直接沿用修好的形状。

    ``required_true`` 承载的是那些"取值本身就是法律"的开关，例如
    ``mechanical_gate_before_llm`` / ``runs_before_any_mental_step`` /
    ``candidate_wake_not_promise_to_speak`` / ``model_calls == 0``。把它们判为
    False 的政策等于一份违宪政策，引擎必须拒绝带着它运行，而不是静默降级。
    """
    if not isinstance(section, dict):
        raise WakeError(f"政策段 {section_name!r} 必须是对象")
    for key in required_fields:
        if key not in section:
            raise WakeError(f"政策段 {section_name} 缺少法定字段 {key!r}")
    for key in required_true:
        value = section.get(key)
        expected = 0 if key == "model_calls" else True
        if value is not expected:
            raise WakeError(
                f"政策段 {section_name}.{key} 法定值为 {expected!r}，实际为 {value!r}"
                " —— 拒绝带着漂移的法律参数运行"
            )
    return dict(section)


def load_heartbeat_policy(policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """读取并校验 ``heartbeat`` 段。"""
    root = dict(policy) if policy is not None else load_runtime_policy()
    return validate_policy_section(
        "heartbeat",
        root.get("heartbeat"),
        required_fields=(
            "trigger_kind_name",
            "interval_hours_factory_default",
            "gate_predicates",
            "gate_cancel_target_share",
            "feedback_signals_for_frequency_adaptation",
            "absolute_floor_not_subject_to_rhythm_learning",
        ),
        required_true=(
            "is_seventh_trigger_kind",
            "interval_hours_is_factory_default_not_law",
            "candidate_wake_not_promise_to_speak",
            "step0_convenience_check_has_final_veto",
            "candidate_wake_downgrades_to_silent_patrol_on_QUIET",
            "mechanical_gate_before_llm",
            "night_work_driving_sleep_windows_default_to_silent",
            "safety_trigger_never_suppressed_by_gate_or_cooldown",
            "feedback_cooldown_is_hard_constraint",
            "cancelled_heartbeat_must_still_log_silent_patrol",
        ),
    )


def load_step0_policy(policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """读取并校验 ``step0_safety_gate`` 段。"""
    root = dict(policy) if policy is not None else load_runtime_policy()
    section = validate_policy_section(
        "step0_safety_gate",
        root.get("step0_safety_gate"),
        required_fields=(
            "checks",
            "verdicts",
            "hard_block_still_allows",
        ),
        required_true=(
            "runs_before_any_mental_step",
            "deterministic_rules_only",
            "hard_block_prohibits_external_delivery",
            "verdicts_materialized_into_session_audit",
            "hidden_chain_of_thought_substitute_prohibited",
        ),
    )
    if section.get("model_calls") != 0:
        raise WakeError(
            f"step0_safety_gate.model_calls 法定值为 0，实际为 "
            f"{section.get('model_calls')!r} —— Step-0 必须是纯机械闸"
        )
    checks = section["checks"]
    for key in ("a_safety_hard_signal", "b_convenience_mechanical"):
        value = checks.get(key)
        if not isinstance(value, list) or not value:
            raise WakeError(f"step0_safety_gate.checks.{key} 必须是非空列表")
    # 陷阱：裁决名在本仓库里有**两种大小写表示**，且都是法定的 ——
    #   SafetyVerdict.OK.name == "OK"（= SafetyGateVerdict.convenience 的 Literal）
    #   SafetyVerdict.OK.value == "ok"（= 落盘/线格式的字符串值）
    # 政策 step0_safety_gate.verdicts 用的是**大写 name**。拿 .value 去比会必然失配，
    # 而这种失配看起来像"政策漂移"，实际是自己比错了字段 —— 所以这里显式写明比的是 name。
    legal_names = {v.name for v in SafetyVerdict}
    if set(section["verdicts"]) != legal_names:
        raise WakeError(
            f"step0_safety_gate.verdicts 必须与法定 SafetyVerdict 的**名称**完全一致："
            f"{sorted(section['verdicts'])!r} vs {sorted(legal_names)!r}"
        )
    return section


def load_token_budget_policy(policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """读取并校验 ``token_budget`` 段（Step-0 §1(d) 预算闸门的法定上限来源）。"""
    root = dict(policy) if policy is not None else load_runtime_policy()
    section = validate_policy_section(
        "token_budget",
        root.get("token_budget"),
        required_fields=("monthly_total_cap", "daily_total_cap", "subsystems"),
    )
    heartbeat = section["subsystems"].get("heartbeat")
    if not isinstance(heartbeat, dict) or "monthly_cap" not in heartbeat:
        raise WakeError("token_budget.subsystems.heartbeat.monthly_cap 缺失")
    return section


def _validated_section(loader: Any, section: Any, section_name: str) -> Dict[str, Any]:
    """把"注入一个政策段"归一成"注入一份合成 root"，再走**同一个** loader。

    注入路径若走另一套校验，就等于给测试/调用方留了一条弱校验的后门 ——
    M2-005R 已经栽过一次（初版 ``__init__`` 对注入的政策完全不校验）。
    """
    if section is None:
        return loader()
    return loader({section_name: section})


def _assert_floor_channels_match_policy(heartbeat_policy: Mapping[str, Any]) -> None:
    """守卫：本模块的 :data:`ABSOLUTE_FLOOR_CHANNELS` 常量必须与政策逐字一致。

    常量存在的意义是给类型注解和测试一个稳定引用，但**运行时判定读政策**。
    这条断言把两者的漂移变成硬失败，而不是让常量悄悄过期。
    """
    legal = frozenset(heartbeat_policy["absolute_floor_not_subject_to_rhythm_learning"])
    if legal != ABSOLUTE_FLOOR_CHANNELS:
        raise WakeError(
            "absolute_floor_not_subject_to_rhythm_learning 与 ABSOLUTE_FLOOR_CHANNELS "
            f"漂移：政策={sorted(legal)} 常量={sorted(ABSOLUTE_FLOOR_CHANNELS)}"
        )


def _utc(moment: datetime) -> datetime:
    """把 naive datetime 一律当 UTC 解释，避免虚拟时钟里混入本地时区。"""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 候选触发器 / 候选唤醒
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CandidateTrigger:
    """候选触发器：心跳出声的**唯一**正当理由（门禁 1）。

    ``evidence_refs`` 为空意味着这次唤醒除了节奏时钟之外**没有任何实质理由**，
    即政策所说的"固定节奏炸弹"。判定放在数据上而不是放在调度器的 if 里，
    是为了让 :attr:`is_rhythm_bomb` 成为一处可被审计、可被测试的单一真相。
    """

    trigger_id: str
    detected_at: datetime
    kind: WakeSourceV3 = WakeSourceV3.RELATION_RHYTHM
    evidence_refs: tuple[str, ...] = ()
    dimension_id: str | None = None
    floor_channel: str | None = None

    def __post_init__(self) -> None:
        if not self.trigger_id:
            raise WakeError("CandidateTrigger.trigger_id 不得为空")
        if self.floor_channel is not None and self.floor_channel not in ABSOLUTE_FLOOR_CHANNELS:
            raise WakeError(
                f"未知的绝对底线通道 {self.floor_channel!r}；法定值为 "
                f"{sorted(ABSOLUTE_FLOOR_CHANNELS)}"
            )

    @property
    def is_rhythm_bomb(self) -> bool:
        """无证据 ⇒ 纯节奏驱动 ⇒ 政策要求 7 天平稳数据下此类出声数为 0。"""
        return not self.evidence_refs

    @property
    def is_absolute_floor(self) -> bool:
        """生命安全值守 / 已登记自我承诺任务：不受节律学习与冷却压制。"""
        return self.floor_channel is not None


@dataclass(frozen=True, slots=True)
class CandidateWake:
    """候选唤醒 —— **不是承诺出声**（ADJ-002 §2 / 红线 25）。

    ``promises_delivery`` 用**两层**把"承诺出声"做成无法构造的状态，而不是"文档里
    写了不要这样"：

    * 静态层：类型是 ``Literal[False]``，类型检查器在调用点就拒绝 ``True``。
    * 运行层：``__post_init__`` 抛 :exc:`PromiseToSpeakError`。

    两层都必须有，因为这是 ``@dataclass`` 而非 pydantic 模型 —— dataclass **不校验
    注解**，只写 ``Literal[False]`` 等于只挡得住静态检查，运行时传 ``True`` 会静默
    通过。而运行层刻意抛领域错误（点名红线 25）而不是泛化的 ``ValidationError``：
    违宪时要能一眼看出违的是哪一条。
    """

    wake_id: str
    source: WakeSourceV3 | WakeSource
    created_at: datetime
    trigger: CandidateTrigger | None = None
    priority: WakePriority = WakePriority.P3_BACKGROUND_TICK
    projected_tokens: int | None = None
    #: P0 生命安全穿透所需的法定载荷。既有 ``dispatch_wake_event`` 在 P0 分支会读
    #: ``wake.safety_bypass.hazard_type`` 去构造 ``SafetyBypassReceipt``，而该字段
    #: **必填**。若此处留空，失败会推迟到投递那一刻才炸 —— 那是最难查的位置
    #: （已经穿过了闸门与队列）。所以改成构造期就拦。
    safety_bypass: SafetyBypassPayload | None = None
    object_id: str | None = None
    promises_delivery: Literal[False] = False

    def __post_init__(self) -> None:
        if not self.wake_id:
            raise WakeError("CandidateWake.wake_id 不得为空")
        # 门禁 1 在构造边界拒绝：没有候选触发器的心跳唤醒根本不该存在。
        # 例外只有生命安全唤醒本身（P0 硬件穿透 / source=SAFETY）—— 它不是心跳，
        # 不该被要求出示"关系节奏候选触发器"。
        is_safety_wake = (
            self.priority is WakePriority.P0_CRITICAL_SAFETY
            or self.source is WakeSource.SAFETY
        )
        if self.trigger is None and not is_safety_wake:
            raise MissingCandidateTriggerError(
                f"唤醒 {self.wake_id!r} 未携带候选触发器；心跳触发 100% 必须带触发器",
                context={"wake_id": self.wake_id, "source": str(self.source)},
            )
        if self.projected_tokens is not None and self.projected_tokens < 0:
            raise WakeError(f"projected_tokens 不得为负：{self.projected_tokens}")
        if self.promises_delivery is not False:
            raise PromiseToSpeakError(
                f"唤醒 {self.wake_id!r} 试图承诺出声；候选唤醒不是承诺出声（红线 25 / "
                "ADJ-002 §2 语义降级：触发不等于必须打扰）",
                context={"wake_id": self.wake_id, "promises_delivery": True},
            )
        if self.priority is WakePriority.P0_CRITICAL_SAFETY and self.safety_bypass is None:
            raise WakeError(
                f"P0 生命安全唤醒 {self.wake_id!r} 缺少 safety_bypass 载荷；"
                "既有 dispatch_wake_event 的硬件穿透分支必须拿到 hazard_type",
                context={"wake_id": self.wake_id, "priority": self.priority.value},
            )

    @property
    def is_safety_trigger(self) -> bool:
        """生命安全类唤醒：穿透闸门与冷却（``safety_trigger_never_suppressed``）。"""
        return (
            self.priority is WakePriority.P0_CRITICAL_SAFETY
            or self.source is WakeSource.SAFETY
            or (self.trigger is not None and self.trigger.is_absolute_floor)
        )

    def require_trigger(self) -> CandidateTrigger:
        """门禁 1 在投递边界**再拒一次**（防御纵深：构造可被绕过，投递不能）。"""
        if self.trigger is None:
            raise MissingCandidateTriggerError(
                f"唤醒 {self.wake_id!r} 无候选触发器，拒绝投递",
                context={"wake_id": self.wake_id, "boundary": "deliver"},
            )
        return self.trigger


# ---------------------------------------------------------------------------
# Step-0 机械闸门
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BudgetLedger:
    """预算账本：Step-0 §1(d) 的输入。上限一律取自 ``token_budget`` 段。

    ``projected_tokens=None`` 表示**调用方无法给出本次唤醒的花费估算**。对主动心跳
    而言这不是"当作 0"，而是"无法证明可负担"⇒ 保守 HARD_BLOCK（失败方向永远朝着
    沉默，绝不朝着打扰）。安全触发不受此限（红线 31）。
    """

    heartbeat_cap: int
    monthly_cap: int
    heartbeat_spent: int = 0
    monthly_spent: int = 0

    def over_cap(self, projected: int | None) -> tuple[bool, str | None]:
        if projected is None:
            return True, "projected_tokens_unavailable_cannot_prove_affordable"
        if self.heartbeat_spent + projected > self.heartbeat_cap:
            return True, "heartbeat_subsystem_cap_exceeded"
        if self.monthly_spent + projected > self.monthly_cap:
            return True, "monthly_total_cap_exceeded"
        return False, None


@dataclass(frozen=True, slots=True)
class GateSignals:
    """Step-0 的机械输入。全部来自传感器/时钟/日历/信道状态，**无一项需要理解语义**。

    ``flags`` 的键取自政策的检查清单（``a_safety_hard_signal`` +
    ``b_convenience_mechanical`` + ``heartbeat.gate_predicates``），因此政策新增一个
    便利判据时，闸门自动生效，不需要改代码 —— 这是"引用而非复制"的实际收益。

    取值为 :class:`TriState` 而非 ``bool``：**判不了的信号必须显式是 UNKNOWN**，
    不能伪装成 False。UNKNOWN 的便利信号一律朝沉默方向失败（QUIET）并在
    ``overrides`` 落字，绝不静默当成"方便"。
    """

    now: datetime
    flags: Mapping[str, TriState] = field(default_factory=dict)
    notification_epoch: int | None = None
    budget: BudgetLedger | None = None

    @classmethod
    def all_clear(
        cls,
        now: datetime,
        *,
        notification_epoch: int,
        budget: "BudgetLedger | None",
        step0_policy: Mapping[str, Any] | None = None,
        heartbeat_policy: Mapping[str, Any] | None = None,
    ) -> "GateSignals":
        """构造一份"全部机械判据均已**明确解析为 FALSE**"的信号集。

        为什么需要它：闸门的失败方向朝沉默（UNKNOWN ⇒ QUIET），所以调用方必须有一种
        显式方式声明"这些判据我都问过了，答案都是否"。**留空 flags 不是这个意思** ——
        留空是"我没问"，必须 QUIET。把两者的区别做成 API 而不是注释，是为了让
        "忘了填信号"永远不会伪装成"一切方便"。

        判据清单从政策读取，因此政策新增一个便利判据时，这里自动覆盖到它。
        """
        s0 = step0_policy if step0_policy is not None else load_step0_policy()
        hb = heartbeat_policy if heartbeat_policy is not None else load_heartbeat_policy()
        names = (
            tuple(s0["checks"]["a_safety_hard_signal"])
            + tuple(s0["checks"]["b_convenience_mechanical"])
            + tuple(hb["gate_predicates"])
        )
        return cls(
            now=now,
            flags={name: TriState.FALSE for name in names},
            notification_epoch=notification_epoch,
            budget=budget,
        )

    def flag(self, name: str) -> TriState:
        value = self.flags.get(name)
        return TriState.UNKNOWN if value is None else value

    def is_true(self, name: str) -> bool:
        return self.flag(name) is TriState.TRUE


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Step-0 的物化结论。

    ``verdicts_materialized_into_session_audit = true`` 且
    ``hidden_chain_of_thought_substitute_prohibited = true``：判定必须落成可审计
    的结构化记录，不得用"模型心里想过了"代替。:attr:`rules_fired` 就是那份记录，
    :meth:`audit_record` 给出 JSON 可序列化形态。
    """

    #: 法定物化载体（``ManifestInstance.step0_safety`` 的类型），不是本模块自造的结构。
    verdict: SafetyGateVerdict
    rules_fired: tuple[str, ...]
    allows: frozenset[str]
    delivery_permitted: bool
    wake_id: str

    @property
    def convenience(self) -> Literal["OK", "QUIET", "HARD_BLOCK"]:
        return self.verdict.convenience

    def audit_record(self) -> Dict[str, Any]:
        """物化进 Session 审计的记录（JSON 可序列化，禁用隐藏思维链）。"""
        return {
            "wake_id": self.wake_id,
            "verdict": self.verdict.verdict.value,
            "hard_safe_ok": self.verdict.hard_safe_ok,
            "convenience": self.verdict.convenience,
            "overrides": list(self.verdict.overrides),
            "rules_fired": list(self.rules_fired),
            "still_allows": sorted(self.allows),
            "delivery_permitted": self.delivery_permitted,
            "model_calls": 0,
        }


class Step0SafetyGate:
    """ADJ-001 Step-0：先于一切心智步骤的确定性机械闸（门禁 2）。

    **本类没有任何模型适配器参数**，所以"Step-0 叫了大模型"这件事在结构上无法发生。
    这不是"当前实现恰好没叫"，而是"接口上就没有叫的入口" —— 两者的可回归性差一个
    数量级：前者靠人守，后者靠类型守。

    优先级（严格顺序，前者一旦命中即定案）：

    0. **绝对底线**：安全触发穿透闸门与冷却，连 ``d_budget_gate`` 一并穿透
       （红线 31：安全便利优先于 token 预算），并在 ``overrides`` 逐字落原因。
    1. ``a_safety_hard_signal``（fall/impact/permission/current_interrupting_input）
       ⇒ HARD_BLOCK：正在发生的事比主动寒暄重要，此刻不许出声打扰。
    2. ``c_channel_legality``：无通知 epoch ⇒ 播放通道**物理断电** ⇒ HARD_BLOCK。
       这是 ``delivery_fsm.zero_mistrigger_legal_criterion.false_playback_without_
       epoch = 0`` 的唯一实现点，也是其不变量 I1 的闸门侧对应物。
    3. ``d_budget_gate``：超额或无法证明可负担 ⇒ HARD_BLOCK（法定码 BUDGET_EXHAUSTED）。
    4. ``b_convenience_mechanical`` + ``heartbeat.gate_predicates`` ⇒ QUIET。
    5. 未决（UNKNOWN）便利信号 ⇒ QUIET 并落字（失败方向朝沉默）。
    6. 节奏炸弹（无证据的候选触发器）⇒ QUIET 并落字（门禁 4）。
    7. 否则 OK。

    HARD_BLOCK 压倒 QUIET，因为 ``hard_block_prohibits_external_delivery``；
    但 ``hard_block_still_allows`` 里的后台静默巡检与安全值守**不受影响**
    （政策 ``$precedence_note``：这是优先级裁定，不是例外清单）。
    """

    def __init__(
        self,
        *,
        step0_policy: Mapping[str, Any] | None = None,
        heartbeat_policy: Mapping[str, Any] | None = None,
        meter: ModelCallMeter | None = None,
    ) -> None:
        self.step0_policy: Dict[str, Any] = _validated_section(
            load_step0_policy, step0_policy, "step0_safety_gate"
        )
        self.heartbeat_policy: Dict[str, Any] = _validated_section(
            load_heartbeat_policy, heartbeat_policy, "heartbeat"
        )
        _assert_floor_channels_match_policy(self.heartbeat_policy)
        #: 复用 M2-005R 的计量器：只读不写，用来**证明** Step-0 的 model_calls 为 0。
        self.meter: ModelCallMeter = meter if meter is not None else ModelCallMeter()

        checks = self.step0_policy["checks"]
        self._hard_signals: Final[tuple[str, ...]] = tuple(checks["a_safety_hard_signal"])
        self._convenience: Final[tuple[str, ...]] = tuple(checks["b_convenience_mechanical"])
        self._gate_predicates: Final[tuple[str, ...]] = tuple(
            self.heartbeat_policy["gate_predicates"]
        )
        self._allows: Final[frozenset[str]] = frozenset(
            self.step0_policy["hard_block_still_allows"]
        )

    # -- 主入口 ------------------------------------------------------------

    def evaluate(self, wake: CandidateWake, signals: GateSignals) -> GateDecision:
        """对一次候选唤醒执行 Step-0，产出物化结论。**零模型调用。**"""
        rules: list[str] = []
        overrides: list[str] = []

        # 0 · 绝对底线：安全触发永不被闸门或冷却压制
        if wake.is_safety_trigger:
            rules.append("absolute_floor_safety_trigger_bypasses_gate")
            overrides.append("safety_trigger_never_suppressed_by_gate_or_cooldown")
            overrides.append("redline31_safety_over_token_budget")
            return self._decision(
                wake, SafetyVerdict.OK, rules, overrides, delivery_permitted=True
            )

        # 门禁 1 在闸门内**第三次**拒绝（构造、投递、闸门三处，任何一处都拦得住）
        trigger = wake.require_trigger()
        rules.append(f"candidate_trigger:{trigger.kind.value}")

        # 1 · 安全硬信号
        fired_hard = [name for name in self._hard_signals if signals.is_true(name)]
        if fired_hard:
            rules.extend(f"a_safety_hard_signal:{name}" for name in fired_hard)
            overrides.extend(f"hard_signal_present:{name}" for name in fired_hard)
            return self._decision(
                wake, SafetyVerdict.HARD_BLOCK, rules, overrides, delivery_permitted=False
            )
        unresolved_hard = [
            name for name in self._hard_signals if signals.flag(name) is TriState.UNKNOWN
        ]
        if unresolved_hard:
            rules.extend(f"a_safety_hard_signal_unresolved:{n}" for n in unresolved_hard)

        # 2 · 投放信道合法性（false_playback_without_epoch = 0 的唯一实现点）
        if signals.notification_epoch is None:
            rules.append("c_channel_legality:no_notification_epoch_playback_cut_off")
            overrides.append("false_playback_without_epoch_prevented")
            return self._decision(
                wake, SafetyVerdict.HARD_BLOCK, rules, overrides, delivery_permitted=False
            )
        rules.append(f"c_channel_legality:epoch={signals.notification_epoch}")

        # 3 · 预算闸门
        if signals.budget is None:
            rules.append("d_budget_gate:ledger_absent_cannot_prove_affordable")
            overrides.append("budget_ledger_absent_fail_closed")
            return self._decision(
                wake, SafetyVerdict.HARD_BLOCK, rules, overrides, delivery_permitted=False
            )
        over, reason = signals.budget.over_cap(wake.projected_tokens)
        if over:
            rules.append(f"d_budget_gate:{reason}")
            overrides.append(f"budget_gate:{reason}")
            return self._decision(
                wake, SafetyVerdict.HARD_BLOCK, rules, overrides, delivery_permitted=False
            )
        rules.append("d_budget_gate:within_cap")

        # 4 · 便利机械判（含心跳段的 gate_predicates）
        convenience_names = self._convenience + self._gate_predicates
        fired_conv = [name for name in convenience_names if signals.is_true(name)]
        if fired_conv:
            rules.extend(f"b_convenience_mechanical:{name}" for name in fired_conv)
            overrides.extend(f"convenience_silence:{name}" for name in fired_conv)
            return self._decision(
                wake, SafetyVerdict.QUIET, rules, overrides, delivery_permitted=False
            )

        # 5 · 未决便利信号：朝沉默方向失败
        unknown_conv = [
            name for name in convenience_names if signals.flag(name) is TriState.UNKNOWN
        ]
        if unknown_conv:
            rules.extend(f"b_convenience_unresolved:{name}" for name in unknown_conv)
            overrides.extend(f"unresolved_convenience_signal:{name}" for name in unknown_conv)
            return self._decision(
                wake, SafetyVerdict.QUIET, rules, overrides, delivery_permitted=False
            )

        # 6 · 固定节奏炸弹
        if trigger.is_rhythm_bomb:
            rules.append("fixed_rhythm_bomb:no_evidence_beyond_rhythm_clock")
            overrides.append("fixed_rhythm_bomb_suppressed")
            return self._decision(
                wake, SafetyVerdict.QUIET, rules, overrides, delivery_permitted=False
            )

        # 7 · 放行
        rules.append("all_checks_passed")
        return self._decision(wake, SafetyVerdict.OK, rules, overrides, delivery_permitted=True)

    # -- 内部 --------------------------------------------------------------

    def _decision(
        self,
        wake: CandidateWake,
        verdict: SafetyVerdict,
        rules: Sequence[str],
        overrides: Sequence[str],
        *,
        delivery_permitted: bool,
    ) -> GateDecision:
        convenience: Literal["OK", "QUIET", "HARD_BLOCK"] = {
            SafetyVerdict.OK: "OK",
            SafetyVerdict.QUIET: "QUIET",
            SafetyVerdict.HARD_BLOCK: "HARD_BLOCK",
        }[verdict]
        # 法定物化载体：SafetyGateVerdict 是 ManifestInstance 的必填字段，
        # 因此 Step-0 的结论天然会成为看板的一部分，无法被丢弃。
        materialized = SafetyGateVerdict(
            verdict=verdict,
            hard_safe_ok=verdict is not SafetyVerdict.HARD_BLOCK,
            convenience=convenience,
            overrides=list(overrides),
        )
        allows = self._allows if verdict is SafetyVerdict.HARD_BLOCK else frozenset()
        if delivery_permitted and verdict is not SafetyVerdict.OK:
            # 不可达分支的硬守卫：放行与裁决不一致就是实现 bug，必须炸而不是静默。
            raise WakeError(
                f"内部不一致：verdict={verdict.value} 却 delivery_permitted=True",
                context={"wake_id": wake.wake_id},
            )
        return GateDecision(
            verdict=materialized,
            rules_fired=tuple(rules),
            allows=allows,
            delivery_permitted=delivery_permitted,
            wake_id=wake.wake_id,
        )


# ---------------------------------------------------------------------------
# 冷却与去重合并队列
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QueueDecision:
    """入队判定：NEW（新事件）/ MERGED（与在队事件同源合并）/ SUPPRESSED（冷却中）。"""

    state: WakeState
    wake_id: str
    merged_into: str | None = None
    reason: str | None = None
    cooldown_until: datetime | None = None

    def to_audit(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "wake_id": self.wake_id,
            "merged_into": self.merged_into,
            "reason": self.reason,
            "cooldown_until": (
                self.cooldown_until.isoformat() if self.cooldown_until else None
            ),
        }


@dataclass(frozen=True, slots=True)
class ThresholdChangeEntry:
    """二级治理参数的演进条目 —— 字段名逐字取自 ``threshold_governance.change_log_fields``。

    ``change_log_must_be_replayable`` / ``change_log_must_be_rollbackable`` 都要求
    这八个字段齐全；缺一个就无法回放或回滚。字段齐不齐由 :meth:`validate_against_policy`
    对着政策校验，不靠人记。
    """

    param_id: str
    prev_value: Any
    next_value: Any
    input_window: str
    learner_hash: str
    rationale: str
    applied_at: datetime
    reversible: bool

    def validate_against_policy(self, threshold_policy: Mapping[str, Any]) -> None:
        legal = tuple(threshold_policy["change_log_fields"])
        present = tuple(
            k for k in ("param_id", "prev_value", "next_value", "input_window",
                        "learner_hash", "rationale", "applied_at", "reversible")
        )
        if present != legal:
            raise WakeError(
                f"变更日志字段与法定 schema 漂移：法定={legal} 本模块={present}"
            )
        if not self.learner_hash:
            raise WakeError("learner_hash 不得为空：无法追溯是哪一版学习器做的决定")

    def to_audit(self) -> Dict[str, Any]:
        return {
            "param_id": self.param_id,
            "prev_value": self.prev_value,
            "next_value": self.next_value,
            "input_window": self.input_window,
            "learner_hash": self.learner_hash,
            "rationale": self.rationale,
            "applied_at": self.applied_at.isoformat(),
            "reversible": self.reversible,
        }


class CooldownQueue:
    """唤醒事件的冷却与去重合并队列（``wake/__init__.py`` 声明的 M2 职责）。

    两条与数值无关的硬性质，是本类真正的承重墙：

    * **冷却是硬约束**（``feedback_cooldown_is_hard_constraint``）：一旦某次出声被
      用户 ``rejected``/``suspended``，同源唤醒在冷却窗内一律 SUPPRESSED，
      调度器不得以"节律到了"为由绕过。唯一穿透者是绝对底线通道。
    * **序关系**：``rejected``/``suspended`` 的冷却必须**严格长于** ``accepted``。
      政策没给秒数，但给了方向 —— 负反馈必须比正反馈更克制。这条不等式不依赖
      提案数值，所以可以先入测试；具体秒数留待治理批准。
    """

    def __init__(
        self,
        *,
        heartbeat_policy: Mapping[str, Any] | None = None,
        cooldowns: Mapping[str, int] | None = None,
        dedup_window_seconds: int = PROPOSED_DEDUP_WINDOW_SECONDS,
    ) -> None:
        self.heartbeat_policy: Dict[str, Any] = _validated_section(
            load_heartbeat_policy, heartbeat_policy, "heartbeat"
        )
        _assert_floor_channels_match_policy(self.heartbeat_policy)
        self._legal_feedback = tuple(
            self.heartbeat_policy["feedback_signals_for_frequency_adaptation"]
        )
        # 提案数值，未入法：调用方可覆盖，但覆盖后仍受序关系约束。
        self._cooldowns: Dict[str, int] = dict(
            cooldowns if cooldowns is not None else PROPOSED_FEEDBACK_COOLDOWNS
        )
        unknown = set(self._cooldowns) - set(self._legal_feedback)
        if unknown:
            raise WakeError(
                f"冷却表出现非法反馈信号 {sorted(unknown)}；法定信号为 "
                f"{list(self._legal_feedback)}"
            )
        missing = set(self._legal_feedback) - set(self._cooldowns)
        if missing:
            raise WakeError(f"冷却表缺少法定反馈信号 {sorted(missing)}")
        self.assert_cooldown_ordering()
        if dedup_window_seconds <= 0:
            raise WakeError(f"去重窗口必须为正：{dedup_window_seconds}")
        self._dedup_window = timedelta(seconds=dedup_window_seconds)
        self._queue: Dict[str, CandidateWake] = {}
        self._cooldown_until: Dict[str, datetime] = {}
        self._suppression_log: list[Dict[str, Any]] = []

    # -- 硬性质 ------------------------------------------------------------

    def assert_cooldown_ordering(self) -> None:
        """强制"负反馈比正反馈更克制"这条**与具体秒数无关**的法定方向。"""
        accepted = self._cooldowns["accepted"]
        for signal in ("rejected", "suspended"):
            if signal in self._cooldowns and self._cooldowns[signal] <= accepted:
                raise WakeError(
                    f"反馈冷却违反硬约束：{signal}={self._cooldowns[signal]}s 必须严格长于 "
                    f"accepted={accepted}s（负反馈必须比正反馈更克制）"
                )
        if self._cooldowns["ignored"] < accepted:
            raise WakeError(
                f"反馈冷却违反方向约束：ignored={self._cooldowns['ignored']}s 不得短于 "
                f"accepted={accepted}s"
            )

    # -- 入队 --------------------------------------------------------------

    def enqueue(self, wake: CandidateWake, *, now: datetime) -> QueueDecision:
        """入队。绝对底线通道穿透冷却；同源在窗内合并。"""
        now = _utc(now)
        key = self._dedup_key(wake)

        if wake.is_safety_trigger:
            # safety_trigger_never_suppressed_by_gate_or_cooldown +
            # absolute_floor_not_subject_to_rhythm_learning
            self._queue[wake.wake_id] = wake
            return QueueDecision(
                state=WakeState.NEW,
                wake_id=wake.wake_id,
                reason="absolute_floor_bypasses_cooldown_and_dedup",
            )

        until = self._cooldown_until.get(key)
        if until is not None and now < until:
            self._suppression_log.append(
                {"wake_id": wake.wake_id, "reason": "feedback_cooldown", "now": now.isoformat()}
            )
            return QueueDecision(
                state=WakeState.SUPPRESSED,
                wake_id=wake.wake_id,
                reason="feedback_cooldown_is_hard_constraint",
                cooldown_until=until,
            )

        for queued_id, queued in self._queue.items():
            if self._dedup_key(queued) == key and now - _utc(queued.created_at) <= self._dedup_window:
                self._suppression_log.append(
                    {"wake_id": wake.wake_id, "reason": "merged", "into": queued_id}
                )
                return QueueDecision(
                    state=WakeState.MERGED,
                    wake_id=wake.wake_id,
                    merged_into=queued_id,
                    reason="same_source_within_dedup_window",
                )

        self._queue[wake.wake_id] = wake
        return QueueDecision(state=WakeState.NEW, wake_id=wake.wake_id)

    def record_feedback(
        self, wake: CandidateWake, signal: str, *, now: datetime
    ) -> ThresholdChangeEntry | None:
        """记录用户反馈并施加**硬冷却**。

        反馈同时是频率自适应的输入（``feedback_signals_for_frequency_adaptation``），
        但本方法只负责冷却这一段；节律学习由 :meth:`HeartbeatScheduler.learn_interval`
        承担，并且必须落 threshold_change_log。两者分开是为了让"这一次别再说"
        与"以后少说"在审计上是两件事。
        """
        if signal not in self._legal_feedback:
            raise WakeError(
                f"非法反馈信号 {signal!r}；法定信号为 {list(self._legal_feedback)}"
            )
        now = _utc(now)
        seconds = self._cooldowns[signal]
        self._cooldown_until[self._dedup_key(wake)] = now + timedelta(seconds=seconds)
        return None

    def drain(self) -> list[CandidateWake]:
        """取出全部在队唤醒（FIFO 按创建时间）。"""
        items = sorted(self._queue.values(), key=lambda w: _utc(w.created_at))
        self._queue.clear()
        return items

    def pending_count(self) -> int:
        return len(self._queue)

    def suppression_log(self) -> list[Dict[str, Any]]:
        """被合并/被冷却压制的唤醒全部留痕 —— 静默失效一律非法。"""
        return list(self._suppression_log)

    @staticmethod
    def _dedup_key(wake: CandidateWake) -> str:
        trigger = wake.trigger
        dimension = trigger.dimension_id if trigger is not None else None
        kind = trigger.kind.value if trigger is not None else str(wake.source)
        return f"{kind}|{dimension or '-'}"


# ---------------------------------------------------------------------------
# 心跳调度器
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SilentPatrolRecord:
    """静默巡检留痕：每一次**没有出声**的心跳都必须留下一条。

    ``cancelled_heartbeat_must_still_log_silent_patrol = true``。这条记录的存在使
    "被闸门取消"与"根本没运行"在审计上可区分 —— 否则后台巡检停转会以"很安静"的
    形式伪装成合规。``hard_block_still_allows`` 里的 ``background_silent_patrol``
    正是由它承载：HARD_BLOCK 禁止对外投递，但**不**禁止巡检。
    """

    beat_index: int
    at: datetime
    reason: str
    verdict: SafetyVerdict | None
    wake_id: str | None
    still_allows: tuple[str, ...]
    #: 触发静默的**具体**规则名。粗粒度的 ``reason`` 只能说"被 Step-0 挡了"，
    #: 说不出是便利、信道、预算还是节奏炸弹 —— 而这四者在治理上是完全不同的事。
    rules_fired: tuple[str, ...] = ()

    def to_audit(self) -> Dict[str, Any]:
        return {
            "beat_index": self.beat_index,
            "at": self.at.isoformat(),
            "reason": self.reason,
            "verdict": self.verdict.value if self.verdict is not None else None,
            "wake_id": self.wake_id,
            "still_allows": list(self.still_allows),
            "rules_fired": list(self.rules_fired),
        }


@dataclass(frozen=True, slots=True)
class BeatOutcome:
    """一次心跳的完整结果：候选唤醒 + Step-0 结论 + 入队判定 + 巡检留痕。"""

    beat_index: int
    at: datetime
    wake: CandidateWake | None
    decision: GateDecision | None
    queue: QueueDecision | None
    patrol: SilentPatrolRecord | None

    @property
    def deliverable(self) -> bool:
        """这次心跳是否**已具备出声资格**（尚需显式调用 :meth:`HeartbeatScheduler.deliver`）。

        刻意不设 ``delivered`` 字段：``beat`` 从不投递，而 ``deliver`` 无法回写一个
        冻结实例 —— 于是 ``delivered`` 只能是恒假的死字段，读它的人会得到"从没出声"
        的错误结论。是否真的出声由 :meth:`HeartbeatScheduler.deliver` 的返回值与
        调度器审计计数记录，那才是唯一有权威的地方。
        """
        return (
            self.wake is not None
            and self.decision is not None
            and self.decision.delivery_permitted
            and self.queue is not None
            and self.queue.state is WakeState.NEW
        )


class HeartbeatScheduler:
    """长平稳主动探寻心跳调度器（§80 / ADJ-002）。

    三件互相咬合的事，任何一件单独拿出来都会被绕过，所以合在一个类里：

    1. **产出候选唤醒**：心跳到点只产生"候选"，不产生"承诺"。没有实质证据
       （``evidence_refs`` 为空）时**根本不构造唤醒**，直接落一条静默巡检记录 ——
       这是 ``fixed_rhythm_bomb_count_under_7d_stable_data = 0`` 的正面实现。
    2. **过 Step-0**：任何模型调用之前。QUIET ⇒ 降级为静默巡检（政策
       ``candidate_wake_downgrades_to_silent_patrol_on_QUIET``）。
    3. **过冷却去重队列**：反馈冷却是硬约束，节律到了也不能绕过。

    ``deliver`` 是唯一的出声出口，要求 Step-0 放行 + 队列判定为 NEW/MERGED 主件。
    """

    def __init__(
        self,
        *,
        policy: Mapping[str, Any] | None = None,
        heartbeat_policy: Mapping[str, Any] | None = None,
        step0_policy: Mapping[str, Any] | None = None,
        token_budget_policy: Mapping[str, Any] | None = None,
        threshold_policy: Mapping[str, Any] | None = None,
        gate: Step0SafetyGate | None = None,
        queue: CooldownQueue | None = None,
        meter: ModelCallMeter | None = None,
        interval_hours: float | None = None,
    ) -> None:
        # 两种注入形状：``policy=`` 给整份 root；``heartbeat_policy=`` 等给单个段。
        # 两者最终都汇进同一批 loader，注入路径不享受任何弱校验。
        root: Dict[str, Any] = dict(policy) if policy is not None else load_runtime_policy()
        self.heartbeat_policy: Dict[str, Any] = (
            _validated_section(load_heartbeat_policy, heartbeat_policy, "heartbeat")
            if heartbeat_policy is not None
            else load_heartbeat_policy(root)
        )
        _assert_floor_channels_match_policy(self.heartbeat_policy)
        self.token_budget_policy: Dict[str, Any] = (
            _validated_section(load_token_budget_policy, token_budget_policy, "token_budget")
            if token_budget_policy is not None
            else load_token_budget_policy(root)
        )
        self.threshold_policy: Dict[str, Any] = (
            validate_policy_section(
                "threshold_governance",
                threshold_policy
                if threshold_policy is not None
                else root.get("threshold_governance"),
                required_fields=("change_log_fields", "governance_level"),
            )
        )
        self.meter: ModelCallMeter = meter if meter is not None else ModelCallMeter()
        self.gate: Step0SafetyGate = (
            gate
            if gate is not None
            else Step0SafetyGate(
                step0_policy=step0_policy,
                heartbeat_policy=self.heartbeat_policy,
                meter=self.meter,
            )
        )
        self.queue: CooldownQueue = (
            queue if queue is not None else CooldownQueue(heartbeat_policy=self.heartbeat_policy)
        )

        # 触发器法定名映射：政策给的是名字，代码用的是既有枚举，映射只此一处。
        kind_name = self.heartbeat_policy["trigger_kind_name"]
        if kind_name not in TRIGGER_KIND_LEGAL_NAME:
            raise WakeError(
                f"政策 trigger_kind_name={kind_name!r} 未在 TRIGGER_KIND_LEGAL_NAME 中登记；"
                "拒绝自拟第七种触发器名（编号漂移的真实成因）"
            )
        self.trigger_kind: Final[WakeSourceV3] = TRIGGER_KIND_LEGAL_NAME[kind_name]

        factory = self.heartbeat_policy["interval_hours_factory_default"]
        self.factory_min: Final[float] = float(factory["min"])
        self.factory_max: Final[float] = float(factory["max"])
        if interval_hours is None:
            interval_hours = (self.factory_min + self.factory_max) / 2.0
        # 出厂默认取中值；显式给的间隔同样必须为正 —— 只在 learn_interval 里校验
        # 等于让构造参数成为一条绕过检查的路径（与本模块反复踩的"注入绕过校验"同源）。
        if interval_hours <= 0:
            raise WakeError(f"心跳间隔必须为正：{interval_hours}")
        self._interval_hours: float = float(interval_hours)
        self._change_log: list[ThresholdChangeEntry] = []

        self._beat_index = 0
        self._patrol_log: list[SilentPatrolRecord] = []
        self._counts: Dict[str, int] = {
            "beats": 0,
            "delivered": 0,
            "quiet": 0,
            "hard_blocked": 0,
            "no_evidence_skipped": 0,
            "suppressed_by_cooldown": 0,
            "merged": 0,
            "rhythm_bombs_delivered": 0,
            "safety_bypasses": 0,
        }

    # -- 节律（出厂默认，非铁律） ------------------------------------------

    @property
    def interval_hours(self) -> float:
        return self._interval_hours

    def learn_interval(
        self,
        next_hours: float,
        *,
        learner_hash: str,
        rationale: str,
        input_window: str,
        now: datetime,
    ) -> ThresholdChangeEntry:
        """按 ADJ-008 学习心跳节律，逐字产出法定八字段的变更条目（可回放可回滚）。

        本方法**不判断学到的值是否合理** —— 那是学习器与治理的职责。它只保证：
        每一步演进都留下 prev/next/learner_hash/rationale/applied_at，且
        ``reversible=True``。没有这条日志，"阈值长期自主演进"就退化成无法审计的
        随机漂移。
        """
        if next_hours <= 0:
            raise WakeError(f"心跳间隔必须为正：{next_hours}")
        prev = self._interval_hours
        self._interval_hours = float(next_hours)
        entry = ThresholdChangeEntry(
            param_id="heartbeat.interval_hours",
            prev_value=prev,
            next_value=float(next_hours),
            input_window=input_window,
            learner_hash=learner_hash,
            rationale=rationale,
            applied_at=_utc(now),
            reversible=True,
        )
        entry.validate_against_policy(self.threshold_policy)
        self._change_log.append(entry)
        return entry

    def rollback_interval(self) -> ThresholdChangeEntry | None:
        """回滚最近一次节律演进（``change_log_must_be_rollbackable``）。"""
        if not self._change_log:
            return None
        last = self._change_log[-1]
        self._interval_hours = float(last.prev_value)
        return last

    def change_log(self) -> list[ThresholdChangeEntry]:
        return list(self._change_log)

    # -- 心跳 --------------------------------------------------------------

    def beat(
        self,
        *,
        now: datetime,
        signals: GateSignals,
        evidence_refs: Sequence[str] = (),
        dimension_id: str | None = None,
        floor_channel: str | None = None,
        projected_tokens: int | None = None,
        wake_id: str | None = None,
        safety_bypass: SafetyBypassPayload | None = None,
    ) -> BeatOutcome:
        """跑一次心跳。

        顺序即法律：先判有没有实质理由（无则**不构造唤醒**，只留巡检痕迹），
        再 Step-0，再冷却队列。任何一步不过，用户面前什么都没有，但审计里全都有。
        """
        now = _utc(now)
        self._beat_index += 1
        self._counts["beats"] += 1
        index = self._beat_index

        # 1 · 无实质证据 ⇒ 纯节奏 ⇒ 不出声，也不构造唤醒（门禁 4 正面实现）
        if not evidence_refs and floor_channel is None:
            self._counts["no_evidence_skipped"] += 1
            patrol = self._log_patrol(
                index, now, "no_candidate_evidence_rhythm_bomb_not_emitted", None, None
            )
            return BeatOutcome(index, now, None, None, None, patrol)

        trigger = CandidateTrigger(
            trigger_id=wake_id or f"trig-hb-{index}",
            detected_at=now,
            kind=self.trigger_kind,
            evidence_refs=tuple(evidence_refs),
            dimension_id=dimension_id,
            floor_channel=floor_channel,
        )
        wake = CandidateWake(
            wake_id=wake_id or f"hb-{index}",
            source=self.trigger_kind,
            created_at=now,
            trigger=trigger,
            # P0 只属于**真实险情**（必须携带 hazard 载荷）。安全值守通道的常规心跳
            # 是后台静默巡检，优先级为 P3 —— 把值守心跳一律抬成 P0，等于让每一次
            # 节律到点都宣称"有生命危险"，既污染审计也会把硬件穿透路径变成日常通道。
            priority=(
                WakePriority.P0_CRITICAL_SAFETY
                if safety_bypass is not None
                else WakePriority.P3_BACKGROUND_TICK
            ),
            projected_tokens=projected_tokens,
            safety_bypass=safety_bypass,
            object_id=wake_id,
        )

        # 2 · Step-0 闸门（先于一切心智步骤，零模型调用）
        decision = self.gate.evaluate(wake, signals)
        if wake.is_safety_trigger:
            self._counts["safety_bypasses"] += 1

        if decision.verdict.verdict is SafetyVerdict.QUIET:
            self._counts["quiet"] += 1
            patrol = self._log_patrol(
                index, now, "step0_convenience_veto_downgraded_to_silent_patrol",
                decision.verdict.verdict, wake.wake_id,
                rules_fired=decision.rules_fired,
            )
            return BeatOutcome(index, now, wake, decision, None, patrol)

        if decision.verdict.verdict is SafetyVerdict.HARD_BLOCK:
            self._counts["hard_blocked"] += 1
            # HARD_BLOCK 禁止对外投递，但**不**禁止后台静默巡检与安全值守。
            patrol = self._log_patrol(
                index, now, "step0_hard_block_external_delivery_prohibited",
                decision.verdict.verdict, wake.wake_id,
                still_allows=tuple(sorted(decision.allows)),
                rules_fired=decision.rules_fired,
            )
            return BeatOutcome(index, now, wake, decision, None, patrol)

        # 3 · 冷却与去重队列
        queued = self.queue.enqueue(wake, now=now)
        if queued.state is WakeState.SUPPRESSED:
            self._counts["suppressed_by_cooldown"] += 1
            patrol = self._log_patrol(
                index, now, "feedback_cooldown_hard_constraint",
                decision.verdict.verdict, wake.wake_id,
                rules_fired=decision.rules_fired,
            )
            return BeatOutcome(index, now, wake, decision, queued, patrol)
        if queued.state is WakeState.MERGED:
            self._counts["merged"] += 1

        return BeatOutcome(index, now, wake, decision, queued, None)

    def deliver(self, outcome: BeatOutcome, context: Any) -> Dict[str, Any]:
        """唯一的出声出口：三张凭证齐备才投递。

        * 门禁 1：``wake.require_trigger()``（第三次拒绝点）
        * 门禁 2/3：``decision.delivery_permitted``
        * 队列：必须是本次心跳自己入队的主件（NEW），合并进来的重复件不再投一次

        投递复用既有 ``wake.dispatcher.dispatch_wake_event``：P0 生命安全走 0 延迟
        硬件穿透，其余走常规看板装配。本模块**不另造第二条投递路径** —— 两条路径
        意味着两套绕过闸门的可能。
        """
        if outcome.wake is None:
            raise MissingCandidateTriggerError(
                f"心跳 #{outcome.beat_index} 未产出候选唤醒（无实质证据），无可投递",
                context={"beat_index": outcome.beat_index},
            )
        if outcome.decision is None:
            raise WakeError(
                f"心跳 #{outcome.beat_index} 未经 Step-0 判定，拒绝投递",
                context={"beat_index": outcome.beat_index},
            )
        outcome.wake.require_trigger()
        if not outcome.decision.delivery_permitted:
            raise PromiseToSpeakError(
                f"Step-0 裁决为 {outcome.decision.verdict.verdict.value}，候选唤醒不得出声"
                "（红线 25：候选唤醒不是承诺出声）",
                context={
                    "wake_id": outcome.wake.wake_id,
                    "verdict": outcome.decision.verdict.verdict.value,
                    "rules_fired": list(outcome.decision.rules_fired),
                },
            )
        if not outcome.deliverable:
            state = outcome.queue.state.value if outcome.queue is not None else "absent"
            raise WakeError(
                f"唤醒 {outcome.wake.wake_id!r} 队列状态为 {state}，非新件不得投递"
                "（合并进来的重复件再投一次，去重就等于没做）",
                context={"wake_id": outcome.wake.wake_id, "queue_state": state},
            )
        receipt = dispatch_wake_event(outcome.wake, context)
        self._counts["delivered"] += 1
        if outcome.wake.trigger is not None and outcome.wake.trigger.is_rhythm_bomb:
            # 恒为 0 的反面指标；一旦非 0 就是门禁 4 被击穿。
            self._counts["rhythm_bombs_delivered"] += 1
        return receipt

    def record_feedback(self, outcome: BeatOutcome, signal: str, *, now: datetime) -> None:
        """把用户反馈转成硬冷却（``feedback_cooldown_is_hard_constraint``）。"""
        if outcome.wake is None:
            raise WakeError("无候选唤醒，无从记录反馈")
        self.queue.record_feedback(outcome.wake, signal, now=now)

    # -- 审计 --------------------------------------------------------------

    def _log_patrol(
        self,
        index: int,
        now: datetime,
        reason: str,
        verdict: SafetyVerdict | None,
        wake_id: str | None,
        *,
        still_allows: Iterable[str] = (),
        rules_fired: Iterable[str] = (),
    ) -> SilentPatrolRecord:
        record = SilentPatrolRecord(
            beat_index=index,
            at=now,
            reason=reason,
            verdict=verdict,
            wake_id=wake_id,
            still_allows=tuple(still_allows),
            rules_fired=tuple(rules_fired),
        )
        self._patrol_log.append(record)
        return record

    def patrol_log(self) -> list[SilentPatrolRecord]:
        return list(self._patrol_log)

    def audit(self) -> Dict[str, Any]:
        """调度器自记账。``model_calls`` 取自共享计量器，**恒应为 0**。

        ``gate_cancel_share`` 对照政策 ``gate_cancel_target_share``：政策把心跳月度
        预算（36K）建立在"80% 的心跳被 Step-0 机械闸门取消"之上。取消率掉下来，
        预算就会破 —— 所以这不是一个观感指标，而是预算闭合的承重参数。
        """
        beats = self._counts["beats"]
        cancelled = beats - self._counts["delivered"]
        return {
            "counts": dict(self._counts),
            "interval_hours": self._interval_hours,
            "factory_default": {"min": self.factory_min, "max": self.factory_max},
            "trigger_kind": self.trigger_kind.value,
            "patrol_records": len(self._patrol_log),
            "queue_pending": self.queue.pending_count(),
            "queue_suppressions": len(self.queue.suppression_log()),
            "change_log_entries": len(self._change_log),
            "gate_cancel_share": (cancelled / beats) if beats else 0.0,
            "gate_cancel_target_share": self.heartbeat_policy["gate_cancel_target_share"],
            "model_calls": self.meter.model_calls,
            "tokens": self.meter.tokens,
        }
