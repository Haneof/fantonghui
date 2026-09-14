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
- M0 完成度：**12 / 22 FINAL PASS**
- 已正式通过到：**M0-012**
- M0-012 语义冻结：`5ab6ed1c21f2c3f2664104faff3494113bdd5bc1`
- 下一任务：**M0-013 — Goal（目标）一等对象**
- M0-013 状态：**已授权 / 总工程师负责 / 尚未开始**
- 当前生产分支：`arena/01a09bc6-fantonghui`
- 当前开发模式：核心生产代码仍为单写入者

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | 当前负责人 | M0-013（尚未开始） | **M0-012 FINAL PASS**；284 正式测试 + Reference 15 全通过 | 亲自推进 M0-013 |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | M0-010 收尾已验收 | 等总工以后分配施工任务 |
| **GPT-6 架构审计员** | `architect-01` | **待命** | 当前无任务 | 尚未触发架构升级 | M0 Gate 必须介入；当前无需启动 |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 等总工宣布可并行 |
| **自动测试** | `ci` | **通过** | 每次 core push 自动回归 | M0-012 semantic HEAD：Python 3.12.14，284 passed；Reference 15 passed | 后续 push 自动重跑 |

## 四、M0-012 已冻结什么

- EventAnchor 是对多维世界的认知解释/锚点，不是底层 Observation 本身。
- 生命周期支持 CANDIDATE / ACTIVE / RESOLVED / REVISED / REJECTED / MERGED / SPLIT。
- 候选事件可低置信度创建，不要求 confidence=1。
- Claim、EvidenceSet、修订/合并/拆分历史依据使用 pinned revision。
- 保留既有 `evidence_set_refs`，并明确增加 support/counter EvidenceSet 引用。
- REVISED、REJECTED、MERGED、SPLIT 保留 revision_reason；修订/合并/拆分保持明确历史指向。
- “学校运动会 → 校内田径测试”案例证明旧判断和修正原因均可历史回放，不能通过改标题抹掉过去。
- Event 不复制原始 Observation payload。
- 构造后篡改 provenance 仍由 M0-009 durable persistence revalidation 拦截。

正式审查文件：`reviews/M0/M0-012_final_PASS_2026-09-14.md`

## 五、沟通与权限

用户只需说“继续下一任务”或某个角色“做完了”。总工程师自行读取真实分支、报告、diff、源码、review 与 CI。

- 施工 AI 不能自己宣布 FINAL PASS。
- 总工程师负责最终验收、冻结 commit、授权下一任务。
- GPT-6 架构审计员在 M0 Gate 必须介入；当前无升级触发。
- 自动测试全绿是必要条件，不替代架构审查。
