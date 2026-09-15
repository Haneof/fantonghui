# AIOS 总工程师审查档案

本目录保存 AIOS 各开发任务的正式工程审查记录。

规则：

- reviews/ 记录“为什么某项任务通过或被打回”
- `reviews/M0/` 保存开发任务级评审；`reviews/architecture/` 与 `reviews/constitution/`
  保存架构级（宪法/契约级）评审及其证据，其裁决针对文档与契约，
  不得被引用为任何开发任务的 FINAL_PASS
- 同一对象存在多份架构评审时，以 `reviews/architecture/AIOS_V3_MULTI_REVIEW_META_AUDIT_NO_GO_2026-09-16.md`
  的统一元裁决为准；后到的评审必须声明与既有档案的收敛/增量关系，不得另立裁决口径
- 宪法/R1/R2/架构规格仍以仓库根目录正式文件为唯一权威
- reviews/ 不修改系统定义，只保存工程裁决
- 每个重大任务至少保留 PATCH_REQUIRED / FINAL_PASS 等关键审查记录
- 不允许开发代理自行伪造 FINAL_PASS
- FINAL_PASS 只能依据项目总工程师明确裁决创建
- 测试输出、review packet等证据放入对应 milestone/evidence 目录
