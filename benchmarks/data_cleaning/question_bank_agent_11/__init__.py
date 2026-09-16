"""Agent-11 出题器包：为 AIOS 3.0 云端对抗大考生成 10,000 道高熵多模态清洗考题。

用法::

    python -m question_bank_agent_11 --agent-id agent-11 --out-root benchmarks/data_cleaning
"""

from __future__ import annotations

from .builder import QuestionBuilder, split_ground_truth, strip_ground_truth

__all__ = ["QuestionBuilder", "split_ground_truth", "strip_ground_truth"]
__version__ = "1.0.0"
