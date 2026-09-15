# AIOS 全套工程文档与 V3 宪法横向对齐及落地断层审查

- **审查类型**：Gap Audit / Requirements Traceability Audit
- **审查角色**：AIOS 核心系统总架构师与工程审计长
- **审查日期**：2026-09-16
- **审查状态**：`REALIGNMENT REQUIRED / M0 冻结门不得放行`
- **最高基准**：`AIOS核心系统宪法v3.0.md`
- **代码基线**：`cd8bb292a433a6d2961eac2c324c6e293647260b`（`aios-2.0`）
- **审查原则**：V3 是唯一规范来源；但若 V3 内部互相冲突，则先形成 v3.0.1 裁决，不以“机械照抄”伪装成 100% 对齐。

---

# 0. 最终判词

## 0.1 对核心问题的直接回答

> **不能。** 如果工程团队完全按照现有《架构规划》《总工任务书》《工作台规格》和《测试规范》实施，能够得到一个较扎实的 **R2 时代 AIOS Core**：有追加版本、三类时间、Claim/EvidenceSet、实体、任务、Wake、工作台、工具循环、纠错和多尺度总结；但**不能完整实现 V3 所定义的运行时、人格、检索、条件调度、长会话、边缘摄入和穿戴交互能力**。

问题不是缺几个字段，而是 V3 于 2026-09-15 新增/升级的机制，没有沿着以下链条完整下传：

```text
V3 条款
  → 唯一模块责任
  → 一等数据/协议契约
  → 可派发 Issue
  → 确定性测试或场景测试
  → 里程碑退出门
```

目前该链在多处停在第一层或第二层。结果将是：代码“按任务书完成”、M0/M1/M2 自己的旧验收也可能通过，但仍然严重违背 V3。

本审计共登记 **41 项重大断层：30 项 P0、11 项 P1**；提出 **28 个不与现有编号冲突的新 Issue**，并对 34 组现有 Issue 给出 KEEP/UPGRADE/REWRITE/SPLIT 裁决。

## 0.2 项目会在哪个里程碑卡死？

必须区分**审计阻断点**和**运行崩塌点**：

| 判定视角 | 首个里程碑 | 判词 |
|---|---:|---|
| 宪法与契约审计 | **M0** | 必须立即停止冻结。V3 的 22 个核心对象中，任务书只冻结了 19 个；`Prediction`、`LifeChapter`、`CommunicationExperience` 缺失，`PredictionCheckTask` 与通用 `TriggerExpression` 也未进入 Task 契约。带着这份 schema snapshot 进入 M1，就是把 V3 缺口固化为兼容性债务。 |
| 数据与查询实现 | **M1** | 开始实质分叉。M1-001 会按通用 Observation 批量写传感器；M1-012 会实现 FTS/实体筛选，却没有 V3 原生 `world.co_search`、中文分词契约和拓扑交集排名；M1-010 没有完整 LOD/5D 查询契约。 |
| 用户可观察的主动闭环 | **M2** | **第一个必然的运行断崖。** M2 会建出 Worker、Task、Wake 和工作包，但没有通用条件 AST/就绪索引、长会话增量萃取、前台活跃窗口、召回水位和端到端 1 秒指标。系统要么反复唤醒模型检查未就绪任务，要么丢失 50 轮对话中的旧话题，要么继续靠多次临时搜索。 |
| 纠错与长期人格 | **M3** | 已无法靠“补一个服务”修复。缺失的一等对象、事件订阅和会话水位已侵入存储、API、队列与测试；M3 现有内容又没有 LifeChapter、Prediction 闭环、CommunicationExperience 和有界传播内核。 |

**最终裁决**：项目应在 **M0 Gate 立即冻结并做 V3 对齐补丁**；若无视该门继续开发，则在 **M2 主动闭环**处出现不可掩盖的机制性卡死。M3 不是补救点，而是债务放大器。

## 0.3 不是推倒重来

现有 R2 设计中，下列部分应保留：

- 三类时间、稳定 ID、追加 revision、World Revision、Knowledge Cutoff；
- Claim / EvidenceSet / Event / Goal 分离；
- Observation 默认不 Wake；
- Wake 去重、冷却、优先级、抢占；
- Action / Outcome / receipt / 幂等；
- `workspace.open` 的聚合初始工作包；
- 自主工具调用、证据下钻、Session checkpoint；
- 强基线、公平赛道、隐藏真值隔离和既有 V01~V20；
- 浏览器开发者控制台。

需要做的是**升级权威基线、补齐契约并重写若干关键 Issue**，而不是把这些地基废掉。

---

# 1. 审查基线与证据方法

## 1.1 五份主审文件快照

以下校验值用于保证本报告结论可复现：

| 简称 | 文件 | SHA-256 |
|---|---|---|
| V3 | `AIOS核心系统宪法v3.0.md` | `4df049fc34482df46fbb75ff8701026403c1ea512f97719269f3a525f21bcef1` |
| ARCH | `AIOS Core 系统架构图与开发规划.md` | `9fb1b1cf9c431512f88c514a662b15d40d20c27ef0505f242241edef4050cf71` |
| TASK | `AIOS_Core_详细开发任务拆分_R2_总工程师版.md` | `314f94b32a8b119e09e369c971d0e7f887ea295a745c8058f59526c7136bf5cb` |
| WB | `AIOS认知工作台功能规格.md` | `c568d2ab41ce1a81bc1324dfaecb5973fd49c55eb9be29cdc4b0b2f6709b4a51` |
| TEST | `AIOS虚拟世界测试规范.md` | `a5f90a1b7d966f5a1ca8e7351d9d53e4456354d68163eede1765d192a54506a6` |

本报告使用 `V3:L1073–1091` 表示 V3 文件对应行号，其他文件同理。本次 Gap Audit 同时继承前一份独立审查已确认的规范冲突与实测证据：`reviews/architecture/AIOS_v3.0_CHIEF_REVIEW_PATCH_REQUIRED_2026-09-15.md`；它不把尚未修正的 V3 绝对化措辞强行变成不安全实现。

## 1.2 判定等级

| 代码 | 含义 |
|---|---|
| `A` | 已明确进入架构、Issue 和验收，基本对齐 |
| `P` | 有可复用雏形，但关键语义/接口/测试不完整 |
| `G` | Gap：V3 有要求，下游无对应可派发实现 |
| `C` | Conflict：下游设计与 V3 字面要求相反 |
| `N` | Normative conflict：V3 自身不存在唯一可执行答案，必须先修宪 |

## 1.3 一个必须先纠正的审查误区

以下三组概念不能混为一谈：

1. **V3 禁止的多轮低效提示**，是“系统发一段 → 模型说知道了 → 系统再发下一段”；它不等于 AI 在拿到完整 Manifest 后自主调用搜索、下钻和写入工具。V3 自己在第八十六、九十一条允许自主工具路径。
2. **PC 浏览器控制台**是开发者调试器，不是最终用户手环 UI。V3 自己要求开发阶段提供可视化认知调试控制台（V3:L1187–1188）。保留 PC 控制台不违宪；缺的是另一个面向穿戴端的交互协议。
3. **共现检索**只能定位关联候选区，不能单凭交集得出因果。对齐 V3 的接口不意味着必须复制其“共现即因果”的错误措辞。

---

# 2. 首要治理断层：四份工程文件仍以 V2/R2 为权威

这是其他所有 Gap 的根因。

| 证据 | 当前事实 | 后果 |
|---|---|---|
| V3:L3–7 | V3 声明自己是唯一正式开发基线 | 所有下游文件应显式声明 V3 版本/校验值 |
| ARCH:L3–6 | 架构规划 V0.1 明写“依据：宪法 v2.0” | C 模块、阶段和能力范围停留在 V2 |
| TASK:L3–7 | 总工任务书上位依据只列 v2、R1、R2 和三份旧规格 | R3/V3 新对象不会被派单 |
| TASK:L4240–4257 | 文件结尾再次把开发基线写成 v2 + R1 + R2 | 与 V3 唯一基线直接冲突 |
| WB:L3–5 | 工作台只声明依赖“第一份规格” | 继承 ARCH 的 V2 语义 |
| TEST:L1–5 | 测试规范没有声明 V3/R3 兼容版本 | 新条款无场景追踪义务 |

