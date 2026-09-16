# AIOS Core 详细开发任务拆分（R2 冻结基线）

**版本**：V1.0-draft  
**日期**：2026-09-14  
**依据**：AIOS 宪法 2.0、R1、R2、《AIOS Core 系统架构图与开发规划》《AIOS认知工作台功能规格》《AIOS虚拟世界测试规范》  
**用途**：把架构规格继续拆成可直接进入 Issue / 看板 / AI 编码代理的开发任务。  

> 本文不替代架构文档。原 P01-P11 保留为“任务包索引”，但**不再直接作为开发 Issue**。正式开发以本文的 M0-M8 与 CORE/WORLD/TASK/WB/SIM/TEST 等细粒度任务为准。

---

# 0. 总体执行规则

## 0.1 当前技术形态

第一阶段沿用现有架构决定：

- Core：Python 模块化单体。
- 数据库：SQLite 起步，所有写入通过唯一 Core 写入层。
- AI Worker：不得直接访问数据库，只经 Core 接口读写世界。
- 控制台：浏览器界面，只是同一套工作台能力的人类可视化入口。
- Simulator / Evaluator：独立运行、独立存储、隐藏真值隔离。
- 第一轮只使用虚拟人、模拟输入、模拟行动；不把完整 Linux UI、驱动、实体硬件、应用商店放入关键路径。

## 0.2 完成定义

任何 Issue 只有同时满足以下条件才可关闭：

1. 代码已合并。
2. 对应接口或数据结构已写文档。
3. 单元测试通过。
4. 若属于跨模块能力，至少有一条集成测试。
5. 有可运行证据或可回放案例。
6. 已知限制已记录。
7. 没有违反 R2 冻结契约。

“代码写完”“AI说实现了”“接口能返回200”均不等于完成。

## 0.3 每个 Issue 的固定模板

每个开发 Issue 必须包含：

- 编号
- 目标
- 背景/原因
- 输入
- 输出
- 数据结构
- API/命令
- 前置依赖
- 禁止行为
- 单元测试
- 集成测试
- 验收场景
- 已知限制

## 0.4 R2 冻结项

以下内容不得由开发者在单个 Issue 中自行修改：

- 唯一时间轴与 occurred/learned/recorded 三类时间。
- 稳定对象 ID + Revision 版本机制。
- Observation 默认不直接产生 Wake。
- Claim 的语义类型与知识状态分离。
- EvidenceSet 为一等对象。
- EventAnchor 具有候选、成立、修正、否定、合并、拆分等生命周期。
- Goal 与 Task 分离。
- DimensionDefinition / Membership / Derivation 分离。
- 动态维度 Candidate → Trial → Active 生命周期。
- 第一轮至少支持原始 → 日 → 周 → 月总结。
- 用户世界与 AI 世界共用对象、时间、版本机制。
- 高层认知可以追溯证据。
- 修正通过依赖关系传播，不覆盖历史。
- AI 自主选择工作路径，不被固定思考流水线绑死。
- 未来工作必须任务化，认知写入不得产生无限自唤醒。

如需修改，必须进入正式架构变更流程。

---

# 1. 里程碑总览

| 里程碑 | 目标 | 退出条件 |
|---|---|---|
| M0 世界契约 | 把以后不能轻易改的数据和接口固定 | 核心对象、时间、ID、版本、引用、错误码、协议全部可测试 |
| M1 世界内核 | 世界可以写入、查询、修改、回放 | 候选事件可下钻多维证据，修正后历史仍可重建 |
| M2 时间/唤醒/任务/工作台 | AI 不依赖用户提问也能工作 | 无用户提问时能够被正确唤醒、调查、任务化、行动或沉默 |
| M3 纠错/证据/总结/派生维度 | 世界可以长期生长又可纠正 | 依赖传播、EvidenceSet stale、日周月总结、派生维度最小闭环 |
| M4 一个月虚拟人闭环 | 验证长期连续性 | 同一虚拟人连续30天，任务/认知/结果跨日延续 |
| M5 AI操作经验 | 验证 AI 是否越来越会使用世界 | A/B 证明经验在未见任务上带来收益或明确判定无收益 |
| M6 教育 App | 验证 App 共用认知底座 | 教学会根据跨维度用户状态调整，并有真实学习结果指标 |
| M7 一年运行与强基线 | 验证规模、长期漂移和机制价值 | 与强基线公平比较并形成年度报告 |
| M8 消融与机制裁决 | 决定哪些机制值得保留 | 每个复杂机制有独立收益证据或被简化/后移 |

---

# 2. M0：世界契约冻结

