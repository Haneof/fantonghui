"""测试海量人生底层基础数据直写入库与存储容量测算器 (tests/simulation/test_massive_life_store_feeder.py)."""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.contracts.enums import SourceClass
from aios_core.simulation.massive_life_store_feeder import (
    MassiveLifeStoreFeeder,
    RawStreamKind,
)

UTC = timezone.utc


def test_feeder_direct_sqlite_ingestion_and_capacity_measurement():
    with tempfile.TemporaryDirectory() as tmp_dir:
        subject_id = "P-TEST-001"
        db_path = MassiveLifeStoreFeeder.resolve_subject_store_path(tmp_dir, subject_id)
        feeder = MassiveLifeStoreFeeder(db_path)

        base_time = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)

        # 1. 模拟五大底层基础数据源
        # (1) 物理传感器 (SENSOR)
        obs_sensor = feeder.record_raw_observation(
            subject_id=subject_id,
            stream_kind=RawStreamKind.SENSOR,
            content={"heart_rate": 72, "steps": 1250, "sleep_stage": "deep_sleep"},
            occurred_at=base_time,
            modality="sensor_telemetry",
            source_class=SourceClass.SENSOR,
        )

        # (2) MIC 环境录音转文字 (MIC_TRANSCRIPTION)
        obs_mic = feeder.record_raw_observation(
            subject_id=subject_id,
            stream_kind=RawStreamKind.MIC_TRANSCRIPTION,
            content="地铁车厢报站声：下一站国贸，请下车的乘客提前做好准备。",
            occurred_at=base_time + timedelta(hours=1),
            modality="transcription_text",
            source_class=SourceClass.AI_COGNITION,
        )

        # (3) 环境照片转文本描述 (CAMERA_CAPTION)
        obs_cam = feeder.record_raw_observation(
            subject_id=subject_id,
            stream_kind=RawStreamKind.CAMERA_CAPTION,
            content="镜头拍摄：办公桌前堆满待审批的合同卷宗，左侧放着半杯已冷却的美式咖啡。",
            occurred_at=base_time + timedelta(hours=3),
            modality="caption_text",
            source_class=SourceClass.AI_COGNITION,
        )

        # (4) APP 真实数据 (APP_DATA: 消费、日程、社交等)
        obs_app = feeder.record_raw_observation(
            subject_id=subject_id,
            stream_kind=RawStreamKind.APP_DATA,
            content={
                "app": "Alipay",
                "type": "bill",
                "amount": 28.5,
                "merchant": "老王面馆",
                "time": "12:15",
            },
            occurred_at=base_time + timedelta(hours=4),
            modality="structured_json",
            source_class=SourceClass.AI_COGNITION,
        )

        # (5) 与用户的真实日常双向聊天 (USER_CHAT)
        obs_chat = feeder.record_raw_observation(
            subject_id=subject_id,
            stream_kind=RawStreamKind.USER_CHAT,
            content={
                "user_prompt": "今天开了一整天会，头疼得要命，晚上帮我把非紧急提醒全静音。",
                "ai_reply": "收到。已为您启用沉浸静音模式，仅保留家人来电与心率突增强提醒，好好休息。",
            },
            occurred_at=base_time + timedelta(hours=12),
            modality="dialogue_json",
            source_class=SourceClass.USER,
        )

        assert obs_sensor.object_id.startswith("obs_")
        assert obs_chat.source_kind == "user_chat"

        # 2. 测算 3 年存储容量报告
        report = feeder.measure_storage_capacity(subject_id)
        assert report.total_observations == 5
        assert report.total_commits >= 5
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

        # 3. 做题人日常事实切片提取验证
        daily_records = feeder.query_daily_observations(subject_id, "2024-01-01")
        assert len(daily_records) == 5
        assert any("美式咖啡" in str(r.get("value")) for r in daily_records)
        assert any("非紧急提醒全静音" in str(r.get("value")) for r in daily_records)