同时还有两个结构性漂移：

### 模块编号漂移

- ARCH:L92–97：`C05=事件、认知与总结`，`C06=世界查询`，`C09=触发调度`；
- V3:L1458–1463：`C05=多尺度总结与人生章节`，`C06=认知与证据`，`C09=Observation 接入+触发`。

同一个 `C06` 在两份正式文件中分别表示“查询”与“认知”，会导致 Issue 所有权、包依赖和评审人错位。

### 里程碑编号漂移

- ARCH:L278–286 只定义 M0~M6，并把“一年验证”叫 M5；
- TASK:L163–173 与 V3:L1484–1504 定义 M0~M8，把一年运行叫 M7。

如果项目经理说“当前进入 M5”，两份规划甚至无法确定是在做一年测试还是 AI 操作经验。

**治理裁决**：在所有代码派单前，必须先发布 V3 对齐版 ARCH/WB/TEST/TASK，并冻结唯一模块映射与里程碑映射。否则不存在可审计的“按计划实施”。

现有 R2 参考代码也证明这不是纸面风险：`aios_core_r2_reference/src/aios_core/contracts/enums.py:L6–25` 的 ObjectType 正好只有旧 19 类，`:L94–105` 的 TaskType 只有旧 10 类；`contracts/models.py:L197–217` 的 Task 只有 `next_wake_at/deadline/recurrence/dependency_refs`，没有 TriggerExpression。也就是说，继续按旧任务书编码正在把断层写进 schema。

---

# 3. 七大核心对齐项逐项审查

# 3.1 唤醒与看板：Single-Shot Cockpit vs 十三步循环

## V3 要求

- V3:L1075–1077：一次性向模型交付结构化 Cockpit Manifest，禁止分段喂提示词；
- V3:L1079–1091：要求“照镜子 → 校准羁绊 → 定姿态 → 看用户世界/触发”的四步，并要求看板包含 AI 自身、羁绊、Wake、现场、能力和带条件任务；
- V3:L1150–1175：看板只负责呈现，AI 自主选择工作项目，可跳过、交叉、回退和跨会话继续。

## 现有下游实际情况

| 文件/Issue | 已有能力 | 对齐判断 |
|---|---|---:|
| ARCH:L97 | C10 仍写“十三步循环” | `C`：命名和责任仍是旧制 |
| WB:L46–66 | 一次返回时间、Wake、紧急项、世界、任务、承诺、AI 状态、数据质量和工具 | `P`：这已经是 Manifest 的良好雏形 |
| WB:L305–328 | 仍按十三步记录，顺序是 Wake/紧急/用户世界/AI 自身/调查…… | `C/P`：若作为审计生命周期可保留；若作为心智顺序则违背 V3 |
| TASK M2-009，L2351–2394 | `workspace.open` 聚合单个 `WorkspaceSnapshot`，带 refs/revision/age/coverage | `P`：不是旧式逐段喂提示 |
| TASK M2-010，L2398–2441 | 提供时间、搜索、下钻等结构化工具 | `A`：V3 允许 Manifest 后自主操作 |
| TASK M2-012，L2492–2535 | “首包 workspace.open；模型可多轮 tool calls”；明确不能退化成固定十三步脚本 | `A/P`：工具循环合法，但缺 V3 启动因子、上下文预算和验收 |

WB:L305 还写着“按宪法第三十四条记录十三步”；但 V3 的第三十四条现在是“Observation 默认只写入世界，不直接唤醒 AI”（V3:L485–495）。这不是措辞差异，而是条款编号已失效的直接证据。

## 严格裁决

**不能把 M2-012 的多轮 tool calls 判成违宪。** V3 禁的是低效的分段系统提示，不是有目的的查询工具调用。当前真正的 Gap 是：

1. 没有命名、版本化的 `CockpitManifest` 契约，只有较泛的 `WorkspaceSnapshot`；
2. 没有每类 Wake 的字段选择策略、Token/字节上限、构建 deadline 和降级标记；
3. 没有 `extraction_watermark`，无法说明近期对话是否已被后台萃取；
4. 没有“只暴露当前 READY/需裁决任务”的硬契约；WB 的任务摘要仍可能包含阻塞/等待项（WB:L57）；
5. 没有 `DIM_AI_IDENTITY / DIM_AI_RAPPORT / DIM_AI_PROMISES` 的初始化与快照协议；
6. 十三步仍被写成“认知循环”，而不是**一次 Session 的事后审计阶段**；
7. 没有测试证明系统只调用一次 `workspace.open` 即获得完整首包，也没有测试禁止“好的，我知道了”式占位轮次。

## V3 自身阻断冲突

V3 目前同时要求：

- Wake Reason 是第一任务指针（V3:L1021）；
- 方便度必须第一优先研判（V3:L1043–1046）；
- AI 第一纳秒先看自己，第四步才看 Wake（V3:L1079–1084）。

三者无法同时成为字面意义的“第一”。因此不能让 Worker 用隐藏思维链证明顺序。应在 v3.0.1 中改为**可观察决策不变量**：安全/当前输入优先，身份与权限常驻，关系只影响表达，不改变事实阈值；十三步只作审计分类。

**结论**：`部分对齐，接口可复用；心智顺序、任务暴露、预算与测试必须重写。`

---

# 3.2 任务调度：条件驱动 vs 无脑遍历

## V3 要求

V3:L1153–1160 要求每项待办显式声明 `time_reached`、`context_matched`、`event_occurred`、`dependency_ready` 等 Trigger Criteria；调度器只向模型暴露已满足条件或必须裁决的任务。

## 现有下游实际情况

- ARCH:L156 的 Task 概念提到“触发/截止规则”，图中也写“条件命中”，属于架构意图；
- WB:L211–213 的共同 Task 字段只有 `next_wake_at/deadline/recurrence/dependencies` 等，没有通用激活表达式；
- WB:L227 规定无截止待办进入“定期盘点或相关情境唤醒”，但没有可执行的“相关情境”索引；
- WB:L269–281 只为**观察任务**定义了 `condition`，并正确区分机械与语义判断；
- TASK M0-014，L805–827 冻结的 Task 字段仍没有通用条件 AST；
- TASK M2-005，L2176–2198 仅按 `next_wake/deadline/recurrence` 调度；“等待证据后新资料到达变 READY”没有事件订阅契约；
- TASK M2-006，L2223–2245 要求 TODO 设置 `next review`，本质上仍可能周期性唤醒模型盘点；
- TASK M2-007，L2270–2292 有“有限 DSL/JSON”，但只覆盖 Watch/Verification，不覆盖全部 Task 类型。

## 失效链

```text
TODO 没有可编译条件
  → 只能设置 next_review_at
  → 到期产生 Wake
  → workspace 把 TODO 交给模型
  → 模型再次判断“条件还不成熟”
  → 再设 next_review_at
  → N 个待办 × 周期盘点 × 模型调用
```

这正是 V3 要消灭的 Token 空转。现有实现不一定会在**每一次任意 Wake**中扫描全部任务，但它没有任何契约能保证不会发生；也无法高效回答“10 万 Task 中现在 ready 的 10 个是谁”。

## 必须补齐

- 一等、版本化 `TriggerExpression` AST；
- `TRUE/FALSE/UNKNOWN` 三值结果与 `unknown_policy`；
- 时间、事件类型、实体、维度、依赖等订阅键；
- `next_evaluation_at`、迟到事件、时区/DST、debounce、hysteresis、expiry；
- 机械预筛与有预算语义复核分离；
- `ReadyTaskQueue` 和事件驱动增量求值，禁止每次 Wake 全表扫描；
- Manifest 构建时只读取 READY/需要裁决的任务；
- 任务检查成本、模型调用和假唤醒的 telemetry。

**结论**：`严重 Gap；M2-005/006 现状无法兑现第八十六条。`

---

# 3.3 上下文管理：50 轮长会话与 1 秒响应

## V3 要求

V3:L1093–1146 定义：

