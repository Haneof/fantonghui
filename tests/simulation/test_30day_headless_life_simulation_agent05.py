"""SIM-001 无界面 Linux 30天/180天高熵多维人生仿真器 —— 四大硬门禁验收。
独立命名并存线（agent-05）：本文件为 agent-05 共存线交付版本的独立验收测试，与规范实现的验收测试并存，零覆盖、互不依赖。

纯 Python、零 UI、无图形依赖。业务情境（严禁低幼化）：长期高压创业企业法务总监
的 30 天高熵人生（85dB 车间 / 120 次工作会议 / 老王合同违约商业危机 / 对赌回购 /
司法裁定反转 / 跨国供应链圆桌 / 心梗跌倒 P0）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios_core.simulation.headless_life_driver_agent05 import (
    HeadlessLifeDriver,
    HighEntropyLifeStream,
    run_headless_simulation,
)

REPO = Path(__file__).resolve().parents[2]
POLICY = REPO / "governance" / "runtime_policy.json"


@pytest.fixture(scope="module")
def report30():
    """30 天全量仿真报告（模块内共享一次跑批，确定性保证可复用）。"""
    return run_headless_simulation(days=30)


@pytest.fixture(scope="module")
def ticks30():
    return list(HighEntropyLifeStream(days=30))


# ----------------------------------------------------------------------
# 门禁 1：真实高熵成年人 30 天时空流发生器（720 小时连续时间流）
# ----------------------------------------------------------------------


class TestHighEntropyLifeStream:
    def test_720_hours_continuous_with_circadian_rhythm(self, ticks30):
        ticks = ticks30
        assert len(ticks) == 720
        # 昼夜节律：每个 24 小时块内深睡恰 4 小时（02~06）、浅睡恰 4 小时（00,01,06,23）
        for day in range(30):
            block = ticks[day * 24 : day * 24 + 24]
            deep = [t for t in block if t.phase == "deep_sleep"]
            sleep = [t for t in block if t.phase == "sleep"]
            awake = [t for t in block if t.phase == "awake"]
            assert len(deep) == 4 and {t.hour for t in deep} == {2, 3, 4, 5}
            assert len(sleep) == 4 and {t.hour for t in sleep} == {0, 1, 6, 23}
            assert len(awake) == 16
            # 时间流严格连续（逐小时推进）
            for a, b in zip(block, block[1:]):
                assert (b.at - a.at).total_seconds() == 3600

    def test_120_real_work_meetings(self, ticks30):
        meetings = [t for t in ticks30 if t.environment == "meeting"]
        assert len(meetings) == 120  # 20 个工作日 × 6 场

    def test_workshop_high_noise_and_crisis_present(self, ticks30):
        # 85dB 车间高噪环境出现
        assert any(t.environment == "workshop" for t in ticks30)
        # 突发商业危机：连续 3 晚 21:00 心率 > 95（老王违约压力）
        crisis_nights = [t for t in ticks30 if t.day in (11, 12, 13) and t.hour == 21]
        assert len(crisis_nights) == 3
        assert all(t.heart_rate_bpm > 95 for t in crisis_nights)
        # 羽毛球高频心率波动（运动高熵）
        assert any(t.environment == "badminton" and t.heart_rate_bpm > 110 for t in ticks30)
        # P0 时刻唯一（03:15 心梗跌倒）
        assert sum(1 for t in ticks30 if t.is_p0_moment) == 1

    def test_stream_is_deterministic(self, ticks30):
        b = list(HighEntropyLifeStream(days=30))
        assert [t.heart_rate_bpm for t in ticks30] == [t.heart_rate_bpm for t in b]
        assert [t.environment for t in ticks30] == [t.environment for t in b]


# ----------------------------------------------------------------------
# 门禁 2：驱动 AIOS 完整技术链（C01→C06→C02→C04→C05 + M2/M3 主线）
# ----------------------------------------------------------------------


class TestFullTechChain:
    def test_30day_run_drives_all_stages(self, report30):
        r = report30
        # C01 边缘清洗：图片全量粉碎（滞留 0）、声纹 24 人 72 切片
        assert r.images_sunk == r.images_purged
        assert r.images_kept > 0
        assert r.voiceprint_speakers == 24
        assert r.voiceprint_slices_assigned == 72
        # C06 倒排求交：123 文档（120 会议 + 违约 + 股权 + 裁定），多词求交命中
        assert r.documents_indexed == 123
        assert r.query_hits_buyback >= 100
        assert r.query_hits_breach >= 50
        # C02 账本持久化：154 事实（120 会议 + 30 日汇总 + 违约/股权/裁定/P0 4 条危机事件）
        assert r.facts_recorded == 154
        assert r.ledger_integrity_ok is True
        # C04 单看板装配：24 次危机/事件对话，逐次 ≤1500 Token
        assert r.cockpit_assemblies == 24
        assert 0 < r.cockpit_max_tokens <= 1500
        # C05 回溯注记：零提前泄露 + 当前可见 + 单跳级联恰 4 个一级节点
        assert r.annotation_id == "ann:sim:ruling-reversal"
        assert r.zero_early_leak_ok is True
        assert r.overlay_visible_now_ok is True
        assert r.cascade_marked_stale == 4
        assert r.cascade_deeper_untouched_ok is True

    def test_m2_m3_mainlines(self, report30):
        r = report30
        # M2-005R：Level-1/Level-2 成熟，心内科/股权/对赌三旗舰任务闭环
        assert r.tasks_matured_level1 >= 3
        assert r.tasks_matured_level2 == 1
        assert r.cardiology_task_state == "completed"
        assert r.equity_task_state == "completed"
        assert r.buyback_task_state == "completed"
        # M2-001：P0 硬件直穿 1 次、深睡静默挂起 120 条、晨间无损解冻 120 条
        assert r.p0_hardware_pulses == 1
        assert r.silent_suspended == 120
        assert r.thawed_total == 120
        # M3-001R：1 维晋升 ACTIVE、1 维 EXPIRED、1 次递归熔断
        assert r.dimension_active == 1
        assert r.dimension_expired == 1
        assert r.dimension_archived == 0
        assert r.reflection_cuts == 1


# ----------------------------------------------------------------------
# 门禁 3：30 天连续推演 0 死锁与内存平稳
# ----------------------------------------------------------------------


class TestNoDeadlockAndMemoryStable:
    def test_zero_deadlock_and_memory_envelope(self, report30):
        r = report30
        assert r.deadlock_count == 0  # 进程死锁次数严格为 0
        assert r.peak_rss_mb <= 128.0  # 驻留 RSS ≤ 128MB
        # 内存增长曲线平稳（首尾差 ≤ 20MB，无泄漏）
        assert r.vmrss_last_mb - r.vmrss_first_mb <= 20.0
        # 原始二进制图片滞留量严格为 0
        assert r.raw_binary_retained_bytes == 0


# ----------------------------------------------------------------------
# 门禁 4：月度 Token 封套核验
# ----------------------------------------------------------------------


class TestMonthlyTokenEnvelope:
    def test_token_total_within_runtime_policy_budget(self, report30):
        with open(POLICY, "r", encoding="utf-8") as fh:
            budget = int(json.load(fh)["monthly_token_budget"])
        assert budget == 2_554_000  # 工单口径
        r = report30
        assert r.token_envelope_budget == budget
        assert r.token_envelope_total <= budget  # 严格受控于月度总预算
        assert r.token_envelope_total > 0


# ----------------------------------------------------------------------
# 长时程（180 天）冒烟 + 确定性双跑
# ----------------------------------------------------------------------


class TestLongHorizonAndDeterminism:
    def test_180day_smoke_stays_stable(self):
        report = run_headless_simulation(days=180)
        assert report.hours_processed == 4320
        assert report.deadlock_count == 0
        assert report.peak_rss_mb <= 128.0
        assert report.raw_binary_retained_bytes == 0
        assert report.token_envelope_total <= report.token_envelope_budget
        # 事件性阶段在 180 天窗口内各发生一次（不重复触发）
        assert report.p0_hardware_pulses == 1
        assert report.annotation_id == "ann:sim:ruling-reversal"

    def test_double_run_is_bit_deterministic(self, report30):
        r2 = run_headless_simulation(days=30)
        assert report30.ledger_fingerprint == r2.ledger_fingerprint
        assert report30.cockpit_tokens_total == r2.cockpit_tokens_total
        assert report30.facts_recorded == r2.facts_recorded
        assert report30.token_envelope_total == r2.token_envelope_total
        assert r2.peak_rss_mb <= 128.0


class TestDriverContract:
    def test_invalid_days_rejected(self):
        with pytest.raises(ValueError, match="days"):
            HighEntropyLifeStream(days=0)
        with pytest.raises(ValueError, match="days"):
            HeadlessLifeDriver(days=0)
