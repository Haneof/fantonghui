"""Conversation Working State must be durable, versioned and evidence-linked."""

from datetime import datetime, timezone

import pytest

from aios_core.runtime.conversation_state import (
    ConversationStateConflict,
    ConversationStateStore,
    ConversationWorkingState,
)

UTC = timezone.utc


def test_conversation_state_is_append_only_and_recoverable(tmp_path):
    store = ConversationStateStore(tmp_path / "world.db")
    v1 = ConversationWorkingState(
        session_id="ses_1",
        version=1,
        current_topic="老王借款",
        open_loops=("确认还款日期",),
        unresolved_questions=("老王是否已经转账",),
        commitments=("用户答应晚点补银行流水",),
        key_turn_refs=("turn_12", "turn_18"),
        relevant_entity_refs=("ent_wang",),
        evidence_refs=("obs_loan",),
        updated_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
    )
    store.append(v1)

    v2 = ConversationWorkingState(
        session_id="ses_1",
        version=2,
        supersedes_version=1,
        current_topic="老王还款确认",
        topic_branches=("银行流水",),
        open_loops=(),
        unresolved_questions=(),
        commitments=("AI 后续继续关注退赔结果",),
        key_turn_refs=("turn_12", "turn_18", "turn_27"),
        relevant_entity_refs=("ent_wang",),
        evidence_refs=("obs_loan", "obs_bank_receipt"),
        updated_at=datetime(2026, 9, 18, 9, 0, tzinfo=UTC),
    )
    store.append(v2)

    assert store.latest("ses_1") == v2
    assert store.get("ses_1", 1) == v1
    assert store.history("ses_1") == [v1, v2]


def test_conversation_state_rejects_version_gap_or_overwrite(tmp_path):
    store = ConversationStateStore(tmp_path / "world.db")
    store.append(ConversationWorkingState(session_id="ses_1", version=1))

    with pytest.raises(ConversationStateConflict):
        store.append(
            ConversationWorkingState(
                session_id="ses_1",
                version=3,
                supersedes_version=2,
            )
        )

    with pytest.raises(ConversationStateConflict):
        store.append(ConversationWorkingState(session_id="ses_1", version=1))


def test_state_contract_rejects_broken_supersedes_chain():
    with pytest.raises(ValueError):
        ConversationWorkingState(
            session_id="ses_1",
            version=2,
            supersedes_version=None,
        )

    with pytest.raises(ValueError):
        ConversationWorkingState(
            session_id="ses_1",
            version=1,
            supersedes_version=1,
        )
