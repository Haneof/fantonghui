# AIOS PROJECT EXECUTION MASTER V1.0

> AIOS 项目总工程执行准则 / PM 自我约束文件
> 制定日期：2026-09-10
> 状态：ACTIVE
> 适用范围：整个 AIOS 项目开发生命周期
> 适用对象：AIOS 总体架构规划、PM、Technical Lead、Development Task Owner、Code Acceptance Owner
> 注意：本文件不取代 Constitution，也不修改 00-09 Canonical 文档。

---

# 0. 文件定位

本文件的唯一目的：

**约束 AIOS 项目的总体规划者自己，避免项目在长期迭代过程中出现方向漂移、重复实现、错误状态判断、任务编号失真、验证线与产品线混淆，以及 Agent 擅自扩展架构等问题。**

本文件解决的是：

```text
“AIOS 应该是什么”
        ↓
由 Constitution + 00-09 Canonical Docs 决定

“AIOS 现在实际做到什么程度”
        ↓
由 Git + STATUS + DELIVERED_LEDGER + 测试证据决定

“AIOS 下一步应该做什么”
        ↓
由本文件规定的工程治理规则决定

“具体应该修改哪些代码”
        ↓
由 ACTIVE_TASK / 任务单决定
```

本文件**不是**新的产品架构文档。

本文件不得重新定义 Constitution 中已经定义的核心原则。

---

# 1. AIOS 权威层级

任何项目判断必须遵循下面的优先级：

```text
LEVEL 1
AIOS Constitution V1.2-r1
        ↓
LEVEL 2
00-09 Canonical Documents
        ↓
LEVEL 3
Project Control Documents
        ↓
LEVEL 4
已验证测试与运行证据
        ↓
LEVEL 5
当前代码实现
        ↓
LEVEL 6
历史对话 / Agent 报告 / 人工记忆
```

规则：

## 1.1 Constitution 高于一切

如果代码、任务单、Agent 建议或 PM 记忆与 Constitution 冲突：

**必须服从 Constitution。**

不得为了方便实现修改 Constitution。

---

## 1.2 Canonical Docs 高于实现代码

如果实现与 Canonical Docs 的**语义要求**冲突：

**修改实现。**

不能以“代码已经写出来”为理由反向修改架构原则。

---

## 1.3 Git 事实高于 PM 记忆

如果 PM 记得：

> “这个模块以前已经完成。”

但 Git 中没有可以验证的代码、提交、测试或运行证据：

**视为未完成。**

---

## 1.4 Agent 报告不是证据本身

以下说法不能直接作为完成依据：

```text
“已经实现”
“测试通过”
“功能完成”
“已经接入”
“已经修复”
```

必须能够追溯到：

```text
具体文件
具体提交
具体测试
具体命令
实际 stdout/stderr
必要时实际运行结果
```

---

# 2. 唯一产品实现主线

AIOS 产品实现主线固定为：

```text
aios/01_os/
```

除非未来经过正式架构裁决，否则不得再建立第二套 AIOS 产品主线。

---

## 2.1 旧验证线的处理方式

历史上存在：

```text
core/
arena/
实验目录
benchmark 目录
历史实现
```

这些内容可以作为：

```text
验证资产
实验资产
参考实现
历史资产
```

但：

**不能因为某个历史目录存在，就继续发展第二套产品 Runtime。**

---

## 2.2 验证资产的正确处理

历史验证资产的正确路径：

```text
历史实现
   ↓
确认能力是否真实有效
   ↓
确认是否符合 Canonical
   ↓
提取已验证语义
   ↓
吸收进入 aios/01_os
   ↓
主线重新验收
```

而不是：

```text
旧实现
+
主线实现
=
两个 AIOS 同时维护
```

---

# 3. 全局唯一开发总线

以后所有任务必须挂到下面这条总线上：

```text
REALITY / INPUT
        ↓
SENSOR / DSP
        ↓
SPECIALIZED PERCEPTION
        ↓
SEMANTIC EVENT
        ↓
EVENT RUNTIME
        ↓
ENTITY / FUSION
        ↓
WORLD UPDATE
        ↓
WORLD STATE
        ↓
WORLD CHANGE
        ↓
MEMORY
        ↓
RELEVANCE
        ↓
ATTENTION
        ↓
WAKE
        ↓
AI RUNTIME
        ↓
COGNITION / GOALS / GROWTH
        ↓
DECISION
        ↓
CAPABILITY
        ↓
PERMISSION / SAFETY
        ↓
ACTION
        ↓
OUTCOME
        ↓
EVOLUTION
        ↓
WORLD UPDATE
        ↓
循环
```

