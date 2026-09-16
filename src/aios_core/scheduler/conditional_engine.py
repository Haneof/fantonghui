"""M2-005R 条件驱动任务调度双轨引擎与 DORMANT 隐形机制。

落实宪法 §86之2（条件驱动任务零浪费执行）、§91（task.create_conditional /
task.inspect_ready）、§85之1（严禁盲目灌入全量长上下文）、§77（触发器不负责理解人生）。
法律参数一律**引用** ``governance/runtime_policy.json`` 的 ``task_readiness`` 段，
不在本模块内复制常量（复制即漂移源，见 v1.2.0 的 THRESH-BASE 事故）。

四条硬门禁与本模块的落点
------------------------

1. **未成熟任务 Token 严格为 0**
   :meth:`ConditionalEngine.build_manifest` 只挂载 ``READY`` 任务（政策字段
   ``manifest_mounts_only_ready_tasks``）。DORMANT 任务在装配路径上**连 token 估算
   都不发生**——不是"估算了再减掉"，而是根本不进入那条代码路径。可测性质是
   **不变性**：DORMANT 任务数量从 0 涨到 200，manifest 的 token_total 分毫不动。

2. **Level-1 机械快轨 0 Token 判定**
   :meth:`ConditionalEngine.tick` 只对机械轨任务求值，复用既有
   ``eligibility_worker.MechanicalEvaluator``（其 docstring 即「绝不调模型」）与
   Kleene 三值逻辑。整个 tick 期间 :class:`ModelCallMeter` 的模型调用数恒为 0。

3. **Level-2 机会式捎带**
   :meth:`ConditionalEngine.piggyback_evaluate` 是**唯一**能触发模型调用的入口，
   且必须持有由 :meth:`ConditionalEngine.issue_user_wake_token` 签发、经 HMAC 校验的
   ``UserWakeToken``。任务自身无法伪造该令牌，因此"为了评估一个休眠任务而自主唤醒
   大模型"在本模块内**没有可调用的代码路径**。捎带前还先跑机械前置过滤：机械子树
   判 FALSE 就直接返回，连模型都不叫。

4. **状态机非法跃迁 100% 拦截**
   状态与转移表**全部复用法定定义**：``contracts.enums.TaskState`` 与
   ``services.state_machines._TASK_TRANSITIONS``。本模块不新造任何状态枚举——
   本仓库曾出现过 ``ObjectType`` / ``ObjectTypeV3`` 双枚举导致 v3 扩展类型完全无法
   落盘的真实缺陷，同一个坑不踩第二次。

术语映射（工单用语 → 法定枚举）
------------------------------
工单说的 ``DORMANT`` 在法定 ``TaskState`` 中**没有同名成员**，其语义由
``TaskState.DRAFT`` 承载：``DRAFT`` 是唯一先于 ``READY`` 的状态，且法定转移表规定
``DRAFT -> {READY, CANCELLED}``，正好等价于工单要求的
``DORMANT -> READY -> RUNNING -> COMPLETED`` 且禁止从未就绪状态直接执行。
本模块导出 :data:`DORMANT` 作为 ``TaskState.DRAFT`` 的别名，只为让调用方能用工单
词汇说话，**不新增枚举值**（新增即需一级治理变更）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from aios_core.contracts.enums import ErrorCode, TaskState
from aios_core.contracts.enums_v3 import TriState
from aios_core.contracts.models_v3 import (
    MechanicalPredicate,
    SemanticPredicate,
    TriggerExpression,
)
from aios_core.errors import AIOSProtocolError
from aios_core.services.eligibility_worker import (
    EvalVerdict,
    MechanicalEvaluator,
    prune_semantic_subtrees,
)
from aios_core.services.manifest_data_plane import estimate_tokens
from aios_core.services.state_machines import allowed_task_transitions

__all__ = [
    "DORMANT",
    "AutonomousWakeProhibitedError",
    "ConditionalEngine",
    "ConditionalTask",
    "ForgedWakeTokenError",
    "IllegalStateTransitionError",
    "ManifestBuild",
    "ManifestSlot",
    "MechanicalResolver",
    "MissingTriggerCriteriaError",
    "ModelCallMeter",
    "PiggybackOutcome",
    "SchedulerError",
    "TickReport",
    "TrackKind",
    "TrackMismatchError",
    "UserWakeToken",
    "load_task_readiness_policy",
    "validate_task_readiness_section",
    "reference_physical_resolver",
]

#: 工单词汇 DORMANT 的法定落点。见模块 docstring「术语映射」。
DORMANT: TaskState = TaskState.DRAFT

#: 法定四态主链（工单 §4）。它是法定转移表的**投影**，不是新规则：
#: DRAFT->READY->RUNNING->COMPLETED 每一步都在 _TASK_TRANSITIONS 里，
#: 而 DRAFT->RUNNING、DRAFT->COMPLETED 都不在，故必然被拦。
PRIMARY_CHAIN: Tuple[TaskState, ...] = (
    DORMANT,
    TaskState.READY,
    TaskState.RUNNING,
    TaskState.COMPLETED,
)

_POLICY_PATH = Path(__file__).resolve().parents[3] / "governance" / "runtime_policy.json"

#: 本模块依赖的法律字段。构造时逐一校验存在性与取值，政策漂移即 fail-closed。
_REQUIRED_POLICY_FIELDS: Tuple[Tuple[str, Any], ...] = (
    ("trigger_criteria_is_required_on_task", True),
    ("periodic_todo_sweep_prohibited", True),
    ("manifest_mounts_only_ready_tasks", True),
    ("mechanical_trigger_output_is_binary_signal_only", True),
    ("predicate_dsl_must_be_finite_json", True),
    ("python_eval_prohibited", True),
)


def validate_task_readiness_section(section: Any) -> Dict[str, Any]:
    """校验 ``task_readiness`` 段的法定字段存在且取值未漂移。

    **注入路径与文件路径都必须过这一关**：只在读文件时校验，等于给
    ``ConditionalEngine(policy=...)`` 留了一条绕过法律的口子——测试注入一份
    被改过的政策，引擎就会带着漂移参数静默运行。
    """
    if not isinstance(section, dict):
        raise SchedulerError("task_readiness 段必须是对象")
    for key, expected in _REQUIRED_POLICY_FIELDS:
        if key not in section:
            raise SchedulerError(f"task_readiness 缺少法定字段 {key!r}")
        if section[key] is not expected:
            raise SchedulerError(
                f"task_readiness.{key} 法定值为 {expected!r}，实际为 {section[key]!r}"
                " —— 引擎拒绝带着漂移的法律参数运行"
            )
    registry = section.get("context_predicate_registry")
    if not isinstance(registry, list) or not registry:
        raise SchedulerError("task_readiness.context_predicate_registry 必须是非空列表")
    return dict(section)


def load_task_readiness_policy() -> Dict[str, Any]:
    """读取 ``governance/runtime_policy.json`` 的 ``task_readiness`` 段并校验。

    引用而非复制：本模块的所有阈值都以政策文件为唯一权威。字段缺失或取值被改动
    都会立即失败，而不是让引擎带着过期参数静默运行。
    """
    policy = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(policy.get("task_readiness"), dict):
        raise SchedulerError(
            f"runtime_policy.json 缺少 task_readiness 段（{_POLICY_PATH}）"
        )
    return validate_task_readiness_section(policy["task_readiness"])


# ---------------------------------------------------------------------------
# 异常族
# ---------------------------------------------------------------------------


class SchedulerError(AIOSProtocolError):
    """条件调度引擎的协议错误基类。"""

    def __init__(self, message: str, *, code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
                 context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(code, message, context=context)


class IllegalStateTransitionError(SchedulerError):
    """工单 §4：任何非法状态跃迁 100% 拦截。

    特别地，从未就绪状态（DORMANT / WAITING_* / BLOCKED）直接触发执行必抛本异常。
    """


class MissingTriggerCriteriaError(SchedulerError):
    """无触发条件的任务一律拒绝登记。

    法律：``task_readiness.trigger_criteria_is_required_on_task = true``，
    ``todo_without_criteria_rejected_with = "INVALID_ARGUMENT"``。
    宪法依据：§86之2 与断层审计 G14~G17（"todo 必须 next_review" 就是宪法禁止的
    无脑遍历）。
    """


class AutonomousWakeProhibitedError(SchedulerError):
    """工单 §3：绝不为评估休眠任务而自主唤醒大模型。"""


class ForgedWakeTokenError(SchedulerError):
    """捎带令牌签名不符或已消费 —— 任务无法自行伪造"用户唤醒了我"。"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, code=ErrorCode.PERMISSION_DENIED, context=context)


