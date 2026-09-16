"""SIM-001 · 预算封套判决门与纵向退化守卫 —— 门禁测试

四道门，每道都必须是**可以失败**的：

1. 预算封套 —— ``token_budget`` 的十二个子系统上限 + 日上限 + 月上限，含政策自己的
   零基闭合式（``$closure_note`` 记载 v1.0.0 曾被判决门抓住 4,000 token 漂移）。
2. 纵向退化守卫 —— 25 项法定不变量、四种趋势语义、7 日均值平滑、30 虚拟日窗口；
   窗口不足**不判决**，缺指标**即失败**（不静默跳过）。
3. CI 运行时预算 —— ``ci_runtime_minutes_max_mock_adapter = 15``。
4. 确定性 —— ``deterministic_seed_required``：同一 seed 跑两次比摘要。

另有一组"敏感度证明"测试：并行线驱动器把 ``raw_bytes_resident`` / ``deadlocks``
硬编码为 0，其测试断言 ``== 0`` 因此**永远为真**。本文件用 AST 取证这一点，并证明
本模块的对应测量（驻留探针、线程增量、确定性门）在真的出事时**会变红** —— 一个只会
返回期望值的测量不是测量。
"""

from __future__ import annotations

import ast
import random
import threading
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios_core.simulation import envelope_verdict_gate as evg
from aios_core.simulation import headless_life_driver as driver
from aios_core.simulation.envelope_verdict_gate import (
    PROPOSED_SIM_SUBSYSTEM_MAPPING,
    UNATTRIBUTABLE_DRIVER_POOLS,
    PROPOSED_TREND_SEMANTICS,
    SMOOTHING_DAYS,
    VIRTUAL_DAYS_REQUIRED,
    DegradationGuard,
    DeterminismGate,
    InvariantVerdict,
    ResidencyProbe,
    RuntimeBudgetGate,
    SimVerdict,
    SimVerdictGateError,
    TokenEnvelopeGate,
    TokenViolation,
    build_verdict,
    load_degradation_policy,
    load_runtime_policy,
    load_token_budget_policy,
    measure_thread_delta,
    validate_policy_section,
)
from aios_core.simulation.headless_life_driver import RunReport

MODULE_SOURCE = Path(evg.__file__).read_text(encoding="utf-8")
DRIVER_SOURCE = Path(driver.__file__).read_text(encoding="utf-8")
#: 驱动器源码去掉模块 docstring 之后的部分（用于取证"承诺只写在文档里"）。
DRIVER_BODY = DRIVER_SOURCE.split('"""', 2)[2]

ROOT = load_runtime_policy()
TB = ROOT["token_budget"]
DG = ROOT["degradation_invariants"]
SUBSYSTEMS = TB["subsystems"]
MONTHLY_CAP = TB["monthly_total_cap"]
DAILY_CAP = TB["daily_total_cap"]
INVARIANTS = {i["metric_id"]: i for i in DG["invariants"]}


def healthy_guard() -> DegradationGuard:
    """一个"健康的虚拟人"：25 项指标 30 天全部平稳为 0。"""
    guard = DegradationGuard()
    for metric_id in guard.metric_ids:
        for day in range(VIRTUAL_DAYS_REQUIRED):
            guard.record_day(metric_id=metric_id, day=day, value=0.0)
    return guard


def constant_guard(metric_id: str, value: float) -> DegradationGuard:
    guard = healthy_guard()
    for day in range(VIRTUAL_DAYS_REQUIRED):
        guard._series[metric_id][day] = value
    return guard


def ramp_guard(metric_id: str, start: float, stop: float) -> DegradationGuard:
    """线性上升的指标（用来触发趋势违例）。"""
    guard = healthy_guard()
    for day in range(VIRTUAL_DAYS_REQUIRED):
        guard._series[metric_id][day] = start + (stop - start) * day / 29.0
    return guard


# ---------------------------------------------------------------------------
# A · 政策绑定
# ---------------------------------------------------------------------------


class TestPolicyBinding:
    def test_policy_file_is_the_single_authority(self):
        assert evg._POLICY_PATH.exists()
        assert evg._POLICY_PATH.parent.name == "governance"

    def test_zero_base_closure_holds(self):
        """政策 ``$closure_note``：十二个子系统之和必须精确等于 monthly_total_cap。"""
        total = sum(v["monthly_cap"] for v in SUBSYSTEMS.values())
        assert total == MONTHLY_CAP == 2554000
        assert len(SUBSYSTEMS) == 12
        assert TokenEnvelopeGate().audit()["zero_base_closure_holds"] is True

    def test_a_broken_closure_is_refused_with_the_drift_amount(self):
        """v1.0.0 曾把合计凑成 2,550,000 而被判决门抓住 4,000 token 漂移。

        判决门的第一道检查就是这条闭合式 —— 它必须在**读政策时**就炸，
        而不是等到某个子系统超支时才被发现。
        """
        drifted = dict(TB)
        drifted["monthly_total_cap"] = 2550000
        with pytest.raises(SimVerdictGateError) as info:
            load_token_budget_policy({"token_budget": drifted})
        assert "4000" in str(info.value) or "+4000" in str(info.value)
        assert "零基闭合" in str(info.value)

    def test_measurement_window_is_legally_fixed(self):
        assert DG["measurement"] == "compressed_30_virtual_days"
        assert VIRTUAL_DAYS_REQUIRED == 30
        drifted = dict(DG)
        drifted["measurement"] = "compressed_7_virtual_days"
        with pytest.raises(SimVerdictGateError, match="compressed_30_virtual_days"):
            load_degradation_policy({"degradation_invariants": drifted})

    def test_sampling_and_smoothing_are_legally_fixed(self):
        assert DG["sampling"] == "daily"
        assert DG["smoothing"] == "7_day_moving_average"
        assert SMOOTHING_DAYS == 7
        for key, bad in (("sampling", "hourly"), ("smoothing", "3_day_moving_average")):
            drifted = dict(DG)
            drifted[key] = bad
            with pytest.raises(SimVerdictGateError):
                load_degradation_policy({"degradation_invariants": drifted})

    def test_deterministic_seed_is_legally_required(self):
        assert DG["deterministic_seed_required"] is True
        drifted = dict(DG)
        drifted["deterministic_seed_required"] = False
        with pytest.raises(SimVerdictGateError, match="法定值"):
            load_degradation_policy({"degradation_invariants": drifted})
        with pytest.raises(SimVerdictGateError):
            DeterminismGate(degradation_policy=drifted)

    def test_every_invariant_is_complete_and_uses_a_registered_trend(self):
        assert len(DG["invariants"]) == 26
        for spec in DG["invariants"]:
            assert set(spec) >= {"metric_id", "trend", "tolerance", "severity"}
            assert spec["trend"] in PROPOSED_TREND_SEMANTICS
            assert spec["severity"] in ("warning", "blocker")

    def test_all_four_trend_semantics_are_exercised_by_the_law(self):
        """四种趋势语义都在法定清单里出现，所以四种判据都必须实现。"""
        used = {spec["trend"] for spec in DG["invariants"]}
        assert used == set(PROPOSED_TREND_SEMANTICS)

    def test_an_unregistered_trend_is_refused(self):
        drifted = dict(DG)
        items = [dict(i) for i in DG["invariants"]]
        items[0]["trend"] = "improving"
        drifted["invariants"] = items
        with pytest.raises(SimVerdictGateError, match="未登记"):
            load_degradation_policy({"degradation_invariants": drifted})

    def test_an_illegal_severity_is_refused(self):
        drifted = dict(DG)
        items = [dict(i) for i in DG["invariants"]]
        items[0]["severity"] = "fatal"
        drifted["invariants"] = items
        with pytest.raises(SimVerdictGateError, match="severity"):
            load_degradation_policy({"degradation_invariants": drifted})

    def test_an_incomplete_invariant_is_refused(self):
        drifted = dict(DG)
        items = [dict(i) for i in DG["invariants"]]
        del items[3]["tolerance"]
        drifted["invariants"] = items
        with pytest.raises(SimVerdictGateError, match="tolerance"):
            load_degradation_policy({"degradation_invariants": drifted})

    def test_empty_invariant_list_is_refused(self):
        drifted = dict(DG)
        drifted["invariants"] = []
        with pytest.raises(SimVerdictGateError, match="不得为空"):
            load_degradation_policy({"degradation_invariants": drifted})

    def test_injected_sections_are_validated_like_the_file(self):
        """注入路径不得享受弱校验（M2-005R 栽过的真 bug）。"""
        with pytest.raises(SimVerdictGateError):
            TokenEnvelopeGate(token_budget_policy={"monthly_total_cap": 1})
        with pytest.raises(SimVerdictGateError):
            DegradationGuard(degradation_policy={"measurement": "x"})

    def test_validate_policy_section_rejects_a_non_object(self):
        with pytest.raises(SimVerdictGateError, match="必须是对象"):
            validate_policy_section("token_budget", "nope", required_fields=())

    def test_no_legal_number_is_copied_into_the_module_code(self):
        """AST 取数字字面量，不用字符串匹配（docstring 引用法定数字是正当的）。"""
        tree = ast.parse(MODULE_SOURCE)
        literals = {
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
        }
        legal = {MONTHLY_CAP, DAILY_CAP} | {v["monthly_cap"] for v in SUBSYSTEMS.values()}
        assert not (literals & legal), f"代码硬编码了法定数字 {sorted(literals & legal)}"
        assert literals, "AST 判据失效：应当数得出数字字面量"

    def test_proposed_semantics_are_marked_as_not_yet_ratified(self):
        assert "提案" in MODULE_SOURCE
        assert "尚未入法" in MODULE_SOURCE
        assert "PROPOSED" in MODULE_SOURCE


