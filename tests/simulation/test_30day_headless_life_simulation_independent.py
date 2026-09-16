"""SIM-001：无界面 Linux 30 天 / 180 天高熵人生仿真门禁测试。

零 UI、纯 Python。四道门禁全部取**实测值**，不接受硬编码。

被驱动的完整链路：
    数据接入 → C01 边缘清洗 → C06 倒排求交 → C02 账本持久化
             → C04 单看板装配 → C05 回溯注记
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios_core.simulation.headless_life_driver_independent import (
    BUSINESS_CRISIS_COUNT,
    CONTRACT_BREACH_COUNT,
    DEEP_SLEEP_END_HOUR,
    DEEP_SLEEP_START_HOUR,
    MEETING_COUNT,
    HeadlessLifeDriver,
    RuntimePolicy,
    SimulationConfig,
    SimulationReport,
)
from aios_core.world.retrospective_annotation import RetrospectiveAnnotationJournal

POLICY_PATH = Path(__file__).resolve().parents[2] / "governance" / "runtime_policy.json"


def _run(days: int, workdir: Path, *, seed: int = 20260916) -> tuple[SimulationReport, HeadlessLifeDriver]:
    """跑一遍完整推演，返回报告与驱动实例。"""
    workdir.mkdir(parents=True, exist_ok=True)
    policy = RuntimePolicy.load(POLICY_PATH)
    config = SimulationConfig(days=days, seed=seed)
    journal = RetrospectiveAnnotationJournal(workdir / "annotations.sqlite3")
    driver = HeadlessLifeDriver(
        config,
        ledger_conn=sqlite3.connect(workdir / "ledger.sqlite3"),
        index_conn=sqlite3.connect(workdir / "index.sqlite3"),
        annotation_journal=journal,
        policy=policy,
    )
    return driver.run(), driver


@pytest.fixture(scope="module")
def thirty_day(tmp_path_factory: pytest.TempPathFactory) -> SimulationReport:
    """整个模块只跑一次 30 天推演（约 1~3 秒），各门禁共享同一份报告。"""
    report, _driver = _run(30, tmp_path_factory.mktemp("sim30"))
    return report


@pytest.fixture(scope="module")
def one_eighty_day(tmp_path_factory: pytest.TempPathFactory) -> SimulationReport:
    report, _driver = _run(180, tmp_path_factory.mktemp("sim180"))
    return report


# ---------------------------------------------------------------------------
# 门禁 0：治理策略文件本身
# ---------------------------------------------------------------------------


def test_policy_file_exists_and_declares_the_2_554_000_budget() -> None:
    assert POLICY_PATH.exists(), "governance/runtime_policy.json 必须存在"
    policy = RuntimePolicy.load(POLICY_PATH)
    assert policy.monthly_total_tokens == 2_554_000
    assert policy.peak_rss_megabytes == 128
    assert policy.max_deadlock_count == 0
    assert policy.max_raw_image_retention_bytes == 0


# ---------------------------------------------------------------------------
# 门禁 1：720 小时连续时间流
# ---------------------------------------------------------------------------


def test_gate1_seven_hundred_twenty_continuous_hours(thirty_day: SimulationReport) -> None:
    assert thirty_day.days == 30
    assert thirty_day.total_hours == 720
    # 1 分钟粒度 × 720 小时 = 43,200 个 tick，一个都不能少
    assert thirty_day.ticks_processed == 720 * 60 == 43_200


def test_gate1_high_entropy_scenario_events_all_fired(
    thirty_day: SimulationReport,
) -> None:
    """120 次会议 / 1 次商业危机 / 1 次老王合同违约 / 工业高噪。"""
    assert thirty_day.meetings_held == MEETING_COUNT == 120
    assert thirty_day.business_crises == BUSINESS_CRISIS_COUNT == 1
    assert thirty_day.contract_breaches == CONTRACT_BREACH_COUNT == 1
    # 6 个高噪日 × 每天 9 小时 = 54 段
    assert thirty_day.noise_episodes == 54


def test_gate1_circadian_rhythm_actually_engages_deep_sleep(
    thirty_day: SimulationReport,
) -> None:
    """昼夜节律必须真实生效：02:00~06:00 的候选被静默闸拦下。

    每小时 1 条后台提醒 × 4 小时深睡 × 30 天 = 120 条被拦。
    """
    assert DEEP_SLEEP_START_HOUR == 2
    assert DEEP_SLEEP_END_HOUR == 6
    expected_suppressed = (DEEP_SLEEP_END_HOUR - DEEP_SLEEP_START_HOUR) * 30
    assert thirty_day.wake_suppressed_deep_sleep == expected_suppressed == 120


def test_gate1_heart_rate_and_hrv_stream_is_high_frequency(
    thirty_day: SimulationReport,
) -> None:
    """高频心率 / HRV 流：每分钟一帧，30 天不间断。"""
    assert thirty_day.chain_invocations["ingest"] == 43_200


# ---------------------------------------------------------------------------
# 门禁 2：完整链路被真实驱动
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage",
    [
        "ingest",
        "c01_edge_clean",
        "c06_inverted_intersect",
        "c02_ledger_persist",
        "c04_cockpit_assembly",
        "c05_retrospective_annotation",
    ],
)
def test_gate2_every_chain_stage_was_really_invoked(
    thirty_day: SimulationReport, stage: str
) -> None:
    assert thirty_day.chain_invocations[stage] > 0, f"{stage} 从未被调用"


def test_gate2_chain_is_complete_as_a_whole(thirty_day: SimulationReport) -> None:
    assert thirty_day.chain_complete is True


def test_gate2_ledger_index_annotations_all_populated(
    thirty_day: SimulationReport,
) -> None:
    """C02 / C06 / C05 三段必须留下可核对的物理产物。"""
    # 120 场会议 + 30 份日汇总 + 危机 + 违约 = 152 条封存事实
    assert thirty_day.facts_sealed == 152
    assert thirty_day.index_entities == 174
    assert thirty_day.index_postings > 3_000
    assert thirty_day.annotations_written == 30
    assert thirty_day.integrity_ok is True


def test_gate2_cockpit_assembles_one_bounded_prompt_per_wake(
    thirty_day: SimulationReport,
) -> None:
    """C04：每次真实唤醒只装配一份 Prompt，且总量受 1500 token 硬上限约束。"""
    assemblies = thirty_day.chain_invocations["c04_cockpit_assembly"]
    # 120 场会议 + 1 次危机 + 1 次违约
    assert assemblies == MEETING_COUNT + 2 == 122
    # 平均每次装配远低于 1500 token 硬上限
    average = thirty_day.total_tokens_used / assemblies
    assert average < 1_500


# ---------------------------------------------------------------------------
# 门禁 3：死锁 0 / RSS ≤128MB / 原始图片滞留 0
# ---------------------------------------------------------------------------


def test_gate3_zero_deadlocks(thirty_day: SimulationReport) -> None:
    assert thirty_day.deadlock_count == 0


def test_gate3_peak_rss_within_128mb(thirty_day: SimulationReport) -> None:
    assert thirty_day.peak_rss_megabytes <= 128.0


def test_gate3_rss_growth_is_module_attributable(thirty_day: SimulationReport) -> None:
    """V3G-012 修正后的门禁：只考核**归因于本次推演**的内存增量。

    旧写法直接断言进程级 ``ru_maxrss`` 高水位 < 64MB，而该值单调不减、
    包含同进程此前所有测试的峰值 —— 于是本测试单跑通过、全量跑失败。
    现在改读 ``/proc/self/statm`` 的当前驻留页，峰值与增量都是模块级的。
    """
    assert thirty_day.rss_baseline_megabytes > 0
    assert thirty_day.peak_rss_megabytes >= thirty_day.rss_baseline_megabytes
    # 30 天推演自身的内存占用必须很小
    assert thirty_day.rss_growth_megabytes < 32.0


def test_gate3_no_memory_leacross_two_consecutive_runs(
    tmp_path: Path,
) -> None:
    """连跑两遍 30 天，峰值 RSS 不得显著增长（无泄漏）。"""
    first, _ = _run(30, tmp_path / "run1")
    second, _ = _run(30, tmp_path / "run2")

    # 现在 peak 取的是**当前** RSS 峰值（会随释放回落），
    # 所以这个差值才真正有"泄漏"语义；旧写法下单调高水位永远只增不减，
    # 该断言实际上恒成立、什么也没验证。
    growth = second.peak_rss_megabytes - first.peak_rss_megabytes
    assert growth <= 16.0, (
        f"第二遍峰值 RSS 比第一遍高 {growth:.2f}MB，疑似泄漏"
    )
    assert second.rss_growth_megabytes < 32.0


def test_gate3_raw_binary_image_retention_is_strictly_zero(
    thirty_day: SimulationReport,
) -> None:
    assert thirty_day.raw_image_bytes_retained == 0
    # 确实处理过原始图像帧，"0 滞留"才有意义
    assert thirty_day.raw_image_frames_purged == 174


# ---------------------------------------------------------------------------
# 门禁 4：月度 Token 预算
# ---------------------------------------------------------------------------


def test_gate4_monthly_token_total_within_budget(
    thirty_day: SimulationReport,
) -> None:
    assert thirty_day.monthly_token_budget == 2_554_000
    assert thirty_day.total_tokens_used <= 2_554_000
    assert thirty_day.token_utilization <= 1.0


def test_gate4_token_spend_is_substantial_not_vacuously_zero(
    thirty_day: SimulationReport,
) -> None:
    """Token 预算门禁不能靠"什么都不干"通过。"""
    assert thirty_day.total_tokens_used > 50_000
    assert thirty_day.token_utilization > 0.01


# ---------------------------------------------------------------------------
# 与 M2-005R / M2-001 / M3-001R 的联动
# ---------------------------------------------------------------------------


def test_dimension_guards_fire_under_sustained_load(
    thirty_day: SimulationReport,
) -> None:
    """30 天里每日自省配额被对抗性探针撞了 30 次，全部被挡下。"""
    assert thirty_day.dimension_introspections == 30
    assert thirty_day.quota_blocks == 30
    assert thirty_day.recursion_cuts == 30


def test_wake_cooldown_keeps_motor_feedback_sparse(
    thirty_day: SimulationReport,
) -> None:
    """马达振动次数应远低于唤醒投递次数：后台提醒不驱动马达。"""
    assert thirty_day.motor_vibrations < thirty_day.wake_dispatched
    # 30 天不到 300 次物理振动
    assert thirty_day.motor_vibrations < 300


# ---------------------------------------------------------------------------
# 180 天长周期
# ---------------------------------------------------------------------------


def test_180_day_run_holds_every_gate(one_eighty_day: SimulationReport) -> None:
    assert one_eighty_day.total_hours == 180 * 24 == 4_320
    assert one_eighty_day.ticks_processed == 4_320 * 60 == 259_200
    assert one_eighty_day.deadlock_count == 0
    assert one_eighty_day.raw_image_bytes_retained == 0
    assert one_eighty_day.peak_rss_megabytes <= 128.0
    assert one_eighty_day.rss_growth_megabytes < 32.0
    assert one_eighty_day.chain_complete is True
    # 180 天 ≈ 6 个月，Token 仍按"月度预算"口径衡量单月强度
    per_month = one_eighty_day.total_tokens_used / 6
    assert per_month <= 2_554_000


def test_180_day_run_scales_linearly_in_ticks(
    thirty_day: SimulationReport, one_eighty_day: SimulationReport
) -> None:
    assert one_eighty_day.ticks_processed == thirty_day.ticks_processed * 6


# ---------------------------------------------------------------------------
# 确定性与可复现
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_reports(tmp_path: Path) -> None:
    first, _ = _run(7, tmp_path / "a", seed=4242)
    second, _ = _run(7, tmp_path / "b", seed=4242)

    comparable = {
        "ticks_processed",
        "meetings_held",
        "total_tokens_used",
        "facts_sealed",
        "noise_episodes",
        "motor_vibrations",
    }
    left = {k: v for k, v in first.model_dump().items() if k in comparable}
    right = {k: v for k, v in second.model_dump().items() if k in comparable}
    assert left == right


def test_config_rejects_naive_start_time() -> None:
    from datetime import datetime

    with pytest.raises(Exception, match="timezone"):
        # 故意构造 naive datetime：本测试要证明它被拒绝
        SimulationConfig(days=1, start_at=datetime(2026, 9, 1))  # noqa: DTZ001


def test_policy_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        RuntimePolicy.load(tmp_path / "nope.json")


def test_run_returns_a_driver_with_a_live_ledger(tmp_path: Path) -> None:
    """推演结束后账本仍可独立校验（持久化是真的落盘了）。"""
    report, driver = _run(2, tmp_path / "ledger_check")
    assert report.integrity_ok is True
    assert driver.ledger.verify_fact_integrity().all_intact is True
    assert driver.ledger.fact_count() == report.facts_sealed
