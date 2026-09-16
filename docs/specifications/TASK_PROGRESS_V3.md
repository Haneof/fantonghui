# AIOS 3.0 全量工程开发进度总表与派工台账

> **基准宪法**：`docs/constitution/AIOS核心系统宪法v3.0.md`  
> **核心仓库**：`aios-2.0` / `aios-3.0`  
> **总指挥部**：首席架构总工  
> **最后更新**：2026-09-16  
> **当前状态**：**1132 passed, 0 xfailed, 0 failed (100% 满堂绿)**（会话 `01a0a700` 合流 M5-005 战训考场 8 项验收后复测）

---

## 一、全生命周期里程碑进度全景

| 里程碑 | 主题与核心攻坚方向 | 规划任务数 | 状态 | 交付物与关键门禁 (Gate Assertion) |
|---|---|:---:|:---:|---|
| **M0** | 世界契约底座与生命安全熔断 | 23 项 | **100% 已闭环 (CLOSED)** | 既有 535 项单测全绿；M0-023 生命安全熔断直通穿透 $\le 50\text{ms}$；已正式签发 M0 封关令。 |
| **M1** | 共同世界、多模态清洗与 CJK 倒排 | 20 项 | **100% 已闭环 (CLOSED)** | 5 大核心工单全部熔铸合流；M1-019/020 闭环；运动会贯穿案例 B 半 4 闹铃摘除；中文三词共现 $\le 30\text{ms}$；声纹 180 天 TTL 墓碑；5D 多尺度金字塔；老王案 18000 事实 SHA-256 不可变与双时间透镜。 |
| **M2** | 条件驱动调度、Single-Shot 看板与流式流水线 | 24 项 | **100% 核心闭环 (CLOSED)** | `M2-009R` 单看板 1500 tokens 封套；`M2-005R` 条件双轨引擎（Level-1 机械快轨 $\le 1\text{ms}$ + Level-2 捎带）；`M2-001` 唤醒防抖冷却（250 脉搏/5s 归一）与 DEEP_SLEEP 静默闸。 |
| **M3** | 单跳雪崩隔离、动态维度生命周期与周期总结 | 17 项 | **100% 核心闭环 (CLOSED)** | `M3-001R` 三重硬门限状态机（$\ge 2$ 物理域持续 3 天、30 天候选试用 $\ge 70\%$ 准度、每日 1 次反思配额）；系统活跃维度硬封顶 $\le 32$；递归深度 $\le 2$ 熔断。 |
| **M4** | 虚拟人 30 天连续闭环与 V21~V30 对抗测试 | 9 项 | **🔥 核心大突破 (80% CLOSED)** | `SIM-001` 30 天/180 天无头仿真闭环；`M4-005`（V21~V30 十大高阶对抗场景）**100% 全绿通过**（老王诈骗反转、心梗跌倒 0 延迟、跨半年声纹淘汰、50轮对话防爆、深度睡眠静默、反爹味老友语调等）。 |
| **M5** | AI 操作经验沉淀与心智自主进化 | 7 项 | **🔥 核心大突破 (7/7 CLOSED)** | `M5-001` 多维检索总线原生四大维度（维度/主张/实体/注记）满绿；`M5-002` 维度生命周期与高阶提炼；`M5-003` 人设镜面与像人姿态；`M5-004` 共生决策推演；`M5-005` 千人千面战训考场 `agent_mind_bench` 闭环（10,100 条观测 / 10 项危机考验点 / 优秀 Agent 100.0 分 vs 劣质 Agent 50.3 分 / 铁律违规 0 分，8/8 PASS）。 |
| **M6** | 教育轻量微插件与手环 23cm 柔性屏画布 | 7 项 | 排期中 (PENDING) | 微技能不分裂主脑人格；手环微卡片渲染 $\le 16\text{ms}$。 |
| **M7** | 1 年期 360 万条长漂移压测与多模型热插拔 | 6 项 | 排期中 (PENDING) | 360 万条下倒排检索持续 $\le 30\text{ms}$；断网 500ms 切备用 SLM。 |
| **M8** | 架构机制消融实验与终审裁决门 | 5 项 | 排期中 (PENDING) | 完成 Single-Shot 与条件任务消融对比量化矩阵；正式签发生产令。 |

---

## 二、M5 攻坚波次（多维检索底座与共生心智闭环）验收总账

