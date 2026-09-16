# [M0-023] 写入来源分类 source_class 与触发豁免契约

## 目标
给"这次写入是谁发起的"以内核表达，使第 64/82 条反风暴条款第一次技术上可执行；封死"修正→维护写→触发→唤醒→再修正"的认知永动机（设计书诊断 F2）。

## 输入/输出契约
OperationRequest 新增 `source_class: SourceClass`（user/sensor/ai_cognition/maintenance/safety，默认 ai_cognition 保持既有调用方兼容）与 `maintenance_class: MaintenanceClass | None`（maintenance 必填、其余必须为空，after-validator 互斥校验已冻结）。

## 允许修改文件
- src/aios_core/contracts/{enums,operations}.py
- tests/unit/test_m0_prime_contracts.py
- schemas/r2/m0_contract_snapshot.json（批准漂移再生成）

## 禁止修改
- 三类时间语义、Object ID 规则、EvidenceSet 语义
- 禁止以"语义识别这像不像维护内容"代替字段判定豁免（第 77/106 条）
- 禁止 DEFAULT 蒙混历史回填（迁移必须显式 UPDATE，M1 执行）

## 必须测试
- MAINTENANCE 缺 maintenance_class → ValidationError；非 MAINTENANCE 携带 → ValidationError；默认值兼容 → 通过。

## 预开工件记录（arena 分支；M1 Gate 未开，不构成里程碑状态变更）
- [x] 存储层加列 + 迁移 + 部分索引已作为**预开工件**落地：`world_commits.source_class`
      五值 CHECK、`idx_commits_triggerable`（排除 maintenance）；旧库迁移走
      补列→显式回填 `ai_cognition`→表重建（无 DEFAULT 蒙混），审计 JSON 写入
      `world_meta.schema_migration_m0_023`（测试锁定）。
- [x] `triggerable_commits_after()` 读面就位：M2-002 触发引擎届时只消费该过滤器，
      `MAINTENANCE → skip` 已结构性成立（维护提交对触发评估不可见）。
- 边界：本记录不改变上方遗留工作中 M2-002/M2-GATE 的待办状态；运行路径接入仍待 Gate。

## 遗留工作（不入本契约任务）
- M1：world_commits/operations 加列 + 显式回填迁移 + `idx_commits_triggerable` 部分索引（存储侧已以预开工件完成，见上；operations 表如需审计加列仍归 M2-002 接入时决定）
- M2-002 重写：触发引擎 `MAINTENANCE → skip`；SAFETY 去抖带（V32）
- M2-GATE：V21b 风暴回归（唤醒放大比≤1、时钟冻结检测）

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
