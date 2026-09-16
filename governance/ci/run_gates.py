#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""治理与证据 CI 门（`PROBE-CI-002` + `SPINE-EVIDENCE` 的可执行形态）。

为什么需要它
------------
本仓库现在有三类"证据"：①编号 registry + 其检查器；②设计书（1,300+ 行，引用大量实测数字）；
③探针脚本 + 其归档工件（1M / 100k 两档）。三者之间**没有任何机器强制的一致性**：
脚本改了而工件没重跑、工件重跑了而文档数字没改、文档引用了 registry 里不存在的号 —— 
这三种腐化都不会让任何测试失败。本脚本把它们全部变成 hard fail。

五道门
------
CG-1 工件完整性与**溯源**：SHA256SUMS 逐条校验；每个 JSON 工件内嵌的
     `provenance.script_sha256` 必须等于当前脚本字节哈希（脚本改动而工件未重跑 ⇒ fail）。
CG-2 编号 registry 门：调用 `check_issue_registry.py --json`；
     规则 A/B/D/E-格式违规 ⇒ hard fail；CONFLICT/UNRATIFIED/gate 争议 ⇒ **治理债**，
     计入 baseline 并做**棘轮**（只许减少不许增加）。
CG-3 文档 ↔ registry 一致性：设计书引用的每个 `RC-***` 必须已注册或已登记 alias；
     registry 的每条 RC/alias 必须在设计书中出现；slug 必须逐字相同；
     门位必须一致（除非 owner 上存在 OPEN 的 `gate_disputes`）。
CG-4 探针 CI 档实跑：`--scale 100k` 当场跑一遍，要求 exit 0、全部适用门通过、
     `gates_not_applicable` 只含 G2b 绝对超门断言，并复核 I7 非空转断言。
CG-5 数字可追溯：归档 1M 工件的每个数值事实必须能在设计书正文定位（豁免表显式登记）；
     且**已被取代的旧运行值**（superseded_values）不得再出现在正文里（防数字回潮）。
CG-6 交付物存在性（V3G-003）：派工单注册表声明的"核心交付源码"必须存在且行数 ≥ min_lines；
     缺口总数对 gate_baseline.cg6_deliverables.cg6_missing_max 做棘轮（只许减少）。
     blocking=false 时只计数不阻断——真实缺口存在时阻断会挡住所有其他工作，故先棘轮、补齐后翻阻断。
CG-1 另对 as-built 审计工件做**双向溯源**：探针脚本哈希 + 被测源码哈希（subject_sha256）都必须对得上；
     被测代码一旦变更，旧审计工件即失效，不得继续用它的数字下结论（铁律 2 第四元）。

退出码：0 = 无 hard fail；1 = 有 hard fail；2 = 环境/文件错误。
只用标准库（本沙箱 `pip install` 受 PEP 668 阻断，CI 门不得依赖第三方包）。

用法
----
    python3 governance/ci/run_gates.py                 # 全五道门（含 100k 探针，约 30 s）
    python3 governance/ci/run_gates.py --skip-probe     # 只跑文档/registry/工件门
    python3 governance/ci/run_gates.py --json           # 机器可读
    python3 governance/ci/run_gates.py --write-baseline # 把当前治理债写入 baseline（需人工确认）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# `AIOS_GATES_REPO` 允许对**仓库副本**跑门（负向自测用；CI 里不设，默认本仓库根）。
REPO = Path(os.environ.get("AIOS_GATES_REPO") or HERE.parent.parent).resolve()
REGISTRY = REPO / "governance/issue_registry/v3_issue_registry.json"
CHECKER = REPO / "governance/issue_registry/check_issue_registry.py"
REG_EVIDENCE = REPO / "governance/issue_registry/evidence"
ARCH_EVIDENCE = REPO / "reviews/architecture/evidence"
PROBE = ARCH_EVIDENCE / "verify_reconstruction_design.py"
BOOK = REPO / ("reviews/architecture/AIOS_Core_重构设计书_独立首席架构师版_"
               "可执行验证_2026-09-16.md")
ART_1M = ARCH_EVIDENCE / "verify_reconstruction_design_1m_result.json"
ART_CI = ARCH_EVIDENCE / "verify_reconstruction_design_100k_result.json"
BASELINE = REPO / "governance/ci/gate_baseline.json"
# as-built 审计探针：审计工件的溯源要**双向**校验（探针脚本 + 被测源码），
# 因为"被测代码改了但审计工件没重跑"与"探针改了但工件没重跑"同样是溯源断裂。
AUDIT_PROBE = ARCH_EVIDENCE / "verify_landed_m1_017_cjk.py"
AUDIT_ARTIFACTS = [ARCH_EVIDENCE / "verify_landed_m1_017_cjk_1m_result.json",
                   ARCH_EVIDENCE / "verify_landed_m1_017_cjk_100k_result.json",
                   ARCH_EVIDENCE / "verify_landed_m1_017_cjk_10k_result.json",
                   ARCH_EVIDENCE / "verify_landed_m1_001r_edge_result.json"]
# 刻意**不**把 *_PREFIX_historical_result.json 放进 AUDIT_ARTIFACTS：它的 subject_sha256
# 指向修复前的源码字节状态（工作树中已不存在），双向溯源必然不符。它作为 HISTORICAL 证据
# 进 SHA256SUMS（防篡改），但不参与"当前代码"的溯源校验——这正是三态规则里"历史运行"的处置方式。
HISTORICAL_AUDIT_ARTIFACTS = [ARCH_EVIDENCE / "verify_landed_m1_001r_edge_PREFIX_historical_result.json"]
DISPATCH_REGISTRY = REPO / "governance/dispatches/TASK_DISPATCH_REGISTRY.md"
CI_EVIDENCE = REPO / "governance/ci/evidence"

RC_RE = re.compile(r"\bRC-(\d{3})\b")

