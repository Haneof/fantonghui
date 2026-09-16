"""M1-018 认知反向传播语义图层契约与回溯标注引擎（王建国案）单测.

覆盖宪法第九十三条与老大最高指示的三条铁律：
1. 历史原始事实的 SHA-256 在挂载图层前后 100% 不变（含 SQLite 行字节级复核，
   以及升级版工单要求的万条级高密度事实逐条比对）；
2. 带 ``as_of_cutoff`` 的历史查询绝对不泄露今天才学到的新认知；
3. 严禁任何级联递归重算历史（严格单跳、有界链条、派生重算恒为 0，
   以及升级版工单要求的 5 层 10/200/1000 依赖拓扑单跳隔离）。

并存说明：战队已合入基线 ``world/retrospective_annotation.py`` 的 25 项测试保持原样，
本文件只测本线独立落盘的 ``world/epistemic_world_lens.py``。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    Claim,
    Dependency,
    Entity,
    EventAnchor,
    ObjectRef,
    ObjectType,
    Observation,
    OperationRequest,
    Summary,
    TemporalExtent,
)
from aios_core.contracts.enums import ClaimType, ErrorCode, KnowledgeState
from aios_core.query import HistoricalWorldQuery
from aios_core.storage import SQLiteWorldStore
from aios_core.world.epistemic_world_lens import (
    MAX_DIAGNOSTIC_DEPTH,
    MAX_OVERLAY_HOPS,
    MAX_SUPERSEDE_CHAIN_DEPTH,
    AnnotationTargetNotFound,
    BiTemporalEpistemicLens,
    EpistemicWorldLens,
    HistoricalEpistemicSlice,
    HistoryImmutabilityViolation,
    OverlayCascadeForbidden,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationError,
    SingleHopCascadeIsolator,
    SingleHopInvalidationReport,
    annotation_sha256,
    coerce_annotation,
    coerce_world_object,
    fact_sha256,
    new_annotation_id,
    normalize_dependency_graph,
)

# --- 老王案时间轴 -----------------------------------------------------------
# 两年前：与老王合伙、喝酒聊天、当时的心率（原始客观事实，永不可改）
T_PARTNERSHIP = datetime(2024, 3, 1, 19, 30, tzinfo=timezone.utc)
T_PARTNERSHIP_END = datetime(2024, 3, 1, 22, 0, tzinfo=timezone.utc)
# 当时的认知截止点（“两年前那个晚上之后不久”）
T_CUTOFF_THEN = T_PARTNERSHIP_END + timedelta(hours=2)
# 今天：用户指认老王是骗子（T_now 新认知）
T_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)

USER = "user_1"
LAOWANG = "ent_laowang"
CHAT_TEXT = "老王：兄弟，合伙稳赚不赔，钱打我卡上就行"
STATEMENT_ID = "clm_today_laowang_is_fraud"
OVERLAY = "疑似欺诈"


def chat_log(*, learned_at: datetime = T_PARTNERSHIP) -> Observation:
    return Observation(
        object_id="obs_chat_laowang_partnership",
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent.point(T_PARTNERSHIP),
        learned_at=learned_at,
        recorded_at=learned_at,
        created_by="m1-018-test",
        source_kind="chat_export",
        modality="text",
        value={"text": CHAT_TEXT, "channel": "wechat"},
        metadata={"entity_id": LAOWANG},
    )


def heart_rate() -> Observation:
    return Observation(
        object_id="obs_hr_dinner_with_laowang",
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent(
            start=T_PARTNERSHIP,
            end=T_PARTNERSHIP_END,
        ),
        learned_at=T_PARTNERSHIP,
        recorded_at=T_PARTNERSHIP,
        created_by="m1-018-test",
        source_kind="wristband_sensor",
        modality="numeric",
        value={"heart_rate_bpm": 88, "mood": "放松"},
        unit="bpm",
        metadata={"entity_id": LAOWANG},
    )


def partnership_event() -> EventAnchor:
    return EventAnchor(
        object_id="evt_partnership_with_laowang",
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent(start=T_PARTNERSHIP, end=T_PARTNERSHIP_END),
        learned_at=T_PARTNERSHIP,
        recorded_at=T_PARTNERSHIP,
        created_by="m1-018-test",
        title="与老王合伙吃饭并达成口头合伙意向",
        interpretation="当时判断老王是值得信任的合伙人",
        event_time=TemporalExtent(start=T_PARTNERSHIP, end=T_PARTNERSHIP_END),
        participant_refs=[ObjectRef(object_id=LAOWANG, revision=1)],
        confidence=0.82,
        metadata={"entity_id": LAOWANG},
    )


def weekly_summary_then() -> Summary:
    """两年前的历史周总结：忠实记录“当时信任老王”的人生原貌。"""

    return Summary(
        object_id="sum_week_2024w09_social",
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent(start=T_PARTNERSHIP, end=T_PARTNERSHIP_END),
        learned_at=T_PARTNERSHIP_END,
        recorded_at=T_PARTNERSHIP_END,
        created_by="m1-018-test",
        summary_time=TemporalExtent(
            start=datetime(2024, 2, 26, tzinfo=timezone.utc),
            end=datetime(2024, 3, 3, tzinfo=timezone.utc),
        ),
        granularity="week",
        source_world_revision=7,
        coverage={"social": "本周与老王确定合伙意向，关系升温"},
        metadata={"entity_id": LAOWANG},
    )


def police_report_learned_today() -> Observation:
    """今天才拿到的、关于两年前那顿饭的新证据（同样受 cutoff 屏蔽）。"""

    return Observation(
        object_id="obs_police_report_laowang",
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent.point(T_PARTNERSHIP),
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="m1-018-test",
        source_kind="police_report",
        modality="text",
        value={"text": "警方通报：老王涉嫌合同诈骗，两年前那笔合伙款被转移"},
        metadata={"entity_id": LAOWANG},
    )


def fraud_annotation(
    *,
    annotation_id: str | None = None,
    overlay: str = OVERLAY,
    learned_at: datetime = T_NOW,
    supersedes_annotation_id: str | None = None,
    target_entity_id: str = LAOWANG,
    target_start: datetime = T_PARTNERSHIP,
    target_end: datetime = T_PARTNERSHIP_END,
) -> RetrospectiveAnnotation:
    return RetrospectiveAnnotation(
        annotation_id=annotation_id or new_annotation_id(),
        target_entity_id=target_entity_id,
        semantic_overlay=overlay,
        target_time_start=target_start,
        target_time_end=target_end,
        learned_at=learned_at,
        source_statement_ref=STATEMENT_ID,
        confidence=0.95,
        supersedes_annotation_id=supersedes_annotation_id,
    )


def laowang_lens() -> EpistemicWorldLens:
    """装载两年前全部历史事实的双时间透镜（不含任何今天的新认知）。"""

    lens = EpistemicWorldLens()
    anchors = lens.register_facts(
        [chat_log(), heart_rate(), partnership_event(), weekly_summary_then()]
    )
    assert len(anchors) == 4
    assert {anchor.entity_id for anchor in anchors} == {LAOWANG}
    return lens


def raw_durable_rows(db_path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT object_id, revision, world_revision, learned_at, recorded_at,
                   payload_json
            FROM object_revisions
            ORDER BY object_id ASC, revision ASC
            """
        ).fetchall()
    finally:
        conn.close()


def dumped(view: dict) -> str:
    return json.dumps(view, ensure_ascii=False, sort_keys=True)


def commit(store: SQLiteWorldStore, objects, expected: int, key: str) -> None:
    store.commit(
        objects,
        OperationRequest(
            operation_name="world.commit",
            expected_world_revision=expected,
            reason="M1-018 老王案双时间视图测试",
            idempotency_key=key,
        ),
    )


def seeded_store(tmp_path) -> SQLiteWorldStore:
    """把两年前的原始事实真实落盘（append-only），返回已就绪的存储。"""

    store = SQLiteWorldStore(tmp_path / "world.db")
    entity = Entity(
        object_id=LAOWANG,
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent.point(T_PARTNERSHIP),
        learned_at=T_PARTNERSHIP,
        recorded_at=T_PARTNERSHIP,
        created_by="m1-018-test",
        entity_kind="person",
        canonical_name="老王",
    )
    commit(store, [entity, chat_log(), heart_rate()], 0, "m1-018-seed")
    return store