class TrackMismatchError(SchedulerError):
    """机械轨任务被送去语义复核（浪费预算），或语义轨任务被要求纯机械判定。"""


# ---------------------------------------------------------------------------
# 轨道与计量
# ---------------------------------------------------------------------------


class TrackKind:
    """双轨标识（字符串常量而非 Enum：避免再造一个与政策字段并列的枚举）。"""

    #: Level-1 机械快轨：纯 Python 判定，0 模型调用，命中即自动跃迁 READY。
    LEVEL1_MECHANICAL = "level1_mechanical"
    #: Level-2 机会式捎带：只在用户主动唤醒且场景相关时顺路评估。
    LEVEL2_SEMANTIC = "level2_semantic"

    ALL: Tuple[str, ...] = (LEVEL1_MECHANICAL, LEVEL2_SEMANTIC)


@dataclass(slots=True)
class ModelCallMeter:
    """模型调用与 token 计量器 —— 四条门禁里三条的**唯一**可观测证据。

    引擎内部任何一次模型调用都必须经过 :meth:`charge`；测试直接读本计量器断言
    "严格为 0"。把它做成显式对象而不是散落的计数器，是为了让"0 次"这个断言
    有一个无法被绕过的单一出口。
    """

    model_calls: int = 0
    tokens: int = 0
    call_log: list = field(default_factory=list)

    def charge(self, *, lane: str, tokens: int, reason: str) -> None:
        if tokens < 0:
            raise SchedulerError(f"token 计量不得为负：{tokens}")
        self.model_calls += 1
        self.tokens += tokens
        self.call_log.append((lane, tokens, reason))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "tokens": self.tokens,
            "call_log": list(self.call_log),
        }