> 目标：先固定“世界是什么”，避免 M2/M3 再返工数据库与 API。

## M0-A 工程骨架与规范

### CORE-001 仓库与模块边界
- 建立 `core/`、`ai_worker/`、`console/`、`simulator/`、`evaluator/`、`tests/`。
- 输出模块依赖图。
- **验收**：AI Worker 代码层面无法直接 import 数据库写入实现。

### CORE-002 配置与环境
- 统一开发/测试配置加载。
- 隐藏真值配置与 Core 配置物理分开。
- **验收**：Core 运行环境中不可读取 evaluator truth 路径。

### CORE-003 错误码契约
- 实现并冻结：`INVALID_ARGUMENT / NOT_FOUND / VERSION_CONFLICT / INCOMPLETE_DATA / STALE_INDEX / BUDGET_EXHAUSTED / PERMISSION_DENIED / DEPENDENCY_INVALID / OUTCOME_UNKNOWN`。
- **验收**：接口不再用任意异常文本表达协议级错误。

### CORE-004 操作审计协议
- 定义 `operation_id / session_id / operation_name / arguments / expected_world_revision / reason / idempotency_key`。
- **验收**：所有修改世界的操作都有可查询审计记录。

## M0-B ID、时间与版本

### WORLD-001 稳定对象ID生成器
- 支持不同对象类型统一生成稳定 ID。
- 名称变化不改变 ID。
- **验收**：未知 P001 后来认定“妈妈”，历史引用仍指向同一 ID。

### WORLD-002 三类时间模型
- 实现 `occurred_at / learned_at / recorded_at`。
- 支持时间点、区间、未知端点。
- **验收**：今天知道“昨天发生的事”时三个时间不混淆。

### WORLD-003 时区规则
- 对 Task、事件、用户本地时间建立明确时区字段。
- **验收**：“明天”按任务所属时区解释。

### WORLD-004 Object Revision
- 每个长期对象修改生成 Revision，不覆盖旧版本。
- **验收**：读取 v1/v2 均可重建。

### WORLD-005 World Revision
- 每次事务提交产生全局世界版本号。
- **验收**：可查询“世界 revision 123 时系统知道什么”。

### WORLD-006 可见性截止时间
- 查询支持 `knowledge_cutoff`。
- **验收**：测试中未来资料即使已经存在于生成器，也无法被当前 Core 查询到。

## M0-C 核心对象契约

### DATA-001 Observation 模型
- 字段：来源、模态、值/引用、时间、质量、主体、版本。
- **禁止**：Observation 本身写“这是分手/运动会/焦虑”。

### DATA-002 Entity 模型
- 稳定 ID、候选身份、别名、状态、身份主张引用。

### DATA-003 Relation 模型
- 两端 Entity、关系类型、有效时间、EvidenceSet/Claim 引用。

### DATA-004 DimensionDefinition 模型
- 定义、主体、数据形态、更新规则、生命周期、维护状态。

### DATA-005 DimensionMembership 模型
- 对象如何挂载到维度，支持同一对象属于多个维度。

### DATA-006 DimensionDerivation 模型
- output/input 维度、事件、Claim、Summary、EvidenceSet、规则、范围、限制、版本。
- **验收**：“学习能力”能追到数学/英语/编程等输入。

### DATA-007 Claim 模型
- 实现 `claimant_id / subject_id / claim_type / knowledge_state / confidence / support/counter evidence / valid_time`。
- 枚举至少包含 FACT、OPINION、BELIEF、DESIRE、INTENTION、PLAN、PREDICTION、PROMISE、PREFERENCE、INFERENCE、HYPOTHESIS。

### DATA-008 EvidenceSet 模型
- 支持明确成员、区间选择器、支持/反对/上下文、覆盖率、缺失、knowledge_cutoff、聚合算法版本。

### DATA-009 EventAnchor 模型
- 支持 CANDIDATE / ACTIVE / RESOLVED / REVISED / REJECTED / MERGED / SPLIT。
- 支持 confidence、primary_claims、EvidenceSet、修订关系。

### DATA-010 Summary 模型
- 主体、维度、time_range、granularity、source revision、EvidenceSet、coverage、missingness、claims、状态。

### DATA-011 Goal 模型
- owner、source_type、status、success_criteria、related dimensions/events/tasks/apps、confidence。

### DATA-012 Dependency 模型
- `dependent_object / dependency_object / dependency_revision / dependency_type`。

### DATA-013 Task 模型
- 先冻结公共字段，不实现完整运行：类型、Goal关联、优先级、时间、依赖、状态、完成/取消条件。

### DATA-014 Wake 模型
- 来源、规则、首末命中、合并次数、证据、优先级、状态。

