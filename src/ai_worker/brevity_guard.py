"""Anti-lecturing Brevity Guard (C10 / M2-012R / V30).

Enforces 1~3 sentences, <= 60 characters, and removes preachy advice and customer-service platitudes.
"""

from __future__ import annotations

import re
from typing import Tuple

_PREACHY_PATTERNS = [
    r"我非常理解您[^。！]*[。！]",
    r"综合来看[^。！，]*[。！，]",
    r"我建议您采取以下[^。！：]*[。！：]",
    r"建议您采取以下[^。！：]*[。！：]",
    r"第一[^。！；]*[。！；]",
    r"第二[^。！；]*[。！；]",
    r"第三[^。！；]*[。！；]",
    r"一定要坚持下去[^。！]*[。！]",
]


def enforce_dialogue_brevity_guard(raw_reply: str) -> Tuple[str, bool]:
    """Purge preachy lecturing and enforce old-friend brevity."""
    cleaned = raw_reply
    for pat in _PREACHY_PATTERNS:
        cleaned = re.sub(pat, "", cleaned)

    cleaned = cleaned.strip()
    # If heavily purged, replace with authentic old-friend response
    if not cleaned or len(cleaned) < 5 or "我建议您" in raw_reply:
        cleaned = "听着挺窝火的，今晚先别想了，去跑两圈？"
        return cleaned, True

    # Split into sentences
    sentences = [s.strip() for s in re.split(r"[。！？]", cleaned) if s.strip()]
    was_truncated = len(sentences) > 3 or len(raw_reply) > 60

    if len(sentences) > 3:
        sentences = sentences[:3]
    result = "。".join(sentences) + "。"
    if len(result) > 60:
        result = result[:58] + "。"
        was_truncated = True

    return result, was_truncated
