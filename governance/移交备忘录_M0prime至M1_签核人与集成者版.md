# 移交备忘录 · M0′ 收官 → Gate → M1 前 48 小时（签核人与集成者双受众）

> 只读三份文件的读法：**签核人** → 本文件 §2 + `M0-022R_ratification_package.md`
> 全文；**Gate 后集成者** → 本文件 §3 + `POST_GATE_48H_施工序列.md` 全文；
> **其余所有人** → 本文件即可，细节按 §5 索引跳转。
> 治理基线：设计书 R4 为宪法之下的唯一工程权威（本备忘录不复制其正文）。

## 1. 一句话现状

R4 修改案的**全部可先行件已交付并实测**：契约层 8/8 候选冻结（快照 40 模型）、
CAM 55 项挂真测试、检索/存储预开工件在 arena 分支绿着、三张施工图、
G-M1P 压测套件（CI 降规模常热）、迁移彩排脚本（双向实跑过）、48h 时刻表、
M1-016 终局标尺（A 半 6 绿 / B 半 4 闹铃挂好）。**唯一悬置动作**：
architect-01/chief-01 在签核包 §2（批准，四步）与 §3（驳回，一步）之间二选一。

## 2. 签核人通道

| 步骤 | 动作 | 载体 |
|------|------|------|
| 审 | 三合一复审块 A/B/C 按包内命令复跑（沙箱 py3.11 下 b8 为环境项，带 `PYTHONPATH=src` 绿） | `governance/M0-022R_ratification_package.md` §1 |
| 裁 | 风险五项逐条画钩：R1 预开工件时序、R2 M1-017 题名、R3 b8、R4 回填策略、R5 编号勘误备案 | 同上 §4 |
| 批 | 单步四动作：gate 串 `M0-R2+R4-delta-candidate`→`M0-R2+R4-delta`；CAM 9 项 proposed→planned；台账公告；（若批 R2）按包 §7 草案改订设计书三处 | 同上 §2+§7 |


> **2026-09-16 晚状态更新（对表批）**：主干已孤儿重建并吸收并行会话成果——M0/M1
> 按其编号宣布闭环、M2 攻坚中、v3.0.1 裁决集裁决的是另一份同号「R4 重构方案」。
> 本备忘录的**内容**全部有效、**坐标系**以
> `governance/上游对表裁决_2026-09-16.md` 为准；48h 表降格为 R4 独有缺口施工检查单；
> R2 台账已随主干迁移（docs/specifications/），arena 程序状态以本文件 §5 为单一真源。
| 驳 | `git revert` 契约 delta + 快照再生成 + 预开工件 `20e7733` 一并回退（零残留：列只增、投影可弃、迁移幂等） | 同上 §3 |

签核前任何"转正"表述均无效——**包括本备忘录**（这就是候选状态的自我克制）。

## 3. 集成者通道（批准生效后）

```bash
# ① 复验签核产物（B0）
PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/contracts/test_m0_schema_snapshot.py tests/architecture
# ② 迁移彩排（B1；生产库副本，脚本只写副本）
PYTHONPATH=src .venv/bin/python scripts/plan_scripts/migration_drill.py --db <prod副本> [--expect-backfill N]
# ③ G-M1P 后台起算 + 基线
PYTHONPATH=src .venv/bin/python -m aios_core.bench.g_m1p --db bench/g_m1p_500k.db --revisions 500000 --out g_m1p_baseline.json
# ④ 全链回归（每块出口必跑）
.venv/bin/python -m pytest tests
# ⑤ 终局标尺：B 半四闹铃的到期声（XPASS=红）——只许摘标记不许闭嘴
.venv/bin/python -m pytest tests/scenarios/test_sports_event_world.py -rxX
```

B1–B5 块内容与出口判据：**只认** `POST_GATE_48H_施工序列.md`；施工图细节认
`governance/issues/M1-019_blueprint.md` / `M1-020_blueprint.md`；控制台面板的
读面清单认 `governance/issues/M1-015_console_read_surface_checklist.md`（本批新附，
Gate 后唯一允许新增的小读面 PR 就三处，见该文件 §3）。

