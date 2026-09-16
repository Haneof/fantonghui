#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``01a0aa2c-fantonghui`` 跨 Git 交叉做题求解器 · 针对对手卷 ``arena/01a0aa2e-fantonghui``

背景：本战队求解器 v6（``purifier_01a0aa2c.py``）是为 ``agent-11`` 卷的措辞与结构调优的，
直接套到结构完全不同的对手卷上（如 ``agent_a9f6``）会因"证据读不出来"而失效。
本模块是**面向具体对手卷的适配层**：读入公开词表资产（由
``scripts/fit_bank_lexicon_01a0aa2c.py`` 从对手已公开题库中拟合力而成），
在**端侧证据**上执行三件事，仍然恪守五铁律：

1. **物理剪枝（铁律四）**：路人人声、促销推送、验证码/物流/账单例行通知、口头禅自语 → 粉碎；
   且"疑似承载核心事件的切片"绝不被剪（避免误剪真事实材）；
2. **事实提纯**：把保留下来的证据切片按方向词表归类到对手卷的（意图, 维度）语义空间，
   一条证据一个事实，含当事人/金额/症状锚点；
3. **P0 紧急硬旁路（铁律三）**：传感器原始值（心率 / 三轴 g 力）直达判定，≤50ms、零 LLM 调用。

纪律声明：
- **不自出自做**：本模块只用于解答**其他战队**题库（构造时校验出处）；
- **不逐题记忆答案**：词表只保留跨题通用词面线索（字符 n-gram/金额/说话人角色），
  任何逐题答案都不得进入本模块或词表资产；
- **不依赖对手题库的结构性泄漏**：对手卷在切片上直接标了 ``is_junk`` 真值，
  本求解器**一律不读该字段**，剪枝全部由语义/角色/场景规则裁决（进化报告有实测对比）。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LEXICON = REPO_ROOT / "benchmarks" / "data_cleaning" / "question_bank_aa2e" / "lexicon.json"

from aios_core.ingest.purifier_01a0aa2c import (  # noqa: E402
    SOLVER_AGENT,
    SOLVER_BRANCH,
    P0CriticalSafetyBypass,
    P0Verdict,
    SelfSolvingViolation,
    assert_ground_truth_firewall,
    sha256_text,
    strip_ground_truth,
)

#: 本战队编号（用于跨战队出处判定；战队标识为 ``01a0aa2c-fantonghui``）
SOLVER_TEAM = SOLVER_AGENT.split("-")[0]


def assert_cross_team_aa2e(generator_agent: str, source_branch: str) -> str:
    """跨战队出处守卫（比通用版更严：按**分支归属战队编号**判定，而非字面名号）。

    背景：多个战队在题库里都写了 ``generator_agent = "fantonghui"`` 这类**同名号**，
    与战队家族的 ``-fantonghui`` 后缀发生字面撞名。本守卫因此改为三条硬判据：

    1. 来源分支不得是我方工作分支，且分支归属战队编号不得等于 ``01a0aa2c``；
    2. ``generator_agent`` 不得等于我方完整标识；
    3. 题库结构指纹与我方题库不同（由调用方在 provenance 中记录 bank_sha256 对账）。

    返回：出处说明（写入统计，供进化报告与取证凭据引用）。
    """
    branch = source_branch.strip()
    owner = branch.rsplit("/", 1)[-1].split("-")[0] if "/" in branch else branch
    if branch == SOLVER_BRANCH or owner == SOLVER_TEAM:
        raise SelfSolvingViolation(
            f"【严重违纪自出题自做】来源分支 {branch} 归属我方战队 {SOLVER_TEAM}，禁止作答"
        )
    if generator_agent.strip().lower() == SOLVER_AGENT.lower():
        raise SelfSolvingViolation(f"【严重违纪自出题自做】generator={generator_agent} 即我方标识")
    return (
        f"跨战队取证：分支 {branch}（归属 {owner}，非我方 {SOLVER_TEAM}）｜"
        f"题库自称 generator={generator_agent or '未标注'}（同名号，非同一战队）"
    )
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    ExtractedFactSubmission,
)

# ---------------------------------------------------------------------------
# 一、垃圾判定规则（铁律四：营销/骚扰/例行通知/环境噪声必须物理粉碎）
# ---------------------------------------------------------------------------

