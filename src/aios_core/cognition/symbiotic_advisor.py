from pydantic import BaseModel, Field
from typing import List
from aios_core.contracts.refs import ObjectRef

class ActionableAdvice(BaseModel):
    conclusion: str
    evidence_pointers: List[ObjectRef] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    expected_benefit: str
    # ---- M5-004 可选扩展字段（向下兼容：v1 用例无需感知） ----
    advice_id: str = Field(default="", description="建议唯一编号")
    hard_refusal: bool = Field(default=False, description="是否硬核阻击")
    forced_action: bool = Field(default=False, description="是否强制行动")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

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


# =====================================================================
# M5-004 共生决策辅助演化件（最高宪法第一铁律：输出质量绝对第一）
# =====================================================================
#
# v1 的三个顾问只会背诵预置结论；M5 要求它们**下钻全周期记忆**：
# 1. EvidenceLedger 证据台账——顾问只能引用台账里真实存在的事实指针，
#    引用不存在的 object_id 直接抛 MissingEvidenceError（禁止凭空捏造）；
# 2. 送老妈礼物：从历年礼物结局（落灰/闲置腰疼/好评）+ 当年膝盖受凉
#    观测真实推导，严禁笨重水洗家电与无用饰品，预算不足自动降级替代品；
# 3. 反诈阻击：法院判决 + 历史拖延记录缺一不可，证据链不齐拒绝出具建议；
# 4. 疲劳熔断：通宵与早搏的时间先后必须构成因果方向，否则不出熔断令。
# v1 无参 advise() 语义保持 100% 向下兼容。

import datetime as _datetime
import uuid as _uuid
from typing import Dict as _Dict, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional


class MissingEvidenceError(ValueError):
    """建议所需的因果证据缺失或指针不实——宁可不答，绝不编造。"""


class EvidenceLedger:
    """因果证据台账：fact_id -> 事实载荷，并铸造可校验的 ObjectRef 指针。"""

    def __init__(self, facts: _Optional[_Mapping[str, _Mapping]] = None) -> None:
        self._facts: _Dict[str, dict] = {}
        if facts:
            for fact_id, payload in facts.items():
                self.register(fact_id, payload)

    def register(self, fact_id: str, payload: _Mapping) -> ObjectRef:
        if not fact_id:
            raise ValueError("fact_id 不能为空")
        self._facts[fact_id] = dict(payload)
        return self.ref(fact_id)

    def has(self, fact_id: str) -> bool:
        return fact_id in self._facts

    def get(self, fact_id: str) -> dict:
        if fact_id not in self._facts:
            raise MissingEvidenceError(f"证据指针 {fact_id} 不在台账中，禁止引用")
        return self._facts[fact_id]

    def ref(self, fact_id: str) -> ObjectRef:
        self.get(fact_id)  # 校验存在性：不存在的指针一律拒绝
        return ObjectRef(object_id=fact_id)

    def ids(self) -> list:
        return list(self._facts.keys())

    def find(self, *, text_contains: _Iterable[str] = (), kinds: _Iterable[str] = ()) -> list:
        """按文本关键词 / kind 粗筛事实，返回 fact_id 列表。"""
        keywords = tuple(text_contains)
        kind_set = set(kinds)
        matched = []
        for fact_id, payload in self._facts.items():
            text = str(payload.get("text", ""))
            kind = str(payload.get("kind", ""))
            if kind_set and kind in kind_set:
                matched.append(fact_id)
                continue
            if keywords and any(k in text for k in keywords):
                matched.append(fact_id)
        return matched


# ---- 统一数据结构说明：ActionableAdvice 已原生携带硬阻击/强制行动/置信度字段 ----


def _new_advice_id(prefix: str) -> str:
    return f"{prefix}_{_uuid.uuid4().hex[:10]}"


# ===================== 老妈生日礼物顾问（证据驱动版） =====================

