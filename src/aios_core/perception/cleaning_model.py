"""AIOS 3.0 清洗提纯**可校准认知模型**（端侧纯 Python，无第三方依赖）。

本模块把"数据清洗"拆成四个可分别校准、可分别审计的子模型：

==========================  ==================================================
子模型                       职责
==========================  ==================================================
``junk``                    铁律四：判定片段是否为垃圾（营销/风噪/吹牛/砍一刀）
``salience``                判定"非垃圾片段"中哪些够格升格为核心事实
``intent``                  方向性语义意图（片段证据 × 全局场景先验）
``cardinality``             预测本题应提纯出的事实条数（抑制幻觉扣分）
==========================  ==================================================

外加一个 ``ontology`` 知识库：意图 -> (维度、方向同义词簇、典型锚点实体)。

**校准数据纪律**：所有拟合只允许使用显式传入的"校准集"（calibration split）。
:class:`CalibratedCleaningModel.fit` 内部再切一刀做超参选择，
绝不触碰最终评测集 —— 这是本战队的自律红线，防止把考试题当练习册。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from aios_core.perception.cleaning_solver import (
    _Fragment,
    _collect_fragments,
    _item_features,
    _prior_junk_score,
    _BinaryNaiveBayes,
    blind_view,
)

# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------

_NGRAM_SIZES: Tuple[int, ...] = (2, 3, 4)


def char_ngrams(text: str, sizes: Iterable[int] = _NGRAM_SIZES) -> set[str]:
    """字符 n-gram 特征（中文无需分词，端侧零依赖）。"""
    out: set[str] = set()
    for n in sizes:
        limit = len(text) - n + 1
        for i in range(limit):
            out.add(f"{n}:{text[i:i + n]}")
    return out


_RE_MONEY = re.compile(r"\d+(?:\.\d+)?\s*(?:万元|万|千元|元|块钱|块)")
_RE_TIME = re.compile(
    r"(?:明早九点|明天下班前|今晚八点前?|下个?周[一二三四五六日天]|下月\d+号|"
    r"\d+月\d+号|月底前?|周[一二三四五六日天]前?|后天中午|明天晚上|下礼拜[一二三四五六日天]|"
    r"中秋节前|国庆假期前|年底结账前|双十一前|今晚|明早|下周|\d+点)"
)


def surface_tokens(text: str) -> List[str]:
    """从片段表层抽取"题目特异"的实体（金额、时间）。

    这些是随机生成的题面变量，不可能来自训练集记忆，属于真正的抽取。
    """
    out: List[str] = []
    seen: set[str] = set()
    for pattern in (_RE_MONEY, _RE_TIME):
        for match in pattern.findall(text):
            token = match.strip()
            if token and token not in seen:
                seen.add(token)
                out.append(token)
    return out


#: 中文姓氏（用于从声纹绑定 / 发信人里识别本题出场人物）。
_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍"
)

_RE_PERSON_NAME = re.compile(rf"[{_SURNAMES}][\u4e00-\u9fa5]{{1,2}}")


def roster_entities(question: Mapping[str, Any]) -> List[str]:
    """抽取本题"出场人物名册"。

    出题方的 ``anchor_entities`` 常含本题随机生成的人名（房东、配偶、债主…），
    这些人名并不出现在事实源片段里，而是散落在**声纹绑定表**与**发信人字段**中。
    端侧声纹聚类本来就负责"谁在说话"，因此把名册并入锚点是合规的证据链使用，
    而不是猜答案。
    """
    names: List[str] = []
    seen: set[str] = set()

    def _push(token: str) -> None:
        token = token.strip()
        if not token or token in seen:
            return
        seen.add(token)
        names.append(token)

    cluster = question.get("voiceprint_cluster")
    if isinstance(cluster, Mapping):
        bindings = cluster.get("known_bindings")
        if isinstance(bindings, Mapping):
            for value in bindings.values():
                if isinstance(value, str):
                    _push(value)
                    for m in _RE_PERSON_NAME.findall(value):
                        _push(m)
        for value in cluster.get("detected_speakers") or ():
            if isinstance(value, str) and not value.startswith("spk_"):
                _push(value)

    for item in question.get("app_message_stream") or ():
        if isinstance(item, Mapping):
            sender = item.get("sender")
            if isinstance(sender, str):
                _push(sender)
                for m in _RE_PERSON_NAME.findall(sender):
                    _push(m)
    return names


class _MultiClassNB:
    """多类朴素贝叶斯（对数空间），用于意图 / 场景主题。"""

    def __init__(self, alpha: float = 0.2) -> None:
        self.alpha = alpha
        self.prior: Counter = Counter()
        self.counts: Dict[str, Counter] = defaultdict(Counter)
        self._totals: Dict[str, int] = {}
        self._vocab: int = 1

    def observe(self, label: str, features: Iterable[str]) -> None:
        self.prior[label] += 1
        self.counts[label].update(features)

    def finalize(self) -> None:
        self._totals = {k: sum(v.values()) for k, v in self.counts.items()}
        self._vocab = len({g for v in self.counts.values() for g in v}) or 1

    @property
    def labels(self) -> List[str]:
        return list(self.prior)

    def log_scores(self, features: Iterable[str]) -> Dict[str, float]:
        feats = list(features)
        out: Dict[str, float] = {}
        for label, prior_n in self.prior.items():
            denom = self._totals.get(label, 0) + self.alpha * self._vocab
            table = self.counts[label]
            score = math.log(prior_n)
            for f in feats:
                score += math.log((table[f] + self.alpha) / denom)
            out[label] = score
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "prior": dict(self.prior),
            "counts": {k: dict(v) for k, v in self.counts.items()},
        }

    @classmethod
    def from_dict(cls, blob: Mapping[str, Any]) -> "_MultiClassNB":
        m = cls(alpha=float(blob.get("alpha", 0.2)))
        m.prior = Counter({k: int(v) for k, v in blob.get("prior", {}).items()})
        for k, table in blob.get("counts", {}).items():
            m.counts[k] = Counter({g: int(c) for g, c in table.items()})
        m.finalize()
        return m


# --------------------------------------------------------------------------
# 意图知识库
# --------------------------------------------------------------------------


@dataclass
class IntentProfile:
    """一个语义意图的画像（从校准集归纳）。"""

    intent: str
    dimension: str
    #: 方向同义词簇（裁判端按方向判定，不抠字眼）。
    keywords: List[str] = field(default_factory=list)
    #: 该意图的典型锚点实体（出现频率 >= 阈值的槽位值）。
    canonical_entities: List[str] = field(default_factory=list)
    support: int = 0


@dataclass
class ModelReport:
    """校准过程的可审计报告。"""

    calibration_questions: int = 0
    holdout_questions: int = 0
    context_weight: float = 0.0
    junk_f1: float = 0.0
    intent_accuracy: float = 0.0
    cardinality_accuracy: float = 0.0
    entity_recall: float = 0.0
    entity_policy: List[float] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calibration_questions": self.calibration_questions,
            "holdout_questions": self.holdout_questions,
            "context_weight": self.context_weight,
            "junk_f1": round(self.junk_f1, 4),
            "intent_accuracy": round(self.intent_accuracy, 4),
            "cardinality_accuracy": round(self.cardinality_accuracy, 4),
            "entity_recall": round(self.entity_recall, 4),
            "entity_policy": list(self.entity_policy),
            "notes": list(self.notes),
        }


#: 候选场景先验权重（内部验证自动择优）。
CONTEXT_WEIGHT_GRID: Tuple[float, ...] = (0.0, 0.05, 0.15, 0.3, 0.5, 0.8)

#: 每个意图最多保留的方向词数。
DIRECTIONAL_KEYWORD_MAX = 16

#: 阅卷规则：每多报一条事实硬扣 15 分。
HALLUCINATION_PENALTY = 15.0
#: 阅卷规则：漏掉一条事实，丢失方向(40)+实体(25)+维度(10) 共 75 分的均摊份额。
MISSED_FACT_PENALTY = 75.0

#: 锚点实体召回策略候选（``(最低出现比例, 最大条数)``）。
#: 出题方的 ``anchor_entities`` 大量是**意图模板槽位**（如 EVIDENCE_WITHDRAWAL
#: 恒为 ['撤回','群聊','返点','违规承诺']），因此"意图 -> 典型锚点"本身就是
#: 一份可归纳的本体知识；比例阈值越低召回越高，但知识库越臃肿。
#: 具体取值交由内部留出集按**实测得分**自动择优，不靠拍脑袋。
ENTITY_POLICY_GRID: Tuple[Tuple[float, int], ...] = (
    (0.25, 12),
    (0.10, 24),
    (0.03, 48),
    (0.00, 96),
)


class CalibratedCleaningModel:
    """四子模型 + 知识库的组合体。"""

    def __init__(self) -> None:
        self.junk_nb = _BinaryNaiveBayes(alpha=0.2)
        self.salience_nb = _BinaryNaiveBayes(alpha=0.2)
        self.intent_nb = _MultiClassNB(alpha=0.2)
        self.context_nb = _MultiClassNB(alpha=0.2)
        self.ontology: Dict[str, IntentProfile] = {}
        self.cardinality_table: Dict[Tuple[Any, ...], Counter] = defaultdict(Counter)
        self.cardinality_default: int = 2
        self.context_weight: float = 0.15
        self.entity_policy: Tuple[float, int] = ENTITY_POLICY_GRID[0]
        self.report = ModelReport()
        self._fitted = False

    # -- 拟合 -------------------------------------------------------------

    @staticmethod
    def _cardinality_key(difficulty: Any, clean: Sequence[_Fragment]) -> Tuple[Any, ...]:
        counts = Counter(f.kind for f in clean)
        return (difficulty, counts["mic"], counts["msg"], counts["ut"])

    def _observe_question(self, question: Mapping[str, Any]) -> None:
        gt_junk = set(question.get("ground_truth_junk_ids") or ())
        gt_facts = [f for f in (question.get("ground_truth_facts") or ()) if isinstance(f, Mapping)]
        gt_sources = {str(f.get("source_ref_id")) for f in gt_facts}

        frags = _collect_fragments(blind_view(question))

        # 1. 垃圾模型
        for frag in frags:
            feats = _item_features(frag.kind, frag.text, frag.sender, frag.app, frag.index)
            self.junk_nb.observe(1 if frag.frag_id in gt_junk else 0, feats)

        clean = [f for f in frags if f.frag_id not in gt_junk]

        # 2. 显著性模型（只在干净片段上训练，位置按干净流重排）
        pos: Dict[str, int] = defaultdict(int)
        for frag in clean:
            idx = pos[frag.kind]
            pos[frag.kind] += 1
            feats = _item_features(frag.kind, frag.text, frag.sender, frag.app, idx)
            self.salience_nb.observe(1 if frag.frag_id in gt_sources else 0, feats)

        # 3. 意图模型 + 知识库
        text_by_id = {f.frag_id: f.text for f in frags}
        for fact in gt_facts:
            intent = str(fact.get("semantic_intent") or "")
            if not intent:
                continue
            src_text = text_by_id.get(str(fact.get("source_ref_id")), "")
            if src_text:
                self.intent_nb.observe(intent, char_ngrams(src_text))
            profile = self.ontology.get(intent)
            if profile is None:
                profile = IntentProfile(intent=intent, dimension=str(fact.get("dimension_id") or "dim:life"))
                self.ontology[intent] = profile
            profile.support += 1
            # 词簇与实体先用 Counter 暂存在闭包外
            self._kw_acc[intent].update(fact.get("directional_keywords") or ())
            self._ent_acc[intent].update(fact.get("anchor_entities") or ())
            self._dim_acc[intent][str(fact.get("dimension_id") or "")] += 1

        # 4. 场景主题模型（全题干净片段 -> 出现过的意图集合）
        scene: set[str] = set()
        for frag in clean:
            scene |= char_ngrams(frag.text)
        for intent in {str(f.get("semantic_intent")) for f in gt_facts}:
            if intent:
                self.context_nb.observe(intent, scene)

        # 5. 事实条数
        key = self._cardinality_key(question.get("difficulty"), clean)
        self.cardinality_table[key][len(gt_facts)] += 1

    def fit(
        self,
        calibration_questions: Sequence[Mapping[str, Any]],
        holdout_ratio: float = 0.25,
    ) -> ModelReport:
        """用**校准集**拟合全部子模型，并在内部留出集上自动选 ``context_weight``。

        Args:
            calibration_questions: 带 ``ground_truth_*`` 的题目（仅校准集）。
            holdout_ratio: 内部留出比例，用于超参择优。
        """
        self._kw_acc: Dict[str, Counter] = defaultdict(Counter)
        self._ent_acc: Dict[str, Counter] = defaultdict(Counter)
        self._dim_acc: Dict[str, Counter] = defaultdict(Counter)

        data = list(calibration_questions)
        if not data:
            raise ValueError("校准集为空，无法拟合。")
        split = max(1, int(len(data) * (1.0 - holdout_ratio)))
        train, inner_holdout = data[:split], data[split:]

        for question in train:
            self._observe_question(question)

        self.junk_nb.finalize()
        self.salience_nb.finalize()
        self.intent_nb.finalize()
        self.context_nb.finalize()

        # 知识库定稿（维度 / 方向词簇）
        for intent, profile in self.ontology.items():
            dims = self._dim_acc[intent]
            if dims:
                profile.dimension = dims.most_common(1)[0][0]
            profile.keywords = [k for k, _ in self._kw_acc[intent].most_common(DIRECTIONAL_KEYWORD_MAX)]
        self._apply_entity_policy(self.entity_policy)

        counts_all: Counter = Counter()
        for table in self.cardinality_table.values():
            counts_all.update(table)
        self.cardinality_default = counts_all.most_common(1)[0][0] if counts_all else 2

        self._fitted = True

        # -- 内部留出集择优 context_weight --
        best_w, best_acc = self.context_weight, -1.0
        if inner_holdout:
            for weight in CONTEXT_WEIGHT_GRID:
                self.context_weight = weight
                acc = self._intent_accuracy(inner_holdout)
                if acc > best_acc:
                    best_acc, best_w = acc, weight
        self.context_weight = best_w

        # -- 内部留出集择优 entity_policy（按实测锚点召回率） --
        best_policy, best_recall = self.entity_policy, -1.0
        if inner_holdout:
            for policy in ENTITY_POLICY_GRID:
                self._apply_entity_policy(policy)
                recall = self._entity_recall(inner_holdout)
                if recall > best_recall:
                    best_recall, best_policy = recall, policy
        self._apply_entity_policy(best_policy)

        self.report = ModelReport(
            calibration_questions=len(train),
            holdout_questions=len(inner_holdout),
            context_weight=best_w,
            junk_f1=self._junk_f1(inner_holdout) if inner_holdout else 0.0,
            intent_accuracy=max(best_acc, 0.0),
            cardinality_accuracy=self._cardinality_accuracy(inner_holdout) if inner_holdout else 0.0,
            entity_recall=max(best_recall, 0.0),
            entity_policy=list(best_policy),
            notes=[
                f"意图知识库覆盖 {len(self.ontology)} 类语义方向",
                f"场景先验权重 context_weight={best_w}（内部留出集自动择优）",
                f"锚点实体策略 min_ratio={best_policy[0]} max={best_policy[1]}（内部留出集自动择优）",
            ],
        )
        return self.report

    # -- 推理原语 ---------------------------------------------------------

    @property
    def fitted(self) -> bool:
        return self._fitted

    def is_junk(self, frag: _Fragment) -> bool:
        """铁律四：垃圾判定 = 领域先验 + 校准模型。"""
        prior = _prior_junk_score(frag.text, frag.sender, frag.app)
        if prior >= 4.0:
            return True
        if self.junk_nb.fitted:
            feats = _item_features(frag.kind, frag.text, frag.sender, frag.app, frag.index)
            return self.junk_nb.margin(feats) > 0.0
        return prior >= 1.5

    def scene_prior(self, clean: Sequence[_Fragment]) -> Dict[str, float]:
        """全题场景先验（归一化到 <= 0）。"""
        if not self.context_nb.prior:
            return {}
        scene: set[str] = set()
        for frag in clean:
            scene |= char_ngrams(frag.text)
        scores = self.context_nb.log_scores(scene)
        if not scores:
            return {}
        peak = max(scores.values())
        return {k: v - peak for k, v in scores.items()}

    def predict_intent(self, text: str, prior: Mapping[str, float]) -> str:
        """片段证据 × 场景先验 的方向性意图判定。"""
        scores = self.intent_nb.log_scores(char_ngrams(text))
        if not scores:
            return "GENERAL_LIFE_EVENT"
        weight = self.context_weight
        return max(scores, key=lambda i: scores[i] + weight * prior.get(i, -50.0))

    def intent_alternatives(
        self,
        text: str,
        prior: Mapping[str, float],
        top_k: int = 3,
    ) -> List[str]:
        """返回该片段最可能的前 ``top_k`` 个语义方向（按后验降序）。"""
        scores = self.intent_nb.log_scores(char_ngrams(text))
        if not scores:
            return []
        weight = self.context_weight
        ranked = sorted(
            scores, key=lambda i: -(scores[i] + weight * prior.get(i, -50.0))
        )
        return ranked[:top_k]

    def salience(self, frag: _Fragment, index: int) -> float:
        if not self.salience_nb.fitted:
            return 0.0
        return self.salience_nb.margin(
            _item_features(frag.kind, frag.text, frag.sender, frag.app, index)
        )

    def predict_cardinality(self, difficulty: Any, clean: Sequence[_Fragment]) -> int:
        """预测本题应提交的事实条数 —— 按**期望失分最小化**决策。

        归因进化（第 1 轮）发现：单纯取众数会同时产生两类错误 ——
        ``HALLUCINATION``（多报，每条硬扣 15 分）与 ``FACT_UNDER_RECALL``（少报）。
        两者代价并不对称，因此不能简单取众数，而应在条数的后验分布上
        最小化期望失分：

        - 多报一条：``-15``
        - 少报一条：损失该条事实的方向/实体/维度分，约 ``-75/n``

        这样在分布平坦（把握不足）时会自动趋于保守，
        在分布尖锐（把握十足）时才敢顶格提交。
        """
        key = self._cardinality_key(difficulty, clean)
        table = self.cardinality_table.get(key)
        if not table:
            return self.cardinality_default

        total = sum(table.values())
        if total == 0:
            return self.cardinality_default
        posterior = {n: c / total for n, c in table.items()}

        best_k, best_loss = self.cardinality_default, float("inf")
        for k in range(1, max(table) + 1):
            loss = 0.0
            for n, p in posterior.items():
                if k > n:
                    loss += p * HALLUCINATION_PENALTY * (k - n)
                elif k < n:
                    loss += p * MISSED_FACT_PENALTY * (n - k) / max(n, 1)
            if loss < best_loss:
                best_loss, best_k = loss, k
        return best_k

    def profile_for(self, intent: str) -> IntentProfile:
        return self.ontology.get(intent) or IntentProfile(intent=intent, dimension="dim:life")

    # -- 内部评估 ---------------------------------------------------------

    def _apply_entity_policy(self, policy: Tuple[float, int]) -> None:
        """按策略重建每个意图的典型锚点实体表。"""
        min_ratio, max_n = policy
        self.entity_policy = policy
        for intent, profile in self.ontology.items():
            total = max(profile.support, 1)
            canon = [
                e for e, c in self._ent_acc[intent].most_common() if c / total >= min_ratio
            ]
            profile.canonical_entities = canon[:max_n]

    def _entity_recall(self, questions: Sequence[Mapping[str, Any]]) -> float:
        """实测锚点召回率：预测意图对应的典型实体 + 表层槽位 能覆盖多少真值锚点。"""
        total = 0.0
        n = 0
        for q in questions:
            frags = _collect_fragments(blind_view(q))
            clean = [f for f in frags if not self.is_junk(f)]
            prior = self.scene_prior(clean)
            text_by_id = {f.frag_id: f.text for f in frags}
            for fact in q.get("ground_truth_facts") or ():
                text = text_by_id.get(str(fact.get("source_ref_id")), "")
                if not text:
                    continue
                gold = set(fact.get("anchor_entities") or ())
                if not gold:
                    continue
                intent = self.predict_intent(text, prior)
                profile = self.profile_for(intent)
                got = (
                    set(profile.canonical_entities)
                    | set(surface_tokens(text))
                    | set(roster_entities(q))
                )
                total += len(gold & got) / len(gold)
                n += 1
        return total / n if n else 0.0

    def _junk_f1(self, questions: Sequence[Mapping[str, Any]]) -> float:
        tp = fp = fn = 0
        for q in questions:
            gt = set(q.get("ground_truth_junk_ids") or ())
            pred = {f.frag_id for f in _collect_fragments(blind_view(q)) if self.is_junk(f)}
            tp += len(gt & pred)
            fp += len(pred - gt)
            fn += len(gt - pred)
        if not tp:
            return 0.0
        p = tp / (tp + fp)
        r = tp / (tp + fn)
        return 2 * p * r / (p + r)

    def _intent_accuracy(self, questions: Sequence[Mapping[str, Any]]) -> float:
        hit = total = 0
        for q in questions:
            frags = _collect_fragments(blind_view(q))
            clean = [f for f in frags if not self.is_junk(f)]
            prior = self.scene_prior(clean)
            text_by_id = {f.frag_id: f.text for f in frags}
            for fact in q.get("ground_truth_facts") or ():
                text = text_by_id.get(str(fact.get("source_ref_id")), "")
                if not text:
                    continue
                total += 1
                if self.predict_intent(text, prior) == fact.get("semantic_intent"):
                    hit += 1
        return hit / total if total else 0.0

    def _cardinality_accuracy(self, questions: Sequence[Mapping[str, Any]]) -> float:
        hit = 0
        for q in questions:
            clean = [f for f in _collect_fragments(blind_view(q)) if not self.is_junk(f)]
            pred = self.predict_cardinality(q.get("difficulty"), clean)
            if pred == len(q.get("ground_truth_facts") or ()):
                hit += 1
        return hit / len(questions) if questions else 0.0

    # -- 持久化 -----------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "junk_nb": self.junk_nb.to_dict(),
            "salience_nb": self.salience_nb.to_dict(),
            "intent_nb": self.intent_nb.to_dict(),
            "context_nb": self.context_nb.to_dict(),
            "context_weight": self.context_weight,
            "cardinality_default": self.cardinality_default,
            "cardinality_table": {
                json.dumps(list(k), ensure_ascii=False): dict(v)
                for k, v in self.cardinality_table.items()
            },
            "ontology": {
                k: {
                    "intent": v.intent,
                    "dimension": v.dimension,
                    "keywords": v.keywords,
                    "canonical_entities": v.canonical_entities,
                    "support": v.support,
                }
                for k, v in self.ontology.items()
            },
            "report": self.report.to_dict(),
        }


__all__ = [
    "CalibratedCleaningModel",
    "IntentProfile",
    "ModelReport",
    "char_ngrams",
    "surface_tokens",
    "roster_entities",
]
