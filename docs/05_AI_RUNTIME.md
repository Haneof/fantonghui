# AIOS AI Runtime V1.4-r1

## 1. 目标

AIOS AI Runtime 不是“一次 Prompt + 一次回答”，而是一个可持续进入 AIOS World、读取自身与世界认知、产生认知结果并通过 Session Continuity 延续的 AI 运行时。

核心原则：

```text
AI Instance
  ↓
Identity Bootstrap（固定第一步）
  ↓
Session Initialization
  ↓
Autonomous Context Construction
  ↓
World / User Dimensions + AI Dimensions
  ↓
Cognitive Runtime
  ↓
Inference / Help / Action / Silence
  ↓
Cognitive Delta + Outcome
  ↓
Persistent Update / Handoff
```

## 2. AI Instance Identity Bootstrap（强制）

**任何 AI 认知实例进入 AIOS 后，必须先完成身份建立，然后才能进行世界认知。**

这是 Runtime 的硬性保证，不由模型自行决定是否执行。

Identity Bootstrap 至少确认：

- 当前 AI Instance 身份
- 明确自己是运行在 AIOS 中的 AI 实例，而不是 AIOS 本身
- 当前角色 / 责任 / 权限
- 当前 Session 身份
- Wake Reason
- 当前可用能力与工具权限
- 持久认知位于 AIOS，而不是当前 LLM Context
- 当前 Context 是工作记忆，不等于长期认知

Identity Bootstrap 完成后，Runtime 不得强制规定固定的“先读 Dimension A，再读 Dimension B”的认知路线。

## 3. 自主认知入口

AI 唤醒后，Runtime 提供可访问的世界，而不是提供一条固定思维路线。

AI 可以自主决定：

- 读取哪些 User / World Dimensions
- 读取哪些 AI Dimensions
- 沿时间轴向前或向后查看什么
- 进行哪些跨维度关联
- 搜索哪些证据
- 提出哪些假设
- 哪些信息暂时不需要读取
- 是否需要继续探索
- 是否应该帮助、等待或保持沉默

Runtime 的职责是**提供能力、边界、可追溯性和连续性**，而不是规定具体认知顺序。

## 4. 两个并行的长期认知世界

AIOS 的所有 Dimension 共享同一 Global Timeline，但长期认知在概念上分为两条并行系统：

### 4.1 User / World Dimensions

描述用户与现实世界的持续状态、关系、事件、习惯、环境和其他可观察/推断维度。

### 4.2 AI Dimensions

描述 AI 自身不断发展的：

- 用户理解
- 用户偏好与价值判断
- AI 与用户的关系
- AI 自身人格 / 风格
- 认知策略
- 长期假设
- 开放问题
- 历史经验
- 已验证与失败的判断模式

两者不是两套数据库，而是**同一 Global Timeline 上的两组可动态挂载认知视角**。

## 5. Persistent Cognition ≠ LLM Context

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

LLM Context 可以销毁；AIOS 的长期世界与认知不能依赖 Context 永久存在。

因此第二个 AI Instance 不应重新阅读整段历史来“重新认识世界”。它应获得：

- 当前世界变化
- 相关持久认知
- 当前 Session Handoff
- Cognitive Delta
- Open Questions / Active Watches
- 必要的证据引用

## 6. Cognitive Runtime 与 Cognitive Mechanisms 分离

### Runtime 固定保证

- Identity Bootstrap
- Session 生命周期
- Context Construction 接口
- Context Overflow / Continuation
- Handoff
- Persistence
- Cognitive Delta Commit
- 权限与工具边界
- Evidence / Provenance 可追溯

### Cognitive Mechanisms 可优化

机制用于提供能力，而不是规定固定思维路线，例如：

- 假设生成与竞争
- 证据寻找
- 跨维度推理
- 时间推理
- 关系推理
- 用户潜在意图识别
- 不确定性管理
- 自我修正
- 帮助方式选择
- 干预时机判断

这些机制应通过 Simulator / Regression 持续优化。

## 7. Session Handoff

当一个 AI Instance 因 Context、模型切换、资源限制或其他原因结束时，Runtime 必须能够生成机器可读的 Handoff，而不是要求下一实例重新读取全部历史。

Handoff 至少可表达：

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

Handoff 是增量认知状态，不是完整聊天记录。

## 8. Cognitive Delta

Session 不应要求每次重写整个世界模型。

```text
World State
   ↓
Session
   ↓
Cognitive Delta
   ↓
Persistent Update
```

Delta 记录本次 Session 真正发生的认知变化、关系变化、置信变化、维度变化和待解决问题。

## 9. AI 输出类型

模型输出进入系统审核/提交层后，才决定是否形成持久状态或执行 Action。

```text
BELIEF_UPDATE
HYPOTHESIS
QUESTION
PREDICTION
DECISION
CAPABILITY_REQUEST
MESSAGE
WATCH_REQUEST
REFLECTION
ACTION_PROPOSAL
SILENCE
```

原始 Observation 不得被模型输出覆盖。

## 10. AI Watch

AI 可以建立临时观察条件；AIOS 负责持续机械观察。命中条件后再次唤醒 AI。

AI Watch 不要求 AI 持续运行，也不允许通过后台持续占用模型 Context 来模拟长期意识。

## 11. Context Overflow / Continuation

Context 接近 Runtime 限制时，由 Runtime 触发 Continuation/Handoff。

不得依赖模型自行判断“我是不是快没上下文了”。

Continuation 应尽可能只传递：

- 当前目标
- 已确认的关键证据引用
- 已形成的假设
- 尚未解决的问题
- 已做出的决策
- 尚未提交的 Cognitive Delta
- 下一步需要关注的事项

## 12. 模型与 AI 的关系

```text
AIOS AI Runtime
      ↓
Model Router
      ↓
GPT / Claude / Gemini / Local / Specialist
```

模型可以更换；AI Instance Identity、Persistent Cognition、World、Relationship 和 Session Continuity 不应随模型更换而丢失。

## 13. 最低实现要求

V1.4-r1 Runtime 至少必须能够证明：

1. AI Instance 有持久 identity。
2. 每次 Wake 强制先执行 Identity Bootstrap。
3. Bootstrap 后 AI 可以自主选择读取哪些 Dimension。
4. User/World Dimensions 与 AI Dimensions 共享 Global Timeline。
5. AI 不需要固定顺序读取 Dimension。
6. Session 可以生成 Cognitive Delta。
7. Session 可以生成 Handoff。
8. 第二个 AI Instance 可以基于 Handoff + Delta + 当前变化继续，而不是从零开始。
9. Context Overflow 可以自动进入 Continuation。
10. Outcome 可以回到 Timeline 并参与后续 Self Update。