# 完整性清单：显式列表（不含清单自身、不含派生索引 PROVENANCE.json、不含带时间戳的运行日志）。
MANIFEST = ARCH_EVIDENCE / "verify_reconstruction_design_SHA256SUMS"
MANIFEST_FILES = [
    "reviews/architecture/evidence/verify_reconstruction_design.py",
    "reviews/architecture/evidence/verify_reconstruction_design_1m_result.json",
    "reviews/architecture/evidence/verify_reconstruction_design_1m.log",
    "reviews/architecture/evidence/verify_reconstruction_design_100k_result.json",
    "reviews/architecture/evidence/verify_reconstruction_design_100k.log",
    "reviews/architecture/AIOS_Core_重构设计书_独立首席架构师版_可执行验证_2026-09-16.md",
    "governance/issue_registry/v3_issue_registry.json",
    "governance/issue_registry/check_issue_registry.py",
    "governance/issue_registry/evidence/check_run_2026-09-16.log",
    "governance/issue_registry/evidence/check_run_2026-09-16.json",
    "governance/issue_registry/evidence/check_run_2026-09-16_v0.3.0.log",
    "governance/issue_registry/evidence/check_run_2026-09-16_v0.3.0.json",
    "governance/issue_registry/evidence/negative_self_test_2026-09-16.log",
    "governance/ci/run_gates.py",
    "governance/ci/negative_self_test.py",
    "governance/ci/gate_baseline.json",
    "governance/ci/governance-gates.workflow.yml",
    # --- as-built 审查（第一批派工交付）证据：探针 + 100k/1M 工件 + 审查报告 ---
    "reviews/architecture/evidence/verify_landed_m1_017_cjk.py",
    "reviews/architecture/evidence/verify_landed_m1_017_cjk_1m_result.json",
    "reviews/architecture/evidence/verify_landed_m1_017_cjk_1m.log",
    "reviews/architecture/evidence/verify_landed_m1_017_cjk_100k_result.json",
    "reviews/architecture/evidence/verify_landed_m1_017_cjk_100k.log",
    "reviews/architecture/evidence/verify_landed_m1_017_cjk_10k_result.json",
    "reviews/architecture/evidence/verify_landed_m1_017_cjk_10k.log",
    "reviews/architecture/AIOS_Core_as_built_审查报告_第一批派工交付_2026-09-16.md",
    # --- as-built 审查（M1-001R 端侧摄入与声纹 TTL）证据 ---
    "reviews/architecture/evidence/verify_landed_m1_001r_edge.py",
    "reviews/architecture/evidence/verify_landed_m1_001r_edge_result.json",
    "reviews/architecture/evidence/verify_landed_m1_001r_edge.log",
    "reviews/architecture/evidence/verify_landed_m1_001r_edge_PREFIX_historical_result.json",
    "reviews/architecture/evidence/verify_landed_m1_001r_edge_PREFIX_historical.log",
    "reviews/architecture/AIOS_Core_as_built_审查报告_M1_001R_端侧摄入与声纹TTL_2026-09-16.md",
]
# 自测结果 JSON 同样**不进清单**：它由自测自身重写，被哈希就会形成"写→不符→再写"的自指回路。
# 它作为运行记录入库（内容字节确定性，便于 diff），完整性由 git 与 PROVENANCE.json 保证。
# 刻意**不**把带时间戳的运行记录（gate_run_canonical_*.log/.json、negative_self_test_*.log）放进清单：
# 它们是"运行日志"，内容含本次运行的时刻与耗时，一旦被哈希就会出现
# "刷新清单 → 写新日志 → 清单又不符"的无穷回归。清单只覆盖**输入**：脚本、工件、文档、registry、
# baseline、workflow，以及字节确定性的自测结果 JSON。
# 说明：带时间戳的逐次运行日志（gate_run_<ts>.json）不入库、不进清单 —— 入库的是**一次canonical 运行**
# （gate_run_canonical_*），否则每次本地跑都会制造新的哈希不符。


# 第二份清单：registry 自己的证据目录（路径相对 governance/issue_registry/，沿用既有格式）
REG_MANIFEST = REPO / "governance/issue_registry/evidence/SHA256SUMS"
REG_MANIFEST_ROOT = REPO / "governance/issue_registry"
REG_MANIFEST_FILES = [
    "v3_issue_registry.json",
    "check_issue_registry.py",
    "evidence/check_run_2026-09-16.log",
    "evidence/check_run_2026-09-16.json",
    "evidence/check_run_2026-09-16_v0.3.0.log",
    "evidence/check_run_2026-09-16_v0.3.0.json",
    "evidence/negative_self_test_2026-09-16.log",
    "evidence/check_run_2026-09-16_v0.3.1.log",
    "evidence/check_run_2026-09-16_v0.3.1.json",
    "evidence/pytest_environment_ruling_2026-09-16.log",
]


