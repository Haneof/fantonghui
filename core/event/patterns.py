"""Patterns —— 契约来源: 04 §7 算法清单.

Sprint 1 Task 1 只建立骨架;方法在对应 Task 中实现。
禁止在本文件外绕过 core/ 直接改写世界状态(宪法 第十章:系统间只走标准接口)。
"""
from __future__ import annotations

CONTRACT = "04 §7 算法清单"
SPRINT = "1"


class Patterns:
    """Patterns 骨架。"""

    contract = CONTRACT

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} 骨架未实现,见 Sprint {SPRINT} 对应 Task"
        )
    def detect(self, *args, **kwargs):  # pragma: no cover - 骨架
        raise NotImplementedError("Patterns.detect 未实现 (契约 04 §7 算法清单)")

