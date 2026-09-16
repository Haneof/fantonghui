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
