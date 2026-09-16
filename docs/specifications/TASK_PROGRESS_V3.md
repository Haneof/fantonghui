# AIOS 3.0 全量工程开发进度总表与派工台账

> **基准宪法**：`docs/constitution/AIOS核心系统宪法v3.0.md`  
> **核心仓库**：`aios-2.0` @ `51268f5`  
> **总指挥部**：首席架构总工  
> **最后更新**：2026-09-16  

---

## 一、全生命周期里程碑进度全景

| 里程碑 | 主题与核心攻坚方向 | 规划任务数 | 状态 | 交付物与关键门禁 (Gate Assertion) |
|---|---|:---:|:---:|---|
| **M0** | 世界契约底座与生命安全熔断 | 23 项 | **100% 已闭环 (CLOSED)** | 既有 535 项单测全绿；M0-023 生命安全熔断直通穿透 $\le 50\text{ms}$；已正式签发 M0 封关令。 |
| **M1** | 共同世界、多模态清洗与 CJK 倒排 | 20 项 | **100% 已闭环 (CLOSED)** | 5 大核心工单全部熔铸合流；拒存原始大图；中文三词共现 $\le 30\text{ms}$；声纹 180 天 TTL 墓碑；5D 多尺度金字塔；老王案 18000 事实 SHA-256 不可变与双时间透镜。 |
| **M2** | 条件驱动调度、Single-Shot 看板与流式流水线 | 24 项 | **100% 核心闭环 (CLOSED)** | `M2-009R` 单看板 1500 tokens 封套；`M2-005R` 条件双轨引擎（Level-1 机械快轨 $\le 1\text{ms}$ + Level-2 捎带）；`M2-001` 唤醒防抖冷却（250 脉搏/5s 归一）与 DEEP_SLEEP 静默闸。 |
| **M3** | 单跳雪崩隔离、动态维度生命周期与周期总结 | 17 项 | **100% 核心闭环 (CLOSED)** | `M3-001R` 三重硬门限状态机（$\ge 2$ 物理域持续 3 天、30 天候选试用 $\ge 70\%$ 准度、每日 1 次反思配额）；系统活跃维度硬封顶 $\le 32$；递归深度 $\le 2$ 熔断。 |
| **M4** | 虚拟人 30 天连续闭环与 V21~V30 对抗测试 | 9 项 | **🔥 当前攻坚 (IN PROGRESS)** | `SIM-001` 30 天/180 天高熵人生仿真驱动引擎闭环（720 小时流、120 会议、3 危机、0 死锁、0 原始大图滞留、月度 2.55M Token 封套）；V22 硬件直穿穿透。 |
| **M5** | AI 操作经验沉淀与工具自主进化 | 7 项 | 排期中 (PENDING) | 经验库安全落盘；非安全主动提醒阈值自适应拉长。 |
| **M6** | 教育轻量微插件与手环 23cm 柔性屏画布 | 7 项 | 排期中 (PENDING) | 微技能不分裂主脑人格；手环微卡片渲染 $\le 16\text{ms}$。 |
| **M7** | 1 年期 360 万条长漂移压测与多模型热插拔 | 6 项 | 排期中 (PENDING) | 360 万条下倒排检索持续 $\le 30\text{ms}$；断网 500ms 切备用 SLM。 |
| **M8** | 架构机制消融实验与终审裁决门 | 5 项 | 排期中 (PENDING) | 完成 Single-Shot 与条件任务消融对比量化矩阵；正式签发生产令。 |

---

## 二、M1 攻坚波次全量验收总账（全部 100% 满堂绿）

| 派单工号 | 责任模块 | 核心任务代号 | 攻坚任务名称 | 优胜战队 | 状态 | 核心工程交付物与代码落盘路径 |
|---|---|---|---|---|:---:|---|
| **#1** | C01 摄入 | `M1-001R-ADV` | 高熵多模态清洗、24人LSH声纹与180天淘汰 | 01a0a700 / 01a0a67a | **CLOSED (11/11 PASS)** | `src/aios_core/ingest/multimodal_edge.py`<br>`tests/unit/test_m1_001r_high_entropy_audio.py` |
| **#2** | C06 查询 | `M1-017` | CJK 拓扑倒排聚集表与多词检索加速 | Agent-02 战队 | **CLOSED (6/6 PASS)** | `src/aios_core/query/cjk_inverted_index.py`<br>`tests/unit/test_m1_017_cjk_index.py` |
| **#3** | C05 总结 | `M1-010R` | 5D 时空多尺度连续聚合器与物化视图 | Agent-03 / 01a0a700 | **CLOSED (28/28 PASS)** | `src/aios_core/summaries/pyramid_aggregator.py`<br>`tests/unit/test_m1_010r_pyramid.py` |
| **#4** | C06 查询 | `M1-012R` | 实体拓扑超链接网络穿透检索器 | Agent-04 / 01a0a700 | **CLOSED (41/41 PASS)** | `src/aios_core/query/hyperlink_traverser.py`<br>`tests/unit/test_m1_012r_hyperlink.py` |
| **#5** | C02/C05 | `M1-018` | 事实不可变账本、双时间透镜与单跳隔离 | 01a0a700 / Agent-05 | **CLOSED (52/52 PASS)** | `src/aios_core/world/retrospective_annotation.py`<br>`src/aios_core/world/epistemic_world_lens.py`<br>`tests/unit/test_m1_018_retrospective_annotation.py`<br>`tests/unit/test_m1_018_epistemic_world_lens.py` |

