"""Tests for Three-Stage Streaming Mind Pipeline & Cockpit Execution (C10 / M2-016 / V25 / ADJ-001 / R6)."""

from __future__ import annotations

from ai_worker.brevity_guard import enforce_dialogue_brevity_guard
from ai_worker.cockpit_executor import CockpitExecutor
from ai_worker.context_pipeline import ContextAssemblyPipeline
from ai_worker.manifest_optimizer import CockpitManifestOptimizer
from ai_worker.stream_pipeline import (
    ActiveRollingWindow,
    ProactiveAssociativeRecall,
    StreamingExtractWorker,
    ThreeStageStreamPipeline,
)


# ============================================================================
# 1. 前台活跃滑窗向后兼容性与 50 轮防爆测试 (V25)
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
# 2. 第二级：后台异步增量事实萃取测试
# ============================================================================
def test_streaming_extract_worker_extraction():
    worker = StreamingExtractWorker()

    turns_batch = [
        ("今天老张答应了要还我五万块钱", "好啊，那心里石头总算落下了。"),
        ("下午给妈妈买了支降压药", "记得提醒阿姨按时吃。"),
        ("晚上身体难受，好像发烧了", "先测个体温，多喝温水别硬撑。"),
    ]

    claims = worker.extract_sync(turns_batch, turn_offset=10)

    assert len(claims) >= 3
    subjects = [c.subject for c in claims]
    assert "老张" in subjects or "用户" in subjects
    assert any("妈妈" in c.subject or "买" in c.raw_quote for c in claims)
    assert any("发烧" in c.raw_quote or "难受" in c.raw_quote for c in claims)

    assert worker.watermark == 13
    all_extracted = worker.get_all_extracted()
    assert len(all_extracted) >= 3


# ============================================================================
# 3. 第三级：跨周期超链接主动联想回捞测试
# ============================================================================
def test_proactive_associative_recall():
    worker = StreamingExtractWorker()
    recall = ProactiveAssociativeRecall(worker)

    past_turns = [
        ("今天老张借走了我的相机，答应下周还", "行，那下周提醒他。"),
        ("给母亲买了羊毛围巾做生日礼物", "挺用心的，阿姨肯定喜欢。"),
    ]
    worker.extract_sync(past_turns, turn_offset=5)

    current_user_msg = "老张今天好像又找我借车了"
    cues = recall.recall_for_turn(current_user_msg, top_k=2)

    assert len(cues) >= 1
    matched = cues[0]
    assert matched["subject"] == "老张"
    assert "相机" in matched["raw_quote"] or "借" in matched["predicate"]
    assert matched["relevance_score"] >= 0.90


# ============================================================================
# 4. 三级流式流水线端到端闭环测试 (ThreeStageStreamPipeline)
# ============================================================================
def test_three_stage_stream_pipeline_lifecycle():
    pipeline = ThreeStageStreamPipeline(max_active_turns=4)

    for turn in range(1, 11):
        user_text = (
            f"这是第 {turn} 句话，我和老李商量了合伙做项目的事。"
            if turn == 2
            else f"日常闲聊第 {turn} 句。"
        )

        def mock_reply_gen(active_msgs, recalled):
            if recalled:
                return f"想起老李之前的事了。第 {turn} 轮。"
            return f"收到第 {turn} 轮。"

        res = pipeline.process_turn(user_text, mock_reply_gen)
        assert res["turn_index"] == turn
        assert res["active_turns"] <= 4

    recall_res = pipeline.process_turn(
        "老李刚才又给我打电话了",
        lambda msgs, recalled: "老李怎么说了？" if recalled else "谁是老李？",
    )
    assert len(recall_res["recalled_cues"]) >= 1
    assert any(c["subject"] == "老李" for c in recall_res["recalled_cues"])
    assert "老李怎么说了？" in recall_res["reply"]


# ============================================================================
# 5. 上下文装配器：稳定布局不等于固定思维顺序
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

    # 保留四段稳定布局，但明确不得把布局误读成 AI 的固定思考顺序。
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
# 6. 回复详略是 AI 的认知/表达策略，不是 3 句或 60 字硬闸
# ============================================================================
def test_cockpit_executor_preserves_ai_semantics_without_length_cap():
    executor = CockpitExecutor()

    routine_reply = (
        "我非常理解您的心情！第一，要调整作息；第二，要注意饮食；第三，要坚持运动。"
        "除此之外，最近连续几天的工作密度也值得一起看，因为疲劳不一定只是单一原因。"
    )

    def routine_model_handler(ctx):
        return routine_reply

    executor.model_handler = routine_model_handler
    res_routine = executor.execute_turn("我最近有点累")

    assert len(routine_reply) > 60
    assert res_routine.reply == routine_reply
    assert res_routine.raw_reply == routine_reply
    assert res_routine.was_brevity_truncated is False

    # Legacy guard API itself must also be semantically non-destructive.
    preserved, changed = enforce_dialogue_brevity_guard(routine_reply)
    assert preserved == routine_reply
    assert changed is False

    detailed_reply = (
        "既然你想展开听，我给你盘盘这三个维度的具体因果：首先是体征连续3天心率偏高，"
        "其次是睡眠深睡不足1小时，最后是白天工作日程密度过载。建议今晚先降低负荷，"
        "但是否需要进一步处理仍应结合你接下来的实际状态。"
    )

    def long_detailed_handler(ctx):
        return detailed_reply

    executor.model_handler = long_detailed_handler
    res_expansion = executor.execute_turn("这事你怎么看的？给我详细说说")

    assert res_expansion.reply == detailed_reply
    assert res_expansion.was_brevity_truncated is False
    assert len(res_expansion.reply) > 60
