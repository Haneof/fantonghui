# AIOS Core 全盘重构设计书 V2 · 认知账本架构（Epistemic Ledger Architecture）

> 作者：Independent Chief Systems Architect & Engineering Director（第二独立方案）
> 与 V1（`01d8fb7`，OS 内核化路线）关系：**互斥的世界观，可互为压力测试**；本方案主张账本优先
> 基线：`aios-2.0` @ `f210765` × 【V3宪法】× 旧规划/旧任务书/工作台/测试规范
> 日期：2026-09-16

---

## 一、独立诊断：这不是"缺政策"，而是"缺会计"

### 1.1 我的不同抓法

所有既有审查（含我的 V1）把断层描述为"宪法机制在任务书里缺承载"。再深一层：**V3 宪法描述的其实是一个信念经济系统**——置信度（货币）、证据（准备金）、晋升（发行）、衰减（通胀控制）、纠错（清算）、删除（销毁）。而旧规划把它建成了**对象 CRUD 系统**。CRUD 没有守恒律：

- 置信度可以被任何写入者凭空设为 0.9（**无准备金发行**）；
- 自省结论可自我确权（**央行给自己印钞**）；
- 纠错要逐条改写下游（**逐笔现金召回**，必然雪崩）；
- 金字塔/索引/看板各自现算（**每部门私铸货币**，口径分裂）。

> **一句话诊断：AIOS 的致命断层是"认知经济没有账本"。政策（V1 的药方） Without 账本 = 警察 Without 账册——抓得到个案，控不住总量。**

### 1.2 首崩点（账本语言重述）

- **静崩 = 信心超发（M1 第 1 月）**：introspection/inference 无发行上限地累积为高置信 claim，"信心质量"稀释；测试断言形状，无人计量总置信质量 → 慢性恶性通胀。
- **响崩 = 挤兑（M2 E2E）**：一次身份翻转使大量"存款"（Summary/Claim）同时被怀疑，若按 eager 召回=挤兑，算力瞬间破产。
- 旧规划的 M2-015 主动闭环是第一次把"银行"开门营业的日子——**开门即挤兑**。

### 1.3 总体战略：先建账本，再开银行

1. **M0.5 记账内核**：复式记账（Claim 借/Evidence 贷）、发行上限、衰减表、独立审计 daemon。
2. **一切读取=视图（View）**：金字塔/检索/看板都是带水位的物化视图，口径唯一来自账本（私铸即违宪，§18 正解）。
3. **纠错=清算净额化**：只记清算条目+视图标脏，读时带预算刷新（挤兑变排队）。
4. **交互=柜员窗口**：FSM=营业时间；1~3 句=柜员话术上限；高影响发言需"抵押"（evidence_refs≥1）。
5. **虚拟测试=审计与压力演练**：超发演练、挤兑演练、双花（幂等）、伪钞（注入）。
6. 兼顾策略：账本在 Linux 仿真与手环上是**同一本账**；穿戴层只是柜员窗口形态（迟绑定）。

---

## 二、架构升级：C01~C14 → 账本化重组

| 动作 | 模块 | 账本语义 | 关键边界 |
|---|---|---|---|
| 重塑 | **C02 认知账本核心** | 追加式复式总账；world_revision=账页号 | 唯一写入点；append-only |
| 新设 | **C15 发行与衰减政策** | 发行上限、per-source 速率、置信衰减表（读时计息） | 衰减在读时算，禁写时摊销（防写放大） |
| 重塑 | **C01 边缘铸币** | 原始件=金条；语义化=铸币；检疫金库 TTL；声纹墓碑=销户留底 | 铸币必须带 content_hash 准备金凭证 |
| 重塑 | **C06 视图服务** | co_occur/5D/manifest 均为物化视图+水位 | 交互路径禁碰总账 raw |
| 重塑 | **C07 清算所** | 纠错=净额清算条目+视图标脏；超级节点 breaker | 禁逐笔级联 |
| 升级 | **C09 柜员调度** | ready-list/timer-wheel；模态分桶；single-flight | O(ready) |
| 拆分 | **C10 → 产品柜员窗口 + C17 开发者控制台** | 柜员只读视图+话术上限 | 面板/回放非产品 UI |
| 新设 | **C16 穿戴交互契约** | 营业时间 FSM；骨传导电源=闸门 | sim 先行 |
| 新设 | **C18 审计 daemon** | 只读全账+否决门；不变量监视 | 与被审系统零共享写路径 |

