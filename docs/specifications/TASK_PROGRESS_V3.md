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
| **M1** | 共同世界、多模态清洗与 CJK 倒排 | 20 项 | **🔥 当前攻坚 (IN PROGRESS)** | 拒存原始大图；中文三词共现检索 $\le 30\text{ms}$；声纹 180 天 TTL 墓碑；5D 多尺度连续下钻 $\le 45\text{ms}$。 |
| **M2** | 条件驱动调度、Single-Shot 看板与流式流水线 | 24 项 | 排期中 (PENDING) | 彻底废黜 13 步循环；看板装配 $\le 1500\text{tokens}$；首字响应平稳且质量第一；手环微震零误触。 |
| **M3** | 单跳雪崩隔离、动态维度生命周期与周期总结 | 17 项 | 排期中 (PENDING) | 历史推翻单跳失效隔离；并发重算锁定 $\le 3$；系统活跃维度受控 $\le 32$。 |
| **M4** | 虚拟人 30 天连续闭环与 V21~V30 对抗测试 | 9 项 | 排期中 (PENDING) | 30 天虚拟推演 0 死锁；V21~V30 场景 pytest 全绿通过。 |
| **M5** | AI 操作经验沉淀与工具自主进化 | 7 项 | 排期中 (PENDING) | 经验库安全落盘；非安全主动提醒阈值自适应拉长。 |
| **M6** | 教育轻量微插件与手环 23cm 柔性屏画布 | 7 项 | 排期中 (PENDING) | 微技能不分裂主脑人格；手环微卡片渲染 $\le 16\text{ms}$。 |
| **M7** | 1 年期 360 万条长漂移压测与多模型热插拔 | 6 项 | 排期中 (PENDING) | 360 万条下倒排检索持续 $\le 30\text{ms}$；断网 500ms 切备用 SLM。 |
| **M8** | 架构机制消融实验与终审裁决门 | 5 项 | 排期中 (PENDING) | 完成 Single-Shot 与条件任务消融对比量化矩阵；正式签发生产令。 |

---

## 二、M1 当前攻坚波次：五大 Agent 并行派单登记册

| 派单工号 | 责任模块 | 核心任务代号 | 攻坚任务名称 | 派发对象 | 状态 | 核心工程交付物与代码落盘路径 |
|---|---|---|---|---|:---:|---|
| **#1** | C01 摄入 | `M1-001R` | 端侧多模态轻量摄入与声纹淘汰 | Agent-01 战队 | **ADV 加固版已交付（本会话，单测 11 项全绿，待总工沙箱验收）** | `src/aios_core/ingest/multimodal_edge.py`<br>`tests/unit/test_m1_001r_high_entropy_audio.py` |
| **#2** | C06 查询 | `M1-017` | CJK 拓扑倒排聚集表与多词检索加速 | Agent-02 战队 | **DISPATCHED** | `src/aios_core/query/cjk_inverted_index.py`<br>`tests/unit/test_m1_017_cjk_index.py` |
| **#3** | C05 总结 | `M1-010R` | 5D 时空多尺度连续聚合器与物化视图 | Agent-03 战队 | **CODED / 单测 25 项全绿（待总工沙箱验收）** | `src/aios_core/summaries/pyramid_aggregator.py`<br>`tests/unit/test_m1_010r_pyramid.py` |
| **#4** | C06 查询 | `M1-012R` | 实体拓扑超链接网络穿透检索器 | Agent-04 战队 | **CODED / 单测 15 项全绿（待总工沙箱验收）** | `src/aios_core/query/hyperlink_traverser.py`<br>`tests/unit/test_m1_012r_hyperlink.py` |
| **#5** | C02/C05 | `M1-018` | 认知反向传播语义图层契约 (老王案) | Agent-05 战队 | **CODED / 单测 18 项全绿（待总工沙箱验收）** | `src/aios_core/world/retrospective_annotation.py`<br>`tests/unit/test_m1_018_retrospective_annotation.py` |
| **#6** | C04 工作台 | `M2-009R` | 高密危机单看板 1500 Token 物理截断流水线 | Agent-05 战队 | **CODED / 单测 11 项全绿（待总工沙箱验收）** | `src/aios_core/cockpit/pipeline.py`<br>`tests/unit/test_m2_009r_cockpit_budget.py` |
| **#7** | C03 唤醒 | `M0-023-V22` | 跨模态心血管突发危机 P0 硬件直穿快速通道 | Agent-05 战队 | **CODED / 单测 5 项全绿（待总工沙箱验收）** | `src/aios_core/wake/dispatcher.py`<br>`tests/unit/test_v22_acute_cardiac_fall_safety.py` |

