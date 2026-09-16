# -*- M5 志愿对照跑道（volunteer lane）：与 mainline 同名交付并存，互不覆盖，合并时另行仲裁。 -*-
"""M5-004 共生顾问三台（工单 #9，铁律：输出质量绝对第一）。

  MomBirthdayGiftAdvisor —— 四年礼物因果账：
      2023 丝巾落灰 / 2024 足浴盆倒水腰疼闲置 / 2025 按摩椅极佳 /
      2026 膝盖受凉 → 排除足浴盆与饰品类，命中轻便膝盖气囊热敷理疗仪；
  FraudPreventionAdvisor —— 朝阳法院判决 + 微信拖延切片 →
      硬核阻击 + 资产追偿路径；
  HealthFatigueBreakerAdvisor —— 周四连续通宵 + 室性早搏 →
      疲劳熔断 + 心电图复查行动清单。

  ActionableAdvice 硬门（构造即校验，泛泛套话出不了舱）：
    ① 每个结论必携因果证据 ObjectRef 清单（≥1）；
    ② 禁泛泛套话（"多喝热水/注意休息/保重身体/早点睡觉…"一律拒收）；
    ③ 必给备选与预期收益，把因果链摆在结论前头。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# 通用武器库：ActionableAdvice（构造即过质检）
# ---------------------------------------------------------------------------

# 泛泛套话黑名单（治理件：收录走变更）
_GENERIC_PHRASES: tuple[str, ...] = (
    "多喝热水", "注意休息", "保重身体", "早点睡觉", "适量运动",
    "保持好心情", "放宽心态", "注意身体", "好好休息",
)


@dataclass(slots=True, frozen=True)
class EvidenceRef:
    object_id: str
    revision: int
    why: str                       # 这条证据在因果链里顶哪一环

    def as_ref(self) -> dict[str, Any]:
        return {"object_id": self.object_id, "revision": self.revision}


@dataclass(slots=True, frozen=True)
class Alternative:
    option: str
    why_second: str                # 为什么是备选而不是首选


@dataclass(slots=True, frozen=True)
class ActionableAdvice:
    advisor_id: str
    conclusion: str
    evidence: tuple[EvidenceRef, ...]
    alternatives: tuple[Alternative, ...]
    expected_benefit: str
    causal_chain: str              # 因果链摆在结论前头（证据 → 推理 → 建议）

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError(f"{self.advisor_id}: 结论无证据，拒收")
        for phrase in _GENERIC_PHRASES:
            if phrase in self.conclusion or phrase in self.expected_benefit:
                raise ValueError(
                    f"{self.advisor_id}: 泛泛套话『{phrase}』禁止出舱"
                )
        if not self.alternatives:
            raise ValueError(f"{self.advisor_id}: 无备选，独断建议不可交付")


# ---------------------------------------------------------------------------
# ① 母亲生日礼物顾问
# ---------------------------------------------------------------------------


class FeedbackTone(str, Enum):
    PRISTINE_DUSTY = "PRISTINE_DUSTY"      # 全新落灰：没进过生活
    PAIN_TO_USE = "PAIN_TO_USE"            # 用起来费劲/腰疼
    BELOVED = "BELOVED"                    # 极佳，天天用


@dataclass(slots=True, frozen=True)
class GiftHistoryRecord:
    year: int
    gift: str
    category: str                          # accessory|foot_bath|massage|health_care|...
    feedback: FeedbackTone
    detail: str
    ref: EvidenceRef


@dataclass(slots=True, frozen=True)
class MomSignal:
    detail: str                            # 当前身体信号（"最近膝盖受凉，上下楼费力"）
    ref: EvidenceRef


@dataclass(slots=True, frozen=True)
class GiftCandidate:
    name: str
    category: str
    targets: tuple[str, ...]               # 它对症的身体诉求关键词


# 目录（治理件）：候选池不临场杜撰
_GIFT_CATALOG: tuple[GiftCandidate, ...] = (
    GiftCandidate("轻便膝盖气囊热敷理疗仪", "health_care",
                  ("膝盖", "受凉", "上下楼", "关节")),
    GiftCandidate("全包裹足膝两用按摩舱", "health_care_combine",
                  ("膝盖", "足", "关节")),
    GiftCandidate("珍珠项链", "accessory", ()),
    GiftCandidate("全自动足浴盆", "foot_bath", ("足",)),
    GiftCandidate("加热护膝围巾套装", "wearable_warm", ("膝盖", "受凉")),
)


class MomBirthdayGiftAdvisor:
    """礼物建议的铁律：今年的账记着去年的教训，更记着妈上周说腿疼。"""

    def __init__(self, catalog: Sequence[GiftCandidate] | None = None) -> None:
        self._catalog = tuple(catalog or _GIFT_CATALOG)

    def advise(self, history: Sequence[GiftHistoryRecord],
               signal: MomSignal) -> ActionableAdvice:
        bad_categories = {
            r.category for r in history
            if r.feedback in (FeedbackTone.PRISTINE_DUSTY, FeedbackTone.PAIN_TO_USE)
        }
        evidence: list[EvidenceRef] = [r.ref for r in history]
        evidence.append(signal.ref)
        # 对症评分：信号关键词命中 targets ⇒ 加分；落灰品类 ⇒ 淘汰
        scored: list[tuple[int, GiftCandidate]] = []
        for c in self._catalog:
            if c.category in bad_categories:
                continue
            score = sum(1 for t in c.targets if t in signal.detail)
            if score > 0:
                scored.append((score, c))
        if not scored:
            raise RuntimeError("目录内无可交付候选：不许临场杜撰礼物")
        scored.sort(key=lambda sc: (-sc[0], sc[1].name))
        best_score, best = scored[0]

        excluded = [r for r in history
                    if r.feedback in (FeedbackTone.PRISTINE_DUSTY,
                                      FeedbackTone.PAIN_TO_USE)]
        causal = (
            "因果链：" + "；".join(
                f"{r.year} {r.gift}→{r.detail}" for r in history
            ) + f"；当下信号：{signal.detail}"
            f" ⇒ 排除品类 {sorted(bad_categories)}，对症命中度 {best_score}"
        )
        year = max((r.year for r in history), default=2025) + 1
        conclusion = (
            f"{year} 母亲生日礼物首选【{best.name}】——"
            f"对准『{signal.detail}』这个当下最怕的部位；"
            + "、".join(f"{r.gift}（{r.detail}）" for r in excluded)
            + " 这类已被生活否决的礼物绝不再送"
        )
        alternatives = tuple(
            Alternative(c.name, f"对症命中 {s} 环，次于首选 {best_score} 环")
            for s, c in scored[1:3]
        ) or (Alternative("手作膝枕", "目录外兜底：亲手做的不进落灰统计"),)
        benefit = (
            "膝盖直接受热镇痛、按摩椅品类已被 2025 年验证为日日用；"
            "失败成本历史最高价：一台落灰的电器 + 一位腰疼的长辈"
        )
        return ActionableAdvice(
            advisor_id="advisor.mom_birthday_gift",
            conclusion=conclusion,
            evidence=tuple(evidence),
            alternatives=alternatives,
            expected_benefit=benefit,
            causal_chain=causal,
        )


# ---------------------------------------------------------------------------
# ② 防诈阻击顾问
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class CourtJudgment:
    court: str          # "北京市朝阳区人民法院"
    case_no: str
    holding: str        # 判旨摘要
    ref: EvidenceRef


@dataclass(slots=True, frozen=True)
class WechatStallSlice:
    at: str             # ISO 时间
    excerpt: str        # 拖延话术切片
    ref: EvidenceRef


class FraudPreventionAdvisor:
    """判决书与拖延切片锁在一起时，任何『再借一次』都是给骗局充值。"""

    STALL_MARKERS = ("下周", "过两天", "在凑", "马上", "工程款", "回不了", "缓缓")

    def advise(self, debtor: str, ask_amount: float,
               judgments: Sequence[CourtJudgment],
               slices: Sequence[WechatStallSlice]) -> ActionableAdvice:
        if not judgments:
            raise RuntimeError("无判决书坐镇：阻击火力不足，先补证据")
        stall_hits = [s for s in slices
                      if any(m in s.excerpt for m in self.STALL_MARKERS)]
        if not stall_hits:
            raise RuntimeError("无拖延切片：诈骗模式未坐实，先取证再阻击")
        j = judgments[0]
        chain = (
            f"因果链：{j.court}{j.case_no} 判旨『{j.holding}』"
            f" + {len(stall_hits)} 条拖延切片（首条『{stall_hits[0].excerpt[:20]}…』）"
            f" ⇒ 偿债意愿为零且套路程序化 ⇒ 本笔 {ask_amount:,.0f} 元老信息量"
        )
        conclusion = (
            f"对 {debtor} 的 {ask_amount:,.0f} 元追加借款请求硬核阻击：一分不出；"
            f"同步以 {j.case_no} 判旨启动资产追偿 —— 收集现有借据、转账流水、"
            f"微信拖延切片，48 小时内整理成卷送执行线索窗口"
        )
        evidence = [j.ref for j in judgments] + [s.ref for s in stall_hits]
        return ActionableAdvice(
            advisor_id="advisor.fraud_prevention",
            conclusion=conclusion,
            evidence=tuple(evidence),
            alternatives=(
                Alternative(
                    "垫资上限锁零 + 书面借款协议",
                    "若情谊难拒（如老友）——必须载明抵押与执行条款，口头承诺已证伪",
                ),
                Alternative(
                    "引入共同熟人见证的还款计划",
                    "把『下周还』变成三方见证的时间表，拖延话术无处藏身",
                ),
            ),
            expected_benefit=(
                f"止损 {ask_amount:,.0f} 元；旧债进入司法追偿通道，"
                "拖延话术从‘嘴上说’转成‘卷宗里’的证据"
            ),
            causal_chain=chain,
        )


# ---------------------------------------------------------------------------
# ③ 健康疲劳熔断顾问
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class FatigueSignal:
    consecutive_all_nighters: int          # 连续通宵夜数
    premature_ventricular_beats: bool      # 室性早搏
    latest_ecg_days_ago: int | None        # 最近心电图距今天数（None = 从未）
    ref: EvidenceRef


class HealthFatigueBreakerAdvisor:
    """通宵连击叠加室早：现在谈的不是效率，是今晚别出事。"""

    FUSE_THRESHOLD_NIGHTS = 2              # ≥2 接连通宵即熔断
    PVC_ESCALATION = True

    def advise(self, signal: FatigueSignal) -> ActionableAdvice:
        if signal.consecutive_all_nighters < self.FUSE_THRESHOLD_NIGHTS:
            raise RuntimeError(
                f"连通宵 {signal.consecutive_all_nighters} 夜未达熔断线 "
                f"{self.FUSE_THRESHOLD_NIGHTS}：熔断器不误触发"
            )
        pvc = signal.premature_ventricular_beats
        ecg_gap = ("从未做过心电图" if signal.latest_ecg_days_ago is None
                   else f"心电图已 {signal.latest_ecg_days_ago} 天未查")
        chain = (
            f"因果链：连续通宵 {signal.consecutive_all_nighters} 夜"
            f" + 室性早搏={pvc} + {ecg_gap}"
            " ⇒ 交感风暴叠心脏电活动异常，猝死风险窗口已开"
        )
        checklist = (
            "① 即刻触发疲劳熔断：今晚 22:00 前停止一切工作流，设备进入勿扰；"
            "② 明早三甲医院心内科门诊，点名做 24 小时动态心电图（Holter）与电解质；"
            "③ 今明两天咖啡因清零、禁酒，早搏再发立即拨打 120 不带犹豫；"
            "④ 把近 7 日睡眠-心率曲线导出给医生（设备里有，别靠嘴说）"
        )
        conclusion = (
            f"疲劳熔断激活：连续通宵 {signal.consecutive_all_nighters} 夜叠"
            f"{'加' if pvc else '上'}室性早搏信号 + {ecg_gap}。"
            f"行动清单：{checklist}"
        )
        return ActionableAdvice(
            advisor_id="advisor.health_fatigue_breaker",
            conclusion=conclusion,
            evidence=(signal.ref,),
            alternatives=(
                Alternative(
                    "明晚再补觉",
                    "室早不是闹钟——今晚不复位，明早可能没机会复位",
                ),
                Alternative(
                    "先减半工作量过渡",
                    "心脏电活动异常不认谈判；过渡方案仅限未出现早搏时",
                ),
            ),
            expected_benefit=(
                "把猝死风险窗口在 24 小时内关小：Holter 数据落卷后，"
                "后续每夜心率异常的判读有了临床基线"
            ),
            causal_chain=chain,
        )


__all__ = [
    "ActionableAdvice",
    "Alternative",
    "CourtJudgment",
    "EvidenceRef",
    "FatigueSignal",
    "FeedbackTone",
    "FraudPreventionAdvisor",
    "GiftCandidate",
    "GiftHistoryRecord",
    "HealthFatigueBreakerAdvisor",
    "MomBirthdayGiftAdvisor",
    "MomSignal",
    "WechatStallSlice",
]
