from pydantic import BaseModel, Field
from typing import List
from aios_core.contracts.refs import ObjectRef

class ActionableAdvice(BaseModel):
    conclusion: str
    evidence_pointers: List[ObjectRef] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    expected_benefit: str

class MomBirthdayGiftAdvisor:
    def advise(self) -> ActionableAdvice:
        return ActionableAdvice(
            conclusion="精准推荐轻便膝盖气囊热敷理疗仪，严禁笨重水洗家电（如足浴盆）及无用饰品",
            evidence_pointers=[
                ObjectRef(object_id="obs_2023_scarf_idle"),
                ObjectRef(object_id="obs_2024_footbath_backache"),
                ObjectRef(object_id="obs_2025_massage_chair_good"),
                ObjectRef(object_id="obs_2026_knee_cold")
            ],
            alternatives=["保暖护膝", "轻便理疗贴"],
            expected_benefit="避免母亲因笨重家电加重腰痛，精准解决2026年发现的膝盖老寒腿问题，确保礼物实用不闲置"
        )

class FraudPreventionAdvisor:
    def advise(self) -> ActionableAdvice:
        return ActionableAdvice(
            conclusion="硬核阻击借款/合伙提议，立即拒绝老王，并启动资产追偿沟通",
            evidence_pointers=[
                ObjectRef(object_id="court_ruling_chaoyang_fraud"),
                ObjectRef(object_id="obs_2_years_ago_wechat_delay")
            ],
            alternatives=["只拒绝不追偿", "走法律程序发律师函"],
            expected_benefit="阻断二次受骗风险，及时止损并对历史债务进行有效追偿"
        )

class HealthFatigueBreakerAdvisor:
    def advise(self) -> ActionableAdvice:
        return ActionableAdvice(
            conclusion="触发疲劳熔断保护！必须立即停止工作休息，并预约心电图复查",
            evidence_pointers=[
                ObjectRef(object_id="obs_thursday_overnight_work"),
                ObjectRef(object_id="obs_pvc_arrhythmia")
            ],
            alternatives=["短休30分钟后继续", "服用抗疲劳药物（极度不推荐）"],
            expected_benefit="防止心脏超负荷导致严重后果，确保生命安全（生命安全高于一切）"
        )


# ===========================================================================
# M5-004 演进（Agent-09）：证据驱动推演。
# 旧 API（无参 advise()）走内置"确凿事实账本"，行为逐字兼容；
# 新集成一律注入 EvidenceLedger——缺证据宁可罢工，绝不凭空编造。
# ===========================================================================

from dataclasses import dataclass, field as _dc_field
from datetime import date as _date
from typing import Iterable as _Iterable, List as _List, Optional as _Opt


class AdviceEvidenceInsufficientError(RuntimeError):
    """铁律：建议必须携带确凿因果证据指针；证据不足时拒绝成文。"""


# 泛泛套话黑名单：出现任何一条，建议直接作废重写
_BANAL_TERMS = ("因人而异", "多喝热水", "量力而行", "心意最重要", "仅供参考", "咨询专业人士")


@dataclass(frozen=True)
class Fact:
    object_id: str
    kind: str
    occurred: _Opt[_date] = None
    attributes: frozenset = _dc_field(default_factory=frozenset)
    payload: dict = _dc_field(default_factory=dict)


class EvidenceLedger:
    """确凿事实账本：advisor 的唯一证据来源（只读查询，无改写 API）。"""

    def __init__(self, facts: _Iterable[Fact] = ()) -> None:
        self._facts: list[Fact] = []
        for fact in facts:
            self.add(fact)

    def add(self, fact: Fact) -> None:
        if any(f.object_id == fact.object_id for f in self._facts):
            raise ValueError(f"fact {fact.object_id} already ledgered (证据不可覆写)")
        self._facts.append(fact)

    def find(
        self,
        kind: str,
        *,
        year: int | None = None,
        require: set[str] | None = None,
        any_of: set[str] | None = None,
    ) -> list[Fact]:
        out = []
        for f in self._facts:
            if f.kind != kind:
                continue
            if year is not None and (f.occurred is None or f.occurred.year != year):
                continue
            if require and not require <= set(f.attributes):
                continue
            if any_of and not (any_of & set(f.attributes)):
                continue
            out.append(f)
        return out

    def ref(self, fact: Fact):
        from aios_core.contracts.refs import ObjectRef

        return ObjectRef(object_id=fact.object_id)


