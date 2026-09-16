# 交付物 ③ · 新机制发明与新工具提议（ToolProposal 提案书）

> 任务要求：基于 `aios_core.contracts.models.ToolProposal` 契约，交付 **≥1–2 件**新的纯代码工具/算子。
> 本次实际交付 **8 件**，且**每一件都已在盲测中被真实调用**（不是纸面提案）：
> 契约对象由 `aios_core/bench/tool_catalog.py` 构造并走真实 `ToolProposalPipeline`
> （`submit_proposal` → `review_proposal` → `execute_proposal`），
> 端点断言见 `tests/bench/test_tool_catalog.py`（7 个用例，全部通过）。

老大约法三章第一条：并行 Agent 的意义不是验智商，而是"总结更有效的机制/方法，或发明新工具"。
因此本提案书**不写未来时**：每一件工具下面给出的"实测证据"都来自本次盲测的真实数字。

---

## 契约字段总览（`ToolProposal`）

| 字段 | 说明 | 本次填写口径 |
| --- | --- | --- |
| `capability_gap` | 能力缺口 | 指向宪法条文或盲测中被打脸的具体场景 |
| `use_cases` | 用例 | 至少 2 条，均可由已实现接口完成 |
| `current_limitations` | 现状局限 | 旧实现/无实现的具体短板 |
| `proposed_interface` | 接口定义 | 与真实代码**逐字一致**（类名、方法名、参数名） |
| `expected_benefit` | 预期收益 | 带数字 |
| `validation_plan` | 验证计划 | 指向具体 pytest 文件或用例名 |
| `status` | 状态 | `draft` → `submitted`（↺ 审批由总工裁决） |

提交后的 8 件提案 ID：`tool_proposal_adaptive_temporal_compressor`、
`tool_proposal_multiscale_crystal_index`、`tool_proposal_dual_lens_projection_index`、
`tool_proposal_lightweight_condition_evaluator`、`tool_proposal_resonance_synthesizer`、
`tool_proposal_cooccurrence_recall_bus`、`tool_proposal_persona_guard`、`tool_proposal_mind_sequence_guard`。

---

## 工具 1 · `AdaptiveTemporalCompressor`（自适应时间压缩器）

- **能力缺口（宪法视角）**：50Hz IMU 原始波形与逐拍心率**禁止直写数据库**（铁律 4 与 S1 硬约束），
  但匀速抽稀会把跌倒撞击峰抹平 —— 需要一种**误差有界**的压缩器，既省存储又不吃掉救命波形。
- **用例**：① 200k@50Hz 波形 → 宏观运动状态 + 异常冲击波形；② 稳定期逐拍心率 → 区间均值，
  突变单独成 `Observation`；③ 为 P0 硬旁路保留 3.4g 级撞击样本。
- **现状局限**：原实现按固定窗口抽稀，静止段与撞击段同一口径，误差不可控、不可审计。
- **接口**：
  `AdaptiveTemporalCompressor(tolerance=0.12, max_segment_span_s=30.0, impact_threshold_g=2.0,
  fall_threshold_g=3.2, impact_delta_g=1.0, max_impact_samples=32, min_state_span_s=1.0)`
  → `compress(timeline) -> CompressionResult`、`verify_reconstruction(timeline) -> bool`；
  结果字段 `max_absorption_error / error_bound_holds / macro_states / impacts`。
  **冲击判据是双条件**：`peak_g ≥ impact_threshold_g` **且** `peak_g − 上一段基线 ≥ impact_delta_g`；
  暴露唯一配额常量 `MAX_IMPACT_WAVEFORM_SAMPLES = 32`，供存储审计复用（杜绝口径漂移）。
- **实测证据（本轮修复后）**：
  ① 单机验证：200k@50Hz → 5,122 段（压缩比 **39×**），`max_absorption_error ≤ 0.12`、`error_bound_holds = True`；
  ② 盲测 GATE：`motion_compression_ratio = **815.6×**`、`hr_compression_ratio = 8.42×`、
  3 条 3.45 g 真实跌倒判为 `FALL_SUSPECT` 并保留波形、波形扫描违例 **0**；
  ③ 盲测 FULL（4,579,518 条原始样本）：`motion_compression_ratio = **1,790.47×**`、
  `hr_compression_ratio = 23.39×`、冲击波形 10 条（3 条 FALL + 7 条跑步尖峰 IMPACT）、波形扫描违例 **0**；
  ④ **缺陷修复对照**：修复前同口径 `motion_compression_ratio = 813×`（分母被 427,838 条假冲击污染），
  修复后 1,790.47× —— 见诊断书 §1.5 与 `evidence/full_snapshot_prefix_461k.json`。
