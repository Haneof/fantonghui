# AIOS Development Task Ledger

> 状态：ACTIVE
> 唯一开发分支：`aios`
> 唯一 OS 主线：`aios/01_os/`
> 唯一有效宪法：`docs/AIOS_Constitution_V1.4-r3.md`
> 唯一完整架构：`docs/AIOS_Architecture_V1.4-r3.md`
>
> **工程规则：任何代码、Schema、Runtime Contract、架构文档或测试发生修改后，必须同步更新本任务表。没有测试/运行证据和 Commit，不得标记完成。**

## 0. 永久工程规则

1. 只在 `aios` 分支开发。
2. `aios/01_os/` 是唯一 OS 产品实现主线。
3. 不恢复旧 `core/`、旧 Constitution、旧 Runtime 或旧 Schema/Test 作为当前设计。
4. Observation 是事实入口；Global Timeline 是共同时间基准，但不是世界维度的父节点。
5. Dimension 是长期持续生长的认知线，不是固定字段、标签、快照或父子分类树。
6. 基础维度可以预先存在并从空状态开始；没有证据不得强行填值。
7. User/World Dimensions 与 AI Dimensions 可以并行演化，不要求使用相同维度集合。
8. AI 可以根据长期认知价值形成新的维度；系统不写死固定阈值或固定触发规则。
9. 不规定固定 Dimension 阅读顺序或固定思维路线。
10. Runtime 提供能力、边界、权限、上下文容量和连续性，不替 AI 写死认知答案。
11. 节点可以形成局部关联；系统同时提供全局导航与查询能力；具体关联由 AI 根据上下文和证据形成。
12. 产品讨论中的具体例子仅用于解释概念，不得直接固化成 Schema 或硬规则。
13. 世界按真实观察和认知增量稀疏生长，不机械遍历所有维度制造更新。
14. Observation / Evidence / Cognition / Hypothesis / Prediction / Outcome 必须可区分、可追溯、可修正。
15. 时间需要区分发生、发现/观察、记录和认知形成等不同时间语义；未知时不得虚构精确时间。
16. 总结是派生认知，不删除或覆盖底层证据、节点和历史认知。
17. AI 服务统一承载用户主动和 AI 主动，不拆成两个独立大脑。
18. 能力系统是 AI 与现实世界之间的统一执行接口。
19. AI 能力应用不得建立第二套用户记忆、人格、关系或世界模型。
20. UI 不拥有独立 AI、Timeline、Memory、Trigger 或 Cognition。
21. 模型供应商可替换，不得成为 AIOS 身份或长期认知的一部分。
22. Simulator 的 Hidden Expected Intent 对被测 AI 隐藏。
23. PC/Linux 先完整实现软件闭环，手机和手环通过适配器后接入。

## 1. V1.4-r3 总体开发路线

```text
A0 架构基线冻结
 → A1 系统基础
 → A2 现实接入 / Observation
 → A3 Global Timeline / 世界对象 / 节点 / 关系 / 全局导航
 → A4 开放 World Dimensions / Dimension Runtime
 → A5 Evidence / Confidence / Outcome / Provenance
 → A6 Trigger + MODE + Watch
 → A7 Unified AI Service / Session / Identity / Cognitive Runtime
 → A8 Autonomous Context / Delta / Handoff / Continuation
 → A9 Capability System / 权限 / 路由
 → A10 Model Gateway / Router
 → A11 AI Capability Apps
 → A12 Human Interaction
 → A13 Personal Safety OS
 → A14 PC 完整 Simulator
 → A15 手机适配
 → A16 手环适配
 → A17 Cognitive Trace / Evaluator / Mechanism Optimization / Regression
```

## 2. 架构基线任务

| ID | 任务 | 状态 | 验收 |
|---|---|---|---|
| A0-T1 | V1.4-r3 完整 OS 模块树 | ✅ | 架构文档已提交 |
| A0-T2 | V1.4-r3 宪法 | ✅ | r3 为唯一当前入口 |
| A0-T3 | 开放世界维度模型 | ✅ | 维度平行、可演化、不固定认知路线 |
| A0-T4 | 节点 / 局部关联 / 全局导航抽象 | ✅ | 能力边界明确，不把示例固化为规则 |
| A0-T5 | 时间语义与世界坐标 | ✅ | occurrence / observation / record / cognition 可区分 |
| A0-T6 | 稀疏生长与非破坏性总结 | ✅ | 不机械遍历维度，不破坏底层证据 |
| A0-T7 | AI 自身世界与 AI Dimensions | ✅ | AI 可拥有独立长期认知线 |
| A0-T8 | Unified AI Service | ✅ | 用户主动/AI 主动统一 |
| A0-T9 | Capability System | ✅ | 统一现实执行接口 |
| A0-T10 | AI Capability Apps | ✅ | 不建立第二套核心认知 |
| A0-T11 | PC 优先、硬件后适配 | ✅ | 模拟器优先原则冻结 |
| A0-T12 | r2 → r3 文档切换 | ✅ | r2 不再作为当前架构入口 |