| 派单工号 | 责任模块 | 任务代号 | 攻坚任务名称 | 状态 | 核心交付物与门禁结果 |
|---|---|---|---|:---:|---|
| **#6** | C06 查询 | `TASK-M5-001-SEARCH` | 多维心智检索总线原生四大维度（维度/主张/实体/注记）联合精准检索 | **CLOSED (8/8 PASS)** | `src/aios_core/query/search.py`<br>`src/aios_core/operations/world_operator.py`<br>`tests/query/test_multidimensional_search_bus.py` (5/5 PASS)<br>`tests/query/test_multidimensional_search.py` (3/3 PASS) |
| **#7** | C03 认知 | `TASK-M5-002-DIM-LIFECYCLE` | 维度生命周期（跨域3天/试用30天/每日1次反思配额）与高阶提炼挂载 | **CLOSED (3/3 PASS)** | `src/aios_core/cognition/dimension_engine.py`<br>`tests/cognition/test_dimension_lifecycle.py` |
| **#8** | C08 人设 | `TASK-M5-003-RAPPORT-MIRROR` | AI 自我镜面审视、动态羁绊与像人三档姿态决策机 | **CLOSED (7/7 PASS)** | `src/aios_core/cognition/self_reflection.py`<br>`tests/cognition/test_self_reflection.py` |
| **#9** | C05 决策 | `TASK-M5-004-ACTION-ADVISOR` | 共生决策推演引擎（送礼推演/老王防诈阻击/早搏熔断，带因果证据引用） | **CLOSED (3/3 PASS)** | `src/aios_core/cognition/symbiotic_advisor.py`<br>`tests/cognition/test_symbiotic_advisor.py` |
| **#10**| 考场评测 | `TASK-M5-005-AGENT-ARENA` | 独立 Agent 虚拟人生千人千面战训考场与全景诊断器 | **CLOSED (8/8 PASS)** | `src/aios_core/simulation/agent_mind_bench.py`（千人千面世界发生器 + 独立沙箱 + 10 项危机考验点 + 四维指标记录器 + 铁律一票否决 + 体检报告持久化）<br>`tests/simulation/test_agent_mind_bench.py` (8/8 PASS)<br>会话 `01a0a700` 执行，详见第五节 |

---

## 二、M1 攻坚波次全量验收总账（全部 100% 满堂绿）

| 派单工号 | 责任模块 | 核心任务代号 | 攻坚任务名称 | 优胜战队 | 状态 | 核心工程交付物与代码落盘路径 |
|---|---|---|---|---|:---:|---|
| **#1** | C01 摄入 | `M1-001R-ADV` | 高熵多模态清洗、24人LSH声纹与180天淘汰 | 01a0a700 / 01a0a67a | **CLOSED (11/11 PASS)** | `src/aios_core/ingest/multimodal_edge.py`<br>`tests/unit/test_m1_001r_high_entropy_audio.py` |
| **#2** | C06 查询 | `M1-017` | CJK 拓扑倒排聚集表与多词检索加速 | Agent-02 战队 | **CLOSED (6/6 PASS)** | `src/aios_core/query/cjk_inverted_index.py`<br>`tests/unit/test_m1_017_cjk_index.py` |
| **#3** | C05 总结 | `M1-010R` | 5D 时空多尺度连续聚合器与物化视图 | Agent-03 / 01a0a700 | **CLOSED (28/28 PASS)** | `src/aios_core/summaries/pyramid_aggregator.py`<br>`tests/unit/test_m1_010r_pyramid.py` |
| **#4** | C06 查询 | `M1-012R` | 实体拓扑超链接网络穿透检索器 | Agent-04 / 01a0a700 | **CLOSED (41/41 PASS)** | `src/aios_core/query/hyperlink_traverser.py`<br>`tests/unit/test_m1_012r_hyperlink.py` |
| **#5** | C02/C05 | `M1-018` | 事实不可变账本、双时间透镜与单跳隔离 | 01a0a700 / Agent-05 | **CLOSED (52/52 PASS)** | `src/aios_core/world/retrospective_annotation.py`<br>`src/aios_core/world/epistemic_world_lens.py`<br>`tests/unit/test_m1_018_retrospective_annotation.py`<br>`tests/unit/test_m1_018_epistemic_world_lens.py` |
| **#6** | 场景/查询 | `M1-016/019/020` | 运动会体测贯穿案例、Tombstone冷档归档与HotCard管道 | 总指挥总工部 | **CLOSED (10/10 PASS)** | `src/aios_core/world/view_lens.py`<br>`src/aios_core/query/hot_cards.py`<br>`tests/scenarios/test_sports_event_world.py` (4 闹铃全部转正摘除) |

