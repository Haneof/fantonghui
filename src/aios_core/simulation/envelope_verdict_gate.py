"""SIM-001 · 30 天虚拟人仿真的预算封套判决门与纵向退化守卫

本模块**不重跑**仿真。并行线的 ``simulation/headless_life_driver.py`` 已经把
C01→C06→C02→C04→C05 的真实链路接通（复用既有 EdgeMultimodalCleaner /
CJKTopologicalInvertedIndex / SQLiteWorldStore / ManifestDataPlaneBuilderV0），
这部分做得扎实，本模块不动它一行。

本模块补的是驱动器**没有做**的那一层：把仿真产出的数字拿到法定政策面前受审。
之所以要单独一层，是因为取证发现三处缺口，每一处都会让"30 天仿真全绿"这句话
失去意义：

**缺口一：驱动器对政策零引用。** ``headless_life_driver.py`` 里 ``token_budget`` /
``daily_total_cap`` / ``degradation_invariants`` / ``ci_runtime_minutes`` /
``deterministic_seed`` 的命中数**全是 0**，唯一一次 ``monthly_total_cap`` 出现在
docstring 的"可复算"承诺里。承诺写在文档里而代码不读政策，等于封套合规只在
某个测试的某一行成立，换个测试就没了。:class:`TokenEnvelopeGate` 把
``token_budget`` 的**十二个子系统上限 + 日上限 + 月上限**变成机制本体。

**缺口二：两条"卫生证明"是构造性空转。** 驱动器把 ``report.raw_bytes_resident = 0``
写在主循环里（每一步都赋值 0），``report.deadlocks = 0`` 写在结尾；而测试断言
``report.raw_bytes_resident == 0`` / ``report.deadlocks == 0``。这两条断言
**永远为真** —— 若原始字节真的驻留、真的死锁，报告照样写 0。一个只会返回期望值的
"测量"不是测量，是最危险的一类假绿：它披着自证的外衣，却对现实无任何敏感度。
:mod:`ResidencyProbe` 与 :func:`measure_thread_delta` 给出**可以失败**的测量。

**缺口三：25 条法定退化不变量一条都没产出。** ``degradation_invariants.invariants``
有 25 项、四种趋势语义（non_decreasing / non_increasing / bounded / flat）、
两级严重度（warning / blocker）。政策 ``$comment`` 的方法论要点是：五种退化
「在快照式测试下全部表现为'这一轮指标还行'，**只在趋势上可见**」。而 ``SimReport``
恰是快照 —— 它测的是函数值，产品承诺的是导数。:class:`DegradationGuard` 按法定
``sampling=daily`` + ``smoothing=7_day_moving_average`` + ``measurement=
compressed_30_virtual_days`` 把 25 项逐条判出来。

尚未入法 / 推导而来的解释
------------------------
``bounded`` 与 ``flat`` 两种趋势，政策只给了 ``tolerance`` 而**没有给绝对界**
（例如 ``cost.tokens_per_virtual_day`` 的 tolerance=0.15，但 15% 是相对什么的 15%
并未写明）。本模块采用的解释是**相对窗口基线**：

* ``bounded``：任一日的 7 日均值 ≤ 基线 × (1 + tolerance)
* ``flat``：|末日 7 日均值 − 基线| ≤ |基线| × tolerance

基线取窗口首个可算出 7 日均值的那一日。这个解释能自洽地覆盖两种极端：
tolerance=0 且基线=0 的计数型指标（``intrusion.fixed_rhythm_bomb_count`` /
``style.sycophancy_rate`` / ``delivery.false_playback_without_epoch``）退化为
"必须恒为 0"，与政策别处给出的绝对判据一致；tolerance=0.15 的成本型指标退化为
"相对基线涨幅不得超过 15%"。**但它仍是推导，须交治理批准**，故 :data:`TREND_*`
常量与判据函数都带 ``PROPOSED`` 标注，并在测试里把这条解释显式钉住 —— 一旦治理
给出别的读法，测试会先变红，而不是让两种读法在代码里各活一半。

复用的既有法定构件
------------------
``governance/runtime_policy.json`` 的 ``token_budget`` / ``degradation_invariants``
两段（唯一权威）、并行线 ``simulation/headless_life_driver.py`` 的 ``SimReport`` /
``TokenMeter``（本模块接受它们作为输入，不另造报告格式）。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Final, Iterable, Mapping, Sequence

__all__ = [
    "PROPOSED_SIM_SUBSYSTEM_MAPPING",
    "PROPOSED_TREND_SEMANTICS",
    "SMOOTHING_DAYS",
    "VIRTUAL_DAYS_REQUIRED",
    "DegradationGuard",
    "DeterminismGate",
    "InvariantVerdict",
    "ResidencyProbe",
    "RuntimeBudgetGate",
    "SimVerdict",
    "SimVerdictGateError",
    "TokenEnvelopeGate",
    "TokenViolation",
    "build_verdict",
    "measure_thread_delta",
    "load_runtime_policy",
    "load_token_budget_policy",
    "load_degradation_policy",
    "validate_policy_section",
]


_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_POLICY_PATH: Final[Path] = _REPO_ROOT / "governance" / "runtime_policy.json"


class SimVerdictGateError(RuntimeError):
    """判决门自身的错误（政策漂移、数据不全、窗口不足）。

    刻意**不**用 ``AIOSProtocolError``：判决门是仿真/CI 期的治理构件，不是协议边界
    上的运行时失败，把它塞进协议错误族会让线上调用方误以为需要按码分支。
    """


# ---------------------------------------------------------------------------
# 政策引用与校验
# ---------------------------------------------------------------------------


def load_runtime_policy() -> Dict[str, Any]:
    if not _POLICY_PATH.exists():
        raise SimVerdictGateError(f"找不到法定政策文件：{_POLICY_PATH}")
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def validate_policy_section(
    section_name: str,
    section: Any,
    required_fields: Sequence[str],
    *,
    required_true: Sequence[str] = (),
) -> Dict[str, Any]:
    """校验政策段。文件路径与**注入路径**都执行（M2-005R 栽过的真 bug）。"""
    if not isinstance(section, dict):
        raise SimVerdictGateError(f"政策段 {section_name!r} 必须是对象")
    for key in required_fields:
        if key not in section:
            raise SimVerdictGateError(f"政策段 {section_name} 缺少法定字段 {key!r}")
    for key in required_true:
        if section.get(key) is not True:
            raise SimVerdictGateError(
                f"政策段 {section_name}.{key} 法定值为 True，实际为 {section.get(key)!r}"
            )
    return dict(section)


def _validated_section(loader: Callable[..., Dict[str, Any]], section: Any, name: str):
    if section is None:
        return loader()
    return loader({name: section})


def load_token_budget_policy(policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """读取并校验 ``token_budget``，且**零基闭合必须成立**。

    政策 ``$closure_note`` 记载：v1.0.0 曾把合计四舍五入成 2,550,000，被判决门第一次
    运行抓住 4,000 token 漂移；修正方向是把总帽改成推导值而非把推导值凑成总帽。
    所以闭合式是判决门的**第一道**检查，而不是可选断言。
    """
    root = dict(policy) if policy is not None else load_runtime_policy()
    section = validate_policy_section(
        "token_budget",
        root.get("token_budget"),
        required_fields=("monthly_total_cap", "daily_total_cap", "subsystems"),
    )
    total = sum(int(v["monthly_cap"]) for v in section["subsystems"].values())
    if total != int(section["monthly_total_cap"]):
        raise SimVerdictGateError(
            f"token_budget 零基闭合破裂：{len(section['subsystems'])} 个子系统之和 "
            f"{total} != monthly_total_cap {section['monthly_total_cap']}"
            f"（漂移 {total - int(section['monthly_total_cap']):+d} token）"
        )
    return section


def load_degradation_policy(policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """读取并校验 ``degradation_invariants``。"""
    root = dict(policy) if policy is not None else load_runtime_policy()
    section = validate_policy_section(
        "degradation_invariants",
        root.get("degradation_invariants"),
        required_fields=(
            "measurement",
            "sampling",
            "smoothing",
            "ci_runtime_minutes_max_mock_adapter",
            "invariants",
        ),
        required_true=("deterministic_seed_required",),
    )
    if section["measurement"] != "compressed_30_virtual_days":
        raise SimVerdictGateError(
            f"degradation_invariants.measurement 法定值为 'compressed_30_virtual_days'，"
            f"实际为 {section['measurement']!r}"
        )
    if section["sampling"] != "daily":
        raise SimVerdictGateError(f"sampling 法定值为 'daily'，实际为 {section['sampling']!r}")
    if section["smoothing"] != "7_day_moving_average":
        raise SimVerdictGateError(
            f"smoothing 法定值为 '7_day_moving_average'，实际为 {section['smoothing']!r}"
        )
    if not section["invariants"]:
        raise SimVerdictGateError("degradation_invariants.invariants 不得为空")
    for item in section["invariants"]:
        for key in ("metric_id", "trend", "tolerance", "severity"):
            if key not in item:
                raise SimVerdictGateError(f"不变量 {item.get('metric_id', '?')} 缺少 {key!r}")
        if item["trend"] not in PROPOSED_TREND_SEMANTICS:
            raise SimVerdictGateError(
                f"不变量 {item['metric_id']} 的趋势语义 {item['trend']!r} 未登记；"
                f"已登记：{sorted(PROPOSED_TREND_SEMANTICS)}"
            )
        if item["severity"] not in ("warning", "blocker"):
            raise SimVerdictGateError(
                f"不变量 {item['metric_id']} 的 severity {item['severity']!r} 非法"
            )
    return section


#: **提案，尚未入法**：四种趋势语义的可执行判据（见模块 docstring 的解释与理由）。
PROPOSED_TREND_SEMANTICS: Final[frozenset[str]] = frozenset(
    {"non_decreasing", "non_increasing", "bounded", "flat"}
)

#: **提案，尚未入法**：并行线 ``TokenMeter`` 的四个记账桶 → 法定十二子系统的映射。
#:
#: 没有这层映射，封套判决门就用不到既有驱动器上（``manifest_tokens`` /
#: ``caption_tokens`` / ``claim_tokens`` / ``retro_tokens`` 都不是法定子系统名）。
#: 依据逐条写明，便于治理评审；映射错了会把花费记到别的子系统头上，从而让某一项
#: 的上限形同虚设 —— 所以它必须是提案而不能是随手一比。
PROPOSED_SIM_SUBSYSTEM_MAPPING: Final[Dict[str, str]] = {
    # 单看板装配是会话路径的一部分（L0 切片 + 槽位），故记 conversation.fast
    "manifest_tokens": "conversation.fast",
    # 端侧多模态摄入后的字幕/描述抽取，属 extract 子系统
    "caption_tokens": "extract",
    # 会议纪要落 Claim 也是"观测抽取入世界"，同属 extract
    "claim_tokens": "extract",
    # 回溯注记是复盘行为，对应 reflection（30 次/月 × 3000）
    "retro_tokens": "reflection",
}

#: 法定窗口长度：``compressed_30_virtual_days``。
VIRTUAL_DAYS_REQUIRED: Final[int] = 30

#: 法定平滑窗：``7_day_moving_average``。
SMOOTHING_DAYS: Final[int] = 7


# ---------------------------------------------------------------------------
# 预算封套判决门
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenViolation:
    """一次封套违例。``legal_cap`` 必须落字 —— 违例不引用法定上限就无法复核。"""

    day: int
    subsystem: str
    tokens: int
    legal_cap: int
    scope: str  # "subsystem_monthly" | "daily_total" | "monthly_total"

    def to_audit(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "subsystem": self.subsystem,
            "tokens": self.tokens,
            "legal_cap": self.legal_cap,
            "scope": self.scope,
            "overage": self.tokens - self.legal_cap,
        }


class TokenEnvelopeGate:
    """把 ``token_budget`` 的十二个子系统上限 + 日上限 + 月上限变成机制本体。

    **未知子系统一律拒绝**（fail-closed）：若允许随意记账，超支只要换个名字就能
    绕过封套 —— 而"换个名字"恰恰是最省事的实现方式。
    """

    def __init__(self, *, token_budget_policy: Mapping[str, Any] | None = None) -> None:
        self.policy: Dict[str, Any] = _validated_section(
            load_token_budget_policy, token_budget_policy, "token_budget"
        )
        self.monthly_total_cap: Final[int] = int(self.policy["monthly_total_cap"])
        self.daily_total_cap: Final[int] = int(self.policy["daily_total_cap"])
        self.subsystem_caps: Final[Dict[str, int]] = {
            name: int(spec["monthly_cap"]) for name, spec in self.policy["subsystems"].items()
        }
        self._spent_by_subsystem: Dict[str, int] = {name: 0 for name in self.subsystem_caps}
        self._spent_by_day: Dict[int, int] = {}
        self._spent_by_day_subsystem: Dict[tuple[int, str], int] = {}
        self._violations: list[TokenViolation] = []

    def record(self, *, day: int, subsystem: str, tokens: int) -> None:
        if subsystem not in self.subsystem_caps:
            raise SimVerdictGateError(
                f"未知子系统 {subsystem!r}；法定子系统为 {sorted(self.subsystem_caps)}。"
                "记账到不存在的子系统等于给超支开一条改名即可绕过的后门"
            )
        if tokens < 0:
            raise SimVerdictGateError(f"token 记账不得为负：{tokens}")
        if day < 0 or day >= VIRTUAL_DAYS_REQUIRED:
            raise SimVerdictGateError(
                f"虚拟日 {day} 超出法定窗口 [0, {VIRTUAL_DAYS_REQUIRED})"
            )
        self._spent_by_subsystem[subsystem] += tokens
        self._spent_by_day[day] = self._spent_by_day.get(day, 0) + tokens
        key = (day, subsystem)
        self._spent_by_day_subsystem[key] = self._spent_by_day_subsystem.get(key, 0) + tokens

    def violations(self) -> tuple[TokenViolation, ...]:
        """按法定上限逐条核对，返回全部违例（不是遇到第一条就停）。"""
        found: list[TokenViolation] = []
        for name, spent in self._spent_by_subsystem.items():
            cap = self.subsystem_caps[name]
            if spent > cap:
                found.append(
                    TokenViolation(
                        day=-1, subsystem=name, tokens=spent, legal_cap=cap,
                        scope="subsystem_monthly",
                    )
                )
        for day, spent in sorted(self._spent_by_day.items()):
            if spent > self.daily_total_cap:
                found.append(
                    TokenViolation(
                        day=day, subsystem="*", tokens=spent,
                        legal_cap=self.daily_total_cap, scope="daily_total",
                    )
                )
        total = sum(self._spent_by_subsystem.values())
        if total > self.monthly_total_cap:
            found.append(
                TokenViolation(
                    day=-1, subsystem="*", tokens=total,
                    legal_cap=self.monthly_total_cap, scope="monthly_total",
                )
            )
        self._violations = found
        return tuple(found)

    def spent(self, subsystem: str | None = None) -> int:
        if subsystem is None:
            return sum(self._spent_by_subsystem.values())
        return self._spent_by_subsystem[subsystem]

    def headroom(self, subsystem: str | None = None) -> int:
        """剩余封套。负数即已超支 —— 返回负数而不是抛错，让调用方能画出趋势。"""
        if subsystem is None:
            return self.monthly_total_cap - self.spent()
        return self.subsystem_caps[subsystem] - self.spent(subsystem)

    def verdict(self) -> bool:
        return not self.violations()

    def audit(self) -> Dict[str, Any]:
        violations = self.violations()
        return {
            "zero_base_closure_holds": (
                sum(self.subsystem_caps.values()) == self.monthly_total_cap
            ),
            "subsystems": len(self.subsystem_caps),
            "monthly_total_cap": self.monthly_total_cap,
            "daily_total_cap": self.daily_total_cap,
            "spent_total": self.spent(),
            "spent_by_subsystem": dict(self._spent_by_subsystem),
            "headroom_by_subsystem": {
                name: self.headroom(name) for name in sorted(self.subsystem_caps)
            },
            "violations": [v.to_audit() for v in violations],
            "verdict": "PASS" if not violations else "FAIL",
        }


# ---------------------------------------------------------------------------
# 纵向退化守卫
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InvariantVerdict:
    """一条法定不变量的判决。"""

    metric_id: str
    trend: str
    tolerance: float
    severity: str
    baseline: float | None
    final_ma: float | None
    worst: float | None
    passed: bool
    reason: str

    @property
    def blocks(self) -> bool:
        """只有 ``blocker`` 级违例才阻断判决门；``warning`` 级只记录。"""
        return not self.passed and self.severity == "blocker"

    def to_audit(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "trend": self.trend,
            "tolerance": self.tolerance,
            "severity": self.severity,
            "baseline": self.baseline,
            "final_ma": self.final_ma,
            "worst": self.worst,
            "passed": self.passed,
            "blocks": self.blocks,
            "reason": self.reason,
        }


class DegradationGuard:
    """按法定采样与平滑，对 25 条退化不变量逐条判决。

    两条与"少测一点也没关系"正相反的纪律：

    * **窗口不足不判决。** ``measurement = compressed_30_virtual_days``：少于 30 个
      虚拟日的数据根本不构成法定测量，此时返回 PASS 等于用 10 天的趋势冒充 30 天的
      结论。故 :meth:`render` 在数据不足时**抛错**，而不是给出一个宽容的判决。
    * **缺指标即失败，不静默跳过。** 25 条里少一条数据，不是"少一行输出"，而是
      "少一个判决"。静默跳过会让退化恰好发生在没人测的那一项上 —— 而政策
      ``$comment`` 已经点明退化只在趋势上可见，趋势缺一段就等于没有。
    """

    def __init__(self, *, degradation_policy: Mapping[str, Any] | None = None) -> None:
        self.policy: Dict[str, Any] = _validated_section(
            load_degradation_policy, degradation_policy, "degradation_invariants"
        )
        self.invariants: Final[tuple[Dict[str, Any], ...]] = tuple(self.policy["invariants"])
        self.metric_ids: Final[tuple[str, ...]] = tuple(i["metric_id"] for i in self.invariants)
        self._series: Dict[str, Dict[int, float]] = {mid: {} for mid in self.metric_ids}

    def record_day(self, *, metric_id: str, day: int, value: float) -> None:
        if metric_id not in self._series:
            raise SimVerdictGateError(
                f"未知指标 {metric_id!r}；法定 25 项见 degradation_invariants.invariants"
            )
        if day < 0 or day >= VIRTUAL_DAYS_REQUIRED:
            raise SimVerdictGateError(
                f"虚拟日 {day} 超出法定窗口 [0, {VIRTUAL_DAYS_REQUIRED})"
            )
        if day in self._series[metric_id]:
            raise SimVerdictGateError(
                f"{metric_id} 第 {day} 日重复记账；sampling=daily 要求每日恰好一条"
            )
        self._series[metric_id][day] = float(value)

    def moving_average(self, metric_id: str) -> list[float]:
        """法定 ``7_day_moving_average``。前 6 日无法成窗，故不出点。"""
        if metric_id not in self._series:
            raise SimVerdictGateError(f"未知指标 {metric_id!r}")
        days = sorted(self._series[metric_id])
        out: list[float] = []
        for i, day in enumerate(days):
            if i + 1 < SMOOTHING_DAYS:
                continue
            window = [self._series[metric_id][d] for d in days[i + 1 - SMOOTHING_DAYS : i + 1]]
            out.append(sum(window) / len(window))
        return out

    def _judge(self, spec: Mapping[str, Any]) -> InvariantVerdict:
        metric_id = spec["metric_id"]
        trend = spec["trend"]
        tolerance = float(spec["tolerance"])
        severity = spec["severity"]
        ma = self.moving_average(metric_id)
        recorded = len(self._series[metric_id])

        if recorded < VIRTUAL_DAYS_REQUIRED:
            # 缺数据即失败，不静默跳过（见类 docstring）
            return InvariantVerdict(
                metric_id=metric_id, trend=trend, tolerance=tolerance, severity=severity,
                baseline=None, final_ma=None, worst=None, passed=False,
                reason=(
                    f"数据不全：{recorded}/{VIRTUAL_DAYS_REQUIRED} 个虚拟日；"
                    "缺一个指标就是缺一个判决，不是少一行输出"
                ),
            )
        if len(ma) < 2:
            return InvariantVerdict(
                metric_id=metric_id, trend=trend, tolerance=tolerance, severity=severity,
                baseline=None, final_ma=None, worst=None, passed=False,
                reason=f"平滑后不足两点（{len(ma)}），无法判断趋势",
            )

        baseline, final = ma[0], ma[-1]
        worst: float
        passed: bool
        reason: str

        if trend == "non_decreasing":
            worst = min(b - a for a, b in zip(ma, ma[1:]))
            passed = final >= baseline - tolerance
            reason = (
                f"7 日均值须不降（容差 {tolerance}）：基线 {baseline:.6g} → 末日 {final:.6g}"
            )
        elif trend == "non_increasing":
            worst = max(b - a for a, b in zip(ma, ma[1:]))
            passed = final <= baseline + tolerance
            reason = (
                f"7 日均值须不升（容差 {tolerance}）：基线 {baseline:.6g} → 末日 {final:.6g}"
            )
        elif trend == "bounded":
            # 提案解释：任一日的均值 ≤ 基线 × (1 + tolerance)
            ceiling = baseline * (1.0 + tolerance)
            worst = max(ma)
            passed = all(v <= ceiling + 1e-12 for v in ma)
            reason = (
                f"任一日均值须 ≤ 基线×(1+{tolerance}) = {ceiling:.6g}；"
                f"实测峰值 {worst:.6g}（基线 {baseline:.6g}）"
            )
        else:  # flat
            # 提案解释：|末日 − 基线| ≤ |基线| × tolerance
            allowed = abs(baseline) * tolerance
            worst = max(abs(v - baseline) for v in ma)
            passed = worst <= allowed + 1e-12
            reason = (
                f"偏离基线须 ≤ |基线|×{tolerance} = {allowed:.6g}；"
                f"实测最大偏离 {worst:.6g}（基线 {baseline:.6g}）"
            )

        return InvariantVerdict(
            metric_id=metric_id, trend=trend, tolerance=tolerance, severity=severity,
            baseline=baseline, final_ma=final, worst=worst, passed=passed, reason=reason,
        )

    def render(self, *, require_full_window: bool = True) -> tuple[InvariantVerdict, ...]:
        """逐条判决全部 25 项法定不变量。

        ``require_full_window`` 为真时，窗口不足直接**抛错**而不是给宽容判决：
        用 10 天的趋势冒充 30 天的结论，是快照式测试最容易犯的错。
        """
        if require_full_window:
            short = [
                mid for mid in self.metric_ids
                if len(self._series[mid]) < VIRTUAL_DAYS_REQUIRED
            ]
            if short:
                raise SimVerdictGateError(
                    f"法定窗口为 compressed_30_virtual_days，但 {len(short)} 项指标数据不足："
                    f"{short[:5]}{'...' if len(short) > 5 else ''}"
                )
        return tuple(self._judge(spec) for spec in self.invariants)

    def blockers(self) -> tuple[InvariantVerdict, ...]:
        return tuple(v for v in self.render() if v.blocks)

    def audit(self) -> Dict[str, Any]:
        verdicts = self.render(require_full_window=False)
        return {
            "measurement": self.policy["measurement"],
            "sampling": self.policy["sampling"],
            "smoothing": self.policy["smoothing"],
            "invariants_total": len(verdicts),
            "passed": sum(1 for v in verdicts if v.passed),
            "warnings": sum(1 for v in verdicts if not v.passed and v.severity == "warning"),
            "blockers": sum(1 for v in verdicts if v.blocks),
            "verdicts": [v.to_audit() for v in verdicts],
        }


# ---------------------------------------------------------------------------
# CI 运行时预算 / 确定性 / 可失败的测量
# ---------------------------------------------------------------------------


class RuntimeBudgetGate:
    """``ci_runtime_minutes_max_mock_adapter`` 的机制化。

    驱动器只记录 ``wall_seconds`` 而不与法定上限比对；本门类负责比对，并给出
    剩余预算 —— 上限不是用来事后解释"这次刚好没超"的，是用来在超之前就拒绝的。
    """

    def __init__(self, *, degradation_policy: Mapping[str, Any] | None = None) -> None:
        self.policy: Dict[str, Any] = _validated_section(
            load_degradation_policy, degradation_policy, "degradation_invariants"
        )
        self.minutes_max: Final[float] = float(
            self.policy["ci_runtime_minutes_max_mock_adapter"]
        )
        self.seconds_max: Final[float] = self.minutes_max * 60.0

    def check(self, wall_seconds: float) -> bool:
        if wall_seconds < 0:
            raise SimVerdictGateError(f"墙钟不得为负：{wall_seconds}")
        return wall_seconds <= self.seconds_max

    def remaining_seconds(self, wall_seconds: float) -> float:
        return self.seconds_max - wall_seconds

    def enforce(self, wall_seconds: float) -> None:
        if not self.check(wall_seconds):
            raise SimVerdictGateError(
                f"仿真墙钟 {wall_seconds:.1f}s 超出法定上限 "
                f"{self.seconds_max:.0f}s（{self.minutes_max} 分钟，mock adapter）"
            )


class DeterminismGate:
    """``deterministic_seed_required`` 的机制化：**跑两次，比摘要**。

    只声明"有 seed 参数"并不等于可复放 —— 中间若混入墙钟、集合迭代顺序、
    环境相关分支，同一个 seed 也会跑出不同结果。所以判据是行为性的：同一 seed
    两次运行的摘要必须逐字节相同。
    """

    def __init__(self, *, degradation_policy: Mapping[str, Any] | None = None) -> None:
        self.policy: Dict[str, Any] = _validated_section(
            load_degradation_policy, degradation_policy, "degradation_invariants"
        )
        if self.policy["deterministic_seed_required"] is not True:
            raise SimVerdictGateError("deterministic_seed_required 法定值为 True")

    @staticmethod
    def digest(payload: Any) -> str:
        """对可 JSON 序列化的产物取稳定摘要。"""
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def verify(self, run_once: Callable[[], Any], *, runs: int = 2) -> str:
        if runs < 2:
            raise SimVerdictGateError(f"确定性至少需要两次运行才能比对，收到 {runs}")
        digests = [self.digest(run_once()) for _ in range(runs)]
        if len(set(digests)) != 1:
            raise SimVerdictGateError(
                f"同一 seed 的 {runs} 次运行产出不一致（{len(set(digests))} 种摘要）："
                "存在墙钟、集合序或环境依赖等非确定性来源"
            )
        return digests[0]


class ResidencyProbe:
    """**可以失败**的原始字节驻留测量，替代自证常量。

    驱动器把 ``report.raw_bytes_resident = 0`` 写在主循环里，于是"原始大图不驻留"
    这条 C01 铁律变成了一句永真的断言。本探针真的去数：遍历给定容器，统计
    ``bytes`` / ``bytearray`` 且长度 ≥ 阈值的载荷。返回值**可以非零** —— 这正是
    它与自证常量的全部区别。
    """

    def __init__(self, *, min_bytes: int = 1024) -> None:
        if min_bytes <= 0:
            raise SimVerdictGateError(f"min_bytes 必须为正：{min_bytes}")
        self.min_bytes = min_bytes
        self.observations: list[Dict[str, Any]] = []

    def scan(self, container: Any, *, label: str = "", _depth: int = 0) -> int:
        """返回容器内（含嵌套）达到阈值的二进制载荷数量。"""
        if _depth > 12:  # 防病态自引用结构导致的无限递归
            return 0
        found = 0
        if isinstance(container, (bytes, bytearray, memoryview)):
            if len(container) >= self.min_bytes:
                found += 1
                self.observations.append(
                    {"label": label, "bytes": len(container), "depth": _depth}
                )
            return found
        if isinstance(container, Mapping):
            for key, value in container.items():
                found += self.scan(value, label=f"{label}.{key}", _depth=_depth + 1)
            return found
        if isinstance(container, (list, tuple, set, frozenset)):
            for i, value in enumerate(container):
                found += self.scan(value, label=f"{label}[{i}]", _depth=_depth + 1)
            return found
        # dataclass 与 slots 类**没有 __dict__**：只靠 vars() 遍历会静默漏掉它们的
        # 全部字段 —— 那正是"看起来在测、其实测不到"的缺陷，本探针必须自己避免。
        #
        # 注：下面三条分支（dataclass / __dict__ / __slots__）**互为冗余纵深**。变异测试
        # 证实单独拆掉 dataclass 分支不会漏报，因为非 slots 对象走 __dict__、slots 对象
        # 走 __slots__，两者合起来已穷尽对象形态。保留它的理由是：dataclass 分支按
        # **字段**遍历，语义比 vars() 的"全部实例属性"更可预测（ClassVar、property 不
        # 会被误当成载荷），且一旦将来有人调整分支顺序，它是显式的那一道。
        if dataclasses.is_dataclass(container) and not isinstance(container, type):
            for spec in dataclasses.fields(container):
                found += self.scan(
                    getattr(container, spec.name, None),
                    label=f"{label}.{spec.name}", _depth=_depth + 1,
                )
            return found
        if hasattr(container, "__dict__"):
            for key, value in vars(container).items():
                found += self.scan(value, label=f"{label}.{key}", _depth=_depth + 1)
            return found
        for key in getattr(container, "__slots__", ()):
            found += self.scan(
                getattr(container, key, None), label=f"{label}.{key}", _depth=_depth + 1
            )
        return found

    def assert_clean(self, container: Any, *, label: str = "") -> None:
        count = self.scan(container, label=label)
        if count:
            raise SimVerdictGateError(
                f"C01 铁律违例：{label or '产物'} 中驻留 {count} 份 ≥{self.min_bytes}B "
                f"的二进制载荷（raw 字节不得出 C01 调用帧）；观测={self.observations[:5]}"
            )


@dataclass(frozen=True, slots=True)
class ThreadMeasurement:
    """线程增量的**测量值**，而不是被赋值的 0。"""

    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


class measure_thread_delta:
    """上下文管理器：测量一段代码是否新起了线程。

    驱动器把 ``report.deadlocks = 0`` 写在结尾并声称"单线程无锁，deadlock 没有物理
    载体"。这个论证本身成立，但把它写成常量赋值就让断言失去敏感度；本测量给出
    真实的线程数增量 —— 若某天有人加了一条后台线程，这里会立刻变红。
    """

    def __init__(self) -> None:
        self.result: ThreadMeasurement | None = None
        self._before = 0

    def __enter__(self) -> "measure_thread_delta":
        self._before = threading.active_count()
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.result = ThreadMeasurement(self._before, threading.active_count())
        return False


# ---------------------------------------------------------------------------
# 汇总判决
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SimVerdict:
    """一次 30 天仿真的总判决。

    ``PASS`` 的含义是**四道门同时成立**：封套无违例、25 项退化不变量无 blocker
    违例、墙钟在法定上限内、同一 seed 可复放。少任何一道，"30 天仿真全绿"这句话
    都只是快照式的自我安慰。
    """

    envelope_pass: bool
    envelope_violations: tuple[TokenViolation, ...] = ()
    degradation_blockers: tuple[InvariantVerdict, ...] = ()
    degradation_warnings: tuple[InvariantVerdict, ...] = ()
    invariants_total: int = 0
    runtime_seconds: float = 0.0
    runtime_within_budget: bool = True
    determinism_digest: str | None = None
    thread_delta: int = 0
    raw_byte_payloads: int = 0

    @property
    def passed(self) -> bool:
        return (
            self.envelope_pass
            and not self.degradation_blockers
            and self.runtime_within_budget
            and self.thread_delta == 0
            and self.raw_byte_payloads == 0
            and self.determinism_digest is not None
        )

    def to_audit(self) -> Dict[str, Any]:
        return {
            "verdict": "PASS" if self.passed else "FAIL",
            "envelope_pass": self.envelope_pass,
            "envelope_violations": [v.to_audit() for v in self.envelope_violations],
            "degradation_blockers": [v.to_audit() for v in self.degradation_blockers],
            "degradation_warnings": [v.to_audit() for v in self.degradation_warnings],
            "invariants_total": self.invariants_total,
            "runtime_seconds": round(self.runtime_seconds, 3),
            "runtime_within_budget": self.runtime_within_budget,
            "determinism_digest": self.determinism_digest,
            "thread_delta": self.thread_delta,
            "raw_byte_payloads": self.raw_byte_payloads,
        }


def build_verdict(
    *,
    envelope: TokenEnvelopeGate,
    guard: DegradationGuard,
    runtime: RuntimeBudgetGate,
    wall_seconds: float,
    determinism_digest: str | None,
    thread_delta: int,
    raw_byte_payloads: int,
) -> SimVerdict:
    """把四道门的结论汇成一份可审计判决。"""
    verdicts = guard.render()
    return SimVerdict(
        envelope_pass=envelope.verdict(),
        envelope_violations=envelope.violations(),
        degradation_blockers=tuple(v for v in verdicts if v.blocks),
        degradation_warnings=tuple(
            v for v in verdicts if not v.passed and v.severity == "warning"
        ),
        invariants_total=len(verdicts),
        runtime_seconds=wall_seconds,
        runtime_within_budget=runtime.check(wall_seconds),
        determinism_digest=determinism_digest,
        thread_delta=thread_delta,
        raw_byte_payloads=raw_byte_payloads,
    )
