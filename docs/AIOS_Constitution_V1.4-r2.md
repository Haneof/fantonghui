# AIOS 宪法 V1.4-r2 —— 完整 OS 架构补丁

> V1.4-r2 在 V1.4-r1 的认知运行时基础上，补齐完整 AIOS 操作系统模块边界。
> V1.4-r1 的认知真实性、Global Timeline、Dynamic Dimension、Identity First、Autonomous Cognition、Evidence / Confidence、Outcome、Continuation 等原则全部继承。

## 1. AIOS 定义

AIOS 是 AI 原生个人操作系统，不是聊天应用、普通助手、传统手机应用集合或单纯的智能手表系统。

```text
系统基础
  ↓
现实接入
  ↓
观察 / 世界运行时
  ↓
核心认知
  ↓
触发 / MODE
  ↓
AI 服务
  ↓
能力系统
  ↓
AI 能力应用
  ↓
人机交互
```

安全系统贯穿上述链路；模型接入是 AI 服务的模型供应层；模拟器与测试系统独立于生产认知。

## 2. 核心架构原则

1. **Observation First**：先记录事实与来源，再形成认知。
2. **Global Timeline 唯一**：所有长期世界与认知状态最终锚定同一时间轴。
3. **Dimension 动态化**：Dimension 是时间轴上的观察视角/时间曲线，不是固定字段。
4. **User/World 与 AI Dimensions 并行**：共用同一 Global Timeline。
5. **Identity First**：任何 AI Instance 进入 AIOS 后必须首先完成 Identity Bootstrap。
6. **Autonomous Cognition**：Identity 之后不得规定固定 Dimension 阅读顺序。
7. **Persistent Cognition ≠ LLM Context**：长期认知属于 AIOS，不属于某一次模型上下文。
8. **Evidence 可追溯**：Observation、Evidence、Cognition、Hypothesis、Prediction、Outcome 必须区分。
9. **Outcome 回写**：预测、计划和行动尽可能通过结果验证并更新认知。
10. **能力统一**：AI 不直接绑定具体应用，而通过统一能力接口执行现实行动。
11. **AI 能力应用原生化**：应用是专业 AI 能力领域，不复制传统手机应用的大脑。
12. **UI 无大脑**：UI 不拥有独立 AI、记忆、时间轴、世界模型或触发系统。
13. **安全优先**：安全系统可以绕过普通 AI 帮助流程执行硬性升级。
14. **模拟器与生产隔离**：评估器的 Expected Intent 不进入生产 AI 上下文。
15. **硬件后适配**：先在 PC/Linux 完整实现软件闭环，再接手机和手环。

## 3. 核心认知

AIOS 不再把“人生记忆树”作为独立系统。长期个人世界由：

```text
Global Timeline
+ 世界对象 / 实体
+ 关系
+ Evidence / Provenance
+ User / World Dimensions
+ AI Dimensions
+ Cognitive Delta
+ Open Questions
```

共同构成。

AI Dimensions 可表达用户理解、偏好、价值、关系、AI 人格、策略、长期假设、历史经验和开放问题。

## 4. AI 服务

AI 服务是系统级常驻服务，统一承载：

- 用户主动聊天 / 求助
- AI 主动聊天
- AI 主动帮助
- AI 主动提醒
- 事件触发后的介入
- 时间触发后的介入
- 安全相关 AI 协助
- Help / Decision / Action / Silence

“主动”和“被动”不是两个 AI 系统。

## 5. 能力系统

能力系统向 AI 提供稳定、统一的可执行接口，例如：

```text
发送消息
查询天气
打开地图
搜索商品
查询日历
拍照
读取文件
控制设备
```

能力实现可以来自 AIOS 原生能力、手机应用、网络服务或第三方接口。

能力系统负责发现、路由、权限、确认、执行和结果回写；不替 AI 决定用户真正意图。

## 6. AI 能力应用生态

AI 能力应用必须是轻量、AI 原生、专业领域化。

允许：

- 教育
- 社交
- 兴趣
- 购物
- 健康
- 健身
- 工作 / 商务
- 其他垂直领域

禁止把 AIOS 的应用层理解成重新实现微信、淘宝、亚马逊、短视频等传统应用。应用使用 AIOS 核心认知，而不是建立第二套用户记忆和人格。

## 7. 模型接入

模型是可替换执行引擎：

```text
AI 服务 → 模型接入 → 文字 / 视觉 / 语音 / 专用模型
```

模型切换不得导致 AIOS 的身份、长期认知、世界、关系和连续性丢失。

AIOS 不以本地运行大模型推理为前提；本地运行时负责世界、认知状态、调度、权限、能力和设备控制，模型通过统一接口接入。

## 8. 安全

安全系统独立于普通帮助系统，负责异常检测、用户确认、无响应升级、紧急联系人和求救流程。

普通 AI 不得覆盖安全系统的硬性保护规则。

## 9. AI Runtime

```text
Wake
 → Identity Bootstrap
 → Session 初始化
 → Autonomous Context Construction
 → Cognitive Runtime
 → Help / Decision / Action / Silence
 → Outcome
 → Cognitive Delta
 → Persistent Update
 → Handoff / Continuation
```

Runtime 固定保证连续性，但不规定具体思维路线。

## 10. 认知优化

```text
Scenario
 → Hidden Expected Intent
 → AIOS Runtime
 → Structured Cognitive Trace
 → Evaluator
 → Failure Diagnosis
 → Mechanism Optimization
 → Regression
```

Trace 只记录可审计结构，不以保存隐藏思维链为前提。

## 11. 关键词 / 实体导航

关键词与实体索引属于世界导航基础设施：

```text
关键词 / 指称
 → 世界实体
 → Timeline refs
 → Relationships
 → Dimensions
 → Evidence
 → AI Context
```

它不是简单的全文搜索，也不是第二套记忆系统。

## 12. 软件优先、硬件后适配

第一阶段使用 PC/Linux + 模拟器实现完整功能：

```text
模拟传感器 / 手机 / 摄像头 / 语音 / 屏幕 / 震动
                  ↓
               完整 AIOS
```

之后替换为真实手机与手环适配器。

## 13. 禁止事项

- 不建立第二套 Core Runtime。
- 不恢复已删除的旧 Constitution / Schema / Runtime 作为当前设计。
- 不把 AIOS 应用做成传统手机应用复制品。
- 不让每个应用建立独立用户记忆。
- 不让 UI 拥有独立 AI 大脑。
- 不把 LLM Context 当长期记忆。
- 不用固定 Dimension 顺序硬编码认知。
- 不把模型供应商绑定成 AIOS 身份。
- 不让单次错误直接变成永久事实。
- 不把 Simulator 的隐藏 Expected Intent 泄露给生产 AI。

## 14. 版本关系

V1.4-r2 = V1.4-r1 + 完整 OS 模块架构补丁。

V1.4-r2 不推翻 r1，而是把 r1 的认知运行时嵌入完整 AIOS，并明确系统基础、现实接入、世界运行时、核心认知、AI 服务、能力系统、模型接入、AI 能力应用、人机交互、安全、模拟器之间的职责边界。
