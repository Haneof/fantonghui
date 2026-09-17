"""End-to-end R5 session executor tests."""

from datetime import datetime, timezone

from ai_worker.cognitive_executor import CognitiveExecutor
from aios_core.contracts.enums import SourceClass
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.runtime import CapabilityCall, ModelDirective
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc


def _store(tmp_path):
    store = SQLiteWorldStore(tmp_path / "world.db")
    t = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    store.commit(
        [
            Observation(
                object_id="obs_wang",
                subject_id="user_1",
                revision=1,
                source_kind="user_chat",
                modality="text",
                value="老王去年借过五万元，说年底归还。",
                occurred=TemporalExtent.point(t),
                learned_at=t,
                recorded_at=t,
                created_by="test",
            )
        ],
        OperationRequest(
            operation_id="op_executor_fixture",
            operation_name="test.fixture",
            expected_world_revision=0,
            reason="executor fixture",
            idempotency_key="idem_executor_fixture",
            source_class=SourceClass.USER,
        ),
    )
    return store


def test_executor_model_can_recall_then_respond_and_raw_turn_is_sealed(tmp_path):
    store = _store(tmp_path)

    def model(snapshot):
        if not snapshot.capability_history:
            return ModelDirective(
                capability_calls=(
                    CapabilityCall(name="search_world", arguments={"query": "老王"}),
                )
            )
        assert snapshot.capability_history[-1].ok is True
        assert snapshot.capability_history[-1].data[0]["object_id"] == "obs_wang"
        return ModelDirective(response="查到了：去年有一条老王借款记录。")

    executor = CognitiveExecutor(
        world_store=store,
        model_handler=model,
        session_id="ses_runtime_1",
    )
    result = executor.execute_turn("老王那笔钱你还记得吗？")

    assert result.response == "查到了：去年有一条老王借款记录。"
    assert len(result.runtime.capability_history) == 1
    turns = executor.timeline.list_turns("ses_runtime_1")
    assert len(turns) == 1
    assert turns[0].turn_id == result.raw_turn_ref
    assert turns[0].user_text == "老王那笔钱你还记得吗？"
    assert turns[0].assistant_text == result.response


def test_executor_allows_controlled_working_state_write_then_response(tmp_path):
    store = _store(tmp_path)

    def model(snapshot):
        if not snapshot.capability_history:
            return ModelDirective(
                capability_calls=(
                    CapabilityCall(
                        name="update_conversation_state",
                        arguments={
                            "session_id": "ses_runtime_2",
                            "expected_version": 0,
                            "current_topic": "老王借款",
                            "open_loops": ["确认是否还款"],
                            "evidence_refs": ["obs_wang"],
                        },
                    ),
                )
            )
        assert snapshot.capability_history[-1].ok is True
        return ModelDirective(response="我把这件未完事项挂到当前会话状态里了。")

    executor = CognitiveExecutor(
        world_store=store,
        model_handler=model,
        session_id="ses_runtime_2",
    )
    result = executor.execute_turn("这件事先别忘。")

    assert result.conversation_state_version == 1
    state = executor.conversation_states.latest("ses_runtime_2")
    assert state is not None
    assert state.current_topic == "老王借款"
    assert state.open_loops == ("确认是否还款",)
    assert state.evidence_refs == ("obs_wang",)


def test_next_turn_receives_durable_conversation_state_in_cockpit(tmp_path):
    store = _store(tmp_path)
    seen_states = []

    def model(snapshot):
        seen_states.append(snapshot.cockpit["conversation_working_state"])
        if len(seen_states) == 1:
            return ModelDirective(
                capability_calls=(
                    CapabilityCall(
                        name="update_conversation_state",
                        arguments={
                            "session_id": "ses_runtime_3",
                            "expected_version": 0,
                            "current_topic": "合同复核",
                            "unresolved_questions": ["合同原件在哪"],
                            "evidence_refs": ["obs_wang"],
                        },
                    ),
                )
            )
        if snapshot.capability_history:
            return ModelDirective(response="先把合同原件位置确认下来。")
        return ModelDirective(response="上轮未完问题还在：合同原件在哪？")

    executor = CognitiveExecutor(
        world_store=store,
        model_handler=model,
        session_id="ses_runtime_3",
    )
    executor.execute_turn("先记一下这个问题")
    second = executor.execute_turn("接着说")

    assert second.response == "上轮未完问题还在：合同原件在哪？"
    assert seen_states[-1]["current_topic"] == "合同复核"
    assert seen_states[-1]["unresolved_questions"] == ["合同原件在哪"]
    assert len(executor.timeline.list_turns("ses_runtime_3")) == 2
