# AIOS 3.0 Constitutional Runtime Realignment — 作战规划

> 日期：2026-09-18  
> 基线：`c0f2bc26528cf35c65994d9223b3b424be526e68`  
> 施工分支：`arena/architect-runtime-realignment-20260918`  
> 目标：停止继续堆叠“假认知”功能，保留可靠 World/Search 底座，清理违宪规则脑，修复时间/来源/幂等正确性缺陷，并补齐 R5/R6 要求的 AI Cognitive Runtime、Conversation Working State、AI Self World 与 Cognitive Policy Registry。

## 0. 总原则

1. **保留并保护 Data Plane**：SQLiteWorldStore、版本、引用、证据链、全局时间轴、墓碑、索引水位、CJK/别名检索不做无必要重写。
2. **Search 负责找候选，不替 AI 决定真相**：关键词、实体、时间、关系、索引和确定性 routing hint 可以存在；最终相关性、重要性、是否继续下钻由 AI 决定。
3. **Runtime 给 AI 方向盘，不成为第二个规则脑**：程序负责能力、边界、工具执行、事务、审计和资源控制；模型负责理解、判断、联想、取舍、表达和是否继续追忆。
4. **历史不可倒写**：新认知以新 Claim / Reinterpretation / Summary / Experience / Reflection 向前演进。
5. **认知策略不是硬编码真理**：属于 R6 Cognitive Policy 的阈值、权重、风格和召回策略必须版本化、带证据、可回滚。
6. **不得用“旧测试必须绿”作为违宪代码回滚理由**：旧测试与 R5/R6 冲突时，更新测试语义并保留真正的确定性回归约束。

## 1. G0 — 法统唯一化与治理清理

### 必做
- 更新 `docs/constitution/README.md`，登记 v3.0、v3.0.1 ADJ、R5、R6 的现行解释关系。
- 新建 `governance/normative_versions/registry.md`，形成机器/Agent 可读的现行规范注册表。
- 明确 R4 未批准部分不得自动拥有现行最高法效力；被后续正式法统吸收的语义以新法为准。
- 清理“大模型自主物理删除”等与 ADJ-004 冲突的治理表述。
- 更新 `governance/runtime_policy.json` 的 constitution baseline，并标记认知策略项后续迁入 R6 Policy Registry。

### Gate
- 任意新 Agent 只需读 registry 即可得到唯一法统优先级。
- 不再存在“LLM 可直接物理删除”的正式治理口径。

## 2. G1 — 恢复 CI 与废法测试清理

### 必做
- 修复当前 2 个失败：
  - Cockpit 四段是稳定布局，不是固定思维顺序；保留字段兼容，不再锁定旧文案。
  - 删除 V30 对 1~3 句/60 字/序数词正则清洗的强制断言，改为“不得破坏模型语义”。
- 新增 R5/R6 constitutional regression：
  - brevity guard 不得破坏语义；
  - 不得默认预设“生死死党/损友僚机”；
  - 不得强制固定 thought order；
  - Cognitive Policy 不应作为不可审计常量继续扩散。

### Gate
- `pytest` 全绿。
- reference contract suite 全绿。
- 当前分支 CI 重新 GREEN。

## 3. G2 — 世界正确性 BUG 修复

### P0-1 AS_KNOWN 双时态
- `AS_KNOWN(as_of=T)` 必须以 `learned_at <= T` 为知识可见性必要条件。
- `occurred_at/valid_time` 仅描述世界何时发生，不得替代“当时是否已知”。

### P0-2 Observation 三时间分离
- `occurred_at`：现实发生时间。
- `learned_at`：AI/系统首次获知时间。
- `recorded_at`：写入时间。
- Simulation feeder 不得默认把补录历史事件伪装成历史时已经知道。

### P0-3 来源分类
- MIC/CAMERA/APP 不得默认归类为 `AI_COGNITION`。
- 扩充或明确 SourceClass 的 perception/app/external 语义，并保持旧值兼容。

### P0-4 Ingest replay identity
- 删除随机 UUID 作为原始流幂等身份的做法。
- 幂等 identity 至少稳定绑定 subject/source/occurred/content canonical digest。

### Gate
- “三年前发生、今天才知道”在去年 AS_KNOWN 不可见，今天可见。
- 同一原始流 replay 两次不能产生重复写入语义。
- MIC/CAMERA/APP 不再冒充 AI_COGNITION。

## 4. G3 — Rule Brain 清理

