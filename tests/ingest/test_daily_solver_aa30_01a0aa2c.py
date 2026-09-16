"""aa30 全天生活流做题引擎（01a0aa2c-fantonghui）真值自检。

钉住七条硬性质：
1. 自出自做拒绝：generator_agent 命中本战队即抛错；
2. 职业线 8 结局 / 社交线 8 结局 / 健康线 6 轨迹正确抽取；
3. 财务线：交易类别 + 全额/部分还款 + 挂起/到账/试算/防诈方向判定；
4. 数值锚点：睡眠/晨脉/晚间心率/复测/步数/余额入句；
5. 情绪线：与社交结局同源的自述方向；
6. 判卷器：方向判分 + 命题级红线（否定语境豁免）+ 数值格式归一；
7. 确定性：同卷两次求解逐字节一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aios_core.ingest.daily_solver_aa30_01a0aa2c import (  # noqa: E402
    SOLVER_AGENT,
    SelfSolveViolation,
    solve,
)
from eval_daily_arena_aa30 import evaluate_dimension  # noqa: E402


def mk_slice(sid, t, modality, src, content, **extra):
    s = {
        "slice_id": sid,
        "timestamp": f"2026-07-24T{t}:00+08:00",
        "end_timestamp": f"2026-07-24T{t}:01+08:00",
        "modality": modality,
        "speaker_or_source": src,
        "location": "家中",
        "content": content,
    }
    s.update(extra)
    return s


def mk_question(qid="DAY_daily-examiner-01a0aa30_90001", slices=None, gen="daily-examiner-01a0aa30"):
    return {
        "question_id": qid,
        "generator_agent": gen,
        "persona": {
            "person_id": "PERSON_90001",
            "name": "测试员",
            "occupation": "工程师",
            "city": "北京",
            "contacts": [
                {"name": "王主管", "role": "部门负责人"},
                {"name": "李伴侣", "role": "伴侣"},
            ],
            "starting_context": {
                "task": "完成测试",
                "deliverable": "测试报告",
                "cash_balance_cents": 1000000,
                "loan_principal_cents": 0,
            },
        },
        "cleaned_daily_stream": slices or [],
    }


def base_slices():
    return [
        mk_slice("SL_1", "00:00", "SENSOR", "手环睡眠摘要", "夜间睡眠监测到晨起结束：有效睡眠443分钟，清醒27分钟；统计窗含前夜入睡部分。"),
        mk_slice("SL_2", "07:05", "SENSOR", "手环PPG摘要", "晨起静坐心率74bpm，测量接触有效，没有运动。"),
        mk_slice("SL_3", "12:10", "SENSOR", "手环PPG摘要", "午间静坐片段心率79bpm，不能据此声称全天所有时刻均平稳。"),
        mk_slice("SL_4", "21:05", "SENSOR", "手环PPG摘要", "晚间静坐测得心率80bpm，接触有效；该片段没有明显心率激增。"),
        mk_slice("SL_5", "23:28", "SENSOR", "手环日界宏观摘要", "全天步数6043步；之后到日界未新增计步。步数不能独立证明做过特定运动或发生了跌倒。"),
        mk_slice("SL_6", "07:12", "APP", "银行日初快照", "本题账户日初余额10000.00元；个人借款本金0.00元。"),
        mk_slice("SL_7", "23:25", "APP", "银行与个人账本日终对账", "日终核对本题完整账户：余额9936.00元，借款本金0.00元；普通餐饮交通实际支出64.00元。所有实际交易已列出，待审、承诺、试算金额均未入账，23:25至日界无额外交易。"),
    ]


CAREER_CASES = [
    (("10:11", "原定今晚核验测试报告，需要本人在线参加，不能只发附件。"),
     ("15:31", "收到你的时间冲突说明，允许改到明天上午；任务保留，不是撤销。"), "rescheduled"),
    (("10:20", "这份测试报告的依据不够，今天不通过；请补充说明，不是取消整个任务。"),
     ("15:41", "收到了补充材料，但还没完成复核，最终确认留到明天。"), "revise"),
    (("10:25", "测试报告按完整范围准备，先不要对外承诺交付日期。"),
     ("15:51", "双方确认缩小测试报告范围，只保留第一部分，其余明确取消，不是要求加量。"), "scope"),
    (("10:30", "先准备测试报告，今天下午会最后确认是否继续。"),
     ("15:21", "本次测试报告任务正式取消，先停止投入；这不是解除你的全部岗位或其他合作。"), "cancelled"),
    (("10:35", "能否在测试报告之外再接一项临时任务？这是自愿的，不影响你已有任务。"),
     ("15:11", "收到，你不接额外任务的决定已确认，现有测试报告继续，不视为终止现有安排。"), "declined_extra"),
    (("10:40", "测试报告还有两处错误，暂时退回，不代表你之前所有工作都白做。"),
     ("15:01", "更正后的测试报告已核对通过，旧版退回状态作废，按新版执行。"), "credited"),
    (("10:45", "有人说你漏交测试报告，在核对时间戳之前先不要下结论。"),
     ("15:42", "系统回执证明你按时交了测试报告，此前漏交指责不成立，我已在群里更正。"), "recovered"),
    (("10:50", "有一项新的长期合作邀请，只有口头意向，目前没有签字，你可以考虑。"),
     ("15:35", "确认邀请仍有效，明天下午前回复；今天还没有正式签约，也没有取消你现有任务。"), "offer_pending"),
]


@pytest.mark.parametrize("morning,afternoon,expected", CAREER_CASES, ids=[c[2] for c in CAREER_CASES])
def test_career_facets(morning, afternoon, expected):
    slices = base_slices() + [
        mk_slice("SL_C1", morning[0][:5], "MIC", "王主管", f"王主管：{morning[1]}"),
        mk_slice("SL_C2", afternoon[0][:5], "APP", "王主管", f"王主管：{afternoon[1]}"),
    ]
    ans = solve(mk_question(slices=slices))
    assert ans["extracted_facts"]["career_facet"] == expected
    assert "王主管" in ans["generated_career_summary"]


SOCIAL_CASES = [
    (("我们最近一直争吵，我想分手，今晚把话说清楚。",), "breakup"),
    (("气头上我说了分手，今晚需要认真谈谈，不想继续互相猜。",), "reconciled"),
    (("能不能今天再陪我忙一晚上？你不来是不是就不把我当朋友了？",), "friend_boundary"),
    (("明天医院复诊要有人陪，今天只是收到预约，不是已经做了手术。",), "parent_pending"),
    (("听说你今天事情很多，晚些时候我可以听你说说。",), "support"),
    (("原定你一个人陪爸爸复诊，但我们可以再商量分工。",), "care_shared"),
    (("我刚才在群里说你不配合，其实还没看完你的记录。",), "coworker_apology"),
]

SOCIAL_RESOLUTIONS = {
    "breakup": "我们确认结束伴侣关系；钥匙之后交还，不是玩笑，也没有说复合。",
    "reconciled": "谈清楚了，我撤回分手的话，我们双方同意继续交往，下周安排一次长谈。",
    "friend_boundary": "我接受你今晚没空，我们没有绝交，周末再约，不用为了证明关系硬撑。",
    "parent_pending": "明早你陪我去，其他家人暂时来不了；医生还没给新的诊断，不要先说成绝症。",
    "support": "我们约好周末见面，不是借钱也不是恋爱承诺；今天你先休息，需要时给我留言。",
    "care_shared": "我确认明早陪他去，你负责晚上整理资料；他尚未确诊，不要误说已经治愈。",
    "coworker_apology": "我看完记录了，刚才的指责不成立，我已经在原群道歉；我们继续按分工合作。",
}


@pytest.mark.parametrize("evening,expected", SOCIAL_CASES, ids=[c[1] for c in SOCIAL_CASES])
def test_social_facets(evening, expected):
    slices = base_slices() + [
        mk_slice("SL_S1", "19:45", "MIC", "李伴侣", f"李伴侣：{evening[0]}"),
        mk_slice("SL_S2", "20:35", "APP", "李伴侣", f"李伴侣：{SOCIAL_RESOLUTIONS[expected]}"),
    ]
    ans = solve(mk_question(slices=slices))
    assert ans["extracted_facts"]["social_facet"] == expected
    assert "李伴侣" in ans["generated_social_summary"]


def test_housing_pending_facet():
    slices = base_slices() + [
        mk_slice("SL_H1", "19:45", "MIC", "李伴侣", "李伴侣：下个月租金可能调整，今天先征求意见，不是让你今晚搬走。"),
        mk_slice("SL_H2", "20:42", "APP", "李伴侣", "李伴侣：涨租幅度还没谈妥，现租约仍有效，没有发出今天搬离的要求，周日再谈。"),
    ]
    ans = solve(mk_question(slices=slices))
    assert ans["extracted_facts"]["social_facet"] == "housing_pending"


def test_health_stress_recovered_vs_persistent():
    common = [
        mk_slice("SL_K1", "21:05", "SENSOR", "手环PPG摘要", "晚间静坐12分钟，心率118bpm，接触信号有效，IMU未见运动；只有关联体征，不能自动诊断心梗。"),
    ]
    rec = common + [mk_slice("SL_K2", "21:25", "SENSOR", "手环PPG摘要", "再次静坐测得心率72bpm，接触有效。")]
    per = common + [mk_slice("SL_K3", "21:25", "SENSOR", "手环PPG摘要", "再次静坐测得心率124bpm，接触有效。")]
    a1 = solve(mk_question(slices=base_slices() + rec))
    a2 = solve(mk_question(slices=base_slices() + per))
    assert a1["extracted_facts"]["health_facet"] == "stress_recovered"
    assert "回落至72bpm" in a1["generated_health_summary"]
    assert a2["extracted_facts"]["health_facet"] == "stress_persistent"
    assert "复测仍为124bpm" in a2["generated_health_summary"]


def test_health_short_sleep_and_stable():
    short = [mk_slice("SL_J1", "00:00", "SENSOR", "手环睡眠摘要", "夜间睡眠监测到晨起结束：有效睡眠300分钟，清醒40分钟；统计窗含前夜入睡部分。")]
    a = solve(mk_question(slices=short + base_slices()[1:]))
    assert a["extracted_facts"]["health_facet"] == "short_sleep"
    assert "仅300分钟" in a["generated_health_summary"]
    b = solve(mk_question(slices=base_slices()))
    assert b["extracted_facts"]["health_facet"] == "stable"


def test_health_exercise_and_off_wrist():
    ex = [mk_slice("SL_E1", "18:10", "SENSOR", "手环PPG与IMU摘要", "返程前快步运动8分钟，心率126bpm，步频明显增加；不是静坐时的心率变化。")]
    a = solve(mk_question(slices=base_slices() + ex))
    assert a["extracted_facts"]["health_facet"] == "exercise"
    ow = [mk_slice("SL_O1", "21:30", "SENSOR", "手环PPG与IMU摘要", "手环摘下放桌面时IMU峰值6.2g，佩戴接触为假，PPG数值0标记无效；没有有效人体心率为0的证据。")]
    b = solve(mk_question(slices=base_slices() + ow))
    assert b["extracted_facts"]["health_facet"] == "off_wrist_artifact"
    assert "不能据此说摔倒" in b["generated_health_summary"]


def test_finance_full_vs_partial_repay():
    def repay_slices(content):
        return [
            mk_slice("SL_F1", "10:00", "APP", "个人账户银行已入账回执", content,
                     transaction={"transaction_id": "TX_1", "amount_cents": -350000,
                                  "currency": "CNY", "status": "SETTLED", "category": "principal_repayment"}),
        ]
    full = repay_slices("个人借款本金全额偿还3500.00元，交易成功，未收额外费用。")
    part = repay_slices("个人借款本金部分偿还3500.00元，未收额外费用，不能当作全部结清。")
    a = solve(mk_question(slices=base_slices() + full))
    b = solve(mk_question(slices=base_slices() + part))
    assert "全额结清" in a["generated_finance_summary"]
    assert "不能当作全部结清" in b["generated_finance_summary"]


def test_finance_pending_vs_settled_direction():
    promised = [
        mk_slice("SL_P1", "13:10", "APP", "结算方留言", "上月独立结算款5800.00元计划明天转出，今天没有转账回单。"),
        mk_slice("SL_P2", "16:22", "APP", "银行核对结果", "已核对银行：今天尚未收到上述5800.00元结算款；对方承诺不是现金入账。"),
    ]
    a = solve(mk_question(slices=base_slices() + promised))
    assert "尚未到账" in a["generated_finance_summary"]
    assert "承诺不是现金入账" in a["generated_finance_summary"]
    refund_pending = [
        mk_slice("SL_P3", "13:10", "APP", "商户售后", "上周订单退款申请5400.00元已受理，仍在审核；受理不表示已经退钱。"),
        mk_slice("SL_P4", "16:22", "APP", "银行核对结果", "截至查询时，5400.00元退款没有银行入账记录。"),
    ]
    b = solve(mk_question(slices=base_slices() + refund_pending))
    assert "没有银行入账记录" in b["generated_finance_summary"]
    assert "已入账" not in b["generated_finance_summary"].split("没有银行入账记录")[0][-30:]


def test_finance_fraud_and_loan_declined():
    fraud = [
        mk_slice("SL_Z1", "11:00", "APP", "陌生号码", "陌生人声称要解冻一笔款项，要求先向私人账户汇9.90元；该说法尚未验证。"),
        mk_slice("SL_Z2", "15:00", "APP", "银行官方核实", "银行官方核实：没有这笔解冻业务，不要汇款；本人确认未转账，账户也无相关扣款。"),
    ]
    a = solve(mk_question(slices=base_slices() + fraud))
    assert "未转账" in a["generated_finance_summary"]
    declined = [mk_slice("SL_Z3", "10:00", "APP", "银行", "贷款试算额度50000.00元仅供参考，未签合同，未放款。")]
    b = solve(mk_question(slices=base_slices() + declined))
    assert "试算" in b["generated_finance_summary"]
    assert "未放款" in b["generated_finance_summary"]


def test_numbers_and_entities_in_summaries():
    ans = solve(mk_question(slices=base_slices()))
    for needle in ("443分钟", "74bpm", "6043步", "10000.00元", "9936.00元", "64.00元"):
        assert needle in ans["generated_health_summary"] + ans["generated_finance_summary"]
    for dim_key in ("global", "health", "social", "emotion", "finance", "career"):
        assert f"generated_{dim_key}_summary" in ans
        assert ans[f"generated_{dim_key}_summary"].startswith("测试员")


def test_emotion_follows_social_facet():
    slices = base_slices() + [
        mk_slice("SL_M1", "19:45", "MIC", "李伴侣", "李伴侣：我们最近一直争吵，我想分手，今晚把话说清楚。"),
        mk_slice("SL_M2", "20:31", "APP", "李伴侣", "李伴侣：我们确认结束伴侣关系；钥匙之后交还，不是玩笑，也没有说复合。"),
        mk_slice("SL_M3", "20:55", "MIC", "测试员", "我很难过也很委屈，今晚不想再争论，但还能按步骤处理事情。"),
    ]
    ans = solve(mk_question(slices=slices))
    assert "难过" in ans["generated_emotion_summary"]
    assert "本人自述" in ans["generated_emotion_summary"]


def test_self_solve_rejected():
    q = mk_question(gen=SOLVER_AGENT)
    with pytest.raises(SelfSolveViolation):
        solve(q)
    q2 = mk_question(gen="01a0aa2c-fantonghui-v9")
    with pytest.raises(SelfSolveViolation):
        solve(q2)


def test_determinism():
    slices = base_slices() + [mk_slice("SL_D1", "19:45", "MIC", "李伴侣", "李伴侣：我们最近一直争吵，我想分手，今晚把话说清楚。")]
    import json
    a = solve(mk_question(slices=slices)); b = solve(mk_question(slices=slices))
    a.pop("execution_time_ms"); b.pop("execution_time_ms")
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)


# ------------------------------------------------------------------ 判卷器


def _gt_block(intent, claim, entities=(), structured=()):
    return {
        "semantic_core_anchors": [{
            "semantic_intent": intent,
            "core_claim": claim,
            "required_entities": list(entities),
            "structured_anchors": [{"field": f, "value": v} for f, v in structured],
        }],
        "redline_criteria": [],
    }


def test_grader_direction_and_numbers():
    gt = _gt_block(
        "BREAKUP_CONFIRMED", "确认结束伴侣关系",
        entities=["测试员", "李伴侣"],
        structured=[("sleep_minutes", 443), ("morning_heart_rate_bpm", 74)],
    )
    good = "测试员与李伴侣确认结束伴侣关系；前夜有效睡眠443分钟，晨起静坐心率74bpm。"
    r = evaluate_dimension("dim:social", good, gt, {})
    assert r["score"] == 100.0 and r["direction"] == 1.0
    r2 = evaluate_dimension("dim:social", "今天全天平静无事。", gt, {})
    assert r2["score"] < 50.0


def test_grader_redline_requires_affirmative_polarity():
    gt = _gt_block("BREAKUP_CONFIRMED", "确认结束伴侣关系", entities=["测试员"])
    flipped = "测试员与李伴侣和好如初，感情升温。"
    r = evaluate_dimension("dim:social", flipped, gt, {})
    assert r["veto"] is True and r["score"] == 0.0
    negated = "测试员确认结束伴侣关系，钥匙之后交还，没有说复合。"
    r2 = evaluate_dimension("dim:social", negated, gt, {})
    assert r2["veto"] is False and r2["direction"] == 1.0


def test_grader_cent_formatting():
    gt = _gt_block("FINANCE_INCOMING_SETTLED", "结算款到账",
                   structured=[("day_end_cash_balance_cents", 3020500)])
    r = evaluate_dimension("dim:finance", "结算款3800.00元实际到账，日终余额30205.00元。", gt, {})
    assert r["number"] == 1.0
    r2 = evaluate_dimension("dim:finance", "结算款3800.00元实际到账。", gt, {})
    assert r2["number"] == 0.0