1. 前台 Active Rolling Window（约 5~8 轮/1500 tokens）；
2. 后台 Incremental Streamer，在会话中持续把完成片段变成 Claim/Event；
3. 用户重提旧事时，通过实体/事件/任务/原话超链接按需召回；
4. 日常首字约 1 秒，长上下文只用于深度模式。

## 现有文档中缺什么

五份主审文件中，TASK 没有任何 Issue 以 `Streaming Extract`、增量萃取、对话水位、turn offset 或 active window 为实现目标。

容易被误认为“已有”的两个 Issue 实际不是同一机制：

- M2-011（TASK:L2445–2488）管理的是**AI 工作 Session 的世界快照和中断恢复**，不是用户自然对话的 turn buffer；
- M2-012（TASK:L2492–2535）管理的是一次 Worker 的模型/工具循环，不是 50 轮前台会话与后台萃取并发。

冻结对象清单也没有以下最小协议：

```text
conversation_id / turn_id / monotonic_seq
speaker/source envelope
turn finalization status
extractable span start/end
extractor + prompt/schema version
input_hash / idempotency_key
extraction_watermark
PENDING/RUNNING/COMMITTED/FAILED/QUARANTINED
commit_world_revision
```

因此会出现：

- 后台抽取落后，前台已把旧 turn 移出窗口，出现暂时失忆；
- 同一片段重试两次，产生重复 Claim/Event；
- 前台与后台同时修同一实体/Claim，发生 revision 冲突风暴；
- 话题边界切错，代词和未完成承诺被截断；
- 用户突然提旧事时，系统不知道哪一段已经沉淀、哪一段仍须回读原文；
- 无法区分 TTFT、首音频与最终有用答案，更无法证明 1 秒。

TEST 虽引用 LongMemEval/LoCoMo（TEST:L450–455），却没有 50 轮实时对话、异步抽取、crash/retry/watermark 的场景。

## 裁决

没有这些 Issue，系统可以完成短 Session demo，但不能称“长会话三级流式流水线”。固定 1500 tokens 和 5~8 轮也不应作为不可变真理，应升级为**受 Token 预算约束的语义工作集**：最近 turn + 未闭合话题 + 未解析指代 + 未提交工具结果 + 萃取水位之后的所有 turn。

**结论**：`完全缺失的 P0 运行机制；M2 会直接暴露。`

---

# 3.4 世界检索：原生多关键词共现与 5D 时间镜头

## V3 要求

- V3:L1213–1225：原生 `world.co_search(keywords=[...])`，一次计算多关键词在实体/Event/Claim 拓扑中的共现密集区；
- V3:L1190–1204：多尺度时间缩放、平移、框选和下钻；
- V3:L1234–1245：给出新的原子 API 名称。

## 现有设计并非“只有单关键词”，但仍不够

现有能力包括：

- ARCH:L93、L109–115：全文、语义、时间、实体查询；
- WB:L138–152：`world.search`、实体解析、follow links 和分阶段扩大召回；
- M1-010（TASK:L1642–1685）：时间范围、粒度、维度、knowledge cutoff；
- M1-011（TASK:L1689–1732）：多维对齐和机械共变；
- M1-012（TASK:L1736–1779）：FTS5、实体别名、文本/实体/时间/主体/type filters；
- M1-013（TASK:L1783–1826）：证据和事件下钻。

所以“现有设计只能搜一个词”并不准确。真正断层是：

1. M1-012 的测试写的是“妈妈+生日+礼物+近 3 年**逐步过滤**”（TASK:L1765–1768），不是一个版本化、原子的 joint query；
2. TASK/WB 没有 `world.co_search`、query plan、term coverage、交集/并集/最小命中数、共同时间窗和拓扑距离定义；
3. 没有中文分词、词典版本、短词、别名、代词、否定和角色语义契约；
4. 没有 FTS、结构化 postings、实体、向量和图候选的统一融合排名；
5. 没有候选扩展的深度/宽度/时间/节点预算；
6. 没有把“相关密集区”与“因果已成立”分开；
7. 规模门在 M7-002 才测，太晚。

本仓库已附的 360 万对象 SQLite 探针进一步证明：默认 FTS5 `unicode61` 对连续中文 `给妈妈买生日礼物` 查询 `妈妈 AND 生日 AND 礼物` 命中 0，显式预分词后才命中 1。证据见：

- `reviews/architecture/evidence/aios_v3_sqlite_probe.py`
- `reviews/architecture/evidence/aios_v3_sqlite_probe_3_6m_result.json`

## 5D 时间镜头判断

M1-010 已覆盖时间范围、粒度、主体、维度和 knowledge cutoff，是很好的基础；但仍缺：

- 明确的 `valid_time / knowledge_cutoff / world_revision_cutoff / LOD / subject-dimension projection`；
- `target_points` 或目标分辨率驱动的自动 raw/hour/day/week 选择；
- rollup 物化和 index watermark；
- 不超过传感器真实时间精度的 uncertainty；
- `time.select_range` 与 V3 API 迁移映射；
- 百万级冷/热查询 P95/P99 的 M1 Gate。

## 因果边界

`[妈妈, 生日, 礼物]` 交集可以帮助定位证据；`[饮酒, 争吵]` 共现不能自动写成“饮酒导致争吵”。正确输出应是 `CandidateAssociation/CAUSAL_HYPOTHESIS`，再由反例、时间方向和 Prediction 验证。

**结论**：`检索基础部分对齐，但 V3 原生联合检索、中文语义、排名、LOD 和早期规模门缺失。`

---

# 3.5 端侧边缘轻量摄入：图像、语音、声纹、IMU/心率

## V3 要求

V3:L455–483 要求在端侧完成：

- IMU/心率降采样、状态与异常波形提炼；
- 图像语义化文字/OCR，不直接复制原始大图；
- ASR、声纹 embedding、未知实体绑定与半年冷热淘汰；
- 每日由模型提议清洗噪声并保留关键证据。

## 下游现状

- ARCH 的 C01 只有格式、单位、时间、来源和重复包（ARCH:L88）；
- M0-007 只定义通用 `source_kind/modality/value/unit/data_quality/raw_locator`，并把高频 block 后移（TASK:L463–506）；
- M1-001 直接把虚拟 GPS、心率、IMU、文本、App 数据写 Observation，验收是 10k 心率批量写入（TASK:L1219–1262）；
- 声纹在任务书中只作为实体解析/验证测试素材出现，没有采集、embedding、质量、spoof risk、生命周期或淘汰服务；
- 图像 caption/OCR、ASR、特征模型版本、设备算力预算均没有 Issue；
- M3-004 反而要求原始数据数量不变并禁止总结后删日志（TASK:L2854–2864）。

因此，M1-001 确实漏掉了多模态边缘降噪和声纹生命周期。10k 心率写入测试也不能代表真实高频摄入：

- 100 Hz 每天是 **8,640,000 个采样时刻**；一年约 **31.5 亿**；
- 50 Hz 每天是 4,320,000 个采样时刻；
- 10k 条只相当于单通道 100 Hz 的 100 秒；
- 本仓库极简 360 万对象结构库已约 1.69 GiB，且尚未存真实 payload、图像、音频和向量。

若把 IMU 每个采样点、连续音频和大图按旧通用接入直接落库，存储、写放大和上传带宽必然失控。

## 但 V3 也不能原样实施

V3:L369–383 又要求底层物理观测和原话永存，而 L476–483 要求每日物理删除噪声；两者没有保留分级、legal hold、延迟删除或审计协议。直接让 LLM 拥有不可逆删除权会破坏证据链。

正确补丁应是：

1. 原始高频数据进入端侧加密 ring buffer，不逐点长期入 Core；
2. 长期保存多分辨率特征、质量、异常窗口和 transform model/version；
3. 关键图像保留有 TTL 的加密缩略图/关键帧或 hash+locator，普通图像只保留派生语义；
4. 声纹作为 `SpeakerCluster` 候选，不直接认定 Entity；
5. 半年规则只退休低价值生物模板，不能删除历史实体引用；
6. LLM 只能提出 retention decision，确定性 worker 根据策略、引用锁和审计执行；
7. 当前阶段只实现 Linux 上的**模拟端侧适配器和数据缩减比测试**，不把真实硬件拉入关键路径。