### 退出 production 认知权
- `StreamingExtractWorker._default_heuristic_extract`
- `ProactiveAssociativeRecall` 固定 `0.95` 相关度
- Search `derive_dimension()` 的关键词语义判定（降级为 routing hint 或迁出正式认知语义）
- `self_reflection.py` 的 trust score 阶梯、关键词触发人格/介入
- `CommunicationStyleGovernor` 的认知型正则判断与固定话术替换
- `ExperienceTracker` 的固定 `0.5` 认知阈值作为永久真理

### 保留
- ActiveRollingWindow
- 异步队列与 watermark
- Action/Evidence/CommunicationExperience 持久化
- CJK/index/alias/time/tombstone/search watermark

### Gate
- 无模型认知能力时宁可只保存原始证据，也不得伪造“已经理解”。
- production 关键路径不再由关键词直接宣布情绪、关系、重要性或回复内容。

## 5. G4 — AI Cognitive Runtime / Executive Plane

### 新建核心
- `CapabilityRegistry`
- `WorldCapabilityBus`
- `CognitiveRuntime`

### 最小能力集
- `search_world`
- `search_timeline`
- `focus_entity`
- `follow_relation`
- `retrieve_original_observation`
- `inspect_evidence`
- `compare_claims`
- `expand_recall`
- `commit_claim`
- `commit_event`
- `record_communication_experience`
- `record_ai_self_reflection`
- `inspect_ready_tasks`
- `execute_capability`
- `respond`
- `silence`

### 执行协议
`WAKE -> minimal cockpit -> MODEL -> tool call? -> execute -> MODEL -> ... -> respond/act/silence -> commit -> optional reflect -> sleep`

注意：这是能力循环，不是要求模型输出固定思维链。Runtime 只管理工具循环、预算、错误、审计和终止条件。

## 6. G5 — Conversation Working State / 长会话闭环

正式建立：

`Raw Turn Timeline + Active Window + ConversationWorkingState + Multi-scale Summary + Long-term Cognition`

Working State 至少包含：
- current topic
- topic branches
- open loops
- unresolved questions
- commitments / promises
- key raw-turn refs
- relevant entity refs
- evidence refs
- version / updated_at

所有摘要/状态必须可追溯原始 Turn，不得替代或删除原始对话。

## 7. G6 — AI Self World 重建

废除“游戏属性条式 AI”：不再以共情=80、克制=85、死党=100 作为核心模型。

正式 AI Self World 以以下对象为主：
- Identity / Principle / Boundary
- Relationship Understanding
- Belief / Understanding
- CommunicationExperience
- OperationExperience
- Commitments
- SelfReflection
- PolicyLearning

所有变化记录 reason、evidence、previous version、learned_at、rollback/retraction 语义。

## 8. G7 — R6 Cognitive Policy Registry

实现可审计策略结构：

```text
policy_id
scope
class
default_value
current_value
allowed_range_or_choices
mutable_by_ai
reason
evidence_refs
changed_by
changed_at
version
previous_version
rollback_pointer
evaluation_window
```

优先迁移：
- recall expansion / stopping policy
- communication verbosity/style
- intervention policy
- reflection trigger policy
- ranking boosts
- relationship communication strategy

## 9. G8 — Cognitive Arena 2.0

保留现有 Arena 基础设施，但重新解释 PASS：
- deterministic judge 只判客观约束；
- independent semantic judge 判认知质量；
- sealed ground truth；
- counterfactual forks；
- driver model 与 judge model 分离；
- 主指标：Recall@K、False Recall、Unsupported Memory、Stale Belief、Open-loop Recovery、Cross-session Continuity、Contradiction、Latency、Token、Tool Loop、Commit Correctness。

## 10. G9 — 最终废代码物理删除与总回归

只有在替代路径稳定、引用为零、测试迁移完成后才物理删除：
- destructive `brevity_guard` 兼容壳
- `allow_expansion` 兼容参数
- 旧 rule-brain classes/functions
- 旧废法 tests
- 无调用的旧 AI Self/rapport 策略实现

最终要求：
- 代码与法统一致；
- progress 文档由真实 Gate/CI 结果生成或至少引用 exact SHA；
- 不再用“文件存在/测试数量”冒充功能已经接入生产运行链。

## 11. 施工顺序冻结

```text
G0 法统唯一化
 -> G1 CI 绿
 -> G2 世界正确性 BUG
 -> G3 Rule Brain 清理
 -> G4 Cognitive Runtime
 -> G5 Conversation Working State
 -> G6 AI Self World
 -> G7 Cognitive Policy Registry
 -> G8 Arena 2.0
 -> G9 删除与终审
```

**G4 完成前禁止继续堆叠新的“聪明模块”。**