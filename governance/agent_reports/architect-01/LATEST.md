# M1-001 Architecture Review

## Baseline

- branch: `aios-2.0`
- exact SHA: `f2107656d404bb9cac526f71175cbfc1fbbb91cb`
- 实现分支：`m1/core-m1-001-observation-ingest-20260915`；本次读取 HEAD 同为上述 SHA。
- 独立测试分支：`m1/parallel-m1-001-tests-20260915`；本次读取 HEAD 同为上述 SHA。
- 治理依据：`governance/aios-control-plane@5d6c2307e538dec65985b84513c85163d76aa445`。
- Reviewer：architect-01；日期：2026-09-15。

已直接读取指定六份权威文件、治理启动文件、基线 Git tree、Observation/WorldObject/ObjectRef/SourceRef/OperationRequest/time 契约、SQLite commit 与幂等实现、Observation 单测及架构边界测试。两个 M1 工作分支尚无相对基线的新提交；基线 world 模块仍为占位，未见 ingestion 实现、接口细案或 M1-001 测试交付。

## Verdict

**APPROVE WITH REQUIRED CHANGES**

此结论仅批准已发布 M1-001 任务方案的架构方向，要求补齐下述服务语义；不表示实现已验收，不授权合并。目前没有实现 candidate 可作行为验证。本轮没有运行 pytest，也不将 M0 测试成绩算作 M1-001 证据。

## Constitution / R1 / R2 consistency

方案限定格式、单位、时间、数据质量、来源元数据和来源消息去重，与宪法第二条、第四条、第十二条、第四十三条及任务母表 M1-001 一致。R2 §3 明确 Observation 默认只写入、不直接 Wake；它对 R1 的基础观测触发表述作了明确细化。

文本“我明天肯定考上”可以原样成为已获得资料，但 ingestion 不得生成“明天考上”的事实或预测对象。App 已提供的结果可以作为有来源的输入保存，不能因此推导用户能力。资料内容提到事件，不等于 ingestion 获准创建 Event。

当前只审查 M1-001。维度挂载、Claim/Event 服务、触发调度及总结，仍属于后续任务。

## M0 frozen-contract impact

**目前没有证据表明 M1-001 必须改变 M0 冻结契约。**

Observation 已有 value、unit、data_quality、raw_locator 和继承的 metadata/source_refs；source_event_id/source_seq/dedupe_key 可以在服务输入模型中定义，并以有命名空间的 metadata 保存来源身份。母表要求定义这些标识，没有要求把它们新增为 Observation 顶层字段。

SourceRef.object_id 是世界对象引用，不能直接填入尚不存在的设备消息 ID。外部消息标识应作为来源元数据或 locator 保存；真实世界对象引用仍接受 Core 的完整验证。

可行的无契约变更方向是：服务基于持久化来源身份查重，所有新增 Observation 通过现有 Core commit 提交，查重依据与 expected_world_revision 保持一致；冲突后重新读取、重新判定。此处是兼容性方向，不是已实现或已证明的算法。具体实现仍需证明并发、重启和性能要求。

不得放宽 Core fingerprint 为“只比较 value 或 source key”；不得允许空 commit、跳对象 revision、改写历史或改变 SourceRef 含义来方便接入。任何此类要求，或修改冻结 schema/snapshot，必须升级为 **ARCHITECTURE BLOCKER / M0 CONTRACT CHANGE REQUEST**，列出字段/语义、无变更替代方案、历史兼容影响及 M0 Gate 重跑范围，交 Chief 裁决。

## Ingestion boundary review

必须在服务接口说明中明确：

1. 接收资料与规范化规则，包括单位换算、无时区时间处理、未知时间及无效输入处理；不能把不合法值静默删除后返回成功。
2. data_quality 表示采集/格式/信号质量，不能成为对事件、情绪或主张真实性的评分。
3. learned_at 表示 AIOS 获知资料的时间，不能自动等于 occurred。普通接入的时间由受控上下文确定；模拟/导入路径必须明确时钟和 provenance。recorded_at 保持 M0 约束；物理提交时间仍属于 world_commits.committed_at。
4. 每次重放不得把首次获知时间刷新成当前时间，或根据消息叙述把获知时间回填到过去。
5. 接入服务位于 Core 边界内；外部适配器/Worker 不获得 SQLite 连接、路径或存储内部写能力。所有正式写入必须到现有 commit。

## Deduplication semantic review

当前任务描述没有规定完整去重身份和冲突处理，合并前必须冻结。

| 待验证情形 | 必须保持的结果 |
|---|---|
| 两设备分别发出 source_seq=1 | 按来源命名空间区分，不能误去重 |
| 同设备重启后序号复用 | 必须有来源协议规定的序号作用域；不能默认永久唯一 |
| 同来源同消息跨请求、跨批次、重启后重放 | 返回已有 Observation，不新增证据或 revision |
| 心率 80 在两个采样时刻出现 | 保留两条独立 Observation |
| 同消息标识对应不同内容 | 明确冲突；不能静默视为成功或覆盖旧资料 |
| 批次 [A,B] 后再收到 [B,C] | B 不重复，C 按一个原子新增集合提交 |
| 同批次重复身份对应不一致内容 | 提交前明确拒绝，不能任意保留一个 |

特别需要区分：

