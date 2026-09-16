# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-002 高阶维度生命周期引擎（工单 #7）。

四件本体：
  CrossDimensionalAnomalyDetector —— 跨域物理异常侦测：同一信号跨 ≥2 个
     物理域且连续 ≥3 天（熬夜 × 心率骤升 × 咖啡因依赖这类合流才算数）；
  DimensionLifecycleStateMachine —— 三重硬门生命周期：
     门一：连续 3 天跨域异常才准入候选；门二：30 天试用 + 逐日预测验证；
     门三：每日反思配额恒 1。实现**适配复用** M3-001R 落定的
     DimensionEvolutionGuard，不自造第二套门（铁律 5 全等行为唯一来源）；
  HighOrderDimensionDistiller —— 把异常信号蒸馏为高阶维度提案，
     名录锁死三只：DIM_BURNOUT_RISK / DIM_CREDIT_RISK / DIM_PARENT_HEALTH；
  DimensionOverlayOperator —— 维度以「只读标签」挂载对象：tag 挂摘只写
     旁车表，世界本体与历史改一个字都算违规（一票否决在 Agent-10 落锤）。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from ..dimensions.evolution_guard_m3r import (
    DAILY_REFLECTION_QUOTA,
    MIN_ANOMALY_DOMAINS,
    MIN_ANOMALY_SECONDS,
    MIN_PREDICTION_ACCURACY,
    DimensionEvolutionGuard,
    DimensionState,
    GateRejectionError,
)

# ---------------------------------------------------------------------------
# 跨域物理异常侦测
# ---------------------------------------------------------------------------

# 物理域关键词表（治理件：收录/扩充都走变更，不许运行时漂移）
_DOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BODY_VITALS", ("心率", "早搏", "血压", "室性", "心悸", "心电图")),
    ("SLEEP_BEHAVIOR", ("熬夜", "通宵", "凌晨", "失眠", "缺觉", "深睡")),
    ("STIMULANT_INTAKE", ("咖啡因", "咖啡", "浓茶", "能量饮料", "美式")),
    ("FAMILY_PARENTS", ("母亲", "妈妈", "父亲", "膝盖", "受凉", "体检")),
    ("CREDIT_RELATION", ("借款", "借钱", "欠款", "拖欠", "追偿", "王建国", "老王")),
    ("CAREER_LEGAL", ("合同", "诉讼", "判决", "对赌", "股权", "法院")),
)

CONSECUTIVE_ANOMALY_DAYS = 3          # 门一：连续 3 天
_DIMENSION_KEYWORDS: dict[str, tuple[tuple[str, ...], str]] = {
    # 高阶维度 ← 必备关键词簇 + 一句话判词（蒸馏器用）
    "DIM_BURNOUT_RISK": (
        ("心率", "熬夜", "咖啡因", "早搏", "通宵", "血压", "过劳"),
        "过劳熔断风险：睡眠、体征、兴奋剂三域合流",
    ),
    "DIM_CREDIT_RISK": (
        ("借款", "拖欠", "追偿", "拖延", "借钱"),
        "信用追偿风险：借贷承诺与兑现长期背离",
    ),
    "DIM_PARENT_HEALTH": (
        ("母亲", "膝盖", "受凉", "体检", "骨质"),
        "父母健康守护：体征、起居、就诊三线合观",
    ),
}

HIGH_ORDER_DIMENSIONS: tuple[str, ...] = tuple(_DIMENSION_KEYWORDS)


@dataclass(slots=True, frozen=True)
class AnomalySignal:
    """一次跨域物理异常的完整呈堂证供。"""
    signal_id: str
    domains: tuple[str, ...]          # ≥2 物理域
    first_seen: str                   # ISO
    last_seen: str                    # ISO
    span_days: int                    # 覆盖自然日数（连续）
    evidence: tuple[dict[str, str], ...]  # ObjectRef 级证据：object_id/revision/domain
    occurrence_count: int

    @property
    def duration_seconds(self) -> float:
        return self.span_days * 86_400.0


