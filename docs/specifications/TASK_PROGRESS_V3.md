# AIOS 3.0 全量工程开发进度总表与派工台账

> **基准宪法**：`docs/constitution/AIOS核心系统宪法v3.0.md`  
> **核心仓库**：`aios-2.0` / `aios-3.0`  
> **总指挥部**：首席架构总工  
> **最后更新**：2026-09-16  
> **当前状态**：**1095 passed, 0 xfailed, 0 failed (100% 满堂绿)**

---

## 一、全生命周期里程碑进度全景

| 里程碑 | 主题与核心攻坚方向 | 规划任务数 | 状态 | 交付物与关键门禁 (Gate Assertion) |
|---|---|:---:|:---:|---|
| **M0** | 世界契约底座与生命安全熔断 | 23 项 | **100% 已闭环 (CLOSED)** | 既有 535 项单测全绿；M0-023 生命安全熔断直通穿透 $\le 50\text{ms}$；已正式签发 M0 封关令。 |
| **M1** | 共同世界、多模态清洗与 CJK 倒排 | 20 项 | **100% 已闭环 (CLOSED)** | 5 大核心工单全部熔铸合流；M1-019/020 闭环；运动会贯穿案例 B 半 4 闹铃摘除；中文三词共现 $\le 30\text{ms}$；声纹 180 天 TTL 墓碑；5D 多尺度金字塔；老王案 18000 事实 SHA-256 不可变与双时间透镜。 |
| **M2** | 条件驱动调度、Single-Shot 看板与流式流水线 | 24 项 | **100% 核心闭环 (CLOSED)** | `M2-009R` 单看板 1500 tokens 封套；`M2-005R` 条件双轨引擎（Level-1 机械快轨 $\le 1\text{ms}$ + Level-2 捎带）；`M2-001` 唤醒防抖冷却（250 脉搏/5s 归一）与 DEEP_SLEEP 静默闸。 |
| **M3** | 单跳雪崩隔离、动态维度生命周期与周期总结 | 17 项 | **100% 核心闭环 (CLOSED)** | `M3-001R` 三重硬门限状态机（$\ge 2$ 物理域持续 3 天、30 天候选试用 $\ge 70\%$ 准度、每日 1 次反思配额）；系统活跃维度硬封顶 $\le 32$；递归深度 $\le 2$ 熔断。 |
| **M4** | 虚拟人 30 天连续闭环与 V21~V30 对抗测试 | 9 项 | **🔥 核心大突破 (80% CLOSED)** | `SIM-001` 30 天/180 天无头仿真闭环；`M4-005`（V21~V30 十大高阶对抗场景）**100% 全绿通过**（老王诈骗反转、心梗跌倒 0 延迟、跨半年声纹淘汰、50轮对话防爆、深度睡眠静默、反爹味老友语调等）。 |
| **M5** | AI 操作经验沉淀与心智自主进化 | 7 项 | **🔥 核心大突破 (6/7 CLOSED)** | `M5-001` 多维检索总线原生四大维度（维度/主张/实体/注记）满绿；`M5-002` 维度生命周期与高阶提炼；`M5-003` 人设镜面与像人姿态；`M5-004` 共生决策推演；`M5-005` 千人千面海量战训考场就绪。 |
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
| **#10**| 考场评测 | `TASK-M5-005-AGENT-ARENA` | 独立 Agent 虚拟人生千人千面战训考场与全景诊断器 | **EXECUTING** | 派发云端大兵团多 Agent 战队并发实测与经验沉淀 |

---

## 三、全功能海量盲测与缺口补齐工单总账 (34 项工单全量就绪)

> **云端并发指令**：全量提示词已落盘至 `governance/dispatches/`，云端 Agent 可并发读取对应源码与宪法条文进行盲测与机制突破。严禁自编自答，严禁单一老套案例，全面覆盖人生百态！

### 1. 架构缺口补齐工单 (GAP Prompts - 4 项)
存放路径：`governance/dispatches/gap_prompts/`

| 工单编号 | 任务代号与名称 | 宪法条文 | 状态 | 目标模块路径 |
|---|---|---|:---:|---|
| **GAP-001** | 叙事分段 (NarrativeSegment) 模型与切片管线构建 | 第八章 第29条 / 第24章 | **DISPATCHED** | `contracts/models.py`, `narrative/segmenter.py` |
| **GAP-002** | 维度曲线数据点 (DimensionCurvePoint) 与高阶认知导数引擎 | 第七章 第23条 | **DISPATCHED** | `contracts/models.py`, `curves/dimension_curve.py` |
| **GAP-003** | 工具提案 (ToolProposal) 全生命周期管线与自适应演化 | 第二十章 第70条 / 第28章 | **DISPATCHED** | `contracts/models.py`, `tools/proposal_pipeline.py` |
| **GAP-004** | 沟通体验 (CommunicationExperience) 记录与自适应共生风格 | 第三章 第12条 / 第20章第69条 | **DISPATCHED** | `contracts/models.py`, `communication/experience_tracker.py` |

### 2. 全功能海量盲测与机制优化工单 (Mass Test Prompts - 30 项)
存放路径：`governance/dispatches/mass_test_prompts/`

