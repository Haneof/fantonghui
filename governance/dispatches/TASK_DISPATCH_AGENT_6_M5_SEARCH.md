# 工单 #6：M5-001 多维世界搜索底座与操作总线原生装配 (Multidimensional Search Base)

- **派发代号**：`TASK-M5-001-SEARCH`
- **指派战队**：Agent-06 战队（搜索与索引研发）
- **所属模块**：C02 存储底座、C03 检索层、C08 操作驾驶舱
- **前置依赖**：`M1-017`、`M1-018`
- **目标分支**：`arena/agent-06-m5-search`

## 1. 任务背景与核心目标
多维世界是 AI 认知人生的基石。AI 面对海量真实时空流（10,000~100,000+ 事实）时，绝不能靠暴力全表扫。必须提供毫秒级多维感知检索总线，支持按【维度 (Dimension) + 实体 (Entity) + 关键字 (CJK Bi-gram) + 时空窗 (Temporal Window) + 外挂注记 (RetrospectiveAnnotation)】联合召回。

## 2. 核心交付代码
1. `src/aios_core/query/search.py`:
   - 增加 `derive_dimension(payload, object_type) -> str` 维度推导；
   - 升级 `search_occurred` 表，支持 `dimension TEXT`；
   - 升级 `search_annotations` 表，在 `catch_up` 时自动同步外挂解释注记；
   - 提供 `search_mind(keywords, dimension, entity_id, object_types, time_range, limit) -> MindSearchPage`；
2. `src/aios_core/operations/world_operator.py`:
   - 实现 `MultidimensionalSearchOperator`；
   - 在 `WorldOperatorSuite` 中挂载 `self.search`，输出结构化命中与 Token 封套 (<= 150 Tokens)。

## 3. 验收标准
- 运行 `pytest tests/query/test_multidimensional_search.py` 100% 满绿；
- 单次多维联合检索耗时 <= 20ms，100% 召回今天挂载的外挂注记；
- 与 `co_search` 100% 向下兼容。