**结论**：`P0 Gap + V3 自身 retention 冲突；先修契约，再重写 M1-001。`

---

# 3.6 穿戴物理形态：震动先导 FSM 与三层 UI

## V3 要求

- V3:L1300–1329：柔性全屏手环、震动语义、IDLE→TRIGGERED→显示/骨传导/超时；
- V3:L1367–1407：体态与触觉 → Core Ambient Canvas → 可挂载技能微界面；
- V3:L1417–1421：本地只做信号、ASR、声纹、基础视觉，不做高层语义。

## 现有设计的真实判断

ARCH:L20–24 明确实体手环不进入第一阶段关键路径，ARCH:L109–123 选择浏览器控制台；M1-015 实现的也是开发者控制台。这**符合当前“Linux + 虚拟用户”目标，也符合 V3 对调试控制台的要求**，不应为了对齐 V3 就把 M1 改成柔性屏前端开发。

真正缺失的是跨阶段契约：

- 没有 `WearableInteractionPort`；
- 没有 haptic pattern、display summary、bone-conduction、speaker、side-button、gesture 的 typed command/event；
- 没有 Notification ID、content revision、应答 window、epoch、取消与重启恢复；
- 没有软件 FSM 或模拟器场景；
- M6-001 的 AppManifest/Capability 只有通用 permission 和工具字段（TASK:L3542–3585），没有 Ambient Canvas card projection、插件 UI 生命周期和最小上下文 scope；
- 没有测试“未收到当前 notification 的手势绝不能播放”“两个窗口重叠”“TRIGGERED 时重启”“用户取消/超时”。

V3 的“零误触”是绝对宣传语，FSM 只能降低误触概率。软件可保证的是：**无有效 notification epoch 时，播放命令必定被拒绝**；通知本身误报和窗口内偶然摸耳仍需多信号与真实硬件测量。

## 当前阶段正确落地方式

- 继续保留 PC 开发者工作台；
- 在 M2 加一个设备无关 `InteractionPort + FSM Simulator`；
- 在 M6 加 Ambient Canvas/SkillCard 数据投影协议；
- 用虚拟手势、并发通知、掉电和误触场景验证状态机；
- 柔性屏、马达音频、功耗、温升和人体可懂度只进入 `POST-M8-HW` Gate，不进入当前 Core 关键路径。

**结论**：`当前不做硬件是正确范围控制；但软件边界与模拟 FSM 完全缺失。`

---

# 3.7 虚拟世界测试：V21~V30 与 V3 高阶验收

## 现有测试规范并不“只会测 1 天/1 月/1 年”

TEST 已经包含：

- 隐藏真值四层隔离（TEST:L26–44）；
- 噪声、延迟、缺失、重复和模糊表达（TEST:L98–108）；
- 固定回放与行动改变世界两类实验（TEST:L163–186）；
- 强 B2 基线和公平赛道（TEST:L190–232）；
- V01~V20 的身份纠错、同名、长任务、拒绝、模型中断、紧急抢占和旧总结等场景（TEST:L236–261）；
- 证据、纠错、任务、成本和盲测指标（TEST:L265–427）。

所以其科学实验框架仍值得保留。问题是它停在 2026-09-14 的 R2 版本。

## 确切断层

1. TEST 的场景矩阵只定义 V01~V20；
2. V3:L1604–1621 才定义 V21~V30；
3. TASK M4-004 只写一句“V01~V30 覆盖”（TASK:L3375–3378），却没有将 V21~V30 的输入、隐藏真值、变体和判定条件写入 Issue；
4. V3 的 R3-01~R3-07、V3-01~V3-03 没有进入 TEST；
5. Single-Shot、50 轮流式对话、通用条件任务、原生 co-search、关系节奏心跳、1~3 句、端侧缩减和 wearable FSM 没有场景编号；
6. 现有 Issue 普遍没有按 V3:L1545–1560 要求显式列出“单元测试、集成测试、验收场景编号、已知限制”四个独立项目。

## 关于任务描述中例子的校正

V3 当前的 V21~V30 实际是：高频输入、预测语气、EvidenceSet、迟到数据、派生维度、无收益维度、Goal/Task、推断 Goal 否认、Event 否定和月度下钻。它们**不包含**“老王身份反转、50 轮长对话、静默心跳抑制”。

- 身份反转可强化现有 V04/V29；
- `[老王, 借钱, 争执]` 是 V3 的检索示例，不是已编号验收场景；
- 50 轮对话来自第八十五条；
- 长平稳心跳来自第八十条。

这意味着 Gap 比“缺 V21~V30”更大：**V3 新运行机制本身尚无对应 V31+ 场景。**

**结论**：`测试方法论强，但需求版本陈旧；M4-004 的“V01~V30 覆盖”目前是不可验收的空引用。`

---

# 4. 全量重大断层清单

以下列出本次发现的所有 P0/P1 级实质断层；不把文案风格差异冒充工程 Gap。

