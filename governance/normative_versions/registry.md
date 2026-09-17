# AIOS Normative Version Registry

> 状态：ACTIVE  
> 最后更新：2026-09-18  
> 施工基线：`c0f2bc26528cf35c65994d9223b3b424be526e68`

本文件是 AIOS 运行时、测试、Agent 派工和审计解释“当前到底以哪套规范为准”的唯一注册入口。它不替代正文，只登记生效状态、解释优先级与冲突裁决规则。

## 1. 当前生效规范栈

| Priority | Normative document | Status | Scope / authority |
|---:|---|---|---|
| 1 | `docs/constitution/AIOS核心系统宪法v3.0.md` | ACTIVE | 主宪法与基础原则 |
| 2 | `docs/constitution/v3.0.1_规范裁决集_ADJ-001-012.md` | ACTIVE | 对主宪法歧义/冲突的正式裁决；同一事项优先采用裁决后的解释 |
| 3 | `docs/constitution/AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md` | ACTIVE | Executive Plane、AI 驾驶权、主动 Recall/Search/Follow/Compare/Commit 的正式增补 |
| 4 | `docs/constitution/AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md` | ACTIVE | Hard Boundary / Engineering Parameter / Cognitive Policy 分层及认知阈值治理的正式增补 |

**冲突规则**：在同一规范层级内，后生效且明确处理同一事项的正式裁决/修改案优先于旧表述；R5/R6 不取消主宪法的数据完整性、安全、权限、历史不可篡改等硬边界。

## 2. 解释优先级

当代码、测试、治理表、注释或旧设计存在冲突时，按以下顺序解释：

```text
现行正式法统正文（上表）
  > 正式机器可读 policy 中与法统一致的硬边界/工程参数
  > 当前批准的工程规格
  > 历史测试/历史进度表/历史注释
  > 未批准候选设计
```

“测试曾经是绿的”不构成恢复已被后续法统废止行为的理由。

## 3. 已明确的现行裁决

### 3.1 AI Cognitive Runtime

- World / Data Plane 负责保存事实、认知对象、时间、版本、证据与历史。
- Search / Recall Plane 负责找到可能相关的世界切片。
- AI Cognitive Runtime / Executive Plane 负责让 AI 自主选择是否继续搜索、追关系、比较主张、查看原始证据、回应、行动、沉默、写回和反思。
- 程序不得用固定关键词、固定心理状态机、固定人物关系分数或固定话术替 AI 完成高阶认知。

### 3.2 Cockpit

`step1/step2/step3/step4` 可以为了布局、缓存和序列化兼容继续存在，但不是强制思维顺序。不得通过测试或 Prompt 要求模型按固定次序输出思考过程。

### 3.3 回复长度与风格

“1~3 句”“60 字”只可作为历史启发式/默认风格目标。Runtime 不得因此截断、删除、正则清洗或替换大模型已形成的有效语义。

### 3.4 删除与历史保护

LLM 可以形成清理/删除意图，但没有直接物理删除历史事实的普通认知权限。物理清理必须经过确定性的引用、保留/冻结、权限和审计门禁，再由受控执行路径完成。

### 3.5 Cognitive Policy

Recall 阈值、排序偏好、关系/沟通策略、主动介入策略、摘要/反思触发策略等若属于认知策略，不得因写入 Python 常量就获得永久法律地位。正式 Runtime 中应具有 scope、版本、证据与回滚语义。

## 4. 候选/非自动生效文件

- 明确标注“待批准”“待签发”的 R4 或其他修改案：`CANDIDATE`，不得仅凭文件存在即视为现行最高法统。
- 路线图、研究报告、Arena 题库/判卷规则、TASK_PROGRESS 等：`NON_NORMATIVE`，可作为工程证据或计划，但不能覆盖现行法统。
- 历史 R1/R2/R3：`HISTORICAL`；已被 v3 正式法统吸收的部分通过现行正文继续有效，不再作为独立最高解释入口。

## 5. 变更纪律

1. 新的正式修改案/裁决生效时，必须在同一变更中更新本 registry。
2. `governance/runtime_policy.json` 的 `constitution_baseline` 必须与本 registry 对齐。
3. 所有新 Gate 测试应引用具体法统语义，不得用历史产品偏好冒充宪法硬边界。
4. 任何 Agent 开工前，若发现本文与正文状态不一致，必须先停止新增功能并修复法统注册漂移。
