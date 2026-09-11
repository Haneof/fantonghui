"""InteractionRuntime —— 契约来源: 02 §12 Interaction.

Sprint 1 Task 1 只建立骨架;方法在对应 Task 中实现。
禁止在本文件外绕过 core/ 直接改写世界状态(宪法 第十章:系统间只走标准接口)。
"""
from __future__ import annotations

CONTRACT = "02 §12 Interaction"
SPRINT = "1"


class InteractionRuntime:
    """InteractionRuntime 骨架。"""

    contract = CONTRACT

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} 骨架未实现,见 Sprint {SPRINT} 对应 Task"
        )
    def enqueue(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("InteractionRuntime.enqueue 未实现 (契约 02 §12 Interaction)")

    def deliver(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("InteractionRuntime.deliver 未实现 (契约 02 §12 Interaction)")

    def open_session(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("InteractionRuntime.open_session 未实现 (契约 02 §12 Interaction)")