---

## 三、独立红队验收批次登记（agent-05-redteam-batch-20260916，2026-09-16 追加，纯增量）

> 总师指令："将这些任务逐个跑完，然后都提交推送，**不要覆盖任何版本，独立起名**。"
> 本批次对已合流至 `arena/01a0a700-fantonghui` 的四个工单交付物做**独立命名**的对抗性复核层。
> 全部交付物为**新增文件**（独立命名），未修改、未覆盖任何既有版本与既有测试；
> 全仓回归 **704 passed**（基线 651 + 新增红队 53）。

| 红队层（独立命名） | 复核对象（既有版本，未触碰） | 新增测试数 | 关键对抗口径 |
|---|---|:---:|---|
| `tests/unit/test_m1_018_independent_redteam.py` | M1-018 `world/retrospective_annotation.py` | 14 | 倒写强校验 / 双时间戳 now 锚点 / 图层零提前泄露 / naive-UTC 契约 / 跨实例哈希确定性 / 非 JSON fail-closed / 级联动态图语义 / 2,000 事实 + 3,211 节点 5 层网络独立复测 |
| `tests/unit/test_m2_009r_independent_redteam.py` | M2-009R `cockpit/pipeline.py` | 11 | 200 轮深滚动（窗口 6 / 归档 194 / 证据链有序无损）/ 组装 P95 ≤15ms / 20k 字巨型轮硬帽 ≤1500 / BrevityGuard 模式规避说教硬截断 / 提示词字节级确定性 |
| `tests/unit/test_v22_independent_redteam.py` + `wake/v22_hardware_first.py` | M0-023-V22 `wake/dispatcher.py` | 11 | 畸形 P0"先脉冲后降级"绝不静音 SOS / 降级审计不伪造 hazard_type / 脉冲失败回执诚实 / 复合体征快照逐字节透传 / 100 次 P0 突发 ≤50ms / 5ms 慢脉冲仍达标 / 非 P0 严格隔离 |
| `tests/unit/test_m1_001r_adv_independent_redteam.py` | M1-001R-ADV `ingest/multimodal_edge.py` | 17 | 180 天 TTL 整点边界（179d23h59m59s 仍活跃）/ 错峰到期 / 360 天 15 未绑定全墓碑 vs 8 绑定永驻 / 墓碑复活 / LSH 24 人 720 切片 100% 纯净 / 类内-类间汉明间隙 / 未知第 25 人异常可检测 / RawByteSink 2,000 垃圾粉碎 0 残留 + 3,000 张 ≤30ms / 画质 0.4 边界与昏暗 ×0.3 崩塌 |

**红队审计发现（3 项，均留档于对应红队层测试，未改既有版本）：**

1. **V22 畸形 P0 审计回执丢失**：V1 主链在硬件脉冲发出**之后**构造收据阶段对畸形 `safety_bypass` 抛 `AttributeError` —— SOS 送达但审计回执丢失。已由新增 `wake/v22_hardware_first.py::safe_dispatch_v22` 兜底（先脉冲 → 返回 `SAFETY_BYPASS_EXECUTED_DEGRADED` 降级审计，`hazard_type=None` 不伪造）；V1 主链保持原样。
2. **M1-018 naive 切片锚点 × aware 注记 overlap 崩溃**：`_ranges_overlap` 比较前未归一化切片边界 → `TypeError`。事实侧/视图侧均按 UTC 归一化，唯 overlap 路径漏归一化。留档为硬化候选，**提请总师裁定**（本批次不改既有版本）。
3. **BrevityGuard 纯标点输入**："…………" 会被计为 1~3 句"标点句"（结构约束成立、信息量为零）。留档为增强候选（信息量兜底），不影响 1~3 句硬门禁。

**分支与谱系**：全部提交至 `arena/01a0a700-fantonghui`（会话锁定分支）。谱系：`7785aed`（M1-018 增量硬化合流点，基线 651）→ 本批次 4 个独立提交 → 治理登记。既有版本 `b0c540a` / `8f21987` / `29d115f` / `db40aa0` / `0f097c4` 均保留于历史、未被覆盖。
