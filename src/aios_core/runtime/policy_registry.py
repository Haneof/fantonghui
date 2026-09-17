"""R6 policy registry: hard boundaries, engineering parameters, cognitive policies.

Policy versions are append-only. AI may adapt only policies explicitly registered as
`cognitive_policy` and `mutable_by_ai=True`; it cannot use ordinary strategy learning
to loosen hard boundaries or engineering authorization limits.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.contracts.time import as_utc, canonical_utc_iso, utc_now
from aios_core.storage.idempotency import canonical_json_dumps


class PolicyClass(StrEnum):
    HARD_BOUNDARY = "hard_boundary"
    ENGINEERING_PARAMETER = "engineering_parameter"
    COGNITIVE_POLICY = "cognitive_policy"


class CognitivePolicyVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    policy_class: PolicyClass
    default_value: Any
    current_value: Any
    allowed_range_or_choices: Any = None
    mutable_by_ai: bool = False
    reason: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    changed_by: str = Field(min_length=1)
    changed_at: datetime = Field(default_factory=utc_now)
    version: int = Field(ge=1)
    previous_version: int | None = Field(default=None, ge=1)
    rollback_pointer: int | None = Field(default=None, ge=1)
    evaluation_window: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy(self) -> "CognitivePolicyVersion":
        as_utc(self.changed_at, "changed_at")
        for name in ("policy_id", "scope", "reason", "changed_by", "evaluation_window"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be blank")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence_refs must contain only non-blank strings")
        if self.version == 1 and self.previous_version is not None:
            raise ValueError("version 1 cannot have previous_version")
        if self.version > 1 and self.previous_version != self.version - 1:
            raise ValueError("policy versions must form a contiguous chain")
        if self.rollback_pointer is not None and self.rollback_pointer >= self.version:
            raise ValueError("rollback_pointer must point to an earlier version")
        if self.policy_class is PolicyClass.HARD_BOUNDARY and self.mutable_by_ai:
            raise ValueError("hard boundaries cannot be mutable_by_ai")
        if self.mutable_by_ai and self.policy_class is not PolicyClass.COGNITIVE_POLICY:
            raise ValueError("only cognitive_policy entries may be mutable_by_ai")

        allowed = self.allowed_range_or_choices
        if isinstance(allowed, dict) and ("min" in allowed or "max" in allowed):
            if not isinstance(self.current_value, (int, float)) or isinstance(self.current_value, bool):
                raise ValueError("numeric allowed range requires a numeric current_value")
            if "min" in allowed and self.current_value < allowed["min"]:
                raise ValueError("current_value is below allowed policy range")
            if "max" in allowed and self.current_value > allowed["max"]:
                raise ValueError("current_value is above allowed policy range")
        elif isinstance(allowed, (list, tuple, set)) and allowed:
            if self.current_value not in allowed:
                raise ValueError("current_value is not one of allowed policy choices")
        return self


class PolicyConflict(ValueError):
    pass


class PolicyAuthorizationError(PermissionError):
    pass


class CognitivePolicyRegistry:
    """Append-only policy ledger with AI mutation authorization checks."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_policy_versions(
                    policy_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    scope TEXT NOT NULL,
                    policy_class TEXT NOT NULL,
                    mutable_by_ai INTEGER NOT NULL,
                    changed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(policy_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_policy_latest
                ON runtime_policy_versions(policy_id, version DESC)
                """
            )
            conn.commit()

    @staticmethod
    def _decode(raw: str) -> CognitivePolicyVersion:
        return CognitivePolicyVersion.model_validate(json.loads(raw))

    def latest(self, policy_id: str) -> CognitivePolicyVersion | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM runtime_policy_versions WHERE policy_id=? ORDER BY version DESC LIMIT 1",
                (policy_id,),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def get(self, policy_id: str, version: int) -> CognitivePolicyVersion | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM runtime_policy_versions WHERE policy_id=? AND version=?",
                (policy_id, version),
            ).fetchone()
        return None if row is None else self._decode(str(row["payload_json"]))

    def history(self, policy_id: str) -> list[CognitivePolicyVersion]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM runtime_policy_versions WHERE policy_id=? ORDER BY version ASC",
                (policy_id,),
            ).fetchall()
        return [self._decode(str(row["payload_json"])) for row in rows]

    def append(
        self,
        policy: CognitivePolicyVersion,
        *,
        actor_is_ai: bool = False,
    ) -> CognitivePolicyVersion:
        policy = CognitivePolicyVersion.model_validate(policy.model_dump(mode="python"))
        current = self.latest(policy.policy_id)

        if actor_is_ai:
            if current is None:
                raise PolicyAuthorizationError("AI cannot create a new policy registration")
            if current.policy_class is not PolicyClass.COGNITIVE_POLICY or not current.mutable_by_ai:
                raise PolicyAuthorizationError(f"policy {policy.policy_id!r} is not mutable by AI")
            if not policy.evidence_refs:
                raise PolicyAuthorizationError("AI policy changes require evidence_refs")

        if current is None:
            if policy.version != 1:
                raise PolicyConflict("initial policy version must be 1")
        else:
            if policy.version != current.version + 1:
                raise PolicyConflict(
                    f"policy {policy.policy_id!r} must append version {current.version + 1}, got {policy.version}"
                )
            for attr in (
                "scope",
                "policy_class",
                "mutable_by_ai",
                "default_value",
                "allowed_range_or_choices",
            ):
                if getattr(policy, attr) != getattr(current, attr):
                    raise PolicyConflict(f"{attr} cannot change through an ordinary policy value update")

        payload = canonical_json_dumps(policy.model_dump(mode="python"))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT MAX(version) AS version FROM runtime_policy_versions WHERE policy_id=?",
                (policy.policy_id,),
            ).fetchone()
            durable_current = int(row["version"]) if row and row["version"] is not None else 0
            if policy.version != durable_current + 1:
                conn.rollback()
                raise PolicyConflict(
                    f"concurrent policy update: expected version {durable_current + 1}, got {policy.version}"
                )
            conn.execute(
                """
                INSERT INTO runtime_policy_versions(
                    policy_id, version, scope, policy_class, mutable_by_ai,
                    changed_at, payload_json
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    policy.policy_id,
                    policy.version,
                    policy.scope,
                    policy.policy_class.value,
                    int(policy.mutable_by_ai),
                    canonical_utc_iso(policy.changed_at, "changed_at"),
                    payload,
                ),
            )
            conn.commit()
        return policy

    def rollback(
        self,
        policy_id: str,
        target_version: int,
        *,
        changed_by: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
        actor_is_ai: bool = False,
    ) -> CognitivePolicyVersion:
        current = self.latest(policy_id)
        target = self.get(policy_id, target_version)
        if current is None or target is None:
            raise KeyError(f"unknown policy/version: {policy_id}@{target_version}")
        next_version = CognitivePolicyVersion(
            policy_id=current.policy_id,
            scope=current.scope,
            policy_class=current.policy_class,
            default_value=current.default_value,
            current_value=target.current_value,
            allowed_range_or_choices=current.allowed_range_or_choices,
            mutable_by_ai=current.mutable_by_ai,
            reason=reason,
            evidence_refs=evidence_refs,
            changed_by=changed_by,
            version=current.version + 1,
            previous_version=current.version,
            rollback_pointer=target.version,
            evaluation_window=current.evaluation_window,
        )
        return self.append(next_version, actor_is_ai=actor_is_ai)
