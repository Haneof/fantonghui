"""MemoryRuntime —— 契约来源: 02 §4 Memory.

Sprint 1 Task 1 只建立骨架;方法在对应 Task 中实现。
禁止在本文件外绕过 core/ 直接改写世界状态(宪法 第十章:系统间只走标准接口)。
"""
from __future__ import annotations

CONTRACT = "02 §4 Memory"
SPRINT = "1"


class MemoryRuntime:
    """MemoryRuntime 骨架。"""

    contract = CONTRACT

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} 骨架未实现,见 Sprint {SPRINT} 对应 Task"
        )
    def append_fact(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("MemoryRuntime.append_fact 未实现 (契约 02 §4 Memory)")

    def summarize(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("MemoryRuntime.summarize 未实现 (契约 02 §4 Memory)")

    def drill_down(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("MemoryRuntime.drill_down 未实现 (契约 02 §4 Memory)")

    def index(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("MemoryRuntime.index 未实现 (契约 02 §4 Memory)")

