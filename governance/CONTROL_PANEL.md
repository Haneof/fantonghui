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
| **并行程序员2** | `parallel-02` | 后续第三条并行施工线 |
| **自动测试** | `ci` | GitHub Actions，负责机械测试事实，不负责架构判断 |

## 二、当前项目状态

- 当前里程碑：**M0 最终 Gate**
- M0 完成度：**21 / 22 FINAL PASS**
- 已正式通过到：**M0-021**
- M0-021 语义冻结：`8818dba83d97f73e3e48df97df9a18e3c450ba9d`
- M0-022 总工侧状态：**Gate 材料完成 / CI 全绿 / 等待 GPT-6 架构审计员**
- M0-022 Gate 候选：`95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- M1 状态：**暂停不准开始**
- 并行核心开发：**暂停不准开始**

## 三、当前人员与任务

| 中文职位 | 内部编号 | 当前状态 | 当前任务 | 最近结果 | 下一步 |
|---|---|---|---|---|---|
| **总工程师 / 总工** | `chief-01` | **等待架构审计** | M0-022 Gate | schema snapshot + 四类 fixture + Gate review 已完成；391+15 全绿 | 读取 GPT-6 红队报告后裁决 Gate |
| **核心程序员 / 主程序员** | `core-01` | **待命** | 无 | 无新生产任务 | M0 Gate 后再分配 M1 |
| **GPT-6 架构审计员** | `architect-01` | **已授权 / 必须执行 / 可开始** | M0 独立架构红队 | 尚无 `LATEST.md` 结果 | 独立审查并提交 PASS / ruling / blocker |
| **并行程序员1** | `parallel-01` | **未授权** | 无 | 无 | Gate 后评估 |
| **并行程序员2** | `parallel-02` | **未授权** | 无 | 无 | 后续按冲突面决定 |
| **自动测试** | `ci` | **通过** | M0 Gate 候选回归 | Python 3.12.14，391 passed；Reference 15 passed | 保持 exact-head 机械证据 |

## 四、总工侧 Gate 已完成内容

- 已加入冻结契约 schema/hash snapshot：`schemas/r2/m0_contract_snapshot.json`。
- CI 会重新生成模型 schema hash、枚举和 Task/Event transition map；任何漂移都会失败，必须显式批准 snapshot 变化。
- 已加入四个任务书强制 fixture：运动会、未知人物、未来预测、Goal/Task 分离。
- 从 Gate 前归档 HEAD 到候选 HEAD，仅新增 snapshot 和测试文件，没有修改 production contract/storage/query/service/runtime 代码。
- Gate 候选 `95cec414...` 的 exact-head CI：run `34814629456` / job `103882644741`，正式 **391 passed**，Reference **15 passed**，SUCCESS。
- 第一次 snapshot bootstrap 使用空 `{}` 期望值，故意得到 1 个 mismatch 以捕获规范化输出；该失败已进入正式审查记录，没有隐藏。

正式总工 Gate readiness：`reviews/M0/M0-022_chief_gate_ready_2026-09-14.md`

## 五、为什么现在还不能宣布 M0 完成

M0 Gate 的治理规则要求 **GPT-6 架构审计员独立红队**。它必须把 M0-001~021 的既有 FINAL PASS 当成待验证主张，至少攻击：时间/knowledge cutoff、object/world revision、引用、证据链、反自证、Task/Wake/Action/Outcome、幂等与并发回滚、历史回放、Worker DB 权限边界、状态机、schema snapshot 和 Gate fixture。

要求输出：`ARCHITECTURE PASS | RULING REQUIRED | BLOCKER FOUND`。

在该独立结果出现并由总工处理之前：

- **M0 仍是 21/22 FINAL PASS**；
- **M0-022 不能签 FINAL PASS**；
- **M1 不准开始**；
- **并行核心开发不准启用**。

## 六、操作口令

GPT-6 架构审计员完成后，项目负责人只需说：**“GPT-6架构审计员做完了”**。

总工程师会自行读取云端 `governance/agent_reports/architect-01/LATEST.md`，检查真实报告、代码、CI 和 Gate 证据，然后决定：M0 FINAL PASS、要求 PATCH，或进入架构裁决。