| ID | 级别 | 状态 | V3 要求 | 当前断层 | 最早失效点 | 修复入口 |
|---|---:|---:|---|---|---:|---|
| GOV-01 | P0 | C | V3 唯一基线 | ARCH/TASK 仍显式以 V2/R2 为上位依据 | M0 | M0-023 |
| GOV-02 | P0 | C | 唯一模块责任 | C05/C06/C09 在 ARCH 与 V3 中含义不同 | M0 | M0-023 + ARCH 重发 |
| GOV-03 | P1 | C | M0~M8 | ARCH 仍是 M0~M6，里程碑名称冲突 | 管理层 | M0-023 |
| GOV-04 | P1 | G | 每 Issue 12 要素 | 现有 A~J 没有独立场景映射和已知限制 | 全阶段 | TASK 模板升级 |
| OBJ-01 | P0 | G | 22 个核心对象 | TASK 只冻结 19 个，缺 Prediction/LifeChapter/CommunicationExperience | M0 | M0-024~026 |
| OBJ-02 | P0 | C | Prediction 一等对象 | 现有 `ClaimType.PREDICTION` 与新一等对象并存但无迁移语义 | M0 | M0-024 |
| OBJ-03 | P0 | G | 11 类 Task | TASK 只有 10 类，缺 PredictionCheckTask | M0 | M0-014/M0-024 |
| DATA-01 | P0 | G | 多源轻量摄入 | Observation 无 transform/provenance/retention 完整契约 | M0/M1 | M0-007/M0-030 |
| DATA-02 | P0 | N | 原始永存 vs 噪声删除 | V3 自身相冲突，下游选择“全部保留” | M1/M3 | v3.0.1 + M1-019 |
| DATA-03 | P1 | G | 内心数据回溯标注 | 无 RetrospectiveAnnotation/valid-known 查询测试 | M1/M3 | M3-012 |
| CKT-01 | P0 | P | Single-Shot Manifest | workspace.open 是雏形，但无 Manifest 版本/预算/deadline | M2 | M0-029/M2-009 |
| CKT-02 | P0 | N | 四步绝对顺序 | 与 Wake first、方便度 first 内部冲突 | M2 | v3.0.1 + M2-012 |
| CKT-03 | P0 | G | 只挂就绪 Task | 初始包/任务面板没有 ready-only 硬不变量 | M2 | M2-005/M2-009 |
| TASK-01 | P0 | G | 通用 Trigger Criteria | 仅 Watch 有有限 condition；Task 无 AST | M0/M2 | M0-027/M2-005 |
| TASK-02 | P0 | G | 按需激活 | 无事件订阅索引、增量求值和 ReadyTaskQueue | M2 | M2-005/006 |
| TASK-03 | P1 | P | context_matched | 已区分机械/语义，但无 UNKNOWN、复查间隔和成本门 | M2 | M2-007 |
| CTX-01 | P0 | G | Active Rolling Window | 无 conversation/turn/工作集协议 | M0/M2 | M0-028/M2-016 |
| CTX-02 | P0 | G | Incremental Streamer | 无异步萃取 Issue、水位、幂等和重试 | M2 | M2-017 |
| CTX-03 | P0 | G | 主动联想召回 | 无前台查询线索解析、抽取水位与召回融合器 | M2 | M2-018 |
| SLO-01 | P0 | G | 约 1 秒首字 | 无 TTFU/TTFT/TTFAudio/最终有用延迟分解及百分位 | M2 | M2-019 |
| QRY-01 | P0 | P | `world.co_search` | 有混合筛选/超链，但没有原子联合共现查询 | M1 | M1-012/M1-018 |
| QRY-02 | P0 | G | 中文复合检索 | 无 tokenizer/别名/否定/角色/排名版本 | M1 | M1-018 |
| QRY-03 | P1 | P | 5D 时间镜头 | 已有 view/zoom/shift，缺双时态 LOD、target points 与 rollup 计划 | M1/M3 | M1-010/M3-005 |
| QRY-04 | P1 | C | 因果穿透 | V3 把共现写成因果，下游正确地不应自动定因果 | M1/M3 | v3.0.1 + M1-011 |
| ING-01 | P0 | G | IMU/心率边缘压缩 | M1-001 仍以通用 Observation 批量写入为主 | M1 | M1-001/M1-017 |
| ING-02 | P0 | G | 图片 caption/OCR | 无图像派生、模型版本、质量、关键帧 TTL Issue | M1 | M1-017/M1-019 |
| ING-03 | P0 | G | 声纹绑定/冷热淘汰 | 只有测试素材，无 SpeakerCluster 服务和生命周期 | M1 | M1-002/M1-017 |
| WAKE-01 | P1 | G | 关系节奏/长平稳心跳 | M2-002 只有 no-update；“有采样但平稳”与关系节奏无实现 | M2 | M2-002 |
| WAKE-02 | P1 | G | 个性化阈值演进 | 只有 trigger.update 泛接口，无基线版本/回滚/eval Issue | M2/M4 | M2-002/M4-005 |
| PERS-01 | P0 | G | AI seed dimensions | M3-010 是泛 self world，无 Identity/Rapport/Promise 初始化契约 | M0/M3 | M0-026/M3-010 |
| PERS-02 | P0 | G | CommunicationExperience | TASK 对象、服务、评估均缺失 | M0/M3 | M0-026/M3-014 |
| PERS-03 | P1 | G | 1~3 句/反谄媚/反说教 | 无输出契约、例外、场景或指标 | M2/M4 | M2-023/M4-005 |
| PRED-01 | P0 | G | Prediction Register | 无 schema/service/check scheduler/校准/失效传播 | M0/M2 | M0-024/M2-020 |
| LIFE-01 | P0 | G | LifeChapter | 无 schema、候选判定、归档和基线迁移任务 | M0/M3 | M0-025/M3-013 |
| DEP-01 | P0 | P | 有限纠错传播 | M3-001 只写最大深度/批量，缺 typed policy、visited/SCC、epoch、continuation、no-op diff | M3 | M0-015/M3-001 |
| WEAR-01 | P1 | G | 震动先导 FSM | 无设备无关状态机和仿真故障测试 | M2/M8 | M2-021 |
| WEAR-02 | P1 | G | Ambient Canvas/Skill UI | 浏览器仅是调试器；无手环投影 DTO 和插件 UI 生命周期 | M6 | M6-001/M6-005 |
| SEC-01 | P0 | G | 多源聊天/OCR/插件输入 | 无 instruction/data trust lane 和长期记忆写入防火墙 | M0/M2 | M0-030/M2-018 |
| TEST-01 | P0 | G | V21~V30 | TEST 仅 V01~V20；M4-004 只空泛引用 V01~V30 | M2/M4 | TEST V0.2/M4-005 |
| TEST-02 | P0 | G | V3 新运行机制 | 无 Single-Shot、50 轮、条件任务、co-search、心跳、FSM 场景 | M2/M4 | V31~V45 |
| SCALE-01 | P0 | C | 可实施检索/调度 | 360 万规模首次正式门在 M7，发现 schema 问题过晚 | M1 | M1-020 + M7-002 |

---

# 5. V3 新增但完全未进入任务书的四个核心域

七项专项之外，还有四个不能遗漏的 V3 断层。

V3 自身的开发治理表也需要同步修正：第七十一条列出 22 个第一版核心对象（V3:L930–957），但 M0 “必须冻结项”（V3:L1508–1510）没有列出 Prediction、LifeChapter、CommunicationExperience 等新增契约。所以下游遗漏不能只归咎于任务书；v3.0.1 必须先明确哪些新增对象在 M0 冻结 schema、哪些只冻结扩展槽位并在 M2/M3 实现行为。

## 5.1 Prediction 被误当成 Claim 枚举，而不是一等闭环

V3:L699–746 定义独立 Prediction；V3:L945 又把它列为核心对象。TASK 只在 M0-008 的 `claim_type` 枚举中出现 `PREDICTION`（TASK:L523–529），没有 Prediction schema、Register、verification state、actual outcome、check task 或 API。

必须定义兼容语义：

- `Claim(type=PREDICTION)` 是历史 R2 表述，迁移为或引用 `Prediction`；
- Prediction 必须引用一个或多个 source claims/evidence；
- PENDING/CORROBORATED/FALSIFIED/INCONCLUSIVE/EXPIRED 分开；
- 到期无观测不能自动等同证伪；
- 模型/规则 evaluator 版本、观测覆盖和干预引用必须记录；
- 证实不能机械无限抬高 source Claim 置信度。

## 5.2 LifeChapter 没有任何 schema 或 Issue

V3:L400–406、L947 将 LifeChapter 定义为一等抽象，V3 模块图也把它交给 C05；TASK 全文没有 `LifeChapter`。M3-004/005 只做日周月日历总结，无法表达非日历章节、候选相变、归档和新基线。

## 5.3 CommunicationExperience 没有任何对象、服务或验收

V3:L124–126、L918–920、L956 要求按表达方式、语气、用户反应积累沟通经验。TASK 的 M5 只验证通用 OperationExperience；M3-010 只记录接受/拒绝事实，未定义 CommunicationExperience。于是 V3 的“人格进化”最后只能重新退化为 prompt 文案。

## 5.4 有界依赖传播仍不足以防雪崩

M3-001 的“限制最大传播深度/批量”是正确起点，但没有：

- dependency kind 对应 HARD/SOFT/NONE invalidation policy；
- InvalidationEpoch、全局 visited 和 SCC；
- 超级节点 fan-out 预算与 continuation cursor；
- 同一 dependent 多路径合并；
- input fingerprint、结构化 semantic diff 和 no-op 终止；
- worker crash/重复投递幂等；
- stale 查询可见性。

上一份正式架构审查的 360 万探针中，一个超级节点有 360,004 个直接下游；查出它们只需约 133~138 ms，但若随后同步发起 36 万次重算或模型调用，系统会雪崩。该机制必须在 M3 前任务化，而不是靠一句“防爆炸”。

---

# 6. 总工任务书必须重写/升级的现有 Issue

动作定义：`KEEP` 保留；`UPGRADE` 保留编号并扩展契约；`REWRITE` 目标语义发生实质变化；`SPLIT` 原 Issue 过大，需拆出新 Issue。