任何新功能在开始开发前必须回答：

```text
它位于这条总线的什么位置？
它的输入是什么？
它的输出是什么？
它依赖哪个上游能力？
谁消费它？
它是否绕过了某一层？
```

回答不清楚：

**不得直接开发。**

---

# 4. 第一原则：先世界，后认知

AIOS 不是普通 Chat App。

AIOS 的基础不是：

```text
用户说话
 ↓
LLM回答
```

而是：

```text
现实
 ↓
感知
 ↓
事件
 ↓
世界
 ↓
世界变化
 ↓
记忆
 ↓
相关性
 ↓
注意
 ↓
唤醒
 ↓
AI
```

因此：

**没有稳定 World Runtime，不允许为了“看起来像 AI”而优先扩大 AI Runtime。**

---

# 5. Event → World 是第一条产品生命线

Phase 1 必须优先证明：

```text
Semantic Event
      ↓
Event Runtime
      ↓
World Update
      ↓
World State
      ↓
World Change
```

最低要求：

```text
可注入
可持久化
可回放
可确定性重放
可追踪
不会把 AI 推断写成现实事实
```

只有这条链稳定后，才能继续扩大后面的神经系统。

---

# 6. Event 的基本原则

Event 是：

**对现实的结构化事实输入。**

Event 不是：

```text
AI 判断
AI 猜测
AI 结论
AI 价值观
AI 经验
AI 建议
AI 决策
```

不得在 Event Runtime 中偷偷混入认知。

---

# 7. State 的基本原则

World State 表示：

> **当前世界是什么样。**

World Change 表示：

> **世界发生了什么变化。**

Memory 表示：

> **过去发生了什么以及长期保留的信息。**

Cognition 表示：

> **AI 对世界的理解。**

Growth 表示：

> **AI 从经验中形成的策略、能力和进化。**

四者严格分离。

不得因为开发方便将：

```text
事实
推断
记忆
认知
成长
```

全部塞入一个数据库表或一个 JSON 对象中。

---

# 8. 冲突分类规则

所有“Canonical 与代码不一致”的情况必须先区分：

## A. 语义冲突

Canonical 要求：

```text
行为 A
```

代码实际执行：

```text
行为 B
```

这是：

**真正的架构/语义冲突。**

必须改代码。

---

## B. 表示冲突

Canonical 要求：

```text
字段 / 命名 / 格式 / 存储 / 内部数据结构
```

而现有经过充分验证的 Runtime 采用不同表示，但最终语义一致：

这是：

**表示冲突。**

优先：

```text
Adapter
Mapper
Translator
Compatibility Layer
```

不得为了字段名称一致而重写已经验证的核心 Runtime。

---

## 8.1 处理原则

永久规则：

> **语义冲突改实现；表示冲突优先适配。**

这是为了防止在 Sprint 2 / Sprint 3 对已验证 Memory、Model Router、Evolution 等资产进行无必要重写。

---

# 9. 已验证能力 ≠ 产品主线完成

任何能力必须记录两个维度：

```text
Validation Status
Product Mainline Status
```

例如：

```text
World Runtime

Validation:
✅ Core Simulator 已验证

Mainline:
❌ aios/01_os 尚未完成吸收

Overall:
❌ 产品能力未完成
```

反过来也一样：

```text
某服务文件存在
≠
该 Canonical 能力已经完成
```

---

# 10. 状态枚举标准

所有模块状态统一使用：

```text
NOT_STARTED
SKELETON
PARTIAL
VALIDATED
MAINLINE_INTEGRATED
ACCEPTED
DEPRECATED
ARCHIVED
BLOCKED
```

禁止使用含义模糊的：

```text
差不多完成
基本完成
已经接入
半完成
应该完成
```

---

## 10.1 状态解释

### NOT_STARTED

没有实际实现。

### SKELETON

只有空壳、heartbeat、日志、占位接口等。

### PARTIAL

