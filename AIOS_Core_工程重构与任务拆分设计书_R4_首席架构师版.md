# AIOS Core 工程重构与任务拆分设计书（R4 · 独立首席架构师版）

**作者**：独立首席系统架构师与技术总监
**日期**：2026-09-16
**审阅范围**：《AIOS核心系统宪法v3.0.md》【V3宪法】、《AIOS Core 系统架构图与开发规划.md》V0.1【旧规划】、《AIOS_Core_详细开发任务拆分_R2_总工程师版.md》【旧任务书】、《AIOS认知工作台功能规格.md》《AIOS虚拟世界测试规范.md》、`src/aios_core/`（M0 实物）、`TASK_PROGRESS_R2.md`
**配套文件**：《AIOS宪法v3.0_首席评审报告》（`reviews/AIOS宪法v3.0_首席评审报告_2026-09-15.md`）——评审报告判罪，本设计书重建。
**地位建议**：采纳后，本文件成为**模块编号与调度语义的唯一账本**；旧规划 V0.1 归档废止；旧任务书保留为底稿，增量以"′"里程碑修订段挂接，不重开已 FINAL PASS 的 M0-001~021。

---

# 第一部分 · 独立诊断与重构主张

## 1.1 最致命断层：工程三件套根本不在同一个世界里

我先不谈任何认知科学，只摆四份仓库实物：

| # | 证据（可在仓库逐字核对） | 后果 |
|---|---|---|
| D1 | `TASK_PROGRESS_R2.md` 首屏写着 **`> 宪法基线：AIOS宪法2.0.txt + R1/R2`**；而 V3 宪法自述"唯一宪法基线" | 正在推进的 418 项测试与 22 个 M0 契约，冻结的是**旧宪法的世界**。V3 的十项机制在工程账本上没有一行对应契约 |
| D2 | 旧规划 V0.1 标注 **`依据：《AIOS核心系统宪法v2.0》`**，里程碑只有 M0–M6 七段；V3 宪法第 109 条是 M0–M8 九段 | 顶层规划从未随修宪升级。按旧规划施工= 做出一个宪法里不存在的系统 |
| D3 | **同编号异语义**：宪法第 108 条 C 表 C05=总结与人生章节、C06=认知与证据；旧规划 C 表 C05=事件认知总结、C06=世界查询。且第 108 条"14 组件"清单第 5 号是"世界搜索引擎"，C 边界表却**没有给检索任何模块** | 编号体系已分叉；检索是"有户口没住房"的孤儿组件。M0 的 B5/B6/B7/R4 三轮 REOPENED 已演示过"语义歧义烧成契约返工"的真实成本 |
| D4 | 宪法第 71 条 22 个一等对象 vs 第 109 条 M0"必须冻结项"只覆盖 15 类：**Summary、Prediction、LifeChapter、两类 Experience、ToolProposal 不在任何冻结清单**，却被 M3/M5 依赖、被 V3-03/R3 验收引用 | M1 开工第一天就踩在未冻结对象上写服务层，M3 前必然二次修宪 |
| D5 | 旧规划 §10 的交付门与宪法验收表（114 条 A/R1/R2/R3/V3）互不引用；性能基准全部压到 M7-002，而 M2/M4 的闭环每天都依赖检索 | 规划、任务书、验收三者没有对过账 |

**一句话诊断**：这不是"规划不够细"，是**修宪只改了法条，没改国家机构表**。任何编码代理按现状开工，实现的是宪法 2.0 的骨架 + v3.0 的口号。

## 1.2 我认定的四个致命断层（按杀伤力排序）

**F1 · 时态语义裁判缺席（宪法级矛盾的工程投影）。** 第 31 条之一"倒带给历史切片追加标注"与第 93 条"新认知只写在 T_now"互斥，第 71 条清单里没有承载回溯标注的对象。M0-020 的 `world_at(T)` 快照、M0-019 的 pinned 引用、M3-001 的传播引擎全部建立在"节点内容 + 知识截止"两元假设上；回溯标注以第三元形态进入时（第 81 条把它写成"必须"），M0-020 与 M0-005 的测试语义全部重写。

**F2 · 写入无分类 ⇒ 认知永动机 ⇒ 虚拟时钟冻结。** M2-002 原文"Observation commit 后把**变更摘要**投递 trigger engine"——它订阅 commit 流，不区分写入者。M3-001 纠错传播每轮都在写世界（标 STALE、建复核 Task，第 86.4 要求维护写走完整版本记录＝必然产生新 revision）。第 79 条触发源第 9 项"与任务依赖相关的**新资料到达**"。三者闭环：**修正→写→新资料→触发→唤醒→再修正**。第 64 条只禁"递归创建 Wake"，82 条只压"同源重复命中"，都拦不住"维护写冒充新资料"。`src/aios_core/storage` 今天没有任何 `source_class` 字段——宪法没立法、任务书没排产、代码没字段，三层同缺。

**F3 · 查询面被排成二等公民，性能闸门顺序排错。** 全部检索承诺（85 全局联想、89 毫秒级共现、87 下钻）压在 M1-012"FTS5 + alias index"一行字上：无规模验收、无 p95、无物理计划禁令；首次压测在 M7-002。但 M2-009 工作包、M2-012 工具循环、M4-001 三十天人生（6–30 万条）每天都在用检索，且 M4/M8 的科学结论反过来要靠这个从未压测过的读面产生。**在 M7 才发现检索不行 = 在验尸时才检查心脏。**

**F4 · 预算只有口号没有账房。** 第 85 条"1 秒"、第 86 条"零浪费"、第 53 条"防 Token 滥用"、第 114 条验收表——后者**一条延迟/成本阈值都没有**；M4-002 的"成本"是事后统计指标，不是运行时闸门。没有 gate 的规则等于没有规则：模型会超支、心跳会空转、STALE 积压会无界增长，而系统**无法在任何一次会话中知道自己超支了**。

## 1.3 不修就开工：最先崩溃点预测（具体到模块与场景）

**崩点①（M3 集成期引爆，V21b 场景暴露）——虚拟时钟冻结。** M2-014 日产 2k–10k 条观测 → 高频 commit 持续进入 trigger engine（无豁免）→ M3-001 传播标 STALE/建复核任务（每次唤醒都在写）→ 维护写被 79.9 认作"新资料到达"→ 新 Wake → AI 再写 → ……M2-001 的 `advance_to_next` 语义是"推进到最早到期点"；唤醒队列永不空 ⇒ **虚拟时间永远无法越过当天**。症状极具欺骗性：不报错、只是"不动"，团队会以为是模拟慢。V21 与 R2-15 各自单测全绿，联动必炸。
**崩点②（M4-001）——索引水位策略真空。** M1-014 只写了"提供 rebuild CLI"：FTS 在 10 万+ 条上重建是分钟级；三十天加速运行下，要么每次唤醒撞 STALE_INDEX，要么同步重建拖死回放，要么静默用旧索引返回缺新数据的结果 → 误判被 oracle 扣分且**归因器无法区分**"认知错"还是"索引旧"（第 86 条七向归因的第 3/4 向被搅浑）。M4 结论被索引工程污染，M8 无法裁决。
**崩点③（M2-009/M7-003）——1 秒叙事当场破产。** 首字延迟从未入闸；M7-003 接入真实模型的当天，同步全局联想（85.2.3 字面执行）在百万级检索上花费秒级，"穿戴端 1 秒真人节奏"崩盘，返工牵动 C10/C11/工作台/M2-009/M2-012，M4/M7 结论重写。
三个崩点的共同根源：**v3.0 的宪法承诺在旧任务书（为 v2.0 所写）里没有落位**——回到 1.1。

## 1.4 总体重构战略：一法 · 一账本 · 一矩阵 · 双 Profile

