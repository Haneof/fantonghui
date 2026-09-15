# AIOS 总工程师审查档案

本目录保存 AIOS 各开发任务的正式工程审查记录。

规则：

- reviews/ 记录“为什么某项任务通过或被打回”
- `reviews/M0/` 保存开发任务级评审；`reviews/architecture/` 与 `reviews/constitution/`
  保存架构级（宪法/契约级）评审及其证据，其裁决针对文档与契约，
  不得被引用为任何开发任务的 FINAL_PASS
- 同一对象存在多份架构评审时，以 `reviews/architecture/AIOS_V3_MULTI_REVIEW_META_AUDIT_NO_GO_2026-09-16.md`
  的统一元裁决为准；后到的评审必须声明与既有档案的收敛/增量关系，不得另立裁决口径
- **派单编号唯一来源 = 文件，不是文档**：`governance/issue_registry/v3_issue_registry.json`。
  同一 `M*-***` 号段已被 **5 套方案**重复分配（D+统一母表 / E / F+P3 / P1 / P2），实际争用面 **66 个号**
  （交叉矩阵见 `reviews/architecture/AIOS_V3_UNIFIED_BACKLOG_AND_AS_BUILT_VERIFICATION_2026-09-16.md` §9.2）。
  规则：①**任何评审/方案文档都不得自我宣告编号唯一性**，只能向 registry 提交候选 slug；
  ②派单必须携带 `slug` + `source_docs`，号仅作显示；③`governance/issue_registry/check_issue_registry.py`
  （临时号 `NUMCI-001`）为 CI 门，当前实跑 **GATE = RED**（CONFLICT 39 / UNRATIFIED 21），
  **转绿之前禁止按任何一套号位开工**；④裸 `V` 前缀与 `GAP-` 前缀停用（前者被 5 套语义占用，
  后者被两份报告双占用），审计发现用 `V3G-*`、工程任务用 `M*-*`，两者以 `traces_to` 关联
- **性能数字唯一来源与三态规则**：Issue 验收只允许引用该文件 §5.2「可引用数字表」（as-built 探针与
  A 的 3.6M 探针，脚本+输出+日志+SHA256 均已入库）。三态见其 §9.4：**可引用**（有工件）／
  **可复现但未取证**（脚本已入库但无运行工件，如 B 的三支探针 ⇒ 暂不得写入验收，须由 `PROBE-CI-002`
  跑一次留工件后转态）／**不可引用**（仅正文数字，永久替换）
- 宪法/R1/R2/架构规格仍以仓库根目录正式文件为唯一权威
- reviews/ 不修改系统定义，只保存工程裁决
- 每个重大任务至少保留 PATCH_REQUIRED / FINAL_PASS 等关键审查记录
- 不允许开发代理自行伪造 FINAL_PASS
- FINAL_PASS 只能依据项目总工程师明确裁决创建
- 测试输出、review packet等证据放入对应 milestone/evidence 目录
