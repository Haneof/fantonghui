"""政策门自身的回归测试：证明 `test_runtime_policy.py` 抓得住违宪。

一份只"全绿"的守宪测试没有信息量 —— 它可能绿是因为守宪，也可能绿是因为
断言写空了。本文件的唯一职责是排除后一种可能。

这与仓库里已有的 `tests/architecture/test_scanner_regression.py` 是同一种纪律：
那边给边界扫描器写了 12 个 case（含 CASE-10：源码不可解析时必须 fail-closed
而不是静默跳过）。**给执法机关写测试，是这个项目已经证明有效的品味，
我只是把它从"架构边界"推广到"运行时政策"。**

机制
----
`test_runtime_policy.POLICY` 是模块级全局字典，测试函数在调用时才查找它。
因此本文件对一份深拷贝做定点变异、临时重绑该全局、调用目标断言、
再无条件恢复 —— 全程不触碰磁盘上的 `governance/runtime_policy.json`。

CASE-00 是反向锚点：未变异的政策必须通过全部断言。
若 CASE-00 失败，后面所有 case 的"抓到违宪"都可能是假阳性
（因为断言在任何输入下都失败）。
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# 双入口：pytest 下 rootdir 已在 sys.path；独立运行时手动补上仓库根，
# 这样 `python3 tests/policy/test_policy_gate_regression.py` 也能跑。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.policy import test_runtime_policy as gate  # noqa: E402


# ---------------------------------------------------------------------------
# 变异夹具
# ---------------------------------------------------------------------------


@contextmanager
def mutated(mutator: Callable[[dict[str, Any]], None]) -> Iterator[dict[str, Any]]:
    """深拷贝政策 → 定点变异 → 重绑全局 → 交还控制权 → 无条件恢复。"""
    original = gate.POLICY
    draft = copy.deepcopy(original)
    mutator(draft)
    gate.POLICY = draft
    try:
        yield draft
    finally:
        gate.POLICY = original


def _assert_caught(mutator: Callable[[dict[str, Any]], None], *targets: str) -> None:
    """断言：给定变异会让 *每一个* 目标断言抛错。

    要求"每个"而不是"至少一个"：一条法律被违反时，所有相关条款都应当报警，
    只报一个意味着其余条款是装饰。

    "抛错"包括 AssertionError 与任何其它异常 —— 对一个 fail-closed 的门来说，
    KeyError 冒泡出去同样是 CI 判红。但 AssertionError 之外的类型会被记录下来，
    因为那通常意味着断言写得不够前置（先崩在取数据上，而不是崩在判断上）。
    """
    soft: list[str] = []
    with mutated(mutator):
        silent = []
        for name in targets:
            try:
                getattr(gate, name)()
            except AssertionError:
                continue
            except Exception as exc:  # noqa: BLE001 - fail-closed：抛错即判红
                soft.append(f"{name}({type(exc).__name__})")
                continue
            silent.append(name)
    assert not silent, f"政策门未抓住违宪（这些断言在变异后仍然通过）: {silent}"


# ---------------------------------------------------------------------------
# CASE-00：反向锚点
# ---------------------------------------------------------------------------


def test_case_00_unmutated_policy_passes_every_gate() -> None:
    """未变异的政策必须通过全部断言。否则本文件的"抓到违宪"没有意义。"""
    names = [n for n in dir(gate) if n.startswith("test_")]
    assert len(names) >= 50, f"政策门断言数量异常（{len(names)}），文件可能被截断"

    failures = []
    for n in sorted(names):
        try:
            getattr(gate, n)()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{n}: {exc}")
    assert not failures, "未变异的政策未通过自身断言:\n" + "\n".join(failures)


def test_case_00b_policy_file_on_disk_is_the_one_under_test() -> None:
    """防止本文件与磁盘上的政策脱钩（例如有人换了路径）。"""
    reloaded = json.loads(gate.POLICY_PATH.read_text(encoding="utf-8"))
    assert reloaded == gate.POLICY, "内存中的政策与 governance/runtime_policy.json 不一致"


# ---------------------------------------------------------------------------
# 可审计性
# ---------------------------------------------------------------------------


def test_case_01_section_without_constitution_ref_is_caught() -> None:
    """无宪法出处的指标 = 私人偏好 = 不是法律。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["constitution_ref"] = "   "

    _assert_caught(m, "test_every_auditable_section_cites_the_constitution")


def test_case_02_missing_section_is_caught() -> None:
    """删掉整个域必须判红，不能"缺了就当没有这条法律"。"""
    def m(p: dict[str, Any]) -> None:
        del p["retention_policy"]

    # 只指向"缺域检查"这一条：它是最先报警的条款，且报的是 AssertionError
    # 而不是 KeyError。被删域自身的那条断言当然也会红（KeyError 冒泡），
    # 但那属于 fail-closed 的兜底，不属于本 case 要证明的精确性。
    _assert_caught(m, "test_every_auditable_section_cites_the_constitution")


def test_case_03_policy_without_ci_enforcer_is_caught() -> None:
    """没有执法者的政策只是更长的散文。"""
    def m(p: dict[str, Any]) -> None:
        p["enforced_by"] = ["docs/README.md"]

    _assert_caught(m, "test_policy_is_versioned_and_bound_to_constitution")


def test_case_04_note_field_without_dollar_prefix_is_caught() -> None:
    """说明性字段必须以 $ 前缀标注，否则会被当成配置读取。"""
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["explanation_note"] = "这是一段会被误读为配置的说明"

    _assert_caught(m, "test_section_keys_starting_with_dollar_are_notes_not_config")


# ---------------------------------------------------------------------------
# 预算闭合
# ---------------------------------------------------------------------------


def test_case_05_budget_overrun_is_caught() -> None:
    """子系统之和 > 总帽：总帽是谎言。"""
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["subsystems"]["janitor"]["monthly_cap"] += 50_000

    _assert_caught(m, "test_token_subsystems_sum_exactly_to_monthly_cap")