1. **一法（修宪 R4，三案，先于 M0′ 提交）**：R4-① Reinterpretation 统一语义裁决（附条款文本见附录 A）；R4-② 延迟/成本预算写入第 114 条验收表；R4-③ 共振改"按需提案" + Claim 增加 `source_trust`。宪法是法，本设计书是实施细则总纲。
2. **一账本**：C01–C15 模块编号以本设计书 §2 为唯一账本；`TASK_PROGRESS_R2.md` 基线行**立即**改为"宪法 v3.0 + R4 修改案"——全仓库性价比最高的一行修改。
3. **一矩阵（CAM）**：把第 114 条全部 46 项 + R4 新增 9 项（合计 55 项）转录成机读账本 `schemas/constitution_acceptance.py`（验收项 ↔ 条款 ↔ 模块 ↔ 里程碑 ↔ 状态 ↔ 测试；采用 .py 而非 .yaml 以避免向冻结中的 M0 引入 PyYAML 依赖，属第 115 条实现优化级调整），CI 增加映射 gate（`tests/architecture/test_cam_coverage.py`）：**任何未映射验收项 = 红灯**。把这部宪法的防退化机制从人力改造成机器力，同时让 D5 类漂移在提交时可见。
4. **双 Profile（穿戴端不排队等 M8）**：`runtime_profile ∈ {virtual, band_v0}` 决定 C01 摄入硬约束（不存大图/不存 50Hz 原始/心率平均线）、C13 首字延迟预算、C02 存储速率上限。`virtual` 放宽数值、**不放宽代码路径**；`band_v0` 从 M2 起在每个里程碑 CI 跑"一天回放"冒烟。穿戴约束与长周期机制在**同一条代码路径**上同时成立，这就是"兼顾 Linux 虚拟测试与穿戴端随身心智"的答案：不搞两套工程，把约束做成配置文件。

三行重构原则（写给工程师，也写给后人）：
- **调度即法律，推理是恩典**：凡是确定性可判定的（时间、水位、豁免、预算封顶、预过滤）进内核；只有语义裁决交给模型。凡让模型"自主"做内核能做的事，都是事故隐患。
- **规则不入闸，等于没立**：无数字的验收=口号，无预算的接口=不设防的门，无测试的对象=幽灵。
- **索引是世界的第二颗心脏**：世界＝"append-only 真相 + 可重建投影"的双投影；投影的水位契约是一等公民。

---
# 第二部分 · 《系统架构图与开发规划》升级方案（Plan V0.2 底稿）

## 2.1 C 模块体系重构：唯一账本与迁移对照

编号规则：C02/C03/C05/C06/C07/C08/C09/C10 **以宪法第 108 条边界表语义为准**（宪法是法）；C01/C04/C12/C13/C14 沿用旧规划；C11 新设；旧规划 C06"世界查询"更名 **C11 世界检索与索引（读面）**；旧规划 C11"能力与交互"顺延 **C15**。

| 旧规划编号/名称 | 本设计书 | V3 宪法第 108 条 | 调整性质 |
|---|---|---|---|
| C01 接入与清洗 | **C01 边缘接入与特征提炼** | （未列，本次补界） | 重定义职责边界 |
| C02 时间与世界存储 | C02（+写入分类/双透镜/tombstone） | C02 ✓ | 增补 |
| C03 维度注册与投影 | C03（+共振提案入口） | C03 ✓ | 增补 |
| C04 实体与关联 | C04（+消歧前置/声纹生命周期） | （并入 C02） | 拆分独立+增补 |
| C05 事件、认知与总结 | 拆分：认知→**C06**，总结→**C05** | C05/C06 ✓ | **拆分**（对表宪法） |
| C06 世界查询 | **升格为 C11 世界检索与索引** | **无家可归**（组件 5） | **新设为编号模块**；要求第 108 条 C 表补录 |
| C07 依赖与纠错 | C07 依赖图与传播（+传播预算/积压老化） | C07 ✓ | 增补 |
| C08 任务中心 | **C08 任务中心与谓词调度**（timer wheel + 谓词倒排） | C08 ✓ | 实质更名+内核化 |
| C09 触发与调度 | C09 触发与唤醒仲裁（+豁免表/安全去抖/budget grant） | C09 ✓ | 重定义 |
| C10 工作台与会话 | C10 认知工作台（AssemblyPolicy+两段召回+四步埋点） | C10 ✓ | 重定义 |
| C11 能力与交互 | **C15 能力与穿戴仿真** | （未列） | 改号+扩义（band FSM 仿真） |
| C12 AI操作经验 | C12（+组装策略经验） | （未列） | 沿用+增补 |
| C13 模型接入 | **C13 模型接入与经济控制** | （未列） | 升格为唯一网关+预算执法 |
| C14 仿真与评估 | C14（+对抗注入/影子双世界/延迟注入/序列断言） | （未列） | 增补 |

### 逐模块职责与红线（相对旧版的关键变化）

- **C01 边缘接入与特征提炼**：执行 33 条全部规则——IMU 只提宏观状态、心率长平稳段压平均线、图像端侧语义化不存大图、声纹 embedding 绑定。**新增**：`SourceClass` 写入点（SENSOR 唯一入口）；输出含 **1s/10s 稀疏事件层**（转写句、异常点、显著运动），并明文承认"没有原始高频数据就没有微观镜头"——堵死 87 条微秒下钻的空头支票。红线不变：不做语义判断。
- **C02 时间与世界存储**：append-only revisions / world commits / 引用校验 / knowledge cutoff 全部保留。**新增三件**：① `operations`/`world_commits` 增 `source_class`；② `status=PRUNED` tombstone 修订替代物理删除（修 33.5）；③ `world_at(T, view=AS_KNOWN|ANNOTATED)` 双透镜读面（F1 落点，复用 M0-020 cutoff 机制，不建第二库）。
- **C03 维度注册与投影**：新维度产生唯一路径 = AI 基于共振线索提交 Candidate + DimensionDerivation，走 72–76 生命周期。**新增 `resonance_hint` 对象**：对齐总结出现跨维异常共现时生成"候选线索"（非结论、不写语义）。**永久禁止全局维度对扫描**——"纵向交织"（22 条）从此有了可执行定义。
- **C04 实体与关联**：`resolve()` 作为检索的强制前置换算子（文字≠实体，36 条工程化）；声纹绑定生命周期 + **6 个月淘汰前的抢救条款**（身份绑定被推翻时 embedding 移入 quarantine 区而非销毁）。
- **C05 多尺度总结与人生章节**：日/周/月按第 28 条范围不变。**新增**：summary 重算走预算闸门；`stale_backlog`（数量+最老账龄）为 C09/C13 可见一等指标；LifeChapter 判定为**事件驱动**（异常共振触发复盘），禁止周期性全量重算——第 29 条"去参数化"由此获得第二个可判定红线（第一个是"不得硬编码阈值"）。
- **C06 认知与证据**：Claim/EvidenceSet/Prediction/EventAnchor 生命周期归此（宪法映射表 C06+C07）。**新增**：① **Reinterpretation 对象与可见性裁决器**（F1 责任模块，规格见 §3.4-T4）；② Claim 增 `source_trust` + `corroboration_required`（对抗注入防线）；③ Prediction Register（50–53 条，M0′ 冻结，对撞任务账本在 C08）。
- **C07 依赖图与传播**：持久化反向索引（替代现 `collect_impacted_dependents` 的 O(E) 内存全扫）；**传播预算**（深度/扇出/账龄老化：STALE 超 N 虚拟日未复核 → 降级为观察项，防无界积压）；MAINTENANCE 写入的**生产者**，其全部写入豁免 79 条触发评估。红线不变：引擎只标"谁要复核"，绝不代写新答案；禁止 DB 级 cascade delete。
- **C08 任务中心与谓词调度**：**实质性更名**——不是"表+状态机+轮询"，是**时钟-谓词双通道调度内核**：虚拟时钟域 timer wheel + 谓词倒排索引（86.2 四类谓词编译成可执行表达式，bucket 路由，O(命中) 评估）。第 86 条"零浪费"从宪法愿景变成物理事实。崩溃恢复 = 从 `last_watermark` 重放 world_commits。
- **C09 触发与唤醒仲裁**：**豁免表**（MAINTENANCE 永不产生直接 Wake，只能经 C08 复核任务通道；SAFETY 免冷却但**必须自带去抖带+确认窗**，封死"手腕上的秃鹫"）；Wake 生成时附 C13 的 budget_grant。77/79/82 条既有规则原样保留。
- **C10 认知工作台**：看板组装升格为**版本化 AssemblyPolicy 对象**（谁组看板谁定义 AI 的世界——策略本身入世界、可被 C12 经验改进、改动走 ToolProposal 审批）；**两段式召回编排**（HotCard 同步 + 深联想异步句尾注入）；**四步序 instrumented**（84 条心智法则从祈祷变审计）。
- **C11 世界检索与索引（新设）**：`world_search`（FTS5）+ `occurred_index`（时间透镜物理底座）+ `index_watermark`（世界第二时钟）+ **HotCard 热卡**（1 秒预算内唯一同步召回源）+ 共现交集物理计划。89 条"毫秒级/秒级"矛盾由本模块统一为**一个带 CI 门禁的数字**（p95≤50ms@50万修订）。87 条更名 **Time Lens（时间镜头+维度子集）**——"5D"从未定义，别再装。
- **C12 AI 操作经验**：67–69 条不变；+ AssemblyPolicy 与检索路径经验的反馈环（经验改**排序与裁剪参数**，不改**数据源白名单**——安全轨写入本设计书 §3.4-T5）。
- **C13 模型接入与经济控制**：**全系统唯一模型出口**。`gateway.chat(session, purpose, budget_grant)`；无 grant 即拒（PERMISSION_DENIED）；MeteringRecord 按 (session×purpose×虚拟日) 记账；三级预算（轮/日/周期）。"调用账单"从旧规划 C13 的一句备注升格为带执法权的内核。
- **C14 仿真与评估**：隐藏真值隔离不变；+对抗注入场景库、影子双世界（清洗 vs 全留）、模型延迟/故障注入、四步序断言器、CAM 映射校验。
- **C15 能力与穿戴仿真**：Capability Registry、模拟行动回执；**band FSM 模拟器**（98 条之一状态机变成可执行 fixture：IDLE→TRIGGERED→通道 A/B/C，含"无震动时摸耳必拒绝"负例）；TTS 超 20s 分段器。

