"""M1-019 Retention & Tombstone Worker —— 宪法 C1 裁决执行体的场景测试。

验收锚（M1 退出条件④ 的分解）：
  * 确定性 TTL：到期才动，没到期连看都不看；
  * 引用锁（§25）：被任何存活对象引用的对象永不进隔离；
  * 两阶段（C1 裁决）：stage1 冷却后 stage2，冷却期 = 反对派的撤销窗口；
  * auto_release：冷却期内出现新引用 → 永不 stage2（policy $auto_release_note）；
  * DeletionLog 机制锁（ADJ-004.3）：机械身份签名、mechanical_check_passed 必真；
  * legal_hold 法务锁：持锁对象三锁之一，直接豁免；
  * REVOCATION_FREE 吊销权外：默认永存策略不允许被时间擦掉；
  * 声纹簇退休（ADJ-009/V40）：半年沉默 → RETIRED，不可逆；
  * 幂等：同一评估时刻重跑 → durable_object_delta == 0（重复墓碑=0）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios_core.contracts.enums_v3 import (
    ObjectTypeV3,
    RetentionClass,
    SpeakerClusterStatus,
    TombstoneStage,
)
from aios_core.contracts.models_v3 import (
    ConversationTurn,
    SourceEnvelopeV3,
    SpeakerCluster,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.services.retention_worker import (
    RetentionPolicy,
    RetentionWorker,
    SimulatedCryptoShredder,
    WORKER_IDENTITY,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from tests.unit.conftest import world_kwargs

T0 = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
TNOW = datetime(2026, 9, 16, 0, 0, 0, tzinfo=timezone.utc)

_POLICY_JSON = {
    "policy_version": "1.1.0-test",
    "retention_policy": {
        "ttl_days_by_retention_class": {
            RetentionClass.REVOCABLE_RAW.value: 180,
            RetentionClass.EPHEMERAL_SESSION.value: 30,
        },
        "quarantine_cooldown_days": 30,
        "speaker_cluster_retire_days": 180,
    },
}


def _policy() -> RetentionPolicy:
    return RetentionPolicy.from_runtime_policy(_POLICY_JSON)


def _store(tmp_path: Path) -> SQLiteWorldStore:
    return SQLiteWorldStore(tmp_path / "world.db")


def _commit(store: SQLiteWorldStore, objs, key: str) -> None:
    rev = store.current_world_revision()
    store.commit(
        objs,
        OperationRequest(
            operation_id=f"seed-{key}",
            operation_name="world.commit",
            expected_world_revision=rev,
            reason=f"seed {key}",
            idempotency_key=key,
        ),
    )


def _turn(
    object_id: str,
    *,
    learned_at: datetime = T0,
    retention: RetentionClass | None = RetentionClass.REVOCABLE_RAW,
    legal_hold: bool = False,
    utterance: str = "某天随口说的话",
) -> ConversationTurn:
    env = None
    if retention is not None or legal_hold:
        env = SourceEnvelopeV3(
            source_id=f"src-{object_id}",
            collector="sim-mic",
            retention_class=retention or RetentionClass.REVOCABLE_RAW,
            legal_hold=legal_hold,
        )
    return ConversationTurn(
        object_id=object_id,
        conv_id="conv-1",
        seq=0,
        speaker="user",
        utterance=utterance,
        finalized_at=learned_at,
        source_envelope=env,
        **world_kwargs(learned_at=learned_at, recorded_at=learned_at),
    )


def _cluster(object_id: str, *, last_heard: datetime) -> SpeakerCluster:
    return SpeakerCluster(
        object_id=object_id,
        cluster_status=SpeakerClusterStatus.ACTIVE,
        feature_locator="vec://sim/features/0001.bin",
        first_heard_at=min(last_heard, T0),
        last_heard_at=last_heard,
        **world_kwargs(learned_at=T0, recorded_at=T0),
    )


def _worker(store: SQLiteWorldStore, *, now: datetime = TNOW) -> RetentionWorker:
    return RetentionWorker(store, _policy(), now_fn=lambda: now)


def _by_type(store: SQLiteWorldStore, otype: ObjectTypeV3) -> list[dict]:
    return [p for p in store.list_payloads() if p.get("object_type") == otype.value]


# ---------------------------------------------------------------------------
# Phase R —— 声纹簇退休
# ---------------------------------------------------------------------------


def test_retires_cluster_silent_beyond_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stale = T0  # 2025-06-01 → 距今 > 180 天
    _commit(store, [_cluster("clu-old", last_heard=stale)], "c0")
    report = _worker(store).run_cycle()
    assert report.clusters_retired == ["clu-old"]
    payload = store.get_payload("clu-old")
    assert payload["cluster_status"] == SpeakerClusterStatus.RETIRED.value
    assert payload["revision"] == 2
    assert payload["retired_after"] is not None


def test_active_cluster_within_window_untouched(tmp_path: Path) -> None:
    store = _store(tmp_path)
    recent = TNOW - timedelta(days=10)
    _commit(store, [_cluster("clu-new", last_heard=recent)], "c0")
    report = _worker(store).run_cycle()
    assert report.clusters_retired == []
    assert store.get_payload("clu-new")["revision"] == 1


# ---------------------------------------------------------------------------
# Phase Q —— TTL 与隔离标记
# ---------------------------------------------------------------------------


def test_expired_revocable_raw_becomes_stage1_tombstone(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _commit(store, [_turn("turn-old")], "q0")  # learned 2025-06 → 超 180d
    report = _worker(store).run_cycle()
    assert report.stage1_marked == ["turn-old"]
    tbs = _by_type(store, ObjectTypeV3.RETENTION_TOMBSTONE)
    assert len(tbs) == 1
    assert tbs[0]["tombstone_stage"] == TombstoneStage.STAGE1_SOFT.value
    assert tbs[0]["target_ref"] == {"object_id": "turn-old", "revision": 1}
    assert tbs[0]["created_by"] == WORKER_IDENTITY


def test_fresh_object_is_not_touched(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _commit(store, [_turn("turn-fresh", learned_at=TNOW - timedelta(days=5))], "q0")
    report = _worker(store).run_cycle()
    assert report.stage1_marked == []
    assert _by_type(store, ObjectTypeV3.RETENTION_TOMBSTONE) == []


def test_referenced_object_is_reference_locked(tmp_path: Path) -> None:
    """§25 + C1：被引用物永不进隔离——这就是"被引用数据不可删"的机器面。"""
    store = _store(tmp_path)
    _commit(store, [_turn("turn-old")], "q0")
    referencing = _turn("turn-ref", learned_at=TNOW - timedelta(days=1))
    referencing = referencing.model_copy(
        update={
            "source_refs": [
                {
                    "object_id": "turn-old",
                    "revision": 1,
                    "source_locator": None,
                }
            ]
        }
    )
    _commit(store, [referencing], "q1")
    report = _worker(store).run_cycle()
    assert report.stage1_marked == []
    assert "turn-old" in report.skipped_reference_locked


def test_legal_hold_exempts_object(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _commit(store, [_turn("turn-hold", legal_hold=True)], "q0")
    report = _worker(store).run_cycle()
    assert report.stage1_marked == []
    assert "turn-hold" in report.skipped_legal_hold


def test_revocation_free_never_gced(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _commit(store, [_turn("turn-keep", retention=RetentionClass.REVOCATION_FREE)], "q0")
    report = _worker(store).run_cycle()
    assert report.stage1_marked == []
    assert report.skipped_revocation_free >= 1


def test_object_without_envelope_defaults_to_revocation_free(tmp_path: Path) -> None:
    """ADJ-004 的默认面：没有声明保留类的对象一律吊销权外（宁漏杀不错杀）。"""
    store = _store(tmp_path)
    _commit(store, [_turn("turn-bare", retention=None)], "q0")
    report = _worker(store).run_cycle()
    assert report.stage1_marked == []
    assert report.skipped_revocation_free >= 1


# ---------------------------------------------------------------------------
# Phase S —— 冷却后粉碎 + 撤销权
# ---------------------------------------------------------------------------


def test_stage2_after_cooldown_writes_log_and_upgrades_tombstone(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _commit(store, [_turn("turn-old")], "q0")
    t1 = TNOW
    _worker(store, now=t1).run_cycle()

    # 冷却 31 天后重跑
    t2 = t1 + timedelta(days=31)
    worker = _worker(store, now=t2)
    shredder: SimulatedCryptoShredder = worker._shredder  # type: ignore[assignment]
    report = worker.run_cycle()
    assert report.stage2_shredded == ["turn-old"]

    logs = _by_type(store, ObjectTypeV3.DELETION_LOG)
    assert len(logs) == 1
    assert logs[0]["deleted_ref"] == {"object_id": "turn-old", "revision": 1}
    assert logs[0]["authorized_by"] == WORKER_IDENTITY
    assert logs[0]["mechanical_check_passed"] is True
    assert logs[0]["legal_hold_at_time"] is False  # 取的是时刻值，不是豁免

    tbs = _by_type(store, ObjectTypeV3.RETENTION_TOMBSTONE)
    assert len(tbs) == 1
    assert tbs[0]["tombstone_stage"] == TombstoneStage.STAGE2_SHREDDED.value
    assert tbs[0]["revision"] == 2
    assert tbs[0]["deletion_log_ref"] == {"object_id": logs[0]["object_id"], "revision": 1}

    certs = shredder.certificates
    assert len(certs) == 1 and certs[0]["object_id"] == "turn-old"
    assert "content" not in certs[0], "擦除证书不得含被擦内容（§93 之五读法）"


def test_new_reference_during_cooldown_is_veto(tmp_path: Path) -> None:
    """auto_release_on_new_dependency 的机器面：冷却不是走形式，它真的救下对象。"""
    store = _store(tmp_path)
    _commit(store, [_turn("turn-old")], "q0")
    _worker(store, now=TNOW).run_cycle()
    assert _by_type(store, ObjectTypeV3.RETENTION_TOMBSTONE)[0]["tombstone_stage"] == TombstoneStage.STAGE1_SOFT.value

    # 冷却期内出现新引用
    ref_now = _turn("turn-later", learned_at=TNOW, utterance="回引旧话")
    ref_now = ref_now.model_copy(
        update={"source_refs": [{"object_id": "turn-old", "revision": 1}]}
    )
    _commit(store, [ref_now], "q1")

    t2 = TNOW + timedelta(days=45)
    report = _worker(store, now=t2).run_cycle()
    assert report.stage2_shredded == []
    assert report.release_blocked_by_references == ["turn-old"]
    tbs = _by_type(store, ObjectTypeV3.RETENTION_TOMBSTONE)
    assert all(t["tombstone_stage"] == TombstoneStage.STAGE1_SOFT.value for t in tbs)
    assert _by_type(store, ObjectTypeV3.DELETION_LOG) == []


def test_tombstone_target_ref_never_creates_self_lock(tmp_path: Path) -> None:
    """墓碑自身的 target_ref 不能成为引用锁——否则没有任何对象能走到 stage2。"""
    store = _store(tmp_path)
    _commit(store, [_turn("turn-old")], "q0")
    _worker(store, now=TNOW).run_cycle()
    t2 = TNOW + timedelta(days=31)
    report = _worker(store, now=t2).run_cycle()
    assert report.stage2_shredded == ["turn-old"], "墓碑自锁 bug 复活"


# ---------------------------------------------------------------------------
# 幂等
# ---------------------------------------------------------------------------


def test_rerun_same_moment_is_zero_delta(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _commit(store, [_turn("turn-old"), _cluster("clu-old", last_heard=T0)], "q0")
    first = _worker(store).run_cycle()
    count_after_first = len(store.list_payloads())

    second = _worker(store).run_cycle()
    assert second.durable_object_delta == 0
    assert len(store.list_payloads()) == count_after_first
    assert first.stage1_marked == ["turn-old"]
    assert first.clusters_retired == ["clu-old"]


# ---------------------------------------------------------------------------
# 政策载入 fail-closed
# ---------------------------------------------------------------------------


def test_policy_loader_rejects_missing_ttl_table() -> None:
    bad = json.loads(json.dumps(_POLICY_JSON))
    del bad["retention_policy"]["ttl_days_by_retention_class"]
    with pytest.raises(AssertionError, match="ttl"):
        RetentionPolicy.from_runtime_policy(bad)


def test_policy_loader_rejects_unknown_retention_class_silently_absent(tmp_path: Path) -> None:
    """法外保留类 = 立刻抛错（Worker 不替法律发明处置规则）。"""
    store = _store(tmp_path)
    alien = _turn("turn-alien")
    alien = alien.model_copy(
        update={
            "source_envelope": SourceEnvelopeV3(
                source_id="s", collector="c", retention_class=RetentionClass.REVOCABLE_RAW
            )
        }
    )
    # 通过 metadata 走私非法类（契约层防不住 payload 直写场景）
    _commit(store, [alien], "q0")
    payloads = store.list_payloads
    policy = _policy()
    worker = RetentionWorker(store, policy, now_fn=lambda: TNOW)
    # monkeypatch: 把已登记类从 TTL 法表中抽走，验证 worker 拒不自作主张
    orig = worker._policy
    object.__setattr__(worker, "_policy", RetentionPolicy(
        ttl_days={k: v for k, v in orig.ttl_days.items() if k != RetentionClass.REVOCABLE_RAW.value},
        quarantine_cooldown_days=orig.quarantine_cooldown_days,
        speaker_cluster_retire_days=orig.speaker_cluster_retire_days,
        policy_version=orig.policy_version,
    ))
    with pytest.raises(AssertionError, match="未在 TTL 法表"):
        worker.run_cycle()
    assert payloads is not None  # noqa: F841 （保留引用防优化）
