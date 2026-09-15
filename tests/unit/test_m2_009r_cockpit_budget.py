from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from aios_core.cockpit.pipeline import (
    ActiveRollingWindow,
    BrevityGuard,
    CockpitPipeline,
    ConversationObservationArchive,
    ConversationTurn,
    CrisisCockpitContext,
    SingleShotCockpitManifest,
    Utf8ByteTokenCounter,
    split_sentences,
)

START = datetime(2026, 9, 16, 21, 0, tzinfo=UTC)


def _crisis_context() -> CrisisCockpitContext:
    dense_evidence = "；".join(
        [
            f"证据链{i:03d}:薪酬变更通知、岗位权限回收日志、竞业协议版本差异、"
            "绩效校准会议纪要与仲裁时效风险必须保持来源边界"
            for i in range(240)
        ]
    )
    return CrisisCockpitContext(
        session_id="session_employment_crisis_50_turns",
        ai_self_summary=(
            "我是与用户共同承担长期后果的随身老友；不替公司合理化，不在高压状态催促签字，"
            "必须区分已核验劳动事实、法律不确定性和情绪支持。"
        )
        * 40,
        rapport_state=(
            "长期高度信任；用户当前因恶意降薪、强制调岗和竞业索赔威胁处于高压但仍保持专业判断。"
        )
        * 40,
        wake_reason_anchor=(
            "深夜两小时职业危机连续谈判；最新输入涉及公司要求次日上午签署降薪调岗确认书。"
        )
        * 40,
        local_world_facts=dense_evidence,
        ready_tasks=[
            {
                "task_id": "preserve-evidence",
                "state": "READY",
                "title": "固化薪酬、调岗与权限回收证据链",
            },
            {
                "task_id": "deadline-map",
                "state": "READY",
                "title": "核对竞业索赔与仲裁程序时限",
            },
            {
                "task_id": "avoid-coerced-signature",
                "state": "READY",
                "title": "高压状态下暂缓签署争议文件",
            },
        ],
    )


def _turn(index: int) -> ConversationTurn:
    legal_detail = (
        f"第{index:02d}轮：公司在未完成协商程序的情况下将固定薪酬下调，"
        "同时撤销生产系统审批权限并要求转入无实权岗位；HR又以竞业违约金和"
        "未披露商业秘密清单施压，现有邮件头、版本化附件、门禁日志与会议录音"
        "之间存在时间戳交叉矛盾。"
    )
    user_text = (
        legal_detail
        + (
            "我现在需要判断哪些陈述已经有原始证据，哪些只是对方口头威胁，"
            "以及明早之前最不能做错的动作。"
        )
        * 18
    )
    assistant_text = (
        "先别在高压下签争议确认书，原始通知和版本记录一份都别改。"
        "这一轮我只帮你钉住事实边界和明早前的关键时限。"
    )
    return ConversationTurn(
        turn_id=f"employment-crisis-turn-{index:02d}",
        sequence_no=index,
        occurred_at=START + timedelta(seconds=(index - 1) * 144),
        user_text=user_text,
        assistant_text=assistant_text,
    )


