"""M1-001R-ADV 高熵工业/商务场景验收单测：5ms 垃圾图粉碎 / 24 人声纹 LSH / 180 天 TTL 墓碑。

高阶实战场景：手环佩戴者连续穿梭于重型工业装配车间（85dB 持续背景机械低频
噪音）与跨国供应链 24 人商务圆桌晚宴（高密度中文/英文/方言交叉重叠混杂），
并在现场持续抓拍设备标牌与合同文本。

四大硬门禁断言：
1. 昏暗+走动抖动场景画质 < 0.4 的 500 张垃圾图 5ms 内物理删除，
   主存储与内存原始字节保留量严格为 0；
2. 24 个不同声源同一音频流切片 → 128 维 LSH，准确区分 8 名核心商务伙伴
   （实体绑定）与 16 名穿梭的服务员/路人（未绑定）；
3. 360 天时间轴模拟：15 个未绑定背景声纹在最后接触满 180 天的瞬间
   is_tombstone 严格置 True，并从活跃匹配热表剥离至归档区。
"""
from __future__ import annotations

import os
import random
import time
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.ingest import (
    FEATURE_DIM,
    EdgeMultimodalCleaner,
    QualityGate,
    RawByteSink,
    VoiceprintLSHIndex,
    VoiceprintLifecycleManager,
    VoiceprintProfile,
    VoiceprintTTLRegistry,
    assess_image_quality,
)

UTC = timezone.utc

N_GARBAGE = 500
N_GOOD = 300
RAW_SIZE = 8 * 1024  # 每帧原始字节 8KB

N_CORE_PARTNERS = 8
N_BACKGROUND = 16
N_SLICES_PER_SPEAKER = 20
LSH_PLANES = 128
SPEAKER_SEED = 20260918
SLICE_NOISE = 0.03

#: 8 名核心商务伙伴（实体绑定）：跨国供应链圆桌
_CORE_PARTNER_ENTITIES = [
    "entity:exec:zhang_supchain",      # 供应链总监（中文）
    "entity:exec:chen_procurement",    # 采购负责人（中文）
    "entity:exec:liu_legal",           # 法务 counsel（中文/英文）
    "entity:partner:kato_jp",          # 日方客户代表（日语口音英文）
    "entity:partner:smith_us",         # 美方客户代表（英文）
    "entity:partner:garcia_mx",        # 墨西哥客户代表（西语口音英文）
    "entity:partner:ahmed_me",         # 中东客户代表（阿语口音英文）
    "entity:partner:kim_kr",           # 韩方客户代表（韩语口音英文）
]

SIM_EPOCH = datetime(2025, 9, 16, tzinfo=UTC)  # 360 天模拟时间轴起点


# ----------------------------------------------------------------------
# 场景数据生成（确定性）
# ----------------------------------------------------------------------


def build_image_batch() -> tuple[list[dict], list[dict], list[bytes]]:
    """500 张昏暗抖动垃圾图 + 300 张达标图（工业车间 + 圆桌晚宴场景）。"""
    rng = random.Random(20260916)
    garbage, good = [], []
    scenes = ("heavy_industrial_assembly_line", "roundtable_dinner", "equipment_signage", "contract_document")
    for i in range(N_GARBAGE + N_GOOD):
        if i < N_GARBAGE:  # 昏暗 + 走动抖动（85dB 车间环境）
            meta = {
                "image_id": f"img_garbage_{i:04d}",
                "mean_luma": round(rng.uniform(15.0, 38.0), 1),
                "high_freq_energy": round(rng.uniform(0.05, 0.35), 3),
                "motion_magnitude": round(rng.uniform(0.5, 0.95), 3),
                "noise_floor_db": 85,
                "scene": rng.choice(scenes),
            }
            garbage.append(meta)
        else:  # 达标抓拍（标牌/合同文本/圆桌特写）
            meta = {
                "image_id": f"img_good_{i - N_GARBAGE:04d}",
                "mean_luma": round(rng.uniform(120.0, 190.0), 1),
                "high_freq_energy": round(rng.uniform(0.55, 0.85), 3),
                "motion_magnitude": round(rng.uniform(0.02, 0.12), 3),
                "scene": rng.choice(scenes),
                "caption": rng.choice(
                    [
                        "设备标牌：装配线 3 号工位扭矩参数",
                        "合同文本：Pre-A 交割条款第 7.2 页",
                        "圆桌晚宴：核心伙伴就供应链条款交换意见",
                        "车间巡检：质检台 A 类缺陷率看板",
                    ]
                ),
                "tags": ["supply_chain", "roundtable", "contract"],
            }
            good.append(meta)
    raws = [os.urandom(RAW_SIZE) for _ in range(N_GARBAGE + N_GOOD)]
    return garbage, good, raws