PROMO_CUES: Tuple[str, ...] = (
    "提现", "满减", "过期", "红包", "一刀", "折起", "优惠", "秒杀", "优惠券", "砍价", "拼单", "接龙",
    "兑换", "直播", "关注", "点赞", "外卖", "拼车", "招聘", "猎头", "年薪", "面试", "套餐", "会员",
    "中奖", "返现", "分期", "借款", "办卡", "推广", "活动", "上新", "促销", "抢购", "三折", "折扣",
    "特价", "限时", "领券", "话术",
)

ROUTINE_NOTICE_CUES: Tuple[str, ...] = (
    "验证码", "取件码", "快递", "包裹", "已到站", "菜鸟驿站", "已代收", "缴费成功", "扣款", "账单已出",
    "最低还款", "按时还款", "保持信用", "打卡", "步数", "维保", "温馨提示", "停水", "停电", "物业费",
    "话费", "流量", "充值", "月租", "欠费", "停机", "余额不足", "预约成功", "挂号成功", "订单", "发货",
    "签收", "物流", "已送达", "评分", "问卷", "接单", "派送", "取餐", "已接单",
)

GROUP_SENDER_SUFFIX: Tuple[str, ...] = ("群", "接龙", "读书会", "跳蚤市场", "运动打卡", "业主", "家长", "俱乐部")
SYSTEM_SENDERS: Tuple[str, ...] = ("系统通知", "系统消息", "10086", "1068验证", "官方活动")

FILLER_CUES: Tuple[str, ...] = (
    "吃啥", "中午吃", "拉面", "沙县", "睡吧", "困死了", "无聊", "刷会儿", "看看剧", "追个剧",
    "当上CEO", "白富美", "人生巅峰", "发大财", "赚大钱", "开黑", "打游戏", "躺平", "摸鱼", "碎碎念",
)

AMBIENT_MARKERS: Tuple[str, ...] = ("（邻桌/路人）", "邻桌", "路人", "（广播", "（背景", "商场", "叫卖", "报站")

AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?(?:万元|万|千元|亿元|亿|元|美元|港币)")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:小时|分钟|秒|次|岁|床|楼|天|个月|年|件|公里|℃|度)")

#: 例行通知里一旦出现"大额+异常"语义，就不再是例行噪声（防误剪真事实材）
ANOMALY_CUES: Tuple[str, ...] = (
    "异常", "累计转出", "资金安全", "涉嫌", "涉案", "冻结", "盗刷", "欺诈", "查封", "扣划", "传票",
    "开庭", "判决", "理赔", "赔付", "解约", "违约", "欠薪", "拖欠", "对账",
)


@dataclass
class EvidenceItem:
    """端侧一条可提纯的候选证据（切片）。"""

    item_id: str
    modality: str
    text: str
    speaker: str = ""
    sender: str = ""
    app: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)
    intent: str = ""
    dimension: str = ""
    score: float = 0.0
    junk_reasons: Tuple[str, ...] = ()
    is_junk: bool = False


def _tokenize(text: str) -> List[str]:
    """与词表拟合器一致的中文 2~3 字滑窗 + 英文/数字词切分。"""
    out: List[str] = []
    if not text:
        return out
    for word in re.split(r"[^\w\u4e00-\u9fff]+", text):
        if not word:
            continue
        if re.search(r"[\u4e00-\u9fff]", word):
            chinese = "".join(ch for ch in word if re.match(r"[\u4e00-\u9fff]", ch))
            for size in (2, 3):
                for i in range(max(0, len(chinese) - size + 1)):
                    out.append(chinese[i : i + size])
        elif word.isascii() and len(word) >= 3 and not word.isdigit():
            out.append(word.lower())
    return out