```mermaid
flowchart TD
  RAW[多模态原始件] -->|检疫金库 72h| C01[C01 边缘铸币]
  C01 -->|mint(provenance,hash)| J[(C02 复式总账<br/>append-only·账页=world_revision)]
  J --> V1V[视图: 金字塔 rollup]
  J --> V2V[视图: posting/alias/tombstone]
  J --> V3V[视图: cockpit manifest]
  C15[C15 发行与衰减] -->|cap/decay 规则| J
  C07[C07 清算所] -->|netting+标脏| J
  C09[C09 柜员调度] -->|ready-only| C10[C10 柜员窗口]
  C10 -->|话术需抵押| C13[C13 模型接入]
  C13 -->|新认知=新发行| J
  C18[C18 审计 daemon] -.只读+否决.-> J & V1V & V2V & V3V
  C16[C16 营业 FSM] --> C10
```

---

## 三、任务拆分蓝图（M0→M8，账本里程碑）

### 3.1 里程碑调整

- **M0**：保持并关闭 5+1 签核（契约=账本字段类型，资产保护）。
- **M0.5 记账内核**（新，6 Issue）：M1 前置。
- **M1a 铸币与身份**：modality 铸币契约、墓碑销户留底、重识别。
- **M1b 视图与规模门**：视图服务 + 360万探针进 CI（性能首测不前移=渎职）。
- **M2 柜员与主动闭环**；**M2.5 流水线与 SLO**（新）；**M3 清算所+挤兑混沌门**；**M4 审计绑定验收**（V21~V30 三版本+风格门）；M5~M8 入口读探针基线。

### 3.2 新增 Issue 清单

| 编号 | 名称 | 交付 |
|---|---|---|
| M0.5-001 | 复式记账 journal 与平衡校验（LB-01） | Claim 借/Evidence 贷、txn 平衡触发器 |
| M0.5-002 | 发行上限与读时衰减（LB-02） | introspection 未担保发行≤活跃置信质量 20%；per-source 速率；衰减读时计 |
| M0.5-003 | 审计 daemon 与否决门（LB-05） | 只读、独立进程、gate CI |
| M0.5-004 | 水位与视图物化协议 | 视图=可重建派生；watermark_rev；私铸检测 |
| M0.5-005 | 检疫金库与销户留底 | raw TTL、tombstone 24 月、回归重识别 |
| M1b-001 | 视图服务 co_occur/5D（LB-03 读侧） | posting 交集+rollup 纪律 |
| M2-009r | 柜员 manifest（LB-04） | 四步序段序+12K+话术抵押 |
| M3-001 | 清算净额化与挤兑混沌（LB-03） | netting+标脏+日预算刷新+breaker |

### 3.3 重写/废黜

| 旧项 | 处置 | 账本理由 |
|---|---|---|
| M0-008/009 Claim/EvidenceSet | **升级**为 journal 双条目 | 单条目无平衡律 |
| M1-012/M1-010 | 重写为视图服务 | 私铸口径 |
| M2-009 | 重写 LB-04 | 柜员无预算无抵押 |
| 工作台十三步序 | 降为审计清单 | 启动序=开柜四查 |
| §18 禁冗余字面义 | 修宪 | 视图=合法派生，准备金单一 |
| 测试 V0.1 | 升 V1.0 审计演练 | 见四 |

### 3.4 代码级规约（4 项）

#### LB-01 · 复式 journal（SQL DDL + Pydantic）

```sql
CREATE TABLE journal(
  txn_id TEXT NOT NULL, entry_seq INT NOT NULL,
  side TEXT CHECK(side IN ('claim','evidence')),
  object_id TEXT NOT NULL, object_rev INT NOT NULL,
  provenance TEXT CHECK(provenance IN
    ('observation','external','inference','introspection')),
  confidence_delta REAL NOT NULL,      -- claim 侧为正(发行), evidence 侧为准备金凭证
  envelope_hash TEXT,                   -- 铸币准备金凭证
  epoch INT NOT NULL,
  PRIMARY KEY(txn_id, entry_seq));
CREATE INDEX journal_obj ON journal(object_id, object_rev);
-- 平衡触发器：每个 txn 的 claim 发行量 ≤ Σ evidence 权重 × provenance_factor
```

```python
class JournalTxn(BaseModel):
    txn_id: str
    claims: list[ClaimEntry]      # 发行侧
    evidence: list[EvidenceEntry] # 准备金侧，含 provenance_factor:
    # observation=1.0 external=0.9 inference=0.5 introspection=0.2
    def balanced(self) -> bool:
        issued = sum(c.confidence_delta for c in self.claims)
        backed = sum(e.weight*e.provenance_factor for e in self.evidence)
        return issued <= backed          # 禁超发
```