def _archive_digest(turn: ConversationTurn) -> str:
    payload = json.dumps(
        {
            "assistant_text": turn.assistant_text,
            "occurred_at": turn.occurred_at.isoformat(),
            "sequence_no": turn.sequence_no,
            "turn_id": turn.turn_id,
            "user_text": turn.user_text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_50_turn_crisis_pipeline_is_bounded_lossless_and_under_15ms_p95() -> None:
    context = _crisis_context()
    archive = ConversationObservationArchive(clock=lambda: START + timedelta(hours=2))
    pipeline = CockpitPipeline(
        archive=archive, clock=lambda: START + timedelta(hours=2)
    )
    source_turns = [_turn(index) for index in range(1, 51)]
    latencies_ms: list[float] = []
    manifests: list[SingleShotCockpitManifest] = []

    for turn in source_turns:
        started = time.perf_counter_ns()
        manifest = pipeline.process_turn(turn, context)
        latencies_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        manifests.append(manifest)

        assert manifest.prompt_token_count <= 1_500
        assert manifest.prompt_token_count == len(manifest.prompt.encode("utf-8"))
        assert len(manifest.active_turn_ids) <= 6

    assert CockpitPipeline.p95_ms(latencies_ms) <= 15.0
    assert len(pipeline.window) == 6
    assert manifests[-1].active_turn_ids == [turn.turn_id for turn in source_turns[-6:]]
    assert manifests[-1].archived_observation_count == 44
    assert manifests[-1].omitted_utf8_bytes > 50_000
    assert all(turn.turn_id in manifests[-1].prompt for turn in source_turns[-6:])

    archived = archive.snapshot()
    assert len(archived) == 44
    assert [item.source_turn_id for item in archived] == [
        turn.turn_id for turn in source_turns[:-6]
    ]
    by_id = {turn.turn_id: turn for turn in source_turns}
    for observation in archived:
        original = by_id[observation.source_turn_id]
        assert observation.user_text == original.user_text
        assert observation.assistant_text == original.assistant_text
        assert observation.content_sha256 == _archive_digest(original)

    represented_ids = {item.source_turn_id for item in archived} | {
        item.turn_id for item in pipeline.window.snapshot()
    }
    assert represented_ids == {turn.turn_id for turn in source_turns}


def test_manifest_rejects_forged_token_receipt_and_over_budget_prompt() -> None:
    with pytest.raises(ValueError, match="does not match physical"):
        SingleShotCockpitManifest(
            session_id="forged-token-receipt",
            generated_at=START,
            prompt="证据" * 20,
            prompt_token_count=1,
            active_turn_ids=[],
            archived_observation_count=0,
            omitted_utf8_bytes=0,
        )

    with pytest.raises(ValueError):
        SingleShotCockpitManifest(
            session_id="physical-overflow",
            generated_at=START,
            prompt="x" * 1_501,
            prompt_token_count=1_501,
            active_turn_ids=[],
            archived_observation_count=0,
            omitted_utf8_bytes=0,
        )

    with pytest.raises(ValueError, match="between 1 and 1500"):
        CockpitPipeline(prompt_token_limit=1_501)


def test_utf8_counter_never_cuts_a_multibyte_character() -> None:
    counter = Utf8ByteTokenCounter()
    source = "司法证据ABC"

    for budget in range(1, counter.count(source) + 1):
        truncated = counter.truncate(source, budget)
        assert counter.count(truncated) <= budget
        truncated.encode("utf-8").decode("utf-8")


def test_brevity_guard_rewrites_paternalistic_five_point_injection() -> None:
    injected_lecture = (
        "您要保持积极心态。为您推荐以下五点心理疏导方案。"
        "第一点，接受公司的安排。第二点，学会感恩平台。第三点，避免过度维权。"
        "综上所述，我建议您采取积极沟通的方式，很高兴为您服务。"
    )

    result = BrevityGuard().enforce(injected_lecture)

    assert result.was_rewritten is True
    assert result.was_truncated is True
    assert 1 <= len(result.sentences) <= 3
    assert len(split_sentences(result.text)) == 2
    assert "positive-mindset" in result.blocked_patterns
    assert "five-point-counselling" in result.blocked_patterns
    for forbidden in [
        "您要保持积极心态",
        "为您推荐以下五点",
        "第一点",
        "综上所述",
        "很高兴为您服务",
    ]:
        assert forbidden not in result.text
    assert "降薪、调岗和竞业索赔材料原样留住" in result.text


def test_brevity_guard_hard_truncates_non_paternal_reply_to_three_sentences() -> None:
    raw_reply = (
        "这次降薪通知的程序确实不对。"
        "先保留原始邮件头和附件版本。"
        "今晚不要签新的调岗确认。"
        "明早再核对仲裁时限。"
        "竞业范围也要单独拆开看。"
    )

    result = BrevityGuard().enforce(raw_reply)

    assert result.was_rewritten is False
    assert result.was_truncated is True
    assert len(result.sentences) == 3
    assert result.text == "".join(split_sentences(raw_reply)[:3])


def test_window_rejects_out_of_order_turn_without_evicting_history() -> None:
    window = ActiveRollingWindow()
    first = _turn(1)
    window.push(first)

    with pytest.raises(ValueError, match="increase monotonically"):
        window.push(first.model_copy(update={"turn_id": "replayed-turn"}))

    assert window.snapshot() == (first,)
