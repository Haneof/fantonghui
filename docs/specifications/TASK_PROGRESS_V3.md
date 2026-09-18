# AIOS 3.0 当前工程状态与下一阶段开发台账

> **状态日期**：2026-09-18  
> **现行法统入口**：`governance/normative_versions/registry.md`  
> **Runtime Policy**：`governance/runtime_policy.json` v1.1.0  
> **本轮起始主线**：`c0f2bc26528cf35c65994d9223b3b424be526e68`  
> **Realignment 代码候选**：`90b13abf93bb82e100e5580621349f0deca307d6`  
> **候选 Gate**：GitHub Actions run `35302643287` — **SUCCESS**  
> **测试事实**：主套件 **1537 passed / 10 skipped / 0 failed**；reference contract suite **15 passed / 0 failed**。

本文件从 2026-09-18 起替代此前“按文件存在/历史工单数量推算完成度”的进度口径。  
**只有已经接入现行运行链、受现行法统约束且有 exact-SHA Gate 证据的能力，才可写为 CLOSED。**

---

## 1. 当前真实架构状态

| 领域 | 当前状态 | 已进入正式链的事实 | 仍未完成 / 下一步 |
|---|---|---|---|
| World / Data Plane | **STABLE FOUNDATION** | SQLite world、版本/引用/证据、时间、tombstone、索引水位等确定性底座继续保留 | 后续只做缺陷修复与能力扩展，不重写基础契约 |
| 双时间 / 来源 / replay 正确性 | **REALIGNED** | `AS_KNOWN`、Observation 时间语义、来源分类、稳定 replay identity 已按本轮计划纠偏 | 继续以 adversarial regression 防回归 |
| Search / Recall Plane | **REALIGNED FOUNDATION** | Search 返回候选/检索证据；不再按关键词直接宣布健康/财务/社交维度；注记不再获得固定“最高解释权”；CoOccurrence 无内置世界同义词真理与固定 0.5 相关性门槛 | 补齐更完整的 relation traversal / expansion orchestration；认知相关性继续归模型 |
| AI Cognitive Runtime / Executive Plane | **PRIMARY PATH / FOUNDATION COMPLETE** | `CognitiveRuntime` + `CapabilityRegistry` + `WorldCapabilityBus` 已形成模型驱动工具循环；`ai_worker.CognitiveExecutor` 已成为顶层正式入口 | 继续补齐 R5 全量 capability catalog：如更完整 relation follow、受控 Claim/Event commit、ready-task/action 总线等 |
| Conversation Working State | **CONNECTED** | Raw Turn Timeline + versioned ConversationWorkingState 已进入 `CognitiveExecutor` 持久链 | 下一步补多尺度 summary / open-loop 恢复的长期 Arena 指标 |
| AI Self World | **CONNECTED FOUNDATION** | versioned AI self memory、relationship understanding、evidence refs 已进入最小 cockpit / state capability | 扩展 Principle/Boundary/Belief/Commitment/SelfReflection 的正式对象与评估，而不是恢复 score 人格条 |
| R6 Cognitive Policy Registry | **CONNECTED FOUNDATION** | 策略 version / scope / evidence / rollback 语义与 `update_cognitive_policy` capability 已接入 | 将 legacy/offline 认知阈值逐项迁入 Policy Registry；补 evaluation window 自动评估 |
| 回复风格 / verbosity | **REALIGNED** | “1~3句/60字”已回归**普通口语软偏好**；程序不得截断、正则删改、固定替换模型语义；`ai_worker/brevity_guard.py` 已物理删除 | 后续只允许 AI / Cognitive Policy 决定详略；安全硬边界另行处理 |
| Cockpit | **REALIGNED** | `step1~step4` 仅保留布局/序列化兼容，不是固定思考顺序 | 逐步减少 legacy one-shot cockpit 在新代码中的使用 |
| P0 Safety | **REALIGNED** | 首硬件安全动作前 0 LLM / 0 World；首动作后允许受控 EmergencyDialogueJudge 研判 | 保持物理直通门与认知研判的时序隔离，继续压测 |
| Legacy DimensionEvolution | **LEGACY / OFFLINE EXPERIMENTAL** | 不在 R5 Runtime / AI Worker 正式主链 | 2域/3天/30天/70% 等历史语义阈值迁入 R6 Policy 前，**禁止重新接生产认知链** |
| Cognitive Arena 2.0 | **PARTIAL / NEXT PHASE** | 既有 deterministic/adversarial 基础设施仍可复用 | 独立 semantic judge、sealed truth、counterfactual forks、长期 Life Simulation 仍需继续完成 |

