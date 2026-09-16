# Gate 后 48 小时施工序列（POST_GATE_48H）

> 性质：**开工验证与关键路径闭合序列**，不是"M1 完成"许诺。前提唯一：签核包
> §2 四步执行完毕（含 R2 批准时的设计书改订）。每个区块给出**出口判据 = 可直接
> 粘贴的命令**；红灯 = 立即执行的冻结动作，写死，不留临场裁量。
>
> 依据：设计书 R4 §2.4（profile 规则）、§3.4-T2（G-M1P/T6）、L49（双 profile）、
> F3（读面必须先于 M2 扛负载）；M1-019/020 施工图；M0-023 issue 预开工件记录；
> `aios_core.bench.g_m1p`。M1 表行状态翻转只允许发生在对应区块出口判据通过
> 之后、且随该区块 commit 一并入账——台账不得跑到工件前面。

## 时刻表（H+0 起算 = 签核 commit 落地）

| 块 | 窗口 | 内容 | 出口判据（命令） | 红灯动作 |
|----|------|------|------------------|----------|
| B0 | 0–1h | **转正收尾**：签核包 §2 步1–4 已由签核人执行；集成者复验 gate 串/CAM 状态/设计书改订三处 | `pytest -q tests/unit/contracts/test_m0_schema_snapshot.py tests/architecture` | 任一不符 → 冻结全序列，回签核人 |
| B1 | 1–4h | **迁移彩排**（生产库副本）+ **G-M1P 生成后台起算**（目标硬件） | 彩排：`python scripts/plan_scripts/migration_drill.py --db <prod副本>`（见 §1 附脚本）；压测：`PYTHONPATH=src python -m aios_core.bench.g_m1p --db bench/g_m1p_500k.db --revisions 500000 --out g_m1p_baseline.json &` | 彩排审计 JSON 与 `backfilled_rows` 预期不符 → 生产库列为不可迁移态，M1 只在新库推进；压测进程死亡 → 换硬件重跑，不算红 |
| B2 | 4–16h | **内核服务化接线**：M1-012（`world_search` 服务层 = `co_search` 适配 + `world.navigate` 指针展开）、M1-013（下钻 = evidence.read/trace，骨架直接复用 bench `one_drill` 的 ≤8-ref 展开纪律）、M1-014（水位升格：所有读响应强制 `(world_revision, watermark, lag)` 三元组——设计书 §222 行已把这定为 M0-023 级契约） | `pytest -q tests/integration -k "m1_012 or m1_013 or m1_014 or search"`；三元组缺失 = 测试红 | 服务层要求改内核私有面 → **拒**，内核改动走独立小评审（投影纪律不允许被消费方反向污染） |
| B3 | 16–30h | **主线首批**：M1-001（Observation 接入+去重，**profile 消费首站**：C01 摄入硬约束读 `DEFAULT_*` profile，丢帧必录在此落地）→ M1-002（Entity/别名/身份服务，读写 `search_alias` 同一张表——索引与服务的别名分叉从 schema 层禁止）→ M1-005（Claim 服务：第三方来源默认 `corroboration_required=True`，`may_drive_external_action` 进创建路径返回值） | 各任务按总工程师版任务书自带验收 + `pytest -q tests/integration -k "m1_001 or m1_002 or m1_005"`；B3 末重跑 `g_m1p_baseline`（queries 1200）确认服务化未把 p95 拉红 | p95 相对 B1 基线漂移 >±20% → 触发 R4-02 一致性问题单，B4 挂起 |
| B4 | 30–40h | **归档与热卡开面**：019a（object_revisions `revision_kind` 迁移器——逐字套用 M0-023 审计模式，`schema_migration_m1_019`）+ 019b（`world.prune` 提交口 + `latest_visible` 读面，单测 5 例）；020a（hot_cards 三表 + builder 骨架 + PK 读面） | `pytest -q tests/integration -k "prune or hot_cards"` + `plan_checks` 全真 + R4-07a 守卫绿（新增 DROP 必须先过 `r4-07-exempt` 评审注释） | 019a 彩排失败处置同 B1（新库先行） |
| B5 | 40–48h | **闭合与台账**：019c（ref_counts 投影，损坏=drop 重建测试必含）；G-M1P **终跑**（含 B2–B4 全部改动）；`governance/bench_ledger.json` 初始化（G-M1P p95 数字入册，M4a/M7 槽位=pending）；T6 profile 冒烟段：bench 报告新增 `profile` 节（virtual/band_v0 各一跑，数字超限=红灯机制就位，剧本一天回放留 M2）；M1 表行批量入账 | `python -m aios_core.bench.g_m1p --db bench/g_m1p_500k.db --revisions 500000 --out g_m1p_final.json` → `verdict: pass`；`consistency.verdict: pending_followup`（此时只该是这个值）| 终跑 fail → 只允许内核修复窗口（回 B2 owner），**M2 禁止启动**条款自动生效（F3） |

