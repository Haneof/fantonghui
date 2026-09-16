# arena01 · M5-001~004 认知演化线（与主链路收敛交付并存，纯增量）

- **日期**：2026-09-16
- **会话分支**：`arena/01a0a700-fantonghui`（本会话固定分支，工单所列 `arena/agent-06~10-*`
  分支无法在本会话创建，交付统一落于本分支）
- **基线**：`origin/aios-2.0@582e187` 主干 M5 认知底座 + 会话分支收敛态 `bb5e7c5`
  （含并行会话 M5-005 战训考场交付，已采纳为唯一 M5-005 实现）。

## 交付内容（5 个提交，均为对主干薄实现的叠加演化，v1 语义 100% 向下兼容）

| 提交 | 工单 | 要点 |
| --- | --- | --- |
| `61cdfbd` | M5-001 | `PathwayComparisonExecutor`：A 暴力全扫 / B 朴素关键词 / C 拓扑分级下钻同场竞技，实测 A 36,269 tokens 召回 0、B 召回 0.33、C 30 tokens 召回 1.0，压缩比 1209×；回执自动喂给 `OperationExperienceDistiller` 沉淀黄金经验（≤500 tokens、准确率 1.0、SQLite 持久化）；单次命中 ≤150 tokens 门禁 |
| `ed9092e` | M5-002 | `detect_anomaly_window` 可审计异常窗口；`HighOrderDimensionDistillerV2` 从低阶物理事实提炼 DIM_BURNOUT_RISK / DIM_CREDIT_RISK / DIM_PARENT_HEALTH（门槛1 一票否决 + 拒绝理由 + 证据链）；`ReadOnlyDimensionTag` 只读挂载（冻结、幂等、撤销即抛错） |
| `f6c8f55` | M5-003 | `review_iron_rules` 四铁律 + 认知底线；羁绊升级双硬门槛（365 天陪伴 + 3 次关键共同事件才可 TRUSTED）；`decide_posture_with_rapport` 紧迫度×羁绊矩阵（生死级任何层级直言 / 高危对陌生人微震 / MEDIUM 一律微震 / 琐碎沉默）；启动四步序切片 ≤350 tokens |
| `2b7b19f` | M5-004 | `EvidenceLedger` 证据台账：虚指即抛 `MissingEvidenceError`；送礼/反诈/熔断三顾问证据驱动化（足浴盆与饰品禁区、判决+拖延缺一拒绝、通宵→早搏因果方向校验）；`ActionableAdvice` 扩展 advice_id/hard_refusal/forced_action/confidence |
| `ec8839c` | 对齐 | MEDIUM 级一律微震（开口只留给高危与生死）；送礼顾问兼容无品类标注的历史结局事实 |

## 与并行会话交付的边界

- M5-005（`agent_mind_bench.py`）采用并行会话收敛交付（千面世界发生器 + 文件级克隆沙箱 +
  三对照战队），本会话同名实现已在 rebase 中主动放弃，零覆盖。
- 本线仅演化 `cognition/` 模块并扩展 `tests/cognition/` 用例（原有用例全部保留且满绿）。

## 验证

- `tests/cognition/` 39 用例、`tests/query/` 21 用例、`tests/simulation/`（含战训考场 8 用例）满绿；
- 全量回归 **1158 passed / 0 failed**（41.6s）。