# ---------------------------------------------------------------------------
# B · 门 1：预算封套
# ---------------------------------------------------------------------------


class TestTokenEnvelopeGate:
    def test_caps_are_read_from_policy(self):
        gate = TokenEnvelopeGate()
        assert gate.monthly_total_cap == MONTHLY_CAP
        assert gate.daily_total_cap == DAILY_CAP
        assert gate.subsystem_caps == {k: v["monthly_cap"] for k, v in SUBSYSTEMS.items()}

    def test_unknown_subsystem_is_refused(self):
        """fail-closed：记账到不存在的子系统 = 给超支开一条改名即可绕过的后门。"""
        gate = TokenEnvelopeGate()
        with pytest.raises(SimVerdictGateError, match="未知子系统"):
            gate.record(day=0, subsystem="make_up_a_name", tokens=1)

    def test_every_attributable_driver_pool_maps_to_a_legal_subsystem(self):
        """映射提案的每个目标都必须是法定子系统，且**声明为无法归因的池不得偷偷出现在映射里**。

        少一个可归因池，那部分花费就永远进不了封套判决 —— 而这恰好是最容易发生的遗漏，
        因为漏掉的池不会报错，只会安静地不计费。反过来更危险：把一个跨子系统的聚合池
        硬摊派给某个子系统，会让判决门拿到一个"看起来完整"的输入，从而把"测不到"
        伪装成"测到了没超"。所以两个集合必须互斥且都被显式声明。
        """
        gate = TokenEnvelopeGate()
        for target in PROPOSED_SIM_SUBSYSTEM_MAPPING.values():
            assert target in gate.subsystem_caps, f"{target} 不是法定子系统"
        assert not (set(PROPOSED_SIM_SUBSYSTEM_MAPPING) & UNATTRIBUTABLE_DRIVER_POOLS), (
            "同一个池既被归因又被声明为无法归因 —— 两处口径互相矛盾"
        )
        # 报告字段必须真实存在，否则映射指向空气
        for pool in set(PROPOSED_SIM_SUBSYSTEM_MAPPING) | set(UNATTRIBUTABLE_DRIVER_POOLS):
            if pool == "llm_tokens":          # 住在 report.extra 里，不是 dataclass 字段
                assert pool in {f.name for f in fields(RunReport)} | {"llm_tokens"}
                continue
            assert pool in {f.name for f in fields(RunReport)}, f"{pool} 不是 RunReport 字段"

    def test_evidence_the_driver_has_no_per_subsystem_accounting(self):
        """**取证（不代改他人文件）**：驱动器全模块 0 次提及 ``subsystem``。

        这不是吹毛求疵：法定封套是**十二个子系统各自一个上限**，而驱动器只有三个聚合池。
        没有按子系统记账，子系统上限就无法判定 —— 判不了就必须声明判不了，
        不能用总量合规冒充分项合规。
        """
        assert "subsystem" not in DRIVER_BODY, (
            "驱动器已开始按子系统记账，映射提案应扩充覆盖，本取证需重新评估"
        )
        assert UNATTRIBUTABLE_DRIVER_POOLS, "无法归因池不得为空：那等于声称全都能归因"

    def test_an_attributable_pool_can_be_paid_into_the_envelope(self):
        gate = TokenEnvelopeGate()
        gate.record(
            day=0,
            subsystem=PROPOSED_SIM_SUBSYSTEM_MAPPING["dormant_prompt_tokens"],
            tokens=3000,
        )
        assert gate.spent() == 3000
        assert gate.verdict() is True

    def test_evidence_the_driver_total_prompt_tokens_undercounts(self):
        """**取证（行为级，用主干自己的公开 API）**：``prompt_token_total`` 名为 total，
        实为**最后一次渲染的快照** —— 它由 ``self.prompt_token_total = _approx_tokens(prompt)``
        赋值而非累加。驱动器却把它与累加量 ``llm.tokens`` 相加，得到
        ``report.prompt_tokens_total``，于是"总 prompt token"系统性少报。

        少报只会朝一个方向骗人：骗的是预算守卫。喂进封套判决门后，月帽检查偏松 ——
        虚拟人可能已经超支，而报告显示仍在封套内。这条取证不修改任何他人文件，
        只调用 ``register_task`` / ``tick`` / ``render_llm_prompt_context`` 三个公开方法。
        """
        from aios_core.scheduler.conditional_engine import (
            ConditionalSchedulerEngine, TimeArrivalCondition,
        )

        now = datetime(2026, 9, 16, tzinfo=timezone.utc)
        engine = ConditionalSchedulerEngine()
        condition = TimeArrivalCondition(due_at=now - timedelta(hours=1))
        engine.register_task(task_id="T1", title="第一个任务标题", conditions=[condition])
        engine.tick(now)
        engine.render_llm_prompt_context(now)
        first = engine.prompt_token_total
        assert first > 0, "第一次渲染应产生非零 token，否则本取证无意义"

        engine.register_task(task_id="T2", title="第二个任务标题" * 20, conditions=[condition])
        engine.tick(now)
        engine.render_llm_prompt_context(now)
        second = engine.prompt_token_total

        # 快照语义：字段值只反映最后一次渲染，第一次的花费被整段丢弃。
        # 若它改成累加，第二次读数必然 ≥ 两次之和，本断言即红（那是好消息）。
        assert first > 0 and second > first, f"渲染未产生可比较的读数：{first} / {second}"
        assert second < first + second, (
            f"prompt_token_total 已从快照改为累加（{first} -> {second}），本取证需重新评估"
        )
        # AST 侧同一条结论：该字段只有赋值、没有自增（字符串匹配会命中注释，故用语法树）
        from aios_core.scheduler import conditional_engine as ce_mod

        ce_tree = ast.parse(Path(ce_mod.__file__).read_text(encoding="utf-8"))
        assigns = [
            n for n in ast.walk(ce_tree)
            if isinstance(n, ast.Assign) and any(
                isinstance(tg, ast.Attribute) and tg.attr == "prompt_token_total" for tg in n.targets)
        ]
        augs = [
            n for n in ast.walk(ce_tree)
            if isinstance(n, ast.AugAssign)
            and isinstance(n.target, ast.Attribute) and n.target.attr == "prompt_token_total"
        ]
        assert assigns and not augs, (
            f"prompt_token_total 已出现自增（assign={len(assigns)} aug={len(augs)}），缺陷已修复"
        )

    def test_evidence_monthly_budget_has_two_mouths_and_they_must_agree(self):
        """**双口径钉死**：顶层 ``monthly_token_budget`` 与 ``token_budget.monthly_total_cap``
        是同一部法的两处表述。主干驱动器读前者，法定封套写后者；两处并存即可漂移，
        而漂移不会报错，只会让两拨代码各自守着不同的月帽。
        """
        assert ROOT["monthly_token_budget"] == ROOT["token_budget"]["monthly_total_cap"], (
            "两处月帽口径已漂移 —— 判决门与驱动器将各守一个上限"
        )
        assert ROOT["monthly_token_budget"] == MONTHLY_CAP
        # 驱动器读的正是前一个键，判决门读的正是后一个键；两者必须是同一部法
        assert "monthly_token_budget" in DRIVER_BODY
        assert TB["monthly_total_cap"] == MONTHLY_CAP

    @pytest.mark.parametrize("subsystem", sorted(SUBSYSTEMS))
    def test_every_subsystem_cap_is_within_the_monthly_envelope(self, subsystem):
        assert SUBSYSTEMS[subsystem]["monthly_cap"] <= MONTHLY_CAP

    @pytest.mark.parametrize("subsystem", sorted(SUBSYSTEMS))
    def test_spending_exactly_the_cap_is_not_a_violation(self, subsystem):
        """边界：恰好等于上限合法，多一个 token 才违例。

        **必须按日铺开**：把整月配额记在一天会先触发日上限（85134），
        那测的就不是子系统上限了。这本身也是个发现 —— 多个子系统的月帽
        远大于日帽，所以任何子系统都不可能在一天内花完一个月的额度。
        """
        cap = SUBSYSTEMS[subsystem]["monthly_cap"]
        per_day, remainder = divmod(cap, VIRTUAL_DAYS_REQUIRED)
        gate = TokenEnvelopeGate()
        for day in range(VIRTUAL_DAYS_REQUIRED):
            gate.record(
                day=day, subsystem=subsystem,
                tokens=per_day + (remainder if day == 0 else 0),
            )
        assert gate.spent(subsystem) == cap
        assert gate.violations() == ()
        assert gate.headroom(subsystem) == 0
        gate.record(day=1, subsystem=subsystem, tokens=1)
        found = gate.violations()
        assert len(found) == 1
        assert found[0].legal_cap == cap
        assert found[0].scope == "subsystem_monthly"
        assert gate.headroom(subsystem) == -1
        assert cap // VIRTUAL_DAYS_REQUIRED <= DAILY_CAP

    def test_heartbeat_cap_matches_its_policy_basis_arithmetic(self):
        """政策 basis 散文的算术锚：240 次/月 × (1-0.8) × 750 = 36000。

        散文不进生产代码解析（与 M2-001/M3-001R 同一手法），但它证明取消率 0.8 是
        预算闭合的承重参数。另注意浮点陷阱：1-0.8 == 0.19999999999999996，
        故必须用 round 而非 int 截断。
        """
        share = ROOT["heartbeat"]["gate_cancel_target_share"]
        assert round(240 * (1 - share) * 750) == SUBSYSTEMS["heartbeat"]["monthly_cap"] == 36000

    def test_dimension_cap_matches_its_policy_basis_arithmetic(self):
        assert 10 * 3000 == SUBSYSTEMS["dimension"]["monthly_cap"] == 30000

    def test_several_subsystem_caps_close_on_their_basis_arithmetic(self):
        """多项 basis 散文可精确复算 —— 说明这些上限是**推导值**而非凑数。"""
        assert 30 * (400 + 150) * 30 == SUBSYSTEMS["conversation.fast"]["monthly_cap"]
        assert 60 * 200 * 30 == SUBSYSTEMS["extract"]["monthly_cap"]
        assert (4 * 1800 * 30) + (48 * 2500) + (12 * 4000) == SUBSYSTEMS["summary"]["monthly_cap"]
        assert 60 * 2500 == SUBSYSTEMS["event"]["monthly_cap"]
        assert 20 * 1500 == SUBSYSTEMS["prediction"]["monthly_cap"]
        assert 30 * 3000 == SUBSYSTEMS["reflection"]["monthly_cap"]
        assert 10 * 3000 == SUBSYSTEMS["dimension"]["monthly_cap"]

    def test_deep_conversation_cap_covers_its_basis_with_headroom(self):
        """``conversation.deep`` 的 basis 是"封顶 8K/次、3 次/日"，但同句还写了
        "用户显式要求深度复盘才放开到 100K" —— 故上限**大于**基线算术是有意留的余量，
        不能按相等断言。这条测试把"为什么这里不相等"钉住，避免后人误判为漂移。
        """
        basis_spend = 3 * 8000 * 30
        assert SUBSYSTEMS["conversation.deep"]["monthly_cap"] >= basis_spend
        assert "放开到 100K" in SUBSYSTEMS["conversation.deep"]["basis"]

    def test_daily_total_cap_is_enforced(self):
        gate = TokenEnvelopeGate()
        gate.record(day=3, subsystem="conversation.fast", tokens=DAILY_CAP)
        assert gate.violations() == ()
        gate.record(day=3, subsystem="extract", tokens=1)
        found = gate.violations()
        assert any(v.scope == "daily_total" and v.day == 3 for v in found)

    def test_daily_cap_times_thirty_exceeds_the_monthly_cap(self):
        """**真实政策发现**：85134 × 30 = 2,554,020 > 2,554,000，多出 20 token。

        也就是说日上限连乘满 30 天会比月上限宽松，真正绑定的是月帽。两条上限并非
        互相推导（月帽是 12 个子系统的零基闭合值，日帽是独立给的），所以这类 20 token
        量级的缝隙会一直存在。后果不严重，但**判决门必须两道都查**：只查日上限的话，
        一个天天贴着 85134 花的虚拟人会在第 30 天冲破月帽而一路绿灯。
        """
        assert DAILY_CAP * VIRTUAL_DAYS_REQUIRED == 2554020
        assert DAILY_CAP * VIRTUAL_DAYS_REQUIRED - MONTHLY_CAP == 20

    def test_a_virtual_day_at_the_daily_cap_breaks_the_monthly_cap(self):
        """承上：天天恰好花到日上限（合法），第 30 天必然冲破月帽。"""
        gate = TokenEnvelopeGate()
        per_day = DAILY_CAP
        for day in range(VIRTUAL_DAYS_REQUIRED):
            # 拆成两个子系统记，避免单个子系统月帽先被触发
            gate.record(day=day, subsystem="conversation.deep", tokens=per_day - 1200)
            gate.record(day=day, subsystem="extract", tokens=1200)
        assert gate.spent() == per_day * VIRTUAL_DAYS_REQUIRED == MONTHLY_CAP + 20
        found = gate.violations()
        assert any(v.scope == "monthly_total" for v in found)
        assert not any(v.scope == "daily_total" for v in found), "每天都没超日上限"

    def test_monthly_total_cap_is_enforced_on_a_controllable_policy(self):
        """用小数字的注入政策把月帽判据单独钉住（真实政策的三个上限互相纠缠）。"""
        tiny = {
            "monthly_total_cap": 100,
            "daily_total_cap": 4,
            "subsystems": {
                "conversation.fast": {"monthly_cap": 60},
                "extract": {"monthly_cap": 40},
            },
        }
        gate = TokenEnvelopeGate(token_budget_policy=tiny)
        assert gate.audit()["zero_base_closure_holds"] is True
        for day in range(VIRTUAL_DAYS_REQUIRED):
            gate.record(day=day, subsystem="conversation.fast", tokens=2)
            gate.record(day=day, subsystem="extract", tokens=2)
        assert gate.spent() == 120
        found = gate.violations()
        # conversation.fast 恰好 60 == 上限（不违例）；extract 60 > 40（违例）；
        # 月度 120 > 100（违例）；每天 4 == 日上限（不违例）。
        assert [(v.scope, v.subsystem) for v in found] == [
            ("subsystem_monthly", "extract"),
            ("monthly_total", "*"),
        ]
        assert not any(v.scope == "daily_total" for v in found)

    def test_violations_returns_all_of_them_not_just_the_first(self):
        gate = TokenEnvelopeGate()
        for day, name in enumerate(("heartbeat", "dimension", "prediction")):
            gate.record(day=day, subsystem=name, tokens=SUBSYSTEMS[name]["monthly_cap"] + 1)
        found = gate.violations()
        assert len(found) == 3, "应当恰好三条子系统违例，且未连带触发日上限"
        assert all(v.scope == "subsystem_monthly" for v in found)
        assert {v.subsystem for v in found} == {"heartbeat", "dimension", "prediction"}

    def test_negative_tokens_are_refused(self):
        gate = TokenEnvelopeGate()
        with pytest.raises(SimVerdictGateError, match="不得为负"):
            gate.record(day=0, subsystem="extract", tokens=-1)

    def test_days_outside_the_legal_window_are_refused(self):
        gate = TokenEnvelopeGate()
        for bad in (-1, VIRTUAL_DAYS_REQUIRED, 999):
            with pytest.raises(SimVerdictGateError, match="法定窗口"):
                gate.record(day=bad, subsystem="extract", tokens=1)

    def test_violation_cites_the_legal_cap(self):
        """违例不引用法定上限就无法复核 —— 这是审计的最小信息量要求。"""
        violation = TokenViolation(
            day=2, subsystem="heartbeat", tokens=40000, legal_cap=36000,
            scope="subsystem_monthly",
        )
        payload = violation.to_audit()
        assert payload["legal_cap"] == 36000
        assert payload["overage"] == 4000
        assert payload["scope"] == "subsystem_monthly"

    def test_audit_is_json_serializable(self):
        import json

        gate = TokenEnvelopeGate()
        gate.record(day=0, subsystem="heartbeat", tokens=99999)
        text = json.dumps(gate.audit(), ensure_ascii=False)
        assert json.loads(text)["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# C · 门 2：纵向退化守卫
# ---------------------------------------------------------------------------


class TestDegradationGuard:
    def test_all_twenty_five_legal_invariants_are_registered(self):
        guard = DegradationGuard()
        assert len(guard.metric_ids) == 26
        assert set(guard.metric_ids) == set(INVARIANTS)

    def test_the_five_degradations_named_by_the_policy_are_all_measurable(self):
        """政策 ``$comment`` 点名的五种退化，每一种都必须有对应的法定指标。

        这五种退化的共同点是"快照式测试下表现为'这一轮指标还行'，只在趋势上可见"。
        若其中一种在指标清单里缺席，它就会正好发生在没人测的那一项上。
        """
        named = {
            "STALE 累积": "debt.stale_object_count",
            "复核队列增长": "debt.review_queue_oldest_age_days",
            "维度棘轮": "debt.dimension_active_count",
            "召回率随规模下降": "retrieval.golden_recall",
            "打扰率随自信上升": "intrusion.unnecessary_rate_7d_ma",
        }
        for description, metric_id in named.items():
            assert metric_id in INVARIANTS, f"{description} 缺少法定指标 {metric_id}"

    def test_a_healthy_thirty_day_life_passes_every_invariant(self):
        guard = healthy_guard()
        verdicts = guard.render()
        assert len(verdicts) == 26
        assert all(v.passed for v in verdicts)
        assert guard.blockers() == ()
        assert guard.audit()["blockers"] == 0

    def test_an_insufficient_window_refuses_to_render_a_verdict(self):
        """窗口不足**不判决**：用 10 天的趋势冒充 30 天的结论，正是快照式测试的错法。"""
        guard = DegradationGuard()
        for metric_id in guard.metric_ids:
            for day in range(10):
                guard.record_day(metric_id=metric_id, day=day, value=0.0)
        with pytest.raises(SimVerdictGateError, match="compressed_30_virtual_days"):
            guard.render()

    def test_a_short_window_still_reports_per_invariant_when_explicitly_asked(self):
        guard = DegradationGuard()
        for metric_id in guard.metric_ids:
            for day in range(10):
                guard.record_day(metric_id=metric_id, day=day, value=0.0)
        verdicts = guard.render(require_full_window=False)
        assert all(not v.passed for v in verdicts)
        assert all("数据不全" in v.reason for v in verdicts)

    def test_a_single_missing_metric_fails_rather_than_being_skipped(self):
        """缺指标即失败，不静默跳过 —— 少一条数据不是少一行输出，是少一个判决。"""
        guard = healthy_guard()
        guard._series["retrieval.golden_recall"].pop(17)
        with pytest.raises(SimVerdictGateError, match="数据不足"):
            guard.render()
        verdicts = guard.render(require_full_window=False)
        failed = [v for v in verdicts if not v.passed]
        assert len(failed) == 1
        assert failed[0].metric_id == "retrieval.golden_recall"
        assert INVARIANTS["retrieval.golden_recall"]["severity"] == "blocker"
        assert failed[0].blocks is True

    def test_duplicate_daily_record_is_refused(self):
        guard = DegradationGuard()
        guard.record_day(metric_id="debt.stale_object_count", day=0, value=1.0)
        with pytest.raises(SimVerdictGateError, match="重复记账"):
            guard.record_day(metric_id="debt.stale_object_count", day=0, value=2.0)

    def test_unknown_metric_is_refused(self):
        guard = DegradationGuard()
        with pytest.raises(SimVerdictGateError, match="未知指标"):
            guard.record_day(metric_id="help.made_up_metric", day=0, value=1.0)

    def test_days_outside_the_window_are_refused(self):
        guard = DegradationGuard()
        with pytest.raises(SimVerdictGateError, match="法定窗口"):
            guard.record_day(metric_id="debt.stale_object_count", day=30, value=1.0)

    def test_the_seven_day_average_produces_no_point_before_day_seven(self):
        guard = healthy_guard()
        ma = guard.moving_average("debt.stale_object_count")
        assert len(ma) == VIRTUAL_DAYS_REQUIRED - SMOOTHING_DAYS + 1 == 24

    def test_non_decreasing_violation_is_detected(self):
        spec = INVARIANTS["retrieval.golden_recall"]
        assert spec["trend"] == "non_decreasing"
        guard = ramp_guard("retrieval.golden_recall", 0.9, 0.5)  # 召回率随规模下降
        verdict = next(v for v in guard.render() if v.metric_id == "retrieval.golden_recall")
        assert verdict.passed is False
        assert spec["severity"] == "blocker"
        assert verdict.blocks is True
        assert verdict.final_ma < verdict.baseline

    def test_non_increasing_violation_is_detected(self):
        spec = INVARIANTS["intrusion.unnecessary_rate_7d_ma"]
        assert spec["trend"] == "non_increasing"
        guard = ramp_guard("intrusion.unnecessary_rate_7d_ma", 0.01, 0.30)  # 打扰率随自信上升
        verdict = next(
            v for v in guard.render()
            if v.metric_id == "intrusion.unnecessary_rate_7d_ma"
        )
        assert verdict.passed is False
        assert verdict.worst > 0

    def test_bounded_violation_is_detected(self):
        """``cost.tokens_per_virtual_day`` tolerance=0.15：相对基线涨幅超 15% 即违例。"""
        spec = INVARIANTS["cost.tokens_per_virtual_day"]
        assert spec["trend"] == "bounded" and spec["severity"] == "blocker"
        guard = healthy_guard()
        for day in range(VIRTUAL_DAYS_REQUIRED):
            guard._series["cost.tokens_per_virtual_day"][day] = 1000.0 + 20.0 * day
        verdict = next(
            v for v in guard.render() if v.metric_id == "cost.tokens_per_virtual_day"
        )
        assert verdict.passed is False
        assert verdict.blocks is True
        assert "1.15" in verdict.reason or "基线" in verdict.reason

    def test_a_bounded_rise_within_tolerance_passes(self):
        guard = healthy_guard()
        for day in range(VIRTUAL_DAYS_REQUIRED):
            guard._series["cost.tokens_per_virtual_day"][day] = 1000.0 + 1.0 * day
        verdict = next(
            v for v in guard.render() if v.metric_id == "cost.tokens_per_virtual_day"
        )
        # 末日 1029 相对基线（前 7 日均值 1003）涨幅约 2.6% < 15%
        assert verdict.passed is True

    def test_zero_tolerance_bounded_metrics_must_stay_at_zero(self):
        """tolerance=0 且基线=0 的计数型指标退化为"必须恒为 0"，
        与政策别处给出的绝对判据（如 fixed_rhythm_bomb_count_under_7d_stable_data=0、
        false_playback_without_epoch=0）一致 —— 这条自洽性是提案解释的主要依据。
        """
        for metric_id, spec in INVARIANTS.items():
            if spec["trend"] == "bounded" and spec["tolerance"] == 0:
                guard = healthy_guard()
                guard._series[metric_id][20] = 1.0  # 只要有一天冒出 1 次
                verdict = next(v for v in guard.render() if v.metric_id == metric_id)
                assert verdict.passed is False, f"{metric_id} 应当零容忍"
                assert spec["severity"] == "blocker"

    def test_flat_violation_is_detected(self):
        spec = INVARIANTS["latency.legal_first_token_p95_ms"]
        assert spec["trend"] == "flat" and spec["tolerance"] == 0.2
        guard = healthy_guard()
        for day in range(VIRTUAL_DAYS_REQUIRED):
            guard._series["latency.legal_first_token_p95_ms"][day] = 800.0 + 20.0 * day
        verdict = next(
            v for v in guard.render() if v.metric_id == "latency.legal_first_token_p95_ms"
        )
        assert verdict.passed is False
        assert verdict.blocks is True

    def test_flat_metric_with_zero_baseline_must_not_move(self):
        spec = INVARIANTS["integrity.tombstone_lookup_hit_rate"]
        assert spec["trend"] == "flat" and spec["tolerance"] == 0.0
        guard = healthy_guard()
        guard._series["integrity.tombstone_lookup_hit_rate"][29] = 0.001
        verdict = next(
            v for v in guard.render() if v.metric_id == "integrity.tombstone_lookup_hit_rate"
        )
        assert verdict.passed is False

    def test_warning_severity_does_not_block_but_is_recorded(self):
        spec = INVARIANTS["debt.stale_object_count"]
        assert spec["severity"] == "warning"
        guard = ramp_guard("debt.stale_object_count", 10.0, 500.0)
        verdict = next(v for v in guard.render() if v.metric_id == "debt.stale_object_count")
        assert verdict.passed is False
        assert verdict.blocks is False, "warning 级违例不得阻断判决门"
        assert guard.audit()["warnings"] >= 1
        assert guard.blockers() == () or all(v.metric_id != "debt.stale_object_count" for v in guard.blockers())

    def test_blocker_and_warning_are_distinguished_by_the_law_not_by_us(self):
        severities = {spec["severity"] for spec in DG["invariants"]}
        assert severities == {"warning", "blocker"}
        blockers = [m for m, s in INVARIANTS.items() if s["severity"] == "blocker"]
        assert len(blockers) > 10

    def test_the_dimension_ratchet_is_a_legally_tracked_degradation(self):
        """维度棘轮（M3-001R 的对手指标）必须在退化清单里，否则托管白做。"""
        spec = INVARIANTS["debt.dimension_active_count"]
        assert spec["trend"] == "bounded"
        assert spec["tolerance"] == 0.2
        guard = ramp_guard("debt.dimension_active_count", 8.0, 40.0)
        verdict = next(
            v for v in guard.render() if v.metric_id == "debt.dimension_active_count"
        )
        assert verdict.passed is False

    def test_audit_is_json_serializable(self):
        import json

        payload = json.loads(json.dumps(healthy_guard().audit(), ensure_ascii=False))
        assert payload["invariants_total"] == 26
        assert payload["passed"] == 26
        assert payload["measurement"] == "compressed_30_virtual_days"


# ---------------------------------------------------------------------------
# D · 门 3/4：CI 运行时预算与确定性
# ---------------------------------------------------------------------------


class TestRuntimeAndDeterminism:
    def test_ci_ceiling_comes_from_policy(self):
        gate = RuntimeBudgetGate()
        assert gate.minutes_max == DG["ci_runtime_minutes_max_mock_adapter"] == 15
        assert gate.seconds_max == 900.0

    def test_runtime_boundary(self):
        gate = RuntimeBudgetGate()
        assert gate.check(900.0) is True
        assert gate.check(900.001) is False
        assert gate.remaining_seconds(60.0) == 840.0

    def test_negative_wall_clock_is_refused(self):
        with pytest.raises(SimVerdictGateError, match="不得为负"):
            RuntimeBudgetGate().check(-1.0)

    def test_enforce_raises_above_the_ceiling(self):
        gate = RuntimeBudgetGate()
        gate.enforce(12.0)
        with pytest.raises(SimVerdictGateError, match="法定上限"):
            gate.enforce(1000.0)

    def test_the_ci_runtime_ceiling_is_a_mechanism_not_a_hope(self):
        """法定 ``ci_runtime_minutes_max_mock_adapter = 15`` 必须由机制承载。

        这里换过一次判据，原因记在案：原先本测试去读兄弟测试文件，断言它自设的墙钟上界
        ``wall_seconds < 120.0`` 落在法定 15 分钟之内。主干重写后**那条自设界已经不存在**
        （兄弟测试改为 ``days=180``，不再断言墙钟），本测试随之变红 —— 拿别人的自设界
        当自己的判据，别人一改我就红，而且红得像是法定上限失守。改为直接测本模块的门。

        顺带记一处口径差：兄弟测试跑 180 虚拟日，而法定测量窗口是
        ``compressed_30_virtual_days``。跑更长不违规，但**判决必须按法定 30 日窗口**做 ——
        180 日的趋势会把某个 30 日窗口内的退化摊平。这与 :meth:`DegradationGuard.render`
        在窗口不足时抛错是同一条纪律的两面。
        """
        sibling = Path(__file__).parent / "test_30day_headless_life_simulation.py"
        assert sibling.exists()
        gate = RuntimeBudgetGate()
        assert gate.seconds_max == 900.0 == 15 * 60
        assert gate.check(900.0) is True          # 恰好在上限：合法
        assert gate.check(900.1) is False         # 超出一瞬：不合法
        assert DG["measurement"] == "compressed_30_virtual_days"
        assert VIRTUAL_DAYS_REQUIRED == 30

    def test_determinism_passes_for_a_seeded_run(self):
        def run_once():
            rng = random.Random(20260916)
            return {"series": [round(rng.gauss(70, 5), 6) for _ in range(20)]}

        digest = DeterminismGate().verify(run_once)
        assert len(digest) == 64

    def test_determinism_detects_a_wall_clock_dependency(self):
        """**敏感度证明**：混入墙钟就必须变红，否则这道门等于没有。"""

        def run_once():
            return {"t": datetime.now(timezone.utc).timestamp()}

        with pytest.raises(SimVerdictGateError, match="非确定性"):
            DeterminismGate().verify(run_once)

    def test_determinism_detects_an_unseeded_rng(self):
        def run_once():
            return {"v": random.random()}

        with pytest.raises(SimVerdictGateError, match="非确定性"):
            DeterminismGate().verify(run_once)

    def test_determinism_requires_at_least_two_runs(self):
        with pytest.raises(SimVerdictGateError, match="两次"):
            DeterminismGate().verify(lambda: {}, runs=1)

    def test_the_driver_is_seeded_by_a_literal_not_by_the_clock(self):
        """法定 ``deterministic_seed_required = true`` 必须由机制承载。

        判据换过一次：原先断言 ``HeadlessLifeDriver()._rng`` 的状态等于固定种子。
        主干重写后驱动器构造函数改签名（需 ``cfg`` 与 ``db_path``），``_rng`` 也移进了
        ``CircadianPersona`` —— 旧判据随之失效。改写后测的是**同一条法律的更强形式**：
        种子必须是源码里的字面量，不能由墙钟派生（AST 判据），且节律发生器的 rng
        确实由它派生（行为判据）。
        """
        assert DG["deterministic_seed_required"] is True
        cfg = driver.SimConfig()
        assert cfg.seed == 20260916
        # AST：seed 的默认值必须是字面量常量，不得是 time()/urandom 之类的派生
        tree = ast.parse(DRIVER_SOURCE)
        cfg_cls = next(n for n in tree.body
                       if isinstance(n, ast.ClassDef) and n.name == "SimConfig")
        seed_default = next(
            st.value for st in cfg_cls.body
            if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)
            and st.target.id == "seed"
        )
        assert isinstance(seed_default, ast.Constant) and isinstance(seed_default.value, int), (
            f"种子默认值不再是整型字面量：{ast.unparse(seed_default)}"
        )
        # 行为：节律发生器的随机流确实由该种子派生 → 同种子必同序列
        persona = driver.CircadianPersona(cfg)
        assert persona._rng.getstate() == random.Random(cfg.seed).getstate()

    def test_digest_is_stable_across_key_order(self):
        gate = DeterminismGate()
        assert gate.digest({"a": 1, "b": 2}) == gate.digest({"b": 2, "a": 1})


