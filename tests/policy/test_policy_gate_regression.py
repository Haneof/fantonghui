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


def _key_paths(node: Any, prefix: str = "") -> dict[str, Any]:
    """收集全部字典键路径 → 值，用于判断一次变异到底改了什么。"""
    out: dict[str, Any] = {}
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.update(_key_paths(v, path))
            else:
                out[path] = v
    return out


def _assert_caught(
    mutator: Callable[[dict[str, Any]], None],
    *targets: str,
    allow_additive: bool = False,
) -> None:
    """断言：给定变异会让 *每一个* 目标断言抛错。

    要求"每个"而不是"至少一个"：一条法律被违反时，所有相关条款都应当报警，
    只报一个意味着其余条款是装饰。

    "抛错"包括 AssertionError 与任何其它异常 —— 对一个 fail-closed 的门来说，
    KeyError 冒泡出去同样是 CI 判红。但 AssertionError 之外的类型会被记录下来，
    因为那通常意味着断言写得不够前置（先崩在取数据上，而不是崩在判断上）。
    """
    # 先确认目标断言真实存在。v1.1.0 重构判决门时改名了 11 个断言，
    # 导致 24 个变异 case 的 getattr 抛 AttributeError，被 except 分支当成
    # "已抓住违宪" —— 一个假绿通道，而且是那种最难发现的假绿：
    # 重构越勤快，绿灯越多。守卫的名字必须先于守卫的行为被校验。
    absent = [n for n in targets if not callable(getattr(gate, n, None))]
    assert not absent, (
        f"变异 case 引用了不存在的判决断言（harness 假绿）: {absent}\n"
        "  判决门若已改名，请同步更新本 case 的目标；不要让它静默通过。"
    )

    # 第二类假绿：变异一个已经不存在的键。
    # v1.1.0 重写判决门时删掉/改名了若干政策字段，而旧变异 case 仍在给它们赋值 ——
    # 赋值一个不存在的键只会新增一个键，政策实质未变，于是判决门"通过"，
    # 本 harness 却报不出任何异常。这类假绿比重命名更隐蔽：它看起来像是守卫很稳。
    # 因此默认要求变异必须改动至少一个既有键；纯新增键的 case 必须显式声明
    # allow_additive=True（其存在意义就是"新增了这个键本身即违宪"）。
    before = _key_paths(gate.POLICY)
    probe = copy.deepcopy(gate.POLICY)
    mutator(probe)
    after = _key_paths(probe)
    changed_existing = [k for k in before if k in after and before[k] != after[k]]
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    # 删除或改名既有键同样是实质变异（CASE-198 的场景命名空间改名一度被误判为
    # "纯新增"）。只有"既没改动任何既有值、也没删除任何既有键、只凭空多出键"
    # 才是可疑的无效变异。
    if not changed_existing and not removed and added and not allow_additive:
        raise AssertionError(
            f"变异未改动任何既有字段，只新增了键: {added}\n"
            "  这通常意味着被变异的字段已在判决门重构中改名或删除 —— "
            "请更新本 case 指向真实字段，或在确属『新增即违宪』时传 allow_additive=True。"
        )

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


def test_case_00c_harness_rejects_a_renamed_or_missing_target() -> None:
    """守卫守卫者，第二层：_assert_caught 的目标断言必须真实存在。

    v1.1.0 重构判决门时改名了 11 个断言，导致 24 个变异 case 的 getattr
    抛 AttributeError，被 except 分支当成"已抓住违宪" —— 一个假绿通道，
    而且是那种最难发现的假绿：重构越勤快，绿灯越多。
    """
    def noop(p: dict[str, Any]) -> None:
        p["policy_version"] = "0.0.0-mutated"

    try:
        _assert_caught(noop, "test_this_gate_does_not_exist")
    except AssertionError as exc:
        assert "harness 假绿" in str(exc), f"报错信息应指明这是 harness 假绿: {exc}"
        return
    raise AssertionError("_assert_caught 未拒绝不存在的目标断言 —— harness 假绿通道仍然存在")


def test_case_00d_harness_rejects_a_mutation_that_touches_nothing_real() -> None:
    """守卫守卫者，第三层：变异必须改动至少一个既有字段。

    v1.1.0 删除/改名了若干政策字段，而旧变异 case 仍在给它们赋值 ——
    赋值一个不存在的键只会新增一个键，政策实质未变，判决门"通过"，
    harness 却报不出任何异常。这类假绿比改名更隐蔽：它看起来像守卫很稳。
    """
    def phantom(p: dict[str, Any]) -> None:
        p["heartbeat"]["a_field_that_never_existed"] = False

    try:
        _assert_caught(phantom, "test_heartbeat_gate_is_mechanical_and_precedes_the_llm")
    except AssertionError as exc:
        assert "只新增了键" in str(exc), f"报错信息应指明变异未触及真实字段: {exc}"
        return
    raise AssertionError("_assert_caught 未拒绝无效变异 —— 第二类假绿通道仍然存在")


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


def test_case_03_policy_without_a_real_enforcer_is_caught() -> None:
    """没有执法者的政策只是更长的散文。

    v1.1.0 起执法通道的真实形态是 testpaths 自动收集（不是那条未获权限的 CI 步骤），
    所以本 case 改为抽掉 enforced_by 里的 pytest 通道，并连带检查
    "政策是否如实声明了自己的执法状态"。
    """
    def m(p: dict[str, Any]) -> None:
        p["enforced_by"] = ["docs/README.md"]

    _assert_caught(m, "test_ci_wiring_status_is_honestly_declared")


def test_case_04_note_field_without_dollar_prefix_is_caught() -> None:
    """说明性字段必须以 $ 前缀标注，否则会被当成配置读取。"""
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["explanation_note"] = "这是一段会被误读为配置的说明"

    # 纯新增：本 case 的违宪点就是"新增了这个键"本身（说明性字段未加 $ 前缀）。
    _assert_caught(
        m, "test_section_keys_starting_with_dollar_are_notes_not_config",
        allow_additive=True,
    )


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


def test_case_11_fast_lane_made_haltable_is_caught() -> None:
    """§85之1 首字响应不许被预算牺牲。

    v1.0.0 的本 case 给 over_quota_policy 新增了一个 'safety' 键 ——
    而 'safety' 从来不是被预算的子系统，于是它新增了一个判决门从不读取的键，
    静默通过了一整轮。真正的教训不在 case，在判决门：它用 .get(sub) != "halt"
    校验，让"键不存在"与"键合规"返回同一个结果。两侧都已修。
    """
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["over_quota_policy"]["conversation.fast"] = "halt"

    _assert_caught(m, "test_safety_and_fast_lane_are_never_degradable")


def test_case_11b_safety_treated_as_a_budgeted_subsystem_is_caught() -> None:
    """反向守卫：安全一旦被给予配额，就存在"配额用完"的语义 ——
    而安全通道不允许有"用完"这个状态。
    """
    def m(p: dict[str, Any]) -> None:
        p["token_budget"]["subsystems"]["safety"] = {
            "monthly_cap": 1000, "basis": "安全反射"
        }
        p["token_budget"]["over_quota_policy"]["safety"] = "halt"
        # 保持零基闭合，否则先撞上预算闭合断言，掩盖本 case 想证明的东西。
        p["token_budget"]["subsystems"]["lifechapter"]["monthly_cap"] -= 1000
        p["token_budget"]["monthly_total_cap"] -= 0

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

    _assert_caught(m, "test_perceived_latency_stage_budget_can_meet_the_perceived_slo")


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

    _assert_caught(m, "test_latency_overrun_requires_perceivable_degradation")


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

    _assert_caught(m, "test_retention_uses_two_phase_tombstone_with_reference_lock")


def test_case_39_quarantine_cooldown_too_short_is_caught() -> None:
    """冷却期是 LLM 清洁工的撤销权（AV3-04）。缩到 0 天等于没有撤销权。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["quarantine_cooldown_days"] = 0

    _assert_caught(m, "test_tombstone_retention_covers_a_full_longitudinal_ci_cycle")


def test_case_40_purge_without_audit_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["purge_requires_audit_record"] = False

    _assert_caught(
        m, "test_purge_audit_record_is_enough_to_detect_tampering_without_content"
    )


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

    _assert_caught(m, "test_invariant_I1_requires_both_triggered_state_and_notification_epoch")


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


def test_case_51_zero_mistrigger_tolerance_loosened_is_caught() -> None:
    """ADJ-007 §2 把"绝对零误触"这条不可证伪的口号，换成了一个 0 容忍的可判定判据：
    false_playback_without_epoch = 0（无通知 epoch 时马达骨传导通路必须断电）。

    v1.0.0 的本 case 变异的是 zero_mistrigger_claim_is_not_falsifiable ——
    一个在 v1.1.0 已不存在的字段。它因此静默通过了一整轮，
    直到 harness 加上"变异必须改动既有字段"的守卫才暴露。
    """
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["zero_mistrigger_legal_criterion"]["false_playback_without_epoch"] = 3

    _assert_caught(m, "test_zero_mistrigger_has_exactly_one_legal_zero_tolerance_criterion")


def test_case_52_hardware_validation_list_gutted_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["delivery_fsm"]["hardware_pending_validation"] = ["待定"]

    _assert_caught(m, "test_hardware_pending_validation_is_still_honest")


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

    _assert_caught(m, "test_four_step_sequence_is_a_layout_not_a_pipeline")


def test_case_55_pipeline_order_hard_enforced_is_caught() -> None:
    """反向也要抓：强制物理执行顺序会违反 §110之14 与 §86之3。

    这一条特别重要 —— 它证明本政策门不是单向的"越严越好"，
    而是守着 C3 裁决的**两侧**。只禁"省略"不禁"僵化"的门是半个门。
    """
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["order_strictly_enforced"] = True

    # 纯新增且必须新增：违宪点正是"把那个歧义布尔字段放回来"。
    # ADJ-001 §2 之后，order_strictly_enforced 这个名字本身就是错的 ——
    # 它无法表达"排版序严格、调用序宽松"这对正交约束。
    _assert_caught(
        m, "test_layout_order_is_strict_while_call_order_is_not",
        allow_additive=True,
    )


def test_case_56_cache_without_dirty_flags_is_caught() -> None:
    """允许从缓存满足，但必须有脏标记来源，否则 AI 会用过期的人格镜像说话。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["cache_dirty_flag_source"] = []

    _assert_caught(m, "test_layout_order_is_strict_while_call_order_is_not")


