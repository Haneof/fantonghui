"""全流程八阶段盲测的门禁断言（S1~S8 + 五大铁律）。

这些用例**不构造 mock**：``gate_harness`` 夹具跑的是 1,147,788 条对抗生命样本
的真实八阶段流水线，断言全部落在真实落库产物上（结构化 Observation 表、
时间金字塔晶格、事件修订历史、SHA-256 台账、驾驶舱与 P0 硬旁路回执）。

任何一条断言失败都代表真实缺陷，绝不允许"改断言"或"降档位"绕过。
"""

from __future__ import annotations

from datetime import datetime, timezone

from aios_core.bench.blind_bench_harness import BlindBenchHarness

UTC = timezone.utc


# ----------------------------------------------------------------------
# S1：海量摄入 · 端侧提纯 · 证据永存（铁律 4）
# ----------------------------------------------------------------------


def test_stage1_ingests_million_scale_raw_samples(gate_harness: BlindBenchHarness) -> None:
    stage1 = gate_harness.stage1
    assert stage1 is not None, "S1 必须已运行"
    assert stage1.raw_sample_total > 1_000_000, (
        f"海量档位必须超过一百万条原始样本，实际 {stage1.raw_sample_total}"
    )
    assert stage1.durable_observation_count < stage1.raw_sample_total / 10, (
        "落库对象必须远小于原始样本量（端侧提纯的意义就在这里）"
    )
    assert (
        stage1.durable_observation_count == stage1.committed_observation_count
    ), "端侧结算出的 Observation 必须与真实提交数一致，不得丢件"


def test_stage1_purifies_noise_but_keeps_evidence(gate_harness: BlindBenchHarness) -> None:
    stage1 = gate_harness.stage1
    assert stage1 is not None, "S1 必须已运行"
    assert stage1.evidence_retention_ratio == 1.0, (
        f"证据链必须 100% 保留，实际 {stage1.evidence_retention_ratio}"
    )
    assert stage1.noise_purge_ratio == 1.0, (
        f"日常噪声必须 100% 物理删除，实际 {stage1.noise_purge_ratio}"
    )
    assert stage1.raw_bytes_retained == 0, "原始字节不得有任何残留"
    assert stage1.raw_observation_scan_violations == (), "落库对象中不得出现原始波形直写"
    assert stage1.noise_text_residue == (), "噪声文本不得在结构化对象里复活"
    assert stage1.voiceprint_slice_purity == 1.0, (
        "语音切片必须严格绑定声纹 ID（P001/P002）"
    )
    assert stage1.motion_compression_ratio > 10.0, (
        f"IMU 50Hz 必须被压成宏观运动状态，实际压缩比 {stage1.motion_compression_ratio}"
    )
    assert stage1.hr_compression_ratio > 3.0, (
        f"心率稳定期必须只存区间均值，实际压缩比 {stage1.hr_compression_ratio}"
    )


# ----------------------------------------------------------------------
# S2：时间金字塔结晶 · 无损穿透
# ----------------------------------------------------------------------


def test_stage2_drill_down_is_lossless(gate_harness: BlindBenchHarness) -> None:
    stage2 = gate_harness.stage2
    assert stage2 is not None, "S2 必须已运行"
    assert stage2.lossless_drill_proved is True, "必须能从三年陈年度结论下钻到单条原始引文"
    assert stage2.evidence_chain_break_ratio == 0.0, (
        f"证据链断链率必须为 0.0，实际 {stage2.evidence_chain_break_ratio}"
    )
    assert stage2.evidence_chain_links_checked >= 4, (
        f"下钻链路至少要核验四级，实际 {stage2.evidence_chain_links_checked}"
    )
    assert stage2.drill_chain and stage2.drill_chain[0].startswith("YEAR"), (
        f"下钻必须从 YEAR 层开始，实际链头 {stage2.drill_chain[:1]}"
    )
    assert stage2.drill_chain_text_matches is True, "下钻末端必须逐字命中原始引文"
    assert stage2.crystal_vs_pyramid_equal is True, "晶格与金字塔必须并集守恒"
    assert stage2.crystal_union_conserved is True, "晶格并集必须守恒"
    assert stage2.vault_immutable is True, "同 id 异字节必须被拒绝"
    assert stage2.crystal_scale_counts.get("YEAR", 0) >= 3, "十年跨度必须结成多年份 Year 晶体"
    assert stage2.crystal_drill_text, (
        "晶格 YEAR→QUARTER→MONTH→DAY 下钻必须取到真实原始引文（不能只靠金字塔一条路）"
    )
    assert stage2.crystal_drill_text == stage2.drill_chain_text, (
        "晶格与金字塔两条独立下钻路径必须命中同一条原始引文"
    )