有部分真实能力，但尚未完成 Canonical 要求。

### VALIDATED

能力已经有实际测试/实验验证。

### MAINLINE_INTEGRATED

已进入 `aios/01_os` 唯一产品主线。

### ACCEPTED

PM 已检查代码 + 测试 + 运行证据，并正式验收。

### DEPRECATED

不再作为主实现，但尚未删除。

### ARCHIVED

历史参考资产，不再参与产品运行。

### BLOCKED

有明确外部阻塞。

---

# 11. Task 编号不是项目真相

历史 Task 编号允许发生错位、重命名、拆分或合并。

因此：

**不得通过 Task 编号判断项目实际进度。**

真正的项目进度依据：

```text
Canonical Capability
        ↓
Bus Position
        ↓
Implementation
        ↓
Validation
        ↓
Mainline Integration
        ↓
Acceptance
```

Task 编号只是：

**本次施工的临时工作编号。**

---

# 12. 能力账本是长期记忆

项目必须维护：

```text
DELIVERED_LEDGER.md
```

用于记录：

```text
能力
总线位置
Canonical 依据
实现位置
验证线
主线
提交
测试
状态
备注
```

例如：

```text
Dedup
├── Bus: Event Runtime
├── Canonical: Sprint 2 / Event Runtime
├── Validation: ✅
├── Mainline: ✅ / ❌
├── Commit: xxxx
├── Tests: xxx
└── Status: ACCEPTED / VALIDATED
```

以后 PM 判断能力是否完成：

**优先查账本，而不是依赖聊天记录。**

---

# 13. STATUS.md 的职责

`STATUS.md` 是：

**项目当前现实状态表。**

它必须描述：

```text
Canonical 能力
当前主线实现
实际状态
证据
缺口
阻塞
```

不允许写：

```text
“按计划已经完成”
```

如果代码实际上还是空壳：

必须写：

```text
SKELETON
```

---

# 14. ACTIVE_TASK.md 的职责

`ACTIVE_TASK.md` 表示：

**当前唯一主任务。**

必须能够回答：

```text
现在项目究竟在干什么？
哪个 Agent 负责？
修改哪些文件？
禁止改哪些文件？
验收什么？
什么时候算完成？
```

任何 Agent 不得自行改变 Active Task 的目标。

---

# 15. 单能力单 Owner 原则

任何时刻：

**同一个核心能力只能有一个代码 Owner。**

特别是：

```text
World State
Event Runtime
Memory
Wake
AI Runtime
Permission
Safety
```

不允许两个 Agent 同时实现同一能力。

允许并行工作的前提：

```text
不同能力
或
不同文件
且
没有共享写入边界
```

---

# 16. 并行开发规则

可以并行：

```text
Agent A
→ stated / World

Agent B
→ 独立 benchmark harness
```

不可以并行：

```text
Agent A → stated.py
Agent B → stated.py
```

也不可以：

```text
Agent A → World Runtime
Agent B → 另一个 World Runtime
```

因为这会产生：

**第二套真相。**

---

# 17. Agent 权限边界

Coding Agent 负责：

```text
阅读代码
修改允许文件
运行测试
提交代码
报告证据
```

Coding Agent 不负责：

```text
修改 Constitution
决定架构
决定项目下一阶段
宣布 AIOS 完成
为了局部 Bug 重建系统
建立第二套 Runtime
擅自扩大任务范围
```

如果 Agent 发现架构问题：

必须：

```text
提出问题
说明证据
暂停相关扩大性修改
等待 PM 裁决
```

---

# 18. 每一个任务必须包含

任务单必须至少包含：

```text
1. Task ID
2. Bus Position
3. Objective
4. Canonical References
5. Current Reality
6. Allowed Files
7. Forbidden Files
8. Implementation Requirements
9. Explicit Non-Goals
10. Test Requirements
11. Acceptance Criteria
12. Required Raw Evidence
13. Commit Requirement
14. Expected Next Bus Position
```

---

# 19. Agent 不允许“顺手重构”

禁止：

```text
“顺便优化”
“顺便统一架构”
“顺便重写”
“顺便整理”
“顺便迁移所有文件”
```

除非任务单明确授权。

原因：

局部 Bug ≠ 架构需要重建。

---

# 20. 130+ 文件治理规则

