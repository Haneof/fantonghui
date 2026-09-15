"""运行时政策层（governance/runtime_policy.json）的守宪测试。

这是"宪法 → 法律 → 判决"三层结构的第三层：
  - 宪法（AIOS核心系统宪法v3.0.md）讲价值：什么不可违背；
  - 法律（governance/runtime_policy.json）讲参数：多少算好；
  - 判决（本文件）讲执行：是否守宪。

设计纪律
--------
1. **纯标准库**。不 import pytest、不 import pydantic、不 import yaml。
   pyproject.toml 是 M0 冻结的基础契约（A03/ARCH-03：M0 产物不得静默修改），
   本文件不给它增加任何新的运行时依赖。
2. **双入口**。pytest 按 ``test_*`` 约定自动收集；也可 ``python3
   tests/policy/test_runtime_policy.py`` 独立运行并以退出码报告，
   便于 CI 之外的人工复核（本重构方案的作者就是这样复核的）。
3. **fail-closed**。与 tests/architecture/test_scanner_regression.py 的 CASE-10
   同一种品味：文件缺失、解析失败、键缺失、预算自相矛盾 —— 一律判红，
   不静默跳过。一份不校验自身的政策文件只是一份更长的散文。
4. **每条断言都指向宪法条款**。政策条目若没有 constitution_ref，
   那它是私人偏好而不是法律，本文件直接判红。

覆盖的裁决（详见 AIOS_Core_任务规划与开发任务拆分重构方案_R4.md）
----------------------------------------------------------------
- C1 留存矛盾（§33之5 物理删除 vs §93之1 严禁篡改）
- C2 传播矛盾（§49 即时影响 vs §93之3 拒绝级联雪崩）
- C3 心智启动矛盾（§84之2 四步不可颠倒 vs §110之14 不受流水线限制）
- C4 上下文预算矛盾（§84之1 单次看盘 vs §85之2 1500 tokens）
- 第一个真实崩溃点：中文 2 字词检索静默 0 命中（§89 举的 9 个词全是 2 字词）
- 成本封套 2.55M tokens/月/用户（§86 条件驱动零浪费）
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "governance" / "runtime_policy.json"

# ---------------------------------------------------------------------------
# 加载：fail-closed
# ---------------------------------------------------------------------------


def load_policy() -> dict[str, Any]:
    """加载政策文件。缺失或非法 JSON 一律抛错，绝不返回空 dict 兜底。"""
    if not POLICY_PATH.is_file():
        raise AssertionError(f"政策文件缺失: {POLICY_PATH}")
    try:
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - 只在文件损坏时触发
        raise AssertionError(f"政策文件不是合法 JSON: {POLICY_PATH}: {exc}") from exc


POLICY = load_policy()

# 政策中每一个需要可审计出处的顶层域。
# 没有 constitution_ref 的域 = 私人偏好 = 不是法律。
AUDITABLE_SECTIONS = (
    "token_budget",
    "manifest_layer_caps",
    "latency_slo",
    "retrieval_slo",
    "storage_envelope",
    "propagation_caps",
    "retention_policy",
    "delivery_fsm",
    "mental_startup",
    "task_readiness",
    "heartbeat",
    "style_constraints",
    "degradation_invariants",
    "dimension_escrow",
)


# ---------------------------------------------------------------------------
# 0. 元结构与可审计性
# ---------------------------------------------------------------------------


def test_policy_is_versioned_and_bound_to_constitution() -> None:
    """政策必须声明版本、宪法基线与执法者，否则无人知道该由谁在何时校验。"""
    for key in ("policy_version", "constitution_baseline", "enforced_by"):
        assert key in POLICY, f"政策缺少元字段: {key}"
    assert POLICY["policy_version"], "policy_version 不得为空"
    assert any("ci.yml" in e for e in POLICY["enforced_by"]), (
        "政策必须绑定 CI 工作流作为执法者；否则它只是文档"
    )


def test_every_auditable_section_cites_the_constitution() -> None:
    """§115 三级修宪纪律的参数化延伸：每条指标必须有宪法出处。"""
    missing = [s for s in AUDITABLE_SECTIONS if s not in POLICY]
    assert not missing, f"政策缺少必需域: {missing}"

    uncited = [
        s for s in AUDITABLE_SECTIONS
        if not str(POLICY[s].get("constitution_ref", "")).strip()
    ]
    assert not uncited, (
        f"以下域未引用任何宪法条款，属于无出处的私人偏好: {uncited}"
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
# 1. Token 封套：子系统之和必须等于总帽（C4 的量化落地）
# ---------------------------------------------------------------------------


def test_token_subsystems_sum_exactly_to_monthly_cap() -> None:
    """§86 条件驱动零浪费：预算必须闭合。

    子系统之和若大于总帽，则总帽是谎言；若小于总帽，则有一笔无主预算
    会被工程直觉悄悄花掉。两者都必须判红。
    """
    tb = POLICY["token_budget"]
    subsystems = tb["subsystems"]
    total = sum(v["monthly_cap"] for v in subsystems.values())
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
    """§78之4 硬件级安全响应 + §85之1 首字响应：这两条不许被预算牺牲。"""
    tb = POLICY["token_budget"]
    for sub in tb["never_degradable"]:
        assert tb["over_quota_policy"].get(sub) != "halt", (
            f"{sub} 被列为 never_degradable，却允许 halt"
        )
    assert "safety" in tb["never_degradable"]


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
    total = tb["monthly_total_cap"]
    assert deep / total < 0.35, (
        f"深车道占月预算 {deep / total:.0%}，超过 35%；§85之1 要求它按需开启而非默认"
    )
    mlc = POLICY["manifest_layer_caps"]
    assert mlc["deep_lane_requires_explicit_request"] is True, (
        "深车道必须由用户显式要求触发"
    )


# ---------------------------------------------------------------------------
# 2. Manifest 分层预算：物理顺序即 KV-cache 顺序（快车道延迟的关键杠杆）
# ---------------------------------------------------------------------------


def test_manifest_layers_are_declared_in_cache_stability_order() -> None:
    """声明顺序 == prompt 物理顺序 == 最稳定 → 最易变。

    Wake Reason（§78 语义第一）必须物理最后，否则 prefix KV-cache 每次全 miss，
    快车道首字延迟从 ~600ms 退化到全量 prefill。这条断言守的是延迟，不是美学。
    """
    mlc = POLICY["manifest_layer_caps"]
    layers = mlc["layers"]
    assert mlc["layer_order_is_prompt_order"] is True

    # L7（触发意图/Wake Reason）必须是最后一层。
    assert layers[-1] == "l7_trigger", (
        f"l7_trigger 必须物理排最后以保住 prefix cache，当前顺序: {layers}"
    )
    # 可缓存层必须是严格前缀，中间不得插入易变层。
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
        assert s == spec["total_cap"], (
            f"{lane} 车道分层之和 {s} ≠ total_cap {spec['total_cap']}"
        )
        assert spec["stable_prefix_tokens"] > 0, f"{lane} 车道必须声明稳定前缀"
        assert spec["stable_prefix_tokens"] <= spec["total_cap"]

    # C4 裁决的直接体现：1500 这个数字必须落在 L6，而不是 total。
    assert mlc["fast"]["l6_dialog"] == 1500, (
        "宪法 §85之2 的 1500 tokens 指的是前台对话滑动窗口（L6），不是 Manifest 总量"
    )
    assert mlc["fast"]["total_cap"] > 1500, (
        "若把 1500 当成 Manifest 总量，则单次看盘（§84之1）无法成立"
    )


def test_manifest_omission_must_be_honest() -> None:
    """§89 之 P3 原则在上下文层的镜像：裁剪可以，隐瞒不行。"""
    mlc = POLICY["manifest_layer_caps"]
    assert mlc["silent_omission_prohibited"] is True
    assert mlc["omission_requires_query_hint"] is True


# ---------------------------------------------------------------------------
# 3. 延迟 SLO：阶段预算必须能凑出 p95
# ---------------------------------------------------------------------------


def test_latency_stage_budget_can_meet_the_p95_slo() -> None:
    """串行阶段之和不得超过快车道 p95，否则 SLO 在算术上就不可能达成。"""
    slo = POLICY["latency_slo"]
    stages = slo["stage_budget_ms"]
    worst = sum(v["max"] for v in stages.values())
    best = sum(v["min"] for v in stages.values())
    p95 = slo["fast_lane_first_token_ms"]["p95"]
    p50 = slo["fast_lane_first_token_ms"]["p50"]

    assert worst <= p95, (
        f"阶段最坏串行和 {worst}ms > p95 SLO {p95}ms；该 SLO 在算术上不可达"
    )
    assert best <= p50, (
        f"阶段最好串行和 {best}ms > p50 SLO {p50}ms"
    )
    for name, v in stages.items():
        assert v["min"] <= v["max"], f"{name} 的 min > max"
        assert "where" in v, f"{name} 缺少 where（device/service/network/cloud）"


def test_speculative_recall_is_the_reason_the_slo_is_reachable() -> None:
    """推测式召回必须与尾静音重叠，否则它的延迟无法被吸收。"""
    stages = POLICY["latency_slo"]["stage_budget_ms"]
    co = stages["co_search_net_add"]
    vad = stages["vad_tail_silence"]
    assert co["min"] == 0, (
        "co_search_net_add 的 min 必须为 0：召回应在 ASR partial 出现时启动，"
        "与尾静音窗口重叠，净增延迟才可能为零"
    )
    assert co["max"] <= vad["min"], (
        f"召回净增上限 {co['max']}ms 必须能被尾静音 {vad['min']}ms 吸收"
    )


def test_offline_degradation_is_mandatory() -> None:
    """断网不得静默失败。参照 Humane AI Pin（2025-02-28 云依赖致全设备变砖）。"""
    assert POLICY["latency_slo"]["offline_degradation_required"] is True


# ---------------------------------------------------------------------------
# 4. 检索 SLO：第一个真实崩溃点的防线
# ---------------------------------------------------------------------------


def test_golden_query_set_is_dominated_by_two_char_cjk() -> None:
    """§89 举出的 9 个关键词（妈妈、生日、礼物、老张、合同、复查、承诺……）
    全部是 2 字词。而 FTS5 unicode61 把连续汉字整段视为单一 token、
    trigram 要求查询 ≥3 字符 —— 2 字中文词在这两种配置下永远返回 0 命中，
    且不报错。这是本项目"直接开工会在哪一步崩溃"的答案，必须在政策里钉死。
    """
    gq = POLICY["retrieval_slo"]["golden_query_set"]
    assert gq["min_two_char_cjk"] >= gq["total"] // 2, (
        f"2 字中文查询至少应占金标集一半，当前 {gq['min_two_char_cjk']}/{gq['total']}"
    )
    assert gq["min_synonym_near_synonym"] > 0, (
        "§96 关键词是入口不是真相：必须包含同义/近义改写查询"
    )
    assert 0 < gq["recall_at_10_min"] <= 1.0


def test_capability_gap_enum_forbids_silent_empty_results() -> None:
    """P3 原则：静默失效一律非法。

    0 命中必须可判别为"确实没有记录"（none）或"本索引结构上无法回答"
    （tokenizer_unable / index_missing / semantic_unavailable ...）。
    没有这个枚举，中文检索的结构性缺陷会被误读为"用户没有相关记忆"，
    并经由 §93 严禁篡改历史的约束固化为永久地质层。
    """
    rs = POLICY["retrieval_slo"]
    gaps = rs["capability_gap_values"]
    assert "none" in gaps, "必须能表达'检索完整执行且确实无结果'"
    assert "tokenizer_unable" in gaps, (
        "必须能表达'分词器无法处理该查询'——这正是中文 2 字词的真实情况"
    )
    assert len(gaps) >= 5, f"capability_gap 至少 5 值，当前 {len(gaps)}: {gaps}"
    assert rs["silent_empty_result_prohibited"] is True


def test_prohibited_tokenizer_configs_are_named() -> None:
    """禁止项必须具体到配置名，否则工程师会"以为自己做对了"。"""
    banned = POLICY["retrieval_slo"]["prohibited_tokenizer_config"]
    joined = " ".join(banned)
    assert any("unicode61" in b for b in banned), "必须点名 unicode61"
    assert any("trigram" in b for b in banned), "必须点名 trigram"
    assert any("LIKE" in b for b in banned), "必须点名 LIKE 全表扫描"
    assert len(joined) > 60


def test_vector_channel_is_m1_blocking() -> None:
    """测试规范 §8 的 B2 强基线要求"关键词与向量检索"且"B2 不能故意做弱"。
    若 A 组（AIOS）无向量通道，B2 对照实验会得出"AIOS 不敌强基线"，
    而该结论反映的是少了一个分词器，不是架构优劣。公平性前置检查。
    """
    rs = POLICY["retrieval_slo"]
    assert rs["vector_is_m1_blocking"] is True, (
        "语义向量检索必须是 M1 阻塞项，不得降级为'未来可选'"
    )
    for ch in ("typed_keyword_inverted", "vector_semantic", "graph_traversal"):
        assert ch in rs["required_channels"], f"缺少必需检索通道: {ch}"


def test_retrieval_latency_scales_to_a_million_objects() -> None:
    """§95 全局世界索引：SLO 必须在 1M 对象规模下声明，而不是在演示数据上。"""
    rs = POLICY["retrieval_slo"]
    assert rs["co_search_p95_ms_at_1m_objects"] <= 150
    assert rs["slice_read_p95_ms_at_1m_objects"] <= 150
    assert rs["slice_read_peak_rss_mb_at_1m_objects"] <= 50
    assert rs["reverse_dependency_lookup_p95_ms"] <= 1, (
        "§90 图谱拓扑穿透的反向依赖查询必须走索引，不得全扫"
    )


# ---------------------------------------------------------------------------
# 5. 存储与派生索引：P1 日志唯一真相
# ---------------------------------------------------------------------------


def test_ingest_ceiling_matches_the_only_viable_tier() -> None:
    """§33 边缘轻量化摄入。实测 M 档快照 16.3GB、H 档 108GB 均 OOM，
    L 档 0.24GB/年 是唯一可上穿戴的档位。
    M1-001 的验收必须由"10k 条心率可写入"反转为"360000 采样点 → ≤5 条落库"。
    """
    se = POLICY["storage_envelope"]
    viable = [k for k, v in se["tiers"].items() if "viable" in v["verdict"]]
    assert viable == ["L"], f"唯一可上穿戴的档位应为 L，实际: {viable}"
    ceiling = se["ingest_ceiling_obs_per_day"]
    assert ceiling <= se["tiers"]["L"]["obs_per_day"] * 2, (
        f"摄入上限 {ceiling} 与唯一可行档位 L 的规模不自洽"
    )


def test_index_must_be_a_pure_function_of_the_log() -> None:
    """P1 原则。索引是日志的纯函数：rebuild(log[0..W]) == index@W。
    这条性质让"索引坏了"永远可修复，也让 §93 的不可篡改成为可实现约束。
    """
    se = POLICY["storage_envelope"]
    assert se["index_is_pure_function_of_log"] is True
    assert se["unbounded_fetchall_prohibited"] is True
    assert "log_watermark" in se["derivation_fingerprint"], (
        "派生指纹必须绑定日志水位，否则无法判断索引是否落后于真相"
    )
    assert "builder_version" in se["derivation_fingerprint"]


# ---------------------------------------------------------------------------
# 6. 传播熔断（裁决 C2：§49 eager vs §93之3 lazy）
# ---------------------------------------------------------------------------


def test_fanout_caps_prevent_the_small_world_blowup() -> None:
    """实测：小世界拓扑失控时单次实体级修正波及 89726 对象 = 179.5M token。
    熔断必须存在，且 hub 实体必须被强制改道聚合车道。
    """
    pc = POLICY["propagation_caps"]
    assert pc["fanout_cap_objects"] < pc["scan_cap_objects"]
    assert pc["hub_entity_forces_aggregate_lane"] is True
    assert pc["hub_entity_indegree_threshold"] > 0


def test_propagation_lanes_resolve_the_eager_vs_lazy_contradiction() -> None:
    """C2 裁决：不是二选一，而是三车道各归其位。
    安全/承诺/活跃主张 → eager；总结/派生/人生章节 → deferred；
    冷历史/归档 → lazy。
    """
    lanes = POLICY["propagation_caps"]["lanes"]
    assert set(lanes) == {"eager", "deferred", "lazy"}, (
        f"必须三车道齐备以裁决 §49 与 §93之3 的表面冲突，当前: {sorted(lanes)}"
    )
    assert "safety" in lanes["eager"]["kinds"], "安全类必须走 eager 即时车道"
    assert "promise" in lanes["eager"]["kinds"], "承诺类必须走 eager（§19之二/§32 人格支柱）"
    assert "summary" in lanes["deferred"]["kinds"]
    assert "cold_history" in lanes["lazy"]["kinds"]
    assert lanes["eager"]["max_objects_per_correction"] <= POLICY["propagation_caps"]["fanout_cap_objects"]


def test_oscillation_and_debt_have_hard_ceilings() -> None:
    """§64 不允许无限自我唤醒；§63 认知复核队列不得老化。"""
    pc = POLICY["propagation_caps"]
    osc = pc["oscillation_detection"]
    assert osc["max_reverse_revisions"] >= 1
    assert "freeze_non_safety_intervention_on_topic" in osc["on_trigger"], (
        "检测到同一话题反复翻案时必须冻结非安全干预，否则 AI 会无限自我说服"
    )
    assert pc["review_queue_oldest_age_days_ceiling"] <= 7


# ---------------------------------------------------------------------------
# 7. 留存与合规（裁决 C1：一票否决级矛盾）
# ---------------------------------------------------------------------------


def test_retention_resolves_the_physical_delete_contradiction() -> None:
    """C1 是一票否决级矛盾：§33之5 要求"物理删除"，§25/§93之1/§116/R3§八
    判定"物理删除历史记录"为严重违宪。两条同时生效则任何实现都违宪。

    裁决：分档留存 + 隔离冷却 + 审计式清除。物理删除不是默认路径。
    """
    rp = POLICY["retention_policy"]
    assert rp["resolution"] == "tiered_retention_with_quarantine"
    assert rp["physical_delete_by_default"] is False
    assert set(rp["retention_states"]) == {"active", "quarantined", "purged_audited"}
    assert rp["quarantine_cooldown_days"] >= 7, (
        "冷却期就是 LLM 清洁工的撤销权，专治'误删了后来才重要的证据'（AV3-04）"
    )
    assert rp["auto_release_on_new_dependency"] is True
    assert rp["purge_requires_audit_record"] is True


def test_purge_audit_record_is_enough_to_detect_tampering_without_content() -> None:
    """§93之1：清除必须留证，但证据不得含被清除内容（否则等于没删）。"""
    fields = set(POLICY["retention_policy"]["purge_audit_fields"])
    assert {"purged_at", "object_ids", "content_sha256", "approver"} <= fields
    assert "content" not in fields and "text" not in fields


def test_janitor_is_not_a_pure_llm_job() -> None:
    """§106 禁止本地小模型负责复杂语义判断，但"数据留存分诊"不属于该清单
    （情绪/压力/事件/人物关系/人生意义/用户意图）。
    若清洁工全用 LLM，H 档成本 = 3.29B tokens/年 ≈ $9,900，§33之5 在经济上不可实现。
    """
    rp = POLICY["retention_policy"]
    tier = rp["janitor_tiering"]
    assert abs(tier["rules_and_edge_model_share"] + tier["llm_share"] - 1.0) < 1e-9
    assert tier["llm_role"] == "tie_break_only"
    assert tier["llm_share"] <= 0.10


def test_erasure_right_beats_immutability() -> None:
    """被遗忘权必须穿透全部派生层，且不得可经由 EvidenceSelector 重建。

    这会改变 §43 EvidenceSet"区间证据必须可重建"的选择器语义 ——
    正是它必须现在写进宪法（而非上线后再补）的原因：
    事后加要动 15 条不可变更基础契约 + 全量数据迁移。
    """
    legal = POLICY["retention_policy"]["legal_override"]
    assert legal["erasure_right_beats_immutability"] is True
    assert legal["erasure_leaves_certificate_only"] is True
    assert legal["certificate_must_not_contain_erased_content"] is True
    assert legal["must_not_be_reconstructable_via_evidence_selector"] is True
    for layer in ("summary", "claim", "derivation", "index"):
        assert layer in legal["must_penetrate_all_derived_layers"], (
            f"被遗忘权必须穿透派生层: {layer}"
        )
    assert legal["third_party_voice_default"].strip(), (
        "第三方声纹/可识别转写的默认策略必须明示（隐私泄露风险）"
    )


# ---------------------------------------------------------------------------
# 8. 交付 FSM：通道无关交付（P4）与投递黑洞
# ---------------------------------------------------------------------------


def test_fsm_states_and_ledger_states_are_consistent() -> None:
    """§98之一 柔性手环交互状态机。旧 86 个 Issue 中'马达/震动/骨传导/FSM'命中数为 0。"""
    fsm = POLICY["delivery_fsm"]
    assert {"acked", "consumed", "expired", "re_delivered"} <= set(fsm["ledger_states"])
    for s in ("idle", "triggered", "acked", "consumed", "expired"):
        assert s in fsm["states"], f"FSM 缺少状态: {s}"
    assert fsm["response_window_ms"]["min"] < fsm["response_window_ms"]["max"]


def test_invariant_I3_closes_the_delivery_black_hole() -> None:
    """I3：action_status == completed 蕴含 ledger.state ∈ {acked, consumed}。

    没有 I3，AI 世界会记录"我答应提醒他妈妈生日 → 已完成"，
    而用户在开会没理会振动、窗口销毁、什么都没收到。
    对一个把承诺与内疚清单当人格支柱（§19之二/§32）的系统，
    这比功能失效严重得多 —— 它会侵蚀 AI 的自我模型。
    """
    inv = POLICY["delivery_fsm"]["invariants"]
    assert "I3" in inv and "acked" in inv["I3"] and "consumed" in inv["I3"]
    assert "I4" in inv and "strong_burst" in inv["I4"], (
        "安全关键投递必须用强振动且不受冷却期约束（§78之4）"
    )
    assert "I1" in inv and "bone_conduction" in inv["I1"] and "triggered" in inv["I1"], (
        "I1 必须同时点名骨传导与 triggered 态：骨传导只允许在 triggered 态开启，"
        "否则公共场所隐私泄露。只写 'bone_conduction_enabled == True' 等于没有这条不变量"
    )


def test_core_never_references_hardware() -> None:
    """P4 原则：Core 只产出 DeliveryIntent。
    ConsoleSimAdapter 与 WearableFsmAdapter 跑同一套测试 → M8 只接物理驱动。
    """
    fsm = POLICY["delivery_fsm"]
    assert fsm["core_must_not_reference_hardware"] is True
    assert {"ConsoleSimAdapter", "WearableFsmAdapter"} == set(fsm["adapters"])


def test_zero_mistrigger_claim_is_replaced_by_measurable_rates() -> None:
    """"绝对零误触"不可证伪。必须改为 FAR / 窗口内误触发率 / 送达确认率，
    并规定噪声语料。FSM 消除的是"无振动时的骨传导误触发"，
    未消除振动误报与窗口内误触 —— 把不可证伪的口号当验收项，就是假 PASS。
    """
    fsm = POLICY["delivery_fsm"]
    assert fsm["zero_mistrigger_claim_is_not_falsifiable"] is True
    pending = " ".join(fsm["hardware_pending_validation"])
    for kw in ("MOS", "FAR", "柔性屏", "功耗"):
        assert kw in pending, f"硬件待验证项缺少: {kw}"


# ---------------------------------------------------------------------------
# 9. 心智启动（裁决 C3：四步序 vs 自主性）
# ---------------------------------------------------------------------------


def test_four_step_sequence_is_a_checklist_not_a_pipeline() -> None:
    """C3 裁决：§84之2"顺序绝对不可颠倒" vs §110之14"不被固定认知流水线限制"
    vs §86之3"绝对不得强制固定阅读顺序"。

    解法：四步都不可省略（保留 §84 的认知价值），但允许从缓存满足
    （保留 §110之14 与 R1-01 的自主性），脏标记由世界版本号驱动。
    """
    ms = POLICY["mental_startup"]
    assert ms["resolution"] == "checklist_not_pipeline"
    assert ms["steps"] == [
        "mirror_self", "calibrate_rapport", "set_stance_and_tone", "inspect_world_and_trigger",
    ], "四步序顺序（语义顺序）必须固定"
    assert ms["no_step_may_be_omitted"] is True
    assert ms["steps_may_be_satisfied_from_cache"] is True
    assert ms["order_strictly_enforced"] is False, (
        "物理执行顺序不得强制，否则违反 §110之14 与 §86之3"
    )
    assert "identity_version" in ms["cache_dirty_flag_source"]


def test_safety_critical_has_a_compressed_path() -> None:
    """没有旁路，用户说"我胸口好疼"时 AI 会在不知道紧急程度的情况下
    先把姿态与语调定死，可能用调侃语气回应心梗。
    """
    path = POLICY["mental_startup"]["safety_critical_compressed_path"]
    assert path[0] == "mirror_self_baseline_only"
    assert "inspect_trigger" in path
    assert any("afterwards" in s for s in path), (
        "安全旁路必须把 rapport/tone 校准推到响应之后，而不是省略它"
    )


def test_mental_startup_is_observable() -> None:
    """四步序当前零可观测性零验收项，必然退化成被忽略的 system prompt。
    trace 是让它可测试的唯一途径。
    """
    ms = POLICY["mental_startup"]
    assert ms["trace_is_required"] is True
    assert ms["trace_object"] == "MentalStartupTrace"
    for f in ("step", "tokens", "cache_hit", "elapsed_ms"):
        assert f in ms["trace_fields"], f"trace 缺少字段: {f}"


def test_thirteen_step_loop_is_demoted_not_deleted() -> None:
    """十三步循环覆盖到"结果回写"与"AI 自身更新"，四步序没有。
    降级为审计维度而非废除；同时工作台规格 §10 引用的"宪法第三十四条"
    是 v2.0 条号残留（v3.0 该条讲的是 Observation 不直接唤醒），必须修正。
    """
    assert POLICY["mental_startup"]["thirteen_step_loop_status"] == "demoted_to_audit_dimension"


# ---------------------------------------------------------------------------
# 10. 条件就绪与心跳：§86 零浪费的两个执行点
# ---------------------------------------------------------------------------


def test_todo_without_trigger_criteria_is_rejected() -> None:
    """§86之2 条件驱动零浪费。旧 M2-005 §C"scheduler 根据
    next_wake/deadline/recurrence 生成 Wake"是纯时间驱动；
    工作台规格 §7.2 与旧 M2-006 §C 的"todo 必须 next_review"
    正是宪法禁止的无脑遍历。
    """
    tr = POLICY["task_readiness"]
    assert tr["trigger_criteria_is_required_on_task"] is True
    assert tr["todo_without_criteria_rejected_with"] == "INVALID_ARGUMENT"
    assert tr["periodic_todo_sweep_prohibited"] is True
    assert tr["manifest_mounts_only_ready_tasks"] is True, (
        "§84之1 单次看盘：只有就绪任务才允许占用 Manifest 预算"
    )
    assert {"time_reached", "context_matched", "event_occurred", "dependency_ready"} == set(
        tr["trigger_kinds"]
    )


def test_trigger_predicate_dsl_forbids_arbitrary_eval() -> None:
    """复用旧 M2-007 §D 已有的正确禁令，不要另造一套 DSL。"""
    tr = POLICY["task_readiness"]
    assert tr["predicate_dsl_must_be_finite_json"] is True
    assert tr["python_eval_prohibited"] is True
    assert len(tr["context_predicate_registry"]) >= 8, (
        "上下文谓词注册表必须足够覆盖 §80之2 的方便度判据"
    )


def test_heartbeat_is_a_seventh_trigger_kind_with_a_mechanical_gate() -> None:
    """"心跳"与"巡检"在旧 86 个 Issue 中双双 0 命中（幽灵需求）。
    实测无闸门 = 0.54~1.28M tok/月；有闸门 = 36K tok/月（-94%）。

    §80之2 的五个判据（工作时间/深度学习/会议专注/驾驶中/深夜睡眠）
    全部机械可判，却被旧方案安排给了 LLM ——
    为了决定"要不要打扰用户"先花一次完整四步序。这违反宪法自己的 §77 与 §79。
    """
    hb = POLICY["heartbeat"]
    assert hb["is_seventh_trigger_kind"] is True
    assert hb["trigger_kind_name"] == "LONG_STABLE_HEARTBEAT"
    assert hb["distinct_from_source_stale_trigger"] is True, (
        "§79'数据源长时间无更新'是来源告警；§80 长平稳心跳是'一切正常该关心内心'"
    )
    assert hb["mechanical_gate_before_llm"] is True
    assert hb["gate_cancel_target_share"] >= 0.75
    assert hb["safety_trigger_never_suppressed_by_gate_or_cooldown"] is True
    assert hb["cancelled_heartbeat_must_still_log_silent_patrol"] is True, (
        "§80之3 后台静默巡检绝不停转：被闸门取消的心跳仍须留下巡检记录"
    )


# ---------------------------------------------------------------------------
# 11. 风格：一票否决条款必须有检测方法
# ---------------------------------------------------------------------------


def test_sycophancy_is_a_blocker_with_a_zero_tolerance() -> None:
    """宪法把"违背事实谄媚奉承"列为一票否决项（§116），
    但旧测试规范零检测方法 —— 一票否决条款没有检测方法就等于没有这条款。
    """
    sc = POLICY["style_constraints"]
    hard = sc["tier_1_hard_auto_checkable"]
    assert hard["sycophancy_rate_max"] == 0.0
    assert hard["sycophancy_severity"] == "blocker"
    assert hard["max_sentences_daily"] == 3, "§14之一 反长篇大论病：日常 1~3 句"


def test_preachiness_is_detected_by_a_blacklist_not_by_taste() -> None:
    """说教必须有确定性检测面，否则 C15 检查层无法执行。"""
    hard = POLICY["style_constraints"]["tier_1_hard_auto_checkable"]
    bl = hard["preach_marker_blacklist"]
    assert len(bl) >= 6
    assert any("你应该" in m or "我建议你" in m for m in bl)
    assert "numbered_list_answer" in bl, (
        "把日常对话组织成 首先/其次/最后 的编号清单，是说教最典型的结构特征"
    )


def test_stance_origin_is_checkable_as_reference_integrity() -> None:
    """本政策的核心设计品味：R3 §5.3 说 AI 立场的"唯一原点"是
    "我对你整个人生的长期理解"。这句话是可执行的 ——
    AI 每一次警告/调侃/阻拦，其输出必须携带 evidence_refs，
    且这些 refs 必须真实存在于世界日志中、当时可见。
    于是"是否有骨气"从模糊的语义判断变成了可自动校验的引用完整性检查。
    """
    soft = POLICY["style_constraints"]["tier_2_soft_blind_review"]
    assert soft["stance_origin_must_be_traceable"] is True
    assert "指鹿为马" in soft["anti_sycophancy_probe"], (
        "反谄媚探针必须包含可判定的荒谬断言（2+2=5 / 已故者在世 / 否认有录音证据的话）"
    )


def test_safety_exception_lifts_the_sentence_cap() -> None:
    """§14之一 的 1~3 句是日常约束，不是安全约束。
    急性胸痛/自杀风险/家暴情境需要更长的引导，否则硬约束会杀人。
    """
    exc = POLICY["style_constraints"]["tier_3_safety_exception"]
    assert exc["sentence_and_char_caps_lifted"] is True
    assert exc["length_decided_by_ai"] is True
    assert exc["exception_must_be_logged"] is True
    assert len(exc["applies_to"]) >= 3


def test_hardcoded_intimacy_rules_are_prohibited() -> None:
    """R3 §5.1：严禁写死"亲密度达到 80 则称兄道弟""检测到愤怒必须道歉三遍"。
    分寸必须由世界状态涌现（§11 分寸感自涌现）。
    """
    assert POLICY["style_constraints"]["hardcoded_intimacy_rules_prohibited"] is True


# ---------------------------------------------------------------------------
# 12. 纵向退化守卫：产品承诺是导数，不是函数值
# ---------------------------------------------------------------------------


def test_every_invariant_is_machine_checkable_and_cited() -> None:
    """旧测试规范 §11 五大指标族测的全是水平值（这一轮指标还行），
    而产品承诺是单调改善（导数）。五种退化 —— STALE 累积、复核队列增长、
    维度棘轮、召回率随规模下降、打扰率随自信上升 —— 只在趋势上可见。
    """
    inv = POLICY["degradation_invariants"]["invariants"]
    assert len(inv) >= 15, f"退化不变量至少 15 条，当前 {len(inv)}"
    allowed_trends = {"non_decreasing", "non_increasing", "bounded", "flat"}
    ids = set()
    for i in inv:
        assert i["trend"] in allowed_trends, f"{i['metric_id']} 的 trend={i['trend']} 非法"
        assert i["severity"] in {"warning", "blocker"}
        assert str(i.get("constitution_ref", "")).strip(), (
            f"{i['metric_id']} 缺少 constitution_ref —— 无出处的指标是私人偏好"
        )
        assert i["metric_id"] not in ids, f"重复的 metric_id: {i['metric_id']}"
        ids.add(i["metric_id"])


def test_blocker_invariants_cover_cost_latency_style_and_retrieval() -> None:
    """四条最致命的退化必须是 blocker 而不是 warning。"""
    blockers = {
        i["metric_id"] for i in POLICY["degradation_invariants"]["invariants"]
        if i["severity"] == "blocker"
    }
    required = {
        "cost.tokens_per_virtual_day",
        "latency.fast_lane_first_token_p95_ms",
        "style.sycophancy_rate",
        "retrieval.golden_recall",
        "retrieval.capability_gap_rate",
    }
    assert required <= blockers, f"以下致命指标未被列为 blocker: {required - blockers}"


def test_hard_caps_agree_with_the_budget_and_slo_sections() -> None:
    """同一数字在政策里出现两次时，两次必须相同。
    这是"参数层"最容易腐烂的地方 —— 改了预算忘了改不变量。
    """
    inv = {i["metric_id"]: i for i in POLICY["degradation_invariants"]["invariants"]}
    tb = POLICY["token_budget"]
    slo = POLICY["latency_slo"]
    pc = POLICY["propagation_caps"]

    assert inv["cost.tokens_per_virtual_day"]["hard_cap"] == tb["daily_total_cap"], (
        "成本不变量的 hard_cap 必须等于 token_budget.daily_total_cap"
    )
    assert inv["latency.fast_lane_first_token_p95_ms"]["hard_cap"] == (
        slo["fast_lane_first_token_ms"]["p95"]
    ), "延迟不变量的 hard_cap 必须等于 latency_slo 的 p95"
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
    assert di["tolerance_must_be_frozen_before_blind_test"] is True, (
        "保留旧测试规范 §16 的正确纪律：不得看完盲测结果后修改标准"
    )


def test_the_guard_itself_is_tested_by_degradation_injection() -> None:
    """守卫必须被证明能守卫。与 tests/architecture/test_scanner_regression.py
    给扫描器本身写 12 个 case 是同一种纪律。
    抓不到任何一种注入 = M-CI-001 不通过。
    """
    suite = POLICY["degradation_invariants"]["degradation_injection_suite"]
    cases = suite["cases"]
    assert len(cases) >= 6, f"退化注入用例至少 6 个，当前 {len(cases)}"

    metric_ids = {i["metric_id"] for i in POLICY["degradation_invariants"]["invariants"]}
    for c in cases:
        assert c["inject"].strip() and c["expect_red"], f"注入用例不完整: {c}"
        unknown = set(c["expect_red"]) - metric_ids
        assert not unknown, f"注入用例引用了不存在的指标: {unknown}"

    # 每一类退化都必须至少被一个注入用例覆盖。
    covered = {m for c in cases for m in c["expect_red"]}
    for must in (
        "cost.tokens_per_virtual_day",
        "debt.stale_object_count",
        "debt.dimension_active_count",
        "style.sycophancy_rate",
        "latency.fast_lane_first_token_p95_ms",
    ):
        assert must in covered, f"退化类别 {must} 未被任何注入用例覆盖 —— 守卫未被证明能守卫它"


# ---------------------------------------------------------------------------
# 13. 工程硬门与维度预算托管
# ---------------------------------------------------------------------------


def test_engineering_hard_gates_are_all_zero() -> None:
    """继承《测试规范》§16 —— 那六条"0 次"是全项目最好的验收设计，原样继承。"""
    gates = POLICY["engineering_hard_gates"]
    keys = [k for k in gates if not k.startswith("$") and k != "source"]
    assert len(keys) == 6, f"工程硬门应为 6 条，当前 {len(keys)}: {keys}"
    for k in keys:
        assert gates[k] == 0, f"工程硬门 {k} 必须为 0 次，当前 {gates[k]}"


def test_dimension_creation_is_escrowed_not_free() -> None:
    """§72（AI 拥有维度创建权）+ §75（低频不等于无价值）+ §76（维度不能无限爆炸）
    三者同时成立会产生棘轮效应：维度数与共振对 O(D²) 单调递增，无人能降。

    解法：创建前必须预分配月度 token 配额；配额不足则以 BUDGET_EXHAUSTED 拒绝；
    休眠归还配额；低频维度只休眠不删除 —— §75 与 §76 由此同时满足。
    """
    de = POLICY["dimension_escrow"]
    assert de["candidate_to_trial_requires_preallocated_monthly_token_quota"] is True
    assert de["insufficient_quota_action"] == "reject_creation_with_BUDGET_EXHAUSTED"
    assert de["dormant_returns_quota"] is True
    assert de["low_frequency_dimension_must_not_be_deleted"] is True
    assert de["insufficient_quota_action"].endswith(
        POLICY["token_budget"]["error_code"]
    ), "配额拒绝必须复用 M0-002 已存在的 BUDGET_EXHAUSTED 错误码"


def test_resonance_is_an_explicit_bounded_operator() -> None:
    """§22 的"共振"若不落成显式算子，就是 O(D²) 的 token 黑洞。
    度数上限防止小世界拓扑失控（实测失控时单次修正波及 90% 图）。
    """
    de = POLICY["dimension_escrow"]
    assert 0 < de["resonance_pair_cap_per_window"] <= 100
    assert de["cross_domain_synapse_fanin_max"] <= 8
    assert de["cross_domain_synapse_fanout_max"] <= 8


# ---------------------------------------------------------------------------
# 14. 编号注册表：堵住假 PASS 通道
# ---------------------------------------------------------------------------


def test_id_namespaces_have_single_owners() -> None:
    """断层审计 G01~G08：A01~A10 在两份文档里 10/10 同号不同义，
    而任务书引用的正是被误读的那一套 —— M2-011 §H"R1-10/W12/A06 通过"
    用的是架构规划义（重复投递不重复行动），而宪法 A06 = 世界搜索可用。
    世界搜索从未被验证过，却在 gate 上显示 PASS。
    """
    reg = POLICY["id_namespace_registry"]
    assert reg["unregistered_reference_is_ci_red"] is True
    assert reg["dangling_reference_is_ci_red"] is True

    ns = reg["namespaces"]
    # A01..A10 的 owner 必须是宪法，架构规划那一套必须改名。
    assert ns["A01..A10"]["owner"] == "宪法 §114"
    assert ns["ARCH-01..10"]["status" if "status" in ns["ARCH-01..10"] else "owner"], (
        "架构规划 §12 的数据完整性定义必须改名为 ARCH-01~10"
    )
    assert ns["R2-24"]["status"] == "GHOST_ID_MUST_BE_DELETED"
    assert ns["R2-24"]["replace_with"] == "R2-04"
    assert ns["CORE-001..004"]["status"] == "DEPRECATED"
    assert ns["CORE-021..032"]["status"] == "DEMOTED_TO_EXAMPLE"


def test_scenario_namespace_covers_the_constitution_required_range() -> None:
    """V21~V30 来自宪法 §113 必须落地；旧 M4-004 §G 写着"V01~V30 覆盖"，
    而测试规范只到 V20 —— 一条引用 10 个不存在场景的验收，
    在 gate 上要么被忽略要么被伪造。V31~V40 为对抗场景。
    """
    ns = POLICY["id_namespace_registry"]["namespaces"]
    assert ns["V01..V40"]["owner"].startswith("测试规范")
    assert "V21~V30" in ns["V01..V40"]["note"]
    assert "V31~V40" in ns["V01..V40"]["note"]
    assert ns["M0.1"]["owner"] and ns["M-CI"]["owner"], (
        "M0.1 阻塞性里程碑与 M-CI 正交持续门必须在注册表中登记"
    )
    assert ns["CP1..CP4"]["owner"], "带硬数字的检查点必须登记"


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
    print(f"policy: {POLICY_PATH}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