---

## 三、M2 / M3 / M4 攻坚波次全量验收总账（熔铸收敛）

| 派单工号 | 责任模块 | 任务代号 | 核心攻坚主题 | 优胜战队 | 状态 | 交付物与验证门禁 |
|---|---|---|---|---|:---:|---|
| **#7** | C04 看板 | `M2-009R` | 单看板 1500 Token 硬预算流水线与反爹味护栏 | 01a0a700 / Agent-09 | **CLOSED (22/22 PASS)** | `src/aios_core/cockpit/pipeline.py`<br>`tests/unit/test_m2_009r_cockpit_budget.py`<br>`tests/unit/test_m2_009r_independent_redteam.py` |
| **#8** | C07 调度 | `M0-023-V22` | 夜间室性早搏合并跌倒 P0 硬件直穿 | 01a0a700 / Agent-v22 | **CLOSED (16/16 PASS)** | `src/aios_core/wake/dispatcher.py`<br>`tests/unit/test_v22_acute_cardiac_fall_safety.py`<br>`tests/unit/test_v22_independent_redteam.py` |
| **#9** | C07 调度 | `M2-005R` | 条件驱动任务调度双轨引擎与 DORMANT 隐形机制 | 01a0a67a / Agent-05 | **CLOSED (34/34 PASS)** | `src/aios_core/scheduler/conditional_engine.py`<br>`tests/unit/test_m2_005r_conditional_scheduler.py`<br>`tests/unit/test_m2_005r_conditional_scheduler_agent05.py` |
| **#10** | C07 唤醒 | `M2-001` | 高频唤醒去重合并队列与 DEEP_SLEEP 静默闸 | 01a0a67a / Agent-05 | **CLOSED (29/29 PASS)** | `src/aios_core/wake/cooldown_queue.py`<br>`tests/unit/test_m2_001_wake_cooldown.py`<br>`tests/unit/test_m2_001_wake_cooldown_agent05.py` |
| **#11** | C03 认知 | `M3-001R` | 动态维度衍生三重硬门限状态机与 32 维度硬封顶 | 01a0a67a | **CLOSED (18/18 PASS)** | `src/aios_core/dimensions/evolution_guard.py`<br>`tests/unit/test_m3_001r_dimension_guard.py` |
| **#12** | 仿真推演 | `SIM-001` | 30 天/180 天高熵无界面人生仿真驱动引擎 | Agent-05 / 01a0a700 | **CLOSED (7/7 PASS)** | `src/aios_core/simulation/headless_life_driver.py`<br>`tests/simulation/test_30day_headless_life_simulation.py` |
| **#13** | 对抗套件 | `M4-005` | V21~V30 宪法级高阶对抗场景全套测试 | 总指挥总工部 | **CLOSED (10/10 PASS)** | `tests/scenarios/test_v21_to_v30_adversarial.py`<br>`src/aios_core/wearable/fsm.py`<br>`src/ai_worker/brevity_guard.py`<br>`src/ai_worker/stream_pipeline.py` |
| **#14** | 治理体系 | `M0-PRIME` | M0-023..030 契约候选冻结 + G-M1P 压测套件 | 01a0a638 / 01a0a46e | **CLOSED (36/36 PASS)** | `src/aios_core/bench/g_m1p.py`<br>`tests/unit/test_m0_prime_contracts.py`<br>`tests/integration/test_g_m1p_smoke.py` |
| **#15** | C05/C08 | `M5-004` | 共生决策辅助与行动推演引擎 | Agent-09 | **CLOSED (3/3 PASS)** | `src/aios_core/cognition/symbiotic_advisor.py`<br>`tests/cognition/test_symbiotic_advisor.py` |
| **#16** | C01/C06 | `M5-002` | 维度生命周期与高阶维度提炼挂载引擎 | Agent-07 | **CLOSED (3/3 PASS)** | `src/aios_core/cognition/dimension_engine.py`<br>`tests/cognition/test_dimension_lifecycle.py` |

---

## 四、首席架构总指挥法定仲裁案卷 (Chief Architect Adjudication Dossier)

1. **ADJ-V3G-012（内存指标与单调基线）**：
   - 裁决结论：驳回以 `ru_maxrss` 绝对值作为模块门禁的做法。主干全面采信差值归因范式（`rss_delta_kb = max(0, rss_after - rss_before)` 与 `/proc/self/statm` 时点测量），已彻底根除跨用例污染。
