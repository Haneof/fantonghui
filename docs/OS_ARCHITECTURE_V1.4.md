# AIOS OS Architecture V1.4

## 1. 唯一主链

```text
外界数据
  ↓
Observation
  ↓
数据清洗 / 归一化 / 机械检测
  ↓
Global Timeline + Dimension Curves
  ↓
Trigger（机械唤醒）
  ↓
AI Session
  ↓
Inference Event / Cognition / Relationship / Task
  ↓
Help / Decision
  ↓
Action 或 Silence
  ↓
Outcome
  ↓
AI Self Update
```

**底层不负责理解世界。AI 负责理解。**

## 2. OS 的核心对象

- Observation：现实世界证据，第一公民。
- Global Timeline：唯一时间轴，所有对象都挂在这里。
- Dimension：可动态挂载的用户/世界/AI状态曲线。
- Trigger：机械条件满足后唤醒 AI，不做主观相关性判断。
- AI Session：真正理解上下文、历史、人物、关系和用户意图的认知会话。
- Inference Event：AI 根据证据生成的事件，不覆盖原始观测。
- Cognition：AI 对世界、用户和关系的当前判断。
- Task：定时或条件任务。
- Action：AI 或用户授权后的执行。
- Outcome：行动结果，必须回流时间轴。
- AI Self Update：AI 根据结果更新自己的判断、策略和能力认知。

## 3. 三条绝对边界

### 3.1 Observation 与 Interpretation 分离

不能把“听到一句话”直接写成“发生了谈判”。

正确：

```text
听到/看到/测到什么 → Observation
                     ↓
                    Trigger
                     ↓
                 AI Interpretation
                     ↓
               Inference Event
```

### 3.2 Trigger 与 AI 判断分离

Trigger 只回答：**“现在要不要把 AI 叫醒？”**

AI 才回答：**“这到底是什么、重不重要、要不要帮、怎么帮？”**

### 3.3 UI 与 OS 分离

UI 是呈现和交互层，不拥有：

- Memory
- Timeline
- AI brain
- Trigger Runtime
- 独立 App AI

3D Body / 屏幕 / 动画 / 手势 / 触觉都通过 Interaction Contract 与 OS 通信。

## 4. Runtime 分层

### L0 Sensor / Adapter

负责设备和外部数据接入。

### L1 Observation Runtime

负责接收、清洗、标准化、保存证据。

### L2 Timeline / Dimension Runtime

负责把 Observation 挂到唯一时间轴，并形成可比较的维度曲线。

### L3 Trigger Runtime

只执行机械规则：阈值、方向变化、关键词命中、定时、用户操作、安全硬规则。

### L4 AI Runtime

AI 被唤醒后选择读取范围，理解世界，生成事件、关系、认知、帮助和行动建议。

### L5 Capability / Action Runtime

调用外部能力。涉及花钱、对外发送、物理控制等高风险动作必须经过授权/确认策略。

### L6 Interaction Runtime

把 AIOS 的结果转换成屏幕、3D、震动、语音、骨传导等交互状态。

### L7 Outcome / Self Update

记录结果并让 AI 更新自己的认知与策略。

## 5. 当前代码主线

所有新 OS 代码只进入：

```text
aios/01_os/
```

旧 `core/` 是历史实现资产。不得继续扩张成第二套 OS。
