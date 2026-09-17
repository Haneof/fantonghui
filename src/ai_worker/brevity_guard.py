"""Dialogue style compatibility guard for AIOS 3.0.

Historical versions hard-truncated replies to 1~3 sentences / 60 characters and
rewrote content with regular expressions. That behavior confused a conversational
style preference with a semantic hard boundary and could overwrite the AI's own
judgment.

Brevity is now a soft preference: simple things should usually be said simply;
when the situation needs explanation, the AI may expand freely. The legacy
function signature is retained for compatibility, but this module never deletes,
truncates, or substitutes semantic content.
"""

from __future__ import annotations

from typing import Tuple


DEFAULT_DIALOGUE_STYLE_HINT = (
    "自然、口语化；简单事情尽量简短直接，需要解释时充分展开。"
    "不要为了满足固定句数或字数而删除、截断或替换语义。"
)


def enforce_dialogue_brevity_guard(raw_reply: str) -> Tuple[str, bool]:
    """Compatibility shim that preserves the AI reply exactly as generated.

    The returned boolean preserves the historical call contract and is always
    ``False`` because destructive truncation/rewrite is no longer permitted.
    """
    return raw_reply, False
