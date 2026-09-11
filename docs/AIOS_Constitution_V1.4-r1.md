# AIOS 宪法 V1.4-r1 —— Cognitive Runtime

> V1.4-r1 是 V1.4-r0 的正式架构补丁版本。
> 本版本在保留 World Cognition、Evidence / Confidence、Global Timeline、Dynamic Dimensions 等既有原则的基础上，补齐 Cognitive Runtime、Identity Bootstrap、Autonomous Cognition 与 Cognitive Continuity。

## 1. 规范主链路

```text
Observation → Global Timeline → Dimension → Trigger → AI Session
→ Identity Bootstrap → Autonomous Context Construction
→ Cognitive Runtime → Inference / Help / Action / Silence
→ Outcome → Cognitive Delta → AI Self Update
→ Persistent Cognition / Session Handoff
```

## 2. Identity First —— 固定宪法原则

**任何 AI 认知实例进入 AIOS 后，必须先完成身份建立，然后才能进行世界认知。**

这是 Runtime 的硬性保证，不由模型自行决定。

Identity Bootstrap 至少建立：

- AI Instance 身份
- 明确自己是运行在 AIOS 中的 AI Instance，而不是 AIOS 本身
- 当前角色、责任、权限
- Session 身份
- Wake Reason
- 当前能力与工具权限
- 持久认知位于 AIOS，而不是当前 LLM Context
- 当前 Context 是工作记忆，不等于长期认知

**Identity Bootstrap 是唯一明确规定“必须首先发生”的认知入口。**

## 3. Autonomous Cognition —— 不规定固定读取路线

完成 Identity Bootstrap 后，AIOS 不得规定：

```text
先读 Dimension A → B → C → 最后判断
```

这种固定路线会把 AIOS 变成硬编码工作流。

Runtime 应提供：

- World / User Dimension 查询
- AI Dimension 查询
- Global Timeline 查询
- Evidence / Provenance 查询
- 跨维度关联
- 时间与关系查询
- 持久认知访问
- 权限与能力边界
- Context 容量与 Continuation

然后允许 AI 根据当前世界和当前任务自主决定如何认识世界。

## 4. 两个并行的长期认知世界

所有 Dimension 共享唯一 Global Timeline：

```text
                    Global Timeline
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
       User / World            AI Dimensions
        Dimensions              Dimensions
```

### User / World Dimensions

描述现实世界、用户状态、人物关系、事件、行为、环境、习惯等持续状态。

### AI Dimensions

描述 AI 自身不断形成、验证和修正的：

- 用户理解
- 用户偏好 / 价值
- AI 与用户关系
- AI 人格 / 风格
- 认知策略
- 长期假设
- Open Questions
- 历史经验
- 已验证 / 失败的判断模式

这不是两套数据库，而是同一时间轴上的两组动态观察视角。

## 5. Dimension 是观察视角，不是固定字段

AI 可以：

```text
选择 Dimension
→ 沿时间轴查看
→ 横向关联其他 Dimension
→ 搜索 Evidence
→ 建立假设
→ 发现矛盾
→ 修正认知
→ 创建高阶 Dimension
→ 冻结 / 合并 / 淘汰 Dimension
```

AI 可以决定不读取某个 Dimension，也可以决定继续探索更多 Dimension。

## 6. Runtime Mechanism 与 Persistent Cognition 分离

### Runtime 固定保证

- Identity Bootstrap
- Session 生命周期
- Context Construction
- Context Overflow / Continuation
- Persistence
- Cognitive Delta Commit
- Session Handoff
- Permission / Capability Boundary
- Evidence / Provenance 可追溯

### Cognitive Mechanisms —— 可优化能力

- 假设生成与竞争
- Evidence Seeking
- 跨维度推理
- 时间推理
- 关系推理
- 潜在意图识别
- 不确定性管理
- 自我修正
- Help / Intervention 判断

这些机制提供能力，但不规定唯一思维路线。

### Persistent Cognitive State

机制产生的长期结果可以进入 AI Dimensions，例如用户理解、关系理解、AI-User Relationship、AI 人格、行为模式、长期假设、Open Questions、已验证策略和失败经验。

**机制不是 Dimension；机制产生的持久认知结果才是 Dimension 的候选内容。**

## 7. Persistent Cognition ≠ LLM Context

```text
Persistent World / Cognition
        ↓
Context Construction
        ↓
LLM Context
        ↓
Session
        ↓
Cognitive Delta
        ↓
Persistent Update
```