**验收**：任意 txn 不平衡即拒写（protocol INVALID_ARGUMENT）；E-B12 七例转绿（ref 先验=开户 KYC）。**禁止**：无 evidence 的 fact 发行；写时改历史账页。

#### LB-02 · 发行上限与读时衰减

```text
mint(c, policy):
  mass_introspection += c.conf if c.provenance=='introspection'
  if mass_introspection > 0.20 * active_confidence_mass(): raise IssuanceCap
  if rate_limit(c.envelope.speaker_ref): raise RateLimit
  journal.append(balanced_txn)
effective_confidence(claim, now):      # 读时计息，禁写时摊销
  return claim.conf * decay(provenance, now - claim.learned_at)
```

**验收**：introspection 风暴 fixture：fact 质量占比不升（超发演练 PASS）；衰减单调。**禁止**：读路径豁免衰减；上限参数进模型 prompt（必须代码强制）。

#### LB-03 · 清算净额化（防挤兑）

```text
settle(correction):                     # 老张翻转
  net = clearing_entry(correction)      # 一笔净额，不触碰下游
  mark_views_dirty(root, BFS depth<=3, visited/SCC, breaker degree>500)
view_read(v):
  if dirty(v):
     if budget_today(): refresh(v)      # 排队刷新，日预算 50 视图
     else: return stale(v, banner)      # 挤兑变排队，照付+告示
```

**验收**：200 依赖 hub 翻转：当日刷新≤50、交互 p99 无尖峰、循环图无无限 wake。**禁止**：eager 级联写；交互内联刷新。

#### LB-04 · 柜员 manifest 与话术抵押

```python
class TellerManifest(BaseModel):
    seg_order: Literal["mirror","bonds","stance","world"]  # 开柜四查硬序
    tokens_total: int = Field(le=12000); assembled_ms: int = Field(le=150)
class UtteranceRule(BaseModel):
    max_sentences: int = 3
    high_impact_requires_collateral: bool = True   # evidence_refs>=1 方可断言
```

**验收**：首 token 前 LLM 往返=1；无抵押高影响断言 fixture 必 fail；冷战亲密语气 fail。**禁止**：串行调用先于首字；话术上限可配置放开。

---

## 四、工作台与测试：柜员窗口 + 审计演练

### 4.1 柜员窗口（C10/C16）

| FSM | 进入 | 退出 | 电源 |
|---|---|---|---|
| CLOSED(IDLE) | 默认 | — | 骨断 |
| BELL(微震/强震) | 事件 | 5~10s | 断 |
| OPEN(BONE_ON) | 窗内触摸 | 会话毕 | ≤200ms 上电 |
| SILENCE_HOLD | 会议/驾驶/深夜 | 情境退出 | 断 |

L1 画布=柜员话术区：≤3 句+rollup 卡片；L2 技能=共用一本账的代办窗口（AppManifest 投影）。

### 4.2 测试规范 V1.0 = 审计与压力演练

1. **超发演练**：introspection 风暴 30 天 → fact 质量占比 Δ≤0；
2. **挤兑演练**：hub 翻转+全视图请求 → p99 无尖峰、日刷新≤预算；
3. **双花演练**：换 attempt 幂等重放 → 一成一拒；
4. **伪钞演练**：投毒对话/恶意 OCR → 无 collateral 不进 fact；
5. **V21~V30 三版本** + **风格门**（≤3 句计量、反说教/谄媚探针、分寸三态）；
6. **红线**：旧 V01~V20 全绿而审计演练红 = 阻断合入（防机械 Chatbot 化即防"银行变成自动售货机"）。

---

## 五、终判（V2 vs V1）

V1 用 OS 内核回答"政策放哪"，V2 用复式账本回答"凭什么相信"。**V2 的不可替代贡献是总量控制**：发行上限与读时衰减直接计量并遏制信心通胀——这是 V1 与全部并行模型都没给出的守恒律。建议：**M0.5 同时冻结"内核管道（V1）+ 记账平衡（V2）"双视角为同一组件的两面**（管道是流程，账本是记录），审计 daemon 独立建制。如此 v3.0 方能从"方向对护栏缺"进入"可冻结施工、可审计运营"。

— Independent Chief Systems Architect, 2026-09-16
