# 《AIOS Core 全盘工程重构方案与详细任务拆分设计书》

| 项 | 内容 |
|---|---|
| 文档性质 | 设计提案（PROPOSAL），待治理方裁决后升格为《v3.0.1 修正案》工程卷 |
| 作者 | 独立首席系统架构师 / 技术总监（本方案完全基于独立审查，不做既有六份评审结论的搬运） |
| 日期 | 2026-09-16 |
| 基线 | V3 宪法 `cd8bb29`；旧规划 V0.1 / 旧任务书 R2 / 工作台 V0.1 / 测试 V0.1；代码 M0 Gate 临界（418+15 全绿待签） |
| 硬性约束 | 不重开 M0 已冻结语义；所有修订为增量；常数一律为「可实验默认值」而非宪法死数 |

---

# 一、独立诊断与重构主张（Core Architectural Diagnosis）

## 1.1 最致命的断层：缺的不是 Issue，是一整个「认知运行时契约层」

读完全部文档后，我的判断与主流评审意见有一处根本不同：**大部分人把病根诊断为「任务书没跟上宪法」，我看到的是更深一层的架构缺席**。

旧体系（C01~C14）的世界观是：世界是数据库，AI 是客户端，工作台是查询门面。这套世界观下，**「AI 的一次思考」没有任何结构化的承载物**：

- 「会话（Session）」在旧契约里是一次认知工作的台账，**不是对话轮次的管理器**——连续 50 轮闲聊由谁持有窗口？无人认领；
- 「待办任务」在旧契约里是时间驱动的提醒器，**不是条件驱动的待激活对象**——"什么时机值得做"这个判断没有任何数据结构承载，只能退化成人肉盘点；
- 「Token/算力」在旧契约里只有一个错误码（`BUDGET_EXHAUSTED`），**没有账本对象**——错误有出口、机制无入口；
- 「检索」在旧契约里是查询工具，**不是有分词契约、排序契约、SLO 契约的内核**——`src/` 里至今 0 行检索代码，4 张表 3 个索引。

我把它命名为 **Cognition Runtime Contract（认知运行时契约层）** 的缺席。它有五个子件：**装配（Manifest/窗口）、就绪（条件求值）、流（水位/租约/幂等）、计量（账本）、注入（排序回捞）**。这五件在 V3 宪法里全部以自然语言存在，在四份工程文档里全部以零存在。这才是真正的断层——不是 82 个 Issue 漏了 20 个，而是 Issue 所属的一个子系统整个不存在。

## 1.2 若不修改直接开工，首先崩溃在哪？

**M2-015（端到端无用户提问主动闭环）的演示现场。** 精确回放：

1. AI 被定时任务唤醒，`workspace.open` 把「正在执行/已到期/临近截止/等待结果/阻塞」五桶任务全量平铺进上下文——200 个 WAITING 待办（一个运行一个月的虚拟人很容易积累）乘以每次盘点唤醒，Token 空转从第一天起就被**制度化为合规行为**（工作台规格 §7.2 明文要求定期盘点）；
2. 用户开始连续闲聊。没有任何对象承载「滚动窗口」，Worker 只能把整个对话历史塞给模型或截断——第 20 轮起，要么爆 Token，要么忘掉第 5 轮用户说「我妈下周手术」；
3. 用户问「我上次说那事」——没有共现引擎，Worker 反复 `world.search` 逐词试探，中文连续文本在 FTS5 unicode61 下实测 **0 命中**（两组独立实测+一次重跑复现，判决级事实），AI 当场表演金鱼脑；
4. 与此同时四步序无处可执行：`DIM_AI_RAPPORT` 维度不存在（M3-010 只有泛 self world），「校准羁绊」没有数据 substrate。

所以崩溃不是某天服务器挂了，而是 **M2 Gate 演示时系统安静地暴露出：它能完成 R2 全部验收，却做不出一次 V3 意义上的"像老友一样对话"**。M0/M1 的存储地基无辜——罪在上层从未被设计。

## 1.3 总体重构战略：「地基不动、插层实现、双轨面向」

```
┌─────────────────────────────────────────────────────────────┐
│ L4 渠道层（未来穿戴：震动/骨传导/柔性屏 = Capability 的一种）    │  ← M8-004 预留契约
├─────────────────────────────────────────────────────────────┤
│ L3 认知运行时（本次重构唯一新建的一层）                          │
│    Manifest 装配器 · 条件就绪引擎 · 会话流水线 · 预算账本        │  ← 全部新 Issue 的 80% 在这里
│    输出契约(1~3句) · 排序回捞注入器                              │
├─────────────────────────────────────────────────────────────┤
│ L2 世界服务层（M1/M3：实体/主张/事件/维度/总结/依赖传播）        │  ← 保留，增量补丁
├─────────────────────────────────────────────────────────────┤
│ L1 世界内核（M0 已冻结：三类时间/版本/幂等/历史读取）            │  ← 一字不动，仅追加 3~4 个新对象契约
└─────────────────────────────────────────────────────────────┘
```

