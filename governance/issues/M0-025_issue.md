# [M0-025] Prediction Register 契约冻结（第 50~53 条）

## 目标
假说-演绎闭环获得一等对象：预测可登记、可对撞、可裁决、可追责（立项理由）。

## 输入/输出契约
新增 `Prediction`（prefix prd）：`source_claim_ref`（必须 pinned，第 18 条指针主义）、`target_dimension_id`、`expected_change`（必须非空可证伪）、`time_window`、`verification_state`（pending/corroborated/falsified/expired 状态机）、`actual_outcome_ref`（verdict 状态必填）、`reasoning`（第 53 条立项理由，空白即拒写——内核能强制的形式校验）。

## 禁止修改 / 必须测试
- 禁止预测 AI 自身内部计算行为（语义级，列入 evaluator 判分场景，不做字段校验伪装）
- pinned 校验 / reasoning 空白拒写 / verdict 无证据拒写（均已单测）

## 遗留工作
- M2-016/017：PredictionCheckTask 进入 timer_heap（kind=PREDICT_CLASH）
- M3：对撞服务与置信度下调反思链（R3-03 验收）

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