### DATA-015 Session 模型
- wake、世界快照、操作轨迹、检查点、提交状态。

### DATA-016 Action / Outcome 模型
- Action 和 Outcome 分开；执行ID稳定。
- **验收**：消息已发送 ≠ 用户接受 ≠ 目标改善。

### DATA-017 OperationExperience 模型
- 仅冻结格式：问题类型、路径、条件、成本、结果、遗漏、正反案例、状态。

### DATA-018 ToolProposal 模型
- 缺失能力、场景、现有工具不足、预期收益、验证方法。

## M0-D 引用与一致性

### WORLD-007 SourceRef 统一格式
- 任何对象引用使用统一 ref + revision 结构。

### WORLD-008 引用存在性验证
- 写入时检查引用对象是否存在、版本是否可见。

### WORLD-009 禁止自我证明依赖
- 对“证据依赖”图做最小循环检查。
- 普通语义关系图可有环；证据链不能靠自己证明自己。

### WORLD-010 幂等键规则
- 修改和 Action 执行支持 idempotency key。

### TEST-001 M0 契约测试套件
- 对全部对象做 schema round-trip。
- 验证时间、revision、引用、非法枚举、未知字段策略。

### TEST-002 R2-02 主张语义测试
- “我明天一定考上某学校”必须可拆成说过/相信或预测/现实未知。

### TEST-003 R2-04 区间证据冻结测试
- EvidenceSet 的“过去两周”一周后仍指向原时间窗。

**M0 退出门**：DATA-001~018 与 WORLD-001~010 接口冻结；后续变更必须走架构变更。

---

# 3. M1：共同世界内核

## M1-A 存储与事务

### STORE-001 SQLite 初始化与迁移框架
- 支持 schema version。

### STORE-002 Object Store
- 统一对象写入/读取，不让各模块直接随意建表写数据。

### STORE-003 Revision Store
- 保存所有历史版本。

### STORE-004 World Commit Transaction
- 对象版本、Dependency、审计记录、待投递事件在同一事务提交。

### STORE-005 历史快照读取
- 给定 World Revision 重建对象可见版本。

### STORE-006 重启恢复
- 数据库重启后 revision、待办提交、索引水位保持一致。

## M1-B 基础写入

### INGEST-001 Observation 写入 API
- 支持批量高频写入。
- **禁止**：每条写入自动产生 Wake。

### INGEST-002 数据质量字段
- 缺失、延迟、重复、来源中断状态。

### INGEST-003 重复包处理
- 对完全重复原始包去重但保留计数/来源信息。

### INGEST-004 未知主体处理
- 无法识别的人/物创建稳定未知 Entity。

## M1-C Entity / Relation / Dimension

### ENTITY-001 Entity CRUD + Revision
### ENTITY-002 Alias 别名索引
### ENTITY-003 Identity Claim 绑定
### ENTITY-004 entity.resolve
- 不直接“改ID”，只更新身份主张与展示名。

### REL-001 relation.upsert
### REL-002 关系有效期
### REL-003 关系版本历史

### DIM-001 DimensionDefinition CRUD
### DIM-002 DimensionMembership CRUD
### DIM-003 多维挂载
- 一个 Observation/Event/Claim 可同时挂载多个维度。
### DIM-004 dimension.inspect

## M1-D Claim / Evidence / Event / Goal

### CLAIM-001 claim.create
### CLAIM-002 claim.inspect
### CLAIM-003 claim.revise
### CLAIM-004 claim.compare_versions

### EVID-001 evidence_set.create
### EVID-002 evidence_set.inspect
### EVID-003 明确成员证据集
### EVID-004 区间选择器证据集
### EVID-005 支持/反对/缺失分栏
### EVID-006 EvidenceSet 重建

### EVENT-001 event.create candidate
### EVENT-002 event.expand
### EVENT-003 event.resolve
### EVENT-004 event.revise
### EVENT-005 event.reject
### EVENT-006 event.merge
### EVENT-007 event.split

### GOAL-001 goal.create
### GOAL-002 goal.update
### GOAL-003 goal.query
### GOAL-004 goal.link_task 协议占位

## M1-E 世界查询

### QUERY-001 world.view
- 时间范围 + 主体 + 维度 + knowledge_cutoff。

### QUERY-002 world.zoom
### QUERY-003 world.shift
### QUERY-004 world.select_dimensions
### QUERY-005 world.align
### QUERY-006 world.compare
### QUERY-007 world.detect_changes
- 只做机械变化/统计，不自动写因果。

### QUERY-008 world.search 基础版
- 时间、关键词、实体、关系、对象类型组合筛选。

