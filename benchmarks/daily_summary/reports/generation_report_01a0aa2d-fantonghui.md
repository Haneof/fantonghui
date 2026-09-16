# 出卷交付报告：全天生活流与多维总结高熵考卷（10,000 人 × 24 小时）

> **出卷战队**：`01a0aa2d-fantonghui` · **考段**：Master Dispatch #11 第二步（全维度多尺度时间日志总结大考）出题侧
> **确定性种子**：`20260916`（`scripts/generate_daily_summary_01a0aa2d.py` 可一键复现）
> **交付物**：`benchmarks/daily_summary/questions/questions_01a0aa2d-fantonghui.jsonl`（39.1 MB，10,000 行 = 10,000 个人的一天）

---

## 一、试卷结构（单题四键，严格符合出题规范）

```json
{
  "question_id": "Q_01a0aa2d-fantonghui_00001",
  "generator_agent": "01a0aa2d-fantonghui",
  "exam_date / difficulty / archetype / trap / day_signature": "元信息",
  "persona": {"name","age","city","job","relationship","partner","band_id"},
  "cleaned_daily_stream": [
    {"t":"07:23","src":"sensor","text":"晨起静息心率80bpm；昨夜睡眠5小时0分…"},
    {"t":"09:46","src":"mic","who":"同事","text":"早，昨晚看球了吗？…"},
    {"t":"13:05","src":"app","app":"企业微信","sender":"HR","text":"岗位调整通知…"},
    {"t":"20:25","src":"app","app":"微信","sender":"史娟辰","text":"这几天是我不对…"}
  ],
  "directional_ground_truth": {
    "global_daily_summary": {"core_plot","core_anchors","acceptable_directions","redline_violations","key_evidence_refs"},
    "dim:health":  {…同构…},
    "dim:social":  {…},
    "dim:emotion": {…},
    "dim:finance": {…},
    "dim:career":  {…}
  }
}
```

**方向性标答铁律落实**：每维给出
- `core_plot`：出卷官认定的事实基准（一段话）；
- `acceptable_directions`：可接受方向同义词簇（如 分手/被提分手/感情破裂/失恋 —— 命中簇内任一方向即给分，严禁抠字眼）；
- `redline_violations`：**绝对偏离红线**（如 甜蜜互动/求婚成功/感情升温 —— 命中即一票否决）；
- `key_evidence_refs`：证据溯源（如 `app@21:05`、`sensor@21:42`，全库 91,603 条引用 100% 带流@时间戳）。

## 二、高熵与因果一致性设计

| 机制 | 说明 | 全库统计 |
|---|---|---|
| 事件模板组合 | 事业 15 模板 × 社交 12 模板 × 财务 10 模板 × 陷阱 4 档 | **2,936 种事件组合签名**（0 重复人名/ID） |
| 参数随机化 | 金额按事件分级（医疗垫付 899~2,300 / 房贷 6,800~9,800 / 年终奖 28,000~42,000）、心率、时长、时刻 | 文本级逐卷不同 |
| 跨维度冲突 | 至少两维非平稳（事业×社交×财务×体征联动） | archetype 26 类，双重受挫日占 13.2% |
| **因果编织** | 心率骤升时刻 = 负面事件时刻（±2min）；情绪基调 = 白天/晚间事件符号组合 | 全库时间窗 07:00~23:30 严格有序 |
| **对抗陷阱** | 15.4% 卷面含陷阱：群转发明星分手新闻 / 同事口嗨辞职 / 平台分期广告，红线判据同步注入对应维度 | 1,538 道 ADVERSARIAL |

难度分布：`MEDIUM 1,299 / HARD 7,163 / ADVERSARIAL 1,538`。

## 三、质检结论（自动校验 0 错误）

- ✅ 10,000 行 JSONL 全部可解析；`question_id`、`persona.name` 全局唯一（10,000/10,000）
- ✅ 每卷六维标答齐全（60,000/60,000 维度 schema 正确）；`acceptable_directions` 与 `redline_violations` 非空
- ✅ 91,603 条 `key_evidence_refs` 全部为 `流@HH:MM` 形式且指向真实切片
- ✅ 时间轴有序且落在 07:00~23:30；金额符合事件分级；陷阱题红线注入正确
- ✅ 已人工盲检样卷：普通卷（Q_00004 调岗+和好+垫付）与陷阱卷（Q_00003 绩效C+催婚争吵+广告陷阱）因果自洽

## 四、做题方指引（下一步 1 对多交叉做题）

1. 读题：`cleaned_daily_stream` 为**已清洗**生活流（无营销骚扰/垃圾切片），做题模型需在琐碎日常与关键大事之间提纯六维核心剧情；
2. 答题：按维度输出方向性摘要（无需与 `core_plot` 字句一致，落入 `acceptable_directions` 簇即对；触碰 `redline_violations` 一票否决）；
3. 陷阱卷：正确行为是**忽略**转发新闻/口嗨玩笑/平台广告，不把它们编入本人事实；
4. 阅卷建议：复用主干 `DirectionalSemanticMatcher` 的方向容差思想，按"簇命中给分、红线命中归零"执行。

——出卷官 `01a0aa2d-fantonghui` · 2026-09-16