# --- ra01 数据契约：冻结、只向前、指针语义 ----------------------------------


def test_ra01_annotation_contract_is_frozen_forward_only_and_bi_temporal():
    annotation = fraud_annotation()

    # learned_at == recorded_at == T_now（今天）
    assert annotation.learned_at == T_NOW
    assert annotation.recorded_at == annotation.learned_at
    # 指针指向两年前的时间切片
    assert annotation.target_time_range.start == T_PARTNERSHIP
    assert annotation.target_time_range.end == T_PARTNERSHIP_END
    assert annotation.source_statement_ref == STATEMENT_ID

    # 冻结契约：任何就地改写都被拒绝
    with pytest.raises(ValidationError):
        annotation.semantic_overlay = "可信合伙人"
    with pytest.raises(ValidationError):
        annotation.target_time_start = T_NOW

    # 额外字段一律拒绝
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation.model_validate(
            {
                **annotation.model_dump(),
                "rewrite_history": True,
            }
        )


def test_ra02_writing_cognition_backwards_into_history_is_rejected():
    # 铁律：新认知只能写在事实之后（今天），严禁 learned_at 倒写到两年前
    with pytest.raises(ValidationError) as excinfo:
        fraud_annotation(learned_at=T_PARTNERSHIP - timedelta(days=1))
    assert "forward in time" in str(excinfo.value)

    # 目标窗口自身倒置同样拒绝
    with pytest.raises(ValidationError):
        fraud_annotation(target_start=T_PARTNERSHIP_END, target_end=T_PARTNERSHIP)

    # naive 时间戳拒绝（双时间轴必须可比较）
    with pytest.raises(ValidationError):
        fraud_annotation(learned_at=datetime(2026, 9, 15, 9, 0))

    # recorded_at 早于 learned_at 拒绝
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(
            annotation_id=new_annotation_id(),
            target_entity_id=LAOWANG,
            semantic_overlay=OVERLAY,
            target_time_start=T_PARTNERSHIP,
            target_time_end=T_PARTNERSHIP_END,
            learned_at=T_NOW,
            recorded_at=T_NOW - timedelta(hours=1),
            source_statement_ref=STATEMENT_ID,
        )

    # 自指 supersede 拒绝
    with pytest.raises(ValidationError):
        fraud_annotation(
            annotation_id="ran_self",
            supersedes_annotation_id="ran_self",
        )


def test_ra03_overlay_pointer_covers_and_intersects_the_past_slice_only():
    annotation = fraud_annotation()

    assert annotation.covers(T_PARTNERSHIP)
    assert annotation.covers(T_PARTNERSHIP_END)
    assert annotation.covers(T_PARTNERSHIP + timedelta(minutes=30))
    assert not annotation.covers(T_PARTNERSHIP - timedelta(seconds=1))
    assert not annotation.covers(T_NOW)

    assert annotation.intersects(T_PARTNERSHIP, T_PARTNERSHIP_END)
    assert annotation.intersects(T_PARTNERSHIP_END, T_NOW)
    assert not annotation.intersects(T_NOW - timedelta(days=1), T_NOW)


# --- ra04 原始事实哈希在挂载前后 100% 不变 ----------------------------------


def test_ra04_raw_fact_sha256_is_identical_before_and_after_annotation_attach():
    observation = chat_log()
    hr = heart_rate()
    event = partnership_event()
    digest_before = {
        obj.object_id: fact_sha256(obj) for obj in (observation, hr, event)
    }
    payload_before = {
        obj.object_id: json.dumps(
            obj.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        )
        for obj in (observation, hr, event)
    }

    lens = EpistemicWorldLens([observation, hr, event])
    digest_registered = {
        anchor.object_id: anchor.payload_sha256 for anchor in lens.fact_anchors(LAOWANG)
    }
    assert digest_registered == digest_before

    receipt = lens.attach_annotation(fraud_annotation())

    # 挂载之后：活对象、锚点指纹、查询返回的 payload 三者哈希完全一致
    assert {obj.object_id: fact_sha256(obj) for obj in (observation, hr, event)} == (
        digest_before
    )
    assert {
        anchor.object_id: anchor.payload_sha256 for anchor in lens.fact_anchors(LAOWANG)
    } == digest_before
    assert receipt.history_rewrites == 0
    assert receipt.derived_recomputations == 0
    assert receipt.overlay_hops == MAX_OVERLAY_HOPS
    assert receipt.anchored_fact_count == 3
    assert receipt.anchored_fact_sha256 == {
        f"{object_id}@1": digest for object_id, digest in digest_before.items()
    }

    view = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    assert {fact["object_id"]: fact["payload_sha256"] for fact in view["facts"]} == (
        digest_before
    )
    assert {
        fact["object_id"]: json.dumps(fact["payload"], ensure_ascii=False, sort_keys=True)
        for fact in view["facts"]
    } == payload_before
    assert view["integrity"]["verified"] is True
    assert view["integrity"]["algorithm"] == "sha256"
    assert view["integrity"]["tampered"] == []

    # 原始对象自身也没有被引擎碰过一个字段
    assert observation.value["text"] == CHAT_TEXT
    assert observation.learned_at == T_PARTNERSHIP
    assert observation.revision == 1


def test_ra05_durable_sqlite_rows_are_never_updated_or_deleted_by_overlay(tmp_path):
    store = seeded_store(tmp_path)
    rows_before = raw_durable_rows(tmp_path / "world.db")
    bytes_before = {
        (row[0], row[1]): hashlib.sha256(row[5].encode("utf-8")).hexdigest()
        for row in rows_before
    }
    world_revision_before = store.current_world_revision()

    lens = EpistemicWorldLens.from_historical_query(
        HistoricalWorldQuery(store),
        entity_ids=LAOWANG,
        object_type=ObjectType.OBSERVATION,
    )
    lens.attach_annotation(fraud_annotation())
    lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    lens.query_historical_slice(LAOWANG, T_PARTNERSHIP, as_of_cutoff=T_CUTOFF_THEN)

    # 挂载/查询之后：SQLite 行数、内容、字节哈希、世界版本号全部原封不动
    rows_after = raw_durable_rows(tmp_path / "world.db")
    assert rows_after == rows_before
    assert {
        (row[0], row[1]): hashlib.sha256(row[5].encode("utf-8")).hexdigest()
        for row in rows_after
    } == bytes_before
    assert store.current_world_revision() == world_revision_before

    # 透镜登记的指纹就是持久化 payload_json 的行字节指纹
    for anchor in lens.fact_anchors(LAOWANG):
        assert anchor.payload_sha256 == bytes_before[(anchor.object_id, anchor.revision)]


# --- ra06 双时间透镜：两年前原貌 vs 今天的警示图层 ---------------------------


def test_ra06_as_of_cutoff_two_years_ago_reproduces_the_original_life():
    lens = laowang_lens()
    lens.attach_annotation(fraud_annotation())

    view = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP,
        as_of_cutoff=T_CUTOFF_THEN,
    )

    assert view["view_mode"] == "as_of_cutoff"
    assert view["as_of_cutoff"] == T_CUTOFF_THEN.isoformat().replace("+00:00", "Z")
    # 当时已知：聊天记录、心率、合伙事件、当周总结全部忠实重现
    assert {fact["object_id"] for fact in view["facts"]} == {
        "obs_chat_laowang_partnership",
        "obs_hr_dinner_with_laowang",
        "evt_partnership_with_laowang",
        "sum_week_2024w09_social",
    }
    chat_view = next(
        fact
        for fact in view["facts"]
        if fact["object_id"] == "obs_chat_laowang_partnership"
    )
    assert chat_view["payload"]["value"]["text"] == CHAT_TEXT
    # 当时没有任何“骗子”认知：图层、标签、溯源全部不可见
    assert view["overlays"] == []
    assert view["overlay_labels"] == []
    assert view["coverage"]["hidden_by_cutoff_overlays"] == 1
    assert view["coverage"]["returned_overlays"] == 0
    assert view["coverage"]["returned_facts"] == 4

    serialized = dumped(view)
    for forbidden in (OVERLAY, "骗子", "诈骗", STATEMENT_ID, "ran_"):
        assert forbidden not in serialized

    # 点状事实只属于它自己的时刻：饭局结束后的瞬间不再返回 19:30 的那条聊天原文
    later = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP + timedelta(minutes=30),
        as_of_cutoff=T_CUTOFF_THEN,
    )
    assert "obs_chat_laowang_partnership" not in {
        fact["object_id"] for fact in later["facts"]
    }
    assert "obs_hr_dinner_with_laowang" in {
        fact["object_id"] for fact in later["facts"]
    }


