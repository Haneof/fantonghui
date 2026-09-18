"""盲测八阶段的产出物结构（纯数据，便于报告与断言共享同一事实源）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Sequence

from aios_core.ingest.edge_stream_purifier import PurificationReport

__all__ = [
    "StageEightResult",
    "StageFiveResult",
    "StageFourResult",
    "StageOneResult",
    "StageSevenResult",
    "StageSixResult",
    "StageThreeResult",
    "StageTwoResult",
]


@dataclass(frozen=True, slots=True)
class StageOneResult:
    """S1：百万级摄入 → 端侧提纯 → 事实落库。"""

    profile_name: str
    raw_sample_total: int
    durable_observation_count: int
    committed_observation_count: int
    report: PurificationReport
    evidence_observation_ids: Mapping[str, str]
    noise_texts: tuple[str, ...]
    evidence_keys: tuple[str, ...]
    evidence_retention_ratio: float
    noise_purge_ratio: float
    motion_compression_ratio: float
    hr_compression_ratio: float
    tombstoned_voiceprints: tuple[str, ...]
    bound_voiceprints: Mapping[str, str]
    voiceprint_slice_purity: float
    raw_bytes_retained: int
    db_size_bytes: int
    duplicate_observations_dropped: int = 0
    durable_by_kind: Mapping[str, int] = field(default_factory=dict)
    raw_observation_scan_violations: tuple[str, ...] = ()
    noise_text_residue: tuple[str, ...] = ()

    @property
    def compression_ratio(self) -> float:
        if not self.durable_observation_count:
            return 0.0
        return self.raw_sample_total / self.durable_observation_count


@dataclass(frozen=True, slots=True)
class StageTwoResult:
    """S2：时间金字塔 + 七档结晶 + 无损穿透。"""

    digest_count: int
    pyramid_years: tuple[int, ...]
    drill_chain: tuple[str, ...]
    drill_chain_observation_id: str
    drill_chain_text: str
    drill_chain_expected_text: str
    drill_chain_text_matches: bool
    evidence_chain_break_ratio: float
    evidence_chain_links_checked: int
    union_conserved: bool
    vault_size: int
    vault_fingerprint_before: str
    vault_fingerprint_after: str
    crystal_scale_counts: Mapping[str, int]
    crystal_union_conserved: bool
    crystal_union_checked_levels: tuple[str, ...]
    crystal_vs_pyramid_equal: bool
    crystal_fingerprint_before: str
    crystal_fingerprint_after: str
    crystal_drill_text: str
    crystal_raw_event_count: int
    half_year_crystal_count: int
    vault_immutable: bool = True
    pyramid_latency_ms: float = 0.0

    @property
    def lossless_drill_proved(self) -> bool:
        return (
            self.drill_chain_text_matches
            and self.evidence_chain_break_ratio == 0.0
            and self.union_conserved
            and self.crystal_union_conserved
        )


@dataclass(frozen=True, slots=True)
class StageThreeResult:
    """S3：共现召回 + 跨域共振合成 + 事件生命周期。"""

    exact_intersection_hits: int
    exact_intersection_control_hits: int
    bus_hits: int
    bus_top_entity: str
    bus_coverage: float
    bus_recall_latency_ms: float
    exact_recall_latency_ms: float
    indexed_entities: int
    indexed_terms: int
    resonance_candidate_count: int
    resonance_domains: tuple[str, ...]
    resonance_evidence_refs: tuple[str, ...]
    synthesized_event_id: str
    event_lifecycle_chain: tuple[str, ...]
    event_revision_count: int
    event_history_preserved: bool
    stale_nodes: tuple[str, ...]
    cascade_untouched: tuple[str, ...]
    cascade_nodes_naive: int
    hop_amplification_blocked: bool
    traverser_nodes: int
    traverser_expansions: int
    traverser_fresh: bool


@dataclass(frozen=True, slots=True)
class StageFourResult:
    """S4：认知导数 + 新维度三闸 + 人生章节相变。"""

    curve_dimensions: tuple[str, ...]
    curve_points: int
    velocity_points: int
    acceleration_points: int
    hardware_derivative_violations: tuple[str, ...]
    trend: Mapping[str, Any]
    inflection_detected: bool
    early_warning_raised: bool
    early_warning_text: str
    gate1_rejections: tuple[str, ...]
    gate1_accepted: str
    quota_rejections: tuple[str, ...]
    gate2_rejection: str
    gate2_promotion: str
    recursion_cut: bool
    chapter_sealed: str
    chapter_opened: str
    chapter_sealed_reason: str
    chapter_baseline_reset: bool
    chapter_evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageFiveResult:
    """S5：历史不可篡改 + 单跳隔离防雪崩 + 双透镜。"""

    immutability_violations: tuple[str, ...]
    ledger_facts: int
    ledger_integrity: bool
    history_rewrites: int
    overlay_hops: int
    derived_recomputations: int
    annotation_id: str
    annotation_target: str
    overlay_cascade_blocked: bool
    cascade_nodes_naive: int
    cascade_nodes_single_hop: int
    untouched_downstream: int
    second_hop_stale: tuple[str, ...]
    llm_recompute_calls: int
    llm_calls_naive_estimate: int
    as_known_facts: int
    annotated_extra_annotations: int
    base_fingerprint_equal: bool
    data_consistency_ratio: float
    store_history_intact: bool
    deleted_rows: int


@dataclass(frozen=True, slots=True)
class StageSixResult:
    """S6：共生决策推演 + 主动帮助。"""

    advice_count: int
    advice_conclusions: tuple[str, ...]
    evidence_pointer_counts: tuple[int, ...]
    evidence_pointers_resolved: int
    evidence_pointers_total: int
    sentence_counts: tuple[int, ...]
    advice_program_rewrites: int
    model_outputs_preserved: bool
    task_id: str
    task_llm_calls_while_dormant: int
    task_tokens_while_dormant: int
    task_triggered: bool
    goal_id: str
    goal_status_after_denial: str
    goal_revision_after_denial: int
    retraction_recorded: bool
    reflection_recorded: bool
    proactive_help_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageSevenResult:
    """S7: evidence-linked communication history and protocol validation."""

    action_log_entries: int
    logged_postures: tuple[str, ...]
    silence_actions: int
    feedback_coverage: float
    scenario_samples: int
    reaction_counts: Mapping[str, int]
    style_statistics: Mapping[str, Mapping[str, float | int]]
    protocol_samples: int
    protocol_rejected: int
    protocol_rewritten: int
    protocol_violations: tuple[str, ...]
    model_content_preserved: bool


@dataclass(frozen=True, slots=True)
class StageEightResult:
    """S8：驾驶舱一次装配 + P0 硬旁路 + 条件双轨 + 终极对话。"""

    manifest_steps: tuple[str, ...]
    manifest_token_count: int
    manifest_budget: int
    single_load_assemblies: int
    manifest_layout_stable: bool
    runtime_call_order: tuple[str, ...]
    p0_iterations: int
    p0_latency_p50_ms: float
    p0_latency_p99_ms: float
    p0_latency_max_ms: float
    p0_llm_calls: int
    p0_cockpit_assemblies: int
    p0_world_persistence_yielded: bool
    p0_receipts: int
    p0_malformed_pulse: bool
    p0_degraded_audit: bool
    dormant_task_count: int
    dormant_tokens: int
    dormant_board_prompt_tokens: int
    dormant_llm_calls: int
    dormant_skip_ratio: float
    dormant_tick_ms: float
    dialogue_rounds: int
    dialogue_sentence_counts: tuple[int, ...]
    dialogue_evidence_rounds: int
    dialogue_max_tokens: int
    window_round_ids: tuple[str, ...]
    archive_lossless: bool
    dialogue_program_rewrites: int
    dialogue_model_outputs_preserved: bool


@dataclass(frozen=True, slots=True)
class HarnessSnapshot:
    """整轮压测的可序列化快照（报告与回归共享）。"""

    profile: str
    seed: int
    stage_metrics: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    token_ledger: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    model_calls: Mapping[str, int] = field(default_factory=dict)
    generated_at: datetime | None = None
    latencies: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(int(item["tokens"]) for item in self.token_ledger.values())

    @property
    def total_llm_calls(self) -> int:
        return sum(int(value) for value in self.model_calls.values())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "seed": self.seed,
            "stage_metrics": {key: dict(value) for key, value in self.stage_metrics.items()},
            "token_ledger": {key: dict(value) for key, value in self.token_ledger.items()},
            "model_calls": dict(self.model_calls),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "latencies": {key: dict(value) for key, value in self.latencies.items()},
        }


def stage_metric_rows(snapshot: HarnessSnapshot) -> Sequence[Mapping[str, Any]]:
    """把阶段度量摊平成报告可直接渲染的行。"""

    rows: list[Mapping[str, Any]] = []
    for stage in sorted(snapshot.stage_metrics):
        metric = snapshot.stage_metrics[stage]
        rows.append(
            {
                "stage": stage,
                "label": metric.get("label", ""),
                "elapsed_ms": metric.get("elapsed_ms", 0.0),
                "tokens": metric.get("tokens", 0),
                "llm_calls": metric.get("llm_calls", 0),
                "counters": dict(metric.get("counters", {})),
            }
        )
    return rows
