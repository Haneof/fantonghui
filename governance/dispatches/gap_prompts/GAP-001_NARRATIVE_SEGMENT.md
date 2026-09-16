# AIOS 3.0 缺口补齐开发工单：叙事分段 (NarrativeSegment) 模型与切片管线构建工单

> **工单编号**：GAP-001  
> **宪法法统**：宪法第八章 第二十九条 / 第四编 第二十四章  
> **派发对象**：云端并发开发团队 (Cloud Development Agents)  
> **验收负责人**：Antigravity 首席架构师兼工程总指挥  
> **核心使命**：建立用户生命线按主题/事件/情境进行非线性切割与标注的叙事分段系统。作为人生相变(LifeChapter)识别的底层切片基石，支持跨维度线索编织与一键下钻。  

---

## 一、关联核心源代码清单

以下为必须阅读、修改或新建的代码路径：
- `src/aios_core/contracts/models.py`
- `src/aios_core/contracts/enums.py`
- `src/aios_core/narrative/segmenter.py`
- `tests/narrative/test_narrative_segmenter.py`

---

## 二、详细规格要求与实现规范


### 1. 契约定义规范
- 在 `enums.py` 中注册 `ObjectType.NARRATIVE_SEGMENT` 与 `NarrativeSegmentStatus` (OPEN, SEALED, REVISED, MERGED)。
- 在 `models.py` 中定义继承自 `WorldObject` 的 `NarrativeSegment`。必须支持：
  - `title: str`, `description: str`, `segment_time: TemporalExtent`
  - `dimension_refs: list[ObjectRef]`, `key_event_refs: list[ObjectRef]`, `key_claim_refs: list[ObjectRef]`
  - `supersedes_ref: ObjectRef | None`, `merged_into_ref: ObjectRef | None`, `life_chapter_ref: ObjectRef | None`
  - `theme_tags: list[str]`, `coherence_score: float`
  - 强制 model_validator：合并必须带 `merged_into_ref`，封存必须带明确理由与标题，所有引用必须 pinned revision。

### 2. 管线实现与多方案探索
- 实现 `NarrativeSegmenter` 类，负责：
  - `open_segment` / `attach_event` / `attach_claim` / `seal_segment` / `merge_segments`
  - 按维度聚类主题切片 (`get_segments_by_dimension`)
  - 启发式或聚类算法探索：如何根据多维事件密度自动建议封存与开启新段落？

### 3. Agent 交付物要求
- 完整可运行代码，严禁任何占位符。
- 完备单测，覆盖状态机转移与引用校验。
- 撰写机制演进建议：如何在端侧资源受限下实现高内聚的叙事切割。


---

## 三、云端 Agent 并发执行与择优机制

1. **多 Agent 独立并发探索**：
   - 各位 Agent 请读取仓库主干代码，基于上述规范独立设计实现。
   - 允许不同的内部算法演进方案（例如不同的聚类方式、不同的导数平滑算法）。
2. **零偷懒、零占位符铁律**：
   - 严禁 `# TODO`, `# ...`, `pass` 等糊弄代码，必须 100% 可直接交付生产。
   - 所有模型字段和时间校验必须符合宪法三类时间解耦原则。
3. **提交物与优化报告**：
   - 提交完整的代码与测试用例（`pytest` 必须 100% 满绿）；
   - 附带一份《方案设计与性能优化报告》，详细阐述你的算法选型优势。
   - 最终由总工在沙箱中跑分并熔铸择优。
