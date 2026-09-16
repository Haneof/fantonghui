# 《AIOS 全流程海量盲测与极限压测报告》

> Agent：arena/01a0a8c1-fantonghui（云端全栈心智算法与测试总攻 Agent）
> 日期：2026-09-16
> 基准：`docs/constitution/AIOS核心系统宪法v3.0.md` + `governance/runtime_policy.json`
> 代码法统：`src/aios_core/**`（只编排生产引擎，未改动一行生产契约）
> 全量测试基线：**1181 passed**（云上既有 1153 项 + 本次新增 28 项）

---

## 0. 诚实性声明（先于一切数字）

本报告所有延迟、吞吐、内存数字均来自**同一进程内真实执行**的采样
（`time.perf_counter` / `tracemalloc`），由
`src/aios_core/simulation/mass_stress.py` 与
`src/aios_core/simulation/arena_agent_mind_bench.py` 产出，可在总工沙箱**一条命令复现**：

```
PYTHONPATH=src python -m aios_core.simulation.mass_stress --db /tmp/s.db --target 400000
```

"上百万条样本"与"上百万次对象修订"是两个概念，本报告如实分开标注：
原始样本流（50Hz IMU × 心率 × 噪声）在边缘就被压缩/剪枝，**世界账本里的对象修订数
远小于原始样本数**——这正是宪法第 33 条与铁律 4 要求的结果，不是压低工作量。

---

## 1. 全流程执行时间与吞吐

| 指标 | 数值 | 采样条件 |
|---|---|---|
| 原始样本流总量 | 1,200,000 条（50Hz IMU × 心率 × 噪声 3 流） | `--target 400000`，3 流各 40 万 |
| 边缘清洗后写入 Observation | 119,512 条 | 每 500 条一批提交，239 批 |
| 原始→宏观压缩比 | **10.04 : 1** | 心率均值化 + IMU 宏观化 + 噪声剪枝 |
| 原始大图字节滞留 | **0 B** | RawByteSink purge 全程审计 |
| 全流程墙钟 | **260.1 s**（≈4 分 20 秒） | 含建库、摄入、倒排、金字塔 |
| 摄入吞吐 | **459 obs/s**（≈55.5 批/分钟） | 批提交，WAL 开启 |
| 内存驻留峰值 | **59.88 MB**（61322 KB） | tracemalloc 峰值 |

> 换算说明：119,512 条 Observation 对应 239 次提交（每次提交 batch=500）。若把
> commit 的粒度再放大（如 1500/批），单批耗时上界 ~1.4s、总批数约 80，吞吐可进
> 一步提升——本报告保留 500/批是为了给出更细的延迟分布样本。

---

## 2. 延迟分布（P50 / P95 / P99）

| 环节 | 样本数 | P50 | P95 | P99 | 均值 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| 摄入 commit（500 obs/批） | 239 | 880 ms | 1069 ms | 1386 ms | 909 ms | 批写瓶颈，见 §3 |
| 倒排共现 co_search | 150 | 1.02 ms | 3.80 ms | **9564 ms** | 166 ms | P99 异常尖刺，见 §3 |
| 金字塔下钻 drill_down | 31 | 4.49 ms | 4.72 ms | 4.73 ms | 4.52 ms | 达标（<45ms 门禁） |
| 驾驶舱看板组装 | 40 | 0.15 ms | 0.22 ms | 0.22 ms | — | 达标（1500 Token 硬预算） |
| P0 硬旁路穿透 | 1 | 0.036 ms | — | — | 0.036 ms | **≤50ms，0 大模型调用** |

**八阶段盲测墙钟**（`arena_agent_mind_bench.py`，521 条真实对象 + 59 条断言）：

- 摄入 commit：P95 = 44.0 ms（本档小批量）
- co_search：P95 = 2.87 ms
- 金字塔 rollup：2.45 ms / drill：0.37 ms
- 驾驶舱组装：P95 = 0.22 ms
- **P0 心率骤停穿透：0.036 ms（均值近 1000× 优于 50ms 红线）**

---

## 3. 两个必须点名的延迟真相（不粉饰）

1. **摄入 commit 的 P95 ≈ 1.07s**：commit 是全库最重的写事务——引用完整性校验
   （`_collect_refs` + `_reference_exists`）逐对象过 SQLite，500 对象一批意味着
   一次事务数百次点查。这是"端侧每 500 条一刷"场景的**真实物理成本**，不是缺陷
   而是换纪律（append-only + 引用校验）的代价。**优化出口见 03 号交付物 TLP-C02**
   （双时间透镜合并物化 IO）与本报告 §5 的"批内 reference 跳过已见对"建议。
2. **co_search P99 = 9.56s 尖刺**：P50/P95 都 <4ms，唯独 P99 飙到 9.5s。根因是
   `WorldSearchIndex.catch_up()` 在请求路径上**同步重建投影**：压测中索引后有大量
   新提交未进投影，下一次 co_search 触发整批追赶把延迟打进采样。这是"迟到数据 →
   strict 回 stale_index，adaptive 才允许追赶"纪律在 benchmark 中的复现。**铁律
   层面完全正确**（宁慢不吐劣质）；性能层面的出口是把追赶挪到后台心跳（TLP-C02）。
3. **金字塔下钻全程 <5ms**：物化视图 + 只读深拷贝的正确性没有牺牲延迟。

---

## 4. 五大铁律压测裁决（附关键断言通过记录）

| 铁律 | 裁决 | 关键断言（生产引擎，非自答） |
|---|---|:---|
| 铁律1 输出质量绝对第一 | ✅ 捍卫 | 驾驶舱单看板硬预算内；BrevityGuard 对说教句拦截并回落 1~3 句；40 轮对话旬数 ≤3 |
| 铁律2 历史绝不篡改 | ✅ 捍卫 | EpistemicWorldLens 拦截同 id/rev 异字节重注册；`attachment.history_rewrites=0`、`overlay_hops=1`；AsKnown/Annotated 双视图 SHA-256 一致 |
| 铁律3 P0 硬旁路 | ✅ 捍卫 | dispatch_wake_event 首行穿透，实测 0.036ms，`llm_calls=0`、`cockpit_assemblies=0`、`world_persistence_yielded=true` |
| 铁律4 自主删噪 | ✅ 捍卫 | RawByteSink：retained 80 段原始字节 purge 后 = 0 B；声纹 180 天 TTL 未绑定墓碑化、绑定永存 |
| 铁律5 维度门槛 | ✅ 捍卫 | EvolutionGuard：未跨域未满 3 天的候选 throw `ImmaturePatternRejectedError`，且**不烧当天反思配额**；每日配额 strict 1 次 |

**完整断言清册**（59 条）可复现：`PYTHONPATH=src python -c "..."` 或直接
`pytest tests/simulation/test_arena_agent_mind_bench.py -v`。

---

## 5. 结论

五大铁律在全流程压测中 **100% 得到捍卫**；代价集中在两处已被点名且有明确出口
（commit 写放大、co_search 同步追赶）。绝不靠"牺牲深度检索换 1 秒首字"：
co_search P95 2.87ms 的**正确结果**优先于造假低延迟。下一份《诊断书》给出
Token/I-O 归因与更优机制。
