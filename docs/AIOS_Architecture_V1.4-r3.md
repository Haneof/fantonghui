# AIOS 总体架构 V1.4-r3 —— 开放世界与完整 OS

> 本版本在 V1.4-r2 完整 OS 架构上进一步明确世界维度、节点、关联、全局导航和 AI 自主认知的边界。它不是增加固定分类，而是为开放 AI 世界提供稳定承载能力。

## 1. AIOS 总体定位

AIOS 是 AI 原生个人操作系统。手环是 AIOS 的具身终端，手机可以是重要现实数据源，但 AIOS 的核心不是设备 UI，也不是聊天应用。

```text
Linux / Device Base
        ↓
01 System Foundation
        ↓
02 Reality Access
        ↓
03 Observation & World Runtime
        ↓
04 Open World + Core Cognition
        ↓
05 Trigger / MODE / Watch
        ↓
06 Unified AI Service
        ↓
07 Capability System
        ↓
08 Model Gateway
        ↓
09 AI Capability Apps
        ↓
10 Human Interaction
        ↓
Reality
```

Personal Safety OS 横贯全链路；Simulator / Evaluator 与生产认知隔离。

## 2. OS 全局模块树

```text
AIOS
│
├─ 01 系统基础
│  ├─ 启动与生命周期
│  ├─ 系统调度
│  ├─ 设备管理
│  ├─ 电源管理
│  ├─ 存储管理
│  ├─ 网络与通信基础
│  ├─ 权限与安全基础
│  ├─ 更新 / 回滚 / 恢复
│  └─ Linux 适配
│
├─ 02 现实接入层
│  ├─ 传感器
│  ├─ 手机
│  ├─ 摄像头
│  ├─ 麦克风 / ASR / TTS
│  ├─ 定位
│  ├─ 生理数据
│  ├─ 网络数据
│  └─ 设备适配器
│
├─ 03 观察与世界运行时
│  ├─ Observation
│  ├─ Evidence / Provenance
│  ├─ Global Timeline
│  ├─ World Object / Entity
│  ├─ Node
│  ├─ Dynamic Relation
│  ├─ Global Navigation / Index
│  ├─ Query
│  └─ World State
│
├─ 04 核心认知
│  ├─ Open World Dimensions
│  ├─ User / World Dimensions
│  ├─ AI Dimensions
│  ├─ Cognitive Delta
│  ├─ Confidence
│  ├─ Hypothesis / Prediction
│  ├─ Outcome Verification
│  ├─ Summary / Trend
│  └─ Persistent Cognition
│
├─ 05 Trigger / MODE / Watch
│  ├─ Trigger Runtime
│  ├─ MODE Runtime
│  ├─ Time / Event / State Trigger
│  ├─ AI Watch
│  └─ Wake Management
│
├─ 06 Unified AI Service
│  ├─ AI Identity
│  ├─ Session
│  ├─ Autonomous Context Construction
│  ├─ Cognitive Runtime
│  ├─ User-Initiated Interaction
│  ├─ AI-Initiated Interaction
│  ├─ Help / Decision / Action / Silence
│  ├─ Outcome Processing
│  ├─ Self Update
│  └─ Handoff / Continuation
│
├─ 07 Capability System
│  ├─ Capability Contract
│  ├─ Discovery
│  ├─ Routing
│  ├─ Permission
│  ├─ Confirmation
│  ├─ Execution
│  ├─ Outcome
│  └─ Native / Phone / Web / Third Party
│
├─ 08 Model Gateway
│  ├─ Text
│  ├─ Vision
│  ├─ Speech
│  ├─ Specialized Models
│  ├─ Routing
│  ├─ Switching
│  ├─ Retry / Timeout / Fallback
│  └─ Provider Isolation
│
├─ 09 AI Capability Apps
│  ├─ Education
│  ├─ Social
│  ├─ Interest
│  ├─ Shopping
│  ├─ Health
│  ├─ Fitness
│  ├─ Work / Business
│  └─ Other Domains
│
├─ 10 Human Interaction
│  ├─ Screen
│  ├─ Touch
│  ├─ Gesture
│  ├─ Voice
│  ├─ Haptic
│  ├─ Bone Conduction / Private Audio
│  ├─ Wake / Notification
│  └─ Interaction State
│
├─ 11 Personal Safety OS
│  ├─ Fall / Collision
│  ├─ Physiological Anomaly
│  ├─ Non-response
│  ├─ User Confirmation
│  ├─ Emergency Escalation
│  └─ Family / Emergency Contacts
│
└─ 12 Simulator / Evaluation
   ├─ World Simulator
   ├─ Sensor Simulator
   ├─ Model Mock
   ├─ UI / Haptic Simulator
   ├─ Scenario Engine
   ├─ Cognitive Trace
   ├─ Evaluator
   ├─ Failure Diagnosis
   ├─ Mechanism Optimization
   └─ Regression
```

