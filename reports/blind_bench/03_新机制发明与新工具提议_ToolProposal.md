# 新机制发明与新工具提议（ToolProposal）

> 契约：`src/aios_core/contracts/models.py::ToolProposal`（能力缺口 / 适用场景 / 当前局限 /
> 提议接口 / 期望收益 / 验收计划）
> 实现：`src/aios_core/tools/{adaptive_temporal_compressor,dual_lens_index_projector,conditional_event_evaluator}.py`
> 提案与探针：`src/aios_core/tools/proposed_operators.py`
> 评审通道：`ToolProposalPipeline`（draft → submitted → approved → executed）
> 一键复核：`PYTHONPATH=src python -c "from aios_core.tools.proposed_operators import validate_all_proposals as v; [print(r) for r in v()]"`

本提案不是 PPT：**三个算子全部已经写进仓库、可被当场跑出量化收益**。
每个提案的 `validation_plan` 都是一个**可执行函数**，探针跑不出数字就不算通过。

---

## 1. TLP-ATC-001 · 自适应时序压缩算子（AdaptiveTemporalCompressor）

**能力缺口**
端侧高频流（IMU 50 Hz / 心率 1 Hz）此前只能用固定时间窗合并：平稳期照样按窗产出，
突变期又被平均抹平。既没有"误差有界"的保证，也没有"冲击保真"的通道。

**适用场景**
IMU 宏观运动状态提炼与跌倒冲击保真；心率长平稳期时段均值压缩；任何需要
"压缩后仍能给出误差上界"的端侧时序通道。

**当前局限（没有它之前）**
`PulseMergeWindow` 是固定 5 s 窗，压缩比与信号平稳度无关；固定窗平均会削平冲击波形，
必须另开通道检测跌倒；没有重建误差上界，压缩损失不可量化、不可审计。

**提议接口**

```python
AdaptiveTemporalCompressor(
    epsilon=2.0,             # 窗口内任一采样相对重建值的硬误差界
    curvature_budget=4.0,    # 允许的曲率累计预算（控制窗口增长）
    impact_magnitude=4.0,    # 冲击判据（合成加速度 g），命中即单点成段
    min_window=8,            # 最小窗口（保证噪声被吸收）
    max_window=4096,         # 2 小时级平稳平台的最大窗口
).compress(samples: Iterable[tuple[int, float]]) -> CompressionResult
# 复核：verify_error_bound(samples, result) -> 实测最大绝对误差
```

**期望收益**
百万级原始采样压到千级派生段（≥ 95% 缩减），冲击波形 100% 原值保留，
窗口内偏差硬约束在 ε 之内 —— 存储与 Token 双降，跌倒识别不降级。

**可执行验收（probe_atc，实测结果）**

| 指标 | 实测 | 门槛 |
| --- | --- | --- |
| 缩减率 `reduction_ratio` | **0.99978** | > 0.95 |
| 冲击段数 | **5 / 5** 全保真 | == 5 |
| 最大重建误差 | **0.2271** | ≤ ε = 0.5 |

**百万级旁证**（`operator_microbench(imu_samples=200_000)`）：200,000 条 → 16 段，
缩减比 0.99992，最大重建误差 0.0，吞吐 **2,159,402 条/秒**。
在阶段一真实管线中，它把 1,050,000 条 IMU 采样压成 73 条宏观状态 + 20 条冲击观察。

---

## 2. TLP-DLV-002 · 双透镜虚拟索引投影器（DualLensVirtualIndexProjector）

**能力缺口**
"老王案"要求：历史事实字节级不可改，今天的司法认知只能作为外部注解。
若读面每次查询都全量拉取事实再叠加注解，在"3 年 18,000 条事实 + 今日 1 条注解"的场景里，
**每次查询都在重建全量索引** —— 铁律 2 说得清、实现上却做不到便宜。

**适用场景**
AS_KNOWN（当时已知）与 ANNOTATED（今日审视）双透镜检索；历史回溯标注的读面投影；
任何"底层只增不改、注解频繁追加"的检索场景。

