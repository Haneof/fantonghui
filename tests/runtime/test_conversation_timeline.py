"""Raw dialogue must remain durable and append-only independent of summaries/state."""

from datetime import datetime, timezone

import pytest

from aios_core.runtime.conversation_timeline import (
    ConversationTimelineConflict,
    ConversationTimelineStore,
    ConversationTurn,
)

UTC = timezone.utc


def test_raw_turns_are_append_only_and_replay_idempotent(tmp_path):
    store = ConversationTimelineStore(tmp_path / "world.db")
    t1 = ConversationTurn.create(
        session_id="ses_1",
        turn_index=1,
        user_text="老王那笔钱你还记得吗？",
        assistant_text="记得，我先查一下原始记录。",
        occurred_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 8, 0, 1, tzinfo=UTC),
    )
    t2 = ConversationTurn.create(
        session_id="ses_1",
        turn_index=2,
        user_text="我刚收到银行流水。",
        assistant_text="把流水和之前的借款记录一起对一下。",
        occurred_at=datetime(2026, 9, 18, 8, 1, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 8, 1, 1, tzinfo=UTC),
    )

    store.append(t1)
    store.append(t2)
    assert store.append(t2) == t2
    assert store.list_turns("ses_1") == [t1, t2]


def test_raw_turn_slot_cannot_be_rewritten(tmp_path):
    store = ConversationTimelineStore(tmp_path / "world.db")
    sealed = ConversationTurn.create(
        session_id="ses_1",
        turn_index=1,
        user_text="原话",
        assistant_text="原回复",
        occurred_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 8, 0, 1, tzinfo=UTC),
    )
    store.append(sealed)

    changed = ConversationTurn.create(
        session_id="ses_1",
        turn_index=1,
        user_text="被改写的原话",
        assistant_text="原回复",
        occurred_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 8, 0, 1, tzinfo=UTC),
    )
    with pytest.raises(ConversationTimelineConflict):
        store.append(changed)


def test_turn_indices_must_be_contiguous(tmp_path):
    store = ConversationTimelineStore(tmp_path / "world.db")
    turn2 = ConversationTurn.create(
        session_id="ses_1",
        turn_index=2,
        user_text="跳过第一轮",
        assistant_text="不允许",
        occurred_at=datetime(2026, 9, 18, 8, 1, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 18, 8, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ConversationTimelineConflict):
        store.append(turn2)
