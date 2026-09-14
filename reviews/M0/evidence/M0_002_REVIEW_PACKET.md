# M0-002 审查证据包

## 任务
统一错误码、协议级错误结构与机器可恢复异常契约

## 起始commit
8197c4f943c8e06f87bf25f18d79aceef982e196 (M0-001 FINAL PASS)

## 结束commit
待提交 (M0-002 实现)

## 修改文件
- src/aios_core/contracts/errors.py (新增)
- src/aios_core/errors.py (新增)
- src/aios_core/contracts/__init__.py (导出 ErrorResponse)
- src/aios_core/storage/sqlite_store.py (StoreError 继承 AIOSProtocolError + 结构化 context)
- tests/unit/test_errors.py (新增 24 tests)
- README.md (增加 M0-002 错误协议说明)
- TASK_PROGRESS_R2.md (M0-002 IN PROGRESS -> CODE COMPLETE)
- docs/DEV_LOG.md (追加 M0-002 日志)

## ErrorCode集合
冻结10个，不得新增：
- INVALID_ARGUMENT
- NOT_FOUND
- VERSION_CONFLICT
- INCOMPLETE_DATA
- STALE_INDEX
- BUDGET_EXHAUSTED
- PERMISSION_DENIED
- DEPENDENCY_INVALID
- OUTCOME_UNKNOWN
- IDEMPOTENCY_CONFLICT

值保持大写字符串，StrEnum。

## ErrorResponse schema
```python
class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: ErrorCode
    message: Annotated[str, Field(min_length=1)]
    context: dict[str, JsonValue] = Field(default_factory=dict)
```
约束：
- code 必须是 ErrorCode
- message 不允许空字符串
- context 默认 {}
- context 必须 JSON 序列化 (JsonValue: str/int/float/bool/None/list/dict)
- extra 字段禁止
- response 不得包含 traceback
- 不得自动暴露内部 exception repr

可 model_dump(mode="json")。

## AIOSProtocolError行为
```python
class AIOSProtocolError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, context: dict[str, JsonValue] | None = None)
    @property
    def code: ErrorCode
    @property
    def message: str
    @property
    def context: dict[str, JsonValue]
    def to_response() -> ErrorResponse
    def __str__() -> str: return message
```
- 统一 Core 内部已知、可分类失败
- to_response() 返回 ErrorResponse
- str() 返回 message 方便日志，但业务禁止依赖 str
- 可通过 `raise ... from original` 保留 __cause__ 用于内部日志
- ErrorResponse 只输出 code/message/context，不包含 cause/traceback

## StoreError迁移
- 原继承：RuntimeError
- 新继承：AIOSProtocolError
- 保持 except StoreError 仍然有效
- 也可 except AIOSProtocolError 统一捕获
- 构造函数新增 context 参数：`StoreError(code, message, *, context=None)`

## Store context迁移 (逐项)
- A. 空commit: INVALID_ARGUMENT, context {operation_id, reason="empty_commit"}
- B. world revision冲突: VERSION_CONFLICT, context {expected_world_revision, current_world_revision, operation_id}
- C. object revision冲突: VERSION_CONFLICT, context {object_id, expected_revision, actual_revision}
- D. 当前对象引用自己当前revision: DEPENDENCY_INVALID, context {object_id, revision}
- E. 引用不存在: NOT_FOUND, context {referenced_object_id, referenced_revision} (revision None => null)
- F. read object not found: NOT_FOUND, context {object_id, revision}
- G. operation not found: NOT_FOUND, context {operation_id}
- 额外: duplicate revision: INVALID_ARGUMENT, context {operation_id, reason="duplicate_revision"}
- 未修改 schema/事务顺序/world revision递增/append-only/idempotency算法/reference validation规则

## OUTCOME_UNKNOWN
- 语义：真实结果未知，非 FAILED。例如 Action 向外部提交消息后超时，不知是否已发出，不能安全自动重试。
- 测试方式：模拟 Action boundary 捕获 TimeoutError 显式转换为 AIOSProtocolError(ErrorCode.OUTCOME_UNKNOWN, ..., context={action_id, cause="timeout"})
- 验证 code == OUTCOME_UNKNOWN，context 含 action_id
- 未创建正式 Action 执行器，仅最小模拟

## Message独立性
- 业务分类示例：
```python
def classify(error: ErrorResponse):
    if error.code == ErrorCode.VERSION_CONFLICT:
        return "retry_after_refresh"
    ...
```
- 给完全不同 message "文本A" vs "完全重写后的文本B"，只要 code 相同，结果必须相同
- 测试 test_message_independence_classify 验证
- 日志使用 message 合法，禁止依赖 message 内容决定业务逻辑

## 安全序列化
- 内部先产生 ValueError("internal sensitive diagnostic")
- 然后显式构建 AIOSProtocolError(INVALID_ARGUMENT, "invalid request", context={"field": "x"}) 并保留 __cause__
- 序列化 ErrorResponse 后输出不含 "internal sensitive diagnostic", "ValueError", "traceback"
- 内部 __cause__ 保留用于诊断，不进入协议序列化

