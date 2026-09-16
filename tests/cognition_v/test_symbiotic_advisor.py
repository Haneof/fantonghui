# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-004 共生顾问验收（工单 #9 §3，输出质量绝对第一）：

  * ActionableAdvice 必携因果证据 ObjectRef 清单（≥1），否则构造即拒收
  * 泛泛套话（多喝热水/注意休息/…）出不了舱
  * 母亲生日：足浴盆倒水腰疼闲置 + 丝巾落灰 ⇒ 两品类排除；
    2026 膝盖受凉 ⇒ 命中轻便膝盖气囊热敷理疗仪
  * 防诈：朝阳判决 + 微信拖延切片 ⇒ 硬核阻击 + 资产追偿
  * 健康：周四连续通宵 + 室性早搏 ⇒ 疲劳熔断 + 心电图复查清单
"""

from __future__ import annotations

import pytest

from aios_core.cognition_m5.symbiotic_advisor import (
    ActionableAdvice,
    Alternative,
    CourtJudgment,
    EvidenceRef,
    FatigueSignal,
    FeedbackTone,
    FraudPreventionAdvisor,
    GiftHistoryRecord,
    HealthFatigueBreakerAdvisor,
    MomBirthdayGiftAdvisor,
    MomSignal,
    WechatStallSlice,
)


def _ref(oid: str, why: str = "") -> EvidenceRef:
    return EvidenceRef(object_id=oid, revision=1, why=why or "因果链环")


# ---------------------------------------------------------------------------
# ActionableAdvice 硬门
# ---------------------------------------------------------------------------


def test_advice_without_evidence_is_rejected():
    with pytest.raises(ValueError, match="证据"):
        ActionableAdvice(
            advisor_id="x", conclusion="结论", evidence=(),
            alternatives=(Alternative("备", "次选"),),
            expected_benefit="收益", causal_chain="链",
        )


def test_generic_phrase_cannot_leave_the_cabin():
    for phrase in ("多喝热水", "注意休息", "保重身体", "早点睡觉"):
        with pytest.raises(ValueError, match=phrase):
            ActionableAdvice(
                advisor_id="x", conclusion=f"建议{phrase}再观察",
                evidence=(_ref("e-1"),),
                alternatives=(Alternative("备", "次选"),),
                expected_benefit="收益", causal_chain="链",
            )


def test_advice_without_alternatives_is_rejected():
    with pytest.raises(ValueError, match="备选"):
        ActionableAdvice(
            advisor_id="x", conclusion="结论", evidence=(_ref("e-1"),),
            alternatives=(), expected_benefit="收益", causal_chain="链",
        )


# ---------------------------------------------------------------------------
# ① 母亲生日礼物
# ---------------------------------------------------------------------------


def _mom_history() -> list[GiftHistoryRecord]:
    return [
        GiftHistoryRecord(2023, "真丝丝巾", "accessory",
                          FeedbackTone.PRISTINE_DUSTY, "吊牌未剪，落灰三年",
                          _ref("gift-2023")),
        GiftHistoryRecord(2024, "全自动足浴盆", "foot_bath",
                          FeedbackTone.PAIN_TO_USE, "倒水弯腰腰疼，用两次闲置",
                          _ref("gift-2024")),
        GiftHistoryRecord(2025, "按摩椅", "massage",
                          FeedbackTone.BELOVED, "反馈极佳，每日都用",
                          _ref("gift-2025")),
    ]


def test_mom_gift_hits_knee_therapy_and_excludes_rejected_categories():
    advisor = MomBirthdayGiftAdvisor()
    signal = MomSignal("最近膝盖受凉，上下楼都费力", _ref("mom-signal-2026"))
    advice = advisor.advise(_mom_history(), signal)

    assert "轻便膝盖气囊热敷理疗仪" in advice.conclusion
    assert "足浴盆" not in [a.option for a in advice.alternatives], "倒水腰疼的品类永久出局"
    assert all("珍珠" not in a.option and "丝巾" not in a.option
               for a in advice.alternatives), "落灰饰品类永久出局"
    # 因果链把四年账摆齐了
    for token in ("2023", "2024", "2025", "落灰", "腰疼", "极佳", "膝盖受凉"):
        assert token in advice.causal_chain, f"链上缺环 {token}"
    # 证据 ObjectRef 一个不缺：3 年记录 + 当年信号
    refs = {e.object_id for e in advice.evidence}
    assert refs == {"gift-2023", "gift-2024", "gift-2025", "mom-signal-2026"}
    assert advice.alternatives, "必给备选"


# ---------------------------------------------------------------------------
# ② 防诈阻击
# ---------------------------------------------------------------------------


def test_fraud_advisor_blocks_hard_and_chases_assets():
    advisor = FraudPreventionAdvisor()
    judgments = [CourtJudgment(
        court="北京市朝阳区人民法院", case_no="(2025)京0105民初12345号",
        holding="王建国偿还借款本金 18 万元及利息，限判决生效十日内履行",
        ref=_ref("court-judgment-1"))]
    slices = [
        WechatStallSlice("2026-09-02T21:14:00+08:00", "工程款在凑，下周准还",
                         _ref("wc-slice-1")),
        WechatStallSlice("2026-09-09T22:40:00+08:00", "过两天回不了你找我",
                         _ref("wc-slice-2")),
    ]
    advice = advisor.advise("王建国", 50_000, judgments, slices)

    assert "硬核阻击" in advice.conclusion and "一分不出" in advice.conclusion
    assert "资产追偿" in advice.conclusion
    assert "(2025)京0105民初12345号" in advice.causal_chain
    assert "50,000" in advice.conclusion
    refs = {e.object_id for e in advice.evidence}
    assert {"court-judgment-1", "wc-slice-1", "wc-slice-2"} <= refs


def test_fraud_advisor_refuses_without_sitting_evidence():
    advisor = FraudPreventionAdvisor()
    with pytest.raises(RuntimeError, match="判决书"):
        advisor.advise("王建国", 10_000, [],
                       [WechatStallSlice("2026-09-01T10:00:00+08:00", "下周还",
                                         _ref("wc-0"))])
    with pytest.raises(RuntimeError, match="拖延切片"):
        advisor.advise("王建国", 10_000,
                       [CourtJudgment("北京市朝阳区人民法院", "X", "判还款",
                                      _ref("c-1"))],
                       [WechatStallSlice("2026-09-01T10:00:00+08:00",
                                         "已转账请查收", _ref("wc-1"))])


# ---------------------------------------------------------------------------
# ③ 健康疲劳熔断
# ---------------------------------------------------------------------------


def test_fatigue_breaker_fuses_and_orders_ecg_checklist():
    advisor = HealthFatigueBreakerAdvisor()
    signal = FatigueSignal(
        consecutive_all_nighters=2,      # 周四连续通宵
        premature_ventricular_beats=True,
        latest_ecg_days_ago=180,
        ref=_ref("vitals-watch-20260916"),
    )
    advice = advisor.advise(signal)
    assert "疲劳熔断激活" in advice.conclusion
    for token in ("心电图", "Holter", "心内科", "咖啡因清零"):
        assert token in advice.conclusion, f"清单缺 {token}"
    assert advice.evidence[0].object_id == "vitals-watch-20260916"
    assert "猝死风险窗口" in advice.causal_chain


def test_fatigue_breaker_never_misfires_below_threshold():
    advisor = HealthFatigueBreakerAdvisor()
    with pytest.raises(RuntimeError, match="熔断线"):
        advisor.advise(FatigueSignal(
            consecutive_all_nighters=1, premature_ventricular_beats=False,
            latest_ecg_days_ago=30, ref=_ref("v-1")))


# ---------------------------------------------------------------------------
# 综合：三台的证据从不缺席
# ---------------------------------------------------------------------------


def test_every_advice_object_carries_object_refs_end_to_end():
    mom = MomBirthdayGiftAdvisor().advise(
        _mom_history(), MomSignal("膝盖受凉，上下楼费力", _ref("s-1")))
    fraud = FraudPreventionAdvisor().advise(
        "王建国", 30_000,
        [CourtJudgment("北京市朝阳区人民法院", "Y", "判还款", _ref("j-1"))],
        [WechatStallSlice("2026-09-10T20:00:00+08:00", "在凑下周还", _ref("w-1"))])
    health = HealthFatigueBreakerAdvisor().advise(FatigueSignal(
        2, True, None, _ref("v-9")))
    for advice in (mom, fraud, health):
        assert advice.evidence and all(
            e.as_ref()["object_id"] for e in advice.evidence), \
            f"{advice.advisor_id} 证据断链"
