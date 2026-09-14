"""M0-004 唯一时间轴、三类时间语义、跨时区规范化与 Knowledge Cutoff 冻结 + R1 DST fold"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from aios_core.contracts.time import (
    KnowledgeWindow,
    TemporalExtent,
    TimePrecision,
    as_utc,
    canonical_utc_iso,
    require_aware,
    require_timezone_name,
    utc_now,
)


# T01 TemporalExtent.point aware成功, naive失败
def test_t01_point_aware_success_naive_fail():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    extent = TemporalExtent.point(aware)
    assert extent.start == aware
    assert extent.end == aware

    naive = datetime(2026, 9, 14, 12, 0)
    with pytest.raises(ValueError):
        TemporalExtent.point(naive)


# T02 point start == end
def test_t02_point_start_eq_end():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    extent = TemporalExtent.point(aware, precision=TimePrecision.SECOND)
    assert extent.start == extent.end
    assert extent.start == aware


# T03 bounded interval 不同timezone但真实instant顺序正确
def test_t03_bounded_interval_different_timezone():
    start = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # 04:00 UTC
    end = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)  # 05:00 UTC
    extent = TemporalExtent(start=start, end=end, precision=TimePrecision.HOUR)
    assert extent.start == start
    assert extent.end == end
    assert as_utc(start, "start") < as_utc(end, "end")


# T04 open-start interval
def test_t04_open_start():
    end = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    extent = TemporalExtent(start=None, end=end, precision=TimePrecision.DAY)
    assert extent.start is None
    assert extent.end == end
    assert extent.unknown is False


# T05 open-end interval
def test_t05_open_end():
    start = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    extent = TemporalExtent(start=start, end=None, precision=TimePrecision.DAY)
    assert extent.start == start
    assert extent.end is None
    assert extent.unknown is False


# T06 explicit unknown
def test_t06_explicit_unknown():
    extent = TemporalExtent.unknown_time()
    assert extent.unknown is True
    assert extent.start is None
    assert extent.end is None
    assert extent.precision == TimePrecision.UNKNOWN


# T07 unknown=True同时有endpoint拒绝
def test_t07_unknown_with_endpoint_rejected():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        TemporalExtent(start=aware, end=None, unknown=True)
    with pytest.raises(ValueError):
        TemporalExtent(start=None, end=aware, unknown=True)
    with pytest.raises(ValueError):
        TemporalExtent(start=aware, end=aware, unknown=True)


# T08 unknown=True但precision=DAY拒绝
def test_t08_unknown_with_day_precision_rejected():
    with pytest.raises(ValueError):
        TemporalExtent(unknown=True, precision=TimePrecision.DAY)
    with pytest.raises(ValueError):
        TemporalExtent(unknown=True, precision=TimePrecision.HOUR, start=None, end=None)


# T09 start/end真实instant end < start 即使local clock看似更晚也拒绝 (不同时区)
def test_t09_end_before_start_real_instant_rejected():
    start = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)  # 06:00 UTC
    end = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # 12:00 +08 = 04:00 UTC
    with pytest.raises(ValueError):
        TemporalExtent(start=start, end=end)


# T10 两个不同时区表示同一instant start == end按真实时间相等允许
def test_t10_same_instant_different_timezone_allowed():
    start = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # 04:00 UTC
    end = datetime(2026, 9, 14, 4, 0, tzinfo=timezone.utc)  # 04:00 UTC same instant
    extent = TemporalExtent(start=start, end=end, precision=TimePrecision.SECOND)
    assert as_utc(extent.start, "start") == as_utc(extent.end, "end")


# T11 昨天发生、今天才知道
def test_t11_yesterday_occurred_today_learned():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import TemporalExtent

    yesterday = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    today = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    later_today = datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc)

    class TestObs(WorldObject):
        object_type: ObjectType = ObjectType.OBSERVATION
        subject_id: str = "user_1"
        value: str = "test"

    obj = TestObs(
        object_id="test_obj",
        revision=1,
        occurred=TemporalExtent.point(yesterday),
        learned_at=today,
        recorded_at=later_today,
        created_by="test",
        value="yesterday event",
    )
    assert obj.occurred.start == yesterday
    assert obj.learned_at == today
    assert obj.recorded_at == later_today
    assert obj.occurred.start != obj.learned_at
    assert obj.learned_at < obj.recorded_at


# T12 今天知道、明天才发生 (未来计划)
def test_t12_today_learned_tomorrow_occurred():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import TemporalExtent

    today = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    tomorrow = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)

    class TestEvent(WorldObject):
        object_type: ObjectType = ObjectType.EVENT
        subject_id: str = "test"
        title: str = "future"

    obj = TestEvent(
        object_id="future_event",
        revision=1,
        occurred=TemporalExtent.point(tomorrow),
        learned_at=today,
        recorded_at=today,
        created_by="test",
        title="tomorrow hospital",
    )
    assert obj.learned_at < obj.occurred.start


# T13 WorldObject naive learned_at拒绝
def test_t13_naive_learned_at_rejected():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import TemporalExtent

    class TestObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"

    naive = datetime(2026, 9, 14, 12, 0)
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        TestObj(
            object_id="test",
            revision=1,
            occurred=TemporalExtent.point(aware),
            learned_at=naive,
            recorded_at=aware,
            created_by="test",
        )


# T14 WorldObject naive recorded_at拒绝
def test_t14_naive_recorded_at_rejected():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import TemporalExtent

    class TestObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"

    naive = datetime(2026, 9, 14, 12, 0)
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        TestObj(
            object_id="test",
            revision=1,
            occurred=TemporalExtent.point(aware),
            learned_at=aware,
            recorded_at=naive,
            created_by="test",
        )


# T15 recorded_at < learned_at 拒绝
def test_t15_recorded_before_learned_rejected():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.time import TemporalExtent

    class TestObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test"

    learned = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    recorded = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        TestObj(
            object_id="test",
            revision=1,
            occurred=TemporalExtent.point(learned),
            learned_at=learned,
            recorded_at=recorded,
            created_by="test",
        )


# T16 KnowledgeWindow aware cutoff成功
def test_t16_knowledge_window_aware_success():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    window = KnowledgeWindow(knowledge_cutoff=aware, world_revision=1)
    assert window.knowledge_cutoff == aware
    assert window.world_revision == 1


# T17 naive knowledge_cutoff拒绝
def test_t17_knowledge_window_naive_rejected():
    naive = datetime(2026, 9, 14, 12, 0)
    with pytest.raises(ValueError):
        KnowledgeWindow(knowledge_cutoff=naive)


# T18 world_revision=-1拒绝, 0允许
def test_t18_world_revision_bounds():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(Exception):
        KnowledgeWindow(knowledge_cutoff=aware, world_revision=-1)

    window = KnowledgeWindow(knowledge_cutoff=aware, world_revision=0)
    assert window.world_revision == 0

    window2 = KnowledgeWindow(knowledge_cutoff=aware, world_revision=None)
    assert window2.world_revision is None


# T19 两个datetime不同时区同一instant canonical结果相同
def test_t19_canonical_same_instant_different_tz():
    dt_shanghai = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # 04:00 UTC
    dt_utc = datetime(2026, 9, 14, 4, 0, tzinfo=timezone.utc)  # 04:00 UTC

    canon_shanghai = canonical_utc_iso(dt_shanghai, "test")
    canon_utc = canonical_utc_iso(dt_utc, "test")

    assert canon_shanghai == canon_utc, f"{canon_shanghai} != {canon_utc}"


# T20 canonical结果必须以 +00:00 结尾并具有固定microseconds - 补强为明确值
def test_t20_canonical_format():
    dt = datetime(2026, 9, 14, 4, 0, tzinfo=timezone.utc)
    canon = canonical_utc_iso(dt, "test")
    # 固定microseconds冻结
    assert canon == "2026-09-14T04:00:00.000000+00:00"
    assert canon.endswith("+00:00")
    assert "T" in canon

    # 带实际microsecond
    dt2 = datetime(2026, 9, 14, 4, 0, 0, 123456, tzinfo=timezone.utc)
    canon2 = canonical_utc_iso(dt2, "test")
    assert canon2 == "2026-09-14T04:00:00.123456+00:00"


# T21 canonical_utc_iso naive拒绝
def test_t21_canonical_naive_rejected():
    naive = datetime(2026, 9, 14, 12, 0)
    with pytest.raises(ValueError):
        canonical_utc_iso(naive, "test")


# T22 Task timezone_name America/New_York 成功
def test_t22_task_timezone_ny():
    from aios_core.contracts.models import Task
    from aios_core.contracts.enums import TaskType
    from aios_core.contracts.time import utc_now

    now = utc_now()
    wake_at = datetime(2026, 9, 15, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    deadline = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)

    task = Task(
        object_id="tsk_test",
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        task_type=TaskType.TODO,
        title="test task",
        timezone_name="America/New_York",
        next_wake_at=wake_at,
        deadline=deadline,
    )
    assert task.timezone_name == "America/New_York"
    utc = task.next_wake_at.astimezone(timezone.utc)
    assert utc.tzinfo == timezone.utc


# T23 timezone_name Asia/Shanghai 成功
def test_t23_task_timezone_shanghai():
    from aios_core.contracts.models import Task
    from aios_core.contracts.enums import TaskType
    from aios_core.contracts.time import utc_now

    now = utc_now()
    wake_at = datetime(2026, 9, 15, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    task = Task(
        object_id="tsk_test2",
        subject_id="test_subject",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        task_type=TaskType.TODO,
        title="test",
        timezone_name="Asia/Shanghai",
        next_wake_at=wake_at,
    )
    assert task.timezone_name == "Asia/Shanghai"


# T24 timezone_name Mars/Base1 失败
def test_t24_task_timezone_invalid():
    from aios_core.contracts.models import Task
    from aios_core.contracts.enums import TaskType
    from aios_core.contracts.time import utc_now

    now = utc_now()
    wake_at = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        Task(
            object_id="tsk_invalid",
            subject_id="test_subject",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
            task_type=TaskType.TODO,
            title="test",
            timezone_name="Mars/Base1",
            next_wake_at=wake_at,
        )


# T25 naive next_wake_at 失败
def test_t25_task_naive_wake_rejected():
    from aios_core.contracts.models import Task
    from aios_core.contracts.enums import TaskType
    from aios_core.contracts.time import utc_now

    now = utc_now()
    naive_wake = datetime(2026, 9, 15, 9, 0)

    with pytest.raises(ValueError):
        Task(
            object_id="tsk_naive",
            subject_id="test_subject",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
            task_type=TaskType.TODO,
            title="test",
            next_wake_at=naive_wake,
        )


# T26 naive deadline 失败
def test_t26_task_naive_deadline_rejected():
    from aios_core.contracts.models import Task
    from aios_core.contracts.enums import TaskType
    from aios_core.contracts.time import utc_now

    now = utc_now()
    wake_at = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)
    naive_deadline = datetime(2026, 9, 16, 9, 0)

    with pytest.raises(ValueError):
        Task(
            object_id="tsk_naive_deadline",
            subject_id="test_subject",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
            task_type=TaskType.TODO,
            title="test",
            next_wake_at=wake_at,
            deadline=naive_deadline,
        )


# T27 Future knowledge leakage 数据库测试 - 核心验收
def test_t27_future_knowledge_leakage(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import utc_now
    import uuid

    def DummyObj(**kwargs):
        from aios_core.contracts import Observation
        return Observation(subject_id="test_leak", source_kind="test", modality="json",
                           **kwargs)

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    learned_rev1 = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    learned_rev2 = datetime(2026, 9, 14, 2, 0, tzinfo=timezone(timedelta(hours=-4)))

    obj1 = DummyObj(
        object_id="leak_obj",
        revision=1,
        learned_at=learned_rev1,
        recorded_at=learned_rev1,
        created_by="test",
        value="known_before_cutoff",
    )
    op1 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj1], op1)

    obj2 = DummyObj(
        object_id="leak_obj",
        revision=2,
        learned_at=learned_rev2,
        recorded_at=learned_rev2,
        created_by="test",
        value="future_secret",
    )
    op2 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=1,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj2], op2)

    cutoff = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)

    payload = store.get_payload("leak_obj", knowledge_cutoff=cutoff)
    assert payload["value"] == "known_before_cutoff"
    assert payload["value"] != "future_secret"
    assert payload is not None


# T28 list_payloads 也必须验证跨时区cutoff
def test_t28_list_payloads_cross_timezone(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    import uuid
    from datetime import timezone, timedelta

    def DummyObj(**kwargs):
        from aios_core.contracts import Observation
        return Observation(subject_id="test_list", source_kind="test", modality="json",
                           **kwargs)

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    learned_rev1 = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    learned_rev2 = datetime(2026, 9, 14, 2, 0, tzinfo=timezone(timedelta(hours=-4)))

    obj1 = DummyObj(
        object_id="list_obj",
        revision=1,
        learned_at=learned_rev1,
        recorded_at=learned_rev1,
        created_by="test",
        value="known_before_cutoff",
    )
    op1 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj1], op1)

    obj2 = DummyObj(
        object_id="list_obj",
        revision=2,
        learned_at=learned_rev2,
        recorded_at=learned_rev2,
        created_by="test",
        value="future_secret",
    )
    op2 = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=1,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj2], op2)

    cutoff = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)
    payloads = store.list_payloads(knowledge_cutoff=cutoff)
    assert len(payloads) == 1
    assert payloads[0]["value"] == "known_before_cutoff"


# T29 naive数据库cutoff必须拒绝 get_payload
def test_t29_naive_cutoff_get_payload_rejected(tmp_path):
    from aios_core.storage.sqlite_store import SQLiteWorldStore

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    naive_cutoff = datetime(2026, 9, 14, 12, 0)

    with pytest.raises(ValueError):
        store.get_payload("any_obj", knowledge_cutoff=naive_cutoff)


# T30 naive cutoff list_payloads 也必须失败
def test_t30_naive_cutoff_list_payloads_rejected(tmp_path):
    from aios_core.storage.sqlite_store import SQLiteWorldStore

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)
    naive_cutoff = datetime(2026, 9, 14, 12, 0)

    with pytest.raises(ValueError):
        store.list_payloads(knowledge_cutoff=naive_cutoff)


# T31 TemporalExtent timezone_name Asia/Shanghai 成功
def test_t31_temporal_extent_timezone_shanghai():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    extent = TemporalExtent(
        start=aware, end=aware, timezone_name="Asia/Shanghai", precision=TimePrecision.SECOND
    )
    assert extent.timezone_name == "Asia/Shanghai"


# T32 timezone_name America/New_York 成功
def test_t32_temporal_extent_timezone_ny():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    extent = TemporalExtent(
        start=aware, end=aware, timezone_name="America/New_York", precision=TimePrecision.HOUR
    )
    assert extent.timezone_name == "America/New_York"


# T33 timezone_name invalid/timezone/AIOS 失败
def test_t33_temporal_extent_timezone_invalid():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        TemporalExtent(
            start=aware, end=aware, timezone_name="invalid/timezone/AIOS", precision=TimePrecision.SECOND
        )


# T34 timezone_name "" 失败, None 合法
def test_t34_temporal_extent_timezone_empty_and_none():
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        TemporalExtent(start=aware, end=aware, timezone_name="", precision=TimePrecision.SECOND)

    extent_none = TemporalExtent(start=aware, end=aware, timezone_name=None, precision=TimePrecision.SECOND)
    assert extent_none.timezone_name is None


# 额外：不得混淆event time与knowledge time
def test_knowledge_cutoff_uses_learned_at_not_occurred(tmp_path):
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType
    from aios_core.contracts.operations import OperationRequest
    from aios_core.storage.sqlite_store import SQLiteWorldStore
    from aios_core.contracts.time import TemporalExtent
    import uuid

    def DummyObj(**kwargs):
        from aios_core.contracts import Observation
        return Observation(subject_id="test_knowledge", source_kind="test", modality="json",
                           **kwargs)

    db = tmp_path / "test.db"
    store = SQLiteWorldStore(db)

    occurred_2020 = datetime(2020, 1, 1, 10, 0, tzinfo=timezone.utc)
    learned_2026 = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    cutoff_2025 = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

    obj = DummyObj(
        object_id="knowledge_test_obj",
        revision=1,
        occurred=TemporalExtent.point(occurred_2020),
        learned_at=learned_2026,
        recorded_at=learned_2026,
        created_by="test",
        value="old event but learned late",
    )
    op = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test",
        arguments={},
        expected_world_revision=0,
        reason="test",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obj], op)

    from aios_core.storage.sqlite_store import StoreError
    from aios_core.contracts.enums import ErrorCode

    try:
        payload = store.get_payload("knowledge_test_obj", knowledge_cutoff=cutoff_2025)
        pytest.fail(f"Should not be visible: occurred {occurred_2020} < cutoff {cutoff_2025} but learned {learned_2026} > cutoff, should be hidden. Got {payload}")
    except StoreError as e:
        assert e.code == ErrorCode.NOT_FOUND

    payloads = store.list_payloads(knowledge_cutoff=cutoff_2025)
    assert len(payloads) == 0


# D01 DST fold: start fold=1 (06:30 UTC) end fold=0 (05:45 UTC) 本地墙钟 01:45 > 01:30 但真实 05:45 < 06:30 必须拒绝
def test_d01_temporal_extent_dst_fold_end_before_start_rejected():
    ny = ZoneInfo("America/New_York")
    # 2026-11-01 是DST回拨日，America/New_York 02:00 -> 01:00
    start = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=1)  # 06:30 UTC
    end = datetime(2026, 11, 1, 1, 45, tzinfo=ny, fold=0)    # 05:45 UTC

    # 显式验证真实instant顺序
    assert as_utc(end, "end") < as_utc(start, "start"), f"{as_utc(end,'end')} should < {as_utc(start,'start')}"
    # 本地墙钟看起来 end > start
    # 但真实instant end < start，必须拒绝
    with pytest.raises(ValueError):
        TemporalExtent(start=start, end=end, precision=TimePrecision.MINUTE)


# D02 DST fold 反向: start fold=0 (05:30 UTC) end fold=1 (06:15 UTC) 墙钟 01:15 < 01:30 但真实 06:15 > 05:30 必须允许
def test_d02_temporal_extent_dst_fold_wall_clock_less_but_instant_greater_allowed():
    ny = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=0)  # 05:30 UTC
    end = datetime(2026, 11, 1, 1, 15, tzinfo=ny, fold=1)    # 06:15 UTC

    assert as_utc(end, "end") > as_utc(start, "start")
    # 墙钟 end 01:15 < start 01:30，但真实 instant 06:15 > 05:30，应允许
    extent = TemporalExtent(start=start, end=end, precision=TimePrecision.MINUTE)
    assert extent.start == start
    assert extent.end == end


# D03 WorldObject DST: learned fold=0 05:30 UTC, recorded fold=1 06:15 UTC，本地 recorded 01:15 < learned 01:30 但真实 recorded > learned 必须合法
def test_d03_worldobject_dst_recorded_wall_less_but_instant_greater_allowed():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType

    ny = ZoneInfo("America/New_York")

    learned = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=0)  # 05:30 UTC
    recorded = datetime(2026, 11, 1, 1, 15, tzinfo=ny, fold=1)  # 06:15 UTC

    assert as_utc(recorded, "recorded_at") > as_utc(learned, "learned_at")

    class TestObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test_dst"

    obj = TestObj(
        object_id="dst_obj",
        revision=1,
        learned_at=learned,
        recorded_at=recorded,
        created_by="test",
    )
    assert obj.learned_at == learned
    assert obj.recorded_at == recorded


# D04 WorldObject DST: learned fold=1 06:30 UTC, recorded fold=0 05:45 UTC，本地 recorded 01:45 > learned 01:30 但真实 recorded < learned 必须拒绝
def test_d04_worldobject_dst_recorded_wall_greater_but_instant_less_rejected():
    from aios_core.contracts.base import WorldObject
    from aios_core.contracts.enums import ObjectType

    ny = ZoneInfo("America/New_York")

    learned = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=1)  # 06:30 UTC
    recorded = datetime(2026, 11, 1, 1, 45, tzinfo=ny, fold=0)  # 05:45 UTC

    assert as_utc(recorded, "recorded_at") < as_utc(learned, "learned_at")

    class TestObj(WorldObject):
        object_type: ObjectType = ObjectType.ENTITY
        subject_id: str = "test_dst"

    with pytest.raises(ValueError):
        TestObj(
            object_id="dst_obj2",
            revision=1,
            learned_at=learned,
            recorded_at=recorded,
            created_by="test",
        )

# D05 Wake DST false-reject protection
def test_d05_wake_dst_wall_less_but_instant_greater_allowed():
    from aios_core.contracts.models import Wake
    from aios_core.contracts.enums import WakeSource
    from aios_core.contracts.time import utc_now

    ny = ZoneInfo("America/New_York")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=0)  # 05:30 UTC
    last = datetime(2026, 11, 1, 1, 15, tzinfo=ny, fold=1)   # 06:15 UTC

    assert as_utc(last, "last_hit_at") > as_utc(first, "first_hit_at")

    now = utc_now()
    wake = Wake(
        object_id="wake_dst_05",
        subject_id="test_wake",
        revision=1,
        learned_at=now,
        recorded_at=now,
        created_by="test",
        wake_source=WakeSource.TASK_DUE,
        first_hit_at=first,
        last_hit_at=last,
    )
    assert wake.first_hit_at == first
    assert wake.last_hit_at == last


# D06 Wake DST false-accept protection
def test_d06_wake_dst_wall_greater_but_instant_less_rejected():
    from aios_core.contracts.models import Wake
    from aios_core.contracts.enums import WakeSource
    from aios_core.contracts.time import utc_now

    ny = ZoneInfo("America/New_York")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=1)  # 06:30 UTC
    last = datetime(2026, 11, 1, 1, 45, tzinfo=ny, fold=0)   # 05:45 UTC

    assert as_utc(last, "last_hit_at") < as_utc(first, "first_hit_at")

    now = utc_now()
    with pytest.raises(ValueError):
        Wake(
            object_id="wake_dst_06",
            subject_id="test_wake",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
            wake_source=WakeSource.TASK_DUE,
            first_hit_at=first,
            last_hit_at=last,
        )


# Wake naive first_hit_at reject
def test_wake_naive_first_hit_rejected():
    from aios_core.contracts.models import Wake
    from aios_core.contracts.enums import WakeSource
    from aios_core.contracts.time import utc_now

    now = utc_now()
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 14, 12, 0)

    with pytest.raises(ValueError):
        Wake(
            object_id="wake_naive_1",
            subject_id="test_wake",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
            wake_source=WakeSource.TASK_DUE,
            first_hit_at=naive,
            last_hit_at=aware,
        )


# Wake naive last_hit_at reject
def test_wake_naive_last_hit_rejected():
    from aios_core.contracts.models import Wake
    from aios_core.contracts.enums import WakeSource
    from aios_core.contracts.time import utc_now

    now = utc_now()
    aware = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 14, 12, 0)

    with pytest.raises(ValueError):
        Wake(
            object_id="wake_naive_2",
            subject_id="test_wake",
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="test",
            wake_source=WakeSource.TASK_DUE,
            first_hit_at=aware,
            last_hit_at=naive,
        )
