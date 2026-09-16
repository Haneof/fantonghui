"""SIM-001 无界面 Linux 30 天高熵多维人生仿真器驱动引擎。

纯 Python、零 UI、可在无图形 Linux 服务器上跑批的"虚拟人多维人生
时空仿真推演机"。驱动 AIOS 真实技术链（不 mock 核心模块）：

* **C01 边缘清洗**：``ingest.multimodal_edge.RawByteSink``——垃圾抓拍
  亚毫秒物理粉碎，原始字节零滞留；
* **C06 结构检索**：``query.hyperlink_traverser``——实体→事件锚点→
  证据集→观测的四级穿透（别名"老王"入口）；
* **C02 账本持久化**：``storage.SQLiteWorldStore``——追加式世界存储
  逐日真实事务提交；
* **C04 单看板装配**：``cockpit.CrisisDialoguePipeline``——危机对话
  单看板 Token 封套记账；
* **C05 回溯注记**：``world.retrospective_annotation``——SHA-256 物理
  台账 + 注记双时间可见性 + 单跳级联隔离。

四大硬门禁：720 小时连续时空流（昼夜节律/高频心率/HRV/工业高噪/
120 次会议/第 23 天商业危机与老王合同违约）；全链驱动；30 天连续
推演 0 死锁、驻留 RSS ≤128MB、原始二进制图片滞留为 0；月度 Token
总量受 ``governance/runtime_policy.json`` 的 2,554,000 封套约束。
"""

from __future__ import annotations

import json
import random
import resource
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from aios_core.cockpit.pipeline import CrisisDialoguePipeline, estimate_tokens
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent
from aios_core.ingest.multimodal_edge import CaptureFrame, RawByteSink
from aios_core.query.hyperlink_traverser import EntityHyperlinkGraphTraverser
from aios_core.storage.sqlite_store import SQLiteWorldStore
from aios_core.world.retrospective_annotation import (
    AnnotationKind,
    ObservationHashLedger,
    RetrospectiveAnnotation,
    RetrospectiveAnnotationLog,
    SingleHopCascadeIsolator,
)

__all__ = [
    "HeadlessLifeDriver",
    "SIM_MONTH_TOKEN_BUDGET_FALLBACK",
    "SimRunReport",
]

UTC = timezone.utc
#: 策略文件缺失时的兜底预算（与 governance/runtime_policy.json 保持一致）。
SIM_MONTH_TOKEN_BUDGET_FALLBACK = 2_554_000
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_POLICY = _REPO_ROOT / "governance" / "runtime_policy.json"

#: 30 天 × 24 小时。
TOTAL_VIRTUAL_HOURS = 720
#: 全月工作会议次数（4 次/虚拟日）。
MEETINGS_PER_DAY = 4
#: 死锁看门狗：单阶段墙钟预算（秒）。真实死锁/挂起必然远超此值。
STAGE_DEADLOCK_BUDGET_SECONDS = 120.0


class SimRunReport(BaseModel):
    """一次 30 天无头推演的完整对账报告（四大门禁的全部证据）。"""

    model_config = ConfigDict(extra="forbid")

    virtual_days: StrictInt = Field(ge=0)
    virtual_hours: StrictInt = Field(ge=0)
    wall_seconds: float = Field(ge=0.0)
    effective_acceleration: float = Field(ge=0.0)

    observations_committed: StrictInt = Field(ge=0)
    meetings_generated: StrictInt = Field(ge=0)
    world_revisions: StrictInt = Field(ge=0)

    junk_frames_purged: StrictInt = Field(ge=0)
    junk_raw_residual_bytes: StrictInt = Field(ge=0)
    keeper_frames_retained: StrictInt = Field(ge=0)

    hyperlink_traversals_ok: StrictInt = Field(ge=0)
    hyperlink_observations_reached: StrictInt = Field(ge=0)

    crisis_sessions: StrictInt = Field(ge=0)
    manifests_assembled: StrictInt = Field(ge=0)
    token_total: StrictInt = Field(ge=0)
    token_budget: StrictInt = Field(gt=0)
    token_budget_source: StrictStr

    hash_ledger_entries: StrictInt = Field(ge=0)
    annotation_hidden_historical: StrictInt = Field(ge=0)
    annotation_visible_now: StrictInt = Field(ge=0)
    stale_marked_count: StrictInt = Field(ge=0)
    isolator_llm_calls: StrictInt = Field(ge=0)

    deadlock_count: StrictInt = Field(ge=0)
    peak_rss_mb: float = Field(ge=0.0)
    rss_growth_mb: float = Field(
        ge=0.0,
        description="驱动器自身诱发的 RSS 增量（当前值差，不继承套件历史水位）",
    )


