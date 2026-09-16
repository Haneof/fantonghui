# M0_CORE_原子任务拆解清单

**定位**：AIOS 3.0 M0-Core 原子任务拆解与派单。
**参考宪法**：第 109 条（M0 必须冻结项清单）
**交付规范**：严格遵守 12 要素规范

---

## 核心任务列表

### CORE-001: 三类时间模型与基类定义
1. **任务编号**：CORE-001
2. **目的**：建立全局唯一时间轴与三类时间分离规则（发生时间、获知时间、写入时间），统一所有 AIOS 核心数据对象的基类继承基础。
3. **输入**：系统时间、传感器事实发生时间戳。
4. **输出**：基础数据模型对象基类。
5. **接口**：`class BaseRecord(BaseModel): ...`
6. **数据结构**：Pydantic 模型包含 `object_id` (str), `world_revision` (int), `occurred_at` (datetime), `learned_at` (datetime), `recorded_at` (datetime)。继承自 `03_核心技术资产代码与DDL黄金底库` 的 `BaseRecord` 契约。
7. **前置依赖**：无。
8. **禁止行为**：严禁混淆 `occurred_at`, `learned_at` 和 `recorded_at`。严禁不使用 UTC 时区。
9. **单元测试**：测试三类时间戳是否正确赋值，测试 `world_revision` 是否 >= 1。
10. **集成测试**：验证在世界状态中，时间排序的一致性。
11. **验收场景**：V21
12. **已知限制**：当前暂不支持复杂相对时间（如“明天下午”）的自动解析。

### CORE-002: 全局对象 ID 生成与验证器
1. **任务编号**：CORE-002
2. **目的**：提供所有对象必须使用的 UUID4 稳定标识符，禁止随状态变更而变更。
3. **输入**：无或对象基本信息。
4. **输出**：稳定的 UUID4 字符串生成与验证。
5. **接口**：`def generate_uuid4_str() -> str:`
6. **数据结构**：依赖 `uuid.uuid4()` 生成字符串，并在 Pydantic 中增加 `@field_validator("object_id")` 校验。继承自 `03_黄金底库.md` 中的 `base.py`。
7. **前置依赖**：CORE-001。
8. **禁止行为**：严禁使用自增整型或业务含义字符串作为主键 ID。
9. **单元测试**：测试 10000 次 ID 生成不重复且符合 UUID4 规范，测试错误 UUID 格式抛出异常。
10. **集成测试**：对象跨表引用时 UUID 匹配测试。
11. **验收场景**：V22
12. **已知限制**：单机 UUID 生成不处理跨多节点的严格分布式时序排序问题。

### CORE-003: Observation 结构定义与底层 DDL
1. **任务编号**：CORE-003
2. **目的**：实现原始事实切片的追加写入存储结构，支持边缘轻量化与多模态。
3. **输入**：硬件传感器、端侧模型提取的语义文本摘要。
4. **输出**：Observation 实例及落盘数据。
5. **接口**：`def append_observation(obs: Observation) -> str:`
6. **数据结构**：Pydantic: `observation_id`, `world_revision`, `dimension_id`, `content`, `confidence`, `occurred_at`, `learned_at`, `recorded_at`, `source_device`, `checksum`。SQLite DDL: `observations` 表。继承自 `03_黄金底库` `facts_schema.sql`。
7. **前置依赖**：CORE-001, CORE-002。
8. **禁止行为**：严禁在 `observations` 表执行 UPDATE 或 DELETE 操作；严禁直接存储原始高频时序数据或二进制大图。
9. **单元测试**：测试追加写入 100 条 Observation 并正确按 occurred_at 排序读取。
10. **集成测试**：测试传感器数据转换至 Observation 落地。
11. **验收场景**：V23
12. **已知限制**：暂时不支持视频流的自动抽取。

### CORE-004: Entity 与 Relation 结构与 DDL
1. **任务编号**：CORE-004
2. **目的**：定义实体档案及可演化关系，支撑未知到已知的动态身份解析机制。
3. **输入**：人物/物品的摘要信息。
4. **输出**：Entity 对象与关系连线。
5. **接口**：`def upsert_entity(entity: Entity) -> None:`
6. **数据结构**：`entity_id`, `canonical_name`, `alias_json`, `entity_type`, `created_at`。SQLite DDL: `entities`, `entity_co_occurrence_edges`。继承自 `03_黄金底库` `facts_schema.sql` 和 `cjk_inverted_index.sql`。
7. **前置依赖**：CORE-002。
8. **禁止行为**：严禁依靠名称判定实体相同（必须使用 UUID 指针）。
9. **单元测试**：测试实体建立、同名实体的分立 UUID 验证。
10. **集成测试**：通过 UUID 获取实体详情与共现网络。
11. **验收场景**：V24
12. **已知限制**：当前无图数据库优化，大规模关系遍历性能受限。

