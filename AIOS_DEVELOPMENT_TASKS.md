# AIOS Development Task Ledger

> 状态：ACTIVE
> 唯一开发分支：`aios`
> 唯一 OS 主线：`aios/01_os/`
> 唯一有效宪法：`docs/AIOS_Constitution_V1.4-r2.md`
> 唯一完整架构：`docs/AIOS_Architecture_V1.4-r2.md`
>
> **硬规则：任何代码、Schema、Runtime Contract、架构文档或测试发生修改后，必须同步更新本任务表。没有测试/运行证据和 Commit，不得标记完成。**

## 0. 永久工程规则

1. 只在 `aios` 分支开发。
2. `aios/01_os/` 是唯一 OS 产品实现主线。
3. 不恢复旧 `core/`、旧 Constitution、旧 Runtime 或旧 Schema/Test 作为当前设计。
4. Observation 是事实入口；Global Timeline 是唯一时间基准。
5. Dimension 是 Timeline 上的动态观察视角/时间曲线，不是静态字段、标签或快照。
6. User/World Dimensions 与 AI Dimensions 共用唯一 Global Timeline，并行演化。
7. AI Instance 接入后必须首先完成 Identity Bootstrap。
8. Identity 之后不得规定固定 Dimension 阅读顺序。
9. Runtime 提供能力、边界、权限、上下文容量和连续性，不替 AI 写死思维路线。
10. Observation / Evidence / Cognition / Hypothesis / Prediction / Outcome 必须可区分、可追溯、可修正。
11. AI 服务统一承载用户主动和 AI 主动，不拆成两个独立大脑。
12. 能力系统是 AI 与现实世界之间的统一执行接口。
13. AI 能力应用不得建立第二套用户记忆、人格、关系或世界模型。
14. UI 不拥有独立 AI、Timeline、Memory、Trigger 或 Cognition。
15. 模型供应商可替换，不得成为 AIOS 身份或长期认知的一部分。
16. Simulator 的 Expected Intent 对被测 AI 隐藏。

## 1. V1.4-r2 总体开发路线

```text
A0 架构基线冻结
 → A1 系统基础
 → A2 现实接入 / Observation
 → A3 Global Timeline / 世界对象 / 关系 / 实体索引
 → A4 User/World + AI Dimensions
 → A5 Evidence / Confidence / Outcome
 → A6 Trigger + MODE + Watch
 → A7 AI Service / Session / Identity / Cognitive Runtime
 → A8 自主上下文 / Delta / Handoff / Continuation
 → A9 能力系统 / 权限 / 路由
 → A10 模型接入
 → A11 AI 能力应用生态
 → A12 人机交互
 → A13 Personal Safety OS
 → A14 PC 完整模拟器
 → A15 手机适配
 → A16 手环适配
 → A17 认知模拟 / 评估 / 机制优化 / 回归
```

## 2. 架构基线任务

| ID | 任务 | 状态 | 验收 |
|---|---|---|---|
| A0-T1 | V1.4-r2 完整 OS 模块树 | ✅ | 架构文档已提交 |
| A0-T2 | V1.4-r2 宪法补丁 | ✅ | 新宪法为唯一入口 |
| A0-T3 | AI 服务统一主动/被动 | ✅ | 架构边界明确 |
| A0-T4 | 能力系统统一接口 | ✅ | 能力层边界明确 |
| A0-T5 | AI 能力应用模型 | ✅ | 不再按传统手机应用复制 |
| A0-T6 | PC 优先、硬件后适配 | ✅ | 模拟器优先原则冻结 |
| A0-T7 | 关键词/实体导航索引纳入架构 | ✅ | 作为世界导航基础设施定义 |
| A0-T8 | 旧 V1.4-r1 文档切换到 r2 | ✅ | r1 不再作为当前架构入口 |

## 3. 下一阶段任务

