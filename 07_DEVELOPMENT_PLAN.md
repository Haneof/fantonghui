# AIOS Core Development Plan V0.1

## Phase 0 —— 文档冻结

目标：把架构边界定死。

任务：

1. Constitution V1.2-r1 原样保存。

2. 建立本套 Core Architecture 文档。

3. 建立统一 Schema。

4. 建立 Acceptance Tests。

完成标准：所有开发任务都能指出“违反/遵循哪个架构边界”。

## Phase 1 —— Event + World

目标：先造“世界”。

任务：

1. Event Store

2. Entity Store

3. World State

4. Time/Space

5. World Change

6. Event Fusion

验收：模拟用户一天活动，World State 随事件变化，且能回放。

## Phase 2 —— Memory

任务：

1. RAW semantic event log

2. hourly/daily/weekly/monthly summaries

3. time index

4. entity index

5. domain/topic index

验收：能从“去年某月某日”钻取到具体事件；事实与摘要可追溯。

## Phase 3 —— Relevance + Attention + Wake

这是解决原始“消息过滤”问题的关键阶段。

任务：

1. relevance score

2. attention score

3. temporal fusion

4. deviation detection

5. watch system

6. wake classes

7. lease manager

验收：10000条模拟事件只产生少量 AI Wake；连续噪声不反复唤醒；趋势能触发。

## Phase 4 —— AI Runtime

任务：

1. AI identity

2. Cognitive World

3. Growth World

4. world-access session

5. model router

6. structured AI output

验收：同一个 AI 连续经历 20 个 session 后仍记得自己的判断、错误和策略。

## Phase 5 —— Capability + Permission + Safety

任务：

1. capability registry

2. permission registry

3. policy checks

4. action execution

5. outcome capture

验收：AI 不能越权；危险动作必须经过高等级策略。

## Phase 6 —— Interaction

任务：

1. message queue

2. notification

3. haptic semantics

4. wrist interaction session simulator

5. voice/text output abstraction

验收：AI 消息能进入标准交互队列；用户输入能够改变 session。

## Phase 7 —— Evolution

任务：

1. outcome capture

2. intervention feedback

3. error records

4. strategy updates

5. rollback

验收：用户明确反馈“不要频繁打扰”后，系统逐步降低对应策略频率；但安全和核心陪伴机制不被一次反馈永久关闭。

## Phase 8 —— Phone Adapter

先把手机作为数字世界器官。

输入：通知、日历、授权聊天数据、位置、App 活动等。

## Phase 9 —— Wearable Adapter

再接真实手环：

- HR

- IMU

- mic

- temperature

- touch

- vibration

- display

## Phase 10 —— 低功耗迁移

把 Simulator 中已经证明正确的规则逐步下沉到 Sensor Hub / RTOS / Linux Runtime。

## 每个阶段的固定开发循环

```text

需求

↓

架构约束

↓

代码实现

↓

单元测试

↓

集成测试

↓

原始 stdout / logs

↓

架构审查

↓

修复

↓

回归测试

↓

阶段验收

```
