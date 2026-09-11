# AIOS Core —— 开始构建说明

## 当前唯一有效架构依据

**AIOS Constitution V1.4-r1** 是当前 AIOS 唯一有效 Constitution。

V1.4-r0 为上一补丁版本；V1.3-r0、V1.2-r1 及更早版本仅作为历史资料保留，不得作为新代码、新 Runtime、新任务的架构依据。

当前 V1.4-r1 重点补齐：

- Identity First：AI Instance 接入后必须先认识自己是谁。
- Autonomous Cognition：除 Identity Bootstrap 外，不规定固定 Dimension 读取路线。
- 两组并行长期认知：User / World Dimensions + AI Dimensions，共享 Global Timeline。
- Cognitive Runtime：Session、Context Construction、Continuation、Persistence。
- Cognitive Delta：记录一次 Session 真正发生的认知变化。
- Session Handoff：让下一个 AI Instance 无需从零重读历史即可继续。
- Cognitive Optimization：通过隐藏 Expected Intent + Simulator + Structured Telemetry + Regression 优化认知机制。

## 实际开发依据

1. `AIOS_Constitution_V1.4-r1.md` —— 当前唯一有效宪法。
2. `01_CORE_ARCHITECTURE.md` —— AIOS 底座分层。
3. `02_RUNTIME_CONTRACTS.md` —— Runtime 输入、输出、边界和接口。
4. `03_WORLD_EVENT_SCHEMA.md` —— 世界事件与认知对象格式。
5. `04_WAKE_RUNTIME.md` —— 机械唤醒与上下文进入机制。
6. `05_AI_RUNTIME.md` —— AI 如何进入世界、建立身份并保持认知连续性。
7. `06_REPOSITORY_LAYOUT.md` —— 代码仓库结构。
8. `07_DEVELOPMENT_PLAN.md` —— 开发顺序。
9. `08_ACCEPTANCE_TESTS.md` —— 阶段验收。
10. `09_FIRST_SPRINT_TASKS.md` —— 当前 Sprint 任务。
11. `AIOS_PROJECT_MASTER_PROMPT_V1.0.md` —— 项目主控 Prompt。

## 先做什么

第一阶段不要做手环硬件，不要先做完整 UI，不要先做领域 App。

先在 Windows/Linux PC 上做 `AIOS Core Simulator`，跑通：

```text
Reality / Observation
    → Global Timeline
    → Dimensions
    → Trigger
    → Identity Bootstrap
    → Autonomous AI Cognition
    → Capability / Action / Silence
    → Outcome
    → Cognitive Delta
    → Persistent Update / Handoff
```

## 一个最重要的工程结论

AIOS 不让低层模型替 AI 做复杂世界理解，也不让 Runtime 把 AI 的思维过程硬编码成固定 Dimension 顺序。

低层负责：

- 原始输入接入
- Observation
- 清洗 / 归一化
- 确定性机械检测
- Global Timeline
- Trigger

AI Runtime 负责：

- Identity Bootstrap
- 自主选择相关 World / User / AI Dimensions
- Evidence 查询
- 跨时间 / 跨维度 / 跨关系推理
- 用户意图理解
- 帮助 / 决策 / 行动 / 沉默
- Cognitive Delta
- Session Handoff

Simulator 负责：

- Hidden Expected Intent
- Structured Cognitive Trace / Telemetry
- Failure Diagnosis
- Mechanism Optimization
- Regression

**最终目标不是让 AIOS “记住更多”，而是让 AI 越来越懂这个人，并且能像一个真正有连续人格和关系的 AI 一样，在正确的时候提供真正有价值的帮助。**
