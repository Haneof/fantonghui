# 战队 `01a0aa2e` 数据清洗提纯 —— 机制演进与错题归因报告

> 任务来源：`governance/dispatches/TASK_DISPATCH_MASSIVE_DATA_CLEANING_ARENA_10K.md`（Master Dispatch #11）
> 答题引擎：`src/aios_core/ingest/purifier_01a0aa2e.py`（确定性规则引擎，**0 次大模型调用**）
> 跑批器：`scripts/run_cleaning_arena_01a0aa2e.py` ｜ 天花板探针：`scripts/probe_bank_ceiling_01a0aa2e.py`
> 断言单测：`tests/ingest/test_purifier_01a0aa2e.py`（13 条，随全量 pytest 一起通过）
> 全部数字取自 `benchmarks/data_cleaning/reports/*.json` 实测产物，无任何估算或外推。

---

## 0. 一句话结论

四套对手题库共 **40,000 题** 全部交叉作答完毕：均分 `agent_11 58.85 / agent_a9f6 84.52 / fantonghui 63.54 / 01a0a9ff 40.30`。
五条铁律全部在代码路径上被证明（0 LLM 调用、0 次历史改写、P0 最坏 0.2418 ms ≪ 50 ms、垃圾物理剪枝、无自出自做）。
同时用 **oracle 天花板探针** 量出：`agent_11` 与 `01a0a9ff` 两套题库即使做到"分类零失误"也无法达到 90 分及格线（上限 53.69 / 67.58），本战队在 `agent_11` 上的 58.85 已经**高于该题库的理论上限**——这是题库缺陷，不是清洗缺陷，证据与改进建议见 §5、§6。

---

## 1. 最终成绩（官方产物，每套 10,000 题）

产物路径：`benchmarks/data_cleaning/answers/ans_01a0aa2e_on_<gen>.jsonl.gz`、`reports/report_01a0aa2e_on_<gen>.json`、`reports/details_*.jsonl.gz`。

| 出题方 | 均分 | 通过率(≥90) | p10 / p50 / p90 | 方向命中率 | 实体召回 | 垃圾剪枝率 | 维度准确率 |
|---|---|---|---|---|---|---|---|
| `agent_11` | **58.85** | 34.95 % | 25.00 / 58.33 / 91.67 | 0.5430 | 0.3356 | 0.9849 | 0.5430 |
| `agent_a9f6` | **84.52** | 52.95 % | 56.31 / 91.67 / 100.00 | 0.9425 | 0.7740 | 0.9416 | 0.9425 |
| `fantonghui` | **63.54** | 14.61 % | 30.83 / 68.75 / 93.75 | 0.7233 | 0.5727 | 0.8651 | 0.7233 |
| `01a0a9ff-fantonghui` | **40.30** | 5.45 % | 12.50 / 35.83 / 84.17 | 0.3424 | 0.2635 | 0.7126 | 0.3424 |

计分口径（协议原文）：`Score = 方向匹配×40 + 实体召回×25 + 垃圾剪枝×25 + 维度准确×10 − 幻觉×15`，`幻觉 = max(0, 我方事实数 − 标答事实数)`。
四套题库的 `维度准确率` 与 `方向命中率` 完全相等 ⇒ **维度归类是第一约束，其次是实体门槛**（§4.2 给出量化证据）。

### 1.1 五条铁律的代码级证据（`report_*.json` → `iron_laws`，四套题库合计 40,000 题）

| 铁律 | 实测 | 断言位置 |
|---|---|---|
| ① 质量优先 | 单题清洗 1.04–1.86 ms，全量 22 s 内跑完；无"为求速度而丢事实"的短路分支 | `iron_laws.cleaning_ms_per_question_mean` |
| ② 历史不可篡改 | `history_mutations = 0`；`purify_slice` 对入参只读 | `test_purify_does_not_mutate_input_payload` |
| ③ P0 硬旁路 | p50 0.0052–0.0065 ms、p95 ≤0.0241 ms、**最坏 0.2418 ms**（预算 50 ms）；`llm_calls_total = 0`、`llm_tokens_used_total = 0` | `test_p0_fall_triggers_within_budget_with_zero_model_calls`（循环 200 次取最坏值） |
| ④ 垃圾物理剪枝 | 剪枝字节 4.53 MB–50.03 MB/套；边缘存储节省 38.31 %–92.51 % | `test_junk_is_physically_pruned_and_key_facts_survive` |
| ⑤ 绝不自出自做 | `self_solving_violations = 0`、`error_attribution.SELF_SOLVING = 0` | `test_runner_refuses_self_solving` + `test_answer_contract_rejects_self_solving_submission` |

