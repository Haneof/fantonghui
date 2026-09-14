# M0 Gate — B6 / B7 / B5 / R4 总工程师修复裁决

日期：2026-09-14  
角色：`chief-01`  
状态：**PATCH GREEN / WAITING INDEPENDENT ARCHITECT RE-REVIEW — NOT FINAL PASS**

## 1. 输入与正式结论

独立 `architect-01` 第二轮正式复审更新于治理分支：

- report commit: `c068fc1fa0de528ab17cbfc4a4c6f9112b3ae164`
- verdict: `BLOCKER FOUND`
- audited candidate: `268d403836b107a1969a9a5d8b85e4955baec9bf`

总工程师独立复核后接受以下问题：

- B6：幂等 request fingerprint 在未规范化重试对象与规范化 durable payload 之间不一致；
- B7：`OperationRequest` assignment validation 失败后可能留下脏实例，而 durable commit 未重新验证；
- B5-a：`sqlite3.connect()` 位于异常协议映射边界之外；
- B5-b：内部 storage/schema 故障错误地归类为 `INVALID_ARGUMENT`；
- R4：EvidenceSet 的冻结 `knowledge_cutoff` 与其显式成员可见性可以自相矛盾。

本轮同时接受 architect 对窄范围 B2/B3/B4 的关闭判断，以及 R3 的 M1/M2 future Gate 判断；这不构成整个 M0 Gate 通过。

## 2. Chief 架构裁决

### 2.1 B6 — canonical durable request identity

幂等 identity 必须使用**与实际持久化完全相同的规范化表示**。

因此：

- WorldObject fingerprint 前先执行与 durable persistence 相同的 Pydantic round-trip revalidation；
- OperationRequest fingerprint 同样使用重新验证后的快照；
- exact retry 仍然必须发生在 stale `expected_world_revision` 检查之前；
- 同 key 的有效 altered request 仍返回 `IDEMPOTENCY_CONFLICT`；
- 已成功且可被规范化的同一请求，在 restart 后必须 exact replay，不能因为原 Python 实例内部表示不同而冲突。

### 2.2 B7 — OperationRequest durable boundary

`OperationRequest` 是 durable audit identity 的一部分，不能信任构造后的 live Pydantic 实例状态。

新写入路径冻结顺序为：

1. existing-key replay / idempotency conflict；
2. reused operation-id conflict；
3. expected world revision；
4. **OperationRequest persistence revalidation**；
5. WorldObject persistence revalidation；
6. revision/type/reference/dependency validation；
7. durable writes。

这样保持 stale exact replay 的既有优先级，同时防止 failed assignment 后的脏 request 落库。

### 2.3 B5-a / B5-b — storage protocol

重新打开 M0-002 与 M0-017。

新增正式错误码：

`STORAGE_FAILURE`

语义：调用方通过修改业务请求通常无法修复的数据库/存储内部故障。

冻结分类：

- SQLite busy/locked：`VERSION_CONFLICT`, `reason=storage_busy`，调用方从新 snapshot 重试；
- connect/unavailable：`STORAGE_FAILURE`, `reason=storage_unavailable`；
- SQLite integrity internal failure：`STORAGE_FAILURE`, `reason=sqlite_integrity_error`；
- non-lock OperationalError：`STORAGE_FAILURE`, `reason=sqlite_operational_error`；
- other SQLite DatabaseError：`STORAGE_FAILURE`, `reason=sqlite_database_error`。

`sqlite3.connect()` 本身必须在 capability/error mapping boundary 内；raw SQLite exception 不作为 Core 公共协议。

这不是把所有数据库故障声明为可自动恢复；M2 runtime retry policy 仍必须按 code/reason 明确决定 retry / stop / escalate。

### 2.4 R4 — EvidenceSet frozen cutoff

重新打开 M0-009 与 M0-019。

最小 M0 invariant：EvidenceSet 中所有正式 typed refs，包括递归收集到的：

- `member_refs`
- `support_refs`
- `counter_refs`
- `context_refs`
- selector 内正式 `ObjectRef`

都必须在 `EvidenceSet.knowledge_window.knowledge_cutoff` 时可见。

不能再用 EvidenceSet 自身更宽的 `learned_at` 作为这些 evidence refs 的知识可见性 cutoff。

本轮**不**把完整 `knowledge_window.world_revision` 材料化/冻结语义提前到 M0：

