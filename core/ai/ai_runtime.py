"""AIRuntime —— 契约来源: 02 §10 AI.

Sprint 1 Task 1 只建立骨架;方法在对应 Task 中实现。
禁止在本文件外绕过 core/ 直接改写世界状态(宪法 第十章:系统间只走标准接口)。
"""
from __future__ import annotations

CONTRACT = "02 §10 AI"
SPRINT = "1"


class AIRuntime:
    """AIRuntime 骨架。"""

    contract = CONTRACT

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} 骨架未实现,见 Sprint {SPRINT} 对应 Task"
        )
    def wake_session(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("AIRuntime.wake_session 未实现 (契约 02 §10 AI)")

    def think(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("AIRuntime.think 未实现 (契约 02 §10 AI)")

    def judge(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("AIRuntime.judge 未实现 (契约 02 §10 AI)")

    def plan(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("AIRuntime.plan 未实现 (契约 02 §10 AI)")

    def reflect(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("AIRuntime.reflect 未实现 (契约 02 §10 AI)")