def build_speaker_streams():
    """24 名说话人 × 20 条 128 维切片（同一音频流交织），确定性生成。"""
    rng = random.Random(900000)
    speakers = {}
    for s in range(N_CORE_PARTNERS + N_BACKGROUND):
        prototype = _norm([rng.gauss(0.0, 1.0) for _ in range(FEATURE_DIM)])
        slices = [
            _norm([p + SLICE_NOISE * rng.gauss(0.0, 1.0) for p in prototype])
            for _ in range(N_SLICES_PER_SPEAKER)
        ]
        canonical = _norm([sum(axis) / 18.0 for axis in zip(*slices[:18])])
        entity = _CORE_PARTNER_ENTITIES[s] if s < N_CORE_PARTNERS else None
        speakers[f"vp_{s:02d}"] = {"canonical": canonical, "slices": slices, "entity": entity}
    # 同一音频流：24 人切片轮转交织（交叉重叠混杂）
    stream = [
        (vp_id, speakers[vp_id]["slices"][s])
        for s in range(N_SLICES_PER_SPEAKER)
        for vp_id in speakers
    ]
    return speakers, stream


def _norm(vec):
    import math

    n = math.sqrt(sum(v * v for v in vec))
    return tuple(v / n for v in vec)


# ----------------------------------------------------------------------
# 门禁 1：画质退化亚毫秒粉碎（500 张 < 5ms，原始字节保留量严格 0）
# ----------------------------------------------------------------------


class TestGate1_SubMillisecondGarbagePurge:
    def test_500_garbage_images_purged_within_5ms_and_zero_retained(self):
        garbage, good, raws = build_image_batch()
        cleaner = EdgeMultimodalCleaner()
        sink = RawByteSink()

        # 全量 800 帧原始字节进入端侧暂存池
        for meta, raw in zip(garbage + good, raws):
            sink.sink(meta["image_id"], raw)
        assert sink.retained_bytes == (N_GARBAGE + N_GOOD) * RAW_SIZE

        # 端侧初筛：500 张昏暗抖动图全部 < 0.4 被抛弃；300 张达标出 Caption
        garbage_ids, good_ids = [], []
        observations = []
        for meta in garbage + good:
            result = cleaner.evaluate_and_clean_image(meta, b"")
            if result is None:
                garbage_ids.append(meta["image_id"])
                assert assess_image_quality(meta) < QualityGate().threshold == 0.4
            else:
                good_ids.append(meta["image_id"])
                observations.append(result)
        assert len(garbage_ids) == N_GARBAGE
        assert len(good_ids) == N_GOOD
        assert all(o.raw_image_bytes_retained is False for o in observations)
        assert all(o.semantic_caption for o in observations)
        assert all(o.quality_score >= 0.4 for o in observations)

        # 5ms 内物理粉碎 500 张垃圾图原始字节
        started = time.perf_counter()
        freed = sink.purge(garbage_ids)
        purge_ms = (time.perf_counter() - started) * 1000.0
        assert freed == N_GARBAGE * RAW_SIZE
        assert purge_ms < 5.0, f"500 张垃圾图粉碎耗时 {purge_ms:.3f}ms 超过 5ms 红线"

        # 达标图 Caption 提取完毕，原始字节同样必须粉碎（主库零保留铁律）
        sink.purge(good_ids)
        assert sink.retained_bytes == 0  # 主存储与内存原始字节保留量严格为 0
        assert len(sink) == 0

    def test_boundary_quality_0_4_is_kept(self):
        cleaner = EdgeMultimodalCleaner()
        kept = cleaner.evaluate_and_clean_image({"quality_score": 0.4}, b"x")
        assert kept is not None
        dropped = cleaner.evaluate_and_clean_image({"quality_score": 0.39}, b"x")
        assert dropped is None

    def test_raw_bytes_never_land_in_persisted_fields(self):
        _, good, _ = build_image_batch()
        cleaner = EdgeMultimodalCleaner()
        observation = cleaner.evaluate_and_clean_image(good[0], b"\x00" * 64)
        dumped = observation.model_dump_json()
        assert "000000000000" not in dumped  # 原始字节零泄漏进持久化字段
        assert observation.raw_image_bytes_retained is False


# ----------------------------------------------------------------------
# 门禁 2：24 人高密声纹 128 维 LSH（核心伙伴 vs 服务员/路人）
# ----------------------------------------------------------------------