def test_ra07_current_view_renders_overlay_on_top_of_untouched_history():
    lens = laowang_lens()
    annotation = fraud_annotation()
    lens.attach_annotation(annotation)

    historical = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP + timedelta(minutes=30),
        as_of_cutoff=T_CUTOFF_THEN,
    )
    current = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP + timedelta(minutes=30),
    )

    assert current["view_mode"] == "current_cognition"
    assert current["as_of_cutoff"] is None
    assert current["overlay_labels"] == [OVERLAY]
    assert len(current["overlays"]) == 1
    overlay = current["overlays"][0]
    assert overlay["semantic_overlay"] == OVERLAY
    assert overlay["status"] == "active"
    assert overlay["learned_at"] == T_NOW.isoformat().replace("+00:00", "Z")
    assert overlay["source_evidence_ref"] == STATEMENT_ID
    assert overlay["annotation_id"] == annotation.annotation_id
    assert overlay["annotation_sha256"] == annotation_sha256(annotation)

    # 历史曲线原貌不受任何破坏：两种视图的事实 payload 与哈希逐字节相同
    assert [fact["payload_sha256"] for fact in current["facts"]] == [
        fact["payload_sha256"] for fact in historical["facts"]
    ]
    assert [fact["payload"] for fact in current["facts"]] == [
        fact["payload"] for fact in historical["facts"]
    ]
    assert current["coverage"]["hidden_by_cutoff_overlays"] == 0


def test_ra08_cutoff_also_hides_new_facts_learned_today_about_the_past():
    lens = laowang_lens()
    lens.register_fact(police_report_learned_today())
    lens.attach_annotation(fraud_annotation())

    historical = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP,
        as_of_cutoff=T_CUTOFF_THEN,
    )
    current = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)

    assert historical["coverage"]["hidden_by_cutoff_facts"] == 1
    assert "obs_police_report_laowang" not in {
        fact["object_id"] for fact in historical["facts"]
    }
    assert "诈骗" not in dumped(historical)

    assert "obs_police_report_laowang" in {
        fact["object_id"] for fact in current["facts"]
    }
    assert current["coverage"]["hidden_by_cutoff_facts"] == 0


def test_ra09_slice_outside_the_overlay_window_stays_clean():
    lens = laowang_lens()
    lens.attach_annotation(fraud_annotation())

    elsewhere = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP - timedelta(days=30),
    )
    assert elsewhere["overlays"] == []
    assert elsewhere["overlay_labels"] == []
    assert elsewhere["facts"] == []

    # 其他实体不受影响（图层只挂在自己的指针窗口上）
    stranger = lens.query_historical_slice("ent_laoli", T_PARTNERSHIP)
    assert stranger["overlays"] == []
    assert stranger["facts"] == []


# --- ra10 严禁级联递归重算历史 ----------------------------------------------


def test_ra10_attaching_overlay_never_recomputes_or_rewrites_history():
    lens = laowang_lens()
    summary_digest_before = next(
        anchor.payload_sha256
        for anchor in lens.fact_anchors(LAOWANG)
        if anchor.object_id == "sum_week_2024w09_social"
    )
    summary_payload_before = next(
        anchor.payload
        for anchor in lens.fact_anchors(LAOWANG)
        if anchor.object_id == "sum_week_2024w09_social"
    )

    for index in range(5):
        lens.attach_annotation(
            fraud_annotation(
                overlay=f"疑似欺诈-线索{index}",
                learned_at=T_NOW + timedelta(minutes=index),
            )
        )
        lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)

    audit = lens.recompute_audit()
    assert audit.history_rewrites == 0
    assert audit.derived_recomputations == 0
    assert audit.max_recursion_depth == 0
    assert audit.max_overlay_hops == MAX_OVERLAY_HOPS == 1
    assert audit.annotations_attached == 5
    assert audit.slice_queries == 5
    assert audit.history_rewrite_attempts_blocked == 0
    assert audit.cascade_attempts_blocked == 0

    # 两年前的历史周总结没有被翻遍重算，字节与指纹原封不动
    summary_anchor = next(
        anchor
        for anchor in lens.fact_anchors(LAOWANG)
        if anchor.object_id == "sum_week_2024w09_social"
    )
    assert summary_anchor.payload_sha256 == summary_digest_before
    assert summary_anchor.payload == summary_payload_before
    assert "疑似欺诈" not in json.dumps(summary_anchor.payload, ensure_ascii=False)

    view = lens.query_slice_view(LAOWANG, T_PARTNERSHIP)
    assert view.recompute_audit.history_rewrites == 0
    assert view.recompute_audit.derived_recomputations == 0


def test_ra11_overlay_work_is_bounded_to_the_pointed_slice():
    lens = laowang_lens()
    # 目标窗口之外的历史长尾（两年间的其他事实）绝不被卷入本次挂载
    for day in range(1, 60):
        moment = T_PARTNERSHIP + timedelta(days=day * 7)
        lens.register_fact(
            Observation(
                object_id=f"obs_tail_{day}",
                subject_id=USER,
                revision=1,
                occurred=TemporalExtent.point(moment),
                learned_at=moment,
                recorded_at=moment,
                created_by="m1-018-test",
                source_kind="chat_export",
                modality="text",
                value={"text": f"日常闲聊 {day}"},
                metadata={"entity_id": LAOWANG},
            )
        )

    receipt = lens.attach_annotation(fraud_annotation())

    assert receipt.anchored_fact_count == 4
    assert set(receipt.anchored_fact_sha256) == {
        "obs_chat_laowang_partnership@1",
        "obs_hr_dinner_with_laowang@1",
        "evt_partnership_with_laowang@1",
        "sum_week_2024w09_social@1",
    }
    assert lens.recompute_audit().facts_registered == 63
    assert lens.recompute_audit().derived_recomputations == 0


def test_ra12_overlay_on_top_of_overlay_is_forbidden_single_hop():
    lens = laowang_lens()
    annotation = fraud_annotation()
    lens.attach_annotation(annotation)

    # 图层叠图层（把 annotation_id 当作实体再挂一层）→ 严格单跳拒绝
    with pytest.raises(OverlayCascadeForbidden) as excinfo:
        lens.attach_annotation(
            fraud_annotation(target_entity_id=annotation.annotation_id)
        )
    assert excinfo.value.code == ErrorCode.INVALID_ARGUMENT
    assert excinfo.value.context["reason"] == "overlay_of_overlay_forbidden"
    assert excinfo.value.context["max_overlay_hops"] == MAX_OVERLAY_HOPS
    assert lens.recompute_audit().cascade_attempts_blocked == 1
    # 被拒绝的挂载没有污染认知账本
    assert len(lens.annotations) == 1
    assert len(lens.attachments) == 1


