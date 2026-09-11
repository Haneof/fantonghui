"""CognitiveWorld —— 契约来源: 05 §2 / 宪法 6.5.

Sprint 1 Task 1 只建立骨架;方法在对应 Task 中实现。
禁止在本文件外绕过 core/ 直接改写世界状态(宪法 第十章:系统间只走标准接口)。
"""
from __future__ import annotations

CONTRACT = "05 §2 / 宪法 6.5"
SPRINT = "1"


class CognitiveWorld:
    """CognitiveWorld 骨架。"""

    contract = CONTRACT

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} 骨架未实现,见 Sprint {SPRINT} 对应 Task"
        )
    def load(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("CognitiveWorld.load 未实现 (契约 05 §2 / 宪法 6.5)")

    def propose_update(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("CognitiveWorld.propose_update 未实现 (契约 05 §2 / 宪法 6.5)")