def test_case_06_unallocated_slack_is_caught() -> None:
    """子系统之和 < 总帽：存在无主预算，会被工程直觉悄悄花掉。

    这正是本方案自己第一次运行时被抓到的错误方向（我当时把合计四舍五入成 2.55M，
    而逐项推导的真实和是 2,554,000 —— 4,000 token 的无主余量）。
    """
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["subsystems"]["janitor"]["monthly_cap"] -= 4_000

    _assert_caught(m, "test_token_subsystems_sum_exactly_to_monthly_cap")


def test_case_07_subsystem_without_basis_is_caught() -> None:
    """没有推导依据的数字是愿望，不是预算。"""
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["subsystems"]["event"]["basis"] = ""

    _assert_caught(m, "test_every_subsystem_has_a_basis_and_an_over_quota_policy")


def test_case_08_subsystem_without_over_quota_policy_is_caught() -> None:
    """没有超额策略的预算是空话 —— 超了怎么办必须有答案。"""
    def m(p: dict[str, Any]) -> None:
        del p["token_budget"]["over_quota_policy"]["reflection"]

    _assert_caught(m, "test_every_subsystem_has_a_basis_and_an_over_quota_policy")


def test_case_09_illegal_over_quota_action_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["over_quota_policy"]["summary"] = "ignore_and_continue"

    _assert_caught(m, "test_every_subsystem_has_a_basis_and_an_over_quota_policy")


def test_case_10_daily_cap_inconsistent_with_monthly_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["daily_total_cap"] = 120_000

    _assert_caught(m, "test_monthly_cap_implies_the_daily_cap")


def test_case_11_safety_listed_as_haltable_is_caught() -> None:
    """§78之4 硬件级安全响应不许被预算牺牲。"""
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["over_quota_policy"]["safety"] = "halt"

    _assert_caught(m, "test_safety_and_fast_lane_are_never_degradable")


def test_case_12_deep_lane_becoming_default_is_caught() -> None:
    """§85之1 的"1M 上下文战略核武器"默认不开火。"""
    def m(p: dict[str, Any]) -> None:
        p["manifest_layer_caps"]["deep_lane_requires_explicit_request"] = False

    _assert_caught(m, "test_deep_lane_is_capped_and_gated")


def test_case_13_deep_lane_eating_the_budget_is_caught() -> None:
    """把深车道放大到吞掉月预算 35% 以上，必须同时触发两条断言。"""
    def m(p: dict[str, Any]) -> None:
        tb = p["token_budget"]
        # 从 lifechapter 搬 1.2M 到深车道，保持总和闭合，只改变结构占比。
        moved = 1_200_000
        tb["subsystems"]["lifechapter"]["monthly_cap"] -= moved
        tb["subsystems"]["conversation.deep"]["monthly_cap"] += moved

    _assert_caught(m, "test_deep_lane_is_capped_and_gated")


# ---------------------------------------------------------------------------
# Manifest 物理顺序（KV-cache）
# ---------------------------------------------------------------------------


def test_case_14_wake_reason_moved_to_front_is_caught() -> None:
    """把 L7 提前会让 prefix KV-cache 每次全 miss，快车道延迟退化 2~4.8×。

    这条断言守的是延迟，不是美学 —— 所以它必须是 blocker。
    """
    def m(p: dict[str, Any]) -> None:
        layers = p["manifest_layer_caps"]["layers"]
        layers.remove("l7_trigger")
        layers.insert(0, "l7_trigger")

    _assert_caught(m, "test_manifest_layers_are_declared_in_cache_stability_order")


def test_case_15_volatile_layer_inside_cacheable_prefix_is_caught() -> None:
    """可缓存层必须是严格前缀，中间不得插入易变层。"""
    def m(p: dict[str, Any]) -> None:
        mlc = p["manifest_layer_caps"]
        mlc["cacheable_layers"] = ["l0_identity", "l1_self_world", "l4_state", "l2_rapport"]

    _assert_caught(m, "test_manifest_layers_are_declared_in_cache_stability_order")


def test_case_16_1500_tokens_misread_as_manifest_total_is_caught() -> None:
    """裁决 C4：§85之2 的 1500 是 L6 单层，不是整个 Manifest。

    这是宪法内部矛盾里最容易被"顺手实现错"的一条：把 1500 当总量，
    单次看盘（§84之1）就装不下 L0~L5，工程师会静默砍掉自我镜像与关系校准。
    """
    def m(p: dict[str, Any]) -> None:
        p["manifest_layer_caps"]["fast"]["total_cap"] = 1500

    _assert_caught(
        m,
        "test_manifest_layer_caps_sum_to_total_and_stable_prefix_is_declared",
    )


def test_case_17_silent_truncation_allowed_is_caught() -> None:
    """P3 原则在上下文层的镜像：裁剪可以，隐瞒不行。"""
    def m(p: dict[str, Any]) -> None:
        p["manifest_layer_caps"]["silent_omission_prohibited"] = False

    _assert_caught(m, "test_manifest_omission_must_be_honest")


# ---------------------------------------------------------------------------
# 延迟
# ---------------------------------------------------------------------------


def test_case_18_unreachable_latency_slo_is_caught() -> None:
    """阶段最坏串行和超过 p95 —— 这个 SLO 在算术上就不可能达成。"""
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["stage_budget_ms"]["cloud_prefill_ttft"]["max"] = 900

    _assert_caught(m, "test_latency_stage_budget_can_meet_the_p95_slo")


def test_case_19_recall_not_overlapped_with_tail_silence_is_caught() -> None:
    """若召回不与尾静音重叠，它的延迟无法被吸收，1 秒首字就是空话。"""
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["stage_budget_ms"]["co_search_net_add"]["min"] = 150

    # 注意：这个变异不会让 test_latency_stage_budget 变红
    # （最坏串行和 1000ms 仍等于 p95，最好串行和 575ms 仍低于 p50）。
    # 这正是需要 test_speculative_recall 单独存在的原因 ——
    # 总预算合法不等于每一段都摆在了正确的位置。
    _assert_caught(m, "test_speculative_recall_is_the_reason_the_slo_is_reachable")


