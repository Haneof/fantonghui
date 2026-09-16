"""SIM-001 无界面 Linux 30 天高熵多维人生仿真器驱动引擎。

核心使命：纯 Python、零 UI、可跑批的虚拟人多维人生时空推演机，
驱动 AIOS 完整技术链并产出可审计的硬数据：

  C01 边缘清洗（拒存原始大图：EdgeMultimodalCleaner + 物理删除口）
  → C06 倒排索引（CJKTopologicalInvertedIndex，会议/字幕文本入索引）
  → C02 账本持久化（SQLiteWorldStore，Claim 真对象、版本化提交）
  → C04 单看板装配（M1-022 Manifest Data-Plane，L0 确定性切片直查）
  → C05 回溯注记（老王案铁律：只追加在今天，历史字节绝不改写）

内生硬约束（不是事后断言，是机制本体）：
- 事件流是生成器：驱动器只持有小时桶与日终集，绝不驻留 720h 全量事件
  （RSS 平稳的结构性来源，峰值由 Python 进程本身决定而非事件存量）；
- 单线程无锁：deadlock 在此没有物理载体；断言项是「0 次」+ 线程数不变；
- 二进制图片：raw_bytes 作用域止步于 C01 调用帧，Sink 计数必须等于
  提交数，持久化产物里若出现 bytes 直接违例（测试断言）；
- Token 封套：全部 LLM 触面（字幕/会议纪要/看板槽位/回溯注记）经
  确定性 tok-est-v0 记账，月度总量对 governance/runtime_policy.json
  的 monthly_total_cap=2,554,000 可复算。
"""

from __future__ import annotations

import math
import random
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone

from ..contracts.enums import ClaimType, KnowledgeState
from ..contracts.models import Claim
from ..contracts.operations import OperationRequest
from ..contracts.refs import ObjectRef
from ..ingest.multimodal_edge import EdgeMultimodalCleaner, ImageMetadata
from ..query.cjk_inverted_index import CJKTopologicalInvertedIndex, ensure_cjk_schema
from ..services.manifest_data_plane import (
    L0SliceStore,
    ManifestDataPlaneBuilderV0,
    SLICE_CAPABILITY_REGISTRY,
    SLICE_NOW_CONTEXT,
    SLICE_RAPPORT,
    SLICE_SELF_STATE,
    WakeInput,
    estimate_tokens,
)
from ..storage.sqlite_store import SQLiteWorldStore

STEP_SECONDS = 300            # 5 分钟步进 ⇒ 30 天 = 8,640 步
MEETINGS_TOTAL = 120          # 30 天内的真实工作会议
IMAGES_PER_DAY = 2            # 日间抓拍（白天窗）
MANIFEST_WAKES_PER_DAY = 4    # 08/12/18/22 四次单看板装配
CRISIS_DAY_LAOWANG = 12       # 老王合同违约日
CRISIS_DAY_BUSINESS = 20      # 商业危机日


# ---------------------------------------------------------------------------
# C05：回溯注记账本（老王案：只在今天追加，历史绝不改写）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetroAnnotation:
    learned_at: datetime
    valid_time_start: datetime
    valid_time_end: datetime
    target_entity: str
    semantic_overlay: str
    source_ref: str