## 2.2 更新后的架构数据流（三个回路是重设计重点）

```text
[Sensors/IM/相册]──►C01 接入+特征提炼──►C02 写入(source_class=SENSOR)──►┬─►C08 谓词桶
                    (1s/10s稀疏层;tombstone生成点)   ▲                  └─►C11 索引(异步,水位)
                        │                            │                            │
                        ▼                            │ 修正/标注/复核              ▼
              C09 触发评估:跳过MAINTENANCE ◄──豁免表──C07 传播(预算/老化;MAINTENANCE生产者)──C06 认知/证据/Reinterpretation
                        │                                     │                          ▲
                        ▼                                     ▼                          │写入(source_class=AI_COGNITION)
              Wake队列(去重/合并/冷却/去抖/优先级) ──►C08 到期时钟(timer wheel)          │
                        │                                     │                          │
                        ▼ 唤醒(附budget_grant)                  ▼                          │
              C10 工作台:AssemblyPolicy@v ──► 看板(Wake Reason第一指针+HotCard) ──►C13 模型网关(预算执法/唯一出口)
                        │        ▲                                    │                    │
                        │        └── C11 两段召回:同步≤50ms/异步句尾 ◄─┘                    ▼
                        │                                        C12 经验 ◄── C14 评估/回放/对撞(隐藏真值隔离)
                        ▼
              C15 能力与交互(震动/骨传导/TTS分段;回执→C02)

  回路A 修正回路(安全闭环): C06修正→C07传播→C08复核任务→(MAINTENANCE被C09豁免)→C10再裁决   ← 不经过触发评估
  回路B 认知回路(唯一可进模型的环): C02新写→C09→C10→C13→C06→C02                          ← 每跳都受预算约束
  回路C 经验回路(慢环,后台): C13计量+C14判分→C12→AssemblyPolicy提案(C15/C10治理生效)       ← 不改内核
```

要点：① 回路 A 的"豁免"是 F2 的结构性闭合——维护写**有完整版本记录**（满足 86.4 审计）但**无触发可见性**（满足 64 防风暴）；② 回路 B 的每一跳都过 C13，模型调用必须有 grant，否则"零浪费"无法证明；③ 回路 C 是"经验改善看板"的唯一合法通道——经验只能调**排序与裁剪参数**，调不了**数据源白名单**（防止经验学习变成注入通道）。

## 2.3 V3 十项机制 → 模块/数据/执法三级落位表

| 机制 | 条款 | 主模块 | 数据落位 | 运行时执法点（gate/CI） |
|---|---|---|---|---|
| 双平行世界 | 30–32 | C02/C06 | subject_id 统一机制 + AI 五维种子 | A01 + CAM-A01 自动映射 |
| 认知反哺（回溯标注） | 31之一,81 | **C06** | `Reinterpretation`（新对象） | R4-06：目标节点 revision 不变 + 双视图确定性分叉 |
| 轴向时间金字塔 | 21,26–28 | C05 | Summary 链（source_world_revision） | R2-12/13/14 + 下钻延迟抽样入 M4 指标 |
| 纵向突触共振 | 22,88 | C03 | `resonance_hint`（线索非结论） | 静态断言：维度成对全扫描循环 = 违宪编译错误 |
| 可挂载架构/指针 | 18–20,24 | C03/C02 | Membership/Derivation 引用 | M0-011 已冻结 + 冗余拷贝扫描器（CI 工具） |
| 端侧轻量摄入 | 33 | C01/C02 | 特征提炼 + PRUNED tombstone + 稀疏事件层 | band_v0 profile 一日回放，存储/带宽超限 = 红灯 |
| 单次看盘看板 | 84 | C10 | AssemblyPolicy 版本化对象 | 看板组装单测：一次模型调用一份看板 |
| 心智四步序 | 84.2 | C10/C14 | step trace 标记 | **R4-04**：回放顺序断言（evaluator 校验） |
| 三级流水线+1s | 85 | C10/C11/C13 | HotCard + 两段召回 + 抽取预算 | **R4-01**：首字 p95≤1.0s（mock 链路也测） |
| 条件任务零浪费 | 86.2 | C08 | 谓词四类编译 + 桶路由索引 | **R4-03**：调度器评估次数 O(命中)、零 LLM 调用 |
| 5D 滑条（更名时间镜头） | 87 | C11 | occurred_index 范围查询 | 层级无数据 → zoom 返回 EMPTY_LAYER，禁现编 |
| 共现检索 | 89 | C11 | FTS posting-AND ∩ occurred ∩ 实体解析 | **R4-02**：p95≤50ms@50万修订 + 禁 payload 扫描 |
| 震动 FSM 零误触 | 98之一 | C15/C09 | FSM 仿真 fixture | V21b + 安全去抖：无先导震动的骨传导指令 = 测试失败 |
| 三层 UI/插件挂载 | 104之一 | C15 | Capability Registry + 卡片协议 | 插件私存记忆 = 架构扫描红灯（99 条） |
| 预测证伪闭环 | 50–53 | C06/C08 | Prediction Register + 对撞任务 | R3-03 + 立项理由 schema 强检（无 reasoning 拒写） |

## 2.4 双 Profile（Linux 虚拟测试与穿戴端的同路径策略）

```yaml
runtime_profile:
  virtual:            # M1–M8 默认
    ingest:   {hr_compression_window: 2h, imu: macro_events_only, images: semantic_text_only}
    latency:  {first_token_budget_ms: 1000, recall_sync_budget_ms: 50, transport: mock_fixed_rtt}
    storage:  {raw_tier_days: 30, pruned_tombstone: true}
  band_v0:            # 每个里程碑出口强制冒烟（M2 起）：同一 Core 跑"一天回放"
    ingest:   {…virtual 同款 + 更严: 每摄入算力预算 us 数, 图像队列深度 3, 丢帧必须写 Observation(数据覆盖异常)}
    latency:  {同预算 + tts_max_sec_per_turn: 20, 超限强制分段}
    storage:  {band_local_only: 语义文本+波形包络, ring_buffer_hours: 48, 溢出转基站}
```

