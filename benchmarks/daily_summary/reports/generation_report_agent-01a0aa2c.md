# 出卷报告 —— 全天生活流与多维总结竞技场 (agent-01a0aa2c)

> 出卷官: `agent-01a0aa2c` · 2026-09-16 · 确定性种子 `0xd417`
> 协议: `src/aios_core/simulation/summary_arena_protocol.py`
> (`DailyPaper` 试卷契约 + `DirectionalSummaryJudge` 方向性裁判)
> 引擎: `benchmarks/daily_summary/generators/daily_paper_generator.py`

## 一、交付产物

| 文件 | 说明 | 规模 |
|---|---|---|
| `papers/papers_agent-01a0aa2c.jsonl` | 母卷 (题面+标答, 出卷底稿) | 1000 卷 / 7.1MB |
| `questions/questions_agent-01a0aa2c.jsonl` | 盲卷 (做题人唯一可读) | 1000 卷 / 4.3MB |
| `ground_truth/gt_agent-01a0aa2c.jsonl` | 独立标答卷 | 1000 卷 / 2.9MB |
| `reports/manifest_agent-01a0aa2c.json` | 分布统计与 SHA-256 | — |

盲卷已过泄漏审计: `core_statement / accepted_synonyms / red_lines /
background_to_ignore` 四键零出现。

## 二、试卷设计

- **16 副人生人格 × 19 条跨维度弧线**: 从 17 岁复读生到 78 岁独居老人,
  每卷一人一天 (07:00~23:30), 平均 21.7 切片; 关键大事 (5~9 节拍)
  编织进海量琐碎 (买咖啡/取快递/群聊/新闻/步数) 中。
- **跨维度冲突是标配**: 如 A01 白天被批+晚上分手+125bpm、
  A11 高速抛锚+油卡盗刷+瞒报家人、A13 讨薪围堵+痛风发作两头跑。
- **六维方向标答**: `global` + `dim:health/social/emotion/finance/career`,
  每维含核心句 / ≥4 同义词 / ≥3 红线 / 接地实体 / 证据切片链,
  另附 `background_to_ignore` (琐事拔高惩罚清单)。
- **难度**: EASY 135 / MEDIUM 341 / HARD 318 / ADVERSARIAL 206。
  ADVERSARIAL 含戏剧性诱饵 (目睹他人吵架/邻里骂战/追尾围观等,
  与佩戴者无关) 与口是心非隐藏态 (“我没事”+体征崩盘)。

## 三、质量门禁 (全部通过)

1. `DailyPaper / BlindDailyQuestion / DailyGTRecord` pydantic 全卷校验。
2. 证据链 100% 可解, 切片时间严格有序且落在 07:00~23:30。
3. 同义↔红线集合与子串级互斥 (杜绝裁判自相矛盾)。
4. **关键实体 100% 接地**: 2000 卷审计, 标答实体在题面零缺失
   (上一代清洗卷 FAINT 地点锚点不可知的教训, 本卷已根治)。
5. **人格一致性审计**: 性别称谓/职业语境/退休状态全卷零错配
   (如复读生无“同事”、已婚者无“女友”、男性无“更年期”)。
6. 时间敏感填充加窗口约束 (晚安≥21点、午休限中午等), 卷内文本去重。
7. 裁判自测: 满分卷 100 / 同义改写 96.5 / 红线整卷否决 / 空卷 0。

## 四、判分尺 (DirectionalSummaryJudge)

- 六维权重 global 30 + 五维各 14; 每维 = 0.65×同义覆盖(≥2中即满)
  + 0.35×实体召回; ≥60 分 PASS。
- 任一维度命中红线 ⇒ **整卷一票否决** (分数保留供诊断)。
- 全局总结出现背景琐事词 ⇒ 每唯一项 −5 (主次不分惩罚)。

## 五、给做题人的提示

本卷考察: 主线提炼 (大事 vs 琐事 vs 诱饵)、跨维度因果串联
(挨批→分手→心率→失眠)、隐性状态识别 (嘴硬 vs 体征)、
维度归因精度 (情绪性心动过速 ≠ 心梗, 待复查 ≠ 确诊)。

*做题人只能读取 `questions/` 盲卷; 命中同义算对, 触红线否决。*
