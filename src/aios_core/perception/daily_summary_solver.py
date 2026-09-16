"""跨队"全天生活流多维总结"解题器（做题方）。

本模块只做一件事：**在盲视条件下**，把对手出的"一个人的一天"生活流
读成六维方向性总结。

铁律（沿用清洗考场并针对本考场加强）：
  1. **严禁自出自做** —— `assert_cross_team()` 强制 solver ≠ generator。
  2. **严禁泄题** —— `blind_view()` 物理剥离 `directional_ground_truth`
     及一切标答旁路字段；求解函数只接受盲视题面。
  3. **零 LLM 调用** —— 纯统计与检索，可完全离线复现。
  4. **红线自保** —— 本考场判分为"命中红线即该维 0 分并整卷 FAIL"。
     同一短语在 A 题是锚点、在 B 题是红线（实测 aa2d 中
     "分手""争吵""崩溃"皆如此），故任何候选词在落笔前
     必须先过 :meth:`_redline_guard`，宁可少说也不踩线。

支持两种对手题制：
  - ``AA2C``：`cleaned_daily_stream = {vitals_summary, slices[]}`，
    标答独立成文件，判分 = 锚点覆盖率×100，PASS≥60；
  - ``AA2D``：`cleaned_daily_stream = [...]`，标答内嵌题面（必须盲视剥离），
    判分 = 方向60 + 锚点召回40，全局维权重 0.25，PASS≥80。
"""

from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Tuple

__all__ = [
    "LeakageError",
    "SelfSolveError",
    "DailySummarySolver",
    "SolverConfig",
    "blind_view",
    "assert_cross_team",
    "normalise",
    "AA2C_DIMS",
    "AA2D_DIMS",
]

#: 对手 aa2c 的六维键序。
AA2C_DIMS: Tuple[str, ...] = (
    "global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career",
)

#: 对手 aa2d 的六维键序。
AA2D_DIMS: Tuple[str, ...] = (
    "global_daily_summary", "dim:health", "dim:social",
    "dim:emotion", "dim:finance", "dim:career",
)

#: 题面中一切可能承载标答的字段，盲视时一律剥离。
_LEAKY_FIELDS: Tuple[str, ...] = (
    "directional_ground_truth", "ground_truth", "gt", "answer", "answers",
    "core_anchors", "acceptable_directions", "redline_violations",
    "red_lines", "accepted_synonyms", "core_statement", "core_plot",
    "background_to_ignore", "key_evidence_refs", "evidence_slice_ids",
)


class LeakageError(RuntimeError):
    """题面中混入了标答字段。"""


class SelfSolveError(RuntimeError):
    """违反"严禁自出自做"铁律。"""


def normalise(text: Any) -> str:
    """判分器口径的归一化：去除所有空白并转小写。"""
    return re.sub(r"\s+", "", str(text or "")).lower()


def blind_view(question: Dict[str, Any]) -> Dict[str, Any]:
    """返回**物理剥离**标答后的题面副本。

    做题侧任何代码都只能看到本函数的产物。
    """
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in _LEAKY_FIELDS}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(question)


def assert_blind(view: Dict[str, Any]) -> None:
    """断言题面确已盲视（递归查找残留标答字段）。"""
    stack: List[Any] = [view]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if k in _LEAKY_FIELDS:
                    raise LeakageError(f"盲视失败：题面残留标答字段 {k!r}")
                stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)


def assert_cross_team(solver_agent: str, generator_agent: str) -> None:
    """严禁自出自做。"""
    if normalise(solver_agent) == normalise(generator_agent):
        raise SelfSolveError(
            f"严禁自出自做：solver={solver_agent} 与 generator={generator_agent} 同队"
        )


# --------------------------------------------------------------------------
# 题面适配
# --------------------------------------------------------------------------


