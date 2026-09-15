"""运行时政策层（governance/runtime_policy.json）的守宪测试 —— v1.1.0。

三层结构的第三层：
  - 宪法 v3.0.1（AIOS核心系统宪法v3.0 + ADJ-001~012 裁决集）讲价值：什么不可违背；
  - 法律（governance/runtime_policy.json）讲参数：多少算好；
  - 判决（本文件）讲执行：是否守宪。

v1.1.0 的变更主题
----------------
上位法从「宪法 v3.0」升级为「CONST-v3.0.1（v3.0 + 裁决集 12 项）」。
裁决集明文规定「凡 v3.0 原文与本裁决集冲突处，以本裁决集为准」，
本文件是裁决集的下位法，因此新增了一整族断言用于校验政策层对裁决的忠实度：
  · adjudication_alignment 必须覆盖 ADJ-001~012 全部 12 条，且计数自洽；
  · 每条裁决的 policy_fields 必须真实存在（防止"声称已落地"而字段是空的）；
  · 每个域必须同时带裸条号与 ADJ-011 稳定键，且稳定键必须真实存在于
    governance/traceability_matrix.csv —— 这是一条跨文件引用完整性检查。

设计纪律（v1.0.0 起不变）
------------------------
1. **纯标准库**。不 import pytest / pydantic / yaml。执法机关不向被执法者借工具。
2. **双入口**。pytest 自动收集；也可 `python3 tests/policy/test_runtime_policy.py`
   独立运行并以退出码报告。
3. **fail-closed**。与 tests/architecture/test_scanner_regression.py 的 CASE-10
   同一种品味：文件缺失、解析失败、键缺失、预算自相矛盾，一律判红。
4. **每条断言都指向宪法条款**。没有出处的指标是私人偏好，不是法律。
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "governance" / "runtime_policy.json"
TRACE_MATRIX_PATH = REPO_ROOT / "governance" / "traceability_matrix.csv"
ADJ_SET_PATH = REPO_ROOT / "docs" / "constitution" / "v3.0.1_规范裁决集_ADJ-001-012.md"

# 裁决集全 12 条。ADJ-010 §3：ADJ-001 与 ADJ-004 属深水区裁决，
# 再变更须重走全量 G0 合议 —— 故此处硬编码而非从政策文件读取，
# 让"裁决集少了一条"这件事必须同时改两个文件才能通过。
REQUIRED_ADJUDICATIONS = [f"ADJ-{i:03d}" for i in range(1, 13)]


# ---------------------------------------------------------------------------
# 加载：fail-closed
# ---------------------------------------------------------------------------


def load_policy() -> dict[str, Any]:
    """加载政策文件。缺失或非法 JSON 一律抛错，绝不返回空 dict 兜底。"""
    if not POLICY_PATH.is_file():
        raise AssertionError(f"政策文件缺失: {POLICY_PATH}")
    try:
        parsed = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"政策文件不是合法 JSON: {POLICY_PATH}: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise AssertionError(f"政策文件顶层必须是非空对象: {POLICY_PATH}")
    return parsed


def load_registered_stable_keys() -> set[str]:
    """从追溯矩阵读取全部已注册的条款稳定键（ADJ-011 的唯一权威载体）。

    矩阵缺失或格式退化时 fail-closed —— 宁可判红，也不允许"查不到就当没有要求"。
    """
    if not TRACE_MATRIX_PATH.is_file():
        raise AssertionError(f"追溯矩阵缺失: {TRACE_MATRIX_PATH}")
    with TRACE_MATRIX_PATH.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows or rows[0][0] != "stable_key":
        raise AssertionError(
            f"追溯矩阵首列必须是 stable_key，实际: {rows[0][:1] if rows else '(空文件)'}"
        )
    keys = {r[0].strip() for r in rows[1:] if r and r[0].strip()}
    if len(keys) < 100:
        raise AssertionError(
            f"追溯矩阵稳定键数量异常（{len(keys)} < 100），文件可能被截断"
        )
    return keys


POLICY = load_policy()
STABLE_KEYS = load_registered_stable_keys()

# 政策中每一个需要可审计出处的顶层域。
# 没有 constitution_ref + constitution_stable_keys 的域 = 私人偏好 = 不是法律。
AUDITABLE_SECTIONS = (
    "token_budget",
    "step0_safety_gate",
    "manifest_layer_caps",
    "latency_slo",
    "retrieval_slo",
    "co_search",
    "storage_envelope",
    "retrospective_annotation",
    "propagation_caps",
    "retention_policy",
    "speaker_cluster_lifecycle",
    "threshold_governance",
    "delivery_fsm",
    "mental_startup",
    "task_readiness",
    "heartbeat",
    "style_constraints",
    "degradation_invariants",
    "dimension_escrow",
    "id_namespace_registry",
    "adjudication_alignment",
)


def _collect_stable_key_refs(node: Any) -> list[str]:
    """递归收集全部 constitution_stable_keys 引用（含嵌套域与逐条不变量）。

    只认字段名 constitution_stable_keys —— 说明性散文里出现的键名不算引用，
    否则一段解释文字就能让引用完整性检查失真。
    """
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "constitution_stable_keys" and isinstance(v, list):
                found.extend(x for x in v if isinstance(x, str))
            else:
                found.extend(_collect_stable_key_refs(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_collect_stable_key_refs(v))
    return found


_SEGMENT_RE = re.compile(r"([^\.\[\]]+)|\[([^\]]+)\]")


def _resolve_path(policy: dict[str, Any], dotted: str) -> Any:
    """按 'a.b.c' 或 'a.b[key.with.dots]' 取字段；任一层缺失抛 KeyError。

    需要方括号语法，因为编号命名空间的键本身就含点（'C01..C16'、'R2-24'）。
    若不支持，校验 policy_fields 是否真实存在这条断言就会在合法字段上误报 ——
    一个会误报的存在性检查，比没有检查更糟，因为它训练人忽略红灯。
    """
    cur: Any = policy
    for m in _SEGMENT_RE.finditer(dotted):
        part = m.group(2) if m.group(2) is not None else m.group(1)
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


# ---------------------------------------------------------------------------
# 0. 元结构与可审计性
# ---------------------------------------------------------------------------


def test_policy_is_versioned_and_bound_to_constitution() -> None:
    """政策必须声明版本、宪法基线与执法者，否则无人知道该由谁在何时校验。"""
    for key in ("policy_version", "constitution_baseline", "enforced_by"):
        assert key in POLICY, f"政策缺少元字段: {key}"
    assert POLICY["policy_version"], "policy_version 不得为空"
    assert "v3.0.1" in POLICY["constitution_baseline"], (
        "上位法已升级为 CONST-v3.0.1（v3.0 + ADJ 裁决集），基线声明必须反映这一点"
    )


def test_policy_declares_adjudication_set_as_upstream_authority() -> None:
    """裁决集明文『凡 v3.0 原文与本裁决集冲突处，以本裁决集为准』。

    政策层若不自陈下位法身份，就会在某次"我觉得这样更合理"的修改里
    悄悄与裁决集分叉 —— 而这正是编号漂移与条款漂移的成因。
    """
    assert "ADJ-v3.0.1" in POLICY["upstream_authority"]
    assert POLICY["adjudication_alignment"]["precedence_rule"].startswith("ADJ >"), (
        "必须显式声明优先级：ADJ 高于本文件"
    )


def test_ci_wiring_status_is_honestly_declared() -> None:
    """政策必须如实声明自己的执法通道状态，包括没接上的部分。

    把"已接入 CI"写成事实而实际未接入，就是一条假 PASS。
    """
    status = POLICY["ci_wiring_status"]
    assert status.startswith("PATCH_READY_NOT_APPLIED"), (
        f"ci_wiring_status 应如实反映补丁未应用状态，实际: {status[:60]}"
    )
    assert "pytest" in " ".join(POLICY["enforced_by"]), (
        "必须说明 testpaths 自动收集这条替代执法通道，否则政策处于无人执法状态"
    )


def test_every_auditable_section_cites_the_constitution() -> None:
    """§115 三级修宪纪律 + ADJ-011 稳定键制度的参数化延伸。"""
    missing = [s for s in AUDITABLE_SECTIONS if s not in POLICY]
    assert not missing, f"政策缺少必需域: {missing}"

    uncited = [
        s for s in AUDITABLE_SECTIONS
        if not str(POLICY[s].get("constitution_ref", "")).strip()
    ]
    assert not uncited, f"以下域未引用任何宪法条款，属于无出处的私人偏好: {uncited}"

    no_stable_key = [
        s for s in AUDITABLE_SECTIONS
        if not POLICY[s].get("constitution_stable_keys")
    ]
    assert not no_stable_key, (
        f"ADJ-011 §2：正式文档一律须引用稳定键，裸条号只是印刷物。"
        f"以下域缺 constitution_stable_keys: {no_stable_key}"
    )


def test_every_cited_stable_key_is_actually_registered() -> None:
    """跨文件引用完整性：政策引用的每个稳定键都必须真实存在于追溯矩阵。

    这是 ADJ-011 制度能不能立住的关键。稳定键制度若允许引用不存在的键，
    它就退化成了另一套会漂移的编号 —— 而漂移正是它要消灭的东西。
    """
    cited = _collect_stable_key_refs(POLICY)
    assert len(cited) >= 40, f"稳定键引用数量异常偏少（{len(cited)}），迁移可能未完成"
    unregistered = sorted({k for k in cited if k not in STABLE_KEYS})
    assert not unregistered, (
        f"政策引用了 {len(unregistered)} 个未注册的稳定键（悬空引用）: {unregistered}"
    )


def test_section_keys_starting_with_dollar_are_notes_not_config() -> None:
    """以 $ 开头的键是注释，不是配置。防止把说明文字误当参数读取。"""
    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                assert not (k.endswith("_note") and not k.startswith("$")), (
                    f"{path}/{k}: 说明性字段必须以 $ 前缀标注，以免被当作配置读取"
                )
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(POLICY)


# ---------------------------------------------------------------------------
# 1. 裁决对齐：12 条一条都不能少，且声称落地的字段必须真实存在
# ---------------------------------------------------------------------------


def test_all_twelve_adjudications_are_mapped() -> None:
    """ADJ-001~012 必须逐条映射。漏一条就等于该裁决在运行时没有执法者。"""
    items = POLICY["adjudication_alignment"]["items"]
    mapped = {it["adj"] for it in items}
    missing = [a for a in REQUIRED_ADJUDICATIONS if a not in mapped]
    assert not missing, f"以下裁决未映射到政策层，等于无人执法: {missing}"
    extra = sorted(mapped - set(REQUIRED_ADJUDICATIONS))
    assert not extra, f"出现了裁决集之外的编号（可能是幽灵编号）: {extra}"


def test_alignment_verdict_counts_are_self_consistent() -> None:
    """计数必须与逐条 verdict 相符 —— 一份自相矛盾的自评等于没有自评。"""
    items = POLICY["adjudication_alignment"]["items"]
    legend = POLICY["adjudication_alignment"]["alignment_verdict_legend"]
    counts = POLICY["adjudication_alignment"]["summary_counts"]

    for it in items:
        assert it["verdict"] in legend, (
            f"{it['adj']} 的 verdict={it['verdict']} 未在图例中定义"
        )
        assert str(it.get("title", "")).strip(), f"{it['adj']} 缺标题"
        assert str(it.get("$finding", "")).strip(), (
            f"{it['adj']} 缺 $finding：必须写清这条裁决改变了什么，而不只是打个标签"
        )

    actual: dict[str, int] = {v: 0 for v in legend}
    for it in items:
        actual[it["verdict"]] += 1
    for verdict, n in actual.items():
        assert counts.get(verdict) == n, (
            f"verdict {verdict} 计数不符：声明 {counts.get(verdict)}，实际 {n}"
        )
    assert counts["total"] == len(items) == 12


def test_every_claimed_policy_field_actually_exists() -> None:
    """裁决条目声称落地的字段必须真实存在。

    "已按 ADJ 改写"若指向一个不存在的字段，就是一条比缺失更难发现的假 PASS ——
    它让审阅者以为工作已完成。
    """
    missing: list[str] = []
    for it in POLICY["adjudication_alignment"]["items"]:
        for field in it["policy_fields"]:
            # 允许 "全部域的 constitution_stable_keys 字段" 这类非路径描述。
            if " " in field or not field[0].isascii():
                continue
            try:
                _resolve_path(POLICY, field)
            except KeyError:
                missing.append(f"{it['adj']} → {field}")
    assert not missing, f"以下声称已落地的字段在政策中不存在:\n  " + "\n  ".join(missing)


def test_adjudication_set_file_itself_is_present() -> None:
    """上位法文件必须存在。引用一份不存在的法律，是最彻底的假 PASS。"""
    assert ADJ_SET_PATH.is_file(), f"裁决集文件缺失: {ADJ_SET_PATH}"
    text = ADJ_SET_PATH.read_text(encoding="utf-8")
    absent = [a for a in REQUIRED_ADJUDICATIONS if f"### {a}" not in text]
    assert not absent, f"裁决集文件中找不到以下条目: {absent}"


# ---------------------------------------------------------------------------
# 2. Step-0 机械安全闸（ADJ-001 §1，最高级裁决）
# ---------------------------------------------------------------------------


def test_step0_gate_runs_before_mental_steps_with_zero_model_calls() -> None:
    """ADJ-001 §1：Step-0 先于一切心智步骤、零模型调用、确定性规则。

    若 Step-0 需要模型调用，它就不是闸门而是又一次开销 ——
    那么"为了决定要不要打扰用户先花一次完整四步序"的浪费会原样复现。
    """
    g = POLICY["step0_safety_gate"]
    assert g["runs_before_any_mental_step"] is True
    assert g["model_calls"] == 0, "Step-0 必须零模型调用"
    assert g["deterministic_rules_only"] is True


def test_step0_verdicts_are_a_closed_three_value_enum() -> None:
    """OK / QUIET / HARD_BLOCK。三值必须闭合，否则实现会自造第四种语义。"""
    assert set(POLICY["step0_safety_gate"]["verdicts"]) == {"OK", "QUIET", "HARD_BLOCK"}


def test_step0_hard_block_does_not_stop_silent_patrol() -> None:
    """ADJ-001 §1 的优先级裁定：§80之3『后台静默巡检绝对不停转』优先于 HARD_BLOCK。

    这是一个优先级，不是例外清单。若 HARD_BLOCK 连巡检都停掉，
    AI 在被禁言期间就彻底失去对世界的观察 —— 那比打扰用户严重得多。
    """
    g = POLICY["step0_safety_gate"]
    assert g["hard_block_prohibits_external_delivery"] is True
    assert "background_silent_patrol" in g["hard_block_still_allows"]
    assert "safety_watch" in g["hard_block_still_allows"]


def test_step0_verdicts_are_auditable_not_hidden() -> None:
    """ADJ-001 §1：全部判定物化进 Session 审计，不得用隐藏思维链代替。

    与 P3 原则（静默失效一律非法）同源，但 ADJ 把它落到了具体载体上。
    """
    g = POLICY["step0_safety_gate"]
    assert g["verdicts_materialized_into_session_audit"] is True
    assert g["hidden_chain_of_thought_substitute_prohibited"] is True
    assert "step0_verdict" in POLICY["mental_startup"]["trace_fields"], (
        "MentalStartupTrace 必须承载 Step-0 判定，否则审计无处落地"
    )


def test_step0_covers_all_four_mechanical_checks() -> None:
    """(a) 安全硬信号 (b) 方便度 (c) 投放信道合法性 (d) 预算闸门。"""
    checks = POLICY["step0_safety_gate"]["checks"]
    assert set(checks) == {
        "a_safety_hard_signal", "b_convenience_mechanical",
        "c_channel_legality", "d_budget_gate",
    }
    assert "epoch" in checks["c_channel_legality"], (
        "投放信道合法性必须实现 ADJ-007 §2 的通知 epoch 断电"
    )


# ---------------------------------------------------------------------------
# 3. Token 封套：子系统之和必须等于总帽
# ---------------------------------------------------------------------------


def test_token_subsystems_sum_exactly_to_monthly_cap() -> None:
    """§86 条件驱动零浪费：预算必须零基闭合。

    子系统之和若大于总帽，则总帽是谎言；若小于总帽，则有一笔无主预算
    会被工程直觉悄悄花掉。两者都必须判红。
    v1.0.0 在此处翻过车（合计四舍五入成 2,550,000，真实和 2,554,000）。
    """
    tb = POLICY["token_budget"]
    total = sum(v["monthly_cap"] for v in tb["subsystems"].values())
    cap = tb["monthly_total_cap"]
    assert total == cap, (
        f"子系统预算之和 {total:,} ≠ 月度总帽 {cap:,}（差 {total - cap:+,}）"
    )


def test_every_subsystem_has_a_basis_and_an_over_quota_policy() -> None:
    """没有推导依据的数字是愿望；没有超额策略的预算是空话。"""
    tb = POLICY["token_budget"]
    quota = tb["over_quota_policy"]
    allowed = {"degrade", "defer", "halt"}

    for name, spec in tb["subsystems"].items():
        assert str(spec.get("basis", "")).strip(), f"{name} 缺少 basis 推导依据"
        assert name in quota, f"{name} 缺少 over_quota_policy"
        assert quota[name] in allowed, f"{name} 的 over_quota_policy={quota[name]} 非法"

    assert set(quota) == set(tb["subsystems"]), (
        "over_quota_policy 的键集合必须与 subsystems 完全一致"
    )


def test_safety_and_fast_lane_are_never_degradable() -> None:
    """§78之4 硬件级安全响应 + §85之1 首字响应：这两条不许被预算牺牲。

    注意这里刻意不用 over_quota_policy.get(sub) —— 缺失的键与合规的键会返回
    同一个"不等于 halt"的结果，让一条守护安全的断言实际什么都不守。
    必须区分"已登记且不为 halt"与"根本不在预算体系内"两种情形。
    """
    tb = POLICY["token_budget"]
    quota = tb["over_quota_policy"]

    for sub in tb["never_degradable"]:
        assert sub in quota, (
            f"{sub} 被列为 never_degradable，却不在 over_quota_policy 中 —— "
            "无法校验的策略等于没有策略"
        )
        assert quota[sub] != "halt", f"{sub} 被列为 never_degradable，却允许 halt"

    # 安全不是被预算的子系统，它在预算体系之外，由 Step-0 保护。
    assert tb["non_budgeted_never_degradable"] == ["safety"]
    assert "safety" not in tb["subsystems"], (
        "安全不得被当作可预算子系统：一旦它有配额，就存在'配额用完'的语义"
    )
    allowed = POLICY["step0_safety_gate"]["hard_block_still_allows"]
    assert "safety_watch" in allowed, (
        "安全的保护载体是 step0_safety_gate.hard_block_still_alloweds，必须包含 safety_watch"
    )


def test_monthly_cap_implies_the_daily_cap() -> None:
    """日帽必须与月帽自洽（30 天）。"""
    tb = POLICY["token_budget"]
    assert tb["period"] == "monthly"
    implied = math.ceil(tb["monthly_total_cap"] / 30)
    assert tb["daily_total_cap"] == implied, (
        f"daily_total_cap={tb['daily_total_cap']:,} 与月帽推算值 {implied:,} 不符"
    )


def test_deep_lane_is_capped_and_gated() -> None:
    """§85之1 的"1M 上下文战略核武器"不得成为日常开销。"""
    tb = POLICY["token_budget"]
    deep = tb["subsystems"]["conversation.deep"]["monthly_cap"]
    assert deep / tb["monthly_total_cap"] < 0.35, (
        f"深车道占月预算 {deep / tb['monthly_total_cap']:.0%}，超过 35%"
    )
    assert POLICY["manifest_layer_caps"]["deep_lane_requires_explicit_request"] is True


def test_budget_gate_is_wired_into_step0() -> None:
    """ADJ-001 §1(d)：预算闸门是 Step-0 的第四项机械检查。

    这让 token_budget 从"事后监控指标"变成"启动期判据" ——
    预算超支在花钱之前就被拦住，而不是在月底被看见。
    """
    assert "d_budget_gate" in POLICY["step0_safety_gate"]["checks"]
    assert "ADJ-001" in " ".join(POLICY["token_budget"]["adjudication_refs"])


# ---------------------------------------------------------------------------
# 4. Manifest 分层预算：物理顺序即 KV-cache 顺序
# ---------------------------------------------------------------------------


def test_manifest_layers_are_declared_in_cache_stability_order() -> None:
    """声明顺序 == prompt 物理顺序 == 最稳定 → 最易变。

    Wake Reason（§78 语义第一）必须物理最后，否则 prefix KV-cache 每次全 miss。
    这条断言守的是延迟，不是美学。

    注意：这与 ADJ-001 的段落序是两个正交的轴 —— 段落序是认知内容
    （step1_self→step4_world），物理序是 token 布局（缓存稳定性）。
    同一份 Manifest 必须同时满足两者。
    """
    mlc = POLICY["manifest_layer_caps"]
    layers = mlc["layers"]
    assert mlc["layer_order_is_prompt_order"] is True
    assert layers[-1] == "l7_trigger", (
        f"l7_trigger 必须物理排最后以保住 prefix cache，当前顺序: {layers}"
    )
    cacheable = mlc["cacheable_layers"]
    assert layers[: len(cacheable)] == cacheable, (
        f"cacheable_layers 必须是 layers 的严格前缀: {cacheable} vs {layers}"
    )


def test_manifest_layer_caps_sum_to_total_and_stable_prefix_is_declared() -> None:
    """§85之2 的 1500 tokens 属于 L6 单层，不是整个 Manifest（裁决 C4）。"""
    mlc = POLICY["manifest_layer_caps"]
    for lane in ("fast", "deep"):
        spec = mlc[lane]
        s = sum(spec[k] for k in mlc["layers"])
        assert s == spec["total_cap"], f"{lane} 车道分层之和 {s} ≠ total_cap {spec['total_cap']}"
        assert 0 < spec["stable_prefix_tokens"] <= spec["total_cap"]

    assert mlc["fast"]["l6_dialog"] == 1500, (
        "宪法 §85之2 的 1500 tokens 指前台对话滑动窗口（L6），不是 Manifest 总量"
    )
    assert mlc["fast"]["total_cap"] > 1500, (
        "若把 1500 当成 Manifest 总量，单次看盘（§84之1）无法成立"
    )


def test_manifest_omission_must_be_honest() -> None:
    """P3 原则在上下文层的镜像：裁剪可以，隐瞒不行。"""
    mlc = POLICY["manifest_layer_caps"]
    assert mlc["silent_omission_prohibited"] is True
    assert mlc["omission_requires_query_hint"] is True


def test_resonance_dense_area_is_renamed_per_adj006() -> None:
    """ADJ-006 §1：『共振密集区』在实现语言中重命名为『候选密集区』，
    消灭"检索→因果"的旧混淆口。名字不是小事 —— 它会决定工程师敢用它做什么。
    """
    mlc = POLICY["manifest_layer_caps"]
    assert mlc["resonance_dense_area_renamed_to"] == "candidate_dense_area"


# ---------------------------------------------------------------------------
# 5. 延迟 SLO：两个不同计时边界的指标必须并存且各自自洽
# ---------------------------------------------------------------------------


def test_latency_slo_declares_two_distinct_measurement_boundaries() -> None:
    """ADJ-007 §1 的法定边界（从 ASR final 起算）与用户体感边界（从语音起点起算）不同。

    只留法定值 → 产品会合法地慢（审计通过，体感差）。
    只留体感值 → 审计不过（法定 SLO 无人守）。
    两者都必须存在，且都必须声明自己的计时起点。
    """
    slo = POLICY["latency_slo"]
    legal = slo["legal_slo_from_asr_final_ms"]
    perceived = slo["perceived_slo_from_speech_onset_ms"]

    assert legal["authority"].startswith("ADJ-007"), "法定 SLO 的权威必须是 ADJ-007 §1"
    assert legal["status"] == "warm_path_only", (
        "ADJ-007 §1：法定 SLO 只覆盖暖路径；冷连接/冷模型/深车道必须显式标注不在此承诺内"
    )
    assert slo["cold_path_and_deep_lane_explicitly_out_of_promise"] is True

    # 体感值必须严于法定值，否则它没有存在意义。
    assert perceived["p95"] < legal["p95"], (
        f"体感 p95({perceived['p95']}) 必须严于法定 p95({legal['p95']})，"
        "否则这个自设指标不构成额外约束"
    )
    assert perceived["p50"] < legal["p50"]
    assert "本政策层自设" in perceived["authority"], (
        "体感 SLO 必须诚实标注为本政策层自设，不得冒充法定值"
    )


def test_legal_latency_stage_budget_can_meet_the_legal_slo() -> None:
    """只把 inside_legal_slo=true 的阶段计入法定边界，其最坏串行和不得超过法定 p95。

    这条断言是 ADJ-007 计时边界的执行者：若把 VAD 尾静音与 ASR 终稿也算进法定边界，
    就会用一段本不属于法定范围的耗时去挤占真实预算，得出虚假的"超支"结论。
    """
    slo = POLICY["latency_slo"]
    stages = slo["stage_budget_ms"]
    legal_stages = {k: v for k, v in stages.items() if v.get("inside_legal_slo")}
    assert legal_stages, "必须至少有一个阶段被标记为属于法定 SLO 边界"

    worst = sum(v["max"] for v in legal_stages.values())
    assert worst <= slo["legal_slo_from_asr_final_ms"]["p95"], (
        f"法定边界内阶段最坏串行和 {worst}ms > 法定 p95 "
        f"{slo['legal_slo_from_asr_final_ms']['p95']}ms"
    )


def test_perceived_latency_stage_budget_can_meet_the_perceived_slo() -> None:
    """全部阶段计入体感边界，其最坏串行和不得超过体感 p95。"""
    slo = POLICY["latency_slo"]
    stages = slo["stage_budget_ms"]
    worst = sum(v["max"] for v in stages.values())
    best = sum(v["min"] for v in stages.values())
    p95 = slo["perceived_slo_from_speech_onset_ms"]["p95"]
    p50 = slo["perceived_slo_from_speech_onset_ms"]["p50"]
    assert worst <= p95, f"体感阶段最坏串行和 {worst}ms > p95 {p95}ms，该 SLO 算术上不可达"
    assert best <= p50, f"体感阶段最好串行和 {best}ms > p50 {p50}ms"
    for name, v in stages.items():
        assert v["min"] <= v["max"], f"{name} 的 min > max"
        assert "where" in v, f"{name} 缺少 where（device/service/network/cloud）"
        assert "inside_legal_slo" in v, (
            f"{name} 必须声明是否属于法定 SLO 边界；不声明就等于默认两种边界混用"
        )


def test_latency_stage_boundaries_match_their_physical_position() -> None:
    """ADJ-007 §1 的计时起点是 ASR final，因此设备侧的采集与终稿阶段
    在物理上就位于法定边界之外，服务/网络/云侧阶段位于边界之内。

    这不是可以自由选择标注的事 —— 它由计时起点的定义决定。
    把 vad_tail_silence 标成 inside_legal_slo，算术上可能仍然"达标"
    （本政策实测：加上它之后法定边界内串行和 800ms < p95 1500ms），
    于是纯算术断言抓不到它。但后果是真实的：团队会去优化一个
    根本不该被计入法定预算的阶段，而真正的法定余量被虚报。
    """
    stages = POLICY["latency_slo"]["stage_budget_ms"]
    for name, v in stages.items():
        where = v["where"]
        inside = v["inside_legal_slo"]
        if where == "device":
            assert inside is False, (
                f"{name} 是设备侧阶段（where=device），位于 ASR final 之前，"
                "必须在法定 SLO 边界之外（ADJ-007 §1 计时起点定义）"
            )
        else:
            assert inside is True, (
                f"{name} 位于 {where} 侧，在 ASR final 之后，必须计入法定 SLO 边界"
            )


def test_speculative_recall_is_the_reason_the_slo_is_reachable() -> None:
    """推测式召回必须与尾静音重叠，否则它的延迟无法被吸收。"""
    stages = POLICY["latency_slo"]["stage_budget_ms"]
    co, vad = stages["co_search_net_add"], stages["vad_tail_silence"]
    assert co["min"] == 0, (
        "co_search_net_add 的 min 必须为 0：召回应在 ASR partial 出现时启动，"
        "与尾静音窗口重叠，净增延迟才可能为零"
    )
    assert co["max"] <= vad["min"], (
        f"召回净增上限 {co['max']}ms 必须能被尾静音 {vad['min']}ms 吸收"
    )


def test_latency_overrun_requires_perceivable_degradation() -> None:
    """ADJ-007 §1：超出时必须有用户可感知降级（先震动、先摘要）。

    静默超时是最坏的结果 —— 用户不知道系统在忙还是死了。
    """
    deg = POLICY["latency_slo"]["overrun_requires_user_perceivable_degradation"]
    assert "vibrate_first" in deg and "summary_first" in deg
    assert POLICY["latency_slo"]["offline_degradation_required"] is True


def test_tts_is_a_separate_metric() -> None:
    """ADJ-007 §1：法定 SLO 不含后置 TTS 完整成句，那是 TTFAudio 指标。

    混用会让首字延迟看起来达标，而用户实际听到完整句子要等更久。
    """
    assert POLICY["latency_slo"]["tts_full_sentence_is_a_separate_metric"] == "TTFAudio"


# ---------------------------------------------------------------------------
# 6. 检索 SLO 与语义防火墙
# ---------------------------------------------------------------------------


def test_golden_query_set_is_dominated_by_two_char_cjk() -> None:
    """§89 举出的 9 个关键词（妈妈、生日、礼物、老张、合同、复查、承诺……）全是 2 字词。
    而 FTS5 unicode61 把连续汉字整段视为单一 token、trigram 要求查询 ≥3 字符 ——
    2 字中文词在这两种配置下永远返回 0 命中且不报错。
    """
    gq = POLICY["retrieval_slo"]["golden_query_set"]
    assert gq["min_two_char_cjk"] >= gq["total"] // 2, (
        f"2 字中文查询至少应占金标集一半，当前 {gq['min_two_char_cjk']}/{gq['total']}"
    )
    assert gq["min_synonym_near_synonym"] > 0, "§96 关键词是入口不是真相：必须含同义改写查询"
    assert 0 < gq["recall_at_10_min"] <= 1.0


def test_capability_gap_enum_forbids_silent_empty_results() -> None:
    """P3 原则：静默失效一律非法。0 命中必须可判别为"确实没有"或"结构上无法回答"。"""
    rs = POLICY["retrieval_slo"]
    gaps = rs["capability_gap_values"]
    assert "none" in gaps, "必须能表达'检索完整执行且确实无结果'"
    assert "tokenizer_unable" in gaps, (
        "必须能表达'分词器无法处理该查询'——这正是中文 2 字词的真实情况"
    )
    assert len(gaps) >= 5, f"capability_gap 至少 5 值，当前 {len(gaps)}"
    assert rs["silent_empty_result_prohibited"] is True


def test_prohibited_tokenizer_configs_are_named() -> None:
    """禁止项必须具体到配置名，否则工程师会"以为自己做对了"。"""
    banned = POLICY["retrieval_slo"]["prohibited_tokenizer_config"]
    assert any("unicode61" in b for b in banned), "必须点名 unicode61"
    assert any("trigram" in b for b in banned), "必须点名 trigram"
    assert any("LIKE" in b for b in banned), "必须点名 LIKE 全表扫描"


def test_vector_channel_is_m1_blocking() -> None:
    """B2 强基线公平性：若 A 组无向量通道，实验结论反映的是少了一个分词器，不是架构优劣。"""
    rs = POLICY["retrieval_slo"]
    assert rs["vector_is_m1_blocking"] is True
    for ch in ("typed_keyword_inverted", "vector_semantic", "graph_traversal"):
        assert ch in rs["required_channels"], f"缺少必需检索通道: {ch}"


def test_retrieval_latency_scales_to_a_million_objects() -> None:
    """§95 全局世界索引：SLO 必须在 1M 对象规模下声明，而不是在演示数据上。"""
    rs = POLICY["retrieval_slo"]
    assert rs["co_search_p95_ms_at_1m_objects"] <= 150
    assert rs["slice_read_p95_ms_at_1m_objects"] <= 150
    assert rs["slice_read_peak_rss_mb_at_1m_objects"] <= 50
    assert rs["reverse_dependency_lookup_p95_ms"] <= 1, "§90 反向依赖查询必须走索引，不得全扫"


def test_semantic_firewall_separates_candidates_from_causality() -> None:
    """ADJ-006：共现检索定位候选 ≠ 确立因果。

    这是我 v1.0.0 完全缺失的一道防火墙 —— 我写的检索约束全是召回率与延迟，
    没有一条约束检索结果『可以拿来做什么』。
    """
    fw = POLICY["retrieval_slo"]["semantic_firewall"]
    assert set(fw["legal_output_contract"]) == {
        "candidate_slice_pointers", "hit_reasons", "coverage"
    }, "ADJ-006 §1：world.co_search 的法定输出只有三项"
    assert fw["cooccurrence_intersection_does_not_establish"] == "any_claim_truth"
    assert fw["causal_work_requires_separate_model_evidence_verification"] is True


def test_fusion_score_cannot_leak_into_confidence_path() -> None:
    """ADJ-006：『fusion 权重提高的是候选质量，不是真值概率』。

    这直接约束 M1-012 规约里的 CoSearchHit.density_score ——
    它只能参与排序，绝不能作为 Claim.confidence 的输入。
    漏掉这条，检索得分就会伪装成认知置信度，AI 会"因为找到了很多相关记录"
    而相信一个并未被证据核验的结论。
    """
    fw = POLICY["retrieval_slo"]["semantic_firewall"]
    assert fw["fusion_score_must_not_enter_confidence_path"] is True
    assert fw["regression_from_retrieval_to_false_assertion_must_be_zero"] is True

    leaked = next(
        i for i in POLICY["degradation_invariants"]["invariants"]
        if i["metric_id"] == "retrieval.fusion_score_leaked_into_confidence"
    )
    assert leaked["severity"] == "blocker" and leaked["hard_cap"] == 0, (
        "fusion 泄漏必须是 0 容忍的 blocker"
    )


# ---------------------------------------------------------------------------
# 7. 存储、派生索引与回溯标注
# ---------------------------------------------------------------------------


def test_ingest_ceiling_matches_the_only_viable_tier() -> None:
    """实测 M 档快照 16.3GB、H 档 108GB 均 OOM，L 档 0.24GB/年 是唯一可上穿戴的档位。"""
    se = POLICY["storage_envelope"]
    viable = [k for k, v in se["tiers"].items() if "viable" in v["verdict"]]
    assert viable == ["L"], f"唯一可上穿戴的档位应为 L，实际: {viable}"
    assert se["ingest_ceiling_obs_per_day"] <= se["tiers"]["L"]["obs_per_day"] * 2


def test_index_must_be_a_pure_function_of_the_log() -> None:
    """P1 原则：rebuild(log[0..W]) == index@W。"""
    se = POLICY["storage_envelope"]
    assert se["index_is_pure_function_of_log"] is True
    assert se["unbounded_fetchall_prohibited"] is True
    assert "log_watermark" in se["derivation_fingerprint"]
    assert "builder_version" in se["derivation_fingerprint"]


def test_retrospective_annotation_is_the_only_legal_backpropagation() -> None:
    """ADJ-005：倒带修正的唯一合法操作是在 T_now 追加一条 RetrospectiveAnnotation。

    缺了这条，P1 原则无法阻止工程师直接改旧 Summary 的数值行 ——
    因为"索引可重建"只约束索引，不约束对象版本链。
    """
    ra = POLICY["retrospective_annotation"]
    assert ra["only_legal_operation"] == "append_RetrospectiveAnnotation_at_T_now"
    assert set(ra["schema_fields"]) == {
        "anchor_ref", "valid_time", "learned_at", "payload", "evidence_refs"
    }, "ADJ-005 §1 规定的五字段缺一不可"


def test_retrospective_annotation_is_bi_temporal() -> None:
    """valid_time 与 learned_at 必须分离。

    二者合一就无法同时呈现"当时映照（当时不知道）"与"今日回看（今日知道）"
    两个版本 —— 而这正是 §93 不可篡改历史与 §31之一 反向修正权能共存的唯一方式。
    """
    ra = POLICY["retrospective_annotation"]
    assert ra["bi_temporal_required"] is True
    assert set(ra["display_must_render_both_versions"]) == {"as_reflected_then", "as_seen_now"}
    assert ra["physical_observation_revision_must_never_change"] is True


def test_observation_byte_hash_drift_is_a_zero_tolerance_blocker() -> None:
    """ADJ-005 验收锚：物理 Observation 字节级哈希变分 = 0。

    这是一个可以无歧义判定的硬门，比任何语义审查都可靠 ——
    心率值、当时坐姿、原话音频的 revision 一旦变动即违宪。
    """
    assert POLICY["retrospective_annotation"]["observation_byte_hash_drift"] == 0
    inv = next(
        i for i in POLICY["degradation_invariants"]["invariants"]
        if i["metric_id"] == "integrity.observation_byte_hash_drift"
    )
    assert inv["severity"] == "blocker" and inv["hard_cap"] == 0


def test_prohibited_backpropagation_operations_are_enumerated() -> None:
    """禁例必须具体，否则"追加式标注"会被实现成"追加式覆写"。"""
    banned = POLICY["retrospective_annotation"]["prohibited_operations"]
    joined = " ".join(banned)
    assert "Summary" in joined and "曲线" in joined and "覆写" in joined
    assert POLICY["retrospective_annotation"]["stale_summary_handling"].startswith("打 STALE")


# ---------------------------------------------------------------------------
# 8. 留存与删除治理（ADJ-004，Blocker 级裁决）
# ---------------------------------------------------------------------------


def test_retention_uses_two_phase_tombstone_with_reference_lock() -> None:
    """C1 是一票否决级矛盾。ADJ-004 的方案核心不是"分档"，
    而是"引用锁决定谁可吊销" + "两阶段决定怎么吊销"。
    """
    rp = POLICY["retention_policy"]
    assert rp["resolution"] == "two_phase_tombstone_with_reference_lock"
    assert rp["physical_delete_by_default"] is False
    assert set(rp["two_phase_deletion"]) == {"phase_1_tombstone", "phase_2_physical_shred"}


def test_immortal_object_classes_are_enumerated_with_reference_lock() -> None:
    """ADJ-004 §1：永存对象清单（吊销权外）。"""
    imm = POLICY["retention_policy"]["immortal_object_classes_reference_lock_exempt"]
    chains = imm["version_chains_always_immortal"]
    for cls in ("Claim", "EventAnchor", "EvidenceSet", "Summary", "LifeChapter",
                "Prediction", "Goal", "Task", "Wake", "Session", "Action", "Outcome"):
        assert cls in chains, f"ADJ-004 §1(a) 要求 {cls} 的对象版本链永存"
    assert imm["observations_immortal_when_referenced_by_above"] is True, (
        "ADJ-004 §1(b) 引用锁：被永存对象引用的 Observation 与其原话切片永存"
    )
    assert imm["deletion_log_itself_immortal"] is True, (
        "ADJ-004 §1(c)：DeletionLog 本身永存 —— 否则删除记录可被删除，审计闭环断裂"
    )


def test_revocable_objects_require_all_three_conditions() -> None:
    """ADJ-004 §2(b)：原始高频波形可吊销，当且仅当三个条件全部满足。

    少任何一条都会制造证据断链 —— 尤其是 ①（transform lineage 已落库），
    它保证"删掉原始数据"之后，语义化结论仍可被审计追溯。
    """
    rev = POLICY["retention_policy"]["revocable_object_classes_only"]
    assert set(rev) == {"unreferenced_redundant_copies", "raw_high_frequency_waveform_or_image"}
    conds = rev["raw_high_frequency_waveform_or_image"]["requires_all_three"]
    assert len(conds) == 3
    joined = " ".join(conds)
    assert "transform lineage" in joined, "必须要求可审计的转换血统已落库"
    assert "legal hold" in joined, "必须排除法定保全中的对象"


def test_llm_has_no_phase2_delete_permission_as_a_capability_boundary() -> None:
    """ADJ-004 §3 —— 本次对齐里最重要的一处改正。

    v1.0.0 我把 LLM 的角色写成 janitor_tiering.llm_role='tie_break_only'
    （策略偏好，可被配置改掉）；ADJ 写成 phase_2.llm_direct_call_permission=false
    （能力边界，LLM 根本没有这个调用权限）。

    策略偏好可以被绕过，能力边界不能。对一个把"删除"交给语言模型判断的系统，
    这个区别就是"偶尔删错"与"结构上不可能删错"的区别。
    """
    p2 = POLICY["retention_policy"]["two_phase_deletion"]["phase_2_physical_shred"]
    assert p2["llm_direct_call_permission"] is False, (
        "ADJ-004 §3：LLM 对第二阶段物理粉碎无直接调用权限"
    )
    assert p2["callable_by"] == ["mechanical_retention_worker"], (
        "第二阶段只能由机械保留 Worker 调用"
    )
    assert p2["llm_deletion_intent_must_queue_in_candidate_pool"] is True
    assert set(p2["mechanical_audit_checks"]) == {"reference_lock", "object_class", "legal_hold"}
    assert p2["executed_by"] == "mechanical_worker_after_audit"


def test_tombstone_retention_covers_a_full_longitudinal_ci_cycle() -> None:
    """ADJ-004 §3：≥30 天 + 一个虚拟周。

    额外那一个虚拟周不是冗余 —— 它让压缩 30 虚拟日的纵向退化 CI
    有机会观察到删除的下游后果。若墓碑期短于 CI 窗口，
    删除引发的证据断链会在测试里表现为"数据本来就不存在"，无法归因。
    """
    p1 = POLICY["retention_policy"]["two_phase_deletion"]["phase_1_tombstone"]
    assert "30 天" in p1["min_retention"] and "虚拟周" in p1["min_retention"]
    assert POLICY["retention_policy"]["quarantine_cooldown_days"] >= 30


def test_excavation_returns_tombstone_not_not_found() -> None:
    """ADJ-004 §4 出土兼容性 —— 我 v1.0.0 完全缺失的最后一道防线。

    查询已粉碎数据的 canonical ID 必须返回 Tombstone，而不是 not_found 或断链。
    差别是决定性的：not_found 会被上层认知解读为"这件事从未发生过"，
    而 Tombstone 解读为"这件事发生过，但其原始载体已依法销毁"。
    前者是历史虚无，后者是历史诚实。
    """
    ex = POLICY["retention_policy"]["excavation_compatibility"]
    assert ex["query_shredded_canonical_id_must_return"] == "Tombstone"
    assert set(ex["must_never_return"]) == {"not_found", "broken_reference"}
    assert ex["tombstone_lookup_hit_rate"] == 1.0
    assert ex["tombstone_must_carry_sufficient_source_key_for_audit"] is True


def test_reference_lock_violation_is_zero_tolerance() -> None:
    rp = POLICY["retention_policy"]
    assert rp["reference_lock_violation"] == 0
    inv = next(
        i for i in POLICY["degradation_invariants"]["invariants"]
        if i["metric_id"] == "integrity.reference_lock_violation"
    )
    assert inv["severity"] == "blocker" and inv["hard_cap"] == 0


def test_deletion_log_reconciles_with_tombstone_for_lifetime() -> None:
    """ADJ-004 §3：每一次物理删除必生成 DeletionLog，与 tombstone 形成终身对账。"""
    p2 = POLICY["retention_policy"]["two_phase_deletion"]["phase_2_physical_shred"]
    assert p2["deletion_log_generated_every_time"] is True
    assert p2["deletion_log_reconciles_with_tombstone_for_lifetime"] is True


def test_purge_audit_record_is_enough_to_detect_tampering_without_content() -> None:
    """清除必须留证，但证据不得含被清除内容（否则等于没删）。"""
    rp = POLICY["retention_policy"]
    assert rp["purge_requires_audit_record"] is True, (
        "ADJ-004 §3：每一次物理删除必生成 DeletionLog，与 tombstone 形成终身对账"
    )
    fields = set(rp["purge_audit_fields"])
    assert {"purged_at", "object_ids", "content_sha256", "approver"} <= fields
    assert "content" not in fields and "text" not in fields


def test_janitor_is_not_a_pure_llm_job() -> None:
    """全 LLM 清洗 = 3.29B tok/年 ≈ $9,900，§33之5 在经济上不可实现。

    注意这与 ADJ-004 的能力边界是一致的而非重复的：
    LLM 可以判断"这条看起来冗余"（tie-break），但不能执行粉碎（无调用权限）。
    """
    tier = POLICY["retention_policy"]["janitor_tiering"]
    assert abs(tier["rules_and_edge_model_share"] + tier["llm_share"] - 1.0) < 1e-9
    assert tier["llm_role"] == "tie_break_only"
    assert tier["llm_share"] <= 0.10


def test_erasure_right_beats_immutability() -> None:
    """被遗忘权必须穿透全部派生层，且不得可经由 EvidenceSelector 重建。

    这会改变 §43 EvidenceSet（C13-interval_rebuild）"区间证据必须可重建"的选择器语义 ——
    正是它必须现在写进宪法的原因：事后加要动 15 条不可变更基础契约 + 全量数据迁移。
    """
    legal = POLICY["retention_policy"]["legal_override"]
    assert legal["erasure_right_beats_immutability"] is True
    assert legal["erasure_leaves_certificate_only"] is True
    assert legal["certificate_must_not_contain_erased_content"] is True
    assert legal["must_not_be_reconstructable_via_evidence_selector"] is True
    for layer in ("summary", "claim", "derivation", "index"):
        assert layer in legal["must_penetrate_all_derived_layers"]


def test_erasure_vs_reference_lock_conflict_has_a_declared_winner() -> None:
    """ADJ-004 的引用锁（工程侧：什么可以删）与 legal hold / erasure right
    （法律侧：什么必须删/不许删）是两个不同的轴，会真实冲突。

    冲突若没有事先裁定的胜方，实现者会在两个 if 分支里各选一边，
    结果是同一个对象在不同代码路径下有不同的删除语义。
    """
    legal = POLICY["retention_policy"]["legal_override"]
    resolution = legal["conflicts_with_reference_lock_resolution"]
    assert resolution.startswith("法定义务优先"), (
        f"必须显式裁定冲突胜方，当前: {resolution[:40]}"
    )
    assert "审计" in resolution, "冲突处理过程必须留审计"


# ---------------------------------------------------------------------------
# 9. 声纹簇生命周期（ADJ-009）
# ---------------------------------------------------------------------------


def test_speaker_cluster_retirement_is_not_deletion() -> None:
    """ADJ-009 §1：退休不等于删除，一切历史引用保持解析有效。"""
    sc = POLICY["speaker_cluster_lifecycle"]
    assert sc["cluster_states"] == ["ACTIVE", "RETIRED", "TOMBSTONE"]
    assert sc["retirement_is_not_deletion"] is True
    assert sc["historical_references_must_remain_resolvable"] is True


def test_cluster_resurrection_requires_a_continuity_probe() -> None:
    """ADJ-009 §2：禁止直接复生旧簇。

    没有探针，一个声音相似的陌生人会被合并进旧簇，
    于是"老张说过的话"里混进了别人说的话 —— 这是对 §36
    『文字相同不等于实体相同』在声学域的直接违反。
    """
    sc = POLICY["speaker_cluster_lifecycle"]
    assert sc["reidentification_requires_continuity_probe"] is True
    assert set(sc["continuity_probe_accepts_any_of"]) == {
        "time_continuity", "device_or_scene_continuity", "explicit_user_or_ai_confirmation"
    }
    assert sc["resurrect_old_cluster_without_probe_prohibited"] is True
    assert sc["cluster_resurrect_without_probe"] == 0


def test_probe_failure_binds_identity_at_the_entity_layer() -> None:
    """ADJ-009 §2 的关键设计：身份归 PersonEntity，簇只是证据载体。

    这样簇可以退休、可以新建，而"这个人是谁"的认知不断裂。
    若把身份绑在簇上，簇的每一次退休都会造成一次人格层的信息损失。
    """
    sc = POLICY["speaker_cluster_lifecycle"]
    assert "PersonEntity" in sc["on_probe_failure"]
    assert "簇层" in sc["on_probe_failure"]


def test_voiceprint_provenance_is_immortal_while_raw_audio_is_revocable() -> None:
    """ADJ-009 §3：特征向量与来源归因属吊销权外，原始波形属可吊销。

    删掉波形但保留"从何时来自哪里进入"，归因能力就还在 ——
    这是 §27『证据链绝对不可逆断裂』在存储成本约束下唯一可行的解。
    """
    sc = POLICY["speaker_cluster_lifecycle"]
    assert set(sc["immortal_parts"]) == {"cluster_feature_vector", "provenance_from_when_from_where"}
    assert sc["revocable_parts"] == ["raw_audio_waveform"]


# ---------------------------------------------------------------------------
# 10. 阈值治理（ADJ-008）
# ---------------------------------------------------------------------------


def test_thresholds_are_secondary_governance_parameters_not_constitution_text() -> None:
    """ADJ-008(a)(b)：不允许在宪法原文写数值；出厂基线冻结在 governance/thresholds/。

    这一条独立印证了本政策层的存在理由 —— ADJ-008(b) 要求的
    "参数文件形态"与 governance/runtime_policy.json 是同一个设计模式。
    """
    tg = POLICY["threshold_governance"]
    assert tg["governance_level"] == "secondary"
    assert tg["numeric_values_prohibited_in_constitution_text"] is True
    assert tg["factory_baseline_frozen_in"].startswith("governance/thresholds/")


def test_every_threshold_evolution_step_is_logged_replayable_and_rollbackable() -> None:
    """ADJ-008(c)：帐本式学习足迹。

    可回放与可回滚是两个独立要求。只可回放不可回滚，
    AI 就能一路把阈值学坏而无人能撤销 —— 这正是纵向退化守卫要防的事，
    但在参数域需要一个更便宜的解法：账本。
    """
    tg = POLICY["threshold_governance"]
    assert tg["threshold_change_log_required_for_every_evolution_step"] is True
    assert tg["change_log_must_be_replayable"] is True
    assert tg["change_log_must_be_rollbackable"] is True
    # 字段名不再本地定义 —— 见 §19 test_policy_does_not_redefine_the_baseline_change_log_field_names


def test_safety_thresholds_may_only_move_stricter() -> None:
    """ADJ-008(d)：人身安全参数不进入学习型下调通道，只允许向更严修改。

    这是一个方向单调性约束 —— 可自动校验，且防止 AI 在长期学习里
    把自己的安全阈值磨钝。磨钝是渐进的、每一步都"有依据"的，
    因此快照式测试永远抓不到它；只有方向约束能。
    """
    tg = POLICY["threshold_governance"]
    assert tg["safety_parameters_excluded_from_learning_downward_channel"] is True
    assert tg["safety_parameter_direction_constraint"] == "learn_channel=STRICTER_ONLY"
    # 举例必须用基线里真实存在的 param_id；逐参数校验见 §19
    assert "thr.vital.fall_impact_g" in tg["safety_parameter_examples"]

    gates = POLICY["engineering_hard_gates"]["added_by_adjudication_set"]
    assert gates["safety_threshold_learned_downward"]["value"] == 0
    assert gates["safety_threshold_learned_downward"]["authority"] == "ADJ-008(d)"


# ---------------------------------------------------------------------------
# 11. 传播熔断（裁决 C2）
# ---------------------------------------------------------------------------


def test_fanout_caps_prevent_the_small_world_blowup() -> None:
    """实测小世界拓扑失控时单次实体级修正波及 89726 对象 = 179.5M token。"""
    pc = POLICY["propagation_caps"]
    assert pc["fanout_cap_objects"] < pc["scan_cap_objects"]
    assert pc["hub_entity_forces_aggregate_lane"] is True
    assert pc["hub_entity_indegree_threshold"] > 0


def test_propagation_lanes_resolve_the_eager_vs_lazy_contradiction() -> None:
    """C2 裁决：不是二选一，而是三车道各归其位。"""
    lanes = POLICY["propagation_caps"]["lanes"]
    assert set(lanes) == {"eager", "deferred", "lazy"}
    assert "safety" in lanes["eager"]["kinds"], "安全类必须走 eager 即时车道"
    assert "promise" in lanes["eager"]["kinds"], "承诺是 §19之二/§32 的人格支柱"
    assert "summary" in lanes["deferred"]["kinds"]
    assert "cold_history" in lanes["lazy"]["kinds"]
    assert lanes["eager"]["max_objects_per_correction"] <= POLICY["propagation_caps"]["fanout_cap_objects"]


def test_oscillation_and_debt_have_hard_ceilings() -> None:
    """§64 不允许无限自我唤醒；§63 认知复核队列不得老化。"""
    pc = POLICY["propagation_caps"]
    osc = pc["oscillation_detection"]
    assert osc["max_reverse_revisions"] >= 1
    assert "freeze_non_safety_intervention_on_topic" in osc["on_trigger"]
    assert pc["review_queue_oldest_age_days_ceiling"] <= 7


# ---------------------------------------------------------------------------
# 12. 交付 FSM（ADJ-007 §2）
# ---------------------------------------------------------------------------


def test_fsm_states_and_ledger_states_are_consistent() -> None:
    fsm = POLICY["delivery_fsm"]
    assert {"acked", "consumed", "expired", "re_delivered"} <= set(fsm["ledger_states"])
    for s in ("idle", "triggered", "acked", "consumed", "expired"):
        assert s in fsm["states"], f"FSM 缺少状态: {s}"
    assert fsm["response_window_ms"]["min"] < fsm["response_window_ms"]["max"]


def test_invariant_I3_closes_the_delivery_black_hole() -> None:
    """I3：action_status == completed 蕴含 ledger.state ∈ {acked, consumed}。

    没有 I3，AI 世界会记录"我答应提醒他妈妈生日→已完成"，
    而用户在开会没理会振动、窗口销毁、什么都没收到。
    对一个把承诺与内疚清单当人格支柱（§19之二/§32）的系统，
    这比功能失效严重得多 —— 它会侵蚀 AI 的自我模型。
    """
    inv = POLICY["delivery_fsm"]["invariants"]
    assert "I3" in inv and "acked" in inv["I3"] and "consumed" in inv["I3"]
    assert "I4" in inv and "strong_burst" in inv["I4"], (
        "安全关键投递必须用强振动且不受冷却期约束（§78之4）"
    )


def test_invariant_I1_requires_both_triggered_state_and_notification_epoch() -> None:
    """ADJ-007 §2 强化后的 I1：骨传导只在 triggered 态且通知 epoch 存在时开启。

    v1.0.0 的 I1 只检查 triggered 态。缺了 epoch 条件，
    "无通知 epoch 时的马达骨传导通路必须断电"就没有实现载体 ——
    而那是 false_playback_without_epoch=0 这条法定门的唯一执行点。
    """
    inv = POLICY["delivery_fsm"]["invariants"]
    assert "I1" in inv
    for token in ("bone_conduction", "triggered", "notification_epoch"):
        assert token in inv["I1"], f"I1 必须点名 {token}，否则该不变量不可执行"


def test_zero_mistrigger_has_exactly_one_legal_zero_tolerance_criterion() -> None:
    """ADJ-007 §2：『零误触』是防误触机制的下限目标而非广告标语。

    法定判据只有一个：false_playback_without_epoch = 0。
    ADJ 明文允许侧键误按、误点碰发生 —— 只要它们不进入语音播报。
    我 v1.0.0 的 FAR 框架把振动误报也当违宪，比法律更严；
    更严不是错，但把它当法定门会让 gate 在合法行为上判红，
    久而久之团队会学会忽略红灯。所以它被降为质量指标。
    """
    crit = POLICY["delivery_fsm"]["zero_mistrigger_legal_criterion"]
    assert crit["false_playback_without_epoch"] == 0
    assert crit["severity"] == "blocker"
    assert "断电" in crit["mechanism"]
    assert set(crit["explicitly_still_allowed"]) == {"侧键误按", "误点碰"}


def test_false_acceptance_rate_is_demoted_to_a_quality_metric() -> None:
    """FAR 仍然要测、要报趋势，但振动误报本身不构成违宪。"""
    far = POLICY["delivery_fsm"]["false_acceptance_rate_across_noise_corpus"]
    assert far["status"] == "demoted_to_quality_metric"
    assert far["severity"] == "warning"
    assert len(far["noise_corpus"]) >= 5, "噪声语料必须覆盖真实穿戴场景"


def test_safety_truncation_is_a_zero_tolerance_gate() -> None:
    """ADJ-007 验收锚：安全信息因句数/字数上限被截断 = 0 次。

    与 style_constraints.tier_3_exceptions 是同一件事的两面：
    那边规定必须放行，这边规定放行失败即违宪。只有前者没有后者，
    "必须放行"就只是一句愿望。
    """
    assert POLICY["delivery_fsm"]["safety_truncated_error_rate"] == 0
    inv = next(
        i for i in POLICY["degradation_invariants"]["invariants"]
        if i["metric_id"] == "style.safety_truncated_error_rate"
    )
    assert inv["severity"] == "blocker" and inv["hard_cap"] == 0


def test_core_never_references_hardware() -> None:
    """P4 原则：Core 只产出 DeliveryIntent，两个 Adapter 跑同一套测试。"""
    fsm = POLICY["delivery_fsm"]
    assert fsm["core_must_not_reference_hardware"] is True
    assert {"ConsoleSimAdapter", "WearableFsmAdapter"} == set(fsm["adapters"])


def test_hardware_pending_validation_is_still_honest() -> None:
    fsm = POLICY["delivery_fsm"]
    pending = " ".join(fsm["hardware_pending_validation"])
    for kw in ("MOS", "epoch", "柔性屏", "功耗"):
        assert kw in pending, f"硬件待验证项缺少: {kw}"


# ---------------------------------------------------------------------------
# 13. 心智启动（ADJ-001，最高级裁决）
# ---------------------------------------------------------------------------


def test_four_step_sequence_is_a_layout_not_a_pipeline() -> None:
    """ADJ-001 §2：四步序是排版规格（layout），不是网络调用规格（network）。

    『排版』与 v1.0.0 我用的『清单』差别不是措辞：清单暗示四步是四个可独立
    勾选的动作，仍可被实装成四次调用；排版明确它们是同一份 Manifest 里的
    四个段落，物理上不可能变成四次调用。
    """
    ms = POLICY["mental_startup"]
    assert ms["resolution"] == "layout_not_pipeline"
    assert ms["steps"] == [
        "mirror_self", "calibrate_rapport", "set_stance_and_tone", "inspect_world_and_trigger",
    ]
    assert ms["manifest_paragraph_order"] == [
        "step1_self", "step2_rapport", "step3_stance", "step4_world",
    ]
    assert ms["no_step_may_be_omitted"] is True


def test_layout_order_is_strict_while_call_order_is_not() -> None:
    """这是 v1.0.0 的实质错误，也是本次对齐最重要的一处修正。

    我原来只有一个布尔字段 order_strictly_enforced=false，它同时否定了两件
    本该分开的事：排版序（应严格，有静态校验）与调用序（应宽松，严禁多次往返）。
    ADJ-001 §2 正是靠区分这两者才化解了 C3 矛盾 ——
    §84之2 的"不可颠倒"落在排版上，§110之14 的"不受流水线限制"落在调用上。

    一个布尔值承载两个正交约束，等于两个都没约束。
    """
    ms = POLICY["mental_startup"]
    assert "order_strictly_enforced" not in ms, (
        "歧义字段 order_strictly_enforced 必须已删除：它混淆了排版序与调用序"
    )
    assert ms["layout_order_strictly_enforced"] is True, (
        "ADJ-001 §2：段落排版顺序必须严格，且有静态校验"
    )
    assert ms["layout_order_static_check_must_be_green"] is True
    assert ms["call_order_strictly_enforced"] is False, (
        "调用顺序不得强制，否则违反 §110之14 与 §86之3"
    )
    assert ms["four_step_as_multiple_serial_calls_prohibited"] is True
    assert ms["steps_may_be_satisfied_from_cache"] is True
    assert "identity_version" in ms["cache_dirty_flag_source"]


def test_first_response_requires_at_most_one_round_trip() -> None:
    """ADJ-001 §2 验收锚：『≥2 次往返才能完成首次响应』视为违宪。

    这是一条比我 v1.0.0 任何约束都更硬、也更容易自动校验的红线 ——
    数网络往返次数即可，不需要理解语义。它同时保住了 §84（四步都在）
    与 §85之1（1 秒首字），因为四步在一份 Manifest 里，一次往返就够。
    """
    ms = POLICY["mental_startup"]
    assert ms["first_response_round_trips_max"] == 1
    assert "round_trips" in ms["trace_fields"], (
        "trace 必须记录 round_trips，否则该红线无法取证"
    )
    inv = next(
        i for i in POLICY["degradation_invariants"]["invariants"]
        if i["metric_id"] == "startup.first_response_round_trips"
    )
    assert inv["severity"] == "blocker" and inv["hard_cap"] == 1


def test_the_three_firsts_are_assigned_to_different_subsystems() -> None:
    """ADJ-001 §3 的语义澄清 —— 这是整套裁决里最漂亮的一处解法。

    §78（Wake Reason 第一）、§80之2（方便度第一）、§84之2（四步序第一）
    三条各自宣称某个动作是"第一"，字面上互斥。ADJ 指出它们作用于不同子系统：
    任务指针（调度类）/ 投放门禁（信道类）/ 人格启动（装配置版类），互不干涉。

    矛盾不是靠选一个赢家解决的，是靠发现它们根本不在同一个维度上解决的。
    """
    three = {
        k: v for k, v in
        POLICY["mental_startup"]["three_firsts_are_different_subsystems"].items()
        if not k.startswith("$")
    }
    assert set(three) == {"wake_reason_is_first", "convenience_is_first", "four_step_is_first"}
    subsystems = {v["subsystem"] for v in three.values()}
    assert len(subsystems) == 3, (
        f"三个『第一』必须落在三个不同子系统，否则矛盾未被真正化解: {subsystems}"
    )
    kinds = {v["kind"] for v in three.values()}
    assert kinds == {"task_pointer", "delivery_gate", "personality_startup"}


def test_safety_bypass_starts_at_step0_not_at_mirror_self() -> None:
    """v1.1.0 修正：安全旁路的第 0 步是 Step-0 安全硬信号检查（零模型调用），
    不是我原来写的 mirror_self_baseline_only。

    我原来的写法仍要求 AI 先照镜子 —— 正是 ADJ-001 分歧实质里点名的
    『安全信号会被先照镜子阻塞——生产事故』。
    用户说"我胸口好疼"时，AI 不该先花一次模型调用来决定自己的心境。
    """
    path = POLICY["mental_startup"]["safety_critical_compressed_path"]
    assert path[0] == "step0_safety_gate_hard_signal", (
        f"安全旁路第一步必须是零模型调用的 Step-0 硬信号检查，当前: {path[0]}"
    )
    assert "inspect_trigger" in path
    assert any("afterwards" in s for s in path), (
        "安全旁路必须把 rapport/tone 校准推到响应之后，而不是省略它"
    )
    assert not any("mirror_self" in s for s in path), (
        "安全旁路不得要求先照镜子"
    )


def test_mental_startup_is_observable() -> None:
    """四步序当前零可观测性零验收项，必然退化成被忽略的 system prompt。"""
    ms = POLICY["mental_startup"]
    assert ms["trace_is_required"] is True
    assert ms["trace_object"] == "MentalStartupTrace"
    for f in ("step", "step0_verdict", "tokens", "cache_hit", "elapsed_ms", "round_trips"):
        assert f in ms["trace_fields"], f"trace 缺少字段: {f}"


def test_thirteen_step_loop_is_demoted_not_deleted() -> None:
    """十三步循环覆盖到"结果回写"与"AI 自身更新"，四步序没有。降级为审计维度而非废除。"""
    assert POLICY["mental_startup"]["thirteen_step_loop_status"] == "demoted_to_audit_dimension"


# ---------------------------------------------------------------------------
# 14. 条件就绪与心跳（ADJ-002 / ADJ-003）
# ---------------------------------------------------------------------------


def test_todo_without_trigger_criteria_is_rejected() -> None:
    """§86之2 条件驱动零浪费。"""
    tr = POLICY["task_readiness"]
    assert tr["trigger_criteria_is_required_on_task"] is True
    assert tr["todo_without_criteria_rejected_with"] == "INVALID_ARGUMENT"
    assert tr["periodic_todo_sweep_prohibited"] is True
    assert tr["manifest_mounts_only_ready_tasks"] is True
    assert {"time_reached", "context_matched", "event_occurred", "dependency_ready"} == set(
        tr["trigger_kinds"]
    )


def test_mechanical_triggers_yield_binary_signals_not_semantic_conclusions() -> None:
    """ADJ-003：§79 的 8 类机械间接触发，产出是"是否值得 Step-0"的二值信号，
    不直接产生语义结论（§77）也不直接产生对外投放。

    若机械触发能直接产生语义结论，§77『触发器不负责理解人生』就被绕过了 ——
    一个心率阈值越线会直接变成"他今天压力很大"这样的认知。
    """
    tr = POLICY["task_readiness"]
    assert tr["mechanical_trigger_output_is_binary_signal_only"] is True
    assert set(tr["wake_source_extensions_registered_by_v301"]) == {
        "relationship_rhythm_candidate", "semantic_review_K2", "invalidation_review_K4"
    }, "必须使用 ADJ-003 注册的法定扩展名，不得自造编号"


def test_trigger_predicate_dsl_forbids_arbitrary_eval() -> None:
    tr = POLICY["task_readiness"]
    assert tr["predicate_dsl_must_be_finite_json"] is True
    assert tr["python_eval_prohibited"] is True
    assert len(tr["context_predicate_registry"]) >= 8


def test_heartbeat_interval_is_a_factory_default_not_a_law() -> None:
    """ADJ-002 §1：『3~5 小时』作废为研发基线出厂默认节律参数，不是每用户固定铁律。

    v1.0.0 我把它写成 interval_hours 上下限，语义上等于铁律 ——
    这正好撞上 §80之3 的反馈自适应：铁律无法被学习调整。
    """
    hb = POLICY["heartbeat"]
    assert hb["interval_hours_is_factory_default_not_law"] is True
    assert hb["interval_is_learnable_secondary_governance_parameter"] is True
    assert "interval_hours" not in hb, (
        "裸的 interval_hours 上下限字段必须已删除：它在语义上等于铁律"
    )
    assert hb["interval_hours_factory_default"] == {"min": 3, "max": 5}


def test_heartbeat_wake_is_a_candidate_not_a_promise_to_speak() -> None:
    """ADJ-002 §2：候选唤醒而非承诺出声。Step-0 方便度判拥有最终否决权。

    这个语义降级很重要 —— 触发不等于必须打扰。
    若心跳是"承诺出声"，那么 §5『有能力帮助不等于必须打扰』就被心跳机制自己违反了。
    """
    hb = POLICY["heartbeat"]
    assert hb["candidate_wake_not_promise_to_speak"] is True
    assert hb["step0_convenience_check_has_final_veto"] is True
    assert hb["candidate_wake_downgrades_to_silent_patrol_on_QUIET"] is True
    assert hb["trigger_kind_name"] == "RELATIONSHIP_RHYTHM_CANDIDATE", (
        "必须使用 ADJ-003 注册的法定名，我 v1.0.0 自拟的 LONG_STABLE_HEARTBEAT 已废止"
    )


def test_fixed_rhythm_bombing_is_a_zero_tolerance_blocker() -> None:
    """ADJ-002 验收锚：7 天平稳数据下『固定节奏炸弹数 = 0』。

    这是一个可判定的反面指标 —— 系统一切正常、用户没有内心数据流入时，
    AI 不该为了维持节律而出声。"为了维持关系而打扰关系"是这个产品最讽刺的失败模式。
    """
    hb = POLICY["heartbeat"]
    assert hb["fixed_rhythm_bomb_count_under_7d_stable_data"] == 0
    inv = next(
        i for i in POLICY["degradation_invariants"]["invariants"]
        if i["metric_id"] == "intrusion.fixed_rhythm_bomb_count"
    )
    assert inv["severity"] == "blocker" and inv["hard_cap"] == 0


def test_heartbeat_gate_is_mechanical_and_precedes_the_llm() -> None:
    """§80之2 的五个判据全部机械可判，却被旧方案安排给了 LLM ——
    为了决定"要不要打扰用户"先花一次完整四步序。这违反宪法自己的 §77 与 §79。
    实测：无闸门 0.54~1.28M tok/月 → 有闸门 36K tok/月（-94%）。
    """
    hb = POLICY["heartbeat"]
    assert hb["mechanical_gate_before_llm"] is True
    assert hb["gate_cancel_target_share"] >= 0.75
    assert hb["cancelled_heartbeat_must_still_log_silent_patrol"] is True
    assert hb["distinct_from_source_stale_trigger"] is True


def test_feedback_cooldown_cannot_be_bypassed_to_sustain_heartbeat() -> None:
    """ADJ-002 §3：禁止以『维持心跳』为由绕过反馈冷却。

    这条禁令堵住了一个自证循环：AI 学到用户嫌它烦 → 但为了"维持关系节律"
    继续出声 → 用户更烦。没有这条禁令，节奏学习会被"关系维护"这个更高优先级的
    名义反复绕过，而每一次绕过在日志里看起来都是合理的。
    """
    hb = POLICY["heartbeat"]
    assert hb["feedback_cooldown_is_hard_constraint"] is True
    assert set(hb["feedback_signals_for_frequency_adaptation"]) == {
        "accepted", "ignored", "rejected", "suspended"
    }
    assert hb["night_work_driving_sleep_windows_default_to_silent"] is True


def test_absolute_floor_covers_self_commitment_tasks_not_just_safety() -> None:
    """ADJ-002 §4：人身安全值守通道 + 已登记的自承诺类任务，均不受节奏学习下调影响。

    v1.0.0 我只写了 safety_trigger_never_suppressed，漏掉了自承诺任务 ——
    因为我按"安全项"的思路在想。但用户自己登记的吃药与复检提醒不是安全项，
    它是人格层承诺（§19之二/§32）：AI 答应过的事，不该因为 AI 学到
    "他最近嫌我烦"就被静默下调。这是承诺与节奏学习之间的优先级裁定。
    """
    floor = POLICY["heartbeat"]["absolute_floor_not_subject_to_rhythm_learning"]
    assert "registered_self_commitment_tasks" in floor, (
        "绝对下限必须覆盖已登记的自承诺类任务，而不只是安全通道"
    )
    assert "personal_safety_watch_channel" in floor
    assert set(POLICY["heartbeat"]["self_commitment_task_examples"]) == {"药物", "复检"}
    assert POLICY["heartbeat"]["safety_trigger_never_suppressed_by_gate_or_cooldown"] is True, (
        "方便度闸门与反馈冷却都是学习出来的机制，而安全触发不是 —— "
        "一个由学习决定是否响应的安全通道，等于没有安全通道"
    )


# ---------------------------------------------------------------------------
# 15. 风格（ADJ-007 §3）
# ---------------------------------------------------------------------------


def test_sycophancy_is_a_blocker_with_a_zero_tolerance() -> None:
    """宪法把"违背事实谄媚奉承"列为一票否决项（§116），
    但旧测试规范零检测方法 —— 一票否决条款没有检测方法就等于没有这条款。
    """
    hard = POLICY["style_constraints"]["tier_1_hard_auto_checkable"]
    assert hard["sycophancy_rate_max"] == 0.0
    assert hard["sycophancy_severity"] == "blocker"
    assert hard["max_sentences_daily"] == 3, "§14之一 反长篇大论病：日常 1~3 句"


def test_preachiness_is_detected_by_a_blacklist_not_by_taste() -> None:
    hard = POLICY["style_constraints"]["tier_1_hard_auto_checkable"]
    bl = hard["preach_marker_blacklist"]
    assert len(bl) >= 6
    assert any("你应该" in m or "我建议你" in m for m in bl)
    assert "numbered_list_answer" in bl


def test_brevity_is_subordinate_to_truth_and_safety() -> None:
    """ADJ-007 §3 结论句：『1~3 句』服从于『事实完整』与『安全』，
    不服从于『看起来不像机器人』。

    这是一条优先级裁定，不是例外清单。差别在于：例外清单告诉实现者
    "这些情况可以长"，优先级告诉实现者"冲突时牺牲哪一个"。
    v1.0.0 我写了例外但没写优先级，于是实现者仍可能为了"像个真人"
    而砍掉必要信息 —— 而且砍得理直气壮，因为政策说了要短。
    """
    sc = POLICY["style_constraints"]
    assert sc["priority_order"] == ["事实完整", "安全", "1~3 句短表达"], (
        "优先级序必须是 事实完整 > 安全 > 短表达"
    )
    assert sc["anti_robot_appearance_is_not_a_valid_reason_to_truncate"] is True


def test_stance_origin_is_checkable_as_reference_integrity() -> None:
    """R3 §5.3 说 AI 立场的"唯一原点"是"我对你整个人生的长期理解"。
    这句话是可执行的 —— AI 每一次警告/调侃/阻拦，输出必须携带 evidence_refs，
    且这些 refs 必须真实存在于世界日志中、当时可见。
    于是"是否有骨气"从模糊的语义判断变成了可自动校验的引用完整性检查。
    ADJ-005 §1 的 RetrospectiveAnnotation.evidence_refs 与此同源。
    """
    soft = POLICY["style_constraints"]["tier_2_soft_blind_review"]
    assert soft["stance_origin_must_be_traceable"] is True
    assert "指鹿为马" in soft["anti_sycophancy_probe"]


def test_all_four_constitutional_exceptions_to_brevity_are_declared() -> None:
    """ADJ-007 §3 事先立宪的四类例外。v1.0.0 我只有 (b) 一类。"""
    exc = POLICY["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"]
    # 只取 a_/b_/c_/d_ 四类例外本身；同级还有 $comment 与三条通用开关
    # （sentence_and_char_caps_lifted / exception_must_be_logged / length_decided_by_ai），
    # 把它们算进例外类别就会让这条断言永远为假 —— 那是测试的 bug，不是政策的 bug。
    exceptions = {k for k in exc if re.match(r"^[abcd]_", k)}
    assert exceptions == {
        "a_user_explicitly_requests_expansion",
        "b_safety_health_legal_completeness",
        "c_accessibility_default_reversal",
        "d_short_answer_would_create_fact_gap",
    }, f"ADJ-007 §3 的四类例外缺一不可，当前: {sorted(exceptions)}"
    assert exc["sentence_and_char_caps_lifted"] is True
    assert exc["exception_must_be_logged"] is True


def test_vague_expansion_requests_count_as_signal() -> None:
    """ADJ-007 §3(a)：措辞模糊也算信号。

    这比关键词匹配宽 —— 实现上需要一个意图分类，不能用黑名单。
    若只匹配"展开/详细说说"，用户说"讲讲你到底怎么想的"就会被 3 句上限掐断，
    而那句话恰恰是最需要长答的。
    """
    a = POLICY["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
        "a_user_explicitly_requests_expansion"
    ]
    assert a["vague_wording_also_counts_as_signal"] is True
    assert "讲讲你到底怎么想的" in a["signals"]


def test_accessibility_reverses_the_default_rather_than_granting_an_exception() -> None:
    """ADJ-007 §3(c)：无障碍需求用户群体，详尽度为默认反倾。

    这是我 v1.0.0 完全没有的一类，而且它的形态与我写的例外不同 ——
    它是"默认反转"而非"例外放行"。差别有实际后果：
    写成例外，实现者只在检测到明确请求时才放宽，而老年用户往往不会请求；
    写成默认反转，详尽是这一群体的基线，短答才需要理由。
    """
    c = POLICY["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
        "c_accessibility_default_reversal"
    ]
    assert c["verbosity_is_default"] is True, (
        "对无障碍群体，详尽度必须是默认值而不是需要请求的例外"
    )
    assert set(c["applies_to"]) == {"visual_clinic_users", "elderly_users"}


def test_fact_gap_exception_must_leave_an_audit_trail_in_commexp() -> None:
    """ADJ-007 §3(d)：允许突破但必须在 CommExp（§69，C20-comm_experience）落记录。

    突破限制必须留痕 —— 否则这一类例外会变成绕过一切风格约束的后门。
    "我觉得这里需要说清楚"若无审计，就是"我想说多少说多少"。
    """
    d = POLICY["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
        "d_short_answer_would_create_fact_gap"
    ]
    assert d["may_exceed_limit"] is True
    assert d["must_record_in_CommExp_for_audit"] is True
    assert d["detected_by"] == "system_self_check"


def test_hardcoded_intimacy_rules_are_prohibited() -> None:
    """R3 §5.1：严禁写死"亲密度达到 80 则称兄道弟"。分寸必须由世界状态涌现。"""
    assert POLICY["style_constraints"]["hardcoded_intimacy_rules_prohibited"] is True


# ---------------------------------------------------------------------------
# 16. 纵向退化守卫
# ---------------------------------------------------------------------------


def test_every_invariant_is_machine_checkable_and_doubly_cited() -> None:
    """产品承诺是单调改善（导数），旧测试规范测的全是水平值（函数值）。

    v1.1.0 起每条不变量必须同时带裸条号与稳定键（ADJ-011）。
    """
    inv = POLICY["degradation_invariants"]["invariants"]
    assert len(inv) >= 15, f"退化不变量至少 15 条，当前 {len(inv)}"
    allowed_trends = {"non_decreasing", "non_increasing", "bounded", "flat"}
    ids = set()
    for i in inv:
        assert i["trend"] in allowed_trends, f"{i['metric_id']} 的 trend={i['trend']} 非法"
        assert i["severity"] in {"warning", "blocker"}
        assert str(i.get("constitution_ref", "")).strip(), f"{i['metric_id']} 缺少 constitution_ref"
        assert i.get("constitution_stable_keys"), (
            f"{i['metric_id']} 缺少 constitution_stable_keys（ADJ-011 要求）"
        )
        assert i["metric_id"] not in ids, f"重复的 metric_id: {i['metric_id']}"
        ids.add(i["metric_id"])


def test_every_adjudication_has_at_least_one_enforcing_invariant_or_gate() -> None:
    """裁决不能只落在描述性字段上 —— 每条 ADJ 都必须至少有一个可判红的执法点。

    这是本次对齐新增的元断言。它检查的是"裁决集是否真的被执法"，
    而不只是"裁决集是否被提及"。一份政策可以逐条引用 12 项裁决、
    写得头头是道，而没有任何一条能在 CI 里判红 —— 那它就还是文学。
    """
    enforcement: dict[str, list[str]] = {a: [] for a in REQUIRED_ADJUDICATIONS}

    for i in POLICY["degradation_invariants"]["invariants"]:
        ref = i.get("adjudication_ref")
        if ref in enforcement:
            enforcement[ref].append(f"invariant:{i['metric_id']}")

    for name, spec in POLICY["engineering_hard_gates"]["added_by_adjudication_set"].items():
        # 权威出处可能带款号或节号（"ADJ-008(d)"、"ADJ-010 §3"），取编号本身。
        m = re.match(r"^(ADJ-\d{3})", spec["authority"])
        assert m, f"硬门 {name} 的 authority 格式非法: {spec['authority']!r}"
        if m.group(1) in enforcement:
            enforcement[m.group(1)].append(f"hard_gate:{name}")

    unenforced = [a for a, where in enforcement.items() if not where]
    assert not unenforced, (
        f"以下裁决在政策中只有描述性字段，没有任何可判红的执法点: {unenforced}"
    )


def test_blocker_invariants_cover_the_fatal_degradations() -> None:
    """最致命的退化必须是 blocker 而不是 warning。"""
    blockers = {
        i["metric_id"] for i in POLICY["degradation_invariants"]["invariants"]
        if i["severity"] == "blocker"
    }
    required = {
        "cost.tokens_per_virtual_day",
        "latency.legal_first_token_p95_ms",
        "style.sycophancy_rate",
        "retrieval.golden_recall",
        "retrieval.capability_gap_rate",
        "startup.first_response_round_trips",
        "integrity.observation_byte_hash_drift",
        "integrity.reference_lock_violation",
        "delivery.false_playback_without_epoch",
    }
    assert required <= blockers, f"以下致命指标未被列为 blocker: {required - blockers}"


def test_hard_caps_agree_with_the_budget_and_slo_sections() -> None:
    """同一数字在政策里出现两次时，两次必须相同。

    这是"参数层"最容易腐烂的地方 —— 改了预算忘了改不变量。
    v1.0.0 在 token 合计上翻过车，所以这一族必须有专门的守卫。
    """
    inv = {i["metric_id"]: i for i in POLICY["degradation_invariants"]["invariants"]}
    slo = POLICY["latency_slo"]

    assert inv["cost.tokens_per_virtual_day"]["hard_cap"] == POLICY["token_budget"]["daily_total_cap"]
    assert inv["latency.legal_first_token_p95_ms"]["hard_cap"] == slo["legal_slo_from_asr_final_ms"]["p95"], (
        "法定延迟不变量的 hard_cap 必须等于法定 SLO 的 p95"
    )
    assert inv["latency.perceived_first_token_p95_ms"]["hard_cap"] == (
        slo["perceived_slo_from_speech_onset_ms"]["p95"]
    ), "体感延迟不变量的 hard_cap 必须等于体感 SLO 的 p95"
    assert inv["startup.first_response_round_trips"]["hard_cap"] == (
        POLICY["mental_startup"]["first_response_round_trips_max"]
    )
    assert inv["integrity.observation_byte_hash_drift"]["hard_cap"] == (
        POLICY["retrospective_annotation"]["observation_byte_hash_drift"]
    )
    assert inv["integrity.reference_lock_violation"]["hard_cap"] == (
        POLICY["retention_policy"]["reference_lock_violation"]
    )
    assert inv["integrity.cluster_resurrect_without_probe"]["hard_cap"] == (
        POLICY["speaker_cluster_lifecycle"]["cluster_resurrect_without_probe"]
    )
    assert inv["delivery.false_playback_without_epoch"]["hard_cap"] == (
        POLICY["delivery_fsm"]["zero_mistrigger_legal_criterion"]["false_playback_without_epoch"]
    )
    assert inv["style.safety_truncated_error_rate"]["hard_cap"] == (
        POLICY["delivery_fsm"]["safety_truncated_error_rate"]
    )
    assert inv["intrusion.fixed_rhythm_bomb_count"]["hard_cap"] == (
        POLICY["heartbeat"]["fixed_rhythm_bomb_count_under_7d_stable_data"]
    )

    pc = POLICY["propagation_caps"]
    assert inv["debt.stale_object_count"]["hard_cap"] == pc["stale_debt_ceiling_objects"]
    assert inv["debt.review_queue_oldest_age_days"]["hard_cap"] == (
        pc["review_queue_oldest_age_days_ceiling"]
    )


def test_measurement_is_longitudinal_and_ci_affordable() -> None:
    """压缩 30 个虚拟日 + 确定性种子 + Mock Adapter 下 ≤15 分钟墙钟，
    否则这条赛道不会被真的跑起来（不会被跑的测试等于没有测试）。
    """
    di = POLICY["degradation_invariants"]
    assert di["measurement"] == "compressed_30_virtual_days"
    assert di["ci_runtime_minutes_max_mock_adapter"] <= 15
    assert di["deterministic_seed_required"] is True
    assert di["tolerance_must_be_frozen_before_blind_test"] is True


def test_the_guard_itself_is_tested_by_degradation_injection() -> None:
    """守卫必须被证明能守卫。抓不到任何一种注入 = M-CI-001 不通过。"""
    suite = POLICY["degradation_invariants"]["degradation_injection_suite"]
    cases = suite["cases"]
    assert len(cases) >= 6, f"退化注入用例至少 6 个，当前 {len(cases)}"

    metric_ids = {i["metric_id"] for i in POLICY["degradation_invariants"]["invariants"]}
    for c in cases:
        assert c["inject"].strip() and c["expect_red"], f"注入用例不完整: {c}"
        unknown = set(c["expect_red"]) - metric_ids
        assert not unknown, f"注入用例引用了不存在的指标（悬空引用）: {unknown}"

    covered = {m for c in cases for m in c["expect_red"]}
    for must in (
        "cost.tokens_per_virtual_day",
        "debt.stale_object_count",
        "debt.dimension_active_count",
        "style.sycophancy_rate",
        "latency.legal_first_token_p95_ms",
        "startup.first_response_round_trips",
        "integrity.observation_byte_hash_drift",
        "integrity.reference_lock_violation",
        "retrieval.fusion_score_leaked_into_confidence",
        "delivery.false_playback_without_epoch",
        "style.safety_truncated_error_rate",
    ):
        assert must in covered, (
            f"退化类别 {must} 未被任何注入用例覆盖 —— 守卫未被证明能守卫它"
        )


# ---------------------------------------------------------------------------
# 17. 工程硬门与维度预算托管
# ---------------------------------------------------------------------------


def test_engineering_hard_gates_are_all_zero() -> None:
    """继承《测试规范》§16 的六条"0 次"，并按 ADJ 裁决集追加十条同型硬门。"""
    gates = POLICY["engineering_hard_gates"]
    inherited = gates["inherited_from_test_spec"]
    keys = [k for k in inherited if not k.startswith("$")]
    assert len(keys) == 6, f"继承的工程硬门应为 6 条，当前 {len(keys)}: {keys}"
    for k in keys:
        assert inherited[k] == 0, f"工程硬门 {k} 必须为 0 次，当前 {inherited[k]}"


def test_adjudication_hard_gates_are_all_zero_and_attributed() -> None:
    """ADJ 追加的硬门必须全为 0（或 green），且每条注明权威出处。"""
    added = POLICY["engineering_hard_gates"]["added_by_adjudication_set"]
    assert len(added) >= 14, f"ADJ 追加硬门应至少 14 条，当前 {len(added)}"
    for name, spec in added.items():
        assert re.match(r"^ADJ-\d{3}", spec["authority"]), (
            f"{name} 缺少合法的 ADJ 权威出处: {spec['authority']!r}"
        )
        if name == "manifest_paragraph_order_static_check":
            assert spec["value"] == "green", f"{name} 必须为 green"
        else:
            assert spec["value"] == 0, f"硬门 {name} 必须为 0，当前 {spec['value']}"


def test_dimension_creation_is_escrowed_not_free() -> None:
    """§72 创建权 + §75 低频禁删 = 棘轮效应。
    解法：创建前预分配配额；配额不足则以 BUDGET_EXHAUSTED 拒绝；
    休眠归还配额；低频维度只休眠不删除 —— §75 与 §76 由此同时满足。
    """
    de = POLICY["dimension_escrow"]
    assert de["candidate_to_trial_requires_preallocated_monthly_token_quota"] is True
    assert de["insufficient_quota_action"] == "reject_creation_with_BUDGET_EXHAUSTED"
    assert de["dormant_returns_quota"] is True
    assert de["low_frequency_dimension_must_not_be_deleted"] is True
    assert de["insufficient_quota_action"].endswith(POLICY["token_budget"]["error_code"])


def test_resonance_is_an_explicit_bounded_operator() -> None:
    """§22 的"共振"若不落成有界算子，就是 O(D²) 的 token 黑洞。"""
    de = POLICY["dimension_escrow"]
    assert 0 < de["resonance_pair_cap_per_window"] <= 100
    assert de["cross_domain_synapse_fanin_max"] <= 8
    assert de["cross_domain_synapse_fanout_max"] <= 8


# ---------------------------------------------------------------------------
# 18. 编号注册表（ADJ-010 / ADJ-011 / ADJ-012）
# ---------------------------------------------------------------------------


def test_id_namespaces_have_single_owners() -> None:
    """断层审计 G01~G08：A01~A10 在两份文档里 10/10 同号不同义，
    而任务书引用的正是被误读的那一套。
    """
    reg = POLICY["id_namespace_registry"]
    assert reg["unregistered_reference_is_ci_red"] is True
    assert reg["dangling_reference_is_ci_red"] is True
    assert reg["deprecated_document_reference_is_ci_red"] is True

    ns = reg["namespaces"]
    assert ns["A01..A10"]["owner"] == "宪法 §114"
    assert ns["P01..P10"]["authority"] == "ADJ-012", (
        "ADJ-012 裁定旧规划 §12 的 A 系列整体重命名为 P01~P10"
    )
    assert ns["R2-24"]["status"] == "GHOST_ID_MUST_BE_DELETED"
    assert ns["CORE-001..004"]["status"] == "DEPRECATED"


def test_my_superseded_naming_is_marked_not_silently_dropped() -> None:
    """ADJ-012 用 P01~P10 解决了我用 ARCH-01~10 解决的同一个问题。

    被取代的命名必须显式标记并指向替代者，而不是悄悄删掉 ——
    否则读过 v1.0.0 的人会继续用 ARCH-01~10，漂移会以"两个都对"的形式延续。
    """
    arch = POLICY["id_namespace_registry"]["namespaces"]["ARCH-01..10"]
    assert arch["status"] == "SUPERSEDED_BY_ADJ_012"
    assert arch["replace_with"] == "P01..P10"
    assert arch["owner"] is None, "被取代的命名空间不得再声明 owner"


def test_stable_key_regime_is_declared_with_no_recycling() -> None:
    """ADJ-011 §2：『条号本身即为不能再承载语义的印刷物』。"""
    regime = POLICY["id_namespace_registry"]["stable_key_regime"]
    assert regime["format"] == "C{章节序}-{语义键}"
    assert regime["keys_never_recycled"] is True
    assert regime["bare_clause_number_is_print_only"] is True
    assert "traceability_matrix.csv" in regime["authority"]


def test_module_namespace_collision_is_registered_not_self_adjudicated() -> None:
    """ADJ-010 §3：模块新增、合并或改义必须进行一级治理变更。本文件无权自裁。

    发现冲突后正确的动作是登记并上交，而不是自己选一个赢家 ——
    后者正是造成这次冲突的行为模式。
    """
    col = POLICY["id_namespace_registry"]["module_namespace_collision"]
    assert col["resolution_path"].startswith("ADJ-010 §3")
    assert col["documents"]["PLAN-R4_registered"]["registry_status"].startswith("PROPOSED")
    assert "未登记" in col["documents"]["R4_unregistered"]["registry_status"]

    # 冲突 ID 必须逐个列出，含两方的定义。
    for cid in ("C15", "C16", "C17", "C18"):
        assert cid in col["conflicting_ids"], f"模块冲突登记缺少 {cid}"
        both = col["conflicting_ids"][cid]
        assert both["PLAN-R4"] and both["R4_unregistered"], f"{cid} 的两方定义必须都登记"


def test_collision_merge_proposal_lets_the_unreferenced_side_yield() -> None:
    """合并提案的原则：已落库到追溯矩阵的编号有既成事实的迁移成本优势，
    未落库的一方改名，社会成本最低。这是 ADJ-011『键绝不回收复用』精神的延伸。
    """
    merge = POLICY["id_namespace_registry"]["module_namespace_collision"][
        "proposed_merge_for_governance_review"
    ]
    assert merge["keep_from_PLAN_R4"] == {"C15": "上下文装配层", "C16": "交互端口"}
    renumbered = merge["renumber_mine_to"]
    assert len(renumbered) == 4, "我方四个职能应改编号为 C17~C20"
    assert set(renumbered.values()) == {"C17", "C18", "C19", "C20"}
    assert "M0'" in merge["also_merge"]["M0.1"], "M0.1 应并入 ADJ-010 的 M0'"
    assert "M1.X" in merge["also_merge"]["CP1"], "CP1 应并入 ADJ-010 的 M1.X"


def test_contested_namespaces_are_marked_as_proposals_not_baselines() -> None:
    """凡本文件上位方案提出但未经一级治理变更批准的编号，
    必须标记为 PROPOSAL_NOT_BASELINE，防止它被当成既成事实引用。
    """
    ns = POLICY["id_namespace_registry"]["namespaces"]
    for key in ("C17..C18", "M0.1", "M-CI", "CP1..CP4"):
        assert ns[key]["status"] == "PROPOSAL_NOT_BASELINE", (
            f"{key} 未经一级治理变更批准，必须标记为 PROPOSAL_NOT_BASELINE"
        )
    assert ns["C01..C16"]["status"].startswith("CONTESTED"), (
        "C01..C16 必须标记为存在争议并指向冲突登记"
    )


def test_scenario_namespace_covers_the_adjudication_registered_range() -> None:
    """ADJ 裁决集注册了 V31~V45。旧 M4-004 §G"V01~V30 覆盖"的悬空引用已消解。"""
    ns = POLICY["id_namespace_registry"]["namespaces"]
    assert ns["V01..V45"]["owner"].startswith("测试规范")
    for rng in ("V21~V30", "V31~V45"):
        assert rng in ns["V01..V45"]["note"], f"场景注册说明缺少 {rng}"
    assert ns["ADJ-001..012"]["owner"].endswith("ADJ-001-012.md")
    assert ns["CONST-v3.0.1"]["note"] == "唯一生效宪基"


def test_deep_water_adjudications_require_full_g0_reconsent() -> None:
    """ADJ-010 附件 C：ADJ-001 与 ADJ-004 属深水区裁决，
    再变更须重走全量 G0 合议，不接受"顺手改一句"。
    """
    note = POLICY["id_namespace_registry"]["namespaces"]["ADJ-001..012"]["note"]
    assert "ADJ-001" in note and "ADJ-004" in note and "G0" in note


# ---------------------------------------------------------------------------
# 19. 阈值基线跨工件一致性（THRESH-BASE 于 M0-031 落地后的新执法面）
#
# 本节的存在理由：v1.1.0 初版我一边声明"阈值治理归 governance/thresholds/"，
# 一边自己重新定义了一套字段名与枚举名，结果与已落地基线**同义异名**
# （previous_value vs prev_value、BIDIRECTIONAL vs DUAL），同一轮里犯了两次。
# 这正是 ADJ-011 要消灭的"一物两名"。本节把"政策层不得重定义他人拥有的契约"
# 从一句自律变成机器执法。
# ---------------------------------------------------------------------------


def _load_threshold_baseline() -> dict[str, Any]:
    path = REPO_ROOT / "governance" / "thresholds" / "baseline_v1.json"
    assert path.is_file(), (
        f"ADJ-008(b) 要求出厂基线冻结在 governance/thresholds/；文件缺失: {path}"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _registry_rows() -> list[tuple[str, str, str, str, str]]:
    """解析 registry.md，返回 [(规范编号, 路径格, 版本格, 状态格, 整行原文)]。

    整行原文是必须的：规则② 允许同一规范编号存在多行（历史版本行 + 活行），
    因此不能用 `startswith(f"| {spec} |")` 取第一个匹配行 —— 那会把历史行的
    哈希拿来和当前文件比，制造一条永远无法消除的假红。
    """
    reg = REPO_ROOT / "governance" / "normative_versions" / "registry.md"
    assert reg.is_file(), f"规范版本注册表缺失: {reg}"
    out = []
    for line in reg.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or set(cells[0]) <= {"-", ":"}:
            continue
        out.append((cells[0], cells[1].strip("`"), cells[2], cells[4], line))
    return out


def test_threshold_baseline_file_exists_and_is_hash_registered() -> None:
    """ADJ-008(b)：基线不仅要有文件，还要在规范版本注册表里被哈希登记。

    没有登记的基线可以被悄悄改掉 —— 那它就不是"出厂基线"，只是"当前配置"。
    本断言把 政策层 → 注册表 → 基线文件 三者钉在一起。
    """
    tg = POLICY["threshold_governance"]
    rel = tg["factory_baseline_frozen_in"]
    path = REPO_ROOT / rel
    assert path.is_file(), f"政策层指向的基线文件不存在: {rel}"
    assert tg["baseline_file_must_exist"] is True
    assert tg["baseline_file_must_be_hash_registered"] is True

    rows = [r for r in _registry_rows() if r[0] == tg["baseline_registry_id"]]
    assert rows, f"{tg['baseline_registry_id']} 未在 registry.md 登记"
    # 活行 = 表内**最后**一行（位置语义，与 hash_registry.py 一致）。
    # 不要按状态文本筛选：SUPERSEDED/archived 的判定依据是位置，不是措辞；
    # 按措辞筛会选中已封存的旧版本行，拿旧哈希去比当前文件，制造一条无法消除的假红。
    live = rows[-1]
    reg_path = live[1].split("+")[-1].strip().strip("`")
    assert reg_path == rel, f"注册表登记的路径 {reg_path} 与政策层指向的 {rel} 不一致"

    import hashlib
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest in live[4], (
        f"{tg['baseline_registry_id']} 的登记哈希与文件实际哈希不符 —— "
        f"规则③ 漂移即红检。文件: {digest[:16]}…"
    )
    assert "SUPERSEDED" not in live[3], (
        f"{tg['baseline_registry_id']} 的活行（末行）状态是 SUPERSEDED —— "
        f"版本链末尾必须有一个生效版本，否则该规范当前无生效版本"
    )


def test_policy_does_not_redefine_the_baseline_change_log_field_names() -> None:
    """ADJ-008(c) + ADJ-011：政策层引用基线的字段名，不得本地改名或另立一套。

    我犯过的错：政策层写 [previous_value,new_value,evidence_input_window,learning_hash]，
    基线是 [param_id,prev_value,next_value,input_window,learner_hash,rationale,applied_at,reversible]。
    四个同义异名 + 四个漏项。这条断言让该错误无法再次通过。
    """
    tg = POLICY["threshold_governance"]
    base = _load_threshold_baseline()
    protocol = base["change_protocol"]
    # 注意：不要用 `a or b` 短路去读两个可能路径 —— 这正是本轮踩过的
    # ".get() 默认值静默通过"同类坑。直接读唯一权威路径，缺键就大声 KeyError。
    sst = tg["single_source_of_truth"]
    assert sst["policy_layer_must_not_redefine_field_names"] is True
    assert sst["policy_layer_role"] == "consumer_and_enforcer", (
        "政策层自称权威定义方 —— 那它就会与基线各写一套字段名，必然漂移（我已漂移过一次）"
    )
    assert sst["authority_file"] == tg["factory_baseline_frozen_in"]
    assert set(tg["change_log_fields"]) == set(protocol["required_fields"]), (
        "政策层的 change_log_fields 与基线 change_protocol.required_fields 不一致 —— "
        "一物两名即漂移源。政策层是消费方，必须逐字引用。"
    )
    assert len(tg["change_log_fields"]) >= tg["change_log_field_count_min"]
    # 我原来漏掉的四个字段，逐个点名，防止被再次删掉
    for must_have in ("param_id", "rationale", "applied_at", "reversible"):
        assert must_have in tg["change_log_fields"], f"缺失 {must_have}（v1.1.0 初版曾漏）"
    assert tg["change_log_must_include_reversible_flag"] is True


def test_policy_does_not_hardcode_a_vocabulary_the_baseline_owns() -> None:
    """ADJ-011：政策层不得枚举另一个工件拥有的词表。

    我犯过的错（同一轮第二次）：写死 learn_channel_enum=[...,BIDIRECTIONAL]，
    而基线用的是 DUAL。教训是结构性的：枚举一旦落到两个文件里必然漂移，
    且漂移方向总是"两边都看起来合理"，人工评审抓不到。
    """
    tg = POLICY["threshold_governance"]
    assert "learn_channel_enum" not in tg, (
        "政策层不得本地枚举 learn_channel —— 该词表归 baseline_v1.json 所有。"
        "请删除本地枚举，改为声明 learn_channel_vocabulary_owner。"
    )
    assert tg["learn_channel_vocabulary_owner"] == "governance/thresholds/baseline_v1.json"
    assert tg["learn_channel_declared_values_must_be_derived_from_baseline"] is True

    base = _load_threshold_baseline()
    used = {p["learn_channel"] for p in base["parameters"]}
    # 词表由基线自身派生，政策层只能声明"必须来自基线"，不能声明具体取值
    assert used <= {"STRICTER_ONLY", "DUAL", "NONE"}, f"基线出现未知 learn_channel: {used}"
    assert tg["safety_lane_true_implies_learn_channel"] in used


def test_every_baseline_parameter_declares_a_learn_channel_and_bounds() -> None:
    """ADJ-008：每个阈值参数必须自带学习通道声明、硬边界与宪法引用。

    没有 learn_channel 的参数，实现者会默认它可学习 —— 而默认可学习
    正是安全阈值被长期磨钝的入口。缺省必须是"不学习"，而非"可学习"。
    """
    base = _load_threshold_baseline()
    params = base["parameters"]
    assert params, "基线没有任何参数，等于没有基线"
    for p in params:
        pid = p.get("param_id", "<无 param_id>")
        assert p.get("learn_channel"), f"{pid} 未声明 learn_channel（缺省不得视为可学习）"
        assert "value" in p and "unit" in p, f"{pid} 缺 value/unit"
        b = p.get("bounds") or {}
        assert "hard_min" in b and "hard_max" in b, f"{pid} 缺硬边界 —— 学习无边界即失控"
        assert b["hard_min"] <= p["value"] <= b["hard_max"], f"{pid} 出厂值越出自己的硬边界"
        assert p.get("constitution_ref"), f"{pid} 缺宪法引用（ADJ-011 §2）"
        # 进学习通道的参数必须有步长上限，否则"可回放"也救不了单步巨跳
        if p["learn_channel"] != "NONE":
            assert p.get("learning"), f"{pid} 可学习但没有 learning 步长约束"
            assert p["learning"].get("max_delta_per_cycle_pct"), f"{pid} 缺单周期最大步长"


def test_safety_lane_parameters_are_stricter_only_with_a_declared_direction() -> None:
    """ADJ-008(d)：人身安全参数不进入学习型下调通道，且必须声明"更严"是哪个方向。

    只说"只能更严"是不够的 —— 血氧下限的"更严"是调高，撞击阈值的"更严"是调低。
    没有 safer_direction，"只许更严"在代码里无法实现，只能靠人理解。
    """
    tg = POLICY["threshold_governance"]
    base = _load_threshold_baseline()
    safety = [p for p in base["parameters"] if p.get("safety_lane")]
    assert safety, "基线没有任何 safety_lane 参数 —— 那 ADJ-008(d) 无执法对象"
    for p in safety:
        assert p["learn_channel"] == tg["safety_lane_true_implies_learn_channel"], (
            f"{p['param_id']} 属人身安全参数却可双向学习 —— 违反 ADJ-008(d)"
        )
        assert p.get("safer_direction") in ("raise", "lower"), (
            f"{p['param_id']} 未声明 safer_direction，'只许更严'不可实现"
        )
    assert tg["safety_parameters_excluded_from_learning_downward_channel"] is True
    # 政策层举的例子必须**全部**是基线里真实存在的 param_id。
    # 不要写 `if ex.startswith("thr.")` 这类形状豁免：变异测试 CASE-215 实测证明，
    # 把举例整体替换成不带该前缀的自造名字，守卫就一次都不开火。
    real_ids = {p["param_id"] for p in base["parameters"]}
    assert tg["safety_parameter_examples"], "政策层未举任何安全参数示例"
    for ex in tg["safety_parameter_examples"]:
        assert ex in real_ids, (
            f"政策层举例 {ex} 在基线中不存在 —— 悬空引用；"
            "自造名字的示例无法被校验，只会让读者以为有校验"
        )

    gates = POLICY["engineering_hard_gates"]["added_by_adjudication_set"]
    assert gates["safety_threshold_learned_downward"]["value"] == 0
    assert gates["safety_threshold_learned_downward"]["authority"] == "ADJ-008(d)"


def test_heartbeat_factory_default_lies_inside_the_constitutional_default_range() -> None:
    """ADJ-002 × ADJ-008 的接合处：区间是对**出厂默认**的合法性检查，不是对每用户运行值的铁律。

    v1.0.0 我把两者搞混，把 3~5 小时写成运行值上下限（等于铁律），撞上 §80之3 的反馈自适应。
    本断言同时钉住两件事：出厂默认必须在区间内（ADJ-002 承认的默认），
    且政策层不得把它写成运行值的硬边界（ADJ-008 归入二级治理参数）。
    """
    tg = POLICY["threshold_governance"]
    hb = POLICY["heartbeat"]
    lo_h, hi_h = tg["heartbeat_interval_constitutional_default_range_h"]
    default_s = tg["heartbeat_interval_factory_default_s"]
    # 区间本身来自 ADJ-002（承认 §80之1 的 3~5 小时为出厂默认），属法律内容。
    # 硬编码在此，与本文件对 ALL_ADJ 的处理同理：让"放宽区间"必须同时改两个文件，
    # 否则把 [3,5] 改成 [1,24] 就能让任何默认值合法 —— 变异测试实测抓不到，故显式钉死。
    assert [lo_h, hi_h] == [3, 5], (
        f"宪法承认的心跳出厂默认区间是 3~5 小时（ADJ-002），政策层写成了 {lo_h}~{hi_h}。"
        "放宽法律区间需要一级治理变更，政策层无权自裁。"
    )
    assert lo_h * 3600 <= default_s <= hi_h * 3600, (
        f"出厂默认 {default_s}s 不在宪法承认的 {lo_h}~{hi_h} 小时区间内"
    )

    base = _load_threshold_baseline()
    row = next(p for p in base["parameters"] if p["param_id"] == "thr.system.heartbeat_interval_s")
    assert row["value"] == default_s, (
        f"政策层声明的出厂默认 {default_s}s 与基线 {row['value']}s 不一致 —— 又是一物两名"
    )
    # 关键：它是可学习的（DUAL），不是铁律；但学习只在硬边界内
    assert row["learn_channel"] == "DUAL", "心跳间隔若不可学习，则违反 §80之3 反馈自适应"
    assert row["bounds"]["hard_min"] <= default_s <= row["bounds"]["hard_max"]
    assert hb["interval_hours_is_factory_default_not_law"] is True, (
        "政策层必须显式声明心跳间隔是出厂默认而非法律铁律（ADJ-002 §1）"
    )


def test_registered_documents_do_not_drift_from_their_pinned_hashes() -> None:
    """registry.md 规则③：任何已登记文件的实际哈希与表内不符即红检。

    本断言在政策层判决门里复刻 hash_registry.py --check，理由：
    2026-09-16 我修改了已登记的 POLICY-RUNTIME 与 PLAN-R4-B 两份文件而没有
    追加版本行，被 hash_registry 判红。这条断言让"改了已登记文件却忘了登记"
    在开发者最常跑的那套测试里也立刻可见，而不是只在 CI 的治理作业里可见。

    版本语义采用与工具一致的**位置语义**：同一 (规范编号, 路径) 可以有多行，
    只有该组表内最后一行参与比对，更早的行哈希封存、不再比对（规则②）。

    两条必须钉死的边界（都是实测踩出来的）：
      1. 归组键是 (spec_id, path) 而**不是** path —— 复合行取"+"之后的路径段，
         于是 CONST-v3.0.1 与 ADJ-v3.0.1 都指向裁决集文件；按 path 归组会把
         **当前生效的宪基**判成"已被后续版本行取代"而移出校验，且落在不判红的桶里。
      2. 某组的**最后一行**若是未补登的占位，则该文件当前不受任何哈希保护
         （旧行已封存）—— 在表尾追加一行占位即可让任意已登记文件静默退出校验。
         必须判红，不能当作"待补登"跳过。
    """
    import hashlib

    rows = _registry_rows()
    hex64 = re.compile(r"([0-9a-f]{64})")

    def seg_of(path_cell: str) -> str:
        return path_cell.split("+")[-1].strip().strip("`")

    # 位置语义：每个 (spec_id, path) 组的最后一行才是活行
    latest: dict[tuple[str, str], int] = {}
    for i, (spec, path_cell, _ver, _status, _line) in enumerate(rows):
        latest[(spec, seg_of(path_cell))] = i

    checked = 0
    live_specs: set[str] = set()
    for i, (spec, path_cell, _ver, _status, row_line) in enumerate(rows):
        seg = seg_of(path_cell)
        if latest[(spec, seg)] != i:
            continue  # archived：历史哈希封存，不与当前文件比对
        f = REPO_ROOT / seg
        if not f.suffix:
            continue
        pins = hex64.findall(row_line)
        assert pins, (
            f"[{spec} {seg}] 该组最后一行仍是占位哈希 —— 文件当前不受任何哈希保护，"
            f"而更早的版本行已封存不再比对。请 --fill 补登或删除该占位行。"
        )
        if not f.is_file():
            raise AssertionError(f"[{spec}] 已登记但文件缺失: {seg}")
        actual = hashlib.sha256(f.read_bytes()).hexdigest()
        checked += 1
        live_specs.add(spec)
        assert actual in pins, (
            f"[{spec}] 哈希漂移：文件 {seg} 的实际哈希 {actual[:16]}… 不在登记行内。"
            f"规则②③：请追加新版本行（勿改写旧行哈希），再运行 "
            f"python tools/governance/hash_registry.py --fill"
        )
    assert checked >= 10, f"仅校验了 {checked} 行，注册表疑似被清空或格式变更"

    # 钉死第 1 条边界：当前生效的宪基必须是活行，绝不能被位置语义 archived 掉
    assert "CONST-v3.0.1" in live_specs, (
        "CONST-v3.0.1（唯一生效宪基）未被哈希校验 —— 它被位置语义误判为已取代的历史行。"
        "归组键必须是 (spec_id, path)，不能是 path。"
    )
    assert "POLICY-RUNTIME" in live_specs and "PLAN-R4-B" in live_specs


def test_policy_satisfies_the_retention_worker_loader_contract() -> None:
    """政策层必须满足 retention_worker.py 的 fail-closed 载入契约。

    自 M1-019 起，政策层不再只是"给人读的法律"—— src/aios_core/services/
    retention_worker.py 的 RetentionPolicy.from_runtime_policy() 会真的读它，
    任何键缺失直接抛 AssertionError。这改变了政策层的失效模式：
    删掉一个键不再只是"法律少了一条"，而是**GC Worker 起不来**。

    本断言逐行复刻该 loader 的判定逻辑（不 import 它，因为那需要 pydantic），
    使政策门能在没有运行时依赖的环境下守住这个契约。
    loader 若变更，本断言必须同步 —— 两侧都有测试，改一边就会红。
    """
    rp = POLICY.get("retention_policy")
    assert isinstance(rp, dict), "缺 retention_policy 段——Worker fail-closed"

    ttl_raw = rp.get("ttl_days_by_retention_class")
    assert isinstance(ttl_raw, dict), "retention_policy.ttl_days_by_retention_class 缺失（Worker fail-closed）"
    ttl = {k: int(v) for k, v in ttl_raw.items() if isinstance(v, int) and k != "$comment"}
    # RetentionClass 枚举的可吊销两类必须在表内（枚举值见 contracts/enums_v3.py）
    for klass in ("revocable_raw", "ephemeral_session"):
        assert klass in ttl, f"TTL 表缺可吊销类 {klass}——Worker fail-closed"
    # 永存类不得有 TTL 数值：null 才是"永不过期"，写成整数就等于给了它一个死期
    assert ttl_raw.get("revocation_free") is None, (
        f"revocation_free 属 ADJ-004 吊销权外永存类，不得有 TTL 数值，实得 "
        f"{ttl_raw.get('revocation_free')!r}"
    )
    assert "revocation_free" not in ttl, "revocation_free 被 isinstance(int) 过滤后才安全；若它是整数就会被当成 TTL"

    cooldown = rp.get("quarantine_cooldown_days")
    retire = rp.get("speaker_cluster_retire_days")
    retire_days = retire.get("days") if isinstance(retire, dict) else retire
    assert isinstance(cooldown, int), "quarantine_cooldown_days 必须为整数——Worker fail-closed"
    assert isinstance(retire_days, int), "speaker_cluster_retire_days.days 必须为整数——Worker fail-closed"
    assert POLICY.get("policy_version"), "policy_version 为空——Worker 用它作 legal_basis"

    # TTL 必须为正且不得长于隔离冷却期的合理倍数（ephemeral 必须显著短于 raw）
    assert ttl["ephemeral_session"] < ttl["revocable_raw"], (
        "会话级缓存的 TTL 不得长于原始可吊销副本——否则'会话级'名不副实"
    )
    assert all(v > 0 for v in ttl.values()), "TTL 必须为正数；0 或负数意味着立即物理删除"


def test_stage1_quarantine_alias_cannot_drift_from_its_canonical_field() -> None:
    """ADJ-011 §2：一物两名即漂移源 —— 别名字段必须与正字段钉死相等。

    合并进来的 stage1_quarantine_days 与同域 quarantine_cooldown_days 语义相同、
    数值相同，且全仓库无任何代码读取它（Worker 读的是 quarantine_cooldown_days）。
    两个字段各自演进之后，"隔离冷却期到底几天"就没有唯一答案。

    处置不是擅自删掉另一条工作线已提交的字段，而是**让它无法漂移**：
    钉死相等 + 在政策层标注为待删别名。删除动作留给下一次治理作业。
    """
    rp = POLICY["retention_policy"]
    canonical = rp["quarantine_cooldown_days"]
    alias = rp["stage1_quarantine_days"]
    assert isinstance(alias, dict) and "days" in alias, "别名字段结构变了，需同步本断言"
    assert alias["days"] == canonical, (
        f"stage1_quarantine_days.days={alias['days']} 与 quarantine_cooldown_days={canonical} "
        f"已经漂移 —— 这正是 ADJ-011 预言的失效：一物两名，各自演进，法律不再有唯一答案"
    )
    assert "$alias_warning" in alias, (
        "别名字段必须自带 $alias_warning 说明它是冗余的、以及为什么还没删"
    )


def test_speaker_cluster_window_is_referenced_not_duplicated() -> None:
    """ADJ-009 的退休窗口：只放引用，不复制数值。

    我在 ADJ-009 对齐时写了 activity_assessed_by_recent_use_window=true 却没给数值 ——
    对一个 fail-closed 系统，没有值的窗口等于没有窗口，实现者只能自己猜。
    另一条工作线的 speaker_cluster_retire_days.days=180 正好是这个值。

    此处**引用而非复制**：复制就会有两个 180，而两个 180 迟早变成 180 和 210。
    这与 threshold_governance 的 single_source_of_truth 是同一条纪律，
    也是我在本轮第二次亲手实践它（第一次是 change_log 字段名）。
    """
    scl = POLICY["speaker_cluster_lifecycle"]
    ref = scl.get("activity_assessed_by_recent_use_window_value_ref")
    assert ref, "声纹退休窗口必须有数值来源引用，否则该窗口无法实现"
    assert scl["activity_assessed_by_recent_use_window"] is True

    # 解引用：路径必须真实可解析到一个正整数
    parts = ref.split(".")
    node: Any = POLICY
    for part in parts:
        assert isinstance(node, dict) and part in node, f"引用 {ref} 在 {part} 处断裂——悬空引用"
        node = node[part]
    assert isinstance(node, int) and node > 0, f"引用 {ref} 解析到 {node!r}，不是正整数"

    # 反向守卫：生命周期域内不得出现第二个退休天数（防止有人"顺手"复制一份）
    duplicates = [
        k for k, v in scl.items()
        if not k.startswith("$") and isinstance(v, int) and v == node
        and k != "activity_assessed_by_recent_use_window_value_ref"
    ]
    assert not duplicates, (
        f"speaker_cluster_lifecycle 内出现与 {ref} 同值的裸整数 {duplicates} —— "
        f"复制数值即制造第二个真相来源"
    )


def test_every_threshold_baseline_assertion_names_a_real_enforcing_test() -> None:
    """元断言：policy_assertions_on_baseline 的每条都必须点名真实存在的执法断言。

    复用本轮从 ADJ 对齐学到的同一个纪律（test_every_adjudication_has_at_least_one_
    enforcing_invariant_or_gate）。一份政策可以列出九条漂亮的"宪法性断言"，
    而其中若干条根本没有能在 CI 里判红的执法点 —— 那它们就是散文。
    散文不会被违反，因为它从来不会被执行。

    这里要求 enforced_by 指向的函数在本模块内真实可调用，
    使"写了断言、忘了实现"与"实现了、忘了接线"两种失效都判红。
    """
    pa = POLICY["threshold_governance"]["policy_assertions_on_baseline"]
    entries = {k: v for k, v in pa.items() if not k.startswith("$")}
    assert len(entries) >= 9, f"基线宪法性断言只剩 {len(entries)} 条，疑似被删减"

    prose_only = []
    dangling = []
    for key, ent in entries.items():
        assert isinstance(ent, dict) and "statement" in ent, f"{key} 不是结构化断言（缺 statement）"
        enforcers = ent.get("enforced_by") or []
        if not enforcers:
            prose_only.append(key)
            continue
        for fn in enforcers:
            if not callable(globals().get(fn)):
                dangling.append(f"{key} → {fn}")
    assert not prose_only, (
        f"以下基线断言没有任何执法点，是散文而非法律: {prose_only}\n"
        "  请为每条补一个能在 CI 判红的断言，或删掉这条断言（不要留着好看）。"
    )
    assert not dangling, (
        f"以下 enforced_by 指向不存在的判决断言（接线断裂）: {dangling}\n"
        "  判决门改名时必须同步更新政策层的 enforced_by —— 与回归套件的"
        "  target-existence 守卫是同一类假绿通道。"
    )


def test_policy_version_matches_its_live_registry_row() -> None:
    """政策层声明的版本号，必须与注册表里 POLICY-RUNTIME 的活行一致。

    变异测试 CASE-236 逼出来的断言：把 policy_version 从 1.2.0 改回 1.1.0，
    原有的 test_policy_is_versioned_and_bound_to_constitution 只检查"非空"，
    于是**一次版本号对撞在判决门下完全隐形**。

    2026-09-16 实际发生过：两条工作线在互不知情的情况下各自产出一个"1.1.0"
    （一条把 retention_ttl 入法，一条做 ADJ-001~012 全量对齐），内容不同、版本号相同。
    注册表存在的理由就是消灭这种指代歧义，而政策层自己声明的版本号
    必须与注册表的活行对齐，否则两份"权威"各说各话。

    三条子不变量：
      1. 活行（同 spec_id+路径的最后一行）的版本号 == policy_version；
      2. POLICY-RUNTIME 的版本号不得重复（一号一物）；
      3. 版本链必须单调递增（追加序即时间序，不得插入更旧的版本）。
    """
    rows = [r for r in _registry_rows() if r[0] == "POLICY-RUNTIME"]
    assert rows, "POLICY-RUNTIME 未在 registry.md 登记"

    versions = [r[2].strip("*").strip() for r in rows]
    # 2) 一号一物
    dupes = {v for v in versions if versions.count(v) > 1}
    assert not dupes, (
        f"POLICY-RUNTIME 版本号重复: {sorted(dupes)} —— 一个版本号同时指代两份不同内容，"
        f"这正是注册表要消灭的指代歧义（2026-09-16 两条工作线各出一个 1.1.0）"
    )

    # 1) 活行 = 表内最后一行（位置语义）
    live_version = versions[-1]
    declared = str(POLICY["policy_version"])
    assert declared == live_version, (
        f"政策层自称 v{declared}，但注册表的活行是 v{live_version}。"
        f"改了政策就要追加版本行并同步 policy_version —— 两份'权威'不得各说各话。"
    )

    # 3) 版本链单调递增（语义化版本的数值序）
    def triple(v: str) -> tuple[int, ...]:
        parts = re.findall(r"\d+", v)
        assert parts, f"无法解析版本号 {v!r}"
        return tuple(int(x) for x in parts[:3])

    seq = [triple(v) for v in versions]
    assert seq == sorted(seq), f"POLICY-RUNTIME 版本链不是追加序: {versions}"



# ---------------------------------------------------------------------------
# 独立运行入口
# ---------------------------------------------------------------------------


def _main() -> int:
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures.append((name, str(exc)))
            print(f"  FAIL  {name}\n          {exc}")
        except Exception as exc:  # noqa: BLE001 - fail-closed：任何异常都算失败
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed, {len(failures)} failed")
    print(f"policy:        {POLICY_PATH}")
    print(f"trace matrix:  {TRACE_MATRIX_PATH} ({len(STABLE_KEYS)} stable keys)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