- **source identity**：来源消息的身份。
- **Core request identity**：operation_id、session_id、operation_name、arguments、expected_world_revision、reason、key 和完整对象集合的规范化身份。

基线 request_fingerprint 明确包含上述字段。将 source key 直接作为 Core key，却在重试时重建 operation_id、时间或对象 ID，会变成不同请求；不得通过修改 M0 幂等规则消除这个冲突。服务应明确原请求精确重试与新请求携带重复来源消息的不同处理。

来源身份编码必须无歧义；不能用未经转义的字符串拼接产生碰撞。规范化版本变化后也不得让同一消息变成新证据。缺失可靠来源标识时应明确拒绝或声明无来源去重保证，不能退回按 value 判断。

## Atomicity / revision review

基线 commit 使用 BEGIN IMMEDIATE，优先处理幂等重放，检查 expected_world_revision、对象 revision/type 和引用，随后在同一事务写入世界提交、对象、operation、幂等记录与 world_meta；异常时 rollback。

这些底层能力不自动证明新的 ingestion 正确。必须补证：

- 查重读取绑定一个明确的世界 revision。两个接入者同时认定消息未存在时，不得都新增；输掉版本竞争的一方重新查重，不能只刷新 expected_world_revision 后盲目提交。
- 一个成功的新数据批次只消耗一个 world revision；各新对象从 revision 1 开始。不得以逐条 commit 实现并宣称整批原子。
- 全重复批次不得调用空 commit；不得新增占位 Observation 或虚假 world revision。返回 refs 及 world_revision 的含义必须明确，尤其是重复成员来自不同历史提交时。
- 失败不得留下半批对象，也不得先在另一个事务标记“已去重”，导致重试时丢失未提交资料。
- 晚到资料仍按真实 learned_at 控制可见性。重放返回已有对象不是放宽历史读规则的理由；若接口承诺历史视图，其 refs 必须对应所声明的世界 snapshot 与 knowledge cutoff。

## Forbidden semantic leakage check

已发布方案明确禁止生成 Event，R2 与本次授权进一步约束 Wake、Claim、Summary 和高层认知。基线 Observation 测试验证直接 store.commit 不创建若干派生对象，但不能证明尚未交付的 ingestion、回调和生产装配同样满足边界。

后续必须检查实际调用链及结果对象集合。不能只检测 Observation 顶层没有 event_type：value/metadata/data_quality 均可承载结构化数据，服务仍可能在其中自行写入语义结论。应区分忠实保存上游资料与 ingestion 自行解释资料。

## Required changes

以下是方案必须补齐的要求，不是对尚不存在实现的缺陷断言：

1. 冻结来源身份的命名空间、序号作用域、缺失标识及同标识异内容处理。
2. 冻结 source replay 与 Core exact retry 的区别、持久化依据及重启恢复流程。
3. 冻结批内/跨批去重、全重复批次响应、world_revision 含义和版本竞争处理。
4. 冻结时间归属、单位规范化、质量字段含义及 provenance 保留规则。
5. 提交仅涉及 M1-001 的实现与独立测试，证明调用 Core commit、整批原子及不生成高层对象。
6. 提供 exact-SHA diff，确认冻结模型、OperationRequest、引用契约、SQLite 语义及 M0 snapshot 未被顺带修改。结构 snapshot 绿色不能代替行为回归。

## Non-blocking observations

- 先 service、后 HTTP 与母表一致；不需要为本任务扩展架构路线。
- 10k 心率测试应记录环境、批量耗时和数据质量可查询性；母表没有给出固定毫秒门槛，不应擅自新增。
- 治理 CONTROL_PANEL/CURRENT_STATE/ACTIVE_ASSIGNMENTS 仍含旧 M0 状态，与 9 月 15 日分工及进度不一致。本轮按用户明确授权及最新 M1 文件执行；建议 Chief 同步旧入口，避免下一位 agent 误领旧任务。
- 分支清理文档称清理时没有 open PR；本次列表仍显示旧 M0 PR #3，未见 M1-001 PR。它不构成 M1 方案错误，但不能作为当前 PR 状态的准确说明。
- 本轮未修改生产、任务母表或实现；没有重新裁决 M0 FINAL PASS。

## Exact conditions for Chief Engineer merge approval

Chief 仅在下列条件全部满足后考虑合并：

1. M1-001 candidate 从正式 aios-2.0 基线派生，PR base 正确，exact SHA 已记录，diff 无未授权范围。
2. 上述 Required changes 已写入接口说明并落实，实现与独立测试预期一致。
3. exact candidate 通过 source replay、同值不同时间、跨来源碰撞、混合/全重复批次、重启、同 key 异请求、并发 writer、晚到资料和无效输入测试。
4. 每个预期失败前后，world revision、world_commits、object_revisions、operations、idempotency_records 均无本次残留；注入中途失败后仍可正常重试。
5. 10k 混合/心率相关验收、无 AI 调用、无自动 Claim/Event/Wake/Summary、data_quality 可读的证据齐全。
6. 正式回归、Reference、M0 schema snapshot 及相关原子性/幂等/引用/历史读测试结果绑定同一个待合并 SHA，失败解释可复核。
7. 任何 M0 冻结契约变化先走独立变更裁决，不能以此报告代替批准。

当前尚不满足实现合并条件。最终验收与 merge authority 属于 Chief Engineer。