def test_case_57_steps_reordered_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["steps"] = [
            "inspect_world_and_trigger", "mirror_self",
            "calibrate_rapport", "set_stance_and_tone",
        ]

    _assert_caught(m, "test_four_step_sequence_is_a_layout_not_a_pipeline")


def test_case_58_safety_path_without_deferred_calibration_is_caught() -> None:
    """安全旁路必须把 rapport/tone 推到响应**之后**，而不是省略它。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["safety_critical_compressed_path"] = [
            "mirror_self_baseline_only", "inspect_trigger"
        ]

    _assert_caught(m, "test_safety_bypass_starts_at_step0_not_at_mirror_self")


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

    _assert_caught(m, "test_heartbeat_gate_is_mechanical_and_precedes_the_llm")


def test_case_68_gate_suppressing_safety_trigger_is_caught() -> None:
    """方便度闸门绝不能压住安全触发。这是心跳机制里唯一不可让渡的一条。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["safety_trigger_never_suppressed_by_gate_or_cooldown"] = False

    _assert_caught(m, "test_absolute_floor_covers_self_commitment_tasks_not_just_safety")


def test_case_69_cancelled_heartbeat_leaves_no_patrol_record_is_caught() -> None:
    """§80之3 后台静默巡检绝不停转：被取消的心跳仍须留痕，
    否则"AI 一直在默默关心"就变成无法审计的宣称。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["cancelled_heartbeat_must_still_log_silent_patrol"] = False

    _assert_caught(m, "test_heartbeat_gate_is_mechanical_and_precedes_the_llm")


def test_case_70_heartbeat_conflated_with_source_stale_is_caught() -> None:
    """§79"数据源长时间无更新"是来源告警；§80 长平稳心跳是"一切正常该关心内心"。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["distinct_from_source_stale_trigger"] = False

    _assert_caught(m, "test_heartbeat_gate_is_mechanical_and_precedes_the_llm")


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
        p["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"]["sentence_and_char_caps_lifted"] = False

    _assert_caught(m, "test_all_four_constitutional_exceptions_to_brevity_are_declared")


def test_case_79_safety_exception_unlogged_is_caught() -> None:
    """例外必须留痕，否则"安全例外"会变成绕过一切风格约束的后门。"""
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"]["exception_must_be_logged"] = False

    _assert_caught(m, "test_all_four_constitutional_exceptions_to_brevity_are_declared")


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

    _assert_caught(m, "test_every_invariant_is_machine_checkable_and_doubly_cited")


def test_case_82_illegal_trend_verb_is_caught() -> None:
    """"improving" 不是可判定的趋势动词 —— 它没有方向也没有界。"""
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["invariants"][0]["trend"] = "improving"

    _assert_caught(m, "test_every_invariant_is_machine_checkable_and_doubly_cited")


def test_case_83_duplicate_metric_id_is_caught() -> None:
    """重复 metric_id 会让 CI 只报一条、掩盖另一条 —— 一种静默失效。"""
    def m(p: dict[str, Any]) -> None:
        inv = p["degradation_invariants"]["invariants"]
        inv[1]["metric_id"] = inv[0]["metric_id"]

    _assert_caught(m, "test_every_invariant_is_machine_checkable_and_doubly_cited")


def test_case_84_invariant_count_thinned_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["degradation_invariants"]["invariants"] = (
            p["degradation_invariants"]["invariants"][:5]
        )

    _assert_caught(
        m,
        "test_every_invariant_is_machine_checkable_and_doubly_cited",
        "test_blocker_invariants_cover_the_fatal_degradations",
    )


def test_case_85_cost_invariant_downgraded_to_warning_is_caught() -> None:
    """成本失控必须是 blocker。降到 warning 就等于允许 107× 的成本回潮。"""
    def m(p: dict[str, Any]) -> None:
        for i in p["degradation_invariants"]["invariants"]:
            if i["metric_id"] == "cost.tokens_per_virtual_day":
                i["severity"] = "warning"

    _assert_caught(m, "test_blocker_invariants_cover_the_fatal_degradations")


def test_case_86_retrieval_invariants_downgraded_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        for i in p["degradation_invariants"]["invariants"]:
            if i["metric_id"].startswith("retrieval."):
                i["severity"] = "warning"

    _assert_caught(m, "test_blocker_invariants_cover_the_fatal_degradations")


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
        p["latency_slo"]["legal_slo_from_asr_final_ms"]["p95"] = 2000

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
        p["engineering_hard_gates"]["inherited_from_test_spec"]["duplicate_simulated_action_on_retry"] = 1

    _assert_caught(m, "test_engineering_hard_gates_are_all_zero")


def test_case_97_a_hard_gate_quietly_deleted_is_caught() -> None:
    """删除比放宽更隐蔽：门不见了，CI 还是绿的。"""
    def m(p: dict[str, Any]) -> None:
        del p["engineering_hard_gates"]["inherited_from_test_spec"]["task_dropped_without_record"]

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
        p["id_namespace_registry"]["namespaces"]["V01..V45"]["note"] = "V01~V20 已有"

    _assert_caught(m, "test_scenario_namespace_covers_the_adjudication_registered_range")