def _write_manifest(path: Path, root: Path, files: list[str], rep: Report) -> dict:
    lines, missing = [], []
    for rel in files:
        f = root / rel
        if not f.exists():
            missing.append(rel)
            continue
        lines.append(f"{sha256_file(f)}  {rel}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for m in missing:
        rep.fail("CG-1", f"清单 {path.name} 应包含但文件不存在：{m}")
    return {"manifest": str(path.relative_to(REPO)), "entries": len(lines), "missing": missing}


def refresh_manifest(rep: Report) -> dict:
    """人工/代理显式动作：按当前仓库状态重算**两份**清单。CI 只跑校验，不跑本函数。"""
    out = {"architecture": _write_manifest(MANIFEST, REPO, MANIFEST_FILES, rep),
           "registry": _write_manifest(REG_MANIFEST, REG_MANIFEST_ROOT, REG_MANIFEST_FILES, rep)}
    rep.sections["MANIFEST_REFRESH"] = out
    return out


def fatal(msg: str) -> None:
    print(f"[run_gates] FATAL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> dict:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                              text=True, timeout=30).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                               text=True, timeout=30).stdout.strip()
        return {"commit": head or "UNKNOWN", "dirty": bool(dirty)}
    except Exception:  # noqa: BLE001 - CI 门不得因 git 缺失而崩
        return {"commit": "UNKNOWN", "dirty": None}


class Report:
    """hard fail 与治理债分账：治理债（号位未裁决）不该让工程门永远红，
    但必须被计数并**只许减少**（棘轮），否则它会变成被忽略的噪音。"""

    def __init__(self) -> None:
        self.hard: list[str] = []
        self.debt: dict[str, int] = {}
        self.info: list[str] = []
        self.sections: dict[str, dict] = {}

    def fail(self, gate: str, msg: str) -> None:
        self.hard.append(f"{gate} {msg}")

    def note(self, msg: str) -> None:
        self.info.append(msg)


# --------------------------------------------------------------------------- #
# CG-1 工件完整性与溯源
# --------------------------------------------------------------------------- #
AUDIT_SCALE_SUFFIXES = ("_1m", "_100k", "_50k", "_10k")


def _resolve_audit_probe(art: Path, prov: dict) -> tuple[Path | None, str]:
    """定位一份审计工件的**own** 探针脚本（显式自述优先，文件名约定兜底）。"""
    rel = prov.get("probe_script")
    if rel:
        cand = REPO / rel
        return (cand, "provenance.probe_script") if cand.exists() else (None, "provenance.probe_script")
    name = art.name
    stem = name[: -len("_result.json")] if name.endswith("_result.json") else art.stem
    for suffix in AUDIT_SCALE_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    cand = art.parent / f"{stem}.py"
    return (cand, "filename_convention") if cand.exists() else (None, "filename_convention")


def cg1_provenance(rep: Report) -> dict:
    out: dict = {"sums_files": 0, "sums_ok": 0, "artifacts": []}
    sums = [REG_EVIDENCE / "SHA256SUMS", ARCH_EVIDENCE / "verify_reconstruction_design_SHA256SUMS"]
    for s in sums:
        if not s.exists():
            rep.fail("CG-1", f"缺少完整性清单：{s.relative_to(REPO)}")
            continue
        for line in s.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            digest, _, rel = line.partition("  ")
            rel = rel.strip()
            out["sums_files"] += 1
            # 清单里的路径可能相对 repo 根，也可能相对清单所在目录
            cands = [REPO / rel, s.parent / rel, s.parent.parent / rel]
            target = next((c for c in cands if c.exists()), None)
            if target is None:
                rep.fail("CG-1", f"清单条目指向不存在的文件：{rel}（in {s.name}）")
                continue
            actual = sha256_file(target)
            if actual != digest.strip():
                rep.fail("CG-1", f"哈希不符：{rel} 期望 {digest[:12]}… 实际 {actual[:12]}…")
            else:
                out["sums_ok"] += 1

    probe_sha = sha256_file(PROBE) if PROBE.exists() else ""
    for art in (ART_1M, ART_CI):
        if not art.exists():
            rep.fail("CG-1", f"缺少探针工件：{art.name}")
            continue
        try:
            raw = art.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            rep.fail("CG-1", f"工件不是合法 UTF-8（疑似被逐字节篡改或截断）：{art.name}: {exc}")
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            rep.fail("CG-1", f"工件不是合法 JSON：{art.name}: {exc}")
            continue
        if not isinstance(data, dict):
            rep.fail("CG-1", f"工件顶层不是 JSON 对象：{art.name}")
            continue
        prov = data.get("provenance") or {}
        rec = {"artifact": art.name, "sha256": sha256_file(art),
               "probe_version": prov.get("probe_version"),
               "script_sha256_in_artifact": prov.get("script_sha256"),
               "script_sha256_actual": probe_sha,
               "scale": prov.get("scale_label"), "ci_scale": prov.get("ci_scale"),
               "all_gates_pass": data.get("all_gates_pass"),
               "gate_count_applicable": data.get("gate_count_applicable"),
               "gates_not_applicable": list((data.get("gates_not_applicable") or {}).keys())}
        out["artifacts"].append(rec)
        if not prov:
            rep.fail("CG-1", f"工件缺 provenance 块（无法溯源）：{art.name}")
            continue
        if prov.get("script_sha256") != probe_sha:
            rep.fail("CG-1", f"溯源断裂：{art.name} 由脚本 {str(prov.get('script_sha256'))[:12]}… 产出，"
                             f"当前脚本为 {probe_sha[:12]}… ⇒ 脚本改动后未重跑，"
                             f"该工件不得作为文档数字来源（铁律 2 第四元）")
        if not data.get("all_gates_pass"):
            rep.fail("CG-1", f"归档工件的门未全绿：{art.name}")
    # 审计工件（as-built 审查）：不要求 all_gates_pass —— 审计探针 exit=1 表示"发现未达标项"，
    # 那是**结论**而不是**门失败**。但溯源必须成立：探针脚本哈希 + 被测源码哈希都要对得上。
    out["audit_artifacts"] = []
    for art in AUDIT_ARTIFACTS:
        if not art.exists():
            rep.fail("CG-1", f"缺少 as-built 审计工件：{art.name}")
            continue
        try:
            data = json.loads(art.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            rep.fail("CG-1", f"审计工件不可解析：{art.name}: {type(exc).__name__}: {exc}")
            continue
        prov = data.get("provenance") or {}
        # 每份审计工件对**它自己那支探针**负责（本轮踩坑：曾把所有审计工件都拿去比
        # M1-017 那支探针的哈希，于是 M1-001R 的工件被误判为"溯源断裂"）。
        # 解析顺序：① provenance.probe_script 显式自述（新探针必须写）；
        #           ② 文件名约定 verify_landed_<mod>[_<scale>]_result.json → verify_landed_<mod>.py
        #              （旧工件没有 probe_script 字段，用约定兜底，避免为了加字段而重跑 1M 档）。
        probe_path, probe_source = _resolve_audit_probe(art, prov)
        if probe_path is None:
            rep.fail("CG-1", f"无法定位审计工件的探针脚本：{art.name}"
                             f"（provenance.probe_script={prov.get('probe_script')!r}，"
                             f"文件名约定也未命中）⇒ 该工件不可溯源")
            continue
        audit_probe_sha = sha256_file(probe_path)
        rec = {"artifact": art.name, "sha256": sha256_file(art),
               "probe_script": str(probe_path.relative_to(REPO)),
               "probe_script_resolved_by": probe_source,
               "probe_version": prov.get("probe_version"),
               "script_sha256_in_artifact": prov.get("script_sha256"),
               "script_sha256_actual": audit_probe_sha,
               "subject": prov.get("subject_under_test"),
               "subject_sha256_in_artifact": prov.get("subject_sha256"),
               "all_gates_pass": data.get("all_gates_pass"),
               "failed_gates": sorted(k for k, v in (data.get("gates") or {}).items() if not v)}
        subj = prov.get("subject_under_test")
        if subj:
            sp = REPO / subj
            rec["subject_sha256_actual"] = sha256_file(sp) if sp.exists() else "MISSING"
            if not sp.exists():
                rep.fail("CG-1", f"审计工件指向的被测源码不存在：{subj}（{art.name}）")
            elif rec["subject_sha256_actual"] != prov.get("subject_sha256"):
                rep.fail("CG-1", f"审计溯源断裂：{subj} 已被修改（工件记 {str(prov.get('subject_sha256'))[:12]}…，"
                                 f"现为 {str(rec['subject_sha256_actual'])[:12]}…）⇒ {art.name} 的实测数不再描述当前代码。"
                                 f"处置：重跑审计探针，或把该工件显式标注为历史运行；**不得**沿用旧数字下结论")
        if prov.get("script_sha256") != audit_probe_sha:
            rep.fail("CG-1", f"审计探针溯源断裂：{art.name} 由 {str(prov.get('script_sha256'))[:12]}… 产出，"
                             f"当前探针 {probe_path.name} 为 {audit_probe_sha[:12]}… ⇒ 探针改动后未重跑")
        out["audit_artifacts"].append(rec)

    rep.sections["CG-1"] = out
    return out


# --------------------------------------------------------------------------- #
# CG-6 派工单交付物存在性门（V3G-003）
# --------------------------------------------------------------------------- #
def cg6_deliverables(rep: Report) -> dict:
    """派发索引自称"唯一派发索引"，就必须与仓库对得上。

    只做两件不需要人类判断的事：① 声明的交付源码是否存在；② 存在的话行数是否 ≥ 下限（防空文件充数）。
    本轮**不阻断**（blocking=false）：当前仓库确有 2 项缺失，直接 hard fail 会让所有其他工作被这道门挡住；
    改为**计数 + 棘轮**（cg6_missing_max），与治理债同一套逻辑 —— 缺失数只许减少，增加即 fail。
    等 3号/4号补齐或注册表改标 NOT_DELIVERED 后，把 blocking 翻成 true。
    """
    if not DISPATCH_REGISTRY.exists():
        rep.note("CG-6 跳过：缺少派工单注册表")
        return {"skipped": True}
    try:
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        base = {}
    cfg = base.get("cg6_deliverables", {})
    min_lines = int(cfg.get("min_lines", 50))
    blocking = bool(cfg.get("blocking", False))
    cap = cfg.get("cg6_missing_max")
    text = DISPATCH_REGISTRY.read_text(encoding="utf-8")
    row_re = re.compile(r"^\|\s*\*\*(\d+号提示词)\*\*\s*\|(.*)$")
    path_re = re.compile(r"`((?:src|tests)/[^`]+\.py)`")
    rows, missing, thin = [], [], []
    for line in text.splitlines():
        m = row_re.match(line.strip())
        if not m:
            continue
        agent, rest = m.group(1), m.group(2)
        for rel in path_re.findall(rest):
            p = REPO / rel
            n = 0
            if p.exists():
                try:
                    n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                except OSError:
                    n = -1
            rec = {"agent": agent, "path": rel, "exists": p.exists(), "lines": n,
                   "min_lines": min_lines}
            rows.append(rec)
            if not p.exists():
                missing.append(f"{agent}:{rel}")
            elif 0 <= n < min_lines:
                thin.append(f"{agent}:{rel}={n}行")
    bad = missing + thin
    if blocking and bad:
        rep.fail("CG-6", f"派工单声明的交付物缺失/过薄：{', '.join(bad)}")
    elif bad:
        rep.note(f"CG-6（非阻断，计数+棘轮）：交付物缺失 {len(missing)} 项、低于 {min_lines} 行 {len(thin)} 项："
                 f"{', '.join(bad)} ⇒ 见 V3G-003")
    if isinstance(cap, int) and len(bad) > cap:
        rep.fail("CG-6", f"交付物缺口棘轮被突破：当前 {len(bad)} > baseline {cap}"
                         f"（缺失数只许减少；补齐交付或把注册表改标 NOT_DELIVERED 后下调 baseline）")
    out = {"registry": str(DISPATCH_REGISTRY.relative_to(REPO)), "declared": len(rows),
           "rows": rows, "missing": missing, "thin": thin, "min_lines": min_lines,
           "blocking": blocking, "cg6_missing_max": cap, "gap_count": len(bad)}
    rep.sections["CG-6"] = out
    return out


# --------------------------------------------------------------------------- #
# CG-2 编号 registry 门 + 治理债棘轮
# --------------------------------------------------------------------------- #
DEBT_KEYS = ("CONFLICT", "UNRATIFIED_SINGLE_CLAIM", "GATE_DISPUTE_OPEN")
HARD_KEYS = ("RULE_A", "UNREGISTERED", "RULE_D")


def cg2_registry(rep: Report) -> dict:
    if not CHECKER.exists():
        rep.fail("CG-2", f"检查器不存在：{CHECKER}")
        return {}
    proc = subprocess.run([sys.executable, str(CHECKER), "--json"], cwd=REPO,
                          capture_output=True, text=True, timeout=300)
    if proc.returncode == 2:
        rep.fail("CG-2", f"检查器环境错误：{proc.stderr.strip()[:400]}")
        return {}
    try:
        res = json.loads(proc.stdout)
    except json.JSONDecodeError:
        rep.fail("CG-2", f"检查器输出不可解析：{proc.stdout[:300]}")
        return {}
    counts = res.get("counts", {})
    for k in HARD_KEYS:
        if counts.get(k, 0) != 0:
            rep.fail("CG-2", f"registry 完整性违规 {k} = {counts[k]}（必须为 0）")
    for k in DEBT_KEYS:
        rep.debt[k] = int(counts.get(k, 0))
    out = {"checker_exit": proc.returncode, "gate": res.get("gate"),
           "registry_version": res.get("registry_version"), "counts": counts,
           "rc_entries": res.get("provisional_rc_ids"), "aliases": res.get("alias_ids"),
           "scope_docs_scanned": res.get("scope_docs_scanned"),
           "open_disputes": res.get("gate_disputes_open", [])}

    if BASELINE.exists():
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        bcounts = base.get("debt_baseline", {})
        ratchet = {}
        for k in DEBT_KEYS:
            b, now = int(bcounts.get(k, 0)), rep.debt[k]
            ratchet[k] = {"baseline": b, "now": now, "delta": now - b}
            if now > b:
                rep.fail("CG-2", f"治理债棘轮被突破：{k} {b} → {now}（只许减少；"
                                 f"新增争用号/新争议必须先裁决再入库）")
        out["ratchet"] = ratchet
        out["baseline_registry_version"] = base.get("registry_version")
    else:
        rep.note("CG-2 无 baseline 文件，棘轮未启用（先跑 --write-baseline）")
    rep.sections["CG-2"] = out
    return out


# --------------------------------------------------------------------------- #
# CG-3 文档 ↔ registry 一致性
# --------------------------------------------------------------------------- #
FENCE_RE = re.compile(r"```.*?```", re.S)
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")


def split_citations(text: str) -> tuple[str, list[str]]:
    """把文档分成"断言性正文"与"字面量提及"（代码块/行内代码）。

    与 registry 检查器规则 B 的同一纪律：只有**断言位**的号才要求已注册；
    代码跨度里的号是字面量（例如负向自测表里引用的不存在号 `RC-099`）。
    字面量里的**未注册号**必须出现在 baseline 的 `quoted_label_allowlist` 并附理由，
    否则仍然 fail —— 允许清单在 baseline 里，而 baseline 进 SHA256SUMS，扩容必然在 diff 中可见。
    """
    quoted: list[str] = []
    for m in list(FENCE_RE.finditer(text)) + list(CODE_SPAN_RE.finditer(text)):
        quoted.extend(f"RC-{g}" for g in RC_RE.findall(m.group(0)))
    masked = FENCE_RE.sub(lambda m: " " * len(m.group(0)), text)
    masked = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), masked)
    return masked, quoted


def cg3_doc_registry(rep: Report) -> dict:
    if not (REGISTRY.exists() and BOOK.exists()):
        rep.fail("CG-3", "registry 或设计书缺失")
        return {}
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        text = BOOK.read_text(encoding="utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        rep.fail("CG-3", f"registry 或设计书不可解析：{type(exc).__name__}: {exc}")
        return {}
    base_doc = None
    if BASELINE.exists():
        try:
            base_doc = json.loads(BASELINE.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            rep.fail("CG-3", f"baseline 不可解析（无法核对字面量允许清单）：{exc}")
    rc_entries = {i["id"]: i for i in reg["issues"] if i.get("namespace") == "RC"}
    aliases: dict[str, str] = {}
    for i in reg["issues"]:
        for a in i.get("aliases") or []:
            aliases[a] = i["id"]
    by_id = {i["id"]: i for i in reg["issues"]}

    masked, quoted = split_citations(text)
    cited = sorted({f"RC-{m}" for m in RC_RE.findall(masked)})
    unknown = [c for c in cited if c not in rc_entries and c not in aliases]
    for u in unknown:
        rep.fail("CG-3", f"设计书在**断言位**引用了 registry 中不存在的临时号：{u}"
                         f"（文档只能引用号，不能分配号 —— §9.3 R2）")
    allow = (base_doc.get("quoted_label_allowlist", {}) if base_doc else {})
    quoted_unknown = sorted({q for q in quoted
                             if q not in rc_entries and q not in aliases})
    for q in quoted_unknown:
        if q in allow:
            rep.note(f"CG-3 字面量提及未注册号 {q}（允许清单理由：{allow[q]}）")
        else:
            rep.fail("CG-3", f"设计书在字面量中提及未注册号 {q}，且不在 baseline 的 "
                             f"quoted_label_allowlist 中 ⇒ 要么注册/登记 alias，要么显式登记理由")
    unref = [r for r in sorted(rc_entries) if r not in text]
    for u in unref:
        rep.fail("CG-3", f"registry 条目在设计书中从未出现（孤儿号）：{u}")
    unref_alias = [a for a in sorted(aliases) if a not in text]
    for a in unref_alias:
        rep.fail("CG-3", f"registry alias 在设计书中从未出现（孤儿 alias）：{a}")

    # slug 与门位逐字核对：从设计书 §3.3 表格行解析
    row_re = re.compile(r"^\|\s*\*\*(RC-\d{3})\*\*\s*\|\s*`([^`]+)`\s*\|")
    gate_re = re.compile(r"^### (Gate\s*[0-9.]+(?:~[0-9.]+)?)")
    gate = None
    mismatches = []
    for line in text.splitlines():
        gm = gate_re.match(line)
        if gm:
            gate = gm.group(1).replace(" ", "")
        m = row_re.match(line)
        if not m:
            continue
        rid, slug = m.group(1), m.group(2)
        entry = rc_entries.get(rid)
        if entry is None:
            # alias：设计书表格里以 RC 标签出现，registry 中登记在 owner 上
            owner = aliases.get(rid)
            if owner is None:
                mismatches.append(f"{rid} 既非 RC 条目也非 alias")
                continue
            o = by_id[owner]
            if slug != o.get("slug"):
                mismatches.append(f"{rid}(alias→{owner}) slug 不一致：文档 {slug!r} vs registry {o.get('slug')!r}")
            disputes = {d.get("proposed_gate") for d in (o.get("gate_disputes") or [])}
            if gate and o.get("gate") and gate != o["gate"] and gate not in disputes:
                mismatches.append(f"{rid}(alias→{owner}) 门位不一致且未登记 gate_disputes："
                                  f"文档 {gate} vs registry {o['gate']}")
            continue
        if slug != entry.get("slug"):
            mismatches.append(f"{rid} slug 不一致：文档 {slug!r} vs registry {entry.get('slug')!r}")
        if gate and entry.get("gate") != gate:
            mismatches.append(f"{rid} 门位不一致：文档 {gate} vs registry {entry.get('gate')!r}")
    for m in mismatches:
        rep.fail("CG-3", m)

    out = {"rc_cited_in_assert_position": len(cited), "rc_entries": len(rc_entries),
           "aliases": len(aliases), "slug_or_gate_mismatches": len(mismatches),
           "unknown_labels": unknown, "orphan_entries": unref + unref_alias,
           "quoted_labels": len(set(quoted)), "quoted_unknown_labels": quoted_unknown,
           "quoted_allowlist_size": len(allow)}
    rep.sections["CG-3"] = out
    return out


# --------------------------------------------------------------------------- #
# CG-4 探针 CI 档实跑
# --------------------------------------------------------------------------- #
ALLOWED_NA = {"G2b_rejected_plans_over_gate_at_scale"}


def cg4_probe(rep: Report, scale: str, skip: bool) -> dict:
    if skip:
        rep.note("CG-4 跳过（--skip-probe）：本次运行不为探针门作证")
        return {"skipped": True}
    if not PROBE.exists():
        rep.fail("CG-4", f"探针不存在：{PROBE}")
        return {}
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "ci.sqlite3")
        js = os.path.join(td, "ci.json")
        t0 = time.time()
        proc = subprocess.run([sys.executable, str(PROBE), "--scale", scale, "--db", db,
                               "--json", js], cwd=REPO, capture_output=True, text=True,
                              timeout=1800)
        wall = round(time.time() - t0, 1)
        if proc.returncode != 0:
            rep.fail("CG-4", f"探针 {scale} 档 exit={proc.returncode}（门未全绿）")
        if not Path(js).exists():
            rep.fail("CG-4", f"探针未产出 JSON 工件（stdout 尾部：{proc.stdout[-300:]}）")
            return {"scale": scale, "wall_s": wall, "exit": proc.returncode}
        data = json.loads(Path(js).read_text(encoding="utf-8"))

    gates = data.get("gates", {})
    na = data.get("gates_not_applicable", {}) or {}
    failed = sorted(k for k, v in gates.items() if v is not True)
    for k in failed:
        rep.fail("CG-4", f"探针门失败：{k}")
    illegal_na = sorted(set(na) - ALLOWED_NA)
    for k in illegal_na:
        rep.fail("CG-4", f"探针把不允许 N/A 的门标成了不适用（绕过嫌疑）：{k}")
    if scale in ("1m",) and na:
        rep.fail("CG-4", f"1M 档不应有任何 N/A 门：{sorted(na)}")

    # I7 非空转复核：绿灯必须建立在"确实测到了东西"之上
    v2, v3, v7 = data["v2_co_search"], data["v3_time_slider"], data["v7_pipeline"]
    vacuous = []
    if v2["two_char_term_recall"]["postings"] <= 0:
        vacuous.append("2 字中文词召回为 0")
    if v3["scan_occurred_at_month_window"]["rows"] <= 0:
        vacuous.append("月窗扫描 0 行")
    if v7["claims"]["after_retry"] != v7["claims_expected_total"]:
        vacuous.append(f"Claim {v7['claims']['after_retry']} ≠ 期望 {v7['claims_expected_total']}")
    if v7["claims"]["before_retry"] >= v7["claims"]["after_retry"]:
        vacuous.append("重试没有补齐任何 Claim（幂等断言空转嫌疑）")
    if v2["fts5_raw_unicode61_AS_BUILT"]["hits"] != 0:
        rep.note(f"CG-4 注意：裸 FTS5 本次命中 {v2['fts5_raw_unicode61_AS_BUILT']['hits']} ≠ 0，"
                 f"与设计书 §1.2 的静默零召回结论不符 ⇒ 必须复核分词器/SQLite 版本")
    for v in vacuous:
        rep.fail("CG-4", f"非空转断言失败（I7）：{v}")

    prov = data.get("provenance", {})
    if prov.get("script_sha256") != sha256_file(PROBE):
        rep.fail("CG-4", "本次运行的 provenance.script_sha256 与脚本哈希不符（不应发生）")

    out = {"scale": scale, "exit": proc.returncode, "wall_s": wall,
           "gates_applicable": len(gates), "gates_failed": failed,
           "gates_not_applicable": sorted(na),
           "db_size_mb": data.get("schema", {}).get("db_size_mb"),
           "python": platform.python_version(), "sqlite": data.get("environment", {}).get("sqlite"),
           "probe_version": prov.get("probe_version"),
           "non_vacuous_checked": ["two_char_recall", "month_window_rows",
                                   "claims_equals_expected", "retry_actually_filled"],
           "vacuous_findings": vacuous}
    rep.sections["CG-4"] = out
    return out


# --------------------------------------------------------------------------- #
# CG-5 数字可追溯（工件 → 文档）+ 旧值回潮防护
# --------------------------------------------------------------------------- #
def flatten(o, pre="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            flatten(v, f"{pre}.{k}", out)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        out[pre] = o
    return out


def cg5_traceability(rep: Report) -> dict:
    if not (ART_1M.exists() and BOOK.exists() and BASELINE.exists()):
        rep.note("CG-5 跳过：缺少 1M 工件 / 设计书 / baseline")
        return {"skipped": True}
    try:
        base_doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        rep.fail("CG-5", f"baseline 不可解析：{exc}")
        return {"skipped": True, "reason": "baseline_unreadable"}
    try:
        data = json.loads(ART_1M.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        rep.fail("CG-5", f"1M 工件不可读/不可解析（无法做数字追溯）：{type(exc).__name__}: {exc}")
        return {"skipped": True, "reason": "artifact_unreadable"}
    try:
        text = BOOK.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        rep.fail("CG-5", f"设计书不可读：{exc}")
        return {"skipped": True, "reason": "book_unreadable"}
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    exemptions = base.get("citation_exemptions", {})
    exempt_keys = set(exemptions.get("key_suffixes", []))
    facts = flatten(data)
    uncited = []
    for k, v in facts.items():
        if any(k.endswith(s) or f".{s}." in k for s in exempt_keys):
            continue
        cands = {str(v)}
        if isinstance(v, float):
            cands |= {f"{v:.3f}".rstrip("0").rstrip("."), f"{v:,.1f}", f"{v:,}", f"{v:.1f}",
                      f"{v / 1000:.1f} s"}
        if isinstance(v, int) and v > 999:
            cands |= {f"{v:,}", f"{v / 10000:.0f} 万", f"{v / 1000000:.0f}M"}
        if not any(c in text for c in cands):
            uncited.append(f"{k} = {v}")
    if uncited:
        rep.fail("CG-5", f"1M 工件中有 {len(uncited)} 个数值事实未在设计书中被引用"
                         f"（文档与工件脱节）：{'; '.join(uncited[:8])}")

    # 旧运行值只允许出现在显式哨兵区域内（§3.7.2 漂移披露表）；区域外的出现 = 数字回潮
    HIST_B, HIST_E = "<!-- HISTORICAL-RUN-VALUES:BEGIN", "<!-- HISTORICAL-RUN-VALUES:END -->"
    outside, hist_chars, regions = text, 0, 0
    while HIST_B in outside:
        b = outside.index(HIST_B)
        e = outside.index(HIST_E, b) + len(HIST_E)
        hist_chars += e - b
        regions += 1
        outside = outside[:b] + outside[e:]
    if regions == 0:
        rep.fail("CG-5", "设计书缺少 HISTORICAL-RUN-VALUES 哨兵区域 ⇒ 无法区分'漂移披露'与'数字回潮'")
    if hist_chars > 0.05 * len(text):
        rep.fail("CG-5", f"哨兵区域占全文 {hist_chars / len(text):.1%} > 5% ⇒ 疑似用哨兵掩盖回潮")
    stale = []
    for s in base.get("superseded_values", []):
        if s in outside:
            stale.append(s)
    if stale:
        rep.fail("CG-5", f"设计书正文出现已被取代的旧运行值（数字回潮）：{', '.join(stale[:10])}"
                         f" ⇒ 必须重跑 --write-baseline 前先核对工件")
    out = {"facts_in_artifact": len(facts), "uncited": len(uncited),
           "uncited_list": uncited[:20], "superseded_values_checked":
               len(base.get("superseded_values", [])), "stale_found": stale,
           "historical_regions": regions, "historical_region_chars": hist_chars,
           "historical_region_share": round(hist_chars / max(len(text), 1), 4)}
    rep.sections["CG-5"] = out
    return out


# --------------------------------------------------------------------------- #
# PROVENANCE.json 生成
# --------------------------------------------------------------------------- #
def write_provenance(rep: Report) -> dict:
    arts = []
    for d in (ARCH_EVIDENCE, REG_EVIDENCE):
        for f in sorted(d.iterdir()):
            # PROVENANCE.json 是**派生索引**且含 git 状态字段 ⇒ 不参与自身列举，也不进 SHA256SUMS
            if f.name in {"PROVENANCE.json"} or f.name.startswith("gate_run_"):
                continue
            if f.is_file() and f.suffix in {".json", ".log", ".py"}:
                rec = {"path": str(f.relative_to(REPO)), "sha256": sha256_file(f),
                       "bytes": f.stat().st_size}
                if f.suffix == ".json":
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        prov = data.get("provenance") if isinstance(data, dict) else None
                        if prov:
                            rec["produced_by"] = {
                                "probe_version": prov.get("probe_version"),
                                "script_sha256": prov.get("script_sha256"),
                                "scale": prov.get("scale_label"),
                                "ci_scale": prov.get("ci_scale"),
                                "gate_applicability": prov.get("gate_applicability"),
                            }
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        rec["unreadable"] = True
                arts.append(rec)
    doc = {
        "generated_by": "governance/ci/run_gates.py",
        # 刻意不写时间戳：本文件要被 SHA256SUMS 哈希，内容必须对同一仓库状态**字节稳定**
        "git": git_head(),
        "rule": ("引用任何数字前先核 script_sha256 与本文件登记值一致；不一致 ⇒ 按统一母表 §9.4 "
                 "降级为『可复现但未取证』，不得写进 Issue 验收。脚本改动后旧工件即失去溯源，"
                 "必须重跑或显式标注为历史运行。"),
        "git_field_semantics": ("git.commit 是**生成本文件时**的 HEAD，git.dirty 表示当时工作区是否有未提交改动；"
                               "入库的 PROVENANCE.json 因此通常记录的是"
                               "『产出这批工件时所在的那个 commit + dirty=true』，CI 每次运行都会重写本文件"
                               "（本文件是派生索引，刻意不进 SHA256SUMS，见 run_gates.py 的清单策略注释）"),
        "scripts": {"probe": {"path": str(PROBE.relative_to(REPO)), "sha256": sha256_file(PROBE)},
                    "registry_checker": {"path": str(CHECKER.relative_to(REPO)),
                                         "sha256": sha256_file(CHECKER)}},
        "book": {"path": str(BOOK.relative_to(REPO)), "sha256": sha256_file(BOOK)},
        "registry": {"path": str(REGISTRY.relative_to(REPO)), "sha256": sha256_file(REGISTRY),
                     "version": json.loads(REGISTRY.read_text(encoding='utf-8')).get("registry_version")},
        "artifacts": arts,
    }
    out_path = ARCH_EVIDENCE / "PROVENANCE.json"
    new_bytes = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    changed = (not out_path.exists()) or out_path.read_bytes() != new_bytes
    out_path.write_bytes(new_bytes)
    doc["_self_sha256"] = hashlib.sha256(new_bytes).hexdigest()
    doc["_changed_this_run"] = changed
    rep.sections["PROVENANCE"] = {"written": str(out_path.relative_to(REPO)),
                                 "artifacts_bound": len(arts),
                                 "self_sha256": doc["_self_sha256"],
                                 "changed_this_run": changed}
    return doc


def write_baseline(rep: Report) -> None:
    doc = {
        "written_by": "governance/ci/run_gates.py --write-baseline",
        "written_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": git_head(),
        "registry_version": rep.sections.get("CG-2", {}).get("registry_version"),
        "debt_baseline": rep.debt,
        "hard_gates_must_be_zero": list(HARD_KEYS),
        "note": ("治理债 = 号位未裁决造成的 CONFLICT/UNRATIFIED/gate 争议。棘轮规则：只许减少。"
                 "本文件只能由人工在裁决后重写，且必须附裁决依据。"),
        "citation_exemptions": {
            "key_suffixes": ["p50", "p50_ms", "note", "changelog", "wall_ms", "objects",
                            "insert_and_index_ms", "analyze_ms"],
            "reason": ("p50/note/wall 属运行环境量，不进入设计书正文；objects 在正文写作『1M/100 万』；"
                       "构建耗时以四舍五入形式引用（如 57.7 s）"),
        },
        "superseded_values": [
            "2181.75", "247.068", "678.2", "9.054", "306.752", "210.428", "147.246",
            "154.343", "5.656", "169.403", "84.9×", "0.081", "1086.0", "3.516", "308.9",
            "181,812", "741×", "218%", "13/13 门", "52.6 s", "111.5 s",
        ],
    }
    BASELINE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rep.note(f"baseline 已写入 {BASELINE.relative_to(REPO)}（治理债 = {rep.debt}）")


def main() -> int:
    ap = argparse.ArgumentParser(description="治理与证据 CI 门（PROBE-CI-002 / SPINE-EVIDENCE）")
    ap.add_argument("--scale", default="100k", choices=["50k", "100k", "200k", "1m"])
    ap.add_argument("--skip-probe", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--no-provenance-write", action="store_true")
    ap.add_argument("--refresh-manifest", action="store_true",
                    help="按当前仓库状态重算 SHA256SUMS（人工动作；CI 只做校验）")
    args = ap.parse_args()

    for f in (REGISTRY, CHECKER, PROBE, BOOK, ART_1M):
        if not f.exists():
            fatal(f"缺少必需文件：{f}")

    rep = Report()
    t0 = time.time()
    if args.refresh_manifest:
        refresh_manifest(rep)
    cg1_provenance(rep)
    cg2_registry(rep)
    cg3_doc_registry(rep)
    cg4_probe(rep, args.scale, args.skip_probe)
    if args.write_baseline:
        write_baseline(rep)
    cg5_traceability(rep)
    cg6_deliverables(rep)
    if not args.no_provenance_write:
        write_provenance(rep)
    wall = round(time.time() - t0, 1)

    result = {
        "runner": "governance/ci/run_gates.py",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {"python": platform.python_version(), "sqlite": __import__("sqlite3").sqlite_version,
                        "platform": platform.platform(), "cpu_count": os.cpu_count()},
        "git": git_head(),
        "wall_s": wall,
        "hard_failures": rep.hard,
        "governance_debt": rep.debt,
        "notes": rep.info,
        "sections": rep.sections,
        "verdict": "PASS" if not rep.hard else "FAIL",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        print(text)
    else:
        print("=" * 78)
        print(f"治理与证据 CI 门  |  python {platform.python_version()} / wall {wall} s")
        print("=" * 78)
        print(f"CG-1 工件溯源 : {rep.sections.get('CG-1', {}).get('sums_ok', 0)}/"
              f"{rep.sections.get('CG-1', {}).get('sums_files', 0)} 哈希核对通过；"
              f"{len(rep.sections.get('CG-1', {}).get('artifacts', []))} 个设计探针工件 + "
              f"{len(rep.sections.get('CG-1', {}).get('audit_artifacts', []))} 份 as-built 审计工件"
              f"（探针哈希 + 被测源码哈希双向溯源）已核对")
        c2 = rep.sections.get("CG-2", {})
        print(f"CG-2 编号门   : checker={c2.get('gate')} registry={c2.get('registry_version')} "
              f"RC 条目 {c2.get('rc_entries')} / alias {c2.get('aliases')}")
        print(f"                治理债 CONFLICT={rep.debt.get('CONFLICT')} "
              f"UNRATIFIED={rep.debt.get('UNRATIFIED_SINGLE_CLAIM')} "
              f"GATE_DISPUTE={rep.debt.get('GATE_DISPUTE_OPEN')}（棘轮：只许减少）")
        c3 = rep.sections.get("CG-3", {})
        print(f"CG-3 文档↔registry : 断言位引用 {c3.get('rc_cited_in_assert_position')} 个 RC 标签"
              f"（字面量 {c3.get('quoted_labels')} 个，其中未注册 {len(c3.get('quoted_unknown_labels', []))} 个走允许清单）/ "
              f"registry {c3.get('rc_entries')} 条 + {c3.get('aliases')} alias / "
              f"slug或门位不符 {c3.get('slug_or_gate_mismatches')}")
        c4 = rep.sections.get("CG-4", {})
        if c4.get("skipped"):
            print("CG-4 探针     : 已跳过")
        else:
            print(f"CG-4 探针     : {c4.get('scale')} 档 exit={c4.get('exit')} "
                  f"适用门 {c4.get('gates_applicable')} 失败 {len(c4.get('gates_failed', []))} "
                  f"N/A {c4.get('gates_not_applicable')} wall {c4.get('wall_s')} s")
        c5 = rep.sections.get("CG-5", {})
        print(f"CG-5 数字追溯 : 工件事实 {c5.get('facts_in_artifact')} 未引用 {c5.get('uncited')}；"
              f"旧值回潮 {len(c5.get('stale_found', []))}")
        print("-" * 78)
        print(f"VERDICT = {result['verdict']}   hard failures = {len(rep.hard)}")
        for h in rep.hard:
            print(f"  ✗ {h}")
        for n in rep.info:
            print(f"  · {n}")
    CI_EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M%S", time.gmtime())
    (CI_EVIDENCE / f"gate_run_{stamp}.json").write_text(text + "\n", encoding="utf-8")
    return 0 if not rep.hard else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CI 门必须给可读错误而非 traceback
        fatal(f"{type(exc).__name__}: {exc}")
