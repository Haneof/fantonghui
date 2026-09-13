# M0-002 实现记录

状态：

WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

统一错误码、协议级错误结构与机器可恢复异常契约

起始commit：

8197c4f943c8e06f87bf25f18d79aceef982e196

## 实现了什么

1. 新建 `src/aios_core/contracts/errors.py`:
   - ErrorResponse (Pydantic, extra="forbid", frozen=True, code: ErrorCode, message: min_length=1, context: dict[str, JsonValue] default {})

2. 新建 `src/aios_core/errors.py`:
   - AIOSProtocolError (code, message, context, to_response(), str() 返回 message, 保留 __cause__ 用于内部日志, response 不泄露 traceback)

3. 修改 `src/aios_core/contracts/__init__.py`:
   - 显式导出 ErrorResponse

4. 修改 `src/aios_core/storage/sqlite_store.py`:
   - StoreError 继承 AIOSProtocolError (原 RuntimeError)
   - 所有已存在 StoreError 增加结构化 context:
     - empty commit: INVALID_ARGUMENT {operation_id, reason="empty_commit"}
     - world revision conflict: VERSION_CONFLICT {expected_world_revision, current_world_revision, operation_id}
     - duplicate revision: INVALID_ARGUMENT {operation_id, reason}
     - object revision conflict: VERSION_CONFLICT {object_id, expected_revision, actual_revision}
     - self reference: DEPENDENCY_INVALID {object_id, revision}
     - reference not found: NOT_FOUND {referenced_object_id, referenced_revision (None=>null)}
     - get_payload not found: NOT_FOUND {object_id, revision}
     - operation not found: NOT_FOUND {operation_id}
   - 未修改 schema/事务/append-only/idempotency/validation

5. 新建 `tests/unit/test_errors.py` 24 tests:
   - E01-E20 全覆盖
   - message独立性测试
   - 安全序列化测试
   - 其他错误码可构造性
   - operation not found

6. README 增加 M0-002 错误协议简短说明 (code/message/context 职责)

7. TASK_PROGRESS_R2.md 更新为 CODE COMPLETE / WAITING CHIEF REVIEW

## 哪些没有实现

- 未新增 ErrorCode (INTERNAL_SERVER_ERROR 等)，遵守冻结10个
- 未修改现有 ErrorCode 字符串值
- 未实现完整 idempotency conflict detection (由 M0-016 完成)
- 未实现完整 Action Runtime (仅最小模拟 OUTCOME_UNKNOWN timeout)
- 未实现 HTTP mapping / API server
- 未实现完整 logging infrastructure (仅通过 exception chaining 保留 __cause__)
- 未修改 reference (保持冻结, 15 tests 通过)
- 未修改 schema/事务/idempotency算法

## 为什么没有越界到 M0-016 / Action Runtime / API

- M0-002 只冻结错误协议，不实现完整业务
- OUTCOME_UNKNOWN 测试使用最小模拟 Action boundary 捕获 TimeoutError 转换，不创建正式 Action执行器
- IDEMPOTENCY_CONFLICT 只冻结协议语义，实际检测由 M0-016 深化
- STALE_INDEX, BUDGET_EXHAUSTED, PERMISSION_DENIED 等只冻结机器语义和可构造性，不实现搜索索引/预算/权限系统
- 遵守“只做 M0-002”指令，禁止顺便开始 M0-003~M0-022

## 测试

- 正式 57 passed (原33 + 新增24)
- Reference 15 passed
- 对抗验证 A-E 均有效，证明测试能捕获破坏

## 审查证据

- reviews/M0/evidence/M0_002_REVIEW_PACKET.md
- reviews/M0/evidence/M0_002_TEST_OUTPUT.txt

## 下一步

等待总工程师 M0-002 CODE REVIEW，签发 FINAL PASS 后才允许进入 M0-003。
