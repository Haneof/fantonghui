"""Evaluator - 隐藏真值、评分、强基线。

提供标准入口，挂载底层 BlindBenchHarness 自动化合宪性评分。
此包保存测试用隐藏答案，绝不能被 aios_core 依赖。
aios_core -> evaluator 绝对禁止。
"""

from .audit_evaluator_entry import (
    BenchRunResult,
    BlindBenchHarness,
    StageReport,
)

__all__ = [
    "BenchRunResult",
    "BlindBenchHarness",
    "StageReport",
]
