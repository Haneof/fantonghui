# 工单 #7：M5-002 维度生命周期与高阶维度提炼挂载引擎 (Dimension Lifecycle & Overlay)

- **派发代号**：`TASK-M5-002-DIM-LIFECYCLE`
- **指派战队**：Agent-07 战队（心智维度演化组）
- **所属模块**：C01 心智宪章与 C06 维度守卫层
- **前置依赖**：`M1-018`
- **目标分支**：`arena/agent-07-m5-dim-lifecycle`

## 1. 任务背景与核心目标（最高宪法第五铁律）
严禁 AI 无休止自言自语导致维度爆炸！但当真实世界出现持续物理异常时，AI 必须能敏锐提炼高阶维度，并将其挂载到实体与关系上。

## 2. 核心交付代码
交付文件：`src/aios_core/cognition/dimension_engine.py`
包含核心组件：
1. `CrossDimensionalAnomalyDetector`:
   - 探测物理跨域连续 3 天以上异常（如深夜熬夜 + 心率骤升 + 咖啡因消费）；
2. `DimensionLifecycleStateMachine`:
   - 严苛实现三重硬门槛状态机：
     * 门槛 1: 物理跨域异常持续 3 天；
     * 门槛 2: 提出候选维度（Candidate Dimension），进入 30 天试用期与 Prediction 验证；
     * 门槛 3: 每日最多 1 次反思配额，验证通过后向系统正式注册（Register）；
3. `HighOrderDimensionDistiller`:
   - 从低阶物理感知事实提炼高阶认知维度：
     * 身心衰竭指数：`DIM_BURNOUT_RISK`
     * 商业信用风险：`DIM_CREDIT_RISK`
     * 亲情健康关切：`DIM_PARENT_HEALTH`
4. `DimensionOverlayOperator`:
   - 将提炼的高阶维度以只读标签方式挂载（Overlay）到实体、关系或事件上。

## 3. 验收标准
- 编写 `tests/cognition/test_dimension_lifecycle.py`；
- 模拟未满 3 天物理异常提炼维度，断言必须被拦截拒绝；
- 模拟通过 30 天验证的候选维度，断言正式注册成功并完成挂载。
