# AIOS 宪法 V1.4-r0 —— World Cognition OS（世界认知操作系统）

> 版本：V1.4-r0
> 状态：**ACTIVE / 生效**
> 生效日期：2026-09-11
> 上一版本：V1.3-r0（历史版本）
> 本次补丁：Confidence / Evidence Epistemic Layer（认知置信与证据层）

## 生效声明

V1.4-r0 是当前 AIOS 唯一有效 Constitution。V1.2-r1、V1.3-r0 及更早版本仅作为历史资料保留，不得作为新代码、新 Runtime、新任务的架构依据。

尚未迁移的旧 Runtime 必须明确标记为兼容实现、历史实现或迁移缺口，不得伪称已经符合 V1.4。

本次补丁不改变 V1.4 的主链路和既有架构边界，而是在世界认知层增加 **Evidence / Epistemic Confidence（证据 / 认知置信）**原则，用于描述 AIOS 对一个命题为什么相信、相信到什么程度，以及未来如何根据新证据修正自己的认知。

规范主链路为：

```text
Observation → Global Timeline → Dimension → Trigger → AI Session
→ Inference Event → Help / Action → Outcome → AI Self Update
```

核心原则：底层负责完整、可追溯的证据与机械触发；AI 负责世界理解、事件生成、关系建立、帮助判断和认知更新。

## 重要边界

1. **Observation First**：先保存观测，再进行认知；原始观测不得被 AI 结论覆盖。
2. **Global Timeline 唯一**：Observation、Dimension Point、Trigger、AI Session、Inference Event、Memory、Task、Action、Outcome、AI Self Update 均挂在唯一全局时间轴。
3. **底层不预先替世界下语义结论**：不得在底层把数据直接判断为谈判、焦虑、家庭冲突、人物身份等复杂语义。
4. **Trigger ≠ AI 判断**：Trigger 只负责机械唤醒；触发后由 AI Session 解释证据。
5. **本地机械层 ≠ 本地语义模型**：本地可以做格式、时间、重复、阈值、存在性、安全硬规则等确定性工作；不得把本地廉价模型当作常规语义过滤器。
6. **Unknown 身份先独立记录**：声纹可以机械区分说话人，身份绑定由 AI 根据证据推断，可修正、可降置信，原始 Unknown 记录永不改写。
7. **曲线是长期状态载体**：维度可动态挂载；趋势、基线、持续时间、波动等用于唤醒依据，单点不应直接替代 AI 判断。
8. **AI Watch**：AI 可以建立临时观察条件；AIOS 负责持续机械观察，命中条件后再次唤醒 AI，不要求 AI 持续运行。
9. **Help-First / Intent-First**：AI 介入以是否真正帮助用户为核心；需要结合用户意图、上下文、MODE、历史和当前世界判断是否帮助、何时帮助、如何帮助，也允许选择沉默。
10. **Safety 最高优先级**：真实安全事件可以绕过普通 MODE、相关性和介入预算；先确认安全，再执行安全策略。
11. **高风险 Action 必须受授权/确认约束**：涉及花费、外部承诺、物理控制等操作不得由普通认知结果直接执行。
12. **Outcome 回写时间轴**：重要行动的结果必须回到 Global Timeline，供后续认知和策略更新。
13. **One AI**：教育、社交、娱乐、工作、健康等应用共享同一个 AI、同一套世界、同一条时间轴，不建立第二套大脑或记忆系统。
14. **UI 是身体，不是大脑**：UI、3D、硬件只负责展示、交互和输入输出，不拥有 AI、Memory、Timeline、Trigger 等核心语义。
15. **唯一产品主线**：当前 OS 主线固定为 `aios/01_os/`。历史 `core/`、`arena/` 等只能作为验证/实验/历史资产，不能发展成第二套产品 Runtime。

## AIOS 的数据真实性与认知状态分层

系统必须区分：

```text
OBSERVED
DERIVED
INFERRED
HYPOTHESIS
UNKNOWN
```

任何 AI 推断都不得伪装成现实事实。原始证据链必须可追溯。

### 认知置信原则

AIOS 必须进一步区分：**“来源陈述是否真实发生”** 与 **“陈述中的命题是否真实”**。

