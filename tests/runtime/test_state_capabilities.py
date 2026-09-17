"""Model-facing state writes must remain evidence/version/governance controlled."""

from aios_core.runtime.ai_self_world import AISelfMemoryKind, AISelfWorldStoreV2
from aios_core.runtime.capabilities import CapabilityCall, CapabilityRegistry
from aios_core.runtime.conversation_state import ConversationStateStore
from aios_core.runtime.policy_registry import (
    CognitivePolicyRegistry,
    CognitivePolicyVersion,
    PolicyClass,
)
from aios_core.runtime.state_capabilities import RuntimeStateCapabilityBus


def _bus(tmp_path):
    db = tmp_path / "world.db"
    states = ConversationStateStore(db)
    self_world = AISelfWorldStoreV2(db)
    policies = CognitivePolicyRegistry(db)
    policies.append(
        CognitivePolicyVersion(
            policy_id="recall.expand_threshold",
            scope="global_default",
            policy_class=PolicyClass.COGNITIVE_POLICY,
            default_value=0.5,
            current_value=0.5,
            allowed_range_or_choices={"min": 0.1, "max": 0.9},
            mutable_by_ai=True,
            reason="initial default",
            evidence_refs=("review:baseline",),
            changed_by="governance",
            version=1,
            evaluation_window="30d",
        )
    )
    return RuntimeStateCapabilityBus(
        conversation_states=states,
        ai_self_world=self_world,
        policies=policies,
    )


def test_conversation_state_write_uses_optimistic_version(tmp_path):
    bus = _bus(tmp_path)
    created = bus.update_conversation_state(
        "ses_1",
        expected_version=0,
        current_topic="老王借款",
        open_loops=["等银行流水"],
        key_turn_refs=["turn_01"],
        evidence_refs=["turn_01"],
    )
    assert created["version"] == 1

    try:
        bus.update_conversation_state("ses_1", expected_version=0, current_topic="脏并发写")
    except ValueError as exc:
        assert "stale conversation state" in str(exc)
    else:
        raise AssertionError("stale conversation state write must fail")


def test_ai_self_write_requires_evidence_for_relationship_understanding(tmp_path):
    bus = _bus(tmp_path)
    try:
        bus.record_ai_self_memory(
            "relationship:user_1",
            AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING.value,
            "直接把用户定义成死党。",
            expected_version=0,
            evidence_refs=[],
        )
    except ValueError as exc:
        assert "requires evidence_refs" in str(exc)
    else:
        raise AssertionError("relationship understanding without evidence must fail")

    record = bus.record_ai_self_memory(
        "relationship:user_1",
        AISelfMemoryKind.RELATIONSHIP_UNDERSTANDING.value,
        "用户在架构讨论中偏好直接的证据化沟通。",
        expected_version=0,
        evidence_refs=["turn_27", "commexp_2"],
    )
    assert record["version"] == 1
    assert record["kind"] == "relationship_understanding"


def test_policy_write_stays_inside_registered_range_and_requires_evidence(tmp_path):
    bus = _bus(tmp_path)
    updated = bus.update_cognitive_policy(
        "recall.expand_threshold",
        expected_version=1,
        current_value=0.42,
        reason="evaluation showed missed old-topic recall",
        evidence_refs=["outcome:miss-1", "outcome:miss-2"],
    )
    assert updated["version"] == 2
    assert updated["current_value"] == 0.42

    try:
        bus.update_cognitive_policy(
            "recall.expand_threshold",
            expected_version=2,
            current_value=0.99,
            reason="try to exceed registered range",
            evidence_refs=["outcome:one-off"],
        )
    except ValueError as exc:
        assert "above allowed policy range" in str(exc)
    else:
        raise AssertionError("out-of-range cognitive policy update must fail")


def test_registry_marks_state_writes_as_side_effecting(tmp_path):
    bus = _bus(tmp_path)
    registry = CapabilityRegistry()
    bus.register_capabilities(registry)
    catalog = {item["name"]: item for item in registry.catalog()}
    assert catalog["update_conversation_state"]["side_effecting"] is True
    assert catalog["record_ai_self_memory"]["side_effecting"] is True
    assert catalog["update_cognitive_policy"]["side_effecting"] is True

    # Registry alone cannot bypass CognitiveRuntime's side-effect authorizer, but the
    # handler itself still enforces durable version/evidence rules if invoked directly.
    result = registry.invoke(
        CapabilityCall(
            name="update_conversation_state",
            arguments={
                "session_id": "ses_2",
                "expected_version": 0,
                "current_topic": "测试",
                "evidence_refs": ["turn_1"],
            },
        )
    )
    assert result.ok is True