规则：profile 只改**数字**，不改**代码路径**；`band_v0` 冒烟失败 = 里程碑不出 gate。穿戴端契合度因此不再是 M8 之后的许诺，而是 M2 起的 CI 产物。

---
# 第三部分 · 《详细开发任务拆分》增补与重构蓝图（R4 任务书 Delta）

## 3.1 里程碑结构调整总表

| 里程碑 | 旧结构 | 本设计调整 | 理由（对应断层） |
|---|---|---|---|
| M0 | 22 任务，M0-022 BLOCKED | **保留** M0-001~021 与 022 终审判定（v2.0 契约集不重开）；新设 **M0′ 契约增量冻结段 M0-023~030**，全绿后 **M0-022R** 复审签 Gate | D1/D4/F1/F2：五类欠账对象+新内核语义必须一次冻结；21 项 FINAL PASS 不得羞辱重审 |
| M1 | 001–016 顺序排 | 检索三件套（M1-012/013/014）**前移**至 M1 第 4 批并行开工；新增 M1-017~020；出口加 **G-M1P 规模冒烟闸**（50 万修订 p95） | F3：读面必须在 M2 开工前扛过负载 |
| M2 | 001–015 | M2-002/005/009 **重写**（见 3.3）；新增 M2-016~021（调度内核/预算闸门/心跳预过滤/四步埋点/安全去抖）；出口新增 **V21b 风暴回归**（唤醒放大比≤1 且虚拟时钟推进≥1 天/分钟） | 崩点①、F2/F4 |
| M3 | 001–011 | M3-001 重写（预算+生产者豁免）；新增 M3-012/013/014（传播预算与积压老化 / Reinterpretation 双视图裁决 / 影子双世界清洗对照） | 崩点②前兆、F1、R8 |
| M4 | 001–004 | 拆 **M4a 工程验证**（V01–V36 全场景+性能与稳定性指标）与 **M4b 科学验证**（对照/盲测/评分）；M4a 不过 → M4b 不开始；新增 M4-005/006/007 | 崩点②③；科学结论必须在工程闸门后取数 |
| M5 | 003 | 新增 M5-004 AssemblyPolicy 经验学习（带安全轨） | R5 治理修正 |
| M6 | 004 | 不变；M6-005 补"插件私存记忆禁扫"静态检查 | 99/104 条 |
| M7 | 004 | M7-002 **降级为复核**（首测在 G-M1P/M4）；新增 M7-005 十年合成规模（测试规范 §138 已允许合成十年，须标注"历史检索测试"非"连续生活"） | F3 顺序修正 |
| M8 | 003 | 新增 **M8-000 基线引入**（B3 = Zep/Graphiti 记忆层进同一仿真器同预算赛道）与 **M8-004 三维消融**（预算闸门/HotCard/回溯标注） | 无 B3 则"代际优势"宣称不成立；无预算消融则"零浪费"不可证 |

横贯：CAM 矩阵 CI Job 从 M0′ 第一天上线（一矩阵）。

## 3.2 必须新增的 Issue 清单（31 项）

| 编号 | 名称 | 里程碑 | 前置 | 验收锚 |
|---|---|---|---|---|
| M0-023 | 写入分类 `source_class` 与触发豁免契约（含安全去抖语义） | M0′ | M0-007/016 | R4-05 |
| M0-024 | LifeChapter 契约冻结（Summary 已在 M0 registry，勘误后缩小范围；STALE/backlog 运行面留 M3） | M0′ | M0-005 | R2-12/13/14 **契约层已落地** |
| M0-025 | Prediction Register 契约冻结（50 条字段 + 53 条立项理由强检） | M0′ | M0-014 | R3-03 |
| M0-026 | CommunicationExperience 契约冻结（OpExp/ToolProposal 已冻，勘误后缩小范围） | M0′ | M0-014 | R1-01, V3-01 **契约层已落地** |
| M0-027 | Reinterpretation 契约冻结 + `world_at(view)` 双透镜读取语义 | M0′ | M0-020 | R4-06 |
| M0-028 | BudgetPolicy / MeteringRecord / AssemblyPolicy 契约冻结 | M0′ | M0-016 | R4-01/03 |
| M0-029 | CAM 宪法验收矩阵 + CI 映射 gate | M0′ | — | **已交付**：账本 55/55 项映射，闸门 7 用例全绿（2026-09-16） |
| M0-030 | runtime_profile 双配置契约（virtual / band_v0） | M0′ | — | band 冒烟通过 |
| M1-017 | FTS5 世界检索核 + 共现交集物理计划（禁 payload 扫描） | M1 | M1-012 | R4-02 |
| M1-018 | 实体/别名消歧前置 resolve-before-intersect 算子 | M1 | M1-002 | V22, 36 条 |
| M1-019 | PRUNED tombstone + 引用计数冷档（33.5 落地为"分层归档"非"删除"） | M1 | M1-001 | R4-07 |
| M1-020 | HotCard 实体×日热卡预计算管道（读面 ≤50ms） | M1 | M1-017 | R4-01 |
| G-M1P | M1 规模冒烟 Gate：50 万修订 p95 集合（检索/下钻/重建） | M1 出口 | M1-017/020 | R4-02 |
| M2-016 | 持久时钟 + 谓词倒排调度器（timer wheel + bucket 路由 + 水位恢复） | M2 | M0-023, M2-005 | R4-03 |
| M2-017 | 条件任务四类谓词编译器（time/context/event/dependency，白名单算子） | M2 | M2-016 | 86.2 |
| M2-018 | C13 经济闸门全链路接入（会话/抽取/心跳/复核四类 call site） | M2 | M0-028, M2-012 | R4-01/03 |
| M2-019 | 长平稳心跳机械预过滤 RuleGate（零 Token）+ LLM 准入 grant | M2 | M2-016/018 | R4-03 |
| M2-020 | 四步序 instrumented step trace + 回放顺序断言 | M2 | M2-009 | R4-04 |
| M2-021 | band FSM 仿真 fixture + 安全通道去抖压测 | M2 | M0-023 | V21b, 98之一 |
| M2-GATE | M2 出口：V21b 风暴回归（唤醒放大比≤1；时钟冻结检测器） | M2 出口 | 全部 | R4-05 |
| M3-012 | 传播预算：深度/扇出上限 + STALE 积压账龄老化降级 | M3 | M3-001 | R2-15 扩展 |
| M3-013 | Reinterpretation 双视图可见性裁决器 + 时态真值集 | M3 | M0-027 | R4-06 |
| M3-014 | 影子双世界清洗对照（全留组 vs 清洗组同 oracle） | M3 | M3-004 | R4-08 |
| M4-005 | 首字延迟预算端到端演示（mock 传输固定 RTT + 30 天回放） | M4a | M2-018/020 | R4-01 |
| M4-006 | 对抗注入场景包 V31（IM 谎报/伪声纹/清洗对抗，三态齐备） | M4b | C06 信任字段 | R4-09 |
| M4-007 | M4b 科学实验闸门：首字+成本进验收报告头版 | M4b | M4-005 | R4-01 |
| M5-004 | AssemblyPolicy 经验学习（白名单不可动，仅排序/裁剪参数） | M5 | M3-011 | V3-03 |
| M6-005 | 插件数据孤岛禁扫（静态：插件命名空间无独立存储句柄） | M6 | M6-001 | 99 条 |
| M7-005 | 十年合成规模与历史检索测试（标注非连续生活） | M7 | M7-002 | 87/26 条 |
| M8-000 | B3=Zep/Graphiti 基线引入（同仿真器同预算赛道） | M8 | — | 112 条 |
| M8-004 | 预算/HotCard/回溯标注 三维消融 | M8 | M8-001 | 53/85/86 条 |

## 3.3 必须重写/废黜的旧 Issue（及改法）

