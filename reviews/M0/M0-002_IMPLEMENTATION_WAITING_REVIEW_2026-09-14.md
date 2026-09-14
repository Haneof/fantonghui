# M0-002 实现记录

状态：

R1 PATCH COMPLETE / WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

统一错误码、协议级错误结构与机器可恢复异常契约

起始commit：

8197c4f943c8e06f87bf25f18d79aceef982e196 (M0-001 FINAL PASS)

R1起始commit：

b59cc719c0af8e0c40a7480179b8e94240198be9 (M0-002 初版)

## 实现了什么

### M0-002 初版 (b59cc71)
1. 新建 src/aios_core/contracts/errors.py: ErrorResponse
2. 新建 src/aios_core/errors.py: AIOSProtocolError
3. 修改 src/aios_core/contracts/__init__.py: 导出 ErrorResponse
4. 修改 src/aios_core/storage/sqlite_store.py: StoreError 继承 AIOSProtocolError + 结构化 context
5. 新建 tests/unit/test_errors.py 24 tests (E01-E20)
6. README 增加 M0-002 错误协议说明

### M0-002-R1 补丁 (本轮)
1. 修改 src/aios_core/contracts/errors.py: 增加 allow_inf_nan=False, 拒绝 NaN/Infinity
2. 修改 src/aios_core/errors.py:
   - 构造即通过 ErrorResponse 验证 (唯一验证源)
   - 内部保存 model_copy(deep=True)
   - context getter 返回 deepcopy
   - to_response 返回 deep copy 稳定
   - 解决原始dict污染、getter污染、to_response不稳定
3. 补充 tests/unit/test_errors.py 新增15 tests:
   - P01-P09 协议不变量
   - S01-S03 Store context回归
   - 清理重复 test_e04
4. 更新 TASK_PROGRESS_R2.md, docs/DEV_LOG.md, reviews

## 哪些没有实现

- 未新增 ErrorCode, 未修改字符串值
- 未实现完整 idempotency conflict detection (M0-016)
- 未实现完整 Action Runtime (仅最小模拟)
- 未实现 HTTP mapping / API
- 未实现完整 logging (仅 exception chaining)
- 未修改 reference (15 passed)
- 未修改 schema/事务/idempotency算法

## 为什么没有越界

- 只修总工明确3个阻塞问题 + 补充测试
- 未扩大范围到 ErrorCode集合、SQLite schema、事务、world revision、reference validation、Action Runtime、HTTP、Dependency engine、M0-003

## 测试

- 正式 72 passed (原57 + 新增15: P01-P09 S01-S03)
- Reference 15 passed
- 对抗验证 R1 A-E 均有效

## 审查证据

- reviews/M0/M0-002_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_002_REVIEW_PACKET.md (更新 R1)
- reviews/M0/evidence/M0_002_TEST_OUTPUT.txt (更新)
- reviews/M0/evidence/M0_002_R1_TEST_OUTPUT.txt (新增, 如有)

## 下一步

等待总工程师 M0-002 FINAL CODE REVIEW。
