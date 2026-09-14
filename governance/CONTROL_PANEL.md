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
- M0 完成度：**14 / 22 FINAL PASS**
- 已正式通过到：**M0-014**
- M0-014 语义冻结：`af49c27c95527ca1d2b28cddd88115b0264b48c4`
- 下一任务：**M0-015 — Dependency（依赖）契约**
- M0-015 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-015（尚未开始） | **M0-014 FINAL PASS**；315 正式测试 + Reference 15 全通过 | 亲自推进 M0-015 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-014 semantic HEAD：Python 3.12.14，315 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-014 已冻结什么

- Task / Wake / Session / Action / Outcome 已成为五类持久的一等对象。
- 未来工作必须进入 Task；不能靠模型上下文“记住以后再做”。
- Task 的 reason/execution/outcome 历史引用使用 pinned revision；Goal/dependency/entity 导航链接不被本任务强制成历史 provenance。
- Wake 独立保存来源、命中次数、证据、优先级和去重信息；Wake evidence 使用 pinned revision。
- Session 保存 originating Wake、世界快照、operation IDs 与 checkpoint，为中断恢复提供持久基础。
- Action 使用稳定 execution_id；Action 与 Outcome 明确分离。
- Outcome 可以继续是 unknown；Action 已完成并不自动代表现实结果成功。
- “提醒已送达”只能证明通知动作/通知 Task 的结果，不能证明用户已经学习、接受帮助或目标改善。
- M0-009 持久化边界重验证继续保护这些 provenance 字段，构造后篡改也不能写入。
- 本轮没有提前实现 M2 调度器。

正式审查文件：`reviews/M0/M0-014_final_PASS_2026-09-14.md`

## 五、M0-015 已授权边界

Dependency 的目标是明确记录“谁依赖谁的哪个版本”，为未来纠错传播和反向查询建立可审计基础。

本轮重点：
- `dependent_ref / dependency_ref / dependency_type`；
- 依赖必须能保留精确版本；
- 普通关系/语义链接不能全部偷换成 Dependency；
- Claim→EvidenceSet→Observation、Summary→Claim、Task→Event 等链可追溯；
- 证明链不能通过自我循环给自己增加可信度；
- M3 才建设完整反向索引与纠错传播运行时。

## 六、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
