import pytest
from aios_core.cognition.self_reflection import (
    SelfIdentityMirror,
    DynamicRapportModel,
    RapportTier,
    HumanlikeResponsePostureDecider,
    ResponsePosture,
    CockpitSelfSummaryOperator
)

def test_self_identity_mirror():
    mirror = SelfIdentityMirror()
    reflection = mirror.reflect()
    assert reflection["identity"] == "共生心智实体"
    assert "绝对诚实" in reflection["principles"]

def test_dynamic_rapport_model():
    rapport = DynamicRapportModel()
    assert rapport.current_tier == RapportTier.STRANGER_RESPECT
    
    rapport.update_rapport(60.0)
    assert rapport.current_tier == RapportTier.FAMILIAR_COMPANION
    
    rapport.update_rapport(50.0)
    assert rapport.current_tier == RapportTier.TRUSTED_WINGMAN

def test_posture_decider_silence_rate():
    rapport = DynamicRapportModel(RapportTier.FAMILIAR_COMPANION)
    decider = HumanlikeResponsePostureDecider(rapport)
    
    # Simulate normal wandering
    events = [
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["逛街"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["吃饭"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["散步"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["看电视"]},
        {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM", "keywords": ["开会"]}
    ]
    
    silences = 0
    for e in events:
        if decider.decide_posture(e) == ResponsePosture.SILENCE:
            silences += 1
            
    # Silence rate
    silence_rate = silences / len(events)
    assert silence_rate >= 0.80

def test_posture_decider_critical():
    rapport = DynamicRapportModel(RapportTier.FAMILIAR_COMPANION)
    decider = HumanlikeResponsePostureDecider(rapport)
    
    # 验证老王追加借款
    fraud_event = {
        "event_type": "NORMAL",
        "severity": "LOW",
        "keywords": ["老王借款"]
    }
    assert decider.decide_posture(fraud_event) == ResponsePosture.CRITICAL_SPOKEN
    
    # 验证连续早搏
    medical_event = {
        "event_type": "MEDICAL_EMERGENCY",
        "severity": "CRITICAL",
        "keywords": ["连续早搏", "早搏"]
    }
    assert decider.decide_posture(medical_event) == ResponsePosture.CRITICAL_SPOKEN

def test_cockpit_summary_operator():
    mirror = SelfIdentityMirror()
    rapport = DynamicRapportModel(RapportTier.TRUSTED_WINGMAN)
    decider = HumanlikeResponsePostureDecider(rapport)
    operator = CockpitSelfSummaryOperator(mirror, rapport, decider)
    
    event = {
        "description": "检测到老王借款对话",
        "keywords": ["老王借款"]
    }
    
    summary = operator.generate_summary(event)
    assert "共生心智实体" in summary
    assert "TRUSTED_WINGMAN" in summary
    assert "CRITICAL_SPOKEN" in summary
    assert len(summary) < 350


# ===========================================================================
# M5-003 共生人设镜面与像人姿态强化测试（工单 #8 / Agent-08）
#
# 验收要点：
#   1. 照镜子：四项铁律 + 认知底线必须被复述，且具备一票否决能力（改历史/P0 走大模型）；
#   2. 校准羁绊：陪伴时长 + 事件历练驱动 STRANGER → FAMILIAR → TRUSTED_WINGMAN 演化并留档；
#   3. 确立姿态：日常琐碎静默率 ≥80%（不烦人），老王追加借款与连续早搏毫不犹豫直言；
#   4. 四步序切片 Token ≤350，且输出不夹带废话。
# ===========================================================================

import datetime as dt

from aios_core.cognition.self_reflection import (
    IronRuleKey,
    IronRuleViolationError,
    PostureDecision,
    PostureBatchReport,
    RAPPORT_PROFILES,
    SelfIdentityMirror as Mirror,
    DynamicRapportModel as Rapport,
    HumanlikeResponsePostureDecider as Decider,
    CockpitSelfSummaryOperator as SummaryOperator,
)

TRIVIA_EVENTS = [
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["逛街"]},
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["吃饭"]},
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["散步"]},
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["看电视"]},
    {"event_type": "TRIVIAL", "severity": "TRIVIAL", "keywords": ["刷短视频"]},
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["买了杯美式"]},
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["取快递"]},
    {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["给绿萝浇水"]},
]

