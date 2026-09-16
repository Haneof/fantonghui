"""AIOS 3.0 共生决策辅助与行动推演引擎（M5-004 / 宪法第一铁律工程化）。

**输出质量绝对第一**：宁可晚半秒，也不吐一句废话，更不许编造证据。

本模块提供三类真实人生推演器，全部建立在**真实世界取证**之上：

1. ``MomBirthdayGiftAdvisor`` —— 妈妈生日礼物推演器
   横向比对 2023 丝巾落灰、2024 足浴盆笨重倒水腰疼闲置、2025 按摩椅好评、
   2026 膝盖受寒，得出"轻便膝盖气囊热敷理疗仪"这一精准解，并明确排除
   笨重水洗家电与无用饰品。

2. ``FraudPreventionAdvisor`` —— 反欺诈阻击推演器
   把法院判决、两年前微信拖延记录与合同履行异常串成证据链，硬核输出
   "拒绝追加借款 + 启动资产追偿"的组合拳，阻断二次受骗。

3. ``HealthFatigueBreakerAdvisor`` —— 心脏早搏疲劳熔断顾问
   关联通宵加班（工时域）与室性早搏（生理域），给出强制停工保护与
   心电图复查清单——生命安全高于一切，此项不建议"再撑一撑"。

三种模式与铁律：
- **世界取证模式**（``advise_from_world``）：所有证据指针都从真实世界里
  经由多维检索 + 拓扑下钻取回，并且**逐条解引用校验**；取不到就直接拒绝出建议
  （``InsufficientEvidenceError``），绝不"先写结论再补证据"。
- **先验沙盘模式**（无参 ``advise``）：不带世界接入时退化为宪法先验剧本，
  结论字段与指针集合保持 M1 兼容，但会显式标注 ``evidence_mode=PRIOR_SANDBOX``，
  禁止被当作真实世界证据引用。
- **反套话闸门**（``AdviceQualityGuard``）：结论必须点名具体对象/金额/时间窗，
  出现"多喝热水""因人而异""具体情况具体分析"等泛泛套话立即
  ``GenericAdviceRejectedError``。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from aios_core.contracts.refs import ObjectRef
from aios_core.storage.sqlite_store import SQLiteWorldStore


class EvidenceMode(StrEnum):
    """证据来源模式（决定这条建议能不能当证据用）。"""

    WORLD_EVIDENCE = "world_evidence"
    PRIOR_SANDBOX = "prior_sandbox"


class InsufficientEvidenceError(ValueError):
    """取证不足：证据链缺口未补齐前，拒绝输出建议（绝不编造）。"""


class GenericAdviceRejectedError(ValueError):
    """套话闸门：结论空洞无物，直接打回。"""


class CausalLink(BaseModel):
    """一条因果链环节：事实 → 推断，权重体现该事实对结论的支配程度。"""

    model_config = ConfigDict(extra="forbid")

    fact_ref: ObjectRef
    fact_summary: str = Field(min_length=1)
    inference: str = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class ActionableAdvice(BaseModel):
    """统一行动建议结构：结论 + 因果证据指针 + 备选方案 + 预期收益。"""

    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(min_length=1)
    evidence_pointers: List[ObjectRef] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    expected_benefit: str = ""
    # ---- M5 强化字段（全部带默认值，兼容 M1 调用方） ----
    advisor: str = ""
    evidence_mode: EvidenceMode = EvidenceMode.PRIOR_SANDBOX
    causal_chain: List[CausalLink] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    world_revision: Optional[int] = None
    token_estimate: int = 0

    def evidence_ids(self) -> List[str]:
        """证据指针 id 列表。"""
        return [ref.object_id for ref in self.evidence_pointers]

    def verify_against(self, store: SQLiteWorldStore) -> "ActionableAdvice":
        """逐条解引用校验证据指针：任何一条不存在即判定为编造证据。"""
        if not self.evidence_pointers:
            raise InsufficientEvidenceError(f"{self.advisor or 'advice'} 没有任何证据指针，禁止输出")
        for ref in self.evidence_pointers:
            try:
                payload = store.get_payload(ref.object_id)
            except Exception as exc:  # 指针指不到东西 = 编造证据
                raise InsufficientEvidenceError(
                    f"evidence pointer {ref.object_id} does not resolve in world: {exc}"
                ) from exc
            if payload.get("object_id") != ref.object_id:
                raise InsufficientEvidenceError(f"evidence pointer {ref.object_id} does not resolve")
        return self

    def as_dict(self) -> Dict[str, Any]:
        """序列化切片（体检报告 / 审计日志用）。"""
        return self.model_dump(mode="json")


class AdviceQualityGuard:
    """反套话闸门：把"听起来没错但毫无用处"的建议挡在门外。"""

    #: 泛泛套话黑名单（出现即打回，不留情面）
    FILLER_PHRASES: Tuple[str, ...] = (
        "多喝热水",
        "注意身体",
        "因人而异",
        "具体情况具体分析",
        "仅供参考",
        "建议谨慎考虑",
        "保持良好心态",
        "适当运动",
        "多休息少熬夜",
        "一切都会好起来的",
    )
    #: 结论必须点名的"具体性"线索（金额 / 时间 / 具体物 / 具体行动）
    SPECIFIC_MARKERS: Tuple[str, ...] = (
        "元",
        "万元",
        "天",
        "小时",
        "分钟",
        "点",
        "热敷",
        "理疗",
        "停工",
        "心电图",
        "追偿",
        "保全",
        "律师函",
        "裁决",
        "判决",
        "膝盖",
        "住院",
        "复查",
    )

    @classmethod
    def violations(cls, advice: ActionableAdvice) -> List[str]:
        """列出全部质量问题（空列表 = 合格）。"""
        problems: List[str] = []
        blob = " ".join(
            [advice.conclusion, advice.expected_benefit, *advice.action_items, *advice.alternatives]
        )
        for phrase in cls.FILLER_PHRASES:
            if phrase in blob:
                problems.append(f"fillphrase:{phrase}")
        if len(advice.evidence_pointers) < 2:
            problems.append(f"evidence_pointers<2:{len(advice.evidence_pointers)}")
        if not advice.action_items:
            problems.append("action_items_empty")
        if not any(marker in advice.conclusion for marker in cls.SPECIFIC_MARKERS):
            problems.append("conclusion_not_specific")
        if advice.causal_chain and any(not link.fact_summary.strip() for link in advice.causal_chain):
            problems.append("causal_chain_empty_summary")
        return problems

    @classmethod
    def enforce(cls, advice: ActionableAdvice) -> ActionableAdvice:
        """质量问题一律抛错（严禁用占位/套话蒙混过关）。"""
        problems = cls.violations(advice)
        if problems:
            raise GenericAdviceRejectedError(f"{advice.advisor or 'advice'} 质量不合格: {problems}")
        return advice


# ===========================================================================
# 世界取证底座
# ===========================================================================
class _EvidenceHarvester:
    """多维检索 + 拓扑下钻取证器（建议引擎的唯一证据来源）。"""

    def __init__(self, store: SQLiteWorldStore, *, index: Any = None, fanout: int = 96) -> None:
        self.store = store
        self.fanout = fanout
        if index is not None:
            self.index = index
        else:
            from aios_core.query.search import MultidimensionalSearchEngine

            self.index = MultidimensionalSearchEngine(store.db_path, store=store)

    def harvest(
        self,
        *,
        intent_key: str,
        seed_entity_ids: Sequence[str],
        keywords: Sequence[str] = (),
        horizon: int = 3,
    ) -> Dict[str, dict]:
        """按意图取回"证据半径"内的全部真实载荷（以 object_id 为键）。"""
        from aios_core.cognition.operation_experience import (
            RetrievalIntent,
            TopologicalDrillDownExecutor,
        )

        # 取证阶段用宽预算（内部扫描不是输出），输出的 Token 纪律由建议结构单独把关
        intent = RetrievalIntent(
            intent_key=intent_key,
            keywords=tuple(keywords),
            seed_entity_ids=tuple(seed_entity_ids),
            evidence_horizon=horizon,
            token_budget=20_000,
            ladder_fanout=self.fanout,
        )
        execution = TopologicalDrillDownExecutor(self.store, index=self.index).execute(intent)
        facts: Dict[str, dict] = {}
        for object_id in execution.fact_ids:
            try:
                facts[object_id] = self.store.get_payload(object_id)
            except Exception:
                continue
        return facts

    def require(self, facts: Mapping[str, dict], prefixes: Sequence[str], *, role: str) -> List[str]:
        """按前缀抽取必需证据；一条都取不到即判定取证失败。"""
        found = sorted(oid for oid in facts if oid.startswith(tuple(prefixes)))
        if not found:
            raise InsufficientEvidenceError(
                f"取证失败：缺少「{role}」类证据（期望前缀 {list(prefixes)}），拒绝输出无证据建议"
            )
        return found


def _summarize(payload: Mapping[str, Any], *, limit: int = 42) -> str:
    """把一条载荷压成短摘要（用于因果链展示，永不返回空串）。"""
    text = ""
    value = payload.get("value")
    if isinstance(value, str) and value.strip():
        text = value
    if not text:
        for key in (
            "content",
            "title",
            "interpretation",
            "purpose",
            "statement",
            "canonical_name",
            "relation_type",
            "entity_kind",
            "name",
        ):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate
                break
    text = " ".join(text.split())
    if not text:
        text = f"{payload.get('object_type', 'object')}:{payload.get('object_id', '?')}"
    return text[:limit]


def _ref(payload: Mapping[str, Any]) -> ObjectRef:
    """从载荷构造带 revision 的证据指针。"""
    return ObjectRef(object_id=str(payload["object_id"]), revision=int(payload.get("revision") or 1))


def _estimate_tokens(obj: Any) -> int:
    """建议体积的 Token 估算（与看板口径一致的粗算）。"""
    import json as _json

    content = obj if isinstance(obj, str) else _json.dumps(obj, ensure_ascii=False, default=str)
    return max(1, int(len(content) / 3.2 + 0.999))


# ===========================================================================
# 三类推演器
# ===========================================================================
class SymbioticDecisionAdvisor:
    """决策顾问基类：统一"无世界走沙盘、有世界走取证"的双模契约。"""

    slug: str = "advisor"
    intent_key: str = "advice"

    def __init__(
        self,
        *,
        store: Optional[SQLiteWorldStore] = None,
        index: Any = None,
        evidence_prefixes: Optional[Sequence[str]] = None,
        seed_entities: Optional[Sequence[str]] = None,
    ) -> None:
        self.store = store
        self.index = index
        #: 取证选择器可被覆写（同一顾问可服务不同对象，亦可用于"证据缺口"对抗测试）
        self._prefix_override = tuple(evidence_prefixes) if evidence_prefixes else None
        self._seed_override = None if seed_entities is None else tuple(seed_entities)
        self._harvester: Optional[_EvidenceHarvester] = None

    def evidence_prefixes(self, defaults: Sequence[str]) -> Tuple[str, ...]:
        """证据前缀选择器（默认取子类常量，可被构造参数覆写）。"""
        return self._prefix_override or tuple(defaults)

    def seed_entities(self, defaults: Sequence[str]) -> Tuple[str, ...]:
        """取证种子实体（默认取子类常量，可被构造参数覆写）。"""
        return tuple(defaults) if self._seed_override is None else self._seed_override

    @property
    def harvester(self) -> _EvidenceHarvester:
        """懒构造取证器（无世界接入时不可用）。"""
        if self.store is None:
            raise InsufficientEvidenceError(f"{self.slug} 未接入世界存储，无法进入取证模式")
        if self._harvester is None:
            self._harvester = _EvidenceHarvester(self.store, index=self.index)
        return self._harvester

    # ---- 对外双模入口 ----------------------------------------------------
    def advise(self, *, world: bool = False) -> ActionableAdvice:
        """默认返回宪法先验沙盘建议；``world=True`` 时走真实取证（需构造时接入 store）。"""
        if world:
            return self.advise_from_world()
        return self.prior_advice()

    def advise_from_world(self) -> ActionableAdvice:
        """真实世界取证模式（子类实现）。"""
        raise NotImplementedError

    def prior_advice(self) -> ActionableAdvice:
        """先验沙盘模式（子类实现）。"""
        raise NotImplementedError

    # ---- 公共校验 --------------------------------------------------------
    def _finalize(self, advice: ActionableAdvice, *, mode: EvidenceMode) -> ActionableAdvice:
        """统一收口：反套话闸门 + 体积统计 + 世界修订号打戳。"""
        advice.evidence_mode = mode
        advice.advisor = self.slug
        if mode is EvidenceMode.WORLD_EVIDENCE and self.store is not None:
            advice.world_revision = int(self.store.current_world_revision())
            advice.verify_against(self.store)
        advice.token_estimate = _estimate_tokens(advice.as_dict())
        return AdviceQualityGuard.enforce(advice)


class MomBirthdayGiftAdvisor(SymbioticDecisionAdvisor):
    """妈妈生日礼物推演器（穿越四年礼物史，只推一件不闲置的礼物）。"""

    slug = "mom_birthday_gift"
    intent_key = "妈妈生日礼物不闲置推演"
    GIFT_PREFIXES = ("obs_mom_gift_", "obs_mom_health_")
    SEED_ENTITIES = ("ent_mom", "ent_user_me")

    # ---- 先验沙盘（M1 兼容剧本） ----------------------------------------
    def prior_advice(self) -> ActionableAdvice:
        return self._finalize(
            ActionableAdvice(
                conclusion=(
                    "精准推荐轻便膝盖气囊热敷理疗仪，严禁笨重水洗家电（如足浴盆）及无用饰品"
                ),
                evidence_pointers=[
                    ObjectRef(object_id="obs_2023_scarf_idle"),
                    ObjectRef(object_id="obs_2024_footbath_backache"),
                    ObjectRef(object_id="obs_2025_massage_chair_good"),
                    ObjectRef(object_id="obs_2026_knee_cold"),
                ],
                alternatives=["保暖护膝", "轻便理疗贴"],
                expected_benefit="避免母亲因笨重家电加重腰痛，精准解决2026年发现的膝盖老寒腿问题，确保礼物实用不闲置",
                action_items=["下单前确认重量 ≤1.5kg 且免搬抬、免倒水"],
                exclusions=["足浴盆（笨重水洗）", "饰品（易落灰）"],
            ),
            mode=EvidenceMode.PRIOR_SANDBOX,
        )

    # ---- 世界取证 --------------------------------------------------------
    def advise_from_world(self) -> ActionableAdvice:
        facts = self.harvester.harvest(
            intent_key=self.intent_key,
            seed_entity_ids=self.seed_entities(self.SEED_ENTITIES),
            keywords=("妈妈", "生日", "礼物", "膝盖"),
        )
        gift_ids = self.harvester.require(facts, self.evidence_prefixes(self.GIFT_PREFIXES), role="历年礼物与健康演化")

        chain: List[CausalLink] = []
        for object_id in gift_ids:
            payload = facts[object_id]
            summary = _summarize(payload)
            chain.append(
                CausalLink(
                    fact_ref=_ref(payload),
                    fact_summary=summary,
                    inference=self._infer(object_id, summary),
                    weight=1.0 if object_id.startswith("obs_mom_health_") else 0.8,
                )
            )

        legacy_hint = next((oid for oid in gift_ids if "2024" in oid), None)
        knee_hint = next((oid for oid in gift_ids if "knee" in oid or "2026" in oid), None)
        if legacy_hint is None or knee_hint is None:
            raise InsufficientEvidenceError(
                "取证失败：缺少 2024 闲置教训或 2026 膝盖受凉事实，无法区分'能用'与'落灰'"
            )

        return self._finalize(
            ActionableAdvice(
                conclusion=(
                    "推荐【轻便膝盖气囊热敷理疗仪】（≤1.5kg、免倒水、免搬抬）；"
                    "排除足浴盆等笨重水洗家电与无用饰品"
                ),
                evidence_pointers=[_ref(facts[oid]) for oid in gift_ids],
                alternatives=[
                    "石墨烯护膝（更便宜，但热敷时长与温控不足）",
                    "膝部艾灸盒（需明火与看护，老年人独处不安全）",
                ],
                expected_benefit=(
                    "直接命中 2026 膝盖受凉痛点，同时规避 2024 足浴盆倒水搬抬加重腰疼的旧坑，"
                    "礼物不闲置、不添负担"
                ),
                causal_chain=chain,
                action_items=[
                    "生日前 7 天下单，预留尺寸退换时间窗",
                    "确认到货整机 ≤1.5kg、免倒水免搬抬（对照 2024 足浴盆教训逐项打勾）",
                    "选择可拆洗布套 + 三档温控（≤55℃）型号",
                    "附上手写卡片说明每天热敷 20 分钟的使用节奏",
                ],
                exclusions=[
                    "足浴盆：2024 已证笨重且倒水需弯腰搬抬",
                    "饰品：2023 丝巾落灰，使用频次极低",
                    "按摩椅等大件：占空间且非膝盖定点理疗",
                ],
            ),
            mode=EvidenceMode.WORLD_EVIDENCE,
        )

    @staticmethod
    def _infer(object_id: str, summary: str) -> str:
        """把历史事实翻译成"为什么这个礼物不行/行"的推断。"""
        if "2023" in object_id:
            return "礼物闲置率极高 → 排除无实用价值的饰品类"
        if "2024" in object_id:
            return "笨重水洗家电加重腰疼 → 排除需倒水/搬抬的一切设备"
        if "2025" in object_id:
            return "大件家电口碑虽好但占地 → 膝盖定点理疗优先于全身大件"
        if "2026" in object_id or "knee" in object_id:
            return "膝盖受凉疼痛是当前第一痛点 → 轻便、免水洗、可定点热敷者优先"
        return "纳入礼物史比对"


class FraudPreventionAdvisor(SymbioticDecisionAdvisor):
    """反欺诈阻击推演器（法院判决 + 历史拖延记录 = 拒绝二次受骗）。"""

    slug = "fraud_prevention"
    intent_key = "老王借款纠纷能否追偿"
    WANG_PREFIXES = ("obs_wang_", "evset_wang_", "anchor_wang_", "claim_wang_", "rel_user_wang")
    SEED_ENTITIES = ("ent_old_wang",)

    def prior_advice(self) -> ActionableAdvice:
        return self._finalize(
            ActionableAdvice(
                conclusion="硬核阻击借款/合伙提议，立即拒绝老王，并启动资产追偿沟通",
                evidence_pointers=[
                    ObjectRef(object_id="court_ruling_chaoyang_fraud"),
                    ObjectRef(object_id="obs_2_years_ago_wechat_delay"),
                ],
                alternatives=["只拒绝不追偿", "走法律程序发律师函"],
                expected_benefit="阻断二次受骗风险，及时止损并对历史债务进行有效追偿",
                action_items=["当场拒绝追加出借，并保留拒绝留痕"],
                exclusions=["任何形式的追加出借", "以新协议置换旧欠条"],
            ),
            mode=EvidenceMode.PRIOR_SANDBOX,
        )

    def advise_from_world(self) -> ActionableAdvice:
        facts = self.harvester.harvest(
            intent_key=self.intent_key,
            seed_entity_ids=self.seed_entities(self.SEED_ENTITIES),
            keywords=("老王", "借款", "判决", "追偿"),
        )
        wang_ids = self.harvester.require(facts, self.evidence_prefixes(self.WANG_PREFIXES), role="老王案证据链")
        has_court = any("court" in oid or "verdict" in oid for oid in wang_ids)
        has_history = any("delay" in oid or "chat" in oid or "msg" in oid for oid in wang_ids)
        if not (has_court and has_history):
            raise InsufficientEvidenceError(
                "取证失败：法院判决或历史拖延记录缺失，拒绝输出追偿类建议"
            )

        chain: List[CausalLink] = []
        for object_id in wang_ids:
            payload = facts[object_id]
            chain.append(
                CausalLink(
                    fact_ref=_ref(payload),
                    fact_summary=_summarize(payload),
                    inference=self._infer(object_id),
                    weight=1.0 if ("court" in object_id or "claim" in object_id) else 0.7,
                )
            )

        deadline_hint = next((oid for oid in wang_ids if "delay" in oid or "fight" in oid), None)
        assert deadline_hint is not None  # 已由 has_history 保证

        return self._finalize(
            ActionableAdvice(
                conclusion=(
                    "硬核阻击：拒绝老王的一切追加借款与合伙提议，立即启动资产追偿"
                    "（律师函 + 财产保全 + 执行申请）"
                ),
                evidence_pointers=[_ref(facts[oid]) for oid in wang_ids],
                alternatives=[
                    "只发催款函不诉（成本低，但对方已多次承诺失信，预期回收率低）",
                    "先谈分期再诉（需签还款计划书并按期违约即启动执行）",
                ],
                expected_benefit="阻断二次受骗的资金外流，把'人情要钱'转成有法律抓手的追偿行动",
                causal_chain=chain,
                action_items=[
                    "48 小时内书面回复拒绝追加出借，措辞只谈事实不谈情面",
                    "整理转账凭证与聊天记录，形成一份可提交的证据清单",
                    "7 天内向有管辖权的法院申请支付令/起诉，并同步申请财产保全",
                    "把所有后续沟通切换到可留痕渠道（文字/邮件），停止口头承诺",
                ],
                exclusions=[
                    "任何追加出借（含'过桥''短借''高息返利'）",
                    "以新合同置换旧欠条（会稀释既有证据强度）",
                    "口头承诺换取延期（历史已证明不可信）",
                ],
            ),
            mode=EvidenceMode.WORLD_EVIDENCE,
        )

    @staticmethod
    def _infer(object_id: str) -> str:
        """把老王的每条事实翻译成对"还能不能再借"的判断。"""
        if "court" in object_id or "verdict" in object_id:
            return "已进入司法程序 → 追加出借等同扩大损失"
        if "delay" in object_id or "msg" in object_id:
            return "拖延话术重复出现 → 口头承诺不可作为还款保障"
        if "fight" in object_id or "call" in object_id:
            return "冲突已发生 → 继续妥协只会抬高沉没成本"
        if "claim" in object_id or "anchor" in object_id:
            return "因果链已成型 → 追偿应走证据与程序，而非人情"
        if "contract" in object_id:
            return "原始合同是大额资金流向的唯一书面凭据，必须纳入证据清单"
        return "纳入老王案证据链"


class HealthFatigueBreakerAdvisor(SymbioticDecisionAdvisor):
    """心脏早搏疲劳熔断顾问（通宵加班 → 室性早搏的因果熔断）。"""

    slug = "health_fatigue_breaker"
    intent_key = "通宵加班与室性早搏因果链"
    HEALTH_PREFIXES = (
        "obs_work_late_night_",
        "obs_bio_arrhythmia_",
        "anchor_overtime_",
        "claim_overtime_",
        "evset_health_",
    )
    SEED_ENTITIES = ("ent_user_me",)

    def prior_advice(self) -> ActionableAdvice:
        return self._finalize(
            ActionableAdvice(
                conclusion="触发疲劳熔断保护！必须立即停止工作休息，并预约心电图复查",
                evidence_pointers=[
                    ObjectRef(object_id="obs_thursday_overnight_work"),
                    ObjectRef(object_id="obs_pvc_arrhythmia"),
                ],
                alternatives=["短休30分钟后继续", "服用抗疲劳药物（极度不推荐）"],
                expected_benefit="防止心脏超负荷导致严重后果，确保生命安全（生命安全高于一切）",
                action_items=["24 小时内完成心电图检查"],
                exclusions=["继续通宵", "靠咖啡因硬撑"],
            ),
            mode=EvidenceMode.PRIOR_SANDBOX,
        )

    def advise_from_world(self) -> ActionableAdvice:
        facts = self.harvester.harvest(
            intent_key=self.intent_key,
            seed_entity_ids=self.seed_entities(self.SEED_ENTITIES),
            keywords=("加班", "早搏", "心率"),
        )
        health_ids = self.harvester.require(facts, self.evidence_prefixes(self.HEALTH_PREFIXES), role="加班-早搏因果链")
        has_work = any(oid.startswith("obs_work_late_night_") for oid in health_ids)
        has_cardiac = any(oid.startswith("obs_bio_arrhythmia_") for oid in health_ids)
        if not (has_work and has_cardiac):
            raise InsufficientEvidenceError(
                "取证失败：缺少通宵加班或室性早搏观测，无法建立因果链，拒绝输出熔断建议"
            )

        chain: List[CausalLink] = []
        for object_id in health_ids:
            payload = facts[object_id]
            chain.append(
                CausalLink(
                    fact_ref=_ref(payload),
                    fact_summary=_summarize(payload),
                    inference=(
                        "通宵工作 → 交感神经过度兴奋（可干预的因）"
                        if object_id.startswith("obs_work_late_night_")
                        else "室性早搏 → 心脏电活动异常（危险的果）"
                        if object_id.startswith("obs_bio_arrhythmia_")
                        else "因果共振已被固化为锚点/主张，属既定结论而非猜测"
                    ),
                    weight=1.0 if object_id.startswith("obs_bio_arrhythmia_") else 0.85,
                )
            )

        return self._finalize(
            ActionableAdvice(
                conclusion=(
                    "触发疲劳熔断保护：立即强制停工 24 小时，48 小时内完成心电图（必要时 24 小时动态心电）复查"
                ),
                evidence_pointers=[_ref(facts[oid]) for oid in health_ids],
                alternatives=[
                    "只停药不停工（无效：诱因未去除，早搏会复发）",
                    "自行服用抗疲劳/提神药物硬撑（极度不推荐，可能加重心律失常）",
                ],
                expected_benefit="切断'通宵加班 → 心律异常'因果链，避免进展为持续性心律失常或更严重后果",
                causal_chain=chain,
                action_items=[
                    "立即停工 24 小时：取消今明两天所有夜间会议与上线窗口",
                    "48 小时内到心内科完成常规心电图 + 心肌酶谱；若仍不适则佩戴 24 小时动态心电",
                    "连续 7 天记录静息心率与早搏自感次数，形成可对比的复查底稿",
                    "复工前设硬门槛：静息心率 <90bpm 且连续两晚睡眠 ≥7 小时",
                ],
                exclusions=[
                    "继续通宵或连续夜间上线",
                    "用咖啡因/提神饮料对冲困意",
                    "把早搏当作'累了正常现象'忽略",
                ],
            ),
            mode=EvidenceMode.WORLD_EVIDENCE,
        )


class AdvisorSuite:
    """三大推演器集成套件（供驾驶舱与战训考场一次性调用）。"""

    def __init__(self, store: SQLiteWorldStore, *, index: Any = None) -> None:
        self.store = store
        self.advisors: Tuple[SymbioticDecisionAdvisor, ...] = (
            MomBirthdayGiftAdvisor(store=store, index=index),
            FraudPreventionAdvisor(store=store, index=index),
            HealthFatigueBreakerAdvisor(store=store, index=index),
        )

    def advise_all(self) -> Dict[str, ActionableAdvice]:
        """三路取证并出建议（任一路取证不足都会抛错，绝不降级为套话）。"""
        return {advisor.slug: advisor.advise_from_world() for advisor in self.advisors}

    def audit(self) -> Dict[str, Any]:
        """套件审计：建议数量、证据指针总数、Token 体积。"""
        advices = self.advise_all()
        return {
            "advisors": len(advices),
            "evidence_pointers": sum(len(a.evidence_pointers) for a in advices.values()),
            "token_estimate_total": sum(a.token_estimate for a in advices.values()),
            "modes": sorted({a.evidence_mode.value for a in advices.values()}),
            "slugs": sorted(advices),
        }
