# AIOS 全流程海量盲测与极限压测报告

- 主体：`user_e2e_1`（T_now = 2026-09-15T12:00:00+00:00）
- 原始流规模：**2,108,670** 条（IMU 50Hz 为主力，全部边缘提纯后落世界）
- 世界对象：**19,511** 个，世界修订号 **53**（全量 append-only）
- 总耗时：**117.83s**；峰值内存：**264.7 MB**
- LLM 调用：**0**（全程纯代码常数级路径，铁律 3 大模型严格 0）

## 一、8 阶段执行明细

| 阶段 | 名称 | 通过 | 耗时(ms) | 关键指标 |
|---|---|---|---|---|
| 1 | 百万级摄入清洗 + 边缘提纯 | ✅ | 62888.7 | raw_records=2108670; raw_imu_samples=2000000; world_objects=19511; gen_ms=22620.2 |
| 2 | 金字塔日→年结晶 + 无损下钻 | ✅ | 1136.1 | summaries=5; vault_events=909; drill_year_to_day_ms=4.38; evidence_break_rate=0.0 |
| 3 | 多关键词共现 + EventAnchor 生命周期 | ✅ | 10371.0 | recall_union=6; strict4_hits=0; recall_ms=10330.0; kw_counts={'合伙': 2, '借贷': 2, '撕逼': 1, '银行流水': 3} |
| 4 | 认知层导数 + 章节基线断裂 + 三重门槛 | ✅ | 1148.5 | curve_points=101; trend=inflection; anomaly_points=13; baseline_mean=39.3 |
| 5 | 老王案双透镜 + 字节不可变 | ✅ | 21.2 | facts_registered=5; annotations=1; as_known_facts=3; annotated_facts=3 |
| 6 | ActionableAdvice + Goal/Task 解耦 + 否认撤销 | ✅ | 29.5 | evidence_pointers=4; advice_sentences=1; retraction_latency_s=0; goal_revisions=2 |
| 7 | AIActionLog + 沟通风格博弈演化 | ✅ | 20.1 | actions=2; outcomes=1; experiences=3; effective_style=老友 |
| 8 | CockpitManifest + P0 + DORMANT + 10 轮会话 | ✅ | 42215.9 | p0_hardware_ms=0.003; p0_e2e_ms=0.055; p0_llm_calls=0; rounds=10 |

**提交批次延迟**：P50=768.56ms / P95=909.56ms / P99=962.85ms
**摄入吞吐**：36,117 原始条/秒（含生成 + 提纯 + 落库）

## 二、五大铁律 100% 捍卫断言账目

| 铁律 | 断言 | 通过 |
|---|---|---|
| 铁律4 | 原始图片字节物理删除：1,024,000 字节经 RawByteSink.purge，留存 0 字节 | ✅ |
| 铁律4 | 核心证据 100% 永存：6,584 条核心证据（关键原话/转账凭证/录音转写）逐条读回命中 | ✅ |
| 铁律4 | 原始流禁直写 DB：2,108,670 条原始 → 19,511 个世界对象（IMU 2,000,000 样本仅产出 134 条宏观状态 + 1 条冲击波形） | ✅ |
| 铁律2 | 世界单调递增全量 append-only：40 个世界修订覆盖 19,511 个对象修订，无 UPDATE/DELETE | ✅ |
| 铁律2 | 下钻证据链断裂率 0.0%（年 sum_year_dim_e2e_health_resting_hr_1789473600 → 12 个月子层 → 365 条日级原始事件，并集与父层严格相等） | ✅ |
| 铁律2 | 底层原始事件永存：抽样 200 条 vault 回读逐字节一致；重复灌入幂等 vault_size 909 不变 | ✅ |
| 铁律2 | 总结=新观察层而非压缩：5 个 Summary 追加进世界，金字塔 vault 仍保留 909 条底层事件 | ✅ |
| 铁律2 | EventAnchor 时间快照：CANDIDATE/ACTIVE/REVISED 三个修订全部可回放，REVISED 携带 supersedes+revision_reason | ✅ |
| 铁律2 | 下游 STALE 只标记派生视图：月度总结 rev1=current → rev2=stale，底层原始事件零改动 | ✅ |
| 铁律5 | 三重硬门槛：门限一（跨域 3 天）放行 1 个合规候选；违规申请 2/2 全部拒绝（immature_pattern_rejected, quota_exceeded_block） | ✅ |
| 铁律5 | 30 天试用 + Prediction 对撞：准确率 80% vs 门限 70%，解释力连续 31 天 → promoted | ✅ |
| 铁律2 | LifeChapter 基线永久断裂：封章+新章双章 append-only 共存，基线引用指向不同时代事实 | ✅ |
| 铁律2 | 历史字节不可变：篡改注入（300 万→500 万）被 HistoryImmutabilityViolation 拦截；SHA-256 复核 5 条全部通过 | ✅ |
| 铁律2 | 双透镜一致：AsKnown(cutoff 2025-06-01) 与 Annotated(cutoff T_now) 的 3 条历史事实指纹完全相同，T_now 认知零泄露（AsKnown 注解数 0） | ✅ |
| 铁律2 | 单跳级联契约锁死：history_rewrites=0, max_recursion_depth=0, derived_recomputations=0，篡改拦截 1 次 | ✅ |
| 铁律1 | 建议硬核且极简：1 句（≤3），BrevityGuard 未拦截（无说教/谄媚/清单体），证据指针 4/4 可读回 | ✅ |
| 铁律2 | Goal/Task 解耦 + 否认即撤销：目标 rev1=active → rev2=abandoned，任务 rev2=cancelled，反思已追加（双修订共存，历史保留） | ✅ |
| 铁律1 | 风格博弈演化：有效风格=老友（老友 2/2 ACCEPTED），雷区规避=['损友']（损友 RESISTED 0/1 入规避清单） | ✅ |
| 铁律1 | 反谄媚/反教师爷：谄媚+说教候选被拦截 1 类违例（PREACH_PATTERN:保持积极心态），输出压回 1 句老友线 | ✅ |
| 铁律3 | AIActionLog 全程可审计：Action×2 + Outcome×1 + CommunicationExperience×3 均为一等世界对象，LLM 调用累计 0 | ✅ |
| 铁律3 | P0 硬旁路：首行硬件穿透（receipt 0.003ms，端到端 0.055ms ≤ 50ms），LLM 0 次、看板 0 次、持久化让路，审计回执 1 条非阻塞入队 | ✅ |
| 铁律1 | 终极 10 轮日常会话：每轮助手输出 [2, 2, 2, 2, 2, 2, 2, 2, 2, 2] 句（全部 1~3 句），看板 token 260~383（≤1500 预算） | ✅ |
| 铁律3 | DORMANT 零 Token：1 个休眠任务被机械冻结，Token 贡献 0（若泄漏需 14 token），泄漏断言通过，DORMANT 直执违约拦截=True | ✅ |
| 铁律1 | 心智四步序结构在场：{'镜': True, '羁绊': True, '现场': True, '姿态': True}；黑盒零 UI：Prompt 不含置信度/图谱/A-B 问卷=True；滑窗 6 轮 + 归档 16 轮无损 | ✅ |
| 新机制门槛 | Tool A 压缩比 3.0:1、max|原始-重建|=0.1950g、瞬态保峰=True；Tool B 与基线对撞：4 词 identical=True、成对 identical=True（基线 868.8ms vs 加速 1.08ms，加速 802.5x），两工具均经 ToolProposalPipeline SUBMITTED→APPROVED→EXECUTED 并落世界 | ✅ |

