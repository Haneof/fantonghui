# AIOS OS Architecture V1.4-r1

## 1. 唯一主链

```text
外界数据
  ↓
Observation
  ↓
数据清洗 / 归一化 / 机械检测
  ↓
Global Timeline + Dynamic Dimensions
  ↓
Trigger（机械唤醒）
  ↓
AI Session
  ↓
Identity Bootstrap（强制第一步）
  ↓
Autonomous Context Construction
  ↓
Cognitive Runtime
  ↓
Inference Event / Cognition / Relationship / Task
  ↓
Help / Decision
  ↓
Action 或 Silence
  ↓
Outcome
  ↓
Cognitive Delta / AI Self Update
  ↓
Persistent Cognition / Session Handoff
```

**底层不负责理解世界。AI 负责理解。**

## 2. OS 的核心对象

- Observation：现实世界证据，第一公民。
- Global Timeline：唯一时间轴，所有对象都挂在这里。
- Dimension：可动态挂载的用户/世界/AI状态曲线。
- Trigger：机械条件满足后唤醒 AI，不做主观相关性判断。
- AI Session：真正理解上下文、历史、人物、关系和用户意图的认知会话。
- Identity Bootstrap：AI Instance 进入世界后必须首先完成的身份建立。
- Cognitive Runtime：负责认知会话生命周期、上下文构建、连续性和持久化边界。
- Inference Event：AI 根据证据生成的事件，不覆盖原始观测。
- Cognition：AI 对世界、用户和关系的当前判断。
- Task：定时或条件任务。
- Action：AI 或用户授权后的执行。
- Outcome：行动结果，必须回流时间轴。
- Cognitive Delta：本次 Session 相对于持久认知真正发生的变化。
- Session Handoff：供下一个 AI Instance 延续工作的增量状态。
- AI Self Update：AI 根据结果更新自己的认知与策略。

## 3. 两个并行的长期认知系统

所有 Dimension 共享同一条 Global Timeline，但概念上存在两组并行的动态观察视角：

```text
                    Global Timeline
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
       User / World            AI Dimensions
        Dimensions              Dimensions
              │                     │
              └──────────┬──────────┘
                         ↓
                 Cross-Dimension
                    Reasoning
```

### User / World Dimensions

描述现实世界、用户状态、人物关系、事件、习惯、环境等。

### AI Dimensions

描述 AI 自己不断发展的用户理解、关系、人格/风格、策略、长期假设、开放问题、历史经验和判断模式。

这不是两套数据库，而是同一时间轴上的两组可动态挂载认知视角。

## 4. 三条绝对边界

### 4.1 Observation 与 Interpretation 分离

不能把“听到一句话”直接写成“发生了谈判”。

```text
听到/看到/测到什么 → Observation
                     ↓
                    Trigger
                     ↓
                 AI Interpretation
                     ↓
               Inference Event
```

### 4.2 Trigger 与 AI 判断分离

Trigger 只回答：**“现在要不要把 AI 叫醒？”**

AI 才回答：**“这到底是什么、重不重要、要不要帮、怎么帮？”**

### 4.3 UI 与 OS 分离

UI 是呈现和交互层，不拥有：

- Memory
- Timeline
- AI brain
- Trigger Runtime
- 独立 App AI

3D Body / 屏幕 / 动画 / 手势 / 触觉都通过 Interaction Contract 与 OS 通信。

## 5. Runtime 分层

### L0 Sensor / Adapter

负责设备和外部数据接入。

### L1 Observation Runtime

负责接收、清洗、标准化、保存证据。

### L2 Timeline / Dimension Runtime

负责把 Observation 挂到唯一时间轴，并形成可比较的动态维度曲线。维度不等于固定数据库字段。

### L3 Trigger Runtime

只执行机械规则：阈值、方向变化、关键词命中、定时、用户操作、安全硬规则。

### L4 AI Cognitive Runtime

分为两个层次：

1. **Runtime Guarantees**：Identity Bootstrap、Session 生命周期、Context Construction、Context Overflow、Handoff、Persistence、Delta Commit、权限边界。
2. **Cognitive Mechanisms**：假设生成、证据寻找、跨维度推理、时间/关系推理、潜在意图识别、不确定性管理、自我修正、帮助判断。

Runtime 不得把认知路线硬编码成“固定先读某个维度再读某个维度”。除 Identity Bootstrap 外，认知路径由 AI 根据当前世界自主选择，并通过 Simulator/Regression 持续优化。

### L5 Capability / Action Runtime

调用外部能力。涉及花钱、对外发送、物理控制等高风险动作必须经过授权/确认策略。

### L6 Interaction Runtime

把 AIOS 的结果转换成屏幕、3D、震动、语音、骨传导等交互状态。

### L7 Outcome / Self Update

记录结果，生成 Cognitive Delta，并更新持久认知；必要时生成 Session Handoff。

## 6. Context Continuity

Context 不是长期记忆。

```text
Persistent World / Cognition
        ↓
Context Construction
        ↓
Session
        ↓
Cognitive Delta
        ↓
Persistent Update
```

AI Instance 切换、模型切换或 Context Overflow 后，不得要求新实例重新读取整个人生历史。应优先提供：

- 当前世界变化
- 相关 User/World Dimensions
- 相关 AI Dimensions
- Handoff
- Cognitive Delta
- Open Questions / Active Watches
- 必要证据引用

## 7. Cognitive Optimization

生产 Runtime 不接收隐藏的“标准答案”。Simulator 单独维护 Expected Intent 作为评估目标：

```text
Scenario
   ↓
Expected Intent（仅评估器知道）
   ↓
AIOS Runtime
   ↓
Cognitive Trace / Structured Telemetry
   ↓
Evaluator
   ↓
Failure Diagnosis
   ↓
Mechanism Optimization
   ↓
Regression
```

Expected Intent 是评价标准，不是生产 AI 的提示词。

认知优化优先修改机制，而不是针对单个案例硬编码回答。

## 8. 当前代码主线

所有新 OS 代码只进入：

```text
aios/01_os/
```

旧 `core/` 是历史实现资产。不得继续扩张成第二套 OS。