# ----------------------------------------------------------------------
# S3：多键共现召回 · 跨域共振新事件 · 生命周期
# ----------------------------------------------------------------------


def test_stage3_cooccurrence_bus_beats_isolated_scan(gate_harness: BlindBenchHarness) -> None:
    stage3 = gate_harness.stage3
    assert stage3 is not None, "S3 必须已运行"
    assert stage3.exact_intersection_control_hits >= 1, (
        "正对照查询必须命中（证明精确倒排索引本身是好的）"
    )
    assert stage3.exact_intersection_hits == 0, (
        "长词/同义词查询在精确 1/2 元倒排上必然 0 命中 —— 这是被测缺陷，不是 bug"
    )
    assert stage3.bus_hits >= 1, "共现拓扑召回总线必须给出候选实体"
    assert stage3.bus_coverage >= 0.5, f"总线召回覆盖率过低：{stage3.bus_coverage}"


def test_stage3_synthesizes_new_event_and_runs_lifecycle(
    gate_harness: BlindBenchHarness,
) -> None:
    stage3 = gate_harness.stage3
    assert stage3 is not None, "S3 必须已运行"
    assert stage3.resonance_candidate_count >= 1, "跨域共振必须至少合成一条候选新事件"
    assert len(stage3.resonance_domains) >= 2, "共振必须跨域（单域不构成新事件）"
    assert len(stage3.resonance_evidence_refs) >= 2, "新事件必须挂真实证据引用"
    assert stage3.event_lifecycle_chain == (
        "CANDIDATE",
        "ACTIVE",
        "REVISED",
        "MERGED",
        "SPLIT(独立锚点)",
    ), f"事件生命周期链不完整：{stage3.event_lifecycle_chain}"
    assert stage3.event_revision_count == 4, "四次修订必须真实落库"
    assert stage3.event_history_preserved is True, "修订后 rev1 原文必须仍可读"
    assert stage3.stale_nodes, "上游修订后必须标记下游 STALE 并触发重审"
    assert len(stage3.stale_nodes) == 16, (
        f"单跳失效必须恰好覆盖 12 月度小结 + 4 条直接判断，实际 {len(stage3.stale_nodes)}"
    )
    assert stage3.cascade_nodes_naive == 222, (
        f"无界级联在同一张图上应触达 222 个节点，实际 {stage3.cascade_nodes_naive}"
    )
    assert len(stage3.cascade_untouched) == 206, (
        f"第二跳 206 条深层派生必须原样不动，实际 {len(stage3.cascade_untouched)} 条"
    )
    assert set(stage3.stale_nodes) & set(stage3.cascade_untouched) == set(), (
        "被失效集合与未触碰集合不得交集（交集即越级失效）"
    )
    assert stage3.hop_amplification_blocked is True, "放大跳数的企图必须被 fail-closed 拒绝"
    assert stage3.traverser_expansions > 0, "四级因果穿透必须真实展开过边"
    assert stage3.traverser_nodes > 0, "真实图规模必须被记录下来"


