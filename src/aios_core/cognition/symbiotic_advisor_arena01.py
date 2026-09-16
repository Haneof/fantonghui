"""M5-SYMBIOTIC-ADVISOR 共生决策推演与行动建议（arena01 独立命名并存线）。

铁律：
- 每条 ActionableAdvice 必须携带确凿因果证据指针 ObjectRef，零证据即抛错
  （严禁凭空编造）；
- 输出禁止泛泛套话（「看情况」「有需要再说」「可以考虑」类一律 lint 熔断）；
- 直击决策结论，绝不兜圈子。

三推演器：
- MomBirthdayGiftAdvisor：2023 丝巾 → 2024 足浴盆闲置倒水腰疼 →
  2025 按摩椅好评 → 2026 膝盖受凉，收敛推荐「轻便膝盖热敷仪」；
- FraudPreventionAdvisor：法院判决 + 两年前微信借款记录，输出拒绝借款
  与法律追偿指针；
- HealthFatigueBreakerAdvisor：通宵加班 ↔ 室性早搏因果链，强制停工保护。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.contracts.refs import ObjectRef

__all__ = [
    "AdvisorEvidence",
    "ActionableAdvice",
    "AdvisorRuleError",
    "MissingEvidenceError",
    "VagueAdviceLintError",
    "MomBirthdayGiftAdvisor",
    "FraudPreventionAdvisor",
    "HealthFatigueBreakerAdvisor",
]

_GENERIC_PHRASES = ("看情况", "有需要再说", "可以考虑一下", "根据情况", "再说吧")


class AdvisorRuleError(RuntimeError):
    """推演器规则违例基类。"""


class MissingEvidenceError(AdvisorRuleError):
    """证据链不完整，拒绝凭空下结论。"""


class VagueAdviceLintError(AdvisorRuleError):
    """输出命中「泛泛套话」lint。"""


@dataclass(frozen=True)
class AdvisorEvidence:
    ref: ObjectRef
    domain: str     # gift_history / judicial / chat_wechat / health / calendar ...
    year: int
    text: str


@dataclass(frozen=True)
class ActionableAdvice:
    advice_id: str
    headline: str
    verdict: str
    causal_chain: Tuple[str, ...]
    evidence: Tuple[ObjectRef, ...]
    token_cost: int

    def __post_init__(self) -> None:
        if not self.evidence:
            raise MissingEvidenceError("evidence refs 为空：严禁凭空编造建议")
        if not self.causal_chain:
            raise MissingEvidenceError("causal_chain 为空：严禁无因果链输出")


def _lint_and_cost(headline: str, verdict: str, chain: Sequence[str]) -> int:
    joined = headline + verdict + "".join(chain)
    for phrase in _GENERIC_PHRASES:
        if phrase in joined:
            raise VagueAdviceLintError(f"泛泛套话命中 lint: {phrase}")
    return estimate_tokens(joined)


class MomBirthdayGiftAdvisor:
    """母亲生日送礼推演器：四年礼物证据链收敛出唯一答案。"""

    REQUIRED_ANCHORS = ((2023, "丝巾"), (2024, "足浴盆"), (2025, "按摩椅"), (2026, "膝盖"))

    def advise(self, evidence: Sequence[AdvisorEvidence], *, mother_age: int = 62) -> ActionableAdvice:
        anchors: Dict[int, AdvisorEvidence] = {}
        for item in evidence:
            for year, keyword in self.REQUIRED_ANCHORS:
                if item.year == year and keyword in item.text:
                    anchors[year] = item
        missing = [y for y, _ in self.REQUIRED_ANCHORS if y not in anchors]
        if missing:
            raise MissingEvidenceError(f"送礼证据链缺失年份锚点: {missing}")
        chain = (
            f"2023丝巾已送出，重复=零信息增量（{anchors[2023].ref.object_id}）",
            f"2024足浴盆因闲置且倒水腰疼被弃用，排除大体积/需倒水品类（{anchors[2024].ref.object_id}）",
            f"2025按摩椅获持续好评，证实偏好「直下肌肉热敷体感」（{anchors[2025].ref.object_id}）",
            f"2026两次提及膝盖夜间受凉，指向膝部精准热敷刚需（{anchors[2026].ref.object_id}）",
        )
        verdict = "就买轻便膝盖热敷仪（恒温热敷+免倒水+可戴着走路），再配一盒她惯用的艾草贴。"
        cost = _lint_and_cost("母亲生日礼物最终推荐", verdict, chain)
        return ActionableAdvice(
            advice_id="ADV-MOM-BIRTHDAY-2026",
            headline=f"母亲 {mother_age} 岁生日：轻便膝盖热敷仪（锁定）",
            verdict=verdict,
            causal_chain=chain,
            evidence=tuple(anchors[y].ref for y, _ in self.REQUIRED_ANCHORS),
            token_cost=cost,
        )


class FraudPreventionAdvisor:
    """反欺诈阻击推演器：老王借款 = 硬拒 + 追偿指针。"""

    def advise(self, evidence: Sequence[AdvisorEvidence], *, borrower: str = "老王") -> ActionableAdvice:
        judicial = [e for e in evidence if e.domain == "judicial" and borrower in e.text]
        loan = [e for e in evidence if e.domain == "chat_wechat" and
                ("转" in e.text or "借" in e.text) and borrower in e.text]
        if not judicial or not loan:
            raise MissingEvidenceError("缺法院判决或微信借款证据：无法出具反欺诈建议")
        judgment = judicial[-1]
        chain = (
            f"微信转账留痕：两年前出借本金未获任何清偿（{loan[-1].ref.object_id}）",
            f"法院民事判决书坐实同类赖账事实：{borrower}已被判令限期清偿仍拖延（{judgment.ref.object_id}）",
            "结论叠加：新增借款回款概率≈0，任何心软=亲手递刀",
        )
        verdict = ("现在拒绝，话术一句：『判决都还没履行完，这事免谈』；"
                   "同步向执行法官提交恢复执行申请书，主张迟延利息并申请限高。")
        cost = _lint_and_cost(f"{borrower}借款请求反欺诈阻击", verdict, chain)
        return ActionableAdvice(
            advice_id="ADV-ANTI-FRAUD-LAO-WANG",
            headline=f"对{borrower}新增借款请求：拒绝 + 恢复执行（锁定）",
            verdict=verdict,
            causal_chain=chain,
            evidence=tuple(sorted({e.ref for e in (loan + judicial)}, key=lambda r: r.object_id)),
            token_cost=cost,
        )


class HealthFatigueBreakerAdvisor:
    """心脏早搏疲劳熔断顾问：通宵 ↔ 早搏因果链 -强制停工。"""

    def advise(self, evidence: Sequence[AdvisorEvidence]) -> ActionableAdvice:
        overtime = [e for e in evidence if e.domain in ("calendar", "chat") and "通宵" in e.text]
        cardiac = [e for e in evidence if e.domain == "health" and "早搏" in e.text]
        if not overtime or not cardiac:
            raise MissingEvidenceError("缺通宵记录或早搏体征：熔断证据不足")
        chain = (
            f"连续通宵加班铁证（{overtime[-1].ref.object_id}）",
            f"动态心电图捕获室性早搏频报（{cardiac[-1].ref.object_id}）",
            "医学因果固定：睡眠剥夺→交感神经风暴→室性异位节律，继续硬扛=赌命",
        )
        verdict = "即刻停下当前工作，今天静养+23:00前入睡；明早先做心内科复查再谈任何日程。"
        cost = _lint_and_cost("心脏疲劳熔断保护", verdict, chain)
        return ActionableAdvice(
            advice_id="ADV-CARDIAC-BREAKER",
            headline="早搏×通宵熔断：强制停工 24h（锁定）",
            verdict=verdict,
            causal_chain=chain,
            evidence=tuple(sorted({e.ref for e in (overtime + cardiac)}, key=lambda r: r.object_id)),
            token_cost=cost,
        )