class CrossDimensionalAnomalyDetector:
    """从读面 payload 里抓跨域异常：同域词簇命中 → 按自然日并轨 → ≥3 天成信号。"""

    def detect(self, payloads: Iterable[Mapping[str, Any]]) -> list[AnomalySignal]:
        # (object_id → (day → {domains, hits}))
        per_object: dict[str, dict[str, dict[str, Any]]] = {}
        for p in payloads:
            oid = p.get("object_id")
            if not isinstance(oid, str) or not oid:
                continue
            day = self._day_of(p)
            if day is None:
                continue
            text = json.dumps(p, ensure_ascii=False, default=str)
            domains = {
                dom for dom, kws in _DOMAIN_KEYWORDS if any(k in text for k in kws)
            }
            if not domains:
                continue
            per_object.setdefault(oid, {}).setdefault(day, set()).update(domains)

        # 跨对象并轨：同一天命中域集合并集跨 ≥2 域 → 当日记一次跨域异常
        day_domains: dict[str, set[str]] = {}
        day_evidence: dict[str, list[dict[str, str]]] = {}
        for oid, days in per_object.items():
            for day, domains in days.items():
                day_domains.setdefault(day, set()).update(domains)
                day_evidence.setdefault(day, []).append(
                    {"object_id": oid, "revision": "1", "domain": "+".join(sorted(domains))}
                )

        anomalous_days = sorted(d for d, doms in day_domains.items()
                                if len(doms) >= MIN_ANOMALY_DOMAINS)
        if not anomalous_days:
            return []

        signals: list[AnomalySignal] = []
        run: list[str] = [anomalous_days[0]]
        for day in anomalous_days[1:]:
            prev = datetime.fromisoformat(run[-1])
            if (datetime.fromisoformat(day) - prev).days == 1:
                run.append(day)
            else:
                signals.extend(self._emit_if_long_enough(run, day_domains, day_evidence))
                run = [day]
        signals.extend(self._emit_if_long_enough(run, day_domains, day_evidence))
        return signals

    def _emit_if_long_enough(
        self,
        run: list[str],
        day_domains: Mapping[str, set[str]],
        day_evidence: Mapping[str, list[dict[str, str]]],
    ) -> list[AnomalySignal]:
        if len(run) < CONSECUTIVE_ANOMALY_DAYS:
            return []
        domains = sorted({d for day in run for d in day_domains[day]})
        evidence: list[dict[str, str]] = []
        for day in run:
            evidence.extend(day_evidence[day])
        sig = AnomalySignal(
            signal_id=f"sig-{run[0]}-{len(run)}d",
            domains=tuple(domains),
            first_seen=run[0],
            last_seen=run[-1],
            span_days=len(run),
            evidence=tuple(evidence),
            occurrence_count=len(evidence),
        )
        return [sig]

    @staticmethod
    def _day_of(p: Mapping[str, Any]) -> str | None:
        for k in ("occurred_at", "asserted_at", "learned_at", "recorded_at", "occurred"):
            v = p.get(k)
            if isinstance(v, datetime):
                return v.astimezone(timezone.utc).date().isoformat()
            if isinstance(v, str) and v:
                try:
                    parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).date().isoformat()
        return None


# ---------------------------------------------------------------------------
# 生命周期状态机（适配 evolution_guard，门的行为唯一来源在 guard）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DimensionLifecycleStateMachine:
    """三重硬门：候选(≥3天跨域) → 30 天试用(逐日预测验证) → ACTIVE。

    门的行为语义全部委托 DimensionEvolutionGuard —— 与铁律 5 全等；
    本类只负责把「信号 → 提案 → 试用 → 注册」的轨道铺直。
    """

    guard: DimensionEvolutionGuard = field(default_factory=DimensionEvolutionGuard)

    def propose_from_signal(self, dimension_id: str, signal: AnomalySignal) -> str:
        """门一：异常持续 <3 天/跨域不足 → 必拦截（GateRejectionError）。"""
        self.guard.submit_candidate(
            dimension_id,
            anomaly_domains=set(signal.domains),
            anomaly_duration_seconds=signal.duration_seconds,
        )
        return dimension_id

    def submit_trial_day(self, dimension_id: str, *, day_key: str,
                         predictions_made: int, predictions_correct: int) -> None:
        """试用期每日记录：先消耗当日反思配额（门三），再记预测账（门二）。"""
        self.guard.consume_reflection_quota(day_key)
        self.guard.record_probation_report(
            dimension_id,
            predictions_made=predictions_made,
            predictions_correct=predictions_correct,
        )

    def finalize(self, dimension_id: str) -> DimensionState:
        """门二落锤：30 期账齐且准确率 ≥70% → ACTIVE，否则 EXPIRED（终态）。"""
        return self.guard.finalize_probation(dimension_id)

    def state_of(self, dimension_id: str) -> DimensionState:
        return self.guard.state_of(dimension_id)

    def quota_left(self, day_key: str) -> int:
        return self.guard.quota_left(day_key)


# ---------------------------------------------------------------------------
# 高阶维度蒸馏器
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class DimensionProposal:
    dimension_id: str
    signal: AnomalySignal
    rationale: str                  # 蒸馏判词：为什么是这只高阶维度
    evidence: tuple[dict[str, str], ...]


