"""共现召回加速器（Tool B —— E2E 海量盲测产出的纯代码新机制）。

瓶颈来源（阶段 3 压测实测）：多关键词共现检索走
``WorldSearchIndex.search_mind`` 时，路径为「全量 token 候选并集 →
search_occurred 全表 ORDER BY 扫描 → 逐行逐关键词子串匹配」，
19,511 对象规模下 4 关键词查询 ~9.9s（全表排序 + 逐行子串是主要成本）。

加速路径（**语义与基线严格同构**）：

1. **倒排预过滤**：每个关键词 → 其全部分词（CJK 二元组 + ASCII 词，
   与基线同一分词器）→ 倒排 posting 求**交集**（AND 共现语义 =
   基线 ``matched_all`` 的必要条件，预过滤零假阴性）；
2. **小候选集子串确认**：仅对交集候选回读 haystack 做子串确认
   （与基线 matched_all 完全同一判定）——候选集通常 < 10 个；
3. **一致性对撞**（禁止自编自答）：加速器结果必须与基线
   ``search_mind`` 多关键词结果在 object_id 集合级**完全一致**，
   任何差异即失败并输出两侧差异明细。

复杂度：O(Σ|posting(kw)| + |候选|×|kw|)，无全表排序、无全量子串扫描。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Set, Tuple

from aios_core.query.search import WorldSearchIndex, tokens_for

__all__ = [
    "CooccurrenceRecallAccelerator",
    "CooccurrenceVerification",
    "build_tool_proposal",
]


@dataclass(frozen=True)
class CooccurrenceVerification:
    """一次加速器 vs 基线的一致性对撞记录（可审计）。"""

    keywords: Tuple[str, ...]
    baseline_count: int
    accelerator_count: int
    identical: bool
    missing_in_accelerator: Tuple[str, ...] = ()   # 基线有、加速器漏（必须为空）
    missing_in_baseline: Tuple[str, ...] = ()       # 加速器有、基线漏（必须为空）
    baseline_ms: float = 0.0
    accelerator_ms: float = 0.0
    speedup: float = 0.0
    detail: Dict[str, Any] = field(default_factory=dict)


class CooccurrenceRecallAccelerator:
    """多关键词共现召回加速器（读投影索引，零写入）。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        self._connect()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA query_only = ON")
        return conn

    # ------------------------------------------------------------------
    # 倒排预过滤 + 子串确认
    # ------------------------------------------------------------------

    def keyword_postings(self, keywords: Sequence[str]) -> Dict[str, Set[str]]:
        """每个关键词 → 含有其**全部分词**的对象集合（AND 分词，零假阴性）。"""
        conn = self._connect()
        try:
            result: Dict[str, Set[str]] = {}
            for kw in keywords:
                tokens = sorted(tokens_for(kw))
                sets: List[Set[str]] = []
                for tok in tokens:
                    rows = conn.execute(
                        "SELECT DISTINCT object_id FROM search_postings WHERE token = ?",
                        (tok,),
                    ).fetchall()
                    sets.append({r["object_id"] for r in rows})
                if not sets:
                    result[kw] = set()
                else:
                    inter = set.intersection(*sets)
                    result[kw] = inter
            return result
        finally:
            conn.close()

    def intersect_candidates(self, keywords: Sequence[str]) -> Set[str]:
        """AND 共现预过滤：各关键词 posting 集合的交集。"""
        postings = self.keyword_postings(keywords)
        sets = [postings[kw] for kw in keywords]
        if not sets:
            return set()
        return set.intersection(*sets)

    def recall(self, keywords: Sequence[str]) -> Set[str]:
        """完整共现召回 = 倒排预过滤 ∩ 子串确认（与基线 matched_all 同判据）。"""
        if not keywords or any(not kw.strip() for kw in keywords):
            raise ValueError("keywords must be non-blank (第 89 条共现语义)")
        candidates = self.intersect_candidates(keywords)
        if not candidates:
            return set()
        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in candidates)
            rows = conn.execute(
                f"SELECT object_id, COALESCE(haystack, '') AS haystack FROM search_doc "
                f"WHERE object_id IN ({placeholders})",
                tuple(candidates),
            ).fetchall()
        finally:
            conn.close()
        out: Set[str] = set()
        for r in rows:
            haystack = r["haystack"] or ""
            if all(kw in haystack for kw in keywords):
                out.add(r["object_id"])
        return out

    def top(self, keywords: Sequence[str], *, limit: int = 50) -> List[Dict[str, Any]]:
        """按共现强度（命中分词数之和）排序的 top 结果，含摘录。"""
        conn = self._connect()
        try:
            scored: Dict[str, int] = {}
            for kw in keywords:
                tokens = sorted(tokens_for(kw))
                placeholders = ",".join("?" for _ in tokens)
                rows = conn.execute(
                    f"SELECT object_id, COUNT(*) AS hits FROM search_postings "
                    f"WHERE token IN ({placeholders}) GROUP BY object_id",
                    tokens,
                ).fetchall()
                for r in rows:
                    scored[r["object_id"]] = scored.get(r["object_id"], 0) + int(r["hits"])
            confirmed = self.recall(keywords)
            ranked = sorted(
                (oid for oid in confirmed if oid in scored),
                key=lambda oid: (-scored[oid], oid),
            )[:limit]
            if not ranked:
                return []
            placeholders = ",".join("?" for _ in ranked)
            rows = conn.execute(
                f"SELECT object_id, MAX(revision) AS revision, "
                f"COALESCE(excerpt, '') AS excerpt "
                f"FROM search_doc WHERE object_id IN ({placeholders}) "
                f"GROUP BY object_id",
                tuple(ranked),
            ).fetchall()
            by_id = {r["object_id"]: dict(r) for r in rows}
            return [
                {**by_id[oid], "co_score": scored[oid]}
                for oid in ranked if oid in by_id
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 一致性对撞（禁止自编自答的硬校验）
    # ------------------------------------------------------------------

    def verify_against_baseline(
        self,
        keywords: Sequence[str],
        baseline: WorldSearchIndex,
        *,
        limit: int = 5000,
    ) -> CooccurrenceVerification:
        """加速器 vs 基线 search_mind 多关键词查询：object_id 集合必须完全一致。"""
        t0 = time.perf_counter()
        page = baseline.search_mind(keywords=list(keywords), limit=limit)
        baseline_ms = (time.perf_counter() - t0) * 1000.0
        baseline_ids = {h.object_id for h in page.hits}

        t0 = time.perf_counter()
        acc_ids = self.recall(keywords)
        accelerator_ms = (time.perf_counter() - t0) * 1000.0

        missing_acc = tuple(sorted(baseline_ids - acc_ids))
        missing_base = tuple(sorted(acc_ids - baseline_ids))
        return CooccurrenceVerification(
            keywords=tuple(keywords),
            baseline_count=len(baseline_ids),
            accelerator_count=len(acc_ids),
            identical=(baseline_ids == acc_ids),
            missing_in_accelerator=missing_acc,
            missing_in_baseline=missing_base,
            baseline_ms=round(baseline_ms, 2),
            accelerator_ms=round(accelerator_ms, 2),
            speedup=round(baseline_ms / accelerator_ms, 1) if accelerator_ms > 0 else 0.0,
            detail={"baseline_lag": page.lag, "baseline_status": page.status},
        )


def build_tool_proposal(
    *,
    subject_id: str,
    t_now,
    measured: Dict[str, Any],
) -> "object":
    """构造本工具的 ToolProposal 世界对象（走 ToolProposalPipeline 生命周期）。"""
    from aios_core.contracts.models import ToolProposal
    from aios_core.contracts.time import TemporalExtent

    return ToolProposal(
        object_id="tool_proposal_cooccurrence_recall_accelerator",
        subject_id=subject_id, revision=1,
        capability_gap=(
            "多关键词共现检索基线路径（全表 ORDER BY 扫描 + 逐行逐词子串匹配）在 2 万对象世界下"
            "4 关键词查询 ~9.9s，是全流程最耗时查询；且全共现（AND）结果无法用倒排直接表达。"
        ),
        use_cases=[
            "阶段 3 多关键词共现召回 [合伙/借贷/撕逼/银行流水] 的加速路径",
            "新维度三重门槛中'跨域异常共现'的候选对象预过滤",
            "与 search_mind/co_search 做 object_id 集合级一致性对撞，杜绝加速带来的召回漂移",
        ],
        current_limitations=[
            "依赖 WorldSearchIndex 投影已 catch_up（lag=0 时结果才与基线严格一致）",
            "仅加速 AND 共现场景；OR 并集召回直接用逐词 postings 即可，无需本工具",
        ],
        proposed_interface={
            "class": "CooccurrenceRecallAccelerator",
            "module": "aios_core.tools.cooccurrence_recall_accelerator",
            "entry": "recall(keywords) -> set[str]；top(keywords, limit) -> list[dict]",
            "collision": "verify_against_baseline(keywords, WorldSearchIndex) -> CooccurrenceVerification",
        },
        expected_benefit=(
            f"实测对撞：基线 {measured.get('baseline_ms', 0):.1f}ms vs 加速器 {measured.get('accelerator_ms', 0):.1f}ms"
            f"（加速 {measured.get('speedup', 0):.1f}x），object_id 集合 {measured.get('identical', 'n/a')}。"
        ),
        validation_plan=(
            "pytest 全量：真实 E2E 世界（19,511 对象）上 4 关键词 + 成对关键词 + 零命中关键词"
            "三组对撞，断言 identical=True 且差异明细为空。"
        ),
        occurred=TemporalExtent.point(t_now),
        learned_at=t_now, recorded_at=t_now, created_by="e2e_blind_test_agent11",
    )
