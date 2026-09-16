"""Agent-09 / M5-SYMBIOTIC-ADVISOR：共生顾问三人组。

工单红线：所有 ActionableAdvice 必带确凿 ObjectRef 因果指针、
严禁编造（缺证据必须 MissingEvidenceError）、严禁泛泛套话
（黑名单正则命中即 ValidationError）。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aios_core.cognition.symbiotic_advisor import (
    ActionableAdvice,
    EvidenceRecord,
    FraudPreventionAdvisor,
    HealthFatigueBreakerAdvisor,
    MissingEvidenceError,
    MindEvidenceStore,
    MomBirthdayGiftAdvisor,
)

UTC = timezone.utc


def _gift_store() -> MindEvidenceStore:
    store = MindEvidenceStore()
    store.add_all((
        EvidenceRecord(
            object_id="obs_gift_2023_silk", revision=1, kind="gift", year=2023,
            keywords=("丝巾", "母亲节"), content="2023 年送真丝方巾，母亲收下但只出门戴过一次。",
        ),
        EvidenceRecord(
            object_id="obs_gift_2024_tub", revision=1, kind="gift", year=2024,
            keywords=("足浴盆", "母亲节"), content="2024 年送足浴盆，三个月后闲置在阳台角落。",
        ),
        EvidenceRecord(
            object_id="obs_health_2024_waist", revision=2, kind="health_signal", year=2024,
            keywords=("倒水", "腰疼"), content="母亲倒 4L 足浴盆水后腰疼两天，拒绝再自己操作。",
        ),
        EvidenceRecord(
            object_id="obs_gift_2025_chair", revision=1, kind="gift_feedback", year=2025,
            keywords=("按摩椅", "好评"), content="2025 年送按摩椅，母亲主动说每天热敷模式很舒服。",
        ),
        EvidenceRecord(
            object_id="obs_health_2026_knee", revision=1, kind="health_signal", year=2026,
            keywords=("膝盖", "受凉"), content="2026 年清明电话里说膝盖受凉就酸胀。",
        ),
    ))
    return store


# ----------------------------------------------------------------------
# 送礼推演：四年证据链 → 轻便膝盖热敷仪
# ----------------------------------------------------------------------

def test_gift_advisor_converges_on_knee_heating_pad() -> None:
    advice = MomBirthdayGiftAdvisor().advise(_gift_store(), at=datetime(2026, 4, 20, tzinfo=UTC))
    assert "膝盖热敷仪" in advice.headline
    assert "轻便" in advice.headline or "轻量" in advice.headline
    # 四年证据链全部 pin 为 ObjectRef（2024 腰疼记录 revision=2 必须保留）
    refs = {r.object_id: r.revision for r in advice.evidence_refs}
    assert refs["obs_health_2024_waist"] == 2
    assert len(refs) >= 5
    assert any("石墨烯" in a or "≤500g" in a for a in advice.actions)  # 可执行非套话


def test_gift_advisor_refuses_to_fabricate_when_chain_broken() -> None:
    store = _gift_store()
    empty = MindEvidenceStore()
    with pytest.raises(MissingEvidenceError) as excinfo:
        MomBirthdayGiftAdvisor().advise(empty, at=datetime(2026, 4, 20, tzinfo=UTC))
    assert "health:2026膝盖受凉" in excinfo.value.missing
    # 抽掉 2024 腰疼证据 → 该环节缺失，整链拒绝出主意
    partial = MindEvidenceStore()
    partial.add_all(r for r in store.find() if r.object_id != "obs_health_2024_waist")
    with pytest.raises(MissingEvidenceError) as excinfo2:
        MomBirthdayGiftAdvisor().advise(partial, at=datetime(2026, 4, 20, tzinfo=UTC))
    assert "gift:2024足浴盆+倒水腰疼" in excinfo2.value.missing


# ----------------------------------------------------------------------
# 反诈阻击：法院判决 + 两年前微信借款 → 拒借 + 追偿指针
# ----------------------------------------------------------------------

def _fraud_store() -> MindEvidenceStore:
    store = MindEvidenceStore()
    store.add_all((
        EvidenceRecord(
            object_id="obs_court_judgment_2024", revision=1, kind="court",
            keywords=("判决", "担保"), content="2024 年法院判决书认定其关联担保欺诈，判令返还。",
        ),
        EvidenceRecord(
            object_id="obs_wechat_loan_2024", revision=3, kind="loan_record", year=2024,
            keywords=("借款", "微信"),
            content="2024 年微信转账借出 6 万元，备注『周转』，至今无归还记录。",
        ),
    ))
    return store


def test_fraud_advisor_refuses_loan_with_legal_pointer() -> None:
    advice = FraudPreventionAdvisor().advise(_fraud_store(), at=datetime(2026, 5, 1, tzinfo=UTC))
    assert advice.urgency == "high"
    assert "拒绝" in advice.headline
    assert any("支付令" in a or "诉讼" in a for a in advice.actions)  # 法律追偿指针
    refs = {r.object_id: r.revision for r in advice.evidence_refs}
    assert refs["obs_wechat_loan_2024"] == 3   # 借款记录 revision pin


def test_fraud_advisor_requires_both_evidence_legs() -> None:
    half = MindEvidenceStore()
    half.add(EvidenceRecord(
        object_id="obs_court_judgment_2024", revision=1, kind="court",
        keywords=("判决", "担保"), content="2024 年法院判决书认定其关联担保欺诈，判令返还。",
    ))
    with pytest.raises(MissingEvidenceError) as excinfo:
        FraudPreventionAdvisor().advise(half, at=datetime(2026, 5, 1, tzinfo=UTC))
    assert "loan_record:2024年微信借款" in excinfo.value.missing


# ----------------------------------------------------------------------
# 疲劳熔断：通宵 × 室性早搏 → 强制停工（p0）
# ----------------------------------------------------------------------

def _breaker_store() -> MindEvidenceStore:
    store = MindEvidenceStore()
    store.add_all((
        EvidenceRecord(
            object_id="obs_work_overnight_mon", revision=1, kind="work_pattern",
            keywords=("通宵", "加班"), content="周一通宵改融资材料至 06:40。",
        ),
        EvidenceRecord(
            object_id="obs_work_overnight_wed", revision=1, kind="work_pattern",
            keywords=("通宵", "加班"), content="周三再次通宵部署发布至 05:20。",
        ),
        EvidenceRecord(
            object_id="obs_health_pvc_thu", revision=2, kind="health_signal",
            keywords=("室性早搏",), content="周四心电带复测室性早搏 412 次/24h，伴心悸。",
        ),
    ))
    return store


def test_breaker_forces_shutdown_on_overnight_pvc_causality() -> None:
    advice = HealthFatigueBreakerAdvisor().advise(_breaker_store(), at=datetime(2026, 5, 14, 23, 30, tzinfo=UTC))
    assert advice.urgency == "p0"
    assert "停工" in advice.headline
    assert any("零点前入睡" in a or "入睡" in a for a in advice.actions)
    refs = {r.object_id for r in advice.evidence_refs}
    assert {"obs_work_overnight_mon", "obs_work_overnight_wed", "obs_health_pvc_thu"} <= refs


def test_breaker_refuses_without_health_signal() -> None:
    store = MindEvidenceStore()
    store.add_all((
        EvidenceRecord(
            object_id="obs_work_overnight_mon", revision=1, kind="work_pattern",
            keywords=("通宵", "加班"), content="周一通宵改融资材料至 06:40。",
        ),
        EvidenceRecord(
            object_id="obs_work_overnight_wed", revision=1, kind="work_pattern",
            keywords=("通宵", "加班"), content="周三再次通宵部署发布至 05:20。",
        ),
    ))
    with pytest.raises(MissingEvidenceError):
        HealthFatigueBreakerAdvisor().advise(store, at=datetime(2026, 5, 14, 23, 30, tzinfo=UTC))


# ----------------------------------------------------------------------
# 套话黑名单：模板鸡汤在契约层直接 ValidationError
# ----------------------------------------------------------------------

@pytest.mark.parametrize("bad_text,field", [
    ("保持良好心态最重要", "headline"),
    ("为您推荐以下三点", "headline"),
    ("希望这些建议对您有帮助", "rationale"),
    ("具体情况请咨询专业人士", "rationale"),
])
def test_boilerplate_platitudes_are_contractually_forbidden(bad_text: str, field: str) -> None:
    fields: dict[str, object] = dict(
        advice_id="adv_boiler_test", advisor="test", urgency="routine",
        confidence=0.5, created_at=datetime(2026, 5, 1, tzinfo=UTC),
        evidence_refs=(EvidenceRecord(
            object_id="obs_any", revision=1, kind="x", content="证据内容",
        ).ref(),),
        headline="今晚停工静养，明早复测心率", rationale="通宵后早搏负荷上升，因果有据。",
        actions=("行动一",),
    )
    fields[field] = bad_text
    with pytest.raises(ValidationError, match="boilerplate"):
        ActionableAdvice.model_validate(fields)
