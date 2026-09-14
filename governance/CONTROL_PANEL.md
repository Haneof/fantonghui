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
- M0 完成度：**19 / 22 FINAL PASS**
- 已正式通过到：**M0-019**
- M0-019 语义冻结：`f1dc7cc8ca07131f75d7afe5c505f534c2f3dbe8`
- 下一任务：**M0-020 — 历史世界读取与 Knowledge Cutoff**
- M0-020 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-020（尚未开始） | **M0-019 FINAL PASS**；366 正式测试 + Reference 15 全通过 | 亲自推进 M0-020 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-019 semantic HEAD：Python 3.12.14，366 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-019 已冻结什么

- 世界对象持久化前必须递归验证内部 `ObjectRef / SourceRef`。
- `SQLiteWorldStore.commit()` 不再允许调用者通过 `validate_references=False` 绕过引用完整性。
- pinned 引用必须精确命中那个 object revision。
- floating 引用保持此前冻结的“至少存在一个在 cutoff 前可见版本”的导航语义。
- 引用目标是否可见以引用者自己的 `learned_at` 作为 knowledge cutoff。
- 同一事务里新建对象可以互相引用，只要引用目标在知识时间上并不位于引用者未来。
- 普通语义互引仍然允许，不因为形成 A↔B 就自动判非法。
- 对象引用自己的“当前 revision”必须拒绝，返回 `DEPENDENCY_INVALID`。
- 对象的新 revision 可以引用自己过去的 revision，用于历史/修订链。
- 缺失或尚不可见引用返回 `NOT_FOUND`，事务整体不落盘，不会自动删除坏 ref。

正式审查文件：`reviews/M0/M0-019_final_PASS_2026-09-14.md`

## 五、M0-020 已授权边界

下一轮冻结“历史世界读取 + Knowledge Cutoff”：

- 可以精确读取指定 object revision；
- 可以按 `as_of_world_revision` 读取当时最新状态；
- 可以按 `knowledge_cutoff` 隐藏后来才知道的数据；
- world revision 与 knowledge cutoff 可以组合；
- list 查询也必须在限制条件内为每个对象选择最新可见 revision；
- 知识可见性看 `learned_at`，不能只看 `recorded_at`；
- 未来人生数据即使已经存在数据库里，被测 AI 在过去时间点也必须 0 泄露；
- Worker 后续通过 Core/query 层使用历史世界，不直接 SQL。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
