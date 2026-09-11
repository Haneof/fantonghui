# AIOS PROJECT EXECUTION MASTER V1.0

> AIOS 项目总工程执行准则 / PM 自我约束文件
> 状态：ACTIVE
> 唯一开发分支：`aios`
> 唯一 OS 产品主线：`aios/01_os/`
> 唯一有效宪法：`docs/AIOS_Constitution_V1.4-r1.md`
> 唯一实时任务表：`AIOS_DEVELOPMENT_TASKS.md`

---

# 0. 权威关系

```text
AIOS Constitution V1.4-r1
        ↓
Runtime / Data Model / Acceptance
        ↓
AIOS_DEVELOPMENT_TASKS.md
        ↓
Git + Tests + Runtime Evidence
        ↓
Current Code
```

Git 历史只用于审计，不用于恢复已经废弃的架构。

---

# 1. 唯一产品主线

```text
aios/01_os/
```

禁止创建第二套 OS Runtime。

已废弃的旧 `core/`、旧 Constitution、旧架构入口已经删除。不得恢复后继续开发。

---

# 2. V1.4-r1 唯一主链

```text
Observation
 ↓
Global Timeline
 ↓
Dynamic Dimension Curves
 ↓
Trigger
 ↓
AI Session
 ↓
Identity Bootstrap
 ↓
Autonomous Context Construction
 ↓
Cognitive Runtime
 ↓
Help / Decision / Action / Silence
 ↓
Outcome
 ↓
Cognitive Delta
 ↓
AI Self Update
 ↓
Persistent Cognition / Session Handoff
```

## 关键约束

- Observation 是底层证据入口，不是 AI 结论。
- Global Timeline 是唯一时间基准。
- Dimension 是 Timeline 上的动态观察视角/曲线，不是静态字段。
- User / World Dimensions 与 AI Dimensions 并行共享 Timeline。
- Identity First 是唯一强制的认知入口。
- Identity 之后不得写死 Dimension 阅读顺序。
- Runtime 提供查询、权限、上下文容量、连续性和持久化能力，但不规定模型具体思维路线。
- Source Confidence、Evidence Confidence、Claim Confidence 必须区分。
- Prediction 必须可通过 Outcome 验证并更新置信度。

---

# 3. 开发治理

每个任务必须遵循：

```text
读取任务表
 ↓
读取当前宪法
 ↓
检查真实代码
 ↓
只实现当前任务
 ↓
测试 / 验收
 ↓
更新 AIOS_DEVELOPMENT_TASKS.md
 ↓
Commit 到 aios
```

### 禁止

- 根据聊天历史猜任务状态。
- 把计划写成已完成。
- 用一个大 Prompt 代替 Runtime 机制。
- 把 Dimension 做成固定分类表。
- 把 LLM Context 当长期记忆。
- 把 Expected Intent 暴露给被测 AI。
- 为了通过单个场景而硬编码答案。

---

# 4. 当前执行入口

当前唯一下一任务由 `AIOS_DEVELOPMENT_TASKS.md` 的 `当前执行任务` 决定。

完成一个任务后，必须修改任务表并记录：变更文件、测试结果、Commit SHA、下一任务。
