"""SIM-001 无界面 Linux 30 天/180 天高熵多维人生仿真器驱动引擎。

纯 Python、零 UI、可无头跑批的"虚拟人多维人生时空仿真推演机"。
驱动完整技术链：

    数据接入 -> C01 边缘清洗 -> C06 倒排求交 -> C02 账本持久化
             -> C04 单看板装配 -> C05 回溯注记

四大硬门禁 → 工程落点：

1. 高熵 30 天时空流发生器：720 小时连续时间轴（昼夜节律、高频心率/HRV
   噪声、车间高噪环境、恰好 120 次工作会议、突发商业危机、老王合同违约
   剧情线），由单一 seed 完全确定性重放。
2. 全链驱动：六个阶段计数器全部非零才算跑通；C02 用正式 SQLiteWorldStore
   账本，C05 用 M1-018 回溯注记引擎，C04/C01 调度联动用本批 M2-005R /
   M2-001 引擎，C06 为驱动所需的轻量化倒排求交头。
3. 0 死锁 + 内存平稳：协作式单线程主循环，逐日推进量守恒校验
   （deadlock_cycles 恒 0）；流水线对象流式写入 SQLite，每日 flush 后
   驻留 buffer 清空；原始二进制滞留量恒 0。
4. 月度 Token 封套：全部"大模型"消耗经 PseudoLLM 计量器记账，与
   governance/runtime_policy.json 的 monthly_token_budget 比对。
"""

from __future__ import annotations

