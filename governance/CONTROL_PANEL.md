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
| **并行程序员1** | `parallel-01` | M0 Gate 后允许多 AI 并行开发时的第二条施工线 |
| **并行程序员2** | `parallel-02` | 以后需要第三条并行施工线时启用 |
| **自动测试** | `ci` | GitHub Actions，负责机械测试事实，不负责架构判断 |

## 二、当前项目状态

- 当前里程碑：M0 — Gate 前最后一步
- M0 完成度：**21 / 22 FINAL PASS**
- 已正式通过到：**M0-021**
- M0-021 语义冻结：`8818dba83d97f73e3e48df97df9a18e3c450ba9d`
- 下一任务：**M0-022 — M0 契约总测试与冻结快照 / M0 Gate**
- M0-022 状态：**已授权 / 总工程师 Gate / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者；M0 Gate 通过前不启用并行核心开发

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | **Gate 负责人** | M0-022 | **M0-021 FINAL PASS**；385 正式测试 + Reference 15 全通过 | 做总测试、schema snapshot、fixtures、Gate 总审 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | Gate 后再分配 M1 施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **已授权 / Gate 必须介入** | M0 独立架构红队 | 尚未开始 | 独立审查 M0 冻结契约，出具 PASS / ruling / blocker |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | M0 Gate 通过后评估启用 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 后续按冲突面决定 |
| **自动测试** | `ci` | **通过** | 每次 production push 自动回归 | M0-021 semantic HEAD：Python 3.12.14，385 passed；Reference 15 passed | M0-022 继续作为机械证据 |

## 四、M0-021 已冻结什么

- Task 合法状态转换矩阵已经显式写入代码并完整枚举测试。
- Event 合法状态转换矩阵已经显式写入代码并完整枚举测试。
- `RUNNING -> WAITING_RESULT` 合法；`COMPLETED -> RUNNING` 非法。
- `CANDIDATE -> REJECTED` 合法；`MERGED -> ACTIVE` 非法。
- Task 的 `COMPLETED/FAILED/EXPIRED/CANCELLED` 都是终态。
- Event 的 `MERGED/SPLIT` 是终态。
- 对外 transition view 返回 immutable `frozenset`，调用者不能运行时篡改冻结矩阵。
- 状态变化校验要求同一个 object_id 且正好 `revision + 1`，把状态变化表达成 append-only 新 revision。

正式审查文件：`reviews/M0/M0-021_final_PASS_2026-09-14.md`

## 五、M0-022 Gate 已授权边界

M0 最后一项不是普通小任务，而是正式里程碑 Gate：

- 全量回归 M0-001~021 的 schema、枚举、时间、引用、revision、world revision、幂等、knowledge cutoff、Task/Event 状态机；
- 导出 Pydantic JSON Schema 或稳定结构 hash 进入仓库，作为以后契约变化检测基准；
- 至少覆盖运动会、未知人物、未来预测、Goal/Task 分离四个 Gate fixture；
- 生成 M0 Gate report；
- CI 全绿只是必要条件，不等于 M0 FINAL PASS；
- **GPT-6 架构审计员必须独立红队审查**，通过后总工程师才能签 M0 Gate；
- Gate 前不进入 M1，也不启用并行核心开发。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员本轮已经进入强制 Gate 流程。
- 自动测试全绿是必要条件，不替代架构审查。
