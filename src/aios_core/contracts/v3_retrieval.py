"""
V3 Retrieval Engine Contracts
M1-020 Co-occurrence + Graph + 5D Slider + M1-021 Materialized Views

独立首席架构师重构：检索脊柱，解决FTS中文0命中+单关键词割裂
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Posting(BaseModel):
    keyword: str
    object_id: str
    object_type: str
    tf: float = 1.0
    position: int = 0

class CoSearchRequest(BaseModel):
    keywords: List[str] = Field(description="[妈妈, 生日, 礼物] 直接取拓扑交集")
    time_range: Optional[tuple[datetime, datetime]] = None
    entity_filter: Optional[List[str]] = None
    limit: int = 20

class CoSearchResult(BaseModel):
    intersection_nodes: List[str] = Field(description="同时命中多关键词的Event/Claim/Entity ID")
    resonance_score: float = Field(description="共振密集度")
    pointers: List[str] = Field(description="超链接指针，AI按需navigate")
    query_plan: str = Field(description="POSTING_INTERSECTION+BFS2 / MATERIALIZED")
    coverage: float
    truncated: bool
    watermark: Optional[int] = None

class GraphEdge(BaseModel):
    src_id: str
    dst_id: str
    edge_type: str  # PARTICIPANT_OF / EVIDENCE_OF / DERIVED_FROM / RELATED_TO
    weight: float = 1.0

class ResonanceMaterialized(BaseModel):
    resonance_id: str
    keywords_hash: str
    node_ids: List[str]
    score: float
    last_updated: datetime

class TimeSliderRequest(BaseModel):
    scale: str = Field(description="1s|10s|1min|10min|1h|1d|1w|1m|1y|10y")
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    offset: Optional[str] = None  # "-1d" / "+1w"

class TimeSliceResult(BaseModel):
    refs: List[str]
    coverage: float
    omitted_count: int
    watermark: int
    granularity: str

# Core algorithm pseudocode as docstring for implementation reference
ALGORITHM = """
def co_search(req: CoSearchRequest) -> CoSearchResult:
    # 1. 中文预分词版本化（解决FTS默认单字切分，'给妈妈买生日礼物'→[妈妈,生日,礼物]）
    keywords = [normalize_with_tokenizer_v2(k) for k in req.keywords]  # jieba+自定义词库，版本化

    # 2. 倒排posting取交集
    postings = [get_postings(k) for k in keywords]  # each: set(object_id)
    intersection = set.intersection(*postings) if postings else set()

    # 3. 若交集为空，图扩展≤2跳，扇出上限100，防超级节点爆炸
    if not intersection:
        expanded = set()
        for kw in keywords:
            seeds = get_postings(kw)
            for seed in seeds:
                neighbors = bfs(seed, depth=2, fanout_limit=100)
                expanded.update(neighbors)
        intersection = {n for n in expanded if count_keywords_hit(n, keywords) >= 2}

    # 4. 共振评分：同时命中关键词数 × 图距离衰减 × 时间新鲜度
    scored = []
    for nid in intersection:
        score = len(keywords_hit(nid)) * graph_distance_decay(nid) * recency_decay(nid)
        scored.append((nid, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    # 5. 物化表加速
    mat = get_materialized(keywords_hash(req.keywords))
    if mat and now - mat.last_updated < 1d:
        return CoSearchResult(..., query_plan="MATERIALIZED", ...)

    topk = [nid for nid,_ in scored[:req.limit]]
    return CoSearchResult(intersection_nodes=topk, resonance_score=scored[0][1] if scored else 0, pointers=topk, query_plan="POSTING_INTERSECTION+BFS2", coverage=len(topk)/len(intersection) if intersection else 0, truncated=len(intersection)>req.limit)

def bfs(start_id: str, depth: int, fanout_limit: int) -> set:
    visited=set(); queue=[(start_id,0)]
    while queue:
        nid,d = queue.pop(0)
        if d>=depth: continue
        neighbors = get_graph_neighbors(nid)[:fanout_limit]  # 扇出上限防超级节点
        for nb in neighbors:
            if nb not in visited:
                visited.add(nb); queue.append((nb,d+1))
    return visited
"""

SQL_DDL = """
CREATE TABLE fts_index (
  keyword TEXT,
  object_id TEXT,
  object_type TEXT,
  tf REAL,
  tokenizer_version TEXT, -- 版本化
  PRIMARY KEY (keyword, object_id)
);
CREATE INDEX idx_fts_kw ON fts_index(keyword);
CREATE INDEX idx_fts_obj ON fts_index(object_id);

CREATE TABLE graph_edges (
  src_id TEXT,
  dst_id TEXT,
  edge_type TEXT,
  weight REAL,
  PRIMARY KEY (src_id, dst_id, edge_type)
);
CREATE INDEX idx_graph_src ON graph_edges(src_id);
CREATE INDEX idx_graph_dst ON graph_edges(dst_id);

CREATE TABLE resonance_materialized (
  resonance_id TEXT PRIMARY KEY,
  keywords_hash TEXT,
  node_ids JSONB,
  score REAL,
  last_updated TIMESTAMPTZ
);
CREATE INDEX idx_resonance_hash ON resonance_materialized(keywords_hash);

-- 5D Slider物化视图
CREATE MATERIALIZED VIEW mv_daily AS
SELECT subject_id, dimension_id, date_trunc('day', occurred_at) as day, avg((value_json->>'avg_bpm')::float) as avg_bpm, count(*) as cnt
FROM observations_edge WHERE signal_quality!='NOISE' GROUP BY 1,2,3;

CREATE MATERIALIZED VIEW mv_weekly AS
SELECT subject_id, dimension_id, date_trunc('week', occurred_at) as week, avg((value_json->>'avg_bpm')::float) as avg_bpm, count(*) as cnt
FROM observations_edge GROUP BY 1,2,3;

CREATE MATERIALIZED VIEW mv_monthly AS
SELECT subject_id, dimension_id, date_trunc('month', occurred_at) as month, avg((value_json->>'avg_bpm')::float) as avg_bpm, count(*) as cnt
FROM observations_edge GROUP BY 1,2,3;
"""