def test_ra13_supersede_chain_is_bounded_acyclic_and_same_entity():
    lens = laowang_lens()

    with pytest.raises(RetrospectiveAnnotationError) as missing:
        lens.attach_annotation(fraud_annotation(supersedes_annotation_id="ran_ghost"))
    assert missing.value.code == ErrorCode.NOT_FOUND
    assert missing.value.context["reason"] == "supersede_target_missing"

    first = fraud_annotation()
    lens.attach_annotation(first)

    with pytest.raises(OverlayCascadeForbidden) as mismatch:
        lens.attach_annotation(
            fraud_annotation(
                target_entity_id="ent_laoli",
                supersedes_annotation_id=first.annotation_id,
            )
        )
    assert mismatch.value.context["reason"] == "supersede_entity_mismatch"

    # 链条必须收敛在上限之内，杜绝无界级联
    previous = first
    for depth in range(MAX_SUPERSEDE_CHAIN_DEPTH):
        previous = fraud_annotation(
            overlay=f"{OVERLAY}-{depth}",
            learned_at=T_NOW + timedelta(minutes=depth + 1),
            supersedes_annotation_id=previous.annotation_id,
        )
        lens.attach_annotation(previous)

    with pytest.raises(OverlayCascadeForbidden) as unbounded:
        lens.attach_annotation(
            fraud_annotation(
                learned_at=T_NOW + timedelta(hours=5),
                supersedes_annotation_id=previous.annotation_id,
            )
        )
    assert unbounded.value.context["reason"] == "supersede_chain_unbounded"
    assert lens.recompute_audit().history_rewrites == 0


def test_ra14_superseding_overlay_grows_forward_without_deleting_the_past():
    lens = laowang_lens()
    first = fraud_annotation()
    lens.attach_annotation(first)

    cleared = fraud_annotation(
        overlay="误会已澄清：老王并未欺诈",
        learned_at=T_NOW + timedelta(days=30),
        supersedes_annotation_id=first.annotation_id,
    )
    lens.attach_annotation(cleared)

    current = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    assert current["overlay_labels"] == ["误会已澄清：老王并未欺诈"]
    assert [overlay["annotation_id"] for overlay in current["overlays"]] == [
        cleared.annotation_id
    ]
    assert current["coverage"]["superseded_overlays_hidden"] == 1

    trail = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP,
        include_superseded=True,
    )
    assert [overlay["annotation_id"] for overlay in trail["overlays"]] == [
        first.annotation_id,
        cleared.annotation_id,
    ]
    assert trail["overlays"][0]["status"] == "superseded"
    assert trail["overlays"][0]["superseded_by"] == cleared.annotation_id
    assert trail["overlays"][1]["status"] == "active"

    # 旧认知永久留存（append-only），历史事实哈希依旧不变
    assert first in lens.annotations
    assert annotation_sha256(first) == trail["overlays"][0]["annotation_sha256"]
    assert lens.recompute_audit().history_rewrites == 0
    assert lens.verify_history_integrity().verified is True

    # 在“澄清”之前那个 cutoff 上，只看得见第一条图层
    between = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP,
        as_of_cutoff=T_NOW + timedelta(days=1),
    )
    assert between["overlay_labels"] == [OVERLAY]


# --- ra15 篡改历史被当场识破并拒绝服务 --------------------------------------


def test_ra15_tampering_with_a_raw_fact_is_detected_and_refused():
    observation = chat_log()
    original_digest = fact_sha256(observation)
    lens = EpistemicWorldLens([observation])

    # 违宪操作：试图把两年前的聊天记录就地改成“老王是骗子”
    observation.value = {"text": "老王：我确实是骗子", "channel": "wechat"}

    report = lens.verify_history_integrity(LAOWANG)
    assert report.verified is False
    assert report.checked_facts == 1
    finding = report.tampered[0]
    assert finding.object_id == observation.object_id
    assert finding.expected_sha256 == original_digest
    assert finding.observed_sha256 == fact_sha256(observation)
    assert finding.reason == "digest_mismatch"

    with pytest.raises(HistoryImmutabilityViolation) as attach_exc:
        lens.attach_annotation(fraud_annotation())
    assert attach_exc.value.code == ErrorCode.STORAGE_FAILURE
    assert attach_exc.value.context["reason"] == "history_immutability_violation"
    assert attach_exc.value.context["expected_sha256"] == original_digest

    with pytest.raises(HistoryImmutabilityViolation):
        lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)

    # 引擎留存的仍是未被污染的历史原貌，且违宪尝试被计数
    anchor = lens.fact_anchors(LAOWANG)[0]
    assert anchor.payload_sha256 == original_digest
    assert anchor.payload["value"]["text"] == CHAT_TEXT
    assert lens.recompute_audit().history_rewrite_attempts_blocked >= 1
    assert lens.recompute_audit().history_rewrites == 0


def test_ra16_same_object_revision_with_different_bytes_is_refused():
    lens = EpistemicWorldLens()
    anchors = lens.register_fact(chat_log(), entity_ids=LAOWANG)

    # 幂等重登记：同一字节形态不会产生第二条历史
    replay = lens.register_fact(chat_log(), entity_ids=LAOWANG)
    assert replay == anchors
    assert len(lens.fact_anchors(LAOWANG)) == 1

    # 同一 object_id/revision 换内容 = 改写历史 → 拒绝
    rewritten = chat_log().model_copy(
        update={"value": {"text": "老王：我确实是骗子", "channel": "wechat"}}
    )
    with pytest.raises(HistoryImmutabilityViolation) as excinfo:
        lens.register_fact(rewritten, entity_ids=LAOWANG)
    assert excinfo.value.context["reason"] == "history_immutability_violation"
    assert excinfo.value.context["expected_sha256"] == anchors[0].payload_sha256
    assert lens.fact_anchors(LAOWANG)[0].payload_sha256 == anchors[0].payload_sha256

    # 认知向前演化只能通过“新版本”追加，旧版本永久可见
    forward = chat_log().model_copy(
        update={
            "revision": 2,
            "value": {"text": "聊天原文补全（含语音转写）", "channel": "wechat"},
            "learned_at": T_NOW,
            "recorded_at": T_NOW,
        }
    )
    lens.register_fact(forward, entity_ids=LAOWANG)

    then = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP,
        as_of_cutoff=T_CUTOFF_THEN,
    )
    assert [fact["revision"] for fact in then["facts"]] == [1]
    assert then["facts"][0]["payload"]["value"]["text"] == CHAT_TEXT

    now = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    assert [fact["revision"] for fact in now["facts"]] == [2]
    assert lens.verify_history_integrity().verified is True
    assert len(lens.fact_anchors(LAOWANG)) == 2


# --- ra17 挂载幂等、参数守门与只读边界 --------------------------------------


def test_ra17_annotation_attach_is_idempotent_and_conflict_is_detected():
    lens = laowang_lens()
    annotation = fraud_annotation()

    first = lens.attach_annotation(annotation)
    replay = lens.attach_annotation(annotation)

    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.annotation_sha256 == first.annotation_sha256
    assert len(lens.attachments) == 1
    assert len(lens.annotations) == 1

    conflicting = fraud_annotation(
        annotation_id=annotation.annotation_id,
        overlay="可信合伙人",
    )
    with pytest.raises(RetrospectiveAnnotationError) as excinfo:
        lens.attach_annotation(conflicting)
    assert excinfo.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert excinfo.value.context["reason"] == "annotation_fingerprint_mismatch"
    assert lens.annotations[0].semantic_overlay == OVERLAY


def test_ra18_unanchored_targets_and_invalid_arguments_fail_closed():
    lens = laowang_lens()

    with pytest.raises(AnnotationTargetNotFound) as excinfo:
        lens.attach_annotation(fraud_annotation(target_entity_id="ent_stranger"))
    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert excinfo.value.context["reason"] == "annotation_target_not_found"

    # 指针指向没有事实的时间窗口同样拒绝（图层必须挂在真实历史切片上）
    with pytest.raises(AnnotationTargetNotFound):
        lens.attach_annotation(
            fraud_annotation(
                target_start=T_NOW - timedelta(days=2),
                target_end=T_NOW - timedelta(days=1),
                learned_at=T_NOW,
            )
        )

    permissive = EpistemicWorldLens(require_anchored_target=False)
    receipt = permissive.attach_annotation(fraud_annotation())
    assert receipt.anchored_fact_count == 0
    assert receipt.anchored_fact_sha256 == {}

    with pytest.raises(RetrospectiveAnnotationError) as blank_entity:
        lens.query_historical_slice("  ", T_PARTNERSHIP)
    assert blank_entity.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(RetrospectiveAnnotationError) as naive_time:
        lens.query_historical_slice(LAOWANG, datetime(2024, 3, 1, 19, 30))
    assert naive_time.value.context["reason"] == "query_timestamp_invalid"

    with pytest.raises(RetrospectiveAnnotationError) as naive_cutoff:
        lens.query_historical_slice(
            LAOWANG,
            T_PARTNERSHIP,
            as_of_cutoff=datetime(2024, 3, 2, 0, 0),
        )
    assert naive_cutoff.value.code == ErrorCode.INVALID_ARGUMENT

    # 残缺映射：能识别为注记载荷但通不过契约校验
    with pytest.raises(RetrospectiveAnnotationError) as incomplete:
        lens.attach_annotation({"semantic_overlay": OVERLAY})  # type: ignore[arg-type]
    assert incomplete.value.code == ErrorCode.INVALID_ARGUMENT
    assert incomplete.value.context["reason"] == "annotation_coercion_failed"

    # 完全不相干的类型：直接判为类型违宪
    with pytest.raises(RetrospectiveAnnotationError) as wrong_type:
        lens.attach_annotation("老王是骗子")  # type: ignore[arg-type]
    assert wrong_type.value.context["reason"] == "annotation_type_invalid"