### QUERY-009 world.follow_links
### QUERY-010 evidence.read
### QUERY-011 evidence.trace
### QUERY-012 “当时已知世界”查询
- 同时使用 learned_at / knowledge_cutoff / revision。

## M1-F 索引与重建

### INDEX-001 时间索引
### INDEX-002 实体/别名索引
### INDEX-003 全文关键词索引
### INDEX-004 维度索引
### INDEX-005 索引水位
- 查询结果返回索引水位和世界 revision。
### INDEX-006 索引重建工具

## M1-G 最小依赖图

### DEP-001 dependency.create
### DEP-002 dependency.inspect
### DEP-003 反向依赖查询
### DEP-004 依赖 revision 校验

## M1-H 开发者最小控制台

### CONSOLE-001 世界对象浏览器
### CONSOLE-002 时间范围选择器
### CONSOLE-003 Entity/Event/Claim 展开
### CONSOLE-004 EvidenceSet 展开
### CONSOLE-005 Revision 历史查看
### CONSOLE-006 操作审计查看

## M1-I 验收

### TEST-010 A01 多维引用不复制事实
### TEST-011 A03 未知实体身份更新后历史引用不断裂
### TEST-012 A05 重建某时刻系统当时知道什么
### TEST-013 R2-03 候选运动会 EvidenceSet 支持/反对/缺失可见
### TEST-014 R2-10 Event 生命周期回放
### TEST-015 M1 贯穿案例：运动会→体育测试修正
- 输入多维观测。
- 建立 CANDIDATE 运动会。
- 新证据到达。
- REVISED 为体育测试。
- 旧版本仍可回放。

**M1 退出门**：世界能写、查、修、回放；AI 尚未接入也能人工通过控制台完成完整世界操作。

---

# 4. M2：时间、唤醒、任务与 AI 认知工作台

## M2-A 虚拟时钟

### TIME-001 离散事件虚拟时钟
### TIME-002 下一观测推进
### TIME-003 下一任务到期推进
### TIME-004 下一观察检查推进
### TIME-005 不越过到期点
### TIME-006 虚拟时间与真实执行耗时分离
### TIME-007 时区与“明天/一年后/月末”规则

## M2-B Wake 触发器

### WAKE-001 数值幅度触发
### WAKE-002 趋势/斜率触发
### WAKE-003 状态切换触发
### WAKE-004 持续时间触发
### WAKE-005 关键词/实体机械匹配触发
### WAKE-006 长时间无更新触发
- 必须区分“持续采样稳定”“来源断流”“非连续采样”。
### WAKE-007 用户主动交互直接 Wake
### WAKE-008 Task 到期直接 Wake
### WAKE-009 Watch 条件命中 Wake
### WAKE-010 Safety 高优先 Wake

### WAKE-011 重复命中合并
### WAKE-012 冷却
### WAKE-013 强度升级重新唤醒
### WAKE-014 新独立来源重新唤醒
### WAKE-015 Wake 队列
### WAKE-016 高优先抢占
### WAKE-017 防队列饿死
### WAKE-018 自唤醒循环保护

### TEST-020 R2-01 高频心率/IMU不逐条唤醒
### TEST-021 R1-06 同关键词重复命中合并
### TEST-022 安全 Wake 不被普通冷却屏蔽

## M2-C Task Center

### TASK-001 Task 状态机
- DRAFT/READY/RUNNING/WAITING_TIME/WAITING_EVIDENCE/WAITING_USER/WAITING_RESULT/BLOCKED/COMPLETED/FAILED/EXPIRED/CANCELLED。

### TASK-002 即时任务
### TASK-003 定时任务
### TASK-004 截止任务
### TASK-005 待办任务
### TASK-006 周期任务
### TASK-007 跟进任务
### TASK-008 观察任务
### TASK-009 验证任务
### TASK-010 后台维护任务
### TASK-011 App任务占位

### TASK-012 task.create
### TASK-013 task.update
### TASK-014 task.query
### TASK-015 task.cancel
### TASK-016 Goal 关联
### TASK-017 completion_condition 检查
### TASK-018 cancel_condition 检查
### TASK-019 recurrence 实例 occurrence_id
### TASK-020 重试/退避/失败去向
### TASK-021 停机后到期恢复策略
### TASK-022 待办盘点时间

### WATCH-001 watch.register
### WATCH-002 机械条件命中
### WATCH-003 语义条件只唤醒 AI，不本地裁决
### WATCH-004 MATCHED / NOT_MATCHED_WITH_SUFFICIENT_DATA / INSUFFICIENT_DATA

