# AIOS 3.0 缺口补齐开发工单：工具提案 (ToolProposal) 全生命周期管线与自适应演化工单

> **工单编号**：GAP-003  
> **宪法法统**：宪法第二十章 第七十条 / 第二十八章 插件体系  
> **派发对象**：云端并发开发团队 (Cloud Development Agents)  
> **验收负责人**：Antigravity 首席架构师兼工程总指挥  
> **核心使命**：实现 AI 自发察觉能力短板、自主提出新工具提案、经历沙箱评估、审批与动态挂载的自演进闭环。  

---

## 一、关联核心源代码清单

以下为必须阅读、修改或新建的代码路径：
- `src/aios_core/contracts/models.py (已有模型)`
- `src/aios_core/contracts/enums.py`
- `src/aios_core/tools/proposal_pipeline.py`
- `tests/tools/test_proposal_pipeline.py`

---

## 二、详细规格要求与实现规范


### 1. 业务流程闭环
- 提案状态流转：`DRAFT` -> `SUBMITTED` -> `UNDER_REVIEW` -> `APPROVED` / `REJECTED` -> `EXECUTED` -> `RETIRED`。
- 实现 `ToolProposalPipeline`：
  - `submit_proposal`: 严格校验能力缺口说明与预期收益；
  - `review_proposal`: 支持安全策略拦截与资源配额审核；
  - `execute_proposal`: 模拟或真实执行动态挂载；
  - `retire_proposal`: 废弃落后工具。

### 2. Agent 交付物要求
- 机制突破：设计一套让 AI 根据历史检索耗时自动发起'索引加速工具提案'的示例策略。
- 满绿单测与架构评审报告。


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