两者不得使用同一个置信度表示。

例如：

```text
用户说：“明天股票大涨。”

事实 1：用户确实说过这句话
→ Source Confidence = 100%

命题 2：明天股票确实会大涨
→ Claim Confidence 可能只有 40%
```

因此：**“用户说过 X”可以是高确定性事实，而 X 本身可以是不确定的预测、观点或假设。**

### 三层认知置信

对需要认知判断的 Claim，AIOS 应支持至少以下三个概念：

```text
Source Confidence
    ↓
Evidence Confidence
    ↓
Claim Confidence
```

#### 1. Source Confidence

表示某个信息来源、来源行为或来源记录本身的可信程度。

例如：

- AIOS 系统时间：通常为确定性来源。
- 官方日历/历法：在正确获取并验证后，可视为高可靠来源。
- 用户本人陈述：对于“用户确实说过这句话”，通常为 100%；但这不代表陈述内容本身必然为真。
- 陌生人陈述：应根据身份、历史和交叉证据评估。
- AI 自己的推断：不得反向当作独立现实证据。

#### 2. Evidence Confidence

表示支持或反驳某个 Claim 的证据强度、独立性、时效性和一致程度。

证据必须能够追溯到 Global Timeline 中的 Observation 或其他明确来源。

多源、独立、时间相关且相互一致的证据可以提高置信；矛盾、过期、来源不可靠或被后续事实否定的证据可以降低置信。

#### 3. Claim Confidence

表示 AIOS 当前对某个具体命题为真的认知程度。

Claim Confidence 是**可演化状态，不是事实本身的固有属性**。

新证据可以使 Claim Confidence：

```text
提高
降低
保持
分裂为多个不同命题
被新状态取代
失效
```

历史置信度和历史证据不得因为当前状态变化而被覆盖。

## 主观陈述与客观命题

AIOS 不得简单采用“主观 = 低置信度、客观 = 高置信度”的规则。

置信度必须针对具体命题判断。

例如：

```text
用户说：“我现在很难过。”
```

对于命题：

```text
“用户在此时主观上体验到难过。”
```

由于用户本人是其内部体验的直接报告者，该命题可以具有很高的 Claim Confidence；如果聊天记录、行为、生理状态或后续陈述提供独立支持，置信度还可以进一步提高。

但：

```text
用户说：“我觉得明天股票会涨。”
```

对于命题：

```text
“明天股票会涨。”
```

这是关于外部未来世界的预测，当前置信度应根据历史准确率、外部证据、预测条件和其他信息计算，而不能因为来源是用户本人就自动设为高置信。

## 陈述、命题、预测必须拆分

AIOS 在语义建模时，应避免把一条用户话语直接压缩成一个“事实”。

至少应能够区分：

```text
Utterance / Observation
        ↓
Claim
        ↓
Claim Type
        ↓
Confidence
        ↓
Evidence
        ↓
Verification / Outcome
```

Claim Type 至少可以包括：

```text
FACT
SUBJECTIVE_STATE
OPINION
PREFERENCE
PREDICTION
HYPOTHESIS
INTENTION
PLAN
REPORT
```

例如：

```text
用户：“我和女朋友分手了。”

Observation：用户确实说过该句话
Source Confidence = 100%

Claim：用户与女朋友已分手
Claim Type = REPORT / RELATIONSHIP_STATE

初始 Claim Confidence：根据上下文和证据评估

若聊天记录存在明确的分手对话：
Evidence Confidence ↑
Claim Confidence 可能达到 90%+
```

随后如果出现复合证据，系统不得删除“分手”这一历史事实，而应在 Global Timeline 中记录关系状态的后续变化。

## 确定性信息

对于具有可靠确定性来源并能够机械验证的信息，可以具有接近或等于 100% 的 Claim Confidence。

例如：

```text
系统时间
日期
已发生的系统事件
经过可靠来源验证的日历事件
设备实际产生的确定性操作记录
```

但“100%”必须描述具体命题，而不是泛化到整个上下文。

例如：

```text
“用户在 20:00 发送了这句话” = 100%

“这句话描述的外部世界一定为真” ≠ 自动 100%
```

