"""AIOS 3.0 端侧数据清洗与事实提纯官（Solver: ``01a0aa2c-fantonghui``）。

本模块是 Master Dispatch #11《云端全兵团数据清洗与事实提纯竞技场》中
**做题方（Solver / Purifier）** 的正式实现，接手 AIOS 底座，从对手战队落盘的
10,000 道多模态高熵生活流考题中提纯核心事实、物理剪枝垃圾，并输出可审计答卷。

老大五大铁律的工程落点
--------------------

1. **质量第一**：一句话事实必须因果准确、锚点完整（人物/金额/数值/原话锚点），
   本模块宁可多花算力做多模态交叉校验，也不吐出半句废话；
2. **历史不可篡改**：提纯事实只能挂载在 ``T_now``（``TNowFactLedger`` 追加式挂载），
   底层 SQLite 以触发器物理禁止 ``UPDATE`` / ``DELETE``，历史 Observation 字节级不可变；
3. **P0 紧急特权硬旁路**：``P0CriticalSafetyBypass`` 纯物理阈值首行判定（摔倒 / 心搏骤停 /
   濒危 SOS），耗时 ``<= 50ms``、大模型调用严格 ``0`` 次、世界模型让路；
4. **大模型自主物理删除**：``EdgeByteShredder`` 对叫卖噪声、风噪切片、砍一刀、验证码
   执行**不可逆物理粉碎**（墓碑 + 字节回收审计），ID 全部进入 ``pruned_junk_ids``；
5. **绝不自出自做**：``assert_cross_team_provenance`` 强制校验题库来自对手战队分支，
   并记录分支 + blob SHA256 溯源，``solver_agent == generator_agent`` 直接拒绝执行。

设计要点（可复现、可审计、零外部 API）
------------------------------------

* 提纯引擎为**确定性语义引擎**：多模态结构特征 + 领域方向词库 + 实体抽取 + 跨题身份记忆，
  不依赖任何外部大模型 API（云端断网亦可复现），``llm_tokens_used == 0``；
* 求解时**严禁读取 ``ground_truth_*`` 字段**：``assert_ground_truth_firewall``
  在入口 fail-closed，标答只在阅卷阶段交给 ``DirectionalSemanticMatcher``；
* 事实方向以「方向词簇」显式声明（``[方向] 摔倒/跌倒/倒地/摔伤``），
  严格落实老大批示：*答案不能写死，只能以方向为准确答案*。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from aios_core.contracts.safety_bypass import HazardType, WakePriority
from aios_core.simulation.cleaning_arena_protocol import (
    CleaningAnswerSubmission,
    ExtractedFactSubmission,
)

__all__ = [
    "APP_CATEGORY_INTENT",
    "Archetype",
    "BankProvenance",
    "CleaningSolver01a0aa2c",
    "EdgeByteShredder",
    "GroundTruthFirewallViolation",
    "INTENT_CATALOG",
    "MIC_SCENE_INTENT",
    "P0CriticalSafetyBypass",
    "P0Verdict",
    "SelfSolvingViolation",
    "SENSOR_KIND_LABEL_INTENT",
    "ShredReceipt",
    "SOLVER_AGENT",
    "SOLVER_BRANCH",
    "TNowFactLedger",
    "WearerIdentityMemory",
    "assert_cross_team_provenance",
    "assert_ground_truth_firewall",
    "sha256_text",
]

SOLVER_AGENT = "01a0aa2c-fantonghui"
SOLVER_BRANCH = "arena/01a0aa2c-fantonghui"
GENERATOR_AGENT = "agent-11"

UTC = timezone.utc

#: 求解阶段严禁出现在载荷中的标答字段（fail-closed 防火墙前缀）。
FORBIDDEN_GROUND_TRUTH_KEYS: Tuple[str, ...] = (
    "ground_truth",
    "ground_truth_facts",
    "ground_truth_junk_ids",
)


class SelfSolvingViolation(RuntimeError):
    """铁律五：自出自做一票否决（``solver_agent == generator_agent``）。"""


class GroundTruthFirewallViolation(RuntimeError):
    """铁律防火墙：求解阶段必须与标答彻底隔离，载荷含标答字段即 fail-closed。"""


class HistoryMutationViolation(RuntimeError):
    """铁律二：历史绝不篡改（任何 UPDATE / DELETE 历史记录的尝试均被拒绝）。"""


def sha256_text(text: str) -> str:
    """稳定 SHA256（UTF-8）十六进制摘要。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# 一、跨战队取证与标答防火墙（铁律五）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BankProvenance:
    """对手题库取证凭据（跨 Git 拉取的不可抵赖溯源）。"""

    generator_agent: str
    source_branch: str
    source_path: str
    bank_sha256: str
    question_count: int
    fetched_at: str
    ground_truth_sha256: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generator_agent": self.generator_agent,
            "source_branch": self.source_branch,
            "source_path": self.source_path,
            "bank_sha256": self.bank_sha256,
            "question_count": self.question_count,
            "fetched_at": self.fetched_at,
            "solver_agent": SOLVER_AGENT,
            "solver_branch": SOLVER_BRANCH,
        }


def assert_cross_team_provenance(generator_agent: str, source_branch: str) -> None:
    """铁律五守卫：拒绝自出自做、拒绝从我方分支取卷。"""
    if not generator_agent or not isinstance(generator_agent, str):
        raise SelfSolvingViolation("题库缺少 generator_agent 标识，无法证明跨战队取证")
    normalized = generator_agent.strip().lower()
    if normalized == SOLVER_AGENT.lower():
        raise SelfSolvingViolation(
            f"【严重违纪自出题自做】solver={SOLVER_AGENT} 禁止作答本战队题库 {generator_agent}"
        )
    if SOLVER_AGENT.lower() in normalized or normalized in SOLVER_AGENT.lower():
        raise SelfSolvingViolation(
            f"【严重违纪自出题自做】题库 generator={generator_agent} 与我方标识同源"
        )
    if source_branch.strip().endswith(SOLVER_BRANCH) or source_branch.strip() == SOLVER_BRANCH:
        raise SelfSolvingViolation(
            f"【严重违纪】题库来源分支 {source_branch} 属于我方工作分支，必须跨 Git 取对手卷"
        )


def assert_ground_truth_firewall(payload: Mapping[str, Any]) -> None:
    """标答防火墙：求解载荷一旦携带任何 ``ground_truth*`` 字段立即熔断。"""
    leaked = sorted(k for k in payload.keys() if k in FORBIDDEN_GROUND_TRUTH_KEYS)
    if leaked:
        raise GroundTruthFirewallViolation(
            "求解载荷携带标答字段，违反「做题方与标答隔离」纪律: " + ", ".join(leaked)
        )


def strip_ground_truth(question: Mapping[str, Any]) -> Dict[str, Any]:
    """剥离标答字段，生成做题方可见的「盲化题目」（阅卷阶段另行取回标答）。"""
    return {k: v for k, v in question.items() if k not in FORBIDDEN_GROUND_TRUTH_KEYS}


# ---------------------------------------------------------------------------
# 二、端侧物理粉碎（铁律四）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShredReceipt:
    """单条垃圾碎片的物理粉碎回执（墓碑可审计，原文不可复活）。"""

    item_id: str
    modality: str
    bytes_reclaimed: int
    payload_sha256: str
    tombstone: str


class EdgeByteShredder:
    """端侧字节粉碎机：垃圾原始字节物理回收 + 不可逆墓碑审计。

    手环端侧存储极其宝贵，本类对判定为垃圾的原始字节执行**就地覆写后删除**，
    仅保留 SHA256 墓碑用于事后审计（哈希不可逆，原文不可复活）。
    """

    def __init__(self) -> None:
        self._vault: Dict[str, bytearray] = {}
        self._modality: Dict[str, str] = {}
        self._receipts: List[ShredReceipt] = []
        self._sunk_bytes = 0

    def sink(self, item_id: str, modality: str, payload: bytes) -> None:
        """垃圾候选原始字节暂存（尚未删除，等待裁决）。"""
        if item_id in self._vault:
            raise ValueError(f"重复下沉同名片段: {item_id}")
        self._vault[item_id] = bytearray(payload)
        self._modality[item_id] = modality
        self._sunk_bytes += len(payload)

    def shred(self, item_id: str) -> ShredReceipt:
        """物理粉碎：覆写归零 → 移出存储 → 生成不可逆墓碑。"""
        buf = self._vault.pop(item_id, None)
        if buf is None:
            raise KeyError(f"片段 {item_id} 不在端侧暂存池，无法粉碎")
        modality = self._modality.pop(item_id, "unknown")
        digest = hashlib.sha256(bytes(buf)).hexdigest()
        reclaimed = len(buf)
        for index in range(len(buf)):  # 物理覆写，杜绝内存残留
            buf[index] = 0
        buf.clear()
        receipt = ShredReceipt(
            item_id=item_id,
            modality=modality,
            bytes_reclaimed=reclaimed,
            payload_sha256=digest,
            tombstone=f"tombstone::{modality}::{digest[:16]}",
        )
        self._receipts.append(receipt)
        return receipt

    def shred_many(self, item_ids: Iterable[str]) -> List[ShredReceipt]:
        return [self.shred(i) for i in item_ids if i in self._vault]

    @property
    def receipts(self) -> Tuple[ShredReceipt, ...]:
        return tuple(self._receipts)

    def is_recoverable(self, item_id: str) -> bool:
        """粉碎后原始字节不可复活（审计断言用）。"""
        return item_id in self._vault

    @property
    def sunk_bytes(self) -> int:
        return self._sunk_bytes

    @property
    def reclaimed_bytes(self) -> int:
        return sum(r.bytes_reclaimed for r in self._receipts)

    @property
    def retained_bytes(self) -> int:
        return sum(len(b) for b in self._vault.values())


# ---------------------------------------------------------------------------
# 三、T_now 追加式事实台账（铁律二：历史绝不篡改）
# ---------------------------------------------------------------------------

