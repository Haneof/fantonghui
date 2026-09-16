"""SIM-001 无头 30 天成年高熵生活仿真验收。

门 1（时间轴）：720h 决定论高熵——HR/HRV 昼夜节律、工业噪声、
    恰好 120 场工作会议、商务危机 + 老王合同违约，指纹零漂移。
门 2（真实 C 链）：C01 EdgeMultimodalCleaner 清洗帧 → C06 治理闸
    （runtime_policy.json + FactImmutabilityLedger 封印危机事实）→
    C02 CJK 倒排建索引 → C04 共现/打分检索 → C05 对话观察归档。
门 3（性能）：时间严格单调、零死锁（显式 SimulationDeadlockError）、
    常驻对象有界、raw image 残留字节恒 0、千倍速回放整月不过时。
门 4（预算）：月 token ≤ governance/runtime_policy.json 的 2,554,000。
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import pytest

from aios_core.ingest.multimodal_edge import RawByteSink
from aios_core.simulation.headless_life_driver_independent2 import (
    POLICY_PATH,
    SCENE_BREACH_AUDIT,
    SCENE_CRISIS,
    SCENE_MEETING,
    SCENE_NOISE,
    SCENE_VITALS,
    HeadlessLifeDriver,
    RuntimePolicyError,
    SimulationDeadlockError,
    TimelineScene,
    generate_30day_adult_timeline,
)


# ---------------------------------------------------------------------------
# 门 1：时间轴契约
# ---------------------------------------------------------------------------

def test_timeline_is_720h_deterministic_and_high_entropy() -> None:
    t1 = generate_30day_adult_timeline()
    t2 = generate_30day_adult_timeline()
    assert t1 == t2, "同种子时间轴必须逐事件指纹一致（决定论）"
    t3 = generate_30day_adult_timeline(seed=42)
    assert t1 != t3, "不同种子必须产生不同高熵序列"

    assert t1[0].at_hour == 0.0
    assert t1[-1].at_hour <= 720.0
    hours = [s.at_hour for s in t1]
    assert hours == sorted(hours)

    meetings = [s for s in t1 if s.kind == SCENE_MEETING]
    assert len(meetings) == 120, "全月必须恰好 120 场工作会议"

    vitals = [s for s in t1 if s.kind == SCENE_VITALS]
    assert len(vitals) == 180, "30 天 × 6 拍/天 = 180 帧昼夜节律"
    hrs = [s.heart_rate for s in vitals if s.heart_rate]
    assert 50 <= min(hrs) and max(hrs) <= 92, "HR 必须落在成年昼夜节律区间"
    assert statistics.pstdev(hrs) > 2, "HR 序列必须有昼夜波动"

    sdnn = [s.hrv_state.sdnn_ms for s in vitals if s.hrv_state]
    assert statistics.pstdev(sdnn) > 2, "HRV(SDNN) 必须随昼夜摆动"

    noise = [s for s in t1 if s.kind == SCENE_NOISE]
    assert noise and all(70.0 <= (s.noise_db or 0) <= 95.0 for s in noise)

    crisis = [s for s in t1 if s.kind == SCENE_CRISIS]
    breach = [s for s in t1 if s.kind == SCENE_BREACH_AUDIT]
    assert len(crisis) == 1 and len(breach) == 1
    assert "995011" in crisis[0].brief and "老王" in breach[0].brief

    # 帧保留字段一律为清洗端消纳对象，时间轴自身不声明保留
    assert all(s.frames >= 0 for s in t1)


# ---------------------------------------------------------------------------
# 门 2/3/4：真实 C 链 + 零死锁 + 零字节 + 预算
# ---------------------------------------------------------------------------

def _budget() -> int:
    policy = json.loads(Path(POLICY_PATH).read_text(encoding="utf-8"))
    return int(policy["monthly_token_budget"])


def test_full_30day_run_zero_deadlock_zero_bytes_within_budget() -> None:
    driver = HeadlessLifeDriver()
    timeline = generate_30day_adult_timeline()

    started = time.perf_counter()
    stats = driver.ingest(timeline)
    elapsed = time.perf_counter() - started

    assert stats.finalized
    assert stats.scenes_total == len(timeline)
    assert stats.meetings_consumed == 120
    assert stats.vitals_consumed == 180
    assert stats.crisis_sealed == 1

    # 门 4：月预算（governance/runtime_policy.json）
    budget = _budget()
    assert budget == 2_554_000, "预算硬数必须不可漂移"
    assert stats.tokens_used <= budget
    assert stats.tokens_used > 0

    # 门 3：零死锁只在 ingest 中显式断言——本用例能跑完 = 单调推进成立
    assert stats.retained_image_bytes == 0, RawByteSink().retained_byte_count == 0
    assert stats.purged_frames >= 123, "120 会议帧 + 危机 2 帧 + 违约 1 帧必须全部经 sink 消纳"
    assert stats.purged_bytes >= stats.purged_frames * 64

    # 常驻对象有界（30 天全量也绝不让驱动器吃不进）
    assert stats.object_footprint_filtered <= HeadlessLifeDriver.FOOTPRINT_KEEP

    # 正常发布的 30 天级历史查询/共现关系都被建立（非打表统计）
    assert stats.queries_issued > 0
    assert stats.co_occurrences_recorded > 0

    # 千倍速回放约束：720h 压进亚分钟级
    assert elapsed < 60.0, f"30 天仿真超过性能闸: {elapsed:.2f}s"


def test_rejected_rollback_raises_deadlock_error() -> None:
    driver = HeadlessLifeDriver()
    scene_a = TimelineScene(scene_id="S1", at_hour=10.0, kind=SCENE_VITALS, brief="HR=70")
    scene_b = TimelineScene(scene_id="S2", at_hour=9.5, kind=SCENE_VITALS, brief="HR=71")
    with pytest.raises(SimulationDeadlockError):
        driver.ingest([scene_a, scene_b])


def test_unknown_scene_type_fails_loudly() -> None:
    driver = HeadlessLifeDriver()
    bogus = TimelineScene(scene_id="B1", at_hour=0.5, kind="nap_chat", brief="闲聊发呆")
    with pytest.raises(ValueError):
        driver.ingest([bogus])


def test_budget_violation_raises_before_breach(tmp_path: Path) -> None:
    policy_path = tmp_path / "runtime_policy.json"
    policy_path.write_text(json.dumps({"monthly_token_budget": 100}), encoding="utf-8")
    driver = HeadlessLifeDriver(policy_path=policy_path)
    fat = TimelineScene(scene_id="F1", at_hour=0.5, kind=SCENE_VITALS, brief="a" * 2000)
    with pytest.raises(RuntimePolicyError):
        driver.ingest([fat])
    assert driver.stats.tokens_used == 0, "越账场景不得入账 token（预检挂账）"


def test_deterministic_digest_across_runs() -> None:
    t = generate_30day_adult_timeline()
    d1 = HeadlessLifeDriver().ingest(t)
    d2 = HeadlessLifeDriver().ingest(t)
    assert d1.digest == d2.digest
    assert d1.tokens_used == d2.tokens_used
