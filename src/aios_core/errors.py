from __future__ import annotations

from typing import Any

from pydantic import JsonValue

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.errors import ErrorResponse


class AIOSProtocolError(Exception):
    """Core 内部向协议边界传播已知、可分类失败的统一异常

    code: 机器分支语义
    message: 人类可读说明
    context: 机器可读细节，JSON可序列化

    to_response() 返回 ErrorResponse
    str(exception) 返回 message，方便日志阅读，但业务代码禁止依赖 str
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        context: dict[str, JsonValue] | None = None,
    ) -> None:
        if not isinstance(code, ErrorCode):
            raise TypeError(f"code must be ErrorCode, got {type(code)}")
        if not message or not isinstance(message, str):
            raise ValueError("message must be non-empty string")
        # context validation will be done via ErrorResponse
        self._code = code
        self._message = message
        self._context: dict[str, JsonValue] = context if context is not None else {}
        super().__init__(message)

    @property
    def code(self) -> ErrorCode:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def context(self) -> dict[str, JsonValue]:
        return self._context

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            code=self.code,
            message=self.message,
            context=self.context,
        )

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, context={self.context!r})"