## 3. 开放世界模型

AIOS 世界不是一棵预定义分类树，而是一个持续生长的认知空间。

```text
观察 / Evidence
      ↓
世界对象 / 节点 / 状态 / 事件
      ↓
并行维度上的长期生长
      ↘        ↙
       动态关联
           ↓
  全局导航 / 查询 / 重构
           ↓
       AI Cognition
```

AIOS 必须能够承载世界，但不能替 AI 决定世界最终应该长成什么样。

## 4. 世界维度模型

### 4.1 维度是什么

Dimension 是一条长期持续生长的认知线，用于从某个长期视角观察和理解世界。

它不是：

- 数据库固定字段集合；
- 必须属于某个父维度的子树；
- 每天必须更新的任务；
- 一次事件的所有标签集合；
- 一个静态分类目录。

基础维度可以预先存在，例如时间、地点、环境、人物、事件、社交、情绪、压力、学习、工作、身体、偏好等，但初始状态可以为空。

这些只是系统的基础认知能力，不是封闭的世界分类表。

### 4.2 维度的平行性

维度在概念上平行、独立、持续延伸：

```text
时间 ─────────●──────────●──────────→
地点 ─────●──────────────●───────────→
环境 ───────────●────●──────────────→
人物 ──●──────────────●──────●──────→
事件 ───────●──●──────────────●──────→
情绪 ─────────●────────●────────────→
工作 ──●──────────●─────────────────→
AI认知 ─────●──────────────●─────────→
```

共同使用时间、地点、环境等世界坐标，不意味着这些维度拥有其他维度。

### 4.3 维度的动态形成

AI 可以在持续观察中发现某类信息具有独立、长期、可复用的认知价值，从而形成新的维度。

系统只提供：

- 创建能力
- 命名 / 描述能力
- 生命周期能力
- 查询能力
- 更新能力
- 合并 / 拆分 / 重组能力
- 停用能力

系统不规定固定阈值或固定触发条件。

## 5. 节点模型

Node 是世界中的可引用认知单元，可以代表：

- 一次观察
- 一个事件
- 一个状态
- 一个实体
- 一个关系
- 一个认知
- 一个假设
- 一个结果
- 其他 AI 判断有长期价值的信息

节点可以携带局部上下文，并引用其他节点、实体或维度。

## 6. 关联模型

关联是 AI 理解世界后形成的结构，不是预定义硬编码答案。

系统应支持：

- 节点 ↔ 节点
- 节点 ↔ 实体
- 节点 ↔ 维度
- 维度 ↔ 维度
- 节点 ↔ 时间 / 地点 / 环境
- 跨时间关联
- 跨上下文关联
- 语义、因果、关系、相似、支持、冲突等不同类型的关联

具体是否关联、关联强度、关系类型和生命周期由认知机制根据证据和上下文决定。

**示例不是规则。** 产品讨论中出现的某个具体事件或关键词，只用于解释概念，不得直接转化为固定 Schema 约束。

## 7. 全局导航与局部上下文

AIOS 同时提供两种能力：

### 局部理解

从一个节点出发，读取该节点相关的局部上下文和直接关系。

### 全局发现

从关键词、实体、事件概念、时间、地点、关系或其他导航线索出发，在整个世界中发现相关节点和证据。

```text
全局导航
    ↓
候选节点集合
    ↓
局部节点上下文
    ↓
跨节点比较 / 重构
    ↓
AI 形成当前认知
```

全局索引只是导航基础设施，不是第二套记忆系统，也不限制 AI 必须怎样组织认知。

核心能力是：

> **全局能够找，局部能够看，AI 能够重新理解。**

## 8. 时间模型

时间是独立维度，也是所有时间性信息的共同坐标。

系统至少支持：

