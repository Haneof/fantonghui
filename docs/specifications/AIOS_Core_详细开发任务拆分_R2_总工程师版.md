# AIOS Core 详细开发任务拆分 R2（总工程师重写版）

**文档版本**：R2-DEV-FULL v2.0  
**日期**：2026-09-14  
**状态**：建议作为下一轮正式开发任务母表，取代旧《AIOS_Core_详细开发任务拆分_R2.md》作为直接派单依据  
**上位依据**：AIOS 宪法 2.0、R1、R2、《AIOS Core 系统架构图与开发规划》《AIOS认知工作台功能规格》《AIOS虚拟世界测试规范》  
**当前开发目标**：不是做完整 Linux 操作系统，而是用虚拟世界和模拟数据证明 AIOS Core 的核心认知机制成立。

> 这份文件专门解决旧任务拆分“不够细”的问题。每个任务都写清：当前实现目标、为什么要做、实现方式、技术/代码指导、接口、数据、测试、验收标准、禁止事项、前置依赖和交付物。
>
> **原则**：低能力编码模型只能执行已经冻结的 Issue，不能自行重新设计世界模型。关键底层契约、世界写入、版本、证据、纠错、任务状态机等核心代码由总工程师亲自给出参考实现或逐段审核。

---

# 0. 这份任务书如何使用

## 0.1 三层管理，不再把“任务包”直接丢给编码模型

项目从现在开始分成三层：

```text
宪法 / R1 / R2
      ↓
里程碑 M0～M8
      ↓
细粒度 Issue（本文件）
      ↓
代码 + 自动测试 + 可回放证据
```

旧 P01～P11 继续作为历史规划索引，但不再直接作为开发任务。原因是诸如“世界存储、版本、统一提交、查询快照”这种任务包实际包含多个不能同时模糊实现的工程问题。

## 0.2 每个 Issue 的关闭条件

任何任务只有同时满足以下条件才可以关闭：

1. 代码已经进入指定分支或提交。
2. 接口/数据结构与本文件一致。
3. 单元测试通过。
4. 涉及跨模块行为时，至少一个集成测试通过。
5. 有一份可以重放的运行证据或测试日志。
6. 失败路径被测试，不只测试成功路径。
7. 已知限制写入 Issue。
8. 未绕过 Core 直接改 SQLite。
9. 未修改 R2 冻结字段/语义。
10. 代码评审确认没有把语义判断偷偷塞到底层机械规则。

“代码能跑”“HTTP 200”“模型说完成了”都不是完成标准。

## 0.3 技术基线（第一阶段冻结）

为了让研发重点放在认知机制，而不是基础设施堆叠，第一阶段采用：

- **Python 3.12+**：核心服务、AI Worker、仿真器。
- **Pydantic 2**：世界对象契约、接口输入输出校验。
- **SQLite**：第一阶段持久化；使用 WAL、事务、明确唯一写入层。
- **pytest**：单元测试、集成测试、回归测试。
- **浏览器控制台**：开发者可视化工作台；技术可用 FastAPI + 简单前端，具体前端框架不是核心冻结项。
- **模型接入适配器**：先 Mock，再接一个真实大模型；AIOS Core 不与某个模型厂商绑定。
- **仿真器 / 评分器独立存储**：隐藏真值绝不能被 Core 或 AI Worker 查询。

第一阶段**不需要**微服务、Kafka、Kubernetes、图数据库集群。只有当测试证明 SQLite / 模块化单体真的成为瓶颈后再替换。

## 0.4 代码仓库推荐结构

```text
aios/
├── pyproject.toml
├── src/
│   ├── aios_core/
│   │   ├── contracts/          # 冻结世界对象契约
│   │   ├── storage/            # 唯一写入层、版本、事务
│   │   ├── world/              # Entity/Claim/Event/Dimension/Goal 服务
│   │   ├── query/              # 时间镜头、搜索、下钻、对齐
│   │   ├── dependency/         # 依赖和纠错传播
│   │   ├── tasks/              # 任务中心
│   │   ├── wake/               # 机械触发、队列、冷却
│   │   ├── workspace/          # AI 认知工作台结构化接口
│   │   ├── actions/            # 行动、回执、结果
│   │   ├── summaries/          # 日/周/月总结
│   │   └── dimensions/         # 动态维度生命周期、派生维度
│   ├── ai_worker/              # 大模型适配、工具循环、checkpoint
│   ├── simulator/              # 虚拟人生、虚拟时钟、观测生成
│   ├── evaluator/              # 隐藏真值、评分、强基线
│   └── console/                # 人类调试界面
└── tests/
    ├── unit/
    ├── integration/
    ├── scenarios/
    └── regression/
```

## 0.5 总工程师亲自负责的关键代码

以下部分不应交给低能力模型自由设计：

- 稳定 ID、三类时间、对象版本、世界版本。
- `Claim`（主张）与 `EvidenceSet`（证据集合）契约。
- `EventAnchor`（事件锚点）、`DimensionDerivation`（派生维度）、`Goal`（目标）契约。
- 唯一世界写入事务、幂等、乐观并发、历史世界读取。
- Task（任务）状态机和 Event（事件）生命周期转换。
- Dependency（依赖）反向索引和纠错传播策略。
- Wake（唤醒）与 Observation（基础观测）的分离。
- 日/周/月总结如何保留来源和可下钻性。
- AI Worker 可以做什么、不能绕过什么。

**当前已由总工程师亲自编写第一批参考代码**，目录为 `aios_core_r2_reference/`，包括世界契约、SQLite 追加式版本库、全局世界版本、幂等、历史读取、Task/Event 状态机和 15 个自动测试。后续编码应以参考实现的语义为基准，而不是另起一套模型。

## 0.6 编码代理的权限边界

编码代理允许：

- 实现已经定义清楚的接口。
- 增加测试。
- 优化性能但保持语义不变。
- 修复 bug。
- 提出架构变更建议。

编码代理禁止：

- 把 Event 改成普通文本字段。
- 把 Claim 的 `claim_type` 和 `knowledge_state` 合并。
- 删除 EvidenceSet，只保留 `source_refs[]`。
- 将所有维度强行数值化。
- 将用户世界与 AI 世界拆成两套不兼容数据库。
- 让每条 Observation 自动触发大模型。
- 让摘要覆盖或删除原始证据。
- 为“省代码”直接把模型生成文本写进数据库而不经过结构校验。
- 用另一个小模型在底层替代大模型做情绪、关系、事件语义判断。

---

# 1. R2 冻结的数据对象

第一阶段至少冻结以下对象：

| 对象 | 中文含义 | 第一阶段作用 |
|---|---|---|
| Observation | 基础观测 | 保存系统真正获得的数据，不做高层语义结论 |
| Entity | 实体 | 人、物、地点、组织等稳定 ID |
| Relation | 关系 | 实体之间带时间和证据的关系 |
| DimensionDefinition | 维度定义 | 定义“这个维度是什么” |
| DimensionMembership | 维度挂载 | 某节点/对象为什么属于某维度 |
| DimensionDerivation | 派生维度 | 多个低层维度如何组成高层认知 |
| Claim | 主张 | 一项可被支持、反对、修正的具体认知 |
| EvidenceSet | 证据集合 | 单点、区间、多维组合证据的冻结集合 |
| EventAnchor | 事件锚点 | 多维证据共同组成的事件解释 |
| Summary | 总结 | 日/周/月等时间尺度的认知视图 |
| Goal | 目标 | 跨多个 Task 的长期目标 |
| Dependency | 依赖 | 一个认知由什么产生；修正时反查 |
| Task | 任务 | 定时、待办、观察、验证、跟进等未来工作 |
| Wake | 唤醒 | 为什么这次要让 AI 介入 |
| Session | 会话执行 | AI 本次醒来操作世界的工作记录 |
| Action | 行动 | AI 实际发起的外部动作 |
| Outcome | 结果 | 行动真正发生了什么结果 |
| OperationExperience | 操作经验 | AI 如何更好使用世界的经验 |
| ToolProposal | 工具提案 | AI 发现缺少什么认知工具 |

---

# 2. 里程碑总览

| 里程碑 | 目标 | 只有满足这些条件才能进入下一阶段 |
|---|---|---|
| M0 | 冻结世界契约与核心存储 | 对象、时间、引用、版本、幂等、历史读取全部自动测试通过 |
| M1 | 建成可写、可查、可下钻的共同世界 | 能完成“运动会候选→证据展开→后来修正”的世界操作 |
| M2 | 建成主动运行闭环 | 无用户提问，系统能机械唤醒 AI，AI调查、帮助或沉默，并留下未来任务 |
| M3 | 建成长期纠错与多尺度认知 | 新证据能让旧认知失效并重审；支持原始→日→周→月总结与派生维度 |
| M4 | 连续一个月虚拟人生 | 任务、关系、Goal、AI自身世界跨日延续；可以和强基线比较 |
| M5 | 验证 AI 操作经验 | “AI越来越会使用世界”必须通过 A/B 实验证明 |
| M6 | 教育 App | 证明 App 不是独立人格，而是同一 AI 在专业场所工作 |
| M7 | 一年虚拟运行 | 验证规模、长期漂移、模型切换、恢复与成本 |
| M8 | 消融与机制裁决 | 没有独立收益的复杂机制被简化；决定是否进入真实设备原型 |

---

# M0：世界契约与核心存储冻结

这是整个项目最不能交给低能力模型自由发挥的阶段。M0 做错，后面所有认知、任务和实验都会建立在错误世界上。

## M0-001 仓库骨架、包边界与依赖方向

**负责人级别**：总工程师定义，编码代理执行  
**前置依赖**：无

### A. 当前实现目标

建立统一 Python 仓库结构，让 Core、AI Worker、Console、Simulator/Evaluator 从第一天就物理分区，并通过代码依赖约束保证 AI Worker 不能直接写数据库。

### B. 为什么现在必须做

如果不先划边界，后续模型代理最容易为了省事直接 import SQLite 或把测试真值导入 Core，最终无法证明架构。

### C. 具体实现方式

创建 src 布局；Core 对外暴露 contracts/storage/service/query 等接口；AI Worker 只依赖 Core 公共接口；Evaluator 单独包且不能成为 Core 依赖。建立 import-lint 或最少用测试扫描禁止依赖。

### D. 技术 / 代码指导

Python package 使用 pyproject.toml；第一阶段保持模块化单体，不拆微服务。将 `src/aios_core` 作为唯一世界读写实现。

### E. 推荐代码位置

`pyproject.toml`, `src/aios_core/`, `src/ai_worker/`, `src/simulator/`, `src/evaluator/`, `src/console/`, `tests/`

### F. 对外接口 / 命令

无业务 API；只冻结模块依赖。

### G. 必须编写的测试

测试 `ai_worker` 中不存在对 `sqlite3`/`storage.sqlite_store` 私有连接的直接使用；测试 Core 环境无法读取 evaluator truth path。

### H. 验收标准

全仓可安装；pytest 能运行；依赖方向检查通过；README 能说明四个运行单元。

### I. 明确禁止

不得一开始拆 Kubernetes/微服务；不得把 evaluator 代码当公共 util 给 Core 用。

### J. 本任务交付物

仓库骨架、依赖图、安装说明、最小 CI。

---

## M0-002 统一错误码和协议级异常

**负责人级别**：总工程师审核  
**前置依赖**：M0-001

### A. 当前实现目标

冻结跨模块可依赖的错误语义，避免每个接口返回随意自然语言导致 AI Worker 无法可靠恢复。

### B. 为什么现在必须做

AIOS 会长期运行、重试、恢复；必须让“版本冲突、资料不足、索引落后、结果未知”有机器可读区别。

### C. 具体实现方式

定义 ErrorCode 枚举和统一异常/响应结构；Core 内部异常转换成协议错误，但保留诊断日志。结果未知绝不能等同失败。

### D. 技术 / 代码指导

Pydantic 错误响应；Python Enum/StrEnum。HTTP 层以后可以映射状态码，但核心服务先使用同一错误对象。

### E. 推荐代码位置

`contracts/enums.py`, `errors.py`, `tests/unit/test_errors.py`

### F. 对外接口 / 命令

`INVALID_ARGUMENT, NOT_FOUND, VERSION_CONFLICT, INCOMPLETE_DATA, STALE_INDEX, BUDGET_EXHAUSTED, PERMISSION_DENIED, DEPENDENCY_INVALID, OUTCOME_UNKNOWN, IDEMPOTENCY_CONFLICT`

### G. 必须编写的测试

逐个错误码构造；确认调用者可以分支处理；模拟 Action 超时返回 OUTCOME_UNKNOWN。

### H. 验收标准

所有协议级失败都有 code + message + context；禁止只有 traceback 或 HTTP 500。

### I. 明确禁止

不要在 message 文本上做业务判断。

### J. 本任务交付物

错误码契约、异常类、测试。

---

## M0-003 稳定对象 ID 生成器

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-001

### A. 当前实现目标

给所有长期对象产生与名称无关的稳定 ID；后续“未知人物 A”认成妈妈时 ID 不变。

### B. 为什么现在必须做

实体名称、事件解释、维度名字都会被修正。若 ID 由名字生成，所有历史引用都会断裂。

### C. 具体实现方式

每种对象使用短前缀 + 随机不透明 ID；稳定 ID 只在对象首次创建时生成。Revision 更新不得生成新 object_id。

### D. 技术 / 代码指导

参考实现已提供 `new_object_id(ObjectType)`。UUID4 足够第一阶段；不要把时间/名字编码成业务含义。

### E. 推荐代码位置

`contracts/ids.py`

### F. 对外接口 / 命令

`new_object_id(object_type) -> str`；`new_operation_id()`；`new_execution_id()`

### G. 必须编写的测试

创建 Entity P；修改 canonical_name；确认 object_id 不变。批量生成 100k ID 检查唯一性。

### H. 验收标准

所有对象 ID 唯一；rename/revise 不改变 ID；ID 不泄露测试真值。

### I. 明确禁止

禁止 `mom_001`、`birthday_2026` 等语义 ID 作为核心对象 ID。

### J. 本任务交付物

ID 生成器、测试、前缀表。

---

## M0-004 唯一时间轴与三类时间语义

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-003

### A. 当前实现目标

实现 occurred（发生时间）、learned（系统得知时间）、recorded（写入时间），支持时间点、区间、未知端点和明确 unknown。

### B. 为什么现在必须做

用户今天说“昨天去了医院”时，发生时间与得知时间不同；虚拟测试还必须保证未来资料不能提前可见。

### C. 具体实现方式