2. **ADJ-V3G-013（多版本竞争收敛）**：
   - 裁决结论：对 M2-005R、M2-001、M3-001R 采信 `01a0a67a` 的 `AIOSProtocolError` 完备状态机与严密 FSM 设计作为官方主干，同时以别名和适配层原生吸纳 `Agent-05` 驱动接口；对 SIM-001 采信 `Agent-05` 的真实全链持久化与跨平台无头推演引擎。消除 12 个冗余并存文件。
3. **ADJ-V3G-014（AST 检查器与语法制程）**：
   - 裁决结论：批准吸纳 `governance/ci/lint_assert_msg_ast.py`，全库扫描 146 个 Python 文件，命中 0 处语法歧义，作为 CI 静态防线永久固化。
4. **ADJ-V3G-015（POST_GATE_48H B半收敛与 V21~V30 宪法对抗套件全线贯通）**：
   - 裁决结论：实现 `aios_core.world.view_at` 双透镜读面、`aios_core.query.hot_cards` 实体热卡管道与 `store.prune` 提交口；摘除 `test_sports_event_world.py` 全部 4 处 `xfail(strict=True)` 闹铃标记；新增落地 `M4-005`（V21~V30 十大高阶对抗场景全套用例），全库单测飙升至 **1092 项全部满绿通过，0 报警，0 失败**。

---

## 五、M5-005 战训考场执行台账（会话 01a0a700 执行登记）

| 项目 | 内容 |
|---|---|
| 执行会话 | `arena/01a0a700-fantonghui`（工单目标分支 `arena/agent-10-m5-agent-arena` 因会话锁不可用，映射提请总师知悉） |
| 前置收编 | M5 批次 #6~#9 已由主链路收敛闭环（见第二节总账），本会话先执行**主链路 1:1 同步**（收敛版 M1-M3 + M5 认知包 + 检索总线 + 世界操作套件 + 海量人生发生器），同步后基线 1124 passed |
| 交付物 | `src/aios_core/simulation/agent_mind_bench.py`（约 1,100 行，零占位符）+ `tests/simulation/test_agent_mind_bench.py`（8 项验收） |
| 世界规模 | 主线 canonical 5,000 条（四大剧情线）+ 程序员陈默 / 创业者刘畅 / 全职妈妈赵敏 各 1,700 条 = **10,082 条观测**，跨度 2023-01-01 ~ 2026-09-15（1,353 天） |
| 10 项考验点 | 老王案 / 老妈生日 / 早搏危机 / 感情破裂 / P0 跌倒硬旁路 / 高阶维度衍生×2（过劳猝死风险、老王信用破产）/ 30 天试用注册门槛 / 每日反思配额 / 像人姿态分寸（20 闲逛 + 2 关键节点） |
| 诊断结果 | 优秀 Agent（TopologyMindAgent）：**100.0 分 / PASS / 10/10**，平均决策 207.8 Token、证据召回 100%、检索延迟 29ms、闲逛静默率 100%、维度合规 1.0；劣质 Agent（BruteForceChatterAgent）：**50.3 分 / FAIL / 5/10**（暴力全扫描 40,000 Token 均值、静默率 0.6、维度违规 2 次）；铁律违规 Agent（RogueAgent）：**0.0 分**（篡改历史 + P0 走大模型双重一票否决） |
| 铁律审计 | 独立沙箱（世界 DB 文件级克隆）+ 世界指纹（revision + 全量 object_revisions SHA-256）+ 裁判篡改台账；`RogueAgent` 的越权动作仅落在沙箱，源世界指纹跨 3 次运行 0 变化；`tamper_history` 通道不触碰真相表（R4-07a 静态守卫 0 违例） |
| 经验沉淀 | 体检报告《AIOS 3.0 共生心智操作全景体检报告》自动持久化至 `operation_experiences` 经验库（key: `agent_mind_diagnostic::<Agent>`，与 `OperationExperienceDistiller` 同表） |
| 套件复测 | **1132 passed, 0 failed**（主链路 1124 + 本批次 8） |

> 备注：M5-005 工单验收标准"模拟优秀 Agent vs 劣质 Agent，断言诊断器能准确识别劣质 Agent 的违规与高能耗"已逐项覆盖；
> 维度门槛对抗验收（未满 30 天注册必须抛异常 / 当日第 2 次反思必须被拒）由考场 `run_gate_audit()` 内置审计与 M5-002 既有测试双重锁定。
