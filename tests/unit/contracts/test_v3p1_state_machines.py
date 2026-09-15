"""Frozen transition matrix tests for V3.0.1 extension lifecycles."""

from __future__ import annotations

import pytest

from aios_core.contracts.enums_v3 import (
    EpochState,
    LifeChapterStatus,
    PredictionStatus,
    SpeakerClusterStatus,
    TombstoneStage,
)
from aios_core.services.state_machines_v3 import (
    allowed_chapter_transitions,
    allowed_cluster_transitions,
    allowed_epoch_transitions,
    allowed_prediction_transitions,
    allowed_tombstone_transitions,
)


def test_prediction_terminal_states_are_closed_except_inconclusive():
    assert allowed_prediction_transitions(PredictionStatus.SUPPORTED) == frozenset()
    assert allowed_prediction_transitions(PredictionStatus.FALSIFIED) == frozenset()
    assert allowed_prediction_transitions(PredictionStatus.EXPIRED) == frozenset()
    # 缺测终态：迟到观测允许复议重开，回到 PENDING 重排窗口
    assert allowed_prediction_transitions(
        PredictionStatus.INCONCLUSIVE
    ) == frozenset({PredictionStatus.PENDING})


def test_prediction_pending_can_reach_all_terminal_states():
    assert allowed_prediction_transitions(PredictionStatus.PENDING) == frozenset(
        {
            PredictionStatus.SUPPORTED,
            PredictionStatus.FALSIFIED,
            PredictionStatus.INCONCLUSIVE,
            PredictionStatus.EXPIRED,
        }
    )


def test_chapter_revised_is_terminal_and_active_can_only_archive_or_revise():
    assert allowed_chapter_transitions(LifeChapterStatus.REVISED) == frozenset()
    assert allowed_chapter_transitions(LifeChapterStatus.REJECTED) == frozenset()
    assert allowed_chapter_transitions(LifeChapterStatus.ACTIVE) == frozenset(
        {LifeChapterStatus.ARCHIVED, LifeChapterStatus.REVISED}
    )


def test_cluster_never_resurrects():
    # ADJ-009：RETIRED 只能走向 TOMBSTONE，绝不回 ACTIVE
    assert allowed_cluster_transitions(SpeakerClusterStatus.ACTIVE) == frozenset(
        {SpeakerClusterStatus.RETIRED}
    )
    assert allowed_cluster_transitions(SpeakerClusterStatus.RETIRED) == frozenset(
        {SpeakerClusterStatus.TOMBSTONE}
    )
    assert allowed_cluster_transitions(SpeakerClusterStatus.TOMBSTONE) == frozenset()


def test_tombstone_is_append_only():
    assert allowed_tombstone_transitions(TombstoneStage.STAGE1_SOFT) == frozenset(
        {TombstoneStage.STAGE2_SHREDDED}
    )
    assert allowed_tombstone_transitions(TombstoneStage.STAGE2_SHREDDED) == frozenset()


def test_epoch_flow_covers_quarantine_and_continuation():
    marking = allowed_epoch_transitions(EpochState.MARKING)
    assert EpochState.QUARANTINED_PARTIAL in marking
    assert EpochState.CONTINUATION in marking
    assert EpochState.BUDGETED_REVIEW in marking
    assert EpochState.DONE in marking
    # 隔离区不是终态——解封后可续办
    assert EpochState.DRAFT not in allowed_epoch_transitions(
        EpochState.QUARANTINED_PARTIAL
    )
    assert allowed_epoch_transitions(EpochState.DONE) == frozenset()
