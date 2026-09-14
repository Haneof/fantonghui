# AIOS 2.0 云端总控面板

这个文件是给项目负责人看的中文总面板。

原则：人看中文职位名，机器保留稳定编号。

最后同步：2026-09-14
控制面分支：`governance/aios-control-plane`

## 一、中文职位名对照表

| 你平时叫法 | 系统内部编号 | 是谁 / 干什么 |
|---|---|---|
| **总工程师 / 总工** | `chief-01` | 负责架构、关键任务亲自实现、审代码、签 FINAL PASS、发下一任务 |
| **核心程序员 / 主程序员** | `core-01` | 日常按总工命令写代码、补测试、提交施工结果 |
| **GPT-6 架构审计员 / GPT-6 首席架构师** | `architect-01` | 重大架构争议、冻结契约变更或里程碑 Gate 的独立红队 |
| **并行程序员1** | `parallel-01` | 以后允许多 AI 并行开发时的第二条施工线 |
| **并行程序员2** | `parallel-02` | 以后需要第三条并行施工线时启用 |
| **自动测试** | `ci` | GitHub Actions，负责机械测试事实，不负责架构判断 |

## 二、当前项目状态

- 当前里程碑：M0 — 进行中
- M0 完成度：**17 / 22 FINAL PASS**
- 已正式通过到：**M0-017**
- M0-017 验收冻结：`c9bd2d85ff0047515f6f4cc5b9e7058c70cff6dc`
- 下一任务：**M0-018 — 全局 World Revision 与原子提交**
- M0-018 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-018（尚未开始） | **M0-017 FINAL PASS**；353 正式测试 + Reference 15 全通过 | 亲自推进 M0-018 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-017 acceptance HEAD：Python 3.12.14，353 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-017 已冻结什么

- 第一阶段 SQLite 世界存储正式冻结五张核心表：`world_meta / world_commits / object_revisions / operations / idempotency_records`。
- Store connection 使用 WAL 和 foreign keys。
- 对象 revision 追加保存，不覆盖旧历史。
- 重启后 world revision、对象 payload 和历史 revision 都保留。
- 一个多对象事务成功后，所有对象共享同一 world revision。
- 非法事务失败后，world/object/operation/idempotency 都不会留下半写状态。
- 两个 writer 拿同一个旧 world revision 写入时，后提交者必须收到 `VERSION_CONFLICT`，不能覆盖先提交者。
- AI Worker 继续被架构测试禁止直接 import `sqlite3` 或 `aios_core.storage`。
- 没有引入运行时随意 `ALTER TABLE`；未来 migration 必须走显式版本化方案。

正式审查文件：`reviews/M0/M0-017_final_PASS_2026-09-14.md`

## 五、M0-018 已授权边界

下一轮专门冻结“全局 World Revision + 原子提交”语义：

- 事务开始时检查 `expected_world_revision`；
- 一个成功事务只生成一个新的全局 world revision；
- 同一事务里的所有对象共享这个 world revision；
- 只有事务完整成功后 world meta 才推进；
- stale writer 必须返回 `VERSION_CONFLICT`；
- 任意验证/写入失败都必须 rollback，不能推进 world revision，也不能留下部分对象；
- 继续保持 append-only 历史与既有幂等顺序；
- 使用现有 `BEGIN IMMEDIATE` 事务边界；
- 不提前实现后续调度/恢复运行时。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