def test_case_20_missing_offline_degradation_is_caught() -> None:
    """断网静默失败 = Humane AI Pin 的结局（2025-02-28 全设备变砖）。"""
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["offline_degradation_required"] = False

    _assert_caught(m, "test_offline_degradation_is_mandatory")


# ---------------------------------------------------------------------------
# 检索：第一个真实崩溃点
# ---------------------------------------------------------------------------


def test_case_21_golden_set_without_two_char_cjk_is_caught() -> None:
    """§89 举出的 9 个关键词全是 2 字词。金标集若不含 2 字中文，
    这个崩溃点就永远不会在测试里现形 —— 它会静默污染全部后续认知。
    """
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["golden_query_set"]["min_two_char_cjk"] = 10

    _assert_caught(m, "test_golden_query_set_is_dominated_by_two_char_cjk")


def test_case_22_removing_tokenizer_unable_gap_is_caught() -> None:
    """去掉 tokenizer_unable，"索引结构上无法回答"就会伪装成"用户没有相关记忆"。"""
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["capability_gap_values"].remove("tokenizer_unable")

    _assert_caught(m, "test_capability_gap_enum_forbids_silent_empty_results")


def test_case_23_silent_empty_result_permitted_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["silent_empty_result_prohibited"] = False

    _assert_caught(m, "test_capability_gap_enum_forbids_silent_empty_results")


def test_case_24_ban_list_softened_to_abstraction_is_caught() -> None:
    """禁止项若抽象成"不要用不合适的分词器"，工程师会以为自己用对了。
    必须点名 unicode61 / trigram / LIKE。
    """
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["prohibited_tokenizer_config"] = [
            "不要使用不合适的中文分词方案"
        ]

    _assert_caught(m, "test_prohibited_tokenizer_configs_are_named")


def test_case_25_vector_channel_demoted_to_optional_is_caught() -> None:
    """旧 M1-012 §D 正是这么写的（"语义向量不是 M1 阻塞项"）。
    后果：B2 强基线对照实验会得出"AIOS 不敌强基线"，
    而这个结论反映的是少了一个分词器，不是架构优劣。
    """
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["vector_is_m1_blocking"] = False

    _assert_caught(m, "test_vector_channel_is_m1_blocking")


def test_case_26_slo_measured_only_on_demo_data_is_caught() -> None:
    """§95 全局世界索引：SLO 必须在 1M 对象规模下声明。"""
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["co_search_p95_ms_at_1m_objects"] = 3400  # LIKE 全扫实测值

    _assert_caught(m, "test_retrieval_latency_scales_to_a_million_objects")


# ---------------------------------------------------------------------------
# 存储与派生
# ---------------------------------------------------------------------------


def test_case_27_high_tier_declared_viable_is_caught() -> None:
    """实测 M 档快照 16.3GB、H 档 108GB 均 OOM。把 H 档说成可上穿戴就是造假。"""
    def m(p: dict[str, Any]) -> None:
        p["storage_envelope"]["tiers"]["H"]["verdict"] = "only tier viable on wearable"
        p["storage_envelope"]["tiers"]["L"]["verdict"] = "acceptable"

    _assert_caught(m, "test_ingest_ceiling_matches_the_only_viable_tier")


def test_case_28_ingest_ceiling_raised_to_h_tier_is_caught() -> None:
    """旧 M1-001 的验收（"10k 条心率可批量写入"）把 §33 禁止的行为写成通过条件。"""
    def m(p: dict[str, Any]) -> None:
        p["storage_envelope"]["ingest_ceiling_obs_per_day"] = 30_000

    _assert_caught(m, "test_ingest_ceiling_matches_the_only_viable_tier")


def test_case_29_index_not_declared_pure_function_is_caught() -> None:
    """P1 原则。少了它，"索引坏了"就不可修复，§93 的不可篡改也无法实现。"""
    def m(p: dict[str, Any]) -> None:
        p["storage_envelope"]["index_is_pure_function_of_log"] = False

    _assert_caught(m, "test_index_must_be_a_pure_function_of_the_log")


def test_case_30_derivation_fingerprint_without_watermark_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["storage_envelope"]["derivation_fingerprint"] = "sha256(index_kind || builder_version)"

    _assert_caught(m, "test_index_must_be_a_pure_function_of_the_log")


def test_case_31_unbounded_fetchall_permitted_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["storage_envelope"]["unbounded_fetchall_prohibited"] = False

    _assert_caught(m, "test_index_must_be_a_pure_function_of_the_log")


# ---------------------------------------------------------------------------
# 传播（裁决 C2）
# ---------------------------------------------------------------------------


def test_case_32_fanout_cap_removed_is_caught() -> None:
    """实测小世界拓扑失控时单次修正波及 89726 对象 = 179.5M token。"""
    def m(p: dict[str, Any]) -> None:
        p["propagation_caps"]["fanout_cap_objects"] = 1_000_000

    _assert_caught(m, "test_fanout_caps_prevent_the_small_world_blowup")


def test_case_33_hub_entity_allowed_to_stay_eager_is_caught() -> None:
    """老张这类高度数实体（实测 644 对象/次）必须改道聚合车道。"""
    def m(p: dict[str, Any]) -> None:
        p["propagation_caps"]["hub_entity_forces_aggregate_lane"] = False

    _assert_caught(m, "test_fanout_caps_prevent_the_small_world_blowup")


def test_case_34_collapsing_three_lanes_into_eager_only_is_caught() -> None:
    """退回 §49 的纯即时传播 = 级联雪崩，违反 §93之3。"""
    def m(p: dict[str, Any]) -> None:
        p["propagation_caps"]["lanes"] = {
            "eager": p["propagation_caps"]["lanes"]["eager"]
        }

    _assert_caught(m, "test_propagation_lanes_resolve_the_eager_vs_lazy_contradiction")