## 正式测试
- Python版本：3.11.2 (正式基线 >=3.12, 总工独立验证 3.13.5)
- 原有 33 passed (6 boundary + 12 regression + 15 unit)
- 新增 24 passed (test_errors.py)
- 总计 57 passed, 0 failed
- Reference 15 passed

## 新增测试数量和概括
24 tests:
- E01 所有10个 ErrorCode 可构造
- E02 model_dump(mode="json")
- E03 未知 ErrorCode 拒绝
- E04 空 message 拒绝
- E05 额外字段拒绝
- E06 非JSON context 拒绝
- E07 ProtocolError properties
- E08 to_response() 相同语义
- E09 StoreError 是 AIOSProtocolError 子类
- E10 StoreError 可被 except StoreError 捕获
- E11 StoreError 可被 except AIOSProtocolError 统一捕获
- E12 world revision conflict context
- E13 object revision conflict context
- E14 NOT_FOUND 读取对象 context
- E15 不存在引用 context (含 null 处理)
- E16 OUTCOME_UNKNOWN 模拟 timeout
- E17 OUTCOME_UNKNOWN 不被改为 FAILED
- E18 NOT_FOUND vs INCOMPLETE_DATA 不同
- E19 VERSION_CONFLICT vs IDEMPOTENCY_CONFLICT 不同
- E20 不包含 traceback
- message独立性 classify 测试
- 安全序列化不泄露
- 其他错误码可构造性 (STALE_INDEX等)
- operation not found context

## 对抗性验证
- A: 让 ErrorResponse 接受额外字段 -> 额外字段被接受，证明原 extra=forbid 测试有效，原实现拒绝额外字段 PASS
- B: StoreError 改回 RuntimeError -> 不是 AIOSProtocolError 子类，继承测试失败，攻击有效
- C: 删除 VERSION_CONFLICT context -> context 缺少 expected_world_revision，结构化测试失败，攻击有效
- D: OUTCOME_UNKNOWN 改成 INVALID_ARGUMENT -> code 不是 OUTCOME_UNKNOWN，测试失败，攻击有效
- E: 业务按 message 含 "revision" 分支 -> 重写 message 后分类不一致，暴露问题，证明需按 code 分支，攻击有效，正确实现按 code 分类 PASS

## 已知限制
- 完整 idempotency conflict detection 由 M0-016 完成，本轮只冻结协议语义
- 完整 Action Runtime 由后续任务完成，本轮仅最小模拟 OUTCOME_UNKNOWN
- HTTP mapping 由后续接口层完成
- 完整 logging infrastructure 由后续阶段完成，本轮通过 exception chaining 保留 __cause__
- 未新增 ErrorCode (INTERNAL等)，如需新码写入架构建议，不擅自添加

## Python版本
- 正式基线 >=3.12
- 本地 3.11.2 PYTHON_312_RUNTIME_UNAVAILABLE
- 总工独立验证 3.13.5

## git status
clean after commit

## 未修改 reference
- aios_core_r2_reference/ 保持冻结，15 tests 通过
- 正式 src 合法超越 reference (错误协议)

---

## R1 PATCH

### 问题
- AIOSProtocolError构造时未验证context, 依赖类型标注无运行时保证, object()可先成功创建到 to_response()才失败
- context内部状态可被外部污染: 原始dict修改、err.context getter修改可污染内部
- 严格JSON数值: NaN/Infinity/-Infinity 不是标准JSON, 需显式拒绝

### 修复
- ErrorResponse: ConfigDict allow_inf_nan=False
- AIOSProtocolError: 构造即 validated = ErrorResponse(...), 非法立即失败; 内部保存 model_copy(deep=True); context getter 返回 deepcopy; to_response 返回 deep copy
- 保证原始dict隔离、getter隔离、to_response稳定

### 新测试 (15新增)
- P01 构造拒绝 object() 立即失败
- P02 构造拒绝 open 立即失败
- P03 ErrorResponse拒绝 NaN
- P04 ErrorResponse拒绝 Infinity/-Infinity (parametrize)
- P05 AIOSProtocolError拒绝 NaN/Infinity
- P06 合法协议 json.dumps(allow_nan=False) 成功
- P07 原始context隔离: ctx修改不污染 err.context
- P08 getter隔离: returned dict修改不污染内部
- P09 to_response稳定: 外部修改后仍得原始内容
- S01 empty commit context {operation_id, reason="empty_commit"}
- S02 duplicate revision context {operation_id, reason="duplicate_revision"}
- S03 self-current reference context {object_id, revision}
- 清理重复 test_e04_empty_message_rejected

### 测试结果
- 正式 72 passed (57 + 15新增)
- Reference 15 passed
- Python 3.11.2 (正式 >=3.12, PYTHON_312_RUNTIME_UNAVAILABLE)

### 对抗验证 R1
- A 删除构造验证 -> P01/P02/P05失败, 攻击有效
- B 直接返回内部dict -> P08/P09失败, 攻击有效
- C 删除 allow_inf_nan=False -> NaN/Infinity测试失败 (LooseResponse 允许 nan), 攻击有效
- D 删除 empty_commit context -> S01失败, 攻击有效
- E 删除 self-current context -> S03失败, 攻击有效

### Commit
- R1待提交