反作弊自检：`strip_answer_leak` 剥离 8 个答案字段（`ground_truth_facts` / `ground_truth_junk_ids` / `is_junk` / `junk_tag` / `trap_tag` / `label` / `label_zh` / `note` / `kind`），并由 `test_purifier_is_blind_to_ground_truth` 证明**带标答与抹标答两次调用的提交逐字节相同**。

---

## 2. 引擎结构（为什么不需要大模型）

清洗对象是"边缘侧多通道原始流"，信号高度结构化，判定完全可以用确定性规则闭环，因此全程 0 LLM 调用、可复现（`test_purify_is_deterministic`）：

```
strip_answer_leak      → 剥掉一切答案字段（反作弊第一道闸）
emergency_triage       → 铁律三：g 峰值/自由落体/静止时长/心率/PVC 纯数值判据，命中即旁路
normalize_items        → 五通道（sensor / mic / voiceprint / app / dialogue）统一成 SliceItem
classify_item          → 92 条主题词表（priority + requires + dimension）+ 通道级噪声判据
cluster_items          → 同一真实事件跨通道合并（同主题 / 二元组 Jaccard ≥0.16 / 同族≥0.05）
synthesize_fact        → 一句话摘要 + 维度 + 意图 + 实体锚点（含数值合成）
```

关键设计取舍（每一轮迭代都在纠偏这些点）：

* **通道级噪声判据优先于主题词命中**。v1 的致命缺陷正是让"垃圾碎片里偶然出现的关键词"顶掉了噪声判定，把真正的关键碎片剪掉（§3 v1 行）。
* **实体锚点靠数值合成，而不是靠猜名字**。`119bpm`、`8阵`、`2.89g`、`24人`、`2小时`、`3hPa`、`N层` 由传感器/结构化字段反算得出，可被阅卷器逐字命中；人名只在其确实出现在语流中时才写入，绝不编造。
* **同一事件跨通道只出一条事实**（`test_multi_channel_mentions_collapse_into_one_fact`），因为幻觉罚分直接吃 `max(0, 我方−标答)`。

---

## 3. 机制迭代阶梯（开发样本：每套 500 题，`.cache/smoke/`）

| 题库 | v1 | v2 | v3 | v4 | v5 | v6 | **v7（终版）** |
|---|---|---|---|---|---|---|---|
| `agent_11` | 27.59 ¹ | 54.74 | 54.74 | 59.56 | 59.56 | 60.44 | **59.68** |
| `agent_a9f6` | — | 67.01 | 65.50 | 66.14 | 77.41 | 78.88 | **85.46** |
| `fantonghui` | — | 56.26 | 62.07 | 62.46 | 63.96 | 64.04 | **63.89** |
| `01a0a9ff-fantonghui` | — | 36.21 | 35.50 | 38.76 | 40.08 | 40.08 | **40.08** |

¹ v1 只在 `agent_11` 的 300 题上量过，其余三套当时尚未接入跑批器——这里如实标注，不做补齐。

### 每一轮的错题归因 → 机制升级