**当前局限（没有它之前）**
注解一旦挂载就得重建倒排；两条透镜要么维护两份索引（存储翻倍），要么每次查询现算（延迟爆炸）；
基底哈希无法证明"注解没有改历史"。

**提议接口**

```python
projector = DualLensVirtualIndexProjector()
projector.index_fact(object_id, text, learned_us=...)   # 幂等且内容锁定
frozen = projector.freeze_base()                         # 基底 SHA-256（此后不可变）
projector.attach_annotation(annotation_id, target_object_id, statement, slot, annotated_us)
projector.query(keywords, lens=AS_KNOWN | ANNOTATED, as_of_us=..., limit=...)
projector.assert_lens_consistency(keywords)              # 两条透镜事实集合一致
projector.metrics()                                      # base/overlay postings、节省比
```

**期望收益**
注解挂载成本从 O(基底 posting 总数) 降到 O(注解词元数)；两条透镜返回同一组事实；
基底 SHA-256 前后逐字节不变（可审计）。

**可执行验收（probe_dlv，实测结果）**

| 指标 | 实测 | 门槛 |
| --- | --- | --- |
| 节省比 `saved_ratio` | **0.998874** | ≥ 0.95 |
| 基底 posting / overlay 写入 | 43,501 / **49** | overlay ≪ base |
| 双透镜事实集合一致 | True | True |
| 基底哈希不变 | True | True |

**老王案旁证**（阶段五）：基底哈希 `8f924db3b7a23ff4`，1,376 条基础 posting +
75 条 overlay，节省比 **0.999651**；两条透镜各返回 500 条且事实集合完全一致，
注解在 ANNOTATED 透镜可见、AS_KNOWN 透镜不可见。

---

## 3. TLP-LCE-003 · 轻量条件事件求值器（LightweightConditionalEventEvaluator）

**能力缺口**
机械快轨此前对**全部**待办任务做线性扫描：10 万条休眠任务时，每个信号都要看 10 万遍。
Token 虽然为 0，但端侧 CPU 与电量在静默期被无差别烧掉 —— 对 23 cm 手环是不可接受的。

**适用场景**
条件任务的"宽相位建索引 + 窄相位只碰命中桶"；端侧长驻条件求值；
任何"注册多、触发少"的机械条件集合。

**当前局限（没有它之前）**
线性扫描与任务数成正比；静默期照样全量跑；语义条件（需要大模型）与机械条件混在同一条轨道上。

**提议接口**

```python
evaluator = LightweightConditionalEventEvaluator()
evaluator.register(task_id, title, conditions=(Condition(kind=GEO_FENCE | VITAL_THRESHOLD | ABSOLUTE_TIME | SEMANTIC_SCENE, ...),))
evaluator.tick(EvaluatorSignals(now=..., present_places=(...), vitals={...})) -> EvaluationReport
#   报告字段：tasks_evaluated / narrow_phase_hits / fired_task_ids /
#             blocked_by_semantics / time_heap_popped / elapsed_ms / llm_calls
evaluator.index_sizes()          # time_heap / geo_places / vital_metrics 三桶规模
evaluator.earliest_pending_us()  # 堆顶：未到期连一次比较都不做
```

**期望收益**
静默 tick 求值次数为 0（堆顶未到期即返回）；有信号 tick 只碰命中的地理/指标桶，
实际求值次数 < 注册任务数的 5%；语义条件永不上机械轨（挂起等待大模型确认，且不计费）。

**可执行验收（probe_lce，实测结果）**

| 指标 | 实测 | 门槛 |
| --- | --- | --- |
| 窄相位触碰比例 `narrow_phase_ratio` | **0.0084** | < 0.05 |
| 静默 tick 求值次数 | **0** | == 0 |
| 静默 tick 耗时 | **0.0054 ms** | < 1 ms |
| 有信号 tick 求值次数 | 42 / 5,000 | < 5% |

