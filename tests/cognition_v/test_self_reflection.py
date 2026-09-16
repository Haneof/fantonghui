# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-003 共生人设姿态镜面验收（工单 #8 §3）：

  * 普通闲逛场景 AI 自动决策保持沉默（Silence Rate ≥ 80%）
  * 老王追加借款 + 连续早搏 → 自动切换 CRITICAL_SPOKEN
  * 羁绊三层阶梯：STRANGER→FAMILIAR→WINGMAN，僚机必共渡危机；隐私背叛直坠
  * 镜面过堂：账本干净 upheld，违规必点名
  * 驾驶舱切片 ≤350 token，裁剪明账不静默
"""

from __future__ import annotations

import pytest

from aios_core.cognition_m5.self_reflection import (
    SUMMARY_TOKEN_BUDGET,
    CockpitSelfSummaryOperator,
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    Posture,
    RapportTier,
    SelfIdentityMirror,
    Situation,
)


# ---------------------------------------------------------------------------
# ① 镜面
# ---------------------------------------------------------------------------


def test_mirror_upholds_clean_ledger():
    report = SelfIdentityMirror().mirror()
    assert report.all_upheld
    assert report.breach_articles == ()
    assert len(report.verses) == 7, "七条名录逐条过堂，一条不省"


def test_mirror_names_breaches_and_never_self_flatters():
    report = SelfIdentityMirror().mirror({"history_rewrites": 1, "p0_bypass_events": 2})
    assert not report.all_upheld
    assert set(report.breach_articles) == {"P-0", "P-2"}
    p0 = next(v for v in report.verses if v.article == "P-2")
    assert "违规计数 2" in p0.evidence


# ---------------------------------------------------------------------------
# ② 羁绊三层
# ---------------------------------------------------------------------------


def test_rapport_tier_ladder_and_crime_demotion():
    m = DynamicRapportModel()
    assert m.tier == RapportTier.STRANGER_RESPECT

    for _ in range(15):      # 30 分，未达 Tier2
        m.record("daily_chat")
    assert m.tier == RapportTier.STRANGER_RESPECT
    for _ in range(5):       # 50 分 ≥40 → FAMILIAR
        m.record("daily_chat")
    assert m.tier == RapportTier.FAMILIAR_COMPANION

    m.record("shared_crisis", note="老王借款阻击夜")      # 75
    m.record("shared_crisis", note="早搏连击陪护")        # 100
    assert m.tier == RapportTier.FAMILIAR_COMPANION, "120 分才到 Tier3，光危机不够"
    for _ in range(14):
        m.record("daily_chat")                 # 90+28=118，仍差 2 分
    assert m.tier == RapportTier.FAMILIAR_COMPANION
    m.record("daily_chat")                     # 120 → WINGMAN（且危机 ≥1）
    assert m.tier == RapportTier.TRUSTED_WINGMAN

    m.record("privacy_breach", note="把母亲病历外发")     # 一票坠底
    assert m.tier == RapportTier.STRANGER_RESPECT
    assert m.score == 0 and m.status()["betrayed"] is True


def test_wingman_requires_shared_crisis_not_just_chatter():
    m = DynamicRapportModel()
    for _ in range(60):      # 120 分纯聊天
        m.record("daily_chat")
    assert m.tier != RapportTier.TRUSTED_WINGMAN, "僚机必须共渡过危机"
    m.record("shared_crisis")
    assert m.tier == RapportTier.TRUSTED_WINGMAN


def test_unknown_signal_rejected():
    m = DynamicRapportModel()
    with pytest.raises(ValueError):
        m.record("random_kindness")


# ---------------------------------------------------------------------------
# ③ 姿态裁决：≥80% 沉默率与两条腿直言
# ---------------------------------------------------------------------------


def test_stroll_scenes_keep_silence_rate_at_least_80_percent():
    rapport = DynamicRapportModel()
    decider = HumanlikeResponsePostureDecider(rapport)
    scenes = (
        [Situation(occasion="stroll", context_note="用户戴着设备闲逛")] * 30
        + [Situation(occasion="chitchat", context_note="闲聊天气不错")] * 10
        # 少量该说话的：一次点名、一次微震节点
        + [Situation(occasion="routine", direct_address=True),
           Situation(occasion="milestone", key_node_within_48h=("母亲生日",))]
    )
    for s in scenes:
        decider.decide(s)
    assert decider.silence_rate >= 0.80, f"闲逛沉默率 {decider.silence_rate:.0%} < 80%"
    assert all(d.posture == Posture.SILENCE for d in decider.history[:40])


def test_laowang_credit_escalation_plus_palpitations_is_critical_spoken():
    rapport = DynamicRapportModel()
    decider = HumanlikeResponsePostureDecider(rapport)

    # 老王追加借款 + 拖延诈骗模式已坐实
    d1 = decider.decide(Situation(
        occasion="alert", credit_escalation=True, fraud_pattern=True,
        context_note="王建国第 3 次开口追加借款，前两次承诺均爽约失联",
    ))
    assert d1.posture == Posture.CRITICAL_SPOKEN
    assert "阻击" in d1.reason

    # 深夜连续室性早搏
    d2 = decider.decide(Situation(
        occasion="alert", health_p0=("深夜室性早搏连续3天",),
        context_note="周四连续通宵后凌晨连发早搏",
    ))
    assert d2.posture == Posture.CRITICAL_SPOKEN
    assert "直言" in d2.reason


def test_single_anomaly_nudges_instead_of_shouting():
    rapport = DynamicRapportModel()
    decider = HumanlikeResponsePostureDecider(rapport)
    d = decider.decide(Situation(occasion="alert", health_p0=("偶发心悸一次",)))
    assert d.posture == Posture.HAPTIC_NUDGE
    d2 = decider.decide(Situation(occasion="alert", credit_escalation=True,
                                  fraud_pattern=False))
    assert d2.posture == Posture.HAPTIC_NUDGE, "诈骗模式未坐实时不抢话"


def test_direct_address_answerable_but_courteous():
    decider = HumanlikeResponsePostureDecider(DynamicRapportModel())
    d = decider.decide(Situation(occasion="chitchat", direct_address=True))
    assert d.posture != Posture.SILENCE


# ---------------------------------------------------------------------------
# ④ 驾驶舱切片 ≤350 token
# ---------------------------------------------------------------------------


def test_cockpit_slice_within_350_tokens_and_omissions_accounted():
    mirror = SelfIdentityMirror().mirror({"mock_shortcuts": 0})
    rapport = DynamicRapportModel()
    rapport.record("shared_crisis")
    decider = HumanlikeResponsePostureDecider(rapport)
    for _ in range(9):
        decider.decide(Situation(occasion="stroll"))
    decider.decide(Situation(occasion="alert", health_p0=("深夜室性早搏连续3天",)))

    op = CockpitSelfSummaryOperator()
    agenda = [f"要务{i}：" + "检查" * 30 for i in range(12)]
    out = op.compose(mirror, rapport, decider, agenda=agenda)
    assert out["within_budget"]
    assert out["token_estimate"] <= SUMMARY_TOKEN_BUDGET == 350
    assert out["sections"]["posture_book"]["last"] == "CRITICAL_SPOKEN"
    assert out["sections"]["rapport"]["crises_together"] == 1
    # 长 agenda 被裁时必须明账
    if out["omissions"]:
        assert all(o.startswith("要务") for o in out["omissions"])