### TEST-023 十类任务状态覆盖
### TEST-024 三个月后定时任务未遗忘未重复
### TEST-025 无外部输入但任务到期仍唤醒
### TEST-026 R2-08 Goal与Task分离

## M2-D Action / Outcome

### ACT-001 action.propose
### ACT-002 稳定 execution_id
### ACT-003 模拟消息发送
### ACT-004 模拟提醒
### ACT-005 模拟教育动作
### ACT-006 action.status
### ACT-007 Outcome 写入
### ACT-008 OUTCOME_UNKNOWN 处理
### ACT-009 重试前查询收据
### ACT-010 Action 幂等测试

## M2-E AI 工作台协议

### WB-001 workspace.open
- 返回时间、世界 revision、Wake、紧急事项、当前世界、任务、承诺、未确认认知、AI状态、数据质量、可用能力。

### WB-002 workspace.changes
### WB-003 self.inspect
### WB-004 session.checkpoint
### WB-005 session.finish

### WB-006 当前 Goal 区域
### WB-007 当前 Event / EvidenceSet 区域
### WB-008 Task 面板
### WB-009 Wake 面板
### WB-010 紧急事项面板
### WB-011 数据缺口/过期信息展示

## M2-F AI Worker 与模型

### AI-001 Mock 模型适配器
### AI-002 真实模型适配器接口
### AI-003 结构化工具调用协议
### AI-004 工具参数校验
### AI-005 模型超时与失败
### AI-006 会话预算
### AI-007 会话快照固定
### AI-008 刷新世界 changes
### AI-009 session checkpoint 恢复
### AI-010 不保存私密思维链，只保存可观察操作、引用、判断摘要、决定、结果

## M2-G AI 自主工作目录

### AI-011 唤醒上下文自动提供
### AI-012 AI 可自由选时间范围
### AI-013 AI 可自由选维度
### AI-014 AI 可搜索/下钻/比较
### AI-015 AI 可建立/修正 Claim/Event
### AI-016 AI 可创建 Task/Watch
### AI-017 AI 可选择 ACT_NOW/ASK/SUGGEST/DEFER/WATCH/SILENCE
### AI-018 无认知增量时允许什么都不写

## M2-H 控制台升级

### CONSOLE-020 当前世界面板
### CONSOLE-021 Wake详情
### CONSOLE-022 Task中心
### CONSOLE-023 紧急事项
### CONSOLE-024 时间缩放
### CONSOLE-025 维度开关
### CONSOLE-026 多维对齐
### CONSOLE-027 搜索与下钻
### CONSOLE-028 Action/Outcome收据
### CONSOLE-029 Session 操作回放

## M2-I 最小 Simulator

### SIM-001 隐藏真值存储
### SIM-002 观测生成层
### SIM-003 一天虚拟人状态
### SIM-004 基础活动生成
### SIM-005 传感器/对话/App观测生成
### SIM-006 噪声/延迟/缺失/重复注入
### SIM-007 行动响应模型基础版
### SIM-008 帮助机会登记
### SIM-009 应沉默机会登记
### SIM-010 证据不足机会登记

## M2-J 贯穿验收

### TEST-030 无用户提问主动闭环
- 虚拟世界自然产生变化。
- 机械触发 Wake。
- AI自主查看资料。
- 建立合理认知。
- 选择帮助或沉默。
- 若需未来继续，创建 Task。

### TEST-031 R1-09 主动帮助并完成跟进
### TEST-032 W10 AI选择沉默并记录依据
### TEST-033 A06 重启/重试不重复行动
### TEST-034 W12 模型中断后从 checkpoint 接续

**M2 退出门**：系统在用户完全不提问的情况下能完成“资料→Wake→AI调查→决定→Task/Action→等待结果”的最小闭环。

---

# 5. M3：纠错、证据失效、多尺度总结、派生维度

## M3-A 依赖传播与纠错

### FIX-001 Claim 修订后反向依赖查找
### FIX-002 Entity 身份变更后反向依赖查找
### FIX-003 Event REVISED/REJECTED 传播
### FIX-004 Summary stale 标记
### FIX-005 DimensionDerivation stale 标记
### FIX-006 Goal 关键依赖 stale 标记
### FIX-007 未执行 Task 暂停复核
### FIX-008 已执行 Action 不回滚历史，只追加解释/补救
### FIX-009 生成去重复核任务
### FIX-010 修正误伤保护

### TEST-040 A04 底层主张修正找到受影响认知和任务
### TEST-041 R2-11 运动会修正为体育测试后下游正确复核
### TEST-042 不相关对象不被误改
### TEST-043 R2-15 修正不产生无限 Task/Wake

