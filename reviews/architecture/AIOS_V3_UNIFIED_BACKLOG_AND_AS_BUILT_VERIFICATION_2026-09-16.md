# AIOS V3 统一整改母表与 as-built 复核（Gate 0 交付物 / 第 4 份 Gap Audit 仲裁版）

| 项 | 内容 |
|---|---|
| 文档角色 | **不是第 5 份独立 Gap Audit**。本报告是元裁决 `AIOS_V3_MULTI_REVIEW_META_AUDIT_NO_GO_2026-09-16.md` §6.1 第 5 项与 §7.3 强制要求的交付物：「以 D 为底稿合并 E/F：先做语义去重和同号异义消解，再冻结唯一的 `M0-023~` backlog」「必须生成一份去重母表，保留来源映射」 |
| 审查人 | AIOS 核心系统总架构师 / 工程审计长（第 4 轮横向对齐审查） |
| 日期 | 2026-09-16 |
| 分支 / 基线 | `arena/01a0a631-fantonghui`；文档基线 commit `cc66e13`（含 `493a3e0` 元裁决） |
| 比对对象 | 【V3宪法】`AIOS核心系统宪法v3.0.md`(1720 行)、【架构规划】`AIOS Core 系统架构图与开发规划.md`(326 行)、【总工任务书】`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`(4262 行)、【工作台规格】`AIOS认知工作台功能规格.md`(403 行)、【测试规范】`AIOS虚拟世界测试规范.md`(480 行)；合计 7,191 行全文逐条比对 |
| 代码复核 | `schemas/r2/m0_contract_snapshot.json`（`gate_version=M0-R2`、16 枚举、30 模型哈希、ObjectType 19 类、ErrorCode 11 项）、`src/aios_core/contracts/{models,enums}.py`、`src/aios_core/storage/sqlite_store.py`、`src/aios_core/dependency/graph.py` |
| 实测依据 | 仅引用**已入库且 SHA256 可校验**的两套探针：本审计 `aios_v3_as_built_probe`（as-built 冻结 schema，1M revision / 2,211,817 边）与报告 A `aios_v3_sqlite_probe`（自建优化 schema，3.6M 对象）。未入库数字一律列入 §5.3「不可引用表」 |
| 裁决 | **PATCH_REQUIRED / AS-WRITTEN NO-GO**（服从元裁决）。**Gate 0 未过：停止新的 M1/M2 派单**；允许只做 v3.0.1 修正案、契约扩展、迁移 fixture 与测试夹具 |
| 与既有档案关系 | 收敛于 D(41 gap)/E(30 gap)/F(25 gap)/元裁决(H-01~H-21)；本报告的增量是 **①编号仲裁定稿 ②去重母表 ③as-built 实测验收值 ④五张可直接派单的 12 要素 Issue 卡片 ⑤两条新发现（悬空验收引用 TASK:L3377、测试规模单位与第三十三条冲突）** |

---

## 0. 明确判词

### 0.1 对核心问题的直接回答

> **不能。** 完全按现有【架构规划】【总工任务书】【工作台规格】【测试规范】编码，团队会交付一个**扎实的 R2 时代 AIOS Core**（追加式版本、三类时间、Claim/EvidenceSet/Dependency、实体消歧、十类任务、六类触发、工作台与工具循环、纠错传播、多尺度总结、五基线双赛道评测），但**不能实现 V3 宪法新增的运行时机制**：Single-Shot Cockpit 与四步序、条件驱动任务、长会话三级流式流水线、多关键词共现引擎、5D 滑动条的预聚合读法、端侧多模态轻量化与声纹生命周期、穿戴 FSM 与三层 UI、Prediction/LifeChapter/CommunicationExperience 三个一等对象、V21~V30 与 R3/V3 验收家族。

根因不是实现走偏，而是**图纸从未升级**，且这条根因有字面证据：

| 证据 | 原文 | 后果 |
|---|---|---|
| 【架构规划】L5 | `**依据**：《AIOS核心系统宪法v2.0》` | C01~C14 责任表、M0~M6 阶段、A01~A10 验收全部停留在 v2.0 |
| 【总工任务书】L6 | `**上位依据**：AIOS 宪法 2.0、R1、R2、《…架构规划》《…工作台规格》《…测试规范》` | v3.0 与 R3 **不在派单依据链内** |
| 【总工任务书】L4240–4257 | 派单链写作 `AIOS宪法2.0 + R1 + R2 + 三份开发规格 + 本任务书 → GitHub Issues → 代码 → 自动测试` | **v3.0 完全不出现在从宪法到 Issue 的授权链上**；按此链派单，任何 v3.0 条款都没有 owner |
| 【工作台规格】L4 | `**依赖**：第一份规格的数据、时间、任务和版本约定` | 继承【架构规划】的 v2.0 语义 |
| 【测试规范】L1–5 | 无 v3.0/R3 兼容声明 | V21~V30、R3-01~07、V3-01~03 成为**孤儿验收**（无场景、无指标、无 Gate） |

### 0.2 卡死点分层判定（与 D §0.2 / 元裁决 §7.4 同构，本表补 as-built 与契约证据）

| 视角 | 首个卡死里程碑 | 判词 | 本报告补充的硬证据 |
|---|---|---|---|
| 治理与契约审计 | **M0（M0-V3 扩展门）** | 必须立即停止冻结。`schemas/r2/m0_contract_snapshot.json` 的 `gate_version` 仍为 **`M0-R2`**，ObjectType **19 类**、models **30 个**，其中无 `prediction` / `life_chapter` / `communication_experience`；`TaskType` 10 项无 `PREDICTION_CHECK`（`enums.py:97-107`）；`WakeSource` 8 项无心跳/关系节奏（`enums.py:125-133`）；`Observation.modality` 是**无枚举约束的自由字符串**（`models.py:31`）；`Task.completion_condition/cancel_condition/recurrence` 是**无类型 `dict[str,Any]`**（`models.py:332-339`）。`TASK_PROGRESS_R2.md` 记录 **M0-022 处于 BLOCKED** | 结论：v3.0 的 10 项机制中 **8 项在冻结契约里没有任何载体**，因此不是"补一个服务"能解决的，必须走第一百一十五条第 3 款的正式架构变更 |
| **物理可交付性** | **M1（M1-012）** | **第一个做不出宪法指标的 Issue**。M1-012（TASK:L1736-1782）指定"第一版 SQLite FTS5 + Entity alias index"，验收是"搜索'妈妈'返回实体候选+文本命中"与"'妈妈+生日+礼物+近3年'**逐步过滤**" | as-built 实测：冻结 schema 上三词共现 **1,282.8~1,357.9 ms/次**（P3），`occurred_at` 时间窗 **1,201.4~1,468.6 ms/次且与窗口无关**（P4），而第八十九条(L1213-1226)要求"毫秒级"、第九十条要求"秒级因果召回" ⇒ **差 2~3 个数量级**；且 FTS5 默认 `unicode61` 对连续中文 **0 命中**、`trigram` 对 2 字词 **0 命中且不报错**（P5）⇒ 该 Issue 的验收测试会**静默零召回而绿灯通过** |
| **验收可判定性** | **M4（M4-002 / M4-004）** | **第一个验收不可判定的 Issue**。TASK:L3377 的验收标准写 `V01~V30覆盖`，但【测试规范】§10 场景矩阵（L236-259）**只定义到 V20** | V21~V30 的定义只存在于【V3宪法】L1604-1619，从未下传到测试规范 ⇒ M4-002/M4-004 的验收条件引用了**不存在的测试资产**，属悬空引用（dangling acceptance reference），M4 Gate 无法签收 |
| 用户可观察运行 | **M2** | 第一个必然的运行断崖（与 D/元裁决一致）：M2-009/010/012 建出的是"工作包 + 自由工具循环"，而第八十四条要求单次看板 + 四步序、第八十六条要求条件就绪过滤、第八十五条要求三级流式流水线 | as-built 实测：看板**组装本身**只需 **0.3 ms**（P2b，85 行 payload 四步序），证明 M2 的瓶颈不在存储而在**内容选择与预算**；同时单条提交 fsync `FULL` **0.47 ms/次**（P1b）⇒ 830 观测/日若逐条提交，真实闪存上是 1.7~12.5 s/日纯 fsync，必须 group commit |
| 债务放大 | **M3** | 不是补救点。缺失的一等对象、条件 AST、会话水位此时已侵入存储/API/队列/测试；M3 现有 11 个 Issue 无 Prediction 闭环、无 LifeChapter、无 CommunicationExperience、无有界传播内核 | as-built 实测：M0 现状传播（`dependency/graph.py::collect_impacted_dependents` 要求全量入内存）单次枢纽修正 **9.3 s / 51,822 受影响对象 ≈ 15.55 M token 复核**（P7），而预算化有界遍历只需 **10.82 ms**（500 节点/深度 2）⇒ 差距 **860 倍**，越晚补越贵 |

### 0.3 本轮新增判词：**当前状态下"派单"这个动作本身已不可执行**

元裁决 §7.3 已预警「绝不让审计本身制造第四套任务语义」，§5.3 第 12 项已驳回「把 D/E/F 的 Issue 编号原样叠加」。核对三份审计的增补建议后，冲突不是零星而是系统性的：

- **同一个 `M0-023`**：D = `V3 Authority & Traceability Freeze`；E = `Prediction 契约冻结`；F = `Prediction 契约冻结`（D 把 Prediction 放在 `M0-024`）。
- **同一个 `M2-016`**：D = `Active Conversation Working Set`；E = `条件编译引擎 TriggerExpression`；F = `条件就绪判定引擎`。
- **同一个 `M1-019`**：D = `Retention & Tombstone Worker`；E = `回溯加注服务`；F = `中文分词与别名检索契约`。
- **同一个 `V31`**：D = `Single-Shot Cockpit`；E = `时钟倒挂`（脏数据族）；F = `长会话流水线`。
- **`V` 前缀被 5 套语义占用**：测试规范 V01~V20（场景）、宪法 L1604-1619 V21~V30（场景）、宪法 L1692-1698 V3-01~V3-03（验收）、D V31~V45（场景）、E V31~V36 与 F V31~V37（场景，内容互不相同）。
- **`A01~A10` 一物两义**：宪法第一百一十四条(L1633-1642) 与【架构规划】§12(L313-324) 同号异义，而 M2-015 裸引 A07/A08/A09（元裁决 H-18 已判定为治理级高价值发现）。

**判词**：在 §3 的编号仲裁定稿并冻结唯一 backlog 之前，任何"按 D/E/F 增补 Issue"的执行动作都会产生**同号异义的第四套语义**，使 Gate 0 的第 8 项（`CONFLICT/UNMAPPED = 0`）永久无法达成。本报告 §3~§4 即为该仲裁与母表的定稿建议，供 v3.0.1 修正案直接采纳。

---

## 1. 前提校正（审计人义务：先纠正命题本身的四处不准确）

元裁决 §5.3 已驳回「10 项机制工程覆盖率全部为零」等绝对判词。核对原文后，本次任务描述中有四处命题需要校正——**校正不改变结论方向，但改变整改动作**：

| # | 命题 | 文档实况（含行号） | 裁定与整改含义 |
|---|---|---|---|
| 1 | "V21~V30 = 老王身份反转、长对话因果穿透、静默心跳抑制" | 宪法 L1610-1619 的 V21~V30 实为：V21 高频传感器无异常、V22 愿望/预测被当事实语气、V23 多维区间共同支持候选事件、V24 迟到数据改变区间认知、V25 数学/英语/编程形成学习能力、V26 新维度无长期收益、V27 长期目标产生多次任务、V28 推断目标被否认、V29 候选事件被否定、V30 一个月跨尺度下钻。"老王"只是 L1219 的共现检索示例 `[老王, 借钱, 争执]`；"身份纠正"是【测试规范】V04；"因果穿透"是 L1197 的下钻；"静默/抑制"是 L1050 与第八十二条 | **命题不准确，但结论更严重**：测试规范确实缺 V21~V30，而且 TASK:L3377 已经引用 `V01~V30` ⇒ 悬空验收（见 §0.2）。整改动作是"逐条下传宪法原文 10 条 + 为每条建正例/近似反例/证据不足三版本"，不是新编三个场景 |
| 2 | "测试规范仍停留在基础的 1天/1月/1年模拟" | 测试规范有：四层真值隔离(§2)、五基线 B0/B1/B2/A/O(§8)、机制隔离与自主调度双赛道(§9)、V01~V20 场景矩阵(§10)、五组指标(§11)、动态维度与经验的分叉对照(§12)、7 项消融(§13)、盲测纪律(§14)、三层评分(§15)、初始验收门(§16)、失败归因表(§17)、LongMemEval/LoCoMo 外部基准(§18) | **命题不成立**（元裁决驳回 #3 同旨）。测试规范的**评测方法论是全仓最成熟的部分**，应保留；缺的是 v3.0 场景家族（V21~V30/R3/V3）、会话层与检索层指标（TTFT/窗口溢出/萃取延迟/recall@k/co_search p95）、以及把 §16 的门与 v3.0 条款挂钩 |
| 3 | "M1-010~M1-013 只支持单关键词/全文匹配" | M1-012(L1736-1782) 的 B 段明写目标是"用户希望'生日→妈妈→礼物→过去几年'的全球关联"，G 段测试明写"'妈妈+生日+礼物+近3年'逐步过滤"；M1-013 有 `evidence.trace` 的 DAG 递归与深度/节点限制 | **命题不准确**：不是"只有单搜"，而是**范式不同**——任务书是"串行窄化 + 分阶段扩大召回"（WB:L152 同），宪法第八十九条 L1218-1220 是"**严禁把复合意图割裂为多次低效的单词检索**…直接计算多关键词在实体、事件与 Claim 节点上的**交集与共振密集区**"。整改动作是**新增原子 `world.co_search` 并保留 search/follow_links 作为降级路径**（元裁决 §5.2 已如此改写；驳回 E 的"逐步过滤必然等于多轮模型往返"判词，见元裁决 L209） |
| 4 | "工作台规格把所有界面都当成 PC 桌面浏览器端" | WB §2(L20-40) 确为 PC 三栏布局；但 WB §1 明确工作台是"AI 进入世界的统一工作环境 + 开发者面板"，且宪法 L1187-1188 自己要求开发阶段提供可视化认知调试控制台 | **PC 控制台不违宪**（D §1.3-2 同旨）。真正的缺口是**没有任何面向最终用户的穿戴端交互契约**：柔性/马达/骨传导/FSM/三层UI 在四份工程文档中命中数全为 0（见 §2 审查项 6）。整改动作是新增设备无关 `InteractionPort + FSM Simulator`（元裁决 §6.4），**不是**删掉 PC 控制台 |

> 另需澄清一条常被误引的判词：**多轮工具调用本身不违宪**（元裁决驳回 #10）。第八十四条 L1075-1076 禁止的是"系统发提示词 → AI 说好的我知道了 → 再发下一段"这种**分段 onboarding**；第九十一条 L1247 与第八十六条第 3 款明确允许 AI 自主工具路径。因此 M2-012 需要**重写而非废除**。

---

## 2. 七大核心对齐项逐项裁定

主表（每项的详细证据见随后小节）：

