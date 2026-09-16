# [M0-024] LifeChapter 契约冻结（修订：Summary 已在 M0 注册表，本任务补人生章节）

## 目标
第 29 条人生章节一等对象落地：可追溯的章节基线、相变证据、封章理由。

## 输入/输出契约
新增 `LifeChapter`（prefix lfc）：`chapter_title`、`baseline_refs[]`（承载的维度/总结引用）、`transition_evidence_set_refs[]`（相变判定依据——第 77 条：判定由 AI 在唤醒会话中形成并附证据，触发器不得代判）、`supersedes_chapter_id`、`sealed_reason`（status=sealed 时必填，after-validator 已冻结）。
**勘误记录**：R4 设计书 D4 原判定"Summary 未冻结"有误——`contracts/registry.py` 已含 Summary/OperationExperience/ToolProposal；真实缺口为 Prediction/LifeChapter/CommunicationExperience/Reinterpretation 四项。

## 禁止修改 / 必须测试
- 禁止把相变判定硬编码进内核（第 29 条去参数化）；封章缺理由必须拒写（已测）。

## 遗留工作
- M3-005：sealed 状态与 Summary STALE 联动；M4 V35 相变场景判分

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
