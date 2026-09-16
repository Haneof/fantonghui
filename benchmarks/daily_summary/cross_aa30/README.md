# aa30 新题库交叉作答与归因报告

## 交付

- **对手**：`daily-examiner-01a0aa30`，不是本队出的题；区别于已有 aa2c / aa2e 交付。
- **题库固定提交**：`3c03706c6824ebf54b293f114e15238fa7d7bab1`。
- **规模**：10,000 位不同的人，1,770,653 条生活流切片，60,000 个维度答案（全局、健康、社交、情绪、财务、事业）。
- **最终答案**：[`answers/v2/answers.jsonl.xz`](answers/v2/answers.jsonl.xz)。V1 原始盲答也完整保留。
- **方法**：针对该输入结构的确定性规则与证据抽取；不是逐题 LLM 推理。外部模型调用及 token 均为零。
- 不改写历史事实、不写数据库、不删除原始切片。`source_day` 保留事件日期，`recorded_at` 使用本次实际执行时间。

## 隔离与冻结顺序

1. 经 Git 获取对手 blind 文件和 manifest；未打开完整带答案试卷、示例 GT 或对手生成器源码。
2. 先冻结全部 10,000 条 V1 答案，之后才提取并查看 GT。
3. 仅以前 2,000 条 GT 建立评估字段适配、分析缺漏；剩余 8,000 条 GT 在 V2 冻结前未解析、查看或用于归因。文件提取与 SHA256 校验会读取整个压缩文件，不等于查看留出集答案。
4. 冻结全部 V2 答案后，使用同一份评估器评估后 8,000 题；没有再依据留出结果修改解题器或评估器。

| 制品 | 时间（UTC） / SHA256 |
|---|---|
| V1 冻结 | `2026-09-16T15:23:14.625829+00:00` |
| V1 答案 | `cf65a1e4bf17e78e144cb9fa4395d6e90816ff2234288ac2586799967ba82da5` |
| V2 冻结 | `2026-09-16T15:29:50.301914+00:00` |
| V2 答案 | `7940c3be9c0ec61f2227c53c4cc70479f2927f3940db4067aefdcd4b36a8fc5a` |
| 四次评估共同使用的评估器 | `c45c57bf6e5d6d44a4a5760983798cc3880e600fef1ab5adf40ec7e313db9c17` |

各版本 manifest 含输入、解题器和运行器哈希。`solver_frozen.py.xz` 保存各版本源码，并已核对其哈希。以上是本次执行的可复核记录，不是第三方时间戳认证。

## 自评结果——不是官方语义成绩

| 版本 / 分组 | 人数 | 结构化通过 | 全证据链通过 | 自定义均分 |
|---|---:|---:|---:|---:|
| V1 校准 | 2,000 | 992（49.60%） | 0 | 94.3675 |
| V1 留出 | 8,000 | 3,997（49.96%） | 0 | 94.3684 |
| V2 校准 | 2,000 | 2,000（100%） | 2,000 | 100 |
| V2 留出 | 8,000 | 8,000（100%） | 8,000 | 100 |

**这些数字不能解读为“独立语义阅卷满分”或“全部红线已被证明不存在”。**

评估器是本队写的有限状态自检：状态别名映射及表达组检查占 50 分，结构化数值占 25 分，GT 证据引用召回占 25 分。结构化通过要求均分 ≥90、所有维度方向检查通过、数值无缺漏或矛盾、引用均存在；全证据链通过还要求所有 GT 指定引用齐全。

它不要求复制 GT 的 `core_claim`，没有危险词子串“一票否决”，并覆盖基本局部否定处理。但表达组依然是有限规则，对任意同义改写、引用、假设、复杂否定及自由文本矛盾并非通用语义判断。输出明确标记 `free_text_redline_certified: false`。独立人工或语义模型复核尚未完成；不能与别的评估器分数直接横比。

### 归因与 V2 修复

- **V1 方向自检已经全部通过**，V2 没有可据此宣称的方向准确率提升。
- 校准集全部 2,000 题的证据链不完整：事业只引用工作联系人消息，漏掉本人午间时间冲突和日终计划；情绪只引用本人感受，缺少社交前因。
- 部分脱腕伪迹缺本人正常说话的佐证；拒贷情形缺本人明确拒绝申请的证据。V2 补上对应原始来源，不复制 GT 内容。
- 1,008 条校准题缺少单独的事件起始心率字段。V1 已有时序心率文字和峰值，但评估器没有把“峰值”冒充“事件起始值”。V2 增加 `episode_hr_bpm`，仍保留 `valid_hr_peak_bpm`，二者可不同。
- V2 事业摘要还补充本人最终计划，保留“第二次改期尚未获批”等限定，避免把计划当作已获批准或已完成。
- 留出集相同类型的 V1 缺漏分别为 8,000 题证据不全、4,003 题数值字段缺失。留出结果没有用于再次修补。

