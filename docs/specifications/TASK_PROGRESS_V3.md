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
| **#1** | C01 摄入 | `M1-001R` | 端侧多模态轻量摄入与声纹淘汰 | Agent-01 战队 | **DISPATCHED** | `src/aios_core/ingest/multimodal_edge.py`<br>`tests/unit/test_m1_001r_edge_cleaner.py` |
| **#2** | C06 查询 | `M1-017` | CJK 拓扑倒排聚集表与多词检索加速 | Agent-02 战队 | **DISPATCHED** | `src/aios_core/query/cjk_inverted_index.py`<br>`tests/unit/test_m1_017_cjk_index.py` |
| **#3** | C05 总结 | `M1-010R` | 5D 时空多尺度连续聚合器与物化视图 | Agent-03 战队 | **CODED / 单测 25 项全绿（待总工沙箱验收）** | `src/aios_core/summaries/pyramid_aggregator.py`<br>`tests/unit/test_m1_010r_pyramid.py` |
| **#4** | C06 查询 | `M1-012R` | 实体拓扑超链接网络穿透检索器 | Agent-04 战队 | **DISPATCHED** | `src/aios_core/query/hyperlink_traverser.py`<br>`tests/unit/test_m1_012r_hyperlink.py` |
| **#5** | C02/C05 | `M1-018` | 认知反向传播语义图层契约 (老王案) | Agent-05 战队 | **DISPATCHED** | `src/aios_core/world/retrospective_annotation.py`<br>`tests/unit/test_m1_018_retrospective_annotation.py` |
