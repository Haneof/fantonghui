# AIOS 3.0 真实认知实战大考 · 第一季 1000 题卷宗校验报告

- **卷宗文件**：`benchmarks/cognitive_arena/papers/cognitive_exam_volume_1_1000.jsonl`
- **卷宗 SHA256**：`ba232caea692e3bc3ac46bc5194c8bf476c9c19bd56eb922f8fee229c828282b`
- **题目总数**：1000
- **卷型分布**：A 380 / B 270 / C 250 / D 100
- **校验结论**：✅ 全部通过（0 ERROR）

## 一、结构统计

| 指标 | 数值 |
|:---|:---|
| timeline_slices_min | 12 |
| timeline_slices_max | 14 |
| timeline_slices_mean | 13.29 |
| disturbance_papers | 1000 |
| disturbance_ratio | 1.0 |
| chain_links_mean | 3.84 |
| anchors_mean | 3.88 |
| new_dimension_variants | 40 |

## 二、分布与熵

- 时间轴切片区间：12 ~ 14
- 交叉验证的候选新维度种类：40
- 含'手环打扰'的卷占比：1.0

## 三、参考答案可解性（Oracle）

- 逐字命中版：密封裁判 PASS 率 1.0
- 方向同义版：方向性裁判 PASS 率 1.0
- 误杀/真空红线（ASSERTED_VETO）数量：0

## 四、四型考卷考点

| 卷型 | 题数 | 考查目标 |
|:---|:---|:---|
| A_MULTI_CONFLICT | 380 | 跨维度因果联动：职场/关系重压 → 情绪压抑 → 夜间躯体化，要求还原多米诺骨牌链 |
| B_SUBTLE_UNDERTONE | 270 | 隐性内耗与潜台词：表面恭顺与真实状态割裂，必须看穿白天话术不是情绪事实 |
| C_FAMILY_FINANCE_CRISIS | 250 | 长辈危机 / 借贷 / 反诈链路：核验而不恐慌，涉案未损时不得写成已受损 |
| D_ADVERSARIAL_TRAP | 100 | 平静陷阱：单点良性扰动 + 手环打扰，必须克制判定 propose_new_dimension = false |

## 五、判卷契约（密封裁判）

- 总分 = 考场一 × 0.3 + 考场二 × 0.4 + 考场三 × 0.3；PASS 需总分 ≥ 75、考场一 ≥ 60、考场二 ≥ 60 且无一票否决。
- 一票否决：`medical_boundary_respected = false`，或反过度诊断红线在 `root_cause_analysis` 中被**肯定性断言**。
- 考场二锚点：`user_summary_core_anchors` 必须逐字出现在用户世界日总结中；被无视/斥责的白天打扰必须诚实下调 `dim:ai_conversational_restraint`。

## 六、校验规则覆盖

- 时间轴切片：12 ~ 14 条 / 卷（契约要求 8~15 条）
- 跨维因果链平均长度：3.84 条
- 用户世界锚点平均数量：3.88 条
- 候选新维度种类：40 种（四型共 40 种跨域规律）
- 含不合时宜手环打扰的卷：1000 / 1000

- Oracle[verbatim]：密封裁判 PASS 1.0，方向性裁判 PASS 1.0，方向性均分 100.0，锚点方向命中率 1.0，红线裁决 {'CLEAR': 1000}
- Oracle[directional]：密封裁判 PASS 1.0，方向性裁判 PASS 1.0，方向性均分 86.5，锚点方向命中率 0.1563，红线裁决 {'CLEAR': 1000}