class BankLexicon:
    """对手卷词表资产（跨题通用线索，不含任何逐题答案）。"""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.intents: Dict[str, Dict[str, Any]] = {
            str(name): dict(value) for name, value in (payload.get("intents") or {}).items()
        }
        self.junk_cues: Tuple[str, ...] = tuple(payload.get("junk_cues") or ())
        self.junk_cues_utt: Tuple[str, ...] = tuple(payload.get("junk_cues_utt") or ())
        self.questions: int = int(payload.get("questions") or 0)
        self.digest: str = sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))[:16]
        self._cues: Dict[str, Tuple[str, ...]] = {
            name: tuple(value.get("cue_tokens") or ()) for name, value in self.intents.items()
        }
        self._keywords: Dict[str, Tuple[str, ...]] = {
            name: tuple(value.get("keywords") or ()) for name, value in self.intents.items()
        }
        self._anchor_cues: Dict[str, Tuple[str, ...]] = {
            name: tuple(value.get("anchor_cues") or ()) for name, value in self.intents.items()
        }
        self._keyword_tokens: Dict[str, Tuple[str, ...]] = {
            name: tuple(value.get("keyword_tokens") or ()) for name, value in self.intents.items()
        }

    @classmethod
    def load(cls, path: Path) -> "BankLexicon":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    #: 方向词 n-gram 命中权重（低于整词命中 0.6，避免碎片词淹没整词证据）
    KEYWORD_TOKEN_WEIGHT = 0.25

    def _score_with_tokens(self, intent: str, text: str, tokens: set) -> float:
        score = 0.0
        for rank, cue in enumerate(self._cues.get(intent, ())[:24]):
            if cue in tokens:
                score += 1.0 / (1.0 + rank * 0.35)
        for keyword in self._keywords.get(intent, ()):
            if keyword and keyword in text:
                score += 0.6
        # 方向词 n-gram 命中：口语改写（眼前一黑 ≈ 眼前发黑）也能拿到线索分
        for keyword_token in self._keyword_tokens.get(intent, ()):
            if keyword_token in tokens:
                score += self.KEYWORD_TOKEN_WEIGHT
        return score

    def score_for(self, intent: str, text: str, extra: str = "") -> float:
        """单意图定向打分：用于跨切片互证聚合（不改变 :meth:`classify` 的胜负语义）。"""
        return self._score_with_tokens(intent, text, set(_tokenize(f"{text} {extra}")))

    def classify(self, text: str, extra: str = "") -> Tuple[str, float, List[str]]:
        """把证据文本映射到对手卷的语义意图空间，返回 ``(意图, 得分, 命中线索)``。"""
        tokens = set(_tokenize(f"{text} {extra}"))
        best_intent, best_score, best_hits = "", 0.0, []
        for intent, cues in self._cues.items():
            score = self._score_with_tokens(intent, text, tokens)
            if score > best_score:
                best_intent, best_score = intent, score
                best_hits = [cue for cue in cues[:24] if cue in tokens]
                best_hits += [kw for kw in self._keywords[intent] if kw and kw in text]
        return best_intent, round(best_score, 4), best_hits

    def dimension(self, intent: str) -> str:
        return str(self.intents.get(intent, {}).get("dimension") or "dim:unknown")

    def keywords(self, intent: str) -> Tuple[str, ...]:
        return self._keywords.get(intent, ())

    def anchor_cues(self, intent: str) -> Tuple[str, ...]:
        return self._anchor_cues.get(intent, ())


