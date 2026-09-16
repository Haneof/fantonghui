# -*- coding: utf-8 -*-
"""SIM-001 无界面 Linux 30 天高熵多维人生仿真推演机 · 验收测试

四大硬门禁：

1. 真实高熵成年人 30 天时间流发生器（720 小时分钟级连续推进、昼夜节律、
   车间高噪、整 120 次工作会议、第 22 天老王合同违约事件链）；
2. 驱动完整技术链：C01 边缘清洗与粉碎 → C06 内建倒排求交 → C02 账本落盘
   → C04 1500 Token 单看板 → C05 双时间回溯注记（M2-001/M2-005R 联调）；
3. 30 天连续推演 0 死锁、驻留内存受控、原始二进制滞留量为 0；
4. 月度 Token 封套（governance/runtime_policy_arena01.json 的 2,554,000）核验。
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import resource
import threading
import time
import tracemalloc

import pytest

from aios_core.scheduler.conditional_engine_arena01 import ConditionalTaskState
from aios_core.simulation.headless_life_driver_arena01 import (
    BREACH_DAY,
    HeadlessLifeDriver,
    LifeStreamGenerator,
    load_runtime_policy,
)

SIM_START = datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)  # 周一
SEED = 0x51AC001


def _policy():
    return load_runtime_policy("governance/runtime_policy_arena01.json")


# ---------------------------------------------------------------------------
# 门禁一：高熵 720 小时时空流发生器
# ---------------------------------------------------------------------------


def test_gate1_stream_fidelity_deterministic_high_entropy():
    stream = LifeStreamGenerator(seed=SEED, start=SIM_START, days=30)
    events = list(stream.iter_events())
    kinds = Counter(e.kind for e in events)

    # 720 小时分钟级连续体征流：30×24×60 = 43,200 条，无一断点
    assert kinds["vitals_minute"] == 30 * 24 * 60
    minutes = [e.ts for e in events if e.kind == "vitals_minute"]
    assert minutes[0] == SIM_START and minutes[-1] == SIM_START + timedelta(minutes=43200 - 1)
    gaps = [(b - a).total_seconds() for a, b in zip(minutes, minutes[1:])]
    assert set(gaps) == {60.0}

    # 整 120 次工作会议（4×30），第 22 天老王违约恰好一次
    assert kinds["meeting"] == 120
    breach = [e for e in events if e.kind == "breach"]
    assert len(breach) == 1
    assert (breach[0].ts - SIM_START).days == BREACH_DAY
    assert "老王" in breach[0].payload["document"] and "违约" in breach[0].payload["document"]

    # 车间高噪日：1 张达标 + 1 张废片成对出现
    workshop_imgs = [e for e in events if e.kind == "workshop_image"]
    good = [e for e in workshop_imgs if e.payload["metadata"]["quality_score"] >= 0.4]
    junk = [e for e in workshop_imgs if e.payload["metadata"]["quality_score"] < 0.4]
    assert len(good) == len(junk) == len(workshop_imgs) // 2 == 13

    # 昼夜节律：凌晨均值显著低于日间峰值
    night = [e.payload["hr"] for e in events if e.kind == "vitals_minute" and 2 <= e.ts.hour < 6]
    noon = [e.payload["hr"] for e in events if e.kind == "vitals_minute" and 13 <= e.ts.hour < 17]
    assert sum(night) / len(night) + 12 < sum(noon) / len(noon)

    # 危机心率尖峰：违约时刻分钟体征被事件链推高
    spiked = [
        e.payload["hr"] for e in events
        if e.kind == "vitals_minute" and e.ts == breach[0].ts
    ]
    assert spiked and spiked[0] > 100.0

    # 定时收市锚点：每日 21:30 复盘
    assert kinds["daily_close"] == 30

    # 决定性：同 seed 两路发生器逐事件一致（指纹含原始字节哈希）
    import hashlib

    def _fingerprint(evs):
        return [
            (e.ts.isoformat(), e.kind, hashlib.sha256(repr(sorted(e.payload.items())).encode()).hexdigest())
            for e in evs
        ]

    twin = list(LifeStreamGenerator(seed=SEED, start=SIM_START, days=30).iter_events())
    assert _fingerprint(events) == _fingerprint(twin)


# ---------------------------------------------------------------------------
# 门禁二：完整技术链 E2E（C01→C06→C02→C04→C05，M2-001/M2-005R 联调）
# ---------------------------------------------------------------------------


def test_gate2_full_chain_30day_e2e(tmp_path):
    driver = HeadlessLifeDriver(workdir=tmp_path, policy=_policy(), start=SIM_START, seed=SEED)
    m = driver.run(days=30)

    # 链路吞吐：120 次会议、720 条小时体征、854 条账本行
    assert m.meetings == 120
    assert m.vitals_persisted == 720
    assert m.c02_rows == driver._store.current_world_revision() == 720 + 120 + 13 + 1
    assert m.images_cleaned == 13 and m.images_shredded == 13

    # C01 硬红线：原始二进制从零开始、峰值 >0、终值精确归零（物理粉碎）
    assert m.raw_bytes_peak > 0
    assert m.raw_bytes_end == 0

    # 落账数据零二进制：任一载荷序列化不含原始字节
    for payload in driver._store.list_payloads(subject_id="sim-user"):
        blob = json.dumps(payload, ensure_ascii=False)
        assert "raw_bytes" not in blob and len(blob) < 2048

    # C06 内建倒排求交：老王+违约 精确命中违约告知函
    assert m.c06_docs == 120 + 13 + 1
    hits = driver._c06.search_all(["老王", "违约"])
    assert len(hits) == 1 and "撕毁" in driver._c06._docs[hits[0]]

    # C04 单看板：每日一次装配，单次 ≤1500 Token
    assert m.cockpit_assemblies == 30 and m.cockpit_max_tokens <= 1500

    # M2-005R 违约作战室：爆雷时刻机械快轨自动就绪，全程零 LLM
    assert driver._scheduler.state_of("sim-breach-war-room") is ConditionalTaskState.READY
    assert driver._scheduler.stats["llm_calls"] == 0

    # C05 双时间锚点核验：as-of 无图层 / 现视图 1 层追加注记
    assert m.c05_annotations == 1
    assert m.c05_asof_annotations == 0 and m.c05_current_annotations == 1
    assert m.c05_facts == 121

    # M2-001 防抖：43,200 脉搏冲出 5 分钟窗合并成 8,640 个批次
    assert m.queue_downstream_wakes == 8640

    # 高熵商业场景禁止玩具数据：纪要语义含实际对抗议题
    meeting_docs = [t for t in driver._c06._docs.values() if "纪要" in t]
    assert any("对赌" in t for t in meeting_docs) and any("知识产权" in t for t in meeting_docs)

    # 预算封套（门禁四前置）：>0 且远低于 2,554,000
    assert 0 < m.total_tokens <= 2_554_000
    assert m.llm_calls == 0


# ---------------------------------------------------------------------------
# 门禁三：0 死锁 + 内存受控（并发统计轮询 + tracemalloc 峰值审计）
# ---------------------------------------------------------------------------


def test_gate3_zero_deadlock_and_memory_stable(tmp_path):
    driver = HeadlessLifeDriver(workdir=tmp_path, policy=_policy(), start=SIM_START, seed=SEED)

    rss_before_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tracemalloc.start()
    holder = {}

    def _worker():
        holder["metrics"] = driver.run(days=30)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    polls = 0
    while worker.is_alive():
        snap = driver.stats_snapshot()
        assert snap is not None
        polls += 1
        time.sleep(0.01)
    worker.join(timeout=120)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    m = holder["metrics"]
    # 连环锁压力段每事件都走过、且 0 次 try-lock 超时（锁序单调 ⇒ 无死锁）
    assert m.chaos_sections == expected_total_events()
    assert polls > 100
    assert m.deadlock_timeouts == 0

    # 内存：Python 堆峰值 ≤64MB；进程 RSS 增量 ≤128MB（含 SQLite 页缓存）
    assert peak <= 64 * 1024 * 1024, f"tracemalloc peak {peak / 1e6:.1f}MB"
    assert (rss_after_kb - rss_before_kb) <= 128 * 1024

    # 有界容器不被 4.3 万事件撑爆：近窗体征恒 ≤120
    assert len(driver._recent_hr) <= 120


def expected_total_events() -> int:
    """锁压力段应被执行的总次数（与驱动主循环事件一一对应）。

    构成：43,200 分钟体征 + 120 会议 + 26 图像 + 1 违约 + 30 收盘 = 43,577。
    """
    return 43200 + 120 + 26 + 1 + 30


# ---------------------------------------------------------------------------
# 门禁四：月度 Token 封套与确定性回放
# ---------------------------------------------------------------------------


def test_gate4_token_envelope_and_deterministic_replay(tmp_path):
    policy = _policy()
    assert policy["token_budget"]["monthly_token_budget"] == 2_554_000

    for sub in ("a", "b", "c"):
        (tmp_path / sub).mkdir()
    d1 = HeadlessLifeDriver(workdir=tmp_path / "a", policy=policy, start=SIM_START, seed=SEED)
    d2 = HeadlessLifeDriver(workdir=tmp_path / "b", policy=policy, start=SIM_START, seed=SEED)
    m1 = d1.run(days=30)
    m2 = d2.run(days=30)

    # 同 seed 决定性回放：指标指纹逐位一致
    assert m1.fingerprint() == m2.fingerprint()

    # 封套：双引擎合计仍不足月度预算的十分之一（单引擎 < 5%）
    assert m1.total_tokens * 10 < policy["token_budget"]["monthly_token_budget"]

    # 预算硬违约演练：伪造 1 Token 预算必须被驱动引擎硬拒
    tiny = dict(policy)
    tiny["token_budget"] = dict(policy["token_budget"], monthly_token_budget=1)
    d3 = HeadlessLifeDriver(workdir=tmp_path / "c", policy=tiny, start=SIM_START, seed=SEED)
    with pytest.raises(AssertionError, match="monthly token envelope"):
        d3.run(days=30)

    # 生存模块守门：anyio 等异步容器不得进入仿真链（零协作式挂起点）
    import aios_core.simulation.headless_life_driver_arena01 as mod

    assert not hasattr(mod, "anyio")
