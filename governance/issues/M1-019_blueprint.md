# M1-019 施工图：PRUNED tombstone + 引用计数冷档（分层归档，非删除）

> 性质：**Gate 前设计文档 + 静态守卫先行件**。契约层已备好（M0-023 候选冻结：
> `OperationRequest.source_class=MAINTENANCE ⇔ maintenance_class=PRUNE`），
> 运行面实现（schema 迁移、prune 提交口、冷档表、CLI、审计器）全部待 M1 Gate
> 后开工；本文件不宣称任何 M1 状态变更。
>
> 上位依据：宪法 33.5（R4 改订：物理删除 → tombstone+分层归档+三条件合取）；
> 设计书 R4 修改案 R4-07（归档审计：全库无未授权物理删除）；§3.4-T3；
> L291 三条禁止令。依赖：M1-001（Observation 接入服务——tombstone 作用对象
> 由它产生）、M0-023 运行面（已在 arena 分支预开工件就位）。

## 0. 编号勘误备案

上轮收尾把"唤醒回路接 triggerable 过滤器"误称 M1-019。对表设计书 §3.4：
唤醒/触发属 **M2-002/016/019/021**；M1-019 实名即本任务。本批按实号出件。

## 1. 核心裁决（写死，不留给实现者许愿）

1. **tombstone = 新修订，不是状态翻转。** 对目标对象 append 一条
   `revision_kind='tombstone'` 的新修订（复用 store 既有的
   `latest+1` 自动修订分配，已实测存在于 `commit()` 路径）；此前任何修订
   永不改写、永不删除——这是 M0-027 Reinterpretation"零改写历史"同构，
   也是"已确立事件/关键原话/核心证据链永存 = append-only，不是许愿"的执法点。
2. **`world_at` 双透镜下的可见性规则**：
   - `AS_KNOWN`（当时的知识）：tombstone 修订按提交序进入，读到即见"已归档"标记；
   - `ANNOTATED`（现状标注）：最新修订为 tombstone 的对象在**检索/热卡/唤醒**
     三类消费面默认过滤，但**按编号 pin 的引用永远可解析**（含 tombstone
     修订本身）——引用计数只降不删的根因。
3. **物理清除三条件合取，且执行体离线**：
   `零引用 ∧ 超龄(raw_tier_days, 默认30, 来自 runtime_profile) ∧ 用户显式授权`
   全部机械可判定才放行；放行后的动作是 **移入冷档层**（同库 `cold_archive`
   表，payload 出热表留副本指针），宪法意义上的"离线压缩"仅指冷档内的
   载荷压缩，永远不含 `DELETE`。判断权分工：大模型复盘有**提案权**
   （产出一份提案清单工件），执行前人工确认；运行路径**无一处语义判断**
   （L291 禁止令之一：禁"语义识别维护内容再豁免"）。
4. **触发风暴闭合**：`world.prune` 提交必携
   `source_class=MAINTENANCE, maintenance_class=PRUNE`（契约强检互斥已冻结），
   故经 `triggerable_commits_after()`（预开工件）对唤醒评估结构性不可见——
   复盘每 prune 一万条也不会放大成一万次唤醒（R2 永动机封死点的归档侧）。

## 2. Schema delta（存储层，不动 pydantic 契约 → 不触发契约再冻结）

```
object_revisions  + revision_kind TEXT NOT NULL DEFAULT 'content'
                    CHECK(revision_kind IN ('content','tombstone'))
                  （旧库迁移沿用 M0-023 迁移器纪律：补列→显式回填
                    'content'→重建加约束→world_meta 审计键 schema_migration_m1_019；
                    禁止 DEFAULT 静默冒充历史——DEFAULT 只在新库 DDL 里存在）

cold_archive(
    object_id TEXT NOT NULL, revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,            -- 唯一允许"搬家"的载荷
    archived_at TEXT NOT NULL,
    authz_ref TEXT NOT NULL,               -- 指向授权凭证记录的编号
    PRIMARY KEY(object_id, revision)
)                                          -- 冷档行与 tombstone 修订一一对应，
                                           -- 双向孤儿 = 审计红灯

ref_counts(object_id TEXT NOT NULL PRIMARY KEY,
            in_degree INTEGER NOT NULL DEFAULT 0,
            recomputed_watermark INTEGER NOT NULL DEFAULT 0)
            -- 引用计数是投影不是真相：与检索核同款水位/追赶/整删重建纪律，
            -- 永不与"真值"对账；损坏=drop重建，不必修补
```