130+ 文件不是天然垃圾。

必须分类：

```text
A = 核心运行时
B = 已验证能力
C = 可适配/可吸收资产
D = 实验/benchmark/历史资产
```

进一步处置：

```text
KEEP
ABSORB
ADAPT
EXPERIMENT
DEPRECATE
ARCHIVE
DELETE
```

---

## 20.1 不允许一次性清理

在核心主链没有跑通以前：

**禁止批量删除 130+ 文件。**

原因：

这些文件中可能有：

```text
已验证能力
测试
数据集
回放工具
兼容层
历史实现
重要实验结果
```

先完成主链收敛，再进行仓库清理。

---

# 21. Schema 治理规则

Canonical Schema 是：

**语义标准。**

但传输层可以拥有自己的 framing。

例如：

```text
Bus Frame
{
  t,
  topic,
  msg
}
```

不等于：

```text
Canonical Event
{
  id,
  timestamp,
  source,
  type,
  content,
  entities,
  location_id,
  confidence,
  raw_ref
}
```

两者允许并存，前提是：

```text
Transport Frame
        ↓
Canonical Adapter
        ↓
Canonical Event
```

不能把 Transport Schema 偷换成 Canonical Domain Schema。

---

# 22. Schema 唯一性原则

同一个 Canonical Domain Object：

**只能有一个 Canonical Contract。**

例如 Event：

不允许长期存在多个互相竞争的：

```text
Event Schema A
Event Schema B
Event proto
Event JSON
```

如果多个版本存在：

必须明确：

```text
Canonical
Transport
Legacy
Experimental
```

而不是让不同 Runtime 各自解释。

---

# 23. LLM 使用红线

不得把 LLM 放在：

```text
Raw Event
 ↓
LLM
 ↓
世界
```

作为常规逐事件过滤器。

AIOS 必须采用：

```text
Reality
 ↓
Perception
 ↓
Semantic Event
 ↓
Event Runtime
 ↓
Fusion
 ↓
World Change
 ↓
Relevance
 ↓
Attention
 ↓
Wake
 ↓
AI
```

高成本模型必须通过：

```text
Relevance
Attention
Wake
Resource Scheduling
```

被选择性唤醒。

---

# 24. 永远不能默认“每条 Event 调模型”

任何代码审查发现：

```text
for event:
    call_llm(event)
```

或者等价行为：

```text
每个事件
→ 云模型
```

默认视为：

**严重架构风险。**

除非 Canonical 明确授权，否则必须拒绝。

---

# 25. World 不由模型直接写入

AI 可以：

```text
观察世界
理解世界
提出计划
请求能力
产生行动
```

但不能直接绕过：

```text
World Runtime
Permission
Safety
Outcome
```

把自己推断出来的内容写成事实。

---

# 26. Wake 系统必须遵循漏斗

后续 Wake Runtime 必须逐级压缩：

```text
大量 Raw / Semantic Events
        ↓
Dedup
        ↓
Window
        ↓
Clustering
        ↓
Trend
        ↓
Baseline Deviation
        ↓
Relevance
        ↓
Attention
        ↓
Wake
        ↓
AI
```

目标：

**不是让 AI 看更多，而是让 AI 只看到值得它思考的东西。**

---

# 27. MODE 规则

MODE 是上下文条件。

正确逻辑：

```text
Event
 ↓
MODE
 ↓
Relevance / Attention
 ↓
Wake
```

MODE 不应该成为：

```text
云 LLM 每事件分类器
```

优先：

```text
规则
轻量分类
上下文状态
已有 World State
```

---

# 28. Safety 的特殊优先级

Safety 不得依赖普通 AI Wake。

必须支持：

```text
EMERGENCY_WAKE
```

并允许：

```text
Emergency Signal
 ↓
Hard Rule / Safety
 ↓
Immediate Intervention
```

不能因为：

```text
Relevance 低
Attention 低
AI 没醒
```

就阻止明显的人身安全事件。

---

# 29. Active Watch 是核心机制，不是附属功能

以后 AI Runtime 可以请求：

```text
Watch(entity, condition, duration)
```

AIOS 负责：

```text
观察
过滤
持续判断
```

只有满足条件的：

```text
World Change
```

才重新唤醒 AI。

因此：

