# 工单 #5：M1-018 认知反向传播语义图层契约 (高阶双时间透镜与单跳隔离)

- **派发代号**：`TASK-M1-018`
- **指派战队**：Agent-05 战队（多模型并行开发）
- **所属模块**：C02 存储底座与 C05 复盘回溯层
- **前置依赖**：`M0-004`、`M0-005`、`M0-017`
- **目标分支**：`arena/agent-05-m1-018`

## 1. 任务背景与核心目标（最高宪法铁律：历史事实绝不篡改，只在今天打标签）

严禁使用低幼玩具样例（如日常琐碎聊天、借还小额现金等）。必须基于**高阶复杂现实人生情境**建模：
> **复杂实战情境**：用户两年前与核心技术合伙人“王建国”签署联合孵化协议。在过去 730 天内，系统累积记录了 18,000 条客观 Observation 事实链（重大战略合同、股东会纪要、财务汇款往来凭证、晚间心率与压力体征指标）。
> 第 730 天（`T_now`），司法部门下达查封执行文书，证实该合伙人自创立之初即设立离岸壳公司转移资产并隐匿巨额对外连带担保。

**必须坚决捍卫的架构铁律**：
1. **历史 Observation 字节级绝对不可变**：
   - 过去 730 天内发生的 18,000 条事实（哪怕当时的推断写着“王建国是卓越合伙人”）**物理哈希不可改变，严禁任何 SQL UPDATE 或 DELETE**；
2. **今天写入外挂解释图层（`RetrospectiveAnnotation`）**：
   - 在今天（`T_now`）写下一条新认知：`learned_at = recorded_at = T_now`；
   - 目标有效区间 `valid_time_range = [T0, T_now]`，精确挂载于该商业实体；
3. **双时间认知透镜（Bi-Temporal Epistemic Lens）**：
   - **历史切片还原视图（`as_of_cutoff = T0 + 100d`）**：精准再现用户在第 100 天时面对的世界真实认知原貌（绝不产生“事后诸葛亮”的历史虚无主义）；
   - **当下审视全景视图（`as_of_cutoff = None` 即当前）**：在完整保留历史事实的基础上，外挂叠加上“事后证实为特大诈骗”的解释注记（Overlay）；
4. **单跳级联隔离（`SingleHopCascadeIsolator`）**：
   - 严禁触发级联回溯递归重算，将下游重算范围严格限制在单跳（Direct 1-Hop）范围内，杜绝无界 API 算力雪崩！

## 2. 必须实现的接口契约与代码骨架
在 `src/aios_core/world/retrospective_annotation.py` 实现：

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, Field, ConfigDict

class RetrospectiveAnnotation(BaseModel):
    """外挂回溯解释图层：只在今天写入，挂载指向历史时空。"""
    model_config = ConfigDict(extra="forbid")

    annotation_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    semantic_overlay: str = Field(..., description="挂载的法律/信用/关系重估事实标签")
    valid_time_start: datetime = Field(..., description="指向历史事件实际生效区间的起点")
    valid_time_end: datetime = Field(..., description="指向历史事件实际生效区间的终点")
    learned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="今天发现认知的时刻")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_evidence_ref: str = Field(..., description="如法院执行文书、司法审计报告等证据引用")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

class HistoricalEpistemicSlice(BaseModel):
    """双时间透镜查询产物：呈现当时历史与外挂注记。"""
    entity_id: str
    query_time: datetime
    as_of_cutoff: Optional[datetime]
    raw_observations: List[Dict[str, Any]]
    active_annotations: List[RetrospectiveAnnotation]
    effective_interpretation: str

class BiTemporalEpistemicLens:
    """双时间认知透镜：隔离当时已知与今日认知。"""
    def __init__(self, raw_store: Any, annotation_store: Any):
        self.raw_store = raw_store
        self.annotation_store = annotation_store

    def query_entity_state(
        self,
        entity_id: str,
        target_time: datetime,
        as_of_cutoff: Optional[datetime] = None,
    ) -> HistoricalEpistemicSlice:
        ...

class SingleHopCascadeIsolator:
    """单跳级联隔离器：彻底掐灭历史回溯引发的 210 次递归算力雪崩。"""
    def invalidate_downstream_single_hop(
        self,
        entity_id: str,
        annotation: RetrospectiveAnnotation,
        dependency_graph: Any,
    ) -> Set[str]:
        """
        仅将直接消费该实体认知的一级下游节点（1-Hop Direct Dependents）标记为 is_stale=True。
        对二度及更深远间接节点坚决禁止级联递归触发展开！
        """
        ...
```

## 3. 严苛单测与复杂对抗场景验收标准
在 `tests/unit/test_m1_018_retrospective_annotation.py` 中编写严密测试：
1. **历史哈希防篡改测试**：模拟 10,000 条高密度历史事实，写入新司法查封回溯注记后，逐条比对历史事实记录的 SHA-256 哈希，断言 100% 字节级一致；
2. **双时间透镜对撞测试**：传入 `as_of_cutoff = 两年前` 时，断言系统精准还原当时合作状态，`active_annotations` 严格为空；传入当前时间时，断言新注记精准叠加；
3. **单跳隔离深度防爆测试**：构建 5 层深度依赖拓扑网（10 个 1 级节点、200 个 2 级节点、1000 个 3 级节点），断言失效标记的节点数严格等于 1 级节点数（10 个），深度遍历次数严格为 1，杜绝级联重算。

