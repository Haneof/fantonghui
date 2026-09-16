"""百万级原始样本全流程极限压测（512 万点 / 5 切片 / 3 年全马）。

军令口径的"海量"验收：上百万条原始采样独立贯穿 8 大阶段，五大铁律
100% 捍卫 + P50/P95/P99 + 内存峰值全采集。压测在**独立子进程**执行
（内存足迹不污染同进程其他测试的 RSS 门禁），报告 JSON 落盘后回读断言。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_CHILD = """
import sys
from aios_core.bench.press_harness import PressConfig, run_full_press
report = run_full_press(PressConfig(days=int(sys.argv[1]), density="full", drill_sample=200))
report.write_json(__import__("pathlib").Path(sys.argv[2]))
"""


@pytest.fixture(scope="module")
def full_press(tmp_path_factory: Any) -> Any:
    out = tmp_path_factory.mktemp("full_press") / "full_press_report.json"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, "1096", str(out)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT, timeout=900,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(out.read_text(encoding="utf-8"))


def test_million_point_world_generated(full_press: dict) -> None:
    # 上百万级：512 万原始采样点（IMU 波形点/心率槽/语音碎片/图片帧/短信）
    assert full_press["total_raw_points"] > 1_000_000
    assert full_press["cleaned_records"] > 100_000
    # 清洗收敛一个数量级（边缘提纯的意义）
    assert full_press["cleaned_records"] * 8 <= full_press["total_raw_points"]
    s0 = full_press["stages"][0]
    assert s0["detail"]["impacts_manifest"] >= 10      # 对抗真值：摔倒/冲击剧本
    assert s0["detail"]["hr_spikes_manifest"] >= 10    # 心律失常剧本


def test_full_press_wall_time_envelope(full_press: dict) -> None:
    # 512 万点全流程端到端 ≤ 120s（工程红线：海量≠失控）
    assert full_press["wall_total_ms"] <= 120_000


def test_all_eight_stages_executed(full_press: dict) -> None:
    names = [s["name"] for s in full_press["stages"]]
    assert len(names) == 9   # 阶段0 生成 + 阶段1~8
    for n in names:
        assert n.startswith("阶段")


def test_full_scale_five_iron_laws_100_percent(full_press: dict) -> None:
    assert len(full_press["iron_laws"]) == 5
    for name, verdict in full_press["iron_laws"].items():
        assert verdict["pass"], f"全马铁律失守 {name}: {verdict['evidence']}"
    law2 = full_press["iron_laws"]["铁律2_历史绝不篡改"]
    assert "SHA-256 前后一致" in str(law2["evidence"])
    assert full_press["latencies"]["p0_bypass"]["p99_ms"] <= 50.0
    assert full_press["latencies"]["p0_bypass"]["max_ms"] <= 50.0


def test_full_scale_quality_metrics(full_press: dict) -> None:
    s1 = full_press["stages"][1]["detail"]
    assert s1["compression_ratio"] >= 10.0
    assert s1["impact_recall"] >= 0.95
    assert s1["voiceprint_consistency"] >= 0.99
    s2 = full_press["stages"][2]["detail"]
    assert s2["drill_breakage_rate"] == 0.0
    assert s2["sampled_drills"] == 200
    s5 = full_press["stages"][5]["detail"]
    assert s5["summary_nodes"] == 500              # 10 年 500 总结节点
    assert s5["history_observations"] == 200


def test_memory_and_report_artifact(full_press: dict) -> None:
    assert full_press["rss_peak_mb"] > 0           # 内存峰值如实采集
    data = full_press
    assert set(data["iron_laws"]) == {
        "铁律1_输出质量绝对第一", "铁律2_历史绝不篡改", "铁律3_紧急触发硬旁路",
        "铁律4_大模型自主删除", "铁律5_新维度严苛门槛",
    }
    lat = data["latencies"]
    assert lat["p0_bypass"]["p95_ms"] <= 50.0
    assert lat["pyramid_drill_through"]["p99_ms"] < 5.0