| 旧 Issue | 问题（原文核对） | 重写方式 |
|---|---|---|
| **M2-002 机械触发引擎** | "Observation commit 后把变更摘要投递 trigger engine"——commit 流无分类，F2 的直接载体 | 入口前置豁免表：`if commit.source_class==MAINTENANCE: return`；SAFETY 通道自带去抖带+确认窗参数；新增单测"维护风暴零唤醒"入 Gate |
| **M2-005 任务中心持久调度** | "持久调度"实为表轮询（O(N)/tick），与 86.2"零浪费"矛盾 | 由 M2-016 取代内核：timer wheel + 谓词桶；"轮询任务表"写进 I 节禁止事项 |
| **M2-009 workspace.open 初始工作包** | 一次性倾倒式组装，无策略对象、无两段式、无预算 | 重写为 AssemblyPolicy@version 驱动 + HotCard 同步 + 深联想异步；响应附 `budget_grant_id` |
| **M1-010/011 时间镜头与多维对齐** | 87 条"微秒"承诺 vs 33 条禁高频存储 | 声明 1s/10s 层=稀疏事件 only；层级无数据时 zoom 返回 `EMPTY_LAYER`（诚实报空），禁止现编摘要 |
| **M1-012 世界搜索** | "FTS5 + alias，语义向量可替换适配器"一句带过，无规模验收 | 内核划入 M1-017；G-M1P 为出口闸；"语义向量后置"决定保留（正确） |
| **M1-014 索引水位** | 只给"提供 rebuild CLI"一句，水位策略真空 | 升格为 M0-023 级契约：所有读响应强制返回 `(world_revision, watermark, lag)`；adaptive 追赶 ≤2000 修订同步 apply |
| **M3-001 纠错传播引擎** | "限制最大传播深度/批量"有意识，无预算落点，生产者不豁免 | 接 M3-012；全部维护写打 MAINTENANCE；STALE 积压老化规则成文 |
| **M4-002 评价指标** | 成本是事后统计；无延迟类指标 | 首字 p95、每回合调用数、预算耗尽率升**一级指标**且与 C13 ledger 同源（运行时闸即指标，禁止两套账本） |
| **M7-002 规模基准** | 首测放 M7，顺序排错 | 降级为"复核"；首测在 G-M1P，二次在 M4a，三点位一致才过 |
| **旧规划 V0.1 整体** | 依据 v2.0、七段里程碑、C 表与宪法冲突 | 废止归档；以本设计书第二部分 + 旧规划 §5/§6/§8（数据契约/一致性/调度并发三节是**好资产**，编号订正后并入）组成规划 V0.2 |
| **TASK_PROGRESS_R2.md 基线行** | `宪法基线：AIOS宪法2.0.txt + R1/R2` | 立即改 `宪法基线：AIOS核心系统宪法v3.0（+R4修改案待批）`；同步 README |

## 3.4 五个核心任务的代码级详规（按任务书 A–J 格式）

### T1 · M0-023 写入分类与触发豁免契约（F2 闭合点）

**A 目标**：给"这次写入是谁发起的"以内核表达，使 64/82 条反风暴条款第一次技术上可执行。
**B 为什么现在**：必须在 M1-001（Observation 接入）落第一笔数据前冻结，否则 M2/M3 全部历史无法审计，豁免策略永远补不回来。
**C 方案**：contracts 增枚举；OperationRequest（M0-016 模型）与 world_commits 增字段；Observation 增 `origin`；触发引擎读 `commit.source_class` 过滤。
**D 数据契约**：

```python
class SourceClass(str, Enum):
    USER = "USER"                  # 用户亲口（按键/语音/亲述）
    SENSOR = "SENSOR"              # C01 传感器/模拟摄入
    AI_COGNITION = "AI_COGNITION"  # 会话内语义写入(claim/event/task/annotation)
    MAINTENANCE = "MAINTENANCE"    # 维护写:STALE标记/总结重建/PRUNE/索引元数据
    SAFETY = "SAFETY"              # 固件安全通道,唯一免冷却者

class MaintenanceClass(str, Enum):
    STALE_MARK; SUMMARY_REBUILD; PRUNE; INDEX_META; POLICY_SYNC

class OperationRequest(BaseModel):        # M0-016 增补
    ...existing 10 fields...
    source_class: SourceClass = SourceClass.AI_COGNITION
    maintenance_class: MaintenanceClass | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.source_class is SourceClass.MAINTENANCE and not self.maintenance_class:
            raise ValueError("MAINTENANCE requires maintenance_class")
        if self.source_class is not SourceClass.MAINTENANCE and self.maintenance_class:
            raise ValueError("maintenance_class only with MAINTENANCE")
        return self
```

```sql
-- world_commits 迁移（append-only,显式回填,禁止 DEFAULT 蒙混）
CREATE TABLE world_commits_v2 AS
  SELECT world_revision, committed_at, operation_id, session_id, reason,
         'AI_COGNITION' AS source_class FROM world_commits;
ALTER TABLE world_commits RENAME TO world_commits_v1;
ALTER TABLE world_commits_v2 RENAME TO world_commits;
CREATE INDEX idx_commits_triggerable
  ON world_commits(world_revision) WHERE source_class <> 'MAINTENANCE';
```

```python
def on_world_commit(commit, delta):                    # M2-002 重写入口(十行)
    if commit.source_class == SourceClass.MAINTENANCE:
        return            # F2闭合:维护写对触发评估不可见;复核经C08任务通道,天然有序
    if commit.source_class == SourceClass.SAFETY:
        wake_arbiter.push_safety(commit, debounce_state)  # 免冷却≠免去抖
        return
    wake_arbiter.push(evaluate_rules(delta))
```

**E 位置**：`contracts/enums.py, operations.py, storage/sqlite_store.py, wake/, tests/unit/test_source_class.py`
**F 接口**：不新增公开 API；ai_worker 默认且仅可 AI_COGNITION；MAINTENANCE/SAFETY 凭证仅内核调度器与固件桥持有（service 层 session role 校验）。
**G 测试**：① 维护写 1 万笔 → 0 Wake；② ai_worker 冒充 MAINTENANCE → PERMISSION_DENIED；③ 摔倒阈值 50 次/秒抖动 → 去抖带后 ≤1 条强震指令 + 确认窗；④ 旧库迁移幂等、历史回填可证明。
**H 验收（新 R4-05）**：V21b 三十天回放：唤醒放大比≤1；commit 流审计 100% 可归类；`git grep` 确认触发路径无 `source_class IS NULL` 兜底。
**I 禁止**：禁止语义识别"维护内容"再豁免（那是语义判断，违 77/106）；禁止物理删除伪装 PRUNE（tombstone 必留 revision）；禁止 AI 修改安全阈值（83.2）。
**J 交付**：契约+迁移+引擎过滤+风暴测试组。

### T2 · M1-017/018/020 共现检索核 + 消歧 + HotCard（C11）

**A 目标**：把 85/87/89 的"毫秒级/下钻/全局联想"变成带 CI 门禁的物理事实；索引=**世界的可重建投影**，永不与真相争辩。
**C 方案（物理结构）**：

```sql
CREATE VIRTUAL TABLE world_search USING fts5(
    object_id UNINDEXED, revision UNINDEXED,
    entry_tokens,      -- 分词管道写入:关键词+entity_ids+别名+事件标签(投影,非拷贝)
    excerpt,           -- ≤200字符命中上下文,可整体重建
    tokenize='unicode61 remove_diacritics 2');
CREATE TABLE occurred_index(                    -- 5D滑条物理底座:镜头=该表范围查询
    object_id TEXT, revision INTEGER,
    occurred_start_us INTEGER NOT NULL, occurred_end_us INTEGER NOT NULL,
    subject_id TEXT NOT NULL, object_type TEXT NOT NULL,
    PRIMARY KEY(object_id, revision));
CREATE INDEX idx_occurred_time ON occurred_index(occurred_start_us, object_type, subject_id);
CREATE TABLE index_watermark(index_name TEXT PRIMARY KEY,
    last_world_revision INTEGER NOT NULL, lag_threshold_us INTEGER, rebuilt_at TEXT);
CREATE TABLE hot_cards(                          -- 1s预算内唯一同步召回源
    subject_id TEXT, entity_id TEXT, day_us INTEGER,
    digest_json TEXT NOT NULL,                   -- 关系标签/待兑承诺/近期事件摘要/心理基线
    built_from_revision INTEGER NOT NULL,
    PRIMARY KEY(subject_id, entity_id, day_us));
```