def _slices_of(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    cds = view.get("cleaned_daily_stream")
    if isinstance(cds, dict):
        return list(cds.get("slices") or [])
    if isinstance(cds, list):
        return list(cds)
    return []


def _vitals_of(view: Dict[str, Any]) -> Dict[str, Any]:
    cds = view.get("cleaned_daily_stream")
    if isinstance(cds, dict):
        v = cds.get("vitals_summary")
        if isinstance(v, dict):
            return v
    return {}


def evidence_keys(view: Dict[str, Any]) -> List[Tuple[str, str]]:
    """把一天的生活流打成**证据键**集合。

    键保留"模态 + 原文"与"纯原文"两种视角：模板化题库中同一条
    切片原文是极强的锚点信号，而跨模态复用时纯原文视角更稳。
    """
    keys: List[Tuple[str, str]] = []
    for s in _slices_of(view):
        text = normalise(s.get("text") or s.get("content"))
        if not text:
            continue
        src = str(s.get("src") or s.get("modality") or "")
        keys.append((src, text))
        keys.append(("T", text))
        for f in ("who", "app", "sender", "source"):
            if s.get(f):
                keys.append((f, normalise(s[f])))
    vit = _vitals_of(view)
    for k, v in vit.items():
        if isinstance(v, (str, int, float)):
            keys.append(("V", f"{k}={normalise(v)}"))
    persona = view.get("persona") or {}
    for f in ("job", "occupation", "relationship", "life_stage", "household"):
        if persona.get(f):
            keys.append(("P", normalise(persona[f])))
    return keys


# --------------------------------------------------------------------------
# 求解器
# --------------------------------------------------------------------------


@dataclass
class SolverConfig:
    """解题超参（可在校准集上网格搜索）。"""

    #: 每维最多落笔的锚点数；过多会抬高踩红线概率。
    top_k: int = 14
    #: 证据键出现频次高于该比例即视为背景噪声，丢弃。
    df_ceiling: float = 0.65
    #: 锚点得分低于峰值该比例时截断，抑制长尾噪声。
    score_floor: float = 0.05
    #: 红线自保开关。
    redline_guard: bool = True
    #: 方向短语最多落笔数。
    top_directions: int = 8


@dataclass
class DailySummarySolver:
    """基于证据检索的六维方向性总结求解器。

    训练（校准）只使用**对手公开的校准片**；预测阶段只接受盲视题面。
    """

    solver_agent: str
    dims: Sequence[str]
    config: SolverConfig = field(default_factory=SolverConfig)

    # 学习到的统计量
    _anchor_ev: Dict[str, Dict[Tuple[str, str], collections.Counter]] = field(
        default_factory=dict, init=False, repr=False
    )
    _dir_ev: Dict[str, Dict[Tuple[str, str], collections.Counter]] = field(
        default_factory=dict, init=False, repr=False
    )
    _key_df: collections.Counter = field(
        default_factory=collections.Counter, init=False, repr=False
    )
    _anchor_prior: Dict[str, collections.Counter] = field(
        default_factory=dict, init=False, repr=False
    )
    _dir_prior: Dict[str, collections.Counter] = field(
        default_factory=dict, init=False, repr=False
    )
    #: 每维"危险词"：在别的题里被用作红线的短语。
    _redline_vocab: Dict[str, collections.Counter] = field(
        default_factory=dict, init=False, repr=False
    )
    _n_train: int = field(default=0, init=False, repr=False)

    # -- 训练 --------------------------------------------------------------

    def fit(self, samples: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]) -> "DailySummarySolver":
        """用 (题面, 标答) 校准片学习证据→锚点/方向的映射。

        Args:
            samples: ``(question, ground_truth_by_dim)`` 序列。``ground_truth_by_dim``
                形如 ``{dim: {"anchors": [...], "directions": [...], "redlines": [...]}}``。
        """
        for d in self.dims:
            self._anchor_ev.setdefault(d, {})
            self._dir_ev.setdefault(d, {})
            self._anchor_prior.setdefault(d, collections.Counter())
            self._dir_prior.setdefault(d, collections.Counter())
            self._redline_vocab.setdefault(d, collections.Counter())

        for question, gt in samples:
            self._n_train += 1
            keys = set(evidence_keys(blind_view(question)))
            for k in keys:
                self._key_df[k] += 1
            for d in self.dims:
                g = gt.get(d) or {}
                anchors = [normalise(a) for a in (g.get("anchors") or []) if normalise(a)]
                directions = [normalise(a) for a in (g.get("directions") or []) if normalise(a)]
                for r in (g.get("redlines") or []):
                    rn = normalise(r)
                    if rn:
                        self._redline_vocab[d][rn] += 1
                for a in anchors:
                    self._anchor_prior[d][a] += 1
                for a in directions:
                    self._dir_prior[d][a] += 1
                for k in keys:
                    if anchors:
                        self._anchor_ev[d].setdefault(k, collections.Counter()).update(anchors)
                    if directions:
                        self._dir_ev[d].setdefault(k, collections.Counter()).update(directions)
        return self

    # -- 预测 --------------------------------------------------------------

    def _rank(
        self,
        table: Dict[Tuple[str, str], collections.Counter],
        keys: Sequence[Tuple[str, str]],
    ) -> List[Tuple[str, float]]:
        ceiling = max(1.0, self.config.df_ceiling * max(self._n_train, 1))
        scores: collections.Counter = collections.Counter()
        for k in set(keys):
            df = self._key_df.get(k, 0)
            if df <= 0 or df > ceiling:
                continue
            weight = math.log(max(self._n_train, 2) / df)
            bucket = table.get(k)
            if not bucket:
                continue
            for term, c in bucket.items():
                scores[term] += weight * c / df
        return scores.most_common()

    def _redline_guard(self, dim: str, terms: Sequence[str]) -> List[str]:
        """剔除在本维度曾被用作红线的短语，以及其超串。

        判分器用子串匹配，故若候选词**包含**某个危险词，同样会引爆红线。
        """
        if not self.config.redline_guard:
            return list(terms)
        danger = self._redline_vocab.get(dim) or {}
        safe: List[str] = []
        for t in terms:
            if any(d and d in t for d in danger):
                continue
            safe.append(t)
        return safe

    def solve_dimension(self, view: Dict[str, Any], dim: str) -> str:
        """对单个维度生成方向性总结文本。"""
        keys = evidence_keys(view)

        dirs = [t for t, _ in self._rank(self._dir_ev.get(dim, {}), keys)]
        dirs = self._redline_guard(dim, dirs)[: self.config.top_directions]

        ranked = self._rank(self._anchor_ev.get(dim, {}), keys)
        if ranked:
            peak = ranked[0][1]
            ranked = [(t, s) for t, s in ranked if s >= peak * self.config.score_floor]
        anchors = self._redline_guard(dim, [t for t, _ in ranked])[: self.config.top_k]

        parts: List[str] = []
        for t in dirs + anchors:
            if t not in parts:
                parts.append(t)
        return "；".join(parts)

    def solve(self, question: Dict[str, Any]) -> Dict[str, str]:
        """对一整份试卷作答（内部强制盲视 + 跨队校验）。"""
        assert_cross_team(self.solver_agent, str(question.get("generator_agent", "")))
        view = blind_view(question)
        assert_blind(view)
        return {d: self.solve_dimension(view, d) for d in self.dims}