使用 timezone-aware datetime；用 TemporalExtent 表示 point/range/open interval/unknown。所有长期对象继承三类时间。禁止 naive datetime。

### D. 技术 / 代码指导

参考实现已提供 `TemporalExtent`、`KnowledgeWindow`。后续所有查询必须区分 event time 与 knowledge cutoff。

### E. 推荐代码位置

`contracts/time.py`, `contracts/base.py`

### F. 对外接口 / 命令

`TemporalExtent.point()`, `TemporalExtent.unknown_time()`, `KnowledgeWindow`

### G. 必须编写的测试

昨天事件今天得知；一侧未知时间；错误 end<start；naive datetime；跨时区 Task。

### H. 验收标准

能够重建“事情什么时候发生”和“AI什么时候知道”；测试真值未来信息不会因数据库已存在而泄露。

### I. 明确禁止

禁止把 learned_at 自动设置成 occurred_at；禁止无时区时间。

### J. 本任务交付物

时间契约、边界测试、时区说明。

---

## M0-005 WorldObject 公共字段与 Revision 规则

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-004

### A. 当前实现目标

冻结所有长期对象的共同字段和追加式版本语义。

### B. 为什么现在必须做

AIOS 会不停修正世界；必须保留“当时认为是什么”，不能覆盖旧值。

### C. 具体实现方式

所有世界对象包含 object_id/object_type/subject_id/revision/occurred/learned_at/recorded_at/source_refs/created_by/status/metadata。Revision 从1开始，只能 +1。

### D. 技术 / 代码指导

Pydantic BaseModel；存储层必须校验当前最大 Revision。世界版本和对象 Revision 分开：前者表示一次世界提交，后者表示单对象修订。

### E. 推荐代码位置

`contracts/base.py`, `storage/sqlite_store.py`

### F. 对外接口 / 命令

`WorldObject`；存储 `commit()`

### G. 必须编写的测试

写 rev1、rev2；尝试直接写 rev4 应 VERSION_CONFLICT；读 rev1 仍存在。

### H. 验收标准

任何修改不覆盖旧 revision；对象版本可以回放。

### I. 明确禁止

禁止 UPDATE 覆盖 payload；除明确的索引表外，真相对象只追加版本。

### J. 本任务交付物

公共基类、版本规则测试。

---

## M0-006 ObjectRef / SourceRef 版本化引用

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-005

### A. 当前实现目标

建立统一引用格式，让证据、事件、关系、维度等对象可以指向明确版本。

### B. 为什么现在必须做

如果只引用 object_id 最新值，历史认知回放会被后来的修正偷偷改变。

### C. 具体实现方式

ObjectRef 支持 object_id + optional revision。用于证据时原则上优先冻结 revision；用于“追随最新实体身份”的导航可以使用最新语义，但必须明确接口。

### D. 技术 / 代码指导

Pydantic immutable model；写入时存储层验证引用存在且在 knowledge cutoff 内可见。

### E. 推荐代码位置

`contracts/refs.py`, `storage/reference_validation.py`

### F. 对外接口 / 命令

`ObjectRef`, `SourceRef`

### G. 必须编写的测试

引用不存在对象；引用不存在 revision；同事务创建并互相合法引用；历史版本引用。

### H. 验收标准

所有关键 Claim/Event/Evidence/Dependency 能追到准确 revision。

### I. 明确禁止

禁止证据链仅保存自由文本“来自昨天聊天”。

### J. 本任务交付物

引用契约、验证器、测试。

---

## M0-007 Observation（基础观测）契约

**负责人级别**：总工程师审核  
**前置依赖**：M0-004,M0-006

### A. 当前实现目标

只表达“系统真实获得了什么”，不承载情绪、关系、事件等大模型结论。

### B. 为什么现在必须做

多维世界必须有可靠底层；否则 AI 后续修改认知时无法回到底层证据。

### C. 具体实现方式

字段至少 source_kind/modality/value/unit/data_quality/raw_locator + 公共时间/来源。高频传感器可后续支持 block，但第一版先统一 Observation 语义。

### D. 技术 / 代码指导

值可以结构化 JSON；原始超大文件使用 locator，不把二进制塞 JSON。Observation 写入本身默认不 Wake。

### E. 推荐代码位置

`contracts/models.py::Observation`

### F. 对外接口 / 命令

`ingest.observation.create` 后续实现

### G. 必须编写的测试

心率、GPS、对话文本、App答题记录各建一条；确认不能出现 `event_type=breakup` 之类高层结论字段。

### H. 验收标准

不同来源资料能够进入同一时间轴；底层对象不做语义判断。

### I. 明确禁止

禁止在清洗阶段调用模型判断“用户焦虑”。

### J. 本任务交付物

Observation schema 与样例 fixture。

---

## M0-008 Claim（主张）语义模型

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-005,M0-006

### A. 当前实现目标

把“谁对谁/什么提出了什么性质的主张”做成可修正对象，并将 claim_type 与 knowledge_state 分离。

### B. 为什么现在必须做

用户一句“我明天一定考上某校”同时包含话语事实、信念/预测，但不等于现实录取事实。长期系统若不拆会积累严重错误。

### C. 具体实现方式

字段 claimant_id、subject_id、claim_type、content、valid_time、asserted_at、knowledge_state、confidence、support/counter EvidenceSet、unknown_items。claim_type 至少 FACT/OPINION/BELIEF/DESIRE/INTENTION/PLAN/PREDICTION/PROMISE/PREFERENCE/INFERENCE/HYPOTHESIS。

### D. 技术 / 代码指导

代码中 confidence 只约束 0..1，不自动根据来源赋值。模型生成 Claim 后 Core 只做结构校验，语义由后续证据和测试验证。

### E. 推荐代码位置

`contracts/models.py::Claim`, `contracts/enums.py`

### F. 对外接口 / 命令

`claim.create`, `claim.revise` 后续服务

### G. 必须编写的测试

“明天生日”“一定考上”“我觉得妈妈生气了”分别拆 Claim；高置信话语事实不得把现实预测置信度一起抬高。

### H. 验收标准

测试能明确展示同一句话的多个主张，且每项可单独修正。

### I. 明确禁止

禁止 `content + confidence` 两字段简化模型；禁止 claim_type=FACT 就自动 confidence=1。

### J. 本任务交付物

Claim schema、枚举、语义测试集。

---

## M0-009 EvidenceSet（证据集合）一等对象

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-006,M0-008

### A. 当前实现目标

把单点、区间、多维组合证据保存成可复核、可冻结、可重建的对象。

### B. 为什么现在必须做

“过去两周睡眠下降”不是一条 SourceRef；运动会也可能由心率区间+声音+地点+聊天共同支持。

### C. 具体实现方式

EvidenceSet 包含 purpose、KnowledgeWindow、member/support/counter/context refs、可选 selector、selection_method、aggregation_method/version、coverage、missingness/stale。区间 selector 必须冻结 time_range 和 knowledge cutoff。

### D. 技术 / 代码指导

第一版允许显式成员和 query selector 两种。query selector 重建结果必须可材料化为成员版本；迟到资料以后通过 stale/rebuild 产生新 revision。

### E. 推荐代码位置

`contracts/models.py::EvidenceSet/EvidenceSelector/EvidenceCoverage`

### F. 对外接口 / 命令

`evidence_set.create/inspect/rebuild` 后续

### G. 必须编写的测试

空 EvidenceSet 应拒绝；区间证据一周后仍指原区间；support/counter/context 分开；覆盖率缺失可见。

### H. 验收标准

任何高层 Claim/Event 能解释“依据是什么”和“缺什么证据”。

### I. 明确禁止

禁止只存自然语言“综合多个维度判断”；禁止 selector 使用 now-14d 这种会漂移的动态时间。

### J. 本任务交付物

EvidenceSet schema、区间 fixture、测试。

---

## M0-010 Entity + Relation（实体与关系）契约

**负责人级别**：总工程师审核  
**前置依赖**：M0-006,M0-008,M0-009

### A. 当前实现目标

支持未知人物/物品先有稳定 ID，之后身份变清楚；关系带有效时间、证据和置信度。

### B. 为什么现在必须做

关键词相同不等于同一个实体；“妈妈”身份也可能是后来才知道。

### C. 具体实现方式

Entity 保存 kind/name/aliases/identity_claim_refs；Relation 保存 left/right/relation_type/valid_time/evidence/confidence。身份认定本质上也由 Claim 支撑。

### D. 技术 / 代码指导

不要将关系作为 Entity JSON 内嵌永久列表；保持独立对象，便于时间变化与纠错。

### E. 推荐代码位置

`contracts/models.py::Entity/Relation`

### F. 对外接口 / 命令

`entity.resolve`, `relation.upsert` 后续

### G. 必须编写的测试

未知 P001→妈妈；同名两个小王；关系从同事变前同事；历史时点查询。

### H. 验收标准

实体身份更新不改 ID；关系历史可回放；字符串搜索不自动合并实体。

### I. 明确禁止

禁止 canonical_name 作为主键。

### J. 本任务交付物

实体/关系契约与测试 fixture。

---

## M0-011 DimensionDefinition / Membership / Derivation 三层契约

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-006,M0-009

### A. 当前实现目标

把“维度是什么”“什么对象挂载该维度”“高层维度如何由低层组合”分成三种对象。

### B. 为什么现在必须做

如果全部塞进一个 Dimension 表，后续“数学+英语+编程→学习能力”无法明确追溯，也容易把维度误解成数值曲线。

### C. 具体实现方式

Definition 定义 name/description/data_shape/lifecycle/update_method；Membership 引用 dimension 和 member；Derivation 引用 output_dimension + input_refs + evidence + applicable_scope/time + confidence/counterexamples。

### D. 技术 / 代码指导

一个对象允许多个 Membership。Derivation 的 input 可以是维度、事件、Claim、Summary、EvidenceSet，而不是只允许数值曲线。

### E. 推荐代码位置

`contracts/models.py::DimensionDefinition/DimensionMembership/DimensionDerivation`

### F. 对外接口 / 命令

`dimension.inspect/propose/transition`, `dimension.derivation.*` 后续

### G. 必须编写的测试

同一“运动会事件”同时挂事件/运动经历等维度；学习能力可下钻到数学/英语/编程；原始证据不复制。

### H. 验收标准

高层维度能追溯输入；维度 data_shape 不被强制 curve。

### I. 明确禁止

禁止维度 = vector<float> 的单一实现；禁止复制 Observation 作为每个维度私有数据。

### J. 本任务交付物

三类维度 schema、追溯测试。

---

## M0-012 EventAnchor（事件锚点）契约与生命周期

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-008,M0-009,M0-010

### A. 当前实现目标

把事件定义为对多维世界的解释/锚点，而不是底层采集事实；允许候选→成立→结束→修正/否定/合并/拆分。

### B. 为什么现在必须做

AI最初可能认为是“运动会”，后来确认只是“体育测试”；不能覆盖历史，也不能要求事件一创建就100%正确。

### C. 具体实现方式

Event 包含 title、interpretation、event_status、event_time、participants、primary_claims、EvidenceSets、confidence、supersedes/merged/split refs。状态转换单独校验。

### D. 技术 / 代码指导

Event 本身只引用证据和实体，不复制全部 Observation。REVISED 建新 Revision；MERGED/SPLIT 保留指向。

### E. 推荐代码位置

`contracts/models.py::EventAnchor`, `services/state_machines.py`

### F. 对外接口 / 命令

`event.create/expand/revise/reject/merge/split` 后续

### G. 必须编写的测试

candidate→active；candidate→rejected；active→revised；merged 终态；历史事件仍可回放。

### H. 验收标准

运动会案例能看到“当时为什么猜错”和“后来为何修正”。

### I. 明确禁止

禁止 Event create 时强制 confidence=1；禁止修改 title 就抹掉旧版本。

### J. 本任务交付物

事件契约、状态机、生命周期测试。

---

## M0-013 Goal（目标）一等对象

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-006,M0-008

### A. 当前实现目标

将长期目标和短期 Task 分开；支持用户明确目标、AI推断目标、App目标等不同来源。

### B. 为什么现在必须做

“一年学会英语”不是一个一次性任务。几百个学习/复测/提醒 Task 可以共同服务一个 Goal。

### C. 具体实现方式

Goal 保存 owner/source_type/title/description/status/success_criteria/related dimensions/events/tasks/apps/confidence。明确用户目标与 AI inferred goal 必须区分。

### D. 技术 / 代码指导

Goal 不自动转 Task；AI Worker 在需要未来行动时创建 Task 并链接 Goal。

### E. 推荐代码位置

`contracts/models.py::Goal`

### F. 对外接口 / 命令

`goal.create/update/query/assess_progress` 后续

### G. 必须编写的测试

用户明确“我要减肥”和 AI 推断“用户可能想减肥”存成不同 source_type；用户否认推断目标后相关 Task 能复核。

### H. 验收标准

帮助决策可以回答“这与哪个用户目标有关”。

### I. 明确禁止

禁止把 Goal 仅作为 Task.goal 字符串。

### J. 本任务交付物

Goal schema、来源语义测试。

---

## M0-014 Task / Wake / Session / Action / Outcome 基础契约

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-005,M0-013

### A. 当前实现目标

冻结主动系统需要的未来工作、唤醒原因、会话执行、外部行动与现实结果对象。

### B. 为什么现在必须做

AI如果只是“想起来以后再问”，但没有持久 Task，就不是真正管家；Action 发出也不等于用户接受。

### C. 具体实现方式

Task 包含 type/state/goal/priority/next_wake/deadline/dependencies/completion/cancel/executions/outcomes；Wake 包含 source/hits/evidence/priority/dedupe；Session 固定世界快照；Action 与 Outcome 分开。

### D. 技术 / 代码指导

第一阶段先冻结字段，M2 再实现调度。Action 使用稳定 execution_id；Outcome 可以 UNKNOWN。

### E. 推荐代码位置

`contracts/models.py::{Task,Wake,Session,Action,Outcome}`

### F. 对外接口 / 命令

后续 `task.*`, `workspace.*`, `action.*`

### G. 必须编写的测试

“提醒已送达”只完成通知 Task；不代表“用户已经学习”；Action 超时后保持 outcome unknown。

### H. 验收标准

对象可以序列化/版本化，字段含义无歧义。

### I. 明确禁止

禁止模型上下文代替 Task；禁止消息送达=帮助成功。

### J. 本任务交付物

五类对象契约及 fixture。

---

## M0-015 Dependency（依赖）契约

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-006,M0-009

### A. 当前实现目标

记录一个认知/总结/任务依赖哪个对象的哪个版本，为未来纠错传播提供反向查询依据。

