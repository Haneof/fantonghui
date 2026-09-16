"""M1-001R-ADV 独立红队验收层（独立命名，纯追加 —— 不改动、不覆盖任何既有版本）。

高熵工业/商务场景（85dB 车间 + 24 人跨国圆桌）对抗性复核：

- TTL 边界"瞬间"语义：最后接触满 180 天的整点迁移（179 天 23:59:59 仍活跃）；
- 错峰到期：5 个不同接触日的声纹各自在恰好的时刻墓碑化；
- 360 天工单规模复测：15 未绑定全部墓碑 / 8 绑定核心伙伴永驻热表；
- 墓碑复活语义（再次接触 → 回热表 → 重新计 180 天）；
- LSH 红队：同人重现小距离聚类 / 未知第 25 人异常可检测 / 24 人 100% 纯净；
- RawByteSink 红队：未知 id / 重复 purge / 单写约束 / 3000 张线性缩放；
- 画质边界 0.4 与昏暗崩塌（luma<40 × 0.3）。
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.ingest.multimodal_edge import (
    FEATURE_DIM,
    EdgeMultimodalCleaner,
    QualityGate,
    RawByteSink,
    VoiceprintLSHIndex,
    VoiceprintProfile,
    VoiceprintTTLRegistry,
    assess_image_quality,
)

UTC = datetime(2026, 1, 1, tzinfo=timezone.utc)
SEED = 20260918
LSH_PLANES = 128


def make_speaker_base(rng: random.Random) -> list[float]:
    return [rng.gauss(0.0, 1.0) for _ in range(FEATURE_DIM)]


def jitter(base: list[float], rng: random.Random, sigma: float = 0.05) -> list[float]:
    return [v + rng.gauss(0.0, sigma) for v in base]


def make_profile(
    voiceprint_id: str,
    *,
    entity_id: str | None,
    first_detected_at: datetime,
    last_contact_at: datetime,
) -> VoiceprintProfile:
    return VoiceprintProfile(
        voiceprint_id=voiceprint_id,
        entity_id=entity_id,
        feature_hash=f"hash:{voiceprint_id}",
        first_detected_at=first_detected_at,
        last_contact_at=last_contact_at,
    )


# ----------------------------------------------------------------------
# 门禁 3 红队：180 天 TTL 墓碑状态机
# ----------------------------------------------------------------------


class TestTtlBoundarySemantics:
    def test_tombstones_at_exact_180th_day_moment_only(self):
        registry = VoiceprintTTLRegistry()
        contacts = {f"vp-{d:02d}": UTC + timedelta(days=d) for d in (10, 20, 30, 40, 50)}
        for vp_id, at in contacts.items():
            registry.register(make_profile(vp_id, entity_id=None, first_detected_at=at, last_contact_at=at))

        # 第 10 天接触的声纹在 179 天 23:59:59 仍必须活跃
        near = UTC + timedelta(days=189, hours=23, minutes=59, seconds=59)
        assert registry.sweep(near) == []
        assert len(registry.active_hot) == 5

        # 恰好满 180 天的"瞬间"：严格墓碑化（>= 边界）
        assert registry.sweep(UTC + timedelta(days=190)) == ["vp-10"]
        assert registry.is_tombstone("vp-10") is True
        assert registry.is_tombstone("vp-20") is False

        # 错峰到期：其余 4 个各自在"接触日 + 180 天"的恰好的时刻墓碑化，一次只到期一个
        for day, vp_id in ((200, "vp-20"), (210, "vp-30"), (220, "vp-40"), (230, "vp-50")):
            assert registry.sweep(UTC + timedelta(days=day)) == [vp_id]
        assert registry.sweep(UTC + timedelta(days=360)) == []  # 无新增
        assert len(registry.archived) == 5
        assert len(registry.active_hot) == 0

    def test_ticket_scale_360_day_run_15_unbound_vs_8_bound(self):
        rng = random.Random(SEED)
        registry = VoiceprintTTLRegistry()
        unbound_ids, bound_ids = [], []
        for i in range(15):  # 15 个未绑定背景人声（服务员/路人/车间访客）
            last = UTC + timedelta(days=rng.randint(0, 100), hours=rng.randint(0, 23))
            vp_id = f"bg-{i:02d}"
            registry.register(make_profile(vp_id, entity_id=None, first_detected_at=last - timedelta(days=30), last_contact_at=last))
            unbound_ids.append(vp_id)
        for i in range(8):  # 8 名绑定核心商务伙伴
            last = UTC + timedelta(days=rng.randint(300, 359))
            vp_id = f"core-{i:02d}"
            registry.register(make_profile(vp_id, entity_id=f"entity:partner:{i}", first_detected_at=UTC, last_contact_at=last))
            bound_ids.append(vp_id)

        tombstoned = registry.sweep(UTC + timedelta(days=360))
        assert sorted(tombstoned) == sorted(unbound_ids)  # 15 个全部墓碑
        assert {p.voiceprint_id for p in registry.active_hot} == set(bound_ids)  # 8 个永驻热表
        assert {p.voiceprint_id for p in registry.archived} == set(unbound_ids)

    def test_tombstone_revives_on_recontact_then_ages_again(self):
        registry = VoiceprintTTLRegistry()
        last = UTC + timedelta(days=10)
        registry.register(make_profile("vp-r", entity_id=None, first_detected_at=last, last_contact_at=last))
        assert registry.sweep(UTC + timedelta(days=190)) == ["vp-r"]
        assert registry.is_tombstone("vp-r") is True

        # 再次接触 → 复活回热表
        revived = registry.note_contact("vp-r", UTC + timedelta(days=200))
        assert revived.is_tombstone is False
        assert {p.voiceprint_id for p in registry.active_hot} == {"vp-r"}

        # 从复活时刻重新计 180 天：第 380 天（200+180）再次墓碑
        assert registry.sweep(UTC + timedelta(days=379)) == []
        assert registry.sweep(UTC + timedelta(days=380)) == ["vp-r"]

    def test_bound_partner_is_ttl_exempt_even_after_360_days(self):
        registry = VoiceprintTTLRegistry()
        registry.register(
            make_profile("core-x", entity_id="entity:partner:x", first_detected_at=UTC, last_contact_at=UTC)
        )
        assert registry.sweep(UTC + timedelta(days=360)) == []
        assert registry.is_tombstone("core-x") is False


# ----------------------------------------------------------------------
# 门禁 2 红队：24 人 128 维 LSH
# ----------------------------------------------------------------------


class TestLshRedTeam:
    @pytest.fixture(scope="class")
    @classmethod
    def index_and_speakers(cls):
        rng = random.Random(SEED)
        index = VoiceprintLSHIndex(seed=SEED, lsh_planes=LSH_PLANES)
        bases = {}
        for i in range(24):
            base = make_speaker_base(rng)
            bases[f"spk-{i:02d}"] = base
            index.add(f"spk-{i:02d}", base, entity_id=f"entity:partner:{i}" if i < 8 else None)
        slices = {}
        for vp_id, base in bases.items():
            slices[vp_id] = [jitter(base, rng) for _ in range(30)]
        return index, slices

    def test_24_speakers_720_stream_slices_100_percent_pure(self, index_and_speakers):
        index, slices = index_and_speakers
        wrong = 0
        for vp_id, speaker_slices in slices.items():
            for sl in speaker_slices:
                if index.assign_slice(sl) != vp_id:
                    wrong += 1
        assert wrong == 0  # 24 × 30 = 720 条交织切片 100% 归位

    def test_intra_inter_hamming_separation_margin(self, index_and_speakers):
        from aios_core.ingest.multimodal_edge import _normalize, hamming_distance, lsh_signature

        index, slices = index_and_speakers
        # 类内：同人切片签名 vs 参考签名（取最大距离）
        intra_max = 0
        for vp_id, speaker_slices in slices.items():
            ref_sig = index.signature(vp_id)
            for sl in speaker_slices:
                sig = lsh_signature(_normalize(sl), index._planes)
                intra_max = max(intra_max, hamming_distance(ref_sig, sig))
        # 类间：24 个参考签名两两最小距离
        ids = list(slices)
        inter_min = min(
            hamming_distance(index.signature(a), index.signature(b))
            for i, a in enumerate(ids)
            for b in ids[i + 1 :]
        )
        assert intra_max < inter_min  # 类内/类间汉明距离存在可分间隙

    def test_same_person_reappearance_clusters_tightly(self, index_and_speakers):
        index, slices = index_and_speakers
        rng = random.Random(SEED + 1)
        return_slice = jitter(slices["spk-05"][0], rng, sigma=0.03)  # 核心伙伴重现
        top_id, top_dist = index.candidate_search(return_slice, k=1)[0]
        assert top_id == "spk-05"
        assert top_dist <= 3  # 同人重现：极小汉明距离

    def test_unknown_25th_speaker_is_detectable_anomaly(self, index_and_speakers):
        index, slices = index_and_speakers
        from aios_core.ingest.multimodal_edge import _normalize, hamming_distance, lsh_signature

        intra_max = max(
            hamming_distance(index.signature(vp_id), lsh_signature(_normalize(sl), index._planes))
            for vp_id, speaker_slices in slices.items()
            for sl in speaker_slices
        )
        rng = random.Random(SEED + 2)
        stranger = make_speaker_base(rng)  # 第 25 人：完全未注册
        top_id, top_dist = index.candidate_search(stranger, k=1)[0]
        # 异常可检测：陌生人与任何已注册声纹的距离都显著大于类内噪声水平
        assert top_dist > intra_max

    def test_signature_is_128_bit_lsh(self, index_and_speakers):
        index, _ = index_and_speakers
        for vp_id in index._signatures:
            sig = index.signature(vp_id)
            assert 0 < sig.bit_length() <= 128
            assert 0 < bin(sig).count("1") < 128  # 非退化签名

    def test_registration_contract(self, index_and_speakers):
        index, _ = index_and_speakers
        with pytest.raises(ValueError, match="128-dim"):
            index.add("bad-dim", [0.1] * 64)
        with pytest.raises(ValueError, match="already registered"):
            index.add("spk-00", [0.1] * FEATURE_DIM)
        with pytest.raises(KeyError):
            index.signature("ghost")


# ----------------------------------------------------------------------
# 门禁 1 红队：RawByteSink 物理粉碎与画质边界
# ----------------------------------------------------------------------


class TestRawByteSinkRedTeam:
    def _blob(self, rng: random.Random, kb_min: int, kb_max: int) -> bytes:
        size = rng.randint(kb_min * 1024, kb_max * 1024)
        return bytes(rng.getrandbits(8) for _ in range(size))

    def test_2000_garbage_purged_zero_retained_for_them(self):
        rng = random.Random(SEED)
        sink = RawByteSink()
        garbage_sizes, good_sizes = {}, {}
        for i in range(2000):
            blob = self._blob(rng, 1, 4)
            sink.sink(f"garbage-{i:04d}", blob)
            garbage_sizes[f"garbage-{i:04d}"] = len(blob)
        for i in range(500):
            blob = self._blob(rng, 1, 8)
            sink.sink(f"good-{i:03d}", blob)
            good_sizes[f"good-{i:03d}"] = len(blob)
        assert sink.retained_bytes == sum(garbage_sizes.values()) + sum(good_sizes.values())

        freed = sink.purge(list(garbage_sizes))
        assert freed == sum(garbage_sizes.values())
        assert sink.retained_bytes == sum(good_sizes.values())  # 垃圾图原始字节严格 0 残留
        assert len(sink) == 500

    def test_purge_unknown_ids_and_double_purge_are_noops(self):
        sink = RawByteSink()
        sink.sink("a", b"12345")
        assert sink.purge(["nope", "never"]) == 0
        assert sink.purge(["a"]) == 5
        assert sink.purge(["a"]) == 0  # 二次粉碎：无事发生
        assert sink.retained_bytes == 0

    def test_single_write_contract(self):
        sink = RawByteSink()
        sink.sink("img", b"raw")
        with pytest.raises(ValueError, match="single-write"):
            sink.sink("img", b"other")
        with pytest.raises(ValueError, match="non-empty"):
            sink.sink("", b"x")

    def test_3000_image_purge_linear_scaling(self):
        rng = random.Random(SEED + 3)
        sink = RawByteSink()
        for i in range(3000):
            sink.sink(f"scale-{i:04d}", self._blob(rng, 1, 2))
        started = time.perf_counter()
        freed = sink.purge([f"scale-{i:04d}" for i in range(3000)])
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert freed > 0
        assert sink.retained_bytes == 0
        # 5ms 红线按 500 张口径 × 6 倍线性缩放
        assert elapsed_ms <= 30.0, f"3000 张粉碎耗时 {elapsed_ms:.2f}ms 超出线性缩放预算"


class TestQualityGateRedTeam:
    def test_boundary_0_4_kept_and_0_3999_dropped(self):
        cleaner = EdgeMultimodalCleaner()
        assert cleaner.evaluate_and_clean_image({"quality_score": 0.3999}, b"raw") is None
        kept = cleaner.evaluate_and_clean_image(
            {"quality_score": 0.4, "caption": "设备标牌：3号装配线", "tags": ["nameplate"]}, b"raw"
        )
        assert kept is not None
        assert kept.raw_image_bytes_retained is False
        assert kept.quality_score == 0.4

    def test_dark_scene_collapse_multiplies_by_0_3(self):
        # 明亮清晰但昏暗（luma<40）：总分 ×0.3 → 0.6912×0.3 ≈ 0.207 < 0.4
        meta = {"mean_luma": 30.0, "high_freq_energy": 1.0, "motion_magnitude": 0.0}
        assert assess_image_quality(meta) < 0.4
        assert QualityGate().passes(assess_image_quality(meta)) is False

    def test_explicit_score_bypasses_sensor_synthesis(self):
        assert assess_image_quality({"quality_score": 0.9, "mean_luma": 5.0}) == 0.9