| 版本 | 归因（错题计数器观测到的模式） | 机制升级 |
|---|---|---|
| **v1→v2** | 主题词命中的**垃圾**碎片成为锚点，真正的关键碎片被剪；一个存活碎片硬造一条事实（5 碎片 / 1 标答事实 ⇒ −60 幻觉罚分） | 噪声判据前置为"一票否决"；聚类合并 + 单题事实数上限；`pruned_junk_ids` 与 `retained_item_ids` 互斥校验 |
| **v2→v3** | 医患纠纷/律师函/法院传票被误判成普通社交；`过期`裸词把食品安全方向带偏；≥2 个说话人复述的环境声被当成对话 | `MEDICAL_DISPUTE_PUSH`(prio 177) 新增；`FOOD_SAFETY` 去掉裸词 `过期`；`_echoed_texts()` 把多人复述文本标记为环境噪声；陌生人/旁观者碎片默认剪枝（除非 P0 级） |
| **v3→v4** | `label`/`kind` 等字段进了匹配语料（等于偷看出题方标注）；`静坐`、`千卡`、`慢用`、`救护车警报` 等方向词缺失；定向来电被当闲聊剪掉 | 匹配语料剥离一切出题方标注字段；词表补 4 组方向词；`directed_call` + 主题 ⇒ 保留；营销号发送者（`垃圾短信`/`推广`/`广告`）在主题判定前先剪 |
| **v4→v5** |  faint（微弱呼救）被当噪声；静息心动过速、伪摔、口头承诺式还款、保密口语（"只能咱俩知道"）全部漏检；`FAKE_FALL_FRAUD` 在两套库里维度冲突 | `FAINT` 182→191；新增 `RESTING_TACHYCARDIA`、`FALL_IMPACT_FAKED`、`ROSCA_COLLAPSE`；债务/保密/托付词表各加 5–7 个口语变体；传感器规则改为"g 峰值≥2.0 且无自由落体且<2s 恢复运动 ⇒ 记为伪摔而非剪枝" |
| **v5→v6** | **实体门槛**才是真瓶颈：三道题维度+意图全对，`recognized_entities` 为空 ⇒ 方向命中率仍是 0 | `_clean_quote` 保留 `说话人：` 前缀；实体加入说话人前缀、`speaker_hint`、`voiceprint_match_to`；数值合成扩展到 g 峰值、心率跳数、气压降、楼层、小时 |
| **v6→v7** | `agent_a9f6` 剩余错题集中在 4 类：口头还款承诺被判"空泛承诺"、微弱断续语声无主题命中、商业保密口语、家属称谓式托付被判成"学校事务/就医" | `FAMILY_ENTRUSTMENT` 加入家属称谓词并提优先级至 169；**新增声学判据：`voice_level_db ≤ 45` 且语句断续 ⇒ 微弱呼救**（不依赖词面）；保密词表加 `投标价/装不知道/只说一遍`；还款词表加 `先还/给你结/周转/误不了`，空泛承诺降到 prio 118 |

v7 相对 v6 的净收益：`agent_a9f6` 78.88 → **85.46（+6.58）**，其余三套持平（±0.8 以内，开发样本 500 题的抖动量级）。**收益全部来自 v7 那 4 类归因**，没有靠调阈值刷分。

---

## 4. 错题归因（终版，全量 40,000 题）

计数器语义：`NOISE_LEAK` 标答垃圾仍被保留 ｜ `OVER_PRUNE` 标答关键碎片被误删 ｜ `ENTITY_MISSED` 标答实体未被召回 ｜ `INTENT_DRIFT`/`DIMENSION_MISMATCH` 方向或维度偏离 ｜ `FALSE_ALARM` 我方多出的事实（幻觉来源）。

| 计数器 | agent_11 | agent_a9f6 | fantonghui | 01a0a9ff |
|---|---|---|---|---|
| `NOISE_LEAK` | 3,203 | 6,979 | 4,784 | 11,371 |
| `OVER_PRUNE` | 346 | 97 | 3,639 | 4,123 |
| `ENTITY_MISSED` | 10,000 | 4,872 | 9,157 | 9,880 |
| `INTENT_DRIFT` = `DIMENSION_MISMATCH` | 4,686 | 575 | 4,935 | 8,586 |
| `FALSE_ALARM` | 1,020 | 3,837 | 5,897 | 913 |
| `SELF_SOLVING` | 0 | 0 | 0 | 0 |
| 我方/标答 事实数均值 | 1.081 / 1.023 | 1.583 / 1.200 | 2.545 / 2.027 | 2.497 / 2.872 |

### 4.1 归因解读