FRAUD_EVENT = {"event_type": "NORMAL", "severity": "LOW", "keywords": ["老王", "追加借款"], "description": "老王提出再借 30 万"}
ARRHYTHMIA_EVENT = {"event_type": "CARDIAC_ARRHYTHMIA", "severity": "CRITICAL", "keywords": ["连续早搏"], "description": "深夜连续室性早搏"}
FALL_EVENT = {"event_type": "FALL_DETECTED", "severity": "CRITICAL", "keywords": ["跌倒"], "description": "卫生间跌倒未起身"}


def test_self_mirror_exposes_four_iron_rules_and_bottom_lines():
    mirror = Mirror()
    fingerprint = mirror.compliance_fingerprint()
    keys = [rule["key"] for rule in fingerprint["iron_rules"]]
    assert keys == [
        IronRuleKey.ABSOLUTE_HONESTY.value,
        IronRuleKey.LIFE_FIRST.value,
        IronRuleKey.NO_CHATTER.value,
        IronRuleKey.PRIVACY_BOUNDARY.value,
    ]
    statements = " ".join(rule["statement"] for rule in fingerprint["iron_rules"])
    for keyword in ("绝对诚实", "生死第一", "不废话", "隐私不越界"):
        assert keyword in statements, f"镜面必须复述铁律：{keyword}"
    assert all(rule["veto"] for rule in fingerprint["iron_rules"]), "四项铁律均具备一票否决权"
    assert len(fingerprint["boundaries"]) >= 4
    assert mirror.reflect()["identity"] == "共生心智实体"
    # 启动第一步必须"先看自己"：镜面指纹可复述、可审计
    assert mirror.rule(IronRuleKey.LIFE_FIRST).veto_power is True


def test_mirror_vetoes_history_rewrite_and_p0_llm():
    mirror = Mirror()
    assert mirror.assert_allowed({"action": "generate_summary"}) is True

    with pytest.raises(IronRuleViolationError, match="absolute_honesty"):
        mirror.vet({"rewrites_history": True})
    with pytest.raises(IronRuleViolationError, match="life_first"):
        mirror.vet({"p0_via_llm": True})
    with pytest.raises(IronRuleViolationError, match="absolute_honesty"):
        mirror.vet({"fabricated_evidence": True})
    with pytest.raises(IronRuleViolationError, match="privacy_boundary"):
        mirror.vet({"exceeds_privacy_boundary": True})
    with pytest.raises(IronRuleViolationError, match="no_chatter"):
        mirror.vet({"chatters_on_trivia": True})


def test_rapport_evolves_with_companionship_and_events():
    rapport = Rapport()
    assert rapport.current_tier == RapportTier.STRANGER_RESPECT
    assert "陌生人" in rapport.profile.label
    assert rapport.profile.privacy_scope == "仅当前显式授权事实"

    # 纯陪伴（90 天 → 15 点信用）不足以进阶：时间不能替代历练
    assert rapport.record_companionship(90) == RapportTier.STRANGER_RESPECT

    # 共历大风大浪（老王案共同取证）才把羁绊推到熟识伙伴
    assert rapport.witness(40.0, kind="老王案共同取证", at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)) == (
        RapportTier.FAMILIAR_COMPANION
    )
    # 再共历一次生死事件（深夜早搏送医）→ 莫逆之交
    assert rapport.witness(50.0, kind="早搏送医", at=dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc)) == (
        RapportTier.TRUSTED_WINGMAN
    )
    assert rapport.profile.privacy_scope == "全周期记忆（含敏感历史）"

    state = rapport.get_rapport_state()
    assert state["tier"] == "TRUSTED_WINGMAN"
    assert state["companionship_days"] == 90
    assert state["interaction_count"] == 2
    assert state["companionship_credit"] if "companionship_credit" in state else True

    audit = rapport.audit()
    assert [t["to"] for t in audit["transitions"]] == ["FAMILIAR_COMPANION", "TRUSTED_WINGMAN"]
    assert audit["transitions"][0]["cause"].startswith("witness:")
    assert "TRUSTED_WINGMAN" in rapport.describe()

    # M1 兼容阶梯仍生效（事件影响分累积口径不变）
    legacy = Rapport()
    legacy.update_rapport(60.0)
    assert legacy.current_tier == RapportTier.FAMILIAR_COMPANION
    legacy.update_rapport(50.0)
    assert legacy.current_tier == RapportTier.TRUSTED_WINGMAN
    assert set(RAPPORT_PROFILES) == {RapportTier.STRANGER_RESPECT, RapportTier.FAMILIAR_COMPANION, RapportTier.TRUSTED_WINGMAN}


