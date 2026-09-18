import pytest

from aios_core.communication.experience_tracker import ExperienceTracker
from aios_core.contracts.enums import UserReaction
from aios_core.contracts.models import CommunicationExperience
from aios_core.contracts.time import TemporalExtent, utc_now


@pytest.fixture
def tracker() -> ExperienceTracker:
    return ExperienceTracker()


def create_experience(
    scenario: str, style: str, reaction: UserReaction
) -> CommunicationExperience:
    now = utc_now()
    return CommunicationExperience(
        object_id=f"ce_{now.timestamp()}_{scenario}_{style}_{reaction.value}",
        subject_id="user_1",
        occurred=TemporalExtent(start=now, end=now),
        learned_at=now,
        recorded_at=now,
        source_refs=[],
        created_by="test",
        metadata={},
        scenario=scenario,
        style=style,
        user_reaction=reaction,
    )


def test_record_experience(tracker: ExperienceTracker) -> None:
    exp = create_experience("greeting", "formal", UserReaction.ACCEPTED)
    recorded = tracker.record_experience(exp)
    assert recorded in tracker._experiences
    assert len(tracker._experiences) == 1


def test_get_experiences_by_scenario(tracker: ExperienceTracker) -> None:
    tracker.record_experience(
        create_experience("greeting", "formal", UserReaction.ACCEPTED)
    )
    tracker.record_experience(
        create_experience("farewell", "casual", UserReaction.ACCEPTED)
    )
    greetings = tracker.get_experiences_by_scenario("greeting")
    assert len(greetings) == 1
    assert greetings[0].scenario == "greeting"


def test_success_rate_is_descriptive_only(tracker: ExperienceTracker) -> None:
    tracker.record_experience(
        create_experience("greeting", "formal", UserReaction.ACCEPTED)
    )
    tracker.record_experience(
        create_experience("greeting", "formal", UserReaction.RESISTED)
    )
    tracker.record_experience(
        create_experience("greeting", "formal", UserReaction.ACCEPTED)
    )
    assert tracker.get_success_rate("greeting", "formal") == 2 / 3


def test_reaction_counts_are_observed_facts(tracker: ExperienceTracker) -> None:
    tracker.record_experience(
        create_experience("feedback", "a", UserReaction.ACCEPTED)
    )
    tracker.record_experience(
        create_experience("feedback", "a", UserReaction.RESISTED)
    )
    tracker.record_experience(
        create_experience("feedback", "b", UserReaction.IGNORED)
    )
    assert tracker.get_reaction_counts("feedback") == {
        UserReaction.ACCEPTED.value: 1,
        UserReaction.IGNORED.value: 1,
        UserReaction.RESISTED.value: 1,
    }


def test_style_statistics_do_not_rank_or_ban(tracker: ExperienceTracker) -> None:
    tracker.record_experience(
        create_experience("feedback", "style_a", UserReaction.ACCEPTED)
    )
    tracker.record_experience(
        create_experience("feedback", "style_a", UserReaction.RESISTED)
    )
    tracker.record_experience(
        create_experience("feedback", "style_b", UserReaction.RESISTED)
    )
    stats = tracker.get_style_statistics("feedback")
    assert stats["style_a"]["samples"] == 2
    assert stats["style_a"]["acceptance_rate"] == 0.5
    assert stats["style_b"]["resistance_rate"] == 1.0
    assert not hasattr(tracker, "get_effective_style")
    assert not hasattr(tracker, "get_avoidance_list")
    assert not hasattr(tracker, "evolve_strategy")


def test_empty_scenario_is_empty_evidence(tracker: ExperienceTracker) -> None:
    assert tracker.get_success_rate("unknown", "style") == 0.0
    assert tracker.get_reaction_counts("unknown") == {}
    assert tracker.get_style_statistics("unknown") == {}