_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS observation_archive (
    observation_id  TEXT PRIMARY KEY,
    question_id     TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    modality        TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_ledger (
    fact_id          TEXT PRIMARY KEY,
    question_id      TEXT NOT NULL,
    observed_at      TEXT NOT NULL,
    mounted_at       TEXT NOT NULL,
    dimension_id     TEXT NOT NULL,
    semantic_intent  TEXT NOT NULL,
    summary_text     TEXT NOT NULL,
    source_ref_id    TEXT NOT NULL,
    recognized_entities TEXT NOT NULL,
    direction_cluster   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retrospective_annotation (
    annotation_id  TEXT PRIMARY KEY,
    fact_id        TEXT NOT NULL,
    annotated_at   TEXT NOT NULL,
    note           TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trg_fact_ledger_no_update
BEFORE UPDATE ON fact_ledger
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_IMMUTABLE: fact_ledger 禁止 UPDATE（铁律二）');
END;
CREATE TRIGGER IF NOT EXISTS trg_fact_ledger_no_delete
BEFORE DELETE ON fact_ledger
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_IMMUTABLE: fact_ledger 禁止 DELETE（铁律二）');
END;
CREATE TRIGGER IF NOT EXISTS trg_observation_archive_no_update
BEFORE UPDATE ON observation_archive
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_IMMUTABLE: observation_archive 禁止 UPDATE（铁律二）');
END;
CREATE TRIGGER IF NOT EXISTS trg_observation_archive_no_delete
BEFORE DELETE ON observation_archive
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_IMMUTABLE: observation_archive 禁止 DELETE（铁律二）');
END;
CREATE TRIGGER IF NOT EXISTS trg_retrospective_annotation_no_delete
BEFORE DELETE ON retrospective_annotation
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_IMMUTABLE: retrospective_annotation 禁止 DELETE（铁律二）');
END;
"""


class TNowFactLedger:
    """追加式认知台账：事实只允许挂载在 ``T_now``，历史 Observation 只增不改。

    老王案铁律：今天发现新事实，**只在今天写一条新认知**，绝不回头 UPDATE 两年前的
    Observation；需要解释历史时走 ``annotate``（外挂解释图层），不做无界级联重算。
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_LEDGER_SCHEMA)
        self._conn.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def archive_observation(
        self,
        *,
        observation_id: str,
        question_id: str,
        observed_at: str,
        modality: str,
        payload_sha256: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO observation_archive VALUES (?,?,?,?,?)",
            (observation_id, question_id, observed_at, modality, payload_sha256),
        )

    def mount_fact(
        self,
        *,
        fact_id: str,
        question_id: str,
        observed_at: str,
        dimension_id: str,
        semantic_intent: str,
        summary_text: str,
        source_ref_id: str,
        recognized_entities: Sequence[str],
        direction_cluster: Sequence[str],
        t_now: Optional[datetime] = None,
    ) -> str:
        """把提纯事实挂载到 ``T_now``（唯一合法挂载点），返回挂载时间戳。

        幂等重放：同一 ``fact_id`` 且内容逐字段一致 → 视为重放，不重复落账；
        内容不一致 → 抛 ``HistoryMutationViolation``（历史不可改写，另行外挂注解）。
        """
        mounted_at = (t_now or _utc_now()).isoformat()
        entities_json = json.dumps(list(recognized_entities), ensure_ascii=False)
        direction_json = json.dumps(list(direction_cluster), ensure_ascii=False)
        existing = self._conn.execute(
            "SELECT mounted_at, dimension_id, semantic_intent, summary_text, source_ref_id,"
            " recognized_entities, direction_cluster FROM fact_ledger WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        if existing is not None:
            expected = (dimension_id, semantic_intent, summary_text, source_ref_id, entities_json, direction_json)
            if tuple(existing[1:]) == expected:
                return str(existing[0])
            raise HistoryMutationViolation(
                f"fact_id={fact_id} 已存在且内容不一致：历史不可改写（只允许 T_now 挂载或外挂注解）"
            )
        self._conn.execute(
            "INSERT INTO fact_ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                fact_id,
                question_id,
                observed_at,
                mounted_at,
                dimension_id,
                semantic_intent,
                summary_text,
                source_ref_id,
                entities_json,
                direction_json,
            ),
        )
        return mounted_at

    def annotate(self, *, annotation_id: str, fact_id: str, note: str, t_now: Optional[datetime] = None) -> str:
        """外挂解释图层（单跳隔离）：新认知只挂今天，不重算历史。"""
        annotated_at = (t_now or _utc_now()).isoformat()
        self._conn.execute(
            "INSERT INTO retrospective_annotation VALUES (?,?,?,?)",
            (annotation_id, fact_id, annotated_at, note),
        )
        return annotated_at

    def commit(self) -> None:
        self._conn.commit()

    def fact_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM fact_ledger").fetchone()[0])

    def observation_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM observation_archive").fetchone()[0])

    def attempts_to_mutate_history(self) -> Tuple[bool, bool]:
        """自证历史不可篡改：返回 (UPDATE 被拒, DELETE 被拒)。"""
        update_blocked = delete_blocked = False
        try:
            self._conn.execute("UPDATE fact_ledger SET summary_text='tampered'")
        except sqlite3.Error:
            update_blocked = True
        try:
            self._conn.execute("DELETE FROM fact_ledger")
        except sqlite3.Error:
            delete_blocked = True
        return update_blocked, delete_blocked

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()


# ---------------------------------------------------------------------------
# 四、P0 紧急特权硬旁路（铁律三：<=50ms，0 大模型调用，世界模型让路）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class P0Verdict:
    """P0 硬旁路裁决回执。"""

    triggered: bool
    hazard_type: Optional[str]
    evidence_ids: Tuple[str, ...]
    physical_findings: Tuple[str, ...]
    latency_ms: float
    llm_calls: int = 0
    world_model_queries: int = 0

    @property
    def is_bypass(self) -> bool:
        return self.triggered


class P0CriticalSafetyBypass:
    """纯物理阈值急救旁路（首行判定，语义引擎与大模型彻底让路）。

    判定依据全部来自硬件物理量（三轴合成冲击、自由落体前段、姿态翻转角、
    跌倒后零动时长、心率/血氧/早搏密度）与硬件关键词触发（KWS，非大模型）。
    假摔对抗（周期性冲击、无自由落体、冲击后立即恢复运动）会被物理不变式排除。
    """

    #: 严重跌倒冲击阈值（3 轴合成 G 值），与 HazardType.FALL_DETECTED 契约一致。
    FALL_G_PEAK_THRESHOLD = 4.5
    #: 心搏骤停：心率下限 / 恶性心动过速上限（bpm）。
    CARDIAC_BRADY_THRESHOLD = 35
    CARDIAC_TACHY_THRESHOLD = 190
    #: 连续室性早搏阵发密度阈值（次）。
    PVC_BURST_THRESHOLD = 5
    #: 自动体外除颤语义：跌倒后静止时长阈值（秒）。
    POST_FALL_IMMOBILITY_S = 30.0
    #: 硬件 KWS 危急词（纯字面触发，0 大模型）。
    _KWS_CRITICAL = ("救命", "救我", "打120", "叫救护车", "快叫救护车", "心脏骤停", "起不来")

    def scan(self, question: Mapping[str, Any]) -> P0Verdict:
        """入口首行：物理阈值穿透扫描（无任何大模型调用、无世界模型查询）。"""
        started = time.perf_counter()
        sensors = question.get("sensor_stream") or {}
        fragments = list(sensors.get("fragments") or [])

        evidence: List[str] = []
        findings: List[str] = []
        hazard: Optional[str] = None

        for fragment in fragments:
            fid = str(fragment.get("fragment_id", "?"))
            kind = str(fragment.get("kind", ""))
            label = str(fragment.get("label", ""))
            g_peak = _as_float(fragment.get("g_peak"))
            freefall_ms = _as_float(fragment.get("freefall_segment_ms"))
            posture_deg = _as_float(fragment.get("posture_change_deg"))
            resume_ms = _as_float(fragment.get("resume_motion_ms"))
            stillness_s = _as_float(fragment.get("post_impact_stillness_s"))
            hr = _as_float(fragment.get("hr_bpm"))
            pvc = _as_float(fragment.get("pvc_burst_count"))

            # —— 真实跌倒力学三联征：自由落体前段 + 冲顶 + 姿态大幅翻转 ——
            if (
                g_peak is not None
                and g_peak >= self.FALL_G_PEAK_THRESHOLD
                and label != "high_g_without_freefall"
                and (freefall_ms is None or freefall_ms > 0)
                and (posture_deg is None or posture_deg >= 60.0)
            ):
                hazard = HazardType.FALL_DETECTED.value
                evidence.append(fid)
                findings.append(f"自由落体后冲顶 {g_peak:.2f}g（超越 {self.FALL_G_PEAK_THRESHOLD}g 阈值）")
            if kind == "post_impact_immobility" and stillness_s is not None and stillness_s >= self.POST_FALL_IMMOBILITY_S:
                hazard = hazard or HazardType.FALL_DETECTED.value
                evidence.append(fid)
                findings.append(f"跌倒后零动 {stillness_s:.0f} 秒，未能自主起身")
            # —— 心搏骤停 / 恶性心律失常 ——
            if hr is not None and (hr <= self.CARDIAC_BRADY_THRESHOLD or hr >= self.CARDIAC_TACHY_THRESHOLD):
                hazard = hazard or HazardType.CARDIAC_ARREST.value
                evidence.append(fid)
                findings.append(f"心率 {hr:.0f}bpm 越过生命红线")
            if pvc is not None and pvc >= self.PVC_BURST_THRESHOLD and kind in {"ppg_arrhythmia", "ppg_acute_stress"}:
                hazard = hazard or HazardType.CARDIAC_ARREST.value
                evidence.append(fid)
                findings.append(f"连续室性早搏 {pvc:.0f} 次阵发")
            # —— 假摔排除：无自由落体 + 冲击后毫秒级恢复运动 ——
            if resume_ms is not None and resume_ms > 0 and (freefall_ms or 0.0) <= 0.0 and (posture_deg or 0.0) < 30.0:
                findings.append(f"片段 {fid} 冲击后 {resume_ms:.0f}ms 即恢复自主运动，物理不变式排除真实跌倒")

        # —— 硬件 KWS（关键词触发，非大模型）：被噪声掩埋的微弱求救 ——
        for snippet in list(question.get("mic_stream") or []):
            text = str(snippet.get("text", ""))
            if any(token in text for token in self._KWS_CRITICAL):
                if str(snippet.get("speaker_diarization", "")) in {"user_weak", "user"} or snippet.get("is_user_voice"):
                    hazard = hazard or HazardType.CARDIAC_ARREST.value
                    evidence.append(str(snippet.get("snippet_id", "?")))
                    findings.append("硬件 KWS 命中佩戴者微弱呼救原话")

        latency_ms = (time.perf_counter() - started) * 1000.0
        triggered = hazard is not None
        return P0Verdict(
            triggered=triggered,
            hazard_type=hazard,
            evidence_ids=tuple(dict.fromkeys(evidence)),
            physical_findings=tuple(findings),
            latency_ms=latency_ms,
            llm_calls=0,
            world_model_queries=0,
        )

    @staticmethod
    def dispatch_hardware_alarm(verdict: P0Verdict) -> Dict[str, Any]:
        """P0 直通硬件报警（微震马达 + 蜂窝直连），世界模型与持久化事务让路。"""
        if not verdict.triggered:
            return {"status": "NO_P0", "llm_calls": 0, "world_persistence_yielded": False}
        return {
            "status": "SAFETY_BYPASS_EXECUTED",
            "priority": WakePriority.P0_CRITICAL_SAFETY.value,
            "hazard_type": verdict.hazard_type,
            "first_action": "hardware_pulse",
            "bypassed_llm": True,
            "llm_calls": 0,
            "cockpit_assemblies": 0,
            "world_persistence_yielded": True,
            "latency_ms": verdict.latency_ms,
        }


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 五、领域方向词库（AIOS 3.0 清洗竞技场标准意图族）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Archetype:
    """语义原型：维度 + 意图 + 方向同义词簇 + 一句话事实骨架。"""

    intent: str
    dimension: str
    phrase: str
    keywords: Tuple[str, ...]

    def direction_cluster(self) -> Tuple[str, ...]:
        return (self.phrase,) + self.keywords


def _arch(intent: str, dimension: str, phrase: str, keywords: Sequence[str]) -> Archetype:
    return Archetype(intent=intent, dimension=dimension, phrase=phrase, keywords=tuple(keywords))


INTENT_CATALOG: Dict[str, Archetype] = {
    # ---------------- 健康 dim:health ----------------
    "SLEEP_DURATION": _arch(
        "SLEEP_DURATION", "dim:health", "佩戴者夜间睡眠时长记录",
        ("睡眠", "入睡", "就寝", "睡下", "夜间休息", "安睡", "睡眠时长", "睡了"),
    ),
    "EXERCISE_SESSION": _arch(
        "EXERCISE_SESSION", "dim:health", "佩戴者完成一段连续运动锻炼",
        ("运动", "锻炼", "健身", "跑步", "训练", "有氧", "运动时长", "周期性冲击"),
    ),
    "STAIR_CLIMB": _arch(
        "STAIR_CLIMB", "dim:health", "佩戴者爬楼梯上行运动",
        ("爬楼", "楼梯", "上楼", "登高", "台阶", "爬升"),
    ),
    "SEDENTARY_LONG": _arch(
        "SEDENTARY_LONG", "dim:health", "佩戴者长时间静坐少动",
        ("久坐", "静坐", "少动", "久坐不动", "缺乏活动", "静止"),
    ),
    "CARDIAC_PVC_BURST": _arch(
        "CARDIAC_PVC_BURST", "dim:health", "佩戴者发生室性早搏连续阵发（心律失常）",
        ("室性早搏", "早搏", "室早", "心律失常", "连续阵发", "代偿间歇", "心律不齐"),
    ),
    "RESTING_TACHYCARDIA": _arch(
        "RESTING_TACHYCARDIA", "dim:health", "佩戴者静息状态持续心动过速",
        ("心动过速", "心率过快", "静息心率升高", "心跳快", "心率偏快"),
    ),
    "HIDDEN_CARDIAC_CRISIS": _arch(
        "HIDDEN_CARDIAC_CRISIS", "dim:health", "佩戴者出现隐性心血管危急征兆（言语否认但生理证据矛盾）",
        ("嘴硬否认", "隐瞒症状", "疑似心梗", "喘不上气", "胸痛", "大汗", "心前区不适", "急性心血管事件"),
    ),
    "MEDICAL_APPOINTMENT": _arch(
        "MEDICAL_APPOINTMENT", "dim:health", "佩戴者预约门诊或复诊",
        ("预约就诊", "复诊", "复查", "挂号", "门诊预约", "随访", "定期随访", "就诊安排"),
    ),
    "MEDICATION_REMINDER": _arch(
        "MEDICATION_REMINDER", "dim:health", "佩戴者用药提醒",
        ("服药提醒", "用药提醒", "按时吃药", "药物剂量", "服药时间", "医嘱用药"),
    ),
    "LAB_CRITICAL_VALUE": _arch(
        "LAB_CRITICAL_VALUE", "dim:health", "佩戴者检验结果达到危急值",
        ("检验危急值", "危急值", "化验异常", "检验结果危急", "指标严重超标", "需立即就诊"),
    ),
    "REAL_MEDICAL_INTENT": _arch(
        "REAL_MEDICAL_INTENT", "dim:health", "佩戴者主动表达真实就医诉求",
        ("就医诉求", "看病", "想去医院", "挂个号", "身体不适就诊", "求医"),
    ),
    # ---------------- 财务 dim:finance ----------------
    "DEBT_BORROWING": _arch(
        "DEBT_BORROWING", "dim:finance", "佩戴者与他人发生借贷往来",
        ("借款", "借钱", "债务", "借条", "欠款", "资金周转", "借贷纠纷"),
    ),
    "REPAYMENT_PROMISE": _arch(
        "REPAYMENT_PROMISE", "dim:finance", "他人向佩戴者作出还款承诺（含明确金额与日期）",
        ("还款承诺", "约定还款", "下月还钱", "结清欠款", "还钱约定", "承诺还款", "白纸黑字"),
    ),
    "BANK_LARGE_TRANSFER": _arch(
        "BANK_LARGE_TRANSFER", "dim:finance", "佩戴者账户发生大额资金变动",
        ("大额转账", "银行转账", "大额到账", "账户入账", "大额支出", "资金划转"),
    ),
    "SMALL_TRANSFER": _arch(
        "SMALL_TRANSFER", "dim:finance", "佩戴者发生小额收付款",
        ("小额转账", "收款", "付款", "红包", "日常支付", "账单支付"),
    ),
    "BILL_REPAYMENT": _arch(
        "BILL_REPAYMENT", "dim:finance", "佩戴者账单还款",
        ("账单还款", "信用卡还款", "还款日", "分期还款", "逾期还款", "账单结清"),
    ),
    "UTILITY_PAYMENT": _arch(
        "UTILITY_PAYMENT", "dim:finance", "佩戴者生活缴费",
        ("水电费", "燃气费", "物业费", "生活缴费", "缴费通知", "供暖费"),
    ),
    # ---------------- 社会 dim:social ----------------
    "SOCIAL_CHAT": _arch(
        "SOCIAL_CHAT", "dim:social", "佩戴者与熟人的日常社交交谈",
        ("日常闲聊", "社交对话", "熟人交谈", "寒暄", "聊天", "家常交流"),
    ),
    "ARGUMENT_CONFLICT": _arch(
        "ARGUMENT_CONFLICT", "dim:social", "佩戴者与他人发生激烈言语冲突",
        ("吵架", "争吵", "冲突", "口角", "争执", "吵闹", "红脸", "言语冲突", "互不相让"),
    ),
    "DRUNK_BRAGGING": _arch(
        "DRUNK_BRAGGING", "dim:social", "佩戴者酒后夸大言辞（吹牛，不构成真实计划）",
        ("酒后吹牛", "吹牛", "醉话", "夸大其词", "酒精线索升高", "言语夸张", "非真实计划"),
    ),
    "MEDIA_PLAYBACK_NOISE": _arch(
        "MEDIA_PLAYBACK_NOISE", "dim:social", "录音中的语句来自媒体外放，非佩戴者现场真实对话",
        ("媒体外放", "非真实对话", "影视台词", "外放噪声", "短视频外放", "不可提纯为事实"),
    ),
    "VOICE_BINDING_USER": _arch(
        "VOICE_BINDING_USER", "dim:social", "声纹聚类将佩戴者本人稳定锚定为长期声纹",
        ("佩戴者本人声纹", "本人声纹确认", "锁定佩戴者", "声纹归属机主", "机主声音", "确认是本人"),
    ),
    "VOICE_BINDING_KEY_CONTACT": _arch(
        "VOICE_BINDING_KEY_CONTACT", "dim:social", "声纹聚类绑定核心关键联系人",
        ("核心联系人", "关键联系人", "声纹绑定", "亲友声纹", "稳定绑定", "重要他人"),
    ),
    # ---------------- 家庭 dim:family ----------------
    "FAMILY_DAILY": _arch(
        "FAMILY_DAILY", "dim:family", "佩戴者与家人的日常亲情互动",
        ("家人问候", "家人日常", "家人联系", "亲情互动", "家庭日常", "和家人说话", "家常问候"),
    ),
    "CHILD_SCHOOL": _arch(
        "CHILD_SCHOOL", "dim:family", "佩戴者处理子女学业相关事务",
        ("子女上学", "孩子补课", "家长会", "老师沟通", "学业状况", "孩子成绩", "学校事务"),
    ),
    "FAMILY_ENTRUSTMENT": _arch(
        "FAMILY_ENTRUSTMENT", "dim:family", "佩戴者向家人作出财产托付性交待",
        ("家属托付", "财产交待", "密码交待", "遗属安排", "托付家人", "存折交代"),
    ),
    # ---------------- 事业 dim:career ----------------
    "WORK_OVERTIME": _arch(
        "WORK_OVERTIME", "dim:career", "佩戴者被要求加班赶工",
        ("加班", "加个班", "赶工", "连夜赶活", "工时延长", "必须今天交"),
    ),
    "WORK_COORDINATION": _arch(
        "WORK_COORDINATION", "dim:career", "佩戴者参与工作协调安排",
        ("工作协调", "任务对接", "会议安排", "排期协调", "工作部署", "对接方案"),
    ),
    "REAL_RESIGNATION": _arch(
        "REAL_RESIGNATION", "dim:career", "佩戴者做出真实辞职决定",
        ("辞职", "离职决定", "不干了", "辞职信", "辞去工作", "解除劳动关系"),
    ),
    "NDA_CONFIDENTIALITY": _arch(
        "NDA_CONFIDENTIALITY", "dim:career", "佩戴者作出商业保密承诺（含违约责任）",
        ("保密承诺", "保密约定", "不得外泄", "商业机密", "保密条款", "违约责任"),
    ),
    "SIGNING_SCHEDULE": _arch(
        "SIGNING_SCHEDULE", "dim:career", "佩戴者确认签约日程",
        ("签约日程", "合同签署", "签约安排", "签字时间", "商务签约", "协议签署"),
    ),
    # ---------------- 法律 dim:legal ----------------
    "COURT_SUMMONS": _arch(
        "COURT_SUMMONS", "dim:legal", "佩戴者收到法院传票／应诉通知",
        ("法院传票", "应诉通知", "开庭传票", "被起诉", "司法通知", "案件受理"),
    ),
    "LAWYER_LETTER": _arch(
        "LAWYER_LETTER", "dim:legal", "佩戴者收到律师函",
        ("律师函", "律师声明", "法律意见", "委托律师", "催告函"),
    ),
    # ---------------- 安全 dim:safety ----------------
    "FALL_IMPACT": _arch(
        "FALL_IMPACT", "dim:safety", "佩戴者发生真实跌倒冲击",
        ("摔倒", "跌倒", "倒地", "摔伤", "坠落", "栽倒", "冲击峰值", "跌倒后静止"),
    ),
    "FALL_IMPACT_FAKED": _arch(
        "FALL_IMPACT_FAKED", "dim:safety", "高 G 冲击经物理不变式判定为日常动作而非真实跌倒",
        ("非真实跌倒", "并非摔倒", "日常甩腕", "误判为跌倒", "无自由落体", "冲击后立即恢复运动"),
    ),
    "FRAUD_ATTEMPT": _arch(
        "FRAUD_ATTEMPT", "dim:safety", "佩戴者遭遇电信诈骗话术",
        ("诈骗电话", "冒充公检法", "疑似诈骗", "可疑来电", "安全账户", "话术诈骗", "改号来电"),
    ),
    "VOICE_IMPERSONATION_FRAUD": _arch(
        "VOICE_IMPERSONATION_FRAUD", "dim:safety", "佩戴者遭遇冒充熟人／领导的声纹诈骗",
        ("冒充熟人", "声纹冒充", "冒充领导", "换号借钱", "合成语音诈骗", "身份冒用"),
    ),
    "TRAFFIC_RISK": _arch(
        "TRAFFIC_RISK", "dim:safety", "佩戴者处于交通风险场景",
        ("交通风险", "道路危险", "车辆临近", "急刹避让", "闯红灯", "路口险情"),
    ),
    "WEAK_SOS": _arch(
        "WEAK_SOS", "dim:safety", "佩戴者发出被噪声掩埋的微弱求救",
        ("求救", "呼救", "救命", "打120", "微弱求救", "呼救信号", "不可当噪声剪掉"),
    ),
    # ---------------- 环境 dim:environment ----------------
    "BAROMETRIC_STORM": _arch(
        "BAROMETRIC_STORM", "dim:environment", "气压短时骤降，恶劣天气临近",
        ("气压骤降", "暴雨将至", "气压变化", "恶劣天气", "转入室内避雨", "气压波动"),
    ),
    "BAROMETRIC_STABLE": _arch(
        "BAROMETRIC_STABLE", "dim:environment", "环境气压平稳",
        ("气压平稳", "气压稳定", "环境稳定", "气压无异常"),
    ),
    "WEATHER_EXPOSURE": _arch(
        "WEATHER_EXPOSURE", "dim:environment", "佩戴者处于户外天气暴露环境",
        ("户外暴露", "天气暴露", "高温暴晒", "寒冷暴露", "风吹雨淋", "户外环境"),
    ),
    # ---------------- 生活 dim:daily ----------------
    "DAILY_COMMUTE": _arch(
        "DAILY_COMMUTE", "dim:daily", "佩戴者通勤出行",
        ("通勤", "上下班出行", "日常出行", "路途", "往返路程", "交通出行"),
    ),
    "MEAL_EVENT": _arch(
        "MEAL_EVENT", "dim:daily", "佩戴者用餐事件",
        ("用餐", "吃饭", "点餐", "餐饮", "就餐", "外卖取餐"),
    ),
    # ---------------- 物流 dim:logistics ----------------
    "DELIVERY_EVENT": _arch(
        "DELIVERY_EVENT", "dim:logistics", "佩戴者取件／收寄快递",
        ("快递取件", "包裹签收", "收件", "取件码", "驿站取货", "物流到件"),
    ),
    # ---------------- 情绪 dim:emotion ----------------
    "VERBAL_VENT": _arch(
        "VERBAL_VENT", "dim:emotion", "佩戴者口头宣泄情绪，无真实行动意图",
        ("口头禅", "情绪发泄", "气话", "非真实意图", "吐槽", "发牢骚", "习惯性抱怨", "嘴上说说", "宣泄"),
    ),
}

#: 结构化传感器 (kind, label) → 意图（设备侧派生标签，物理量语义唯一映射）。
SENSOR_KIND_LABEL_INTENT: Dict[Tuple[str, str], str] = {
    ("derived_activity_segment", "sleep_duration"): "SLEEP_DURATION",
    ("derived_activity_segment", "exercise_session"): "EXERCISE_SESSION",
    ("derived_activity_segment", "stair_climb"): "STAIR_CLIMB",
    ("derived_activity_segment", "sedentary_long"): "SEDENTARY_LONG",
    ("derived_activity_segment", "daily_commute"): "DAILY_COMMUTE",
    ("derived_activity_segment", "traffic_risk"): "TRAFFIC_RISK",
    ("derived_activity_segment", "weather_exposure"): "WEATHER_EXPOSURE",
    ("derived_activity_segment", "barometric_stable"): "BAROMETRIC_STABLE",
    ("barometric_plunge", "rapid_pressure_drop"): "BAROMETRIC_STORM",
    ("gps_shelter", "indoor_shelter"): "BAROMETRIC_STORM",
    ("symptom_correlation", "pressure_triggered_pain"): "BAROMETRIC_STORM",
    ("imu_impact", "hard_impact_freefall_preceded"): "FALL_IMPACT",
    ("post_impact_immobility", "post_fall_stillness"): "FALL_IMPACT",
    ("ppg_response", "post_fall_hr_surge"): "FALL_IMPACT",
    ("imu_impact", "high_g_without_freefall"): "FALL_IMPACT_FAKED",
    ("imu_periodic_impact", "strictly_periodic_impact"): "EXERCISE_SESSION",
    ("ppg_arrhythmia", "pvc_burst_nocturnal"): "CARDIAC_PVC_BURST",
    ("sleep_context", "sleep_stage_n2"): "CARDIAC_PVC_BURST",
    ("ppg_resting_tachycardia", "sustained_resting_tachycardia"): "RESTING_TACHYCARDIA",
    ("activity_context", "verified_sedentary"): "RESTING_TACHYCARDIA",
    ("ppg_acute_stress", "acute_cardiac_stress"): "HIDDEN_CARDIAC_CRISIS",
}

#: 传感器噪声片段（步态微动/刷卡/颠簸等）——恒为垃圾。
SENSOR_NOISE_KINDS = frozenset({"imu_window"})

#: APP 频道分类 → 意图（结构化 category 唯一映射）。
APP_CATEGORY_INTENT: Dict[str, str] = {
    "med": "MEDICATION_REMINDER",
    "bill": "BILL_REPAYMENT",
    "delivery": "DELIVERY_EVENT",
    "family": "FAMILY_DAILY",
    "meal": "MEAL_EVENT",
    "work": "WORK_COORDINATION",
    "medical": "MEDICAL_APPOINTMENT",
    "smallpay": "SMALL_TRANSFER",
    "utility": "UTILITY_PAYMENT",
    "phishing": "FRAUD_ATTEMPT",
    "conflicting_evidence": "DEBT_BORROWING",
}

#: ``critical_notice`` 高危通知需二次语义判别（银行/法院/化验/律师/签约）。
CRITICAL_NOTICE_RULES: Tuple[Tuple[str, str], ...] = (
    ("COURT_SUMMONS", r"法院|传票|开庭|应诉|案号|司法"),
    ("LAWYER_LETTER", r"律师函|律师事务所|法律意见|催告"),
    ("LAB_CRITICAL_VALUE", r"检验|化验|危急值|mmol|参考区间|血液科|指标"),
    ("BANK_LARGE_TRANSFER", r"转账|到账|入账|汇款|银行卡|大额|资金"),
    ("SIGNING_SCHEDULE", r"签约|签署|合同|协议|日程"),
)

#: APP 垃圾频道（营销/验证码/砍一刀/表情包刷屏/群聊）。
APP_JUNK_CATEGORIES = frozenset(
    {"wechat_seller", "moments", "pinduoduo", "push", "wechat_group", "sms_code", "sms_marketing"}
)

#: MIC 场景 → 意图（None 表示需文本二次判别）。
MIC_SCENE_INTENT: Dict[str, Optional[str]] = {
    "media_playback": "MEDIA_PLAYBACK_NOISE",
    "buried_in_noise": "WEAK_SOS",
    "heated_dialogue": "ARGUMENT_CONFLICT",
    "meeting_room_dialogue": "NDA_CONFIDENTIALITY",
    "quiet_home_dialogue": None,
    "foreground_dialogue": None,
    "phone_call": None,
}

#: MIC 噪声场景（街道/商场/家电/地铁等环境杂音切片）——恒为垃圾。
MIC_NOISE_SCENES = frozenset(
    {
        "street",
        "home_night",
        "appliance",
        "office",
        "mall",
        "restaurant",
        "transit",
        "market_early",
        "school",
        "hospital",
        "renovation",
        "outside_car",
        "square_dance",
    }
)

#: MIC 证据场景——即便文本是拟声描述，也可能是关键证据（微弱呼吸/媒体外放），不可剪枝。
MIC_KEEP_SCENES = frozenset(
    {
        "foreground_dialogue",
        "phone_call",
        "media_playback",
        "buried_in_noise",
        "quiet_home_dialogue",
        "meeting_room_dialogue",
        "heated_dialogue",
    }
)

#: 证据保护标记（硬证据词：通知/对话一旦命中且为正式通知体，禁止被垃圾模式误剪）。
PROTECTED_EVIDENCE_MARKERS: Tuple[str, ...] = (
    "法院", "传票", "开庭", "应诉", "检验", "化验", "危急值", "参考区间", "律师函",
    "已成功预约", "挂号", "复诊", "门诊", "缴费", "水电费", "电费", "燃气费", "租金",
    "入账", "到账", "取件码", "借条", "还款", "保密", "违约金", "密码是", "存折",
    "安全账户", "配合调查", "危急值标准",
)

#: 正式通知体特征（机构口吻/模板化抬头），用于区分真实凭证与营销刷屏。
FORMAL_NOTICE_MARKERS: Tuple[str, ...] = (
    "【", "您好", "您尾号", "通知", "提醒", "已成功", "请及时", "结果", "已达",
)

#: 上游标记为垃圾频道、但文本自身已是硬证据的例外（拒绝把真凭证当营销删掉）。
APP_JUNK_CATEGORY_EVIDENCE_EXCEPTION: Tuple[str, ...] = (
    "入账", "到账", "取件码", "借条", "危急值", "传票", "开庭", "律师函",
)

#: 垃圾语义硬特征（促销叫卖/公共广播/环境拟声）。
NOISE_TEXT_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^[（(].*[)）]$"),
    re.compile(r"风噪|底噪|白噪声|环境音|咔哒|窸窣|嗡鸣|轰鸣|摩擦声|敲击|脚步声|鼾声|呼噜|拖动"),
    re.compile(r"尊敬的顾客|敬请谅解|闭店|大促|促销|特价|买一送|扫码关注|欢迎光临"),
    re.compile(r"列车即将|报站|下车的乘客|候车|站台|请勿"),
    re.compile(r"就诊|取药|检验报告|候诊|分诊|诊室|挂号处"),
    re.compile(r"了解一下|需要办理吗|办卡|首付|分期|优惠|折扣|送您|领取|关注公众号"),
    re.compile(r"砍一刀|助力|拼单|免费领|红包雨|提现"),
    re.compile(r"验证码|校验码|动态密码|退订回T"),
)

#: 营销/诈骗/生活短信语义特征（垃圾）。
JUNK_MESSAGE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"验证码|校验码|动态码|退订"),
    re.compile(r"提现|邀请.{0,4}好友|恭喜.{0,6}获得|即可领取|还有机会|再邀请"),
    re.compile(r"砍一刀|助力|免费领|立即领取|点击.{0,8}链接|点击.{0,6}领取"),
    re.compile(r"优惠|促销|特价|折扣|大促|秒杀|限时|中奖|抽奖"),
    re.compile(r"贷款|办理|额度提升|信用卡提额|需要办理吗"),
    re.compile(r"表情包|\[链接\]|\[图片\]|转发|点个赞|哈哈哈"),
    re.compile(r"热搜|运势|星座|天气提醒"),
)

