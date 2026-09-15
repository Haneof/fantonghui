# 工单 #4：M1-012R 实体拓扑超链接网络穿透检索器

- **派发代号**：`TASK-M1-012R`
- **指派战队**：Agent-04 战队（多模型并行开发）
- **所属模块**：C06 拓扑查询与超链接检索层
- **前置依赖**：`M0-010`、`M0-012`
- **目标分支**：`arena/agent-04-m1-012r`

## 1. 任务背景与核心目标
废除旧时代基于单表的低效模糊扫表（`LIKE %xxx%`）。
构建穿透图谱：`Entity -> EventAnchor -> EvidenceSet -> Observation`。
当查找某人物（如“老王”）时，通过超链接图谱在 25ms 内向上遍历其所有参与的事件、证据组与原始言论，并支持别名（如“王叔”、“老王八蛋”）自动链接归一。

## 2. 接口契约与代码骨架
在 `src/aios_core/query/hyperlink_traverser.py` 实现：

```python
from typing import List, Dict, Any, Optional

class HyperlinkTraversalResult(BaseModel):
    root_entity_id: str
    matched_aliases: List[str]
    anchors: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    traversal_depth: int
    traversal_ms: float

class EntityHyperlinkGraphTraverser:
    def traverse_entity_network(self, entity_id: str, depth: int = 4) -> HyperlinkTraversalResult:
        # 执行图扩散与穿透索引
        pass
```

## 3. 验收标准与 pytest 断言
在 `tests/unit/test_m1_012r_hyperlink.py` 验证：
- 深度为 4 穿透检索耗时 $\le 25\text{ms}$；
- 返回完整的实体、锚点与观察事实拓扑链。
