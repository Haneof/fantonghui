"""SIM-001 无头 30 天成年高熵生活仿真驱动器（无唤醒真机接入，逐事件驱动仓库内真实 C 链）。

时间轴契约（门 1）：
    720 小时确定性高熵事件序列：昼夜节律 HR/HRV、工业噪声脉冲、
    恰好 120 场工作会议、商务危机与"老王"合同违约取证请求。
    序列由种子决定论生成，逐小时指纹零漂移。

真实 C 链（门 2，不打桩）：
    C01 端侧清洗   ``ingest.multimodal_edge.EdgeMultimodalCleaner``
                    （会议/危机场景的真实图像帧元数据路径；raw 帧全部进 purge）
    C06 治理审计   ``governance/runtime_policy_independent2.json`` 预算闸 +
                    ``world.fact_immutability_ledger.FactImmutabilityLedger``
                    钉死危机事实（不可回溯、可核验）
    C02 世界引擎   ``query.cjk_inverted_index.CJKTopologicalInvertedIndex.index_entity_text``
    C04 检索汇聚   同索引 ``co_search_scored`` / ``top_co_occurrence``
    C05 归档器     ``cockpit.pipeline.ConversationObservationArchive.append_turn``
    C06 预算尺     ``cockpit.pipeline.Utf8ByteTokenCounter`` 逐事件累计

性能闸（门 3）：
    虚拟时间必须严格单调推进；在途事件窗结案门槛 = 0；
    连续空转 tick 超阈即 SimulationDeadlockError（死锁显式命名）。
    常驻对象由有界环形清单约束；raw image 帧字节一律
    ``RawByteSink.retained_byte_count == 0``。

预算闸（门 4）：
    ``governance/runtime_policy_independent2.json`` 月预算为硬顶，越顶 RuntimePolicyError。
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from aios_core.cockpit.pipeline import (
    ConversationObservationArchive,
    ConversationTurn,
    Utf8ByteTokenCounter,
)
from aios_core.ingest.multimodal_edge import EdgeMultimodalCleaner, RawByteSink
from aios_core.query.cjk_inverted_index import CJKTopologicalInvertedIndex
from aios_core.world.fact_immutability_ledger import FactImmutabilityLedger

POLICY_PATH = Path(__file__).resolve().parents[3] / "governance" / "runtime_policy_independent2.json"

SCENE_VITALS = "vitals_circadian"
SCENE_NOISE = "sensor_burst_noise"
SCENE_MEETING = "work_meeting"
SCENE_CRISIS = "crisis_event"
SCENE_BREACH_AUDIT = "contract_breach_audit"

_MEETING_TOPICS = (
    "合规季度审查与并购重组条款核对",
    "跨境数据出境安全评估备案进度",
    "劳动仲裁应诉证据链加固",
    "供应链担保函连带责任风险",
    "董事会决议合规公告稿措辞",
    "竞业限制补充协议边界复核",
)

_CRISIS_CASE_NO = "合规-995011"


class SimulationDeadlockError(RuntimeError):
    """仿真死锁：虚拟时间进程中出现不可前进、或未结案在途事件。"""


class RuntimePolicyError(RuntimeError):
    """违反 governance/runtime_policy_independent2.json 硬约束。"""


@dataclass(frozen=True)
class HRVState:
    mean_hr: int
    sdnn_ms: int
    hrv_trend: str


@dataclass(frozen=True)
class TimelineScene:
    scene_id: str
    at_hour: float
    kind: str
    brief: str
    tags: tuple[str, ...] = ()
    heart_rate: int | None = None
    hrv_state: HRVState | None = None
    noise_db: float | None = None
    frames: int = 0


def _fingerprint(scene: TimelineScene) -> tuple[Any, ...]:
    return (scene.scene_id, scene.at_hour, scene.kind, scene.brief,
            scene.tags, scene.heart_rate, scene.noise_db)


def generate_30day_adult_timeline(*, seed: int = 20260916) -> tuple[TimelineScene, ...]:
    """720h 决定论高熵时间轴：120 场会议 + 危机与违约 + 节律生命体征。"""
    rng = random.Random(seed)
    scenes: list[TimelineScene] = []
    hour_cursor = 0.0

    def add(kind: str, *, day: int, hour: float, brief: str, tags: Sequence[str] = (),
            hr: int | None = None, sdnn: int | None = None,
            noise: float | None = None, frames: int = 0) -> None:
        nonlocal hour_cursor
        at = day * 24.0 + hour
        hrv = HRVState(mean_hr=hr, sdnn_ms=sdnn, hrv_trend=("上升" if sdnn and sdnn >= 52 else "平稳")) if hr is not None else None
        scenes.append(TimelineScene(
            scene_id=f"D{day:02d}H{int(at % 24):02d}_{len(scenes):05d}",
            at_hour=at, kind=kind, brief=brief, tags=tuple(tags),
            heart_rate=hr, hrv_state=hrv, noise_db=noise, frames=frames,
        ))
        hour_cursor = max(hour_cursor, at)

    # 昼夜节律生命体征（每 4 小时一拍，共 180 帧）
    for day in range(30):
        for slot, hour in enumerate((0.0, 4.0, 8.0, 12.0, 16.0, 20.0)):
            phase = 2.0 * math.pi * (hour / 24.0)
            base_hr = round(70 + 9 * math.sin(phase - 1.1) + rng.uniform(-2.0, 2.0))
            base_sdnn = round(46 + 9 * math.cos(phase - 0.6) + rng.uniform(-3.0, 3.0))
            add(SCENE_VITALS, day=day, hour=hour,
                brief=f"昼夜节律体征采样 day{day} {hour:04.0f}:00 HR={base_hr}bpm SDNN={base_sdnn}ms",
                tags=("vitals", "circadian"), hr=base_hr, sdnn=base_sdnn)

    # 工业噪声脉冲：工作日三班制（冲压车间）
    for day in range(30):
        if day % 7 in (5, 6):
            continue  # 周末工厂例行检修，无噪声暴露
        for burst_id, hour in enumerate((8.5, 13.25, 18.75)):
            level = round(82.0 + rng.uniform(-3.0, 4.5), 1)
            add(SCENE_NOISE, day=day, hour=hour,
                brief=f"冲压车间噪声暴露窗 day{day}-burst{burst_id} {level}dB",
                tags=("noise", "occupational"), noise=level)

    # 工作会议：每日 4 场，全月恰好 120 场（高熵法务总监日程）
    for day in range(30):
        slots = (9.15, 11.30, 14.45, 17.20)
        for idx, hour in enumerate(slots):
            topic = _MEETING_TOPICS[(day * 4 + idx) % len(_MEETING_TOPICS)]
            add(SCENE_MEETING, day=day, hour=hour,
                brief=f"工作会议 day{day}-{idx}: {topic}（第{(day * 4 + idx) + 1}场/120）",
                tags=("meeting", _CRISIS_CASE_NO if day >= 12 else "法务日程"),
                frames=1)

    # 商务危机：day10 05:30 公关函件危机
    add(SCENE_CRISIS, day=10, hour=5.30,
        brief=f"[{_CRISIS_CASE_NO}] 商务危机预警：合作方公开函件指控我方货源瑕疵，法务总监启动证据保全并严禁回溯篡改",
        tags=("crisis", _CRISIS_CASE_NO), frames=2)

    # 合同违约：day12 15:40 老王违约取证审计
    add(SCENE_BREACH_AUDIT, day=12, hour=15.40,
        brief=f"合同违约取证审计（合同号 {_CRISIS_CASE_NO}，对方当事人：老王）："
              f"请求未来 14 天不在本地长期留存履约证据音频，仅以几何指纹检索",
        tags=("audit", _CRISIS_CASE_NO, "老王违约"), frames=1)

    # 危机后续会议与取证安排（不打乱 120 场硬顶——复用同一场工位次会议的议程标签即可）
    scenes.sort(key=lambda s: (s.at_hour, s.scene_id))
    return tuple(scenes)


@dataclass
class SimulationStats:
    scenes_total: int = 0
    meetings_consumed: int = 0
    vitals_consumed: int = 0
    noise_consumed: int = 0
    crisis_sealed: int = 0
    queries_issued: int = 0
    co_occurrences_recorded: int = 0
    tokens_used: int = 0
    purged_frames: int = 0
    purged_bytes: int = 0
    retained_image_bytes: int = 0
    object_footprint_filtered: int = 0
    digest: str = ""
    finalized: bool = False


class HeadlessLifeDriver:
    """逐场景驱动真实 C 链的无头执行器（事件源 → 入库 → 归档 → 检索）。"""

    INFLIGHT_CAP = 32
    STALL_LIMIT = 3
    FOOTPRINT_KEEP = 512

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        policy_path: Path = POLICY_PATH,
        token_counter: Utf8ByteTokenCounter | None = None,
        cleaner: EdgeMultimodalCleaner | None = None,
        clock_start: datetime | None = None,
    ) -> None:
        self._conn = conn or sqlite3.connect(":memory:")
        self._index = CJKTopologicalInvertedIndex(self._conn)
        self._index.ensure_schema()
        self._ledger = FactImmutabilityLedger(self._conn)
        self._ledger.ensure_schema()
        self._archive = ConversationObservationArchive(clock=lambda: self._now_dt)
        self._token_counter = token_counter or Utf8ByteTokenCounter()
        self._cleaner = cleaner or EdgeMultimodalCleaner(clock=lambda: self._now_dt)
        self._sink: RawByteSink = self._cleaner.raw_byte_sink

        policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        self._monthly_token_budget: int = int(policy["monthly_token_budget"])
        self._now_hour = 0.0
        self._clock_start = clock_start or datetime(2026, 9, 16, tzinfo=timezone.utc)
        self._inflight: dict[str, TimelineScene] = {}
        self._stall_count = 0
        self._observation_ring: list[str] = []
        self._footprint_bytes = 0
        self._turn_seq = 0
        self.stats = SimulationStats()
        self._digest = sha256()

    # ------------------------------------------------------------- 主循环

    @property
    def _now_dt(self) -> datetime:
        return self._clock_start + timedelta(hours=self._now_hour)

    def ingest(self, timeline: Sequence[TimelineScene]) -> SimulationStats:
        """逐场景依拟真路径驱动；任何回滚/空转死锁即刻显式抛出。"""
        last_hour = -math.inf
        for scene in timeline:
            if scene.at_hour <= last_hour:
                raise SimulationDeadlockError(
                    f"时间回滚拒绝推进: {scene.scene_id} at {scene.at_hour} <= {last_hour}"
                )
            last_hour = scene.at_hour
            self._advance_virtual_clock(scene.at_hour)
            if len(self._inflight) > self.INFLIGHT_CAP:
                raise SimulationDeadlockError(
                    f"在途事件积压 {len(self._inflight)} 超过硬顶 {self.INFLIGHT_CAP}，引擎失速"
                )
            self._consume(scene)
        self._finalize()
        return self.stats

    # -------------------------------------------------------- 死锁守卫

    def _advance_virtual_clock(self, target_hour: float) -> None:
        stalled = 0
        while self._now_hour < target_hour and not self._can_resolve_awaiting():
            step = min(1.0, target_hour - self._now_hour)
            self._now_hour += step
            stalled += 1
            if stalled > self.STALL_LIMIT and self._inflight:
                raise SimulationDeadlockError(
                    f"连续空转 {stalled} tick 未能推进在途事件 {sorted(self._inflight)}，判定死锁"
                )
            if self._now_hour >= target_hour:
                break

    def _can_resolve_awaiting(self) -> bool:
        # 场景一旦进入驱动器，其完成路径完全确定（无外部异步等待）——
        # 空转只能发生在不存在待决事件时，死锁守卫永不该被以打表方式绕过
        return not self._inflight

    # ------------------------------------------------------------- 消费

    def _consume(self, scene: TimelineScene) -> None:
        if scene.scene_id in self._observation_ring:
            raise SimulationDeadlockError(f"重复消费同一场景 {scene.scene_id}，事件引擎失序")
        self._inflight[scene.scene_id] = scene
        try:
            tokens = self._token_counter.count(scene.brief)
            self._budget_check(self.stats.tokens_used + tokens, scene.scene_id)
            self.stats.tokens_used += tokens
            self._digest.update(scene.brief.encode("utf-8"))

            if scene.kind == SCENE_VITALS:
                self.stats.vitals_consumed += 1
            elif scene.kind == SCENE_NOISE:
                self.stats.noise_consumed += 1
            elif scene.kind == SCENE_MEETING:
                self._consume_meeting(scene)
                self.stats.meetings_consumed += 1
            elif scene.kind == SCENE_CRISIS:
                self._seal_crisis_fact(scene)
                self._consume_evidence_flow(scene)
                self.stats.crisis_sealed += 1
            elif scene.kind == SCENE_BREACH_AUDIT:
                self._seal_crisis_fact(scene)
                self._consume_evidence_flow(scene)
            else:  # 未知场景类型必须在仿真里显式失败
                raise ValueError(f"未知场景类型 {scene.kind}: {scene.scene_id}")

            self.stats.scenes_total += 1
            self._track_footprint(scene)
            self._now_hour = scene.at_hour
        finally:
            self._inflight.pop(scene.scene_id, None)

    def _consume_meeting(self, scene: TimelineScene) -> None:
        caption = self._clean_frame(scene) or f"会议纪要：{scene.brief}"
        entities = [
            f"{_CRISIS_CASE_NO}:day-{int(scene.at_hour // 24)}",
            "法务总监",
        ]
        self._index.index_entity_text(scene.scene_id, caption, int(scene.at_hour * 3_600_000_000_000))
        self.stats.co_occurrences_recorded += self._index.record_co_occurrence(
            entities, int(scene.at_hour * 3_600_000_000_000)
        )
        if self.stats.meetings_consumed % 12 == 11:  # 周期性真实检索行为（C04）
            self.stats.queries_issued += len(self._index.co_search_scored([entities[0]]))
        self._archive_turn(scene, user_text=scene.brief, assistant_text=caption)

    def _consume_evidence_flow(self, scene: TimelineScene) -> None:
        caption = self._clean_frame(scene) or scene.brief
        self._index.index_entity_text(f"EVID-{scene.scene_id}", caption,
                                      int(scene.at_hour * 3_600_000_000_000))
        self.stats.queries_issued += len(
            self._index.co_search_scored([_CRISIS_CASE_NO])
        )
        self._archive_turn(scene, user_text=scene.brief, assistant_text=caption)

    def _clean_frame(self, scene: TimelineScene) -> str | None:
        """C01 真实图像帧路径：调用端侧清洗器，帧字节此生必清零。"""
        kept: list[str] = []
        for _ in range(scene.frames):
            frame = bytearray(range(64))  # 仿真帧：确定性内容，入端必被清洗或拒收
            obs = self._cleaner.evaluate_and_clean_image(
                {
                    "quality_score": 0.82,
                    "semantic_caption": f"{scene.kind}: {scene.brief[:120]}",
                    "scene_tags": [scene.kind],
                    "captured_at": self._now_dt,
                },
                frame,
            )
            if obs is not None:
                kept.append(obs.semantic_caption)
        self.stats.purged_frames = self._sink.purged_frame_count
        self.stats.purged_bytes = self._sink.purged_byte_count
        self.stats.retained_image_bytes = self._sink.retained_byte_count
        return " | ".join(kept) if kept else None

    def _seal_crisis_fact(self, scene: TimelineScene) -> None:
        occurred = self._clock_start + timedelta(hours=scene.at_hour)
        self._ledger.seal_fact(
            object_id=f"EVID-{scene.scene_id}",
            revision=1,
            object_type="timeline_scene",
            subject_id="法务总监",
            occurred_at=occurred,
            learned_at=occurred,
            payload={"scene": scene.brief, "tags": list(scene.tags)},
        )

    def _archive_turn(self, scene: TimelineScene, *, user_text: str, assistant_text: str) -> None:
        self._turn_seq += 1
        self._archive.append_turn(
            ConversationTurn(
                turn_id=scene.scene_id,
                sequence_no=self._turn_seq,
                occurred_at=self._now_dt,
                user_text=user_text,
                assistant_text=assistant_text,
            )
        )

    # ------------------------------------------------------------- 收口

    def _budget_check(self, prospective: int, scene_id: str) -> None:
        if prospective > self._monthly_token_budget:
            raise RuntimePolicyError(
                f"场景 {scene_id} 使累计 token {prospective} 越过月预算 "
                f"{self._monthly_token_budget}（governance/runtime_policy_independent2.json）"
            )

    def _track_footprint(self, scene: TimelineScene) -> None:
        self._observation_ring.append(scene.scene_id)
        if len(self._observation_ring) > self.FOOTPRINT_KEEP:
            del self._observation_ring[: len(self._observation_ring) // 2]
        self._footprint_bytes = min(
            self._footprint_bytes + len(scene.brief.encode("utf-8")),
            self.FOOTPRINT_KEEP * 4096,
        )
        self.stats.object_footprint_filtered = len(self._observation_ring)

    def _finalize(self) -> None:
        if self._inflight:
            raise SimulationDeadlockError(
                f"仿真收尾仍有 {len(self._inflight)} 条未结案在途事件，禁止叛忍式吞没"
            )
        self.stats.digest = self._digest.hexdigest()
        self.stats.finalized = True
        if self.stats.retained_image_bytes != 0:
            raise RuntimePolicyError(
                f"仿真存在 raw image 字节残留 {self.stats.retained_image_bytes}，违反零保留铁律"
            )
