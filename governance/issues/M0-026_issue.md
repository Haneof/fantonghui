# [M0-026] CommunicationExperience 契约冻结（第 12/69 条）

## 目标
沟通风格进化有据可依：什么场景、什么方式、什么语气、用户真实反应、反例，一体成对象。

## 输入/输出契约
新增 `CommunicationExperience`（prefix cxp）：`scenario`、`style`、`tone`、`user_reaction`（accepted/resisted/ignored/unknown——第 11 条分寸感的原料）、`action_ref`（若关联具体干预必须 pinned）、`applicable_conditions`、`counterexample_refs`（反例不许缺席）。
OperationExperience/ToolProposal 已在 M0 冻结（见 M0-024 勘误），本任务不重复。

## 禁止修改 / 必须测试
- 禁止把一次成功升级为永久规则（第 12 条，evaluator 场景约束）
- action_ref 未 pinned → ValidationError（已测）

## 遗留工作
- M5-002：捕获管道与失效规则；V3-01 风格漂移评分（M4b）
- W6 冗长/爹味探测器输出登记为负样本（工作台规格 §4.1-W6）

## 上位依据
- AIOS核心系统宪法v3.0 + 《AIOS宪法v3.0修改案_R4.md》（本任务依赖该修改案批准；契约层已以候选契约先行冻结，gate_version=M0-R2+R4-delta-candidate）
- 详细任务书：《AIOS_Core_工程重构与任务拆分设计书_R4_首席架构师版.md》§3.4
- CAM 验收矩阵：schemas/constitution_acceptance.py

## 验收
- [x] 契约单测通过（tests/unit/test_m0_prime_contracts.py，12 用例）
- [x] Schema snapshot 无未批准变化（已按批准漂移流程再生成；见下）
- [ ] R4 修改案签核后转正（仅改 gate_version 字符串，不改字段）

## 已知限制
M0′ 只冻结契约与校验语义；运行面按设计书排入 M1/M2/M3（见下"遗留工作"）。
