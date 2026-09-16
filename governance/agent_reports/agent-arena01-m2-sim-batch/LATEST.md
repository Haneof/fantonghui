# Agent Batch Report (arena01) — M2-005R / M2-001 / M3-001R / SIM-001

- 日期：2026-09-16（Asia/Shanghai）
- 分支：`arena/01a0a700-fantonghui`
- 共存声明：推送时发现远端已被先行集成两条并行线（规范线 `conditional_engine.py`
  与并存线 `*_agent05.py`，内容与本交付无关且均不同）。按「绝不覆盖任何版本、
  并行实现独立起名」铁律，本批次全部改称 `*_arena01` 独立命名落位，与两条既有
  线零冲突并存；远端既有 13 个同名/同名词缀文件 **本批次未触碰任何字节**。

## 交付与闸门（全部绿）
- **M2-005R** `src/aios_core/scheduler/conditional_engine_arena01.py` +
  `tests/unit/test_m2_005r_conditional_scheduler_arena01.py`（9/9）：
  DORMANT 隐形 `dormant_token_charge==0`；L1 机械快轨（TIME_ABSOLUTE/地理围栏
  Haversine/HR·METRIC）单条件 <1ms、200 任务 tick <0.5s、`llm_calls==0`；
  L2 仅用户唤醒时 `scene_tags ⊆ wake_tags` 子集搭车（无评测器 fail-closed）；
  非法跃迁 100% 抛 `IllegalStateTransitionError`。
- **M2-001** `src/aios_core/wake/cooldown_queue_arena01.py` +
  `tests/unit/test_m2_001_wake_cooldown_arena01.py`（8/8）：250 条 50Hz 脉冲/5s
  → 1 `MergedBatch`（`key|ts|kind|value` SHA-1 精确重放去重）；自适应冷却
  15→30min 夹取；DEEP_SLEEP 非 P0 无损暂存、motor 0 震动、深睡中
  `flush_silent_backlog` 抛 `ValueError`、P0 直穿；晨间冲刷 ts 升序 +
  P0>P1>P2>P3、分组计数、单声轻震、空冲刷幂等。
- **M3-001R** `src/aios_core/dimensions/evolution_guard_arena01.py` +
  `tests/unit/test_m3_001r_dimension_guard_arena01.py`（13/13）：准入
  ≥2 物理域 & 跨度≥3d（不合格 REJECTED 附原因）；30d 试炼准确率≥0.70 且
  覆盖≥0.80 否则 EXPIRED；同日重放/日期伪造抛错；反思配额 1/自然日
  （`QuotaExceededBlockError`）、父链自引用 >1 层 `ReflectionLoopCutError` +
  熔断人工复位；活跃上限 32，逐出分 `activity*0.6+contribution*0.4`（9dp，
  并列最小 slug 归档），200 维风暴 ≤32 活跃。
- **SIM-001** `src/aios_core/simulation/headless_life_driver_arena01.py` +
  `tests/simulation/test_30day_headless_life_simulation_arena01.py`（4/4）：
  720h/43,200 tick 决定性人生流；整 120 场会议；13 对车间图像；day-22 老王
  合同违约链；C01 原始二进制滞留严格 0；C02 落账 854 行；C04 单日看板
  ≤1500 Token 且总耗 << 2,554,000 封套（封套硬违约演练被引擎硬拒）；
  C05 as-of 0 层/现视图 1 层；联调 M2-001（8,640 批次）与 M2-005R
  （违约作战室自动 READY，0 LLM）；43,577 次连环锁压力段 0 死锁；
  tracemalloc 峰值 ≤64MB、RSS 增量 ≤128MB。
- `governance/runtime_policy_arena01.json`：月度封套 2,554,000 全局锚点
  （同级 `runtime_policy.json` 为先到者版本，未改一字）。

## 新增文件（13 项，全部 NEW）
`governance/runtime_policy_arena01.json`；
`src/aios_core/scheduler/conditional_engine_arena01.py`；
`src/aios_core/wake/cooldown_queue_arena01.py`；
`src/aios_core/dimensions/evolution_guard_arena01.py`；
`src/aios_core/simulation/headless_life_driver_arena01.py`；
`tests/unit/test_m2_005r_conditional_scheduler_arena01.py`；
`tests/unit/test_m2_001_wake_cooldown_arena01.py`；
`tests/unit/test_m3_001r_dimension_guard_arena01.py`；
`tests/simulation/test_30day_headless_life_simulation_arena01.py`；
`governance/agent_reports/agent-arena01-m2-sim-batch/LATEST.md`。
（包级 `__init__.py` 均已由先到线提供，本批次不新建、不修改。）
