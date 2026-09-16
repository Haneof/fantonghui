# AIOS 3.0 全天生活流与多维总结题库（出题方：战队 `01a0aa2e`）

**10,000 个人的一整天**（07:00 ~ 23:30），每道题 = 一个人的 24 小时高熵生活流 + 六维方向性语义标答。

| 文件 | 内容 | 大小 |
|---|---|---|
| `generators/daily_life_generator_01a0aa2e.py` | 出卷引擎（确定性、seeded、含出题自查） | ~110 KB |
| `questions/questions_01a0aa2e.jsonl.gz` | 10,000 道**题面**（不含标答，供做题方） | 14.4 MB |
| `ground_truth/gt_01a0aa2e.jsonl.gz` | 10,000 份**标答对象**（含 `directional_ground_truth`） | 27.8 MB |
| `reports/coherence_01a0aa2e.json` | 出题方自查指标（全量 10,000 题） | — |
| `reports/generation_report_01a0aa2e.md` | 出卷统计、设计说明、自查结论 | — |

## 一、数据契约

**题面**（`questions_*.jsonl.gz`，每行一个 JSON）：

```json
{
  "question_id": "Q_daily_01a0aa2e_00001",
  "persona": { "name", "age", "gender", "city", "occupation", "company", "boss",
               "colleague", "best_friend", "father", "mother",
               "relationship_status", "partner_name", "has_child", "child_name",
               "monthly_income", "commute_mode", "living_with", "pet",
               "health_baseline", "sleep_baseline_hours", "resting_hr_baseline", "personality" },
  "cleaned_daily_stream": {
    "date": "2026-07-03", "timezone": "Asia/Shanghai", "coverage_window": "07:00-23:30",
    "mic_slices":        [ { "snippet_id": "M001", "ts": "11:23", "speaker", "location", "channel", "text", "ambient_noise_db" } ],
    "app_notifications": [ { "msg_id": "A001", "ts": "10:02", "app", "sender", "session", "direction", "content" } ],
    "sensor_summary":    { "sensor_id": "S0", "sleep_hours", "sleep_quality", "morning_resting_hr_bpm",
                           "steps_total", "steps_reading", "calories_kcal", "hrv_rmsd_ms", "blood_pressure",
                           "hr_events": [ { "event_id": "SH01", "ts", "reading", "peak_bpm", "window_mean_bpm", "duration_s" } ],
                           "imu_events": [ { "event_id": "SI01", "ts", "reading", "peak_g", "axis" } ],
                           "stress_index_by_period": [ { "period": "上午", "index": 55 } ],
                           "health_baseline" }
  }
}
```

**标答**（`gt_*.jsonl.gz`）在题面基础上增加 `directional_ground_truth` 与 `generator_meta`：

```json
{
  "question_id": "...", "persona": { }, "cleaned_daily_stream": { },
  "directional_ground_truth": {
    "global_daily_summary": { "semantic_core", "acceptable_synonyms", "red_line_rejections",
                              "directional_keywords", "key_entities", "evidence_ref_ids",
                              "secondary_points": [ … ] },
    "dimensions": { "dim:health": {…}, "dim:social": {…}, "dim:emotion": {…},
                    "dim:finance": {…}, "dim:career": {…} }
  },
  "generator_meta": { "spine_id", "spine_title", "subplot_ids", "event_count", "seed" }
}
```

字段语义：

* `semantic_core` —— 该维度的**方向性核心要点**（一句话），阅卷时判"方向是否一致"，不做字句匹配。
* `acceptable_synonyms` —— **可接受的方向同义词**（每个标答 ≥3 个）。命中任一即算方向正确。
  例：事实是"恋人提出分手"，答"激烈吵架""感情破裂""协议分开"均算对。
* `red_line_rejections` —— **绝对偏离红线**（每个标答 ≥2 个）。命中任一即**一票否决**。
  例：同一事实答"打情骂俏""甜蜜互动"判严重偏离。
