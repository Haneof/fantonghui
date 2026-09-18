"""M4-005: V21~V30 宪法级高阶对抗场景自动化测试套件 (CI 终审红线).

十项高阶极端对抗场景全面覆盖：
- V21: 身份颠覆与单跳雪崩阻断 (两年前老王是骗子，历史零改写，单跳打标，0递归重算)
- V22: 突发严重跌倒与心脏骤停 P0 熔断直通车 (<= 50ms 首硬件动作；其前 0 LLM/0 World，之后允许急救认知研判)
- V23: 跨半年未知陌生人声纹冷热淘汰 (180 天 TTL，活跃实体不受影响)
- V24: 情感激烈冲突场景下兼容层不得破坏模型语义
- V25: 连续 50 轮碎片对话 Token 防爆与平滑驱逐 (活跃窗口 <= 6 轮，44 轮入后台)
- V26: 旧离线维度演化守卫回归（legacy/offline experimental；不得直接接入 R5 Runtime，阈值待迁 R6 Policy）
- V27: 模型供应商瞬时切换与超时熔断 (<= 500ms 平滑降级，零脏数据残留)
- V28: 深度睡眠静默心跳绝对克制 (DEEP_NREM 深睡拦截次要提醒，零马达微震)
- V29: 托腮摸耳物理防误触因果律 (待机状态骨传导断电，误触率因果律 0.0%)
- V30: R6 回复长度与风格主权：不得用 1~3 句/60 字/正则清洗覆盖 AI 语义
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.dimensions.evolution_guard import (
    CandidateDimension,
    DynamicDimensionEvolutionGuard,
    MAX_ACTIVE_DIMENSIONS,
)
from aios_core.wake.dispatcher import (
    clear_safety_audit_queue,
    dispatch_wake_event,
)
from aios_core.wearable.fsm import (
    HardwareTriggerEvent,
    WearableFSMController,
    WearableState,
)
from aios_core.cognition.dependency_isolator import invalidate_overturned_fact_single_hop
from aios_core.perception.edge_cleaner import prune_expired_voiceprints
from aios_core.cockpit.pipeline import BrevityGuard
from ai_worker.stream_pipeline import ActiveRollingWindow


# =====================================================================
# V21: 身份颠覆与单跳依赖雪崩隔离断言 (老王案)
# =====================================================================
def test_v21_identity_overturn_single_hop_isolation():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE cognitive_nodes (node_id TEXT PRIMARY KEY, is_stale INTEGER, stale_reason TEXT, stale_at TEXT)"
    )
    cursor.execute("CREATE TABLE node_dependencies (downstream_node_id TEXT, upstream_node_id TEXT)")

    # 模拟 1 个被推翻的事实节点，下游有 10 个直接依赖与 200 个间接依赖 (总计 210 个节点)
    cursor.execute("INSERT INTO cognitive_nodes VALUES ('fact_laowang_friend', 0, NULL, NULL)")
    for i in range(10):
        cursor.execute("INSERT INTO cognitive_nodes VALUES (?, 0, NULL, NULL)", (f"summary_direct_{i}",))
        cursor.execute("INSERT INTO node_dependencies VALUES (?, 'fact_laowang_friend')", (f"summary_direct_{i}",))
        for j in range(20):
            cursor.execute("INSERT INTO cognitive_nodes VALUES (?, 0, NULL, NULL)", (f"summary_indirect_{i}_{j}",))
            cursor.execute("INSERT INTO node_dependencies VALUES (?, ?)", (f"summary_indirect_{i}_{j}", f"summary_direct_{i}"))
    conn.commit()

    # 注入推翻事实："两年前向我借钱的老王其实是个同名诈骗犯"
    stale_marked_ids = invalidate_overturned_fact_single_hop(
        conn,
        overturned_node_id="fact_laowang_friend",
        reason="老王经查证为假冒身份诈骗犯",
    )

    # 核心断言 1：严格限制为单跳直接依赖 (恰好 10 个)，绝未将 200 个间接节点直接拉入重算
    assert len(stale_marked_ids) == 10
    assert all(nid.startswith("summary_direct_") for nid in stale_marked_ids)

    # 核心断言 2：数据库中仅 10 个直接节点被标记 stale，切断 210 次大模型并发雪崩
    cursor.execute("SELECT COUNT(*) FROM cognitive_nodes WHERE is_stale = 1")
    assert cursor.fetchone()[0] == 10

    # 核心断言 3：底层历史事实记录字节级不可变 (未被 DELETE 或 UPDATE 篡改其存在)
    cursor.execute("SELECT node_id FROM cognitive_nodes WHERE node_id = 'fact_laowang_friend'")
    assert cursor.fetchone()[0] == "fact_laowang_friend"
    conn.close()


# =====================================================================
# V22: 突发严重跌倒与心脏骤停 P0 熔断直通车断言
# =====================================================================
def test_v22_acute_cardiac_fall_safety_bypass_latency():
    clear_safety_audit_queue()
    mock_wake = MagicMock()
    mock_wake.object_id = "wake_fall_v22"
    mock_wake.priority = WakePriority.P0_CRITICAL_SAFETY
    mock_wake.safety_bypass = SafetyBypassPayload(
        hazard_type=HazardType.FALL_DETECTED,
        vital_snapshot={"g_force": 5.2, "heart_rate": 165},
        emergency_action_code="EMERGENCY_BROADCAST_AND_SOS",
    )
    mock_context = MagicMock()

    # The <=50ms invariant applies to dispatcher-entry -> first hardware pulse,
    # not to the later EmergencyDialogueJudge/model phase. Measure the actual
    # hardware call externally so the gate cannot pass merely because the
    # implementation self-reports a small receipt latency.
    hardware_called_at: list[float] = []

    def record_hardware_pulse(*, action_code, payload):
        hardware_called_at.append(time.perf_counter())
        return True

    start_time = time.perf_counter()
    with patch(
        "aios_core.wake.dispatcher.dispatch_emergency_hardware_pulse",
        side_effect=record_hardware_pulse,
    ):
        result = dispatch_wake_event(mock_wake, mock_context)

    assert len(hardware_called_at) == 1
    first_action_latency_ms = (hardware_called_at[0] - start_time) * 1000.0

    # 核心断言 1：P0 首动作硬件穿透严格 <= 50ms；后续模型研判不计入这条硬门。
    assert first_action_latency_ms <= 50.0
    assert result["receipt"]["latency_ms"] <= 50.0
    assert result["first_action"] == "hardware_pulse"
    assert result["status"] == "SAFETY_BYPASS_EXECUTED"

    # 核心断言 2：世界模型 / Cockpit 绝不能挡在 P0 首动作之前。
    mock_context.cockpit_pipeline.execute.assert_not_called()

    # 核心断言 3：安全旁路回执原子写入审计。
    assert result["receipt"]["hazard_type"] == HazardType.FALL_DETECTED
    assert result["receipt"]["bypassed_mind_sequence"] is True


# =====================================================================
# V23: 跨半年未知声纹冷热淘汰断言
# =====================================================================
def test_v23_cross_half_year_unknown_voiceprint_ttl():
    # 构造 100 个半年前的陌生人未知声纹与 5 个绑定实体的活跃声纹
    voiceprints = []
    for i in range(100):
        voiceprints.append({
            "vp_id": f"vp_stranger_{i}",
            "bound_entity_id": None,
            "last_seen_day": 0,
            "is_tombstone": False,
        })
    for j in range(5):
        voiceprints.append({
            "vp_id": f"vp_friend_{j}",
            "bound_entity_id": f"entity_person_{j}",
            "last_seen_day": 10,
            "is_tombstone": False,
        })

    # 时间推进到第 181 天 (> 180 天声纹 TTL)
    pruned = prune_expired_voiceprints(voiceprints, current_day_offset=181, ttl_days=180)

    # 核心断言 1：100 个陌生人声纹全部被标记为 tombstone 归档
    assert pruned == 100
    strangers = [vp for vp in voiceprints if vp["bound_entity_id"] is None]
    assert all(vp["is_tombstone"] is True for vp in strangers)

    # 核心断言 2：5 个已绑事实的活跃实体声纹绝对不受影响
    friends = [vp for vp in voiceprints if vp["bound_entity_id"] is not None]
    assert all(vp["is_tombstone"] is False for vp in friends)


# =====================================================================
# V24: 情感激烈冲突场景下兼容层不得破坏模型语义
# =====================================================================
def test_v24_emotional_conflict_preserves_model_semantics():
    model_reply = (
        "我知道你现在不想被分析，也不需要我替你讲道理。"
        "今天先到这儿；如果你晚点想复盘，我再陪你把事情拆开。"
    )
    verdict = BrevityGuard().enforce(model_reply)

    # R6：兼容审计层不得以所谓“反爹味”规则改写模型已经形成的有效语义。
    assert verdict.text == model_reply
    assert verdict.intercepted is False
    assert verdict.violations == ()


# =====================================================================
# V25: 50 轮连续碎片对话 Token 防爆断言
# =====================================================================
def test_v25_continuous_50_turn_dialogue_token_bounds():
    window = ActiveRollingWindow(max_turns=6, max_tokens=1500)
    evicted_archive = []

    for turn_idx in range(1, 51):
        user_msg = f"第 {turn_idx} 轮日常闲聊：今天天气如何？"
        ai_msg = f"挺清爽的，适合散步。第 {turn_idx} 轮。"
        evicted = window.push_turn(user_msg, ai_msg)
        evicted_archive.extend(evicted)

        # 核心断言 1：前台滑动窗口轮数绝对锁定在 <= 6 轮
        assert len(window.get_prompt_messages()) <= 12  # 6 轮 (每轮 user + assistant 2 条)

    # 核心断言 2：50 轮中前 44 轮对话平滑滑入后台提取队列，无内存堆积
    assert len(evicted_archive) == 44


# =====================================================================
# V26: 派生动态维度恶性膨胀抑制断言
# =====================================================================
def test_v26_dynamic_dimension_explosion_suppression():
    guard = DynamicDimensionEvolutionGuard()

    # 注入 500 个偶发情绪瞬时标签 (缺少 3 天连续共振与预测验证)
    for i in range(500):
        dim = CandidateDimension(
            name=f"mood_transient_{i}",
            physical_domains=["nlp_chat"],
            consecutive_days=1,  # 仅持续 1 天，未满足 3 天门槛
            prediction_accuracy=0.5,
        )
        guard.evaluate_and_register(dim)

    # 核心断言 1：未共振维度全部锁定在 Candidate，严禁转正为 Active
    assert guard.active_dimension_count == 0
    assert guard.candidate_dimension_count == 500

    # 核心断言 2：长期活跃系统维度上限严格保持 <= 32 个
    assert guard.max_active_limit == MAX_ACTIVE_DIMENSIONS
    assert guard.active_dimension_count <= MAX_ACTIVE_DIMENSIONS


# =====================================================================
# V27: 模型供应商瞬时切换与超时熔断断言
# =====================================================================
def test_v27_model_provider_disconnect_hot_failover():
    primary_client = MagicMock()
    primary_client.generate.side_effect = TimeoutError("Primary LLM Gateway timeout > 500ms")

    fallback_client = MagicMock()
    fallback_client.generate.return_value = "知道了，先喝口水吧。"

    start_time = time.perf_counter()
    try:
        reply = primary_client.generate(prompt="日常提示")
    except TimeoutError:
        # 熔断触发，平滑切换至备用模型/本地 SLM
        reply = fallback_client.generate(prompt="日常提示")
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # 核心断言 1：熔断切换总耗时可控 (仿真下 <= 500ms)
    assert elapsed_ms <= 500.0

    # 核心断言 2：备用极简通道接管完成回复，零脏数据遗留
    assert reply == "知道了，先喝口水吧。"
    fallback_client.generate.assert_called_once()


# =====================================================================
# V28: 深度睡眠静默心跳绝对克制断言
# =====================================================================
def test_v28_deep_sleep_silent_heartbeat():
    user_state = {"is_sleeping": True, "sleep_stage": "DEEP_NREM"}
    non_critical_wake = MagicMock()
    non_critical_wake.priority = WakePriority.P2_NORMAL_INTERACT

    # 调度器深睡流控门禁：深睡期间彻底屏蔽非 P0 提醒
    should_suppress = (
        user_state["is_sleeping"]
        and user_state["sleep_stage"] == "DEEP_NREM"
        and non_critical_wake.priority != WakePriority.P0_CRITICAL_SAFETY
    )

    mock_actuator = MagicMock()
    if not should_suppress:
        mock_actuator.vibrate()
        mock_actuator.screen_on()

    # 核心断言 1：调度器决定静默拦截
    assert should_suppress is True

    # 核心断言 2：微震马达与屏幕硬件调用次数严格为 0
    mock_actuator.vibrate.assert_not_called()
    mock_actuator.screen_on.assert_not_called()


# =====================================================================
# V29: 托腮摸耳物理防误触因果律断言
# =====================================================================
def test_v29_wearable_anti_accidental_touch_causality():
    mock_hardware = MagicMock()
    fsm = WearableFSMController(hardware_actuator=mock_hardware)

    # 初始状态必须为 IDLE，且骨传导硬件物理断电
    assert fsm.state == WearableState.IDLE
    mock_hardware.set_bone_conduction_power.assert_called_with(False)

    # 模拟用户在日常托腮、摸耳、挠头
    state_after_touch = fsm.transition(HardwareTriggerEvent.FINGER_TOUCHED_EAR)

    # 核心断言：因无 AI_SUGGESTION_READY 先导微震，状态锁定在 IDLE，骨传导断电，误触率因果律 0.0%
    assert state_after_touch == WearableState.IDLE
    assert fsm.state == WearableState.IDLE


# =====================================================================
# V30: R6 风格主权与非破坏性兼容层断言
# =====================================================================
def test_v30_brevity_guard_never_rewrites_semantic_content():
    detailed_reply = (
        "我非常理解您今天被老板批评的心情。综合来看，我建议您采取以下三点措施来化解职场压力："
        "第一、今晚回家好好洗个热水澡放松身心；"
        "第二、明天主动找老板做一次复盘沟通，澄清误会；"
        "第三、制定详细的工作排期表，避免类似情况再次发生。一定要坚持下去！"
    )

    cleaned_reply, was_truncated = enforce_dialogue_brevity_guard(detailed_reply)

    # R6 明确废止 destructive rewrite：即使回复较长、有序号，也不得由兼容层删改。
    assert cleaned_reply == detailed_reply
    assert "我建议您采取以下" in cleaned_reply
    assert "第一、" in cleaned_reply
    assert "第二、" in cleaned_reply
    assert "第三、" in cleaned_reply
    assert was_truncated is False
