# AIOS PROJECT EXECUTION MASTER V1.0

> AIOS 项目总工程执行准则 / PM 自我约束文件
> 状态：ACTIVE
> 适用范围：整个 AIOS 项目开发生命周期
> 当前 Constitution：**AIOS Constitution V1.4-r0**
> 当前 OS 产品主线：`aios/01_os/`

---

# 0. 文件定位

本文件只负责工程治理，不重新定义产品架构。

权威关系：

```text
AIOS Constitution V1.4-r0
        ↓
V1.4 Canonical / Architecture / Runtime / Data Model / Acceptance
        ↓
Project Control Documents
        ↓
Git + Tests + Runtime Evidence
        ↓
Current Code
        ↓
Historical Chat / Agent Reports
```

如果本文件与 Constitution 冲突，以 Constitution 为准。

---

# 1. 唯一产品主线

```text
aios/01_os/
```

这是当前唯一 AIOS OS 产品实现主线。

历史目录如 `core/`、`arena/`、benchmark、实验目录可以保留为验证、实验或历史资产，但不得继续发展为第二套产品 Runtime。

历史资产的正确处理方式：

```text
发现
 ↓
验证
 ↓
判断是否符合 V1.4
 ↓
提取有效能力
 ↓
吸收/适配到 aios/01_os
 ↓
主线回归测试
 ↓
删除重复实现
```

---

# 2. V1.4 唯一主链

工程实现必须围绕：

```text
Observation
 ↓
Global Timeline
 ↓
Dimension
 ↓
Trigger
 ↓
AI Session
 ↓
Inference Event
 ↓
Help / Action
 ↓
Outcome
 ↓
AI Self Update
```

不要继续使用旧的：

```text
Semantic Event → Event Runtime → Entity/Fusion → World Update → Memory → Attention → Wake
```

作为新的 Canonical 架构总线。旧代码可以存在，但必须被视为迁移对象或兼容实现。

---

# 3. 开发前强制检查

每个任务开始前必须回答：

1. 对应 V1.4 哪条能力？
2. 位于主链哪个位置？
3. 输入是什么？
4. 输出是什么？
5. 当前主线是否已经有实现？
6. 历史资产是否已有经过验证的能力？
7. 是语义冲突还是表示冲突？
8. 是否会产生第二套 Runtime / Schema / Memory / Timeline？
9. 是否错误地把 LLM 放进确定性底层？
10. 如何通过真实测试证明完成？

任何一个问题无法回答，不得直接扩大开发范围。

---

# 4. Observation First

底层首先保存 Observation，而不是直接生成 AI 结论。

底层允许做：

```text
格式校验
时间归一化
去损坏
重复采样处理
单位统一
权限检查
机械阈值
存在性检测
安全硬规则
```

底层不得擅自判断：

```text
这是不是谈判
这是不是焦虑
这是谁
用户真正想表达什么
两件事是否存在复杂关系
```

这些属于 AI Session 的认知职责。

---

# 5. Trigger 与 AI 必须分离

Trigger 是机械唤醒机制，不是语义判断器。

允许：

```text
阈值到达
定时点到达
明显安全硬规则
注册关键词机械命中
Active Watch 条件命中
用户主动请求
```

触发之后才进入 AI Session，由 AI 读取相关世界证据并完成语义理解。

禁止常规模式：

```text
每条观测 → 小模型语义分类 → 再决定是否存在事件
```

---

# 6. One AI / One World

教育、社交、娱乐、工作、健康等应用不能各自建立：

```text
第二套 AI
第二套 Memory
第二条 Timeline
第二套 Wake Runtime
```

应用只能通过 Dimension / Observation / AIOS API 接入同一个世界。

---

# 7. World / Cognition / Outcome 边界

必须严格区分：

```text
OBSERVED     观测到的证据
DERIVED      确定性计算得到的数据
INFERRED     AI 推断
HYPOTHESIS   AI 假设
UNKNOWN      尚未确认
```

AI 不得把推断直接写成现实事实。

所有重要 Action 必须产生 Outcome，并回到 Global Timeline。

---

# 8. Identity / Voiceprint

声纹只承担机械区分“是不是同一个说话人”的能力。

身份绑定必须由 AI 根据上下文、历史和证据完成：

```text
Unknown A
 ↓
AI 发现证据
 ↓
绑定候选身份
 ↓
记录证据与置信度
 ↓
后续可修正
```

原始 Unknown 记录不得被覆盖或删除。

---

# 9. MODE / Help-First / Safety

MODE 是 AI 理解上下文的重要条件，不是必须由云模型逐事件分类的独立 Runtime。

AI 是否介入必须综合：

```text
当前世界
MODE
用户意图
历史关系
Active Watch
相关性
安全状态
介入预算
```

允许沉默；沉默本身可以是正确帮助。

