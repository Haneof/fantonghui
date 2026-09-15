"""Cockpit - Single-Shot 单看板流水线（M2-009R）。

- ``CockpitPipeline``：6 轮无损滚动窗口 + 争议证据链 + 1500 Token 硬预算组装；
- ``BrevityGuard``：反爹味极简老友语调护栏（1~3 句，说教强制截断与拦截）；
- ``estimate_tokens``：确定性上界 Token 估算（物理预算的唯一度量）。
"""
from .pipeline import (
    ACTIVITY_WINDOW_SIZE,
    SINGLE_SHOT_TOKEN_BUDGET,
    BrevityGuard,
    BrevityVerdict,
    CockpitPipeline,
    ConversationRound,
    ConversationState,
    RoundResult,
    RollingRoundWindow,
    SingleShotCockpit,
    estimate_tokens,
)

__all__ = [
    "ACTIVITY_WINDOW_SIZE",
    "SINGLE_SHOT_TOKEN_BUDGET",
    "BrevityGuard",
    "BrevityVerdict",
    "CockpitPipeline",
    "ConversationRound",
    "ConversationState",
    "RoundResult",
    "RollingRoundWindow",
    "SingleShotCockpit",
    "estimate_tokens",
]