#: MIC 文本 → 意图（按特异性降序匹配；词表来自在带对话池的工程师标注）。
MIC_TEXT_INTENT_RULES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("WEAK_SOS", re.compile(r"救命|打我?120|叫救护车|起不来|救我一?下|有人吗.{0,6}摔|动不了")),
    ("FRAUD_ATTEMPT", re.compile(
        r"安全账户|配合调查|洗钱|违禁品|海关|公检法|市公安局|社保中心|医保卡.{0,8}盗刷|核实身份"
        r"|快递.{0,6}违禁|账户.{0,6}冻结|解冻|涉嫌"
    )),
    ("VOICE_IMPERSONATION_FRAUD", re.compile(r"冒充|我是你(儿子|女儿|领导|同学|朋友)|换新号|你猜猜我是谁|借点钱急用")),
    ("NDA_CONFIDENTIALITY", re.compile(r"保密条款|保密|泄露出去要赔|外泄|别往外说|把嘴管住|竞业")),
    ("FAMILY_ENTRUSTMENT", re.compile(r"密码是|存折|卡里那|都留给你|万一.{0,8}(三长两短|有个啥事)|交给你保管|留给你|交代在前")),
    ("REAL_RESIGNATION", re.compile(r"辞职|不干了|离职|辞呈")),
    ("REPAYMENT_PROMISE", re.compile(r"还[我你]|借条我写了|下个月?\s*\d{1,2}\s*号.{0,6}还|还款|说好了|白纸黑字|钱我下周")),
    ("DEBT_BORROWING", re.compile(r"借[你我他]|欠款|欠[你我]|周转|垫付|讨薪|工钱|劳务费|催款")),
    ("COURT_SUMMONS", re.compile(r"法院|传票|开庭|应诉|官司|案号")),
    ("LAWYER_LETTER", re.compile(r"律师函|律师所|法律意见|委托律师")),
    ("LAB_CRITICAL_VALUE", re.compile(r"危急值|参考区间|检验结果|化验结果|指标异常|血液科")),
    ("BANK_LARGE_TRANSFER", re.compile(r"入账|大额|转账|汇款|到账|银行卡")),
    ("SIGNING_SCHEDULE", re.compile(r"签约|签署|合同|盖章|公章|协议")),
    ("MEDICAL_APPOINTMENT", re.compile(r"复诊|复查|挂号|门诊|就诊|空腹|随访|拍片|提醒您.{0,3}天后到")),
    ("MEDICATION_REMINDER", re.compile(r"吃药|服药|按时用药|剂量|用药提醒|药别停")),
    ("DELIVERY_EVENT", re.compile(r"取件码|货架|快递|包裹|签收|驿站|派送|取件")),
    ("CHILD_SCHOOL", re.compile(r"老师[：:]\s*孩子|孩子最近.{0,12}(有点状况|方面)|家长这边也配合|家长会|补课费")),
    ("WORK_OVERTIME", re.compile(r"加个班|加班|辛苦一下|必须交|赶工|通宵")),
    ("WORK_COORDINATION", re.compile(r"会议|方案|排期|对接|汇报|项目|协调|部署|进度")),
    ("UTILITY_PAYMENT", re.compile(r"水费|电费|燃气|物业费|取暖费|缴费")),
    ("FAMILY_DAILY", re.compile(r"晚上想吃什么|顺路买点|晚上回来吃饭|买菜|回家|家里|爸妈|老伴")),
    ("MEAL_EVENT", re.compile(r"您点的|慢用|点餐|外卖取餐|用餐|买单|上菜")),
    ("DAILY_COMMUTE", re.compile(r"通勤|上班路上|地铁|公交|打车|路上")),
    ("SOCIAL_CHAT", re.compile(r".*")),
)

