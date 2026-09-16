# AIOS 3.0 全天生活流与多维总结高熵出卷（01a0aa2c-fantonghui 出卷战队）

> 出题侧交付：**10,000 个人的一天**（每人 24 小时已清洗生活流），
> 每道试卷均为标准 JSON 四键结构，标答为**六维方向性语义锚点**。
>
> 本库与同分支 `questions_agent_aa2c_10k.jsonl`（`README.md`）为同战队互补题库：
> 本库独有语义陷阱池（0~3 条/题）、财务维解耦滚动、锚点实体 100% 可观测自检、
> 跨源证据约束（全局证据 ≥3 条且覆盖 ≥2 种事件来源）与对抗性难度分级，
> 供跨队交叉做题与压力测试选用。


## 交付物

| 文件 | 说明 |
| --- | --- |
| `generators/daily_life_pools_01a0aa2c.py` | 素材库：12 城市 / 20 职业 / 26 剧情原型 / 13 社交·7 情绪·7 健康·13 事业·7 财务状态机 / 25 琐事模板 / 8 语义陷阱 |
| `generators/daily_life_generator_01a0aa2c.py` | 组卷器：人设组装 → 加权选原型 → 财务事件解耦滚动 → 时序编织 → 六维标答 → 自检 |
| `questions/questions_daily_life_01a0aa2c.jsonl` | **10,000 题**（52.5 MB，sha256 见 manifest，均 20.7 事件/天） |
| `questions/manifest_daily_life_01a0aa2c.json` | 指纹与分布统计（剧情族/难度/判卷规则） |
| `../../tests/bench/test_daily_life_generator_01a0aa2c.py` | 20 项真值自检单测 |

## 试卷结构（每行一个 JSON）

```jsonc
{
  "question_id": "QDAY_01a0aa2c-fantonghui_00001",
  "generator_agent": "01a0aa2c-fantonghui",
  "timestamp_utc": "2026-xx-xxT12:00:00Z",
  "difficulty": "EASY | MEDIUM | HARD | ADVERSARIAL",
  "persona": { "persona_id", "age", "occupation", "city", "relationship", "personality", "name" },
  "cleaned_daily_stream": {
    "date": "2026-xx-xx",
    "sensor_summary": { "morning_rest_hr", "total_steps", "sleep_hours", "sleep_window", "anomalies" },
    "events": [
      { "id": "e01", "t": "07:33", "src": "sensor", "text": "晨起静息心率69bpm" },
      { "id": "e04", "t": "09:30", "src": "app", "app": "短信", "from": "市第一人民医院", "text": "……" },
      { "id": "e06", "t": "10:14", "src": "mic", "from": "小杨", "scene": "工位玩笑", "text": "……" }
    ]
  },
  "directional_ground_truth": {
    "global_daily_summary": { "core_anchor", "accepted_synonyms", "redline_criteria", "anchor_entities", "evidence_event_ids", "plot_family", "intensity" },
    "dimensions": [ "dim:health / dim:social / dim:emotion / dim:finance / dim:career" 同构五块 ]
  }
}
```

- **时间轴铁律**：全部事件落在 `07:00~23:30`，单调不减；睡眠窗口由 `sensor_summary` 宏观承载。
- **事件三源混合**：`mic`（家人/同事/朋友/陌生人对白，含 scene）、`app`（工作群/伴侣/银行/外卖/新闻）、`sensor`（心率/步数/睡眠/IMU 宏观摘要）。
- **高熵交织**：每题 15~30 条事件 = 核心大事（跨维度冲突/转折）+ 12~17 条琐碎日常（买咖啡/取快递/同事闲聊）+ 0~3 条语义陷阱。

## 标答：六维方向性语义锚点

每个维度（含全局）包含：

| 字段 | 语义 |
| --- | --- |
| `core_anchor` | 方向核心要点（唯一真方向） |
| `accepted_synonyms` | **可接受方向同义词簇**（命中任一即得分） |
| `redline_criteria` | **绝对偏离红线判据**（命中任一即该维 0 分，一票否决） |
| `anchor_entities` | 判卷锚点实体（已自检 100% 在当日流文本中可观测） |
| `evidence_event_ids` | 支撑该维结论的事件编号 |

**判卷规则（严禁死板字句匹配）**：答案与 `core_anchor` 或任一 `accepted_synonyms` 方向一致即得分；
方向命中任一 `redline_criteria` 即一票否决。例：事实"分手" → 答"吵架/感情破裂/协议分开"得分，
答"打情骂俏/甜蜜互动"否决。

## 出题铁律的工程落实

1. **可观测性自检**（第一轮竞技场"盲卷不可观测锚点"缺陷的出题侧根治）：
   生成器对每题执行 `verify_question()`——每个锚点实体必须在当日语料（事件文本/from/app/scene/异常明细）中出现，10,000/10,000 通过；
2. **必须含跨维度冲突或转折**：26 个剧情原型全部为跨维复合叙事
   （如用户示例原型 `BREAKUP_AFTER_CRITICISM`：白天被领导当众批评 + 晚间女友提分手 + 心率骤升 118~132bpm），
   连平静基线日也内建轻度转折（网购好物到货/外卖超时赔付），全局证据强制 ≥3 条且覆盖 ≥2 种事件来源；
3. **财务维解耦滚动**：财务事件独立于原型抽取，防"原型→财务"指纹捷径；
4. **语义陷阱**：同事玩笑（辞职去大理）、群友吹牛（收购腾讯）、惊悚新闻标题（90后体检异常率）、
   砍一刀、验证码残留、他人朋友圈生活——说话者均为他人，陷阱关键词被红线判据闭环惩罚；
5. **确定性**：seed 化（`0x1a0aa2c + idx*7919`），同种子逐字节可复现。

## 复现

```bash
python3 benchmarks/daily_summary/generators/daily_life_generator_01a0aa2c.py \
    --count 10000 --out benchmarks/daily_summary/questions/questions_daily_life_01a0aa2c.jsonl

python3 -m pytest tests/bench/test_daily_life_generator_01a0aa2c.py -q   # 20 passed
```

## 盲做协议

标答内嵌于题目 JSON（`directional_ground_truth` 字段）。解题方加载后应**先剥离该字段**再交给模型作答，
随后用剥离的标答判卷（与数据清洗侧的结构性剥离先例一致）。

## 分布概览（10,000 题）

- 剧情族 19 类全覆盖：健康危机 1139 / 财务契约 822 / 情感转折 787 / 职场危机 777 /
  职场危机×情感断裂 742 / 职场转折 686 / 复合转折（喜忧参半）683 / …… / 正向突破 310
- 难度：HARD 4054 / ADVERSARIAL 2933 / MEDIUM 1710 / EASY 1303
- 平静基线占比 ~7.8%（防止模型把"平静"当默认答案刷分）
