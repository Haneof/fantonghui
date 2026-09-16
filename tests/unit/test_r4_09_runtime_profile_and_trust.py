"""M0-030（R4-09.3）runtime_profile 双配置契约 + R4-09.1 Claim 信任字段。

候选冻结批测试：契约语义本身；band_v0 一日回放冒烟自 M2 起为里程碑出口
强制项（设计书 T6），不在本文件职责内。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    DEFAULT_BAND_V0,
    DEFAULT_VIRTUAL,
    Claim,
    ClaimType,
    IngestPolicy,
    KnowledgeState,
    LatencyPolicy,
    ProfileName,
    RuntimeProfile,
    StoragePolicy,
    TemporalExtent,
    new_object_id,
    resolve_runtime_profile,
)
from aios_core.contracts.time import utc_now


def make_claim(**kw):
    now = utc_now()
    base = dict(
        object_id=new_object_id("claim"), subject_id="u1", revision=1,
        occurred=TemporalExtent.point(now), learned_at=now, recorded_at=now,
        created_by="r4-09-tests", claimant_id="peer_x",
        claim_type=ClaimType.OPINION, content="同事转述：下周团建改期",
        asserted_at=now, knowledge_state=KnowledgeState.REPORTED, confidence=0.6,
    )
    base.update(kw)
    return Claim(**base)


# ---------------------------------------------------------- R4-09.1 信任字段


def test_trust_fields_default_and_range():
    c = make_claim()
    assert c.source_trust == 1.0 and c.corroboration_required is False
    assert c.may_drive_external_action is True
    with pytest.raises(ValidationError):
        make_claim(source_trust=1.01)


def test_corroboration_required_blocks_fact_promotion():
    with pytest.raises(ValidationError, match="FACT"):
        make_claim(corroboration_required=True, claim_type=ClaimType.FACT, confidence=0.95)


def test_corroboration_required_gates_external_action():
    c = make_claim(corroboration_required=True, source_trust=0.3)
    assert c.may_drive_external_action is False
    # 入候选认知的权利不受影响（第 19.1 条限定：记录权利平等）
    assert c.knowledge_state is KnowledgeState.REPORTED


# ---------------------------------------------------------- M0-030 profiles


def test_resolve_returns_frozen_defaults():
    assert resolve_runtime_profile("virtual") is DEFAULT_VIRTUAL
    assert resolve_runtime_profile("band_v0") is DEFAULT_BAND_V0
    with pytest.raises(ValueError, match="未知 runtime_profile"):
        resolve_runtime_profile("watch_v1")


def test_constitution_hard_lines_apply_to_both_profiles():
    for name in ("virtual", "band_v0"):
        with pytest.raises(ValidationError, match="33.5"):
            RuntimeProfile(name=name, storage=StoragePolicy(pruned_tombstone=False))
        with pytest.raises(ValidationError, match="raw_stream|第 33 条"):
            RuntimeProfile(name=name, ingest=IngestPolicy(imu_mode="raw_stream"))
        with pytest.raises(ValidationError, match="大图|第 33 条"):
            RuntimeProfile(name=name, ingest=IngestPolicy(images_mode="thumbnail_meta"))
        with pytest.raises(ValidationError, match="丢帧"):
            RuntimeProfile(name=name, ingest=IngestPolicy(frame_drop_must_record=False))


def test_band_v0_must_be_at_least_as_strict_numberwise():
    base = DEFAULT_BAND_V0.model_dump()
    loosened = {**base, "latency": {**base["latency"], "recall_sync_budget_ms": 80}}
    with pytest.raises(ValidationError, match="只可更严"):
        RuntimeProfile.model_validate(loosened)
    loosened2 = {**base, "storage": {**base["storage"], "raw_tier_days": 90}}
    with pytest.raises(ValidationError, match="只可更严"):
        RuntimeProfile.model_validate(loosened2)


def test_band_v0_required_knobs():
    base = DEFAULT_BAND_V0.model_dump()
    for section, key in [("ingest", "compute_budget_us_per_ingest"),
                         ("storage", "ring_buffer_hours"),
                         ("storage", "max_commits_per_hour"),
                         ("latency", "tts_max_sec_per_turn")]:
        bad = {**base, section: {**base[section], key: None}}
        with pytest.raises(ValidationError):
            RuntimeProfile.model_validate(bad)
    tight = {**base, "ingest": {**base["ingest"], "image_queue_depth": 4}}
    with pytest.raises(ValidationError, match="深度上限 3"):
        RuntimeProfile.model_validate(tight)


def test_extra_knobs_forbidden_and_serialization_roundtrip():
    with pytest.raises(ValidationError):
        LatencyPolicy(first_token_budget_ms=900, wake_frequency_hz=7)  # 夹带新旋钮=改代码路径
    dumped = DEFAULT_BAND_V0.model_dump(mode="json")
    assert RuntimeProfile.model_validate(dumped) == DEFAULT_BAND_V0  # 确定性：可进 CI fixture


def test_defaults_match_design_book_numbers():
    assert DEFAULT_VIRTUAL.latency.first_token_budget_ms == 1000  # R4-01
    assert DEFAULT_VIRTUAL.latency.recall_sync_budget_ms == 50    # T2/G-M1P
    assert DEFAULT_VIRTUAL.storage.raw_tier_days == 30             # M1-019 施工图引用
    assert DEFAULT_BAND_V0.storage.ring_buffer_hours == 48
    assert DEFAULT_BAND_V0.ingest.image_queue_depth == 3
    assert DEFAULT_BAND_V0.latency.tts_max_sec_per_turn == 20
    assert {p.name for p in (DEFAULT_VIRTUAL, DEFAULT_BAND_V0)} == set(ProfileName)