def test_ra19_lens_exposes_no_history_write_api_and_returns_copies_only():
    lens = laowang_lens()
    lens.attach_annotation(fraud_annotation())

    forbidden_prefixes = (
        "update_",
        "delete_",
        "remove_",
        "rewrite_",
        "mutate_",
        "purge_",
        "erase_",
        "overwrite_",
        "backfill_",
    )
    public_api = [name for name in dir(lens) if not name.startswith("_")]
    assert [name for name in public_api if name.startswith(forbidden_prefixes)] == []

    view = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    for fact in view["facts"]:
        fact["payload"]["value"] = {"text": "篡改后的历史"}
    view["overlay_labels"].append("伪造标签")

    again = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    assert CHAT_TEXT in dumped(again)
    assert "篡改后的历史" not in dumped(again)
    assert again["overlay_labels"] == [OVERLAY]

    # 只读账本视图：外部拿不到可改写的内部容器
    assert isinstance(lens.annotations, tuple)
    assert isinstance(lens.attachments, tuple)
    assert isinstance(lens.fact_anchors(LAOWANG), tuple)


# --- ra20 与既有 M0 双时间存储底座协同 --------------------------------------


def test_ra20_annotation_projects_to_a_t_now_claim_hidden_from_the_past(tmp_path):
    store = seeded_store(tmp_path)
    rows_before = raw_durable_rows(tmp_path / "world.db")

    annotation = fraud_annotation()
    statement = Claim(
        object_id=STATEMENT_ID,
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent.point(T_NOW),
        learned_at=T_NOW,
        recorded_at=T_NOW,
        created_by="m1-018-test",
        claimant_id=USER,
        claim_type=ClaimType.FACT,
        content="今天用户指认老王是骗子",
        valid_time=TemporalExtent.point(T_NOW),
        asserted_at=T_NOW,
        knowledge_state=KnowledgeState.REPORTED,
        confidence=0.99,
    )
    overlay_claim = annotation.to_durable_claim(subject_id=USER, claimant_id=USER)
    assert overlay_claim.learned_at == T_NOW
    assert overlay_claim.asserted_at == T_NOW
    assert overlay_claim.valid_time.start == T_PARTNERSHIP
    assert overlay_claim.valid_time.end == T_PARTNERSHIP_END
    assert OVERLAY in overlay_claim.content
    assert overlay_claim.metadata["retrospective_annotation_id"] == (
        annotation.annotation_id
    )

    commit(store, [statement, overlay_claim], store.current_world_revision(), "m1-018-now")

    query = HistoricalWorldQuery(store)
    then = query.list(knowledge_cutoff=T_CUTOFF_THEN)
    now = query.list()

    then_ids = {payload["object_id"] for payload in then.payloads}
    now_ids = {payload["object_id"] for payload in now.payloads}
    assert STATEMENT_ID not in then_ids
    assert overlay_claim.object_id not in then_ids
    assert {STATEMENT_ID, overlay_claim.object_id} <= now_ids
    assert OVERLAY not in json.dumps(then.payloads, ensure_ascii=False)

    # 两年前的原始事实行仍然一个字节都没动
    rows_after = raw_durable_rows(tmp_path / "world.db")
    assert {row[:5] for row in rows_before} <= {row[:5] for row in rows_after}
    assert len(rows_after) == len(rows_before) + 2
    before_bytes = {(row[0], row[1]): row[5] for row in rows_before}
    after_bytes = {(row[0], row[1]): row[5] for row in rows_after}
    for key, payload in before_bytes.items():
        assert after_bytes[key] == payload


def test_ra21_lens_loaded_from_durable_history_matches_row_digests(tmp_path):
    store = seeded_store(tmp_path)
    rows = raw_durable_rows(tmp_path / "world.db")
    row_digests = {
        (row[0], row[1]): hashlib.sha256(row[5].encode("utf-8")).hexdigest()
        for row in rows
    }

    lens = EpistemicWorldLens.from_historical_query(
        HistoricalWorldQuery(store),
        entity_ids=[LAOWANG, USER],
        knowledge_cutoff=T_CUTOFF_THEN,
    )
    anchors = lens.fact_anchors(LAOWANG)
    assert {anchor.object_id for anchor in anchors} == {
        LAOWANG,
        "obs_chat_laowang_partnership",
        "obs_hr_dinner_with_laowang",
    }
    for anchor in anchors:
        assert anchor.payload_sha256 == row_digests[(anchor.object_id, anchor.revision)]
    # 同一批事实也可以锚定在用户实体下（多实体锚定，历史只登记一份字节）
    assert {anchor.object_id for anchor in lens.fact_anchors(USER)} == {
        anchor.object_id for anchor in anchors
    }

    lens.attach_annotation(fraud_annotation())
    historical = lens.query_historical_slice(
        LAOWANG,
        T_PARTNERSHIP,
        as_of_cutoff=T_CUTOFF_THEN,
    )
    current = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)

    assert historical["overlays"] == []
    assert current["overlay_labels"] == [OVERLAY]
    assert [fact["payload_sha256"] for fact in historical["facts"]] == [
        fact["payload_sha256"] for fact in current["facts"]
    ]
    assert raw_durable_rows(tmp_path / "world.db") == rows


def test_ra22_timeless_facts_and_forged_payloads_fail_closed():
    lens = laowang_lens()
    timeless = Observation(
        object_id="obs_laowang_alias",
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent.unknown_time(),
        learned_at=T_PARTNERSHIP,
        recorded_at=T_PARTNERSHIP,
        created_by="m1-018-test",
        source_kind="address_book",
        modality="text",
        value={"alias": "老王（合伙人）"},
        metadata={"entity_id": LAOWANG},
    )
    lens.register_fact(timeless)

    view = lens.query_historical_slice(LAOWANG, T_PARTNERSHIP)
    # 时间未知的事实不会被硬塞进某个切片，但必须可见地被记为“被跳过”
    assert view["coverage"]["skipped_time_unknown_facts"] == 1
    assert "obs_laowang_alias" not in {fact["object_id"] for fact in view["facts"]}
    assert lens.verify_history_integrity().verified is True

    # 持久化载荷入口：规范载荷可无损复原，且指纹与活对象完全一致
    payload = chat_log().model_dump(mode="json")
    assert coerce_world_object(payload).object_id == chat_log().object_id
    assert fact_sha256(payload) == fact_sha256(chat_log())

    # 伪造/残缺的历史载荷在入口即被拒绝，绝不带病进入透镜
    with pytest.raises(RetrospectiveAnnotationError) as missing:
        coerce_world_object({k: v for k, v in payload.items() if k != "object_type"})
    assert missing.value.code == ErrorCode.INVALID_ARGUMENT
    assert missing.value.context["reason"] == "missing_object_type"

    with pytest.raises(RetrospectiveAnnotationError) as unknown:
        coerce_world_object({**payload, "object_type": "time_machine"})
    assert unknown.value.context["reason"] == "unknown_object_type"

    with pytest.raises(RetrospectiveAnnotationError) as corrupt:
        coerce_world_object({**payload, "learned_at": "两年前"})
    assert corrupt.value.context["reason"] == "payload_revalidation_failed"

    with pytest.raises(TypeError):
        coerce_world_object("obs_chat_laowang_partnership")  # type: ignore[arg-type]


