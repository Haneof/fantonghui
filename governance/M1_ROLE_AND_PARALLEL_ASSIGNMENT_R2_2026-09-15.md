# M1 职务与并行开发任务分配表（R2 派生）

日期：2026-09-15
正式基线：`aios-2.0@f2107656d404bb9cac526f71175cbfc1fbbb91cb`
上位依据：AIOS 宪法 2.0、R1、R2、`AIOS_Core_详细开发任务拆分_R2_总工程师版.md`

> 本表只做“人员/Agent 编排”，不修改 M1-001～M1-016 的任务内容、先后依赖、验收标准或里程碑归属。

## 1. 固定职务

### GPT-6 架构师

职责：
- 宪法/R1/R2 架构一致性裁决。
- 对跨模块接口、世界语义、维度/证据/事件/依赖/查询模型进行架构复核。
- 任何提议修改 M0 冻结 contract/schema 时拥有架构阻断权；不得以“方便 M1”理由静默修改 M0 语义。
- 参加 M1 最终架构 Gate。

不承担：
- 普通 Issue 的主编码责任。
- 替代 Chief 做日常 merge/进度管理。
- 绕过任务母表重排 M1/M2/M3 功能。

### Chief Engineer / 总工程师

职责：
- 唯一任务解锁与依赖裁决人。
- 每个 Issue 的 scope、接口、验收、失败路径、CI、合并审查。
- 决定并行窗口、处理冲突、维护 progress/evidence。
- 对任务母表标注“总工程师审核/亲自/验收”的 Issue 承担对应职责。
- M1-009 亲自或深度审核；M1-016 最终验收。

### Core Programmer / 核心程序员

职责：
- 承担 M1 关键路径和语义敏感实现。
- 只在已解锁 Issue 上写代码。
- 每个 Issue 必须同时交付实现、单测/集成测试、失败路径与说明。
- 不得修改冻结 Issue scope。

### Parallel Programmer / 并行程序员槽位

职责：
- 只领取依赖图已经解锁、且与核心程序员文件边界可隔离的任务。
- 优先承担任务母表标注“编码代理实现”的 Issue、独立查询模块、索引/控制台以及同一 Issue 的独立测试/fixture。
- 任何共享 contract/storage 核心改动必须由 Chief 先裁定文件所有权。

## 2. 冻结依赖图

M1 依赖关系严格按任务母表：

- M1-001 ← M0 Gate
- M1-002 ← M1-001 + M0-008~010
- M1-003 ← M1-002
- M1-004 ← M1-001 + M0-011
- M1-005 ← M1-004 + M0-008 + M0-009 + M0-015
- M1-006 ← M1-001 + M1-004 + M0-009
- M1-007 ← M1-005 + M1-006 + M1-002
- M1-008 ← M1-005
- M1-009 ← M1-005~008
- M1-010 ← M1-001 + M1-004 + M1-007
- M1-011 ← M1-010
- M1-012 ← M1-002 + M1-003 + M1-007
- M1-013 ← M1-006 + M1-009 + M1-012
- M1-014 ← M1-001~013
- M1-015 ← M1-010~014
- M1-016 ← M1-001~015

并行开发只能从这个依赖图推导，不能自行创建新顺序。

## 3. M1 Issue 职务分配

| Issue | 冻结任务 | 主实现职位 | Chief 职责 | GPT-6 架构职责 | 可并行条件 |
|---|---|---|---|---|---|
| M1-001 | Observation 接入服务与去重 | Core Programmer | 审核 API、dedupe、10k 性能与“不生成 Event”边界 | 仅在拟修改 M0 Observation/Operation contract 时介入 | 当前唯一 feature 起点；Parallel 可独立写测试/fixture |
| M1-002 | Entity/别名/身份解析 | Core Programmer | 审核身份解析核心逻辑 | 审核稳定身份与 Claim/Evidence 语义边界 | M1-001 PASS 后可与 M1-004 并行 |
| M1-003 | Relation 时间化服务 | Parallel Programmer A | 审核时间/历史边界 | 重大关系语义争议时介入 | M1-002 PASS 后，可与 M1-005/006 并行 |
| M1-004 | 维度注册与多重挂载 | Parallel Programmer B / Core backup | 总工审核 | 架构 checkpoint：多维挂载不得复制事实 | M1-001 PASS 后可与 M1-002 并行 |
| M1-005 | Claim 创建/修订/比较 | Core Programmer | 核心语义审核 | 审核 Claim/Evidence/Dependency 边界 | M1-004 PASS 后启动 |
| M1-006 | EvidenceSet 创建/冻结/展开 | Parallel Programmer B | 审核 evidence freeze/cutoff | 审核证据冻结语义 | M1-004 PASS 后，可与 M1-005 并行 |
| M1-007 | Event 生命周期服务 | Core Programmer | 生命周期与修订审核 | 审核 Event 解释层边界 | M1-002/005/006 全 PASS 后 |
| M1-008 | Goal 服务与 Task 链接占位 | Parallel Programmer A | 审核 Goal != Task | 如出现 Goal 语义争议再介入 | M1-005 PASS 后，可与 M1-007 并行 |
| M1-009 | Dependency 写入与反向查询 | Core Programmer + Chief | 总工亲自/深度审核 | 架构 checkpoint：为 M3 纠错传播保留精确 revision 语义 | M1-005~008 全 PASS 后 |
| M1-010 | world.view/zoom/shift | Core Programmer | 总工审核接口 | 审核时间镜头不制造另一套世界语义 | M1-007 PASS 后 |
| M1-011 | align/compare/change detection | Parallel Programmer A | 审核机械检测边界 | 确认不得输出语义因果 | M1-010 PASS 后 |
| M1-012 | 搜索/实体解析/关键词超链 | Core Programmer | 总工审核 | 审核 typed link / 搜索命中 != 事实 | M1-002/003/007 PASS 后 |
| M1-013 | evidence.read/trace/event.expand | Core Programmer | 总工审核 | 架构 checkpoint：完整下钻、反证不可隐藏 | M1-006/009/012 PASS 后 |
| M1-014 | 索引水位/重建/STALE_INDEX | Parallel Programmer A | 审核索引不是事实来源 | 必要时复核一致性边界 | M1-001~013 全 PASS 后 |
| M1-015 | 开发者控制台最小版 | Parallel Programmer B | 审核控制台只读、调用同一 query service | 不单独设计认知逻辑 | M1-010~014 PASS 后 |
| M1-016 | 运动会→体育测试贯穿案例 | Core Programmer 负责 fixture/轨迹，所有程序员配合 | 总工最终验收 | GPT-6 最终架构 Gate | M1-001~015 全 PASS 后 |