| # | 对齐项 | 宪法条款 | 架构规划 | 总工任务书 | 工作台规格 | 测试规范 | 裁定 | 唯一 owner（本报告定稿号） |
|---|---|---|---|---|---|---|---|---|
| 1 | Single-Shot Cockpit vs 十三步循环 | L1073-1091 §84；L1148-1152 §86.1 | **冲突**：C10(L97)=「十三步循环…**不强制固定检索顺序**」 | **冲突**：M2-012(L2503)「不能退化成固定十三步脚本」「不强制先看哪个维度」；M2-010(L2437)「**禁止把固定调用顺序写进工具层**」 | **落后**：§3(L46-70) 初始工作包 11 项 = Cockpit 雏形；§10(L305-330) 十三步，且顺序为"当前世界(3)→AI自身(4)"，与四步序"照镜子(1)→羁绊(2)→姿态(3)→世界(4)"**倒置** | 无 | **三方顺序冲突（B/M2）**：看板雏形可复用，但四步序、分档 token 预算、就绪任务过滤、确定性序列化全缺 | **M2-009 重写** + M2-012 重写 + M0-029 |
| 2 | 条件驱动 vs 无脑遍历 | L1153-1160 §86.2（`time_reached`/`context_matched`/`event_occurred`/`dependency_ready`；等待任务静默休眠） | **缺失**：C08(L95)/C09(L96) 无就绪判定概念 | **冲突**：M2-005(L2178)调度只看 `next_wake/deadline/recurrence`；M2-006(L2225)「todo 必须 next review」、测试「待办无 deadline 仍会盘点」；M2-007 的 Watch DSL 是唯一局部能力 | **冲突**：§7.2(L227)「待办任务…**必须进入定期任务盘点**或相关情境唤醒」；§8(L267-280) 两层条件是 Watch 专用 | 无 | **正面冲突（B/M2）**：`time_reached/context_matched/event_occurred/dependency_ready/task.inspect_ready` 在四份文档命中数 = 0；契约层 `Task.completion_condition` 是无类型 dict ⇒ 无可编译条件、无可索引就绪队列 | **M0-027**（TriggerExpression 契约）+ **M2-024**（求值引擎与就绪队列）+ M2-005/006 重写 |
| 3 | 长会话三级流式流水线 | L1093-1147 §85（1500 token 活跃窗口 / 后台增量萃取 / 超链接按需回捞 / 首字 1 秒） | **缺失**：0 命中 | **完全缺失**：`流式/萃取/1500/活跃窗口/50轮/首字/latency` 命中 = **0 个 Issue** | **缺失**：§4 只有 `cursor/limit` 分页 | 无（§11.4 有"每会话输入输出量"，无 TTFT/窗口溢出/萃取延迟） | **结构性缺席（B/M2）**：三个子系统 0 个 Issue ⇒ 长对话能力不存在 | **M0-028**（Conversation/Turn/ExtractionSpan 契约）+ **M2-016**（前台活跃窗口）+ **M2-017**（后台增量萃取）+ **M2-018**（联想回捞注入）+ **M2-019**（TTFT 分段遥测）+ M7-005（年度正式门） |
| 4 | 多关键词共现 vs 传统单搜 | L1213-1226 §89；L1190-1205 §87（5D 滑动条）；L1234-1247 §91（`world.co_search`/`time.select_range`） | **落后**：C06(L93)=「时间镜头、全文与语义检索、筛选、聚合、比较、下钻」 | **范式冲突**：M1-012 = FTS5 + alias index + 逐步过滤；M1-010 = 粒度切换（无预聚合读法）；M1-014 已有 `index_watermark`/`STALE_INDEX`（**可复用的正确地基**） | **落后**：§5.3(L138-152) 单搜 + 分阶段扩大召回 | 无（§11.4 只有"查询次数/耗时"） | **B/M1**：无 `co_search`、无中文分词契约、无共振密度排序、无 SLO；宏观档未强制读预聚合层 | **M1-012 重写** + **M1-018**（co_search 引擎 + 中文分词/别名）+ **M1-021**（倒排与时间桶投影层）+ **M1-022**（排序契约）+ **M1-020**（规模门前移）+ M1-010/M1-014 升级 |
| 5 | 端侧边缘轻量化摄入 | L455-484 §33（IMU 特征提炼 / 心率平稳期均值 / 图像端侧语义化不存原图 / 声纹指纹绑定 + 半年冷热淘汰 / 每日大模型清洗 + 永存白名单） | **落后**：C01(L88)=「格式、单位、时间、来源、重复包…**不判断情绪、关系、人生事件**」，无模态策略 | **落后 + 冲突**：M1-001(L1219-1265) 只接 GPS/心率/IMU/文本/App，验收是「10k 条模拟心率可批量写入」；`图像/摄像头/OCR/语义化` 命中 0；`声纹` 仅 2 次伪命中(L1277 身份解析例子、L2288 Watch 测试)；M3-004 明文**不删除**（v2.0 口径）与 §33.5 冲突 | **缺失**：无模态→存储策略 | 无（§5 允许"数据块"但未要求 reduction） | **B/M1（摄入）+ B/M3（清洗）**：`Observation.modality` 是自由字符串(`models.py:31`)，无 Modality 枚举 ⇒ 分模态策略在契约层无可判定载体 | **M0-030**（SourceEnvelope/transform lineage/retention class）+ **M1-017**（模拟端侧 reduction 管线）+ **M1-019**（Retention & Tombstone Worker）+ M3-004/005 升级 |
| 6 | 穿戴 FSM 与三层 UI | L1300-1331 §98之一（5~6cm×23cm 柔性全屏、震动先导 FSM、零误触铁律）；L1367-1410 §104之一（体态→态势画布→技能插件） | **合规排除**：L24「Linux 桌面、驱动、实体手环、应用商店**不进入本阶段关键路径**」 | **零预留**：`柔性/马达/骨传导/FSM/三层UI/误触` 命中 = **0**（连 mock 通道占位都没有） | **缺失**：只有 AI / 开发者两入口，PC 三栏布局 | 无 | **M（阶段外但必须预留）**：实体硬件不是 Core Gate（元裁决 §6.4、H-17），但**软件契约与仿真端口必须现在预留**，否则 M8-003 Gate 无输入 | **M2-021**（InteractionPort + FSM Simulator）+ **M6-005**（AmbientCanvas/SkillCard 投影契约）+ M8-004（穿戴契约预留评估，M8-003 Gate 输入） |
| 7 | V21~V30 与 1~3 句验收门 | L1604-1619（V21~V30）；L1680-1690（R3-01~07）；L1692-1698（V3-01~03）；L136-152 §14之一（1~3 句法则） | **落后**：§12 A01~A10 与宪法 A01~A10 **一物两义**（H-18） | **悬空引用**：L3377 验收写 `V01~V30覆盖`；`1~3句/说教/谄媚/长篇` 命中 = 0 | **落后**：W01~W12 无输出风格、无 Manifest 就绪挂载、无流水线窗口 | **缺失**：§10 只到 V20；§16 门全是 v2.0 口径；R3/V3 家族 0 命中 | **B/M2 Gate（元裁决 §6.3 第 9 项）**：三个验收家族全是孤儿 + 一处悬空引用 ⇒ M4 Gate 不可签收 | **M4-005**（TEST V0.2 场景包 TS-021~051）+ M4-006（运行时压力与消融包）+ §3.4 验收编号仲裁 |

### 2.1 审查项 1 详证：四步序是"三方顺序冲突"，不是单方缺失

- 宪法 L1078-1085：四步序为 **照镜子(自身记忆树/上次介入状态) → 校准羁绊(`DIM_AI_RAPPORT`) → 确立姿态与视角 → 审视用户世界与触发源**，且「顺序绝不可颠倒」。
- 【工作台规格】L305-318 的十三步顺序为：1 唤醒来源 → 2 紧急程度 → **3 当前世界** → **4 AI自身状态与承诺** → 5 观察计划 → …。即"世界先于自身"，与四步序**倒置**；且十三步中**没有羁绊/姿态两步**（`羁绊/RAPPORT` 在四份工程文档命中 = 0）。
- 【总工任务书】M2-012(L2503)「不能退化成固定十三步脚本」、L2511「系统提示只规定责任/约束/工具，**不强制先看哪个维度**」；M2-010(L2437)「**禁止把固定调用顺序写进工具层**」。
- **冲突性质**：这不是"缺一个功能"，而是**三份文件对同一件事给出了互斥的强制/禁止指令**。实现者无论选边都会违反其中一份正式文件。
- **元裁决改写（H-06、§5.2）**：`Wake-first、安全/方便度-first、四步序不可同时作为绝对串行第一步` ⇒ 改为**可观察决策因子**，冻结为四个结构化审计字段（`self_state / rapport_state / stance / focus`）+ 安全 Step-0 前置，**不要求模型暴露或持久化私有思维链**。
- **本报告 as-built 增量**：
  1. 四步序的**内容顺序**有独立工程正当性——它是 KV 前缀缓存亲和性约束（静态段在前、动态段在后）。因此 Manifest 必须**确定性序列化**，并加 CI 断言 `manifest_prefix_hash`（同输入同前缀哈希），否则前缀缓存失效、TTFT 与成本双双恶化。此断言可直接写进 M0-029 的验收。
  2. 组装代价不是瓶颈：P2b 实测四步序 85 行 payload 组装 = **0.05/0.07/0.05/0.04/0.04 ms，合计 0.3 ms**；点查 0.011 ms、最近 50 条观测 0.1 ms（走 `idx_objects_type_subject`）。⇒ M2-009 的验收重点必须是**内容选择、预算与省略说明**，不是"组装性能"。

### 2.2 审查项 2 详证：条件引擎缺席 + "定期盘点"是明写的空转入口

- 四份工程文档中 `time_reached` / `context_matched` / `event_occurred` / `dependency_ready` / `task.create_conditional` / `task.inspect_ready` 命中数 = **0**（F 的扫描与本报告独立复核一致）。
- 正面冲突文本：WB:L227「待办任务…必须进入**定期任务盘点**或相关情境唤醒」；TASK M2-006:L2225（测试 L2241）「todo 必须 next review」、G 段测试「待办无 deadline 仍会盘点」。
- 契约层证据：`Task` 只有 `next_wake_at / deadline / recurrence / dependencies / completion_condition / cancel_condition`，其中后三者是 `dict[str, Any]`（`models.py:332-339`）⇒ **没有可编译条件 AST、没有订阅键、没有可索引的就绪列**，因此"10 万 WAITING / 10 READY 不做全量扫描"（元裁决 Gate 2 第 2 项）在当前契约下**不可实现也不可测**。
- 局部可复用地基：M2-007 的 Watch 两层条件（WB:L267-280：机械可算 vs 需语义判断）+ 三值结果 `MATCHED / NOT_MATCHED_WITH_SUFFICIENT_DATA / INSUFFICIENT_DATA` ⇒ 这是全仓最接近 `TriggerExpression` 的既有设计，**应提升为全任务一等条件对象**而不是另起炉灶。
- **元裁决改写（H-19、§5.2）**：允许**便宜、确定性的机械复查**；禁止**周期性 LLM 全表盘点**；只有 READY / UNKNOWN-budgeted 项进入模型上下文。⇒ 整改不是"待办永不复查"，而是"复查必须由机械求值器完成，模型只看就绪项"。

### 2.3 审查项 3 详证：三个子系统 0 个 Issue，且没有 TTFT 遥测

- 宪法 L1112（活跃窗口「最近 5~8 轮…约 1500 tokens」）、L1130（后台增量流式萃取，「绝不积压到对话结束」）、L1118-1123（按需维度召回，「直接通过超链接指针将当时那一句原话切片调入上下文」）、L1100（「穿戴端**首字响应在 1 秒左右**」）。
- 工程文档命中：`流式`=0、`萃取`=0、`1500`=0、`活跃窗口`=0、`回捞`=0、`首字`=0、`TTFT`=0；【总工任务书】全文 `token` 仅 1 次（M5-003 L3510「固定模型/预算/世界；比较查询数、token、证据覆盖、正确性」）。
- 唯一的性能基准 Issue 是 **M7-002（TASK:L3781-3827）**：「benchmark记录P50/P95写入/搜索/trace时间、DB大小、索引大小、世界revision增长、月summary成本。分冷热查询」——**排在 M7**，即 M1 检索、M2 会话、M3 纠错、M4/M5/M6 全部完工之后。且它只"记录"，**没有任何阈值门**。
- **本报告 as-built 增量（这是本轮最关键的排期结论）**：按 M7-002 的排期，团队将在**最后**才第一次测量检索延迟。而该数字今天就已可知：冻结 schema 上三词共现 **1.28~1.36 s/次**，时间窗查询 **1.20~1.47 s/次**；按实测扫描律（成本 ∝ payload 总字节，≈500 MB/s）线性外推到【测试规范】§5 的年度规模 360 万条（739 B/行 ⇒ ≈2.66 GB）约为 **5.3 s/次**（外推值，非实测）。⇒ **规模门必须前移到 M1**（本报告定稿 `M1-020`，即 D 的 `M1-020` / E 的「M7-002 前移」/ F 的 `M1-021` 三者归并），否则 M1 Gate 会在错误范式上冻结查询 schema。

### 2.4 审查项 4 详证：不是"只有单搜"，而是范式与分词器双重错位

| 层次 | 宪法要求 | 任务书现状 | as-built 实测 |
|---|---|---|---|
| 检索范式 | L1218「严禁把复合意图割裂为多次低效的单词检索」；L1220「直接计算多关键词在实体、事件与 Claim 节点上的**交集与共振密集区**」 | M1-012 = `world.search` + filters + **逐步过滤**；M2-010 测试 = 「生日→妈妈实体→历年事件→礼物→财务维度」**四跳串行** | 逐步过滤在 as-built 上每一跳都是全表扫描：**1.28~1.36 s × 跳数**；四跳串行 ≈ **5 s 级** |
| 中文分词 | L1219 示例 `[妈妈, 生日, 礼物]`、`[老王, 借钱, 争执]`（全为 2 字词） | M1-012-D「第一版 SQLite FTS5 + Entity alias index」，**全文无分词器选型**（`分词/中文/tokenizer` 命中 0） | `unicode61 MATCH '妈妈'` = **0 命中**；`trigram MATCH '女朋友'`(3字) = 2,925 命中，`MATCH '妈妈'`(2字) = **0 命中且不报错**；预分词列 `MATCH '妈妈 AND 生日 AND 礼物'` = **0.87 ms / 16 命中**；20 万短文本 unicode61+trigram 索引 = **45.9 MB** |
| 时间维 | L1190-1211 5D 滑动条（1s~10s / 1min~10min / 1h~1d / 1w~1m / 1y~10y），宏观档需秒级 | M1-010 = `world.view/zoom/shift` 粒度切换，**未强制宏观档读预聚合层** | `json_extract(occurred_at)` 滑窗 **1,201.4~1,468.6 ms 且与窗口大小无关**（1d/1w/1m/1y 命中 2,642/19,157/82,045/670,652）；预聚合时间桶后 **0.66/3.86/14.40/112.48 ms**；对照 `learned_at` 索引 **0.2 ms** |
| 索引合法性 | L1280 第九十五条要求全局世界索引；第十八条第 3 款「绝对禁止数据冗余拷贝」 | **M1-014(L1830-1876) 已给出正确立场**：「索引可全部删掉重建，不是事实来源」+ `index_watermark` + `STALE_INDEX` | 派生投影实测：倒排 482,345 postings / 构建 3.6 s；时间桶 1M 行 / 13.2 s；存储 **+29%**（704.8→906.7 MB）；结果与 LIKE 全表扫描**逐条一致**（missing=0, extra=0）⇒ 投影是可重建派生视图，不构成语义冗余拷贝 |
| 因果边界 | L1220 用词「共振密集区」易被读成因果 | C06 边界(L93)「不根据关键词命中直接确立结论」；M1-012-I「禁止全文搜索命中=事实成立」 | **工程文档此处优于宪法措辞**（元裁决 H-07 同旨）：共现只产生候选/假说，须经 Prediction + EvidenceSet + 证伪/校准 Gate |

> 结论：审查项 4 的整改**不是推翻 M1-012**，而是（a）新增原子 `world.co_search`，（b）冻结中文分词契约与词典版本，（c）把 M1-014 的"可重建投影"立场升格为宪法层"派生投影"定义（关闭本审计前一轮报告的 B3），（d）宏观档强制读预聚合层，（e）规模门前移到 M1。`world.search` 与 `follow_links` **保留**为降级路径（元裁决 §5.2）。

### 2.5 审查项 5 详证：模态策略在契约层无载体，且 M3-004 与 §33.5 正面冲突

- 契约证据：`Observation.modality: str`（`models.py:31`）——**没有 Modality 枚举**。因此"图像必须端侧语义化、不得存原图""声纹只存极小指纹""IMU 不得 50/100Hz 逐点入库"这三条在契约层**没有任何可判定的载体**，M1-001 的验收（「10k 条模拟心率可批量写入且不触发 AI」）反而**奖励**了宪法禁止的逐点写入。
- 冲突证据：宪法 L477-484 §33.5 要求每日大模型清洗并「坚决物理删除底层无用的嘈杂原话碎片」；M3-004（日总结生成）与第二十五条(L369)/第九十三条(L1257)/第一百一十六条则要求原始历史永存、严禁物理删除。⇒ **宪法内部冲突**，工程文档只实现了"永存"一侧（v2.0 口径）。
- **元裁决改写（H-03、§5.2）**：LLM 不得单独拥有不可逆删除权限；改为**分级保留 + 隔离期 + tombstone + legal hold + 人工/策略 Gate**；声纹**不是永不淘汰**，而是「人物 ID/历史关系不因模板退休而断裂；声纹只作候选证据，模板可撤回/轮换/删除并留审计 tombstone」。
- **本报告 as-built 增量（两条新发现）**：
  1. **存储账可算，且 reduction 是决定性的**：P8 实测按宪法口径（830 观测/日 + 260 派生 = 1,090 行/日）单用户一年 **397,850 行 ≈ 280 MB**（含投影 ≈ **361 MB**）。而【测试规范】§5(L92-96) 的建议规模是 1天 2,000–10,000 条 / 1月 60,000–300,000 条 / 1年 **70万–360万条**，为上述模型的 **1.8~9.2 倍**（三个尺度比例一致）。⇒ 测试规范的"条"若被实现为"一条原始采样 = 一个 Observation"，就与第三十三条第 1 款的 reduction 强制**直接冲突**；若被实现为"reduction 后的长期对象数"，则 360 万条/年意味着 9 倍于宪法口径的摄入强度，必须在测试规范里写明是哪一种。**整改动作**：TEST V0.2 必须把规模表拆成两列——`raw feed volume`（原始投喂量）与 `long-term object rows`（reduction 后落库行数），并各自给出门槛；否则 Gate 1 第 2 项（H-20：同时报告压缩比、异常窗口召回、长期行数）与测试规范会就"条"的含义永久扯皮。
  2. **摄入侧的隐藏成本是 fsync，不是容量**：P1b 实测单条提交 `synchronous=FULL` **0.47 ms/次**（2,146 commits/s）、`NORMAL` **0.09 ms/次**；容器 FS 是**下限**，真实 eMMC/UFS 通常 2~15 ms。830 观测/日若逐条提交 = **1.7~12.5 s/日**纯 fsync。⇒ M1-017 的验收必须包含"**摄入批次 = 一个 world_revision**"（与 M0-018 语义完全兼容），这一条 D/E/F 均未提出。

### 2.6 审查项 6 详证：零穿戴契约，但"零"是合规的——缺的是预留

