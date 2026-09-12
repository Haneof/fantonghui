# AIOS AI 服务与认知运行时 V1.4-r2

AI 服务是 AIOS 的系统级常驻服务。用户主动、AI 主动、事件触发、时间触发和安全协助全部进入同一套 AI Runtime。

## 1. 运行入口

```text
用户主动
AI 主动
Trigger
MODE
安全事件
      ↓
AI Service
      ↓
AI Session
      ↓
Identity Bootstrap
      ↓
Autonomous Context Construction
      ↓
Cognitive Runtime
```

## 2. Identity First

任何 AI Instance 进入 AIOS 后，必须先建立：

- AI Instance 身份
- 当前角色与责任
- Session 身份
- Wake Reason
- 权限与能力
- 持久认知来源
- 当前 Context 与长期认知的区别

Identity 完成后，Runtime 不得强制规定 Dimension 阅读顺序。

## 3. 自主上下文

AI 可以根据目标自主查询：

- Global Timeline
- User / World Dimensions
- AI Dimensions
- 世界实体
- 关系
- Evidence / Provenance
- 历史结果
- Open Questions
- Active Goals
- 当前 MODE
- 当前能力与权限

Runtime 提供查询和预算，不替 AI 写死思考路线。

## 4. 认知与长期状态

```text
Persistent World / Cognition
        ↓
Context Construction
        ↓
Model
        ↓
Session
        ↓
Cognitive Delta
        ↓
Persistent Update
```

LLM Context 可以销毁、截断、更换模型，但 AIOS 长期认知不能丢失。

## 5. 帮助不是普通聊天回复

模型输出进入 AIOS 提交层后，可以形成：

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

最终由 AIOS 权限、能力和安全边界决定是否执行或持久化。

## 6. 能力调用

```text
AI 理解意图
    ↓
Capability Request
    ↓
能力发现 / 路由 / 权限 / 确认
    ↓
执行
    ↓
Outcome
    ↓
Timeline
```

AI 不直接绑定微信、淘宝等具体应用。能力系统负责寻找可用实现。

## 7. Handoff / Continuation

Context 接近运行时限制时，由 Runtime 自动创建 Continuation / Handoff。

Handoff 至少包含：

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

下一 AI Instance 基于 Handoff + Delta + 当前变化继续。

## 8. AI Watch

AI 可以登记观察条件；AIOS 负责低成本持续观察，命中后再次唤醒 AI。不得让模型长期占用上下文模拟“持续意识”。

## 9. 模型接入

```text
AI Service
   ↓
Model Router
   ├─ 文字模型
   ├─ 视觉模型
   ├─ 语音模型
   └─ 其他专用模型
```

模型供应商可以替换，不影响 AIOS 身份、世界、认知、关系和连续性。

## 10. 最低实现目标

V1.4-r2 软件完整功能必须最终证明：

1. 系统启动后 AI 服务可以常驻运行。
2. 用户主动请求可以进入 AI Session。
3. Trigger / MODE 可以唤醒 AI Session。
4. AI Instance 每次进入都先完成 Identity Bootstrap。
5. AI 可以自主查询世界与认知，而非固定读取顺序。
6. AI 可以调用统一能力接口。
7. 行动结果进入 Outcome 并回写 Timeline。
8. Cognitive Delta 可以持久化。
9. Handoff / Continuation 不丢失连续认知。
10. AI 能力应用可以共享核心认知而不建立第二套大脑。
11. 安全系统可以在必要时绕过普通帮助流程升级。
12. PC 模拟器可以运行完整软件闭环。
