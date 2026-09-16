# 战队 `01a0aa2c-fantonghui` 出卷交付说明 · **V3 独立实现**（全天生活流与多维总结高熵试卷 · 10,000 题）

> **与队友成果并存说明**：同一分支上已存在队友产出的 10K 卷（canonical 路径
> `questions/questions_01a0aa2c-fantonghui.jsonl` + `ground_truth/gt_01a0aa2c-fantonghui.jsonl`，
> 由 `benchmarks/data_cleaning/generators/generator_01a0aa2c.py` 生成）。
> 本文件描述的是**另一套独立实现（V3）**的产物，统一带 `_v3` 后缀，**不覆盖、不修改队友任何文件**。
> 两卷都符合 `CleaningQuestion` 契约，可分别独立取卷做题；V3 卷的差异见第六节「与既有卷的差异」。

> **角色**：AIOS 3.0 全天生活流与多维总结高熵出卷官（Master Dispatch #11 · 第一阶段 · 角色一 V3）
> **出卷战队**：`01a0aa2c-fantonghui`　**分支**：`arena/01a0aa2c-fantonghui`
> **随机种子**：`20260916`（确定性可复现：同 seed + 同条数 → 逐字节一致）
> **发生器**：`src/aios_core/simulation/cleaning_arena_generator_01a0aa2c.py`
> **入口**：`scripts/generate_cleaning_arena_bank_01a0aa2c.py`
> **验收测试**：`tests/simulation/test_cleaning_arena_generator_01a0aa2c.py`（26 条，全部通过）

---

## 一、交付物

| 文件 | 说明 | 规模 |
| :--- | :--- | ---: |
| `benchmarks/data_cleaning/questions/questions_01a0aa2c-fantonghui_v3.jsonl` | 考卷，10,000 行，符合 `CleaningQuestion` 契约（题面**不含**任何标答字段） | 10,000 题 / 65.0 MB |
| `benchmarks/data_cleaning/ground_truth/gt_01a0aa2c-fantonghui_v3.jsonl` | 标答底稿，与考卷逐题一一对应（`ground_truth_facts` + `ground_truth_junk_ids` + 六维方向性标答） | 14,261 条事实 / 318,597 个垃圾 ID / 32.4 MB |
| `benchmarks/data_cleaning/questions/manifest_01a0aa2c-fantonghui_v3.json` | 自审报告（配比、垃圾率、意图分布、自检结论、**sha256**） | — |
| `src/aios_core/simulation/cleaning_arena_generator_01a0aa2c.py` | 确定性题库发生器（7 维随机因子拓扑 + 陷阱 + 自检 fail-closed） | 2.6 千行 |
| `tests/simulation/test_cleaning_arena_generator_01a0aa2c.py` | 契约测试（协议合规 / 防泄漏 / 公平可解 / 出卷纪律） | 26 条 |

**sha256**（与 manifest 一致，逐字节可校验；同 seed 重放已验证逐字节相同）：

```
questions_01a0aa2c-fantonghui_v3.jsonl  3588fa17ea44ccc54035a2331fb89efe4244845891de2a56832a0554b2246852
gt_01a0aa2c-fantonghui_v3.jsonl         9b4b607bc3706b321edb0fb1e5375cb9fcb05755df86dc7549cc1e041a4f0144
```

---

## 二、单题结构 = 一个人的一整天（06:30~23:40）

每道题都是**同一个手环佩戴者的完整一天**，五路数据流按 `t`（HH:MM 本地时间）归并为 `cleaned_daily_stream`：

| 数据流 | 占比 | 题内内容 |
| :--- | ---: | :--- |
| **传感器流** (IMU/PPG/GPS/气压) | **30%** | 50Hz 碎步晃动、打字震动、地铁颠簸、心率正常波动 vs 真实高冲击跌倒 / 室性早搏阵发 / 静息心动过速 / 洗胃后低血糖等宏观摘要窗 |
| **MIC 麦克风录音切片** | **30%** | 60~88dB 环境杂音、地铁报站、商场促销、邻桌闲聊、方言颗粒 vs 借还款约定 / 亲人嘱托 / 保密约定 / 隐蔽呼救 |
| **声纹聚类记录** | **20%** | 3~24 个说话人碎片（佩戴者 1 条恒保留 + 陌生路人 + 关键联系人），余弦相似度不可张冠李戴 |
| **APP 杂乱消息流** | **15%** | 微信群刷屏、验证码、营销推送、砍一刀 vs 银行大额凭证 / 法院传票 / 医院检验单 / 签约日程（**应用与发送方按标签推断，绝不出现"工地通报出现在医院 App"**） |
| **用户原话与自言自语** | **5%** | 口嗨吹牛、口头禅发泄、玩笑调侃 vs 真实就医诉求 / 辞职决定 / 隐性心绞痛求助 |

配比由**平滑轮转序列**保证（Webster 除子法思路）：整周期 100 题严格 = 30/30/20/15/5，任意前 n 题最多偏离 1 题。

