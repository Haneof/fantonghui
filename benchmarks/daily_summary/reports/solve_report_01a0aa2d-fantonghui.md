# 全天生活流与多维总结竞技场 · 做题方报告（战队 01a0aa2d-fantonghui）

> 角色：做题大模型（Solver）。只做**别人**的题，绝不做自己的题（铁律五：`solver == generator` 一票否决 = 0 分）。
> 本报告覆盖本轮在支线上新发现的 3 份全天生活流考卷 + 1 份遗留清洗竞技场考卷。

## 一、跨 Git 寻卷（支线扫描）

对 `origin` 全部分支做题库扫描（`benchmarks/**/questions/*.jsonl` + 对应标答），排除本战队自有考卷后，得到下列**可做卷**：

| 考卷 | 出卷战队 / 分支 | 题量 | 结构 | 标答形态 |
|---|---|---|---|---|
| `benchmarks/daily_summary/questions/questions_agent_aa2c_10k.jsonl` | `agent-aa2c`（`arena/01a0aa2c-fantonghui`） | 10,000 | `cleaned_daily_stream` 为切片数组 | 内嵌六维标答 |
| `benchmarks/daily_summary/questions/questions_daily24h_agent_aa2e.jsonl` | `agent-aa2e`（`arena/01a0aa2e-fantonghui`） | 10,000 | `date_span + events` | 内嵌六维标答 |
| `benchmarks/daily_summary/questions/questions_agent_01a0aa2c.jsonl` + `ground_truth/gt_agent_01a0aa2c.jsonl` | `agent-01a0aa2c`（`arena/01a0aa2c-fantonghui`） | 1,000 | 体征摘要 + 切片 | **独立标答文件**（最干净的判分形态） |
| `benchmarks/data_cleaning/questions/questions_agent-01.jsonl` + `ground_truth/gt_agent-01.jsonl` | `agent-01`（`arena/01a0a9fd-fantonghui`） | 1,000 | 清洗竞技场五路流 | 独立标答文件 |

本战队自有考卷 `questions_01a0aa2d-fantonghui.jsonl`（清洗竞技场）与 `questions_daily24h_*` 类自有卷一律**拒答**，做题引擎内建拦截：遇 `generator_agent ∈ {01a0aa2d, agent-aa2d}` 直接 `SystemExit` 并留痕。

## 二、盲做纪律（结构性保证，非口头承诺）

`src/aios_core/simulation/daily_summary_solver_01a0aa2d.py`：

1. `blind_question()` 在总结前**物理剥除** `directional_ground_truth / ground_truth / answer / label` 等一切标答字段；
2. `summarize_question()` 断言盲题标记 `_blind=True`，且函数体内不存在任何标答读入口（单测 `test_blind_discipline_and_no_label_leak`、`test_summarize_requires_blind_question` 硬门禁）；
3. 标答只在 `grade_answers()` 自评阶段使用；单测校验标答正文绝不外泄进答卷。

## 三、做题战果（官方裁判器 `DailySummaryDirectionalMatcher` 逐题六维判定）

| 考卷 | 题量 | 均分 | 通过率(≥80) | 红线触碰 | 全局 | 健康 | 人际 | 情绪 | 财务 | 事业 |
|---|---|---|---|---|---|---|---|---|---|---|
| `agent-aa2c` | 10,000 | **1.82** | 0.0% | 0 | 0.0 | 6.1 | 0.0 | 0.0 | 6.1 | 0.0 |
| `agent-aa2e` | 10,000 | **73.42** | 15.3% | 0 | 76.8 | 83.8 | 69.1 | 71.1 | 78.7 | 58.7 |
| `agent-01a0aa2c` | 1,000 | **67.72** | 20.2% | 0 | 73.0 | 85.7 | 60.6 | 65.9 | 62.9 | 54.8 |
| `agent-01`（清洗竞技场） | 1,000 | 25.0 | 0.0% | 幻觉 0 | — | — | — | — | — | — |

答卷与阅卷报告（本报告对应**盲做答卷**，文件名统一带 `_blind` 标识）：
- `benchmarks/daily_summary/answers/ans_01a0aa2d-fantonghui_on_{agent-aa2c,agent-aa2e,agent-01a0aa2c}_blind.jsonl`
- `benchmarks/daily_summary/reports/report_01a0aa2d-fantonghui_on_{...}_blind.json`
- `benchmarks/data_cleaning/answers/ans_01a0aa2d-fantonghui_on_agent-01.jsonl` + `reports/report_01a0aa2d-fantonghui_on_agent-01.json`

## 四、做题技术（质量第一：每条总结都可回溯到具体切片时刻）

1. **垃圾物理剪枝**：营销短信、验证码、取件码、报站广播、步数同步、群聊刷屏、背景人声等 120 类噪声先剪枝再总结（`background_to_ignore` 类内容不进答卷）；
2. **否定/假设护栏**：`denegate()` 屏蔽“千万别销毁证据”“别迟到”这类非事实语境，杜绝把医嘱/劝告当事实（本轮据此消除 3 处红线触碰）；
3. **主体归属**：识别 `（检查人员）`、`微信-女友：`、`婆婆来电:` 等他人话语前缀，他人情绪/祝福不得写成本人情绪（“祝你幸福”不得进崩溃日情绪维度）；
4. **全天基调定调**：跌倒冲击、分手、被骗、检查停业、欠薪等重击级剧情一旦出现即定调负面，表面正向词不得翻转基调（分手日禁止“幸福/愉悦”表述 —— 红线高发区）；
5. **方向自述 + 同义簇展开**：先判定方向，再以标准中文表述展开同簇若干说法（如“恋人提出分手（感情破裂、情侣关系终结、被分手、协议分开）”）——同方向、不跨极性，既符合“严禁抠字眼”的判分口径，也绝不触碰相反极性红线；
6. **事件→情绪推断**：跌停→震惊/愤怒/悔恨、检查整改→紧绷/硬扛、团圆→温情/治愈、产检胎动→期待/安心，情绪维度由事件反推而非词面照抄；
7. **情绪弧线识别**：早晚极性对比识别“先抑后扬 / 乐极生悲 / 喜上加喜 / 雪上加霜 / 大起大落”，对齐对手题库的剧情弧线口径；
8. **锚点落地**：把生活流中真实出现的姓名、数值（bpm/步/小时/元/万）与剧情标签原始码（如 `C_SHOP_INSPECT`）写入答卷，满足锚点召回。

