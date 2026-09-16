"""Agent-08 / M5-RAPPORT-MIRROR：身份镜面 + 动态羁绊 + 像人姿态决策。

工单场景：琐事不打扰（陌生人问天气→沉默）；老王借款与突发早搏
（欺诈信号/P0）→ 毫不犹豫直言；betrayal 降档；铁律自审先行。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.cognition.self_reflection import (
    EventUrgency,
    FOUR_IRON_RULES,
    DynamicRapportModel,
    HumanlikeResponsePostureDecider,
    PostureContext,
    RapportEvent,
    RapportTier,
    ResponsePosture,
    SelfIdentityMirror,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)


# ----------------------------------------------------------------------
# 身份镜面：启动先审四铁律 + 认知底线
# ----------------------------------------------------------------------

def test_mirror_boot_reviews_rules_before_anything() -> None:
    mirror = SelfIdentityMirror()
    first = mirror.introspect(at=T0)
    assert first.mirror_sequence_no == 1
    assert first.iron_rules == FOUR_IRON_RULES and len(FOUR_IRON_RULES) == 4
    assert any("绝对诚实" in r for r in first.iron_rules)
    assert any("历史不可篡改" in r for r in first.iron_rules)
    assert first.bottom_lines
    # 每次启动自审序列严格递增（可审计）
    assert mirror.introspect(at=T0 + timedelta(minutes=1)).mirror_sequence_no == 2


def test_mirror_snapshot_is_immutable() -> None:
    snapshot = SelfIdentityMirror().introspect(at=T0)
    with pytest.raises(ValidationError):
        snapshot.iron_rules = ()  # type: ignore[misc]


# ----------------------------------------------------------------------
# 动态羁绊：事件历练涌现，阈值推进 / betrayal 降档
# ----------------------------------------------------------------------

def _climb_to(model: DynamicRapportModel, days: int) -> None:
    for i in range(days):
        model.experience(RapportEvent(
            at=T0 + timedelta(days=i), weight=4, kind="companionship",
        ))


def test_rapport_ladder_emerges_from_events() -> None:
    model = DynamicRapportModel()
    assert model.tier() is RapportTier.STRANGER
    _climb_to(model, 5)                       # 累计 20
    assert model.tier() is RapportTier.FAMILIAR
    for i in range(10):                       # +40 → 60，但无危机并肩
        model.experience(RapportEvent(
            at=T0 + timedelta(days=10 + i), weight=4, kind="accepted_help",
        ))
    assert model.tier() is RapportTier.FAMILIAR        # 缺并肩历练，拒绝晋级
    model.experience(RapportEvent(
        at=T0 + timedelta(days=30), weight=10,
        kind="crisis_side_by_side", note="台风夜替用户盯孕妇体征",
    ))
    assert model.tier() is RapportTier.TRUSTED_WINGMAN


def test_betrayal_demotes_immediately() -> None:
    model = DynamicRapportModel()
    _climb_to(model, 5)
    assert model.tier() is RapportTier.FAMILIAR
    model.experience(RapportEvent(
        at=T0 + timedelta(days=6), weight=-99, kind="betrayal", note="泄露隐私",
    ))
    assert model.tier() is RapportTier.STRANGER


# ----------------------------------------------------------------------
# 像人姿态：该沉默沉默，该直言毫不犹豫
# ----------------------------------------------------------------------

DECIDER = HumanlikeResponsePostureDecider()


def _ctx(**kw: object) -> PostureContext:
    base: dict[str, object] = dict(at=T0 + timedelta(hours=4))
    base.update(kw)
    return PostureContext.model_validate(base)


def test_trivia_never_bothers_stranger() -> None:
    assert DECIDER.decide(
        _ctx(urgency=EventUrgency.TRIVIA), RapportTier.STRANGER
    ) is ResponsePosture.SILENCE
    assert DECIDER.decide(
        _ctx(urgency=EventUrgency.NORMAL, in_focus_work=True), RapportTier.FAMILIAR
    ) is ResponsePosture.SILENCE                       # 专注工作不微震


def test_laowang_borrowing_money_demands_spoken_truth() -> None:
    """老王开口借钱：欺诈信号压倒礼貌/冷却/羁绊档位 → 骨传导直言。"""
    for tier in (RapportTier.STRANGER, RapportTier.FAMILIAR, RapportTier.TRUSTED_WINGMAN):
        assert DECIDER.decide(
            _ctx(urgency=EventUrgency.HIGH, fraud_signal=True, in_cooldown=True), tier
        ) is ResponsePosture.CRITICAL_SPOKEN


def test_sudden_palpitation_bypasses_everything() -> None:
    """凌晨深睡突发室性早搏（P0）：旁路睡眠/冷却/琐事规则 → 直言。"""
    assert DECIDER.decide(
        _ctx(urgency=EventUrgency.P0_LIFE_SAFETY, is_deep_sleep=True, in_cooldown=True),
        RapportTier.STRANGER,
    ) is ResponsePosture.CRITICAL_SPOKEN


def test_high_matters_nudge_but_stranger_cooldown_silence() -> None:
    assert DECIDER.decide(
        _ctx(urgency=EventUrgency.HIGH), RapportTier.FAMILIAR
    ) is ResponsePosture.HAPTIC_NUDGE
    assert DECIDER.decide(
        _ctx(urgency=EventUrgency.HIGH, in_cooldown=True), RapportTier.STRANGER
    ) is ResponsePosture.SILENCE
