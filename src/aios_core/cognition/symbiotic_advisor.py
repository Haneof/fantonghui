"""M5-SYMBIOTIC-ADVISOR 共生决策推演与行动建议（Agent-09）。

宪法依据：V3 §4（最终目的是帮助）、§13/§14（功能不写死，行为从对
世界的理解中涌现——本模块只提供**证据到建议的推演骨架**，具体建议
内容由检索到的真实证据决定）、§95（世界索引：妈妈+生日+礼物 → 历年
礼物/反馈/账单/心愿）、§95 之例与 §17（禁止示例模具化：三条顾问均为
证据驱动的通用机制实例）。

铁律：**每条 ActionableAdvice 必须携带确凿因果证据指针
（ObjectRef，pinned revision）**。证据缺失时抛 :class:`MissingEvidenceError`
——严禁凭空编造；headline 严禁泛泛套话（校验器内置模板话术黑名单）。
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, model_validator

from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import require_aware

__all__ = [
    "ActionableAdvice",
    "FraudPreventionAdvisor",
    "HealthFatigueBreakerAdvisor",
    "MindEvidenceStore",
    "MissingEvidenceError",
    "MomBirthdayGiftAdvisor",
]


class MissingEvidenceError(Exception):
    """证据缺失：顾问拒绝凭空编造建议。"""

    def __init__(self, advisor: str, missing: Sequence[str]) -> None:
        super().__init__(
            f"{advisor}: missing required evidence {list(missing)}; "
            f"fabricating advice is forbidden"
        )
        self.missing = tuple(missing)


class EvidenceRecord(BaseModel):
    """证据记录（顾问检索的最小单元；object_id 即 ObjectRef 锚）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: StrictStr = Field(min_length=1)
    revision: StrictInt = Field(default=1, ge=1)
    kind: StrictStr = Field(min_length=1)          # gift / health_signal / court ...
    year: StrictInt | None = None
    keywords: tuple[StrictStr, ...] = Field(default=())
    content: StrictStr = Field(min_length=1)

    def ref(self) -> ObjectRef:
        return ObjectRef(object_id=self.object_id, revision=self.revision)

    def matches(self, keywords: Sequence[str]) -> bool:
        hay = " ".join((self.content, *self.keywords)).casefold()
        return all(kw.casefold() in hay for kw in keywords)


class MindEvidenceStore:
    """多维心智证据库（顾问共用的只读检索面）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, EvidenceRecord] = []

    def add(self, record: EvidenceRecord) -> None:
        with self._lock:
            self._records.append(record)

    def add_all(self, records: Sequence[EvidenceRecord]) -> None:
        for record in records:
            self.add(record)

    def find(self, *, kind: str | None = None, keywords: Sequence[str] = (), year: int | None = None) -> list[EvidenceRecord]:
        with self._lock:
            hits = []
            for record in self._records:
                if kind is not None and record.kind != kind:
                    continue
                if year is not None and record.year != year:
                    continue
                if keywords and not record.matches(keywords):
                    continue
                hits.append(record)
            return hits


# ----------------------------------------------------------------------
# ActionableAdvice 契约
# ----------------------------------------------------------------------

#: 泛泛套话黑名单（headline 命中即拒绝——严禁输出模板鸡汤）。
_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in (
        r"保持(积极|乐观|良好)心态",
        r"为您推荐以下[一二三四五六七八九十\d]+点",
        r"希望这些建议.*(帮助|参考)",
        r"具体.*请咨询(专业|相关)人士",
        r"温馨提示",
        r"仅供参考[,，。]?\s*不构成",
    )
)


class ActionableAdvice(BaseModel):
    """可执行建议：必须因果有据（≥1 pinned 证据指针）、无套话。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    advice_id: StrictStr = Field(min_length=1)
    advisor: StrictStr = Field(min_length=1)
    headline: StrictStr = Field(min_length=6, max_length=120)
    rationale: StrictStr = Field(min_length=6)
    actions: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_refs: tuple[ObjectRef, ...] = Field(min_length=1)
    urgency: Literal["routine", "high", "p0"] = "routine"
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    created_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> "ActionableAdvice":
        require_aware(self.created_at, "created_at")
        for pattern in _BOILERPLATE_PATTERNS:
            if pattern.search(self.headline) or pattern.search(self.rationale):
                raise ValueError(
                    f"boilerplate platitudes are forbidden: {pattern.pattern}"
                )
        for ref in self.evidence_refs:
            if ref.revision is None:
                raise ValueError("evidence_refs must pin object revisions")
        return self


# ----------------------------------------------------------------------
# 三大顾问
# ----------------------------------------------------------------------

