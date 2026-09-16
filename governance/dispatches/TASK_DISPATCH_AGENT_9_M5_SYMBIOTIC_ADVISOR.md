# 工单 #9：M5-004 共生决策辅助与行动推演引擎 (Symbiotic Action Advisor)

- **派发代号**：`TASK-M5-004-ACTION-ADVISOR`
- **指派战队**：Agent-09 战队（因果推演与决策支持组）
- **所属模块**：C05 因果推演层、C08 建议生成
- **前置依赖**：`M1-018`
- **目标分支**：`arena/agent-09-m5-action-advisor`

## 1. 任务背景与核心目标（最高宪法第一铁律：输出质量绝对第一）
绝不为了抢首字吐出废话！在提供决策帮助时，必须下钻全周期记忆，给出真切、精准、证据链确凿的行动建议。

## 2. 核心交付代码
交付文件：`src/aios_core/cognition/symbiotic_advisor.py`
包含核心推演场景与组件：
1. `MomBirthdayGiftAdvisor`:
   - 深度对比 2023 丝巾落灰、2024 足浴盆笨重倒水腰疼闲置、2025 按摩椅极佳；
   - 结合 2026 膝盖老寒腿受凉 Observation 与预算；
   - 产出建议：严禁笨重水洗家电，精准推荐轻便膝盖气囊热敷理疗仪，列举确凿依据；
2. `FraudPreventionAdvisor`:
   - 面对老王借款或新合伙人提议，自动联动朝阳法院判决与历史拖延微信切片；
   - 产出硬核阻击与资产追偿执行建议，阻断二次受骗；
3. `HealthFatigueBreakerAdvisor`:
   - 面对周四连续通宵与室性早搏，自动触发疲劳熔断警告与就医心电图复查清单；
4. `ActionableAdvice`:
   - 统一数据结构：包含结论、因果证据指针清单、备选方案与预期收益。

## 3. 验收标准
- 编写 `tests/cognition/test_symbiotic_advisor.py`；
- 断言生成的建议包含明确的因果事实 ID（ObjectRef）；
- 断言老妈送礼决策严格排除足浴盆与饰品，精准命中膝盖理疗。
