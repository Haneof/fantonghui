#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""已落地 `M1-001R`（端侧多模态轻量摄入 + 声纹 180 天淘汰）的 as-built 规模实测。

工单 `governance/dispatches/TASK_DISPATCH_AGENT_1_M1_001R.md` 给了三条"最高违宪红线"和
两个**未绑定规模档**的性能承诺（§1.2"图像在端侧做 50ms 初筛"、§1.4"128 维声纹 LSH"）。
按设计书铁律 2，未绑定「规模档 + fixture + profile + 工件哈希」的性能话术一律不可判定。
本探针把它们全部变成可判定断言，并额外检查两条**红线是否真的可执行**：

  红线 2 说"raw_bytes 必须立刻坚决物理删除"。但 Python 的 `bytes` 是**不可变**的：
  进程内无法擦除它的存储，只能丢弃引用。实现方在 docstring 里诚实说明了这一点（好），
  可是 `RawByteSink.purge()` 对不可变 bytes 也照记 `purged_byte_count` ⇒
  **一个声称"已销毁 N 字节"的隐私计量，其中一部分实际上只是"丢了引用"**。
  E4 就是把这件事变成断言：计量必须区分「已擦除」与「仅释放引用」。

  红线 3 说"超过 180 天"。仓库里同时存在两套口径：`VoiceprintLifecycleManager` 用**严格 >**，
  `VoiceprintTTLStateMachine` 用**包含 >=**。E7 不裁判谁对（那是治理裁决），只断言
  **两套口径都被测出、且边界日的分歧被显式记录** —— 分歧可以存在，不可以没人知道。

只用标准库（被测模块需要 pydantic）。运行：
    PYTHONPATH=src python3 reviews/architecture/evidence/verify_landed_m1_001r_edge.py --json out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from aios_core.ingest.multimodal_edge import (  # noqa: E402
    EdgeMultimodalCleaner,
    ImageSemanticObservation,
    RawByteSink,
    VoiceprintAudioSlice,
    VoiceprintLifecycleManager,
    VoiceprintLSHEngine,
    VoiceprintProfile,
    VoiceprintTTLStateMachine,
)

PROBE_VERSION = "1.3.0"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PROFILE = {
    # 工单 §1.2"端侧 50ms 初筛"的工程化默认档：单帧、含擦除、2 MB 帧缓冲
    "frame_clean_p95_ms": 50.0,
    "frame_bytes_for_gate": 2 * 1024 * 1024,
    # 128 维 LSH：单次特征哈希的预算（端侧每个音频切片都要算一次）
    "lsh_feature_hash_p95_ms": 20.0,
    # 声纹绑定：P 个待绑 profile × E 个已登记实体，必须在预算内（端侧冷启动路径）
    "bind_profiles": 2_000,
    "bind_enrollments": 500,
    # 预算理由：绑定发生在端侧冷启动/新登记匹配路径上。500 个已登记实体已远超
    # 个人设备的现实规模；本容器实测 748.6 ms 已超预算，而穿戴级 ARM 通常还要再慢
    # 3~10 倍 ⇒ 会变成用户可感知的启动卡顿。故门限取 500 ms（开发靶机口径）。
    "bind_p95_ms": 500.0,
    # 生命周期扫描：10 万条声纹档案一次全量扫描的预算
    "sweep_profiles": 100_000,
    "sweep_p95_ms": 5_000.0,
    "advance_p95_ms": 10_000.0,
    # 红线 3：陌生声纹 > 180 天必须 100% 打墓碑；已绑定的一个都不许打
    "tombstone_recall": 1.0,
    "bound_false_positive": 0,
}


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * len(s)))], 3)


def timed(fn, repeat: int) -> list[float]:
    out = []
    for _ in range(repeat):
        t0 = now_ms()
        fn()
        out.append(now_ms() - t0)
    return out


def make_profile(i: int, *, bound: bool, days: int, tomb: bool = False) -> VoiceprintProfile:
    return VoiceprintProfile(
        voiceprint_id=f"vp_{i:07d}",
        entity_id=f"ent_{i % 997:04d}" if bound else None,
        feature_hash=f"{i:032x}",
        first_detected_at=NOW - timedelta(days=days + 30),
        last_contact_at=NOW - timedelta(days=days),
        is_tombstone=tomb,
    )


