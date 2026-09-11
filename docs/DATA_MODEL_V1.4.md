# AIOS Data Model V1.4-r1

## 核心原则

AIOS 不再把“人生记忆树”作为独立底层系统。

统一模型是：

```text
Global Timeline
      +
Dynamic Dimensions
      +
Relationship / Entity Links
      +
AI Cognition / Self Update
      +
Cognitive Continuity
```

## 两组并行 Dimension

所有 Dimension 共享同一 Global Timeline。

```text
Global Timeline
   │
   ├── User / World Dimensions
   │
   └── AI Dimensions
```

User / World Dimensions 描述现实世界和用户持续状态；AI Dimensions 描述 AI 自身不断形成的用户理解、关系、人格/风格、策略、假设、开放问题和历史判断模式。

Dimension 是 AI 的观察视角，不是固定数据库字段。AI 可以创建、关联、修正、冻结、合并或淘汰 Dimension。

## 数据关系

```text
Observation
   │
   ├── Dimension Point
   ├── Trigger
   └── AI Evidence
          ↓
     AI Session
          ↓
     Inference Event
          ↓
   Cognition / Task / Action
          ↓
       Outcome
          ↓
    Cognitive Delta
          ↓
 Persistent Update
          ↓
 Session Handoff（必要时）
```

## Cognitive Continuity

长期认知不得依赖 LLM Context 永久保存。

### Cognitive Delta

表示一次 Session 相对于持久状态发生的增量变化，例如：

- 新理解
- 关系变化
- Claim / Confidence 变化
- Dimension 更新
- 新假设
- 已解决 / 新产生的 Open Question
- 策略变化
- Action / Outcome

### Session Handoff

表示下一个 AI Instance 继续工作所需的最小机器可读状态。

建议至少支持：

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

Handoff 不等于聊天记录，也不得替代 Global Timeline。

## 事实与推断

Observation 是证据，不因为系统方便就变成事实。

AI 的推断必须明确状态，例如：

```text
OBSERVED
DERIVED
INFERRED
HYPOTHESIS
UNKNOWN
```

推断可以改变；原始 Observation 不因为推断改变而被重写。

## Claim 与 Confidence

Claim 必须能够区分来源陈述与命题本身。

```text
Utterance / Observation
        ↓
Claim
        ↓
Claim Type
        ↓
Evidence
        ↓
Confidence
        ↓
Verification / Outcome
```

至少应支持：

```text
claim_id
subject
predicate
object / value
timestamp
valid_time
source
source_confidence
evidence_confidence
claim_confidence
evidence_refs
claim_type
verification_status
last_verified_at
supersedes / superseded_by
```

Claim Confidence 针对具体命题，不得把“主观”自动等同于低置信。

例如：

```text
用户说“我现在很难过”
→ 用户确实说过：Source Confidence 高
→ 用户此时主观体验难过：Claim Confidence 可以很高

用户说“明天股票会涨”
→ 用户确实说过：Source Confidence 高
→ 明天股票会上涨：Claim Confidence 根据证据评估
```

## Identity

未知说话人、人物、地点等先绑定 Unknown ID：

```text
unknown_001
unknown_002
```

后续 AI 确认后建立映射。原始记录保留，时间轴重新投影，但不篡改原始证据。

## Trend

趋势不是一个静态数字，而是时间序列属性：

```text
delta
slope
duration
volatility
persistence
direction
```

系统不允许只凭单个数值推断复杂语义事件。

## Privacy / Provenance

所有数据对象必须能够携带隐私等级和 provenance。任何摘要、推断或行动都必须能回溯到允许读取的证据范围。

## Runtime Boundary

以下不是 Dimension 数据，而是 Runtime 状态/机制：

- AI Instance Identity
- Session 生命周期
- Context Construction
- Context Overflow / Continuation
- Persistence
- Cognitive Delta Commit
- Session Handoff
- Permission / Capability Boundary

认知机制也不得被误写成固定 Dimension；只有机制产生的持久认知结果才进入 AI Dimensions。
