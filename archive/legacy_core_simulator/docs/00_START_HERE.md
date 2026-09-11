# AIOS Core v0.1 —— 开始构建说明

## 你现在到底需要什么

《AIOS 宪法 V1.3-r0》是当前新架构迁移依据；V1.2-r1 保留为历史版本，不删除。代码尚未全部迁移的部分必须登记为缺口，不得伪称符合新架构。

从今天开始，实际开发以本套文件为准：

1. `01_CORE_ARCHITECTURE.md` —— AIOS 真正底座怎么分层、各系统干什么。

2. `02_RUNTIME_CONTRACTS.md` —— 每个底层运行时的输入、输出、边界和接口。

3. `03_WORLD_EVENT_SCHEMA.md` —— Event / Entity / State / Memory / Cognition / Decision 等统一数据格式。

4. `04_WAKE_RUNTIME.md` —— 最关键：怎样避免让大模型逐条过滤一天几万条信息。

5. `05_AI_RUNTIME.md` —— AI 怎样“进入世界”，而不是收到一条孤立 Prompt。

6. `06_REPOSITORY_LAYOUT.md` —— 第一版代码仓库应该长什么样。

7. `07_DEVELOPMENT_PLAN.md` —— 从 PC Simulator 到手机、手环的开发顺序。

8. `08_ACCEPTANCE_TESTS.md` —— 每阶段用什么测试证明底座真的跑通。

9. `09_FIRST_SPRINT_TASKS.md` —— 当前 Sprint 的具体开发任务。

10. `AIOS_PROJECT_MASTER_PROMPT_V1.0.md` —— 项目主控 Prompt：角色、权限、任务格式与验收纪律。

规范文档总数为 12 份：Constitution + Master Prompt + 00~09。

## 先做什么

第一阶段不要做手环硬件，不要先做完整 UI，不要先做领域 App。

先在 Windows/Linux PC 上做 `AIOS Core Simulator`，跑通：

Reality/Event -> World -> State -> Relevance/Attention -> Wake -> AI -> Capability -> Outcome -> Evolution -> World Update

## 版本关系

Constitution V1.2-r1 = WHY / 原则

Core Architecture V0.1 = WHAT / 底座组成

Runtime Contracts V0.1 = HOW / 系统接口

Development Plan V0.1 = WHEN / 开发顺序

Implementation = 代码

## 一个最重要的工程结论

AIOS 不再让一个 0.5B~2B LLM 负责“每条信息要不要叫醒大模型”。

低层：DSP / 规则 / 专用模型负责把原始输入变成语义事件。

中层：World Runtime + Event Fusion + State Change + Relevance + Attention 负责判断世界有没有发生值得关注的变化。

上层：Wake Runtime 只决定“是否值得让 AI 回来看一眼”。

大模型只在被唤醒后进入 AIOS World，读取自己的 Cognitive World，再进行真正理解、推理、决策、行动和反思。
