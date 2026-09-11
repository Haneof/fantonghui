# AIOS 文档入口

> **当前唯一有效架构：AIOS Constitution V1.4-r1**。
>
> 旧 Constitution、旧 Core、旧 Runtime 文档已经从当前分支删除，不再作为历史代码入口或设计依据。

## 开发者唯一阅读顺序

1. `docs/AIOS_Constitution_V1.4-r1.md` — 唯一有效宪法
2. `docs/05_AI_RUNTIME.md` — AI Cognitive Runtime
3. `docs/06_REPOSITORY_LAYOUT.md` — 当前仓库结构
4. `docs/07_DEVELOPMENT_PLAN.md` — 架构开发计划
5. `docs/08_ACCEPTANCE_TESTS.md` — 验收标准
6. `AIOS_DEVELOPMENT_TASKS.md` — **唯一实时任务状态表**
7. `AIOS_PROJECT_EXECUTION_MASTER_V1.0.md` — 工程治理规则

## 唯一产品 OS 主线

```text
aios/01_os/
```

所有新的 OS Runtime、Schema、Simulator、Tests 必须进入这条主线。

## 当前规范主链

```text
Observation
  → Global Timeline
  → Dynamic Dimension Curves
  → Trigger
  → AI Session
  → Identity Bootstrap
  → Autonomous Context Construction
  → Cognitive Runtime
  → Help / Decision / Action / Silence
  → Outcome
  → Cognitive Delta
  → AI Self Update
  → Persistent Cognition / Session Handoff
```

## 核心硬规则

- AI Instance 接入 AIOS 后，**第一步必须建立自己的身份**。
- Identity Bootstrap 之后，AIOS **不得规定固定 Dimension 阅读顺序**。
- Dimension 是 Global Timeline 上的动态观察视角/时间曲线，不是静态字段或标签表。
- User / World Dimensions 与 AI Dimensions 共用唯一 Global Timeline，并行演化。
- Observation / Evidence / Cognition / Hypothesis / Prediction / Outcome 必须保持可区分和可追溯。
- Local Runtime 不替 AI 做复杂语义判断。
- UI 不拥有独立 AI、Memory、Timeline、Trigger 或 Cognition。
- Simulator 的 Expected Intent 对被测 AI 隐藏。
- 每次代码变更必须更新 `AIOS_DEVELOPMENT_TASKS.md` 并提供测试/验收证据。