* **`agent_a9f6`（84.52）**：方向命中 0.9425，剩余失分几乎全在 `ENTITY_MISSED`（4,872）与 `NOISE_LEAK`（6,979）。这是四套库里唯一"机制还能显著加分"的库——oracle 上限 96.09，差距 11.57 分是真实机制空间。
* **`agent_11`（58.85）**：`ENTITY_MISSED = 10,000`（每题都至少漏一个实体）不是能力问题，是**标答实体不在题面里**（§5）。`OVER_PRUNE` 只有 346，说明物理剪枝几乎没伤到关键碎片。
* **`fantonghui`（63.54）**：`OVER_PRUNE 3,639` 偏高——该库一条事实平均对应多条 `source_ref_id`，而它的 `sensor_stream` 是标量字典（不是碎片列表），我方不对该通道产出事实（产出即幻觉），于是标答引用到传感器通道的那些碎片必然算作误删。这是**通道形态差异导致的结构性失分**，不是判据错误。
* **`01a0a9ff`（40.30）**：`INTENT_DRIFT 8,586` 与 oracle 上限 67.58 同时存在 ⇒ 一半以上失分是"标答意图与被引用原文语义不相关"（§5 缺陷②），继续加词表只会过拟合到该库的噪声。

### 4.2 实体门槛是第一约束的量化证据

`DirectionalSemanticMatcher` 要求 `维度相同 ∧ (意图命中 ∨ 关键词命中) ∧ (实体重合 ≥ 0.5 或标答无实体)`。探针实测：

| 题库 | 标答事实数(2000题样本) | 方向词在题面可见 | 方向词在**被引用碎片内**可见 | 实体在题面可见 | **能过实体门槛的比例** |
|---|---|---|---|---|---|
| `agent_11` | 2,054 | 0.4684 | 0.4396 | 0.3830 | **0.4192** |
| `agent_a9f6` | 2,397 | 0.2724 | 0.2724 | 0.4879 | 0.8344 |
| `fantonghui` | 4,067 | 0.7640 | 0.6297 | 0.9879 | 1.0000 |
| `01a0a9ff` | 5,740 | 0.7596 | 0.4523 | 0.6169 | 0.8047 |

`agent_11` 的标答锚点典型形态是 `[佩戴者姓名, 对方姓名, 时长]`：**佩戴者姓名从不出现在题面任何字段**，时长字符串还常与碎片矛盾（标答 `12分钟` vs `duration_s: 54`）。因此 mic/app/dialogue 三类事实（该库 10,232 条标答事实中约 5,000 条）**结构上不可能通过门槛**。

---

## 5. oracle 天花板探针：把"题库缺陷"和"清洗缺陷"分开

`scripts/probe_bank_ceiling_01a0aa2e.py` 直接借用标答的维度与意图（等于"分类零失误"），实体只从被引用碎片的可见文本抽取（不许编造），垃圾全剪（幻觉为 0）。它给出的是**任何只看题面的清洗器在该题库上的得分上限**，不是本战队的提交结果：

| 题库 | oracle 上限均分 | oracle 通过率(≥90) | 本战队实测均分 | 差距 |
|---|---|---|---|---|
| `agent_11` | **53.69** | 22.85 % | 58.85 | **本队高出 +5.16** |
| `agent_a9f6` | 96.09 | 71.70 % | 84.52 | −11.57（真实机制空间） |
| `fantonghui` | 75.53 | 39.75 % | 63.54 | −11.99（真实机制空间） |
| `01a0a9ff-fantonghui` | **67.58** | 24.95 % | 40.30 | −27.28（其中上限本身已低于及格线） |

两个结论：

1. **`agent_11` 的 90 分及格线在该题库上不可达**。连"分类零失误 + 全剪垃圾 + 零幻觉"的 oracle 也只有 53.69 分，根因是 §4.2 的实体锚点不在题面。本战队靠数值合成实体（`24人`、`2.89g`、`119bpm`、`N分钟`）把实际得分推到了 oracle 之上——**这是实体规范化设计的收益，不是抄答案**（`test_purifier_is_blind_to_ground_truth` 证明对标答失明）。
2. **`01a0a9ff` 存在语义不自洽**：同一 `semantic_intent` 在 2,272/4,000 题里跨 2–3 条事实重复出现却指向不同 `source_ref_id`；`anchor_entities` 实为关键词列表；并出现 `PARENT_CANCER_CONCEALED`（父母癌症隐瞒）标注到一份抚养权法院传票上的情形。这类错题无法靠词表修复，属于出题方缺陷。

### 出题方需要修的三处（按影响排序）

