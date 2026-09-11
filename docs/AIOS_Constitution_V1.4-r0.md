# AIOS 宪法 V1.4-r0 —— World Cognition OS（世界认知操作系统）

> 版本：V1.4-r0
> 状态：**ACTIVE / 生效**
> 生效日期：2026-09-11
> 上一版本：V1.3-r0（历史版本）
> 批准依据：仓库提交 `4b451ad` 已将 V1.4-r0 设为 effective constitution。

## 生效声明

V1.4-r0 是当前 AIOS 唯一有效 Constitution。V1.2-r1、V1.3-r0 及更早版本仅作为历史资料保留，不得作为新代码、新 Runtime、新任务的架构依据。

尚未迁移的旧 Runtime 必须明确标记为兼容实现、历史实现或迁移缺口，不得伪称已经符合 V1.4。

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

## AIOS 的数据真实性分层

系统必须区分：

```text
OBSERVED
DERIVED
INFERRED
HYPOTHESIS
UNKNOWN
```

任何 AI 推断都不得伪装成现实事实。原始证据链必须可追溯。

## 当前工程含义

新代码、新 Schema、新 Runtime、新任务必须以本 Constitution 和 V1.4 Canonical 文档为准。旧实现与 V1.4 不一致时，先登记冲突并判断是语义冲突还是表示冲突：语义冲突修改实现；表示冲突优先使用 Adapter / Mapper / Compatibility Layer。

UI、硬件、具体 App 可以提前定义接口和 Mock，但不得绕过 OS 主线自行建立认知、记忆或时间轴。

**本文件是当前最高架构权威。**