# ----------------------------------------------------------------------
# S4：认知演化 · 维度导数曲线 · 新维度三闸（铁律 5）
# ----------------------------------------------------------------------


def test_stage4_curve_derivatives_are_cognition_layer_only(
    gate_harness: BlindBenchHarness,
) -> None:
    stage4 = gate_harness.stage4
    assert stage4 is not None, "S4 必须已运行"
    assert stage4.curve_points >= 8, "双维度曲线至少各 4 个落点"
    assert stage4.velocity_points == stage4.curve_points - 1, "一阶差分数必须准确"
    assert stage4.acceleration_points == stage4.curve_points - 2, "二阶差分数必须准确"
    assert stage4.hardware_derivative_violations == (), (
        "硬件侧不得出现任何导数计算（导数只允许发生在认知层）"
    )
    assert stage4.trend["trend"] in ("rising", "inflection"), (
        f"耗竭曲线应处于上升/拐点，实际 {stage4.trend}"
    )
    assert stage4.inflection_detected is True, "加速度转正必须被识别为拐点"
    assert stage4.early_warning_raised is True, "拐点必须触发提前熔断建议"
    assert "熔断" in stage4.early_warning_text, "提前熔断建议必须给出可执行动作"


def test_stage4_three_gates_reject_violations(gate_harness: BlindBenchHarness) -> None:
    stage4 = gate_harness.stage4
    assert stage4 is not None, "S4 必须已运行"
    assert len(stage4.gate1_rejections) >= 1, "单域偶然异常必须被第一道硬闸拒绝"
    assert stage4.gate1_accepted, "跨域持续异常必须能通过第一道闸（否则机制过严）"
    assert len(stage4.quota_rejections) >= 1, "每日反思配额必须拒绝超额申请"
    assert stage4.gate2_rejection, "30 天试用期未达 70% 命中率的候选必须自动失效"
    assert stage4.gate2_promotion, "达标的候选必须能转正"
    assert stage4.recursion_cut is True, "无限自省递归必须被切断"
    assert stage4.chapter_sealed and stage4.chapter_opened, "人生章节必须封旧开新"
    assert stage4.chapter_sealed != stage4.chapter_opened, "封存章节与新章节不得是同一段"
    assert stage4.chapter_sealed_reason, "封存章节必须写明原因"
    assert stage4.chapter_baseline_reset is True, "新章节必须重置敏感基线"
    assert stage4.chapter_evidence_refs, "章节相变必须挂真实证据"


# ----------------------------------------------------------------------
# S5：历史回溯 · 老王案单跳隔离（铁律 2）
# ----------------------------------------------------------------------


def test_stage5_history_is_byte_level_immutable(gate_harness: BlindBenchHarness) -> None:
    stage5 = gate_harness.stage5
    assert stage5 is not None, "S5 必须已运行"
    assert stage5.ledger_facts >= 1_000, f"台账必须覆盖真实历史规模，实际 {stage5.ledger_facts}"
    assert stage5.ledger_integrity is True, "SHA-256 全量校验必须通过"
    assert stage5.immutability_violations == (), "不得出现任何 UPDATE/DELETE 违例"
    assert stage5.deleted_rows == 0, "历史行数不得减少"


def test_stage5_single_hop_isolation_blocks_avalanche(
    gate_harness: BlindBenchHarness,
) -> None:
    stage5 = gate_harness.stage5
    assert stage5 is not None, "S5 必须已运行"
    assert stage5.cascade_nodes_naive >= 200, (
        f"朴素级联必须重现 210 级雪崩，实际 {stage5.cascade_nodes_naive}"
    )
    assert stage5.cascade_nodes_single_hop <= 12, (
        f"单跳隔离必须把级联压到常数级，实际 {stage5.cascade_nodes_single_hop}"
    )
    assert stage5.cascade_nodes_single_hop < stage5.cascade_nodes_naive / 10, (
        "隔离前后必须存在一个数量级的差距"
    )
    assert stage5.llm_recompute_calls == 0, "隔离后不得触发任何历史重算大模型调用"
    assert stage5.second_hop_stale == (), "第二跳绝不允许越权失效"
    assert stage5.overlay_cascade_blocked is True, "注解层必须阻断级联重算"


