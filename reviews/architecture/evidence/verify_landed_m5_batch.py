#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M5 批次（Agent-06~10 五张工单）as-built 硬门禁探针 v1.0.0。

被审对象
--------
`origin/aios-2.0` 快照（单个孤儿提交 `582e187`）上的：
  · `src/aios_core/query/search.py`                （#6 M5-001 多维检索总线）
  · `src/aios_core/cognition/operation_experience.py`（#6 三路径对比执行器 + 经验蒸馏）
  · `src/aios_core/cognition/dimension_engine.py`   （#7 M5-002 三重门槛与高阶提炼）
  · `src/aios_core/cognition/self_reflection.py`    （#8 M5-003 镜面/羁绊/姿态）
  · `src/aios_core/cognition/symbiotic_advisor.py`  （#9 M5-004 共生决策推演）
  · `src/aios_core/simulation/massive_life_bench.py`（#10 M5-005 战训考场）
  · `docs/specifications/TASK_PROGRESS_V3.md`       （台账 CLOSED 声称）

为什么需要这个探针
------------------
台账把 #7/#8/#9 记为 `CLOSED (n/n PASS)`，主干全量套件 **1109 passed** 也确实为真。
但"测试全绿"与"工单硬门禁成立"是两件事：本探针不看测试是否通过，而是**按工单原文的断言逐条实测**——
优先用行为实验（构造输入、观察输出），结构性判据用 AST（不用正则，见 V3G-014 的假阴性教训）。

用法
----
    PYTHONPATH=<repo>/src python3 verify_landed_m5_batch.py --repo-root /tmp/trunk \
        --json OUT.json --log OUT.log

本探针 **fail-closed**：被审模块缺失 ⇒ exit=2 并明说"本 checkout 不含 M5 代码"，绝不静默判过。
退出码：0 = 全部门成立；1 = 有门不成立；2 = 被审对象缺失/环境不可用。
只用标准库 + pydantic（被审模块自身依赖）。
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import traceback
from typing import Any, Callable

TOOL_VERSION = "1.2.0"
SUBJECT_FILES = (
    "src/aios_core/query/search.py",
    "src/aios_core/cognition/operation_experience.py",
    "src/aios_core/cognition/dimension_engine.py",
    "src/aios_core/cognition/self_reflection.py",
    "src/aios_core/cognition/symbiotic_advisor.py",
    "src/aios_core/simulation/massive_life_bench.py",
    "tests/cognition/test_dimension_lifecycle.py",
    "tests/cognition/test_operation_experience.py",
    "tests/cognition/test_self_reflection.py",
    "tests/cognition/test_symbiotic_advisor.py",
    "docs/specifications/TASK_PROGRESS_V3.md",
)


