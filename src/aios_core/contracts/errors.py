from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from aios_core.contracts.enums import ErrorCode


class ErrorResponse(BaseModel):
    """协议级错误响应模型

    code: 机器可分支的错误码
    message: 人类可读说明，不允许空字符串
    context: 机器可读细节，JSON可序列化
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    code: ErrorCode
    message: Annotated[str, Field(min_length=1, description="Human readable message, must not be empty")]
    context: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Machine readable details, JSON serializable",
    )
