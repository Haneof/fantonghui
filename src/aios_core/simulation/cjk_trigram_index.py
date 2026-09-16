"""SIM-001 仿真局部 CJK 倒排索引（C06 倒排求交阶段的自持实现）。
独立命名并存线（agent-05）：本模块为同工单独立命名交付版本，与共享分支上的规范实现并存，零覆盖；详见批次报告 agent-05-m2m3-sim-batch-20260916。

定位声明：本模块是 SIM-001 无界面仿真驱动的**自持实现**，用于驱动
"C06 倒排求交"链路语义（多词共现求交）。它**不是** M1-017 工单的交付
模块（CJK 拓扑倒排聚集表归 M1-017 派单，另行落盘），两者独立命名、
互不覆盖。

实现口径：
- 仅索引 CJK 连续段（\\u4e00-\\u9fff）的二元组（bigram）与三元组（trigram）；
- 倒排求交：多词查询 = 各词倒排表求交，得分 = 各词重叠率的均值；
- 确定性：同文档集 + 同查询 → 同结果（按 (-score, doc_id) 排序）。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

__all__ = ["CjkTrigramIndex", "cjk_ngrams"]

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def cjk_ngrams(text: str, sizes: Sequence[int] = (2, 3)) -> List[str]:
    """抽取 CJK 连续段的 n-gram（长度 < n 的段以整段参与，保证短词可检索）。"""
    grams: List[str] = []
    for run in _CJK_RUN.findall(text):
        for n in sizes:
            if len(run) < n:
                if n == min(sizes):
                    grams.append(run)
                continue
            for i in range(len(run) - n + 1):
                grams.append(run[i : i + n])
    return grams


class CjkTrigramIndex:
    """CJK 二元/三元倒排索引（仿真驱动的 C06 求交口径）。"""

    def __init__(self) -> None:
        self._postings: Dict[str, Set[str]] = defaultdict(set)
        self._doc_texts: Dict[str, str] = {}

    # ---------------- 写入 ----------------

    def add(self, doc_id: str, text: str) -> None:
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("doc_id must be a non-empty string")
        if doc_id in self._doc_texts:
            raise ValueError(f"doc {doc_id!r} already indexed (single-write)")
        self._doc_texts[doc_id] = text
        for gram in cjk_ngrams(text):
            self._postings[gram].add(doc_id)

    # ---------------- 查询（倒排求交） ----------------

    @staticmethod
    def _query_terms(word: str) -> Set[str]:
        grams = cjk_ngrams(word, sizes=(2,))
        return set(grams) if grams else {word}

    def query_multi_word(
        self, words: Sequence[str], *, min_overlap: float = 0.5
    ) -> List[Tuple[str, float]]:
        """多词共现求交：返回 (doc_id, score) 降序列表。

        得分 = 各查询词在文档中的 n-gram 重叠率均值；低于 ``min_overlap``
        的文档被求交剔除（严禁单词命中混入）。
        """
        if not words:
            return []
        term_sets = [self._query_terms(w) for w in words]
        candidate_ids: Optional[Set[str]] = None
        for terms in term_sets:
            union: Set[str] = set()
            for term in terms:
                union |= self._postings.get(term, set())
            if candidate_ids is None:
                candidate_ids = set(union)  # 首词：初始化候选集（严禁空集交集陷阱）
            else:
                candidate_ids &= union  # 后续词：倒排求交
            if not candidate_ids:
                return []
        scored: List[Tuple[str, float]] = []
        for doc_id in candidate_ids:
            ratios = []
            for terms in term_sets:
                if not terms:
                    ratios.append(1.0)
                    continue
                hits = 0
                for term in terms:
                    if doc_id in self._postings.get(term, set()):
                        hits += 1
                ratios.append(hits / len(terms))
            score = sum(ratios) / len(ratios)
            if score >= min_overlap:
                scored.append((doc_id, round(score, 6)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored

    # ---------------- 只读 ----------------

    @property
    def doc_count(self) -> int:
        return len(self._doc_texts)

    def has(self, doc_id: str) -> bool:
        return doc_id in self._doc_texts

    def get_text(self, doc_id: str) -> str:
        try:
            return self._doc_texts[doc_id]
        except KeyError:
            raise KeyError(f"unknown doc_id: {doc_id!r}") from None