# ---------------------------------------------------------------------------
# E · 可失败的测量（对照并行线的自证常量）
# ---------------------------------------------------------------------------


class TestMeasurementsThatCanFail:
    def test_evidence_deadlock_counting_is_fixed_and_residency_moved_not_fixed(self):
        """**取证（AST，不代改他人文件；主干重写后复核，一条已修、一条只是搬了家）**。

        原取证：驱动器把 ``raw_bytes_resident = 0`` 写在主循环里、``deadlocks = 0`` 写在
        结尾，测试断言二者 ``== 0``，因此永远为真。主干重写后：

        * **死锁一条已真修好**：``report.deadlock_cycles += 1`` 在检出环时累加，
          这条断言现在**可以失败**了。如实记为主干的改进。
        * **驻留一条只是搬了家**：报告端改成真管道
          ``report.raw_binary_retained_bytes = self.cleaner.raw_binary_retained_bytes``，
          但**喂入端**仍是 ``self.raw_binary_retained_bytes += 0``，旁边注释自己写明
          "原始字节从不入账（构造性为 0）"。字段仍不可能非零，而外观上多了管道，
          比原来更容易被误读成"已经测了"。

        两条都用 AST 判据（字符串匹配会命中 docstring 与注释里的正当提及）。
        """
        tree = ast.parse(DRIVER_SOURCE)
        aug = [
            (n.target.attr, n.lineno) for n in ast.walk(tree)
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Attribute)
            and n.target.attr == "deadlock_cycles"
        ]
        assert aug, "死锁计数已不再是累加 —— 主干的修复被回退了，本取证需重新评估"

        # 驻留字段的喂入端：找 += 0 这种"加了个零"的自增
        zero_feed = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Attribute)
            and n.target.attr == "raw_binary_retained_bytes"
            and isinstance(n.value, ast.Constant) and n.value.value == 0
        ]
        assert zero_feed, (
            "驻留字段的喂入端已改为真实计量 —— 缺陷已修复，本取证应改写为回归守卫"
        )
        # 且报告端确实是管道（不是字面量 0），据此才能说"搬了家"而不是"原样未动"。
        # 判据必须限定到 ``report.<field>``：清洗器 __init__ 里的零初始化是正当的，
        # 不限定就会把它误判成"报告端写死 0"（第一版正是这么误判的）。
        report_side = [
            (ast.unparse(n.value), n.lineno) for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Attribute)
            and n.targets[0].attr == "raw_binary_retained_bytes"
            and isinstance(n.targets[0].value, ast.Name)
            and n.targets[0].value.id == "report"
        ]
        assert report_side, "报告端不再回传该字段 —— 管道被拆了，本取证需重新评估"
        assert not any(isinstance(n, ast.Constant) for _ in report_side
                       for n in [ast.parse(v, mode="eval").body for v, _ in report_side]), (
            f"报告端又变回字面量常量了 —— 比搬家更糟：{report_side}"
        )

    def test_evidence_the_driver_reads_the_monthly_budget_but_nothing_else(self):
        """**取证（主干重写后复核：缺口收窄，但没闭合）**。

        原取证是"驱动器对政策零引用"。主干重写后有了 :func:`load_token_policy`，
        真读 ``monthly_token_budget`` 与 ``hard_rules.raw_binary_image_retention_bytes_max``
        —— 这是实质改进，如实记下，本测试也据此改写：不再断言"零引用"，
        而是断言**哪些读了、哪些仍然没读**，并把"仍然没读"的那五项钉住。

        仍然为 0 的五项，每一项都是一条没有机制承载的法律：
        ``daily_total_cap``（日上限）、``monthly_total_cap``（法定封套的月帽键路径 ——
        驱动器读的是另一个同值键，见双口径测试）、``degradation_invariants``（26 条不变量）、
        ``ci_runtime_minutes``（15 分钟天花板）、``deterministic_seed``（确定性种子要求）。
        """
        # 已读：这两项必须继续读，回退即红
        for token in ("runtime_policy", "monthly_token_budget"):
            assert token in DRIVER_BODY, f"{token} 的读取被移除了 —— 主干的改进被回退"
        # 仍未读：五项法律无机制承载
        for token in ("daily_total_cap", "monthly_total_cap", "degradation_invariants",
                      "ci_runtime_minutes", "deterministic_seed"):
            assert token not in DRIVER_BODY, (
                f"{token} 已被驱动器读取 —— 缺口收窄，本取证需重新评估（这是好消息）"
            )

    def test_residency_probe_reports_zero_for_a_clean_product(self):
        probe = ResidencyProbe(min_bytes=1024)
        assert probe.scan({"caption": "一只猫趴在桌上", "tags": ["cat"]}) == 0

    def test_residency_probe_finds_a_leaked_raw_payload(self):
        """**敏感度证明**：真的泄漏时探针必须报出来（自证常量做不到这一点）。"""
        probe = ResidencyProbe(min_bytes=1024)
        product = {"observations": [{"caption": "x", "raw": bytes(4096)}]}
        assert probe.scan(product) == 1
        with pytest.raises(SimVerdictGateError, match="C01 铁律违例"):
            probe.assert_clean(product)

    def test_residency_probe_scans_nested_dataclasses(self):
        @dataclass
        class Obs:
            caption: str
            payload: bytes

        probe = ResidencyProbe(min_bytes=1024)
        assert probe.scan([Obs("x", bytes(2048))], label="batch") == 1
        assert probe.observations[0]["label"].endswith("payload")

    def test_residency_probe_respects_the_threshold(self):
        probe = ResidencyProbe(min_bytes=1024)
        assert probe.scan({"small": bytes(16)}) == 0
        assert probe.scan({"big": bytes(1024)}) == 1

    def test_residency_probe_survives_a_self_referential_structure(self):
        """深度上限防病态自引用结构导致无限递归（探针自己挂掉就测不出任何东西）。"""
        probe = ResidencyProbe(min_bytes=1024)
        cyclic: dict = {"name": "loop"}
        cyclic["self"] = cyclic
        assert probe.scan(cyclic) == 0

    def test_residency_probe_rejects_a_non_positive_threshold(self):
        with pytest.raises(SimVerdictGateError, match="必须为正"):
            ResidencyProbe(min_bytes=0)

    def test_thread_delta_measures_zero_for_a_single_threaded_run(self):
        with measure_thread_delta() as measurement:
            sum(range(1000))
        assert measurement.result.delta == 0

    def test_thread_delta_detects_a_spawned_thread(self):
        """**敏感度证明**：若哪天有人加了一条后台线程，这里会立刻变红。

        驱动器的"单线程无锁 ⇒ deadlock 没有物理载体"论证本身成立，但写成常量赋值
        之后，这个前提一旦被人破坏就再也不会被发现。
        """
        started = threading.Event()
        stop = threading.Event()

        def worker() -> None:
            started.set()
            stop.wait(5.0)

        with measure_thread_delta() as measurement:
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            assert started.wait(5.0), "工作线程未启动，测量无意义"
        stop.set()
        thread.join(5.0)
        assert measurement.result.delta >= 1

    def test_a_slots_dataclass_payload_is_still_detected(self):
        """主干 ``RunReport`` 是 ``slots=True`` 的 dataclass，**没有 ``__dict__``**。

        只靠 ``vars()`` 遍历会静默漏掉它的全部字段 —— 探针必须自己避免犯它要抓的错。
        """
        assert not hasattr(RunReport(), "__dict__")
        probe = ResidencyProbe(min_bytes=1024)
        assert probe.scan(RunReport()) == 0
        # slots dataclass 的字段也必须被遍历到：extra 是 dict，塞进载荷就得报出来
        assert probe.scan(RunReport(extra={"raw": bytes(4096)})) == 1

        @dataclass(slots=True, frozen=True)
        class Slotted:
            caption: str
            smuggled: bytes

        assert probe.scan(Slotted("x", bytes(8192))) == 1

    @pytest.mark.parametrize("shape", ["dict", "list", "dataclass", "slots_dataclass",
                                       "slots_class", "plain_object"])
    def test_every_container_shape_is_traversed(self, shape):
        """**四种遍历分支互为冗余纵深，但覆盖面必须穷尽**所有对象形态。

        变异测试发现：单独拆掉 dataclass 分支不会漏报（非 slots 对象走 __dict__、
        slots 对象走 __slots__，两者已穷尽形态）—— 那是等价变异，不是漏洞。本测试把
        这个结论钉成显式覆盖面：无论哪条分支干活，六种形态都必须被抓到。
        """
        payload = bytes(4096)

        @dataclass
        class Plain:
            raw: bytes

        @dataclass(slots=True, frozen=True)
        class Slotted:
            raw: bytes

        class SlotsOnly:
            __slots__ = ("raw",)

            def __init__(self, raw):
                self.raw = raw

        class Ordinary:
            def __init__(self, raw):
                self.raw = raw

        containers = {
            "dict": {"obs": {"raw": payload}},
            "list": [{"raw": payload}],
            "dataclass": Plain(payload),
            "slots_dataclass": Slotted(payload),
            "slots_class": SlotsOnly(payload),
            "plain_object": Ordinary(payload),
        }
        probe = ResidencyProbe(min_bytes=1024)
        assert probe.scan(containers[shape], label=shape) == 1, f"{shape} 形态漏报"

    def test_a_driver_report_can_be_probed_instead_of_trusted(self):
        """与自证常量的区别在于：这条断言**可以**失败。"""
        report = RunReport()
        probe = ResidencyProbe(min_bytes=1024)
        assert probe.scan(report, label="RunReport") == 0
        probe.assert_clean(report, label="RunReport")  # 不抛


