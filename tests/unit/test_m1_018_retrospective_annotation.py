"""M1-018 内心数据反哺与历史重估注记管线 —— 10000 级压测单测。

高阶实战场景（首席架构部工单规约，拒绝低幼样例）：

用户两年前（T0）与核心技术合伙人签署《Pre-A 轮联合孵化与股权代持对赌
协议》。730 天内系统累积 18,000 条客观事实 Observation（技术评审纪要、
商业汇款凭证、深夜高压谈判的心率变异度与皮质醇体征、重大合同、关联
离岸空壳资金流水线索）。第 730 天（T_today），司法机关下达冻结查封
裁定书，证实该合伙人自设立之初即利用关联离岸空壳公司转移核心知识
产权并隐匿巨额对外连带担保。

四大硬门禁：
1. 历史事实绝对不可变：18,000 条原始 Observation 的 SHA-256 物理哈希
   在裁定进入后 100% 保持一致；存储引擎对对象数据零 UPDATE / DELETE；
2. 今天只写入一条 RetrospectiveAnnotation（learned_at=T_today，
   valid_time_range=[T0, T_today]，挂载司法查封与欺诈重估注记）；
3. BiTemporalEpistemicLens：T0+100 天精准还原当时商业信任状态
   （active 图层为空）；None 精确叠加外挂重估图层；
4. SingleHopCascadeIsolator：10,000 节点五层依赖网络，反向失效严格
   只标记直接消费该认知的 1 级节点（严格等于 10 个），遍历深度严格
   为 1，彻底掐灭级联递归算力雪崩。
"""

from __future__ import annotations

import json
import pathlib
import random
import re
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation import (
    BiTemporalEpistemicLens,
    CanonicalIntegrityAnchor,
    CascadeIsolationResult,
    DuplicateAnnotationError,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationLedger,
    RetrospectiveAnnotationType,
    SingleHopCascadeIsolator,
    UnknownCognitionNodeError,
    combined_history_digest,
    canonical_payload_digest,
)

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "aios_core"
    / "world"
    / "retrospective_annotation.py"
)
STORE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "aios_core"
    / "storage"
    / "sqlite_store.py"
)

UTC = timezone.utc
T0 = datetime(2024, 9, 16, 9, 0, 0, tzinfo=UTC)          # 对赌协议签署日
T_TODAY = T0 + timedelta(days=730)                        # 司法裁定日（第730天）
T_HIST = T0 + timedelta(days=100)                         # 历史认知还原点
N_OBSERVATIONS = 18_000
CHUNK = 1_000

PARTNER_ENTITY_ID = "ent_partner_shadow"
OFFSHORE_SPVS = (
    "SPV-Cayman-Aegir-001",
    "SPV-BVI-Hryvan-002",
    "SPV-SG-Lokabrenna-003",
)


# ----------------------------------------------------------------------
# 730 天高熵商业观测流生成（确定性，可重放）
# ----------------------------------------------------------------------

def _observation_value(i: int, rng: random.Random) -> tuple[str, str, dict]:
    """按确定性比例混合六类高熵商业观测，返回 (source_kind, modality, value)。"""
    bucket = i % 6
    if bucket == 0:  # 重大合同与补充协议
        if i == 0:
            return "contract_repository", "text", {
                "doc": "《Pre-A轮联合孵化与股权代持对赌协议》",
                "counterparty": PARTNER_ENTITY_ID,
                "equity_proxy_pct": 34.0,
                "vam_clause": "2026-09 前未达 B 轮估值触发股权回购",
            }
        return "contract_repository", "text", {
            "doc": f"补充条款与知识产权归属修订 v{i % 9}",
            "counterparty": PARTNER_ENTITY_ID,
            "ip_assignment": f"专利族 ZL-2024-{rng.randint(10000, 99999)}",
        }
    if bucket == 1:  # 商业汇款凭证
        return "bank_statement", "numeric", {
            "wire_amount_cny": round(rng.uniform(8e4, 4.7e6), 2),
            "beneficiary": rng.choice((PARTNER_ENTITY_ID, *OFFSHORE_SPVS)),
            "purpose": rng.choice(("孵化款", "代持出资", "联合采购预付", "顾问费")),
        }
    if bucket == 2:  # 深夜高压谈判心率变异度
        return "wearable_hrv", "bio_metric", {
            "hrv_ms": round(rng.uniform(18, 52), 1),
            "window": "01:30-02:45",
            "context": "深夜高压谈判（对赌条款/回购罚则）",
        }
    if bucket == 3:  # 皮质醇体征
        return "cortisol_panel", "bio_metric", {
            "cortisol_ug_dl": round(rng.uniform(8.2, 27.6), 2),
            "sample": "晨间唾液",
        }
    if bucket == 4:  # 技术评审纪要（核心知识产权）
        return "tech_review", "text", {
            "module": rng.choice(("推理内核", "多模态管线", "索引引擎", "调度器")),
            "ip_asset": f"核心代码库/专利族 ZL-2024-{rng.randint(10000, 99999)}",
            "attendees": [PARTNER_ENTITY_ID, "user_founder"],
        }
    # 关联离岸空壳资金流水线索
    return "offshore_ledger", "numeric", {
        "entity": rng.choice(OFFSHORE_SPVS),
        "flow_cny": round(rng.uniform(2e5, 9.1e6), 2),
        "linked_party": PARTNER_ENTITY_ID,
    }