* `directional_keywords` —— 从 `semantic_core` 中自动抽取、且**确实在被引用证据里逐字出现**的方向词，供机器阅卷使用。
* `key_entities` —— 关键实体（人名、金额、读数）。**保证逐字出现在 `evidence_ref_ids` 指向的碎片中**。
* `evidence_ref_ids` —— 证据碎片编号（`M###` MIC 切片 / `A###` APP 通知 / `SH##` 心率事件 / `SI##` IMU 事件 / `S0` 体征摘要）。
* `secondary_points` —— 同一维度的次级要点（副线剧情），结构与主锚点一致。

## 二、题目构成

* **单题 40~58 个事件**（中位 50.6）：只有约 10 个碎片承载标答证据（≤29 %），其余是买咖啡、取快递、同事闲聊、地铁报站、外卖送达一类的海量琐碎日常。
* **32 条主线剧情**（每条 312~313 题，全库均匀覆盖），每条都构成**跨维度冲突或转折**。示例：
  * `CRITICISM_AND_BREAKUP` —— 白天被领导当众否定季度汇报，晚间恋人提出分手，21 时心率骤升 125bpm；
  * `LAYOFF_RUMOR_MORTGAGE_FAIL` —— 裁员名单传闻 + 房贷扣款失败 + 深夜好友开口借钱；
  * `RIDER_BAD_REVIEW_STORM` —— 暴雨送单 38 单，超时被扣款并收到差评，电动车打滑；
  * `NEWBORN_NIGHT_FEED_CONFLICT` —— 夜奶 5 次 + 产后情绪筛查偏高 + 喂养观念婆媳冲突。
* **14 条副线**（每题 1~3 条）补充次级要点：快递超时纠纷、健身房续费推销、二手变现、医保门诊报销、通勤延误记迟到、停车费、私单副业、家电维修、课外班续费、宠物疫苗、父母安排相亲、体脂上升等。
* **人物设定**：50 种职业 × 40 座城市 × 22~68 岁 × 5 种婚恋状态，9,537 个不同姓名；职业与剧情强绑定（骑手题只落在骑手人设上，护士题只落在护士人设上）。

## 三、反泄漏纪律（出题方自我约束）

本战队做题时踩过对手题库的坑，出题时逐条堵死，并由 `validate_question()` 在**每一道题落盘前**强制校验：

| 约束 | 校验方式 |
|---|---|
| 题面不含任何答案字段（`ground_truth` / `is_junk` / `label` / `kind` / `note` / `semantic_core` / `spine_id` …） | 递归扫描全部键名 |
| 标答实体逐字出现在被引用证据中 | 逐实体子串校验 |
| 红线词不出现在题面任何文本中（否则标答自相矛盾） | 逐红线子串校验 |
| 同义词与红线不得相交 | 集合求交 |
| 每个标答必须有可追溯证据 | `evidence_ref_ids` 非空且编号存在 |
| 事件时间落在 07:00~23:30 且各通道内升序 | 逐通道校验 |
| 单题事件数 ≥40 | 计数 |
| 题面无残留未填充占位符 | 字符串取值扫描 |

**全量 10,000 题：以上 8 项校验全部通过（0 例外）。**

## 四、复现

```bash
# 出 1 万道题（约 60 秒；同 seed 逐字节可复现）
.venv/bin/python benchmarks/daily_life_summarization/generators/daily_life_generator_01a0aa2e.py \
  --count 10000 --seed 20260916 --out-dir benchmarks/daily_life_summarization

# 只跑自查、不落盘
.venv/bin/python benchmarks/daily_life_summarization/generators/daily_life_generator_01a0aa2e.py --count 50 --dry-run

# 断言单测（14 条）
.venv/bin/python -m pytest tests/simulation/test_daily_life_generator_01a0aa2e.py
```

## 五、给做题方的阅卷建议

1. **先判方向，再判红线**：`acceptable_synonyms` 命中即方向正确；`red_line_rejections` 命中则该维度直接判错（一票否决），两者同时命中以红线为准。
2. **不要用字句匹配**：`semantic_core` 是方向描述，不是标准答案原文；同义词列表也不要求穷举，语义等价即可。
3. **实体按字面核**：`key_entities` 保证逐字出现在证据碎片中，可用于实体召回率的机器计算。
4. **注意噪声占比**：单题约 70 % 以上的碎片是琐碎日常，把它们写进总结不加分，写成"核心剧情"会被红线判错。
