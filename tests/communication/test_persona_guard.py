from aios_core.communication.persona_guard import PersonaGuard


def test_semantic_content_is_preserved_exactly() -> None:
    guard = PersonaGuard()
    candidates = (
        "你说得全对，我也吃过这亏。",
        "根据《民法典》第六百六十七条，我先把法条原文列出来。",
        "请选择：A. 继续 B. 暂停。这里提到了知识图谱和置信度。",
        "第一句。第二句。第三句。第四句。第五句。",
    )
    for candidate in candidates:
        verdict = guard.review(candidate, user_utterance="任意用户输入")
        assert verdict.allowed is True
        assert verdict.text == candidate
        assert verdict.violations == ()
        assert verdict.rewritten is False
        assert verdict.sentences_dropped == 0
        assert verdict.brevity_intercepted is False


def test_protocol_violation_rejects_without_rewriting() -> None:
    guard = PersonaGuard()
    candidate = "header\x00payload"
    verdict = guard.review(candidate)
    assert verdict.allowed is False
    assert "PROTOCOL_NUL" in verdict.violations
    assert verdict.text == candidate
    assert verdict.rewritten is False


def test_transport_budget_is_structural_only() -> None:
    guard = PersonaGuard(max_transport_bytes=4)
    candidate = "你好"
    verdict = guard.review(candidate)
    assert verdict.allowed is False
    assert any(item.startswith("PROTOCOL_TRANSPORT_BYTES_EXCEEDED") for item in verdict.violations)
    assert verdict.text == candidate