**题面标准 JSON 字段**（角色契约）：

```json
{
  "question_id": "Q_01a0aa2c_00001",
  "generator_agent": "01a0aa2c-fantonghui",
  "timestamp_utc": "...", "difficulty": "ADVERSARIAL", "day_span": "06:30~23:40",
  "persona_tag": "D07_钢筋班包工头_48岁",
  "persona": {"name": "...", "age": 48, "city": "广州", "occupation": "...", "life_stage": "...", "key_relations": [".."], "traits": [".."]},
  "cleaned_daily_stream": {"time_span": "07:0x~23:3x", "slices_total": 43, "by_channel": {...}, "ordered_by": "t"},
  "sensor_stream": {...}, "mic_stream": [...], "voiceprint_cluster": {...},
  "app_message_stream": [...], "user_dialogue_stream": [...]
}
```

---

## 三、标答 = 六维方向性核心要点（可接受同义词 + 绝对偏离红线）

标答**只认方向，不认字眼**；同时把"方向反了"写成机器可判的红线：

```json
"directional_ground_truth": {
  "dimensions": [
    {"dimension_id": "dim:global",  "direction_summary": "主线：…；转折：…",
     "acceptable_synonyms": ["欠款","还钱","催款","赖账"],
     "absolute_red_lines": ["债务已全部结清无纠纷","对方免除全部欠款","借款按约到账并如期归还"],
     "evidence_ref": "aF01"},
    {"dimension_id": "dim:emotion", "direction_summary": "清晨尚算平静 → 日间压抑强撑 → 夜间情绪崩溃或彻底沉默",
     "acceptable_synonyms": ["情绪低落","压抑到崩溃","心态崩了","强撑到破防","情绪失控"],
     "absolute_red_lines": ["全天心情愉快轻松","情绪平稳毫无波澜","把冲突写成甜蜜互动"]},
    {"dimension_id": "dim:health",  "direction_summary": "本日无该维度关键事实",
     "acceptable_synonyms": ["无相关事件","未涉及"],
     "absolute_red_lines": ["编造该维度事实=幻觉一票否决"]},
    {"dimension_id": "dim:finance", "fact_ref": "Q_01a0aa2c_00001-fact-1",
     "acceptable_synonyms": ["逾期","还款","征信"],
     "absolute_red_lines": ["债务已全部结清无纠纷","对方免除全部欠款","借款按约到账并如期归还"]}
  ],
  "counterfactual_note": "含真假对抗陷阱：采信伪造/对冲信息为真实事实 = 一票否决"
}
```

- **六维铁定齐备**：`dim:global`（全局日总结/核心剧情主线）+ `dim:health` / `dim:social` / `dim:emotion` / `dim:finance` / `dim:career`；若当日还发生生活契约类事实，额外如实追加 `dim:life`（绝不把生活纠纷硬塞进别的维度）。平均 **6.29 维/题**。
- **可接受方向同义词**：维度级 2~5 个近义簇；事实级 `directional_keywords` 簇内任一词命中即视为方向相符。
- **绝对偏离红线判据**：19 个判据族（`INTENT_VETO_FAMILY`）覆盖全部 42 种语义意图，**无裸事实**（`red_line_facts_share = 1.0`）。老大的判例已固化为自动化断言：事实为吵架/决裂（`CONFLICT_RUPTURE`）时，红线必含 **"打情骂俏/甜蜜互动"**（答成甜蜜互动 = 一票否决）。
- **陷阱题**（4.35% = 435 题）额外携带 `counterfactual_note`：伪造截图 / 先承诺后反悔 / 撤回证据 / 假摔碰瓷，均要求"采信假信息 = 一票否决"。

---

## 四、整卷统计（seed=20260916，manifest 原样摘录）

| 指标 | 数值 |
| :--- | :--- |
| 题量 / 语义意图种类 / 佩戴者谱系 | **10,000** / **42** / **15**（D01 高三复读生 ~ D15） |
| 事实总数 / 每题材事实数 | **14,261**（1 条 5,804 / 2 条 4,131 / 3 条 65） |
| 垃圾 ID 总数 | **318,597** |
| 垃圾占比（按片段） | 均值 **92.89%** / 最低 **90.62%**（铁律四下限 90%） |
| 数据流配比 | 传感器 **30.0%** / MIC **30.0%** / 声纹 **20.0%** / APP **15.0%** / 用户原话 **5.0%** |
| 五大认知域（主事实） | finance 20.22% / social 20.22% / career 20.22% / life 20.21% / health 19.13% |
| 五大认知域（事实级） | social 20.61% / career 20.01% / finance 20.00% / life 19.99% / health 19.40%（**均 ≥15%**） |
| 难度分布 | MEDIUM 75.68% / HARD 12.61% / EASY 7.36% / **ADVERSARIAL 4.35%** |
| 全天跨度 | 均值 **947.6 分钟**（15.8 小时），全部落在 06:30~23:40 内 |
| 锚点可溯源率 / 方向词接地率 / 标答唯一率 | **100%** / 53.13% / 98.19% |
| 自检结论 | `problems = 0` → **PASS**（fail-closed：任一项不过即 `SystemExit`） |

