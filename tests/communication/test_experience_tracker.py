import pytest
from aios_core.contracts.enums import UserReaction
from aios_core.contracts.models import CommunicationExperience
from aios_core.contracts.time import utc_now, TemporalExtent
from aios_core.communication.experience_tracker import ExperienceTracker
from datetime import timedelta

@pytest.fixture
def tracker():
    return ExperienceTracker()

def create_experience(scenario: str, style: str, reaction: UserReaction) -> CommunicationExperience:
    now = utc_now()
    return CommunicationExperience(
        object_id=f"ce_{now.timestamp()}",
        subject_id="user_1",
        occurred=TemporalExtent(start=now, end=now),
        learned_at=now,
        recorded_at=now,
        source_refs=[],
        created_by="test",
        metadata={},
        scenario=scenario,
        style=style,
        user_reaction=reaction
    )

def test_record_experience(tracker):
    exp = create_experience("greeting", "formal", UserReaction.ACCEPTED)
    recorded = tracker.record_experience(exp)
    assert recorded in tracker._experiences
    assert len(tracker._experiences) == 1

def test_get_experiences_by_scenario(tracker):
    tracker.record_experience(create_experience("greeting", "formal", UserReaction.ACCEPTED))
    tracker.record_experience(create_experience("farewell", "casual", UserReaction.ACCEPTED))
    
    greetings = tracker.get_experiences_by_scenario("greeting")
    assert len(greetings) == 1
    assert greetings[0].scenario == "greeting"

def test_get_success_rate(tracker):
    tracker.record_experience(create_experience("greeting", "formal", UserReaction.ACCEPTED))
    tracker.record_experience(create_experience("greeting", "formal", UserReaction.RESISTED))
    tracker.record_experience(create_experience("greeting", "formal", UserReaction.ACCEPTED))
    
    rate = tracker.get_success_rate("greeting", "formal")
    assert rate == 2 / 3

def test_get_effective_style(tracker):
    # casual has 100% success, formal has 50% success
    tracker.record_experience(create_experience("greeting", "formal", UserReaction.ACCEPTED))
    tracker.record_experience(create_experience("greeting", "formal", UserReaction.RESISTED))
    tracker.record_experience(create_experience("greeting", "casual", UserReaction.ACCEPTED))
    
    best_style = tracker.get_effective_style("greeting")
    assert best_style == "casual"

def test_get_avoidance_list(tracker):
    # formal has 100% resisted, casual has 0% resisted, sarcastic has 50% resisted (threshold is 0.5)
    tracker.record_experience(create_experience("feedback", "formal", UserReaction.RESISTED))
    tracker.record_experience(create_experience("feedback", "casual", UserReaction.ACCEPTED))
    tracker.record_experience(create_experience("feedback", "sarcastic", UserReaction.RESISTED))
    tracker.record_experience(create_experience("feedback", "sarcastic", UserReaction.ACCEPTED))
    
    avoid = tracker.get_avoidance_list("feedback", threshold=0.5)
    assert "formal" in avoid
    assert "sarcastic" in avoid
    assert "casual" not in avoid
    assert len(avoid) == 2

def test_evolve_strategy(tracker):
    tracker.record_experience(create_experience("feedback", "casual", UserReaction.ACCEPTED))
    tracker.record_experience(create_experience("feedback", "formal", UserReaction.RESISTED))
    
    strategy = tracker.evolve_strategy("feedback")
    assert strategy["scenario"] == "feedback"
    assert strategy["recommended_style"] == "casual"
    assert "formal" in strategy["avoid_styles"]

def test_empty_scenario(tracker):
    assert tracker.get_success_rate("unknown", "style") == 0.0
    assert tracker.get_effective_style("unknown") is None
    assert tracker.get_avoidance_list("unknown") == []
    
    strategy = tracker.evolve_strategy("unknown")
    assert strategy["recommended_style"] == "default"
    assert strategy["avoid_styles"] == []

def test_multiple_styles_comparison(tracker):
    styles_reactions = [
        ("style1", UserReaction.ACCEPTED),
        ("style1", UserReaction.IGNORED),
        ("style2", UserReaction.ACCEPTED),
        ("style2", UserReaction.ACCEPTED),
        ("style3", UserReaction.RESISTED),
    ]
    for style, reaction in styles_reactions:
        tracker.record_experience(create_experience("test_scene", style, reaction))
        
    assert tracker.get_effective_style("test_scene") == "style2"
    avoid = tracker.get_avoidance_list("test_scene")
    assert "style3" in avoid
    assert "style1" not in avoid
