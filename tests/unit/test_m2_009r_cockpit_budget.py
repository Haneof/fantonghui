"""M2-009R 单看板 1500 Token 封套 —— 高密危机防爆压测。

实战场景：用户遭遇重大职业危机——被公司恶意降薪、强制调岗并面临竞业
协议索赔。深夜 2 小时内经手环连续 50 轮高频、碎片、情绪激烈的对抗对话。

四大硬门禁：
1. 单看板 1500 Token 绝对物理截断：无论上下文累积多少万字，装配出的
   Single-Shot 看板总量严格 ≤ 1500 tokens；
2. 无损滚动：6 轮易变窗口；被淘汰轮次无损进入历史 Observation 归档，
   关键争议点证据（降薪幅度/竞业条款/调岗城市）零丢失；
3. Brevity Guard：长篇爹味说教注入被强制截断并合宪性拦截；
4. 50 轮压测全流程看板组装 P95 ≤ 15ms。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cockpit import (
    BrevityGuard,
    CockpitManifest,
    CrisisDialoguePipeline,
    MANIFEST_TOKEN_BUDGET,
    WINDOW_TURNS,
    estimate_tokens,
)
from aios_core.cockpit.pipeline import split_sentences
from aios_core.contracts.models import Observation

assert split_sentences("你好。再见！") == ["你好。", "再见！"]

UTC = timezone.utc
T_START = datetime(2026, 9, 15, 23, 40, 0, tzinfo=UTC)  # 深夜 23:40 起，连续 2 小时

#: 50 轮高熵危机轮次脚本（碎片、情绪激烈、含关键争议事实）
_DISPUTE_FACTS = {
    4: "他们单方面把我的年薪降了40%，连书面通知都没有",
    22: "竞业协议第7条要我赔120万，但我根本没签过那份附件",
    40: "HR口头通知下个月强制调岗厦门，不去就算自动离职",
}


def _round_text(i: int) -> str:
    if i in _DISPUTE_FACTS:
        return _DISPUTE_FACTS[i]
    fragments = (
        "他们凭什么这么干", "我现在手全是汗", "你听我说完", "凌晨了我睡不着",
        "猎头那边还没回我", "房贷还有23年", "我妈今天又问我工作怎么样",
        "公司法务刚才又发消息了", "我到底签过什么", "你说我该不该找律师",
    )
    body = fragments[i % len(fragments)]
    filler = "昨晚又是一点没睡，心率手环一直报警，我盯着天花板想这事。"
    if i >= 40:  # 深夜后段：语音碎片越来越长（真实危机对话的疲劳特征）
        filler = filler * (6 + i % 6)
    return f"{body}，{filler}"


def build_pipeline() -> CrisisDialoguePipeline:
    return CrisisDialoguePipeline(
        session_id="sess_crisis_night",
        subject_id="user_founder",
        token_budget=MANIFEST_TOKEN_BUDGET,
        window_turns=WINDOW_TURNS,
    )


def run_50_round_session() -> CrisisDialoguePipeline:
    pipeline = build_pipeline()
    at = T_START
    for i in range(1, 51):
        pipeline.push_turn("user", _round_text(i), at)
        at += timedelta(seconds=45)
        ai_text = (
            f"我在。第{i}条你说的我都记着。" if i % 7 else "先喝水，慢慢说，我在听。"
        )
        pipeline.push_turn("ai", ai_text, at)
        at += timedelta(seconds=45)
    return pipeline


ASSEMBLY_KWARGS = dict(
    wake_reason="用户主动唤起：深夜职业危机对抗对话第51轮",
    world_digest="当前主事件：恶意降薪+强制调岗+竞业索赔三线并发；心率变异性：深夜持续高位应激",
    self_mirror="上次介入停留状态：倾听陪伴；承诺：明日午前整理竞业协议疑点清单",
    ready_tasks=(
        "已承诺：对比签署版与附件版竞业条款",
        "跟进：明早9点猎头回复",
        "观察：连续3天睡眠负债",
    ),
    recall_digest=(
        "2025-11 绩效评级 A（与『能力不行』说法矛盾）",
        "2026-03 调薪记录：+12%",
        "劳动合同签署回执：未含竞业附件",
    ),
)


# ======================================================================
# 门禁 1：1500 Token 绝对物理截断
# ======================================================================

def test_gate1_manifest_hard_cap_1500_tokens_never_breached() -> None:
    pipeline = run_50_round_session()
    manifest = pipeline.assemble_manifest(
        **ASSEMBLY_KWARGS,
        session_digest="恶意降薪时间线：" + "2024年以来薪酬与考核记录逐步恶化。" * 800,
    )
    assert isinstance(manifest, CockpitManifest)
    assert manifest.token_total <= MANIFEST_TOKEN_BUDGET  # 绝对物理封顶
    assert manifest.token_budget == 1500
    assert sum(manifest.layer_tokens.values()) == manifest.token_total
    # 累积上下文 5 万+ 字被硬性压缩进 session_digest 层（≤75 tokens）
    digest_layer = manifest.layer_tokens["session_digest"]
    assert digest_layer <= int(MANIFEST_TOKEN_BUDGET * 0.05)
    # 被截断内容全部进入省略索引（指针可复查，绝不静默丢弃）
    assert any(e.layer == "session_digest" for e in manifest.omission_index)
    assert any(e.layer == "conversation_window" for e in manifest.omission_index)


def test_gate1_cap_is_structural_model_validation() -> None:
    """超预算看板在构造期直接爆炸（bug 即测试失败，绝不流入大模型）。"""
    with pytest.raises(ValueError, match="hard cap"):
        CockpitManifest(
            session_id="s",
            wake_reason="w",
            layers={"a": "x" * 50},
            layer_tokens={"a": 999_999},
            token_total=999_999,
            token_budget=1500,
            omission_index=(),
            window_turns_included=0,
            window_turn_range=None,
            assembled_at=T_START,
        )


# ======================================================================
# 门禁 2：6 轮无损滚动与争议证据零丢失
# ======================================================================

def test_gate2_six_turn_window_with_lossless_archive() -> None:
    pipeline = run_50_round_session()

    # 窗口严格保持 6 轮（最近 6 轮：T95..T100）
    window = pipeline.window
    assert len(window) == WINDOW_TURNS
    assert window[-1].turn_index == 100
    assert window[0].turn_index == 95

    # 44 轮被逐出 → 逐条无损封装为 Observation（100 条对话轮 → 94 条归档）
    archived = pipeline.archived_observations
    assert len(archived) == 94
    assert all(isinstance(o, Observation) for o in archived)

    # 关键争议点证据零丢失：三个跨小时散布的争议事实全部在归档原话中
    archived_text = "\n".join(
        str(o.value["text"]) for o in archived if o.value.get("speaker") == "user"
    )
    for turn_index, fact in _DISPUTE_FACTS.items():
        assert fact in archived_text, f"T{turn_index} 争议证据丢失: {fact}"
    # 逐字节无损：归档原话与输入完全一致（用户轮 turn_index = 2i-1）
    for round_index, fact in _DISPUTE_FACTS.items():
        expected_turn = 2 * round_index - 1
        matched = [
            o for o in archived
            if o.value.get("speaker") == "user"
            and o.value["turn_index"] == expected_turn
        ]
        assert len(matched) == 1, f"T{expected_turn} 归档缺失"
        assert matched[0].value["text"] == fact

    # 看板省略索引提供归档复查指针
    manifest = pipeline.assemble_manifest(**ASSEMBLY_KWARGS)
    window_omissions = [e for e in manifest.omission_index
                        if e.layer == "conversation_window"]
    if window_omissions:
        assert "conversation_archive" in window_omissions[0].resume_pointer


# ======================================================================
# 门禁 3：Brevity Guard 反爹味强制截断与合宪性拦截
# ======================================================================

PREACHY_INJECTION = (
    "面对职场挫折，您要保持积极心态！人生就是一场修行。"
    "为您推荐以下五点心理疏导方案：\n"
    "1、深呼吸练习，每天三次；\n"
    "2、记录情绪日记，观察自己的思维模式；\n"
    "3、进行正念冥想，接纳当下的自己；\n"
    "4、建立社会支持系统，与家人朋友沟通；\n"
    "5、必要时寻求专业心理咨询。"
    "要相信生活总会好起来的，首先调整作息，其次规律运动，最后保持希望。"
)


def test_gate3_preachy_injection_force_truncated_and_intercepted() -> None:
    pipeline = build_pipeline()
    reply = pipeline.guard_reply(PREACHY_INJECTION)

    assert reply.truncated is True
    assert reply.sentence_count <= 3                      # 1~3 句硬预算
    assert reply.text == "" or reply.sentence_count >= 0
    assert reply.preaching_detected is True
    assert "PREACHINESS_INTERCEPTED" in reply.violations
    assert "ALL_SENTENCES_PREACHY_SILENCED" in reply.violations  # 全爹味→沉默降级
    assert reply.original_sentence_count >= 8             # 原稿是长篇大论
    assert reply.reply_tokens < reply.original_tokens
    # 全稿爹味：治理降级为沉默（该闭嘴就闭嘴），零说教残留
    assert reply.text == ""
    assert "ALL_SENTENCES_PREACHY_SILENCED" in reply.violations
    # 违例已进流水线记录（→ 沟通经验回路 C12）
    assert len(pipeline.style_violations) == 1
    assert pipeline.style_violations[0].violations == reply.violations


def test_gate3_normal_buddy_reply_passes_through_untouched() -> None:
    """不误伤正常老友语调：2 句短回复零截断零违例。"""
    guard = BrevityGuard()
    reply = guard.govern("降薪40%必须有书面通知。明天我陪你去拿劳动合同原件。")
    assert reply.truncated is False
    assert reply.preaching_detected is False
    assert reply.violations == ()
    assert reply.sentence_count == 2
    assert reply.text.endswith("原件。")


def test_gate3_silence_channel_and_emergency_exemption() -> None:
    guard = BrevityGuard()
    silence = guard.govern(PREACHY_INJECTION, channel="silence")
    assert silence.text == "" and silence.sentence_count == 0
    # 紧急安全通道豁免：急救指令不被截断（但可被追踪）
    emergency = guard.govern("别动！救护车已呼出。保持侧卧。", emergency=True)
    assert emergency.truncated is False
    assert emergency.sentence_count == 3


def test_gate3_guard_is_data_driven_not_hardcoded_style_rules() -> None:
    """拦截清单是数据驱动的模式表（非死板话术规则），可独立扩展审计。"""
    from aios_core.cockpit.pipeline import PREACHY_PATTERNS

    assert len(PREACHY_PATTERNS) >= 5
    for pattern in PREACHY_PATTERNS:
        assert pattern.pattern  # 每条模式可读可审计


# ======================================================================
# 门禁 4：50 轮压测装配 P95 ≤ 15ms
# ======================================================================

def test_gate4_assembly_p95_within_15ms_over_50_rounds() -> None:
    from aios_core.cockpit.pipeline import measure_assembly_p95

    pipeline = run_50_round_session()
    p95_ms, samples = measure_assembly_p95(pipeline, rounds=50, **ASSEMBLY_KWARGS)

    assert len(samples) == 50
    assert p95_ms <= 15.0, f"manifest assembly P95 = {p95_ms}ms > 15ms"
    # 设计预期：O(预算) 装配应远离临界值
    assert p95_ms < 7.5


def test_gate4_full_50_round_session_end_to_end() -> None:
    """50 轮完整会话（推送+装配+治理）端到端压测：每轮看板均 ≤1500。"""
    import time

    pipeline = build_pipeline()
    at = T_START
    assemblies = 0
    started = time.perf_counter()
    for i in range(1, 51):
        pipeline.push_turn("user", _round_text(i), at)
        at += timedelta(seconds=45)
        pipeline.push_turn("ai", f"我在，第{i}条记着呢。", at)
        at += timedelta(seconds=45)
        manifest = pipeline.assemble_manifest(**ASSEMBLY_KWARGS)
        assert manifest.token_total <= MANIFEST_TOKEN_BUDGET
        assemblies += 1
        pipeline.guard_reply(PREACHY_INJECTION if i % 5 == 0 else "我在。说吧。")
    wall_s = time.perf_counter() - started
    assert assemblies == 50
    assert len(pipeline.archived_observations) == 100 - WINDOW_TURNS
    # 50 轮推送+装配+治理全流程应轻松压进 2 小时场景的模拟预算
    assert wall_s < 30.0


# ======================================================================
# 估算器与确定性
# ======================================================================

def test_token_estimator_is_deterministic_and_conservative() -> None:
    assert estimate_tokens("") == 0
    cjk = estimate_tokens("恶意降薪四十个点")          # 8 CJK → 8
    assert cjk == 8
    ascii_tokens = estimate_tokens("abcdefgh")          # 8 ascii → 2
    assert ascii_tokens == 2
    mixed = estimate_tokens("竞业120万索赔")            # 5 CJK + '120'(1) = 6
    assert mixed == 6
    assert estimate_tokens("竞业120万索赔") == mixed    # 确定性


def test_manifest_is_deterministic_replay() -> None:
    p1 = run_50_round_session()
    p2 = run_50_round_session()
    m1 = p1.assemble_manifest(**ASSEMBLY_KWARGS, now=T_START)
    m2 = p2.assemble_manifest(**ASSEMBLY_KWARGS, now=T_START)
    assert m1.token_total == m2.token_total
    assert m1.layers == m2.layers
    assert m1.omission_index == m2.omission_index
