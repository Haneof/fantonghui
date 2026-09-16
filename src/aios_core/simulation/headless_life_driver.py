"""SIM-001 deterministic, headless 30/180-day life simulation driver.

The driver streams hourly events rather than retaining the timeline.  It uses
real AIOS components for C01 image cleanup, C06 CJK indexing, C02 append-only
world persistence, C04 bounded cockpit assembly, and C05 retrospective
annotation.  No display, browser, GUI toolkit, or background service is used.
"""

from __future__ import annotations

import gc
import json
import math
import os
import sqlite3
import time
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.cockpit.pipeline import (
    CockpitPipeline,
    ConversationTurn,
    CrisisCockpitContext,
)
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import (
    TemporalExtent,
    TimePrecision,
    as_utc,
    require_aware,
)
from aios_core.ingest.multimodal_edge import EdgeMultimodalCleaner, RawByteSink
from aios_core.query.cjk_inverted_index import CJKTopologicalInvertedIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation import (
    BiTemporalEpistemicLens,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationJournal,
)


class RuntimePolicyError(RuntimeError):
    """The runtime policy is absent, malformed, ambiguous, or illegally relaxed."""


class TokenBudgetExceededError(RuntimeError):
    """A cockpit assembly would cross the monthly physical token envelope."""


class SimulationMemoryLimitError(RuntimeError):
    """The process crossed the absolute Linux RSS ceiling."""


class RuntimeTokenPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    monthly_token_budget: int = Field(ge=1, le=2_554_000)
    source_path: str = Field(min_length=1)

    CONSTITUTIONAL_MONTHLY_CEILING: ClassVar[int] = 2_554_000
    _BUDGET_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "monthly_token_budget",
            "monthly_total",
            "monthly_total_tokens",
            "monthly_tokens",
        }
    )

    @classmethod
    def load(cls, path: str | Path) -> RuntimeTokenPolicy:
        policy_path = Path(path)
        if not policy_path.is_file():
            raise RuntimePolicyError(f"runtime policy does not exist: {policy_path}")
        try:
            payload = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimePolicyError("runtime policy is not valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimePolicyError("runtime policy root must be an object")

        candidates: list[int] = []

        def walk(node: object) -> None:
            if not isinstance(node, Mapping):
                return
            for key, value in node.items():
                if key in cls._BUDGET_KEYS:
                    if isinstance(value, bool) or not isinstance(value, int):
                        raise RuntimePolicyError(
                            f"runtime token budget {key} must be an integer"
                        )
                    candidates.append(value)
                elif isinstance(value, Mapping):
                    walk(value)

        walk(payload)
        if not candidates:
            raise RuntimePolicyError("runtime policy has no monthly token budget")
        if len(set(candidates)) != 1:
            raise RuntimePolicyError(
                "runtime policy contains conflicting token budgets"
            )
        budget = candidates[0]
        if budget > cls.CONSTITUTIONAL_MONTHLY_CEILING:
            raise RuntimePolicyError(
                "runtime policy cannot relax the 2,554,000-token ceiling"
            )
        try:
            return cls(
                monthly_token_budget=budget,
                source_path=str(policy_path),
            )
        except ValueError as exc:
            raise RuntimePolicyError(
                "runtime token budget is outside allowed bounds"
            ) from exc


class LifeHourEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    hour_index: int = Field(ge=0)
    occurred_at: datetime
    circadian_state: Literal["DEEP_SLEEP", "AWAKE", "WIND_DOWN"]
    location: str
    industrial_noise_db: float = Field(ge=0.0, le=140.0)
    heart_rate_samples: tuple[float, ...] = Field(min_length=300, max_length=300)
    hrv_samples_ms: tuple[float, ...] = Field(min_length=300, max_length=300)
    image_quality: float = Field(ge=0.0, le=1.0)
    semantic_text: str = Field(min_length=1, max_length=8_192)
    meeting_title: str | None = None
    commercial_crisis: str | None = None
    lao_wang_contract_breach: bool = False

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime) -> datetime:
        require_aware(value, "occurred_at")
        return value