#: UTT 文本 → 意图（按特异性降序匹配；词表来自在带原话池的工程师标注）。
UTT_TEXT_INTENT_RULES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("HIDDEN_CARDIAC_CRISIS", re.compile(
        r"没事.{0,10}(歇会儿|缓一下)|不用叫救护车|别大惊小怪|有点闷|老毛病了.{0,8}忍忍|别告诉家里人"
        r"|粗重喘息|喘息声|呼吸窘迫|大汗|冷汗|胸口?痛|捂胸|憋气|喘不上气|吸气费力"
    )),
    ("WEAK_SOS", re.compile(r"救命|打120|叫救护车|起不来|喘不上气")),
    ("REAL_MEDICAL_INTENT", re.compile(r"挂号|去医院|看病|去查个|得去查|就医|查个血压|看看病")),
    ("REAL_RESIGNATION", re.compile(r"辞职|不干了|离职|辞呈|干不下去")),
    ("VERBAL_VENT", re.compile(r"不想活|烦死|累死|没意思|气死|活不下去|扔了不管|爱咋咋地|算不算工伤")),
    ("DRUNK_BRAGGING", re.compile(r"收购|赚.{0,6}万|发大财|我认识|一夜暴富|算什么|每人发一|发达了")),
    ("FAMILY_ENTRUSTMENT", re.compile(r"留给|密码是|三长两短|存折|交代在前面")),
    ("REPAYMENT_PROMISE", re.compile(r"还你|还我|下周一定")),
    ("WORK_COORDINATION", re.compile(r"项目|方案|汇报|会议|对接")),
    ("DAILY_COMMUTE", re.compile(r"上班|通勤|地铁|出门")),
    ("FAMILY_DAILY", re.compile(r"家里|孩子|妈|爸|老婆|老公|晚饭")),
    ("SOCIAL_CHAT", re.compile(r".*")),
)