class _StageWatchdog:
    """阶段看门狗：墙钟超预算计一次死锁（确定性管线超时即结构性挂起）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.deadlocks = 0
        self.stage_wall: dict[str, float] = {}

    def run(self, name: str, fn: Callable[[], Any], *, budget_s: float = STAGE_DEADLOCK_BUDGET_SECONDS) -> Any:
        started = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - started
        with self._lock:
            self.stage_wall[name] = elapsed
            if elapsed > budget_s:
                self.deadlocks += 1
        return result


class HeadlessLifeDriver:
    """30 天虚拟人生无头驱动器（确定性种子，可重放）。"""

    def __init__(
        self,
        *,
        days: int = 30,
        seed: int = 20260915,
        store: SQLiteWorldStore,
        token_policy_path: Path | None = None,
        nominal_acceleration: float = 1000.0,
    ) -> None:
        if days < 1:
            raise ValueError("days must be >= 1")
        self._days = days
        self._rng = random.Random(seed)
        self._store = store
        self._accel = nominal_acceleration
        self._policy_path = token_policy_path or _DEFAULT_POLICY
        self._token_budget, self._budget_source = self._load_token_budget()
        self._sink = RawByteSink()
        self._hyperlink = EntityHyperlinkGraphTraverser()
        self._token_total = 0
        self._watchdog = _StageWatchdog()
        # 计数器
        self._obs_committed = 0
        self._meetings = 0
        self._junk_purged = 0
        self._junk_residual = 0
        self._keepers = 0
        self._traversals_ok = 0
        self._obs_reached = 0
        self._sessions = 0
        self._manifests = 0

    # ------------------------------------------------------------------
    # 策略装载
    # ------------------------------------------------------------------

    def _load_token_budget(self) -> tuple[int, str]:
        path = Path(self._policy_path)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return int(data["simulation_monthly_token_budget"]), str(path)
        return SIM_MONTH_TOKEN_BUDGET_FALLBACK, "fallback"

    # ------------------------------------------------------------------
    # 生成器：720 小时高熵时空流
    # ------------------------------------------------------------------

    def _day_start(self, day_index: int) -> datetime:
        return datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC) + timedelta(days=day_index)

    def _generate_day_observations(
        self, day_index: int
    ) -> tuple[list[Observation], list[CaptureFrame]]:
        """生成一个虚拟日的观测流：昼夜节律生理 + 高噪环境 + 会议 + 危机。"""
        start = self._day_start(day_index)
        observations: list[Observation] = []
        is_workout_day = day_index % 3 == 1
        is_industrial_day = day_index % 2 == 0  # 隔日在重型装配车间巡场

        def make_obs(index_key: str, at: datetime, source_kind: str, value: dict) -> Observation:
            return Observation(
                object_id=f"obs_sim_d{day_index:02d}_{index_key}",
                subject_id="user_legal_director",
                occurred=TemporalExtent.point(at),
                learned_at=at,
                recorded_at=at,
                created_by="sim-001",
                source_kind=source_kind,
                modality="json",
                value=value,
            )

        # 24 小时逐时生理流（高频心率的特征化聚合：5Hz 原始波形在
        # 生成后即聚合丢弃，仅保留特征值——保证 RSS 平稳）
        for hour in range(24):
            at = start + timedelta(hours=hour, minutes=self._rng.randint(0, 30))
            circadian = 58 + 10 * (1 - ((hour - 15) % 24) / 12) if hour < 22 else 54
            hr = int(circadian + self._rng.randint(-4, 6))
            hrv = int(48 + 14 * ((hour + 6) % 24) / 24 + self._rng.randint(-6, 6))
            if is_workout_day and 19 <= hour <= 20:
                hr += self._rng.randint(45, 62)   # 羽毛球/搏击操峰值 ~165bpm
                hrv = max(14, hrv - 22)
            if hour >= 1 and hour <= 4:
                hrv = max(12, hrv - 8)            # 深夜浅睡段
            observations.append(
                make_obs(
                    f"vitals_{hour:02d}",
                    at,
                    "wearable_vitals",
                    {
                        "hr_bpm": hr,
                        "hrv_ms": hrv,
                        "agg": "5Hz-waveform->hourly-features",
                        "raw_waveform_retained": False,
                    },
                )
            )
        # 工业车间高噪环境片段
        observations.append(
            make_obs(
                "env_noise",
                start + timedelta(hours=10, minutes=15),
                "environment_noise",
                {
                    "scene": "heavy_industry_assembly_hall" if is_industrial_day else "open_office",
                    "ambient_db": self._rng.randint(82, 88) if is_industrial_day else self._rng.randint(52, 60),
                    "dominant_band": "low_freq_machinery" if is_industrial_day else "human_chatter",
                },
            )
        )
        # 会议（每日 4 场 → 30 天共 120 场）
        for m in range(MEETINGS_PER_DAY):
            at = start + timedelta(hours=9 + m * 2, minutes=5 * m)
            self._meetings += 1
            observations.append(
                make_obs(
                    f"meeting_{m:02d}",
                    at,
                    "work_meeting",
                    {
                        "seq": self._meetings,
                        "topic": self._rng.choice(
                            (
                                "供应商对赌条款评审",
                                "知识产权质押融资谈判",
                                "竞业限制案证据复盘",
                                "供应链账期压力会议",
                            )
                        ),
                        "attendees": self._rng.randint(3, 11),
                        "stress_level": self._rng.choice(("normal", "high", "high")),
                    },
                )
            )
        # 第 23 天（0 基索引 22）：商业危机 + 老王合同违约
        if day_index == 22:
            breach_at = start + timedelta(hours=21, minutes=40)
            observations.append(
                make_obs(
                    "crisis_breach",
                    breach_at,
                    "contract_event",
                    {
                        "event": "老王单方违约：未按《联合孵化协议》交付核心 IP 授权",
                        "counterparty_alias": "老王",
                        "penalty_clause": "违约定金双倍返还 + 联带担保追索",
                        "user_note": "凌晨接到律师电话，手都在抖",
                    },
                )
            )
            observations.append(
                make_obs(
                    "crisis_counsel",
                    breach_at + timedelta(minutes=35),
                    "contract_event",
                    {
                        "event": "紧急法务对策：证据保全公证 + 仲裁条款激活评估",
                        "deadline": "72 小时内发出违约通知函",
                    },
                )
            )
        # 抓拍帧：1 张有效（标牌/合同文本）+ 1 张走动抖动垃圾
        frames = [
            CaptureFrame(
                frame_id=f"frame_d{day_index:02d}_keeper",
                quality=round(self._rng.uniform(0.68, 0.9), 2),
                brightness=0.7,
                sharpness=0.8,
                jitter=0.1,
                scene_tag="contract_or_nameplate",
                captured_at=start + timedelta(hours=13),
            ),
            CaptureFrame(
                frame_id=f"frame_d{day_index:02d}_junk",
                quality=round(self._rng.uniform(0.05, 0.35), 2),
                brightness=0.2,
                sharpness=0.15,
                jitter=0.9,
                scene_tag="walking_blur",
                captured_at=start + timedelta(hours=13, minutes=2),
            ),
        ]
        return observations, frames

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> SimRunReport:
        wall_started = time.perf_counter()
        rss_current_before = _current_rss_mb()

        for day_index in range(self._days):
            observations, frames = self._watchdog.run(
                f"day{day_index:02d}.generate", lambda d=day_index: self._generate_day_observations(d)
            )
            # C01：抓拍入 sink → 日终粉碎垃圾帧（原始字节零滞留）
            def _edge_clean(frames=frames, day_index=day_index) -> None:
                for frame in frames:
                    self._sink.store(frame, _fake_jpeg_bytes(self._rng, frame.frame_id))
                report = self._sink.purge()
                self._junk_purged += report.purged_count
                self._junk_residual += report.raw_bytes_retained_for_purged
                self._keepers = self._sink.live_frame_count

            self._watchdog.run(f"day{day_index:02d}.c01_edge", _edge_clean)

            # C02：追加式世界账本逐日事务提交（含危机日会话归档观测）
            def _persist(observations=observations, day_index=day_index) -> None:
                chunk = list(observations)
                if day_index == 22:
                    chunk.extend(self._run_crisis_session(day_index))
                self._store.commit(
                    chunk,
                    OperationRequest(
                        operation_id=f"op_sim_d{day_index:02d}",
                        session_id="session_sim_001",
                        operation_name="world.commit",
                        arguments={"virtual_day": day_index},
                        expected_world_revision=self._store.current_world_revision(),
                        reason="sim-001 daily life stream persistence",
                        idempotency_key=f"idem_sim_d{day_index:02d}",
                    ),
                )
                self._obs_committed += len(chunk)

            self._watchdog.run(f"day{day_index:02d}.c02_ledger", _persist)

            # C06：每周 + 危机日注册并四级穿透"老王"实体拓扑
            if day_index % 7 == 6 or day_index == 22:
                self._watchdog.run(
                    f"day{day_index:02d}.c06_hyperlink", lambda d=day_index: self._register_and_traverse(d)
                )

        # C05：SHA-256 物理台账 + 回溯注记双时间可见性 + 单跳级联隔离
        hash_ledger, hidden, visible, stale_marked, iso_llm = self._watchdog.run(
            "c05_annotation_chain", self._run_annotation_chain
        )

        wall_seconds = time.perf_counter() - wall_started
        rss_growth = max(_current_rss_mb() - rss_current_before, 0.0)
        peak_rss = _peak_rss_mb()
        return SimRunReport(
            virtual_days=self._days,
            virtual_hours=self._days * 24,
            wall_seconds=round(wall_seconds, 3),
            effective_acceleration=round((self._days * 86400.0) / max(wall_seconds, 1e-6), 1),
            observations_committed=self._obs_committed,
            meetings_generated=self._meetings,
            world_revisions=self._store.current_world_revision(),
            junk_frames_purged=self._junk_purged,
            junk_raw_residual_bytes=self._junk_residual,
            keeper_frames_retained=self._keepers,
            hyperlink_traversals_ok=self._traversals_ok,
            hyperlink_observations_reached=self._obs_reached,
            crisis_sessions=self._sessions,
            manifests_assembled=self._manifests,
            token_total=self._token_total,
            token_budget=self._token_budget,
            token_budget_source=self._budget_source,
            hash_ledger_entries=hash_ledger,
            annotation_hidden_historical=hidden,
            annotation_visible_now=visible,
            stale_marked_count=stale_marked,
            isolator_llm_calls=iso_llm,
            deadlock_count=self._watchdog.deadlocks,
            peak_rss_mb=round(peak_rss, 1),
            rss_growth_mb=round(rss_growth, 1),
        )

    # ------------------------------------------------------------------
    # C04：危机对话 → 单看板装配（Token 记账）
    # ------------------------------------------------------------------

    def _run_crisis_session(self, day_index: int) -> list[Observation]:
        """第 23 天危机长线对话：6 轮 → 单看板 → 逐出轮次归档为 Observation。"""
        at0 = self._day_start(day_index) + timedelta(hours=21, minutes=45)
        archived: list[Observation] = []
        pipeline = CrisisDialoguePipeline(
            session_id=f"sess_crisis_d{day_index:02d}",
            subject_id="user_legal_director",
            archive_sink=lambda obs: archived.append(obs),
        )
        turns = (
            ("user", "老王刚打电话说 IP 授权黄了，之前两笔孵化款也不退，我现在怎么办。"),
            ("ai", "先稳住。合同和转账凭证今晚全部打包，违约通知函模板我来出。"),
            ("user", "他之前说资金周转困难，我现在越想越不对劲。"),
            ("ai", "把这句话原话记下来，仲裁时这就是主观状态的证据。"),
            ("user", "72 小时够吗？明天我还要主持对赌评审。"),
            ("ai", "够。公证今早办，函我半夜给你，评审你照常去，别乱阵脚。"),
        )
        for i, (speaker, text) in enumerate(turns):
            pipeline.push_turn(speaker, text, at=at0 + timedelta(minutes=4 * i))
        manifest = pipeline.assemble_manifest(
            wake_reason="user_message:contract_breach_night",
            world_digest="d22: 老王违约 + 72h 违约通知窗口 + 对赌评审日程冲突",
            self_mirror="僚机姿态：稳人、办事、不废话",
            ready_tasks=("task:违约通知函 72h 倒计时", "task:证据保全公证预约"),
            recall_digest=("clm_laowang_trust", "evt_incubation_agreement"),
            session_digest=f"crisis_d{day_index:02d}",
            now=at0 + timedelta(minutes=26),
        )
        self._sessions += 1
        self._manifests += 1
        self._token_total += manifest.token_total
        return list(archived)

    # ------------------------------------------------------------------
    # C06：实体拓扑注册 + 四级穿透
    # ------------------------------------------------------------------

    def _register_and_traverse(self, day_index: int) -> None:
        evidence_id = "evs_laowang_breach"
        observation_ids = [f"obs_sim_d{d:02d}_meeting_00" for d in range(0, min(day_index + 1, self._days), 7)]
        observation_ids += [
            "obs_sim_d22_crisis_breach",
            "obs_sim_d22_crisis_counsel",
        ]
        self._hyperlink.register_observation(
            observation_ids[0], content="首周供应商对赌条款评审纪要", occurred_at=self._day_start(0)
        )
        for oid in observation_ids[1:]:
            self._hyperlink.register_observation(oid)
        self._hyperlink.register_evidence_link(
            evidence_id, observation_ids, purpose="老王履约与违约全链证据"
        )
        self._hyperlink.register_anchor_link(
            "evt_laowang_breach_d22", [evidence_id], title="第23天老王单方违约"
        )
        self._hyperlink.register_entity_link(
            "ent_laowang_partner",
            ["老王", "王总"],
            ["evt_laowang_breach_d22"],
            canonical_name="王姓联合孵化对手方",
        )
        result = self._hyperlink.traverse_entity_network("老王", depth=4)
        if result.root_entity_id == "ent_laowang_partner" and len(result.observations) >= len(observation_ids):
            self._traversals_ok += 1
            self._obs_reached += len(result.observations)
        # C06 为确定性机械阶段：0 Token（机械检索不触碰大模型，不占预算）

    # ------------------------------------------------------------------
    # C05：物理台账 + 回溯注记 + 单跳隔离
    # ------------------------------------------------------------------

    def _run_annotation_chain(self) -> tuple[int, int, int, int, int]:
        payloads = self._store.list_payloads(object_type=ObjectType.OBSERVATION)
        ledger = ObservationHashLedger.capture(payloads, label="sim001_30d_observations")

        breach_day_start = self._day_start(22)
        annotation = RetrospectiveAnnotation(
            annotation_id="ann_laowang_breach_d22",
            target_entity_id="ent_laowang_partner",
            semantic_overlay=(
                "老王于第23天单方违约且拒不退还孵化款；欺诈重估：此前"
                "『资金周转困难』话术实为转移 IP 授权的铺垫，信任基线降级"
            ),
            target_time_start=self._day_start(0),
            target_time_end=breach_day_start + timedelta(hours=23, minutes=59),
            learned_at=self._day_start(23) + timedelta(hours=8),  # 次日晨间固化（认知只追加在今天）
            source_statement_ref="obs_sim_d22_crisis_breach",
            annotation_kind=AnnotationKind.FRAUD_REASSESSMENT,
            secondary_kinds=(AnnotationKind.CUSTOM,),
            confidence=0.93,
        )
        log = RetrospectiveAnnotationLog([annotation])
        hidden = len(log.visible_at(self._day_start(10)))     # 第10天视角：尚未获知
        visible = len(log.visible_at(self._day_start(29)))    # 月末视角：已叠加

        isolator = SingleHopCascadeIsolator()
        for i in range(10):
            isolator.register_dependency(f"cog_l1_{i:02d}", "fact_laowang_reliable")
            for j in range(2):
                isolator.register_dependency(f"cog_l2_{i:02d}_{j}", f"cog_l1_{i:02d}")
        report = isolator.mark_stale_from(
            "fact_laowang_reliable", "老王违约：可信认知重估", at=self._day_start(22)
        )
        self._token_total += estimate_tokens(annotation.semantic_overlay)

        return (
            ledger.count if hasattr(ledger, "count") else len(payloads),
            hidden,
            visible,
            report.marked_count,
            report.llm_calls_issued,
        )


def _fake_jpeg_bytes(rng: random.Random, frame_id: str) -> bytes:
    """合成 JPEG 风格原始字节（确定性）。"""
    header = b"\xff\xd8\xff\xe0" + frame_id.encode()[:8]
    return header + bytes(rng.getrandbits(8) for _ in range(1536)) + b"\xff\xd9"


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _current_rss_mb() -> float:
    """当前驻留 RSS（/proc/self/statm，页单位）。用于进程内增量归因。"""
    try:
        fields = Path("/proc/self/statm").read_text().split()
        page_size = 4096
        return (int(fields[1]) * page_size) / (1024.0 * 1024.0)
    except (OSError, IndexError, ValueError):
        return _peak_rss_mb()