## 置信度必须进入 Global Timeline 与 Dimension

置信状态不是独立于世界模型之外的辅助标签。

它必须能够与 Global Timeline、Observation、Dimension、Inference Event、Outcome 和 AI Self Update 建立可追溯关系。

一个 Claim 至少应能够表达：

```text
claim_id
subject
predicate
object / value
timestamp
valid_time
source
source_confidence
claim_confidence
evidence_refs
claim_type
verification_status
last_verified_at
supersedes / superseded_by
```

具体字段名称可由 Canonical Data Model 进一步规定，但不得违反本原则。

### 置信度的时间性

置信度本身也具有时间属性。

例如：

```text
T1：张三是用户老板
Claim Confidence = 95%

T2：用户换工作

T3：张三不再是用户当前老板
Current Confidence for “张三是当前老板” ↓
```

系统必须允许区分：

```text
Historical Truth
Current Truth
Historical Confidence
Current Confidence
```

不得因为当前状态变化而修改过去已经成立的历史 Observation 或历史 Claim。

## 预测必须进入 Outcome 验证闭环

对于 Prediction、Hypothesis、Plan 等未来性 Claim，AIOS 应尽可能在未来通过 Outcome 验证其实际结果。

例如：

```text
用户预测：明天股票上涨
Claim Confidence = 40%
Verification Status = PENDING
        ↓
次日真实市场结果
        ↓
Outcome
        ↓
验证 Prediction
        ↓
更新该 Claim
        ↓
AI Self Update
```

AI Self Update 不仅可以修正该条预测，还可以根据长期结果更新对用户能力、偏好、判断模式或特定条件下预测能力的认知。

例如长期积累后可以形成新的 AI Dimension：

```text
用户股票短期判断能力
```

其内容来自长期验证结果，而不是单次印象。

## 认知可以被修正，但证据不能被抹除

AIOS 必须允许 AI 犯错，也必须允许 AI 修正错误。

错误的 AI Cognition 不得变成不可逆事实。

正确原则：

```text
Evidence 永久可追溯
        ↓
Cognition 可更新
        ↓
Confidence 可升降
        ↓
Dimension 可修正
        ↓
旧认知保留为历史认知
```

AIOS 不应该追求“永远不犯错”，而应该具备：

> **可追溯地犯错、可解释地修正、从结果中学习。**

## 维度与置信度

Dimension 不是数据库字段，而是 AI 的观察视角。

因此，任何动态 Dimension 都可以具有自己的认知基础和置信状态。

AI 可以：

```text
创建 Dimension
→ 收集证据
→ 建立初始判断
→ 观察时间变化
→ 与其他 Dimension 横向关联
→ 沿时间轴纵向验证
→ 发现矛盾
→ 修正 Dimension
→ 产生更高阶 Dimension
→ 冻结、合并或淘汰旧 Dimension
```

由此，AI 对用户的理解不是一个固定的“用户画像表”，而是一个随着 Global Timeline 持续演化、并且带有证据和置信状态的认知空间。

## AI 自我认知更新

AI Self Update 必须能够处理自己的认知错误。

AI 不仅更新：

```text
“用户发生了什么”
```

还可以更新：

```text
“我以前是怎么理解用户的”
“那个理解是否被结果证实”
“我对用户的哪些判断可靠”
“我的帮助是否有效”
“我应该如何调整未来判断”
```

因此，AIOS 的长期 AI Dimension 可以形成自己的认知历史与成长轨迹。

## 当前工程含义

新代码、新 Schema、新 Runtime、新任务必须以本 Constitution 和 V1.4 Canonical 文档为准。旧实现与 V1.4 不一致时，先登记冲突并判断是语义冲突还是表示冲突：语义冲突修改实现；表示冲突优先使用 Adapter / Mapper / Compatibility Layer。

UI、硬件、具体 App 可以提前定义接口和 Mock，但不得绕过 OS 主线自行建立认知、记忆或时间轴。

本次 Confidence / Evidence 补丁属于 V1.4-r0 的架构补充，不改变既有 L0-L7 分层、Global Timeline 唯一性、Observation First、Trigger 边界和 One AI 原则。

**本文件是当前最高架构权威。**