class HighOrderDimensionDistiller:
    """异常信号 → 高阶维度提案。名录锁死，名录外的一律免谈。"""

    def distill(self, signals: Iterable[AnomalySignal]) -> list[DimensionProposal]:
        proposals: list[DimensionProposal] = []
        for sig in signals:
            text_bag = " ".join(e.get("domain", "") + e.get("object_id", "")
                                for e in sig.evidence)
            for dim_id, (_kws, rationale) in _DIMENSION_KEYWORDS.items():
                need_domains = self._required_domains(dim_id)
                if need_domains and not need_domains.issubset(set(sig.domains)):
                    continue
                proposals.append(DimensionProposal(
                    dimension_id=dim_id, signal=sig,
                    rationale=f"{rationale}（{sig.span_days} 天 × "
                              f"{len(sig.domains)} 域：{', '.join(sig.domains)}）",
                    evidence=sig.evidence,
                ))
        return proposals

    @staticmethod
    def _required_domains(dimension_id: str) -> frozenset[str]:
        return {
            "DIM_BURNOUT_RISK": frozenset({"BODY_VITALS", "SLEEP_BEHAVIOR", "STIMULANT_INTAKE"}),
            "DIM_CREDIT_RISK": frozenset({"CAREER_LEGAL", "CREDIT_RELATION"}),
            "DIM_PARENT_HEALTH": frozenset({"FAMILY_PARENTS", "BODY_VITALS"}),
        }[dimension_id]


# ---------------------------------------------------------------------------
# 只读维度挂载算子
# ---------------------------------------------------------------------------

OVERLAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS dimension_overlays (
    dimension_id TEXT NOT NULL,
    object_id    TEXT NOT NULL,
    note         TEXT NOT NULL,
    mounted_at   TEXT NOT NULL,
    PRIMARY KEY (dimension_id, object_id)
) WITHOUT ROWID;
"""


class DimensionOverlayOperator:
    """维度标签只读挂载：tag 写旁车表，世界本体一个字不动。"""

    def __init__(self, store: Any, conn: sqlite3.Connection | None = None) -> None:
        self._store = store
        if conn is None:
            conn = sqlite3.connect(getattr(store, "db_path", ":memory:"))
            conn.execute("PRAGMA busy_timeout = 3000")
        self._conn = conn
        self._conn.executescript(OVERLAY_SCHEMA)

    def mount(self, dimension_id: str, object_id: str, *,
              machine: DimensionLifecycleStateMachine | None = None,
              note: str = "") -> None:
        """挂载：维度必须 ACTIVE；对象必须真实存在；本体 revision 不许动。"""
        if machine is not None and machine.state_of(dimension_id) != DimensionState.ACTIVE:
            raise GateRejectionError(
                f"{dimension_id}: 只有 ACTIVE 维度可挂载（当前 "
                f"{machine.state_of(dimension_id).value}）"
            )
        if not self._object_exists(object_id):
            raise GateRejectionError(f"{object_id}: 挂到虚空不许（对象不存在）")
        self._conn.execute(
            "INSERT OR REPLACE INTO dimension_overlays VALUES (?,?,?,?)",
            (dimension_id, object_id, note,
             datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def unmount(self, dimension_id: str, object_id: str) -> None:
        self._conn.execute(
            "DELETE FROM dimension_overlays WHERE dimension_id=? AND object_id=?",
            (dimension_id, object_id),
        )
        self._conn.commit()

    def dimensions_of(self, object_id: str) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT dimension_id FROM dimension_overlays WHERE object_id=? ORDER BY dimension_id",
            (object_id,),
        ).fetchall()
        return tuple(r[0] for r in rows)

    def overlays_of(self, object_id: str) -> list[dict[str, str]]:
        rows = self._conn.execute(
            "SELECT dimension_id, object_id, note, mounted_at FROM dimension_overlays"
            " WHERE object_id=? ORDER BY dimension_id",
            (object_id,),
        ).fetchall()
        return [
            {"dimension_id": d, "object_id": o, "note": n, "mounted_at": t}
            for d, o, n, t in rows
        ]

    def _object_exists(self, object_id: str) -> bool:
        getter = getattr(self._store, "get_payload", None)
        if getter is None:
            return True
        try:
            return getter(object_id) is not None
        except Exception:
            return False


__all__ = [
    "AnomalySignal",
    "CONSECUTIVE_ANOMALY_DAYS",
    "CrossDimensionalAnomalyDetector",
    "DAILY_REFLECTION_QUOTA",
    "DimensionLifecycleStateMachine",
    "DimensionOverlayOperator",
    "DimensionProposal",
    "DimensionState",
    "GateRejectionError",
    "HIGH_ORDER_DIMENSIONS",
    "HighOrderDimensionDistiller",
    "MIN_ANOMALY_DOMAINS",
    "MIN_ANOMALY_SECONDS",
    "MIN_PREDICTION_ACCURACY",
]
