# 题库报告：全天生活流与多维总结样卷（daily_01a0aa2c，300 卷）

> 出卷：`benchmarks/data_cleaning/question_bank_daily_01a0aa2c/`（pools + builder + judge + CLI 自审落盘）
> 种子：`--n 300 --seed 42`，确定性可复现
> 单测：`tests/simulation/test_daily_bank_01a0aa2c.py`（7/7 通过）

---

## 一、交付文件

| 文件 | 内容 | 大小 |
|---|---|---:|
| `questions/questions_daily_01a0aa2c.jsonl` | 300 卷全量（含 `directional_ground_truth`） | 1.65 MB |
| `questions/questions_daily_01a0aa2c_blind.jsonl` | 300 卷盲卷（已剥离标答，供做题方） | 1.14 MB |
| `ground_truth/gt_daily_01a0aa2c.jsonl` | 300 卷独立标答卷（供裁判） | 0.53 MB |

单卷 schema：`question_id / generator_agent / date / persona / arc_id / twist_id / cleaned_daily_stream / directional_ground_truth`。

切片 schema：`{slice_id, time(07:00~23:30升序), modality(mic/app/sensor), scene/speaker 或 source 或 metric, text}`。

标答 schema（每维）：`{core, neutral, anchors:[{key, accept[]}], redlines[]}`，六维为 `global + dim:health/social/emotion/finance/career`。

---

## 二、熵设计

- **16 persona**：年龄 22~55，覆盖互联网/制造/医护/骑手/司机/教师/学生/退休等职业与婚育财务基线，全员出场。
- **21 冲突弧**：每弧横跨 ≥3 维度且含冲突或转折（如当众被批+分手+心率骤升、体检结节+全家担忧、裁员+房贷+失眠、夜班抢救+医患冲突等），各弧使用 13~15 次，`min_arc_use=13`。
- **10 小反转**（出现率 75.7%）：退款到账、偶遇老同学、错过末班车、手机碎屏、被放鸽子等，为全局线追加"小插曲"锚点。
- **36 琐事填充**：咖啡/快递/工作群/天气/追剧/散步等日常噪音，每卷 15~25 切片（均值 20.0），模态 mic/app/sensor 全覆盖。
- **一致性门禁**：persona 属性与弧/填充/反转前提相容（need 语义含 `not_` 否定）：全职妈妈不挨公司批、已婚者"离婚"不"分手"、单身卷无亲密伴侣行为、女性当伴娘/男性当伴郎、子女称谓随性别、租房者才遇涨租等。全库一致性扫描零违例。

## 三、自审（写盘前强制，任一条失败即抛错）

1. 题量严格 300；2. question_id 全局唯一，slice_id 题内唯一，时刻升序且在窗内；
3. 六维齐全，每维 core/anchors(key+accept)/redlines 非空；
4. **溯源**：非 neutral 维 + global 的每个锚点（key 或其 accept）必须原文出现在本卷生活流；
5. 熵底线：persona≥12 种、arc≥15 种、无整卷重复；
6. 每卷 15~25 切片，mic≥3、app≥3、sensor≥2。本次：persona 16 种、arc 21 种，全部通过。

## 四、方向性阅卷器（`judge.py`，无 LLM 基线）

模型作答：六维各一段文本。判分：任一红线命中→该维 0 分并标记 `veto`（一票否决）；
否则按锚点覆盖率给分（key 或其任一 accept 命中即覆盖）；neutral 维无红线即满分（缺席不断言即正确）。
总分 = 六维均值，**PASS ≥ 60**。已验证：纯同义改写 100 分、红线作答该维 0 分+veto、空答不及格。

## 五、中性维度分布（缺席即正确）

career 161、health 142、finance 84、social 27、emotion 14 卷为 neutral；global 永不 neutral。

## 六、扩量说明

CLI 支持 `--n/--seed` 任意扩量至 10k（内容池组合空间：16 persona × 21 弧 × 10 反转 × 琐事采样 ≈ 33.6 万理论组合，
10k 规模无重复风险）。扩量时建议保持自审六条不变。