def build_observation(i: int, rng: random.Random) -> Observation:
    at = T0 + timedelta(minutes=i * 58)  # 均匀铺满 730 天
    if i == N_OBSERVATIONS - 1:
        # 第 730 天：司法机关冻结查封裁定书（客观事实进入系统）
        return Observation(
            object_id="obs_preA_17999",
            subject_id="user_founder",
            occurred=TemporalExtent.point(T_TODAY),
            learned_at=T_TODAY,
            recorded_at=T_TODAY,
            created_by="m1-018-seed",
            source_kind="judicial_record",
            modality="text",
            value={
                "doc": "冻结查封裁定书",
                "court": "市中级人民法院",
                "finding": (
                    "合伙人自设立之初利用关联离岸空壳公司转移核心知识产权，"
                    "并隐匿巨额对外连带担保"
                ),
                "frozen_assets": "涉案股权与知识产权打包冻结",
            },
        )
    source_kind, modality, value = _observation_value(i, rng)
    return Observation(
        object_id=f"obs_preA_{i:05d}",
        subject_id="user_founder",
        occurred=TemporalExtent.point(at),
        learned_at=at,
        recorded_at=at,
        created_by="m1-018-seed",
        source_kind=source_kind,
        modality=modality,
        value=value,
    )


def seed_world_store(store: SQLiteWorldStore) -> None:
    rng = random.Random(730)
    for chunk_index in range(N_OBSERVATIONS // CHUNK):
        objects = [
            build_observation(i, rng)
            for i in range(chunk_index * CHUNK, (chunk_index + 1) * CHUNK)
        ]
        store.commit(
            objects,
            OperationRequest(
                operation_id=f"op_seed_preA_{chunk_index:02d}",
                session_id="session_m1_018_seed",
                operation_name="world.commit",
                arguments={"chunk": chunk_index, "scenario": "preA_incubation"},
                expected_world_revision=store.current_world_revision(),
                reason="seed 730-day pre-A incubation observation chain",
                idempotency_key=f"idem_seed_preA_{chunk_index:02d}",
            ),
        )


def digest_map_of(store: SQLiteWorldStore) -> dict[str, str]:
    payloads = store.list_payloads(object_type=ObjectType.OBSERVATION)
    return {p["object_id"]: canonical_payload_digest(p) for p in payloads}


def build_annotation(digests: dict[str, str]) -> RetrospectiveAnnotation:
    return RetrospectiveAnnotation(
        annotation_id="ra_partner_shadow_freeze_730d",
        subject_entity_id=PARTNER_ENTITY_ID,
        annotation_type=RetrospectiveAnnotationType.JUDICIAL_FREEZE,
        headline=(
            "司法机关冻结查封裁定：核心合伙人涉关联离岸空壳转移核心知识"
            "产权并隐匿巨额对外连带担保"
        ),
        notes=(
            "欺诈重估：自设立之初的股权代持与对赌安排需按交易对手欺诈"
            "重新定性，原『技术合伙人高度可信』认知降级",
            "信任基线重置：730 天内全部基于该合伙人信任的衍生认知进入"
            "单跳失效复核（严禁多级级联）",
        ),
        valid_from=T0,
        valid_until=T_TODAY,
        occurred_at=T_TODAY,
        learned_at=T_TODAY,
        recorded_at=T_TODAY,
        source_refs=(ObjectRef(object_id="obs_preA_17999", revision=1),),
        target_object_refs=(
            ObjectRef(object_id="obs_preA_00000", revision=1),
            ObjectRef(object_id="obs_preA_01000", revision=1),
            ObjectRef(object_id="obs_preA_17999", revision=1),
        ),
        integrity_anchors=tuple(
            CanonicalIntegrityAnchor(object_id=oid, payload_sha256=digest)
            for oid, digest in sorted(digests.items())
        ),
        created_by="ai_worker:m1-018",
    )


# ======================================================================
# 门禁一：历史事实绝对不可变（18000 条 SHA-256 物理哈希 100% 一致）
# ======================================================================

def test_gate1_history_is_physically_immutable_under_ruling(tmp_path) -> None:
    store = SQLiteWorldStore(tmp_path / "world_m1_018.db")
    seed_world_store(store)
    assert store.current_world_revision() == N_OBSERVATIONS // CHUNK

    digests_before = digest_map_of(store)
    combined_before = combined_history_digest(digests_before)
    assert len(digests_before) == N_OBSERVATIONS

    revision_before_annotation = store.current_world_revision()

    # 裁定进入：只追加注记图层，不触碰世界存储一个字节
    ledger = RetrospectiveAnnotationLedger()
    ledger.append(build_annotation(digests_before))

    # 全量复算：18000 条物理哈希 100% 一致
    digests_after = digest_map_of(store)
    assert len(digests_after) == N_OBSERVATIONS
    assert digests_after == digests_before
    assert combined_history_digest(digests_after) == combined_before
    # 世界存储零提交（注记不产生任何新 world revision）
    assert store.current_world_revision() == revision_before_annotation
    # 注记固化的完整性锚与真实历史逐条一致
    annotation = ledger.annotations_active_at(T_TODAY)[0]
    assert {a.object_id: a.payload_sha256 for a in annotation.integrity_anchors} == (
        digests_after
    )


def test_gate1_storage_engine_is_append_only_redline() -> None:
    """红线探针（AST 级，不受文档字符串误伤）：
    - 引擎对对象数据零 UPDATE/DELETE；唯一允许的 UPDATE 仅限 world_meta
      全局版本计数器（元数据递增，非历史记录改写）；
    - 注记模块零 sqlite3 导入、零任何 SQL execute 调用面。"""
    import ast

    source = STORE_PATH.read_text(encoding="utf-8")
    assert "DELETE FROM" not in source, "append-only engine must never DELETE"
    updated_tables = re.findall(r"UPDATE\s+([a-zA-Z_]\w*)", source)
    assert set(updated_tables) <= {"world_meta"}, (
        f"object data tables must never be UPDATEd, found: {updated_tables}"
    )

    module_tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(module_tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0] != "sqlite3" for alias in node.names
            ), "annotation module must never import sqlite3"
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "sqlite3"
        if isinstance(node, ast.Attribute) and node.attr in (
            "execute",
            "executemany",
            "executescript",
        ):
            raise AssertionError(
                "annotation module must never issue raw SQL statements"
            )