```text
occurrence_time   发生
observation_time  被观察 / 发现
record_time       被记录
cognition_time    AI 形成认知
```

这些时间可能相同，也可能不同。

如果无法确定发生时间，保存未知、范围或上下界，而不是编造精确时间。

后续证据可以修正时间，同时保留 provenance。

## 9. 稀疏生长机制

世界模型不是“每天遍历所有维度”。

正确机制是：

```text
现实变化
 ↓
Observation
 ↓
AI 判断是否具有认知价值
 ↓
选择已有结构 / 建立新结构 / 暂不长期保存
 ↓
更新相关节点 / 维度 / 关联 / AI Cognition
```

没有证据，不等于数值为零；没有变化，不等于必须写一条“无变化”。

## 10. AI 世界

AI 也拥有自己的长期认知状态，可以形成独立的 AI Dimensions，例如：

- AI 对用户的理解
- AI 与用户关系
- AI 状态
- AI 计划
- AI 目标
- AI 经验
- AI 策略
- AI 假设
- AI 未解决问题
- AI 行为倾向

这些结构不是固定人格脚本，而是在持续互动、行动结果和用户反馈中演化。

## 11. Evidence / Cognition / Outcome

```text
Observation
   ↓
Evidence / Provenance
   ↓
Cognition / Hypothesis
   ↓
Prediction / Plan
   ↓
Action
   ↓
Outcome
   ↓
Verification
   ↓
Cognitive Update
```

系统必须保留足够证据链，使 AI 能够解释“为什么现在这样理解”，并能够在新证据出现时修正。

## 12. 多时间尺度总结

```text
底层观察 / 节点 / 证据
        ↓
日总结
        ↓
周总结
        ↓
月总结
        ↓
半年总结
        ↓
年度总结
        ↓
更长期趋势
```

总结是派生认知，不删除底层信息，不成为维度父节点。

## 13. Unified AI Service

AI Service 是系统级常驻服务：

```text
Wake
 ↓
Identity / Continuity
 ↓
Autonomous Context Construction
 ↓
Cognitive Runtime
 ↓
Help / Decision / Action / Silence
 ↓
Outcome
 ↓
Cognitive Delta
 ↓
Persistent Update
 ↓
Continuation
```

Runtime 提供能力、权限、连续性和上下文访问，不规定 AI 固定读取哪些维度或按照什么思维顺序。

## 14. Capability System

统一能力系统连接 AI 与现实世界：

```text
AI Intent
 ↓
Capability Discovery
 ↓
Routing
 ↓
Permission / Confirmation
 ↓
Execution
 ↓
Outcome
 ↓
World / Cognition Update
```

## 15. AI Capability Apps

应用是专业能力领域，不是传统手机应用复制品。

应用共享核心世界、认知、关系和能力系统，不得建立第二套 Memory / Personality / World Model。

## 16. Model Gateway

```text
AI Service
 ↓
Model Gateway
 ├─ Text
 ├─ Vision
 ├─ Speech
 └─ Specialized
```

模型可替换、可路由、可降级；模型切换不能破坏 AIOS 连续性。

## 17. Human Interaction

交互层负责把 AI 决定呈现给用户，以及把用户输入送回 AIOS：

- 屏幕
- 触摸
- 手势
- 语音
- 震动
- 骨传导
- 通知 / 唤醒

UI 不拥有世界模型和认知。

## 18. Personal Safety OS

安全系统独立于普通帮助系统，可以根据跌倒、碰撞、生理异常、无响应等信号进入安全流程，并按权限联系用户、家属或紧急服务。

## 19. Simulator / Evaluator

```text
Scenario
 ↓
Hidden Expected Intent
 ↓
AIOS Runtime
 ↓
Structured Cognitive Trace
 ↓
Evaluator
 ↓
Failure Diagnosis
 ↓
Mechanism Optimization
 ↓
Regression
```

评估的是 AIOS 的机制和行为质量，不把测试答案硬编码进生产系统。

## 20. 开发原则

生产运行时和模拟器保持边界；先 PC/Linux 完整闭环，再接手机，再接手环。

任何新增机制都必须回答：

1. 它是在提供 AI 能力，还是在替 AI 做决定？
2. 它是在承载世界，还是在把世界写死成分类？
3. 它是否保留证据和可修正性？
4. 它是否破坏 AI 的自主认知？
5. 它是否应该属于 Core OS，而不是某个应用？