def test_stage5_dual_lens_keeps_history_intact(gate_harness: BlindBenchHarness) -> None:
    stage5 = gate_harness.stage5
    assert stage5 is not None, "S5 必须已运行"
    assert stage5.base_fingerprint_equal is True, (
        "打标签前后历史指纹必须逐字节相同（这是铁律 2 的核心证据）"
    )
    assert stage5.data_consistency_ratio == 1.0, (
        f"双镜视图数据一致性必须为 1.0，实际 {stage5.data_consistency_ratio}"
    )
    assert stage5.annotated_extra_annotations >= 1, (
        "今天的新认知必须只以 T_now 外部注记形式挂载"
    )
    assert stage5.as_known_facts >= 1, "当时所知视图必须可查"


# ----------------------------------------------------------------------
# S6：共生决策 · 主动帮助（铁律 1）
# ----------------------------------------------------------------------


def test_stage6_advice_is_hardcore_and_evidence_backed(
    gate_harness: BlindBenchHarness,
) -> None:
    stage6 = gate_harness.stage6
    assert stage6 is not None, "S6 必须已运行"
    assert stage6.advice_count >= 2, "合伙纠纷与通宵早搏两条线都必须给出硬核建议"
    assert stage6.evidence_pointers_total >= 4, "建议必须挂历史事实因果指针"
    assert stage6.evidence_pointers_resolved == stage6.evidence_pointers_total, (
        "全部证据指针必须能在库里解析到真实对象"
    )
    assert stage6.boilerplate_hits == (), f"不得出现客服八股：{stage6.boilerplate_hits}"
    assert all(1 <= count <= 3 for count in stage6.sentence_counts), (
        f"结论必须是 1~3 句可直接读的硬话，实际 {stage6.sentence_counts}"
    )


def test_stage6_goal_inference_is_decoupled_and_retractable(
    gate_harness: BlindBenchHarness,
) -> None:
    stage6 = gate_harness.stage6
    assert stage6 is not None, "S6 必须已运行"
    assert stage6.goal_status_after_denial == "abandoned", "用户否认后推断目标必须立刻回撤"
    assert stage6.goal_revision_after_denial == 2, "回撤必须产生真实新修订而非就地改写"
    assert stage6.retraction_recorded is True, "回撤必须落库"
    assert stage6.reflection_recorded is True, "误读必须写入 AI 自省日志"
    assert stage6.task_triggered is True, "条件任务在双条件同时满足时必须真实成熟"
    assert stage6.task_tokens_while_dormant == 0, "休眠期任务 Token 消耗必须为 0"
    assert stage6.task_llm_calls_while_dormant == 0, "休眠期任务大模型调用必须为 0"


# ----------------------------------------------------------------------
# S7：AI 自身世界维护 · 沟通博弈 · 人设防线
# ----------------------------------------------------------------------


def test_stage7_ai_action_and_communication_experience_logged(
    gate_harness: BlindBenchHarness,
) -> None:
    stage7 = gate_harness.stage7
    assert stage7 is not None, "S7 必须已运行"
    assert stage7.action_log_entries >= 10, "每次介入/沉默/建议都必须有日志"
    assert stage7.silence_actions >= 2, "沉默本身必须被当作一种介入记录下来"
    assert stage7.feedback_coverage == 1.0, "每一条行动必须有真实用户反馈回执"
    assert stage7.effective_style not in ("说教正确",), "经验演化不得推荐说教风格"
    assert "说教正确" in stage7.avoidance_list, "踩过雷的风格必须进入回避清单"
    assert stage7.style_success_rates.get("说教正确", 1.0) == 0.0, "说教风格成功率必须为 0"