- 【架构规划】L24 明文「Linux 桌面、驱动、实体手环、应用商店**不进入本阶段关键路径**」，与当前开发目标（Linux + 虚拟人 + 模拟数据）一致，**不构成违宪**（元裁决 H-17、§6.4）。
- 但四份工程文档中 `柔性/马达/震动/骨传导/FSM/误触/三层UI/态势画布/挂载技能` 命中数**全为 0**，连 mock 通道占位都没有 ⇒ M8-003「是否进入真实设备/真实用户原型的 Gate」**没有任何输入文档**，M6-001 的 Capability Registry 也没有震动/骨传导/抬腕/侧键通道可注册。
- **本报告增量（前一轮已提出，此处落入母表）**：骨传导可懂度必须设**里程碑门**——腕→指→耳路径有量产先例（Sgnal），公开评价为"发闷、需用力压耳、以低频为主"。因此 1~3 句法则在骨传导通道上的**可懂度**是独立风险：M2-021 的 FSM Simulator 必须能注入"分档 SNR 字表可懂度"参数，未达标前骨传导只能作为**辅助**通道，不得作为唯一私密听音路径。同时 `IGNORED`（用户主动忽略）与 `NOT_PERCEIVED`（根本没察觉震动）必须在 InteractionPort 的结果枚举里分开，否则第九十七条的接受率统计被系统性污染，并与第八十条的冷却自适应叠加成"永久沉默"。
- **元裁决驳回 #6**：不得宣称"震动先导因果链已保证零误触"；正确表述是"FSM 设计**降低**误触，零误触无证据"⇒ M2-021 的验收写"无有效 notification epoch 时听音通道开启次数 = 0"，而**不写**"零误触已证明"。

### 2.7 审查项 7 详证：三个孤儿验收家族 + 一处悬空引用 + 一套双义编号

| 缺陷 | 证据 | 后果 |
|---|---|---|
| V21~V30 未下传 | 宪法 L1604-1619 定义 10 条；【测试规范】§10(L236-259) 止于 V20 | 10 个进阶场景无 fixture、无隐藏真值、无 oracle |
| **悬空验收引用（本报告新发现）** | 【总工任务书】M4-002 验收 L3377：`V01~V30覆盖；模型失败/重试纳入日志`；M4-004(L3346-3396) 同族 | M4 Gate 的验收条件引用了**仓库内不存在的测试资产**⇒ 无法签收；且"覆盖"二字无逐条 oracle，属元裁决 Gate 2 第 9 项明令禁止的"笼统标覆盖" |
| R3-01~07 孤儿 | 宪法 L1680-1690；【测试规范】命中 0 | R3-03（预测证伪闭环）、R3-05（相变与章节归档）无载体对象（Prediction/LifeChapter 未冻结）⇒ 双重不可验收 |
| V3-01~03 孤儿 | 宪法 L1692-1698；【测试规范】命中 0 | V3-01（沟通风格进化）需 CommunicationExperience；V3-02（关系节奏触发）需心跳触发；V3-03（上下文精准组装）需 Manifest 差异化 ⇒ 三项均无 Issue |
| 1~3 句法则无验收 | 宪法 L142-146（§14之一 L136-152）；四份工程文档命中 0 | 无输出长度预算器、无例外条款（安全/无障碍/用户要求展开）、无合规率指标 |
| A01~A10 一物两义 | 宪法 L1633-1642 vs【架构规划】§12 L313-324；M2-015 裸引 A07/A08/A09 | 同号异义 ⇒ 签收二义（元裁决 H-18：旧架构编号改 `ARCH-*`） |
| §16 门未挂钩 v3.0 | 【测试规范】L391-430 的硬门/能力门/相对价值门全为 v2.0 口径 | 共现检索 p95、条件任务等待期模型调用数、1~3 句合规率、四步序字段完整率、回溯加注不改历史 revision、清洗后证据链可下钻率——**六项 v3.0 专属硬门全缺** |
| 盲测版本纪律 | 【测试规范】L393「不得看完盲测结果后修改标准」 | **正确且必须保留**；元裁决 §5.2 改写为：同一冻结 test version 不得看结果改门，**新宪法可发布新版本 + 新 hidden set 后重新盲测** ⇒ TEST V0.2 必须在新盲测前冻结（H-21） |

---

## 3. 编号仲裁（核心交付物 A）

### 3.1 仲裁规则（先定规则，再定号）

1. **以 D 为底稿**（元裁决 §6.1 第 5 项、§7.3「D 的范围、安全边界、41 项断层和 Gate 设计最完整，作为合并整改母表」）。
2. **append-only，永不重编号**：现有 `M0-001~022`、`M1-001~016`、`M2-001~015`、`M3-001~011`、`M4-001~004`、`M5-001~003`、`M6-001~004`、`M7-001~004`、`M8-001~003` 一律不动；已有 16/22 个 M0 Issue 的 FINAL_PASS 证据不因 v3.0 缺口而追溯失效（元裁决驳回 #14）。新增一律追加到该里程碑序列尾部。
3. **同号异义必须消解**，落选方改号并在母表保留来源映射（§4 的「来源」列）。
4. **前缀即命名空间**：`M*-*` = Issue；`TS-*` = 测试场景；`ACC-*` = v3.0 工程验收门；`WB-*` = 工作台验收；`ARCH-*` = 架构规划验收；`PAR-*` = 可测参数；`MOD-C*` = 模块。**禁止再用裸 `V` 前缀新增任何编号**（`V` 已被 5 套语义占用）。
5. **宪法既有编号不动**：A01~A10 / R1-01~11 / R2-01~15 / R3-01~07 / V3-01~03 / V21~V30 属宪法文本，只能由 v3.0.1 修正案处理；工程侧一律通过映射表引用（`TS-021 ≡ 宪法 V21`）。
6. **阈值不入宪法**：所有 `PAR-*` 与 `ACC-*` 中的数字都是**测试 profile 默认值**，写入 TEST V0.2 的参数登记表，宪法只要求"有量化 SLO、有退化策略、有版本化 profile"（第七十六条 + 元裁决 §5.2）。

### 3.2 Issue 同号异义消解表（定稿）

| 定稿号 | 定稿语义（唯一） | D 原号 | E 原号 | F 原号 | 仲裁说明 |
|---|---|---|---|---|---|
| **M0-023** | V3 Authority & Traceability Freeze（v3.0 hash、`MOD-C01~C14` 唯一映射、M0~M8 映射、旧 API→V3 API 兼容表、条款→module→Issue→test 矩阵） | M0-023 | §9.6 治理修补 1/3 | §3.6 文档 V0.2 | 保留 D 语义（治理冻结必须最先做）；E/F 的文档刷新动作并入本 Issue 交付物 |
| **M0-024** | Prediction / PredictionCheckTask 契约 | M0-024 | **M0-023** | **M0-023** | E/F 的 M0-023 让位；本号为唯一 Prediction 契约 Issue |
| **M0-025** | LifeChapter 契约与生命周期 | M0-025 | **M0-024** | **M0-024** | 同上 |
| **M0-026** | CommunicationExperience 契约 + AI seed 维度（含 `DIM_AI_RAPPORT`） | M0-026 | **M0-025** | **M0-025** | E/F 的 M0-025 让位；F 的 G-15（羁绊维度）并入本 Issue |
| **M0-027** | TriggerExpression 与 Task Eligibility 契约（AST、三值、版本、订阅键、expiry） | M0-027 | M2-016 的契约部分 | M2-016 的契约部分 | 契约与运行时分离：契约在 M0，求值引擎在 **M2-024** |
| **M0-028** | Conversation Stream 契约（Turn envelope/seq/speaker/finalization/ExtractionSpan/Job/Watermark/ContextSlice） | M0-028 | —（E/F 只有运行时 Issue） | — | D 独有，保留 |
| **M0-029** | CockpitManifest 契约（含四步序审计字段、预算、水位、省略说明、`manifest_prefix_hash`） | M0-029 | M2-009 重写的契约部分 | M2-009 重写的契约部分 | 契约在 M0，组装器在 **M2-009（重写）** |
| **M0-030** | SourceEnvelope / transform lineage / retention class / **Modality 枚举** / `source_quality` 计算口径 / `min_granularity` | M0-030 | M0-007 升级 + M1-017 契约部分 | M1-017 契约部分 | 合并 E 的 M0-007 升级；修复 `models.py:31` 的 `modality: str` 无枚举问题 |
| **M0-031** | 双时态写/读不变量与回溯标注契约（`valid_from/valid_to/known_from/known_to/invalidated_by/supersedes/annotates` + 禁止 UPDATE/DELETE 历史的架构测试 + 默认当前读与显式 as-of 读） | Gate 1 不变量（未单列号） | **M0-005 升级** | G-17 | **新号**：元裁决 H-04/H-05 要求"M0-V3 契约前置"，必须有独立 Issue 才能进 Gate 0 清单 |
| **M0-032** | 派生投影合法化与 schema 扩展（关键词倒排表、别名/同义词表、时间桶 rollup、`Tombstone` 表、预算账本表）+ 宪法层"派生投影"定义 | 分散在 M1-018/M1-019 | **M0-017 升级** | G-06/G-07 的存储侧 | **新号**：这是关闭"第十八条第 3 款 vs 第八十九条"双向违宪的**唯一修法载体**，必须是契约级 Issue；as-built 实测存储增幅 **+29%** 须在此登记为预算 |
| **M1-012** | **重写**：`world.co_search` 为宪法主入口；`world.search`/`follow_links` 降级为 fallback；中文分词与别名前置；打分与 `why_matched`；top-k 与时间窗预裁剪 | 判定 REWRITE | **M1-012 重写** | 判定重写 | 三方一致；本报告补 as-built 验收数字（§4.2） |
| **M1-017** | Simulated Edge Reduction Pipeline（Camera→caption/OCR、Audio→ASR+SpeakerCluster、IMU/HR→窗特征+异常片段；输出 reduction report） | M1-017 | M1-017 | M1-017 | 三方同号同义，**唯一无冲突项**；保留 |
| **M1-018** | Chinese Hybrid Co-search Engine（预分词/词典版本、entity postings、FTS、向量兜底、有界图扩展、fusion rerank） | M1-018 | M1-012 重写的实现部分 | **M1-018** | 保留 D/F 语义；吸收 F 的 M1-019（中文分词契约）与 E 的 M1-012 ①②③④⑤⑥ |
| **M1-019** | Retention & Tombstone Worker（确定性 TTL、引用锁、两阶段删除、加密擦除接口、审计、SpeakerCluster 退休） | M1-019 | M1-017 的删除侧 | G-10/G-11 的实现侧 | 保留 D 语义；**声纹按元裁决改写**：模板可撤回/轮换/删除并留 tombstone，人物 ID 与历史引用不断裂（不采纳 E 的"只允许合并、不允许淘汰"，也不采纳宪法原文的"半年自动淘汰"） |
| **M1-020** | Early Scale & Query Plan Gate（10 万 / 100 万 / 360 万对象；中文 co-search；raw vs rollup；高扇出图；WAL 长 reader；10 万 Task 索引雏形；固定环境 P50/P95/P99 + SQL plan） | M1-020 | M7-002 前移 | **M1-021** | 保留 D 语义；F 的 M1-021 与 E 的"M7-002→M1-021 前移"并入。**本报告已用 as-built 探针预先完成 100 万档**（§5.2），M1-020 只需补 360 万档、WAL 长 reader 与 10 万 Task 索引 |
| **M1-021** | Keyword/Alias Inverted Projection & Time-Bucket Rollup Layer（投影构建、增量维护、水位、重建成本基准） | 并入 M1-018 | **M1-018** | 并入 M1-018 | **新号（拆分）**：投影层（存储/重建/水位，属 M1-014 边界）与查询引擎（排序/预算/原子接口）必须分离，否则 M1-014 的水位机制无处挂载。as-built 实测：倒排 482,345 postings/构建 3.6 s；时间桶 1M 行/13.2 s |
| **M1-022** | Retrieval Ranking & Memory-Slice Scoring Contract（recency/importance/relevance/置信度/羁绊多因子，常数入 `PAR-*`） | 并入 M1-018 | 并入 M1-012 重写 | **M1-020** | **新号**：F 的 M1-020 让位给规模门；打分契约独立成 Issue（"没有打分函数的图谱等于没有图谱"） |
| **M1-010** | **升级**：`time.zoom/select_range/shift` 命名对齐第九十一条；宏观档强制读 rollup；按 `min_granularity` 夹紧并返回 `missingness`；**并入显式 as-of 读视图** | UPGRADE | M1-010 升级 | G-09 | as-of 读视图从 E 的 M1-019 上移至此（读侧能力属查询层，M0-020 已有 `as_of_world_revision` 地基） |
| **M1-014** | **升级**：水位覆盖新增三类投影（倒排/时间桶/反向依赖）；重建成本与失败回退基准 | KEEP+UPGRADE | 复用 | G-06 附带 | 任务书既有正确立场（"索引可全部删掉重建，不是事实来源"），只需扩范围 |
| **M2-005 / M2-006** | **重写**：调度输入从 `next_wake/deadline/recurrence` 改为 TriggerExpression 求值结果；删除"待办必须定期盘点"，改为"便宜确定性机械复查 + 只有 READY/UNKNOWN-budgeted 项进入模型"；`TODO` 必须有条件或明确阻塞依赖 + 下一次条件评估点 | REWRITE | M2-005/006 重写 | G-03/G-05 | 元裁决 H-19 与 §5.2 口径；正面冲突文本在 WB:L227 与 TASK:L2225 |
| **M2-009** | **重写**：Cockpit Manifest 聚合组装器（四步序审计字段、分档 token 预算、`DIM_AI_RAPPORT` 专列、**只挂载就绪任务**、确定性序列化 + `manifest_prefix_hash`、持久化本次组装 envelope） | REWRITE | M2-009 重写 | G-01/G-18 | 元裁决 H-06/H-12；E 的 GAP-29（持久化上下文切片集合）并入，作为 7 向归因与高保真回放前提 |
| **M2-010** | **升级**：暴露第九十一条原子清单（含 E 统计的 26 个未暴露操作）；删除"生日→妈妈→历年事件→礼物→财务"四跳串行测试，改为 `co_search` 单次调用；每个工具受 capability/最小权限/危险动作确认约束 | UPGRADE | UPGRADE | G-25 | 元裁决驳回 #9：不得"Core 原子接口 100% 直接暴露给模型" |
| **M2-012** | **重写**：首包 Manifest(L0) → 按需回捞(L1，带 deadline) → 深度会话(L2)；`max_tool_steps / deadline_ms / token_budget`；固定前缀可缓存；**明确"单次看盘"指上下文一次性组装，不禁止有目的的工具循环** | REWRITE | M2-012 重写 + 冲突条款修订 | G-02 | 元裁决驳回 #10；删除与第八十四条字面冲突的"禁止固定顺序"表述，改为"冻结可观察不变量与审计字段" |
| **M2-016** | Active Conversation Working Set（token 预算内的近期轮次 + 未决话题/代词/承诺 + 水位后原始 turn；**不是死 5~8 轮**） | M2-016 | M2-017 的① | **M2-016**（=条件引擎） | **保留 D 语义**；E/F 的"条件引擎"改号为 **M2-024** |
| **M2-017** | Incremental Streaming Extractor（话题/turn 边界、异步 ExtractionJob、幂等、backpressure、revision conflict、dead letter） | M2-017 | M2-017 的② | M2-018 的 b | 保留 D 语义 |
| **M2-018** | Proactive Recall & Context Assembler（实体/事件/任务/原话/反证联合召回；deadline-aware L0/L1/L2；instruction/data 隔离） | M2-018 | M2-017 的③④ | **M2-018**（=三级流水线整体） | 保留 D 语义；F 把三个子系统合成一个 Issue，本表按 D 拆为 M2-016/017/018 三个（可并行、可独立验收） |
| **M2-019** | End-to-End Latency & Token Telemetry（TTFU/TTFT/TTFAudio/FinalUsefulLatency；ASR/检索/prefill/TTS 分段；P50/P95/P99；冷/热与 Mock/真实模型分栏） | M2-019 | **M7-005** | G-24 | 保留 D 语义（遥测必须在 M2 建，否则 M2 Gate 无法判定 1 秒）；E 的 M7-005 改为**年度正式门**（见 M7-005） |
| **M2-020** | Prediction Register Runtime（create/query/due/verify；PredictionCheckTask 调度；证伪进入**有界** invalidation） | M2-020 | M3-012 | **M2-020** | 三方同号同义（E 把它放 M3，本表按 D 放 M2 运行时 + M3-015 校准） |
| **M2-021** | WearableInteractionPort & FSM Simulator（typed haptic/display/private-audio/speaker/gesture/button；notification epoch；`IDLE/ARMED/PLAYING/EXPIRED/CANCELLED/FAULT/RECOVERY`；结果枚举区分 `IGNORED` 与 `NOT_PERCEIVED`；可注入骨传导可懂度参数） | M2-021 | **M2-020** | M6-005 的仿真部分 | 保留 D 语义；E 的 M2-020（FSM 模拟器）让位。本报告增量：`IGNORED` vs `NOT_PERCEIVED` 必须分开，否则第九十七条接受率被污染 |
| **M2-022** | Relationship Rhythm & Quiet-Heartbeat Policy（stable-data heartbeat、rapport cadence 候选、busy/sleep/driving 机械前置过滤、用户反馈冷却**设上下界**、后台静默巡检不停转） | M2-022 | **M2-019** | **M2-019** | 保留 D 语义；E/F 的 M2-019 让位。需同步扩 `WakeSource` 枚举（`enums.py:125-133` 现仅 8 项） |
| **M2-023** | Concise Response & Interaction Outcome Contract（句数/语言模式、展开请求、安全与无障碍例外、delivery/seen/ignored/unknown、style metadata） | M2-023 | —（E 无输出契约 Issue） | **M2-021** | 保留 D 语义；F 的 M2-021 让位 |
| **M2-024** | **Trigger Eligibility Engine & Ready Queue**（四类条件求值器、事件订阅索引、ready queue、hysteresis/debounce、TTL、"条件长期不可达"检测、饥饿审计；禁止 `eval`） | 契约在 M0-027，运行时未单列 | **M2-016** | **M2-016** | **新号**：E/F 的 M2-016 语义在此落地。验收含"10 万 WAITING / 10 READY 不做全量 LLM 扫描，等待期模型调用 = 0" |
| **M2-025** | **Budget Ledger & Degradation Ladder**（日/周 × 类别：沉淀/清洗/检索/对话/心跳；接上已冻结的 `BUDGET_EXHAUSTED`；无网降级能力清单） | 指标层（§8.3） | **M2-018** | G-24 | **新号**：E 的 M2-018 让位给回捞组装器。元裁决 §5.2：账本形态由 ADR 决定（WorldObject / control-plane table / telemetry ledger），但必须持久、可查询、可审计 |
| **M2-011** | **升级**：Session 快照必须持久化本次组装的上下文 envelope（refs/版本/水位/排名解释/省略/预算/模型与策略版本） | UPGRADE | GAP-29 | G-01 附带 | 元裁决 §5.2：不默认永久复制敏感原文，按 retention/加密策略处理 |
| **M3-004 / M3-005** | **升级**：日度复盘新增大模型清洗通道，但必须带永存白名单（EventAnchor 证据、关键原话、锚点数据源）+ 隔离区滚动窗口 + `Tombstone`（被删 ID 清单 + 内容哈希 + 删除理由 + 决策证据）+ 人工/策略 Gate | UPGRADE | M3-004/005 升级 | G-11 | 元裁决 H-03；关闭"§33.5 物理删除 vs 第二十五/九十三/一百一十六条永存"的宪法内部冲突 |
| **M3-010** | **升级**：AI 自身世界补 `DIM_AI_RAPPORT` / `DIM_AI_GROWTH` seed 维度（沟通经验消费 CommunicationExperience） | UPGRADE | M3-010 升级 | G-15 | 四步序第二步的数据源，缺它则 M2-009 无法组装羁绊切片 |
| **M3-012** | Retrospective Semantic Annotation（迟到用户自述以 `valid_time + learned_at` **追加**到旧时间切片；原始物理 Observation 不改；可重建"当时不知道"与"今天回看"） | M3-012 | **M1-019** | G-17 | 保留 D 语义；E 的 M1-019 并入（其读侧 as-of 视图上移到 M1-010 升级） |
| **M3-013** | LifeChapter Candidate & Baseline Migration（多维 change-point 只产生候选；经持续/反证/迟滞确认后 ACTIVE；旧敏感度版本归档；误判可回滚） | M3-013 | M3-013 | M3-013 | 三方同号同义，保留 |
| **M3-014** | CommunicationExperience & Rapport Consolidation（从 Action/Outcome/Delivery 提炼候选经验；适用范围/反例/过期；rapport 只影响表达成本，不改变事实阈值） | M3-014 | M3-014 | G-14 | 保留；元裁决 §5.2「不以讨好换接受率」 |
| **M3-015** | Prediction Calibration & No-op Propagation（Brier/log score、分桶校准、重复与相关预测去重、semantic no-op diff） | M3-015 | M3-012 的校准部分 | G-12 附带 | 保留 D 语义 |
| **M3-016** | **Bounded Propagation Kernel**（typed dependency、visited/SCC 去重、深度与节点预算、continuation 可暂停可续跑、read-time validation、封存区间只追加 postscript） | §5.4 指出不足但未单列号 | 无 | 无 | **新号（本报告新增）**：元裁决 H-10 要求"禁止全图级联重算"，但 D/E/F 都没有给它独立 Issue；as-built 实测证明这是**成本最高的一处**（9.3 s / 51,822 对象 / 15.55 M token vs 预算化 10.82 ms，差 860 倍） |
| **M3-001** | **升级**：依赖失效与纠错传播改调 M3-016 内核，删除"全量 Dependency 读入内存"的实现前提（`dependency/graph.py::collect_impacted_dependents` 现状） | REWRITE | 无 | G-12 附带 | as-built 实测：现状 9.3 s/次且随历史线性增长 |
| **M4-002 / M4-004** | **修订**：验收文本 `V01~V30覆盖` 改为逐条 `TS-001~TS-051` oracle 引用；禁止"笼统标覆盖" | 修订 | §9.5 | G-23 | 消除悬空验收引用（TASK:L3377） |
| **M4-005** | TEST V0.2 Scenario Pack（`TS-021~TS-051`，每条含 oracle、正例/近似反例/证据不足三版本、seed、预算） | M4-005 | §9.5 测试规范升级 | §3.5 | 保留 D 语义 |
| **M4-006** | Runtime Stress & Ablation Pack（50 轮对话、10 万 Task、中文 co-search、Wake storm、extractor crash、FSM overlap、memory injection；失败可归因到七层；后台成本计入总 token/CPU/I-O） | M4-006 | 无 | 无 | 保留 D 独有 |
| **M5-004** | CommunicationExperience A/B（同一世界检查点分叉；只有未见情境中提高净帮助且不增加谄媚/操控/错误事实，才允许进入优先建议） | M5-004 | M5-003 升级 | G-14 | 保留 D 语义 |
| **M6-005** | AmbientCanvas / SkillCard Projection Contract（设备无关卡片 DTO、生命周期、layout budget、accessibility fallback、capability scope；插件只获最小上下文投影） | M6-005 | **M6-005** | **M6-005**（=穿戴模拟通道） | 保留 D/E 语义；F 的"mock 震动/骨传导通道注册"并入 **M2-021** |
| **M7-002** | **升级**：三档规模（10 万/100 万/360 万）正式复测 + P50/P95/P99 + 检索/滑动条聚合/依赖传播超节点/WAL/库体积；首测已在 M1-020 完成 | UPGRADE | M7-002 升级 | 无 | 保留"记录"职责，但门在 M1-020 |
| **M7-005** | End-to-End Latency & Cost SLO 年度正式门（TTFT/TTFAudio/FinalUsefulLatency、看板体积、token/调用/唤醒/维护成本；**数据未达标前任何文档不得宣称"保障 1 秒"**） | 并入 M2-019 | **M7-005** | G-24 | 保留 E 号（M7 现有序列 001~004，append 安全）；与 M2-019 关系 = 建遥测 vs 年度正式门 |
| **M8-004** | 穿戴契约预留评估（FSM 零误触状态机契约、三层 UI 信息架构、马达/骨传导能力抽象、插件最小授权域、离线降级契约）——作为 M8-003 Gate 的**输入文档**，此 Gate 之前不写一行硬件代码 | POST-M8-HW-001 前置 | 无 | **M8-004** | 保留 F 号（M8 现有 001~003） |
| **POST-M8-HW-001** | 真实柔性屏、马达骨传导、续航、热与量产、人体实验 | POST-M8-HW-001 | 无 | M8-004 之后 | 保留 D 号；只在 M8-003 通过后启动，不得反向阻塞当前 Linux Core |

