"""M1-001R 验收单测：机械画质门 / 绝不存图 / 声纹 180 天墓碑。"""

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.ingest.multimodal_edge import (
    QUALITY_DROP_THRESHOLD,
    EdgeMultimodalCleaner,
    ImageMetadata,
    InMemoryPurgeSink,
    VoiceprintLifecycleManager,
    VoiceprintProfile,
)

NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)


def meta(q: float, image_id: str = "img-1") -> ImageMetadata:
    return ImageMetadata(
        image_id=image_id,
        quality_score=q,
        captured_at=NOW,
        trigger="mechanical:impact",
    )


def test_quality_below_threshold_returns_none_and_purges_bytes():
    sink = InMemoryPurgeSink()
    cleaner = EdgeMultimodalCleaner(sink=sink)
    assert cleaner.evaluate_and_clean_image(meta(0.39), b"\x00blurry") is None
    assert sink.purged == ["img-1"]  # 丢弃同样物理删除，不落地


def test_quality_boundary_is_mechanical_not_llm():
    sink = InMemoryPurgeSink()
    cleaner = EdgeMultimodalCleaner(sink=sink)
    # 严格小于才丢：0.4 恰为合格线
    assert cleaner.evaluate_and_clean_image(meta(QUALITY_DROP_THRESHOLD - 1e-9), b"x") is None
    assert cleaner.evaluate_and_clean_image(meta(QUALITY_DROP_THRESHOLD), b"x") is not None


def test_observation_never_retains_raw_bytes():
    sink = InMemoryPurgeSink()
    cleaner = EdgeMultimodalCleaner(sink=sink)
    obs = cleaner.evaluate_and_clean_image(meta(0.9), b"RAW_SECRET_BYTES")
    assert obs is not None
    assert obs.raw_image_bytes_retained is False  # 严格为 False
    assert sink.purged == ["img-1"]
    dumped = obs.model_dump_json()
    assert "RAW_SECRET_BYTES" not in dumped  # 字节不得经任何字段泄漏
    assert obs.semantic_caption
    assert isinstance(obs.scene_tags, list)


def test_observation_model_cannot_carry_bytes_field():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # extra=forbid：想偷存原始字节字段直接被契约拒绝
        ImageMetadata(
            image_id="x", quality_score=0.9, captured_at=NOW,
            trigger="mechanical:key", raw_image_bytes=b"z",
        )


def test_semantic_trigger_must_be_mechanical():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ImageMetadata(image_id="x", quality_score=0.9, captured_at=NOW, trigger="semantic:party")


def test_stale_unbound_voiceprints_tombstoned_100_percent():
    mgr = VoiceprintLifecycleManager()
    profiles = [
        VoiceprintProfile(  # 超 180 天未绑定 → 必须墓碑
            voiceprint_id="vp-stale-1", feature_hash="h1",
            first_detected_at=NOW - timedelta(days=400),
            last_contact_at=NOW - timedelta(days=181),
        ),
        VoiceprintProfile(  # 一年+ 未绑定 → 必须墓碑
            voiceprint_id="vp-stale-2", feature_hash="h2",
            first_detected_at=NOW - timedelta(days=900),
            last_contact_at=NOW - timedelta(days=365),
        ),
        VoiceprintProfile(  # 恰 180 天（未"超过"）→ 不墓碑
            voiceprint_id="vp-exact", feature_hash="h3",
            first_detected_at=NOW - timedelta(days=200),
            last_contact_at=NOW - timedelta(days=180),
        ),
        VoiceprintProfile(  # 新鲜未绑定 → 不墓碑
            voiceprint_id="vp-fresh", feature_hash="h4",
            first_detected_at=NOW - timedelta(days=100),
            last_contact_at=NOW - timedelta(days=10),
        ),
        VoiceprintProfile(  # 已绑定实体，哪怕 400 天未出现 → 不归本规则管
            voiceprint_id="vp-bound", entity_id="entity:P001", feature_hash="h5",
            first_detected_at=NOW - timedelta(days=800),
            last_contact_at=NOW - timedelta(days=400),
        ),
    ]
    swept = mgr.sweep_stale_voiceprints(profiles, NOW)
    assert swept == ["vp-stale-1", "vp-stale-2"]
    by_id = {p.voiceprint_id: p for p in profiles}
    assert by_id["vp-stale-1"].is_tombstone is True
    assert by_id["vp-stale-2"].is_tombstone is True
    assert by_id["vp-exact"].is_tombstone is False
    assert by_id["vp-fresh"].is_tombstone is False
    assert by_id["vp-bound"].is_tombstone is False
    # 墓碑保留 feature_hash（销户留底，供回归重识别）
    assert by_id["vp-stale-1"].feature_hash == "h1"


def test_sweep_is_idempotent():
    mgr = VoiceprintLifecycleManager()
    p = VoiceprintProfile(
        voiceprint_id="vp-x", feature_hash="h",
        first_detected_at=NOW - timedelta(days=400),
        last_contact_at=NOW - timedelta(days=200),
    )
    assert mgr.sweep_stale_voiceprints([p], NOW) == ["vp-x"]
    assert mgr.sweep_stale_voiceprints([p], NOW) == []  # 二次 sweep 不重复打碑