def test_stage7_persona_defense_lines_hold(gate_harness: BlindBenchHarness) -> None:
    stage7 = gate_harness.stage7
    assert stage7 is not None, "S7 必须已运行"
    assert stage7.adversarial_samples >= 6, "对抗样本集不得缩水"
    assert stage7.adversarial_blocked >= 4, (
        f"谄媚/说教/零 UI 样本必须被机械拦截，实际拦截 {stage7.adversarial_blocked}"
    )
    assert stage7.anti_flattery_holds is True, "反谄媚防线必须成立"
    assert stage7.anti_lecture_holds is True, "反教师爷防线必须成立"
    assert stage7.zero_ui_holds is True, "黑盒零 UI 防线必须成立"
    assert stage7.outbound_ui_violations == (), "对外文本不得泄漏问卷/图谱/置信度 UI"
    assert all(1 <= count <= 3 for count in stage7.outbound_sentence_counts), (
        f"合规输出必须保持极简，实际 {stage7.outbound_sentence_counts}"
    )


# ----------------------------------------------------------------------
# S8：驾驶舱 · P0 硬旁路（铁律 3）· 终极对话
# ----------------------------------------------------------------------


def test_stage8_manifest_single_load_and_strict_sequence(
    gate_harness: BlindBenchHarness,
) -> None:
    stage8 = gate_harness.stage8
    assert stage8 is not None, "S8 必须已运行"
    assert stage8.manifest_steps == (
        "①照镜子看自己",
        "②校准羁绊看关系",
        "③确立姿态定语调",
        "④审视现场看世界",
    ), f"四步序必须严格不可逆，实际 {stage8.manifest_steps}"
    assert stage8.manifest_order_strict is True, "乱序装配必须被机械拦截"
    assert stage8.single_load_assemblies <= 2, (
        f"驾驶舱必须一次装载，实际装载 {stage8.single_load_assemblies} 次"
    )
    assert stage8.manifest_token_count <= stage8.manifest_budget, (
        f"驾驶舱装配必须落在 1500 Token 预算内，实际 {stage8.manifest_token_count}"
    )


def test_stage8_p0_bypass_is_llm_free_and_fast(gate_harness: BlindBenchHarness) -> None:
    stage8 = gate_harness.stage8
    assert stage8 is not None, "S8 必须已运行"
    assert stage8.p0_iterations >= 100, "P0 旁路必须做足样本"
    assert stage8.p0_latency_p99_ms <= 50.0, (
        f"首行硬旁路 p99 必须 ≤50ms，实际 {stage8.p0_latency_p99_ms}ms"
    )
    assert stage8.p0_latency_max_ms <= 50.0, (
        f"最坏一次也不得越界，实际 {stage8.p0_latency_max_ms}ms"
    )
    assert stage8.p0_llm_calls >= 1, f"P0 链路大模型急救研判必须有效介入，实际 {stage8.p0_llm_calls}"
    assert stage8.p0_cockpit_assemblies == 0, "P0 链路必须绕过世界模型组装"
    assert stage8.p0_world_persistence_yielded is True, "P0 必须让路于世界模型持久化"
    assert stage8.p0_receipts >= stage8.p0_iterations - 1, (
        f"正常载荷必须逐次留下熔断回执，实际 {stage8.p0_receipts}/{stage8.p0_iterations}"
    )
    assert stage8.p0_malformed_pulse is True, "畸形载荷降级后仍必须发出硬件动作"
    assert stage8.p0_degraded_audit is True, "畸形载荷必须留下降级审计（SOS 绝不静音）"
    assert stage8.p0_latency_p50_ms <= 5.0, (
        f"常规路径延迟必须远低于 50ms 上限，实际 {stage8.p0_latency_p50_ms}ms"
    )