## M3-B EvidenceSet 生命周期

### EVID-020 stale 判定
### EVID-021 rebuild
### EVID-022 迟到 Observation 导致 stale
### EVID-023 底层 Revision 变化导致 stale
### EVID-024 成员覆盖率重算
### EVID-025 counter evidence 新增
### EVID-026 EvidenceSet 版本对比

### TEST-044 R2-03 可复核证据集合
### TEST-045 R2-24迟到数据重审

## M3-C Summary 最小体系

### SUM-001 日总结生成协议
### SUM-002 周总结生成协议
### SUM-003 月总结生成协议
### SUM-004 Event 维度总结
### SUM-005 数值/频率维度总结
### SUM-006 认知/学习类维度总结
### SUM-007 summary.expand
### SUM-008 月→周→日→事件→证据下钻
### SUM-009 允许月直接跳原始相关事件
### SUM-010 Summary stale
### SUM-011 Summary 重算
### SUM-012 保留旧 Summary Revision

### TEST-046 R2-12 原始→日→周→月
### TEST-047 R2-13重算不删除原始历史
### TEST-048 R2-14 AI可绕过总结层直接下钻

## M3-D 动态维度生命周期

### DIM-020 Candidate 创建
### DIM-021 Candidate 说明字段
### DIM-022 Trial 工程检查
### DIM-023 资源预算检查
### DIM-024 Trial 运行记录
### DIM-025 Active 晋级规则接口
### DIM-026 Low Activity
### DIM-027 Dormant
### DIM-028 Reactivate
### DIM-029 Merge
### DIM-030 Split
### DIM-031 Reject
### DIM-032 历史引用保留

### TEST-049 R2-06 Candidate不自动Active
### TEST-050 R2-07低频高价值维度不误清理

## M3-E DimensionDerivation

### DER-001 dimension.derivation.create
### DER-002 dimension.derivation.inspect
### DER-003 dimension.derivation.revise
### DER-004 dimension.derivation.trace
### DER-005 输入维度/事件/Claim/Summary绑定
### DER-006 时间范围与适用scope
### DER-007 counterexample
### DER-008 输入失效→派生维度复核

### TEST-051 R2-05学习能力下钻到输入维度和EvidenceSet

## M3-F Goal Progress

### GOAL-020 goal.assess_progress
### GOAL-021 明确Goal与推断Goal显示差异
### GOAL-022 Goal依赖修正
### GOAL-023 success criteria 检查
### GOAL-024 Goal状态历史

### TEST-052 R2-09推断目标与用户明确目标分离
### TEST-053 推断目标被用户否认后任务进入停止/复核

## M3-G AI 自身世界最小闭环

### SELF-001 AI帮助记录进入AI主体世界
### SELF-002 用户拒绝/接受/无回应分别记录
### SELF-003 AI误判修正记录
### SELF-004 AI承诺与Task关联
### SELF-005 AI当前开放问题
### SELF-006 不要求每次Wake都生成“反思”占位内容

## M3-H M3 贯穿验收

### TEST-054 “A是谁”身份纠错完整案例
- 最初 A 未知。
- AI形成错误身份候选。
- 后续用户明确纠正。
- Event/Summary/Task/派生维度依赖被发现。
- 不相关历史不被修改。
- AI世界保留本次错误与修正结果。

### TEST-055 一个月时间缩放演示
- 月总结→某日→某事件→某句原话。

**M3 退出门**：世界已经具备“会错、会改、不会覆盖历史；会总结、会下钻；会产生试用维度、会淘汰无效维度”的核心能力。

---

# 6. M4：同一虚拟人一个月闭环

> 目标：不再只测单次案例，开始验证长期连续性。

### SIM-020 月度虚拟人生成器
### SIM-021 同一人物连续30天状态演化
### SIM-022 缓慢趋势生成
### SIM-023 同一问题重复出现
### SIM-024 身份/关系错误后纠正
### SIM-025 跨周跟进
### SIM-026 用户拒绝导致局部策略变化
### SIM-027 App间资料共享模拟
### SIM-028 任务延期/撤销
### SIM-029 数据源中断与恢复
### SIM-030 一个动态维度候选场景

### EVAL-001 机会召回率
### EVAL-002 介入精确率
### EVAL-003 不必要打扰率
### EVAL-004 净帮助效用
### EVAL-005 主张正确性
### EVAL-006 Evidence 支持率
### EVAL-007 不确定性校准
### EVAL-008 修正覆盖率/误伤率
### EVAL-009 Task完成/遗漏/重复执行
### EVAL-010 世界操作查询次数与无关资料比例