# --- 王建国案（升级版工单高阶实战情境） --------------------------------------
# 两年前签署联合孵化协议；730 天内累积高密度客观事实链；
# 第 730 天（T_now）司法部门下达查封执行文书。
WANGJIANGUO = "ent_wangjianguo"
T0 = datetime(2024, 9, 16, 0, 0, tzinfo=timezone.utc)
T_TODAY = T0 + timedelta(days=730)
T_CUTOFF_100D = T0 + timedelta(days=100)
COURT_DOC = "court_execution_doc_2026_hu01_zhi_1234"
SEIZURE_OVERLAY = "司法冻结查封确认欺诈"
ANNOTATION_ID = "ran_judicial_seizure_0001"


def incubation_fact(
    object_id: str,
    occurred_at: datetime,
    source_kind: str,
    value: dict,
) -> Observation:
    return Observation(
        object_id=object_id,
        subject_id=USER,
        revision=1,
        occurred=TemporalExtent.point(occurred_at),
        learned_at=occurred_at,
        recorded_at=occurred_at,
        created_by="m1-018-test",
        source_kind=source_kind,
        modality="json",
        value=value,
        metadata={"entity_id": WANGJIANGUO},
    )


def incubation_facts() -> list[Observation]:
    """联合孵化协议签署后 730 天内的高价值客观事实链（节选）。"""

    return [
        incubation_fact(
            "obs_wjg_agreement",
            T0,
            "joint_incubation_agreement",
            {"doc_no": "HT-2024-0001", "equity_ratio": 0.32, "party_b": "王建国"},
        ),
        incubation_fact(
            "obs_wjg_minutes",
            T_CUTOFF_100D,
            "shareholder_minutes",
            {"resolution": "追加投资 800 万元", "vote": "全票通过", "chair": "王建国"},
        ),
        incubation_fact(
            "obs_wjg_vitals",
            T_CUTOFF_100D + timedelta(hours=22),
            "evening_vitals",
            {"heart_rate_bpm": 96, "stress_index": 0.71},
        ),
        incubation_fact(
            "obs_wjg_wire",
            T0 + timedelta(days=400),
            "wire_transfer_voucher",
            {"amount_cny": 3_200_000, "payee": "王建国控制的离岸账户"},
        ),
    ]


def judicial_annotation(**overrides) -> RetrospectiveAnnotation:
    """今天（``T_now = T0 + 730d``）司法查封文书触发的外挂解释图层。

    使用升级版工单的规范字段名（``valid_time_start / valid_time_end /
    source_evidence_ref``），``valid_time_range = [T0, T_now]``。
    """

    fields: dict = {
        "annotation_id": ANNOTATION_ID,
        "target_entity_id": WANGJIANGUO,
        "semantic_overlay": SEIZURE_OVERLAY,
        "valid_time_start": T0,
        "valid_time_end": T_TODAY,
        "learned_at": T_TODAY,
        "source_evidence_ref": COURT_DOC,
        "confidence": 0.99,
    }
    fields.update(overrides)
    return RetrospectiveAnnotation(**fields)


def layered_topology() -> tuple[dict[str, list[str]], list[list[str]]]:
    """5 层深度依赖拓扑网：10 个 1 级 / 200 个 2 级 / 1000 个 3 级 / 2000 / 4000。"""

    layers = [
        [f"L1_{index:02d}" for index in range(10)],
        [f"L2_{index:03d}" for index in range(200)],
        [f"L3_{index:04d}" for index in range(1000)],
        [f"L4_{index:04d}" for index in range(2000)],
        [f"L5_{index:04d}" for index in range(4000)],
    ]
    adjacency: dict[str, list[str]] = {WANGJIANGUO: list(layers[0])}
    fanout = (20, 5, 2, 2)
    for depth, width in enumerate(fanout):
        for index, node in enumerate(layers[depth]):
            adjacency[node] = layers[depth + 1][index * width : (index + 1) * width]
    return adjacency, layers


def baseline_line():
    """战队已合入基线（并存不覆盖）；若首席日后裁掉该线，互操作断言自动跳过。"""

    try:
        return import_module("aios_core.world.retrospective_annotation")
    except ImportError:  # pragma: no cover - 取决于首席仲裁结果
        pytest.skip("baseline retrospective_annotation line is not present")


# --- ra23 升级版契约命名与双线互操作 ----------------------------------------


def test_ra23_upgraded_contract_naming_and_sibling_interoperability():
    upgraded = judicial_annotation()

    assert upgraded.valid_time_start == T0
    assert upgraded.valid_time_end == T_TODAY
    assert upgraded.source_evidence_ref == COURT_DOC
    assert upgraded.learned_at == upgraded.recorded_at == T_TODAY
    assert upgraded.valid_time_range.start == T0
    assert upgraded.valid_time_range.end == T_TODAY

    # 一号工单命名以只读别名同值暴露，两版工单读法都成立
    assert upgraded.target_time_start == upgraded.valid_time_start
    assert upgraded.target_time_end == upgraded.valid_time_end
    assert upgraded.source_statement_ref == upgraded.source_evidence_ref
    assert upgraded.target_time_range == upgraded.valid_time_range

    # 用一号工单字段名构造 → 与升级版规范名构造得到同一份契约与同一枚指纹
    legacy = RetrospectiveAnnotation(
        annotation_id=ANNOTATION_ID,
        target_entity_id=WANGJIANGUO,
        semantic_overlay=SEIZURE_OVERLAY,
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        source_statement_ref=COURT_DOC,
        confidence=0.99,
    )
    assert legacy.model_dump() == upgraded.model_dump()
    assert annotation_sha256(legacy) == annotation_sha256(upgraded)

    with pytest.raises(ValidationError):
        RetrospectiveAnnotation.model_validate(
            {**upgraded.model_dump(), "rewrite_history": True}
        )

    baseline = baseline_line()
    sibling = baseline.RetrospectiveAnnotation(
        annotation_id=ANNOTATION_ID,
        target_entity_id=WANGJIANGUO,
        semantic_overlay=SEIZURE_OVERLAY,
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=T_TODAY,
        source_statement_ref=COURT_DOC,
    )

    # 基线注记可直接投喂本线引擎（双线熔铸零成本）
    coerced = coerce_annotation(sibling)
    assert isinstance(coerced, RetrospectiveAnnotation)
    assert coerced.annotation_id == ANNOTATION_ID
    assert coerced.valid_time_start == T0
    assert coerced.valid_time_end == T_TODAY
    assert coerced.source_evidence_ref == COURT_DOC
    assert coerced.recorded_at == T_TODAY
    assert coerced.confidence == 1.0

    # 本线注记也可投影回基线契约（只投影对方声明过的字段）
    projected = upgraded.to_sibling_annotation()
    assert isinstance(projected, baseline.RetrospectiveAnnotation)
    assert projected.target_time_start == T0
    assert projected.target_time_end == T_TODAY
    assert projected.source_statement_ref == COURT_DOC
    assert projected.recorded_at == T_TODAY
    assert coerce_annotation(projected).model_dump() == coerced.model_dump()


# --- ra24 升级版双时间认知透镜外壳 ------------------------------------------


