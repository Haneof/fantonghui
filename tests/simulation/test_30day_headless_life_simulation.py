"""SIM-001 无界面 30 天高熵多维人生仿真器验收测试。

纯 Python、零 UI，1000x 加速回放推进 30 天（720 小时）：昼夜节律 +
高频心率/HRV + 工业车间高噪 + 120 场工作会议 + 突发商业危机 +
老王合同违约 + 夜间心源性晕厥跌倒。

四大硬门禁：
1. 720 小时连续高熵时空流完整发生；
2. 完整驱动 C01 边缘清洗 -> C06 倒排求交 -> C02 账本 -> C04 单看板
   -> C05 回溯注记技术链；
3. 0 死锁、驻留 RSS <= 128MB、原始二进制图片滞留量严格为 0；
4. 全局 Token 总量受控于 governance/runtime_policy.json 的 2,554,000
   月度预算。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from aios_core.simulation.headless_life_driver import (
    TOTAL_HOURS,
    HeadlessLifeDriver,
    SimConfig,
    SimulationReport,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "governance" / "runtime_policy.json"


@pytest.fixture(scope="module")
def sim_run() -> dict:
    """30 天 / 1000x 加速一次性连续推演（确定性种子）。"""

    driver = HeadlessLifeDriver(SimConfig())
    report = driver.run()
    return {"driver": driver, "report": report}


@pytest.fixture(scope="module")
def report(sim_run: dict) -> SimulationReport:
    return sim_run["report"]


# ---------------------------------------------------------------------------
# 硬门禁 1：真实高熵成年人 30 天时空流发生器
# ---------------------------------------------------------------------------


def test_gate1_720_hours_stream_with_120_meetings_and_scripted_crises(
    report: SimulationReport,
) -> None:
    assert TOTAL_HOURS == 720
    assert report.hours_streamed == 720
    assert report.ticks == 30 * 144
    assert report.speed_factor == 1000

    # 120 场真实工作会议 + 四大剧本事件（商业危机/心源性跌倒/老王违约/司法查封）。
    assert report.meetings == 120
    assert report.crisis_events == 4
    assert report.breach_event is True
    assert report.p0_events == 1  # 夜间室性早搏合并跌倒走 P0 硬件直穿


# ---------------------------------------------------------------------------
# 硬门禁 2：完整驱动 AIOS 技术链
# ---------------------------------------------------------------------------


def test_gate2_full_chain_c01_c06_c02_c04_c05_all_engaged(
    sim_run: dict, report: SimulationReport
) -> None:
    driver: HeadlessLifeDriver = sim_run["driver"]

    # C01 边缘清洗：抓拍进管、废片粉碎。
    assert report.c01_frames_ingested >= 30 * 12
    assert report.c01_garbage_purged > 0

    # C06 倒排求交：每日例行检索，违约日之后必须命中老王违约证据链。
    assert report.c06_intersection_queries >= 30
    assert report.c06_hits > 0
    assert driver.c06_index.intersect(("老王", "违约"))

    # C02 不可变账本：30 天事实持久化（体征抽样 + 会议 + 剧本事件）。
    assert report.c02_observations > 1500

    # C04 单看板装配：30 次夜间复盘 + 20 次合同审查会议 + 3 次危机对话窗口。
    assert report.c04_assemblies == 53

    # C05 回溯注记：第 21 天老王欺诈重估（只追加在今天，指针指向过去）。
    assert report.c05_annotations == 1
    (annotation,) = driver.c05_registry.all()
    assert annotation.target_entity_id == "entity:partner:laowang"
    assert annotation.learned_at == annotation.recorded_at


# ---------------------------------------------------------------------------
# 硬门禁 3：0 死锁、内存平稳、原始二进制图片零滞留
# ---------------------------------------------------------------------------


def test_gate3_zero_deadlock_stable_memory_zero_raw_image_retention(
    report: SimulationReport,
) -> None:
    assert report.deadlocks == 0

    # 驻留 RSS <= 128MB 且增长曲线平稳（30 天推演无内存泄漏）。
    assert report.rss_peak_mb <= 128.0
    assert report.rss_growth_mb <= 24.0

    # 原始二进制图片滞留量严格为 0（端侧只留特征摘要，不落原图）。
    assert report.c01_retained_raw_bytes == 0

    # 1000x 加速回放：30 天推演墙钟必须在预算内完成。
    assert report.wall_seconds < 120.0


# ---------------------------------------------------------------------------
# 硬门禁 4：月度 Token 封套核验
# ---------------------------------------------------------------------------


def test_gate4_token_consumption_within_monthly_policy_budget(
    report: SimulationReport,
) -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    budget = policy["monthly_token_budget"]
    assert budget == 2_554_000

    assert report.tokens_consumed > 0
    assert report.tokens_consumed <= budget, (
        f"30 天仿真 Token 总量 {report.tokens_consumed} 超出月度预算 {budget}"
    )
    # 每次看板装配都不得突破单看板 1500 物理硬帽。
    assert report.tokens_consumed <= report.c04_assemblies * 1500