| 编号 | 测试功能主题 | 核心代表场景 (人生百态) | 铁律约束 | 状态 |
|---|---|---|:---:|:---:|
| **MT-001** | 传感器波形特征轻量化提炼盲测 | 马拉松间歇跑 vs 伏案久坐 vs 楼梯踩空 | 严禁 50Hz 直灌 DB | **READY** |
| **MT-002** | 多模态图文抽取与声纹实体动态绑定 | 嘈杂创业沙龙多方会谈 / 医院急诊室抓拍 | 不存原始大图/音频 | **READY** |
| **MT-003** | 垃圾数据智能剪枝与物理删除盲测 | 商圈闲逛叫卖杂音 vs 傍晚商业合同借据原话 | 铁律4 (大模型自主删) | **READY** |
| **MT-004** | 22种核心对象CRUD与三类时间解耦一致性 | 跨年历史事件迟到补录 (3年前旧事今日说) | 发生/获知/写入三分离 | **READY** |
| **MT-005** | 实体与关系动态演变及时间快照盲测 | 高中死党变合伙人反目决裂十年后复和 | 实体ID永恒锁定 | **READY** |
| **MT-006** | 维度自主创建与生命周期状态机盲测 | 从零自学滑翔伞/自律戒糖新维度演进 | 状态机流转准入准出 | **READY** |
| **MT-007** | 新维度衍生三重硬门槛拦截盲测 | 熬夜诱导慢性绝症假说 vs 连续一月重创 | 铁律5 (三重硬门槛) | **READY** |
| **MT-008** | 事实主张(Claim)严格分类与置信度解耦 | 醉酒夸海口下月必收购腾讯已谈妥 | 11类主张严格切分 | **READY** |
| **MT-009** | 证据集合(EvidenceSet)动态聚合与复核 | 连续两周体检报告迟到冲击原结论 | 正反证据分离与STALE | **READY** |
| **MT-010** | 事件跨维度共振合成与状态流转盲测 | 突发火灾撤离事件多源对冲与修正 | 状态演变保留历史指针 | **READY** |
| **MT-011** | 高阶认知维度速度与加速度(导数)盲测 | 博士论文重压期身心崩溃加速与减速 | 严禁底层硬件做导数 | **READY** |
| **MT-012** | 认知回溯单跳隔离与双透镜只读注解 | 多年信任伙伴今日被法院裁定诈骗潜逃 | 铁律2 (老王案防雪崩) | **READY** |
| **MT-013** | 目标(Goal)推断验证与用户否认修正状态机 | 替表弟查考公资料被误判为自身目标 | 推断目标可撤销/终止 | **READY** |
| **MT-014** | 假说-演绎闭环预测(Prediction)对撞评分 | 预测新产品三天必破万单 vs 现实惨淡 | 必须含立项理由与对撞 | **READY** |
| **MT-015** | 时间金字塔多尺度摘要无损穿透下钻盲测 | 退休老干部五年慢性病演进历程 | 总结是新层非压缩删除 | **READY** |
| **MT-016** | 非线性人生相变(LifeChapter)基线重塑 | 校园步入职场 / 重病大手术生活重塑 | 去参数化基线断裂 | **READY** |
| **MT-017** | P0紧急特权硬旁路防线与0模型调用穿透 | 独居老人严重跌倒昏迷 / 急性心梗骤停 | 铁律3 (≤50ms, 0大模型) | **READY** |
| **MT-018** | 触发器机械去重冷却与长平稳微心跳探底 | 颠簸虚假抖动 vs 连续5小时静默日常 | 情境方便度与微心跳 | **READY** |
| **MT-019** | 条件驱动任务(Task)双轨休眠与零Token空转 | 等待半年后某会议召开才提醒 | 严禁无成熟条件遍历 | **READY** |
| **MT-020** | 驾驶舱清单(CockpitManifest)四步序单次装载 | 深夜突发唤醒一次性装载极简看板 | 严禁多轮问答式组装 | **READY** |
| **MT-021** | 活跃前台窗口与后台切片防溢出盲测 | 连续深度长聊80轮(上万字)人际困境吐槽 | 5~8轮前台+后台异步流 | **READY** |
| **MT-022** | 多关键词共现拓扑召唤与超链接因果穿透 | 跨越三年复合线索[初恋,银杏叶,车祸,误解] | 拒绝弱智金鱼失忆 | **READY** |
| **MT-023** | 5D生物时间镜头缩放仪自由推移盲测 | 微观心律脉冲瞬間自由缩放至大学四年 | 1s~10y 尺度自由缩放 | **READY** |
| **MT-024** | 操作经验(OperationExperience)蒸馏进化 | 通读十年人生到秒级多维联合定位进化史 | 检索策略与路标沉淀 | **READY** |
| **MT-025** | 沟通策略进化(CommunicationExperience)博弈 | 自尊心极强高管：从温柔到铁血直言 | 专属共生风格自演化 | **READY** |
| **MT-026** | 黑盒认知与“零交互问卷/零UI”违宪拦截 | 诱导AI弹出A/B选项选择题或图谱后台 | 一票否决严禁做题UI | **READY** |
| **MT-027** | AI分寸感自涌现与反谄媚、反教师爷立场 | 用户犯浑要求附和 / 倾诉时严禁背大道理 | 真实善意防线与自尊 | **READY** |
| **MT-028** | 1~3句话极简日常表达与防长篇客服综合症 | 用户说“今天有点烦”，骨传导简短接话 | 铁律1 (适配手环扫读) | **READY** |
| **MT-029** | 叙事分段(NarrativeSegment)主题切割盲测 | 考研复习周期与初创求职并行的多线交织 | 主题内聚度与切割断点 | **READY** |
| **MT-030** | 维度曲线(DimensionCurvePoint)趋势拐点预警 | 连续高压下精力衰竭加速与猝死前夕警报 | 拐点检测与早期熔断 | **READY** |

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