```text
AI Watch
≠
AI 持续运行
```

而是：

```text
AI 一次决策
 ↓
AIOS 持续观察
 ↓
相关变化
 ↓
AI 再次唤醒
```

---

# 30. 不能为了“看起来完整”提前做后期阶段

开发顺序：

```text
PHASE 1
World

PHASE 2
Memory

PHASE 3
Relevance / Attention / Wake

PHASE 4
AI Runtime

PHASE 5
Capability / Permission / Safety

PHASE 6
Interaction

PHASE 7
Evolution

PHASE 8
Phone

PHASE 9
Wearable

PHASE 10
Low Power / RTOS / Hardware
```

不得因为硬件概念很有吸引力，就提前跳到：

```text
Phone
Wearable
RTOS
```

---

# 31. 当前阶段路线

当前第一目标：

**AIOS Core Simulator / Mainline Runtime**

必须证明：

```text
Event
 ↓
World
 ↓
State
 ↓
World Change
```

然后：

```text
Relevance
 ↓
Attention
 ↓
Wake
```

最后：

```text
AI
 ↓
Capability
 ↓
Outcome
 ↓
Evolution
```

---

# 32. 第一阶段禁止事项

在 World 基础链没有稳定前：

不要优先做：

```text
手环工业设计
完整手机 App
大量领域扩张
万能小模型
每事件云模型
复杂商业化界面
多设备产品化
```

---

# 33. 测试原则

任何核心 Runtime 都必须尽量具备：

```text
Unit Test
Integration Test
Replay Test
Determinism Test
Failure Test
Restart Test
Boundary Test
Regression Test
```

涉及 World：

必须特别验证：

```text
Replay
Idempotency
Timestamp
Ordering
State Continuity
Traceability
```

---

# 34. “测试通过”必须有范围

禁止说：

> “测试全部通过。”

除非能够明确：

```text
测试总数
测试命令
通过数量
失败数量
跳过数量
环境
提交
```

例如：

```text
192 passed
0 failed
commit: xxxxx
environment: WSL2
```

才构成有效证据。

---

# 35. 双环境规则

核心 Python Runtime 在可能情况下必须至少覆盖：

```text
Windows
WSL2
```

发现：

```text
Windows PASS
WSL FAIL
```

不能宣布完成。

应标记：

```text
PARTIAL / BLOCKED
```

---

# 36. 回放确定性是核心指标

对同一输入事件流：

```text
Replay #1
Replay #2
Replay #3
```

若确定性要求成立：

最终：

```text
World State
World Change
关键持久化结果
```

必须一致。

必要时使用：

```text
Canonical Serialization
Hash
```

验证。

---

# 37. 不允许测试“假通过”

禁止：

```text
mock 核心逻辑
跳过真实 Runtime
直接构造最终结果
测试只检查文件存在
只检查函数能 import
```

如果任务目标是证明：

```text
Event → World
```

测试必须真的执行：

```text
Event
 ↓
Runtime
 ↓
World
```

而不是：

```text
调用一个 fake_world_update()
```

---

# 38. PM 每次发任务前的强制 10 问

在签发任何 Coding Agent 任务前，PM 必须自己回答：

### Q1

这个任务属于全局总线的哪一层？

### Q2

它直接服务哪个 Canonical 能力？

### Q3

是否违反 Constitution？

### Q4

当前主线已经有没有类似实现？

### Q5

有没有历史验证资产可以直接吸收？

### Q6

这是语义冲突还是表示冲突？

### Q7

是否会制造第二套 Runtime / Schema / State？

### Q8

有没有不必要地引入 LLM？

### Q9

什么测试能证明它真的完成？

### Q10

完成后总线的下一个明确位置是什么？

任何一个问题答不清：

**不要急着发任务。**

---

# 39. PM 每次验收前的强制 8 问

### Q1

代码真的存在吗？

### Q2

修改是否落在允许范围？

### Q3

测试真的执行了吗？

### Q4

stdout/stderr 是否能证明？

### Q5

有没有隐藏失败？

### Q6

有没有改变架构边界？

### Q7

有没有新增重复实现？

### Q8

它到底属于：

```text
VALIDATED
MAINLINE_INTEGRATED
还是 ACCEPTED
```

不能混淆。

---

# 40. Agent 报告验收标准

