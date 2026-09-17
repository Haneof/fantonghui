"""Tests for long-conversation streaming support and legacy Cockpit execution."""

from __future__ import annotations

import hashlib

from ai_worker.brevity_guard import enforce_dialogue_brevity_guard
from ai_worker.cockpit_executor import CockpitExecutor
from ai_worker.context_pipeline import ContextAssemblyPipeline
from ai_worker.manifest_optimizer import CockpitManifestOptimizer
from ai_worker.stream_pipeline import (
    ActiveRollingWindow,
    ExtractedClaimCandidate,
    ProactiveAssociativeRecall,
    StreamingExtractWorker,
    ThreeStageStreamPipeline,
)


def _test_cognitive_extractor(batch, turn_offset):
    """Deterministic test double for an external/model cognitive extractor.

    Production has no regex fallback. Tests inject cognition explicitly so transport,
    watermark and recall behavior can be checked without pretending rules are AI.
    """

    results = []
    for idx, (user_msg, _ai_msg) in enumerate(batch):
        turn_no = turn_offset + idx + 1
        subject = "用户"
        for known in ("老张", "妈妈", "母亲", "老李"):
            if known in user_msg:
                subject = known
                break
        digest = hashlib.sha256(f"{turn_no}:{user_msg}".encode("utf-8")).hexdigest()[:12]
        results.append(
            ExtractedClaimCandidate(
                claim_id=f"clm_test_{digest}",
                subject=subject,
                predicate="模型提取候选",
                object_val=subject if subject != "用户" else user_msg[:12],
                context_topic="test_extractor",
                sentiment="未知",
                raw_quote=user_msg,
                turn_index=turn_no,
                idempotency_key=f"idem_test_{digest}",
            )
        )
    return results


# ============================================================================
# 1. Active window is a bounded cache, not durable memory
# ============================================================================
def test_active_rolling_window_v25_compatibility():
    window = ActiveRollingWindow(max_turns=6, max_tokens=1500)
    evicted_archive = []

    for turn_idx in range(1, 51):
        user_msg = f"第 {turn_idx} 轮日常闲聊：今天天气如何？"
        ai_msg = f"挺清爽的，适合散步。第 {turn_idx} 轮。"
        evicted = window.push_turn(user_msg, ai_msg)
        evicted_archive.extend(evicted)
        assert len(window.get_prompt_messages()) <= 12

    assert len(evicted_archive) == 44
    assert window.estimate_tokens() < 500


# ============================================================================
# 2. Extraction transport never fabricates cognition when no model is configured
# ============================================================================
def test_streaming_extract_worker_requires_explicit_cognitive_extractor():
    turns_batch = [
        ("今天老张答应了要还我五万块钱", "好。"),
        ("下午给妈妈买了支降压药", "记下了。"),
        ("晚上身体难受，好像发烧了", "先看实际体征。"),
    ]

    raw_only = StreamingExtractWorker()
    assert raw_only.extract_sync(turns_batch, turn_offset=10) == []
    assert raw_only.watermark == 13
    assert raw_only.get_all_extracted() == []

    worker = StreamingExtractWorker(custom_extractor=_test_cognitive_extractor)
    claims = worker.extract_sync(turns_batch, turn_offset=10)
    assert len(claims) == 3
    assert any(c.subject == "老张" for c in claims)
    assert any(c.subject == "妈妈" for c in claims)
    assert worker.watermark == 13

    # Same model result replay is deduplicated by candidate idempotency key.
    assert worker.extract_sync(turns_batch, turn_offset=10) == []
    assert len(worker.get_all_extracted()) == 3


def test_enqueued_batch_without_background_thread_drain_does_not_deadlock():
    worker = StreamingExtractWorker(custom_extractor=_test_cognitive_extractor)
    worker.enqueue_evicted_turns([("老李打电话了", "知道了")], turn_offset=4)
    drained = worker.drain()
    assert len(drained) == 1
    assert drained[0].subject == "老李"


# ============================================================================
# 3. Prefetch signal is a candidate hint, not an authoritative relevance score
# ============================================================================
def test_proactive_associative_recall_emits_signal_not_cognitive_score():
    worker = StreamingExtractWorker(custom_extractor=_test_cognitive_extractor)
    recall = ProactiveAssociativeRecall(worker)

    past_turns = [
        ("今天老张借走了我的相机，答应下周还", "行。"),
        ("给母亲买了羊毛围巾做生日礼物", "记下了。"),
    ]
    worker.extract_sync(past_turns, turn_offset=5)

    cues = recall.recall_for_turn("老张今天好像又找我借车了", top_k=2)
    assert len(cues) >= 1
    matched = cues[0]
    assert matched["subject"] == "老张"
    assert matched["retrieval_signal"] in {"exact_subject", "exact_subject_and_object"}
    assert "relevance_score" not in matched
    assert "AI must decide actual relevance" in matched["why_recalled"]


