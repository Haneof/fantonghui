# 00-09 与宪法 V1.4-r0 的一致性索引（条款级作废/待修订清单）

- 生成：2026-09-11（V1.4-r0 批准生效当日）｜ 依据：V1.4 §4.4、§11、§12
- 为什么需要这份文件：00-09 是 **V1.2 体系**写的 WHAT/HOW 说明书，V1.4 换了主范式（Observation → Trigger → AI Interpretation）。
  宪法 §12.1 要求旧文件"保留、不删除、不改写为历史事实"，本仓红线又禁止"另起平行文档集"——
  所以既不能改它们，也不能让人照旧措辞写新代码。唯一合规解法就是这份**索引**：指到哪一节作废，谁取代它。
- 用法：动 00-09 任何一节之前先查本表。标 **VOID** 的节不得作为实现依据；标 **KEEP** 的照用；标 **REVISE** 的等 v0.2 修订。

| 文档 | 节 | V1.4 判定 | 取代者 / 说明 |
|---|---|---|---|
| `01_CORE_ARCHITECTURE` | §2 总体结构、§3 核心对象（以 Event 为中心） | **REVISE** | V1.4 §1.2 的底层主对象是**唯一 Global Timeline**，Event 降级为"AI 的解释结果"（§11 表第 4 行）。核心对象须补：Observation / Dimension Point / Trigger / Inference Event / Summary Node / Task / Outcome / AI Self Update |
| `01` | §3 World / State / Memory / Cognition / Growth 的对象定义 | KEEP | §12.3 明确这些基础可保留；语义仍成立 |
| `02_RUNTIME_CONTRACTS` | §0 Perception Runtime（"输出标准 Semantic Event"） | **VOID** | V1.4 §11 第 1 行改判：底层先输出 **Observation**。perceptiond 现有语义补全属兼容层（见 `code/services/README_V1.4_BOUNDARY.md`） |
| `02` | §1 Event Runtime | **REVISE** | 只作为兼容适配层存在（§12.2）；新代码不得以其为唯一底层输入 |
| `02` | §2 World / §3 State Runtime | KEEP+重标 | 保留；在 V1.4 中是"Global Timeline 的事实槽位投影"，且曲线值永不写事实槽位（NEXT_TASK 旧红线仍有效） |
| `02` | §6 Relevance Runtime | **VOID** | 独立的相关性运行时取消：§4.1「Trigger 不负责决定是否有意义，意义由 AI 判断」。`gate_rules.py` 内核并入 attentiond 的机械阈值，不再是"Relevance 评分" |
| `02` | §7 Attention Runtime + §8 Lease Runtime | **VOID（并列关系作废）** | §11 第 9 行：V1.3「Trigger/AI 判断/Lease 三者分离」并列提法**即刻废止**。四件机械事见 §4.3；算力预算只是配额，不设语义评审 |
| `02` | §9 Wake Runtime | **VOID** | 由 §4.2 **六类 Trigger** 取代；`NO_WAKE/MICRO/AI/EMERGENCY` 四级命名作废，其中 EMERGENCY 的语义并入第 6 类 Safety Trigger（硬规则、豁免学习） |
| `02` | §10 AI / §11 Capability / §12 Interaction Runtime | KEEP+重标 | Capability 须过 Permission + Audit（§10）；Interaction 补 §9.2 语义枚举（只定契约、不实现） |
| `03_WORLD_EVENT_SCHEMA` | Event / Entity / World State / World Change | KEEP（在用） | 主线三件套 `aios/01_os/schemas/{event,world_state,world_change}.json` 是本文逐字节副本，测试锁定（S1 验收） |
| `03` | Canonical schema set / naming rule | **REVISE** | 须新增 Observation、DimensionPoint、TriggerRecord、InferenceEvent、SummaryNode 五份；`raw_ref` 唯一引用规则**继续有效**（Observation Store 就是 raw 的归宿） |
| `03` | Memory / Relationship / Cognition / Growth / Decision | KEEP+重标 | Memory 须长出 Event Anchor + Keyword Inverted Index（§8.2、§6）；Cognition 的 epistemic 五状态已合 §5.5，保留 |
| `04_WAKE_RUNTIME` | §2 流水线 Level 1 Semanticization（低层做语义化） | **VOID** | §4.4 第 1、2 条冻结：底层不做语义分类、本地小模型不做语义判断 |
| `04` | §3 Level 4 Relevance / Level 5 Attention 分层 | **VOID** | 同 §6/§7/§8 判定，漏斗分层收敛为「机械触发 → AI」两段 |
| `04` | §1 直接答案（"不能让大模型逐条过滤"） | KEEP | 这是 V1.4 仍然成立的核心动机，只是实现手段换成阈值触发 |
| `04` | §5 Active Watch | **REVISE** | 升级为 §4.2-3 Inactivity Trigger（个性化安静/陪伴窗口）+ §5.8 定时任务自治；仍是主线缺口（旧验收 F 未完成，现由 P0 清单接管） |
| `05_AI_RUNTIME` | §2 AI Wake Session 10 步 | **REVISE** | 须并入 §5.9「AI 介入标准顺序」——先看自己记忆树/Attitude 再看曲线，顺序不可乱；并补 §5.4 完整产出、§5.3 `summary_node_id` 增量总结 |
| `05` | §4 十类结构化输出 | **REVISE** | 改判为 §5.2 Inference Event（带真实度与知识状态，§5.5）；10 类枚举待 v0.2 重列 |
| `06_REPOSITORY_LAYOUT` | 仓库布局要求（`aios-core/core/{...}`） | **VOID** | STATUS 冲突 1 已裁「`aios/01_os` 为唯一实现主线」，V1.4 §12.4 进一步禁止 `core/` 与主线并存；根目录 `core/` 簇已归档 `archive/legacy_core_simulator/` |
| `06` | "文档规范位置 / 规范文件与仓库路径规则" | KEEP | 文档集中放 `docs/`、代码放 `aios/01_os/code/` 的规矩不变 |
| `07_DEVELOPMENT_PLAN` | Phase 0-10 推进顺序 | KEEP | 「先底层闭环、UI/App/Hardware 靠后」与 §12.5 一致 |
| `07` | Phase 1/3 各阶段内容 | **REVISE** | 内容须换成 Observation → Trigger → AI Interpretation → Memory/Curve；Phase 3 的 Relevance/Attention/Wake 三段并成 Trigger 一段 |
| `08_ACCEPTANCE_TESTS` | A-J 十项 | KEEP+扩充 | 骨架仍有效。B 的「AI 调用 ≤1%」口径须换：V1.4 漏斗为 30 万信号→几万语义事件→几百 World Change→几十候选→几个真唤醒（PM 裁决 5）；须新增 5 项：曲线方向触发、关键词召回后上下文筛选、Unknown ID 重投影不改原始观测、定时自治闹钟本、安全底线不被 Regret 放宽 |
| `09_FIRST_SPRINT_TASKS` | Sprint 1 Task 1-9 | KEEP（历史验收） | Task 5 已验收并吸收主线（`test_s1_t5.py`）；不重做 Task 4 的红线继续有效 |
| `09` | Sprint 2 及以后划分 | **VOID** | 被 V1.4 的 P0 缺口清单取代，见根目录 `NEXT_TASK.md` |
| `09` | Sprint 1 禁止事项 1-7 | 部分 KEEP | "禁止在低层调用大模型/网络"仍有效且更严（本地模型零语义）；其机械执行器 `forbidden_scan.py` 已随 `core/` 簇归档，V1.4 下须重指向新宪法后重建 |
| `AIOS_PROJECT_MASTER_PROMPT_V1.0` | 全文 | KEEP | 角色、权限、任务格式、验收纪律与 V1.4 无冲突 |

## 冻结与修订的边界（避免误会）

- 本索引**没有**修改 00-09 任何一个字：它们保持原样，等指挥官批准 v0.2 修订时一次性改。
- "VOID" 的含义是"不得再作为实现依据"，不是"文档作废"——它仍是理解既有代码（M0-M3.5 为什么长这样）的说明书。
- 下一步若做 v0.2：按 PM 治理裁决 6「升级现有 00-09 并入新机制，**禁止另起平行文档集**」，在本目录下原地升版，不新建编号文档。