LLM Context 可以销毁、截断、压缩或更换模型，但 AIOS 的长期世界与认知不能因此丢失。

## 8. Cognitive Delta

一次 Session 不应重写整个世界。

Delta 记录本次 Session 真正发生的变化：

- 新理解
- Claim / Confidence 变化
- Relationship 变化
- Dimension 更新
- 新假设
- Open Question 变化
- 策略变化
- Action / Outcome

## 9. Session Handoff

AI Instance 因 Context、模型切换、资源限制或其他原因结束时，Runtime 必须能够交付机器可读 Handoff。

至少支持：

```text
session_id
wake_reason
objective
world_changes
cognitive_delta
new_understanding
relationship_updates
active_goals
open_questions
hypotheses
decisions
help_or_action
outcome
confidence_updates
dimension_updates
next_attention
```

Handoff 是增量认知状态，不是聊天记录，也不替代 Global Timeline。

下一 AI Instance 应基于 Handoff + Delta + 当前变化继续，而不是从零重新读取全部历史。

## 10. Context Overflow / Continuation

Context 接近 Runtime 限制时，由 Runtime 自动进入 Continuation / Handoff。

不得依赖模型自行判断“我是不是快没有 Context 了”。

Continuation 优先传递当前目标、关键 Evidence 引用、假设、未解决问题、决策和未提交 Delta。

## 11. Evidence / Confidence 继承 V1.4-r0

V1.4-r1 保留并继续执行 V1.4-r0 的认知真实性原则：

```text
OBSERVED
DERIVED
INFERRED
HYPOTHESIS
UNKNOWN
```

并区分：

```text
Source Confidence
Evidence Confidence
Claim Confidence
```

“用户确实说过 X”和“X 本身为真”必须是不同命题。

证据必须可追溯；认知可以修正；历史证据不得被当前认知覆盖。

## 12. Outcome / Self Update

预测、假设、计划和行动应尽可能进入：

```text
Prediction / Hypothesis / Plan
        ↓
Outcome
        ↓
Verification
        ↓
Confidence Update
        ↓
AI Self Update
```

AI 可以从长期结果形成新的 AI Dimension，但不得把单次错误直接固化为永久事实。

核心原则：

> **可追溯地犯错、可解释地修正、从结果中学习。**

## 13. Cognitive Optimization —— AIOS 自我优化机制

认知优化必须与生产认知分离。

Simulator 可以持有生产 AI 不知道的 Expected Intent：

```text
Scenario
   ↓
Expected Intent（仅 Evaluator 知道）
   ↓
AIOS Runtime
   ↓
Structured Cognitive Trace / Telemetry
   ↓
Evaluator
   ↓
Failure Diagnosis
   ↓
Mechanism Optimization
   ↓
Regression
```

Expected Intent 是评价目标，不是生产 AI 的指令。

例如评估器期望 AI 在用户回家后主动安慰用户，但 AI 只看到饮食或消费异常并给出无关建议，则属于认知失败。

失败至少可以分类：

- Observation Failure
- Context Failure
- Interpretation Failure
- Reasoning / Mechanism Failure
- Intervention Failure
- Continuity Failure

优化应修改机制，而不是针对单一案例硬编码答案。

## 14. Structured Cognitive Trace

Runtime / Simulator 可以记录结构化诊断信息：

```text
selected_dimensions
evidence_refs
queries
hypotheses
confidence_changes
decision_factors
action_proposal
outcome
failure_class
```

Trace 用于定位问题，不以保存模型隐藏思维链作为架构前提。

## 15. Regression 原则

任何认知机制优化必须通过场景回归。

不能因为某一类任务命中率提高，就允许其他任务、安全判断、用户意图识别、连续性或帮助质量下降。

目标是整体认知能力提升，而非单案例过拟合。

## 16. 与 V1.4-r0 的关系

V1.4-r1 不推翻 V1.4-r0。

保留：

- Observation First
- Global Timeline 唯一
- Dynamic Dimensions
- Trigger ≠ AI Judgment
- One AI
- Help-First / Intent-First
- Safety First
- Outcome 回写
- Evidence / Confidence

新增：

> **Identity First + Autonomous Cognition + Cognitive Continuity + Cognitive Optimization。**

除 Identity Bootstrap 外，AIOS 不规定 AI 必须采用固定认知路线；Runtime 提供能力与边界，认知机制通过模拟、评估和回归持续优化。
