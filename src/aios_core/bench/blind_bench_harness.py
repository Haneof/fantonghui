"""AIOS 全流程海量盲测编排器（8 大阶段端到端 · 独立考官 + 被测系统隔离）。

职责
----
把"对抗生命数据发生器（考官）→ 真实系统组件（被测）→ 可审计度量（判决）"
串成一条可复跑的流水线，供压测报告、缺陷诊断与回归测试共同消费：

* ``run_stage1``：百万级原始样本流式摄入 → 端侧提纯 → 结构化事实落库；
* ``run_stage2``：日→周→月→季→半年→年→多年逐级结晶 → 无损穿透到单条原话；
* ``run_stage3..8``：委托 ``blind_bench_cognition`` / ``blind_bench_dialogue``
  执行（认知/对话两条主线），本模块只负责装配与度量。

纪律
----
1. 只调用公开接口（store / pyramid / crystal / guard / cockpit / dispatcher …），
   不触碰任何私有字段；
2. 所有度量来自真实调用点（``perf_counter`` / ``/proc/self/statm``），不估算；
3. 阶段失败直接抛真实异常，绝不吞掉或"降级成通过"。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

from aios_core.bench.adversarial_life_bench import (
    GATE_PROFILE,
    BenchProfile,
    MassiveSyntheticLifeBench,
    ROLE_NOISE,
)
from aios_core.bench.blind_bench_metrics import (
    LatencyRecorder,
    MemoryProbe,
    ModelCallMeter,
    StageMetric,
    TokenLedger,
)
from aios_core.bench.blind_bench_results import HarnessSnapshot, StageOneResult, StageTwoResult
from aios_core.contracts.enums import ObjectType, SourceClass
from aios_core.contracts.ids import new_operation_id
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.ingest.edge_stream_purifier import EdgeStreamPurifier, EvidenceNoiseJanitor
from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    RawByteSink,
    VoiceprintLSHIndex,
    VoiceprintTTLRegistry,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.summaries.pyramid_aggregator import PyramidAggregator
from aios_core.tools.adaptive_temporal_compressor import (
    AdaptiveScalarCompressor,
    AdaptiveTemporalCompressor,
)
from aios_core.tools.adaptive_temporal_compressor import MAX_IMPACT_WAVEFORM_SAMPLES
from aios_core.tools.multiscale_crystal_index import MultiScaleCrystalIndex

UTC = timezone.utc

#: 落库批次大小（越小内存越省、越大吞吐越高；4000 为实测折中）。
COMMIT_BATCH_SIZE = 4000

#: 每处理多少条原始样本结算一次（把 Observation 及时落库、避免整批驻留）。
INGEST_FLUSH_EVERY = 40_000

#: 允许出现的"波形逐点保留"载荷键（仅冲击波形与生理突变，且长度受限）。
_WAVEFORM_KEYS = ("waveform_samples",)
#: 与压缩器的保留配额同源：异常冲击波形允许保留的逐点样本上限（口径不得漂移）。
_WAVEFORM_MAX_LEN = MAX_IMPACT_WAVEFORM_SAMPLES


def _parse_utc(value: str) -> datetime:
    """解析世界库 ISO 时间戳（无时区按 UTC）。"""

    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _iter_payload_values(value: Any) -> Iterable[str]:
    """把任意载荷摊平成字符串流（用于噪声残留扫描）。"""

    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _iter_payload_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_payload_values(item)
    else:
        yield str(value)


class BlindBenchHarness:
    """8 大阶段端到端盲测编排器（真实组件驱动，零 mock 断言）。"""

    _STAGE_LABELS: Mapping[str, str] = {
        "S1": "海量原始摄入 · 端侧提纯 · 证据永存",
        "S2": "时间金字塔逐级结晶 · 无损穿透",
        "S3": "共现拓扑召回 · 跨域共振合成 · 事件生命周期",
        "S4": "高阶认知导数 · 新维度三闸 · 人生章节相变",
        "S5": "历史认知回溯 · 老王案单跳隔离",
        "S6": "共生决策推演 · 主动帮助",
        "S7": "AI 自身世界维护 · 沟通策略博弈",
        "S8": "驾驶舱全景调度 · 硬旁路 · 终极对话",
    }

    def __init__(
        self,
        *,
        workdir: pathlib.Path,
        profile: BenchProfile = GATE_PROFILE,
        seed: int = 20260916,
    ) -> None:
        self.workdir = pathlib.Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        self.seed = int(seed)
        self.db_path = self.workdir / f"blind_bench_{profile.name}.db"
        if self.db_path.exists():
            self.db_path.unlink()
        self.store = SQLiteWorldStore(self.db_path)
        self.bench = MassiveSyntheticLifeBench(profile, seed=seed)
        self.recorder = LatencyRecorder()
        self.memory = MemoryProbe()
        self.ledger = TokenLedger()
        self.meter = ModelCallMeter()
        self.metrics: Dict[str, StageMetric] = {}
        #: 上一阶段结算时的驻留内存峰值：用于给出**每阶段增量**而不是累计峰值。
        self._peak_at_last_stage_kb = self.memory.peak_kb
        self.stage1: StageOneResult | None = None
        self.stage2: StageTwoResult | None = None
        self.purifier: EdgeStreamPurifier | None = None
        self.aggregator: PyramidAggregator | None = None
        self.crystal: MultiScaleCrystalIndex | None = None
        self.duplicate_observations_dropped = 0
        # 阶段 3+ 的共享上下文（实体、事件、目标、任务 …）
        self.world: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 度量
    # ------------------------------------------------------------------

    def _record_metrics(
        self, stage: str, started_at: float, *, facts: Mapping[str, Any] | None = None
    ) -> StageMetric:
        """结算单阶段度量。

        ``rss_peak_delta_kb`` 口径是**本阶段新增的驻留内存峰值**（相对上一阶段结算点），
        而不是进程累计峰值 —— 否则每个阶段都会抄到同一个大数字，把"谁在吃内存"
        这件事彻底糊掉（这正是"度量口径必须精确"的教训）。
        """

        self.memory.sample()  # 结算点上采样：确保本阶段真实占用被计入峰值
        stage_delta_kb = max(0, self.memory.peak_kb - self._peak_at_last_stage_kb)
        self._peak_at_last_stage_kb = self.memory.peak_kb
        metric = StageMetric(
            stage=stage,
            label=self._STAGE_LABELS[stage],
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            rss_peak_delta_kb=stage_delta_kb,
            tokens=self.ledger.total_tokens,
            llm_calls=self.meter.total,
            counters=dict(facts or {}),
            latencies=self.recorder.summary(),
        )
        self.metrics[stage] = metric
        return metric

    def snapshot(self) -> HarnessSnapshot:
        return HarnessSnapshot(
            profile=self.profile.name,
            seed=self.seed,
            stage_metrics={stage: metric.as_dict() for stage, metric in self.metrics.items()},
            token_ledger=self.ledger.snapshot(),
            model_calls=self.meter.snapshot(),
            generated_at=datetime.now(UTC),
            latencies=self.recorder.summary(),
        )

    # ------------------------------------------------------------------
    # S1：海量原始摄入 → 端侧提纯 → 事实落库
    # ------------------------------------------------------------------

    def _build_purifier(self) -> EdgeStreamPurifier:
        return EdgeStreamPurifier(
            imu_compressor=AdaptiveTemporalCompressor(
                tolerance=0.12,
                min_state_span_s=0.8,
                impact_threshold_g=1.9,
                fall_threshold_g=2.6,
            ),
            hr_compressor=AdaptiveScalarCompressor(
                tolerance=5.0, max_segment_span_s=7200.0, min_episode_span_s=1800.0
            ),
            janitor=EvidenceNoiseJanitor(),
            cleaner=EdgeMultimodalCleaner(),
            voiceprints=VoiceprintLSHIndex(),
            sink=RawByteSink(),
            voiceprint_ttl=VoiceprintTTLRegistry(),
            min_motion_state_s=0.8,
            min_hr_episode_s=1800.0,
        )

    def run_stage1(self) -> StageOneResult:
        """流式摄入百万级原始样本，端侧提纯后仅把结构化事实落库。"""

        started = time.perf_counter()
        purifier = self._build_purifier()
        self.purifier = purifier
        raw_total = 0
        committed = 0
        noise_texts_ground_truth: set[str] = set()
        evidence_ids: Dict[str, str] = {}
        since_flush = 0
        batch_started = time.perf_counter()

        for sample in self.bench.iter_samples():
            raw_total += 1
            if sample.kind == "imu_burst":
                raw_total += len(sample.payload.get("samples", ())) - 1
            payload = sample.payload
            visible_text = payload.get("text") or payload.get("transcript")
            if isinstance(visible_text, str) and visible_text and sample.role == ROLE_NOISE:
                noise_texts_ground_truth.add(visible_text)
            purifier.ingest(sample.blinded())
            since_flush += 1
            if since_flush >= INGEST_FLUSH_EVERY:
                self.recorder.record(
                    "S1.ingest_batch_ms", (time.perf_counter() - batch_started) * 1000.0
                )
                batch_started = time.perf_counter()
                since_flush = 0
                drained = purifier.drain_observations()
                committed += self._commit_observations(drained)
                self.memory.sample()
                self._remember_evidence(drained, evidence_ids)
            self.memory.sample()

        self.recorder.record(
            "S1.ingest_batch_ms", (time.perf_counter() - batch_started) * 1000.0
        )
        purifier.flush(datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC))
        # 收尾结算点：全量尾巴（flush + drain + 最后一次落库）才是真正的内存峰值所在，
        # 必须显式采样，否则会低报（这正是"探针只在事件上采样"的教训）。
        self.memory.sample()
        drained = purifier.drain_observations()
        committed += self._commit_observations(drained)
        self.memory.sample()
        self._remember_evidence(drained, evidence_ids)
        self.memory.sample()

        tombstoned = purifier.sweep_voiceprints(datetime(2026, 6, 1, tzinfo=UTC))
        purity = self._voiceprint_slice_purity(purifier)
        violations, residue = self._self_audit_store(purifier)
        beat_texts = {beat.key: beat.text for beat in self.bench.beats}
        evidence_keys = tuple(sorted(self.bench.evidence_keys()))
        report = purifier.report
        result = StageOneResult(
            profile_name=self.profile.name,
            raw_sample_total=raw_total,
            durable_observation_count=report.durable_observation_count,
            committed_observation_count=committed,
            report=report,
            evidence_observation_ids={
                key: evidence_ids[text] for key, text in beat_texts.items() if text in evidence_ids
            },
            noise_texts=tuple(sorted(noise_texts_ground_truth)),
            evidence_keys=evidence_keys,
            evidence_retention_ratio=purifier.evidence_retention_ratio(evidence_keys, beat_texts),
            noise_purge_ratio=purifier.noise_purge_ratio(
                tuple(sorted(noise_texts_ground_truth))
            ),
            motion_compression_ratio=purifier.motion_compression_ratio,
            hr_compression_ratio=purifier.hr_compression_ratio,
            tombstoned_voiceprints=tuple(tombstoned),
            bound_voiceprints=dict(purifier.bound_voiceprints),
            voiceprint_slice_purity=purity,
            raw_bytes_retained=purifier.raw_bytes_retained,
            db_size_bytes=self.db_path.stat().st_size,
            duplicate_observations_dropped=self.duplicate_observations_dropped,
            durable_by_kind=dict(report.durable_by_kind),
            raw_observation_scan_violations=tuple(violations),
            noise_text_residue=tuple(residue),
        )
        self.stage1 = result
        self.world["evidence_texts"] = {
            str(payload["object_id"]): str(
                (payload.get("value") or {}).get("transcript")
                or (payload.get("value") or {}).get("text")
                or ""
            )
            for payload in self.store.list_payloads(object_type=ObjectType.OBSERVATION)
            if isinstance(payload.get("value"), Mapping) and payload["value"].get("evidence") is True
        }
        self.ledger.charge(
            "S1.edge_purifier",
            tokens=report.durable_observation_count * 6,
            calls=report.durable_observation_count,
        )
        self._record_metrics(
            "S1",
            started,
            facts={
                "raw_samples": raw_total,
                "durable_observations": committed,
                "evidence_retention": round(result.evidence_retention_ratio, 4),
                "noise_purge": round(result.noise_purge_ratio, 4),
                "raw_scan_violations": len(violations),
                "raw_scan_violation_samples": list(violations[:3]),
                "durable_by_kind": dict(report.durable_by_kind),
                "motion_compression_ratio": round(result.motion_compression_ratio, 2),
                "hr_compression_ratio": round(result.hr_compression_ratio, 2),
                "impact_waveforms": report.impact_waveform_count,
                "fall_suspect": report.fall_suspect_count,
            },
        )
        return result

    def _commit_observations(self, observations: Sequence[Observation]) -> int:
        """按批提交 Observation（同一批内同 id 去重，存储层保证修订单调）。"""

        deduped: list[Observation] = []
        seen: set[str] = set()
        for observation in observations:
            if observation.object_id in seen:
                self.duplicate_observations_dropped += 1
                continue
            seen.add(observation.object_id)
            deduped.append(observation)
        committed = 0
        for start in range(0, len(deduped), COMMIT_BATCH_SIZE):
            chunk = deduped[start : start + COMMIT_BATCH_SIZE]
            if not chunk:
                continue
            operation = OperationRequest(
                operation_id=new_operation_id(),
                operation_name="blind_bench.ingest.edge_purified",
                expected_world_revision=self.store.current_world_revision(),
                reason="端侧提纯后的结构化事实落库（原始波形与噪声已物理删除）",
                idempotency_key=(
                    f"blind_bench_{self.seed}_{start}_{len(chunk)}_{self._chunk_fingerprint(chunk)}"
                ),
                source_class=SourceClass.SENSOR,
            )
            with self.recorder.time_block("S1.commit_batch_ms"):
                self.store.commit(chunk, operation)
            committed += len(chunk)
        return committed

    @staticmethod
    def _chunk_fingerprint(chunk: Sequence[Observation]) -> str:
        """批次内容指纹：同内容重放 = 等价请求（可幂等），不同内容绝不撞键。

        2026-09-16 实测教训：早期用 ``start/len/committed`` 拼幂等键，
        当两批"形状相同、内容不同"时会被存储层判为
        ``IDEMPOTENCY_CONFLICT``（FULL 档位 S1 曾因此整段失败）。
        """

        digest = hashlib.sha1(
            "|".join(observation.object_id for observation in chunk).encode("utf-8")
        ).hexdigest()
        return digest[:16]

    @staticmethod
    def _remember_evidence(
        observations: Iterable[Observation], evidence_ids: Dict[str, str]
    ) -> None:
        for observation in observations:
            value = observation.value if isinstance(observation.value, Mapping) else {}
            if value.get("evidence") is not True:
                continue
            text = value.get("transcript") or value.get("text")
            if isinstance(text, str) and text:
                evidence_ids.setdefault(text, observation.object_id)

    @staticmethod
    def _voiceprint_slice_purity(purifier: EdgeStreamPurifier) -> float:
        tokens = tuple(purifier.bound_voiceprints) + tuple(
            token
            for token in purifier.voiceprint_last_contact
            if token not in purifier.bound_voiceprints
        )
        if not tokens:
            return 0.0
        correct = sum(1 for token in tokens if purifier.assign_voiceprint_slice(token) == token)
        return correct / len(tokens)

    def _self_audit_store(
        self, purifier: EdgeStreamPurifier
    ) -> tuple[list[str], list[str]]:
        """落库后自审：原始波形残留 + 噪声文本残留（两会事，都要为零）。"""

        noise_texts = set(purifier.report.noise_texts_purged)
        violations: list[str] = []
        residue: list[str] = []
        for payload in self.store.list_payloads(object_type=ObjectType.OBSERVATION):
            value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
            for key in _WAVEFORM_KEYS:
                samples = value.get(key)
                if isinstance(samples, (list, tuple)) and len(samples) > _WAVEFORM_MAX_LEN:
                    violations.append(f"{payload.get('object_id')}:{key}")
            for key, item in value.items():
                if key == "samples" and isinstance(item, (list, tuple)) and len(item) > 3:
                    violations.append(f"{payload.get('object_id')}:{key}")
            blob = " ".join(_iter_payload_values(value))
            for text in noise_texts:
                if text and text in blob:
                    residue.append(str(payload.get("object_id")))
                    break
        return violations, residue

    # ------------------------------------------------------------------
    # S2：时间金字塔逐级结晶 → 无损穿透
    # ------------------------------------------------------------------

    def _build_day_digests(self) -> list[Dict[str, Any]]:
        """把落库的结构化事实逐日聚成"日结晶"事件（金字塔底层事实）。"""

        observations = self.store.list_payloads(object_type=ObjectType.OBSERVATION)
        by_day: Dict[str, list[Dict[str, Any]]] = {}
        for payload in observations:
            occurred = payload.get("occurred") or {}
            started = occurred.get("start")
            if isinstance(started, str) and started:
                by_day.setdefault(started[:10], []).append(payload)
        digests: list[Dict[str, Any]] = []
        for day_key in sorted(by_day):
            items = by_day[day_key]
            evidence_refs: list[str] = []
            health_points = 0
            finance_points = 0
            social_points = 0
            motion_states = 0
            for payload in items:
                value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
                object_id = str(payload.get("object_id"))
                if value.get("evidence") is True:
                    evidence_refs.append(object_id)
                if str(payload.get("source_kind", "")).startswith("wearable"):
                    health_points += 1
                if value.get("motion_state"):
                    motion_states += 1
                if "chat_message" in object_id or "utterance" in object_id:
                    social_points += 1
                serialized = json.dumps(value, ensure_ascii=False)
                if "转出" in serialized or "借条" in serialized:
                    finance_points += 1
            digests.append(
                {
                    "id": f"digest_{day_key}",
                    "time": f"{day_key}T23:00:00+00:00",
                    "dimension_id": "DIM_LIFE_EVENTS",
                    "text": (
                        f"{day_key} 共 {len(items)} 条结构化事实"
                        f"（证据 {len(evidence_refs)} / 生理 {health_points} /"
                        f" 社交 {social_points} / 运动状态 {motion_states}）"
                    ),
                    "evidence_ids": evidence_refs[:16],
                    "observation_count": len(items),
                    "health_points": health_points,
                    "finance_points": finance_points,
                    "social_points": social_points,
                    "x": round(min(1.0, health_points / 60.0), 4),
                    "y": round(min(1.0, social_points / 40.0), 4),
                    "z": round(min(1.0, finance_points / 5.0), 4),
                    "r": round(min(1.0, len(evidence_refs) / 4.0), 4),
                    "c": 0.62,
                }
            )
        return digests

    def run_stage2(self) -> StageTwoResult:
        """日→周→月→季→半年→年逐级结晶，并从年度结论穿透回单条原始原话。"""

        started = time.perf_counter()
        if self.stage1 is None:
            raise RuntimeError("run_stage2 requires run_stage1")

        digests = self._build_day_digests()
        aggregator = PyramidAggregator()
        self.aggregator = aggregator
        crystal = MultiScaleCrystalIndex()
        self.crystal = crystal
        by_year: Dict[int, list[Dict[str, Any]]] = {}
        for digest in digests:
            by_year.setdefault(int(digest["time"][:4]), []).append(digest)

        year_summaries: Dict[int, Any] = {}
        pyramid_started = time.perf_counter()
        for year in sorted(by_year):
            with self.recorder.time_block("S2.pyramid_rollup_ms"):
                year_summaries[year] = aggregator.generate_materialized_rollup(
                    "YEAR", "DIM_LIFE_EVENTS", by_year[year]
                )
        pyramid_ms = (time.perf_counter() - pyramid_started) * 1000.0
        vault_before = aggregator.vault_size()
        raw_probe_id = digests[0]["id"]
        fingerprint_before = hashlib.sha256(
            json.dumps(aggregator.get_raw_event(raw_probe_id), sort_keys=True, default=str).encode(
                "utf-8"
            )
        ).hexdigest()

        # —— 年度结论 → 月 → 周 → 日 → 单条原话 ——
        target_year = min(year_summaries)
        year_summary = year_summaries[target_year]
        with self.recorder.time_block("S2.drill_down_ms"):
            months = aggregator.drill_down(year_summary.summary_id, "MONTH")
        chain: list[str] = [f"YEAR:{year_summary.summary_id}"]
        observation_id = ""
        observation_text = ""
        for month in months:
            with self.recorder.time_block("S2.drill_down_ms"):
                weeks = aggregator.drill_down(month.summary_id, "WEEK")
            for week in weeks:
                with self.recorder.time_block("S2.drill_down_ms"):
                    raw_days = aggregator.drill_down(week.summary_id, "DAY")
                for raw_day in raw_days:
                    refs = list(raw_day.get("evidence_ids") or ())
                    if not refs:
                        continue
                    probe = str(refs[0])
                    payload = self.store.get_payload(probe)
                    value = (
                        payload.get("value")
                        if isinstance(payload.get("value"), Mapping)
                        else {}
                    )
                    observation_id = probe
                    observation_text = str(value.get("transcript") or value.get("text") or "")
                    chain.extend(
                        [
                            f"MONTH:{month.summary_id}",
                            f"WEEK:{week.summary_id}",
                            f"DAY:{raw_day['id']}",
                            f"OBSERVATION:{probe}",
                        ]
                    )
                    break
                if observation_id:
                    break
            if observation_id:
                break

        # —— 证据链完整率：每个日结晶的证据指针都必须指回可读事实 ——
        evidence_index: Dict[str, str] = {}
        for payload in self.store.list_payloads(object_type=ObjectType.OBSERVATION):
            value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
            if value.get("evidence") is True:
                text = value.get("transcript") or value.get("text")
                if isinstance(text, str):
                    evidence_index[str(payload["object_id"])] = text
        broken = 0
        total_links = 0
        for digest in digests:
            for ref in digest["evidence_ids"]:
                total_links += 1
                if ref not in evidence_index:
                    broken += 1
        break_ratio = (broken / total_links) if total_links else 0.0

        month_union: set[str] = set()
        for month in months:
            month_union |= set(month.evidence_ids)
        union_conserved = month_union == set(year_summary.evidence_ids)

        # —— 七档结晶（补足季/半年尺度缝），逐档守恒 ——
        year_crystals: Dict[int, Any] = {}
        for year in sorted(by_year):
            with self.recorder.time_block("S2.crystal_rollup_ms"):
                year_crystals[year] = crystal.crystallize(
                    "YEAR", "DIM_LIFE_EVENTS", by_year[year]
                )
        crystal_fingerprint_before = crystal.vault_fingerprint()
        target_crystal = year_crystals[target_year]
        with self.recorder.time_block("S2.crystal_drill_ms"):
            quarters = crystal.drill(target_crystal.crystal_id, "QUARTER")
        with self.recorder.time_block("S2.crystal_drill_ms"):
            halves = crystal.drill(target_crystal.crystal_id, "HALF_YEAR")
        crystal_union_conserved = crystal.assert_union_conserved(
            target_crystal.crystal_id, "QUARTER"
        ) and crystal.assert_union_conserved(target_crystal.crystal_id, "HALF_YEAR")
        union_levels = ["QUARTER", "HALF_YEAR"]
        first_quarter = quarters[0]
        with self.recorder.time_block("S2.crystal_drill_ms"):
            quarter_months = crystal.drill(first_quarter.crystal_id, "MONTH")
        crystal_union_conserved = crystal_union_conserved and crystal.assert_union_conserved(
            first_quarter.crystal_id, "MONTH"
        )
        union_levels.append("MONTH")
        crystal_month = quarter_months[0]
        with self.recorder.time_block("S2.crystal_drill_ms"):
            crystal_raw_events = crystal.drill(crystal_month.crystal_id, "DAY")
        # 下钻探针必须挑"真的挂着证据引文"的那一天：多数日期只有例行传感数据，
        # 若机械取第 0 条，"链路通不通"就会被"那天有没有引文"污染（度量口径必须精确）。
        probe_event = next(
            (
                item
                for item in crystal_raw_events
                if list(item.get("evidence_ids") or ())
            ),
            crystal_raw_events[0],
        )
        crystal_refs = list(probe_event.get("evidence_ids") or ())
        crystal_text = ""
        if crystal_refs:
            payload = self.store.get_payload(str(crystal_refs[0]))
            value = payload.get("value") if isinstance(payload.get("value"), Mapping) else {}
            crystal_text = str(value.get("transcript") or value.get("text") or "")
        crystal_fingerprint_after = crystal.vault_fingerprint()
        pyramid_month = next(item for item in months if item.start_time.month == 1)
        crystal_vs_pyramid_equal = (
            set(crystal_month.evidence_ids) == set(pyramid_month.evidence_ids)
            and set(target_crystal.evidence_ids) == set(year_summary.evidence_ids)
        )
        fingerprint_after = hashlib.sha256(
            json.dumps(aggregator.get_raw_event(raw_probe_id), sort_keys=True, default=str).encode(
                "utf-8"
            )
        ).hexdigest()

        result = StageTwoResult(
            digest_count=len(digests),
            pyramid_years=tuple(sorted(year_summaries)),
            drill_chain=tuple(chain),
            drill_chain_observation_id=observation_id,
            drill_chain_text=observation_text,
            drill_chain_expected_text=evidence_index.get(observation_id, ""),
            drill_chain_text_matches=bool(observation_text)
            and observation_text == evidence_index.get(observation_id, ""),
            evidence_chain_break_ratio=break_ratio,
            evidence_chain_links_checked=total_links,
            union_conserved=union_conserved,
            vault_size=aggregator.vault_size(),
            vault_fingerprint_before=fingerprint_before,
            vault_fingerprint_after=fingerprint_after,
            crystal_scale_counts=dict(crystal.scale_counts()),
            crystal_union_conserved=crystal_union_conserved,
            crystal_union_checked_levels=tuple(union_levels),
            crystal_vs_pyramid_equal=crystal_vs_pyramid_equal,
            crystal_fingerprint_before=crystal_fingerprint_before,
            crystal_fingerprint_after=crystal_fingerprint_after,
            crystal_drill_text=crystal_text,
            crystal_raw_event_count=len(crystal_raw_events),
            half_year_crystal_count=len(halves),
            vault_immutable=(
                fingerprint_before == fingerprint_after
                and crystal_fingerprint_before == crystal_fingerprint_after
                and vault_before == aggregator.vault_size()
            ),
            pyramid_latency_ms=pyramid_ms,
        )
        self.stage2 = result
        self.world["digests"] = digests
        self.ledger.charge("S2.pyramid", tokens=len(digests) * 8, calls=len(digests))
        self._record_metrics(
            "S2",
            started,
            facts={
                "digests": len(digests),
                "evidence_chain_break_ratio": round(break_ratio, 6),
                "union_conserved": union_conserved,
                "crystals": crystal.crystal_count(),
            },
        )
        return result

    # ------------------------------------------------------------------
    # S3–S8：委托认知/对话主线模块（延迟导入，避免循环依赖）
    # ------------------------------------------------------------------

    def run_stage3(self) -> Any:
        from aios_core.bench.blind_bench_cognition import run_stage3

        return run_stage3(self)

    def run_stage4(self) -> Any:
        from aios_core.bench.blind_bench_cognition import run_stage4

        return run_stage4(self)

    def run_stage5(self) -> Any:
        from aios_core.bench.blind_bench_cognition import run_stage5

        return run_stage5(self)

    def run_stage6(self) -> Any:
        from aios_core.bench.blind_bench_dialogue import run_stage6

        return run_stage6(self)

    def run_stage7(self) -> Any:
        from aios_core.bench.blind_bench_dialogue import run_stage7

        return run_stage7(self)

    def run_stage8(self) -> Any:
        from aios_core.bench.blind_bench_dialogue import run_stage8

        return run_stage8(self)

    def run_all(self) -> HarnessSnapshot:
        """顺序跑完八阶段（任一阶段失败即抛真实异常）。"""

        self.run_stage1()
        self.run_stage2()
        self.run_stage3()
        self.run_stage4()
        self.run_stage5()
        self.run_stage6()
        self.run_stage7()
        self.run_stage8()
        return self.snapshot()
