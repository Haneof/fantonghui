# AIOS 2.0 云端总控面板

最后同步：2026-09-14
控制面分支：`governance/aios-control-plane`

## 一、角色

| 中文职位 | 内部编号 | 当前职责 |
|---|---|---|
| 总工程师 / 总工 | `chief-01` | 修复并验收 M0 Gate blocker，最终签 Gate |
| 核心程序员 | `core-01` | 待命 |
| GPT-6 架构审计员 | `architect-01` | 独立复审 blocker patch |
| 并行程序员1/2 | `parallel-01/02` | M0 Gate 前未授权 |
| 自动测试 | `ci` | 机械回归证据 |

## 二、当前项目状态

- 当前里程碑：**M0 最终 Gate**
- 原 Gate 候选：`95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- GPT-6 首轮结论：**BLOCKER FOUND**，报告提交 `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- 当前状态：**Blocker 已由总工程师修补并机械验证，等待 GPT-6 独立复审**
- 当前 patch 候选：`8b3bca9ef3bf8fde2ee09b73a2631a3a2f12db0a`
- exact-head CI：run `34821050459` / job `103902471146`
- 正式测试：**400 passed**；Reference：**15 passed**；结论 SUCCESS
- M1：**暂停不准开始**
- 并行核心开发：**暂停不准开始**

## 三、已处理的三个 blocker

### B1 幂等错误重放

原问题：同一个 idempotency key 即使对应完全不同的 operation、arguments、expected revision、object set，也会直接返回旧结果。

当前修复：key 只允许重放完全相同的 durable commit request fingerprint。任何字段或对象 payload 不一致都返回 `IDEMPOTENCY_CONFLICT`，且不产生世界写入。

### B3 Dependency 持久化环

原问题：cycle helper 存在，但 durable SQLite commit 可绕过 helper 持久化 proof cycle。

当前修复：当 commit 含 Dependency 时，durable write boundary 会把当前 latest Dependency graph 与 pending edges 合并检查；形成环则在写入前 `DEPENDENCY_INVALID` 全事务回滚。Relation 环继续合法。

### B2 Worker DB 隔离

总工正式裁决：M0 是**模块化单体 + trusted reviewed code**，不是同一 Python interpreter 内的恶意代码 sandbox。

准确规则：Worker 生产代码必须只通过 Core 公共接口，不得注入 DB path、sqlite connection 或 storage object。静态 scanner 作为 defense-in-depth，现已额外覆盖 GPT-6 提出的 `__import__('sqlite3')` 和 `importlib.import_module('aios_core.storage')` 反例；但测试不再被表述为“恶意 Python 绝对无法绕过”的安全证明。

## 四、当前人员状态

| 中文职位 | 状态 | 下一步 |
|---|---|---|
| 总工程师 | **等待架构复审** | 读取新 `LATEST.md` 后最终裁决 |
| 核心程序员 | **待命** | Gate 后再派 M1 |
| GPT-6 架构审计员 | **已授权 / 必须复审** | 按 `REREVIEW_REQUEST.md` 独立攻击 B1/B2/B3 |
| 并行程序员1/2 | **未授权** | Gate 后评估 |
| 自动测试 | **通过** | 400+15 exact-head 证据已获得 |

## 五、正式材料

- GPT-6 原 blocker 报告：`governance/agent_reports/architect-01/LATEST.md`
- 总工 blocker 修复裁决：`reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`
- GPT-6 复审请求：`governance/agent_reports/architect-01/REREVIEW_REQUEST.md`

在 GPT-6 复审转为可接受 Gate verdict 前，**M0 不签 FINAL PASS、M1 不开始、并行核心开发不启用**。
