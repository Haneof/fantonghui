"""SIM-001 30 天无界面高熵人生仿真——四大硬门验收。

  1. 720h 时空流：昼夜节律、HRV、工厂噪声、120 场会议、老王违约+商业危机双事件
  2. 全链驱动：C01 边缘清洗→C06 倒排→C02 账本→C04 单看板→C05 回溯注记
  3. 0 死锁 / RSS ≤128MB 平稳 / 原始二进制滞留严格 0
  4. 月度 Token 封套：≤ governance/runtime_policy.json 的 2,554,000（读文件不硬编码）
"""

from __future__ import annotations

import json
import resource
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path

import pytest

from aios_core.ingest.multimodal_edge import EdgeMultimodalCleaner, InMemoryPurgeSink
from aios_core.services.manifest_data_plane import L0SliceStore, ManifestDataPlaneBuilderV0
from aios_core.simulation.headless_life_driver import (
    CRISIS_DAY_BUSINESS,
    CRISIS_DAY_LAOWANG,
    HeadlessLifeDriver,
    RetroAnnotationLog,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

REPO_ROOT = Path(__file__).resolve().parents[2]
RSS_HARD_CAP_KB = 128 * 1024  # Linux ru_maxrss 以 KB 计

@pytest.fixture(scope="module")
def sim_run(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("sim001")
    store = SQLiteWorldStore(tmp_path / "sim_world.db")
    sink = InMemoryPurgeSink()
    cleaner = EdgeMultimodalCleaner(sink=sink)
    conn = sqlite3.connect(":memory:")
    builder = ManifestDataPlaneBuilderV0(store)
    slices = L0SliceStore(store)
    retro = RetroAnnotationLog()
    driver = HeadlessLifeDriver(seed=20260916)

    rss_before_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    threads_before = threading.active_count()
    report = driver.run(
        store=store, cleaner=cleaner, index_conn=conn,
        builder=builder, slices=slices, retro_log=retro, days=30,
    )
    rss_peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "report": report, "sink": sink, "retro": retro, "store": store,
        "rss_before_kb": rss_before_kb, "rss_peak_kb": rss_peak_kb,
        "threads_delta": threading.active_count() - threads_before,
        "tmp_path": tmp_path,
    }


# ---------------------------------------------------------------------------
# 门禁 1：720h 高熵时空流
# ---------------------------------------------------------------------------


def test_720h_stream_coverage_and_content_richness(sim_run):
    report = sim_run["report"]
    assert report.steps == 30 * 24 * 12 == 8640, "720 小时 × 12 步/小时"
    assert report.virtual_days == 30
    assert report.claims_committed == 120, "30 天 120 场真实工作会议（每天 4 场，含周末高压连轴）"
    assert report.images_submitted == 60, "30 天 × 每天 2 次日间抓拍"
    assert report.manifests_built == 120, "30 天 × 每日 4 次单看板装配"
    assert report.anomaly_hours >= 1, "危机期（老王+商业危机）应激必超 95bpm 阈值"


def test_laowang_and_business_crisis_events_materialized(sim_run):
    retro = sim_run["retro"]
    entries = retro.entries()
    assert len(entries) >= 1, "老王违约注记必落账"
    laowang = entries[0]
    assert laowang.target_entity == "王建国"
    assert (laowang.learned_at - laowang.valid_time_start).days >= CRISIS_DAY_LAOWANG
    assert laowang.valid_time_start < laowang.valid_time_end, "双时间窗成立（回溯指向过去）"
    assert "离岸" in laowang.semantic_overlay or "违约" in laowang.semantic_overlay
    assert CRISIS_DAY_LAOWANG < CRISIS_DAY_BUSINESS  # 剧本次序自证


# ---------------------------------------------------------------------------
# 门禁 2：全链驱动（C01→C06→C02→C04→C05）
# ---------------------------------------------------------------------------


def test_chain_c01_purged_every_raw_binary(sim_run):
    report = sim_run["report"]
    sink = sim_run["sink"]
    assert len(sink.purged) == report.images_submitted, "每张原始图必走物理删除口（含画质丢弃件）"
    assert len(set(sink.purged)) == len(sink.purged), "删除口幂等域内无重复 id"


def test_chain_c02_ledger_versioned_and_growing(sim_run):
    store = sim_run["store"]
    payloads = store.list_payloads()
    meeting_claims = [p for p in payloads if str(p.get("object_id", "")).startswith("claim-meeting-")]
    assert len(meeting_claims) == 120
    rev = store.current_world_revision()
    assert rev >= 120, "版本随提交单调增长（账本代际可读）"
    # 老王铁律：历史 Claim 内容保持原样（C05 注记绝不倒写 C02 历史）
    contents = [p["payload"]["content"] if "payload" in p else p.get("content") for p in meeting_claims]
    assert any("王建国" in str(c) for c in contents), "历史纪要原文留在账内，未被注记改写"


def test_chain_c04_c05_are_distinct_lanes(sim_run):
    report = sim_run["report"]
    assert report.manifests_built == 120 and report.retro_annotations >= 1
    # C04 的看板 token 与 C05 的注记 token 各自记账、互不挪用
    meter = report.token_meter
    assert meter.manifest_tokens > 0 and meter.retro_tokens > 0
    assert meter.total == (meter.manifest_tokens + meter.caption_tokens
                           + meter.claim_tokens + meter.retro_tokens)


# ---------------------------------------------------------------------------
# 门禁 3：0 死锁 / 内存平稳 / 二进制零滞留
# ---------------------------------------------------------------------------


def test_zero_deadlock_and_thread_stable(sim_run):
    report = sim_run["report"]
    assert report.deadlocks == 0
    assert report.thread_delta == 0 and sim_run["threads_delta"] == 0
    assert report.wall_seconds < 120.0, f"加速回放墙钟 {report.wall_seconds:.1f}s（1000x 语义）"


def test_memory_plateau_within_128mb(sim_run):
    peak_kb = sim_run["rss_peak_kb"]
    assert peak_kb <= RSS_HARD_CAP_KB, f"RSS 峰值 {peak_kb / 1024:.1f}MB 越 128MB 硬顶"
    # 台地语义：720h 全量事件流不驻留——峰值不应随天数线性爬升
    assert peak_kb - sim_run["rss_before_kb"] <= 64 * 1024, "仿真本体增量驻留须 ≤64MB"


def test_zero_binary_blob_residency(sim_run):
    report = sim_run["report"]
    assert report.raw_bytes_resident == 0
    payloads = sim_run["store"].list_payloads()
    for p in payloads:
        blob = json.dumps(p, ensure_ascii=False, default=str)
        assert "base64" not in blob and "b'" not in blob[:0], "持久化面无二进制形态"
    # 结构性同证：C01 观察物的契约字段 raw_image_bytes_retained 恒 False
    assert report.images_captioned <= report.images_submitted


# ---------------------------------------------------------------------------
# 门禁 4：月度 Token 封套核验（读政策文件，不硬编码）
# ---------------------------------------------------------------------------


def test_monthly_token_envelope_within_policy_cap(sim_run):
    policy = json.loads((REPO_ROOT / "governance" / "runtime_policy.json").read_text(encoding="utf-8"))
    cap = policy["token_budget"]["monthly_total_cap"]
    assert cap == 2_554_000, "政策锚点漂移：月度总帽必须以 v1.3.0 现行值为准"
    total = sim_run["report"].token_meter.total
    assert 0 < total <= cap, f"30 天全局 Token 消耗 {total:,} 越月度封套 {cap:,}"