def test_case_35_promise_moved_out_of_eager_is_caught() -> None:
    """承诺是 §19之二/§32 的人格支柱，走 deferred 就意味着 AI 会忘记自己答应过什么。"""
    def m(p: dict[str, Any]) -> None:
        p["propagation_caps"]["lanes"]["eager"]["kinds"] = ["safety", "active_claim"]

    _assert_caught(m, "test_propagation_lanes_resolve_the_eager_vs_lazy_contradiction")


def test_case_36_oscillation_freeze_removed_is_caught() -> None:
    """§64 不允许无限自我唤醒：反复翻案必须冻结非安全干预。"""
    def m(p: dict[str, Any]) -> None:
        p["propagation_caps"]["oscillation_detection"]["on_trigger"] = ["log_only"]

    _assert_caught(m, "test_oscillation_and_debt_have_hard_ceilings")


def test_case_37_review_queue_allowed_to_age_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["propagation_caps"]["review_queue_oldest_age_days_ceiling"] = 90

    _assert_caught(m, "test_oscillation_and_debt_have_hard_ceilings")


# ---------------------------------------------------------------------------
# 留存（裁决 C1，一票否决级）
# ---------------------------------------------------------------------------


def test_case_38_physical_delete_by_default_is_caught() -> None:
    """C1：§33之5 要求物理删除，§93之1/§116 判定物理删除历史记录为严重违宪。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["physical_delete_by_default"] = True

    _assert_caught(m, "test_retention_resolves_the_physical_delete_contradiction")


def test_case_39_quarantine_cooldown_too_short_is_caught() -> None:
    """冷却期是 LLM 清洁工的撤销权（AV3-04）。缩到 0 天等于没有撤销权。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["quarantine_cooldown_days"] = 0

    _assert_caught(m, "test_retention_resolves_the_physical_delete_contradiction")


def test_case_40_purge_without_audit_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["purge_requires_audit_record"] = False

    _assert_caught(m, "test_retention_resolves_the_physical_delete_contradiction")


def test_case_41_audit_record_leaking_purged_content_is_caught() -> None:
    """清除必须留证，但证据含被清除内容 = 等于没删。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["purge_audit_fields"].append("content")

    _assert_caught(
        m, "test_purge_audit_record_is_enough_to_detect_tampering_without_content"
    )


def test_case_42_janitor_made_pure_llm_is_caught() -> None:
    """全 LLM 清洗 = 3.29B tok/年 ≈ $9,900，§33之5 在经济上不可实现。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["janitor_tiering"] = {
            "rules_and_edge_model_share": 0.0,
            "llm_share": 1.0,
            "llm_role": "full_semantic_judgement",
        }

    _assert_caught(m, "test_janitor_is_not_a_pure_llm_job")


def test_case_43_erasure_not_penetrating_derived_layers_is_caught() -> None:
    """被遗忘权必须穿透派生层，否则删了原文却留着总结 = 没删。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["legal_override"]["must_penetrate_all_derived_layers"] = [
            "index"
        ]

    _assert_caught(m, "test_erasure_right_beats_immutability")


def test_case_44_erasure_reconstructable_via_evidence_selector_is_caught() -> None:
    """这会改变 §43 EvidenceSet 的选择器语义 —— 所以必须现在写进宪法。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["legal_override"][
            "must_not_be_reconstructable_via_evidence_selector"
        ] = False

    _assert_caught(m, "test_erasure_right_beats_immutability")


def test_case_45_erasure_certificate_retaining_content_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["legal_override"][
            "certificate_must_not_contain_erased_content"
        ] = False

    _assert_caught(m, "test_erasure_right_beats_immutability")


# ---------------------------------------------------------------------------
# 交付 FSM
# ---------------------------------------------------------------------------


def test_case_46_invariant_I3_removed_is_caught() -> None:
    """投递黑洞：AI 记录"已完成提醒"，用户在开会什么都没收到。
    对一个把承诺当人格支柱的系统，这比功能失效严重。
    """
    def m(p: dict[str, Any]) -> None:
        del p["delivery_fsm"]["invariants"]["I3"]

    _assert_caught(m, "test_invariant_I3_closes_the_delivery_black_hole")


def test_case_47_safety_delivery_subject_to_cooldown_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["invariants"]["I4"] = (
            "safety_critical implies haptic == 'soft_single'"
        )

    _assert_caught(m, "test_invariant_I3_closes_the_delivery_black_hole")


def test_case_48_bone_conduction_always_on_is_caught() -> None:
    """I1：骨传导只允许在 triggered 态开启，否则公共场所隐私泄露。"""
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["invariants"]["I1"] = "bone_conduction_enabled == True"

    _assert_caught(m, "test_invariant_I3_closes_the_delivery_black_hole")


def test_case_49_core_referencing_hardware_is_caught() -> None:
    """P4 原则。Core 里出现一行引用屏幕的代码，抽象就破了。"""
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["core_must_not_reference_hardware"] = False

    _assert_caught(m, "test_core_never_references_hardware")


def test_case_50_single_adapter_breaks_equivalence_is_caught() -> None:
    """只留 WearableFsmAdapter，Linux 阶段就没有可跑的东西；
    只留 ConsoleSimAdapter，M8 就是重新设计而不是接驱动。
    """
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["adapters"] = ["ConsoleSimAdapter"]

    _assert_caught(m, "test_core_never_references_hardware")


def test_case_51_unfalsifiable_zero_mistrigger_claim_is_caught() -> None:
    """"绝对零误触"必须换成 FAR / 窗口内误触发率 / 送达确认率，
    否则它就是一条在 gate 上被伪造的验收。
    """
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["zero_mistrigger_claim_is_not_falsifiable"] = False

    _assert_caught(m, "test_zero_mistrigger_claim_is_replaced_by_measurable_rates")


