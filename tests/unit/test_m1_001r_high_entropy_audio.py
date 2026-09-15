"""M1-001R-ADV 高熵工业/商务场景多模态边缘摄入 —— 压测单测。

实战场景：佩戴者连续穿梭于重型工业装配车间（85dB 持续机械低频噪音）
与跨国供应链 24 人商务圆桌晚宴（中英文与方言交叉重叠混杂），并在现场
持续抓拍设备标牌与合同文本。

三大硬门禁：
1. 画质 < 0.4 的 500 张垃圾图片在 5ms 内物理删除（RawByteSink.purge），
   主存储与内存中原始字节保留量严格为 0；
2. 24 声源同流切片 → 128 维 SimHash-LSH 声纹聚类；核心商务伙伴与
   穿梭的服务员/路人零混淆；
3. 360 天时间轴模拟：15 个未绑定实体的背景人声声纹，最后接触满 180
   天的瞬间 is_tombstone 严格置 True，并从活跃热表剥离至归档区。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.ingest import (
    CAPTURE_PURGE_THRESHOLD,
    LSH_BANDS,
    TTL_DAYS,
    VOICEPRINT_DIM,
    CaptureFrame,
    RawByteSink,
    VoiceprintLSHEngine,
    VoiceprintTTLRegistry,
    assess_capture_quality,
)

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 18, 30, 0, tzinfo=UTC)  # 晚宴入场

# ======================================================================
# 门禁一：画质退化亚毫秒粉碎
# ======================================================================

def _frame(frame_id: str, quality, at) -> CaptureFrame:
    return CaptureFrame(
        frame_id=frame_id,
        quality=quality,
        brightness=quality,
        sharpness=min(1.0, quality + 0.05),
        jitter=max(0.0, 1.0 - quality),
        scene_tag="banquet_hall",
        captured_at=at,
    )


def test_gate1_purge_500_garbage_frames_within_5ms_zero_byte_retention() -> None:
    import time

    sink = RawByteSink()
    rng = random.Random(85)
    garbage_ids: list[str] = []
    keeper_ids: list[str] = []
    for i in range(1000):
        if i % 2 == 0:
            # 昏暗 + 走动抖动：画质 < 0.4（合同文本/标牌抓拍失败的废片）
            quality = assess_capture_quality(
                brightness=rng.uniform(0.05, 0.25),
                sharpness=rng.uniform(0.10, 0.30),
                jitter=rng.uniform(0.70, 0.98),
            )
            frame = _frame(f"cam_garbage_{i:04d}", quality, T0 + timedelta(seconds=i))
            assert frame.quality < CAPTURE_PURGE_THRESHOLD
            garbage_ids.append(frame.frame_id)
        else:
            # 现场有效抓拍：设备标牌/合同文本（可语义化入库）
            quality = assess_capture_quality(
                brightness=rng.uniform(0.55, 0.80),
                sharpness=rng.uniform(0.75, 0.95),
                jitter=rng.uniform(0.02, 0.15),
            )
            frame = _frame(f"cam_keeper_{i:04d}", quality, T0 + timedelta(seconds=i))
            assert frame.quality >= CAPTURE_PURGE_THRESHOLD
            keeper_ids.append(frame.frame_id)
        sink.store(frame, bytes(rng.randbytes(2048)))

    assert len(garbage_ids) == 500 and len(keeper_ids) == 500

    started = time.perf_counter()
    report = sink.purge()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert report.purged_count == 500
    assert set(report.purged_ids) == set(garbage_ids)
    assert report.retained_count == 500
    assert elapsed_ms <= 5.0, f"purge took {elapsed_ms}ms > 5ms budget"
    assert report.elapsed_ms <= 5.0
    # 主存储与内存中原始字节保留量严格为 0（物理删除，无软删除副本）
    assert report.raw_bytes_retained_for_purged == 0
    assert all(sink.raw_size_of(fid) == 0 for fid in garbage_ids)
    assert all(sink.raw_size_of(fid) is not None for fid in garbage_ids)
    assert sink.live_frame_count == 500  # 仅剩有效抓拍
    assert all(
        sink.raw_size_of(fid) == 2048 for fid in keeper_ids
    )
    # 删除仅留审计记录（谁/何时/为何/多少字节）
    assert len(sink.audit_trail) == 500
    assert all(r.reason == "LOW_QUALITY_GARBAGE" for r in sink.audit_trail)
    assert sum(r.bytes_freed for r in sink.audit_trail) == 500 * 2048
    # 二次 purge 幂等：不再产生新删除
    second = sink.purge()
    assert second.purged_count == 0


def test_gate1_quality_formula_is_mechanical_and_bounded() -> None:
    assert assess_capture_quality(brightness=0, sharpness=0, jitter=1) == 0.0
    assert assess_capture_quality(brightness=1, sharpness=1, jitter=0) == 1.0
    # 抖动是反向权重：同亮度清晰度下，抖动越高画质越低
    calm = assess_capture_quality(brightness=0.6, sharpness=0.7, jitter=0.1)
    shaken = assess_capture_quality(brightness=0.6, sharpness=0.7, jitter=0.9)
    assert calm > shaken
    # 超界输入被钳制
    assert 0.0 <= assess_capture_quality(brightness=9, sharpness=-3, jitter=0.5) <= 1.0


# ======================================================================
# 门禁二：24 人高密声纹 SimHash-LSH
# ======================================================================

def _make_speaker_vector(rng: random.Random, dim: int = VOICEPRINT_DIM) -> list[float]:
    return [rng.gauss(0.0, 1.0) for _ in range(dim)]


def _slice_of(centroid: list[float], rng: random.Random, noise: float = 0.25) -> list[float]:
    return [c + rng.gauss(0.0, noise) for c in centroid]


def test_gate2_24_speakers_clustered_with_zero_partner_transient_confusion() -> None:
    engine = VoiceprintLSHEngine()
    rng = random.Random(20260915)

    # 8 名核心商务伙伴（圆桌主位，每人 24 个切片）+ 16 名穿梭服务员/路人（1~3 切片）
    partner_centroids = {f"partner_{p:02d}": _make_speaker_vector(rng) for p in range(8)}
    transient_centroids = {f"transient_{t:02d}": _make_speaker_vector(rng) for t in range(16)}

    assignment: dict[str, set[str]] = {}
    stream: list[tuple[str, list[float]]] = []
    for p, centroid in partner_centroids.items():
        for _ in range(24):
            stream.append((p, _slice_of(centroid, rng)))
    for idx, (t, centroid) in enumerate(transient_centroids.items()):
        for _ in range(1 + idx % 3):
            stream.append((t, _slice_of(centroid, rng, noise=0.30)))
    rng.shuffle(stream)  # 交织混杂的现场音频流

    for speaker, vec in stream:
        obs = engine.observe(vec)
        assignment.setdefault(speaker, set()).add(obs.cluster_id)

    # 24 声源 → 恰好 24 个簇（零跨声源合并）
    assert engine.cluster_count == 24
    # 每个核心伙伴的全部切片 100% 归入其唯一簇
    partner_clusters = {spk: next(iter(cids)) for spk, cids in assignment.items()
                        if spk.startswith("partner")}
    assert all(len(cids) == 1 for spk, cids in assignment.items() if spk.startswith("partner"))
    assert len(set(partner_clusters.values())) == 8  # 8 伙伴 → 8 个互异簇
    # 核心商务伙伴与穿梭服务员/路人零混淆
    transient_clusters = {cids.pop() for spk, cids in assignment.items()
                          if spk.startswith("transient")}
    assert len(partner_clusters) == 8 and len(transient_clusters) == 16
    assert set(partner_clusters.values()).isdisjoint(transient_clusters)


def test_gate2_industrial_noise_slices_still_bind_to_partner() -> None:
    """85dB 车间高噪切片（额外噪声 0.35）仍能聚到同一伙伴声纹。"""
    engine = VoiceprintLSHEngine()
    rng = random.Random(424242)
    centroid = _make_speaker_vector(rng)
    first = engine.observe(_slice_of(centroid, rng))
    assert first.is_new_cluster
    hits = 0
    for _ in range(12):
        obs = engine.observe(_slice_of(centroid, rng, noise=0.35))
        if obs.cluster_id == first.cluster_id:
            hits += 1
    assert hits >= 11, f"工业噪声下匹配率过低: {hits}/12"


def test_gate2_engine_rejects_wrong_dim() -> None:
    engine = VoiceprintLSHEngine()
    with pytest.raises(ValueError):
        engine.observe([0.1] * (VOICEPRINT_DIM - 1))
    with pytest.raises(ValueError):
        VoiceprintLSHEngine(bands=15, band_bits=8)  # 15*8 != 128


# ======================================================================
# 门禁三：180 天 TTL 墓碑状态机（360 天时间轴模拟）
# ======================================================================

def _build_lifecycle_world() -> tuple[
    VoiceprintTTLRegistry, dict[str, datetime], list[str]
]:
    """8 个已绑定伙伴声纹 + 15 个未绑定背景人声，360 天时间轴。"""
    registry = VoiceprintTTLRegistry(ttl_days=TTL_DAYS)
    last_contacts: dict[str, datetime] = {}
    transient_ids: list[str] = []
    base = T0
    # 8 个核心伙伴：已绑定实体，最后接触延续到第 200 天（豁免淘汰）
    for p in range(8):
        cid = f"spk_partner_{p:02d}"
        registry.register(cid, first_contact=base, last_contact=base)
        registry.bind_entity(cid, f"ent_partner_{p:02d}")
        registry.touch(cid, base + timedelta(days=200))
    # 15 个背景人声（服务员/路人）：未绑定实体，最后接触散布在第 0~170 天
    for t in range(15):
        cid = f"spk_transient_{t:02d}"
        last = base + timedelta(days=2 + 11 * t)  # 2, 13, ..., 167 天
        registry.register(cid, first_contact=base, last_contact=last)
        last_contacts[cid] = last
        transient_ids.append(cid)
    return registry, last_contacts, transient_ids


def test_gate3_tombstone_exactly_at_180_days_on_360day_timeline() -> None:
    registry, last_contacts, transient_ids = _build_lifecycle_world()
    assert TTL_DAYS == 180

    # 逐日推进 360 天，记录每个背景声纹的精确墓碑日
    tombstone_day: dict[str, int] = {}
    for day in range(0, 361):
        now = T0 + timedelta(days=day)
        report = registry.sweep(now)
        for cid in report.tombstoned_ids:
            tombstone_day[cid] = day

    # 15 个背景声纹全部墓碑化，且墓碑日 = 最后接触 + 180 天（瞬间精确）
    assert set(tombstone_day) == set(transient_ids)
    for cid in transient_ids:
        expected_day = (last_contacts[cid] - T0).days + TTL_DAYS
        assert tombstone_day[cid] == expected_day, (
            f"{cid}: 墓碑日 {tombstone_day[cid]} != 预期 {expected_day}"
        )

    # 墓碑瞬间状态：is_tombstone=True 且已从热表剥离至归档区
    for cid in transient_ids:
        record = registry.state(cid)
        assert record.is_tombstone is True
        assert record.tombstoned_at is not None
        assert cid in registry.archive_ids
        assert cid not in registry.hot_table_ids

    # 已绑定实体的 8 个核心伙伴声纹：360 天全程豁免，热表常驻
    for p in range(8):
        cid = f"spk_partner_{p:02d}"
        record = registry.state(cid)
        assert record.is_tombstone is False
        assert record.entity_binding == f"ent_partner_{p:02d}"
        assert cid in registry.hot_table_ids
    assert len(registry.hot_table_ids) == 8
    assert len(registry.archive_ids) == 15


def test_gate3_boundary_day179_false_day180_true() -> None:
    """「最后接触满 180 天的瞬间」：第 179 天必须仍是活跃，第 180 天瞬间墓碑。"""
    registry = VoiceprintTTLRegistry()
    last = T0 + timedelta(days=10)
    registry.register("spk_one_shot", first_contact=T0, last_contact=last)
    day179 = last + timedelta(days=179)
    day180 = last + timedelta(days=180)
    registry.sweep(day179)
    assert registry.state("spk_one_shot").is_tombstone is False
    assert "spk_one_shot" in registry.hot_table_ids
    report = registry.sweep(day180)
    assert report.tombstoned_ids == ("spk_one_shot",)
    assert registry.state("spk_one_shot").is_tombstone is True
    assert registry.hot_table_ids == ()
    # 接触即续命：第 100 天再接触 → 墓碑日顺延至 +280
    registry2 = VoiceprintTTLRegistry()
    registry2.register("spk_renewed", first_contact=T0, last_contact=T0)
    registry2.touch("spk_renewed", T0 + timedelta(days=100))
    mid = registry2.sweep(T0 + timedelta(days=279))
    assert mid.tombstoned_ids == ()
    due = registry2.sweep(T0 + timedelta(days=280))
    assert due.tombstoned_ids == ("spk_renewed",)


def test_gate3_bound_and_unknown_edges() -> None:
    registry = VoiceprintTTLRegistry()
    registry.register("spk_bound", first_contact=T0, last_contact=T0,
                      entity_binding="ent_partner")
    # 已绑定声纹即使远超 TTL 也绝不被淘汰（R2-07 低频高价值不误清理）
    report = registry.sweep(T0 + timedelta(days=3650))
    assert report.tombstoned_ids == ()
    assert registry.state("spk_bound").is_tombstone is False
    with pytest.raises(ValueError):
        registry.state("spk_ghost")
    with pytest.raises(ValueError):
        VoiceprintTTLRegistry(ttl_days=0)