def test_gate1_frozen_model_blocks_in_place_mutation() -> None:
    ledger = RetrospectiveAnnotationLedger()
    annotation = build_annotation({"obs_x": "a" * 64})
    ledger.append(annotation)
    with pytest.raises(ValidationError):
        annotation.headline = "篡改后的标题"  # type: ignore[misc]


# ======================================================================
# 门禁二：今天只写入一条重估注记
# ======================================================================

def test_gate2_single_annotation_mounted_today() -> None:
    digests = {f"obs_preA_{i:05d}": canonical_payload_digest({"i": i}) for i in range(50)}
    ledger = RetrospectiveAnnotationLedger()
    annotation = build_annotation(digests)
    assert ledger.append(annotation) is True
    assert ledger.append(annotation) is False          # 幂等重放
    assert len(ledger) == 1                            # 今天只写入一条

    mounted = ledger.annotations_active_at(T_TODAY)
    assert len(mounted) == 1
    only = mounted[0]
    assert only.learned_at == T_TODAY                  # learned_at = T_today
    assert (only.valid_from, only.valid_until) == (T0, T_TODAY)
    assert only.annotation_type == RetrospectiveAnnotationType.JUDICIAL_FREEZE
    joined_notes = " | ".join(only.notes)
    assert "司法" in only.headline or "冻结查封" in only.headline
    assert "欺诈重估" in joined_notes                  # 欺诈重估注记已挂载
    assert "单跳失效复核" in joined_notes              # 级联隔离纪律已挂载
    assert len(only.integrity_anchors) == 50

    with pytest.raises(DuplicateAnnotationError):
        ledger.append(
            annotation.model_copy(update={"headline": "同 ID 不同内容"})
        )