## 1. B1 彩排脚本（唯一新增执行物，其余全是既落码工件）

```python
# scripts/plan_scripts/migration_drill.py —— 对生产库副本跑旧库迁移并核对审计
# 用法: python scripts/plan_scripts/migration_drill.py --db copy_of_world.db [--expect-backfill N]
import argparse, json, sqlite3, shutil, tempfile
from pathlib import Path
from aios_core.storage import SQLiteWorldStore
ap = argparse.ArgumentParser()
ap.add_argument("--db", type=Path, required=True); ap.add_argument("--expect-backfill", type=int)
a = ap.parse_args()
work = Path(tempfile.mkdtemp()) / "drill.db"; shutil.copy2(a.db, work)  # 生产库只读，彩排必在副本
before = sqlite3.connect(work).execute("PRAGMA table_info(world_commits)").fetchall()
has_col = any(r[1] == "source_class" for r in before)
store = SQLiteWorldStore(work)
audit = json.loads(sqlite3.connect(work).execute(
    "SELECT value FROM world_meta WHERE key='schema_migration_m0_023'").fetchone()[0]) if not has_col else None
revs = store.current_world_revision()
trig = store.triggerable_commits_after(0, limit=revs) if hasattr(store, "triggerable_commits_after") else []
assert store.current_world_revision() == revs, "彩排本身改写了修订号=严重异常"
if audit: assert not a.expect_backfill or audit["backfilled_rows"] == a.expect_backfill
print(json.dumps({"pre_migrated": has_col, "audit": audit, "revisions": revs,
                  "triggerable_visible": len(trig)}, ensure_ascii=False))
```

本脚本已随本批**真实落码并双向彩排通过**（旧库副本→迁移+审计核对；新库副本
→`pre_migrated=true` 直通），B1 当天无未验证物。签名注：两读面的 `limit` 均为
keyword-only（`triggerable_commits_after(wr, *, limit=500)`、
`revisions_after(wr, *, limit=5000)`），与脚本一致。

## 2. 冻结规则（写死，不接受临场豁免）

1. **F3 宪法**：`g_m1p_final.json` 非 pass 之前，M2 任何 commit 落地 = 违宪，
   CI 以 gate 文件存在性做机械检查（`governance/bench_ledger.json` 的
   `m2_unlock: true` 字段由终跑 pass 后置位）。
2. 内核私有面变更与消费方接线**不同 commit**；预开工件的测试（检索 8 用例）
   在任何区块必须全绿，跳测合入 = 回滚。
3. 生产库迁移只在 B1 彩排通过 + 双人确认后备援；失败回滚 = 换新库重放
   commits（append-only 保证可重放——这是"永存"给的退路，不是运气）。
4. `operations` 表审计加列决策（M0-023 issue 留白）显式**不在本 48h**：定于
   M2-002 开工周第一评审，避免触发引擎与归档引擎互踩。
5. 每区块出口 commit 附带该块全部测试命令输出摘录入 DEV_LOG——48h 结束时的
   DEV_LOG 应能独立复述这四天发生了什么。

## 3. 48h 之后的排期接口（只指路，不展开）

- M1 余量（003/004/006~011/015/016 与 019d/020b-d）按设计书 Part4 W1–W6 的
  周排布；运动会→体测修正贯穿案例（M1-016）为 M1 出口主戏。
- T6 一日回放剧本、M2-002/016/019/021 唤醒线、V31 场景包（M4-006）各按
  既有施工图/issue 挂点。
- `consistency` 的 M4a/M7 槽位由后续跑 `run_bench` 同预算函数回填，±20% 口径
  从 B1 起就对三点位同时生效。
