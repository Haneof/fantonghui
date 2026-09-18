# AIOS 3.0 Runtime Realignment — Final Architecture Audit

> 日期：2026-09-18  
> Repository：`Haneof/fantonghui`  
> 正式主线起点：`aios-2.0 @ c0f2bc26528cf35c65994d9223b3b424be526e68`  
> 审计分支：`arena/architect-runtime-realignment-20260918`  
> 最后代码 Gate 候选：`90b13abf93bb82e100e5580621349f0deca307d6`  
> GitHub Actions：`35302643287` — **SUCCESS**

## 1. Final Verdict

**MERGE PASS — Constitutional Runtime Realignment complete for this scope.**

该结论只表示：
- 现行 production 认知入口已经从规则脑/legacy one-shot 路径切向 R5/R6 模型驱动 Runtime；
- 本轮识别的 merge blockers 已修复；
- exact-SHA 全量测试与 reference contract suite 全绿。

该结论**不表示 AIOS 3.0 全功能完成**。完整 Capability Surface、Cognitive Arena 2.0、legacy cognitive threshold 全量迁移仍是下一阶段工作。

## 2. Gate Evidence

### Exact SHA
`90b13abf93bb82e100e5580621349f0deca307d6`

### CI
GitHub Actions run `35302643287`：
- `1537 passed, 10 skipped, 0 failed`
- reference contract suite：`15 passed, 0 failed`
- conclusion：`success`

### Branch topology
审计时：
- `aios-2.0 = c0f2bc26528cf35c65994d9223b3b424be526e68`
- realignment branch = `90b13abf93bb82e100e5580621349f0deca307d6`
- branch：ahead only，无 behind；可 fast-forward。

## 3. Blockers Found and Resolved

### B1 — Runtime Policy 仍保护旧法
发现：
- constitution baseline 未登记 R5/R6；
- deep lane 只能由用户显式请求；
- P0 被错误表达成“全程 0 LLM”；
- 四步 Cockpit 仍被机器政策当强制心智清单；
- 3句/90字/说教黑名单仍是硬风格门。

处理：
- `governance/runtime_policy.json` 升为 v1.1.0；
- 区分 Hard Boundary / Engineering Parameter / Cognitive Policy；
- P0 改为“首硬件动作前 0 LLM / 0 World，之后允许受控认知研判”；
- deep lane 允许 AI 因 evidence insufficiency / task complexity 主动进入；
- fixed thought order / fixed sentence cap / semantic blacklist 退出合法机器政策。

### B2 — Search / Recall 仍替 AI 做语义裁决
发现：
- `search.py::derive_dimension()` 通过“心率/借款/母亲/代码”等关键词直接宣布维度；
- object type boost 把结构类型变成认知重要性；
- retrospective annotation 获得固定最高解释权；
- CoOccurrenceRecallBus 内置人工世界同义词表；
- `min_coverage=0.5` 作为默认相关性门槛。

处理：
- 维度只投影**显式 world metadata**，缺失时 `dim_unclassified`；
- search score 只表示检索命中证据；
- annotation 作为 companion evidence，不获得固定语义 supremacy；
- production 无内置世界 expansion 表；
- coverage cutoff 变为调用方/Policy 可选 hint，默认不替 AI 切候选。

### B3 — Worker 默认门面仍指向 Legacy CockpitExecutor
发现：
- 新 `CognitiveExecutor` 已存在，但 `ai_worker.__init__` 顶层仍公开 Legacy `CockpitExecutor` 与 brevity compatibility shim。

处理：
- `CognitiveExecutor` 成为 `ai_worker` 正式顶层执行入口；
- Legacy CockpitExecutor 只保留显式模块迁移入口；
- `src/ai_worker/brevity_guard.py` 物理删除；
- 所有相关测试迁到非破坏式语义保证，不恢复旧 shim。

### B4 — Mutation Gate 继续“保护废法”
发现：
- `tests/policy/test_policy_gate_regression.py` 仍把“步骤重排、删固定句数上限、清空说教词表”等当成违宪突变。

处理：
mutation tests 改为攻击真正的 R5/R6 红线：
- 重新强制 fixed thought order；
- 禁止 AI 自主重排/跳过认知路径；
- 允许 programmatic semantic rewrite / truncation；
- 恢复 fixed sentence/char cap；
- 恢复 semantic keyword blacklist；
- 拿走 AI length ownership；
- 允许 durable policy 无证据/版本/rollback 修改。

## 4. Production-Path Rule-Brain Audit

对正式 Runtime / Worker / Search / Communication 关键文件定点扫描后，以下旧模式在当前主路径中未发现：
- `生死死党` / `损友僚机`
- trust score 人格/关系裁决
- `AdviceGate` / `PLAYBOOKS`
- anti-preach regex / natural-language blacklist
- `DEFAULT_SEED_EXPANSIONS`
- production `min_coverage=0.5`
- `no_step_may_be_omitted`
- `order_strictly_enforced`

物理不存在的旧文件：
- `src/aios_core/cognition/self_reflection.py`
- `src/aios_core/storage/ai_self_store.py`
- `src/ai_worker/brevity_guard.py`

## 5. Primary Runtime Now

正式 AI Worker 路径：

`CognitiveExecutor`
→ `CognitiveRuntime`
→ model selects `ModelDirective`
→ `CapabilityRegistry`
→ deterministic capability execution / authorization / budgets / audit
→ model receives structured results
→ model responds / silences / continues tools
→ durable raw turn + optional working-state / AI-self / policy writes

这条链的关键性质：
- Runtime 不要求固定 WAKE/ORIENT/RECALL 私有思维顺序；
- capability history 可审计，但不记录私有 chain-of-thought；
- deterministic layer 管权限、资源、事务、重复调用与 side effect authorization；
- high-level relevance / interpretation / response belongs to model。

## 6. Non-Blockers / Deferred Work

### D1 — Full R5 Capability Catalog incomplete
当前已具备：
- search_world
- search_timeline
- focus_entity
- retrieve_original_observation
- inspect_evidence
- compare_claims
- update_conversation_state
- record_ai_self_memory
- update_cognitive_policy

仍应补：
- follow_relation
- richer expand_recall
- controlled commit_claim
- controlled commit_event
- inspect_ready_tasks
- controlled action execution + receipts

### D2 — Legacy DimensionEvolution
`src/aios_core/dimensions/evolution_guard.py` 仍保存历史 2域/3天/30天/70% 等实验阈值。  
当前确认它**未接入 R5 CognitiveRuntime / AI Worker 正式主链**，所以不是本轮 merge blocker。

裁决：
- 标记 legacy/offline experimental；
- 在迁入 R6 Cognitive Policy Registry 前，不得重新接生产链。

### D3 — Cognitive Arena 2.0
现有 deterministic/adversarial testing infrastructure 可继续复用，但：
- independent semantic judge
- sealed truth
- driver/judge separation
- counterfactual fork
- long-life multi-agent simulation

仍需下一阶段完成。

## 7. Merge Condition

满足以下条件即可 fast-forward `aios-2.0`：
1. 最终治理 closeout commit 不改变 production semantics；
2. closeout exact SHA 的 CI 再次 SUCCESS；
3. 合并前再次确认 `aios-2.0` 未从 `c0f2bc...` 漂移，或重新做 compare/rebase 审计。

本报告建议：**满足以上 3 条后直接 fast-forward merge。**
