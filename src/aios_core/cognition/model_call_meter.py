"""大模型调用计量器（Model Call Meter）—— 铁律 3 / 铁律 2 的审计口径。

为什么必须有独立计量器
----------------------
"P0 紧急事件大模型调用次数严格为 0"、"老王案单跳隔离禁止 210 次 API 算力雪崩"
这两条铁律如果只靠调用方自报（"我这次没调模型"），就是不可证伪的口号。本计量器
把"我要调大模型"这个动作变成一次**显式记账**：任何真正会消耗算力的推理入口
都必须先 ``meter.charge(...)``；测试与审计只读 ``meter.total`` 与 ``meter.entries``，
因此 "0 次" 是**代码路径级**的断言，而不是口头承诺。

计量器可注入、可快照、可差分：

* :meth:`ModelCallMeter.snapshot` 返回不可变快照，供"操作前 / 操作后"差分断言；
* :meth:`ModelCallMeter.delta` 直接给出某段区间内新增的调用明细；
* 预算是硬约束：``max_calls`` 用尽后再记账会抛 :class:`ModelBudgetExceeded`
  （与宪法第 86 条之一的经济控制同族语义）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

__all__ = [
    "ModelBudgetExceeded",
    "ModelCallEntry",
    "ModelCallMeter",
    "ModelCallSnapshot",
    "DEFAULT_METER",
]


class ModelBudgetExceeded(RuntimeError):
    """预算耗尽仍然试图调用大模型 —— fail-closed，绝不静默放行。"""


@dataclass(frozen=True, slots=True)
class ModelCallEntry:
    """一次大模型调用的记账条目（谁在什么路径上花了算力）。"""

    kind: str
    detail: str
    cost: int = 1


@dataclass(frozen=True, slots=True)
class ModelCallSnapshot:
    """调用计量的不可变快照。"""

    total: int
    total_cost: int
    entries: tuple[ModelCallEntry, ...]

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({entry.kind for entry in self.entries}))


@dataclass
class ModelCallMeter:
    """线程安全的显式大模型调用计量器。"""

    name: str = "primary"
    max_calls: int | None = None
    _entries: list[ModelCallEntry] = field(default_factory=list)
    _cost: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ------------------------------------------------------------------

    def charge(self, kind: str, detail: str = "", *, cost: int = 1) -> ModelCallEntry:
        """记一次（或将记录）大模型调用；预算耗尽即抛异常。"""

        if cost < 1:
            raise ValueError("cost must be >= 1")
        entry = ModelCallEntry(kind=kind, detail=detail, cost=cost)
        with self._lock:
            if self.max_calls is not None and len(self._entries) + 1 > self.max_calls:
                raise ModelBudgetExceeded(
                    f"model call budget exhausted: {len(self._entries)}/{self.max_calls} "
                    f"(attempted kind={kind!r})"
                )
            self._entries.append(entry)
            self._cost += cost
        return entry

    def snapshot(self) -> ModelCallSnapshot:
        with self._lock:
            return ModelCallSnapshot(
                total=len(self._entries),
                total_cost=self._cost,
                entries=tuple(self._entries),
            )

    def delta(self, before: ModelCallSnapshot) -> ModelCallSnapshot:
        """返回相对 ``before`` 的新增调用（差分断言的标准入口）。"""

        with self._lock:
            entries = self._entries[before.total :]
            return ModelCallSnapshot(
                total=len(entries),
                total_cost=sum(entry.cost for entry in entries),
                entries=tuple(entries),
            )

    @property
    def total(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def total_cost(self) -> int:
        with self._lock:
            return self._cost

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._cost = 0

    # ------------------------------------------------------------------

    def assert_untouched(self, before: ModelCallSnapshot, *, context: str) -> None:
        """断言某段代码路径**零**大模型调用（违例时给出差分明细）。"""

        delta = self.delta(before)
        if delta.total:
            details = "; ".join(
                f"{entry.kind}:{entry.detail}" for entry in delta.entries[:5]
            )
            raise AssertionError(
                f"{context} must not call the model, but recorded "
                f"{delta.total} call(s): {details}"
            )


#: 进程级默认计量器（生产路径注入共用；测试可注入私有实例做隔离）。
DEFAULT_METER = ModelCallMeter(name="default")