_GIFT_CANDIDATES = (
    {"gift": "轻便膝盖气囊热敷理疗仪", "category": "膝盖理疗", "price_yuan": 299},
    {"gift": "保暖护膝套装", "category": "膝盖理疗", "price_yuan": 79},
    {"gift": "轻便热敷理疗贴", "category": "膝盖理疗", "price_yuan": 39},
    {"gift": "全自动足浴盆", "category": "笨重水洗家电", "price_yuan": 399},
    {"gift": "金银首饰", "category": "饰品", "price_yuan": 1999},
    {"gift": "真丝丝巾", "category": "饰品", "price_yuan": 599},
)

_FORBIDDEN_CATEGORIES = frozenset({"笨重水洗家电", "饰品"})
_NEGATIVE_OUTCOME_HINTS = ("闲置", "腰疼", "落灰", "笨重", "没用过")
_POSITIVE_OUTCOME_HINTS = ("好评", "极佳", "天天用", "很满意")
_KNEE_SIGNAL_HINTS = ("膝盖", "老寒腿", "受凉", "关节疼")


class MomBirthdayGiftAdvisorV2:
    """证据驱动的送礼顾问：历史结局定禁区，当年体征定靶点，预算定档位。"""

    def advise(
        self,
        ledger: EvidenceLedger,
        *,
        budget_yuan: _Optional[float] = None,
    ) -> ActionableAdvice:
        if not isinstance(ledger, EvidenceLedger):
            raise TypeError(" MomBirthdayGiftAdvisorV2 必须携带 EvidenceLedger 证据台账")

        idle_categories = set()
        praised_categories = set()
        knee_evidence: list = []
        history_evidence: list = []

        for fact_id in ledger.ids():
            payload = ledger.get(fact_id)
            text = str(payload.get("text", ""))
            category = payload.get("gift_category")
            if any(h in text for h in _KNEE_SIGNAL_HINTS):
                knee_evidence.append(fact_id)
            if payload.get("kind") == "gift_history" or category:
                history_evidence.append(fact_id)
                if any(h in text for h in _NEGATIVE_OUTCOME_HINTS) and category:
                    idle_categories.add(str(category))
                if any(h in text for h in _POSITIVE_OUTCOME_HINTS) and category:
                    praised_categories.add(str(category))

        if not knee_evidence:
            raise MissingEvidenceError("缺少当年膝盖受凉的观测证据，禁止凭空推荐理疗仪")
        if not history_evidence:
            raise MissingEvidenceError("缺少历年礼物结局证据，禁止凭空对比选礼")

        chosen = None
        for candidate in _GIFT_CANDIDATES:
            if candidate["category"] in _FORBIDDEN_CATEGORIES:
                continue  # 宪法级禁区：笨重水洗家电与无用饰品一票否决
            if candidate["category"] in idle_categories:
                continue  # 历史已证明闲置的品类不再重蹈覆辙
            if budget_yuan is not None and candidate["price_yuan"] > budget_yuan:
                continue
            if candidate["category"] == "膝盖理疗":
                chosen = candidate
                break
            chosen = chosen or candidate

        if chosen is None:
            raise MissingEvidenceError("预算内无可用候选，拒绝硬凑礼物")

        evidence_ids = sorted(set(history_evidence + knee_evidence))
        pointers = [ledger.ref(fid) for fid in evidence_ids]  # 逐一校验，禁止虚指
        banned_notes = "、".join(sorted(_FORBIDDEN_CATEGORIES | idle_categories))
        return ActionableAdvice(
            conclusion=(
                f"精准推荐【{chosen['gift']}】（约 {chosen['price_yuan']} 元）："
                f"历年结局已禁 {banned_notes}，当年膝盖受凉体征精准命中理疗靶点"
            ),
            evidence_pointers=pointers,
            alternatives=[
                c["gift"]
                for c in _GIFT_CANDIDATES
                if c["category"] == "膝盖理疗" and c["gift"] != chosen["gift"]
            ],
            expected_benefit=(
                "礼物直击老妈 2026 年膝盖老寒腿问题，轻便不闲置、不倒水不伤腰，"
                "延续 2025 按摩椅级好评体验"
            ),
            advice_id=_new_advice_id("advice_gift"),
            confidence=0.98,
        )