Safety 是最高优先级。明显的人身安全事件可以绕过普通 MODE、Relevance、Attention 和介入预算。

---

# 10. Active Watch

AI 可以提出：

```text
Watch(entity, condition, duration)
```

AIOS 负责机械观察条件，命中后重新唤醒 AI。

这意味着：

```text
AI 不持续运行
AIOS 持续观察
条件命中
→ AI 再次醒来
```

---

# 11. UI / 3D 边界

当前用户正在构建 3D 模型和 UI，因此 UI 可以提前开发，但必须遵守：

```text
3D / UI
 ↓
UI ↔ Runtime Contract
 ↓
AIOS Runtime
```

UI 可以：

```text
展示状态
展示 AI Intervention
接收触摸/手势
发送用户操作
播放文字/语音/震动语义
```

UI 不可以拥有：

```text
Memory
Global Timeline
Trigger Logic
AI Decision
World Truth
Safety Policy
```

Demo 阶段允许 Mock Runtime Event；未来应能无缝替换为真实 AIOS Runtime Event。

---

# 12. 代码治理

同一个核心能力只能存在一个主实现。

禁止：

```text
顺手重构
顺手统一所有目录
顺手重写历史能力
为了命名漂亮而推倒验证代码
```

语义冲突：改实现。

表示冲突：优先 Adapter / Mapper / Translator / Compatibility Layer。

任何大规模删除必须先做依赖审查和测试审查。

---

# 13. 状态枚举

统一使用：

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

禁止使用“差不多完成”“基本完成”等模糊状态。

`VALIDATED` ≠ `MAINLINE_INTEGRATED` ≠ `ACCEPTED`。

---

# 14. Agent 权限边界

Coding Agent 可以：

```text
阅读代码
修改任务允许文件
运行测试
提交代码
报告真实证据
```

Coding Agent 不可以：

```text
修改 Constitution
自行决定架构
建立第二套 Runtime
擅自扩大任务范围
用 Agent 自报结果代替验收
```

发现架构冲突时：

```text
STOP
REPORT
PROPOSE
```

等待架构裁决。

---

# 15. 验收证据

“已经完成”“测试通过”不是证据本身。

有效证据至少应包含：

```text
修改文件
新增文件
删除文件
实际命令
原始 stdout
原始 stderr
测试通过/失败数量
Git commit
Diff Stat
工作树状态
```

核心 Runtime 必须尽可能覆盖：

```text
Unit
Integration
Replay
Determinism
Failure
Restart
Boundary
Regression
```

禁止通过“文件存在”“函数能 import”“fake 核心结果”冒充真实测试。

---

# 16. 项目现实的唯一判断方法

不要根据聊天记录、Agent 报告、文件数量或任务编号判断完成度。

统一判断：

```text
Canonical Capability
 ↓
Implementation
 ↓
Real Test
 ↓
Runtime Evidence
 ↓
Mainline Integration
 ↓
Acceptance
```

Git 是项目长期事实来源。

---

# 17. 三个长期控制文件

每个阶段结束后至少同步：

```text
STATUS.md
DELIVERED_LEDGER.md
CONFLICT_REGISTER.md
```

必要时同步：

```text
ACTIVE_TASK.md
```

这些文件用于记录项目现实，不得写成愿望清单。

---

# 18. 当前执行路线

当前优先级由 V1.4 Canonical 决定：

```text
1. Observation / Timeline Foundation
2. Dimension / Curve
3. Trigger
4. AI Session
5. Inference Event
6. Help / Intervention
7. Outcome
8. AI Self Update
9. Identity / Relationship
10. Active Watch
11. Safety
12. UI ↔ Runtime Contract
13. Phone / Wearable adapters
```

具体任务可以调整顺序，但不得违反 V1.4 的依赖关系或建立第二套 OS。

---

# 19. 最终工程纪律

```text
先读 Constitution
 ↓
再读 Canonical
 ↓
再看 Git Reality
 ↓
检查已有能力
 ↓
定位主链
 ↓
定义最小任务
 ↓
执行
 ↓
真实测试
 ↓
检查 Diff
 ↓
验收或拒绝
 ↓
更新 STATUS / LEDGER / CONFLICT
 ↓
选择下一任务
```

最终原则：

> **架构由 V1.4 Constitution 决定；项目现实由 Git 和真实证据证明；开发围绕唯一 `aios/01_os` 主线收敛；历史资产优先验证和吸收；同一能力只能有一个主实现；UI 是身体，AIOS Runtime 才是系统；任何 Agent 都不能用自己的报告替代事实。**

---

# STATUS

Status: ACTIVE
Version: V1.0
Current Constitution: V1.4-r0
Owner: AIOS Project Architect / PM
Constitution Override: NO
Canonical Override: NO