# ============================================================================
# 4. Pipeline lifecycle with an explicit cognitive extractor
# ============================================================================
def test_three_stage_stream_pipeline_lifecycle():
    pipeline = ThreeStageStreamPipeline(
        max_active_turns=4,
        custom_extractor=_test_cognitive_extractor,
    )

    for turn in range(1, 11):
        user_text = (
            f"这是第 {turn} 句话，我和老李商量了合伙做项目的事。"
            if turn == 2
            else f"日常闲聊第 {turn} 句。"
        )

        def mock_reply_gen(active_msgs, recalled):
            if recalled:
                return f"想起老李之前的候选记录了。第 {turn} 轮。"
            return f"收到第 {turn} 轮。"

        res = pipeline.process_turn(user_text, mock_reply_gen)
        assert res["turn_index"] == turn
        assert res["active_turns"] <= 4
        assert res["extraction_mode"] == "cognitive_extractor"

    recall_res = pipeline.process_turn(
        "老李刚才又给我打电话了",
        lambda msgs, recalled: "我先基于候选记录继续看。" if recalled else "我需要查历史。",
    )
    assert len(recall_res["recalled_cues"]) >= 1
    assert any(c["subject"] == "老李" for c in recall_res["recalled_cues"])
    assert "候选记录" in recall_res["reply"]


# ============================================================================
# 5. Context assembly: stable layout is not a forced thought sequence
# ============================================================================
def test_context_assembly_pipeline_budgets():
    manifest = CockpitManifestOptimizer.assemble_cockpit(
        wake_reason="用户主动发问",
        user_name="老大",
    )
    recalled = [
        {
            "turn_index": 3,
            "subject": "老王",
            "predicate": "欠款",
            "object_val": "20万",
            "raw_quote": "老王欠了20万",
        }
    ]
    dialogue = [
        {"role": "user", "content": "老王最近有信儿吗？"},
        {"role": "assistant", "content": "暂时没动静，要不要追问一下？"},
    ]

    ctx = ContextAssemblyPipeline.assemble(
        manifest=manifest,
        recalled_cues=recalled,
        rolling_messages=dialogue,
        budget_tier="ROUTINE",
    )

    assert "[布局段1·AI自身世界]" in ctx.system_prompt
    assert "[布局段2·关系模型]" in ctx.system_prompt
    assert "[布局段3·沟通策略提示]" in ctx.system_prompt
    assert "[布局段4·当前世界与就绪任务]" in ctx.system_prompt
    assert "不规定 AI 的思考顺序" in ctx.system_prompt
    assert "[L1 联想回捞历史证据]" in ctx.system_prompt
    assert "老王欠了20万" in ctx.system_prompt
    assert ctx.is_within_budget is True
    assert ctx.total_tokens < 3400


# ============================================================================
# 6. Reply verbosity belongs to AI/policy, not a destructive post-processor
# ============================================================================
def test_cockpit_executor_preserves_ai_semantics_without_length_cap():
    executor = CockpitExecutor()

    routine_reply = (
        "我非常理解您的心情！第一，要调整作息；第二，要注意饮食；第三，要坚持运动。"
        "除此之外，最近连续几天的工作密度也值得一起看，因为疲劳不一定只是单一原因。"
    )

    executor.model_handler = lambda ctx: routine_reply
    res_routine = executor.execute_turn("我最近有点累")

    assert len(routine_reply) > 60
    assert res_routine.reply == routine_reply
    assert res_routine.raw_reply == routine_reply
    assert res_routine.was_brevity_truncated is False

    preserved, changed = enforce_dialogue_brevity_guard(routine_reply)
    assert preserved == routine_reply
    assert changed is False

    detailed_reply = (
        "既然你想展开听，我给你盘盘这三个维度的具体因果：首先是体征连续3天心率偏高，"
        "其次是睡眠深睡不足1小时，最后是白天工作日程密度过载。建议今晚先降低负荷，"
        "但是否需要进一步处理仍应结合你接下来的实际状态。"
    )
    executor.model_handler = lambda ctx: detailed_reply
    res_expansion = executor.execute_turn("这事你怎么看的？给我详细说说")

    assert res_expansion.reply == detailed_reply
    assert res_expansion.was_brevity_truncated is False
    assert len(res_expansion.reply) > 60
