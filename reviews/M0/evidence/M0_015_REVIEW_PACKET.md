# M0-015 Review Packet — Dependency（依赖）契约

日期：2026-09-14
负责人：总工程师 `chief-01`
前置冻结基线：M0-014 archive HEAD `fc4be9d7405d0afb38ec168839554c8259eef644`
语义候选 HEAD：`3b4e8b603e52830d8be44d33141f722bbba244a0`

## 1. 权威任务边界

M0-015 只冻结显式 Dependency 对象及最小循环/反向查询语义：

- `dependent_ref`
- `dependency_ref`
- `dependency_type`
- 依赖必须能指出“哪个对象的哪个版本”
- 普通语义 Relation 不自动升级为 Dependency
- 显式 Dependency / 证明链不能靠闭环自证
- 能从底层 exact-version ref 反查直接/传递受影响对象

本任务不实现 M3 的持久反向索引、自动 stale 标记、自动复核任务创建或纠错传播运行时。

## 2. Dependency schema 冻结

`contracts/models.py::Dependency` 保留三个核心业务字段，并增加以下约束：

1. `object_type` 精确为 `Literal[ObjectType.DEPENDENCY]`；
2. `dependent_ref` 必须 pinned；
3. `dependency_ref` 必须 pinned；
4. `dependency_type` 保持开放字符串，不能为空或全空白；
5. 同一稳定 `object_id` 不得直接依赖自身，即使引用不同 revision。

没有创建封闭的 dependency_type 枚举，以免在 M0 阶段提前把未来依赖语义固化成有限 ontology。

## 3. 最小图规则

新增 `src/aios_core/dependency/graph.py`：

- `find_dependency_cycle`：只检查显式 Dependency 记录，按 `(object_id, revision)` 建图；
- `validate_dependency_graph_acyclic`：发现显式依赖闭环时拒绝；
- `collect_impacted_dependents`：从一个 exact-version 底层 ref 做确定性的反向直接/传递扫描。

普通 `Relation` 不进入这张图，因此人物/关系网络可以有环，符合任务书“关系图可以有环，证明链不能靠自身闭环提置信度”的边界。

## 4. 必测链路

专项测试覆盖：

- Claim@1 → EvidenceSet@1 → Observation@1；
- Summary@1 → Claim@1；
- Task@1 → Event@1；
- 三节点显式 Dependency 闭环被 cycle guard 拒绝；
- 普通 Relation A↔B 允许存在，不被误判成 Dependency cycle；
- Observation@1 的反向扫描可得到 EvidenceSet@1 → Claim@1 → Summary@1；
- Observation@2 不会误命中只依赖 Observation@1 的对象，证明 reverse lookup 是 revision-sensitive。

## 5. 持久化边界

Dependency 继续使用统一 WorldObject/SQLite append-only 存储，没有新建特殊数据库表。

专项测试把真实 Observation / EvidenceSet / Claim / Summary / Event / Task 与四条 Dependency 同事务持久化，随后从 `ObjectType.DEPENDENCY` payload 重建 Dependency 对象，再执行反向扫描。

同时对 post-validation mutation 做对抗测试：将已经合法构造的 pinned `dependency_ref` 通过低级方式篡改为 floating ref 后提交，统一 durable revalidation 必须返回 `INVALID_ARGUMENT / persistence_revalidation_failed`，且 Dependency 不落库。

## 6. 明确未实现

本任务没有实现：

- M3 persistent reverse index；
- 纠错自动传播；
- 自动将受影响对象标 stale；
- 自动创建复核 Task；
- 自动调整 Claim confidence；
- 对 Relation 普遍禁止环；
- 把所有 ObjectRef 链接机械转换成 Dependency；
- 本地语义判断某条链接是不是“值得记录的依赖”。

## 7. CI

Exact semantic candidate：`3b4e8b603e52830d8be44d33141f722bbba244a0`

GitHub Actions：
- run `34809518146`
- job `103867871731`
- CPython 3.12.14
- pytest 8.4.2
- formal: **329 passed**, 1 条既有 M0-009 对抗 warning
- Reference: **15 passed**
- result: SUCCESS

## 8. 总工审查关注点

- 没有改变 M0-006 Generic ObjectRef 的全局 floating/pinned 语义；只由 Dependency 业务对象收紧为 pinned。
- 没有改变任何既有 FINAL PASS 对象字段。
- 没有把 Relation 图强制变成 DAG。
- 没有提前实现 M3 runtime。
- reverse lookup 基于 exact revision，不会把“同 ID 新版本”悄悄视作原依赖。
- dependency_type 保持开放，避免本地规则假装做语义 ontology 裁决。
