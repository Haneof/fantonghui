"""M1-018 验收测试：认知反向传播语义图层契约（复盘注记 / 双时间透镜 / 单跳隔离）。

工单：``governance/dispatches/TASK_DISPATCH_AGENT_5_M1_018.md``
融合档案：``docs/fusion_dossier/02_*`` M1-018 行 + ``04_*`` 争议二终审（**严格单跳**）

高阶实战场景（严禁低幼化样例）
--------------------------------------------------------------------------
两年前签署《Pre-A 轮联合孵化与股权代持对赌协议》；730 天内累积 **18,000 条**客观事实
Observation 链（技术评审、商业汇款凭证、深夜高压谈判时的心率变异度与皮质醇体征、重大合同、
知识产权登记、离岸主体文件……）。第 730 天司法机关下达冻结查封裁定书，证实合伙人自设立之初
即利用关联离岸空壳公司转移核心知识产权并隐匿巨额对外连带担保。

四大硬门禁 ↔ 本文件用例
--------------------------------------------------------------------------
1. 历史事实绝对不可变 —— ``test_gate1_*``（SHA-256 逐条 + 原始字节 + 触发器审计 + 负向对照）
2. 今天只写一条注记   —— ``test_gate2_*``
3. 双时间认知透镜     —— ``test_gate3a_*``（as_of=T0+100 天必须还原当时认知）/ ``test_gate3b_*``
4. 单跳隔离防雪崩     —— ``test_gate4a_*``（210 次大模型雪崩被掐灭）/ ``test_gate4b_*``（万级 5 层图）
"""

from __future__ import annotations

import ast
import gc
import hashlib
import inspect
import random
import sqlite3
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    Claim,
    Observation,
    OperationRequest,
    TemporalExtent,
)
from aios_core.contracts.enums import ClaimType, ErrorCode, KnowledgeState, ObjectType
from aios_core.errors import AIOSProtocolError
from aios_core.query import EntityHyperlinkGraphTraverser
from aios_core.storage import SQLiteWorldStore
from aios_core.world import retrospective_annotation as ra
from aios_core.world.retrospective_annotation import (
    MAX_RECOMPUTE_CONCURRENCY,
    AnnotationKind,
    AnnotationReceipt,
    BiTemporalEpistemicLens,
    DuplicateAnnotationError,
    EpistemicSlice,
    EpistemicWorldLens,
    HashLedgerDiff,
    HistoryMutationDetectedError,
    KnowledgeMode,
    ObservationHashLedger,
    PhysicalChainIndex,
    RetroactiveWriteDeniedError,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationLog,
    RetrospectiveAnnotationWriter,
    SingleHopCascadeIsolator,
    UnknownTargetEntityError,
    annotations_from_store,
    observations_linked_to_entity,
)

# ===========================================================================
# 场景常量
# ===========================================================================

T_TODAY = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)
T0 = T_TODAY - timedelta(days=730)          # 协议签署日（两年前）
RULING_AT = T_TODAY - timedelta(hours=3)    # 司法机关下达冻结查封裁定书
PARTNER_ENTITY = "ent_partner"
SUBJECT_ID = "sub_joint_venture"

OBSERVATION_TOTAL = 18_000
DAILY_SAMPLES = 24                          # 每天固定采样条数
MAJOR_DOCUMENTS = 479                       # 重大合同/凭证/登记文件（+ 1 条裁定书 = 18,000）

GATE_ANNOTATION_ID = "ann_judicial_freeze_730d"

#: 万级依赖网络：1 级 10 / 2 级 200 / 3 级 1000 / 4 级 4000 / 5 级 8000（共 5 层）
FIVE_LAYER_FANOUT = (10, 200, 1_000, 4_000, 8_000)

RULING_TEXT = (
    "民事裁定书：冻结查封该合伙人全部股权与关联主体资产；司法审计证实其自设立之初即利用"
    "关联离岸空壳公司转移核心知识产权并隐匿巨额对外连带担保"
)
OVERLAY_TEXT = (
    "司法查封 + 欺诈重估：合作信任状态自签署日起即建立在蓄意隐瞒之上——"
    "该合伙人利用关联离岸空壳公司转移核心知识产权、隐匿对外连带担保，原“可信联合创始人”"
    "标注整体失效，730 天内的技术评审、汇款凭证与深夜谈判记录需按欺诈场景重新解释"
)


# ===========================================================================
# 场景数据生成（高熵商业事实链）
# ===========================================================================

_TECH_REVIEW = "技术评审：核心 IP 归属与代持条款复核，结论待补强证据"
_REMITTANCE = "商业汇款凭证：Pre-A 联合孵化款到账，付方与代持主体名称不一致"
_NEGOTIATION = "深夜高压谈判记录：对赌回购条款与股权代持边界未达成一致"
_CONTRACT = "重大合同：联合孵化与股权代持对赌协议补充条款签署"
_IP_FILING = "知识产权登记：核心专利申请人变更记录待核验"
_OFFSHORE = "离岸主体文件：BVI 壳公司董事变更与股权质押文件"
_BOARD = "董事会决议：技术成果归属与连带担保披露事项"


