# AIOS 2.0 云端总控面板

最后同步：2026-09-14
控制面分支：`governance/aios-control-plane`

## 一、角色

| 中文职位 | 内部编号 | 当前职责 |
|---|---|---|
| 总工程师 / 总工 | `chief-01` | 验收最新 M0 Gate blocker patch，最终签 Gate |
| 核心程序员 | `core-01` | 待命 |
| GPT-6 架构审计员 | `architect-01` | 独立复审最新 `9c080f...` candidate |
| 并行程序员1/2 | `parallel-01/02` | M0 Gate 前未授权 |
| 自动测试 | `ci` | 机械回归证据 |

## 二、当前项目状态

- 当前里程碑：**M0 最终 Gate**
- 原 Gate candidate：`95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- 最新 architect re-review：**BLOCKER FOUND**，报告提交 `c068fc1fa0de528ab17cbfc4a4c6f9112b3ae164`
- 最新 semantic repair：`f38fdd2aa64e31b92c5353206a8aef62c9322087`
- 当前 exact green candidate：`9c080f693917c2c99bfbe6aa924e5f3cb54744a0`
- exact-head CI：run `34827250470` / job `103922130589`
- 正式测试：**418 passed**；Reference：**15 passed**；SUCCESS
- M1：**暂停不准开始**
- 并行核心开发：**暂停不准开始**

## 三、本轮处理结果

### B6 幂等规范化

fingerprint 与 durable persistence 现在共享同一规范化 Pydantic representation。可 coercion 的 post-construction mutation 如果首次写入被接受并规范化，restart 后同一请求必须 exact replay，而不是错误冲突。

### B7 OperationRequest durable validation

新写入在 replay/conflict 与 expected-world 检查之后、任何 durable insert 之前重新验证 `OperationRequest`。assignment validation 抛错后留下的脏 live instance 不得写入 audit/world commit。

### B5 storage protocol

M0-002/M0-017 重新打开并新增：

`ErrorCode.STORAGE_FAILURE`

- busy/lock：`VERSION_CONFLICT / storage_busy`
- connect unavailable：`STORAGE_FAILURE / storage_unavailable`
- internal SQLite integrity/operational/database failure：`STORAGE_FAILURE` + machine-readable reason
- connect/setup 生命周期已纳入异常边界

### R4 EvidenceSet frozen cutoff

EvidenceSet 的 typed refs 改为以它自己的 `knowledge_window.knowledge_cutoff` 做 durable visibility validation。不能把 cutoff 之后才 learned 的节点冻结进一个声称更早截止的证据集合。

完整 `world_revision` materialization/selector freeze 继续由 M1-006 实现，不把整个 Evidence service 偷渡进 M0。

### recorded_at

`recorded_at` 定义为受控 AIOS/simulator 记录时刻；`world_commits.committed_at` 才是物理 DB durable commit time。M1 ingestion 必须执行生产调用方的时间/provenance 约束。

## 四、CI 证据

本轮第一次 repair CI `34827058782`：**417 passed / 1 failed**。唯一失败是 M0 schema snapshot 正确检测到本轮批准的 `STORAGE_FAILURE` 协议扩展；功能/对抗测试全部通过。这个 failure 被保留。

更新冻结 snapshot 后，latest candidate `9c080f...`：

- run `34827250470`
- job `103922130589`
- CPython 3.12.14
- formal **418 passed**, 1 条既有 adversarial warning
- Reference **15 passed**
- SUCCESS

## 五、当前 M0 重新打开项

- M0-002 — PATCHED / WAITING ARCHITECT
- M0-009 — PATCHED / WAITING ARCHITECT
- M0-016 — PATCHED / WAITING ARCHITECT
- M0-017 — PATCHED / WAITING ARCHITECT
- M0-019 — PATCHED / WAITING ARCHITECT
- M0-022 — BLOCKED / LATEST PATCH GREEN

M0-015 的 B3 durable-cycle 修复已被最新 architect re-review 独立验证，可恢复其 bounded M0 FINAL PASS；不代表 M3 correction propagation 已实现。

## 六、当前人员状态

| 中文职位 | 状态 | 下一步 |
|---|---|---|
| 总工程师 | **等待架构复审** | 读取新 `LATEST.md` 后最终裁决 |
| 核心程序员 | **待命** | Gate 后再派 M1 |
| GPT-6 架构审计员 | **已授权 / 必须复审** | 攻击 B6/B7/B5/R4、新 STORAGE_FAILURE、验证全局回归 |
| 并行程序员1/2 | **未授权** | Gate 后评估 |
| 自动测试 | **通过** | 418+15 exact-head 证据 |

## 七、正式材料

- 最新 architect blocker report：`governance/agent_reports/architect-01/LATEST.md`
- Chief 最新裁决：`reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md`
- architect 最新复审请求：`governance/agent_reports/architect-01/REREVIEW_REQUEST.md`

在 GPT-6 对 `9c080f...` 给出可接受 Gate verdict 且 chief-01 最终签字前，**M0 不签 FINAL PASS、M1 不开始、并行核心开发不启用**。