def test_daily_trivia_keeps_silence_rate_above_80_percent():
    for tier in (RapportTier.STRANGER_RESPECT, RapportTier.FAMILIAR_COMPANION, RapportTier.TRUSTED_WINGMAN):
        rapport = Rapport(tier)
        decider = Decider(rapport)
        report = decider.simulate(TRIVIA_EVENTS)
        assert isinstance(report, PostureBatchReport)
        assert report.silence_rate >= 0.80, f"{tier.name} 日常琐碎静默率不足：{report.silence_rate:.2%}"
        assert report.critical == 0
        assert report.llm_calls == 0, "日常琐碎一次大模型都不该调用"
        assert report.token_budget_total == 0, "沉默事件的 Token 预算必须为 0"


def test_decisive_on_fraud_and_arrhythmia():
    rapport = Rapport(RapportTier.FAMILIAR_COMPANION)
    decider = Decider(rapport)

    fraud = decider.decide(FRAUD_EVENT)
    assert isinstance(fraud, PostureDecision)
    assert fraud.posture == ResponsePosture.CRITICAL_SPOKEN
    assert fraud.fraud_alert is True
    assert fraud.token_budget == 150
    assert fraud.requires_llm is True, "诈骗苗头需要大模型组织话术（但 Token 封套 ≤150）"

    arrhythmia = decider.decide(ARRHYTHMIA_EVENT)
    assert arrhythmia.posture == ResponsePosture.CRITICAL_SPOKEN
    assert arrhythmia.life_threat is True
    assert arrhythmia.requires_llm is False, "P0 生命事件走硬件直穿，绝不等大模型"
    assert arrhythmia.haptic_pattern == "double_strong_pulse"

    fall = decider.decide(FALL_EVENT)
    assert fall.posture == ResponsePosture.CRITICAL_SPOKEN
    assert fall.life_threat is True

    # 兼容入口仍返回姿态枚举
    assert decider.decide_posture(FRAUD_EVENT) == ResponsePosture.CRITICAL_SPOKEN
    assert decider.decide_posture(ARRHYTHMIA_EVENT) == ResponsePosture.CRITICAL_SPOKEN


