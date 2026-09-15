# 工单 #2：M1-017 CJK 拓扑倒排聚集表与多词检索加速引擎

- **派发代号**：`TASK-M1-017`
- **指派战队**：Agent-02 战队（多模型并行开发）
- **所属模块**：C06 拓扑查询与超链接检索层
- **前置依赖**：`M0-017`、`M1-001R`
- **目标分支**：`arena/agent-02-m1-017`

## 1. 任务背景与核心目标
在真实压测中，SQLite 默认 FTS5 引擎对中文不分词，用户检索 `[妈妈, 生日, 礼物]` 返回结果直接为 0！
必须在底层建立两张专用加速表：
1. `topological_cjk_terms`（一元与二元重叠倒排分词表）；
2. `entity_co_occurrence_edges`（实体与关键词高频共现拓扑预聚合表）；
3. 实现多词联合检索算法：执行 SQL `SELECT entity_id FROM topological_cjk_terms WHERE term IN (...) GROUP BY entity_id HAVING COUNT(DISTINCT term) = :num_terms` 毫秒级求交集！

## 2. 物理 DDL 与必须实现的代码骨架
在 `src/aios_core/query/cjk_inverted_index.py` 实现：

```sql
CREATE TABLE IF NOT EXISTS topological_cjk_terms (
    term TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    occurred_at INTEGER NOT NULL,
    PRIMARY KEY (term, entity_id, occurred_at)
);
CREATE INDEX IF NOT EXISTS idx_cjk_term_occurred ON topological_cjk_terms (term, occurred_at DESC);

CREATE TABLE IF NOT EXISTS entity_co_occurrence_edges (
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    co_occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_occurred_at INTEGER NOT NULL,
    PRIMARY KEY (source_entity_id, target_entity_id)
);
CREATE INDEX IF NOT EXISTS idx_co_count ON entity_co_occurrence_edges (co_occurrence_count DESC);
```

Python 切分与检索引擎：
```python
import sqlite3
from typing import List, Set

def tokenize_cjk_overlapping(text: str) -> Set[str]:
    # 纯 Python 一元/二元重叠分词切分器 (零外部三方重库依赖)
    terms = set()
    cleaned = "".join([c for c in text if c.isalnum() or c in "，。？！"])
    for i in range(len(cleaned)):
        terms.add(cleaned[i])
        if i + 1 < len(cleaned):
            terms.add(cleaned[i:i+2])
    return terms

class CJKTopologicalInvertedIndex:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def index_entity_text(self, entity_id: str, text: str, timestamp_ns: int):
        terms = tokenize_cjk_overlapping(text)
        with self.conn:
            for t in terms:
                self.conn.execute(
                    "INSERT OR IGNORE INTO topological_cjk_terms (term, entity_id, occurred_at) VALUES (?, ?, ?)",
                    (t, entity_id, timestamp_ns)
                )

    def co_search(self, query_terms: List[str]) -> List[str]:
        if not query_terms:
            return []
        placeholders = ",".join(["?"] * len(query_terms))
        sql = f'''
            SELECT entity_id 
            FROM topological_cjk_terms 
            WHERE term IN ({placeholders}) 
            GROUP BY entity_id 
            HAVING COUNT(DISTINCT term) = ?
        '''
        cursor = self.conn.cursor()
        cursor.execute(sql, (*query_terms, len(query_terms)))
        return [row[0] for row in cursor.fetchall()]
```

## 3. 验收标准与 pytest 断言代码
在 `tests/unit/test_m1_017_cjk_index.py` 必须跑通：
```python
def test_cjk_co_search_intersection():
    conn = sqlite3.connect(":memory:")
    # 建表...
    index = CJKTopologicalInvertedIndex(conn)
    now_ns = 1726400000000000000
    index.index_entity_text("ent_mom", "给妈妈买生日礼物，妈妈非常喜欢这个礼物", now_ns)
    index.index_entity_text("ent_dad", "爸爸喜欢钓鱼，送爸爸一个渔具", now_ns)
    
    # 三词求交集
    hits = index.co_search(["妈妈", "生日", "礼物"])
    assert "ent_mom" in hits
    assert "ent_dad" not in hits
    assert len(hits) == 1
```
