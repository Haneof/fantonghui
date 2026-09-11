# AIOS Acceptance V1.4

## A. Data integrity

- [ ] 每条 Observation 有 timestamp/source/provenance。
- [ ] 原始 Observation 不被 Inference Event 覆盖。
- [ ] 所有关键对象都能回到 Global Timeline。

## B. Trigger

- [ ] Trigger 只做机械检测和唤醒。
- [ ] Trigger 不输出“这是谈判/焦虑/家庭冲突”等语义结论。
- [ ] Safety Trigger 可以绕过普通预算。

## C. AI

- [ ] AI Session 能按任务读取不同范围。
- [ ] Inference Event 带 supporting observations。
- [ ] UNKNOWN / INFERRED / CONFLICT 不会被静默当成 KNOWN。

## D. Identity

- [ ] Unknown ID 可先存在。
- [ ] 后续确认可以重新绑定。
- [ ] 原始 Unknown 记录不被覆盖。

## E. Action

- [ ] 高风险动作经过权限/确认。
- [ ] Outcome 回流 Timeline。
- [ ] Outcome 可供后续 Self Update 使用。

## F. UI

- [ ] UI 不拥有自己的 Memory/Timeline/AI。
- [ ] 3D/UI 可由 Mock OS State 驱动。
- [ ] 后续替换为真实 Runtime 时无需重写 UI 核心交互。

## G. Architecture gate

任何新增代码如果无法明确属于 Observation / Timeline / Dimension / Trigger / AI / Capability / Interaction / Outcome 中的一环，必须先说明为什么存在，禁止随意增加新的平行 Runtime。
