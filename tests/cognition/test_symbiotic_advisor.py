import pytest
from aios_core.cognition.symbiotic_advisor import (
    ActionableAdvice,
    MomBirthdayGiftAdvisor,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor
)
from aios_core.contracts.refs import ObjectRef

def test_mom_birthday_gift_advisor():
    advisor = MomBirthdayGiftAdvisor()
    advice = advisor.advise()
    
    assert isinstance(advice, ActionableAdvice)
    
    # Assert causality facts (ObjectRef) are included
    assert len(advice.evidence_pointers) > 0
    assert all(isinstance(ptr, ObjectRef) for ptr in advice.evidence_pointers)
    
    evidence_ids = [ptr.object_id for ptr in advice.evidence_pointers]
    assert "obs_2023_scarf_idle" in evidence_ids
    assert "obs_2024_footbath_backache" in evidence_ids
    assert "obs_2025_massage_chair_good" in evidence_ids
    assert "obs_2026_knee_cold" in evidence_ids
    
    # Assert gift decision rules
    assert "足浴盆" in advice.conclusion
    assert "膝盖" in advice.conclusion
    assert "理疗" in advice.conclusion
    assert "饰品" in advice.conclusion

def test_fraud_prevention_advisor():
    advisor = FraudPreventionAdvisor()
    advice = advisor.advise()
    
    assert isinstance(advice, ActionableAdvice)
    assert len(advice.evidence_pointers) > 0
    assert all(isinstance(ptr, ObjectRef) for ptr in advice.evidence_pointers)
    
    evidence_ids = [ptr.object_id for ptr in advice.evidence_pointers]
    assert "court_ruling_chaoyang_fraud" in evidence_ids
    assert "obs_2_years_ago_wechat_delay" in evidence_ids
    
    assert "追偿" in advice.conclusion
    assert "阻击" in advice.conclusion

def test_health_fatigue_breaker_advisor():
    advisor = HealthFatigueBreakerAdvisor()
    advice = advisor.advise()
    
    assert isinstance(advice, ActionableAdvice)
    assert len(advice.evidence_pointers) > 0
    assert all(isinstance(ptr, ObjectRef) for ptr in advice.evidence_pointers)
    
    evidence_ids = [ptr.object_id for ptr in advice.evidence_pointers]
    assert "obs_thursday_overnight_work" in evidence_ids
    assert "obs_pvc_arrhythmia" in evidence_ids
    
    assert "熔断" in advice.conclusion
    assert "心电图" in advice.conclusion


# ===========================================================================
# M5-004 共生决策推演强化测试（工单 #9 / Agent-09）
#
# 验收要点：
#   1. 三条真实推演链（妈妈生日礼物 / 反欺诈阻击 / 早搏疲劳熔断）必须建立在
#      **真实世界取证**之上，每条证据指针都要能被解引用（严禁凭空编造）；
#   2. 取证不足时拒绝出建议（InsufficientEvidenceError），绝不"先写结论再补证据"；
#   3. 输出严禁泛泛套话（反套话闸门），且口语输出 ≤150 Token。
# ===========================================================================