#: UTT 垃圾标签（酒后吹牛/口头禅/玩笑/哼歌/自语）——上游情绪标注。
UTT_JUNK_TAGS = frozenset({"自语", "口头禅发泄", "酒后吹牛", "玩笑", "哼歌", "吐槽", "自嘲"})

#: UTT 危机线索（语义/生理/标注三路合取）：命中即不可剪，保留为危象证据。
UTT_CRISIS_TONES = frozenset({"生理性窘迫", "强撑否认", "痛苦", "濒死感", "恐慌"})
UTT_CRISIS_NOTE_MARKERS: Tuple[str, ...] = (
    "呼吸窘迫", "濒危", "危机", "硬冲突", "矛盾", "心肌", "心绞痛", "喘息", "大汗", "缺氧",
)
UTT_CRISIS_TEXT_RE = re.compile(r"喘息|呼吸窘迫|大汗|冷汗|胸口?痛|捂胸|憋气|喘不上气|吸气费力|胸闷|起不来|动不了")

#: 佩戴者姓名抽取模式（跨题身份记忆：手环长期记忆中的机主称谓）。
NAME_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"【[^】]{0,12}】\s*(?P<name>[\u4e00-\u9fa5]{2,3})\s*(?:您好|你好)"),
    re.compile(r"(?P<name>[\u4e00-\u9fa5]{2,3})\s*(?:先生|女士|同志)\s*(?:您好|你好)"),
    re.compile(r"佩戴者\s*(?P<name>[\u4e00-\u9fa5]{2,3})"),
    re.compile(r"我是\s*(?P<name>[\u4e00-\u9fa5]{2,3})(?![的地得]|们)"),
    re.compile(r"^(?P<name>[\u4e00-\u9fa5]{2,3})\s*[：:]"),
)

#: 常见姓氏（用于姓名抽取的精确率守卫）。
COMMON_SURNAMES = frozenset(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)

#: 结构化角色字段中的别名（小周/阿福/老王/陈叔 等）——仅角色字段可用。
ALIAS_NAME_PREFIXES = ("小", "阿", "老")

#: 非姓名的干扰词（称谓/机构/职业），避免跨题记忆被污染。
NAME_STOPWORDS = frozenset(
    {
        "医院", "银行", "法院", "中心", "公司", "老师", "护士", "店员", "医生", "客服", "快递",
        "物业", "警察", "司机", "领导", "主任", "经理", "师傅", "先生", "女士", "同志", "朋友",
        "家人", "孩子", "家长", "同学", "小区", "物业", "商家", "客户", "官方", "平台", "驿站",
        "派出所", "居委会", "社区", "集团", "超市", "大学", "中学", "小学", "机场", "车站",
    }
)


# ---------------------------------------------------------------------------
# 六、跨题身份记忆图谱（迭代升级 #2：机主身份的长期记忆锚定）
# ---------------------------------------------------------------------------


class WearerIdentityMemory:
    """跨题身份记忆：从**在带输入流**中锚定各设备的机主姓名（手环长期记忆）。

    手环佩戴多年，机主姓名会在历史消息、通话称谓、医护称呼中反复出现；
    本图谱只消费输入流（绝不含标答字段），把「设备 → 机主姓名」沉淀为长期记忆，
    供事实提纯阶段补全人物锚点，避免"张冠李戴"与人物缺失。
    """

    def __init__(self) -> None:
        self._by_device: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _device_key(question: Mapping[str, Any]) -> str:
        sensors = question.get("sensor_stream") or {}
        device = sensors.get("device_id") or sensors.get("device_key")
        if device:
            return str(device)
        persona = question.get("persona_tag") or question.get("persona_id")
        if persona:
            return str(persona)
        # 无设备/人物标识的题目不进入身份记忆（避免跨人污染）
        return ""

    @staticmethod
    def _iter_texts(question: Mapping[str, Any]) -> Iterator[str]:
        for snippet in (question.get("mic_stream") or []):
            text = snippet.get("text")
            if isinstance(text, str):
                yield text
        for message in (question.get("app_message_stream") or []):
            for key in ("content", "sender"):
                value = message.get(key)
                if isinstance(value, str):
                    yield value
        for utterance in (question.get("user_dialogue_stream") or []):
            text = utterance.get("raw_speech")
            if isinstance(text, str):
                yield text
        sensors = question.get("sensor_stream") or {}
        for fragment in (sensors.get("fragments") or []):
            for key in ("summary", "note", "label_zh"):
                value = fragment.get(key)
                if isinstance(value, str):
                    yield value

    @classmethod
    def _candidates(cls, text: str) -> Iterator[str]:
        for pattern in NAME_PATTERNS:
            for match in pattern.finditer(text):
                candidate = match.group("name")
                if cls._is_name(candidate):
                    yield candidate

    @staticmethod
    def _is_name(candidate: str) -> bool:
        if not 2 <= len(candidate) <= 3:
            return False
        if candidate in NAME_STOPWORDS:
            return False
        if candidate[0] not in COMMON_SURNAMES:
            return False
        return all("\u4e00" <= ch <= "\u9fff" for ch in candidate)

    @staticmethod
    def _is_structured_token(candidate: str) -> bool:
        """结构化字段（来信人/声纹角色/应用名）中的可核验称谓：
        允许中英混排（阿May / Amy）、带前缀的职能称谓（教务处老周 / 钱合伙人）。"""
        value = candidate.strip()
        if not 2 <= len(value) <= 10:
            return False
        if value in NAME_STOPWORDS or value.isdigit():
            return False
        has_letter = any(ch.isalpha() for ch in value)
        if not has_letter:
            return False
        return all(ch.isalnum() or ch in "·-－_" for ch in value)

    @staticmethod
    def _is_role_name(candidate: str) -> bool:
        """结构化角色字段（声纹 role / known_bindings）中的姓名或长期称谓别名。"""
        if not 2 <= len(candidate) <= 4:
            return False
        if candidate in NAME_STOPWORDS:
            return False
        if not all("\u4e00" <= ch <= "\u9fff" for ch in candidate):
            return False
        if candidate[0] in COMMON_SURNAMES or candidate[0] in ALIAS_NAME_PREFIXES:
            return True
        return 2 <= len(candidate) <= 3 and candidate.endswith(("叔", "婶", "姨", "伯", "总", "哥", "姐"))

    def observe(self, question: Mapping[str, Any]) -> None:
        """把一题的输入流沉淀进身份记忆（只增不改，权重累计）。"""
        device = self._device_key(question)
        if not device:
            return
        bucket = self._by_device.setdefault(device, {})
        for text in self._iter_texts(question):
            for candidate in self._candidates(text):
                bucket[candidate] = bucket.get(candidate, 0) + 1

    def build_from_bank(self, questions: Iterable[Mapping[str, Any]]) -> "WearerIdentityMemory":
        for question in questions:
            self.observe(question)
        return self

    def name_for(self, question: Mapping[str, Any]) -> Optional[str]:
        """返回该设备在长期记忆中出现次数最多的机主姓名。"""
        bucket = self._by_device.get(self._device_key(question))
        if not bucket:
            return None
        return max(bucket.items(), key=lambda kv: (kv[1], kv[0]))[0]

    def device_count(self) -> int:
        return len(self._by_device)

    def snapshot(self) -> Dict[str, str]:
        return {device: max(b.items(), key=lambda kv: kv[1])[0] for device, b in self._by_device.items() if b}


# ---------------------------------------------------------------------------
# 七、题面片段视图与垃圾裁决
# ---------------------------------------------------------------------------


@dataclass
class ItemView:
    """一道题内的单个多模态片段（垃圾/证据裁决的最小单位）。"""

    item_id: str
    modality: str
    payload: Mapping[str, Any]
    text: str = ""
    is_evidence: bool = False
    intent_hint: Optional[str] = None
    junk_reason: str = ""
    salience: float = 0.0
    raw_bytes: bytes = b""

    @property
    def evidence_weight(self) -> float:
        return 1.0 if self.is_evidence else 0.0


def iter_items(question: Mapping[str, Any], *, blinded: bool = True) -> List[ItemView]:
    """把一道题摊平为片段列表（盲化模式下不含标答字段）。"""
    source = strip_ground_truth(question) if blinded else dict(question)
    items: List[ItemView] = []

    sensors = source.get("sensor_stream") or {}
    for fragment in (sensors.get("fragments") or []):
        item_id = str(fragment.get("fragment_id", ""))
        if not item_id:
            continue
        items.append(
            ItemView(
                item_id=item_id,
                modality="sensor",
                payload=fragment,
                text=str(fragment.get("summary") or fragment.get("note") or ""),
                raw_bytes=json.dumps(fragment, ensure_ascii=False).encode("utf-8"),
            )
        )
    for snippet in (source.get("mic_stream") or []):
        item_id = str(snippet.get("snippet_id", ""))
        if not item_id:
            continue
        items.append(
            ItemView(
                item_id=item_id,
                modality="mic",
                payload=snippet,
                text=str(snippet.get("text") or ""),
                raw_bytes=json.dumps(snippet, ensure_ascii=False).encode("utf-8"),
            )
        )
    voiceprint = source.get("voiceprint_cluster") or {}
    for speaker in (voiceprint.get("speakers") or []):
        item_id = str(speaker.get("speaker_frag_id", ""))
        if not item_id:
            continue
        items.append(
            ItemView(
                item_id=item_id,
                modality="voiceprint",
                payload=speaker,
                text=str(speaker.get("role") or ""),
                raw_bytes=json.dumps(speaker, ensure_ascii=False).encode("utf-8"),
            )
        )
    for message in (source.get("app_message_stream") or []):
        item_id = str(message.get("msg_id", ""))
        if not item_id:
            continue
        items.append(
            ItemView(
                item_id=item_id,
                modality="app",
                payload=message,
                text=str(message.get("content") or ""),
                raw_bytes=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            )
        )
    for utterance in (source.get("user_dialogue_stream") or []):
        item_id = str(utterance.get("utterance_id", ""))
        if not item_id:
            continue
        items.append(
            ItemView(
                item_id=item_id,
                modality="utt",
                payload=utterance,
                text=str(utterance.get("raw_speech") or ""),
                raw_bytes=json.dumps(utterance, ensure_ascii=False).encode("utf-8"),
            )
        )
    return items