| Issue | 动作 | 必须修改的内容 | 新增阻断验收 |
|---|---:|---|---|
| M0-007 Observation | `REWRITE` | 加 SourceEnvelope、transform lineage、signal quality、retention class、raw locator TTL、派生/原始区别 | 同一原始片段可追踪到派生 Observation；不允许语义派生冒充原始测量 |
| M0-014 Task/Wake/... | `REWRITE` | 加 TriggerExpression ref、activation state、eligibility revision；TaskType 加 PREDICTION_CHECK | 没有有效触发表达式的非即时任务拒绝进入等待态 |
| M0-015 Dependency | `UPGRADE` | typed edge、invalidation policy、valid time scope、derivation/evaluator version | 语义关联默认不传播；Task guard 可暂停高风险 Action |
| M0-021 状态机 | `UPGRADE` | 加条件状态、Prediction 状态、LifeChapter 生命周期；明确 UNKNOWN/INCONCLUSIVE | 非法跳转全覆盖；迟到证据不篡改旧状态历史 |
| M0-022 M0 Gate | `REWRITE` | schema snapshot 从 R2 升 V3；纳入新增对象/协议和 migration fixtures | 核心清单与 V3 数量、枚举、API 全匹配，0 个 unmapped 条款 |
| M1-001 Ingest | `REWRITE` | 只负责规范 envelope/去重/提交；把高频 reducer、多模态 transform 交给 M1-017 | 100 Hz feed 不等于 100 Hz DB rows；每批有 reduction stats |
| M1-002 Entity | `UPGRADE` | 引入 SpeakerCluster candidate、质量、模型版本、DISPUTED/RETIRED；声纹不得直接定身份 | 回放/低质量样本不能独立 resolve Entity；退休模板不破坏旧引用 |
| M1-009 Dependency | `UPGRADE` | 建 exact revision 反向索引和 edge kind/filter API | 超级节点查询可分页，语义关联不进入 invalidation 集合 |
| M1-010 Time Lens | `REWRITE` | 统一 `TimeLensQuery`：valid time、known at、world revision、LOD、target_points、uncertainty | raw/rollup 自动选择可解释；knowledge/world cutoff 不越界 |
| M1-011 Align | `UPGRADE` | 输出 CandidateAssociation、基线、反例窗口和 coverage，不输出因果 | 共现只生成假说候选，不能生成 CAUSAL 已成立边 |
| M1-012 Search | `REWRITE` | 原生 `world.co_search`；联合 term/entity/time/graph query plan；统一 rerank | `[妈妈,生日,礼物]` 一次请求；中文、否定、别名、角色 fixture 通过 |
| M1-014 Index | `UPGRADE` | FTS、postings、alias、vector、graph、rollup 各自水位与重建 | 查询返回每类水位、partial/truncated/coverage |
| M1-016 M1 Gate | `UPGRADE` | 除运动会案例外，加入 joint co-search、LOD 和 edge reduction 贯穿测试 | 未通过早期 100 万规模/中文查询不得进 M2 |
| M2-002 Trigger | `REWRITE` | 区分 stable-with-samples、source silent、关系节奏；阈值版本化 | 高频稳定 0 逐条 Wake；静默心跳在忙碌/睡眠情境只产生后台检查不发声 |
| M2-004 Queue | `UPGRADE` | 只接收 Wake 与 READY task occurrence；eligibility snapshot 可审计 | 10 万 WAITING 不进入模型队列；抢占后可恢复 |
| M2-005 Task Center | `REWRITE` | TriggerExpression evaluator、subscription index、ReadyTaskQueue、三值状态 | 10 万 Task/10 ready 无全表遍历；ready-only 暴露 |
| M2-006 Task 语义 | `REWRITE` | TODO 不再强制周期模型盘点；由事件订阅/机械 next evaluation 激活 | 无新事件时 TODO 不产生模型调用；DST/迟到/catch-up 全测 |
| M2-007 Watch | `UPGRADE` | 与通用 AST 共用机械谓词；语义 gate 有预算、最短复查、UNKNOWN | semantic gate 不自激，不因缺数据判 FALSE |
| M2-009 Workspace | `REWRITE` | 返回版本化 CockpitManifest；ready-only task、AI identity/rapport/promises、对话水位、预算/partial | 每类 Wake 一次首包；无分段 onboarding prompt；Manifest P95 大小可测 |
| M2-010 Tools | `UPGRADE` | 加 `world.co_search/navigate/focus`、`time.select_range`、`task.create_conditional/inspect_ready`、Prediction/LifeChapter API | V3 原子接口都有 schema、权限、错误码和兼容 alias |
| M2-011 Session | `UPGRADE` | 区分 WorkSession 与 Conversation；checkpoint 记录 turn/extraction/context watermarks | Worker crash 后不重复抽取、不漏 pending turn、不重复 Action |
| M2-012 Worker | `SPLIT` | 保留 Manifest 后自主工具循环；移除“十三步心智顺序”；把 active window/streamer/context assembler 拆至 M2-016~018 | 工具轮次有目的、预算和 deadline；系统占位轮次为 0 |
| M2-014 Simulator | `UPGRADE` | 生成高频原始 feed、多模态素材、关系节奏、长会话，不直接给已降噪答案 | 原始 feed 与 Core 可见派生数据分层且可重放 |
| M2-015 M2 Gate | `REWRITE` | Gate 加条件任务、Single-Shot、50 轮对话、SLO 和关系心跳 | 任一 P0 场景失败不得以“主动帮助 demo 成功”放行 |
| M3-001 Invalidation | `REWRITE` | epoch/visited/SCC/fan-out budget/continuation/coalesce/fingerprint/no-op diff | 环、菱形、10 万扇出、重复投递、crash 全部有界终止 |
| M3-004/005 Summary | `UPGRADE` | 自适应物化、直接证据覆盖、rollup 水位；禁止空维度全量生成 | 冷维度不制造空总结；高层可直接回到底层反例 |
| M3-010 AI World | `REWRITE` | 初始化 Identity/Rapport/Promises/Growth/ActionLog；AI 自述不能成为用户独立证据 | 模型切换人格状态连续；self-loop 不抬高用户 Claim 信心 |
| M3-011 M3 Gate | `UPGRADE` | 加 Prediction、LifeChapter、CommunicationExperience、回溯标注和有界传播 | 这些对象全部进入同一连续虚拟人回放 |
| M4-001 Month | `UPGRADE` | 精确定义 V21~V30 与新增 V3 场景数据，而非只引用编号 | 每个场景有正例、近似反例、证据不足版 |
| M4-002 Metrics | `UPGRADE` | 加 TTFT/TTFAudio、manifest tokens、waiting-task exposure、task evaluations、extraction lag、co-search quality、句数 | 成本统计包含后台抽取、索引、预测检查和维护 |
| M4-004 Experiment | `REWRITE` | 不得只写“V01~V30 覆盖”；逐场景 manifest、oracle、判定器和失败归因 | 每个场景结果可定位到 data/trigger/context/search/reason/dependency/task |
| M6-001 App/Capability | `UPGRADE` | capability-scoped context、SkillCard/AmbientCanvas projection、UI 生命周期、输出通道 | 插件不能因“共享大脑”默认读全量人生；卡片退场后无残留权限 |
| M7-002 Scale | `KEEP+MOVE LEFT` | 保留年度真实规模测试，但把 schema/中文/Task/图超级节点探针提前到 M1/M2 | M7 不得成为第一次运行百万级 SQL 的阶段 |
| M8-003 Hardware Gate | `UPGRADE` | 明确软件 FSM 通过不等于物理硬件通过；列功耗/热/可懂度/误触/隐私证据 | 证据不足保持 Core-only，不因沉没成本进入硬件 |

应明确保留且无需因 V3 推倒的 Issue：M0-004~006、M0-016~020、M1-005~008、M1-013、M1-015、M2-003、M2-008、M2-013，以及 TEST 的隐藏真值/强基线/公平赛道框架。

---

# 7. 必须新增的细粒度 Issue

以下编号接续现有任务书，避免覆盖历史编号。每项仍须按 V3 的 12 要素模板展开后才能派单。

## 7.1 M0：先补契约，禁止边写 M1 边猜

