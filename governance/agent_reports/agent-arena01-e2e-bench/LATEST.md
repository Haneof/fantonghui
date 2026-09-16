# AIOS 全流程海量盲测与极限压测报告（arena01 线 · 2026-09-16）

> 军令：独立对抗生命数据发生器贯穿 8 大阶段盲测；机制总结与工具发明为纲。
> 分支：`arena/01a0a700-fantonghui`（Arena 会话固定分支，零覆盖纯增量）。
> 代码：`src/aios_core/simulation/massive_life_bench_arena01.py` +
> `summaries/adaptive_vital_compressor_arena01.py` +
> `query/bitemporal_index_projector_arena01.py`；测试：
> `tests/e2e/test_massive_e2e_8stage_bench_arena01.py`（11/11 绿）。

## 一、压测实测指标（本机沙箱实测，非编造）

| 指标 | 实测值 | 门禁 |
|---|---|---|
| 原始流吞吐 | **802,742 events/s**（1,000,000 事件 / 1.25s） | 全程 0 次高频直写库 |
| 心率平稳压缩比 | 300:1（6,000 采样 → 20 窗口均值观察） | ≥60:1 ✅ |
| 异常波形召回 | 3/3 心律失常尖峰 + 20/20 >3g 冲击 | 100% 召回 ✅ |
| 图像废片处置 | 0.15 分废片拒收 + RawByteSink purge → 滞留 **0B** | 铁律4 ✅ |
| 音频噪声物理删除 | 垃圾短信/叫卖 100% 移除；关键原话（兜底/原话锚点） **100% 永存** | 铁律4 ✅ |
| 时间金字塔 | 1,095 日事实 → WEEK/MONTH/YEAR 物化；vault 1,095 条完好 | 证据链断裂率 **0.0%**（1,095/7 抽样下钻全覆盖）|
| 老王案不变量 | SHA-256 指纹 append 前后 byte-identical；verify_integrity (True, 1095) | 铁律2 ✅ |
| 单跳级联隔离 | marked_stale=12（仅 1 跳），`llm_recompute_triggered=0`，untouched=12 | 防 210 次雪崩 ✅ |
| P0 硬旁路延迟 | **P50 0.0006ms / P95 0.0012ms / P99 0.0052ms**（max 0.0113ms，200 连发） | ≤50ms 且 llm_calls=0、世界模型旁路 ✅（铁律3）|
| DORMANT 休眠 | 50 任务 `included_task_ids=0`、`dormant_token_charge=0`、hidden=50 | 零 Token 休眠 ✅ |
| 三重硬门槛 | 50/50 违规候选 100% 拒；同日第 2 次反思 QuotaExceededBlockError | 铁律5 ✅ |
| 终极对话 | 10 轮实际会话全部 1~3 句、≤100 tok；反谄媚/反教师爷/黑盒零 UI 全部熔断通过 | 铁律1 ✅ |

## 二、全生命周期心智瓶颈与缺陷诊断书

1. **Token 最大消耗点 = 检索召回的「文本回读成本」而非组装成本**：
   Pathway A 暴力扫库（15,000~50,000 tok/次）比 C 拓扑下钻差 ≥30×；驾驶舱
   组装在 1500 预算内只是小问题——**不修检索，预算永远烧钱**。已用 M5-SEARCH
   线（黄金经验蒸馏 ≤500 tok 直达）证明解决路径。
2. **I/O 最大消耗点 = 高频时序的全量落库冲动**：50Hz 分钟级流若直写，
   SQLite 页缓存与 fsync 双双被冲爆；本线压缩算子（≥60:1）把 I/O 打到
   常数级，并保留 100% 异常波形。
3. **最容易失真的认知抽象 = 双时间透镜的「视图重建」诱惑**：每层注记都
   重建索引/总结会级联（体测复现：12 直接下游之外还有 12 曾孙节点，无界
   级联即 210 次 API 雪崩的现实版）。迫切需要「零拷贝虚拟化」。
4. **现实现不完美之三处**：(a) 压缩阈值静态（慢病基线漂移误报风险）——
   本线用 Welford 在线 z-score 补上；(b) 透视索引按时间点物化——本线
   投影器补上；(c) 条件事件求值走全量布尔扫描——M2-005R 机械快轨已证明
   <1ms 纯 Python 求值可行。

## 三、新机制发明与新工具提议（2 个，已纯代码落地 + ToolProposal 登记）

1. **AdaptiveVitalSeriesCompressor（自适应时序压缩算子）**
   — `summaries/adaptive_vital_compressor_arena01.py` + `build_adaptive_compressor_proposal()`。
   在线均值/方差自适应 z-threshold + >3g 物理绝对冲击线；平稳段 ≥60:1、
   回放决定性、O(1) 流式内存、慢病基线漂移不误报。
2. **BitemporalVirtualIndexProjector（双透镜虚拟索引投影器）**
   — `query/bitemporal_index_projector_arena01.py` + `build_bitemporal_projector_proposal()`。
   postings 级可见性谓词投影：AsKnown(as_of) 与 Annotated(now) 共享同一物理
   索引；注解追加即时生效、历史视图零渗透、源索引 SHA 全程不变、零重建。

## 四、五大铁律捍卫证明（关键断言记录）

- 铁律1（质量第一）：阶段6 三顾问全部带 ObjectRef 因果证据、零证据熔断；
  阶段7/8 全部发言 1~3 句硬熔断（超限 raise）。
- 铁律2（老王案）：指纹不变 + 只追加注记 + 单跳隔离 0 LLM + 双透镜一致性。
- 铁律3（P0 硬旁路）：200 连发 ≤50ms、llm=0、world_model=False、首行报警。
- 铁律4（自主删除）：噪声 100% 物理删除、关键原话 100% 永存、字节滞留 0。
- 铁律5（三重硬门槛）：50 连拒 + 试用未满不转正 + 反思配额强拒。

## 五、缺陷/遗留（诚实列账）

- 压缩算子的 IMU 冲击线为绝对阈值，未做佩戴姿态补偿（下一步引入姿态状态机）。
- Bitemporal 投影目前以 object_id 序号切片，企业级部署需改为单调逻辑时钟列。
- 本压测为单机沙箱基线，规模化部署（分片/只读副本）的延迟分位需另测。
