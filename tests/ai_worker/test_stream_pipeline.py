"""Tests for Three-Stage Streaming Mind Pipeline & Cockpit Execution (C10 / M2-016 / V25 / ADJ-001 / ADJ-007)."""

from __future__ import annotations

import time
import pytest

from ai_worker.brevity_guard import enforce_dialogue_brevity_guard
from ai_worker.cockpit_executor import CockpitExecutor, TurnExecutionResult
from ai_worker.context_pipeline import AssembledContext, ContextAssemblyPipeline
from ai_worker.manifest_optimizer import CockpitManifest, CockpitManifestOptimizer
from ai_worker.stream_pipeline import (
    ActiveRollingWindow,
    ExtractedClaimCandidate,
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

        # 断言 1：前台滑动窗口轮数严格锁定在 <= 6 轮 (12 条消息)
        assert len(window.get_prompt_messages()) <= 12

    # 断言 2：50 轮中前 44 轮对话平滑滑出，无内存堆积
    assert len(evicted_archive) == 44
    # 断言 3：前台 Token 估算处于健康低位
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

    # 验证提取到的结构化事实
    assert len(claims) >= 3
    subjects = [c.subject for c in claims]
    assert "老张" in subjects or "用户" in subjects
    assert any("妈妈" in c.subject or "买" in c.raw_quote for c in claims)
    assert any("发烧" in c.raw_quote or "难受" in c.raw_quote for c in claims)

    # 验证水印与幂等性
    assert worker.watermark == 13
    all_extracted = worker.get_all_extracted()
    assert len(all_extracted) >= 3


# ============================================================================
# 3. 第三级：跨周期超链接主动联想回捞测试
# ============================================================================
def test_proactive_associative_recall():
    worker = StreamingExtractWorker()
    recall = ProactiveAssociativeRecall(worker)

    # 模拟前期对话迁出并沉淀为事实
    past_turns = [
        ("今天老张借走了我的相机，答应下周还", "行，那下周提醒他。"),
        ("给母亲买了羊毛围巾做生日礼物", "挺用心的，阿姨肯定喜欢。"),
    ]
    worker.extract_sync(past_turns, turn_offset=5)

    # 在第 30 轮，用户再次提及“老张”
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

    # 模拟 10 轮对话
    for turn in range(1, 11):
        user_text = f"这是第 {turn} 句话，我和老李商量了合伙做项目的事。" if turn == 2 else f"日常闲聊第 {turn} 句。"
        
        def mock_reply_gen(active_msgs, recalled):
            if recalled:
                return f"想起老李之前的事了。第 {turn} 轮。"
            return f"收到第 {turn} 轮。"

        res = pipeline.process_turn(user_text, mock_reply_gen)
        assert res["turn_index"] == turn
        assert res["active_turns"] <= 4

    # 在后续轮次中提到老李，应该能触发联想回捞
    recall_res = pipeline.process_turn(
        "老李刚才又给我打电话了",
        lambda msgs, recalled: "老李怎么说了？" if recalled else "谁是老李？"
    )
    assert len(recall_res["recalled_cues"]) >= 1
    assert any(c["subject"] == "老李" for c in recall_res["recalled_cues"])
    assert "老李怎么说了？" in recall_res["reply"]


# ============================================================================
# 5. 上下文装配器与预算校验 (ContextAssemblyPipeline)
# ============================================================================
def test_context_assembly_pipeline_budgets():
    manifest = CockpitManifestOptimizer.assemble_cockpit(
        wake_reason="用户主动发问",
        user_name="老大",
    )
    recalled = [
        {"turn_index": 3, "subject": "老王", "predicate": "欠款", "object_val": "20万", "raw_quote": "老王欠了20万"}
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

    # 验证四步序与联想切片均被正确注入
    assert "[第一步·照镜子 (原则底线)]" in ctx.system_prompt
    assert "[第二步·校准羁绊 (动态关系)]" in ctx.system_prompt
    assert "[第三步·确立姿态 (态度与语调)]" in ctx.system_prompt
    assert "[第四步·审视世界与就绪任务]" in ctx.system_prompt
    assert "[L1 联想回捞历史证据]" in ctx.system_prompt
    assert "老王欠了20万" in ctx.system_prompt
    assert ctx.is_within_budget is True
    assert ctx.total_tokens < 3400


# ============================================================================
# 6. CockpitExecutor 与 ADJ-007 展开豁免测试
# ============================================================================
def test_cockpit_executor_brevity_and_exceptions():
    executor = CockpitExecutor()

    # 测试常规输入：被 1~3 句反说教护栏严格截断
    def preachy_model_handler(ctx):
        return "我非常理解您的心情！第一，要调整作息；第二，要注意饮食；第三，要坚持运动。一定要坚持下去啊！"

    executor.model_handler = preachy_model_handler
    res_routine = executor.execute_turn("我最近有点累")
    assert res_routine.was_brevity_truncated is True
    assert "我非常理解您" not in res_routine.reply
    assert len(res_routine.reply) <= 60

    # 测试 ADJ-007 豁免输入：用户明确要求“详细说说”或“展开”
    def long_detailed_handler(ctx):
        return "既然你想展开听，我给你盘盘这三个维度的具体因果：首先是体征连续3天心率偏高，其次是睡眠深睡不足1小时，最后是白天工作日程密度过载。建议今晚直接断电休息。"

    executor.model_handler = long_detailed_handler
    res_expansion = executor.execute_turn("这事你怎么看的？给我详细说说")
    # 豁免生效，不被 60 字与 3 句硬截断
    assert res_expansion.was_brevity_truncated is False
    assert len(res_expansion.reply) > 60
    assert "既然你想展开听" in res_expansion.reply
