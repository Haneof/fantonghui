# M0 Gate Follow-up — B4 / B5 / R3 — chief-01

日期：2026-09-14  
状态：**PATCH IN REVIEW / M0 仍未通过**

## 1. 新的独立红队输入

总工程师在扫查其它 arena 分支时发现另一条独立 `architect-01` 审计线：

- branch: `arena/01a09edf-fantonghui`
- report commit: `42f19a3f39a1e4ac375ac315d6dcf8f487725830`
- verdict: `BLOCKER FOUND`

该报告独立复现了此前 B1，并新增：

- B4：floating self-reference 可以绕过 M0-019 的当前 revision 自证据拒绝；
- B5：raw SQLite `IntegrityError` / `OperationalError` 可能越过协议边界；
- R3：单独使用 world-revision 或裸 revision 查询并不能自动形成 knowledge-cutoff 隔离，未来服务必须绑定双透镜。

## 2. B4 裁决与修复

M0-019 重新打开到本 Gate patch 复审完成。

冻结候选语义：

- 同一 durable object 不得通过 pinned current revision 引用自己；
- 同一 durable object 也不得通过 floating ref (`revision=None`) 引用自己，因为 floating 在当前事务中可解析到 pending/current self，语义等价于当前 revision 自证；
- 指向自身**历史 pinned revision**继续合法，例如 `X@2 -> X@1`，用于显式历史溯源，不视为当前自证。

实现位置：`SQLiteWorldStore.commit()` 的统一引用持久化边界。

拒绝结果：

- `ErrorCode.DEPENDENCY_INVALID`
- `context.reason = self_reference`

新增对抗测试覆盖 ObjectRef floating self-reference、SourceRef floating self-reference、以及历史 pinned self-link 继续合法。

## 3. B5 协议边界加固

B5 不单独驱动原 Gate verdict，但总工程师裁定本轮一并修复，避免 raw SQLite 细节泄漏到 Core 调用方。

### 3.1 operation_id 重用

如果一个已提交 `operation_id` 使用新的 idempotency key 再次提交，不再依赖 SQLite UNIQUE constraint 产生 raw `IntegrityError`。

现在显式返回：

- `ErrorCode.IDEMPOTENCY_CONFLICT`
- `context.reason = operation_id_reused`
- 零世界写入。

### 3.2 SQLite busy / lock

SQLite connection 现在显式配置 `busy_timeout`；锁/忙错误通过 Core 协议映射为：

- `ErrorCode.VERSION_CONFLICT`
- `context.reason = storage_busy`

调用方应从新 snapshot 重试，而不是依赖 SQLite 错误字符串。

其它 SQLite integrity/operational failures 也在 storage capability boundary 内转为 `StoreError`，不直接暴露 raw sqlite exception 作为公共协议。

这不是分布式并发协调器；M1+ 仍需要真实压力测试与运行时 retry policy。

## 4. R3 — 历史读取双透镜正式裁决

总工程师接受第二红队对 P6 的机制判断，但裁定其为 **future service binding Gate**，不是 M0-020 当前存储机制 blocker。

理由：M0-020 已冻结底层独立能力：`as_of_world_revision` 与 `knowledge_cutoff` 可独立或组合使用；任务书也明确后续由 query service 包装。不能为了未来服务纪律把底层 store API 强行改成只有一种查询模式。

从现在冻结以下未来 Gate：

1. **M1 public world/query service**：任何面向 AI Worker、Console 或上层 App 的“当时 AI 知道什么”查询必须同时绑定 resolved world snapshot revision 与 knowledge cutoff；不得把裸 `SQLiteWorldStore.get_payload/list_payloads` 暴露成 Worker public world-read API。
2. **M2 Session executor**：每个 Session 的所有 world reads 必须绑定 `Session.snapshot_world_revision`，并绑定该 session 的知识截止语义；世界后续写入不得扩大同一 session 的可见世界。
3. **Worker capability rule**：Worker 不得获得 raw store read capability；它只能通过上述 Core query surface 读取世界。

因此：

- 单透镜 store read 仍可用于内部维护、调试、显式历史工具；
- 单透镜 read 不得被描述成“过去 AI 可见世界”的完整安全查询；
- M1/M2 若未实现上述绑定，不得通过对应里程碑 Gate。

## 5. 本轮 patch candidate

语义 patch：

`a99326c5034118b3a497e3be0d53ac9466445467`

包含：

- B4 floating self-reference durable rejection；
- B5 operation_id reuse protocol mapping；
- B5 SQLite busy/lock protocol mapping + explicit busy timeout；
- 5 个新的 follow-up 对抗测试。

本文件不是 FINAL PASS。必须等待当前 patch 的 exact archive-head CI 全绿，并再次交给 `architect-01` 独立复审。

## 6. Gate 状态

M0 仍未通过；M1 与并行核心开发继续暂停。

第二轮 architect re-review 必须同时覆盖 B1/B2/B3/B4/B5 与 R3 ruling，不得只复审旧的 B1/B2/B3 request。