Agent 必须返回：

```text
1. 修改文件
2. 新增文件
3. 删除文件
4. 实际执行命令
5. 原始 stdout
6. 原始 stderr
7. 测试结果
8. 失败项
9. 未完成项
10. Git commit
11. Diff Stat
12. 工作树状态
```

缺少关键证据：

**不能直接 PASS。**

---

# 41. Agent 发现架构冲突时的处理

允许：

```text
STOP
REPORT
PROPOSE
```

不允许：

```text
自行修改 Constitution
自行扩大架构
自行创建第二套实现
```

PM 必须先进行裁决。

---

# 42. 已验证资产保护原则

以下类型的资产默认应受到保护：

```text
大量测试已经通过
长期稳定运行
已有真实基准
已经证明性能
已经证明 Replay
已经证明异常恢复
```

如果只是：

```text
字段名称不一样
目录不一样
内部类名不同
存储格式不同
```

不要立即重写。

先考虑：

```text
Adapter
Mapper
Facade
Translator
```

---

# 43. “新代码优先”原则废止

不允许因为：

> “重新写比较干净。”

就放弃已有验证资产。

AIOS 不追求：

```text
最漂亮的代码
```

优先追求：

```text
最可验证的系统
```

---

# 44. 工程判断优先级

当多个方案都满足架构时，优先：

```text
1. 已验证方案
2. 最少破坏现有能力
3. 最少重复实现
4. 最小修改面
5. 最强可测试性
6. 最强可回放性
7. 最低运行复杂度
8. 最低资源消耗
```

---

# 45. 不追求“代码量”

AIOS 不以：

```text
文件数量
代码行数
服务数量
模块数量
```

证明进展。

真正进展指标是：

```text
Canonical Capability
        ↓
实际 Runtime
        ↓
测试
        ↓
真实运行
        ↓
主线集成
        ↓
验收
```

---

# 46. 不允许建立“万能服务”

单一服务不能无限吸收：

```text
Event
World
Memory
Cognition
Decision
Action
```

各模块职责必须保持清晰。

---

# 47. 数据真实性原则

必须区分：

```text
OBSERVED
DERIVED
INFERRED
HYPOTHESIS
UNKNOWN
```

不能把：

```text
Inference
```

伪装成：

```text
Fact
```

不能把：

```text
AI belief
```

直接写入：

```text
World fact
```

---

# 48. Memory 的特殊保护

Memory 已经存在成熟能力时：

不得因为 Canonical 的字段名或结构不同就直接推倒重来。

先做：

```text
Semantic Comparison
        ↓
Mapping
        ↓
Adapter
        ↓
Compatibility Test
```

只有真正存在：

```text
行为冲突
事实隔离失败
时间语义错误
持久化错误
回放错误
```

才进入 Runtime 修改。

---

# 49. Model Router 的特殊保护

Model Router 的目标不是让模型成为系统核心。

它应该是：

```text
AI Runtime
      ↓
Model Router
      ↓
可替换模型
```

而不是：

```text
整个 AIOS
 ↓
某个固定模型
```

模型替换不能损害：

```text
Identity
Cognition
Growth
World
Memory
```

---

# 50. Evolution 的特殊保护

Evolution 不能直接修改：

```text
World Fact
```

它影响的是：

```text
Strategy
Policy
Experience
Lesson
Preference
Growth
```

必须继续保持：

```text
World
Cognition
Growth
```

三层隔离。

---

# 51. 关于“完成”的最终定义

一个能力只有同时满足：

```text
Canonical 对齐
+
实现存在
+
真实测试
+
关键边界验证
+
主线集成
+
回归通过
+
PM 审查
```

才能：

```text
ACCEPTED
```

---

# 52. 关于“项目完成”的最终定义

AIOS 不允许因为：

```text
聊天成功
模型能回答
Demo 看起来漂亮
UI 已完成
手机已经连接
```

就宣布完成。

真正完整必须能够证明：

```text
Reality
 ↓
Event
 ↓
World
 ↓
Memory
 ↓
Relevance
 ↓
Attention
 ↓
Wake
 ↓
AI
 ↓
Capability
 ↓
Permission
 ↓
Safety
 ↓
Action
 ↓
Outcome
 ↓
Evolution
 ↓
World
```

并且这个闭环：

