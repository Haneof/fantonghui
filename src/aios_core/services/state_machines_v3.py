"""V3.0.1 extension lifecycle machines (freeze-line: CONST-V3.0.1 / M0').

Frozen transition matrices for the objects introduced by the M0' patch.
Terminal states are terminal forever; lifecycle writes flow through revision,
never through in-place edits.
"""

from __future__ import annotations

from aios_core.contracts.enums_v3 import (
    EpochState,
    LifeChapterStatus,
    PredictionStatus,
    SpeakerClusterStatus,
    TombstoneStage,
)

_PREDICTION_TRANSITIONS: dict[PredictionStatus, frozenset[PredictionStatus]] = {
    PredictionStatus.PENDING: frozenset(
        {
            PredictionStatus.SUPPORTED,
            PredictionStatus.FALSIFIED,
            PredictionStatus.INCONCLUSIVE,
            PredictionStatus.EXPIRED,
        }
    ),
    PredictionStatus.SUPPORTED: frozenset(),
    PredictionStatus.FALSIFIED: frozenset(),
    # 缺测终态允许复议重开（迟到的现实观测到达时），回到 PENDING 重新排窗
    PredictionStatus.INCONCLUSIVE: frozenset({PredictionStatus.PENDING}),
    PredictionStatus.EXPIRED: frozenset(),
}

_CHAPTER_TRANSITIONS: dict[LifeChapterStatus, frozenset[LifeChapterStatus]] = {
    LifeChapterStatus.CANDIDATE: frozenset(
        {
            LifeChapterStatus.ACTIVE,
            LifeChapterStatus.REJECTED,
        }
    ),
    LifeChapterStatus.ACTIVE: frozenset(
        {
            LifeChapterStatus.ARCHIVED,
            LifeChapterStatus.REVISED,
        }
    ),
    LifeChapterStatus.ARCHIVED: frozenset({LifeChapterStatus.REVISED}),
    # 误判修正链：REVISED 指向修正版；REVISED 本身终态，修正版是新 revision
    LifeChapterStatus.REVISED: frozenset(),
    LifeChapterStatus.REJECTED: frozenset(),
}

_EPOCH_TRANSITIONS: dict[EpochState, frozenset[EpochState]] = {
    EpochState.DRAFT: frozenset({EpochState.MARKING}),
    EpochState.MARKING: frozenset(
        {
            EpochState.BUDGETED_REVIEW,
            EpochState.CONTINUATION,
            EpochState.QUARANTINED_PARTIAL,
            EpochState.DONE,
        }
    ),
    EpochState.BUDGETED_REVIEW: frozenset(
        {
            EpochState.CONTINUATION,
            EpochState.QUARANTINED_PARTIAL,
            EpochState.DONE,
        }
    ),
    EpochState.CONTINUATION: frozenset(
        {
            EpochState.BUDGETED_REVIEW,
            EpochState.QUARANTINED_PARTIAL,
            EpochState.DONE,
        }
    ),
    EpochState.QUARANTINED_PARTIAL: frozenset(
        {
            EpochState.BUDGETED_REVIEW,
            EpochState.CONTINUATION,
            EpochState.DONE,
        }
    ),
    EpochState.DONE: frozenset(),
}

_CLUSTER_TRANSITIONS: dict[SpeakerClusterStatus, frozenset[SpeakerClusterStatus]] = {
    SpeakerClusterStatus.ACTIVE: frozenset({SpeakerClusterStatus.RETIRED}),
    # ADJ-009：退休不可逆——再识别不重开簇，只在实体层建立关联
    SpeakerClusterStatus.RETIRED: frozenset({SpeakerClusterStatus.TOMBSTONE}),
    SpeakerClusterStatus.TOMBSTONE: frozenset(),
}

_TOMBSTONE_TRANSITIONS: dict[TombstoneStage, frozenset[TombstoneStage]] = {
    TombstoneStage.STAGE1_SOFT: frozenset({TombstoneStage.STAGE2_SHREDDED}),
    TombstoneStage.STAGE2_SHREDDED: frozenset(),
}


def allowed_prediction_transitions(
    state: PredictionStatus,
) -> frozenset[PredictionStatus]:
    return _PREDICTION_TRANSITIONS[state]


def allowed_chapter_transitions(
    state: LifeChapterStatus,
) -> frozenset[LifeChapterStatus]:
    return _CHAPTER_TRANSITIONS[state]


def allowed_epoch_transitions(state: EpochState) -> frozenset[EpochState]:
    return _EPOCH_TRANSITIONS[state]


def allowed_cluster_transitions(
    state: SpeakerClusterStatus,
) -> frozenset[SpeakerClusterStatus]:
    return _CLUSTER_TRANSITIONS[state]


def allowed_tombstone_transitions(state: TombstoneStage) -> frozenset[TombstoneStage]:
    return _TOMBSTONE_TRANSITIONS[state]
