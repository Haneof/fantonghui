# QA 报告 · 跨 Git 交叉做题 `01a0aa2c` → 对手卷 `01a0aa2e`

> 范围：本次「换个题库做」的交付自检（对手卷 `arena/01a0aa2e-fantonghui`，10,000 题）
> 方法：可复现命令 + 逐项证据 + 诚实边界（哪些验过、哪些没验）
> 日期：2026-09-16

---

## 一、验收清单

| 项 | 要求 | 实测 | 结论 |
| --- | --- | --- | --- |
| 答卷完整性 | 10,000 条，字段合规 | 10,000 行，字段 `question_id/solver_agent/generator_agent/extracted_facts/pruned_junk_ids/execution_time_ms/llm_tokens_used` | ✅ |
| 身份纪律 | `solver_agent` = `01a0aa2c-fantonghui`，且 ≠ 出题方 | 全量唯一取值 `01a0aa2c-fantonghui`；出题方 `fantonghui`（分支归属 `01a0aa2e`） | ✅ |
| 自出自做 | 必须为零 | 分支归属判据 `01a0aa2e ≠ 01a0aa2c`；首跑触发的同名字面陷阱以**更严的分支级判据**解决，未削弱铁律 | ✅ |
| 标答防火墙 | 做题时不得读到 `ground_truth_*` | 答卷中 `ground_truth/is_junk` 字段出现次数 **0**；`purify()` 入口 `assert_ground_truth_firewall` | ✅ |
| 泄题面纪律 | 不读对手卷内联 `is_junk` | 适配器无任何读取点（`use_inband_labels` 仅接口兼容） | ✅ |
| 幻觉为零 | 幻觉数 = 0 | **未达**：952 条超提事实（多切片伪互证，见进化报告 §5.1） | ❌ 已知缺口 |
| 零 LLM / 零 SQL | `llm_tokens_used = 0`，无写库路径 | 全量 0；`purify()` 为纯函数，无任何 SQL 调用点 | ✅ |
| P0 硬旁路 | ≤50 ms，LLM 调用 0 | 10k 实测最大 0.0397 ms | ✅ |
| 吞吐 | 端侧可跑 | 151.8 题/秒（单进程） | ✅ |
| 质量红线（自加） | 标答事实来源切片 0 误剪 | **0 / 20,267** | ✅ |

## 二、指标（全量 10,000 题）

```
均分 87.722 ｜ 达标率 0.6440 (6,440) ｜ 方向 0.8928 ｜ 实体 0.8156 ｜ 剪枝 0.9646 ｜ 维度 0.8928
幻觉 952 ｜ 提取事实 19,166 ｜ 剪枝切片 36,791 ｜ 标答来源误剪 0 ｜ 墙钟 65.9 s
```

留出诚实性：词表拟合集（前 5,000 题）与评估切片（6000:7000 / 8000:9000）不重叠，
留出两片 `mean 86.32 / 85.67`、`pass 0.595 / 0.581`、`junk 0.9712 / 0.9439`，与全量同量级 ⇒ 增益不是"背评估切片"。

## 三、文件指纹（本次交付）

| 文件 | sha256（全量） |
| --- | --- |
| `answers/ans_01a0aa2c-fantonghui_on_aa2e.jsonl` | `10d5f396cfeb1b314ca508c6c1d0c4ee9750c29b7e3f0bbdc100d6eec2864dc0` |
| `reports/report_01a0aa2c-fantonghui_on_aa2e.json` | `be4ed89c8be4154f926f6f6fd0c948df4d78b817fcddc92ffa1ee3af5c318a0a` |
| `reports/failures_01a0aa2c-fantonghui_on_aa2e.jsonl` | `b94644472622ec8dc78668bd99a1d7c440dcc2e21d74c5044bb0bde4080a5027` |
| `question_bank_aa2e/lexicon.json` | `85d119e2403c228419656dce18c1e766e0afc60e1683221fe4888281bb726c72` |

```bash
sha256sum benchmarks/data_cleaning/answers/ans_01a0aa2c-fantonghui_on_aa2e.jsonl \
          benchmarks/data_cleaning/reports/report_01a0aa2c-fantonghui_on_aa2e.json \
          benchmarks/data_cleaning/question_bank_aa2e/lexicon.json
```

## 四、测试

```bash
/home/user/.venv/bin/python -m pytest tests/ingest/test_purifier_01a0aa2c_iron_laws.py \
                                  tests/ingest/test_purifier_01a0aa2c_aa2e_cross_team.py -q
```

- `test_purifier_01a0aa2c_iron_laws.py`：本队 v6 引擎 15 项铁律回归（历史交付，未改动）
- `test_purifier_01a0aa2c_aa2e_cross_team.py`：本次新增 12 项（跨战队判据 ×4 / 标答防火墙 / 内联标签免疫 /
  铁律四剪枝 / 标答来源零误剪 / 纯噪声不产事实 / 事实预算与判分通路 / P0 旁路 / 词表指纹）

## 五、诚实边界（不粉饰）

1. **幻觉未清零**（952）：多切片互证在对手卷的"邻桌同主题噪声"上会产生伪互证，方案与下一步见进化报告 §5.2。
2. **门禁两项未达**：方向 0.8928（线 0.90）、实体 0.8156（线 0.95），主因是少提一条（1,877 题）与整题空手（113 题）。
3. **`keeper_mis_prune_rate = 0.0334`**：我方垃圾判定比对手卷自报标签更严（对手卷大量"邻桌/路人/自语"切片未标为垃圾），
   被剪的 2,141 个切片中**没有一个是标答事实来源**；此指标按卷方标签统计，故非零。
4. **未使用的捷径**：对手卷每个切片内联了生成器 `is_junk` 标签、且标答直接内嵌题面——两条都可"作弊拿分"，本队全部主动放弃。
5. **本队自家题库仍未自解**（铁律五），本次只做对手卷。