# ======================================================================
# 门禁三：双时间认知透镜
# ======================================================================

def test_gate3_bitemporal_lens_restores_historical_epistemic_state(tmp_path) -> None:
    store = SQLiteWorldStore(tmp_path / "world_lens.db")
    seed_world_store(store)
    digests = digest_map_of(store)
    ledger = RetrospectiveAnnotationLedger()
    ledger.append(build_annotation(digests))
    lens = BiTemporalEpistemicLens(ledger)

    # 视角一：T0+100 天——系统必须忠实还原"当时确实还信任合伙人"
    historical = lens.view(T_HIST, subject_entity_id=PARTNER_ENTITY_ID)
    assert historical.view_cutoff == T_HIST
    assert historical.active_annotations == ()         # 重估图层为空
    assert historical.suppressed_annotations == (
        "ra_partner_shadow_freeze_730d",
    )
    assert historical.historical_fact_layer_intact is True
    # 事实层完整：18000 条原始观测仍然全量在库
    assert len(digest_map_of(store)) == N_OBSERVATIONS

    # 视角二：当下（as_of_cutoff=None）——历史事实完整保留 + 外挂图层精确叠加
    current = lens.view(None, now=T_TODAY, subject_entity_id=PARTNER_ENTITY_ID)
    assert current.view_cutoff == T_TODAY
    assert len(current.active_annotations) == 1
    assert current.active_annotations[0].annotation_id == (
        "ra_partner_shadow_freeze_730d"
    )
    assert current.suppressed_annotations == ()
    assert len(current.active_annotations[0].integrity_anchors) == N_OBSERVATIONS
    # 历史事实未被改写：两视角下事实层摘要完全一致
    assert combined_history_digest(digest_map_of(store)) == (
        combined_history_digest(digests)
    )


# ======================================================================
# 门禁四：单跳隔离杜绝雪崩（10000 节点五层网络压测）
# ======================================================================

def _build_10k_dependency_network(isolator: SingleHopCascadeIsolator) -> dict:
    """1 源 + L1(10) + L2(200) + L3(1000) + L4(4000) + L5(4789) = 10000 节点。"""
    source = "cog_partner_trustworthy"
    isolator.register_node(source)
    l1 = [f"cog_l1_{k:02d}" for k in range(10)]
    l2 = [f"cog_l2_{a:02d}_{b:02d}" for a in range(10) for b in range(20)]
    l3 = [f"cog_l3_{a:03d}_{b:02d}" for a in range(200) for b in range(5)]
    l4 = [f"cog_l4_{a:04d}_{b:02d}" for a in range(1000) for b in range(4)]
    l5 = [f"cog_l5_{n:05d}" for n in range(4789)]
    for node in l1:
        isolator.register_dependency(node, source)
    for idx, consumer in enumerate(l2):
        isolator.register_dependency(consumer, l1[idx % 10])
    for idx, consumer in enumerate(l3):
        isolator.register_dependency(consumer, l2[idx % 200])
    for idx, consumer in enumerate(l4):
        isolator.register_dependency(consumer, l3[idx % 1000])
    for idx, consumer in enumerate(l5):
        isolator.register_dependency(consumer, l4[idx % 4000])
    return {
        "source": source,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "l4": l4,
        "l5": l5,
    }


