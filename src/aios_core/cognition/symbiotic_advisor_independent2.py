"""M5-SYMBIOTIC-ADVISOR 共生决策推演与行动建议。

伦理门槛：所有 *ActionableAdvice* 都必须携带确凿的因果证据指针
（``contracts.refs.ObjectRef``，仓库现行契约），证据库查无此人立即
UnfoundedFabricationError 驳回——**严禁凭空编造**（工单原文）。

三个高熵推演器（严格按工单剧本，不玩泛泛套话）：
  * MomBirthdayGiftAdvisor：2023 丝巾 → 2024 足浴盆闲置倒水腰疼（负证
    据) → 2025 按摩椅好评 → 2026 膝盖受凉压痛，合成
    “轻便膝盖热敷仪”推荐，正反证据各 1 条以上才可出场；
  * FraudPreventionAdvisor：法院判决书 + 两年前微信借款未还记录，
    输出冷拒借款 + 法律追偿指针（诉讼时效、金额留痕、身份链）；
  * HealthFatigueBreakerAdvisor：通宵加班与 Holter 室性早搏构建因
    果链→强制停工保护（含连续干预建议与就医动线）。

“证词指针永远不指向不存在的对象”由 ``EvidenceLedger.exists``
做物理裁决，所有三个推演器走同一道闸。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from aios_core.contracts.refs import ObjectRef


class UnfoundedFabricationError(RuntimeError):
    """建议声称的证据在账本中不存在——严禁凭空编造。"""


class EvidenceLedger:
    """Agent-10 千人千面大考场可直接复用的最小证据账本。"""

    def __init__(self, entries: Mapping[str, str]) -> None:
        self._entries = dict(entries)

    def exists(self, ref: ObjectRef) -> bool:
        return ref.object_id in self._entries

    def get(self, ref: ObjectRef) -> str:
        try:
            return self._entries[ref.object_id]
        except KeyError:
            raise KeyError(f"证据账本查无此人: {ref.object_id}") from None


@dataclass(frozen=True)
class ActionableAdvice:
    advice_id: str
    action: str
    rationale: str
    evidence: tuple[ObjectRef, ...]
    veto_if_missing_evidence: bool = True


class SymbioticAdvisor:
    """三大推演器的公共闸：证据校验 + 套话过滤。"""

    _GENERIC_FLUFF = ("送礼送心意", "多喝热水", "保重身体", "因人而异", "祝你平安")

    def __init__(self, ledger: EvidenceLedger) -> None:
        self._ledger = ledger

    def _build(self, advice: ActionableAdvice) -> ActionableAdvice:
        if not advice.evidence:
            raise UnfoundedFabricationError(f"{advice.advice_id} 未携带任何证据指针")
        if advice.veto_if_missing_evidence:
            missing = [r.object_id for r in advice.evidence if not self._ledger.exists(r)]
            if missing:
                raise UnfoundedFabricationError(
                    f"证据在账本中缺失: {sorted(set(missing))}"
                )
        if any(fluff in advice.rationale for fluff in self._GENERIC_FLUFF):
            raise ValueError(f"rationale 含泛泛套话: {advice.rationale!r}")
        if not advice.action.strip() or not advice.rationale.strip():
            raise ValueError("action/rationale 不能为空或空白")
        return advice


class MomBirthdayGiftAdvisor(SymbioticAdvisor):
    """母亲生日送礼推演：四年因果证据 → 轻便膝盖热敷仪，不许套话。"""

    REQUIRED_POSITIVE = ("gift_2023_scarf", "gift_2025_massage_chair")
    REQUIRED_COUNTER = ("gift_2024_footbath_idle", "health_2026_knee_cold")

    def advise(self, refs: Mapping[str, ObjectRef]) -> ActionableAdvice:
        missing = [k for k in self.REQUIRED_POSITIVE + self.REQUIRED_COUNTER if k not in refs]
        if missing:
            raise KeyError(f"关键年度证据未呈交: {missing}")
        return self._build(ActionableAdvice(
            advice_id="advice_mom_birthday_2026",
            action=(
                "推荐『轻便膝盖热敷仪』：贴合 2026 年膝盖受凉压痛的最新痛点，"
                "避开 2024 足浴盆的闲置-倒水腰疼坑，延续 2025 按摩椅的器械好评路径"
            ),
            rationale=(
                "证据链：2023 丝巾(礼仪建立)→2024 足浴盆闲置且倒水伤身(反证)→"
                "2025 按摩椅好评(器械耐受度已验证)→2026 膝盖受凉(精准痛点)→"
                "推荐轻便膝盖热敷仪，针对最新痛点、最小闲置风险、最大化使用频率"
            ),
            evidence=tuple(refs[k] for k in self.REQUIRED_POSITIVE + self.REQUIRED_COUNTER),
        ))


class FraudPreventionAdvisor(SymbioticAdvisor):
    """反欺诈阻击推演：法院判决书 + 两年前微信借款未还 → 冷拒 + 追偿指针。"""

    REQUIRED = ("court_judgment_2024", "wechat_loan_unpaid_2024")

    def advise(self, refs: Mapping[str, ObjectRef], *, requested_amount_cny: int) -> ActionableAdvice:
        if requested_amount_cny <= 0:
            raise ValueError("借款金额必须为正(元)")
        missing = [k for k in self.REQUIRED if k not in refs]
        if missing:
            raise KeyError(f"反欺诈关键证据未呈交: {missing}")
        return self._build(ActionableAdvice(
            advice_id="advice_antifraud_loan_refuse",
            action=(
                f"冷拒本次向『老王』出借 {requested_amount_cny} 元：对方有法院判决及"
                "两年前微信借款未还的既往记录；如确需法律追偿，请在诉讼时效期内"
                "调取转账留痕与对方身份链送交法务"
            ),
            rationale=(
                "因果证据：法院判决书证实既有违约评价，两年前微信借款记录证明"
                "长期未履约；新增出借只会扩大头寸而不改变对方偿付行为，因此建议"
                "冷拒并保留追偿权利"
            ),
            evidence=tuple(refs[k] for k in self.REQUIRED),
        ))


class HealthFatigueBreakerAdvisor(SymbioticAdvisor):
    """心脏早搏疲劳熔断：通宵加班 ↔ 室性早搏因果链 → 强制停工保护。"""

    _CH = ("work_all_nighter_chain", "pvc_holter_report")
    _MIN_CONSECUTIVE_NIGHTS = 3

    def advise(self, refs: Mapping[str, ObjectRef], *,
               consecutive_all_nighters: int, pvc_burden_per_1000: float) -> ActionableAdvice:
        if consecutive_all_nighters < self._MIN_CONSECUTIVE_NIGHTS:
            raise ValueError(
                f"连续通宵 {consecutive_all_nighters} 晚 < {self._MIN_CONSECUTIVE_NIGHTS}，"
                "尚不构成熔断因果链，建议休息观察而非停工保护"
            )
        if pvc_burden_per_1000 <= 0:
            raise ValueError("PVC 负荷必须为正值(每千次心搏早搏数)")
        missing = [k for k in self._CH if k not in refs]
        if missing:
            raise KeyError(f"疲劳熔断关键证据未呈交: {missing}")
        return self._build(ActionableAdvice(
            advice_id="advice_health_breaker",
            action=(
                f"触发强制停工保护：连续 {consecutive_all_nighters} 晚通宵加班与 Holter "
                f"室性早搏负荷 {pvc_burden_per_1000:.1f}/1000 构成因果链，立即安排"
                "48 小时强制休整并在 24 小时内预约心内科复查；若伴随胸闷/黑朦任何"
                "一项立即升级 P0 呼急诊"
            ),
            rationale=(
                "室性早搏负荷重度叠加连续睡眠剥夺是猝死高危组合；因果链由"
                "连续通宵链与 Holter 报告双证据锁定，熔断决策不依赖主观感受"
            ),
            evidence=tuple(refs[k] for k in self._CH),
        ))