### BASE-001 B0 最近上下文基线
### BASE-002 B1 长上下文+滚动总结基线
### BASE-003 B2 强混合检索记忆基线
### BASE-004 O 证据充分参考组

### TEST-060 V01~V20 批量运行
### TEST-061 V21~V30 批量运行
### TEST-062 固定历史回放实验
### TEST-063 行动影响世界闭环实验

**M4 退出门**：同一虚拟人的昨天任务、认知和结果会真实影响今天，不是30个独立日。

---

# 7. M5：AI 操作经验

> 目标：验证“AI越来越会使用自己的世界”是否真正存在收益。

### EXP-001 experience.record
### EXP-002 experience.search
### EXP-003 适用条件
### EXP-004 正例/反例
### EXP-005 成本统计
### EXP-006 遗漏统计
### EXP-007 Candidate Experience
### EXP-008 Validated Experience
### EXP-009 Expired Experience
### EXP-010 Rejected Experience
### EXP-011 使用经验时保留来源
### EXP-012 经验不能变成固定强制思考路线

### EXP-013 恋爱经历查询实验：通读全人生
### EXP-014 恋爱经历查询实验：关键词
### EXP-015 人物关系→事件→关键词补充
### EXP-016 相似任务复用
### EXP-017 表面相似但条件不同反例
### EXP-018 经验失效案例

### TEST-070 操作经验 A/B 分叉
- 同一世界快照，一组可读Experience，一组不可读。
- 比较证据覆盖、调用量、遗漏、结果。

**M5 退出门**：操作经验必须在未见任务上有可测收益；若无收益，标记“机制尚未得到支持”，不得因为概念好听强保留。

---

# 8. M6：教育 App 与跨维度适配

> 目标：验证 App 是“同一 AI 的专业场所”，不是另一个独立AI。

## M6-A App 最小协议

### APP-001 AppManifest 最小对象
- domain、goal、tools、produced_data、requested_context、task_types。

### APP-002 Education App 注册
### APP-003 Math 场景
### APP-004 English 场景
### APP-005 App不得建立独立用户Memory

## M6-B 教学工具

### EDU-001 题目实体
### EDU-002 作答Observation
### EDU-003 耗时Observation
### EDU-004 错误类型Claim
### EDU-005 讲解方式记录
### EDU-006 知识点掌握Goal/Claim
### EDU-007 教学Task
### EDU-008 复测Task

## M6-C 个性化适配

### EDU-009 数学水平影响解法选择
### EDU-010 睡眠/疲劳影响课程强度
### EDU-011 工作负荷影响教学时长
### EDU-012 历史讲解效果影响新讲解
### EDU-013 用户拒绝/疲劳时允许放假或缩短
### EDU-014 不用用户未掌握方法解释

## M6-D 跨 App/跨维度迁移

### EDU-015 数学发现视觉化学习偏好
### EDU-016 编程教学复用候选认知
### EDU-017 迁移先验证，不机械泛化

## M6-E 评估

### EVAL-020 初次正确率
### EVAL-021 未见同类题迁移
### EVAL-022 延迟保持
### EVAL-023 学习时间
### EVAL-024 是否适配状态
### EVAL-025 是否过早直接给答案
### EVAL-026 用户喜欢与真正学会分开评分

**M6 退出门**：在相同题目下，AIOS教师能因不同用户世界做出不同且可解释的教学策略，并在后续学习结果上验证收益。

---

# 9. M7：一年运行与强基线

### SIM-040 年度生成器
### SIM-041 季节/阶段变化
### SIM-042 长期Goal
### SIM-043 几个月前Task到期
### SIM-044 关系演化
### SIM-045 长期学习增长/倒退
### SIM-046 历史经验失效
### SIM-047 同名/别名冲突
### SIM-048 迟到证据修改旧认知
### SIM-049 模型中断/恢复/切换
### SIM-050 高密度与长低变化区间

### SCALE-001 70万级Observation写入测试
### SCALE-002 100万级查询测试
### SCALE-003 索引重建测试
### SCALE-004 Summary增长测试
### SCALE-005 Task长期恢复测试
### SCALE-006 世界revision增长测试

### BASE-020 机制隔离赛道
### BASE-021 自主调度赛道
### BASE-022 相同模型/预算控制
### BASE-023 成本效果曲线
### BASE-024 第二模型复核

### REPORT-001 一年实验报告
- 主动帮助、纠错、任务、教育、成本、存储、失败、维度价值、经验价值。

**M7 退出门**：能够诚实回答“AIOS是否在相同资源或明确成本差异下优于强记忆基线”。

---

# 10. M8：消融与机制裁决