### B. 为什么现在必须做

没有依赖关系，妈妈身份修正后系统不知道哪些生日总结、提醒、事件需要重审。

### C. 具体实现方式

Dependency 至少 dependent_ref、dependency_ref、dependency_type。写入高层对象时服务层同步写依赖。普通语义链接和“证据依赖”必须区分。

### D. 技术 / 代码指导

第一阶段可用 SQLite 表/对象保存；M3 构建反向索引。证据来源图不允许自我证明循环。

### E. 推荐代码位置

`contracts/models.py::Dependency`

### F. 对外接口 / 命令

`dependency.create/inspect/reverse_lookup` 后续

### G. 必须编写的测试

Claim→EvidenceSet→Observation；Summary→Claim；Task→Event。构造循环证据应拒绝或标红。

### H. 验收标准

能够从底层对象反查受影响对象。

### I. 明确禁止

禁止把所有链接都当 Dependency；关系图可以有环，证明链不能靠自身闭环提置信度。

### J. 本任务交付物

Dependency schema、最小循环测试。

---

## M0-016 OperationRequest、审计与幂等契约

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-002,M0-005

### A. 当前实现目标

所有世界修改带 operation_id/session_id/expected_world_revision/reason/idempotency_key，并能够安全重试。

### B. 为什么现在必须做

大模型调用、网络、进程都会失败重试；没有幂等会重复发消息/重复写认知。

### C. 具体实现方式

OperationRequest 冻结字段；存储层先查 idempotency_key，再做 expected_world_revision 乐观并发校验；重放返回原结果。

### D. 技术 / 代码指导

参考实现已提供 `OperationRequest` 和 SQLite idempotency_records。后续外部 Action 也使用 execution_id 幂等。

### E. 推荐代码位置

`contracts/operations.py`, `storage/sqlite_store.py`

### F. 对外接口 / 命令

`commit(objects, operation)`

### G. 必须编写的测试

同 key 两次提交世界版本只增加一次；旧 expected revision 返回 VERSION_CONFLICT。

### H. 验收标准

重试无重复副作用，审计可查。

### I. 明确禁止

禁止自动吞掉 VERSION_CONFLICT 后覆盖别人结果。

### J. 本任务交付物

Operation 契约、幂等测试。

---

## M0-017 SQLite 追加式世界存储 schema

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-016

### A. 当前实现目标

实现第一阶段世界持久化：object revisions、world commits、operations、idempotency，所有真相对象追加不覆盖。

### B. 为什么现在必须做

必须先证明世界历史和回放正确，再谈更复杂数据库。

### C. 具体实现方式

建立 world_meta/world_commits/object_revisions/operations/idempotency_records；WAL；事务；索引 object_id/type/subject/learned_at。对象 payload 初期可 JSON，公共字段独立列便于查询。

### D. 技术 / 代码指导

参考实现已完成最小 schema。后续 migration 使用显式版本脚本，禁止运行时随意 ALTER。

### E. 推荐代码位置

`storage/sqlite_store.py`, 后续 `storage/migrations/`

### F. 对外接口 / 命令

`SQLiteWorldStore`

### G. 必须编写的测试

建库、重启、连续提交、失败事务 rollback、同对象多 revision、并发 expected revision。

### H. 验收标准

断电/异常模拟后数据库一致；所有历史 revision 保留。

### I. 明确禁止

禁止 AI Worker 获得 sqlite connection。

### J. 本任务交付物

数据库 schema、初始化、事务测试。

---

## M0-018 全局 World Revision 与原子提交

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-017

### A. 当前实现目标

一次世界事务产生一个全局版本，使工作台可以固定快照并回答“world revision 123 时 AI 知道什么”。

### B. 为什么现在必须做

AI 一边读取、一边新资料进入时，需要明确它是基于哪个世界快照做出的判断。

### C. 具体实现方式

事务开始检查 expected_world_revision；本次多个对象一起写入同一个 next world revision；commit 成功后 meta +1。

### D. 技术 / 代码指导

使用 `BEGIN IMMEDIATE`；所有对象先结构/引用/版本校验再 insert。

### E. 推荐代码位置

`storage/sqlite_store.py`

### F. 对外接口 / 命令

`current_world_revision()`, `commit()`

### G. 必须编写的测试

一次写 3 对象 world revision 只+1；失败中途不写半个世界；两写者冲突只有一个成功。

### H. 验收标准

世界提交原子；Session 可以固定 snapshot revision。

### I. 明确禁止

禁止每写一个对象 world revision +1 导致同一逻辑事务被拆碎。

### J. 本任务交付物

原子提交代码、并发/rollback 测试。

---

## M0-019 引用存在性与同事务引用验证

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-006,M0-018

### A. 当前实现目标

任何持久对象写入前验证引用对象/版本存在，允许合法同事务新对象互引，但防明显自我证据引用。

### B. 为什么现在必须做

断裂引用会让多年后证据下钻失败，是硬工程错误。

### C. 具体实现方式

递归收集 Pydantic 对象中的 ObjectRef/SourceRef；查 DB 或 pending set。第一阶段阻止对象把自己的当前 revision 当作自己的证据；更复杂循环 M1/M3 处理。

### D. 技术 / 代码指导

参考实现 `_collect_refs/_reference_exists`。

### E. 推荐代码位置

`storage/sqlite_store.py`, 后续 `storage/reference_validator.py`

### F. 对外接口 / 命令

commit validation

### G. 必须编写的测试

不存在 ref 拒绝；同事务 EvidenceSet 引 Observation 成功；自引用 Claim/Evidence 当前版本拒绝。

### H. 验收标准

测试集无未发现断裂引用。

### I. 明确禁止

不要为了通过测试自动删除失效 ref。

### J. 本任务交付物

引用验证代码与测试。

---

## M0-020 历史世界读取与 Knowledge Cutoff

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-004,M0-018

### A. 当前实现目标

支持按 object revision、world revision、knowledge cutoff 读取，重建“当时 AI 能看到的世界”。

### B. 为什么现在必须做

测试系统可能已经生成未来人生数据，但被测 AI 绝不能提前看到；现实中也要区分后来知道的事实。

### C. 具体实现方式

get/list 查询加 as_of_world_revision 和 knowledge_cutoff；选择截止时点以前最新可见 revision。查询接口返回实际使用的 world revision/coverage。

### D. 技术 / 代码指导

参考实现 `get_payload/list_payloads`。后续 query 服务包装，不让 Worker 直接 SQL。

### E. 推荐代码位置

`storage/sqlite_store.py`, `query/history.py`

### F. 对外接口 / 命令

`get_payload(... as_of_world_revision, knowledge_cutoff)`

### G. 必须编写的测试

rev1 当前可见、rev2 明天 learned；今天查询必须读 rev1。

### H. 验收标准

隐藏未来数据 0 泄露；历史世界可重建。

### I. 明确禁止

禁止只按 recorded_at 判可见性。

### J. 本任务交付物

历史读取代码、泄露回归测试。

---

## M0-021 Task / Event 状态机冻结

**负责人级别**：总工程师亲自代码  
**前置依赖**：M0-012,M0-014

### A. 当前实现目标

将任务和事件允许的状态转换写成代码，防止编码代理随意跳状态。

### B. 为什么现在必须做

长期运行时“COMPLETED 再 RUNNING”“MERGED 再 ACTIVE”会造成不可解释历史。

### C. 具体实现方式

定义允许转换矩阵；服务层每次 transition 调验证。状态字段仍产生新对象 revision，而不是原地 UPDATE。

### D. 技术 / 代码指导

参考实现 `validate_task_transition`/`validate_event_transition`。

### E. 推荐代码位置

`services/state_machines.py`

### F. 对外接口 / 命令

transition validator

### G. 必须编写的测试

RUNNING→WAITING_RESULT 合法；COMPLETED→RUNNING 非法；CANDIDATE→REJECTED 合法；MERGED→ACTIVE 非法。

### H. 验收标准

非法转换明确报错；合法转换完整覆盖。

### I. 明确禁止

禁止服务层绕过状态机直接写状态。

### J. 本任务交付物

状态机、全转换参数化测试。

---

## M0-022 M0 契约总测试与冻结快照

**负责人级别**：总工程师验收  
**前置依赖**：M0-001~021

### A. 当前实现目标

用自动测试证明 M0 世界契约可用，并生成 schema snapshot 作为以后变更检测基准。

### B. 为什么现在必须做

M0 是后面所有模块的地基；必须在 M1 前发现模型字段和版本语义问题。

### C. 具体实现方式

覆盖 schema round-trip、枚举、时间、引用、revision、world revision、幂等、knowledge cutoff、Task/Event 状态机。导出 Pydantic JSON Schema 或结构 hash。

### D. 技术 / 代码指导

pytest；schema snapshot 进入仓库。CI 对冻结 schema diff 失败，必须显式批准。

### E. 推荐代码位置

`tests/unit/contracts/`, `tests/integration/storage/`, `schemas/r2/`

### F. 对外接口 / 命令

无新业务 API

### G. 必须编写的测试

至少复现运动会、未知人物、未来预测、Goal/Task 分离四个 fixture。

### H. 验收标准

全部测试通过；15+核心测试只是起点，M0 gate 最少 50 个断言场景。

### I. 明确禁止

禁止“先进入 M1，以后再补测试”。

### J. 本任务交付物

M0 gate 报告、schema snapshot、fixture。

---

# M1：共同世界内核与认知导航

目标是让多维世界真正可写、可查、可下钻。此阶段还不要求 AI 主动运行，但必须能完整保存运动会等复杂世界结构。

## M1-001 Observation 接入服务与去重

**负责人级别**：编码代理实现，总工程师审核  
**前置依赖**：M0 gate

### A. 当前实现目标

把虚拟 GPS、心率、IMU、文本、App数据统一写入 Observation，并支持来源消息去重。

### B. 为什么现在必须做

后续所有事件和认知都依赖底层资料；重复包不能制造虚假证据。

### C. 具体实现方式

定义 source_event_id/source_seq 或 dedupe_key；接入只做格式、单位、时间、数据质量清洗，不做语义判断。成功后通过 Core commit。

### D. 技术 / 代码指导

服务函数或 FastAPI endpoint 均可；先写 service，再暴露 HTTP。

### E. 推荐代码位置

`world/ingest.py`, `api/ingest.py`, `tests/integration/test_ingest.py`

### F. 对外接口 / 命令

`observation.ingest(batch)` 返回 object refs + world_revision

### G. 必须编写的测试

相同 source message 重放不新增 Observation；不同时间同值仍可新增。

### H. 验收标准

10k 条模拟心率可批量写入且不触发 AI；数据质量字段可查询。

### I. 明确禁止

禁止将 duplicate 简单按 value 去重；禁止生成 Event。

### J. 本任务交付物

接入服务、批量 fixture、性能基线。

---

## M1-002 Entity/别名/身份解析服务

**负责人级别**：总工程师审核核心逻辑  
**前置依赖**：M1-001,M0-008~010

### A. 当前实现目标

让未知人物、物品、地点可先以稳定 Entity 存在，后来通过 Claim+Evidence 修正身份；建立别名搜索但不自动强合并。

### B. 为什么现在必须做

声纹 A 后来知道是妈妈时，历史事件要自然变清楚；同名不能误并。

### C. 具体实现方式

entity.create；alias.add；entity.resolve 创建/修订 identity Claim，再更新 Entity revision 的 identity_claim_refs。字符串匹配只返回候选，不直接 resolve。

### D. 技术 / 代码指导

实体服务调用 Claim/Evidence 服务，禁止直接把 confidence 写在 name 上。

### E. 推荐代码位置

`world/entities.py`, `query/entity_index.py`

### F. 对外接口 / 命令

`entity.create`, `entity.search_candidates`, `entity.resolve`, `entity.expand`

### G. 必须编写的测试

A→妈妈；两个“小王”；“妈妈”在不同说话人上下文指不同实体。

### H. 验收标准

旧事件引用 P001 不变；展示时可解释当前身份和身份历史。

### I. 明确禁止

禁止 rename 等同 resolve；禁止全文命中自动合并。

### J. 本任务交付物

Entity service、alias index、测试。

---

## M1-003 Relation 时间化服务

**负责人级别**：编码代理实现  
**前置依赖**：M1-002

### A. 当前实现目标

创建/修订带有效期的关系，并能查看关系历史。

### B. 为什么现在必须做

用户关系会变化；“女朋友”可能成为“前女友”，不能永远覆盖同一字段。

### C. 具体实现方式

relation.upsert 创建新 Relation 或新 revision；valid_time 与 learned_at 分开；关系由 Claim/Evidence 支持。

### D. 技术 / 代码指导

查询 `relation.at(time)`、`relation.history(entity)`。

### E. 推荐代码位置

`world/relations.py`, `query/relations.py`

### F. 对外接口 / 命令

`relation.upsert/inspect/history`

### G. 必须编写的测试

同一人物关系变更；迟到资料修订有效期。

### H. 验收标准

任一时点能够回答“当时系统认为他们什么关系”。

### I. 明确禁止

禁止关系只存在 Entity.profile JSON。

### J. 本任务交付物

关系服务与时间查询测试。

---

## M1-004 维度注册与多重挂载服务

**负责人级别**：总工程师审核  
**前置依赖**：M1-001,M0-011

### A. 当前实现目标

实现 DimensionDefinition/Membership 的创建、查看、同一对象多维挂载。

### B. 为什么现在必须做

多维世界要求节点独立、维度可挂载，而不是复制多份事实。

### C. 具体实现方式

dimension.create 定义；membership.add 只存 ref；dimension.inspect 返回定义、成员计数、最近更新时间、生命周期。

### D. 技术 / 代码指导

第一版不要求复杂向量数据库；时间/subject/dimension SQL 索引够用。

### E. 推荐代码位置

`world/dimensions.py`, `query/dimensions.py`

### F. 对外接口 / 命令

`dimension.create/inspect`, `dimension.members.add/query`

### G. 必须编写的测试

同 Observation/Event 同时挂 3 个维度；底层对象只有一份。

### H. 验收标准

A01“同一基础资料多维引用不复制事实”通过。

### I. 明确禁止

禁止为每维度复制 payload。

### J. 本任务交付物

维度注册/挂载服务、A01测试。

---

## M1-005 Claim 创建、修订、版本比较服务

**负责人级别**：总工程师审核核心语义  
**前置依赖**：M1-004,M0-008,M0-009,M0-015

### A. 当前实现目标

给 AI Worker 一个安全接口创建/修订 Claim，不允许直接写对象 JSON。

### B. 为什么现在必须做