def test_case_108_unapproved_proposal_presents_itself_as_baseline_is_caught() -> None:
    """ADJ-010 §3：模块/里程碑的新增、合并或改义必须走一级治理变更。

    我提出的 M0.1 / M-CI / CP1~CP4 / C17~C18 尚未经该程序批准，
    必须标记为 PROPOSAL_NOT_BASELINE。把标记摘掉，它们就会在下一份文档里
    被当成既成事实引用 —— 编号漂移正是这样开始的：不是有人造假，
    是有人把提案写成了现状。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["M0.1"]["status"] = "BASELINE"

    _assert_caught(m, "test_contested_namespaces_are_marked_as_proposals_not_baselines")


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


# ===========================================================================
# CASE-112 起：v1.1.0 按 ADJ-001~012 裁决集新增的政策面
# ===========================================================================


# ---------------------------------------------------------------------------
# Step-0 机械安全闸（ADJ-001 §1，最高级裁决）
# ---------------------------------------------------------------------------


def test_case_112_step0_allowed_to_call_a_model_is_caught() -> None:
    """ADJ-001 §1：Step-0 零模型调用。

    若 Step-0 需要模型调用，它就不是闸门而是又一次开销 ——
    "为了决定要不要打扰用户先花一次完整四步序"的浪费会原样复现。
    """
    def m(p: dict[str, Any]) -> None:
        p["step0_safety_gate"]["model_calls"] = 1

    _assert_caught(m, "test_step0_gate_runs_before_mental_steps_with_zero_model_calls")


def test_case_113_step0_verdict_enum_widened_is_caught() -> None:
    """OK / QUIET / HARD_BLOCK 必须闭合，否则实现会自造第四种语义。"""
    def m(p: dict[str, Any]) -> None:
        p["step0_safety_gate"]["verdicts"] = ["OK", "QUIET", "HARD_BLOCK", "MAYBE"]

    _assert_caught(m, "test_step0_verdicts_are_a_closed_three_value_enum")


def test_case_114_hard_block_also_stops_silent_patrol_is_caught() -> None:
    """ADJ-001 §1：§80之3『后台静默巡检绝对不停转』优先于 HARD_BLOCK。

    若禁言期间连观察都停掉，AI 会对世界彻底失明 —— 那比打扰用户严重得多。
    """
    def m(p: dict[str, Any]) -> None:
        p["step0_safety_gate"]["hard_block_still_allows"] = ["safety_watch"]

    _assert_caught(m, "test_step0_hard_block_does_not_stop_silent_patrol")


def test_case_115_step0_verdicts_left_unaudited_is_caught() -> None:
    """ADJ-001 §1：全部判定物化进 Session 审计，不得用隐藏思维链代替。"""
    def m(p: dict[str, Any]) -> None:
        p["step0_safety_gate"]["hidden_chain_of_thought_substitute_prohibited"] = False

    _assert_caught(m, "test_step0_verdicts_are_auditable_not_hidden")


def test_case_116_budget_gate_removed_from_step0_is_caught() -> None:
    """ADJ-001 §1(d)：预算闸门是 Step-0 的第四项检查。

    抽掉它，token_budget 就退回成事后监控 —— 钱花完了才被看见。
    """
    def m(p: dict[str, Any]) -> None:
        del p["step0_safety_gate"]["checks"]["d_budget_gate"]

    _assert_caught(
        m,
        "test_step0_covers_all_four_mechanical_checks",
        "test_budget_gate_is_wired_into_step0",
    )


def test_case_117_channel_legality_check_drops_the_epoch_is_caught() -> None:
    """ADJ-007 §2 的 false_playback_without_epoch=0 唯一执行点就在 Step-0 §1(c)。"""
    def m(p: dict[str, Any]) -> None:
        p["step0_safety_gate"]["checks"]["c_channel_legality"] = "检查音量是否合适"

    _assert_caught(m, "test_step0_covers_all_four_mechanical_checks")


# ---------------------------------------------------------------------------
# 延迟：两个计时边界（ADJ-007 §1）
# ---------------------------------------------------------------------------


def test_case_118_perceived_slo_relaxed_to_match_legal_is_caught() -> None:
    """体感 SLO 必须严于法定 SLO，否则它不构成额外约束，产品会合法地慢。"""
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["perceived_slo_from_speech_onset_ms"]["p95"] = 1500

    _assert_caught(m, "test_latency_slo_declares_two_distinct_measurement_boundaries")


def test_case_119_self_set_slo_passed_off_as_legal_is_caught() -> None:
    """体感 SLO 必须诚实标注为本政策层自设，不得冒充法定值。

    冒充的后果是审计口径混乱：法定 SLO 的计时起点是 ASR final，
    体感的是语音起点，两者相差 230~450ms，混用会得出完全相反的结论。
    """
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["perceived_slo_from_speech_onset_ms"]["authority"] = "ADJ-007 §1"

    _assert_caught(m, "test_latency_slo_declares_two_distinct_measurement_boundaries")


def test_case_120_cold_path_claiming_the_warm_promise_is_caught() -> None:
    """ADJ-007 §1：冷连接/冷模型/深调查车道必须显式标注不在此承诺内。"""
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["cold_path_and_deep_lane_explicitly_out_of_promise"] = False

    _assert_caught(m, "test_latency_slo_declares_two_distinct_measurement_boundaries")


def test_case_121_stage_boundary_flag_removed_is_caught() -> None:
    """每个阶段必须声明是否属于法定边界。不声明就等于默认两种边界混用。"""
    def m(p: dict[str, Any]) -> None:
        del p["latency_slo"]["stage_budget_ms"]["network_rtt"]["inside_legal_slo"]

    _assert_caught(m, "test_perceived_latency_stage_budget_can_meet_the_perceived_slo")


def test_case_122_vad_counted_inside_the_legal_boundary_is_caught() -> None:
    """把 VAD 尾静音算进法定边界，会用一段不属于法定范围的耗时挤占真实预算，
    得出虚假的"超支"结论 —— 然后团队会去优化一个根本不该被计入的阶段。
    """
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["stage_budget_ms"]["vad_tail_silence"]["inside_legal_slo"] = True

    # 注意：这个变异在算术上是"达标"的 —— 加上 VAD 之后法定边界内串行和
    # 800ms 仍小于 p95 1500ms，纯算术断言抓不到它。必须由物理位置断言来抓。
    _assert_caught(m, "test_latency_stage_boundaries_match_their_physical_position")


def test_case_123_tts_folded_into_first_token_is_caught() -> None:
    """ADJ-007 §1：法定 SLO 不含后置 TTS 完整成句，那是 TTFAudio 指标。"""
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["tts_full_sentence_is_a_separate_metric"] = "included_in_first_token"

    _assert_caught(m, "test_tts_is_a_separate_metric")


def test_case_124_overrun_times_out_silently_is_caught() -> None:
    """ADJ-007 §1：超出时必须有用户可感知降级。静默超时是最坏结果 ——
    用户不知道系统在忙还是死了。
    """
    def m(p: dict[str, Any]) -> None:
        p["latency_slo"]["overrun_requires_user_perceivable_degradation"] = []

    _assert_caught(m, "test_latency_overrun_requires_perceivable_degradation")


# ---------------------------------------------------------------------------
# 心智启动（ADJ-001 §2/§3）
# ---------------------------------------------------------------------------


def test_case_125_layout_order_loosened_is_caught() -> None:
    """ADJ-001 §2：段落排版顺序必须严格，且有静态校验。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["layout_order_strictly_enforced"] = False

    _assert_caught(m, "test_layout_order_is_strict_while_call_order_is_not")


def test_case_126_call_order_hard_enforced_is_caught() -> None:
    """双向守卫：调用顺序被强制会违反 §110之14 与 §86之3。

    只禁"省略"不禁"僵化"的门是半个门 —— 而 ADJ-001 的全部价值
    就在于它同时给出了两侧。
    """
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["call_order_strictly_enforced"] = True

    _assert_caught(m, "test_layout_order_is_strict_while_call_order_is_not")


def test_case_127_second_round_trip_permitted_is_caught() -> None:
    """ADJ-001 §2 验收锚：≥2 次往返才能完成首次响应 = 违宪。

    这是一条比任何语义断言都容易自动校验的红线：数网络往返次数即可。
    它同时保住 §84（四步都在）与 §85之1（1 秒首字）。
    """
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["first_response_round_trips_max"] = 2

    _assert_caught(m, "test_first_response_requires_at_most_one_round_trip")


def test_case_128_round_trips_not_traced_is_caught() -> None:
    """没有 trace 字段，这条红线就无法取证 —— 无法取证的红线等于没有红线。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["trace_fields"] = ["step", "tokens", "elapsed_ms"]

    _assert_caught(
        m,
        "test_first_response_requires_at_most_one_round_trip",
        "test_mental_startup_is_observable",
    )


def test_case_129_three_firsts_collapsed_onto_one_subsystem_is_caught() -> None:
    """ADJ-001 §3 是整套裁决里最漂亮的一处解法：三条各自宣称"第一"的条款
    并非互斥，而是作用于三个不同子系统（调度类/信道类/装配置版类）。

    把它们塌缩到同一个子系统，C3 矛盾就会原地复活。
    """
    def m(p: dict[str, Any]) -> None:
        three = p["mental_startup"]["three_firsts_are_different_subsystems"]
        three["convenience_is_first"]["subsystem"] = "调度类"
        three["four_step_is_first"]["subsystem"] = "调度类"

    _assert_caught(m, "test_the_three_firsts_are_assigned_to_different_subsystems")


def test_case_130_safety_bypass_starts_with_mirror_self_is_caught() -> None:
    """ADJ-001 分歧实质点名的生产事故：『安全信号会被先照镜子阻塞』。

    v1.0.0 我写的旁路第一步正是 mirror_self_baseline_only ——
    用户说"我胸口好疼"时，AI 先花一次模型调用决定自己的心境。
    """
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["safety_critical_compressed_path"] = [
            "mirror_self_baseline_only", "inspect_trigger", "calibrate_rapport_and_tone_afterwards"
        ]

    _assert_caught(m, "test_safety_bypass_starts_at_step0_not_at_mirror_self")


def test_case_131_paragraph_order_diverges_from_steps_is_caught() -> None:
    """四步序（语义）与 Manifest 段落序（排版）必须一一对应，否则静态校验无从下手。"""
    def m(p: dict[str, Any]) -> None:
        p["mental_startup"]["manifest_paragraph_order"] = [
            "step4_world", "step1_self", "step2_rapport", "step3_stance"
        ]

    _assert_caught(m, "test_four_step_sequence_is_a_layout_not_a_pipeline")


# ---------------------------------------------------------------------------
# 回溯标注（ADJ-005）
# ---------------------------------------------------------------------------


def test_case_132_valid_time_and_learned_at_merged_is_caught() -> None:
    """ADJ-005 的实质是 bi-temporal：valid_time 与 learned_at 必须分离。

    二者合一就无法同时呈现"当时映照（当时不知道）"与"今日回看（今日知道）"——
    而那是 §93 不可篡改与 §31之一 反向修正权能共存的唯一方式。
    """
    def m(p: dict[str, Any]) -> None:
        p["retrospective_annotation"]["bi_temporal_required"] = False

    _assert_caught(m, "test_retrospective_annotation_is_bi_temporal")


def test_case_133_annotation_schema_field_dropped_is_caught() -> None:
    """ADJ-005 §1 规定的五字段缺一不可。丢掉 anchor_ref 的 pin，
    标注就会随被标注对象的后续修订而漂移。
    """
    def m(p: dict[str, Any]) -> None:
        del p["retrospective_annotation"]["schema_fields"]["anchor_ref"]

    _assert_caught(m, "test_retrospective_annotation_is_the_only_legal_backpropagation")


def test_case_134_in_place_overwrite_relegalised_is_caught() -> None:
    """把唯一合法操作从"追加"改成"原地更新"，§93 就形同虚设。"""
    def m(p: dict[str, Any]) -> None:
        p["retrospective_annotation"]["only_legal_operation"] = "update_annotation_in_place"

    _assert_caught(m, "test_retrospective_annotation_is_the_only_legal_backpropagation")


def test_case_135_prohibited_operations_list_emptied_is_caught() -> None:
    """禁例必须具体，否则"追加式标注"会被实现成"追加式覆写"。"""
    def m(p: dict[str, Any]) -> None:
        p["retrospective_annotation"]["prohibited_operations"] = ["不要乱改历史"]

    _assert_caught(m, "test_prohibited_backpropagation_operations_are_enumerated")


def test_case_136_byte_hash_drift_tolerated_is_caught() -> None:
    """ADJ-005 验收锚：物理 Observation 字节级哈希变分 = 0。"""
    def m(p: dict[str, Any]) -> None:
        p["retrospective_annotation"]["observation_byte_hash_drift"] = 1

    _assert_caught(
        m,
        "test_observation_byte_hash_drift_is_a_zero_tolerance_blocker",
        "test_hard_caps_agree_with_the_budget_and_slo_sections",
    )


# ---------------------------------------------------------------------------
# 留存与删除治理（ADJ-004，Blocker 级）
# ---------------------------------------------------------------------------


def test_case_137_llm_granted_phase2_delete_permission_is_caught() -> None:
    """本次对齐里最重要的一处改正。

    v1.0.0 我把 LLM 的角色写成策略偏好（llm_role='tie_break_only'，可被配置改掉）；
    ADJ-004 §3 写成能力边界（llm_direct_call_permission=false，LLM 根本没有该权限）。
    策略偏好可以被绕过，能力边界不能。对一个把"删除"交给语言模型判断的系统，
    这个区别就是"偶尔删错"与"结构上不可能删错"的区别。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["two_phase_deletion"]["phase_2_physical_shred"][
            "llm_direct_call_permission"
        ] = True

    _assert_caught(m, "test_llm_has_no_phase2_delete_permission_as_a_capability_boundary")


