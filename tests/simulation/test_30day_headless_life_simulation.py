"""SIM-001 验收：30 天（+180 天冒烟）无界面高熵人生仿真，四大硬门禁。"""

from __future__ import annotations

import json
import pathlib

import pytest

from aios_core.contracts.enums import ObjectType
from aios_core.simulation.headless_life_driver import (
    POLICY_PATH,
    HeadlessLifeDriver,
    SimConfig,
    load_token_policy,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _rss_kb() -> int:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        return -1
    return -1


@pytest.fixture(scope="module")
def sim_30d(tmp_path_factory):
    db = tmp_path_factory.mktemp("sim30d") / "world.db"
    driver = HeadlessLifeDriver(SimConfig(), db)
    rss_before = _rss_kb()
    report = driver.run()
    rss_after = _rss_kb()
    if rss_before >= 0 and rss_after >= 0:
        report.extra["rss_delta_kb"] = max(0, rss_after - rss_before)
    return driver, report


# ---------------------------------------------------------------------------
# 门禁一：真实高熵 720 小时时空流
# ---------------------------------------------------------------------------


def test_720_hour_stream_shape(sim_30d):
    _driver, report = sim_30d
    assert report.days == 30
    assert report.ticks == 30 * 144  # 10 分钟粒度 × 720 小时
    assert report.samples_generated == report.ticks
    assert report.meetings == 120  # 恰好 120 次真实工作会议
    assert report.crises == 3  # 突发商业危机
    assert report.laowang_facts == 3  # 合伙 / 违约 / 今天才指认
    # 高熵核验：观测值分散度（心率窗口点数远超下限）
    assert report.observations_committed > 300


# ---------------------------------------------------------------------------
# 门禁二：完整技术链 C01→C06→C02→C04→C05 全部驱动
# ---------------------------------------------------------------------------


def test_full_pipeline_counters(sim_30d):
    driver, report = sim_30d
    assert report.raw_binaries_cleaned == 3  # C01 语义化
    assert report.inverted_index_entries > 0  # C06 倒排表
    assert report.inverted_intersect_queries > 0 and report.inverted_intersect_hits > 0
    assert report.world_revision >= 30  # C02 每日账本 flush
    persisted = driver.store.list_payloads(object_type=ObjectType.OBSERVATION)
    assert len(persisted) == report.observations_committed
    # C04 看板：day 0 全部条件任务仍 DORMANT 物理隐形，30 天后大量 READY
    assert report.extra["day_0_board_items"] == 0
    assert report.extra["day_0_dormant"] == 202
    assert report.extra["day_29_board_items"] > 150
    # C05 回溯注记已挂载
    assert report.retrospective_overlays == 1


def test_c05_retrospective_view_semantics(sim_30d):
    driver, _report = sim_30d
    assert driver.cfg.laowang_learning_day == 18
    # 双时间透镜口径在仿真数据上重演（与 M1-018 验收同构）：
    # as_of_cutoff=day10 → 18 号才学到的"骗子"认知一个字符都不许出现
    past_view = driver.query_laowang_slice(day=2, as_of_day=10)
    assert past_view["overlays"] == []
    assert past_view["overlay_suppressed_by_cutoff"] == 1
    assert [f["object_id"] for f in past_view["facts"]]  # 两年前合伙原始记录在场
    rendered = json.dumps(past_view, ensure_ascii=False)
    for forbidden in ("骗子", "欺诈", "rta_sim_laowang_fraud"):
        assert forbidden not in rendered
    # 当前视图：动态渲染警示标记，底层历史切片分毫未动
    current = driver.query_laowang_slice(day=2)
    assert len(current["overlays"]) == 1
    assert current["facts"] == past_view["facts"]


# ---------------------------------------------------------------------------
# 门禁三：0 死锁 + 内存平稳 + 原始二进制滞留 0
# ---------------------------------------------------------------------------


def test_zero_deadlock_memory_and_binary_residency(sim_30d):
    _driver, report = sim_30d
    assert report.deadlock_cycles == 0  # 30 天推进零停滞
    assert report.retained_records == 0  # 每日 flush 后驻留 buffer 清空
    assert report.raw_binary_retained_bytes == 0  # 原始大图滞留恒 0
    if "rss_delta_kb" in report.extra:
        assert report.extra["rss_delta_kb"] <= 128 * 1024  # 驻留增量 ≤128MB


# ---------------------------------------------------------------------------
# 门禁四：月度 Token 封套
# ---------------------------------------------------------------------------


def test_monthly_token_envelope(sim_30d):
    _driver, report = sim_30d
    policy = load_token_policy(POLICY_PATH)
    assert POLICY_PATH.exists()
    assert policy["monthly_token_budget"] == 2_554_000
    assert 0 < report.prompt_tokens_total <= report.token_budget
    # DORMANT 任务 0 Token / 机械快轨 0 LLM（与 M2-005R 门禁联动复述）
    assert report.dormant_prompt_tokens == 0
    assert report.dormant_board_leaks == 0
    assert report.level1_llm_calls == 0
    assert report.level1_evaluations > 0


def test_policy_file_content():
    raw = json.loads((REPO_ROOT / "governance" / "runtime_policy.json").read_text(encoding="utf-8"))
    assert raw["monthly_token_budget"] == 2_554_000
    assert raw["hard_rules"]["dormant_task_prompt_tokens_max"] == 0


# ---------------------------------------------------------------------------
# 180 天长跑冒烟（粗粒度）：仍 0 死锁、账本与封套受控
# ---------------------------------------------------------------------------


def test_180day_smoke_zero_deadlock(tmp_path):
    cfg = SimConfig(days=180, minutes_step=60, bulk_conditional_tasks=50, meetings_per_day=1)
    driver = HeadlessLifeDriver(cfg, tmp_path / "world180.db")
    report = driver.run()
    assert report.ticks == 180 * 24
    assert report.deadlock_cycles == 0
    assert report.meetings == 180
    assert report.raw_binary_retained_bytes == 0
    assert report.retained_records == 0
    assert 0 < report.prompt_tokens_total <= report.token_budget
    assert report.world_revision >= 180