class Audit:
    def __init__(self) -> None:
        self.res: dict = {"probe_version": PROBE_VERSION, "profile": PROFILE}
        self.cleaner = EdgeMultimodalCleaner()

    # ---------------- E1/E2/E3 红线 1、2 ----------------
    def e_redlines_image(self, repeat: int) -> None:
        gate = PROFILE["frame_clean_p95_ms"]
        size = PROFILE["frame_bytes_for_gate"]

        # 红线 1：画质 < 0.4 直接丢弃；边界 0.4 必须**保留**（工单写的是"< 0.4"）
        discard = self.cleaner.evaluate_and_clean_image({"quality_score": 0.3999}, b"x")
        keep = self.cleaner.evaluate_and_clean_image({"quality_score": 0.4}, b"x")
        below = self.cleaner.evaluate_and_clean_image({"quality_score": 0.0}, b"x")

        # 红线 2：合格观测里不可能存在字节字段
        obs = self.cleaner.evaluate_and_clean_image(
            {"quality_score": 0.91, "caption": "用户在书房阅读专业书籍",
             "tags": ["reading", "indoors"], "captured_at": NOW},
            bytearray(size),
        )
        fields = set(type(obs).model_fields)
        dumped = obs.model_dump_json()
        # 按**注解类型**判定是否藏了字节载荷，而不是靠字段名里有没有 "byte" 这个词
        # （上一版门逻辑就是这么写错的：`raw_image_bytes_retained` 是个 Literal[False]
        # 布尔标志，名字里含 "byte"，被自己的门误判成"存在字节字段"）。
        payload_fields = []
        for name, spec in type(obs).model_fields.items():
            ann = str(getattr(spec, "annotation", ""))
            if any(tok in ann for tok in ("bytes", "bytearray", "memoryview")):
                payload_fields.append(f"{name}:{ann}")
        name_smells = sorted(
            f for f in fields
            if f != "raw_image_bytes_retained"
            and any(tok in f.lower() for tok in ("byte", "raw", "blob", "payload", "image_data"))
        )
        retention_blocked = False
        try:
            ImageSemanticObservation(
                observation_id="x", quality_score=0.9, semantic_caption="c",
                raw_image_bytes_retained=True, captured_at=NOW)
        except Exception:
            retention_blocked = True

        # 红线 2 的物理删除：可变缓冲必须被真擦除（成功/丢弃/非法三条路径都要擦）
        ok_buf = bytearray(b"\xAB" * 4096)
        self.cleaner.evaluate_and_clean_image({"quality_score": 0.8}, ok_buf)
        bad_buf = bytearray(b"\xCD" * 4096)
        self.cleaner.evaluate_and_clean_image({"quality_score": 0.1}, bad_buf)
        err_buf = bytearray(b"\xEF" * 4096)
        try:
            self.cleaner.evaluate_and_clean_image({"quality_score": "not-a-number"}, err_buf)
        except ValueError:
            pass
        mv = memoryview(bytearray(b"\x11" * 4096))
        self.cleaner.evaluate_and_clean_image({"quality_score": 0.8}, mv)
        mv_zeroed = not any(mv.cast("B").tobytes())

        # 性能：单帧清洗（含 2 MB 擦除）p95 —— 工单"50ms 初筛"的可判定形态
        buf = bytearray(size)
        s_accept = timed(
            lambda: self.cleaner.evaluate_and_clean_image(
                {"quality_score": 0.9, "caption": "散步", "tags": ["outdoor"]}, buf), repeat)
        s_discard = timed(
            lambda: self.cleaner.evaluate_and_clean_image({"quality_score": 0.2}, buf), repeat)
        s_immutable = timed(
            lambda: self.cleaner.evaluate_and_clean_image(
                {"quality_score": 0.9, "caption": "散步"}, bytes(size)), repeat)

        self.res["e_image_redlines"] = {
            "redline1_quality_gate": {
                "score_0_3999_discarded": discard is None,
                "score_0_4_kept": keep is not None,
                "score_0_0_discarded": below is None,
                "threshold": EdgeMultimodalCleaner.QUALITY_THRESHOLD,
                "verdict": "边界口径 = 严格小于 0.4 丢弃（0.4 本身保留），与工单『画质 < 0.4 直接丢弃』一致",
            },
            "redline2_no_bytes_in_output": {
                "observation_fields": sorted(fields),
                "fields_with_bytes_annotation": payload_fields,
                "suspicious_field_names": name_smells,
                "has_any_bytes_field": bool(payload_fields or name_smells),
                "raw_image_bytes_retained": obs.raw_image_bytes_retained,
                "retention_true_construction_blocked": retention_blocked,
                "json_dump_bytes": len(dumped.encode()),
                "caption": obs.semantic_caption,
            },
            "redline2_physical_erasure": {
                "accepted_frame_zeroed": ok_buf == bytearray(4096),
                "discarded_frame_zeroed": bad_buf == bytearray(4096),
                "invalid_frame_zeroed": err_buf == bytearray(4096),
                "writable_memoryview_zeroed": mv_zeroed,
                "note": ("三条路径（合格/丢弃/非法）都在 finally 里擦除 ⇒ 异常路径不会漏擦。"
                         "这是本实现比工单骨架强的地方：骨架只在成功路径丢引用"),
            },
            "frame_clean_latency": {
                "frame_bytes": size, "repeat": repeat,
                "accept_mutable_p50_ms": pct(s_accept, .5), "accept_mutable_p95_ms": pct(s_accept, .95),
                "discard_mutable_p95_ms": pct(s_discard, .95),
                "accept_immutable_bytes_p95_ms": pct(s_immutable, .95),
                "gate_ms": gate,
                "under_gate": pct(s_accept, .95) <= gate,
                "note": ("immutable bytes 路径更快，因为它**无法被擦除**（Python bytes 不可变）——"
                         "这个『更快』是隐私缺口，不是优化"),
            },
        }

    # ---------------- E4 RawByteSink 计量语义（本轮要修的缺陷） ----------------
    def e_sink_accounting(self) -> None:
        sink = RawByteSink()
        mutable = bytearray(b"\xAA" * 1_000_000)
        sink.purge(mutable)
        after_mutable = {
            "purged_frames": sink.purged_frame_count,
            "purged_bytes": sink.purged_byte_count,
            "zeroed_frames": getattr(sink, "zeroed_frame_count", None),
            "zeroed_bytes": getattr(sink, "zeroed_byte_count", None),
            "released_frames": getattr(sink, "released_frame_count", None),
            "released_bytes": getattr(sink, "released_byte_count", None),
            "buffer_actually_zeroed": mutable == bytearray(1_000_000),
        }
        immutable = bytes(b"\xBB" * 1_000_000)
        sink.purge(immutable)
        after_immutable = {
            "purged_frames": sink.purged_frame_count,
            "purged_bytes": sink.purged_byte_count,
            "zeroed_frames": getattr(sink, "zeroed_frame_count", None),
            "zeroed_bytes": getattr(sink, "zeroed_byte_count", None),
            "released_frames": getattr(sink, "released_frame_count", None),
            "released_bytes": getattr(sink, "released_byte_count", None),
        }
        distinguishes = after_immutable["zeroed_bytes"] is not None and (
            after_immutable["zeroed_bytes"] == 1_000_000          # 只有可变那一次算"已擦除"
            and after_immutable["released_bytes"] == 1_000_000     # 不可变那次只算"释放引用"
        )
        self.res["e_sink_accounting"] = {
            "after_mutable_purge": after_mutable,
            "after_immutable_purge": after_immutable,
            "distinguishes_zeroed_from_released": bool(distinguishes),
            "defect": ("`purge()` 对**不可变 bytes** 也累加 `purged_byte_count` ⇒ 隐私计量声称"
                       "『已销毁 2,000,000 字节』，其中 1,000,000 字节实际只是被丢了引用、"
                       "存储内容原封不动地留在调用方持有的那块内存里（直到 GC）。"
                       "对一条以『物理删除』为最高红线的模块，这个计量必须能自证区分度"),
            "fix": ("保留 `purged_*` 作为总量（向后兼容），新增 `zeroed_*`（真擦除：bytearray/"
                    "可写 memoryview）与 `released_*`（仅释放引用：不可变 bytes/只读 memoryview），"
                    "并让 `retained_byte_count` 继续恒为 0"),
        }

    # ---------------- E5/E8 LSH ----------------
    def e_lsh(self, repeat: int) -> None:
        rng_vec = [((i * 37) % 2000) / 1000.0 - 1.0 for i in range(128)]
        h1 = VoiceprintLSHEngine.feature_hash(rng_vec)
        h2 = VoiceprintLSHEngine.feature_hash(list(rng_vec))
        dim_fail = False
        try:
            VoiceprintLSHEngine.feature_hash([0.0] * 127)
        except ValueError:
            dim_fail = True
        nonfinite_fail = False
        try:
            VoiceprintLSHEngine.feature_hash([float("nan")] + [0.0] * 127)
        except ValueError:
            nonfinite_fail = True

        gate = PROFILE["lsh_feature_hash_p95_ms"]
        s = timed(lambda: VoiceprintLSHEngine.feature_hash(rng_vec), repeat)

        # 24 个说话人 × 每 8 片 → build_profiles（含 128 维平均 + 哈希）
        slices = [
            VoiceprintAudioSlice(
                slice_id=f"sl_{spk:02d}_{k}", speaker_key=f"spk_{spk:02d}",
                feature_vector=tuple(((i * 31 + spk * 17 + k) % 2000) / 1000.0 - 1.0
                                     for i in range(128)),
                detected_at=NOW - timedelta(hours=k))
            for spk in range(24) for k in range(8)
        ]
        s_build = timed(lambda: VoiceprintLSHEngine.build_profiles(slices), 5)
        built = VoiceprintLSHEngine.build_profiles(slices)
        self.res["e_lsh"] = {
            "bits": VoiceprintLSHEngine.LSH_DIMENSIONS,
            "hash_hex_len": len(h1),
            "deterministic": h1 == h2,
            "rejects_127_dims": dim_fail,
            "rejects_non_finite": nonfinite_fail,
            "feature_hash_p50_ms": pct(s, .5), "feature_hash_p95_ms": pct(s, .95),
            "feature_hash_gate_ms": gate,
            "feature_hash_under_gate": pct(s, .95) <= gate,
            "cost_note": "128 个随机超平面 × 128 维 = 16,384 次乘加，纯 Python；端侧每个音频切片都要付一次",
            "build_profiles_24x8": {"profiles": len(built), "distinct_hashes": len(
                {p.feature_hash for p in built}), "p95_ms": pct(s_build, .95)},
        }

    # ---------------- E9 声纹绑定规模成本 ----------------
    def e_bind(self) -> None:
        P, E = PROFILE["bind_profiles"], PROFILE["bind_enrollments"]
        gate = PROFILE["bind_p95_ms"]
        enrollments = {f"ent_{e:04d}": f"{(e * 7919) % (1 << 128):032x}" for e in range(E)}
        profiles = [make_profile(i, bound=False, days=1) for i in range(P)]
        # 让 profile 哈希分散，避免全部并列
        profiles = [p.model_copy(update={"feature_hash": f"{(i * 104729) % (1 << 128):032x}"})
                    for i, p in enumerate(profiles)]
        t0 = now_ms()
        bound = VoiceprintLSHEngine.bind_nearest_entities(
            profiles, enrolled_entity_hashes=enrollments, max_hamming_distance=16)
        wall = now_ms() - t0
        self.res["e_bind"] = {
            "profiles": P, "enrollments": E, "hamming_comparisons": P * E,
            "wall_ms": round(wall, 1), "gate_ms": gate, "under_gate": wall <= gate,
            "bound_count": sum(1 for p in bound if p.entity_id is not None),
            "per_comparison_us": round(wall * 1000 / max(P * E, 1), 3),
            "note": ("修复前：每次比较都把两个 32 字符十六进制串 `int(...)` 重新解析一遍 ⇒ "
                     "O(P×E) 次字符串解析，实测 748.6 ms（0.749 µs/比较）。"
                     "解析结果在循环内是不变量，已提取到循环外（`_parse_hash` 预解析）⇒ "
                     "本字段记录修复后的实测值；修复前的数字见 "
                     "`verify_landed_m1_001r_edge_PREFIX_historical_result.json`（已标 HISTORICAL）"),
            "bound_count_note": ("bound_count 远小于 profiles 属**预期且正确**：随机哈希的平均海明距离≈64，"
                                 "远超 max_hamming_distance=16，且并列最近者一律**不绑定**（fail-closed）。"
                                 "宁可漏绑也不错绑——错绑会把陌生人的话挂到熟人名下"),
        }

    # ---------------- E6/E7/E10 红线 3 与生命周期 ----------------
    def e_voiceprint_lifecycle(self, repeat: int) -> None:
        n_stale_unbound, n_bound_stale, n_fresh_unbound = 10_000, 2_000, 1_000
        stale_unbound = [make_profile(i, bound=False, days=181 + i % 400)
                         for i in range(n_stale_unbound)]
        bound_stale = [make_profile(i, bound=True, days=900) for i in range(n_bound_stale)]
        fresh_unbound = [make_profile(i, bound=False, days=10) for i in range(n_fresh_unbound)]
        already = [make_profile(i, bound=False, days=400, tomb=True) for i in range(500)]

        mgr = VoiceprintLifecycleManager()
        s_sweep = timed(
            lambda: mgr.sweep_stale_voiceprints(
                stale_unbound + bound_stale + fresh_unbound + already, NOW), repeat)
        swept = mgr.sweep_stale_voiceprints(
            stale_unbound + bound_stale + fresh_unbound + already, NOW)
        tombstoned = [p for p in swept if p.is_tombstone]
        n_tomb_stale_unbound = sum(1 for p in swept[:n_stale_unbound] if p.is_tombstone)
        n_tomb_bound = sum(1 for p in swept[n_stale_unbound:n_stale_unbound + n_bound_stale]
                           if p.is_tombstone)
        n_tomb_fresh = sum(1 for p in swept[n_stale_unbound + n_bound_stale:
                                            n_stale_unbound + n_bound_stale + n_fresh_unbound]
                           if p.is_tombstone)
        inputs_untouched = all(not p.is_tombstone for p in stale_unbound)

        # E7：180 天**边界日**两套口径的分歧
        exact = make_profile(1, bound=False, days=180)
        over = make_profile(2, bound=False, days=181)
        mgr_exact = mgr.sweep_stale_voiceprints([exact], NOW)[0].is_tombstone
        mgr_over = mgr.sweep_stale_voiceprints([over], NOW)[0].is_tombstone
        sm = VoiceprintTTLStateMachine([exact.model_copy(update={"voiceprint_id": "vp_exact"}),
                                        over.model_copy(update={"voiceprint_id": "vp_over"})])
        snap = sm.advance(NOW)
        sm_exact_archived = any(p.voiceprint_id == "vp_exact"
                               for p in snap.archived_profiles)
        sm_over_archived = any(p.voiceprint_id == "vp_over" for p in snap.archived_profiles)

        # E10：10 万条档案的全量 advance（含 pydantic model_copy）
        N = PROFILE["sweep_profiles"]
        big = [make_profile(i, bound=(i % 5 == 0), days=200 + i % 300) for i in range(N)]
        s_big = timed(lambda: mgr.sweep_stale_voiceprints(big, NOW), max(repeat // 5, 3))
        sm_big = VoiceprintTTLStateMachine(big)
        s_adv = timed(lambda: sm_big.advance(NOW + timedelta(days=1)), 3)

        self.res["e_voiceprint_lifecycle"] = {
            "redline3_sweep": {
                "stale_unbound_total": n_stale_unbound,
                "stale_unbound_tombstoned": n_tomb_stale_unbound,
                "recall": round(n_tomb_stale_unbound / n_stale_unbound, 6),
                "recall_required": PROFILE["tombstone_recall"],
                "bound_stale_tombstoned": n_tomb_bound,
                "bound_false_positive_allowed": PROFILE["bound_false_positive"],
                "fresh_unbound_tombstoned": n_tomb_fresh,
                "existing_tombstones_kept": sum(1 for p in swept[-500:] if p.is_tombstone),
                "inputs_not_mutated": inputs_untouched,
                "total_tombstoned": len(tombstoned),
            },
            "boundary_180d_divergence": {
                "manager_at_exactly_180d": mgr_exact,
                "manager_at_181d": mgr_over,
                "state_machine_at_exactly_180d": sm_exact_archived,
                "state_machine_at_181d": sm_over_archived,
                "divergent_on_boundary_day": mgr_exact != sm_exact_archived,
                "semantics": ("Manager = 严格 `> 180d`（工单/宪法『超过 180 天』的字面口径）；"
                              "StateMachine = 包含 `>= 180d`（更早删除，隐私更保守）。"
                              "两者在**边界日**给出相反答案，且各自的测试都把口径钉住了 ⇒ "
                              "不是 bug，是**未裁决的双口径**。本探针只断言『分歧被显式记录』，"
                              "由治理方指定唯一权威口径（建议：对外验收用 `> 180d`，"
                              "端侧自动清理用 `>= 180d` 以偏保守，但必须写进同一份契约）"),
            },
            "scale_cost": {
                "sweep_13_5k_profiles_p95_ms": pct(s_sweep, .95),
                "sweep_100k_profiles_p95_ms": pct(s_big, .95),
                "sweep_gate_ms": PROFILE["sweep_p95_ms"],
                "sweep_under_gate": pct(s_big, .95) <= PROFILE["sweep_p95_ms"],
                "advance_100k_profiles_p95_ms": pct(s_adv, .95),
                "advance_gate_ms": PROFILE["advance_p95_ms"],
                "advance_under_gate": pct(s_adv, .95) <= PROFILE["advance_p95_ms"],
                "profiles": N,
            },
        }

    # ---------------- E11 流式摄入的峰值内存 ----------------
    def e_stream_memory(self, frames: int = 4_000, size: int = 512 * 1024) -> None:
        """同一批帧，分别用 bytearray（可擦除）与 bytes（不可擦除）喂入，比较峰值 RSS。"""
        out = {}
        for mode in ("bytearray", "bytes"):
            db = f"/tmp/aios_m1_001r_mem_{mode}.sqlite3"
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--mem-child",
                 json.dumps({"mode": mode, "frames": frames, "size": size})],
                capture_output=True, text=True, timeout=1800)
            try:
                out[mode] = json.loads(proc.stdout.strip().splitlines()[-1])
            except Exception:
                out[mode] = {"error": (proc.stderr or proc.stdout)[-300:], "rc": proc.returncode}
        b = out.get("bytearray", {}).get("peak_rss_mb")
        i = out.get("bytes", {}).get("peak_rss_mb")
        self.res["e_stream_memory"] = {
            "frames": frames, "frame_bytes": size, "measurements": out,
            "bytearray_peak_rss_mb": b, "bytes_peak_rss_mb": i,
            "note": ("可擦除路径（bytearray）在擦除后那块内存可被复用；不可变路径只能等 GC。"
                     "两条路径的峰值 RSS 差 = 『物理删除』在端侧内存上的真实价值"),
        }

    @staticmethod
    def mem_child(spec: dict) -> int:
        mode, frames, size = spec["mode"], spec["frames"], spec["size"]
        cleaner = EdgeMultimodalCleaner()
        kept = 0
        for i in range(frames):
            payload = (bytearray(size) if mode == "bytearray" else bytes(size))
            obs = cleaner.evaluate_and_clean_image(
                {"quality_score": 0.5 + (i % 50) / 100.0, "caption": f"场景 {i}",
                 "tags": ["routine", f"t{i % 7}"]}, payload)
            kept += 1 if obs is not None else 0
        print(json.dumps({"mode": mode, "frames": frames, "kept": kept,
                          "peak_rss_mb": round(resource.getrusage(
                              resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1),
                          "purged_bytes": cleaner.raw_byte_sink.purged_byte_count},
                         ensure_ascii=False))
        return 0

    # ---------------- 门 ----------------
    def finalize(self) -> dict:
        img = self.res["e_image_redlines"]
        sink = self.res["e_sink_accounting"]
        lsh = self.res["e_lsh"]
        bind = self.res["e_bind"]
        life = self.res["e_voiceprint_lifecycle"]
        r3 = life["redline3_sweep"]
        sc = life["scale_cost"]
        gates = {
            "E1_quality_gate_boundary": (img["redline1_quality_gate"]["score_0_3999_discarded"]
                                         and img["redline1_quality_gate"]["score_0_4_kept"]
                                         and img["redline1_quality_gate"]["score_0_0_discarded"]),
            "E2_no_raw_bytes_in_output": (
                img["redline2_no_bytes_in_output"]["raw_image_bytes_retained"] is False
                and img["redline2_no_bytes_in_output"]["retention_true_construction_blocked"]
                and not img["redline2_no_bytes_in_output"]["has_any_bytes_field"]),
            "E3_mutable_buffer_erased_on_all_paths": all(
                img["redline2_physical_erasure"][k] for k in
                ("accepted_frame_zeroed", "discarded_frame_zeroed",
                 "invalid_frame_zeroed", "writable_memoryview_zeroed")),
            "E4_sink_distinguishes_zeroed_from_released": sink["distinguishes_zeroed_from_released"],
            "E5_frame_clean_under_50ms": img["frame_clean_latency"]["under_gate"],
            "E6_redline3_tombstone_recall_and_no_bound_fp": (
                r3["recall"] >= PROFILE["tombstone_recall"]
                and r3["bound_stale_tombstoned"] <= PROFILE["bound_false_positive"]
                and r3["fresh_unbound_tombstoned"] == 0
                and r3["inputs_not_mutated"]),
            "E7_180d_divergence_explicitly_recorded": bool(
                life["boundary_180d_divergence"]["divergent_on_boundary_day"]),
            "E8_lsh_128bit_deterministic_fail_closed": (
                lsh["deterministic"] and lsh["hash_hex_len"] == 32
                and lsh["rejects_127_dims"] and lsh["rejects_non_finite"]
                and lsh["feature_hash_under_gate"]
                and lsh["build_profiles_24x8"]["distinct_hashes"] == 24),
            "E9_bind_within_budget": bind["under_gate"],
            "E10_lifecycle_scale_within_budget": (sc["sweep_under_gate"]
                                                  and sc["advance_under_gate"]),
        }
        self.res["gates"] = gates
        self.res["gate_count"] = len(gates)
        self.res["passed"] = sum(1 for v in gates.values() if v)
        self.res["all_gates_pass"] = all(gates.values())
        self.res["summary"] = {
            "frame_clean_p95_ms": img["frame_clean_latency"]["accept_mutable_p95_ms"],
            "frame_gate_ms": PROFILE["frame_clean_p95_ms"],
            "lsh_feature_hash_p95_ms": lsh["feature_hash_p95_ms"],
            "bind_wall_ms": bind["wall_ms"], "bind_comparisons": bind["hamming_comparisons"],
            "sweep_100k_p95_ms": sc["sweep_100k_profiles_p95_ms"],
            "advance_100k_p95_ms": sc["advance_100k_profiles_p95_ms"],
            "tombstone_recall": r3["recall"],
            "bound_false_positives": r3["bound_stale_tombstoned"],
            "sink_distinguishes_erasure": sink["distinguishes_zeroed_from_released"],
        }
        self.res["provenance"] = {
            "probe_version": PROBE_VERSION,
            "script_sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
            # 自述产出者：CG-1 优先用它定位"本工件对应的那支探针"（多支审计探针共存时必需）
            "probe_script": str(Path(__file__).resolve().relative_to(REPO)),
            "subject_under_test": "src/aios_core/ingest/multimodal_edge.py",
            "subject_sha256": hashlib.sha256(
                (REPO / "src/aios_core/ingest/multimodal_edge.py").read_bytes()).hexdigest(),
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "dispatch_doc": "governance/dispatches/TASK_DISPATCH_AGENT_1_M1_001R.md",
            "disclaimer": ("合成帧与合成声纹；数字用于**门限可达性与计划间比较**，"
                           "不是产品 SLO 承诺；运行间存在 ±20% 抖动"),
        }
        return self.res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=200)
    ap.add_argument("--json", default="")
    ap.add_argument("--mem-child", default=argparse.SUPPRESS)
    args = ap.parse_args()
    if getattr(args, "mem_child", ""):
        return Audit.mem_child(json.loads(args.mem_child))

    a = Audit()
    wall0 = now_ms()
    a.e_redlines_image(args.repeat)
    a.e_sink_accounting()
    a.e_lsh(args.repeat)
    a.e_bind()
    a.e_voiceprint_lifecycle(args.repeat)
    a.e_stream_memory()
    res = a.finalize()
    res["environment"] = {"repeat": args.repeat, "wall_ms": round(now_ms() - wall0, 1),
                          "python": platform.python_version(),
                          "sqlite": sqlite3.sqlite_version,
                          "platform": platform.platform()}
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    print("\nJSON_SUMMARY " + json.dumps({"gates": res["gates"], "summary": res["summary"]},
                                         ensure_ascii=False))
    return 0 if res["all_gates_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