def test_case_138_phase2_caller_list_widened_is_caught() -> None:
    """即使 llm_direct_call_permission=false，只要 callable_by 里多一个调用者，
    能力边界就破了。两条断言必须同时守。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["two_phase_deletion"]["phase_2_physical_shred"][
            "callable_by"
        ] = ["mechanical_retention_worker", "cognition_worker"]

    _assert_caught(m, "test_llm_has_no_phase2_delete_permission_as_a_capability_boundary")


def test_case_139_mechanical_audit_check_dropped_is_caught() -> None:
    """引用锁 / 对象类别 / legal hold 三项机械审计缺一不可。
    丢掉 legal hold，法定保全中的证据就会被"合规地"粉碎。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["two_phase_deletion"]["phase_2_physical_shred"][
            "mechanical_audit_checks"
        ] = ["reference_lock", "object_class"]

    _assert_caught(m, "test_llm_has_no_phase2_delete_permission_as_a_capability_boundary")


def test_case_140_immortal_class_removed_from_the_lock_list_is_caught() -> None:
    """ADJ-004 §1(a)：十二类对象的版本链永存。摘掉 EvidenceSet，
    证据链就可以被"合规地"删除 —— §27『证据链绝对不可逆断裂』当场失效。
    """
    def m(p: dict[str, Any]) -> None:
        chains = p["retention_policy"][
            "immortal_object_classes_reference_lock_exempt"
        ]["version_chains_always_immortal"]
        chains.remove("EvidenceSet")

    _assert_caught(m, "test_immortal_object_classes_are_enumerated_with_reference_lock")


def test_case_141_deletion_log_made_mortal_is_caught() -> None:
    """ADJ-004 §1(c)：DeletionLog 本身永存。否则删除记录可被删除，审计闭环断裂 ——
    一个能抹掉自己抹除痕迹的系统，无法被审计。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["immortal_object_classes_reference_lock_exempt"][
            "deletion_log_itself_immortal"
        ] = False

    _assert_caught(m, "test_immortal_object_classes_are_enumerated_with_reference_lock")


def test_case_142_reference_lock_on_observations_dropped_is_caught() -> None:
    """ADJ-004 §1(b)：被永存对象引用的 Observation 与原话切片永存。
    少了引用锁，Claim 还在而它引用的原话没了 —— 断链。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["immortal_object_classes_reference_lock_exempt"][
            "observations_immortal_when_referenced_by_above"
        ] = False

    _assert_caught(m, "test_immortal_object_classes_are_enumerated_with_reference_lock")


def test_case_143_revocable_conditions_reduced_is_caught() -> None:
    """ADJ-004 §2(b) 的三条件缺一不可。尤其 ① transform lineage 已落库 ——
    它保证删掉原始数据后语义化结论仍可审计追溯。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["revocable_object_classes_only"][
            "raw_high_frequency_waveform_or_image"
        ]["requires_all_three"] = ["② 未被任何永存对象引用", "③ 不在 legal hold 下"]

    _assert_caught(m, "test_revocable_objects_require_all_three_conditions")


def test_case_144_excavation_returns_not_found_is_caught() -> None:
    """ADJ-004 §4 出土兼容性 —— v1.0.0 完全缺失的最后一道防线。

    not_found 会被上层认知解读为"这件事从未发生过"，
    Tombstone 解读为"发生过，但原始载体已依法销毁"。
    前者是历史虚无，后者是历史诚实。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["excavation_compatibility"][
            "query_shredded_canonical_id_must_return"
        ] = "not_found"

    _assert_caught(m, "test_excavation_returns_tombstone_not_not_found")


def test_case_145_tombstone_hit_rate_below_one_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["excavation_compatibility"]["tombstone_lookup_hit_rate"] = 0.95

    _assert_caught(m, "test_excavation_returns_tombstone_not_not_found")


def test_case_146_erasure_vs_legal_hold_left_undecided_is_caught() -> None:
    """引用锁（工程侧：什么可以删）与 erasure right（法律侧：什么必须删）会真实冲突。

    冲突若没有事先裁定的胜方，实现者会在两个 if 分支里各选一边，
    结果是同一个对象在不同代码路径下有不同的删除语义。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["legal_override"][
            "conflicts_with_reference_lock_resolution"
        ] = "由实现者根据具体情况判断"

    _assert_caught(m, "test_erasure_vs_reference_lock_conflict_has_a_declared_winner")


def test_case_147_tombstone_period_shorter_than_ci_window_is_caught() -> None:
    """ADJ-004 §3：≥30 天 + 一个虚拟周。

    额外那一个虚拟周让压缩 30 虚拟日的纵向 CI 有机会观察到删除的下游后果；
    若墓碑期短于 CI 窗口，删除引发的断链会表现为"数据本来就不存在"，无法归因。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["two_phase_deletion"]["phase_1_tombstone"][
            "min_retention"
        ] = "≥ 7 天"

    _assert_caught(m, "test_tombstone_retention_covers_a_full_longitudinal_ci_cycle")


# ---------------------------------------------------------------------------
# 声纹簇生命周期（ADJ-009）
# ---------------------------------------------------------------------------


def test_case_148_retirement_treated_as_deletion_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["retirement_is_not_deletion"] = False

    _assert_caught(m, "test_speaker_cluster_retirement_is_not_deletion")


def test_case_149_cluster_state_machine_loses_retired_is_caught() -> None:
    """ACTIVE → RETIRED → TOMBSTONE 三态缺一不可。跳过 RETIRED，
    退休就直接变成删除，历史引用当场断链。
    """
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["cluster_states"] = ["ACTIVE", "TOMBSTONE"]

    _assert_caught(m, "test_speaker_cluster_retirement_is_not_deletion")


def test_case_150_old_cluster_resurrected_without_probe_is_caught() -> None:
    """ADJ-009 §2：没有连续性探针，一个声音相似的陌生人会被合并进旧簇，
    于是"老张说过的话"里混进了别人说的话 —— 对 §36 在声学域的直接违反。
    """
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["reidentification_requires_continuity_probe"] = False

    _assert_caught(m, "test_cluster_resurrection_requires_a_continuity_probe")


def test_case_151_probe_criteria_narrowed_to_user_confirmation_only_is_caught() -> None:
    """探针接受三种连续性之一。只留"明确确认"，
    老年用户与不善表达的用户就永远无法续上自己的声纹历史。
    """
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["continuity_probe_accepts_any_of"] = [
            "explicit_user_or_ai_confirmation"
        ]

    _assert_caught(m, "test_cluster_resurrection_requires_a_continuity_probe")


def test_case_152_identity_bound_at_cluster_layer_is_caught() -> None:
    """ADJ-009 §2 的关键设计：身份归 PersonEntity，簇只是证据载体。

    若把身份绑在簇上，簇的每一次退休都会造成一次人格层的信息损失。
    """
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["on_probe_failure"] = "新建簇，并把关系建立在簇层"

    _assert_caught(m, "test_probe_failure_binds_identity_at_the_entity_layer")


def test_case_153_voiceprint_provenance_made_revocable_is_caught() -> None:
    """ADJ-009 §3：删掉波形但保留"从何时来自哪里进入"，归因能力就还在 ——
    这是 §27 在存储成本约束下唯一可行的解。
    """
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["immortal_parts"] = ["cluster_feature_vector"]

    _assert_caught(m, "test_voiceprint_provenance_is_immortal_while_raw_audio_is_revocable")


# ---------------------------------------------------------------------------
# 阈值治理（ADJ-008）
# ---------------------------------------------------------------------------


def test_case_154_safety_threshold_opened_to_downward_learning_is_caught() -> None:
    """ADJ-008(d)：人身安全参数不进入学习型下调通道，只允许向更严修改。

    磨钝是渐进的、每一步都"有依据"的，因此快照式测试永远抓不到它；
    只有方向单调性约束能。
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["safety_parameter_direction_constraint"] = (
            "learnable_in_both_directions"
        )

    _assert_caught(m, "test_safety_thresholds_may_only_move_stricter")


def test_case_155_threshold_ledger_not_rollbackable_is_caught() -> None:
    """ADJ-008(c)：可回放与可回滚是两个独立要求。只可回放不可回滚，
    AI 就能一路把阈值学坏而无人能撤销。
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["change_log_must_be_rollbackable"] = False

    _assert_caught(m, "test_every_threshold_evolution_step_is_logged_replayable_and_rollbackable")