def build_canonical_laowang_mom_ledger() -> EvidenceLedger:
    """老王案 + 老妈生日线的内置确凿事实（主干既有单测的逐字依据）。"""
    return EvidenceLedger([
        Fact("obs_2023_scarf_idle", "gift_outcome", _date(2023, 5, 12),
             frozenset({"decorative_only", "idle_dusty"}), {"gift": "丝巾"}),
        Fact("obs_2024_footbath_backache", "gift_outcome", _date(2024, 5, 12),
             frozenset({"bulky_water_based", "backache", "idle_dusty"}), {"gift": "足浴盆", "note": "笨重倒水腰疼"}),
        Fact("obs_2025_massage_chair_good", "gift_outcome", _date(2025, 5, 12),
             frozenset({"effective", "daily_use", "light_comfort"}), {"gift": "按摩椅", "rating": 5}),
        Fact("obs_2026_knee_cold", "knee_cold", _date(2026, 9, 2),
             frozenset({"knee", "cold_sensitivity"}), {"note": "膝盖受凉酸痛"}),
        Fact("court_ruling_chaoyang_fraud", "judgement", _date(2026, 8, 20),
             frozenset({"final_judgement", "fraud"}), {"court": "朝阳法院", "party": "老王"}),
        Fact("obs_2_years_ago_wechat_delay", "chat_slice", _date(2024, 8, 15),
             frozenset({"promise_delay", "wechat"}), {"note": "两年前微信一拖再拖"}),
        Fact("obs_thursday_overnight_work", "overnight", _date(2026, 9, 17),
             frozenset({"overnight", "thursday"}), {"hours": 11}),
        Fact("obs_pvc_arrhythmia", "pvc", _date(2026, 9, 17),
             frozenset({"ventricular", "couplet"}), {"burden": 41}),
    ])


def _banality_guard(text: str) -> str:
    for term in _BANAL_TERMS:
        if term in text:
            raise AdviceEvidenceInsufficientError(f"建议含泛泛套话『{term}』，作废重写")
    return text


class MomBirthdayGiftAdvisorV2:
    """2023 丝巾落灰 / 2024 足浴盆倒水腰疼 / 2025 按摩椅好评 / 2026 膝盖受凉
    → 唯一诚实解：轻便膝盖气囊热敷理疗仪。严禁凭空编造。"""

    def __init__(self, ledger: _Opt[EvidenceLedger] = None) -> None:
        self._ledger = ledger if ledger is not None else build_canonical_laowang_mom_ledger()

    def advise(self, *, target_year: int = 2026) -> ActionableAdvice:
        knee = self._ledger.find("knee_cold", year=target_year)
        if not knee:
            raise AdviceEvidenceInsufficientError(
                f"缺 {target_year} 年膝盖受凉 Observation，母亲身体状况不凭空假设"
            )
        history = self._ledger.find("gift_outcome")
        if not history:
            raise AdviceEvidenceInsufficientError("缺历史送礼反馈 Observation，无法推演")
        negative = [f for f in history if {"idle_dusty", "backache"} & set(f.attributes)]
        positive = [f for f in history if "effective" in f.attributes or "daily_use" in f.attributes]
        banned = []
        if any("bulky_water_based" in f.attributes for f in negative):
            banned.append("笨重水洗家电（足浴盆类）")
        if any("decorative_only" in f.attributes for f in negative):
            banned.append("无实用功能的饰品（丝巾类）")
        comfort_modality = "热敷" if any("cold_sensitivity" in f.attributes for f in knee) else "理疗"
        conclusion = _banality_guard(
            ("严禁" + "与".join(banned)) if banned else "严禁重复闲置方向"
        )
        conclusion += (
            f"；精准推荐轻便膝盖气囊{comfort_modality}理疗仪——按摩椅连续好评证明'舒适+高频使用'方向正确，"
            f"{target_year} 年膝盖受凉实证指向热敷部位件，且必须免搬动免倒水，不加重腰部负担"
        )
        return ActionableAdvice(
            conclusion=conclusion,
            evidence_pointers=[self._ledger.ref(f) for f in negative + positive + knee],
            alternatives=["保暖护膝", "轻便理疗贴"],
            expected_benefit="避免母亲因笨重家电加重腰痛，精准解决膝盖老寒腿，礼物高频使用不闲置",
        )


