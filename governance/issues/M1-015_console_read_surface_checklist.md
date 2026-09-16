# M1-015 开发者控制台最小版 · 读面查询清单（Gate 前指路件）

> 性质：**只读清单**，非实现承诺。控制台 UI 属 Gate 后 B 块外的 M1 余量；
> 本文件的职责是把 M1-015 压缩成"三个新读面 + 一张面板-接口映射表"，
> 让实现时无设计残留。全部映射基于 arena 分支已实测接口（预开工件），
> 每条"已备"都对应真实方法名，不可空引。

## 1. 面板 → 读面映射（P1–P7）

| 面板 | 查询 | 读面 | 状态 |
|------|------|------|------|
| P1 世界修订流 | 修订时间线（含 source_class 标签、维护笔灰显而非隐藏） | `store.triggerable_commits_after(wr, *, limit)` + `revisions_after(wr, *, limit)` + `commit_source_class(wr)` | ✅ 已备（T4 批实测）|
| P2 对象检视器 | 任意对象按 revision / as_of_world_revision / knowledge_cutoff 三模式读；快照哈希自检（模型 JSON schema vs 冻结快照） | `store.get_payload(oid, *, revision, as_of_world_revision, knowledge_cutoff)` + `build_current_snapshot()` 对拍 | ✅ 已备（M0-020 读面 + 快照测试同源）|
| P3 检索面板 | co_search 结果 + 每发 `(world_revision, watermark, lag)` 三元组、ambiguous_keywords 展示（歧义不自动合并的可视化证词） | `WorldSearchIndex.co_search(...)` 的 `SearchPage` 字段 | ✅ 已备；view 参数等 B2 服务层（M1-016 闹铃 2 看管）|
| P4 索引健康 | 水位/滞后/追赶 ETA（用 bench_ledger 历史速率外推，不重测） | `index.watermark()` / `index.lag()` + `governance/bench_ledger.json` | ✅ 前二者已备；ETA 器 = 纯算术，随 UI 批 |
| P5 迁移审计 | 列出全部 `schema_migration_*` 审计条目（m0_023 起，m1_019 起将追加） | `world_meta` 裸 SQL（今天可用彩排脚本姿势）| ⚠️ 缺一个具名读面，见 §2-a |
| P6 归档/tombstone | 最新修订可见性、ref 入度、冷档行↔tombstone 对应 | `latest_visible(...)` / `ref_counts` / `cold_archive` | ❌ 019b/019c 之后才存在；面板骨架可先占位 |
| P7 profile 面板 | 当前 profile 全字段 + "band 更严"方向性可视化（逐数字 ≤ 条） | `resolve_runtime_profile(name)` + `DEFAULT_*` 常量 model_dump | ✅ 已备（M0-030）；方向性渲染 = 纯展示逻辑 |

## 2. Gate 后允许的最小新增 PR（仅三处，超出即范围蔓延）

a. `store.migration_audits() -> dict[str, dict]` —— `world_meta` 中
   `schema_migration_%` 键的具名只读包装（P5）。半小时内含测试。
b. `WorldSearchIndex.projection_stats() -> dict`（表行数/对象数/token 数，
   P4 用；**禁止**在此顺手加缓存或统计回填——统计也是只读投影的消费面）。
c. `store.object_revision_count(object_id) -> int`（P2/P6 共用的 revision 高度，
   当前要翻 `_latest_revision` 私名——具名化后把私名访问从场景测试里一并清掉）。

每处均按"内核私有面变更与消费方接线不同 commit"纪律独立走查。

## 3. 硬纪律（写进 M1-015 任务卡）

1. **控制台只读**：连接一律 `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`；
   任何写（含 PRAGMA synchronous 变更）= 打红。预开工件的 store 是读写类，
   控制台层禁止实例化 `SQLiteWorldStore` 做展示——用 §2 三个新读面 + 既有
   只读方法，或另立 ReadOnly 门面（继承连接工厂不改语义）。
2. **W1 三行元数据头**（policy 版本/索引水位+lag/budget_grant 余额）属 **M2-009
   看板**，不进 M1-015 控制台——此处是"两个面板头容易混"的预防性澄清：
   控制台显示"系统知道什么"，看板显示"AI 被允许看什么"。
3. 被省略内容必须显示数量与查询入口（89 条下钻承诺在控制台的镜像义务）：
   `SearchPage` 截断时 `limit` 语义由 P3 展示"已截断 n 条"。
4. 控制台不得提供"修补索引"按钮——第 18/投影纪律的唯一执法形态是
   rebuild/drop CLI；UI 里出现任何"修复"动词都属违宪审美。

## 4. 与终局标尺的关系

P1/P2/P3/P7 的展示语义已被 M1-016 骨架 A 半间接锁定（测试即规格）；
B 半四闹铃到期翻红的同批，本清单 §2-a/b/c 与 P6 占位转正必须进同一 M1-015
实现 PR 序列——**面板与场景同时绿，才许在台账把 M1-015 记 DONE**。