def test_case_156_threshold_value_written_into_constitution_is_caught() -> None:
    """ADJ-008(a)：不允许在宪法原文写数值。§76 早就说过阈值是可测试参数，
    不是宪法常量 —— 写进宪法的数字改一次要走一级修宪，于是没人敢改，于是它烂在那里。
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["numeric_values_prohibited_in_constitution_text"] = False

    _assert_caught(
        m, "test_thresholds_are_secondary_governance_parameters_not_constitution_text"
    )


def test_case_157_baseline_moved_out_of_governance_dir_is_caught() -> None:
    """ADJ-008(b)：出厂基线冻结在 governance/thresholds/。
    挪进 src/ 就意味着它可以被一次普通代码提交改掉，而不经治理流程。
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["factory_baseline_frozen_in"] = "src/aios_core/config.py"

    _assert_caught(
        m, "test_thresholds_are_secondary_governance_parameters_not_constitution_text"
    )


# ---------------------------------------------------------------------------
# 心跳（ADJ-002 / ADJ-003）
# ---------------------------------------------------------------------------


def test_case_158_heartbeat_interval_repromoted_to_law_is_caught() -> None:
    """ADJ-002 §1：3~5 小时是出厂默认，不是铁律。

    v1.0.0 我把它写成上下限，语义上等于铁律 —— 正好撞上 §80之3 的反馈自适应。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["interval_hours_is_factory_default_not_law"] = False

    _assert_caught(m, "test_heartbeat_interval_is_a_factory_default_not_a_law")


def test_case_159_bare_interval_bounds_reintroduced_is_caught() -> None:
    """把裸的 interval_hours 上下限字段放回来，铁律语义就回来了。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["interval_hours"] = {"min": 3, "max": 5}

    _assert_caught(
        m, "test_heartbeat_interval_is_a_factory_default_not_a_law", allow_additive=True
    )


def test_case_160_candidate_wake_becomes_a_promise_to_speak_is_caught() -> None:
    """ADJ-002 §2：候选唤醒而非承诺出声。

    若心跳是"承诺出声"，§5『有能力帮助不等于必须打扰』就被心跳机制自己违反了。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["candidate_wake_not_promise_to_speak"] = False

    _assert_caught(m, "test_heartbeat_wake_is_a_candidate_not_a_promise_to_speak")


def test_case_161_step0_loses_its_final_veto_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["step0_convenience_check_has_final_veto"] = False

    _assert_caught(m, "test_heartbeat_wake_is_a_candidate_not_a_promise_to_speak")


def test_case_162_self_commitment_tasks_removed_from_the_floor_is_caught() -> None:
    """ADJ-002 §4。v1.0.0 我只写了安全项，漏掉了自承诺任务 ——
    因为我按"安全"的思路在想。但用户自己登记的吃药与复检提醒不是安全项，
    它是人格层承诺：AI 答应过的事，不该因为 AI 学到"他最近嫌我烦"就被静默下调。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["absolute_floor_not_subject_to_rhythm_learning"] = [
            "personal_safety_watch_channel"
        ]

    _assert_caught(m, "test_absolute_floor_covers_self_commitment_tasks_not_just_safety")


def test_case_163_feedback_cooldown_bypassable_is_caught() -> None:
    """ADJ-002 §3：禁止以『维持心跳』为由绕过反馈冷却。

    这条禁令堵住一个自证循环：AI 学到用户嫌它烦 → 但为了"维持关系节律"继续出声
    → 用户更烦。每一次绕过在日志里看起来都是合理的。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["feedback_cooldown_is_hard_constraint"] = False

    _assert_caught(m, "test_feedback_cooldown_cannot_be_bypassed_to_sustain_heartbeat")


def test_case_164_fixed_rhythm_bombing_tolerated_is_caught() -> None:
    """ADJ-002 验收锚：7 天平稳数据下固定节奏炸弹数 = 0。

    "为了维持关系而打扰关系"是这个产品最讽刺的失败模式。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["fixed_rhythm_bomb_count_under_7d_stable_data"] = 5

    _assert_caught(m, "test_fixed_rhythm_bombing_is_a_zero_tolerance_blocker")


def test_case_165_self_invented_wake_source_name_is_caught() -> None:
    """ADJ-003 已把『关系节奏候选』注册为 WakeSource 扩展。

    v1.0.0 我自拟了 LONG_STABLE_HEARTBEAT —— 一个政策层作者亲手制造的编号漂移源。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["trigger_kind_name"] = "LONG_STABLE_HEARTBEAT"

    _assert_caught(m, "test_heartbeat_wake_is_a_candidate_not_a_promise_to_speak")


def test_case_166_mechanical_trigger_allowed_to_conclude_is_caught() -> None:
    """ADJ-003：§79 的 8 类机械触发只产出二值信号，不直接产生语义结论。

    若机械触发能直接产生结论，§77『触发器不负责理解人生』就被绕过了 ——
    一个心率阈值越线会直接变成"他今天压力很大"这样的认知。
    """
    def m(p: dict[str, Any]) -> None:
        p["task_readiness"]["mechanical_trigger_output_is_binary_signal_only"] = False

    _assert_caught(m, "test_mechanical_triggers_yield_binary_signals_not_semantic_conclusions")


# ---------------------------------------------------------------------------
# 风格（ADJ-007 §3）
# ---------------------------------------------------------------------------


def test_case_167_priority_order_inverted_is_caught() -> None:
    """ADJ-007 §3 结论句：『1~3 句』服从于事实完整与安全，不服从于"看起来不像机器人"。

    这是优先级裁定而非例外清单。差别在于：例外清单告诉实现者"这些情况可以长"，
    优先级告诉实现者"冲突时牺牲哪一个"。v1.0.0 我写了例外没写优先级，
    于是实现者仍可能为了"像个真人"砍掉必要信息 —— 而且砍得理直气壮，因为政策说了要短。
    """
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["priority_order"] = ["1~3 句短表达", "事实完整", "安全"]

    _assert_caught(m, "test_brevity_is_subordinate_to_truth_and_safety")


def test_case_168_anti_robot_appearance_accepted_as_a_reason_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"][
            "anti_robot_appearance_is_not_a_valid_reason_to_truncate"
        ] = False

    _assert_caught(m, "test_brevity_is_subordinate_to_truth_and_safety")


def test_case_169_an_exception_silently_dropped_is_caught() -> None:
    """ADJ-007 §3 的四类例外是事先立宪的，少一类就等于那一类用户被 3 句上限掐断。"""
    def m(p: dict[str, Any]) -> None:
        del p["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
            "c_accessibility_default_reversal"
        ]

    _assert_caught(m, "test_all_four_constitutional_exceptions_to_brevity_are_declared")


def test_case_170_accessibility_written_as_an_exception_not_a_default_is_caught() -> None:
    """ADJ-007 §3(c) 是"默认反转"而非"例外放行"。差别有实际后果：
    写成例外，实现者只在检测到明确请求时才放宽，而老年用户往往不会请求。
    """
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
            "c_accessibility_default_reversal"
        ]["verbosity_is_default"] = False

    _assert_caught(
        m, "test_accessibility_reverses_the_default_rather_than_granting_an_exception"
    )


def test_case_171_vague_expansion_request_not_treated_as_signal_is_caught() -> None:
    """ADJ-007 §3(a)：措辞模糊也算信号。

    若只匹配"展开/详细说说"，用户说"讲讲你到底怎么想的"就会被 3 句上限掐断 ——
    而那句话恰恰是最需要长答的。
    """
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
            "a_user_explicitly_requests_expansion"
        ]["vague_wording_also_counts_as_signal"] = False

    _assert_caught(m, "test_vague_expansion_requests_count_as_signal")


def test_case_172_fact_gap_breakthrough_unlogged_is_caught() -> None:
    """ADJ-007 §3(d)：突破限制必须留痕，否则这一类例外会变成绕过一切风格约束的后门。
    "我觉得这里需要说清楚"若无审计，就是"我想说多少说多少"。
    """
    def m(p: dict[str, Any]) -> None:
        p["style_constraints"]["tier_3_exceptions_constitutionally_predeclared"][
            "d_short_answer_would_create_fact_gap"
        ]["must_record_in_CommExp_for_audit"] = False

    _assert_caught(m, "test_fact_gap_exception_must_leave_an_audit_trail_in_commexp")


# ---------------------------------------------------------------------------
# 检索语义防火墙（ADJ-006）
# ---------------------------------------------------------------------------


def test_case_173_fusion_score_feeding_confidence_is_caught() -> None:
    """ADJ-006：『fusion 权重提高的是候选质量，不是真值概率』。

    这直接约束 M1-012 规约里的 CoSearchHit.density_score。漏掉这条，
    检索得分就会伪装成认知置信度 —— AI 会"因为找到了很多相关记录"
    而相信一个并未被证据核验的结论。
    """
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["semantic_firewall"][
            "fusion_score_must_not_enter_confidence_path"
        ] = False

    _assert_caught(m, "test_fusion_score_cannot_leak_into_confidence_path")


def test_case_174_legal_output_contract_widened_is_caught() -> None:
    """ADJ-006 §1：co_search 的法定输出只有三项。多加一个 confidence 或 truth，
    检索层就在替认知层做判断。
    """
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["semantic_firewall"]["legal_output_contract"] = [
            "candidate_slice_pointers", "hit_reasons", "coverage", "confidence"
        ]

    _assert_caught(m, "test_semantic_firewall_separates_candidates_from_causality")


def test_case_175_cooccurrence_claimed_to_establish_truth_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["retrieval_slo"]["semantic_firewall"][
            "cooccurrence_intersection_does_not_establish"
        ] = "high_confidence_claim"

    _assert_caught(m, "test_semantic_firewall_separates_candidates_from_causality")


def test_case_176_old_resonance_wording_kept_is_caught() -> None:
    """ADJ-006 §1：『共振密集区』重命名为『候选密集区』，消灭检索→因果的混淆口。
    名字不是小事 —— 它会决定工程师敢用它做什么。
    """
    def m(p: dict[str, Any]) -> None:
        p["manifest_layer_caps"]["resonance_dense_area_renamed_to"] = "resonance_dense_area"

    _assert_caught(m, "test_resonance_dense_area_is_renamed_per_adj006")


# ---------------------------------------------------------------------------
# 稳定键制度与裁决对齐（ADJ-010 / ADJ-011 / ADJ-012）
# ---------------------------------------------------------------------------


def test_case_177_unregistered_stable_key_cited_is_caught() -> None:
    """跨文件引用完整性：稳定键制度若允许引用不存在的键，
    它就退化成了另一套会漂移的编号 —— 而漂移正是它要消灭的东西。
    """
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["constitution_stable_keys"] = ["C23-heartbeat", "C99-invented_key"]

    _assert_caught(m, "test_every_cited_stable_key_is_actually_registered")


def test_case_178_section_reverts_to_bare_clause_numbers_is_caught() -> None:
    """ADJ-011 §2：『条号本身即为不能再承载语义的印刷物』。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["constitution_stable_keys"] = []

    _assert_caught(m, "test_every_auditable_section_cites_the_constitution")