**阶段八旁证**：200 条休眠条件任务在看板里 **0 Token**（朴素提示需 1,000 Token），
机械 tick 求值 200 条、**0 次大模型调用**；独立求值器静默 tick 求值 0 条、
带信号 tick 只求值 40 条（20% 桶命中，注册总数 200）。

---

## 4. 三个新机制（不只是三个类）

| 机制 | 一句话 | 落地位置 | 在盲测里的证据 |
| --- | --- | --- | --- |
| **误差有界窗口增长** | 窗口能长到多长，由"窗内偏差 ≤ ε + 曲率预算"决定，而不是由固定秒数决定 | `adaptive_temporal_compressor` | 阶段一压缩比 0.996854；误差界占用率 100%（D1，见诊断书） |
| **基底冻结 + 增量 overlay** | 历史基底只冻结、不重写；今天的新认知只写增量 posting，两条透镜共享同一批事实 | `dual_lens_index_projector` | 阶段五单跳隔离 0 次大模型调用（对比 210 次）、基底哈希不变、节省比 0.999651 |
| **宽相位建索引 / 窄相位只碰桶** | 注册时把条件拆进时间堆与地理/指标桶；tick 只触碰"有信号"的桶，静默期零比较 | `conditional_event_evaluator` | 阶段八休眠 200 条任务 0 Token、机械 tick 0 次大模型调用 |

三个机制共享同一套设计哲学，也正是这次盲测反复验证的那条线：
**凡是"每次都要看全部"的动作，都应该被改成"只在变化的地方看"；
凡是"不可逆"的抽象，都必须带可证明的误差界。**

---

## 5. 提案如何进入正式通道（工程落地）

```python
from aios_core.tools.proposal_pipeline import ToolProposalPipeline
from aios_core.tools.proposed_operators import register_tool_proposals, validate_all_proposals

pipeline = ToolProposalPipeline()
submitted = register_tool_proposals(pipeline)      # 三条提案 → SUBMITTED
assert all(item.status.value == "submitted" for item in submitted)
pipeline.review_proposal("TLP-ATC-001", "approve") # → APPROVED
pipeline.execute_proposal("TLP-ATC-001")           # → EXECUTED

for result in validate_all_proposals():            # 每个提案的验收探针
    assert result.passed is True
```

探针输出（本轮实测）：

```
TLP-ATC-001 True reduction_ratio     0.99978  (门槛 0.95)  in=50000 out=11 impacts=5 max_err=0.2271 <= 0.5
TLP-DLV-002 True saved_ratio         0.998874 (门槛 0.95)  base_postings=43501 overlay_written=49 lens_consistent=True
TLP-LCE-003 True narrow_phase_ratio  0.0084   (门槛 0.05)  registered=5000 idle_evaluated=0 idle_ms=0.0054
```

**验收纪律**：提案的收益方向必须与指标语义一致 —— 压缩/节省类指标"越大越好"，
窄相位触碰比例"越小越好"，`tests/tools/test_proposed_operators.py` 会逐条检查方向，
不允许只凭一个 `passed=True` 字段过审。

---

## 6. 下一步提案（已识别、尚未实现，留给下一轮）

| 候选编号 | 命题 | 依据（来自本轮诊断） |
| --- | --- | --- |
| TLP-RWS-004 | **世界视图增量订阅**：把"每阶段重新整表拉 `object_revisions`"改成按 `world_revision` 增量订阅 | §3 读放大：3,700 条语句扫描 114,163 行 |
| TLP-LZY-005 | **看板透镜懒装载**：按本轮需要的透镜装载，其余只保留计数钩子 | 缺陷 D8 / Token 热点 S8 4,720 |
| TLP-EGC-006 | **误差余量控制器**：按信号平稳度动态收紧 ε，把误差界占用率压到 70% 以下 | 缺陷 D1 误差界占用率 100% |

这三条都还没写代码，因此**不作为本轮交付的 ToolProposal**，等实现 + 探针齐备后再走同一通道。
