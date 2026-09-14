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
- M0 完成度：**15 / 22 FINAL PASS**
- 已正式通过到：**M0-015**
- M0-015 语义冻结：`3b4e8b603e52830d8be44d33141f722bbba244a0`
- 下一任务：**M0-016 — OperationRequest、审计与幂等契约**
- M0-016 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-016（尚未开始） | **M0-015 FINAL PASS**；329 正式测试 + Reference 15 全通过 | 亲自推进 M0-016 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-015 semantic HEAD：Python 3.12.14，329 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-015 已冻结什么

- Dependency 成为显式、带版本的依赖边：`dependent_ref -> dependency_ref`。
- 两端必须钉住具体 revision；不能用 floating latest 作为历史依赖依据。
- `dependency_type` 保持开放字符串，不提前发明封闭依赖类型表。
- 直接自依赖被拒绝；多节点显式 Dependency 闭环可由 cycle guard 检测并拒绝。
- 普通 Relation 网络不是 Dependency 图，因此人物/关系网络仍然可以有环。
- 从底层 exact-version 对象可以反查直接和传递受影响对象。
- 反查严格区分 revision；依赖 Observation@1 不等于依赖 Observation@2。
- Dependency 可以使用统一 SQLite WorldObject 存储，重建后继续反查。
- M3 才实现持久 reverse index、自动 stale、自动复核任务和纠错传播运行时。

正式审查文件：`reviews/M0/M0-015_final_PASS_2026-09-14.md`

## 五、M0-016 已授权边界

下一轮冻结世界修改操作包与安全重试规则：

- operation_id
- session_id
- operation_name / arguments
- expected_world_revision
- reason
- idempotency_key
- 相同 idempotency key 重试不得重复写入
- stale expected world revision 必须明确冲突
- 已提交操作必须可审计

本轮不提前做外部 Action 的分布式幂等或复杂事务编排。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
