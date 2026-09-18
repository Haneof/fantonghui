"""AIOS 3.0 全流程海量盲测一键运行器（可复现的取证 + 诊断产物）。

做三件事，且只做三件事：

1. 用独立发生器 ``MassiveSyntheticLifeBench`` 造出百万级真实人生切片；
2. 让八阶段全部跑在**真实存储 + 真实引擎**上（零 mock、零自编自答）；
3. 挂上 ``StorageIOProfiler`` 外部仪器，把结果折算成
   「Token 账单 / I/O 归因 / 抽象失真 / 五条铁律判据 / 缺陷清单」，
   落盘为 JSON（机器可复核）+ Markdown（人可读）。

用法::

    PYTHONPATH=src python scripts/run_blind_bench.py --scale 1.0 \\
        --out reports/blind_bench

产物：

* ``<out>/bench_run.json`` —— 全量实测证据（含每条 SQL 归因与铁律逐项判据）；
* ``<out>/bench_summary.md`` —— 一页速览（供 PR 描述与验收引用）。

本脚本**不写任何断言**：验收判据在 ``tests/e2e_blind/``，这里只负责取证与排版。
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from aios_core.simulation.blind_bench_diagnostics import (
    IOAttribution,
    StorageIOProfiler,
    bottleneck_diagnosis,
    iron_rule_assertions,
    render_bottleneck_summary,
)
from aios_core.simulation.blind_bench_harness import BlindBenchHarness, raw_stream_totals

UTC = timezone.utc


def _io_attribution_payload(attribution: IOAttribution) -> dict[str, Any]:
    return {
        "per_stage": {
            stage: [
                {
                    "sql": hotspot.signature,
                    "statements": hotspot.statements,
                    "rows_scanned": hotspot.rows_scanned,
                    "total_ms": hotspot.total_ms,
                }
                for hotspot in hotspots
            ]
            for stage, hotspots in attribution.per_stage.items()
        },
        "overall": [
            {
                "sql": hotspot.signature,
                "statements": hotspot.statements,
                "rows_scanned": hotspot.rows_scanned,
                "total_ms": hotspot.total_ms,
            }
            for hotspot in attribution.overall
        ],
        "unassigned_statements": attribution.unassigned_statements,
    }


def _diagnosis_payload(diagnosis: Mapping[str, Any]) -> dict[str, Any]:
    hotspot = diagnosis["token_hotspot"]
    io_hotspot = diagnosis["io_hotspot"]
    return {
        "token_ledger": [
            {"stage_id": row.stage_id, "tokens": row.tokens, "sources": dict(row.sources)}
            for row in diagnosis["token_ledger"]
        ],
        "token_total": diagnosis["token_total"],
        "token_hotspot": {"stage_id": hotspot.stage_id, "tokens": hotspot.tokens},
        "io_hotspot": None
        if io_hotspot is None
        else {
            "signature": io_hotspot.signature,
            "statements": io_hotspot.statements,
            "rows_scanned": io_hotspot.rows_scanned,
            "total_ms": io_hotspot.total_ms,
        },
        "io_hot_stage": list(diagnosis["io_hot_stage"]),
        "io_attribution": _io_attribution_payload(diagnosis["io_attribution"]),
        "abstraction_fidelity": [dict(row) for row in diagnosis["abstraction_fidelity"]],
        "worst_abstraction": dict(diagnosis["worst_abstraction"]),
        "defects": list(diagnosis["defects"]),
        "stage_seconds": dict(diagnosis["stage_seconds"]),
        "slowest_stage": list(diagnosis["slowest_stage"]),
        "microbench": dict(diagnosis["microbench"]),
    }


def run_bench(
    *,
    scale: float = 1.0,
    seed: int = 20260916,
    imu_samples: int = 200_000,
    stages: Sequence[str] | None = None,
) -> dict[str, Any]:
    """跑一轮完整盲测并返回机器可复核的证据载荷（纯函数，无副作用）。"""

    profiler = StorageIOProfiler()
    harness = BlindBenchHarness(scale=scale, seed=seed)
    started = time.perf_counter()
    try:
        with profiler.install():
            result = harness.run(stages=stages)
        attribution = profiler.attribute(result.stage_marks)
        microbench = harness.operator_microbench(imu_samples=imu_samples)
        diagnosis = bottleneck_diagnosis(result, attribution, microbench=microbench)
        iron_rules = iron_rule_assertions(result)
        payload = result.to_dict()
        payload["extras"]["quota"] = raw_stream_totals(scale=scale, seed=seed)
        payload["extras"]["operator_microbench"] = microbench
        payload["extras"]["diagnosis"] = _diagnosis_payload(diagnosis)
        payload["extras"]["iron_rule_assertions"] = [
            {
                "rule": assertion.rule,
                "passed": assertion.passed,
                "checks": [
                    {"name": name, "actual": actual, "requirement": requirement, "ok": ok}
                    for name, actual, requirement, ok in assertion.checks
                ],
            }
            for assertion in iron_rules
        ]
        payload["extras"]["provenance"] = {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "wall_seconds": round(time.perf_counter() - started, 3),
            "generated_at": datetime.now(UTC).isoformat(),
            "harness_scale": scale,
            "harness_seed": seed,
        }
        payload["extras"]["summary"] = render_bottleneck_summary(diagnosis)
    finally:
        harness.close()
    return payload


def render_summary(payload: Mapping[str, Any]) -> str:
    """把证据载荷排版成一页 Markdown（所有数字都来自实测字段）。"""

    extras = payload["extras"]
    diagnosis = extras["diagnosis"]
    quota = extras["quota"]
    stages = {stage["stage_id"]: stage for stage in payload["stages"]}
    iron = extras["iron_rule_assertions"]
    fidelity = diagnosis["abstraction_fidelity"]
    defects = diagnosis["defects"]
    io_hotspot = diagnosis["io_hotspot"]

    lines: list[str] = []
    lines.append("# AIOS 全流程海量盲测速览")
    lines.append("")
    lines.append(
        f"- 规模：scale={payload['scale']}，seed={payload['seed']}；"
        f"原始样本 {quota['total']:,} 条（IMU {quota['imu']:,} / 心率 {quota['heart']:,} / "
        f"图像 {quota['vision']:,} / 音频 {quota['audio']:,} / 文本 {quota['text']:,}）"
    )
    lines.append(
        f"- 总耗时 {payload['total_seconds']:.3f} s（墙钟 {extras['provenance']['wall_seconds']:.3f} s），"
        f"峰值 RSS {payload['peak_rss_mb']:.2f} MB，world_revision {payload['world_revision']}"
    )
    lines.append("")
    lines.append("## 各阶段关键实测")
    lines.append("")
    lines.append("| 阶段 | 关键数字 | 本阶段 Token | 墙钟(s) |")
    lines.append("| --- | --- | --- | --- |")
    highlights = {
        "S1": lambda f: (
            f"压缩比 {f['compression_ratio']:.6f}，吞吐 {f['throughput_samples_per_second']:,.0f}/s，"
            f"微观观察 {f['observations_in_store']:,} 条，噪声物理删 {f['noise_tombstoned_by_daily_review']} 条"
        ),
        "S2": lambda f: (
            f"下钻证据链断链率 {f['evidence_chain_break_rate']:.1%}，"
            f"年→月/周/日 {f['month_summaries']}/{f['week_summaries']}/{f['day_slices_recovered']} 层，"
            f"下钻 p95 {f['drill_p95_ms']:.3f} ms"
        ),
        "S3": lambda f: (
            f"共振 {f['resonant_dimension_count']} 维合成事件，生命周期 "
            f"{f['lifecycle_snapshots']}，非法跃迁被拒 {f['illegal_transition_rejected']}"
        ),
        "S4": lambda f: (
            f"曲线 {f['curve_days']} 天，导数闸门 允许/拒绝 {f['derivative_gate_allowed']}/{f['derivative_gate_rejected']}，"
            f"熔断 0 次大模型调用，试用结局 晋升/弱/断档 = {f['trial_promotion_outcome']}/{f['trial_weak_prediction_outcome']}/{f['trial_patchy_outcome']}"
        ),
        "S5": lambda f: (
            f"真值表前后一致 {f['truth_digest_unchanged']}，单跳隔离 {f['isolation_llm_calls']} 次大模型调用"
            f"（朴素级联需 {f['naive_cascade_recompute_calls']} 次），多跳零触碰 {f['multi_hop_untouched']}"
        ),
        "S6": lambda f: (
            f"证据包 {f['evidence_packet_hits']} 条候选 / 模型选用 {f['advice_evidence_pointers']} 条；"
            f"模型输出原样保留 {f['model_output_preserved']}，空检索命中 {f['empty_packet_hits']}"
        ),
        "S7": lambda f: (
            f"三类行动留痕 {f['actions_logged']} 条（介入 {f['interventions']} / 沉默 {f['silences']} / 建议 {f['advices']}），"
            f"模型决策原样保留 {f['model_decisions_preserved']}、反馈证据覆盖 {f['feedback_evidence_coverage']:.0%}，"
            f"零界面 {f['ui_prompts_issued']}"
        ),
        "S8": lambda f: (
            f"看板 {f['manifest_total_tokens']}/{f['manifest_budget']} Token、0 次提问；"
            f"P0 首动作 {f['p0_first_action']}（{f['p0_llm_calls']} 次大模型、p99 {f['p0_p99_ms']:.4f} ms）；"
            f"休眠 {f['dormant_tasks']} 条任务看板 Token {f['dormant_tokens_in_board']}"
        ),
    }
    for stage_id in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        stage = stages.get(stage_id)
        if stage is None:
            lines.append(f"| {stage_id} | （本次未执行） | —— | —— |")
            continue
        burn = stage.get("token_burn", 0)
        lines.append(
            f"| {stage_id} | {highlights[stage_id](stage['facts'])} | {burn} | "
            f"{diagnosis['stage_seconds'].get(stage_id, 0.0):.3f} |"
        )
    missing = diagnosis.get("missing_stages") or []
    if missing:
        lines.append("")
        lines.append(f"> 部分运行：未执行阶段 {', '.join(missing)}（相应铁律判据不出结论）")
    lines.append("")
    lines.append("## Token 账单")
    lines.append("")
    for row in diagnosis["token_ledger"]:
        detail = ", ".join(f"`{name}`={value}" for name, value in row["sources"].items()) or "机械阶段"
        lines.append(f"- {row['stage_id']}：**{row['tokens']}** Token（{detail}）")
    lines.append(f"- 全轮合计：**{diagnosis['token_total']}** Token")
    lines.append("")
    lines.append("## I/O 归因（外部仪器，非自报）")
    lines.append("")
    if io_hotspot is not None:
        lines.append(
            f"- 最烧 I/O 的查询：`{io_hotspot['signature']}` —— {io_hotspot['statements']} 条语句、"
            f"扫描 {io_hotspot['rows_scanned']:,} 行、{io_hotspot['total_ms']:.2f} ms"
        )
    lines.append(f"- 扫描行数最多的阶段：{diagnosis['io_hot_stage'][0]}（{diagnosis['io_hot_stage'][1]:,} 行）")
    lines.append("- 逐阶段明细见 `bench_run.json` 的 `extras.diagnosis.io_attribution`")
    lines.append("")
    lines.append("## 认知抽象失真度")
    lines.append("")
    lines.append("| 抽象层 | 阶段 | 失真度 | 可恢复性 |")
    lines.append("| --- | --- | --- | --- |")
    for row in fidelity:
        lines.append(
            f"| {row['abstraction']} | {row['stage']} | {row['distortion']:.6f} | {row['recoverable']} |"
        )
    if not fidelity:
        lines.append("| （相应阶段未执行） | —— | —— | —— |")
    lines.append("")
    lines.append("## 五条铁律判据")
    lines.append("")
    if not iron:
        lines.append("（本次为部分运行，没有任何铁律判据被出具）")
    for assertion in iron:
        status = "PASS" if assertion["passed"] else "FAIL"
        lines.append(f"### [{status}] {assertion['rule']}")
        for check in assertion["checks"]:
            mark = "✅" if check["ok"] else "❌"
            lines.append(
                f"- {mark} {check['name']} = {check['actual']}（要求 {check['requirement']}）"
            )
        lines.append("")
    lines.append("## 命中的缺陷（诊断书正文见第 02 篇）")
    lines.append("")
    if not defects:
        lines.append("（本轮筛选中没有缺陷被实测数字命中）")
    for defect in defects:
        lines.append(f"- **{defect['id']}（{defect['severity']}）** {defect['title']} —— {defect['measured']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 全流程海量盲测与诊断")
    parser.add_argument("--scale", type=float, default=1.0, help="数据规模倍率（1.0 = 百万级）")
    parser.add_argument("--seed", type=int, default=20260916, help="发生器随机种子")
    parser.add_argument("--imu-samples", type=int, default=200_000, help="算子微基准的 IMU 样本数")
    parser.add_argument("--out", type=Path, default=Path("reports/blind_bench"), help="产物目录")
    parser.add_argument("--stage", action="append", dest="stages", help="只跑指定阶段（可重复）")
    args = parser.parse_args(argv)

    payload = run_bench(
        scale=args.scale, seed=args.seed, imu_samples=args.imu_samples, stages=args.stages
    )
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "bench_run.json"
    md_path = args.out / "bench_summary.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    md_path.write_text(render_summary(payload), encoding="utf-8")

    print(payload["extras"]["summary"])
    print(f"\n证据 JSON：{json_path}\n速览 Markdown：{md_path}")
    failed = [item for item in payload["extras"]["iron_rule_assertions"] if not item["passed"]]
    if failed:
        print(f"\n[WARN] 有 {len(failed)} 条铁律判据未通过，详见 JSON。", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - 入口
    raise SystemExit(main())