- **验证计划**：`tests/bench/test_iron_laws_gate.py::test_stage1_purifies_noise_but_keeps_evidence`
  + 盲测 S1 `motion_max_error` 断言。
- **机制级教训（本轮新增，已写进代码注释）**：物理量判据必须**成对**给出（绝对阈值 + 相对基线变化）。
  只看绝对幅度时，任何"基线本身很高"的常态活动（跑步 1.9 g 基线）都会被判成异常（跌倒），
  实测代价是 **427,838 条假冲击 / 92.8% 存储与 Token / S3 OOM**。这条规则对心率、声压、光照等所有端侧阈值同样成立。
- **评审建议**：**通过**。该工具是"端侧提纯"能被审计的前提；
  建议后续把 `tolerance` / `impact_threshold_g` / `impact_delta_g` 三个参数一并纳入
  `runtime_policy.json` 参数层（阈值即法律，必须可审计、可回滚）。

---

## 工具 2 · `MultiScaleCrystalIndex`（七档多尺度晶格索引）

- **能力缺口**：时间金字塔只有日/周/月/季/年汇总，缺少**可下钻到单条原始引文**的晶格，
  "摘要是新观察层而不是压缩"这一条无法被证明。
- **用例**：① `YEAR→QUARTER→MONTH→DAY→OBSERVATION` 逐级下钻；② 与金字塔做**并集守恒**对照；③ 跨尺度一致性核账。
- **现状局限**：旧金字塔只存汇总，下钻要回表全扫；同 id 改写无法检测。
- **接口**：`crystallize(scale, dimension_id, events, headline) -> CrystalLayer`、
  `drill(crystal_id, target_scale)`、`assert_union_conserved(crystal_id, target_scale)`、
  `vault_fingerprint()`、`scale_counts()`；错误类 `CrystalError`（同 id 异字节 / 跨窗口汇总一律拒绝）。
- **实测证据**：盲测 S2 下钻链 `YEAR→MONTH→WEEK→DAY→OBSERVATION`（30 条链接，**断链率 0.0%**），
  晶格与金字塔**证据集合逐一相等**（`crystal_vs_pyramid_equal = True`），
  两条独立路径命中**同一条原始引文**（`crystal_drill_text == drill_chain_text`）；
  三档守恒检查全部通过（QUARTER / HALF_YEAR / MONTH）。
- **验证计划**：`tests/bench/test_iron_laws_gate.py::test_stage2_drill_down_is_lossless`。
- **评审建议**：**通过**。已知边界：`scale_counts()` 反映"被真实物化过的档位"，
  GATE 档位下 DAY/WEEK 由 `drill` 现算、不常驻（计数为 0），**不要**把该计数误读成"覆盖不全"。

---

## 工具 3 · `DualLensProjectionIndex`（双镜投影索引）

- **能力缺口**：老王案要求"历史只读、今天只打标签"，但缺一个能同时给出
  **当时所知**与**今天注解**两副眼镜、并证明 base 事实零改写的工具。
- **用例**：① AS_KNOWN vs ANNOTATED 双透视差异清单；② 注解只追加、base 指纹恒等；③ mutation 计量。
- **现状局限**：旧实现把新注解回写到历史对象上，直接违反铁律 2。
- **接口**：`register_fact(fact_id, …)` / `register_annotation(annotation_id, target_id, …)`、
  `project(target_id) -> ProjectedFact`、`lens_delta() -> LensDelta`
  （`base_fingerprint_equal / annotated_only_ids / mutation_count / history_intact`）。
- **实测证据**：盲测 S5 `base_fingerprint_equal = True`、`data_consistency_ratio = 1.0`、
  历史事实零改写（FULL 33,238 条 / GATE 22,357 条）、`immutability_violations = 0`、`Deleted rows = 0`。
- **验证计划**：`tests/bench/test_single_hop_isolation.py`（历史完整性 4 例）+ 门禁 S5 三例。
- **评审建议**：**通过**。该工具是"注解层"能对外解释的技术底座。

---

## 工具 4 · `LightweightConditionEvaluator`（轻量条件求值器）

- **能力缺口**：条件任务双轨调度必须"休眠期**零 Token** 空转"，
  但旧实现仍会把休眠任务塞进看板 Prompt。