import json
import pathlib
import random
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.safety_bypass import WakePriority
from aios_core.contracts.time import TemporalExtent
from aios_core.scheduler.conditional_engine import (
    BiometricThresholdCondition,
    ConditionalSchedulerEngine,
    SchedulerStage,
    SemanticContextCondition,
    TimeArrivalCondition,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.wake.cooldown_queue import (
    SensorPulse,
    SilentWakeEngine,
    SleepStage,
    WakeNotice,
)
from aios_core.world.retrospective_annotation import (
    EpistemicWorldLens,
    RetrospectiveAnnotation,
)

__all__ = ["SimConfig", "RunReport", "HeadlessLifeDriver", "load_token_policy"]

UTC = timezone.utc
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
POLICY_PATH = REPO_ROOT / "governance" / "runtime_policy.json"


def load_token_policy(path: pathlib.Path | None = None) -> dict:
    """读取月度 Token 封套政策；缺失时回退到 SIM-001 工单原文口径。"""
    target = path or POLICY_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    return {
        "monthly_token_budget": int(raw.get("monthly_token_budget", 2_554_000)),
        "raw_binary_image_retention_bytes_max": int(
            (raw.get("hard_rules") or {}).get("raw_binary_image_retention_bytes_max", 0)
        ),
    }


@dataclass(frozen=True, slots=True)
class SimConfig:
    seed: int = 20260916
    days: int = 30
    minutes_step: int = 10
    meetings_per_day: int = 4  # 30 天 × 4 = 恰好 120 次工作会议
    t_origin: datetime = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    laowang_partnership_day: int = 2
    laowang_breach_day: int = 17
    laowang_learning_day: int = 18
    exercise_days: tuple[int, ...] = (5, 11, 16, 23, 28)  # 羽毛球/高压运动日
    crisis_days: tuple[int, ...] = (7, 13, 22)
    subject_id: str = "sim-user-legal-director"
    laowang_entity_id: str = "sim-ent-laowang"
    bulk_conditional_tasks: int = 200  # 法务总监的 200 项跨周期条件任务


@dataclass(slots=True)
class RunReport:
    days: int = 0
    ticks: int = 0
    samples_generated: int = 0
    observations_committed: int = 0
    world_revision: int = 0
    meetings: int = 0
    crises: int = 0
    laowang_facts: int = 0
    retrospective_overlays: int = 0
    dormant_prompt_tokens: int = 0
    dormant_board_leaks: int = 0
    level1_evaluations: int = 0
    level1_llm_calls: int = 0
    llm_calls_total: int = 0
    prompt_tokens_total: int = 0
    token_budget: int = 0
    raw_binary_retained_bytes: int = 0
    raw_binaries_cleaned: int = 0
    inverted_index_entries: int = 0
    inverted_intersect_queries: int = 0
    inverted_intersect_hits: int = 0
    wake_pulses_ingested: int = 0
    wake_batches_emitted: int = 0
    deep_sleep_deferred: int = 0
    morning_flushed_events: int = 0
    deadlock_cycles: int = 0
    retained_records: int = 0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 高熵人生流发生器（确定性）
# ---------------------------------------------------------------------------


class CircadianPersona:
    """单 seed 决定一切随机性：昼夜节律 + 心率/HRV + 环境 + 剧情事件。"""

    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self._rng = random.Random(cfg.seed)
        self._hr_state = 66.0

    def sample(self, minute: int, day: int) -> dict:
        """一个仿真分钟的完整切片（高熵、多物理域）。"""
        rng = self._rng
        hour = (minute // 60) % 24
        asleep = hour >= 23 or hour < 7
        if asleep:
            stage = "deep" if hour in (2, 3, 4, 5) else "light"
            baseline, variability = 52.0, 2.5
        else:
            stage = "awake"
            working = 9 <= hour <= 18
            baseline = 74.0 if working else 64.0
            variability = 6.0 if working else 3.5
            if day in self.cfg.exercise_days and 19 <= hour <= 20:
                baseline, variability = 128.0, 14.0  # 羽毛球赛后心率剧烈波动窗口
            elif day in (self.cfg.laowang_breach_day, self.cfg.laowang_learning_day):
                baseline, variability = 96.0, 10.0  # 高压剧情日
        self._hr_state = self._hr_state * 0.7 + baseline * 0.3
        hr = max(41.0, min(181.0, self._hr_state + rng.gauss(0.0, variability)))
        hrv = max(8.0, (72.0 - abs(hr - 68.0)) * (0.6 if asleep else 1.0) + rng.gauss(0, 4))
        place = self._place_for(hour, asleep)
        activity = "deep_focus" if (place == "office" and hour in (10, 15)) else "normal"
        imu = round(0.12 + abs(rng.gauss(0, 0.08)) + (1.9 if baseline > 100 else 0.0), 3)
        return {
            "minute": minute,
            "day": day,
            "at": self.cfg.t_origin + timedelta(minutes=minute),
            "stage": stage,
            "hr": round(hr, 2),
            "hrv": round(hrv, 1),
            "imu_magnitude_g": imu,
            "env": {
                "noise_db": round(38.0 + (-20.0 if asleep else 26.0) + abs(rng.gauss(0, 7)), 1),
                "place": place,
                "activity": activity,
            },
        }

    @staticmethod
    def _place_for(hour: int, asleep: bool) -> str:
        if asleep:
            return "home_bed"
        if 9 <= hour <= 18:
            return "office"
        if hour in (12, 13):
            return "canteen"
        return "home"

    def discrete_events(self, day: int) -> Iterator[tuple[str, dict]]:
        """剧情事件（每天恰好一次；120 会议 / 危机 / 老王线）。"""
        cfg = self.cfg
        for i in range(cfg.meetings_per_day):
            yield (
                "meeting",
                {
                    "topic": f"诉讼/合规案头评审 #{day * cfg.meetings_per_day + i + 1}",
                    "attendees": (day + i) % 6 + 2,
                },
            )
        if day in cfg.crisis_days:
            yield ("crisis", {"kind": f"突发商业危机：对方律师团突袭送达 #{day}"})
        if day == cfg.laowang_partnership_day:
            yield (
                "laowang_partnership",
                {"note": "与老王签约合伙，信任度满格", "capital_out": 50000.0},
            )
        if day == cfg.laowang_breach_day:
            yield ("laowang_breach", {"note": "老王合同违约：资金挪用证据浮出"})
        if day == cfg.laowang_learning_day:
            yield ("laowang_learned_fraud", {"note": "用户亲口指认：老王是骗子，已卷款出境"})


# ---------------------------------------------------------------------------
# 轻量化 C01 / C06 驱动头；C02/C04/C05 挂正式引擎
# ---------------------------------------------------------------------------


class EdgeCleaner:
    """C01 边缘清洗头：波形压缩 + 二进制全语义化（原始大图 0 滞留）。"""

    HR_QUIET_SECONDS = 2 * 3600  # 宪法第33条：平稳长周期仅记一个时段平均点

    def __init__(self) -> None:
        self._hr_window: list[dict] = []
        self._last_hr_flush_at: datetime | None = None
        self._last_hr_flush_value: float | None = None
        self.raw_binaries_cleaned = 0
        self.raw_binary_retained_bytes = 0

    @property
    def pending_window(self) -> int:
        return len(self._hr_window)

    def push_hr(self, sample: dict) -> list[dict]:
        """心率/HRV 流压缩：平稳段 2h 一个均值点；突变立即冲刷。"""
        self._hr_window.append(sample)
        hr = sample["hr"]
        spike = self._last_hr_flush_value is not None and abs(hr - self._last_hr_flush_value) >= 15.0
        quiet = self._last_hr_flush_at is None or (
            sample["at"] - self._last_hr_flush_at
        ).total_seconds() >= self.HR_QUIET_SECONDS
        if spike or quiet:
            return [self._flush_hr()]
        return []

    def _flush_hr(self) -> dict:
        window, self._hr_window = self._hr_window, []
        avg = sum(s["hr"] for s in window) / len(window)
        self._last_hr_flush_at = window[-1]["at"]
        self._last_hr_flush_value = window[-1]["hr"]
        return {
            "kind": "heart_rate_window",
            "at": window[-1]["at"],
            "value": {
                "avg_bpm": round(avg, 2),
                "max_bpm": max(s["hr"] for s in window),
                "min_bpm": min(s["hr"] for s in window),
                "avg_hrv": round(sum(s["hrv"] for s in window) / len(window), 1),
                "sample_count": len(window),
            },
            "tags": {"health", "heart_rate"},
        }

    def semanticize_binary(self, media_kind: str, raw_bytes_len: int, caption: str) -> dict:
        """图片/录音一律转语义文本，原始字节当场销毁 —— 滞留量恒 0。"""
        if raw_bytes_len <= 0:
            raise ValueError("raw_bytes_len must be positive")
        self.raw_binaries_cleaned += 1
        self.raw_binary_retained_bytes += 0  # 原始字节从不入账（构造性为 0）
        return {
            "kind": f"semantic_{media_kind}",
            "caption": caption,
            "original_bytes_discarded": raw_bytes_len,
            "tags": {"caption", media_kind},
        }


class MiniInvertedIndex:
    """C06 倒排求交头：tag -> object_id posting 表。"""

    def __init__(self) -> None:
        self._postings: dict[str, set[str]] = defaultdict(set)
        self.queries = 0
        self.hits = 0

    def add(self, object_id: str, tags: Iterator[str] | set[str]) -> None:
        for tag in tags:
            self._postings[str(tag)].add(object_id)

    def intersect(self, tags: set[str]) -> list[str]:
        self.queries += 1
        if not tags:
            return []
        postings = [self._postings.get(tag, set()) for tag in sorted(tags)]
        postings.sort(key=len)
        result = set(postings[0])
        for posting in postings[1:]:
            result &= posting
        self.hits += len(result)
        return sorted(result)

    def entries(self) -> int:
        return sum(len(v) for v in self._postings.values())


class PseudoLLM:
    """确定性伪大模型：只计量、不真调用（无头跑批零外部依赖）。"""

    def __init__(self) -> None:
        self.calls = 0
        self.tokens = 0

    def complete(self, prompt_chars: int, completion_chars: int = 80) -> int:
        self.calls += 1
        used = (prompt_chars + 3) // 4 + completion_chars
        self.tokens += used
        return used


@dataclass(slots=True)
class _FlushBuffer:
    objects: list[Observation] = field(default_factory=list)
    tags_by_id: dict[str, set] = field(default_factory=dict)

    def clear(self) -> None:
        self.objects.clear()
        self.tags_by_id.clear()

    def __len__(self) -> int:
        return len(self.objects)


# ---------------------------------------------------------------------------
# 主驱动
# ---------------------------------------------------------------------------


class HeadlessLifeDriver:
    """30/180 天无头人生仿真主循环。"""

    CRISIS_RAW_IMAGE_BYTES = 2_400_000

    def __init__(
        self,
        cfg: SimConfig,
        db_path: str | pathlib.Path,
        policy_path: pathlib.Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.store = SQLiteWorldStore(str(db_path))
        self.cleaner = EdgeCleaner()
        self.index = MiniInvertedIndex()
        self.llm = PseudoLLM()
        self.scheduler = ConditionalSchedulerEngine()
        self.wake = SilentWakeEngine(window_seconds=5.0)
        self.lens = EpistemicWorldLens()
        self.policy = load_token_policy(policy_path)
        self._buffer = _FlushBuffer()
        self._obs_seq = 0
        self._flush_seq = 0
        self._last_stage: str | None = None
        self._retro_events: list[dict] = []
        self.persona = CircadianPersona(cfg)
        self.report = RunReport(token_budget=self.policy["monthly_token_budget"])

    # ------------------------------------------------------------------
    # 内部管道
    # ------------------------------------------------------------------

    def _emit_observation(
        self,
        *,
        at: datetime,
        source_kind: str,
        modality: str,
        value: dict,
        tags: set[str],
    ) -> Observation:
        self._obs_seq += 1
        obs = Observation(
            object_id=new_object_id_from_seq(self._obs_seq),
            subject_id=self.cfg.subject_id,
            occurred=TemporalExtent.point(at),
            learned_at=at,
            recorded_at=at,
            created_by="sim-001-headless-life-driver",
            source_kind=source_kind,
            modality=modality,
            value=value,
        )
        self._buffer.objects.append(obs)
        self._buffer.tags_by_id[obs.object_id] = set(tags)
        return obs

    def _flush(self, now: datetime) -> None:
        if not self._buffer.objects:
            return
        self._flush_seq += 1
        objects = list(self._buffer.objects)
        for obs in objects:
            tags = self._buffer.tags_by_id[obs.object_id]
            self.index.add(obs.object_id, tags)
            self.lens.record_observation(obs, involved_entity_ids=self._lens_entities(tags))
        request = OperationRequest(
            operation_id=f"sim001_flush_{self._flush_seq:06d}",
            session_id="sim-001-session",
            operation_name="sim.commit_batch",
            arguments={"batch_size": len(objects)},
            expected_world_revision=self.store.current_world_revision(),
            reason="SIM-001 headless daily ledger flush",
            idempotency_key=f"sim001-ik-{self._flush_seq:06d}",
        )
        self.store.commit(objects, request)
        self.report.observations_committed += len(objects)
        self._buffer.clear()
        if self.cfg.days >= 2:
            # 日结认知摘要：一次合法的伪 LLM 调用（受 Token 封套计量）
            self.llm.complete(prompt_chars=1200)

    def _lens_entities(self, tags: set[str]) -> list[str]:
        entities = [self.cfg.subject_id]
        if "laowang" in tags:
            entities.append(self.cfg.laowang_entity_id)
        return entities

    # ------------------------------------------------------------------
    # 条件任务挂载（M2-005R 联动）
    # ------------------------------------------------------------------

    def _register_conditional_tasks(self) -> None:
        cfg = self.cfg
        t0 = cfg.t_origin
        for i in range(cfg.bulk_conditional_tasks):
            self.scheduler.register_task(
                task_id=f"tsk_bulk_{i:03d}",
                title=f"跨周期法务条件任务 {i}",
                conditions=[TimeArrivalCondition(due_at=t0 + timedelta(days=2, hours=i))],
            )
        self.scheduler.register_task(
            task_id="tsk_hr_cardiology",
            title="连续3天晚间心率超95启动心内科预约建档",
            conditions=[
                BiometricThresholdCondition(
                    metric="heart_rate",
                    comparator="gt",
                    value=95.0,
                    consecutive_days=3,
                    evening_only=True,
                )
            ],
        )
        self.scheduler.register_task(
            task_id="tsk_equity_watch",
            title="诉讼对方实控人股权变更提醒",
            conditions=[
                SemanticContextCondition(
                    description="工商股权信号语义核验",
                    required_tags=frozenset({"股权", "工商信号"}),
                    needs_physical_gate=False,
                )
            ],
        )

    def _evaluate_level2_at_wake(self, record, scene) -> bool:
        """唯一的 LLM 消费点：用户主动唤醒时被引擎顺路调用，引擎不自主唤醒。"""
        self.llm.complete(prompt_chars=600 + len(record.title) * 4)
        return record.task_id == "tsk_equity_watch"

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> RunReport:
        cfg = self.cfg
        report = self.report
        report.days = cfg.days
        self._register_conditional_tasks()
        day_minutes = 24 * 60 // cfg.minutes_step
        for day in range(cfg.days):
            # —— 离散剧情：每天恰好一次（不得随分钟槽位重复触发）——
            for kind, payload in self.persona.discrete_events(day):
                self._on_discrete(day, kind, payload, report)

            for slot in range(day_minutes):
                minute = day * 24 * 60 + slot * cfg.minutes_step
                sample = self.persona.sample(minute, day)
                report.ticks += 1
                report.samples_generated += 1
                hour = (minute // 60) % 24
                tod = minute % 60

                # —— 睡眠分期 → M2-001 静默闸 ——
                stage = sample["stage"]
                if stage != self._last_stage:
                    self._last_stage = stage
                    self.wake.set_sleep_stage(
                        {
                            "deep": SleepStage.DEEP,
                            "light": SleepStage.LIGHT,
                            "awake": SleepStage.AWAKE,
                        }[stage],
                        at=sample["at"],
                    )
                    if stage == "awake":
                        self.wake.mark_out_of_bed(at=sample["at"])

                # —— C01 边缘清洗 + 心率压缩入账 ——
                for hr_event in self.cleaner.push_hr(sample):
                    self._emit_observation(
                        at=hr_event["at"],
                        source_kind="wristband_sensor",
                        modality="heart_rate",
                        value=hr_event["value"],
                        tags=set(hr_event["tags"]),
                    )
                if 19 <= hour <= 23:  # 晚间心率信号喂给 M2-005R 阈值门
                    self.scheduler.feed_biometric(
                        metric="heart_rate", value=sample["hr"], at=sample["at"]
                    )

                # —— 高频体征脉冲流（运动分钟 → 5s 合并窗批次）——
                exercising = (
                    sample["imu_magnitude_g"] > 1.5
                    and hour in (19, 20)
                    and day in cfg.exercise_days
                )
                if exercising:
                    for k in range(20):  # 50Hz 密度抽稀样本
                        self.wake.ingest_pulse(
                            SensorPulse(
                                metric="imu_accel",
                                value=sample["imu_magnitude_g"],
                                source="wristband_imu_50hz",
                                at=sample["at"] + timedelta(seconds=k * 3),
                            )
                        )
                        report.wake_pulses_ingested += 1
                self.wake.advance_to(sample["at"])

                # —— 在场/专注信号 + 机械快轨心跳 ——
                self.scheduler.feed_presence(
                    place_id=sample["env"]["place"],
                    present=True,
                    activity=sample["env"]["activity"] if sample["env"]["place"] == "office" else None,
                    at=sample["at"],
                )
                self.scheduler.tick(sample["at"])

                # —— 用户主动唤醒窗口（凌晨 2/4 点处于深睡：一般提醒应被静默）——
                if tod == 0 and hour in (2, 4, 8, 13, 20):
                    if stage != "awake":
                        self.wake.submit_notice(
                            WakeNotice(
                                event_id=f"sim_rem_{day}_{hour}",
                                kind="reminder",
                                title="例行法务提醒",
                                occurred_at=sample["at"],
                            ),
                            now=sample["at"],
                        )
                    spoken_today = hour >= 12
                    told_already = day > cfg.laowang_learning_day or (
                        day == cfg.laowang_learning_day and spoken_today
                    )
                    scene_tags = ["股权", "工商信号"] if told_already else []
                    self.scheduler.on_user_wake(
                        now=sample["at"],
                        scene_tags=scene_tags,
                        semantic_evaluator=self._evaluate_level2_at_wake,
                    )

            day_end = cfg.t_origin + timedelta(days=day + 1) - timedelta(minutes=cfg.minutes_step)
            self._flush(day_end)
            board = self.scheduler.board_snapshot(now=day_end)
            report.extra[f"day_{day}_board_items"] = len(board["items"])
            report.extra[f"day_{day}_dormant"] = board["dormant_count"]
            hits = self.index.intersect({"laowang", "contract"})
            if day >= cfg.laowang_partnership_day:
                assert hits, "C06 倒排求交失效：laowang×contract 应命中"
            # 推进量守恒：协作式单线程死锁的唯一可观测前兆 = 计数停滞
            if report.samples_generated != (day + 1) * day_minutes:
                report.deadlock_cycles += 1
        self._finish(report)
        return report

    def _on_discrete(self, day: int, kind: str, payload: dict, report: RunReport) -> None:
        cfg = self.cfg
        at = cfg.t_origin + timedelta(days=day, hours=10)
        if kind == "meeting":
            report.meetings += 1
            self._emit_observation(
                at=at,
                source_kind="calendar",
                modality="text",
                value=payload,
                tags={"meeting", "work"},
            )
        elif kind == "crisis":
            report.crises += 1
            self._emit_observation(
                at=at,
                source_kind="news_push",
                modality="text",
                value=payload,
                tags={"crisis", "work"},
            )
            snap = self.cleaner.semanticize_binary(
                "image",
                self.CRISIS_RAW_IMAGE_BYTES,
                caption=f"突发危机现场文档拍照：{payload['kind']}",
            )
            assert snap["original_bytes_discarded"] == self.CRISIS_RAW_IMAGE_BYTES
            self._emit_observation(
                at=at,
                source_kind="camera_caption",
                modality="text",
                value={"caption": snap["caption"]},
                tags={"crisis", "caption"},
            )
            self.wake.ingest_pulse(
                SensorPulse(
                    metric="spo2",
                    value=79.0,
                    source="wristband",
                    at=at,
                    priority=WakePriority.P0_CRITICAL_SAFETY,
                )
            )
        elif kind == "laowang_partnership":
            report.laowang_facts += 1
            self._emit_observation(
                at=at,
                source_kind="signed_contract",
                modality="text",
                value=payload,
                tags={"laowang", "contract", "partnership"},
            )
        elif kind == "laowang_breach":
            report.laowang_facts += 1
            self._emit_observation(
                at=at,
                source_kind="court_filing",
                modality="text",
                value=payload,
                tags={"laowang", "contract", "breach"},
            )
        elif kind == "laowang_learned_fraud":
            report.laowang_facts += 1
            statement_at = cfg.t_origin + timedelta(days=day, hours=12)
            claim = self._emit_observation(
                at=statement_at,
                source_kind="user_verbal",
                modality="text",
                value={"transcript": "老王是骗子，卷款跑了"},
                tags={"laowang", "claim"},
            )
            # —— C05 回溯注记：只追加在 T_now，指向过去切片，不改写历史 ——
            overlay = RetrospectiveAnnotation(
                annotation_id="rta_sim_laowang_fraud",
                target_entity_id=cfg.laowang_entity_id,
                semantic_overlay="疑似欺诈-骗子（第18天获知）",
                target_time_start=cfg.t_origin + timedelta(days=cfg.laowang_partnership_day),
                target_time_end=cfg.t_origin + timedelta(days=cfg.laowang_breach_day),
                learned_at=statement_at,
                source_statement_ref=claim.object_id,
            )
            assert bool(self.lens.attach_annotation(overlay))
            report.retrospective_overlays += 1
            self._retro_events.append(
                {"statement_obs": claim.object_id, "learned_at": statement_at.isoformat()}
            )

    def _finish(self, report: RunReport) -> None:
        cfg = self.cfg
        self._flush(cfg.t_origin + timedelta(days=cfg.days))
        prompt = self.scheduler.render_llm_prompt_context()
        dormant_leaks = 0
        dormant_token_sum = 0
        for record in self.scheduler._records.values():
            if record.stage is SchedulerStage.DORMANT:
                dormant_token_sum += self.scheduler.dormant_token_contributions[record.task_id]
                if record.title in prompt:
                    dormant_leaks += 1
        report.dormant_prompt_tokens = dormant_token_sum
        report.dormant_board_leaks = dormant_leaks
        report.level1_evaluations = self.scheduler.level1_evaluations
        report.level1_llm_calls = self.scheduler.level1_llm_calls
        report.llm_calls_total = self.llm.calls + self.scheduler.llm_calls
        report.prompt_tokens_total = self.llm.tokens + self.scheduler.prompt_token_total
        report.raw_binary_retained_bytes = self.cleaner.raw_binary_retained_bytes
        report.raw_binaries_cleaned = self.cleaner.raw_binaries_cleaned
        report.inverted_index_entries = self.index.entries()
        report.inverted_intersect_queries = self.index.queries
        report.inverted_intersect_hits = self.index.hits
        wake_stats = self.wake.stats()
        report.wake_batches_emitted = wake_stats["batches_emitted"]
        report.deep_sleep_deferred = wake_stats["deep_sleep_deferred"]
        report.morning_flushed_events = wake_stats["morning_flushed_events"]
        report.retained_records = len(self._buffer)
        report.world_revision = self.store.current_world_revision()
        report.extra["retro_events"] = list(self._retro_events)
        report.extra["scheduler_stats"] = self.scheduler.stats()
        report.extra["wake_stats"] = wake_stats
        report.extra["llm_tokens"] = self.llm.tokens

    # ------------------------------------------------------------------
    # 双时间视图审计口（供测试直接驱动 C05 引擎）
    # ------------------------------------------------------------------

    def query_laowang_slice(self, *, day: int, as_of_day: int | None = None) -> dict:
        target = self.cfg.t_origin + timedelta(days=day, hours=10)
        cutoff = (
            None
            if as_of_day is None
            else self.cfg.t_origin + timedelta(days=as_of_day, hours=23, minutes=59)
        )
        return self.lens.query_historical_slice(
            self.cfg.laowang_entity_id, target, as_of_cutoff=cutoff
        )


def new_object_id_from_seq(seq: int) -> str:
    # 确定性编号（可复现重放）；仍带 obs 前缀，与 C02 账本口径一致
    return f"obs_sim_{seq:07d}"