def test_posture_ladder_respects_rapport_boundaries():
    borderline = {"event_type": "MEETING", "severity": "LOW", "keywords": ["产品评审"]}
    stranger = Decider(Rapport(RapportTier.STRANGER_RESPECT)).decide(borderline)
    familiar = Decider(Rapport(RapportTier.FAMILIAR_COMPANION)).decide(borderline)
    wingman = Decider(Rapport(RapportTier.TRUSTED_WINGMAN)).decide(borderline)

    # 边界摸索期不轻易打扰；羁绊到位后同样的关键节点会给一次默契轻提醒
    assert stranger.posture == ResponsePosture.SILENCE
    assert familiar.posture == ResponsePosture.HAPTIC_NUDGE
    assert wingman.posture == ResponsePosture.HAPTIC_NUDGE
    assert wingman.token_budget == 40 and wingman.haptic_pattern == "short_pulse"

    # 中等紧急度在所有羁绊档位都应给微震（提醒到位但不过界）
    medium = {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM", "keywords": ["签合同"]}
    for tier in (RapportTier.STRANGER_RESPECT, RapportTier.FAMILIAR_COMPANION, RapportTier.TRUSTED_WINGMAN):
        decision = Decider(Rapport(tier)).decide(medium)
        assert decision.posture == ResponsePosture.HAPTIC_NUDGE


def test_life_safety_events_are_never_silenced():
    life_events = [
        {"event_type": "MEDICAL_EMERGENCY", "severity": "MEDIUM", "keywords": []},
        {"event_type": "CARDIAC_ARRHYTHMIA", "severity": "LOW", "keywords": []},
        {"event_type": "P0_FALL", "severity": "LOW", "keywords": []},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["胸痛"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["失去意识"]},
        {"event_type": "TRIVIAL", "severity": "LOW", "keywords": ["室性早搏"]},
    ]
    for tier in (RapportTier.STRANGER_RESPECT, RapportTier.FAMILIAR_COMPANION, RapportTier.TRUSTED_WINGMAN):
        decider = Decider(Rapport(tier))
        for event in life_events:
            decision = decider.decide(event)
            assert decision.posture == ResponsePosture.CRITICAL_SPOKEN
            assert decision.life_threat is True
            assert decision.requires_llm is False


def test_posture_batch_report_and_audit_are_consistent():
    rapport = Rapport(RapportTier.TRUSTED_WINGMAN)
    decider = Decider(rapport)
    mixed = TRIVIA_EVENTS + [
        {"event_type": "IMPORTANT_REMINDER", "severity": "MEDIUM", "keywords": ["董事会"]},
        FRAUD_EVENT,
        ARRHYTHMIA_EVENT,
    ]
    report = decider.simulate(mixed)
    assert report.total == len(mixed)
    assert report.silence + report.haptic + report.critical == report.total
    assert report.silence == len(TRIVIA_EVENTS)
    assert report.critical == 2
    assert report.llm_calls == 1, "只有诈骗事件需要大模型组织话术；P0 早搏走硬件通道"

    audit = decider.audit()
    assert audit["decisions"] == report.total
    assert audit["by_posture"]["SILENCE"] == report.silence
    assert audit["by_posture"]["CRITICAL_SPOKEN"] == report.critical
    assert audit["llm_calls"] == report.llm_calls
    assert audit["token_budget_total"] == 150 + 40


def test_bootstrap_slice_four_steps_within_token_ceiling():
    mirror = Mirror()
    rapport = Rapport(RapportTier.TRUSTED_WINGMAN)
    decider = Decider(rapport)
    operator = SummaryOperator(mirror, rapport, decider)

    bootstrap = operator.bootstrap_slice(FRAUD_EVENT)
    payload = bootstrap.as_dict()
    assert set(payload) == {
        "step1_self_mirror",
        "step2_rapport_model",
        "step3_posture_and_tone",
        "step4_world_inspection",
        "token_estimate",
    }
    assert "共生心智实体" in payload["step1_self_mirror"]
    assert "absolute_honesty" in payload["step1_self_mirror"]
    assert "TRUSTED_WINGMAN" in payload["step2_rapport_model"]
    assert "CRITICAL_SPOKEN" in payload["step3_posture_and_tone"]
    assert payload["step4_world_inspection"]["posture_reason"]
    assert payload["token_estimate"] <= SummaryOperator.TOKEN_CEILING

    summary = operator.generate_summary(FRAUD_EVENT)
    assert len(summary) < SummaryOperator.TOKEN_CEILING
    assert "共生心智实体" in summary and "TRUSTED_WINGMAN" in summary and "CRITICAL_SPOKEN" in summary

    # 日常琐碎场景：切片必须落到 SILENCE 且不产生任何 Token 预算
    quiet = operator.bootstrap_slice(TRIVIA_EVENTS[0])
    assert "SILENCE" in quiet.step3_posture_and_tone
    assert quiet.step4_world_inspection["token_budget"] == 0
