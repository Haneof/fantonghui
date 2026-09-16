# M1-020 施工图：HotCard 实体×日热卡预计算管道（读面 ≤50ms）

> 性质：**Gate 前设计文档**。不实现、不接入、不动 M1 表行。依赖 M1-017 检索核
> （arena 分支已有预开工件 `query/search.py`，本管道以它为底座复用其全部投影
> 纪律）；上位：设计书 R4 §3.4-T2（C 方案 hot_cards 表、G 测试⑤、I 禁止三条）、
> R4-01（首字 p95≤1.0s）、W2 两段召回时间线（第 494 行）。
>
> 编号勘误同 M1-019 批的口径：一切以设计书 §3.4 实号为准，本任务即"M1-020
> HotCard 实体×日热卡预计算管道"。

## 1. 定位裁决（写死）

1. **热卡是 1 秒预算内唯一同步召回源**（T2-C 注释原文），其余深召回一律走
   异步句尾/下轮注入（W2 纪律：禁止首句因"等待检索"延迟；"先像人一样接话，
   再把功课补上"）。因此本管道的验收主指标不是吞吐而是**读路径最坏延迟**：
   `fetch(subject, entity_ids, today)` p95 ≤ 50ms @ 50 万修订，进 G-M1P 集合。
2. **热卡 = 投影的投影**。输入只有两样：world commits 重放（经
   `revisions_after()`，预开工件已就位）与检索核可见修订集。它不新增真相、
   不占用对象编号，损坏语义与 `search_*` 完全同款：整删重建，永不修补对账。
3. **摘要不回写原则（本图新增的核心教义）**：builder 让模型产出的 digest 文案
   只活在 `hot_cards.digest_json` 里；**永远不得**作为世界对象（任何
   ObjectType）提交入 store。理由：二手摘要回流世界 = AI 自食其语料，第 31 条
   append-only 保真会被"摘要的摘要"稀释成幻觉回路。世界只收一手断言
   （Claim/Observation/…），热卡只做**带指针的视图**——digest 每个槽位必须
   携带 `object_id@revision` 指针，展开仍走 `world.navigate`。
4. **迟到数据只打脏，绝不同步重建**（G 测试⑤ + I 禁止"写放大"）：任何读路径
   发现 `built_from_revision < current` 且当日窗口被新提交触碰 → 把
   `(subject, entity, day)` 记入 dirty 表即返回旧卡；重建发生在 builder 自己的
   批处理里（低峰/心跳预算下，走 C13 网关领 grant）。读路径模型调用次数 = 0。

## 2. Schema（T2-C 原文照抄 + 最小增列，全部标注来源）

```sql
CREATE TABLE hot_cards (
    subject_id TEXT NOT NULL, entity_id TEXT NOT NULL, day_us INTEGER NOT NULL,
    digest_json TEXT NOT NULL,          -- 四槽：关系标签/待兑承诺/近期事件/心理基线
    built_from_revision INTEGER NOT NULL,-- T2-C 原列：水位即出身
    stale INTEGER NOT NULL DEFAULT 0,    -- 迟到数据脏标记（G⑤ 的载体）
    PRIMARY KEY(subject_id, entity_id, day_us)
);
CREATE TABLE hot_cards_dirty (          -- builder 的消费队列，非真相，可整删
    subject_id TEXT, entity_id TEXT, day_us INTEGER,
    marked_from_revision INTEGER NOT NULL,
    PRIMARY KEY(subject_id, entity_id, day_us)
);
CREATE TABLE hot_cards_meta (
    key TEXT PRIMARY KEY, value TEXT NOT NULL   -- watermark、上次批量构建时刻、预算台账指针
);
```

不引入 FTS 影子、不动 `search_*` 表；`stale`/dirty 双写以 dirty 表为准、
`stale` 仅为读侧 1 位缓存（两表分歧时 rebuild 按 dirty 收敛——分歧本身是
测试项，不是运行时修补对象）。

## 3. 四槽位的机械抽取（映射到已冻结契约的真实字段）

| 槽位 | 机械来源（零语义判断可完成） | 备注 |
|------|------|------|
| 关系标签 | `Entity.identity_claim_refs` 指向的 Claim 文本指针 + canonical_name/aliases | 只列指针+≤40 字 excerpt，不重述 |
| 待兑承诺 | `Task`：`task_state` 非终态 ∧（`goal_ref`/`reason_refs`/`dependency_refs` 链上出现该 entity 编号）| ref 图查询，走 M0 已有引用索引 |
| 近期事件 | `EventAnchor.participant_refs ∋ entity` ∧ occurred ∈ [day−7d, day+1d] | 时间过滤直接复用 `search_occurred`（同库同水位）|
| 心理基线 | 最新未 `sealed` 的 `LifeChapter.baseline_refs` 指针集 | sealed 章节只作历史，不供当日基线 |

