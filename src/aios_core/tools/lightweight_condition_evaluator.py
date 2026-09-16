"""轻量条件事件求值器（LightweightConditionEvaluator：零 Token 空转的门槛判断）。

问题
----
"等到某个条件满足再叫我"这类条件任务，如果每次都把任务清单塞进大模型
prompt 里问一遍，就会产生大量 **零信息量的 Token 空转**：条件没满足，
却每轮都要烧钱。宪法要求条件任务"双轨休眠、零 Token 空转"。

本求值器做什么
--------------
把条件编译成**机械判定器**，并用倒排索引把"与本轮信号无关的任务"直接跳过：

1. 条件种类：``TIME_ARRIVAL``（到期）/ ``BIOMETRIC_THRESHOLD``（生理阈值）/
   ``KEYWORD_MATCH``（关键词命中）/ ``GEO_ENTER``（进入地理簇）；
2. 索引：时间条件进有序索引（二分），生理条件按指标建倒排，
   关键词条件按词建倒排，地理条件按簇建倒排 —— 一次信号只触碰相关任务；
3. **Token 严格为 0**：本求值器不含任何大模型调用，``tokens_spent == 0``、
   ``llm_calls == 0`` 是可审计的硬事实；
4. 只输出"是否触发"这一布尔事实，**不做语义推断、不生成话术**（话术属于认知层）。
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

__all__ = [
    "CompiledCondition",
    "ConditionEvaluation",
    "ConditionError",
    "LightweightConditionEvaluator",
    "TaskTriggerReport",
]

_TIME = "TIME_ARRIVAL"
_BIOMETRIC = "BIOMETRIC_THRESHOLD"
_KEYWORD = "KEYWORD_MATCH"
_GEO = "GEO_ENTER"
_KINDS = (_TIME, _BIOMETRIC, _KEYWORD, _GEO)

_OPERATORS = {
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
}


class ConditionError(ValueError):
    """条件协议错误。"""


def _as_utc(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ConditionError(f"{field_name} must be datetime or ISO string")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class CompiledCondition:
    """编译后的单条条件（机械判定，不含语义）。"""

    kind: str
    index_keys: tuple[str, ...]
    payload: Mapping[str, Any]

    def matches_signal(self, signal: Mapping[str, Any]) -> bool:
        if self.kind == _BIOMETRIC:
            metric = str(signal.get("metric", ""))
            if metric != str(self.payload.get("metric")):
                return False
            value = signal.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            operator = _OPERATORS[str(self.payload.get("op", ">="))]
            return bool(operator(float(value), float(self.payload.get("value", 0.0))))
        if self.kind == _KEYWORD:
            text = str(signal.get("text", ""))
            return str(self.payload.get("keyword", "")) in text
        if self.kind == _GEO:
            cluster = str(signal.get("cluster", ""))
            return cluster == str(self.payload.get("cluster", ""))
        if self.kind == _TIME:
            moment = signal.get("now")
            if moment is None:
                return False
            return _as_utc(moment, "now") >= _as_utc(self.payload["at"], "at")
        raise ConditionError(f"unknown condition kind {self.kind!r}")

    def matches_moment(self, moment: datetime) -> bool:
        return self.kind == _TIME and moment >= _as_utc(self.payload["at"], "at")


def _compile(raw: Mapping[str, Any]) -> CompiledCondition:
    kind = str(raw.get("kind", "")).strip().upper()
    if kind not in _KINDS:
        raise ConditionError(f"unknown condition kind {raw.get('kind')!r}")
    if kind == _TIME:
        at = _as_utc(raw.get("at"), "at")
        return CompiledCondition(
            kind=kind, index_keys=(f"time:{at.isoformat()}",), payload={"at": at}
        )
    if kind == _BIOMETRIC:
        metric = str(raw.get("metric", "")).strip()
        op = str(raw.get("op", ">=")).strip()
        if not metric:
            raise ConditionError("BIOMETRIC_THRESHOLD requires a metric")
        if op not in _OPERATORS:
            raise ConditionError(f"unknown operator {op!r}")
        value = float(raw.get("value", 0.0))
        return CompiledCondition(
            kind=kind,
            index_keys=(f"metric:{metric}",),
            payload={"metric": metric, "op": op, "value": value},
        )
    if kind == _KEYWORD:
        keyword = str(raw.get("keyword", "")).strip()
        if not keyword:
            raise ConditionError("KEYWORD_MATCH requires a keyword")
        return CompiledCondition(
            kind=kind, index_keys=(f"keyword:{keyword}",), payload={"keyword": keyword}
        )
    cluster = str(raw.get("cluster", "")).strip()
    if not cluster:
        raise ConditionError("GEO_ENTER requires a cluster")
    return CompiledCondition(kind=kind, index_keys=(f"cluster:{cluster}",), payload={"cluster": cluster})


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    """单个条件任务的判定结果。"""

    task_id: str
    triggered: bool
    matched_condition_indexes: tuple[int, ...]
    skipped: bool


@dataclass(frozen=True, slots=True)
class TaskTriggerReport:
    """一轮信号求值的整体结果（含"跳过了什么"的审计）。"""

    triggered_task_ids: tuple[str, ...]
    evaluated_task_ids: tuple[str, ...]
    skipped_task_ids: tuple[str, ...]
    index_reads: int
    tokens_spent: int = 0
    llm_calls: int = 0

    @property
    def evaluated_count(self) -> int:
        return len(self.evaluated_task_ids)

    @property
    def skip_ratio(self) -> float:
        total = self.evaluated_count + len(self.skipped_task_ids)
        return (len(self.skipped_task_ids) / total) if total else 0.0


class LightweightConditionEvaluator:
    """把条件任务编译成机械判定器 + 倒排索引（零 Token 空转）。"""

    def __init__(self) -> None:
        self._conditions: Dict[str, tuple[CompiledCondition, ...]] = {}
        self._triggered: Dict[str, bool] = {}
        self._index: Dict[str, set[str]] = {}
        self._time_index: list[tuple[datetime, str]] = []
        self._evaluations = 0
        self._index_reads = 0
        self._llm_calls = 0
        self._tokens_spent = 0

    # ------------------------------------------------------------------
    # 登记 / 撤销
    # ------------------------------------------------------------------

    def register(self, task_id: str, conditions: Iterable[Mapping[str, Any]]) -> None:
        key = str(task_id).strip()
        if not key:
            raise ConditionError("task_id must be non-empty")
        compiled = tuple(_compile(condition) for condition in conditions)
        if not compiled:
            raise ConditionError("a conditional task requires at least one condition")
        self._conditions[key] = compiled
        self._triggered.setdefault(key, False)
        for condition in compiled:
            for index_key in condition.index_keys:
                self._index.setdefault(index_key, set()).add(key)
            if condition.kind == _TIME:
                bisect.insort(self._time_index, (condition.payload["at"], key))

    def archive(self, task_id: str) -> bool:
        """条件任务销号（物理摘除索引，杜绝僵尸任务继续占位）。"""

        key = str(task_id)
        conditions = self._conditions.pop(key, None)
        self._triggered.pop(key, None)
        if conditions is None:
            return False
        for condition in conditions:
            for index_key in condition.index_keys:
                bucket = self._index.get(index_key)
                if bucket is not None:
                    bucket.discard(key)
                    if not bucket:
                        self._index.pop(index_key, None)
            if condition.kind == _TIME:
                self._time_index = [
                    (moment, holder)
                    for moment, holder in self._time_index
                    if holder != key
                ]
        return True

    # ------------------------------------------------------------------
    # 求值
    # ------------------------------------------------------------------

    def evaluate_signal(self, signal: Mapping[str, Any]) -> TaskTriggerReport:
        """按信号触碰的索引桶求值：无关任务一律跳过（零 Token）。"""

        touched: set[str] = set()
        reads = 0
        if "metric" in signal:
            reads += 1
            touched |= self._index.get(f"metric:{signal['metric']}", set())
        if "text" in signal:
            reads += 1
            for index_key, bucket in self._index.items():
                if index_key.startswith("keyword:") and index_key.split(":", 1)[1] in str(
                    signal["text"]
                ):
                    touched |= bucket
        if "cluster" in signal:
            reads += 1
            touched |= self._index.get(f"cluster:{signal['cluster']}", set())
        if "now" in signal:
            reads += 1
            touched |= {
                holder
                for moment, holder in self._time_index
                if moment <= _as_utc(signal["now"], "now")
            }
        return self._finalize(signal, touched, reads)

    def evaluate_time(self, moment: datetime) -> TaskTriggerReport:
        """纯时间求值：二分定位到期条件，其余任务直接跳过。"""

        cutoff = _as_utc(moment, "moment")
        keys = [item[0] for item in self._time_index]
        position = bisect.bisect_right(keys, cutoff)
        touched = {holder for _moment, holder in self._time_index[:position]}
        return self._finalize({"now": cutoff}, touched, 1)

    def _finalize(
        self, signal: Mapping[str, Any], touched: set[str], reads: int
    ) -> TaskTriggerReport:
        triggered: list[str] = []
        evaluated: list[str] = []
        skipped: list[str] = []
        for task_id, conditions in self._conditions.items():
            if task_id not in touched:
                skipped.append(task_id)
                continue
            evaluated.append(task_id)
            matched = tuple(
                index
                for index, condition in enumerate(conditions)
                if condition.matches_signal(signal)
            )
            if len(matched) == len(conditions):
                self._triggered[task_id] = True
                triggered.append(task_id)
        self._evaluations += 1
        self._index_reads += reads
        return TaskTriggerReport(
            triggered_task_ids=tuple(sorted(triggered)),
            evaluated_task_ids=tuple(sorted(evaluated)),
            skipped_task_ids=tuple(sorted(skipped)),
            index_reads=reads,
            tokens_spent=0,
            llm_calls=0,
        )

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    @property
    def task_count(self) -> int:
        return len(self._conditions)

    @property
    def dormant_count(self) -> int:
        return sum(1 for task_id in self._conditions if not self._triggered.get(task_id, False))

    @property
    def triggered_tasks(self) -> tuple[str, ...]:
        return tuple(sorted(task for task, hit in self._triggered.items() if hit))

    @property
    def tokens_spent(self) -> int:
        return self._tokens_spent

    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def index_reads(self) -> int:
        return self._index_reads

    def index_key_count(self) -> int:
        return len(self._index)

    def index_size(self) -> int:
        return sum(len(bucket) for bucket in self._index.values())

    def conditions_of(self, task_id: str) -> tuple[CompiledCondition, ...]:
        return self._conditions.get(str(task_id), ())

    def audit(self) -> Dict[str, Any]:
        return {
            "tasks": self.task_count,
            "dormant": self.dormant_count,
            "triggered": len(self.triggered_tasks),
            "evaluations": self._evaluations,
            "index_reads": self._index_reads,
            "index_keys": self.index_key_count(),
            "tokens_spent": self._tokens_spent,
            "llm_calls": self._llm_calls,
        }
