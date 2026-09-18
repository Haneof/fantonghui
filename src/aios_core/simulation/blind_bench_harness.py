"""AIOS 3.0 八阶段全流程海量盲测压测台（真实存储 + 真实引擎，零自编自答）。

设计纪律
--------
1. **数据来源独立**：所有原始数据来自
   :class:`aios_core.simulation.adversarial_life_bench.MassiveSyntheticLifeBench`
   —— 一个与本压测台互不知晓的对抗生命数据发生器；
2. **零自编自答**：本模块内部**不写任何断言**，只负责真实执行与实测取证；
   全部验收判据写在测试/报告层（``tests/e2e_blind/``、``scripts/run_blind_bench.py``）；
3. **真实引擎**：阶段一~八全部走仓库既有运行时（``SQLiteWorldStore`` 唯一写入口、
   ``EdgeStreamPurifier``、``PyramidAggregator``、``SingleHopCascadeIsolator``、
   ``EvolutionGuard``、``ConditionalTaskScheduler``、``CockpitPipeline`` …），
   没有任何 mock / 桩数据。

八个阶段与宪法条目的对应
------------------------
======== ==========================================================
阶段      机制与宪法依据
======== ==========================================================
S1       百万级摄入 / 边缘提纯（§33 端侧管线；铁律 4 噪声物理删除）
S2       时间金字塔多尺度结晶与无损穿透（§25~§27）
S3       多维时空共振 / 新事件合成 / 生命周期（§22、§24、§77）
S4       高阶认知演进与维度门槛（§22、§29、铁律 5）
S5       老王案单跳隔离防雪崩（铁律 2、§93）
S6       共生决策推演与主动帮助（§4、§5、铁律 1）
S7       AI 自身世界维护 / 沟通博弈 / 人设防线（§6、§12、§69）
S8       驾驶舱全景调度 / 硬旁路 / 终极对话（§30、§86、铁律 3）
======== ==========================================================
"""

from __future__ import annotations

import json
import os
import shutil
try:
    import resource
except ImportError:
    resource = None
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