def test_case_179_stable_key_recycling_permitted_is_caught() -> None:
    """ADJ-011 §1：键在章节内局部顺序追加，绝不回收复用。

    回收复用会让旧 Issue 里的引用悄悄指向新含义 —— 正是 A01~A10 事故的成因。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["stable_key_regime"]["keys_never_recycled"] = False

    _assert_caught(m, "test_stable_key_regime_is_declared_with_no_recycling")


def test_case_180_an_adjudication_left_unmapped_is_caught() -> None:
    """漏一条裁决，就等于该裁决在运行时没有执法者。"""
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["items"] = [
            it for it in p["adjudication_alignment"]["items"] if it["adj"] != "ADJ-009"
        ]

    _assert_caught(m, "test_all_twelve_adjudications_are_mapped")


def test_case_181_ghost_adjudication_number_invented_is_caught() -> None:
    """裁决集只有 12 条。凭空多出一个 ADJ-013 就是幽灵编号 —— 与 R2-24 同一类事故。"""
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["items"].append({
            "adj": "ADJ-013", "title": "凭空出现的裁决", "verdict": "COMPATIBLE_ENCODED",
            "policy_fields": [], "$finding": "幽灵编号",
        })

    _assert_caught(m, "test_all_twelve_adjudications_are_mapped")


def test_case_182_alignment_claiming_a_field_that_does_not_exist_is_caught() -> None:
    """"已按 ADJ 改写"若指向一个不存在的字段，就是比缺失更难发现的假 PASS ——
    它让审阅者以为工作已完成。
    """
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["items"][0]["policy_fields"] = [
            "step0_safety_gate.nonexistent_field"
        ]

    _assert_caught(m, "test_every_claimed_policy_field_actually_exists")


def test_case_183_verdict_counts_fudged_is_caught() -> None:
    """一份自相矛盾的自评等于没有自评。

    这一条在 v1.1.0 落盘时真的触发过：我声明 5 条 ADJ_SHARPER_ADOPTED，
    逐条数下来是 6 条。
    """
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["summary_counts"]["I_WAS_WRONG_CORRECTED"] = 0

    _assert_caught(m, "test_alignment_verdict_counts_are_self_consistent")


def test_case_184_verdict_outside_the_legend_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["items"][0]["verdict"] = "MOSTLY_FINE"

    _assert_caught(m, "test_alignment_verdict_counts_are_self_consistent")


def test_case_185_alignment_item_without_a_finding_is_caught() -> None:
    """只打标签不写清"这条裁决改变了什么"，对齐就是装饰。"""
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["items"][0]["$finding"] = ""

    _assert_caught(m, "test_alignment_verdict_counts_are_self_consistent")


def test_case_186_adjudication_left_without_any_enforcement_point_is_caught() -> None:
    """这是本次对齐新增的元断言，也是最重要的一条。

    一份政策可以逐条引用 12 项裁决、写得头头是道，而没有任何一条能在 CI 里判红 ——
    那它就还是文学。D1 的诊断（宪法是文学不是法律）会在政策层原样复发。
    """
    def m(p: dict[str, Any]) -> None:
        del p["engineering_hard_gates"]["added_by_adjudication_set"][
            "mechanical_trigger_produced_semantic_conclusion"
        ]

    _assert_caught(m, "test_every_adjudication_has_at_least_one_enforcing_invariant_or_gate")


def test_case_187_precedence_rule_inverted_is_caught() -> None:
    """裁决集明文『凡 v3.0 原文与本裁决集冲突处，以本裁决集为准』。
    政策层若自居上位，就会在某次"我觉得这样更合理"的修改里悄悄与裁决集分叉。
    """
    def m(p: dict[str, Any]) -> None:
        p["adjudication_alignment"]["precedence_rule"] = "本文件 > ADJ"

    _assert_caught(m, "test_policy_declares_adjudication_set_as_upstream_authority")


def test_case_188_baseline_still_declaring_v3_0_is_caught() -> None:
    """上位法已升级为 CONST-v3.0.1。基线声明停留在 v3.0，
    等于整套政策对着一个已被修订的宪法执法。
    """
    def m(p: dict[str, Any]) -> None:
        p["constitution_baseline"] = "AIOS核心系统宪法v3.0.md"

    _assert_caught(m, "test_policy_is_versioned_and_bound_to_constitution")


def test_case_189_module_collision_self_adjudicated_is_caught() -> None:
    """ADJ-010 §3：模块新增、合并或改义必须走一级治理变更。本文件无权自裁。

    发现冲突后正确的动作是登记并上交，而不是自己选一个赢家 ——
    后者正是造成这次冲突的行为模式。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["module_namespace_collision"]["resolution_path"] = (
            "以本政策层的 C01~C18 为准"
        )

    _assert_caught(m, "test_module_namespace_collision_is_registered_not_self_adjudicated")


def test_case_190_conflicting_module_id_left_unregistered_is_caught() -> None:
    """C15/C16/C17/C18 四处冲突必须逐个登记两方定义。
    只登记一半，另一半会在下一份文档里被当成无争议编号引用。
    """
    def m(p: dict[str, Any]) -> None:
        del p["id_namespace_registry"]["module_namespace_collision"]["conflicting_ids"]["C16"]

    _assert_caught(m, "test_module_namespace_collision_is_registered_not_self_adjudicated")


def test_case_191_merge_proposal_lets_the_referenced_side_yield_is_caught() -> None:
    """合并原则：已落库到追溯矩阵的编号有既成事实的迁移成本优势，
    未落库的一方改名，社会成本最低。让被引用的一方让位，等于制造一次全仓迁移。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["module_namespace_collision"][
            "proposed_merge_for_governance_review"
        ]["keep_from_PLAN_R4"] = {"C15": "仿真评估与纵向守卫", "C16": "端侧摄入适配"}

    _assert_caught(m, "test_collision_merge_proposal_lets_the_unreferenced_side_yield")


def test_case_192_unapproved_proposal_marked_as_baseline_is_caught() -> None:
    """凡未经一级治理变更批准的编号必须标记 PROPOSAL_NOT_BASELINE。
    摘掉标记，提案就会在下一份文档里被当成既成事实引用 ——
    编号漂移正是这样开始的：不是有人造假，是有人把提案写成了现状。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["CP1..CP4"]["status"] = "BASELINE"

    _assert_caught(m, "test_contested_namespaces_are_marked_as_proposals_not_baselines")


def test_case_193_superseded_arch_naming_revived_is_caught() -> None:
    """ADJ-012 用 P01~P10 解决了我用 ARCH-01~10 解决的同一个问题。

    被取代的命名必须显式标记并指向替代者，而不是悄悄删掉 ——
    否则读过 v1.0.0 的人会继续用 ARCH-01~10，漂移会以"两个都对"的形式延续。
    """
    def m(p: dict[str, Any]) -> None:
        arch = p["id_namespace_registry"]["namespaces"]["ARCH-01..10"]
        arch["status"] = "ACTIVE"
        arch["owner"] = "架构规划 §12"

    _assert_caught(m, "test_my_superseded_naming_is_marked_not_silently_dropped")


def test_case_194_p_series_authority_unattributed_is_caught() -> None:
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["P01..P10"]["authority"] = "本政策层自拟"

    _assert_caught(m, "test_id_namespaces_have_single_owners")


def test_case_195_adjudication_hard_gate_loosened_is_caught() -> None:
    """ADJ 追加的硬门必须全为 0（或 green），且每条注明权威出处。"""
    def m(p: dict[str, Any]) -> None:
        p["engineering_hard_gates"]["added_by_adjudication_set"][
            "reference_lock_violation"
        ]["value"] = 2

    _assert_caught(m, "test_adjudication_hard_gates_are_all_zero_and_attributed")


def test_case_196_adjudication_hard_gate_unattributed_is_caught() -> None:
    """没有权威出处的硬门，下一轮重构就会被人"看着不像必要的"删掉。"""
    def m(p: dict[str, Any]) -> None:
        p["engineering_hard_gates"]["added_by_adjudication_set"][
            "observation_byte_hash_drift"
        ]["authority"] = "工程惯例"

    _assert_caught(m, "test_adjudication_hard_gates_are_all_zero_and_attributed")