- same-transaction member 如果 `learned_at <= knowledge_cutoff` 仍可合法引用；
- selector materialization、真实 world snapshot 固定、coverage/roles 的完整 service consistency 继续由 M1-006 Gate 强制。

### 2.5 recorded_at 所有权

Chief 选择 architect 的方案 B：

- `recorded_at` = AIOS / simulator 世界时间轴中的记录时刻，由受控 ingestion/import/simulator 提供；
- `world_commits.committed_at` = 实际 SQLite durable commit 的物理时刻。

M0 不修改字段结构。M1 ingestion Gate 必须限制普通生产调用方任意伪造 knowledge/recording time；模拟器和导入路径必须保留明确 provenance。

## 3. 生产修复

核心语义 repair commit：

`f38fdd2aa64e31b92c5353206a8aef62c9322087`

主要修改：

- `src/aios_core/contracts/enums.py`
- `src/aios_core/storage/idempotency.py`
- `src/aios_core/storage/sqlite_store.py`
- `tests/unit/test_errors.py`
- `tests/unit/test_world_revision_atomicity.py`
- 新增 `tests/unit/test_m0_gate_third_followup.py`

新增对抗覆盖 13 个场景，包括：

- coercible nested mutation 的 restart exact replay；
- dirty OperationRequest identity/reason/session 等字段零落库；
- connect failure 不泄漏 raw SQLite；
- internal schema failure 归类 STORAGE_FAILURE；
- EvidenceSet member/support/counter/context cutoff 反例；
- same-transaction、cutoff 内 evidence member 仍合法。

## 4. Schema snapshot

因为 M0-002 正式新增 `STORAGE_FAILURE`，M0 contract snapshot 必须显式变化。

第一次 repair CI：

- run `34827058782`
- job `103921528459`
- formal functional behavior：**417 passed**
- 唯一失败：`test_m0_schema_snapshot_matches_frozen_contract`
- 原因：snapshot 仍冻结旧 10 ErrorCode / 旧 ErrorResponse schema hash
- Reference 因 formal failure 未运行

该失败被保留为正式证据；不是隐藏或删除测试。

新生成结构确认只有预期结构变化：

- `ErrorCode` 新增 `STORAGE_FAILURE`
- `ErrorResponse` JSON-schema hash 更新为 `2ea9a6af49db3192361124253bd811c1352a001ec682808c7a4e4779767014a9`
- 其它 model / Task/Event transition contract 不应变化。

随后按本轮 Chief 明确批准的 M0-002 contract change 更新 snapshot。

当前 exact green candidate：

`9c080f693917c2c99bfbe6aa924e5f3cb54744a0`

## 5. Exact-head CI

Latest exact-head CI：

- run `34827250470`
- job `103922130589`
- checkout `9c080f693917c2c99bfbe6aa924e5f3cb54744a0`
- Ubuntu 24.04.5
- CPython 3.12.14
- pytest 8.4.2
- formal: **418 passed, 1 known warning in 3.84s**
- Reference: **15 passed in 0.24s**
- conclusion: **SUCCESS**

唯一 warning 仍为既有 M0-009 adversarial Pydantic serializer warning，不是本轮新增失败。

## 6. 当前冻结状态

等待 GPT-6 复审期间：

- M0-002：REOPENED / PATCHED / WAITING ARCHITECT
- M0-009：REOPENED / PATCHED / WAITING ARCHITECT
- M0-016：REOPENED / PATCHED / WAITING ARCHITECT
- M0-017：REOPENED / PATCHED / WAITING ARCHITECT
- M0-019：REOPENED / PATCHED / WAITING ARCHITECT
- M0-022：BLOCKED / PATCH CANDIDATE GREEN / WAITING ARCHITECT

B3 / M0-015 已由最新 architect re-review 独立验证其窄修复成立，可恢复原 FINAL PASS；这不代表 correction propagation / M3 reverse-index 已实现。

## 7. Gate 结论

**NOT FINAL PASS.**

机械修复与 CI 证据已完成，但本轮涉及：

- 第三轮幂等核心机制修正；
- 冻结 ErrorCode 协议扩展；
- EvidenceSet frozen-cutoff 基础语义变更；
- storage error boundary。

按治理政策，必须再次由 `architect-01` 独立攻击最新 candidate。

在 `architect-01` 给出可接受 verdict 且 `chief-01` 独立签 Gate 前：

- M0 不恢复 22/22 FINAL PASS；
- M1 不开始；
- 并行核心开发不启用。
