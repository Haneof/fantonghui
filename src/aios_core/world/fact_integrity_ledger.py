"""M1-018 补充件：客观事实完整性台账（SHA-256 基线 + 数据库层不可变约束）。

为什么在 `retrospective_annotation.py` 之外再加这一件
-----------------------------------------------------
同分支的 M1-018 主实现（提交 `829a0a2`）已经交付了回溯加注日志、
双时间认知透镜与单跳隔离，并用 SQLite authorizer 追踪证明**代码路径
没有发出** UPDATE / DELETE。那是对"我方代码守规矩"的审计证明。

本件补的是另一件事，两者互补、不重叠：

1. **持久化的哈希基线**。主实现的 SHA-256 只在测试内即时计算，
   基线从不落库。基线不落库就意味着：一个月后磁盘级篡改、
   运维误操作、备份回滚错位都**无法被发现**——没有可比对的基准。
2. **数据库层的硬约束**。authorizer 只能拦截经过该连接的语句；
   本件在台账表上挂 ``BEFORE UPDATE`` / ``BEFORE DELETE`` 触发器，
   任何连接、任何工具、任何绕过应用层的操作都会被 ``RAISE(ABORT)`` 拒绝。
   这不是"承诺不写 UPDATE"，而是**写不出来**。

与 M0 冻结契约的关系
--------------------
只创建自己的两张追加式侧表，**不修改** ``ObjectType`` 枚举、
**不 ``ALTER``** ``object_revisions``。台账是可随时从 ``object_revisions``
重建的派生记录，但它一旦封存即不可改。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import canonical_utc_iso, require_aware

__all__ = [
    "FactImmutabilityLedger",
    "FactIntegrityReport",
    "SealedFact",
    "canonical_fact_sha256",
]


# ---------------------------------------------------------------------------
# 规范化哈希
# ---------------------------------------------------------------------------


def _json_default(value: object) -> Any:
    if isinstance(value, datetime):
        return canonical_utc_iso(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    return str(value)


def canonical_fact_sha256(payload: Any) -> str:
    """对任意可 JSON 化的事实载荷计算确定性 SHA-256。

    规范化规则缺一即不可复现，故在此固化：

    - 键按字典序排序，消除 dict 插入序差异；
    - 紧凑分隔符，无多余空白；
    - ``ensure_ascii=False`` + UTF-8，中文不被转义成 ``\\uXXXX``；
    - ``datetime`` 统一走 :func:`canonical_utc_iso`（UTC、微秒精度），
      因此同一时刻的不同时区表示得到同一哈希。
    """
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 契约
# ---------------------------------------------------------------------------


class SealedFact(BaseModel):
    """完整性台账里的一条封存事实。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    object_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    occurred_at: datetime
    learned_at: datetime
    canonical_sha256: str = Field(min_length=64, max_length=64)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_times(self) -> SealedFact:
        require_aware(self.occurred_at, "occurred_at")
        require_aware(self.learned_at, "learned_at")
        return self


class FactIntegrityReport(BaseModel):
    """全量完整性校验结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checked: int = Field(ge=0)
    intact: int = Field(ge=0)
    mismatched_object_ids: tuple[str, ...] = ()

    @property
    def all_intact(self) -> bool:
        return not self.mismatched_object_ids and self.checked == self.intact


_DDL = """
CREATE TABLE IF NOT EXISTS fact_integrity_ledger (
    object_id        TEXT    NOT NULL,
    revision         INTEGER NOT NULL,
    object_type      TEXT    NOT NULL,
    subject_id       TEXT    NOT NULL,
    occurred_at      TEXT    NOT NULL,
    learned_at       TEXT    NOT NULL,
    payload_json     TEXT    NOT NULL,
    canonical_sha256 TEXT    NOT NULL,
    sealed_at        TEXT    NOT NULL,
    PRIMARY KEY (object_id, revision)
);

CREATE INDEX IF NOT EXISTS idx_fact_ledger_subject_occurred
    ON fact_integrity_ledger (subject_id, occurred_at);
"""

# 宪法第九十三条的机械化：台账追加式，任何 UPDATE / DELETE 在数据库层 ABORT。
# 注意 RAISE() 只接受单个字符串字面量，不接受 || 拼接表达式。
_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_fact_ledger_no_update
BEFORE UPDATE ON fact_integrity_ledger
BEGIN
    SELECT RAISE(ABORT,
      'AIOS art.93: sealed fact ledger is append-only, UPDATE is forbidden');
END;

CREATE TRIGGER IF NOT EXISTS trg_fact_ledger_no_delete
BEFORE DELETE ON fact_integrity_ledger
BEGIN
    SELECT RAISE(ABORT,
      'AIOS art.93: sealed fact ledger is append-only, DELETE is forbidden');
END;
"""