Claim 是整个认知世界最基础的“可争议认知单元”，必须保证证据和版本规则一致。

### C. 具体实现方式

claim.create 校验 claim_type/knowledge_state/confidence/EvidenceSet 可见性；claim.revise 必须给 reason 和新证据；compare_versions 输出变化字段。

### D. 技术 / 代码指导

服务层自动创建 Dependency 到 EvidenceSet；修订旧 Claim 不删除旧 revision。

### E. 推荐代码位置

`world/claims.py`

### F. 对外接口 / 命令

`claim.create/inspect/revise/compare_versions`

### G. 必须编写的测试

从 HYPOTHESIS 0.55 修订成 FACT/REPORTED 0.95；旧版本仍可读。

### H. 验收标准

AI无法提交不存在证据 ID；修订产生新 world revision。

### I. 明确禁止

禁止 Core 自动把语义“优化”为事实。

### J. 本任务交付物

Claim service、修订测试。

---

## M1-006 EvidenceSet 创建、冻结、展开服务

**负责人级别**：总工程师审核  
**前置依赖**：M1-001,M1-004,M0-009

### A. 当前实现目标

支持 AI 将当前查看的一段世界冻结成证据集合，之后可再次展开相同证据。

### B. 为什么现在必须做

这是“多维组合认证”的核心，不应只靠 prompt 临时记忆。

### C. 具体实现方式

显式成员模式：提交 refs；区间模式：selector 先按 knowledge_cutoff 查询并材料化 members，再保存 selector+members+coverage。evidence.inspect 展示支持/反对/上下文/缺失。

### D. 技术 / 代码指导

EvidenceSet 创建时固定 world_revision/knowledge_cutoff；后续新资料不自动加入旧 EvidenceSet，而是 stale/rebuild 新 revision。

### E. 推荐代码位置

`world/evidence.py`

### F. 对外接口 / 命令

`evidence_set.create/inspect/materialize`

### G. 必须编写的测试

15:00~16:00 心率+GPS+声音集合；第二天新增一条迟到声音后旧集合仍不变。

### H. 验收标准

证据下钻能回原始 Observation；EvidenceSet 自身有覆盖/缺失。

### I. 明确禁止

禁止“动态查询结果”作为永远不冻结的证据。

### J. 本任务交付物

Evidence service、运动会 fixture。

---

## M1-007 Event 生命周期服务

**负责人级别**：总工程师审核  
**前置依赖**：M1-005,M1-006,M1-002

### A. 当前实现目标

让 AI 创建候选事件，后续确认、修正、否定、合并、拆分，并能完整回放。

### B. 为什么现在必须做

用户世界里的“每天发生的事”主要通过 Event 组织，但事件由多维节点共同证明且允许猜错。

### C. 具体实现方式

event.create 必须至少一个 interpretation + EvidenceSet/Claim；transition 使用状态机；revise 给 supersedes；merge/split 建明确引用。event.expand 返回参与实体、证据、主张和历史。

### D. 技术 / 代码指导

Confidence 不由 Core 自动计算，AI给出并通过测试校准。

### E. 推荐代码位置

`world/events.py`

### F. 对外接口 / 命令

`event.create/expand/revise/reject/merge/split`

### G. 必须编写的测试

运动会→体育测试；两个重复候选合并；一个笼统“旅行”拆成航班+入住事件。

### H. 验收标准

事件不复制证据；历史解释可回放；修改影响范围可查。

### I. 明确禁止

禁止事件用字符串 status 自由跳转。

### J. 本任务交付物

Event service、生命周期测试。

---

## M1-008 Goal 服务与 Task 链接占位

**负责人级别**：编码代理实现  
**前置依赖**：M1-005

### A. 当前实现目标

实现 Goal 创建、修订、查询和与现有世界对象的关联；Task 运行逻辑在 M2。

### B. 为什么现在必须做

帮助机会需要知道与用户什么目标相关；教育 App也要围绕长期目标组织任务。

### C. 具体实现方式

goal.create 要区分 explicit/inferred；goal.update 产生新 revision；link_task 先实现引用校验。

### D. 技术 / 代码指导

Goal success criteria 第一版存结构/文本，M3 才做进度评估。

### E. 推荐代码位置

`world/goals.py`

### F. 对外接口 / 命令

`goal.create/update/query/link_task`

### G. 必须编写的测试

用户明确英语目标与 AI推断目标；否认推断目标后状态可 revised/rejected。

### H. 验收标准

Goal 与 Task ID 独立。

### I. 明确禁止

禁止每个 Goal 自动生成 Task。

### J. 本任务交付物

Goal service、测试。

---

## M1-009 Dependency 写入与反向查询

**负责人级别**：总工程师亲自/审核  
**前置依赖**：M1-005~008

### A. 当前实现目标

让高层对象写入时建立依赖，支持从某个底层对象查“谁依赖我”。

### B. 为什么现在必须做

M3纠错传播完全依赖这一能力。

### C. 具体实现方式

提供 dependency.create/bulk_create/reverse_lookup；高层 service 提交时同事务写 Dependency。区分 evidence_support、derived_from、task_depends_on 等类型。

### D. 技术 / 代码指导

SQLite 索引 dependency_object_id/revision；暂不做复杂图数据库。

### E. 推荐代码位置

`dependency/service.py`, `dependency/repository.py`

### F. 对外接口 / 命令

`dependency.create/inspect/reverse_lookup`

### G. 必须编写的测试

Claim→EvidenceSet；Event→Claim；Summary→Event；Task→Event。底层 rev变化可列出直接依赖。

### H. 验收标准

反向查询正确且不重复；引用 revision 明确。

### I. 明确禁止

禁止只在 metadata 保存依赖文字。

### J. 本任务交付物

依赖服务、索引、测试。

---

## M1-010 世界时间镜头 world.view/zoom/shift

**负责人级别**：总工程师审核接口  
**前置依赖**：M1-001,M1-004,M1-007

### A. 当前实现目标

让 AI 像操作“时间地图”一样选择1分钟、1天、1年等范围，而不是每次读全人生。

### B. 为什么现在必须做

这是认知工作台的核心操作之一，直接支持用户提出的“放大/缩小人生”。

### C. 具体实现方式

world.view(subject,time_range,dimensions,granularity,knowledge_cutoff) 返回 refs+coverage；zoom 在已有 view 基础切粒度；shift 前后移动保持长度和主体。

### D. 技术 / 代码指导

返回数据不强制一种视觉形态：数值曲线、状态区间、事件锚点、文本节点。

### E. 推荐代码位置

`query/world_view.py`

### F. 对外接口 / 命令

`world.view`, `world.zoom`, `world.shift`

### G. 必须编写的测试

从月视图 zoom 到某天；shift 前一天；knowledge cutoff 不越界。

### H. 验收标准

AI可以用少量返回快速定位，再下钻；coverage 和 omitted_count 可见。

### I. 明确禁止

禁止 zoom 只是把同一大 JSON 重新格式化。

### J. 本任务交付物

时间镜头接口、性能/边界测试。

---

## M1-011 多维对齐、比较和机械变化检测

**负责人级别**：编码代理实现，总工程师审核边界  
**前置依赖**：M1-010

### A. 当前实现目标

把多个维度按同一时间窗对齐，比较两个时期，提供机械差异/共变，但不在底层声明因果。

### B. 为什么现在必须做

AI需要框选“使用AI频率升高那两个月”，再对齐用户世界其他维度。

### C. 具体实现方式

world.align 返回各维度 coverage；compare 返回统计差异；detect_changes 只输出数值/状态变化段，不写“因为分手”。

### D. 技术 / 代码指导

数值可以基础统计；事件/文本返回 count/refs；缺失≠0。

### E. 推荐代码位置

`query/align.py`, `query/compare.py`, `query/change_detection.py`

### F. 对外接口 / 命令

`world.align/compare/detect_changes`

### G. 必须编写的测试

睡眠缺3天不能当0；AI聊天频率峰值与事件时间窗对齐。

### H. 验收标准

机械检测输出可作为 Wake 输入/AI证据，不产生语义因果。

### I. 明确禁止

禁止底层输出“用户压力增加”。

### J. 本任务交付物

对齐/比较工具与缺失数据测试。

---

## M1-012 世界搜索、实体解析与关键词超链

**负责人级别**：总工程师审核  
**前置依赖**：M1-002,M1-003,M1-007

### A. 当前实现目标

建立关键词/实体/事件/关系/概念的横向搜索入口，支持逐步缩小范围。

### B. 为什么现在必须做

用户希望“生日→妈妈→礼物→过去几年”的全球关联，不应每次通读全部人生。

### C. 具体实现方式

world.search 支持 text/entity/time/subject/type filters；先返回候选实体和匹配类别，不自动把同词合并。follow_links 按类型/深度导航。

### D. 技术 / 代码指导

第一版 SQLite FTS5 + Entity alias index；语义向量作为可替换适配器，不是 M1 阻塞项。

### E. 推荐代码位置

`query/search.py`, `query/fts.py`, `query/links.py`

### F. 对外接口 / 命令

`world.search`, `world.follow_links`, `entity.expand`

### G. 必须编写的测试

搜索“妈妈”返回实体候选+文本命中；“妈妈+生日+礼物+近3年”逐步过滤。

### H. 验收标准

搜索结果有 source refs/时间/coverage；不因相同文字错误合并实体。

### I. 明确禁止

禁止全文搜索命中=事实成立。

### J. 本任务交付物

搜索引擎、超链接口、生日测试。

---

## M1-013 证据下钻 evidence.read/trace 与事件展开

**负责人级别**：总工程师审核  
**前置依赖**：M1-006,M1-009,M1-012

### A. 当前实现目标

从高层 Claim/Event/Summary 一路追到原始证据，回答“为什么”。

### B. 为什么现在必须做

这是多维金字塔可解释和纠错的生命线。

### C. 具体实现方式

evidence.read 读取具体版本；trace 按 Dependency + EvidenceSet 逐层返回 DAG，并标 support/counter/missing；event.expand 把事件结构呈现。

### D. 技术 / 代码指导

递归深度/节点数必须有限制和 cursor；避免一次拉完整人生。

### E. 推荐代码位置

`query/evidence_trace.py`

### F. 对外接口 / 命令

`evidence.read`, `evidence.trace`, `event.expand`

### G. 必须编写的测试

“学习能力提高”→数学/英语/编程→某项目→某天对话；运动会→心率/声音/地点/聊天。

### H. 验收标准

每个结论可追到至少一个可见原始或更低层依据；断裂引用硬失败。

### I. 明确禁止

禁止 trace 隐藏反对证据。

### J. 本任务交付物

追溯接口、树/DAG fixture。

---

## M1-014 索引水位、重建与 STALE_INDEX

**负责人级别**：编码代理实现  
**前置依赖**：M1-001~013

### A. 当前实现目标

让时间、实体、关键词、维度索引可重建并显式告诉调用者“索引是否跟上世界版本”。

### B. 为什么现在必须做

长期系统索引会延迟；AI不能把旧搜索结果当最新世界。

### C. 具体实现方式

每类索引保存 last_world_revision；查询返回 index_watermark；若落后且请求要求 strict_freshness，返回 STALE_INDEX 或回退主库。

### D. 技术 / 代码指导

SQLite FTS5/普通 B-tree；提供 rebuild CLI。

### E. 推荐代码位置

`query/indexes.py`, `cli/rebuild_index.py`

### F. 对外接口 / 命令

`index.status`, `index.rebuild`

### G. 必须编写的测试

人工落后10 revisions；strict 查询报 stale；rebuild 后一致。

### H. 验收标准

索引可全部删掉重建，不是事实来源。

### I. 明确禁止

禁止把向量索引当唯一真相存储。

### J. 本任务交付物

索引管理、重建命令、测试。

---

## M1-015 开发者控制台最小版

**负责人级别**：编码代理实现  
**前置依赖**：M1-010~014

### A. 当前实现目标

让人类能查看同一个世界：时间范围、对象、事件、证据、版本和操作日志。

### B. 为什么现在必须做

我们要优化“AI如何使用世界”；如果看不到它读了什么、改了什么，错误无法定位。

### C. 具体实现方式

先做只读控制台：当前 world revision、对象搜索、time view、Entity/Event/Claim/Evidence 展开、revision history、operation audit。M2再加任务/Wake/回放。

### D. 技术 / 代码指导

FastAPI + 简单 HTML/React/Vue 任一；UI技术不冻结，接口冻结。

### E. 推荐代码位置

`console/`, `api/debug.py`

### F. 对外接口 / 命令

调用与 AI 相同 query service；禁止独立 SQL。

### G. 必须编写的测试

开发者点一个 Event 可看到 EvidenceSet 和原始 Observation；可切 revision。

### H. 验收标准

无需美观，但必须准确展示 unknown/stale/revision。

### I. 明确禁止

禁止控制台自己计算另一套认知。

### J. 本任务交付物

控制台页面、截图/录像、端到端测试。

---

## M1-016 M1 贯穿案例：运动会→体育测试修正

**负责人级别**：总工程师验收  
**前置依赖**：M1-001~015

### A. 当前实现目标

用一个完整世界案例验证 M1 的所有对象与查询，而不是各模块只做单测。

### B. 为什么现在必须做

这是用户最早给出的核心例子，能够验证多维独立、Event组合、证据、实体、修订和下钻。

### C. 具体实现方式

输入：GPS学校、操场视觉文本、加油录音、心率/IMU、用户“跑步第一名”；先建立 CANDIDATE“运动会”；后续输入“其实是校内体育测试”，Event revise。

### D. 技术 / 代码指导

固定 fixture + service calls，不需要真实大模型；先验证世界结构。

### E. 推荐代码位置

`tests/scenarios/test_sports_event_world.py`

### F. 对外接口 / 命令

调用 M1所有核心接口

### G. 必须编写的测试

检查 Event 不复制数据、EvidenceSet完整、旧认知可回放、新认知可见、关键词可搜、实体不变。

### H. 验收标准

一个脚本可从空库跑完并输出可读轨迹。

### I. 明确禁止

禁止为了通过场景写专用 if sports。

### J. 本任务交付物

贯穿测试、可回放 JSON、控制台演示。

---

# M2：主动运行、任务系统与 AI 认知工作台

目标是让系统在没有用户提问时也能醒来、调查、决定帮助/沉默、留下未来任务并可恢复。

## M2-001 离散事件虚拟时钟

**负责人级别**：总工程师审核  
**前置依赖**：M1 gate

### A. 当前实现目标

实现虚拟时间推进，下一 Observation、Task 到期、Watch检查或结果到达决定下一步，不需要真实等三个月。