### ABL-001 去掉多尺度总结
### ABL-002 去掉实体消歧/关联导航
### ABL-003 去掉依赖传播
### ABL-004 去掉AI操作经验
### ABL-005 去掉动态维度
### ABL-006 去掉自主观察/跟进
### ABL-007 去掉跨App共享认知
### ABL-008 去掉AI自身世界中的帮助经验

### DECIDE-001 每个机制收益/成本表
### DECIDE-002 复杂度无收益机制简化建议
### DECIDE-003 宪法后续修订候选
### DECIDE-004 下一阶段是否进入真实用户/真实设备原型

**M8 退出门**：不再靠“感觉这个机制很高级”保留模块；每个复杂机制要么有证据支持，要么明确延后、简化或删除。

---

# 11. 原 P01-P11 与新任务的对应关系

| 原任务包 | 新任务归属 | 处理方式 |
|---|---|---|
| P01 对象协议/时间/错误码 | M0 CORE/WORLD/DATA | 保留思想，拆细 |
| P02 世界存储/版本/快照 | M1 STORE/WORLD | 拆细，不直接开发P02 |
| P03 虚拟时钟/可见性/一天生成器 | M2 TIME/SIM | 拆细 |
| P04 维度/实体/索引/时间镜头 | M1 DIM/ENTITY/QUERY/INDEX | 拆细 |
| P05 任务/触发/紧急 | M2 TASK/WAKE | 拆细 |
| P06 工作台/接续/模型 | M2 WB/AI | 拆细 |
| P07 控制台/回放/模拟能力 | M1/M2 CONSOLE/ACT | 拆细 |
| P08 认知/事件/总结/纠错 | M1/M3 CLAIM/EVENT/SUM/FIX | 被R2明显重构 |
| P09 AI经验/维度生命周期/工具提案 | M3/M5 | 后移验证，不删除 |
| P10 教育/月年生成/闭环 | M4/M6/M7 | 拆成三个里程碑 |
| P11 强基线/盲测/消融 | M4/M7/M8 | 从早期就建设测试基础 |

结论：**原 P01-P11 不废弃，但只作为目录和历史规划，不作为直接开发任务。**

---

# 12. 第一批实际开工队列

R2确认后，不建议一次把全部 M0-M8 派出去。第一批只开以下任务：

1. CORE-001 仓库与模块边界
2. CORE-003 错误码契约
3. CORE-004 操作审计协议
4. WORLD-001 稳定对象ID
5. WORLD-002 三类时间
6. WORLD-004 Object Revision
7. WORLD-005 World Revision
8. WORLD-006 Knowledge Cutoff
9. DATA-001 Observation
10. DATA-007 Claim
11. DATA-008 EvidenceSet
12. DATA-009 EventAnchor
13. DATA-011 Goal
14. DATA-006 DimensionDerivation
15. DATA-012 Dependency
16. TEST-001 M0 契约测试
17. TEST-002 主张语义测试
18. TEST-003 区间证据冻结测试

这些是第一批真正影响后面所有模块的数据契约。它们没有冻结前，不应大规模并行开发工作台、任务、总结和教育 App。

---

# 13. 项目经理看板规则

建议使用四列主状态：

```text
BACKLOG → READY → IN PROGRESS → REVIEW → DONE
```

额外状态：

- BLOCKED：被前置任务阻塞。
- NEEDS_ARCH_CHANGE：发现需要修改R2冻结契约。
- NEEDS_REPRO：失败无法稳定复现。
- REJECTED：实现不符合规格，退回。

任何 `NEEDS_ARCH_CHANGE` 不得由编码人员自己顺手修改 schema 后继续开发。

---

# 14. 每个里程碑必须留下的项目资产

每个 M 结束时必须产出：

1. 可运行代码版本和提交编号。
2. 当前 schema 文档。
3. 当前 API 文档。
4. 自动测试结果。
5. 至少一个贯穿案例回放。
6. 当前性能/成本数据。
7. 已知失败列表。
8. 与宪法/R1/R2 的差异说明。
9. 下一阶段可以并行开的任务。
10. 是否需要正式修宪的建议。

---

# 15. 当前项目决策

1. 不按原 P01-P11 直接开发。
2. 原 P01-P11 作为高层索引保留。
3. 以 R2 为冻结基线，使用本文作为详细 Issue 母表。
4. 第一批只开发 M0 世界契约。
5. M0 冻结前，不允许为赶速度跳到完整工作台或教育 App。
6. 从 M0 开始同步建立测试，不允许“先全部开发，最后再测试”。
7. 每个阶段均以验收场景退出，不以代码量或完成百分比退出。