@dataclass(frozen=True, slots=True)
class UserWakeToken:
    """用户**主动**唤醒 AI 的一次性凭证，Level-2 捎带的唯一入场券。

    ``signature`` 由引擎实例私钥对 (session_id, issued_at, context) 做 HMAC 得出，
    任务侧无法伪造；``consumed`` 由引擎登记，同一令牌对同一任务只能捎带一次，
    这就是"绝不频繁唤醒"的物理实现。
    """

    session_id: str
    issued_at: datetime
    context: frozenset
    signature: str


# ---------------------------------------------------------------------------
# 任务与产物
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ConditionalTask:
    """条件任务的调度侧投影（持久化仍由 storage 层的冻结 Task 对象承载）。

    ``state`` 一律取法定 ``TaskState``，本类不定义任何自有状态值。
    """

    task_id: str
    subject: str
    title: str
    trigger: TriggerExpression
    track: str
    state: TaskState = DORMANT
    priority: int = 0
    required_context: frozenset = frozenset()
    registered_at: Optional[datetime] = None
    mechanical_prefix: Optional[TriggerExpression] = None
    last_verdict: Optional[TriState] = None
    review_count: int = 0


@dataclass(frozen=True, slots=True)
class ManifestSlot:
    task_id: str
    title: str
    state: str
    tokens: int


@dataclass(frozen=True, slots=True)
class ManifestBuild:
    """看板装配结果。``dormant_population`` 与 ``token_total`` 的**无关性**
    就是工单门禁 1 的可测形式。"""

    mounted: Tuple[ManifestSlot, ...]
    token_total: int
    dormant_population: int
    model_calls: int


@dataclass(frozen=True, slots=True)
class TickReport:
    """一次 Level-1 机械快轨 tick 的结果。"""

    evaluated: int
    promoted_to_ready: Tuple[str, ...]
    still_dormant: int
    elapsed_ms: float
    max_task_ms: float
    model_calls: int
    semantic_tasks_touched: int  # 必须恒为 0：tick 不做周期性语义扫荡


@dataclass(frozen=True, slots=True)
class PiggybackOutcome:
    """一次 Level-2 捎带评估的结果。"""

    task_id: str
    invoked_model: bool
    verdict: TriState
    reason: str
    model_calls: int
    tokens: int
    promoted_to_ready: bool


#: 机械谓词解析器：判得了就返回 TriState，判不了返回 None（原样回落法定求值器）。
MechanicalResolver = Callable[
    [MechanicalPredicate, str, datetime, Mapping[str, dict]], Optional[TriState]
]