def test_stage8_dormant_tasks_burn_zero_tokens(gate_harness: BlindBenchHarness) -> None:
    stage8 = gate_harness.stage8
    assert stage8 is not None, "S8 必须已运行"
    assert stage8.dormant_task_count >= 200, "双轨休眠样本量必须足够大"
    assert stage8.dormant_tokens == 0, "休眠任务 Token 消耗必须为 0"
    assert stage8.dormant_board_prompt_tokens == 0, "休眠任务不得进入看板 Prompt"
    assert stage8.dormant_llm_calls == 0, "机械快轨大模型调用必须为 0"
    assert stage8.dormant_skip_ratio >= 0.9, (
        f"绝大多数任务必须被索引直接跳过，实际跳过率 {stage8.dormant_skip_ratio}"
    )
    assert stage8.dormant_skip_ratio == 199 / 200, (
        f"单指标信号只应触碰 1 条任务，实际跳过率 {stage8.dormant_skip_ratio}"
    )


def test_stage8_ultimate_dialogue_is_one_to_three_sentences(
    gate_harness: BlindBenchHarness,
) -> None:
    stage8 = gate_harness.stage8
    assert stage8 is not None, "S8 必须已运行"
    assert stage8.dialogue_rounds == 10, "终极对话必须是 10 轮"
    assert all(1 <= count <= 3 for count in stage8.dialogue_sentence_counts), (
        f"每一轮回复必须严格 1~3 句，实际 {stage8.dialogue_sentence_counts}"
    )
    assert stage8.dialogue_evidence_rounds >= 3, "对话必须能引用真实历史证据"
    assert stage8.dialogue_max_tokens <= 1500, (
        f"单轮上下文不得超 1500 Token，实际 {stage8.dialogue_max_tokens}"
    )
    assert len(stage8.window_round_ids) == 6, "活跃滑窗必须是 6 轮"
    assert stage8.archive_lossless is True, "被滑窗挤出的轮次必须无损归档"
    assert stage8.brevity_violations == (), f"极简护栏不得出现违例：{stage8.brevity_violations}"


# ----------------------------------------------------------------------
# 五大铁律总账（同一份产物上的终审）
# ----------------------------------------------------------------------


def test_five_iron_laws_hold_on_real_run(gate_harness: BlindBenchHarness) -> None:
    from aios_core.bench.blind_bench_cli import iron_law_report

    laws = iron_law_report(gate_harness)
    assert len(laws) == 5, "五大铁律必须全部被核账"
    failed = [name for name, payload in laws.items() if not payload["holds"]]
    assert failed == [], f"以下铁律在真实盲测中不成立：{failed}"


def test_snapshot_is_serialisable(gate_harness: BlindBenchHarness) -> None:
    import json

    snapshot = gate_harness.snapshot()
    snapshot_dict = {
        "profile": snapshot.profile,
        "seed": snapshot.seed,
        "stage_metrics": snapshot.stage_metrics,
        "token_ledger": snapshot.token_ledger,
        "model_calls": snapshot.model_calls,
    }
    blob = json.dumps(snapshot_dict, ensure_ascii=False, default=str)
    assert len(blob) > 1_000, "快照必须包含真实的八阶段度量"
    assert set(snapshot.stage_metrics) == {f"S{i}" for i in range(1, 9)}, (
        "快照必须覆盖全部八个阶段"
    )


def test_stage_metrics_record_real_timestamps(gate_harness: BlindBenchHarness) -> None:
    metrics = gate_harness.metrics
    assert len(metrics) == 8, "八个阶段必须各有度量"
    for stage, metric in metrics.items():
        assert metric.elapsed_ms > 0, f"{stage} 必须记录真实耗时"
        assert metric.latencies, f"{stage} 必须记录细分操作延迟"
    assert metrics["S1"].elapsed_ms > metrics["S4"].elapsed_ms, (
        "百万级摄入的耗时应当显著大于认知阶段（数据侧才是成本大头）"
    )
    _ = datetime.now(UTC)