digest 文案层（可选的一句人话）由 builder 内**单次**模型调用生成，输入仅上表
指针展开后的 ≤1.5K tokens，输出落 `digest_json.prose`；该调用计入 C13 抽取
预算，**不在**会话首字路径。`prose` 缺失或超预算 → 卡片退化为纯指针版
（可用性优先于文采，首字预算高于一切）。

## 4. 构建与追赶

```
builder(每日 04:00 本地时区 / 低峰):
  对 active(subject)×近 90 天有触点的 entity:
    读 revisions_after(card.built_from_revision) → 触碰当日窗口? → 重建该卡
catch-up(随检索核 catch_up 同事务后标记):
  新 commit 的 occurred 落入已建卡窗口 → INSERT OR REPLACE hot_cards_dirty + stale=1
prune 联动(M1-019 就位后):
  对象被 tombstone → 该对象从后续重建中自然消失；不追溯改写旧卡的指针集
  （旧卡 revision 仍可解析——pin 语义保护；卡片换代即清洗，无迁移义务）
```

预算硬线：单次批量 ≤ `min(policy.max_cards_per_run, budget_grant.slots)`；
grant 耗尽即停、脏表残留自然滚入下轮——**热卡管道永不饿死会话路径**。

## 5. 读面 API（C10 消费形态）

```python
def fetch_hot_cards(subject, entity_ids, *, day, as_of_revision=None):
    # SELECT by PK in —— 无 JOIN 无扫描；EXPLAIN 断言 SEARCH hot_cards USING
    # PRIMARY KEY（物理计划禁令同款静态守卫扩到本表）
    # 返回：cards[] + (world_revision, built_from_revision, stale)
    # 消费方(C10)按 W2 渲染两态："已加载热卡 / 深度召回 pending"
```

延迟预算分解（p95 ≤ 50ms 的执法表）：PK 批读 ≤5ms（50 万卡实测预算）；
digest_json ≤6KB/卡 × ≤8 卡；反序列化 ≤10ms；余量留给装配层。超预算唯一
合法降级 = 减少卡数（按 entity 触点新鲜度截断），不是等重建。

## 6. 测试清单（Gate 后实现批的验收面）

1. 冷库：0 卡 fetch 返回空 + 不触发构建（读路径零副作用）
2. 构建后四槽位与源对象逐一可指认（每指针 `world.navigate` 可展开）
3. 迟到提交 → dirty 行数 +1、旧卡仍即时返回、`stale=1`；builder 跑后收敛，
   两表（dirty/stale）分歧场景强制覆盖
4. 摘要不回写：静态扫描 builder 模块，禁止出现 `world.commit`/任何对象构造
   提交调用（把 §1.3 教义变成 CI 断言，仿 R4-07a 手法）
5. EXPLAIN QUERY PLAN 断言 PK SEARCH；含 `SCAN hot_cards` 即红
6. G-M1P 扩展：50 万修订 + 50 万卡下 fetch p95≤50ms；三点位（G-M1P/M4a/
   M7-002）一致性 ±20% 沿用 R4-02 口径
7. 与 M1-019 联动：tombstone 后新卡不含该对象、旧卡指针仍可解析
8. prose 缺失/超预算 → 纯指针版退化路径

## 7. CAM 映射（Gate 后追加，不入当前账本，防未批先占）

- R4-01a：首字链路同步召回源唯一性（热卡外无同步检索调用；静态扫描 C10 侧）
- R4-01b：fetch p95≤50ms（G-M1P 集合新增点位）
- T2-G⑤：迟到数据禁同步重建（测试 3 载体）

## 8. 开工切分（Gate 后即刻可插）

- **020a** schema + builder 骨架（复用 `revisions_after`/`search_occurred`；单测 1/2/5）
- **020b** 四槽位抽取器 + catch-up 脏标记（测试 3）
- **020c** prose 单次调用 + 预算退化路径（测试 8；接 C13 grant 时与 M2-018 联调）
- **020d** 基准套件并入 G-M1P + 静态守卫扩展（测试 4/6/7）

## 9. 明确不做

- 不在卡内做任何跨实体推理/情感判定（那是 C10 装配层与 M5-004 策略学习的地盘）；
- 不把热卡升格为世界对象或新契约类型（§1.3 决定它永远是投影）；
- 不做卡的跨用户共享视图（87 条下钻权限模型未定，先不发明）；
- M1 Gate 前不写 020a–d 任何实现。