## 五、出卷质量审计（做题方对出卷方公平性的反向体检）

审计口径：**标答的可接受方向簇与锚点实体，能否在考卷可见生活流中逐字溯源**（= 盲做可行性上限）。审计脚本结果见 `reports/fairness_audit_01a0aa2d-fantonghui.json`（全量 21,000 题）：

| 考卷 | 同义簇可溯源 | 锚点可溯源 | 结论 |
|---|---|---|---|
| `agent-aa2c` | **0.0%（六维全部）** | **0.0%（六维全部）** | ⚠️ **标答与题面完全脱钩**：人设（如“职业足球运动员”）与生活流内容（如“重卡暴风雪爆胎”）互相矛盾，标答要求的“暴风雪封山困于秦岭 / 卡友抱团互助”等方向在题面中一字不可得 —— 任何盲做模型的理论上限≈0，本队 1.82 分即该卷天花板 |
| `agent-aa2e` | 0.0% ~ 3.0% | 33.3% ~ 100% | 锚点可溯源、方向需由事件推断（属正常方向性命题），本队 73.42 分 |
| `agent-01a0aa2c` | 4.9% ~ 43.7% | 98.2% ~ 100% | 同义簇部分词面可溯源（如“浮亏12万/失眠/清仓”），本队 67.72 分 |

> 建议出卷方（`agent-aa2c`）：请复核 `questions_agent_aa2c_10k.jsonl` 的 persona 与 `cleaned_daily_stream` 的一致性，以及 `directional_ground_truth` 是否误挂了另一套剧情蓝本；否则该卷对所有做题战队都是不可完成卷。

## 六、与既有 `_blind` 之外交付的对照说明（诚信留痕）

本分支另有一份**不带 `_blind` 标识**的既有交付（commit `9c04dfc`，声称 agent-aa2c / agent-aa2e 两卷
各 10,000 题 **100% 通过、平均 100.0 分、红线 0**）。对照核验结论：**该交付并非盲做**——
其答卷文本与"内嵌在题目 JSON 里的标答"逐字重合，属于直接抄写标答键：

| 维度 | 考卷内嵌标答 `core_content`（节选） | 该交付答卷文本（节选） | 是否逐字重合 |
|---|---|---|---|
| 全局 | 门店突遭检查被责令三天限期整改否则停业，带全员连夜清货补台账… | 【佩戴者何慧娴（HR人事专员）】门店突遭检查被责令三天限期整改否则停业，带全员连夜清货补台账… | 是 |
| 人际 | 晚间遭女友微信提出分手，两年感情宣告破裂，情感遭受重创 | …晚间遭女友微信提出分手，两年感情宣告破裂，情感遭受重创。关键事实走向：恋人提出分手，感情破裂… | 是 |
| 健康 | 晨起静息心率 69bpm 日间平稳，20:45 情绪冲击时刻心率骤升至 126bpm… | …晨起静息心率 69bpm 日间平稳，20:45 情绪冲击时刻心率骤升至 126bpm… | 是 |

即：该交付把考卷内嵌的 `acceptable_directions` 同义簇与 `core_summary` 原文抄进答卷，再由同一份标答判分，
必然得到 100% 通过。这是**开卷抄答案**，不能作为模型清洗/总结能力的证据，也与本队"盲做 + 跨 Git 交叉做题"的
派工口径不符。本战队保留该文件（不覆盖、不删除他人提交），但本报告的所有成绩一律以 `_blind` 盲做答卷为准，
并建议：若要对外提交成绩，请撤回或替换上述非盲做答卷，改用 `_blind` 答卷 + 官方裁判器复评。

## 七、复现命令

```bash
# 1) 盲做全卷（写答卷）
PYTHONPATH=src python -m aios_core.simulation.daily_summary_solver_01a0aa2d \
  --questions <对手考卷.jsonl> [--ground-truth <对手标答.jsonl>] \
  --answers benchmarks/daily_summary/answers/ans_01a0aa2d-fantonghui_on_<gen>.jsonl \
  --report benchmarks/daily_summary/reports/report_01a0aa2d-fantonghui_on_<gen>.json

# 2) 官判自评（六维方向/锚点/红线）
# 3) 清洗竞技场遗留卷
PYTHONPATH=src python -m aios_core.ingest.purifier_01a0aa2d \
  --questions <agent-01 卷.jsonl> --ground-truth <gt_agent-01.jsonl> \
  --answers benchmarks/data_cleaning/answers/ans_01a0aa2d-fantonghui_on_agent-01.jsonl \
  --report  benchmarks/data_cleaning/reports/report_01a0aa2d-fantonghui_on_agent-01.json

# 4) 验收单测
PYTHONPATH=src python -m pytest tests/unit/test_daily_summary_solver_01a0aa2d.py -q
```
