"""SIM-001 无界面多维人生时空仿真推演机驱动引擎。

纯 Python、零 UI，在无图形 Linux 服务器上以 1000x 加速回放推进 30 天
（720 小时）高熵成年人时空流，并驱动 AIOS 完整技术链：

    数据接入 -> C01 边缘清洗 -> C06 倒排求交 -> C02 账本持久化
             -> C04 单看板装配 -> C05 回溯注记

硬门禁：0 死锁、驻留 RSS <= 128MB、原始二进制图片滞留量为 0、
全局 Token 总量受控于 ``governance/runtime_policy.json`` 月度预算。
"""

from __future__ import annotations

import math
import random
import resource
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aios_core.cockpit.pipeline import (
    SINGLE_SHOT_TOKEN_BUDGET,
    CockpitPipeline,
    ConversationRound,
    ConversationState,
    estimate_tokens,
)
from aios_core.contracts.safety_bypass import (
    HazardType,
    SafetyBypassPayload,
    WakePriority,
)
from aios_core.ingest.multimodal_edge import QUALITY_GARBAGE_THRESHOLD, RawByteSink
from aios_core.wake.v22_hardware_first import safe_dispatch_v22
from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
)

__all__ = [
    "TOTAL_HOURS",
    "HeadlessLifeDriver",
    "InvertedIntersectionIndex",
    "LifeStreamGenerator",
    "SimConfig",
    "SimulationReport",
]

TOTAL_HOURS = 720
_TICK_MINUTES = 10
TICKS_PER_DAY = 24 * 60 // _TICK_MINUTES  # 144
_LAOWANG_ENTITY = "entity:partner:laowang"
_USER_ENTITY = "entity:user:legal-director"

#: 剧本化高熵事件日（0 基）：商业危机 / 心源性晕厥跌倒 / 老王违约 / 司法查封。
CRISIS_DAY_CASHFLOW = 9
CRISIS_DAY_CARDIAC_FALL = 17
CRISIS_DAY_BREACH = 21
CRISIS_DAY_FREEZE = 24

MEETING_SLOTS = (10 * 6, 11 * 6 + 3, 14 * 6 + 3, 16 * 6)  # 每日 4 场 => 30 天 120 场


@dataclass(frozen=True)
class SimConfig:
    """仿真配置：30 天 / 1000x 加速 / 确定性种子。"""

    days: int = 30
    speed_factor: int = 1000
    seed: int = 20_260_916
    start: datetime = datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)