def test_case_52_hardware_validation_list_gutted_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["hardware_pending_validation"] = ["待定"]

    _assert_caught(m, "test_zero_mistrigger_claim_is_replaced_by_measurable_rates")


def test_case_53_ledger_states_losing_expired_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["ledger_states"] = ["intended", "acked"]

    _assert_caught(m, "test_fsm_states_and_ledger_states_are_consistent")


# ---------------------------------------------------------------------------
# 心智启动（裁决 C3）
# ---------------------------------------------------------------------------


def test_case_54_a_step_made_optional_is_caught() -> None:
    """四步序任一步不得省略（§84之2）。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["no_step_may_be_omitted"] = False

    _assert_caught(m, "test_four_step_sequence_is_a_checklist_not_a_pipeline")


def test_case_55_pipeline_order_hard_enforced_is_caught() -> None:
    """反向也要抓：强制物理执行顺序会违反 §110之14 与 §86之3。

    这一条特别重要 —— 它证明本政策门不是单向的"越严越好"，
    而是守着 C3 裁决的**两侧**。只禁"省略"不禁"僵化"的门是半个门。
    """
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["order_strictly_enforced"] = True

    _assert_caught(m, "test_four_step_sequence_is_a_checklist_not_a_pipeline")


def test_case_56_cache_without_dirty_flags_is_caught() -> None:
    """允许从缓存满足，但必须有脏标记来源，否则 AI 会用过期的人格镜像说话。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["cache_dirty_flag_source"] = []

    _assert_caught(m, "test_four_step_sequence_is_a_checklist_not_a_pipeline")


def test_case_57_steps_reordered_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["steps"] = [
            "inspect_world_and_trigger", "mirror_self",
            "calibrate_rapport", "set_stance_and_tone",
        ]

    _assert_caught(m, "test_four_step_sequence_is_a_checklist_not_a_pipeline")


def test_case_58_safety_path_without_deferred_calibration_is_caught() -> None:
    """安全旁路必须把 rapport/tone 推到响应**之后**，而不是省略它。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["safety_critical_compressed_path"] = [
            "mirror_self_baseline_only", "inspect_trigger"
        ]

    _assert_caught(m, "test_safety_critical_has_a_compressed_path")


def test_case_59_unobservable_startup_trace_is_caught() -> None:
    """四步序零可观测性 → 必然退化成被忽略的 system prompt。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["trace_is_required"] = False

    _assert_caught(m, "test_mental_startup_is_observable")


def test_case_60_trace_missing_token_field_is_caught() -> None:
    """没有 tokens 字段，就无法证明四步序在成本封套内。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["trace_fields"] = ["step", "output_decision"]

    _assert_caught(m, "test_mental_startup_is_observable")


def test_case_61_thirteen_step_loop_deleted_outright_is_caught() -> None:
    """降级而非废除：它覆盖"结果回写"与"AI 自身更新"，四步序没有。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["thirteen_step_loop_status"] = "deleted"

    _assert_caught(m, "test_thirteen_step_loop_is_demoted_not_deleted")


# ---------------------------------------------------------------------------
# 条件就绪与心跳
# ---------------------------------------------------------------------------


def test_case_62_todo_sweep_reintroduced_is_caught() -> None:
    """工作台规格 §7.2 与旧 M2-006 §C 的"todo 必须 next_review"
    正是 §86 禁止的无脑遍历。
    """
    def m(p: dict[str, Any]) -> None:
        p["task_readiness"]["periodic_todo_sweep_prohibited"] = False

    _assert_caught(m, "test_todo_without_trigger_criteria_is_rejected")


def test_case_63_unready_tasks_mounted_on_manifest_is_caught() -> None:
    """§84之1 单次看盘：只有就绪任务才允许占用 Manifest 预算。"""
    def m(p: dict[str, Any]) -> None:
        p["task_readiness"]["manifest_mounts_only_ready_tasks"] = False

    _assert_caught(m, "test_todo_without_trigger_criteria_is_rejected")


def test_case_64_trigger_kind_dropped_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["task_readiness"]["trigger_kinds"] = ["time_reached", "event_occurred"]

    _assert_caught(m, "test_todo_without_trigger_criteria_is_rejected")


def test_case_65_python_eval_allowed_in_predicates_is_caught() -> None:
    """复用旧 M2-007 §D 已有的正确禁令，不要另造一套 DSL。"""
    def m(p: dict[str, Any]) -> None:
        p["task_readiness"]["python_eval_prohibited"] = False

    _assert_caught(m, "test_trigger_predicate_dsl_forbids_arbitrary_eval")


def test_case_66_predicate_registry_too_thin_is_caught() -> None:
    """注册表覆盖不了 §80之2 的方便度判据，闸门就只能交给 LLM 判 —— 那正是浪费。"""
    def m(p: dict[str, Any]) -> None:
        p["task_readiness"]["context_predicate_registry"] = ["in_geofence", "driving"]

    _assert_caught(m, "test_trigger_predicate_dsl_forbids_arbitrary_eval")


def test_case_67_heartbeat_gate_moved_after_llm_is_caught() -> None:
    """为了决定"要不要打扰用户"先花一次完整四步序 —— 违反宪法自己的 §77/§79。
    实测：无闸门 0.54~1.28M tok/月 → 有闸门 36K tok/月（-94%）。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["mechanical_gate_before_llm"] = False

    _assert_caught(m, "test_heartbeat_is_a_seventh_trigger_kind_with_a_mechanical_gate")


def test_case_68_gate_suppressing_safety_trigger_is_caught() -> None:
    """方便度闸门绝不能压住安全触发。这是心跳机制里唯一不可让渡的一条。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["safety_trigger_never_suppressed_by_gate_or_cooldown"] = False

    _assert_caught(m, "test_heartbeat_is_a_seventh_trigger_kind_with_a_mechanical_gate")


