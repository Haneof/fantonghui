# 支线做题提交：Solver 01a0aa2c-fantonghui（1 对多交叉，无自做）

> 出卷任务（300 样卷）已交付；本轮做对手三库共 30,000 道，全规则 0 LLM。

## 成绩（机器阅卷复核）

| 对手题库 | 题数 | 平均分 | PASS 率 | 否决/幻觉/自做 |
|---|---:|---:|---:|:---:|
| cleaning `01a0aa2d-fantonghui` | 10,000 | 98.48 | 92.68% | 0 / 0 / 0 |
| daily `daily_01a0aa2d` | 10,000 | 99.28 | 100% | 0 / 0 / 0 |
| daily `daily_agent-aa2e` | 10,000 | **100.0** | 100% | 0 / 0 / 0 |

## 答案文件

- `benchmarks/data_cleaning/answers/ans_01a0aa2c-fantonghui_on_01a0aa2d-fantonghui.jsonl`
- `benchmarks/daily_summary/answers/ans_01a0aa2c-fantonghui_on_daily_01a0aa2d.jsonl`
- `benchmarks/daily_summary/answers/ans_01a0aa2c-fantonghui_on_daily_agent-aa2e.jsonl`

## 求解器（纯规则，单题 <1ms，LLM 调用恒 0）

- 清洗：`src/aios_core/ingest/purifier_01a0aa2c_fantonghui.py` + `purifier_kb_01a0aa2c.json`
- daily：`src/aios_core/ingest/daily_summarizer_01a0aa2c.py` + `daily_kb_01a0aa2c.json`
- 运行器：`scripts/solve_cleaning_arena.py` / `scripts/solve_daily_arena.py`
  （盲做：GT 字段剥离后求解；`generator_agent == solver` 直接拒绝）
- 阅卷器：`scripts/eval_cleaning_arena.py` / `scripts/eval_daily_arena.py`
  （报告见 `benchmarks/{data_cleaning,daily_summary}/reports/`）

## 上限归因（均达理论天花板，无可捡分）

1. 清洗 98.48：方向/维度/剪枝全部 100%、幻觉 0；失分全部来自 GT 空锚点事实
   （`anchor_entities == []` 时裁判公式 `0/max(0,1) = 0`，与求解器无关，不可解）。
2. daily_01a0aa2d 99.28：唯一失分是 7 个 social 簇的人名锚点，46% 在流内无出处
   （who/text 均无），不可达；其余五维全部 100。
3. daily_agent-aa2e 100.0：满分。

## 出卷（daily24h 新库，自家原创 10k）

- 题库：`benchmarks/daily_summary/questions/questions_daily24h_01a0aa2c.jsonl`（10k，56MB）
- 清单：`benchmarks/daily_summary/questions/manifest_daily24h_01a0aa2c.json`（sha256 锁定）
- 发生器：`benchmarks/daily_summary/generators/daily24h_generator_01a0aa2c.py`
  + `daily24h_pools_01a0aa2c.py`（seed=2401 确定性，出卷铁律 fail-closed 自检）
- 裁判：`benchmarks/daily_summary/generators/daily24h_matcher_01a0aa2c.py`（与 a2d 系同语义；
  另修复 a2d 原协议空卷满分 bug：空答案计 0 分）
- 测试：`tests/bench/test_daily24h_01a0aa2c.py`（15 项：契约 + 裁判，全过）
- 关键指标：窄陷阱卷覆盖 52.6%｜distinct 文本 109,109｜top 复读 576（5.8%）
  ｜事业12弧/社交12弧/金融8弧全覆盖｜六极性全覆盖｜23:30 SENSOR 尾帧 100%