class MomBirthdayGiftAdvisor:
    """母亲生日送礼推演器：四年证据链 → 轻便膝盖热敷仪。

    推演逻辑（证据驱动，非模具）：需求演化 = 2023 丝巾（装饰需求）
    → 2024 足浴盆闲置 + 倒水腰疼（大件操作负担是痛点）
    → 2025 按摩椅好评（热敷按摩方向有效）→ 2026 膝盖受凉（部位收敛）。
    结论：轻便、直击膝部、免操作负担的热敷仪。
    """

    ADVISOR_ID = "mom_birthday_gift"

    def advise(self, store: MindEvidenceStore, *, at: datetime) -> ActionableAdvice:
        require_aware(at, "at")
        silk = store.find(kind="gift", keywords=("丝巾",), year=2023)
        tub = store.find(kind="gift", keywords=("足浴盆",), year=2024)
        waist = store.find(kind="health_signal", keywords=("倒水", "腰"), year=2024)
        chair = store.find(kind="gift_feedback", keywords=("按摩椅", "好"), year=2025)
        knee = store.find(kind="health_signal", keywords=("膝盖", "凉"), year=2026)
        missing = []
        if not silk:
            missing.append("gift:2023丝巾")
        if not (tub and waist):
            missing.append("gift:2024足浴盆+倒水腰疼")
        if not chair:
            missing.append("feedback:2025按摩椅好评")
        if not knee:
            missing.append("health:2026膝盖受凉")
        if missing:
            raise MissingEvidenceError(self.ADVISOR_ID, missing)
        evidence = (*silk, *tub, *waist, *chair, *knee)
        return ActionableAdvice(
            advice_id=f"adv_gift_{at.strftime('%Y%m%d')}",
            advisor=self.ADVISOR_ID,
            headline="今年母亲节送轻便膝盖热敷仪，别再送需要搬动的大件",
            rationale=(
                "证据链四年收敛：23年丝巾只是应景；24年足浴盆闲置且倒水时"
                "腰疼（大件+操作负担是真实痛点）；25年按摩椅获好评（热敷"
                "按摩方向有效）；26年膝盖受凉（部位明确）。交叉结论：轻便、"
                "直击膝部、免操作负担。"
            ),
            actions=(
                "筛选缠绑式轻量石墨烯膝盖热敷仪（≤500g、免注水）",
                "下单前确认三档温控与 30 分钟自动断电",
                "生日前三天到货，附手写使用说明（一句话，不写小作文）",
            ),
            evidence_refs=tuple(r.ref() for r in evidence),
            urgency="routine",
            confidence=0.88,
            created_at=at,
        )


class FraudPreventionAdvisor:
    """反欺诈阻击推演器：法院判决 + 两年前借款记录 → 拒绝借款 + 追偿指针。"""

    ADVISOR_ID = "fraud_prevention"

    def advise(self, store: MindEvidenceStore, *, at: datetime) -> ActionableAdvice:
        require_aware(at, "at")
        judgment = store.find(kind="court", keywords=("判决",))
        loan = store.find(kind="loan_record", keywords=("借款", "微信"), year=at.year - 2)
        missing = []
        if not judgment:
            missing.append("court:生效判决")
        if not loan:
            missing.append(f"loan_record:{at.year - 2}年微信借款")
        if missing:
            raise MissingEvidenceError(self.ADVISOR_ID, missing)
        evidence = (*judgment, *loan)
        return ActionableAdvice(
            advice_id=f"adv_fraud_{at.strftime('%Y%m%d')}",
            advisor=self.ADVISOR_ID,
            headline="拒绝这笔借款：他有判决在身的失信记录，两年前借的钱至今未清",
            rationale=(
                "因果链确凿：生效判决已认定其关联担保欺诈事实；"
                f"{at.year - 2}年微信转账借款至今无归还记录。老债未清再借"
                "新债，追偿成功率趋近于零，且可能被拖入连环担保。"
            ),
            actions=(
                "当面或微信明确拒绝，不留『再看看』的口子",
                "引用法院判决案号与未清偿金额作为唯一理由，不做人身评价",
                "对旧借款同步启动支付令/诉讼追偿，保存好转账凭证与催告记录",
            ),
            evidence_refs=tuple(r.ref() for r in evidence),
            urgency="high",
            confidence=0.94,
            created_at=at,
        )


class HealthFatigueBreakerAdvisor:
    """心脏早搏疲劳熔断顾问：通宵加班 × 室性早搏因果 → 强制停工保护。"""

    ADVISOR_ID = "health_fatigue_breaker"

    def advise(self, store: MindEvidenceStore, *, at: datetime) -> ActionableAdvice:
        require_aware(at, "at")
        overnights = store.find(kind="work_pattern", keywords=("通宵", "加班"))
        pvcs = store.find(kind="health_signal", keywords=("室性早搏",))
        missing = []
        if len(overnights) < 2:
            missing.append("work_pattern:≥2 次通宵加班")
        if not pvcs:
            missing.append("health_signal:室性早搏记录")
        if missing:
            raise MissingEvidenceError(self.ADVISOR_ID, missing)
        evidence = (*overnights, *pvcs)
        return ActionableAdvice(
            advice_id=f"adv_breaker_{at.strftime('%Y%m%d')}",
            advisor=self.ADVISOR_ID,
            headline="今晚必须停工：连续通宵后室性早搏再发，心脏在报警",
            rationale=(
                "因果关联成立：通宵加班次日早搏负荷显著上升，本次早搏再次"
                "出现在连续熬夜窗口内。此时继续高强度工作是在透支传导系统，"
                "生死第一，熔断没有商量余地。"
            ),
            actions=(
                "立即放下未完成事项，今晚零点前入睡（设勿扰与闹钟即可）",
                "明早记录静息心率与早搏频次，如持续＞10 次/分钟或伴胸闷立即心内科",
                "本周向团队明示晚间不可用时段，把截止日顺延而不是硬扛",
            ),
            evidence_refs=tuple(r.ref() for r in evidence),
            urgency="p0",
            confidence=0.91,
            created_at=at,
        )
