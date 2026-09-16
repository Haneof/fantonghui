# M5 五连单交付台账（Agent-06 ~ Agent-10）

> 交付分支说明：五张工单原文均要求"基于 origin/aios-2.0 切具名新分支
> （arena/agent-06-m5-search 等）并提 PR"。因本执行会话被平台硬性绑定在
> `arena/01a0a67a-fantonghui`（其他分支的工作不与本会话关联），五单全部
> 在会话分支上按工单内联规格顺序交付，单/批次隔离由 commit 边界保证。
> 差异在此如实记录，不另切分支。

## 执行前提侦察结论

- `origin/aios-2.0` tip = `582e187`（仅 M5 台账 docs）；该分支上
  `src/aios_core/query/search.py` 与 `src/aios_core/cognition/` 包
  **不存在**，工单前提"主干已同步检索总线"不成立 → 全部新建。
- `governance/dispatches/` 仅有 Agent-1~5 工单文件，Agent-6~10 无云端
  工单文件 → 按消息内联规格执行。
- 本分支既有源码/测试零改动，交付为纯增量（新建模块 + 新建测试 + 本台账）。

## 交付清单

| 单号 | 交付物 | 核心 commit | 测试 |
|---|---|---|---|
| Agent-06 M5-SEARCH | `src/aios_core/query/search.py`（三路径对比执行器）+ `src/aios_core/cognition/operation_experience.py`（黄金经验蒸馏） | `f4854db` | 7 |
| Agent-07 M5-DIM-LIFECYCLE | `src/aios_core/cognition/dimension_engine.py` | （实现随 Agent-06 同批入仓） | 6 |
| Agent-08 M5-RAPPORT-MIRROR | `src/aios_core/cognition/self_reflection.py` | 同上 | 7 |
| Agent-09 M5-SYMBIOTIC-ADVISOR | `src/aios_core/cognition/symbiotic_advisor.py` | `7662fe3` | 10 |
| Agent-10 M5-AGENT-ARENA | `src/aios_core/simulation/agent_mind_bench.py` | `8fbc20f` | 9 |

## 验收指标实测

### Agent-06 检索总线与经验蒸馏

- 三路径：A 暴力扫描（世界可见总量+64）/ B 朴素关键词 OR（无共现约束，
  同名干扰必然混入）/ C 拓扑分级下钻（多关键词 AND 共现）。
- 单次命中简报 ≤150 Token 物理截断（`SINGLE_HIT_TOKEN_CAP`）。
- 蒸馏固化条件：≥3 战役且该路径**全部战役 accuracy==1.0**，平手按
  C>B>A 裁决；金经验反例触发**精确率+召回率双检**，失守自动降级
  （`ExperienceDemotedError`）。压缩比：多次检索对比观测 15k~50k
  Token/次 → 金经验直取 ≤500 Token/次。
- 测试 query 语义教训：研究类查询关键词必须是**全证据链共现词**
  （妈妈/礼物），不能是结论词（膝盖/热敷）——后者使 C 路径只能召回
  链尾，召回率 0.25 触发误降级。

### Agent-07 维度生命周期

- 跨域异常锁：≥2 域 × ≥3 天持续异常日（`CrossDomainAnomalyLock`）；
  单域或 2 天短程必拒。
- 铁律 5 三重硬门槛：3 天异常锁 → 30 天试用期 + 12 次预测验证
  （正确率下限 0.70）→ 每日反思配额 1。
- 对抗用例实测：第 29 天申请晋升 → `PrematurePromotionError`
  （served=29/required=30，状态不被越界改动）；当日第 2 次反思 →
  `QuotaExceededBlockError`。
- `HighOrderDimensionDistiller` 产出 `DIM_BURNOUT_RISK` /
  `DIM_CREDIT_RISK`，frozen + read_only 强制（篡改标签 → ValidationError），
  证据指针必须 pin revision。

### Agent-08 镜面/羁绊/姿态

- `SelfIdentityMirror`：启动第一纳秒自审四铁律（绝对诚实/生死第一/
  不废话/历史不可篡改）+ 三条认知底线，镜面序号单调可审计。
- `DynamicRapportModel`：STRANGER→FAMILIAR(≥20)→TRUSTED_WINGMAN
  (≥60 且危机并肩≥1)；缺并肩历练拒绝晋级；betrayal 立即降档。
- `HumanlikeResponsePostureDecider`：P0 与 fraud_signal 一律
  CRITICAL_SPOKEN（旁路睡眠/冷却/羁绊）；HIGH→HAPTIC_NUDGE（陌生人
  冷却→SILENCE）；琐事+陌生人永远 SILENCE。实测：老王借款与凌晨
  深睡突发早搏均毫不犹豫直言，琐事零打扰。

### Agent-09 共生顾问

- `ActionableAdvice` 契约：≥1 个 pinned ObjectRef 因果指针；套话
  黑名单正则（保持心态/为您推荐以下/希望这些建议/请咨询专业人士/
  温馨提示/仅供参考不构成）headline 或 rationale 命中即 ValidationError。
- 三顾问全部证据驱动，缺任一环证据即 `MissingEvidenceError` 拒答：
  送礼四件套（2023 丝巾→2024 足浴盆+倒水腰疼→2025 按摩椅好评→
  2026 膝盖受凉）→ 轻便膝盖热敷仪；反诈（生效判决 + 两年前微信借款）
  → 拒借 + 支付令/诉讼追偿指针；疲劳熔断（≥2 次通宵 × 室性早搏）
  → p0 强制停工。

### Agent-10 千人千面大考场

- 世界发生器：3 人设 × 3 年 × 3 流/日 = **34,092 条**高熵观测；
  `zlib.crc32` 确定性种子，跨 PYTHONHASHSEED 逐位一致。
- 考场 8 轮复检：1-3 轮三路径对比观察（付全量通读学费），第 4 轮起
  黄金经验直取。
- 全马实测（token_budget=2,000,000）：
  - `FrugalMindAgent`：**PASS**，tokens 655,615（usage 0.328），
    hit 1.0，manner 1.0，违宪 0；
  - `WastefulMindAgent`：**NEEDS_TRAINING**，manner 0.3（琐事吱声、
    欺诈只微震），Token 消耗 ≥2.5× frugal；
  - P0 调大模型探针注入 → 立即 **VETOED**（一票否决实测）；
  - 历史篡改探针：检索总线无 update/delete/remove/rewrite 面。
- 《AIOS 3.0 共生心智操作全景体检报告》json 持久化往返一致。

## 回归基线

- 交付全程全仓回归 **787 passed / 0 failed**（含批次 1/2 存量 707 +
  本批 39 项 + 并行战队 SIM-001 合入项）。
- push 纪律：每单提交前 `git fetch` 核对远端，rebase --ff-only，无 force。