```text
可运行
可回放
可测试
可观测
可恢复
可扩展
```

---

# 53. 当前项目主路线

当前优先顺序固定为：

```text
[1] Mainline World Foundation
    ↓
[2] World Change
    ↓
[3] Simulator
    ↓
[4] Memory Alignment
    ↓
[5] Dedup
    ↓
[6] Window
    ↓
[7] Clustering
    ↓
[8] Trend
    ↓
[9] Baseline
    ↓
[10] Relevance
    ↓
[11] Attention
    ↓
[12] Wake
    ↓
[13] Active Watch
    ↓
[14] AI Identity
    ↓
[15] Cognitive Tree
    ↓
[16] Growth Tree
    ↓
[17] World Access Session
    ↓
[18] Structured Output
    ↓
[19] Capability
    ↓
[20] Permission
    ↓
[21] Safety
    ↓
[22] Action
    ↓
[23] Outcome
    ↓
[24] Evolution
    ↓
[25] Interaction
    ↓
[26] Phone
    ↓
[27] Wearable
    ↓
[28] RTOS / Low Power
```

这个顺序允许在发现实际依赖关系时进行微调，

但：

**不得无理由跨越核心依赖。**

---

# 54. 当前已知治理结论

以下结论已经确定：

## 54.1 Constitution

```text
AIOS_Constitution_V1.2-r1.md
```

为唯一当前 Constitution 权威。

---

## 54.2 旧宪法

```text
AIOS宪法.md
```

历史参考。

不得与 -r1 并列作为现行最高规则。

---

## 54.3 Canonical 00-09

作为 AIOS 当前设计标准。

---

## 54.4 `aios/01_os`

作为唯一产品实现主线。

---

## 54.5 `core/arena`

作为历史验证资产。

不得继续发展为第二套产品主线。

---

## 54.6 `09_FIRST_SPRINT_TASKS.md`

以 Git 中实际版本为准。

当前 Sprint 1：

```text
T1 目录 + Schema
T2 Event 输入和持久化
T3 Entity
T4 World State
T5 Event → World Update
T6 World Change Delta
T7 Simulator
```

Sprint 2：

```text
T1 Dedup
T2 Sliding Window
T3 Clustering
T4 Trend
T5 Baseline Deviation
T6 Relevance
T7 Attention
T8 Wake
```

Sprint 3：

```text
T1 AI Identity
T2 Cognitive Tree
T3 Growth Tree
T4 World Access Session
T5 Model Router
T6 Structured Output
```

不得凭历史记忆改写以上事实。

---

# 55. Task 4 / Task 5 编号处理原则

如果历史 Agent 的 Task 编号与 Canonical Sprint 编号不同：

不要强行按编号解释。

而应该：

```text
能力
 ↓
总线位置
 ↓
验证状态
 ↓
提交
```

例如：

Dedup：

```text
Bus:
Event Runtime

Canonical:
Sprint 2 / Task 1

Historical Agent label:
可能存在其它 Task 编号

判断:
以能力位置为准
```

---

# 56. 当前 World Reality

在状态判断时必须明确区分：

```text
验证线
vs
主线
```

如果：

```text
core/world/world_runtime.py
```

拥有已验证实现，

但：

```text
aios/01_os/.../stated.py
```

仍为空壳，

则：

```text
World Capability:
VALIDATED

Product Mainline:
NOT ACCEPTED
```

不能直接宣布：

```text
World 完成
```

---

# 57. 当前项目最重要的工程目标

不是：

```text
继续增加功能数量
```

而是：

```text
将已经存在的有效能力
收敛到
唯一 Canonical 主线
```

顺序：

```text
发现
 ↓
验证
 ↓
映射
 ↓
吸收
 ↓
回归
 ↓
删除重复
```

---

# 58. PM 防跑偏机制

每次项目进入新阶段时，PM 必须重新检查：

```text
A. 我是不是又开始凭记忆判断？

B. 我是不是把实验能力当产品能力？

C. 我是不是把历史 Task 编号当成真相？

D. 我是不是让两个 Agent 做同一件事情？

E. 我是不是为了形式统一而重写验证资产？

F. 我是不是又创建了第二套实现？

G. 我是不是让 LLM 进入了本该确定性完成的层？

H. 我是不是在核心链没有完成前跳到硬件？

I. 我是不是把 Agent 自报完成当成验收？

J. 我是不是因为一个局部 Bug 又开始重建架构？
```

