# 工单 #5：M1-018 认知反向传播语义图层契约 (老王案/历史不可篡改铁律)

- **派发代号**：`TASK-M1-018`
- **指派战队**：Agent-05 战队（多模型并行开发）
- **所属模块**：C02 存储底座与 C05 复盘回溯层
- **前置依赖**：`M0-004`、`M0-005`、`M0-017`
- **目标分支**：`arena/agent-05-m1-018`

## 1. 任务背景与核心目标（最高宪法铁律）
严格落实**宪法第 93 条与用户最高指示**：
> “只标记当前时间节点的事件，老王是骗子这个标签，没必要回去把所有对话都改成老王是骗子！”
> “推翻历史认知时，新认知只追加在今天，严禁倒写历史！”

**核心工程规约**：
1. 过去发生的客观事实 `Observation`（两年前与老王合伙、喝酒聊天、当时的心率）**字节级不可篡改，绝对严禁执行 SQL UPDATE / DELETE**！
2. 今天获知新认知时，生成一条 `RetrospectiveAnnotation`：
   - 自身时间戳 `learned_at = recorded_at = T_now`（今天）；
   - 指针 `valid_time_range = [两年前, 两年前]`，指向过去老王参与的时空切片；
3. 建立“双时间视图”查询透镜：
   - **当时已知视图（As-Of Cutoff）**：在过去那个切片看，老王是可信合伙人（忠实记录当时人生状态）；
   - **当前认知视图（Current View）**：在今天看过去切片，叠加了“后来发现是骗子”的外部解释图层（Overlay），历史曲线原貌不受任何破坏！

## 2. 接口契约与代码骨架
在 `src/aios_core/world/retrospective_annotation.py` 实现：

```python
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class RetrospectiveAnnotation(BaseModel):
    annotation_id: str
    target_entity_id: str
    semantic_overlay: str = Field(..., description="挂载的解释图层，如'疑似欺诈'")
    target_time_start: datetime
    target_time_end: datetime
    learned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_statement_ref: str

class EpistemicWorldLens:
    def query_historical_slice(self, entity_id: str, target_time: datetime, as_of_cutoff: Optional[datetime] = None):
        # 若 as_of_cutoff == target_time: 仅返回当时已知（不包含后来的反向注记）
        # 若 as_of_cutoff is None: 返回当前认知叠加视图
        pass
```

## 3. 验收标准与 pytest 断言代码
在 `tests/unit/test_m1_018_retrospective_annotation.py` 验证：
- 断言两年前原始 Observation 记录的哈希值在加注后 100% 保持不变；
- 断言根据 `as_of_cutoff` 查询能够完全重现当时的原貌；
- 断言不产生无界的级联历史重算。