---

## 三、M2 / M3 / SIM-001 攻坚波次全量验收总账（熔铸收敛）

| 派单工号 | 责任模块 | 任务代号 | 核心攻坚主题 | 优胜战队 | 状态 | 交付物与验证门禁 |
|---|---|---|---|---|:---:|---|
| **#6** | C04 看板 | `M2-009R` | 单看板 1500 Token 硬预算流水线与反爹味护栏 | 01a0a700 / Agent-09 | **CLOSED (22/22 PASS)** | `src/aios_core/cockpit/pipeline.py`<br>`tests/unit/test_m2_009r_cockpit_budget.py`<br>`tests/unit/test_m2_009r_independent_redteam.py` |
| **#7** | C07 调度 | `M0-023-V22` | 夜间室性早搏合并跌倒 P0 硬件直穿 | 01a0a700 / Agent-v22 | **CLOSED (16/16 PASS)** | `src/aios_core/wake/dispatcher.py`<br>`tests/unit/test_v22_acute_cardiac_fall_safety.py`<br>`tests/unit/test_v22_independent_redteam.py` |
| **#8** | C07 调度 | `M2-005R` | 条件驱动任务调度双轨引擎与 DORMANT 隐形机制 | 01a0a67a / Agent-05 | **CLOSED (34/34 PASS)** | `src/aios_core/scheduler/conditional_engine.py`<br>`tests/unit/test_m2_005r_conditional_scheduler.py`<br>`tests/unit/test_m2_005r_conditional_scheduler_agent05.py` |
| **#9** | C07 唤醒 | `M2-001` | 高频唤醒去重合并队列与 DEEP_SLEEP 静默闸 | 01a0a67a / Agent-05 | **CLOSED (29/29 PASS)** | `src/aios_core/wake/cooldown_queue.py`<br>`tests/unit/test_m2_001_wake_cooldown.py`<br>`tests/unit/test_m2_001_wake_cooldown_agent05.py` |
| **#10** | C03 认知 | `M3-001R` | 动态维度衍生三重硬门限状态机与 32 维度硬封顶 | 01a0a67a | **CLOSED (18/18 PASS)** | `src/aios_core/dimensions/evolution_guard.py`<br>`tests/unit/test_m3_001r_dimension_guard.py` |
| **#11** | 仿真推演 | `SIM-001` | 30 天/180 天高熵无界面人生仿真驱动引擎 | Agent-05 / 01a0a700 | **CLOSED (7/7 PASS)** | `src/aios_core/simulation/headless_life_driver.py`<br>`tests/simulation/test_30day_headless_life_simulation.py` |
| **#12** | 治理体系 | `M0-PRIME` | M0-023..030 契约候选冻结 + G-M1P 压测套件 | 01a0a638 / 01a0a46e | **CLOSED (36/36 PASS)** | `src/aios_core/bench/g_m1p.py`<br>`tests/unit/test_m0_prime_contracts.py`<br>`tests/integration/test_g_m1p_smoke.py` |

---

## 四、首席架构总指挥法定仲裁案卷 (Chief Architect Adjudication Dossier)

1. **ADJ-V3G-012（内存指标与单调基线）**：
   - 裁决结论：驳回以 `ru_maxrss` 绝对值作为模块门禁的做法（量错对象）。主干全面采信差值归因范式（`rss_delta_kb = max(0, rss_after - rss_before)` 与 `/proc/self/statm` 时点测量），已彻底根除跨用例污染。
2. **ADJ-V3G-013（多版本竞争收敛）**：
   - 裁决结论：对 M2-005R、M2-001、M3-001R 采信 `01a0a67a` 的 `AIOSProtocolError` 完备状态机与严密 FSM 设计作为官方主干，同时以别名和适配层原生吸纳 `Agent-05` 驱动接口；对 SIM-001 采信 `Agent-05` 的真实全链持久化与跨平台无头推演引擎。主干统一收敛至 `src/aios_core/{scheduler,wake,dimensions,simulation}`，消除了 12 个冗余并存文件的膨胀，门禁取全部战队之**最大并集**（1082 项测试全部绿透）。
3. **ADJ-V3G-014（AST 检查器与语法制程）**：
   - 裁决结论：批准吸纳 `01a0a631` 提交的 `governance/ci/lint_assert_msg_ast.py`，全库扫描 135 个 Python 文件，命中 0 处语法歧义，作为 CI 静态防线永久固化。



