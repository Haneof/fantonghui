# AIOS 宪法 V1.4-r1 —— Cognitive Runtime Patch

> 基于 V1.4-r0 的正式架构补丁
> 本补丁不推翻 V1.4 的 World Cognition 主链，而是补齐 AI 如何进入世界、建立自身、使用 Dimension、保持连续性以及通过模拟优化认知机制的规范。

## 1. 补丁定位

V1.4-r0 已定义：

```text
Observation → Global Timeline → Dimension → Trigger → AI Session
→ Inference Event → Help / Action → Outcome → AI Self Update
```

V1.4-r1 补齐 AI Session 内部缺失的 Runtime 机制：

```text
AI Wake
  ↓
Identity Bootstrap
  ↓
Session Initialization
  ↓
Autonomous Context Construction
  ↓
Cognitive Runtime
  ↓
Inference / Help / Action / Silence
  ↓
Cognitive Delta
  ↓
Persistent Update / Handoff
```

## 2. 强制原则：Identity First

**任何 AI 认知实例进入 AIOS 后，必须先完成身份建立，然后才能进行世界认知。**

这是 AIOS 的固定宪法级 Runtime 保证，不由模型自行选择，不得通过 Prompt 中的普通建议语句弱化。

Identity Bootstrap 至少建立：

- AI Instance 是谁
- 自己是运行在 AIOS 中的 AI Instance，而不是 AIOS 本身
- 当前角色、责任和权限
- 当前 Session
- Wake Reason
- 当前可用能力与工具
- 持久认知存放于 AIOS，而不是当前 LLM Context
- 当前 Context 只是工作记忆

**Identity Bootstrap 是唯一明确规定“必须首先发生”的认知入口。**

## 3. 不允许硬编码固定认知路线

完成 Identity Bootstrap 后，AIOS 不得规定类似以下固定路线：

```text
先读 Dimension A
→ 再读 Dimension B
→ 再读 Dimension C
→ 最后判断用户需求
```

这会把 AIOS 退化成固定流程，而不是一个能够自我优化的认知 Runtime。

Runtime 应提供：

- 世界访问能力
- Dimension 查询能力
- 时间轴查询能力
- 跨维度关联能力
- Evidence 查询能力
- 持久认知访问能力
- 权限与边界
- Context 成本与容量信息
- Continuation / Handoff

然后允许 AI 根据当前问题自主决定如何认识这个世界。

## 4. 两个并行的长期认知世界

所有 Dimension 共享同一 Global Timeline。

概念上存在：

```text
Global Timeline
      │
      ├── User / World Dimensions
      │
      └── AI Dimensions
```

### User / World Dimensions

描述用户和现实世界的状态、人物、关系、事件、行为、环境、习惯等。

### AI Dimensions

描述 AI 自己不断形成和修正的：

- 用户理解
- 用户偏好 / 价值
- AI 与用户关系
- AI 人格 / 风格
- 认知策略
- 长期假设
- Open Questions
- 历史经验
- 已验证 / 失败的判断模式

它们不是两套数据库，而是同一时间轴上的两组可动态挂载观察视角。

## 5. Dimension 使用原则

Dimension 不是数据库字段，也不是必须全部读取的“记忆列表”。

AI 可以：

```text
选择 Dimension
→ 沿时间轴查看
→ 横向比较其他 Dimension
→ 搜索 Evidence
→ 建立假设
→ 发现矛盾
→ 修正已有认知
→ 创建新的高阶 Dimension
```

AI 必须能够在“不读取某个 Dimension”与“继续探索更多 Dimension”之间自主选择。

## 6. Runtime Mechanism 与 Persistent Cognition 分离

### 固定 Runtime 机制

- Identity Bootstrap
- Session 生命周期
- Context Construction
- Context Overflow / Continuation
- Persistence
- Cognitive Delta Commit
- Session Handoff
- 权限 / Capability Boundary
- Provenance / Evidence 可追溯

### 可优化 Cognitive Mechanisms

- 假设生成与竞争
- Evidence seeking
- 跨维度推理
- 时间推理
- 关系推理
- 潜在意图识别
- 不确定性管理
- 自我修正
- Help / Intervention 判断

### Persistent Cognitive State

由认知产生并长期保存的结果可以进入 AI Dimensions，例如：

- 用户理解
- 用户关系理解
- AI-User Relationship
- AI 人格 / 风格
- 用户行为模式
- 长期假设
- Open Questions
- 已验证策略
- 失败经验

**机制不是 Dimension；机制产生的持久认知结果才是 Dimension 的候选内容。**

## 7. Persistent Cognition ≠ LLM Context

LLM Context 可以被销毁、截断、压缩或更换模型。

长期世界和认知不得依赖某一次 Context 永久存在。

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

## 8. Cognitive Delta

一次 Session 不应要求 AI 重写整个世界。

Cognitive Delta 记录本次 Session 真正改变的部分，包括：

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

Handoff 至少表达：

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

下一 AI Instance 必须能够基于 Handoff + Cognitive Delta + 当前变化继续工作，而不是从零开始重新读取全部历史。

## 10. Context Overflow 必须由 Runtime 保证

当 Context 接近 Runtime 限制时，必须由 Runtime 进入 Continuation / Handoff。

不得要求模型自行“感觉”自己快没有 Context。

Continuation 应优先携带当前目标、关键 Evidence 引用、已形成假设、未解决问题、决策和未提交 Delta。

## 11. Cognitive Optimization / Simulator

AIOS 必须把“生产认知”和“认知优化实验”分开。

Simulator 使用隐藏的 Expected Intent 作为评价目标：

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

**Expected Intent 是评估目标，不是生产 AI 的指令。**

例如：

```text
Expected Intent：用户回家后真正需要的是情绪安慰
```

生产 AI 不知道这个答案，只能根据 World / User / AI Dimensions 自主判断。

如果 AI 因为看到饮食、消费等显著异常而给出完全不相关的帮助，则属于认知失败。应检查：

- Observation Failure
- Context Failure
- Interpretation Failure
- Reasoning / Mechanism Failure
- Intervention Failure
- Continuity Failure

优化目标是修改认知机制，而不是给某一个场景添加固定回答。

## 12. 结构化 Cognitive Trace

Simulator / Runtime 可以记录用于诊断的结构化认知遥测，例如：

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

Trace 的目的是真正定位 Runtime / Context / Mechanism / Intervention 的问题。

不得以保存模型隐藏思维链作为架构前提。

## 13. 回归原则

任何认知机制优化必须经过已有场景回归。

不能因为：

```text
情绪安慰命中率 ↑
```

就允许：

```text
工作帮助 ↓
安全判断 ↓
用户意图识别 ↓
连续性 ↓
```

优化目标应是整体认知能力，而不是单指标过拟合。

## 14. 与 V1.4-r0 的关系

本补丁保留 V1.4-r0 的：

- Observation First
- Global Timeline 唯一
- Dynamic Dimensions
- Trigger ≠ AI Judgment
- One AI
- Help-First / Intent-First
- Safety First
- Outcome 回写
- Evidence / Confidence
- 可追溯地犯错、可解释地修正、从结果中学习

V1.4-r1 新增的核心是：

> **Identity First + Autonomous Cognition + Cognitive Continuity + Cognitive Optimization。**

除 Identity Bootstrap 外，AIOS 不规定 AI 必须采用固定认知路线；Runtime 提供能力与边界，认知机制通过模拟、评估和回归持续优化。
