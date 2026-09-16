from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    ImageSemanticObservation,
    VoiceprintLifecycleManager,
    VoiceprintProfile,
)

NOW = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


def _profile(
    voiceprint_id: str,
    *,
    age_days: float,
    entity_id: str | None = None,
    is_tombstone: bool = False,
) -> VoiceprintProfile:
    last_contact = NOW - timedelta(days=age_days)
    return VoiceprintProfile(
        voiceprint_id=voiceprint_id,
        entity_id=entity_id,
        feature_hash=f"hash-{voiceprint_id}",
        first_detected_at=last_contact - timedelta(days=10),
        last_contact_at=last_contact,
        is_tombstone=is_tombstone,
    )


def test_edge_cleaner_discards_quality_below_point_four() -> None:
    cleaner = EdgeMultimodalCleaner()

    result = cleaner.evaluate_and_clean_image(
        {"quality_score": 0.399999},
        b"low-quality-frame",
    )

    assert result is None


def test_edge_cleaner_accepts_exact_threshold_and_never_retains_raw_bytes() -> None:
    cleaner = EdgeMultimodalCleaner(
        clock=lambda: NOW,
        id_factory=lambda: "obs_img_boundary",
    )
    raw = b"unique-binary-image-payload"

    result = cleaner.evaluate_and_clean_image(
        {
            "quality_score": 0.4,
            "caption": "散步",
            "tags": ["outdoor", "walking"],
        },
        raw,
    )

    assert result is not None
    assert result.observation_id == "obs_img_boundary"
    assert result.semantic_caption == "散步"
    assert result.scene_tags == ["outdoor", "walking"]
    assert result.raw_image_bytes_retained is False
    assert "raw_bytes" not in type(result).model_fields
    assert raw not in result.model_dump_json().encode()


def test_image_contract_cannot_be_constructed_with_retention_enabled() -> None:
    with pytest.raises(ValidationError, match="must never be retained"):
        ImageSemanticObservation(
            observation_id="obs_img_forbidden",
            quality_score=0.9,
            semantic_caption="书房阅读",
            raw_image_bytes_retained=True,
            captured_at=NOW,
        )


@pytest.mark.parametrize(
    "invalid_score",
    [float("nan"), float("inf"), float("-inf"), -0.01, 1.01, True, "bad"],
)
def test_edge_cleaner_rejects_invalid_quality_scores(invalid_score: object) -> None:
    cleaner = EdgeMultimodalCleaner()

    with pytest.raises(ValueError, match="quality_score"):
        cleaner.evaluate_and_clean_image(
            {"quality_score": invalid_score},
            b"frame",
        )


def test_edge_cleaner_generates_collision_resistant_ids() -> None:
    cleaner = EdgeMultimodalCleaner(clock=lambda: NOW)

    ids = {
        cleaner.evaluate_and_clean_image(
            {"quality_score": 0.8, "caption": "日常片段"},
            b"frame",
        ).observation_id
        for _ in range(100)
    }

    assert len(ids) == 100
    assert all(value.startswith("obs_img_") for value in ids)


def test_edge_cleaner_normalizes_tags_and_uses_aware_capture_time() -> None:
    cleaner = EdgeMultimodalCleaner(clock=lambda: NOW)

    result = cleaner.evaluate_and_clean_image(
        {
            "quality_score": "0.85",
            "semantic_caption": "  用户在书房阅读  ",
            "scene_tags": [" reading ", "indoors", "reading"],
        },
        b"frame",
    )

    assert result is not None
    assert result.semantic_caption == "用户在书房阅读"
    assert result.scene_tags == ["reading", "indoors"]
    assert result.captured_at == NOW
    assert result.captured_at.utcoffset() is not None


def test_edge_cleaner_zeroes_mutable_buffer_on_success() -> None:
    cleaner = EdgeMultimodalCleaner(clock=lambda: NOW)
    raw = bytearray(b"sensitive-camera-frame")

    result = cleaner.evaluate_and_clean_image(
        {"quality_score": 0.8, "caption": "室内"},
        raw,
    )

    assert result is not None
    assert raw == bytearray(len(raw))


def test_edge_cleaner_zeroes_mutable_buffer_on_discard_and_validation_error() -> None:
    cleaner = EdgeMultimodalCleaner()
    discarded = bytearray(b"discarded")
    invalid = bytearray(b"invalid")

    assert (
        cleaner.evaluate_and_clean_image(
            {"quality_score": 0.1},
            discarded,
        )
        is None
    )
    with pytest.raises(ValueError, match="quality_score"):
        cleaner.evaluate_and_clean_image(
            {"quality_score": "not-a-number"},
            invalid,
        )

    assert discarded == bytearray(len(discarded))
    assert invalid == bytearray(len(invalid))


