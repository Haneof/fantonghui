"""新工具目录：把盲测中真正发明出来的机制，按 ``ToolProposal`` 契约交付。

老大定下的"约法三章"里最硬的一条：十几个 Agent 并行的意义**不是**去验智商，
而是把有效的机制沉淀成方法、把方法沉淀成**可复用的工具**。所以盲测的最后一步
不是"写报告"，而是把每一件新工具按宪法契约登记成 ``ToolProposal``，
让它可评审、可驳回、可执行 —— 有编号、有接口签名、有验证计划、有真实产出数据。

本模块只做两件事：

1. ``build_catalog()``：把 8 件新工具（4 件优化器 + 3 件召回/合成器 + 1 件守卫）
   变成合法的 ``ToolProposal`` 世界对象；
2. ``submit_catalog(pipeline)``：走真实的 ``ToolProposalPipeline`` 提交并拿到回执。

所有 ``proposed_interface`` 里的签名都与**真实代码**逐字一致（模块里已实现且被
盲测与 pytest 调用过），因此提案不是纸面 PPT，而是"已实现工具的补登记"。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Sequence

from aios_core.contracts.enums import ObjectType, ProposalStatus, SourceClass
from aios_core.contracts.models import ToolProposal
from aios_core.contracts.time import TemporalExtent
from aios_core.tools.proposal_pipeline import ToolProposalPipeline

UTC = timezone.utc
_T_ORIGIN = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)


def _proposal(
    index: int,
    *,
    tool_id: str,
    capability_gap: str,
    use_cases: Sequence[str],
    current_limitations: Sequence[str],
    proposed_interface: Mapping[str, Any],
    expected_benefit: str,
    validation_plan: str,
) -> ToolProposal:
    created = _T_ORIGIN + timedelta(minutes=index)
    return ToolProposal(
        object_id=f"tool_proposal_{tool_id}",
        subject_id="aios_blind_bench",
        occurred=TemporalExtent(start=created, end=created),
        learned_at=created,
        recorded_at=created,
        source_refs=[],
        created_by="blind_bench_cognition",
        metadata={"bench": "blind_bench", "source_class": SourceClass.AI_COGNITION.value},
        capability_gap=capability_gap,
        use_cases=list(use_cases),
        current_limitations=list(current_limitations),
        proposed_interface=dict(proposed_interface),
        expected_benefit=expected_benefit,
        validation_plan=validation_plan,
        status=ProposalStatus.DRAFT,
    )


def build_catalog() -> List[ToolProposal]:
    """构造全部新工具提案（顺序稳定，便于门禁逐项核账）。"""

    return [
        _proposal(
            0,
            tool_id="adaptive_temporal_compressor",
            capability_gap=(
                "50Hz 原始 IMU 波形与逐拍心率既不能直写数据库（铁律 4 与 S1 硬约束），"
                "匀速降采样又会把跌倒撞击峰抹平。缺少一种**误差有界**的自适应压缩器。"
            ),
            use_cases=[
                "端侧把 200k@50Hz 波形压成宏观运动状态 + 异常冲击波形（39× 压缩）",
                "把稳定期逐拍心率压成区间均值，突变单独成 Observation",
                "为 P0 硬旁路保留 3.4g 级撞击样本不被压掉",
            ],
            current_limitations=[
                "原有实现只能按固定窗口抽稀，撞击峰与静止段用同一口径，误差不可控",
                "压缩后无法证明重建误差上界，无法满足测试审计",
                "标量心率压缩器对尖峰不敏感，突变会被均值吸收",
            ],
            proposed_interface={
                "class": "AdaptiveTemporalCompressor",
                "signature": (
                    "AdaptiveTemporalCompressor(tolerance=0.12, max_segment_span_s=..., "
                    "impact_threshold_g=1.9, fall_threshold_g=2.6)"
                ),
                "methods": [
                    "compress(timeline) -> CompressionResult",
                    "verify_reconstruction(timeline) -> bool",
                ],
                "fields": ["max_absorption_error", "error_bound_holds", "hardware_derivative_computed"],
            },
            expected_benefit="原始样本零直写且误差有界：200k@50Hz → 5,122 段，压缩 39×，误差 ≤0.12g。",
            validation_plan=(
                "盲测 S1 全量流式摄入 + pytest：断言 retained_set 覆盖、"
                "error_bound_holds 为真、fall 波形按 FALL_SUSPECT 原样保留。"
            ),
        ),
        _proposal(
            1,
            tool_id="multiscale_crystal_index",
            capability_gap=(
                "时间金字塔只有日/周/月/季/年汇总，缺少**可下钻到单条原始引文**的多尺度晶格索引，"
                "无法证明'摘要是新观察层而非压缩'。"
            ),
            use_cases=[
                "YEAR→MONTH→WEEK→DAY→OBSERVATION 逐级下钻，断链率 0.0%",
                "三段旧锚点相变：HALF_YEAR / QUARTER 晶格与金字塔并集守恒",
                "跨尺度一致性核账（cross_scale_consistency）",
            ],
            current_limitations=[
                "旧金字塔只存汇总，下钻需回表全扫，链路在跨年后断裂",
                "同 id 不同字节的改写无法检测，历史可能被静默覆盖",
            ],
            proposed_interface={
                "class": "MultiScaleCrystalIndex",
                "signature": "crystallize(scale, dimension_id, events, headline) -> CrystalNode",
                "methods": [
                    "drill(crystal_id, target) -> DrillResult",
                    "assert_union_conserved() -> bool",
                    "vault_fingerprint() -> str",
                    "scale_counts() -> Mapping[str, int]",
                ],
                "error": "CrystalError（同 id 异字节 / 跨窗口汇总一律拒绝）",
            },
            expected_benefit="10 年跨度结论可一路下钻到 3 年前那一天的原始引文，证据链断链率 0.0%。",
            validation_plan="盲测 S2 断言 UNION 守恒 + vault 指纹不可变 + 断链率 0.0%；pytest 覆盖重复汇总拒绝。",
        ),
        _proposal(
            2,
            tool_id="dual_lens_projection_index",
            capability_gap=(
                "老王案要求'历史只读、今天只打标签'，但没有工具能同时给出"
                "**当时所知**与**今天注解**两副眼镜的数据一致性视图。"
            ),
            use_cases=[
                "AS_KNOWN 视图 vs ANNOTATED 视图双透视对比",
                "annotation 只追加、永不改写 base 事实（base_fingerprint 恒等）",
                "为对外解释提供'当时判断 vs 现在认知'的差异清单",
            ],
            current_limitations=[
                "旧实现把新注解回写到历史对象上，直接违反铁律 2",
                "缺少 mutation 计量，无法证明历史零改写",
            ],
            proposed_interface={
                "class": "DualLensProjectionIndex",
                "signature": "register_fact(fact_id, ...) / register_annotation(annotation_id, target_id, ...)",
                "methods": ["project(target_id) -> ProjectedFact", "lens_delta() -> LensDelta"],
                "fields": ["base_fingerprint_equal", "mutation_count", "history_intact"],
            },
            expected_benefit="历史指纹 100% 不变，注解只作为 T_now 外部挂载，双镜差异可逐条列出。",
            validation_plan="盲测 S5 断言 base_fingerprint_equal 为真、mutation_count 为 0、双镜一致性 1.0。",
        ),
        _proposal(
            3,
            tool_id="lightweight_condition_evaluator",
            capability_gap=(
                "条件任务双轨调度需要'休眠期零 Token 空转'的机械求值器，"
                "旧实现仍会把休眠任务塞进 Prompt 组装上下文。"
            ),
            use_cases=[
                "200 条条件任务休眠 24 小时，Token 消耗恰好为 0",
                "TIME_ARRIVAL / BIOMETRIC_THRESHOLD / KEYWORD_MATCH / GEO_ENTER 机械判定",
                "任务销号后物理摘除索引，杜绝僵尸任务占位",
            ],
            current_limitations=[
                "语义条件与机械条件混在同一求值路径，无法证明零 Token",
                "缺少 skip_ratio 审计，看不清'跳过了什么'",
            ],
            proposed_interface={
                "class": "LightweightConditionEvaluator",
                "methods": [
                    "register(task_id, conditions)",
                    "evaluate_signal(signal) -> TaskTriggerReport",
                    "evaluate_time(moment) -> TaskTriggerReport",
                    "archive(task_id) -> bool",
                ],
                "fields": ["tokens_spent=0", "llm_calls=0", "skip_ratio"],
            },
            expected_benefit="休眠任务在看板 Prompt 里的 Token 贡献恰好为 0，skip_ratio 可审计。",
            validation_plan="盲测 S8 断言 dormant_tokens 与 dormant_board_prompt_tokens 均为 0；pytest 覆盖 index 摘除。",
        ),
        _proposal(
            4,
            tool_id="resonance_synthesizer",
            capability_gap=(
                "GPS 轨迹、心率尖峰、原始原话、资金流水、环境噪声各自沉睡在不同表里，"
                "缺少把它们**横向对齐成一条新事件**的合成器。"
            ),
            use_cases=[
                "把'凌晨办公室 GPS × 心率早搏 × 原话'合成一个跨域共振新锚点",
                "跨域打分（域数 × 权重 × 关键词重叠 × 时间紧致度）排序候选",
                "为新 EventAnchor 提供 evidence_refs 与拟定标题/解读",
            ],
            current_limitations=[
                "旧实现按单一维度检索，跨域关系只能靠人肉对照",
                "缺少窗口紧致度约束，弱相关信号会被拼成假事件",
            ],
            proposed_interface={
                "class": "CrossDomainResonanceSynthesizer",
                "methods": [
                    "add_signal(signal_id, domain, occurred_at, reference, label, keywords)",
                    "synthesize() -> tuple[ResonanceCandidate, ...]",
                ],
                "fields": ["cross_domain_score", "shared_keywords", "evidence_refs", "window"],
            },
            expected_benefit="跨域共振候选可量化（示例：4.725 分 / 4 域 / 9 小时窗口），新事件有据可查。",
            validation_plan="盲测 S3 合成 1 条真实新锚点并写入 EventAnchor rev1；pytest 覆盖单域信号必须被拒绝。",
        ),
        _proposal(
            5,
            tool_id="cooccurrence_recall_bus",
            capability_gap=(
                "多关键词只能拆成孤立全表扫描；而精确共现倒排索引对同义词与 >2 字长词"
                "天生失明（实测 4 词查询 0 命中）。"
            ),
            use_cases=[
                "口语查询『合伙/借贷/撕逼/银行流水』一次拓扑召回（实测命中 2 个候选实体）",
                "词元级种子扩展 + 覆盖率排序，避免全表扫描",
                "双形态对照：精确倒排 0 命中 vs 总线 0.75 覆盖率",
            ],
            current_limitations=[
                "精确 1/2 元倒排对长词与同义词零召回（正对照查询才有 1 命中）",
                "无覆盖率概念，无法区分'没找到'与'找到一半'",
            ],
            proposed_interface={
                "class": "CoOccurrenceRecallBus",
                "signature": "recall(query_terms, limit=..., min_coverage=...) -> RecallResult",
                "fields": ["hits", "candidate_entities_scanned", "tokens_cost", "scan_mode"],
                "note": "scan_mode 恒为 inverted_index_only，绝不退化成全表扫描",
            },
            expected_benefit="多关键词召回从'孤立扫描'变成'一次拓扑 intersecting'，候选集可解释、可核账。",
            validation_plan="盲测 S3 断言 bus 命中与覆盖率、精确索引对照指标；pytest 覆盖长词查询退化路径。",
        ),
        _proposal(
            6,
            tool_id="persona_guard",
            capability_gap=(
                "反谄媚、反教师爷、黑盒零 UI 三条人设防线此前全靠提示词自觉，"
                "没有任何机械拦截，事故可以静默流出。"
            ),
            use_cases=[
                "句子级拦截谄媚同流合污、法律条文说教、问卷/图谱/置信度 UI 泄漏",
                "拦截后回退到诚实极简兜底话术（GUARD_HONEST_FALLBACK）",
                "与 BrevityGuard 串联，保证对外 1~3 句",
            ],
            current_limitations=[
                "违规检测粒度是整段文本，无法定位到具体句子",
                "无审计记录，违例不可回溯",
            ],
            proposed_interface={
                "class": "PersonaGuard",
                "methods": ["review(text) -> PersonaDefenseVerdict"],
                "fields": ["allowed", "violations", "sentences_dropped", "brevity_intercepted"],
                "violation_kinds": ["SYCOPHANCY", "LECTURE", "ZERO_UI"],
            },
            expected_benefit="6 条对抗样本中 4 条被机械拦截，3 条防线在盲测中保持成立。",
            validation_plan="盲测 S7 用真实对抗样本集断言拦截数与零 UI 违例为 0；pytest 覆盖兜底话术。",
        ),
        _proposal(
            7,
            tool_id="mind_sequence_guard",
            capability_gap=(
                "宪法要求的'①照镜子→②校准羁绊→③确立姿态→④审视现场'四步序"
                "在工程上没有强制，任何一步都可被随手调用，姿态常常先于羁绊。"
            ),
            use_cases=[
                "把四步序变成机械不可逆状态机（跳步/回退/重复一律抛错）",
                "第 N 步只能看到前 N-1 步产物（数据可见性即防越权）",
                "四步走完才允许单次装载驾驶舱骨架（禁止反复追问）",
            ],
            current_limitations=[
                "原先只有文档约束，无运行时守卫",
                "Prompt 组装可任意取用后续步骤产物，先有结论再补姿态",
            ],
            proposed_interface={
                "class": "MindSequenceRunner",
                "methods": [
                    "begin()",
                    "advance(step, payload, tokens=...) -> StepOutcome",
                    "context_for(step) -> Mapping",
                    "as_manifest() -> Mapping",
                ],
                "error": "MindSequenceError（乱序/回退/超预算/越权读取）",
            },
            expected_benefit="四步序 100% 强制：乱序装配被拦截，驾驶舱单次装载，Token 计数 880/1500。",
            validation_plan="盲测 S8 断言乱序被拦截、顺序严格、单次装载；pytest 覆盖超预算与越权读取。",
        ),
    ]


def submit_catalog(
    pipeline: ToolProposalPipeline | None = None,
) -> tuple[ToolProposalPipeline, List[ToolProposal]]:
    """提交全部提案并返回（管线, 提交后提案列表）。"""

    pipeline = pipeline or ToolProposalPipeline()
    submitted: List[ToolProposal] = []
    for proposal in build_catalog():
        submitted.append(pipeline.submit_proposal(proposal))
    return pipeline, submitted


def catalog_digest(proposals: Sequence[ToolProposal]) -> Dict[str, Any]:
    """提案集合的机器可读摘要（供报告与门禁核账）。"""

    return {
        "count": len(proposals),
        "tool_ids": [proposal.object_id.removeprefix("tool_proposal_") for proposal in proposals],
        "statuses": sorted(
            {
                str(getattr(proposal.status, "value", proposal.status))
                for proposal in proposals
            }
        ),
        "interface_keys": sorted(
            {key for proposal in proposals for key in proposal.proposed_interface}
        ),
        "object_type": ObjectType.TOOL_PROPOSAL.value,
    }