铁律断言总数：**25**，全部通过：**是**

## 三、全生命周期心智瓶颈与缺陷诊断（交付物 2）

- **最耗 Token 环节**：阶段 8（CockpitManifest + P0 + DORMANT + 10 轮会话）（3,520 token 当量）
- **最耗 I/O 查询环节**：阶段 1（百万级摄入清洗 + 边缘提纯）（6,584 次存储读）
- **最易失真抽象**：阶段 1 图片层（4,000 帧 → Caption 文字层）（1,024,000 原始字节 → 68,206 字符 Caption（压缩比 15:1，语义保真由核心证据 Caption 校验））
- 结论：Token 压力集中在 cockpit 看板（阶段 8）——已由 1500 token 物理预算 + 6 轮滑窗封顶；I/O 压力集中在核心证据逐条读回（阶段 1）——建议以 SHA-256 批量清单替代逐条读回（见 Tool A）；最大失真点在图片模态——Caption 只存文字，语义损失由核心证据图强制全量 Caption 兜底。

## 四、新机制发明与新工具提议（交付物 3）

基于本轮压测暴露的瓶颈，按 `ToolProposal` 契约提交两个纯代码新工具（已实现 + 测试 + 走 ToolProposalPipeline 生命周期 + 落世界为 EXECUTED 对象）：

1. **自适应时序压缩算子** `tools/adaptive_timeseries_compressor.py`（Tool A）——
   50Hz 原始时序内容自适应压缩：冲击瞬态/动态小叶全保留（零重建误差），
   平稳小叶摆动自适应锚点 + 验证-细化（噪声地板 5σ 封顶），每段 SHA-256 审计链。
2. **共现召回加速器** `tools/cooccurrence_recall_accelerator.py`（Tool B）——
   多关键词共现召回的倒排预过滤 + 子串确认，与 `search_mind` 基线做 object_id 集合级一致性对撞。

**本轮官方压测实测（阶段 8）**：

| 指标 | 实测值 |
|---|---|
| Tool A 压缩比 | 3.0:1 |
| Tool A 最大重建误差 | 0.195 g |
| Tool A 压缩耗时 / 段结构 | 16194.1 ms / steady=4670/transient=1999 |
| Tool B 4 词全共现对撞 identical | True |
| Tool B 成对共现对撞 identical（非退化） | True |
| Tool B 基线 vs 加速 | 868.8 ms vs 1.08 ms（802.5x） |
| Tool B 成对命中 | ['obs_e2e_partner_fight'] |

## 五、结论

✅ 8 阶段全部通过，五大铁律 100% 捍卫，可进入 PR 合入。
