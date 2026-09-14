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
- M0 完成度：**16 / 22 FINAL PASS**
- 已正式通过到：**M0-016**
- M0-016 语义冻结：`cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3`
- 下一任务：**M0-017 — SQLite 追加式世界存储 schema**
- M0-017 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-017（尚未开始） | **M0-016 FINAL PASS**；341 正式测试 + Reference 15 全通过 | 亲自推进 M0-017 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-016 semantic HEAD：Python 3.12.14，341 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-016 已冻结什么

- 所有世界修改操作继续显式携带 `operation_id / session_id / operation_name / arguments / expected_world_revision / reason / idempotency_key`。
- 关键 operation identity、reason 和 idempotency key 不允许空白。
- 同一成功操作的幂等重试先于 expected world revision 冲突检查。
- 因此重复重试返回第一次的结果，不会让 world revision 再加一次，也不会重复写对象。
- 新 idempotency key 如果拿着旧 `expected_world_revision` 写入，必须返回 `VERSION_CONFLICT`。
- 系统不能自动吞掉冲突后覆盖另一个 writer 的结果。
- 已提交操作可以通过 durable operation audit 回查，SQLiteWorldStore 重启后仍然存在。
- 新增 `OperationAuditRecord`，让审计记录拥有明确类型化契约。

正式审查文件：`reviews/M0/M0-016_final_PASS_2026-09-14.md`

## 五、M0-017 已授权边界

下一轮正式验收 SQLite 世界存储本身，而不是只依赖前面任务顺手使用它。

重点包括：
- `world_meta / world_commits / object_revisions / operations / idempotency_records`；
- WAL；
- `BEGIN IMMEDIATE` 等事务边界；
- object_id/type/subject/learned_at 索引；
- 建库和重启后数据仍然正确；
- 连续多次提交；
- 同一对象多个 revision 永久保留；
- 失败事务完整 rollback，不能留下半写状态；
- expected world revision 的并发冲突行为；
- AI Worker 不得拿到 raw sqlite connection；
- migration 以后必须走显式版本脚本，禁止运行时随意 ALTER。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