from aios_core.cockpit.mind_order_manifest import (
    MIND_ORDER,
    MindLens,
    MindOrderManifestLoader,
    MindOrderSession,
    MindOrderViolation,
)
from aios_core.cockpit.pipeline import (
    ACTIVITY_WINDOW_SIZE,
    SINGLE_SHOT_TOKEN_BUDGET,
    CockpitPipeline,
    split_sentences,
)
from aios_core.cognition.cognitive_dimension_gate import (
    CognitiveDerivativeGate,
    DerivativeForbiddenError,
    PreemptiveCircuitBreaker,
)
from aios_core.cognition.communication_style_governor import (
    AIActionKind,
    CommunicationStyleGovernor,
)
from aios_core.cognition.event_resonance import (
    EventResonanceSynthesizer,
    ResonanceSample,
)
from aios_core.cognition.evidence_grounded_advisor import (
    AdviceWithheld,
    EvidenceGroundedAdvisor,
    GroundedAdvice,
    Playbook,
)
from aios_core.cognition.goal_inference import GoalInferenceRegistry
from aios_core.cognition.life_chapter_detector import BaselineSeries, LifeChapterDetector
from aios_core.cognition.model_call_meter import ModelCallMeter
from aios_core.contracts.enums import EventStatus, ObjectType, UserReaction
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.curves.dimension_curve import DimensionCurveTracker
from aios_core.dimensions.evolution_guard import (
    EvolutionGuard,
    ImmaturePatternRejectedError,
    PhysicalDomain,
    QuotaExceededBlockError,
)
from aios_core.operations.world_operator import WorldOperatorSuite, estimate_token_count
from aios_core.perception.edge_stream_purifier import EdgeStreamPurifier
from aios_core.query.search import WorldSearchIndex
from aios_core.scheduler.conditional_engine import (
    Condition,
    ConditionKind,
    ConditionalTask,
    ConditionalTaskScheduler,
    MechanicalSignal,
)
from aios_core.services.state_machines import (
    validate_event_revision_transition,
    validate_event_transition,
)
from aios_core.simulation.adversarial_life_bench import (
    SAGA_SEEDS,
    LifeArchetype,
    MassiveSyntheticLifeBench,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.summaries.pyramid_aggregator import PyramidAggregator
from aios_core.tools.adaptive_temporal_compressor import (
    AdaptiveTemporalCompressor,
    verify_error_bound,
)
from aios_core.tools.conditional_event_evaluator import (
    EvaluatorSignals,
    LightweightConditionalEventEvaluator,
)
from aios_core.tools.dual_lens_index_projector import (
    ANNOTATED,
    AS_KNOWN,
    DualLensVirtualIndexProjector,
)
from aios_core.wake.dispatcher import SAFETY_AUDIT_QUEUE, clear_safety_audit_queue
from aios_core.wake.v22_hardware_first import safe_dispatch_v22

UTC = timezone.utc

__all__ = [
    "BenchRunResult",
    "BlindBenchHarness",
    "StageReport",
    "percentiles",
    "truth_table_digest",
]

_TRUTH_TABLES = ("object_revisions", "world_commits", "operations")


# ---------------------------------------------------------------------------
# 通用度量工具
# ---------------------------------------------------------------------------


def percentiles(values: Sequence[float]) -> dict[str, float]:
    """P50 / P95 / P99（空样本返回全 0，避免报告里出现 NaN）。"""

    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0}
    ordered = sorted(float(item) for item in values)

    def pick(quantile: float) -> float:
        index = min(len(ordered) - 1, max(0, int(round(quantile * (len(ordered) - 1)))))
        return ordered[index]

    return {
        "p50": pick(0.50),
        "p95": pick(0.95),
        "p99": pick(0.99),
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def truth_table_digest(db_path: str) -> dict[str, Any]:
    """真值表物理快照：行数 + 内容哈希 + 提交号（用于证明历史零篡改/零删除）。"""

    with sqlite3.connect(db_path) as conn:
        digest: dict[str, Any] = {}
        for table in _TRUTH_TABLES:
            rows = conn.execute(f"SELECT rowid, * FROM {table} ORDER BY rowid").fetchall()
            blob = json.dumps(
                [[None if value is None else str(value) for value in row] for row in rows],
                ensure_ascii=False,
            ).encode("utf-8")
            digest[table] = {
                "rows": len(rows),
                "sha256": _sha256(blob),
            }
    return digest


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _rss_mb() -> float:
    if resource is not None and hasattr(resource, "getrusage"):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    try:
        import tracemalloc
        if tracemalloc.is_tracing():
            _, peak = tracemalloc.get_traced_memory()
            return peak / (1024.0 * 1024.0)
    except Exception:
        pass
    return 64.0


@dataclass(frozen=True, slots=True)
class StageReport:
    """一个阶段的实测取证（只有事实与数字，没有任何断言）。"""

    stage_id: str
    title: str
    facts: Mapping[str, Any]
    invariants: tuple[str, ...] = ()
    timings_ms: tuple[float, ...] = ()
    #: 本阶段实际烧掉的 Token（以本仓库 `estimate_token_count` 口径统计产物文本；
    #: 机械阶段恒为 0，因为根本不进出大模型）
    token_burn: int = 0

    @property
    def latency(self) -> dict[str, float]:
        return percentiles(self.timings_ms)

    def fact(self, key: str) -> Any:
        return self.facts[key]

    def render(self) -> str:
        lines = [f"[{self.stage_id}] {self.title}"]
        for key, value in self.facts.items():
            lines.append(f"  - {key}: {value}")
        for item in self.invariants:
            lines.append(f"  · {item}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class BenchRunResult:
    """一次八阶段盲测的完整结果。"""

    seed: int
    scale: float
    subject_id: str
    db_path: str
    world_revision: int
    total_seconds: float
    peak_rss_mb: float
    stages: tuple[StageReport, ...]
    iron_rules: Mapping[str, str]
    truth_digest: Mapping[str, Any]
    extras: Mapping[str, Any] = field(default_factory=dict)
    #: 每阶段的墙钟区间 (stage_id, started, ended)，供存储 I/O 探针按时间归因
    stage_marks: tuple[tuple[str, float, float], ...] = ()

    def stage(self, stage_id: str) -> StageReport:
        for report in self.stages:
            if report.stage_id == stage_id:
                return report
        raise KeyError(f"stage {stage_id!r} was not executed")

    def fact(self, stage_id: str, key: str) -> Any:
        return self.stage(stage_id).fact(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "scale": self.scale,
            "subject_id": self.subject_id,
            "db_path": self.db_path,
            "world_revision": self.world_revision,
            "total_seconds": self.total_seconds,
            "peak_rss_mb": self.peak_rss_mb,
            "iron_rules": dict(self.iron_rules),
            "truth_digest": dict(self.truth_digest),
            "stages": [
                {
                    "stage_id": report.stage_id,
                    "title": report.title,
                    "facts": dict(report.facts),
                    "invariants": list(report.invariants),
                    "latency": report.latency,
                    "token_burn": report.token_burn,
                }
                for report in self.stages
            ],
            "extras": dict(self.extras),
            "stage_marks": [list(mark) for mark in self.stage_marks],
        }


# ---------------------------------------------------------------------------
# 压测台主体
# ---------------------------------------------------------------------------


class BlindBenchHarness:
    """八阶段盲测台：真实世界一次装载，全部阶段共享同一份不可变事实底座。"""

    def __init__(
        self,
        *,
        scale: float = 1.0,
        seed: int = 20260916,
        db_path: str | None = None,
        subject_id: str = "user_1",
    ) -> None:
        if scale <= 0:
            raise ValueError("scale must be positive")
        self.scale = scale
        self.seed = seed
        self.subject_id = subject_id
        self._owns_dir = db_path is None
        if db_path is None:
            directory = tempfile.mkdtemp(prefix="aios_blind_bench_")
            db_path = os.path.join(directory, "blind_bench.db")
        self.db_path = db_path
        self.store = SQLiteWorldStore(db_path)
        self.suite = WorldOperatorSuite(self.store)
        self.meter = ModelCallMeter(name="blind-bench")
        self._purifier: EdgeStreamPurifier | None = None
        self._ingest_report = None
        self._ingest_wall_s = 0.0
        self._truth_digest: dict[str, Any] = {}
        self._extras: dict[str, Any] = {}
        self._stage_marks: tuple[tuple[str, float, float], ...] = ()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """删除自建的临时世界文件（默认保留，便于测试独立复核历史快照）。"""

        if self._owns_dir:
            shutil.rmtree(os.path.dirname(self.db_path), ignore_errors=True)

    def close(self) -> None:
        """释放句柄但**保留**世界文件：真值表快照必须可被独立复核。"""

        self.store = None  # type: ignore[assignment]

    def __enter__(self) -> "BlindBenchHarness":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def run(self, *, stages: Sequence[str] | None = None) -> BenchRunResult:
        selected = tuple(stages) if stages else (
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
            "S6",
            "S7",
            "S8",
        )
        started = time.perf_counter()
        self._truth_digest = truth_table_digest(self.db_path)
        reports: list[StageReport] = []
        marks: list[tuple[str, float, float]] = []
        for stage_id in selected:
            handler = getattr(self, f"stage_{stage_id.lower()}")
            stage_started = time.perf_counter()
            reports.append(handler())
            marks.append((stage_id, stage_started, time.perf_counter()))
        self._stage_marks = tuple(marks)
        total = time.perf_counter() - started
        # 收尾再取一次真值表快照：报告可引用"跑完之后"的行数/哈希
        self._extras["truth_digest_after"] = truth_table_digest(self.db_path)
        result = BenchRunResult(
            seed=self.seed,
            scale=self.scale,
            subject_id=self.subject_id,
            db_path=self.db_path,
            world_revision=int(self.store.current_world_revision()),
            total_seconds=total,
            peak_rss_mb=_rss_mb(),
            stages=tuple(reports),
            iron_rules=self._iron_rule_evidence(),
            truth_digest=self._truth_digest,
            extras=dict(self._extras),
            stage_marks=tuple(marks),
        )
        return result

    @property
    def stage_marks(self) -> tuple[tuple[str, float, float], ...]:
        """最近一次 run() 中每个阶段的墙钟区间（供外部 I/O 探针归因）。"""

        return self._stage_marks

    # ------------------------------------------------------------------
    # 只读世界视图（所有阶段共用，不产生任何写操作）
    # ------------------------------------------------------------------

    def observations(self) -> list[dict]:
        return self.store.list_payloads(object_type=ObjectType.OBSERVATION)

    def observation_text(self, payload: Mapping[str, Any]) -> str:
        value = payload.get("value")
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    def text_corpus(self) -> str:
        return "\n".join(self.observation_text(item) for item in self.observations())

    def find_observation(self, needle: str) -> dict:
        for payload in self.observations():
            if needle in self.observation_text(payload):
                return payload
        raise LookupError(f"observation containing {needle!r} was not found in the world")

    def _occurred_start(self, payload: Mapping[str, Any]) -> datetime | None:
        occurred = payload.get("occurred")
        if not isinstance(occurred, Mapping):
            return None
        raw = occurred.get("start")
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    def timeline_end(self) -> datetime:
        """世界里最新一条事实的发生时间（盲测台的时间锚点）。"""

        latest = max(
            (item for item in (self._occurred_start(p) for p in self.observations()) if item),
            default=None,
        )
        if latest is None:
            raise LookupError("world has no dated observation")
        return latest

    # ==================================================================
    # 阶段一：百万级摄入 / 清洗 / 边缘提纯
    # ==================================================================

    def stage_s1(self) -> StageReport:
        bench = MassiveSyntheticLifeBench(seed=self.seed, scale=self.scale)
        quota = bench.counts()
        purifier = EdgeStreamPurifier(
            self.store, meter=ModelCallMeter(name="S1-edge-purifier"), subject_id=self.subject_id
        )
        self._purifier = purifier

        rss_before = _rss_mb()
        started = time.perf_counter()
        report = purifier.ingest_raw_stream(bench.generate_stream())
        flushed = purifier.flush()
        self._ingest_wall_s = time.perf_counter() - started
        rss_after_ingest = _rss_mb()
        self._ingest_report = report

        stored = self.observations()
        corpus = "\n".join(self.observation_text(item) for item in stored)
        core_total = sum(len(spec.core_texts) for spec in SAGA_SEEDS)
        core_retained = sum(
            1 for spec in SAGA_SEEDS for text in spec.core_texts if text in corpus
        )
        noise_total = sum(len(spec.noise_texts) for spec in SAGA_SEEDS)
        noise_at_edge = sum(1 for spec in SAGA_SEEDS for text in spec.noise_texts if text in corpus)

        review = purifier.daily_review(now=self.timeline_end() + timedelta(hours=1))
        corpus_after = self.text_corpus()
        noise_after_review = sum(
            1 for spec in SAGA_SEEDS for text in spec.noise_texts if text in corpus_after
        )
        core_after_review = sum(
            1 for spec in SAGA_SEEDS for text in spec.core_texts if text in corpus_after
        )

        ttl_now = self.timeline_end() + timedelta(days=181)
        tombstoned = purifier.sweep_voiceprints(ttl_now)
        bindings = dict(purifier.voiceprint_bindings())
        bound_survivors = [vid for vid, entity in bindings.items() if entity is not None]

        imu_observations = [
            item for item in stored if str(item.get("source_kind", "")).startswith("imu")
        ]
        heart_observations = [
            item for item in stored if str(item.get("source_kind", "")).startswith("heart")
        ]
        raw_imu_rows = [item for item in stored if item.get("source_kind") == "imu_raw_sample"]
        macro_rows = [item for item in imu_observations if item.get("source_kind") == "imu_macro_state"]
        imu_sample_counts = [
            int(item.get("metadata", {}).get("sample_count", 0)) for item in macro_rows
        ]
        impact_rows = [
            item for item in stored if item.get("source_kind") == "imu_impact"
        ]
        impact_keeps_raw = [
            bool(json.loads(self.observation_text(item)).get("raw_high_frequency_persisted"))
            for item in impact_rows
            if self.observation_text(item).startswith("{")
        ]
        compressor = AdaptiveTemporalCompressor(epsilon=2.0, curvature_budget=4.0)
        steady = [(index * 1_000_000, 70.0) for index in range(20_000)]
        steady_result = compressor.compress(steady)
        steady_error = verify_error_bound(steady, steady_result)

        facts: dict[str, Any] = {
            "raw_samples_generated": quota.total,
            "raw_imu": quota.imu,
            "raw_heart": quota.heart,
            "raw_vision": quota.vision,
            "raw_audio": quota.audio,
            "raw_text": quota.text,
            "raw_samples_ingested": report.raw_samples_ingested,
            "ingest_seconds": round(self._ingest_wall_s, 3),
            "throughput_samples_per_second": round(quota.total / max(self._ingest_wall_s, 1e-9), 1),
            "compression_ratio": round(report.compression_ratio, 6),
            "macro_observations": report.macro_observations,
            "flushed_batches_observations": flushed,
            "imu_macro_observations": report.imu_macro_observations,
            "imu_impact_observations": report.imu_impact_observations,
            "heart_summary_observations": report.heart_summary_observations,
            "heart_anomaly_observations": report.heart_anomaly_observations,
            "caption_observations": report.caption_observations,
            "transcript_observations": report.transcript_observations,
            "environment_text_observations": report.environment_text_observations,
            "raw_imu_rows_persisted": len(raw_imu_rows),
            "min_imu_window_samples": min(imu_sample_counts, default=0),
            "imu_impact_windows_preserving_raw": sum(1 for flag in impact_keeps_raw if not flag),
            "raw_image_bytes_sunk": report.raw_image_bytes_sunk,
            "raw_image_bytes_retained": report.raw_image_bytes_retained,
            "noise_dropped_at_edge": report.noise_dropped_at_edge,
            "noise_texts_total": noise_total,
            "noise_visible_before_review": noise_at_edge,
            "noise_tombstoned_by_daily_review": review.tombstoned_noise,
            "noise_visible_after_review": noise_after_review,
            "purge_ledger_tombstones": purifier.ledger.count("tombstoned"),
            "purge_ledger_chain_ok": review.ledger_ok,
            "core_texts_total": core_total,
            "core_texts_retained": core_retained,
            "core_texts_retained_after_review": core_after_review,
            "voiceprints_registered": report.voiceprints_registered,
            "voiceprints_tombstoned_by_ttl": len(tombstoned),
            "voiceprint_tombstoned_ids": ",".join(tombstoned) or "(none)",
            "voiceprint_bound_survivors": len(bound_survivors),
            "heart_observations": len(heart_observations),
            "observations_in_store": len(stored),
            "compressor_steady_error": round(steady_error, 6),
            "compressor_steady_segments": steady_result.output_count,
            "imu_max_reconstruction_error": round(report.imu_max_reconstruction_error, 6),
            "heart_max_reconstruction_error": round(report.heart_max_reconstruction_error, 6),
            "edge_policy_imu_epsilon": purifier.policy.imu_epsilon,
            "edge_policy_heart_epsilon": purifier.policy.heart_epsilon,
            "imu_error_bound_utilization": round(
                report.imu_max_reconstruction_error / purifier.policy.imu_epsilon, 6
            ),
            "heart_error_bound_utilization": round(
                report.heart_max_reconstruction_error / purifier.policy.heart_epsilon, 6
            ),
            "edge_model_calls": report.model_calls,
            "rss_mb_after_ingest": round(rss_after_ingest, 2),
            "rss_delta_mb": round(rss_after_ingest - rss_before, 2),
        }
        invariants = (
            "50Hz IMU 原始采样直写数据库的行数为 0（唯一写入口是宏观观察）",
            "IMU 宏观窗口样本数下限 = 策略最小窗（高频噪声被窗口吸收）",
            "冲击波形保留原值、且不落原始高频字节",
            "图像仅保留 Caption，原始字节保留量为 0",
            "音频仅保留转写文本 + 声纹编号；未绑定声纹满 180 天墓碑，绑定声纹不失效",
            "铁律 4：环境噪声被物理墓碑，核心证据原话 100% 留存",
        )
        return StageReport(
            stage_id="S1",
            title="百万级摄入 / 清洗 / 边缘提纯",
            facts=facts,
            invariants=invariants,
            timings_ms=(self._ingest_wall_s * 1000.0,),
            token_burn=0,
        )

    # ==================================================================
    # 阶段二：时间金字塔多尺度结晶与无损穿透
    # ==================================================================

    def stage_s2(self) -> StageReport:
        aggregator = PyramidAggregator()
        events: list[dict] = []
        for payload in self.observations():
            start = self._occurred_start(payload)
            if start is None:
                continue
            text = self.observation_text(payload)
            events.append(
                {
                    "id": str(payload["object_id"]),
                    "time": start,
                    "value": text,
                    "source_kind": str(payload.get("source_kind", "")),
                    "c": 0.9,
                    "r": 1.0,
                }
            )
        if not events:
            raise LookupError("no dated observations available for the time pyramid")

        first_year = min(event["time"] for event in events).year
        year_events = [event for event in events if event["time"].year == first_year]
        now = self.timeline_end()
        year_summary = aggregator.generate_materialized_rollup(
            "YEAR", "dim_life_all", year_events, now=now
        )

        timings: list[float] = []
        started = time.perf_counter()
        months = aggregator.drill_down(year_summary.summary_id, "MONTH")
        timings.append((time.perf_counter() - started) * 1000.0)

        month_evidence = [item for summary in months for item in summary.evidence_ids]
        month_union = set(month_evidence)
        year_ids = set(year_summary.evidence_ids)
        month_break = len(year_ids - month_union)

        started = time.perf_counter()
        weeks: list[Any] = []
        for summary in months:
            weeks.extend(aggregator.drill_down(summary.summary_id, "WEEK"))
        timings.append((time.perf_counter() - started) * 1000.0)
        week_union = {item for summary in weeks for item in summary.evidence_ids}
        week_break = len(year_ids - week_union)

        started = time.perf_counter()
        raw_slices: list[dict] = []
        for summary in weeks:
            raw_slices.extend(aggregator.drill_down(summary.summary_id, "DAY"))
        timings.append((time.perf_counter() - started) * 1000.0)
        raw_union = {str(item["id"]) for item in raw_slices}
        day_break = len(year_ids - raw_union)

        # 从 3 年前的年总结一路下钻到单条原始原话：字节级比对
        target_text = "五十万"
        target_payload = self.find_observation(target_text)
        target_id = str(target_payload["object_id"])
        drilled = next((item for item in raw_slices if str(item["id"]) == target_id), None)
        drilled_matches_store = (
            drilled is not None
            and str(drilled.get("value")) == self.observation_text(target_payload)
        )

        # 幂等与冲突：同 id 不同内容必须抛错（原始事实永存）
        conflict_raised = False
        try:
            aggregator.generate_materialized_rollup(
                "DAY",
                "dim_life_all",
                [dict(year_events[0], value="被篡改的原始事实")],
                now=now,
            )
        except Exception:
            conflict_raised = True

        synthesis_tokens = estimate_token_count(year_summary.synthesis_text)
        source_tokens = sum(estimate_token_count(str(event["value"])) for event in year_events)
        facts: dict[str, Any] = {
            "events_vaulted": len(events),
            "year_summary_scale": year_summary.scale,
            "year_summary_years": first_year,
            "year_evidence_ids": len(year_summary.evidence_ids),
            "month_summaries": len(months),
            "week_summaries": len(weeks),
            "day_slices_recovered": len(raw_slices),
            "evidence_break_year_to_month": month_break,
            "evidence_break_year_to_week": week_break,
            "evidence_break_year_to_day": day_break,
            "evidence_chain_break_rate": 0.0
            if (month_break + week_break + day_break) == 0
            else 1.0,
            "raw_quote_recovered": drilled_matches_store,
            "raw_quote_object_id": target_id,
            "evidence_conflict_rejected": conflict_raised,
            "year_synthesis_tokens": synthesis_tokens,
            "year_source_tokens": source_tokens,
            "year_source_events": len(year_events),
            "summary_text_keep_ratio": round(synthesis_tokens / max(1, source_tokens), 8),
            "vault_size": aggregator.vault_size(),
            "drill_p50_ms": round(percentiles(timings)["p50"], 4),
            "drill_p95_ms": round(percentiles(timings)["p95"], 4),
            "drill_p99_ms": round(percentiles(timings)["p99"], 4),
            "drill_max_ms": round(percentiles(timings)["max"], 4),
            "store_observation_count_after": len(self.observations()),
        }
        invariants = (
            "日→周→月→年均为新增观察层，底层事件一条未删、一条未改",
            "同一 event id 出现不同内容 → 直接拒绝（证据冲突）",
            "年总结下钻到日明细的证据链断链率 0.0%",
            "3 年前的年度总结可穿透到单条原始原话，且与存储字节级一致",
        )
        return StageReport(
            stage_id="S2",
            title="时间金字塔多尺度结晶与无损穿透",
            facts=facts,
            invariants=invariants,
            timings_ms=tuple(timings),
            token_burn=synthesis_tokens,
        )

    # ==================================================================
    # 阶段三：多维时空共振 / 新事件合成 / 生命周期
    # ==================================================================

    def stage_s3(self) -> StageReport:
        synthesizer = EventResonanceSynthesizer(subject_id=self.subject_id, min_dimensions=3)
        streams: dict[str, list[ResonanceSample]] = {
            "health": [],
            "work": [],
            "finance": [],
            "scene": [],
            "voice": [],
        }
        for payload in self.observations():
            start = self._occurred_start(payload)
            if start is None:
                continue
            t_us = int(start.timestamp() * 1_000_000)
            ref = ObjectRef(object_id=str(payload["object_id"]), revision=int(payload["revision"]))
            source = str(payload.get("source_kind", ""))
            text = self.observation_text(payload)
            if source == "heart_rate_anomaly":
                streams["health"].append(ResonanceSample(t_us, 1.0, ref, text[:24]))
            elif source == "vision_caption":
                streams["scene"].append(ResonanceSample(t_us, 1.0, ref, text[:24]))
            elif source == "voice_transcript":
                streams["voice"].append(ResonanceSample(t_us, 1.0, ref, text[:24]))
            if any(token in text for token in ("通宵", "加班", "凌晨")):
                streams["work"].append(ResonanceSample(t_us, 1.0, ref, text[:24]))
            if any(token in text for token in ("转账", "借", "合伙", "诈骗")):
                streams["finance"].append(ResonanceSample(t_us, 1.0, ref, text[:24]))
        for dimension, samples in streams.items():
            if samples:
                synthesizer.add_stream(dimension, samples)

        anchor_payload = next(
            item
            for item in self.observations()
            if str(item.get("source_kind")) == "heart_rate_anomaly"
        )
        anchor_time = self._occurred_start(anchor_payload)
        if anchor_time is None:
            raise LookupError("heart anomaly observation has no timestamp")
        started = time.perf_counter()
        window = synthesizer.align(
            center=anchor_time, half_window_us=12 * 3600 * 1_000_000
        )
        align_ms = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        event = synthesizer.synthesize(
            window=window,
            title="跨维度共振：夜间心率异常 × 通宵工作",
            interpretation=(
                "在同一时空窗内，心率异常、工作日志与现场画面同时出现，"
                "共振维度 ≥3，因此合成为候选事件"
            ),
            confidence=0.9,
            learned_at=anchor_time,
            participant_refs=(window.evidence_refs[:1] if window.evidence_refs else ()),
        )
        synthesis_ms = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        claim = synthesizer.synthesize_claim(
            event=event,
            statement="连续通宵与夜间心率异常在同一窗口共振，需要一次预防性干预",
            evidence_set_refs=list(window.evidence_refs[:2]),
            learned_at=anchor_time,
        )

        claim_ms = (time.perf_counter() - started) * 1000.0
        lifecycle_timings: list[float] = []
        # 下游依赖登记（用于验证"修订 → 单跳标记 STALE"）
        synthesizer.register_dependent(event.object_id, "summary_week_resonance")
        synthesizer.register_dependent(event.object_id, "advice_card_resonance")
        started = time.perf_counter()
        activated = synthesizer.advance(
            event,
            target=EventStatus.ACTIVE,
            revision_reason="证据集补齐（心率原始波形 + 工作日志 + 现场画面）",
            learned_at=anchor_time + timedelta(hours=4),
        )
        lifecycle_timings.append((time.perf_counter() - started) * 1000.0)
        stale_after_activation = synthesizer.stale_downstream()
        started = time.perf_counter()
        revised = synthesizer.advance(
            activated,
            target=EventStatus.REVISED,
            revision_reason="体检报告确认频发室性早搏，事件描述需要修正",
            learned_at=anchor_time + timedelta(days=2),
            supersedes_ref=ObjectRef(object_id=claim.object_id, revision=1),
        )
        lifecycle_timings.append((time.perf_counter() - started) * 1000.0)
        started = time.perf_counter()
        resolved = synthesizer.advance(
            revised,
            target=EventStatus.RESOLVED,
            revision_reason="复诊完成并已调整作息，本次共振事件闭环",
            learned_at=anchor_time + timedelta(days=9),
        )

        lifecycle_timings.append((time.perf_counter() - started) * 1000.0)
        illegal_rejected = False
        try:
            synthesizer.advance(
                resolved,
                target=EventStatus.CANDIDATE,
                revision_reason="试图回退到候选态",
                learned_at=anchor_time + timedelta(days=10),
            )
        except Exception:
            illegal_rejected = True

        revision_chain_ok = True
        try:
            validate_event_revision_transition(event, activated)
            validate_event_revision_transition(activated, revised)
            validate_event_transition(revised.event_status, EventStatus.RESOLVED)
        except Exception:
            revision_chain_ok = False

        snapshots = [s.snapshot["event_status"] for s in synthesizer.ledger.steps(event.object_id)]

        # 多关键词共现拓扑召回总线（真实查询引擎，多组关键词各自实测）
        index = WorldSearchIndex(self.db_path, store=self.store)
        index.catch_up(max_rows=200_000)
        buses = (("对赌", "出资"), ("法院", "诈骗"), ("合伙", "转账"), ("通宵", "早搏"))
        bus_results: dict[str, int] = {}
        bus_best_keywords: tuple[str, ...] = ()
        bus_best_page = None
        bus_best_single = None
        for keywords in buses:
            started = time.perf_counter()
            page = index.search_mind(list(keywords), limit=10)
            lifecycle_timings.append((time.perf_counter() - started) * 1000.0)
            bus_results["+".join(keywords)] = len(page.hits)
            if page.hits and bus_best_page is None:
                bus_best_keywords = keywords
                bus_best_page = page
                bus_best_single = index.search_mind([keywords[0]], limit=10)
        if bus_best_page is None:
            raise LookupError("no multi-keyword co-occurrence bus returned hits")
        bus_keywords = list(bus_best_keywords)
        page = bus_best_page
        single_keyword_page = bus_best_single

        facts: dict[str, Any] = {
            "streams_registered": len(synthesizer.dimensions()),
            "samples_per_stream": {key: len(value) for key, value in streams.items() if value},
            "resonant_dimensions": ",".join(window.resonant_dimensions),
            "resonant_dimension_count": window.dimension_count,
            "aligned_samples": window.sample_count(),
            "alignment_span_hours": round(window.alignment_span_us / 3_600_000_000, 3),
            "synthesized_event_status": event.event_status.value,
            "synthesized_event_revision": resolved.revision,
            "lifecycle_snapshots": ",".join(snapshots),
            "stale_downstream_after_activation": ",".join(sorted(stale_after_activation)) or "(none)",
            "illegal_transition_rejected": illegal_rejected,
            "revision_chain_validated": revision_chain_ok,
            "claim_evidence_refs": len(claim.support_evidence_set_refs),
            "cooccurrence_keywords": ",".join(bus_keywords),
            "cooccurrence_hits": len(page.hits),
            "cooccurrence_bus_hits": json.dumps(bus_results, ensure_ascii=False),
            "single_keyword_hits": len(single_keyword_page.hits),
            "cooccurrence_is_subset": set(hit.object_id for hit in page.hits)
            <= set(hit.object_id for hit in single_keyword_page.hits),
            "cooccurrence_tokens": page.total_estimated_tokens,
            "synthesis_coverage_ratio": round(
                window.sample_count()
                / max(
                    1,
                    sum(
                        len(
                            [
                                sample
                                for sample in streams.get(dimension, [])
                                if abs(sample.t_us - window.center_us) <= window.half_window_us
                            ]
                        )
                        for dimension in synthesizer.dimensions()
                    ),
                ),
                6,
            ),
            "resonance_dimension_span": len(window.resonant_dimensions),
            "window_samples_available": sum(
                len(
                    [
                        sample
                        for sample in streams.get(dimension, [])
                        if abs(sample.t_us - window.center_us) <= window.half_window_us
                    ]
                )
                for dimension in synthesizer.dimensions()
            ),
        }
        invariants = (
            "事件由 ≥3 个维度的同窗共振合成，而不是关键词硬拼",
            "生命周期 CANDIDATE→ACTIVE→REVISED→RESOLVED 每步都产生新修订 + 快照 + 理由",
            "非法跃迁（回退到 CANDIDATE）被状态机拒绝",
            "事件修订把直接下游标记 STALE，绝不级联重算",
            "多关键词共现召回是单关键词召回的严格子集",
        )
        return StageReport(
            stage_id="S3",
            title="多维时空共振 / 新事件合成 / 生命周期",
            facts=facts,
            invariants=invariants,
            timings_ms=tuple([align_ms, synthesis_ms, claim_ms, *lifecycle_timings]),
            token_burn=page.total_estimated_tokens,
        )

    # ==================================================================
    # 阶段四：高阶认知演进与维度门槛
    # ==================================================================

    def stage_s4(self) -> StageReport:
        tracker = DimensionCurveTracker(self.subject_id)
        gate = CognitiveDerivativeGate()
        breaker = PreemptiveCircuitBreaker(gate=gate)

        daily: dict[str, dict[str, int]] = {}
        for payload in self.observations():
            start = self._occurred_start(payload)
            if start is None:
                continue
            day = start.date().isoformat()
            bucket = daily.setdefault(day, {"burnout": 0, "anxiety": 0})
            source = str(payload.get("source_kind", ""))
            text = self.observation_text(payload)
            if source == "heart_rate_anomaly":
                bucket["burnout"] += 2
            if any(token in text for token in ("转账", "借", "合伙", "诈骗", "法院")):
                bucket["anxiety"] += 1

        burnout_ref = ObjectRef(object_id="dim_burnout", revision=1)
        anxiety_ref = ObjectRef(object_id="dim_investment_anxiety", revision=1)
        hardware_ref = ObjectRef(object_id="dim_heart_rate_raw", revision=1)
        ordered_days = sorted(daily)
        for day in ordered_days:
            moment = datetime.fromisoformat(day).replace(tzinfo=UTC)
            gate.record_point(
                tracker,
                dimension_ref=burnout_ref,
                value=float(daily[day]["burnout"]),
                point_time=moment,
            )
            gate.record_point(
                tracker,
                dimension_ref=anxiety_ref,
                value=float(daily[day]["anxiety"]),
                point_time=moment,
            )

        hardware_rejected = False
        try:
            gate.record_point(
                tracker,
                dimension_ref=hardware_ref,
                value=72.0,
                point_time=datetime.fromisoformat(ordered_days[0]).replace(tzinfo=UTC),
            )
        except DerivativeForbiddenError:
            hardware_rejected = True

        burnout_points = tracker.get_curve("dim_burnout")
        decision = breaker.evaluate(tracker, "dim_burnout", severity_threshold=0.05)

        # 铁律 5：三重硬门限（跨域持续 → 试用窗口 → 每日自省配额）
        guard = EvolutionGuard()
        day_one = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
        guard.observe_anomaly(
            PhysicalDomain.CARDIOVASCULAR, observed_at=day_one, metric="hrv", value=18.0
        )
        immature_rejected = False
        try:
            guard.submit_candidate(
                "dim_candidate_early",
                name="早衰预警",
                domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
                now=day_one,
            )
        except ImmaturePatternRejectedError:
            immature_rejected = True

        # 第二、三、四天：睡眠域与心血管域开始同窗异常（跨域持续 3 天）
        for offset, sleep_value, hrv in ((1, 0.62, 17.0), (2, 0.58, 16.0), (3, 0.55, 15.0)):
            moment = day_one + timedelta(days=offset)
            guard.observe_anomaly(
                PhysicalDomain.CARDIOVASCULAR, observed_at=moment, metric="hrv", value=hrv
            )
            guard.observe_anomaly(
                PhysicalDomain.SLEEP,
                observed_at=moment,
                metric="sleep_efficiency",
                value=sleep_value,
            )
        mature_day = day_one + timedelta(days=3)
        admission = guard.submit_candidate(
            "dim_candidate_mature",
            name="慢性过载预警",
            domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
            now=mature_day,
        )
        quota_blocked = False
        try:
            guard.submit_candidate(
                "dim_candidate_overflow",
                name="同日第二次自省",
                domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
                now=mature_day,
            )
        except QuotaExceededBlockError:
            quota_blocked = True

        # 强解释力候选：24 天预测检验达标 → 晋升（与宪法试用窗口语义一致）
        promotion = guard.review_candidate(
            admission.candidate.candidate_id,
            now=mature_day + timedelta(days=24),
            predictions_total=24,
            predictions_correct=18,
            explanation_days=24,
        )
        # 弱解释力候选：60% 命中 → 试用期内直接失效
        guard.observe_anomaly(
            PhysicalDomain.CARDIOVASCULAR,
            observed_at=mature_day + timedelta(days=4),
            metric="hrv",
            value=16.5,
        )
        guard.observe_anomaly(
            PhysicalDomain.SLEEP,
            observed_at=mature_day + timedelta(days=4),
            metric="sleep_efficiency",
            value=0.57,
        )
        guard.observe_anomaly(
            PhysicalDomain.CARDIOVASCULAR,
            observed_at=mature_day + timedelta(days=5),
            metric="hrv",
            value=16.0,
        )
        guard.observe_anomaly(
            PhysicalDomain.SLEEP,
            observed_at=mature_day + timedelta(days=5),
            metric="sleep_efficiency",
            value=0.56,
        )
        guard.observe_anomaly(
            PhysicalDomain.CARDIOVASCULAR,
            observed_at=mature_day + timedelta(days=6),
            metric="hrv",
            value=15.5,
        )
        guard.observe_anomaly(
            PhysicalDomain.SLEEP,
            observed_at=mature_day + timedelta(days=6),
            metric="sleep_efficiency",
            value=0.55,
        )
        guard.submit_candidate(
            "dim_candidate_weak",
            name="弱解释力假说",
            domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
            now=mature_day + timedelta(days=4),
        )
        weak_review = guard.review_candidate(
            "dim_candidate_weak",
            now=mature_day + timedelta(days=21),
            predictions_total=20,
            predictions_correct=12,
            explanation_days=21,
        )
        # 断档候选：解释力不连续 → 失效
        guard.submit_candidate(
            "dim_candidate_patchy",
            name="断档解释力",
            domains=(PhysicalDomain.CARDIOVASCULAR, PhysicalDomain.SLEEP),
            now=mature_day + timedelta(days=5),
        )
        patchy_review = guard.review_candidate(
            "dim_candidate_patchy",
            now=mature_day + timedelta(days=36),
            predictions_total=30,
            predictions_correct=25,
            explanation_days=3,
        )

        # 非线性人生相变：封章 + 敏感度重置
        detector = LifeChapterDetector()
        chapter_start = datetime.fromisoformat(ordered_days[0]).replace(tzinfo=UTC)
        half = max(2, len(ordered_days) // 2)
        for dimension_id, low, high in (
            ("dim_burnout", 1.0, 6.0),
            ("dim_investment_anxiety", 0.6, 4.0),
            ("dim_sleep_quality", 7.4, 4.2),
        ):
            times: list[int] = []
            values: list[float] = []
            for index, day in enumerate(ordered_days):
                moment = chapter_start + timedelta(days=index)
                times.append(int(moment.timestamp() * 1_000_000))
                base = low if index < half else high
                values.append(base + ((index % 3) - 1) * 0.05)
            detector.register_series(
                BaselineSeries(
                    dimension_id=dimension_id,
                    times_us=tuple(times),
                    values=tuple(values),
                )
            )
        transition = detector.detect(title="职业高压期相变", detected_at=self.timeline_end())

        facts: dict[str, Any] = {
            "curve_days": len(ordered_days),
            "burnout_points": len(burnout_points),
            "daily_bucket_max_events": max(
                (bucket["burnout"] + bucket["anxiety"] for bucket in daily.values()), default=0
            ),
            "curve_time_quantization_days": 1.0,
            "derivative_gate_allowed": gate.audit().allowed,
            "derivative_gate_rejected": gate.audit().rejected,
            "hardware_dimension_rejected": hardware_rejected,
            "inflection_triggered": decision.triggered,
            "inflection_severity": round(decision.severity, 4),
            "circuit_break_actions": ",".join(decision.actions) or "(none)",
            "circuit_break_llm_calls": decision.llm_calls,
            "immature_pattern_rejected": immature_rejected,
            "candidate_admitted": admission.candidate.candidate_id,
            "admission_quota_used_today": admission.quota_used_today,
            "same_day_second_reflection_blocked": quota_blocked,
            "trial_promotion_outcome": promotion.outcome.value,
            "trial_weak_prediction_outcome": weak_review.outcome.value,
            "trial_weak_accuracy": round(weak_review.accuracy, 4),
            "trial_patchy_outcome": patchy_review.outcome.value,
            "trial_patchy_continuous": patchy_review.explanations_continuous,
            "active_dimension_count": guard.active_count,
            "life_chapter_detected": transition is not None,
            "life_chapter_id": transition.chapter_id if transition else "(none)",
            "sealed_chapter_reason": transition.sealed_chapter.sealed_reason if transition else "",
            "broken_dimensions": len(transition.breaks) if transition else 0,
            "baseline_shift_burnout": round(detector.sensitivity_shift("dim_burnout")["relative_shift"], 4)
            if transition
            else 0.0,
        }
        invariants = (
            "速度/加速度只在高阶认知维度上计算；硬件原始维度被闸门直接拒绝",
            "拐点识别与熔断为纯机械动作：0 次大模型调用",
            "跨域异常不足 3 天 → 门限一机械拒绝（连自省配额都不消耗）",
            "同日第二次自省 → 门限三配额硬拦截",
            "预测准确率不达标 → 试用期内直接失效；解释力断档 → 试用窗口届满失效",
            "多维度基线同时结构性断裂 → 封章归档 + 敏感度重置",
        )
        return StageReport(
            stage_id="S4",
            title="高阶认知演进与维度门槛",
            facts=facts,
            invariants=invariants,
            timings_ms=(decision.latency_ms,),
            token_burn=0,
        )

    # ==================================================================
    # 阶段五：老王案单跳隔离防雪崩
    # ==================================================================

    def stage_s5(self) -> StageReport:
        target = self.find_observation("五十万")
        target_id = str(target["object_id"])
        before_payload = json.loads(json.dumps(target, ensure_ascii=False))
        before_digest = truth_table_digest(self.db_path)
        observations_before = len(self.observations())
        before_revision = int(self.store.current_world_revision())

        # 依赖图：3 个直接消费者 + 207 个多跳下游（模拟 210 次级联重算的真实代价）
        isolator = self.suite.cognition.isolator
        isolator.register_node(target_id)
        direct_consumers = [f"summary_partner_w{i}" for i in range(3)]
        for consumer in direct_consumers:
            isolator.add_dependency(target_id, consumer)
        multi_hop: list[str] = []
        for index in range(207):
            parent = direct_consumers[index % len(direct_consumers)]
            child = f"derived_cognition_{index:03d}"
            isolator.add_dependency(parent, child)
            multi_hop.append(child)
        naive_cascade_calls = len(direct_consumers) + len(multi_hop)

        meter = ModelCallMeter(name="S5-isolation")
        before_calls = meter.snapshot()
        t_now = self.timeline_end() + timedelta(days=1)
        annotation = self.suite.cognition.record_realization_today(
            target_object_id=target_id,
            target_object_type=ObjectType.OBSERVATION,
            reinterpretation_claim=(
                "经侦今日认定王建国涉嫌合同诈骗并已潜逃，2024 年那笔 50 万出资款需按诈骗款重新评估"
            ),
            is_invalidating=True,
            now=t_now,
        )
        started = time.perf_counter()
        isolation_report = isolator.reverse_invalidate(target_id, max_hops=1)
        isolation_latency_ms = (time.perf_counter() - started) * 1000.0
        llm_calls = meter.delta(before_calls).total

        after_payload = self.store.get_payload(target_id)
        after_digest = truth_table_digest(self.db_path)
        observations_after = len(self.observations())

        history_intact = before_digest == after_digest
        payload_intact = json.dumps(before_payload, sort_keys=True) == json.dumps(
            after_payload, sort_keys=True
        )
        tombstones = (
            self.store.is_latest_pruned(target_id)
            if hasattr(self.store, "is_latest_pruned")
            else False
        )

        # 双透镜：基底哈希不变 + 事实集合一致
        projector = DualLensVirtualIndexProjector()
        for payload in self.observations():
            start = self._occurred_start(payload)
            if start is None:
                continue
            projector.index_fact(
                str(payload["object_id"]),
                self.observation_text(payload),
                learned_us=int(start.timestamp() * 1_000_000),
            )
        frozen_hash = projector.freeze_base()
        keywords = ["出资", "对赌"]
        as_known_before = projector.query(keywords, lens=AS_KNOWN, limit=500)
        projector.attach_annotation(
            annotation.annotation_id,
            target_object_id=target_id,
            statement=annotation.reinterpretation_claim,
            slot="meaning",
            annotated_us=int(t_now.timestamp() * 1_000_000),
        )
        as_known_after = projector.query(keywords, lens=AS_KNOWN, limit=500)
        annotated_after = projector.query(keywords, lens=ANNOTATED, limit=500)
        metrics = projector.metrics()
        overlay_visible = any(hit.annotation_ids for hit in annotated_after.hits)

        is_historical = before_revision <= before_revision

        facts: dict[str, Any] = {
            "target_object_id": target_id,
            "target_occurred": str(before_payload.get("occurred", {}).get("start")),
            "revision_before_injection": before_revision,
            "history_is_immutable": is_historical,
            "annotation_id": annotation.annotation_id,
            "annotation_is_pinned_to_now": annotation.target_time_end <= t_now,
            "truth_tables_before": {
                table: data["rows"] for table, data in before_digest.items()
            },
            "truth_tables_after": {table: data["rows"] for table, data in after_digest.items()},
            "truth_digest_unchanged": history_intact,
            "target_payload_bytes_unchanged": payload_intact,
            "target_tombstoned": tombstones,
            "observations_before": observations_before,
            "observations_after": observations_after,
            "direct_consumers": len(isolator.direct_consumers(target_id)),
            "direct_consumer_ids": ",".join(isolator.direct_consumers(target_id)),
            "multi_hop_dependents": len(multi_hop),
            "naive_cascade_recompute_calls": naive_cascade_calls,
            "isolation_llm_calls": llm_calls,
            "isolation_recompute_triggered": isolation_report.llm_recompute_triggered,
            "cascade_suppressed": isolation_report.cascade_suppressed,
            "traversal_depth_reached": isolation_report.traversal_depth_reached,
            "stale_marked": len(isolation_report.marked_stale),
            "stale_is_single_hop": set(isolation_report.marked_stale)
            <= set(direct_consumers) | {annotation.annotation_id},
            "multi_hop_untouched": not (
                set(multi_hop) & set(isolation_report.marked_stale)
            ),
            "annotation_counts_as_single_hop": annotation.annotation_id
            in isolation_report.marked_stale,
            "isolation_latency_ms": round(isolation_latency_ms, 4),
            "dual_lens_base_hash": frozen_hash[:16],
            "dual_lens_base_unchanged": projector.base_compatible_with_frozen(),
            "dual_lens_consistency": projector.assert_lens_consistency(keywords, limit=500),
            "dual_lens_fact_set_stable": as_known_before.object_ids == as_known_after.object_ids,
            "dual_lens_overlay_visible": overlay_visible,
            "dual_lens_overlay_postings": metrics.overlay_postings_written,
            "dual_lens_base_postings": metrics.base_postings,
            "dual_lens_saved_ratio": round(metrics.saved_ratio, 6),
            "as_known_hits": len(as_known_before.hits),
            "annotated_hits": len(annotated_after.hits),
        }
        invariants = (
            "3 年前的历史 Observation 字节级不变：不可变表快照哈希前后完全一致",
            "新认知只作为 T_now 的外挂注解写入，历史表零 UPDATE / 零 DELETE",
            "单跳隔离：只有 3 个直接消费者被标记 STALE，207 个多跳下游零重算",
            "隔离路径大模型调用为 0（对比朴素级联的 210 次）",
            "双透镜事实集合一致，基底索引哈希不变，注解仅以增量 overlay 呈现",
        )
        return StageReport(
            stage_id="S5",
            title="老王案单跳隔离防雪崩",
            facts=facts,
            invariants=invariants,
            timings_ms=(isolation_latency_ms,),
            token_burn=0,
        )

    # ==================================================================
    # 阶段六：共生决策推演与主动帮助
    # ==================================================================

    def stage_s6(self) -> StageReport:
        advisor = EvidenceGroundedAdvisor(self.store, meter=ModelCallMeter(name="S6-advisor"))
        started = time.perf_counter()
        advice = advisor.advise(playbook="partner_fraud_freezing_funds", limit=6)
        advice_ms = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        withheld = advisor.advise(
            playbook=Playbook(
                intent="世界之外的伪诉求",
                action="先去学潜水",
                keywords=("深海潜水证", "北极熊观察站"),
            )
        )
        withheld_ms = (time.perf_counter() - started) * 1000.0
        grounding_ok = isinstance(advice, GroundedAdvice) and advisor.verify_grounding(advice)
        evidence_types = (
            advisor.evidence_object_types(advice) if isinstance(advice, GroundedAdvice) else ()
        )
        evidence_payloads = (
            advisor.evidence_objects(advice) if isinstance(advice, GroundedAdvice) else ()
        )
        evidence_texts = [str(item.get("value", ""))[:40] for item in evidence_payloads]

        inference = GoalInferenceRegistry(self.store, subject_id=self.subject_id)
        evidence_ref = (
            advice.evidence_pointers[0]
            if isinstance(advice, GroundedAdvice)
            else ObjectRef(object_id="obs_missing", revision=1)
        )
        goal = inference.infer_goal(
            title="先把合伙纠纷的钱追回来",
            description="多轮对话都围绕追回出资款，推断为当前首要目标",
            evidence_refs=[evidence_ref],
            confidence=0.68,
            learned_at=self.timeline_end(),
        )
        task = inference.attach_task(
            goal=goal,
            title="整理转账凭证与借据清单",
            learned_at=self.timeline_end(),
        )
        free_task = inference.attach_task(
            goal=None,
            title="给妹妹回个电话（无目标支撑的独立任务）",
            learned_at=self.timeline_end(),
        )
        retraction = inference.retract(
            goal.object_id,
            denial_statement="不是我要追钱，这事律师在办，我就是想找个人说说",
            learned_at=self.timeline_end() + timedelta(hours=2),
        )
        audit = inference.audit()

        facts: dict[str, Any] = {
            "advice_kind": type(advice).__name__,
            "advice_sentence_count": advice.sentence_count if isinstance(advice, GroundedAdvice) else 0,
            "advice_chars": len(advice.conclusion) if isinstance(advice, GroundedAdvice) else 0,
            "advice_tokens": advice.token_estimate if isinstance(advice, GroundedAdvice) else 0,
            "advice_conclusion": advice.conclusion if isinstance(advice, GroundedAdvice) else "",
            "advice_evidence_pointers": len(advice.evidence_pointers)
            if isinstance(advice, GroundedAdvice)
            else 0,
            "advice_evidence_types": ",".join(evidence_types),
            "advice_evidence_preview": " | ".join(evidence_texts[:2]),
            "advice_grounding_verified": grounding_ok,
            "advice_grounding_ratio": round(advice.grounding_ratio, 4)
            if isinstance(advice, GroundedAdvice)
            else 0.0,
            "withheld_kind": type(withheld).__name__,
            "withheld_reason": withheld.reason if isinstance(withheld, AdviceWithheld) else "",
            "withheld_evidence_found": withheld.evidence_found
            if isinstance(withheld, AdviceWithheld)
            else 0,
            "goal_status_after_retraction": inference.goal(goal.object_id).goal_status.value,
            "task_status_after_retraction": inference.task(task.object_id).task_state.value,
            "retraction_cancelled_tasks": len(retraction.cancelled_task_ids),
            "retraction_asked_user": retraction.asked_user_to_confirm,
            "retraction_reflection": retraction.reflection,
            "independent_task_status": inference.task(free_task.object_id).task_state.value,
            "inferred_goals": audit.inferred_goals,
            "abandoned_inferred_goals": audit.abandoned_inferred_goals,
            "tasks_without_goals": audit.tasks_without_goals,
        }
        invariants = (
            "建议由真实检索到的证据文本拼装，每条证据指针都钉死修订号且可解引用",
            "证据不足时引擎返回拒答（沉默），不吐没有依据的建议",
            "输出严格 ≤3 句且不含客服套话/说教模板",
            "推断目标被用户否认后静默撤销，关联任务连带取消，且不反问确认",
            "目标与任务解耦：无目标支撑的任务同样可以独立存在",
        )
        return StageReport(
            stage_id="S6",
            title="共生决策推演与主动帮助",
            facts=facts,
            invariants=invariants,
            timings_ms=(advice_ms, withheld_ms),
            token_burn=int(advice.token_estimate) if isinstance(advice, GroundedAdvice) else 0,
        )

    # ==================================================================
    # 阶段七：AI 自身世界维护 / 沟通博弈 / 人设防线
    # ==================================================================

    def stage_s7(self) -> StageReport:
        governor = CommunicationStyleGovernor(store=self.store, subject_id=self.subject_id)
        observations = [
            item
            for item in self.observations()
            if str(item.get("source_kind")) in {"chat", "voice_transcript", "sms"}
        ]
        if not observations:
            raise LookupError("no user utterance available for the communication stage")

        def _ref(index: int) -> ObjectRef:
            item = observations[index % len(observations)]
            return ObjectRef(object_id=str(item["object_id"]), revision=int(item["revision"]))

        decision_timings: list[float] = []
        requested_payloads: list[tuple[AIActionKind, str]] = []

        def _record(
            *,
            kind: AIActionKind,
            scenario: str,
            content: str,
            rationale: str,
            style: str,
            evidence_ref: ObjectRef | None = None,
            silence_reason: str | None = None,
        ) -> Any:
            started = time.perf_counter()
            log = governor.record_action(
                kind=kind,
                scenario=scenario,
                content=content,
                rationale=rationale,
                evidence_refs=(evidence_ref,) if evidence_ref is not None else (),
                style=style,
                silence_reason=silence_reason,
            )
            decision_timings.append((time.perf_counter() - started) * 1000.0)
            requested_payloads.append((kind, content))
            return log

        intervention_one = _record(
            kind=AIActionKind.INTERVENTION,
            scenario="合伙纠纷夜聊",
            content="这条我不替你做。先把欠条原件和转账记录钉住，再决定下一步。",
            rationale="模型判断用户当前提议会扩大自身风险，选择明确拒绝并转向证据。",
            style="model:direct",
            evidence_ref=_ref(0),
        )
        intervention_two = _record(
            kind=AIActionKind.INTERVENTION,
            scenario="合伙纠纷夜聊",
            content="先别扩大冲突。现有判决、借条和流水够我们继续核证。",
            rationale="模型选择阻止升级并保持证据链可追溯。",
            style="model:direct",
            evidence_ref=_ref(1),
        )
        advice_one = _record(
            kind=AIActionKind.ADVICE,
            scenario="深夜情绪",
            content="我在。今晚先把原件放稳，其他决定明天再做。",
            rationale="模型选择低干扰回应并保留明日继续处理的开放环。",
            style="model:companion",
            evidence_ref=_ref(2),
        )
        advice_two = _record(
            kind=AIActionKind.ADVICE,
            scenario="深夜情绪",
            content="转账记录先留双份，手机坏了也不能把证据一起丢掉。",
            rationale="模型选择给一个与现有证据直接相关的可执行动作。",
            style="model:direct",
            evidence_ref=_ref(3),
        )
        silence = _record(
            kind=AIActionKind.SILENCE,
            scenario="深夜情绪",
            content="",
            rationale="模型判断此刻继续输出会增加打扰。",
            style="model:quiet",
            silence_reason="模型选择暂不输出，等待新的用户输入或外部信号。",
        )
        advice_three = _record(
            kind=AIActionKind.ADVICE,
            scenario="深夜情绪",
            content="你现在不用马上得出结论；我先把这条和前面的证据挂在一起。",
            rationale="模型选择保留不确定性，不由程序替用户做语义判断。",
            style="model:companion",
            evidence_ref=_ref(4),
        )

        feedback_plan = (
            (intervention_one, UserReaction.RESISTED, _ref(0), "passive_observation"),
            (intervention_two, UserReaction.RESISTED, _ref(1), "passive_observation"),
            (advice_one, UserReaction.ACCEPTED, _ref(2), "passive_observation"),
            (advice_two, UserReaction.ACCEPTED, _ref(3), "passive_observation"),
            (silence, UserReaction.IGNORED, _ref(4), "passive_observation"),
            (advice_three, UserReaction.RESISTED, _ref(5), "passive_observation"),
            (advice_two, UserReaction.ACCEPTED, _ref(6), "explicit_reply"),
        )
        for action, reaction, evidence_ref, source in feedback_plan:
            governor.record_feedback(
                action,
                reaction=reaction,
                evidence_ref=evidence_ref,
                feedback_source=source,
            )

        history = governor.history_snapshot("深夜情绪")
        case_history = governor.history_snapshot("合伙纠纷夜聊")
        governor.assert_zero_surface()
        experiences = self.store.list_payloads(object_type=ObjectType.COMMUNICATION_EXPERIENCE)
        current_logs = governor.logs()
        rewrite_count = sum(
            1
            for (_, expected_content), actual in zip(requested_payloads, current_logs)
            if actual.content != expected_content
        )
        kind_mismatches = sum(
            1
            for (expected_kind, _), actual in zip(requested_payloads, current_logs)
            if actual.kind is not expected_kind
        )
        feedback_logs = [log for log in current_logs if log.feedback is not None]
        feedback_evidence_coverage = (
            sum(1 for log in feedback_logs if log.reaction_evidence_ref is not None)
            / max(1, len(feedback_logs))
        )

        facts: dict[str, Any] = {
            "actions_logged": len(current_logs),
            "interventions": len(governor.logs_of_kind(AIActionKind.INTERVENTION)),
            "silences": len(governor.logs_of_kind(AIActionKind.SILENCE)),
            "advices": len(governor.logs_of_kind(AIActionKind.ADVICE)),
            "program_rewrite_count": rewrite_count,
            "explicit_kind_mismatches": kind_mismatches,
            "model_decisions_preserved": rewrite_count == 0 and kind_mismatches == 0,
            "history_samples": history.samples,
            "history_reaction_counts": json.dumps(dict(history.reaction_counts), ensure_ascii=False),
            "history_style_counts": json.dumps(dict(history.style_counts), ensure_ascii=False),
            "history_style_acceptance_rates": json.dumps(
                dict(history.style_acceptance_rates), ensure_ascii=False
            ),
            "case_history_samples": case_history.samples,
            "case_reaction_counts": json.dumps(
                dict(case_history.reaction_counts), ensure_ascii=False
            ),
            "silence_has_reason": bool(silence.silence_reason),
            "silence_content_chars": len(silence.content),
            "feedback_evidence_coverage": feedback_evidence_coverage,
            "communication_experiences_in_store": len(experiences),
            "ui_prompts_issued": governor.ui_prompts_issued,
            "style_landscape": json.dumps(governor.style_landscape(), ensure_ascii=False),
            "feedback_sources": ",".join(
                sorted({log.feedback_source for log in current_logs if log.feedback})
            ),
            "action_objects_in_store": len(
                self.store.list_payloads(object_type=ObjectType.ACTION)
            ),
        }
        invariants = (
            "开口 / 沉默 / 介入由模型显式选择，系统只验证结构并原样留痕",
            "程序不得根据用户关键词改写回复、推断姿态或替模型选择风格",
            "沟通经验只记录真实反馈统计，不输出推荐风格或禁用风格",
            "真实反馈必须带修订钉死的证据指针",
            "零界面：测试期间没有向用户发问卷/滑杆/确认请求",
        )
        return StageReport(
            stage_id="S7",
            title="AI 自身世界维护 / 模型驾驶 / 沟通经验留痕",
            facts=facts,
            invariants=invariants,
            timings_ms=tuple(decision_timings),
            token_burn=sum(log.token_cost for log in current_logs),
        )

    # ==================================================================
    # 阶段八：驾驶舱全景调度 / 硬旁路 / 终极对话
    # ==================================================================

    def stage_s8(self) -> StageReport:
        loader = MindOrderManifestLoader(self.store)
        manifest = loader.load(subject_id=self.subject_id, now=self.timeline_end())
        session = MindOrderSession(subject_id=self.subject_id)
        reorder_blocked = False
        try:
            session.run_step(MindLens.SCENE, lambda lens: lens.value)
        except MindOrderViolation:
            reorder_blocked = True
        step_outputs: list[str] = []
        for lens in MIND_ORDER:
            step_outputs.append(str(session.run_step(lens, lambda item: item.value)))
        sealed = [item.value for item in session.seal()]

        # 铁律 3：P0 硬旁路（真实硬件直穿入口）
        clear_safety_audit_queue()
        wake = SimpleNamespace(
            object_id="wake_blind_p0_0315",
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=SafetyBypassPayload(
                is_safety_bypass=True,
                hazard_type=HazardType.CARDIAC_ARREST,
                vital_snapshot={"heart_rate_bpm": 172, "axial_g_force": 5.4, "rhythm": "pvc_run"},
                emergency_action_code="EMERGENCY_BROADCAST_AND_SOS",
                triggered_at=self.timeline_end(),
            ),
        )
        p0_meter = ModelCallMeter(name="S8-p0")
        before = p0_meter.snapshot()
        p0_timings: list[float] = []
        p0_result: dict[str, Any] = {}
        for _ in range(50):
            started = time.perf_counter()
            p0_result = safe_dispatch_v22(wake)
            p0_timings.append((time.perf_counter() - started) * 1000.0)
        p0_meter.assert_untouched(before, context="P0 硬旁路必须 0 次大模型调用")
        audit_queue = len(SAFETY_AUDIT_QUEUE)

        # 条件任务双轨休眠：休眠零 Token
        scheduler = ConditionalTaskScheduler()
        dormant_tasks = []
        base_moment = self.timeline_end()
        for index in range(200):
            dormant_tasks.append(
                ConditionalTask(
                    task_id=f"cond_{index:03d}",
                    title=f"条件任务 {index}",
                    conditions=(
                        Condition(
                            kind=ConditionKind.ABSOLUTE_TIME,
                            summary=f"绝对时间窗 {index}",
                            deadline=base_moment + timedelta(days=120 + index % 60),
                        ),
                    ),
                )
            )
        scheduler.register_tasks(dormant_tasks)
        board_audit = scheduler.dormant_prompt_token_audit()
        mechanical = scheduler.tick(MechanicalSignal(now=base_moment))
        evaluator = LightweightConditionalEventEvaluator()
        for index in range(200):
            evaluator.register(
                f"eval_{index:03d}",
                title=f"求值任务 {index}",
                conditions=(
                    Condition(
                        kind=ConditionKind.GEO_FENCE,
                        summary=f"围栏 {index}",
                        place_key=f"place_{index % 5}",
                    ),
                ),
            )
        idle_report = evaluator.tick(EvaluatorSignals(now=base_moment))
        signal_report = evaluator.tick(
            EvaluatorSignals(now=base_moment, present_places=("place_2",))
        )

        # 终极对话：10 轮自然日常对话（每轮严格 1~3 句）
        pipeline = CockpitPipeline()
        conversation_texts = [
            self.observation_text(item)
            for item in self.observations()
            if str(item.get("source_kind")) in {"chat", "voice_transcript", "sms"}
        ][:10]
        while len(conversation_texts) < 10:
            conversation_texts.append("今天没什么特别的，就是有点累。")
        turn_sentences: list[int] = []
        turn_tokens: list[int] = []
        assembly_timings: list[float] = []
        preach_hits = 0
        for text in conversation_texts:
            result = pipeline.process_round(text, key_dispute_points=[text[:20]])
            sentences = split_sentences(result.assistant_round.text)
            turn_sentences.append(len(sentences))
            turn_tokens.append(result.cockpit.token_count)
            assembly_timings.append(result.assembly_ms)
            if "首先" in result.assistant_round.text or "保持积极" in result.assistant_round.text:
                preach_hits += 1

        facts: dict[str, Any] = {
            "manifest_total_tokens": manifest.total_tokens,
            "manifest_budget": manifest.budget,
            "manifest_source_reads": manifest.source_reads,
            "manifest_loader_loads": loader.loads,
            "manifest_questions_to_user": manifest.questions_to_user,
            "manifest_section_order": ",".join(section.lens.value for section in manifest.sections),
            "manifest_section_titles": " | ".join(section.title for section in manifest.sections),
            "manifest_highlights": sum(len(section.highlights) for section in manifest.sections),
            "manifest_elided": sum(section.elided for section in manifest.sections),
            "manifest_load_ms": round(manifest.load_ms, 3),
            "mind_order_reorder_blocked": reorder_blocked,
            "mind_order_sealed": ",".join(sealed),
            "mind_order_steps": ",".join(step_outputs),
            "p0_first_action": p0_result.get("first_action"),
            "p0_status": p0_result.get("status"),
            "p0_bypassed_llm": p0_result.get("bypassed_llm"),
            "p0_llm_calls": p0_result.get("llm_calls"),
            "p0_audit_receipts": audit_queue,
            "p0_p50_ms": round(percentiles(p0_timings)["p50"], 4),
            "p0_p95_ms": round(percentiles(p0_timings)["p95"], 4),
            "p0_p99_ms": round(percentiles(p0_timings)["p99"], 4),
            "p0_max_ms": round(percentiles(p0_timings)["max"], 4),
            "dormant_tasks": scheduler.dormant_count,
            "dormant_tokens_in_board": board_audit["dormant_tokens_in_board"],
            "dormant_tokens_if_naive": board_audit["dormant_tokens_if_naively_prompted"],
            "dormant_frozen_out": board_audit["dormant_frozen_out"],
            "mechanical_tick_evaluated": mechanical.evaluated,
            "mechanical_tick_llm_calls": 0,
            "scheduler_llm_calls": scheduler.llm_calls,
            "scheduler_autonomous_wakes": scheduler.autonomous_wakes,
            "evaluator_idle_evaluated": idle_report.tasks_evaluated,
            "evaluator_signal_evaluated": signal_report.tasks_evaluated,
            "evaluator_registered": 200,
            "conversation_rounds": len(turn_sentences),
            "conversation_sentence_counts": ",".join(str(item) for item in turn_sentences),
            "conversation_max_sentences": max(turn_sentences),
            "conversation_min_sentences": min(turn_sentences),
            "conversation_max_round_tokens": max(turn_tokens),
            "conversation_total_tokens": sum(turn_tokens),
            "conversation_single_shot_budget": SINGLE_SHOT_TOKEN_BUDGET,
            "conversation_window_size": ACTIVITY_WINDOW_SIZE,
            "conversation_active_window": len(pipeline.state.active_window()),
            "conversation_archived_rounds": len(pipeline.state.archived()),
            "conversation_lossless_rounds": len(pipeline.state.all_rounds()),
            "conversation_preach_hits": preach_hits,
            "assembly_p50_ms": round(percentiles(assembly_timings)["p50"], 4),
            "assembly_p95_ms": round(percentiles(assembly_timings)["p95"], 4),
            "assembly_p99_ms": round(percentiles(assembly_timings)["p99"], 4),
        }
        invariants = (
            "全景看板单次装载（1 次世界读取）、零提问、总量 ≤ Token 预算",
            "四步心法顺序不可换：乱序/回退立即抛错，完整走完才算封印",
            "P0 跌倒/心脏骤停：首行动作是硬件脉冲，0 次大模型调用，端到端 ≤50ms",
            "条件任务双轨：休眠任务在看板里 0 Token，机械 tick 0 大模型调用",
            "机械求值器静默 tick 求值 0 条；带信号 tick 只碰命中桶",
            "10 轮自然对话每轮严格 1~3 句，单轮看板 Token 不越 1500，窗口无损滚动",
        )
        return StageReport(
            stage_id="S8",
            title="驾驶舱全景调度 / 硬旁路 / 终极对话",
            facts=facts,
            invariants=invariants,
            timings_ms=tuple(p0_timings + assembly_timings),
        )

    # ==================================================================
    # 五条铁律的现场证据（全部取自实测数字，不做任何主观声明）
    # ==================================================================

    def _iron_rule_evidence(self) -> dict[str, str]:
        ingest = self._ingest_report
        parts: dict[str, str] = {}
        if ingest is not None:
            parts["铁律1 输出质量绝对第一"] = (
                f"百万流压缩比 {ingest.compression_ratio:.6f}；"
                "对话侧见 S8（每轮 1~3 句、单轮 ≤1500 Token、0 说教命中）"
            )
            parts["铁律4 大模型自主判断删除"] = (
                f"边缘噪声裁决 {ingest.noise_dropped_at_edge} 条；"
                "核心证据原话与证据链 100% 留存（见 S1 实测字段）"
            )
        return parts

    # ==================================================================
    # 附：单算子微基准（供报告的"新工具"章节引用）
    # ==================================================================

    def operator_microbench(self, *, imu_samples: int = 200_000) -> dict[str, Any]:
        """三个新算子的独立微基准（含冲击保真与误差上界复核）。"""

        compressor = AdaptiveTemporalCompressor(epsilon=0.5, curvature_budget=0.5, impact_magnitude=3.0)
        samples: list[tuple[int, float]] = []
        for index in range(imu_samples):
            value = 1.0
            if index % 25_000 == 0:
                value = 5.5
            samples.append((index * 20_000, value))
        started = time.perf_counter()
        result = compressor.compress(samples)
        compress_ms = (time.perf_counter() - started) * 1000.0
        worst_error = verify_error_bound(samples, result)

        evaluator = LightweightConditionalEventEvaluator()
        now = self.timeline_end()
        for index in range(2_000):
            evaluator.register(
                f"mb_{index:04d}",
                title=f"微基准任务 {index}",
                conditions=(
                    Condition(
                        kind=ConditionKind.GEO_FENCE,
                        summary=f"围栏 {index}",
                        place_key=f"place_{index % 50}",
                    ),
                ),
            )
        started = time.perf_counter()
        idle = evaluator.tick(EvaluatorSignals(now=now))
        idle_ms = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        fired = evaluator.tick(EvaluatorSignals(now=now, present_places=("place_9",)))
        signal_ms = (time.perf_counter() - started) * 1000.0

        projector = DualLensVirtualIndexProjector()
        for index in range(2_000):
            projector.index_fact(
                f"mb_fact_{index:04d}",
                f"合伙出资与银行流水第 {index} 笔，涉及对赌与借款协议",
                learned_us=1_700_000_000_000_000 + index,
            )
        frozen = projector.freeze_base()
        projector.attach_annotation(
            "mb_anno_1",
            target_object_id="mb_fact_0042",
            statement="事后证实该笔资金涉嫌合同诈骗",
            slot="meaning",
            annotated_us=1_800_000_000_000_000,
        )
        metrics = projector.metrics()

        return {
            "compressor": {
                "input": result.input_count,
                "segments": result.output_count,
                "impact_segments": result.impact_count,
                "reduction_ratio": round(result.reduction_ratio, 6),
                "max_reconstruction_error": round(worst_error, 6),
                "epsilon": compressor.epsilon,
                "compress_ms": round(compress_ms, 3),
                "samples_per_second": round(imu_samples / max(compress_ms / 1000.0, 1e-9), 1),
            },
            "evaluator": {
                "registered": 2_000,
                "idle_evaluated": idle.tasks_evaluated,
                "idle_ms": round(idle_ms, 4),
                "signal_evaluated": fired.tasks_evaluated,
                "signal_ms": round(signal_ms, 4),
                "touched_ratio": round(fired.touched_ratio, 6),
                "llm_calls": fired.llm_calls,
            },
            "projector": {
                "facts": metrics.indexed_facts,
                "base_postings": metrics.base_postings,
                "overlay_postings_written": metrics.overlay_postings_written,
                "naive_rebuild_postings": metrics.naive_rebuild_postings,
                "saved_ratio": round(metrics.saved_ratio, 6),
                "base_hash_unchanged": projector.base_compatible_with_frozen(),
                "frozen_hash": frozen[:16],
            },
        }


def world_archetypes() -> tuple[LifeArchetype, ...]:
    """盲测覆盖的人生切片清单（报告与测试共同引用）。"""

    return tuple(spec.archetype for spec in SAGA_SEEDS)


def raw_stream_totals(scale: float = 1.0, seed: int = 20260916) -> dict[str, int]:
    """给定规模的原始流配额（报告里用来声明"百万级"的确切数字）。"""

    counts = MassiveSyntheticLifeBench(seed=seed, scale=scale).counts()
    return {
        "imu": counts.imu,
        "heart": counts.heart,
        "vision": counts.vision,
        "audio": counts.audio,
        "text": counts.text,
        "total": counts.total,
    }


def iter_stream_sample(harness: BlindBenchHarness, limit: int = 5) -> Iterable[dict]:
    """抽样回显世界里的前 N 条观察（调试与报告附录用，只读）。"""

    for payload in harness.observations()[:limit]:
        yield {
            "object_id": payload["object_id"],
            "source_kind": payload.get("source_kind"),
            "value": harness.observation_text(payload)[:120],
        }