def test_case_69_cancelled_heartbeat_leaves_no_patrol_record_is_caught() -> None:
    """§80之3 后台静默巡检绝不停转：被取消的心跳仍须留痕，
    否则"AI 一直在默默关心"就变成无法审计的宣称。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["cancelled_heartbeat_must_still_log_silent_patrol"] = False

    _assert_caught(m, "test_heartbeat_is_a_seventh_trigger_kind_with_a_mechanical_gate")


def test_case_70_heartbeat_conflated_with_source_stale_is_caught() -> None:
    """§79"数据源长时间无更新"是来源告警；§80 长平稳心跳是"一切正常该关心内心"。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["distinct_from_source_stale_trigger"] = False

    _assert_caught(m, "test_heartbeat_is_a_seventh_trigger_kind_with_a_mechanical_gate")


# ---------------------------------------------------------------------------
# 风格
# ---------------------------------------------------------------------------


def test_case_71_sycophancy_downgraded_to_warning_is_caught() -> None:
    """宪法把谄媚列为一票否决项（§116）。降级为 warning = 这条款不存在。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_1_hard_auto_checkable"]["sycophancy_severity"] = "warning"

    _assert_caught(m, "test_sycophancy_is_a_blocker_with_a_zero_tolerance")


def test_case_72_sycophancy_tolerance_loosened_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_1_hard_auto_checkable"]["sycophancy_rate_max"] = 0.05

    _assert_caught(m, "test_sycophancy_is_a_blocker_with_a_zero_tolerance")


def test_case_73_sentence_cap_removed_is_caught() -> None:
    """§14之一 反长篇大论病。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_1_hard_auto_checkable"]["max_sentences_daily"] = 30

    _assert_caught(m, "test_sycophancy_is_a_blocker_with_a_zero_tolerance")


def test_case_74_preach_blacklist_emptied_is_caught() -> None:
    """说教必须有确定性检测面，否则 C15 检查层无法执行，只能靠品味打分。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_1_hard_auto_checkable"]["preach_marker_blacklist"] = []

    _assert_caught(m, "test_preachiness_is_detected_by_a_blacklist_not_by_taste")


def test_case_75_numbered_list_marker_dropped_is_caught() -> None:
    """把日常对话组织成 首先/其次/最后 的编号清单，是说教最典型的结构特征。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_1_hard_auto_checkable"][
            "preach_marker_blacklist"
        ] = ["你应该", "我建议你", "记住"]

    _assert_caught(m, "test_preachiness_is_detected_by_a_blacklist_not_by_taste")


def test_case_76_stance_origin_untraceable_is_caught() -> None:
    """R3 §5.3 的"唯一原点是我对你整个人生的长期理解"必须可执行：
    每一次警告/调侃/阻拦都要携带 evidence_refs 且 refs 当时可见。
    否则"是否有骨气"就退回成模糊的语义判断。
    """
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_2_soft_blind_review"][
            "stance_origin_must_be_traceable"
        ] = False

    _assert_caught(m, "test_stance_origin_is_checkable_as_reference_integrity")


def test_case_77_probe_softened_to_politeness_is_caught() -> None:
    """反谄媚探针必须是可判定的荒谬断言，不能是"观察语气是否得体"。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_2_soft_blind_review"]["anti_sycophancy_probe"] = (
            "观察 AI 的语气是否足够得体"
        )

    _assert_caught(m, "test_stance_origin_is_checkable_as_reference_integrity")


def test_case_78_safety_exception_removed_is_caught() -> None:
    """1~3 句是日常约束不是安全约束。没有例外，硬约束会在心梗情境里杀人。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_3_safety_exception"]["sentence_and_char_caps_lifted"] = False

    _assert_caught(m, "test_safety_exception_lifts_the_sentence_cap")


def test_case_79_safety_exception_unlogged_is_caught() -> None:
    """例外必须留痕，否则"安全例外"会变成绕过一切风格约束的后门。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_3_safety_exception"]["exception_must_be_logged"] = False

    _assert_caught(m, "test_safety_exception_lifts_the_sentence_cap")


def test_case_80_hardcoded_intimacy_rules_allowed_is_caught() -> None:
    """R3 §5.1：严禁"亲密度达到 80 则称兄道弟"。分寸必须由世界状态涌现。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["hardcoded_intimacy_rules_prohibited"] = False

    _assert_caught(m, "test_hardcoded_intimacy_rules_are_prohibited")


# ---------------------------------------------------------------------------
# 纵向退化守卫
# ---------------------------------------------------------------------------


def test_case_81_invariant_without_constitution_ref_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["invariants"][0]["constitution_ref"] = ""

    _assert_caught(m, "test_every_invariant_is_machine_checkable_and_cited")


