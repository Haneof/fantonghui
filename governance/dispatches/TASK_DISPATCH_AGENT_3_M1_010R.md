# 工单 #3：M1-010R 5D 时空多尺度连续聚合器与时间金字塔物化视图

- **派发代号**：`TASK-M1-010R`
- **指派战队**：Agent-03 战队（多模型并行开发）
- **所属模块**：C05 多尺度总结与人生章节层
- **前置依赖**：`M0-011`、`M0-017`
- **目标分支**：`arena/agent-03-m1-010r`

## 1. 任务背景与核心目标
落实**宪法第二十五至二十七条**：总结是新观察层，绝非压缩删除底层事实。
实现多尺度时间金字塔（从日总结、周总结、月总结到年度大纲），支持手环端侧 5D 滑动条从 1 秒到 10 年连续时间无损下钻。
物理距离(x,y,z) × 时间衰减(t) × 羁绊权重(r) × 可信度(c) 多维聚合函数，物化至金字塔缓存，下钻响应 $\le 45\text{ms}$。

## 2. 接口契约与代码骨架
在 `src/aios_core/summaries/pyramid_aggregator.py` 实现：

```python
from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel, Field

class TimePyramidSummary(BaseModel):
    summary_id: str
    scale: str = Field(..., description="DAY / WEEK / MONTH / YEAR")
    start_time: datetime
    end_time: datetime
    dimension_id: str
    headline: str
    synthesis_text: str
    evidence_ids: List[str]
    missingness_ratio: float = 0.0

class PyramidAggregator:
    def generate_materialized_rollup(self, scale: str, dimension_id: str, events: List[Dict[str, Any]]) -> TimePyramidSummary:
        # 聚合计算：绝不删除底层 events，仅提取高阶物化层
        evidence_ids = [e["id"] for e in events]
        return TimePyramidSummary(
            summary_id=f"sum_{scale.lower()}_{dimension_id}_{int(datetime.now().timestamp())}",
            scale=scale,
            start_time=events[0]["time"],
            end_time=events[-1]["time"],
            dimension_id=dimension_id,
            headline=f"{scale} 阶段性演变概览",
            synthesis_text=f"在此跨度内沉淀了 {len(events)} 项核心事实，关系稳步加深。",
            evidence_ids=evidence_ids
        )
```

## 3. 验收标准与 pytest 断言代码
在 `tests/unit/test_m1_010r_pyramid.py` 验证：
- 总结包含全部底层 evidence_ids，证据链完整无裂纹；
- 下钻时底层事件完好无损。
