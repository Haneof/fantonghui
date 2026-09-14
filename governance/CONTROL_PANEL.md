# AIOS 2.0 云端总控面板

最后同步：2026-09-14
控制面分支：`governance/aios-control-plane`

## 一、角色

| 中文职位 | 内部编号 | 当前职责 |
|---|---|---|
| 总工程师 / 总工 | `chief-01` | 修复并验收 M0 Gate blocker，最终签 Gate |
| 核心程序员 | `core-01` | 待命 |
| GPT-6 架构审计员 | `architect-01` | 独立复审最新 Gate patch |
| 并行程序员1/2 | `parallel-01/02` | M0 Gate 前未授权 |
| 自动测试 | `ci` | 机械回归证据 |

## 二、当前项目状态

- 当前里程碑：**M0 最终 Gate**
- 原 Gate 候选：`95cec4142bdd9a87011bbad197e05ec1d27aeb57`
- GPT-6 首轮结论：**BLOCKER FOUND**，治理报告提交 `c6b0191797ab3ef06b4ee031003431a0d9527d48`
- 额外独立红队线：`arena/01a09edf-fantonghui` @ `42f19a3f39a1e4ac375ac315d6dcf8f487725830`，新增 B4/B5/R3 意见
- 当前状态：**B1~B5 已修补/裁决并机械验证，等待 GPT-6 对最新候选独立复审**
- B4/B5 语义 patch：`a99326c5034118b3a497e3be0d53ac9466445467`
- 当前 exact green candidate：`268d403836b107a1969a9a5d8b85e4955baec9bf`
- 生产进度归档：`83577317e96224f9cdb271a8a835a4e48f3aa78c`
- exact-head CI：run `34823226166` / job `103909332923`
- 正式测试：**405 passed**；Reference：**15 passed**；结论 SUCCESS
- M1：**暂停不准开始**
- 并行核心开发：**暂停不准开始**

## 三、当前 Gate 处理结果

### B1 幂等错误重放

同一个 idempotency key 只有完整 durable commit request fingerprint 一致才允许 replay；operation/session/name/arguments/expected revision/reason/object set/revision/payload 任一不一致都返回 `IDEMPOTENCY_CONFLICT` 且零 mutation。

### B2 Worker DB 隔离

M0 威胁模型已正式收窄为**模块化单体 + trusted reviewed code**，不是 hostile-Python sandbox。Worker 只能使用 Core 公共接口，生产 wiring 不得注入 DB path、sqlite connection 或 storage object。静态 scanner 是 defense-in-depth，不作为 sandbox 证明。

### B3 Dependency 持久化环

当 commit 包含 Dependency 时，SQLite durable boundary 会用 latest durable Dependency graph + pending edges 做整体判环；形成环则 `DEPENDENCY_INVALID`，Relation 环仍合法。

### B4 Floating self-reference

新增独立红队发现：`ObjectRef(X, revision=None)` / `SourceRef(X, revision=None)` 可解析到当前 pending self，语义等价于当前 revision 自证。

当前修复：same stable object 的 floating/current self-reference 均在 durable reference-validation boundary 被 `DEPENDENCY_INVALID` 拒绝；历史 pinned self-link（如 `X@2 -> X@1`）继续合法。

### B5 SQLite 协议边界

- operation_id 已提交后换新 key 再写，显式返回 `IDEMPOTENCY_CONFLICT`；
- SQLite busy/lock 映射成 `VERSION_CONFLICT` / `reason=storage_busy`，并配置显式 busy timeout；
- raw sqlite integrity/operational exception 不作为 Core 公共协议响应。

### R3 双透镜裁决

M0-020 的底层 store API 保留 world revision 与 knowledge cutoff 的独立能力，不强行改写冻结接口。但以后：

- M1 面向 AI Worker/Console/App 的“当时 AI 知道什么”公共查询，必须同时绑定 resolved world snapshot revision + knowledge cutoff；
- M2 Session executor 的所有 world reads 必须绑定 `Session.snapshot_world_revision` + session knowledge-cutoff 语义；
- Worker 不得获得 raw store-read capability。

这些是未来里程碑强制 Gate，不是可选建议。

## 四、CI 证据

B4/B5 patch 后第一次归档 CI `34822952167` 得到 **404 passed / 1 failed**：唯一失败是旧 M0-018 测试仍期待 raw `sqlite3.IntegrityError`，而新的协议边界已正确转换成 `StoreError`；5 个新增 B4/B5 对抗测试全部已通过。该失败未隐藏。

随后只修正测试的过时异常期待，不改变 rollback 语义。最新候选 `268d403...` 的 CI `34823226166`：

- CPython 3.12.14
- formal **405 passed**, 1 条已知 adversarial warning
- Reference **15 passed**
- SUCCESS

## 五、当前人员状态

| 中文职位 | 状态 | 下一步 |
|---|---|---|
| 总工程师 | **等待最新架构复审** | 读取新 `LATEST.md` 后最终裁决 |
| 核心程序员 | **待命** | Gate 后再派 M1 |
| GPT-6 架构审计员 | **已授权 / 必须复审** | 按更新后的 `REREVIEW_REQUEST.md` 独立攻击 B1/B2/B3/B4/B5 与 R3 |
| 并行程序员1/2 | **未授权** | Gate 后评估 |
| 自动测试 | **通过** | 405+15 exact-head 证据已获得 |

## 六、正式材料

- GPT-6 原 blocker 报告：`governance/agent_reports/architect-01/LATEST.md`
- 第一轮总工修复裁决：`reviews/M0/M0_gate_blocker_resolution_2026-09-14.md`
- B4/B5/R3 总工裁决：`reviews/M0/M0_gate_followup_B4_B5_R3_2026-09-14.md`
- GPT-6 最新复审请求：`governance/agent_reports/architect-01/REREVIEW_REQUEST.md`

在 GPT-6 对最新候选给出可接受 Gate verdict 前，**M0 不签 FINAL PASS、M1 不开始、并行核心开发不启用**。