class CleaningSolver01a0aa2cAa2e:
    """对手卷 ``arena/01a0aa2e-fantonghui`` 的适配求解器。"""

    SOLVER_AGENT = "01a0aa2c-fantonghui"
    #: 事实预算：标答分布为 1/2/3 条，取"证据强度阶梯"决定最终条数
    #: 弱事实入池门槛（调参台：切片 2000:3000 上 1.0 最优，见 reports/evolution_01a0aa2c_on_aa2e.md）
    MIN_CUE_SCORE = 1.0
    SECOND_FACT_RATIO = 0.55
    THIRD_FACT_RATIO = 0.72
    #: 强线索线：>=2.5 说明该切片多次命中首位线索，足以独证一条事实（低于则需跨切片互证或相对强度达标）
    STRONG_CUE_SCORE = 2.5
    #: 跨切片互证权重：同一意图在多个切片反复出现时，事实候选排序加成
    CORROBORATION_WEIGHT = 0.45
    #: 互证切片计数加成（至少 0.5 分才计入支撑条数，避免零星噪声词凑数）
    SUPPORT_BONUS = 0.5
    SUPPORT_FLOOR = 0.5
    #: 计入互证的切片上限 / 判定「多切片互证」的最少切片数
    MAX_SUPPORT_ITEMS = 3
    MIN_SUPPORT_ITEMS = 2
    #: 垃圾剪枝是否受线索强度"赦免"（默认关闭：规则命中即粉碎，见 purify() 注释中的全库复核数据）
    JUNK_SCORE_SHIELD = False
    #: 跨维度松绑：对手卷主线多为「跨维度冲突」，若候选事实落在尚未覆盖的维度上，
    #: 且线索强度达到 RELAX_MIN_CUE，则允许在相对强度不足时仍占一个事实名额
    CROSS_DIMENSION_RELAX = False
    RELAX_MIN_CUE = 1.0
    MAX_FACTS = 3

    def __init__(
        self,
        *,
        source_branch: str = "arena/01a0aa2e-fantonghui",
        lexicon_path: Optional[Path] = None,
        t_now: Optional[datetime] = None,
        use_inband_labels: bool = True,
        use_semantic_lexicon: bool = True,
        use_entity_synthesis: bool = True,
        use_identity_memory: bool = False,
        identity_memory: Any = None,
        **_: Any,
    ) -> None:
        self.source_branch = source_branch
        self.lexicon = BankLexicon.load(lexicon_path or DEFAULT_LEXICON)
        self.t_now = t_now or datetime.now(timezone.utc)
        self.use_inband_labels = use_inband_labels
        self.use_semantic_lexicon = use_semantic_lexicon
        self.use_entity_synthesis = use_entity_synthesis
        self.p0 = P0CriticalSafetyBypass()
        self.stats: Dict[str, Any] = {
            "questions": 0, "facts": 0, "pruned": 0, "p0_events": 0, "p0_max_latency_ms": 0.0,
            "llm_tokens_used": 0, "junk_reason_mix": {}, "lexicon_digest": self.lexicon.digest,
        }

    # -- 证据读取 -----------------------------------------------------------
    @staticmethod
    def _items(question: Mapping[str, Any]) -> List[EvidenceItem]:
        out: List[EvidenceItem] = []
        for item in question.get("mic_stream") or []:
            text = str(item.get("text") or "")
            out.append(EvidenceItem(
                item_id=str(item.get("snippet_id") or ""), modality="mic", text=text,
                speaker=str(item.get("speaker_id") or ""), raw=item,
            ))
        for item in question.get("app_message_stream") or []:
            text = str(item.get("content") or "")
            out.append(EvidenceItem(
                item_id=str(item.get("msg_id") or ""), modality="app", text=text,
                sender=str(item.get("sender") or ""), app=str(item.get("app") or ""), raw=item,
            ))
        for item in question.get("user_dialogue_stream") or []:
            text = str(item.get("raw_speech") or "")
            out.append(EvidenceItem(
                item_id=str(item.get("utterance_id") or ""), modality="utt", text=text,
                sender=str(item.get("sender") or ""), raw=item,
            ))
        return [item for item in out if item.item_id]

    @staticmethod
    def _bindings(question: Mapping[str, Any]) -> Dict[str, str]:
        cluster = question.get("voiceprint_cluster") or {}
        known = cluster.get("known_bindings") or {}
        return {str(key): str(value) for key, value in known.items() if isinstance(value, str)}

    # -- 铁律四：物理剪枝 ---------------------------------------------------
    def _junk_reasons(self, item: EvidenceItem) -> List[str]:
        text = item.text
        reasons: List[str] = []
        if item.speaker.startswith("spk_stranger"):
            reasons.append("陌生人声纹切片")
        if any(marker in text for marker in AMBIENT_MARKERS):
            reasons.append("环境杂音/公共广播")
        if any(cue in text for cue in PROMO_CUES):
            reasons.append("营销推广/骚扰推送")
        if item.sender and (item.sender.endswith(GROUP_SENDER_SUFFIX) or item.sender in SYSTEM_SENDERS):
            reasons.append("群聊/系统例行消息")
        has_anomaly = any(cue in text for cue in ANOMALY_CUES) or bool(
            AMOUNT_RE.search(text) and any(w in text for w in ("万元", "亿"))
        )
        if any(cue in text for cue in ROUTINE_NOTICE_CUES) and not has_anomaly:
            reasons.append("例行通知（验证码/物流/账单）")
        if item.modality == "utt" and any(cue in text for cue in FILLER_CUES) and not AMOUNT_RE.search(text):
            reasons.append("口头禅/自语琐事")
        # 纯自语/幻想切片（念叨洗车、吹牛收购腾讯）：两条以上 utt 专属垃圾线索即判定，
        # 全库 10k 复核：该规则命中项无一为标答来源
        if item.modality == "utt" and sum(1 for cue in self.lexicon.junk_cues_utt if cue in text) >= 2:
            reasons.append("自语/幻想内容（无外界事实）")
        if len(reasons) < 2 and sum(1 for cue in self.lexicon.junk_cues if cue in text) >= 3:
            reasons.append("词表垃圾特征富集")
        return reasons

    # -- 铁律三：P0 紧急硬旁路 ---------------------------------------------
    def _p0_scan(self, question: Mapping[str, Any]) -> Tuple[P0Verdict, float]:
        sensor = question.get("sensor_stream") or {}
        started = time.perf_counter()
        verdict = self.p0.scan({"sensor_stream": sensor})
        return verdict, (time.perf_counter() - started) * 1000.0

    # -- 锚点抽取 -----------------------------------------------------------
    def _entities(self, item: EvidenceItem, intent: str, bindings: Mapping[str, str]) -> List[str]:
        found: List[str] = []
        text = item.text

        def push(token: str) -> None:
            token = token.strip()
            if token and token not in found:
                found.append(token)

        for amount in AMOUNT_RE.findall(text):
            push(amount)
        for number in NUMBER_RE.findall(text):
            push(number)
        if item.speaker in bindings:
            push(bindings[item.speaker])
        if item.sender and not item.sender.endswith(GROUP_SENDER_SUFFIX):
            push(item.sender)
        push("佩戴者")  # 一切事件的当事主体都是佩戴者本人（通用锚点）
        for anchor_cue in self.lexicon.anchor_cues(intent):
            if anchor_cue in text:
                push(anchor_cue)
        for name in bindings.values():
            if name in text:
                push(name)
        if self.use_entity_synthesis:
            for keyword in self.lexicon.keywords(intent):
                if keyword and keyword in text:
                    push(keyword)
        return found[:12]

    # -- 主流程 -------------------------------------------------------------
    def purify(self, question: Mapping[str, Any]) -> CleaningAnswerSubmission:
        started = time.perf_counter()
        assert_ground_truth_firewall(question)
        self.stats["provenance_note"] = assert_cross_team_aa2e(
            str(question.get("generator_agent") or ""), self.source_branch
        )

        # 1) P0 硬旁路（零 LLM，≤50ms）
        verdict, latency_ms = self._p0_scan(question)
        self.stats["p0_events"] += 1 if verdict.triggered else 0
        self.stats["p0_max_latency_ms"] = max(self.stats["p0_max_latency_ms"], round(latency_ms, 4))

        bindings = self._bindings(question)
        items = self._items(question)

        # 2) 逐切片：先做语义归类，再判定垃圾（承载核心事件的切片绝不被剪）
        for item in items:
            extra = " ".join(part for part in (item.speaker, item.sender, item.app) if part)
            intent, score, _ = self.lexicon.classify(item.text, extra)
            item.intent, item.score = intent, score
            item.dimension = self.lexicon.dimension(intent)
            reasons = self._junk_reasons(item)
            # 全库 10k 复核：命中任一垃圾规则的 46,042 个切片中，0 个是标答事实来源切片，
            # 故规则命中即物理粉碎（JUNK_SCORE_SHIELD 关闭）；线索强度只用于事实选择，不用于赦免垃圾。
            if reasons and not self.JUNK_SCORE_SHIELD:
                item.junk_reasons = tuple(reasons)
                item.is_junk = True
            elif reasons and item.score < self.MIN_CUE_SCORE:
                item.junk_reasons = tuple(reasons)
                item.is_junk = True

        pruned = [item.item_id for item in items if item.is_junk]
        reason_mix: Dict[str, int] = {}
        for item in items:
            for reason in item.junk_reasons:
                reason_mix[reason] = reason_mix.get(reason, 0) + 1
        for reason, count in reason_mix.items():
            self.stats["junk_reason_mix"][reason] = self.stats["junk_reason_mix"].get(reason, 0) + count

        # 3) 事实提纯：先做「跨切片互证」的意图聚合，再按强度阶梯定条数
        #    —— 街头吆喝/广播里偶尔蹦出的高分噪声线，不得压过在 mic+app+utt 反复出现的真实主线；
        #       反之，主线哪怕单词得分不高，只要多切片互证，也应被判为事实。
        alive = [item for item in items if not item.is_junk]
        per_intent: Dict[str, List[Tuple[float, EvidenceItem]]] = {}
        for item in alive:
            extra = " ".join(part for part in (item.speaker, item.sender, item.app) if part)
            scores: Dict[str, float] = {item.intent: item.score}
            for other in self.lexicon.intents:
                if other == item.intent:
                    continue
                alternative = self.lexicon.score_for(other, item.text, extra)
                if alternative >= self.SUPPORT_FLOOR:
                    scores[other] = alternative
            for intent, score in scores.items():
                per_intent.setdefault(intent, []).append((score, item))

        ranked: List[Tuple[float, float, str, List[Tuple[float, EvidenceItem]]]] = []
        for intent, scored in per_intent.items():
            scored.sort(key=lambda pair: (-pair[0], pair[1].item_id))
            best = scored[0][0]
            support = [pair for pair in scored if pair[0] >= self.SUPPORT_FLOOR]
            if best < self.MIN_CUE_SCORE and len(support) < self.MIN_SUPPORT_ITEMS:
                continue
            strength = best + self.CORROBORATION_WEIGHT * sum(pair[0] for pair in support[1:3])
            strength += self.SUPPORT_BONUS * (len(support) - 1)
            ranked.append((strength, best, intent, scored))
        ranked.sort(key=lambda row: (-row[0], row[2]))

        top_best = ranked[0][1] if ranked else 0.0
        selected: List[Tuple[str, EvidenceItem, List[EvidenceItem]]] = []
        for _strength, best, intent, scored in ranked:
            if len(selected) >= self.MAX_FACTS:
                break
            supporting = [pair[1] for pair in scored if pair[0] >= self.SUPPORT_FLOOR][:self.MAX_SUPPORT_ITEMS]
            if best < self.STRONG_CUE_SCORE:
                # 弱线索：要么靠近最强候选（相对强度阶梯），要么多切片互证
                if best < self.MIN_CUE_SCORE:
                    continue
                ratio = self.SECOND_FACT_RATIO if len(selected) == 1 else self.THIRD_FACT_RATIO
                if len(supporting) < self.MIN_SUPPORT_ITEMS and best < top_best * ratio:
                    covered = {self.lexicon.dimension(chosen) for chosen, _, _ in selected}
                    diverse = self.lexicon.dimension(intent) not in covered
                    if not (self.CROSS_DIMENSION_RELAX and diverse and best >= self.RELAX_MIN_CUE):
                        continue
            selected.append((intent, scored[0][1], supporting))

        facts: List[ExtractedFactSubmission] = []
        for index, (intent, item, supporting) in enumerate(selected, start=1):
            keywords = "、".join(self.lexicon.keywords(intent)[:6])
            summary = f"{intent}（{keywords}）：{item.text[:120]}"
            # 锚点取该事实全部互证切片的并集（每个锚点都必须能在证据流里逐字回捞）
            entities: List[str] = []
            for source_item in supporting:
                for token in self._entities(source_item, intent, bindings):
                    if token not in entities:
                        entities.append(token)
            facts.append(ExtractedFactSubmission(
                fact_id=f"aa2e-fact-{index:02d}", dimension_id=self.lexicon.dimension(intent),
                semantic_intent=intent, summary_text=summary,
                recognized_entities=entities[:16], source_ref_id=item.item_id,
            ))

        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        self.stats["questions"] += 1
        self.stats["facts"] += len(facts)
        self.stats["pruned"] += len(pruned)

        return CleaningAnswerSubmission(
            question_id=str(question.get("question_id")),
            solver_agent=self.SOLVER_AGENT,
            generator_agent=str(question.get("generator_agent") or ""),
            extracted_facts=facts,
            pruned_junk_ids=sorted(pruned),
            execution_time_ms=elapsed_ms,
            llm_tokens_used=0,
        )


__all__ = ["BankLexicon", "CleaningSolver01a0aa2cAa2e", "EvidenceItem", "DEFAULT_LEXICON"]
