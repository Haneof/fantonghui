# 战队 `01a0aa2e` —— 数据清洗竞技场提交说明（Master Dispatch #11）

本 README 只描述本次提交：做了什么、产物在哪、怎么复现。机制演进与错题归因见
[`reports/evolution_01a0aa2e.md`](reports/evolution_01a0aa2e.md)。

## 交付物

| 路径 | 内容 |
|---|---|
| `src/aios_core/ingest/purifier_01a0aa2e.py` | 清洗提纯引擎（确定性规则，92 条主题词表，**0 次大模型调用**） |
| `scripts/run_cleaning_arena_01a0aa2e.py` | 交叉做题跑批器 + 机器阅卷 + 错题归因 + 铁律自检 |
| `scripts/probe_bank_ceiling_01a0aa2e.py` | oracle 天花板探针（区分"题库缺陷"与"清洗缺陷"） |
| `tests/ingest/test_purifier_01a0aa2e.py` | 13 条断言单测，覆盖五条铁律 + 反作弊 + 确定性 |
| `benchmarks/data_cleaning/answers/ans_01a0aa2e_on_<gen>.jsonl.gz` | 4 套对手题库 × 10,000 题的答案（40,000 行） |
| `benchmarks/data_cleaning/reports/report_01a0aa2e_on_<gen>.json` | 每套题库的评分、铁律指标、错题归因、最差题清单 |
| `benchmarks/data_cleaning/reports/details_*.jsonl.gz` | 逐题明细（方向命中、实体、剪枝、幻觉，可逐题复核） |
| `benchmarks/data_cleaning/reports/ceiling_probe_01a0aa2e_on_<gen>.json` | 每套题库的理论得分上限探针结果 |
| `reports/evolution_01a0aa2e.md` | v1→v7 迭代阶梯、错题归因、题库/阅卷规则缺陷建议 |

## 最终成绩（每套 10,000 题，共 40,000 题）

| 出题方 | 均分 | 通过率(≥90) | 方向命中 | 实体召回 | 垃圾剪枝 | 维度准确 | oracle 上限 |
|---|---|---|---|---|---|---|---|
| `agent_11` | 58.85 | 34.95 % | 0.5430 | 0.3356 | 0.9849 | 0.5430 | 53.69 |
| `agent_a9f6` | 84.52 | 52.95 % | 0.9425 | 0.7740 | 0.9416 | 0.9425 | 96.09 |
| `fantonghui` | 63.54 | 14.61 % | 0.7233 | 0.5727 | 0.8651 | 0.7233 | 75.53 |
| `01a0a9ff-fantonghui` | 40.30 | 5.45 % | 0.3424 | 0.2635 | 0.7126 | 0.3424 | 67.58 |

`oracle 上限` = 直接借用标答维度/意图、实体只取题面可见文本、垃圾全剪时的得分。
`agent_11` 与 `01a0a9ff` 的上限本身低于 90 分及格线 ⇒ 这两套库存在**题库缺陷**，证据与建议见演进报告 §5。

## 五条铁律的落地方式

1. **质量优先** —— 单题 1.04–1.86 ms，全量 22 s；无短路分支，事实数上限 3 是 A/B 实测后的最优值。
2. **历史不可篡改** —— `history_mutations = 0`；`purify_slice` 对入参只读（`test_purify_does_not_mutate_input_payload`）；全仓无 `UPDATE/DELETE` 落到世界对象。
3. **P0 硬旁路** —— 纯数值判据（g 峰值 / 自由落体时长 / 冲击后静止时长 / 心率 / 室早连发），200 次循环最坏 0.2418 ms，预算 50 ms；`llm_calls_total = 0`。
4. **垃圾物理剪枝** —— 商场喇叭、风噪切片、砍一刀链接、验证码等进 `pruned_junk_ids` 且不出现在保留集；边缘存储节省 38.31 %–92.51 %。
5. **绝不自出自做** —— 跑批器发现 `solver == generator` 立刻 `SystemExit`；协议层 `is_self_solving_violation` 二次兜底判 0 分；本次 `SELF_SOLVING = 0`。

反作弊：`strip_answer_leak` 剥离 `ground_truth_facts`、`ground_truth_junk_ids`、`is_junk`、`junk_tag`、`trap_tag`、`label`、`label_zh`、`note`、`kind`；`test_purifier_is_blind_to_ground_truth` 证明带标答与抹标答两次调用的提交**逐字节相同**。

## 复现

```bash
python3 -m venv .venv && .venv/bin/pip install pydantic pytest   # 本沙箱 Python 3.11.2

# 断言单测（13 条）
.venv/bin/python -m pytest tests/ingest/test_purifier_01a0aa2e.py

# 全量回归：1356 passed in 72.62s，exit 0
.venv/bin/python -m pytest

# 跑一套题库（对手题库需先跨分支取回，见下）
.venv/bin/python scripts/run_cleaning_arena_01a0aa2e.py \
  --questions .cache/inbound/questions_agent_a9f6.jsonl \
  --ground-truth .cache/inbound/gt_agent_a9f6.jsonl \
  --generator-id agent_a9f6 \
  --out-dir benchmarks/data_cleaning
```

对手题库通过跨分支取回落盘，**不入库**（题面 171.8 MiB、含标答 215 MB，已超出产物上限）：

```bash
git fetch origin +refs/heads/arena/01a0a9f6-fantonghui:refs/remotes/origin/arena/01a0a9f6-fantonghui
git show origin/arena/01a0a9f6-fantonghui:benchmarks/data_cleaning/questions/questions_agent_11.jsonl \
  > .cache/inbound/questions_agent_11.jsonl
```

四套题来源：`questions_agent_11` / `questions_agent_a9f6` / `questions_01a0a9ff-fantonghui` @ `arena/01a0a9f6-fantonghui`，`questions_fantonghui` @ `arena/01a0a9fc-fantonghui`。