- **用例**：① 200 条条件任务休眠 24 小时，Token 恰好 0；② 四类机械判定
  （`TIME_ARRIVAL`/`BIOMETRIC_THRESHOLD`/`KEYWORD_MATCH`/`GEO_ENTER`）；③ 销号即物理摘除索引。
- **现状局限**：语义条件与机械条件混在同一求值路径，"零 Token"无法自证；缺 `skip_ratio` 审计。
- **接口**：`register(task_id, conditions)`、`evaluate_signal(signal) -> TaskTriggerReport`、
  `evaluate_time(moment)`、`archive(task_id) -> bool`；
  `TaskTriggerReport(tokens_spent=0, llm_calls=0, skip_ratio)`（构造上恒零，非运行期置零）。
- **实测证据**：单指标信号下 **199/200 条被索引直接跳过**（`skip_ratio = 0.995`），
  `tokens_spent = 0`、`llm_calls = 0`；调度引擎侧 `render_llm_prompt_context` 对休眠任务贡献
  **0 token**（`dormant_board_prompt_tokens = 0`）。
- **验证计划**：`tests/bench/test_iron_laws_gate.py::test_stage8_dormant_tasks_burn_zero_tokens`。
- **评审建议**：**通过**。建议把 `skip_ratio` 纳入月度 Token 封套审计口径（它是"省下来多少"的直接证据）。

---

## 工具 5 · `CrossDomainResonanceSynthesizer`（跨域共振合成器）

- **能力缺口**：GPS 轨迹、心率尖峰、原始原话、资金流水、环境噪声各自沉睡在不同表里，
  缺少把它们**横向对齐成一条新事件**的合成器（宪法要求"事件必须由大模型判断"，但判断前得先有候选）。
- **用例**：① 凌晨办公室 GPS × 心率早搏 × 原话 → 跨域共振新锚点；② 跨域打分排序；
  ③ 为新 `EventAnchor` 提供 `evidence_refs` 与拟定标题/解读。
- **现状局限**：单维检索，跨域关系靠人肉对照；无窗口紧致度约束，弱相关信号会被拼成假事件。
- **接口**：`add_signal(signal_id, domain, occurred_at, reference, label, keywords)`、
  `synthesize() -> tuple[ResonanceCandidate, …]`；
  字段 `cross_domain_score / shared_keywords / evidence_refs / window`。
- **实测证据**：盲测 S3 合成 **1 条候选**（`physiology × utterance`，3 条证据引用，
  分数 4.725 / 4 域 / 9 小时窗口——单域信号被拒）；据此写入真实 `EventAnchor` 并跑完
  `CANDIDATE→ACTIVE→REVISED→MERGED→SPLIT` 全生命周期（4 个修订真实落库）。
- **验证计划**：`tests/bench/test_iron_laws_gate.py::test_stage3_synthesizes_new_event_and_runs_lifecycle`。
- **评审建议**：**通过**。建议下一轮把"跨域共振候选"接入 `Prediction` 对撞（现成的假说-演绎闭环）。

---

## 工具 6 · `CoOccurrenceRecallBus`（多键共现召回总线）

- **能力缺口**：多关键词只能拆成孤立全表扫描；而精确共现倒排索引对**同义词与 >2 字长词**天生失明 ——
  本次盲测实测：`["合伙","借贷","撕逼","银行流水"]` 在精确 1/2 元倒排上 **0 命中**，正对照 `["合伙","借条"]` 才 1 命中。
- **用例**：① 口语查询一次拓扑召回（实测命中 2 个候选实体，覆盖率 0.75）；② 词元级种子扩展 + 覆盖率排序。
- **现状局限**：精确索引对长词零召回；无覆盖率概念，分不清"没找到"与"找到一半"。
- **接口**：`recall(query_terms, limit=…, min_coverage=…) -> RecallResult`；
  字段 `hits / candidate_entities_scanned / tokens_cost / scan_mode`，`scan_mode` 恒为 `inverted_index_only`。
- **实测证据**：命中 `ent_old_wang`（覆盖率 0.75，延迟 **0.150 ms**，FULL 档 0.128 ms），
  对照精确索引 0.188 ms / 0 命中（正对照 `["合伙","借条"]` 1 命中）。
- **验证计划**：`tests/bench/test_iron_laws_gate.py::test_stage3_cooccurrence_bus_beats_isolated_scan`。
- **评审建议**：**通过**。**注意**：扩展键必须是词元级（≤2 字），否则永远匹配不到重叠 1/2 元索引 —— 这条已在代码注释与测试里钉死。

---

## 工具 7 · `PersonaGuard`（人设三防线机械拦截器）