---

## 2. 本轮 Realignment 已解决的核心问题

### 2.1 法统与机器政策
- 建立 `governance/normative_versions/registry.md` 作为唯一规范注册入口。
- Runtime Policy 升至 v1.1.0，对齐 v3.0 + v3.0.1 ADJ + R5 + R6。
- 删除“只有用户显式要求才允许深搜”的旧限制；AI 可因证据不足/任务复杂度主动进入 deep lane。
- 四段 Cockpit 从“必经心智步骤”降为稳定布局。
- 风格政策不再用固定句数、字符数或自然语言黑名单替 AI 决策。

### 2.2 Rule Brain 清理
- 删除 production 默认 heuristic cognition extractor。
- 删除固定 0.95 recall relevance 假分数。
- 删除 Search 关键词维度裁决、类型语义 boost、Annotation 固定最高解释权。
- 删除 CoOccurrence 内置“合伙/借贷/撕逼/妈妈/慢性病……”世界同义词表和固定 0.5 coverage 门。
- 删除旧 self-reflection / style / experience rule-brain 模块；替换路径是 evidence-backed AI Self + R6 Policy。
- 删除 destructive `ai_worker/brevity_guard.py`。

### 2.3 正式执行入口
`src/ai_worker/__init__.py` 现在公开：
- `CognitiveExecutor`
- `CognitiveExecutionResult`
- `ModelDirective`
- R5/R6 Runtime 相关公开能力

Legacy `CockpitExecutor` 仍可从显式模块导入迁移，但不再由 `ai_worker` 顶层伪装成默认执行器。

---

## 3. 当前 Gate 证据

代码候选：`90b13abf93bb82e100e5580621349f0deca307d6`

GitHub Actions：
- run: `35302643287`
- conclusion: **success**
- 主测试：**1537 passed, 10 skipped, 0 failed**
- reference contract suite：**15 passed, 0 failed**

此前中间红灯均被当作 blocker 修复，而不是通过降低现行 R5/R6 语义绕过：
- `ae63d14...`：旧 mutation Gate 仍保护废法，已迁移。
- `f630a971...` / `0557a41e...`：删除 brevity shim 后残留旧测试 import/call，已迁移。
- `90b13ab...`：最终代码 Gate 全绿。

---

## 4. 下一阶段正式开发顺序

### P0 — 补全 R5 Capability Surface
优先增加并接入真实执行链：
1. `follow_relation`
2. 更完整 `expand_recall`
3. 受控 `commit_claim` / `commit_event`
4. `inspect_ready_tasks`
5. 受控 action execution / receipt
6. capability-level permission / resource envelopes 的统一审计

### P1 — 完整认知记忆闭环
1. Multi-scale conversation summary
2. Open-loop recovery
3. contradiction / stale belief revision
4. user-world 与 AI-self-world 的 evidence-linked evolution
5. policy evaluation window 与自动 rollback 候选

### P2 — Legacy Cognitive Threshold Migration
先迁后接，不允许旧常量“原样复活”：
- DimensionEvolution 2域/3天/30天/70%
- 旧 reflection quotas
- 旧 intervention / ranking / communication thresholds

### P3 — Cognitive Arena 2.0
- Driver model 与 Judge model 分离
- sealed ground truth
- independent semantic judge
- counterfactual fork
- multi-agent simulated life
- 指标：Recall@K、False Recall、Unsupported Memory、Stale Belief、Open-loop Recovery、Cross-session Continuity、Contradiction、Latency、Token、Tool Loop、Commit Correctness

---

## 5. 进度纪律

以后禁止再写：
- “某文件存在，所以功能 CLOSED”
- “历史测试数量变大，所以认知闭环完成”
- “旧测试曾经绿色，所以旧规则仍合法”
- “一个固定阈值被写进 Python，所以它就是认知真理”

以后必须写：
- **exact branch / SHA**
- **实际 production path**
- **对应法统**
- **Gate / CI 证据**
- **尚未完成的真实缺口**
