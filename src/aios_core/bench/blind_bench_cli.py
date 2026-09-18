"""盲测命令行入口：一条命令跑完八个阶段并落一份机器可读快照。

用法::

    python -m aios_core.bench.blind_bench_cli --workdir /tmp/aios_bench --json out.json
    python -m aios_core.bench.blind_bench_cli --profile full --stages 1,2

退出码：0 = 全部阶段通过；2 = 断言失败（真实缺陷，不做任何降级）；3 = 参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from aios_core.bench.adversarial_life_bench import FULL_PROFILE, GATE_PROFILE
from aios_core.bench.blind_bench_harness import BlindBenchHarness
from aios_core.bench.tool_catalog import catalog_digest, submit_catalog

STAGES: Mapping[str, str] = {
    "1": "run_stage1",
    "2": "run_stage2",
    "3": "run_stage3",
    "4": "run_stage4",
    "5": "run_stage5",
    "6": "run_stage6",
    "7": "run_stage7",
    "8": "run_stage8",
}

#: 铁律核账：每条铁律在盲测中的可核对断言（阶段 → 断言说明）。
IRON_LAW_CHECKS: Mapping[str, tuple[str, ...]] = {
    "IRON_LAW_1_OUTPUT_QUALITY": (
        "S6 建议带证据指针且零客服八股",
        "S7 模型沟通决策原样保留、反馈事实可追溯、协议畸形可拒绝",
        "S8 模型回复零改写且 Cockpit 上下文 1500 Token 内",
    ),
    "IRON_LAW_2_HISTORY_IMMUTABLE": (
        "S5 Observation 台账 SHA-256 校验通过、UPDATE/DELETE 违例 0",
        "S5 单跳隔离：210 节点级联被压到 10，LLM 重算 0 次",
        "S5 双镜视图 base 指纹恒等、一致性 1.0",
    ),
    "IRON_LAW_3_P0_HARD_BYPASS": (
        "S8 首行硬件初动 p99 ≤ 50ms",
        "S8 世界模型组装 0 次、大模型现场急救研判有效介入",
        "S8 畸形载荷降级仍必须发出硬件动作",
    ),
    "IRON_LAW_4_AUTONOMOUS_DELETION": (
        "S1 证据保留率 1.0、噪声清除率 1.0",
        "S1 原始字节残留 0、波形直写违例 0",
        "S1 语音print 180 天淘汰后切片零残留",
    ),
    "IRON_LAW_5_DIMENSION_GATES": (
        "S4 三闸拒绝零域/直觉/额度超限申请 100%",
        "S4 30 天试用期 70% 命中率门限生效",
        "S4 每日反思配额 1 次，递归自省被切断",
    ),
}


def iron_law_report(harness: BlindBenchHarness) -> Dict[str, Any]:
    """从真实阶段产物里抽取五条铁律的核账记录（拿不到证据就报 False）。"""

    # 阶段结果按需惰性生成：未跑过的阶段为 None，对应铁律一律判 False
    # （绝不因为"没测"而给出"成立"的假结论）。
    s1 = getattr(harness, "stage1", None)
    s2 = getattr(harness, "stage2", None)
    s3 = getattr(harness, "stage3", None)
    s4 = getattr(harness, "stage4", None)
    s5 = getattr(harness, "stage5", None)
    s6 = getattr(harness, "stage6", None)
    s7 = getattr(harness, "stage7", None)
    s8 = getattr(harness, "stage8", None)

    def holds(value: Any) -> bool:
        return bool(value)

    law1 = {
        "holds": holds(
            s6
            and s6.evidence_pointers_resolved == s6.evidence_pointers_total
            and not s6.boilerplate_hits
            and all(count <= 3 for count in s6.sentence_counts)
            and s7
            and s7.feedback_coverage == 1.0
            and s7.model_content_preserved
            and s7.protocol_rewritten == 0
            and s7.protocol_rejected >= 1
            and s8
            and s8.dialogue_program_rewrites == 0
            and s8.dialogue_model_outputs_preserved
            and s8.dialogue_max_tokens <= s8.manifest_budget
        ),
        "evidence": {
            "S6_pointers": f"{s6.evidence_pointers_resolved}/{s6.evidence_pointers_total}" if s6 else None,
            "S6_boilerplate_hits": list(s6.boilerplate_hits) if s6 else None,
            "S7_feedback_coverage": s7.feedback_coverage if s7 else None,
            "S7_protocol_rejected": (
                f"{s7.protocol_rejected}/{s7.protocol_samples}" if s7 else None
            ),
            "S7_protocol_rewritten": s7.protocol_rewritten if s7 else None,
            "S8_dialogue_program_rewrites": s8.dialogue_program_rewrites if s8 else None,
            "S8_model_outputs_preserved": s8.dialogue_model_outputs_preserved if s8 else None,
            "S8_dialogue_max_tokens": s8.dialogue_max_tokens if s8 else None,
        },
    }
    law2 = {
        "holds": holds(
            s5
            and s5.ledger_integrity
            and not s5.immutability_violations
            and s5.deleted_rows == 0
            and s5.cascade_nodes_single_hop <= 12
            and s5.llm_recompute_calls == 0
            and s5.data_consistency_ratio == 1.0
        ),
        "evidence": {
            "S5_immutable_facts": s5.ledger_facts if s5 else None,
            "S5_violations": list(s5.immutability_violations) if s5 else None,
            "S5_cascade_naive_vs_isolated": (
                f"{s5.cascade_nodes_naive} -> {s5.cascade_nodes_single_hop}" if s5 else None
            ),
            "S5_llm_recompute_calls": s5.llm_recompute_calls if s5 else None,
        },
    }
    law3 = {
        "holds": holds(
            s8
            and s8.p0_latency_p99_ms <= 50.0
            and s8.p0_llm_calls >= 1
            and s8.p0_cockpit_assemblies == 0
            and s8.p0_malformed_pulse
        ),
        "evidence": {
            "S8_p0_p99_ms": s8.p0_latency_p99_ms if s8 else None,
            "S8_p0_max_ms": s8.p0_latency_max_ms if s8 else None,
            "S8_p0_llm_calls": s8.p0_llm_calls if s8 else None,
            "S8_p0_cockpit_assemblies": s8.p0_cockpit_assemblies if s8 else None,
        },
    }
    law4 = {
        "holds": holds(
            s1
            and s1.evidence_retention_ratio == 1.0
            and s1.noise_purge_ratio == 1.0
            and s1.raw_bytes_retained == 0
            and not s1.raw_observation_scan_violations
            and not s1.noise_text_residue
            and s1.voiceprint_slice_purity == 1.0
        ),
        "evidence": {
            "S1_evidence_retention": s1.evidence_retention_ratio if s1 else None,
            "S1_noise_purge": s1.noise_purge_ratio if s1 else None,
            "S1_raw_bytes_retained": s1.raw_bytes_retained if s1 else None,
            "S1_scan_violations": list(s1.raw_observation_scan_violations) if s1 else None,
            "S1_noise_text_residue": list(s1.noise_text_residue) if s1 else None,
            "S1_voiceprint_slice_purity": s1.voiceprint_slice_purity if s1 else None,
        },
    }
    law5 = {
        "holds": holds(
            s4
            and len(s4.gate1_rejections) >= 1
            and len(s4.quota_rejections) >= 1
            and s4.gate2_rejection
            and s4.gate2_promotion
            and s4.recursion_cut
            and s4.hardware_derivative_violations == ()
        ),
        "evidence": {
            "S4_gate1_rejections": list(s4.gate1_rejections) if s4 else None,
            "S4_quota_rejections": list(s4.quota_rejections) if s4 else None,
            "S4_gate2_rejection": s4.gate2_rejection if s4 else None,
            "S4_gate2_promotion": s4.gate2_promotion if s4 else None,
            "S4_recursion_cut": s4.recursion_cut if s4 else None,
        },
    }
    laws = {
        "IRON_LAW_1_OUTPUT_QUALITY": law1,
        "IRON_LAW_2_HISTORY_IMMUTABLE": law2,
        "IRON_LAW_3_P0_HARD_BYPASS": law3,
        "IRON_LAW_4_AUTONOMOUS_DELETION": law4,
        "IRON_LAW_5_DIMENSION_GATES": law5,
    }
    for name, payload in laws.items():
        payload["checks"] = list(IRON_LAW_CHECKS[name])
    _ = (s2, s3)
    return laws


def _stage_rows(harness: BlindBenchHarness) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        metric = harness.metrics.get(stage)
        if metric is None:
            continue
        rows.append(
            {
                "stage": stage,
                "label": metric.label,
                "elapsed_ms": round(metric.elapsed_ms, 3),
                "rss_peak_delta_kb": metric.rss_peak_delta_kb,
                "tokens": metric.tokens,
                "llm_calls": metric.llm_calls,
                "counters": metric.counters,
                "latencies": metric.latencies,
            }
        )
    return rows


class MemoryBudgetExceeded(RuntimeError):
    """压测自保：驻留内存超过预算即熔断，绝不把进程拖到被 OOM 杀掉。"""


def _rss_kb() -> int:
    try:
        return int(Path("/proc/self/statm").read_text(encoding="utf-8").split()[1]) * 4
    except (OSError, IndexError, ValueError):
        return 0


def _build_snapshot(
    harness: BlindBenchHarness,
    *,
    profile: str,
    stages: Sequence[str],
    aborted: str | None,
    elapsed_ms: float,
) -> Dict[str, Any]:
    """构造机器可读快照（成功、失败、熔断三条路径共用同一口径）。"""

    _pipeline, proposals = submit_catalog()
    digest = catalog_digest(proposals)
    laws = iron_law_report(harness)
    ran = [row["stage"] for row in _stage_rows(harness)]
    return {
        "profile": profile,
        "seed": harness.seed,
        "stages_requested": list(stages),
        "stages_completed": ran,
        "aborted": aborted,
        "total_elapsed_ms": round(elapsed_ms, 3),
        "stage_rows": _stage_rows(harness),
        "latency_summary": harness.recorder.summary(),
        "memory": harness.memory.snapshot(),
        "token_ledger": harness.ledger.snapshot(),
        "model_calls": harness.meter.snapshot(),
        "iron_laws": laws,
        "tool_catalog": digest,
    }


def _write_snapshot(snapshot: Mapping[str, Any], json_path: Path | None) -> None:
    if json_path is None:
        return
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  快照已写入 {json_path}")


def _start_memory_watchdog(
    harness: BlindBenchHarness,
    *,
    budget_mb: int,
    json_path: Path | None,
    profile: str,
    stages: Sequence[str],
    grace_s: float,
    started: float,
) -> "threading.Thread":
    """阶段内内存看门狗：单阶段内部暴涨时也能自保退出并留下证据。

    为什么必须是**阶段内**看门狗：阶段之间的熔断检查防不住"某一阶段自己把内存打爆"。
    FULL 档位 S3 的全库建图就是这样把进程送去被内核 OOM 杀掉的 —— 我们宁可自己
    先写盘、再退出，也不要一个没有尸检报告的 SIGKILL。
    """

    def _watch() -> None:
        over_since: float | None = None
        while True:
            current_mb = _rss_kb() / 1024.0
            if current_mb > budget_mb:
                over_since = over_since or time.perf_counter()
                if time.perf_counter() - over_since >= grace_s:
                    reason = (
                        f"watchdog: RSS {current_mb:,.1f} MB > budget {budget_mb} MB "
                        f"(grace {grace_s:g}s elapsed)"
                    )
                    print(f"  内存看门狗熔断：{reason}", file=sys.stderr, flush=True)
                    snapshot = _build_snapshot(
                        harness,
                        profile=profile,
                        stages=stages,
                        aborted=reason,
                        elapsed_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    _write_snapshot(snapshot, json_path)
                    sys.stderr.flush()
                    os._exit(4)
            else:
                over_since = None
            time.sleep(0.2)

    thread = threading.Thread(target=_watch, name="blind-bench-memory-watchdog", daemon=True)
    thread.start()
    return thread


def run(
    *,
    workdir: Path,
    profile: str,
    stages: Sequence[str],
    json_path: Path | None,
    keep_workdir: bool,
    max_rss_mb: int = 0,
    rss_grace_s: float = 2.0,
) -> int:
    if workdir.exists() and not keep_workdir:
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    profile_object = FULL_PROFILE if profile == "full" else GATE_PROFILE
    harness = BlindBenchHarness(workdir=workdir, profile=profile_object)
    started = time.perf_counter()
    if max_rss_mb > 0:
        _start_memory_watchdog(
            harness,
            budget_mb=max_rss_mb,
            json_path=json_path,
            profile=profile,
            stages=stages,
            grace_s=rss_grace_s,
            started=started,
        )
    aborted: str | None = None
    exit_code = 0
    for stage in stages:
        try:
            getattr(harness, STAGES[stage])()
        except Exception as exc:  # noqa: BLE001 - 压测必须如实报告失败阶段
            print(f"  ✗ S{stage} 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            aborted = f"S{stage} raised {type(exc).__name__}"
            exit_code = 2
            break
        metric = harness.metrics.get(f"S{stage}")
        rss_mb = _rss_kb() / 1024.0
        print(
            f"  ✓ S{stage} {metric.elapsed_ms:,.1f} ms"
            f"（阶段内存增量 {metric.rss_peak_delta_kb} kB，当前 RSS {rss_mb:,.1f} MB）",
            flush=True,
        )
        if max_rss_mb and rss_mb > max_rss_mb:
            print(
                f"  内存熔断：RSS {rss_mb:,.1f} MB 超过预算 {max_rss_mb} MB，"
                "停止后续阶段以避免 OOM（已完成的阶段度量仍然有效）",
                file=sys.stderr,
            )
            aborted = f"RSS {rss_mb:,.1f} MB > budget {max_rss_mb} MB after S{stage}"
            exit_code = 4
            break
    elapsed = time.perf_counter() - started

    snapshot = _build_snapshot(
        harness,
        profile=profile,
        stages=stages,
        aborted=aborted,
        elapsed_ms=elapsed * 1000.0,
    )
    laws = snapshot["iron_laws"]
    digest = snapshot["tool_catalog"]
    ran = snapshot["stages_completed"]
    all_hold = all(payload["holds"] for payload in laws.values())
    print(f"  铁律核账（已跑阶段：{'/'.join(ran) or '无'}）：{'全部成立' if all_hold else '存在不成立项'}")
    for name, payload in laws.items():
        print(f"    - {name}: {'PASS' if payload['holds'] else 'FAIL'}")
    print(f"  新工具提案：{digest['count']} 件 -> {','.join(digest['tool_ids'])}")
    _write_snapshot(snapshot, json_path)
    if exit_code:
        return exit_code
    return 0 if all_hold else 2


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 全流程海量盲测（八阶段）")
    parser.add_argument("--workdir", default="/tmp/aios_blind_bench", type=Path)
    parser.add_argument("--profile", default="gate", choices=("gate", "full"))
    parser.add_argument("--stages", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--json", dest="json_path", default=None, type=Path)
    parser.add_argument("--keep-workdir", action="store_true")
    parser.add_argument(
        "--max-rss-mb",
        type=int,
        default=0,
        help="驻留内存预算（MB）；超限即熔断退出（0 = 不设限）",
    )
    parser.add_argument(
        "--rss-grace-s",
        type=float,
        default=2.0,
        help="内存超预算后的宽限期（秒）：给当前阶段一个收尾窗口，再硬熔断",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    stages = [item.strip() for item in str(args.stages).split(",") if item.strip()]
    invalid = [item for item in stages if item not in STAGES]
    if invalid:
        print(f"未知阶段：{invalid}（可选 1~8）", file=sys.stderr)
        return 3
    return run(
        workdir=args.workdir,
        profile=args.profile,
        stages=stages,
        json_path=args.json_path,
        keep_workdir=args.keep_workdir,
        max_rss_mb=args.max_rss_mb,
        rss_grace_s=args.rss_grace_s,
    )


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    raise SystemExit(main())