- tombstone 修订的 payload 仍是合法对象模型（同一 `object_type`，内容可全
  同上一修订或加注记字段既有空位），`revision_kind` 只活在表里；对象模型
  **不加** `is_pruned` 字段——避免契约漂移，模型对归档无感知。
- 读面：`resolve(ObjectRef pinned)` 语义不变；新增
  `latest_visible(object_id, *, include_tombstones=False)` 供检索/热卡消费；
  store 层**不存在** `delete_object` 这个名字的公开方法（命名即防线）。

## 3. 检索核接线（对预开工件 `query/search.py` 的增量，Gate 后实施）

- 抽取器写 postings 前查 `revision_kind`：tombstone 修订 → **删除该
  (object_id, revision) 的 doc 行并回退到上一 content 修订的可见性由
  `include_tombstones=False` 消费方自决**；即冷档对象自然退出共现交集，
  无需 co_search 加特判——投影纪律统一"索引=对可见修订的函数"。
- `search_meta` 水位语义不变；`ref_counts` 不参与检索打分（防止计数投影
  损坏污染召回），只做清除前置条件。

## 4. CLI 与审计器（执法件）

```
aios prune propose  --from-review <复盘提案清单.json>  → 提案工件事务（只读校验+人读摘要）
aios prune apply    --ticket <人工签认票据>            → 三条件机器复核 → tombstone 提交
aios prune sweep    --profile band_v0                   → 冷档载荷压缩（gzip 载荷，绝不 DELETE）
aios audit archive  → R4-07 闸门：全库无未授权物理删除扫描
```

审计器三层，全部机械：
1. **静态层（本批先行落码，不等 Gate）**：`tests/architecture/test_no_object_deletion.py`
   扫描 `src/aios_core/**/*.py` 源码，断言不存在针对 `world_objects` /
   `object_revisions` 的 `DELETE FROM` / `DROP TABLE`（投影表 `search_*`、
   冷档 `cold_archive` 与迁移重建临时表不在禁止集——它们本来就不是真相）。
2. **运行层**：每次审计前后 `revision 行数单调不减` ∧ `对象编号集合不变`
   （tombstone 只增不减）；违例=红灯熔断。
3. **对应层**：`cold_archive` 每行 ↔ 存在其编号的 tombstone 修订；反向：每
   条 tombstone 的**前一** content 修订载荷必须在冷档在场。孤儿双向=红灯。

## 5. 验收映射（CAM 追加 3 项，Gate 后转正）

| CAM 项 | 断言 | 载体 |
|--------|------|------|
| R4-07a | 静态：src 全域无对象表 DELETE/DROP | test_no_object_deletion（**本批已落码**）|
| R4-07b | 动态：prune 全链路后修订行数单调不减、pin 引用 100% 可解析 | 集成测试（Gate 后）|
| R4-07c | 触发闭合：万条 tombstone 提交的 `triggerable_commits_after` 返回空 | 集成测试（Gate 后）|

## 6. 开工切分与出口判据（Gate 后即刻可插）

- **019a** schema 迁移器（复用 `_ensure_source_class_schema` 的审计模式）
- **019b** `world.prune` 提交口 + `latest_visible` 读面（单测 5 例）
- **019c** ref_counts 投影（commit 增量维护 + rebuild/drop；含损坏=重建测试）
- **019d** 审计器运行层+对应层 + CLI apply 三条件复核（风暴测试 1 万条：
  `triggerable_commits_after` 空返回 + co_search p95 不因冷档在场退化，
  并入 G-M1P 修订版跑）
- 出口判据 = R4-07a/b/c 全绿 + 风暴测试 + band_v0 冒烟（M2 起强制项的首个
  预演在此任务顺带积累，不替代 M2-GATE）。

## 7. 明确不做

- 不做 ML 语义清洗判断（那是 M3-014 影子双世界的实验对象，不是本任务的执法者）；
- 不引入新对象类型（提案/票据是工件文件与 CLI 记录，不入世界契约——避免
  未批契约膨胀）；
- 不动 `world_commits` 既有语义；不在 M1 Gate 前实现任何上表 019a~d。