class _ResolvingMechanicalEvaluator(MechanicalEvaluator):
    """在既有法定机械求值器之上补一层**可插拔**的谓词解析器。

    既有 ``MechanicalEvaluator.mechanical()`` 对 ``obs_threshold`` / ``state_change`` /
    ``duration_over`` / ``slope`` / ``keyword_entity`` / ``data_gap`` 一律返回 UNKNOWN，
    其注释写明「其余 kind 在 sim 阶段一律 UNKNOWN（有 LLM 的影子就判 UNKNOWN，
    绝不猜 TRUE）」。那是 sim 阶段的**有意保守留白**，不是 bug；但工单 M2-005R
    门禁 2 明确要求地理围栏与心率阈值由底层调度器在 1ms 内纯 Python 判定。

    本类**不修改、不复制**既有求值器：只覆盖 ``mechanical`` 这一个叶子方法，
    解析器判不了就 ``super()`` 回落（即仍是 UNKNOWN）。AST 遍历、Kleene 三值合成、
    时间/事件/依赖三类叶子的语义全部沿用法定实现——杜绝出现第二套求值语义
    （本仓库已有 ``ObjectType`` / ``ObjectTypeV3`` 双枚举的前车之鉴）。
    """

    def __init__(self, *args: Any, resolver: Optional[MechanicalResolver] = None,
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._resolver = resolver

    def mechanical(self, leaf: MechanicalPredicate, subject: str) -> EvalVerdict:
        if self._resolver is not None:
            decided = self._resolver(leaf, subject, self.now, self.payloads)
            if decided is not None:
                return EvalVerdict(decided, f"resolver:{leaf.kind}")
        return super().mechanical(leaf, subject)


def reference_physical_resolver(
    leaf: MechanicalPredicate,
    subject: str,
    now: datetime,
    payloads: Mapping[str, dict],
) -> Optional[TriState]:
    """工单三类客观物理条件的**参考**解析器（纯 Python、0 模型调用）。

    .. warning::
       ``MechanicalPredicate.params`` 在法定契约里是自由字典（``dict[str, Any]``），
       因此下面这套 params 约定是**本模块提出的提案**，尚未入法。投产前必须把它
       提交给 ``governance/runtime_policy.json`` 或契约层批准，否则就会出现
       "两个模块各按自己想象的 params 写代码"这种漂移。在批准之前，
       ``ConditionalEngine`` 的 ``predicate_resolver`` **缺省为 None**，
       即保持法定求值器的保守 UNKNOWN 行为，本函数不会被自动启用。

    支持的 params 约定：

    - ``obs_threshold``（心率阈值超标等）::

        {"source_ref": "<world object id>", "field": "hr_bpm",
         "op": ">=" | ">" | "<=" | "<" | "==" , "value": 95,
         "streak_days": 3}          # 可选：要求连续 N 天成立

      ``streak_days`` 读 ``payloads[source_ref]["daily_streak"]``（上游 C01 边缘清洗
      负责维护连续天数；调度器**不自己**从原始序列推算，避免第二套时间窗语义）。

    - ``state_change``（地理围栏等）::

        {"source_ref": "<world object id>", "field": "location",
         "equals": "shanghai_office"}

    判定规则一律 fail-closed：**数据缺失即 UNKNOWN，绝不猜 TRUE**。这与法定
    求值器的保守取向一致，也符合 ``step0_safety_gate.deterministic_rules_only``。
    """
    params = leaf.params or {}
    source_ref = params.get("source_ref")
    if not isinstance(source_ref, str):
        return None  # 约定不符 => 交回法定求值器（仍为 UNKNOWN）
    payload = payloads.get(source_ref)
    if payload is None:
        return TriState.UNKNOWN  # 世界树里没有这个来源：数据缺口是有名的事
    field_name = params.get("field")
    if not isinstance(field_name, str) or field_name not in payload:
        return TriState.UNKNOWN

    if leaf.kind == "obs_threshold":
        observed = payload[field_name]
        expected = params.get("value")
        op = params.get("op", ">=")
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            return TriState.UNKNOWN
        if isinstance(expected, bool) or not isinstance(expected, (int, float)):
            return None
        comparisons = {
            ">=": observed >= expected, ">": observed > expected,
            "<=": observed <= expected, "<": observed < expected,
            "==": observed == expected,
        }
        if op not in comparisons:
            return None
        hit = comparisons[op]
        streak_days = params.get("streak_days")
        if hit and isinstance(streak_days, int) and streak_days > 1:
            streak = payload.get("daily_streak")
            if not isinstance(streak, int):
                return TriState.UNKNOWN  # 要连续 N 天但上游没给连续天数 => 不猜
            return TriState.TRUE if streak >= streak_days else TriState.FALSE
        return TriState.TRUE if hit else TriState.FALSE

    if leaf.kind == "state_change":
        expected = params.get("equals")
        if expected is None:
            return None
        return TriState.TRUE if payload[field_name] == expected else TriState.FALSE

    return None  # 其余 kind 交回法定求值器


class _ReplayBus:
    """一次 tick 内的事件重放总线。

    为什么需要它：既有 ``MechanicalEvaluator.event_matched`` 的语义是 **drain**
    （取走即清空）。若为每个任务各建一个求值器共享同一条真总线，那么第一个含
    ``EventMatched`` 叶子的任务会把本 tick 的事件全部喝干，后续任务一律判
    ``no_events_drained`` —— 200 项任务里只有排在前面的那几项能被事件触发，
    而且失败是静默的。故 tick 开始时一次性 drain，再给每个任务一份独立重放副本。
    """

    __slots__ = ("_rows",)

    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self._rows = [dict(row) for row in rows]

    def drain(self):
        rows = self._rows
        yield from rows


class ConditionalEngine:
    """条件驱动任务调度双轨引擎。

    - **Level-1 机械快轨**：:meth:`tick`，纯 Python，0 模型调用，命中即自动 READY；
    - **Level-2 机会式捎带**：:meth:`piggyback_evaluate`，必须持用户主动唤醒令牌；
    - **DORMANT 物理隐形**：:meth:`build_manifest` 只挂载 READY，DORMANT 连 token
      估算都不发生。

    引擎不持有任何"周期性遍历全部待办"的入口 —— 政策字段
    ``periodic_todo_sweep_prohibited = true``，宪法禁止无脑遍历（断层审计 G14~G17）。
    """

    def __init__(
        self,
        *,
        policy: Optional[Mapping[str, Any]] = None,
        token_secret: Optional[bytes] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.policy: Dict[str, Any] = (
            validate_task_readiness_section(policy)
            if policy is not None
            else load_task_readiness_policy()
        )
        self._predicate_registry = frozenset(self.policy["context_predicate_registry"])
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # 令牌私钥：每实例随机，任务侧无法伪造"用户唤醒了我"
        self._token_secret = token_secret or secrets.token_bytes(32)
        self._tasks: Dict[str, ConditionalTask] = {}
        self._order: list = []
        self.meter = ModelCallMeter()
        #: (session_id, task_id) 已捎带登记 —— 同一唤醒对同一任务只许评估一次
        self._consumed: set = set()
        #: 按状态累计的 token 估算次数/数量。DORMANT 必须恒为 0（门禁 1 的直接证据）
        self._estimate_audit: Dict[str, Dict[str, int]] = {}

    # ------------------------------------------------------------------
    # 登记与轨道分类
    # ------------------------------------------------------------------

    @staticmethod
    def classify_track(trigger: TriggerExpression) -> str:
        """含语义叶子 => Level-2 捎带轨；否则 => Level-1 机械快轨。

        复用 ``TriggerExpression.has_semantic()``（法定 AST 自带的方法），
        不自己遍历判类型，避免与契约层的定义漂移。
        """
        return TrackKind.LEVEL2_SEMANTIC if trigger.has_semantic() else TrackKind.LEVEL1_MECHANICAL

    def register_task(
        self,
        task_id: str,
        subject: str,
        title: str,
        trigger: Any,
        *,
        priority: int = 0,
        required_context: Iterable[str] = (),
        now: Optional[datetime] = None,
    ) -> ConditionalTask:
        """登记一项条件任务，初始状态一律为 DORMANT（= ``TaskState.DRAFT``）。

        拒绝三类登记：
        1. 无触发条件（``trigger is None``）—— 法律
           ``trigger_criteria_is_required_on_task``，错误码 ``INVALID_ARGUMENT``；
        2. 触发条件不是有限 JSON AST（传了字符串表达式或 Python 可调用对象）——
           法律 ``predicate_dsl_must_be_finite_json`` + ``python_eval_prohibited``；
        3. ``required_context`` 含未登记的情境谓词 —— 只认政策
           ``context_predicate_registry`` 里的法定名，杜绝各模块自造谓词。
        """
        if not isinstance(task_id, str) or not task_id.strip():
            raise SchedulerError("task_id 必须是非空字符串")
        if task_id in self._tasks:
            raise SchedulerError(f"task_id 重复登记：{task_id!r}")
        if not isinstance(subject, str) or not subject.strip():
            raise SchedulerError("subject 必须是非空字符串")
        if not isinstance(title, str) or not title.strip():
            raise SchedulerError("title 必须是非空字符串")

        if trigger is None:
            raise MissingTriggerCriteriaError(
                f"任务 {task_id!r} 缺少触发条件：无条件的 todo 就是宪法禁止的无脑遍历"
                "（task_readiness.trigger_criteria_is_required_on_task）",
                context={"task_id": task_id},
            )
        if callable(trigger) or isinstance(trigger, str):
            raise SchedulerError(
                f"任务 {task_id!r} 的触发条件必须是有限 JSON AST（TriggerExpression），"
                "不接受字符串表达式或可调用对象 —— "
                "task_readiness.python_eval_prohibited / predicate_dsl_must_be_finite_json",
                context={"task_id": task_id, "got": type(trigger).__name__},
            )
        if not isinstance(trigger, TriggerExpression):
            raise SchedulerError(
                f"任务 {task_id!r} 的触发条件类型非法：{type(trigger).__name__}",
                context={"task_id": task_id},
            )

        context = frozenset(required_context)
        unknown = context - self._predicate_registry
        if unknown:
            raise SchedulerError(
                f"任务 {task_id!r} 的情境谓词未在政策登记：{sorted(unknown)}；"
                "法定集合见 task_readiness.context_predicate_registry",
                context={"task_id": task_id, "unknown": sorted(unknown)},
            )

        track = self.classify_track(trigger)
        task = ConditionalTask(
            task_id=task_id,
            subject=subject,
            title=title,
            trigger=trigger,
            track=track,
            state=DORMANT,
            priority=priority,
            required_context=context,
            registered_at=now or self._clock(),
            mechanical_prefix=prune_semantic_subtrees(trigger),
        )
        self._tasks[task_id] = task
        self._order.append(task_id)
        return task

    # ------------------------------------------------------------------
    # 只读查询
    # ------------------------------------------------------------------

    def task(self, task_id: str) -> ConditionalTask:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise SchedulerError(
                f"未登记的任务：{task_id!r}",
                code=ErrorCode.NOT_FOUND,
                context={"task_id": task_id},
            ) from None

    def state_of(self, task_id: str) -> TaskState:
        return self.task(task_id).state

    def task_ids(self, *, state: Optional[TaskState] = None,
                 track: Optional[str] = None) -> Tuple[str, ...]:
        return tuple(
            tid for tid in self._order
            if (state is None or self._tasks[tid].state is state)
            and (track is None or self._tasks[tid].track == track)
        )

    def estimate_audit(self) -> Dict[str, Dict[str, int]]:
        """按任务状态统计 token 估算发生次数。DORMANT 项必须恒为 0。"""
        return {state: dict(counts) for state, counts in self._estimate_audit.items()}

    def _charge_estimate(self, state: TaskState, tokens: int) -> int:
        bucket = self._estimate_audit.setdefault(state.value, {"calls": 0, "tokens": 0})
        bucket["calls"] += 1
        bucket["tokens"] += tokens
        return tokens

    # ------------------------------------------------------------------
    # 门禁 4：状态机
    # ------------------------------------------------------------------

    def transition(self, task_id: str, target: TaskState, *, reason: str = "") -> TaskState:
        """按**法定转移表**跃迁；非法跃迁抛 :class:`IllegalStateTransitionError`。

        转移表直接取自 ``services.state_machines.allowed_task_transitions``，
        本模块不复制、不扩展它。
        """
        task = self.task(task_id)
        if not isinstance(target, TaskState):
            raise SchedulerError(
                f"目标状态必须是法定 TaskState，得到 {target!r}",
                context={"task_id": task_id},
            )
        legal = allowed_task_transitions(task.state)
        if target not in legal:
            raise IllegalStateTransitionError(
                f"非法状态跃迁 {task.state.value} -> {target.value}"
                f"（任务 {task_id!r}）；法定可达集合为 "
                f"{sorted(s.value for s in legal) or '（终态，不可再跃迁）'}",
                context={
                    "task_id": task_id,
                    "from": task.state.value,
                    "to": target.value,
                    "reason": reason,
                },
            )
        task.state = target
        return target

    def request_execution(self, task_id: str) -> TaskState:
        """请求执行：只有 READY 可以进入 RUNNING。

        工单 §4：任何尝试从未就绪状态直接触发执行的操作直接抛出
        :class:`IllegalStateTransitionError`。DORMANT / WAITING_* / BLOCKED /
        终态一律拦截，且拦截率必须 100%（无一条静默放行）。
        """
        task = self.task(task_id)
        if task.state is not TaskState.READY:
            raise IllegalStateTransitionError(
                f"任务 {task_id!r} 处于 {task.state.value}，未就绪不得执行；"
                f"只有 {TaskState.READY.value} 可进入 {TaskState.RUNNING.value}",
                context={"task_id": task_id, "state": task.state.value},
            )
        return self.transition(task_id, TaskState.RUNNING, reason="request_execution")

    def complete(self, task_id: str) -> TaskState:
        return self.transition(task_id, TaskState.COMPLETED, reason="complete")

    def cancel(self, task_id: str) -> TaskState:
        return self.transition(task_id, TaskState.CANCELLED, reason="cancel")

    # ------------------------------------------------------------------
    # 门禁 2：Level-1 机械快轨（0 模型调用）
    # ------------------------------------------------------------------

    def tick(
        self,
        now_utc: datetime,
        world_payloads: Mapping[str, dict],
        event_bus: Any,
        *,
        subject_tz_fn: Optional[Callable[[str], str]] = None,
        predicate_resolver: Optional[MechanicalResolver] = None,
    ) -> TickReport:
        """一次机械快轨判定：只碰 Level-1 且仍 DORMANT 的任务。

        保证：
        - 全程 **0 次模型调用**（``report.model_calls == 0``）；
        - **不触碰任何语义轨任务**（``report.semantic_tasks_touched == 0``），
          即不存在周期性语义扫荡（``periodic_todo_sweep_prohibited``）；
        - 判定为 TRUE 的任务自动跃迁 DORMANT -> READY，无需任何模型参与；
        - 单任务判定耗时逐条测量，``max_task_ms`` 供 1ms 门禁断言。
        """
        import time

        if now_utc.tzinfo is None:
            raise SchedulerError("now_utc 必须是 aware datetime")

        # 一次性 drain：见 _ReplayBus 的说明（逐任务 drain 会静默饿死后续任务）
        drained = list(event_bus.drain()) if event_bus is not None else []

        targets = [
            self._tasks[tid] for tid in self._order
            if self._tasks[tid].track == TrackKind.LEVEL1_MECHANICAL
            and self._tasks[tid].state is DORMANT
        ]
        promoted: list = []
        started_all = time.perf_counter()
        max_task_ms = 0.0
        for task in targets:
            started = time.perf_counter()
            evaluator = _ResolvingMechanicalEvaluator(
                now_utc=now_utc,
                world_payloads=world_payloads,
                event_bus=_ReplayBus(drained),
                subject_tz_fn=subject_tz_fn,
                resolver=predicate_resolver,
            )
            verdict = evaluator.evaluate(task.trigger, task.subject)
            task.last_verdict = verdict.value
            if verdict.value is TriState.TRUE:
                self.transition(task.task_id, TaskState.READY, reason="level1_mechanical_true")
                promoted.append(task.task_id)
            elapsed = (time.perf_counter() - started) * 1000
            if elapsed > max_task_ms:
                max_task_ms = elapsed

        return TickReport(
            evaluated=len(targets),
            promoted_to_ready=tuple(promoted),
            still_dormant=len(targets) - len(promoted),
            elapsed_ms=(time.perf_counter() - started_all) * 1000,
            max_task_ms=max_task_ms,
            model_calls=self.meter.model_calls,
            semantic_tasks_touched=0,
        )

    # ------------------------------------------------------------------
    # 门禁 3：Level-2 机会式捎带
    # ------------------------------------------------------------------

    def _sign(self, session_id: str, issued_at: datetime, context: frozenset) -> str:
        payload = "|".join([session_id, issued_at.isoformat(), *sorted(context)])
        return hmac.new(self._token_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def issue_user_wake_token(
        self,
        session_id: str,
        context: Iterable[str],
        *,
        now: Optional[datetime] = None,
    ) -> UserWakeToken:
        """由**驾驶舱在用户主动唤醒 AI 时**签发捎带令牌。

        这是引擎里唯一能产生合法令牌的地方。任务、调度器、心跳都拿不到私钥，
        因此"为了评估休眠任务而自主唤醒大模型"没有可调用路径。
        """
        ctx = frozenset(context)
        unknown = ctx - self._predicate_registry
        if unknown:
            raise SchedulerError(
                f"唤醒情境含未登记谓词：{sorted(unknown)}",
                context={"unknown": sorted(unknown)},
            )
        if not isinstance(session_id, str) or not session_id.strip():
            raise SchedulerError("session_id 必须是非空字符串")
        issued = now or self._clock()
        return UserWakeToken(
            session_id=session_id,
            issued_at=issued,
            context=ctx,
            signature=self._sign(session_id, issued, ctx),
        )

    def piggyback_evaluate(
        self,
        task_id: str,
        wake_token: Optional[UserWakeToken],
        review_fn: Callable[[str, frozenset], Tuple[TriState, int]],
        *,
        now_utc: Optional[datetime] = None,
        world_payloads: Optional[Mapping[str, dict]] = None,
        event_bus: Any = None,
        predicate_resolver: Optional[MechanicalResolver] = None,
    ) -> PiggybackOutcome:
        """Level-2 机会式捎带评估 —— 引擎内**唯一**会调用模型的入口。

        五道前置闸，任一不满足就**不叫模型**：
        1. 任务必须属语义轨（机械轨任务送语义复核是纯浪费）；
        2. 令牌必须存在且 HMAC 校验通过（任务无法伪造用户唤醒）；
        3. 同一令牌对同一任务只能捎带一次（这就是"绝不频繁唤醒"）；
        4. 用户当前情境必须覆盖任务所需情境（不相关场景不顺路）；
        5. 机械前置子树若判 FALSE，直接跳过 —— 机械上就不可能成立的事，
           不值得花一次模型调用去问。
        """
        task = self.task(task_id)
        if task.track != TrackKind.LEVEL2_SEMANTIC:
            raise TrackMismatchError(
                f"任务 {task_id!r} 属 {task.track}，机械轨任务不需要也不允许语义复核",
                context={"task_id": task_id, "track": task.track},
            )
        if wake_token is None:
            raise AutonomousWakeProhibitedError(
                f"任务 {task_id!r} 的语义评估缺少用户主动唤醒令牌："
                "严禁为评估休眠任务而自主唤醒大模型",
                context={"task_id": task_id},
            )
        expected = self._sign(wake_token.session_id, wake_token.issued_at, wake_token.context)
        if not hmac.compare_digest(expected, wake_token.signature):
            raise ForgedWakeTokenError(
                f"唤醒令牌签名不符（任务 {task_id!r}）：令牌只能由驾驶舱在用户主动唤醒时签发",
                context={"task_id": task_id, "session_id": wake_token.session_id},
            )
        key = (wake_token.session_id, task_id)
        if key in self._consumed:
            raise AutonomousWakeProhibitedError(
                f"会话 {wake_token.session_id!r} 已对任务 {task_id!r} 捎带评估过一次："
                "同一次用户唤醒不得反复叫模型",
                context={"task_id": task_id, "session_id": wake_token.session_id},
            )

        missing = task.required_context - wake_token.context
        if missing:
            # 场景不相关是**正常跳过**，不是错误：用户此刻不在该情境里。
            return PiggybackOutcome(
                task_id=task_id, invoked_model=False, verdict=TriState.UNKNOWN,
                reason=f"context_not_relevant:{','.join(sorted(missing))}",
                model_calls=0, tokens=0, promoted_to_ready=False,
            )

        if task.mechanical_prefix is not None and world_payloads is not None:
            evaluator = _ResolvingMechanicalEvaluator(
                now_utc=now_utc or self._clock(),
                world_payloads=world_payloads,
                event_bus=event_bus if event_bus is not None else _ReplayBus(()),
                resolver=predicate_resolver,
            )
            prefix_verdict = evaluator.evaluate(task.mechanical_prefix, task.subject)
            if prefix_verdict.value is TriState.FALSE:
                return PiggybackOutcome(
                    task_id=task_id, invoked_model=False, verdict=TriState.FALSE,
                    reason=f"mechanical_prefix_false:{prefix_verdict.reason}",
                    model_calls=0, tokens=0, promoted_to_ready=False,
                )

        signature = _first_prompt_signature(task.trigger)
        verdict_value, tokens = review_fn(signature, wake_token.context)
        if not isinstance(verdict_value, TriState):
            raise SchedulerError(
                f"复核适配器必须返回法定 TriState，得到 {verdict_value!r}",
                context={"task_id": task_id},
            )
        self.meter.charge(lane="review", tokens=int(tokens), reason=f"piggyback:{task_id}")
        self._consumed.add(key)
        task.review_count += 1
        task.last_verdict = verdict_value

        promoted = False
        if verdict_value is TriState.TRUE and task.state is DORMANT:
            self.transition(task_id, TaskState.READY, reason="level2_piggyback_true")
            promoted = True
        return PiggybackOutcome(
            task_id=task_id, invoked_model=True, verdict=verdict_value,
            reason="reviewed", model_calls=1, tokens=int(tokens),
            promoted_to_ready=promoted,
        )

    # ------------------------------------------------------------------
    # 门禁 1：DORMANT 物理隐形
    # ------------------------------------------------------------------

    def build_manifest(self, subject: Optional[str] = None) -> ManifestBuild:
        """装配单次看板：**只挂载 READY 任务**。

        DORMANT 任务在这里不是"被过滤掉"，而是**从不进入 token 估算路径**：
        循环只对 ``state is READY`` 的任务调用 ``estimate_tokens``。可观测证据有两条，
        都由测试断言：

        - ``estimate_audit()["dormant"]`` 不存在或恒为 0；
        - **不变性**：DORMANT 任务数从 0 增到 N，``token_total`` 分毫不动。
          这一条才是"严禁把所有未成熟任务灌入 LLM Prompt"的真正证明——
          只断言"DORMANT 不在结果里"是不够的，那挡不住"先全量估算再筛掉"的实现。
        """
        slots: list = []
        total = 0
        dormant_population = 0
        for tid in self._order:
            task = self._tasks[tid]
            if task.state is DORMANT:
                dormant_population += 1
                continue  # 物理隐形：不估算、不排序、不进入任何下游
            if task.state is not TaskState.READY:
                continue
            if subject is not None and task.subject != subject:
                continue
            tokens = estimate_tokens(task.title)
            self._charge_estimate(task.state, tokens)
            total += tokens
            slots.append(
                ManifestSlot(
                    task_id=task.task_id, title=task.title,
                    state=task.state.value, tokens=tokens,
                )
            )
        slots.sort(key=lambda s: (-self._tasks[s.task_id].priority, s.task_id))
        return ManifestBuild(
            mounted=tuple(slots),
            token_total=total,
            dormant_population=dormant_population,
            model_calls=self.meter.model_calls,
        )


def _first_prompt_signature(trigger: TriggerExpression) -> str:
    """取出 AST 中第一个语义叶子的 prompt_signature（复核车道的去重键）。"""
    leaf = trigger.leaf
    if isinstance(leaf, SemanticPredicate):
        return leaf.prompt_signature
    for child in trigger.children:
        found = _first_prompt_signature(child)
        if found:
            return found
    return ""