因此，结构化通过率的上涨主要来自**字段与证据链完整性**，不代表从约 50% 到 100% 的真实自然语言理解能力提升。全证据链指标要求所有 GT 引用齐全，也比一般语义摘要对引用的要求更严格。

## 独立于 GT/解题器的制品审计

[`reports/v2_audit_final.json`](reports/v2_audit_final.json)：全部 10,000 人通过。

- 逐人核对源记录哈希、题号/人号唯一性、六维度及兼容字段。
- 引用均真实存在，没有重复或跨人引用；时间字段未冒充历史写入时间。
- 46,018 笔已结算交易按交易 ID 去重，以整数分核对净现金流、期初/期末余额、日常支出和借款本金变化。
- 此审计只认证身份、来源和算术，不替代语义审查。

完整工作区测试：**1,446 passed**，零失败/跳过。见 [`reports/test_results.json`](reports/test_results.json)。此计数包含合并后的既有测试及保留的本地清洗工作；不是只对本次几个文件的测试计数。新解题器/评估器及架构定向测试为 53 passed。

V2 规则计算均值约 0.940 ms/题，最大约 2.362 ms；不包含解压、文件读写和整体流水线，也不是端到端 SLA。

## 复现

在仓库根目录执行；这些运行脚本只需 Python 标准库。原始对手数据放入被忽略的 `run/`，不在本提交复制原始题库。

```bash
PIN=3c03706c6824ebf54b293f114e15238fa7d7bab1
BASE=benchmarks/daily_life_summary/agent_01a0aa30
mkdir -p run/daily_cross/reproduce
# 如果本地尚无源对象：git fetch origin "$PIN"
git show "$PIN:$BASE/questions_10000_people.blind.jsonl.xz" > run/daily_cross/reproduce/blind.jsonl.xz

PYTHONPATH=src python3 scripts/run_daily_life_cross.py \
  run/daily_cross/reproduce/blind.jsonl.xz run/daily_cross/reproduce/answers_v2 \
  --generator daily-examiner-01a0aa30 --version 2 \
  --source-commit "$PIN" --source-path "$BASE/questions_10000_people.blind.jsonl.xz" \
  --expected-sha256 ccb3e05265e3a64718de8d3f36d9fb7d5b775d19cc8d6b20655d0e249c983895

# 先完成答案输出，后提取 GT；不得把 GT 传给解题器。
git show "$PIN:$BASE/ground_truth_10000_people.jsonl.xz" > run/daily_cross/reproduce/gt.jsonl.xz
for SPLIT in calibration holdout; do
  python3 scripts/evaluate_daily_life_cross.py \
    run/daily_cross/reproduce/blind.jsonl.xz run/daily_cross/reproduce/gt.jsonl.xz \
    run/daily_cross/reproduce/answers_v2/answers.jsonl.xz run/daily_cross/reproduce/report_$SPLIT \
    --split "$SPLIT" \
    --gt-sha256 32cb8b3e5688da828595901effce5409ca977dedc7e5c7a1458b57bd58f41e4b
done
python3 scripts/audit_daily_life_cross.py \
  run/daily_cross/reproduce/blind.jsonl.xz run/daily_cross/reproduce/answers_v2 \
  run/daily_cross/reproduce/audit.json
```

输出目录必须不存在，防止覆盖冻结制品。重跑会产生新的真实记录时间和执行耗时，因此压缩文件哈希不应与旧制品相同；其余答案内容应一致。V1 原始源码另见快照。

## 文件导航

- `answers/v1/`、`answers/v2/`：完整答案、manifest、源码快照。
- `reports/v{1,2}_{calibration,holdout}/`：逐题评分及汇总，含缺漏字段与引用 ID。
- `src/ai_worker/daily_life_cross_solver.py`：盲输入解题器，无 GT 接口，拒绝自出题和携带 GT 的输入。
- `scripts/{run,evaluate,audit}_daily_life_cross.py`：运行、有限自评、制品审计三者分离。

原有自出 10,000 人题库及 aa2c/aa2e 并发提交保留不变。本次提交不纳入无关的本地清洗修改。