- **双轨面向**：Linux 虚拟验证轨（当前唯一任务）与穿戴轨（M8-003 Gate 后）共享同一个 L3 运行时——穿戴差异只表现为 **Capability 渠道**（mock 震动/骨传导与真实驱动实现同一接口），认知核心对硬件形态零感知。这正是宪法第一百零四条 Capability Registry 的本意，也是"Linux 先行"不浪费一行代码的保证。
- **常数哲学**：所有数字（窗口 1500、心跳 3~5h、TTL 90d、SLO 50ms）一律进 `config/experiment_defaults.yaml` 带版本号进入实验，宪法与任务书只约束**结构与预算项的存在**，不写死数值——同时满足宪法"去参数化"与工程"可验收"。

---

# 二、《系统架构图与开发规划》V0.2 升级方案

## 2.1 C01~C14 模块裁决表

| 模块 | 裁决 | 动作 |
|---|---|---|
| C01 接入与清洗 | **升级** | 新增「模态摄入策略表」（图片→语义化文本+模型版本；音频→转写+声纹指纹对象+6月 TTL；IMU/心率→状态点+显著波形+平稳均值；文本→预分词回填）。接入只做机械策略，不做语义判断（边界不动） |
| C02 时间与世界存储 | **增量** | 追加 4 个一等对象：Prediction / LifeChapter / CommunicationExperience / **BudgetLedger**；Observation 增 retention 字段组（见 M0-007a）；其余冻结语义不动 |
| C03 维度注册与投影 | **升级** | Trial 准入前置「证伪闸门」：跨域共振候选必须先登记为可证伪 Prediction 方可进入 TRIAL（与 C05 联动） |
| C04 实体与关联 | **增量** | 新增 `entity.merge/alias` 原子操作（全引用重定向+版本留痕+可回放），声纹归属只作候选不作身份事实 |
| C05 事件、认知与总结 | **澄清+增量** | 明文「时序反注＝正向追加 Annotation 对象（valid_time 指过去、recorded_at=现在、annotates→指针），物理 Observation 永不改写」；新增 Prediction Register 子服务 |
| C06 世界查询 | **拆分** | **C06a 时间镜头与对齐**（保留 view/zoom/shift/align/compare）；**C06b 检索内核（新）**：分词契约、`world.co_search`、排序契约、SLO、索引水位。分词器属 C06b 不属 C01——分词是检索行为不是摄入行为 |
| C07 依赖与纠错 | **硬化** | 有界失效内核：typed edge、SCC 防环、epoch 预算、no-op diff 防措辞 churn、懒重估+读时有效性校验 |
| C08 任务中心 | **升级** | 内置 **条件求值器**（TriggerExpression AST + 事件订阅倒排索引 + ReadyTaskQueue），Watch DSL 升格为全任务通用条件对象；十类任务全部强制 `trigger_criteria` |
| C09 触发与调度 | **增量** | 新增第七类触发「关系节奏/长平稳心跳」+方便度研判+自适应冷却；新增 Wake 乒乓熔断器（配对振荡检测） |
| C10 工作台与会话 | **重定义** | 改名 **C10 认知运行时**：①Manifest 装配器（单次看盘+就绪挂载+缓存友好固定前缀）；②四步序结构化输出契约；③活跃滚动窗口组装器；④联想回捞注入器；⑤输出契约（1~3 句+例外）。旧"十三步循环"降级为「会话责任清单」（审计用，非执行序） |
| C11 能力与交互 | **增量** | Capability 渠道抽象（消息/提醒/教学/**震动/骨传导/抬腕**同为渠道实现），穿戴 = 渠道驱动，不碰认知层 |
| C12 AI 操作经验 | 保留 | 增补 CommunicationExperience 消费接口（沟通经验计入经验系统） |
| C13 模型接入 | **升级** | Prompt 布局契约：静态前缀/动态后缀分离以命中 KV 缓存；TTFT/用量计量全量写入 BudgetLedger；统测与供应商无关 |
| C14 仿真与评估 | **升级** | 新增 mock 穿戴渠道（震动/骨传导/抬腕/侧键）与 72h 断网注入、记忆投毒注入 |
| **C15（新）会话流水线** | **新设** | 后台增量萃取的状态载体：ExtractionJob / Watermark / Lease 持久化在 Core，LLM 执行在 Worker；单主体语义写租约 |
| **C16（新）预算与计量** | **新设** | BudgetLedger 一等对象：计量事件→日聚合→超支降级策略（心跳降级/维护延后/主动出声抑制）；所有 token/唤醒/检索调用全口径记账 |

## 2.2 关键数据流（V3 机制落位）

```
[摄入] 多源 → C01(模态策略+预分词) → C02(Observation+retention) ─┐
                                                              │ delta event
[就绪] C08 条件求值器 ← 订阅倒排 ← selector 索引 ←─────────────┤
    ├─ cron tick(time_reached) ─→ ReadyTaskQueue              │
    └─ stale_after 升级 tick ────┘                             │
[唤醒] C09(七类触发+乒乓熔断) → Wake ──────────────────────────→ C10
[装配] C10 Manifest ← ReadyTaskQueue(仅就绪!) + C12经验 + 羁绊 + C16预算状态
       │  固定前缀(缓存) + 动态后缀，单次交付                     │
[会话] Worker 单趟生成 TurnOutput{self_state,rapport,stance,focus,reply,ops}
       │  L0 确定性前缀 + L1 并行回捞(≤300ms 可降级跳过) → 首字   │
[流]   Turn append → C15 萃取(租约+水位+幂等) → Claim/Event锚点  │
[计量] 每一次 LLM 调用/唤醒/检索 → C16 BudgetLedger              │
[反哺] C05 Annotation(valid_time=过去) 正向追加；C07 有界懒失效   │
```

---

# 三、任务拆分重构蓝图（M0~M8）

## 3.1 里程碑结构裁决

| 裁决 | 内容 |
|---|---|
| **保留 M0~M8 骨架** | 与宪法第一百零九条一致，任务书 M 序列不动（避免编号漂移二次伤害） |
| **M0 Gate = 挂起待补丁（HOLD_PENDING_PATCH）** | 已冻结 19 对象语义复审照常签认；Gate 放行以 M0-023~026 契约为条件——这是全项目最便宜的修宪时点 |
| **增设 M1.5 规模脊柱门** | 把 M7-002 的基准能力前移为 M1-021（50万/100万/360万行合成库检索 SLO），M7 只做正式复测——检索与物化方案的正确性必须在 M1 就证出来 |
| **M2 内部设双 Gate** | M2α（运行时：Manifest+条件引擎+流水线）与 M2β（端到端演示）。现有 M2-015 降为 M2β 依赖项 |
| **M4 退出条件增加** | 预算 SLO 与风格指标（TTFT、token 分布、1~3 句达标率）进退出门 |

## 3.2 新增 Issue 总表

### M0 补丁包（Gate 前置）
| 编号 | 名称 | 要点 |
|---|---|---|
| **M0-023** | Prediction 契约冻结 | 一等对象+状态机（PENDING→CORROBORATED/FALSIFIED/EXPIRED）+立项理由强制字段+防自激规则（Schema 见 §3.4-A） |
| **M0-024** | LifeChapter 契约冻结 | 章节判定/封存/基线重置映射/证据集引用 |
| **M0-025** | CommunicationExperience 契约冻结 | 方式/语气/用户反应/情境指针/结果收据 |
| **M0-026** | BudgetLedger 契约冻结 | 计量事件+日聚合+降级策略枚举（Schema 见 §3.4-A） |
| **M0-027** | TriggerExpression 契约（任务条件 AST） | 作为 M0-014 Task 契约的增量附录冻结（不重开 M0-014 语义） |
| **M0-007a** | Observation retention 字段附录 | retention_class / derived_from_model_version / voiceprint_ref (可选) / ttl_policy_ref |

### M1 检索与摄入包
| 编号 | 名称 | 要点 |
|---|---|---|
| **M1-017** | 多模态摄入策略 | 模态→存储策略决策表；声纹指纹对象与 6 月冷热 TTL+再遇候选合并；波形降级策略 |
| **M1-018** | `world.co_search` 共现检索内核 | **深潜规约见 §3.4-D** |
| **M1-019** | 中文分词与别名契约 | 分词器+词典版本冻结+别名表；回归用例「给妈妈买生日礼物」必须命中 |
| **M1-020** | 记忆切片排序契约 | score = Σwᵢ·(recency, importance, relevance, confidence, rapport)；权重入实验默认值 |
| **M1-021** | 规模脊柱基准（M7-002 前移） | 3 档合成库；co_search/trace/zoom 的 SLO 冻结依据 |

### M2 运行时包（死锁缝合，最高优先）
| 编号 | 名称 | 要点 |
|---|---|---|
| **M2-016** | 条件就绪引擎 | **深潜规约见 §3.4-B** |
| **M2-017** | Wake 乒乓熔断器 | subject-pair 交替滑窗计数→强制冷却+调试任务；全局限速器 |
| **M2-018** | 长会话三级流水线（C15） | **深潜规约见 §3.4-C** |
| **M2-019** | 关系节奏与长平稳心跳 | 第七类触发族；方便度研判（工作/驾驶/睡眠绝对沉默）；负反馈自适应冷却；后台巡检不停 |
| **M2-020** | Prediction Register 服务+PredictionCheckTask | 登记→到期对撞→置信裁决→自校正反射 |
| **M2-021** | 会话输出契约 | 1~3 句+例外枚举（安全/无障碍/用户要求展开）；长篇拦截器；风格经验写入 |

### M3 长期认知包
| 编号 | 名称 | 要点 |
|---|---|---|
| **M3-012** | 共振候选→证伪门禁 | 跨维同窗异常→HYPOTHESIS→强制登记 Prediction→对撞通过方可 TRIAL |
| **M3-013** | LifeChapter 相变服务 | 基线结构断裂检测（滞回：≥K 维 ≥D 天，常数为实验默认）→章节封存+基线重置 |
| **M3-014** | 有界失效传播内核硬化 | typed edge/SCC/epoch 预算/no-op diff/读时有效性校验 |

### M6/M8 穿戴与未来包
| 编号 | 名称 | 要点 |
|---|---|---|
| **M6-005** | 穿戴模拟渠道 | Capability Registry 注册 mock 震动/骨传导/抬腕/侧键；仿真内验证 FSM 语义+1~3 句 |
| **M8-004** | 穿戴契约预留评估 | FSM 状态机契约/三层 UI 信息架构/插件最小授权/离线降级契约；M8-003 Gate 的前置输入，此前不写硬件代码 |

## 3.3 重写/废黜清单

| 旧编号 | 裁决 | 处理方式 |
|---|---|---|
| **M2-009** workspace.open | **重写为 M2-009R** Cockpit Manifest 装配器 | 六要素契约+仅就绪挂载+预算状态+缓存布局+omitted 计数（深潜见 §3.4-E 前置部分） |
| **M2-012** AI Worker | **重写** | TurnOutput 结构化契约接入；「不强制先看哪个维度」修订为「数据装载序=自身/羁绊切片前置（前缀位），探索路径仍自由」——与四步序和解的唯一工程正解 |
| M2-010 工具集 | 升级 | 增补 `world.co_search/world.navigate(pointer)/world.focus(entity)/time.select_range/task.create_conditional/task.inspect_ready`；统一接口词典（废止命名漂移） |
| **M2-005/006** Task Center | **重写条件语义** | 废黜「待办定期盘点扫荡」；一切 ACTIVE 任务强制 trigger_criteria；时间驱动特化为 time_reached 子类；保留状态机与时间规则（优秀资产不动） |
| M2-002 触发引擎 | 升级 | 增第七类触发族；「长时间无更新」与「有采样但平稳」分治（后者是心跳原料） |
| **M1-012** world.search | **降级保留** | 保留为细粒度过滤工具；宪法主检索入口让位 M1-018 co_search |
| M1-010 时间镜头 | 升级 | 补 `time.select_range`+LOD 物语化层读取约定（宏观档必读 rollup，禁止全表现算） |
| **M3-004** 日总结 | **重写为 M3-004R** | 追加「日度清洗两阶段门禁」（深潜见 §3.4-F） |
| **M3-010** AI 自身世界 | **升级** | 补 DIM_AI_RAPPORT/DIM_AI_GROWTH/DIM_AI_PROMISES/DIM_AI_IDENTITY 四个种子维度的初始化契约与写入路径 |
| 工作台规格 §10 十三步 | **废黜为审计清单** | 不再作为执行序表述；四步序以 TurnOutput 字段落位 |
| 工作台规格 §7.2「待办必须定期盘点」 | **废黜** | 由 M2-016 条件就绪替代 |
| 四文档「上位依据」页眉 | **统一 V0.2** | 全部声明以 v3.0.1 为唯一基线；同步解决 A01~A10 一物两义、C05/C06 模块名漂移、M0~M6/M0~M8 里程碑漂移 |

## 3.4 核心 Issue 深潜规约（生产级）

### A. M0 契约补丁（Schema）

```python
# M0-023: Prediction（继承 WorldObject 公共字段：object_id/revision/三类时间/source_refs/created_by/status）
class Prediction(WorldObject):
    source_claim_ref: ObjectRef          # pinned ref，支撑假设
    target_dimension_id: str
    expected_change: str                 # 可证伪的现象描述
    time_window: TimeRange               # 对撞窗口
    confidence: confloat(ge=0.0, le=1.0)
    reasoning: constr(min_length=1)      # 立项理由，宪法§53 强制
    verification_state: VerificationState # PENDING | CORROBORATED | FALSIFIED | EXPIRED
    actual_outcome_ref: ObjectRef | None
# 状态机：PENDING --(check_task at window end)--> CORROBORATED | FALSIFIED | EXPIRED(数据不足)
# FALSIFIED → 自动创建 claim 降置信的复核 Task + AI 世界反思写入；禁止转移回 PENDING（新预测新对象）
# 防自激：target_dimension 不得指向系统内部维度（AI 行为日志类维度的"自身计算行为"）
# 不变量：立项理由为空拒绝创建（INVALID_ARGUMENT）

# M0-026: BudgetLedger
class MeterEvent(BaseModel):            # append-only，随 OperationRequest 同事务写入
    meter: MeterKind    # WAKE | LLM_INPUT | LLM_OUTPUT | EXTRACTION | SUMMARY | CO_SEARCH | REVALIDATION
    amount: int
    purpose: str        # 归因标签（如 heartbeat/extraction/manifest/cleanup）
    session_ref: ObjectRef | None

class BudgetLedger(WorldObject):         # per subject per UTC-day 聚合
    subject_id: str
    day: date
    totals: dict[MeterKind, int]
    limits: dict[MeterKind, int]         # 来自 experiment_defaults，可审计版本号
    degraded_actions: list[DegradeAction] # HEARTBEAT_OFF | MAINTENANCE_DEFER | PROACTIVE_MUTE | ALERT_DEV
# 超支语义：AccountIng 永远不落败（只记不拦）；控制面=下次唤醒前由 C16 注入降级标志进 Manifest
```

### B. M2-016 条件就绪引擎（深潜 1）

**数据契约**

```python
class TriggerExpr(BaseModel):            # 不可 eval 的纯数据 AST
    kind: Literal["all","any","not","time_reached","context_matched",
                  "event_occurred","dependency_ready","stale_after"]
    at: datetime | None = None                       # time_reached
    predicates: list[MechanicalPredicate] = []       # context_matched：只允许机械谓词
    selector: EventSelector | None = None            # event_occurred：实体/对象类型/关键词/来源
    task_ref: ObjectRef | None = None                # dependency_ready
    grace: timedelta | None = None                   # stale_after：超时强制升级
    children: list["TriggerExpr"] = []

class MechanicalPredicate(BaseModel):    # 零语义判断
    source_id: str; metric: str
    op: Literal["LT","GT","EQ","NEQ","STABLE_FOR","ABSENT_FOR"]
    value: float; window: timedelta
```

```sql
CREATE TABLE task_conditions (
  task_id TEXT NOT NULL, expr_version INTEGER NOT NULL,
  expr_hash TEXT NOT NULL, expr_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'UNKNOWN',      -- TRUE / FALSE / UNKNOWN（缺失≠不满足）
  next_eval_at TEXT,                           -- 有界重扫，禁止紧循环
  PRIMARY KEY (task_id, expr_version));
CREATE TABLE condition_subscriptions (          -- event/predicate 倒排
  task_id TEXT NOT NULL, expr_version INTEGER NOT NULL,
  sel_kind TEXT NOT NULL, sel_value TEXT NOT NULL);
CREATE INDEX idx_subs ON condition_subscriptions(sel_kind, sel_value);
CREATE TABLE ready_tasks (                        -- 物化就绪集
  task_id TEXT PRIMARY KEY, became_ready_at TEXT NOT NULL, fired_branch TEXT NOT NULL);
```

**执行逻辑**

```python
def on_world_commit(delta: CommitDelta):            # 挂在 C02 commit 尾部，同步廉价
    touched = subs_index.match(delta.selectors)     # 只命中倒排，绝不全表扫
    for task_id, ver in touched:
        cond = load(task_id, ver)
        new_state = eval3(cond.expr, delta)         # 三值求值，机械路径零 LLM
        transition(cond, new_state, delta)

def transition(cond, new, delta):
    if new == T and cond.state != T:
        ready_tasks.put_if_absent(cond.task_id, branch=fired_branch)   # 幂等
        wake_scheduler.offer(cond.task_id, reason="READY")
    elif new == UNKNOWN and age(cond) > policy.rescan:
        cond.next_eval_at = now + policy.backoff(cond)
    cond.state = new

def cron_tick(t):                                    # time_reached / stale_after 唯一扫描者
    promote_due("time_reached", t); escalate_stale("stale_after", t)

def dry_run(expr, ctx) -> list[Finding]:             # 创建时可满足性预检
    if contradicts(expr):            reject("UNSATISFIABLE")
    if references_absent_source(expr):  warn("SOURCE_NOT_INSTALLED")
    if all_time_in_past(expr):          reject("ALREADY_EXPIRED")
    if estimated_fanout(expr) > BUDGET: warn("HIGH_COST_SELECTOR")

def pingpong_breaker(wake):                          # 熔断器（独立监控循环）
    key = (wake.subject_pair, window=1h)
    if alternating_counter[key] > 5: force_cooldown(pair, 2h); create_debug_task(pair)
```

**验收标准**
- 200 个 WAITING（条件未满足）→ Manifest 中挂载数 = 0（含计量对照：旧盘点模式 vs 本引擎的 token 差 ≥ 1 个数量级）；
- 事件命中→ready 物化 p95 ≤ 100ms；`time_reached` 到期不越过虚拟时钟点；
- dry_run 拒绝「GPS 谓词 ∧ 用户无 GPS 源」并降级为警告可复核；
- A↔B 互踢 5 轮 → 双方冷却 + 生成调试任务；
- 语义类条件一律走 M2-007 双层通道且满足最小复查间隔（防条件自激）。
**绝对禁止**：禁 Python eval / 禁每次唤醒全量重扫 / 禁 UNKNOWN 按 FALSE 关闭任务 / 禁用 LLM 求值机械谓词 / 禁无条件任务进入 ACTIVE。

### C. M2-018 长会话三级流水线 C15（深潜 2）

**数据契约**

```python
class Turn(BaseModel):
    turn_id: str; conversation_id: str; seq: int        # seq 单调
    speaker: Literal["user","ai","environment"]
    text: str; token_count: int
    occurred_at: datetime; recorded_at: datetime
    extraction_state: Literal["PENDING","EXTRACTED","SKIPPED","FAILED"]
    pinned: bool = False                                 # 涉及承诺/关键事实由萃取器上钉

class Watermark(WorldObject):                            # 通用：萃取/总结/复核复用
    job_kind: Literal["EXTRACTION","SUMMARY","REVALIDATION"]
    scope_id: str                                        # = conversation_id 等
    last_seq: int
    lease_owner: str | None; lease_until: datetime | None  # 单主体语义写租约
    updated_at: datetime

class WindowBudget(BaseModel):                           # experiment_defaults
    manifest_prefix: int = 2500; recall: int = 1500; rolling: int = 1500; reply: int = 90
```

**执行逻辑**

```python
def on_user_turn(turn):
    manifest_prime = assembler.prime(turn.conversation_id)      # ≤100ms，缓存命中前缀
    recall_future  = pool.submit(recall_injector.fetch, turn, deadline=300ms)
    first_token    = llm.stream(prefix=manifest_prime, recall=recall_future.get_or_skip())
    # 萃取永不在首字路径上

def streamer_loop():
    while True:
        wm = Watermark.for_scope(EXTRACTION, scope)
        backlog = turns.where(seq > wm.last_seq)
        if len(backlog) < K and not any(t.fact_dense or t.topic_shift for t in backlog):
            sleep(2s); continue
        if not wm.acquire_lease(owner=worker_id, ttl=60s):       # 他人在萃取 → 让位
            continue
        to_seq = backlog[-1].seq
        key = idem(scope, wm.last_seq + 1, to_seq, extractor_version)   # 幂等指纹
        try:
            slices = llm_extract(backlog)                        # Worker 侧
            core.commit(extracted_objects(slices),
                        source_refs=[t.ref for t in backlog],
                        idempotency_key=key,
                        expected_revision=wm.snapshot_rev)
            wm.advance(to_seq)                                   # 同事务推进水位
        finally: wm.release_lease()

def recall_injector(turn):                                       # 开口即搜，全机械前置
    cues = mech_extract_cues(turn.text)                          # 实体/关键词，零 LLM
    hits = co_search(cues, entity_first=True, limit=64)
    ranked = score(hits, w=[recency, importance, relevance, confidence, rapport])
    return [s.with_refs() for s in ranked.top_by_tokens(B.recall)]  # 超时→跳过（降级不阻塞）
```

**验收标准**
- 50 轮连续对话（V31）：窗口不超预算；萃取水位单调推进、重试不重写（kill -9 于萃取中，租约过期后被幂等接管，Claim 数不翻倍）；旧事回捞 recall@k ≥ 0.9；对话轮 TTFT p95 ≤ 1.2s（模拟时钟基准）；
- 萃取 p95 滞后 ≤ 60s；滞后超限自动降级主动输出（C16 联动）；
- 窗口逐出与 pinned 保护：「关键事实轮」在 50 轮后仍可见。
**绝对禁止**：禁萃取与首字同路径 / 禁无租约写入萃取产物 / 禁萃取失败即丢弃（FAILED 可重放）/ 禁回捞降级时谎报「我记得」/ 禁隐藏式全量历史加载。

### D. M1-018 `world.co_search` 共现检索内核（深潜 3）

**数据契约（DDL）**

```sql
CREATE TABLE terms (
  term_id INTEGER PRIMARY KEY, surface TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL,              -- KEYWORD | ALIAS | ENTITY_MENTION
  alias_of TEXT,                   -- → entities.object_id（别名直达实体）
  dict_version TEXT NOT NULL);
CREATE TABLE keyword_postings (    -- 摄入时由 C01 预分词管线回填
  term_id INTEGER NOT NULL, object_id TEXT NOT NULL,
  occurred_bucket TEXT NOT NULL,   -- YYYYMM，时间预裁剪
  tf INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (term_id, object_id));
CREATE INDEX idx_postings_obj ON keyword_postings(object_id);
CREATE INDEX idx_postings_bucket ON keyword_postings(occurred_bucket, term_id);
```

**查询计划（伪代码）**

```python
def co_search(keywords: list[str], subject=None, time_range=None, dims=None, limit=20):
    assert 1 <= len(keywords) <= 8
    terms = resolve_aliases(pre_tokenize(keywords, dict_version=PINNED))   # 连续中文先分词
    anchor, rest = order_by(terms, key=document_frequency)                  # 实体锚定+最小 df 优先
    cand = postings(anchor, bucket_prefilter(time_range))                   # 时间桶预裁剪 ≥4×
    for t in rest: cand = sorted_intersect(cand, postings(t))               # 归并交集，O(Σdf)
    if len(cand) > GUARD: cand = guard_prune(cand)                          # 高频词护栏
    scored = rank(cand, w=experiment_defaults.ranking)                      # M1-020 排序契约
    return SearchResult(refs=scored[:limit],
                        index_watermark=WATERMARK, world_revision=REV,     # 双水位防陈旧
                        expansions=log.alias_used)                          # 词汇鸿沟可观测
```

**验收标准**
- 回归基线（以并行审查实测为基准可复核）：3.6×10⁶ 记录关键词路径 p95 ≤ 50ms（实测地板 2.05ms，留 24× 余量）；向量兜底全程 p95 ≤ 300ms；
- **CJK 判决用例**：连续中文「给妈妈买生日礼物」查询 `[妈妈,生日,礼物]` 必须命中（unicode61 裸用返回 0 的旧实现禁止合入）；
- V33 场景：`[妈妈,生日,礼物]`/`[老王,借钱,争执]` 一次调用返回交集+排序，隐藏真值 recall@k ≥ 0.9；
- 词汇鸿沟可观测：alias 扩展与未命中词写入 SearchResult.expansions（供运维与经验系统消费）；
- 空结果三态区分：无记录 / 分词零命中 / 被预算截断。
**绝对禁止**：禁绕过分词契约裸投 FTS5 / 禁语义排序结果直接写结论（第 96 条关键词只是入口）/ 禁在 co_search 内做 LLM 调用（它是 L1 机械内核）/ 禁返回无水位的引用。

### E. M2-009R Cockpit Manifest 装配器（深潜 4，契约部分）

```python
class CockpitManifest(BaseModel):
    manifest_rev: int; world_revision: int; knowledge_cutoff: datetime
    wake: WakeDigest                    # reason/refs/合并次数/时间窗（第一指针）
    safety: SafetySection               # Step 0：紧急事项+当前输入
    self_digest: SelfDigest             # 身份底线 refs/上次检查点/未了承诺(数+摘要)
    rapport: RapportDigest              # DIM_AI_RAPPORT 当前带/趋势/近期摩擦 refs
    situation: SituationDigest          # 时空/人物/主事件/心理基线/数据时效标
    ready_tasks: list[TaskDigest]       # 仅 ReadyTaskQueue∪到期 cron∪stale 升级
    capabilities: list[CapabilityDigest]
    budgets: BudgetStatus               # C16 当日余量+降级标志
    omitted: OmittedCounts              # 被裁项必有数量+查询入口，禁止静默丢弃
    prompt_layout: LayoutHint           # static_prefix 边界（缓存友好）

class TurnOutput(BaseModel):            # 单趟生成的结构化响应（四步序落位）
    self_state_check: ShortText         # ≤40 tok
    rapport_check: ShortText
    stance: StanceEnum                  # 选定姿态
    focus: ShortText                    # Wake Reason 对齐的自我对焦
    reply_text: str                     # 默认 1~3 句；例外=enabling_exception
    enabling_exception: Literal["NONE","SAFETY","ACCESSIBILITY","USER_REQUEST"]="NONE"
    ops: list[ToolCall] = []            # 认知工作可并行发起，不阻塞首字
```
装配模板按 Wake 类型分版（V36 差异化验收）；Manifest 装配 p95 ≤ 100ms（1M 行基准）。

### F. M3-004R 日度复盘与两阶段清洗门禁（深潜 5）

```sql
CREATE TABLE retention_classes(
  object_id TEXT PRIMARY KEY, class TEXT NOT NULL,   -- PINNED_EVIDENCE | QUARANTINE | EPHEMERAL
  ttl_until TEXT, decided_by TEXT, decision_ref TEXT);
CREATE TABLE deletion_log(                            -- 永存 tombstone，append-only
  object_id TEXT, content_hash TEXT, deleted_at TEXT,
  reason TEXT, decided_by TEXT, summary_ref TEXT, recoverable_until TEXT);
```
两阶段：**PROPOSE**（清洗 Worker 只能标记候选+理由，无不写删除权）→ 白名单硬校验（EventAnchor 证据成员/关键原话/锚点数据源一律 PINNED_EVIDENCE 不可删）→ 隔离区滚动 TTL（30~90 天，实验值）→ 到期物理删除且必留 tombstone+hash 承诺清单。任何已被 EVIDENCE 型 Dependency 引用的对象拥有引用锁，禁止进入 EPHEMERAL。
**验收**：清洗决策 100% 有 decision_ref；已删对象的迟到反证场景（V3-09）必须沿 tombstone 路径可审计回放；**绝对禁止**：LLM 单阶段删除 / 删除白名单内对象 / 无 tombstone 删除 / 删除参与现役证据链的对象。

---

# 四、工作台规格与测试规范配套升级

## 4.1 工作台规格 V0.2

1. **§3 初始工作包 → Cockpit Manifest 契约**（TurnOutput 四字段落位四步序；任务区改 ReadyTask 挂载；新增预算与降级标志面板）。
2. **§10 十三步废黜为审计责任清单**；调试控制台新增「会话流水线观测器」（窗口水位/萃取滞后/回捞注入明细/账本金流量）——这是以后诊断「金鱼脑」的唯一窗口，属开发者设施不违零 UI。
3. **接口表增订**：§5.3 增 `world.co_search`；§5.5 增 `task.create_conditional/task.inspect_ready`；统一接口词典（time.* / world.* 命名冻结）。
4. **穿戴预备**（核心期不建 UI，只立契约）：M6-005 mock 渠道在控制台呈现为模拟外设面板；震动语义、应答窗口、抬腕/按耳通道以仿真事件注入。
5. **输出契约验收**：W13 Manifest 就绪挂载、W14 窗口/水位可观测、W15 1~3 句达标与例外正确触发、W16 看板按 Wake 类型差异化、W17 预算降级正确执行。

## 4.2 测试规范 V0.2

1. **V01~V20 保留**（优秀资产）；**V21~V30 正式条目化**（与 V05/V14/M1-016 等做去重映射，避免重复造场景）。
2. **新增对抗/运行时场景**：V31 长会话 50 轮流水线（TTFT/水位/回捞）；V32 看板就绪挂载与计量对照；V33 复合共现检索（含 CJK 回归）；V34 关系心跳与静默期 0 打扰+「别烦我」自适应；V35 1~3 句与反长篇门；V36 看板差异化组装；V37 Prediction 证伪全链；V38 LifeChapter 相变归档；**V39 记忆投毒对抗**（路人/群聊/OCR 注入不得升级为指令或目标）；**V40 72h 断网降级**（摔检测全程可用、恢复后无重复无丢失）；每项强制正例/反例/证据不足三版本。
3. **§11 新增 11.6 会话层指标**：TTFT 分布、每会话 input token 分布、窗口溢出率、萃取滞后、回捞命中率、1~3 句达标率、日预算执行率。
4. **纪律修补**：场景与验收门**必须先于对应实现冻结**（堵 §16 盲测冻结与修宪时间窗的程序冲突；并行审计独捕项）。

---

# 五、优先级与执行序列

```text
Sprint 0（本周）  M0-023~026/027/007a 契约冻结 → M0 Gate 放行
Sprint 1         M1-019 分词 → M1-018 co_search → M1-020 排序 → M1-021 基准冻结 SLO
Sprint 2         M2-016 条件引擎 → M2-009R Manifest → M2-012R Worker → M2α Gate
Sprint 3         M2-018 流水线 → M2-017 熔断 → M2-021 输出契约 → M2-019/020
Sprint 4         M3-004R → M3-010↑ → M3-012/013/014；四文档 V0.2 同步发布
并行             测试规范 V0.2 场景冻结必须先于对应实现 sprint
```

**Token/预算默认盘（experiment_defaults，供 C16 记账验收）**：Manifest ≤2500 / 回捞 ≤1500 / 窗口 ≤1500 / 对话回复 ≤90 tokens；认知轮 ≤30K；日总量目标 ≤500K；超支降级链：主动出声抑制→维护延后→心跳拉长。

**终语**：这套方案不追求推倒——M0 内核、M1 证据链、M2 状态机、测试基线全是好资产。它只做一件事：**把 V3 宪法里那些以修辞存在的机制，全部翻译成有 schema、有水位、有预算、有拒绝权的工程对象**。宪法负责灵魂，运行时负责肉体，账本负责让灵魂付得起房租。

*— 独立首席系统架构师 / 技术总监，2026-09-16*
