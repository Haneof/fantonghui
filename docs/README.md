# AIOS 文档入口

> 当前唯一有效架构：**AIOS V1.4-r2**。
> 当前唯一开发分支：`aios`。
> 当前唯一 OS 主线：`aios/01_os/`。

## 开发者阅读顺序

1. `docs/AIOS_Constitution_V1.4-r2.md` — 唯一有效宪法
2. `docs/AIOS_Architecture_V1.4-r2.md` — 完整 OS 架构
3. `docs/05_AI_RUNTIME.md` — AI 服务与认知运行时
4. `docs/06_REPOSITORY_LAYOUT.md` — 仓库结构
5. `docs/07_DEVELOPMENT_PLAN.md` — 开发计划
6. `docs/08_ACCEPTANCE_TESTS.md` — 验收标准
7. `AIOS_DEVELOPMENT_TASKS.md` — 唯一实时任务状态表
8. `AIOS_PROJECT_EXECUTION_MASTER_V1.0.md` — 工程治理规则

## 唯一 OS 主线

```text
aios/01_os/
```

## 完整系统结构

```text
系统基础
 ↓
现实接入
 ↓
观察 / 世界运行时
 ↓
核心认知
 ↓
触发 / MODE
 ↓
AI 服务
 ↓
能力系统
 ↓
AI 能力应用
 ↓
人机交互
```

安全系统贯穿全链路；AI 模型接入属于 AI 服务的模型供应层；模拟器、评估和回归属于测试与演进系统。

## 核心认知主链

```text
Observation
 → Evidence / Provenance
 → Global Timeline
 → User / World Dimensions + AI Dimensions
 → Trigger / MODE
 → AI Session
 → Identity Bootstrap
 → Autonomous Context Construction
 → Cognitive Runtime
 → Help / Decision / Action / Silence
 → Outcome
 → Cognitive Delta
 → AI Self Update
 → Persistent Cognition / Handoff
```

## 关键硬规则

- AI Instance 接入 AIOS 后第一步必须建立身份。
- Identity 之后不得规定固定 Dimension 阅读顺序。
- Dimension 是时间轴上的动态观察视角，不是静态字段。
- User / World Dimensions 与 AI Dimensions 共用唯一 Global Timeline。
- AI 服务统一承载用户主动和 AI 主动，不拆成两个大脑。
- 能力系统是 AI 与现实世界之间的统一执行接口。
- AI 能力应用是轻量、AI 原生的专业领域，不复制传统手机应用。
- 应用不得建立第二套用户记忆、人格或关系系统。
- UI 不拥有独立 AI、Memory、Timeline、Trigger 或 Cognition。
- 模型可替换，AIOS 身份与长期认知不可随模型丢失。
- 安全系统拥有高于普通 AI 帮助的保护边界。
- Simulator 的 Expected Intent 对被测 AI 隐藏。
- 先在 PC/Linux 完整实现软件，再接手机和手环。
- 每次代码、Schema、Runtime Contract、架构文档或测试变更必须同步更新 `AIOS_DEVELOPMENT_TASKS.md`。