### B. 为什么现在必须做

定时任务、长期跟进和年度测试必须在可重复虚拟时间里运行。

### C. 具体实现方式

Clock 保存 now；事件优先队列；advance_to_next 不越过最早到期点；虚拟时间与真实执行耗时分别记录。

### D. 技术 / 代码指导

Python heapq 或数据库队列即可。世界对象时间仍用真实 datetime 类型，只是由 virtual clock 提供 now。

### E. 推荐代码位置

`simulator/clock.py`, `tasks/scheduler_clock.py`

### F. 对外接口 / 命令

`clock.now/advance/next_due`

### G. 必须编写的测试

三个月后 Task 不用等待；同时到期稳定排序；时区日期转换。

### H. 验收标准

同 seed 重放时间顺序一致。

### I. 明确禁止

禁止模型调用耗时改变虚拟人生先后顺序（运行模式测试除外）。

### J. 本任务交付物

虚拟时钟、事件队列测试。

---

## M2-002 机械触发引擎：Observation≠Wake

**负责人级别**：总工程师亲自审核/关键代码  
**前置依赖**：M2-001,M1-001

### A. 当前实现目标

建立数值幅度、趋势、状态切换、持续时间、关键词/实体、长时间无更新等机械触发，只有命中才形成 Wake。

### B. 为什么现在必须做

高频传感器每条都 Wake 会让 AI 永久在线；触发器又不能偷偷做语义判断。

### C. 具体实现方式

Observation commit 后把变更摘要投递 trigger engine；rule evaluator 只能使用确定性规则。关键词匹配返回原句/实体候选，不写事件解释。

### D. 技术 / 代码指导

配置化 TriggerRule；规则输出 WakeCandidate；Wake service 再合并/冷却。

### E. 推荐代码位置

`wake/rules.py`, `wake/engine.py`

### F. 对外接口 / 命令

`trigger.evaluate(observation_updates) -> WakeCandidate[]`

### G. 必须编写的测试

1000条稳定心率 0 Wake；一次从80→160命中；“女朋友名字”关键词唤醒但不写“吵架”。

### H. 验收标准

高频输入下模型调用次数由规则控制；语义结论 0 个来自 trigger engine。

### I. 明确禁止

禁止引入本地小模型判断情绪/事件。

### J. 本任务交付物

触发引擎、规则 fixture、性能测试。

---

## M2-003 Wake 去重、时间窗合并、冷却与升级

**负责人级别**：总工程师审核  
**前置依赖**：M2-002

### A. 当前实现目标

把同一连续情境的重复命中合成可解释 Wake，同时新来源/强度升级仍能唤醒。

### B. 为什么现在必须做

用户周围持续喊“加油”不能每秒唤醒；但突然加入安全信号必须立即升级。

### C. 具体实现方式

dedupe_key=subject+rule+context window；保存 first/last/count/evidence refs/peak；cooldown 期间积累。新 independent source 或 severity 升级产生新 wake/提高 priority。

### D. 技术 / 代码指导

实现 WakeRepository + merge policy；所有合并有审计。

### E. 推荐代码位置

`wake/service.py`, `wake/policy.py`

### F. 对外接口 / 命令

`wake.create_or_merge`, `wake.release_after_cooldown`

### G. 必须编写的测试

同词100次→1 wake count=100；冷却后显著新证据→新处理机会。

### H. 验收标准

R1-06/R1-08 通过；证据不丢。

### I. 明确禁止

安全 Wake 永远不被普通冷却屏蔽。

### J. 本任务交付物

Wake 服务、去重测试。

---

## M2-004 Wake 队列、优先级、抢占和饿死保护

**负责人级别**：编码代理实现，总工程师审核策略  
**前置依赖**：M2-003

### A. 当前实现目标

调度多个 Wake/Task，安全与强时效优先，普通任务等待但不能永久饿死。

### B. 为什么现在必须做

AI可能正在做年度总结时出现疑似摔倒；操作系统必须先处理紧急事件。

### C. 具体实现方式

priority queue；Safety 独立高优先；普通 queue 根据等待时间 aging；同主体第一阶段只允许一个语义写会话，其他入队。

### D. 技术 / 代码指导

不要让低级 scheduler 判断“是否值得帮助”，只安排已存在 Wake 的顺序。

### E. 推荐代码位置

`wake/scheduler.py`

### F. 对外接口 / 命令

`scheduler.enqueue/dequeue/ack/requeue`

### G. 必须编写的测试

普通会话中安全 Wake 抢占；100个普通任务后最老任务最终被执行。

### H. 验收标准

无丢 Wake；优先级规则可审计。

### I. 明确禁止

禁止 scheduler 调模型判断 priority。

### J. 本任务交付物

调度器、抢占测试。

---

## M2-005 Task Center 核心状态机和持久调度

**负责人级别**：总工程师关键代码/审核  
**前置依赖**：M0-021,M2-001,M2-004

### A. 当前实现目标

把即时、定时、截止、待办、周期、跟进、观察、验证、维护、App 十类任务统一到可恢复状态机。

### B. 为什么现在必须做

“以后提醒”“继续观察”“等用户反馈”都必须离开模型上下文进入持久系统。

### C. 具体实现方式

Task service 所有 transition 走冻结状态机；创建 READY/WAITING；scheduler 根据 next_wake/deadline/recurrence 生成 Wake；每次 transition 新 revision。

### D. 技术 / 代码指导

持久化 Task 不是 cron 字符串集合；Task 有原因、Goal、完成条件、取消条件、依赖和结果。

### E. 推荐代码位置

`tasks/service.py`, `tasks/repository.py`, `tasks/scheduler.py`

### F. 对外接口 / 命令

`task.create/update/query/cancel/transition`

### G. 必须编写的测试

十类任务状态覆盖；完成/取消后不再执行；等待证据后新资料到达变 READY。

### H. 验收标准

停机重启任务不丢；状态转换非法会拒绝。

### I. 明确禁止

禁止 Task 完成只因为“模型输出了完成”。必须满足 completion condition 或明确人工/环境结果。

### J. 本任务交付物

任务中心、状态迁移测试。

---

## M2-006 定时/截止/周期/待办/跟进具体语义

**负责人级别**：编码代理实现  
**前置依赖**：M2-005

### A. 当前实现目标

补齐不同 Task 类型的时间规则和恢复策略。

### B. 为什么现在必须做

一年后、360天后、每月末、无截止待办不是同一语义。

### C. 具体实现方式

scheduled 绝对/相对；deadline 提前检查+超时；recurring 父任务+occurrence_id；todo 必须 next review；follow-up 绑定原 Action/Outcome。停机后策略明确 catch-up/skip/merge/expire。

### D. 技术 / 代码指导

使用 datetime + timezone；周期规则可先用 dateutil/自定义简单 RRULE subset。

### E. 推荐代码位置

`tasks/time_rules.py`, `tasks/types.py`

### F. 对外接口 / 命令

Task service 内部策略

### G. 必须编写的测试

妈妈生日一年后；月末无31日；错过3次周期任务恢复；待办无 deadline 仍会盘点。

### H. 验收标准

每种时间规则都有确定性测试。

### I. 明确禁止

禁止所有时间任务都转换成固定秒数。

### J. 本任务交付物

时间规则、恢复测试。

---

## M2-007 观察任务与验证任务

**负责人级别**：总工程师审核语义  
**前置依赖**：M2-005,M2-002

### A. 当前实现目标

允许 AI 暂时不下结论，“未来14天观察工作投入”“等新证据确认A是谁”。

### B. 为什么现在必须做

不确定认知不能强迫立即问用户或变事实；像人一样先观察是系统自然性的关键。

### C. 具体实现方式

Watch 分 mechanical condition 与 semantic question；机械部分命中只 Wake AI；语义结论仍由 AI判断。验证任务绑定 Claim 和 evidence gap。到期结果区分 MATCHED / NOT_MATCHED_WITH_SUFFICIENT_DATA / INSUFFICIENT_DATA。

### D. 技术 / 代码指导

Watch 条件使用有限 DSL/JSON，不允许任意 Python eval。

### E. 推荐代码位置

`tasks/watch.py`, `tasks/verification.py`

### F. 对外接口 / 命令

`watch.register`, `watch.evaluate`, `verification.review`

### G. 必须编写的测试

14天无足够数据→INSUFFICIENT，不得当“未匹配”；新声纹证据命中验证任务。

### H. 验收标准

观察期和终止条件明确；不会无限后台运行。

### I. 明确禁止

禁止本地 Watch 写“用户持续挫败”。

### J. 本任务交付物

Watch/Verification 服务、测试。

---

## M2-008 Action / Outcome 执行收据与幂等

**负责人级别**：总工程师审核关键路径  
**前置依赖**：M2-005,M0-016

### A. 当前实现目标

区分“AI决定做”“动作已提交”“动作已执行”“现实结果如何”，支持失败/超时不重复。

### B. 为什么现在必须做

管家系统最危险的问题之一是重试时重复发消息、重复购买、重复设置任务。

### C. 具体实现方式

action.propose 产生 Action；executor 用 execution_id 调模拟能力；先查 receipt 再重试；Outcome 独立写入。OUTCOME_UNKNOWN 保留等待任务。

### D. 技术 / 代码指导

第一阶段只模拟发送消息、提醒、教育动作，不触碰真实外部系统。

### E. 推荐代码位置

`actions/service.py`, `actions/executor.py`, `simulator/capabilities.py`

### F. 对外接口 / 命令

`action.propose/status`, `outcome.record`

### G. 必须编写的测试

模型超时但模拟执行成功；恢复后查 receipt 不重复；消息送达但用户无回应 outcome 分开。

### H. 验收标准

重复执行率0；unknown 路径正确。

### I. 明确禁止

禁止失败就直接重做外部动作。

### J. 本任务交付物

行动执行器、收据、测试。

---

## M2-009 workspace.open 唤醒初始工作包

**负责人级别**：总工程师审核接口  
**前置依赖**：M2-004~008,M1 query services

### A. 当前实现目标

AI醒来第一眼得到当前时间、Wake原因、紧急事项、世界概要、Task/Goal、未确认认知、AI自身状态、数据质量和可用工具。

### B. 为什么现在必须做

模型不应每次从空白 prompt 开始，也不应自动加载全部人生。

### C. 具体实现方式

工作包只给相关摘要+索引入口；所有内容带 refs/revision/age/coverage。当前地点若过时必须标 stale。

### D. 技术 / 代码指导

Pydantic WorkspaceSnapshot；由 query/task/wake/self 服务聚合，不写新认知。

### E. 推荐代码位置

`workspace/service.py`, `workspace/contracts.py`

### F. 对外接口 / 命令

`workspace.open(session/wake)`

### G. 必须编写的测试

无地点显示 unknown；过期地点显示 age；有500条相关历史只返回摘要+查询入口。

### H. 验收标准

W01初始面板字段完整；无偷偷推断。

### I. 明确禁止

禁止把自然语言大摘要作为唯一入口。

### J. 本任务交付物

workspace snapshot 接口、测试。

---

## M2-010 AI 世界操作工具集

**负责人级别**：总工程师审核接口，编码代理实现  
**前置依赖**：M2-009,M1 gate

### A. 当前实现目标

把人类“拖时间轴/点维度/搜索/下钻”映射成结构化工具，让 AI 自由组合。

### B. 为什么现在必须做

AI像人一样操作世界的本质不是鼠标，而是稳定结构化动作。

### C. 具体实现方式

暴露 world.view/zoom/shift/select_dimensions/align/compare/search/follow_links、event.expand、entity.expand、evidence.read/trace、dependency.inspect、goal/task查询。每次工具返回 source_refs/coverage/warnings/world_revision。

### D. 技术 / 代码指导

工具 schema 由 Pydantic 生成 JSON Schema 给模型；禁止自由 SQL。

### E. 推荐代码位置

`workspace/tools.py`, `workspace/tool_registry.py`

### F. 对外接口 / 命令

认知工作台规格中 5.2~5.5 接口

### G. 必须编写的测试

AI可从“生日”搜索→妈妈实体→历年事件→礼物→财务维度；工具参数非法返回协议错误。

### H. 验收标准

所有读写都经过同一 Core service；AI和控制台操作世界规则一致。

### I. 明确禁止

禁止把固定调用顺序写进工具层。

### J. 本任务交付物

工具注册表、schema、集成测试。

---

## M2-011 Session 快照、Checkpoint 与跨会话接续

**负责人级别**：总工程师关键代码/审核  
**前置依赖**：M2-008~010

### A. 当前实现目标

每次 AI 会话固定开始世界版本，记录已做操作、已提交修改、未决问题和下一步；中断可以恢复。

### B. 为什么现在必须做

长期管家不能因为模型超时/进程重启就忘记已经做过什么或重复行动。

### C. 具体实现方式

Session 开始保存 snapshot_world_revision；读新资料必须显式 workspace.changes/refresh；checkpoint 保存 committed refs、pending operations、tasks created、unresolved questions。

### D. 技术 / 代码指导

Checkpoint 不保存私密思维链，只保存可观察事实。

### E. 推荐代码位置

`workspace/session.py`

### F. 对外接口 / 命令

`session.start/checkpoint/finish/resume`, `workspace.changes`

### G. 必须编写的测试

模型在 Action提交后断开；恢复知道已提交 execution_id；世界在会话中更新但旧快照不自动变。

### H. 验收标准

R1-10/W12/A06 通过；无重复动作。

### I. 明确禁止

禁止把完整模型 hidden reasoning 当checkpoint依赖。

### J. 本任务交付物

Session 服务、恢复测试。

---

## M2-012 AI Worker 模型适配与工具循环

**负责人级别**：总工程师审核主循环  
**前置依赖**：M2-009~011

### A. 当前实现目标

让同一个 AI 在 Workspace 上自主选择观察范围和工具，形成/修正认知、Task、Action 或 SILENCE。

### B. 为什么现在必须做

这是“AI如何操作架构”的实际运行核心，不能退化成固定十三步脚本。

### C. 具体实现方式

Adapter 接模型；首包 workspace.open；模型可多轮 tool calls；Core 校验工具参数和 expected revision；达到预算/等待未来条件时 checkpoint。响应层要求最终 decision summary 和必要结构化 writes。

### D. 技术 / 代码指导

先 Mock adapter 做确定性测试，再真实模型。系统提示只规定责任/约束/工具，不强制先看哪个维度。

### E. 推荐代码位置

`ai_worker/runner.py`, `ai_worker/model_adapter.py`, `ai_worker/prompts/core_system.md`