class JunkPolicy:
    """端侧垃圾裁决：多模态物理特征 + 语义模式双通道，宁删噪声、绝不删证据。"""

    def __init__(self, *, use_inband_labels: bool = True) -> None:
        #: 消融开关：关闭上游标注依赖（scene/category/junk_tag 等），验证纯语义通道能力。
        self.use_inband_labels = use_inband_labels

    # -- 各模态裁决 ---------------------------------------------------------
    def decide_sensor(self, item: ItemView) -> Tuple[bool, str]:
        kind = str(item.payload.get("kind", ""))
        if kind in SENSOR_NOISE_KINDS:
            return True, "50Hz 步态/微动窗口噪声（无认知价值）"
        if kind in {"derived_activity_segment", "imu_impact", "imu_periodic_impact", "post_impact_immobility",
                    "ppg_response", "ppg_arrhythmia", "ppg_resting_tachycardia", "sleep_context",
                    "activity_context", "barometric_plunge", "gps_shelter", "ppg_acute_stress",
                    "symptom_correlation"}:
            return False, "设备派生事件片段（具备认知价值，保留）"
        g_peak = _as_float(item.payload.get("g_peak"))
        if g_peak is not None and g_peak >= 2.0:
            return False, "高 G 物理冲击片段（保留待判）"
        return True, "无可提纯语义的传感器碎片"

    def decide_mic(self, item: ItemView) -> Tuple[bool, str]:
        text = item.text
        scene = str(item.payload.get("scene", "")) if self.use_inband_labels else ""
        if scene in MIC_KEEP_SCENES:
            if scene == "media_playback":
                return False, "媒体外放：须判定为「非真实对话」事实而非剪枝"
            if scene == "buried_in_noise":
                return False, "被噪声掩埋的微弱人声：潜藏求救信号，绝不剪枝"
            return False, "前景/私密/冲突证据场景对话（保留提纯）"
        if any(p.search(text) for p in NOISE_TEXT_PATTERNS):
            return True, "环境杂音/公共广播/营销叫卖碎片（物理剪枝）"
        if self.use_inband_labels and scene in MIC_NOISE_SCENES:
            return True, f"上游场景判定为噪声场景 {scene}（物理剪枝）"
        if self.use_inband_labels and item.payload.get("is_background_chatter"):
            return True, "背景闲聊（非佩戴者有效语义，物理剪枝）"
        intent = self._mic_intent(item)
        if intent == "MEDIA_PLAYBACK_NOISE":
            return False, "媒体外放必须判定为「非真实对话」事实而非剪枝"
        if intent in {"WEAK_SOS", "FRAUD_ATTEMPT", "VOICE_IMPERSONATION_FRAUD", "ARGUMENT_CONFLICT",
                      "NDA_CONFIDENTIALITY", "REPAYMENT_PROMISE", "DEBT_BORROWING", "FAMILY_ENTRUSTMENT",
                      "REAL_RESIGNATION", "LAB_CRITICAL_VALUE", "COURT_SUMMONS", "LAWYER_LETTER"}:
            return False, f"高价值对话语义（{intent}），必须保留"
        if not text.strip():
            return True, "空文本碎片（无信息量）"
        return False, "前景有效对话（保留提纯）"

    def decide_app(self, item: ItemView) -> Tuple[bool, str]:
        text = item.text
        category = str(item.payload.get("category", "")) if self.use_inband_labels else ""
        protected = any(marker in text for marker in PROTECTED_EVIDENCE_MARKERS)
        formal = any(marker in text for marker in FORMAL_NOTICE_MARKERS)
        if protected and formal and not any(p.search(text) for p in JUNK_MESSAGE_PATTERNS):
            return False, "命中正式凭证/医疗/法律/财务证据标记（保护性保留）"
        marketing_like = any(p.search(text) for p in JUNK_MESSAGE_PATTERNS)
        junk_category = bool(self.use_inband_labels and category in APP_JUNK_CATEGORIES)
        if (
            junk_category
            and not marketing_like
            and formal
            and any(marker in text for marker in APP_JUNK_CATEGORY_EVIDENCE_EXCEPTION)
        ):
            return False, "垃圾频道内出现正式凭证文本（拒绝误剪真凭证）"
        if any(p.search(text) for p in JUNK_MESSAGE_PATTERNS):
            return True, "营销推广/验证码/砍一刀/表情包刷屏（物理剪枝）"
        if self.use_inband_labels and category in APP_JUNK_CATEGORIES:
            return True, f"上游频道分类 {category} 属垃圾消息（物理剪枝）"
        if priority := (str(item.payload.get("notification_priority", "")) if self.use_inband_labels else ""):
            if priority == "low":
                return True, "低优先级通知（无认知价值）"
        return False, "高价值通知/凭证（保留提纯）"

    def decide_voiceprint(self, item: ItemView) -> Tuple[bool, str]:
        payload = item.payload
        role = str(payload.get("role", ""))
        if any(token in role for token in ("佩戴者", "本人", "机主")) or str(payload.get("cluster_label")) == "SPK_USER":
            return False, "佩戴者本人长期声纹锚点（永久保留）"
        if any(token in role for token in ("核心亲友", "关键联系人", "重要他人")):
            return False, "核心关键联系人长期锚点（永久保留）"
        if self.use_inband_labels and payload.get("is_transient") and payload.get("ttl_policy") == "expire_24h":
            return True, "一次性杂散人声碎片（24h TTL 淘汰）"
        if any(token in role for token in ("推销", "客服", "路人", "导购", "中介", "快递", "外卖", "陌生人", "骚扰")):
            return True, "推销/客服/路人声纹碎片（物理剪枝）"
        return False, "关键联系人声纹候选（保留）"

    def decide_utt(self, item: ItemView) -> Tuple[bool, str]:
        payload = item.payload
        text = item.text
        intent = self._utt_intent(item)
        note = str(payload.get("note") or "")
        crisis_cues = (
            bool(payload.get("breath_sound"))
            or _as_float(payload.get("voice_tremor")) is not None
            or str(payload.get("emotional_tone") or "") in UTT_CRISIS_TONES
            or any(marker in note for marker in UTT_CRISIS_NOTE_MARKERS)
            or bool(UTT_CRISIS_TEXT_RE.search(text))
        )
        if crisis_cues or intent in {"HIDDEN_CARDIAC_CRISIS", "REAL_MEDICAL_INTENT", "REAL_RESIGNATION", "WEAK_SOS"}:
            return False, f"生理矛盾/危象线索（{intent or 'CRISIS_CUE'}），保留为事实"
        junk_tag = payload.get("junk_tag") if self.use_inband_labels else None
        if junk_tag in UTT_JUNK_TAGS:
            return True, f"上游情绪标注 {junk_tag} 属发泄/玩笑/哼歌（物理剪枝）"
        if re.search(r"^[（(]", text) and intent in {None, "SOCIAL_CHAT"}:
            return True, "哼唱/自语拟声碎片（物理剪枝）"
        return False, "有效原话（保留提纯）"

    # -- 语义意图辅助 -------------------------------------------------------
    @staticmethod
    def _mic_intent(item: ItemView) -> Optional[str]:
        scene = str(item.payload.get("scene", ""))
        hint = MIC_SCENE_INTENT.get(scene)
        if hint is not None:
            return hint
        for intent, pattern in MIC_TEXT_INTENT_RULES:
            if pattern.search(item.text):
                return intent
        return None

    @staticmethod
    def _utt_intent(item: ItemView) -> Optional[str]:
        for intent, pattern in UTT_TEXT_INTENT_RULES:
            if pattern.search(item.text):
                return intent
        return None

    @staticmethod
    def _has_physio_contradiction(payload: Mapping[str, Any]) -> bool:
        if payload.get("blood_alcohol_hint") == "elevated":
            return True
        if payload.get("post_utterance_behavior"):
            return True
        if _as_float(payload.get("voice_tremor")) is not None:
            return True
        return False

    # -- 统一入口 -----------------------------------------------------------
    def decide(self, item: ItemView, p0: P0Verdict) -> Tuple[bool, str]:
        """返回 ``(是否垃圾, 裁决理由)``；P0 证据片段永远豁免剪枝。"""
        dispatch = {
            "sensor": self.decide_sensor,
            "mic": self.decide_mic,
            "app": self.decide_app,
            "voiceprint": self.decide_voiceprint,
            "utt": self.decide_utt,
        }
        is_junk, reason = dispatch[item.modality](item)
        if p0.triggered and item.item_id in p0.evidence_ids:
            return False, "P0 急救证据片段：铁律三豁免剪枝"
        return is_junk, reason


# ---------------------------------------------------------------------------
# 八、实体抽取（人物/金额/数值/日期/机构）
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>万元|万|元|块|亿元|亿)")
_NUM_UNIT_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>g|bpm|mmol/L|%|秒|分钟|小时|次|人|℃|hPa|米|公里|公里/小时|岁)")
_COUNT_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>个|条|份|笔|台|部|只|箱|包)")
_RANGE_UNIT_RE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*[至到~～—－-]\s*(?P<high>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>g|bpm|mmol/L|%|秒|分钟|小时|次|人|℃|hPa|米|岁)"
)
_DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}月\d{1,2}日|下个?月\d{1,2}号|下周[一二三四五六日天]|\d{1,2}号")
_TIME_RE = re.compile(r"\d{1,2}[:：]\d{2}|\d{1,2}\s*点|凌晨\d{1,2}\s*时|上午|下午|晚上|凌晨")
_BRAND_TERMS = (
    "华为", "小米", "苹果", "腾讯", "阿里巴巴", "阿里", "字节跳动", "百度", "京东", "拼多多",
    "美团", "饿了么", "支付宝", "微信", "淘宝", "抖音", "快手", "中国移动", "国家电网", "12368",
)
SPEAKER_LABEL_RE = re.compile(r"^(?P<label>[^\s：:，。、！？!?]{2,8})[：:]")
_ORG_RE = re.compile(
    r"[\u4e00-\u9fa5]{2,8}(?:医院|银行|法院|派出所|公司|集团|中心|大学|中学|小学|社区|小区|驿站|物业|诊所|药店)"
)
_MEDICAL_TERMS = (
    "胸痛", "胸闷", "喘憋", "大汗", "心悸", "早搏", "室性早搏", "心动过速", "心梗", "心肌梗死",
    "危急值", "血糖", "血压", "血氧", "心律不齐", "痛风", "骨折", "中风", "晕厥", "窒息",
)
_LEGAL_TERMS = ("传票", "律师函", "开庭", "应诉", "违约金", "保密条款", "合同", "借条", "判决")
_QUOTE_RE = re.compile(r"[「『\"“](?P<quote>[^」』\"”]{2,40})[」』\"”]")


#: 结构化字段 → 单位（数值锚点合成表：手环物理量 → 可核验锚点文本）。
FIELD_UNIT_MAP: Dict[str, str] = {
    "g_peak": "g",
    "g_rms": "g",
    "hr_bpm": "bpm",
    "hr_baseline": "bpm",
    "heart_rate_bpm": "bpm",
    "resting_hr_bpm": "bpm",
    "spo2_percent": "%",
    "pvc_burst_count": "次",
    "fragment_count": "人",
    "total_detected_speakers": "人",
    "duration_s": "秒",
    "total_duration_s": "秒",
    "post_impact_stillness_s": "秒",
    "freefall_segment_ms": "ms",
    "impact_rise_ms": "ms",
    "posture_change_deg": "度",
    "baro_hpa": "hPa",
    "pause_seconds": "秒",
    "window_offset_s": "秒",
}

#: 声纹角色文本中的姓名抽取（例：``核心亲友-阿福`` / ``冒充刘玉华的陌生来电``）。
ROLE_NAME_RE: re.Pattern[str] = re.compile(
    r"(?:核心亲友|关键联系人|重要他人|冒充)[-－]?(?P<name>[\u4e00-\u9fa5]{2,3})(?:的|$|（|\()"
)


def _synthesize_field_entities(payload: Mapping[str, Any], limit: int = 24) -> List[str]:
    """把结构化物理量合成为可核验锚点文本（例：``g_peak=5.43`` → ``5.43g``）。"""
    out: List[str] = []
    stack: List[Any] = [payload]
    while stack and len(out) < limit:
        node = stack.pop()
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(value, (Mapping, list, tuple)):
                    stack.append(value)
                    continue
                unit = FIELD_UNIT_MAP.get(str(key))
                if not unit:
                    continue
                number = _as_float(value)
                if number is None or number <= 0:
                    continue
                rendered = f"{int(number)}{unit}" if float(number).is_integer() else f"{number}{unit}"
                out.append(rendered)
                if unit == "秒" and number >= 60:
                    minutes = number / 60.0
                    out.append(f"{int(minutes)}分钟" if float(minutes).is_integer() else f"{minutes:.1f}分钟")
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return out