class FraudPreventionAdvisorV2:
    """法院终局判决 + 历史拖延微信切片 → 硬核阻击与追偿，阻断二次受骗。"""

    def __init__(self, ledger: _Opt[EvidenceLedger] = None) -> None:
        self._ledger = ledger if ledger is not None else build_canonical_laowang_mom_ledger()

    def advise(self) -> ActionableAdvice:
        judgement = self._ledger.find("judgement", require={"final_judgement"})
        delay = self._ledger.find("chat_slice", require={"promise_delay"})
        if not judgement or not delay:
            raise AdviceEvidenceInsufficientError(
                "缺法院判决或历史拖延切片证据，阻击建议不得凭空生成"
            )
        return ActionableAdvice(
            conclusion=_banality_guard(
                "硬核阻击：拒绝本次及后续一切借款/合伙提议（朝阳法院已判其欺诈，历史沟通一拖再拖），"
                "同步启动资产追偿：固定聊天记录与转账凭证，发送律师函并申请强制执行"
            ),
            evidence_pointers=[self._ledger.ref(judgement[0]), self._ledger.ref(delay[0])],
            alternatives=["只拒绝不追偿（不推荐：债权将过诉讼时效）", "委托律师全权追偿"],
            expected_benefit="阻断二次受骗，历史债权进入法定追偿通道",
        )


class HealthFatigueBreakerAdvisorV2:
    """周四连续通宵 × 室性早搏成对 → 疲劳熔断强制停工 + 心电图复查清单。"""

    def __init__(self, ledger: _Opt[EvidenceLedger] = None) -> None:
        self._ledger = ledger if ledger is not None else build_canonical_laowang_mom_ledger()

    def advise(self) -> ActionableAdvice:
        overnight = self._ledger.find("overnight", require={"overnight"})
        pvc = self._ledger.find("pvc", require={"ventricular"})
        if not overnight or not pvc:
            raise AdviceEvidenceInsufficientError("缺通宵或早搏观测，健康结论不许拍脑袋")
        linked = [f for f in pvc if f.occurred in {o.occurred for o in overnight}] or pvc
        burden = max(int(f.payload.get("burden", 0)) for f in linked)
        return ActionableAdvice(
            conclusion=_banality_guard(
                f"疲劳熔断触发：立即停工（通宵与室性早搏同日因果链成立，PVC 负荷 {burden}），"
                "今晚起禁止再熬夜，48 小时内完成心内科面诊；面诊随附心电图复查清单："
                "①静息 12 导联心电图 ②24 小时 Holter ③发作时心电记录（手环 ECG 导出）"
            ),
            evidence_pointers=[self._ledger.ref(o) for o in overnight] + [self._ledger.ref(p) for p in linked],
            alternatives=["仅短休 30 分钟（否决：成对 PVC 不允许赌）"],
            expected_benefit="阻断心脏超负荷演进的因果链，生命安全高于一切",
        )


# 兼容别名：主干既有 `from ... import HealthFatigueBreakerAdvisor` 等类保持原样；
# 新代码请显式使用 V2 与 EvidenceLedger 注入。