### F. 对外接口 / 命令

`run_session(wake_id)`

### G. 必须编写的测试

同场景模型可以先搜关键词或先看当前窗口；无认知增量时不写反思占位；证据不足可 WATCH/SILENCE。

### H. 验收标准

AI可自由跳过工作项但运行责任完整；所有写入经Core。

### I. 明确禁止

禁止“每次必须先读全局人生”；禁止 AI Worker 直连数据库。

### J. 本任务交付物

Worker、Mock测试、真实模型烟测。

---

## M2-013 主动帮助决策记录

**负责人级别**：总工程师审核语义  
**前置依赖**：M2-012

### A. 当前实现目标

每次帮助/不帮助留下结构化决策记录：机会、Goal/状态/承诺、证据、时机、方式、预期结果、如何跟进。

### B. 为什么现在必须做

我们最终要优化的是“帮助是否有价值”，不是事件数量。没有记录就无法评估主动性。

### C. 具体实现方式

允许 ACT_NOW/ASK/SUGGEST/DEFER/WATCH/SILENCE。若需要未来结果，必须创建跟进 Task。SILENCE 也可以有简短可审计依据。

### D. 技术 / 代码指导

记录可作为 Session decision，不强制另建世界 Claim，除非内容值得长期认知。

### E. 推荐代码位置

`ai_worker/decisions.py`, `workspace/contracts.py`

### F. 对外接口 / 命令

`decision.record` 或 session result

### G. 必须编写的测试

跑步时历史偏好不打扰→SILENCE；奖品未找回→FOLLOW_UP；无证据→WATCH。

### H. 验收标准

每个 Action 有预期结果和后续观察方法；不必要打扰可统计。

### I. 明确禁止

禁止“Wake=一定发消息”。

### J. 本任务交付物

决策记录格式、场景测试。

---

## M2-014 一天虚拟人和观测生成器

**负责人级别**：编码代理实现，评估侧严格隔离  
**前置依赖**：M2-001

### A. 当前实现目标

生成同一虚拟人的真实隐藏状态和可见 Observation 流，包含帮助机会、应沉默、证据不足场景。

### B. 为什么现在必须做

没有可控世界就无法知道 AI 判断对不对，也无法公平比较。

### C. 具体实现方式

Truth layer 定义事件/因果/偏好；Observation generator 只按可见时间产出数据；支持噪声、延迟、缺失、重复。Core只拿 observation feed。

### D. 技术 / 代码指导

Simulator独立数据库/目录；文件名/ID不能泄露“答案”。seed固定可重放。

### E. 推荐代码位置

`simulator/world.py`, `simulator/observations.py`, `evaluator/truth.py`

### F. 对外接口 / 命令

`sim.next_event/feed_until`

### G. 必须编写的测试

运动会正例、看似心率异常但跑步无需健康警报、用户未来预测不是真值。

### H. 验收标准

同 seed 可重放；隐藏真值无法从 Core import/query。

### I. 明确禁止

禁止在Observation metadata写 `ground_truth_event=...`。

### J. 本任务交付物

一天生成器、3个基础虚拟人、隔离测试。

---

## M2-015 M2端到端：无用户提问主动闭环

**负责人级别**：总工程师验收  
**前置依赖**：M2-001~014

### A. 当前实现目标

从空库开始：虚拟世界进数据→机械触发→Wake→AI Worker调查→Event/Claim→帮助或沉默→Task→未来到期→Outcome。

### B. 为什么现在必须做

这是第一轮最重要的“系统活起来”证明。

### C. 具体实现方式

至少跑三种：1)有效主动帮助；2)应该沉默；3)证据不足创建观察/验证任务。每一步记录世界版本和工具轨迹。

### D. 技术 / 代码指导

先 Mock 模型确保工程路径，再真实模型跑同数据。

### E. 推荐代码位置

`tests/scenarios/test_active_loop_day.py`

### F. 对外接口 / 命令

所有 M2 接口

### G. 必须编写的测试

无用户主动问“发生了什么”；系统自行唤醒。重启中断一次，恢复不重复行动。

### H. 验收标准

R1-09/R1-10/W10/A07/A08/A09 同时通过。

### I. 明确禁止

禁止测试脚本直接调用“create event sports”绕过 AI Worker。

### J. 本任务交付物

可回放轨迹、控制台演示、真实模型结果。

---

# M3：纠错、多尺度总结、派生维度与双世界

目标是证明世界能长期生长，同时允许错误被修正，高层认知永远能回到底层。

## M3-001 依赖失效与纠错传播引擎

**负责人级别**：总工程师亲自设计/关键代码  
**前置依赖**：M1-009,M2 Task

### A. 当前实现目标

底层 Claim/Entity/Event 修订后找到受影响对象，标记 stale/needs_review，创建去重复核 Task，而不是自动机械改语义。

### B. 为什么现在必须做

AI可以猜错，架构价值之一就是错误能被修正而不是越积越深。

### C. 具体实现方式

change event→reverse dependency query→按 dependency type 标对象状态→暂停未执行高风险Task→创建一个 review task。AI重审后写新 revision。

### D. 技术 / 代码指导

传播引擎只做“哪些需要复核”，不替大模型判断新答案。限制最大传播深度/批量，防爆炸。

### E. 推荐代码位置

`dependency/invalidation.py`, `dependency/review_tasks.py`

### F. 对外接口 / 命令

`dependency.invalidate_from(ref)`

### G. 必须编写的测试

P001爸爸→妈妈：生日Event、Summary、Task标复核；不相关工作事件不动。

### H. 验收标准

修正覆盖率高、误伤率低；无无限循环Task。

### I. 明确禁止

禁止数据库级 cascade delete。

### J. 本任务交付物

失效传播引擎、纠错场景测试。

---

## M3-002 EvidenceSet stale/rebuild

**负责人级别**：总工程师审核  
**前置依赖**：M3-001,M1-006

### A. 当前实现目标

迟到Observation、底层revision变化或selector覆盖变化时标证据集合过期，并可基于原 selector 重建新 revision。

### B. 为什么现在必须做

区间证据必须反映“当时证据”和“后来新增证据”的差别。

### C. 具体实现方式

Dependency把 EvidenceSet 绑定成员/selector；新资料匹配 selector 时触发维护 Task，不直接修改旧集合。rebuild 保存新 knowledge window、成员、coverage。

### D. 技术 / 代码指导

旧 EvidenceSet revision 永久保留；Claim 可选择是否重审。

### E. 推荐代码位置

`world/evidence_lifecycle.py`

### F. 对外接口 / 命令

`evidence.mark_stale/rebuild/compare_versions`

### G. 必须编写的测试

昨天两周睡眠证据，今天补到一条迟到数据；旧版本不变，新版本成员+1。

### H. 验收标准

可清楚回答“当时基于什么”和“现在基于什么”。

### I. 明确禁止

禁止自动把新数据偷偷塞进旧 EvidenceSet。

### J. 本任务交付物

stale/rebuild 服务与测试。

---

## M3-003 Event/身份修正的完整链路

**负责人级别**：总工程师验收关键场景  
**前置依赖**：M3-001,M3-002

### A. 当前实现目标

验证“错认爸爸→妈妈”或“运动会→体育测试”能够影响世界和未来任务，同时保留历史。

### B. 为什么现在必须做

这是用户明确要求 AI总结自己判断错误和修复认知的基础。

### C. 具体实现方式

新 evidence→Claim revise/entity.resolve→Dependency invalidation→Review Task→AI Worker重审Event/Summary/Task→AI自身世界记录可验证错误经验候选。

### D. 技术 / 代码指导

先用 Mock 预期输出，再真实模型。

### E. 推荐代码位置

`tests/scenarios/test_correction_propagation.py`

### F. 对外接口 / 命令

跨 Claim/Entity/Event/Task/AI-self

### G. 必须编写的测试

检查未执行错误生日提醒被暂停；已发送行动不“回滚”，只可补救；历史版本可见。

### H. 验收标准

A04/R2-11/R2-15通过；传播终止。

### I. 明确禁止

禁止直接 SQL 批量把所有“爸爸”字符串替换“妈妈”。

### J. 本任务交付物

完整纠错轨迹和回归 fixture。

---

## M3-004 日总结生成机制

**负责人级别**：总工程师审核语义和接口  
**前置依赖**：M3-002,M2 Worker

### A. 当前实现目标

对每个活跃维度/事件世界生成日尺度 Summary，保留 coverage、EvidenceSet 和 Claim refs，不删除原始资料。

### B. 为什么现在必须做

AI要能一眼看一天，但又能回到原话。总结是新观察层，不是压缩覆盖。

### C. 具体实现方式

Summary Task 到期唤醒 AI；AI选择相关维度生成主张和总结；Core 保存 Summary+EvidenceSet+Dependencies。无数据或不值得总结可 MISSING/PARTIAL。

### D. 技术 / 代码指导

先实现事件维度、数值/频率维度、认知类三种模板/工具提示，但最终语义仍由大模型。

### E. 推荐代码位置

`summaries/service.py`, `ai_worker/summary_mode.py`

### F. 对外接口 / 命令

`summary.create/expand`

### G. 必须编写的测试

一天1000条Observation→一个可读日总结；点总结能下钻事件和原始；缺失8小时显示coverage。

### H. 验收标准

原始数据数量不变；Summary 删除不影响事实。

### I. 明确禁止

禁止日总结生成后删除日志。

### J. 本任务交付物

日总结任务、接口、测试。

---

## M3-005 周/月总结与跨层下钻

**负责人级别**：总工程师审核  
**前置依赖**：M3-004,M3-001

### A. 当前实现目标

实现原始→日→周→月的第一阶段最小多尺度体系，并支持跳层下钻。

### B. 为什么现在必须做

R2明确完整3/5/10年可后移，但多尺度机制本身不能后移。

### C. 具体实现方式

周总结可引用日 Summary + 关键原始/Event；月总结引用周/日/关键Event。summary.expand 返回子层+coverage，AI也可以直接 world.search 原始，不强制走树。

### D. 技术 / 代码指导

Summary status CURRENT/STALE/PARTIAL/MISSING。Revision随重算增加。

### E. 推荐代码位置

`summaries/hierarchy.py`, `query/summary_expand.py`

### F. 对外接口 / 命令

`summary.expand`, `summary.rebuild`

### G. 必须编写的测试

月→周→日→Event→Observation；也可月→某Event直接跳；底层修正让上层 stale。

### H. 验收标准

R2-12/13/14通过。

### I. 明确禁止

禁止固定要求 AI先看月总结再看日。

### J. 本任务交付物

周/月总结和下钻测试。

---

## M3-006 动态维度 Candidate→Trial→Active

**负责人级别**：总工程师审核机制  
**前置依赖**：M3-005,M1-004

### A. 当前实现目标

允许 AI自由提出候选维度，但长期高成本维护需经过试用和效果验证。

### B. 为什么现在必须做

既要避免维度爆炸，也不能用开发者主观规则阻止AI创造真正有价值的新维度。

### C. 具体实现方式

dimension.propose 创建 Candidate，记录定义、已有维度不足、数据来源、更新方式、预期用户价值、重复性、维护成本、失效条件。工程检查通过→Trial。后续由测试收益/使用记录决定 Active。

### D. 技术 / 代码指导

不使用另一个AI做绝对“价值审批”；语义价值通过实际后续任务实验。

### E. 推荐代码位置

`dimensions/lifecycle.py`, `dimensions/proposal.py`

### F. 对外接口 / 命令

`dimension.propose/transition`

### G. 必须编写的测试

“用户寻求陪伴频率”候选；重复“综合学习水平”与已有维度提示可能合并；资源不足停留candidate。

### H. 验收标准

Candidate 不自动 Active；试用历史可见。

### I. 明确禁止

禁止“模型说有用”=Active。

### J. 本任务交付物

维度生命周期服务、测试。

---

## M3-007 维度合并/拆分/休眠/重新激活

**负责人级别**：总工程师审核  
**前置依赖**：M3-006,M1-009

### A. 当前实现目标

完整管理动态维度生命周期，减少重复和维护浪费，同时不破坏历史引用。

### B. 为什么现在必须做

长期运行必然出现“学习能力/综合学习水平”等重复或过宽维度。

### C. 具体实现方式

merge 创建映射而不改旧ID；split 创建新维度并记录来源；dormant 降低维护频率但保留历史；未完成Task依赖的维度不得无记录休眠。

### D. 技术 / 代码指导

所有 transition 新 revision + reason + impact refs；查询对 retired/merged 给 redirect。

### E. 推荐代码位置

`dimensions/lifecycle.py`

### F. 对外接口 / 命令

`dimension.merge/split/dormant/reactivate`

### G. 必须编写的测试

低频但关联妈妈生日长期Task的维度不可因30天无查询被清理；重复维度合并后旧引用仍解析。

### H. 验收标准

R1-05/R2-07通过。

### I. 明确禁止

禁止物理删除历史维度以“清理空间”。

### J. 本任务交付物

生命周期转换、历史引用测试。

---

## M3-008 DimensionDerivation 高层认知服务

**负责人级别**：总工程师关键审核  
**前置依赖**：M3-002,M3-006

### A. 当前实现目标

真正实现“数学+英语+编程→学习能力”式认知金字塔，并允许反例、新证据让派生关系重审。

### B. 为什么现在必须做

这是多维世界区别普通标签/记忆库的核心机制之一。

### C. 具体实现方式

AI创建 output dimension Candidate/Trial，再创建 Derivation 引 input refs、EvidenceSet、scope/time、confidence、counterexamples。输入依赖失效→derivation stale/review。

### D. 技术 / 代码指导

Derivation不是固定公式，可以是大模型总结；Core只保存来源和结构。

### E. 推荐代码位置

`dimensions/derivation.py`

### F. 对外接口 / 命令

`dimension.derivation.create/inspect/revise/trace`

### G. 必须编写的测试

学习能力下钻到数学/英语/编程；后发现母亲生病导致短期表现低，修正“能力下降”解释。

### H. 验收标准

高层永远可追溯；反例可见；修正传播。

### I. 明确禁止

禁止把相关性自动写成因果。

### J. 本任务交付物

派生维度服务、学习能力场景。

---

## M3-009 Goal 进度评估与状态历史

**负责人级别**：总工程师审核  
**前置依赖**：M3-005,M2 Task

### A. 当前实现目标

让 AI基于世界证据评估长期目标进度，而不是 Task数量代替目标改善。

### B. 为什么现在必须做

教育/健康等场景最终要看用户目标是否改善。

### C. 具体实现方式