def test_gate4_single_hop_isolation_on_10k_network() -> None:
    isolator = SingleHopCascadeIsolator()
    net = _build_10k_dependency_network(isolator)
    assert isolator.node_count == 10_000

    result = isolator.invalidate_direct_consumers(net["source"])

    # 遍历深度严格为 1（契约域物理封死 [1,1]）
    assert isinstance(result, CascadeIsolationResult)
    assert result.traversal_hops == 1
    # 被标记 is_stale=True 的节点严格等于直接消费该认知的 10 个一级节点
    assert result.marked_stale_count == 10
    assert set(result.stale_node_ids) == set(net["l1"])
    assert result.stale_node_ids == tuple(sorted(net["l1"]))
    # 全量扫描：10000 节点中仅 10 个一级节点被标记；源与更深下游全部原状
    assert isolator.is_stale(net["source"]) is False
    assert all(isolator.is_stale(n) for n in net["l1"])
    untouched = net["l2"] + net["l3"] + net["l4"] + net["l5"]
    assert len(untouched) == 9_989
    assert all(not isolator.is_stale(n) for n in untouched)
    assert isolator.stale_nodes() == tuple(sorted(net["l1"]))
    # 级联雪崩扼杀量：递归式遍历本会访问全部 9999 个下游节点；
    # 实际只触碰 10 个，9989 个被结构性隔离（远超工单点名的 210 次量级）
    assert result.suppressed_cascade_count == 9_989
    assert result.suppressed_cascade_count >= 210
    # 性能：万节点网络单跳失效必须远低于调度预算
    assert result.elapsed_ms < 100.0


def test_gate4_isolation_is_idempotent_replay() -> None:
    isolator = SingleHopCascadeIsolator()
    net = _build_10k_dependency_network(isolator)
    first = isolator.invalidate_direct_consumers(net["source"])
    second = isolator.invalidate_direct_consumers(net["source"])
    assert first.model_dump(exclude={"elapsed_ms"}) == (
        second.model_dump(exclude={"elapsed_ms"})
    )
    assert isolator.stale_nodes() == tuple(sorted(net["l1"]))


def test_gate4_unknown_source_rejected_not_silent() -> None:
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("cog_exists")
    with pytest.raises(UnknownCognitionNodeError):
        isolator.invalidate_direct_consumers("cog_ghost")
    with pytest.raises(UnknownCognitionNodeError):
        isolator.is_stale("cog_ghost")


def test_gate4_source_without_consumers_marks_nothing() -> None:
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("cog_lonely")
    result = isolator.invalidate_direct_consumers("cog_lonely")
    assert result.marked_stale_count == 0
    assert result.traversal_hops == 1
    assert result.suppressed_cascade_count == 0


# ======================================================================
# 契约校验与摘要敏感性
# ======================================================================

def test_digest_is_tamper_evident() -> None:
    payload_a = {"object_id": "obs_1", "value": {"amount": 4_700_000}}
    payload_b = {"object_id": "obs_1", "value": {"amount": 4_700_001}}
    assert canonical_payload_digest(payload_a) != canonical_payload_digest(payload_b)
    base = {"obs_1": canonical_payload_digest(payload_a)}
    assert combined_history_digest(base) != combined_history_digest(
        {**base, "obs_2": canonical_payload_digest(payload_b)}
    )
    # 键序不敏感（规范化）
    assert canonical_payload_digest({"a": 1, "b": 2}) == canonical_payload_digest(
        {"b": 2, "a": 1}
    )


def test_annotation_contract_rejects_illegal_time_semantics() -> None:
    digests = {"obs_x": "a" * 64}
    base = build_annotation(digests)
    # 追溯适用窗越过获知时刻：契约必须拒绝（model_validate 显式重跑校验器）
    tampered = base.model_dump()
    tampered["valid_until"] = T_TODAY + timedelta(days=1)
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation.model_validate(tampered)
    # 浮动引用（未锚定 revision）：历史引用必须精确到版本
    unpinned = base.model_dump(mode="json")
    unpinned["source_refs"] = [{"object_id": "obs_preA_17999", "revision": None}]
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation.model_validate(unpinned)


def test_ledger_rejects_unanchored_or_naive_time() -> None:
    digests = {"obs_x": "a" * 64}
    annotation = build_annotation(digests)
    serialized = annotation.model_dump_json(exclude_none=True)
    naive = json.loads(serialized)
    # Pydantic v2 序列化 UTC 时间为 RFC3339 的 "Z" 或 "+00:00" 后缀，均剥掉
    naive["learned_at"] = re.sub(r"(Z|\+00:00)$", "", naive["learned_at"])
    assert "T" in naive["learned_at"]
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation.model_validate(naive)