> 说明：垃圾占比按**片段**计（垃圾片段数 ÷ 全部片段数），与派工单"95% 噪音 / 5% 事实"同口径；
> 本卷取 90%~95% 区间内的 **92.9%**，把省下的配额用于承载跨维度冲突的第二条事实与真假对抗陷阱。

---

## 五、出题纪律（自动化保证，非人工承诺）

1. **零模板化**：37 个事件模板 × 6 方言颗粒 × 10 城 × 15 佩戴者 × 7 声学拓扑 × 6 传感波形 × 42 意图 × 4 类陷阱 → 组合空间 ≫ 10,000，实测标答唯一率 98.19%，意图覆盖 42/42。
2. **跨维度冲突**：双事实题 4,196 道，主事实与次事实**强制不同维度**（单题自检拦截 `SAME_DIMENSION_FACTS`）。
3. **事实↔证据一致**：每条事实的 `source_ref_id` 必指向真实片段；标答 `core_content` 的时间戳与证据片段 `t` **逐题一致**（实测 0 处不一致）；锚点 100% 逐字可溯源。
4. **防泄漏**：题面绝不出现 `ground_truth_*` / `is_junk` / `junk_tag`（实测全卷 0 处）。
5. **防伪冲突**：垃圾片段不得复述事实锚点（拦截"剪枝即丢证据"），另有 3,256 道"回声陷阱"题——垃圾提及方向词，剪枝者必须保住真证据。
6. **片段 ID 唯一 + 零空占位**：单题内 ID 全局唯一（`DUPLICATE_FRAGMENT_ID` 校验），文本不得为空。
7. **绝不自出自做**：协议层一票否决（`solver_agent == generator_agent` → 0 分），测试中已断言。

---

## 六、与既有卷（canonical 路径）的差异

| 维度 | 既有卷（`*_01a0aa2c-fantonghui.jsonl`） | 本 V3 卷（`*_v3.jsonl`） |
| :--- | :--- | :--- |
| 发生器 | `benchmarks/data_cleaning/generators/generator_01a0aa2c.py` | `src/aios_core/simulation/cleaning_arena_generator_01a0aa2c.py` |
| 每题材事实数 | 2.65 | 1.43（1 条 5,804 / 2 条 4,131 / 3 条 65，跨维度冲突强制不同维） |
| 垃圾占比（按片段） | 0.8167（其口径） | **0.929**（均值）/ 0.906（最低），>90% 铁律 |
| 六维标答 | 事实级 `directional_keywords` | 事实级 + **`directional_ground_truth.dimensions` 六维块**（`dim:global` 全局日总结 + emotion 情绪主线 + 每维 `acceptable_synonyms` 与 `absolute_red_lines`，19 个判据族覆盖 42 意图） |
| 对抗陷阱 | 有（其 `chain` 体系） | T01~T04 四类 + 3,256 道垃圾回声陷阱 |
| 契约测试 | 其 QA 报告 | `tests/simulation/test_cleaning_arena_generator_01a0aa2c.py`（26 条，含"抄标答满分/自出自做一票否决"断言） |

两卷可同时作为交叉题库使用：同一战队的两套卷互相独立，**都不允许本战队自做**（自出自做一律 0 分）。


## 七、其他战队如何取卷做题（跨 Git 1 对多）

```bash
git fetch origin arena/01a0aa2c-fantonghui
git checkout origin/arena/01a0aa2c-fantonghui -- \
  benchmarks/data_cleaning/questions/questions_01a0aa2c-fantonghui_v3.jsonl
# 标答永不落盘：阅卷时以流式读取
PYTHONPATH=src python3 scripts/judge_solver_on_bank.py \
  --questions benchmarks/data_cleaning/questions/questions_01a0aa2c-fantonghui_v3.jsonl \
  --answers   benchmarks/data_cleaning/answers/ans_<solver_id>_on_01a0aa2c-fantonghui_v3.jsonl \
  --gt-ref    origin/arena/01a0aa2c-fantonghui:benchmarks/data_cleaning/ground_truth/gt_01a0aa2c-fantonghui_v3.jsonl \
  --report    benchmarks/data_cleaning/reports/report_<solver_id>_on_01a0aa2c-fantonghui_v3.json
```

阅卷口径与派工单一致：`DM×40 + ER×25 + JP×25 + DA×10 − 幻觉×15`，≥90 分 PASS。

---

## 八、复现方式

```bash
PYTHONPATH=src .venv/bin/python scripts/generate_cleaning_arena_bank_01a0aa2c.py \
    --count 10000 --seed 20260916            # 全量重放（约 14 秒）
# 默认输出即 V3 路径（questions/gt/manifest 带 _v3 后缀）
PYTHONPATH=src .venv/bin/python -m pytest \
    tests/simulation/test_cleaning_arena_generator_01a0aa2c.py -q
```