| 新 Issue | 目标与关键输出 | 阻断验收 |
|---|---|---|
| **M0-023 V3 Authority & Traceability Freeze** | 冻结 V3 文件 hash、唯一 C01~C14 映射、M0~M8 映射、旧 API→V3 API 兼容表；生成 clause→module→issue→test 矩阵 | `CONFLICT/UNMAPPED` 为 0 才可重新开 M0 Gate；V3 自身冲突必须有 v3.0.1 决议号 |
| **M0-024 Prediction / PredictionCheckTask Contract** | Prediction schema、EvidenceSet、验证状态、evaluator version、coverage、intervention、actual outcome；TaskType 新增预测检查 | ClaimType.PREDICTION 迁移 fixture；无观测→INCONCLUSIVE，不得自动 FALSIFIED |
| **M0-025 LifeChapter Contract & Lifecycle** | `CANDIDATE/ACTIVE/ARCHIVED/REVISED/REJECTED`、时间范围、基线 refs、EvidenceSet、前后章节、迁移原因 | “永久相变”不能一次信号直接 ACTIVE；旧章节和旧基线可重建 |
| **M0-026 CommunicationExperience & AI Seed Dimensions** | CommunicationExperience 字段；Identity/Rapport/Promises/Growth/ActionLog 稳定 seed IDs 和版本语义 | 缺 delivery 的无回应不得推导抵触；风格效果与事实立场分开 |
| **M0-027 TriggerExpression & Task Eligibility Contract** | AST：TimeReached/EventMatched/ObservationPredicate/DependencyReady/AllOf/AnyOf/Not；三值、版本、订阅键、expiry | 任意非即时任务都有可执行 trigger 或明确 manual-only；任意 Python eval 被拒绝 |
| **M0-028 Conversation Stream Contracts** | Conversation/Turn envelope、seq、speaker、finalization、ExtractionSpan/Job/Watermark、ContextSlice | 重复 turn/重复 span 幂等；乱序与未完成 turn 不被错误萃取 |
| **M0-029 CockpitManifest Contract** | wake、安全、identity、rapport、objective、current evidence、ready tasks、capabilities、conversation/extraction watermarks、omissions、budget | JSON schema snapshot；WAITING task 泄露数为 0；每项带 freshness/source |
| **M0-030 Source Trust, Transform & Retention Contract** | SourceEnvelope、instruction trust lane、transform lineage、model/firmware version、retention class、legal hold、tombstone/audit | OCR/群聊内容默认 DATA 而非指令；LLM 无不可逆删除权限 |

## 7.2 M1：补齐数据脊柱、联合检索和早期规模门

| 新 Issue | 目标与关键输出 | 阻断验收 |
|---|---|---|
| **M1-017 Simulated Edge Reduction Pipeline** | Linux 模拟 Camera→caption/OCR、Audio→ASR+SpeakerCluster、IMU/HR→window features/anomaly snippets；输出 reduction report | 50/100 Hz 原始 feed 不逐点落长期库；异常窗口召回率与压缩比同时报告 |
| **M1-018 Chinese Hybrid Co-search Engine** | 预分词/词典版本、entity postings、FTS、vector adapter、bounded graph expansion、fusion rerank、`world.co_search` | 连续中文、别名、否定、角色错位、零命中和 partial index 全部有 fixture；结果给 hit reasons |
| **M1-019 Retention & Tombstone Worker** | 确定性 TTL、引用锁、两阶段删除、加密擦除接口、审计、SpeakerCluster retirement | 被 EvidenceSet/Task 引用的数据不能删；删除重试幂等；历史引用返回 tombstone 而非断裂 |
| **M1-020 Early Scale & Query Plan Gate** | 10 万/100 万/360 万对象；中文 co-search；raw vs rollup；高扇出图；WAL 长 reader；10 万 Task 索引雏形 | 固定环境 P50/P95/P99、DB/index size、SQL plan；失败则禁止冻结查询 schema |

## 7.3 M2：补齐真正的运行时

| 新 Issue | 目标与关键输出 | 阻断验收 |
|---|---|---|
| **M2-016 Active Conversation Working Set** | Token-budgeted recent turns + unresolved topics/pronouns/promises + post-watermark turns；不是死 5~8 轮 | 50 轮中跨 20 轮代词/承诺仍可恢复；前台 prompt 有硬预算和省略说明 |
| **M2-017 Incremental Streaming Extractor** | 话题/turn 边界、异步 ExtractionJob、幂等、backpressure、revision conflict、dead letter | crash/retry 不重复 Claim/Event；lag 超阈值时前台自动保留未萃取原文 |
| **M2-018 Proactive Recall & Context Assembler** | 实体/事件/任务/原话/反证联合召回；deadline-aware L0/L1/L2；instruction/data 隔离 | 不同 Wake manifest 显著不同；旧话题重提召回正确且恶意 OCR 不能变系统指令 |
| **M2-019 End-to-End Latency & Token Telemetry** | TTFU、TTFT、TTFAudio、FinalUsefulLatency；ASR/检索/prefill/TTS 分段；P50/P95/P99 | 冷/热、Mock/真实模型、partial/degraded 分开报告；无数据不得宣称保障 1 秒 |
| **M2-020 Prediction Register Runtime** | create/query/due/verify；PredictionCheckTask 调度；证伪进入有界 invalidation | 到期、迟到、缺测、AI 干预、自我实现、重复检查均可重放且幂等 |
| **M2-021 WearableInteractionPort & FSM Simulator** | typed haptic/display/private-audio/speaker/gesture/button；notification epoch；IDLE/ARMED/PLAYING/EXPIRED/CANCELLED/FAULT/RECOVERY | 无有效 epoch 的摸耳播放为 0；并发通知、重启、超时、取消不串内容 |
| **M2-022 Relationship Rhythm & Quiet-heartbeat Policy** | stable-data heartbeat、rapport cadence candidate、busy/sleep/driving mechanical prefilter、用户反馈冷却 | 平稳 24h 不产生固定 3~5h 轰炸；不方便时模型可不唤醒或只后台检查，外部通知为 0 |
| **M2-023 Concise Response & Interaction Outcome Contract** | sentence count/language mode、expand request、安全/无障碍例外、delivery/seen/ignored/unknown、style metadata | 普通短对话默认 1~3 句；复杂安全信息不因句数被截断；无回应不等于拒绝 |

## 7.4 M3：补齐纠错后的长期认知

| 新 Issue | 目标与关键输出 | 阻断验收 |
|---|---|---|
| **M3-012 Retrospective Semantic Annotation** | 迟到用户自述以 valid_time+learned_at 追加到旧时间切片；原始物理 Observation 不改 | 可重建“当时不知道”和“今天回看”；心率原值 revision 不变 |
| **M3-013 LifeChapter Candidate & Baseline Migration** | 多维 change-point 只产生候选；经持续、反证、迟滞后确认；旧敏感度版本归档 | 短期旅行/生病不误判永久章节；毕业/迁居等稳定变化可确认并回滚误判 |
| **M3-014 CommunicationExperience & Rapport Consolidation** | 从 Action/Outcome/Delivery 提炼候选沟通经验；适用范围、反例、过期；rapport 只影响表达成本 | 不以讨好换接受率；反谄媚事实阈值在不同 rapport 下保持一致 |
| **M3-015 Prediction Calibration & No-op Propagation** | Brier/log score、分桶校准、重复/相关预测去重、semantic no-op diff | 模型只换措辞不传播；预测很多但不校准不得提高源 Claim 信心 |

## 7.5 M4/M5/M6：把机制变成可验收能力

| 新 Issue | 目标与关键输出 | 阻断验收 |
|---|---|---|
| **M4-005 V3 Scenario Pack V21~V45** | 把 V3 V21~V30 原样工程化，并新增本报告第 8 节场景；每个含 oracle、正/反/不足、seed、预算 | 每项可独立运行，不能只在月度大脚本里笼统标“覆盖” |
| **M4-006 Runtime Stress & Ablation Pack** | 50 轮对话、10 万 Task、中文 co-search、Wake storm、extractor crash、FSM overlap、memory injection | 失败可归因到七层；后台成本计入总 Token/CPU/I/O |
| **M5-004 CommunicationExperience A/B** | 同一世界检查点比较“可读沟通经验/不可读沟通经验”；覆盖相似情境、误迁移、经验过期、反谄媚事实冲突 | 只有在未见情境中提高净帮助且不增加谄媚、操控和错误事实，才允许经验进入优先建议 |
| **M6-005 AmbientCanvas / SkillCard Projection Contract** | 设备无关卡片 DTO、生命周期、layout budget、accessibility fallback、capability scope | 插件只能获得最小上下文投影；卡片过期/撤权后不能调用能力 |

真实柔性屏、马达骨传导和人体实验应登记为 `POST-M8-HW-001`，只在 M8-003 通过后启动，不得反向阻塞当前 Linux Core。

---

# 8. 测试规范必须增加的场景

