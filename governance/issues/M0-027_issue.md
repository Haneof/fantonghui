# [M0-027] Reinterpretation 契约冻结（R4-01，第 31 条之一/93 条裁决的唯一数据形态）

## 目标
"认知反哺/回溯标注"从宪法矛盾变为 append-only 对象：解释层追加、历史不改、双透镜可读。

## 输入/输出契约
新增第 23 个一等对象 `Reinterpretation`（prefix rip）：`target_ref`（必须 pinned 到精确 revision；被指向对象永不产生新 revision）、`slot`（注册制枚举 emotion/meaning/identity_tag，禁自由槽名——第 76 条防爆炸）、`statement`、`confidence`（对标注本身，第 94 条）、`evidence_set_ref`（用户坦白=一等证据）、`supersedes_id`、`valid_time`（指向被加注区间，≠诞生时间）。

## 禁止修改 / 必须测试
- 禁止任何形式的历史节点改写（116 一票否决；本契约以"新对象"形态从根上不可能改写）
- target_ref 未 pinned → 拒写；诞生时刻语义（已测）

## 遗留工作
- M3-013：`world_at(T, view=AS_KNOWN|ANNOTATED)` 读面（复用 M0-020 cutoff 机制，overlay 纯函数）
- M3-013 传播边界：标注撤销只波及引用它的上层总结，半径=O(citation)
- R4-06 验收 + V36 时态双视图场景（测试规范 §4.2）

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
