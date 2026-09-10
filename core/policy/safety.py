"""SafetyRuntime —— 契约来源: 02 §8 Lease / 宪法 5.2.

Sprint 1 Task 1 只建立骨架;方法在对应 Task 中实现。
禁止在本文件外绕过 core/ 直接改写世界状态(宪法 第十章:系统间只走标准接口)。
"""
from __future__ import annotations

CONTRACT = "02 §8 Lease / 宪法 5.2"
SPRINT = "1"


class SafetyRuntime:
    """SafetyRuntime 骨架。"""

    contract = CONTRACT

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} 骨架未实现,见 Sprint {SPRINT} 对应 Task"
        )
    def evaluate(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("SafetyRuntime.evaluate 未实现 (契约 02 §8 Lease / 宪法 5.2)")

    def request_emergency_lease(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("SafetyRuntime.request_emergency_lease 未实现 (契约 02 §8 Lease / 宪法 5.2)")