## 8.1 先把已有 V21~V30 正式下传

TEST V0.2 必须逐项复制 V3:L1608–1619 的定义，并增加 fixture、隐藏真值、近似反例和证据不足版。TASK M4-004 不能再只写“覆盖 V01~V30”。

## 8.2 新增 V31~V45

| 编号 | 场景 | 硬验收重点 |
|---|---|---|
| V31 | Single-Shot Cockpit | 模型在一次 `workspace.open` 获得完整首包；分段 onboarding prompt=0；Manifest 有版本、预算、遗漏和水位 |
| V32 | 启动优先级冲突 | 安全/当前输入/权限不被人格步骤阻塞；rapport 只改变表达，不改变证据阈值 |
| V33 | 50 轮长对话 + 后台萃取 | 活跃工作集不爆 Token；Claim/Event 不重不漏；extractor crash 后续办 |
| V34 | 旧话题突然重提 | 实体别名、历史事件、承诺和关键原话按需召回；水位后的原始 turn 被回读 |
| V35 | 10 万条件 Task，仅 10 个 ready | 无 Task 全表扫描、无 waiting task 入 prompt、无周期模型空转 |
| V36 | 条件边界 | DST、时区迁移、迟到事件、UNKNOWN 质量、抖动、A AND B 时间窗、循环依赖 |
| V37 | 中文多关键词共现 | `[妈妈,生日,礼物]`、别名、代词、否定句、角色反转、短词和零命中；返回 query plan/hit reasons |
| V38 | 5D/LOD 时间镜头 | 年→月→日→原话；raw/rollup 自动切换；known_at/world revision 不越界 |
| V39 | 边缘摄入与存储缩减 | 100 Hz IMU、平稳/异常心率、图片、录音；缩减比、异常保真、模型版本和 retention 全可审计 |
| V40 | 声纹冒认与冷热淘汰 | 噪声/回放/合成候选不直接 resolve；半年退休不破坏历史 Entity/Event 引用 |
| V41 | 长平稳心跳与情境抑制 | 有持续采样但稳定；工作/驾驶/睡眠时不外部打扰；反馈后频率下降但安全旁路仍工作 |
| V42 | Prediction 主动证伪 | PENDING→证实/证伪/缺测；干预改变结果；重复检查幂等；校准可计算 |
| V43 | LifeChapter 候选与误报 | 暂时异常不成章节；稳定结构变化可确认；旧基线归档、误判可修正 |
| V44 | 真人短表达与人格边界 | 日常默认 1~3 句；能应用户要求展开；不谄媚、不教师爷；安全/无障碍例外完整 |
| V45 | Wearable FSM 与恶意输入 | 无先导 epoch 不播放；通知重叠/重启/超时正确；OCR/聊天注入不能获得指令权限 |

## 8.3 新增工程指标

除现有净帮助和正确性指标外，至少增加：

- `manifest_tokens / manifest_build_ms / omitted_count / partial_rate`；
- `waiting_tasks_exposed_to_model`（目标 0）；
- `task_rows_examined_per_ready_task`；
- `model_calls_per_task_evaluation`；
- `extraction_lag_turns / duplicate_extractions / missed_spans`；
- `recall_precision/recall`、term coverage、反证覆盖；
- `TTFU/TTFT/TTFAudio/FinalUsefulLatency P50/P95/P99`；
- edge reduction ratio、异常窗口召回、长期 bytes/day；
- `false_wake_rate / false_playback_without_epoch`；
- 默认短答合规率、安全错误截断率、用户要求展开成功率；
- Prediction calibration 与 LifeChapter false-positive/confirmation delay；
- 后台抽取、索引、预测检查和维护的全部 Token/CPU/I/O 成本。

---

# 9. 要达到“100% 严丝合缝”必须通过的四道门

## G0 — Normative Consistency Gate

发布 v3.0.1，至少裁决：

1. Wake first / convenience first / self first 的优先级；
2. 原始永存与日度物理删除；
3. 共现与因果的边界；
4. 1 秒、1~3 句、零误触等条款的适用条件和例外；
5. 唯一 C01~C14 模块映射；
6. M0 冻结清单补入 Prediction/LifeChapter/CommunicationExperience/PredictionCheckTask。

## G1 — Contract Completeness Gate

- V3 每个一等对象、状态、接口和交互命令都有 schema；
- 旧 R2 数据有明确迁移/兼容策略；
- TriggerExpression、Conversation/Extraction、Manifest、Source/Retention 契约冻结；
- schema snapshot 与 traceability matrix 进入 CI。

## G2 — Runtime Mechanism Gate

- Single-Shot Manifest；
- ready-only conditional scheduling；
- active window + incremental streamer + associative recall；
- native co-search + LOD time lens；
- simulated edge reduction；
- Prediction、CommunicationExperience、LifeChapter、有界 invalidation；
- wearable interaction simulator。

任何一项不能只靠 system prompt 声称完成。

## G3 — Scenario & Scale Gate

- V01~V45 有可重放 manifest；
- 10 万/100 万/360 万规模测试提前；
- 50 轮长会话、10 万 Task、中文查询、超级节点、crash、噪声和注入全部覆盖；
- 所有成本计入公平比较；
- 失败时能落到 data/trigger/context/search/reasoning/dependency/task 七向归因。

只有 G0~G3 全通过，才可以说“工程文档与 V3 100% 对齐”。单纯把 V3 关键词复制到 Issue 标题中，不算对齐。

---

# 10. 建议的执行顺序

```text
立即冻结新 M1/M2 派单
  ↓
G0：v3.0.1 解决规范冲突
  ↓
M0-023：唯一权威/模块/里程碑/追踪矩阵
  ↓
M0-007、014、015、021、022 重写
+ M0-024~030 新契约
  ↓
迁移现有 R2 reference schema 与 fixtures
  ↓
M1-001/010/012/014 重写
+ M1-017~020 数据/检索/规模脊柱
  ↓
M2-005/006/009/012 重写
+ M2-016~023 运行时脊柱
  ↓
M3-001 重写 + M3-012~015
  ↓
TEST V0.2 + M4-005/006
  ↓
再恢复常规 M1/M2/M3 并行开发
```

不能采用的顺序是：“先把 R2 任务都写完，到 M4/M7 看测试再说”。到那时对象枚举、Task schema、索引、Session、队列和 API 已经全被旧语义占据。

---

# 11. 最后的不留情面结论

现有文档体系最大的优点，是 R2 已经把许多 Agent 项目最容易忽略的地基——版本、证据、不确定性、任务、回执、隐藏真值、公平基线——写得比普通项目严谨得多。

最大的失败，是 **V3 在一天后成为“唯一正式基线”，但下游四份工程文档没有做一次正式 requirements re-baseline**。于是出现了一种危险假象：

- 架构图看起来有工作台、Task、搜索和 AI 世界；
- 任务书有 100 多页细粒度 Issue；
- 测试规范也有 V01~V20 和年度仿真；
- 团队因此可能误以为“V3 已经被覆盖”。

实际上：

- Cockpit 只有雏形，没有可验收的 V3 Manifest；
- Task 有状态机，没有通用可执行触发条件；
- Session 有 checkpoint，没有长对话流式心智流水线；
- Search 有 FTS/过滤，没有原生中文联合共现引擎；
- Observation 有统一写入，没有端侧多模态缩减与 retention；
- AI World 有泛化 self subject，没有 Prediction、LifeChapter 和 CommunicationExperience；
- 控制台能在 PC 调试，但穿戴 FSM 与 Ambient Canvas 没有任何软件契约；
- M4 声称 V01~V30，测试规范却只定义到 V20；V3 最新机制连场景编号都没有。

> **所以当前项目不是“差最后一点对齐”，而是“R2 地基已经具备，V3 上层尚未工程化”。**

现在最错误的动作，是继续按旧任务书高速编码；最正确的动作，是在 M0 用最小代价重开契约冻结，把 V3 的新增对象、条件调度、对话流、联合检索和验收场景真正压进 schema、Issue 和 Gate。否则越快开发，只会越快得到一个“测试能过、却不是 V3”的系统。
