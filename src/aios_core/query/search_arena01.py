"""M5-SEARCH 多维检索三路径对比执行器与黄金经验蒸馏（arena01 独立命名并存线）。

工单对位：
- MultidimensionalSearchBus：Dimension / Claim / Entity / Annotation / Observation
  联合检索（确定性 CJK 混合切词、AND 求交、全库有序）；
- PathwayComparisonExecutor：同一查询并行执行三路径并出具对照报告——
  Pathway A 暴力全库扫描（Token 15,000~50,000 量级）、Pathway B 朴素关键词
  倒排（只读候选文档）、Pathway C 拓扑分级下钻（维度主题树剪枝）；
- OperationExperienceDistiller：多轮同族查询后提炼黄金路径，落到只追加
  经验库（JSONL），此后同族直达：500 Token 内返回结论、准确率 100%；
- 铁律：单次命中摘要 Token 严格 ≤150；严禁占位符。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.contracts.refs import ObjectRef

__all__ = [
    "SearchDocument",
    "MultidimensionalSearchBus",
    "PathwayReport",
    "PathwayComparisonExecutor",
    "ExperienceRecord",
    "ExperiencePool",
    "DistilledAnswer",
    "OperationExperienceDistiller",
    "TOKEN_HIT_SOFT_CAP",
    "DISTILL_TARGET_TOKENS",
    "MIN_OBSERVATIONS_FOR_GOLD",
]

TOKEN_HIT_SOFT_CAP = 150
DISTILL_TARGET_TOKENS = 500
MIN_OBSERVATIONS_FOR_GOLD = 3


@dataclass(frozen=True)
class SearchDocument:
    object_id: str
    kind: str  # Dimension / Claim / Entity / Annotation / Observation
    title: str
    text: str
    dimension_slug: str = "root"
    day_index: int = 0

    def to_ref(self, revision: int = 1) -> ObjectRef:
        return ObjectRef(object_id=self.object_id, revision=revision)


def _tokenize(text: str) -> Tuple[str, ...]:
    """CJK 双字窗 + 单字 + 拉丁词的确定性切词。"""
    tokens: List[str] = []
    word = ""
    cjk_run: List[str] = []
    def flush_cjk() -> None:
        for i, ch in enumerate(cjk_run):
            tokens.append(ch)
            if i + 1 < len(cjk_run):
                tokens.append(cjk_run[i] + cjk_run[i + 1])
        cjk_run.clear()
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            if word:
                tokens.append(word.lower())
                word = ""
            cjk_run.append(ch)
        elif ch.isalnum():
            if cjk_run:
                flush_cjk()
            word += ch
        else:
            if word:
                tokens.append(word.lower())
                word = ""
            if cjk_run:
                flush_cjk()
    if word:
        tokens.append(word.lower())
    if cjk_run:
        flush_cjk()
    return tuple(tokens)


class MultidimensionalSearchBus:
    """多维对象联合检索总线（内存态、确定性）。"""

    def __init__(self) -> None:
        self._docs: Dict[str, SearchDocument] = {}
        self._postings: Dict[str, List[str]] = {}
        self._by_dimension: Dict[str, List[str]] = {}

    def add(self, doc: SearchDocument) -> None:
        if doc.object_id in self._docs:
            raise ValueError(f"duplicate document id: {doc.object_id}")
        self._docs[doc.object_id] = doc
        for token in set(_tokenize(doc.title + " " + doc.text)):
            self._postings.setdefault(token, []).append(doc.object_id)
        self._by_dimension.setdefault(doc.dimension_slug, []).append(doc.object_id)

    def __len__(self) -> int:
        return len(self._docs)

    def documents(self) -> Tuple[SearchDocument, ...]:
        return tuple(self._docs[oid] for oid in sorted(self._docs))

    def dimension_nodes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._by_dimension))

    def documents_in(self, slug: str) -> Tuple[SearchDocument, ...]:
        return tuple(self._docs[oid] for oid in sorted(self._by_dimension.get(slug, ())))

    def _search_ids(self, terms: Sequence[str]) -> Tuple[str, ...]:
        sets: List[set] = []
        for term in terms:
            hits: set = set()
            for token in _tokenize(term):
                hits.update(self._postings.get(token, ()))
            if not hits:
                return ()
            sets.append(hits)
        result = set.intersection(*sets) if sets else set()
        return tuple(sorted(result))

    def search(self, terms: Sequence[str]) -> Tuple[ObjectRef, ...]:
        return tuple(ObjectRef(object_id=oid, revision=1) for oid in self._search_ids(terms))


@dataclass(frozen=True)
class PathwayReport:
    pathway: str  # A_brute_scan / B_naive_keyword / C_topology_drill
    query: str
    doc_reads: int
    token_cost: int
    latency_ms: float
    refs: Tuple[ObjectRef, ...]


class PathwayComparisonExecutor:
    """三路径并行对比执行器（A 暴力 / B 朴素关键词 / C 拓扑分级下钻）。"""

    def __init__(self, bus: MultidimensionalSearchBus) -> None:
        self._bus = bus

    def pathway_a_brute_scan(self, terms: Sequence[str]) -> PathwayReport:
        t0 = time.perf_counter()
        want = set()
        for term in terms:
            want.update(_tokenize(term))
        refs: List[ObjectRef] = []
        cost = 0
        reads = 0
        for doc in self._bus.documents():  # 每个文档全文计价 —— 暴力代价
            reads += 1
            cost += estimate_tokens(doc.title + " " + doc.text)
            have = set(_tokenize(doc.title + " " + doc.text))
            if want and want.issubset(have):
                refs.append(doc.to_ref())
        return PathwayReport("A_brute_scan", " ".join(terms), reads, cost,
                             (time.perf_counter() - t0) * 1000, tuple(refs))

    def pathway_b_naive_keyword(self, terms: Sequence[str]) -> PathwayReport:
        t0 = time.perf_counter()
        candidates: List[str] = []
        seen: set = set()
        for term in terms:
            for token in _tokenize(term):
                for oid in self._bus._postings.get(token, ()):
                    if oid not in seen:
                        seen.add(oid)
                        candidates.append(oid)
        cost = 0
        refs: List[ObjectRef] = []
        want = set()
        for term in terms:
            want.update(_tokenize(term))
        for oid in sorted(candidates):
            doc = self._bus._docs[oid]
            cost += estimate_tokens(doc.title + " " + doc.text)
            have = set(_tokenize(doc.title + " " + doc.text))
            if want and want.issubset(have):
                refs.append(doc.to_ref())
        return PathwayReport("B_naive_keyword", " ".join(terms), len(candidates),
                             cost, (time.perf_counter() - t0) * 1000, tuple(refs))

    def pathway_c_topology_drill(self, terms: Sequence[str]) -> PathwayReport:
        t0 = time.perf_counter()
        needles = [_tokenize(t) for t in terms]
        all_query_tokens = {tok for toks in needles for tok in toks}
        cost = 0
        matched_dims: List[str] = []
        strong_query = {tok for tok in all_query_tokens if len(tok) >= 2}
        for slug in self._bus.dimension_nodes():
            cost += estimate_tokens(slug)  # 只看维度目录，不进文档
            dim_strong = {tok for tok in _tokenize(slug) if len(tok) >= 2}
            if strong_query and (strong_query & dim_strong):  # 强词目录命中才下钻
                matched_dims.append(slug)
        refs: List[ObjectRef] = []
        reads = 0
        want = {tok for toks in needles for tok in toks}
        for slug in matched_dims:
            for doc in self._bus.documents_in(slug):
                reads += 1
                cost += estimate_tokens(doc.title + " " + doc.text)
                have = set(_tokenize(doc.title + " " + doc.text))
                if want and want.issubset(have):
                    refs.append(doc.to_ref())
        return PathwayReport("C_topology_drill", " ".join(terms), reads, cost,
                             (time.perf_counter() - t0) * 1000, tuple(refs))

    def run_all(self, terms: Sequence[str]) -> Tuple[PathwayReport, PathwayReport, PathwayReport]:
        return (
            self.pathway_a_brute_scan(terms),
            self.pathway_b_naive_keyword(terms),
            self.pathway_c_topology_drill(terms),
        )


def intent_hash_of(terms: Sequence[str]) -> str:
    blob = json.dumps(list(terms), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


@dataclass(frozen=True)
class ExperienceRecord:
    intent_hash: str
    query: str
    golden_pathway: str
    token_cost: int
    doc_reads: int
    accuracy: float
    runs: int
    evidence_ref_ids: Tuple[str, ...]


class ExperiencePool:
    """只追加 JSONL 经验库（黄金优选检索经验持久化）。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._records: Dict[str, ExperienceRecord] = {}
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                blob = json.loads(line)
                record = ExperienceRecord(
                    intent_hash=blob["intent_hash"], query=blob["query"],
                    golden_pathway=blob["golden_pathway"], token_cost=blob["token_cost"],
                    doc_reads=blob["doc_reads"], accuracy=blob["accuracy"],
                    runs=blob["runs"], evidence_ref_ids=tuple(blob["evidence_ref_ids"]),
                )
                self._records[record.intent_hash] = record  # 后写覆盖（只追加物理）

    def append(self, record: ExperienceRecord) -> bool:
        if record.intent_hash in self._records:
            return False
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "intent_hash": record.intent_hash,
                "query": record.query,
                "golden_pathway": record.golden_pathway,
                "token_cost": record.token_cost,
                "doc_reads": record.doc_reads,
                "accuracy": record.accuracy,
                "runs": record.runs,
                "evidence_ref_ids": list(record.evidence_ref_ids),
            }, ensure_ascii=False) + "\n")
        self._records[record.intent_hash] = record
        return True

    def get(self, intent_hash: str) -> Optional[ExperienceRecord]:
        return self._records.get(intent_hash)

    def __len__(self) -> int:
        return len(self._records)


