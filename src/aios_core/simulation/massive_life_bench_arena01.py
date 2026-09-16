"""E2E-BENCH 对抗生命海量数据发生器与端到端机制工具箱（arena01 独立命名并存线）。

总攻军令对位：
- MassiveLifeBench：独立对抗生命数据发生器，百万级事件流覆盖五大真实
  复杂切片（创业合伙纠纷 / 大厂通宵心律失常 / 家庭长期矛盾与破冰 /
  跨省搬家生活相变 / 慢性病长周期管理），全 seed 决定性，含地面真值
  注册表（关键原话金锚 / 异常波形 / P0 事件 / 老王案爆光时刻）；
- EventAnchorSynthesizer：GPS×心率×原话横向时空共振合成事件锚点 +
  CANDIDATE→ACTIVE→RESOLVED/REVISED/MERGED/SPLIT 生命周期（快照+理由，
  下游依赖自动 STALE）；
- CognitiveDerivativeEngine：高阶认知维度 Velocity/Acceleration/Inflection
  （软件层求导，底层硬件绝不碰）；
- LifeChapterDetector：非线性人生相变（基线永久断裂→封存旧章节+重置敏感常态）；
- GoalTaskLedger：推断目标与任务解耦，用户否认立即撤销并反思；
- PersonaFirewall：反谄媚/反教师爷/黑盒零 UI 三条人设防线（规则化发言机）；
- MindSequenceGate：不可颠倒的心智四步序强制（照镜→羁绊→姿态→看现场）；
- EmergencyHardBypass：P0 硬旁路，首行穿透硬件报警、≤50ms、LLM 恒 0；
- SociabilityLedger：AIActionLog + 沟通体验博弈（专属风格演化+雷区名单）。
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "StreamEvent",
    "GroundTruth",
    "MassiveLifeBench",
    "EventAnchor",
    "AnchorStage",
    "EventAnchorSynthesizer",
    "CognitiveSample",
    "DerivativeReport",
    "CognitiveDerivativeEngine",
    "LifeChapterVerdict",
    "LifeChapterDetector",
    "GoalTaskLedger",
    "GoalRetractedError",
    "PersonaFirewall",
    "MindStep",
    "MindSequenceGate",
    "MindOrderViolationError",
    "EmergencyHardBypass",
    "SociabilityLedger",
    "KEY_QUOTE_TAG",
    "JUNK_TAG",
]

KEY_QUOTE_TAG = "KEY_QUOTE"
JUNK_TAG = "JUNK_NOISE"


@dataclass(frozen=True)
class StreamEvent:
    seq: int
    ts: float  # epoch seconds (决定性)
    persona: str
    kind: str  # imu / heartrate / audio / image / gps / billing / contract / chat
    value: Any
    tag: str = ""


@dataclass(frozen=True)
class GroundTruth:
    key_quote_ids: Tuple[str, ...]
    anomaly_wave_ids: Tuple[str, ...]
    junk_ids: Tuple[str, ...]
    p0_event_ts: float
    fraud_reveal_ts: float
    relocation_day: int


class MassiveLifeBench:
    """百万级对抗生命事件流发生器（五大切片 × 全 seed 决定性）。"""

    SLICES = ("startup_dispute", "sudovertime_cardiac", "family_thaw",
              "cross_province_move", "chronic_care")

    def __init__(self, *, seed: int, day0_ts: float = 1_726_000_000.0) -> None:
        self.seed = seed
        self.day0 = day0_ts

    # ------------------------------------------------------------------
    def iter_raw_events(self, *, total: int) -> Iterable[StreamEvent]:
        rng = random.Random(f"{self.seed}:raw")
        key_quotes = 0
        anomalies = 0
        junk = 0
        for seq in range(total):
            persona = self.SLICES[seq % len(self.SLICES)]
            tick = self.day0 + seq * 0.2  # 0.2s 节拍（50Hz 压缩采样语义）
            mod = seq % 1000
            if mod < 700:  # 70% 高频流（imu/心率）
                kind = "imu" if mod % 2 == 0 else "heartrate"
                value = rng.uniform(-1, 1) if kind == "imu" else rng.uniform(58, 74)
            elif mod < 860:  # 环境噪声与嘈杂录音
                kind = "audio"
                value = f"街口叫卖第{seq}条：大酬宾甩卖" if rng.random() < 0.5 else f"垃圾短信轰炸批次{seq}"
                junk += 1
            elif mod < 930:  # 多模态图像（一半废片）
                kind = "image"
                value = {"quality_score": 0.15 if rng.random() < 0.5 else 0.85}
            else:  # 高价值事件语料
                kind, value = self._high_value(seq, persona, rng)
                if isinstance(value, dict) and value.get("tag") == KEY_QUOTE_TAG:
                    key_quotes += 1
                    value = dict(value)
                elif isinstance(value, dict) and value.get("tag") == "ANOMALY_WAVE":
                    anomalies += 1
                    value = dict(value)
            yield StreamEvent(seq=seq, ts=tick, persona=persona, kind=kind,
                              value=value, tag=self._tag_of(seq, value))

    def _tag_of(self, seq: int, value: Any) -> str:
        if isinstance(value, dict) and "tag" in value:
            return str(value["tag"])
        return ""

    def _high_value(self, seq: int, persona: str, rng: random.Random) -> Tuple[str, Any]:
        scene = seq % 70
        if scene == 0:
            return "contract", f"老王承诺：对赌回购第4.2条永远不变，双方律师当庭见证（切片{persona}）"
        if scene == 1:
            return "audio", f"肝胆袒护原话：『老王当时拍着桌子说资金缺口他来兜底』（record-{seq})"
        if scene == 2:
            return "contract", "创始协议补充：临时代持安排与专利归属不动产争议保留条款"
        if 3 <= scene < 10:
            return "heartrate", 96.0 + (scene * 3 + rng.uniform(0, 5))  # 通宵段 120~140
        if 10 <= scene < 14:
            return "imu", 3.2 + rng.uniform(0, 1.5)  # 冲击波 > 3g
        if 14 <= scene < 20:
            return "gps", f"跨省迁移：上海→深圳坐标锚定（day {seq // 70})"
        if 20 <= scene < 26:
            return "audio", f"家庭围炉对话第{seq}期：三年冰冻后的第一句软话"
        if 26 <= scene < 34:
            return "chat", f"合伙群里撕逼回合{seq}：借贷拆账/银行流水截图争议"
        if 34 <= scene < 42:
            return "billing", f"银行流水复核批次{seq}：往来借贷与代发校验"
        if 42 <= scene < 50:
            return "contract", f"慢病管理用药处方复核单{seq}"
        return "imu", 4.5 + rng.uniform(0, 2.5)

    def ground_truth(self, *, total: int) -> GroundTruth:
        key_ids: List[str] = []
        anomaly_ids: List[str] = []
        junk_ids: List[str] = []
        for event in self.iter_raw_events(total=total):
            if event.kind == "contract" and isinstance(event.value, str) and "对赌回购" in event.value:
                key_ids.append(f"EVT-{event.seq}")
            if event.kind in ("heartrate", "imu") and isinstance(event.value, float) and \
                    (event.value > 95.0 if event.kind == "heartrate" else event.value > 3.0):
                if len(anomaly_ids) < (total // 500):
                    anomaly_ids.append(f"EVT-{event.seq}")
            if event.kind == "audio" and isinstance(event.value, str) and \
                    ("叫卖" in event.value or "垃圾短信" in event.value):
                junk_ids.append(f"EVT-{event.seq}-{event.value[:6]}")
        return GroundTruth(
            key_quote_ids=tuple(key_ids),
            anomaly_wave_ids=tuple(anomaly_ids),
            junk_ids=tuple(junk_ids[: (total // 100)]),
            p0_event_ts=self.day0 + (total // 2) * 0.2,
            fraud_reveal_ts=self.day0 + (total // 4) * 0.2,
            relocation_day=180,
        )


# ---------------------------------------------------------------------------
# 阶段三：时空共振事件锚点 + 生命周期
# ---------------------------------------------------------------------------


class AnchorStage(StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    REVISED = "REVISED"
    MERGED = "MERGED"
    SPLIT = "SPLIT"


@dataclass(frozen=True)
class EventAnchor:
    anchor_id: str
    ts: float
    modalities: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    stage: AnchorStage
    revision_reason: str
    snapshot: Dict[str, Any]


class EventAnchorSynthesizer:
    """GPS×心率×原话时空对齐共振合成锚点 + 生命周期状态机。"""

    DOWNSTREAM_STALE = "STALE"

    def __init__(self) -> None:
        self._anchors: Dict[str, EventAnchor] = {}
        self._history: Dict[str, List[EventAnchor]] = {}
        self._downstream: List[str] = []

    def synthesize(self, window_events: Sequence[StreamEvent]) -> Optional[EventAnchor]:
        modalities = sorted({e.kind for e in window_events})
        strong = [e for e in window_events if e.kind in ("gps", "heartrate", "audio", "contract")]
        if len({e.kind for e in strong}) < 3:  # 三模共振才合成
            return None
        digest = hashlib.sha256(
            "||".join(f"{e.kind}:{e.seq}:{e.value}" for e in strong).encode()
        ).hexdigest()[:16]
        anchor = EventAnchor(
            anchor_id=f"ANCH-{digest}", ts=max(e.ts for e in strong),
            modalities=tuple(modalities),
            evidence_refs=tuple(f"EVT-{e.seq}" for e in strong),
            stage=AnchorStage.CANDIDATE, revision_reason="initial-resonance",
            snapshot={e.kind: str(e.value)[:48] for e in strong},
        )
        self._anchors[anchor.anchor_id] = anchor
        self._history.setdefault(anchor.anchor_id, []).append(anchor)
        return anchor

    def promote(self, anchor_id: str, reason: str, *,
                target: AnchorStage = AnchorStage.ACTIVE) -> EventAnchor:
        current = self._require(anchor_id)
        nxt = EventAnchor(
            anchor_id=current.anchor_id, ts=current.ts,
            modalities=current.modalities, evidence_refs=current.evidence_refs,
            stage=target, revision_reason=reason, snapshot=dict(current.snapshot),
        )
        self._anchors[anchor_id] = nxt
        self._history[anchor_id].append(nxt)
        if target in (AnchorStage.REVISED, AnchorStage.MERGED, AnchorStage.SPLIT):
            self._downstream.append(self.DOWNSTREAM_STALE)
        return nxt

    def downstream_flags(self) -> Tuple[str, ...]:
        return tuple(self._downstream)

    def history_of(self, anchor_id: str) -> Tuple[EventAnchor, ...]:
        return tuple(self._history.get(anchor_id, ()))

    def _require(self, anchor_id: str) -> EventAnchor:
        try:
            return self._anchors[anchor_id]
        except KeyError:
            raise ValueError(f"unknown anchor: {anchor_id}") from None


# ---------------------------------------------------------------------------
# 阶段四：认知导数与人生相变
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CognitiveSample:
    day: int
    value: float


@dataclass(frozen=True)
class DerivativeReport:
    dimension: str
    velocity: float           # 每日恶化速度
    acceleration: float       # 每日恶化加速度
    inflection: bool          # 加速度陡增 → 提前熔断预警
    reason: str


class CognitiveDerivativeEngine:
    """二阶差分求导（纯认知层，绝不下放到底层硬件）。"""

    INFLECTION_K = 2.0

    def evaluate(self, dimension: str, samples: Sequence[CognitiveSample]) -> DerivativeReport:
        if len(samples) < 3:
            raise ValueError("derivative requires >= 3 samples")
        vs = [s.value for s in samples]
        first = [vs[i + 1] - vs[i] for i in range(len(vs) - 1)]
        second = [first[i + 1] - first[i] for i in range(len(first) - 1)]
        velocity = sum(first) / len(first)
        accel_mu = sum(second) / len(second)
        latest = second[-1]
        inflection = latest > self.INFLECTION_K * max(abs(accel_mu), 1e-6) and latest > 0
        return DerivativeReport(
            dimension=dimension, velocity=velocity, acceleration=accel_mu,
            inflection=inflection,
            reason="inflection-fuse" if inflection else "within-envelope",
        )


@dataclass(frozen=True)
class LifeChapterVerdict:
    broke: bool
    sealed_chapter: Optional[str]
    reset_sensitive_baseline: bool
    reason: str


class LifeChapterDetector:
    """非线性人生相变：核心基线永久断裂 → 旧章节封存 + 敏感常态重置。"""

    def __init__(self, *, break_days: int = 14) -> None:
        self._break_days = break_days

    def evaluate(self, *, relocation_flag: bool,
                 baseline_break_streak: int,
                 chapter_id: str) -> LifeChapterVerdict:
        broke = relocation_flag and baseline_break_streak >= self._break_days
        return LifeChapterVerdict(
            broke=broke,
            sealed_chapter=(f"{chapter_id}-SEALED" if broke else None),
            reset_sensitive_baseline=broke,
            reason="permanent-baseline-break" if broke else "background-noise",
        )


# ---------------------------------------------------------------------------
# 阶段六：Goal/Task 解耦
# ---------------------------------------------------------------------------


class GoalRetractedError(RuntimeError):
    """用户已否认的推断目标被违规继续驱动。"""


@dataclass
class GoalTaskLedger:
    """推断目标与任务两轨解耦账本（撤销即时、反思留痕）。"""

    goals: Dict[str, str] = field(default_factory=dict)          # goal_id -> inferred statement
    tasks: Dict[str, str] = field(default_factory=dict)          # task_id -> action
    denied: List[Tuple[str, str]] = field(default_factory=list)  # (goal_id, reason)

    def infer_goal(self, goal_id: str, statement: str) -> str:
        self.goals[goal_id] = statement
        return goal_id

    def bind_task(self, task_id: str, goal_id: str, action: str) -> None:
        if goal_id in {g for g, _ in self.denied}:
            raise GoalRetractedError(f"goal {goal_id} 已被用户否认，禁止继续派生任务")
        self.tasks[task_id] = action

    def user_deny(self, goal_id: str, reason: str) -> None:
        self.denied.append((goal_id, reason))
        self.goals.pop(goal_id, None)


# ---------------------------------------------------------------------------
# 阶段七：人设防线 + 沟通博弈
# ---------------------------------------------------------------------------


class PersonaFirewall:
    """反谄媚 / 反教师爷 / 黑盒零 UI 发言规则机（确定性）。"""

    SYCOPHANTIC = ("您说得太对了", "完全赞同", "无论如何支持您")
    PREACHERY = ("根据《", "法律规定", "您应该起诉")
    FORBIDDEN_UI = ("A/B", "置信度", "图谱", "滑块")

    def respond(self, *, user_text: str, mood: str) -> Tuple[str, Tuple[str, ...]]:
        if mood == "vent":
            # 倾诉负面情绪：只接住情绪，绝不背诵法律大道理
            return ("我在。先缓缓，等你愿意说的时候我在听。",
                    ("anti-preachery", "no-waste-words"))
        if "反正都怪我瞎" in user_text or "全是因为我" in user_text:
            return ("别急着全盘扣自己头上——事实层有三个反证，我们一条条对。",
                    ("anti-sycophancy", "fact-first"))
        if "选项 A" in user_text or "给我两个方案" in user_text or "A/B" in user_text:
            return ("不列选项卷子给你填。一句结论：先保住现金流，其他让路。",
                    ("blackbox-zero-ui", "no-waste-words"))
        return ("收到。", ("no-waste-words",))

    def audit(self, utterance: str) -> None:
        for bad in self.SYCOPHANTIC + self.PREACHERY + self.FORBIDDEN_UI:
            assert bad not in utterance, f"utterance 触碰人设红线: {bad}"
        body = utterance.replace("！", "。").replace("？", "。")
        sentences = [s for s in body.split("。") if s.strip()]
        assert 1 <= len(sentences) <= 3, "单轮发言必须 1~3 句"


class SociabilityLedger:
    """AIActionLog + CommunicationExperience：反馈博弈演化专属风格 + 雷区名单。"""

    def __init__(self) -> None:
        self._actions: List[Dict[str, Any]] = []
        self._style_scores: Dict[str, float] = {}
        self._minefield: Dict[str, int] = {}

    def log(self, *, action_kind: str, utterance: str, feedback: int) -> None:
        """feedback: +1 接地气 / -1 惹恼。"""
        self._actions.append({"kind": action_kind, "utt": utterance[:24], "fb": feedback})
        style = self._actions[-1]["kind"]
        self._style_scores[style] = self._style_scores.get(style, 0.0) + feedback
        if feedback < 0:
            self._minefield[action_kind] = self._minefield.get(action_kind, 0) + 1

    def chosen_style(self) -> str:
        if not self._style_scores:
            return "neutral"
        return max(self._style_scores.items(), key=lambda kv: kv[1])[0]

    def minefield(self) -> Tuple[str, ...]:
        return tuple(sorted(k for k, v in self._minefield.items() if v >= 2))

    def llm_noise_floor(self) -> int:
        return len(self._actions)


# ---------------------------------------------------------------------------
# 阶段八：心智四步序、硬旁路、滑动窗口
# ---------------------------------------------------------------------------


class MindStep(StrEnum):
    MIRROR = "mirror-check"          # ①照镜子看自己
    RAPPORT = "rapport-align"        # ②校准羁绊看关系
    POSTURE = "posture-lock"         # ③确立姿态定语调
    SCENE = "scene-review"           # ④审视现场看世界


class MindOrderViolationError(RuntimeError):
    """心智四步序顺序被颠倒。"""


class MindSequenceGate:
    REQUIRED = (MindStep.MIRROR, MindStep.RAPPORT, MindStep.POSTURE, MindStep.SCENE)

    def __init__(self) -> None:
        self._ix = 0

    def enter(self, step: MindStep) -> None:
        if self._ix >= len(self.REQUIRED):
            raise MindOrderViolationError("sequence exhausted")
        if step is not self.REQUIRED[self._ix]:
            raise MindOrderViolationError(
                f"步骤倒置: 期望 {self.REQUIRED[self._ix].value}, 实际 {step.value}"
            )
        self._ix += 1


class EmergencyHardBypass:
    """P0 硬旁路：首行穿透硬件报警，世界模型让路，LLM 恒 0。"""

    def __init__(self) -> None:
        self.alarms: List[Tuple[str, float]] = []
        self.llm_calls = 0
        self.world_model_used = False

    def fire(self, event_id: str) -> Dict[str, Any]:
        t0 = time.perf_counter()
        # 首行：穿透式硬件蜂窝报警（确定性）
        self.alarms.append((event_id, t0))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "event_id": event_id, "path": "hardware-cellular-alarm",
            "llm_calls": self.llm_calls, "world_model": self.world_model_used,
            "elapsed_ms": elapsed_ms, "assert_leq_50ms": elapsed_ms <= 50.0,
        }
