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
- M0 完成度：**20 / 22 FINAL PASS**
- 已正式通过到：**M0-020**
- M0-020 语义冻结：`426ea4c8e1292f0dd5f57e01f8663014071f7004`
- 下一任务：**M0-021 — Task / Event 状态机冻结**
- M0-021 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-021（尚未开始） | **M0-020 FINAL PASS**；377 正式测试 + Reference 15 全通过 | 亲自推进 M0-021 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-020 semantic HEAD：Python 3.12.14，377 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-020 已冻结什么

- 支持精确 object revision 历史读取。
- 支持 `as_of_world_revision` 重建当时世界状态。
- 支持 `knowledge_cutoff` 按 `learned_at` 隐藏后来才知道的数据。
- world revision 与 knowledge cutoff 可以组合，按交集选择最新可见 revision。
- 数据库中已经存在的未来 revision 在过去时间镜头下不会泄露。
- 历史 list 先选每个对象的最新可见 revision，再应用 `subject_id` 等可变字段筛选，避免旧 revision 被错误复活。
- `HistoricalWorldQuery` 会固定实际使用的 world revision，并把实际 snapshot revision 与最小 coverage 返回给调用方。
- 明确证明 `recorded_at` 不能替代 `learned_at` 做知识可见性。

正式审查文件：`reviews/M0/M0-020_final_PASS_2026-09-14.md`

## 五、M0-021 已授权边界

下一轮冻结 Task / Event 状态机：

- Task 的合法状态转换矩阵进入代码；
- Event 的合法状态转换矩阵进入代码；
- `RUNNING -> WAITING_RESULT` 必须合法；
- `COMPLETED -> RUNNING` 必须拒绝；
- `CANDIDATE -> REJECTED` 必须合法；
- `MERGED -> ACTIVE` 必须拒绝；
- 状态变化通过新的对象 revision 表达，不允许 durable state 原地 UPDATE；
- 服务层不能绕过状态机随意写状态。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