# ---------------------------------------------------------------------------
# F · 汇总判决
# ---------------------------------------------------------------------------


class TestSimVerdict:
    def _all_green(self) -> SimVerdict:
        envelope = TokenEnvelopeGate()
        for day in range(VIRTUAL_DAYS_REQUIRED):
            envelope.record(day=day, subsystem="conversation.fast", tokens=1000)
        return build_verdict(
            envelope=envelope,
            guard=healthy_guard(),
            runtime=RuntimeBudgetGate(),
            wall_seconds=42.0,
            determinism_digest="a" * 64,
            thread_delta=0,
            raw_byte_payloads=0,
        )

    def test_all_four_gates_green_yields_pass(self):
        verdict = self._all_green()
        assert verdict.passed is True
        assert verdict.invariants_total == 26
        assert verdict.to_audit()["verdict"] == "PASS"

    def test_an_envelope_violation_fails_the_verdict(self):
        envelope = TokenEnvelopeGate()
        envelope.record(day=0, subsystem="heartbeat", tokens=SUBSYSTEMS["heartbeat"]["monthly_cap"] + 1)
        verdict = build_verdict(
            envelope=envelope,
            guard=healthy_guard(),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1.0,
            determinism_digest="a" * 64,
            thread_delta=0,
            raw_byte_payloads=0,
        )
        assert verdict.passed is False
        assert len(verdict.envelope_violations) == 1

    def test_a_degradation_blocker_fails_the_verdict(self):
        verdict = build_verdict(
            envelope=TokenEnvelopeGate(),
            guard=ramp_guard("retrieval.golden_recall", 0.9, 0.4),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1.0,
            determinism_digest="a" * 64,
            thread_delta=0,
            raw_byte_payloads=0,
        )
        assert verdict.passed is False
        assert any(v.metric_id == "retrieval.golden_recall" for v in verdict.degradation_blockers)

    def test_a_degradation_warning_alone_does_not_fail_the_verdict(self):
        """warning 与 blocker 的区别必须真的体现在判决上，否则严重度分级是装饰。"""
        verdict = build_verdict(
            envelope=TokenEnvelopeGate(),
            guard=ramp_guard("debt.stale_object_count", 10.0, 900.0),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1.0,
            determinism_digest="a" * 64,
            thread_delta=0,
            raw_byte_payloads=0,
        )
        assert verdict.degradation_warnings
        assert not verdict.degradation_blockers
        assert verdict.passed is True

    def test_running_over_the_ci_ceiling_fails_the_verdict(self):
        verdict = build_verdict(
            envelope=TokenEnvelopeGate(),
            guard=healthy_guard(),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1200.0,
            determinism_digest="a" * 64,
            thread_delta=0,
            raw_byte_payloads=0,
        )
        assert verdict.passed is False
        assert verdict.runtime_within_budget is False

    def test_a_thread_leak_fails_the_verdict(self):
        verdict = build_verdict(
            envelope=TokenEnvelopeGate(),
            guard=healthy_guard(),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1.0,
            determinism_digest="a" * 64,
            thread_delta=2,
            raw_byte_payloads=0,
        )
        assert verdict.passed is False

    def test_a_raw_byte_leak_fails_the_verdict(self):
        verdict = build_verdict(
            envelope=TokenEnvelopeGate(),
            guard=healthy_guard(),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1.0,
            determinism_digest="a" * 64,
            thread_delta=0,
            raw_byte_payloads=1,
        )
        assert verdict.passed is False

    def test_a_missing_determinism_digest_fails_the_verdict(self):
        """没跑过确定性门 ≠ 通过确定性门。"""
        verdict = build_verdict(
            envelope=TokenEnvelopeGate(),
            guard=healthy_guard(),
            runtime=RuntimeBudgetGate(),
            wall_seconds=1.0,
            determinism_digest=None,
            thread_delta=0,
            raw_byte_payloads=0,
        )
        assert verdict.passed is False

    def test_verdict_audit_is_json_serializable(self):
        import json

        payload = json.loads(json.dumps(self._all_green().to_audit(), ensure_ascii=False))
        assert payload["invariants_total"] == 26
        assert payload["envelope_violations"] == []
        assert payload["determinism_digest"] == "a" * 64

    def test_invariant_verdict_audit_carries_the_reason(self):
        """判决不带理由就无法复核，与"违例不引法定上限"是同一类缺陷。"""
        verdict = healthy_guard().render()[0]
        assert isinstance(verdict, InvariantVerdict)
        payload = verdict.to_audit()
        assert payload["reason"]
        assert payload["trend"] in PROPOSED_TREND_SEMANTICS
