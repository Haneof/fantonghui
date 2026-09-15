"""Cockpit - 单次看盘组装流水线（M2-009R）。

R3-ARCH C10「认知工作台」的 Token 预算封套实现：
单次看板 ≤ 1500 tokens 物理硬截断、6 轮无损滚动窗口、Brevity Guard
（1~3 句老友语调治理）。宪法依据：V3 §84（单次看盘聚合）、§85（上下文
精准组装）、§14-1（反长篇大论）。
"""

from .pipeline import (
    BrevityGuard,
    CockpitManifest,
    ConversationTurn,
    CrisisDialoguePipeline,
    GovernedReply,
    MANIFEST_TOKEN_BUDGET,
    OmissionEntry,
    WINDOW_TURNS,
    estimate_tokens,
)

__all__ = [
    "BrevityGuard",
    "CockpitManifest",
    "ConversationTurn",
    "CrisisDialoguePipeline",
    "GovernedReply",
    "MANIFEST_TOKEN_BUDGET",
    "OmissionEntry",
    "WINDOW_TURNS",
    "estimate_tokens",
]