### 3.3 测试场景编号仲裁（`V` → `TS`）

| 定稿号 | 内容 | 来源 | 说明 |
|---|---|---|---|
| `TS-001~TS-020` | 测试规范 §10 现有 V01~V20 **原样保留** | TEST:L240-259 | 只改前缀，内容不动；映射表记录 `TS-00n ≡ V0n` |
| `TS-021~TS-030` | 宪法 L1610-1619 的 V21~V30 **逐条原文下传** | V3 宪法 | 每条补 fixture、隐藏真值、近似反例、证据不足版；映射 `TS-02n ≡ 宪法 V2n` |
| `TS-031~TS-045` | D 的 V31~V45 **原样保留**（Single-Shot Cockpit / 启动优先级冲突 / 50 轮长对话+后台萃取 / 旧话题重提 / 10 万条件 Task / 条件边界 / 中文共现 / 5D-LOD / 边缘摄入缩减 / 声纹冒认与退休 / 长平稳心跳与情境抑制 / Prediction 证伪 / LifeChapter 误报 / 真人短表达 / Wearable FSM 与恶意输入） | D §8.2 | D 为底稿 |
| `TS-046~TS-050` | E 的脏数据族中**未被 D 覆盖**的 5 条：时钟倒挂、乱序到达、传感器长时缺失、ASR 误转写、GPS 漂移 | E §9.5（原 V31~V36） | E 的第 6 条"声纹混淆/冒认"并入 `TS-040` |
| — | F 的 V31~V37 **全部并入 TS-031~TS-045**，不新增号 | F §3.5 | 映射：F-V31→TS-033/034；F-V32→TS-031/035；F-V33→TS-037；F-V34→TS-041；F-V35→TS-044；F-V36→TS-031；F-V37→TS-042 |

### 3.4 验收编号仲裁

| 命名空间 | 定稿 | 依据 |
|---|---|---|
| `A01~A10` | **专属宪法第一百一十四条**（L1633-1642） | 元裁决 H-18 |
| `ARCH-01~ARCH-10` | 【架构规划】§12 的 A01~A10 全部改号；**M2-015 等所有裸引 A07/A08/A09 处同步改写** | 元裁决 H-18、Gate 0 第 3 项 |
| `WB-01~WB-12` | 【工作台规格】§14 的 W01~W12 改前缀（避免与宪法/架构验收混淆） | 本报告 |
| `WB-13 / WB-14 / WB-15` | 新增：Manifest 就绪挂载与预算 / 流水线窗口与萃取水位 / 输出契约（1~3 句与例外） | F §3.6 |
| `R1-* / R2-* / R3-* / V3-01~03` | 宪法既有，不动；工程侧通过映射表引用 | §3.1 规则 5 |
| `ACC-01~ACC-14` | **v3.0 专属工程门（本报告定稿，见 §4.6）** | 补 G2 验收缺口 |
| `PAR-01~PAR-15` | **可测参数登记表（本报告定稿，见 §4.7）** | 第七十六条 + 元裁决 §5.2 |
| `MOD-C01~MOD-C14` | 唯一模块映射，**以宪法 L1452-1463 为准**；【架构规划】L88-97 的 C05/C06/C09/C10 定义作废并改写 | D §1.3 模块编号漂移 |
| `M0~M8` | 里程碑唯一口径（宪法 L1484-1504 与任务书一致）；**【架构规划】§10 的 M0~M6 改号为 M0~M8**，缺失的经验/教育独立阶段补入 | D §1.3、E GAP-27、F G-22 |

---

## 4. 统一整改母表（核心交付物 B）

### 4.0 母表使用规则

1. 每个 Issue 必须按宪法第一百一十三条(L1545-1560)的 **12 要素**施工：任务编号 / 目的 / 输入 / 输出 / 接口 / 数据结构 / 前置依赖 / 禁止行为 / 单元测试 / 集成测试 / **验收场景（引用 `TS-*`）** / 已知限制。
2. **来源列必填**：保留 D/E/F 原号映射，任何后续修订都能追溯到三份审计的原始判定。
3. **验收数字只能引用 §5.2 的可引用表**；引用 §5.3 中未入库数字的 Issue 一律退回。
4. **Gate 归属决定放行顺序**：Gate 0 未过不得派 Gate 1 的编码单；Gate 1 未过不得派 Gate 2。
5. 母表本身是 v3.0.1 修正案的附件，**修正案发布后由追踪矩阵自动生成**，不再手工维护行号（元裁决 L186）。

### 4.1 Gate 0：M0-V3 契约扩展（**现在阻断**）

| 定稿号 | 动作 | 关键输出 | 阻断验收 | 来源 |
|---|---|---|---|---|
| M0-023 | 新增 | v3.0 唯一 hash、`MOD-C01~C14` 映射、M0~M8 映射、旧 API→V3 API 兼容表、条款→module→Issue→test 矩阵、四份工程文档 V0.2 刷新（上位依据改为 v3.0） | `CONFLICT/UNMAPPED = 0` 才可重开 M0 Gate；v3.0 自身冲突必须有 v3.0.1 决议号 | D M0-023 + E §9.6 + F §3.6 |
| M0-024 | 新增 | Prediction schema、EvidenceSet 关联、验证状态机 `PENDING→CORROBORATED/FALSIFIED/EXPIRED`、evaluator version、coverage、intervention、actual outcome；`TaskType` 增 `PREDICTION_CHECK`；第五十三条立项理由必填 | 无立项理由的 Prediction 被拒；无观测→`INCONCLUSIVE`，不得自动 `FALSIFIED`；`ClaimType.PREDICTION` 迁移 fixture | D M0-024 / E M0-023 / F M0-023 |
| M0-025 | 新增 | LifeChapter：`CANDIDATE/ACTIVE/ARCHIVED/REVISED/REJECTED`、时间范围、基线 refs、EvidenceSet、前后章节指针、迁移原因 | 一次信号不得直接 ACTIVE；旧章节与旧基线可重建、只读可查 | D M0-025 / E M0-024 / F M0-024 |
| M0-026 | 新增 | CommunicationExperience（表达方式/语气/用户反应/有效范围，与 OperationExperience 分表）；AI seed 维度稳定 ID：Identity/Rapport/Promises/Growth/ActionLog | 缺 delivery 的"无回应"不得推导为抵触；风格效果与事实立场分开 | D M0-026 / E M0-025 / F M0-025 |
| M0-027 | 新增 | TriggerExpression AST：`TimeReached/EventMatched/ObservationPredicate/DependencyReady/AllOf/AnyOf/Not`；三值求值、版本、订阅键、expiry；`Task.completion_condition/cancel_condition/recurrence` 从无类型 dict 迁到 typed 契约 | 任意非即时任务都有可执行 trigger 或明确 manual-only；任意 Python `eval` 被拒绝；迁移 fixture 覆盖 `models.py:332-339` | D M0-027 + E/F M2-016 契约部分 |
| M0-028 | 新增 | Conversation/Turn envelope、seq、speaker、finalization、ExtractionSpan/Job/Watermark、ContextSlice | 重复 turn / 重复 span 幂等；乱序与未完成 turn 不被错误萃取 | D M0-028 |
| M0-029 | 新增 | CockpitManifest 契约：wake、safety、identity、rapport、objective、current evidence、**ready tasks only**、capabilities、conversation/extraction watermarks、omissions、budget、`manifest_prefix_hash` | JSON schema snapshot；**WAITING task 泄露数 = 0**；每项带 freshness/source；同输入前缀哈希稳定（CI 断言） | D M0-029 + E/F M2-009 契约部分 |
| M0-030 | 新增 | SourceEnvelope、instruction trust lane、transform lineage、model/firmware version、retention class、legal hold、tombstone/audit；**Modality 枚举**（`IMAGE_SEMANTIC/AUDIO_TRANSCRIPT/VOICEPRINT/IMU_FEATURE/HR_AGGREGATE/TEXT/APP/GPS`）；`source_quality` 计算口径；`min_granularity` | OCR/群聊内容默认 DATA 而非指令；**LLM 无不可逆删除权限**；`modality: str` 自由字符串被枚举取代 | D M0-030 + E M0-007 升级 |
| M0-031 | 新增 | 双时态不变量：`valid_from/valid_to/known_from/known_to/invalidated_by/supersedes/annotates`；默认当前读 + 显式 as-of 读；禁止 UPDATE/DELETE 历史 `object_revisions` 的架构测试 | 架构测试通过；as-of 两种视图可重建（`AS_OF(t)` / `AS_KNOWN_AT(cutoff)`） | **本报告新号** + E M0-005 升级；元裁决 H-04/H-05 |
| M0-032 | 新增 | 派生投影合法化：宪法层"派生投影 (Derived Projection)"定义 + schema 扩展（关键词倒排表、别名/同义词表、时间桶 rollup、`Tombstone` 表、预算账本表）；投影可从 revision 全量重建、不参与真相、带 `index_watermark`、失配返回 `STALE_INDEX`、**不计入第十八条第 3 款的冗余拷贝禁令** | 投影全量重建后与主库**逐条一致**（as-built 实测 missing=0 / extra=0）；存储增幅登记为预算（as-built 实测 **+29%**，704.8→906.7 MB / 1M 行） | **本报告新号** + E M0-017 升级；关闭 B3/RT-16 |

> **Gate 0 放行判据**：上述 10 个 Issue 全部合同评审通过（或以同等 ADR 明确合并/替代关系）+ 22 个核心对象逐个做出 `NOW / EXTENSION SLOT / DEFERRED` 决策且无悬空 owner + `CONFLICT/UNMAPPED = 0`。**Gate 0 未过：停止新 M1/M2 派单**，只允许做修正案、契约、迁移 fixture 与测试夹具。

### 4.2 Gate 1：Data / Query / Scale（M1 前置）