def test_case_82_illegal_trend_verb_is_caught() -> None:
    """"improving" 不是可判定的趋势动词 —— 它没有方向也没有界。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["invariants"][0]["trend"] = "improving"

    _assert_caught(m, "test_every_invariant_is_machine_checkable_and_cited")


def test_case_83_duplicate_metric_id_is_caught() -> None:
    """重复 metric_id 会让 CI 只报一条、掩盖另一条 —— 一种静默失效。"""
    def m(p: dict[str, Any]) -> None:
        inv = p["degradation_invariants"]["invariants"]
        inv[1]["metric_id"] = inv[0]["metric_id"]

    _assert_caught(m, "test_every_invariant_is_machine_checkable_and_cited")


def test_case_84_invariant_count_thinned_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["invariants"] = (
            p["degradation_invariants"]["invariants"][:5]
        )

    _assert_caught(
        m,
        "test_every_invariant_is_machine_checkable_and_cited",
        "test_blocker_invariants_cover_cost_latency_style_and_retrieval",
    )


def test_case_85_cost_invariant_downgraded_to_warning_is_caught() -> None:
    """成本失控必须是 blocker。降到 warning 就等于允许 107× 的成本回潮。"""
    def m(p: dict[str, Any]) -> None:
        for i in p["degradation_invariants"]["invariants"]:
            if i["metric_id"] == "cost.tokens_per_virtual_day":
                i["severity"] = "warning"

    _assert_caught(m, "test_blocker_invariants_cover_cost_latency_style_and_retrieval")


def test_case_86_retrieval_invariants_downgraded_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        for i in p["degradation_invariants"]["invariants"]:
            if i["metric_id"].startswith("retrieval."):
                i["severity"] = "warning"

    _assert_caught(m, "test_blocker_invariants_cover_cost_latency_style_and_retrieval")


def test_case_87_hard_cap_drifting_from_budget_section_is_caught() -> None:
    """同一数字在政策里出现两次时必须相同。

    这是参数层最容易腐烂的地方：改了预算忘了改不变量。
    本方案自己在第一次运行时就在这一族上翻过车（合计四舍五入），
    所以这一条必须有专门的守卫。
    """
    def m(p: dict[str, Any]) -> None:
        for i in p["degradation_invariants"]["invariants"]:
            if i["metric_id"] == "cost.tokens_per_virtual_day":
                i["hard_cap"] = 120_000

    _assert_caught(m, "test_hard_caps_agree_with_the_budget_and_slo_sections")


def test_case_88_latency_hard_cap_drifting_from_slo_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["fast_lane_first_token_ms"]["p95"] = 2000

    # 单独指向一致性检查：阶段预算之和（1000ms）在 p95 放宽后依然合法，
    # 但不变量里的 hard_cap 就与 SLO 脱钩了 —— 这是参数层最典型的腐烂方式。
    _assert_caught(m, "test_hard_caps_agree_with_the_budget_and_slo_sections")


def test_case_89_measurement_reverted_to_snapshot_is_caught() -> None:
    """退回快照式测试 = 五种退化全部隐形（它们只在趋势上可见）。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["measurement"] = "single_snapshot"

    _assert_caught(m, "test_measurement_is_longitudinal_and_ci_affordable")


def test_case_90_ci_runtime_blown_past_15_minutes_is_caught() -> None:
    """不会被真的跑起来的测试等于没有测试。15 分钟是这条赛道的生存上限。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["ci_runtime_minutes_max_mock_adapter"] = 180

    _assert_caught(m, "test_measurement_is_longitudinal_and_ci_affordable")


def test_case_91_nondeterministic_seed_is_caught() -> None:
    """没有确定性种子，趋势噪声会淹没退化信号，守卫等于不存在。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["deterministic_seed_required"] = False

    _assert_caught(m, "test_measurement_is_longitudinal_and_ci_affordable")


def test_case_92_tolerance_tuning_after_blind_test_is_caught() -> None:
    """保留旧测试规范 §16 的正确纪律：不得看完盲测结果后修改标准。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["tolerance_must_be_frozen_before_blind_test"] = False

    _assert_caught(m, "test_measurement_is_longitudinal_and_ci_affordable")


def test_case_93_injection_suite_gutted_is_caught() -> None:
    """守卫必须被证明能守卫。删掉注入用例 = 守卫未被验证。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["degradation_injection_suite"]["cases"] = (
            p["degradation_invariants"]["degradation_injection_suite"]["cases"][:2]
        )

    _assert_caught(m, "test_the_guard_itself_is_tested_by_degradation_injection")


def test_case_94_injection_case_pointing_at_unknown_metric_is_caught() -> None:
    """悬空引用：注入用例声称能让某指标变红，而该指标不存在 —— 一条假 PASS。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["degradation_injection_suite"]["cases"][0][
            "expect_red"
        ] = ["cost.tokens_per_virtual_day", "nonexistent.metric"]

    _assert_caught(m, "test_the_guard_itself_is_tested_by_degradation_injection")


def test_case_95_degradation_class_left_uncovered_is_caught() -> None:
    """维度棘轮（§76）没有注入用例覆盖 = 这类退化无人看守。"""
    def m(p: dict[str, Any]) -> None:
        cases = p["degradation_invariants"]["degradation_injection_suite"]["cases"]
        p["degradation_invariants"]["degradation_injection_suite"]["cases"] = [
            c for c in cases if "维度预算托管" not in c["inject"]
        ]

    _assert_caught(m, "test_the_guard_itself_is_tested_by_degradation_injection")


# ---------------------------------------------------------------------------
# 工程硬门与维度托管
# ---------------------------------------------------------------------------


def test_case_96_a_zero_tolerance_gate_loosened_is_caught() -> None:
    """《测试规范》§16 那六条"0 次"是全项目最好的验收设计。放开一条就破了。"""
    def m(p: dict[str, Any]) -> None:
        p["engineering_hard_gates"]["duplicate_simulated_action_on_retry"] = 1

    _assert_caught(m, "test_engineering_hard_gates_are_all_zero")


def test_case_97_a_hard_gate_quietly_deleted_is_caught() -> None:
    """删除比放宽更隐蔽：门不见了，CI 还是绿的。"""
    def m(p: dict[str, Any]) -> None:
        del p["engineering_hard_gates"]["task_dropped_without_record"]

    _assert_caught(m, "test_engineering_hard_gates_are_all_zero")


def test_case_98_dimension_creation_made_free_is_caught() -> None:
    """§72 创建权 + §75 低频禁删 = 棘轮效应。没有预算托管，维度数只增不减。"""
    def m(p: dict[str, Any]) -> None:
        p["dimension_escrow"][
            "candidate_to_trial_requires_preallocated_monthly_token_quota"
        ] = False

    _assert_caught(m, "test_dimension_creation_is_escrowed_not_free")


def test_case_99_low_frequency_dimension_deletion_allowed_is_caught() -> None:
    """反向守卫：§75 低频不等于无价值。只许休眠，不许删除。"""
    def m(p: dict[str, Any]) -> None:
        p["dimension_escrow"]["low_frequency_dimension_must_not_be_deleted"] = False

    _assert_caught(m, "test_dimension_creation_is_escrowed_not_free")


def test_case_100_quota_rejection_inventing_a_new_error_code_is_caught() -> None:
    """必须复用 M0-002 已存在的 BUDGET_EXHAUSTED，不要另造错误码。"""
    def m(p: dict[str, Any]) -> None:
        p["dimension_escrow"]["insufficient_quota_action"] = "reject_with_TOO_MANY_DIMENSIONS"

    _assert_caught(m, "test_dimension_creation_is_escrowed_not_free")


def test_case_101_dormant_dimension_not_returning_quota_is_caught() -> None:
    """休眠不归还配额 = 配额会被历史维度永久占满，新维度再也进不来。"""
    def m(p: dict[str, Any]) -> None:
        p["dimension_escrow"]["dormant_returns_quota"] = False

    _assert_caught(m, "test_dimension_creation_is_escrowed_not_free")


def test_case_102_unbounded_resonance_is_caught() -> None:
    """§22 的"共振"若不落成有界算子，就是 O(D²) 的 token 黑洞。"""
    def m(p: dict[str, Any]) -> None:
        p["dimension_escrow"]["resonance_pair_cap_per_window"] = 100_000
        p["dimension_escrow"]["cross_domain_synapse_fanin_max"] = 64

    _assert_caught(m, "test_resonance_is_an_explicit_bounded_operator")


# ---------------------------------------------------------------------------
# 编号注册表：堵住假 PASS 通道
# ---------------------------------------------------------------------------


def test_case_103_ghost_id_revived_is_caught() -> None:
    """R2-24 是幽灵编号（断层审计 G03）。让它复活就会重新产生不可追溯的 PASS。"""
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["R2-24"]["status"] = "ACTIVE"

    _assert_caught(m, "test_id_namespaces_have_single_owners")


def test_case_104_a01_a10_ownership_ambiguity_restored_is_caught() -> None:
    """A01~A10 在两份文档里 10/10 同号不同义。M2-011 §H 的"A06 通过"
    用的是架构规划义（重复投递不重复行动），而宪法 A06 = 世界搜索可用 ——
    世界搜索从未被验证过，却在 gate 上显示 PASS。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["A01..A10"]["owner"] = "架构规划 §12"

    _assert_caught(m, "test_id_namespaces_have_single_owners")