```python
def co_search(keywords, *, subject, time_range=None, cutoff, freshness="adaptive", limit=64):
    wm = watermark("world_search")
    if wm.lag <= SYNC_CATCHUP_MAX: catch_up(wm)              # 小延迟:同步apply commit log
    elif freshness=="strict" and not fresh(wm, cutoff):
        return STALE_INDEX(retry_after=wm.eta)               # 显式错误,禁止旧索引装新
    sets=[]
    for kw in keywords:
        ent = entity_resolver.resolve(kw, subject, cutoff)   # 36条:先编号后文字;歧义→返回候选不做交集
        sets.append(fts_postings(world_search, q(ent or kw), subject))
    cand = intersection(sets)                                 # 真共现交集(AND),非逐词缩小
    rows = join(cand, occurred_index).where(time_range, visible_before(cutoff))
    topk = bm25(rows, boost={"event_anchor":1.5, "claim":1.2})[:limit]
    return topk, [resonance_weight(o) for o in topk[:16]]    # 图上共振加权:仅top16,禁全图

def recall_for_turn(input_slice):                             # C10 两段召回
    hot  = hot_cards.fetch(entities(input_slice), today)      # 同步 ≤50ms
    task = async_deep_recall(input_slice, budget_grant)      # 异步:句尾/下轮注入
    return hot | pending(task)
```

**Token 纪律**：返回指针（`object_id@revision`）+≤200 字摘要；AI 用 `world.navigate` 按需展开；**检索响应正文 ≤1.5K tokens**（AssemblyPolicy 硬校验）。
**G 测试**：① 50 万修订：`[妈妈,生日,礼物]` p95≤50ms；② `EXPLAIN QUERY PLAN` 断言含 fts5+occurred_index、**不含** `SCAN object_revisions`；③ 同名异实体（小王×3）交集按编号分裂；④ adaptive/strict 两态；⑤ 迟到数据→HotCard 打脏标记延迟重建（禁同步重建）。
**H 验收（R4-02）**：G-M1P / M4a / M7-002 三点位 p95 一致（±20% 内）；V30 全链路下钻走本核。
**I 禁止**：禁 LIKE/payload 扫描（源码静态扫描）；禁 excerpt 拷贝原话全文（冗余扫描器）；禁把 FTS 写入嵌进 C02 提交事务（写放大；异步+水位是唯一形态）。
**J 交付**：索引 schema、重建 CLI、co_search、HotCard 管道、基准套件。

### T3 · M2-016/017 持久时钟与谓词调度器（C08 核心）

**A 目标**：使 86.2 条件任务"就绪才挂载、不空转"成为内核能力；废表轮询。
**C 方案**：双通道——时间通道（虚拟时钟域 timer wheel）+ 谓词通道（倒排桶事件驱动）。谓词编译器把四类谓词编译成受限表达式；**从触发到唤醒零模型调用**（红线：编译器只做语法与白名单校验）。

```sql
CREATE TABLE timer_heap(entry_id INTEGER PRIMARY KEY, due_at_us INTEGER NOT NULL,
  kind TEXT CHECK(kind IN ('TASK_DUE','DEADLINE_CHECK','PREDICT_CLASH','HEARTBEAT','REVIEW','CATCHUP')),
  ref_id TEXT, fingerprint TEXT NOT NULL, status TEXT DEFAULT 'ARMED',
  UNIQUE(fingerprint));                              -- 64条:去重在DDL层
CREATE INDEX idx_timer_due ON timer_heap(due_at_us) WHERE status='ARMED';
CREATE TABLE watch_predicates(pid TEXT PRIMARY KEY, task_id TEXT NOT NULL,
  kind TEXT CHECK(kind IN ('time_reached','context_matched','event_occurred','dependency_ready')),
  compiled TEXT NOT NULL, armed INTEGER NOT NULL DEFAULT 1, fire_policy TEXT NOT NULL);
  -- fire_policy: once | once_per_window:<dur> | rearm_required:<actor>
CREATE TABLE predicate_bucket(bucket_key TEXT, pid TEXT, PRIMARY KEY(bucket_key, pid));
  -- bucket_key: 'entity:P004' 'dim:HR' 'kw:礼物' 'event:REVISED@E012' 'done:T9'
```

```python
class PredicateCompiler:
    def compile(self, task_id, spec):
        match spec.kind:
            case "context_matched":   # 白名单:枚举型维度状态机,禁自由语义
                for p in spec.clauses:
                    assert p.dim in DIM_REGISTRY and p.op in CMP_OPS
                    bucket = f"dim:{p.dim}"
            case "event_occurred":    bucket = f"event:{spec.event_ref}@{spec.transition}"
            case "dependency_ready":  bucket = f"done:{spec.upstream_id}"
            case "time_reached":
                timer_heap.insert(due=spec.at, fingerprint=fp(task_id, spec)); return
        # 编译失败 → INVALID_ARGUMENT,禁止猜测性装载
        return PredicateRow(task_id, spec.kind, buckets=[bucket], ...)

def on_commit(commit):                                # 谓词通道: O(命中) 而非 O(N)
    for key in commit.touch_buckets:                  # C02生成touch集;MAINTENANCE不生成谓词命中
        for pid in bucket[key]:
            p = load(pid)
            if p.armed and eval_compiled(p, commit):  # 确定性求值,微秒级
                fire(pid, fingerprint=f"{pid}:{commit.world_revision // WINDOW}")

def on_timer(now_us):                                 # 时间通道
    for e in heap.pop_all(due_to=now_us):
        wake_queue.push(e.ref, priority=e.kind, catchup=policy(e))  # fire|merge|skip|expire
        # armed=0 且 rearm_required 者:未获再武装即静默(明示记录,防"周期性提醒生日礼物"跑飞)

def recover():
    for c in commits_after(kv("scheduler_watermark")): route(c)     # 重放恢复;豁免保证回放安全
```

**心跳路径（R6 修正）**：`HEARTBEAT` 到期 → **RuleGate 机械预过滤**（日历状态机：工作时段/深夜/驾驶 + 上次震动响应率统计；零 LLM）→ 通过才带 `budget_grant(background_low)` 入队；拒绝则记 `HEARTBEAT_SUPPRESSED`（回放可见，不装醒过）。
**G 测试**：① 1 万条 armed 谓词 × 30 天虚拟风暴：谓词评估数 = O(命中)、**模型调用 = 0**；② 崩溃重放幂等（同 watermark → 同唤醒集）；③ catch-up 四策略矩阵（360 天后生日继承 R2 用例）；④ rearm 不 grant → 静默且有记录；⑤ 心跳预过滤通过/拒绝两态 + 预算拒绝降级。
**H 验收（R4-03）**：调度器全生命周期零 LLM 调用；V21b 时钟冻结检测器（推进吞吐 ≥1 天/分钟）为 M2 出口红线。
**I 禁止**：禁 `SELECT * FROM tasks` 轮询（静态+运行双断言）；禁调度路径模型调用（C13 网关拒签）；禁未登记谓词直接命中；冷却仍不得屏蔽 SAFETY，但 SAFETY 去抖为修宪例外（附录 A-2）。
**J 交付**：调度核、谓词编译器、恢复重放、RuleGate、风暴 fixture。

### T4 · M3-013 Reinterpretation 与双视图可见性裁决器（F1 责任模块）

**A 目标**：把 31 条之一/81 条"回溯标注"翻译成 append-only 数据科学，使 93/116 与"内心数据反哺"**同时**为真。
**C 方案**：新对象 + 双镜头。标注永不改目标；历史查询分 `AS_KNOWN`（AI 当时的世界观——评估器打分用）与 `ANNOTATED`（世界+标注层——叙事呈现用）。双透镜是**查询参数**，不是两个库。