## 3. 下一阶段任务

| ID | 任务 | 状态 | 验收 |
|---|---|---|---|
| A1-T1 | 系统基础接口 | ⬜ | 启动/生命周期/调度/存储接口 |
| A2-T1 | Observation Contract | ⬜ | schema + tests |
| A2-T2 | 现实接入接口 | ⬜ | 传感器/手机/摄像头/语音统一接入 |
| A3-T1 | Global Timeline Runtime | ⬜ | 稳定落轴、查询、引用 |
| A3-T2 | 世界实体 / 节点 Runtime | ⬜ | 可引用对象与节点 |
| A3-T3 | Dynamic Relation Runtime | ⬜ | 动态建立/调整/弱化/重组关联 |
| A3-T4 | 全局导航 / 索引 | ⬜ | 跨时间/跨维度发现相关节点 |
| A3-T5 | World Query | ⬜ | 局部上下文 + 全局发现 |
| A4-T1 | Dimension Registry | ⬜ | 基础维度 + 动态维度生命周期 |
| A4-T2 | Dimension Point / Curve | ⬜ | 维度长期生长与纵向读取 |
| A4-T3 | Cross-Dimension Query | ⬜ | 横向/纵向/关系查询 |
| A4-T4 | Dimension Evolution | ⬜ | 创建/调整/弱化/停用/重组能力 |
| A4-T5 | Sparse Cognitive Update | ⬜ | 只在真实认知增量出现时更新 |
| A5-T1 | Evidence / Provenance | ⬜ | 来源可追溯 |
| A5-T2 | Confidence Model | ⬜ | source/evidence/claim 分离 |
| A5-T3 | Outcome Verification | ⬜ | prediction → outcome → confidence |
| A5-T4 | Time Semantics | ⬜ | occurrence/observation/record/cognition 分离 |
| A6-T1 | Trigger Runtime | ⬜ | 只唤醒，不替 AI 做复杂语义判断 |
| A6-T2 | MODE Runtime | ⬜ | 模式参与上下文，不替代认知 |
| A6-T3 | AI Watch | ⬜ | 条件持续观察、命中后唤醒 |
| A7-T1 | Unified AI Service | ⬜ | 系统级常驻服务 |
| A7-T2 | AI Session + Identity | ⬜ | 每次进入建立身份/连续性 |
| A7-T3 | Cognitive Runtime | ⬜ | wake → identity → cognition → persist |
| A8-T1 | Autonomous Context | ⬜ | 无固定 Dimension 阅读路线 |
| A8-T2 | Cognitive Delta | ⬜ | 只记录真实变化 |
| A8-T3 | Session Handoff | ⬜ | 下一实例可连续认知 |
| A8-T4 | Continuation | ⬜ | 上下文超限自动续接 |
| A9-T1 | Capability Contract | ⬜ | 统一能力描述 |
| A9-T2 | Capability Router | ⬜ | 原生/手机/网络/第三方路由 |
| A9-T3 | Permission / Confirmation | ⬜ | 权限与高风险确认 |
| A9-T4 | Capability Outcome | ⬜ | 执行结果回写世界与认知 |
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

### 2026-09-12 · V1.4-r3 开放世界架构升级

- 将世界维度从“Timeline 上的观察视角/时间曲线”进一步明确为长期、平行、独立、可演化的认知线。
- 明确基础维度可以预先存在但从空状态开始。
- 明确时间、地点、环境等也是独立维度，不是其他维度的父节点。
- 引入节点、局部上下文关联与全局导航/索引的概念边界。
- 明确示例只用于解释抽象概念，不得直接成为硬规则。
- 明确 AIOS 提供关联、查询、索引和维度演化能力，但不替 AI 规定最终世界组织方式。
- 明确世界模型按真实认知增量稀疏生长，不机械遍历所有维度。
- 明确发生、观察/发现、记录、认知形成时间的区别。
- 明确总结是派生认知，不删除底层证据和历史节点。
- 明确 AI 自身也可以拥有独立长期认知维度。
- 保留完整 OS 全局模块架构，并与开放世界核心认知统一。

## 5. 当前执行状态

**V1.4-r3 架构基线已冻结。下一步从 A1-T1 开始，按新架构自底向上实现；不得把具体产品示例反向固化成认知硬规则。**

## 6. Agent 强制流程

```text
读取本任务表
 ↓
读取 V1.4-r3 Constitution
 ↓
读取 V1.4-r3 Architecture
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