### CORE-005: Claim R2 模型与枚举定义
1. **任务编号**：CORE-005
2. **目的**：实现包含 11 类 `claim_type` 的认知主张模型，严格区分主客观与不同来源。
3. **输入**：文本分析结果。
4. **输出**：Claim 数据对象。
5. **接口**：`class Claim(BaseRecord): ...`
6. **数据结构**：`claim_id`, `subject_id`, `claimant_id`, `claim_type` (枚举11类), `content`, `valid_time`, `asserted_at`, `knowledge_state`, `confidence`, `support_evidence_set_ids`, `counter_evidence_set_ids`, `source_refs`, `status`。继承宪法第12章标准。
7. **前置依赖**：CORE-001, CORE-004。
8. **禁止行为**：禁止将 "AI猜测" 强制转换为 "FACT" 并覆盖。
9. **单元测试**：测试 11 种枚举创建，验证 confidence 的合法边界。
10. **集成测试**：从对话提取不同 claimant 和 type 的 Claim。
11. **验收场景**：V25
12. **已知限制**：无复杂逻辑演绎推断规则支持。

### CORE-006: EvidenceSet 一等结构
1. **任务编号**：CORE-006
2. **目的**：提供认知可复核证据集，维持整个认知图谱的证据链完整与下钻。
3. **输入**：选定的源引用 ID 集合。
4. **输出**：EvidenceSet 对象。
5. **接口**：`class EvidenceSet(BaseRecord): ...`
6. **数据结构**：`evidence_set_id`, `purpose`, `time_range`, `knowledge_cutoff`, `member_refs`, `support_refs`, `counter_refs`, `selection_method`, `status`。继承宪法第13章。
7. **前置依赖**：CORE-003, CORE-005。
8. **禁止行为**：禁止仅保存“支持”证据而丢弃“反对/削弱”证据。
9. **单元测试**：构建包含 support 和 counter 引用的 EvidenceSet，测试序列化。
10. **集成测试**：测试通过 evidence_set_id 获取底层 Observation 链条。
11. **验收场景**：V26
12. **已知限制**：不支持基于自然语言的动态 selection_method 重执行。

### CORE-007: EventAnchor 结构与 7 阶段生命周期
1. **任务编号**：CORE-007
2. **目的**：构建多维事件锚点及 CANDIDATE/ACTIVE 等七阶段状态演化支持。
3. **输入**：底层多个 Observation 切片聚类。
4. **输出**：EventAnchor 对象及状态流转。
5. **接口**：`def update_event_status(event_id: str, new_status: EventStatus, revision_reason: str):`
6. **数据结构**：`anchor_id`, `title`, `start_time`, `end_time`, `primary_entity_id`, `summary_text`, `evidence_ids_json`, `status` (7阶段枚举), `confidence`, `supersedes_event_id`, `merged_into_event_id`, `split_from_event_id`, `revision_reason`。基于底库 `event_anchors` 扩展宪法第14章字段。
7. **前置依赖**：CORE-004, CORE-006。
8. **禁止行为**：禁止物理删除被 REJECTED 或 MERGED 的历史 EventAnchor 记录。
9. **单元测试**：测试七阶段状态机合法流转校验（如 CANDIDATE -> ACTIVE）。
10. **集成测试**：事件合并 (MERGED) 后，新旧 Event 之间的指针链接及状态变更。
11. **验收场景**：V27
12. **已知限制**：不包含基于 AI 大模型的自动化聚类与分割策略本身。

### CORE-008: Goal 一等结构
1. **任务编号**：CORE-008
2. **目的**：系统化定义用户意图与目标管理体系，提供目标的生命周期管理。
3. **输入**：目标拆解与关联实体。
4. **输出**：Goal 对象及其追踪记录。
5. **接口**：`class Goal(BaseRecord): ...`
6. **数据结构**：参照宪法，包含 `goal_id`, `title`, `status`, `target_entity_ids`, `milestones`, `created_by`, `confidence`, `priority`, `source_evidence_set_ids` 等。
7. **前置依赖**：CORE-006, CORE-007。
8. **禁止行为**：严禁脱离时间轴修改 Goal 状态而不产生新 revision。
9. **单元测试**：测试目标状态流转与历史版本记录。
10. **集成测试**：目标达成后触发关联子任务关闭。
11. **验收场景**：V28
12. **已知限制**：自动衍生子目标的机制由大模型实现，非结构级保障。

