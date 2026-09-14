# M0 Gate Blocker Resolution — chief-01

日期：2026-09-14  
状态：**PATCH IN REVIEW / M0 仍未通过**

## 1. 背景

独立架构审计 `architect-01` 在治理提交 `c6b0191797ab3ef06b4ee031003431a0d9527d48` 给出 `BLOCKER FOUND`。

总工程师接受三个问题：

- B1：相同 idempotency key 可把不同请求错误重放为旧成功结果；
- B2：AI Worker 的 raw-SQLite 隔离被历史文档表述成了比实际实现更强的安全边界；
- B3：Dependency cycle helper 没有接入 durable persistence boundary。

M0-022 不得在这些问题修复并复审前签 FINAL PASS。

## 2. B1 裁决与修复语义

M0-016 重新打开。

冻结候选语义：一个 idempotency key 只能重放**完全相同的 durable commit request**。

请求身份包括：

- operation_id
- session_id
- operation_name
- normalized arguments
- expected_world_revision
- reason
- idempotency_key
- intended object_id / revision 集合
- 每个对象的 canonical serialized payload

对象输入顺序不属于语义身份。

若 key 已存在：

- fingerprint 完全相同：在 stale-world 检查前返回原 CommitResult，`idempotent_replay=True`；
- fingerprint 不同：返回 `IDEMPOTENCY_CONFLICT`，不得写入任何对象、world revision、operation 或 idempotency side effect。

为了兼容 M0 已有数据库且不引入 runtime ALTER TABLE，本补丁不增加重复 fingerprint 列；它从同一原子事务已经持久化的 `operations` 行以及该 operation 对应 world revision 的 `object_revisions` 重建原始请求 fingerprint。这样旧数据库和新数据库具有同一校验语义。

## 3. B3 裁决与修复语义

M0-015 重新打开。

Dependency 不再依赖调用者“记得先调用 helper”才能保证 proof graph 无环。

当一次 commit 含 Dependency 时，SQLite durable write boundary 会：

1. 读取当前每个 Dependency 对象的 latest durable revision；
2. 用本事务 pending Dependency revision 覆盖同 object_id 的当前 revision；
3. 对 resulting current Dependency graph 执行 exact-version cycle validation；
4. 若存在闭环，返回 `DEPENDENCY_INVALID`，reason=`dependency_cycle`，整个事务回滚。

Relation graph 仍然可以成环；该规则只作用于显式 Dependency graph。

本补丁仍不实现 M3 persistent reverse index、自动 correction propagation 或 stale propagation。

## 4. B2 威胁模型正式裁决

M0 第一阶段继续采用任务书已经冻结的**模块化单体 + trusted reviewed code**模型，不把同一 Python interpreter 描述成恶意代码安全沙箱。

因此：

- “AI Worker 不能直接访问 SQLite/storage”在 M0 的准确含义是**架构依赖规则与代码审查约束**；
- M0 不声称 hostile Python 在同一进程内技术上不可能 dynamic-import sqlite3/storage；
- Worker 必须通过 Core 公共接口访问世界；正常生产代码不得接收 DB path、`sqlite3.Connection` 或 `SQLiteWorldStore` capability；
- 在真实 Worker world-I/O/runtime 启用前，必须重新 Gate capability wiring；若未来威胁模型升级为不受信任代码，则必须采用独立进程/服务或等价的真正 capability boundary。

作为 defense-in-depth，架构 scanner 已新增对常规 import、`__import__('sqlite3')`、`importlib.import_module('aios_core.storage')` 等常量字符串动态导入的检测。但这些测试**不是 sandbox 证明**。

任何历史 review/governance 中“Worker 在同一解释器内绝对无法取得 raw connection”的更强措辞，由本裁决收窄并取代。

## 5. 新增对抗回归

当前 patch 增加：

- same key + different operation identity -> IDEMPOTENCY_CONFLICT；
- same key + altered arguments -> IDEMPOTENCY_CONFLICT；
- same key + altered object payload -> IDEMPOTENCY_CONFLICT；
- exact replay survives restart；
- concurrent same-key different requests：仅一个成功，另一个 IDEMPOTENCY_CONFLICT；
- same-transaction Dependency cycle durable rejection；
- cycle split across commits durable rejection；
- architect 提出的两个 dynamic-import counterexample scanner regression。

## 6. 当前状态

本文件不是 FINAL PASS。

必须等待：

1. patch exact-head 全量 CI；
2. 总工程师独立 diff/CI 核验；
3. M0 Gate snapshot/fixture 全量继续通过；
4. `architect-01` 针对 B1/B2/B3 进行独立复审并转为 `ARCHITECTURE PASS`，或给出新的 ruling/blocker。

在此之前：M0 保持 21/22；M1 与并行核心开发继续暂停。
