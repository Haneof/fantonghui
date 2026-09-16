"""对抗生命数据发生器 + 边缘提纯器测试（E2E 盲测阶段 1 底座）。"""

import json
import os
import tempfile

import pytest

from aios_core.simulation.adversarial_life_bench import (
    CREATOR,
    SUBJECT_ID,
    AdversarialLifeGenerator,
    DailyFactStream,
    EdgePurifier,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore


@pytest.fixture(scope="module")
def world():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteWorldStore(db)
    gen = AdversarialLifeGenerator(imu_sample_count=100_000)
    raw = gen.generate_raw_streams()
    pur = EdgePurifier(store, gen.key_events)
    stats = pur.purify_and_populate(raw, DailyFactStream().generate())
    yield store, raw, pur, stats, gen
    os.remove(db)


def test_raw_scale_contract(world):
    _, raw, *_ = world
    # 百万级原始流（IMU 参数化缩放，其余模态固定量级）
    assert raw.raw_imu_sample_count == 100_000
    assert len(raw.hr_waveform) == 24 * 3600
    assert len(raw.gps_track) == 90 * 3
    assert len(raw.image_frames) == 4_000
    assert len(raw.voice_utterances) == 12_000
    assert len(raw.sms_messages) == 6_000
    assert raw.total_raw_records > 200_000


def test_generator_determinism():
    g1 = AdversarialLifeGenerator(imu_sample_count=20_000)
    g2 = AdversarialLifeGenerator(imu_sample_count=20_000)
    r1, r2 = g1.generate_raw_streams(), g2.generate_raw_streams()
    assert r1.imu_samples == r2.imu_samples
    assert r1.hr_waveform == r2.hr_waveform
    assert r1.sms_messages == r2.sms_messages
    assert [e[0] for e in g1.key_events] == [e[0] for e in g2.key_events]


def test_fixed_story_ids(world):
    """五大剧本关键事件/证据集/主张的固定 ID 契约（下游阶段锚点）。"""
    store, *_ = world
    for oid in (
        "obs_e2e_partner_contract",
        "obs_e2e_partner_bank_flow",
        "obs_e2e_partner_fight",
        "obs_e2e_partner_delay",
        "obs_e2e_wang_eco_police",
        "obs_e2e_move_decision",
        "obs_e2e_move_0",
        "obs_e2e_move_4",
        "obs_e2e_move_newbase",
        "evset_e2e_partner_saga",
        "evset_e2e_night_resonance",
        "evset_e2e_family_saga",
        "evset_e2e_move_phase",
        "clm_e2e_wang_fraud",
        "ent_e2e_wang",
        "rel_e2e_me_wang",
    ):
        assert store.get_payload(oid)["object_id"] == oid


def test_iron_rule4_raw_bytes_purged(world):
    store, raw, pur, stats, _ = world
    # 原始图片字节 100% 物理删除，留存 0
    assert pur.raw_sink.retained_bytes == 0
    assert stats.image_raw_bytes_purged == 4_000 * 256
    # 核心证据 100% 永存（逐条读回）
    assert len(pur.core_evidence_ids) > 6_000
    for oid in pur.core_evidence_ids:
        assert store.get_payload(oid)["object_id"] == oid


def test_iron_rule4_noise_physically_deleted(world):
    _, raw, pur, stats, _ = world
    # 语音：陌生声纹 >180 天且非核心 → 物理淘汰；核心原话永存
    assert stats.voice_tombstoned_gt180d > 10_000
    assert stats.voice_text_obs + stats.voice_tombstoned_gt180d == len(raw.voice_utterances)
    assert pur.store.get_payload("obs_e2e_voice_fight_call")["source_kind"] == "speech_transcript"
    # 短信：噪声物理删除，核心永存
    assert stats.sms_noise_physically_deleted == 5_997
    assert stats.sms_core_obs == 3


def test_imu_never_written_raw(world):
    store, raw, _, stats, _ = world
    # 100k 样本 → 仅 7 条宏观状态 + 1 条冲击波形（< 0.001 比例红线）
    assert stats.imu_macro_state_obs == 7
    assert stats.imu_anomaly_impact_obs == 1
    assert (stats.imu_macro_state_obs + stats.imu_anomaly_impact_obs) < raw.raw_imu_sample_count * 0.001
    # 冲击波形峰值保真（6.2g 跌倒）
    impact_payload = json.loads(store.get_payload("obs_e2e_imu_impact_000")["value"])
    assert impact_payload["peak_g"] > 5.5
    # 世界对象总量远小于原始流（禁直写 DB 的比例证据）
    committed = len(store.revisions_after(0, limit=10**9))
    assert committed < raw.total_raw_records


def test_hr_spike_isolated_and_steady_windowed(world):
    store, _, _, stats, _ = world
    # 突变（早搏簇 113 + 通宵峰值 138）独立成条
    assert stats.hr_spike_obs > 6_000
    spike = json.loads(store.get_payload("obs_e2e_hr_spike_0028080")["value"])
    assert spike["type"] == "hr_spike"
    # 平稳期只存 30 分钟窗均值
    assert stats.hr_steady_window_obs == 46
    steady = store.get_payload("obs_e2e_hr_steady_0000000")["value"]
    assert "30 分钟窗" in steady


def test_gps_daily_summary_and_phase_shift(world):
    store, _, _, stats, _ = world
    assert stats.gps_daily_obs == 90
    # 搬家周（day 0~6）出现大位移相变标注
    moved = [json.loads(store.get_payload(f"obs_e2e_gps_day_{d:04d}")["value"]) for d in range(7)]
    shifts = [v for v in moved if v.get("notes")]
    assert len(shifts) >= 1
    assert any("生活相变" in "；".join(s["notes"]) for s in shifts)


def test_daily_fact_stream_scale():
    facts = DailyFactStream().generate()
    # 3 年+ 每日 ~8 条（含月度财务）
    assert 8_000 <= len(facts) <= 9_000
    # 耗竭期（2026-01~03）深睡塌方文本在场
    burnout = [f for f in facts if "耗竭期深睡塌方" in str(f.value)]
    assert len(burnout) > 50
    # 对象 ID 唯一（commit 前置契约）
    ids = [f.object_id for f in facts]
    assert len(ids) == len(set(ids))


def test_voiceprint_binding(world):
    _, _, pur, _, _ = world
    # 24 个声源全部注册；P001 绑定本主体
    assert len(pur.voiceprints._features) == 24
    assert pur.voiceprints.entity_id("P001") == SUBJECT_ID
    # 128 维声纹特征契约
    assert len(pur.voiceprints._features["P001"]) == 128


def test_committed_objects_carry_creator(world):
    store, *_ = world
    payload = store.get_payload("obs_e2e_partner_contract")
    assert payload["created_by"] == CREATOR
    assert payload["subject_id"] == SUBJECT_ID
