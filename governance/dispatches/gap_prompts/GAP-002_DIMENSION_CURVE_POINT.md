# AIOS 3.0 缺口补齐开发工单：维度曲线数据点 (DimensionCurvePoint) 与高阶认知导数引擎构建工单

> **工单编号**：GAP-002  
> **宪法法统**：宪法第七章 第二十三条 (认知层导数)  
> **派发对象**：云端并发开发团队 (Cloud Development Agents)  
> **验收负责人**：Antigravity 首席架构师兼工程总指挥  
> **核心使命**：构建高阶认知维度的动态时序曲线数据点，实现速度 (Velocity) 与加速度 (Acceleration) 的认知层推演，支持身心耗竭(Burnout)、精力赤字等高维风险的趋势识别与拐点预警。  

---

## 一、关联核心源代码清单

以下为必须阅读、修改或新建的代码路径：
- `src/aios_core/contracts/models.py`
- `src/aios_core/contracts/enums.py`
- `src/aios_core/curves/dimension_curve.py`
- `tests/curves/test_dimension_curve.py`

---

## 二、详细规格要求与实现规范


### 1. 契约定义规范
- 注册 `ObjectType.DIMENSION_CURVE_POINT`。
- 定义 `DimensionCurvePoint(WorldObject)`：
  - `dimension_ref: ObjectRef`, `point_time: datetime`, `value: float`
  - `velocity: float | None`, `acceleration: float | None`, `confidence: float`
  - `anomaly_flag: bool`, `anomaly_description: str | None`, `granularity: str`
  - 强制校验：严禁在底层原始传感器层做导数，导数仅存于认知维度；anomaly_flag 为真时必须携带描述。

### 2. 趋势引擎算法探索
- 实现 `DimensionCurveTracker`：
  - 增量计算一阶导数（速度）与二阶导数（加速度）；
  - 趋势状态判别算法（rising, falling, stable, inflection拐点）；
  - 异常三倍标准差或突变窗口探测。

### 3. Agent 交付物要求
- 提交完整实现及单测，杜绝外部重型依赖。
- 提交针对手环端侧时序平滑与噪声抑制算法的对比总结。


---

## 三、云端 Agent 并发执行与择优机制

1. **多 Agent 独立并发探索**：
   - 各位 Agent 请读取仓库主干代码，基于上述规范独立设计实现。
   - 允许不同的内部算法演进方案（例如不同的聚类方式、不同的导数平滑算法）。
2. **零偷懒、零占位符铁律**：
   - 严禁 `# TODO`, `# ...`, `pass` 等糊弄代码，必须 100% 可直接交付生产。
   - 所有模型字段和时间校验必须符合宪法三类时间解耦原则。
3. **提交物与优化报告**：
   - 提交完整的代码与测试用例（`pytest` 必须 100% 满绿）；
   - 附带一份《方案设计与性能优化报告》，详细阐述你的算法选型优势。
   - 最终由总工在沙箱中跑分并熔铸择优。