def _generate_observation_payloads() -> list[Observation]:
    """生成 18,000 条客观事实（确定性；含生理体征与司法文书）。"""
    rng = random.Random(20260916)
    payloads: list[Observation] = []
    rotating = [_TECH_REVIEW, _REMITTANCE, _NEGOTIATION, _CONTRACT, _IP_FILING, _OFFSHORE, _BOARD]

    for day in range(730):
        day_start = T0 + timedelta(days=day)
        for slot in range(DAILY_SAMPLES):
            at = day_start + timedelta(minutes=slot * 60)
            index = len(payloads)
            if slot == 0:
                # 深夜高压谈判时的心率变异度（RMSSD）
                text = f"心率变异度体征：RMSSD={rng.uniform(18.0, 64.0):.1f}ms（高压谈判夜）"
                modality, source_kind, unit = "physiological", "wearable_band", "ms"
            elif slot == 1:
                # 皮质醇体征
                text = f"皮质醇体征：{rng.uniform(180.0, 620.0):.1f}nmol/L（夜间采样）"
                modality, source_kind, unit = "physiological", "wearable_band", "nmol/L"
            elif slot == 2:
                text = f"{_NEGOTIATION}（第 {day} 天深夜 23:40 通话，时长 {rng.randint(35, 180)} 分钟）"
                modality, source_kind, unit = "text", "call_transcript", ""
            else:
                text = f"{rotating[(day + slot) % len(rotating)]}（第 {day} 天 / 序号 {index}）"
                modality = "text" if slot % 3 else "document"
                source_kind = "meeting_note" if slot % 3 else "document_repository"
                unit = ""
            payloads.append(
                Observation(
                    object_id=f"obs_{index:06d}",
                    subject_id=SUBJECT_ID,
                    occurred=TemporalExtent.point(at),
                    learned_at=at,
                    recorded_at=at,
                    created_by="ingest_pipeline",
                    source_kind=source_kind,
                    modality=modality,
                    value=text,
                    unit=unit or None,
                    metadata={"day_index": day, "slot": slot},
                )
            )

    for major in range(MAJOR_DOCUMENTS):
        at = T0 + timedelta(days=(major * 730) // MAJOR_DOCUMENTS, hours=14 + (major % 8))
        index = len(payloads)
        text = f"{rotating[major % len(rotating)]}（重大事项 #{major}，编号 {index}）"
        payloads.append(
            Observation(
                object_id=f"obs_{index:06d}",
                subject_id=SUBJECT_ID,
                occurred=TemporalExtent.point(at),
                learned_at=at,
                recorded_at=at,
                created_by="ingest_pipeline",
                source_kind="document_repository",
                modality="document",
                value=text,
                metadata={"major_document": major},
            )
        )

    payloads.append(
        Observation(
            object_id=f"obs_{len(payloads):06d}",
            subject_id=SUBJECT_ID,
            occurred=TemporalExtent.point(RULING_AT),
            learned_at=RULING_AT,
            recorded_at=RULING_AT,
            created_by="court_feed",
            source_kind="judicial_ruling",
            modality="document",
            value=RULING_TEXT,
            metadata={"authority": "intermediate_court", "case_type": "freeze_and_seizure"},
        )
    )
    assert len(payloads) == OBSERVATION_TOTAL, f"场景必须恰好 {OBSERVATION_TOTAL} 条事实"
    return payloads


def _observation_ids(payloads: list[Observation]) -> list[str]:
    return [payload.object_id for payload in payloads]


# ===========================================================================
# 只读 SQLite 审计工具（测试层可直接使用 sqlite3：业务代码不得）
# ===========================================================================

AUDIT_TABLE = "_m1_018_mutation_audit"


def _install_mutation_audit_triggers(db_path: Any) -> None:
    """在历史表上挂 AFTER UPDATE / DELETE 触发器：任何改写尝试都会被记录。"""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {AUDIT_TABLE}(
                kind TEXT NOT NULL, table_name TEXT NOT NULL, recorded_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS _m1_018_no_update
            AFTER UPDATE ON object_revisions
            BEGIN
                INSERT INTO {AUDIT_TABLE} VALUES ('UPDATE', 'object_revisions', datetime('now'));
            END;
            CREATE TRIGGER IF NOT EXISTS _m1_018_no_delete
            AFTER DELETE ON object_revisions
            BEGIN
                INSERT INTO {AUDIT_TABLE} VALUES ('DELETE', 'object_revisions', datetime('now'));
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def _mutation_attempts(db_path: Any) -> list[tuple[str, str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            f"SELECT kind, table_name FROM {AUDIT_TABLE} ORDER BY recorded_at"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]
    finally:
        conn.close()


def _raw_observation_payloads(db_path: Any) -> dict[str, str]:
    """读取历史事实的**存储层原始字节**（物理哈希的输入）。"""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT object_id, payload_json FROM object_revisions "
            "WHERE object_type = 'observation' ORDER BY object_id"
        ).fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


def _object_revision_rows(db_path: Any, object_type: str) -> list[tuple[str, int, str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        return [
            (row[0], row[1], row[2])
            for row in conn.execute(
                "SELECT object_id, revision, world_revision FROM object_revisions "
                "WHERE object_type = ? ORDER BY object_id",
                (object_type,),
            ).fetchall()
        ]
    finally:
        conn.close()


def _scalar(db_path: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ===========================================================================
# 场景夹具
# ===========================================================================


@dataclass(frozen=True)
class _Scenario:
    db_path: Any
    store: SQLiteWorldStore
    observation_ids: tuple[str, ...]
    annotation: RetrospectiveAnnotation
    receipt: AnnotationReceipt
    ledger: ObservationHashLedger
    raw_ledger: ObservationHashLedger
    diff_after: HashLedgerDiff
    raw_diff_after: HashLedgerDiff
    mutation_attempts: tuple[tuple[str, str], ...]
    revision_before: int
    revision_after: int
    rows_before: int
    lens: BiTemporalEpistemicLens
    index: PhysicalChainIndex
    ruling_observation_id: str

    def slice(self, target_time: Any, as_of_cutoff: datetime | None = None) -> EpistemicSlice:
        return self.lens.query_historical_slice(PARTNER_ENTITY, target_time, as_of_cutoff)


def _build_annotation(learned_at: datetime = T_TODAY) -> RetrospectiveAnnotation:
    return RetrospectiveAnnotation(
        annotation_id=GATE_ANNOTATION_ID,
        target_entity_id=PARTNER_ENTITY,
        semantic_overlay=OVERLAY_TEXT,
        target_time_start=T0,
        target_time_end=T_TODAY,
        learned_at=learned_at,
        source_statement_ref="obs_017999",
        annotation_kind=AnnotationKind.JUDICIAL_FREEZE,
        secondary_kinds=(AnnotationKind.FRAUD_REASSESSMENT,),
        confidence=0.97,
    )


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    """构建 730 天 / 18,000 条事实的真实世界，并执行"今天打标签"全流程（只读审计齐备）。"""
    db_path = tmp_path_factory.mktemp("m1_018") / "world.db"
    store = SQLiteWorldStore(db_path)

    observation_payloads = _generate_observation_payloads()
    observations = list(observation_payloads)
    revision = store.current_world_revision()
    for start in range(0, len(observations), 2_000):
        chunk = observations[start : start + 2_000]
        store.commit(
            chunk,
            OperationRequest(
                operation_name="world.commit",
                expected_world_revision=revision,
                reason="M1-018 场景：730 天客观事实链摄入",
                idempotency_key=f"m1-018-ingest-{start}",
            ),
        )
        revision += 1

    _install_mutation_audit_triggers(db_path)

    # —— 打标签之前：捕获历史台账（规范化字节 + 存储层原始字节）——
    payloads_before = store.list_payloads(object_type=ObjectType.OBSERVATION)
    ledger = ObservationHashLedger.capture(payloads_before)
    raw_ledger = ObservationHashLedger.from_raw_payloads(_raw_observation_payloads(db_path))
    rows_before = len(store.list_payloads())
    revision_before = store.current_world_revision()

    annotation = _build_annotation()
    writer = RetrospectiveAnnotationWriter(store)
    receipt = writer.write(
        annotation,
        history_ledger=ledger,
        subject_id=SUBJECT_ID,
        created_by="core_retrospective_review",
        history_payloads=payloads_before,
    )

    # —— 打标签之后：逐条核对历史是否被动过 ——
    payloads_after = store.list_payloads(object_type=ObjectType.OBSERVATION)
    diff_after = ledger.verify(payloads_after)
    raw_diff_after = raw_ledger.verify_raw(_raw_observation_payloads(db_path))
    attempts = tuple(_mutation_attempts(db_path))
    revision_after = store.current_world_revision()

    entity_links = {PARTNER_ENTITY: [payload["object_id"] for payload in payloads_after]}
    index = PhysicalChainIndex(payloads_after, entity_links=entity_links)
    lens = BiTemporalEpistemicLens(index, annotations=annotations_from_store(store))

    return _Scenario(
        db_path=db_path,
        store=store,
        observation_ids=tuple(_observation_ids(observations)),
        annotation=annotation,
        receipt=receipt,
        ledger=ledger,
        raw_ledger=raw_ledger,
        diff_after=diff_after,
        raw_diff_after=raw_diff_after,
        mutation_attempts=attempts,
        revision_before=revision_before,
        revision_after=revision_after,
        rows_before=rows_before,
        lens=lens,
        index=index,
        ruling_observation_id="obs_017999",
    )


# ===========================================================================
# 门禁 1：历史事实绝对不可变
# ===========================================================================


def test_gate1_ledger_covers_all_18000_physical_facts(scenario: _Scenario) -> None:
    assert scenario.ledger.count == OBSERVATION_TOTAL
    assert scenario.raw_ledger.count == OBSERVATION_TOTAL
    assert scenario.ledger.mode == "canonical"
    assert scenario.raw_ledger.mode == "raw"
    assert len(scenario.ledger.root_hash) == 64 and len(scenario.raw_ledger.root_hash) == 64
    assert len(scenario.observation_ids) == OBSERVATION_TOTAL
    assert len(set(scenario.observation_ids)) == OBSERVATION_TOTAL


def test_gate1_history_hashes_are_byte_identical_after_annotation(scenario: _Scenario) -> None:
    """验收硬门禁 1：加注后 18,000 条原始事实的 SHA-256 必须 100% 一致。"""
    diff = scenario.diff_after
    assert diff.mismatched_ids == (), f"被篡改的历史事实：{diff.mismatched_ids[:5]}"
    assert diff.missing_ids == (), f"被删除的历史事实：{diff.missing_ids[:5]}"
    assert diff.added_ids == (), "打标签不得新增任何 Observation"
    assert diff.matched == OBSERVATION_TOTAL
    assert diff.root_hash_before == diff.root_hash_after
    assert diff.identical is True

    # 存储层原始字节（物理哈希）同样逐字节一致
    raw = scenario.raw_diff_after
    assert raw.matched == OBSERVATION_TOTAL
    assert raw.root_hash_before == raw.root_hash_after
    assert raw.identical is True
    assert raw.hash_mode == "raw"


def test_gate1_no_sql_update_or_delete_was_even_attempted(scenario: _Scenario) -> None:
    """铁律：绝对禁止 SQL UPDATE / DELETE —— 触发器审计证明"零尝试"。"""
    assert scenario.mutation_attempts == (), (
        f"历史表出现改写尝试（必须为 0）：{scenario.mutation_attempts[:5]}"
    )


def test_gate1_only_one_append_happened_and_revisions_never_moved(scenario: _Scenario) -> None:
    revision_rows = _object_revision_rows(scenario.db_path, "observation")
    assert len(revision_rows) == OBSERVATION_TOTAL
    assert all(row[1] == 1 for row in revision_rows), "历史事实的 revision 必须恒为 1（只追加）"
    assert all(row[2] <= scenario.revision_before for row in revision_rows), (
        "打标签不得把历史事实搬进新的 world_revision"
    )

    claim_rows = _object_revision_rows(scenario.db_path, "claim")
    assert len(claim_rows) == 1, "今天只允许追加一条注记对象"
    assert claim_rows[0][2] == scenario.revision_after == scenario.revision_before + 1

    rows_after = len(scenario.store.list_payloads())
    assert rows_after == scenario.rows_before + 1


def test_gate1_ledger_has_teeth_negative_control(scenario: _Scenario) -> None:
    """负向对照：有人偷偷改一条事实，台账必须当场抓到（证明校验不是摆设）。"""
    payloads = scenario.store.list_payloads(object_type=ObjectType.OBSERVATION)
    tampered = [dict(payload) for payload in payloads]
    target = dict(tampered[42])
    target["value"] = "被悄悄改写的事实（非法）"
    tampered[42] = target

    diff = scenario.ledger.verify(tampered)
    assert diff.mismatched_ids == (payloads[42]["object_id"],)
    assert diff.unchanged is False

    with pytest.raises(HistoryMutationDetectedError) as excinfo:
        scenario.ledger.assert_unchanged(tampered, context={"case": "tamper"})
    assert excinfo.value.code is ErrorCode.VERSION_CONFLICT
    assert excinfo.value.context["reason"] == "history_mutation_detected"
    assert excinfo.value.context["mismatched_ids"] == [payloads[42]["object_id"]]


def test_gate1_writer_refuses_to_write_on_a_corrupted_history(tmp_path: Any) -> None:
    """如果历史真的被外部改写，写注记者必须拒绝落笔（而不是照写不误）。"""
    db_path = tmp_path / "corrupted.db"
    store = SQLiteWorldStore(db_path)
    observations = [
        Observation(
            object_id=f"obs_{i:04d}",
            subject_id=SUBJECT_ID,
            occurred=TemporalExtent.point(T0 + timedelta(days=i)),
            learned_at=T0 + timedelta(days=i),
            recorded_at=T0 + timedelta(days=i),
            created_by="ingest_pipeline",
            source_kind="meeting_note",
            modality="text",
            value=f"客观事实 {i}",
        )
        for i in range(50)
    ]
    store.commit(
        observations,
        OperationRequest(
            operation_name="world.commit",
            expected_world_revision=0,
            reason="corruption fixture",
            idempotency_key="corrupt-ingest",
        ),
    )
    ledger = ObservationHashLedger.capture(store.list_payloads(object_type=ObjectType.OBSERVATION))

    # 外部非法改写（模拟"有人直接 UPDATE 历史"，这是我们要防住的真实事故）
    conn = sqlite3.connect(str(db_path))
    try:
        raw = conn.execute(
            "SELECT payload_json FROM object_revisions WHERE object_id = 'obs_0010'"
        ).fetchone()[0]
        tampered = raw.replace("客观事实 10", "被悄悄改写的事实（非法 UPDATE）")
        assert tampered != raw, "篡改夹具必须真的改到内容"
        conn.execute(
            "UPDATE object_revisions SET payload_json = ? WHERE object_id = 'obs_0010'",
            (tampered,),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(HistoryMutationDetectedError) as excinfo:
        RetrospectiveAnnotationWriter(store).write(
            _build_annotation(),
            history_ledger=ledger,
            subject_id=SUBJECT_ID,
            created_by="core_retrospective_review",
        )
    assert excinfo.value.context["phase"] == "pre_append"
    assert excinfo.value.context["mismatched_ids"] == ["obs_0010"]


# ===========================================================================
# 门禁 2：今天只写入一条 RetrospectiveAnnotation
# ===========================================================================


def test_gate2_exactly_one_annotation_written_today(scenario: _Scenario) -> None:
    receipt = scenario.receipt
    assert receipt.appended_object_count == 1
    assert receipt.annotations_written_today == 1
    assert receipt.world_revision_after == receipt.world_revision_before + 1
    assert receipt.history_unchanged is True
    assert receipt.history_matched == OBSERVATION_TOTAL
    assert receipt.observations_total_before == receipt.observations_total_after == OBSERVATION_TOTAL
    assert receipt.mutating_sql_attempts == 0
    assert receipt.appended_object_id == GATE_ANNOTATION_ID


def test_gate2_annotation_carries_today_and_the_valid_time_range(scenario: _Scenario) -> None:
    annotation = scenario.annotation
    assert annotation.learned_at == T_TODAY
    assert annotation.effective_recorded_at == annotation.learned_at
    assert annotation.valid_time_range == (T0, T_TODAY)
    assert annotation.target_entity_id == PARTNER_ENTITY
    assert annotation.source_statement_ref == scenario.ruling_observation_id
    assert set(annotation.kinds) == {
        AnnotationKind.JUDICIAL_FREEZE,
        AnnotationKind.FRAUD_REASSESSMENT,
    }
    assert "司法查封" in annotation.semantic_overlay
    assert "欺诈重估" in annotation.semantic_overlay


def test_gate2_annotation_is_persisted_as_append_only_claim(scenario: _Scenario) -> None:
    stored = annotations_from_store(scenario.store)
    assert len(stored) == 1, "今天只应存在一条复盘注记"
    round_tripped = stored[0]
    assert round_tripped.annotation_id == GATE_ANNOTATION_ID
    assert round_tripped.content_hash == scenario.annotation.content_hash
    assert round_tripped.knowledge_time == T_TODAY
    assert round_tripped.valid_time_range == (T0, T_TODAY)

    payload = scenario.store.get_payload(GATE_ANNOTATION_ID)
    assert payload is not None
    assert payload["object_type"] == ObjectType.CLAIM.value
    assert payload["claim_type"] == ClaimType.INFERENCE.value
    assert payload["knowledge_state"] == KnowledgeState.HYPOTHESIS.value
    assert payload["status"] == "active"
    valid_start, valid_end = (
        payload["valid_time"]["start"],
        payload["valid_time"]["end"],
    )
    assert valid_start.startswith(T0.isoformat()[:19])
    assert valid_end.startswith(T_TODAY.isoformat()[:19])
    # 注记指向司法裁定（今日新知），而非篡改两年前的事实
    assert payload["source_refs"][0]["object_id"] == scenario.ruling_observation_id


def test_gate2_plain_claims_are_not_mistaken_for_annotations(tmp_path: Any) -> None:
    """只有带模式标记的复盘 Claim 才算注记：绝不把普通 Claim 误读成历史重估。"""
    store = SQLiteWorldStore(tmp_path / "plain.db")
    plain = Claim(
        object_id="claim_plain_1",
        subject_id=SUBJECT_ID,
        learned_at=T_TODAY,
        recorded_at=T_TODAY,
        created_by="core",
        claimant_id="user",
        claim_type=ClaimType.FACT,
        content="普通事实断言，不含复盘图层",
        valid_time=TemporalExtent(start=T0, end=T_TODAY),
        asserted_at=T_TODAY,
        knowledge_state=KnowledgeState.OBSERVED,
        confidence=0.5,
    )
    store.commit(
        [plain],
        OperationRequest(
            operation_name="world.commit",
            expected_world_revision=0,
            reason="plain claim",
            idempotency_key="plain-claim-1",
        ),
    )
    assert annotations_from_store(store) == ()


def test_gate2_retroactive_write_is_denied() -> None:
    """严禁倒写历史：认知时间早于被注记区间结束 -> 直接拒绝。"""
    with pytest.raises(RetroactiveWriteDeniedError) as excinfo:
        RetrospectiveAnnotation(
            annotation_id="ann_illegal",
            target_entity_id=PARTNER_ENTITY,
            semantic_overlay="两年前就该知道他会欺诈（倒写历史，非法）",
            target_time_start=T0,
            target_time_end=T_TODAY,
            learned_at=T0 + timedelta(days=10),
            source_statement_ref="obs_000010",
        )
    assert excinfo.value.code is ErrorCode.PERMISSION_DENIED
    assert excinfo.value.context["reason"] == "retroactive_write_denied"


def test_gate2_annotation_contract_rejects_invalid_input() -> None:
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(
            annotation_id="ann_bad_window",
            target_entity_id=PARTNER_ENTITY,
            semantic_overlay="窗口反了",
            target_time_start=T_TODAY,
            target_time_end=T0,
            learned_at=T_TODAY,
            source_statement_ref="obs_1",
        )
    with pytest.raises(ValidationError):
        RetrospectiveAnnotation(
            annotation_id="ann_empty_overlay",
            target_entity_id=PARTNER_ENTITY,
            semantic_overlay="",
            target_time_start=T0,
            target_time_end=T_TODAY,
            learned_at=T_TODAY,
            source_statement_ref="obs_1",
        )


# ===========================================================================
# 门禁 3：双时间认知透镜
# ===========================================================================


def test_gate3a_cutoff_100_days_restores_the_original_state(scenario: _Scenario) -> None:
    """验收硬门禁 3a：as_of_cutoff = T0 + 100 天 -> active_annotations 必须为空。"""
    cutoff = T0 + timedelta(days=100)
    view = scenario.slice((T0, T_TODAY), as_of_cutoff=cutoff)

    assert view.knowledge_mode is KnowledgeMode.HISTORICAL
    assert view.as_of_cutoff == cutoff
    assert view.active_annotations == (), "当时并不知道两年后的裁定，注记不得出现"
    assert view.active_annotation_count == 0
    assert view.overlay_applied is False
    assert view.suppressed_annotations and view.suppressed_annotations[0].annotation_id == (
        GATE_ANNOTATION_ID
    ), "重估注记必须被如实标记为：当时尚未出现"

    # 当时可见的事实 = 在那之前就已学到的事实（忠实还原，不掺入未来）
    assert view.suppressed_by_cutoff > 0
    assert view.history_preserved is True
    assert all(
        observation.learned_at <= cutoff for observation in view.physical_observations
    )
    assert view.physical_count < OBSERVATION_TOTAL


def test_gate3a_historical_facts_are_untouched_by_the_later_reassessment(scenario: _Scenario) -> None:
    """历史认知视图里的事实内容与哈希，必须与今天的当前视图完全一致。"""
    historical = scenario.slice((T0, T_TODAY), as_of_cutoff=T0 + timedelta(days=100))
    current = scenario.slice((T0, T_TODAY))

    for observation in historical.physical_observations:
        reference = current.hash_of(observation.observation_id)
        assert reference == observation.content_hash

    # 历史视图的聚合指纹必须等于"它自己那批事实"的独立复算值（无外部污染）
    recomputed = hashlib.sha256(
        "\n".join(
            f"{observation.observation_id}\t{observation.content_hash}"
            for observation in sorted(
                historical.physical_observations, key=lambda item: item.observation_id
            )
        ).encode("utf-8")
    ).hexdigest()
    assert historical.physical_chain_hash == recomputed
    # 全链指纹与认知截止无关：两种视图看到的是同一条未被改写的台账
    assert historical.full_chain_hash == current.full_chain_hash
    assert all(
        "欺诈重估" not in observation.caption
        for observation in historical.physical_observations
    ), "注记文本绝不允许污染物理事实内容"


def test_gate3a_point_slice_at_the_signing_day_is_also_faithful(scenario: _Scenario) -> None:
    """两年前签约当天：当时没有任何不利注记，看到的就是完整的"可信合伙人"状态。"""
    day_end = T0 + timedelta(days=1)
    view = scenario.slice((T0, day_end), as_of_cutoff=day_end)
    returned_ids = {observation.observation_id for observation in view.physical_observations}

    assert view.active_annotations == ()
    assert view.suppressed_by_cutoff == 0
    # 签署当天的 24 条每日采样必须一条不少地被端出来
    assert {f"obs_{index:06d}" for index in range(DAILY_SAMPLES)} <= returned_ids
    assert view.physical_count >= DAILY_SAMPLES
    # 窗口内的每一条事实都必须满足"当时已学到 + 发生在窗口内"
    assert all(observation.learned_at <= day_end for observation in view.physical_observations)
    assert all(
        observation.occurred_start <= day_end for observation in view.physical_observations
    )

    # 点窗口：只命中那一刻的事实（同一时刻不会把整天的事实都端出来）
    instant = T0 + timedelta(hours=12)
    point_view = scenario.slice(instant, as_of_cutoff=day_end)
    assert point_view.physical_count == 1
    assert point_view.physical_observations[0].observation_id == "obs_000012"
    assert point_view.active_annotations == ()


def test_gate3b_current_view_overlays_without_rewriting(scenario: _Scenario) -> None:
    """验收硬门禁 3b：as_of_cutoff=None -> 历史完整保留 + 精确叠加外挂重估图层。"""
    view = scenario.slice((T0, T_TODAY))

    assert view.knowledge_mode is KnowledgeMode.CURRENT
    assert view.as_of_cutoff is None
    assert view.physical_count == OBSERVATION_TOTAL
    assert view.suppressed_by_cutoff == 0
    assert view.history_preserved is True
    assert view.active_annotation_count == 1
    assert view.overlay_applied is True

    overlay = view.active_annotations[0]
    assert overlay.annotation_id == GATE_ANNOTATION_ID
    assert overlay.learned_at == T_TODAY
    assert "司法查封" in overlay.semantic_overlay and "离岸空壳公司" in overlay.semantic_overlay

    # 物理事实依旧是原始内容（注记只是外挂图层，不参与事实内容）
    assert all("欺诈重估" not in observation.caption for observation in view.physical_observations)
    assert view.full_chain_hash == scenario.index.entity_chain_hash(PARTNER_ENTITY)


def test_gate3b_boundary_cutoffs_are_exact(scenario: _Scenario) -> None:
    """认知时间的边界：注记只在其 learned_at 之后可见，一天都不能早。"""
    just_before = scenario.slice((T0, T_TODAY), as_of_cutoff=T_TODAY - timedelta(microseconds=1))
    at_learned = scenario.slice((T0, T_TODAY), as_of_cutoff=T_TODAY)
    after = scenario.slice((T0, T_TODAY), as_of_cutoff=T_TODAY + timedelta(days=1))

    assert just_before.active_annotations == ()
    assert just_before.active_annotation_count == 0
    assert at_learned.active_annotation_count == 1
    assert after.active_annotation_count == 1


def test_gate3b_lens_is_read_only_and_unknown_entities_are_explicit(scenario: _Scenario) -> None:
    with pytest.raises(UnknownTargetEntityError) as excinfo:
        scenario.lens.query_historical_slice("ent_does_not_exist", (T0, T_TODAY))
    assert excinfo.value.code is ErrorCode.NOT_FOUND

    # 反复查询不改变任何状态（幂等只读）
    first = scenario.slice((T0, T_TODAY)).physical_chain_hash
    for _ in range(5):
        assert scenario.slice((T0, T_TODAY)).physical_chain_hash == first
    assert scenario.ledger.verify(
        scenario.store.list_payloads(object_type=ObjectType.OBSERVATION)
    ).unchanged


def test_gate3_lens_accepts_the_dispatch_skeleton_name(scenario: _Scenario) -> None:
    """工单骨架类名 EpistemicWorldLens 必须可用（query_historical_slice 同语义）。"""
    assert issubclass(EpistemicWorldLens, BiTemporalEpistemicLens)
    lens = EpistemicWorldLens(scenario.index, annotations=[scenario.annotation])
    historical = lens.query_historical_slice(
        PARTNER_ENTITY, (T0, T_TODAY), as_of_cutoff=T0 + timedelta(days=100)
    )
    current = lens.query_historical_slice(PARTNER_ENTITY, (T0, T_TODAY))
    assert historical.active_annotations == ()
    assert current.active_annotation_count == 1
    assert historical.full_chain_hash == current.full_chain_hash


# ===========================================================================
# 门禁 4：单跳隔离，杜绝 210 次算力雪崩
# ===========================================================================


def _build_golden_isolator(
    sink: Any = None,
) -> SingleHopCascadeIsolator:
    """黄金 DDL 拓扑：1 级 10 个 + 每 1 级下挂 20 个 2 级 = 210 个下游。"""
    isolator = SingleHopCascadeIsolator(recompute_sink=sink)
    isolator.register_node("fact_partner_fraud", node_type="BELIEF", content="合伙人为蓄意欺诈")
    for i in range(10):
        direct = f"summary_direct_{i:02d}"
        isolator.register_dependency(direct, "fact_partner_fraud")
        for j in range(20):
            isolator.register_dependency(f"summary_indirect_{i:02d}_{j:02d}", direct)
    return isolator


def _build_five_layer_isolator() -> SingleHopCascadeIsolator:
    """万级依赖网络：10 / 200 / 1000 / 4000 / 8000（5 层深度）。"""
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("fact_partner_fraud", node_type="BELIEF", content="合伙人为蓄意欺诈")
    previous = ["fact_partner_fraud"]
    for depth, fanout in enumerate(FIVE_LAYER_FANOUT, start=1):
        current = [f"layer{depth}_node_{i:05d}" for i in range(fanout)]
        for index, node_id in enumerate(current):
            parent = previous[index % len(previous)]
            isolator.register_dependency(node_id, parent)
        previous = current
    return isolator


def test_gate4a_single_hop_prevents_the_210_call_avalanche() -> None:
    """验收硬门禁 4：只有 1 级 10 个节点被标 stale，深度严格为 1，零大模型调用。"""
    isolator = _build_golden_isolator()
    report = isolator.mark_stale_from("fact_partner_fraud", "反欺诈裁定：合伙系蓄意隐瞒")

    assert report.marked_count == 10
    assert report.marked_stale_ids == tuple(f"summary_direct_{i:02d}" for i in range(10))
    assert report.traversal_depth == 1
    assert report.max_depth == 1
    assert report.is_single_hop is True
    assert report.would_be_cascade_nodes == 210, "级联算法本会波及 210 个节点"
    assert report.llm_calls_issued == 0, "本层绝不允许触发大模型重算"
    assert report.llm_calls_if_cascaded == 210
    assert report.suppressed_cascade_nodes == 200
    assert report.deferred_count == 200
    assert len(report.deferred_sample_ids) == 64
    assert report.cascade_audit_truncated is False, "210 < 默认审计预算，规模数字必须是精确值"
    assert report.cascade_audit_budget == ra.DEFAULT_CASCADE_AUDIT_BUDGET
    assert report.audit_nodes_scanned == 210

    assert len(isolator.stale_node_ids()) == 10
    assert all(node_id.startswith("summary_direct_") for node_id in isolator.stale_node_ids())
    assert not any(
        isolator.is_stale(f"summary_indirect_{i:02d}_{j:02d}") for i in range(10) for j in range(20)
    ), "2 级下游绝不能被级联污染"


def test_gate4a_marks_only_the_direct_consumers_even_with_shared_parents() -> None:
    """多个上游共用下游时，只标记"直接消费被推翻认知"的那一层。"""
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("belief_fraud")
    for i in range(10):
        isolator.register_dependency(f"direct_{i}", "belief_fraud")
    for i in range(10):
        for j in range(5):
            isolator.register_dependency(f"deep_{i}_{j}", f"direct_{i}")
    report = isolator.mark_stale_from("belief_fraud", "欺诈重估")
    assert report.marked_count == 10
    assert report.would_be_cascade_nodes == 60
    assert isolator.stale_node_ids() == tuple(f"direct_{i}" for i in range(10))


def test_gate4a_deferred_batch_is_handed_off_without_synchronous_recompute() -> None:
    """长尾只交接给后台：标记路径零重算、零大模型调用。"""
    seen: list[str] = []
    isolator = _build_golden_isolator(sink=seen.append)

    report = isolator.mark_stale_from("fact_partner_fraud", "欺诈裁定：合伙系蓄意隐瞒")
    assert report.llm_calls_issued == 0
    assert isolator.recompute_dispatch_count == 0, "标记路径不得触发任何重算"
    assert seen == []

    batch = isolator.prepare_deferred_batch("fact_partner_fraud")
    assert isolator.recompute_dispatch_count == 0, "准备批次也不得触发重算"
    dispatched = isolator.dispatch_deferred_batch(batch)
    assert dispatched == len(batch.batch) == MAX_RECOMPUTE_CONCURRENCY
    assert isolator.recompute_dispatch_count == MAX_RECOMPUTE_CONCURRENCY
    assert seen == [node.node_id for node in batch.batch]

    # 显式换一个 sink 也可以（后台队列可替换）
    other: list[str] = []
    assert isolator.dispatch_deferred_batch(batch, other.append) == len(batch.batch)
    assert other == seen


def test_gate4a_deferred_queue_is_bounded_and_batched() -> None:
    """长尾不递归、不重算：进入并发预算 <= 3 的有界批次，由后台分批消化。"""
    isolator = _build_golden_isolator()
    report = isolator.mark_stale_from("fact_partner_fraud", "欺诈重估")
    batch = isolator.prepare_deferred_batch(report.changed_node_id)
    assert batch.concurrency_budget == MAX_RECOMPUTE_CONCURRENCY == 3
    assert len(batch.batch) == 3
    assert batch.remaining_after_batch == 197  # 200 个长尾，批出 3 个后剩 197
    assert all(node.is_stale is False for node in batch.batch), "长尾节点保持未失效，待懒重算"


def test_gate4b_five_layer_10k_graph_is_isolated_at_depth_one() -> None:
    """万级（5 层 / 13,211 节点）依赖网络：标记严格 = 10，深度严格 = 1，扫描量恒定。"""
    isolator = _build_five_layer_isolator()
    total_nodes = 1 + sum(FIVE_LAYER_FANOUT)
    assert isolator.node_count() == total_nodes == 13_211
    assert isolator.edge_count() == total_nodes - 1

    start = time.perf_counter()
    report = isolator.mark_stale_from("fact_partner_fraud", "司法查封裁定：欺诈重估")
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert report.marked_count == 10
    assert report.traversal_depth == 1
    assert report.is_single_hop is True
    # 13,210 > 默认审计预算 10,000：规模数字必须**如实标注为下界**，不得谎报精确值
    assert report.would_be_cascade_nodes == ra.DEFAULT_CASCADE_AUDIT_BUDGET
    assert report.cascade_audit_truncated is True
    assert report.suppressed_cascade_nodes == report.would_be_cascade_nodes - report.marked_count
    assert report.llm_calls_if_cascaded == report.would_be_cascade_nodes
    assert report.would_be_cascade_depth == 5
    assert report.suppressed_cascade_nodes == ra.DEFAULT_CASCADE_AUDIT_BUDGET - 10
    assert report.deferred_count == report.suppressed_cascade_nodes
    assert report.llm_calls_issued == 0
    assert report.marking_ms <= 5.0, f"单跳标记本身耗时 {report.marking_ms:.3f}ms 过高"
    assert elapsed_ms <= 25.0, f"单跳隔离（含审计）耗时 {elapsed_ms:.3f}ms 超出预算"

    # 审计是"若级联会付出多少代价"的统计：可显式放大预算拿到精确值
    exact = isolator.mark_stale_from(
        "fact_partner_fraud", "司法查封裁定：欺诈重估", cascade_audit_budget=20_000
    )
    assert exact.cascade_audit_truncated is False, "预算给足后必须给出精确规模"
    assert exact.would_be_cascade_nodes == 13_210
    assert exact.would_be_cascade_depth == 5
    assert exact.deferred_count == 13_200
    assert exact.audit_nodes_scanned == 13_210
    assert exact.cascade_audit_budget == 20_000

    stale = isolator.stale_node_ids()
    assert len(stale) == 10
    assert stale == tuple(f"layer1_node_{i:05d}" for i in range(10))
    for depth, fanout in enumerate(FIVE_LAYER_FANOUT[1:], start=2):
        assert not any(isolator.is_stale(f"layer{depth}_node_{i:05d}") for i in range(fanout)), (
            f"第 {depth} 层不得被级联污染"
        )
    print(
        f"[M1-018 单跳隔离] 节点={total_nodes} 级联本会波及={report.would_be_cascade_nodes}"
        f"(下界,审计截断={report.cascade_audit_truncated}) 实际标记={report.marked_count} "
        f"深度={report.traversal_depth} 标记扫描={report.nodes_scanned} "
        f"标记耗时={report.marking_ms:.3f}ms 含审计={elapsed_ms:.3f}ms"
    )


def test_gate4b_marking_is_idempotent_and_bounded() -> None:
    isolator = _build_five_layer_isolator()
    first = isolator.mark_stale_from("fact_partner_fraud", "欺诈重估")
    second = isolator.mark_stale_from("fact_partner_fraud", "欺诈重估")
    assert first.marked_count == second.marked_count == 10
    assert isolator.stale_node_ids() == second.marked_stale_ids
    assert isolator.stale_mark_count() == 10, "重复标记不得重复记账"


def test_gate4_isolator_contract_guards() -> None:
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("belief_a")
    with pytest.raises(AIOSProtocolError):
        isolator.register_dependency("belief_a", "belief_a")
    with pytest.raises(AIOSProtocolError):
        isolator.mark_stale_from("belief_missing", "欺诈重估")
    with pytest.raises(AIOSProtocolError):
        isolator.mark_stale_from("belief_a", "   ")
    with pytest.raises(AIOSProtocolError):
        SingleHopCascadeIsolator(max_recompute_concurrency=0)


def test_gate4_golden_ddl_single_hop_sql_matches_contract(tmp_path: Any) -> None:
    """黄金 DDL §3.5 的 SQL 落库路径：只更新 cognitive_nodes，绝不动历史事实表。"""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE cognitive_nodes (
                node_id TEXT PRIMARY KEY, is_stale INTEGER NOT NULL DEFAULT 0,
                stale_reason TEXT, stale_at TEXT
            );
            CREATE TABLE node_dependencies (
                downstream_node_id TEXT NOT NULL, upstream_node_id TEXT NOT NULL,
                PRIMARY KEY (downstream_node_id, upstream_node_id)
            );
            """
        )
        conn.execute("INSERT INTO cognitive_nodes(node_id) VALUES ('fact_partner_fraud')")
        for i in range(10):
            conn.execute("INSERT INTO cognitive_nodes(node_id) VALUES (?)", (f"summary_direct_{i}",))
            conn.execute(
                "INSERT INTO node_dependencies VALUES (?, 'fact_partner_fraud')",
                (f"summary_direct_{i}",),
            )
            for j in range(20):
                conn.execute(
                    "INSERT INTO cognitive_nodes(node_id) VALUES (?)",
                    (f"summary_indirect_{i}_{j}",),
                )
                conn.execute(
                    "INSERT INTO node_dependencies VALUES (?, ?)",
                    (f"summary_indirect_{i}_{j}", f"summary_direct_{i}"),
                )
        conn.commit()

        marked = ra.invalidate_overturned_fact_single_hop(
            conn, "fact_partner_fraud", "反欺诈裁定：合伙系蓄意隐瞒"
        )
        assert sorted(marked) == sorted(f"summary_direct_{i}" for i in range(10))
        stale = conn.execute("SELECT COUNT(*) FROM cognitive_nodes WHERE is_stale = 1").fetchone()
        assert stale[0] == 10
        indirect_stale = conn.execute(
            "SELECT COUNT(*) FROM cognitive_nodes WHERE is_stale = 1 AND node_id LIKE 'summary_indirect%'"
        ).fetchone()
        assert indirect_stale[0] == 0
    finally:
        conn.close()


# ===========================================================================
# 万级压测（18,000 事实 + 13,211 认知节点）
# ===========================================================================


def test_stress_10k_pipeline_stays_within_budget(scenario: _Scenario) -> None:
    """万级压测：哈希、重建索引、双时间查询、单跳隔离全部在预算内。"""
    payloads = scenario.store.list_payloads(object_type=ObjectType.OBSERVATION)

    started = time.perf_counter()
    ledger = ObservationHashLedger.capture(payloads)
    hash_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    index = PhysicalChainIndex(
        payloads, entity_links={PARTNER_ENTITY: [payload["object_id"] for payload in payloads]}
    )
    rebuild_ms = (time.perf_counter() - started) * 1000.0

    lens = BiTemporalEpistemicLens(index, annotations=[scenario.annotation])
    for _ in range(5):  # 预热：把一次性的冷启动成本（GC / 缓存填充）挪出计量窗口
        lens.query_historical_slice(PARTNER_ENTITY, (T0, T_TODAY), T0 + timedelta(days=100))
        lens.query_historical_slice(PARTNER_ENTITY, (T0, T_TODAY))
    gc.collect()
    historical_ms = []
    current_ms = []
    for _ in range(20):
        started = time.perf_counter()
        lens.query_historical_slice(PARTNER_ENTITY, (T0, T_TODAY), T0 + timedelta(days=100))
        historical_ms.append((time.perf_counter() - started) * 1000.0)
        started = time.perf_counter()
        lens.query_historical_slice(PARTNER_ENTITY, (T0, T_TODAY))
        current_ms.append((time.perf_counter() - started) * 1000.0)

    isolator = _build_five_layer_isolator()
    started = time.perf_counter()
    report = isolator.mark_stale_from("fact_partner_fraud", "司法查封裁定：欺诈重估")
    isolate_ms = (time.perf_counter() - started) * 1000.0

    print(
        f"[M1-018 万级压测] 事实={ledger.count} 哈希={hash_ms:.1f}ms "
        f"索引重建={rebuild_ms:.1f}ms 历史视图 p50={statistics.median(historical_ms):.2f}ms "
        f"当前视图 p50={statistics.median(current_ms):.2f}ms 单跳标记={isolate_ms:.3f}ms"
    )

    assert ledger.count == OBSERVATION_TOTAL
    assert hash_ms <= 2_000.0, f"18,000 条事实哈希耗时 {hash_ms:.1f}ms 过高"
    assert rebuild_ms <= 5_000.0, f"索引重建耗时 {rebuild_ms:.1f}ms 过高"
    assert statistics.median(historical_ms) <= 25.0
    assert statistics.median(current_ms) <= 25.0
    assert max(historical_ms) <= 60.0 and max(current_ms) <= 60.0
    assert isolate_ms <= 25.0
    assert report.marked_count == 10 and report.llm_calls_issued == 0


def test_stress_hash_ledger_scales_linearly_and_is_stable(scenario: _Scenario) -> None:
    """哈希台账在大样本下必须稳定可复现（同一输入 -> 同一 root_hash）。"""
    payloads = scenario.store.list_payloads(object_type=ObjectType.OBSERVATION)
    first = ObservationHashLedger.capture(payloads)
    second = ObservationHashLedger.capture(payloads)
    assert first.root_hash == second.root_hash
    assert first.entries() == second.entries()
    assert scenario.ledger.root_hash == first.root_hash
    assert len(first.entries()) == OBSERVATION_TOTAL


# ===========================================================================
# 契约、桥接与静态纪律
# ===========================================================================


def test_annotation_roundtrip_through_claim_payload() -> None:
    annotation = _build_annotation()
    claim = annotation.to_claim(subject_id=SUBJECT_ID, created_by="core")
    payload = claim.model_dump(mode="json")
    restored = RetrospectiveAnnotation.from_claim_payload(payload)
    assert restored is not None
    assert restored.annotation_id == annotation.annotation_id
    assert restored.target_entity_id == annotation.target_entity_id
    assert restored.semantic_overlay == annotation.semantic_overlay
    assert restored.valid_time_range == annotation.valid_time_range
    assert restored.learned_at == annotation.learned_at
    assert restored.kinds == annotation.kinds
    assert restored.content_hash == annotation.content_hash
    assert RetrospectiveAnnotation.from_claim_payload({"metadata": {}}) is None


def test_annotation_log_is_append_only_and_tamper_evident() -> None:
    log = RetrospectiveAnnotationLog()
    first = _build_annotation()
    log.append(first)
    head_after_first = log.head_hash

    with pytest.raises(DuplicateAnnotationError) as excinfo:
        log.append(first)
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    second = _build_annotation(T_TODAY + timedelta(days=30)).model_copy(
        update={"annotation_id": "ann_restoration", "annotation_kind": AnnotationKind.REPUTATION_RESTORATION}
    )
    log.append(second)
    assert len(log) == 2
    assert log.head_hash != head_after_first
    log.assert_chain_intact()

    # 篡改链条（模拟有人偷改历史注记）必须被抓到
    log._chain[0] = "0" * 64  # noqa: SLF001 - 负向对照需要直接破坏内部链
    with pytest.raises(AIOSProtocolError) as excinfo:
        log.assert_chain_intact()
    assert excinfo.value.context["reason"] == "annotation_chain_broken"


def test_hash_ledger_guards_mode_mismatch(scenario: _Scenario) -> None:
    with pytest.raises(AIOSProtocolError) as excinfo:
        scenario.raw_ledger.verify(
            scenario.store.list_payloads(object_type=ObjectType.OBSERVATION)
        )
    assert excinfo.value.context["reason"] == "ledger_mode_mismatch"

    raw_before = _raw_observation_payloads(scenario.db_path)
    raw_after = _raw_observation_payloads(scenario.db_path)
    assert raw_before == raw_after
    diff = scenario.raw_ledger.verify_raw(raw_after)
    assert diff.identical is True
    assert diff.matched == OBSERVATION_TOTAL


def test_hyperlink_bridge_links_observations_to_entity() -> None:
    """与 C06 超链接穿透层的桥接：实体事实归属来自结构化引用链，而非文本匹配。"""
    traverser = EntityHyperlinkGraphTraverser()
    traverser.register_entity_link(PARTNER_ENTITY, ["老王", "王叔"], ["anchor_1"])
    traverser.register_anchor_link("anchor_1", ["evs_1"], occurred_at=T0)
    traverser.register_evidence_link("evs_1", ["obs_000001", "obs_000002"], knowledge_cutoff=T0)
    for observation_id in ("obs_000001", "obs_000002"):
        traverser.register_observation(observation_id, content=f"事实 {observation_id}", occurred_at=T0)

    result = traverser.traverse_entity_network(PARTNER_ENTITY)
    links = observations_linked_to_entity(result)
    assert links == {PARTNER_ENTITY: ("obs_000002", "obs_000001")} or links == {
        PARTNER_ENTITY: ("obs_000001", "obs_000002")
    }

    index = PhysicalChainIndex(
        [
            {
                "object_id": "obs_000001",
                "occurred": {"start": T0.isoformat(), "end": T0.isoformat(), "unknown": False},
                "learned_at": T0.isoformat(),
                "value": "事实 1",
            },
            {
                "object_id": "obs_000002",
                "occurred": {"start": T0.isoformat(), "end": T0.isoformat(), "unknown": False},
                "learned_at": T0.isoformat(),
                "value": "事实 2",
            },
        ],
        entity_links=links,
    )
    assert index.observation_ids(PARTNER_ENTITY) == ("obs_000001", "obs_000002")


def test_module_never_writes_history_and_never_touches_sqlite(scenario: _Scenario) -> None:
    """静态纪律：不 import sqlite3 / evaluator；SQL 字面量绝不指向历史事实表。"""
    tree = ast.parse(inspect.getsource(ra))

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            docstrings.add(id(node.body[0].value))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "sqlite3" not in imported
    assert "evaluator" not in imported

    history_tables = ("object_revisions", "world_commits", "observations", "entities")
    sql_verbs = ("from", "into", "update", "delete", "join", "table")
    suspicious: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        lowered = node.value.lower()
        if "object_revisions" in lowered or "world_commits" in lowered:
            suspicious.append(node.value)
            continue
        if any(verb in lowered for verb in sql_verbs) and any(
            table in lowered for table in history_tables[2:]
        ):
            suspicious.append(node.value)
    assert suspicious == [], f"查询/注记层不得出现历史事实表 SQL 字面量：{suspicious}"

    # 唯一允许的 SQL 写目标必须是认知层 (cognitive_nodes)
    joined = "\n".join(
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ).lower()
    assert "update cognitive_nodes" in joined
    for table in history_tables[1:]:
        assert f"update {table}" not in joined
        assert f"delete from {table}" not in joined


def test_world_package_exports_the_m1_018_contract() -> None:
    import aios_core.world as world

    for name in (
        "RetrospectiveAnnotation",
        "BiTemporalEpistemicLens",
        "EpistemicWorldLens",
        "ObservationHashLedger",
        "SingleHopCascadeIsolator",
        "RetrospectiveAnnotationWriter",
    ):
        assert hasattr(world, name), f"world 包必须导出 {name}"


def test_lens_rejects_invalid_target_time(scenario: _Scenario) -> None:
    with pytest.raises(AIOSProtocolError):
        scenario.lens.query_historical_slice(PARTNER_ENTITY, "2026-09-16")  # type: ignore[arg-type]
    with pytest.raises(AIOSProtocolError):
        scenario.lens.query_historical_slice(PARTNER_ENTITY, (T_TODAY, T0))
    with pytest.raises(AIOSProtocolError):
        scenario.lens.query_historical_slice(PARTNER_ENTITY, TemporalExtent.unknown_time())