# ------------------------------------------------------------------ 基础设施
class Gate:
    def __init__(self, gid: str, order: str, title: str, requirement: str):
        self.gid, self.order, self.title, self.requirement = gid, order, title, requirement
        self.verdict = "NOT_RUN"
        self.measured: dict[str, Any] = {}
        self.note = ""

    def ok(self, **measured):
        self.verdict, self.measured = "PASS", measured
        return self

    def fail(self, note: str, **measured):
        self.verdict, self.note, self.measured = "FAIL", note, measured
        return self

    def na(self, note: str, **measured):
        self.verdict, self.note, self.measured = "N/A", note, measured
        return self

    def as_dict(self):
        return {"gate_id": self.gid, "order": self.order, "title": self.title,
                "requirement": self.requirement, "verdict": self.verdict,
                "measured": self.measured, "note": self.note}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(root: pathlib.Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def load_module(root: pathlib.Path, dotted: str):
    """按路径加载被审模块（避免把探针自身所在树误当被审对象）。"""
    import importlib.util
    rel = dotted.replace(".", "/") + ".py"
    path = root / "src" / rel
    spec = importlib.util.spec_from_file_location(dotted, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod


def parse(root: pathlib.Path, rel: str) -> ast.AST:
    return ast.parse((root / rel).read_text(encoding="utf-8"))


def funcs(tree: ast.AST, class_name: str | None = None) -> list[ast.FunctionDef]:
    out = []
    nodes = tree.body if class_name is None else [
        n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == class_name
        for n in c.body]
    for n in nodes:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(n)
        elif isinstance(n, ast.ClassDef) and class_name is None:
            out.extend(m for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return out


def unused_imports(tree: ast.AST) -> list[str]:
    imported: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                imported[a.asname or a.name] = f"{n.module}.{a.name}"
        elif isinstance(n, ast.Import):
            for a in n.names:
                imported[(a.asname or a.name).split(".")[0]] = a.name
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            cur = n
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name):
                used.add(cur.id)
    return sorted(k for k in imported if k not in used and k != "annotations")


# ------------------------------------------------------- Agent-06 / M5-001
def g06a_pathway_executor(root, gates):
    g = Gate("G06a", "Agent-06", "三大检索路径对比执行器是否存在",
             "工单：实现 Pathway A 暴力扫描 / B 朴素关键词 / C 拓扑分级下钻 的**对比执行器**")
    tree = parse(root, "src/aios_core/cognition/operation_experience.py")
    classes = [c.name for c in tree.body if isinstance(c, ast.ClassDef)]
    # 判据：是否存在一个可调用体，内部**按路径分支实际执行检索**（调用检索 API 或全量迭代）
    executors = []
    for fn in funcs(tree):
        body_src = ast.unparse(fn)
        branches_on_pathway = "PathwayType.BRUTE_FORCE_SCAN" in body_src and "PathwayType.KEYWORD_SEARCH" in body_src
        calls_retrieval = bool(re.search(r"\.(co_search|search_mind|search_by_\w+)\(", body_src)) or "for obj in" in body_src
        if branches_on_pathway and calls_retrieval:
            executors.append(fn.name)
    # 全 src 范围再扫一遍（执行器可能落在别的模块）
    hits_elsewhere = []
    for p in sorted((root / "src").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        try:
            t = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for fn in funcs(t):
            src = ast.unparse(fn)
            if "BRUTE_FORCE_SCAN" in src and "KEYWORD_SEARCH" in src and "HIERARCHICAL_TOPO" in src:
                hits_elsewhere.append(f"{p.relative_to(root)}::{fn.name}")
    if executors or hits_elsewhere:
        return g.ok(executors=executors, hits_elsewhere=hits_elsewhere)
    return g.fail(
        "全 src 树中不存在任何按三条路径分支并实际执行检索的函数；只有 PathwayType 枚举 + 回执/策略模型 + 蒸馏器。"
        "⇒ 三条路径从未被真正执行过，工单要求的『对比执行器』缺失。",
        classes_in_operation_experience=classes, executors_found=0,
        enum_only=True)


def g06b_unused_imports(root, gates):
    g = Gate("G06b", "Agent-06", "执行力缺失的旁证：导入却从未使用的执行机器",
             "工单铁律：严禁占位符")
    tree = parse(root, "src/aios_core/cognition/operation_experience.py")
    un = unused_imports(tree)
    critical = [x for x in un if x in {"WorldOperatorSuite", "estimate_token_count",
                                       "OperationRequest", "new_operation_id", "SourceClass"}]
    if critical:
        return g.fail(
            f"导入了真正执行/计量所需的机器却从未使用：{critical} ⇒ 执行器是计划中而未落笔的强旁证。",
            unused_imports=un, critical_unused=critical, unused_count=len(un))
    return g.ok(unused_imports=un, critical_unused=[], unused_count=len(un))


def g06c_prior_numbers(root, gates):
    g = Gate("G06c", "Agent-06", "『≤500 Token / 准确率 100%』是实测还是声明",
             "工单：将 Token 由 15,000~50,000 压缩至 500 以内，准确率 100%")
    try:
        oe = load_module(root, "aios_core.cognition.operation_experience")
        store_mod = load_module(root, "aios_core.storage.sqlite_store")
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "probe.sqlite3"
            store = store_mod.SQLiteWorldStore(db_path=db) if "db_path" in store_mod.SQLiteWorldStore.__init__.__code__.co_varnames else store_mod.SQLiteWorldStore(db)
            d = oe.OperationExperienceDistiller(store)
            prior = d.distill_for_intent("探针意图：无任何实测回执")
            res = {"expected_tokens": prior.expected_tokens,
                   "expected_accuracy": prior.expected_accuracy,
                   "expected_latency_ms": prior.expected_latency_ms,
                   "sample_size": prior.sample_size,
                   "preferred_pathway": str(prior.preferred_pathway)}
        if prior.sample_size == 1 and res["expected_tokens"] == 350 and res["expected_accuracy"] == 1.0:
            return g.fail(
                "在**零实测回执**的情况下，蒸馏器直接返回 expected_tokens=350 / accuracy=1.0 / latency=25.0，"
                "并把它作为 sample_size=1 的『经验』持久化入库 ⇒ 台账与测试里那个 ≤500 Token、100% 准确率"
                "来自代码常量，不是任何一次真实检索的测量值。", **res)
        return g.ok(**res)
    except Exception as exc:
        return g.fail(f"探针执行异常（不得视为通过）：{type(exc).__name__}: {exc}",
                      error=traceback.format_exc(limit=3))


def g06d_search_bus(root, gates):
    g = Gate("G06d", "Agent-06", "多维检索总线四大维度是否真实存在（工单前提核对）",
             "工单前提：主干已同步 MultidimensionalSearchEngine，原生支持 Dimension/Claim/Entity/Annotation 联合检索")
    tree = parse(root, "src/aios_core/query/search.py")
    classes = [c.name for c in tree.body if isinstance(c, ast.ClassDef)]
    methods = {m.name for m in funcs(tree, "WorldSearchIndex")}
    need = {"search_by_dimension", "search_by_claim", "search_by_entity", "search_by_annotation"}
    have = sorted(need & methods)
    named_as_claimed = "MultidimensionalSearchEngine" in classes
    if len(have) == 4:
        g.ok(bus_class=[c for c in classes if "Index" in c or "Search" in c],
             four_dimension_methods=have,
             class_named_MultidimensionalSearchEngine=named_as_claimed,
             note="能力存在但类名与工单声称不符" if not named_as_claimed else "")
        g.note = ("四大维度检索方法齐备（能力真实存在）；但工单声称的类名 MultidimensionalSearchEngine "
                  "在全仓库不存在，实际类为 WorldSearchIndex ⇒ 工单前提表述与代码不符（不影响能力成立）。"
                  if not named_as_claimed else "")
        return g
    return g.fail(f"四大维度方法缺失：需要 {sorted(need)}，实得 {have}",
                  four_dimension_methods=have, classes=classes)


# ------------------------------------------------------- Agent-07 / M5-002
def _mk_dimension_env(root):
    de = load_module(root, "aios_core.cognition.dimension_engine")
    import datetime as dt
    return de, dt


def g07a_prediction_accuracy(root, gates):
    g = Gate("G07a", "Agent-07", "门槛二：30 天试用期内预测准确率 ≥70%",
             "工单：候选维度必须在 30 天内提供连续认知解释力与成功预测（Prediction 准确率 ≥70%），否则自动失效")
    de, dt = _mk_dimension_env(root)
    sm = de.DimensionLifecycleStateMachine()
    t0 = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone.utc)
    # 门槛一：连续 3 天、跨 2 个物理域
    for day in range(3):
        sm.detector.add_event(de.AnomalyEvent(timestamp=t0 + dt.timedelta(days=day), domain="sleep", description="睡眠异常"))
        sm.detector.add_event(de.AnomalyEvent(timestamp=t0 + dt.timedelta(days=day), domain="cardio", description="血压异常"))
    sm.propose_dimension("DIM_PROBE", t0 + dt.timedelta(days=2, hours=1))
    # 31 天后：1 次成功 + 9 次失败 ⇒ 准确率 10%
    for i in range(10):
        sm.reflect_and_validate("DIM_PROBE", t0 + dt.timedelta(days=3 + i * 3), successful_prediction=(i == 0))
    t_late = t0 + dt.timedelta(days=35)
    try:
        sm.attempt_register("DIM_PROBE", t_late)
        registered = sm.dimensions["DIM_PROBE"].status.name
    except Exception as exc:
        return g.ok(rejected=True, exception=type(exc).__name__, accuracy=0.1)
    if registered == "REGISTERED":
        return g.fail(
            "准确率 10%（1 成功 / 9 失败）的候选维度在 31 天后被**放行注册为 REGISTERED**。"
            "源码判据是 `predictions_validated <= 0` 才拒绝 ⇒ 实际门槛是『至少成功过 1 次』，"
            "工单要求的 ≥70% 准确率**未实现**。",
            accuracy=0.1, successes=1, attempts=10, final_status=registered,
            source_predicate="predictions_validated <= 0")
    return g.ok(rejected=True, final_status=registered, accuracy=0.1)


def g07b_expired_state(root, gates):
    g = Gate("G07b", "Agent-07", "门槛二：未达标自动失效 EXPIRED",
             "工单：30 天内未达标 ⇒ 自动失效（EXPIRED）")
    de, dt = _mk_dimension_env(root)
    members = [s.name for s in de.DimensionStatus]
    has_expired = "EXPIRED" in members
    # 是否存在任何自动失效推进逻辑
    tree = parse(root, "src/aios_core/cognition/dimension_engine.py")
    src = "\n".join(ast.unparse(f) for f in funcs(tree))
    auto_expire = bool(re.search(r"(expire|EXPIRED|失效)", src))
    if has_expired and auto_expire:
        return g.ok(status_members=members, auto_expire_logic=True)
    return g.fail(
        f"DimensionStatus 枚举成员 = {members}，**没有 EXPIRED**；且全模块无任何自动失效推进逻辑。"
        "⇒ 工单要求的『30 天未达标自动失效』完全缺失：不达标的候选维度会永久停留在 CANDIDATE。",
        status_members=members, has_EXPIRED=has_expired, auto_expire_logic=auto_expire)


def g07c_quota_error_type(root, gates):
    g = Gate("G07c", "Agent-07", "门槛三：每日反思配额 1 次，超额抛 QuotaExceededBlockError",
             "工单：超额直接抛出 QuotaExceededBlockError")
    de, dt = _mk_dimension_env(root)
    has_type = hasattr(de, "QuotaExceededBlockError")
    sm = de.DimensionLifecycleStateMachine()
    t0 = dt.datetime(2026, 3, 1, 9, 0, tzinfo=dt.timezone.utc)
    for day in range(3):
        sm.detector.add_event(de.AnomalyEvent(timestamp=t0 + dt.timedelta(days=day), domain="sleep", description="x"))
        sm.detector.add_event(de.AnomalyEvent(timestamp=t0 + dt.timedelta(days=day), domain="bill", description="y"))
    sm.propose_dimension("DIM_Q", t0 + dt.timedelta(days=2))
    same_day = t0 + dt.timedelta(days=2, hours=3)
    sm.reflect_and_validate("DIM_Q", same_day, successful_prediction=True)
    raised = None
    try:
        sm.reflect_and_validate("DIM_Q", same_day + dt.timedelta(hours=1), successful_prediction=True)
    except Exception as exc:
        raised = type(exc).__name__
    if raised is None:
        return g.fail("同日第二次反思**未被拒绝**（配额未生效）", second_reflection_blocked=False,
                      exception_type=None, QuotaExceededBlockError_defined=has_type)
    if raised == "QuotaExceededBlockError":
        return g.ok(second_reflection_blocked=True, exception_type=raised,
                    QuotaExceededBlockError_defined=has_type)
    return g.fail(
        f"配额确实拦住了同日第二次反思，但抛出的是 **{raised}** 而非工单要求的 `QuotaExceededBlockError`"
        f"（该类型在模块中{'存在' if has_type else '不存在'}）⇒ 调用方无法按类型捕获，"
        "『超额直接抛出 QuotaExceededBlockError』不成立。",
        second_reflection_blocked=True, exception_type=raised, required_type="QuotaExceededBlockError",
        QuotaExceededBlockError_defined=has_type)


def g07d_high_order_distiller(root, gates):
    g = Gate("G07d", "Agent-07", "高阶维度提炼器与工单点名的两个维度",
             "工单：实现 HighOrderDimensionDistiller，提炼 DIM_BURNOUT_RISK（过劳猝死风险）、DIM_CREDIT_RISK（老王信用破产）并挂载只读标签")
    tree = parse(root, "src/aios_core/cognition/dimension_engine.py")
    whole = (root / "src/aios_core/cognition/dimension_engine.py").read_text(encoding="utf-8")
    named = [n for n in ("DIM_BURNOUT_RISK", "DIM_CREDIT_RISK") if n in whole]
    cls = [c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "HighOrderDimensionDistiller"]
    distill_src = ""
    swallows = False
    if cls:
        for fn in cls[0].body:
            if isinstance(fn, ast.FunctionDef) and fn.name == "distill":
                distill_src = ast.unparse(fn)
                swallows = "except ValueError" in distill_src and "return None" in distill_src
    calls_only_propose = "propose_dimension" in distill_src and "distill" not in distill_src.replace("def distill", "")
    # 全仓库找这两个维度名
    elsewhere = []
    for p in sorted((root / "src").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for n in ("DIM_BURNOUT_RISK", "DIM_CREDIT_RISK"):
            if n in txt:
                elsewhere.append(f"{p.relative_to(root)}:{n}")
    problems = []
    if not named and not elsewhere:
        problems.append("工单点名的 DIM_BURNOUT_RISK / DIM_CREDIT_RISK 在全 src 树中不存在")
    if cls and calls_only_propose:
        problems.append("distill() 只是 propose_dimension 的薄包装，无任何『高阶提炼』逻辑（不做跨维度组合、不做解释力评估）")
    if swallows:
        problems.append("distill() 吞掉 ValueError 后返回 None ⇒ 门限未达、重名、状态错误等不同失败被压成同一个 None，不可诊断")
    if problems:
        return g.fail("；".join(problems), named_dimensions_found=named or elsewhere,
                      distiller_class_exists=bool(cls), distill_body=distill_src[:300],
                      swallows_exception=swallows)
    return g.ok(named_dimensions_found=named or elsewhere, distiller_class_exists=bool(cls))


def g07e_readonly_tag(root, gates):
    g = Gate("G07e", "Agent-07", "挂载的维度标签是否真的只读",
             "工单：提炼出的高阶维度挂载**只读**标签")
    de, _ = _mk_dimension_env(root)
    ent = de.Entity(id="e1", tags=set())
    dim = de.DimensionState(name="DIM_X", status=de.DimensionStatus.REGISTERED)
    op = de.DimensionOverlayOperator()
    op.overlay_dimension(ent, dim)
    before = set(ent.tags)
    mutated = False
    try:
        ent.tags.discard("DIM_X")
        ent.tags.clear()
        mutated = True
    except Exception as exc:
        mutated = False
    if mutated:
        return g.fail(
            "标签挂载后调用方可以随意 discard/clear（实测成功清空）⇒ 所谓『只读标签』只是注释里的声明，"
            "无任何强制（既非 frozen dataclass、也非只读视图、也无校验）。篡改已注册维度标签不会被拦截。",
            tags_before=list(before), tags_after=list(ent.tags), mutation_blocked=False)
    return g.ok(tags_before=list(before), mutation_blocked=True)


# ------------------------------------------------------- Agent-08 / M5-003
def g08a_rapport_used_in_posture(root, gates):
    g = Gate("G08a", "Agent-08", "姿态决策是否真的使用羁绊档位",
             "工单：根据当前事件紧急度**与羁绊**精准决策 SILENCE / HAPTIC_NUDGE / CRITICAL_SPOKEN")
    sr = load_module(root, "aios_core.cognition.self_reflection")
    event = {"severity": "MEDIUM", "event_type": "IMPORTANT_REMINDER", "description": "日常提醒"}
    outcomes = {}
    for tier in ("STRANGER_RESPECT", "FAMILIAR_COMPANION", "TRUSTED_WINGMAN"):
        rm = sr.DynamicRapportModel()
        rm.current_tier = sr.RapportTier[tier]
        rm.trust_score = {"STRANGER_RESPECT": 0.0, "FAMILIAR_COMPANION": 60.0, "TRUSTED_WINGMAN": 150.0}[tier]
        dec = sr.HumanlikeResponsePostureDecider(rm)
        outcomes[tier] = dec.decide_posture(dict(event)).name
    distinct = len(set(outcomes.values()))
    tree = parse(root, "src/aios_core/cognition/self_reflection.py")
    dec_fn = [f for f in funcs(tree, "HumanlikeResponsePostureDecider") if f.name == "decide_posture"]
    uses_rapport = bool(dec_fn) and "rapport_model" in ast.unparse(dec_fn[0]).split("def decide_posture", 1)[-1]
    if distinct == 1 and not uses_rapport:
        return g.fail(
            f"同一事件在三档羁绊下姿态完全相同（{outcomes}），且 decide_posture 函数体内**从未引用 self.rapport_model**"
            "（构造函数接收并保存了它，却不用）⇒ 工单要求的『与羁绊』维度实际未参与决策，是装饰性依赖。",
            posture_by_tier=outcomes, distinct_outcomes=distinct, decide_posture_references_rapport=uses_rapport)
    return g.ok(posture_by_tier=outcomes, distinct_outcomes=distinct,
                decide_posture_references_rapport=uses_rapport)


def g08b_scenario_literals(root, gates):
    g = Gate("G08b", "Agent-08", "测试场景字面量是否被写进产品代码（打表）",
             "工单铁律：严禁占位符；测试须验证『老王借款与突发早搏时毫不犹豫直言』")
    rel = "src/aios_core/cognition/self_reflection.py"
    txt = (root / rel).read_text(encoding="utf-8")
    tree = parse(root, rel)
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            for kw in ("老王借款", "早搏", "老王"):
                if kw in n.value:
                    hits.append({"line": n.lineno, "literal": n.value, "matched": kw})
    if hits:
        return g.fail(
            f"产品代码里出现测试场景的字面量关键词 {hits} ⇒ 姿态决策对该场景『果断直言』不是因为理解了紧急度，"
            "而是因为代码里写了这两个词。换任何未在关键词表里的等价表述（如『老张想借钱』『室性早搏』）都会退化为 SILENCE。",
            literal_hits=hits, source_file=rel)
    return g.ok(literal_hits=[], source_file=rel)


def g08c_mirror_actually_mirrors(root, gates):
    g = Gate("G08c", "Agent-08", "SelfIdentityMirror 是否真的『审视』铁律与底线",
             "工单：心智启动时首先**审视**四项铁律与认知底线（绝对诚实、生死第一、不废话）")
    rel = "src/aios_core/cognition/self_reflection.py"
    tree = parse(root, rel)
    fn = [f for f in funcs(tree, "SelfIdentityMirror") if f.name == "reflect"]
    body = ast.unparse(fn[0]) if fn else ""
    returns_constant_only = bool(fn) and len(fn[0].body) == 1 and isinstance(fn[0].body[0], ast.Return)
    checks_anything = bool(re.search(r"(if |raise|assert|verify|check|violat)", body))
    if returns_constant_only and not checks_anything:
        return g.fail(
            "reflect() 的函数体只有一条 return，返回 __init__ 里写死的常量字典；无任何比对、校验、违规检测。"
            "⇒ 『镜面』不照任何东西：它不会发现当前心智状态违反铁律，只是把四条原则字符串复述一遍。",
            reflect_body=body[:300], returns_constant_only=True, performs_any_check=False)
    return g.ok(reflect_body=body[:300], returns_constant_only=returns_constant_only,
                performs_any_check=checks_anything)


# ------------------------------------------------------- Agent-09 / M5-004
def g09a_advisors_take_no_input(root, gates):
    g = Gate("G09a", "Agent-09", "三个推演器是否接收世界状态并调取检索",
             "工单：调取多维心智搜索，比对 2023丝巾/2024足浴盆闲置倒水腰疼/2025按摩椅好评/2026膝盖受凉，精准推荐")
    rel = "src/aios_core/cognition/symbiotic_advisor.py"
    tree = parse(root, rel)
    report = {}
    for cls in ("MomBirthdayGiftAdvisor", "FraudPreventionAdvisor", "HealthFatigueBreakerAdvisor"):
        fns = [f for f in funcs(tree, cls) if f.name == "advise"]
        if not fns:
            report[cls] = {"exists": False}
            continue
        fn = fns[0]
        params = [a.arg for a in fn.args.args if a.arg != "self"]
        body = ast.unparse(fn)
        calls_search = bool(re.search(r"(search_mind|co_search|search_by_|store\.|WorldSearchIndex)", body))
        returns_constant = isinstance(fn.body[-1], ast.Return)
        report[cls] = {"exists": True, "advise_params": params, "param_count": len(params),
                       "calls_retrieval": calls_search, "body_chars": len(body)}
    bad = [c for c, r in report.items() if r.get("param_count", 0) == 0 or not r.get("calls_retrieval")]
    if bad:
        return g.fail(
            f"{bad} 的 advise() **不接收任何输入**（参数只有 self），函数体内**没有任何检索调用**，"
            "直接 return 写死的结论字符串 ⇒ 工单要求的『调取多维心智搜索、比对四年观测』完全未实现；"
            "输出与用户真实世界状态无关，改变 store 内容不会改变建议。",
            per_class=report)
    return g.ok(per_class=report)


def g09b_object_refs_verifiable(root, gates):
    g = Gate("G09b", "Agent-09", "因果证据指针 ObjectRef 是否确凿可核验",
             "工单：所有建议必须携带**确凿的**因果证据指针 ObjectRef，**严禁凭空编造**")
    rel = "src/aios_core/cognition/symbiotic_advisor.py"
    tree = parse(root, rel)
    ids = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "ObjectRef":
            for kw in n.keywords:
                if kw.arg == "object_id" and isinstance(kw.value, ast.Constant):
                    ids.append({"object_id": kw.value.value, "line": n.lineno})
    # 可核验判据（v1.1.0 修正）：object_id 必须能在**数据面**解析到——
    # 数据/夹具文件（.json/.sql/.csv/.txt/.md）、tests/fixtures/、或非测试的 src/ 模块。
    # 只出现在"断言同一个常量"的测试 .py 里 ⇒ 那是同义反复，不构成核验。
    unverifiable, only_in_tests = [], []
    for item in ids:
        oid = item["object_id"]
        data_hits, test_hits, src_hits = [], [], []
        for p in root.rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts or ".git" in p.parts:
                continue
            rp = str(p.relative_to(root))
            if rp == rel or p.suffix not in {".py", ".json", ".md", ".sql", ".csv", ".txt"}:
                continue
            try:
                if oid not in p.read_text(encoding="utf-8", errors="ignore"):
                    continue
            except OSError:
                continue
            if p.suffix != ".py":
                data_hits.append(rp)
            elif rp.startswith("tests/fixtures/") or "/fixtures/" in rp:
                data_hits.append(rp)
            elif rp.startswith("tests/") or rp.startswith("src/"):
                (src_hits if rp.startswith("src/") else test_hits).append(rp)
        item["found_in_data_or_fixtures"] = data_hits[:5]
        item["found_in_src"] = src_hits[:5]
        item["found_only_in_tests"] = test_hits[:5]
        if data_hits or src_hits:
            continue
        if test_hits:
            only_in_tests.append(oid)
        else:
            unverifiable.append(oid)
    bad = unverifiable + only_in_tests
    if bad:
        return g.fail(
            f"{len(bad)}/{len(ids)} 个证据指针**无法在数据面核验**：{bad}"
            f"（其中 {len(unverifiable)} 个全仓库查无此物，{len(only_in_tests)} 个只出现在断言同一常量的测试文件里）。"
            "⇒ 它们不是指向真实观测的指针，而是凭空写出的字符串常量，正好命中工单明令禁止的『凭空编造』；"
            "且没有任何代码在返回前核验这些 id 是否存在于世界库。",
            total_refs=len(ids), unverifiable_count=len(unverifiable),
            only_in_tests_count=len(only_in_tests), unverifiable_ids=unverifiable,
            only_in_tests_ids=only_in_tests, refs=ids)
    return g.ok(total_refs=len(ids), unverifiable_count=0, only_in_tests_count=0, refs=ids)


def g09c_output_invariant_to_world(root, gates):
    g = Gate("G09c", "Agent-09", "建议是否随世界状态变化（打表判定）",
             "工单：调取检索、比对历史观测后给出精准推荐")
    try:
        sa = load_module(root, "aios_core.cognition.symbiotic_advisor")
        outs = {}
        for cls in ("MomBirthdayGiftAdvisor", "FraudPreventionAdvisor", "HealthFatigueBreakerAdvisor"):
            c = getattr(sa, cls)()
            a1 = c.advise()
            a2 = c.advise()
            outs[cls] = {"identical_across_calls": a1.model_dump() == a2.model_dump(),
                         "conclusion_chars": len(a1.conclusion),
                         "evidence_pointer_count": len(a1.evidence_pointers)}
        all_constant = all(v["identical_across_calls"] for v in outs.values())
        if all_constant:
            return g.fail(
                "三个推演器重复调用输出完全一致，且不接受任何世界状态输入 ⇒ 输出是常量表。"
                "『推演』不存在：没有检索、没有比对、没有因果链计算，只有预先写好的答案。",
                per_class=outs)
        return g.ok(per_class=outs)
    except Exception as exc:
        return g.fail(f"探针执行异常：{type(exc).__name__}: {exc}", error=traceback.format_exc(limit=3))


# ------------------------------------------------------- Agent-10 / M5-005
def g10a_arena_deliverables(root, gates):
    g = Gate("G10a", "Agent-10", "工单点名的交付物路径是否存在",
             "工单：交付 src/aios_core/simulation/agent_mind_bench.py 与 tests/simulation/test_agent_mind_bench.py")
    need = ["src/aios_core/simulation/agent_mind_bench.py", "tests/simulation/test_agent_mind_bench.py"]
    missing = [n for n in need if not (root / n).exists()]
    actual = sorted(str(p.relative_to(root)) for p in (root / "src/aios_core/simulation").glob("*.py")
                    if "__pycache__" not in p.parts)
    if missing:
        return g.fail(
            f"工单点名的交付物缺失：{missing}；实际落地的是 {actual} ⇒ 文件名与工单不符，"
            "台账与验收无法按工单路径对账。",
            missing=missing, actual_simulation_files=actual)
    return g.ok(missing=[], actual_simulation_files=actual)


def g10b_arena_capabilities(root, gates):
    g = Gate("G10b", "Agent-10", "战训考场四项核心能力是否存在",
             "工单：AgentMindArena 让目标 Agent 独立进驻，自主调用 search_mind / distill_dimension / decide_posture / advise_decision；"
                   "自动统计 Token 预算使用率、证据检索命中率、人设分寸感得分、五大铁律违宪检查（篡改历史一票否决、P0调用大模型一票否决）；"
                   "自动生成《AIOS 3.0 共生心智操作全景体检报告》并持久化到经验库")
    caps = {
        "AgentMindArena 类": r"class\s+AgentMindArena",
        "自主调用 search_mind": r"search_mind",
        "自主调用 distill_dimension": r"distill_dimension",
        "自主调用 decide_posture": r"decide_posture",
        "自主调用 advise_decision": r"advise_decision",
        "Token 预算使用率": r"(token_budget|预算使用率|budget_usage)",
        "证据检索命中率": r"(hit_rate|命中率)",
        "人设分寸感得分": r"(posture_score|分寸感)",
        "违宪检查/一票否决": r"(违宪|一票否决|veto)",
        "全景体检报告生成": r"(体检报告|panorama|health_report)",
    }
    bench = root / "src/aios_core/simulation/massive_life_bench.py"
    txt = bench.read_text(encoding="utf-8") if bench.exists() else ""
    # 全 src 范围兜底（能力可能落在别处）
    all_src = ""
    for p in sorted((root / "src").rglob("*.py")):
        if "__pycache__" not in p.parts:
            all_src += p.read_text(encoding="utf-8", errors="ignore")
    found, missing = {}, []
    for label, pat in caps.items():
        in_bench = bool(re.search(pat, txt, re.I))
        in_src = bool(re.search(pat, all_src, re.I))
        found[label] = {"in_delivered_bench": in_bench, "anywhere_in_src": in_src}
        if not in_src:
            missing.append(label)
    delivered_classes = []
    if bench.exists():
        t = ast.parse(txt)
        for c in t.body:
            if isinstance(c, ast.ClassDef):
                delivered_classes.append((c.name, [m.name for m in c.body if isinstance(m, ast.FunctionDef)]))
    if missing:
        return g.fail(
            f"工单要求的 {len(caps)} 项能力中 {len(missing)} 项在全 src 树中完全不存在：{missing}。"
            f"实际交付的 massive_life_bench.py 只含 {delivered_classes} ⇒ 那是『世界发生器』，"
            "不是『让 Agent 进驻并自主调用四大能力的战训考场』，也没有评分、违宪检查与体检报告。",
            capability_matrix=found, missing_capabilities=missing, delivered_classes=delivered_classes)
    return g.ok(capability_matrix=found, delivered_classes=delivered_classes)


# ------------------------------------------------------- 台账一致性
def g11_ledger_vs_measured(root, gates):
    g = Gate("G11", "台账", "台账 CLOSED 声称与本探针实测是否一致",
             "台账 docs/specifications/TASK_PROGRESS_V3.md 将 #7/#8/#9 记为 CLOSED (n/n PASS)")
    led = root / "docs/specifications/TASK_PROGRESS_V3.md"
    if not led.exists():
        return g.na("台账文件不存在")
    txt = led.read_text(encoding="utf-8")
    claims = {}
    for line in txt.splitlines():
        m = re.search(r"TASK-M5-00(\d)-([A-Z-]+)", line)
        if m:
            closed = re.search(r"CLOSED\s*\(([^)]*)\)", line)
            is_closed = "CLOSED" in line
            claims[f"M5-00{m.group(1)}"] = {
                "slug": m.group(2),
                "is_closed": is_closed,
                "claimed": (closed.group(1) if closed else
                            ("EXECUTING" if "EXECUTING" in line else "OTHER")),
                "line": line.strip()[:220]}
    failed_by_order = {}
    for gate in gates:
        if gate.verdict == "FAIL":
            failed_by_order.setdefault(gate.order, []).append(gate.gid)
    contradictions = []
    mapping = {"Agent-06": "M5-001", "Agent-07": "M5-002", "Agent-08": "M5-003", "Agent-09": "M5-004",
               "Agent-10": "M5-005"}
    for order, key in mapping.items():
        entry = claims.get(key, {})
        claimed, is_closed = entry.get("claimed", "UNKNOWN"), entry.get("is_closed", False)
        fails = failed_by_order.get(order, [])
        if is_closed and fails:
            contradictions.append({"ledger_id": key, "claimed": f"CLOSED ({claimed})",
                                   "probe_failed_gates": fails, "failed_count": len(fails)})
    if contradictions:
        return g.fail(
            f"{len(contradictions)} 条台账 CLOSED 声称与本探针实测矛盾：{contradictions} ⇒ "
            "『测试全绿』被当成了『工单硬门禁成立』。台账按测试通过数记账，而测试断言的是场景常量，"
            "不是工单的门槛语义。",
            ledger_claims=claims, contradictions=contradictions)
    return g.ok(ledger_claims=claims, contradictions=[])


GATES: list[tuple[str, Callable]] = [
    ("G06d", g06d_search_bus), ("G06a", g06a_pathway_executor), ("G06b", g06b_unused_imports),
    ("G06c", g06c_prior_numbers),
    ("G07a", g07a_prediction_accuracy), ("G07b", g07b_expired_state), ("G07c", g07c_quota_error_type),
    ("G07d", g07d_high_order_distiller), ("G07e", g07e_readonly_tag),
    ("G08a", g08a_rapport_used_in_posture), ("G08b", g08b_scenario_literals), ("G08c", g08c_mirror_actually_mirrors),
    ("G09a", g09a_advisors_take_no_input), ("G09b", g09b_object_refs_verifiable), ("G09c", g09c_output_invariant_to_world),
    ("G10a", g10a_arena_deliverables), ("G10b", g10b_arena_capabilities),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=None, help="被审树根（默认：本文件所在仓库根）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)

    root = pathlib.Path(args.repo_root).resolve() if args.repo_root else pathlib.Path(__file__).resolve().parents[3]
    lines: list[str] = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit(f"M5 批次 as-built 硬门禁探针 v{TOOL_VERSION}")
    emit(f"被审树根：{root}")
    emit(f"被审提交：{git_head(root)}")
    emit(f"运行时刻：{_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")

    missing = [f for f in SUBJECT_FILES if not (root / f).exists()]
    subject_hashes = {f: sha256(root / f) for f in SUBJECT_FILES if (root / f).exists()}
    if missing:
        emit("")
        emit(f"!! 被审对象缺失 {len(missing)} 项：{missing}")
        emit("!! 本探针 fail-closed：不含 M5 代码的 checkout 上不予判定（绝不静默判过）。")
        emit("!! 请在含 M5 交付的树上运行，例如：git worktree add /tmp/trunk origin/aios-2.0")
        if args.json:
            pathlib.Path(args.json).write_text(json.dumps({
                "tool": "reviews/architecture/evidence/verify_landed_m5_batch.py",
                "tool_version": TOOL_VERSION, "subject_commit": git_head(root),
                "provenance": {"probe_script": "reviews/architecture/evidence/verify_landed_m5_batch.py",
                               "script_sha256": sha256(pathlib.Path(__file__).resolve()),
                               "probe_version": TOOL_VERSION,
                               "subject_availability": "SUBJECT_MISSING"},
                "status": "SUBJECT_MISSING", "missing_subject_files": missing,
                "all_gates_pass": False, "gates": {},
                "subject_file_sha256": subject_hashes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.log:
            pathlib.Path(args.log).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 2

    # 让被审模块可导入
    sys.path.insert(0, str(root / "src"))

    gates: list[Gate] = []
    for gid, fn in GATES:
        try:
            gates.append(fn(root, gates))
        except Exception as exc:
            g = Gate(gid, "?", "探针自身异常", "")
            gates.append(g.fail(f"探针执行异常（不得视为通过）：{type(exc).__name__}: {exc}",
                                error=traceback.format_exc(limit=4)))

    # 台账一致性门最后跑（依赖前面结果）
    gates.append(g11_ledger_vs_measured(root, gates))

    emit("")
    emit("=" * 78)
    npass = sum(1 for g in gates if g.verdict == "PASS")
    nfail = sum(1 for g in gates if g.verdict == "FAIL")
    nna = sum(1 for g in gates if g.verdict == "N/A")
    for g in gates:
        mark = {"PASS": "✅", "FAIL": "❌", "N/A": "➖"}[g.verdict]
        emit(f"{mark} {g.gid} [{g.order}] {g.title} → {g.verdict}")
        if g.note:
            emit(f"     判定：{g.note}")
        for k, v in g.measured.items():
            if k in ("error",):
                continue
            emit(f"     · {k} = {json.dumps(v, ensure_ascii=False)[:400]}")
    emit("=" * 78)
    emit(f"合计 {len(gates)} 道门：PASS {npass} / FAIL {nfail} / N/A {nna}")
    emit("VERDICT = " + ("PASS" if nfail == 0 else "FAIL"))

    if args.json:
        probe_path = pathlib.Path(__file__).resolve()
        in_this_repo = (root == probe_path.parents[3]) if len(probe_path.parents) > 3 else False
        out = {
            "tool": "reviews/architecture/evidence/verify_landed_m5_batch.py",
            "tool_version": TOOL_VERSION,
            "provenance": {
                "probe_script": "reviews/architecture/evidence/verify_landed_m5_batch.py",
                # CG-1 需要：产出本工件时探针自身的字节哈希（探针改动后未重跑 ⇒ 溯源断裂）
                "script_sha256": sha256(probe_path),
                "probe_version": TOOL_VERSION,
                "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "subject_repo_root": str(root),
                "subject_commit": git_head(root),
                # 刻意**不设** subject_under_test：被审对象是 origin/aios-2.0 快照上的 6 个 M5 模块，
                # 它们不在本分支的工作树里；CG-1 的工作树比对不适用 ⇒ 改为逐文件哈希 + 被审提交号溯源。
                "subject_availability": (
                    "IN_THIS_TREE" if not missing and in_this_repo else
                    "CROSS_REF（被审对象位于 origin/aios-2.0 快照；本分支不含 M5 代码，"
                    "故按 subject_commit + subject_file_sha256 溯源，不做工作树比对）"),
            },
            "subject_file_sha256": subject_hashes,
            "gate_count": len(gates), "pass": npass, "fail": nfail, "na": nna,
            "verdict": "PASS" if nfail == 0 else "FAIL",
            # CG-1 约定形态：gates 为 {gate_id: 是否成立} 的 dict
            "all_gates_pass": nfail == 0,
            "gates": {g.gid: (g.verdict == "PASS") for g in gates},
            "gate_details": [g.as_dict() for g in gates],
        }
        p = pathlib.Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        emit(f"工件已写入：{p}")
    if args.log:
        pathlib.Path(args.log).write_text("\n".join(lines) + "\n", encoding="utf-8")
        emit(f"日志已写入：{args.log}")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
