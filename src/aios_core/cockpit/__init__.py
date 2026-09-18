"""Cockpit - bounded context assembly for the AIOS cognitive runtime.

CockpitPipeline owns rolling state, evidence projection, and context budgets.
It does not compose, rank, truncate, or rewrite model semantics. BrevityGuard is
kept only as a non-destructive compatibility surface.
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
