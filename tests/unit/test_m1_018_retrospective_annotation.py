"""M1-018 老王案验收测试：认知反向传播语义图层契约与双时间视图引擎。

验收铁律（云端工单 TASK-M1-018 / 宪法第 93 条）：
1. 两年前原始事实对象的 SHA-256 哈希值在挂载标注前后严格保持 100% 相同；
2. 带 as_of_cutoff 的历史查询完整重现「当时信任老王」的人生原貌，
   今天才学到的新认知对该视图严格零泄露；
3. 严禁任何级联递归重算历史：单跳命中、懒加载、预算硬上限、零写入。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation import (
    EpistemicWorldLens,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationError,
    canonical_fact_sha256,
)

ENTITY_LAOWANG = "老王"
ENTITY_OTHER = "老李"

# 两年前的那个夜晚：与老王喝酒、聊合伙，当时完全信任他。
DRINKING_NIGHT = datetime(2024, 9, 15, 20, 30, tzinfo=timezone.utc)
# 第二天签下合伙协议。
PARTNERSHIP_SIGNED_AT = datetime(2024, 9, 16, 10, 0, tzinfo=timezone.utc)
# 切片之外的一个历史时刻（一年前）。
UNRELATED_PAST = datetime(2023, 9, 15, 12, 0, tzinfo=timezone.utc)
# 今天：真相大白的时间戳 T_now。
T_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)

CHAT_PAYLOAD = {
    "source_kind": "chat",
    "modality": "text",
    "value": "老王：兄弟放心，货款下周一准到。我当时完全信任他。",
}
HEART_RATE_PAYLOAD = {
    "source_kind": "wearable",
    "modality": "heart_rate",
    "value": {"bpm": 88, "context": "与老王喝酒谈合伙"},
}
PARTNERSHIP_PAYLOAD = {
    "source_kind": "document",
    "modality": "text",
    "value": "与老王签署合伙协议，各出资 50%。",
}


def _attach_laowang_facts(lens: EpistemicWorldLens) -> dict[str, str]:
    """登记老王案三笔两年前的客观事实底账，返回 fact_id 映射。"""
    return {
        "chat": lens.attach_fact(
            entity_id=ENTITY_LAOWANG,
            valid_time_start=DRINKING_NIGHT,
            payload=CHAT_PAYLOAD,
        ),
        "heart_rate": lens.attach_fact(
            entity_id=ENTITY_LAOWANG,
            valid_time_start=DRINKING_NIGHT,
            payload=HEART_RATE_PAYLOAD,
        ),
        "partnership": lens.attach_fact(
            entity_id=ENTITY_LAOWANG,
            valid_time_start=PARTNERSHIP_SIGNED_AT,
            payload=PARTNERSHIP_PAYLOAD,
        ),
    }


def _make_fraud_annotation(entity_id: str = ENTITY_LAOWANG) -> RetrospectiveAnnotation:
    """今天才学到的认知：后来发现老王是骗子。"""
    return RetrospectiveAnnotation(
        annotation_id="anno-2026-09-15-laowang-fraud",
        target_entity_id=entity_id,
        semantic_overlay="疑似欺诈 / 人际警惕（后来发现是骗子）",
        target_time_start=DRINKING_NIGHT,
        target_time_end=PARTNERSHIP_SIGNED_AT,
        learned_at=T_NOW,
        recorded_at=T_NOW,
        source_statement_ref="stmt://user/2026-09-15/老王其实是骗子",
    )


def _laowang_lens() -> tuple[EpistemicWorldLens, dict[str, str]]:
    lens = EpistemicWorldLens()
    fact_ids = _attach_laowang_facts(lens)
    return lens, fact_ids


def _make_observation() -> Observation:
    """两年前那晚写入世界的原始 Observation（存储底座中的字节级事实）。"""
    return Observation(
        object_id="obs-laowang-drinking-night-2024",
        subject_id="user",
        revision=1,
        occurred=TemporalExtent.point(DRINKING_NIGHT),
        learned_at=DRINKING_NIGHT,
        recorded_at=DRINKING_NIGHT,
        created_by="m1-018-test",
        source_kind="chat",
        modality="text",
        value="老王：兄弟放心，货款下周一准到。我当时完全信任他。",
        data_quality={"trust_level_then": "trusted_partner"},
    )


# ---------------------------------------------------------------------------
# 验收标准 1：原始事实哈希在挂载标注前后严格 100% 不变
# ---------------------------------------------------------------------------


def test_01_raw_fact_sha256_strictly_identical_across_attach() -> None:
    lens, _ = _laowang_lens()

    before_view = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    before_hashes = {f["fact_id"]: f["sha256"] for f in before_view["facts"]}
    before_blobs = {f["fact_id"]: json.dumps(f["payload"], sort_keys=True, ensure_ascii=False) for f in before_view["facts"]}

    annot = _make_fraud_annotation()
    assert lens.attach_annotation(annot) == annot.annotation_id

    after_view = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    after_hashes = {f["fact_id"]: f["sha256"] for f in after_view["facts"]}
    after_blobs = {f["fact_id"]: json.dumps(f["payload"], sort_keys=True, ensure_ascii=False) for f in after_view["facts"]}

    # 字节级铁律：哈希与载荷在加注前后逐比特一致。
    assert before_hashes, "测试前置条件：切片上必须存在历史事实"
    assert after_hashes == before_hashes
    assert after_blobs == before_blobs

    # 反复查询（含当前视图渲染警示图层）同样不得扰动底账分毫。
    for _ in range(50):
        view = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
        assert {f["fact_id"]: f["sha256"] for f in view["facts"]} == before_hashes


def test_02_underlying_observation_object_deep_frozen_through_annotation() -> None:
    obs = _make_observation()
    dump_before = obs.model_dump(mode="json")
    hash_before = canonical_fact_sha256(dump_before)

    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())
    for cutoff in (None, DRINKING_NIGHT, T_NOW):
        lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT, as_of_cutoff=cutoff)

    dump_after = obs.model_dump(mode="json")
    assert dump_after == dump_before
    assert canonical_fact_sha256(dump_after) == hash_before


def test_03_storage_layer_zero_write_and_hash_stable(tmp_path) -> None:
    """端到端：SQLite 存储底座中的历史 Observation 在透镜全部操作后零写入、零哈希漂移。"""
    store = SQLiteWorldStore(tmp_path / "world.db")
    obs = _make_observation()
    op = OperationRequest(
        operation_id=str(uuid.uuid4()),
        operation_name="test_commit",
        arguments={},
        expected_world_revision=0,
        reason="M1-018 laowang seed",
        idempotency_key=str(uuid.uuid4()),
    )
    store.commit([obs], op)
    assert store.current_world_revision() == 1
    payload_hash_before = canonical_fact_sha256(store.get_payload(obs.object_id))

    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())
    lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT, as_of_cutoff=DRINKING_NIGHT)

    # 透镜的任何挂载/查询不得引发存储底座任何新提交（严禁 UPDATE/DELETE/补偿写入）。
    assert store.current_world_revision() == 1
    assert canonical_fact_sha256(store.get_payload(obs.object_id)) == payload_hash_before
    assert canonical_fact_sha256(store.get_payload(obs.object_id, revision=1)) == payload_hash_before


# ---------------------------------------------------------------------------
# 验收标准 2：as_of_cutoff 完整重现历史原貌，新认知零泄露
# ---------------------------------------------------------------------------


def test_04_as_of_cutoff_faithfully_replays_history_without_leak() -> None:
    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())

    target_times = (DRINKING_NIGHT, PARTNERSHIP_SIGNED_AT)
    cutoffs = (
        DRINKING_NIGHT,  # 当时当刻
        PARTNERSHIP_SIGNED_AT,  # 切片终点
        datetime(2024, 9, 17, tzinfo=timezone.utc),  # 切片之后、真相之前
        T_NOW - timedelta(microseconds=1),  # 真相揭晓前一微秒
    )
    for target_time in target_times:
        for cutoff in cutoffs:
            view = lens.query_historical_slice(
                ENTITY_LAOWANG, target_time, as_of_cutoff=cutoff
            )
            assert view["view_mode"] == "as_of_historical"
            assert view["as_of_cutoff"] is not None
            # 零泄露：任何当时视角里都绝对看不到今天才学到的「骗子」图层。
            assert view["overlay_count"] == 0
            assert view["overlays"] == []
            # 历史原貌完整保留：当时的信任记录原样呈现。
            texts = json.dumps(view["facts"], ensure_ascii=False)
            assert "信任" in texts or "合伙" in texts


def test_05_current_view_renders_warning_marker_on_unscarred_history() -> None:
    lens, _ = _laowang_lens()
    before = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    lens.attach_annotation(_make_fraud_annotation())

    view = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    assert view["view_mode"] == "current_overlay"
    assert view["as_of_cutoff"] is None
    assert view["overlay_count"] == 1

    overlay = view["overlays"][0]
    assert overlay["annotation_id"] == "anno-2026-09-15-laowang-fraud"
    assert "欺诈" in overlay["semantic_overlay"]
    assert overlay["rendered_as"] == "warning_marker"
    # 新认知自身只活在今天 T_now。
    assert overlay["learned_at"].startswith("2026-09-15")
    assert overlay["recorded_at"].startswith("2026-09-15")
    # 指针指向两年前的老王切片（外挂解释图层）。
    assert overlay["target_time_start"].startswith("2024-09-15")
    assert overlay["target_time_end"].startswith("2024-09-16")
    assert overlay["source_statement_ref"] == "stmt://user/2026-09-15/老王其实是骗子"

    # 叠加渲染之后，底账哈希与历史载荷仍与加注前逐比特一致。
    assert {f["fact_id"]: f["sha256"] for f in view["facts"]} == {
        f["fact_id"]: f["sha256"] for f in before["facts"]
    }
    assert [f["payload"] for f in view["facts"]] == [f["payload"] for f in before["facts"]]


def test_06_annotation_lives_at_t_now_and_constitutional_ordering() -> None:
    annot = _make_fraud_annotation()
    # learned_at = recorded_at = T_now（今天）
    assert annot.learned_at == T_NOW
    assert annot.recorded_at == T_NOW
    # 认知单向向前：今天学到的认知，严格晚于其指向的历史切片。
    assert annot.learned_at > annot.target_time_end
    assert annot.recorded_at >= annot.learned_at

    # 缺省时间戳默认落在「现在」。
    defaulted = RetrospectiveAnnotation(
        annotation_id="anno-default-times",
        target_entity_id=ENTITY_LAOWANG,
        semantic_overlay="事后注记",
        target_time_start=DRINKING_NIGHT,
        target_time_end=PARTNERSHIP_SIGNED_AT,
        source_statement_ref="stmt://user/x",
    )
    assert defaulted.recorded_at >= defaulted.learned_at
    assert defaulted.learned_at >= PARTNERSHIP_SIGNED_AT


def test_07_cutoff_boundary_is_inclusive_at_exact_learned_at() -> None:
    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())

    # learned_at == cutoff：截止瞬间已学到的知识可见。
    at_exact = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT, as_of_cutoff=T_NOW)
    assert at_exact["overlay_count"] == 1
    # 早一微秒：尚未学到，绝不可见。
    just_before = lens.query_historical_slice(
        ENTITY_LAOWANG, DRINKING_NIGHT, as_of_cutoff=T_NOW - timedelta(microseconds=1)
    )
    assert just_before["overlay_count"] == 0


# ---------------------------------------------------------------------------
# 验收标准 3：严禁级联递归重算历史
# ---------------------------------------------------------------------------


def test_08_single_hop_no_bleed_into_other_slices_or_entities() -> None:
    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())

    # 图层指针范围之外的历史切片：一丝渲染都不允许渗漏。
    outside = lens.query_historical_slice(ENTITY_LAOWANG, UNRELATED_PAST)
    assert outside["overlay_count"] == 0
    outside_asof = lens.query_historical_slice(ENTITY_LAOWANG, UNRELATED_PAST, as_of_cutoff=T_NOW)
    assert outside_asof["overlay_count"] == 0

    # 其他实体：绝不因老王的注记而被级联重标。
    other = lens.query_historical_slice(ENTITY_OTHER, DRINKING_NIGHT)
    assert other["overlay_count"] == 0
    assert other["facts"] == []


def test_09_no_cascade_recompute_is_bounded_and_lazy() -> None:
    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())

    stats0 = lens.stats
    view = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    stats1 = lens.stats

    # 一次查询恰好多一次计数；图层渲染量恰等于直接命中数（1），无任何隐藏级联工作。
    assert stats1["queries"] - stats0["queries"] == 1
    assert stats1["overlay_hits_total"] - stats0["overlay_hits_total"] == view["overlay_count"] == 1
    assert stats1["fact_hits_total"] - stats0["fact_hits_total"] == view["fact_count"]

    # 查询永不反向落账：标注与事实总量全程冻结。
    for _ in range(20):
        lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
        lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT, as_of_cutoff=DRINKING_NIGHT)
    assert len(lens.annotations_for(ENTITY_LAOWANG)) == 1
    assert lens.stats["annotations_attached"] == 1
    assert lens.stats["facts_attached"] == 3

    # 结构性不变量随每个视图发出：历史未重写、无级联重算、懒加载、单跳。
    assert view["integrity"] == {
        "history_rewritten": False,
        "cascade_recompute": False,
        "lazy_evaluation": True,
        "single_hop": True,
    }


def test_10_schema_is_structurally_single_hop() -> None:
    """注记契约不含任何指向注记的字段：结构上不存在注记之注记的递归入口。"""
    fields = set(RetrospectiveAnnotation.model_fields)
    mandated = {
        "annotation_id",
        "target_entity_id",
        "semantic_overlay",
        "target_time_start",
        "target_time_end",
        "learned_at",
        "source_statement_ref",
    }
    assert mandated <= fields, "云端工单冻结字段必须全部存在"
    forbidden_recursive = {
        "target_annotation_id",
        "parent_annotation_id",
        "supersedes_annotation_id",
        "derived_annotation_refs",
        "recompute_scope",
    }
    assert not (fields & forbidden_recursive), "结构上禁止任何级联递归通道"


def test_11_unbounded_annotation_storm_is_rejected_by_budget() -> None:
    lens = EpistemicWorldLens(max_annotations_per_entity=2)
    _attach_laowang_facts(lens)
    hashes_before = {
        f["fact_id"]: f["sha256"]
        for f in lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)["facts"]
    }

    for i in range(2):
        lens.attach_annotation(
            RetrospectiveAnnotation(
                annotation_id=f"anno-storm-{i}",
                target_entity_id=ENTITY_LAOWANG,
                semantic_overlay=f"图层{i}",
                target_time_start=DRINKING_NIGHT,
                target_time_end=PARTNERSHIP_SIGNED_AT,
                learned_at=T_NOW,
                source_statement_ref="stmt://user/storm",
            )
        )

    with pytest.raises(RetrospectiveAnnotationError) as excinfo:
        lens.attach_annotation(
            RetrospectiveAnnotation(
                annotation_id="anno-storm-2",
                target_entity_id=ENTITY_LAOWANG,
                semantic_overlay="雪崩图层",
                target_time_start=DRINKING_NIGHT,
                target_time_end=PARTNERSHIP_SIGNED_AT,
                learned_at=T_NOW,
                source_statement_ref="stmt://user/storm",
            )
        )
    assert excinfo.value.code == ErrorCode.BUDGET_EXHAUSTED

    # 预算拒绝后底账与已挂载图层分毫未动。
    assert len(lens.annotations_for(ENTITY_LAOWANG)) == 2
    hashes_after = {
        f["fact_id"]: f["sha256"]
        for f in lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)["facts"]
    }
    assert hashes_after == hashes_before


def test_12_idempotent_replay_and_conflict_rejected() -> None:
    lens, _ = _laowang_lens()
    annot = _make_fraud_annotation()

    # 完全相同内容的重复挂载：幂等无操作。
    assert lens.attach_annotation(annot) == annot.annotation_id
    assert lens.attach_annotation(annot) == annot.annotation_id
    assert len(lens.annotations_for(ENTITY_LAOWANG)) == 1
    assert lens.stats["annotations_attached"] == 1

    # 同 ID 不同内容：拒绝静默覆盖（解释图层同样不可篡改）。
    conflicting = RetrospectiveAnnotation(
        annotation_id=annot.annotation_id,
        target_entity_id=ENTITY_LAOWANG,
        semantic_overlay="被篡改的图层",
        target_time_start=DRINKING_NIGHT,
        target_time_end=PARTNERSHIP_SIGNED_AT,
        learned_at=T_NOW,
        source_statement_ref="stmt://user/x",
    )
    with pytest.raises(RetrospectiveAnnotationError) as excinfo:
        lens.attach_annotation(conflicting)
    assert excinfo.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert len(lens.annotations_for(ENTITY_LAOWANG)) == 1


# ---------------------------------------------------------------------------
# 契约校验与防污染
# ---------------------------------------------------------------------------


def test_13_annotation_contract_validation() -> None:
    base = dict(
        annotation_id="anno-x",
        target_entity_id=ENTITY_LAOWANG,
        semantic_overlay="疑似欺诈",
        target_time_start=DRINKING_NIGHT,
        target_time_end=PARTNERSHIP_SIGNED_AT,
        learned_at=T_NOW,
        recorded_at=T_NOW,
        source_statement_ref="stmt://user/x",
    )

    # 朴素（无时区）时间戳一律拒绝。
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "target_time_start": DRINKING_NIGHT.replace(tzinfo=None)})
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "learned_at": T_NOW.replace(tzinfo=None)})

    # 终点早于起点。
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "target_time_end": DRINKING_NIGHT - timedelta(days=1)})

    # 倒写历史：假装在切片结束之前就「学到」。
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "learned_at": DRINKING_NIGHT})

    # recorded_at 早于 learned_at。
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "recorded_at": T_NOW - timedelta(seconds=1)})

    # 空白字段与未知字段。
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "semantic_overlay": "   "})
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(**{**base, "rewrite_history": True})


def test_14_query_argument_validation() -> None:
    lens, _ = _laowang_lens()
    with pytest.raises(RetrospectiveAnnotationError) as e1:
        lens.query_historical_slice("  ", DRINKING_NIGHT)
    assert e1.value.code == ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ValueError):
        lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT.replace(tzinfo=None))
    with pytest.raises(ValueError):
        lens.query_historical_slice(
            ENTITY_LAOWANG, DRINKING_NIGHT, as_of_cutoff=T_NOW.replace(tzinfo=None)
        )
    with pytest.raises(TypeError):
        lens.attach_annotation("不是注记")  # type: ignore[arg-type]


def test_15_view_is_fresh_copy_and_fact_ledger_tamper_isolated() -> None:
    caller_payload = {"source_kind": "chat", "modality": "text", "value": "原始对话"}
    lens = EpistemicWorldLens()
    fact_id = lens.attach_fact(
        entity_id=ENTITY_LAOWANG, valid_time_start=DRINKING_NIGHT, payload=caller_payload
    )
    # 调用方事后篡改原对象：透镜冻结底账不受污染。
    caller_payload["value"] = "被倒写的对话"

    view = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    assert view["facts"][0]["payload"]["value"] == "原始对话"
    assert view["facts"][0]["sha256"] == canonical_fact_sha256(
        {"source_kind": "chat", "modality": "text", "value": "原始对话"}
    )
    assert view["facts"][0]["fact_id"] == fact_id

    # 篡改查询返回值：再次查询依旧返回原貌。
    view["facts"][0]["payload"]["value"] = "二次倒写"
    again = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    assert again["facts"][0]["payload"]["value"] == "原始对话"
    assert again["facts"][0]["sha256"] == view["facts"][0]["sha256"]


def test_16_rendering_is_deterministic() -> None:
    lens, _ = _laowang_lens()
    lens.attach_annotation(_make_fraud_annotation())
    v1 = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    v2 = lens.query_historical_slice(ENTITY_LAOWANG, DRINKING_NIGHT)
    assert json.dumps(v1, sort_keys=True, ensure_ascii=False) == json.dumps(
        v2, sort_keys=True, ensure_ascii=False
    )
