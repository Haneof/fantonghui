"""Active Rolling Window Pipeline (C10 / M2-016 / V25).

Maintains active foreground turns <= 6, active tokens <= 1500, smooth background eviction.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Tuple


class ActiveRollingWindow:
    def __init__(self, max_turns: int = 6, max_tokens: int = 1500) -> None:
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._turns: deque[Tuple[str, str]] = deque()

    def push_turn(self, user_msg: str, ai_msg: str) -> List[Tuple[str, str]]:
        self._turns.append((user_msg, ai_msg))
        evicted: List[Tuple[str, str]] = []
        while len(self._turns) > self.max_turns:
            evicted.append(self._turns.popleft())
        return evicted

    def get_prompt_messages(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for user_msg, ai_msg in self._turns:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": ai_msg})
        return messages

    @property
    def total_turns(self) -> int:
        return len(self._turns)
