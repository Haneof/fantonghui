from __future__ import annotations

import copy

from pydantic import JsonValue

from aios_core.contracts.enums import ErrorCode
from aios_core.contracts.errors import ErrorResponse


class AIOSProtocolError(Exception):
    """Core 内部向协议边界传播已知、可分类失败的统一异常

    code: 机器分支语义
    message: 人类可读说明
    context: 机器可读细节，JSON可序列化，严格JSON

    不变量：
    - 构造阶段立即通过 ErrorResponse 验证，非JSON/NaN/Infinity/空message 立即失败
    - 原始调用者dict后续修改不得污染内部
    - err.context 返回独立可变拷贝，修改不得污染内部
    - to_response() 稳定，返回深拷贝，不受外部修改影响
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        context: dict[str, JsonValue] | None = None,
    ) -> None:
        # 1. code 类型检查
        if not isinstance(code, ErrorCode):
            raise TypeError(f"code must be ErrorCode, got {type(code)}")

        # 2. 立即通过 ErrorResponse 验证 (唯一协议验证源)
        #    这会验证 message 非空, context JSON可序列化, 拒绝 NaN/Infinity, 拒绝额外字段
        validated = ErrorResponse(
            code=code,
            message=message,
            context={} if context is None else context,
        )

        # 3. 内部保存经过验证后的独立深拷贝
        #    使用 model_copy(deep=True) 确保内部状态与外部隔离
        self._response = validated.model_copy(deep=True)

        # 4. 基类初始化使用验证后的 message
        super().__init__(self._response.message)

    @property
    def code(self) -> ErrorCode:
        return self._response.code

    @property
    def message(self) -> str:
        return self._response.message

    @property
    def context(self) -> dict[str, JsonValue]:
        # 返回深拷贝，防止外部通过 getter 修改内部状态
        return copy.deepcopy(self._response.context)

    def to_response(self) -> ErrorResponse:
        # 返回深拷贝，保证稳定性，不受之前外部修改影响
        return self._response.model_copy(deep=True)

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, context={self._response.context!r})"