@dataclass(frozen=True)
class DistilledAnswer:
    intent_hash: str
    text: str
    refs: Tuple[ObjectRef, ...]
    source_pathway: str
    reused_experience: bool
    token_cost: int
    hit_accuracy: float


class OperationExperienceDistiller:
    """黄金优选检索经验持久化：15,000~50,000 Token → ≤500 Token，准确率 100%。"""

    def __init__(self, bus: MultidimensionalSearchBus, pool: ExperiencePool) -> None:
        self._bus = bus
        self._pool = pool
        self._attempts: Dict[str, List[Tuple[PathwayReport, PathwayReport, PathwayReport]]] = {}

    def observe(self, terms: Sequence[str]) -> Tuple[PathwayReport, PathwayReport, PathwayReport]:
        reports = PathwayComparisonExecutor(self._bus).run_all(terms)
        key = intent_hash_of(terms)
        self._attempts.setdefault(key, []).append(reports)
        return reports

    def maybe_distill_gold(self, terms: Sequence[str]) -> Optional[ExperienceRecord]:
        """同族观察满阈值且三路径结论一致 → 将最优路径固化为黄金经验。"""
        key = intent_hash_of(terms)
        runs = self._attempts.get(key, [])
        if len(runs) < MIN_OBSERVATIONS_FOR_GOLD:
            return None
        ref_sets = {tuple(r[0].refs) for r in runs}
        if len(ref_sets) != 1:
            return None
        golden: Optional[PathwayReport] = None
        for report in (r[2] for r in runs):  # C 拓扑分级
            if report.refs != runs[0][0].refs:
                return None
            if golden is None or report.token_cost < golden.token_cost:
                golden = report
        if golden is None or golden.token_cost >= min(r[0].token_cost for r in runs):
            return None  # 只有绝对更省的路径才配入库
        record = ExperienceRecord(
            intent_hash=key, query=" ".join(terms),
            golden_pathway=golden.pathway, token_cost=golden.token_cost,
            doc_reads=golden.doc_reads, accuracy=1.0, runs=len(runs),
            evidence_ref_ids=tuple(ref.object_id for ref in golden.refs),
        )
        if self._pool.append(record):
            return record
        return self._pool.get(key)

    def distilled_search(self, terms: Sequence[str]) -> Optional[DistilledAnswer]:
        key = intent_hash_of(terms)
        record = self._pool.get(key)
        if record is None:
            return None
        refs = tuple(ObjectRef(object_id=oid, revision=1) for oid in record.evidence_ref_ids)
        text = f"经验直达[{record.golden_pathway}] {record.query} → 证据 {len(refs)} 条：" + \
            "、".join(record.evidence_ref_ids[:12])
        cost = estimate_tokens(text)
        if cost > DISTILL_TARGET_TOKENS:
            raise AssertionError("distilled answer breached 500-token envelope")
        return DistilledAnswer(
            intent_hash=key, text=text, refs=refs,
            source_pathway=record.golden_pathway, reused_experience=True,
            token_cost=cost, hit_accuracy=record.accuracy,
        )