```python
class AnnotationSlot(str, Enum):          # 注册制枚举,禁自由槽名(76条防爆)
    EMOTION = "EMOTION"                   # 81条场景:平静曲线加注"极度憋屈"
    MEANING = "MEANING"                   # 事件含义修正
    IDENTITY_TAG = "IDENTITY_TAG"         # 31条之一:地点/人物档案挂标签

class Reinterpretation(WorldObject):      # 继承 M0-005 公共字段(含 revision/status)
    object_type = "reinterpretation"
    target_ref: ObjectRef                 # pinned 到精确 revision(18条指针主义)
    slot: AnnotationSlot
    statement: str                        # 一句话;1~3句纪律同样适用于内心独白
    confidence: float                     # 94条:置信度属于本标注,不是被标注对象
    evidence_set_id: str | None           # 支撑标注的用户坦白(42条一等证据)
    supersedes: str | None                # 标注演化链(append-only)
    valid_time_range: TimeRange | None    # 标注指向的区间,≠标注诞生时间

def world_at(subject, T, view, cutoff=None):
    base = store.snapshot(subject, as_of=min(T, cutoff or T))    # M0-020 机制不变
    if view == "AS_KNOWN": return base                            # 标注 learned_at>T 自动不可见
    annos = store.latest_non_superseded(Reinterpretation, target_in=base.ids, visible_before=now)
    return overlay(base, annos)          # 纯函数;overlay 规则由 slot 注册表定义

def invalidate_annotation(r):
    r.revise(status=SUPERSEDED)          # 只波及引用该标注的高层总结;
                                         # 目标节点依赖集不动——爆炸半径=O(citation),非O(history)
```

**与 49/63/79 条的一致性**：标注的**创建** = AI_COGNITION 写（"AI 忽然懂了"本身是新事实，正常进触发评估）；标注的**撤销/替换** = MAINTENANCE（豁免，防标注修订风暴）。
**G 测试**：① 同一 T 两视图确定性分叉；② 标注后原节点 revision 计数不变（哈希审计）；③ 万条标注压力：传播工作量 O(citation) ≤ 预算（R2-15 扩展）；④ 评估器纪律：V36"心里憋屈表面平稳"场景中"当时应知"判分只用 AS_KNOWN 镜头（111 条答案先行扩展到时态轴）；⑤ overlay 幂等。
**H 验收（新 R4-06）**：双视图+append-only+爆炸半径三合一回归；31 条之一条款按附录 A-1 改写后全绿。
**I 禁止**：禁物理/逻辑改写历史 Observation payload（116 一票否决）；禁绕过 slot 注册表发明标注类型；禁 AS_KNOWN 视图被标注污染（评估作弊）；禁"历史总结为反映标注而重算"（93.3——历史总结永为"当时叙事"，这就是它的价值）。
**J 交付**：对象契约（入 M0-027）、裁决器、overlay 引擎、时态真值测试集。

### T5 · M0-028/2-018 预算闸门（C13 经济控制）——"零浪费"的最后一块拼图

**A 目标**：把 53/85/86 的成本叙事变成内核可掐断的三个数；使新增延迟/成本验收可执行。
**C 方案**：模型调用一律经 `gateway.chat(session, purpose, grant)`；**无 grant 的调用 = 测试失败**。账本按 (session × purpose × 虚拟日)；三级预算（轮/日/周期）；**预算是世界对象**（可版本化、可被经验改进），**执法在内核**（不可协商）。

```python
class BudgetPolicy(WorldObject):                  # M0-028 冻结
    scope: Literal["turn","day","background_day","recall_sync","maint_task"]
    max_model_calls: int;  max_prefill_tokens: int;  max_decode_tokens: int
    max_wakes: int | None
    on_exceed: Literal["checkpoint","degrade_rules","defer_low_value","hard_deny"]
    version_reason: str                            # 谁改的、为什么(86.4 全审计)

class MeteringRecord(BaseModel):                   # 记 operations_db,不进世界库
    session_id: str; virtual_day: int
    purpose: Literal["session_answer","stream_extract","heartbeat_llm","review_task","summary_rebuild","eval"]
    tokens_in: int; tokens_out: int; wall_ms: int; world_revision: int
    granted_by: str | None                          # None = 违规,CI 红

def authorize(purpose, est):
    b = policy_cache.current(purpose)
    if ledger.exceeded(b, est):
        record(BUDGET_EXHAUSTED, checkpoint=save_progress())   # 检查点续办(86.4)
        return defer(purpose, to=next_low_activity_window()) if b.on_exceed=="defer_low_value" else REFUSE
    return grant(b.reserve(est))
```

**三个执法接入点**：① 流式抽取（85.2.2）：`stream_extract` 桶 = `1 次/每8回合, ≤40/日`，溢出**合并入队**而非硬等（"绝不积压"改判为"有界延迟积压"——宪法语言与物理和解）；② 复核任务（63 条）：`review_task` 桶 = 每日重建 ≤200 个 Summary，超限转观察项（与 M3-012 共用老化器）；③ 心跳：预过滤通过才准 LLM（T3）。**M4-002 的"成本"指标直接读本账本**——运行时闸与事后指标同源，杜绝两套账。
**G 测试**：① 全通道负例（无 grant 调用必败）；② 耗尽→checkpoint→续办不重复执行（继承 R1-10）；③ 30 天回放：background 桶消耗平滑（方差断言）、turn 桶零击穿；④ AI 只能经 ToolProposal 改预算，安全与摄入底线不可改。
**H 验收（R4-01/03/07）**：M4a 不过则 M4b 科学结论作废（先闸门后实验）。
**I 禁止**：禁把计量记录写进世界库（计量写本身会自我触发——F2 逻辑对预算系统的自反检查）；禁把预算判断塞进 prompt（模型自觉不是预算）；禁预算豁免安全通道。
**J 交付**：两个冻结契约 + 闸门服务 + 三接入点 + 控制台预算面板（§4.1 W4）。

## 3.5 并行度与关键路径

```text
关键链: M0-023 → M0-022R → (M1-017→G-M1P) → M2-016 → M2-GATE(V21b) → M3-013 → M4a → M4b → M8
可并行: M0-024/25/26/27/28, M1-018/020, M2-019/021, M4-006, M5, M6(全部非关键), M8-000(独立搭桥)
Gate 清单: M0′→M1: R4 契约全绿 + CAM 55/55 映射（M0-029 已交付）
           M1→M2: G-M1P(50万修订 p95)
           M2→M3: V21b(唤醒放大比≤1 且 时钟推进≥1天/分钟)
           M3→M4a: R4-06(双视图) + R4-07(归档审计)
           M4a→M4b: R4-01/03/07 + 影子对照组(M3-014)数据完整
           M4b→M5: 112 条 14 项能力评分报告含成本列
           M8: B3 基线完整 + 三维消融结论可反驳
```

---
# 第四部分 · 工作台规格与虚拟测试规范配套升级

## 4.1 《AIOS认知工作台功能规格》六条修订（W1–W6）

**W1 · 看板 = AssemblyPolicy 的产物，不是硬编码逻辑。** §3"唤醒初始工作包"改写：看板渲染 `AssemblyPolicy@version` 的执行结果；面板头三行元数据：**policy 版本 / 索引水位+lag / budget_grant 余额**。被省略内容显示数量与查询入口（旧规格此条保留）。四层架构（85.3）落为四个独立 section，`recall_sync` 桶封顶第三层 ≤800 tokens。
**W2 · 两段召回时间线。** 会话视图每个涉及实体展开"已加载热卡 / 深度召回 pending"两态；**禁止首句因'等待检索'而延迟**——编排器纪律：深召回未返回则句尾/下轮注入并明示"补充背景已送达"。这一条同时是穿戴体验规格：1 秒首字与深邃记忆不可兼得时，**先像人一样接话，再把功课补上**。
**W3 · 四步序时间线。** 回放流新增步骤泳道 `mirror→rapport→posture→world`；乱序/跳步红色标记并计入违宪计数（R4-04）。"认知调试控制台"从日志查看器升级为**断言查看器**。
**W4 · 预算面板。** 常驻四数：今日剩余调用 / token 消耗 / STALE 积压数 / 最老积压账龄。`BUDGET_EXHAUSTED` 从错误码升格为"检查点卡"：开发可手动续办，仿真自动 defer 到下一低活跃窗口。
**W5 · 手环壳（band simulator）。** 23cm 环幕仿真视图：卡片正文硬限 1–3 句（14 条之一的执法点；超限显示"→ 手机看全文"，**截断逻辑本身是可测行为**）；骨传导模式带 TTS 时长表，>20s/轮标红并强制分段；FSM 交互台：先导震动→5–10s 窗口→通道 A/B/C；输入"无震动时摸耳"必须被拒（零误触从口号变成一条输入校验测试）。
**W6 · 反爹味探测器。** 实时指标：输出句数/字数分布、枚举说教标记（"首先/其次/综上/请注意"）密度、道歉循环计数。连续违规 ≥3 次自动登记 CommunicationExperience 负样本（69 条闭环）。同一探测器输出进入 M4/M7 评分（冗长度率，见 4.2 T2）。