| 定稿号 | 动作 | 关键输出 | as-built 验收值（profile：2 vCPU / SQLite 3.40.1 / 容器 FS / 1M revision / seed 20260915） | 来源 |
|---|---|---|---|---|
| M1-012 | **重写** | `world.co_search(keywords[], time_range, dims[], top_k, budget)` 原子入口；中文分词 + 受控关键词抽取（**禁用 `unicode61` 裸用**，`trigram` 仅作 ≥3 字补充）；别名/同义词表（妈妈=母亲=我妈=P003）；`why_matched`；`world.search`/`follow_links` 保留为 fallback | `[妈妈,生日,礼物]` **单次调用**返回历年礼物事件 + 反馈原话 + 消费 + 当前心愿 Claim；连续中文召回 **> 0**；2 字词召回 **> 0**；零命中必须显式 `no_hits`（不得静默空数组）。as-built 现状对照：LIKE 三词共现 **1,282.8~1,357.9 ms**、`json_extract` 时间窗 **1,201.4~1,468.6 ms** | D REWRITE / E M1-012 / F G-06 |
| M1-017 | 新增 | 模拟端侧 reduction 管线：Camera→caption/OCR、Audio→ASR+SpeakerCluster、IMU/HR→窗特征+异常片段；**摄入批次 = 一个 world_revision**（group commit）；输出 reduction report | 50/100 Hz 原始 feed **不逐点入长期库**；平稳 2 h 心率 = **1 个均值 Observation** + 异常独立写入；同时报告压缩比/异常窗口召回/长期行数；**保留** 10k 输入吞吐测试。as-built 实测：单条提交 `FULL` **0.47 ms/次**、`NORMAL` **0.09 ms/次**（容器 FS 下限）⇒ 830 观测/日逐条提交 = 1.7~12.5 s/日纯 fsync | D/E/F M1-017 同号同义 |
| M1-018 | 新增 | Chinese Hybrid Co-search Engine：预分词管线 + 词典版本冻结、entity postings、FTS5（预分词列）、向量兜底适配器、有界图扩展、fusion rerank | 连续中文、别名、否定、角色错位、零命中、partial index 全部有 fixture；结果给 hit reasons。as-built 实测可选路径：预分词列 `MATCH '妈妈 AND 生日 AND 礼物'` = **0.87 ms / 16 命中**；FTS5 `unicode61 MATCH '妈妈'` = **0 命中**；`trigram MATCH '妈妈'`(2字) = **0 命中且不报错**、3 字 = 2,925 命中 | D M1-018 / F M1-018+M1-019 |
| M1-019 | 新增 | Retention & Tombstone Worker：确定性 TTL、引用锁、两阶段删除、加密擦除接口、审计、SpeakerCluster 退休 | 被 EvidenceSet/Task 引用的数据不能删；删除重试幂等；历史引用返回 **tombstone 而非断裂**；声纹模板可撤回/轮换/删除且 Entity/Event 引用不断裂 | D M1-019（声纹口径按元裁决 §5.2 改写） |
| M1-020 | 新增 | Early Scale & Query Plan Gate：10 万 / 100 万 / 360 万对象；中文 co-search；raw vs rollup；高扇出图；WAL 长 reader；10 万 Task 索引雏形；固定环境 P50/P95/P99 + SQL plan | **100 万档已由本报告 as-built 探针预先完成**（§5.2 全部数字 + `EXPLAIN QUERY PLAN`）；剩余：360 万档、WAL 长 reader、10 万 Task 索引。失败则**禁止冻结查询 schema** | D M1-020 / E M7-002 前移 / F M1-021 |
| M1-021 | 新增 | 投影层：关键词/别名倒排表构建与增量维护、时间桶 rollup（日/周/月/年二级）、水位、重建 CLI 与成本基准 | as-built 实测：倒排 **482,345 postings / 构建 3.6 s**；时间桶 **1M 行 / 13.2 s**；存储 **+29%**；GROUP-BY 交集 **43~200 ms**；最稀有词驱动 EXISTS **7.29~47.18 ms**；时间桶滑动 **0.66/3.86/14.40/112.48 ms**（1d/1w/1m/1y）；结果与 LIKE 全表扫描**逐条一致** | **本报告新号**（拆自 E M1-018 / D M1-018） |
| M1-022 | 新增 | 检索排序契约：`α·recency + β·importance + γ·relevance + δ·confidence + ε·rapport`，常数入 `PAR-*`，返回打分解释 | 同一 query 在参数扰动下排序稳定可解释；不得以打分掩盖零召回 | **本报告新号**（F M1-020 让位） |
| M1-010 | **升级** | `time.zoom(scale)/time.select_range(start,end)/time.shift(offset)` 对齐第九十一条；宏观档**强制读 rollup**；按 `min_granularity` 夹紧并返回 `missingness`；并入显式 as-of 读视图 | as-built 实测：现状 `json_extract` 宏观档 **1,468.6 ms**（与窗口无关）；rollup 后 1m/1y = **14.40 / 112.48 ms**。⇒ **1y 档仍超 `PAR-08`（20 ms）**，必须建**二级年桶**（年档读年桶而非日桶求和）；这是本报告从实测得出的、D/E/F 均未指出的具体设计要求 | D/E UPGRADE + E M1-019 读侧 |
| M1-014 | **升级** | 水位覆盖新增三类投影（倒排/时间桶/反向依赖）；`strict_freshness` 回退主库；重建成本与失败回退基准 | 人工落后 10 revisions → strict 查询报 `STALE_INDEX`；rebuild 后逐条一致 | 任务书既有（KEEP+UPGRADE） |
| M1-001 | **修订验收** | 删除"10k 条模拟心率可批量写入"作为**唯一**验收；改为"原始 feed 吞吐测试保留 + 输出必须经 reduction + 同时报告压缩比/异常召回/长期行数" | 元裁决 H-20、§5.2 | E GAP-11 / D H-20 |

### 4.3 Gate 2：Active Cognitive Loop（M2 前置）

| 定稿号 | 动作 | 关键输出 | 阻断验收（含 as-built 值） | 来源 |
|---|---|---|---|---|
| M2-009 | **重写** | Cockpit Manifest 组装器：四步序审计字段（`self_state/rapport_state/stance/focus`）+ 安全 Step-0 前置；分档 token 预算（`PAR-06`）；`DIM_AI_RAPPORT` 专列；**只挂载就绪任务**（调 M2-024 的 `task.inspect_ready()`）；确定性序列化 + `manifest_prefix_hash`；持久化组装 envelope | WAITING 任务 **0 条**进入上下文；看板体积与字段完整率可测；回放可精确复现"当时模型看到了什么"；**组装 p95 ≤ `PAR-09`(20 ms)**（as-built 实测四步序 85 行 = **0.3 ms**，余量充足 ⇒ 验收重点在内容选择而非性能） | D REWRITE / E M2-009 / F G-01 |
| M2-012 | **重写** | L0 首包 Manifest → L1 按需回捞（带 deadline）→ L2 深度会话；`max_tool_steps / deadline_ms / token_budget`；固定前缀可缓存；**明确"单次看盘"= 上下文一次性组装，不禁止有目的的工具循环** | 端到端 TTFT 与 token 有遥测（M2-019）；超预算收敛为"当前最优回答 + 建后续任务"，不重复行动；删除与第八十四条字面冲突的"禁止固定顺序"表述 | D REWRITE / E M2-012 / F G-02 |
| M2-024 | 新增 | Trigger Eligibility Engine & Ready Queue：四类条件求值器（`time_reached/context_matched/event_occurred/dependency_ready`）、事件订阅索引、ready queue、hysteresis/debounce、TTL、条件长期不可达检测、饥饿审计；**禁止 `eval`** | 十类任务全部带条件；**等待期模型调用 = 0**；10 万 WAITING / 10 READY 时**不做全量扫描**；创建时可满足性 dry_run | **本报告新号**（E/F 的 M2-016 语义） |
| M2-016 | 新增 | Active Conversation Working Set：token 预算内近期轮次 + 未决话题/代词/承诺 + 水位后原始 turn（**不是死 5~8 轮**） | 50 轮中跨 20 轮的代词/承诺仍可恢复；前台 prompt 有硬预算（`PAR-01`=1500 token / `PAR-02`=5~8 轮为默认值）和省略说明 | D M2-016 |
| M2-017 | 新增 | Incremental Streaming Extractor：话题/turn 边界检测、异步 ExtractionJob、幂等键、backpressure、revision conflict、dead letter | crash/retry **不重复** Claim/Event；lag 超阈值时前台自动保留未萃取原文；**会话进行中**（非等到日总结）世界已出现新 Claim | D M2-017 |
| M2-018 | 新增 | Proactive Recall & Context Assembler：实体/事件/任务/原话/反证联合召回；deadline-aware L0/L1/L2；**instruction/data 隔离** | 不同 Wake Reason 的 manifest 显著不同（V3-03 可验收）；旧话题重提召回正确；**恶意 OCR/群聊内容不能变成系统指令** | D M2-018 |
| M2-019 | 新增 | 端到端延迟与 token 遥测：TTFU/TTFT/TTFAudio/FinalUsefulLatency；ASR/检索/prefill/TTS 分段；P50/P95/P99；冷/热与 Mock/真实模型分栏 | **无数据不得宣称"保障 1 秒"**（元裁决 H-13、驳回 #4）；as-built 侧已给出存储段下限：看板组装 0.3 ms、点查 0.011 ms、投影检索 7~47 ms ⇒ 1 秒预算的主要消耗在模型 prefill/生成与 ASR/TTS，必须分段实测 | D M2-019 / E M7-005 建遥测部分 |
| M2-022 | 新增 | Relationship Rhythm & Quiet-Heartbeat Policy：stable-data heartbeat（`PAR-03`=3~5 h 为默认值）、rapport cadence 候选、busy/sleep/driving **机械前置过滤**、用户反馈冷却**设上下界**、后台静默巡检不停转；扩 `WakeSource` 枚举 | 平稳 24 h **不产生固定 3~5 h 轰炸**；不方便时模型可不唤醒或只后台检查，**外部通知 = 0**；连续"别烦我"后主动出声频率下降但**不归零**；安全旁路不被冷却屏蔽 | D M2-022 / E M2-019 / F M2-019 |
| M2-023 | 新增 | Concise Response & Interaction Outcome Contract：句数/语言模式、展开请求、安全与无障碍例外、`delivery/seen/ignored/unknown`、style metadata | 普通短对话默认 **1~3 句**（`PAR-11`）；复杂安全信息**不因句数被截断**；**无回应不等于拒绝** | D M2-023 / F M2-021 |
| M2-021 | 新增 | WearableInteractionPort & FSM Simulator：typed haptic/display/private-audio/speaker/gesture/button；notification epoch；`IDLE/ARMED/PLAYING/EXPIRED/CANCELLED/FAULT/RECOVERY`；结果枚举**区分 `IGNORED` 与 `NOT_PERCEIVED`**；可注入骨传导分档 SNR 可懂度参数 | 无有效 epoch 的摸耳播放 = **0 次**；并发通知/重启/超时/取消不串内容；错过窗口不丢通知；安全震动不被普通冷却屏蔽。**不得宣称"零误触已证明"**（元裁决驳回 #6），只写"无先导 epoch 时听音通道开启次数 = 0" | D M2-021 / E M2-020 / F M6-005 仿真部分 |
| M2-020 | 新增 | Prediction Register Runtime：create/query/due/verify；`PredictionCheckTask` 调度；证伪进入**有界** invalidation（调 M3-016 内核） | 到期/迟到/缺测/AI 干预/自我实现/重复检查均可重放且幂等；**预测命中不得自动提高底层事实置信度**（元裁决驳回 #7） | D/E/F M2-020 |
| M2-025 | 新增 | Budget Ledger & Degradation Ladder：日/周 × 类别（沉淀/清洗/检索/对话/心跳）；接上已冻结的 `BUDGET_EXHAUSTED`；无网降级能力清单 | 7 天连续运行各类别用量可查；超支**按策略降级**而非静默继续。as-built 年度账（P9）：对话 **56.6%** / 金字塔 **21.7%** / 每日清洗 **17.7%** / 心跳 **4.0%**，合计 **68.6 M in + 7.3 M out token/用户/年** ⇒ **"零浪费"条款覆盖的对话段只占约一半支出，清洗与金字塔必须同时进账本** | **本报告新号**（E M2-018 让位） |
| M2-005 / M2-006 | **重写** | 调度输入改为 TriggerExpression 求值结果；删除"待办必须定期盘点"；`TODO` 必须有条件或明确阻塞依赖 + 下一次条件评估点；停机恢复策略保留 `catch-up/skip/merge/expire` | 第八十六条零空转可验收；待办任务不再产生遍历式唤醒；**允许便宜确定性机械复查**（元裁决 H-19） | D REWRITE / E M2-005/006 / F G-03 |
| M2-010 | **升级** | 暴露第九十一条原子清单（含 26 个未暴露操作）；删除四跳串行测试改 `co_search` 单次；每工具受 capability/最小权限/危险动作确认约束 | 第九十一条清单 100% 可被 AI 调用，但**不得 100% 直接暴露**（元裁决驳回 #9） | D/E UPGRADE / F G-25 |
| M2-011 | **升级** | 持久化上下文 envelope（refs/版本/水位/排名解释/省略/预算/模型与策略版本）；敏感原文按 retention/加密策略处理，**不默认永久复制** | 7 向归因与高保真回放可实现（E GAP-29） | E GAP-29 / 元裁决 §5.2 |
| M2-015 | **修订** | 裸引 `A07/A08/A09` 改为 `ARCH-07/08/09` 或宪法 `A07/A08/A09`，二者不得混用 | 消除验收二义（H-18） | E GAP-26 |

### 4.4 Gate 3：Long-term Cognition（M3 前置）

| 定稿号 | 动作 | 关键输出 | 阻断验收（含 as-built 值） | 来源 |
|---|---|---|---|---|
| **M3-016** | **新增** | Bounded Propagation Kernel：typed dependency、visited/SCC 去重、深度与节点预算（`PAR-10`）、continuation 可暂停可续跑、read-time validation、封存区间只追加 postscript | as-built 实测对照：M0 现状全量内存扫描 **9.3 s / 51,822 受影响对象**（≈ **15.55 M token** 复核）；索引无预算 **231.9 ms**；预算化（500 节点/深度 2）**10.82 ms**；懒传播（只标直接依赖）**0.82 ms / 20,000**；普通实体 7,093 对象 / 17.87 ms。⇒ 验收：超节点场景单次 ≤ 预算化量级，**禁止全图级联重算**（H-10） | **本报告新号**（D §5.4 指出不足但未单列） |
| M3-001 | **重写** | 依赖失效传播改调 M3-016 内核；删除"全量 Dependency 读入内存"的实现前提 | `dependency/graph.py::collect_impacted_dependents` 的内存前提被替换；持久化反向依赖索引（as-built 实测同规模 Dependency 落库 23.7 s、边表构建 7.5 s、2,211,817 条边） | D REWRITE |
| M3-012 | 新增 | Retrospective Semantic Annotation：迟到自述以 `valid_time + learned_at` **追加**到旧切片；原始物理 Observation 不改；`annotation_generation` 单调计数 + 日上限 | 可重建"当时不知道"与"今天回看"；心率原值 revision **不变**；历史 `object_revisions` 无 UPDATE/DELETE（架构测试） | D M3-012 / E M1-019 |
| M3-013 | 新增 | LifeChapter Candidate & Baseline Migration | 短期旅行/生病不误判永久章节；毕业/迁居等稳定变化可确认且误判可回滚；**R3-05 可验收** | D/E/F M3-013 |
| M3-014 | 新增 | CommunicationExperience & Rapport Consolidation | **不以讨好换接受率**；反谄媚事实阈值在不同 rapport 下保持一致；**V3-01 可验收** | D M3-014 / E M3-014 |
| M3-015 | 新增 | Prediction Calibration & No-op Propagation | Brier/log score 与分桶校准可计算；模型只换措辞**不传播**；预测很多但不校准**不得提高**源 Claim 信心；**R3-03 可验收** | D M3-015 |
| M3-004 / M3-005 | **升级** | 每日大模型清洗通道 + 永存白名单 + 隔离区滚动窗口（`PAR-14`）+ `Tombstone`（ID 清单 + 内容哈希 + 删除理由 + 决策证据）+ 人工/策略 Gate | 删除动作可审计可回放；第二十七条证据链在清洗后仍 **100% 可下钻**；as-built 成本参照：每日清洗读全天 830 条观测 ≈ 33k token 输入，**12.12 M token/年（占全年输入 17.7%）**⇒ 清洗不是免费的"智能剪枝"，必须进 M2-025 账本 | D/E UPGRADE / F G-11 |
| M3-010 | **升级** | 补 `DIM_AI_RAPPORT` / `DIM_AI_GROWTH` seed 维度 | 四步序第二步有数据源；**V3-02 可验收** | E M3-010 升级 / F G-15 |

### 4.5 M4~M8 / TEST V0.2 / 文档 V0.2

