# AIOS Acceptance V1.4-r1

## A. Data integrity

- [ ] 每条 Observation 有 timestamp/source/provenance。
- [ ] 原始 Observation 不被 Inference Event 覆盖。
- [ ] 所有关键对象都能回到 Global Timeline。
- [ ] Claim 能区分 Source Confidence、Evidence Confidence、Claim Confidence。
- [ ] 历史证据不会因当前认知变化而被覆盖。

## B. Trigger

- [ ] Trigger 只做机械检测和唤醒。
- [ ] Trigger 不输出“这是谈判/焦虑/家庭冲突”等语义结论。
- [ ] Safety Trigger 可以绕过普通预算。

## C. AI Identity Bootstrap

- [ ] 每个 AI Instance Wake 后必须先完成 Identity Bootstrap。
- [ ] Bootstrap 明确 AI Instance 身份、角色、权限、Session 和 Wake Reason。
- [ ] AI Instance 明确自己运行于 AIOS 中，而不是把自己等同于 AIOS。
- [ ] Bootstrap 未完成时禁止进入世界认知。

## D. Autonomous Cognition

- [ ] Bootstrap 后 Runtime 不强制固定 Dimension 读取顺序。
- [ ] AI 可以自主选择 User/World Dimensions。
- [ ] AI 可以自主选择 AI Dimensions。
- [ ] AI 可以进行跨维度、时间和关系查询。
- [ ] AI 可以选择继续探索、帮助或保持沉默。
- [ ] User/World Dimensions 与 AI Dimensions 共享 Global Timeline。

## E. Cognitive Continuity

- [ ] Persistent Cognition 与 LLM Context 分离。
- [ ] Session 可以生成 Cognitive Delta。
- [ ] Session 可以生成机器可读 Session Handoff。
- [ ] Context Overflow 可以自动进入 Continuation/Handoff。
- [ ] 第二个 AI Instance 能基于 Handoff + Delta + 当前变化继续，不必重读全部历史。
- [ ] 模型切换不丢失 AI Identity 和 Persistent Cognition。

## F. Identity / Unknown

- [ ] Unknown ID 可先存在。
- [ ] 后续确认可以重新绑定。
- [ ] 原始 Unknown 记录不被覆盖。

## G. Action / Outcome

- [ ] 高风险动作经过权限/确认。
- [ ] Outcome 回流 Timeline。
- [ ] Outcome 可供后续 Self Update 使用。

## H. Cognitive Optimization

- [ ] Simulator 的 Expected Intent 不进入生产 AI Context 作为答案提示。
- [ ] Simulator 可以记录结构化 Cognitive Trace / Telemetry。
- [ ] 失败可以分类为 Observation / Context / Interpretation / Mechanism / Intervention / Continuity 等层级。
- [ ] 机制修改必须通过 Regression，避免单案例修复造成其他场景退化。

## I. UI

- [ ] UI 不拥有自己的 Memory/Timeline/AI。
- [ ] 3D/UI 可由 Mock OS State 驱动。
- [ ] 后续替换为真实 Runtime 时无需重写 UI 核心交互。

## J. Architecture gate

任何新增代码如果无法明确属于 Observation / Timeline / Dimension / Trigger / Cognitive Runtime / Capability / Interaction / Outcome 中的一环，必须先说明为什么存在，禁止随意增加新的平行 Runtime。