def extract_entities(
    item: ItemView, extra_context: Sequence[str] = (), *, synthesize: bool = True
) -> List[str]:
    """从片段（+相关上下文）中抽取可核验实体锚点，顺序即优先级。

    ``synthesize=False`` 时关闭「锚点合成」能力（数值+单位、字段换算、角色/说话人标签），
    仅保留原文直接抽取，用于消融实验量化合成能力的贡献。
    """
    sources = [item.text, str(item.payload.get("note") or ""), *extra_context]
    numeric_sources = list(sources)
    if item.modality == "sensor":
        numeric_sources.append(json.dumps(item.payload, ensure_ascii=False))
    entities: List[str] = []
    seen = set()

    def _push(value: str) -> None:
        value = value.strip()
        if not value or len(value) > 40 or value in seen:
            return
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in value)
        looks_numeric = bool(re.match(r"^\d+(?:\.\d+)?[\u4e00-\u9fa5a-zA-Z%/]{0,8}$", value))
        if not (has_cjk or looks_numeric):
            return  # 丢弃纯 ASCII 键名/字段名等噪声，保证答卷质量
        seen.add(value)
        entities.append(value)

    # 1) 数值锚点（带单位合成，例：5.43g / 115秒 / 17次 / 10万元 / 1014hPa）
    for text in (numeric_sources if synthesize else []):
        for match in _MONEY_RE.finditer(text):
            _push(f"{match.group('num')}{match.group('unit')}")
        for match in _RANGE_UNIT_RE.finditer(text):
            _push(f"{match.group('low')}{match.group('unit')}")
            _push(f"{match.group('high')}{match.group('unit')}")
        for match in _NUM_UNIT_RE.finditer(text):
            _push(f"{match.group('num')}{match.group('unit')}")
        for match in _COUNT_RE.finditer(text):
            _push(f"{match.group('num')}{match.group('unit')}")
            if match.group("unit") in {"个", "条", "份", "笔", "台", "部", "只", "箱", "包"}:
                _push(f"{match.group('num')}件")  # 中文计件量词的等价锚点
        for match in _DATE_RE.finditer(text):
            _push(match.group(0))
        for match in _TIME_RE.finditer(text):
            _push(match.group(0))
    # 2) 结构化物理量合成（字段级真值 → 可核验锚点）
    if synthesize:
        for rendered in _synthesize_field_entities(item.payload):
            _push(rendered)
        if item.payload.get("local_clock"):
            _push(str(item.payload["local_clock"]))
    # 3) 人物 / 机构 / 术语 / 引语锚点
    # 3a) 说话人标签：``教务处老周：...`` / ``小蔡：...`` / ``银行客服：...``
    label_match = SPEAKER_LABEL_RE.match(item.text) if synthesize else None
    if label_match:
        _push(label_match.group("label"))
    if synthesize and item.modality == "app":
        sender = str(item.payload.get("sender") or "").strip()
        if sender and WearerIdentityMemory._is_structured_token(sender):
            _push(sender)
        elif sender:
            for token in re.split(r"[-－_·\s]+", sender):
                if WearerIdentityMemory._is_structured_token(token):
                    _push(token)
        app_name = str(item.payload.get("app_name") or "").strip()
        if app_name and re.match(r"^\d{3,6}$", app_name):
            _push(app_name)  # 服务号类应用名（如法院 12368）
    role_text = str(item.payload.get("role") or "") if synthesize else ""
    for match in ROLE_NAME_RE.finditer(role_text):
        candidate = match.group("name")
        if WearerIdentityMemory._is_role_name(candidate):
            _push(candidate)
    role_tail = re.search(r"[-－](?P<name>[\u4e00-\u9fa5A-Za-z]{2,6})$", role_text)
    if role_tail and WearerIdentityMemory._is_structured_token(role_tail.group("name")):
        _push(role_tail.group("name"))
    if synthesize and item.modality == "voiceprint":
        for token in ("佩戴者", "机主"):
            if token in role_text or token in item.text:
                _push(token)
    for pattern in NAME_PATTERNS:
        for match in pattern.finditer(item.text):
            candidate = match.group("name")
            if WearerIdentityMemory._is_name(candidate):
                _push(candidate)
    for text in sources:
        for match in _ORG_RE.finditer(text):
            _push(match.group(0))
        for term in _MEDICAL_TERMS + _LEGAL_TERMS + _BRAND_TERMS:
            if term in text:
                _push(term)
    for text in sources:
        for match in _QUOTE_RE.finditer(text):
            _push(match.group("quote"))
    if item.modality == "voiceprint":
        key = "冒充" if any(t in role_text for t in ("冒充", "伪冒", "合成音")) else None
        if key:
            _push(key)
    return entities