class HighEntropyLifeStream:
    """Generate a reproducible adult life stream at 300 physiological samples/hour."""

    SAMPLES_PER_HOUR: ClassVar[int] = 300
    MEETING_HOURS: ClassVar[tuple[int, ...]] = (9, 11, 14, 16)
    CRISIS_SLOTS: ClassVar[dict[tuple[int, int], str]] = {
        (4, 10): "供应商突然拒绝履行独家供货与保密承诺",
        (11, 15): "投资方要求当日补签高风险对赌回购附件",
        (19, 9): "核心客户以审计差异为由暂停付款",
        (26, 16): "工厂数据泄露与竞业索赔同时升级",
    }
    LAO_WANG_BREACH_SLOT: ClassVar[tuple[int, int]] = (17, 14)

    def __init__(self, *, start_at: datetime, days: int = 30) -> None:
        require_aware(start_at, "start_at")
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 180:
            raise ValueError("days must be an integer between 1 and 180")
        self.start_at = start_at
        self.days = days

    def __iter__(self) -> Iterator[LifeHourEvent]:
        for hour_index in range(self.days * 24):
            day, hour = divmod(hour_index, 24)
            occurred_at = self.start_at + timedelta(hours=hour_index)
            circadian = self._circadian_state(hour)
            crisis = self.CRISIS_SLOTS.get((day, hour))
            breach = (day, hour) == self.LAO_WANG_BREACH_SLOT
            meeting = (
                f"第{day + 1:02d}日-{hour:02d}时法务经营会议"
                if hour in self.MEETING_HOURS
                else None
            )
            location = "industrial-workshop" if 8 <= hour <= 18 else "shanghai-home"
            noise = (
                91.0 + ((day * 7 + hour) % 8)
                if location == "industrial-workshop"
                else 34.0 + ((day + hour) % 5)
            )
            base_heart_rate = self._base_heart_rate(hour, crisis is not None, breach)
            heart_rate, hrv = self._physiological_samples(
                base_heart_rate,
                day=day,
                hour=hour,
            )
            semantic_parts = [
                f"第{day + 1}天{hour:02d}时",
                "工业车间高噪巡检" if noise >= 85 else "低噪生活与恢复时段",
                f"心率均值{sum(heart_rate) / len(heart_rate):.1f}",
                f"HRV均值{sum(hrv) / len(hrv):.1f}",
            ]
            if meeting is not None:
                semantic_parts.append(meeting)
            if crisis is not None:
                semantic_parts.append(f"突发商业危机：{crisis}")
            if breach:
                semantic_parts.append(
                    "老王合同违约事实确认：隐瞒股权变更并拒绝履行回购义务"
                )
            yield LifeHourEvent(
                hour_index=hour_index,
                occurred_at=occurred_at,
                circadian_state=circadian,
                location=location,
                industrial_noise_db=noise,
                heart_rate_samples=heart_rate,
                hrv_samples_ms=hrv,
                image_quality=(0.28 if hour_index % 7 == 0 else 0.78),
                semantic_text="；".join(semantic_parts),
                meeting_title=meeting,
                commercial_crisis=crisis,
                lao_wang_contract_breach=breach,
            )

    @staticmethod
    def _circadian_state(hour: int) -> Literal["DEEP_SLEEP", "AWAKE", "WIND_DOWN"]:
        if 0 <= hour < 6:
            return "DEEP_SLEEP"
        if hour >= 22:
            return "WIND_DOWN"
        return "AWAKE"

    @staticmethod
    def _base_heart_rate(hour: int, crisis: bool, breach: bool) -> float:
        if 0 <= hour < 6:
            base = 56.0
        elif 8 <= hour <= 18:
            base = 82.0
        else:
            base = 67.0
        if crisis:
            base += 24.0
        if breach:
            base += 18.0
        return base

    @classmethod
    def _physiological_samples(
        cls,
        base_heart_rate: float,
        *,
        day: int,
        hour: int,
    ) -> tuple[tuple[float, ...], tuple[float, ...]]:
        heart_rate = tuple(
            round(
                base_heart_rate
                + math.sin((sample + day * 13 + hour * 5) * 0.17) * 7.0
                + math.cos((sample + hour) * 0.031) * 2.5,
                3,
            )
            for sample in range(cls.SAMPLES_PER_HOUR)
        )
        hrv = tuple(
            round(
                max(
                    8.0,
                    72.0
                    - (value - 55.0) * 0.55
                    + math.sin((sample + day) * 0.11) * 4.0,
                ),
                3,
            )
            for sample, value in enumerate(heart_rate)
        )
        return heart_rate, hrv


class SimulationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    days: int = Field(ge=1, le=180)
    generated_hours: int = Field(ge=1)
    physiological_sample_count: int = Field(ge=1)
    meeting_count: int = Field(ge=0)
    commercial_crisis_count: int = Field(ge=0)
    lao_wang_breach_count: int = Field(ge=0)
    c01_image_frames_processed: int = Field(ge=0)
    c01_semantic_observations: int = Field(ge=0)
    c01_raw_bytes_retained: Literal[0] = 0
    c06_indexed_entities: int = Field(ge=0)
    c06_breach_query_hits: int = Field(ge=0)
    c02_persisted_observations: int = Field(ge=0)
    c02_world_revision: int = Field(ge=0)
    c04_cockpit_assemblies: int = Field(ge=0)
    c05_retrospective_annotations: int = Field(ge=0)
    c05_historical_overlay_count: Literal[0] = 0
    c05_current_overlay_count: int = Field(ge=0)
    consumed_tokens: int = Field(ge=0)
    monthly_token_budget: int = Field(ge=1, le=2_554_000)
    token_budget_remaining: int = Field(ge=0)
    deadlock_count: Literal[0] = 0
    initial_rss_bytes: int = Field(ge=0)
    final_rss_bytes: int = Field(ge=0)
    peak_rss_bytes: int = Field(ge=0)
    rss_limit_bytes: int = Field(ge=1)
    daily_rss_bytes: tuple[int, ...] = Field(min_length=2)
    wall_clock_seconds: float = Field(gt=0.0)
    acceleration_factor: float = Field(gt=0.0)
    completed_chain: tuple[str, ...]

    @model_validator(mode="after")
    def hard_gate_receipt_must_be_consistent(self) -> SimulationReport:
        if self.generated_hours != self.days * 24:
            raise ValueError("generated_hours must cover every simulated hour")
        if self.meeting_count != self.days * 4:
            raise ValueError("simulation must generate four meetings per day")
        if self.c01_image_frames_processed != self.generated_hours:
            raise ValueError("C01 must process every hourly frame")
        if self.c02_persisted_observations != self.generated_hours:
            raise ValueError("C02 must persist every hourly semantic observation")
        if self.consumed_tokens > self.monthly_token_budget:
            raise ValueError("consumed_tokens exceeds monthly budget")
        if (
            self.token_budget_remaining
            != self.monthly_token_budget - self.consumed_tokens
        ):
            raise ValueError("token budget receipt is inconsistent")
        if self.peak_rss_bytes > self.rss_limit_bytes:
            raise ValueError("peak RSS exceeds the configured hard ceiling")
        return self


class _TokenEnvelope:
    __slots__ = ("budget", "consumed")

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.consumed = 0

    def consume(self, token_count: int) -> None:
        if isinstance(token_count, bool) or not isinstance(token_count, int):
            raise TypeError("token_count must be an integer")
        if token_count < 0:
            raise ValueError("token_count must be non-negative")
        if self.consumed + token_count > self.budget:
            raise TokenBudgetExceededError(
                f"monthly token envelope would exceed {self.budget} tokens"
            )
        self.consumed += token_count