- **能力缺口**：反谄媚、反教师爷、黑盒零 UI 三条防线此前全靠提示词自觉，没有任何机械拦截，
  事故可以静默流出到 23cm 柔性屏上。
- **用例**：① 句子级拦截谄媚同流合污 / 法律条文说教 / 问卷·图谱·置信度 UI 泄漏；
  ② 拦截后回退到诚实极简兜底话术（`GUARD_HONEST_FALLBACK`）；③ 与 `BrevityGuard` 串联，保证对外 1~3 句。
- **现状局限**：违规检测粒度是整段文本，无法定位到句子；无审计记录。
- **接口**：`review(text) -> PersonaDefenseVerdict(allowed, violations, sentences_dropped, brevity_intercepted)`；
  违规类型 `SYCOPHANCY / LECTURE / ZERO_UI`。
- **实测证据**：6 条对抗样本中 **4 条被机械拦截**（谄媚、法律说教、零 UI、长篇客服），
  合规样本放行；出站文本零 UI 违例（`outbound_ui_violations = ()`），句数 `[1,2,2,2,1,2]` 全部 ≤3 句。
- **验证计划**：`tests/bench/test_iron_laws_gate.py::test_stage7_persona_defense_lines_hold`。
- **评审建议**：**通过**。建议把违规类型做成可配置词表，随 `CommunicationExperience` 迭代（现在已是句子级，可增量扩张）。

---

## 工具 8 · `MindSequenceRunner`（心智四步序不可逆守卫）

- **能力缺口**：宪法要求的"①照镜子看自己 →②校准羁绊看关系 →③确立姿态定语调 →④审视现场看世界"
  在工程上没有强制：任何一步都可被随手调用，姿态常常先于羁绊，结论先于身份。
- **用例**：① 把四步序变成机械不可逆状态机（跳步/回退/重复一律抛错）；
  ② 第 N 步只能看到前 N-1 步产物（**数据可见性即防越权**）；③ 四步走完才允许**单次装载**驾驶舱骨架。
- **现状局限**：原先只有文档约束，无运行时守卫；Prompt 组装可任意取用后续步骤产物。
- **接口**：`begin()`、`advance(step, payload, tokens=…) -> StepOutcome`、`context_for(step)`、`as_manifest()`；
  错误类 `MindSequenceError`（乱序 / 回退 / 超预算 / 越权读取）。
- **实测证据**：盲测 S8 乱序装配被拦截、四步序严格成立、**驾驶舱单次装载**、
  装配 Token **880 / 1500**；7 个守卫单测覆盖跳步、回退、重开、越权、超预算、未完成装载。
- **验证计划**：`tests/bench/test_mind_sequence_guard.py`（9 个用例）。
- **评审建议**：**通过**。建议把 `token_budgets` 与 `runtime_policy.json` 联动，形成"每步预算"参数层。

---

## 提案与老约法三章的对应

| 约法三章 | 本提案书的回应 |
| --- | --- |
| 不要只验智商，要沉淀机制 | 8 件工具全部落地为可复用算子，并各有一条"机制级"教训写入代码注释（误差有界压缩、词元级扩展、数据可见性防越权…） |
| 不要自造数据自证 | 所有"实测证据"数字都来自**独立对抗发生器**驱动的八阶段盲测快照（`evidence/gate_snapshot.json`、`evidence/full_snapshot.json`，含修复前对照 `evidence/full_snapshot_prefix_461k.json`） |
| 不许有占位符 | `tests/bench/test_tool_catalog.py::test_no_placeholder_markers_in_new_bench_and_tool_sources` 机械扫描 17 个交付源文件，零命中 |

## 待总工裁决事项

1. 8 件提案是否**全部批准**（`approve`）/ 部分要求改动（`request_changes`）？
   - 建议重点看：工具 2 的 `scale_counts` 语义说明、工具 6 的扩展表可配置化、工具 8 的每步预算参数化。
2. 是否把第 11 件工具（**全库增量图索引**，见诊断书 §2.3）列为下一轮 P1？
   本轮修订：假冲击被修掉后，S3 全库建图已不再打爆内存（1,674.0 ms / 181.4 MB 增量，八阶段单进程跑通），
   因此它从"阻塞项"降为"架构缺口"——仍建议立项，但优先级低于 S1 抽取计费解耦。
3. 冲击判据要不要再加**三轴方向性判据**（把 7 条跑步尖峰也从 `IMPACT` 里请出去）？
   取舍点：存储宝贵（7 行）vs 宁可多留可疑；建议由总工在"阈值即法律"的参数层裁决。
