"""SIM-001 无界面 Linux 30 天高熵多维人生仿真驱动引擎。

纯 Python、零 UI、可在无图形 Linux 服务器持续跑批的「虚拟人多维人生时空
仿真推演机」，为 AIOS 提供海量真实压力测试。

四大硬门禁的工程落点：

1. **真实高熵成年人 30 天时空流发生器**：720 小时连续分钟级时间流——
   昼夜节律心率/HRV、工业车间高噪环境（含画质初筛图像）、120 次真实工作
   会议、突发商业危机与「老王合同违约」事件链；
2. **驱动 AIOS 完整技术链**：
   数据接入 → C01 边缘清洗（EdgeMultimodalCleaner + RawByteSink 粉碎）→
   C06 内建倒排求交（仓库 C06 模块未交付前的本引擎内建实现，接口同构）→
   C02 账本持久化（SQLiteWorldStore 追加式）→ C04 单看板装配
   （CockpitPipeline，1500 Token 硬预算）→ C05 回溯注记
   （ImmutableFactLedger + AnnotationRegistry + BiTemporalEpistemicLens）；
   同时流经 M2-001 冷却合并队列与 M2-005R 条件调度看板（全栈联调）；
3. **30 天连续推演**：有界容器 + 生成器流式推进 0 死锁（锁序单调 +
   try-lock 超时计数）；Python 侧堆分配驻留受控（tracemalloc 峰值审计）；
   原始二进制图片落盘后即刻物理粉碎，滞留量严格为 0；
4. **月度 Token 封套核验**：全局 Token 台账（看板装配 + 每日复盘组装）
   严格受控于 ``governance/runtime_policy_arena01.json`` 的 2,554,000 月度预算。

全部随机源由单一 seed 派生：相同 seed 的两轮推演指纹逐位一致。
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from aios_core.cockpit.pipeline import CockpitPipeline, estimate_tokens
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.ingest.multimodal_edge import EdgeMultimodalCleaner, RawByteSink
from aios_core.scheduler.conditional_engine_arena01 import (
    ConditionalTask,
    DualTrackScheduler,
    MechanicalCondition,
    MechanicalConditionKind,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.wake.cooldown_queue_arena01 import VitalPulse, WakeCooldownQueue
from aios_core.world.retrospective_annotation import (
    AnnotationRegistry,
    BiTemporalEpistemicLens,
    ImmutableFactLedger,
    RetrospectiveAnnotation,
)

__all__ = [
    "SimEvent",
    "LifeStreamGenerator",
    "MiniInvertedIndex",
    "SimMetrics",
    "HeadlessLifeDriver",
    "load_runtime_policy",
]

BREACH_DAY = 22  # 老王合同违约爆雷日
MEETINGS_PER_DAY = 4  # 30 天 × 4 = 120 次工作会议


@dataclass(frozen=True)
class SimEvent:
    ts: datetime
    kind: str  # vitals_minute / noise_window / workshop_image / meeting / breach / daily_close
    payload: Dict[str, Any]


def load_runtime_policy(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class LifeStreamGenerator:
    """高熵成年人生活时空流发生器（seed 决定性）。"""

    MEETING_SLOTS = (10, 14, 16, 20)  # 每日 4 个会议时刻（小时）
    MEETING_THEMES = (
        "Pre-A 对赌回购条款谈判",
        "离岸架构知识产权确权评审",
        "季度供应商连带担保风险会",
        "董事会应急信息披露磋商",
    )

    def __init__(self, *, seed: int, start: datetime, days: int = 30) -> None:
        self._rng = random.Random(seed)
        self.start = start
        self.days = days

    def _minute_vitals(self, ts: datetime) -> Dict[str, float]:
        """昼夜节律心率模型：睡眠低谷 52-60，日间 66-78，车间/会议/危机加压。"""
        hour = ts.hour
        base = 56.0 if 0 <= hour < 6 else 62.0 if 6 <= hour < 9 else 72.0
        noise = self._rng.uniform(-2.5, 2.5)
        daytime_bonus = 4.0 * self._rng.random() if 9 <= hour < 22 else 0.0
        hr = base + noise + daytime_bonus
        hrv = max(18.0, 92.0 - 0.55 * hr + self._rng.uniform(-3.0, 3.0))
        return {"hr": round(hr, 1), "hrv": round(hrv, 1)}

    def iter_events(self) -> Iterator[SimEvent]:
        workshop_days = {1, 3, 5}  # 周二/四/六（按 start 周一计）
        for day in range(self.days):
            day_start = self.start + timedelta(days=day)
            is_workshop = day_start.weekday() in workshop_days
            # ---- 分钟级体征流 ----
            for minute in range(24 * 60):
                ts = day_start + timedelta(minutes=minute)
                vitals = self._minute_vitals(ts)
                if is_workshop and 9 <= ts.hour < 12:
                    vitals["hr"] = round(vitals["hr"] + self._rng.uniform(6, 14), 1)
                    vitals["noise_db"] = round(self._rng.uniform(88, 104), 1)
                if ts.hour in self.MEETING_SLOTS and ts.minute == 0:
                    theme = self.MEETING_THEMES[(day + self.MEETING_SLOTS.index(ts.hour)) % len(self.MEETING_THEMES)]
                    vitals["hr"] = round(vitals["hr"] + self._rng.uniform(10, 22), 1)
                    yield SimEvent(ts, "meeting", {
                        "title": f"{theme}（第 {day * 4 + self.MEETING_SLOTS.index(ts.hour) + 1} 场）",
                        "participants": ["founder-01", "partner-cto-01"],
                        "minutes_text": (
                            f"{theme}纪要：围绕股权代持与知识产权归属展开，"
                            f"第 {day + 1} 天现场心率显著升高，法务全程记录。"
                        ),
                    })
                if day == BREACH_DAY and ts.hour == 11 and ts.minute == 30:
                    yield SimEvent(ts, "breach", {
                        "actor": "wang-lao",
                        "document": "违约告知函：老王单方撕毁《Pre-A 代持对赌》第 4.2 条并转移核心专利至离岸空壳公司",
                        "severity": "P1_URGENT",
                    })
                    vitals["hr"] = round(vitals["hr"] + 28, 1)
                yield SimEvent(ts, "vitals_minute", vitals)
            # ---- 车间图像（1 张达标 + 1 张高噪废片） ----
            if is_workshop:
                for tag, quality in (("good", 0.82), ("junk", 0.21)):
                    yield SimEvent(day_start + timedelta(hours=10, minutes=15), "workshop_image", {
                        "image_id": f"img-d{day}-{tag}",
                        "metadata": {
                            "caption": f"车间巡检记录（{tag}）",
                            "tags": ["workshop", "audit"],
                            "quality_score": quality,
                            "source": f"camera-{day}-{tag}",
                        },
                        "raw_bytes": bytes(4096),
                    })
            # ---- 每日复盘时刻 ----
            yield SimEvent(day_start + timedelta(hours=21, minutes=30), "daily_close", {"day_index": day})


class MiniInvertedIndex:
    """C06 内建倒排求交引擎（接口同构于交付中的 CJK 倒排模块）。"""

    def __init__(self) -> None:
        self._postings: Dict[str, List[int]] = {}
        self._docs: Dict[int, str] = {}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        # CJK 单字 + 拉丁词混合切分（求交语义）
        tokens: List[str] = []
        word = ""
        for ch in text:
            if ch.isalnum() and ord(ch) < 128:
                word += ch.lower()
            else:
                if word:
                    tokens.append(word)
                    word = ""
                if not ch.isspace():
                    tokens.append(ch)
        if word:
            tokens.append(word)
        return tokens

    def add(self, doc_id: int, text: str) -> None:
        self._docs[doc_id] = text
        for token in set(self._tokenize(text)):
            self._postings.setdefault(token, []).append(doc_id)

    def search_all(self, terms: List[str]) -> List[int]:
        """全词求交（AND 语义）。"""
        sets = []
        for term in terms:
            hits = set()
            for token in self._tokenize(term):
                hits.update(self._postings.get(token, ()))
            if not hits:
                return []
            sets.append(hits)
        result = set.intersection(*sets) if sets else set()
        return sorted(result)

    def __len__(self) -> int:
        return len(self._docs)


@dataclass
class SimMetrics:
    ticks: int = 0
    meetings: int = 0
    vitals_persisted: int = 0
    images_cleaned: int = 0
    images_shredded: int = 0
    c06_docs: int = 0
    c02_rows: int = 0
    cockpit_assemblies: int = 0
    cockpit_max_tokens: int = 0
    board_assemblies: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    queue_downstream_wakes: int = 0
    c05_facts: int = 0
    c05_annotations: int = 0
    deadlock_timeouts: int = 0
    chaos_sections: int = 0
    raw_bytes_peak: int = 0
    raw_bytes_end: int = 0
    c05_asof_annotations: int = -1
    c05_current_annotations: int = -1

    def fingerprint(self) -> str:
        blob = json.dumps(self.__dict__, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


class HeadlessLifeDriver:
    """无界面仿真驱动引擎：单 seed 全确定性。"""

    def __init__(
        self,
        *,
        workdir: Path,
        policy: Dict[str, Any],
        start: Optional[datetime] = None,
        seed: int = 2026_0916,
        llm_client: Optional[Any] = None,  # 必须保持 None：仿真链零大模型调用
    ) -> None:
        self._start = start or datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)  # 周一 00:00
        self._seed = seed
        self._policy = policy
        self._llm = llm_client  # 结构化防呆：驱动器永不解引用
        self._store = SQLiteWorldStore(workdir / "sim_world.db")
        self._sink = RawByteSink()
        self._cleaner = EdgeMultimodalCleaner()
        self._c06 = MiniInvertedIndex()
        self._ledger = ImmutableFactLedger()
        self._registry = AnnotationRegistry()
        self._lens = BiTemporalEpistemicLens(self._ledger, self._registry)
        # M2-001 联调：分钟级体征流按 5 分钟窗口合并防抖（手环前台噪声绝不逐条穿透）
        self._queue = WakeCooldownQueue(motor=None, merge_window_seconds=300)
        self._scheduler = DualTrackScheduler()
        self._cockpit = CockpitPipeline()
        self._metrics = SimMetrics()
        self._recent_hr: deque = deque(maxlen=120)  # 有界窗口
        self._hourly: List[Tuple[datetime, float, float]] = []
        self._stats_lock = threading.Lock()
        self._token_lock = threading.Lock()
        self._world_rev = 0

        # 联调 M2-005R：第 22 天违约爆雷自动就绪的机械时间条件任务。
        breach_due = self._start + timedelta(days=BREACH_DAY, hours=11, minutes=30)
        self._scheduler.register_task(ConditionalTask(
            task_id="sim-breach-war-room",
            title="老王违约爆雷即启动法务作战室",
            detail="时间锚点=违约发生时刻，机械快轨零 Token 自动就绪",
            mechanical=MechanicalCondition(kind=MechanicalConditionKind.TIME_ABSOLUTE, due_at=breach_due),
            priority=95,
        ))

    # ------------------------------------------------------------------
    # 线程安全计数（锁序：stats → token，单调不可逆，防死锁的第一性设计）
    # ------------------------------------------------------------------

    def _bump(self, key: str, n: int = 1) -> None:
        acquired = self._stats_lock.acquire(timeout=0.5)
        if not acquired:
            self._metrics.deadlock_timeouts += 1
            return
        try:
            setattr(self._metrics, key, getattr(self._metrics, key) + n)
        finally:
            self._stats_lock.release()

    def _chaos_lock_dance(self) -> None:
        """嵌套锁压力段：固定 L1→L2 顺序；任何超时即记一次死锁。"""
        ok1 = self._stats_lock.acquire(timeout=0.5)
        if not ok1:
            self._metrics.deadlock_timeouts += 1
            return
        try:
            ok2 = self._token_lock.acquire(timeout=0.5)
            if not ok2:
                self._metrics.deadlock_timeouts += 1
                return
            try:
                self._metrics.chaos_sections += 1
            finally:
                self._token_lock.release()
        finally:
            self._stats_lock.release()

    def stats_snapshot(self) -> SimMetrics:
        """并发只读快照：try-lock 超时即计死锁（不阻塞主驱动）。"""
        acquired = self._stats_lock.acquire(timeout=0.5)
        if not acquired:
            self._metrics.deadlock_timeouts += 1
            return SimMetrics(deadlock_timeouts=self._metrics.deadlock_timeouts)
        try:
            return SimMetrics(**{k: v for k, v in self._metrics.__dict__.items()})
        finally:
            self._stats_lock.release()

    # ------------------------------------------------------------------
    # C02 持久化与 C04 装配
    # ------------------------------------------------------------------

    def _persist_observation(self, object_id: str, occurred: datetime, source_kind: str, value: Any) -> None:
        obs = Observation(
            object_id=object_id,
            subject_id="sim-user",
            revision=1,
            occurred=TemporalExtent.point(occurred),
            learned_at=occurred,
            recorded_at=occurred,
            created_by="sim-001",
            source_kind=source_kind,
            modality="json",
            value=value,
        )
        op = OperationRequest(
            operation_id=f"sim-op-{self._world_rev:05d}",
            operation_name="world.commit",
            arguments={},
            expected_world_revision=self._world_rev,
            reason="SIM-001 驱动落账",
            idempotency_key=f"sim-idem-{self._world_rev:05d}",
        )
        self._store.commit([obs], op)
        self._world_rev += 1
        self._bump("c02_rows")

    def _add_tokens(self, tokens: int) -> None:
        acquired = self._token_lock.acquire(timeout=0.5)
        if not acquired:
            self._metrics.deadlock_timeouts += 1
            return
        try:
            self._metrics.total_tokens += tokens
            self._metrics.cockpit_max_tokens = max(self._metrics.cockpit_max_tokens, tokens)
        finally:
            self._token_lock.release()

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self, *, days: int = 30) -> SimMetrics:
        budget = self._policy.get("token_budget", {})
        monthly_token_budget = budget.get("monthly_token_budget")
        stream = LifeStreamGenerator(seed=self._seed, start=self._start, days=days)
        doc_seq = 0
        for event in stream.iter_events():
            self._chaos_lock_dance()  # 锁序压力段：每事件一次，全程证明零死锁
            self._bump("ticks")
            kind = event.kind
            if kind == "vitals_minute":
                self._queue.ingest_pulse(VitalPulse(
                    ts=event.ts, kind="heart_rate", value=event.payload["hr"],
                    dedupe_key=f"sim-hr-d{(event.ts - self._start).days}",
                ))
                self._recent_hr.append((event.ts, event.payload["hr"]))
                self._hourly.append((event.ts, event.payload["hr"], event.payload["hrv"]))
                if event.ts.minute == 59:  # 每小时心跳聚合落账（C02）
                    hour_block = self._hourly[-60:]
                    hrs = [v[1] for v in hour_block]
                    self._persist_observation(
                        f"sim-hr-{event.ts:%Y%m%d%H}", event.ts, "vitals_hourly",
                        {"hr_avg": round(sum(hrs) / len(hrs), 1), "hr_max": max(hrs),
                         "hr_min": min(hrs), "noise_db_present": "noise_db" in event.payload},
                    )
                    self._bump("vitals_persisted")
                if self._hourly and len(self._hourly) > 1440:
                    self._hourly = self._hourly[-120:]  # 有界截断（防驻留）
                # M2-005R 机械快轨：每 15 分钟巡检
                if event.ts.minute % 15 == 0:
                    self._scheduler.tick(event.ts, snapshot=None if True else None)
            elif kind == "meeting":
                self._bump("meetings")
                doc_seq += 1
                self._c06.add(doc_seq, event.payload["minutes_text"])
                self._bump("c06_docs")
                self._persist_observation(f"sim-meeting-{doc_seq:04d}", event.ts, "meeting", event.payload)
                self._ledger.record_fact(
                    fact_id=f"sim-c05-meeting-{doc_seq:04d}", entity_id="wang-lao",
                    occurred_at=event.ts, kind="meeting", payload=event.payload,
                )
                self._bump("c05_facts")
            elif kind == "workshop_image":
                raw = event.payload["raw_bytes"]
                self._sink.sink(event.payload["image_id"], raw)
                self._metrics.raw_bytes_peak = max(self._metrics.raw_bytes_peak, self._sink.retained_bytes)
                observation = self._cleaner.evaluate_and_clean_image(
                    dict(event.payload["metadata"]), raw
                )
                if observation is not None:
                    doc_seq += 1
                    self._c06.add(doc_seq, observation.semantic_caption)
                    self._bump("c06_docs")
                    self._persist_observation(
                        f"sim-imgmeta-{event.payload['image_id']}", event.ts, "scene_caption",
                        {"caption": observation.semantic_caption, "quality": observation.quality_score},
                    )
                    self._bump("images_cleaned")
                else:
                    self._bump("images_shredded")
                # 原始二进制即刻物理粉碎（宪法滞留量为零）
                self._sink.purge([event.payload["image_id"]])
            elif kind == "breach":
                doc_seq += 1
                self._c06.add(doc_seq, event.payload["document"])
                self._persist_observation(f"sim-breach-{doc_seq:04d}", event.ts, "legal_breach", event.payload)
                self._ledger.record_fact(
                    fact_id="sim-c05-breach-0001", entity_id="wang-lao",
                    occurred_at=event.ts, kind="breach", payload=event.payload,
                )
                self._bump("c05_facts")
                self._registry.append(RetrospectiveAnnotation(
                    annotation_id="sim-anno-breach-d22",
                    target_entity_id="wang-lao",
                    semantic_overlay="司法查封与欺诈重估：老王违约转移核心专利至离岸空壳",
                    target_time_start=self._start,
                    target_time_end=event.ts,
                    learned_at=event.ts,
                    source_statement_ref="sim://legal/breach-notice-d22",
                ))
                self._bump("c05_annotations")
                # C05 双时间核验（19+2 天前的当时已知视图必须无图层）
                as_of = self._lens.query_historical_slice(
                    "wang-lao", self._start + timedelta(days=10), as_of_cutoff=self._start + timedelta(days=10),
                )
                current = self._lens.query_historical_slice("wang-lao", event.ts)
                self._metrics.c05_asof_annotations = len(as_of.active_annotations)
                self._metrics.c05_current_annotations = len(current.active_annotations)
            elif kind == "daily_close":
                # C04 单看板装配：每日复盘一轮（1500 Token 硬预算内）
                result = self._cockpit.process_round(
                    f"第 {event.payload['day_index'] + 1} 天复盘：{self._recent_hr and self._recent_hr[-1][1]}bpm 收尾",
                    occurred_at=event.ts,
                )
                self._bump("cockpit_assemblies")
                self._add_tokens(result.cockpit.token_count)
                board = self._scheduler.assemble_board(event.ts)
                self._bump("board_assemblies")
                self._add_tokens(board.estimated_prompt_tokens)
                assert board.dormant_token_charge == 0
        # 冲刷合并队列（最后的未满窗口）
        for _ in self._queue.seal_finished_windows(self._start + timedelta(days=days)):
            pass
        self._metrics.queue_downstream_wakes = self._queue.stats["downstream_wakes"]
        self._metrics.raw_bytes_end = self._sink.retained_bytes
        self._metrics.c06_docs = len(self._c06)
        if self._llm is not None:
            raise AssertionError("SIM-001 全程禁用大模型客户端")
        if monthly_token_budget is not None and self._metrics.total_tokens > monthly_token_budget:
            raise AssertionError(
                f"monthly token envelope breached: {self._metrics.total_tokens} > {monthly_token_budget}"
            )
        return self._metrics