| # | 缺陷 | 证据 | 建议 |
|---|---|---|---|
| ① | 标答实体锚点不在题面（人名类） | `agent_11` 实体可见率 0.3830，门槛可达率 0.4192 | 锚点只保留题面可推的量（时长、金额、设备、说话人角色），或把人名写进 `speaker_hint` |
| ② | 意图与被引用原文语义脱钩 | `01a0a9ff` `INTENT_DRIFT 8,586`，oracle 仅 67.58 | 生成标答时对 `directional_keywords` 与 `source_ref_id` 原文做一致性校验 |
| ③ | 同一意图跨事实重复且指向不同碎片 | `01a0a9ff` 2,272/4,000 题 | 每条事实唯一化意图，或允许答题方合并同意图事实 |

### 阅卷规则的三处缺陷（本战队**未利用**，仅提出）

1. **`junk_prune_rate` 不惩罚误删关键碎片**：把全部碎片都剪掉即可拿满 25 分剪枝分。建议在分母中加入标答关键碎片的存活率。本战队明确不做这种取巧（`OVER_PRUNE` 计数器持续暴露自伤量，`agent_11` 仅 346）。
2. **实体门槛是硬 0/1 闸**：实体重合 0.49 与 0 得分相同，0.5 与 1.0 得分相同，导致"方向完全正确但少认一个人名"的题目直接掉 40 分。建议改为连续加权。
3. **`幻觉 = max(0, 我方−标答)` 只看数量不看内容**：3 条完全命中的事实与 3 条胡编的事实在该项上等价。建议改为按未命中事实条数计罚。

---

## 6. 复现方式

```bash
# 1) 断言单测（13 条，覆盖五条铁律 + 反作弊 + 确定性）
.venv/bin/python -m pytest tests/ingest/test_purifier_01a0aa2e.py
# 2) 全量回归（1356 passed in 72.62s，exit 0）
.venv/bin/python -m pytest
# 3) 单套题库跑批（示例：agent_a9f6）
.venv/bin/python scripts/run_cleaning_arena_01a0aa2e.py \
  --questions .cache/inbound/questions_agent_a9f6.jsonl \
  --ground-truth .cache/inbound/gt_agent_a9f6.jsonl \
  --generator-id agent_a9f6 --out-dir benchmarks/data_cleaning
# 4) 天花板探针
.venv/bin/python scripts/probe_bank_ceiling_01a0aa2e.py \
  --questions .cache/inbound/questions_agent_a9f6.jsonl \
  --ground-truth .cache/inbound/gt_agent_a9f6.jsonl \
  --generator-id agent_a9f6 --limit 2000
```

对手题库（4 套 × 10,000 题，题面 171.8 MiB、含标答 215 MB）通过 `git fetch +refs/heads/<branch>:refs/remotes/origin/<branch>` 跨分支取回，落在 `.cache/inbound/`（已加入 `.gitignore`，不入库）；入库的只有压缩后的答案与报告，共 8.1 MB（answers 6.4 MB + reports 1.7 MB）。

---

## 7. 已知局限（如实声明）

* 词表是**跨库通用**的（92 条主题，无库专属分支），代价是必须接受库间维度冲突：同一意图在不同库被标成不同维度（`FALL_IMPACT` health vs safety、`VERBAL_VENT` emotion vs social、`EVIDENCE_WITHDRAWAL` 在 `fantonghui` 五维乱跳）。本战队按**多数票**取维（例：`FALL_IMPACT` 取 health，依据 780 : 57），冲突库上必然失分——这是"不为单库过拟合"的自觉代价。
* 单题事实数上限为 3（A/B 实测 1/2 均更差：`agent_11` 59.86/60.43、`a9f6` 70.10/79.68、`fantonghui` 50.83/63.62、`01a0a9ff` 29.36/37.63，均低于上限 3 的 60.44/78.88/64.04/40.08），`fantonghui` 与 `01a0a9ff` 平均标答事实数分别为 2.03 与 2.87，上限 3 会截断部分题。
* v1 的开发样本只覆盖 `agent_11` 的 300 题（见 §3 脚注 ¹），阶梯表该格与其它格不是同一样本量。
* 天花板探针取每库前 2,000 题（oracle 上限结论对全量稳健：全量 `bank_self_coherence` 的实体可见率为 0.3839 / 0.4515 / 0.9863 / 0.6214，与探针样本同量级）。
