"""端侧流提纯引擎单测：唯一写入口、噪声物理删除、证据 100% 留存、声纹 TTL。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.enums import ObjectType
from aios_core.perception.edge_stream_purifier import (
    EdgePurifierPolicy,
    EdgeStreamPurifier,
    PurgeLedger,
    RawEnvironmentText,
    RawHeartSample,
    RawImuSample,
    RawVisionFrame,
    RetentionAdjudicator,
    RetentionVerdict,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def store(tmp_path) -> SQLiteWorldStore:
    return SQLiteWorldStore(str(tmp_path / "edge.db"))


def test_adjudicator_separates_noise_from_evidence() -> None:
    adjudicator = RetentionAdjudicator()
    noise = adjudicator.adjudicate("商场广播：三楼男装全场促销清仓打折，欢迎扫码关注公众号")
    assert noise.verdict is RetentionVerdict.NOISE
    evidence = adjudicator.adjudicate(
        "陈律师的原话：借据、转账凭证、聊天记录三样齐全，证据链闭合。"
    )
    assert evidence.verdict is RetentionVerdict.KEEP
    protected = adjudicator.adjudicate("商场广播促销", protected_by="EvidenceSet:evs_1")
    assert protected.verdict is RetentionVerdict.KEEP


def test_high_frequency_stream_is_compressed_not_persisted_raw(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store)
    samples = [
        RawImuSample(t_us=int((T0 + timedelta(seconds=index / 50)).timestamp() * 1_000_000), ax=0.0, ay=0.0, az=1.0)
        for index in range(3_000)
    ]
    purifier.ingest_imu_stream(samples)
    purifier.flush()
    stored = store.list_payloads(object_type=ObjectType.OBSERVATION)
    assert stored
    assert all(item["source_kind"] != "imu_raw_sample" for item in stored)
    assert all(int(item["metadata"]["sample_count"]) >= 1 for item in stored)


def test_impacts_are_emitted_as_their_own_observation(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store, policy=EdgePurifierPolicy(imu_impact_magnitude=3.0))
    t_us = int(T0.timestamp() * 1_000_000)
    purifier.ingest_imu_stream(
        [RawImuSample(t_us=t_us + index * 20_000, ax=0.0, ay=0.0, az=1.0) for index in range(400)]
    )
    purifier.ingest_imu_stream([RawImuSample(t_us=t_us + 400 * 20_000, ax=0.0, ay=0.0, az=5.6)])
    purifier.flush()
    kinds = [item["source_kind"] for item in store.list_payloads(object_type=ObjectType.OBSERVATION)]
    assert "imu_impact" in kinds


def test_heart_anomaly_and_summary_are_separate_channels(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store)
    base = int(T0.timestamp() * 1_000_000)
    samples = [RawHeartSample(t_us=base + index * 1_000_000, bpm=68.0, hrv_ms=45.0) for index in range(600)]
    samples.append(RawHeartSample(t_us=base + 600 * 1_000_000, bpm=138.0, hrv_ms=18.0, pvc_count=6))
    purifier.ingest_heart_stream(samples)
    purifier.flush()
    kinds = {item["source_kind"] for item in store.list_payloads(object_type=ObjectType.OBSERVATION)}
    assert "heart_rate_summary" in kinds
    assert "heart_rate_anomaly" in kinds


def test_vision_keeps_caption_and_sinks_raw_bytes(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store)
    frame = RawVisionFrame(
        frame_id="frm_1",
        t_us=int(T0.timestamp() * 1_000_000),
        caption="现场抓拍：合同签字桌与银行流水打印件",
        tags=("evidence",),
        raw_bytes=b"\x00" * 4096,
    )
    purifier.ingest_vision_frame(frame)
    purifier.flush()
    stored = store.list_payloads(object_type=ObjectType.OBSERVATION)
    assert any(item["source_kind"] == "vision_caption" for item in stored)
    assert all("raw_bytes" not in item for item in stored)
    report = purifier.report()
    assert report.raw_image_bytes_retained == 0
    assert report.raw_image_bytes_sunk >= 4096


def test_noise_is_dropped_at_edge_and_evidence_kept(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store)
    base = int(T0.timestamp() * 1_000_000)
    noise = "小区门口房产中介叫卖：学区房特价，买房送车位，扫码进群"
    core = "张医生的医嘱原话：二甲双胍早晚各一片，餐后两小时血糖务必每周测三次。"
    purifier.ingest_text_event(RawEnvironmentText(event_id="t1", t_us=base, channel="sms", text=noise))
    purifier.ingest_text_event(RawEnvironmentText(event_id="t2", t_us=base + 1, channel="sms", text=core))
    purifier.flush()
    corpus = "\n".join(
        str(item.get("value", "")) for item in store.list_payloads(object_type=ObjectType.OBSERVATION)
    )
    assert noise not in corpus
    assert core in corpus
    assert purifier.report().noise_dropped_at_edge >= 1


def test_daily_review_purges_unprotected_text_and_keeps_sensor_rows(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store)
    base = int(T0.timestamp() * 1_000_000)
    purifier.ingest_text_event(
        RawEnvironmentText(event_id="t3", t_us=base, channel="chat", text="嗯嗯好的收到")
    )
    purifier.ingest_heart_stream(
        [RawHeartSample(t_us=base + index * 1_000_000, bpm=66.0, hrv_ms=48.0) for index in range(120)]
    )
    purifier.flush()
    review = purifier.daily_review(now=T0 + timedelta(days=1))
    assert review.tombstoned_noise >= 1
    assert review.ledger_ok is True
    remaining = store.list_payloads(object_type=ObjectType.OBSERVATION)
    assert any(item["source_kind"] == "heart_rate_summary" for item in remaining)
    assert all("嗯嗯好的收到" not in str(item.get("value", "")) for item in remaining)


def test_purge_ledger_hash_chain_detects_tampering() -> None:
    ledger = PurgeLedger()
    ledger.append(object_id="obs_1", action="tombstoned", verdict="noise", score=-0.7, reasons=("促销",))
    ledger.append(object_id="obs_2", action="tombstoned", verdict="noise", score=-0.35, reasons=("广播",))
    assert ledger.verify_chain() is True
    assert ledger.count("tombstoned") == 2
    # 篡改任意一条（含裁决理由）都必须破坏整条链
    entries = ledger.entries
    entries[0] = entries[0].model_copy(update={"reasons": ("被篡改",)})
    assert ledger.verify_chain() is False


def test_voiceprint_ttl_sweep_returns_tuple(store: SQLiteWorldStore) -> None:
    purifier = EdgeStreamPurifier(store)
    base = int(T0.timestamp() * 1_000_000)
    purifier.ingest_heart_stream([RawHeartSample(t_us=base, bpm=70.0)])
    purifier.flush()
    tombstones = purifier.sweep_voiceprints(T0 + timedelta(days=181))
    assert isinstance(tombstones, tuple)