### CORE-009: 维度定义与派生规则结构 (Dimension)
1. **任务编号**：CORE-009
2. **目的**：实现可挂载的、非硬编码的突触式维度与总结金字塔派生规则 (DimensionDerivation)。
3. **输入**：底层维度数据及派生关系配置。
4. **输出**：DimensionDefinition 与 DimensionDerivation 记录。
5. **接口**：`class DimensionDerivation(BaseModel): ...`
6. **数据结构**：`derivation_id`, `output_dimension_id`, `input_dimension_ids`, `input_event_refs`, `scope`, `time_window_rule`, `created_by`, `update_policy`, `revision`, `status`。依据宪法第24条。
7. **前置依赖**：CORE-001。
8. **禁止行为**：禁止在代码中硬编码任何死维度。
9. **单元测试**：测试维度元数据定义对象的有效性及验证器。
10. **集成测试**：构建两级维度拓扑引用并进行下钻检查。
11. **验收场景**：V29
12. **已知限制**：维度动态重算依赖外部触发，无内置自动重算引擎调度。

### CORE-010: 认知复式记账与 Dependency 结构
1. **任务编号**：CORE-010
2. **目的**：保证依赖节点之间的单跳失效隔离及置信度调整追溯。
3. **输入**：高层认知节点与底层证据/节点。
4. **输出**：CognitiveLedgerEntry 与 NodeDependency 数据流。
5. **接口**：`def record_dependency(downstream_id: str, upstream_id: str) -> None:`
6. **数据结构**：Pydantic `CognitiveLedgerEntry`，以及 SQLite `node_dependencies` 和 `cognitive_nodes` (is_stale, stale_reason)。继承自 `03_黄金底库` 和宪法。
7. **前置依赖**：CORE-006。
8. **禁止行为**：严禁循环依赖或级联超过 1-Hop 物理删除。
9. **单元测试**：测试插入 1-Hop 依赖关系，测试标记为 stale 后正确生效。
10. **集成测试**：执行 invalidate_overturned_fact_single_hop 算法，验证下游失效波及正确。
11. **验收场景**：V21
12. **已知限制**：只支持 1-Hop 失效标记，深层图遍历与重算通过 lazy eval 进行。

### CORE-011: Task 与 触发条件结构
1. **任务编号**：CORE-011
2. **目的**：统一 AIOS 环境中的条件驱动任务存储模型。
3. **输入**：触发条件与 Task 载荷。
4. **输出**：ConditionalTask 对象与存储。
5. **接口**：`class ConditionalTask(BaseModel): ...`
6. **数据结构**：`task_id`, `title`, `state`, `condition_type`, `condition_expression`, `payload`, `created_at`。继承底库 `conditional_task.py` 与 `tasks_and_dependencies.sql`。
7. **前置依赖**：CORE-002, CORE-007。
8. **禁止行为**：严禁 DORMANT 任务直接进入大模型提示词。
9. **单元测试**：测试 Task 状态扭转逻辑及序列化。
10. **集成测试**：利用 tick_mechanical_fast_track 将 TIME_ABSOLUTE 任务扭转为 READY。
11. **验收场景**：V30
12. **已知限制**：复杂语义的 SEMANTIC_PIGGY 只能作为占位标志，实际评估需大模型。

### CORE-012: 版本控制与统一引用完整性 (Revision)
1. **任务编号**：CORE-012
2. **目的**：所有核心业务对象的不可变版本迭代体系与外键完整性约束检查。
3. **输入**：任何已存在数据的变更请求。
4. **输出**：新 revision 对象创建与持久化。
5. **接口**：`def increment_world_revision() -> int:`
6. **数据结构**：所有对象依赖 `world_revision` 单调自增，跨表关联遵循 UUID。
7. **前置依赖**：全部核心模型 (CORE-001 ~ CORE-011)。
8. **禁止行为**：严禁使用 SQL 物理删除对象历史 revision；禁止在同一个 world_revision 下混杂不同批次事务。
9. **单元测试**：测试读取指定 world_revision 的世界快照截面。
10. **集成测试**：事务级对象创建，确保关联对象的外键 UUID 全部存在并合法。
11. **验收场景**：V21
12. **已知限制**：不提供时间旅行般的完整系统状态倒回操作，仅支持历史快照检索。

---

## 退出条件检查清单

- [x] 已建立全局唯一的真实时间轴逻辑。
- [x] 已彻底实施了发生时间、获知时间、写入时间的三分离规则。
- [x] 所有数据对象采用了稳定的全局 UUID，无身份重置问题。
- [x] 严格遵守“追加事实 (Append-Only Facts)”约束，严禁修改/删除事实记录。
- [x] 多阶总结体系、认知跨域共振生成高级维度的机制在元数据中已体现。
- [x] 全部 22 类核心对象定义不缺失，尤其是 Observation, Entity, Relation, Claim, EvidenceSet, EventAnchor, Goal 及其状态枚举。
- [x] "当时已知世界 (Knowledge Cutoff / World Revision)" 的查询约束已完整设定，以保证历史回溯不作弊。
- [x] 已废除所有长篇大论爹味说教设计（通过截断门拦截器等配合执行）。