class TestGate2_24SpeakerLSH:
    @pytest.fixture(scope="class")
    def index_and_streams(self):
        speakers, stream = build_speaker_streams()
        index = VoiceprintLSHIndex(seed=SPEAKER_SEED, lsh_planes=LSH_PLANES)
        for vp_id, data in speakers.items():
            index.add(vp_id, data["canonical"], entity_id=data["entity"])
        return index, speakers, stream

    def test_480_stream_slices_cluster_with_100_percent_purity(self, index_and_streams):
        index, speakers, stream = index_and_streams
        assert len(index) == 24
        wrong = 0
        for vp_id, feature in stream:
            if index.assign_slice(feature) != vp_id:
                wrong += 1
        # 24 人同一音频流 480 条切片：聚类指派 100% 正确
        assert wrong == 0

    def test_intra_inter_hamming_separation_gap(self, index_and_streams):
        """同声源汉明距离（簇内）与异声源（簇间）存在清晰分离带。"""
        index, speakers, _ = index_and_streams
        intra, inter = [], []
        for vp_id, data in speakers.items():
            sig = index.signature(vp_id)
            from aios_core.ingest.multimodal_edge import hamming_distance, lsh_signature

            for sl in data["slices"]:
                intra.append(hamming_distance(lsh_signature(sl, index._planes), sig))
        vp_ids = list(speakers)
        for i in range(len(vp_ids)):
            for j in range(i + 1, len(vp_ids)):
                from aios_core.ingest.multimodal_edge import hamming_distance

                inter.append(
                    hamming_distance(index.signature(vp_ids[i]), index.signature(vp_ids[j]))
                )
        gap = min(inter) - max(intra)
        assert gap >= 10, f"簇内/簇间汉明分离带 {gap} 过窄，24 人不可靠区分"

    def test_core_partners_vs_background_are_precisely_separated(self, index_and_streams):
        """核心商务伙伴（实体绑定 8 名）与服务员/路人（未绑定 16 名）精确区分。"""
        index, speakers, _ = index_and_streams
        bound = {vp for vp in speakers if index.entity_id(vp) is not None}
        unbound = {vp for vp in speakers if index.entity_id(vp) is None}
        assert len(bound) == N_CORE_PARTNERS == 8
        assert len(unbound) == N_BACKGROUND == 16
        assert {index.entity_id(vp) for vp in bound} == set(_CORE_PARTNER_ENTITIES)

        # 每名核心伙伴的 held-out 切片 top-1 检索命中自己（身份可穿透确认）
        for vp_id, data in speakers.items():
            top = index.candidate_search(data["slices"][19], k=1)
            assert top[0][0] == vp_id

    def test_feature_dim_and_signature_width(self, index_and_streams):
        index, _, _ = index_and_streams
        assert FEATURE_DIM == 128
        signature = index.signature("vp_00")
        assert LSH_PLANES <= signature.bit_length() <= LSH_PLANES  # 128 位 LSH 签名


# ----------------------------------------------------------------------
# 门禁 3：180 天 TTL 墓碑状态机（360 天时间轴，15 个背景声纹）
# ----------------------------------------------------------------------