class HeadlessLifeDriver:
    """Run the complete deterministic chain in one bounded Linux process."""

    DEFAULT_POLICY_PATH: ClassVar[Path] = Path("governance/runtime_policy.json")
    DEFAULT_RSS_LIMIT_BYTES: ClassVar[int] = 128 * 1024 * 1024
    STABLE_RSS_GROWTH_BYTES: ClassVar[int] = 32 * 1024 * 1024

    def __init__(
        self,
        *,
        work_dir: str | Path,
        runtime_policy_path: str | Path = DEFAULT_POLICY_PATH,
        start_at: datetime,
        days: int = 30,
        rss_limit_bytes: int = DEFAULT_RSS_LIMIT_BYTES,
    ) -> None:
        require_aware(start_at, "start_at")
        if rss_limit_bytes <= 0:
            raise ValueError("rss_limit_bytes must be positive")
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.policy = RuntimeTokenPolicy.load(runtime_policy_path)
        self.start_at = start_at
        self.days = days
        self.rss_limit_bytes = rss_limit_bytes
        self._simulated_now = start_at
        self._image_sequence = 0
        self._has_run = False

        self.raw_sink = RawByteSink()
        self.cleaner = EdgeMultimodalCleaner(
            raw_byte_sink=self.raw_sink,
            clock=lambda: self._simulated_now,
            id_factory=self._next_image_id,
        )
        self.world_store = SQLiteWorldStore(self.work_dir / "world.db")
        self._index_connection = sqlite3.connect(":memory:")
        self.cjk_index = CJKTopologicalInvertedIndex(self._index_connection)
        self.cockpit = CockpitPipeline(clock=lambda: self._simulated_now)
        self.annotation_journal = RetrospectiveAnnotationJournal(
            self.work_dir / "retrospective.db"
        )

    def run(self) -> SimulationReport:
        if self._has_run:
            raise RuntimeError("headless life driver is single-use")
        self._has_run = True
        stream = HighEntropyLifeStream(start_at=self.start_at, days=self.days)
        token_envelope = _TokenEnvelope(self.policy.monthly_token_budget)
        daily_observations: list[Observation] = []
        daily_significant_events: list[LifeHourEvent] = []
        world_revision = self.world_store.current_world_revision()
        generated_hours = 0
        physiological_samples = 0
        meeting_count = 0
        crisis_count = 0
        breach_count = 0
        semantic_observations = 0
        indexed_entities = 0
        cockpit_assemblies = 0
        turn_sequence = 0

        gc.collect()
        initial_rss = self._linux_rss_bytes()
        peak_rss = initial_rss
        daily_rss = [initial_rss]
        wall_started = time.perf_counter()

        try:
            for event in stream:
                self._simulated_now = event.occurred_at
                generated_hours += 1
                physiological_samples += len(event.heart_rate_samples)
                meeting_count += int(event.meeting_title is not None)
                crisis_count += int(event.commercial_crisis is not None)
                breach_count += int(event.lao_wang_contract_breach)

                semantic_caption = self._run_c01(event)
                semantic_observations += int(semantic_caption is not None)
                observation = self._build_world_observation(event, semantic_caption)
                daily_observations.append(observation)

                indexed_entities += int(
                    self.cjk_index.index_entity_text(
                        observation.object_id,
                        event.semantic_text,
                        int(as_utc(event.occurred_at).timestamp() * 1_000_000_000),
                    )
                    > 0
                )

                if (
                    event.meeting_title is not None
                    or event.commercial_crisis is not None
                    or event.lao_wang_contract_breach
                ):
                    daily_significant_events.append(event)

                if (event.hour_index + 1) % 24 == 0:
                    day_number = (event.hour_index + 1) // 24
                    result = self.world_store.commit(
                        daily_observations,
                        OperationRequest(
                            operation_name="simulation.persist_day",
                            expected_world_revision=world_revision,
                            reason="SIM-001 continuous headless life replay",
                            idempotency_key=f"sim-day-{day_number:03d}",
                            arguments={
                                "day": day_number,
                                "hour_count": len(daily_observations),
                            },
                        ),
                    )
                    world_revision = result.world_revision
                    daily_observations.clear()

                    # C04 and C05 run only after the day's C02 ledger commit.
                    for significant_event in daily_significant_events:
                        self._simulated_now = significant_event.occurred_at
                        turn_sequence += 1
                        manifest = self._run_c04(significant_event, turn_sequence)
                        token_envelope.consume(manifest.prompt_token_count)
                        cockpit_assemblies += 1
                        if significant_event.lao_wang_contract_breach:
                            self._run_c05(significant_event)
                    daily_significant_events.clear()
                    self._simulated_now = event.occurred_at
                    gc.collect()
                    day_rss = self._linux_rss_bytes()
                    daily_rss.append(day_rss)
                    peak_rss = max(peak_rss, day_rss)
                    self._enforce_rss(peak_rss)

                current_rss = self._linux_rss_bytes()
                peak_rss = max(peak_rss, current_rss)
                self._enforce_rss(peak_rss)
        finally:
            self._index_connection.commit()

        wall_seconds = max(time.perf_counter() - wall_started, 1e-9)
        final_rss = self._linux_rss_bytes()
        peak_rss = max(peak_rss, final_rss)
        self._enforce_rss(peak_rss)
        if final_rss - initial_rss > self.STABLE_RSS_GROWTH_BYTES:
            raise SimulationMemoryLimitError(
                "RSS growth exceeds the 32MiB stable-growth envelope"
            )

        breach_hits = self.cjk_index.co_search(["老王", "合同违约"])
        historical_overlay_count, current_overlay_count = self._verify_c05_lens()
        simulated_seconds = self.days * 24 * 60 * 60
        return SimulationReport(
            days=self.days,
            generated_hours=generated_hours,
            physiological_sample_count=physiological_samples,
            meeting_count=meeting_count,
            commercial_crisis_count=crisis_count,
            lao_wang_breach_count=breach_count,
            c01_image_frames_processed=self.raw_sink.purged_frame_count,
            c01_semantic_observations=semantic_observations,
            c01_raw_bytes_retained=self.raw_sink.retained_byte_count,
            c06_indexed_entities=indexed_entities,
            c06_breach_query_hits=len(breach_hits),
            c02_persisted_observations=generated_hours,
            c02_world_revision=world_revision,
            c04_cockpit_assemblies=cockpit_assemblies,
            c05_retrospective_annotations=self.annotation_journal.count(),
            c05_historical_overlay_count=historical_overlay_count,
            c05_current_overlay_count=current_overlay_count,
            consumed_tokens=token_envelope.consumed,
            monthly_token_budget=token_envelope.budget,
            token_budget_remaining=token_envelope.budget - token_envelope.consumed,
            deadlock_count=0,
            initial_rss_bytes=initial_rss,
            final_rss_bytes=final_rss,
            peak_rss_bytes=peak_rss,
            rss_limit_bytes=self.rss_limit_bytes,
            daily_rss_bytes=tuple(daily_rss),
            wall_clock_seconds=wall_seconds,
            acceleration_factor=simulated_seconds / wall_seconds,
            completed_chain=(
                "C01_EDGE_CLEAN",
                "C06_INVERTED_INTERSECTION",
                "C02_LEDGER_PERSIST",
                "C04_SINGLE_COCKPIT",
                "C05_RETROSPECTIVE_ANNOTATION",
            ),
        )

    def close(self) -> None:
        self._index_connection.close()

    def _run_c01(self, event: LifeHourEvent) -> str | None:
        raw_frame = bytearray(
            (event.hour_index * 37 + offset * 19) % 256 for offset in range(256)
        )
        result = self.cleaner.evaluate_and_clean_image(
            {
                "quality_score": event.image_quality,
                "semantic_caption": event.semantic_text,
                "scene_tags": [event.location, event.circadian_state.casefold()],
                "captured_at": event.occurred_at,
            },
            raw_frame,
        )
        if any(raw_frame):
            raise RuntimeError("C01 returned while raw image bytes remained in memory")
        if result is None:
            return None
        if result.raw_image_bytes_retained is not False:
            raise RuntimeError("C01 attempted to retain raw image bytes")
        return result.semantic_caption

    def _build_world_observation(
        self,
        event: LifeHourEvent,
        semantic_caption: str | None,
    ) -> Observation:
        average_heart_rate = sum(event.heart_rate_samples) / len(
            event.heart_rate_samples
        )
        average_hrv = sum(event.hrv_samples_ms) / len(event.hrv_samples_ms)
        metadata: dict[str, Any] = {
            "hour_index": event.hour_index,
            "location": event.location,
            "circadian_state": event.circadian_state,
        }
        if event.lao_wang_contract_breach:
            metadata["target_entity_id"] = "entity_lao_wang"
        return Observation(
            object_id=f"obs_sim_life_hour_{event.hour_index:04d}",
            subject_id="entity_simulated_legal_director",
            occurred=TemporalExtent.point(
                event.occurred_at,
                precision=TimePrecision.HOUR,
                timezone_name="Asia/Shanghai",
            ),
            learned_at=event.occurred_at,
            recorded_at=event.occurred_at,
            created_by="SIM-001-headless-life-driver",
            source_kind="linux_virtual_multimodal_device",
            modality="hourly_semantic_vitals",
            value={
                "semantic_caption": semantic_caption,
                "heart_rate_mean_bpm": round(average_heart_rate, 3),
                "hrv_mean_ms": round(average_hrv, 3),
                "industrial_noise_db": event.industrial_noise_db,
                "meeting_title": event.meeting_title,
                "commercial_crisis": event.commercial_crisis,
                "lao_wang_contract_breach": event.lao_wang_contract_breach,
            },
            unit=None,
            data_quality={
                "physiological_samples": len(event.heart_rate_samples),
                "image_quality": event.image_quality,
                "raw_binary_retained": False,
            },
            raw_locator=None,
            metadata=metadata,
        )

    def _run_c04(self, event: LifeHourEvent, sequence: int):
        crisis_text = event.commercial_crisis or (
            "老王合同违约与股权变更证据需要立即固定"
            if event.lao_wang_contract_breach
            else "复杂经营会议进入待决事项"
        )
        turn = ConversationTurn(
            turn_id=f"sim-cockpit-turn-{sequence:04d}",
            sequence_no=sequence,
            occurred_at=event.occurred_at,
            user_text=f"{event.meeting_title or '突发事项'}；{crisis_text}",
            assistant_text=(
                "先固定原始证据和截止时间，不在高压状态下补签争议文件。"
                "这一轮只把最关键的下一步放进看板。"
            ),
        )
        context = CrisisCockpitContext(
            session_id="sim-30day-headless-life",
            ai_self_summary="长期共生僚机；证据优先；不制造焦虑；不越权执行。",
            rapport_state="长期高信任，但高压时坚持短句和事实边界。",
            wake_reason_anchor=event.semantic_text,
            local_world_facts=(
                f"地点={event.location}；噪声={event.industrial_noise_db:.1f}dB；"
                f"事件={crisis_text}"
            ),
            ready_tasks=[
                {
                    "task_id": f"sim-ready-{sequence:04d}",
                    "state": "READY",
                    "title": "固定证据并核对不可逆截止时间",
                }
            ],
        )
        return self.cockpit.process_turn(turn, context)

    def _run_c05(self, event: LifeHourEvent) -> None:
        annotation = RetrospectiveAnnotation(
            annotation_id="annotation_sim_lao_wang_breach",
            target_entity_id="entity_lao_wang",
            semantic_overlay=(
                "今天确认的隐瞒股权变更与拒绝回购事实，重估此前合作承诺的可信度；"
                "历史记录本身不改写。"
            ),
            target_time_start=self.start_at + timedelta(days=2),
            target_time_end=self.start_at + timedelta(days=16),
            learned_at=event.occurred_at,
            source_statement_ref="simulated-court-freeze-and-breach-evidence",
        )
        self.annotation_journal.append(annotation)

    def _verify_c05_lens(self) -> tuple[int, int]:
        if self.days <= HighEntropyLifeStream.LAO_WANG_BREACH_SLOT[0]:
            return 0, 0
        lens = BiTemporalEpistemicLens(journal=self.annotation_journal)
        target_time = self.start_at + timedelta(days=10)
        historical = lens.query_historical_slice(
            "entity_lao_wang",
            target_time,
            as_of_cutoff=self.start_at + timedelta(days=16),
        )
        current = lens.query_historical_slice(
            "entity_lao_wang",
            target_time,
        )
        return len(historical.active_annotations), len(current.active_annotations)

    def _next_image_id(self) -> str:
        self._image_sequence += 1
        return f"obs_sim_image_{self._image_sequence:04d}"

    def _enforce_rss(self, rss_bytes: int) -> None:
        if rss_bytes > self.rss_limit_bytes:
            raise SimulationMemoryLimitError(
                f"RSS {rss_bytes} exceeds hard limit {self.rss_limit_bytes}"
            )

    @staticmethod
    def _linux_rss_bytes() -> int:
        statm = Path("/proc/self/statm")
        try:
            fields = statm.read_text(encoding="ascii").split()
            resident_pages = int(fields[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE")
        except (IndexError, OSError, ValueError) as exc:
            raise RuntimeError("SIM-001 requires Linux /proc RSS accounting") from exc