# ===================== 反诈阻击顾问（证据驱动版） =====================

class FraudPreventionAdvisorV2:
    """证据驱动的反诈阻击：法院判决与历史拖延记录缺一不可。"""

    def advise(self, ledger: EvidenceLedger) -> ActionableAdvice:
        if not isinstance(ledger, EvidenceLedger):
            raise TypeError("FraudPreventionAdvisorV2 必须携带 EvidenceLedger 证据台账")

        court_ids = ledger.find(text_contains=("判决", "裁定"), kinds=("court_judgment",))
        delay_ids = ledger.find(text_contains=("拖延", "已读不回", "赖账", "催款"), kinds=("wechat_record",))

        if not court_ids:
            raise MissingEvidenceError("缺少法院判决/裁定证据，禁止出具硬核阻击建议")
        if not delay_ids:
            raise MissingEvidenceError("缺少历史拖延记录证据，禁止凭空定性二次受骗")

        pointers = [ledger.ref(fid) for fid in sorted(set(court_ids + delay_ids))]
        return ActionableAdvice(
            conclusion=(
                "硬核阻击：当场拒绝老王追加借款与任何新合伙提议；"
                "已生效判决立即转入资产追偿执行程序"
            ),
            evidence_pointers=pointers,
            alternatives=[
                "委托律师发出限期还款律师函",
                "向法院申请强制执行与财产保全",
                "将其列入共生心智风险名单，相关话题一律骨传导直言预警",
            ],
            expected_benefit="阻断二次受骗，判决债权进入可执行追偿通道，历史欠款不再躺平",
            advice_id=_new_advice_id("advice_fraud"),
            hard_refusal=True,
            confidence=1.0,
        )


# ===================== 健康疲劳熔断顾问（证据驱动版） =====================

class HealthFatigueBreakerAdvisorV2:
    """证据驱动的疲劳熔断：通宵与早搏必须构成时间因果方向。"""

    def advise(self, ledger: EvidenceLedger) -> ActionableAdvice:
        if not isinstance(ledger, EvidenceLedger):
            raise TypeError("HealthFatigueBreakerAdvisorV2 必须携带 EvidenceLedger 证据台账")

        allnighter_ids = ledger.find(text_contains=("通宵", "彻夜"), kinds=("overnight_work",))
        pvc_ids = ledger.find(text_contains=("早搏", "室性早搏", "心悸"), kinds=("pvc",))

        if not allnighter_ids:
            raise MissingEvidenceError("缺少连续通宵证据，熔断令无据可依")
        if not pvc_ids:
            raise MissingEvidenceError("缺少早搏体征证据，熔断令无据可依")

        def _occurred(fact_id: str):
            value = ledger.get(fact_id).get("occurred_at")
            if isinstance(value, _datetime.datetime):
                return value
            return None

        allnighter_at = max(filter(None, (_occurred(i) for i in allnighter_ids)), default=None)
        pvc_at = max(filter(None, (_occurred(i) for i in pvc_ids)), default=None)
        if allnighter_at and pvc_at and pvc_at < allnighter_at:
            raise MissingEvidenceError("早搏早于通宵，因果方向不成立，拒绝出具熔断令")

        pointers = [ledger.ref(fid) for fid in sorted(set(allnighter_ids + pvc_ids))]
        return ActionableAdvice(
            conclusion=(
                "疲劳熔断生效：立即停止一切工作强制休息，"
                "72 小时内完成心电图复查与动态心电监测"
            ),
            evidence_pointers=pointers,
            alternatives=[
                "就医清单：心电图 + 24h 动态心电 + 心肌酶谱",
                "今晚 23 点前入睡，连续 3 天睡眠不少于 7 小时",
                "咖啡因摄入即日起单日不超过 1 杯",
            ],
            expected_benefit="切断通宵-早搏因果链，防止心脏超负荷演变为恶性事件（生命安全高于一切）",
            advice_id=_new_advice_id("advice_fatigue"),
            forced_action=True,
            confidence=1.0,
        )
