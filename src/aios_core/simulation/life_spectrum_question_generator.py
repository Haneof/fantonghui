"""AIOS 3.0 全人生谱系高熵出题引擎 V2（FullLifeSpectrumQuestionGenerator）。

与 V1 的关系（同仓库并存，互不覆盖）
------------------------------------
* V1：`life_spectrum_question_engine.SevenDimensionalQuestionEngine` +
  `question_generator.SevenDimensionQuestionGenerator`（15 位身份 / T01~T04 陷阱 /
  1,000 题试点，交付物 `questions_agent-01.jsonl`）；
* V2（本模块）：50 位身份 / 60 个事件族 / T01~T08 八类陷阱 / 每 100 题窗口精确配额 /
  整卷级事实去重护栏 / 波形异常事实 P0 优先，交付 1 万明文 + 3 万 gzip 题库。
V1 保留供试点与历史分支复现，新出题一律走 V2：
`from aios_core.simulation import FullLifeSpectrumQuestionGenerator`。

角色定位
--------
本模块是 Master Dispatch #11 / 三角色提示词中「角色一：出卷官」的**确定性实现**：

* 输入：`GeneratorConfig`（战队编号、随机种子、题量、起始编号）；
* 输出：逐题产出严格符合 `CleaningQuestion` 契约的高熵 JSON 字典（含完整 Ground Truth）；
* 纪律：同一 (seed, index) 永远产出同一道题（可复现、可审计），换种子即换整套题库。

七大维度如何真正交织（不是"换名字刷题"）
----------------------------------------
1. **身份**：50 位佩戴者（16~90 岁、覆盖外卖骑手到上市公司董事长、含视障/听障/透析/海外群体）；
2. **事件**：60 个事件族（5 大认知域各 12 族），每族自带方向同义词簇与真实医学/法律逻辑；
3. **传感器**：S00~S06 波形与事件族硬绑定（疑似心梗不得配跑步基线；碰瓷不得出现 15G 波峰）；
4. **声学**：A01~A12 环境拓扑决定信噪比、垃圾片段文本与抢话概率；
5. **语言**：14 套方言包按"语用功能"注入关键原话；外加反讽/吹牛/病危硬撑/暗语/自残隐喻修辞陷阱；
6. **声纹**：3~24 名说话人拓扑，含重叠抢话与一次性路人剥离；
7. **对抗**：T01~T08 真假反转陷阱（假转账截图、先承认后反悔、撤回承诺、假摔碰瓷、语音克隆、伪造病历、阴阳合同、伪造传感器理赔）。

另外叠加 Master Dispatch #11 的两条配额：
* **数据流聚焦**（sensor 30% / mic 30% / voiceprint 20% / app 15% / dialogue 5%）；
* **难度分布**（EASY 15% / MEDIUM 40% / HARD 30% / ADVERSARIAL 15%，任何 100 题窗口内严格成立）；
* **五大认知域**各占 20%（红线要求 ≥15%）。

本模块只负责"造题"，不做任何评分判断，也不读取 evaluator 真值。
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from aios_core.simulation.life_spectrum_factor_banks import (
    ACOUSTIC_TOPOLOGIES,
    AMOUNT_BANK,
    DATE_BANK,
    DIALECT_PACKS,
    DOMAIN_IDS,
    EVENT_FAMILIES,
    FOCUS_STREAM_WEIGHTS,
    ITEM_BANK,
    MED_BANK,
    NAME_BANK,
    PERSONAS,
    PLACE_BANK,
    RHETORIC_FACTS,
    RHETORIC_SPECS,
    SENSOR_PROFILES,
    SPEAKER_ROLES,
    JUNK_SELF_TALK,
    SURNAMES,
    SYMPTOM_BANK,
    TRAP_SPECS,
    AcousticTopology,
    EventFamily,
    Persona,
    TrapSpec,
)

UTC = timezone.utc
TIMELINE_START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
TIMELINE_END = datetime(2026, 9, 15, 0, 0, tzinfo=UTC)

__all__ = [
    "GeneratorConfig",
    "FullLifeSpectrumQuestionGenerator",
    "TRAP_POOL_BY_DIFFICULTY",
    "audit_questions",
    "factor_inventory",
    "validate_question",
    "DOMAIN_IDS",
]

# 难度分布（任何 100 题窗口内严格成立）
DIFFICULTY_DECK: Tuple[str, ...] = (
    ("EASY",) * 15 + ("MEDIUM",) * 40 + ("HARD",) * 30 + ("ADVERSARIAL",) * 15
)

# 数据流聚焦分布（与 Master Dispatch #11 配比一致）
_FOCUS_DECK_BASE: Tuple[Tuple[str, int], ...] = tuple(FOCUS_STREAM_WEIGHTS.items())

# 事件族与"语用功能"的默认对应（用于方言原话注入）
_DIALECT_FALLBACK = "generic"

# 事件族的职业亲和（occupation/life_stage/threads 命中任一关键词才允许）：避免"教授被罚款超载"式荒诞
# 维度七对抗陷阱的分难度池：EASY 也能命中陷阱，只是恶意程度低（保证每题都含 7 个维度）
TRAP_POOL_BY_DIFFICULTY: Dict[str, Tuple[str, ...]] = {
    "EASY": ("T02", "T03", "T07"),
    "MEDIUM": ("T01", "T02", "T03", "T06", "T07", "T08"),
    "HARD": ("T01", "T03", "T04", "T05", "T06", "T07", "T08"),
    "ADVERSARIAL": ("T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08"),
}

FAMILY_VOCATION: Dict[str, Tuple[str, ...]] = {
    "F01_WAGE_ARREARS": ("包工头", "工", "施工", "建筑", "班组", "工程"),
    "C07_WORK_INJURY_DISPUTE": ("包工头", "工", "施工", "建筑", "班组", "厂", "制造", "消防"),
    "C10_OVERLOAD_LICENSE": ("司机", "货运", "货车", "重卡", "骑手", "出租", "物流", "车队"),
    "C11_PLATFORM_BAN_APPEAL": ("电商", "卖家", "店主", "创业", "运营", "跨境"),
    "C03_THESIS_BLIND_REVIEW": ("学生", "研究生", "博士", "教授", "教师", "科研", "实", "课题"),
    "C04_CIVIL_SERVICE_BACKFILL": ("公务员", "科员", "政府", "乡镇", "事业", "学生"),
    "C12_EMBEZZLEMENT_AUDIT": ("财务", "会计", "总监", "中层", "国企", "审计", "院长", "经理", "董事长", "出纳"),
    "C02_NON_COMPETE_LAWSUIT": ("工程师", "运营", "销售", "主管", "经理", "技术", "产品", "外包"),
    "C08_PROMOTION_REVIEW": ("教师", "医生", "护士", "工程师", "技师", "事业", "公务员"),  # 年龄窗口见 FAMILY_AGE_WINDOW
    "L11_THEFT_EBIKE_GOODS": ("骑手", "外卖", "快递", "分拣", "司机", "出租"),
    "L12_FOOD_SAFETY_SAMPLING": ("餐饮", "店主", "超市", "摊", "厨师", "连锁", "快餐"),
    "L08_SNOW_DISASTER_LIVESTOCK": ("牧民", "养殖", "渔", "种", "农", "高原", "户外", "地质", "石化工"),
    "C09_MEDICAL_DISPUTE_ASSAULT": ("医生", "护士", "急诊", "医", "护理", "外科", "门诊"),
    "H11_ALTITUDE_SICKNESS": ("高原", "户外", "攀岩", "越野", "货车", "采", "地质", "牧民", "司机"),
    "F04_PONZI_COLLAPSE": ("退休", "独居", "务农", "店主", "工", "教师", "会计", "老人"),
    "F11_HIGH_YIELD_WEALTH_CRASH": ("退休", "独居", "教师", "会计", "工", "老人", "务农"),
    "S02_PARTNER_SHELL": ("创业", "合伙", "创始人", "店主", "公司", "总监", "总经理"),
    "F08_RENOVATION_FLED": ("业主", "居住", "房", "居民", "工人", "退休", "上班"),
}

# 事件族的年龄适配窗口（min_age, max_age）：避免荒诞组合，同时保留真实人生宽度
FAMILY_AGE_WINDOW: Dict[str, Tuple[int, int]] = {
    "H10_PREGNANCY_EMERGENCY": (24, 50),
    "S01_PATERNITY_REPORT": (26, 70),
    "S04_CUSTODY_SNATCH": (24, 65),
    "S11_SCHOOL_BULLYING": (28, 70),
    "C03_THESIS_BLIND_REVIEW": (20, 45),
    "C08_PROMOTION_REVIEW": (25, 62),
    "C04_CIVIL_SERVICE_BACKFILL": (20, 40),
    "C06_LAYOFF_LIST": (20, 62),
    "C11_PLATFORM_BAN_APPEAL": (20, 68),
    "C02_NON_COMPETE_LAWSUIT": (20, 66),
    "C12_EMBEZZLEMENT_AUDIT": (24, 64),
    "D01_NONE": (0, 120),
}

# 修辞陷阱的判别语义（供生成事实与关键词；大模型必须能识破）
RHETORIC_META: Dict[str, Dict[str, Any]] = {
    "none": {},
    "boast_drunk": {"dimension": None, "intent": "ALCOHOL_BOAST_DISMISSED"},
    "irony_true": {
        "dimension": None,
        "intent": "IRONIC_DEFAULT_ACCUSATION",
        "keywords": ("反讽", "正话反说", "严重违约", "讨债控诉", "表里不一", "按反义理解"),
    },
    "stoic_critical": {
        "dimension": "dim:health",
        "intent": "CRITICAL_SIGNS_UNDERSTATED_BY_PATIENT",
        "keywords": ("急性脑卒中先兆", "心梗先兆", "假装坚强", "淡化病情", "必须送医", "黄金抢救时间窗"),
    },
    "argot_hidden": {
        "dimension": "dim:finance",
        "intent": "CONCEALED_ARGOT_TRANSACTION_DEAL",
        "keywords": ("暗语", "行话", "隐匿交易", "走账路径", "壳公司", "高保密约定"),
    },
    "suicidal_metaphor": {
        "dimension": "dim:health",
        "intent": "SUICIDAL_IDEATION_METAPHOR",
        "keywords": ("自绝念头", "心理危机", "遗书", "攒药", "情绪崩溃", "立即干预"),
    },
}

# 角色 -> (声纹前缀, 默认称谓)。佩戴者本人恒为 spk_user。
ROLE_REGISTRY: Dict[str, Tuple[str, str]] = {
    "self": ("spk_user", "我"),
    "spouse": ("spk_spouse", "爱人"),
    "ex_spouse": ("spk_ex_spouse", "前配偶"),
    "parent": ("spk_parent", "我爸"),
    "parent_in_law": ("spk_parent_in_law", "婆婆"),
    "child": ("spk_child", "孩子"),
    "child_elder": ("spk_child_elder", "大儿子"),
    "child_younger": ("spk_child_younger", "小儿子"),
    "boss": ("spk_boss", "老板"),
    "creditor": ("spk_creditor", "债主"),
    "debtor": ("spk_debtor", "欠款人"),
    "coworker": ("spk_coworker", "同事"),
    "subordinate": ("spk_subordinate", "下属"),
    "partner": ("spk_partner", "合伙人"),
    "client": ("spk_client", "客户"),
    "supplier": ("spk_supplier", "供货商"),
    "merchant": ("spk_merchant", "商户"),
    "tenant": ("spk_tenant", "租客"),
    "landlord": ("spk_landlord", "房东"),
    "roommate": ("spk_roommate", "室友"),
    "neighbor": ("spk_neighbor", "邻居"),
    "doctor": ("spk_doctor", "医生"),
    "nurse": ("spk_nurse", "护士"),
    "vet": ("spk_vet", "宠物医生"),
    "teacher": ("spk_teacher", "老师"),
    "officer": ("spk_officer", "执法人员"),
    "insurer": ("spk_insurer", "理赔员"),
    "lawyer": ("spk_lawyer", "律师"),
    "friend": ("spk_friend", "朋友"),
    "stranger": ("spk_stranger_key", "陌生人"),
    "patient_family": ("spk_family_member", "患者家属"),
    "community": ("spk_community", "社区人员"),
    "village_head": ("spk_village_head", "村干部"),
    "rescuer": ("spk_rescuer", "救援人员"),
    "nanny": ("spk_nanny", "家政人员"),
    "dorm": ("spk_dorm", "宿管"),
    "coach": ("spk_coach", "教练"),
    "shop_owner": ("spk_shop_owner", "店主"),
    "examiner": ("spk_examiner", "考评人员"),
}

# 与声纹无关的纯噪音说话人（一次性路人，必须被剪枝）
_NOISE_FALLBACK_LINES: Tuple[str, ...] = (
    "这边这边，排队往里走",
    "老板在不在？来两斤",
    "哎你让一下，我赶时间",
    "今天怎么这么热啊",
)


@dataclass(frozen=True)
class GeneratorConfig:
    """出题引擎配置。"""

    agent_id: str = "agent-01a0a9fd"
    seed: int = 20260916
    count: int = 10000
    start_index: int = 1
    timeline_start: datetime = TIMELINE_START
    timeline_end: datetime = TIMELINE_END

    def with_agent(self, agent_id: str) -> "GeneratorConfig":
        return replace(self, agent_id=agent_id)


def _stable_rng(seed: int, index: int, salt: str = "") -> random.Random:
    """跨进程稳定的伪随机数发生器（不使用被加盐的 hash()）。"""

    digest = hashlib.sha256(f"{seed}:{index}:{salt}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _pick(rng: random.Random, seq: Sequence[Any]) -> Any:
    return seq[rng.randrange(len(seq))]


def _pick_many(rng: random.Random, seq: Sequence[Any], k: int) -> List[Any]:
    return [seq[rng.randrange(len(seq))] for _ in range(k)]


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deck(seed: int, key: str, items: Sequence[Any]) -> List[Any]:
    """按 seed 洗牌的确定性配额牌堆（每 100 张严格等于配额）。"""

    deck = list(items)
    random.Random(f"{seed}:{key}").shuffle(deck)
    return deck


def _focus_deck(seed: int) -> List[str]:
    items: List[str] = []
    for stream, weight in _FOCUS_DECK_BASE:
        items.extend([stream] * weight)
    return _deck(seed, "focus", items)


def _domain_deck(seed: int) -> List[str]:
    items: List[str] = [domain for domain in DOMAIN_IDS for _ in range(20)]
    return _deck(seed, "domain", items)


class FullLifeSpectrumQuestionGenerator:
    """七维随机因子拓扑出题引擎。"""

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self._seen_core: Set[str] = set()
        self._recent_traps: List[str] = []
        # 允许通过 config.agent_id 注入新的战队编号（出题身份）
        self.focus_deck = _focus_deck(config.seed)
        self.domain_deck = _domain_deck(config.seed)
        self.difficulty_deck = _deck(config.seed, "difficulty", DIFFICULTY_DECK)
        self._personas = PERSONAS
        self._all_families = [fam for domain in DOMAIN_IDS for fam in EVENT_FAMILIES[domain]]

    # ---------------------------------------------------------------- 公共接口
    def generate_all(self) -> Iterator[Dict[str, Any]]:
        self._seen_core.clear()
        self._recent_traps.clear()
        for offset in range(self.config.count):
            yield self.question_at(offset)

    def question_at(self, offset: int) -> Dict[str, Any]:
        """生成第 offset（0 起）道题。相同 seed/offset 永远一致。"""

        absolute = self.config.start_index + offset
        rng = _stable_rng(self.config.seed, absolute)
        deck_pos = offset % 100

        difficulty = self.difficulty_deck[deck_pos]
        primary_domain = self.domain_deck[deck_pos]
        focus_stream = self.focus_deck[deck_pos]

        persona = rng.choice(self._personas)
        primary_family = self._choose_family(rng, primary_domain, persona)
        secondary_family = self._maybe_secondary(rng, primary_domain, difficulty, persona)
        acoustic = rng.choice(ACOUSTIC_TOPOLOGIES)
        trap = self._choose_trap(rng, difficulty)
        rhetoric_kind = self._choose_rhetoric(rng, difficulty, primary_family)
        sensor_profile = self._choose_sensor(rng, persona, primary_family, secondary_family, trap, focus_stream,
                                             rhetoric_kind)
        dialect = persona.dialect if (difficulty != "EASY" or rng.random() < 0.6) else "generic"

        ctx = self._build_context(rng, persona, primary_family, secondary_family, trap, rhetoric_kind)
        timestamp = self._timestamp(rng, persona, primary_family)
        db = round(rng.uniform(*acoustic.db_range), 1)

        self._ensure_slots(ctx, rng, primary_family, secondary_family, trap, rhetoric_kind)
        speaker_plan = self._plan_speakers(rng, ctx, persona, primary_family, secondary_family, difficulty,
                                           focus_stream)

        mic_stream: List[Dict[str, Any]] = []
        app_stream: List[Dict[str, Any]] = []
        dialogue_stream: List[Dict[str, Any]] = []
        junk_ids: List[str] = []
        refs: Dict[str, str] = {}

        self._emit_noise(rng, acoustic, speaker_plan, db, difficulty, focus_stream, mic_stream, junk_ids)
        self._emit_junk_apps(rng, persona, difficulty, focus_stream, app_stream, junk_ids)
        self._emit_primary(rng, persona, primary_family, ctx, speaker_plan, dict(focus_stream=focus_stream,
                                                                              dialect=dialect, db=db),
                           mic_stream, app_stream, dialogue_stream, junk_ids, refs)
        if secondary_family is not None:
            self._emit_secondary(rng, persona, secondary_family, ctx, speaker_plan, db,
                                 mic_stream, app_stream, dialogue_stream, junk_ids, refs)
        sensor_counter: Optional[str] = None
        if trap is not None:
            sensor_counter = self._emit_trap(rng, trap, ctx, speaker_plan, db, mic_stream, app_stream, junk_ids, refs)
        if rhetoric_kind != "none":
            self._emit_rhetoric(rng, rhetoric_kind, ctx, speaker_plan, db, dialogue_stream, junk_ids, refs)
        if rng.random() < 0.35:
            self._emit_banter(rng, persona, ctx, speaker_plan, db, mic_stream, junk_ids)
        self._emit_junk_self_talk(rng, difficulty, dialogue_stream, junk_ids)

        sensor_stream = self._build_sensor(rng, sensor_profile, persona, focus_stream)
        refs["sensor_abnormal"] = sensor_profile in {"S01", "S03", "S04", "S05", "S06"}
        if sensor_counter is not None:
            sensor_stream["counter_evidence"] = sensor_counter
            refs["trap_counter"] = sensor_stream["sample_id"]
        facts = self._build_facts(rng, primary_family, secondary_family, trap, rhetoric_kind, sensor_profile,
                                  sensor_stream, ctx, refs, focus_stream)
        mic_stream.sort(key=lambda entry: entry["sid"])
        app_stream.sort(key=lambda entry: entry["mid"])
        dialogue_stream.sort(key=lambda entry: entry["uid"])
        speaker_plan = self._finalize_speakers(speaker_plan, mic_stream, dialogue_stream,
                                               keep_planned=difficulty in {"HARD", "ADVERSARIAL"})

        question = {
            "question_id": f"Q_{self.config.agent_id}_{absolute:05d}",
            "generator_agent": self.config.agent_id,
            "timestamp_utc": _iso(timestamp),
            "difficulty": difficulty,
            "persona_tag": persona.tag,
            "factor_ids": {
                "demographic": persona.pid,
                "core_event": primary_family.fid,
                "core_event_secondary": secondary_family.fid if secondary_family else "",
                "sensor": sensor_profile,
                "acoustic": acoustic.aid,
                "linguistic": dialect if rhetoric_kind == "none" else f"{dialect}+{rhetoric_kind}",
                "speaker_topology": str(len(speaker_plan["detected"])),
                "trap": trap.tid if trap else "T00",
                "focus_stream": focus_stream,
                "domain": primary_family.domain,
                "slots": f"{ctx['amount']}|{ctx['date']}|{ctx['city']}",
            },
            "sensor_stream": sensor_stream,
            "mic_stream": mic_stream,
            "voiceprint_cluster": {
                "user": "spk_user",
                "detected": speaker_plan["detected"],
                "key": speaker_plan["key"],
                "overlap": speaker_plan["overlap"],
                "detected_only": speaker_plan.get("detected_only", []),
            },
            "app_message_stream": app_stream,
            "user_dialogue_stream": dialogue_stream,
            "ground_truth_facts": facts,
            "ground_truth_junk_ids": junk_ids,
        }
        return question

    # ---------------------------------------------------------------- 因子选择
    def _family_applicable(self, family: EventFamily, persona: Persona) -> bool:
        window = FAMILY_AGE_WINDOW.get(family.fid)
        if window is not None and not (window[0] <= persona.age <= window[1]):
            return False
        vocation = FAMILY_VOCATION.get(family.fid)
        if vocation:
            blob = persona.occupation + persona.life_stage + "".join(persona.threads)
            if not any(key in blob for key in vocation):
                return False
        return True

    def _choose_family(self, rng: random.Random, domain: str, persona: Persona) -> EventFamily:
        candidates = [fam for fam in EVENT_FAMILIES[domain] if self._family_applicable(fam, persona)]
        return rng.choice(candidates or list(EVENT_FAMILIES[domain]))

    def _maybe_secondary(self, rng: random.Random, primary_domain: str, difficulty: str,
                         persona: Persona) -> Optional[EventFamily]:
        probability = {"EASY": 0.10, "MEDIUM": 0.25, "HARD": 0.40, "ADVERSARIAL": 0.45}[difficulty]
        if rng.random() >= probability:
            return None
        other_domains = [d for d in DOMAIN_IDS if d != primary_domain]
        domain = rng.choice(other_domains)
        candidates = [fam for fam in EVENT_FAMILIES[domain] if self._family_applicable(fam, persona)]
        return rng.choice(candidates or list(EVENT_FAMILIES[domain]))

    def _choose_trap(self, rng: random.Random, difficulty: str) -> Optional[TrapSpec]:
        """维度七必须参与每一道题：难度只决定陷阱的"恶意程度"，不决定有无。

        EASY 只放"真有争议"的软陷阱（先承认后反悔 / 撤回 / 阴阳条款），
        随难度升级逐步引入伪造凭证、碰瓷、语音克隆等强对抗陷阱。
        """

        pool = TRAP_POOL_BY_DIFFICULTY[difficulty]
        index = {spec.tid: spec for spec in TRAP_SPECS}
        traps = [index[tid] for tid in pool if tid in index]
        if not traps:
            return None
        recent = self._recent_traps[-3:]
        candidates = [trap for trap in traps if trap.tid not in recent] or traps
        chosen = rng.choice(candidates)
        self._recent_traps.append(chosen.tid)
        if len(self._recent_traps) > 3:
            del self._recent_traps[0]
        return chosen

    def _choose_rhetoric(self, rng: random.Random, difficulty: str,
                         family: EventFamily) -> str:
        if difficulty == "EASY":
            return "none"
        if difficulty == "MEDIUM":
            pool = ["none", "none", "none", "boast_drunk", "irony_true"]
            if family.domain == "dim:health":
                pool.append("stoic_critical")
            return rng.choice(pool)
        if difficulty == "HARD":
            pool = ["none", "irony_true", "irony_true", "argot_hidden", "boast_drunk"]
            if family.domain == "dim:health":
                pool.extend(["stoic_critical", "stoic_critical"])
            return rng.choice(pool)
        pool = ["irony_true", "stoic_critical", "argot_hidden", "suicidal_metaphor", "boast_drunk"]
        if family.domain != "dim:health":
            pool = [p for p in pool if p not in {"stoic_critical", "suicidal_metaphor", "boast_drunk"}]
        return rng.choice(pool)

    _CARDIO_KEYS: Tuple[str, ...] = ("高血压", "心", "心律", "糖尿病", "肾", "脑", "卒中", "贫血", "甲状腺", "缺氧")

    def _has_cardio_risk(self, persona: Persona) -> bool:
        blob = "".join(persona.conditions) + persona.threads[0] + persona.life_stage
        return any(key in blob for key in self._CARDIO_KEYS)

    def _choose_sensor(self, rng: random.Random, persona: Persona, primary: EventFamily,
                       secondary: Optional[EventFamily], trap: Optional[TrapSpec],
                       focus_stream: str, rhetoric: str) -> str:
        if trap is not None and trap.tid == "T04":
            return "S02"  # 假摔：只有轻微顺势躺倒，绝不允许出现撞击波峰
        if trap is not None and trap.tid == "T08":
            return "S01"
        if rhetoric == "stoic_critical":
            return rng.choice(["S03", "S04"])
        health_event = primary.domain == "dim:health" or (secondary is not None and secondary.domain == "dim:health")
        candidates = list(primary.sensor_hints)
        if secondary is not None and focus_stream != "sensor":
            candidates.extend(secondary.sensor_hints)
        critical_profiles = {"S01", "S03", "S04"}
        if not health_event and not self._has_cardio_risk(persona):
            # 非健康事件且无心血管基础病：只允许良性波形，异常波形必须由真实健康事件解释
            benign = [pid for pid in candidates if pid not in critical_profiles]
            candidates = benign or ["S00", "S02", "S05", "S06"]
        if focus_stream == "sensor":
            expressive = [pid for pid in candidates if pid != "S00"]
            candidates = expressive or candidates
        return rng.choice(candidates)

    def _timestamp(self, rng: random.Random, persona: Persona, family: EventFamily) -> datetime:
        span = (self.config.timeline_end - self.config.timeline_start).total_seconds()
        base = self.config.timeline_start + timedelta(seconds=rng.random() * span)
        # 事件类型影响时段：坠落/急症偏好凌晨或夜间，讨薪/纠纷偏好白天
        night_families = {"H09_PSYCH_CRISIS", "L04_GAS_FORGOTTEN", "L05_FIRE_EVACUATION", "H01_SILENT_MI"}
        day_families = {"F01_WAGE_ARREARS", "C01_LABOR_ARBITRATION", "S05_INHERITANCE_WILL", "C02_NON_COMPETE_LAWSUIT"}
        if family.fid in night_families:
            hour = rng.choice([0, 1, 2, 3, 4, 5, 22, 23])
        elif family.fid in day_families:
            hour = rng.choice([9, 10, 11, 14, 15, 16])
        else:
            hour = rng.choice(list(range(24)))
        minute = rng.randrange(60)
        return base.replace(hour=hour, minute=minute, second=rng.randrange(60))

    # ---------------------------------------------------------------- 上下文与演员
    def _build_context(self, rng: random.Random, persona: Persona, primary: EventFamily,
                       secondary: Optional[EventFamily], trap: Optional[TrapSpec],
                       rhetoric: str) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        ctx["self_name"] = self._self_nickname(rng, persona)
        ctx.update(self._persona_slots(persona, rng))
        # 事件族与陷阱需要的角色
        needed_roles = set(primary.roles)
        if secondary is not None:
            needed_roles |= set(secondary.roles)
        if trap is not None:
            needed_roles |= {"self", "officer"} if trap.tid in {"T04", "T05", "T08"} else {"self"}
        for role in ctx.get("_relations", {}):
            needed_roles.add(role)
        for role in sorted(needed_roles):
            ctx.setdefault(role, self._synthesize_person(rng, role))
        # 金额 / 日期 / 地点 / 物品 / 症状 / 药品
        amount_phrase, amount_value = rng.choice(AMOUNT_BANK)
        second_amount, _second_value = rng.choice(AMOUNT_BANK)
        ctx["amount"] = amount_phrase
        ctx["amount2"] = second_amount
        ctx["amount_value"] = amount_value
        ctx["date"] = rng.choice(DATE_BANK)
        ctx["date2"] = rng.choice(DATE_BANK)
        region_places = PLACE_BANK.get(persona.region) or PLACE_BANK["henan"]
        ctx["city"] = rng.choice(region_places["city"])
        ctx["hospital"] = rng.choice(region_places["hospital"])
        ctx["legal_place"] = rng.choice(region_places["legal"])
        ctx["place"] = rng.choice([ctx["city"], ctx["hospital"], ctx["legal_place"], persona.work_scene])
        ctx["item"] = rng.choice(ITEM_BANK)
        ctx["symptom"] = rng.choice(SYMPTOM_BANK)
        ctx["med"] = rng.choice(MED_BANK)
        ctx["vital"] = rng.choice(("血压 190/116", "血糖 32.6", "血氧 68%", "体温 39.5℃", "心率 208"))
        ctx["project"] = rng.choice(("三号楼主体结构", "冷链仓储改造", "地铁配套管廊", "跨境电商海外仓", "厂区屋顶光伏"))
        ctx["company"] = rng.choice(("宏远建工", "星辰智造", "恒泰物流", "嘉禾食品", "联创电子"))
        ctx["job"] = persona.occupation
        ctx["dialect"] = persona.dialect
        return ctx

    _NON_ROLE_SLOTS = frozenset({
        "self_name", "amount", "amount2", "amount_value", "date", "date2", "city", "hospital",
        "legal_place", "place", "item", "symptom", "med", "vital", "project", "company", "job",
        "dialect", "dialect_line", "rhet_line", "counter_name", "role_name", "impact", "rest",
        "peak", "pause", "_relations", "_dialect_fn", "_rhetoric", "self_persona",
    })

    def _ensure_slots(self, ctx: Dict[str, Any], rng: random.Random, primary: EventFamily,
                      secondary: Optional[EventFamily], trap: Optional[TrapSpec],
                      rhetoric: str) -> None:
        """扫描全部待渲染模具，补齐缺失的角色槽位（防模板 KeyError 漏网）。"""

        templates: List[str] = []
        families = [primary] + ([secondary] if secondary is not None else [])
        for family in families:
            templates.extend(family.other_lines)
            templates.extend(family.user_lines)
            templates.extend(family.fact_lines)
            for _app, sender, content in family.app_keys:
                templates.extend([sender, content])
        if trap is not None:
            templates.extend([trap.claim_line, trap.counter_line, trap.fact_line])
        if rhetoric in RHETORIC_FACTS:
            templates.extend(list(RHETORIC_FACTS[rhetoric]["fact_lines"]))
        placeholders = set()
        for template in templates:
            for token in re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", template):
                placeholders.add(token)
        for token in sorted(placeholders - self._NON_ROLE_SLOTS):
            if token in ctx:
                continue
            ctx[token] = self._synthesize_person(rng, token)

    def _self_nickname(self, rng: random.Random, persona: Persona) -> str:
        surname = rng.choice(SURNAMES)
        if persona.age >= 40:
            return f"老{surname}"
        if persona.age <= 22:
            return f"小{surname}"
        return f"{surname}{rng.choice(NAME_BANK['male' if persona.gender == 'm' else 'female'])}"

    def _persona_slots(self, persona: Persona, rng: random.Random) -> Dict[str, Any]:
        slots: Dict[str, Any] = {"_relations": {}}
        relations: Dict[str, Any] = {}
        for relation in persona.companions:
            role = relation.role
            if role in slots:
                continue
            slots[role] = relation.name
            relations[role] = relation
        slots["_relations"] = relations
        slots["self_persona"] = persona
        return slots

    def _synthesize_person(self, rng: random.Random, role: str) -> str:
        if role in {"self", "user"}:
            return "我"
        default = ROLE_REGISTRY.get(role, (f"spk_{role}", "对方"))[1]
        surname = rng.choice(SURNAMES)
        if role in {"child", "child_elder", "child_younger"}:
            return f"{default}" if default in {"孩子"} else default
        if role in {"officer", "doctor", "nurse", "lawyer", "teacher", "police", "examiner", "insurer", "vet",
                    "patient_family", "community", "village_head", "rescuer"}:
            return f"{surname}{'医生' if role == 'doctor' else default}"
        return f"{surname}{default}"

    def _speaker_id_for(self, ctx: Dict[str, Any], role: str) -> str:
        relations = ctx.get("_relations", {})
        if role in relations:
            return relations[role].speaker_id
        return ROLE_REGISTRY.get(role, (f"spk_{role}", ""))[0]

    def _plan_speakers(self, rng: random.Random, ctx: Dict[str, Any], persona: Persona,
                       primary: EventFamily, secondary: Optional[EventFamily],
                       difficulty: str, focus_stream: str) -> Dict[str, Any]:
        base_range = {
            "EASY": (3, 6),
            "MEDIUM": (4, 10),
            "HARD": (6, 18),
            "ADVERSARIAL": (8, 24),
        }[difficulty]
        if focus_stream == "voiceprint":
            low = max(base_range[0], 8)
            high = min(24, base_range[1] + 8)
            if low > high:
                low = high
        else:
            low, high = base_range
        total = rng.randint(low, high)
        key_roles = ["self"]
        for role in list(primary.roles):
            if role != "self":
                key_roles.append(role)
        if secondary is not None:
            key_roles.extend([r for r in secondary.roles if r != "self"][:1])
        key_speakers = []
        for role in key_roles:
            if role == "self":
                key_speakers.append("spk_user")
            else:
                key_speakers.append(self._speaker_id_for(ctx, role))
        key_speakers = list(dict.fromkeys(key_speakers))
        noise_pool = [role[0] for role in SPEAKER_ROLES]
        noise_count = max(1, total - len(key_speakers))
        detected = list(key_speakers)
        for idx in range(noise_count):
            detected.append(noise_pool[idx % len(noise_pool)] if idx < len(noise_pool) else f"spk_stranger_{idx:02d}")
        detected = list(dict.fromkeys(detected))
        if len(detected) > 24:
            detected = detected[:24]
        return {
            "detected": detected,
            "key": key_speakers,
            "noise_speakers": [s for s in detected if s not in key_speakers],
            "overlap": [],
        }

    # ---------------------------------------------------------------- 语料渲染
    def _render(self, template: str, ctx: Dict[str, Any], rng: random.Random,
                extra: Optional[Dict[str, Any]] = None) -> str:
        local = dict(ctx)
        if extra:
            local.update(extra)
        # 延迟解析：方言原话与修辞原话按需注入
        if "{dialect_line}" in template and "dialect_line" not in local:
            local["dialect_line"] = self._dialect_line(rng, ctx.get("dialect", _DIALECT_FALLBACK),
                                                       ctx.get("_dialect_fn", "money"))
        if "{rhet_line}" in template and "rhet_line" not in local:
            local["rhet_line"] = self._rhetoric_line(rng, ctx.get("_rhetoric", "none"))
        try:
            return template.format(**local)
        except KeyError as exc:  # 模板缺槽位属于出题侧缺陷，必须显式暴露
            raise KeyError(f"模板缺少槽位 {exc} : {template}") from exc

    def _dialect_line(self, rng: random.Random, dialect: str, function: str) -> str:
        pack = DIALECT_PACKS.get(dialect) or DIALECT_PACKS[_DIALECT_FALLBACK]
        lines = list(pack.get(function) or pack.get("money") or ())
        if not lines:
            pack = DIALECT_PACKS[_DIALECT_FALLBACK]
            lines = list(pack.get(function) or pack["money"])
        vocab = DIALECT_FUNCTION_FILTER.get(function)
        if vocab:
            narrowed = [line for line in lines if any(token in line for token in vocab)]
            if narrowed:
                lines = narrowed
            else:
                pain_lines = list(pack.get("pain") or lines)
                narrowed = [line for line in pain_lines if any(token in line for token in vocab)]
                lines = narrowed or pain_lines
        return rng.choice(lines)

    def _rhetoric_line(self, rng: random.Random, kind: str) -> str:
        spec = RHETORIC_SPECS[kind]
        return rng.choice(list(spec["utterances"]))

    # ---------------------------------------------------------------- 数据流发射
    def _emit_noise(self, rng: random.Random, acoustic: AcousticTopology, speaker_plan: Dict[str, Any],
                    db: float, difficulty: str, focus_stream: str,
                    mic_stream: List[Dict[str, Any]], junk_ids: List[str]) -> None:
        base = {"EASY": 2, "MEDIUM": 3, "HARD": 3, "ADVERSARIAL": 4}[difficulty]
        count = base + (1 if acoustic.aid in {"A01", "A03", "A06"} else 0)
        if focus_stream == "mic":
            count += 1
        noise_speakers = speaker_plan["noise_speakers"] or ["spk_stranger_noise"]
        line_pool = list(acoustic.junk_lines)
        rng.shuffle(line_pool)
        extra_pool = [line for _role, _label, lines in SPEAKER_ROLES for line in lines]
        rng.shuffle(extra_pool)
        for idx in range(count):
            sid = noise_speakers[idx % len(noise_speakers)]
            if idx < len(line_pool):
                text = line_pool[idx]
            elif idx - len(line_pool) < len(extra_pool):
                text = extra_pool[idx - len(line_pool)]
            else:
                text = rng.choice(list(acoustic.junk_lines))
            snippet_id = f"mic_{len(mic_stream) + 1:02d}"
            entry: Dict[str, Any] = {
                "sid": snippet_id,
                "spk": sid,
                "db": round(db + rng.uniform(-2.0, 2.0), 1),
                "text": text,
                "junk": True,
            }
            if rng.random() < acoustic.overlap_rate:
                others = [s for s in noise_speakers if s != sid] or ["spk_user"]
                entry["overlap"] = rng.choice(others)
                speaker_plan["overlap"].append(snippet_id)
            mic_stream.append(entry)
            junk_ids.append(snippet_id)

    def _emit_junk_apps(self, rng: random.Random, persona: Persona, difficulty: str, focus_stream: str,
                        app_stream: List[Dict[str, Any]], junk_ids: List[str]) -> None:
        base = {"EASY": 2, "MEDIUM": 2, "HARD": 3, "ADVERSARIAL": 4}[difficulty]
        count = base + (1 if focus_stream == "app" else 0)
        pool = list(_JUNK_APP_TEMPLATES)
        rng.shuffle(pool)
        for idx in range(count):
            template = pool[idx % len(pool)]
            msg_id = f"msg_{len(app_stream) + 1:02d}"
            app_stream.append({
                "mid": msg_id,
                "app": template[0],
                "sender": template[1],
                "content": template[2],
                "junk": True,
            })
            junk_ids.append(msg_id)

    def _emit_primary(self, rng: random.Random, persona: Persona, family: EventFamily, ctx: Dict[str, Any],
                      speaker_plan: Dict[str, Any], flags: Dict[str, Any],
                      mic_stream: List[Dict[str, Any]], app_stream: List[Dict[str, Any]],
                      dialogue_stream: List[Dict[str, Any]], junk_ids: List[str], refs: Dict[str, str]) -> None:
        dialect = flags["dialect"]
        focus_stream = flags["focus_stream"]
        db = flags["db"]
        ctx = dict(ctx)
        ctx["_dialect_fn"] = family.dialect_fn
        ctx["_rhetoric"] = "none"

        # 1) 关键交互人原话（MIC）
        other_line = self._render(rng.choice(family.other_lines), ctx, rng)
        role_key, _, spoken = other_line.partition(">")
        spoken = spoken or role_key
        speaker_role = role_key if role_key in ROLE_REGISTRY or role_key in ctx else "coworker"
        snippet_id = f"mic_{len(mic_stream) + 1:02d}"
        mic_stream.append({
            "sid": snippet_id,
            "spk": self._speaker_id_for(ctx, speaker_role),
            "db": round(db + rng.uniform(-1.0, 1.0), 1),
            "text": spoken,
            "junk": False,
        })
        refs["primary_mic"] = snippet_id

        # 2) 方言关键原话（同一交互人以方言重复施压/呼救）
        dialect_speaker = speaker_role if speaker_role != "self" else "coworker"
        dialect_snippet = f"mic_{len(mic_stream) + 1:02d}"
        mic_stream.append({
            "sid": dialect_snippet,
            "spk": self._speaker_id_for(ctx, dialect_speaker),
            "db": round(db + rng.uniform(-1.5, 1.5), 1),
            "text": self._dialect_line(rng, dialect, family.dialect_fn),
            "junk": False,
            "dialect": f"转写自{DIALECT_PACKS.get(dialect, DIALECT_PACKS['generic'])['name']}",
        })
        refs["primary_dialect"] = dialect_snippet

        # 3) 关键 APP 消息（银行/法院/医院/平台）
        for idx, (app, sender, content) in enumerate(family.app_keys):
            msg_id = f"msg_{len(app_stream) + 1:02d}"
            resolved_sender = content and self._render(sender, ctx, rng) or sender
            app_stream.append({
                "mid": msg_id,
                "app": app,
                "sender": resolved_sender,
                "content": self._render(content, ctx, rng),
                "junk": False,
            })
            refs.setdefault("primary_app", msg_id)

        # 4) 佩戴者原话 / 自言自语
        user_line = self._render(rng.choice(family.user_lines), ctx, rng)
        utter_id = f"ut_{len(dialogue_stream) + 1:02d}"
        dialogue_stream.append({
            "uid": utter_id,
            "text": user_line,
            "scene": self._scene_for(rng, persona, family),
            "junk": False,
        })
        refs.setdefault("primary_dialogue", utter_id)

        # 5) 聚焦流决定主证据落点（保证数据流配比不是空话；溯源不得指向平庸基线）
        if focus_stream == "sensor" and refs.get("sensor_abnormal"):
            refs["primary"] = "sensor"
        elif focus_stream == "app" and "primary_app" in refs:
            refs["primary"] = refs["primary_app"]
        elif focus_stream == "dialogue":
            refs["primary"] = refs["primary_dialogue"]
        elif focus_stream == "voiceprint":
            refs["primary"] = refs["primary_mic"]
            if mic_stream and len(mic_stream) > 0:
                key_entry = next((entry for entry in mic_stream if entry["sid"] == refs["primary_mic"]), None)
                noise = [s for s in speaker_plan["noise_speakers"] if s != key_entry.get("spk")]
                if key_entry is not None and noise:
                    key_entry["overlap"] = noise[0]
        else:
            refs["primary"] = refs["primary_mic"]

    def _emit_secondary(self, rng: random.Random, persona: Persona, family: EventFamily, ctx: Dict[str, Any],
                        speaker_plan: Dict[str, Any], db: float, mic_stream: List[Dict[str, Any]],
                        app_stream: List[Dict[str, Any]], dialogue_stream: List[Dict[str, Any]],
                        junk_ids: List[str], refs: Dict[str, str]) -> None:
        local = dict(ctx)
        local["_dialect_fn"] = family.dialect_fn
        line = self._render(rng.choice(family.other_lines), local, rng)
        role_key, _, spoken = line.partition(">")
        spoken = spoken or role_key
        speaker_role = role_key if (role_key in ROLE_REGISTRY or role_key in local) else "coworker"
        snippet_id = f"mic_{len(mic_stream) + 1:02d}"
        mic_stream.append({
            "sid": snippet_id,
            "spk": self._speaker_id_for(local, speaker_role),
            "db": round(db + rng.uniform(-2.0, 1.0), 1),
            "text": spoken,
            "junk": False,
        })
        refs["secondary"] = snippet_id
        if family.app_keys:
            app, sender, content = family.app_keys[0]
            msg_id = f"msg_{len(app_stream) + 1:02d}"
            app_stream.append({
                "mid": msg_id,
                "app": app,
                "sender": self._render(sender, local, rng),
                "content": self._render(content, local, rng),
                "junk": False,
            })
            refs["secondary_app"] = msg_id

    def _emit_trap(self, rng: random.Random, trap: TrapSpec, ctx: Dict[str, Any], speaker_plan: Dict[str, Any],
                   db: float, mic_stream: List[Dict[str, Any]], app_stream: List[Dict[str, Any]],
                   junk_ids: List[str], refs: Dict[str, str]) -> Optional[str]:
        claimant = ctx.get("stranger") or ctx.get("coworker") or "对方"
        local = dict(ctx)
        local["counter_name"] = claimant
        local["role_name"] = claimant

        claim_snippet = f"mic_{len(mic_stream) + 1:02d}"
        mic_stream.append({
            "sid": claim_snippet,
            "spk": self._speaker_id_for(ctx, "stranger" if "stranger" in ctx else "coworker"),
            "db": round(db + rng.uniform(-1.0, 1.0), 1),
            "text": self._render(trap.claim_line, local, rng),
            "junk": trap.junk_claim,
        })
        if trap.junk_claim:
            junk_ids.append(claim_snippet)

        if trap.claim_app:
            msg_id = f"msg_{len(app_stream) + 1:02d}"
            app_stream.append({
                "mid": msg_id,
                "app": trap.claim_app,
                "sender": claimant,
                "content": self._render(trap.claim_line, local, rng),
                "junk": trap.junk_claim,
            })
            refs["trap_claim"] = msg_id
            if trap.junk_claim:
                junk_ids.append(msg_id)

        counter_text = self._render(trap.counter_line, local, rng)
        if trap.counter_app == "SensorStream":
            refs["trap_counter"] = "sensor"
            return counter_text
        msg_id = f"msg_{len(app_stream) + 1:02d}"
        app_stream.append({
            "mid": msg_id,
            "app": trap.counter_app or trap.claim_app,
            "sender": "系统通知",
            "content": counter_text,
            "junk": False,
            "role": "counter",
        })
        refs["trap_counter"] = msg_id
        return None

    def _emit_rhetoric(self, rng: random.Random, kind: str, ctx: Dict[str, Any], speaker_plan: Dict[str, Any],
                       db: float, dialogue_stream: List[Dict[str, Any]], junk_ids: List[str],
                       refs: Dict[str, str]) -> None:
        spec = RHETORIC_SPECS[kind]
        utter_id = f"ut_{len(dialogue_stream) + 1:02d}"
        dialogue_stream.append({
            "uid": utter_id,
            "text": rng.choice(list(spec["utterances"])),
            "scene": "独自一人时低声自语",
            "junk": bool(spec["is_junk"]),
            "rhet": kind,
        })
        if spec["is_junk"]:
            junk_ids.append(utter_id)
        else:
            refs["rhetoric"] = utter_id

    def _emit_banter(self, rng: random.Random, persona: Persona, ctx: Dict[str, Any],
                     speaker_plan: Dict[str, Any], db: float, mic_stream: List[Dict[str, Any]],
                     junk_ids: List[str]) -> None:
        role, _label, lines = rng.choice(SPEAKER_ROLES)
        snippet_id = f"mic_{len(mic_stream) + 1:02d}"
        mic_stream.append({
            "sid": snippet_id,
            "spk": role,
            "db": round(db + rng.uniform(-3.0, 1.0), 1),
            "text": rng.choice(list(lines)),
            "junk": True,
        })
        junk_ids.append(snippet_id)

    def _emit_junk_self_talk(self, rng: random.Random, difficulty: str,
                             dialogue_stream: List[Dict[str, Any]], junk_ids: List[str]) -> None:
        count = {"EASY": 0, "MEDIUM": 1, "HARD": 1, "ADVERSARIAL": 1}[difficulty]
        for _ in range(count):
            utter_id = f"ut_{len(dialogue_stream) + 1:02d}"
            dialogue_stream.append({
                "uid": utter_id,
                "text": rng.choice(list(JUNK_SELF_TALK)),
                "scene": "自言自语的口头禅发泄",
                "junk": True,
            })
            junk_ids.append(utter_id)

    def _finalize_speakers(self, speaker_plan: Dict[str, Any], mic_stream: List[Dict[str, Any]],
                           dialogue_stream: List[Dict[str, Any]], keep_planned: bool = False) -> Dict[str, Any]:
        speakers: List[str] = ["spk_user"]
        for entry in mic_stream:
            speakers.append(entry["spk"])
        for speaker in speaker_plan["key"]:
            if speaker not in speakers and speaker in speaker_plan["detected"] and speaker == "spk_user":
                speakers.append(speaker)
        detected = list(dict.fromkeys(speakers))
        planned = [sid for sid in speaker_plan["detected"] if sid not in detected]
        detected_only: List[str] = []
        if keep_planned and planned:
            # 声纹聚类记录覆盖全天，允许存在"当日检测到但本题无切片"的散杂人声（必须被剥离，不得当证据）
            detected_only = planned[: max(0, 24 - len(detected))]
            detected.extend(detected_only)
        if len(detected) < 3:
            for role, _label, _lines in SPEAKER_ROLES:
                if role not in detected:
                    detected.append(role)
                if len(detected) >= 3:
                    break
        detected = detected[:24]
        overlap_ids = [entry["sid"] for entry in mic_stream if "overlap" in entry]
        speaker_plan = dict(speaker_plan)
        speaker_plan["detected"] = detected
        speaker_plan["key"] = [sid for sid in speaker_plan["key"] if sid in detected] or ["spk_user"]
        speaker_plan["overlap"] = overlap_ids
        speaker_plan["detected_only"] = detected_only
        return speaker_plan

    def _scene_for(self, rng: random.Random, persona: Persona, family: EventFamily) -> str:
        pool = [persona.home_scene, persona.work_scene, "独自坐在车里", "走廊尽头接电话"]
        if family.domain == "dim:health":
            pool.append("捂着胸口靠墙蹲下")
        return rng.choice(pool)

    def _tone_for(self, family: EventFamily) -> str:
        if family.severity == "critical":
            return "压抑忍痛"
        if family.domain == "dim:finance":
            return "焦躁"
        return "疲惫"

    # ---------------------------------------------------------------- 传感器流
    def _build_sensor(self, rng: random.Random, profile_id: str, persona: Persona,
                      focus_stream: str) -> Dict[str, Any]:
        profile = SENSOR_PROFILES[profile_id]
        low, high = profile["g_range"]  # type: ignore[assignment]
        detail = 6 if focus_stream == "sensor" else 4
        g_points = detail + 2 if profile_id in {"S01", "S02", "S06"} else detail
        series: List[float] = []
        if profile_id == "S01":
            spike = round(rng.uniform(low, high), 2)
            series = [round(rng.uniform(0.95, 1.15), 2) for _ in range(detail)]
            series.insert(rng.randrange(1, 3), spike)
            series.extend([round(rng.uniform(0.92, 1.02), 2)] * 4)  # 撞击后长时间静止
        elif profile_id == "S02":
            series = [round(rng.uniform(1.2, 2.6), 2) for _ in range(detail)]
            series.insert(rng.randrange(0, 2), round(rng.uniform(low, high), 2))
            series.extend([round(rng.uniform(1.4, 3.2), 2) for _ in range(3)])  # 连续挥拍/鼓掌
        elif profile_id in {"S03"}:
            series = [round(rng.uniform(0.94, 1.06), 2) for _ in range(detail)]
        elif profile_id == "S04":
            series = [round(rng.uniform(0.90, 1.25), 2) for _ in range(detail)]
        elif profile_id == "S06":
            series = [round(rng.uniform(low, high), 2) for _ in range(g_points)]
        else:
            series = [round(rng.uniform(low, high), 2) for _ in range(detail)]

        hr_low, hr_high = profile["hr_range"]  # type: ignore[assignment]
        pvc_low, pvc_high = profile["pvc_range"]  # type: ignore[assignment]
        baro_low, baro_high = profile["baro_range"]  # type: ignore[assignment]
        sensor: Dict[str, Any] = {
            "sample_id": "sen_01",
            "profile": profile_id,
            "raw_imu_g_force": series,
            "heart_rate_bpm": rng.randint(hr_low, hr_high),
            "pvc_burst_count": rng.randint(pvc_low, pvc_high),
            "baro_hpa": round(rng.uniform(baro_low, baro_high), 1),
            "motion_state": profile["motion_state"],
            "spO2_pct": (rng.randint(95, 99) if profile_id == "S00" else
                         (rng.randint(84, 92) if profile_id == "S04" else rng.randint(89, 99))),
            "gps_loc": rng.choice((PLACE_BANK.get(persona.region) or PLACE_BANK["henan"])["city"]),
        }
        if profile_id == "S04":
            sensor["sinus_pause_s"] = round(rng.uniform(3.2, 4.2), 1)
        if profile_id == "S05":
            sensor["baro_drop_hpa"] = round(rng.uniform(16.0, 24.0), 1)
            sensor["baro_trend_hpa_per_3h"] = -round(rng.uniform(5.5, 8.0), 1)
            sensor["ambient_temp_c"] = round(rng.uniform(6.0, 15.0), 1)
        if profile_id == "S06":
            sensor["cadence_spm"] = rng.randint(168, 182)
            sensor["pace_min_per_km"] = "4'30\""
        if profile_id == "S03":
            rest_hr = rng.randint(58, 68)
            peak_hr = rng.randint(190, 212)
            sensor["hr_rest_bpm"] = rest_hr
            sensor["hr_max_bpm"] = peak_hr
            sensor["hr_onset_note"] = f"由静息 {rest_hr}bpm 突升至 {peak_hr}bpm"
        if profile_id == "S01":
            sensor["impact_peak_g"] = round(max(series), 2)
            sensor["post_impact_still_s"] = rng.randint(25, 300)
        if profile_id == "S02":
            sensor["impact_peak_g"] = round(max(series), 2)
            sensor["false_impact_note"] = "单峰高 G 但后续运动连续，无坠落静止段"
        return sensor

    # ---------------------------------------------------------------- 事实与垃圾
    def _build_facts(self, rng: random.Random, primary: EventFamily, secondary: Optional[EventFamily],
                     trap: Optional[TrapSpec], rhetoric: str, sensor_profile: str,
                     sensor_stream: Dict[str, Any], ctx: Dict[str, Any], refs: Dict[str, str],
                     focus_stream: str) -> List[Dict[str, Any]]:
        facts: List[Dict[str, Any]] = []

        def add(dimension: str, intent: str, keywords: Sequence[str], core_content: str,
                source_ref: str, extra_anchors: Sequence[str] = ()) -> None:
            anchors = self._collect_anchors(core_content, ctx, extra_anchors)
            facts.append({
                "fact_id": f"fact_{len(facts) + 1:02d}",
                "dimension_id": dimension,
                "semantic_intent": intent,
                "anchor_entities": anchors,
                "directional_keywords": list(keywords),
                "core_content": core_content,
                "source_ref_id": source_ref,
                "confidence": 1.0,
            })

        tail_persons = self._tail_persons(ctx, primary, secondary)
        tail_person = rng.choice(tail_persons)
        primary_content = self._render(rng.choice(primary.fact_lines), ctx, rng)
        primary_content = self._enrich_fact(rng, primary_content, primary.domain, tail_persons)
        primary_content = self._dedupe_core(rng, primary_content, primary.domain, tail_persons, ctx)
        primary_ref = refs.get("primary", refs.get("primary_mic", "mic_01"))
        if primary_ref == "sensor":
            primary_ref = sensor_stream["sample_id"]
        if primary_ref == "sensor" and not refs.get("sensor_abnormal"):
            primary_ref = refs.get("primary_mic", "mic_01")
        add(primary.domain, primary.intent, primary.keywords, primary_content, primary_ref)


        # 波形异常事实（冲击坠落 / 恶性心律失常 / 窦性停搏）属 P0 安全证据：
        # 优先级仅次于主事件，先于次事件与陷阱落位；且恒属生理危机域，
        # 不得因为主事件发生在职场或家庭就把它错记成别维事实。
        if sensor_profile in {"S01", "S03", "S04"}:
            sensor_extra = {
                "impact": sensor_stream.get("impact_peak_g", ""),
                "rest": sensor_stream.get("hr_rest_bpm", 60),
                "peak": sensor_stream.get("hr_max_bpm", 200),
                "pause": sensor_stream.get("sinus_pause_s", 3.8),
            }
            content = self._render(_SENSOR_FACT_LINES[sensor_profile], ctx, rng, sensor_extra)
            add("dim:health", _SENSOR_FACT_INTENTS[sensor_profile],
                _SENSOR_FACT_KEYWORDS[sensor_profile], content, sensor_stream["sample_id"])

        if secondary is not None and len(facts) < 4:
            content = self._render(rng.choice(secondary.fact_lines), ctx, rng)
            content = self._enrich_fact(rng, content, secondary.domain, tail_persons)
            content = self._dedupe_core(rng, content, secondary.domain, tail_persons, ctx)
            add(secondary.domain, secondary.intent, secondary.keywords, content,
                refs.get("secondary", refs.get("secondary_app", "mic_01")))

        if trap is not None:
            local = dict(ctx)
            local["counter_name"] = ctx.get("stranger") or ctx.get("coworker") or "对方"
            local["role_name"] = local["counter_name"]
            content = self._render(trap.fact_line, local, rng)
            add(primary.domain, trap.intent, trap.keywords, content, refs.get("trap_counter", "msg_01"))

        if rhetoric in RHETORIC_FACTS:
            meta = RHETORIC_FACTS[rhetoric]
            dimension = meta["dimension"] or primary.domain
            content = self._render(rng.choice(list(meta["fact_lines"])), ctx, rng)
            content = self._dedupe_core(rng, content, dimension, tail_persons, ctx)
            add(dimension, str(meta["intent"]), list(meta["keywords"]), content,
                refs.get("rhetoric", "ut_01"))

        return facts

    def _enrich_fact(self, rng: random.Random, text: str, domain: str, tail_persons: List[str]) -> str:
        """给事实补一句"记录视角"的客观旁证，并在同一次渲染内先做一轮去重。

        补语只描述在场者的客观动作（记录 / 陪同 / 归档），不引入任何未被证据支持的新事件。
        """

        if rng.random() >= 0.45:
            return text
        tails = _FACT_TAIL_HEALTH if domain == "dim:health" else _FACT_TAIL_CONFLICT
        person = rng.choice(tail_persons)
        enriched = text + rng.choice(tails).format(tail_person=person)
        if rng.random() < 0.2:
            others = [value for value in tail_persons if value != person] or [person]
            second = rng.choice(tails).format(tail_person=rng.choice(others))
            if second not in enriched:
                enriched += second
        return enriched

    def _dedupe_core(self, rng: random.Random, text: str, domain: str, tail_persons: List[str],
                     ctx: Dict[str, Any]) -> str:
        """整卷级去重护栏：同一份卷子里的事实描述必须逐条唯一（确定性重渲染，最多 12 次）。"""

        seen = self._seen_core
        if text not in seen:
            seen.add(text)
            return text
        tails = _FACT_TAIL_HEALTH if domain == "dim:health" else _FACT_TAIL_CONFLICT
        for _ in range(12):
            candidate = text + rng.choice(tails).format(tail_person=rng.choice(tail_persons))
            if candidate not in seen:
                seen.add(candidate)
                return candidate
        candidate = f"{text}，{rng.choice(tail_persons)}在{ctx['date2']}又补录了一次现场情况"
        while candidate in seen:
            candidate += "并另附说明"
        seen.add(candidate)
        return candidate

    def _tail_persons(self, ctx: Dict[str, Any], primary: EventFamily,
                      secondary: Optional[EventFamily]) -> List[str]:
        """补语可用的在场者候选：优先真名（2~4 字），其次角色代称（如"同办公室老师"）。"""

        roles: List[str] = []
        for family in (primary, secondary):
            if family is None:
                continue
            roles.extend([role for role in family.roles if role != "self"])
        values = [ctx[role] for role in roles if isinstance(ctx.get(role), str) and ctx.get(role) != "我"]
        named = [value for value in values if 1 < len(value) <= 4]
        ordered = list(dict.fromkeys(named + values))
        return ordered or ["在场人员"]

    def _collect_anchors(self, text: str, ctx: Dict[str, Any], extra: Sequence[str]) -> List[str]:
        anchors: List[str] = []
        for value in list(extra):
            if value and str(value) in text:
                anchors.append(str(value))
        preferred = (
            "self_name", "creditor", "spouse", "boss", "doctor", "child", "parent", "officer", "lawyer",
            "partner", "supplier", "client", "tenant", "landlord", "merchant", "neighbor", "teacher", "vet",
            "amount", "date", "date2", "place", "hospital", "legal_place", "item", "symptom", "med", "vital",
            "city", "project", "company", "stranger",
        )
        for key in preferred:
            value = ctx.get(key)
            if isinstance(value, str) and value and value in text and value not in anchors:
                anchors.append(value)
        for value in ctx.values():
            if isinstance(value, str) and value and value in text and value not in anchors:
                anchors.append(value)
        return anchors[:6]


# --------------------------------------------------------------------------------------
# 传感器事实模板（用于"传感器流聚焦"题的主证据）
# --------------------------------------------------------------------------------------
_SENSOR_FACT_LINES: Dict[str, str] = {
    "S01": "{self_name}的手环记录到一次 {impact}G 的剧烈冲击，随后长时间静止无动作，属高危坠落特征，需立即确认伤情",
    "S03": "{self_name}在夜间静息状态下心率由 {rest}bpm 突升至 {peak}bpm 并伴随高频室性早搏阵发，属恶性心律失常事件",
    "S04": "{self_name}出现长达 {pause} 秒的窦性停搏、心率跌至三十余次，身体失衡失速下沉，属缓慢性心脏停搏危象",
}
_SENSOR_FACT_INTENTS: Dict[str, str] = {
    "S01": "HIGH_G_IMPACT_FALL_EVENT",
    "S03": "MALIGNANT_ARRHYTHMIA_BURST",
    "S04": "CARDIAC_SINUS_ARREST",
}
_SENSOR_FACT_KEYWORDS: Dict[str, Sequence[str]] = {
    "S01": ("剧烈冲击", "坠落风险", "长时间静止", "高 G 值", "紧急确认伤情", "疑似骨折"),
    "S03": ("恶性心律失常", "室性早搏阵发", "心率飙升", "夜间静息", "心悸胸闷", "紧急就医"),
    "S04": ("窦性停搏", "心率骤降", "失速下沉", "晕厥风险", "缓慢性心律失常", "立即急救"),
}

# 事实细节补充语：只做"记录视角"的客观补全，不引入未被证据支持的新事实
_FACT_TAIL_CONFLICT: Tuple[str, ...] = (
    "，{tail_person}全程在场",
    "，{tail_person}劝了很久才把双方拉开",
    "，{tail_person}事后逐条做了书面记录",
    "，{tail_person}与当事人各执一词",
    "，{tail_person}当场用手机拍了照留存",
    "，{tail_person}说会继续跟进这件事",
    "，{tail_person}被叫来一起作证",
    "，{tail_person}一直在旁边帮着算账",
    "，{tail_person}把每一笔都记在了本子上",
    "，{tail_person}来回跑了两趟才把手续补齐",
    "，{tail_person}说该讲的话已经讲清楚了",
    "，{tail_person}把通话记录也一并保存了",
    "，{tail_person}当时正在隔壁忙别的",
    "，{tail_person}提醒对方不要再改口",
    "，{tail_person}把过程复述了一遍",
    "，{tail_person}不肯在调解书上签字",
)
_FACT_TAIL_HEALTH: Tuple[str, ...] = (
    "，{tail_person}随后赶到陪同",
    "，{tail_person}已作书面记录",
    "，{tail_person}协助完成了初步处置",
    "，{tail_person}交代了后续注意事项",
    "，{tail_person}在场交接了生命体征",
    "，{tail_person}把检查结果归档了",
    "，随访由{tail_person}负责安排",
    "，用药调整由{tail_person}跟进",
    "，{tail_person}把监护数据打印了一份",
    "，{tail_person}让先观察半小时再说",
    "，{tail_person}把既往用药史问了一遍",
    "，{tail_person}交代了复诊时间",
    "，{tail_person}在交接班时重点提了这件事",
    "，{tail_person}把体征数据核对了两遍",
    "，{tail_person}提醒不要自行停药",
    "，{tail_person}安排再抽一次血复查",
)

# 方言语用功能的语义过滤（同一"疼痛"语料内再分：头晕 / 胸闷 / 肢体）
DIALECT_FUNCTION_FILTER: Dict[str, Optional[Tuple[str, ...]]] = {
    "pain": None,
    "dizzy": ("晕", "昏", "眼", "转", "脑壳"),
    "chest": ("胸", "闷", "喘", "气", "心口", "压"),
    "limb": ("脚", "腿", "腰", "肿", "关节", "嘶", "疼"),
    "neuro": ("麻", "不利索", "手", "舌", "半边"),
}

# 垃圾 APP 消息模板（营销/砍一刀/验证码/刷屏，铁律四必须物理删除）
_JUNK_APP_TEMPLATES: Tuple[Tuple[str, str, str], ...] = (
    ("WeChat", "砍一刀互助群", "【帮我点一下】我只差0.01元就能提现100元现金！"),
    ("WeChat", "拼单福利群", "今日秒杀：9.9元抢三件套，链接已发，手慢无！"),
    ("SMS", "1069xxxx", "【XX银行】您的信用卡可提额至5万元，点击链接立即申请，退订回T"),
    ("SMS", "1069xxxx", "【验证码】您的登录验证码为 8846，5分钟内有效，请勿泄露"),
    ("SMS", "1069xxxx", "【XX教育】0元试听名师课，孩子提分就靠这个，点击领取"),
    ("Taobao", "官方活动", "您的购物车商品降价了，今晚八点前下单再减20元"),
    ("PDD", "多多果园", "您的水果树快饿死啦，快来浇水收获免费水果！"),
    ("WeChat", "小区业主群", "[表情包] 早上好，今天天气不错，大家注意防晒"),
    ("WeChat", "家族群", "转发这条消息给十个人，全家平安一整年"),
    ("Douyin", "直播通知", "您关注的主播开播啦，今晚抽奖送手机，快来！"),
    ("WeChat", "微商代理", "姐妹们，代理价拿货最后三天，错过再等一年！"),
    ("Meituan", "优惠券提醒", "您有 3 张优惠券即将过期，下单立减 15 元"),
    ("WeChat", "宠物群", "谁家狗狗走丢了？看到在小区门口转悠，附图"),
    ("QQ", "兴趣部落", "签到七天送会员，戳我领取"),
)


def validate_question(question: Dict[str, Any]) -> Any:
    """用 CleaningQuestion 契约验证题目结构（延迟导入，避免循环依赖）。"""

    from aios_core.simulation.cleaning_arena_protocol import CleaningQuestion

    return CleaningQuestion.model_validate(
        {key: value for key, value in question.items() if key in CleaningQuestion.model_fields}
    )


def factor_inventory() -> Dict[str, int]:
    """因子库规模（用于出题覆盖率审计）。"""

    return {
        "personas": len(PERSONAS),
        "event_families": sum(len(EVENT_FAMILIES[d]) for d in DOMAIN_IDS),
        "sensor_profiles": len(SENSOR_PROFILES),
        "acoustic_topologies": len(ACOUSTIC_TOPOLOGIES),
        "dialect_packs": len(DIALECT_PACKS),
        "speaker_roles": len(SPEAKER_ROLES),
        "traps": len(TRAP_SPECS),
        "rhetoric_specs": len(RHETORIC_SPECS),
    }


def audit_questions(questions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """对一批题目做覆盖率与自洽性审计（不依赖任何外部评分器）。"""

    total = 0
    domains: Dict[str, int] = {d: 0 for d in DOMAIN_IDS}
    difficulty: Dict[str, int] = {}
    focus: Dict[str, int] = {}
    traps: Dict[str, int] = {}
    dialects: Dict[str, int] = {}
    personas: Dict[str, int] = {}
    fact_count = 0
    junk_total = 0
    snippet_total = 0
    signatures: set = set()
    core_contents: set = set()
    duct_issues: List[str] = []
    speaker_counts: List[int] = []

    for question in questions:
        total += 1
        signature = json.dumps(question["factor_ids"], ensure_ascii=False, sort_keys=True)
        signatures.add(signature)
        core = "|".join(fact["core_content"] for fact in question["ground_truth_facts"])
        core_contents.add(core)

        sig = question["factor_ids"]
        domains[sig["domain"]] = domains.get(sig["domain"], 0) + 1
        difficulty[question["difficulty"]] = difficulty.get(question["difficulty"], 0) + 1
        focus[sig["focus_stream"]] = focus.get(sig["focus_stream"], 0) + 1
        personas[sig["demographic"]] = personas.get(sig["demographic"], 0) + 1
        dialects[sig["linguistic"]] = dialects.get(sig["linguistic"], 0) + 1
        if sig["trap"] != "T00":
            traps[sig["trap"]] = traps.get(sig["trap"], 0) + 1

        fact_count += len(question["ground_truth_facts"])
        junk_total += len(question["ground_truth_junk_ids"])
        ids = {s["sid"] for s in question["mic_stream"]}
        ids |= {m["mid"] for m in question["app_message_stream"]}
        ids |= {u["uid"] for u in question["user_dialogue_stream"]}
        ids.add(question["sensor_stream"]["sample_id"])
        snippet_total += len(ids)
        for junk in question["ground_truth_junk_ids"]:
            if junk not in ids:
                duct_issues.append(f"{question['question_id']} 垃圾ID不在片段集合: {junk}")
        for fact in question["ground_truth_facts"]:
            if fact["source_ref_id"] not in ids:
                duct_issues.append(f"{question['question_id']} 事实溯源ID不存在: {fact['source_ref_id']}")
            if len(fact["directional_keywords"]) < 6:
                duct_issues.append(f"{question['question_id']} 方向词簇不足6个: {fact['fact_id']}")
        speaker_counts.append(len(question["voiceprint_cluster"]["detected"]))
        for speaker in question["voiceprint_cluster"]["detected"]:
            if speaker not in {"spk_user"} and not speaker.startswith("spk_"):
                duct_issues.append(f"{question['question_id']} 非法声纹标识: {speaker}")

    return {
        "total": total,
        "unique_factor_signatures": len(signatures),
        "unique_core_contents": len(core_contents),
        "domains": domains,
        "domain_ratio": {k: round(v / max(total, 1), 4) for k, v in domains.items()},
        "difficulty": difficulty,
        "focus_streams": focus,
        "focus_ratio": {k: round(v / max(total, 1), 4) for k, v in focus.items()},
        "traps": traps,
        "dialects": dialects,
        "personas": personas,
        "facts_total": fact_count,
        "facts_per_question": round(fact_count / max(total, 1), 3),
        "junk_ratio": round(junk_total / max(snippet_total, 1), 4),
        "speaker_count_min": min(speaker_counts) if speaker_counts else 0,
        "speaker_count_max": max(speaker_counts) if speaker_counts else 0,
        "duct_issues": duct_issues[:20],
        "duct_issue_count": len(duct_issues),
    }
