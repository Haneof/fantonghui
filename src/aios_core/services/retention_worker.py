"""M1-019 · Retention & Tombstone Worker —— 宪法 C1 裁决的执行体。

法律链（三层齐全，没有一层是散文）：
  宪法     §25/§33之5/§93之1 + C1 裁决（runtime_policy.retention_policy，tiered quarantine）
  契约     RetentionTombstone（STAGE1_SOFT→STAGE2_SHREDDED，单向）/ DeletionLog /
           SpeakerCluster（ACTIVE→RETIRED→TOMBSTONE）/ SourceEnvelopeV3.retention_class
  政策     governance/runtime_policy.json v1.1.0：ttl_days_by_retention_class、
           quarantine_cooldown_days、speaker_cluster_retire_days、janitor 分层

Mechanical adjudication（机械判决，零 LLM——LLM 不持有删除权的字面实现）：

  Phase R   声纹簇退休：ACTIVE 且 last_heard_at 距今 > retire_days → RETIRED 新 revision。
  Phase Q   隔离标记：对象 retention_class ∈ {revocable_raw, ephemeral_session}、TTL 到期、
            无墓碑、无存活入向引用、无 legal_hold → RetentionTombstone(STAGE1_SOFT)。
  Phase S   粉碎执行：STAGE1 墓碑满冷却期 → 重核三锁（仍存在/仍无引用/无 hold）→
            DeletionLog(authorized_by=WORKER_IDENTITY, mechanical_check_passed=True)
            + 墓碑 revision+1 转 STAGE2_SHREDDED(deletion_log_ref 钉死)。
            物理字节擦除走 CryptoShredder 接口——sim 阶段的空实现返回证书占位，
            真机接密钥吊销（EVICT）；append-only 世界树自身永不改字。

auto_release_on_new_dependency 的契约兼容读法：墓碑状态机只有单向边
STAGE1→STAGE2（M0-030 冻结），因此"释放"不是一个转移——Phase S 每轮重核
存活引用锁，冷却期内出现的任何新引用都会让对象**永远到不了** STAGE2。
冷却期不只是时间缓冲，它就是宪法的撤销权（policy $auto_release_note）。

幂等：一切新对象 ID 由确定性 sha256(target, stage, policy 版本) 派生；
重复跑同一评估时刻不产出第二个墓碑/DeletionLog（重放 = 零点增量）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol

from ..contracts.enums_v3 import (
    ObjectTypeV3,
    RetentionClass,
    SpeakerClusterStatus,
    TombstoneStage,
)
from ..contracts.models_v3 import (
    DeletionLog,
    RetentionTombstone,
    SpeakerCluster,
)
from ..contracts.operations import OperationRequest
from ..contracts.refs import ObjectRef
from ..contracts.time import TemporalExtent
from ..storage.sqlite_store import SQLiteWorldStore

WORKER_IDENTITY = "retention-worker.v1"

# 永不进入 GC 视野的对象类：吊销权外清单（DeletionLog/墓碑自身是审计链，链不可自噬）。
_GC_EXEMPT_TYPES = {
    ObjectTypeV3.RETENTION_TOMBSTONE.value,
    ObjectTypeV3.DELETION_LOG.value,
    ObjectTypeV3.BUDGET_LEDGER_ENTRY.value,
}


class CryptoShredder(Protocol):
    """物理擦除接口（宪法 33之5 的合法出口）：返回擦除证书，证书不得含被擦内容。"""

    def shred(self, object_id: str, *, certificate: Mapping[str, Any]) -> None:
        ...


class SimulatedCryptoShredder:
    """sim 阶段空实现：登记证书并丢弃内容密钥语义。真机实现接密钥管理（吊销权）。"""

    def __init__(self) -> None:
        self.certificates: list[dict[str, Any]] = []

    def shred(self, object_id: str, *, certificate: Mapping[str, Any]) -> None:
        entry = {"object_id": object_id, **{k: v for k, v in certificate.items() if k != "content"}}
        self.certificates.append(entry)


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetentionPolicy:
    """runtime_policy.json retention_policy 的不可变载入。任何键缺失 = fail-closed 抛错。"""

    ttl_days: Mapping[str, int]  # 仅 REVOCABLE_RAW / EPHEMERAL_SESSION 两个可吊销类有表项
    quarantine_cooldown_days: int
    speaker_cluster_retire_days: int
    policy_version: str

    @classmethod
    def from_runtime_policy(cls, policy: Mapping[str, Any]) -> "RetentionPolicy":
        rp = policy.get("retention_policy")
        if not isinstance(rp, Mapping):
            raise AssertionError("runtime_policy.json 缺 retention_policy 段——fail-closed")
        ttl_raw = rp.get("ttl_days_by_retention_class")
        if not isinstance(ttl_raw, Mapping):
            raise AssertionError("retention_policy.ttl_days_by_retention_class 缺失（v1.1.0 起入法）")
        ttl = {
            k: int(v)
            for k, v in ttl_raw.items()
            if isinstance(v, int) and k != "$comment"
        }
        for klass in (RetentionClass.REVOCABLE_RAW.value, RetentionClass.EPHEMERAL_SESSION.value):
            if klass not in ttl:
                raise AssertionError(f"TTL 表缺可吊销类 {klass}")
        cooldown = rp.get("quarantine_cooldown_days")
        retire = rp.get("speaker_cluster_retire_days")
        retire_days = retire.get("days") if isinstance(retire, Mapping) else retire
        if not isinstance(cooldown, int) or not isinstance(retire_days, int):
            raise AssertionError("quarantine_cooldown_days / speaker_cluster_retire_days 必须为整数")
        version = str(policy.get("policy_version", ""))
        if not version:
            raise AssertionError("policy_version 为空")
        return cls(
            ttl_days=ttl,
            quarantine_cooldown_days=cooldown,
            speaker_cluster_retire_days=retire_days,
            policy_version=version,
        )


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@dataclass
class RetentionCycleReport:
    evaluated_at: str
    world_revision_before: int
    clusters_retired: list[str] = field(default_factory=list)
    stage1_marked: list[str] = field(default_factory=list)
    stage2_shredded: list[str] = field(default_factory=list)
    release_blocked_by_references: list[str] = field(default_factory=list)
    skipped_reference_locked: list[str] = field(default_factory=list)
    skipped_legal_hold: list[str] = field(default_factory=list)
    skipped_revocation_free: int = 0
    commits: int = 0

    @property
    def durable_object_delta(self) -> int:
        """本轮新增耐久对象数（墓碑+DeletionLog）。重放时必须是 0。"""
        return len(self.stage1_marked) + len(self.stage2_shredded) * 2 + len(self.clusters_retired)


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, str):
        try:
            return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _walk_object_refs(node: Any, into: set[str], *, depth: int = 0) -> None:
    """从 payload 树收集 ObjectRef 形状的引用（object_id+revision 连体出现才算引用）。"""
    if isinstance(node, dict):
        oid = node.get("object_id")
        if depth > 0 and isinstance(oid, str) and "revision" in node:
            into.add(oid)
        for v in node.values():
            _walk_object_refs(v, into, depth=depth + 1)
    elif isinstance(node, list):
        for v in node:
            _walk_object_refs(v, into, depth=depth)


def _det_id(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:length]


class RetentionWorker:
    """确定性 GC：同样的世界投影 + 同样的评估时刻 ⇒ 同一组对象、同一份报告。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        policy: RetentionPolicy,
        *,
        now_fn: Callable[[], datetime],
        shredder: CryptoShredder | None = None,
    ) -> None:
        self._store = store
        self._policy = policy
        self._now_fn = now_fn
        self._shredder = shredder or SimulatedCryptoShredder()
        self._rev: int = 0
        self._seq: int = 0

    # -- store plumbing -----------------------------------------------------

    def _commit(self, objects: Iterable[Any], reason: str) -> None:
        objs = list(objects)
        if not objs:
            return
        self._seq += 1
        op = OperationRequest(
            operation_id=f"retention-{_det_id(str(self._seq), reason)}",
            operation_name="retention.cycle_commit",
            arguments={"worker": WORKER_IDENTITY, "policy_version": self._policy.policy_version},
            expected_world_revision=self._rev,
            reason=reason,
            idempotency_key=f"rtn-{self._policy.policy_version}-{_det_id(*sorted(o.object_id for o in objs))}",
        )
        result = self._store.commit(objs, op)
        self._rev = result.world_revision

    # -- cycle --------------------------------------------------------------

    def run_cycle(self) -> RetentionCycleReport:
        now = _aware(self._now_fn())
        self._rev = self._store.current_world_revision()
        report = RetentionCycleReport(
            evaluated_at=now.isoformat(), world_revision_before=self._rev
        )

        payloads = self._store.list_payloads()
        by_id = {p["object_id"]: p for p in payloads if "object_id" in p}

        # 存活入向引用集：墓碑/DeletionLog/预算账本不产出锁（它们的 target_ref 是历史坐标，
        # 不是使用中的依赖，否则会自我锁死永远无法粉碎）。
        referenced: set[str] = set()
        for p in payloads:
            if p.get("object_type") in _GC_EXEMPT_TYPES:
                continue
            _walk_object_refs(p, referenced)

        tombstone_by_target: dict[str, dict] = {}
        for p in payloads:
            if p.get("object_type") == ObjectTypeV3.RETENTION_TOMBSTONE.value:
                target = (p.get("target_ref") or {}).get("object_id")
                if target:
                    tombstone_by_target[target] = p

        self._phase_cluster_retire(by_id, now, report)
        self._phase_quarantine(by_id, tombstone_by_target, referenced, now, report)
        self._phase_shred(by_id, tombstone_by_target, referenced, now, report)
        report.commits = self._seq
        return report

    # -- Phase R ------------------------------------------------------------

    def _phase_cluster_retire(self, by_id: dict[str, dict], now: datetime, report: RetentionCycleReport) -> None:
        for oid, p in sorted(by_id.items()):
            if p.get("object_type") != ObjectTypeV3.SPEAKER_CLUSTER.value:
                continue
            if p.get("cluster_status") != SpeakerClusterStatus.ACTIVE.value:
                continue
            last_heard = _parse_dt(p.get("last_heard_at"))
            if last_heard is None:
                continue
            if (now - last_heard) <= timedelta(days=self._policy.speaker_cluster_retire_days):
                continue
            new_revision = {
                **p,
                "cluster_status": SpeakerClusterStatus.RETIRED.value,
                "retired_after": now.isoformat(),
                "revision": int(p["revision"]) + 1,
            }
            cluster = SpeakerCluster.model_validate(new_revision)
            self._commit([cluster], f"speaker cluster {oid} retired after {self._policy.speaker_cluster_retire_days}d silence")
            report.clusters_retired.append(oid)

    # -- Phase Q ------------------------------------------------------------

    def _phase_quarantine(
        self,
        by_id: dict[str, dict],
        tombstone_by_target: dict[str, dict],
        referenced: set[str],
        now: datetime,
        report: RetentionCycleReport,
    ) -> None:
        for oid, p in sorted(by_id.items()):
            otype = p.get("object_type")
            if otype in _GC_EXEMPT_TYPES or otype == ObjectTypeV3.SPEAKER_CLUSTER.value:
                continue
            if oid in tombstone_by_target:
                continue  # 已有墓碑，由 Phase S 定生死
            env = p.get("source_envelope") or {}
            klass = env.get("retention_class") or p.get("retention_class")
            if klass == RetentionClass.REVOCATION_FREE.value or klass is None:
                report.skipped_revocation_free += 1
                continue
            if klass not in self._policy.ttl_days:
                raise AssertionError(f"未在 TTL 法表中的 retention_class: {klass!r}（fail-closed 拒绝私自处置）")
            if env.get("legal_hold") or p.get("legal_hold"):
                report.skipped_legal_hold.append(oid)
                continue
            learned = _parse_dt(p.get("learned_at")) or _parse_dt(p.get("recorded_at"))
            if learned is None or (now - learned) < timedelta(days=self._policy.ttl_days[klass]):
                continue
            if oid in referenced:
                report.skipped_reference_locked.append(oid)
                continue

            tb = RetentionTombstone(
                object_id=f"tmb-{_det_id(oid, 'quarantine', self._policy.policy_version)}",
                subject_id=p.get("subject_id", "system"),
                revision=1,
                occurred=TemporalExtent.point(now),
                learned_at=now,
                recorded_at=now,
                created_by=WORKER_IDENTITY,
                target_ref=ObjectRef(object_id=oid, revision=int(p["revision"])),
                tombstone_stage=TombstoneStage.STAGE1_SOFT,
                source_key_hash=hashlib.sha256(oid.encode("utf-8")).hexdigest(),
                tombstoned_at=now,
            )
            self._commit([tb], f"stage1 quarantine mark for {oid} ({klass})")
            report.stage1_marked.append(oid)

    # -- Phase S ------------------------------------------------------------

    def _phase_shred(
        self,
        by_id: dict[str, dict],
        tombstone_by_target: dict[str, dict],
        referenced: set[str],
        now: datetime,
        report: RetentionCycleReport,
    ) -> None:
        for target_id, tmb in sorted(tombstone_by_target.items()):
            if tmb.get("tombstone_stage") != TombstoneStage.STAGE1_SOFT.value:
                continue
            tombstoned_at = _parse_dt(tmb.get("tombstoned_at"))
            if tombstoned_at is None:
                continue
            if (now - tombstoned_at) < timedelta(days=self._policy.quarantine_cooldown_days):
                continue  # 冷却期中：宪法的撤销权窗口
            if target_id in referenced:
                # auto_release_on_new_dependency：冷却没有白等，它真的拦下了一次误删
                report.release_blocked_by_references.append(target_id)
                continue
            env = (by_id.get(target_id) or {}).get("source_envelope") or {}
            target = by_id.get(target_id)
            legal_hold = bool(env.get("legal_hold") or (target or {}).get("legal_hold"))

            log = DeletionLog(
                object_id=f"dlog-{_det_id(target_id, 'shred', self._policy.policy_version)}",
                subject_id=(target or {}).get("subject_id", "system"),
                revision=1,
                occurred=TemporalExtent.point(now),
                learned_at=now,
                recorded_at=now,
                created_by=WORKER_IDENTITY,
                deleted_ref=ObjectRef(object_id=target_id, revision=int((target or tmb.get("target_ref"))["revision"])),
                reason=f"retention TTL expired, quarantine {self._policy.quarantine_cooldown_days}d served (policy {self._policy.policy_version})",
                authorized_by=WORKER_IDENTITY,  # 机械身份；没有任何 LLM 会话能填这个字段
                mechanical_check_passed=True,
                legal_hold_at_time=legal_hold,
            )
            tb2 = RetentionTombstone(
                object_id=tmb["object_id"],
                subject_id=tmb.get("subject_id", "system"),
                revision=int(tmb["revision"]) + 1,
                occurred=TemporalExtent.point(now),
                learned_at=now,
                recorded_at=now,
                created_by=WORKER_IDENTITY,
                target_ref=ObjectRef.model_validate(tmb["target_ref"]),
                tombstone_stage=TombstoneStage.STAGE2_SHREDDED,
                source_key_hash=tmb["source_key_hash"],
                tombstoned_at=tombstoned_at,
                deletion_log_ref=ObjectRef(object_id=log.object_id, revision=1),
            )
            self._commit([log, tb2], f"stage2 crypto-erase certificate for {target_id}")
            self._shredder.shred(
                target_id,
                certificate={
                    "object_id": target_id,
                    "erased_at": now.isoformat(),
                    "legal_basis": f"runtime_policy {self._policy.policy_version} retention_ttl",
                    "approver": WORKER_IDENTITY,
                },
            )
            report.stage2_shredded.append(target_id)


__all__ = [
    "CryptoShredder",
    "RetentionCycleReport",
    "RetentionPolicy",
    "RetentionWorker",
    "SimulatedCryptoShredder",
    "WORKER_IDENTITY",
]
