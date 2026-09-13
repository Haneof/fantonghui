from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .ids import new_operation_id


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(default_factory=new_operation_id)
    session_id: str | None = None
    operation_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_world_revision: int = Field(ge=0)
    reason: str
    idempotency_key: str


class CommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    world_revision: int = Field(ge=0)
    object_refs: list[tuple[str, int]]
    idempotent_replay: bool = False