def test_ra24_bi_temporal_lens_reproduces_day_100_and_overlays_today():
    facts = incubation_facts()
    digests = {fact.object_id: fact_sha256(fact) for fact in facts}
    annotation = judicial_annotation()

    lens = BiTemporalEpistemicLens(facts, [annotation])
    # 工单骨架原文：raw_store / annotation_store 就是调用方注入的那两个库对象
    assert lens.raw_store is facts
    assert lens.annotation_store == [annotation]
    assert isinstance(lens.engine, EpistemicWorldLens)
    assert lens.registered_annotations == (annotation,)
    assert lens.registered_fact_count == len(facts)

    then = lens.query_entity_state(
        WANGJIANGUO,
        T_CUTOFF_100D,
        as_of_cutoff=T_CUTOFF_100D,
        slice_mode="cumulative",
    )
    assert isinstance(then, HistoricalEpistemicSlice)
    assert then.query_time == T_CUTOFF_100D
    assert then.target_time == then.query_time
    assert then.entity_id == WANGJIANGUO
    assert then.view_kind == "AS_OF"
    assert then.as_of_cutoff == T_CUTOFF_100D
    assert then.active_annotations == []
    assert then.has_overlay is False
    assert "当时已知认知原貌" in then.effective_interpretation
    assert SEIZURE_OVERLAY not in then.effective_interpretation
    # 第 100 天当时已知：孵化协议 + 当日股东会纪要（当晚体征与第 400 天汇款尚未发生）
    assert {obs["object_id"] for obs in then.raw_observations} == {
        "obs_wjg_agreement",
        "obs_wjg_minutes",
    }
    assert then.raw_observation_digests == {
        f"{object_id}@1": digests[object_id]
        for object_id in ("obs_wjg_agreement", "obs_wjg_minutes")
    }
    assert SEIZURE_OVERLAY not in json.dumps(
        then.model_dump(mode="json"), ensure_ascii=False
    )

    now = lens.query_entity_state(
        WANGJIANGUO,
        T_CUTOFF_100D,
        slice_mode="cumulative",
    )
    assert now.view_kind == "CURRENT"
    assert now.as_of_cutoff is None
    assert [item.annotation_id for item in now.active_annotations] == [ANNOTATION_ID]
    assert now.has_overlay is True
    assert SEIZURE_OVERLAY in now.effective_interpretation
    # 历史事实与其哈希在两种视图下逐条一致
    assert now.raw_observation_digests == then.raw_observation_digests
    assert [obs["object_id"] for obs in now.raw_observations] == [
        obs["object_id"] for obs in then.raw_observations
    ]
    assert {fact.object_id: fact_sha256(fact) for fact in facts} == digests
    assert lens.engine.verify_history_integrity().verified is True

    # 一号工单签名形态（Dict[str, Any]）与升级版外壳同源
    raw = lens.query_historical_slice(
        WANGJIANGUO,
        T_CUTOFF_100D,
        slice_mode="cumulative",
    )
    assert raw["overlay_labels"] == [SEIZURE_OVERLAY]
    assert raw["slice_mode"] == "cumulative"
    assert raw["view_mode"] == "current_cognition"
    assert {fact["object_id"]: fact["payload_sha256"] for fact in raw["facts"]} == {
        key.split("@")[0]: value
        for key, value in then.raw_observation_digests.items()
    }

    with pytest.raises(ValueError):
        BiTemporalEpistemicLens(facts, engine=lens.engine)


# --- ra25 单跳级联隔离：5 层万级拓扑严格锁死在 1 级 10 个节点 ----------------


def test_ra25_single_hop_isolation_never_expands_the_second_hop():
    adjacency, layers = layered_topology()
    level_one, level_two = layers[0], layers[1]
    deep_nodes = layers[1] + layers[2] + layers[3] + layers[4]

    recompute_calls: list[str] = []
    isolator = SingleHopCascadeIsolator(recompute_hook=recompute_calls.append)
    marked = isolator.invalidate_downstream_single_hop(
        WANGJIANGUO,
        judicial_annotation(),
        adjacency,
    )

    # 严格等于 1 级节点数（10 个），2 级及更远一个都不许碰
    assert marked == set(level_one)
    assert len(marked) == 10
    assert isolator.stale_nodes() == frozenset(level_one)
    assert all(isolator.is_stale(node) for node in level_one)
    assert not any(isolator.is_stale(node) for node in deep_nodes)
    assert isolator.stale_reason(level_one[0]).startswith(
        f"retrospective_annotation:{ANNOTATION_ID}:"
    )

    report = isolator.last_report()
    assert report.marked_stale == tuple(sorted(level_one))
    assert report.marked_stale_count == 10
    assert report.traversal_depth_reached == 1
    assert report.graph_queries == 1
    assert report.nodes_visited == 11
    assert report.llm_recompute_triggered == 0
    assert report.second_hop_expanded is False
    assert report.cascade_suppressed is True
    assert report.annotation_id == ANNOTATION_ID
    assert report.entity_id == WANGJIANGUO
    assert report.origin_node_id == WANGJIANGUO

    # 大模型重算触发次数严格为 0：间谍回调一次都没被调用
    assert recompute_calls == []
    assert isolator.recompute_calls == ()
    assert isolator.isolation_count == 1

    # 报告契约根本无法表达“发生过级联递归”
    for violation in (
        {"graph_queries": 2},
        {"llm_recompute_triggered": 1},
        {"traversal_depth_reached": 2},
        {"second_hop_expanded": True},
    ):
        with pytest.raises(ValidationError):
            SingleHopInvalidationReport(**{**report.model_dump(), **violation})

    # 只读诊断：被刻意压制的 200 个 2 级节点看得清，但不打 stale、不重算
    suppressed = isolator.diagnose_suppressed_downstream(
        adjacency, WANGJIANGUO, depth=2
    )
    assert set(suppressed) == set(level_two)
    assert len(suppressed) == 200
    assert isolator.stale_nodes() == frozenset(level_one)
    assert recompute_calls == []

    with pytest.raises(RetrospectiveAnnotationError) as deep:
        isolator.diagnose_suppressed_downstream(
            adjacency, WANGJIANGUO, depth=MAX_DIAGNOSTIC_DEPTH + 1
        )
    assert deep.value.context["reason"] == "diagnostic_depth_unbounded"

    # 无界级联请求被物理拒绝，且拒绝后既有 stale 状态不受影响
    with pytest.raises(OverlayCascadeForbidden) as unbounded:
        isolator.invalidate_downstream_single_hop(
            WANGJIANGUO,
            judicial_annotation(),
            adjacency,
            max_hops=2,
        )
    assert unbounded.value.code == ErrorCode.INVALID_ARGUMENT
    assert unbounded.value.context["reason"] == "max_hops_locked_to_one"
    assert isolator.blocked_cascades == 1
    assert isolator.stale_nodes() == frozenset(level_one)
    assert recompute_calls == []

    # 绊线图：任何 2 级邻接查询都会当场炸掉测试，实证“深度遍历次数严格为 1”
    class TripwireGraph:
        def __init__(self, table: dict[str, list[str]], origin: str) -> None:
            self._table = table
            self._origin = origin
            self.queries: list[str] = []

        def direct_consumers(self, node_id: str) -> tuple[str, ...]:
            self.queries.append(node_id)
            if node_id != self._origin:
                raise AssertionError(f"级联递归被触发：查询了下游节点 {node_id}")
            return tuple(self._table[node_id])

    tripwire = TripwireGraph(adjacency, WANGJIANGUO)
    strict = SingleHopCascadeIsolator()
    assert strict.invalidate_downstream_single_hop(
        WANGJIANGUO, judicial_annotation(), tripwire
    ) == set(level_one)
    assert tripwire.queries == [WANGJIANGUO]

    # M0-005 显式 Dependency 记录同样可以直接当依赖图使用
    dependencies = [
        Dependency(
            object_id=f"dep_wjg_summary_{index}",
            subject_id=USER,
            revision=1,
            occurred=TemporalExtent.point(T_TODAY),
            learned_at=T_TODAY,
            recorded_at=T_TODAY,
            created_by="m1-018-test",
            dependent_ref=ObjectRef(object_id=f"sum_wjg_week_{index}", revision=1),
            dependency_ref=ObjectRef(object_id=WANGJIANGUO, revision=1),
            dependency_type="summary_of_entity",
        )
        for index in range(3)
    ]
    assert normalize_dependency_graph(dependencies) == {
        WANGJIANGUO: (
            "sum_wjg_week_0",
            "sum_wjg_week_1",
            "sum_wjg_week_2",
        )
    }
    contract_isolator = SingleHopCascadeIsolator()
    assert contract_isolator.invalidate_downstream_single_hop(
        WANGJIANGUO, judicial_annotation(), dependencies
    ) == {"sum_wjg_week_0", "sum_wjg_week_1", "sum_wjg_week_2"}

    with pytest.raises(RetrospectiveAnnotationError) as bad_graph:
        contract_isolator.invalidate_downstream_single_hop(
            WANGJIANGUO, judicial_annotation(), 42
        )
    assert bad_graph.value.context["reason"] == "dependency_graph_invalid"