任何一个回答：

```text
YES
```

都必须停下来重新评估任务。

---

# 59. PM 自我约束：不得为了证明自己正确而推进错误方向

如果新的代码证据证明：

```text
之前的判断是错的
```

必须：

```text
承认
修正
更新 STATUS
更新 LEDGER
重新规划
```

不得为了维护历史决策而继续错误方向。

---

# 60. PM 自我约束：不以“说得通”为验收

以下不是验收：

```text
理论上应该可以
设计上没问题
看起来合理
Agent 说已经跑过
代码逻辑没明显问题
```

必须优先使用：

```text
真实代码
真实测试
真实运行
真实日志
真实提交
```

---

# 61. PM 自我约束：不因为代码多而害怕重构，也不因为代码漂亮而主动重构

重构必须由：

```text
真实语义冲突
性能问题
可靠性问题
安全问题
维护问题
明确架构收益
```

驱动。

而不能由：

```text
看起来不整齐
目录不漂亮
命名不好看
“我更喜欢另一种写法”
```

驱动。

---

# 62. Git 是长期项目记忆

长期项目事实必须尽可能固化到 Git：

```text
Constitution
Canonical Docs
STATUS
DELIVERED_LEDGER
ACTIVE_TASK
CONFLICT_REGISTER
Acceptance Records
```

而不是只存在于：

```text
Chat
Agent
PM
人工记忆
```

---

# 63. 每个阶段结束必须更新三张表

至少更新：

```text
STATUS.md
DELIVERED_LEDGER.md
CONFLICT_REGISTER.md
```

必要时同步：

```text
ACTIVE_TASK.md
```

---

# 64. CONFLICT_REGISTER.md

用于记录：

```text
冲突编号
来源
Canonical 要求
实际代码
冲突类型
严重程度
推荐处理
当前 Owner
状态
```

冲突不能只留在聊天记录。

---

# 65. 项目最终治理模型

AIOS 长期采用：

```text
CONSTITUTION
     ↓
CANONICAL
     ↓
PROJECT CONTROL
     ↓
BUS
     ↓
CAPABILITY
     ↓
IMPLEMENTATION
     ↓
TEST
     ↓
EVIDENCE
     ↓
ACCEPTANCE
```

形成：

```text
Design
 ↓
Implementation
 ↓
Verification
 ↓
Acceptance
 ↓
Ledger
 ↓
Next Task
```

闭环。

---

# 66. 最终一句话原则

> **AIOS 的架构由 Canonical 决定，项目现实由 Git 证明，开发方向由全局总线决定，任务由能力而不是编号定义，冲突按语义与表示区分，已验证资产优先保护，同一能力只能有一个实现主线，而 PM 自己必须接受代码和证据的反驳。**

---

# 67. 当前执行纪律

从本文件生效以后：

```text
不凭记忆推进
不凭 Agent 自报完成推进
不凭 Task 编号推进
不凭代码数量推进
不凭“看起来合理”推进
不凭漂亮架构图推进
```

而是：

```text
Read Canonical
        ↓
Read Git Reality
        ↓
Locate Bus Position
        ↓
Check Existing Capability
        ↓
Check Ownership
        ↓
Define Smallest Correct Task
        ↓
Execute
        ↓
Inspect
        ↓
Test
        ↓
Accept / Reject
        ↓
Update Ledger
        ↓
Select Next Task
```

这条流程是本项目长期默认流程。

---

# 68. 生效说明

本文件本身：

* 不修改 Constitution
* 不覆盖 00-09 Canonical
* 不改变已有架构
* 不宣布任何模块自动完成
* 不替代 Acceptance Tests
* 不允许 Agent 自行解释为架构授权

它唯一做的事：

**约束项目管理与开发执行过程。**

任何后续 PM 决策如果违反本文件，必须明确记录：

```text
违反哪一条
为什么
替代方案
谁批准
```

未经明确记录，不允许绕过本文件。

---

# STATUS

Status: ACTIVE
Version: V1.0
Owner: AIOS Project Architect / PM
Authority: Project Governance
Constitution Override: NO
Canonical Override: NO