def test_edge_cleaner_rejects_naive_capture_time() -> None:
    cleaner = EdgeMultimodalCleaner()

    with pytest.raises(ValidationError, match="captured_at must be timezone-aware"):
        cleaner.evaluate_and_clean_image(
            {
                "quality_score": 0.9,
                "caption": "场景",
                "captured_at": datetime(2026, 9, 16),  # noqa: DTZ001
            },
            b"frame",
        )


def test_voiceprint_sweep_tombstones_every_stale_unbound_profile() -> None:
    manager = VoiceprintLifecycleManager()
    profiles = [
        _profile(f"vp_{index:03d}", age_days=181 + index) for index in range(100)
    ]

    result = manager.sweep_stale_voiceprints(profiles, NOW)

    assert len(result) == 100
    assert all(profile.is_tombstone is True for profile in result)
    assert all(profile.is_tombstone is False for profile in profiles)


def test_voiceprint_sweep_uses_strict_over_180_day_boundary() -> None:
    manager = VoiceprintLifecycleManager()
    exact_boundary = _profile("vp_exact", age_days=180)
    just_over_boundary = _profile(
        "vp_over",
        age_days=180 + (1 / 86_400),
    )

    exact_result, over_result = manager.sweep_stale_voiceprints(
        [exact_boundary, just_over_boundary],
        NOW,
    )

    assert exact_result.is_tombstone is False
    assert over_result.is_tombstone is True


def test_voiceprint_sweep_never_tombstones_entity_bound_profile() -> None:
    manager = VoiceprintLifecycleManager()
    bound = _profile(
        "vp_known",
        age_days=1_000,
        entity_id="entity_alice",
    )

    result = manager.sweep_stale_voiceprints([bound], NOW)

    assert result == [bound]
    assert result[0].is_tombstone is False


def test_voiceprint_sweep_preserves_active_and_existing_tombstone_states() -> None:
    manager = VoiceprintLifecycleManager()
    active = _profile("vp_active", age_days=179)
    tombstoned = _profile(
        "vp_tombstoned",
        age_days=400,
        is_tombstone=True,
    )

    result = manager.sweep_stale_voiceprints(
        [active, tombstoned],
        NOW,
    )

    assert result[0].is_tombstone is False
    assert result[1].is_tombstone is True


def test_voiceprint_sweep_requires_timezone_aware_current_time() -> None:
    manager = VoiceprintLifecycleManager()

    with pytest.raises(ValueError, match="current_time must be timezone-aware"):
        manager.sweep_stale_voiceprints(
            [_profile("vp_one", age_days=181)],
            datetime(2026, 9, 16),  # noqa: DTZ001
        )


def test_voiceprint_profile_rejects_invalid_temporal_order() -> None:
    with pytest.raises(
        ValidationError,
        match="last_contact_at must not precede first_detected_at",
    ):
        VoiceprintProfile(
            voiceprint_id="vp_invalid",
            feature_hash="hash",
            first_detected_at=NOW,
            last_contact_at=NOW - timedelta(seconds=1),
        )