| 定稿号 | 动作 | 关键输出 | 来源 |
|---|---|---|---|
| M4-002 / M4-004 | **修订** | 验收文本 `V01~V30覆盖` → 逐条 `TS-001~TS-051` oracle 引用；禁止笼统标覆盖 | 本报告（悬空引用）+ D §8.1 |
| M4-005 | 新增 | TEST V0.2 场景包 `TS-021~TS-051`（每条含 oracle、正例/近似反例/证据不足版、seed、预算）；**在新盲测前版本化冻结**（H-21） | D M4-005 / E §9.5 / F §3.5 |
| M4-006 | 新增 | Runtime Stress & Ablation Pack：50 轮对话、10 万 Task、中文 co-search、Wake storm、extractor crash、FSM overlap、memory injection；失败可归因到七层；后台成本计入总 token/CPU/I-O | D M4-006 |
| M5-004 | 新增 | CommunicationExperience A/B（同一世界检查点分叉） | D M5-004 / E M5-003 升级 |
| M6-005 | 新增 | AmbientCanvas / SkillCard Projection Contract：设备无关卡片 DTO、生命周期、layout budget、accessibility fallback、capability scope；与 M6-001 AppManifest 打通；先做 23cm 环形画布布局约束模拟器，**不做硬件** | D/E M6-005 / F M6-005 |
| M7-002 | **升级** | 三档规模正式复测 + P50/P95/P99 + 检索/滑动条聚合/依赖传播超节点/WAL/库体积（首测在 M1-020） | E M7-002 升级 |
| M7-005 | 新增 | 端到端延迟与成本 SLO **年度正式门**；数据未达标前任何文档不得宣称"保障 1 秒" | E M7-005 |
| M8-004 | 新增 | 穿戴契约预留评估（M8-003 Gate 输入文档）：FSM 契约、三层 UI 信息架构、马达/骨传导能力抽象、插件最小授权域、离线降级 | F M8-004 |
| POST-M8-HW-001 | 新增 | 真实柔性屏/马达骨传导/续航/热/量产/人体实验；只在 M8-003 通过后启动 | D |
| **TEST V0.2** | 文档 | ①`TS-001~TS-051` 场景矩阵；②§11 新增会话层与检索层指标（TTFT 分布、每会话 input token 分布、窗口溢出率、萃取延迟、回捞 recall@k、1~3 句达标率、co_search p95、就绪判定模型调用数）；③§16 补 `ACC-01~ACC-14` 与 R3/V3 家族；④**§5 规模表拆成 `raw feed volume` 与 `long-term object rows` 两列**（见 §2.5 新发现）；⑤声明 v3.0 兼容版本与 hash | E §9.5 / F §3.5 / 本报告 |
| **ARCH V0.2** | 文档 | 上位依据改 v3.0；C10「十三步循环」→「Manifest + 四步序决策因子 + 会话流水线」；C06 增列共现引擎与排序契约；C09 增列第七类触发；C01 增列多模态轻量化策略；**§10 M0~M6 改号 M0~M8**；**§12 A01~A10 改号 ARCH-01~10**；`MOD-C01~C14` 以宪法 L1452-1463 为准 | E §9.6 / F §3.6 / D §1.3 |
| **WB V0.2** | 文档 | §3 工作包 → Manifest 字段契约；§10 十三步降级为"会话责任清单（不得作为强制执行序）"并说明与四步序的关系（四步序 = 决策因子完整性，十三步 = 责任覆盖）；§5.3 增补 `co_search`；§7.2 删除"定期任务盘点"；新增 `WB-13/14/15` | E §9.6 第 5 项 / F §3.6 |
| **TASK V0.3** | 文档 | L6 上位依据加 v3.0 与 R3；L4240-4257 派单链改为 `v3.0 + v3.0.1 修正案 + R1/R2/R3 + 四份 V0.2 规格 + 本任务书 → GitHub Issues`；Issue 模板（L4173-4180）的"AIOS宪法2.0"改 v3.0；并入本报告 §4 母表 | 本报告 |

### 4.6 v3.0 专属工程验收门 `ACC-01~ACC-14`（定稿；数字均为 profile 默认值）

| 编号 | 门 | 判据（profile：2 vCPU / SQLite 3.40.1 / 1M revision / as-built 冻结 schema） | as-built 实测支撑 |
|---|---|---|---|
| ACC-01 | 共现检索 | `co_search` 单次调用；p95 ≤ **50 ms**（`PAR-07`）；连续中文召回 > 0；2 字词召回 > 0；零命中显式 `no_hits` | 现状 LIKE **1,282.8~1,357.9 ms**；投影路径 **7.29~47.18 ms**；预分词 FTS **0.87 ms** |
| ACC-02 | 时间滑动条 | 宏观档强制读 rollup；1d/1w/1m p95 ≤ **20 ms**（`PAR-08`）；1y 档须二级年桶后 ≤ 20 ms；必须返回 `missingness` 与 `granularity_floor` | 现状 **1,201.4~1,468.6 ms**（与窗口无关）；rollup 后 **0.66/3.86/14.40/112.48 ms** ⇒ **1y 档现状不达标，需二级年桶** |
| ACC-03 | 条件任务 | 10 万 WAITING / 10 READY：等待期**模型调用 = 0**；就绪判定为索引查；三值求值；条件永假检测 | 契约前提：`Task.completion_condition` 现为无类型 dict（`models.py:338`）⇒ 未过 M0-027 前**不可测** |
| ACC-04 | Manifest | 单次首包；WAITING 泄露 = 0；分档预算；`manifest_prefix_hash` CI 断言；组装 p95 ≤ **20 ms**（`PAR-09`） | 四步序 85 行组装实测 **0.3 ms**（0.05/0.07/0.05/0.04/0.04） |
| ACC-05 | 长会话 | 50 轮前台 token 不随轮次线性增长；萃取 crash/retry 不重不漏；第 30 轮召回第 3 轮人名原话 | 契约前提：M0-028（Conversation/Turn/ExtractionSpan）未冻结前不可测 |
| ACC-06 | 摄入 reduction | 50/100 Hz feed 不逐点入长期库；平稳 2 h 心率 = 1 均值点 + 异常独立；报告压缩比/异常召回/长期行数；保留 10k 吞吐测试 | 宪法口径单用户 **1,090 行/日 → 397,850 行/年 ≈ 280 MB**（含投影 **361 MB**）；测试规范建议规模为其 **1.8~9.2 倍** ⇒ 必须声明"条"的含义 |
| ACC-07 | 摄入提交 | 批次 = 一个 world_revision；逐条提交路径必须显式声明 group commit 与 fsync 代价 | 单条提交 `FULL` **0.47 ms/次**、`NORMAL` **0.09 ms/次**（容器 FS 下限）；830 观测/日逐条 = **1.7~12.5 s/日**（真实闪存 2~15 ms/次外推） |
| ACC-08 | 保留与删除 | LLM 无不可逆删除权限；被引用数据不可删；删除 = tombstone + 隔离期 + 审计 + 人工/策略 Gate；声纹模板可撤回/轮换/删除且引用不断裂 | 元裁决 H-03、§5.2；关闭宪法 §33.5 与第二十五/九十三/一百一十六条的内部冲突 |
| ACC-09 | 回溯标注 | 历史 `object_revisions` 无 UPDATE/DELETE（架构测试）；默认当前读 + 显式 as-of 读双通过 | 元裁决 H-04/H-05；as-of 单对象回读已是索引 seek（实测点查 **0.011 ms**） |
| ACC-10 | 有界传播 | typed/有界/可暂停/可续跑/读时校验；超节点单次 ≤ 预算化量级；复核 token 有日上限；封存章节只追加 postscript | 现状 **9.3 s / 51,822 对象 / 15.55 M token**；预算化 **10.82 ms**；懒传播 **0.82 ms** |
| ACC-11 | 延迟遥测 | TTFU/TTFT/TTFAudio/FinalUsefulLatency 分段 P50/P95/P99；冷/热与 Mock/真实模型分栏；**无数据不得宣称保障 1 秒** | 存储段已测（看板 0.3 ms / 点查 0.011 ms / 投影检索 7~47 ms）⇒ 1 秒预算主消耗在模型与 ASR/TTS，须分段实测 |
| ACC-12 | 输出契约 | 日常默认 1~3 句；安全/无障碍/用户要求展开例外；`IGNORED` 与 `NOT_PERCEIVED` 分开统计 | 本报告增量：二者混计会系统性污染第九十七条接受率，并与冷却自适应叠加成永久沉默 |
| ACC-13 | 预算账本 | 日/周 × 类别可查；超支按策略降级并接 `BUDGET_EXHAUSTED` | 年度账 **68.6 M in / 7.3 M out**；对话 56.6% / 金字塔 21.7% / 清洗 17.7% / 心跳 4.0%；中端档 ≈ **$316/用户/年** |
| ACC-14 | 投影合法性 | 投影可全量重建且与主库**逐条一致**；带 `index_watermark`；失配返回 `STALE_INDEX`；存储增幅有预算 | 实测 missing=0 / extra=0；存储 **+29%**（704.8→906.7 MB）；重建 3.6 s（倒排）/ 13.2 s（时间桶） |

### 4.7 可测参数登记表 `PAR-01~PAR-15`（第七十六条要求；一律为默认值，可实验调整）

| 编号 | 参数 | 默认值 | 来源条款 | 备注 |
|---|---|---|---|---|
| PAR-01 | 前台活跃窗口 token | 1500 | §85 L1112 | 与 PAR-02 联动，按模型 profile 调 |
| PAR-02 | 前台活跃窗口轮数 | 5~8 轮 | §85 L1112 | 不得实现为硬编码常量 |
| PAR-03 | 长平稳心跳间隔 | 3~5 h | §80 L1041 | 结合用户作息；反馈驱动可调，**设上下界** |
| PAR-04 | 震动应答检测窗口 | 5~10 s | §98之一 L1320 | 超时补发语义：URGENT 可重发，ROUTINE 进未读胶囊 |
| PAR-05 | 声纹模板留存期 | 由 retention class 决定 | §33 L470 | **不写死 6 个月**（元裁决 §5.2）；模板可撤回/轮换/删除 + tombstone |
| PAR-06 | 看板分档 token 预算 | SAFETY ≤512 / ROUTINE ≤2K / REVIEW ≤8K | §84/§86 | E 提议，标为实验默认值 |
| PAR-07 | `co_search` p95 | ≤50 ms @1M | §89 | 必须带 profile（硬件/规模/冷热/schema 主体） |
| PAR-08 | `time.*` 宏观档 p95 | ≤20 ms @1M | §87 | 1y 档需二级年桶（as-built 实测 112.48 ms） |
| PAR-09 | Manifest 组装 p95 | ≤20 ms | §84 | as-built 实测 0.3 ms，余量充足 |
| PAR-10 | 传播预算 | 深度 ≤2 / 节点 ≤500 / 单次 ≤10.8 ms / 日 token 上限 | §49/§93 | as-built 实测依据 |
| PAR-11 | 日常输出句数 | 1~3 句 | §14之一 L142-146 | 例外：安全、无障碍、用户明确要求展开、复杂操作步骤 |
| PAR-12 | IMU 入库粒度 | 宏观运动状态 + 显著波形特征 | §33.1 | **禁止 50/100 Hz 逐点入库** |
| PAR-13 | 心率平稳期聚合窗 | 2 h | §33.1 | 平稳期只记 1 个均值点 |
| PAR-14 | 清洗隔离期 | 30~90 天（按类型/风险/授权/容量/legal hold） | §33.5 | 元裁决 §5.2：不写死单一时长 |
| PAR-15 | 首字响应目标 | 1 s，拆为 TTFU/TTFT/TTFAudio/FinalUsefulLatency | §85 L1100 | 元裁决 H-13：无端到端测量不得宣称保障 |

### 4.8 明确**不进入**母表的项（元裁决驳回清单映射，防止团队照 D/E/F 原文执行）

| 被驳回的原判词/原建议 | 出处 | 元裁决裁定 | 母表处理 |
|---|---|---|---|
| "10 项机制工程覆盖率全部为零" | F | 驳回 #3：改判"局部能力存在，V3 语义/owner/Gate 大面积缺失" | 母表每项必须标 KEEP/UPGRADE/REWRITE/SPLIT，不得写"零覆盖" |
| "逐步过滤 = N 次模型往返 = 正面违宪" | E | 驳回（L209）：M1-012 可单次 `world.search` 内部 query planning | M1-012 保留 fallback，只新增 `co_search` 原子入口 |
| "多轮工具调用本身违宪" | E/F 语气 | 驳回 #10 | M2-012 重写而非废除 |
| "1 秒已证明可达" / "物理不可能" | C / B | 驳回 #4 | ACC-11 + PAR-15：分段实测，无数据不得宣称 |
| "震动先导因果链已保证零误触" | 宪法语气 | 驳回 #6 | M2-021 验收只写"无 epoch 时开启次数 = 0" |
| "声纹永不淘汰" | E M1-017 | 改写（§5.2） | M1-019：模板可撤回/轮换/删除 + tombstone，引用不断裂 |
| "1~3 句绝对规则" | 宪法语气 | 改写（§5.2） | M2-023 + PAR-11：日常默认 + 四类例外 |
| "删除 M1-001 的 10k 心率吞吐验收" | E | 改写（§5.2）：保留吞吐测试，但输出须经 reduction | M1-001 修订验收，不删除测试 |
| "TODO 永不做周期复查" | E/F 语气 | 改写（H-19） | M2-005/006：允许机械复查，禁止 LLM 全表盘点 |
| "`p95 < 50ms` 写入宪法" | C/F | 改写（§5.2） | 写入 TEST V0.2 profile，宪法只要求"有量化 SLO + 退化策略 + 版本化 profile" |
| "一个 sprint 可修完 / 三个对象只是 schema 工作量" | F | 驳回 #11 | 母表不给工期承诺，只给 Gate 顺序与前置依赖 |
| "把 D/E/F 编号原样叠加" | 三份审计 | 驳回 #12 | §3 仲裁表为唯一编号来源 |
| "因 V3 缺口追溯宣告既有 R2 M0 测试全部无效" | — | 驳回 #14 | M0 已验证能力（ID/append-only revision/三类时间/幂等/引用完整性/状态机）**保留有效** |

---

## 5. as-built 实测验收值登记表（核心交付物 C：**唯一可引用的数字来源**）

### 5.1 仓库内三套探针的性质区分（必须先分清，否则 SLO 会被误引）

| 探针 | 测量主体 | 规模 | 证据是否入库 | 可引用范围 |
|---|---|---|---|---|
| **A** `reviews/architecture/evidence/aios_v3_sqlite_probe.py` + `..._3_6m_result.json`（commit `cf4e9f6`） | **自建优化 schema**：FTS5 预分词列 + 归一化倒排表 + 预聚合 rollup + 独立依赖表 | 3,600,000 对象 / 3,959,999 依赖 / 663,812 postings / 17,520 rollup | ✅ 脚本 + JSON 均入库 | **"某类实现路径可行/不可行"的上限参考**。A 自己的 disclaimer 明确：`Synthetic single-user structural SQLite microbenchmark; not an AIOS implementation benchmark, wearable benchmark, cold-cache result, or SLO proof.` |
| **本审计** `reviews/architecture/evidence/aios_v3_as_built_probe.py` + `.log` + `_result.json` + `_environment.txt` + `_SHA256SUMS`（commit `cc66e13`） | **as-built 冻结 M0-017 schema**：`payload_json` blob + 仓库现有的 3 个索引；另建派生投影作对照组 | 1,000,000 revision / 2,211,817 依赖边 | ✅ 五件套齐全，`sha256sum -c` 通过 | **"今天照现有任务书施工会得到什么"的现状值**。结构性数字（行数/体积/B每行/命中数/postings/扇出/token 账）由固定种子决定，跨次运行**完全一致**；时延类 ±10% 抖动，本表取自入库日志那一次 |
| **B** 报告正文内联探针（`reviews/constitution/AIOS_v3.0_独立评审报告_2026-09-15.md` L389-401） | 自建（完整 DDL 未在库内） | 500,000 / 1,000,000 | ❌ **无脚本、无 JSON**，仅正文内联 | **不可作为 SLO 依据**。元裁决 L216 已判定：「50/100 万数字来自 B 的未入库探针输出，E 没有新增脚本/JSON，不能再记一轮独立实测」。只可作方向性旁证 |

### 5.2 可引用数字表（写进 Issue 验收时**必须**注明主体与 profile）

**（a）as-built 现状值 —— 本审计探针，profile：2 vCPU / SQLite 3.40.1 / WAL / 容器 FS / seed 20260915 / 1M revision**

| 指标 | 值 | 用于哪个 Issue/门 |
|---|---|---|
| 库体积 / 每行 | **704.8 MB / 739 B** | ACC-06、M1-020 |
| 批量写入吞吐（`synchronous=FULL`, batch=10k） | **42.6k~59.7k 行/s**，总写入 23.5 s | M1-017 |
| **单条提交 fsync**（1 Observation = 1 world_revision） | `FULL` **0.47 ms/次**（2,146/s）；`NORMAL` **0.09 ms/次**（10,902/s） | ACC-07、M1-017（group commit 要求） |
| 点查（`object_id` + revision） | **0.011 ms** | ACC-04、ACC-09 |
| 类型+主体计数（80,340 行） | 4.9 ms | M1-010 |
| `learned_at` 单日计数（2,725 行） | **0.2 ms** | M1-010（对照：索引列 vs payload 列） |
| 最近 50 条观测（index seek） | **0.1 ms** | ACC-04 |
| **Cockpit Manifest 四步序组装（85 行 payload）** | 0.05/0.07/0.05/0.04/0.04 → **合计 0.3 ms** | ACC-04、M2-009 |
| **三词共现（`payload_json LIKE`，as-built 唯一可行路径）** | **1,282.8~1,357.9 ms/次**（命中 3,359/65/7/9） | ACC-01、M1-012 重写理由 |
| **`json_extract(occurred_at)` 时间窗** | **1,201.4~1,468.6 ms/次，与窗口大小无关**（1d/1w/1m/1y 命中 2,642/19,157/82,045/670,652） | ACC-02、M1-010 升级理由 |
| FTS5 `unicode61 MATCH '妈妈'` | **0 命中** | ACC-01、M1-018 |
| FTS5 `trigram MATCH '女朋友'`(3字) / `'妈妈'`(2字) | 2,925 命中 / **0 命中且不报错** | ACC-01（零命中必须显式 `no_hits`） |
| FTS5 预分词列 `MATCH '妈妈 AND 生日 AND 礼物'` | **0.87 ms / 16 命中** | ACC-01、M1-018 |
| 20 万短文本 unicode61+trigram 索引体积 / 构建 | **45.9 MB** / 1.54~2.09 s | M1-021 存储预算 |
| 倒排投影（postings / 构建） | **482,345 / 3.6 s** | M1-021 |
| 时间桶投影（1M 行 / 构建） | **13.2 s** | M1-021 |
| 投影存储增幅 | **+29%**（704.8 → 906.7 MB） | ACC-14、M0-032 |
| 投影后共现（GROUP BY 交集形状 / 最稀有词驱动 EXISTS） | **43~200 ms** / **7.29~47.18 ms**（驱动词基数 5,878~28,695） | ACC-01 |
| 投影后时间桶滑动（1d/1w/1m/1y） | **0.66 / 3.86 / 14.40 / 112.48 ms** | ACC-02（**1y 档需二级年桶**） |
| 投影结果与 LIKE 全表扫描一致性 | **逐条一致（missing=0, extra=0）** | ACC-14 |
| **依赖传播：M0 现状全量内存扫描** | **9.3 s → 51,822 受影响对象**（2,211,817 边） | ACC-10、M3-001/M3-016 |
| 依赖传播：索引无预算 | **231.9 ms / 同 51,822（深度 8）** | M3-016 |
| 依赖传播：索引预算化（500 节点/深度 2） | **10.82 ms** | PAR-10、ACC-10 |
| 依赖传播：懒传播（只标直接依赖） | **0.82 ms / 20,000** | PAR-10 |
| 普通实体对照 | 7,093 对象 / 17.87 ms | M3-016 |
| **复核 token 代价** | 枢纽 **15.55 M**、普通 **2.13 M** | ACC-10、ACC-13、M2-025 |
| 边表构建 / 同规模 Dependency 落库 | 7.5 s / 23.7 s | M3-001 |
| **一年期资源账** | 830 观测/日 + 260 派生 = **1,090 行/日 → 397,850 行/年 ≈ 280 MB**（含投影 **361 MB**） | ACC-06、TEST V0.2 规模表拆列 |
| **一年期 token 账** | **68.6 M in / 7.3 M out**；对话 56.6% / 金字塔 21.7% / 每日清洗 17.7% / 心跳 4.0%；中端档 ≈ **$316/用户/年** | ACC-13、M2-025 |
| 扫描律 | 全表扫描成本 **∝ payload 总字节**，实测吞吐 ≈ **500 MB/s** | 一切外推的唯一依据 |
| 全程运行时间 | 2 m 14 s | 复现成本参考 |