Goal success_criteria 可由AI形成 Claim/EvidenceSet；assess_progress 产生进度 Claim/summary，不直接覆写 Goal。Achieved/Abandoned 需新 revision和依据。

### D. 技术 / 代码指导

进度是一种认知，也可以不确定。

### E. 推荐代码位置

`world/goal_progress.py`

### F. 对外接口 / 命令

`goal.assess_progress`, `goal.transition`

### G. 必须编写的测试

“英语能日常交流”不能仅因完成100节课宣布达成；需要测试/对话证据。

### H. 验收标准

目标状态变化有Evidence；显式和推断Goal分开。

### I. 明确禁止

禁止 Task completed count = Goal success。

### J. 本任务交付物

Goal progress服务与教育fixture。

---

## M3-010 AI 自身世界最小闭环

**负责人级别**：总工程师审核语义  
**前置依赖**：M2 Action/Task,M3-003

### A. 当前实现目标

让AI自身作为 subject 记录帮助、拒绝/接受、误判修正、承诺、开放问题和后续任务，但不把AI关注当用户状态证据。

### B. 为什么现在必须做

双世界互补是陪伴连续性的基础；否则每次像接手档案的新助手。

### C. 具体实现方式

Action/Outcome/Task/Claim/Event都可 subject=ai；关系连接 AI↔user。帮助统计先记录事实，不必每次生成自我反思。

### D. 技术 / 代码指导

AI world 使用同一对象契约和时间轴，不另建 self_memory.json。

### E. 推荐代码位置

`world/self_world.py`

### F. 对外接口 / 命令

`self.inspect`

### G. 必须编写的测试

“昨天答应继续找奖品”形成 Task；用户拒绝5次记录事实；AI误判妈妈身份被修正。

### H. 验收标准

去掉self world时后续行为可实验对比；self数据不会反向冒充用户证据。

### I. 明确禁止

禁止“AI担心用户”作为用户确实抑郁的新独立证据。

### J. 本任务交付物

Self world查询、双世界场景。

---

## M3-011 M3贯穿测试：纠错+总结+派生维度+AI世界

**负责人级别**：总工程师验收  
**前置依赖**：M3-001~010

### A. 当前实现目标

把M3机制放在同一连续虚拟人中跑通。

### B. 为什么现在必须做

单模块正确不代表长期世界不会形成循环污染。

### C. 具体实现方式

30天缩小版fixture：学习变化→派生“学习能力”trial；身份误认→修正；日周月总结；AI多次帮助/拒绝；最后查询高层并下钻。

### D. 技术 / 代码指导

固定seed、Mock和真实模型各跑；记录 world revisions/queries/tasks。

### E. 推荐代码位置

`tests/scenarios/test_month_core_growth.py`

### F. 对外接口 / 命令

跨M1-M3所有接口

### G. 必须编写的测试

高层认知能下钻；错误不会在Summary中继续当事实；AI self不自证。

### H. 验收标准

M3 gate报告中修正覆盖率/误伤率/历史污染率可计算。

### I. 明确禁止

禁止针对fixture写硬编码答案。

### J. 本任务交付物

M3可回放世界数据库、报告。

---

# M4：一个月虚拟人生与强基线

开始真正做科学实验：同一个人连续生活30天，并与强记忆基线公平比较。

## M4-001 连续30天虚拟人生生成器

**负责人级别**：编码代理实现，总工程师审核实验设计  
**前置依赖**：M3 gate

### A. 当前实现目标

生成同一个虚拟人连续30天生活，而不是30个独立一天。

### B. 为什么现在必须做

长期任务、慢趋势、拒绝后的策略变化、身份修正都需要连续世界。

### C. 具体实现方式

Truth state 日间递推；至少包含慢变化、重复问题、跨周跟进、承诺延期/撤销、一次身份纠错、一个动态维度候选、一次App数据复用。

### D. 技术 / 代码指导

seed化仿真；隐藏真值和可见资料分层。

### E. 推荐代码位置

`simulator/month.py`, `simulator/profiles/`

### F. 对外接口 / 命令

仿真内部接口

### G. 必须编写的测试

相同seed可复现；Day1认知会影响Day20可见系统状态但真值不被AI读取。

### H. 验收标准

符合虚拟世界规范5.2。

### I. 明确禁止

禁止每天重置AIOS数据库。

### J. 本任务交付物

月生成器、至少12开发人物模板。

---

## M4-002 评价指标实现：帮助/理解/纠错/任务/成本

**负责人级别**：总工程师审核公式  
**前置依赖**：M4-001

### A. 当前实现目标

把成功从“模型回答看起来不错”变成可重复指标。

### B. 为什么现在必须做

项目是否值得继续必须靠实验，不靠我们自己感觉。

### C. 具体实现方式

实现机会召回、介入精确、不必要打扰、净帮助效用、主张正确、证据支持、不确定性校准、修正覆盖/误伤、Task完成/重复、查询成本。

### D. 技术 / 代码指导

确定性指标程序计算；语义支持用独立评分配置+盲审抽查。权重盲测前冻结。

### E. 推荐代码位置

`evaluator/metrics.py`, `evaluator/semantic_judge.py`

### F. 对外接口 / 命令

评估CLI

### G. 必须编写的测试

构造已知小样本手算比对；重复提醒只计一次收益另算打扰。

### H. 验收标准

结果可按虚拟人物聚类输出，不把百万Observation当百万样本。

### I. 明确禁止

禁止被测模型给自己总分。

### J. 本任务交付物

指标库、验证样本、报告模板。

---

## M4-003 B0/B1/B2/O 强基线

**负责人级别**：总工程师审核公平性  
**前置依赖**：M4-002

### A. 当前实现目标

实现真正有竞争力的对照系统，尤其 B2 强混合检索记忆。

### B. 为什么现在必须做

只有打败合理基线，才说明多维世界复杂度有价值。

### C. 具体实现方式

B0当前上下文；B1长上下文+滚动总结；B2时间/实体/关键词/向量/事实更新/任务调度；O直接给充分当时证据仅作能力上限。

### D. 技术 / 代码指导

所有系统相同模型、输入输出预算、Task/Action执行能力；机制隔离赛道相同Wake。

### E. 推荐代码位置

`evaluator/baselines/`

### F. 对外接口 / 命令

统一 SystemAdapter 协议

### G. 必须编写的测试

同一世界回放到四个系统；确认B2不是故意少工具。

### H. 验收标准

公平比较清单通过。

### I. 明确禁止

禁止把“聊天记录+top3向量”当唯一强基线。

### J. 本任务交付物

四基线、资源统计。

---

## M4-004 30天闭环实验与固定回放实验

**负责人级别**：总工程师验收  
**前置依赖**：M4-001~003

### A. 当前实现目标

分别测试固定历史推理能力和行动真正改变虚拟人生的闭环帮助。

### B. 为什么现在必须做

固定回放适合比较认知；闭环实验才能测帮助结果，两者不能混在一个结论里。

### C. 具体实现方式

固定回放：各系统接收相同资料，Action不改变未来。闭环：相同初始世界/随机条件，Action改变后续状态导致分叉。

### D. 技术 / 代码指导

每个人物至少3次模型运行；保存seed、模型、prompt、架构、预算。

### E. 推荐代码位置

`evaluator/runners.py`, `reports/month/`

### F. 对外接口 / 命令

实验runner

### G. 必须编写的测试

V01~V30覆盖；模型失败/重试纳入日志。

### H. 验收标准

输出配对差值和95%CI；失败案例可回放。

### I. 明确禁止

禁止只展示成功截图。

### J. 本任务交付物

月度实验数据库与报告。

---

# M5：AI 操作经验

单独验证“AI越来越会使用自己的世界”是否真的带来收益。

## M5-001 OperationExperience 候选经验捕获

**负责人级别**：总工程师审核  
**前置依赖**：M4

### A. 当前实现目标

记录AI完成任务时的可观察操作路径、成本、遗漏、结果和适用条件，作为“如何使用世界”的候选经验。

### B. 为什么现在必须做

用户明确要AI不断总结使用搜索/关键词/人物关系工具的经验。

### C. 具体实现方式

从 Session tool trace 生成 Candidate Experience；可以由AI提出自然语言策略，但必须带案例refs和成本，不是隐藏思维链。

### D. 技术 / 代码指导

经验对象不强制每次Wake产生；只有有潜在复用价值时记录。

### E. 推荐代码位置

`experience/service.py`

### F. 对外接口 / 命令

`experience.record/search`

### G. 必须编写的测试

“查感情史：通读全人生很慢”形成候选；普通一次心率查询不强制写经验。

### H. 验收标准

R1-02通过，无占位反思垃圾。

### I. 明确禁止

禁止保存私密CoT作为经验。

### J. 本任务交付物

经验捕获服务、fixture。

---

## M5-002 经验验证、适用范围、反例与过期

**负责人级别**：总工程师审核机制  
**前置依赖**：M5-001

### A. 当前实现目标

只有后续实验验证过的经验才成为优先建议，并能因条件变化过期/被否定。

### B. 为什么现在必须做

一次成功不能变成永久固定思考路线，否则AI越学越僵。

### C. 具体实现方式

Candidate→Validated/Expired/Rejected；保存 positive/negative cases、applicability、model/tool versions。Worker可查询经验但可忽略。

### D. 技术 / 代码指导

Experience 只改变“建议的路径/排序”，不修改工具权限。

### E. 推荐代码位置

`experience/lifecycle.py`

### F. 对外接口 / 命令

经验状态转换

### G. 必须编写的测试

关键词经验对有别名的关系场景失败→添加反例；工具升级后旧经验过期。

### H. 验收标准

V16“经验成功后失效”通过。

### I. 明确禁止

禁止 Validated experience 变硬编码必走流程。

### J. 本任务交付物

经验生命周期、失效测试。

---

## M5-003 操作经验A/B与“恋爱经历查询”实验

**负责人级别**：总工程师验收  
**前置依赖**：M5-002

### A. 当前实现目标

证明经验是否真的减少无关读取/查询次数，同时不降低证据覆盖。

### B. 为什么现在必须做

如果经验没有独立收益，就不应因为概念好听保留复杂度。

### C. 具体实现方式

同一世界checkpoint分叉：A读取经验，B不读；测试通读全人生、关键词、人物关系→事件→关键词三种方法；加入表面相似反例和过期经验。

### D. 技术 / 代码指导

固定模型/预算/世界；比较查询数、token、证据覆盖、正确性。

### E. 推荐代码位置

`evaluator/experiments/experience_ab.py`

### F. 对外接口 / 命令

实验 runner

### G. 必须编写的测试

至少相似、反例、过期、新工具四类任务。

### H. 验收标准

只有在未见任务上收益才算有效；调用少但遗漏多不算进步。

### I. 明确禁止

禁止用开发集同题证明经验有用。

### J. 本任务交付物

A/B报告、是否保留机制的决策。

---

# M6：教育 App 与跨领域认知复用

验证App只是同一个AI进入专业场所，而不是另起人格/记忆。

## M6-001 AppManifest 与 Capability Registry 最小协议

**负责人级别**：总工程师审核  
**前置依赖**：M4

### A. 当前实现目标

定义轻量App如何声明领域、目标、工具、产生的数据和所需认知；定义AI当前可用能力。

### B. 为什么现在必须做

App是AI进入专业领域的场所，不应各自重建人格/Memory。

### C. 具体实现方式

AppManifest fields：app_id/domain/subdomain/goals/tools/observation_types/context_requests；Capability：id/input/output/side_effect/permission/simulator adapter。

### D. 技术 / 代码指导

第一阶段只做Education app；协议要可扩展但不要构建完整应用商店。

### E. 推荐代码位置

`apps/contracts.py`, `capabilities/registry.py`

### F. 对外接口 / 命令

`app.register`, `capability.list/invoke`

### G. 必须编写的测试

Education app不能读取独立memory；Worker进入App时仍是同一subject/self world。

### H. 验收标准

App工具能产生Observation/Task/Outcome回共同世界。

### I. 明确禁止

禁止 App 自带永久 user_profile.db。

### J. 本任务交付物

App/Capability协议、测试。

---

## M6-002 Education Adapter + 数学/英语场景

**负责人级别**：编码代理实现，总工程师审核教学边界  
**前置依赖**：M6-001,M3 Goal/Claim

### A. 当前实现目标

建立第一个专业场所，产生题目、作答、耗时、讲解、掌握度和复测任务。

### B. 为什么现在必须做

教育能最好验证“同一个AI理解用户全世界后，教学是否更合适”。

### C. 具体实现方式

题目/知识点可作为App对象或Observation；回答耗时/错误写Observation；AI教学产生Action；掌握度作为Claim+Evidence；学习Goal/Task进入共同世界。

### D. 技术 / 代码指导

先虚拟题库和规则评分，不追求完整教育产品UI。

### E. 推荐代码位置

`apps/education/`

### F. 对外接口 / 命令

Education capabilities

### G. 必须编写的测试

用户只会加减法时禁止直接用微积分；数学水平来自历史世界。

### H. 验收标准

教学数据可被后续编程App查询到相关高层认知。

### I. 明确禁止

禁止“答对一次=已掌握”。

### J. 本任务交付物

Education adapter、题库fixture、测试。

---

## M6-003 跨维度状态适配教学

**负责人级别**：总工程师验收核心价值  
**前置依赖**：M6-002

### A. 当前实现目标

AI教师结合睡眠、工作负荷、身体/情绪、学习历史动态决定难度、时长、教学方法甚至今天放假。

### B. 为什么现在必须做

这是普通通用模型与AIOS个性化教育最直观差异。

### C. 具体实现方式

Workspace进入Education场景时只拉相关认知索引；Worker自主决定是否再查睡眠/工作/历史讲解效果。教学decision记录为什么缩短/休息/改变方法。

### D. 技术 / 代码指导

不得固定“睡眠<5h就放假”，语义仍由大模型结合世界判断；机械数据只是证据。

### E. 推荐代码位置

`apps/education/context.py`, Worker prompt/tool usage

### F. 对外接口 / 命令

同一工具集

### G. 必须编写的测试

疲劳一天→短复习；状态良好→新知识；历史图形法有效→优先视觉讲解，但有反例时可改。

### H. 验收标准

适配不会无依据；“喜欢讲解”和“真正学会”分开。

### I. 明确禁止

禁止用静态profile替代世界查询。

### J. 本任务交付物

跨维度教学场景与评分。

---

## M6-004 跨App认知迁移实验

**负责人级别**：总工程师验收  
**前置依赖**：M6-003

### A. 当前实现目标

验证数学场景产生的“视觉化理解更好”等认知是否能适当帮助编程教学，同时防机械泛化。