| ID | 任务 | 状态 | 验收 |
|---|---|---|---|
| A1-T1 | 系统基础接口 | ⬜ | 启动/生命周期/调度/存储接口 |
| A2-T1 | Observation Contract | ⬜ | schema + tests |
| A2-T2 | 现实接入接口 | ⬜ | 传感器/手机/摄像头/语音统一接入 |
| A3-T1 | Global Timeline Runtime | ⬜ | 稳定落轴、查询、引用 |
| A3-T2 | 世界实体与关系 Runtime | ⬜ | 人/地点/物品/事件/项目/组织 |
| A3-T3 | 关键词/实体超链接索引 | ⬜ | keyword → entity → timeline → relation → dimension → evidence |
| A4-T1 | Dimension Registry | ⬜ | 动态创建/停用/查询 |
| A4-T2 | Dimension Point / Curve | ⬜ | 时间轴绑定、纵向读取、更新、比较 |
| A4-T3 | Cross-Dimension Query | ⬜ | 横向/纵向/关系查询 |
| A5-T1 | Evidence / Provenance | ⬜ | 来源可追溯 |
| A5-T2 | Confidence Model | ⬜ | source/evidence/claim 分离 |
| A5-T3 | Outcome Verification | ⬜ | prediction → outcome → confidence |
| A6-T1 | Trigger Runtime | ⬜ | 只唤醒，不替 AI 做复杂语义判断 |
| A6-T2 | MODE Runtime | ⬜ | 模式参与上下文，不替代认知 |
| A6-T3 | AI Watch | ⬜ | 条件持续观察、命中后唤醒 |
| A7-T1 | AI Service | ⬜ | 系统级常驻服务 |
| A7-T2 | AI Session + Identity | ⬜ | 每次进入先身份建立 |
| A7-T3 | Cognitive Runtime | ⬜ | wake → identity → cognition → persist |
| A8-T1 | Autonomous Context | ⬜ | 无固定 Dimension 阅读路线 |
| A8-T2 | Cognitive Delta | ⬜ | 只记录真实变化 |
| A8-T3 | Session Handoff | ⬜ | 下一实例可连续认知 |
| A8-T4 | Continuation | ⬜ | 上下文超限自动续接 |
| A9-T1 | Capability Contract | ⬜ | 统一能力描述 |
| A9-T2 | Capability Router | ⬜ | 原生/手机/网络/第三方路由 |
| A9-T3 | Permission / Confirmation | ⬜ | 权限与高风险确认 |
| A9-T4 | Capability Outcome | ⬜ | 执行结果回写 Timeline |
| A10-T1 | Model Gateway | ⬜ | 文字/视觉/语音统一接入 |
| A10-T2 | Model Router | ⬜ | 切换/降级/重试 |
| A11-T1 | AI 能力应用框架 | ⬜ | 领域应用共享核心认知 |
| A11-T2 | 教育应用 | ⬜ | AI 个性化教学 |
| A11-T3 | 社交应用 | ⬜ | 联系人/消息 + 核心认知 + 能力调用 |
| A11-T4 | 兴趣应用 | ⬜ | 专业领域 AI |
| A11-T5 | 购物应用 | ⬜ | 多平台能力调用与比较 |
| A12-T1 | Interaction Runtime | ⬜ | 屏幕/触摸/手势/语音/震动 |
| A12-T2 | AI 输出呈现 | ⬜ | UI 不拥有认知 |
| A13-T1 | Personal Safety OS | ⬜ | 异常/跌倒/生理/无响应升级 |
| A14-T1 | PC 完整 Simulator | ⬜ | 完整主链路可运行 |
| A17-T1 | Cognitive Trace | ⬜ | 结构化诊断、不保存隐藏思维链 |
| A17-T2 | Evaluator | ⬜ | 理解/相关性/帮助/连续性等评分 |
| A17-T3 | Mechanism Optimization | ⬜ | 机制优化而非案例硬编码 |
| A17-T4 | Regression | ⬜ | 新机制不得破坏旧场景 |

## 4. 架构切换记录

### 2026-09-12 · V1.4-r2 完整 OS 架构补丁

- 从“认知运行时优先”的开发路线升级为完整 AIOS 模块架构。
- 新增系统基础、现实接入、观察/世界运行时、核心认知、触发/MODE、AI 服务、能力系统、模型接入、AI 能力应用、人机交互、安全、模拟器/测试完整模块树。
- 明确 AI 服务是系统级统一服务，用户主动和 AI 主动不拆成两个系统。
- 明确 AI 能力应用是专业领域能力，不复制传统手机应用。
- 新增统一能力接口层，负责 AI 与现实世界的执行连接。
- 明确模型是可替换供应层，不属于 AIOS 身份和长期认知。
- 明确 PC/Linux 先完整实现软件，手机和手环通过适配器后接入。
- 关键词/实体超链接索引提升为世界导航基础设施。

## 5. 当前执行状态

**架构已冻结，暂不进入旧 P1-T1 实现。下一步从 A1-T1 开始，按新架构自底向上实现。**

## 6. Agent 强制流程

```text
读取本任务表
 ↓
读取 V1.4-r2 Constitution
 ↓
读取 V1.4-r2 Architecture
 ↓
读取当前模块 Contract / Schema
 ↓
检查实际代码
 ↓
只实现当前任务
 ↓
测试 / 验收
 ↓
更新本任务表
 ↓
Commit 到 aios
 ↓
重新检查实际 Git 状态
```