def test_case_197_inherited_hard_gate_quietly_deleted_is_caught() -> None:
    """《测试规范》§16 那六条与 ADJ 追加的十条必须分区存放。

    混在一起，下一次"精简"就会分不清哪条来自已签发的测试规范、
    哪条来自裁决集 —— 而两者的变更门槛完全不同。
    """
    def m(p: dict[str, Any]) -> None:
        del p["engineering_hard_gates"]["inherited_from_test_spec"][
            "future_info_or_hidden_truth_leak"
        ]

    _assert_caught(m, "test_engineering_hard_gates_are_all_zero")


def test_case_198_scenario_range_reverted_to_v40_is_caught() -> None:
    """ADJ 裁决集注册了 V31~V45。退回到 V01~V40，
    旧 M4-004 §G"V01~V30 覆盖"那类悬空引用就会重新出现。
    """
    def m(p: dict[str, Any]) -> None:
        ns = p["id_namespace_registry"]["namespaces"]
        ns["V01..V40"] = ns.pop("V01..V45")

    _assert_caught(m, "test_scenario_namespace_covers_the_adjudication_registered_range")


def test_case_199_deep_water_protection_note_removed_is_caught() -> None:
    """ADJ 附件 C：ADJ-001 与 ADJ-004 属深水区裁决，再变更须重走全量 G0 合议，
    不接受"顺手改一句"。摘掉这条标注，最高级裁决就会被当成普通参数改。
    """
    def m(p: dict[str, Any]) -> None:
        p["id_namespace_registry"]["namespaces"]["ADJ-001..012"]["note"] = "裁决集编号"

    _assert_caught(m, "test_deep_water_adjudications_require_full_g0_reconsent")


def test_case_200_adjudication_set_file_missing_is_caught() -> None:
    """引用一份不存在的法律，是最彻底的假 PASS。"""
    original = gate.ADJ_SET_PATH
    try:
        gate.ADJ_SET_PATH = original.parent / "does_not_exist.md"
        try:
            gate.test_adjudication_set_file_itself_is_present()
        except AssertionError:
            pass
        else:
            raise AssertionError("裁决集文件缺失时未 fail-closed")
    finally:
        gate.ADJ_SET_PATH = original


def test_case_201_trace_matrix_missing_is_caught() -> None:
    """稳定键的权威载体缺失时必须判红，而不是"查不到就当没有要求"。"""
    original = gate.TRACE_MATRIX_PATH
    try:
        gate.TRACE_MATRIX_PATH = original.parent / "does_not_exist.csv"
        try:
            gate.load_registered_stable_keys()
        except AssertionError:
            pass
        else:
            raise AssertionError("追溯矩阵缺失时未 fail-closed")
    finally:
        gate.TRACE_MATRIX_PATH = original



# ---------------------------------------------------------------------------
# CASE-202~222：THRESH-BASE 落地后的跨工件一致性执法面
#
# 这批 case 的来源与前面几批不同：前面几批来自"法律要求什么"，
# 这批来自"我实际漂移过什么"。CASE-206 与 CASE-208 复刻的是我在同一轮里
# 亲手犯下的两次同义异名错误（change_log 字段名、learn_channel 枚举名）。
# 把自己犯过的错固化成回归用例，是唯一能保证不重犯的机制 ——
# 记忆会失效，测试不会。
# ---------------------------------------------------------------------------


def test_case_202_baseline_path_pointing_nowhere_is_caught() -> None:
    """政策层指向一份不存在的基线，等于阈值治理没有出厂基线（ADJ-008(b)）。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["factory_baseline_frozen_in"] = "governance/thresholds/nope.json"

    _assert_caught(m, "test_threshold_baseline_file_exists_and_is_hash_registered")


def test_case_203_baseline_existence_requirement_dropped_is_caught() -> None:
    """把"基线文件必须存在"关掉，政策层就退化为一句指向空气的引用。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["baseline_file_must_exist"] = False

    _assert_caught(m, "test_threshold_baseline_file_exists_and_is_hash_registered")


def test_case_204_registry_id_renamed_is_caught() -> None:
    """登记编号写错，注册表里就查无此人 —— 而查无此人与尚未登记在旧写法下是同一个结果。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["baseline_registry_id"] = "THRESH-WRONG"

    _assert_caught(m, "test_threshold_baseline_file_exists_and_is_hash_registered")


def test_case_205_hash_registration_requirement_dropped_is_caught() -> None:
    """未登记的基线可以被悄悄改掉，那它就不是"出厂基线"而是"当前配置"。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["baseline_file_must_be_hash_registered"] = False

    _assert_caught(m, "test_threshold_baseline_file_exists_and_is_hash_registered")


def test_case_206_change_log_fields_reverted_to_my_invented_names_is_caught() -> None:
    """【复刻我自己的错误 #1】prev_value → previous_value，一物两名即漂移源。

    我在 v1.1.0 初版写了 [previous_value,new_value,evidence_input_window,learning_hash]，
    而落地基线是 [param_id,prev_value,next_value,input_window,learner_hash,
    rationale,applied_at,reversible]。四个同义异名 + 四个漏项。
    """
    def m(p: dict[str, Any]) -> None:
        f = p["threshold_governance"]["change_log_fields"]
        f[f.index("prev_value")] = "previous_value"
        f[f.index("next_value")] = "new_value"

    _assert_caught(m, "test_policy_does_not_redefine_the_baseline_change_log_field_names")


def test_case_207_reversible_field_dropped_is_caught() -> None:
    """漏掉 reversible，"可回滚"就从实现约束退化为态度表态。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["change_log_fields"].remove("reversible")

    _assert_caught(m, "test_policy_does_not_redefine_the_baseline_change_log_field_names")


def test_case_208_learn_channel_enum_reintroduced_locally_is_caught() -> None:
    """【复刻我自己的错误 #2】政策层重新枚举基线拥有的词表（且我把 DUAL 写成 BIDIRECTIONAL）。

    这是纯新增键的变异：判决门不会因为多了一个键而读到错值，
    但"本地枚举"本身就是被禁止的形态 —— 故必须 allow_additive。
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["learn_channel_enum"] = ["STRICTER_ONLY", "NONE", "BIDIRECTIONAL"]

    _assert_caught(
        m,
        "test_policy_does_not_hardcode_a_vocabulary_the_baseline_owns",
        allow_additive=True,
    )


def test_case_209_vocabulary_owner_claimed_by_policy_itself_is_caught() -> None:
    """把词表所有权认领回政策层，"不得本地枚举"就失去了依据。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["learn_channel_vocabulary_owner"] = "governance/runtime_policy.json"

    _assert_caught(m, "test_policy_does_not_hardcode_a_vocabulary_the_baseline_owns")


def test_case_210_derivation_requirement_dropped_is_caught() -> None:
    """允许本地声明枚举取值，等于给下一次同义异名开了门。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["learn_channel_declared_values_must_be_derived_from_baseline"] = False

    _assert_caught(m, "test_policy_does_not_hardcode_a_vocabulary_the_baseline_owns")


def test_case_211_policy_role_promoted_to_definer_is_caught() -> None:
    """政策层一旦自称定义方而非消费方，重复定义就变得"合法"了。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["single_source_of_truth"]["policy_layer_role"] = "authoritative_definer"

    _assert_caught(m, "test_policy_does_not_redefine_the_baseline_change_log_field_names")


def test_case_212_min_field_count_raised_beyond_reality_is_caught() -> None:
    """最小字段数是个下限约束；把它抬到不可能满足，说明它在被当装饰。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["change_log_field_count_min"] = 99

    _assert_caught(m, "test_policy_does_not_redefine_the_baseline_change_log_field_names")


def test_case_213_safety_channel_relaxed_to_dual_is_caught() -> None:
    """ADJ-008(d)：人身安全参数进入双向学习通道，就是安全阈值被长期磨钝的入口。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["safety_lane_true_implies_learn_channel"] = "DUAL"

    _assert_caught(m, "test_safety_lane_parameters_are_stricter_only_with_a_declared_direction")


def test_case_214_safety_exclusion_flag_dropped_is_caught() -> None:
    """把"安全参数不进下调通道"关掉，方向单调性约束就没了声明依据。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["safety_parameters_excluded_from_learning_downward_channel"] = False

    _assert_caught(m, "test_safety_lane_parameters_are_stricter_only_with_a_declared_direction")


def test_case_215_safety_examples_reverted_to_self_invented_names_is_caught() -> None:
    """自造名字的举例无法被校验：拿 fall_detection 去基线里找，找不到，
    而"找不到"与"找错"在 .get() 语义下是同一个结果 —— 本轮踩过的坑。
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["safety_parameter_examples"] = ["fall_detection", "impact_detection"]

    _assert_caught(m, "test_safety_lane_parameters_are_stricter_only_with_a_declared_direction")


def test_case_216_heartbeat_default_pushed_outside_three_to_five_hours_is_caught() -> None:
    """出厂默认 6 小时，超出 ADJ-002 承认的 3~5 小时区间。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["heartbeat_interval_factory_default_s"] = 21600

    _assert_caught(m, "test_heartbeat_factory_default_lies_inside_the_constitutional_default_range")


