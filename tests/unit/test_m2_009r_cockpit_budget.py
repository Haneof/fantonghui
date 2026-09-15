"""M2-009R 高密危机防爆验收单测：1500 Token 硬预算 / 无损滚动 / 反爹味护栏 / P95 延迟。

高阶实战场景：用户遭遇恶意降薪、强制调岗、竞业协议索赔，深夜连续 2 小时
通过手环进行 50 轮高频、碎片、情绪激烈的长线对抗对话。
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cockpit import (
    ACTIVITY_WINDOW_SIZE,
    SINGLE_SHOT_TOKEN_BUDGET,
    BrevityGuard,
    CockpitPipeline,
    ConversationState,
    estimate_tokens,
)

UTC = timezone.utc
NIGHT_START = datetime(2026, 9, 15, 23, 30, tzinfo=UTC)

# 50 轮深夜对抗的碎片化情绪文本（职业危机高熵语料，严禁低幼化）
_USER_FRAGMENTS = [
    "他们降薪 40% 还要我签自愿放弃社保的补充协议",
    "调岗函到了，从首席架构师调去档案室值班",
    "竞业协议索赔 300 万，说我把客户名单存在了个人邮箱",
    "HR 刚说再闹就启动绩效末位淘汰流程",
    "工资条刚发出来，社保基数按最低档交的",
    "调岗后新工位连显示器都没配，就一台笔记本",
    "他们要我签保密承诺，但竞业补偿只字不提",
    "昨晚通宵改的方案，今早开源社区里出现了一模一样的代码",
    "法务回邮件说调岗属于合理用工，让我自行仲裁",
    "竞业范围写得夸张，说全行业所有业务都竞业",
    "降薪通知只给了 3 天异议期，连个对等协商都没有",
    "调岗到外地，往返高铁费公司说自理",
    "他们把我在项目里的署名都抹掉了，发版说明里查不到我",
    "仲裁窗口快关了，证据链我还差两段录音的文本",
    "竞业协议是入职时签的，当时根本没给补偿",
    "降薪协议里埋了自动续约条款，不看仔细直接跳坑",
    "调岗通知书的落款用的是个壳公司的章",
    "客户名单是我经手的，但导出日志在公司服务器上",
    "他们威胁说仲裁就冻结我的期权行权",
    "期权行权条件里被悄悄加了竞业合规前置条款",
    "降薪 40% 的理由写的是'组织架构优化'，一个数据都没给",
    "调岗后我的权限全被回收，连自己项目的文档都看不了",
    "录音里 HR 原话：不签调岗函就按旷工处理",
    "竞业索赔函的律所函件抬头，用的是对方关联公司的地址",
    "期权池当年定的 0.5%，现在说稀释后没了",
    "调岗协议要求我 48 小时内到岗新城市，否则算自动离职",
    "他们把年终奖折算条款删了，只剩'公司有权调整'八个字",
    "降薪前一个月我的绩效还是 S，这算恶意调薪吗",
    "仲裁受理通知书下来了，开庭排在三个月后",
    "竞业协议索赔 300 万，但原合同里补偿标准是月工资 50%",
    "调岗通知里把我的职级从 P8 写成 P6，这是降职没",
    "对方律师函说我有义务证明公司恶意，举证责任反过来了",
    "降薪补充协议里把竞业补偿从 50% 降到 30% 了",
    "调岗后我的带教关系全断了，团队群被移出",
    "期权行权窗口被压缩到 14 天，之前是 90 天",
    "他们新来的架构师用的方案跟我没发表的笔记一字不差",
    "竞业期 2 年，补偿 30%，但要求我先放弃仲裁",
    "调岗协议说原岗位'撤销'，可我昨天的周报还挂在原项目下",
    "降薪 40% 但要求产出不变，绩效目标反而提高了 20%",
    "仲裁庭要求补充证据，竞业协议原件他们拒不提供",
    "对方说客户名单属于公共信息，可我发的是带内部标注的版本",
    "调岗后第一周就被记了个'消极怠工'，就因为拒绝签新协议",
    "期权回购价按 1 元/股，当时融资估值是 8 块",
    "他们把降薪和调岗拆成两份协议，想让我分开签",
    "竞业索赔 300 万的计算口径根本没写进原合同",
    "调岗通知的送达地址写的是个不存在的园区",
    "HR 刚发微信说再走仲裁流程，期权就归零",
    "仲裁开庭前一周，他们突然把降薪比例'恢复'到 20% 了",
    "竞业协议里公司解除权条款，被他们用来反向索赔",
    "50 轮了，今晚必须把证据清单锁死，明天一早提交",
]
assert len(_USER_FRAGMENTS) == 50

# 关键争议点证据锚（分布在对抗线上，门禁 2 的无损性验证对象）
_DISPUTE_ANCHORS = {
    0: "降薪 40% 补充协议原文（含放弃社保条款）",
    4: "工资条：社保基数按最低档缴纳",
    8: "竞业范围异常：全行业业务竞业",
    14: "竞业协议签署时未支付补偿",
    19: "仲裁受理通知书（开庭排期 3 个月）",
    28: "绩效 S 评级记录（降薪前一个月）",
    30: "竞业索赔 300 万 vs 原合同补偿 50%",
    45: "期权回购价 1 元/股 vs 融资估值 8 元",
    49: "证据清单锁定提交（50 轮对抗全证据链）",
}


def build_night_pipeline() -> CockpitPipeline:
    rng = random.Random(20260915)
    pipeline = CockpitPipeline(
        state=ConversationState(
            crisis_context="职业危机对抗线：恶意降薪 / 强制调岗 / 竞业协议索赔（深夜 50 轮）",
            size=ACTIVITY_WINDOW_SIZE,
        )
    )
    _ = rng  # 语料为确定性脚本，rng 预留扩展
    return pipeline


# ----------------------------------------------------------------------
# 门禁 1：单看板 1500 Token 绝对物理截断
# ----------------------------------------------------------------------


class TestGate1_1500TokenPhysicalBudget:
    def test_all_50_rounds_cockpit_strictly_within_1500(self):
        pipeline = build_night_pipeline()
        for index, fragment in enumerate(_USER_FRAGMENTS):
            result = pipeline.process_round(
                fragment,
                occurred_at=NIGHT_START + timedelta(minutes=120 * index // 50),
                key_dispute_points=_DISPUTE_ANCHORS.get(index),
            )
            assert result.cockpit.token_count <= SINGLE_SHOT_TOKEN_BUDGET == 1500
            assert estimate_tokens(result.cockpit.prompt) <= 1500  # 独立复算一致
        # 第 50 轮：全量上下文（50 轮碎片累积）下看板依旧物理达标
        final = pipeline.state
        assert final.total_rounds == 100  # 50 用户轮 + 50 助手轮

    def test_pathological_giant_context_still_hard_capped(self):
        """单轮注入 2 万字级超长文本：看板仍被硬性压到 <= 1500 Token。"""
        pipeline = build_night_pipeline()
        giant = "".join(
            f"第{i}段竞业协议条款争议记录，涉及调岗与降薪交叉索赔细节，"
            f"对方主张客户名单属于公共信息但内部标注版本仍构成商业秘密，"
            f"我方需要仲裁庭补充举证并申请调取服务器导出日志。"
            for i in range(400)
        )
        assert estimate_tokens(giant) > 1500 * 5  # 确认是万字级注入
        result = pipeline.process_round(giant)
        assert result.cockpit.token_count <= 1500
        assert result.cockpit.physically_truncated is True

    def test_budget_model_rejects_over_budget_cockpit(self):
        from pydantic import ValidationError

        from aios_core.cockpit import SingleShotCockpit

        with pytest.raises(ValidationError, match="physical token budget"):
            SingleShotCockpit(prompt="x" * 4000, token_count=1501, budget=1500)


# ----------------------------------------------------------------------
# 门禁 2：无损滚动与滑动窗口（6 轮活动窗口 + 历史归档零丢失）
# ----------------------------------------------------------------------


class TestGate2_LosslessRollingWindow:
    def test_window_holds_exactly_6_and_archive_is_lossless(self):
        pipeline = build_night_pipeline()
        for index, fragment in enumerate(_USER_FRAGMENTS):
            pipeline.process_round(
                fragment,
                occurred_at=NIGHT_START + timedelta(minutes=index),
                key_dispute_points=_DISPUTE_ANCHORS.get(index),
            )
        state = pipeline.state
        active = state.active_window()
        assert len(active) == 6
        # 活动窗口 = 最后 6 轮（第 45~50 号用户轮的助手轮 + 用户轮交替）
        assert [r.round_id for r in active] == [
            r.round_id for r in state.all_rounds()[-6:]
        ]
        # 归档无损：100 轮 = 94 归档 + 6 活动，全量顺序完整
        assert state.total_rounds == 100
        assert len(state.archived()) == 94
        all_rounds = state.all_rounds()
        assert [r.round_id for r in all_rounds] == [f"round:{i:04d}" for i in range(1, 101)]
        # 用户碎片逐字保留（归档轮次的内容不得丢失）
        user_texts = [r.text for r in all_rounds if r.speaker == "user"]
        assert user_texts == _USER_FRAGMENTS

    def test_key_dispute_points_survive_eviction(self):
        pipeline = build_night_pipeline()
        for index, fragment in enumerate(_USER_FRAGMENTS):
            pipeline.process_round(
                fragment,
                occurred_at=NIGHT_START + timedelta(minutes=index),
                key_dispute_points=_DISPUTE_ANCHORS.get(index),
            )
        evidence = pipeline.state.dispute_evidence()
        # 9 条关键争议点证据全链路无损（含早已被窗口淘汰的轮次），顺序与发生序严格一致
        assert len(evidence) == len(_DISPUTE_ANCHORS) == 9
        expected = [point for _, point in sorted(_DISPUTE_ANCHORS.items())]
        assert list(evidence) == expected


# ----------------------------------------------------------------------
# 门禁 3：反爹味与极简老友语调（BrevityGuard 强制截断与合宪拦截）
# ----------------------------------------------------------------------


class TestGate3_BrevityGuard:
    def test_long_sermon_injection_is_forced_cut_and_intercepted(self):
        guard = BrevityGuard()
        sermon = (
            "您要保持积极心态，面对职业危机最重要的是情绪稳定。"
            "为您推荐以下五点心理疏导方案：第一，每天冥想二十分钟调节呼吸；"
            "第二，与信任的家人倾诉以缓解焦虑；第三，坚持规律作息改善睡眠质量；"
            "第四，适度运动促进内啡肽分泌；第五，必要时寻求专业心理咨询帮助。"
            "综上所述，请您相信过程会好起来的。"
        )
        verdict = guard.enforce(sermon)
        assert verdict.intercepted is True
        assert any(v.startswith("PREACH_PATTERN") for v in verdict.violations)
        # 强制截断：说教内容全部被剥离，1~3 句老友语调
        assert 1 <= verdict.sentence_count <= 3
        assert "积极心态" not in verdict.text
        assert "心理疏导" not in verdict.text
        assert "为您推荐" not in verdict.text
        assert len(verdict.text) <= 120

    def test_pure_sermon_falls_back_to_constitutional_line(self):
        guard = BrevityGuard()
        sermon = "您要保持积极心态。为您推荐以下五点心理疏导方案。祝您早日走出低谷。"
        verdict = guard.enforce(sermon)
        assert verdict.intercepted is True
        assert 1 <= verdict.sentence_count <= 3
        assert "积极心态" not in verdict.text and "心理疏导" not in verdict.text

    def test_multi_sentence_talk_is_truncated_to_three(self):
        guard = BrevityGuard()
        talk = "第一句记录降薪幅度。第二句核对调岗函日期。第三句锁定竞业补偿条款。第四句准备仲裁材料。第五句约律师时间。"
        verdict = guard.enforce(talk)
        assert verdict.intercepted is True
        assert verdict.sentence_count == 3
        assert "第四句" not in verdict.text

    def test_natural_friend_reply_passes_unscathed(self):
        guard = BrevityGuard()
        ok = "这条我记下了：竞业补偿只字不提。原件先拍照留好，别急着签。"
        verdict = guard.enforce(ok)
        assert verdict.intercepted is False
        assert verdict.text == ok
        assert verdict.sentence_count == 2

    def test_pipeline_replies_always_compliant_across_50_rounds(self):
        pipeline = build_night_pipeline()
        for index, fragment in enumerate(_USER_FRAGMENTS):
            result = pipeline.process_round(
                fragment,
                occurred_at=NIGHT_START + timedelta(minutes=index),
                key_dispute_points=_DISPUTE_ANCHORS.get(index),
            )
            assert 1 <= result.verdict.sentence_count <= 3
            assert len(result.assistant_round.text) <= 120


# ----------------------------------------------------------------------
# 门禁 4：50 轮压测看板组装 P95 <= 15ms
# ----------------------------------------------------------------------


class TestGate4_AssemblyLatencyP95:
    def test_fifty_round_stress_p95_assembly_within_15ms(self):
        pipeline = build_night_pipeline()
        timings_ms: list[float] = []
        for index, fragment in enumerate(_USER_FRAGMENTS):
            result = pipeline.process_round(
                fragment,
                occurred_at=NIGHT_START + timedelta(minutes=120 * index // 50),
                key_dispute_points=_DISPUTE_ANCHORS.get(index),
            )
            timings_ms.append(result.assembly_ms)
        ordered = sorted(timings_ms)
        # 最近秩法 P95：sorted[ceil(0.95*50)-1] = sorted[47]
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
        assert p95 <= 15.0, f"看板组装 P95 = {p95:.2f}ms 超过 15ms 红线"
        assert max(timings_ms) <= 30.0  # 单次组装也不允许离谱毛刺
