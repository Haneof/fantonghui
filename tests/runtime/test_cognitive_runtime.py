"""R5/R6 AI Cognitive Runtime regression tests."""

from __future__ import annotations

from aios_core.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySpec,
)
from aios_core.runtime.cognitive_runtime import CognitiveRuntime, ModelDirective


def test_direct_response_needs_no_capability_call():
    registry = CapabilityRegistry()
    seen = []

    def model(snapshot):
        seen.append(snapshot)
        return ModelDirective(response="这是当前信息就能回答的问题。")

    result = CognitiveRuntime(registry=registry, model_handler=model).run_turn("现在几点？")
    assert result.response == "这是当前信息就能回答的问题。"
    assert result.capability_history == ()
    assert result.model_rounds == 1
    assert result.termination_reason == "responded"
    assert len(seen) == 1


def test_model_can_search_then_answer_from_tool_result():
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            name="search_world",
            description="return candidate memories",
            kind=CapabilityKind.READ,
        ),
        lambda query: [{"object_id": "obs_1", "excerpt": f"关于 {query} 的旧事"}],
    )

    def model(snapshot):
        if not snapshot.capability_history:
            return ModelDirective(
                capability_calls=(CapabilityCall(name="search_world", arguments={"query": "老王"}),)
            )
        tool = snapshot.capability_history[-1]
        assert tool.ok is True
        assert tool.data[0]["object_id"] == "obs_1"
        return ModelDirective(response="我查到之前关于老王的记录了。")

    result = CognitiveRuntime(registry=registry, model_handler=model).run_turn("老王那事后来怎么样？")
    assert result.response == "我查到之前关于老王的记录了。"
    assert len(result.capability_history) == 1
    assert result.capability_history[0].name == "search_world"
    assert result.model_rounds == 2


def test_unknown_capability_is_structured_evidence_and_model_can_recover():
    registry = CapabilityRegistry()

    def model(snapshot):
        if not snapshot.capability_history:
            return ModelDirective(
                capability_calls=(CapabilityCall(name="invented_tool", arguments={}),)
            )
        error = snapshot.capability_history[-1]
        assert error.ok is False
        assert error.error_code == "CAPABILITY_NOT_FOUND"
        return ModelDirective(response="这个能力不可用，我不会假装已经查到了。")

    result = CognitiveRuntime(registry=registry, model_handler=model).run_turn("帮我查一下")
    assert result.response == "这个能力不可用，我不会假装已经查到了。"
    assert result.capability_history[-1].error_code == "CAPABILITY_NOT_FOUND"


def test_repeated_identical_call_is_bounded_by_loop_guard():
    registry = CapabilityRegistry()
    calls = []
    registry.register(
        CapabilitySpec(name="search_world", description="search", kind=CapabilityKind.READ),
        lambda query: calls.append(query) or [],
    )

    def model(snapshot):
        # Deliberately pathological model: repeats the exact same call forever.
        return ModelDirective(
            capability_calls=(CapabilityCall(name="search_world", arguments={"query": "同一个查询"}),)
        )

    result = CognitiveRuntime(
        registry=registry,
        model_handler=model,
        max_tool_rounds=3,
        repeated_call_limit=1,
    ).run_turn("测试循环保护")

    assert calls == ["同一个查询"]
    assert any(
        item.error_code == "REPEATED_CAPABILITY_CALL_BLOCKED"
        for item in result.capability_history
    )
    assert result.termination_reason == "tool_round_budget_exhausted"


def test_side_effecting_capability_is_denied_by_default():
    registry = CapabilityRegistry()
    executed = []
    registry.register(
        CapabilitySpec(
            name="commit_claim",
            description="commit a derived claim",
            kind=CapabilityKind.WRITE,
            side_effecting=True,
        ),
        lambda content: executed.append(content) or {"committed": True},
    )

    def model(snapshot):
        if not snapshot.capability_history:
            return ModelDirective(
                capability_calls=(CapabilityCall(name="commit_claim", arguments={"content": "猜测"}),)
            )
        assert snapshot.capability_history[-1].error_code == "CAPABILITY_NOT_AUTHORIZED"
        return ModelDirective(response="写入没有获得授权，因此没有落库。")

    result = CognitiveRuntime(registry=registry, model_handler=model).run_turn("记住这个")
    assert executed == []
    assert result.response == "写入没有获得授权，因此没有落库。"


def test_side_effecting_capability_runs_only_when_authorized():
    registry = CapabilityRegistry()
    executed = []
    registry.register(
        CapabilitySpec(
            name="commit_claim",
            description="commit a derived claim",
            kind=CapabilityKind.WRITE,
            side_effecting=True,
        ),
        lambda content: executed.append(content) or {"committed": True},
    )

    def model(snapshot):
        if not snapshot.capability_history:
            return ModelDirective(
                capability_calls=(CapabilityCall(name="commit_claim", arguments={"content": "有证据的结论"}),)
            )
        return ModelDirective(response="已通过受控写入路径提交。")

    runtime = CognitiveRuntime(
        registry=registry,
        model_handler=model,
        side_effect_authorizer=lambda spec, call, snapshot: spec.name == "commit_claim",
    )
    result = runtime.run_turn("记住这个")
    assert executed == ["有证据的结论"]
    assert result.capability_history[0].ok is True
    assert result.response == "已通过受控写入路径提交。"