class TestGate3_180DayTTLTombstone:
    N_BACKGROUND_VOICES = 15

    def _build_registry(self):
        registry = VoiceprintTTLRegistry(ttl_days=180)
        bg_last_contact_day = {}
        for i in range(self.N_BACKGROUND_VOICES):
            last_day = 30 + 8 * i  # 最后接触分布在第 30~142 天
            bg_last_contact_day[f"vp_bg_{i:02d}"] = last_day
            registry.register(
                VoiceprintProfile(
                    voiceprint_id=f"vp_bg_{i:02d}",
                    entity_id=None,  # 未绑定实体身份：服务员/路人
                    feature_hash=f"hash_bg_{i:02d}",
                    first_detected_at=SIM_EPOCH + timedelta(days=last_day - 20),
                    last_contact_at=SIM_EPOCH + timedelta(days=last_day),
                )
            )
        for i in range(N_CORE_PARTNERS):
            registry.register(
                VoiceprintProfile(
                    voiceprint_id=f"vp_core_{i:02d}",
                    entity_id=_CORE_PARTNER_ENTITIES[i],  # 核心伙伴：实体绑定，TTL 豁免
                    feature_hash=f"hash_core_{i:02d}",
                    first_detected_at=SIM_EPOCH + timedelta(days=5),
                    last_contact_at=SIM_EPOCH + timedelta(days=350),
                )
            )
        return registry, bg_last_contact_day

    def test_tombstone_flips_at_exactly_180_days_over_360_day_timeline(self):
        registry, last_day = self._build_registry()
        tombstone_day: dict[str, int] = {}
        state_before: dict[str, bool] = {vp: False for vp in last_day}

        for day in range(0, 361):
            now = SIM_EPOCH + timedelta(days=day)
            # 清扫前：记录"满 180 天瞬间"的上一状态（必须仍为活跃）
            for vp, t_day in last_day.items():
                if day == t_day + 180:
                    assert registry.is_tombstone(vp) is state_before[vp]
                    assert state_before[vp] is False  # 满 180 天前一天仍活跃
            swept = registry.sweep(now)
            for vp in swept:
                tombstone_day.setdefault(vp, day)
                state_before[vp] = True
                assert registry.is_tombstone(vp) is True

        # 每个背景声纹都在"最后接触满 180 天的瞬间"精确墓碑化（>= 边界语义）
        assert len(tombstone_day) == self.N_BACKGROUND_VOICES
        for vp, t_day in last_day.items():
            assert tombstone_day[vp] == t_day + 180, (
                f"{vp} 应在第 {t_day + 180} 天墓碑，实际第 {tombstone_day[vp]} 天"
            )

        # 热表/归档区剥离：15 个背景声纹全部在归档区，8 名核心伙伴留在热表
        archived_ids = {p.voiceprint_id for p in registry.archived}
        hot_ids = {p.voiceprint_id for p in registry.active_hot}
        assert archived_ids == set(last_day)
        assert hot_ids == {f"vp_core_{i:02d}" for i in range(N_CORE_PARTNERS)}
        assert len(hot_ids) == N_CORE_PARTNERS

    def test_boundary_semantics_179_days_still_active(self):
        registry = VoiceprintTTLRegistry(ttl_days=180)
        t_contact = datetime(2025, 1, 1, tzinfo=UTC)
        registry.register(
            VoiceprintProfile(
                voiceprint_id="vp_edge",
                entity_id=None,
                feature_hash="hash_edge",
                first_detected_at=t_contact - timedelta(days=10),
                last_contact_at=t_contact,
            )
        )
        # 满 180 天差 1 秒：仍活跃
        assert registry.sweep(t_contact + timedelta(days=179, hours=23, minutes=59, seconds=59)) == []
        assert registry.is_tombstone("vp_edge") is False
        # 满 180 天瞬间：严格墓碑
        assert registry.sweep(t_contact + timedelta(days=180)) == ["vp_edge"]
        assert registry.is_tombstone("vp_edge") is True

    def test_recontact_revives_tombstoned_voiceprint(self):
        registry, last_day = self._build_registry()
        vp = "vp_bg_00"
        tombstone_moment = SIM_EPOCH + timedelta(days=last_day[vp] + 180)
        assert vp in registry.sweep(tombstone_moment)
        assert registry.is_tombstone(vp) is True
        # 再次接触（10 天后）：状态机 TOMBSTONED -> ACTIVE，复活回热表
        revived = registry.note_contact(vp, tombstone_moment + timedelta(days=10))
        assert revived.is_tombstone is False
        hot_ids = {p.voiceprint_id for p in registry.active_hot}
        assert vp in hot_ids
        assert hot_ids >= {f"vp_core_{i:02d}" for i in range(N_CORE_PARTNERS)}
        # 其余 14 个背景声纹此时尚未满 180 天（TTL 未到期），本应仍在热表
        assert len(hot_ids) == N_CORE_PARTNERS + self.N_BACKGROUND_VOICES
        # 复活后 TTL 重新计时（340 + 180 > 360）：360 天时间轴终点不再墓碑
        swept_at_360 = registry.sweep(SIM_EPOCH + timedelta(days=360))
        assert vp not in swept_at_360
        assert vp in {p.voiceprint_id for p in registry.active_hot}
        assert registry.is_tombstone(vp) is False

    def test_skeleton_sweep_still_compatible(self):
        """M1-001R 骨架契约回归：批量清扫 API 行为不变。"""
        mgr = VoiceprintLifecycleManager()
        now = datetime(2026, 9, 16, tzinfo=UTC)
        old = VoiceprintProfile(
            voiceprint_id="vp_001",
            feature_hash="hash123",
            first_detected_at=now - timedelta(days=200),
            last_contact_at=now - timedelta(days=190),
        )
        fresh = VoiceprintProfile(
            voiceprint_id="vp_002",
            entity_id="entity:exec:zhang_supchain",
            feature_hash="hash124",
            first_detected_at=now - timedelta(days=10),
            last_contact_at=now - timedelta(days=1),
        )
        res = mgr.sweep_stale_voiceprints([old, fresh], now)
        assert res[0].is_tombstone is True
        assert res[1].is_tombstone is False  # 实体绑定豁免 TTL