## 4. 实际并行波次

波次不是新的里程碑，只是依赖图的执行视图；某任务一旦满足前置即可提前进入，不必等待同波所有任务。

### Wave 0 — 当前
- Core Programmer：M1-001 service implementation。
- Parallel Programmer A：M1-001 独立 integration tests、10k fixture、dedupe/rollback/performance cases。
- Chief：冻结接口与验收，review/merge。
- GPT-6：只做 M1 起点架构一致性检查，不写实现。

### Wave 1 — M1-001 PASS 后
- Core Programmer：M1-002 Entity/identity。
- Parallel Programmer B：M1-004 Dimension registration/membership。

### Wave 2
- Parallel A：M1-003 Relation（M1-002 后）。
- Core：M1-005 Claim（M1-004 后）。
- Parallel B：M1-006 EvidenceSet（M1-004 后）。

### Wave 3
- Core：M1-007 Event（M1-002/005/006 后）。
- Parallel A：M1-008 Goal（M1-005 后）。

### Wave 4
在各自前置满足后并行：
- Core/Chief：M1-009 Dependency。
- Core：M1-010 world.view/zoom/shift。
- Parallel B 或 Core backup：M1-012 search/links。

### Wave 5
- Parallel A：M1-011 align/compare/change detection。
- Core：M1-013 evidence trace/event expand。

### Wave 6
- Parallel A：M1-014 index watermark/rebuild。

### Wave 7
- Parallel B：M1-015 developer console。

### Wave 8
- 全员：M1-016 scenario。
- Chief：最终验收。
- GPT-6：最终 architecture Gate。

## 5. 分支/PR 纪律

- 基线：`aios-2.0`。
- 一个 Issue 一个主 feature branch；同 Issue 的独立测试可有第二 branch。
- feature branch 命名：`m1/<role>-m1-XXX-<slug>-YYYYMMDD`。
- PR 一律 base `aios-2.0`。
- 依赖 Issue 未 PASS 的 PR 不得 merge；原则上不提前开始依赖功能。
- 不允许两个程序员同时修改同一核心文件而没有 Chief 明确划分。
- 任何 M0 schema snapshot 变化自动升级为架构事件，停止普通 merge，交 GPT-6 + Chief 裁决。

## 6. 当前正式派单

### Core Programmer — M1-001 implementation

实现必须严格来自任务母表：
- 统一接入虚拟 GPS、心率、IMU、文本、App 数据为 Observation。
- 使用 `source_event_id/source_seq` 或 `dedupe_key` 做来源消息去重。
- 只做格式、单位、时间、数据质量清洗，不做语义判断。
- 成功写入必须通过 Core commit。
- 相同 source message 重放不得新增 Observation。
- 不同时间的相同 value 仍允许新增。
- 10k 模拟心率批量写入且不触发 AI。
- 禁止按 value 简单去重；禁止生成 Event。

推荐文件仍按母表：`world/ingest.py`, `api/ingest.py`, `tests/integration/test_ingest.py`。先 service，HTTP 后置。

### Parallel Programmer A — M1-001 independent tests

只写测试/fixture/性能基线，不修改核心实现：
- exact source replay idempotency。
- same value / different time 必须保留。
- mixed GPS/HR/IMU/text/app batch。
- invalid time/unit/data-quality 失败路径。
- 事务失败不产生半批 Observation。
- 10k HR baseline。
- 验证 ingest 后 Event/Wake/Claim 不被自动创建。

测试预期在执行前冻结；不得为了实现通过而事后改 expected outcome。

## 7. 当前 Gate

`M1-001 = ASSIGNED / IN PROGRESS`

`M1-002~M1-016 = LOCKED BY DEPENDENCIES`

除 M1-001 的独立测试工作外，当前没有其他 feature 被授权开始。