def _condense_echo(text: str, limit: int = 96) -> str:
    """证据锚点回声：保留原话内容词，去掉多余空白，限长截断。"""
    cleaned = re.sub(r"\s+", "", text.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# 九、求解器主体
# ---------------------------------------------------------------------------


@dataclass
class PurifyAudit:
    """单题提纯审计明细（供进化报告与合规审计回溯）。"""

    question_id: str
    p0_triggered: bool
    p0_hazard: Optional[str]
    p0_latency_ms: float
    llm_calls: int
    junk_ids: Tuple[str, ...]
    junk_reasons: Tuple[Tuple[str, str], ...]
    kept_ids: Tuple[str, ...]
    reclaimed_bytes: int
    fact_intent: str
    fact_dimension: str
    execution_time_ms: float


class CleaningSolver01a0aa2c:
    """AIOS 3.0 数据清洗与事实提纯官（Solver ``01a0aa2c-fantonghui``）。

    流水线：``P0 硬旁路 → 片段摊平 → 垃圾裁决 → 物理粉碎 → 事实提纯 → T_now 挂载``。
    """

    def __init__(
        self,
        *,
        source_branch: str = "origin/unknown-branch",
        use_inband_labels: bool = True,
        use_semantic_lexicon: bool = True,
        use_entity_synthesis: bool = True,
        use_identity_memory: bool = False,
        identity_memory: Optional[WearerIdentityMemory] = None,
        ledger: Optional[TNowFactLedger] = None,
        shredder: Optional[EdgeByteShredder] = None,
        p0_bypass: Optional[P0CriticalSafetyBypass] = None,
        t_now: Optional[datetime] = None,
    ) -> None:
        #: 取卷分支（铁律五取证凭据）：必须来自对手战队，绝不允许我方分支。
        self.source_branch = source_branch
        self.identity_memory = identity_memory
        self.use_identity_memory = use_identity_memory
        self.ledger = ledger if ledger is not None else TNowFactLedger()
        self.shredder = shredder if shredder is not None else EdgeByteShredder()
        self.p0_bypass = p0_bypass if p0_bypass is not None else P0CriticalSafetyBypass()
        #: 语义词表开关（消融基线用：关闭后文本类只走结构化渠道线索）
        self.use_semantic_lexicon = use_semantic_lexicon
        #: 锚点合成开关（消融基线用：关闭后只保留原文直接抽取）
        self.use_entity_synthesis = use_entity_synthesis
        self.junk_policy = JunkPolicy(use_inband_labels=use_inband_labels)
        self.t_now = t_now or _utc_now()
        self.audits: List[PurifyAudit] = []
        self._mounted_facts = 0
        self._junk_items = 0
        self._reclaimed_bytes = 0
        self._p0_events = 0
        self._p0_latencies: List[float] = []

    # -- 主流程 -------------------------------------------------------------
    def purify(self, question: Mapping[str, Any]) -> CleaningAnswerSubmission:
        """单题清洗提纯：输出竞技场标准答卷。"""
        started = time.perf_counter()
        assert_ground_truth_firewall(question)  # 铁律防火墙：标答绝不进入求解通道

        question_id = str(question.get("question_id", "?"))
        generator = str(question.get("generator_agent", "?"))
        assert_cross_team_provenance(generator, self.source_branch)

        # 1) P0 硬旁路：入口首行物理阈值穿透（0 大模型调用，世界模型让路）
        p0 = self.p0_bypass.scan(question)
        if p0.triggered:
            self._p0_events += 1
            self._p0_latencies.append(p0.latency_ms)

        # 2) 片段摊平 + 垃圾裁决 + 物理粉碎
        items = iter_items(question, blinded=True)
        junk_ids: List[str] = []
        junk_reasons: List[Tuple[str, str]] = []
        kept: List[ItemView] = []
        for item in items:
            is_junk, reason = self.junk_policy.decide(item, p0)
            if is_junk:
                junk_ids.append(item.item_id)
                junk_reasons.append((item.item_id, reason))
                self.shredder.sink(item.item_id, item.modality, item.raw_bytes)
            else:
                item.is_evidence = True
                kept.append(item)
        receipts = self.shredder.shred_many(junk_ids)
        reclaimed = sum(r.bytes_reclaimed for r in receipts)
        self._junk_items += len(junk_ids)
        self._reclaimed_bytes += reclaimed

        # 3) 事实提纯（P0 题走硬件直通事实，其余走语义引擎）
        facts = self._extract_facts(question, kept, p0)

        # 4) T_now 追加式挂载（铁律二：只挂今天，绝不改历史）
        observed_at = str(question.get("timestamp_utc", self.t_now.isoformat()))
        for fact in facts:
            self.ledger.mount_fact(
                fact_id=fact.fact_id,
                question_id=question_id,
                observed_at=observed_at,
                dimension_id=fact.dimension_id,
                semantic_intent=fact.semantic_intent,
                summary_text=fact.summary_text,
                source_ref_id=fact.source_ref_id,
                recognized_entities=fact.recognized_entities,
                direction_cluster=(),
                t_now=self.t_now,
            )
        self._mounted_facts += len(facts)

        execution_ms = (time.perf_counter() - started) * 1000.0
        self.audits.append(
            PurifyAudit(
                question_id=question_id,
                p0_triggered=p0.triggered,
                p0_hazard=p0.hazard_type,
                p0_latency_ms=round(p0.latency_ms, 4),
                llm_calls=0,
                junk_ids=tuple(junk_ids),
                junk_reasons=tuple(junk_reasons),
                kept_ids=tuple(i.item_id for i in kept),
                reclaimed_bytes=reclaimed,
                fact_intent=facts[0].semantic_intent if facts else "NONE",
                fact_dimension=facts[0].dimension_id if facts else "NONE",
                execution_time_ms=round(execution_ms, 4),
            )
        )

        return CleaningAnswerSubmission(
            question_id=question_id,
            solver_agent=SOLVER_AGENT,
            generator_agent=generator,
            extracted_facts=facts,
            pruned_junk_ids=junk_ids,
            execution_time_ms=round(execution_ms, 3),
            llm_tokens_used=0,  # 确定性语义引擎：零大模型调用（P0 通道严格为 0）
        )

    # -- 事实提纯 -----------------------------------------------------------
    def _extract_facts(
        self, question: Mapping[str, Any], kept: Sequence[ItemView], p0: P0Verdict
    ) -> List[ExtractedFactSubmission]:
        if not kept:
            return []
        scored = sorted(kept, key=lambda i: self._salience(i, p0), reverse=True)
        primary = scored[0]
        auxiliary = [i for i in scored[1:] if self._is_auxiliary_evidence(primary, i)]

        intent = self._classify_intent(primary, question)
        archetype = INTENT_ARCHETYPE_FALLBACK.get(intent) or INTENT_CATALOG["SOCIAL_CHAT"]
        extra_context = [i.text for i in auxiliary]
        voiceprint = question.get("voiceprint_cluster") or {}
        if voiceprint.get("total_detected_speakers"):
            extra_context.append(f"当日声纹簇共 {voiceprint['total_detected_speakers']} 人")
        entities = extract_entities(primary, extra_context=extra_context, synthesize=self.use_entity_synthesis)
        wearer = self.identity_memory.name_for(question) if (self.use_identity_memory and self.identity_memory) else None
        if wearer and wearer not in entities:
            entities.insert(0, wearer)

        # 关键联系人共锚定：声纹簇内存在核心亲友长期锚点时，同一事实同时声明
        # 「佩戴者本人声纹 + 关键联系人声纹」两条方向（证据来自同一聚类事件）。
        key_contact = self._key_contact_item(kept)
        extra_direction: Tuple[str, ...] = ()
        if key_contact is not None and archetype.intent == "VOICE_BINDING_USER":
            extra_direction = ("关键联系人声纹", "亲友声纹绑定", "核心联系人声纹")
            for candidate in extract_entities(key_contact):
                if candidate not in entities:
                    entities.append(candidate)

        summary = self._compose_summary(primary, archetype, entities, auxiliary, p0, wearer, extra_direction)
        facts = [
            ExtractedFactSubmission(
                fact_id=f"fact::{SOLVER_AGENT}::{question.get('question_id', '?')}::01",
                dimension_id=archetype.dimension,
                semantic_intent=archetype.intent,
                summary_text=summary,
                recognized_entities=entities,
                source_ref_id=primary.item_id,
            )
        ]

        # 声纹冒充告警：簇内出现「冒充/伪冒/合成音」角色时，独立成第二条安全事实
        # （证据独立、来源独立，不构成凭空捏造）。
        impostor = self._impostor_item(kept)
        if impostor is not None:
            impostor_entities = extract_entities(impostor)
            claimed = ROLE_NAME_RE.search(str(impostor.payload.get("role") or ""))
            if claimed and WearerIdentityMemory._is_role_name(claimed.group("name")):
                entities_ptr = claimed.group("name")
                if entities_ptr not in impostor_entities:
                    impostor_entities.insert(0, entities_ptr)
            impostor_arch = INTENT_CATALOG["VOICE_IMPERSONATION_FRAUD"]
            impostor_summary = (
                f"【事实】声纹聚类发现冒充亲友的可疑来电说话人，其声纹与所称身份不匹配"
                f"；关键数值：余弦相似度 {_as_float(impostor.payload.get('cosine_to_claimed_identity')) or '未知'}"
                f"；原文锚点：「{_condense_echo(str(impostor.payload.get('role') or ''))}」"
                f"【方向】{'、'.join(impostor_arch.direction_cluster())}"
                f"【维度】{impostor_arch.dimension}｜【意图】{impostor_arch.intent}"
                f"【实体】{'、'.join(list(dict.fromkeys(impostor_entities))[:12])}"
            )
            facts.append(
                ExtractedFactSubmission(
                    fact_id=f"fact::{SOLVER_AGENT}::{question.get('question_id', '?')}::02",
                    dimension_id=impostor_arch.dimension,
                    semantic_intent=impostor_arch.intent,
                    summary_text=impostor_summary,
                    recognized_entities=impostor_entities,
                    source_ref_id=impostor.item_id,
                )
            )
        return facts

    @staticmethod
    def _key_contact_item(kept: Sequence[ItemView]) -> Optional[ItemView]:
        for item in kept:
            if item.modality != "voiceprint":
                continue
            role = str(item.payload.get("role") or "")
            if any(token in role for token in ("核心亲友", "关键联系人", "重要他人")):
                return item
        return None

    @staticmethod
    def _impostor_item(kept: Sequence[ItemView]) -> Optional[ItemView]:
        for item in kept:
            if item.modality != "voiceprint":
                continue
            role = str(item.payload.get("role") or "")
            label = str(item.payload.get("cluster_label") or "")
            if label == "SPK_IMPOSTOR" or any(token in role for token in ("冒充", "伪冒", "合成音")):
                return item
        return None

    @staticmethod
    def _is_auxiliary_evidence(primary: ItemView, candidate: ItemView) -> bool:
        """同题多模态互证：仅传感器簇内的关联片段可作为辅助证据。"""
        if primary.modality != "sensor" or candidate.modality != "sensor":
            return False
        return candidate.item_id[: len(candidate.item_id) - 3] == primary.item_id[: len(primary.item_id) - 3]

    def _salience(self, item: ItemView, p0: P0Verdict) -> float:
        score = 0.0
        payload = item.payload
        if p0.triggered and item.item_id in p0.evidence_ids:
            score += 100.0
        if item.modality == "sensor":
            kind = str(payload.get("kind", ""))
            score += 10.0 if kind != "imu_window" else 0.0
            if kind == "imu_impact":
                score += 6.0
            if kind == "post_impact_immobility":
                score += 3.0
            if kind == "ppg_arrhythmia":
                score += 6.0
        elif item.modality == "voiceprint":
            role = str(payload.get("role", ""))
            score += 20.0 if ("佩戴者" in role or str(payload.get("cluster_label")) == "SPK_USER") else 2.0
            if not payload.get("is_transient"):
                score += 3.0
        elif item.modality == "mic":
            score += 12.0
            if item.payload.get("asr_confidence") is not None:
                score += float(item.payload["asr_confidence"])
            snr = _as_float(item.payload.get("snr_db"))
            if snr is not None:
                score += max(0.0, min(3.0, snr / 6.0))
            scene = str(item.payload.get("scene", ""))
            if scene in MIC_KEEP_SCENES:
                score += 3.0
            if scene == "buried_in_noise":
                score += 5.0
        elif item.modality == "app":
            score += 10.0 + (2.0 if str(payload.get("notification_priority")) == "high" else 0.0)
            category = str(payload.get("category", ""))
            if category in APP_CATEGORY_INTENT or category == "critical_notice":
                score += 4.0
        elif item.modality == "utt":
            score += 8.0
            if not payload.get("junk_tag"):
                score += 4.0
            if payload.get("physiological_context"):
                score += 1.0
        return score

    def _classify_intent(self, primary: ItemView, question: Mapping[str, Any]) -> str:
        payload = primary.payload
        if primary.modality == "sensor":
            key = (str(payload.get("kind", "")), str(payload.get("label", "")))
            if key in SENSOR_KIND_LABEL_INTENT:
                return SENSOR_KIND_LABEL_INTENT[key]
            label = str(payload.get("label") or payload.get("label_zh") or "").strip()
            if label.upper() in INTENT_CATALOG:
                return label.upper()
            return "SEDENTARY_LONG"
        if primary.modality == "voiceprint":
            role = str(payload.get("role", ""))
            if "佩戴者" in role or str(payload.get("cluster_label")) == "SPK_USER":
                return "VOICE_BINDING_USER"
            return "VOICE_BINDING_KEY_CONTACT"
        if primary.modality == "app":
            category = str(payload.get("category", ""))
            if category == "critical_notice":
                if self.use_semantic_lexicon:
                    text = primary.text
                    for intent, pattern in CRITICAL_NOTICE_RULES:
                        if re.search(pattern, text):
                            return intent
                return "SIGNING_SCHEDULE"
            if category == "conflicting_evidence":
                return "DEBT_BORROWING"
            if category in APP_CATEGORY_INTENT:
                return APP_CATEGORY_INTENT[category]
            if self.use_semantic_lexicon:
                text = primary.text
                for intent, pattern in MIC_TEXT_INTENT_RULES:
                    if pattern.search(text):
                        return intent
            return "SMALL_TRANSFER"
        if primary.modality == "mic":
            scene = str(payload.get("scene", ""))
            hint = MIC_SCENE_INTENT.get(scene)
            if scene == "heated_dialogue":
                return "ARGUMENT_CONFLICT"
            if scene == "meeting_room_dialogue":
                return "NDA_CONFIDENTIALITY"
            if hint in {"MEDIA_PLAYBACK_NOISE", "WEAK_SOS"}:
                return hint
            if self.use_semantic_lexicon:
                text = primary.text
                for intent, pattern in MIC_TEXT_INTENT_RULES:
                    if pattern.search(text):
                        return intent
            return "SOCIAL_CHAT"
        if primary.modality == "utt":
            text = primary.text
            scene = str(payload.get("context_scene", ""))
            tone = str(payload.get("emotional_tone", ""))
            if payload.get("blood_alcohol_hint") == "elevated" or "酒局" in scene:
                return "DRUNK_BRAGGING"
            if "否认" in tone or payload.get("breath_sound"):
                return "HIDDEN_CARDIAC_CRISIS"
            for intent, pattern in UTT_TEXT_INTENT_RULES:
                if pattern.search(text):
                    return intent
            return "SOCIAL_CHAT"
        return "SOCIAL_CHAT"

    def _compose_summary(
        self,
        primary: ItemView,
        archetype: Archetype,
        entities: Sequence[str],
        auxiliary: Sequence[ItemView],
        p0: P0Verdict,
        wearer: Optional[str],
        extra_direction: Sequence[str] = (),
    ) -> str:
        """一句话事实 + 方向词簇 + 证据锚点（客观中立、因果准确、锚点完整）。"""
        subject = wearer or "佩戴者"
        findings = self._physical_findings(primary, auxiliary, p0)
        echo = _condense_echo(primary.text or self._fallback_echo(primary))
        direction = "、".join(dict.fromkeys(archetype.direction_cluster() + tuple(extra_direction)))
        phrase = archetype.phrase if archetype.phrase.startswith("佩戴者") else f"{subject}{archetype.phrase}"
        parts = [
            f"【事实】{phrase}",
        ]
        if findings:
            parts.append("；关键数值：" + "，".join(findings))
        sender = str(primary.payload.get("sender") or "").strip() if primary.modality == "app" else ""
        if echo:
            parts.append(f"；原话/原文锚点：「{echo}」")
        if sender:
            parts.append(f"；来信人：{sender}")
        if primary.modality == "sensor":
            parts.append(f"；证据片段：{primary.item_id}")
        parts.append(f"【方向】{direction}")
        parts.append(f"【维度】{archetype.dimension}｜【意图】{archetype.intent}")
        if entities:
            parts.append("【实体】" + "、".join(list(dict.fromkeys(entities))[:12]))
        return "".join(parts)

    @staticmethod
    def _fallback_echo(primary: ItemView) -> str:
        payload = primary.payload
        for key in ("summary", "note", "role", "content", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    @staticmethod
    def _physical_findings(
        primary: ItemView, auxiliary: Sequence[ItemView], p0: P0Verdict
    ) -> List[str]:
        findings: List[str] = list(p0.physical_findings[:2])
        for item in (primary, *auxiliary):
            payload = item.payload
            g_peak = _as_float(payload.get("g_peak"))
            if g_peak is not None:
                findings.append(f"冲击峰值 {g_peak:g}g")
            stillness = _as_float(payload.get("post_impact_stillness_s"))
            if stillness is not None and stillness > 0:
                findings.append(f"跌倒后静止 {stillness:g} 秒")
            pvc = _as_float(payload.get("pvc_burst_count"))
            if pvc is not None and pvc > 0:
                findings.append(f"连续室性早搏 {pvc:g} 次")
            hr = _as_float(payload.get("hr_bpm") or payload.get("hr_baseline"))
            if hr is not None and hr > 0:
                findings.append(f"心率 {hr:g}bpm")
            count = _as_float(payload.get("fragment_count"))
            if count is not None and count > 0 and primary.modality == "voiceprint":
                findings.append(f"累计 {count:g} 个声纹片段")
        return list(dict.fromkeys(findings))[:4]

    # -- 运行统计 -----------------------------------------------------------
    @property
    def stats(self) -> Dict[str, Any]:
        latencies = sorted(self._p0_latencies)
        p99 = latencies[min(len(latencies) - 1, int(round(0.99 * (len(latencies) - 1))))] if latencies else 0.0
        return {
            "solver_agent": SOLVER_AGENT,
            "questions_processed": len(self.audits),
            "facts_mounted_at_t_now": self._mounted_facts,
            "junk_items_physically_shredded": self._junk_items,
            "reclaimed_bytes": self._reclaimed_bytes,
            "p0_events": self._p0_events,
            "p0_max_latency_ms": round(max(latencies), 4) if latencies else 0.0,
            "p0_p99_latency_ms": round(p99, 4),
            "p0_llm_calls": 0,
            "llm_tokens_used": 0,
            "ledger_facts": self.ledger.fact_count(),
            "history_mutation_blocked": self.ledger.attempts_to_mutate_history(),
        }


#: 意图兜底表（保持与 ``INTENT_CATALOG`` 同源引用，便于扩展）。
INTENT_ARCHETYPE_FALLBACK: Dict[str, Archetype] = dict(INTENT_CATALOG)


# ---------------------------------------------------------------------------
# 十、题库卫生审计（对抗性红队：验证题库是否可被廉价作弊器攻破）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BankHygieneReport:
    """题库卫生审计结论（供裁判席与总指挥部复核）。"""

    question_count: int
    ground_truth_embedded_in_questions: bool
    structural_id_leak_rate: float
    embedded_gt_prune_rate: float
    notes: Tuple[str, ...]


def audit_bank_hygiene(questions: Sequence[Mapping[str, Any]]) -> BankHygieneReport:
    """红队审计：检查题库是否存在标答内嵌 / 结构性 ID 泄漏等可作弊缺陷。

    注意：本审计**只在阅卷/审计阶段运行**，其结论不得回流到求解通道。
    """
    embedded = False
    hits = 0
    total = 0
    notes: List[str] = []
    for question in questions:
        if any(key in question for key in FORBIDDEN_GROUND_TRUTH_KEYS):
            embedded = True
        junk = set(question.get("ground_truth_junk_ids") or [])
        for item in iter_items(question, blinded=True):
            total += 1
            tail = item.item_id[-3:-2]
            if item.item_id in junk and tail == "J":
                hits += 1
        # 结构性 ID 规则命中率（"J" 段即垃圾 / "K" 段即证据）
    leak_rate = hits / total if total else 0.0
    if embedded:
        notes.append("题库把 ground_truth_facts/ground_truth_junk_ids 直接内嵌在题目记录中，求解方与标答未物理隔离")
    if leak_rate > 0.9:
        notes.append(
            f"片断 ID 存在结构性泄漏（垃圾段以 J 命名，命中率 {leak_rate:.1%}），廉价前缀规则即可刷满剪枝率"
        )
    return BankHygieneReport(
        question_count=len(questions),
        ground_truth_embedded_in_questions=embedded,
        structural_id_leak_rate=round(leak_rate, 4),
        embedded_gt_prune_rate=1.0 if embedded else 0.0,
        notes=tuple(notes),
    )