### B. 为什么现在必须做

这是“App越多，同一个AI对人越完整”的核心命题。

### C. 具体实现方式

Education数学产生 Candidate Claim/Dimension；编程场景查询时可使用，但先验证适用范围。设置一个正迁移和一个反例。

### D. 技术 / 代码指导

用checkpoint A/B：共享认知 vs 不共享，底层资料相同。

### E. 推荐代码位置

`evaluator/experiments/cross_app.py`

### F. 对外接口 / 命令

App场景适配器

### G. 必须编写的测试

正例改善理解；反例中AI能放弃不适用偏好。

### H. 验收标准

跨App共享带来可测收益且不过度泛化。

### I. 明确禁止

禁止将一个App单次偏好升级为全领域永久事实。

### J. 本任务交付物

跨App实验报告。

---

# M7：一年运行、规模与模型切换

验证长期漂移、恢复、规模、成本和机制价值。

## M7-001 一年虚拟人生与长期漂移

**负责人级别**：编码代理实现，总工程师审核实验覆盖  
**前置依赖**：M6

### A. 当前实现目标

把同一虚拟人扩展到一年，包含季节、目标、关系、学习、任务、历史经验失效和迟到证据。

### B. 为什么现在必须做

只有长期运行才能暴露Summary、Task、索引、世界Revision增长和旧认知污染问题。

### C. 具体实现方式

按规范至少包含数月前Task、身份/目标/关系变化、学习增长/倒退、别名冲突、模型中断/切换、高密度/低变化区间。

### D. 技术 / 代码指导

70万+ observation 作为规模档位，不把数量本身当成功指标。

### E. 推荐代码位置

`simulator/year.py`

### F. 对外接口 / 命令

年度runner

### G. 必须编写的测试

一年从空状态逐步形成世界，不允许直接装全年总结。

### H. 验收标准

年度运行完整、可恢复、无未来泄露。

### I. 明确禁止

禁止把十年合成检索测试说成AI连续生活十年。

### J. 本任务交付物

年度生成器、人物集。

---

## M7-002 规模、索引、世界版本和存储增长基准

**负责人级别**：编码代理实现  
**前置依赖**：M7-001

### A. 当前实现目标

测70万～360万Observation下写入、查询、下钻、索引重建、Summary和Task恢复。

### B. 为什么现在必须做

长期世界会变大；必须知道何时SQLite/当前索引真的不够，而不是凭感觉提前换技术。

### C. 具体实现方式

benchmark记录P50/P95写入/搜索/trace时间、DB大小、索引大小、世界revision增长、月summary成本。分冷热查询。

### D. 技术 / 代码指导

pytest-benchmark或自定义脚本均可，固定硬件/配置。

### E. 推荐代码位置

`benchmarks/`

### F. 对外接口 / 命令

CLI benchmark

### G. 必须编写的测试

100万对象后“近7天某实体相关事件”仍可在设定目标内返回；完整结果含coverage。

### H. 验收标准

报告真实性能，不人为设不合理门；如果超标提出优化证据。

### I. 明确禁止

禁止为了快删除历史。

### J. 本任务交付物

性能报告、火焰图/SQL计划。

---

## M7-003 模型中断、恢复与模型供应商切换

**负责人级别**：总工程师审核  
**前置依赖**：M2 Session,M7-001

### A. 当前实现目标

证明世界属于AIOS而不是某个模型上下文；模型A中断后模型B可以从Workspace/Checkpoint继续。

### B. 为什么现在必须做

长期OS不能绑定单一厂商，也不能因上下文丢失失忆。

### C. 具体实现方式

ModelAdapter统一tool schema；Session checkpoint只含可观察工作；切换模型后加载同一snapshot/changes/Task。Action execution id防重复。

### D. 技术 / 代码指导

先Mock A/B，再至少两个真实模型条件允许时复核。

### E. 推荐代码位置

`ai_worker/adapters/`, `tests/scenarios/test_model_switch.py`

### F. 对外接口 / 命令

统一ModelAdapter

### G. 必须编写的测试

Action提交后模型切换；新模型不重复执行且能继续等待Outcome。

### H. 验收标准

跨模型认知/Task/身份连续。

### I. 明确禁止

禁止把关键状态藏在某厂商thread id。

### J. 本任务交付物

模型切换测试、报告。

---

## M7-004 年度强基线、公平赛道与成本效果曲线

**负责人级别**：总工程师验收  
**前置依赖**：M7-001~003,M4 baselines

### A. 当前实现目标

用机制隔离赛道和自主调度赛道比较 AIOS 与 B2，并报告资源成本。

### B. 为什么现在必须做

AIOS可能因调用更多模型而变好；必须区分架构收益和纯预算收益。

### C. 具体实现方式

机制隔离：同Wake/模型/预算/工具；自主调度：各自安排观察，但总资源上限一致。计算配对差值/95%CI和成本-效果曲线。

### D. 技术 / 代码指导

按虚拟人物聚类统计。第二模型复核主要结论。

### E. 推荐代码位置

`evaluator/year_benchmark.py`

### F. 对外接口 / 命令

实验runner

### G. 必须编写的测试

至少月度+年度均观察收益才可宣称长期机制价值。

### H. 验收标准

报告“支持/部分支持/不支持/无效/证据不足”之一。

### I. 明确禁止

禁止看盲测后改权重。

### J. 本任务交付物

年度正式报告。

---

# M8：消融、机制裁决与下一阶段Gate

让实验决定复杂机制是否值得保留，并决定是否进入真实设备原型。

## M8-001 机制消融实验

**负责人级别**：总工程师验收  
**前置依赖**：M7

### A. 当前实现目标

逐项去掉多尺度总结、实体导航、依赖纠错、AI经验、动态维度、自主观察、跨App共享、AI自身世界，测独立收益。

### B. 为什么现在必须做

架构复杂不代表正确；没有独立收益的机制应简化。

### C. 具体实现方式

同checkpoint/同模型/同世界分叉，只有目标机制开关不同；重复运行。

### D. 技术 / 代码指导

feature flags必须只切机制，不偷改其它资源。

### E. 推荐代码位置

`evaluator/ablations.py`

### F. 对外接口 / 命令

实验runner

### G. 必须编写的测试

每个消融至少对应一个原本声称的优势场景。

### H. 验收标准

输出收益/成本/置信区间/失败类型。

### I. 明确禁止

禁止只在最有利案例做消融。

### J. 本任务交付物

消融矩阵与报告。

---

## M8-002 机制裁决与架构简化

**负责人级别**：总工程师决策  
**前置依赖**：M8-001

### A. 当前实现目标

根据实验决定哪些机制保留、重构、后移或删除，并形成下一版宪法候选。

### B. 为什么现在必须做

我们要让实验决定架构，而不是为了维护最初设计面子。

### C. 具体实现方式

每机制表：目标、实际收益、成本、失败模式、是否存在更简单替代。形成 KEEP/REVISE/DEFER/REMOVE。

### D. 技术 / 代码指导

不编码；这是架构决策文件。

### E. 推荐代码位置

`reports/mechanism_decision.md`

### F. 对外接口 / 命令

无

### G. 必须编写的测试

所有复杂机制均有证据引用。

### H. 验收标准

没有收益的机制不得仅因为“看起来先进”保留。

### I. 明确禁止

禁止把实验失败归咎于用户/模型而不做归因。

### J. 本任务交付物

机制裁决表、R3候选修改案。

---

## M8-003 是否进入真实设备/真实用户原型的 Gate

**负责人级别**：项目负责人+总工程师  
**前置依赖**：M8-002

### A. 当前实现目标

明确下一阶段是否值得投入 Linux/硬件/真实传感器/App生态。

### B. 为什么现在必须做

核心认知机制没有验证前做完整OS会浪费巨大资源。

### C. 具体实现方式

Gate至少检查：相对B2收益、主动帮助精确率、纠错、任务完成、成本、长期稳定、跨App收益、主要风险。

### D. 技术 / 代码指导

会议/文档决策，无需新技术。

### E. 推荐代码位置

`reports/next_stage_gate.md`

### F. 对外接口 / 命令

无

### G. 必须编写的测试

若证据不足则明确“继续实验”而不是强行通过。

### H. 验收标准

只有Gate通过才进入真实设备路线。

### I. 明确禁止

禁止因为已经投入很多时间而用沉没成本推进。

### J. 本任务交付物

下一阶段决定。

---

# 12. 关键核心代码的“总工程师所有权”清单

为了防止低能力编码模型为了快速完成任务而偷偷改变项目核心，以下文件/模块执行特殊规则：

| 模块 | 规则 |
|---|---|
| `contracts/enums.py` | 总工程师定义；新增枚举必须评审 |
| `contracts/time.py` | 总工程师代码；不得自行合并三类时间 |
| `contracts/base.py` | 总工程师代码；长期对象公共字段冻结 |
| `contracts/models.py` 中 Claim/Evidence/Event/DimensionDerivation/Goal | 总工程师代码或逐段审核 |
| `storage/sqlite_store.py` | 总工程师代码或逐段审核；任何绕过唯一写入层的改动拒绝 |
| `services/state_machines.py` | 总工程师代码 |
| `dependency/invalidation.py` | 总工程师设计+首版代码 |
| `tasks/state_machine.py` | 总工程师设计+首版代码 |
| `wake/engine.py` | 总工程师审核，确保无语义判断 |
| `workspace/tool_registry.py` | 总工程师审核，确保AI自主操作而非固定流程 |
| `summaries/` 核心协议 | 总工程师审核，确保总结不覆盖证据 |
| `dimensions/derivation.py` | 总工程师审核，确保高层可下钻/可反证 |

这不意味着总工程师必须写所有 UI、CRUD、测试夹具和仿真数据。外围代码可以交给编码代理并行完成，但关键世界语义不能交给代理自行定义。

---

# 13. 当前已经亲自提供的参考代码

本轮同时提供 `aios_core_r2_reference/`，当前包含：

```text
src/aios_core/contracts/
  enums.py
  ids.py
  time.py
  refs.py
  base.py
  models.py
  operations.py

src/aios_core/storage/
  sqlite_store.py

src/aios_core/services/
  state_machines.py

tests/
  test_contracts.py
  test_store.py
  test_state_machines.py
```

已经实现并通过自动测试的关键点：

1. 稳定对象 ID。
2. `occurred / learned_at / recorded_at` 三类时间。
3. `ClaimType` 和 `KnowledgeState` 分离。
4. EvidenceSet 一等对象。
5. Event/DimensionDerivation/Goal/Task/Wake/Session/Action/Outcome 基础契约。
6. SQLite 追加式对象 Revision。
7. 全局 World Revision。
8. expected_world_revision 乐观并发检查。
9. idempotency key 幂等重放。
10. 版本化引用基本校验。
11. 按 world revision / knowledge cutoff 历史读取。
12. Task/Event 状态机校验。
13. 15个自动测试全部通过。

**注意**：这只是关键地基的参考实现，不代表 M0 已全部完成。尤其证据依赖的复杂循环检测、迁移框架、完整 API、Dependency 反向索引等还要按本任务书继续实现。

---

# 14. 第一批真正开工顺序

不要让多个编码代理同时改核心契约。第一批按以下顺序：

```text
第1批（总工程师地基）
M0-001 → M0-006
        ↓
M0-008 / M0-009 / M0-011 / M0-012 / M0-013 / M0-014 / M0-015
        ↓
M0-016 → M0-020 → M0-021
        ↓
M0-022 Gate
```

M0 Gate 通过后才允许并行：

```text
路线A：M1-001 接入
路线B：M1-002~004 实体/关系/维度
路线C：M1-005~009 Claim/Evidence/Event/Goal/Dependency
路线D：M1-010~014 查询与索引
路线E：M1-015 控制台
```

所有路线最终必须汇合到 M1-016 贯穿案例。

---

# 15. GitHub Issue 模板（以后每个任务照这个发）

```markdown
# [M0-008] Claim（主张）语义模型

## 目标
一句话写清用户可见结果/系统能力。

## 上位依据
- AIOS宪法2.0
- R1
- R2：R2-02
- 详细任务书：M0-008

## 允许修改文件
- src/aios_core/contracts/models.py
- tests/unit/contracts/test_claim.py

## 禁止修改
- 三类时间语义
- Object ID规则
- EvidenceSet语义

## 输入/输出契约
贴本任务书字段。

## 实现步骤
1. ...
2. ...

## 必须测试
- ...

## 验收
- [ ] 单测通过
- [ ] Schema snapshot无未批准变化
- [ ] 边界场景通过
- [ ] 已知限制已记录

## 提交时必须附
- commit hash
- pytest输出
- 变更文件列表
- 未解决问题
```

---

# 16. 给低能力编码模型的统一工作提示

每次派单应在任务前附加：

> 你不是本项目架构师，你是实现工程师。不得重新设计 AIOS 世界模型。严格按照 Issue 的字段、接口、禁止事项和验收标准实现。如果你认为规格存在冲突，停止修改核心契约，列出冲突和建议，不得自行选择一个新架构。不得为了减少代码把 Claim、EvidenceSet、Event、Dimension、Goal、Task 等对象合并。不得让 AI Worker 直接访问数据库。必须先写失败测试，再实现，最后给出完整 pytest 输出和改动文件列表。

---

# 17. 项目经理每周看板必须回答的问题

不看“写了多少行代码”，只看：

1. 当前处于哪个 Gate？
2. 哪些冻结契约已经通过自动测试？
3. 哪个端到端场景现在可以从空库重放？
4. 有没有断裂引用、重复Action、未来信息泄露？
5. 最近一次AI错误能否追溯到：数据/检索/推理/任务/行动中的哪一层？
6. 哪些复杂机制已经有独立收益证据？
7. 哪些只是做出来了但尚未证明有价值？
8. 当前最大阻塞是机制问题还是工程问题？

---

# 18. 当前开发决策

**从此版本起，旧《AIOS_Core_详细开发任务拆分_R2.md》不再直接用于派单。**

新的开发基线顺序是：

```text
AIOS宪法2.0
 + R1
 + R2
 + 三份开发规格
 + 本《R2总工程师重写版详细开发任务》
        ↓
GitHub Issues
        ↓
代码
        ↓
自动测试
        ↓
虚拟世界实验
        ↓
实验结果决定是否修宪
```

核心目标保持不变：

> **验证 AI 能否在一个持续增长、可追溯、可纠错的多维世界中，自主选择观察尺度和查询路径，形成带不确定性的认知，管理未来任务，学习更有效地使用世界，并最终在适当时间更有效地帮助同一个用户。**