class FactImmutabilityLedger:
    """客观事实的 SHA-256 封存台账。

    接受任意 ``sqlite3.Connection``（内存库、独立台账文件、或与主库同文件）。
    只操作 ``fact_integrity_ledger`` 一张表。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_DDL)
            self._conn.executescript(_TRIGGERS)

    # ------------------------------------------------------------- 封存

    def seal_fact(
        self,
        *,
        object_id: str,
        revision: int,
        object_type: str,
        subject_id: str,
        occurred_at: datetime,
        learned_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        """封存一条客观事实并登记其 SHA-256，返回哈希。"""
        require_aware(occurred_at, "occurred_at")
        require_aware(learned_at, "learned_at")
        digest = canonical_fact_sha256(payload)
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO fact_integrity_ledger "
                "(object_id, revision, object_type, subject_id, occurred_at, "
                " learned_at, payload_json, canonical_sha256, sealed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    object_id,
                    revision,
                    object_type,
                    subject_id,
                    canonical_utc_iso(occurred_at),
                    canonical_utc_iso(learned_at),
                    json.dumps(
                        payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        default=_json_default,
                    ),
                    digest,
                    canonical_utc_iso(datetime.now(UTC)),
                ),
            )
        return digest

    def seal_many(self, facts: Iterable[dict[str, Any]]) -> int:
        """批量封存，单事务提交（逐条事务在 18,000 条量级会慢一个数量级）。"""
        sealed_at = canonical_utc_iso(datetime.now(UTC))
        rows: list[tuple[Any, ...]] = []
        for fact in facts:
            payload = fact["payload"]
            rows.append(
                (
                    fact["object_id"],
                    fact["revision"],
                    fact["object_type"],
                    fact["subject_id"],
                    canonical_utc_iso(fact["occurred_at"]),
                    canonical_utc_iso(fact["learned_at"]),
                    json.dumps(
                        payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        default=_json_default,
                    ),
                    canonical_fact_sha256(payload),
                    sealed_at,
                )
            )
        if not rows:
            return 0
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO fact_integrity_ledger "
                "(object_id, revision, object_type, subject_id, occurred_at, "
                " learned_at, payload_json, canonical_sha256, sealed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    # ------------------------------------------------------------- 校验

    def verify_fact_integrity(self) -> FactIntegrityReport:
        """逐条重算哈希并与台账基线比对，报出被篡改的对象。

        这是本件存在的理由：基线**已落库**，因此可以在任意后续时刻、
        由任意进程复核，发现磁盘级篡改、运维误操作与备份回滚错位。
        """
        cursor = self._conn.execute(
            "SELECT object_id, payload_json, canonical_sha256 FROM fact_integrity_ledger"
        )
        checked = 0
        intact = 0
        mismatched: list[str] = []
        for object_id, payload_json, expected in cursor.fetchall():
            checked += 1
            if canonical_fact_sha256(json.loads(payload_json)) == expected:
                intact += 1
            else:
                mismatched.append(object_id)
        return FactIntegrityReport(
            checked=checked,
            intact=intact,
            mismatched_object_ids=tuple(sorted(mismatched)),
        )

    # ------------------------------------------------------------- 读取

    def facts_for(
        self,
        subject_id: str,
        *,
        up_to: datetime | None = None,
    ) -> tuple[SealedFact, ...]:
        """按主体取封存事实；``up_to`` 过滤**发生时间**（AS_OF 语义）。"""
        clauses = ["subject_id = ?"]
        params: list[Any] = [subject_id]
        if up_to is not None:
            require_aware(up_to, "up_to")
            clauses.append("occurred_at <= ?")
            params.append(canonical_utc_iso(up_to))

        rows = self._conn.execute(
            "SELECT object_id, revision, object_type, subject_id, occurred_at, "
            "learned_at, payload_json, canonical_sha256 "
            f"FROM fact_integrity_ledger WHERE {' AND '.join(clauses)} "
            "ORDER BY occurred_at, object_id",
            params,
        ).fetchall()

        return tuple(
            SealedFact(
                object_id=object_id,
                revision=revision,
                object_type=object_type,
                subject_id=subject_id_value,
                occurred_at=datetime.fromisoformat(occurred_at),
                learned_at=datetime.fromisoformat(learned_at),
                canonical_sha256=digest,
                payload=json.loads(payload_json),
            )
            for (
                object_id,
                revision,
                object_type,
                subject_id_value,
                occurred_at,
                learned_at,
                payload_json,
                digest,
            ) in rows
        )

    def fact_count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) FROM fact_integrity_ledger").fetchone()[
                0
            ]
        )

    def digest_of(self, object_id: str, revision: int = 1) -> str | None:
        row = self._conn.execute(
            "SELECT canonical_sha256 FROM fact_integrity_ledger "
            "WHERE object_id = ? AND revision = ?",
            (object_id, revision),
        ).fetchone()
        return None if row is None else str(row[0])
