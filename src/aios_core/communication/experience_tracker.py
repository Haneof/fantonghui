"""Evidence-only communication experience history.

The tracker records what happened. It does not recommend a style, ban a style,
or turn reaction rates into a cognitive decision. Those decisions belong to the
cognitive model/runtime.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from aios_core.contracts.enums import UserReaction
from aios_core.contracts.models import CommunicationExperience


class ExperienceTracker:
    def __init__(self) -> None:
        self._experiences: list[CommunicationExperience] = []

    def record_experience(
        self, experience: CommunicationExperience
    ) -> CommunicationExperience:
        self._experiences.append(experience)
        return experience

    def get_experiences_by_scenario(
        self, scenario: str
    ) -> list[CommunicationExperience]:
        return [e for e in self._experiences if e.scenario == scenario]

    def get_success_rate(self, scenario: str, style: str) -> float:
        """Historical acceptance rate only; never a recommendation."""

        experiences = [
            e
            for e in self._experiences
            if e.scenario == scenario and e.style == style
        ]
        if not experiences:
            return 0.0
        accepted = sum(
            1 for e in experiences if e.user_reaction is UserReaction.ACCEPTED
        )
        return accepted / len(experiences)

    def get_reaction_counts(self, scenario: str) -> dict[str, int]:
        """Observed reaction counts for one scenario."""

        counts = Counter(
            e.user_reaction.value
            for e in self.get_experiences_by_scenario(scenario)
        )
        return dict(sorted(counts.items()))

    def get_style_statistics(
        self, scenario: str
    ) -> dict[str, dict[str, float | int]]:
        """Observed per-style frequencies and rates, with no ranking."""

        buckets: dict[str, list[CommunicationExperience]] = defaultdict(list)
        for experience in self.get_experiences_by_scenario(scenario):
            buckets[experience.style].append(experience)

        result: dict[str, dict[str, float | int]] = {}
        for style, experiences in sorted(buckets.items()):
            total = len(experiences)
            accepted = sum(
                1 for e in experiences if e.user_reaction is UserReaction.ACCEPTED
            )
            resisted = sum(
                1 for e in experiences if e.user_reaction is UserReaction.RESISTED
            )
            ignored = sum(
                1 for e in experiences if e.user_reaction is UserReaction.IGNORED
            )
            unknown = sum(
                1 for e in experiences if e.user_reaction is UserReaction.UNKNOWN
            )
            result[style] = {
                "samples": total,
                "accepted": accepted,
                "resisted": resisted,
                "ignored": ignored,
                "unknown": unknown,
                "acceptance_rate": accepted / total if total else 0.0,
                "resistance_rate": resisted / total if total else 0.0,
            }
        return result
