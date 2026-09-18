"""Non-destructive outbound protocol validation.

R5/R6 assign semantic judgment and communication style to the cognitive model.
This module therefore validates only transport/protocol properties. It never
regex-scores natural language, deletes sentences, truncates prose, or replaces a
model response with a canned fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

__all__ = [
    "MAX_OUTBOUND_BYTES",
    "PersonaDefenseVerdict",
    "PersonaGuard",
]

MAX_OUTBOUND_BYTES = 65_536
_ALLOWED_CONTROLS = {"\t", "\n", "\r"}


@dataclass(frozen=True, slots=True)
class PersonaDefenseVerdict:
    """Protocol verdict that always preserves the candidate bytes/text."""

    text: str
    allowed: bool
    violations: Tuple[str, ...]
    sentences_dropped: int = 0
    brevity_intercepted: bool = False

    @property
    def rewritten(self) -> bool:
        return False


class PersonaGuard:
    """Validate outbound transport shape without making semantic decisions."""

    def __init__(self, *, max_transport_bytes: int = MAX_OUTBOUND_BYTES) -> None:
        if max_transport_bytes <= 0:
            raise ValueError("max_transport_bytes must be positive")
        self.max_transport_bytes = int(max_transport_bytes)

    def review(
        self,
        candidate: str,
        *,
        user_utterance: str = "",
        context: Mapping[str, object] | None = None,
    ) -> PersonaDefenseVerdict:
        """Return protocol findings while preserving candidate exactly."""

        _ = user_utterance, context
        text = "" if candidate is None else str(candidate)
        violations = list(self.detect(text))
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError:
            violations.append("PROTOCOL_INVALID_UNICODE")
        else:
            if len(encoded) > self.max_transport_bytes:
                violations.append(
                    f"PROTOCOL_TRANSPORT_BYTES_EXCEEDED:{len(encoded)}>{self.max_transport_bytes}"
                )
        return PersonaDefenseVerdict(
            text=text,
            allowed=not violations,
            violations=tuple(dict.fromkeys(violations)),
            sentences_dropped=0,
            brevity_intercepted=False,
        )

    def review_all(
        self,
        candidates: Sequence[str],
        *,
        user_utterance: str = "",
    ) -> Tuple[PersonaDefenseVerdict, ...]:
        return tuple(
            self.review(candidate, user_utterance=user_utterance)
            for candidate in candidates
        )

    @staticmethod
    def detect(text: str) -> Tuple[str, ...]:
        """Detect protocol-invalid characters only; never inspect meaning."""

        violations: list[str] = []
        if "\x00" in text:
            violations.append("PROTOCOL_NUL")
        controls = sorted(
            {
                f"U+{ord(char):04X}"
                for char in text
                if ord(char) < 32 and char not in _ALLOWED_CONTROLS and char != "\x00"
            }
        )
        violations.extend(f"PROTOCOL_CONTROL:{code}" for code in controls)
        return tuple(violations)
