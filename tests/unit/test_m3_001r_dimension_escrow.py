"""M3-001R · 维度创建权 Token 配额托管与 O(D²) 刹车 —— 门禁测试

四大硬门禁的可判定形式（政策 ``dimension_escrow`` + ``token_budget`` 为唯一权威）：

1. 创建权必须预算托管 —— CANDIDATE→TRIAL 前先扣配额；池不足即按法定动作
   ``reject_creation_with_BUDGET_EXHAUSTED`` 拒绝，错误码是法定
   ``ErrorCode.BUDGET_EXHAUSTED``（可跨协议边界分支），不是本地 ``RuntimeError``。
2. DORMANT 归还配额（反棘轮）—— 承重不变量是**守恒式**
   ``自由 + Σ未归还托管 == 池总量``，每一次变更后都成立。它比"归还会发生"强得多：
   同时排除重复归还（凭空造配额）与漏归还（配额泄漏），两者都会让棘轮重新长出来。
3. 低频不等于无价值，绝不删除 —— 用三种方式钉死：AST 断言不存在任何
   delete/remove/erase/purge/drop/forget/evict 类公开方法；行为断言跑完整生命周期后
   每个曾注册的 id 仍可查且历史完整；契约断言法定枚举里没有 DELETED 成员。
4. 共振对与跨域突触上限把 O(D²) 刹成 O(1) —— 70 个维度共 2415 个可能对，
   实际接受数必须**恰好等于**法定上限 60；扇入/扇出各 ≤ 8。

测试一律从政策文件读取上限与配额池，因此政策改动时覆盖面自动跟随。
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios_core.contracts.enums import DimensionLifecycle, ErrorCode
from aios_core.contracts.models import DimensionDefinition
from aios_core.dimensions import dimension_escrow as de
from aios_core.dimensions.dimension_escrow import (
    PROPOSED_DIMENSION_TRANSITIONS,
    BudgetExhaustedError,
    DimensionDeletionAttemptError,
    DimensionEscrow,
    DimensionEscrowError,
    EscrowAccount,
    IllegalLifecycleTransitionError,
    ResonanceCapExceededError,
    SynapseFanCapExceededError,
    TransitionProposal,
    allowed_dimension_transitions,
    load_dimension_escrow_policy,
    load_runtime_policy,
    load_token_budget_policy,
    validate_policy_section,
)

MODULE_SOURCE = Path(de.__file__).read_text(encoding="utf-8")
ROOT = load_runtime_policy()
ESC = ROOT["dimension_escrow"]
TB = ROOT["token_budget"]
POOL = TB["subsystems"]["dimension"]["monthly_cap"]
RESONANCE_CAP = ESC["resonance_pair_cap_per_window"]
FANIN_MAX = ESC["cross_domain_synapse_fanin_max"]
FANOUT_MAX = ESC["cross_domain_synapse_fanout_max"]

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PER_CANDIDATE = 3000  # 出自政策 basis 散文「10 候选/月 × 3000」，见下方算术锚测试


def dim(object_id: str, lifecycle=DimensionLifecycle.CANDIDATE) -> DimensionDefinition:
    """构造法定维度记录。

    **必须显式钉住 ``recorded_at``**：``WorldObject.recorded_at`` 默认取真实墙钟
    ``utc_now()``，而契约校验要求 ``recorded_at >= learned_at``。若不钉住，本测试
    会在 ``NOW``（12:00 UTC）之前运行失败、之后运行通过 —— 结构性 flaky，
    正是 ``degradation_invariants.deterministic_seed_required`` 要排除的东西。
    """
    return DimensionDefinition(
        object_id=object_id,
        subject_id="user-1",
        learned_at=NOW,
        recorded_at=NOW,
        created_by="aios",
        name=f"维度 {object_id}",
        description="测试维度",
        data_shape="scalar",
        lifecycle=lifecycle,
    )


@pytest.fixture
def escrow() -> DimensionEscrow:
    return DimensionEscrow()


def fill_pool(escrow, count: int, *, quota: int = PER_CANDIDATE, activate: bool = False):
    """注册并托管 count 个维度，返回 id 列表。"""
    ids = []
    for i in range(count):
        oid = f"d{i}"
        escrow.register_candidate(dim(oid), now=NOW)
        escrow.promote_to_trial(oid, monthly_token_quota=quota, now=NOW)
        if activate:
            escrow.promote_to_active(oid, now=NOW)
        ids.append(oid)
    return ids


# ---------------------------------------------------------------------------
# A · 政策绑定：引用而非复制
# ---------------------------------------------------------------------------


class TestPolicyBinding:
    def test_policy_file_is_the_single_authority(self):
        assert de._POLICY_PATH.exists()
        assert de._POLICY_PATH.parent.name == "governance"

    def test_pool_comes_from_the_legal_dimension_subsystem(self, escrow):
        assert escrow.pool_tokens == POOL == 30000
        assert TB["subsystems"]["dimension"]["monthly_cap"] == POOL

    def test_token_budget_closes_to_zero_base(self):
        """政策 ``$closure_note``：12 个子系统之和必须精确等于 monthly_total_cap。

        维度托管花的每一个 token 都是从用户月度总封套里真实扣走的，不是凭空多出来
        的一笔 —— 这条闭合式就是那句话的可执行形式。
        """
        total = sum(v["monthly_cap"] for v in TB["subsystems"].values())
        assert total == TB["monthly_total_cap"] == 2554000
        assert len(TB["subsystems"]) == 12

    def test_per_candidate_arithmetic_closes_on_the_policy_basis(self):
        """政策 basis 散文「10 候选/月 × 3000（§76 预算托管准入）」的算术锚。

        散文不进生产代码解析（与 M2-001 对心跳 240 × 750 的处置同一手法），
        但它证明配额池的大小与准入节奏是**互相锁定**的：改任一个都会破闭合。
        """
        assert 10 * PER_CANDIDATE == POOL
        assert "10 候选/月 × 3000" in TB["subsystems"]["dimension"]["basis"]

    def test_caps_are_read_from_policy(self, escrow):
        assert escrow.resonance_cap == RESONANCE_CAP == 60
        assert escrow.fanin_max == FANIN_MAX == 8
        assert escrow.fanout_max == FANOUT_MAX == 8

    def test_no_legal_number_is_copied_into_the_module_code(self):
        """**用 AST 查代码里的数字字面量，不用字符串匹配。**

        docstring 里引用法定数字（说明政策写了什么）是正当且必要的；字符串匹配会把
        它误判成硬编码。这是本轮第四次踩同一陷阱（前三次：M2-005R 的
        ``_TASK_TRANSITIONS``、M2-001 的 ``meter.charge(`` 与 ``class WakePriority``），
        所以判据一律走语法树 —— AST 天然把文档字符串与代码分开。
        """
        tree = ast.parse(MODULE_SOURCE)
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
        }
        legal_numbers = {
            POOL, TB["monthly_total_cap"], RESONANCE_CAP, FANIN_MAX, FANOUT_MAX, PER_CANDIDATE,
        }
        assert not (literals & legal_numbers), (
            f"代码里硬编码了法定数字 {sorted(literals & legal_numbers)}；"
            "一律必须从政策读取"
        )
        # 反向自检：判据本身有效（确实数得出字面量）
        assert literals, "AST 判据失效：应当数得出数字字面量"

    @pytest.mark.parametrize(
        "key",
        [
            "candidate_to_trial_requires_preallocated_monthly_token_quota",
            "dormant_returns_quota",
            "low_frequency_dimension_must_not_be_deleted",
        ],
    )
    def test_injected_section_with_a_flipped_law_is_refused(self, key):
        """注入路径必须享受与文件路径**完全相同**的校验（M2-005R 栽过的真 bug）。"""
        drifted = dict(ESC)
        drifted[key] = False
        with pytest.raises(DimensionEscrowError, match="法定值"):
            load_dimension_escrow_policy({"dimension_escrow": drifted})
        with pytest.raises(DimensionEscrowError, match="法定值"):
            DimensionEscrow(escrow_policy=drifted)

    def test_injected_root_policy_gets_the_same_validation(self):
        drifted_root = dict(ROOT)
        section = dict(ESC)
        section["dormant_returns_quota"] = False
        drifted_root["dimension_escrow"] = section
        with pytest.raises(DimensionEscrowError, match="法定值"):
            DimensionEscrow(policy=drifted_root)

    def test_a_different_insufficient_quota_action_is_refused(self):
        drifted = dict(ESC)
        drifted["insufficient_quota_action"] = "warn_and_continue"
        with pytest.raises(DimensionEscrowError, match="reject_creation_with_BUDGET_EXHAUSTED"):
            DimensionEscrow(escrow_policy=drifted)

    @pytest.mark.parametrize(
        "key",
        ["resonance_pair_cap_per_window", "cross_domain_synapse_fanin_max",
         "cross_domain_synapse_fanout_max"],
    )
    @pytest.mark.parametrize("bad", [0, -1, "8", None])
    def test_non_positive_or_non_integer_caps_are_refused(self, key, bad):
        drifted = dict(ESC)
        drifted[key] = bad
        with pytest.raises(DimensionEscrowError):
            DimensionEscrow(escrow_policy=drifted)

    @pytest.mark.parametrize(
        "key",
        ["insufficient_quota_action", "resonance_pair_cap_per_window",
         "cross_domain_synapse_fanin_max", "cross_domain_synapse_fanout_max"],
    )
    def test_missing_field_is_refused(self, key):
        drifted = {k: v for k, v in ESC.items() if k != key}
        with pytest.raises(DimensionEscrowError, match="缺少法定字段"):
            DimensionEscrow(escrow_policy=drifted)

    def test_a_token_budget_without_the_dimension_subsystem_is_refused(self):
        drifted = dict(TB)
        drifted["subsystems"] = {
            k: v for k, v in TB["subsystems"].items() if k != "dimension"
        }
        with pytest.raises(DimensionEscrowError, match="没有法定来源"):
            DimensionEscrow(token_budget_policy=drifted)

    def test_pool_larger_than_the_monthly_envelope_is_refused(self):
        with pytest.raises(DimensionEscrowError, match="零基闭合"):
            DimensionEscrow(pool_tokens=TB["monthly_total_cap"] + 1)

    def test_negative_pool_is_refused(self):
        with pytest.raises(DimensionEscrowError, match="不得为负"):
            DimensionEscrow(pool_tokens=-1)

    def test_an_explicit_smaller_pool_is_allowed(self):
        escrow = DimensionEscrow(pool_tokens=9000)
        assert escrow.pool_tokens == 9000
        ids = fill_pool(escrow, 3)
        assert escrow.audit()["free_tokens"] == 0
        escrow.register_candidate(dim("d9"), now=NOW)
        with pytest.raises(BudgetExhaustedError):
            escrow.promote_to_trial("d9", monthly_token_quota=PER_CANDIDATE, now=NOW)

    def test_validate_policy_section_rejects_a_non_object(self):
        with pytest.raises(DimensionEscrowError, match="必须是对象"):
            validate_policy_section("dimension_escrow", [], required_fields=())

    def test_missing_policy_file_is_reported_not_swallowed(self, monkeypatch):
        monkeypatch.setattr(de, "_POLICY_PATH", Path("/nonexistent/runtime_policy.json"))
        with pytest.raises(DimensionEscrowError, match="找不到法定政策文件"):
            de.load_runtime_policy()


# ---------------------------------------------------------------------------
# B · 门禁 1：创建权必须预算托管
# ---------------------------------------------------------------------------


class TestGate1CreationRightIsEscrowed:
    def test_policy_anchor(self):
        assert ESC["candidate_to_trial_requires_preallocated_monthly_token_quota"] is True
        assert ESC["insufficient_quota_action"] == "reject_creation_with_BUDGET_EXHAUSTED"

    def test_promotion_escrows_before_it_promotes(self, escrow):
        ids = fill_pool(escrow, 1)
        assert escrow.lifecycle_of(ids[0]) is DimensionLifecycle.TRIAL
        assert escrow.quota_of(ids[0]) == PER_CANDIDATE
        assert escrow.audit()["free_tokens"] == POOL - PER_CANDIDATE

    def test_registering_a_candidate_does_not_escrow(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        assert escrow.quota_of("d0") == 0
        assert escrow.audit()["free_tokens"] == POOL

    def test_the_eleventh_candidate_is_rejected_with_the_legal_code(self, escrow):
        """政策 basis 的 10 候选/月 × 3000 恰好耗尽 30000 的池 —— 上限必须真的绑定。"""
        fill_pool(escrow, 10)
        assert escrow.audit()["free_tokens"] == 0
        escrow.register_candidate(dim("d10"), now=NOW)
        with pytest.raises(BudgetExhaustedError) as info:
            escrow.promote_to_trial("d10", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert info.value.code is ErrorCode.BUDGET_EXHAUSTED
        assert info.value.context["action"] == ESC["insufficient_quota_action"]
        assert info.value.context["requested"] == PER_CANDIDATE
        assert info.value.context["free"] == 0

    def test_the_legal_error_reaches_the_protocol_boundary(self, escrow):
        """用 ``AIOSProtocolError`` 而不是本地 ``RuntimeError``：调用方可以按码分支。

        本地异常到不了协议边界，调用方只能去匹配错误文案 —— 那不是接口，是猜谜。
        """
        from aios_core.errors import AIOSProtocolError

        fill_pool(escrow, 10)
        escrow.register_candidate(dim("d10"), now=NOW)
        with pytest.raises(AIOSProtocolError) as info:
            escrow.promote_to_trial("d10", monthly_token_quota=1, now=NOW)
        assert info.value.code is ErrorCode.BUDGET_EXHAUSTED
        response = info.value.to_response()
        assert response.code is ErrorCode.BUDGET_EXHAUSTED

    def test_a_rejected_promotion_leaves_the_state_untouched(self, escrow):
        """失败必须是**全或无**：不得出现"已晋升但无预算"的维度。"""
        fill_pool(escrow, 10)
        escrow.register_candidate(dim("d10"), now=NOW)
        with pytest.raises(BudgetExhaustedError):
            escrow.promote_to_trial("d10", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.lifecycle_of("d10") is DimensionLifecycle.CANDIDATE
        assert escrow.quota_of("d10") == 0
        assert escrow.audit()["conservation_holds"] is True

    def test_rejection_is_logged_not_silently_dropped(self, escrow):
        fill_pool(escrow, 10)
        escrow.register_candidate(dim("d10"), now=NOW)
        with pytest.raises(BudgetExhaustedError):
            escrow.promote_to_trial("d10", monthly_token_quota=PER_CANDIDATE, now=NOW)
        log = escrow.audit()["rejection_log"]
        assert len(log) == 1
        assert log[0]["dimension_id"] == "d10"
        assert log[0]["action"] == ESC["insufficient_quota_action"]

    def test_a_partial_quota_that_does_not_fit_is_refused(self, escrow):
        fill_pool(escrow, 9)  # 用掉 27000，剩 3000
        escrow.register_candidate(dim("d9"), now=NOW)
        with pytest.raises(BudgetExhaustedError):
            escrow.promote_to_trial("d9", monthly_token_quota=PER_CANDIDATE + 1, now=NOW)
        assert escrow.audit()["free_tokens"] == PER_CANDIDATE

    def test_non_positive_quota_is_refused(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        with pytest.raises(DimensionEscrowError, match="必须为正"):
            escrow.promote_to_trial("d0", monthly_token_quota=0, now=NOW)

    def test_double_escrow_is_refused_before_any_state_changes(self, escrow):
        """重复托管会让守恒式失去意义：旧额度既没归还也没计入新账户。

        必须在改动任何状态**之前**拦住，而不是让 ``_assert_conservation`` 事后抛一个
        看不出成因的错。
        """
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        with pytest.raises(DimensionEscrowError, match="重复托管"):
            escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.audit()["conservation_holds"] is True
        assert escrow.quota_of("d0") == PER_CANDIDATE

    def test_registering_a_non_candidate_definition_is_refused(self, escrow):
        with pytest.raises(DimensionEscrowError, match="入册时 lifecycle"):
            escrow.register_candidate(
                dim("d0", lifecycle=DimensionLifecycle.ACTIVE), now=NOW
            )

    def test_duplicate_registration_is_refused_including_terminal_states(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.reject("d0", now=NOW, reason="试用期未通过")
        with pytest.raises(DimensionEscrowError, match="终态维度禁复活"):
            escrow.register_candidate(dim("d0"), now=NOW)

    def test_unknown_dimension_is_refused(self, escrow):
        with pytest.raises(DimensionEscrowError, match="不在册"):
            escrow.promote_to_trial("ghost", monthly_token_quota=100, now=NOW)
        with pytest.raises(DimensionEscrowError, match="不在册"):
            escrow.lifecycle_of("ghost")


# ---------------------------------------------------------------------------
# C · 门禁 2：DORMANT 归还配额（反棘轮）
# ---------------------------------------------------------------------------


class TestGate2DormantReturnsQuota:
    def test_policy_anchor_and_the_ratchet_diagnosis(self):
        assert ESC["dormant_returns_quota"] is True
        # 政策 evidence 行点名的病灶：配额只出不进 = 棘轮
        assert "棘轮" in ESC["evidence"]
        assert "O(D²)" in ESC["evidence"]

    def test_dormant_returns_the_escrowed_quota(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        escrow.mark_low_activity("d0", now=NOW)
        returned = escrow.send_dormant("d0", now=NOW)
        assert returned == PER_CANDIDATE
        assert escrow.audit()["free_tokens"] == POOL
        assert escrow.quota_of("d0") == 0

    def test_conservation_holds_after_every_single_mutation(self, escrow):
        """承重不变量：自由 + Σ未归还托管 == 池总量，**每一次**变更后都成立。"""
        ops = 0
        ids = fill_pool(escrow, 6)
        ops += 1
        assert escrow.audit()["conservation_holds"]
        for oid in ids[:3]:
            escrow.promote_to_active(oid, now=NOW)
            assert escrow.audit()["conservation_holds"]
            ops += 1
        for oid in ids[:2]:
            escrow.mark_low_activity(oid, now=NOW)
            escrow.send_dormant(oid, now=NOW)
            assert escrow.audit()["conservation_holds"]
            ops += 2
        # 已 ACTIVE 的维度退役走 DORMANT，不是 REJECTED（后者属试用期未通过）
        escrow.send_dormant(ids[2], now=NOW)
        assert escrow.audit()["conservation_holds"]
        escrow.register_candidate(dim("dx"), now=NOW)
        escrow.promote_to_trial("dx", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.audit()["conservation_holds"]
        escrow.merge_into(ids[3], ids[4], now=NOW)
        assert escrow.audit()["conservation_holds"]
        assert ops > 0

    def test_returning_quota_twice_does_not_conjure_tokens(self, escrow):
        """**重复归还**是守恒式的另一半：它会凭空造出配额，把棘轮反向击穿。"""
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        first = escrow.send_dormant("d0", now=NOW)
        assert first == PER_CANDIDATE
        assert escrow.audit()["free_tokens"] == POOL
        # 已归还的账户再归还必须是幂等的 0，而不是再吐一次
        assert escrow._return_quota("d0", now=NOW, reason="again") == 0
        assert escrow.audit()["free_tokens"] == POOL
        assert escrow.audit()["conservation_holds"] is True

    def test_the_ratchet_is_actually_broken(self, escrow):
        """反棘轮的正面证明：池被耗尽 → 归还 → 新维度又能进。

        只禁删不归还就是纯棘轮（池永远只减不增，第 11 个维度永远进不来）；
        这条测试就是"归还路径存在且有效"的可执行形式。
        """
        fill_pool(escrow, 10)
        assert escrow.audit()["free_tokens"] == 0
        escrow.register_candidate(dim("blocked"), now=NOW)
        with pytest.raises(BudgetExhaustedError):
            escrow.promote_to_trial("blocked", monthly_token_quota=PER_CANDIDATE, now=NOW)

        escrow.promote_to_active("d0", now=NOW)
        escrow.mark_low_activity("d0", now=NOW)
        escrow.send_dormant("d0", now=NOW)

        escrow.promote_to_trial("blocked", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.lifecycle_of("blocked") is DimensionLifecycle.TRIAL
        assert escrow.audit()["free_tokens"] == 0
        assert escrow.audit()["conservation_holds"] is True

    def test_reactivation_must_re_escrow(self, escrow):
        """复活不是免费的：DORMANT → REACTIVATED 必须重新托管。"""
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        escrow.send_dormant("d0", now=NOW)
        assert escrow.audit()["free_tokens"] == POOL
        escrow.reactivate("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.lifecycle_of("d0") is DimensionLifecycle.REACTIVATED
        assert escrow.quota_of("d0") == PER_CANDIDATE
        assert escrow.audit()["free_tokens"] == POOL - PER_CANDIDATE

    def test_a_failed_reactivation_rolls_the_state_back_to_dormant(self, escrow):
        """不得留下"已复活但无预算"的维度 —— 那比不复活更糟。"""
        fill_pool(escrow, 10)
        escrow.promote_to_active("d0", now=NOW)
        escrow.send_dormant("d0", now=NOW)
        escrow.register_candidate(dim("d10"), now=NOW)
        escrow.promote_to_trial("d10", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.audit()["free_tokens"] == 0
        with pytest.raises(BudgetExhaustedError):
            escrow.reactivate("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.lifecycle_of("d0") is DimensionLifecycle.DORMANT
        assert escrow.quota_of("d0") == 0
        assert escrow.audit()["conservation_holds"] is True

    def test_rejection_returns_the_quota_too(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        returned = escrow.reject("d0", now=NOW, reason="准确率不足")
        assert returned == PER_CANDIDATE
        assert escrow.audit()["free_tokens"] == POOL

    def test_merge_returns_the_quota(self, escrow):
        """§76 维度不能无限爆炸的正面手段：合并即释放预算。"""
        fill_pool(escrow, 2)
        returned = escrow.merge_into("d0", "d1", now=NOW)
        assert returned == PER_CANDIDATE
        assert escrow.lifecycle_of("d0") is DimensionLifecycle.MERGED
        assert escrow.audit()["free_tokens"] == POOL - PER_CANDIDATE

    def test_a_failed_promotion_rolls_the_escrow_back(self, escrow):
        """跃迁失败必须退回刚托管的配额，否则守恒式虽成立、额度却被死锁。"""
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        # TRIAL → LOW_ACTIVITY 不在提案表内（低频降级只适用于已活跃维度）
        with pytest.raises(IllegalLifecycleTransitionError):
            escrow.mark_low_activity("d0", now=NOW)
        assert escrow.audit()["conservation_holds"] is True
        assert escrow.quota_of("d0") == PER_CANDIDATE

    def test_quota_returning_events_are_counted(self, escrow):
        fill_pool(escrow, 3)
        escrow.promote_to_active("d0", now=NOW)
        escrow.send_dormant("d0", now=NOW)
        escrow.reject("d1", now=NOW)
        assert escrow.audit()["quota_returning_events"] == 2


# ---------------------------------------------------------------------------
# D · 门禁 3：低频不等于无价值，绝不删除
# ---------------------------------------------------------------------------


class TestGate3LowFrequencyIsNeverDeleted:
    FORBIDDEN_VERBS = (
        "delete", "remove", "erase", "purge", "drop", "forget",
        "evict", "discard", "clear", "truncate", "prune", "destroy",
    )

    def test_policy_anchor(self):
        assert ESC["low_frequency_dimension_must_not_be_deleted"] is True
        assert "低频不等于无价值" in ESC["constitution_ref"] or "§75" in ESC["constitution_ref"]

    def test_the_legal_enum_has_no_deletion_state(self):
        """法定 ``DimensionLifecycle`` 里没有 DELETED / ARCHIVED / EXPIRED。

        "留档但不再花钱"的法定形态是 LOW_ACTIVITY → DORMANT，不是另造一个终态。
        """
        members = {m.name for m in DimensionLifecycle}
        assert members == {
            "CANDIDATE", "TRIAL", "ACTIVE", "LOW_ACTIVITY", "DORMANT",
            "MERGED", "SPLIT", "REVISED", "REJECTED", "REACTIVATED",
        }
        assert not (members & {"DELETED", "ARCHIVED", "EXPIRED", "REMOVED", "TOMBSTONE"})

    def test_no_public_method_can_delete_a_dimension(self):
        """AST 断言：不存在任何删除语义的**公开**方法。

        用 AST 而不是字符串匹配 —— docstring 里正当提及 delete/删除 是必要的
        （说明这条门禁），字符串匹配会把它误判成 API。这是本轮第三次踩同一陷阱
        （前两次：M2-005R 的 _TASK_TRANSITIONS、M2-001 的 meter.charge 与
        class WakePriority），所以判据一律走语法树。
        """
        tree = ast.parse(MODULE_SOURCE)
        public = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
        ]
        assert public, "AST 判据失效：应当数得出公开方法"
        offenders = [
            name
            for name in public
            if any(verb in name.lower() for verb in self.FORBIDDEN_VERBS)
        ]
        assert offenders == [], f"出现删除语义的公开方法：{offenders}"

    def test_internal_stores_never_shrink(self, escrow):
        """行为断言：跑完整生命周期后，三个内部存储的键数只增不减。"""
        ids = fill_pool(escrow, 5, activate=True)
        peak = (len(escrow._records), len(escrow._accounts), len(escrow._history))
        escrow.mark_low_activity(ids[0], now=NOW)
        escrow.send_dormant(ids[0], now=NOW)
        escrow.send_dormant(ids[1], now=NOW)   # ACTIVE → DORMANT（退役而非拒绝）
        escrow.merge_into(ids[2], ids[3], now=NOW)
        after = (len(escrow._records), len(escrow._accounts), len(escrow._history))
        assert after == peak, "内部存储缩水了 —— 有维度被删除"
        assert after[0] == 5

    def test_every_ever_registered_id_stays_queryable(self, escrow):
        ids = fill_pool(escrow, 4, activate=True)
        escrow.send_dormant(ids[0], now=NOW)
        escrow.send_dormant(ids[1], now=NOW)
        escrow.merge_into(ids[2], ids[3], now=NOW)
        assert set(escrow.registered_ids()) == set(ids)
        for oid in ids:
            assert isinstance(escrow.record_of(oid), DimensionDefinition)
            assert isinstance(escrow.lifecycle_of(oid), DimensionLifecycle)
            assert escrow.history_of(oid), "变迁史不得为空"

    def test_a_dormant_dimension_keeps_its_full_history(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        escrow.mark_low_activity("d0", now=NOW)
        escrow.send_dormant("d0", now=NOW)
        states = [h["to"] for h in escrow.history_of("d0")]
        assert states == [
            "candidate", "trial", "active", "low_activity", "dormant"
        ]
        assert escrow.quota_of("d0") == 0, "休眠维度不再花钱"
        assert escrow.record_of("d0").name == "维度 d0", "记录内容仍在"

    def test_a_low_frequency_dimension_degrades_instead_of_vanishing(self, escrow):
        """低频的正确归宿是 LOW_ACTIVITY → DORMANT（留档 + 归还配额）。

        只禁删不归还 = 纯棘轮；只归还可删 = 丢了 §75。两者必须同时成立。
        """
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        escrow.mark_low_activity("d0", now=NOW)
        assert escrow.lifecycle_of("d0") is DimensionLifecycle.LOW_ACTIVITY
        assert "d0" in escrow.registered_ids()
        escrow.send_dormant("d0", now=NOW)
        assert escrow.lifecycle_of("d0") is DimensionLifecycle.DORMANT
        assert "d0" in escrow.registered_ids()

    def test_low_activity_can_warm_back_up(self, escrow):
        """§75 的另一半：低频不等于无价值，回暖即复活跃。"""
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        escrow.mark_low_activity("d0", now=NOW)
        escrow._transition("d0", DimensionLifecycle.ACTIVE, now=NOW)
        assert escrow.lifecycle_of("d0") is DimensionLifecycle.ACTIVE

    def test_deletion_attempt_error_exists_and_is_typed(self):
        err = DimensionDeletionAttemptError("不许删")
        assert err.code is ErrorCode.INVALID_ARGUMENT
        assert isinstance(err, DimensionEscrowError)

    def test_an_active_dimension_retires_via_dormancy_not_rejection(self, escrow):
        """REJECTED 属"试用期未通过"；已 ACTIVE 的维度退役走 LOW_ACTIVITY/DORMANT/MERGED。

        这条区分不是洁癖：把活跃维度标成 REJECTED 会抹掉"它曾经有效过"这一事实，
        而 §75「低频不等于无价值」正建立在这段历史上。三条失败测试就是踩了它，
        所以把它沉淀成规格而不是只改测试。
        """
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.promote_to_active("d0", now=NOW)
        assert DimensionLifecycle.REJECTED not in allowed_dimension_transitions(
            DimensionLifecycle.ACTIVE
        )
        with pytest.raises(IllegalLifecycleTransitionError):
            escrow.reject("d0", now=NOW)
        # 试用期维度则可以 REJECTED
        escrow.register_candidate(dim("d1"), now=NOW)
        escrow.promote_to_trial("d1", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.reject("d1", now=NOW) == PER_CANDIDATE
        assert escrow.lifecycle_of("d1") is DimensionLifecycle.REJECTED

    def test_terminal_states_have_no_outgoing_edges_but_keep_records(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        escrow.reject("d0", now=NOW)
        assert allowed_dimension_transitions(DimensionLifecycle.REJECTED) == frozenset()
        with pytest.raises(IllegalLifecycleTransitionError):
            escrow.promote_to_active("d0", now=NOW)
        assert escrow.record_of("d0") is not None


# ---------------------------------------------------------------------------
# E · 门禁 4：共振对与突触上限把 O(D²) 刹成 O(1)
# ---------------------------------------------------------------------------


class TestGate4QuadraticBrake:
    def test_policy_anchor(self):
        assert RESONANCE_CAP == 60
        assert FANIN_MAX == 8 and FANOUT_MAX == 8

    def test_seventy_dimensions_yield_exactly_the_cap(self, escrow):
        """70 个维度共 D(D-1)/2 = 2415 个可能对，接受数必须**恰好等于** 60。

        这条断言是整个门禁的要点：可能的对数随 D 平方增长，而接受数是常数。
        """
        count = 70
        ids = [f"x{i}" for i in range(count)]
        for oid in ids:
            escrow.register_candidate(dim(oid), now=NOW)
        assert count * (count - 1) // 2 == 2415
        accepted = 0
        rejected = 0
        for i in range(count):
            for j in range(i + 1, count):
                try:
                    escrow.add_resonance_pair(ids[i], ids[j], window_id="w1")
                    accepted += 1
                except ResonanceCapExceededError:
                    rejected += 1
        assert accepted == RESONANCE_CAP
        assert rejected == 2415 - RESONANCE_CAP
        assert escrow.resonance_pairs_in("w1") == RESONANCE_CAP

    @pytest.mark.parametrize("count,expected", [(11, 55), (12, 60), (13, 60), (40, 60)])
    def test_the_cap_binds_regardless_of_population(self, escrow, count, expected):
        """D=11 时 55 对全部放行（未触顶）；D≥12 起一律截断在 60。"""
        ids = [f"y{i}" for i in range(count)]
        for oid in ids:
            escrow.register_candidate(dim(oid), now=NOW)
        accepted = 0
        for i in range(count):
            for j in range(i + 1, count):
                try:
                    escrow.add_resonance_pair(ids[i], ids[j], window_id="w")
                    accepted += 1
                except ResonanceCapExceededError:
                    pass
        assert accepted == expected

    def test_a_new_window_resets_the_budget(self, escrow):
        ids = fill_pool(escrow, 3)
        for i in range(RESONANCE_CAP):
            escrow.add_resonance_pair(ids[0], ids[1], window_id="w1")
        assert escrow.resonance_pairs_in("w1") == 1, "同一对重复登记不得占第二个名额"
        escrow.add_resonance_pair(ids[0], ids[1], window_id="w2")
        assert escrow.resonance_pairs_in("w2") == 1
        assert escrow.resonance_pairs_in("w1") == 1

    def test_pairs_are_unordered(self, escrow):
        """(a,b) 与 (b,a) 是同一对。按有序处理会让上限被无声翻倍，
        而 O(D²) 的平方项恰恰来自无序对数 D(D-1)/2。
        """
        ids = fill_pool(escrow, 2)
        escrow.add_resonance_pair(ids[0], ids[1], window_id="w")
        escrow.add_resonance_pair(ids[1], ids[0], window_id="w")
        assert escrow.resonance_pairs_in("w") == 1

    def test_self_resonance_is_refused(self, escrow):
        ids = fill_pool(escrow, 1)
        with pytest.raises(DimensionEscrowError, match="自身共振"):
            escrow.add_resonance_pair(ids[0], ids[0], window_id="w")

    def test_resonance_with_an_unregistered_dimension_is_refused(self, escrow):
        ids = fill_pool(escrow, 1)
        with pytest.raises(DimensionEscrowError, match="不在册"):
            escrow.add_resonance_pair(ids[0], "ghost", window_id="w")

    def test_resonance_rejections_are_logged(self, escrow):
        count = 13
        ids = [f"z{i}" for i in range(count)]
        for oid in ids:
            escrow.register_candidate(dim(oid), now=NOW)
        for i in range(count):
            for j in range(i + 1, count):
                try:
                    escrow.add_resonance_pair(ids[i], ids[j], window_id="w")
                except ResonanceCapExceededError:
                    pass
        log = escrow.audit()["rejection_log"]
        assert len(log) == 78 - RESONANCE_CAP
        assert all(entry["cap"] == RESONANCE_CAP for entry in log)

    def test_fanin_is_capped(self, escrow):
        ids = [f"f{i}" for i in range(FANIN_MAX + 2)]
        for oid in ids:
            escrow.register_candidate(dim(oid), now=NOW)
        hub = ids[-1]
        for i in range(FANIN_MAX):
            escrow.add_synapse(ids[i], hub)
        assert escrow.fanin_of(hub) == FANIN_MAX
        with pytest.raises(SynapseFanCapExceededError) as info:
            escrow.add_synapse(ids[FANIN_MAX], hub)
        assert info.value.context["cap"] == FANIN_MAX

    def test_fanout_is_capped(self, escrow):
        ids = [f"g{i}" for i in range(FANOUT_MAX + 2)]
        for oid in ids:
            escrow.register_candidate(dim(oid), now=NOW)
        hub = ids[0]
        for i in range(1, FANOUT_MAX + 1):
            escrow.add_synapse(hub, ids[i])
        assert escrow.fanout_of(hub) == FANOUT_MAX
        with pytest.raises(SynapseFanCapExceededError) as info:
            escrow.add_synapse(hub, ids[-1])
        assert info.value.context["cap"] == FANOUT_MAX

    def test_a_synapse_counts_against_both_ends(self, escrow):
        ids = fill_pool(escrow, 2)
        escrow.add_synapse(ids[0], ids[1])
        assert escrow.fanout_of(ids[0]) == 1
        assert escrow.fanin_of(ids[1]) == 1

    def test_duplicate_synapse_is_idempotent(self, escrow):
        ids = fill_pool(escrow, 2)
        escrow.add_synapse(ids[0], ids[1])
        escrow.add_synapse(ids[0], ids[1])
        assert escrow.fanout_of(ids[0]) == 1
        assert escrow.audit()["synapses"] == 1

    def test_reverse_synapse_is_a_distinct_edge(self, escrow):
        """有向边：a→b 与 b→a 各占一个名额（与共振对的无序语义刻意不同）。"""
        ids = fill_pool(escrow, 2)
        escrow.add_synapse(ids[0], ids[1])
        escrow.add_synapse(ids[1], ids[0])
        assert escrow.audit()["synapses"] == 2

    def test_self_synapse_is_refused(self, escrow):
        ids = fill_pool(escrow, 1)
        with pytest.raises(DimensionEscrowError, match="自身建立突触"):
            escrow.add_synapse(ids[0], ids[0])

    def test_the_hub_cap_is_what_stops_the_avalanche(self, escrow):
        """上限的意义不是省内存：扇入无界的枢纽一旦形成，任何一次修正都会沿它
        扇出成雪崩 —— 这正是 M3 里程碑"依赖雪崩隔离"要防的东西。
        """
        count = 30
        ids = [f"h{i}" for i in range(count)]
        for oid in ids:
            escrow.register_candidate(dim(oid), now=NOW)
        hub = ids[0]
        blocked = 0
        for other in ids[1:]:
            try:
                escrow.add_synapse(other, hub)
            except SynapseFanCapExceededError:
                blocked += 1
        assert escrow.fanin_of(hub) == FANIN_MAX
        assert blocked == count - 1 - FANIN_MAX


# ---------------------------------------------------------------------------
# F · 转移表提案：两条不依赖具体边集的硬性质
# ---------------------------------------------------------------------------


class TestTransitionProposal:
    def test_the_table_is_exhaustive_over_the_legal_enum(self):
        """键穷尽法定枚举全部十个成员 —— 漏一个就意味着那个状态无法被推理。"""
        assert set(PROPOSED_DIMENSION_TRANSITIONS) == set(DimensionLifecycle)
        assert len(PROPOSED_DIMENSION_TRANSITIONS) == 10

    def test_every_edge_endpoint_is_a_legal_member(self):
        """提案永不脱离契约：任何一条边的两端都必须是法定成员。"""
        for source, proposals in PROPOSED_DIMENSION_TRANSITIONS.items():
            assert isinstance(source, DimensionLifecycle)
            for proposal in proposals:
                assert isinstance(proposal, TransitionProposal)
                assert isinstance(proposal.target, DimensionLifecycle)
                assert proposal.basis, "没有依据的边与随手编的在代码里长得一样"

    def test_every_edge_cites_its_basis(self):
        for proposals in PROPOSED_DIMENSION_TRANSITIONS.values():
            for proposal in proposals:
                assert len(proposal.basis) > 4

    def test_terminal_states_have_no_outgoing_edges(self):
        for state in (
            DimensionLifecycle.MERGED,
            DimensionLifecycle.SPLIT,
            DimensionLifecycle.REJECTED,
        ):
            assert allowed_dimension_transitions(state) == frozenset()

    def test_the_policy_required_edges_are_present(self):
        """政策点名的两条边必须在表里（其余边属提案，这两条属法律）。"""
        assert (
            DimensionLifecycle.TRIAL
            in allowed_dimension_transitions(DimensionLifecycle.CANDIDATE)
        ), "candidate_to_trial_requires_preallocated_monthly_token_quota 要求这条边"
        assert (
            DimensionLifecycle.DORMANT
            in allowed_dimension_transitions(DimensionLifecycle.LOW_ACTIVITY)
        ), "dormant_returns_quota 要求低频能走到休眠"
        assert (
            DimensionLifecycle.LOW_ACTIVITY
            in allowed_dimension_transitions(DimensionLifecycle.ACTIVE)
        ), "low_frequency_dimension_must_not_be_deleted 要求降级而非删除"

    def test_query_shape_matches_the_existing_task_table(self):
        """刻意与既有 ``allowed_task_transitions`` 同名同形：将来获批迁入
        ``services/state_machines.py`` 时，调用方只需改 import。
        """
        from aios_core.services.state_machines import allowed_task_transitions

        assert callable(allowed_task_transitions)
        assert callable(allowed_dimension_transitions)
        assert isinstance(
            allowed_task_transitions(__import__(
                "aios_core.contracts.enums", fromlist=["TaskState"]
            ).TaskState.DRAFT), frozenset
        )
        assert isinstance(
            allowed_dimension_transitions(DimensionLifecycle.CANDIDATE), frozenset
        )

    def test_a_non_enum_query_is_refused(self):
        with pytest.raises(DimensionEscrowError, match="必须是法定"):
            allowed_dimension_transitions("candidate")  # type: ignore[arg-type]

    def test_illegal_transitions_are_refused_with_the_legal_alternatives(self, escrow):
        escrow.register_candidate(dim("d0"), now=NOW)
        with pytest.raises(IllegalLifecycleTransitionError) as info:
            escrow.promote_to_active("d0", now=NOW)  # CANDIDATE 不能直接 ACTIVE
        assert info.value.context["current"] == "candidate"
        assert info.value.context["target"] == "active"
        assert set(info.value.context["allowed"]) == {
            t.value for t in allowed_dimension_transitions(DimensionLifecycle.CANDIDATE)
        }

    def test_the_proposal_is_marked_as_not_yet_ratified(self):
        """提案必须在源码里显式标注，否则会被后人当成法定值引用。"""
        assert "提案" in MODULE_SOURCE
        assert "尚未入法" in MODULE_SOURCE
        assert "state_machines.py" in MODULE_SOURCE  # 记录了法定归属地


# ---------------------------------------------------------------------------
# G · 复用既有法定构件 + 并行线缺陷取证
# ---------------------------------------------------------------------------


class TestReuseAndEvidence:
    def test_reuses_the_legal_lifecycle_enum(self):
        from aios_core.contracts import enums

        assert de.DimensionLifecycle is enums.DimensionLifecycle

    def test_reuses_the_legal_dimension_contract(self):
        from aios_core.contracts import models

        assert de.DimensionDefinition is models.DimensionDefinition

    def test_state_lives_in_the_legal_contract_field(self, escrow):
        """状态存放在 ``DimensionDefinition.lifecycle``，不是本模块的私有副本。

        法定契约的 ``validate_assignment=True`` 会当场校验写入值 —— 非法状态根本
        写不进去，而不是写进去之后再检查。
        """
        escrow.register_candidate(dim("d0"), now=NOW)
        record = escrow.record_of("d0")
        assert record.lifecycle is DimensionLifecycle.CANDIDATE
        escrow.promote_to_trial("d0", monthly_token_quota=PER_CANDIDATE, now=NOW)
        assert escrow.record_of("d0").lifecycle is DimensionLifecycle.TRIAL
        assert escrow.record_of("d0") is record, "同一个契约对象被就地更新"

    def test_module_defines_no_state_enum_of_its_own(self):
        """AST 断言：本模块不得定义第二个状态枚举（双枚举 = 落盘失败的既有前车之鉴）。"""
        tree = ast.parse(MODULE_SOURCE)
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        assert not (defined & {
            "DimensionState", "DimensionLifecycle", "Lifecycle", "DimState", "State"
        })
        assert defined <= {
            "DimensionEscrowError", "BudgetExhaustedError",
            "IllegalLifecycleTransitionError", "ResonanceCapExceededError",
            "SynapseFanCapExceededError", "DimensionDeletionAttemptError",
            "TransitionProposal", "EscrowAccount", "DimensionEscrow",
        }, f"出现了未登记的类定义：{defined}"

    def test_errors_all_propagate_through_the_protocol_error(self):
        from aios_core.errors import AIOSProtocolError

        for cls in (
            BudgetExhaustedError,
            IllegalLifecycleTransitionError,
            ResonanceCapExceededError,
            SynapseFanCapExceededError,
            DimensionDeletionAttemptError,
        ):
            assert issubclass(cls, AIOSProtocolError)

    def test_budget_error_code_is_the_legal_one(self):
        assert BudgetExhaustedError("x").code is ErrorCode.BUDGET_EXHAUSTED

    def test_no_illegal_state_error_code_was_invented(self):
        """``ErrorCode`` 没有 ILLEGAL_STATE，故一律走 INVALID_ARGUMENT（不为造码改枚举）。"""
        assert not hasattr(ErrorCode, "ILLEGAL_STATE")
        assert IllegalLifecycleTransitionError("x").code is ErrorCode.INVALID_ARGUMENT

    def test_evidence_the_sibling_state_enum_still_cannot_be_persisted(self):
        """**取证（主干重写后复核：缺陷没有消失，只是改了名）**。

        原取证：并行线 ``dimensions/evolution_guard.py`` 自定义 ``DimensionState``，四个成员
        值全为大写（``"CANDIDATE"``），而法定 ``DimensionLifecycle`` 是小写（``"candidate"``），
        且 ``EXPIRED`` / ``ARCHIVED`` 在法定枚举里根本不存在 —— 0/4 全灭，整个状态模型
        无法落盘。这是本仓库已付过学费的缺陷类（``ObjectType`` / ``ObjectTypeV3`` 双枚举
        曾致 v3 扩展类型完全无法落盘）。

        主干把那份实现整体重写后，``DimensionState`` 这个名字**确实消失了**。若据此判"已修复"
        就会漏掉真缺陷：新的 ``CandidateStatus`` 原样继承了同样四个大写值，落盘能力一个都没变。
        更值得注意的是同一个文件里出现了**两种值域约定** —— ``CandidateStatus`` 用大写值，
        ``ReviewOutcome`` 用小写值（``still_on_trial`` / ``promoted`` / ``expired``），
        而法定 ``DimensionLifecycle`` 是小写。约定不统一本身就是下一次漂移的温床。
        """
        from aios_core.dimensions import evolution_guard as sibling

        tree = ast.parse(Path(sibling.__file__).read_text(encoding="utf-8"))
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

        # 旧名已消失（这正是"看起来修好了"的陷阱），锚点必须重新定位而不是断言旧名存在
        assert "DimensionState" not in classes
        assert "CandidateStatus" in classes, "取证锚点消失：需重新定位兄弟模块的状态枚举"

        def enum_values(node):
            return [
                st.value.value for st in node.body
                if isinstance(st, ast.Assign) and isinstance(st.value, ast.Constant)
                for tgt in st.targets if isinstance(tgt, ast.Name)
            ]

        values = enum_values(classes["CandidateStatus"])
        assert values == ["CANDIDATE", "ACTIVE", "EXPIRED", "ARCHIVED"], (
            f"兄弟模块状态值域已变，本取证需重新评估：{values}"
        )
        legal = {m.value for m in DimensionLifecycle}
        assert [v for v in values if v in legal] == [], (
            f"有大写值意外落进法定值域，说明法定枚举被改过：{legal}"
        )
        # 逐个实测落盘：0/4 仍然全灭
        failed = []
        for value in values:
            with pytest.raises(Exception):
                dim("probe", lifecycle=value)  # type: ignore[arg-type]
            failed.append(value)
        assert failed == values, f"预期 0/4 全灭，实际 {len(failed)}/{len(values)}"
        # 法定小写值可以落盘 → 失败源于值域，不是契约本身
        assert dim("probe", lifecycle=DimensionLifecycle.CANDIDATE).lifecycle.value == "candidate"
        # EXPIRED / ARCHIVED 在法定枚举里连对应概念都没有（大写小写都找不到）
        assert "EXPIRED" not in legal and "expired" not in legal
        assert "ARCHIVED" not in legal and "archived" not in legal
        # 同一文件两种值域约定：CandidateStatus 全大写，ReviewOutcome 全小写
        review = enum_values(classes["ReviewOutcome"])
        assert review and all(v.isupper() for v in values) and all(v.islower() for v in review), (
            f"值域约定已统一或已变化，本取证需重新评估：{values} / {review}"
        )

    def test_evidence_the_sibling_recursion_fuse_still_trusts_the_caller(self):
        """**取证（主干重写后复核：形式变好了，核心缺陷未变）**。

        原取证：``enter_reflection(depth)`` 由调用方自报深度，而 ``_current_reflection_depth``
        在 ``__init__`` 之后再未被引用（死字段）；调用方永远传 0，熔断就永远不响 ——
        那不是熔断，是建议。

        主干重写后有了 ``ReflectionRecursionGuard``：会校验 ``depth`` 是正整数、会累加
        ``cut_count`` / ``admitted_count``、超限抛 ``RecursiveReflectionCutError``。
        但**深度仍然由调用方自报** —— ``enter(self, depth)`` 的 depth 是入参，类内没有任何
        自持深度栈（没有 enter 时 +1、退出时 -1 的状态），因此一个永远报 1 的调用方
        调用一千次也不会触发熔断。计数器记的是"多少次自称合规"，不是"实际递归多深"。
        """
        from aios_core.dimensions import evolution_guard as sibling

        guard_cls = sibling.ReflectionRecursionGuard
        assert "depth" in inspect.signature(guard_cls.enter).parameters, (
            "取证锚点消失：enter 不再接收调用方自报的 depth"
        )
        cls_node = next(
            n for n in ast.walk(ast.parse(Path(sibling.__file__).read_text(encoding="utf-8")))
            if isinstance(n, ast.ClassDef) and n.name == "ReflectionRecursionGuard"
        )
        touched = {
            tgt.attr for n in ast.walk(cls_node) if isinstance(n, ast.Assign)
            for tgt in n.targets if isinstance(tgt, ast.Attribute)
        } | {
            n.target.attr for n in ast.walk(cls_node)
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Attribute)
        }
        depth_state = {a for a in touched if "depth" in a.lower()}
        assert depth_state <= {"_max_depth"}, (
            f"守卫已开始自持深度状态 {sorted(depth_state)}，本取证需重新评估"
        )
        # 行为证明：永远自报 1，一千次也不熔断（真实递归多深与它无关）
        guard = guard_cls(max_depth=1)
        for _ in range(1000):
            assert guard.enter(1) == 1
        assert guard.cut_count == 0
        assert guard.admitted_count == 1000
        # 而自报 2 立刻熔断 → 熔断只取决于调用方说什么
        with pytest.raises(sibling.RecursiveReflectionCutError):
            guard.enter(2)
        assert guard.cut_count == 1
        # 非正整数会被拒（这是重写后新增的真改进，如实记下来）
        for bad in (0, -1):
            with pytest.raises(Exception):
                guard.enter(bad)

    def test_evidence_the_sibling_cap_enforcement_still_uses_a_bare_assert(self):
        """**取证（主干重写后复核：常量没了，bare assert 还在承重）**。

        原取证：并行线把 ACTIVE ≤ 32 的"硬顶不变量"实现为 ``assert len(self._active) <=
        ACTIVE_CAP``，而 ``assert`` 在 ``python -O`` 下被整体剥除 —— 自称"不是告警"的
        不变量会在优化模式下静默消失。

        主干重写后 ``ACTIVE_CAP`` 常量确实没了（改为实例级 ``_max_active``），但硬顶分支里
        仍留着一句 ``assert victim is not None``：它承重的是"到达上限时必须能算出该归档谁"。
        ``-O`` 下这句被剥除后，``victim`` 为 ``None`` 会被当合法值继续用（随后取
        ``victim.candidate_id`` 抛 AttributeError，或更糟 —— 若那行也变了就静默错误归档）。
        本模块的守恒式一律用显式 raise 实现，不受 ``-O`` 影响，另有测试钉住。
        """
        from aios_core.dimensions import evolution_guard as sibling

        sibling_tree = ast.parse(Path(sibling.__file__).read_text(encoding="utf-8"))
        asserts = [n for n in ast.walk(sibling_tree) if isinstance(n, ast.Assert)]
        assert asserts, "兄弟模块已不再使用 bare assert —— 本取证应改写为回归守卫"

        # 定位：断言至少有一个 assert 位于硬顶分支（if len(self._active) >= self._max_active）之内
        parent = {c: p for p in ast.walk(sibling_tree) for c in ast.iter_child_nodes(p)}
        def under_cap_branch(node):
            cur = parent.get(node)
            while cur is not None:
                if isinstance(cur, ast.If):
                    test_src = ast.get_source_segment(
                        Path(sibling.__file__).read_text(encoding="utf-8"), cur.test) or ""
                    if "_max_active" in test_src:
                        return True
                cur = parent.get(cur)
            return False

        cap_asserts = [n for n in asserts if under_cap_branch(n)]
        assert cap_asserts, (
            f"bare assert 已移出硬顶分支（现存 assert 行号 {[n.lineno for n in asserts]}），"
            "本取证需重新评估"
        )
        # 本模块的承重不变量不得是 assert
        bare_asserts = [n for n in ast.walk(ast.parse(MODULE_SOURCE)) if isinstance(n, ast.Assert)]
        assert bare_asserts == [], "承重不变量用 assert 实现，-O 下会被剥除"


# ---------------------------------------------------------------------------
# H · 观测面与端到端
# ---------------------------------------------------------------------------


class TestAuditAndEndToEnd:
    def test_audit_reports_the_conservation_invariant(self, escrow):
        fill_pool(escrow, 3)
        audit = escrow.audit()
        assert audit["conservation_holds"] is True
        assert audit["pool_tokens"] == POOL
        assert audit["escrowed_tokens"] == 3 * PER_CANDIDATE
        assert audit["free_tokens"] == POOL - 3 * PER_CANDIDATE
        assert audit["dimensions_registered"] == 3
        assert audit["dimensions_by_lifecycle"] == {"trial": 3}

    def test_audit_is_json_serializable(self, escrow):
        fill_pool(escrow, 2)
        escrow.add_resonance_pair("d0", "d1", window_id="w")
        escrow.add_synapse("d0", "d1")
        text = json.dumps(escrow.audit(), ensure_ascii=False)
        assert json.loads(text)["synapses"] == 1

    def test_account_is_json_serializable(self, escrow):
        fill_pool(escrow, 1)
        account = escrow._account("d0")
        assert isinstance(account, EscrowAccount)
        payload = json.loads(json.dumps(account.to_audit(), ensure_ascii=False))
        assert payload["quota"] == PER_CANDIDATE
        assert payload["lifecycle"] == "trial"
        assert payload["returned_at"] is None

    def test_naive_datetimes_are_interpreted_as_utc(self, escrow):
        naive = datetime(2026, 9, 16, 12, 0)
        escrow.register_candidate(dim("d0"), now=naive)
        account = escrow._account("d0")
        assert account.escrowed_at.tzinfo is not None
        assert account.escrowed_at == NOW

    def test_a_full_month_of_dimension_life_stays_inside_the_escrow(self, escrow):
        """端到端：一个月里反复创建、降级、休眠、复活、合并、拒绝。

        断言三件事同时成立 —— 每一次变更后配额守恒；注册总数只增不减（零删除）；
        任何时候池都不为负。这三条一起，就是"棘轮被刹住"的可执行定义。
        """
        ever_registered = set()
        for day in range(30):
            now = NOW + timedelta(days=day)
            oid = f"m{day}"
            escrow.register_candidate(dim(oid), now=now)
            ever_registered.add(oid)
            try:
                escrow.promote_to_trial(oid, monthly_token_quota=PER_CANDIDATE, now=now)
            except BudgetExhaustedError:
                assert escrow.audit()["free_tokens"] < PER_CANDIDATE
                continue
            assert escrow.audit()["conservation_holds"]
            if day % 3 == 0:
                escrow.promote_to_active(oid, now=now)
                if day % 6 == 0:
                    escrow.mark_low_activity(oid, now=now)
                    escrow.send_dormant(oid, now=now)
            elif day % 3 == 1:
                escrow.reject(oid, now=now, reason="试用期未通过")
            assert escrow.audit()["conservation_holds"]
            assert escrow.audit()["free_tokens"] >= 0
            assert set(escrow.registered_ids()) >= ever_registered

        audit = escrow.audit()
        assert audit["conservation_holds"] is True
        assert audit["dimensions_registered"] == 30
        assert audit["free_tokens"] + audit["escrowed_tokens"] == POOL
        assert audit["quota_returning_events"] > 0, "一个月里没有一次归还 = 棘轮"

    def test_the_pool_bounds_how_many_dimensions_a_month_can_buy(self, escrow):
        """配额池直接把"AI 一个月能造多少维度"变成可计算的常数（§72 创建权 +
        §76 不能无限爆炸的合流点）。
        """
        affordable = POOL // PER_CANDIDATE
        assert affordable == 10
        made = fill_pool(escrow, affordable)
        assert len(made) == affordable
        escrow.register_candidate(dim("one_too_many"), now=NOW)
        with pytest.raises(BudgetExhaustedError):
            escrow.promote_to_trial(
                "one_too_many", monthly_token_quota=PER_CANDIDATE, now=NOW
            )
        assert escrow.audit()["dimensions_by_lifecycle"]["trial"] == affordable

    def test_public_api_surface_is_stable(self):
        """钉住公开面：门禁 3 要求"无删除 API"，这条测试让任何新增的公开方法
        都必须经过复核（新增即失败），而不是悄悄混进来。
        """
        public = {
            name
            for name, _ in inspect.getmembers(DimensionEscrow, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert public == {
            "add_resonance_pair", "add_synapse", "audit", "fanin_of", "fanout_of",
            "history_of", "lifecycle_of", "mark_low_activity", "merge_into",
            "promote_to_active", "promote_to_trial", "quota_of", "reactivate",
            "record_of", "register_candidate", "registered_ids", "reject",
            "resonance_pairs_in", "send_dormant",
        }