def test_case_217_constitutional_range_widened_to_legitimise_anything_is_caught() -> None:
    """把 [3,5] 放宽成 [1,24]，任何默认值都"合法"了 —— 这是在改法律，不是改参数。

    这条 case 是设计出来的而不是事后补的：我先写了这个变异，发现纯算术断言抓不到
    （10800 落在 [1,24] 内，基线值也仍然相等），于是回到判决门把区间硬编码钉死。
    **变异测试的价值不在于确认守卫有效，而在于发现守卫无效。**
    """
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["heartbeat_interval_constitutional_default_range_h"] = [1, 24]

    _assert_caught(m, "test_heartbeat_factory_default_lies_inside_the_constitutional_default_range")


def test_case_218_heartbeat_default_relegalised_as_law_is_caught() -> None:
    """ADJ-002 §1：把出厂默认重新升格为每用户铁律，撞上 §80之3 的反馈自适应。"""
    def m(p: dict[str, Any]) -> None:
        p["heartbeat"]["interval_hours_is_factory_default_not_law"] = False

    _assert_caught(m, "test_heartbeat_factory_default_lies_inside_the_constitutional_default_range")


def test_case_219_enforced_by_stripped_making_assertion_prose_is_caught() -> None:
    """摘掉执法点，断言就从法律退化为散文 —— 散文不会被违反，因为它从不被执行。"""
    def m(p: dict[str, Any]) -> None:
        p["threshold_governance"]["policy_assertions_on_baseline"]["g_safety_params_are_stricter_only"]["enforced_by"] = []

    _assert_caught(m, "test_every_threshold_baseline_assertion_names_a_real_enforcing_test")


def test_case_220_enforced_by_pointing_at_nonexistent_test_is_caught() -> None:
    """接线断裂：enforced_by 指向一个不存在的判决断言。

    与回归套件的 target-existence 守卫是同一类假绿通道 ——
    判决门改名而政策层未同步，断言就指向空气。
    """
    def m(p: dict[str, Any]) -> None:
        ent = p["threshold_governance"]["policy_assertions_on_baseline"]["a_baseline_file_exists"]
        ent["enforced_by"] = ["test_this_function_does_not_exist"]

    _assert_caught(m, "test_every_threshold_baseline_assertion_names_a_real_enforcing_test")


def test_case_221_baseline_assertions_silently_pruned_is_caught() -> None:
    """把九条基线断言删到只剩两条，其余七项性质就无人看守了。"""
    def m(p: dict[str, Any]) -> None:
        pa = p["threshold_governance"]["policy_assertions_on_baseline"]
        for k in ["d_log_written_before_value_change", "e_log_replayable_from_baseline",
                  "f_every_param_declares_learn_channel", "g_safety_params_are_stricter_only",
                  "h_heartbeat_default_within_constitutional_range", "i_no_duplicate_vocabulary",
                  "c_change_protocol_present"]:
            pa.pop(k, None)

    _assert_caught(m, "test_every_threshold_baseline_assertion_names_a_real_enforcing_test")


def test_case_222_statement_field_removed_from_assertion_entry_is_caught() -> None:
    """结构化断言退化成裸字符串，就无法再被元断言逐条校验。"""
    def m(p: dict[str, Any]) -> None:
        pa = p["threshold_governance"]["policy_assertions_on_baseline"]
        pa["a_baseline_file_exists"] = "基线文件必须存在"

    _assert_caught(m, "test_every_threshold_baseline_assertion_names_a_real_enforcing_test")



# ---------------------------------------------------------------------------
# CASE-223~236：1.2.0 合并面 —— 政策层现在是运行时代码的 fail-closed 依赖
#
# 这批 case 的性质与前几批不同。此前政策层的失效模式是"法律少了一条"；
# 自 M1-019 起，retention_worker.py 的 RetentionPolicy.from_runtime_policy()
# 会真的读政策层，缺键直接抛 AssertionError —— 失效模式变成"GC Worker 起不来"。
# 政策层从规范文档变成了运行时契约，守卫等级也要跟着升。
# ---------------------------------------------------------------------------


def test_case_223_ttl_table_removed_breaks_the_worker_loader() -> None:
    """删掉 TTL 表，retention_worker 直接 fail-closed 抛错。"""
    def m(p: dict[str, Any]) -> None:
        del p["retention_policy"]["ttl_days_by_retention_class"]

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_224_revocable_class_missing_from_ttl_table() -> None:
    """TTL 表少一个可吊销类，Worker 会拒绝处置该类对象（fail-closed 拒绝私自处置）。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["ttl_days_by_retention_class"].pop("ephemeral_session")

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_225_immortal_class_given_a_ttl_is_caught() -> None:
    """给 revocation_free 写上整数 TTL = 给永存类判了死期。

    ADJ-004 的吊销权外清单（对象版本链/被引用观测/DeletionLog）永不过期，
    null 才是"永存"的机器表达。写成 365 看起来只是"保留一年"，
    实际是把永存类降级成了可吊销类 —— 而且 Worker 的 isinstance(v,int) 过滤
    会把它当成真 TTL 读进去，静默生效。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["ttl_days_by_retention_class"]["revocation_free"] = 365

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_226_session_ttl_longer_than_raw_ttl_is_caught() -> None:
    """会话级缓存活得比原始可吊销副本还久，"会话级"就名不副实了。"""
    def m(p: dict[str, Any]) -> None:
        t = p["retention_policy"]["ttl_days_by_retention_class"]
        t["ephemeral_session"] = 400

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_227_zero_ttl_means_immediate_physical_delete() -> None:
    """TTL=0 等于立即物理删除 —— 绕过两阶段墓碑，正是 C1 一票否决的行为。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["ttl_days_by_retention_class"]["revocable_raw"] = 0

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_228_cluster_retire_days_made_non_integer() -> None:
    """Worker 要求 speaker_cluster_retire_days.days 为整数，否则 fail-closed。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["speaker_cluster_retire_days"]["days"] = "半年"

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_229_quarantine_cooldown_made_non_integer() -> None:
    """隔离冷却期是 Worker 的撤销权窗口，非整数即 fail-closed。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["quarantine_cooldown_days"] = 30.5

    _assert_caught(m, "test_policy_satisfies_the_retention_worker_loader_contract")


def test_case_230_policy_version_emptied_breaks_legal_basis() -> None:
    """Worker 把 policy_version 写进每条处置记录的 legal_basis；空版本号 = 无法追溯依哪版法律处置。"""
    def m(p: dict[str, Any]) -> None:
        p["policy_version"] = ""

    _assert_caught(
        m,
        "test_policy_satisfies_the_retention_worker_loader_contract",
        "test_policy_is_versioned_and_bound_to_constitution",
    )


def test_case_231_quarantine_alias_drifts_from_canonical_field() -> None:
    """ADJ-011：一物两名各自演进，"隔离冷却期到底几天"就没有唯一答案。

    stage1_quarantine_days 与 quarantine_cooldown_days 语义相同、数值相同，
    且全仓库无代码读取前者。不擅自删除另一条工作线的字段，改为钉死相等。
    """
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["stage1_quarantine_days"]["days"] = 45

    _assert_caught(m, "test_stage1_quarantine_alias_cannot_drift_from_its_canonical_field")


def test_case_232_alias_warning_removed_is_caught() -> None:
    """摘掉别名警告，冗余字段就会被后人当成独立参数各自维护。"""
    def m(p: dict[str, Any]) -> None:
        p["retention_policy"]["stage1_quarantine_days"].pop("$alias_warning")

    _assert_caught(m, "test_stage1_quarantine_alias_cannot_drift_from_its_canonical_field")


def test_case_233_cluster_window_reference_removed_is_caught() -> None:
    """我在 ADJ-009 对齐时只写了 window=true 却没给数值 —— 没有值的窗口等于没有窗口。"""
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"].pop("activity_assessed_by_recent_use_window_value_ref")

    _assert_caught(m, "test_speaker_cluster_window_is_referenced_not_duplicated")


def test_case_234_cluster_window_reference_left_dangling_is_caught() -> None:
    """引用指向不存在的路径 = 悬空引用，与没有引用同样无法实现。"""
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"][
            "activity_assessed_by_recent_use_window_value_ref"
        ] = "retention_policy.speaker_cluster_retire_days.weeks"

    _assert_caught(m, "test_speaker_cluster_window_is_referenced_not_duplicated")


def test_case_235_cluster_window_value_copied_instead_of_referenced_is_caught() -> None:
    """复制数值即制造第二个真相来源：两个 180 迟早变成 180 和 210。"""
    def m(p: dict[str, Any]) -> None:
        p["speaker_cluster_lifecycle"]["retirement_window_days"] = 180

    _assert_caught(
        m,
        "test_speaker_cluster_window_is_referenced_not_duplicated",
        allow_additive=True,
    )


def test_case_236_version_collision_reintroduced_is_caught() -> None:
    """两条工作线各自产出一个"1.1.0"（内容不同、版本号相同）。

    合并后必须是 1.2.0：任何一方都不"赢得"1.1.0 这个号。
    退回去就等于让一个版本号重新指代两份不同内容 —— 注册表要消灭的正是这个。
    """
    def m(p: dict[str, Any]) -> None:
        p["policy_version"] = "1.1.0"

    _assert_caught(m, "test_policy_version_matches_its_live_registry_row")


def test_case_237_policy_version_ahead_of_registry_live_row_is_caught() -> None:
    """改了政策却没追加版本行：政策层自称的版本号比注册表活行更新。

    与 CASE-236 同一条不变量的另一个方向 —— 两份"权威"各说各话，
    谁都说不清线上跑的到底是哪一版法律。
    """
    def m(p: dict[str, Any]) -> None:
        p["policy_version"] = "9.9.9"

    _assert_caught(m, "test_policy_version_matches_its_live_registry_row")


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
