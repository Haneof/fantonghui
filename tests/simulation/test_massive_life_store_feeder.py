"""海量人生底层基础数据直写入库与存储容量测算器回归测试。"""

import tempfile
from datetime import datetime, timedelta, timezone

from aios_core.contracts.enums import SourceClass
from aios_core.simulation.massive_life_store_feeder import (
    MassiveLifeStoreFeeder,
    RawStreamKind,
)

UTC = timezone.utc


def _record(
    feeder: MassiveLifeStoreFeeder,
    *,
    subject_id: str,
    kind: RawStreamKind,
    content,
    occurred_at: datetime,
    modality: str,
):
    # 用固定 ingest 时刻保证测试确定性，同时显式验证 occurred/learned/recorded 三时间分离。
    learned = occurred_at + timedelta(days=30)
    recorded = learned + timedelta(seconds=1)
    return feeder.record_raw_observation(
        subject_id=subject_id,
        stream_kind=kind,
        content=content,
        occurred_at=occurred_at,
        learned_at=learned,
        recorded_at=recorded,
        modality=modality,
    )


def test_feeder_direct_sqlite_ingestion_and_capacity_measurement():
    with tempfile.TemporaryDirectory() as tmp_dir:
        subject_id = "P-TEST-001"
        db_path = MassiveLifeStoreFeeder.resolve_subject_store_path(tmp_dir, subject_id)
        feeder = MassiveLifeStoreFeeder(db_path)
        base_time = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)

        obs_sensor = _record(
            feeder,
            subject_id=subject_id,
            kind=RawStreamKind.SENSOR,
            content={"heart_rate": 72, "steps": 1250, "sleep_stage": "deep_sleep"},
            occurred_at=base_time,
            modality="sensor_telemetry",
        )
        obs_mic = _record(
            feeder,
            subject_id=subject_id,
            kind=RawStreamKind.MIC_TRANSCRIPTION,
            content="地铁车厢报站声：下一站国贸，请下车的乘客提前做好准备。",
            occurred_at=base_time + timedelta(hours=1),
            modality="transcription_text",
        )
        obs_cam = _record(
            feeder,
            subject_id=subject_id,
            kind=RawStreamKind.CAMERA_CAPTION,
            content="镜头拍摄：办公桌前堆满待审批的合同卷宗，左侧放着半杯已冷却的美式咖啡。",
            occurred_at=base_time + timedelta(hours=3),
            modality="caption_text",
        )
        obs_app = _record(
            feeder,
            subject_id=subject_id,
            kind=RawStreamKind.APP_DATA,
            content={
                "app": "Alipay",
                "type": "bill",
                "amount": 28.5,
                "merchant": "老王面馆",
                "time": "12:15",
            },
            occurred_at=base_time + timedelta(hours=4),
            modality="structured_json",
        )
        obs_chat = _record(
            feeder,
            subject_id=subject_id,
            kind=RawStreamKind.USER_CHAT,
            content={
                "user_prompt": "今天开了一整天会，头疼得要命，晚上帮我把非紧急提醒全静音。",
                "ai_reply": "收到。已为您启用沉浸静音模式，仅保留家人来电与心率突增强提醒，好好休息。",
            },
            occurred_at=base_time + timedelta(hours=12),
            modality="dialogue_json",
        )

        assert obs_sensor.object_id.startswith("obs_")
        assert obs_chat.source_kind == "user_chat"
        assert obs_mic.learned_at > obs_mic.occurred.start
        assert obs_mic.recorded_at > obs_mic.learned_at

        # 原始外部 perception/app 流默认进入现有非-AI原始摄入类，不能冒充 AI_COGNITION。
        assert feeder.store.commit_source_class(1) == SourceClass.SENSOR.value
        assert feeder.store.commit_source_class(2) == SourceClass.SENSOR.value
        assert feeder.store.commit_source_class(3) == SourceClass.SENSOR.value
        assert feeder.store.commit_source_class(4) == SourceClass.SENSOR.value
        assert feeder.store.commit_source_class(5) == SourceClass.USER.value

        report = feeder.measure_storage_capacity(subject_id)
        assert report.total_observations == 5
        assert report.total_commits == 5
        assert report.total_file_bytes > 0
        assert report.total_file_kb > 0
        assert report.category_counts[RawStreamKind.SENSOR.value] == 1
        assert report.category_counts[RawStreamKind.MIC_TRANSCRIPTION.value] == 1
        assert report.category_counts[RawStreamKind.CAMERA_CAPTION.value] == 1
        assert report.category_counts[RawStreamKind.APP_DATA.value] == 1
        assert report.category_counts[RawStreamKind.USER_CHAT.value] == 1

        md_summary = report.summary_markdown()
        assert "3年存储容量测算报告" in md_summary
        assert "user_chat" in md_summary
        assert "sensor" in md_summary

        # 每日生活流按 occurred_at 取，不受一个月后的 learned_at 影响。
        daily_records = feeder.query_daily_observations(subject_id, "2024-01-01")
        assert len(daily_records) == 5
        assert any("美式咖啡" in str(r.get("value")) for r in daily_records)
        assert any("非紧急提醒全静音" in str(r.get("value")) for r in daily_records)

        # 同一原始流重放：deterministic observation id + existence check -> no-op。
        commits_before = report.total_commits
        replay = feeder.record_raw_observation(
            subject_id=subject_id,
            stream_kind=RawStreamKind.MIC_TRANSCRIPTION,
            content="地铁车厢报站声：下一站国贸，请下车的乘客提前做好准备。",
            occurred_at=base_time + timedelta(hours=1),
            learned_at=obs_mic.learned_at + timedelta(days=1),
            recorded_at=obs_mic.recorded_at + timedelta(days=1),
            modality="transcription_text",
        )
        assert replay.object_id == obs_mic.object_id
        replay_report = feeder.measure_storage_capacity(subject_id)
        assert replay_report.total_observations == 5
        assert replay_report.total_commits == commits_before


def test_backfilled_history_defaults_knowledge_time_to_ingest_time():
    with tempfile.TemporaryDirectory() as tmp_dir:
        feeder = MassiveLifeStoreFeeder(
            MassiveLifeStoreFeeder.resolve_subject_store_path(tmp_dir, "P-BACKFILL")
        )
        historical_occurrence = datetime(2020, 5, 1, 12, 0, tzinfo=UTC)
        obs = feeder.record_raw_observation(
            subject_id="P-BACKFILL",
            stream_kind=RawStreamKind.USER_CHAT,
            content="今天才告诉你：2020 年我和老王签过一份合同。",
            occurred_at=historical_occurrence,
            modality="dialogue_text",
        )
        assert obs.occurred.start == historical_occurrence
        assert obs.learned_at > historical_occurrence
        assert obs.recorded_at >= obs.learned_at