**（b）自建优化 schema 上限参考 —— A 探针，profile：SQLite 3.40.1 / WAL / `synchronous=NORMAL` / 3.6M 对象（warm）**

| 指标 | p50 / p95 | 用途 |
|---|---|---|
| 有索引近期时间片 | **0.102 / 0.155 ms** | 证明"投影 + 索引"路径的量级 |
| 单维一年逐日聚合（有过滤，现算） | **24.224 / 25.489 ms** | ACC-02 的反面教材 |
| 读预聚合 rollup（同 365 个结果） | **0.135 / 0.204 ms** | ACC-02：**同为 365 结果差约 180 倍** |
| FTS5 三词 AND（预分词中文） | **0.136 / 0.167 ms** | ACC-01 上限参考 |
| 归一化倒排三词交集 | **2.047 / 2.137 ms** | ACC-01 上限参考 |
| **反向依赖超节点物化** | **133.276 / 137.755 ms，360,004 受影响** | ACC-10：一跳标记廉价，全量物化百毫秒级 |
| 有界遍历（深度 4 / limit 10001） | **0.215 / 0.27 ms** | PAR-10：有界策略有效的直接证据 |
| CJK 分词探针 | `continuous_chinese_match_rows = 0`（仅人工空格预分词行命中 1） | ACC-01：与本报告 P5 **双实测印证** |
| 库体积 / 建库 | **1.81 GB** / 84.3 s | M1-020 的 360 万档基线 |
| WAL 旧读者 | 存在旧读者时 WAL **416,152 B** 且 passive checkpoint **0 页**；读者释放后 truncate 归零 | M1-020 的 WAL 长 reader 测试设计 |

### 5.3 **不可引用**数字表（当前仍散落在 E 的整改建议里，必须替换）

| 出现在 | 数字 | 实际来源 | 处置 |
|---|---|---|---|
| E L157、L322（M1-012 验收） | 无索引 LIKE 三词共现 **319 ms@50万 / 654 ms@100万**；FTS5 预分词 **4.2 ms**；倒排三表 JOIN **31.3 ms**（1,248,910 postings） | B 的**未入库**内联探针 | **不得写入 Issue 验收**。替换为 §5.2(a) 的 as-built 值（1,282.8~1,357.9 ms / 0.87 ms / 7.29~47.18 ms）+ §5.2(b) 的 A 上限值（0.136 ms / 2.047 ms） |
| E L325（M1-010 验收） | 现算按月分桶 **369 ms@100万**；预聚合 **0.135 ms@360万** | 前者为 B 未入库探针；后者为 A 入库 JSON | 前半替换为 as-built `json_extract(occurred_at)` **1,201.4~1,468.6 ms**；后半保留（A 可引用） |
| E L180 | 50万行 **273 MB**、100万行 **628 MB** | B 未入库探针 | 替换为 as-built **704.8 MB@100万（739 B/行）**；360 万档保留 A 的 **1.81 GB** |
| F L176（M1-018 SLO） | 「3.6×10⁶ 记录关键词路径 p95≤50ms【平行审查探针已实证可行】」 | 引 A 的**自建 schema** | 结论方向正确但**表述必须加主体**：A 证明的是"自建优化 schema 上 p95 = 0.167 ms（FTS5 预分词）/ 2.137 ms（倒排交集）"，**不是** as-built schema 上可达 50 ms。as-built 上必须先落 M0-032 + M1-021 才可能达标 |

### 5.4 三组数字为何不矛盾（以及 SLO 的正确写法）

同一"三词共现"在三份材料里有三个数量级不同的值，这**不是**谁测错了，而是测量主体不同：

1. **列不同**：B 的时间窗测试用 `GROUP BY substr(learned_at,1,7)` —— `learned_at` 是**顶层索引列**；本审计用 `json_extract(payload_json,'$.occurred_at')` —— `occurred_at` 在 **payload 内、无索引**。而第八十七条的滑动条按语义必须切 `occurred_at`（事情发生时间），不是 `learned_at`（系统得知时间）。⇒ **B 的 369 ms 系统性低估了宪法要求的查询**，本审计的 1.2~1.5 s 才是 as-built 真值。这一点对 M1-010 的验收设计是决定性的。
2. **payload 密度不同**：B 628 B/行 vs 本审计 739 B/行；按扫描律（成本 ∝ 字节），同等查询在两种语料上必然不同。⇒ SLO 必须绑定"每行 payload 字节分布"。
3. **语料 postings 密度不同**：B 50万行产生 1,248,910 postings（2.5/行），本审计 1M 行产生 482,345 postings（0.48/行，关键词抽取更保守）。⇒ 交集代价与语料关键词分布强相关，SLO 必须绑定语料 profile。

**SLO 正确写法（强制模板，写进 TEST V0.2 §16 与每个 Issue 验收）**：

```text
<指标> 在 profile <硬件/CPU 数/SQLite 版本/journal_mode/synchronous/冷热> 
       × <规模：行数 + B每行 + postings 密度> 
       × <schema 主体：as-built 冻结 schema | 含派生投影 | 自建优化 schema> 
       × <查询形状：关键词数、时间窗、top_k> 
下 P50/P95/P99 = <值>；未达标时退化策略 = <fallback 行为 + 返回的错误码>。
```

任何缺少上述五个绑定之一的性能承诺（包括宪法原文的"毫秒级""秒级""1 秒首字""绝不算力雪崩"）都**不得**写入验收，只能写"待分层实测"（元裁决 H-13、驳回 #4/#5）。

---

## 6. 五张可直接派单的 12 要素 Issue 卡片

> 按宪法第一百一十三条(L1545-1560)的 12 要素编写。其余 Issue 的卡片由 owner 按同一模板补全，母表（§4）已给出关键输出与验收。

### 6.1 M0-023 V3 Authority & Traceability Freeze（Gate 0 第一张单，阻断其余全部）

| 要素 | 内容 |
|---|---|
| 1 任务编号 | `M0-023`（来源：D M0-023 + E §9.6 + F §3.6） |
| 2 目的 | 让"从宪法到 Issue"的授权链**唯一且可追溯**。现状：【总工任务书】L4240-4257 的派单链是 `宪法2.0 + R1 + R2 + 三份规格 → GitHub Issues → 代码`，**v3.0 不在链上**；同时 `MOD-C05/C06/C09/C10` 在宪法(L1452-1463)与架构规划(L88-97)中定义互斥，里程碑存在 M0~M6 与 M0~M8 两套口径 |
| 3 输入 | `AIOS核心系统宪法v3.0.md`（1720 行）+ v3.0.1 修正案（对 C-01~C-12 的唯一规范文字与决议号）+ 四份工程文档 + 本报告 §3 仲裁表 |
| 4 输出 | `governance/v3_authority.json`：v3.0 文件 SHA256、`MOD-C01~C14` 唯一映射、`M0~M8` 唯一映射、旧 API→V3 API 兼容表、`ACC-*`/`TS-*`/`PAR-*`/`WB-*`/`ARCH-*` 命名空间注册表；`governance/v3_traceability_matrix.csv`：条款→module→契约→Issue→test→gate |
| 5 接口 | `scripts/freeze_authority.py --constitution <path> --out governance/`；`scripts/check_traceability.py --fail-on CONFLICT,UNMAPPED` |
| 6 数据结构 | 上述 JSON/CSV 的 schema；每条矩阵行含 `clause_id, clause_line, module, contract_issue, impl_issue, test_id(TS-*), acc_id(ACC-*), gate, status ∈ {MAPPED, CONFLICT, UNMAPPED, DEFERRED}` |
| 7 前置依赖 | v3.0.1 修正案发布（对 C-01~C-12 给出唯一文字）；本报告 §3 仲裁表被采纳 |
| 8 禁止行为 | 禁止手工长期维护行号（元裁决 L186：改版后必须由矩阵自动生成）；禁止在本 Issue 内顺手修改任何契约代码；禁止保留两套 `C0x` 或两套里程碑口径；禁止用裸 `V` 前缀新增编号 |
| 9 单元测试 | 命名空间注册表的唯一性测试（同一 ID 不得出现两次）；矩阵生成器的幂等性测试 |
| 10 集成测试 | `check_traceability.py` 在 CI 中对全仓 Issue 与测试文件运行，**`CONFLICT = 0` 且 `UNMAPPED = 0`** |
| 11 验收场景 | 不适用（治理 Issue）；其产出是 `TS-*`/`ACC-*` 的注册前提 |
| 12 已知限制 | 不解决 v3.0 条款自身的矛盾（那是 v3.0.1 修正案的职责）；不评估工期与人力 |

### 6.2 M0-032 派生投影合法化与 schema 扩展（关闭"宪法禁止自己要求的性能"）

