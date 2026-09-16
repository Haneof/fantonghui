"""SIM-001 验收测试：无界面 30 天高熵多维人生仿真推演机。

工单：``arena/agent-sim-engine``
实现：``src/aios_core/simulation/headless_life_driver.py``

实战情境
--------------------------------------------------------------------------
纯 Python、零 UI 的虚拟人推演：30 天（720 小时）时空流涵盖昼夜节律、高频心率与 HRV、
工业车间高噪环境、120 次真实工作会议、突发商业危机，以及**老王合同违约**事件；
推演过程真实驱动 AIOS 六段技术链，并对死锁/内存/二进制滞留/月度 Token 封套立硬指标。

四大硬门禁 ↔ 用例
--------------------------------------------------------------------------
1. 720 小时高熵时空流（120 会议 + 危机 + 违约）—— ``test_gate1_*``
2. 驱动 AIOS 完整技术链（接入->C01->C06->C02->C04->C05）—— ``test_gate2_*``
3. 0 死锁 + RSS <= 128MB + 二进制滞留 0 —— ``test_gate3_*``（含哨兵"长牙"负向对照）
4. 月度 Token 封套（<= 2,554,000）—— ``test_gate4_*``
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest

from aios_core.simulation.headless_life_driver import (
    DEFAULT_MONTHLY_TOKEN_BUDGET,
    SIMULATION_DAYS_SHORT,
    ChainStage,
    DeadlockSentinel,
    HeadlessLifeDriver,
    LifeEventKind,
    SimulationConfig,
    StageTimeoutError,
    load_runtime_policy,
)

# ---------------------------------------------------------------------------
# 场景夹具：30 天推演只跑一次（module 级），四个门禁共用同一份证据
# ---------------------------------------------------------------------------

POLICY_TOKEN_BUDGET = 2_554_000
DAYS = SIMULATION_DAYS_SHORT
HOURS = DAYS * 24
MEETINGS = 120
SESSIONS_PER_DAY = 40
EXPECTED_SESSIONS = DAYS * SESSIONS_PER_DAY
FRAMES = DAYS * 6
RSS_BUDGET_MB = 128.0


@dataclass(frozen=True)
class _SimRun:
    """一次 30 天推演的完整证据（驱动 + 报告）。"""

    driver: HeadlessLifeDriver
    report: Any


@pytest.fixture(scope="module")
def simulation(tmp_path_factory: pytest.TempPathFactory) -> _SimRun:
    """30 天推演**只跑一遍**（约 2 秒），四个门禁共用同一份证据。"""
    db_path = tmp_path_factory.mktemp("sim001") / "world.db"
    driver = HeadlessLifeDriver(SimulationConfig(days=DAYS, db_path=str(db_path)))
    return _SimRun(driver=driver, report=driver.run(run_id="sim001-30d"))


@pytest.fixture(scope="module")
def report(simulation: _SimRun):
    return simulation.report


def _stage(report, stage: ChainStage):
    for item in report.stages:
        if item.stage is stage:
            return item
    raise AssertionError(f"阶段 {stage} 未执行")


# ===========================================================================
# 硬门禁 1：真实高熵成年人 30 天时空流
# ===========================================================================


def test_gate1_thirty_day_timeline_is_720_hours_and_high_entropy(
    simulation: _SimRun,
) -> None:
    driver = simulation.driver
    events = list(driver._timeline.events())
    kinds = {kind: sum(1 for e in events if e.kind is kind) for kind in LifeEventKind}

    assert driver.config.days == DAYS
    assert driver.config.hours == HOURS == 720
    assert kinds[LifeEventKind.CIRCADIAN_TICK] == HOURS, "每小时一个昼夜节律采样点"
    assert kinds[LifeEventKind.MEETING] == MEETINGS == 120, "全月恰好 120 次真实工作会议"
    assert kinds[LifeEventKind.BUSINESS_CRISIS] == 1
    assert kinds[LifeEventKind.CONTRACT_BREACH] == 1, "老王合同违约事件必须发生"
    assert kinds[LifeEventKind.WORKSHOP_NOISE] > 0, "工业车间高噪环境必须存在"
    assert kinds[LifeEventKind.CAPTURE_FRAME] == FRAMES

    # 昼夜节律必须真的是"高熵"：心率有波动、睡眠阶段有区分、HRV 与心率反相
    ticks = [e for e in events if e.kind is LifeEventKind.CIRCADIAN_TICK]
    heart_rates = [e.payload["heart_rate_bpm"] for e in ticks]
    hrvs = [e.payload["hrv_ms"] for e in ticks]
    stages = {e.payload["sleep_stage"] for e in ticks}
    assert max(heart_rates) - min(heart_rates) > 15.0, "心率必须跨昼夜显著波动"
    assert len(stages) >= 3, f"睡眠阶段至少 3 种（实测 {stages}）"
    assert max(hrvs) - min(hrvs) > 10.0
    night = [e for e in ticks if e.payload["sleep_stage"] == "deep_sleep"]
    assert all(e.payload["heart_rate_bpm"] < 70.0 for e in night), "深睡段心率必须落在静息区间"

    breach = next(e for e in events if e.kind is LifeEventKind.CONTRACT_BREACH)
    assert breach.payload["counterparty"] == "ent_wang"
    assert breach.payload["loss_cny"] == 23_000_000
    assert breach.occurred_at == driver._timeline.start + timedelta(days=26, hours=16, minutes=20)


def test_gate1_timeline_is_reproducible_with_the_same_seed() -> None:
    config = SimulationConfig(days=3, sessions_per_day=0)
    first = [(e.event_id, e.payload.get("heart_rate_bpm")) for e in HeadlessLifeDriver(config)._timeline.events()]
    second = [(e.event_id, e.payload.get("heart_rate_bpm")) for e in HeadlessLifeDriver(config)._timeline.events()]
    assert first == second, "同种子必须产出逐字节一致的时间流（可回归、可复现）"

    other = SimulationConfig(days=3, seed=config.seed + 1, sessions_per_day=0)
    third = [(e.event_id, e.payload.get("heart_rate_bpm")) for e in HeadlessLifeDriver(other)._timeline.events()]
    assert third != first, "不同种子必须产出不同的生理噪声（否则压测就是自欺欺人）"


def test_gate1_short_window_without_breach_is_refused(tmp_path) -> None:
    """窗口短到不含违约事件时不生成退化世界，而是显式报错。"""
    config = SimulationConfig(days=5, sessions_per_day=0, db_path=str(tmp_path / "short.db"))
    with pytest.raises(Exception) as excinfo:
        HeadlessLifeDriver(config).run(run_id="sim001-short")
    assert getattr(excinfo.value, "context", {}).get("reason") == "breach_event_missing"


def test_gate1_hundred_and_eighty_day_window_scales(tmp_path) -> None:
    """180 天长窗同样可跑（工单 30 天/180 天双口径），且不牺牲链路完整。"""
    config = SimulationConfig(days=180, meetings_total=720, sessions_per_day=0, db_path=str(tmp_path / "l180.db"))
    driver = HeadlessLifeDriver(config)
    result = driver.run(run_id="sim001-180d")

    assert result.hours_simulated == 180 * 24 == 4320
    assert result.meetings == 720
    assert result.deadlocks == 0
    assert result.tokens_within_budget is True
    print(
        f"[SIM-001 长窗] 180 天：事件={result.events_total} 会议={result.meetings} "
        f"峰值RSS={result.rss_peak_mb:.1f}MB 死锁={result.deadlocks}"
    )


# ===========================================================================
# 硬门禁 2：驱动 AIOS 完整技术链
# ===========================================================================


def test_gate2_all_six_stages_ran_in_order(report) -> None:
    """六段链路齐备且顺序自洽。

    顺序说明：C06 的倒排索引是**账本的只读派生**（``build_from_store`` 只调
    ``list_payloads``），因此必须在 C02 落账之后重建——否则穿透到的就是空图。
    这里断言的是真实可行的因果顺序，而不是纸面顺序。
    """
    order = [item.stage for item in report.stages]
    assert order == [
        ChainStage.INGEST,
        ChainStage.C01_EDGE_CLEAN,
        ChainStage.C02_LEDGER_PERSIST,
        ChainStage.C06_HYPERLINK_INTERSECT,
        ChainStage.C04_BOARD_ASSEMBLY,
        ChainStage.C05_RETRO_ANNOTATION,
    ], f"技术链阶段顺序不得错乱：{order}"
    assert all(item.ok for item in report.stages)
    assert all(item.events_in > 0 for item in report.stages)
    # C06 读到的就是 C02 写下的对象：索引非空即证明"账本 -> 索引"的因果连接真实存在
    c02 = _stage(report, ChainStage.C02_LEDGER_PERSIST)
    c06 = _stage(report, ChainStage.C06_HYPERLINK_INTERSECT)
    assert c02.detail["committed"] >= c06.detail["observations"]


def test_gate2_c01_edge_cleaning_purges_and_filters(report) -> None:
    c01 = _stage(report, ChainStage.C01_EDGE_CLEAN)
    assert c01.detail["frames_assessed"] == FRAMES
    assert c01.detail["purged_frames"] == FRAMES, "低画质帧必须被物理粉碎"
    assert c01.detail["bytes_freed"] > 0
    assert c01.detail["noise_filtered"] > 0, "车间高噪环境必须被门限过滤"
    assert c01.detail["live_frames_after_purge"] == 0
    assert c01.events_out < c01.events_in, "清洗后事件数必须减少（噪声被剔除）"


def test_gate2_c02_ledger_persisted_every_object_once(report, tmp_path) -> None:
    c02 = _stage(report, ChainStage.C02_LEDGER_PERSIST)
    assert c02.detail["committed"] == c02.events_out == c02.events_in
    assert c02.detail["batches"] >= 1
    assert c02.detail["world_revision"] >= 1
    assert c02.elapsed_ms > 0.0


def test_gate2_c06_inverted_intersection_walks_the_structured_chain(report) -> None:
    c06 = _stage(report, ChainStage.C06_HYPERLINK_INTERSECT)
    assert c06.detail["anchors"] >= 1, "违约事件锚点必须能被穿透到"
    assert c06.detail["evidence_sets"] >= 1
    assert c06.detail["observations"] >= 1, "必须落到具体客观事实上（而不是空图）"
    assert c06.detail["truncated"] is False


def test_gate2_c04_board_assembly_ran_every_session(report) -> None:
    c04 = _stage(report, ChainStage.C04_BOARD_ASSEMBLY)
    assert c04.events_in == DAYS
    assert c04.events_out == EXPECTED_SESSIONS == 1200
    assert c04.tokens > 0, "看板装配必须真实计量 Token"
    assert c04.detail["manifest_token_budget"] == 1500, "单看板封套必须沿用 C04 硬顶"


def test_gate2_c05_retrospective_annotation_kept_history_intact(report) -> None:
    c05 = _stage(report, ChainStage.C05_RETRO_ANNOTATION)
    assert c05.detail["history_unchanged"] is True, "回溯注记不得改写任何历史事实"
    assert c05.detail["matched"] > 800, "全量客观事实都必须通过哈希核对"
    before, after = c05.detail["world_revision"]
    assert after == before + 1, "注记只允许追加一个世界修订"


# ===========================================================================
# 硬门禁 3：0 死锁 + 内存平稳 + 二进制滞留 0
# ===========================================================================


def test_gate3_no_deadlock_across_the_whole_run(report) -> None:
    assert report.deadlocks == 0
    assert report.deadlock_free is True
    assert report.wall_clock_seconds < 600.0, "30 天推演必须远快于实时（1000x 加速口径）"


def test_gate3_memory_stays_flat_and_within_128mb(simulation: _SimRun, report) -> None:
    samples = simulation.driver.memory.samples
    assert len(samples) >= DAYS + 1, "必须逐日采样 RSS（至少 31 个样本）"
    assert report.rss_peak_mb <= RSS_BUDGET_MB, (
        f"峰值 RSS {report.rss_peak_mb:.2f}MB 超出 128MB 预算"
    )
    assert report.memory_within_budget is True
    assert report.rss_growth_mb <= 32.0, f"整月增长 {report.rss_growth_mb:.2f}MB 过高，疑似泄漏"
    assert report.rss_tail_flat is True, "尾部 RSS 必须平稳（泄漏不会自己回落）"
    print(
        f"[SIM-001 内存] 基线={report.rss_baseline_mb:.1f}MB 峰值={report.rss_peak_mb:.1f}MB "
        f"增长={report.rss_growth_mb:.2f}MB 样本={len(samples)} 尾窗平稳={report.rss_tail_flat}"
    )


def test_gate3_no_raw_binary_image_residue(report) -> None:
    assert report.raw_binary_residue_bytes == 0
    assert report.no_binary_residue is True
    c01 = _stage(report, ChainStage.C01_EDGE_CLEAN)
    assert c01.detail["live_frames_after_purge"] == 0, "粉碎后不得有任何帧字节滞留"
    assert c01.detail["purged_frames"] == FRAMES


def test_gate3_deadlock_sentinel_has_teeth() -> None:
    """负向对照：真的挂住时，哨兵必须报死锁（而不是静静通过）。"""
    sentinel = DeadlockSentinel(timeout_seconds=0.05)

    def _hang() -> None:
        time.sleep(2.0)

    with pytest.raises(StageTimeoutError) as excinfo:
        sentinel.run("c04_board_assembly", _hang)
    assert excinfo.value.context["reason"] == "stage_timeout"
    assert sentinel.deadlock_count == 1
    assert sentinel.timed_out_stages == ("c04_board_assembly",)
    sentinel.shutdown()


# ===========================================================================
# 硬门禁 4：月度 Token 封套核验
# ===========================================================================


def test_gate4_runtime_policy_declares_the_monthly_envelope() -> None:
    policy = load_runtime_policy()
    assert policy.monthly_token_budget == POLICY_TOKEN_BUDGET == DEFAULT_MONTHLY_TOKEN_BUDGET
    assert policy.manifest_token_budget == 1500
    assert policy.simulation["rss_budget_mb"] == 128
    assert policy.simulation["deadlock_budget"] == 0


def test_gate4_month_tokens_stay_inside_the_governance_envelope(report) -> None:
    assert report.token_budget == POLICY_TOKEN_BUDGET, "月度封套必须来自 runtime_policy.json"
    assert report.tokens_total > 0
    assert report.tokens_within_budget is True
    assert report.tokens_total <= POLICY_TOKEN_BUDGET, (
        f"30 天消耗 {report.tokens_total:,} tokens 超出 {POLICY_TOKEN_BUDGET:,} 月度封套"
    )
    assert sum(report.tokens_by_stage.values()) == report.tokens_total
    assert report.tokens_by_stage["c04_board_assembly"] == report.tokens_total, (
        "Token 只应来自真实的大模型上下文装配（其它阶段是纯机械处理）"
    )
    utilisation = report.tokens_total / POLICY_TOKEN_BUDGET
    assert 0.10 <= utilisation <= 1.0, f"负载失真：利用率 {utilisation:.0%} 不合常理"
    print(
        f"[SIM-001 Token 封套] 30 天消耗={report.tokens_total:,} / 预算={POLICY_TOKEN_BUDGET:,} "
        f"（利用率 {utilisation:.1%}），按阶段={report.tokens_by_stage}"
    )


def test_gate4_requesting_more_than_the_envelope_is_refused(tmp_path) -> None:
    """批处理不允许自说自话突破治理封套：预算必须落在策略文件允许的范围内。"""
    with pytest.raises(Exception):
        SimulationConfig(
            days=DAYS,
            monthly_token_budget=POLICY_TOKEN_BUDGET * 24,
            db_path=str(tmp_path / "x.db"),
        )


# ===========================================================================
# 总览
# ===========================================================================


def test_simulation_report_summarises_all_four_gates(report) -> None:
    summary = report.summary()
    assert summary["hours"] == HOURS
    assert summary["meetings"] == MEETINGS
    assert summary["deadlocks"] == 0
    assert summary["raw_binary_residue_bytes"] == 0
    assert summary["tokens_total"] <= POLICY_TOKEN_BUDGET
    assert summary["events"] > HOURS, "事件密度必须高于小时采样（否则谈不上高熵）"
    assert summary["days"] == DAYS and summary["crises"] == 1 and summary["breaches"] == 1
    print(f"[SIM-001 总览] {summary}")