def test_voiceprint_profile_rejects_non_boolean_tombstone() -> None:
    with pytest.raises(ValidationError, match="is_tombstone must be a boolean"):
        VoiceprintProfile(
            voiceprint_id="vp_invalid_bool",
            feature_hash="hash",
            first_detected_at=NOW - timedelta(days=1),
            last_contact_at=NOW,
            is_tombstone="false",  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# as-built 审查（V3G-009 / V3G-010）补测
#
# 这两组断言不是"新功能测试"，而是把审查中发现的两个缺陷钉死：
#   V3G-009  RawByteSink 曾把"仅释放引用"（不可变 bytes）计入 purged_byte_count，
#            使隐私计量声称销毁了它并没有销毁的字节（探针门 E4）。
#   V3G-010  bind_nearest_entities 曾在每次比较里重复解析 32 字符十六进制串，
#            2,000×500 = 100 万次比较耗时 748.6 ms；把解析提到循环外后 123.2 ms（探针门 E9）。
# 另外补一条工单 §1.2"端侧 50ms 初筛"的**绑定规模档**断言（探针门 E5）。
# 证据：reviews/architecture/evidence/verify_landed_m1_001r_edge.py
# --------------------------------------------------------------------------- #

import time  # noqa: E402

from aios_core.ingest.multimodal_edge import (  # noqa: E402
    RawByteSink,
    VoiceprintLSHEngine,
)

_MASK_128 = (1 << 128) - 1


def _hex128(value: int) -> str:
    return f"{value & _MASK_128:032x}"


def test_raw_byte_sink_separates_zeroed_from_released_accounting() -> None:
    """V3G-009：擦除与释放引用必须分开计量，否则隐私计量会撒谎。"""
    sink = RawByteSink()

    writable = bytearray(b"\xAA" * 1_000)
    sink.purge(writable)
    assert writable == bytearray(1_000)          # 真的被擦成零
    assert sink.zeroed_frame_count == 1
    assert sink.zeroed_byte_count == 1_000
    assert sink.released_frame_count == 0        # 可写缓冲不算"仅释放"
    assert sink.released_byte_count == 0

    immutable = bytes(b"\xBB" * 1_000)
    sink.purge(immutable)
    # 不可变 bytes 在进程内**无法擦除**，只能丢引用 ⇒ 必须记在 released 一侧
    assert sink.zeroed_frame_count == 1
    assert sink.zeroed_byte_count == 1_000
    assert sink.released_frame_count == 1
    assert sink.released_byte_count == 1_000

    # purged_* 保持为总量（向后兼容），且恒等于两侧之和
    assert sink.purged_frame_count == sink.zeroed_frame_count + sink.released_frame_count
    assert sink.purged_byte_count == sink.zeroed_byte_count + sink.released_byte_count == 2_000
    # 无论哪条路径，本组件都不持有任何字节
    assert sink.retained_byte_count == 0


def test_raw_byte_sink_memoryview_accounting_follows_writability() -> None:
    """只读 memoryview 与 bytes 同属"不可擦除"；可写 memoryview 属"已擦除"。"""
    sink = RawByteSink()

    readonly = memoryview(b"\x11" * 64)
    sink.purge(readonly)
    assert sink.released_frame_count == 1
    assert sink.zeroed_frame_count == 0

    backing = bytearray(b"\x22" * 64)
    writable = memoryview(backing)
    sink.purge(writable)
    assert backing == bytearray(64)              # 透过 memoryview 擦到了底层存储
    assert sink.zeroed_frame_count == 1
    assert sink.released_frame_count == 1
    assert sink.purged_byte_count == 128


def test_cleaner_sink_accounting_tracks_frame_mutability() -> None:
    """走完整清洗路径时，计量必须反映调用方交进来的是可擦除帧还是不可擦除帧。"""
    sink = RawByteSink()
    cleaner = EdgeMultimodalCleaner(raw_byte_sink=sink)

    frame = bytearray(b"\xFF" * 4096)
    assert cleaner.evaluate_and_clean_image({"quality_score": 0.9}, frame) is not None
    assert frame == bytearray(4096)
    assert (sink.zeroed_byte_count, sink.released_byte_count) == (4096, 0)

    # 被判丢弃的帧同样要擦除，并同样计入 zeroed
    discarded = bytearray(b"\xEE" * 4096)
    assert cleaner.evaluate_and_clean_image({"quality_score": 0.1}, discarded) is None
    assert discarded == bytearray(4096)
    assert (sink.zeroed_byte_count, sink.released_byte_count) == (8192, 0)

    # 端侧若交进不可变 bytes，缺口必须**可见**（这就是 released_frame_count 存在的理由）
    assert cleaner.evaluate_and_clean_image({"quality_score": 0.9}, bytes(4096)) is not None
    assert sink.released_frame_count == 1
    assert sink.released_byte_count == 4096
    assert sink.zeroed_byte_count == 8192


def _naive_bind_reference(
    profiles: list[VoiceprintProfile],
    enrolled: dict[str, str],
    max_distance: int,
) -> list[tuple[str, str | None]]:
    """优化前的形状：每次比较都调用公开的 hamming_distance（重复解析十六进制）。

    用它作为**行为基准**——优化只允许改变耗时，不允许改变绑定结果。
    """
    out: list[tuple[str, str | None]] = []
    for profile in profiles:
        if profile.entity_id is not None or profile.is_tombstone or not enrolled:
            out.append((profile.voiceprint_id, profile.entity_id))
            continue
        ranked = sorted(
            (VoiceprintLSHEngine.hamming_distance(profile.feature_hash, h), eid)
            for eid, h in enrolled.items()
        )
        nearest_distance, nearest_id = ranked[0]
        unique = len(ranked) == 1 or ranked[1][0] != nearest_distance
        bound = nearest_distance <= max_distance and unique
        out.append((profile.voiceprint_id, nearest_id if bound else None))
    return out


def _vp(voiceprint_id: str, bits: int, **kwargs: object) -> VoiceprintProfile:
    return VoiceprintProfile(
        voiceprint_id=voiceprint_id,
        feature_hash=_hex128(bits),
        first_detected_at=NOW - timedelta(days=20),
        last_contact_at=NOW - timedelta(days=1),
        **kwargs,  # type: ignore[arg-type]
    )


def test_bind_nearest_entities_optimization_preserves_exact_behaviour() -> None:
    """V3G-010：把解析提到循环外之后，绑定结果必须与优化前**逐一相同**。

    覆盖五种判定分支：唯一最近且够近 ⇒ 绑定；并列最近 ⇒ 不绑定（fail-closed）；
    最近但太远 ⇒ 不绑定；已绑定 ⇒ 不动；已墓碑 ⇒ 不动。
    """
    far_a = sum(1 << i for i in range(60, 90))     # 30 位置 1
    far_b = sum(1 << i for i in range(20, 50))     # 另 30 位，与 far_a 距离 60
    enrolled = {
        "ent_a": _hex128(1 << 0),
        "ent_d": _hex128(1 << 1),
        "ent_far": _hex128(far_a),
    }
    profiles = [
        # 与 ent_d 完全相同（距 0），距 ent_a 2 位，距 ent_far 31 位 ⇒ 唯一最近 ⇒ 绑定
        _vp("p_unique", 1 << 1),
        # 距 ent_a 与 ent_d **都是 1 位** ⇒ 并列 ⇒ 宁可漏绑也不错绑
        _vp("p_tie", 0),
        # 距三个登记项分别 31 / 31 / 60 位 ⇒ 全部 > 16 ⇒ 不绑
        _vp("p_far", far_b),
        _vp("p_bound", 1 << 1, entity_id="ent_preexisting"),   # 已绑定 ⇒ 不动
        _vp("p_tomb", 1 << 1, is_tombstone=True),              # 已墓碑 ⇒ 不动
    ]

    bound = VoiceprintLSHEngine.bind_nearest_entities(
        profiles, enrolled_entity_hashes=enrolled, max_hamming_distance=16
    )
    assert [(p.voiceprint_id, p.entity_id) for p in bound] == _naive_bind_reference(
        profiles, enrolled, 16
    )
    by_id = {p.voiceprint_id: p.entity_id for p in bound}
    assert by_id["p_unique"] == "ent_d"      # 距 0，唯一最近
    assert by_id["p_tie"] is None            # 并列 ⇒ 宁可漏绑也不错绑
    assert by_id["p_far"] is None            # 最近也 > max_hamming_distance
    assert by_id["p_bound"] == "ent_preexisting"
    assert by_id["p_tomb"] is None
    # 输入不被就地改写
    assert [p.entity_id for p in profiles[3:]] == ["ent_preexisting", None]


def test_bind_nearest_entities_at_scale_matches_reference_and_stays_bounded() -> None:
    """规模档断言：300×200 = 6 万次比较，结果与基准一致，且耗时远在端侧预算内。"""
    enrolled = {f"ent_{e:04d}": _hex128((e * 7919) << (e % 90)) for e in range(200)}
    profiles = [_vp(f"p_{i:04d}", (i * 104729) << (i % 100)) for i in range(300)]

    start = time.perf_counter()
    bound = VoiceprintLSHEngine.bind_nearest_entities(
        profiles, enrolled_entity_hashes=enrolled, max_hamming_distance=24
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert [(p.voiceprint_id, p.entity_id) for p in bound] == _naive_bind_reference(
        profiles, enrolled, 24
    )
    # 工单未绑定规模档；这里按 as-built 探针 E9 的口径给一个**宽松**上界（实测 ~7 ms），
    # 阈值放到 250 ms 以便在慢 30 倍的机器上仍然稳定，同时仍能抓住 O(P×E) 解析回潮。
    assert elapsed_ms < 250.0, f"bind 退化：{elapsed_ms:.1f} ms"


@pytest.mark.parametrize(
    "bad_hash", ["", "abc", "0" * 31, "0" * 33, "z" * 32],
)
def test_bind_nearest_entities_rejects_malformed_enrollment_hash(bad_hash: str) -> None:
    """登记侧畸形哈希必须在**触碰任何 profile 之前**抛错（优化不许放松校验）。"""
    with pytest.raises(ValueError, match="LSH hash must"):
        VoiceprintLSHEngine.bind_nearest_entities(
            [_vp("p_good", 0b1010)], enrolled_entity_hashes={"ent_a": bad_hash}
        )


@pytest.mark.parametrize("bad_hash", ["abc", "0" * 31, "0" * 33, "z" * 32])
def test_bind_nearest_entities_rejects_malformed_profile_hash(bad_hash: str) -> None:
    """profile 侧畸形哈希同样抛错；空串则更早被模型层拦下（分层校验，两者都是 fail-closed）。"""
    with pytest.raises(ValueError, match="LSH hash must"):
        VoiceprintLSHEngine.bind_nearest_entities(
            [VoiceprintProfile(
                voiceprint_id="p_bad",
                feature_hash=bad_hash,
                first_detected_at=NOW - timedelta(days=5),
                last_contact_at=NOW,
            )],
            enrolled_entity_hashes={"ent_a": _hex128(1)},
        )


def test_bind_nearest_entities_empty_profile_hash_is_rejected_by_model_layer() -> None:
    """空串在 pydantic 层就被拦（min_length=1），到不了 LSH 校验——记录分层，别误判为漏检。"""
    with pytest.raises(ValidationError):
        VoiceprintProfile(
            voiceprint_id="p_bad",
            feature_hash="",
            first_detected_at=NOW - timedelta(days=5),
            last_contact_at=NOW,
        )


@pytest.mark.parametrize(
    "lenient_hash", ["0x" + "0" * 30, "1_" + "0" * 30],
)
def test_hash_validation_leniency_is_pinned_as_known_behaviour(lenient_hash: str) -> None:
    """**钉住既有宽松行为**（不是认可它）：`int(value, 16)` 接受 `0x` 前缀与下划线分隔符，
    所以 32 字符里含前缀/下划线的串会被当成合法 128 位哈希（实际有效位更少）。

    本测试的目的：任何收紧都必须是一次**显式**决定——收紧会让已入库的这类哈希失效，
    属于契约变更，需治理方裁决，不能在重构里顺手改掉。
    """
    assert len(lenient_hash) == 32
    distance = VoiceprintLSHEngine.hamming_distance(lenient_hash, _hex128(0))
    assert distance in (0, 1)


def test_hamming_distance_semantics_unchanged_after_parse_hoisting() -> None:
    """公开 API 的语义与错误信息必须逐字不变（重构不许改契约）。"""
    assert VoiceprintLSHEngine.hamming_distance(_hex128(0), _hex128(0)) == 0
    assert VoiceprintLSHEngine.hamming_distance(_hex128(1), _hex128(0)) == 1
    assert VoiceprintLSHEngine.hamming_distance(_hex128(0), _hex128(_MASK_128)) == 128
    with pytest.raises(ValueError, match="LSH hash must encode exactly 128 bits"):
        VoiceprintLSHEngine.hamming_distance("0" * 31, "0" * 32)
    with pytest.raises(ValueError, match="LSH hash must be hexadecimal"):
        VoiceprintLSHEngine.hamming_distance("z" * 32, "0" * 32)


def test_two_megabyte_frame_cleaning_stays_under_the_50ms_edge_budget() -> None:
    """工单 §1.2 的"端侧 50ms 初筛"——绑定规模档：2 MB 帧、含擦除、20 次取 p95。"""
    cleaner = EdgeMultimodalCleaner()
    frame = bytearray(2 * 1024 * 1024)
    samples: list[float] = []
    for index in range(20):
        frame[:] = b"\x5A" * len(frame)        # 每轮还原成非零，确保真的擦了
        start = time.perf_counter()
        result = cleaner.evaluate_and_clean_image(
            {"quality_score": 0.5 + (index % 50) / 100.0,
             "caption": f"场景 {index}", "tags": ["routine"]},
            frame,
        )
        samples.append((time.perf_counter() - start) * 1000.0)
        assert result is not None
        assert result.raw_image_bytes_retained is False

    p95 = sorted(samples)[int(0.95 * len(samples))]
    assert frame == bytearray(2 * 1024 * 1024)
    assert p95 < 50.0, f"单帧初筛 p95={p95:.3f} ms 超出工单 50 ms 预算"