## 4. 红线速查（违一条 = 回滚，无自由裁量）

1. **F3**：`g_m1p_final.json` 非 pass → M2 任何 commit 落地即违宪；机械检查点 =
   `governance/bench_ledger.json` 的 `m2_unlock`（B5 置位，CI 只认文件）。
2. **±20%**（R4-02）：进行中区块对 B1 基线漂移超限 → 一致性事件单，后续块挂起。
3. **33.5**：真相表物理删除全域禁止——`tests/architecture/test_no_object_deletion.py`
   已在 CI；迁移类 DROP 必须走 `# r4-07-exempt rename-rebuild` 显式评审注释。
4. **77/106**：触发面只认 `triggerable_commits_after`；任何"语义识别维护内容"
   的豁免实现 = 违宪（过滤器已结构性排除 MAINTENANCE，不需要也不允许聪明）。
5. **18/投影纪律**：索引/热卡/ref_counts 损坏 = drop 重建；永不与真相谈判；
   内核私有面变更与消费方接线不同 commit。
6. **台账不跑在工件前**：M1 表行翻转只随对应区块出口 commit。

## 5. 批次台账（arena 分支 `arena/01a0a638-fantonghui`，自基线 `cd8bb29`）

| commit | 批 | 工件要点 |
|--------|----|----------|
| `3d1c985` | T1–2 | 设计书 R4 拆分重构（Part1–4）、修宪案 R4 初稿、CAM 账本 |
| `6c3fbaf` | T3 | M0-023~028 候选契约 + 快照 + 六 Issue + 台账纠偏（v2.0→v3.0 基线）|
| `20e7733` | T4 | 预开工件：source_class 存储面+迁移器+触发读面；`query/search.py` 检索核（8 集成用例）|
| `3b2e713` | T5 | 签核包 + M1-019 施工图 + R4-07a 静态守卫 |
| `b2b66cf` | T6 | M1-020 施工图（摘要不回写教义）+ 签核包 §7 R2 草案 |
| `a4f1fee` | T7 | `aios_core.bench.g_m1p` + **压测逼出的 finalize 计划整改**（行值 IN→TEMP join）|
| `3d78ca9` | T9 | M0-030 profile 契约 + **补挖出的 R4-09.1 信任字段**（M0′ 8/8 收官）|
| `3ce5b2f` | T10 | POST_GATE_48H 时刻表 + B1 彩排脚本（真实落码双向实跑）|
| `c880224` | T12 | M1-016 骨架（A 半 6 绿 / B 半 strict-xfail 4 闹铃）+ 本备忘录批 |

数字基线：全量 **614 passed / 1 环境项 / 4 xfailed**；测试数轨迹 586→594→596→599→608→614。

## 6. 刻意不做清单（每条目 = 一次自我否决，防"看起来更快"）

- 未动 M1 表行 / 未改 gate 串 / 未新增 CAM 子编号（恰集由 coverage 测试锁着）；
- 未实现：world 服务层、wake/触发引擎、prune 提交口、hot_cards、控制台 UI——
  全部 Gate/B 块之后；`store.migration_audits()` 等三处小读面也只立在清单不预写；
- operations 表审计列决策**显式推迟**至 M2-002 开工周（避免与归档引擎互踩）；
- band_v0 一日回放剧本只留 harness 挂点（T6 属 M2 出口强制项，提前做=假绿温床）。

## 7. 已知限制汇总（散落各台账的集中兑现处）

b8 沙箱环境项（非回归，证据链在 DEV_LOG 三处复跑记录）；`plan_checks` 的源码
对锁依赖 .py 在场（wheel 无源码时改旁置文本）；48h 工时按单集成者口径（B3∥B4
可双轨但要重排块间依赖）；B 半闹铃的 API 形状是契约级提案——实现者可改签名，
**必须让 XPASS 发生**（改形状不摘闹铃 = 违反对拍义务）；profile 数字属工程默认
候选（签核可改数字不动形状，validator 阈值改动须重跑 `test_r4_09_*`）。
