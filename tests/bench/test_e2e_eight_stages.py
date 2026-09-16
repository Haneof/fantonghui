"""端到端 8 大阶段贯穿盲测（450 天中档对抗世界）。

红线自查：真值全部来自 MassiveLifeBench 生成期封存的 BenchManifest
（与被测管线完全解耦），断言一律"管线输出对照卷宗"，绝无自编自答。

执行隔离：压测在**独立子进程**运行并落盘 JSON 报告，本进程只读报告
断言——海量压测的内存足迹（数百 MB 级）绝不污染同进程其他测试的
RSS 门禁（如 SIM-001 的 128MB 硬预算）。
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
days, density, drill, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
report = run_full_press(PressConfig(days=int(days), density=density, drill_sample=drill))
report.write_json(__import__("pathlib").Path(out))
"""


@pytest.fixture(scope="module")
def mid_press(tmp_path_factory: Any) -> Any:
    out = tmp_path_factory.mktemp("press") / "mid_press.json"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, "450", "mid", "100", str(out)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT, timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(out.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# 吞吐与清洗收敛
# ----------------------------------------------------------------------

def test_stage1_million_scale_cleaning_convergence(mid_press: dict) -> None:
    assert mid_press["total_raw_points"] > 400_000
    assert mid_press["cleaned_records"] * 8 <= mid_press["total_raw_points"]
    s1 = mid_press["stages"][1]
    assert s1["detail"]["impact_recall"] >= 0.95
    assert s1["detail"]["hr_spike_recall"] >= 0.90
    assert s1["detail"]["noise_sms_entered_engine"] == 0
    assert s1["detail"]["voiceprint_consistency"] >= 0.99
    assert s1["detail"]["voiceprint_speakers"] >= 5   # 4 主说话人 + 合伙人


def test_stage1_iron_law4_noise_deleted_evidence_kept(mid_press: dict) -> None:
    s1 = mid_press["stages"][1]["detail"]
    assert s1["noise_raw_purged_pct"] >= 0.99      # 噪声原始字节物理粉碎
    assert s1["evidence_raw_retained_pct"] == 1.0  # 证据 100% 永存
    assert s1["captions_stored"] > 0               # 图片只存 Caption
    assert s1["evicted_180d"] > 0                  # 180 天淘汰机制生效


def test_stage2_pyramid_lossless_drill_through(mid_press: dict) -> None:
    s2 = mid_press["stages"][2]["detail"]
    assert s2["drill_breakage_rate"] == 0.0        # 证据链断裂率 0.0%
    assert s2["levels"]["year"] >= 1 and s2["levels"]["week"] > 50
    assert mid_press["latencies"]["pyramid_drill_through"]["p95_ms"] < 5.0


def test_stage3_resonance_and_lifecycle(mid_press: dict) -> None:
    s3 = mid_press["stages"][3]["detail"]
    assert s3["clusters_synthesized"] >= 1         # 跨模态共振成锚
    assert s3["anchors_registered"] >= 1
    assert s3["stale_dependents"] >= 1             # 下游自动 STALE
    assert s3["recheck_queue"] >= 1                # 复核队列触发


def test_stage4_gates_and_chapters(mid_press: dict) -> None:
    s4 = mid_press["stages"][4]["detail"]
    assert s4["gate1_rejections"] == 2             # 偶发/短期 100% 拒
    assert s4["quota_blocks"] == 1                 # 同日第 2 次反思拒
    assert s4["kinematic_steps"] > 0               # 认知层导数在跑


def test_stage5_history_immutable_single_hop(mid_press: dict) -> None:
    s5 = mid_press["stages"][5]["detail"]
    assert s5["sha256_unchanged"] is True
    assert s5["isolator_llm_calls"] == 0
    assert s5["single_hop_respected"] is True      # 标记数 == 一级下游数
    assert s5["lens_consistent"] is True           # 双透镜一致
    assert s5["dual_lens_build_scans"] == 2        # O(注解) 构建


def test_stage6_advice_with_pinned_evidence(mid_press: dict) -> None:
    s6 = mid_press["stages"][6]["detail"]
    assert s6["advice_issued"] == 3
    assert s6["advice_with_pinned_evidence"] == 3  # 无证据建议=编造，零容忍
    assert s6["goal_revoked_on_denial"] is True    # 用户否认 → 目标立即撤销


def test_stage7_three_defense_lines(mid_press: dict) -> None:
    s7 = mid_press["stages"][7]["detail"]
    assert s7["sycophancy_blocked"] >= 1           # 反谄媚拦截
    assert s7["zero_ui_blocked"] == 1              # 问卷/置信度拦截
    assert "亏损安慰" in s7["taboo_topics"]        # 雷区名单自发建立


def test_stage8_p0_bypass_and_dialogue(mid_press: dict) -> None:
    s8 = mid_press["stages"][8]["detail"]
    assert s8["p0_bypass_max_ms"] <= 50.0          # 铁律3：≤50ms
    assert s8["p0_llm_calls"] == 0                 # 大模型 0 次
    assert s8["p0_pulse_dispatched"] is True
    assert s8["dormant_task_zero_token"] is True   # 双轨休眠零 Token
    assert s8["dialogue_sentence_violations"] == 0 # 1~3 句铁律
    assert s8["manifest_tokens_used"] <= s8["manifest_token_budget"]


def test_five_iron_laws_all_pass(mid_press: dict) -> None:
    for name, verdict in mid_press["iron_laws"].items():
        assert verdict["pass"], f"{name} 未捍卫：{verdict['evidence']}"