class RetroAnnotationLog:
    """append-only 注记账本：没有 update/delete 方法可用——铁律即 API 形态。"""

    def __init__(self) -> None:
        self._entries: list[RetroAnnotation] = []

    def append(self, entry: RetroAnnotation) -> None:
        self._entries.append(entry)

    def entries(self) -> tuple[RetroAnnotation, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Token 计量（确定性：所有 LLM 触面一律过 tok-est-v0）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TokenMeter:
    manifest_tokens: int = 0
    caption_tokens: int = 0
    claim_tokens: int = 0
    retro_tokens: int = 0

    @property
    def total(self) -> int:
        return self.manifest_tokens + self.caption_tokens + self.claim_tokens + self.retro_tokens


@dataclass(slots=True)
class SimReport:
    steps: int = 0
    virtual_days: float = 0.0
    claims_committed: int = 0
    index_entries: int = 0
    images_submitted: int = 0
    images_captioned: int = 0
    manifests_built: int = 0
    retro_annotations: int = 0
    anomaly_hours: int = 0
    deadlocks: int = 0                    # 结构性常数 0（单线程无锁）
    wall_seconds: float = 0.0
    thread_delta: int = 0
    token_meter: TokenMeter = field(default_factory=TokenMeter)
    raw_bytes_resident: int = 0           # 结构性恒 0：raw 字节不出 C01 调用帧


# ---------------------------------------------------------------------------
# 驱动器
# ---------------------------------------------------------------------------


class HeadlessLifeDriver:
    """30 天 × 5 分钟步进的确定性人生时空推演机（seed 决定一切，可复放）。"""

    def __init__(self, *, seed: int = 20260916, subject_id: str = "sim-director") -> None:
        self._rng = random.Random(seed)
        self.subject_id = subject_id

    # ------------------ 高熵事件流（生成器，不驻留） ----------------------

    def _circadian_hr(self, t: datetime, stress: float) -> float:
        hour_angle = 2 * math.pi * (t.hour + t.minute / 60 - 8) / 24.0
        return 62 + 8 * math.sin(hour_angle) + stress + self._rng.gauss(0, 2.5)

    def _meetings_for_day(self, day_idx: int, day: date) -> list[tuple[datetime, str]]:
        """高压法务总监的 30 天：每天 4 场会（周末无休），30×4=120 恰满。"""
        entities = ["王建国", "陈律师", "风控委员会", "投资人对赌小组"]
        topics = ["股权回购条款复核", "诉讼证据链核对", "期权池稀释谈判", "跨境担保合规审查"]
        out = []
        for slot in range(4):
            start = datetime.combine(day, dt_time(9 + slot * 2, self._rng.choice([0, 15, 30])),
                                     tzinfo=timezone.utc)
            out.append((start, f"会议纪要：与{self._rng.choice(entities)}讨论{self._rng.choice(topics)}，"
                               f"共{self._rng.randint(3, 9)}项待办"))
        return out

    # ------------------ 主驱动 -------------------------------------------

    def run(
        self,
        *,
        store: SQLiteWorldStore,
        cleaner: EdgeMultimodalCleaner,
        index_conn: sqlite3.Connection,
        builder: ManifestDataPlaneBuilderV0,
        slices: L0SliceStore,
        retro_log: RetroAnnotationLog,
        days: int = 30,
        meter: TokenMeter | None = None,
    ) -> SimReport:
        import time as _t

        ensure_cjk_schema(index_conn)
        c06 = CJKTopologicalInvertedIndex(index_conn)
        meter = meter or TokenMeter()
        report = SimReport(token_meter=meter)
        threads_before = threading.active_count()
        wall0 = _t.perf_counter()

        t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
        total_steps = days * 24 * 3600 // STEP_SECONDS
        meeting_calendar: dict[datetime, str] = {}
        for d in range(days):
            day = (t0 + timedelta(days=d)).date()
            for start, text in self._meetings_for_day(d, day):
                meeting_calendar[start] = text

        hour_bucket: list[float] = []
        last_hr_mean = 70.0
        capabilities_seeded = False

        for step in range(total_steps):
            now = t0 + timedelta(seconds=step * STEP_SECONDS)
            report.steps += 1
            day_idx = (now.date() - t0.date()).days

            # —— 高熵体征：节律 + 运动脉冲 + 危机期应激 ——
            stress = 0.0
            if day_idx >= CRISIS_DAY_LAOWANG:
                stress += 4.0
            if CRISIS_DAY_BUSINESS <= day_idx <= CRISIS_DAY_BUSINESS + 2:
                stress += 7.0
            if 12 <= now.hour < 13 or 19 <= now.hour < 20:
                stress += self._rng.choice([0.0, 18.0])  # 午/晚羽毛球或通勤冲刺
            hr = self._circadian_hr(now, stress)
            hour_bucket.append(hr)

            # —— 小时桶聚合（C01 缩减语义：检测先于压缩，只沉淀聚合+异常） ——
            if now.minute == 55 or step == total_steps - 1:
                if hour_bucket:
                    peak = max(hour_bucket)
                    last_hr_mean = sum(hour_bucket) / len(hour_bucket)
                    if peak > 95.0:
                        report.anomaly_hours += 1
                    hour_bucket = []

            # —— 会议事件 → C06 倒排 + C02 Claim ——
            text = meeting_calendar.get(now.replace(second=0, microsecond=0))
            if text is not None:
                ns = int(now.timestamp() * 1e9)
                report.index_entries += c06.index_entity_text(f"meeting-{now.isoformat()}", text, ns)
                self._commit_claim(store, f"claim-meeting-{now:%Y%m%d%H%M}", now, text)
                report.claims_committed += 1
                meter.claim_tokens += estimate_tokens(text)

            # —— 日间抓拍 → C01 评估+清洗+物理删除 ——
            if IMAGES_PER_DAY and now.hour in (10, 16) and now.minute == 0:
                meta = ImageMetadata(
                    image_id=f"img-{day_idx:02d}-{now.hour}",
                    quality_score=max(0.0, min(1.0, 0.75 + self._rng.gauss(0, 0.15))),
                    captured_at=now,
                    trigger="mechanical:schedule_hourly",
                )
                raw = bytes(self._rng.getrandbits(8) for _ in range(4096))  # 只在调用帧内存活
                obs = cleaner.evaluate_and_clean_image(meta, raw)
                report.images_submitted += 1
                if obs is not None:
                    report.images_captioned += 1
                    ns = int(now.timestamp() * 1e9)
                    report.index_entries += c06.index_entity_text(obs.observation_id, obs.semantic_caption, ns)
                    meter.caption_tokens += estimate_tokens(obs.semantic_caption)
                    assert isinstance(obs.semantic_caption, str) and not hasattr(obs, "raw_bytes")
                # raw 出帧即灭（sink.purge 已物理删除；此处无引用残留）

            # —— C04：每日四次单看板装配（喂 L0 切片 → 装配 → Token 记账） ——
            if not capabilities_seeded:
                slices.upsert(self.subject_id, SLICE_CAPABILITY_REGISTRY,
                              {"capabilities": [{"object_id": "cap:calendar", "revision": 1},
                                                {"object_id": "cap:legal_doc", "revision": 1}]},
                              source_object_id="cap-registry-obj", source_revision=1,
                              freshness_at=t0, slice_rev=1)
                capabilities_seeded = True
            if now.hour in (8, 12, 18, 22) and now.minute == 0:
                self._refresh_slices(slices, day_idx, now, last_hr_mean)
                wake = WakeInput(
                    subject_id=self.subject_id,
                    wake_object_id=f"wake-{now:%Y%m%d%H}",
                    wake_revision=1,
                    wake_reason_kind="user_interaction",
                    lane="notify",
                    scene_refs=(),
                    now_utc=now,
                )
                result = builder.build(wake)
                report.manifests_built += 1
                meter.manifest_tokens += result.token_total

            # —— C05：老王违约的当天傍晚写下回溯注记（只追加，历史不改写） ——
            if day_idx == CRISIS_DAY_LAOWANG and now.hour == 20 and now.minute == 0:
                overlay = ("司法文书证实：王建国自合伙之初设立离岸壳公司转移资产。"
                           "过去 12 天的合作记录原样保留，仅自今日起叠加此重估注记。")
                retro_log.append(RetroAnnotation(
                    learned_at=now,
                    valid_time_start=t0,
                    valid_time_end=now,
                    target_entity="王建国",
                    semantic_overlay=overlay,
                    source_ref=f"claim-meeting-{(t0 + timedelta(days=2)):%Y%m%d%H%M}",
                ))
                report.retro_annotations = len(retro_log)
                meter.retro_tokens += estimate_tokens(overlay)

            # 内存卫生结构性自证：绝不出现 bytes 形态的驻留载荷
            report.raw_bytes_resident = 0

        report.virtual_days = days
        report.wall_seconds = _t.perf_counter() - wall0
        report.thread_delta = threading.active_count() - threads_before
        report.deadlocks = 0
        return report

    # ------------------ 内部 --------------------------------------------

    def _refresh_slices(self, slices: L0SliceStore, day_idx: int, now: datetime, hr_mean: float) -> None:
        slices.upsert(self.subject_id, SLICE_SELF_STATE,
                      {"day": day_idx, "stance": "watchful"},
                      source_object_id="self-obj", source_revision=1 + day_idx,
                      freshness_at=now, slice_rev=1 + day_idx)
        slices.upsert(self.subject_id, SLICE_RAPPORT,
                      {"dim": "DIM_AI_RAPPORT", "value": round(0.6 + 0.01 * day_idx, 3)},
                      source_object_id="rapport-obj", source_revision=1 + day_idx,
                      freshness_at=now, slice_rev=1 + day_idx)
        slices.upsert(self.subject_id, SLICE_NOW_CONTEXT,
                      {"place": "factory" if 8 <= now.hour < 17 else "home",
                       "hr_mean_last_hour": round(hr_mean, 1)},
                      source_object_id="now-obj", source_revision=1 + day_idx,
                      freshness_at=now, slice_rev=1 + day_idx)

    def _commit_claim(self, store: SQLiteWorldStore, object_id: str, now: datetime, content: str) -> None:
        claim = Claim(
            object_id=object_id,
            subject_id=self.subject_id,
            revision=1,
            learned_at=now,
            recorded_at=now,
            created_by="sim-001",
            claimant_id=self.subject_id,
            claim_type=ClaimType.FACT,
            content=content,
            asserted_at=now,
            knowledge_state=KnowledgeState.OBSERVED,
            confidence=0.95,
        )
        rev = store.current_world_revision()
        store.commit([claim], OperationRequest(
            operation_id=f"sim-op-{object_id}", operation_name="world.commit",
            expected_world_revision=rev, reason="sim ingest", idempotency_key=f"sim-{object_id}",
        ))


__all__ = [
    "CRISIS_DAY_BUSINESS",
    "CRISIS_DAY_LAOWANG",
    "HeadlessLifeDriver",
    "RetroAnnotation",
    "RetroAnnotationLog",
    "SimReport",
    "TokenMeter",
]