| 要素 | 内容 |
|---|---|
| 1 任务编号 | `M0-032`（来源：本报告新号 + E M0-017 升级） |
| 2 目的 | 第十八条第 3 款「绝对禁止数据冗余拷贝」与第八十九条/第九十五条「全局索引深度覆盖、毫秒级共现召回」构成**双向违宪**：审计者可用前者否决倒排索引，实现者可用后者绕过前者。必须在契约层给出"派生投影"的合法身份 |
| 3 输入 | M0-017 冻结 schema（`object_revisions` 等 5 表 3 索引）；as-built 探针实测（§5.2a） |
| 4 输出 | ①宪法层定义：`Derived Projection` = 可从 revision 全量重建、不参与真相、带 `index_watermark`、失配返回 `STALE_INDEX`、**不计入冗余拷贝禁令**；②schema 扩展：`keyword_posting`、`alias_synonym`、`time_bucket_rollup`（日/周/月/**年二级**）、`tombstone`、`budget_ledger` |
| 5 接口 | `storage/schema_v3.py`（DDL）；`index.rebuild(projection, from_revision)`；`index.status() -> {projection, index_watermark, lag}` |
| 6 数据结构 | 每张投影表含 `source_watermark_revision`、`built_at`、`builder_version`；`time_bucket_rollup` 含 `bucket_kind ∈ {DAY, WEEK, MONTH, YEAR}`（**年档必须独立物化**，见 ACC-02） |
| 7 前置依赖 | M0-023（编号与条款映射）；M0-031（双时态不变量，投影必须能按 as-of 重建） |
| 8 禁止行为 | 禁止把投影作为真相来源；禁止投影参与 Claim 置信度计算；禁止无水位投影；禁止把向量索引当唯一真相存储（沿用 M1-014 的既有禁令）；禁止年档用日桶求和代替年桶 |
| 9 单元测试 | 全量重建后与主库**逐条一致**（as-built 已实测 missing=0 / extra=0）；水位落后时 strict 查询返回 `STALE_INDEX` |
| 10 集成测试 | 删除全部投影 → 重建 → 查询结果与删除前一致；重建期间并发读不阻塞（WAL） |
| 11 验收场景 | `TS-037`（中文多关键词共现）、`TS-038`（5D/LOD）；门 `ACC-01`、`ACC-02`、`ACC-14` |
| 12 已知限制 | 存储增幅必须登记为预算：as-built 实测 **+29%**（704.8→906.7 MB / 1M 行）；构建代价 3.6 s（倒排）/ 13.2 s（时间桶）；本 Issue 不实现向量兜底 |

### 6.3 M1-018 Chinese Hybrid Co-search Engine（第一个做不出宪法指标的 Issue 的解药）

| 要素 | 内容 |
|---|---|
| 1 任务编号 | `M1-018`（来源：D M1-018 + F M1-018/M1-019 + E M1-012 实现部分） |
| 2 目的 | 第八十九条要求 `[妈妈, 生日, 礼物]` 一次调用取拓扑交集共振区并"毫秒级形成完整决策支持"。as-built 现状是 **1,282.8~1,357.9 ms/次**，且 FTS5 默认分词对连续中文 **0 命中**、`trigram` 对 2 字词 **0 命中且不报错**（宪法示例全为 2 字词） |
| 3 输入 | M0-032 的投影表；分词器与词典（版本冻结）；别名/同义词表；实体 postings |
| 4 输出 | `world.co_search(keywords[], time_range, dims[], top_k, budget) -> {hits[], score, why_matched[], coverage, index_watermark, omitted_count, fallback_used}` |
| 5 接口 | `query/co_search.py`；工具层由 M2-010 暴露给模型（受 capability 与最小权限约束） |
| 6 数据结构 | `CoSearchRequest/CoSearchResult`；`why_matched` 为每命中项给出 `{keyword, node_type, node_ref, matched_via ∈ {ENTITY_ALIAS, POSTING, FTS, VECTOR_FALLBACK}}` |
| 7 前置依赖 | M0-032（投影）、M1-021（投影层维护）、M1-002（实体/别名解析）、M1-022（排序契约） |
| 8 禁止行为 | **禁用 `unicode61` 裸用作中文召回**；`trigram` 仅作 ≥3 字补充；禁止把"零命中"静默返回空数组（必须显式 `no_hits` + 分词诊断）；禁止共现交集直接升级为因果事实（元裁决 H-07：只产生候选/假说）；禁止以多次单词检索拼装冒充原子 `co_search` |
| 9 单元测试 | 连续中文召回 > 0；2 字词召回 > 0；别名例（妈妈=母亲=我妈=P003）同召回；否定句与角色错位例；零命中例返回 `no_hits` |
| 10 集成测试 | `[妈妈,生日,礼物]` **单次调用**返回历年礼物事件 + 反馈原话切片 + 消费账单 + 当前心愿 Claim，且每项可下钻至原始证据；partial index（水位落后）下行为可预期 |
| 11 验收场景 | `TS-037`；门 `ACC-01`（p95 ≤ `PAR-07`=50 ms @1M，profile 按 §5.4 模板书写） |
| 12 已知限制 | as-built 可达路径的实测参照：预分词 FTS **0.87 ms**、最稀有词驱动 EXISTS **7.29~47.18 ms**、GROUP BY 交集 **43~200 ms**；A 的自建 schema 上限为 **0.167 ms / 2.137 ms**。向量兜底不在本 Issue；360 万档由 M1-020 复测 |

### 6.4 M2-009（重写）Cockpit Manifest 聚合组装器

| 要素 | 内容 |
|---|---|
| 1 任务编号 | `M2-009`（重写；来源：D REWRITE + E M2-009 + F G-01/G-18/G-21） |
| 2 目的 | 第八十四条要求**一次性**交付统一看板并冻结四步序为不可颠倒的心智启动；现状 M2-009 只给"相关摘要 + 索引入口"，无四步序、无预算、无就绪过滤、无确定性序列化，且【工作台规格】§10 的十三步顺序（世界→自身）与四步序（自身→羁绊→姿态→世界）**倒置** |
| 3 输入 | Wake（原因/合并次数/优先级）、安全状态、AI 自身世界切片（Identity/Promises/Growth）、`DIM_AI_RAPPORT`、当前时空与主事件、Capability Registry、**就绪任务清单**（调 M2-024 `task.inspect_ready()`）、会话与萃取水位 |
| 4 输出 | `CockpitManifest`：分档 token 预算（`PAR-06`）、四步序审计字段（`self_state / rapport_state / stance / focus`）+ 安全 Step-0 前置、每项带 `freshness / source_ref / revision_age`、`omissions[]`（被省略内容的数量与查询入口）、`manifest_prefix_hash`、组装 envelope（供回放） |
| 5 接口 | `workspace.open(session_id | wake_id) -> CockpitManifest`（**单次首包**，不分段 onboarding） |
| 6 数据结构 | M0-029 冻结的 `CockpitManifest` 契约；envelope 含 refs/版本/水位/排名解释/省略/预算/模型与策略版本 |
| 7 前置依赖 | M0-029（契约）、M0-026（`DIM_AI_RAPPORT` seed 维度）、M2-024（就绪判定）、M3-010（羁绊维度数据） |
| 8 禁止行为 | 禁止分段 onboarding 式多轮提示（第八十四条 L1075-1076）；禁止 WAITING 任务进入上下文；禁止把自然语言大摘要作为唯一入口（沿用现有 M2-009 禁令）；禁止要求模型复述看板或发表空洞分析（第八十六条第 1 款）；**禁止要求模型输出或持久化私有思维链**（元裁决 §5.2：只冻结可观察不变量与审计字段）；禁止非确定性序列化（会破坏 KV 前缀缓存亲和性） |
| 9 单元测试 | 同输入 → 同 `manifest_prefix_hash`；WAITING 任务泄露数 = 0；预算超限时按档裁剪并写 `omissions` |
| 10 集成测试 | 不同 Wake Reason 下 manifest 内容显著不同（V3-03）；回放可精确复现"当时模型看到了什么"；安全 Wake 不被人格步骤阻塞（`TS-032`） |
| 11 验收场景 | `TS-031`、`TS-032`、`TS-036`；门 `ACC-04`（组装 p95 ≤ `PAR-09`=20 ms；as-built 实测 85 行四步序 = **0.3 ms**） |
| 12 已知限制 | 组装性能不是瓶颈（实测 0.3 ms），本 Issue 的难点在**内容选择、预算与省略说明**；不实现 L1 回捞（属 M2-018）；不实现输出风格契约（属 M2-023） |

### 6.5 M2-024 Trigger Eligibility Engine & Ready Queue（消除 Token 空转）

| 要素 | 内容 |
|---|---|
| 1 任务编号 | `M2-024`（本报告新号；来源：E/F 的 `M2-016` 语义，D 的契约部分在 M0-027） |
| 2 目的 | 第八十六条第 2 款要求待办任务带显式触发条件、未就绪任务**静默休眠**、严禁每次醒来无脑遍历。现状：`time_reached/context_matched/event_occurred/dependency_ready` 在四份工程文档命中 **0**；WB:L227 与 TASK:L2225 明写"待办必须进入定期任务盘点"；契约层 `Task.completion_condition` 是无类型 `dict`（`models.py:338`）⇒ 既不可编译也不可索引 |
| 3 输入 | M0-027 冻结的 `TriggerExpression` AST；Observation 提交事件流；Task 表；订阅键索引 |
| 4 输出 | `task.create_conditional(condition, action)`、`task.inspect_ready() -> ReadyTask[]`、ready queue、条件求值审计（三值 `TRUE/FALSE/UNKNOWN` + 依据）、饥饿审计报告 |
| 5 接口 | `tasks/eligibility.py`；供 M2-005 调度器与 M2-009 看板消费 |
| 6 数据结构 | `TriggerExpression`（`TimeReached/EventMatched/ObservationPredicate/DependencyReady/AllOf/AnyOf/Not`）、`subscription_key`、`expiry`、`stale_after`、`hysteresis/debounce`、`condition_version` |
| 7 前置依赖 | M0-027（契约）、M2-002（机械触发引擎，复用其确定性 rule evaluator）、M2-007（Watch 两层条件与三值结果，**提升为全任务一等条件**） |
| 8 禁止行为 | **禁止 `eval` 或任意 Python 表达式**；禁止在求值器内做语义判断（沿用 M2-002 禁令：语义结论 0 个来自 trigger engine）；禁止 WAITING 任务进入模型上下文；禁止周期性 LLM 全表盘点（元裁决 H-19：允许便宜确定性**机械**复查）；禁止全表扫描求就绪 |
| 9 单元测试 | 四类条件各自的求值与三值语义；DST/时区迁移/迟到事件/`UNKNOWN` 质量/抖动/`A AND B` 时间窗/循环依赖（`TS-036`）；条件永假检测；创建时可满足性 `dry_run` |
| 10 集成测试 | **10 万 WAITING / 10 READY**：就绪判定为索引查、等待期**模型调用 = 0**、无 Task 全表扫描（`TS-035`）；十类任务全部带条件 |
| 11 验收场景 | `TS-035`、`TS-036`；门 `ACC-03` |
| 12 已知限制 | 语义条件（如"是否出现持续学习挫败"）仍须由 Wake 后模型复核，求值器只做机械前置过滤；不实现预算账本（属 M2-025） |

---

## 7. 放行条件与结论

### 7.1 放行顺序（硬约束）

```text
v3.0.1 修正案（对 C-01~C-12 给唯一文字 + 采纳 §3 编号仲裁 + 派生投影定义 + as-of 读语义）
      ↓
Gate 0：M0-023 ~ M0-032（契约扩展；M0-022 的 BLOCKED 一并解除）
      ↓  ← 未过：停止新 M1/M2 派单；只允许做修正案、契约、迁移 fixture、测试夹具
Gate 1：M1-012 重写 + M1-017 ~ M1-022 + M1-010/M1-014 升级 + M1-001 验收修订
      ↓  ← 未过：禁止冻结查询 schema（M1-020 规模门是硬门）
Gate 2：M2-005/006/009/010/012 重写 + M2-016 ~ M2-025
      ↓  ← 未过：不得宣称"1 秒首字"、不得宣称"零浪费"、不得宣称"零误触"
Gate 3：M3-001 重写 + M3-004/005/010 升级 + M3-012 ~ M3-016
      ↓
M4-002/M4-004 修订 + M4-005（TEST V0.2 场景包，盲测前冻结）+ M4-006
      ↓
M5-004 → M6-005 → M7-002/M7-005 → M8-004 → M8-003 Gate → POST-M8-HW-001
```

### 7.2 最终判词

> **按现有四份工程文档直接实施，项目不会在某个里程碑"突然崩溃"，而是会在三个不同层面依次不可交付：**
>
> 1. **治理层——现在就不可派单**。【总工任务书】L4240-4257 的授权链上没有 v3.0；`MOD-C05/C06/C09/C10` 与里程碑口径各有两套；三份 Gap Audit 对 `M0-023 / M1-019 / M2-016 / M2-018 / M2-019 / M2-020 / M2-021 / M3-012 / V31` 等编号**同号异义**；`A01~A10` 一物两义。**审计首断点 = M0-V3 Gate**（与元裁决 §7.4 一致）。
> 2. **物理层——M1 就做不出宪法指标**。冻结 schema 上三词共现 **1.28~1.36 s/次**、`occurred_at` 时间窗 **1.20~1.47 s/次**（与窗口无关），而第八十九条要求"毫秒级"、第九十条要求"秒级因果召回"，**差 2~3 个数量级**；FTS5 默认分词对连续中文 **0 命中**、对 2 字词 **0 命中且不报错**，而宪法示例全是 2 字词 ⇒ **M1-012 会绿灯通过却交付一个静默零召回的检索引擎**。这是第一个"物理上交付不出来"的 Issue。
> 3. **验收层——M4 无法签收**。M4-002/M4-004 的验收写 `V01~V30覆盖`，而【测试规范】只定义到 V20，V21~V30 仅存在于宪法 L1610-1619 ⇒ **悬空验收引用**；R3-01~07 与 V3-01~03 两个家族在测试规范中命中 0，且其中 R3-03/R3-05/V3-01/V3-02/V3-03 所依赖的对象（Prediction / LifeChapter / CommunicationExperience）连冻结契约都没进 ⇒ **M4 Gate 的验收条件不可判定**。
>
> 若无视上述三层继续按现任务书编码，**第一个用户可观察的运行断崖在 M2**（条件任务空转、50 轮对话丢旧话题、无 1 秒体验度量、无关系心跳），**M3 是债务放大器**（as-built 实测：现状传播 9.3 s / 51,822 对象 / 15.55 M token vs 预算化 10.82 ms，差 **860 倍**）。

### 7.3 一句不留情面的话

四份工程文档的质量并不差——【总工任务书】对宪法 2.0/R2 的落地粒度（82 个 Issue、每个 10 段结构、10 条关闭条件）在同类项目里是罕见的细；【测试规范】的五基线双赛道与消融纪律甚至优于多数学术论文。**问题在于它们瞄准的是昨天的宪法，而今天仓库里已经有 4 份主审 + 3 份 Gap Audit + 1 份元裁决在讨论同一批缺口，却给出了三套互不兼容的 Issue 编号。** 现在最危险的动作不是"修得慢"，而是让三个团队各自照着 D、E、F 的编号开工——那样我们会得到三个都自称"M0-023 已完成"的分支，而 Gate 0 的第 8 项（`CONFLICT/UNMAPPED = 0`）将永远无法达成。

---

## 8. 附录

### 8.1 本报告引用的证据文件

| 文件 | 说明 | 完整性 |
|---|---|---|
| `reviews/architecture/evidence/aios_v3_as_built_probe.py` | as-built 独立探针（不 import 产品代码，仅用 M0-017 冻结 schema 原形） | `aios_v3_as_built_probe_SHA256SUMS` ✅ |
| `reviews/architecture/evidence/aios_v3_as_built_probe.log` | 完整运行日志（1M 行 / 1M 边，2 m 14 s），末尾含 `JSON_SUMMARY` | ✅ |
| `reviews/architecture/evidence/aios_v3_as_built_probe_result.json` | 机器可读结果（含 disclaimer 与环境字段） | ✅ |
| `reviews/architecture/evidence/aios_v3_as_built_probe_environment.txt` | 环境快照（内核/CPU/内存/Python/SQLite/磁盘 + 容器 FS 下限声明） | ✅ |
| `reviews/architecture/evidence/aios_v3_sqlite_probe.py` + `..._3_6m_result.json` | 报告 A 的自建 schema 探针（3.6M 对象） | 入库；本报告**不修改**，仅作上限参考 |
| `schemas/r2/m0_contract_snapshot.json` | `gate_version=M0-R2`、16 枚举、30 模型哈希、ObjectType 19 类、ErrorCode 11 项（含 `STALE_INDEX`/`BUDGET_EXHAUSTED`） | 仓库冻结件 |
| `src/aios_core/contracts/models.py` | `Observation.modality: str`(L31)、`Claim.valid_time`(L133)、`Task.next_wake_at/recurrence/completion_condition/cancel_condition`(L332-339) | 仓库冻结件 |
| `src/aios_core/contracts/enums.py` | `TaskType` 10 项(L97-107，无 `PREDICTION_CHECK`)、`WakeSource` 8 项(L125-133，无心跳/关系节奏) | 仓库冻结件 |
| `src/aios_core/storage/sqlite_store.py` | 5 表 3 索引、WAL + `synchronous=FULL` | 仓库冻结件 |
| `src/aios_core/dependency/graph.py` | `collect_impacted_dependents()` 自述 "deterministic in-memory contract helper, not the M3 persistent reverse index" | 仓库冻结件 |
| `TASK_PROGRESS_R2.md` | M0 16/22 FINAL PASS；M0-022 **BLOCKED**；M1~M8 未开始 | 仓库现状 |

### 8.2 与仓库内既有 8 份档案的关系

| 档案 | 本报告的关系 |
|---|---|
| **A** `AIOS_v3.0_CHIEF_REVIEW_PATCH_REQUIRED_2026-09-15.md`（6/10，C-01~C-12） | 元裁决指定为"统一修正案事实底稿"；其 3.6M 自建 schema 探针数字在本报告 §5.2(b) 作为**上限参考**引用 |
| **B** `reviews/constitution/AIOS_v3.0_独立评审报告_2026-09-15.md`（6.3/10） | 其内联探针数字**不入库**，本报告 §5.3 明确列为不可引用；其 read-side as-of 发现已被前一轮报告 §3.6 采纳并落入本报告 `M0-031` |
| **C** `CONST_V3.0_CHIEF_REVIEW_2026-09-15.md`（7.5） | 其 `co_search p95≤50ms` 被采纳为 `PAR-07`，但按元裁决 §5.2 **写入 TEST V0.2 profile 而非宪法** |
| **D** `AIOS_V3_ENGINEERING_GAP_AUDIT_PATCH_REQUIRED_2026-09-16.md`（41 gaps，V31~V45） | **本报告以 D 为底稿**（元裁决 §6.1-5）；§3.2 保留 D 的全部 Issue 语义，只为 E/F 的冲突项分配新号 |
| **E** `AIOS_v3.0_工程文档横向对齐断层审计_2026-09-16.md`（30 gaps） | 其 `A01~A10` 一物两义、定期盘点原文、10k 心率验收、盲测版本窗口四项**有效新增全部并入**（`ARCH-*`、M2-005/006、M1-001、M4-005）；其"逐步过滤必然等于多轮模型往返"判词按元裁决 L209 **不采纳**；其引用的 B 探针数字按 §5.3 替换 |
| **F** `CONST_V3.0_GAP_AUDIT_2026-09-16.md`（25 gaps） | 作为管理摘要有效；其编号方案按元裁决 §7.3 **不作为工程承诺**，本报告 §3.2/§3.3 给出其每项的归并去向 |
| **元裁决** `AIOS_V3_MULTI_REVIEW_META_AUDIT_NO_GO_2026-09-16.md` | 本报告**执行**其 §6.1 第 5 项与 §7.3 的强制交付物；H-01~H-21、§5.2 改写表、§5.3 十四条驳回全部落入 §4.8 与母表验收口径 |
| **前一轮报告** `AIOS_v3.0_CHIEF_REVIEW_R2_AS_BUILT_STRESS_PROBE_2026-09-15.md` | 本报告的实测数字全部来自其探针与日志；其 B1/B2/B3/G1/G2 与 Top 3（CORE-P1/P2/P3）在本报告中被**转译为可派单的 Issue**：CORE-P1→`M0-032 + M1-021 + M1-018`，CORE-P2→`M0-030 + M1-019 + M3-004/005`，CORE-P3→`M3-016 + M3-001 + M2-025` |

> 按元裁决 §0.2 的样本纪律，本报告**不计入独立评审票数**；它是元裁决点名的整改母表交付物。

### 8.3 引用行号索引（本次基线 `cc66e13`；文档改版后应由 M0-023 的追踪矩阵自动生成）

| 文件 | 关键行 |
|---|---|
| 【V3宪法】 | §14之一 L136-152；§25 L369；§29 L400；§31之一 L429；§33 L455-484；§49 L686；§50~53 L701-751；§76 L992；§78 L1013；§80 L1037-1051；§81 L1052-1054；§82 L1056-1062；§84 L1073-1091；§85 L1093-1147；§86 L1148-1189；§87 L1190-1205；§88 L1206-1211；§89 L1213-1226；§90 L1227-1233；§91 L1234-1250；§93 L1257；§95 L1280；§98之一 L1300-1331；§104之一 L1367-1410；§109 L1484；§113 L1589-1619（含 V21~V30 L1604-1619、12 要素 Issue 规范 L1545-1560）；§114 L1627-1701（A01~A10 L1633-1642、R3 L1680-1690、V3-01~03 L1692-1698）；C01~C14 映射 L1452-1463 |
| 【架构规划】 | L5 依据 v2.0；L24 手环不入关键路径；C01 L88；C06 L93；C09 L96；C10 L97（十三步循环）；§10 L276-286（M0~M6）；§12 L313-324（A01~A10） |
| 【总工任务书】 | L6 上位依据；M1-001 L1219-1265；M1-010 L1642-1688；M1-011 L1689-1735；M1-012 L1736-1782（FTS5 L1755）；M1-013 L1783-1829；M1-014 L1830-1876；M2-002 L2022-2068；M2-003 L2069-2115；M2-005 L2163-2209（L2178 调度输入）；M2-006 L2210-2256（L2225 todo next review、L2241 盘点测试）；M2-009 L2351-2397；M2-010 L2398-2444（L2437 禁止固定顺序）；M2-012 L2492-2538（L2503 十三步、L2511 不强制维度）；M3-001 L2684；M3-004 L2825；M4-002 L3252（验收 L3377 `V01~V30覆盖`）；M4-004 L3346-3396；M7-002 L3781-3827（L3796 benchmark）；上位依据 L4173-4180；派单链 L4240-4257 |
| 【工作台规格】 | L4 依赖第一份规格；§2 L20-40 PC 三栏布局；§3 L46-70 初始工作包 11 项；§4 L70-97 操作协议与错误码；§5.3 L138-152（L152 分阶段扩大召回）；§7.2 L220-232（L227 定期任务盘点）；§8 L267-280 两层条件；§10 L305-330 十三步；§14 L390-403 W01~W12 |
| 【测试规范】 | §2 L20-40 四层隔离；§5 L86-100（规模表 L92-96）；§8 L190-200 五基线；§9 双赛道；§10 L236-259（V01~V20）；§11 指标；§13 消融；§14 盲测纪律；§16 L391-430（L393 不得看结果改门）；§17 失败归因；§18 外部基准 |

### 8.4 交付物清单（本报告可直接被 v3.0.1 修正案采纳的部分）

1. **§3.2 Issue 同号异义消解表** —— 唯一编号来源，34 行定稿。
2. **§3.3 场景编号仲裁** —— `TS-001~TS-051`，`V` 前缀停止新增。
3. **§3.4 验收编号仲裁** —— `A*`/`ARCH-*`/`WB-*`/`R*`/`V3-*`/`ACC-*`/`PAR-*`/`MOD-C*`/`M0~M8` 九个命名空间的唯一归属。
4. **§4.1~4.5 统一整改母表** —— Gate 0(10) + Gate 1(10) + Gate 2(16) + Gate 3(8) + M4~M8 与文档(13) = **57 项**，每项带来源映射与阻断验收。
5. **§4.6 `ACC-01~ACC-14`** —— v3.0 专属工程门，全部绑定 as-built 实测值。
6. **§4.7 `PAR-01~PAR-15`** —— 可测参数登记表（第七十六条要求的载体）。
7. **§4.8 驳回清单映射** —— 14 条，防止团队照 D/E/F 原文执行已被元裁决驳回的判词。
8. **§5 实测值登记表** —— 可引用 / 不可引用 / SLO 书写模板三段，是"哪个数字能写进 Issue"的唯一裁判。
9. **§6 五张 12 要素 Issue 卡片** —— M0-023、M0-032、M1-018、M2-009、M2-024，可直接开单。

*— AIOS 核心系统总架构师 / 工程审计长，2026-09-16*