def test_case_105_unregistered_reference_allowed_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["unregistered_reference_is_ci_red"] = False

    _assert_caught(m, "test_id_namespaces_have_single_owners")


def test_case_106_dangling_reference_allowed_is_caught() -> None:
    """旧 M4-004 §G"V01~V30 覆盖"引用了 10 个不存在的场景 ——
    一条永远无法验证的测试要求，在 gate 上要么被忽略要么被伪造。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["dangling_reference_is_ci_red"] = False

    _assert_caught(m, "test_id_namespaces_have_single_owners")


def test_case_107_constitution_scenarios_left_unimplemented_is_caught() -> None:
    """V21~V30 来自宪法 §113 必须落地。"""
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["V01..V40"]["note"] = "V01~V20 已有"

    _assert_caught(m, "test_scenario_namespace_covers_the_constitution_required_range")


def test_case_108_new_milestones_unregistered_is_caught() -> None:
    """M0.1 阻塞性里程碑与 M-CI 正交持续门若未登记，就没有归属，
    下一轮重构会把它们当成幽灵编号删掉。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["M0.1"]["owner"] = ""

    _assert_caught(m, "test_scenario_namespace_covers_the_constitution_required_range")


# ---------------------------------------------------------------------------
# fail-closed 本身
# ---------------------------------------------------------------------------


def test_case_109_missing_policy_file_fails_closed() -> None:
    """政策文件缺失必须抛错，绝不能返回空 dict 兜底后"全部通过"。"""
    original = gate.POLICY_PATH
    try:
        gate.POLICY_PATH = original.parent / "does_not_exist.json"
        try:
            gate.load_policy()
        except AssertionError:
            return
        raise AssertionError("政策文件缺失时 load_policy() 未 fail-closed")
    finally:
        gate.POLICY_PATH = original


def test_case_110_corrupt_policy_file_fails_closed() -> None:
    """非法 JSON 必须抛错。这是 CASE-10（扫描器对不可解析源码 fail-closed）的政策层同构。

    临时文件写在系统 tmp 目录里，不在 governance/ 下留任何痕迹 ——
    一个会弄脏被守护目录的测试，迟早会在某次失败后把脏文件留在仓库里。
    """
    original = gate.POLICY_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "corrupt_policy.json"
            bad.write_text("{ this is not json", encoding="utf-8")
            gate.POLICY_PATH = bad
            try:
                gate.load_policy()
            except AssertionError:
                pass
            else:
                raise AssertionError("政策文件损坏时 load_policy() 未 fail-closed")
    finally:
        gate.POLICY_PATH = original


def test_case_111_truncated_policy_file_fails_closed() -> None:
    """空文件 / 顶层不是对象，同样必须抛错而不是被当成"政策全空所以全过"。"""
    original = gate.POLICY_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for body in ("", "[]", "null"):
                bad = Path(tmp) / "degenerate_policy.json"
                bad.write_text(body, encoding="utf-8")
                gate.POLICY_PATH = bad
                try:
                    loaded = gate.load_policy()
                except AssertionError:
                    continue
                except Exception:  # noqa: BLE001 - fail-closed
                    continue
                if not isinstance(loaded, dict) or not loaded:
                    continue
                raise AssertionError(f"退化政策 {body!r} 未被 fail-closed 拦截")
    finally:
        gate.POLICY_PATH = original


# ---------------------------------------------------------------------------
# 独立运行入口（与 test_runtime_policy.py 保持同一种双入口约定）
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
        except Exception as exc:  # noqa: BLE001
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} caught, {len(failures)} missed")
    print("(missed = 政策门在该变异下仍然全绿 = 守卫失效)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
