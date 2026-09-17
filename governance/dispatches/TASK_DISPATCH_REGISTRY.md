# M1/M5 里程碑云端派工总表与工单索引

本文档为 AI 模型团队在 GitHub 云端领单开发的唯一派发索引。

| 提示词代号 | 领单工单文件 | 对应工程任务 | 目标分支建议 | 核心交付源码 |
|---|---|---|---|---|
| **1号提示词** | [`TASK_DISPATCH_AGENT_1_M1_001R.md`](./TASK_DISPATCH_AGENT_1_M1_001R.md) | `M1-001R` 多模态清洗与声纹TTL | `arena/agent-01-m1-001r` | `src/aios_core/ingest/multimodal_edge.py` |
| **2号提示词** | [`TASK_DISPATCH_AGENT_2_M1_017.md`](./TASK_DISPATCH_AGENT_2_M1_017.md) | `M1-017` CJK 倒排索引加速表 | `arena/agent-02-m1-017` | `src/aios_core/query/cjk_inverted_index.py` |
| **3号提示词** | [`TASK_DISPATCH_AGENT_3_M1_010R.md`](./TASK_DISPATCH_AGENT_3_M1_010R.md) | `M1-010R` 5D 时空多尺度金字塔 | `arena/agent-03-m1-010r` | `src/aios_core/summaries/pyramid_aggregator.py` |
| **4号提示词** | [`TASK_DISPATCH_AGENT_4_M1_012R.md`](./TASK_DISPATCH_AGENT_4_M1_012R.md) | `M1-012R` 实体拓扑超链接网络 | `arena/agent-04-m1-012r` | `src/aios_core/query/hyperlink_traverser.py` |
| **5号提示词** | [`TASK_DISPATCH_AGENT_5_M1_018.md`](./TASK_DISPATCH_AGENT_5_M1_018.md) | `M1-018` 认知反向回溯标注 (老王案) | `arena/agent-05-m1-018` | `src/aios_core/world/retrospective_annotation.py` |
| **6号提示词** | [`TASK_DISPATCH_AGENT_6_M5_SEARCH.md`](./TASK_DISPATCH_AGENT_6_M5_SEARCH.md) | `M5-001` 多维搜索底座与操作总线 | `arena/agent-06-m5-search` | `src/aios_core/query/search.py` |
| **7号提示词** | [`TASK_DISPATCH_AGENT_7_M5_DIM_LIFECYCLE.md`](./TASK_DISPATCH_AGENT_7_M5_DIM_LIFECYCLE.md) | `M5-002` 维度生命周期与高阶提炼 | `arena/agent-07-m5-dim-lifecycle` | `src/aios_core/cognition/dimension_engine.py` |
| **8号提示词** | [`TASK_DISPATCH_AGENT_8_M5_RAPPORT_MIRROR.md`](./TASK_DISPATCH_AGENT_8_M5_RAPPORT_MIRROR.md) | `M5-003` AI自身维度总结与羁绊镜面 | `arena/agent-08-m5-rapport-mirror` | `src/aios_core/cognition/self_reflection.py` |
| **9号提示词** | [`TASK_DISPATCH_AGENT_9_M5_SYMBIOTIC_ADVISOR.md`](./TASK_DISPATCH_AGENT_9_M5_SYMBIOTIC_ADVISOR.md) | `M5-004` 共生决策辅助与行动推演 | `arena/agent-09-m5-action-advisor` | `src/aios_core/cognition/symbiotic_advisor.py` |
| **10号提示词** | [`TASK_DISPATCH_AGENT_10_M5_AGENT_ARENA.md`](./TASK_DISPATCH_AGENT_10_M5_AGENT_ARENA.md) | `M5-005` 独立Agent战训考场诊断器 | `arena/agent-10-m5-agent-arena` | `src/aios_core/simulation/agent_mind_bench.py` |
| **11号总工令** | [`TASK_DISPATCH_MASSIVE_DATA_CLEANING_ARENA_10K.md`](./TASK_DISPATCH_MASSIVE_DATA_CLEANING_ARENA_10K.md) | `MASS-CLEAN-ARENA` 全兵团数据清洗出题与交叉做题大考（每人1万题） | `arena/agent-*-cleaning-10k` | `benchmarks/data_cleaning/dataset_cleaning_10k.jsonl` + `src/aios_core/ingest/llm_data_purifier.py` |
| **12号总工令** | [`TASK_DISPATCH_COGNITIVE_ARENA_DUAL_WORLD_AND_DIMENSIONS.md`](./TASK_DISPATCH_COGNITIVE_ARENA_DUAL_WORLD_AND_DIMENSIONS.md) | `M5-COGNITIVE-ARENA` 核心认知实战大考（多维联动因果 × 双平行世界自省 × 新维度提炼与合宪注册） | `arena/agent-*-cognitive-exam` | `src/aios_core/simulation/cognitive_arena_protocol.py` + `benchmarks/cognitive_arena/` |
| **13号总工令** | [`TASK_DISPATCH_3YEAR_MASSIVE_LIFE_COGNITIVE_EVOLUTION.md`](./TASK_DISPATCH_3YEAR_MASSIVE_LIFE_COGNITIVE_EVOLUTION.md) | `M5-3YEAR-SYSTEM-ARENA` 三年前瞻·数万人千人千面原生系统级实战（3年人生 × 真实内核接入 × 预测对撞与系统优化） | `arena/agent-*-3year-sim` | `src/aios_core/simulation/headless_life_driver.py` + `storage/sqlite_store.py` |