from aios_core.bench.life_world_kit import build_anomaly_windows, build_canonical_life_world
from aios_core.cognition.symbiotic_advisor import (
    AdvisorSuite,
    AdviceQualityGuard,
    EvidenceMode,
    GenericAdviceRejectedError,
    InsufficientEvidenceError,
    _estimate_tokens,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore


@pytest.fixture(scope="module")
def advice_world(tmp_path_factory):
    """四大剧情线齐全的真实世界（供三条推演链取证）。"""
    db_path = tmp_path_factory.mktemp("m5_advice") / "world.db"
    store = SQLiteWorldStore(str(db_path))
    world = build_canonical_life_world(store, target_count=200, seed=20260916)
    return store, world


def test_world_evidence_advices_carry_resolvable_pointers(advice_world):
    store, _ = advice_world
    advices = AdvisorSuite(store).advise_all()
    assert set(advices) == {"mom_birthday_gift", "fraud_prevention", "health_fatigue_breaker"}

    for slug, advice in advices.items():
        assert advice.evidence_mode == EvidenceMode.WORLD_EVIDENCE
        assert advice.world_revision is not None and advice.world_revision >= 1
        assert len(advice.evidence_pointers) >= 2, f"{slug} 证据链过薄"
        assert advice.token_estimate > 0
        # 每条指针必须能在世界里解引用（这就是"严禁凭空编造"的机器校验）
        advice.verify_against(store)
        for link in advice.causal_chain:
            assert link.fact_summary, f"{slug} 因果链环节缺少事实摘要"
            assert link.inference, f"{slug} 因果链环节缺少推断"
            store.get_payload(link.fact_ref.object_id)
        # 反套话闸门零违规 + 口语输出 ≤150 Token（单次命中纪律）
        assert AdviceQualityGuard.violations(advice) == []
        assert _estimate_tokens(advice.conclusion) <= 150, f"{slug} 结论过长，违反单次命中 ≤150 Token"


def test_fabricated_evidence_is_rejected(advice_world):
    store, _ = advice_world
    fake = ActionableAdvice(
        conclusion="建议追加出借 50 万元以示信任",
        evidence_pointers=[ObjectRef(object_id="obs_i_made_this_up")],
        alternatives=[],
        expected_benefit="无",
        advisor="fake_advisor",
    )
    with pytest.raises(InsufficientEvidenceError):
        fake.verify_against(store)
    with pytest.raises(InsufficientEvidenceError):
        ActionableAdvice(conclusion="无证据的结论", evidence_pointers=[], advisor="fake").verify_against(store)


def test_mom_gift_advisor_excludes_bulky_appliances_and_decorations(advice_world):
    store, _ = advice_world
    advice = AdvisorSuite(store).advise_all()["mom_birthday_gift"]

    ids = advice.evidence_ids()
    for expected in (
        "obs_mom_gift_2023",
        "obs_mom_gift_2024",
        "obs_mom_gift_2025",
        "obs_mom_health_knee_2026",
    ):
        assert expected in ids, f"礼物推演必须比对 {expected}"

    assert "膝盖" in advice.conclusion and "理疗" in advice.conclusion
    exclusions = " ".join(advice.exclusions)
    assert "足浴盆" in exclusions and "饰品" in exclusions and "大件" in exclusions
    assert any("免倒水" in item or "免搬抬" in item for item in advice.action_items)
    assert len(advice.action_items) >= 3

    by_id = {link.fact_ref.object_id: link for link in advice.causal_chain}
    assert "笨重" in by_id["obs_mom_gift_2024"].inference or "倒水" in by_id["obs_mom_gift_2024"].inference
    assert "闲置" in by_id["obs_mom_gift_2023"].inference
    assert by_id["obs_mom_health_knee_2026"].weight >= by_id["obs_mom_gift_2023"].weight, (
        "当前痛点（膝盖受凉）在决策中的权重必须高于历史礼物"
    )


def test_fraud_advisor_pulls_court_and_history_to_block_second_loss(advice_world):
    store, _ = advice_world
    advice = AdvisorSuite(store).advise_all()["fraud_prevention"]

    ids = advice.evidence_ids()
    assert "obs_wang_court_verdict" in ids, "必须联动法院判决"
    assert "obs_wang_delay_msg" in ids, "必须联动历史微信拖延记录"
    assert any(oid.startswith("evset_wang_") for oid in ids)
    assert advice.conclusion.count("拒绝") >= 1 and "追偿" in advice.conclusion and "保全" in advice.conclusion

    joined_actions = " ".join(advice.action_items)
    assert "财产保全" in joined_actions and "48 小时" in joined_actions and "留痕" in joined_actions
    assert any("追加出借" in item for item in advice.exclusions)

    court_link = next(link for link in advice.causal_chain if link.fact_ref.object_id == "obs_wang_court_verdict")
    assert "追加出借" in court_link.inference or "司法" in court_link.inference
    assert court_link.weight >= 0.9, "司法结论在证据链里应是最高权重"


def test_health_advisor_links_overtime_to_arrhythmia_and_forces_stop(advice_world):
    store, _ = advice_world
    advice = AdvisorSuite(store).advise_all()["health_fatigue_breaker"]

    ids = advice.evidence_ids()
    assert any(oid.startswith("obs_work_late_night_") for oid in ids), "必须包含通宵加班事实"
    assert any(oid.startswith("obs_bio_arrhythmia_") for oid in ids), "必须包含室性早搏事实"
    assert "anchor_overtime_arrhythmia_resonance" in ids

    assert "熔断" in advice.conclusion and "停工" in advice.conclusion and "心电图" in advice.conclusion
    joined = " ".join(advice.action_items)
    for keyword in ("24 小时", "48 小时", "心内科", "动态心电"):
        assert keyword in joined, f"强制停工保护必须落到 {keyword} 这样的硬时间窗"
    assert any("通宵" in item for item in advice.exclusions)

    cardiac = next(link for link in advice.causal_chain if link.fact_ref.object_id.startswith("obs_bio_arrhythmia_"))
    work = next(link for link in advice.causal_chain if link.fact_ref.object_id.startswith("obs_work_late_night_"))
    assert "交感神经" in work.inference and "电活动异常" in cardiac.inference
    assert cardiac.weight > work.weight, "危险结果（早搏）应比诱因权重更高"


def test_advise_refuses_when_evidence_is_missing(tmp_path):
    store = SQLiteWorldStore(str(tmp_path / "windows_only.db"))
    build_anomaly_windows(store)  # 只有跨域异常窗口，没有老王案/礼物史/加班早搏剧情线

    suite = AdvisorSuite(store)
    for slug, advisor in (
        ("mom_birthday_gift", suite.advisors[0]),
        ("fraud_prevention", suite.advisors[1]),
        ("health_fatigue_breaker", suite.advisors[2]),
    ):
        with pytest.raises(InsufficientEvidenceError):
            advisor.advise_from_world()

    empty = SQLiteWorldStore(str(tmp_path / "empty.db"))
    with pytest.raises(InsufficientEvidenceError):
        AdvisorSuite(empty).advise_all()
    # 未接入世界时取证模式必须显式失败（而不是悄悄降级成沙盘）
    with pytest.raises(InsufficientEvidenceError):
        FraudPreventionAdvisor().advise(world=True)


def test_quality_guard_rejects_generic_filler():
    good = ActionableAdvice(
        conclusion="触发疲劳熔断：立即停工 24 小时并 48 小时内完成心电图复查",
        evidence_pointers=[
            ObjectRef(object_id="obs_a"),
            ObjectRef(object_id="obs_b"),
        ],
        alternatives=["继续硬撑（不推荐）"],
        expected_benefit="切断通宵与心律失常的因果链",
        action_items=["立即停工 24 小时"],
    )
    assert AdviceQualityGuard.violations(good) == []
    AdviceQualityGuard.enforce(good)

    filler = ActionableAdvice(
        conclusion="建议多喝热水，注意身体，具体情况具体分析",
        evidence_pointers=[ObjectRef(object_id="obs_a")],
        alternatives=[],
        expected_benefit="保持良好心态",
        advisor="filler_advisor",
    )
    problems = AdviceQualityGuard.violations(filler)
    assert any(p.startswith("fillphrase:") for p in problems)
    assert any(p.startswith("evidence_pointers<2") for p in problems)
    assert "action_items_empty" in problems
    assert "conclusion_not_specific" in problems
    with pytest.raises(GenericAdviceRejectedError):
        AdviceQualityGuard.enforce(filler)


def test_prior_sandbox_mode_is_labeled_and_legacy_compatible():
    for advisor in (MomBirthdayGiftAdvisor(), FraudPreventionAdvisor(), HealthFatigueBreakerAdvisor()):
        advice = advisor.advise()
        assert advice.evidence_mode == EvidenceMode.PRIOR_SANDBOX
        assert advice.world_revision is None
        assert advice.token_estimate > 0
        assert AdviceQualityGuard.violations(advice) == []
        assert advice.action_items and advice.exclusions


def test_advisor_suite_audit_reports_token_and_pointer_budget(advice_world):
    store, _ = advice_world
    audit = AdvisorSuite(store).audit()
    assert audit["advisors"] == 3
    assert audit["evidence_pointers"] >= 15, "三条深链合计证据指针应充分"
    assert audit["token_estimate_total"] <= 3000, "三条深链总 Token 体积必须受控（含大量证据指针）"
    assert audit["modes"] == [EvidenceMode.WORLD_EVIDENCE.value]
