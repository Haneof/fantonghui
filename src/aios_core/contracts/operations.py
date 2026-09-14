from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ids import new_operation_id


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    operation_id: str = Field(default_factory=new_operation_id, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    operation_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_world_revision: int = Field(ge=0)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_nonblank_identity_fields(self) -> "OperationRequest":
        for field_name in [
            "operation_id",
            "operation_name",
            "reason",
            "idempotency_key",
        ]:
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.session_id is not None and not self.session_id.strip():
            raise ValueError("session_id must not be blank when provided")
        return self


class CommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1)
    world_revision: int = Field(ge=0)
    object_refs: list[tuple[str, int]]
    idempotent_replay: bool = False


class OperationAuditRecord(BaseModel):
    """Durable audit view for one committed OperationRequest."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1)
    session_id: str | None = None
    operation_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_world_revision: int = Field(ge=0)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    status: str = Field(min_length=1)
    result_world_revision: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
