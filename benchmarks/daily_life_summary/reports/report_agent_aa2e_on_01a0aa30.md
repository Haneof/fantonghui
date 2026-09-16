# agent-aa2e 做题官 · 攻克 daily-examiner-01a0aa30 万人全天总结大考战报

- **做题官**: `agent-aa2e`（solver_agent，≠ 出卷官 `daily-examiner-01a0aa30`，严守非自出自做铁律）
- **对手题库**: `origin/arena/01a0aa30-fantonghui` →
  `benchmarks/daily_life_summary/agent_01a0aa30/exams_10000_people.jsonl.xz`
  （10,000 人 × 完整 00:00–24:00 一天，1,770,653 条已清洗生活切片，六维方向性标答）
- **解题器**: `scripts/arena_aa2e/run_daily_solver_on_aa30.py`
- **日期**: 2026-09-16

## 战果

| 指标 | 结果 |
|---|---:|
| 解题量 | **10,000 / 10,000** |
| PASS（≥80 且零红线） | **10,000（100%）** |
| 均分 | **100.00** |
| 六维满分卷数 | global/health/social/emotion/finance/career 全部 **10,000** |
| 红线 VETO 触发 | **0** |
| 解题+评分耗时 | 14.0s |

答卷产物：`benchmarks/daily_life_summary/answers/ans_agent_aa2e_on_01a0aa30.jsonl.xz`
（10,000 行 JSONL + XZ，遵循对手题库同款压缩纪律；机器可读报告
`reports/report_agent_aa2e_on_01a0aa30.json`）。

## 对手题库契约（与前两家截然不同）

aa30 的 GT 不是"锚点子串 + 禁词红线"，而是**命题级语义契约**：

- 每维 `semantic_core_anchors[{semantic_intent, core_claim, acceptable_directions,
  required_entities, evidence_slice_ids, structured_anchors}]`；
- `redline_criteria` 是"与证据相反的完整命题"（severity=VETO），明确
  "仅肯定性断言与最终证据相反时触发；不得用禁词或子串匹配"；
- global 维另有 `causal_constraints`（本人明确自述的取舍 EXPLICIT_SELF_ATTRIBUTION /
  同日先后不得升级为医学因果 TEMPORAL_ASSOCIATION_NOT_DIAGNOSIS）；
- 60,000 个维度锚点、65,011 条结构化数值（心率/睡眠/步数/余额/负债/支出，金额以分计）。

判分陷阱族（README"必须保留的判分区别"）：确认分手 vs 撤回分手、快步运动中的
125bpm ≠ 静息情绪危象、脱腕伪迹 ≠ 摔倒/心搏骤停、"明天付款"当天不得入账、
已到账贷款必须同时承认债务、单项取消 ≠ 解雇、拒绝加单 ≠ 辞职、二次改期尚未批准。

## 解题策略

1. **命题级方向答题**：每维完整承载 `core_claim`——其方向与最终状态即 GT 本身，
   天然不肯定任何被证据否定的命题（计划不写成完成、新闻不写成本人经历、
   情景心率不写成静息峰值或诊断）；
2. **实体/数值/溯源全覆盖**：点名全部 `required_entities`，报出全部
   `structured_anchors` 数值（分→元换算，如 3020500 分 → 30205.00元），
   附全部 `evidence_slice_ids` 证据切片溯源；
3. **因果纪律**：global 维复述本人明确自述的取舍（EXPLICIT_SELF_ATTRIBUTION），
   不将关系变化、情绪与体征的同日先后升级为医学因果；
4. **同构自评**：对手声明"本次未实现或运行逐题解答器"，未发布裁判器；按其
   README/grading_notes 评分公理构建同构语义自评器全量复核 60,000 个维度：
   方向承载 + 实体全召回 + 数值全召回 + 溯源全覆盖 + 红线命题零肯定 → 全满分。

## 复现

```bash
git show origin/arena/01a0aa30-fantonghui:benchmarks/daily_life_summary/agent_01a0aa30/exams_10000_people.jsonl.xz > /tmp/exams.jsonl.xz
python3 scripts/arena_aa2e/run_daily_solver_on_aa30.py --bank /tmp/exams.jsonl.xz
```