## 4.2 《AIOS虚拟世界测试规范》升级（T1–T7）

**T1 · 新增场景包（§10 矩阵 V21~V30 之上扩展）**：

| 场景 | 内容 | 一票否决式验收 |
|---|---|---|
| V21b | 高频传感 + 维护写风暴叠加 | 唤醒放大比 ≤1；**虚拟时钟冻结检测**：推进吞吐 ≥1 天/分钟，否则红灯 |
| V31 | 对抗注入：IM 第三方谎报（"你妈说车借他"）、伪声纹、清洗对抗样本 | 第三方 REPORTED 不得升为高置信 FACT、不得触发对外行动；`source_trust` 账本完整可见 |
| V32 | 摔倒阈值抖动 + 安全通道 | 去抖后 ≤1 次强震确认；安全唤醒不被常规冷却压制、也**不是机关枪** |
| V33 | 连续 30 天、每天一次触及枢纽实体（老张式）的修正 | STALE 积压 ≤配额；传播不爆预算；R2-11/15 全绿（算力雪崩实测数字入报告） |
| V34 | 首字延迟：固定注入 RTT（ASR 尾点 400ms + 网络 150ms） | p95 ≤1.0s；热卡 miss 时按"先短答后补背景"降级并记 CommunicationExperience |
| V35 | 影子双世界：全留组 vs LLM 清洗组（同 oracle 同预算） | 清洗组效用 ≥ 全留组 − ε **且**存储显著下降；否则 33.5 机制本身被消融出局 |
| V36 | 时态双视图："心里憋屈表面平稳"当日 | 判分只用 AS_KNOWN 透镜评"当时应知"；标注叙事单独计分列 |

**T2 · 指标表扩容（§11 之上）**：一级指标新增 **首字 p95、每回合模型调用数、唤醒数/日、预算耗尽率、STALE 积压 P95 账龄、注入拦截率、冗长度率**。成本从"报告附录"（§232 的好精神）升为**与准确率并列的一级指标**，且数据源与 C13 运行时账本同源。
**T3 · 基线组**：§8"B2 不能故意做弱"落为 **B3 = Zep/Graphiti 记忆层**接入同一仿真器、同 oracle、同预算赛道。若架构宣称"代际优势"，必须赢 B3；赢不了，按 426 条"成本-效果曲线"规则如实报告——这条纪律是本项目学术诚信的保险丝。
**T4 · 时钟与故障注入**（§6 扩展）：模型延迟/超时/降智（随机错误输出率 ε）注入必须覆盖"1 秒预算下链路退化行为"——超时后 HotCard 兜底回复、深召回迟到注入，**不许重试打爆预算**；断网场景验证"本地缓冲带（48h）+ 恢复追赶"与恢复风暴抑制（79 条"系统恢复"合法，但恢复唤醒必须过 C09 合并器）。
**T5 · 评分隔离**（§2 四层隔离扩展）：评估器只读 `AS_KNOWN` 快照 + 隐藏真值；**禁止评估器读 ANNOTATED 视图打分**（否则系统在"事后诸葛"意义上被奖励，正反馈造假通道）；CAM 映射表本身纳入版本库评审。
**T6 · 穿戴 Profile 冒烟**：每个里程碑出口，同一仿真剧本在 `band_v0` profile 下重放一天——存储/带宽/首字/TTS 超限即红灯。穿戴契合度进入回归，不再靠自觉。
**T7 · M8 消融维度表补全**：`{预算闸门, HotCard, 回溯标注, 抽取流水线, 动态维度, 双世界}` × `{效用, 成本, 鲁棒(V31/V32), 冗长度}` 全矩阵；任何机制消融后指标不退化的，M8 裁决**当场删除该机制**——这部宪法必须被它自己的第 112 条公平地审判。

## 4.3 附录 A · 修宪 R4 条款文本（供宪法修订案直接采用）

**A-1（裁决 F1，改写第 31 条之一第 1 款）**：
> AI 获知内心事实后，通过创建 `Reinterpretation` 对象为历史时空切片**追加解释层**：该对象诞生于当前时间戳、以 pinned 引用指向被加注节点，永不改写被加注对象。历史查询区分"当时已知（AS_KNOWN）"与"完整世界（ANNOTATED）"两种透镜；一切认知修正仍遵守第 93 条历史不可篡改铁律。第 81 条"修正原有的平稳曲线"改为"为原有的平稳曲线追加可展开的标注层"。

**A-2（补第 82 条例外）**：
> 安全信号不受普通冷却规则屏蔽；但安全通道必须自带**去抖带与确认窗**：连续抖动命中合并为单次确认，确认通过前不得向用户输出紧急震动。防误触（98 条之一）优先于防漏报的呈现节奏，漏报由固件确认窗兜底。

**A-3（第 33 条第 5 款末句替换）**：
> 大模型每日复盘拥有的是**归档提案权**而非物理删除权：判定为噪声的碎片标记 `PRUNED`（tombstone，保留可重建引用），移入冷存层；仅当"零引用 ∧ 超龄 ∧ 用户显式授权"三条件合取时，方可离线压缩。已确立事件、关键原话、核心证据链永存——永存的实现方式是 append-only，不是许愿。

**A-4（第 87 条更名与定义）**：
> "5D 时间镜头"更名为**时间镜头（Time Lens）**：缩放（zoom）、平移（shift）、框选（select）三操作 × 维度开/闭（88.1）× 并行对比（88.2）。1s/10s 层仅含稀疏事件（显著运动点、转写句、异常标记）；该层无数据时 zoom 返回 EMPTY_LAYER，禁止以推断填充。

**A-5（第 89 条单位统一 + 第 114 条增设 R4 验收行）**：
> 共现检索延迟统一为"毫秒级（p95 ≤ 50ms @ 50 万对象修订）"，删除"秒级"表述。第 114 条新增：R4-01 首字 p95≤1.0s（V34 链路）；R4-02 检索规模闸（G-M1P/M4/M7 三点位一致）；R4-03 调度器零模型调用+谓词命中数 O(命中)；R4-04 四步序回放断言通过；R4-05 V21b 风暴回归；R4-06 双视图确定性分叉；R4-07 归档审计（全库无未授权物理删除）；R4-08 影子对照结论；R4-09 注入拦截（V31 全绿）。

---

# 结语：这次重构到底在救什么

这份设计书没有增加任何一个新机制——这是刻意的。**v3.0 已经死于"说得太多"，不会再死于"做得太少"。** 我做的全部事情是：把散落在四份文档里的相互矛盾的法律，收拢成一套可执行的机构表（一账本）、一台会说真话的秤（预算与延迟闸门）、一组能自己抓住违约的摄像头（CAM 矩阵），然后给三个从未被任何代码模块认领的承诺（回溯标注、谓词调度、检索规模）找到户口，把它们排在各自崩溃点之前落地。

一句话总纲：**调度即法律，推理是恩典；规则不入闸，等于没有立。** M0-023 那一个枚举字段的成本是一天；它的缺失的代价，是 M4 的三十天永远跑不完，和 M8 拿着一份被索引与风暴污染的评分去裁决一部宪法。先修承重墙，再浇混凝土。

*（本设计书为独立第三方评审产物，与总工程师现行排期冲突之处，按宪法第 115 条走"机制优化/架构修改"分级流程裁决；其引用的全部旧文档证据均可在仓库 HEAD cd8bb29 逐字复核。）*