# --- ra26 万条级高密度历史事实逐条哈希比对 ----------------------------------


def test_ra26_ten_thousand_high_density_facts_keep_every_single_sha256():
    # 730 天 ≈ 1,051,200 分钟；每 105 分钟一条 → 10,000 条高密度事实链
    facts = [
        incubation_fact(
            f"obs_wjg_stream_{index:06d}",
            T0 + timedelta(minutes=index * 105),
            "contract_ledger_stream",
            {
                "seq": index,
                "amount_cny": 10_000 + index,
                "counterparty": "王建国",
                "doc_no": f"HT-2024-{index:06d}",
            },
        )
        for index in range(10_000)
    ]

    lens = EpistemicWorldLens()
    lens.register_facts(facts)
    sealed = {
        anchor.object_id: anchor.payload_sha256
        for anchor in lens.fact_anchors(WANGJIANGUO)
    }
    assert len(sealed) == 10_000
    assert {fact.object_id: fact_sha256(fact) for fact in facts} == sealed
    aggregate_before = hashlib.sha256(
        "".join(sealed[key] for key in sorted(sealed)).encode("utf-8")
    ).hexdigest()
    assert lens.verify_history_integrity().checked_facts == 10_000

    receipt = lens.attach_annotation(judicial_annotation())
    assert receipt.anchored_fact_count == 10_000
    assert receipt.history_rewrites == 0
    assert receipt.derived_recomputations == 0
    assert receipt.overlay_hops == MAX_OVERLAY_HOPS

    # 逐条比对：写入司法查封回溯注记后，10,000 条历史事实哈希 100% 字节级一致
    after = {
        anchor.object_id: anchor.payload_sha256
        for anchor in lens.fact_anchors(WANGJIANGUO)
    }
    assert len(after) == 10_000
    assert [key for key in sealed if sealed[key] != after.get(key)] == []
    assert after == sealed
    assert {fact.object_id: fact_sha256(fact) for fact in facts} == sealed
    assert (
        hashlib.sha256(
            "".join(after[key] for key in sorted(after)).encode("utf-8")
        ).hexdigest()
        == aggregate_before
    )
    integrity = lens.verify_history_integrity()
    assert integrity.verified is True
    assert integrity.checked_facts == 10_000
    assert integrity.tampered == ()

    # 第 100 天当时已知视图：零图层泄露，事实量级符合“当时”的累积规模
    then = lens.query_historical_slice(
        WANGJIANGUO,
        T_CUTOFF_100D,
        as_of_cutoff=T_CUTOFF_100D,
        slice_mode="cumulative",
    )
    assert then["overlay_labels"] == []
    assert then["overlays"] == []
    assert then["coverage"]["hidden_by_cutoff_overlays"] == 1
    assert 1_000 < then["coverage"]["returned_facts"] < 2_000
    assert SEIZURE_OVERLAY not in dumped(then)
    assert COURT_DOC not in dumped(then)

    # 当下审视全景视图：历史事实一字不改，司法查封图层精准叠加
    now = lens.query_historical_slice(
        WANGJIANGUO,
        T_CUTOFF_100D,
        slice_mode="cumulative",
    )
    assert now["overlay_labels"] == [SEIZURE_OVERLAY]
    assert now["coverage"]["returned_facts"] == then["coverage"]["returned_facts"]
    assert [fact["payload_sha256"] for fact in now["facts"]] == [
        fact["payload_sha256"] for fact in then["facts"]
    ]

    audit = lens.recompute_audit()
    assert audit.history_rewrites == 0
    assert audit.derived_recomputations == 0
    assert audit.max_recursion_depth == 0
    assert audit.annotations_attached == 1


# --- ra27 双线一致性：与战队已合入基线在四大门禁上给出同一答案 ----------------


def test_ra27_both_implementation_lines_agree_on_all_four_hard_gates():
    baseline = baseline_line()
    facts = incubation_facts()
    annotation = judicial_annotation()

    # —— 本线（world/epistemic_world_lens.py）——
    mine = EpistemicWorldLens()
    mine.register_facts(facts)
    my_digests = {
        anchor.object_id: anchor.payload_sha256
        for anchor in mine.fact_anchors(WANGJIANGUO)
    }
    mine.attach_annotation(annotation)
    my_then = mine.query_historical_slice(
        WANGJIANGUO,
        T_CUTOFF_100D,
        as_of_cutoff=T_CUTOFF_100D,
        slice_mode="cumulative",
    )
    my_now = mine.query_historical_slice(
        WANGJIANGUO, T_CUTOFF_100D, slice_mode="cumulative"
    )

    # —— 战队基线（world/retrospective_annotation.py）——
    ledger = baseline.ImmutableFactLedger()
    sealed = {
        fact.object_id: ledger.record_fact(
            fact_id=fact.object_id,
            entity_id=WANGJIANGUO,
            occurred_at=fact.occurred.start,
            kind=fact.source_kind,
            payload=fact.value,
        )
        for fact in facts
    }
    registry = baseline.AnnotationRegistry()
    registry.append(annotation.to_sibling_annotation())
    theirs = baseline.BiTemporalEpistemicLens(ledger, registry)
    their_then = theirs.query_historical_slice(
        WANGJIANGUO, T_CUTOFF_100D, as_of_cutoff=T_CUTOFF_100D
    )
    their_now = theirs.query_historical_slice(WANGJIANGUO, T_CUTOFF_100D)

    # 门禁 1【历史事实绝对不可变】：两条线各自的哈希审计都是全绿
    assert ledger.verify_integrity()[0] is True
    assert ledger.all_hashes() == sealed
    assert mine.verify_history_integrity().verified is True
    assert {
        anchor.object_id: anchor.payload_sha256
        for anchor in mine.fact_anchors(WANGJIANGUO)
    } == my_digests

    # 门禁 2/3【今天打标签 + 双时间透镜】：当时零图层、今天恰好一层，结论一致
    assert my_then["overlay_labels"] == []
    assert tuple(their_then.active_annotations) == ()
    assert their_then.view_kind == "AS_OF"
    assert my_now["overlay_labels"] == [SEIZURE_OVERLAY]
    assert tuple(
        item.semantic_overlay for item in their_now.active_annotations
    ) == (SEIZURE_OVERLAY,)
    assert their_now.view_kind == "CURRENT"
    assert {fact["object_id"] for fact in my_then["facts"]} == {
        fact.fact_id for fact in their_then.facts
    }

    # 门禁 4【单跳级联隔离】：同样锁死在 10 个 1 级节点、深度 1、重算 0 次
    adjacency, layers = layered_topology()
    level_one = layers[0]

    my_isolator = SingleHopCascadeIsolator()
    my_marked = my_isolator.invalidate_downstream_single_hop(
        WANGJIANGUO, annotation, adjacency
    )

    their_isolator = baseline.SingleHopCascadeIsolator()
    their_isolator.register_node(WANGJIANGUO)
    for node in level_one:
        their_isolator.register_node(node)
        their_isolator.add_dependency(WANGJIANGUO, node)
    their_isolator.register_node("L2_000")
    their_isolator.add_dependency(level_one[0], "L2_000")
    their_report = their_isolator.reverse_invalidate(WANGJIANGUO)

    my_report = my_isolator.last_report()
    assert my_marked == set(level_one)
    assert set(their_report.marked_stale) == my_marked
    assert their_report.traversal_depth_reached == my_report.traversal_depth_reached == 1
    assert (
        their_report.llm_recompute_triggered
        == my_report.llm_recompute_triggered
        == 0
    )
    assert their_isolator.stale_nodes() == frozenset(level_one)
    assert my_isolator.stale_nodes() == frozenset(level_one)
    assert their_isolator.is_stale("L2_000") is False
    assert my_isolator.is_stale("L2_000") is False