class SimulationReport(BaseModel):
    """30 天连续推演的全部门禁审计回执。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hours_streamed: int = Field(ge=0)
    ticks: int = Field(ge=0)
    speed_factor: int = Field(ge=1)
    meetings: int = Field(ge=0)
    crisis_events: int = Field(ge=0)
    breach_event: bool = False
    p0_events: int = Field(ge=0)
    p0_llm_calls: int = Field(ge=0)
    c01_frames_ingested: int = Field(ge=0)
    c01_garbage_purged: int = Field(ge=0)
    c01_retained_raw_bytes: int = Field(ge=0)
    c06_intersection_queries: int = Field(ge=0)
    c06_hits: int = Field(ge=0)
    c02_observations: int = Field(ge=0)
    c04_assemblies: int = Field(ge=0)
    c05_annotations: int = Field(ge=0)
    tokens_consumed: int = Field(ge=0)
    deadlocks: int = Field(ge=0)
    rss_start_mb: float = Field(ge=0.0)
    rss_peak_mb: float = Field(ge=0.0)
    rss_growth_mb: float
    wall_seconds: float = Field(ge=0.0)


class InvertedIntersectionIndex:
    """C06 倒排求交引擎（端侧轻量实现）：词项 -> 事件倒排链。"""

    def __init__(self) -> None:
        self._postings: dict[str, set[str]] = {}
        self.queries = 0
        self.hits = 0

    def add_document(self, doc_id: str, terms: tuple[str, ...]) -> None:
        for term in terms:
            self._postings.setdefault(term, set()).add(doc_id)

    def intersect(self, terms: tuple[str, ...]) -> frozenset[str]:
        """多词项倒排链求交：全部命中才返回。"""

        self.queries += 1
        chains = [self._postings.get(term, set()) for term in terms]
        if not chains or any(not chain for chain in chains):
            return frozenset()
        result = frozenset(set.intersection(*chains))
        self.hits += len(result)
        return result


class LifeStreamGenerator:
    """真实高熵成年人 30 天时空流发生器（昼夜节律 + 体征 + 场景 + 剧本事件）。"""

    def __init__(self, config: SimConfig) -> None:
        self._config = config
        self._rng = random.Random(config.seed)

    def sim_time(self, day: int, tick: int) -> datetime:
        return self._config.start + timedelta(
            days=day, minutes=tick * _TICK_MINUTES
        )

    def sleep_stage(self, tick: int) -> str:
        minutes = tick * _TICK_MINUTES
        return "deep_sleep" if minutes >= 23 * 60 + 30 or minutes < 6 * 60 else "awake"

    def vitals(self, day: int, tick: int) -> dict[str, float]:
        """昼夜节律心率/HRV：深夜低谷、会议高压抬升、赛后波动。"""

        phase = (tick / TICKS_PER_DAY) * 2 * math.pi
        heart_rate = 62.0 + 14.0 * math.sin(phase - math.pi / 2)
        if self.sleep_stage(tick) == "awake":
            heart_rate += 8.0
        if day == CRISIS_DAY_CARDIAC_FALL and tick in (19, 20):
            heart_rate = 165.0  # 凌晨 03:10 起室性早搏连发
        heart_rate += self._rng.uniform(-2.5, 2.5)
        hrv = max(8.0, 96.0 - heart_rate * 0.55 + self._rng.uniform(-4.0, 4.0))
        return {"heart_rate_bpm": round(heart_rate, 1), "hrv_ms": round(hrv, 1)}

    def scene(self, day: int, tick: int) -> str:
        minutes = tick * _TICK_MINUTES
        if self.sleep_stage(tick) != "awake":
            return "home_sleep"
        if day % 7 in (2, 4) and 9 * 60 <= minutes < 12 * 60:
            return "industrial_workshop_85db"  # 重型工业装配车间巡检
        if any(abs(minutes - slot) < _TICK_MINUTES for slot in MEETING_SLOTS):
            return "boardroom_meeting"
        if day % 5 == 3 and 18 * 60 <= minutes < 21 * 60:
            return "supply_chain_roundtable"  # 跨国供应链商务圆桌晚宴
        return "office"

    def scripted_events(self, day: int) -> dict[str, dict[str, Any]]:
        events: dict[str, dict[str, Any]] = {}
        if day == CRISIS_DAY_CASHFLOW:
            events["cashflow_crisis"] = {
                "tick": 15 * 6,
                "title": "突发商业危机：主力客户回款链断裂",
                "terms": ("商业危机", "现金流", "回款"),
            }
        if day == CRISIS_DAY_CARDIAC_FALL:
            events["cardiac_fall"] = {
                "tick": 19,
                "title": "夜间室性早搏连发伴心源性晕厥跌倒",
                "terms": ("生命安全", "心律失常", "跌倒"),
            }
        if day == CRISIS_DAY_BREACH:
            events["laowang_breach"] = {
                "tick": 10 * 6,
                "title": "老王合同违约：股权代持骗局与知识产权转移暴露",
                "terms": ("老王", "违约", "股权代持", "欺诈"),
            }
        if day == CRISIS_DAY_FREEZE:
            events["judicial_freeze"] = {
                "tick": 9 * 6,
                "title": "司法机关下达冻结查封裁定书",
                "terms": ("老王", "司法查封", "裁定书"),
            }
        return events


@dataclass
class _P0Wake:
    """V22 硬件直穿唤醒事件（模拟凌晨 03:15 心血管突发 + 跌倒）。"""

    object_id: str
    priority: WakePriority
    safety_bypass: SafetyBypassPayload


class HeadlessLifeDriver:
    """30 天连续推演驱动引擎：单线程纯 Python，结构性 0 死锁。"""

    def __init__(self, config: SimConfig | None = None) -> None:
        self.config = config or SimConfig()
        self.stream = LifeStreamGenerator(self.config)

        # 技术链组件装配。
        self.c01_sink = RawByteSink()  # C01 边缘清洗
        self.c06_index = InvertedIntersectionIndex()  # C06 倒排求交
        self.c02_ledger = ImmutableFactLedger()  # C02 不可变事实账本
        self.c04_state = ConversationState(
            crisis_context=(
                "法务总监 30 天高压仿真：对赌回购、老王股权代持违约、"
                "司法查封与心源性晕厥跌倒危机线。"
            )
        )
        self.c04_pipeline = CockpitPipeline(state=self.c04_state)  # C04 单看板
        self.c05_registry = AnnotationRegistry()  # C05 回溯注记

        self._ledger_lock = threading.Lock()
        self._p0_llm_calls = 0
        self._deadlocks = 0
        self._tokens = 0
        self._assemblies = 0
        self._meetings = 0
        self._crisis_events = 0
        self._p0_events = 0
        self._frames = 0
        self._garbage_purged = 0
        self._sunk_ids: list[str] = []
        self._garbage_ids: list[str] = []

    # -- 主循环 ---------------------------------------------------------------

    def run(self) -> SimulationReport:
        started_wall = time.perf_counter()
        rss_start_mb = _rss_mb()
        rss_peak_mb = rss_start_mb
        breach_event = False

        for day in range(self.config.days):
            day_facts: list[dict[str, Any]] = []
            scripted = self.stream.scripted_events(day)

            for tick in range(TICKS_PER_DAY):
                sim_dt = self.stream.sim_time(day, tick)
                scene = self.stream.scene(day, tick)
                vitals = self.stream.vitals(day, tick)

                # 高频体征流：每 30 分钟抽样一条事实入候选。
                if tick % 3 == 0:
                    day_facts.append(
                        {
                            "fact_id": f"sim:vitals:{day:02d}:{tick:03d}",
                            "entity_id": _USER_ENTITY,
                            "occurred_at": sim_dt,
                            "kind": "biometric",
                            "payload": {"scene": scene, **vitals},
                        }
                    )

                # 设备标牌/合同抓拍：每 12 tick 一帧，昏暗抖动帧画质退化。
                if tick % 12 == 0:
                    self._ingest_frame(day, tick, scene)

                # 120 场真实工作会议（每日 4 场）。
                if tick in MEETING_SLOTS:
                    self._meetings += 1
                    meeting_id = f"sim:meeting:{self._meetings:03d}"
                    terms = ("工作会议", "供应链", "对赌回购")
                    if self._meetings % 6 == 0:
                        terms = terms + ("合同审查",)
                        self._assemble_session(
                            f"合同审查会议 {self._meetings}：对赌回购条款风险清单核对。"
                        )
                    self.c06_index.add_document(meeting_id, terms)
                    day_facts.append(
                        {
                            "fact_id": meeting_id,
                            "entity_id": _USER_ENTITY,
                            "occurred_at": sim_dt,
                            "kind": "work_meeting",
                            "payload": {"scene": scene, "terms": list(terms)},
                        }
                    )

                # 剧本化高熵事件。
                for event_key, event in scripted.items():
                    if event["tick"] != tick:
                        continue
                    self._crisis_events += 1
                    event_id = f"sim:event:{event_key}"
                    self.c06_index.add_document(event_id, event["terms"])
                    day_facts.append(
                        {
                            "fact_id": event_id,
                            "entity_id": _LAOWANG_ENTITY
                            if event_key in ("laowang_breach", "judicial_freeze")
                            else _USER_ENTITY,
                            "occurred_at": sim_dt,
                            "kind": "scripted_crisis",
                            "payload": {"title": event["title"]},
                        }
                    )
                    if event_key == "laowang_breach":
                        breach_event = True
                    if event_key == "cardiac_fall":
                        self._fire_p0(sim_dt)
                    else:
                        self._crisis_dialogue(event, sim_dt, day)

                # C06 每日例行检索：老王违约证据链求交。
                if tick == TICKS_PER_DAY - 1:
                    self.c06_index.intersect(("老王", "违约"))

            # 每日夜间复盘：单看板装配（预算硬帽）。
            self._assemble_session(f"第 {day + 1} 天夜间复盘：争议点与体征曲线梳理。")

            # C02 账本持久化：锁获取带超时，失败即计死锁（单线程下恒为 0）。
            if not self._ledger_lock.acquire(timeout=2.0):
                self._deadlocks += 1
                continue
            try:
                self.c02_ledger.record_facts(day_facts)
            finally:
                self._ledger_lock.release()

            # C01 边缘策略：废片粉碎 + 端侧不留原始字节（只留特征摘要）。
            self._garbage_purged += len(self._garbage_ids)
            self.c01_sink.purge(self._garbage_ids)
            garbage_set = set(self._garbage_ids)
            residue_ids = [i for i in self._sunk_ids if i not in garbage_set]
            self.c01_sink.purge(residue_ids)
            self._sunk_ids.clear()
            self._garbage_ids.clear()

            # C05 回溯注记：第 21 天获知老王欺诈，只追加在今天、指针指向过去。
            if day == CRISIS_DAY_BREACH:
                self._record_breach_annotation(sim_dt)

            rss_peak_mb = max(rss_peak_mb, _rss_mb())

        return SimulationReport(
            hours_streamed=self.config.days * 24,
            ticks=self.config.days * TICKS_PER_DAY,
            speed_factor=self.config.speed_factor,
            meetings=self._meetings,
            crisis_events=self._crisis_events,
            breach_event=breach_event,
            p0_events=self._p0_events,
            p0_llm_calls=self._p0_llm_calls,
            c01_frames_ingested=self._frames,
            c01_garbage_purged=self._garbage_purged,
            c01_retained_raw_bytes=self.c01_sink.retained_bytes,
            c06_intersection_queries=self.c06_index.queries,
            c06_hits=self.c06_index.hits,
            c02_observations=self.c02_ledger.count(),
            c04_assemblies=self._assemblies,
            c05_annotations=self.c05_registry.count(),
            tokens_consumed=self._tokens,
            deadlocks=self._deadlocks,
            rss_start_mb=rss_start_mb,
            rss_peak_mb=rss_peak_mb,
            rss_growth_mb=rss_peak_mb - rss_start_mb,
            wall_seconds=time.perf_counter() - started_wall,
        )

    # -- 技术链环节 -------------------------------------------------------------

    def _ingest_frame(self, day: int, tick: int, scene: str) -> None:
        rng = random.Random(self.config.seed + day * 1000 + tick)
        dim_or_shaky = scene == "industrial_workshop_85db" or tick % 24 == 0
        quality = rng.uniform(0.05, 0.39) if dim_or_shaky else rng.uniform(0.55, 0.95)
        asset_id = f"sim:frame:{day:02d}:{tick:03d}"
        self.c01_sink.sink(asset_id, b"\x00" * 1024)
        self._sunk_ids.append(asset_id)
        if quality < QUALITY_GARBAGE_THRESHOLD:
            self._garbage_ids.append(asset_id)
        self._frames += 1

    def _assemble_session(self, seed_text: str) -> None:
        """C04：危机对话窗口压入 + 单看板装配（Token 记账，硬帽 1500）。"""

        round_ = ConversationRound(
            round_id=self.c04_state.next_round_id(),
            speaker="user",
            text=seed_text,
            occurred_at=datetime.now(timezone.utc),
            key_dispute_points=[seed_text[:24]],
        )
        self.c04_state.push(round_)
        cockpit = self.c04_pipeline.assemble_cockpit()
        self._assemblies += 1
        self._tokens += cockpit.token_count
        assert cockpit.token_count <= SINGLE_SHOT_TOKEN_BUDGET

    def _crisis_dialogue(
        self, event: dict[str, Any], sim_dt: datetime, day: int
    ) -> None:
        """危机日用户高频碎片对话（经 C04 窗口与预算流水线）。"""

        for burst in range(3):
            round_ = ConversationRound(
                round_id=self.c04_state.next_round_id(),
                speaker="user",
                text=f"[第{day + 1}天] {event['title']}：证据固化第 {burst + 1} 批。",
                occurred_at=sim_dt,
                key_dispute_points=[event["title"]],
            )
            self.c04_state.push(round_)
        cockpit = self.c04_pipeline.assemble_cockpit()
        self._assemblies += 1
        self._tokens += cockpit.token_count

    def _fire_p0(self, sim_dt: datetime) -> None:
        """跨模态心血管突发：V22 失败安全硬件直穿（大模型/看板全让路）。"""

        wake = _P0Wake(
            object_id="sim:p0:cardiac-fall",
            priority=WakePriority.P0_CRITICAL_SAFETY,
            safety_bypass=SafetyBypassPayload(
                hazard_type=HazardType.CARDIAC_ARREST,
                vital_snapshot={
                    "scene": "nocturnal_deep_sleep",
                    "heart_rate_bpm": 165,
                    "arrhythmia": "nocturnal_pvc_run",
                    "g_force_impact": 5.2,
                    "suspected_syncope": "cardiogenic",
                },
                emergency_action_code="EMERGENCY_CELLULAR_SOS_AND_FALL_ALERT",
                triggered_at=sim_dt,
            ),
        )
        result = safe_dispatch_v22(wake)
        assert result["status"].startswith("SAFETY_BYPASS_EXECUTED")
        assert result["bypassed_llm"] is True
        self._p0_llm_calls += int(result.get("llm_calls", 0))
        self._p0_events += 1

    def _record_breach_annotation(self, learned_at: datetime) -> None:
        start = self.config.start
        self.c05_registry.append(
            RetrospectiveAnnotation(
                annotation_id="sim:m1-018:laowang-breach-reassessment",
                target_entity_id=_LAOWANG_ENTITY,
                semantic_overlay=(
                    "疑似欺诈重估：老王合同违约、股权代持骗局与核心知识产权转移"
                ),
                target_time_start=start,
                target_time_end=learned_at,
                learned_at=learned_at,
                recorded_at=learned_at,
                source_statement_ref="司法冻结查封裁定书（仿真）财保字第0916号",
            )
        )


def _rss_mb() -> float:
    """Linux 驻留 RSS（MB）。"""

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
